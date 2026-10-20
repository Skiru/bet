#!/usr/bin/env python3
"""Measure this model's probability calibration from the cache alone.

`run_backfill.py` does the same job properly — it pulls each league season and
replays it. It also needs Sofascore, and Sofascore is the one thing this
pipeline cannot rely on being reachable. This script needs no network and no
prices: calibration is a question about pairs of (prediction, outcome), and
every pair it needs is already in `sofa.db`.

That distinction is the point. The reason `config/sofa_market_reliability.json`
has been `{}` since the pipeline was written is not that the measurement is
hard, it is that the only path to it went through a provider that has been
403-ing. Every row the sheet produces therefore carries `UNFITTED_CONSTANTS`
and an uncorrected `p_central`, and the coupon inherits the consequence: on
2026-09-18 every one of its rows sat above the devigged market price, median
ratio 1.43, with nothing measured to say whether that is edge or error.

Method, mirroring `run_sheet.py` exactly so that what is measured is what
ships:

  * for each finished match in the cache, rebuild each side's sample from
    matches strictly **before** that match's kickoff — the same chronological
    rule the sampler uses, so no row is scored against its own result;
  * shrink toward the league baseline with the same K_CENTRE;
  * take SHEET's own predictive sd (`engine.sheet_predictive_sd`: the
    Poisson floor and, for football counts, the variance scaled by
    centre / mean) and SHEET's own estimator (`engine.sheet_count_p_raw`:
    the negative binomial for NEGATIVE_BINOMIAL_METRICS, else the normal
    with the support floor; the empirical-frequency metrics through
    `p_empirical_centred_raw`, as SHEET prices a rung with no price) against
    the same `winning_boundary`. Until 2026-10-02 this was a support-floored
    normal on the unscaled variance for every market, so a replayed NB
    metric's stored p_central was not the p SHEET computes, and the curve
    fit_confidence keys on that stored p described another model;
  * refuse the same rungs `outside_model_resolution` refuses;
  * settle against what actually happened.

`market_p` is NULL on every row: there are no historical Superbet prices
(PLAN §A9). So this supports the calibration curve and K_CENTRE, and it
cannot support K_PRICE or MAX_LADDER_SIGMA, which need a live ladder. Those
stay NOT_FITTED, and `fit_constants.py` already says so.

Since the stats-only rating prices (epochs.TENNIS_RATING_PRICES_FROM_UTC,
2026-10-07) the tennis games rows are priced as SHEET prices them: the
rating's neighbours as of the match's UTC day (tennis_rating.AsOfRating, the
book and neighbour table grown from tennis_rating.load_history, never a later
match) for games_won_for, handicap_games and most_games, and a 50/50 mix with
the NB for games_total (`--tennis-rating`). The football joints (both_over_ /
most_ / handicap_) of the bases in epochs.DERIVED_MARGINAL_CENTRES_METRICS are
replayed from the marginal rows' centres on request (`--derived`).

Audit 2026-10-13 A6 / B1 / B2 / B5, all opt-in (off = the rows as before,
byte for byte): `--football-rating` prices every football marginal row with
SHEET's live centre - the rating book replayed to each match's UTC day start,
blended at W_FOOTBALL_RATING - through one hook, `live_centre`, which also
applies `--rated-scope`, `--venue-prior`, `--game-state`,
`--count-stretch` (epochs.FOOTBALL_COUNT_STRETCH) and `--goals-stretch`
(epochs.FOOTBALL_GOALS_STRETCH) as SHEET does; `--player-stretch`
(epochs.FOOTBALL_PLAYER_STRETCH) multiplies a footballer's shots centre by
his side's supremacy term, read off a rating book replayed for the player
targets;
`--tennis-set-ratings` adds the per-set games and sets_total rows, priced
off the tennis rating's neighbours (tennis_rating.SET_RATING_PRICED_MARKETS).

Football player markets (F54, since 2026-10-03) are replayed beside the team
markets, from the cached `/lineups` - see `build_player_rows`. Their rows
carry the same marking (run_date 'cache-calibration', p_bar = p_central,
market_p NULL); the subject is the player's normalised Sofascore name.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import math
import sqlite3
import statistics
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

from bet.sofa import epochs
from bet.sofa import tennis_aces_opponent as aces_opp
from bet.sofa.atomic import write_atomic
from bet.sofa.comparability import (
    SAME_COMPETITION_METRICS,
    MatchKind,
    match_kind,
    pick_same_competition,
)
from bet.sofa.config import SofaConfig, config_path
from bet.sofa.contracts import GapReason
from bet.sofa.count_dispersion import DispersionTable
from bet.sofa.count_dispersion import load_table as load_dispersion_table
from bet.sofa.count_stretch import CountStretchTable
from bet.sofa.count_stretch import is_total as count_stretch_is_total
from bet.sofa.count_stretch import load_table as load_count_stretch_table
from bet.sofa.cup_strength import CupStrength
from bet.sofa.cup_strength import apply as apply_cup_strength
from bet.sofa.cup_strength import load as load_cup_strength
from bet.sofa.derived import (
    SideStats,
    load_side_correlations,
    marginal_centred_stats,
)
from bet.sofa.derived import probability as derived_probability
from bet.sofa.engine import (
    outside_model_resolution,
    p_empirical_centred_raw,
    sheet_count_p_raw,
    sheet_predictive_sd,
    uses_empirical_frequency,
    winning_boundary,
)
from bet.sofa.epochs import DERIVED_MARGINAL_CENTRES_METRICS
from bet.sofa.football_rating import (
    RATED_SCOPE_MARKETS,
    VENUE_PRIOR_MARKETS,
    W_FOOTBALL_RATING,
    FootballForecast,
    FootballResult,
    RatingBook,
)
from bet.sofa.football_rating import load_history as load_football_history
from bet.sofa.game_state import GameStateTable
from bet.sofa.game_state import load_table as load_game_state_table
from bet.sofa.goals_stretch import GoalsStretchTable, stretch_supremacy
from bet.sofa.goals_stretch import load_table as load_goals_stretch_table
from bet.sofa.joint import build_joint
from bet.sofa.listing_index import entity_indexed_events, listed_events_by_id
from bet.sofa.metrics import (
    FOOTBALL_METRICS,
    calculate_cards_points,
    extract_flat_statistics,
    extract_metric,
    goal_score_inconsistent,
    infer_best_of,
    regulation_score,
    stat_is_untracked,
    zero_pair_not_recorded,
)
from bet.sofa.opponent_correction import SampleCorrector, corrected_metric
from bet.sofa.per_market_k import k_for_market
from bet.sofa.player_stretch import PlayerStretchTable
from bet.sofa.player_stretch import load_table as load_player_stretch_table
from bet.sofa.players import (
    PLAYER_METRICS,
    extract_player_metric,
    is_player_metric,
    match_player,
    squad_statistics,
    started,
)
from bet.sofa.rating_weight import RatingWeightTable
from bet.sofa.rating_weight import blend as rating_blend
from bet.sofa.rating_weight import load_table as load_rating_weight_table
from bet.sofa.samples import (
    FRIENDLY_COMPETITION_IDS,
    INDEXED_HISTORY_LIMIT,
    MIN_HOURS_BETWEEN_MATCHES,
    PLAYER_WIDE_SAMPLE_N,
    _competition_id,
    finish_history,
    one_listing_per_match,
)
from bet.sofa.season_phase import SeasonPhaseTable, phases_by_event
from bet.sofa.season_phase import apply as apply_season_phase
from bet.sofa.season_phase import load_table as load_season_phase_table
from bet.sofa.settle import is_completed_event, settle, surfaces_comparable
from bet.sofa.supremacy_stretch import stretch_supremacy as side_or_home_supremacy
from bet.sofa.tennis_aces_opponent import ACES_MARKETS
from bet.sofa.tennis_prior import load_tier_baselines, tier_prior
from bet.sofa.tennis_rating import (
    RATING_PRICED_MARKETS,
    SET_RATING_PRICED_MARKETS,
    W_GAMES_TOTAL_RATING,
    AsOfRating,
    MatchForecast,
    load_coefficients,
    load_history,
    start_for_rule,
)

# Metric base -> Sofascore statistics key. Goals are not here: they come off
# the listing, which covers twenty times more matches than /statistics does.
STAT_KEYS = {
    "corners": "cornerKicks",
    "shots": "totalShotsOnGoal",
    "shots_on_target": "shotsOnGoal",
    "fouls": "fouls",
    "offsides": "offsides",
    # 2026-09-25 coverage audit; see metrics.py. Without these the new
    # metrics would never get a league baseline or a confidence curve.
    "saves": "goalkeeperSaves",
    "throw_ins": "throwIns",
    "goal_kicks": "goalKicks",
    "tackles": "totalTackle",
    "aces": "aces",
    "double_faults": "doubleFaults",
    "games": "gamesWon",
}

SPORT_OF_BASE = {
    "corners": "football",
    "shots": "football",
    "shots_on_target": "football",
    "fouls": "football",
    "offsides": "football",
    "saves": "football",
    "throw_ins": "football",
    "goal_kicks": "football",
    "tackles": "football",
    "cards_points": "football",
    "goals": "football",
    "aces": "tennis",
    "double_faults": "tennis",
    "games": "tennis",
}

# The football per-half bases ("goals_1h", "corners_2h", ...): every
# FOOTBALL_METRICS `<base>_for` whose scope is a half. Replayed with
# `--halves include` (opt-in, 2026-10-04; match_values always reads them, so
# regrade_settled can grade such rows). Without it the replay reads the ALL
# period only, so a per-half market's curve comes from live SETTLE alone - a
# few hundred rows a bucket at best - and where a bucket falls under
# fit_confidence.MIN_MARKET_BUCKET CONFIDENCE reads the football pool instead
# (goals_1h_total UNDER at 0.80-0.85 printed 0.815 / 0.841 from
# pooled:football on 2026-10-03; the replay measured 0.812 / 0.841 there, so
# the pool was not the error - data/night_2026-10-03/g1h/). Each half value is
# read with metrics.extract_metric, the function SAMPLES and SETTLE call: the
# listing's period1 / period2 for goals, /statistics "1ST" / "2ND" for the
# rest, with its refusals (a negative corrected half score, a half that does
# not add up with its complement to ALL, the placeholder zero, a match that
# went to extra time for the non-goal counts).
HALF_BASES: tuple[str, ...] = tuple(
    sorted(
        metric[: -len("_for")]
        for metric in FOOTBALL_METRICS
        if metric.endswith("_for") and ("_1h_" in metric or "_2h_" in metric)
    )
)

# The sheet's own default when nothing is fitted. Calibrating against a
# different value would measure a model that does not ship.
# The pipeline's per-side tennis games market is `games_won_for`, not
# `games_for`. A curve keyed on a name the engine never looks up is a
# correction that silently does nothing, which is worse than no curve at all
# because the artifact then claims to be calibrated.
MARKET_NAME_OVERRIDES = {
    ("games", "for"): "games_won_for",
    ("games_set1", "for"): "games_won_set1_for",
    ("games_set2", "for"): "games_won_set2_for",
    ("games_set3", "for"): "games_won_set3_for",
}


def market_name(base: str, suffix: str) -> str:
    return MARKET_NAME_OVERRIDES.get((base, suffix), f"{base}_{suffix}")


# Audit 2026-10-13 B5 (--tennis-set-ratings, epochs.TENNIS_SET_RATING_PRICES):
# the tennis per-set games and the number of sets, read off the set score of
# the listing (metrics.extract_metric, as SAMPLES and SETTLE read them), and
# which of a base's two markets SHEET prices: games_setN_total and
# games_won_setN_for (set three: the player's games only - Superbet quotes no
# set-three total), sets_total (no per-side market). Absent unless the flag is
# given, so the default replay is byte for byte the one before it.
SET_BASE_MARKETS: dict[str, tuple[str, ...]] = {
    "games_set1": ("for", "total"),
    "games_set2": ("for", "total"),
    "games_set3": ("for",),
    "sets": ("total",),
}


def set_values(event: dict[str, Any]) -> dict[str, tuple[float, float]]:
    """(home, away) per SET_BASE_MARKETS base of one finished tennis match. A
    set that was not played, a match tiebreak and a score that is no set score
    give no value (extract_metric's refusals), never zero. ``sets`` is the
    sets each side won (``current``), kept only when they add up to the sets
    the listing shows - its total is what sets_total settles on.

    Best-of-three only (metrics.infer_best_of == 3), as SAMPLES scopes a
    best-of-three fixture's sample and the rating models it: a best-of-five
    match always has >= 3 sets, so a sets_total row of one read off a
    best-of-three sample (UNDER 2.5 at p ~0.45, realised ~0) wrote 6,688
    misgraded rows into the 2026-10-14 night replay (Grand Slams, Next Gen
    Finals) and Superbet never quotes 2.5 there; its sets in a player's
    history would equally bend a best-of-three fixture's sample. A format
    the listing cannot tell (None) is not guessed."""
    out: dict[str, tuple[float, float]] = {}
    if infer_best_of(event) != 3:
        return out
    for index in (1, 2, 3):
        metric = f"games_won_set{index}_for"
        home = extract_metric(metric, "tennis", {}, None, event, True)
        away = extract_metric(metric, "tennis", {}, None, event, False)
        if isinstance(home, float) and isinstance(away, float):
            out[f"games_set{index}"] = (home, away)
    played = extract_metric("sets_total", "tennis", {}, None, event, True)
    won_home = (event.get("homeScore") or {}).get("current")
    won_away = (event.get("awayScore") or {}).get("current")
    if (
        isinstance(played, float)
        and isinstance(won_home, int | float) and not isinstance(won_home, bool)
        and isinstance(won_away, int | float) and not isinstance(won_away, bool)
        and float(won_home) + float(won_away) == played
    ):
        out["sets"] = (float(won_home), float(won_away))
    return out


# The tennis serve bases read with --tennis-serve-markets: the per-set aces and
# double faults and the aces + double faults quantity (serve_points), match and
# per set - metrics.TENNIS_METRICS' serve markets other than the full-match
# aces / double faults (STAT_KEYS). Until 2026-10-17 the replay never read them,
# so their curves came from live SETTLE alone (a bucket below 0.60, nothing a
# coupon could print) and CONFIDENCE refused them for good.
SERVE_BASES: tuple[str, ...] = (
    "aces_set1", "aces_set2", "double_faults_set1", "double_faults_set2",
    "serve_points", "serve_points_set1", "serve_points_set2",
)


def serve_values(
    event: dict[str, Any], statistics_json: str | None
) -> dict[str, tuple[float, float]]:
    """(home, away) per SERVE_BASES base of one finished tennis match, read by
    metrics.extract_metric exactly as SAMPLES reads a sample and SETTLE grades
    a row (a set nobody reported, a missing half of aces + double faults: no
    value, never zero). Any format: a set-1 / set-2 serve count is the same
    quantity in a best-of-five, and SAMPLES scopes the format itself."""
    out: dict[str, tuple[float, float]] = {}
    if not statistics_json:
        return out
    try:
        flat = extract_flat_statistics(json.loads(statistics_json))
    except ValueError:
        return out
    for base in SERVE_BASES:
        metric = market_name(base, "for")
        home = extract_metric(metric, "tennis", flat, None, event, True)
        away = extract_metric(metric, "tennis", flat, None, event, False)
        if isinstance(home, float) and isinstance(away, float):
            out[base] = (home, away)
    return out


# The fallback, used only when nothing has been fitted yet. The shipped value
# is read from config/sofa_engine_constants.json — see k_centre_for.
K_CENTRE = 10.0
SAMPLE_N = 10
MIN_SAMPLE = 8


def k_centre_for(sport: str, constants: dict[str, Any] | None = None) -> float:
    """The K_CENTRE this sport actually ships with.

    This module's docstring promises it mirrors run_sheet "exactly so that what
    is measured is what ships", and until 2026-09-18 it did not: run_sheet read
    the fitted constant while this replayed every row at a hardcoded 10.0. The
    gap became material the moment K was fitted per sport — football ships 25
    and tennis 2 — so the reliability curve was describing a model nobody runs
    (F47, the same family as the two naming breaks this file already records).

    Order matters: the K fit itself recomputes the centre for every K on the
    grid from (sample_mean, sample_size, prior) and never reads the stored
    p_central, so it is unaffected by this. Only the reliability curve is, and
    it is fitted from these rows. Run calibrate -> fit_constants; if K moves,
    run the pair again so the curve describes the new K.
    """
    if constants is None:
        constants = _load_engine_constants()
    entry = constants.get("K_CENTRE")
    if isinstance(entry, dict):
        by_sport = entry.get("by_sport")
        if isinstance(by_sport, dict):
            value = by_sport.get(sport)
            if isinstance(value, int | float) and not isinstance(value, bool):
                return float(value)
        value = entry.get("value")
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    return K_CENTRE


def _load_engine_constants() -> dict[str, Any]:
    path = config_path("sofa_engine_constants.json")
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


@dataclass(frozen=True)
class Played:
    event_id: int
    timestamp: int
    home_id: int
    away_id: int
    sport: str
    competition_id: int | None
    values: dict[str, tuple[float, float]]
    # comparability.match_kind, so the replayed history is the one SAMPLES
    # builds: a FRIENDLY never enters a side's history, and a goal sample is
    # the side's REGULAR matches of the fixture's competition when it has
    # enough of them (comparability.SAME_COMPETITION_METRICS, 2026-10-04).
    kind: str = MatchKind.REGULAR
    # tennis only: what tennis_rating.TennisRatingModel.forecast is asked
    tennis: TennisContext | None = None


@dataclass(frozen=True)
class TennisContext:
    """The fixture facts the sheet hands the rating (run_sheet.tennis_forecast):
    the category's name (tier), the ground type (surface), and best of five,
    which the rating does not model."""

    category_name: str
    ground_type: str | None
    best_of_five: bool
    # metrics.infer_best_of (3 / 5 / None): what --tennis-sample-scope
    # matches a past match's format against, as SAMPLES does
    best_of: int | None = None


def match_values(
    event: dict[str, Any],
    sport: str,
    statistics_json: str | None,
    incidents_json: str | None,
) -> dict[str, tuple[float, float]]:
    """(home, away) per base quantity of one finished match, as the replay
    grades it. Its own function so that scripts/sofa/regrade_settled.py
    re-grades a cache-calibration row with exactly the code that wrote it."""
    values: dict[str, tuple[float, float]] = {}

    if sport == "football" and not goal_score_inconsistent(event):
        # The same refusal extract_metric applies (review round 2,
        # 2026-10-04: the replay read Buxton - South Shields as 0-2 while
        # SAMPLES and SETTLE refuse its self-contradicting score).
        score = regulation_score(event)
        if score is not None:
            values["goals"] = score

    all_period: dict[str, tuple[float, float]] = {}
    flat: dict[str, dict[str, tuple[float, float]]] = {}
    if statistics_json:
        try:
            flat = extract_flat_statistics(json.loads(statistics_json))
        except ValueError:
            flat = {}
        all_period = flat.get("ALL", {})
        for base, key in STAT_KEYS.items():
            pair = all_period.get(key)
            # The same placeholder-zero refusals the sheet applies.
            if (
                pair is not None
                and not stat_is_untracked(key, pair)
                and not zero_pair_not_recorded(key, all_period)
            ):
                values[base] = (float(pair[0]), float(pair[1]))
    if incidents_json:
        try:
            points = calculate_cards_points(json.loads(incidents_json), all_period)
        except ValueError:
            points = None
        if points is not None and not isinstance(points, str):
            values["cards_points"] = (float(points[0]), float(points[1]))
    if sport == "tennis" and "games" in values:
        # Games as extract_metric reads them for SAMPLES and SETTLE: the set
        # score (a match tiebreak one game), gamesWon only where the sets are
        # unreadable. STAT_KEYS' gamesWon read 6-7 2-6 as 19 (event
        # 17149657). Only where /statistics gave a games value, as before:
        # reading every match off its set score added ~145k tennis matches
        # (6.7M rows) to the replay - a population change to be measured on
        # its own, not slipped into a refit (2026-10-04 night).
        home = extract_metric("games_won_for", "tennis", flat, None, event, True)
        away = extract_metric("games_won_for", "tennis", flat, None, event, False)
        if isinstance(home, float) and isinstance(away, float):
            values["games"] = (home, away)
        else:
            values.pop("games", None)
    if sport == "football":
        values.update(half_values(event, flat))
    return values


def half_values(
    event: dict[str, Any], flat: dict[str, dict[str, tuple[float, float]]]
) -> dict[str, tuple[float, float]]:
    """(home, away) per football per-half base (HALF_BASES) of one finished
    match, read by metrics.extract_metric exactly as SAMPLES reads a sample
    observation and SETTLE grades a live row. A base either side of which
    extract_metric refuses is absent, never zero."""
    out: dict[str, tuple[float, float]] = {}
    for base in HALF_BASES:
        home = extract_metric(f"{base}_for", "football", flat, None, event, True)
        away = extract_metric(f"{base}_for", "football", flat, None, event, False)
        if isinstance(home, float) and isinstance(away, float):
            out[base] = (home, away)
    return out


REPLAYED_SPORTS = ("football", "tennis")

# Subtrees of a Sofascore event no replay reader looks at (names in every
# language, kit colours, a team's sub-teams and country). Dropped at load:
# they were ~half of every held event.
_DISPLAY_KEYS = frozenset({"fieldTranslations", "teamColors", "subTeams"})
_TEAM_DISPLAY_KEYS = _DISPLAY_KEYS | {"country"}


def _event_sport(event: dict[str, Any]) -> str | None:
    sport = (
        ((event.get("tournament") or {}).get("category") or {}).get("sport") or {}
    ).get("slug")
    return sport if isinstance(sport, str) else None


def _without(value: Any, drop: frozenset[str]) -> Any:
    if isinstance(value, dict):
        return {k: _without(v, _DISPLAY_KEYS) for k, v in value.items()
                if k not in drop}
    if isinstance(value, list):
        return [_without(v, _DISPLAY_KEYS) for v in value]
    return value


def slim_event(event: dict[str, Any]) -> dict[str, Any]:
    """The event without its display-only subtrees (_DISPLAY_KEYS anywhere,
    and a team's country)."""
    out: dict[str, Any] = {}
    for key, value in event.items():
        if key in _DISPLAY_KEYS:
            continue
        drop = _TEAM_DISPLAY_KEYS if key in ("homeTeam", "awayTeam") else _DISPLAY_KEYS
        out[key] = _without(value, drop)
    return out


def load_cache(
    db_path: Path, dropped_out: set[int] | None = None,
    tennis_sets: bool = False,
    since_ts: int | None = None,
    until_ts: int | None = None,
    tennis_serve: bool = False,
    sports: tuple[str, ...] = (),
) -> list[Played]:
    """Every finished cached match, one listing per match.

    `dropped_out`, when given, receives the event ids the duplicate-listing
    collapse removed, so write_settled can delete the replay rows an earlier
    run stored under them.

    `tennis_sets` (--tennis-set-ratings): every completed tennis match also
    carries its set bases (set_values) - read off the listing, as SAMPLES
    reads them, so a match without /statistics enters the replay for those
    bases alone (its other bases' histories are untouched: they are keyed by
    base).

    `tennis_serve` (--tennis-serve-markets): every tennis match with
    /statistics also carries its SERVE_BASES (serve_values).

    `sports` (a measurement): only these of REPLAYED_SPORTS are held; empty
    = all of them. A side's history is keyed by team, so a tennis-only load
    is the same tennis replay.

    `since_ts` / `until_ts` (a smoke run's --history-from / --to): only the
    matches kicking off inside them are held - a light replay whose samples
    are cut at since_ts, never a rebuild.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        # The first *finished* copy of each event on any cached page, then the
        # listed-event index (listing_index.py), whose newer finished copy
        # wins. Only finished copies are kept: the replay drops the rest below
        # anyway, and keeping the first copy of any status let a stale
        # pre-match copy (a `next` page) block the finished one - on a later
        # page or in the index (2026-10-02 review, F5).
        # Only the sports replayed below, and without the display-only
        # subtrees (slim_event): 1.41M whole events held 25 GB on 2026-10-04
        # and the replay thrashed a 48 GB machine for hours.
        def finished_copy(event: dict[str, Any]) -> dict[str, Any] | None:
            status = (event.get("status") or {}).get("type")
            sport = _event_sport(event)
            if status != "finished" or sport not in REPLAYED_SPORTS or (
                    sports and sport not in sports):
                return None
            if since_ts is not None or until_ts is not None:
                start = event.get("startTimestamp")
                if not isinstance(start, int) or (
                        since_ts is not None and start < since_ts) or (
                        until_ts is not None and start >= until_ts):
                    return None
            return slim_event(event)

        identity = listed_events_by_id(conn, finished_copy, kinds=None)

        stats_by_event: dict[int, tuple[str | None, str | None]] = {}
        for event_id, statistics_json, incidents_json in conn.execute(
            "SELECT sofascore_event_id, statistics_json, incidents_json "
            "FROM sofa_event_stats WHERE status_type = 'finished'"
        ):
            if event_id in identity:
                stats_by_event[event_id] = (statistics_json, incidents_json)
    finally:
        conn.close()

    played: list[Played] = []
    # One entry per physical match, the way SAMPLES reads a history. Sofascore
    # lists some matches twice under two event ids (same teams, same day);
    # keyed by event id alone, the replay settled the first copy, appended it
    # to both teams' history, then settled the second copy against a sample
    # that already held that very match - its own result in its own sample.
    # Filtered to finished first: a pre-match copy has no score and would
    # "disagree" with the finished one, which drops both.
    finished = [
        event
        for event in identity.values()
        if (event.get("status") or {}).get("type") == "finished"
    ]
    kept = one_listing_per_match(finished)
    if dropped_out is not None:
        kept_ids = {e.get("id") for e in kept}
        dropped_out.update(
            int(e["id"]) for e in finished
            if isinstance(e.get("id"), int) and e.get("id") not in kept_ids
        )
    for event in kept:
        # A retirement or a walkover is `finished` but no result: SAMPLES
        # and SETTLE refuse it (is_completed_event); the replay graded it as
        # a whole match (review round 2, 2026-10-04: 438 retired + 275
        # walkover in a 1/20 sample of finished tennis). Filtered AFTER the
        # newest copy is chosen, so a later "retired" copy is never undercut
        # by an older "Ended" one (review round 3).
        if not is_completed_event(event):
            continue
        event_id = int(event["id"])
        home = (event.get("homeTeam") or {}).get("id")
        away = (event.get("awayTeam") or {}).get("id")
        started = event.get("startTimestamp")
        if not home or not away or not started:
            continue
        sport = _event_sport(event)
        if sport not in REPLAYED_SPORTS:
            continue
        unique = ((event.get("tournament") or {}).get("uniqueTournament") or {}).get(
            "id"
        )

        statistics_json, incidents_json = stats_by_event.get(event_id, (None, None))
        values = match_values(event, sport, statistics_json, incidents_json)
        if tennis_sets and sport == "tennis":
            values = {**values, **set_values(event)}
        if tennis_serve and sport == "tennis":
            values = {**values, **serve_values(event, statistics_json)}

        if values:
            played.append(
                Played(
                    event_id=event_id,
                    timestamp=int(started),
                    home_id=int(home),
                    away_id=int(away),
                    sport=sport,
                    competition_id=int(unique) if unique else None,
                    values=values,
                    kind=match_kind(event, sport),
                    tennis=(
                        TennisContext(
                            category_name=str(
                                ((event.get("tournament") or {}).get("category")
                                 or {}).get("name") or ""),
                            ground_type=event.get("groundType"),
                            # defaultPeriodCount is not on a listing; a completed
                            # best-of-five has a winner with 3 sets.
                            best_of_five=infer_best_of(event) == 5,
                            best_of=infer_best_of(event),
                        )
                        if sport == "tennis" else None
                    ),
                )
            )

    played.sort(key=lambda p: p.timestamp)
    return played


def without_halves(played: list[Played]) -> list[Played]:
    """The replay as it was before the per-half markets (--halves skip)."""
    out: list[Played] = []
    for match in played:
        values = {b: v for b, v in match.values.items() if b not in HALF_BASES}
        if values:
            out.append(dataclasses.replace(match, values=values))
    return out


def lines_for(centre: float) -> list[float]:
    """A grid of half-lines around the centre, as a bookmaker would post."""
    lowest = max(0, math.floor(centre) - 4)
    return [lowest + 0.5 + step for step in range(9)]


def load_baselines() -> dict[str, Any]:
    path = config_path("sofa_league_baselines.json")
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def prior_for(
    baselines: dict[str, Any], market: str, competition_id: int | None
) -> float | None:
    entry = baselines.get(market)
    if not isinstance(entry, dict):
        return None
    if competition_id is not None:
        league = entry.get(str(competition_id))
        if isinstance(league, dict) and isinstance(league.get("mean"), int | float):
            return float(league["mean"])
    # Both pool shapes: `{"mean": x, "n": k}` since 2026-09-21, a bare float
    # in every file written before it. Reading only one of them would not
    # error — it would silently return None and recalibrate against a model
    # with no prior at all, which is the worst of the three outcomes.
    overall = entry.get("global")
    if isinstance(overall, dict) and isinstance(overall.get("mean"), int | float):
        return float(overall["mean"])
    if isinstance(overall, int | float) and not isinstance(overall, bool):
        return float(overall)
    return None


@dataclass
class SettledRow:
    event_id: int
    sport: str
    competition_id: int | None
    market: str
    subject: str
    line: float
    direction: str
    sample_size: int
    sample_mean: float
    sample_sd: float
    p_central: float
    actual: float
    outcome: str

    @property
    def won(self) -> bool:
        return self.outcome == "WIN"


class Past(NamedTuple):
    """One earlier match in a side's replayed history."""

    timestamp: int
    event_id: int
    own: float
    total: float
    competition_id: int | None = None
    regular: bool = True
    # "home" / "away": where the side earned it (the venue prior of
    # --venue-prior reads the sample's venues, as SHEET reads Observation.venue)
    venue: str | None = None
    # the side's opponent in that match (Observation.opponent_id): what
    # --opponent-correction rescales the observation by
    opponent: int | None = None
    # tennis: the match's format (infer_best_of) and surface (groundType),
    # what --tennis-sample-scope filters on
    best_of: int | None = None
    surface: str | None = None


def recent_for(
    history: list[Past], market: str, competition_id: int | None,
    tennis: TennisContext | None = None,
) -> list[Past]:
    """A side's sample for ``market``, as SAMPLES picks it: the newest
    SAMPLE_N, or for a goal market (SAME_COMPETITION_METRICS) the newest
    SAMPLE_N REGULAR matches of the fixture's competition when there are at
    least SAME_COMPETITION_MIN of them. Oldest first, like the history.

    `tennis` (a tennis fixture) under --tennis-sample-scope
    (TENNIS_SAMPLE_SCOPE): only past matches of the fixture's format and a
    comparable surface (samples.py's rule: infer_best_of equal to the
    fixture's, settle.surfaces_comparable; an unknown fixture surface has no
    sample - SURFACE_UNKNOWN), looking back INDEXED_HISTORY_LIMIT matches."""
    if TENNIS_SAMPLE_SCOPE and tennis is not None:
        if tennis.ground_type is None:
            return []
        scoped: list[Past] = []
        for past in history[: -INDEXED_HISTORY_LIMIT - 1 : -1]:
            if (tennis.best_of is not None and past.best_of != tennis.best_of):
                continue
            if not surfaces_comparable(past.surface, tennis.ground_type):
                continue
            scoped.append(past)
            if len(scoped) >= SAMPLE_N:
                break
        return list(reversed(scoped))
    if market in SAME_COMPETITION_METRICS and competition_id is not None:
        # SAMPLES picks from the pages it read and the listed-event index -
        # at most INDEXED_HISTORY_LIMIT matches back - so the replay looks no
        # further, and walks back from the newest (a slice, not a copy of a
        # side's whole history, once per side per match).
        picked = pick_same_competition(
            history[: -INDEXED_HISTORY_LIMIT - 1 : -1], competition_id, SAMPLE_N,
            lambda p: p.competition_id, lambda p: p.regular,
        )
        if picked is not None:
            return list(reversed(picked))
    return history[-SAMPLE_N:]


def pooled_total_sample(
    home_recent: list[Past], away_recent: list[Past]
) -> list[float]:
    """The sample of a match-total row, the way SHEET builds it.

    run_sheet.py prices a `*_total` rung (no subject) from
    `deduplicate_observations([side_a, side_b, h2h])`: both sides' last
    SAMPLE_N matches pooled, one historical match once. SAMPLES' h2h bucket
    holds only meetings already present in side_a or side_b
    (samples.py, `is_h2h`), so the union of the two recent lists, keyed by
    event id, is the whole pool - a past meeting of these two sides sits in
    both lists with the same total and enters once.

    Until 2026-10-02 the replay settled a total once per SIDE from that side's
    own ten matches, under one key (event, market, "", line, direction): the
    away side's rows overwrote the home side's wherever their line grids
    overlapped, so a replayed total carried one side's sample while the
    sheet ships a pooled one (71.6M rows written, 29.4M keys, in a rehearsal).
    """
    seen: set[int] = set()
    values: list[float] = []
    for past in (*home_recent, *away_recent):
        if past.event_id in seen:
            continue
        seen.add(past.event_id)
        values.append(past.total)
    return values


# market, line, direction -> the rating's P(selection wins), or None
RatingP = Callable[[str, float, str], float | None]

# The handicap_games ladder the rating prices (Superbet posts about +-1.5..+-9.5
# on a best-of-three); every half-line, a row each side. most_games has no line.
HANDICAP_LINES: tuple[float, ...] = tuple(x + 0.5 for x in range(-10, 10))


class RatingReplay:
    """The tennis rating SHEET prices with, for a replayed match: the book and
    the neighbour table as of the match's UTC day start (run_sheet builds one
    model per day, ``cut`` = the day), not a match later. ``history`` is
    tennis_rating.load_history - the sheet's own population, which is wider
    than the matches this replay can grade (a match without /statistics is a
    rating match and no row)."""

    def __init__(
        self,
        history: list[Any],
        coefficients: dict[str, list[float]],
        names: tuple[str, ...],
        scoped: bool = False,
        tier_start: Mapping[str, float] | None = None,
    ) -> None:
        # scoped / tier_start: epochs.TENNIS_SCOPED_TABLE (default off). The
        # rating is built in memory from the history on every run, never
        # cached on disk, so the two rules cannot collide in a cache.
        self._rating = AsOfRating(history, coefficients, names, scoped, tier_start)
        self.forecasts = 0
        self.unrated = 0

    @classmethod
    def from_db(cls, db_path: Path, scoped: bool = False) -> RatingReplay | None:
        loaded = load_coefficients()
        if loaded is None:
            return None
        coefficients, meta = loaded
        return cls(
            load_history(db_path), coefficients, tuple(meta["features"]),
            scoped, start_for_rule(
                meta["features"], meta.get("tier_start"), scoped))

    def forecast(self, match: Played) -> MatchForecast | None:
        ctx = match.tennis
        if ctx is None or ctx.best_of_five:
            return None  # best of five is not modelled (run_sheet.tennis_forecast)
        day = match.timestamp - match.timestamp % 86400
        found = self._rating.model_at(day).forecast(
            match.home_id, match.away_id, ctx.category_name, ctx.ground_type,
            datetime.fromtimestamp(match.timestamp, UTC),
        )
        if found is None:
            self.unrated += 1
        else:
            self.forecasts += 1
        return found


def rating_reader(forecast: MatchForecast, side: str) -> RatingP:
    """run_sheet's p_rating for one side's games_won_for row and, with side
    None, the match's games_total row; and, under --tennis-set-ratings
    (TENNIS_SET_RATINGS), the per-set games and sets_total of
    SET_RATING_PRICED_MARKETS (a player's set games from his side, a total
    from the home pool, as MatchForecast.read reads it); nothing for any
    other market."""

    def read(market: str, line: float, direction: str) -> float | None:
        if market == "games_won_for":
            return forecast.read(market, side, line, direction)
        if market == "games_total":
            return forecast.read(market, None, line, direction)
        if TENNIS_SET_RATINGS and market in SET_RATING_PRICED_MARKETS:
            return forecast.read(
                market, side if market.endswith("_for") else None, line,
                direction)
        return None

    return read


def rating_derived_rows(
    match: Played,
    forecast: MatchForecast,
    home_sample: list[float],
    away_sample: list[float],
) -> Iterator[SettledRow]:
    """handicap_games and most_games, priced by the neighbours alone as run_sheet
    does (derived.price_derived_rungs with _stats_only_rating_p), settled the way
    run_settle._settle_derived does: actual = the side's margin, a handicap
    wins when margin > -line, `most` when the margin is positive. The draw of
    most_games is not rating-priced and not replayed."""
    home_games, away_games = match.values["games"]
    for team, side, margin, sample in (
        (match.home_id, "side_a", home_games - away_games, home_sample),
        (match.away_id, "side_b", away_games - home_games, away_sample),
    ):
        mean = statistics.mean(sample)
        sd = statistics.stdev(sample)
        for market, lines in (("handicap_games", HANDICAP_LINES),
                              ("most_games", (0.0,))):
            for line in lines:
                p = forecast.read(market, side, line, "OVER")
                if p is None or outside_model_resolution(p):
                    continue
                won = margin > -line if market == "handicap_games" else margin > 0
                yield SettledRow(
                    event_id=match.event_id,
                    sport=match.sport,
                    competition_id=match.competition_id,
                    market=market,
                    subject=str(team),
                    line=line,
                    direction="OVER",
                    sample_size=len(sample),
                    sample_mean=round(mean, 4),
                    sample_sd=round(sd, 4),
                    p_central=round(p, 6),
                    actual=margin,
                    outcome="WIN" if won else "LOSS",
                )


# ---------------------------------------------------------------------------
# The football centre as SHEET builds it live (audit 2026-10-13 A6)
# ---------------------------------------------------------------------------
#
# Until --football-rating the replay's football centre was the K_CENTRE
# shrink of the sample alone, while SHEET blends the opponent-adjusted rating
# into it at W_FOOTBALL_RATING (run_sheet.process_fixture): the curves were
# fitted on another centre than the one that prints. With the flag the
# rating book is replayed in time order and read as SHEET reads it.


@dataclass(frozen=True)
class CentreRules:
    """Which live centre terms the replay applies (all off = the replay as
    it was, byte for byte). ``rated_scope``, ``game_state`` and
    ``venue_prior`` are the audit 2026-10-13 B1 / B2 switches
    (epochs.FOOTBALL_RATED_SCOPE / GAME_STATE / FOOTBALL_VENUE_PRIOR); they
    need the rating, as in SHEET. The book's own rules (link, regional unit
    strength, strict league rate) are read from epochs at the replay's start,
    as SHEET would read them for a day built now."""

    football_rating: bool = False
    rated_scope: bool = False
    venue_prior: bool = False
    game_state: GameStateTable | None = None
    # epochs.FOOTBALL_GOALS_STRETCH (--goals-stretch): a goals centre x the
    # supremacy stretch (bet.sofa.goals_stretch)
    goals_stretch: GoalsStretchTable | None = None
    # epochs.FOOTBALL_COUNT_STRETCH (--count-stretch): a count centre outside
    # GAME_STATE x the supremacy stretch (bet.sofa.count_stretch)
    count_stretch: CountStretchTable | None = None
    # epochs.FOOTBALL_PLAYER_STRETCH (--player-stretch): a footballer's shots
    # centre x his side's supremacy term (bet.sofa.player_stretch; the
    # player replay, build_player_rows)
    player_stretch: PlayerStretchTable | None = None
    # audit 2026-10-13 B14 (epochs.FOOTBALL_RATING_WEIGHT): W per market
    rating_weights: RatingWeightTable | None = None
    # audit 2026-10-13 C1 (epochs.SEASON_PHASE): the goals centre x the phase
    season_phase: SeasonPhaseTable | None = None
    # audit 2026-10-13 B15 / A5 (epochs.SAMPLE_OPPONENT_CORRECTION): the
    # football sample rescaled to a neutral opponent and today's domain
    # before its centre (ReplayOpponentCorrection)
    opponent_correction: bool = False
    shared_league_link: bool = True
    unit_strength_from_parent: bool = False
    strict_league_rate: bool = False
    # epochs.FOOTBALL_CUP_STRENGTH (--cup-strength): the league strength the
    # book learns in international club cups (bet.sofa.cup_strength)
    cup_strength: CupStrength | None = None
    cup_strength_path: str | None = None
    # epochs.SAMPLE_CUP_STRENGTH (--sample-cup-strength): B15's gaps read
    # the cup strength with the past match's and the fixture's competition
    sample_cup_strength: bool = False

    def describe(self) -> dict[str, Any]:
        return {
            "football_rating": self.football_rating,
            "rated_scope": self.rated_scope,
            "venue_prior": self.venue_prior,
            "game_state": (None if self.game_state is None
                           else self.game_state.path or "in-memory"),
            "goals_stretch": (None if self.goals_stretch is None
                              else self.goals_stretch.path or "in-memory"),
            "count_stretch": (None if self.count_stretch is None
                              else self.count_stretch.path or "in-memory"),
            "player_stretch": (None if self.player_stretch is None
                               else self.player_stretch.path or "in-memory"),
            "rating_weights": (None if self.rating_weights is None
                               else self.rating_weights.path or "in-memory"),
            "season_phase": (None if self.season_phase is None
                             else self.season_phase.path or "in-memory"),
            "opponent_correction": self.opponent_correction,
            "shared_league_link": self.shared_league_link,
            "unit_strength_from_parent": self.unit_strength_from_parent,
            "strict_league_rate": self.strict_league_rate,
            "cup_strength": (None if self.cup_strength is None
                             else self.cup_strength_path or "in-memory"),
            "sample_cup_strength": self.sample_cup_strength,
        }


# Set by main() from the flags; the replay as it was by default.
CENTRE_RULES = CentreRules()

# --tennis-set-ratings (audit 2026-10-13 B5): the set bases are loaded
# (load_cache tennis_sets) and their markets read off the rating's neighbours.
TENNIS_SET_RATINGS = False
# --tennis-sample-scope (2026-10-16): a tennis side's sample is scoped as
# SAMPLES scopes it - the fixture's format and a comparable surface. Without
# it, 13% of the replayed best-of-three rows (57% ATP) held a Grand Slam
# five-setter in the games sample, centre +1.97 games, log-loss +0.0445
# (docs/sofa/evidence/tennis_replay_sample_scope_2026-10-16.md).
TENNIS_SAMPLE_SCOPE = False


def day_start(ts: int) -> int:
    """00:00Z of the match's UTC day - the cut SHEET replays the football book
    to (run_sheet: football_rating.replay(history, the day))."""
    return ts - ts % 86400


class FootballRatingReplay:
    """The football rating book SHEET prices with, as of each replayed match.

    SHEET replays football_rating.load_history up to the day being built
    (``cut`` = that day's 00:00Z) and reads every fixture of the day from that
    one book. Here the book is advanced lazily, in time order, to the UTC day
    start of the match being priced: it holds only matches that kicked off
    strictly before that day - never the match itself, nor a later one - and
    it never moves backwards (the replay is chronological; a request for an
    earlier day raises)."""

    def __init__(
        self, history: Iterable[FootballResult], rules: CentreRules,
    ) -> None:
        self._history = sorted(history, key=lambda r: r.ts)
        self._next = 0
        self.cut = -(2**62)
        self.rules = rules
        self.book = RatingBook(shared_league_link=rules.shared_league_link)
        self.book.unit_strength_from_parent = rules.unit_strength_from_parent
        apply_cup_strength(self.book, rules.cup_strength)
        self.forecasts = 0
        # --season-phase, or a --goals-stretch table with per-phase
        # coefficients: each event's phase as of its kickoff, asked before
        # the event is added (season_phase.phases_by_event)
        self.phases: dict[int, str | None] = (
            phases_by_event(self._history)
            if rules.season_phase is not None or (
                rules.goals_stretch is not None and rules.goals_stretch.by_phase)
            else {})

    @classmethod
    def from_db(cls, db_path: Path, rules: CentreRules) -> FootballRatingReplay:
        # the history SHEET reads, through the same pickle cache next to the DB
        return cls(load_football_history(db_path, db_path.parent / "cache"), rules)

    def advance(self, cut_ts: int) -> None:
        """Update the book with every result that kicked off before cut_ts."""
        if cut_ts < self.cut:
            raise ValueError(f"football book asked back from {self.cut} to {cut_ts}")
        self.cut = cut_ts
        history = self._history
        while self._next < len(history) and history[self._next].ts < cut_ts:
            self.book.update(history[self._next])
            self._next += 1

    @property
    def seen(self) -> int:
        """How many history results the book holds."""
        return self._next

    def forecast(self, match: Played) -> FootballForecast | None:
        """SHEET's FootballForecast for a football match; None for another
        sport or a match with no competition. Valid until the next call for a
        later day (the book is shared and moves on)."""
        if match.sport != "football" or match.competition_id is None:
            return None
        return self.forecast_fixture(match.competition_id, match.home_id,
                                     match.away_id, match.timestamp)

    def forecast_fixture(self, competition_id: int, home_id: int,
                         away_id: int, kickoff_ts: int) -> FootballForecast:
        """SHEET's FootballForecast for a football fixture kicking off at
        ``kickoff_ts`` (the book advanced to that UTC day's start)."""
        self.advance(day_start(kickoff_ts))
        self.forecasts += 1
        return FootballForecast(
            self.book, competition_id, home_id, away_id,
            strict_league_rate=self.rules.strict_league_rate,
            rated_scope=(RATED_SCOPE_MARKETS if self.rules.rated_scope
                         else frozenset()),
        )


def live_centre(
    match: Played,
    market: str,
    side: str | None,
    sample_centre: float,
    forecast: FootballForecast | None,
    venues: Sequence[str | None] = (),
    rules: CentreRules | None = None,
    phase: str | None = None,
) -> float:
    """THE hook: the centre SHEET prices a football marginal row with, from
    the replay's shrunk sample centre - every live centre term is applied
    here and nowhere else (run_sheet.process_fixture, the order kept):

      1. the rating (FootballForecast.centre; the rated scope lives in the
         forecast) blended at W_FOOTBALL_RATING;
      2. --venue-prior: a sample-only side centre of VENUE_PRIOR_MARKETS x
         the league venue multiplier over ``venues`` (the sample's);
      3. --game-state: x exp(beta x the side's expected goal difference);
      3a. --count-stretch: a count centre outside GAME_STATE x exp(beta x
         s [+ beta2 x s^2]) (a side) or exp(g1 |s| + g2 s^2) (a total, s
         the home side's);
      3b. --goals-stretch: a goals centre x exp(beta x s) (a side) or
         exp(g1 |s| + g2 s^2) (a total, s the home side's), per season
         phase where the table has the phase (``phase``);
      4. --season-phase: x exp(c[market][phase]), the phase as of the
         match's kickoff (``phase``).

    The blend's W is the market's fitted one under --rating-weight
    (rating_weight.blend), else W_FOOTBALL_RATING.

    ``side`` is "side_a" (home) / "side_b" (away) / None for a total. No
    forecast (rating off, another sport, no competition) or a player market:
    the sample centre unchanged. A later centre term goes here, behind its
    own CentreRules field."""
    rules = rules if rules is not None else CENTRE_RULES
    if forecast is None or is_player_metric(market):
        return sample_centre
    centre = sample_centre
    rated = forecast.centre(market, side)
    if rated is not None:
        centre = (rating_blend(rated[0], centre, market, rules.rating_weights)
                  if rules.rating_weights is not None else
                  W_FOOTBALL_RATING * rated[0] + (1 - W_FOOTBALL_RATING) * centre)
    if (rules.venue_prior and rated is None and side is not None
            and market in VENUE_PRIOR_MARKETS):
        v_mult = forecast.venue_multiplier(market, side, venues)
        if v_mult is not None:
            centre *= v_mult
    if rules.game_state is not None and side:
        sup = forecast.supremacy(side)
        g_mult = rules.game_state.multiplier(market, sup)
        if g_mult is not None and sup is not None:
            centre *= g_mult
    if rules.count_stretch is not None:
        cs_sup = side_or_home_supremacy(
            forecast, side, count_stretch_is_total(market))
        cs_mult = rules.count_stretch.multiplier(market, cs_sup)
        if cs_mult is not None and cs_sup is not None:
            centre *= cs_mult
    if rules.goals_stretch is not None:
        st_sup = stretch_supremacy(forecast, market, side)
        st_mult = rules.goals_stretch.multiplier(market, st_sup, phase)
        if st_mult is not None and st_sup is not None:
            centre *= st_mult
    if rules.season_phase is not None:
        centre, _ = apply_season_phase(centre, market, phase, rules.season_phase)
    return centre


class ReplayOpponentCorrection:
    """SHEET's B15 correction (bet.sofa.opponent_correction, run_sheet.
    process_fixture under epochs.SAMPLE_OPPONENT_CORRECTION) on the replay's
    samples, read through the same book SHEET holds - the football rating
    book as of the match's UTC day start (FootballRatingReplay.book).

    The arithmetic is SampleCorrector.factors, the gate corrected_metric
    (goals, player markets and markets without a rating metric stay raw).
    An observation stays raw, as live, when its opponent is unknown or not
    rated on the metric (< MIN_TEAM_MATCHES). A total's for / against split
    is the side's own count and the rest of the match total (Past.own,
    Past.total - Past.own): the replay always holds it, where SHEET reads
    it from the ``*_for`` sample of the same match (B13) and leaves an
    observation raw without one.

    One instance per match: the corrector caches the book's link gaps, and
    the book moves on with the next day."""

    def __init__(
        self, book: RatingBook, cup_aware: bool = False,
        today_competition: int | None = None,
    ) -> None:
        self.corrector = SampleCorrector(book, cup_aware=cup_aware)
        self.today_competition = today_competition

    def side(
        self, recent: Sequence[Past], market: str, team: int,
        today_opponent: int | None,
    ) -> list[float]:
        """A ``*_for`` sample as SHEET prices it (SampleCorrector.correct):
        each observation x its opponent's 1/def^c x exp(g)."""
        metric = corrected_metric(market)
        if metric is None:
            return [p.own for p in recent]
        out: list[float] = []
        for p in recent:
            f = (None if p.opponent is None else
                 self.corrector.factors(team, p.opponent, today_opponent, metric,
                                        p.competition_id, self.today_competition))
            out.append(p.own if f is None else p.own * f[0])
        return out

    def total(
        self, home_recent: Sequence[Past], away_recent: Sequence[Past],
        market: str, home: int, away: int,
    ) -> list[float]:
        """A ``*_total`` sample as SHEET prices it (correct_total, then
        deduplicate_observations): pooled_total_sample's pool - home side
        first, one historical match once - with each match read from the
        side whose list it came from."""
        metric = corrected_metric(market)
        seen: set[int] = set()
        out: list[float] = []
        for recent, team, other in ((home_recent, home, away),
                                    (away_recent, away, home)):
            for p in recent:
                if p.event_id in seen:
                    continue
                seen.add(p.event_id)
                f = (None if metric is None or p.opponent is None else
                     self.corrector.factors(team, p.opponent, other, metric,
                                            p.competition_id,
                                            self.today_competition))
                out.append(p.total if f is None
                           else p.own * f[0] + (p.total - p.own) * f[1])
        return out


# Football joints (both_over_ / most_ / handicap_) of the bases measured out of
# sample for the marginal centres, replayed from the SAME centres SHEET gives
# derived.price_derived_rungs (epochs.DERIVED_MARGINAL_CENTRES_FROM_UTC): both
# sides' K_CENTRE-shrunk centres, variance scaled and inflated by
# marginal_centred_stats, the measured side correlation. Not replayed: the
# football rating blended into the centre (W_FOOTBALL_RATING), as for every
# football marginal row.
JOINT_BASES: frozenset[str] = frozenset(
    m[: -len("_for")] for m in DERIVED_MARGINAL_CENTRES_METRICS)
# half-lines either side of the centre a joint grid reaches
JOINT_REACH = 3


def football_joint_rows(
    match: Played,
    base: str,
    home_sample: list[float],
    away_sample: list[float],
    centres: tuple[float | None, float | None],
    rho: float,
) -> Iterator[SettledRow]:
    """both_over_<base> (OVER and UNDER), handicap_<base> (each side, OVER) and
    most_<base> (each side and the draw, OVER) for one match, graded the way
    run_settle._settle_derived grades them: both_over by min(home, away) >=
    floor(line) + 1 (actual = the min), a handicap by the side's own margin >
    -line (actual = the margin), `most` by the margin's sign (actual = home -
    away). A whole-number handicap landing on its line is a push and no row."""
    side_metric = f"{base}_for"
    raw = []
    for sample in (home_sample, away_sample):
        n = len(sample)
        var = statistics.variance(sample) if n > 1 else 0.0
        raw.append(SideStats(n=n, mean=statistics.mean(sample), variance=var,
                             sd=math.sqrt(var)))
    c_home, c_away = centres
    # epochs.COUNT_DISPERSION: the marginal spreads carry the fitted alpha, as
    # derived.price_derived_rungs gives them in SHEET (replay == SHEET)
    disp = (
        COUNT_DISPERSION.read(match.sport, side_metric, match.competition_id)
        if COUNT_DISPERSION is not None else None
    )
    stats = (
        [marginal_centred_stats(raw[0], side_metric, c_home, disp),
         marginal_centred_stats(raw[1], side_metric, c_away, disp)]
        if c_home is not None and c_away is not None else raw
    )
    joint = build_joint(stats[0].mean, stats[0].variance, stats[1].mean,
                        stats[1].variance, rho)
    home, away = match.values[base]
    n = min(len(home_sample), len(away_sample))
    mean = round(statistics.mean([*home_sample, *away_sample]), 4)
    sd = round(statistics.stdev([*home_sample, *away_sample]), 4)

    def row(market: str, subject: str, line: float, direction: str, p: float | None,
            actual: float, won: bool) -> Iterator[SettledRow]:
        if p is None or outside_model_resolution(p):
            return
        yield SettledRow(
            event_id=match.event_id, sport=match.sport,
            competition_id=match.competition_id, market=market, subject=subject,
            line=line, direction=direction, sample_size=n, sample_mean=mean,
            sample_sd=sd, p_central=round(p, 6), actual=actual,
            outcome="WIN" if won else "LOSS")

    both = min(home, away)
    low = max(0, math.floor(min(stats[0].mean, stats[1].mean)) - JOINT_REACH)
    for line in (low + 0.5 + k for k in range(2 * JOINT_REACH + 1)):
        for direction in ("OVER", "UNDER"):
            hit = both >= math.floor(line) + 1
            yield from row(
                f"both_over_{base}", "", line, direction,
                derived_probability(joint, f"both_over_{base}", line,
                                    direction, None),
                both, hit if direction == "OVER" else not hit)
    for side, team, margin in (("side_a", match.home_id, home - away),
                               ("side_b", match.away_id, away - home)):
        ahead = stats[0].mean - stats[1].mean
        centre_margin = ahead if side == "side_a" else -ahead
        first = math.floor(-centre_margin) - JOINT_REACH
        for line in (first + 0.5 + k for k in range(2 * JOINT_REACH + 1)):
            if margin == -line:
                continue
            yield from row(
                f"handicap_{base}", str(team), line, "OVER",
                derived_probability(joint, f"handicap_{base}", line, "OVER",
                                    side),
                margin, margin > -line)
        yield from row(
            f"most_{base}", str(team), 0.0, "OVER",
            derived_probability(joint, f"most_{base}", 0.0, "OVER", side),
            home - away, margin > 0)
    # The draw of most_<base> is a different event from a side's win and would
    # share one curve with it (fit_confidence keys by market and direction):
    # it is not replayed - line evidence reads it (review 2026-10-07).


def build(
    played: list[Played],
    baselines: dict[str, Any],
    rating: RatingReplay | None = None,
) -> list[SettledRow]:
    return list(iter_rows(played, baselines, rating))


def iter_rows(
    played: list[Played],
    baselines: dict[str, Any],
    rating: RatingReplay | None = None,
    joint_bases: frozenset[str] = frozenset(),
    football: FootballRatingReplay | None = None,
    emit_from: int | None = None,
    emit_to: int | None = None,
) -> Iterator[SettledRow]:
    """build() one row at a time, for a measurement that aggregates the
    replay without holding tens of millions of rows.

    ``football`` (--football-rating): the rating book SHEET prices football
    with, read through live_centre for every football marginal row and joint
    centre. ``emit_from`` / ``emit_to`` (unix seconds, a smoke window): rows
    only for matches kicking off inside [emit_from, emit_to); every earlier
    match still enters the histories, nothing after emit_to is read."""
    # Read once: the constant is per sport and must be the one that ships.
    engine_constants = _load_engine_constants()
    correlations = load_side_correlations(cards_correlation=CARDS_CORRELATION)
    # (team, base) -> chronological list of earlier matches
    history: dict[tuple[int, str], list[Past]] = collections.defaultdict(list)

    for match in played:
        if emit_to is not None and match.timestamp >= emit_to:
            break
        if match.kind == MatchKind.FRIENDLY and match.sport != "football":
            # fit_meta.friendly_exclusion_sql drops football friendlies by
            # competition id only; a tennis exhibition's rows would enter
            # every fit (review round 3). Never settled, never in a history.
            continue
        if emit_from is None or match.timestamp >= emit_from:
            yield from _match_rows(
                match, history, baselines, engine_constants, correlations,
                rating, joint_bases, football)

        # Only after settling: a match may never contribute to its own sample.
        # A friendly is settled like any match (the fit drops friendly rows,
        # fit_meta.friendly_exclusion_sql) but never enters a history.
        if match.kind == MatchKind.FRIENDLY:
            continue
        regular = match.kind == MatchKind.REGULAR
        for base, (home_value, away_value) in match.values.items():
            total = home_value + away_value
            fmt = (None if match.tennis is None else match.tennis.best_of)
            surf = (None if match.tennis is None else match.tennis.ground_type)
            history[(match.home_id, base)].append(
                Past(match.timestamp, match.event_id, home_value, total,
                     match.competition_id, regular, "home", match.away_id,
                     fmt, surf)
            )
            history[(match.away_id, base)].append(
                Past(match.timestamp, match.event_id, away_value, total,
                     match.competition_id, regular, "away", match.home_id,
                     fmt, surf)
            )


def _match_rows(
    match: Played,
    history: dict[tuple[int, str], list[Past]],
    baselines: dict[str, Any],
    engine_constants: dict[str, Any],
    correlations: Mapping[str, float | None],
    rating: RatingReplay | None,
    joint_bases: frozenset[str],
    football: FootballRatingReplay | None,
) -> Iterator[SettledRow]:
    """Every settled row of one match, from the histories before it."""
    # The goal samples' same-competition rule applies to league fixtures
    # only (SAMPLES, review 2026-10-04: worse on KNOCKOUT targets).
    sample_competition = (
        match.competition_id if match.kind == MatchKind.REGULAR else None
    )
    forecast = (
        rating.forecast(match)
        if rating is not None and match.sport == "tennis"
        and ("games" in match.values or (
            TENNIS_SET_RATINGS
            and any(b in match.values for b in SET_BASE_MARKETS)))
        else None
    )
    football_fc = (
        football.forecast(match)
        if football is not None and match.sport == "football" else None
    )
    # --season-phase / a per-phase --goals-stretch: the match's phase as of
    # its kickoff
    match_phase = (football.phases.get(match.event_id)
                   if football_fc is not None and football is not None else None)
    # --opponent-correction (B15): the sample rescaled through the book SHEET
    # holds for the match's day, before its mean, variance and centre - as
    # run_sheet does, whether or not the fixture has a forecast
    opponent: ReplayOpponentCorrection | None = None
    if (football is not None and football.rules.opponent_correction
            and match.sport == "football"):
        football.advance(day_start(match.timestamp))
        opponent = ReplayOpponentCorrection(
            football.book, football.rules.sample_cup_strength, match.competition_id)

    def settle_rows(
        market: str, subject: str, actual: float, sample: list[float],
        rating_p: RatingP | None, side: str | None, recent: Sequence[Past],
    ) -> list[SettledRow]:
        # --tennis-aces-opponent: the aces centre x today's returner's factor
        # (bet.sofa.tennis_aces_opponent), as run_sheet applies it
        aces_mult = (
            tennis_aces_multiplier(match, market, side, history,
                                   sample_competition, engine_constants)
            if TENNIS_ACES_OPPONENT and match.sport == "tennis"
            and market in ACES_MARKETS else None)
        if aces_mult is not None:
            return _settle_centred(match, market, subject, actual, sample,
                                   baselines, engine_constants, rating_p,
                                   lambda c: c * aces_mult)
        # Without a football forecast: _settle_sample, the call before A6
        # argument for argument (a measurement swaps a collector in for it).
        if football_fc is None:
            return _settle_sample(match, market, subject, actual, sample,
                                  baselines, engine_constants, rating_p)
        venues = tuple(p.venue for p in recent)
        return _settle_centred(
            match, market, subject, actual, sample, baselines,
            engine_constants, rating_p,
            lambda c: live_centre(match, market, side, c, football_fc, venues,
                                  phase=match_phase))

    for base, (home_value, away_value) in match.values.items():
        total = home_value + away_value
        for_market = market_name(base, "for")
        set_markets = SET_BASE_MARKETS.get(base)
        if (set_markets is not None and match.tennis is not None
                and match.tennis.best_of_five):
            # never a set row of a best-of-five match (set_values drops them;
            # a Played built elsewhere is held to the same rule)
            continue
        rated_base = base == "games" or (
            set_markets is not None and TENNIS_SET_RATINGS)
        home_recent = recent_for(
            history[(match.home_id, base)], for_market, sample_competition,
            match.tennis,
        )
        away_recent = recent_for(
            history[(match.away_id, base)], for_market, sample_competition,
            match.tennis,
        )

        # `*_for`: each side from its own history only, as SHEET does
        # (determine_side; h2h never reaches a per-side market).
        for team, own, recent, side in (
            (match.home_id, home_value, home_recent, "side_a"),
            (match.away_id, away_value, away_recent, "side_b"),
        ):
            if set_markets is not None and "for" not in set_markets:
                break
            if len(recent) >= MIN_SAMPLE:
                yield from settle_rows(
                    for_market, str(team), own,
                    [p.own for p in recent] if opponent is None
                    else opponent.side(
                        recent, for_market, team,
                        match.away_id if side == "side_a" else match.home_id),
                    rating_reader(forecast, side)
                    if forecast is not None and rated_base else None,
                    side, recent,
                )

        if set_markets is not None and "total" not in set_markets:
            continue
        # `*_total`: ONE row set per match, from the pooled sample, and
        # only when BOTH sides have a sample - SHEET refuses a total with
        # either side thin (THIN_SAMPLE, "total pools both sides").
        # Residual difference from the sheet, not removable here: the
        # per-side threshold is this replay's MIN_SAMPLE (8), not the
        # sheet's config.min_sample (5); the per-side sample is the last
        # SAMPLE_N matches that HAVE this statistic, where SAMPLES takes
        # the last sample_n events and loses the gaps; and SAMPLES'
        # scoping of tennis (surface / best-of) is not replayed - the same
        # differences every `*_for` row already has (the tennis scoping is
        # replayed under --tennis-sample-scope). Friendlies are out of
        # the history since 2026-10-04 (Played.kind), and a goal total
        # picks its sides the way SAMPLES does (recent_for).
        total_market = market_name(base, "total")
        home_total = recent_for(
            history[(match.home_id, base)], total_market, sample_competition,
            match.tennis,
        )
        away_total = recent_for(
            history[(match.away_id, base)], total_market, sample_competition,
            match.tennis,
        )
        if len(home_total) >= MIN_SAMPLE and len(away_total) >= MIN_SAMPLE:
            yield from settle_rows(
                total_market, "", total,
                pooled_total_sample(home_total, away_total) if opponent is None
                else opponent.total(home_total, away_total, total_market,
                                    match.home_id, match.away_id),
                rating_reader(forecast, "side_a")
                if forecast is not None and rated_base else None,
                None, (),
            )
            # SHEET prices a derived row of a fixture whose two sides both
            # have a sample (derived.price_derived_rungs: n >= min_sample).
            if forecast is not None and base == "games":
                yield from rating_derived_rows(
                    match, forecast,
                    [p.own for p in home_recent],
                    [p.own for p in away_recent],
                )
        # SHEET prices a joint of a fixture whose two sides both have a
        # sample (derived.price_derived_rungs: n >= min_sample), neither
        # all zero together.
        if (
            base in joint_bases
            and match.sport == "football"
            and len(home_recent) >= MIN_SAMPLE
            and len(away_recent) >= MIN_SAMPLE
            and any(p.own for p in (*home_recent, *away_recent))
        ):
            # a side whose own marginal row is refused (all zero) has no
            # centre: the joint then reads both raw samples, as in SHEET.
            # A side's centre is its marginal row's (derived.
            # price_derived_rungs reads SHEET's marginal centres): with
            # --football-rating the live one (live_centre); with
            # --opponent-correction the marginal row's corrected sample's,
            # while the joint itself reads the raw samples, as
            # derived.price_derived_rungs reads 03_samples.json.
            joint_centres: list[float | None] = [
                None if not any(p.own for p in rec) else live_centre(
                    match, for_market, side,
                    shrunk_centre(
                        match, for_market,
                        [p.own for p in rec] if opponent is None
                        else opponent.side(rec, for_market, team, other),
                        baselines, engine_constants),
                    football_fc, tuple(p.venue for p in rec), phase=match_phase)
                for rec, side, team, other in (
                    (home_recent, "side_a", match.home_id, match.away_id),
                    (away_recent, "side_b", match.away_id, match.home_id))]
            yield from football_joint_rows(
                match, base, [p.own for p in home_recent],
                [p.own for p in away_recent],
                (joint_centres[0], joint_centres[1]),
                correlations.get(base) or 0.0)


# epochs.TENNIS_ACES_OPPONENT in the replay (--tennis-aces-opponent): the
# tier baselines its factor's prior is read from (None = off).
TENNIS_ACES_TIERS: dict[str, Any] | None = None
TENNIS_ACES_OPPONENT = False


def tennis_aces_multiplier(
    match: Played,
    market: str,
    side: str | None,
    history: Mapping[tuple[int, str], list[Past]],
    sample_competition: int | None,
    engine_constants: dict[str, Any],
) -> float | None:
    """run_sheet's TENNIS_ACES_OPPONENT multiplier for one aces row of a
    replayed tennis match: f(the returner) for a side row, the total's
    weighted pair for a total. The returner's conceded aces are his scoped
    `aces` history's total minus own (SAMPLES' `against`), the prior the
    fixture's full-match aces tier prior, K the tennis K_CENTRE. None (no
    correction) where run_sheet has none: no tier prior (best-of-five,
    unknown tier / surface) or a returner with too few values."""
    tennis = match.tennis
    if tennis is None or tennis.best_of_five or TENNIS_ACES_TIERS is None:
        return None
    tier = tier_prior(TENNIS_ACES_TIERS, aces_opp.PRIOR_MARKET,
                      tennis.category_name, tennis.ground_type)
    if tier is None:
        return None
    prior = tier[0]
    k = k_centre_for("tennis", engine_constants)

    def recent(team: int) -> list[Past]:
        return recent_for(history[(team, "aces")], "aces_for",
                          sample_competition, tennis)

    def factor(team: int) -> float | None:
        return aces_opp.returner_factor(
            [p.total - p.own for p in recent(team)], prior, k)

    if market in aces_opp.ACES_SIDE_MARKETS:
        if side not in ("side_a", "side_b"):
            return None
        return factor(match.away_id if side == "side_a" else match.home_id)
    f_home, f_away = factor(match.home_id), factor(match.away_id)
    if f_home is None or f_away is None:
        return None
    return aces_opp.total_multiplier(
        aces_opp.shrunk([p.own for p in recent(match.home_id)], prior, k),
        aces_opp.shrunk([p.own for p in recent(match.away_id)], prior, k),
        f_home, f_away)


def shrunk_centre(
    match: Played,
    market: str,
    sample: list[float],
    baselines: dict[str, Any],
    engine_constants: dict[str, Any],
) -> float:
    """SHEET's centre of a marginal row: the sample mean shrunk toward the
    league baseline with K_CENTRE (no football rating - see _settle_sample)."""
    n = len(sample)
    mean = statistics.mean(sample)
    prior = prior_for(baselines, market, match.competition_id)
    if prior is None:
        return mean
    k = k_centre_for(match.sport, engine_constants)
    if PER_MARKET_K:
        k = k_for_market(engine_constants, match.sport, market, k)
    weight = n / (n + k)
    return weight * mean + (1.0 - weight) * prior


# The fitted football count dispersion (bet.sofa.count_dispersion), set by
# main() from --count-dispersion; None = the replay as it was (the sample's
# variance). Module state like the measurements' monkey-patch of _settle_sample.
COUNT_DISPERSION: DispersionTable | None = None

# epochs.CARDS_CORRELATION in the replay (--cards-correlation): the cards
# joints' sides at epochs.CARDS_CORRELATION_RHO instead of independent.
CARDS_CORRELATION = False

# epochs.PER_MARKET_K in the replay (--per-market-k): football centres shrunk
# with K_CENTRE.by_market of the engine constants (bet.sofa.per_market_k).
PER_MARKET_K = False


def _settle_sample(
    match: Played,
    market: str,
    subject: str,
    actual: float,
    sample: list[float],
    baselines: dict[str, Any],
    engine_constants: dict[str, Any],
    rating_p: RatingP | None = None,
) -> list[SettledRow]:
    """The rows of one sample at the replay's sample centre. Its signature
    is the one measurements swap a collector in for (measure_count_families,
    fit_count_dispersion); a live football centre goes through
    _settle_centred."""
    return _settle_centred(match, market, subject, actual, sample, baselines,
                           engine_constants, rating_p)


def _settle_centred(
    match: Played,
    market: str,
    subject: str,
    actual: float,
    sample: list[float],
    baselines: dict[str, Any],
    engine_constants: dict[str, Any],
    rating_p: RatingP | None = None,
    centre_hook: Callable[[float], float] | None = None,
) -> list[SettledRow]:
    out: list[SettledRow] = []
    n = len(sample)
    if n < MIN_SAMPLE or all(v == 0.0 for v in sample):
        return out
    mean = statistics.mean(sample)
    variance = statistics.variance(sample) if n > 1 else 0.0
    sample_sd = statistics.stdev(sample) if n > 1 else 0.0
    centre = shrunk_centre(match, market, sample, baselines, engine_constants)
    if centre_hook is not None:
        # --football-rating: SHEET's live centre (live_centre, audit A6)
        centre = centre_hook(centre)

    # SHEET's spread and SHEET's estimator, from the functions SHEET calls
    # (see the module docstring). What is NOT replayed, and so still differs
    # from a live row: the tennis tier / ladder priors, and - unless
    # --football-rating gives a centre_hook (live_centre) - the football
    # rating's centre (W_FOOTBALL_RATING): without it the replay's centre is
    # the league-baseline shrink alone. The tennis rating IS replayed since the
    # stats-only rating prices (epochs.TENNIS_RATING_PRICES_FROM_UTC): a
    # rating_p callable, given by iter_rows, replaces p for games_won_for and
    # mixes into games_total exactly as run_sheet does.
    # epochs.COUNT_DISPERSION: the same fitted alpha SHEET reads, only with
    # --count-dispersion (COUNT_DISPERSION is None otherwise: the sample variance)
    dispersion = (
        COUNT_DISPERSION.read(match.sport, market, match.competition_id)
        if COUNT_DISPERSION is not None else None
    )
    spread = sheet_predictive_sd(
        market, match.sport, mean, variance, n, centre, dispersion)
    empirical = uses_empirical_frequency(market)

    for line in lines_for(centre):
        for direction in ("OVER", "UNDER"):
            boundary = winning_boundary(line, direction)
            # The tennis rating's own p (run_sheet: MatchForecast.probability
            # for a rated fixture, from epochs.tennis_rating_prices on).
            p_rating = (
                rating_p(market, line, direction) if rating_p is not None else None
            )
            if empirical:
                # run_sheet refuses an empirical rung whose raw frequency is
                # outside resolution before it looks at the shrunk one - not a
                # rung the rating prices (`p_rating is None and ...`).
                hits = sum(
                    1 for v in sample
                    if (v > boundary if direction == "OVER" else v < boundary)
                )
                if p_rating is None and outside_model_resolution(hits / n):
                    continue
                p_raw = p_empirical_centred_raw(
                    sample, boundary, direction, centre - mean
                )
            else:
                p_raw = sheet_count_p_raw(
                    market, centre, spread, boundary, direction, dispersion
                )
            if p_rating is not None:
                # run_sheet: the neighbours alone for the RATING_PRICED
                # families, a W_GAMES_TOTAL_RATING mix with the NB for
                # games_total.
                # --tennis-set-ratings: SET_RATING_PRICED_MARKETS alone too
                # (run_sheet's set_rated rows keep p_rating).
                p_raw = (
                    p_rating if market in RATING_PRICED_MARKETS
                    or market in SET_RATING_PRICED_MARKETS
                    else W_GAMES_TOTAL_RATING * p_rating
                    + (1.0 - W_GAMES_TOTAL_RATING) * p_raw
                )
            if outside_model_resolution(p_raw):
                continue
            # settle.py owns this vocabulary. Writing "WON"/"LOST" here
            # produced 1.5M rows that fit_constants.py filters out with
            # `outcome IN ('WIN','LOSS')` — it read zero, wrote an empty
            # reliability file over a measured one, and reported success.
            # A half-line cannot PUSH, but the grid is built from a centre
            # and must not assume that.
            outcome = settle(actual, line, direction)
            if outcome == "PUSH":
                continue
            out.append(
                SettledRow(
                    event_id=match.event_id,
                    sport=match.sport,
                    competition_id=match.competition_id,
                    market=market,
                    subject=subject,
                    line=line,
                    direction=direction,
                    sample_size=n,
                    sample_mean=round(mean, 4),
                    sample_sd=round(sample_sd, 4),
                    p_central=round(p_raw, 6),
                    actual=actual,
                    outcome=outcome,
                )
            )
    return out


# ---------------------------------------------------------------------------
# Football player markets (F54)
# ---------------------------------------------------------------------------
#
# Until 2026-10-03 the replay wrote no player row, so fit_confidence never had
# a curve for a player prop and AWAITING_OWN_CURVE could never lapse. The
# replay below rebuilds a player's sample the way SAMPLES and SHEET build it,
# from the functions they call:
#
#   * a side's history: its indexed listing (entity_indexed_events, as SAMPLES
#     tops its pages up), SAMPLES' admission rule for football (finished
#     normally, before kickoff, no friendly, the side in the match), then
#     samples.finish_history (one listing per match, second squads out, one
#     squad per entity, newest sample_n);
#   * per historical match: players.squad_statistics with the match's
#     /statistics (the team-sum proof of a zero), players.match_player
#     against that match's squad, players.extract_player_metric (the
#     appearance gate) - build_player_samples' loop;
#   * the side the player belongs to: where he was found more often, a tie
#     refused (build_player_samples);
#   * SHEET: n >= config.min_sample, an all-zero sample refused, centre = the
#     sample mean (no league baseline exists for a player_ market -
#     fit_constants._in_baselines - and SHEET applies no football rating to
#     one), engine.sheet_predictive_sd and engine.sheet_count_p_raw, the
#     rungs outside_model_resolution refuses dropped.
#
# The ladder is not a grid around the centre (lines_for) but every line
# Superbet has printed for the metric (runs/sofa/*/04_offer.json): a player
# ladder is short and fixed (shots 0.5..9.5, assists 0.5..2.5), and a grid
# would settle rungs nobody can bet. Both directions are written, though
# Superbet quotes OVER only: the curve is per direction anyway.
#
# Validated against SHEET before it was written here (2026-10-02 scratch
# replay): 6,048 of 6,048 settled live player rows reproduced SHEET's p to
# 1e-6 and their outcome exactly.
#
# What is NOT replayed: the target's own squad is the player set (every
# player who appeared, minutesPlayed present) - live, the set is whoever
# Superbet quotes, matched by a Superbet name; here the subject is the
# Sofascore name, so name matching across Superbet's spelling is not tested.

# How many of a side's newest indexed events before kickoff are read. SAMPLES
# walks ~30-event pages and stops once a page yields sample_n usable matches,
# so its candidate set (which one_squad_per_entity checks for two squads) is
# one or two pages; the validated scratch replay read 60.
PLAYER_HISTORY_LISTED = 60

Squad = dict[str, dict[str, Any]]


def printed_player_ladder(runs_dir: Path) -> dict[str, list[float]]:
    """{player metric: every line Superbet printed for it}, from the offers."""
    lines: dict[str, set[float]] = collections.defaultdict(set)
    for path in sorted(runs_dir.glob("*/04_offer.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(doc, list):
            continue
        for fixture in doc:
            rungs = fixture.get("rungs") if isinstance(fixture, dict) else None
            for rung in rungs if isinstance(rungs, list) else ():
                if not isinstance(rung, dict):
                    continue
                market, line = rung.get("market"), rung.get("line")
                if (
                    isinstance(market, str)
                    and is_player_metric(market)
                    and isinstance(line, int | float)
                    and not isinstance(line, bool)
                ):
                    lines[market].add(float(line))
    return {market: sorted(found) for market, found in sorted(lines.items())}


def admitted_football_event(
    event: dict[str, Any], entity_id: int, kickoff_ts: int
) -> bool:
    """SAMPLES' admission of one listed event into a football side's history
    (samples.get_historical_events, `admit`, the non-tennis branch)."""
    if not is_completed_event(event):
        return False
    start = event.get("startTimestamp")
    if not isinstance(start, int) or start >= kickoff_ts:
        return False
    competition = _competition_id(event)
    if competition is not None and competition in FRIENDLY_COMPETITION_IDS:
        return False
    return entity_id in (
        (event.get("homeTeam") or {}).get("id"),
        (event.get("awayTeam") or {}).get("id"),
    )


def is_same_match(past: dict[str, Any], target: dict[str, Any]) -> bool:
    """`past` is the target match listed again under another id.

    Live, the fixture is not finished and never in its own sides' histories.
    In the replay it is, and a re-listed copy kicked off an hour earlier is
    "before kickoff": its own result in its own sample. Same opponent (id or
    name) inside MIN_HOURS_BETWEEN_MATCHES of the target - no side plays one
    opponent twice inside a day.
    """
    gap = int(target.get("startTimestamp") or 0) - int(past.get("startTimestamp") or 0)
    if not 0 <= gap / 3600 < MIN_HOURS_BETWEEN_MATCHES:
        return False

    def sides(e: dict[str, Any]) -> tuple[frozenset[Any], frozenset[str]]:
        home, away = e.get("homeTeam") or {}, e.get("awayTeam") or {}
        return (
            frozenset((home.get("id"), away.get("id"))),
            frozenset(
                (str(home.get("name") or "").casefold(),
                 str(away.get("name") or "").casefold())
            ),
        )

    ids_a, names_a = sides(past)
    ids_b, names_b = sides(target)
    return ids_a == ids_b or (names_a == names_b and "" not in names_a)


# (event, is_home, player, metric, sample mean, n, actual)
PlayerSampleHook = Callable[
    [dict[str, Any], bool, str, str, float, int, float], None]


def player_rows_for_event(
    event: dict[str, Any],
    target: dict[bool, Squad | None],
    history: dict[bool, list[Squad]],
    ladder: dict[str, list[float]],
    min_sample: int,
    counts: collections.Counter[str] | None = None,
    *,
    starters_only: bool = False,
    starts_only: bool = False,
    player_stretch: PlayerStretchTable | None = None,
    side_supremacy: Mapping[bool, float | None] | None = None,
    on_sample: PlayerSampleHook | None = None,
    wide_history: dict[bool, list[Squad]] | None = None,
    sample_n: int | None = None,
) -> list[SettledRow]:
    """Every settled player rung of one finished match.

    `target[is_home]` is that side's squad in this match (squad_statistics,
    with this match's /statistics); `history[is_home]` the side's historical
    squads, newest first - one per sampled match that has a squad.

    `starters_only`: only a player who started this match is an outcome
    (Superbet voids the market of one who did not). `starts_only`: his
    sample is his starts (samples.build_player_samples `starts_only`).

    `player_stretch` (--player-stretch, epochs.FOOTBALL_PLAYER_STRETCH): the
    centre of a market it covers is his sample mean x exp(beta x s), s his
    side's expected goal difference (`side_supremacy[is_home]`, None: the
    mean unchanged), as run_sheet prices it; the spread follows the centre.
    `on_sample`: called once per priced sample (event, is_home, player,
    metric, sample mean, n, actual) - a fit's collector
    (scripts/sofa/fit_player_stretch.py), never a row.

    `wide_history` (--player-coverage, epochs.FOOTBALL_PLAYER_COVERAGE_FROM_UTC;
    with `sample_n`): each side's squads of its newest
    samples.PLAYER_WIDE_SAMPLE_N matches. A player whose `history` sample is
    thin (or tied, or empty) is sampled over it - his newest `sample_n`
    values, the side found more often there - as
    samples.coverage_player_samples does; the woodwork shot is then counted
    once (players.SHOTS_IDENTITY_PARTS) in his sample and his outcome alike.
    """
    woodwork_once = wide_history is not None
    tally: collections.Counter[str] = (
        counts if counts is not None else collections.Counter()
    )
    rows: list[SettledRow] = []
    event_id = int(event["id"])
    competition = _competition_id(event)
    # A name in both of this match's squads would put two players under one
    # (event, market, subject, line, direction) key.
    both = set(target.get(True) or {}) & set(target.get(False) or {})
    for is_home in (True, False):
        squad = target.get(is_home)
        if not squad:
            tally["target_side_without_squad"] += 1
            continue
        for name, stats in sorted(squad.items()):
            if stats.get("minutesPlayed") is None:
                continue  # did not appear: Superbet voids the market
            if starters_only and started(stats) is False:
                tally["not_started_void"] += 1
                continue  # off the bench: Superbet voids the market too
            tally["appearances"] += 1
            if name in both:
                tally["name_in_both_squads"] += 1
                continue
            # build_player_samples' match: per historical squad, by name.
            matched = {
                side: [(past, match_player(name, past)) for past in squads]
                for side, squads in history.items()
            }
            wide_matched = None if wide_history is None else {
                side: [(past, match_player(name, past)) for past in squads]
                for side, squads in wide_history.items()
            }
            for metric, lines in ladder.items():
                if not lines:
                    continue
                actual = extract_player_metric(
                    metric, stats, woodwork_once=woodwork_once)
                if isinstance(actual, GapReason):
                    tally[f"actual_gap:{metric}"] += 1
                    continue
                per_side = _side_values(metric, matched, starts_only, woodwork_once)
                n_home = len(per_side.get(True, []))
                n_away = len(per_side.get(False, []))
                if wide_matched is not None and sample_n is not None and (
                        n_home == n_away
                        or len(per_side[n_home > n_away]) < min_sample):
                    wide = _side_values(metric, wide_matched, starts_only, True)
                    w_home = len(wide.get(True, []))
                    w_away = len(wide.get(False, []))
                    if w_home != w_away and len(
                            wide[w_home > w_away][:sample_n]) >= min_sample:
                        per_side = {side: values[:sample_n]
                                    for side, values in wide.items()}
                        n_home, n_away = w_home, w_away
                        tally["wide_window"] += 1
                if n_home == n_away:
                    tally["no_sample" if n_home == 0 else "side_tie"] += 1
                    continue
                if (n_home > n_away) != is_home:
                    # SHEET would price him from the other side's history.
                    tally["majority_on_other_side"] += 1
                    continue
                sample = per_side[is_home]
                n = len(sample)
                if n < min_sample:
                    tally["thin_sample"] += 1
                    continue
                if all(v == 0.0 for v in sample):
                    tally["all_zero_sample"] += 1
                    continue
                mean = statistics.mean(sample)
                variance = statistics.variance(sample) if n > 1 else 0.0
                sample_sd = statistics.stdev(sample) if n > 1 else 0.0
                centre = mean
                if player_stretch is not None and side_supremacy is not None:
                    p_mult = player_stretch.multiplier(
                        metric, side_supremacy.get(is_home))
                    if p_mult is not None:
                        centre = mean * p_mult
                        tally[f"player_stretch:{metric}"] += 1
                spread = sheet_predictive_sd(
                    metric, "football", mean, variance, n, centre
                )
                tally["samples"] += 1
                if on_sample is not None:
                    on_sample(event, is_home, name, metric, mean, n, actual)
                for line in lines:
                    for direction in ("OVER", "UNDER"):
                        boundary = winning_boundary(line, direction)
                        p_raw = sheet_count_p_raw(
                            metric, centre, spread, boundary, direction
                        )
                        if outside_model_resolution(p_raw):
                            tally["outside_model_resolution"] += 1
                            continue
                        outcome = settle(actual, line, direction)
                        if outcome not in ("WIN", "LOSS"):
                            continue
                        rows.append(
                            SettledRow(
                                event_id=event_id,
                                sport="football",
                                competition_id=competition,
                                market=metric,
                                subject=name,
                                line=line,
                                direction=direction,
                                sample_size=n,
                                sample_mean=round(mean, 4),
                                sample_sd=round(sample_sd, 4),
                                p_central=round(p_raw, 6),
                                actual=actual,
                                outcome=outcome,
                            )
                        )
    return rows


def _side_values(
    metric: str,
    matched: dict[bool, list[tuple[Squad, str | None]]],
    starts_only: bool,
    woodwork_once: bool,
) -> dict[bool, list[float]]:
    """A player's values per side, newest first: build_player_samples' loop
    over each historical squad he was matched in."""
    per_side: dict[bool, list[float]] = {}
    for side, pairs in matched.items():
        values: list[float] = []
        for past, key in pairs:
            if key is None:
                continue
            if starts_only and started(past[key]) is False:
                continue
            value = extract_player_metric(
                metric, past[key], woodwork_once=woodwork_once)
            if not isinstance(value, GapReason):
                values.append(value)
        per_side[side] = values
    return per_side


def _event_payloads(
    conn: sqlite3.Connection, ids: list[int], with_detail: bool
) -> dict[int, dict[str, Any]]:
    """The listed payload of each id, else the board's own event detail (a
    board fixture's event is often only in sofa_event_detail)."""
    out: dict[int, dict[str, Any]] = {}
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        marks = ",".join("?" * len(chunk))
        for event_id, raw in conn.execute(
            "SELECT event_id, event_json FROM sofa_listed_event "
            f"WHERE event_id IN ({marks})",
            chunk,
        ):
            try:
                event = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if isinstance(event, dict):
                out[int(event_id)] = event
        missing = [i for i in chunk if i not in out]
        if not missing or not with_detail:
            continue
        marks = ",".join("?" * len(missing))
        for event_id, raw in conn.execute(
            "SELECT sofascore_event_id, detail_json FROM sofa_event_detail "
            f"WHERE sofascore_event_id IN ({marks})",
            missing,
        ):
            try:
                detail = json.loads(raw)
            except (TypeError, ValueError):
                continue
            event = detail.get("event", detail) if isinstance(detail, dict) else None
            if isinstance(event, dict):
                out[int(event_id)] = event
    return out


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone() is not None


def player_targets(
    conn: sqlite3.Connection, counts: collections.Counter[str] | None = None
) -> list[dict[str, Any]]:
    """Finished football matches with a cached squad list, one listing per
    match, chronological (event id breaks a tie) - every one, no date window,
    so the same cache replays to the same rows."""
    tally: collections.Counter[str] = (
        counts if counts is not None else collections.Counter()
    )
    if not _has_table(conn, "sofa_listed_event"):
        return []
    ids = [
        int(r[0])
        for r in conn.execute(
            "SELECT sofascore_event_id FROM sofa_event_stats "
            "WHERE lineups_json IS NOT NULL AND length(lineups_json) > 10 "
            "ORDER BY sofascore_event_id"
        )
    ]
    payloads = _event_payloads(conn, ids, _has_table(conn, "sofa_event_detail"))
    events: list[dict[str, Any]] = []
    for event_id in ids:
        event = payloads.get(event_id)
        sport = (
            (((event or {}).get("tournament") or {}).get("category") or {})
            .get("sport") or {}
        ).get("slug")
        if event is None or sport != "football":
            tally["target_not_football_or_unknown"] += 1
            continue
        if not is_completed_event(event) or not isinstance(
            event.get("startTimestamp"), int
        ):
            tally["target_not_completed"] += 1
            continue
        competition = _competition_id(event)
        if competition is not None and competition in FRIENDLY_COMPETITION_IDS:
            tally["target_friendly"] += 1
            continue
        events.append(event)
    kept = one_listing_per_match(events)
    tally["target_duplicate_listing"] += len(events) - len(kept)
    kept.sort(key=lambda e: (int(e["startTimestamp"]), int(e["id"])))
    return kept


def target_supremacy(
    targets: Sequence[dict[str, Any]], football: FootballRatingReplay,
) -> dict[int, dict[bool, float | None]]:
    """event id -> {is_home: that side's expected goal difference} from the
    rating book as of each target's UTC day start (SHEET's cut), the
    targets read in kickoff order (the book only moves forward). A target
    without a kickoff, a competition or a team id has no entry (its rows
    then keep the sample mean)."""
    out: dict[int, dict[bool, float | None]] = {}
    timed = [e for e in targets if isinstance(e.get("startTimestamp"), int)]
    for event in sorted(timed, key=lambda e: (int(e["startTimestamp"]),
                                              int(e["id"]))):
        competition = _competition_id(event)
        home = int(((event.get("homeTeam") or {}).get("id")) or 0)
        away = int(((event.get("awayTeam") or {}).get("id")) or 0)
        if competition is None or not home or not away:
            continue
        fc = football.forecast_fixture(competition, home, away,
                                       int(event["startTimestamp"]))
        out[int(event["id"])] = {True: fc.supremacy("side_a"),
                                 False: fc.supremacy("side_b")}
    return out


def build_player_rows(
    db_path: Path,
    ladder: dict[str, list[float]],
    *,
    sample_n: int,
    min_sample: int,
    starts_only: bool = False,
    player_stretch: PlayerStretchTable | None = None,
    football: FootballRatingReplay | None = None,
    on_sample: PlayerSampleHook | None = None,
    coverage: bool = False,
) -> tuple[list[SettledRow], collections.Counter[str]]:
    """The player rows of every finished football match with a squad list
    (`starts_only`: starters' outcomes from their starts - the bet Superbet
    settles). `player_stretch` with `football` (a fresh rating replay - the
    targets are read in kickoff order for it): the shots centres carry each
    side's supremacy term (player_rows_for_event). `coverage`
    (--player-coverage): a thin player is sampled over the side's newest
    samples.PLAYER_WIDE_SAMPLE_N matches (player_rows_for_event wide_history)."""
    if player_stretch is not None and football is None:
        raise ValueError("player_stretch needs the football rating replay")
    counts: collections.Counter[str] = collections.Counter()
    if not any(ladder.values()):
        counts["no_printed_player_ladder"] += 1
        return [], counts
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows: list[SettledRow] = []
    try:
        targets = player_targets(conn, counts)
        supremacy: dict[int, dict[bool, float | None]] = (
            target_supremacy(targets, football)
            if player_stretch is not None and football is not None else {})
        squads: collections.OrderedDict[int, dict[bool, Squad | None]] = (
            collections.OrderedDict()
        )

        def squads_of(event_id: int) -> dict[bool, Squad | None]:
            """Both sides' squads of one match, parsed once (bounded cache)."""
            if event_id in squads:
                squads.move_to_end(event_id)
                return squads[event_id]
            found = conn.execute(
                "SELECT statistics_json, lineups_json FROM sofa_event_stats "
                "WHERE sofascore_event_id = ?",
                (event_id,),
            ).fetchone()
            stats = json.loads(found[0]) if found and found[0] else None
            lineups = json.loads(found[1]) if found and found[1] else None
            both = {
                h: squad_statistics(lineups, is_home=h, statistics=stats)
                for h in (True, False)
            }
            squads[event_id] = both
            if len(squads) > 50_000:
                squads.popitem(last=False)
            return both

        for event in targets:
            kickoff = int(event["startTimestamp"])
            competition = _competition_id(event)
            history: dict[bool, list[Squad]] = {}
            wide_history: dict[bool, list[Squad]] = {}
            for is_home in (True, False):
                entity = int(((event.get("homeTeam" if is_home else "awayTeam")) or {})
                             .get("id") or 0)
                admitted = []
                for past in entity_indexed_events(
                    conn, entity, "last", kickoff, PLAYER_HISTORY_LISTED
                ):
                    if not admitted_football_event(past, entity, kickoff):
                        continue
                    if is_same_match(past, event):
                        counts["history_same_match_dropped"] += 1
                        continue
                    admitted.append(past)
                recent = finish_history(
                    admitted, entity, "football", competition, kickoff,
                    PLAYER_WIDE_SAMPLE_N if coverage else sample_n,
                )
                side_squads: list[Squad] = []
                wide_squads: list[Squad] = []
                for i, past in enumerate(recent):
                    own_home = (past.get("homeTeam") or {}).get("id") == entity
                    squad = squads_of(int(past["id"]))[own_home]
                    if squad:
                        wide_squads.append(squad)
                        if i < sample_n:
                            side_squads.append(squad)
                history[is_home] = side_squads
                wide_history[is_home] = wide_squads
            produced = player_rows_for_event(
                event, squads_of(int(event["id"])), history, ladder, min_sample,
                counts, starters_only=starts_only, starts_only=starts_only,
                player_stretch=player_stretch,
                side_supremacy=(supremacy.get(int(event["id"]))
                                if player_stretch is not None else None),
                on_sample=on_sample,
                wide_history=wide_history if coverage else None,
                sample_n=sample_n,
            )
            counts["targets"] += 1
            if produced:
                counts["targets_with_rows"] += 1
            rows.extend(produced)
    finally:
        conn.close()
    return rows, counts


class ReliabilityAccumulator:
    """reliability_curve's counts, one row at a time (rows, sum of
    p_central, wins per market and bucket), so the replay never has to hold
    every row to measure them."""

    def __init__(self) -> None:
        self.by_market: dict[str, dict[str, list[float]]] = (
            collections.defaultdict(lambda: collections.defaultdict(
                lambda: [0.0, 0.0, 0.0]))
        )
        self.pooled: dict[str, list[float]] = collections.defaultdict(
            lambda: [0.0, 0.0, 0.0])
        self.rows = 0
        self.p_sum = 0.0
        self.wins = 0

    def add(self, row: SettledRow) -> None:
        index = min(9, int(row.p_central * 10))
        key = f"{index / 10.0:.1f}-{(index + 1) / 10.0:.1f}"
        won = 1.0 if row.won else 0.0
        for cell in (self.by_market[row.market][key], self.pooled[key]):
            cell[0] += 1
            cell[1] += row.p_central
            cell[2] += won
        self.rows += 1
        self.p_sum += row.p_central
        self.wins += int(won)

    def curve(self) -> dict[str, Any]:
        def entry(cell: list[float], corrected: bool) -> dict[str, Any]:
            n = int(cell[0])
            predicted = cell[1] / n
            realised = cell[2] / n
            enough = n >= 150
            correction = round(max(0.0, predicted - realised), 4)
            return {
                "rows": n,
                "predicted": round(predicted, 4),
                "realised": round(realised, 4),
                "correction": correction if (enough or not corrected) else 0.0,
                "status": "MEASURED" if enough else "TOO_FEW_ROWS",
            }

        out: dict[str, Any] = {
            "_doc": (
                "Measured by scripts/sofa/calibrate_from_cache.py from finished "
                "matches already in sofa.db, each scored against a sample built "
                "strictly before its own kickoff. `correction` is subtracted from "
                "p_central by the engine and is clamped to >= 0 there and here, so "
                "this file can only ever raise the bar. A bucket below "
                "`_min_rows` is written with correction 0.0 and its count, never "
                "dropped - an absent bucket and a measured-zero bucket must not "
                "look alike."
            ),
            "_min_rows": 150,
            # What a market with too few rows of its own falls back to. The
            # overconfidence being corrected is a property of the estimator - a
            # normal approximation fitted to ten observations - far more than of
            # any one market, so the pooled curve is a better estimate for a thin
            # market than pretending the correction is zero. Measured across
            # every market at once, which is why it is worth having.
            "_pooled": {
                bucket: entry(cell, corrected=False)
                for bucket, cell in sorted(self.pooled.items())
            },
        }
        for market, by_bucket in sorted(self.by_market.items()):
            out[market] = {
                bucket: entry(cell, corrected=True)
                for bucket, cell in sorted(by_bucket.items())
            }
        return out


def reliability_curve(rows: Iterable[SettledRow]) -> dict[str, Any]:
    """Per market, per probability bucket: what we said against what happened.

    The correction the engine consumes is `predicted - realised`, floored at
    zero. The engine may only ever *lower* p, so a market that turns out to be
    underconfident is left alone rather than being handed a discount.
    """
    acc = ReliabilityAccumulator()
    for row in rows:
        acc.add(row)
    return acc.curve()


# The unique key is (event, market, subject, line, direction) - run_date is not
# in it - so once the backfill put recent matches in the cache, a replay row
# shared its key with a live SETTLE row. INSERT OR REPLACE then swapped 3,154
# live rows (3,103 of them priced, the only input K_PRICE fits from) for
# market_p = NULL replay rows on 2026-09-26. A replay row may refresh another
# replay row; it never touches a row SETTLE wrote.
_ONLY_OVER_CACHE_ROWS = (
    "ON CONFLICT(sofascore_event_id, market, subject, line, direction) DO UPDATE SET "
    "sport=excluded.sport, competition_id=excluded.competition_id, "
    "sample_size=excluded.sample_size, sample_mean=excluded.sample_mean, "
    "sample_sd=excluded.sample_sd, p_central=excluded.p_central, "
    "p_bar=excluded.p_bar, market_p=excluded.market_p, "
    "actual_value=excluded.actual_value, outcome=excluded.outcome, "
    "settled_at=excluded.settled_at, ladder_sigma=excluded.ladder_sigma "
    "WHERE sofa_settled_row.run_date = 'cache-calibration'"
)

# Rows per commit in write_settled: short enough that a concurrent writer's
# 30 s busy timeout is never reached, long enough that commits do not dominate.
WRITE_BATCH = 50_000


# By event id, through the UNIQUE(sofascore_event_id, ...) index: the unary
# `+` keeps the planner off the run_date index, which after the inserts holds
# ~59M 'cache-calibration' rows - read once per stale id, 2,490 ids, the
# 2026-10-04 refit rehearsal stood in this DELETE for hours.
_DELETE_STALE_REPLAY_ROWS = (
    "DELETE FROM sofa_settled_row "
    "WHERE sofascore_event_id = ? AND +run_date = 'cache-calibration'"
)


def write_settled(
    rows: Iterable[SettledRow], db_path: Path, drop_event_ids: Iterable[int] = ()
) -> int:
    """Upsert the replay rows; delete the replay rows of collapsed copies.

    The upsert key is the event id, so collapsing a duplicate listing to one
    id (one_listing_per_match) left the rows an earlier run had stored under
    the OTHER id in the table, and every fit kept reading the match twice.
    `drop_event_ids` are those other ids: only their run_date =
    'cache-calibration' rows go - never a row SETTLE wrote - and never an id
    this run is writing.
    """
    # A long insert waits for a lock rather than failing in 5 s and leaving
    # the cache rows deleted (review 2026-10-03).
    conn = sqlite3.connect(str(db_path), timeout=300.0)
    written = 0
    try:
        # `rows` may be a generator (the replay streams ~90M rows since the
        # per-half markets, 2026-10-04), so the ids being written are known
        # only once it is spent; the stale ids are deleted after the inserts.
        # Committed every WRITE_BATCH rows: one transaction around a streamed
        # replay held the write lock for the whole computation, so a settle or
        # a daily loop writing meanwhile failed with "database is locked"
        # (night review 2026-10-04). Each row is an upsert, so a run cut off
        # between batches is repaired by running it again.
        writing: set[int] = set()
        for row in rows:
            writing.add(row.event_id)
            conn.execute(
                "INSERT INTO sofa_settled_row "
                "(run_date, sofascore_event_id, sport, competition_id, market, "
                " subject, line, direction, sample_size, sample_mean, "
                " sample_sd, p_central, p_bar, market_p, actual_value, "
                " outcome, settled_at, ladder_sigma) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                + _ONLY_OVER_CACHE_ROWS,
                (
                    "cache-calibration",
                    row.event_id,
                    row.sport,
                    row.competition_id,
                    row.market,
                    row.subject,
                    row.line,
                    row.direction,
                    row.sample_size,
                    row.sample_mean,
                    row.sample_sd,
                    row.p_central,
                    row.p_central,
                    None,
                    row.actual,
                    row.outcome,
                    datetime.now(UTC).isoformat(),
                    None,
                ),
            )
            written += 1
            if written % WRITE_BATCH == 0:
                conn.commit()
        stale = sorted(set(drop_event_ids) - writing)
        conn.executemany(
            _DELETE_STALE_REPLAY_ROWS, [(event_id,) for event_id in stale]
        )
        conn.commit()
    finally:
        conn.close()
    return written


def replay_players(
    db_path: Path,
    runs_dir: Path,
    baselines: dict[str, Any],
    config: SofaConfig,
    rows: list[SettledRow],
    starts_only: bool = False,
    football: FootballRatingReplay | None = None,
    coverage: bool = False,
) -> dict[str, Any]:
    """Append the player rows to `rows`; the summary's player metrics.
    `football` (a fresh rating replay) with CENTRE_RULES.player_stretch:
    the shots centres carry the supremacy term."""
    carried = sorted(k for k in baselines if is_player_metric(k))
    if carried:
        # SHEET would shrink a player toward these and the replay does not:
        # its rows would describe another model. fit_constants never writes
        # one (_in_baselines); a file that has them was edited by hand.
        return {"player_replay": f"SKIPPED: baselines carry {carried}"}
    started = datetime.now(UTC)
    ladder = printed_player_ladder(runs_dir)
    stretch = CENTRE_RULES.player_stretch
    produced, counts = build_player_rows(
        db_path, ladder, sample_n=config.sample_n, min_sample=config.min_sample,
        starts_only=starts_only,
        player_stretch=stretch if football is not None else None,
        football=football if stretch is not None else None,
        coverage=coverage,
    )
    rows.extend(produced)
    by_market = collections.Counter(r.market for r in produced)
    return {
        "player_replay": "OK" if produced else "NO_ROWS",
        "player_starts_only": starts_only,
        "player_coverage": coverage,
        "player_rows": len(produced),
        "player_rows_by_market": dict(sorted(by_market.items())),
        "player_ladder": ladder,
        "player_ladder_unprinted": sorted(set(PLAYER_METRICS) - set(ladder)),
        "player_counts": dict(sorted(counts.items())),
        "player_seconds": round((datetime.now(UTC) - started).total_seconds(), 1),
    }


def day_ts(day: str | None) -> int | None:
    """00:00Z of a YYYY-MM-DD day as unix seconds (None stays None)."""
    if day is None:
        return None
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=None)
    parser.add_argument(
        "--out",
        default=None,
        help=(
            "optional path for a raw (ungated) curve, for inspection only. "
            "The curve the engine reads is written by fit_constants.py from "
            "the rows this script inserts."
        ),
    )
    parser.add_argument(
        "--runs-dir",
        default=None,
        help="where the days' 04_offer.json live (the printed player ladder); "
        "default SOFA_RUNS_DIR / runs/sofa",
    )
    parser.add_argument(
        "--halves",
        choices=("include", "skip"),
        default="skip",
        help="the football per-half markets (HALF_BASES, since 2026-10-04) "
        "beside the full-match ones, or not (default: the replay as it was "
        "before them). Opt-in, an operator decision at a refit: measured "
        "2026-10-04 offline, ~31.5M rows; per-half curves from them would "
        "lapse AWAITING_OWN_CURVE for every per-half market listed there, and "
        "at p>=0.70 the replayed corners_2h_total OVER / corners_2h_for OVER / "
        "corners_1h_for OVER curves sit 7-10 pp above what their live rows "
        "realised (n=245-342) - see data/night_2026-10-03/g1h/",
    )
    parser.add_argument(
        "--players",
        choices=("include", "skip", "only"),
        default="include",
        help="football player markets beside the team markets (default), "
        "not at all, or alone (the team rows are then neither rebuilt nor "
        "touched)",
    )
    parser.add_argument(
        "--player-starts-only",
        action="store_true",
        help="football player rows as Superbet settles them: only a starter is "
        "an outcome, and his sample is his starts (epochs."
        "PLAYER_STARTS_ONLY_FROM_UTC; 2026-10-11). Default off: every "
        "appearance",
    )
    parser.add_argument(
        "--player-coverage",
        action="store_true",
        help="football player rows as SAMPLES builds them under epochs."
        "FOOTBALL_PLAYER_COVERAGE_FROM_UTC: a player thin in the newest "
        "sample_n is sampled over the newest samples.PLAYER_WIDE_SAMPLE_N, "
        "a woodwork shot counted once. Default off",
    )
    parser.add_argument(
        "--derived",
        default="",
        help="comma list of football bases whose both_over_ / most_ / handicap_ "
        f"joints are replayed beside the marginals ({', '.join(sorted(JOINT_BASES))};"
        " default none). ~5 ms (goals) to ~15 ms (corners) a match for the "
        "joint and ~120 rows a match and base - an opt-in, an operator decision "
        "at a refit; fit_confidence reads them into their own curves only",
    )
    parser.add_argument(
        "--tennis-rating",
        choices=("include", "skip"),
        default="include",
        help="price the tennis games rows the way SHEET does since "
        "epochs.TENNIS_RATING_PRICES_FROM_UTC (2026-10-07): games_won_for, "
        "handicap_games, most_games from the rating's neighbours as of the "
        "match's day, games_total mixed with the NB (default). `skip` is the "
        "replay as it was: the sample estimator alone, no derived rows. "
        "Needs config/tennis_rating.json (SOFA_CONFIG_DIR) and the cached "
        "player listings (tennis_rating.load_history, ~30 s, ~250 MB)",
    )
    parser.add_argument(
        "--tennis-scoped-table",
        action="store_true",
        help="replay the tennis rating as SHEET prices it under "
        "epochs.TENNIS_SCOPED_TABLE_FROM_UTC: the neighbour table cut by tier "
        "x gender (tier, then pooled, when a cell is thin) and the tier "
        "start of config/tennis_rating.json when it names lp_t. Default off: "
        "the pooled table. Needs the V5 config staged in SOFA_CONFIG_DIR "
        "(fit_tennis_rating.py --tier-start --out ...); the curves fitted "
        "from such a replay describe that rule and no other. A refit that "
        "replays it must not be installed without the switch. Limitation: "
        "the tier_start offsets are fitted from the players' Elo at the cut "
        "(fit_tennis_rating --tier-start) and applied to every replayed "
        "earlier match - an in-sample look-ahead of the same kind as the "
        "coefficients'",
    )
    parser.add_argument(
        "--count-dispersion",
        nargs="?", const="", default=None, metavar="CONFIG",
        help="price the football counts with the dispersion fitted on the "
        "history, as SHEET does under epochs.COUNT_DISPERSION_FROM_UTC "
        "(bet.sofa.count_dispersion; CONFIG defaults to config/"
        "sofa_count_dispersion.json, SOFA_CONFIG_DIR). Default off: the sample "
        "variance. A staged refit that replays it describes the rule that "
        "ships with the switch; the alphas were fitted on the same history, "
        "so the replay is in-sample for them (a few parameters per market)",
    )
    parser.add_argument(
        "--cards-correlation", action="store_true",
        help="price the football cards joints (both_over_ / most_ / handicap_ "
        "cards_points) with the sides correlated at epochs."
        "CARDS_CORRELATION_RHO, as SHEET does under epochs."
        "CARDS_CORRELATION_FROM_UTC. Default off: independent sides. Needs "
        "--derived with a cards joint; the number was measured on the same "
        "history (in-sample for one parameter)",
    )
    parser.add_argument(
        "--per-market-k", action="store_true",
        help="shrink the football centres with the K of their own market "
        "(config/sofa_engine_constants.json K_CENTRE.by_market.football; "
        "bet.sofa.per_market_k), as SHEET does under epochs."
        "PER_MARKET_K_FROM_UTC. Default off: the sport's K. The K were chosen "
        "on the same history (docs/sofa/evidence/k_under_dispersion_"
        "2026-10-08.md), so the replay is in-sample for them",
    )
    parser.add_argument(
        "--football-rating", action="store_true",
        help="audit 2026-10-13 A6: price the football marginal rows (and the "
        "--derived joints' centres) with SHEET's live centre - the football "
        "rating book replayed in time order to each match's UTC day start "
        "(football_rating.load_history, the pickle next to the DB; ~10 min "
        "the first time) and blended with the shrunk sample centre at "
        "W_FOOTBALL_RATING (live_centre). Default off: the sample centre "
        "alone, byte for byte as before",
    )
    parser.add_argument(
        "--rated-scope", action="store_true",
        help="with --football-rating: the rating also prices RATED_SCOPE_"
        "MARKETS (epochs.FOOTBALL_RATED_SCOPE_FROM_UTC, audit B2)",
    )
    parser.add_argument(
        "--venue-prior", action="store_true",
        help="with --football-rating: a sample-only side centre of VENUE_"
        "PRIOR_MARKETS x the league venue multiplier (epochs.FOOTBALL_VENUE_"
        "PRIOR_FROM_UTC, audit B2)",
    )
    parser.add_argument(
        "--game-state", nargs="?", const="", default=None, metavar="CONFIG",
        help="with --football-rating: the game-state term exp(beta x expected "
        "goal difference) (epochs.GAME_STATE_FROM_UTC, audit B1; CONFIG "
        "defaults to config/sofa_game_state.json, SOFA_CONFIG_DIR). The betas "
        "were fitted on the same history: in-sample for them",
    )
    parser.add_argument(
        "--goals-stretch", nargs="?", const="", default=None, metavar="CONFIG",
        help="with --football-rating: a goals centre x the supremacy stretch, "
        "exp(beta x s) on goals_for / goals_1h_for / goals_2h_for and "
        "exp(g1 |s| + g2 s^2) on the totals, s the expected goal difference "
        "(epochs.FOOTBALL_GOALS_STRETCH_FROM_UTC; CONFIG defaults to "
        "config/sofa_goals_stretch.json; a market's coefficients may be per "
        "season phase). Fitted on the same history: in-sample for it",
    )
    parser.add_argument(
        "--count-stretch", nargs="?", const="", default=None, metavar="CONFIG",
        help="with --football-rating: a count centre outside GAME_STATE "
        "(count_stretch.COUNT_STRETCH_MARKETS) x the supremacy stretch, "
        "exp(beta x s [+ beta2 x s^2]) on a side, exp(g1 |s| + g2 s^2) on a "
        "total (epochs.FOOTBALL_COUNT_STRETCH_FROM_UTC; CONFIG defaults to "
        "config/sofa_count_stretch.json). Fitted on the same history: "
        "in-sample for it",
    )
    parser.add_argument(
        "--player-stretch", nargs="?", const="", default=None, metavar="CONFIG",
        help="with --football-rating: a footballer's shots centre "
        "(player_stretch.PLAYER_STRETCH_MARKETS) x exp(beta x s), s his side's "
        "expected goal difference from a rating book replayed for the player "
        "targets (epochs.FOOTBALL_PLAYER_STRETCH_FROM_UTC; CONFIG defaults to "
        "config/sofa_player_stretch.json). Fitted on the same history: "
        "in-sample for it",
    )
    parser.add_argument(
        "--rating-weight", nargs="?", const="", default=None, metavar="CONFIG",
        help="with --football-rating: the rating blended at the market's "
        "fitted W (epochs.FOOTBALL_RATING_WEIGHT_FROM_UTC, audit B14; CONFIG "
        "defaults to config/sofa_rating_weight.json). Fitted on the same "
        "history: in-sample for it",
    )
    parser.add_argument(
        "--season-phase", nargs="?", const="", default=None, metavar="CONFIG",
        help="with --football-rating: the goals centre x exp(c[market][phase]),"
        " the phase as of the kickoff (epochs.SEASON_PHASE_FROM_UTC, audit C1;"
        " CONFIG defaults to config/sofa_season_phase.json). Fitted on the "
        "same history: in-sample for it",
    )
    parser.add_argument(
        "--opponent-correction", action="store_true",
        help="with --football-rating: the football side / total samples "
        "rescaled to a neutral opponent (x / def(opponent)^c) and to the "
        "match's league domain through the rating book as of the match's day, "
        "before their mean, variance and centre (epochs.SAMPLE_OPPONENT_"
        "CORRECTION_FROM_UTC, audit B15 / A5; bet.sofa.opponent_correction). "
        "Goals and player markets stay raw. Default off: the raw sample",
    )
    parser.add_argument(
        "--cup-strength", nargs="?", const="", default=None, metavar="CONFIG",
        help="with --football-rating: the rating book learns a per-league "
        "correction in international club cups and reads it on their "
        "cross-league fixtures, as SHEET under epochs.FOOTBALL_CUP_STRENGTH_"
        "FROM_UTC (bet.sofa.cup_strength; CONFIG defaults to config/"
        "sofa_cup_strength.json). Default off: the book as it was",
    )
    parser.add_argument(
        "--tennis-sample-scope", action="store_true",
        help="a tennis side's sample scoped as SAMPLES scopes it: the "
        "fixture's format (best of 3 / 5) and a comparable surface. Default "
        "off: the last SAMPLE_N matches of any format and surface",
    )
    parser.add_argument(
        "--sample-cup-strength", action="store_true",
        help="with --opponent-correction and --cup-strength: the sample "
        "correction's gaps read the cup league strength with the past match's "
        "and the fixture's competition (epochs.SAMPLE_CUP_STRENGTH_FROM_UTC)",
    )
    parser.add_argument(
        "--tennis-aces-opponent", action="store_true",
        help="epochs.TENNIS_ACES_OPPONENT: an aces row's centre x today's "
        "returner's factor (bet.sofa.tennis_aces_opponent; the tier "
        "baselines' full-match aces prior), as SHEET prices it. Default "
        "off: the server's sample alone",
    )
    parser.add_argument(
        "--tennis-serve-markets", action="store_true",
        help="replay the tennis per-set aces / double faults and the aces + "
        "double faults markets (serve_points, match and per set) from "
        "/statistics (SERVE_BASES); default off: no such rows, their curves "
        "only from live SETTLE",
    )
    parser.add_argument(
        "--tennis-set-ratings", action="store_true",
        help="audit 2026-10-13 B5: replay the tennis per-set games "
        "(games_set1/2_total, games_won_set1/2/3_for) and sets_total from "
        "the listing's set score, priced off the rating's neighbours as of "
        "the match's day as SHEET prices them under epochs.TENNIS_SET_RATING_"
        "PRICES_FROM_UTC. Needs --tennis-rating include. Default off: no "
        "such rows",
    )
    parser.add_argument(
        "--from", dest="emit_from", default=None, metavar="YYYY-MM-DD",
        help="smoke window: rows only for matches from this UTC day (earlier "
        "ones still build the histories and the books)",
    )
    parser.add_argument(
        "--to", dest="emit_to", default=None, metavar="YYYY-MM-DD",
        help="smoke window: rows only for matches before this UTC day",
    )
    parser.add_argument(
        "--history-from", default=None, metavar="YYYY-MM-DD",
        help="smoke only (needs --no-write): hold only the matches from this "
        "UTC day (to --to), so a smoke does not load the whole history; the "
        "samples of the window's first weeks are then thinner than a "
        "rebuild's. The rating books (football, tennis) still read their "
        "whole history",
    )
    parser.add_argument(
        "--no-write", action="store_true",
        help="count and time the rows, write nothing to the DB (a smoke run)",
    )
    args = parser.parse_args()
    needs_rating = [name for name, on in (
        ("--rated-scope", args.rated_scope), ("--venue-prior", args.venue_prior),
        ("--game-state", args.game_state is not None),
        ("--goals-stretch", args.goals_stretch is not None),
        ("--count-stretch", args.count_stretch is not None),
        ("--player-stretch", args.player_stretch is not None),
        ("--rating-weight", args.rating_weight is not None),
        ("--season-phase", args.season_phase is not None),
        ("--opponent-correction", args.opponent_correction),
        ("--cup-strength", args.cup_strength is not None)) if on]
    if args.sample_cup_strength and not (
            args.opponent_correction and args.cup_strength is not None):
        parser.error("--sample-cup-strength needs --opponent-correction and "
                     "--cup-strength")
    if needs_rating and not args.football_rating:
        # SHEET applies them only through its FootballForecast
        parser.error(f"{', '.join(needs_rating)} need --football-rating")
    if args.tennis_set_ratings and args.tennis_rating != "include":
        # rides on the rating prices (epochs.tennis_set_rating_prices)
        parser.error("--tennis-set-ratings needs --tennis-rating include")
    if args.history_from is not None and not args.no_write:
        # a cut history is a smoke: its rows would describe thinner samples
        parser.error("--history-from needs --no-write")
    if (args.count_dispersion is not None) != bool(args.per_market_k):
        # fitted jointly: SHEET refuses one without the other
        # (epochs.require_k_with_dispersion), so the replay must too
        parser.error("--count-dispersion and --per-market-k go together "
                     "(they were fitted jointly); give both or neither")

    global COUNT_DISPERSION, CARDS_CORRELATION, PER_MARKET_K
    global CENTRE_RULES, TENNIS_SET_RATINGS, TENNIS_SAMPLE_SCOPE
    global TENNIS_ACES_OPPONENT, TENNIS_ACES_TIERS
    CARDS_CORRELATION = bool(args.cards_correlation)
    PER_MARKET_K = bool(args.per_market_k)
    TENNIS_SET_RATINGS = bool(args.tennis_set_ratings)
    TENNIS_SAMPLE_SCOPE = bool(args.tennis_sample_scope)
    TENNIS_ACES_OPPONENT = bool(args.tennis_aces_opponent)
    if TENNIS_ACES_OPPONENT:
        TENNIS_ACES_TIERS = load_tier_baselines()
        if not TENNIS_ACES_TIERS:
            raise SystemExit("--tennis-aces-opponent: no tennis tier "
                             "baselines (config/sofa_tennis_tier_baselines.json)")
    if args.football_rating:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        CENTRE_RULES = CentreRules(
            football_rating=True,
            rated_scope=bool(args.rated_scope),
            venue_prior=bool(args.venue_prior),
            game_state=(
                load_game_state_table(
                    Path(args.game_state) if args.game_state else None)
                if args.game_state is not None else None),
            goals_stretch=(
                load_goals_stretch_table(
                    Path(args.goals_stretch) if args.goals_stretch else None)
                if args.goals_stretch is not None else None),
            count_stretch=(
                load_count_stretch_table(
                    Path(args.count_stretch) if args.count_stretch else None)
                if args.count_stretch is not None else None),
            player_stretch=(
                load_player_stretch_table(
                    Path(args.player_stretch) if args.player_stretch else None)
                if args.player_stretch is not None else None),
            rating_weights=(
                load_rating_weight_table(
                    Path(args.rating_weight) if args.rating_weight else None)
                if args.rating_weight is not None else None),
            season_phase=(
                load_season_phase_table(
                    Path(args.season_phase) if args.season_phase else None)
                if args.season_phase is not None else None),
            opponent_correction=bool(args.opponent_correction),
            cup_strength=(
                load_cup_strength(
                    Path(args.cup_strength) if args.cup_strength else None)
                if args.cup_strength is not None else None),
            cup_strength_path=(args.cup_strength or "config/sofa_cup_strength.json"
                               if args.cup_strength is not None else None),
            sample_cup_strength=bool(args.sample_cup_strength),
            # the book's rules SHEET would use for a day built now
            shared_league_link=epochs.link_shared_league(today),
            unit_strength_from_parent=epochs.unit_strength_from_parent(today),
            strict_league_rate=epochs.football_league_rate_rule(today),
        )
    if args.count_dispersion is not None:
        COUNT_DISPERSION = load_dispersion_table(
            Path(args.count_dispersion) if args.count_dispersion else None)

    config = SofaConfig.from_env()
    db_path = Path(args.db_path or config.db_path)
    joint_bases = frozenset(b for b in args.derived.split(",") if b)
    if joint_bases - JOINT_BASES:
        raise SystemExit(f"--derived: {sorted(joint_bases - JOINT_BASES)} "
                         f"not in {sorted(JOINT_BASES)}")
    rating: RatingReplay | None = None
    if args.tennis_rating == "include" and args.players != "only":
        rating = RatingReplay.from_db(db_path, args.tennis_scoped_table)
        if rating is None:
            # A replay that silently reverts to the sample estimator would
            # fit a curve for a model that no longer ships.
            raise SystemExit("config/tennis_rating.json absent: "
                             "--tennis-rating skip, or fit it first")

    dropped: set[int] = set()
    played: list[Played] = []
    baselines = load_baselines()
    t_load = datetime.now(UTC)
    if args.players != "only":
        load_kw: dict[str, Any] = {}
        if args.tennis_serve_markets:
            load_kw["tennis_serve"] = True
        if TENNIS_SET_RATINGS:
            load_kw["tennis_sets"] = True
        if args.history_from is not None:
            # a light smoke: the held history starts here, nothing after --to
            load_kw["since_ts"] = day_ts(args.history_from)
            load_kw["until_ts"] = day_ts(args.emit_to)
        played = load_cache(db_path, dropped, **load_kw)
        if args.halves == "skip":
            played = without_halves(played)
    load_seconds = round((datetime.now(UTC) - t_load).total_seconds(), 1)

    # --player-stretch: the player targets read their own rating replay (the
    # team replay's book must start fresh), from the one history load
    player_stretch_on = (CENTRE_RULES.player_stretch is not None
                         and args.players != "skip")
    football_history: list[FootballResult] | None = None
    football_seconds: float | None = None
    if CENTRE_RULES.football_rating and (played or player_stretch_on):
        t_hist = datetime.now(UTC)
        football_history = load_football_history(db_path, db_path.parent / "cache")
        football_seconds = round(
            (datetime.now(UTC) - t_hist).total_seconds(), 1)

    player_rows: list[SettledRow] = []
    player_metrics: dict[str, Any] = {"player_replay": "SKIPPED"}
    if args.players != "skip":
        player_metrics = replay_players(
            db_path,
            Path(args.runs_dir or config.runs_dir),
            baselines,
            config,
            player_rows,
            starts_only=args.player_starts_only,
            coverage=args.player_coverage,
            football=(FootballRatingReplay(football_history, CENTRE_RULES)
                      if player_stretch_on and football_history is not None
                      else None),
        )

    football: FootballRatingReplay | None = None
    if CENTRE_RULES.football_rating and played and football_history is not None:
        football = FootballRatingReplay(football_history, CENTRE_RULES)
    # each replay holds its own sorted copy: the loaded list is not read again
    football_history = None

    emit_from, emit_to = day_ts(args.emit_from), day_ts(args.emit_to)
    window = emit_from is not None or emit_to is not None

    # The team rows are streamed into the DB, never held: 56M rows on the
    # 2026-10-03 refit, ~31M more since the per-half markets (2026-10-04).
    acc = ReliabilityAccumulator()
    team_count = [0]
    team_events: set[int] = set()
    by_market: collections.Counter[str] = collections.Counter()
    t_rows = datetime.now(UTC)

    def measured() -> Iterator[SettledRow]:
        team = iter_rows(played, baselines, rating, joint_bases, football,
                         emit_from, emit_to) if played else iter(())
        for row in team:
            team_count[0] += 1
            if window or args.no_write:
                team_events.add(row.event_id)
                by_market[row.market] += 1
            acc.add(row)
            yield row
        for row in player_rows:
            acc.add(row)
            yield row

    if args.no_write:
        written = 0
        for _ in measured():
            pass
    else:
        # a window's rows are a smoke, not a rebuild: the collapsed copies'
        # rows are deleted only by a whole replay
        written = write_settled(measured(), db_path,
                                set() if window else dropped)
    rows_seconds = round((datetime.now(UTC) - t_rows).total_seconds(), 1)
    team_rows = team_count[0]
    window_played = [
        m for m in played
        if (emit_from is None or m.timestamp >= emit_from)
        and (emit_to is None or m.timestamp < emit_to)
    ]
    curve = acc.curve()
    if args.out:
        # Off by default. `fit_constants.py` owns
        # config/sofa_market_reliability.json and applies a confidence-interval
        # gate this script does not; two writers on one file meant whichever
        # ran last won, and the first time that happened an empty file
        # overwrote a measured one and reported success.
        write_atomic(
            Path(args.out),
            json.dumps(curve, indent=2, ensure_ascii=False) + "\n",
        )

    measured_buckets = sum(
        1
        for market, entry in curve.items()
        if not market.startswith("_")
        for bucket in entry.values()
        if bucket["status"] == "MEASURED"
    )
    overall_predicted = acc.p_sum / acc.rows if acc.rows else 0.0
    overall_realised = acc.wins / acc.rows if acc.rows else 0.0
    # Players asked for and none produced is not a success: a wrong runs dir
    # (no 04_offer.json, so no printed ladder) emptied the player replay with
    # exit 0 and the refit fitted on no player rows (review 2026-10-03).
    players_missing = args.players != "skip" and player_metrics.get(
        "player_replay"
    ) != "OK"
    summary = {
        "stage": "CALIBRATE_FROM_CACHE",
        "verdict": "OK" if acc.rows and not players_missing else "PARTIAL",
        "metrics": {
            "matches_replayed": len(played),
            "settled_rows": acc.rows,
            "team_rows": team_rows,
            **player_metrics,
            "markets": len([m for m in curve if not m.startswith("_")]),
            "measured_buckets": measured_buckets,
            "overall_predicted": round(overall_predicted, 4),
            "overall_realised": round(overall_realised, 4),
            "overall_overconfidence": round(
                overall_predicted - overall_realised, 4
            ),
            "rows_written_to_db": written,
            "half_rows_by_market": {
                market: sum(int(cell[0]) for cell in by_bucket.values())
                for market, by_bucket in sorted(acc.by_market.items())
                if "_1h_" in market or "_2h_" in market
            },
            "duplicate_listing_ids_dropped": len(dropped),
            "tennis_rating": args.tennis_rating,
            "tennis_scoped_table": args.tennis_scoped_table,
            "tennis_rating_forecasts": rating.forecasts if rating else None,
            "tennis_rating_unrated": rating.unrated if rating else None,
            # the replay's rules, for fitted_from (prepare_refit records them)
            "replay_rules": {
                **CENTRE_RULES.describe(),
                "tennis_set_ratings": TENNIS_SET_RATINGS,
                "tennis_sample_scope": TENNIS_SAMPLE_SCOPE,
                "tennis_aces_opponent": TENNIS_ACES_OPPONENT,
                "tennis_serve_markets": bool(args.tennis_serve_markets),
                "tennis_rating": args.tennis_rating,
                "tennis_scoped_table": args.tennis_scoped_table,
                "count_dispersion": args.count_dispersion is not None,
                "per_market_k": bool(args.per_market_k),
                "cards_correlation": bool(args.cards_correlation),
                "halves": args.halves,
                "derived": sorted(joint_bases),
                "player_starts_only": bool(args.player_starts_only),
                "player_coverage": bool(args.player_coverage),
            },
            "football_rating_forecasts": football.forecasts if football else None,
            "football_history_results": football.seen if football else None,
            "football_history_seconds": football_seconds,
            "load_seconds": load_seconds,
            "rows_seconds": rows_seconds,
            "window": [args.emit_from, args.emit_to] if window else None,
            "window_matches": len(window_played) if window else None,
            "window_matches_by_sport": dict(collections.Counter(
                m.sport for m in window_played)) if window else None,
            "matches_with_rows": len(team_events) if team_events else None,
            "team_rows_by_market": (dict(sorted(by_market.items()))
                                    if by_market else None),
            "no_write": bool(args.no_write),
            "next_step": "python -m scripts.sofa.fit_constants",
        },
        "output_path": args.out,
    }
    print(f"SOFA_SUMMARY: {json.dumps(summary)}", flush=True)
    return 1 if players_missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
