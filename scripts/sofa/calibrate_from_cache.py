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

Football player markets (F54, since 2026-10-03) are replayed beside the team
markets, from the cached `/lineups` - see `build_player_rows`. Their rows
carry the same marking (run_date 'cache-calibration', p_bar = p_central,
market_p NULL); the subject is the player's normalised Sofascore name.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import sqlite3
import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

from bet.sofa.atomic import write_atomic
from bet.sofa.config import SofaConfig, config_path
from bet.sofa.contracts import GapReason
from bet.sofa.engine import (
    outside_model_resolution,
    p_empirical_centred_raw,
    sheet_count_p_raw,
    sheet_predictive_sd,
    uses_empirical_frequency,
    winning_boundary,
)
from bet.sofa.listing_index import entity_indexed_events, listed_events_by_id
from bet.sofa.metrics import (
    calculate_cards_points,
    extract_flat_statistics,
    regulation_score,
    stat_is_untracked,
)
from bet.sofa.players import (
    PLAYER_METRICS,
    extract_player_metric,
    is_player_metric,
    match_player,
    squad_statistics,
)
from bet.sofa.samples import (
    FRIENDLY_COMPETITION_IDS,
    MIN_HOURS_BETWEEN_MATCHES,
    _competition_id,
    finish_history,
    one_listing_per_match,
)
from bet.sofa.settle import is_completed_event, settle

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

# The sheet's own default when nothing is fitted. Calibrating against a
# different value would measure a model that does not ship.
# The pipeline's per-side tennis games market is `games_won_for`, not
# `games_for`. A curve keyed on a name the engine never looks up is a
# correction that silently does nothing, which is worse than no curve at all
# because the artifact then claims to be calibrated.
MARKET_NAME_OVERRIDES = {("games", "for"): "games_won_for"}


def market_name(base: str, suffix: str) -> str:
    return MARKET_NAME_OVERRIDES.get((base, suffix), f"{base}_{suffix}")


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

    if sport == "football":
        score = regulation_score(event)
        if score is not None:
            values["goals"] = score

    all_period: dict[str, tuple[float, float]] = {}
    if statistics_json:
        try:
            flat = extract_flat_statistics(json.loads(statistics_json))
        except ValueError:
            flat = {}
        all_period = flat.get("ALL", {})
        for base, key in STAT_KEYS.items():
            pair = all_period.get(key)
            # The same placeholder-zero refusal the sheet applies.
            if pair is not None and not stat_is_untracked(key, pair):
                values[base] = (float(pair[0]), float(pair[1]))
    if incidents_json:
        try:
            points = calculate_cards_points(json.loads(incidents_json), all_period)
        except ValueError:
            points = None
        if points is not None and not isinstance(points, str):
            values["cards_points"] = (float(points[0]), float(points[1]))
    return values


