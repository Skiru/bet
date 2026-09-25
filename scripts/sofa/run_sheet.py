import argparse
import json
import logging
import os
import re
import statistics
import sys
from collections import Counter
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, Literal

from pydantic import RootModel
from rapidfuzz import fuzz

from bet.sofa.config import SofaConfig
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
from bet.sofa.coupon import effective_kickoff
from bet.sofa.derived import load_side_correlations, price_derived_rungs
from bet.sofa.engine import (
    MAX_LADDER_SIGMA,
    MAX_SPREAD_RATIO,
    MIN_SPREAD_RATIO,
    P_CEILING,
    P_FLOOR,
    bar_is_unreachable,
    bar_probability,
    calc_p_central_nb_raw,
    calc_p_central_raw,
    calculate_p_low,
    devig,
    get_required_odds,
    ladder_centre,
    ladder_implied_sd,
    outside_model_resolution,
    p_empirical_centred_raw,
    p_empirical_shrunk_to_price,
    predictive_sd,
    support_floor_for,
    uses_empirical_frequency,
    uses_negative_binomial,
    uses_poisson_floor,
    winning_boundary,
)
from bet.sofa.football_rating import (
    W_FOOTBALL_RATING,
    FootballForecast,
    RatingBook,
)
from bet.sofa.football_rating import load_history as load_football_history
from bet.sofa.football_rating import replay as replay_football
from bet.sofa.market_mapper import fold, is_derived
from bet.sofa.names import normalize_name
from bet.sofa.players import is_player_metric, player_sample_key
from bet.sofa.stage import set_stage
from bet.sofa.tennis_prior import tier_prior
from bet.sofa.tennis_rating import (
    W_TENNIS_RATING,
    MatchForecast,
    TennisRatingModel,
    blend_with_price,
    build_model,
    load_coefficients,
    load_history,
)
from bet.sofa.timeutil import now

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
    return _load_json_config(Path("config/sofa_league_baselines.json"))


def load_tennis_tier_baselines(config: SofaConfig) -> dict[str, Any]:
    """bet.sofa.tennis_prior; absent until fit_tennis_tier_baselines.py ran.

    SOFA_TENNIS_TIER_BASELINES points a scratch run at a candidate file, so
    one can be exercised end to end without installing it for the real day.
    """
    path = os.environ.get(
        "SOFA_TENNIS_TIER_BASELINES", "config/sofa_tennis_tier_baselines.json"
    )
    loaded = _load_json_config(Path(path))
    metrics = loaded.get("metrics")
    return metrics if isinstance(metrics, dict) else {}


def load_reliability(config: SofaConfig) -> dict[str, Any]:
    return _load_json_config(Path("config/sofa_market_reliability.json"))


def load_engine_constants(config: SofaConfig) -> dict[str, Any]:
    return _load_json_config(Path("config/sofa_engine_constants.json"))


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


def home_competition(observations: list[Observation]) -> int | None:
    """The competition a side actually plays in: the one holding most of its
    sample, and at least half of it. None when the sample has no majority."""
    comps = [o.competition_id for o in observations if o.competition_id is not None]
    if not comps:
        return None
    comp, count = Counter(comps).most_common(1)[0]
    return comp if count * 2 >= len(observations) else None


def _fitted_league_mean(
    baselines: dict[str, Any], metric: str, competition_id: int
) -> float | None:
    entry = (baselines.get(metric) or {}).get(str(competition_id))
    if isinstance(entry, dict) and isinstance(entry.get("mean"), int | float):
        return float(entry["mean"])
    return None


