import argparse
import itertools
import json
import logging
import os
import re
import statistics
import sys
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import RootModel
from rapidfuzz import fuzz

from bet.sofa import epochs, sheet_config
from bet.sofa import player_share as psh
from bet.sofa import referees as referee_terms
from bet.sofa import tennis_aces_opponent as aces_opp
from bet.sofa.artifact_guard import incomplete_reason
from bet.sofa.atomic import write_atomic
from bet.sofa.closeness_stretch import CLOSENESS_UNFITTED, ClosenessStretchTable
from bet.sofa.closeness_stretch import load_table as load_closeness_stretch_table
from bet.sofa.closeness_stretch import supremacy as closeness_supremacy
from bet.sofa.confidence import CLASS_WOMEN, WOMEN_COMPETITION_IDS, match_class
from bet.sofa.config import SofaConfig, config_dir, config_path
from bet.sofa.contracts import (
    Fixture,
    FixtureOffer,
    FixtureSamples,
    GapReason,
    Observation,
    PricedRung,
    SheetRow,
    Veto,
)
from bet.sofa.count_dispersion import Dispersion, DispersionTable
from bet.sofa.count_dispersion import load_table as load_dispersion_table
from bet.sofa.count_stretch import COUNT_STRETCH_UNFITTED, CountStretchTable
from bet.sofa.count_stretch import is_total as count_stretch_is_total
from bet.sofa.count_stretch import load_table as load_count_stretch_table
from bet.sofa.coupon import effective_kickoff
from bet.sofa.cup_strength import load as load_cup_strength
from bet.sofa.derived import load_side_correlations, price_derived_rungs
from bet.sofa.engine import (
    MAX_LADDER_SIGMA,
    MAX_SPREAD_RATIO,
    MIN_SPREAD_RATIO,
    P_CEILING,
    P_FLOOR,
    bar_is_unreachable,
    bar_probability,
    calculate_p_low,
    devig,
    get_required_odds,
    ladder_centre,
    ladder_implied_sd,
    outside_model_resolution,
    p_empirical_centred_raw,
    p_empirical_shrunk_to_price,
    sheet_count_p_raw,
    sheet_predictive_sd,
    uses_empirical_frequency,
    winning_boundary,
)
from bet.sofa.epochs import (
    DERIVED_MARGINAL_CENTRES_METRICS,
    STATS_ONLY,
    derived_marginal_centres_enabled,
    tennis_rating_prices,
)
from bet.sofa.epochs import stats_only as stats_only_epoch
from bet.sofa.football_1x2_dnb import (
    DNB_SUBJECT,
    DRAW_NO_BET,
    RESULT_1X2,
    RESULT_SIDES,
)
from bet.sofa.football_1x2_dnb import MARKETS as RESULT_1X2_DNB_MARKETS
from bet.sofa.football_1x2_dnb import note as result_1x2_dnb_note
from bet.sofa.football_1x2_dnb import probabilities as result_1x2_dnb_probabilities
from bet.sofa.football_1x2_dnb import row_p as result_1x2_dnb_row_p
from bet.sofa.football_card_halves import (
    CARD_COUNT_MARKETS as CARD_HALF_COUNT_MARKETS,
)
from bet.sofa.football_card_halves import (
    EVENT_MARKETS as CARD_HALF_EVENT_MARKETS,
)
from bet.sofa.football_card_halves import (
    HALF_OF as CARD_HALF_OF,
)
from bet.sofa.football_card_halves import (
    MARKETS as CARD_HALF_MARKETS,
)
from bet.sofa.football_card_halves import (
    TOTAL_MARKETS as CARD_HALF_TOTAL_MARKETS,
)
from bet.sofa.football_card_halves import (
    UNFITTED_CONSTANTS as CARD_HALF_UNFITTED,
)
from bet.sofa.football_card_halves import (
    CardHalfRates,
    card_half_p,
    card_halves_note,
    side_event_p,
)
from bet.sofa.football_card_halves import (
    load_rates as load_card_half_rates,
)
from bet.sofa.football_incidents import (
    FG_SUBJECTS,
    FIRST_GOAL,
    IncidentPricing,
    first_goal_probs,
    incident_note,
)
from bet.sofa.football_incidents import INCIDENT_MARKETS as FOOTBALL_INCIDENT_MARKETS
from bet.sofa.football_incidents import UNFITTED_CONSTANTS as INCIDENT_UNFITTED
from bet.sofa.football_incidents import load_rates as load_incident_rates
from bet.sofa.football_rating import (
    CROSS_LEAGUE_UNLINKED_NOTE,
    MIN_LEAGUE_MATCHES,
    RATED_SCOPE_MARKETS,
    RATING_UNFITTED,
    UNLINKED,
    VENUE_PRIOR_MARKETS,
    W_FOOTBALL_RATING,
    FootballForecast,
    RatingBook,
)
from bet.sofa.football_rating import load_history as load_football_history
from bet.sofa.football_rating import replay as replay_football
from bet.sofa.football_result import (
    DOUBLE_CHANCE,
    LEFT_OUT,
    ResultConfig,
    dc_note,
    result_probs,
)
from bet.sofa.football_result import UNFITTED_CONSTANTS as RESULT_UNFITTED
from bet.sofa.football_result import load_config as load_result_config
from bet.sofa.football_score_markets import MARKETS as SCORE_MARKETS
from bet.sofa.football_score_markets import note as score_market_note
from bet.sofa.football_score_markets import row_p as score_market_row_p
from bet.sofa.football_score_markets import score_grid
from bet.sofa.football_score_markets import valid_rung as score_market_rung
from bet.sofa.game_state import GAME_STATE_UNFITTED, GameStateTable
from bet.sofa.game_state import load_table as load_game_state_table
from bet.sofa.goals_stretch import (
    GOALS_STRETCH_UNFITTED,
    GoalsStretchTable,
    stretch_supremacy,
)
from bet.sofa.goals_stretch import load_table as load_goals_stretch_table
from bet.sofa.late_resolve import merge_by_event, parse_event_ids
from bet.sofa.market_mapper import (
    derived_base,
    derived_side_metric,
    fold,
    is_derived,
)
from bet.sofa.men_friendly import (
    FriendlyBaseline,
    is_men_friendly_fixture,
    load_men_friendly_baseline,
)
from bet.sofa.names import normalize_name
from bet.sofa.opponent_correction import NOTE as OPPONENT_NOTE
from bet.sofa.opponent_correction import SampleCorrector, correct_total
from bet.sofa.per_market_k import k_for_market
from bet.sofa.player_stretch import PLAYER_STRETCH_UNFITTED, PlayerStretchTable
from bet.sofa.player_stretch import load_table as load_player_stretch_table
from bet.sofa.players import (
    PLAYER_PROPS_V2_METRICS,
    is_player_metric,
    player_sample_key,
)
from bet.sofa.rating_weight import RatingWeightTable
from bet.sofa.rating_weight import blend as rating_blend
from bet.sofa.rating_weight import load_table as load_rating_weight_table
from bet.sofa.rating_weight import weight_for as rating_weight_for
from bet.sofa.referees import (
    REFEREE_UNFITTED,
    RefereeEffectTable,
    RefereeRead,
)
from bet.sofa.sample_age import stalest_side_newest_days
from bet.sofa.samples import FRIENDLY_COMPETITION_IDS
from bet.sofa.season_phase import (
    SEASON_PHASE_UNFITTED,
    SeasonPhaseIndex,
    SeasonPhaseTable,
    index_from_history,
)
from bet.sofa.season_phase import apply as apply_season_phase
from bet.sofa.season_phase import load_table as load_season_phase_table
from bet.sofa.shot_detail import FIT_FILE as SHOT_DETAIL_FIT_FILE
from bet.sofa.shot_detail import METRICS as SHOT_DETAIL_METRICS
from bet.sofa.shot_detail import MIN_STARTS as SHOT_DETAIL_MIN_STARTS
from bet.sofa.shot_detail import WINDOW as SHOT_DETAIL_WINDOW
from bet.sofa.shot_detail import forecast as shot_detail_forecast
from bet.sofa.shot_detail import load_fit as load_shot_detail_fit
from bet.sofa.shot_detail import shrunk_mean as shot_detail_shrunk_mean
from bet.sofa.stage import set_stage
from bet.sofa.supremacy_stretch import stretch_supremacy as side_or_home_supremacy
from bet.sofa.tennis_prior import tier_prior
from bet.sofa.tennis_rating import (
    RATING_PRICED_MARKETS,
    SET_RATING_PRICED_MARKETS,
    W_GAMES_TOTAL_RATING,
    W_TENNIS_RATING,
    MatchForecast,
    TennisRatingModel,
    blend_with_price,
    build_model,
    load_coefficients,
    load_history,
    start_for_rule,
)
from bet.sofa.tennis_sets import (
    SET1_WON_FOR,
    SET_MARKETS,
    SET_SCORE,
    SET_SCORE_NOT,
    complement_note,
    flip,
    score_probs,
    set_note,
    set_win_p,
    split_score_subject,
)
from bet.sofa.tennis_winner import (
    MATCH_WON_FOR,
    RATING_ONLY_MARKETS,
    winner_note,
    winner_p,
)
from bet.sofa.timeutil import frozen_clock_refusal, now

logger = logging.getLogger(__name__)


def deduplicate_observations(
    obs_lists: list[list[Observation]],
) -> list[Observation]:
    """Pool observation buckets, newest first, one match once (L13)."""
    seen: set[int] = set()
    unique: list[Observation] = []
    for obs_list in obs_lists:
        for obs in obs_list:
            if obs.sofascore_event_id not in seen:
                seen.add(obs.sofascore_event_id)
                unique.append(obs)
    # Sort by match_date_utc descending to take the latest N?
    # The plan says "ostatnie 10 zakończonych meczów przed F.kickoff_utc".
    # In E6 it was limited to SOFA_SAMPLE_N. But deduplication might result in more?
    # Wait, the sample was already built taking latest 10. We just union them.
    # We should take the top SOFA_SAMPLE_N by date.
    unique.sort(key=lambda x: x.match_date_utc, reverse=True)
    return unique


def read_file(path: Path) -> bytes:
    if not path.exists():
        print(f"{path} missing", file=sys.stderr)
        sys.exit(2)
    with open(path, "rb") as f:
        return f.read()


def _load_json_config(path: Path) -> dict[str, Any]:
    """T35: a missing or unreadable config degrades to "no correction".

    Not to a crash, and not to a value from somewhere else — an empty dict
    means the engine behaves exactly as documented for an unfitted state.
    """
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("config %s unreadable (%s); continuing without it", path, exc)
        return {}
    return loaded if isinstance(loaded, dict) else {}


def load_baselines(config: SofaConfig) -> dict[str, Any]:
    return _load_json_config(config_path("sofa_league_baselines.json"))


def load_tennis_tier_baselines(config: SofaConfig) -> dict[str, Any]:
    """bet.sofa.tennis_prior; absent until fit_tennis_tier_baselines.py ran.

    SOFA_TENNIS_TIER_BASELINES points a scratch run at a candidate file, so
    one can be exercised end to end without installing it for the real day.
    """
    path = os.environ.get(
        "SOFA_TENNIS_TIER_BASELINES",
        str(config_path("sofa_tennis_tier_baselines.json")),
    )
    loaded = _load_json_config(Path(path))
    metrics = loaded.get("metrics")
    return metrics if isinstance(metrics, dict) else {}


def load_reliability(config: SofaConfig) -> dict[str, Any]:
    return _load_json_config(config_path("sofa_market_reliability.json"))


def load_engine_constants(config: SofaConfig) -> dict[str, Any]:
    return _load_json_config(config_path("sofa_engine_constants.json"))


# Starting values, explicitly NOT fitted. §6.0 forbids carrying `simple`'s
# numbers over; these are the plan's own placeholders and every row priced
# with one says so in `notes`, so an unfitted engine cannot be mistaken for a
# calibrated one (T35: missing config degrades to documented behaviour, it does
# not crash and it does not invent).
# Tennis shrinks its centre toward the bookmaker's ladder, not toward a league
# baseline, because tennis does not have league baselines. `config/
# sofa_league_baselines.json` carries 451 per-competition entries for
# `goals_for` and exactly ONE for `games_won_for` — a single global mean for
# the whole of tennis, ATP to ITF — which is what the comment on
# `read_constant` below already says. The consequence is measurable: over 327
# settled player-fixtures the shrunk centre is indistinguishable from the raw
# sample (corr +0.198 against +0.199, MAE 3.22 against 3.24), while Superbet's
# own ladder is twice as correlated with the realised value:
#
#     centre for games_won_for      corr     MAE
#     raw sample                   +0.199    3.24
#     ours, after K_CENTRE         +0.198    3.22
#     Superbet's ladder            +0.388    2.73
#
#     centre for games_total        corr     MAE
#     ours, after K_CENTRE         +0.118    5.01
#     Superbet's ladder            +0.354    4.31
#
# This is the same defect as K_DERIVED_CENTRE in derived.py and it is fixed
# the same way. Fitted on 535 settled tennis marginal rows carrying a ladder,
# errors scaled per market so one market's units cannot dominate: the curve is
# flat from K=15 to K=100 (0.9515 -> 0.9514) with a minimum of 0.9483 at
# K=32.5, against 1.0097 for today's behaviour. Leave-one-day-out improves the
# held-out day every time (0.8154/0.9536, 1.0057/1.0515, 0.9996/1.0262) but
# refits K at 17.5, 32.5 and 117.5 — a much wider spread than the handicap
# fit, so 30.0 is chosen as the middle of the flat region and because it is
# the value derived.py already uses, not because the data pins it.
#
# Football is NOT in scope. Football is already well calibrated — across
# 10 buckets and 4,457-12,449 rows each, its largest deviation between claimed
# and realised probability is 0.027 — and it has real per-competition
# baselines to shrink to. Tennis is flat over the same range: it claims 0.05
# and realises 0.207, claims 0.95 and realises 0.724.
K_TENNIS_LADDER_CENTRE = 30.0

UNFITTED_K_CENTRE = 10.0
UNFITTED_K_PRICE = 10.0


def read_constant(
    engine_constants: dict[str, Any], name: str, fallback: float, sport: str = ""
) -> tuple[float, bool]:
    """Return (value, was_fitted). A null or missing entry is NOT fitted.

    A constant may be fitted per sport, and K_CENTRE has to be: it weighs the
    league prior against the sample, and the priors are not comparable between
    the two sports. Football carries 419 per-competition baselines; tennis
    carries one global mean for the whole of tennis, ATP to ITF. Fitted on the
    pooled history — 98% of which is football — K_CENTRE came out 25, and on
    tennis alone 25 scores a Brier of 0.2049 against 0.1887 at K = 2 (F46).
    One number was quietly asking a UTR PTT group match to be two-thirds
    "the average tennis match".
    """
    entry = engine_constants.get(name)
    if isinstance(entry, dict):
        by_sport = entry.get("by_sport")
        if sport and isinstance(by_sport, dict):
            value = by_sport.get(sport)
            if isinstance(value, int | float) and not isinstance(value, bool):
                return float(value), True
        value = entry.get("value")
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value), True
        return fallback, False
    if isinstance(entry, int | float) and not isinstance(entry, bool):
        return float(entry), True
    return fallback, False


def row_correction(
    reliability: dict[str, Any],
    market: str,
    p: float,
    direction: str,
    price_anchored: bool,
) -> float:
    """The reliability correction for one row, or 0 for a p already on the
    price (see the measurement where it is called)."""
    if price_anchored:
        return 0.0
    return get_calibration_correction(reliability, market, p, direction)


def get_calibration_correction(
    reliability: dict[str, Any], market: str, p: float, direction: str = ""
) -> float:
    """§6.5 step 2. The market's own measured curve, else the pooled one.

    A market with too few settled rows of its own used to get a correction of
    exactly zero, which is not the neutral choice it looks like: it asserts
    the estimator is calibrated for that market while the pooled measurement
    says it is not. The overconfidence being corrected is mostly a property of
    the estimator — a normal approximation over ten observations — so the
    pooled curve is the better fallback, and `_pooled` exists for that.
    """
    bucket_index = min(9, int(p * 10))
    bucket = f"{bucket_index / 10.0:.1f}-{(bucket_index + 1) / 10.0:.1f}"

    bucket_entry: Any = None
    # Most specific first: this market, this direction (F48). OVER and UNDER
    # are exact complements, so a bias toward one cancels exactly when the two
    # are pooled — the pooled curve cannot see it, and on tennis it is worth
    # 20-40% relative.
    keys = [f"{market}|{direction}", market] if direction else [market]
    for key in keys:
        market_entry = reliability.get(key)
        if isinstance(market_entry, dict):
            candidate = market_entry.get(bucket)
            if isinstance(candidate, dict) and candidate.get("status") == "MEASURED":
                bucket_entry = candidate
                break

    if bucket_entry is None:
        pooled = reliability.get("_pooled")
        if isinstance(pooled, dict):
            candidate = pooled.get(bucket)
            if isinstance(candidate, dict) and candidate.get("status") == "MEASURED":
                bucket_entry = candidate

    if not isinstance(bucket_entry, dict):
        return 0.0

    correction = bucket_entry.get("correction", 0.0)
    if not isinstance(correction, int | float) or isinstance(correction, bool):
        return 0.0
    # The engine clamps this to >= 0 as well; doing it here too means a hand-
    # edited config cannot turn a bar-raiser into a discount at either end.
    return max(0.0, float(correction))


def get_prior(
    baselines: dict[str, Any], metric: str, competition_id: int
) -> float | None:
    """League baseline for this metric, keyed on uniqueTournament.id (L11).

    A league-blind prior measured 0.821 against a pinned global 1.243 in the
    Argentine Liga Profesional — the difference decided that day's only bet.
    """
    metric_entry = baselines.get(metric)
    if not isinstance(metric_entry, dict):
        return None

    league_entry = metric_entry.get(str(competition_id))
    if isinstance(league_entry, dict) and isinstance(
        league_entry.get("mean"), int | float
    ):
        return float(league_entry["mean"])

    # The pool carries its own `n` since 2026-09-21, so it reads like a league
    # entry. The bare-float shape is what every baselines file written before
    # that date holds, and one of those is still on disk in any checkout that
    # has not re-fitted — reading only the new shape would silently drop every
    # prior rather than fix one.
    global_entry = metric_entry.get("global")
    if isinstance(global_entry, dict) and isinstance(
        global_entry.get("mean"), int | float
    ):
        return float(global_entry["mean"])
    if isinstance(global_entry, int | float) and not isinstance(global_entry, bool):
        return float(global_entry)
    return None


# The same evidence bar fit_constants.py holds a league entry to
# (MIN_BASELINE_OBSERVATIONS); a test pins the two together.
MIN_DAY_LEAGUE_OBSERVATIONS = 30

# metric -> competition id -> (match id, owner) -> value
DayLeagueObservations = dict[str, dict[str, dict[tuple[int, str], float]]]


def _is_half_metric(metric: str) -> bool:
    return "_1h_" in metric or "_2h_" in metric


def day_league_observations(
    fixtures: list[Fixture], samples: list[FixtureSamples]
) -> DayLeagueObservations:
    """Every league match already in the day's sample, per metric and league.

    `config/sofa_league_baselines.json` only carries a league once SETTLE has
    graded thirty of its rows, so a league new to the board was shrunk toward
    the *global* pool - every league on earth, youth and women's blowouts
    included. On 2026-09-23 that put Gaucho Serie A2 at 3.29 goals a match
    while the 72 Gaucho A2 matches in that day's own 03_samples.json averaged
    2.10, Superbet's ladders sat at 2.08-2.10, and both staked OVER 1.5 legs
    existed only because of the gap. The day already held the league's
    history; this collects it.

    Football only: a tennis tournament id is one week of one event, and tennis
    shrinks toward the ladder, not a league. Half-match metrics are left out:
    Sofascore's period split can be wrong while the full-time total is right -
    Nigeria's NPFL put every goal of Kano Pillars 3-2 Niger Tornadoes (2-0 at
    the break) in the second half, which sums correctly and so passes the
    period1 + period2 == normaltime check - and a prior built on it moved all
    24 of that day's goals_2h_total rows away from the price.

    Match totals are keyed by match; a per-side metric by (match, the team the
    history belongs to), so two teams' counts in one match are two
    observations of "a team's count in this league".
    """
    fixture_by_id = {f.sofascore_event_id: f for f in fixtures}
    out: DayLeagueObservations = {}
    for fs in samples:
        fx = fixture_by_id.get(fs.sofascore_event_id)
        if fx is None or fx.sport != "football":
            continue
        for metric, ms in fs.metrics.items():
            if _is_half_metric(metric):
                continue
            if metric.endswith("_total"):
                lists = [("", ms.side_a), ("", ms.side_b), ("", ms.h2h)]
            elif "_for" in metric:
                lists = [(f"{fs.sofascore_event_id}:a", ms.side_a),
                         (f"{fs.sofascore_event_id}:b", ms.side_b)]
            else:
                continue
            per_comp = out.setdefault(metric, {})
            for owner, obs_list in lists:
                for o in obs_list:
                    if o.competition_id is None:
                        continue
                    per_comp.setdefault(str(o.competition_id), {})[
                        (o.sofascore_event_id, owner)] = o.value
    return out


def day_league_prior(
    day_obs: DayLeagueObservations,
    metric: str,
    competition_id: int | None,
    exclude_events: set[int],
) -> tuple[float, int] | None:
    """The league's day mean over matches that are NOT this fixture's sample.

    Leaving the fixture's own matches out keeps the prior an independent
    number: in Goiano Acesso on 2026-09-23 half the pool was the priced
    match's own sample, which then counted twice - once as the sample and
    once as the target it shrinks toward.
    """
    if competition_id is None:
        return None
    pool = day_obs.get(metric, {}).get(str(competition_id), {})
    values = [v for (eid, _), v in pool.items() if eid not in exclude_events]
    if len(values) < MIN_DAY_LEAGUE_OBSERVATIONS:
        return None
    return statistics.mean(values), len(values)


