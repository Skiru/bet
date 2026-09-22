import argparse
import json
import logging
import re
import statistics
import sys
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
    p_empirical_raw,
    predictive_sd,
    support_floor_for,
    uses_empirical_frequency,
    uses_negative_binomial,
    uses_poisson_floor,
    winning_boundary,
)
from bet.sofa.market_mapper import fold, is_derived
from bet.sofa.names import normalize_name
from bet.sofa.stage import set_stage
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
) -> tuple[list[SheetRow], list[tuple[Any, GapReason, str]]]:
    rows: list[SheetRow] = []
    skipped: list[tuple[Any, GapReason, str]] = []

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
        # Check if metric exists in samples
        if rung.market not in samples.metrics:
            continue

        metric_sample = samples.metrics[rung.market]
        ladder_rungs = rungs_by_market_subject.get((rung.market, rung.subject), [])

        # A _total market pools both histories; one historical match still
        # contributes one observation (L13). A per-side market uses only the
        # side it names.
        if not rung.subject:
            obs = deduplicate_observations(
                [metric_sample.side_a, metric_sample.side_b, metric_sample.h2h]
            )
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
            obs = metric_sample.side_a if side == "side_a" else metric_sample.side_b

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
        if fixture.sport == "tennis" and ladder_target is not None:
            w_c = n / (n + K_TENNIS_LADDER_CENTRE)
            centre = w_c * mean + (1 - w_c) * ladder_target
        else:
            prior = get_prior(baselines, rung.market, fixture.competition_id)
            if prior is not None:
                w_c = n / (n + k_centre)  # K_CENTRE
                centre = w_c * mean + (1 - w_c) * prior
            else:
                centre = mean

        pred_sd = predictive_sd(
            variance, mean, n, apply_poisson_floor=uses_poisson_floor(rung.market)
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
            if uses_empirical_frequency(rung.market):
                p_raw = p_empirical_raw(hits, n)
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

            notes: list[str] = []
            if (
                fixture.sport == "tennis"
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

            if unfitted:
                notes.append(f"UNFITTED_CONSTANTS: {', '.join(unfitted)}")

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
    reliability = load_reliability(config)
    engine_constants = load_engine_constants(config)

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