def resolve_prior(
    baselines: dict[str, Any],
    day_obs: DayLeagueObservations,
    metric: str,
    fixture: Fixture,
    own_sides: list[list[Observation]],
    own_events: set[int],
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
    for side in own_sides:
        home = home_competition(side)
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
    pooled = get_prior(baselines, metric, comp)
    return pooled, global_prior_note(baselines, metric, comp, pooled)


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

# A leading market scope, folded: "1.polowa", "2. polowa". These describe which
# part of the match the line covers, not who it is about.
_SCOPE_PREFIX = re.compile(r"^[12]\.\s?polowa\b")


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
    home_score = fuzz.token_sort_ratio(subject_norm, normalize_name(fixture.home_name))
    away_score = fuzz.token_sort_ratio(subject_norm, normalize_name(fixture.away_name))

    best = max(home_score, away_score)
    if best < SIDE_MATCH_THRESHOLD:
        return None
    if abs(home_score - away_score) < 1e-9:
        # Two equally good answers is not an answer.
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
    The earlier of the two clocks decides, as at every other kickoff gate.
    """
    kickoff = effective_kickoff(fixture)
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
    rating: MatchForecast, side: str | None, p_rating: float, market_p: float | None
) -> str:
    who = "home" if side in (None, "side_a") else "away"
    p = rating.p_side_wins(side or "side_a")
    blend = (
        f"blended {W_TENNIS_RATING:g} with market_p {market_p:.4f}"
        if market_p is not None
        else "no price on this rung, rating alone"
    )
    return (
        f"TENNIS_RATING: rating p {p_rating:.4f}, {blend} "
        f"(W_TENNIS_RATING); {who} wins the match {p:.3f}, "
        f"{len(rating.neighbours_home)} nearest historical matches, "
        f"rated matches {rating.rated_home}/{rating.rated_away}"
    )


def load_tennis_rating(
    config: SofaConfig, fixtures: list[Fixture], run_date: str
) -> TennisRatingModel | None:
    """The rating model for this day, or None when there is no tennis or no
    fitted calibration. Ratings run over history strictly before the day."""
    if not any(f.sport == "tennis" for f in fixtures):
        return None
    loaded = load_coefficients()
    if loaded is None:
        logger.warning("sheet: config/tennis_rating.json absent, tennis unrated")
        return None
    coefficients, _meta = loaded
    cut = datetime.strptime(run_date, "%Y-%m-%d").replace(tzinfo=UTC)
    history = load_history(config.db_path)
    return build_model(history, coefficients, int(cut.timestamp()))


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
) -> tuple[list[SheetRow], list[tuple[Any, GapReason, str]]]:
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

    # Now evaluate each rung and direction
    for rung in offer.rungs:
        # A derived market is about both sides at once and has no marginal
        # sample to be priced against. derived.py handles it below; falling
        # through here would silently drop it as "metric not in samples".
        if is_derived(rung.market):
            continue
        ladder_rungs = rungs_by_market_subject.get((rung.market, rung.subject), [])
        extra_notes: list[str] = []
        # The histories behind this row, for the prior: which leagues the
        # sides play in, and which matches the prior must leave out.
        own_sides: list[list[Observation]] = []
        own_events: set[int] = set()

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
                own_sides = [metric_sample.side_a, metric_sample.side_b]
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

        n = len(obs)
        if n < config.min_sample:
            skipped.append(
                (rung, GapReason.THIN_SAMPLE, f"n={n} < min_sample={config.min_sample}")
            )
            continue

        values = [o.value for o in obs]
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
        sample_newest_days: int | None = None
        dates = [o.match_date_utc for o in obs if o.match_date_utc is not None]
        if dates:
            sample_newest_days = (now() - max(dates)).days

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
        if fixture.sport == "tennis" and ladder_target is not None:
            row_unfitted.append("K_TENNIS_LADDER_CENTRE")
            w_c = n / (n + K_TENNIS_LADDER_CENTRE)
            centre = w_c * mean + (1 - w_c) * ladder_target
        else:
            # A tennis rung with no ladder - most of them - used to fall into
            # the football lookup below, keyed on a competition id that is one
            # week of one tournament, so it always reached the global pool or
            # nothing. See bet.sofa.tennis_prior (measured metrics only).
            tier = (
                tier_prior(tennis_tiers, rung.market, fixture.category_name,
                           fixture.ground_type)
                # Fitted on best-of-three only, like the rating; a best-of-
                # five pulled toward it would lose ~15 games of centre.
                if fixture.sport == "tennis" and tennis_tiers
                and fixture.default_period_count in (None, 3)
                else None
            )
            prior: float | None
            prior_note: str | None
            if tier is not None:
                prior, prior_note = tier
                extra_notes.append(prior_note)
            elif day_obs is not None and own_sides:
                prior, prior_note = resolve_prior(
                    baselines, day_obs, rung.market, fixture, own_sides, own_events)
                if prior_note:
                    extra_notes.append(prior_note)
            else:
                prior = get_prior(baselines, rung.market, fixture.competition_id)
                prior_note = global_prior_note(
                    baselines, rung.market, fixture.competition_id, prior)
                if prior_note:
                    extra_notes.append(prior_note)
            if prior is not None:
                w_c = n / (n + k_centre)  # K_CENTRE
                centre = w_c * mean + (1 - w_c) * prior
            else:
                centre = mean
            # The opponent-adjusted rating replaces the sample's centre where
            # it has one (bet.sofa.football_rating). The spread stays the
            # sample's.
            rated = (
                football.centre(
                    rung.market,
                    determine_side(rung.subject, fixture) if rung.subject else None,
                )
                if football is not None and not is_player_metric(rung.market)
                else None
            )
            if rated is not None:
                sample_centre = centre
                centre = W_FOOTBALL_RATING * rated[0] + (
                    1 - W_FOOTBALL_RATING) * sample_centre
                row_unfitted.append("W_FOOTBALL_RATING")
                extra_notes.append(
                    f"FOOTBALL_RATING: centre {centre:.2f} from the rating "
                    f"({rated[1]}) at W_FOOTBALL_RATING={W_FOOTBALL_RATING:g}, "
                    f"sample centre was {sample_centre:.2f}"
                )

        pred_sd = predictive_sd(
            variance, mean, n, apply_poisson_floor=uses_poisson_floor(rung.market)
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
            if p_rating is not None:
                p_raw = blend_with_price(
                    p_rating,
                    market_ps.get((rung.market, rung.subject, rung.line, direction)),
                )
            elif uses_empirical_frequency(rung.market):
                # Counted on the SHRUNK centre, not on the raw sample. The
                # shrink above is not advisory: a note that says "pulled to
                # 5.23" beside a number computed at 3.40 describes a row the
                # stage did not price (F55).
                rung_price = market_ps.get(
                    (rung.market, rung.subject, rung.line, direction)
                )
                if fixture.sport == "tennis" and (
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
                else:
                    p_raw = p_empirical_centred_raw(
                        values, boundary, direction, centre - mean
                    )
            elif uses_negative_binomial(rung.market):
                # A count is right-skewed and the normal CDF is not. See
                # NEGATIVE_BINOMIAL_METRICS: symmetric tails put +4.7 pp on
                # every OVER rung, which is what makes a coupon come out
                # 88.8% OVER. No support floor here — the distribution is
                # discrete on 0,1,2,... so there is no mass below zero to
                # condition away.
                p_raw = calc_p_central_nb_raw(centre, pred_sd, boundary, direction)
            else:
                p_raw = calc_p_central_raw(
                    centre,
                    pred_sd,
                    boundary,
                    direction,
                    support_floor_for(rung.market),
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

            corr = get_calibration_correction(
                reliability, rung.market, p_cent, direction
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
                notes.append(rating_note(rating, rating_side, p_rating, m_p))
                if "W_TENNIS_RATING" not in row_unfitted:
                    row_unfitted = [*row_unfitted, "W_TENNIS_RATING"]
            tennis_price_shrink = (
                p_rating is None
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
                    sample_weight * P_CEILING + (1.0 - sample_weight) * m_p_out
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
            )
            rows.append(row)

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
        correction_for=lambda market, p, direction="": get_calibration_correction(
            reliability, market, p, direction
        ),
        rating_p=(rating.probability if rating is not None else None),
        rating_note=(
            partial(rating_note, rating) if rating is not None else None
        ),
    )
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
    # Every request underneath this call is this stage's cost (F22).
    set_stage("SHEET")
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD", default=now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    config = SofaConfig.from_env()

    runs_dir = Path(config.runs_dir) / args.date
    fixtures_path = runs_dir / "02_fixtures.json"
    samples_path = runs_dir / "03_samples.json"
    offer_path = runs_dir / "04_offer.json"

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

    side_correlations = load_side_correlations()
    baselines = load_baselines(config)
    tennis_tiers = load_tennis_tier_baselines(config)
    day_obs = day_league_observations(fixtures, samples)
    reliability = load_reliability(config)
    engine_constants = load_engine_constants(config)
    tennis_model = (
        load_tennis_rating(config, fixtures, args.date)
        if os.environ.get("SOFA_TENNIS_RATING", "1") != "0"
        else None
    )
    rated_fixtures = 0
    football_book: RatingBook | None = None
    if os.environ.get("SOFA_FOOTBALL_RATING", "1") != "0" and any(
        f.sport == "football" for f in fixtures
    ):
        cut = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=UTC)
        football_book = replay_football(
            load_football_history(config.db_path), int(cut.timestamp())
        )

    all_rows = []
    skip_reasons: dict[str, int] = {}

    try:
        for offer in offers:
            if offer.status == "NO_PRICE":
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
                    )
                    if football_book is not None and fixture.sport == "football"
                    else None
                ),
                tennis_tiers,
            )
            all_rows.extend(rows)
            for _rung, reason, _detail in skipped:
                skip_reasons[reason.value] = skip_reasons.get(reason.value, 0) + 1

        sheet_path = runs_dir / "05_sheet.json"

        with open(sheet_path, "w", encoding="utf-8") as f:
            json.dump(
                [r.model_dump(mode="json") for r in all_rows],
                f,
                indent=2,
                ensure_ascii=False,
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