# Never a side's league for the prior: friendlies (samples.FRIENDLY_COMPETITION_IDS)
# and International Friendly Games (851), the modal competition of most national
# teams - a Gulf Cup or CONCACAF Nations League tie shrank toward it (2026-10-03).
# 851 is on the friendly list itself since 2026-10-04; named here as well so
# the prior rule does not depend on that list.
NOT_A_LEAGUE: frozenset[int] = FRIENDLY_COMPETITION_IDS | {851}


def home_competition(
    observations: list[Observation], league: int | None = None
) -> int | None:
    """The competition a side actually plays in: the one holding most of its
    sample, and at least half of it. None when the sample has no majority.

    `league` is the side's league from the football rating (its modal
    competition over the last year, RatingBook.domain). It wins over the
    sample's majority when the sample holds at least half as many matches of
    it as of the majority: a short sample in an early-season cup run is mostly
    cup. On 2026-10-03 every Scottish League One / Two fixture (207, 209) took
    its prior from the Challenge Cup (331), which held 4 of Annan Athletic's 6
    corners matches against 2 in League Two. One match in ten does not win: a
    promoted side's rated league is last season's (Cymru North 13820 took
    Cymru Premier 254 from 1 of 10 under a looser rule the same day). The
    Challenge Cup is itself the modal competition of 8 teams (B sides), so
    "is it anyone's league" cannot tell it from a league.
    """
    comps = [o.competition_id for o in observations if o.competition_id is not None]
    if not comps:
        return None
    counts = Counter(comps)
    comp, count = counts.most_common(1)[0]
    if (
        league is not None
        and league not in NOT_A_LEAGUE
        and counts.get(league, 0) * 2 >= count
    ):
        return league
    return comp if count * 2 >= len(observations) else None


def _fitted_league_mean(
    baselines: dict[str, Any], metric: str, competition_id: int
) -> float | None:
    entry = (baselines.get(metric) or {}).get(str(competition_id))
    if isinstance(entry, dict) and isinstance(entry.get("mean"), int | float):
        return float(entry["mean"])
    return None


def rated_leagues(
    football: FootballForecast | None, teams: list[int]
) -> list[int | None] | None:
    """Each team's league per the football rating (its modal competition
    over the last year), or None without a rating."""
    if football is None:
        return None
    book = football.book
    out: list[int | None] = []
    for team in teams:
        unit = book.domain(team)
        out.append(None if unit is None else book.unit_competition(unit))
    return out


def resolve_prior(
    baselines: dict[str, Any],
    day_obs: DayLeagueObservations,
    metric: str,
    fixture: Fixture,
    own_sides: list[list[Observation]],
    own_events: set[int],
    side_leagues: list[int | None] | None = None,
) -> tuple[float | None, str | None]:
    """The shrink target for one row, and a note saying where it came from.

    In order: the fitted league entry; the league measured on the day's
    sample; the leagues the sides actually play in; the global pool. The third
    exists for cups: KNVB beker and Copa Uruguay carry their own competition
    id, so both staked cup legs of 2026-09-23 were shrunk toward the global
    pool while the teams' own leagues were measured on the same page.
    """
    comp = fixture.competition_id
    fitted = _fitted_league_mean(baselines, metric, comp)
    if fitted is not None:
        return fitted, None
    day = day_league_prior(day_obs, metric, comp, own_events)
    if day is not None:
        mean, n = day
        return mean, (f"PRIOR_FROM_DAY_SAMPLES: competition {comp} mean {mean:.4g} "
                      f"over {n} matches in this day's samples, this match's own "
                      "sample excluded (no fitted league baseline)")
    parts: list[str] = []
    means: list[float] = []
    for i, side in enumerate(own_sides):
        home = home_competition(
            side, side_leagues[i] if side_leagues is not None else None)
        if home is None or home == comp:
            continue
        league = _fitted_league_mean(baselines, metric, home)
        source = "fitted"
        if league is None:
            measured = day_league_prior(day_obs, metric, home, own_events)
            league, source = (measured[0], f"day n={measured[1]}") if measured else (
                None, "")
        if league is not None:
            means.append(league)
            parts.append(f"{home}={league:.4g} ({source})")
    if means and len(means) == len(own_sides):
        prior = statistics.mean(means)
        return prior, (f"PRIOR_FROM_TEAMS_LEAGUES: competition {comp} has no "
                       f"baseline; the sides' own leagues {', '.join(parts)} "
                       f"-> {prior:.4g}")
    women = women_global_prior(baselines, metric, fixture)
    if women is not None:
        return women
    pooled = get_prior(baselines, metric, comp)
    return pooled, global_prior_note(baselines, metric, comp, pooled)


# A women's league with no baseline of its own shrinks to the women's pool.
MIN_WOMEN_POOL_N = 300


def is_womens_fixture(fixture: Fixture) -> bool:
    """confidence.match_class - the one reading of "women's football" SHEET
    and CONFIDENCE share (SHEET has no board names; CONFIDENCE adds them)."""
    return match_class(fixture.sport, fixture.competition_name, None,
                       fixture.competition_id) == CLASS_WOMEN


def women_global_prior(
    baselines: dict[str, Any], metric: str, fixture: Fixture,
    women_ids: frozenset[int] | None = None,
) -> tuple[float, str] | None:
    """The women's global pool for a women's fixture with no league baseline.

    The global pool is ~90% men's football. Measured on the fitted baselines
    2026-09-30, women's leagues against the global pool: goals_total 3.57 vs
    3.17, cards_points_total 2.59 vs 4.45, fouls_total 17.8 vs 24.9 - and a
    league with no baseline is shrunk toward the pool at weight 0.71 at n=10.
    """
    if not is_womens_fixture(fixture):
        return None
    if _fitted_league_mean(baselines, metric, fixture.competition_id) is not None:
        return None
    ids = WOMEN_COMPETITION_IDS if women_ids is None else women_ids
    entry = baselines.get(metric)
    if not isinstance(entry, dict):
        return None
    total_n, total = 0, 0.0
    for key, league in entry.items():
        if not key.isdigit() or int(key) not in ids or not isinstance(league, dict):
            continue
        mean, n = league.get("mean"), league.get("n")
        if isinstance(mean, int | float) and isinstance(n, int) and n > 0:
            total_n += n
            total += float(mean) * n
    if total_n < MIN_WOMEN_POOL_N:
        return None
    prior = total / total_n
    return prior, (f"PRIOR_GLOBAL_WOMEN: competition {fixture.competition_id} has "
                   f"no {metric} baseline; the women's leagues' pool "
                   f"{prior:.4g} (n={total_n}) stands in for the global one")


def global_prior_note(
    baselines: dict[str, Any],
    metric: str,
    competition_id: int,
    prior: float | None,
) -> str | None:
    """Say so when a row is shrunk toward the global pool, or toward nothing.

    Every other prior source leaves a note; this one did not, so a row pulled
    toward the world average read exactly like one pulled toward its own
    league. 5 of the 17 football singles on the 2026-09-25 PDF were priced this
    way and nothing on them said it.
    """
    if _fitted_league_mean(baselines, metric, competition_id) is not None:
        return None
    if prior is None:
        return (f"NO_PRIOR: no baseline for {metric} in competition "
                f"{competition_id} or globally; centre is the sample's own")
    entry = (baselines.get(metric) or {}).get("global")
    n = entry.get("n") if isinstance(entry, dict) else None
    return (f"PRIOR_GLOBAL: competition {competition_id} has no fitted baseline "
            f"and too few day-sample matches; shrunk toward the global "
            f"{metric} mean {prior:.4g}" + (f" (n={n})" if n else ""))


# A per-side market must be attributed to a side we can actually name. Below
# this ratio, or on a tie, we do not know which side it is.
SIDE_MATCH_THRESHOLD = 70.0
SIDE_MATCH_MARGIN = 10.0

# A leading market scope, folded: "1.polowa", "2. polowa". These describe which
# part of the match the line covers, not who it is about.
_SCOPE_PREFIX = re.compile(r"^[12]\.\s?polowa\b")


# A tennis player's name the token sort could not place. Superbet and
# Sofascore disagree on middle names ("tai sach" / "Tai Leonard Sach",
# "rafael alfonso de alba valdes" / "Rafael de Alba"), initials ("d.nicolae
# madaras"), compounds ("heerae im" / "Im Hee Rae") and spelling ("Oyinlomo" /
# "Qyinlomo"): six per-player ladders lost on 2026-09-30. A side is taken only
# when it reads clearly as the player AND the other side clearly does not -
# both of a match's names are on the fixture, so two plausible answers stay
# no answer.
TENNIS_FALLBACK_MATCH = 90.0
TENNIS_FALLBACK_OTHER_MAX = 50.0


def _name_tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[\s.\-]+", name) if t]


def _tennis_name_score(subject: str, side: str) -> float:
    sub, sid = _name_tokens(subject), _name_tokens(side)
    if not sub or not sid:
        return 0.0
    # compounds: the same letters in some order of whole tokens
    if len(sid) <= 4 and any(
        "".join(perm) == "".join(sub) for perm in itertools.permutations(sid)
    ):
        return 100.0
    # an initial stands for a token of the other name
    full = [t for t in sub if len(t) > 1]
    initials = [t for t in sub if len(t) == 1]
    if initials and full and all(any(s.startswith(i) for s in sid) for i in initials):
        sub = full
    return float(
        max(
            fuzz.token_set_ratio(" ".join(sub), " ".join(sid)),
            fuzz.token_sort_ratio(" ".join(sub), " ".join(sid)),
        )
    )


def _tennis_name_fallback(subject_norm: str, fixture: Fixture) -> str | None:
    home = _tennis_name_score(subject_norm, normalize_name(fixture.home_name))
    away = _tennis_name_score(subject_norm, normalize_name(fixture.away_name))
    if home >= TENNIS_FALLBACK_MATCH and away < TENNIS_FALLBACK_OTHER_MAX:
        return "side_a"
    if away >= TENNIS_FALLBACK_MATCH and home < TENNIS_FALLBACK_OTHER_MAX:
        return "side_b"
    return None


def _core_name(name: str) -> str:
    """A normalised club name without its generic words and short affixes
    ("ca", "fc", "club", "atletico", ...); the name itself when nothing else
    is left."""
    from bet.sofa.resolve import _GENERIC_NAME_TOKENS

    core = [w for w in name.split() if len(w) > 3 and w not in _GENERIC_NAME_TOKENS]
    return " ".join(core) if core else name


def determine_side(subject: str, fixture: Fixture) -> str | None:
    """Which side a per-participant market belongs to, or None if unclear.

    Returning None rather than defaulting to the home side is the point: a
    subject that matches nothing would otherwise land quietly on side_a and be
    priced against the wrong team's sample.
    """
    # A subject that still carries a market scope is not a team name, whatever
    # it scores. "1.połowa - Hapoel Tel Aviv" reached 73.2 against a threshold
    # of 70 purely because the long team name diluted the prefix — 678 of 1160
    # side/half combinations leaked this way, and whether a row leaked depended
    # on how long the club's name was. F29's fold() fixes this at the source by
    # classifying the market as half-time; this is the last line of defence,
    # and it has to hold for the scopes that have no metric of their own
    # (half-time cards, half-time corners), which still arrive here (F29b).
    if _SCOPE_PREFIX.match(fold(subject)):
        return None

    subject_norm = normalize_name(subject)
    home_norm = normalize_name(fixture.home_name)
    away_norm = normalize_name(fixture.away_name)
    # The club's own name first: a generic word or a short affix shared with
    # the OTHER side can outscore it. 2026-10-17: "ca platense" scored 73.7
    # against "CA Lanús" and 60.6 against "Club Atlético Platense", so every
    # Platense row was priced on Lanús (verifier). On the core tokens it is
    # 100 / 0. Measured over 5,985 football subject-fixture pairs of
    # 10-12..10-17: 2 change, both to the right side (this one, and "annecy"
    # against "Annecy FC", unmatched before); when the core decides nothing
    # the full names decide as before.
    # Clubs only: a tennis player's short surname ("Li", "Wu") is the name.
    if fixture.sport != "tennis":
        core_home = fuzz.token_sort_ratio(
            _core_name(subject_norm), _core_name(home_norm))
        core_away = fuzz.token_sort_ratio(
            _core_name(subject_norm), _core_name(away_norm))
        if (max(core_home, core_away) >= SIDE_MATCH_THRESHOLD
                and abs(core_home - core_away) >= SIDE_MATCH_MARGIN):
            return "side_a" if core_home > core_away else "side_b"
    home_score = fuzz.token_sort_ratio(subject_norm, home_norm)
    away_score = fuzz.token_sort_ratio(subject_norm, away_norm)

    best = max(home_score, away_score)
    if best < SIDE_MATCH_THRESHOLD:
        if fixture.sport == "tennis":
            return _tennis_name_fallback(subject_norm, fixture)
        return None
    if abs(home_score - away_score) < SIDE_MATCH_MARGIN:
        # Two (nearly) equally good answers is not an answer. Exact equality
        # used to be the test, so "martinez" against Pedro and Juan Martinez
        # went to whichever name was shorter. Measured 2026-10-01 over three
        # days of offers: 0 of 1,557 matched subjects sit within the margin.
        return None
    return "side_a" if home_score > away_score else "side_b"


def strip_in_play_prices(
    offer: FixtureOffer, fixture: Fixture
) -> tuple[FixtureOffer, set[tuple[str, str, float]]]:
    """Drop the odds of every rung fetched at or after the fixture's kickoff.

    A filtered OFFER refresh carries forward the previous file's rungs for
    fixtures it skipped as started, and some of those were fetched after the
    start: on 2026-09-23 Taro Daniel UNDER 12.5 sat at 50.0, fetched 05:49Z on
    a 04:00Z match. Once a tennis row is priced mostly FROM the price
    (p_empirical_shrunk_to_price), an in-play price is not just a bad bar, it
    is the number itself - and it flows into SETTLE's population and every fit
    after it. The rung keeps its row, as NO_PRICE, so the day still settles.
    The earliest clock decides, as at every other kickoff gate: the two
    RESOLVE froze, Superbet's start time as the fetch saw it
    (FixtureOffer.superbet_kickoff_seen_utc), and the moment a fetch found
    Superbet reporting the match under way (superbet_started_utc).
    """
    kickoff = effective_kickoff(fixture)
    for later_signal in (offer.superbet_started_utc, offer.superbet_kickoff_seen_utc):
        if later_signal is not None:
            kickoff = min(kickoff, later_signal)
    kept: list[PricedRung] = []
    stripped: set[tuple[str, str, float]] = set()
    for r in offer.rungs:
        if r.fetched_at_utc >= kickoff and (
            r.over_odds is not None or r.under_odds is not None
        ):
            kept.append(r.model_copy(update={"over_odds": None, "under_odds": None}))
            stripped.add((r.market, r.subject, r.line))
        else:
            kept.append(r)
    if not stripped:
        return offer, stripped
    return offer.model_copy(update={"rungs": kept}), stripped


def rating_note(
    rating: MatchForecast, side: str | None, p_rating: float,
    market_p: float | None, *, rule: str | None = None,
) -> str:
    """The TENNIS_RATING note. `market_p` is the price the rating was
    actually blended with (tennis_rating.blend_with_price), None when
    p_central is the rating alone; `rule` names the stats-only switch under
    which the rating alone prices the row (the price never enters there)."""
    who = "home" if side in (None, "side_a") else "away"
    p = rating.p_side_wins(side or "side_a")
    # the old-rule wording (a blended row, an unpriced rung) stays byte for
    # byte: the old-epoch sheets carry it
    if market_p is not None:
        blend = (f"blended {W_TENNIS_RATING:g} with market_p {market_p:.4f} "
                 "(W_TENNIS_RATING)")
    elif rule is not None:
        blend = f"p_central is the rating alone, no price ({rule})"
    else:
        blend = "no price on this rung, rating alone (W_TENNIS_RATING)"
    return (
        f"TENNIS_RATING: rating p {p_rating:.4f}, {blend}; "
        f"{who} wins the match {p:.3f}, "
        f"{len(rating.neighbours_home)} nearest historical matches, "
        f"rated matches {rating.rated_home}/{rating.rated_away}"
    )


def load_tennis_rating(
    config: SofaConfig, fixtures: list[Fixture], run_date: str,
    scoped: bool = False,
) -> TennisRatingModel | None:
    """The rating model for this day, or None when there is no tennis or no
    fitted calibration. Ratings run over history strictly before the day."""
    if not any(f.sport == "tennis" for f in fixtures):
        return None
    loaded = load_coefficients()
    if loaded is None:
        logger.warning("sheet: config/tennis_rating.json absent, tennis unrated")
        return None
    coefficients, meta = loaded
    cut = datetime.strptime(run_date, "%Y-%m-%d").replace(tzinfo=UTC)
    # epochs.TENNIS_RATING_SCORE_WINNER (audit 2026-10-23 P14): the day being
    # built and the build clock. Off: the one-argument call, as before.
    if epochs.tennis_rating_score_winner(run_date):
        history = load_history(config.db_path, score_winner=True)
    else:
        history = load_history(config.db_path)
    if not scoped:
        return build_model(
            history, coefficients, int(cut.timestamp()), names=meta["features"],
            tier_start=start_for_rule(
                meta["features"], meta.get("tier_start"), False),
        )
    # epochs.TENNIS_SCOPED_TABLE: the table cut by tier x gender and, when the
    # config was fitted with it, the tier-initialised start (V5)
    return build_model(
        history, coefficients, int(cut.timestamp()), names=meta["features"],
        scoped=True, tier_start=meta.get("tier_start"),
    )


def sample_centre(
    *,
    fixture: Fixture,
    market: str,
    subject: str,
    n: int,
    mean: float,
    own_sides: list[list[Observation]],
    own_events: set[int],
    own_teams: list[int],
    baselines: dict[str, Any],
    day_obs: DayLeagueObservations | None,
    football: FootballForecast | None,
    tennis_tiers: dict[str, Any] | None,
    engine_constants: dict[str, Any],
    k_centre: float,
    per_market_k_on: bool,
    side: str | None = None,
    rating_weights: RatingWeightTable | None = None,
    men_friendly_baseline: FriendlyBaseline | None = None,
) -> tuple[float, list[str], list[str], tuple[float, str] | None]:
    """SHEET's centre of one marginal row (6.2), outside the tennis ladder
    path: the prior (tennis tier, the day's league / teams' leagues, women's
    pool, the global baseline), the K_CENTRE shrink toward it, then the
    football rating at W_FOOTBALL_RATING. Returns (centre, notes, unfitted
    constants added, the rating's (centre, note) or None). `side` names the
    rating's side directly ("side_a" / "side_b"); None reads it off `subject`
    as the marginal row does.

    One formula for the marginal row and, from epochs.DERIVED_SHEET_MARGINS,
    for a derived joint's side whose own ladder Superbet does not quote
    (audit 2026-10-13 B3) - so the two can never drift apart.

    `men_friendly_baseline` (epochs.MEN_FRIENDLY_BASELINE, bet.sofa.
    men_friendly): an 851 fixture's goals_total / goals_for prior is the
    as-of men's friendly mean instead of the chain below. None: as before."""
    notes: list[str] = []
    unfitted_add: list[str] = []
    rated: tuple[float, str] | None = None
    # A tennis rung with no ladder - most of them - used to fall into
    # the football lookup below, keyed on a competition id that is one
    # week of one tournament, so it always reached the global pool or
    # nothing. See bet.sofa.tennis_prior (measured metrics only).
    tier = (
        tier_prior(tennis_tiers, market, fixture.category_name,
                   fixture.ground_type)
        # Fitted on best-of-three only, like the rating; a best-of-
        # five pulled toward it would lose ~15 games of centre.
        if fixture.sport == "tennis" and tennis_tiers
        and fixture.default_period_count in (None, 3)
        else None
    )
    friendly = (
        men_friendly_baseline.prior(market)
        if men_friendly_baseline is not None
        and is_men_friendly_fixture(fixture.sport, fixture.competition_id)
        else None
    )
    prior: float | None
    prior_note: str | None
    if tier is not None:
        prior, prior_note = tier
        notes.append(prior_note)
    elif friendly is not None:
        prior, prior_note = friendly
        notes.append(prior_note)
    elif day_obs is not None and own_sides:
        prior, prior_note = resolve_prior(
            baselines, day_obs, market, fixture, own_sides, own_events,
            rated_leagues(football, own_teams)
            if len(own_teams) == len(own_sides) else None)
        if prior_note:
            notes.append(prior_note)
    elif (women := women_global_prior(
            baselines, market, fixture)) is not None:
        prior, prior_note = women
        notes.append(prior_note)
    else:
        prior = get_prior(baselines, market, fixture.competition_id)
        prior_note = global_prior_note(
            baselines, market, fixture.competition_id, prior)
        if prior_note:
            notes.append(prior_note)
    if prior_note and prior_note.startswith("PRIOR_GLOBAL_WOMEN"):
        unfitted_add.append("MIN_WOMEN_POOL_N")
    if prior is not None:
        # epochs.PER_MARKET_K: the football market's own K, else the
        # sport's (off: k_centre, byte for byte)
        k_row = (
            k_for_market(
                engine_constants, fixture.sport, market, k_centre)
            if per_market_k_on else k_centre
        )
        w_c = n / (n + k_row)  # K_CENTRE
        centre = w_c * mean + (1 - w_c) * prior
    else:
        centre = mean
    # The opponent-adjusted rating replaces the sample's centre where
    # it has one (bet.sofa.football_rating). The spread stays the
    # sample's.
    rated = (
        football.centre(
            market,
            side if side is not None
            else determine_side(subject, fixture) if subject else None,
        )
        if football is not None and not is_player_metric(market)
        else None
    )
    if rated is not None:
        own_centre = centre
        if rating_weights is None:
            centre = W_FOOTBALL_RATING * rated[0] + (
                1 - W_FOOTBALL_RATING) * own_centre
            w_note = f"W_FOOTBALL_RATING={W_FOOTBALL_RATING:g}"
        else:
            # epochs.FOOTBALL_RATING_WEIGHT (audit 2026-10-13 B14)
            centre = rating_blend(rated[0], own_centre, market, rating_weights)
            w_m = rating_weight_for(market, rating_weights)
            w_note = (f"W={w_m:g} "
                      + ("(market's own, epochs.FOOTBALL_RATING_WEIGHT)"
                         if rating_weights.weight(market) is not None
                         else "(W_FOOTBALL_RATING)"))
        unfitted_add.append("W_FOOTBALL_RATING")
        unfitted_add.extend(RATING_UNFITTED)
        notes.append(
            f"FOOTBALL_RATING: centre {centre:.2f} from the rating "
            f"({rated[1]}) at {w_note}, "
            f"sample centre was {own_centre:.2f}"
        )
    elif (football is not None and not is_player_metric(market)
          and football.no_league_rate(market)):
        notes.append(
            f"NO_LEAGUE_RATE: competition {fixture.competition_id} has "
            f"fewer than {MIN_LEAGUE_MATCHES} rated matches; centre "
            "from the sample alone (epochs.FOOTBALL_LEAGUE_RATE_RULE)")
    return centre, notes, unfitted_add, rated


