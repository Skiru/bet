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
from bet.sofa.engine import (
    MAX_LADDER_SIGMA,
    bar_probability,
    calc_p_central,
    calculate_p_low,
    devig,
    get_required_odds,
    ladder_centre,
    p_empirical,
    predictive_sd,
    uses_empirical_frequency,
    uses_poisson_floor,
    winning_boundary,
)
from bet.sofa.market_mapper import fold
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
UNFITTED_K_CENTRE = 10.0
UNFITTED_K_PRICE = 10.0


def read_constant(
    engine_constants: dict[str, Any], name: str, fallback: float
) -> tuple[float, bool]:
    """Return (value, was_fitted). A null or missing entry is NOT fitted."""
    entry = engine_constants.get(name)
    if isinstance(entry, dict):
        value = entry.get("value")
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value), True
        return fallback, False
    if isinstance(entry, int | float) and not isinstance(entry, bool):
        return float(entry), True
    return fallback, False


def get_calibration_correction(
    reliability: dict[str, Any], market: str, p: float
) -> float:
    """§6.5 step 2. Zero until E11 has measured this market's own curve."""
    market_entry = reliability.get(market)
    if not isinstance(market_entry, dict):
        return 0.0

    bucket_index = min(9, int(p * 10))
    bucket = f"{bucket_index / 10.0:.1f}-{(bucket_index + 1) / 10.0:.1f}"
    bucket_entry = market_entry.get(bucket)
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

    global_entry = metric_entry.get("global")
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
) -> tuple[list[SheetRow], list[tuple[Any, GapReason, str]]]:
    rows: list[SheetRow] = []
    skipped: list[tuple[Any, GapReason, str]] = []

    k_centre, k_centre_fitted = read_constant(
        engine_constants, "K_CENTRE", UNFITTED_K_CENTRE
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
        key = (rung.market, rung.subject)
        if key not in rungs_by_market_subject:
            rungs_by_market_subject[key] = []
        rungs_by_market_subject[key].append(rung)

    ladder_centres: dict[tuple[str, str], float | None] = {}
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

    # Now evaluate each rung and direction
    for rung in offer.rungs:
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

        mean = statistics.mean(values)
        if n > 1:
            variance = statistics.variance(values)
            sample_sd = statistics.stdev(values)
        else:
            variance = 0.0
            sample_sd = 0.0

        hits = 0  # Not calculated yet, need logic for hits for OVER/UNDER.

        # 6.2 Środek
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
                p_cent = p_empirical(hits, n)
            else:
                p_cent = calc_p_central(centre, pred_sd, boundary, direction)

            p_low_val = calculate_p_low(centre, sample_sd, n, boundary, direction)

            m_p = market_ps.get((rung.market, rung.subject, rung.line, direction))

            corr = get_calibration_correction(reliability, rung.market, p_cent)

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
                if l_sigma is None:
                    verdict = "LEAN"
                    notes.append(
                        "NO_LADDER_CHECK: ladder_sigma unmeasurable "
                        f"(rungs={len(ladder_rungs)}, "
                        f"sample_sd={sample_sd:.4f}); VALUE withheld"
                    )
                elif l_sigma <= max_ladder_sigma:
                    verdict = "VALUE"
                else:
                    verdict = "LEAN"
                    notes.append(
                        f"LADDER_DISAGREES: ladder_sigma {l_sigma:.3f} > "
                        f"{max_ladder_sigma:.3f}"
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
                required_odds=req_odds_out,
                offered_odds=offered_odds,
                edge=edge,
                surplus=surplus,
                verdict=verdict,
                notes=notes,
            )
            rows.append(row)

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