def load_cache(
    db_path: Path, dropped_out: set[int] | None = None
) -> list[Played]:
    """Every finished cached match, one listing per match.

    `dropped_out`, when given, receives the event ids the duplicate-listing
    collapse removed, so write_settled can delete the replay rows an earlier
    run stored under them.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        # The first *finished* copy of each event on any cached page, then the
        # listed-event index (listing_index.py), whose newer finished copy
        # wins. Only finished copies are kept: the replay drops the rest below
        # anyway, and keeping the first copy of any status let a stale
        # pre-match copy (a `next` page) block the finished one - on a later
        # page or in the index (2026-10-02 review, F5).
        def finished_copy(event: dict[str, Any]) -> dict[str, Any] | None:
            status = (event.get("status") or {}).get("type")
            return event if status == "finished" else None

        identity = listed_events_by_id(conn, finished_copy, kinds=None)

        stats_by_event: dict[int, tuple[str | None, str | None]] = {}
        for event_id, statistics_json, incidents_json in conn.execute(
            "SELECT sofascore_event_id, statistics_json, incidents_json "
            "FROM sofa_event_stats WHERE status_type = 'finished'"
        ):
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
        event_id = int(event["id"])
        home = (event.get("homeTeam") or {}).get("id")
        away = (event.get("awayTeam") or {}).get("id")
        started = event.get("startTimestamp")
        if not home or not away or not started:
            continue
        sport = (
            ((event.get("tournament") or {}).get("category") or {}).get("sport") or {}
        ).get("slug")
        if sport not in ("football", "tennis"):
            continue
        unique = ((event.get("tournament") or {}).get("uniqueTournament") or {}).get(
            "id"
        )

        statistics_json, incidents_json = stats_by_event.get(event_id, (None, None))
        values = match_values(event, sport, statistics_json, incidents_json)

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
                )
            )

    played.sort(key=lambda p: p.timestamp)
    return played


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


def build(played: list[Played], baselines: dict[str, Any]) -> list[SettledRow]:
    # Read once: the constant is per sport and must be the one that ships.
    engine_constants = _load_engine_constants()
    # (team, base) -> chronological list of earlier matches
    history: dict[tuple[int, str], list[Past]] = collections.defaultdict(list)
    rows: list[SettledRow] = []

    for match in played:
        for base, (home_value, away_value) in match.values.items():
            total = home_value + away_value
            home_recent = history[(match.home_id, base)][-SAMPLE_N:]
            away_recent = history[(match.away_id, base)][-SAMPLE_N:]

            # `*_for`: each side from its own history only, as SHEET does
            # (determine_side; h2h never reaches a per-side market).
            for team, own, recent in (
                (match.home_id, home_value, home_recent),
                (match.away_id, away_value, away_recent),
            ):
                if len(recent) >= MIN_SAMPLE:
                    rows.extend(
                        _settle_sample(
                            match,
                            market_name(base, "for"),
                            str(team),
                            own,
                            [p.own for p in recent],
                            baselines,
                            engine_constants,
                        )
                    )

            # `*_total`: ONE row set per match, from the pooled sample, and
            # only when BOTH sides have a sample - SHEET refuses a total with
            # either side thin (THIN_SAMPLE, "total pools both sides").
            # Residual difference from the sheet, not removable here: the
            # per-side threshold is this replay's MIN_SAMPLE (8), not the
            # sheet's config.min_sample (5); the per-side sample is the last
            # SAMPLE_N matches that HAVE this statistic, where SAMPLES takes
            # the last sample_n events and loses the gaps; and SAMPLES'
            # scoping (friendlies out, tennis surface / best-of) is not
            # replayed - the same differences every `*_for` row already has.
            if len(home_recent) >= MIN_SAMPLE and len(away_recent) >= MIN_SAMPLE:
                rows.extend(
                    _settle_sample(
                        match,
                        market_name(base, "total"),
                        "",
                        total,
                        pooled_total_sample(home_recent, away_recent),
                        baselines,
                        engine_constants,
                    )
                )

        # Only after settling: a match may never contribute to its own sample.
        for base, (home_value, away_value) in match.values.items():
            total = home_value + away_value
            history[(match.home_id, base)].append(
                Past(match.timestamp, match.event_id, home_value, total)
            )
            history[(match.away_id, base)].append(
                Past(match.timestamp, match.event_id, away_value, total)
            )

    return rows


def _settle_sample(
    match: Played,
    market: str,
    subject: str,
    actual: float,
    sample: list[float],
    baselines: dict[str, Any],
    engine_constants: dict[str, Any],
) -> list[SettledRow]:
    out: list[SettledRow] = []
    n = len(sample)
    if n < MIN_SAMPLE or all(v == 0.0 for v in sample):
        return out
    mean = statistics.mean(sample)
    variance = statistics.variance(sample) if n > 1 else 0.0
    sample_sd = statistics.stdev(sample) if n > 1 else 0.0

    prior = prior_for(baselines, market, match.competition_id)
    if prior is not None:
        k_centre = k_centre_for(match.sport, engine_constants)
        weight = n / (n + k_centre)
        centre = weight * mean + (1.0 - weight) * prior
    else:
        centre = mean

    # SHEET's spread and SHEET's estimator, from the functions SHEET calls
    # (see the module docstring). What is NOT replayed, and so still differs
    # from a live row: the football rating's centre (W_FOOTBALL_RATING), the
    # tennis rating and the tennis tier / ladder priors - the replay's centre
    # is the league-baseline shrink alone.
    spread = sheet_predictive_sd(market, match.sport, mean, variance, n, centre)
    empirical = uses_empirical_frequency(market)

    for line in lines_for(centre):
        for direction in ("OVER", "UNDER"):
            boundary = winning_boundary(line, direction)
            if empirical:
                # run_sheet refuses an empirical rung whose raw frequency is
                # outside resolution before it looks at the shrunk one.
                hits = sum(
                    1 for v in sample
                    if (v > boundary if direction == "OVER" else v < boundary)
                )
                if outside_model_resolution(hits / n):
                    continue
                p_raw = p_empirical_centred_raw(
                    sample, boundary, direction, centre - mean
                )
            else:
                p_raw = sheet_count_p_raw(
                    market, centre, spread, boundary, direction
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


def player_rows_for_event(
    event: dict[str, Any],
    target: dict[bool, Squad | None],
    history: dict[bool, list[Squad]],
    ladder: dict[str, list[float]],
    min_sample: int,
    counts: collections.Counter[str] | None = None,
) -> list[SettledRow]:
    """Every settled player rung of one finished match.

    `target[is_home]` is that side's squad in this match (squad_statistics,
    with this match's /statistics); `history[is_home]` the side's historical
    squads, newest first - one per sampled match that has a squad.
    """
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
            tally["appearances"] += 1
            if name in both:
                tally["name_in_both_squads"] += 1
                continue
            # build_player_samples' match: per historical squad, by name.
            matched = {
                side: [(past, match_player(name, past)) for past in squads]
                for side, squads in history.items()
            }
            for metric, lines in ladder.items():
                if not lines:
                    continue
                actual = extract_player_metric(metric, stats)
                if isinstance(actual, GapReason):
                    tally[f"actual_gap:{metric}"] += 1
                    continue
                per_side: dict[bool, list[float]] = {}
                for side, pairs in matched.items():
                    values: list[float] = []
                    for past, key in pairs:
                        if key is None:
                            continue
                        value = extract_player_metric(metric, past[key])
                        if not isinstance(value, GapReason):
                            values.append(value)
                    per_side[side] = values
                n_home = len(per_side.get(True, []))
                n_away = len(per_side.get(False, []))
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
                spread = sheet_predictive_sd(
                    metric, "football", mean, variance, n, mean
                )
                tally["samples"] += 1
                for line in lines:
                    for direction in ("OVER", "UNDER"):
                        boundary = winning_boundary(line, direction)
                        p_raw = sheet_count_p_raw(
                            metric, mean, spread, boundary, direction
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


def build_player_rows(
    db_path: Path,
    ladder: dict[str, list[float]],
    *,
    sample_n: int,
    min_sample: int,
) -> tuple[list[SettledRow], collections.Counter[str]]:
    """The player rows of every finished football match with a squad list."""
    counts: collections.Counter[str] = collections.Counter()
    if not any(ladder.values()):
        counts["no_printed_player_ladder"] += 1
        return [], counts
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows: list[SettledRow] = []
    try:
        targets = player_targets(conn, counts)
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
                    admitted, entity, "football", competition, kickoff, sample_n
                )
                side_squads: list[Squad] = []
                for past in recent:
                    own_home = (past.get("homeTeam") or {}).get("id") == entity
                    squad = squads_of(int(past["id"]))[own_home]
                    if squad:
                        side_squads.append(squad)
                history[is_home] = side_squads
            produced = player_rows_for_event(
                event, squads_of(int(event["id"])), history, ladder, min_sample,
                counts,
            )
            counts["targets"] += 1
            if produced:
                counts["targets_with_rows"] += 1
            rows.extend(produced)
    finally:
        conn.close()
    return rows, counts


def reliability_curve(rows: list[SettledRow]) -> dict[str, Any]:
    """Per market, per probability bucket: what we said against what happened.

    The correction the engine consumes is `predicted - realised`, floored at
    zero. The engine may only ever *lower* p, so a market that turns out to be
    underconfident is left alone rather than being handed a discount.
    """
    buckets: dict[str, dict[str, list[SettledRow]]] = collections.defaultdict(
        lambda: collections.defaultdict(list)
    )
    for row in rows:
        index = min(9, int(row.p_central * 10))
        key = f"{index / 10.0:.1f}-{(index + 1) / 10.0:.1f}"
        buckets[row.market][key].append(row)

    pooled: dict[str, list[SettledRow]] = collections.defaultdict(list)
    for row in rows:
        index = min(9, int(row.p_central * 10))
        pooled[f"{index / 10.0:.1f}-{(index + 1) / 10.0:.1f}"].append(row)

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
        # overconfidence being corrected is a property of the estimator — a
        # normal approximation fitted to ten observations — far more than of
        # any one market, so the pooled curve is a better estimate for a thin
        # market than pretending the correction is zero. Measured across every
        # market at once, which is why it is worth having.
        "_pooled": {
            bucket: {
                "rows": len(bucket_rows),
                "predicted": round(
                    statistics.mean(r.p_central for r in bucket_rows), 4
                ),
                "realised": round(
                    sum(1 for r in bucket_rows if r.won) / len(bucket_rows), 4
                ),
                "correction": round(
                    max(
                        0.0,
                        statistics.mean(r.p_central for r in bucket_rows)
                        - sum(1 for r in bucket_rows if r.won) / len(bucket_rows),
                    ),
                    4,
                ),
                "status": "MEASURED" if len(bucket_rows) >= 150 else "TOO_FEW_ROWS",
            }
            for bucket, bucket_rows in sorted(pooled.items())
        },
    }
    for market, by_bucket in sorted(buckets.items()):
        entry: dict[str, Any] = {}
        for bucket, bucket_rows in sorted(by_bucket.items()):
            predicted = statistics.mean(r.p_central for r in bucket_rows)
            realised = sum(1 for r in bucket_rows if r.won) / len(bucket_rows)
            enough = len(bucket_rows) >= 150
            entry[bucket] = {
                "rows": len(bucket_rows),
                "predicted": round(predicted, 4),
                "realised": round(realised, 4),
                "correction": (
                    round(max(0.0, predicted - realised), 4) if enough else 0.0
                ),
                "status": "MEASURED" if enough else "TOO_FEW_ROWS",
            }
        out[market] = entry
    return out


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


def write_settled(
    rows: list[SettledRow], db_path: Path, drop_event_ids: Iterable[int] = ()
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
        writing = {row.event_id for row in rows}
        stale = sorted(set(drop_event_ids) - writing)
        conn.executemany(
            "DELETE FROM sofa_settled_row "
            "WHERE run_date = 'cache-calibration' AND sofascore_event_id = ?",
            [(event_id,) for event_id in stale],
        )
        for row in rows:
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
) -> dict[str, Any]:
    """Append the player rows to `rows`; the summary's player metrics."""
    carried = sorted(k for k in baselines if is_player_metric(k))
    if carried:
        # SHEET would shrink a player toward these and the replay does not:
        # its rows would describe another model. fit_constants never writes
        # one (_in_baselines); a file that has them was edited by hand.
        return {"player_replay": f"SKIPPED: baselines carry {carried}"}
    started = datetime.now(UTC)
    ladder = printed_player_ladder(runs_dir)
    produced, counts = build_player_rows(
        db_path, ladder, sample_n=config.sample_n, min_sample=config.min_sample
    )
    rows.extend(produced)
    by_market = collections.Counter(r.market for r in produced)
    return {
        "player_replay": "OK" if produced else "NO_ROWS",
        "player_rows": len(produced),
        "player_rows_by_market": dict(sorted(by_market.items())),
        "player_ladder": ladder,
        "player_ladder_unprinted": sorted(set(PLAYER_METRICS) - set(ladder)),
        "player_counts": dict(sorted(counts.items())),
        "player_seconds": round((datetime.now(UTC) - started).total_seconds(), 1),
    }


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
        "--players",
        choices=("include", "skip", "only"),
        default="include",
        help="football player markets beside the team markets (default), "
        "not at all, or alone (the team rows are then neither rebuilt nor "
        "touched)",
    )
    args = parser.parse_args()

    config = SofaConfig.from_env()
    db_path = Path(args.db_path or config.db_path)

    dropped: set[int] = set()
    played: list[Played] = []
    baselines = load_baselines()
    rows: list[SettledRow] = []
    if args.players != "only":
        played = load_cache(db_path, dropped)
        rows = build(played, baselines)
    team_rows = len(rows)

    player_metrics: dict[str, Any] = {"player_replay": "SKIPPED"}
    if args.players != "skip":
        player_metrics = replay_players(
            db_path,
            Path(args.runs_dir or config.runs_dir),
            baselines,
            config,
            rows,
        )

    curve = reliability_curve(rows)
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

    written = write_settled(rows, db_path, dropped)

    measured = sum(
        1
        for market, entry in curve.items()
        if not market.startswith("_")
        for bucket in entry.values()
        if bucket["status"] == "MEASURED"
    )
    overall_predicted = (
        statistics.mean(r.p_central for r in rows) if rows else 0.0
    )
    overall_realised = (
        sum(1 for r in rows if r.won) / len(rows) if rows else 0.0
    )
    # Players asked for and none produced is not a success: a wrong runs dir
    # (no 04_offer.json, so no printed ladder) emptied the player replay with
    # exit 0 and the refit fitted on no player rows (review 2026-10-03).
    players_missing = args.players != "skip" and player_metrics.get(
        "player_replay"
    ) != "OK"
    summary = {
        "stage": "CALIBRATE_FROM_CACHE",
        "verdict": "OK" if rows and not players_missing else "PARTIAL",
        "metrics": {
            "matches_replayed": len(played),
            "settled_rows": len(rows),
            "team_rows": team_rows,
            **player_metrics,
            "markets": len([m for m in curve if not m.startswith("_")]),
            "measured_buckets": measured,
            "overall_predicted": round(overall_predicted, 4),
            "overall_realised": round(overall_realised, 4),
            "overall_overconfidence": round(
                overall_predicted - overall_realised, 4
            ),
            "rows_written_to_db": written,
            "duplicate_listing_ids_dropped": len(dropped),
            "next_step": "python -m scripts.sofa.fit_constants",
        },
        "output_path": args.out,
    }
    print(f"SOFA_SUMMARY: {json.dumps(summary)}", flush=True)
    return 1 if players_missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