def tennis_aces_correction(
    fixture: Fixture,
    samples: FixtureSamples,
    market: str,
    side: str | None,
    tennis_tiers: dict[str, Any] | None,
    k: float,
) -> tuple[float | None, str]:
    """epochs.TENNIS_ACES_OPPONENT: the multiplier of one aces row's centre
    and the row's note (bet.sofa.tennis_aces_opponent). The returner's
    conceded aces are his full-match `aces_for` sample's `against` (SAMPLES
    scopes it like his own), the prior the fixture's full-match aces tier
    prior - the one sample_centre shrinks aces_for toward, best of three only
    - and K the tennis K_CENTRE. (None, why) where no correction applies."""
    tier = (
        tier_prior(tennis_tiers, aces_opp.PRIOR_MARKET, fixture.category_name,
                   fixture.ground_type)
        if tennis_tiers and fixture.default_period_count in (None, 3) else None
    )
    if tier is None:
        return None, (f"{aces_opp.NOTE}: no correction (no full-match aces "
                      "tier prior for this fixture)")
    prior = tier[0]
    full = samples.metrics.get(aces_opp.PRIOR_MARKET)
    if full is None:
        return None, f"{aces_opp.NOTE}: no correction (no aces_for sample)"

    def conceded(obs: list[Observation]) -> list[float]:
        return [float(o.against) for o in obs if o.against is not None]

    def own(obs: list[Observation]) -> list[float]:
        return [o.value for o in obs]

    f_a = aces_opp.returner_factor(conceded(full.side_a), prior, k)
    f_b = aces_opp.returner_factor(conceded(full.side_b), prior, k)
    if market in aces_opp.ACES_SIDE_MARKETS:
        if side not in ("side_a", "side_b"):
            return None, f"{aces_opp.NOTE}: no correction (side unknown)"
        factor = f_b if side == "side_a" else f_a
        if factor is None:
            return None, (f"{aces_opp.NOTE}: no correction (the returner has "
                          f"< {aces_opp.MIN_RETURNER_VALUES} conceded values)")
        return factor, (f"returner factor {factor:.3f} over prior "
                        f"{prior:.2f}, K {k:g}")
    if f_a is None or f_b is None or not full.side_a or not full.side_b:
        return None, (f"{aces_opp.NOTE}: no correction (a returner has < "
                      f"{aces_opp.MIN_RETURNER_VALUES} conceded values)")
    c_a = aces_opp.shrunk(own(full.side_a), prior, k)
    c_b = aces_opp.shrunk(own(full.side_b), prior, k)
    mult = aces_opp.total_multiplier(c_a, c_b, f_a, f_b)
    return mult, (f"sides {c_a:.2f} x f {f_b:.3f} + {c_b:.2f} x f {f_a:.3f} "
                  f"over {c_a + c_b:.2f}, K {k:g}")


def sheet_derived_margins(
    fixture: Fixture,
    samples: FixtureSamples,
    offer: FixtureOffer,
    marginal_centres: dict[tuple[str, str], float],
    *,
    baselines: dict[str, Any],
    day_obs: DayLeagueObservations | None,
    football: FootballForecast | None,
    engine_constants: dict[str, Any],
    k_centre: float,
    per_market_k_on: bool,
    min_sample: int,
    rating_weights: RatingWeightTable | None = None,
    men_friendly_baseline: FriendlyBaseline | None = None,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """epochs.DERIVED_SHEET_MARGINS (audit 2026-10-13 B3). Fills, IN PLACE,
    `marginal_centres` for every side of a football joint's metric
    (DERIVED_MARGINAL_CENTRES_METRICS) that has no marginal row - Superbet
    quoted no ladder for that side - with the centre the marginal row would
    have had (sample_centre: prior, K_CENTRE shrink, W_FOOTBALL_RATING x the
    rating), instead of letting the joint fall back to both raw samples. A
    side SHEET would not price (thin, all zero) stays without one, as before.

    Returns (side metric -> notes, side metric -> unfitted constants) for the
    derived rows: the filled sides, and CROSS_LEAGUE_UNLINKED for every
    football joint whose metric the rating cannot link - CONFIDENCE refuses
    those rows as it refuses the marginal rows of that fixture."""
    notes: dict[str, list[str]] = {}
    unfitted: dict[str, list[str]] = {}
    side_metrics = sorted({
        derived_side_metric(base)
        for rung in offer.rungs
        if is_derived(rung.market)
        and (base := derived_base(rung.market)) is not None
    })
    for side_metric in side_metrics:
        if football is not None and (
            football.link_status(side_metric) or football.fixture_link()
        ) == UNLINKED:
            notes.setdefault(side_metric, []).append(
                f"{CROSS_LEAGUE_UNLINKED_NOTE}: the two sides share no league "
                "and their leagues' strengths are unmeasured - the joint's "
                "margins describe other leagues (epochs.DERIVED_SHEET_MARGINS)"
            )
        if side_metric not in DERIVED_MARGINAL_CENTRES_METRICS:
            continue
        sample = samples.metrics.get(side_metric)
        if sample is None:
            continue
        own_events = {
            o.sofascore_event_id
            for lst in (sample.side_a, sample.side_b, sample.h2h)
            for o in lst
        }
        for side, obs, team in (
            ("side_a", sample.side_a, fixture.home_entity_id),
            ("side_b", sample.side_b, fixture.away_entity_id),
        ):
            if (side_metric, side) in marginal_centres:
                continue
            values = [o.value for o in obs]
            if len(values) < min_sample or all(v == 0.0 for v in values):
                continue
            centre, _centre_notes, centre_unfitted, rated = sample_centre(
                fixture=fixture,
                market=side_metric,
                subject="",
                n=len(values),
                mean=statistics.mean(values),
                own_sides=[obs],
                own_events=own_events,
                own_teams=[team],
                baselines=baselines,
                day_obs=day_obs,
                football=football,
                tennis_tiers=None,
                engine_constants=engine_constants,
                k_centre=k_centre,
                per_market_k_on=per_market_k_on,
                side=side,
                rating_weights=rating_weights,
                men_friendly_baseline=men_friendly_baseline,
            )
            marginal_centres[(side_metric, side)] = centre
            source = "rating at W_FOOTBALL_RATING" if rated is not None else "no rating"
            notes.setdefault(side_metric, []).append(
                f"SHEET_MARGIN: {side} {side_metric} centre {centre:.2f} from "
                f"the SHEET formula, no ladder quoted ({source}; "
                "epochs.DERIVED_SHEET_MARGINS)"
            )
            unfitted.setdefault(side_metric, []).extend(centre_unfitted)
    return notes, unfitted


def _stats_only_rating_p(
    rating: MatchForecast,
) -> Callable[[str, str | None, float, str], float | None]:
    # The derived rows the neighbours price alone (never the draw of most_games).
    def read(
        market: str, side: str | None, line: float, direction: str
    ) -> float | None:
        if market not in RATING_PRICED_MARKETS or side not in ("side_a", "side_b"):
            return None
        return rating.read(market, side, line, direction)
    return read


# Tennis markets whose range is set by the format: a best-of-five match
# always has >= 3 sets. Their history curve is fitted on best-of-three matches
# only (calibrate_from_cache.set_values, 2026-10-14), and with no known format
# the neighbour table (tennis_forecast) would price the fixture as best of
# three - so a fixture not known to be best of three is refused, never priced.
FORMAT_BOUND_TENNIS_MARKETS: frozenset[str] = frozenset({"sets_total"})


def format_bound_refusal(fixture: Fixture, market: str) -> str | None:
    """Why a format-bound tennis market is refused on this fixture, or None
    (BEST_OF_FIVE_NOT_MODELLED)."""
    if (fixture.sport != "tennis" or market not in FORMAT_BOUND_TENNIS_MARKETS
            or fixture.default_period_count == 3):
        return None
    if fixture.default_period_count is None:
        return (f"{market}: the match format is unknown (no "
                "defaultPeriodCount); its curve is fitted on best of three only")
    return (f"{market}: best of {fixture.default_period_count} is not "
            "modelled; its curve is fitted on best of three only")


def tennis_forecast(
    model: TennisRatingModel | None, fixture: Fixture
) -> MatchForecast | None:
    if model is None or fixture.sport != "tennis":
        return None
    if fixture.default_period_count not in (None, 3):
        return None  # best of five is not modelled
    return model.forecast(
        fixture.home_entity_id,
        fixture.away_entity_id,
        fixture.category_name,
        fixture.ground_type,
        fixture.kickoff_utc,
    )


def football_forecast_p(
    market: str,
    sport: str,
    values: list[float],
    mean: float,
    variance: float,
    n: int,
    rated_centre: float,
    boundary: float,
    direction: Literal["OVER", "UNDER"],
    dispersion: Dispersion | None = None,
) -> float | None:
    """The football rating's own P(selection wins) - K11's "model" number.

    The same predictive distribution SHEET prices a row with
    (`sheet_predictive_sd`, the same estimator), centred on the rating's
    expected count instead of the sample's shrunk centre. Not calibrated,
    never a gate, never an order: shown beside the calibrated confidence.
    """
    if uses_empirical_frequency(market):
        p = p_empirical_centred_raw(values, boundary, direction, rated_centre - mean)
    else:
        sd = sheet_predictive_sd(
            market, sport, mean, variance, n, rated_centre, dispersion)
        p = sheet_count_p_raw(
            market, rated_centre, sd, boundary, direction, dispersion)
    return None if outside_model_resolution(p) else p


def winner_rows(
    fixture: Fixture,
    rung: PricedRung,
    rating: MatchForecast | None,
    market_ps: dict[tuple[str, str, float, str], float],
    stats_only: bool,
) -> tuple[list[SheetRow], list[tuple[Any, GapReason, str]]]:
    """D2 (epochs.TENNIS_MATCH_WINNER): the two rows of one tennis winner rung,
    priced by the as-of rating alone (bet.sofa.tennis_winner).

    p_central is the rating's P(the subject's side wins) - no sample, no
    price. The row carries no sample (sample_size 0) and p_bar = p_central
    ("rating_only"): 06_coupon.json's priced selector never calls it VALUE
    (no ladder check), the confidence comes from the match_won_for curve."""
    side = determine_side(rung.subject, fixture)
    if side is None:
        return [], [(rung, GapReason.NO_MATCHING_EVENT,
                     f"subject {rung.subject!r} matches neither side")]
    if rating is None:
        return [], [(rung, GapReason.NOT_RATED,
                     "no rating forecast (best of five, or a player under "
                     "MIN_RATED rated matches)")]
    p_side = rating.p_side_wins(side)
    rows: list[SheetRow] = []
    skipped: list[tuple[Any, GapReason, str]] = []
    note = winner_note(p_side, side, rating.rated_home, rating.rated_away,
                       rating.table_scope)
    for direction in ("OVER", "UNDER"):
        p = winner_p(p_side, direction)
        if outside_model_resolution(p):
            skipped.append((rung, GapReason.OUTSIDE_MODEL_RESOLUTION,
                            f"p={p:.4g} for {direction} is outside "
                            f"[{P_FLOOR}, {P_CEILING}]"))
            continue
        offered = rung.over_odds if direction == "OVER" else rung.under_odds
        m_p = market_ps.get((rung.market, rung.subject, rung.line, direction))
        p_out = round(p, 4)
        m_p_out = round(m_p, 4) if m_p is not None else None
        req = round(get_required_odds(p_out, "LEAN"), 4)
        surplus = round(offered - req, 4) if offered is not None else None
        verdict: Literal["VALUE", "LEAN", "BELOW_BAR", "NO_PRICE", "BLOCKED"] = (
            "NO_PRICE" if offered is None
            else "LEAN" if surplus is not None and surplus > 0 else "BELOW_BAR")
        notes = [note]
        if verdict == "LEAN":
            notes.append("RATING_ONLY: no sample and no ladder check - "
                         "VALUE withheld (06_coupon.json is not the coupon)")
        rows.append(SheetRow(
            sofascore_event_id=fixture.sofascore_event_id,
            sport=fixture.sport,
            market=rung.market,
            subject=rung.subject,
            line=rung.line,
            direction=direction,
            sample_size=0,
            sample_mean=0.0,
            sample_sd=0.0,
            centre=round(p_side, 4),
            p_central=p_out,
            market_p=m_p_out,
            ladder_centre=None,
            ladder_sigma=None,
            p_bar=p_out,
            bar_reason="rating_only",
            calibration_correction=0.0,
            sample_newest_days=None,
            sample_frequency=None,
            required_odds=req,
            offered_odds=offered,
            edge=round(p_out - m_p_out, 4) if m_p_out is not None else None,
            surplus=surplus,
            verdict=verdict,
            notes=notes,
            epoch=STATS_ONLY if stats_only else None,
            forecast_p=p_out if stats_only else None,
            forecast_source="tennis_rating" if stats_only else None,
        ))
    return rows, skipped


def double_chance_rows(
    fixture: Fixture,
    rung: PricedRung,
    football: FootballForecast | None,
    result_config: ResultConfig,
    market_ps: dict[tuple[str, str, float, str], float],
    stats_only: bool,
) -> tuple[list[SheetRow], list[tuple[Any, GapReason, str]]]:
    """Audit D1 (epochs.FOOTBALL_RESULT_MARKETS): the row of one football
    double chance rung, priced from independent NB goals on the PURE rating
    centres (bet.sofa.football_result) - no sample, no price.

    Only the OVER (the DC selection) is priced: its UNDER is a single 1X2
    outcome, which did not meet the registered threshold. An UNLINKED
    fixture keeps its row with CROSS_LEAGUE_UNLINKED (CONFIDENCE refuses it,
    as every football row); no goals centre for either side - no row."""
    if rung.subject not in LEFT_OUT:
        return [], [(rung, GapReason.NO_MATCHING_EVENT,
                     f"double chance selection {rung.subject!r} unknown")]
    home = football.centre("goals_for", "side_a") if football else None
    away = football.centre("goals_for", "side_b") if football else None
    if football is None or home is None or away is None:
        return [], [(rung, GapReason.NOT_RATED,
                     "no football rating goals centre for one of the sides "
                     "(thin team, friendly, no league rate)")]
    lh, la = home[0], away[0]
    try:
        probs = result_probs(lh, la, result_config.nb_r)
    except ValueError as exc:
        return [], [(rung, GapReason.NOT_RATED, str(exc))]
    p = probs[rung.subject]
    if outside_model_resolution(p):
        return [], [(rung, GapReason.OUTSIDE_MODEL_RESOLUTION,
                     f"p={p:.4g} for OVER is outside [{P_FLOOR}, {P_CEILING}]")]
    offered = rung.over_odds
    m_p = market_ps.get((rung.market, rung.subject, rung.line, "OVER"))
    p_out = round(p, 4)
    m_p_out = round(m_p, 4) if m_p is not None else None
    req = round(get_required_odds(p_out, "LEAN"), 4)
    surplus = round(offered - req, 4) if offered is not None else None
    verdict: Literal["VALUE", "LEAN", "BELOW_BAR", "NO_PRICE", "BLOCKED"] = (
        "NO_PRICE" if offered is None
        else "LEAN" if surplus is not None and surplus > 0 else "BELOW_BAR")
    notes = [dc_note(rung.subject, p, lh, la, result_config.nb_r)]
    if football.fixture_link() == UNLINKED:
        notes.append(
            f"{CROSS_LEAGUE_UNLINKED_NOTE}: the two sides share no league "
            "and their leagues' strengths are unmeasured - the rating "
            "describes other leagues")
    if verdict == "LEAN":
        notes.append("RATING_ONLY: no sample and no ladder check - "
                     "VALUE withheld (06_coupon.json is not the coupon)")
    notes.append("UNFITTED_CONSTANTS: "
                 f"{', '.join(RESULT_UNFITTED + RATING_UNFITTED)}")
    row = SheetRow(
        sofascore_event_id=fixture.sofascore_event_id,
        sport=fixture.sport,
        market=rung.market,
        subject=rung.subject,
        line=rung.line,
        direction="OVER",
        sample_size=0,
        sample_mean=0.0,
        sample_sd=0.0,
        centre=p_out,
        p_central=p_out,
        market_p=m_p_out,
        ladder_centre=None,
        ladder_sigma=None,
        p_bar=p_out,
        bar_reason="rating_only",
        calibration_correction=0.0,
        sample_newest_days=None,
        sample_frequency=None,
        required_odds=req,
        offered_odds=offered,
        edge=round(p_out - m_p_out, 4) if m_p_out is not None else None,
        surplus=surplus,
        verdict=verdict,
        notes=notes,
        epoch=STATS_ONLY if stats_only else None,
        forecast_p=p_out if stats_only else None,
        forecast_source="football_rating" if stats_only else None,
        result_rule=epochs.FOOTBALL_RESULT_MARKETS,
    )
    return [row], []


def result_1x2_dnb_rows(
    fixture: Fixture,
    rung: PricedRung,
    football: FootballForecast | None,
    result_config: ResultConfig,
    phase: str | None,
    market_ps: dict[tuple[str, str, float, str], float],
    stats_only: bool,
) -> tuple[list[SheetRow], list[tuple[Any, GapReason, str]]]:
    """epochs.FOOTBALL_RESULT_1X2_DNB: the rows of one result_1x2 rung (its
    OVER, the side's win) or draw_no_bet rung (OVER the home side, UNDER the
    away side), priced from the double chance's NB goals on the PURE rating
    centres (bet.sofa.football_1x2_dnb) - no sample, no price. Each row
    carries the fixture's as-of season phase (`result_phase`), which picks
    its curve class in CONFIDENCE. UNLINKED keeps CROSS_LEAGUE_UNLINKED
    (CONFIDENCE refuses it); no goals centre for either side - no row."""
    directions: tuple[Literal["OVER", "UNDER"], ...] = (
        ("OVER",) if rung.market == RESULT_1X2 else ("OVER", "UNDER"))
    if ((rung.market == RESULT_1X2 and rung.subject not in RESULT_SIDES)
            or (rung.market == DRAW_NO_BET and rung.subject != DNB_SUBJECT)):
        return [], [(rung, GapReason.NO_MATCHING_EVENT,
                     f"{rung.market} subject {rung.subject!r} unknown")]
    home = football.centre("goals_for", "side_a") if football else None
    away = football.centre("goals_for", "side_b") if football else None
    if football is None or home is None or away is None:
        return [], [(rung, GapReason.NOT_RATED,
                     "no football rating goals centre for one of the sides "
                     "(thin team, friendly, no league rate)")]
    lh, la = home[0], away[0]
    try:
        probs = result_1x2_dnb_probabilities(lh, la, result_config.nb_r)
    except ValueError as exc:
        return [], [(rung, GapReason.NOT_RATED, str(exc))]
    rows: list[SheetRow] = []
    skipped: list[tuple[Any, GapReason, str]] = []
    unlinked = football.fixture_link() == UNLINKED
    for direction in directions:
        p = result_1x2_dnb_row_p(rung.market, rung.subject or "", direction,
                                 probs)
        if p is None:
            continue
        if outside_model_resolution(p):
            skipped.append((rung, GapReason.OUTSIDE_MODEL_RESOLUTION,
                            f"p={p:.4g} for {direction} is outside "
                            f"[{P_FLOOR}, {P_CEILING}]"))
            continue
        notes = [result_1x2_dnb_note(rung.market, rung.subject or "", direction,
                                     p, lh, la, result_config.nb_r, phase)]
        if unlinked:
            notes.append(
                f"{CROSS_LEAGUE_UNLINKED_NOTE}: the two sides share no league "
                "and their leagues' strengths are unmeasured - the rating "
                "describes other leagues")
        notes.append("UNFITTED_CONSTANTS: "
                     f"{', '.join(RESULT_UNFITTED + RATING_UNFITTED)}")
        row = _model_only_row(
            fixture, rung, direction, p, notes, market_ps, stats_only,
            "football_rating", {})
        rows.append(row.model_copy(update={
            "result_1x2_dnb_rule": epochs.FOOTBALL_RESULT_1X2_DNB,
            "result_phase": phase}))
    return rows, skipped


def score_market_rows(
    fixture: Fixture,
    rung: PricedRung,
    football: FootballForecast | None,
    result_config: ResultConfig,
    market_ps: dict[tuple[str, str, float, str], float],
    stats_only: bool,
    phase: str | None = None,
) -> tuple[list[SheetRow], list[tuple[Any, GapReason, str]]]:
    """epochs.FOOTBALL_SCORE_MARKETS: the OVER row of one football
    score-market rung ("or" result markets, the +L handicap, the DC & goals
    pairs - bet.sofa.football_score_markets), priced from the double
    chance's NB goals on the PURE rating centres - no sample, no price. The
    rung's UNDER is a price for its margin only. UNLINKED keeps
    CROSS_LEAGUE_UNLINKED (CONFIDENCE refuses it); no goals centre for
    either side - no row. The row carries the fixture's as-of season phase
    (`result_phase`), which picks its curve class in CONFIDENCE."""
    subject = rung.subject or ""
    if not score_market_rung(rung.market, subject, rung.line):
        return [], [(rung, GapReason.NO_MATCHING_EVENT,
                     f"{rung.market} {subject!r} @ {rung.line} unknown")]
    home = football.centre("goals_for", "side_a") if football else None
    away = football.centre("goals_for", "side_b") if football else None
    if football is None or home is None or away is None:
        return [], [(rung, GapReason.NOT_RATED,
                     "no football rating goals centre for one of the sides "
                     "(thin team, friendly, no league rate)")]
    lh, la = home[0], away[0]
    try:
        grid = score_grid(lh, la, result_config.nb_r)
    except ValueError as exc:
        return [], [(rung, GapReason.NOT_RATED, str(exc))]
    p = score_market_row_p(rung.market, subject, rung.line, grid)
    if outside_model_resolution(p):
        return [], [(rung, GapReason.OUTSIDE_MODEL_RESOLUTION,
                     f"p={p:.4g} for OVER is outside [{P_FLOOR}, {P_CEILING}]")]
    notes = [score_market_note(rung.market, subject, rung.line, p, lh, la,
                               result_config.nb_r)]
    if football.fixture_link() == UNLINKED:
        notes.append(
            f"{CROSS_LEAGUE_UNLINKED_NOTE}: the two sides share no league "
            "and their leagues' strengths are unmeasured - the rating "
            "describes other leagues")
    notes.append("UNFITTED_CONSTANTS: "
                 f"{', '.join(RESULT_UNFITTED + RATING_UNFITTED)}")
    row = _model_only_row(fixture, rung, "OVER", p, notes, market_ps,
                          stats_only, "football_rating",
                          {"score_market_rule": epochs.FOOTBALL_SCORE_MARKETS})
    return [row.model_copy(update={"result_phase": phase})], []


def _model_only_row(
    fixture: Fixture,
    rung: PricedRung,
    direction: Literal["OVER", "UNDER"],
    p: float,
    notes: list[str],
    market_ps: dict[tuple[str, str, float, str], float],
    stats_only: bool,
    source: str,
    marker: dict[str, str],
) -> SheetRow:
    """One row of a market priced by a model alone (no sample, no price):
    the football incident and tennis set markets. p_bar = p_central
    ("rating_only"): 06_coupon.json's priced selector never calls it VALUE."""
    offered = rung.over_odds if direction == "OVER" else rung.under_odds
    m_p = market_ps.get((rung.market, rung.subject, rung.line, direction))
    p_out = round(p, 4)
    m_p_out = round(m_p, 4) if m_p is not None else None
    req = round(get_required_odds(p_out, "LEAN"), 4)
    surplus = round(offered - req, 4) if offered is not None else None
    verdict: Literal["VALUE", "LEAN", "BELOW_BAR", "NO_PRICE", "BLOCKED"] = (
        "NO_PRICE" if offered is None
        else "LEAN" if surplus is not None and surplus > 0 else "BELOW_BAR")
    row_notes = list(notes)
    if verdict == "LEAN":
        row_notes.append("RATING_ONLY: no sample and no ladder check - "
                         "VALUE withheld (06_coupon.json is not the coupon)")
    return SheetRow(
        sofascore_event_id=fixture.sofascore_event_id,
        sport=fixture.sport,
        market=rung.market,
        subject=rung.subject,
        line=rung.line,
        direction=direction,
        sample_size=0,
        sample_mean=0.0,
        sample_sd=0.0,
        centre=p_out,
        p_central=p_out,
        market_p=m_p_out,
        ladder_centre=None,
        ladder_sigma=None,
        p_bar=p_out,
        bar_reason="rating_only",
        calibration_correction=0.0,
        sample_newest_days=None,
        sample_frequency=None,
        required_odds=req,
        offered_odds=offered,
        edge=round(p_out - m_p_out, 4) if m_p_out is not None else None,
        surplus=surplus,
        verdict=verdict,
        notes=row_notes,
        epoch=STATS_ONLY if stats_only else None,
        forecast_p=p_out if stats_only else None,
        forecast_source=source if stats_only else None,
    ).model_copy(update=marker)


# The sides a two-sided model row is written for - both, like the match
# winner (a side Superbet does not quote is NO_PRICE).
_BOTH_DIRECTIONS: tuple[Literal["OVER", "UNDER"], ...] = ("OVER", "UNDER")


def incident_rows(
    fixture: Fixture,
    rung: PricedRung,
    football: FootballForecast | None,
    incidents: IncidentPricing,
    market_ps: dict[tuple[str, str, float, str], float],
    stats_only: bool,
) -> tuple[list[SheetRow], list[tuple[Any, GapReason, str]]]:
    """epochs.FOOTBALL_INCIDENT_MARKETS: the rows of one football first-goal,
    red-cards or penalties rung (bet.sofa.football_incidents) - no sample,
    no price.

    first_goal (OVER only, one-sided): the double chance's NB goals on the
    PURE rating centres - no goals centre for a side, no row; UNLINKED keeps
    its row with CROSS_LEAGUE_UNLINKED like every rated football row. Red
    cards / penalties (OVER and UNDER): the competition's as-of full-feed
    rate shrunk to the gender's, on the measured lines (0.5, 1.5) only."""
    marker = {"incident_rule": epochs.FOOTBALL_INCIDENT_MARKETS}
    unfitted = "UNFITTED_CONSTANTS: " + ", ".join(INCIDENT_UNFITTED)
    if rung.market == FIRST_GOAL:
        if rung.subject not in FG_SUBJECTS:
            return [], [(rung, GapReason.NO_MATCHING_EVENT,
                         f"first goal selection {rung.subject!r} unknown")]
        home = football.centre("goals_for", "side_a") if football else None
        away = football.centre("goals_for", "side_b") if football else None
        if football is None or home is None or away is None:
            return [], [(rung, GapReason.NOT_RATED,
                         "no football rating goals centre for one of the sides "
                         "(thin team, friendly, no league rate)")]
        lh, la = home[0], away[0]
        try:
            p = first_goal_probs(lh, la, incidents.result.nb_r)[rung.subject]
        except ValueError as exc:
            return [], [(rung, GapReason.NOT_RATED, str(exc))]
        if outside_model_resolution(p):
            return [], [(rung, GapReason.OUTSIDE_MODEL_RESOLUTION,
                         f"p={p:.4g} for OVER is outside [{P_FLOOR}, {P_CEILING}]")]
        notes = [incident_note(
            rung.market, rung.subject, p,
            f"NB goals (r {incidents.result.nb_r:g}) on the pure rating centres "
            f"home {lh:.3f} / away {la:.3f}")]
        if football.fixture_link() == UNLINKED:
            notes.append(
                f"{CROSS_LEAGUE_UNLINKED_NOTE}: the two sides share no league "
                "and their leagues' strengths are unmeasured - the rating "
                "describes other leagues")
        notes.append(f"{unfitted}, "
                     f"{', '.join(RESULT_UNFITTED + RATING_UNFITTED)}")
        return [_model_only_row(fixture, rung, "OVER", p, notes, market_ps,
                                stats_only, "football_rating", marker)], []
    p_over = incidents.rates.p_over(rung.market, fixture.competition_id, rung.line)
    if p_over is None:
        return [], [(rung, GapReason.NOT_RATED,
                     f"{rung.market} line {rung.line:g}: not a measured line "
                     "or no gender rate behind it")]
    n_comp = incidents.rates.n_comp(rung.market, fixture.competition_id)
    rows: list[SheetRow] = []
    skipped: list[tuple[Any, GapReason, str]] = []
    for direction in _BOTH_DIRECTIONS:
        p = p_over if direction == "OVER" else 1.0 - p_over
        if outside_model_resolution(p):
            skipped.append((rung, GapReason.OUTSIDE_MODEL_RESOLUTION,
                            f"p={p:.4g} for {direction} is outside "
                            f"[{P_FLOOR}, {P_CEILING}]"))
            continue
        notes = [incident_note(
            rung.market, "", p,
            f"the competition's as-of rate ({n_comp} full-feed matches) shrunk "
            "toward the gender's"), unfitted]
        rows.append(_model_only_row(fixture, rung, direction, p, notes,
                                    market_ps, stats_only, "league_rate", marker))
    return rows, skipped


def card_half_term_mults(
    football: FootballForecast | None,
    game_state: GameStateTable | None,
    referee_effect: RefereeEffectTable | None,
    referee_reads: Mapping[str, RefereeRead] | None,
    closeness_stretch: ClosenessStretchTable | None,
) -> dict[str, tuple[float, str]]:
    """epochs.FOOTBALL_CARD_HALVES_TERMS: side -> (the multiplier the sheet
    puts on a full-match cards_points_for centre - GAME_STATE x referee x
    closeness, each 1.0 when its table is off or it reads nothing - and its
    note), for a side whose full-match row has no live centre."""
    market = "cards_points_for"
    out: dict[str, tuple[float, str]] = {}
    ref_mult, ref_why = 1.0, "referee off"
    if referee_effect is not None:
        applied = referee_effect.apply(
            market, (referee_reads or {}).get(referee_terms.family_of(market) or ""))
        if applied is not None:
            ref_mult = applied[0]
            ref_why = f"referee {applied[1].get('status')} x{ref_mult:.3f}"
    cl_mult, cl_why = 1.0, "closeness off"
    if closeness_stretch is not None and football is not None:
        m = closeness_stretch.multiplier(market, closeness_supremacy(football))
        if m is not None:
            cl_mult, cl_why = m, f"closeness x{m:.3f}"
    for side in ("side_a", "side_b"):
        gs_mult, gs_why = 1.0, "game state off"
        if game_state is not None and football is not None:
            m = game_state.multiplier(market, football.supremacy(side))
            if m is not None:
                gs_mult, gs_why = m, f"game state x{m:.3f}"
        out[side] = (gs_mult * ref_mult * cl_mult,
                     f"no full-match row: {gs_why}, {ref_why}, {cl_why}")
    return out


def card_half_rows(
    fixture: Fixture,
    rung: PricedRung,
    football: FootballForecast | None,
    rates: CardHalfRates,
    market_ps: dict[tuple[str, str, float, str], float],
    stats_only: bool,
    live_centres: Mapping[str, float] | None = None,
    term_mults: Mapping[str, tuple[float, str]] | None = None,
) -> tuple[list[SheetRow], list[tuple[Any, GapReason, str]]]:
    """epochs.FOOTBALL_CARD_HALVES: the rows of one football card-half,
    side / half red-card or penalty rung (bet.sofa.football_card_halves) -
    no sample, no price.

    Card halves: an NB count per side on the side's full-match card-points
    rating centre x the competition's as-of half share (counts OVER and
    UNDER; most / handicap OVER only, one selection each). No centre for a
    side, no row; UNLINKED keeps its row with CROSS_LEAGUE_UNLINKED like
    every rated football row. Events (OVER and UNDER): the competition's
    as-of full-feed rate shrunk to the gender's, on the measured lines.

    epochs.FOOTBALL_CARD_HALVES_TERMS (``term_mults`` not None): a side's
    centre is its full-match live cards_points_for centre
    (``live_centres``, the sheet's own row centre), else its rating centre
    x ``term_mults`` (GAME_STATE x referee x closeness, with their notes);
    penalties_for / penalties_1h_for / red_cards_for at 0.5 scale the
    league intensity by the side's game state (side_event_p)."""
    terms_on = term_mults is not None
    marker = {"incident_rule": (epochs.FOOTBALL_CARD_HALVES_TERMS if terms_on
                                else epochs.FOOTBALL_CARD_HALVES)}
    unfitted = "UNFITTED_CONSTANTS: " + ", ".join(CARD_HALF_UNFITTED)
    sided = rung.market not in CARD_HALF_TOTAL_MARKETS
    side = determine_side(rung.subject, fixture) if sided else None
    if sided and side is None:
        return [], [(rung, GapReason.NO_MATCHING_EVENT,
                     f"subject {rung.subject!r} matches neither side")]
    rows: list[SheetRow] = []
    skipped: list[tuple[Any, GapReason, str]] = []
    if rung.market in CARD_HALF_EVENT_MARKETS:
        p_over = rates.p_over(rung.market, fixture.competition_id, rung.line)
        if p_over is None:
            return [], [(rung, GapReason.NOT_RATED,
                         f"{rung.market} line {rung.line:g}: not a measured line "
                         "or no gender rate behind it")]
        n_comp = rates.n_comp(rung.market, fixture.competition_id, rung.line)
        event_detail = (f"the competition's as-of rate ({n_comp} full-feed "
                        "matches) shrunk toward the gender's")
        if terms_on and side is not None:
            ev_sup = football.supremacy(side) if football is not None else None
            p_term = side_event_p(rung.market, rung.line, p_over, ev_sup)
            if p_term is not None and ev_sup is not None:
                event_detail += (
                    f", {p_over:.4f} -> {p_term:.4f} by the side's expected "
                    f"goal difference {ev_sup:+.2f} "
                    "(epochs.FOOTBALL_CARD_HALVES_TERMS)")
                p_over = p_term
        for direction in _BOTH_DIRECTIONS:
            p = p_over if direction == "OVER" else 1.0 - p_over
            if outside_model_resolution(p):
                skipped.append((rung, GapReason.OUTSIDE_MODEL_RESOLUTION,
                                f"p={p:.4g} for {direction} is outside "
                                f"[{P_FLOOR}, {P_CEILING}]"))
                continue
            notes = [card_halves_note(rung.market, rung.subject, p,
                                      event_detail), unfitted]
            rows.append(_model_only_row(fixture, rung, direction, p, notes,
                                        market_ps, stats_only, "league_rate",
                                        marker))
        return rows, skipped
    home = football.centre("cards_points_for", "side_a") if football else None
    away = football.centre("cards_points_for", "side_b") if football else None
    if football is None or home is None or away is None:
        return [], [(rung, GapReason.NOT_RATED,
                     "no football rating card-points centre for one of the "
                     "sides (thin team, friendly, no league rate)")]
    half = CARD_HALF_OF[rung.market]
    share = rates.half_share(fixture.competition_id, half)
    if share is None:
        return [], [(rung, GapReason.NOT_RATED,
                     "no as-of card-points half share behind the gender")]
    centres = (home[0], away[0])
    detail = (f"NB card points (half {half}, share {share:.3f}) on the rating "
              f"centres home {home[0]:.3f} / away {away[0]:.3f}")
    if term_mults is not None:
        # epochs.FOOTBALL_CARD_HALVES_TERMS: the full-match live centre
        parts = []
        live_pair = []
        for s_key, rated_c, label in (("side_a", home[0], "home"),
                                      ("side_b", away[0], "away")):
            live_c = (live_centres or {}).get(s_key)
            if live_c is not None:
                live_pair.append(live_c)
                parts.append(f"{label} {live_c:.3f} (its full-match "
                             "cards_points_for row's centre)")
            else:
                mult, why = term_mults.get(s_key, (1.0, "no term"))
                live_pair.append(rated_c * mult)
                parts.append(f"{label} {rated_c * mult:.3f} = rating "
                             f"{rated_c:.3f} x {mult:.3f} ({why})")
        centres = (live_pair[0], live_pair[1])
        detail = (f"NB card points (half {half}, share {share:.3f}) on the "
                  f"full-match live centres {'; '.join(parts)} "
                  "(epochs.FOOTBALL_CARD_HALVES_TERMS)")
    p_sel = card_half_p(rung.market, side, rung.subject, rung.line,
                        centres, share)
    if p_sel is None:
        return [], [(rung, GapReason.NOT_RATED,
                     f"{rung.market} {rung.subject!r} line {rung.line:g}: "
                     "not a measured line or subject")]
    directions: tuple[Literal["OVER", "UNDER"], ...] = (
        _BOTH_DIRECTIONS if rung.market in CARD_HALF_COUNT_MARKETS else ("OVER",))
    for direction in directions:
        p = p_sel if direction == "OVER" else 1.0 - p_sel
        if outside_model_resolution(p):
            skipped.append((rung, GapReason.OUTSIDE_MODEL_RESOLUTION,
                            f"p={p:.4g} for {direction} is outside "
                            f"[{P_FLOOR}, {P_CEILING}]"))
            continue
        notes = [card_halves_note(rung.market, rung.subject, p, detail)]
        if football.fixture_link() == UNLINKED:
            notes.append(
                f"{CROSS_LEAGUE_UNLINKED_NOTE}: the two sides share no league "
                "and their leagues' strengths are unmeasured - the rating "
                "describes other leagues")
        notes.append(f"{unfitted}, {', '.join(RATING_UNFITTED)}")
        rows.append(_model_only_row(fixture, rung, direction, p, notes,
                                    market_ps, stats_only, "football_rating",
                                    marker))
    return rows, skipped


def set_market_rows(
    fixture: Fixture,
    rung: PricedRung,
    rating: MatchForecast | None,
    market_ps: dict[tuple[str, str, float, str], float],
    stats_only: bool,
) -> tuple[list[SheetRow], list[tuple[Any, GapReason, str]]]:
    """epochs.TENNIS_SET_MARKETS: the rows of one tennis set-winner rung (OVER
    and UNDER, like the match winner) or exact-sets rung (OVER only), from
    the as-of rating's neighbours (bet.sofa.tennis_sets) - no sample, no
    price. Best of three only: no forecast, no row."""
    marker = {"set_market_rule": epochs.TENNIS_SET_MARKETS}
    if rung.market == SET_SCORE_NOT:
        # epochs.TENNIS_SET_COMPLEMENTS: NOT the exact score (OVER only)
        marker = {**marker, "set_complement_rule": epochs.TENNIS_SET_COMPLEMENTS}
    if rung.market in (SET_SCORE, SET_SCORE_NOT):
        parsed = split_score_subject(rung.subject)
        name = parsed[0] if parsed is not None else ""
    else:
        parsed = None
        name = rung.subject
    side = determine_side(name, fixture) if name else None
    if side is None:
        return [], [(rung, GapReason.NO_MATCHING_EVENT,
                     f"subject {rung.subject!r} matches neither side")]
    if rating is None or not rating.neighbours_home:
        return [], [(rung, GapReason.NOT_RATED,
                     "no rating forecast (best of five, or a player under "
                     "MIN_RATED rated matches)")]
    pool = len(rating.neighbours_home)
    if rung.market in (SET_SCORE, SET_SCORE_NOT):
        assert parsed is not None
        probs = score_probs(rating.neighbours_home)
        if probs is None:
            return [], [(rung, GapReason.NOT_RATED, "no neighbours")]
        score = parsed[1] if side == "side_a" else flip(parsed[1])
        p = probs[score] if rung.market == SET_SCORE else 1.0 - probs[score]
        if outside_model_resolution(p):
            return [], [(rung, GapReason.OUTSIDE_MODEL_RESOLUTION,
                         f"p={p:.4g} for OVER is outside [{P_FLOOR}, {P_CEILING}]")]
        notes = [set_note(rung.market, rung.subject, p, side, pool,
                          rating.table_scope)
                 if rung.market == SET_SCORE else
                 complement_note(rung.subject, p, side, pool, rating.table_scope)]
        return [_model_only_row(fixture, rung, "OVER", p, notes, market_ps,
                                stats_only, "tennis_rating", marker)], []
    set_index = 1 if rung.market == SET1_WON_FOR else 2
    p_home = set_win_p(rating.neighbours_home, set_index)
    if p_home is None:
        return [], [(rung, GapReason.NOT_RATED, "no neighbours")]
    p_side = p_home if side == "side_a" else 1.0 - p_home
    rows: list[SheetRow] = []
    skipped: list[tuple[Any, GapReason, str]] = []
    for direction in _BOTH_DIRECTIONS:
        p = p_side if direction == "OVER" else 1.0 - p_side
        if outside_model_resolution(p):
            skipped.append((rung, GapReason.OUTSIDE_MODEL_RESOLUTION,
                            f"p={p:.4g} for {direction} is outside "
                            f"[{P_FLOOR}, {P_CEILING}]"))
            continue
        notes = [set_note(rung.market, rung.subject, p_side, side, pool,
                          rating.table_scope)]
        rows.append(_model_only_row(fixture, rung, direction, p, notes,
                                    market_ps, stats_only, "tennis_rating", marker))
    return rows, skipped


def player_coverage_notes(subject: str, sample: Any) -> list[str]:
    """The notes of a footballer's sample built under
    epochs.FOOTBALL_PLAYER_COVERAGE_FROM_UTC (its two name fallbacks, its
    widened window); [] for every other sample, so a sheet built without the
    switch is unchanged."""
    notes: list[str] = []
    if sample.match_rule == "transliteration":
        notes.append(f"PLAYER_NAME_TRANSLITERATION: Superbet {subject!r} read as "
                     f"Sofascore {sample.matched_name!r} across the Polish / "
                     "English transliteration "
                     "(players.match_player_by_transliteration)")
    if sample.match_rule == "inner_surname":
        notes.append(f"PLAYER_NAME_INNER_SURNAME: Superbet {subject!r} read as "
                     f"Sofascore {sample.matched_name!r} by a surname inside "
                     "the full name (players.match_player_by_inner_surname)")
    if sample.wide_window:
        notes.append(f"PLAYER_WIDE_WINDOW: his newest {len(sample.observations)} "
                     f"starts in the team's last {sample.wide_window} matches - "
                     "fewer than min_sample in the last sample_n "
                     "(samples.coverage_player_samples)")
    return notes


def shot_detail_rows(
    fixture: Fixture,
    rung: PricedRung,
    samples: FixtureSamples,
    fitted: Mapping[str, Any] | None,
    market_ps: dict[tuple[str, str, float, str], float],
    stats_only: bool,
) -> tuple[list[SheetRow], list[tuple[Any, GapReason, str]]]:
    """epochs.SHOT_DETAIL_MARKETS: the two rows of one footballer shot-detail
    rung, priced by shot_detail.forecast - the player's last starts (newest
    last) shrunk to his position's mean, read through a Poisson - from the
    operator-installed config/sofa_shot_detail.json (`fitted`; None: not
    installed, no row, NO_SHOT_DETAIL_FIT). No price enters p_central; p_bar
    = p_central and VALUE is withheld (no ladder check)."""
    player_sample = samples.players.get(player_sample_key(rung.market, rung.subject))
    if player_sample is None:
        return [], [(rung, GapReason.NO_ENTITY_FOUND,
                     f"player {rung.subject!r} has no sample for {rung.market}")]
    if fitted is None:
        return [], [(rung, GapReason.NO_SHOT_DETAIL_FIT,
                     f"NO_SHOT_DETAIL_FIT: config/{SHOT_DETAIL_FIT_FILE} is not "
                     "installed (scripts/sofa/fit_shot_detail.py; the operator's "
                     "install)")]
    spec = (fitted.get("metrics") or {}).get(rung.market)
    if spec is None:
        return [], [(rung, GapReason.NO_SHOT_DETAIL_FIT,
                     f"NO_SHOT_DETAIL_FIT: config/{SHOT_DETAIL_FIT_FILE} has no "
                     f"{rung.market}")]
    obs = player_sample.observations  # newest first
    values = [o.value for o in reversed(obs)]
    p_over = shot_detail_forecast(values, player_sample.position, rung.market,
                                  rung.line, fitted)
    if p_over is None:
        return [], [(rung, GapReason.THIN_SAMPLE,
                     f"{len(values)} observations < MIN_STARTS="
                     f"{SHOT_DETAIL_MIN_STARTS} (or no pool for position "
                     f"{player_sample.position!r})")]
    pools = spec.get("pool") or {}
    pool = float(pools.get(player_sample.position or "", spec.get("pool_all")))
    window = values[-SHOT_DETAIL_WINDOW:]
    centre = shot_detail_shrunk_mean(window, pool, float(spec["k"]))
    n = len(values)
    mean = statistics.mean(values)
    sample_sd = statistics.stdev(values) if n > 1 else 0.0
    newest_days = stalest_side_newest_days([], now(), obs)
    note = (f"SHOT_DETAIL: mean {centre:.3f} = last {len(window)} starts "
            f"{statistics.mean(window):.3f} shrunk to position "
            f"{player_sample.position or 'all'} {pool:.3f} with k={spec['k']} "
            f"(config/{SHOT_DETAIL_FIT_FILE}), Poisson; epochs.SHOT_DETAIL_MARKETS")
    rows: list[SheetRow] = []
    skipped: list[tuple[Any, GapReason, str]] = []
    for direction in ("OVER", "UNDER"):
        p = p_over if direction == "OVER" else 1.0 - p_over
        if outside_model_resolution(p):
            skipped.append((rung, GapReason.OUTSIDE_MODEL_RESOLUTION,
                            f"p={p:.4g} for {direction} is outside "
                            f"[{P_FLOOR}, {P_CEILING}]"))
            continue
        offered = rung.over_odds if direction == "OVER" else rung.under_odds
        m_p = market_ps.get((rung.market, rung.subject, rung.line, direction))
        p_out = round(p, 4)
        m_p_out = round(m_p, 4) if m_p is not None else None
        req = round(get_required_odds(p_out, "LEAN"), 4)
        surplus = round(offered - req, 4) if offered is not None else None
        verdict: Literal["VALUE", "LEAN", "BELOW_BAR", "NO_PRICE", "BLOCKED"] = (
            "NO_PRICE" if offered is None
            else "LEAN" if surplus is not None and surplus > 0 else "BELOW_BAR")
        notes = [note]
        if player_sample.appearances == "starts":
            notes.append("PLAYER_STARTS_ONLY: the sample is his starts - "
                         "Superbet voids a player market unless he starts")
        if player_sample.match_rule == "tokens":
            notes.append(f"PLAYER_NAME_TOKENS: Superbet {rung.subject!r} read as "
                         f"Sofascore {player_sample.matched_name!r} by whole "
                         "name tokens (players.match_player_by_tokens)")
        if player_sample.match_rule == "surname":
            notes.append(f"PLAYER_NAME_SURNAME: Superbet {rung.subject!r} read as "
                         f"Sofascore {player_sample.matched_name!r} by surname "
                         "and first-name prefix (players.match_player_by_surname)")
        notes.extend(player_coverage_notes(rung.subject, player_sample))
        if verdict == "LEAN":
            notes.append("SHOT_DETAIL_ONLY: no ladder check - VALUE withheld "
                         "(06_coupon.json is not the coupon)")
        rows.append(SheetRow(
            sofascore_event_id=fixture.sofascore_event_id,
            sport=fixture.sport,
            market=rung.market,
            subject=rung.subject,
            line=rung.line,
            direction=direction,
            sample_size=n,
            sample_mean=round(mean, 4),
            sample_sd=round(sample_sd, 4),
            centre=round(centre, 4),
            p_central=p_out,
            market_p=m_p_out,
            ladder_centre=None,
            ladder_sigma=None,
            p_bar=p_out,
            bar_reason="shot_detail",
            calibration_correction=0.0,
            sample_newest_days=newest_days,
            sample_frequency=None,
            required_odds=req,
            offered_odds=offered,
            edge=round(p_out - m_p_out, 4) if m_p_out is not None else None,
            surplus=surplus,
            verdict=verdict,
            notes=notes,
            epoch=STATS_ONLY if stats_only else None,
            forecast_p=None,
            forecast_source=None,
            shot_detail_rule=epochs.SHOT_DETAIL_MARKETS,
        ))
    return rows, skipped


def load_shot_detail(config_directory: Path | None = None) -> dict[str, Any] | None:
    """config/sofa_shot_detail.json, or None while the operator has not
    installed it (shot_detail_rows then writes NO_SHOT_DETAIL_FIT)."""
    base = config_directory if config_directory is not None else config_dir()
    return load_shot_detail_fit(base / SHOT_DETAIL_FIT_FILE)


# Fields a stats-only sheet row carries; an old-rule row is written without
# them, so a sheet built before 2026-10-05 is byte-for-byte what it was.
STATS_ONLY_ROW_FIELDS = ("epoch", "forecast_p", "forecast_source")


# The row fields of epochs' audit 2026-10-13 markers (absent while off).
AUDIT_MARKER_FIELDS: tuple[str, ...] = tuple(m[0] for m in (
    epochs.GAME_STATE_MARKER, epochs.FOOTBALL_RATED_SCOPE_MARKER,
    epochs.FOOTBALL_VENUE_PRIOR_MARKER, epochs.SEASON_PHASE_MARKER,
    epochs.FOOTBALL_RATING_WEIGHT_MARKER, epochs.TENNIS_SET_RATING_PRICES_MARKER,
    epochs.FOOTBALL_CUP_STRENGTH_MARKER, epochs.SAMPLE_CUP_STRENGTH_MARKER,
    epochs.FOOTBALL_GOALS_STRETCH_MARKER, epochs.FOOTBALL_COUNT_STRETCH_MARKER,
    epochs.FOOTBALL_PLAYER_STRETCH_MARKER, epochs.TENNIS_ACES_OPPONENT_MARKER,
    epochs.FOOTBALL_REFEREE_MARKER,
    epochs.FOOTBALL_PLAYER_SHARE_MARKER,
    epochs.FOOTBALL_CLOSENESS_STRETCH_MARKER,
))


def cup_book_args(on: bool) -> dict[str, Any]:
    """football_rating.replay's cup arguments: the installed cup list and
    step while epochs.FOOTBALL_CUP_STRENGTH is on, none (the book as it was)
    when off."""
    if not on:
        return {}
    cup = load_cup_strength()
    return {"cup_competitions": cup.competitions, "cup_eta": cup.eta}


def stamp_marker(rows: list[SheetRow], marker: tuple[str, str, str],
                 on: bool) -> list[SheetRow]:
    """The marker's rule name on every row of its sport while `on`
    (epochs.sheet_has_marker reads the same rows); rows unchanged when off."""
    if not on:
        return rows
    field_name, rule, sport = marker
    return [r.model_copy(update={field_name: rule}) if r.sport == sport else r
            for r in rows]


def sheet_row_json(row: SheetRow) -> dict[str, Any]:
    out = row.model_dump(mode="json")
    if out.get("epoch") is None:
        for key in STATS_ONLY_ROW_FIELDS:
            out.pop(key, None)
    # absent under the old link rule: an older sheet stays byte-for-byte
    if out.get("link_rule") is None:
        out.pop("link_rule", None)
    # likewise absent under the sample variance (epochs.COUNT_DISPERSION)
    if out.get("dispersion_rule") is None:
        out.pop("dispersion_rule", None)
    # and from the pooled tennis neighbour table (epochs.TENNIS_SCOPED_TABLE)
    if out.get("tennis_table_rule") is None:
        out.pop("tennis_table_rule", None)
    # and under the sport's K (epochs.PER_MARKET_K)
    if out.get("k_rule") is None:
        out.pop("k_rule", None)
    # and without the cards correlation (epochs.CARDS_CORRELATION)
    if out.get("cards_rule") is None:
        out.pop("cards_rule", None)
    # and from the raw sample (epochs.SAMPLE_OPPONENT_CORRECTION)
    if out.get("opponent_rule") is None:
        out.pop("opponent_rule", None)
    if out.get("corrected_sample") is None:
        out.pop("corrected_sample", None)
    # and the audit 2026-10-13 switches' markers while off, and the config
    # fingerprint of a row priced outside main (tests, replays)
    for key in AUDIT_MARKER_FIELDS + ("result_rule", "shot_detail_rule",
                                      "incident_rule", "set_market_rule",
                                      "result_1x2_dnb_rule", "result_phase",
                                      "score_market_rule", "set_complement_rule",
                                      "referee_read", "player_props_v2_rule",
                                      "config_sha"):
        if out.get(key) is None:
            out.pop(key, None)
    return out


def player_share_centre(
    market: str,
    subject: str,
    side: str,
    samples: FixtureSamples,
    cell: psh.ShareCell,
    team_centres: Mapping[tuple[str, str], float],
) -> tuple[float | None, str]:
    """(the share model's centre or None, the row's note) for one
    footballer's row (epochs.FOOTBALL_PLAYER_SHARE): his volume over his
    sampled starts against his side's in the same matches (the raw SAMPLES
    values), shrunk to his position's share, x his side's team centre today
    (``team_centres``, the team rows SHEET priced); None - the old centre -
    when the side has no team row or too few matched starts."""
    team_metric = psh.TEAM_METRIC[market]
    team_centre = team_centres.get((team_metric, side))
    if team_centre is None:
        return None, (f"{psh.NOTE}: no {team_metric} row for his side (not "
                      "quoted or not priced) - the centre is his own sample's")
    volume = samples.players.get(
        player_sample_key(psh.VOLUME_METRIC[market], subject))
    team_sample = samples.metrics.get(team_metric)
    if volume is None or team_sample is None:
        return None, (f"{psh.NOTE}: no {psh.VOLUME_METRIC[market]} / "
                      f"{team_metric} sample - the centre is his own sample's")
    own_sample = (samples.players.get(player_sample_key(market, subject))
                  if market in psh.ACCURACY_MARKETS else None)
    team_obs = team_sample.side_a if side == "side_a" else team_sample.side_b
    inputs = psh.share_inputs(
        [(o.sofascore_event_id, o.value) for o in volume.observations],
        [(o.sofascore_event_id, o.value) for o in team_obs],
        None if own_sample is None
        else [(o.sofascore_event_id, o.value) for o in own_sample.observations])
    if inputs.matches < psh.MIN_SHARE_MATCHES:
        return None, (f"{psh.NOTE}: {inputs.matches} of his starts matched to "
                      f"his side's {team_metric} (< {psh.MIN_SHARE_MATCHES}) - "
                      "the centre is his own sample's")
    position = next(
        (ps.position for key, ps in sorted(samples.players.items())
         if ps.position and key.endswith(f"|{subject}")), None)
    prior = cell.share_prior(position)
    accuracy_prior = cell.accuracy_prior(position)
    centre = psh.share_centre(
        his_volume=inputs.his_volume, team_volume=inputs.team_volume,
        team_centre=team_centre, prior_share=prior, m=cell.m,
        his_count=inputs.his_count if market in psh.ACCURACY_MARKETS else None,
        prior_accuracy=accuracy_prior, m_accuracy=cell.m_accuracy)
    text = (f"{psh.NOTE}: centre {centre:.2f} = share of {inputs.his_volume:g} "
            f"/ {inputs.team_volume:g} in {inputs.matches} starts (prior "
            f"{prior:.3f}, {position or 'all positions'}) x his side's "
            f"{team_metric} centre {team_centre:.2f}")
    if market in psh.ACCURACY_MARKETS and inputs.his_count is not None:
        text += (f" x accuracy of {inputs.his_count:g} / {inputs.his_volume:g} "
                 f"(prior {accuracy_prior or 0.0:.3f})")
    return centre, (f"{text}; {cell.describe()}; "
                    "epochs.FOOTBALL_PLAYER_SHARE")


def process_fixture(
    fixture: Fixture,
    samples: FixtureSamples,
    offer: FixtureOffer,
    baselines: dict[str, Any],
    reliability: dict[str, Any],
    engine_constants: dict[str, Any],
    vetoes: list[Veto],
    config: SofaConfig,
    side_correlations: dict[str, float | None] | None = None,
    day_obs: DayLeagueObservations | None = None,
    rating: MatchForecast | None = None,
    football: FootballForecast | None = None,
    tennis_tiers: dict[str, Any] | None = None,
    stats_only: bool = False,
    rating_prices: bool = False,
    marginal_centres_on: bool = False,
    dispersion_table: DispersionTable | None = None,
    per_market_k_on: bool = False,
    game_state: GameStateTable | None = None,
    goals_stretch: GoalsStretchTable | None = None,
    count_stretch: CountStretchTable | None = None,
    player_stretch: PlayerStretchTable | None = None,
    player_share: psh.ShareTable | None = None,
    closeness_stretch: ClosenessStretchTable | None = None,
    venue_prior_on: bool = False,
    set_rating_prices: bool = False,
    sample_corrector: SampleCorrector | None = None,
    tennis_winner_on: bool = False,
    result_config: ResultConfig | None = None,
    incident_pricing: IncidentPricing | None = None,
    set_markets_on: bool = False,
    sheet_margins_on: bool = False,
    card_half_rates: CardHalfRates | None = None,
    card_half_terms_on: bool = False,
    season_phase: SeasonPhaseTable | None = None,
    season_phase_label: str | None = None,
    rating_weights: RatingWeightTable | None = None,
    men_friendly_baseline: FriendlyBaseline | None = None,
    shot_detail_on: bool = False,
    shot_detail_fit: Mapping[str, Any] | None = None,
    result_1x2_dnb: ResultConfig | None = None,
    result_phase: str | None = None,
    score_markets: ResultConfig | None = None,
    aces_opponent_on: bool = False,
    referee_effect: RefereeEffectTable | None = None,
    referee_reads: Mapping[str, RefereeRead] | None = None,
) -> tuple[list[SheetRow], list[tuple[Any, GapReason, str]]]:
    """`stats_only` (bet.sofa.epochs, from 2026-10-05): the price no longer
    enters p_central - no ladder centre, no rating blended with the price, no
    empirical shrink to the rung's price, no handicap centre pulled onto the
    ladder. A rated tennis row is then priced by the sample's estimator, as
    the cache replay the curves were fitted on prices it, and the rating
    (football and tennis) is published beside it as `forecast_p` - shown,
    never calibrated, never a gate. `p_bar` / `required_odds` stay priced:
    06_coupon.json is not the coupon.

    `sample_corrector` (epochs.SAMPLE_OPPONENT_CORRECTION, audit 2026-10-13
    B15 / A5): a football sample is rescaled to a neutral opponent and
    today's domain before its mean, variance and hits
    (bet.sofa.opponent_correction); the row carries the values it priced
    from (`corrected_sample`) for CONFIDENCE's gates. None: the raw sample."""
    rows: list[SheetRow] = []
    skipped: list[tuple[Any, GapReason, str]] = []

    offer, in_play_keys = strip_in_play_prices(offer, fixture)

    k_centre, k_centre_fitted = read_constant(
        engine_constants, "K_CENTRE", UNFITTED_K_CENTRE, fixture.sport
    )
    k_price, k_price_fitted = read_constant(
        engine_constants, "K_PRICE", UNFITTED_K_PRICE
    )
    max_ladder_sigma, sigma_fitted = read_constant(
        engine_constants, "MAX_LADDER_SIGMA", MAX_LADDER_SIGMA
    )
    unfitted = [
        name
        for name, fitted in (
            ("K_CENTRE", k_centre_fitted),
            ("K_PRICE", k_price_fitted),
            ("MAX_LADDER_SIGMA", sigma_fitted),
        )
        if not fitted
    ]

    # 6.4 Cena rynkowa — odvigowanie i środek drabiny
    # Group rungs by (market, subject) to find ladder_centre
    rungs_by_market_subject: dict[tuple[str, str], list[PricedRung]] = {}
    for rung in offer.rungs:
        if is_derived(rung.market):
            continue
        key = (rung.market, rung.subject)
        if key not in rungs_by_market_subject:
            rungs_by_market_subject[key] = []
        rungs_by_market_subject[key].append(rung)

    ladder_centres: dict[tuple[str, str], float | None] = {}
    ladder_sds: dict[tuple[str, str], float | None] = {}
    market_ps: dict[tuple[str, str, float, str], float] = {}

    for key, rung_list in rungs_by_market_subject.items():
        devigged = []
        for r in rung_list:
            probs = devig(r.over_odds, r.under_odds)
            if probs:
                p_over, p_under = probs
                devigged.append((r.line, p_over))
                market_ps[(r.market, r.subject, r.line, "OVER")] = p_over
                market_ps[(r.market, r.subject, r.line, "UNDER")] = p_under

        lc = ladder_centre(devigged)
        ladder_centres[key] = lc
        ladder_sds[key] = ladder_implied_sd(devigged)

    # epochs.FOOTBALL_PLAYER_SHARE: a footballer's centre reads his side's
    # team centre, so the team rows are priced first (the rows are put back
    # in the offer's order after the loop); off, the loop is as it was.
    share_on = player_share is not None and fixture.sport == "football"
    team_centres: dict[tuple[str, str], float] = {}
    # epochs.FOOTBALL_CARD_HALVES_TERMS (empty while off)
    deferred_card_halves: list[PricedRung] = []
    live_card_centres: dict[str, float] = {}
    loop_rungs = (sorted(offer.rungs, key=lambda r: is_player_metric(r.market))
                  if share_on else offer.rungs)

    # Now evaluate each rung and direction
    for rung in loop_rungs:
        # D2: the tennis match winner, priced by the rating alone (no sample).
        # OFFER emits it only under epochs.TENNIS_MATCH_WINNER; off, a stray
        # rung of it is dropped like a market with no sample.
        if rung.market in RATING_ONLY_MARKETS:
            if (tennis_winner_on and fixture.sport == "tennis"
                    and rung.market == MATCH_WON_FOR):
                w_rows, w_skipped = winner_rows(
                    fixture, rung, rating, market_ps, stats_only)
                rows.extend(w_rows)
                skipped.extend(w_skipped)
            # D1: the football double chance (`result_config` is None while
            # epochs.FOOTBALL_RESULT_MARKETS is off - OFFER maps no such rung)
            if (result_config is not None and fixture.sport == "football"
                    and rung.market == DOUBLE_CHANCE):
                dc_rows, dc_skipped = double_chance_rows(
                    fixture, rung, football, result_config, market_ps,
                    stats_only)
                rows.extend(dc_rows)
                skipped.extend(dc_skipped)
            # epochs.FOOTBALL_RESULT_1X2_DNB (None while off - OFFER maps no
            # such rung)
            if (result_1x2_dnb is not None and fixture.sport == "football"
                    and rung.market in RESULT_1X2_DNB_MARKETS):
                r_rows, r_skipped = result_1x2_dnb_rows(
                    fixture, rung, football, result_1x2_dnb, result_phase,
                    market_ps, stats_only)
                rows.extend(r_rows)
                skipped.extend(r_skipped)
            # epochs.FOOTBALL_SCORE_MARKETS (None while off - OFFER maps no
            # such rung)
            if (score_markets is not None and fixture.sport == "football"
                    and rung.market in SCORE_MARKETS):
                sm_rows, sm_skipped = score_market_rows(
                    fixture, rung, football, score_markets, market_ps,
                    stats_only, result_phase)
                rows.extend(sm_rows)
                skipped.extend(sm_skipped)
            # epochs.FOOTBALL_INCIDENT_MARKETS / TENNIS_SET_MARKETS (None /
            # False while off - OFFER maps no such rung)
            if (incident_pricing is not None and fixture.sport == "football"
                    and rung.market in FOOTBALL_INCIDENT_MARKETS):
                i_rows, i_skipped = incident_rows(
                    fixture, rung, football, incident_pricing, market_ps,
                    stats_only)
                rows.extend(i_rows)
                skipped.extend(i_skipped)
            # epochs.FOOTBALL_CARD_HALVES (None while off - OFFER maps no
            # such rung)
            if (card_half_rates is not None and fixture.sport == "football"
                    and rung.market in CARD_HALF_MARKETS
                    and card_half_terms_on):
                # epochs.FOOTBALL_CARD_HALVES_TERMS: priced after the loop,
                # on the full-match cards_points_for rows' live centres
                deferred_card_halves.append(rung)
            elif (card_half_rates is not None and fixture.sport == "football"
                    and rung.market in CARD_HALF_MARKETS):
                c_rows, c_skipped = card_half_rows(
                    fixture, rung, football, card_half_rates, market_ps,
                    stats_only)
                rows.extend(c_rows)
                skipped.extend(c_skipped)
            if (set_markets_on and fixture.sport == "tennis"
                    and rung.market in SET_MARKETS):
                s_rows, s_skipped = set_market_rows(
                    fixture, rung, rating, market_ps, stats_only)
                rows.extend(s_rows)
                skipped.extend(s_skipped)
            continue
        # epochs.SHOT_DETAIL_MARKETS: a footballer's shots by place / body
        # part, priced by bet.sofa.shot_detail's estimator, not the sample
        # centre below (off: OFFER maps no such rung).
        if rung.market in SHOT_DETAIL_METRICS:
            if shot_detail_on and fixture.sport == "football":
                sd_rows, sd_skipped = shot_detail_rows(
                    fixture, rung, samples, shot_detail_fit, market_ps,
                    stats_only)
                rows.extend(sd_rows)
                skipped.extend(sd_skipped)
            else:
                skipped.append((rung, GapReason.NO_SHOT_DETAIL_FIT,
                                "epochs.SHOT_DETAIL_MARKETS is off"))
            continue
        # A derived market is about both sides at once and has no marginal
        # sample to be priced against. derived.py handles it below; falling
        # through here would silently drop it as "metric not in samples".
        if is_derived(rung.market):
            continue
        refused_format = format_bound_refusal(fixture, rung.market)
        if refused_format is not None:
            skipped.append((rung, GapReason.BEST_OF_FIVE_NOT_MODELLED,
                            refused_format))
            continue
        ladder_rungs = rungs_by_market_subject.get((rung.market, rung.subject), [])
        extra_notes: list[str] = []
        if football is not None and (
            football.link_status(rung.market) or football.fixture_link()
        ) == UNLINKED:
            extra_notes.append(
                f"{CROSS_LEAGUE_UNLINKED_NOTE}: the two sides share no league "
                "and their leagues' strengths are unmeasured - the sample and "
                "the rating both describe other leagues"
            )
        # The histories behind this row, for the prior: which leagues the
        # sides play in, and which matches the prior must leave out.
        own_sides: list[list[Observation]] = []
        own_teams: list[int] = []
        own_events: set[int] = set()
        # the raw sample's values when the sample was corrected (B15)
        raw_values: list[float] | None = None
        corrector = (sample_corrector if fixture.sport == "football"
                     else None)
        # the side a footballer's sample was matched in (a player market)
        player_side: str | None = None

        # F54. A player market's subject is a person, and its sample is that
        # person's own appearances — SAMPLES already did the name match
        # against each historical squad, so SHEET looks it up by the exact
        # (market, subject) pair the rung carries and never re-guesses.
        if is_player_metric(rung.market):
            player_sample = samples.players.get(
                player_sample_key(rung.market, rung.subject)
            )
            if player_sample is None:
                skipped.append(
                    (
                        rung,
                        GapReason.NO_ENTITY_FOUND,
                        f"player {rung.subject!r} has no sample for "
                        f"{rung.market}",
                    )
                )
                continue
            obs = player_sample.observations
            player_side = player_sample.side
            # A starter's ninety minutes and a substitute's twelve are not
            # two observations of the same quantity, and nothing else in the
            # row can say so. Reported, never blocking: Superbet pays a
            # player market out on a cameo, so a cameo is a real observation
            # of a real bet — it is just a weaker one, and the operator has
            # to be able to see that before staking.
            minutes = [o.minutes for o in obs if o.minutes is not None]
            if minutes:
                median_minutes = statistics.median(minutes)
                full = sum(1 for m in minutes if m >= 60.0)
                extra_notes.append(
                    f"PLAYER_MINUTES: median {median_minutes:.0f}', "
                    f"{full}/{len(minutes)} appearances of 60'+, "
                    f"played {len(obs)} of {player_sample.squad_matches} "
                    f"sampled matches"
                )
            if player_sample.appearances == "starts":
                extra_notes.append(
                    "PLAYER_STARTS_ONLY: the sample is his starts - Superbet "
                    "voids a player market unless he starts"
                )
            if player_sample.match_rule == "tokens":
                extra_notes.append(
                    f"PLAYER_NAME_TOKENS: Superbet {rung.subject!r} read as "
                    f"Sofascore {player_sample.matched_name!r} by whole name "
                    "tokens (players.match_player_by_tokens)"
                )
            if player_sample.match_rule == "surname":
                extra_notes.append(
                    f"PLAYER_NAME_SURNAME: Superbet {rung.subject!r} read as "
                    f"Sofascore {player_sample.matched_name!r} by surname and "
                    "first-name prefix (players.match_player_by_surname)"
                )
            extra_notes.extend(player_coverage_notes(rung.subject, player_sample))
        # Check if metric exists in samples
        elif rung.market not in samples.metrics:
            continue
        else:
            metric_sample = samples.metrics[rung.market]
            own_events = {
                o.sofascore_event_id
                for lst in (metric_sample.side_a, metric_sample.side_b,
                            metric_sample.h2h)
                for o in lst
            }

            # A _total market pools both histories; one historical match still
            # contributes one observation (L13). A per-side market uses only the
            # side it names.
            if not rung.subject:
                # A match total pools both histories, so it is only a match
                # total when BOTH histories are there. With one side thin the
                # pool is the other side's matches wearing this match's name:
                # on 2026-09-23 UE Sant Andreu - Real Madrid Castilla priced
                # corners OVER 7.5 from 2 Sant Andreu matches (5 and 5, both
                # losing the bet) and 9 of Castilla's. SAMPLES had already
                # written THIN_SAMPLE for it; SHEET only counted the pool.
                thin = [
                    f"{name}={len(side)}"
                    for name, side in (("side_a", metric_sample.side_a),
                                       ("side_b", metric_sample.side_b))
                    if len(side) < config.min_sample
                ]
                if thin:
                    skipped.append(
                        (rung, GapReason.THIN_SAMPLE,
                         f"total pools both sides and {', '.join(thin)} "
                         f"< min_sample={config.min_sample}")
                    )
                    continue
                obs = deduplicate_observations(
                    [metric_sample.side_a, metric_sample.side_b, metric_sample.h2h]
                )
                if corrector is not None:
                    raw_values = [o.value for o in obs]
                    obs = deduplicate_observations(correct_total(
                        corrector, samples.metrics, rung.market,
                        fixture.home_entity_id, fixture.away_entity_id,
                        fixture.competition_id))
                own_sides = [metric_sample.side_a, metric_sample.side_b]
                own_teams = [fixture.home_entity_id, fixture.away_entity_id]
            else:
                side = determine_side(rung.subject, fixture)
                if side is None:
                    skipped.append(
                        (
                            rung,
                            GapReason.NO_MATCHING_EVENT,
                            f"subject {rung.subject!r} matches neither side",
                        )
                    )
                    continue
                obs = (
                    metric_sample.side_a
                    if side == "side_a"
                    else metric_sample.side_b
                )
                own_sides = [obs]
                own_teams = [
                    fixture.home_entity_id if side == "side_a"
                    else fixture.away_entity_id
                ]
                if corrector is not None:
                    raw_values = [o.value for o in obs]
                    obs = corrector.correct(
                        obs, rung.market, own_teams[0],
                        fixture.away_entity_id if side == "side_a"
                        else fixture.home_entity_id,
                        today_competition=fixture.competition_id)

        n = len(obs)
        if n < config.min_sample:
            skipped.append(
                (rung, GapReason.THIN_SAMPLE, f"n={n} < min_sample={config.min_sample}")
            )
            continue

        values = [o.value for o in obs]
        # what CONFIDENCE's gates read: the corrected values, only where one
        # moved (else the raw sample it reads anyway)
        corrected_sample: list[float] | None = None
        if raw_values is not None:
            moved = sum(1 for r, v in zip(raw_values, values, strict=True)
                        if abs(r - v) > 1e-9)
            if moved:
                corrected_sample = [round(v, 4) for v in values]
                extra_notes.append(
                    f"{OPPONENT_NOTE}: {moved} of {len(values)} observations "
                    "rescaled to a neutral opponent and today's domain, "
                    f"sample mean {statistics.mean(raw_values):.2f} -> "
                    f"{statistics.mean(values):.2f}")
        # L1: a sample that is all zeros is usually a provider gap wearing a
        # value, not a market that never happens. Do not price it.
        if all(v == 0.0 for v in values):
            skipped.append(
                (rung, GapReason.ALL_ZERO_SAMPLE, f"all {n} observations are 0.0")
            )
            continue

        # How stale the freshest match behind this row is. Computed here
        # because this is the last place the observations exist as objects;
        # the sheet row is all the coupon ever sees.
        #
        # Per side, and the staler side wins (2026-10-01). A match total pools
        # both histories, so the pool's newest match hid a side that had
        # stopped playing: Bublik's hard-court side was 194 days old, Mensik's
        # was this week's, and every Bublik-Mensik total read "1 day".
        sample_newest_days = stalest_side_newest_days(own_sides, now(), obs)

        mean = statistics.mean(values)
        if n > 1:
            variance = statistics.variance(values)
            sample_sd = statistics.stdev(values)
        else:
            variance = 0.0
            sample_sd = 0.0

        hits = 0  # Not calculated yet, need logic for hits for OVER/UNDER.

        # 6.2 Środek
        # See K_TENNIS_LADDER_CENTRE. For tennis the ladder replaces the league
        # baseline as the shrink target, because tennis has no league baseline
        # worth the name. Where a rung is one-sided and no ladder could be
        # fitted, the old path still runs — there is nothing better to use.
        ladder_target = ladder_centres.get((rung.market, rung.subject))
        # K_TENNIS_LADDER_CENTRE was chosen on centre MAE, "not because the
        # data pins it" (above) - never fitted on probability. A row priced
        # through it says so, like any other constant nobody fitted.
        row_unfitted = list(unfitted)
        referee_info: dict[str, Any] | None = None
        rated: tuple[float, str] | None = None
        if fixture.sport == "tennis" and ladder_target is not None and not stats_only:
            row_unfitted.append("K_TENNIS_LADDER_CENTRE")
            w_c = n / (n + K_TENNIS_LADDER_CENTRE)
            centre = w_c * mean + (1 - w_c) * ladder_target
        else:
            centre, centre_notes, centre_unfitted, rated = sample_centre(
                fixture=fixture,
                market=rung.market,
                subject=rung.subject,
                n=n,
                mean=mean,
                own_sides=own_sides,
                own_events=own_events,
                own_teams=own_teams,
                baselines=baselines,
                day_obs=day_obs,
                football=football,
                tennis_tiers=tennis_tiers,
                engine_constants=engine_constants,
                k_centre=k_centre,
                per_market_k_on=per_market_k_on,
                rating_weights=rating_weights,
                men_friendly_baseline=men_friendly_baseline,
            )
            extra_notes.extend(centre_notes)
            row_unfitted.extend(centre_unfitted)
            side_key = determine_side(rung.subject, fixture) if rung.subject else None
            # epochs.FOOTBALL_VENUE_PRIOR (audit 2026-10-13 B2): a sample-only
            # side centre reads the league's home / away rate as a multiplier
            # - the sample is never split by venue.
            if (venue_prior_on and football is not None and rated is None
                    and side_key is not None
                    and rung.market in VENUE_PRIOR_MARKETS):
                v_mult = football.venue_multiplier(
                    rung.market, side_key, (o.venue for o in obs))
                if v_mult is not None:
                    v_before = centre
                    centre *= v_mult
                    extra_notes.append(
                        f"VENUE_PRIOR: centre {centre:.2f} = {v_before:.2f} x "
                        f"{v_mult:.3f} (league rate at today's venue over the "
                        "sample's venues; epochs.FOOTBALL_VENUE_PRIOR)")
            # epochs.GAME_STATE (audit 2026-10-13 B1): the favourite /
            # outsider term, exp(beta x the side's expected goal difference).
            if game_state is not None and football is not None and side_key:
                g_sup = football.supremacy(side_key)
                g_mult = game_state.multiplier(rung.market, g_sup)
                if g_mult is not None and g_sup is not None:
                    g_before = centre
                    centre *= g_mult
                    row_unfitted.extend(GAME_STATE_UNFITTED)
                    extra_notes.append(
                        f"GAME_STATE: centre {centre:.2f} = {g_before:.2f} x "
                        f"{g_mult:.3f} (expected goal difference {g_sup:+.2f}, "
                        f"beta {game_state.betas[rung.market]:+.4f}; "
                        "epochs.GAME_STATE)")
            # epochs.FOOTBALL_COUNT_STRETCH: a count centre outside
            # GAME_STATE x the supremacy stretch (side: exp(beta x s [+ beta2
            # x s^2]); total: exp(g1 |s| + g2 s^2), s the home side's), after
            # GAME_STATE and the venue prior, blended or sample-only.
            if count_stretch is not None and football is not None:
                cs_total = count_stretch_is_total(rung.market)
                cs_sup = side_or_home_supremacy(football, side_key, cs_total)
                cs_mult = count_stretch.multiplier(rung.market, cs_sup)
                if cs_mult is not None and cs_sup is not None:
                    cs_before = centre
                    centre *= cs_mult
                    row_unfitted.extend(COUNT_STRETCH_UNFITTED)
                    extra_notes.append(
                        f"COUNT_STRETCH: centre {centre:.2f} = {cs_before:.2f} x "
                        f"{cs_mult:.3f} (expected goal difference {cs_sup:+.2f}"
                        f"{' (home)' if cs_total else ''}, "
                        f"{count_stretch.describe(rung.market)}; "
                        "epochs.FOOTBALL_COUNT_STRETCH)")
            # epochs.FOOTBALL_REFEREE: a cards / fouls centre x the fixture
            # referee's as-of shrunk ratio ** beta (bet.sofa.referees), after
            # GAME_STATE and the count stretch; no referee named (or none
            # with a record in the history) leaves the centre as it is and
            # says so on the row (referee_read.status).
            if (referee_effect is not None and football is not None
                    and fixture.sport == "football"):
                fam = referee_terms.family_of(rung.market)
                applied = referee_effect.apply(
                    rung.market,
                    (referee_reads or {}).get(fam) if fam is not None else None)
                if applied is not None:
                    r_mult, referee_info = applied
                    if referee_info["status"] == "APPLIED":
                        r_before = centre
                        centre *= r_mult
                        row_unfitted.extend(REFEREE_UNFITTED)
                        extra_notes.append(
                            f"REFEREE: centre {centre:.2f} = {r_before:.2f} x "
                            f"{r_mult:.3f} (referee {referee_info['referee_id']}, "
                            f"{referee_info['n']} matches, ratio "
                            f"{referee_info['ratio']:.3f}; epochs.FOOTBALL_REFEREE)")
            # epochs.FOOTBALL_CLOSENESS_STRETCH: a count centre x exp(g1 |s|
            # + g2 s^2), s the home side's (|s|, s^2 even), after GAME_STATE
            # and the count stretch, blended or sample-only.
            if closeness_stretch is not None and football is not None:
                cl_sup = closeness_supremacy(football)
                cl_mult = closeness_stretch.multiplier(rung.market, cl_sup)
                if cl_mult is not None and cl_sup is not None:
                    cl_before = centre
                    centre *= cl_mult
                    row_unfitted.extend(CLOSENESS_UNFITTED)
                    extra_notes.append(
                        f"CLOSENESS_STRETCH: centre {centre:.2f} = "
                        f"{cl_before:.2f} x {cl_mult:.3f} (expected goal "
                        f"difference {cl_sup:+.2f} (home), "
                        f"{closeness_stretch.describe(rung.market)}; "
                        "epochs.FOOTBALL_CLOSENESS_STRETCH)")
            # epochs.FOOTBALL_GOALS_STRETCH: a goals centre x the supremacy
            # stretch (side: exp(beta x s); total: exp(g1 |s| + g2 s^2), s
            # the home side's), on the same blended centre; a market with
            # per-phase coefficients reads the fixture's season phase.
            if goals_stretch is not None and football is not None:
                st_sup = stretch_supremacy(football, rung.market, side_key)
                st_mult = goals_stretch.multiplier(
                    rung.market, st_sup, season_phase_label)
                if st_mult is not None and st_sup is not None:
                    st_before = centre
                    centre *= st_mult
                    row_unfitted.extend(GOALS_STRETCH_UNFITTED)
                    extra_notes.append(
                        f"GOALS_STRETCH: centre {centre:.2f} = {st_before:.2f} x "
                        f"{st_mult:.3f} (expected goal difference {st_sup:+.2f}"
                        f"{' (home)' if side_key is None else ''}, "
                        f"{goals_stretch.describe(rung.market, season_phase_label)}; "
                        "epochs.FOOTBALL_GOALS_STRETCH)")
            # epochs.FOOTBALL_PLAYER_SHARE: his shrunk share of his side's
            # team centre in place of his own mean (and of the stretch below,
            # which the team centre's game state already carries).
            shared = False
            if share_on and player_share is not None and player_side is not None:
                share_cell = player_share.cell(rung.market)
                if share_cell is not None:
                    s_centre, s_note = player_share_centre(
                        rung.market, rung.subject, player_side, samples,
                        share_cell, team_centres)
                    extra_notes.append(s_note)
                    if s_centre is not None:
                        centre = s_centre
                        shared = True
            # epochs.FOOTBALL_PLAYER_STRETCH: a footballer's shots centre x
            # exp(beta x s), s his own side's expected goal difference.
            if (player_stretch is not None and football is not None
                    and player_side is not None and not shared):
                ps_sup = football.supremacy(player_side)
                ps_mult = player_stretch.multiplier(rung.market, ps_sup)
                if ps_mult is not None and ps_sup is not None:
                    ps_before = centre
                    centre *= ps_mult
                    row_unfitted.extend(PLAYER_STRETCH_UNFITTED)
                    extra_notes.append(
                        f"PLAYER_STRETCH: centre {centre:.2f} = {ps_before:.2f} x "
                        f"{ps_mult:.3f} (his side's expected goal difference "
                        f"{ps_sup:+.2f}, {player_stretch.describe(rung.market)}; "
                        "epochs.FOOTBALL_PLAYER_STRETCH)")
            # epochs.SEASON_PHASE (audit 2026-10-13 C1): the goals centre x
            # exp(c[market][phase]), the phase as of the day's cut.
            if season_phase is not None and football is not None:
                p_before = centre
                centre, p_mult = apply_season_phase(
                    centre, rung.market, season_phase_label, season_phase)
                if p_mult is not None:
                    row_unfitted.extend(SEASON_PHASE_UNFITTED)
                    extra_notes.append(
                        f"SEASON_PHASE: centre {centre:.2f} = {p_before:.2f} x "
                        f"{p_mult:.3f} (phase {season_phase_label}; "
                        "epochs.SEASON_PHASE)")
            # epochs.TENNIS_ACES_OPPONENT: an aces centre x today's
            # returner's factor (bet.sofa.tennis_aces_opponent)
            if (aces_opponent_on and fixture.sport == "tennis"
                    and rung.market in aces_opp.ACES_MARKETS):
                a_mult, a_detail = tennis_aces_correction(
                    fixture, samples, rung.market, side_key, tennis_tiers,
                    k_centre)
                if a_mult is None:
                    extra_notes.append(a_detail)
                else:
                    a_before = centre
                    centre *= a_mult
                    extra_notes.append(
                        aces_opp.describe(a_mult, a_before, centre, a_detail))

        # epochs.FOOTBALL_PLAYER_SHARE: the side's team centre, for its
        # players' rows (priced after every team row while the switch is on)
        if (share_on and rung.subject and rung.market in psh.TEAM_METRIC_KEYS):
            t_side = determine_side(rung.subject, fixture)
            if t_side in ("side_a", "side_b"):
                team_centres.setdefault((rung.market, t_side), centre)
        # epochs.FOOTBALL_CARD_HALVES_TERMS: the side's full-match live
        # card-points centre, for its card-half rows (priced after the loop)
        if (card_half_terms_on and fixture.sport == "football" and rung.subject
                and rung.market == "cards_points_for"):
            c_side = determine_side(rung.subject, fixture)
            if c_side in ("side_a", "side_b"):
                live_card_centres.setdefault(c_side, centre)

        # The spread moves with the centre (football counts) - see
        # engine.sheet_predictive_sd, which the cache replay shares.
        # epochs.COUNT_DISPERSION: the history's alpha for (market,
        # competition) instead of the sample's variance (None = off, or a
        # market / sport the table does not cover).
        dispersion = (
            dispersion_table.read(
                fixture.sport, rung.market, fixture.competition_id)
            if dispersion_table is not None else None
        )
        pred_sd = sheet_predictive_sd(
            rung.market, fixture.sport, mean, variance, n, centre, dispersion
        )

        # The rating forecast replaces the sample's estimate wherever it has
        # one (see bet.sofa.tennis_rating). The sample still decides whether
        # the row exists at all and is still published beside it.
        rating_side = (
            determine_side(rung.subject, fixture) if rung.subject else None
        )

        for direction in ("OVER", "UNDER"):
            # A rung quoted on one side only still gets a row: the forecast is
            # worth recording even where it cannot be bet (A6). It lands as
            # NO_PRICE, never as a verdict against a price that does not exist.
            offered_odds = rung.over_odds if direction == "OVER" else rung.under_odds

            boundary = winning_boundary(rung.line, direction)

            # Count hits against the *winning boundary*, not the raw line, so
            # a push is neither a hit nor a miss. Counting it as a hit is how a
            # sample with pushes looks like a sample with zero misses and takes
            # the Laplace cap it has not earned.
            if direction == "OVER":
                hits = sum(1 for v in values if v > boundary)
            else:
                hits = sum(1 for v in values if v < boundary)

            # For a variable with two possible values the normal CDF is the
            # wrong model whatever its width, so the sample's own frequency is
            # what gets used (F30). Everything else keeps the CDF.
            p_rating = (
                rating.probability(rung.market, rating_side, rung.line, direction)
                if rating is not None
                else None
            )
            # epochs.TENNIS_SET_RATING_PRICES (audit 2026-10-13 B5): the
            # per-set games and sets_total read off the neighbours too.
            set_rated = (
                set_rating_prices and rating is not None
                and rung.market in SET_RATING_PRICED_MARKETS
            )
            if set_rated and rating is not None:
                p_rating = rating.read(
                    rung.market, rating_side, rung.line, direction)
            # The second number (K11): the rating's own forecast, never
            # blended with the price. Written only in the stats-only epoch.
            forecast_p: float | None = None
            forecast_source: str | None = None
            p_rating_gt: float | None = None  # games_total: mixed into the NB below
            if stats_only:
                if p_rating is not None:
                    forecast_p, forecast_source = p_rating, "tennis_rating"
                elif rated is not None:
                    forecast_p = football_forecast_p(
                        rung.market, fixture.sport, values, mean, variance, n,
                        rated[0], boundary, direction, dispersion,
                    )
                    forecast_source = (
                        "football_rating" if forecast_p is not None else None)
                # The rating no longer prices the row (K1): its estimator is
                # the sample's, as in the cache replay - except, from
                # epochs.tennis_rating_prices, the families measured out of
                # sample to be better read off the neighbours.
                if rating_prices and fixture.sport == "tennis" and p_rating is not None:
                    if rung.market == "games_total":
                        p_rating_gt, p_rating = p_rating, None
                    elif not (
                        rung.market in RATING_PRICED_MARKETS
                        and rating_side in ("side_a", "side_b")
                    ) and not set_rated:
                        p_rating = None
                else:
                    p_rating = None
            # A tennis p already pulled onto Superbet's price (the rating blend
            # with a price, the empirical shrink to the rung's price) is not
            # the estimator the reliability curve was fitted on. See
            # price_anchored below.
            price_anchored = False
            anchor_price: float | None = None
            if p_rating is not None:
                anchor_price = (
                    None if stats_only else market_ps.get(
                        (rung.market, rung.subject, rung.line, direction))
                )
                p_raw = blend_with_price(p_rating, anchor_price)
                price_anchored = fixture.sport == "tennis" and anchor_price is not None
            elif uses_empirical_frequency(rung.market):
                # Counted on the SHRUNK centre, not on the raw sample. The
                # shrink above is not advisory: a note that says "pulled to
                # 5.23" beside a number computed at 3.40 describes a row the
                # stage did not price (F55).
                rung_price = market_ps.get(
                    (rung.market, rung.subject, rung.line, direction)
                )
                if fixture.sport == "tennis" and not stats_only and (
                    rung_price is not None or ladder_target is not None
                ):
                    # The ladder shrink in probability space, not on the
                    # centre: the ladder centre is a median, and moving a
                    # bimodal sample onto it overshot both the sample and the
                    # price (see p_empirical_shrunk_to_price). Keyed on the
                    # RUNG's price, not on a fitted ladder: a one-rung ladder
                    # has no centre and still has a price (476 sets_total rows
                    # on 2026-09-23 went round this path otherwise).
                    p_raw = p_empirical_shrunk_to_price(
                        hits, n, rung_price, K_TENNIS_LADDER_CENTRE
                    )
                    price_anchored = rung_price is not None
                else:
                    p_raw = p_empirical_centred_raw(
                        values, boundary, direction, centre - mean
                    )
            else:
                # A count is right-skewed and the normal CDF is not. See
                # NEGATIVE_BINOMIAL_METRICS: symmetric tails put +4.7 pp on
                # every OVER rung, which is what makes a coupon come out
                # 88.8% OVER. engine.sheet_count_p_raw picks the NB or the
                # support-floored normal; the cache replay calls the same.
                p_raw = sheet_count_p_raw(
                    rung.market, centre, pred_sd, boundary, direction,
                    dispersion,
                )

            if p_rating_gt is not None:
                p_raw = (
                    W_GAMES_TOTAL_RATING * p_rating_gt
                    + (1.0 - W_GAMES_TOTAL_RATING) * p_raw
                )

            # F35: a rung whose estimate falls outside the clamp band is not a
            # rung the model has an opinion about, and the clamped value is not
            # a cheaper opinion — it is a floor of 0.05 wearing the costume of
            # a probability. Priced, it says a team scoring seven goals happens
            # once in twenty matches, which at odds of 150 reads as a surplus
            # of +128 and wins the top coupon slot on merit it does not have.
            # Refuse the rung instead, the way an all-zero sample is refused.
            # F35 applies to the SAMPLE, not to a number the price has
            # already pulled inside the band: an 18/18 sample shrunk 75% toward
            # the price reads 0.72 and would be priced as though the sample had
            # said anything at this line.
            if (
                p_rating is None
                and uses_empirical_frequency(rung.market)
                and outside_model_resolution(hits / n)
            ):
                skipped.append(
                    (
                        rung,
                        GapReason.OUTSIDE_MODEL_RESOLUTION,
                        f"sample {hits}/{n} for {direction} is outside "
                        f"[{P_FLOOR}, {P_CEILING}]",
                    )
                )
                continue
            if outside_model_resolution(p_raw):
                skipped.append(
                    (
                        rung,
                        GapReason.OUTSIDE_MODEL_RESOLUTION,
                        f"p={p_raw:.4g} for {direction} is outside "
                        f"[{P_FLOOR}, {P_CEILING}]",
                    )
                )
                continue

            p_cent = p_raw

            # Deliberately without a support floor, unlike p_central above.
            # calculate_p_low shifts the centre 1.96 SE *against* the bet, and
            # that shifted centre is an artificial device, not a mean the
            # quantity could have. Conditioning it on the support is not
            # meaningful and measurably backfires: at centre 0.3, sd 2.5,
            # n = 5, the OVER shift lands at -1.89, and renormalising a
            # distribution centred below its own support inflates the upper
            # tail from 0.191 to 0.626. p_low is only ever used to cap p
            # downward (see apply_caps), so no floor is the strictly more
            # protective choice, and it keeps this agreeing with settle.py.
            p_low_val = calculate_p_low(centre, sample_sd, n, boundary, direction)

            m_p = market_ps.get((rung.market, rung.subject, rung.line, direction))

            # sofa_market_reliability.json was fitted on settled rows of every
            # estimator, mostly sample-based ones, and a tennis p already
            # pulled onto the price is calibrated without it. Measured
            # 2026-10-02 on 50,434 settled priced tennis rows 09-24..10-01
            # within 0.15 of the price: claimed 0.751 / realised 0.759 at
            # 0.7-0.8, 0.849 / 0.850 at 0.8-0.9; the correction moved Brier
            # +0.00028 (event-id halves +0.00016 / +0.00040), worse in the
            # 0.8-1.0 buckets on both halves. Sample-based tennis rows keep
            # it: they are the overconfident ones (claimed 0.749, realised
            # 0.614, n=500) and it helps them on both halves.
            corr = row_correction(
                reliability, rung.market, p_cent, direction, price_anchored
            )

            force_weight_0 = False
            for veto in vetoes:
                if veto.sofascore_event_id != fixture.sofascore_event_id:
                    continue
                if veto.market is not None and veto.market != rung.market:
                    continue
                if veto.subject is not None and veto.subject != rung.subject:
                    continue
                if veto.line is not None and veto.line != rung.line:
                    continue
                if veto.direction is not None and veto.direction != direction:
                    continue
                if veto.reason_class == "SAMPLE_UNINFORMATIVE":
                    force_weight_0 = True
                    break

            p_bar, bar_reason = bar_probability(
                p_central=p_cent,
                hits=hits,
                n=n,
                p_low_val=p_low_val,
                market_p=m_p,
                k_price=k_price,
                correction=corr,
                force_weight_0=force_weight_0,
            )

            req_odds = get_required_odds(
                p_bar, "LEAN"
            )  # Hardcoded LEAN tier margin for E8

            lc = ladder_centres.get((rung.market, rung.subject))
            market_sd = ladder_sds.get((rung.market, rung.subject))
            spread_ratio = (
                pred_sd / market_sd
                if market_sd is not None and market_sd > 0
                else None
            )
            l_sigma = None
            if lc is not None and sample_sd > 0:
                l_sigma = abs(centre - lc) / sample_sd

            # Round FIRST, then subtract. The artifact publishes p_central and
            # market_p to 4 places; if edge is computed from the unrounded
            # values, a reader who subtracts the two printed numbers gets a
            # different answer than the field says. A report has to agree with
            # its own arithmetic (L27).
            p_cent_out = round(p_cent, 4)
            m_p_out = round(m_p, 4) if m_p is not None else None
            req_odds_out = round(req_odds, 4)

            edge = round(p_cent_out - m_p_out, 4) if m_p_out is not None else None
            surplus = (
                round(offered_odds - req_odds_out, 4)
                if offered_odds is not None
                else None
            )

            notes: list[str] = list(extra_notes)
            if (rung.market, rung.subject, rung.line) in in_play_keys:
                notes.append(
                    "IN_PLAY_PRICE_DROPPED: this rung was fetched at or after "
                    "kickoff; its odds are not a pre-match price"
                )
            if p_rating is not None and rating is not None:
                # the price the rating was blended with (none in the
                # stats-only epoch: there p_central is the rating alone)
                notes.append(rating_note(
                    rating, rating_side, p_rating, anchor_price,
                    rule=(None if not stats_only
                          else "epochs.TENNIS_SET_RATING_PRICES" if set_rated
                          else "epochs.TENNIS_RATING_PRICES")))
                if "W_TENNIS_RATING" not in row_unfitted:
                    row_unfitted = [*row_unfitted, "W_TENNIS_RATING"]
            tennis_price_shrink = (
                p_rating is None
                and not stats_only
                and fixture.sport == "tennis"
                and uses_empirical_frequency(rung.market)
                and (m_p is not None or ladder_target is not None)
            )
            # The constant is used only when there is a price to shrink toward.
            if (
                tennis_price_shrink
                and m_p is not None
                and "K_TENNIS_LADDER_CENTRE" not in row_unfitted
            ):
                row_unfitted = [*row_unfitted, "K_TENNIS_LADDER_CENTRE"]
            if tennis_price_shrink:
                # The number was shrunk in probability space, so that is what
                # the note says - a note describing a centre the row was not
                # priced from is the F55 mistake.
                w_p = n / (n + K_TENNIS_LADDER_CENTRE)
                notes.append(
                    f"P_SHRUNK_TO_PRICE: sample {hits}/{n} = {hits / n:.3f}, "
                    + (
                        f"market_p {m_p:.4f}, weight {w_p:.3f} "
                        if m_p is not None
                        else "no price on this rung, raw frequency "
                    )
                    + f"(K_TENNIS_LADDER_CENTRE={K_TENNIS_LADDER_CENTRE:g})"
                )
            elif (
                p_rating is None
                and not stats_only
                and fixture.sport == "tennis"
                and ladder_target is not None
                and abs(centre - mean) > 1e-9
            ):
                notes.append(
                    f"CENTRE_SHRUNK_TO_LADDER: sample {mean:.2f} pulled to "
                    f"{centre:.2f} (ladder {ladder_target:.2f}, "
                    f"K_TENNIS_LADDER_CENTRE={K_TENNIS_LADDER_CENTRE:g}, n={n})"
                )
            verdict: Literal["VALUE", "LEAN", "BELOW_BAR", "NO_PRICE", "BLOCKED"] = (
                "BELOW_BAR"
            )
            if offered_odds is None:
                verdict = "NO_PRICE"
            elif surplus is not None and surplus > 0:
                # §3.2/§6.6: with one provider the ladder gate is the ONLY
                # external check a live row ever gets. No measurement means no
                # check, so the row cannot be VALUE — it is a LEAN with the
                # reason recorded. Letting an unmeasurable row through would
                # promote exactly the thin ladders (one rung, or a ladder
                # entirely on one side of 0.5) that carry the least information.
                if m_p is None:
                    # The same rule as the ladder gate below, for the same
                    # reason. `market_p` is what `bar_probability` shrinks the
                    # sample toward and what `edge` is measured against; with
                    # no complement price quoted there is nothing to devig, so
                    # p_bar falls back to the raw model at w=1 and
                    # `bar_is_unreachable` cannot fire either. The row is then
                    # selected by the model alone, unchecked by any price —
                    # and the model is the thing the settled record says loses.
                    # On 2026-09-19 those 71 rows carried a median surplus of
                    # 4.95 against 0.24 for the anchored ones, at median odds
                    # of 12.0 against 3.10. That is not an edge, it is the
                    # absence of a check.
                    verdict = "LEAN"
                    notes.append(
                        "NO_PRICE_ANCHOR: only one side of this rung is "
                        "quoted, so market_p could not be devigged and the "
                        "bar is unchecked by any price; VALUE withheld"
                    )
                elif l_sigma is None:
                    verdict = "LEAN"
                    notes.append(
                        "NO_LADDER_CHECK: ladder_sigma unmeasurable "
                        f"(rungs={len(ladder_rungs)}, "
                        f"sample_sd={sample_sd:.4f}); VALUE withheld"
                    )
                elif l_sigma > max_ladder_sigma:
                    verdict = "LEAN"
                    notes.append(
                        f"LADDER_DISAGREES: ladder_sigma {l_sigma:.3f} > "
                        f"{max_ladder_sigma:.3f}"
                    )
                elif spread_ratio is not None and not (
                    MIN_SPREAD_RATIO <= spread_ratio <= MAX_SPREAD_RATIO
                ):
                    # The centre agrees and the width does not. A distribution
                    # of the right centre and the wrong spread is wrong at
                    # every rung at once, in the direction that makes the bar
                    # easiest to beat.
                    verdict = "LEAN"
                    notes.append(
                        f"LADDER_SPREAD_DISAGREES: our predictive sd is "
                        f"{spread_ratio:.2f}x the market's implied spread "
                        f"(band {MIN_SPREAD_RATIO}-{MAX_SPREAD_RATIO}); "
                        "VALUE withheld"
                    )
                else:
                    verdict = "VALUE"

            if verdict == "BELOW_BAR" and bar_is_unreachable(
                offered_odds, m_p_out, n, k_price=k_price
            ):
                # Not "this row missed the bar" but "no sample could have
                # cleared it at this price". The two used to read the same,
                # and 1,578 of the 2026-09-18 sheet's rows were the second
                # kind — every short-priced favourite on the board (F52).
                sample_weight = n / (n + k_price)
                best_p_bar = (
                    sample_weight * P_CEILING
                    + (1.0 - sample_weight) * cast(float, m_p_out)
                )
                notes.append(
                    "UNREACHABLE_BAR: no sample could clear this price "
                    f"(market_p {m_p_out:.4f}, best possible required odds "
                    f"{get_required_odds(best_p_bar):.4f} > "
                    f"offered {offered_odds:.2f})"
                )

            if row_unfitted:
                notes.append(f"UNFITTED_CONSTANTS: {', '.join(row_unfitted)}")

            if edge is not None and abs(edge) >= 0.15:
                # L16: a price disagreement annotates, it never demotes.
                notes.append(f"PRICE_GAP: edge {edge:+.3f} vs market")

            row = SheetRow(
                sofascore_event_id=fixture.sofascore_event_id,
                sport=fixture.sport,
                market=rung.market,
                subject=rung.subject,
                line=rung.line,
                direction=direction,
                sample_size=n,
                sample_mean=round(mean, 4),
                sample_sd=round(sample_sd, 4),
                centre=round(centre, 4),
                p_central=p_cent_out,
                market_p=m_p_out,
                ladder_centre=round(lc, 4) if lc is not None else None,
                ladder_sigma=round(l_sigma, 4) if l_sigma is not None else None,
                p_bar=round(p_bar, 4),
                bar_reason=bar_reason,
                calibration_correction=round(corr, 4),
                sample_newest_days=sample_newest_days,
                # A rated row's claim is the rating, not the sample's
                # frequency; CONFIDENCE reads this field as the claim.
                sample_frequency=(
                    round(hits / n, 4)
                    if uses_empirical_frequency(rung.market) and p_rating is None
                    else None
                ),
                required_odds=req_odds_out,
                offered_odds=offered_odds,
                edge=edge,
                surplus=surplus,
                verdict=verdict,
                notes=notes,
                epoch=STATS_ONLY if stats_only else None,
                forecast_p=(
                    round(forecast_p, 4) if forecast_p is not None else None
                ),
                forecast_source=forecast_source,
                corrected_sample=corrected_sample,
                referee_read=referee_info,
            )
            rows.append(row)

    if deferred_card_halves and card_half_rates is not None:
        mults = card_half_term_mults(football, game_state, referee_effect,
                                     referee_reads, closeness_stretch)
        for rung in deferred_card_halves:
            c_rows, c_skipped = card_half_rows(
                fixture, rung, football, card_half_rates, market_ps,
                stats_only, live_card_centres, mults)
            rows.extend(c_rows)
            skipped.extend(c_skipped)

    if share_on or deferred_card_halves:
        # back in the offer's order (a stable sort: OVER before UNDER)
        order: dict[tuple[str, str, float], int] = {}
        for i, r in enumerate(offer.rungs):
            order.setdefault((r.market, r.subject, r.line), i)
        rows.sort(key=lambda r: order.get((r.market, r.subject, r.line), len(order)))
        rung_index = {id(r): i for i, r in enumerate(offer.rungs)}
        skipped.sort(key=lambda s: rung_index.get(id(s[0]), len(rung_index)))

    marginal_centres: dict[tuple[str, str], float] | None = None
    if fixture.sport == "football" and marginal_centres_on:
        marginal_centres = {}
        for marginal in rows:
            if (marginal.market in DERIVED_MARGINAL_CENTRES_METRICS
                    and marginal.subject and marginal.centre is not None):
                msd = determine_side(marginal.subject, fixture)
                if msd in ("side_a", "side_b"):
                    marginal_centres.setdefault((marginal.market, msd), marginal.centre)
    side_metric_notes: dict[str, list[str]] | None = None
    side_metric_unfitted: dict[str, list[str]] | None = None
    if (fixture.sport == "football" and sheet_margins_on
            and marginal_centres is not None):
        side_metric_notes, side_metric_unfitted = sheet_derived_margins(
            fixture, samples, offer, marginal_centres,
            baselines=baselines, day_obs=day_obs, football=football,
            engine_constants=engine_constants, k_centre=k_centre,
            per_market_k_on=per_market_k_on, min_sample=config.min_sample,
            rating_weights=rating_weights,
            men_friendly_baseline=men_friendly_baseline,
        )
    derived_rows, derived_skipped = price_derived_rungs(
        fixture=fixture,
        samples=samples,
        offer=offer,
        correlations=side_correlations or {},
        vetoes=vetoes,
        min_sample=config.min_sample,
        max_ladder_sigma=max_ladder_sigma,
        k_price=k_price,
        unfitted=unfitted,
        correction_for=cast(
            "Callable[[str, float, str], float]",
            lambda market, p, direction="": get_calibration_correction(
                reliability, market, p, direction
            ),
        ),
        rating_p=(
            rating.probability if rating is not None and not stats_only
            else _stats_only_rating_p(rating)
            if rating is not None and rating_prices else None
        ),
        rating_note=(
            partial(rating_note, rating)
            if rating is not None and not stats_only else None
        ),
        stats_only=stats_only,
        marginal_centres=marginal_centres,
        dispersion_table=dispersion_table,
        side_metric_notes=side_metric_notes,
        side_metric_unfitted=side_metric_unfitted,
    )
    if stats_only:
        derived_rows = [
            r.model_copy(update={"epoch": STATS_ONLY}) for r in derived_rows
        ]
    rows.extend(derived_rows)
    skipped.extend(derived_skipped)

    for rung, reason, detail in skipped:
        logger.info(
            "sheet: no row for event=%s market=%s subject=%s line=%s (%s: %s)",
            fixture.sofascore_event_id,
            rung.market,
            rung.subject,
            rung.line,
            reason.value,
            detail,
        )

    return rows, skipped


def main() -> int:
    """A configuration error (a rule marker the config cannot honour: the K /
    dispersion pair, a malformed dispersion file, a V5 rating config without
    its tier_start) is FAILED (rc 2), never PARTIAL: run_pipeline and
    rebuild_day continue on 1 and CONFIDENCE would read the old sheet."""
    try:
        return _main()
    except (ValueError, OSError) as exc:
        print(f"SHEET: configuration error: {exc}", file=sys.stderr)
        return 2


def _main() -> int:
    # Every request underneath this call is this stage's cost (F22).
    set_stage("SHEET")
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD", default=now().strftime("%Y-%m-%d"))
    parser.add_argument(
        "--event-ids", default=None,
        help="comma-separated Sofascore event ids: price only these fixtures and "
        "merge their rows into 05_sheet.json, every other fixture's rows kept as "
        "they were (the late RESOLVE pass, bet.sofa.late_resolve); the day's "
        "context (league observations, ratings) still reads every fixture")
    args = parser.parse_args()
    only_ids = parse_event_ids(args.event_ids)

    config = SofaConfig.from_env()
    _frozen = frozen_clock_refusal(config.runs_dir)
    if _frozen:
        print(_frozen, file=sys.stderr)
        return 2

    runs_dir = Path(config.runs_dir) / args.date
    fixtures_path = runs_dir / "02_fixtures.json"
    samples_path = runs_dir / "03_samples.json"
    offer_path = runs_dir / "04_offer.json"
    refusal = incomplete_reason(fixtures_path)
    if refusal:
        print(refusal, file=sys.stderr)
        return 2

    try:
        fixtures_data = read_file(fixtures_path)
        samples_data = read_file(samples_path)
        offer_data = read_file(offer_path)

        fixtures = RootModel[list[Fixture]].model_validate_json(fixtures_data).root
        samples = RootModel[list[FixtureSamples]].model_validate_json(samples_data).root
        offers = RootModel[list[FixtureOffer]].model_validate_json(offer_data).root

    except Exception as e:
        print(f"Error loading inputs: {e}", file=sys.stderr)
        sys.exit(2)

    fixtures_by_id = {f.sofascore_event_id: f for f in fixtures}
    samples_by_id = {s.sofascore_event_id: s for s in samples}

    vetoes = []
    vetoes_path = runs_dir / "vetoes.json"
    if vetoes_path.exists():
        vetoes_data = read_file(vetoes_path)
        if vetoes_data:
            vetoes = RootModel[list[Veto]].model_validate_json(vetoes_data).root

    # epochs.CARDS_CORRELATION: the cards joints' sides at the measured
    # residual (the number lives behind the switch, not in the config file)
    cards_correlation_on = (
        stats_only_epoch(args.date) and epochs.cards_correlation_enabled(args.date))
    side_correlations = load_side_correlations(
        cards_correlation=cards_correlation_on)
    baselines = load_baselines(config)
    tennis_tiers = load_tennis_tier_baselines(config)
    day_obs = day_league_observations(fixtures, samples)
    reliability = load_reliability(config)
    engine_constants = load_engine_constants(config)
    # epochs.TENNIS_SCOPED_TABLE: the day being built and the build clock
    tennis_scoped = (stats_only_epoch(args.date)
                     and epochs.tennis_scoped_table_enabled(args.date))
    tennis_model = (
        load_tennis_rating(config, fixtures, args.date, scoped=tennis_scoped)
        if os.environ.get("SOFA_TENNIS_RATING", "1") != "0"
        else None
    )
    rated_fixtures = 0
    # the link rule of the day being built (epochs.link_shared_league)
    link_shared = epochs.link_shared_league(args.date)
    football_book: RatingBook | None = None
    football_history: list[Any] | None = None
    # epochs.SEASON_PHASE (audit 2026-10-13 C1): read only while on
    season_phase_on = (stats_only_epoch(args.date)
                       and epochs.season_phase_enabled(args.date))
    season_index: SeasonPhaseIndex | None = None
    referee_reads_by_event: dict[int, dict[str, RefereeRead]] = {}
    cup_strength_on = (stats_only_epoch(args.date)
                       and epochs.football_cup_strength(args.date))
    if os.environ.get("SOFA_FOOTBALL_RATING", "1") != "0" and any(
        f.sport == "football" for f in fixtures
    ):
        cut = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=UTC)
        football_history = load_football_history(
            config.db_path, Path(config.db_path).parent / "cache")
        # also the as-of phase of a 1X2 / DNB row (epochs.FOOTBALL_RESULT_1X2_DNB)
        # and of a score-market row (epochs.FOOTBALL_SCORE_MARKETS)
        # and of a goals-stretch row (epochs.FOOTBALL_GOALS_STRETCH: a
        # market's coefficients may be per phase)
        if season_phase_on or (stats_only_epoch(args.date) and (
                epochs.football_result_1x2_dnb(args.date)
                or epochs.football_score_markets(args.date)
                or epochs.football_goals_stretch(args.date))):
            season_index = index_from_history(
                football_history, int(cut.timestamp()))
        if (stats_only_epoch(args.date)
                and epochs.football_referee(args.date)):
            # the fixture's referee (stored label or the cached /event
            # RESOLVE / FIXTURE_CHECK wrote) and his record strictly before
            # the day's cut
            fixture_referees: dict[int, int | None] = {}
            for fx in fixtures:
                if fx.sport == "football":
                    found = referee_terms.referee_for_event(
                        config.db_path, fx.sofascore_event_id)
                    fixture_referees[fx.sofascore_event_id] = (
                        found.referee_id if found is not None else None)
            referee_reads_by_event = referee_terms.fixture_reads(
                football_history, referee_terms.load_labels(config.db_path),
                int(cut.timestamp()), fixture_referees)
        football_book = replay_football(
            football_history,
            int(cut.timestamp()),
            shared_league_link=link_shared,
            # epochs.UNIT_STRENGTH_FROM_PARENT (audit 2026-10-13 A1)
            unit_strength_from_parent=epochs.unit_strength_from_parent(args.date),
            # epochs.FOOTBALL_CUP_STRENGTH: the league strength learnt in
            # international club cups (a missing / malformed file raises, rc 2)
            **cup_book_args(cup_strength_on),
        )

    all_rows = []
    skip_reasons: dict[str, int] = {}
    # See bet.sofa.epochs: from the 10-05 stats-only rebuild on, the price
    # no longer enters p_central.
    stats_only = stats_only_epoch(args.date)
    rating_prices = stats_only and tennis_rating_prices(args.date)
    # epochs.TENNIS_SET_RATING_PRICES (audit 2026-10-13 B5, off): rides on
    # the rating prices
    set_rating_prices = rating_prices and epochs.tennis_set_rating_prices(args.date)
    # epochs.TENNIS_ACES_OPPONENT: aces centres x the returner's factor
    aces_opponent_on = stats_only and epochs.tennis_aces_opponent(args.date)
    marginal_centres_on = stats_only and derived_marginal_centres_enabled(args.date)
    # epochs.DERIVED_SHEET_MARGINS (audit 2026-10-13 B3): a joint's side with
    # no quoted ladder priced by the SHEET formula (off: byte-identical)
    sheet_margins_on = marginal_centres_on and epochs.derived_sheet_margins(args.date)
    # epochs.COUNT_DISPERSION: a missing / malformed config raises here (rc 2),
    # never a sheet that claims a rule it did not use
    epochs.require_k_with_dispersion(args.date)
    count_dispersion_on = stats_only and epochs.count_dispersion_enabled(args.date)
    # epochs.PER_MARKET_K: K_CENTRE.by_market of the engine constants
    per_market_k_on = stats_only and epochs.per_market_k_enabled(args.date)
    # epochs.FOOTBALL_LEAGUE_RATE_RULE: a competition below MIN_LEAGUE_MATCHES
    # gives the rating no centre (NO_LEAGUE_RATE) instead of the all-league
    # mean (measured worse, off - docs/sofa/evidence/league_rate_rule_2026-10-13.md)
    league_rate_on = stats_only and epochs.football_league_rate_rule(args.date)
    dispersion_table = load_dispersion_table() if count_dispersion_on else None
    # Audit 2026-10-13 B1 / B2 (all None = the centre as it was, byte for
    # byte): the game-state term (a missing / malformed config raises, rc 2),
    # the rating on RATED_SCOPE_MARKETS, the league venue multiplier.
    game_state_table = (
        load_game_state_table()
        if stats_only and epochs.game_state_enabled(args.date) else None)
    # epochs.FOOTBALL_GOALS_STRETCH (off: None, the centre byte for byte; a
    # missing / malformed config raises, rc 2)
    goals_stretch_table = (
        load_goals_stretch_table()
        if stats_only and epochs.football_goals_stretch(args.date) else None)
    # epochs.FOOTBALL_COUNT_STRETCH / FOOTBALL_PLAYER_STRETCH (off: None, the
    # centre byte for byte; a missing / malformed config raises, rc 2)
    count_stretch_table = (
        load_count_stretch_table()
        if stats_only and epochs.football_count_stretch(args.date) else None)
    # epochs.FOOTBALL_REFEREE: cards / fouls centres x the referee term (a
    # missing / malformed config raises, rc 2); the reads need the history.
    referee_effect_table = (
        referee_terms.load_effect_table()
        if stats_only and epochs.football_referee(args.date) else None)
    player_stretch_table = (
        load_player_stretch_table()
        if stats_only and epochs.football_player_stretch(args.date) else None)
    # epochs.FOOTBALL_PLAYER_SHARE (off: None, the centre byte for byte; a
    # missing / malformed config raises, rc 2)
    player_share_table = (
        psh.load_table()
        if stats_only and epochs.football_player_share(args.date) else None)
    # epochs.FOOTBALL_CLOSENESS_STRETCH (off: None, the centre byte for byte;
    # a missing / malformed config raises, rc 2)
    closeness_stretch_table = (
        load_closeness_stretch_table()
        if stats_only and epochs.football_closeness_stretch(args.date)
        else None)
    rated_scope_on = stats_only and epochs.football_rated_scope(args.date)
    venue_prior_on = stats_only and epochs.football_venue_prior(args.date)
    # epochs.SAMPLE_OPPONENT_CORRECTION (audit 2026-10-13 B15 / A5): the
    # football sample read through the rating book (None: the raw sample)
    opponent_on = (stats_only and football_book is not None
                   and epochs.sample_opponent_correction(args.date))
    # epochs.SAMPLE_CUP_STRENGTH (off): the correction's gaps read the cup
    # league strength, with the observation's and the fixture's competition
    sample_cup_on = (opponent_on and cup_strength_on
                     and epochs.sample_cup_strength(args.date))
    sample_corrector = (SampleCorrector(football_book, cup_aware=sample_cup_on)
                        if opponent_on and football_book is not None else None)
    # Audit 2026-10-13 D2: the tennis match winner from the rating (off: no
    # such rung reaches SHEET at all - OFFER does not map it).
    tennis_winner_on = stats_only and epochs.tennis_match_winner(args.date)
    # Audit D1: the football double chance from the pure rating (off: None,
    # no such rung reaches SHEET; a missing / malformed config raises, rc 2)
    result_config = (load_result_config()
                     if stats_only and epochs.football_result_markets(args.date)
                     else None)
    # epochs.SHOT_DETAIL_MARKETS: the footballer shot-detail estimator (off:
    # no such rung reaches SHEET; on without config/sofa_shot_detail.json:
    # every such rung NO_SHOT_DETAIL_FIT)
    shot_detail_on = stats_only and epochs.shot_detail_markets(args.date)
    # epochs.FOOTBALL_RESULT_1X2_DNB: football 1X2 / draw no bet (off: None,
    # no such rung reaches SHEET; a missing / malformed config raises, rc 2)
    result_1x2_dnb_config = (
        load_result_config()
        if stats_only and epochs.football_result_1x2_dnb(args.date) else None)
    shot_detail_fit = load_shot_detail() if shot_detail_on else None
    # epochs.FOOTBALL_SCORE_MARKETS: the football "or" / handicap / DC & goals
    # markets (off: None, no such rung reaches SHEET; a missing / malformed
    # config raises, rc 2)
    score_markets_config = (
        load_result_config()
        if stats_only and epochs.football_score_markets(args.date) else None)
    # epochs.FOOTBALL_INCIDENT_MARKETS (off: None, no such rung reaches
    # SHEET): the as-of red-card / penalty rates from the cached incident
    # lists of the football history (read-only) and the double chance's NB r
    # (a missing / malformed config raises, rc 2)
    incident_pricing = (
        IncidentPricing(
            load_incident_rates(
                config.db_path, football_history,
                int(datetime.strptime(args.date, "%Y-%m-%d")
                    .replace(tzinfo=UTC).timestamp())),
            load_result_config())
        if (stats_only and football_history is not None
            and epochs.football_incident_markets(args.date))
        else None)
    # epochs.FOOTBALL_CARD_HALVES (off: None, no such rung reaches SHEET):
    # the as-of card-points half shares and side / half red-card and penalty
    # rates from the cached incident lists of the football history
    # (read-only)
    card_half_rates = (
        load_card_half_rates(
            config.db_path, football_history,
            int(datetime.strptime(args.date, "%Y-%m-%d")
                .replace(tzinfo=UTC).timestamp()))
        if (stats_only and football_history is not None
            and epochs.football_card_halves(args.date))
        else None)
    # epochs.FOOTBALL_CARD_HALVES_TERMS: the halves on the full-match live
    # centre, the side events with their game state (off: card_halves_v1)
    card_half_terms_on = (card_half_rates is not None
                          and epochs.football_card_halves_terms(args.date))
    # epochs.TENNIS_SET_MARKETS: the tennis set winner and exact sets score
    set_markets_on = stats_only and epochs.tennis_set_markets(args.date)
    # Audit 2026-10-13 C1 / B14 (None = byte for byte; a missing / malformed
    # config raises, rc 2): the season-phase term of the goals centre, the
    # rating's weight per market.
    season_phase_table = load_season_phase_table() if season_phase_on else None
    rating_weight_table = (
        load_rating_weight_table()
        if stats_only and epochs.football_rating_weight(args.date) else None)
    # epochs.MEN_FRIENDLY_BASELINE (off: None, byte for byte): the as-of
    # men's friendly goals mean, read from the listing index only on a day
    # with an 851 fixture (bet.sofa.men_friendly)
    men_friendly_prior: FriendlyBaseline | None = None
    if (stats_only and epochs.men_friendly_baseline(args.date)
            and any(is_men_friendly_fixture(f.sport, f.competition_id)
                    for f in fixtures)):
        day_start = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=UTC)
        men_friendly_prior = load_men_friendly_baseline(
            config.db_path, int(day_start.timestamp()))

    try:
        for offer in offers:
            if offer.status == "NO_PRICE":
                continue
            if only_ids is not None and offer.sofascore_event_id not in only_ids:
                continue

            fixture = fixtures_by_id.get(offer.sofascore_event_id)
            fixture_samples = samples_by_id.get(offer.sofascore_event_id)

            if not fixture or not fixture_samples:
                continue

            if fixture_samples.readiness == "BLOCKED":
                continue

            forecast = tennis_forecast(tennis_model, fixture)
            rated_fixtures += forecast is not None
            rows, skipped = process_fixture(
                fixture,
                fixture_samples,
                offer,
                baselines,
                reliability,
                engine_constants,
                vetoes,
                config,
                side_correlations,
                day_obs,
                forecast,
                (
                    FootballForecast(
                        football_book,
                        fixture.competition_id,
                        fixture.home_entity_id,
                        fixture.away_entity_id,
                        strict_league_rate=league_rate_on,
                        rated_scope=(RATED_SCOPE_MARKETS if rated_scope_on
                                     else frozenset()),
                    )
                    if football_book is not None and fixture.sport == "football"
                    else None
                ),
                tennis_tiers,
                stats_only=stats_only,
                rating_prices=rating_prices,
                marginal_centres_on=marginal_centres_on,
                sheet_margins_on=sheet_margins_on,
                dispersion_table=dispersion_table,
                per_market_k_on=per_market_k_on,
                game_state=game_state_table,
                goals_stretch=goals_stretch_table,
                count_stretch=count_stretch_table,
                referee_effect=referee_effect_table,
                referee_reads=referee_reads_by_event.get(fixture.sofascore_event_id),
                player_stretch=player_stretch_table,
                player_share=player_share_table,
                closeness_stretch=closeness_stretch_table,
                venue_prior_on=venue_prior_on,
                set_rating_prices=set_rating_prices,
                aces_opponent_on=aces_opponent_on,
                sample_corrector=sample_corrector,
                tennis_winner_on=tennis_winner_on,
                result_config=result_config,
                incident_pricing=incident_pricing,
                card_half_rates=card_half_rates,
                card_half_terms_on=card_half_terms_on,
                set_markets_on=set_markets_on,
                season_phase=(season_phase_table if season_index is not None
                              else None),
                season_phase_label=(
                    season_index.phase(
                        fixture.competition_id, fixture.season_id,
                        int(fixture.kickoff_utc.timestamp()),
                        fixture.home_entity_id, fixture.away_entity_id)
                    if season_index is not None and fixture.sport == "football"
                    else None),
                rating_weights=rating_weight_table,
                men_friendly_baseline=men_friendly_prior,
                shot_detail_on=shot_detail_on,
                shot_detail_fit=shot_detail_fit,
                result_1x2_dnb=result_1x2_dnb_config,
                result_phase=(
                    season_index.phase(
                        fixture.competition_id, fixture.season_id,
                        int(fixture.kickoff_utc.timestamp()),
                        fixture.home_entity_id, fixture.away_entity_id)
                    if (season_index is not None and fixture.sport == "football"
                        and (result_1x2_dnb_config is not None
                             or score_markets_config is not None))
                    else None),
                score_markets=score_markets_config,
            )
            all_rows.extend(rows)
            for _rung, reason, _detail in skipped:
                skip_reasons[reason.value] = skip_reasons.get(reason.value, 0) + 1

        sheet_path = runs_dir / "05_sheet.json"
        if link_shared:
            all_rows = [r.model_copy(update={"link_rule": epochs.LINK_SHARED_LEAGUE})
                        for r in all_rows]

        if cards_correlation_on:
            all_rows = [
                r.model_copy(update={"cards_rule": epochs.CARDS_CORRELATION})
                for r in all_rows
            ]

        if tennis_scoped:
            all_rows = [
                r.model_copy(update={"tennis_table_rule": epochs.TENNIS_SCOPED_TABLE})
                if r.sport == "tennis" else r
                for r in all_rows
            ]

        if per_market_k_on:
            all_rows = [
                r.model_copy(update={"k_rule": epochs.PER_MARKET_K})
                for r in all_rows
            ]

        if count_dispersion_on:
            all_rows = [
                r.model_copy(update={"dispersion_rule": epochs.COUNT_DISPERSION})
                for r in all_rows
            ]

        if opponent_on:
            all_rows = [
                r.model_copy(
                    update={"opponent_rule": epochs.SAMPLE_OPPONENT_CORRECTION})
                for r in all_rows
            ]

        # Audit 2026-10-13 switches: the rule on the rows it applies to, so a
        # rebuild re-runs SHEET on a sheet built before the switch
        # (rebuild_plan); the same flags that reached process_fixture.
        for marker, on in (
            (epochs.GAME_STATE_MARKER, game_state_table is not None),
            (epochs.FOOTBALL_RATED_SCOPE_MARKER, rated_scope_on),
            (epochs.FOOTBALL_VENUE_PRIOR_MARKER, venue_prior_on),
            (epochs.SEASON_PHASE_MARKER, season_phase_table is not None),
            (epochs.FOOTBALL_RATING_WEIGHT_MARKER,
             rating_weight_table is not None),
            (epochs.TENNIS_SET_RATING_PRICES_MARKER, set_rating_prices),
            (epochs.TENNIS_ACES_OPPONENT_MARKER, aces_opponent_on),
            (epochs.FOOTBALL_CUP_STRENGTH_MARKER,
             cup_strength_on and football_book is not None),
            (epochs.SAMPLE_CUP_STRENGTH_MARKER, sample_cup_on),
            (epochs.FOOTBALL_GOALS_STRETCH_MARKER,
             goals_stretch_table is not None),
            (epochs.FOOTBALL_COUNT_STRETCH_MARKER,
             count_stretch_table is not None),
            (epochs.FOOTBALL_PLAYER_STRETCH_MARKER,
             player_stretch_table is not None),
            (epochs.FOOTBALL_REFEREE_MARKER, referee_effect_table is not None),
            (epochs.FOOTBALL_PLAYER_SHARE_MARKER,
             player_share_table is not None),
            (epochs.FOOTBALL_CLOSENESS_STRETCH_MARKER,
             closeness_stretch_table is not None),
        ):
            all_rows = stamp_marker(all_rows, marker, on)
        # epochs.FOOTBALL_PLAYER_PROPS_V2: its rows exist only while OFFER
        # read them, so the mark goes on those rows alone (off: no row).
        all_rows = [
            r.model_copy(update={
                "player_props_v2_rule": epochs.FOOTBALL_PLAYER_PROPS_V2})
            if r.market in PLAYER_PROPS_V2_METRICS else r
            for r in all_rows
        ]
        # the fitted config the rows were priced on (bet.sofa.sheet_config)
        config_sha = sheet_config.fingerprint()
        all_rows = [r.model_copy(update={"config_sha": config_sha})
                    for r in all_rows]

        written = [sheet_row_json(r) for r in all_rows]
        replaced_previous = 0
        if only_ids is not None:
            # the late RESOLVE pass: every other fixture's rows as they were
            previous_rows = (json.loads(sheet_path.read_text(encoding="utf-8"))
                             if sheet_path.exists() else [])
            written, replaced_previous = merge_by_event(
                previous_rows, written, only_ids)
        write_atomic(
            sheet_path,
            json.dumps(
                written,
                indent=2,
                ensure_ascii=False,
            ),
        )

    except Exception:
        logger.exception("Error generating sheet")
        sys.exit(2)

    # Summary
    verdict_counts: dict[str, int] = {}
    for r in all_rows:
        verdict_counts[r.verdict] = verdict_counts.get(r.verdict, 0) + 1

    summary = {
        "stage": "SHEET",
        "verdict": "OK",
        "metrics": {
            "rows_generated": len(all_rows),
            **({"event_ids_only": len(only_ids),
                "replaced_previous_rows": replaced_previous,
                "rows_written": len(written)}
               if only_ids is not None else {}),
            "epoch": STATS_ONLY if stats_only else "old",
            "link_rule": epochs.LINK_SHARED_LEAGUE if link_shared else "old",
            "dispersion_rule": (
                epochs.COUNT_DISPERSION if count_dispersion_on else "old"),
            "k_rule": (
                epochs.PER_MARKET_K if per_market_k_on else "old"),
            "opponent_rule": (
                epochs.SAMPLE_OPPONENT_CORRECTION if opponent_on else "old"),
            "football_league_rate_rule": (
                epochs.LEAGUE_RATE_RULE if league_rate_on else "old"),
            "cards_rule": (
                epochs.CARDS_CORRELATION if cards_correlation_on else "old"),
            "tennis_table_rule": (
                epochs.TENNIS_SCOPED_TABLE if tennis_scoped else "old"),
            "tennis_set_rule": (
                epochs.TENNIS_SET_RATING_PRICES if set_rating_prices else "old"),
            "tennis_aces_rule": (
                epochs.TENNIS_ACES_OPPONENT if aces_opponent_on else "old"),
            "game_state_rule": (
                epochs.GAME_STATE if game_state_table is not None else "old"),
            "rated_scope_rule": (
                epochs.FOOTBALL_RATED_SCOPE if rated_scope_on else "old"),
            "venue_prior_rule": (
                epochs.FOOTBALL_VENUE_PRIOR if venue_prior_on else "old"),
            "season_phase_rule": (
                epochs.SEASON_PHASE if season_phase_table is not None else "old"),
            "rating_weight_rule": (
                epochs.FOOTBALL_RATING_WEIGHT if rating_weight_table is not None
                else "old"),
            "cup_strength_rule": (
                epochs.FOOTBALL_CUP_STRENGTH
                if cup_strength_on and football_book is not None else "old"),
            "sample_cup_rule": (
                epochs.SAMPLE_CUP_STRENGTH if sample_cup_on else "old"),
            "goals_stretch_rule": (
                epochs.FOOTBALL_GOALS_STRETCH if goals_stretch_table is not None
                else "old"),
            "count_stretch_rule": (
                epochs.FOOTBALL_COUNT_STRETCH if count_stretch_table is not None
                else "old"),
            "player_stretch_rule": (
                epochs.FOOTBALL_PLAYER_STRETCH
                if player_stretch_table is not None else "old"),
            "referee_rule": (
                epochs.FOOTBALL_REFEREE if referee_effect_table is not None
                else "old"),
            "player_share_rule": (
                epochs.FOOTBALL_PLAYER_SHARE
                if player_share_table is not None else "old"),
            "closeness_rule": (
                epochs.FOOTBALL_CLOSENESS_STRETCH
                if closeness_stretch_table is not None else "old"),
            "config_sha": config_sha,
            **({"derived_margins_rule": epochs.DERIVED_SHEET_MARGINS_RULE}
               if sheet_margins_on else {}),
            "tennis_rated_fixtures": rated_fixtures,
            "verdicts": verdict_counts,
            # Every rung that produced no row says why (C8/L1).
            "skipped_rungs": skip_reasons,
        },
        "output_path": str(sheet_path),
    }
    print(f"SOFA_SUMMARY: {json.dumps(summary)}", flush=True)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
