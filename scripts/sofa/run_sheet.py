import argparse
import json
import logging
import math
import statistics
import sys
from pathlib import Path
from rapidfuzz import fuzz

from pydantic import RootModel

from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture, FixtureSamples, FixtureOffer, SheetRow, GapReason, Veto
from bet.sofa.engine import (
    predictive_sd,
    winning_boundary,
    calc_p_central,
    devig,
    ladder_centre,
    calculate_p_low,
    bar_probability,
    get_required_odds,
    MAX_LADDER_SIGMA
)
from bet.sofa.timeutil import now

logger = logging.getLogger(__name__)

def deduplicate_observations(obs_lists: list[list]) -> list:
    seen = set()
    unique = []
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

def load_baselines(config: SofaConfig) -> dict:
    baseline_path = Path("config/sofa_league_baselines.json")
    if baseline_path.exists():
        with open(baseline_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def load_reliability(config: SofaConfig) -> dict:
    rel_path = Path("config/sofa_market_reliability.json")
    if rel_path.exists():
        with open(rel_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def load_engine_constants(config: SofaConfig) -> dict:
    constants_path = Path("config/sofa_engine_constants.json")
    if constants_path.exists():
        with open(constants_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def get_calibration_correction(reliability: dict, market: str, p: float) -> float:
    if market not in reliability:
        return 0.0
    
    b = min(9, int(p * 10))
    bucket_str = f"{b/10.0:.1f}-{(b+1)/10.0:.1f}"
    
    if bucket_str in reliability[market]:
        # Only use correction if it exists (E11 fitted it)
        return reliability[market][bucket_str].get("correction", 0.0)
        
    return 0.0

def get_prior(baselines: dict, metric: str, competition_id: int) -> float | None:
    if metric in baselines:
        if str(competition_id) in baselines[metric]:
            return baselines[metric][str(competition_id)]["mean"]
        if "global" in baselines[metric]:
            return baselines[metric]["global"]
    return None

def determine_side(subject: str, fixture: Fixture) -> str:
    home_score = fuzz.token_sort_ratio(subject.lower(), fixture.home_name.lower())
    away_score = fuzz.token_sort_ratio(subject.lower(), fixture.away_name.lower())
    return "side_a" if home_score >= away_score else "side_b"

def process_fixture(
    fixture: Fixture, 
    samples: FixtureSamples, 
    offer: FixtureOffer,
    baselines: dict,
    reliability: dict,
    engine_constants: dict,
    vetoes: list[Veto],
    config: SofaConfig
) -> list[SheetRow]:
    rows = []
    
    k_centre = engine_constants.get("K_CENTRE", {}).get("value", 10.0)
    k_price = engine_constants.get("K_PRICE", {}).get("value", 10.0)
    max_ladder_sigma = engine_constants.get("MAX_LADDER_SIGMA", MAX_LADDER_SIGMA)
    
    # 6.4 Cena rynkowa — odvigowanie i środek drabiny
    # Group rungs by (market, subject) to find ladder_centre
    rungs_by_market_subject = {}
    for rung in offer.rungs:
        key = (rung.market, rung.subject)
        if key not in rungs_by_market_subject:
            rungs_by_market_subject[key] = []
        rungs_by_market_subject[key].append(rung)
        
    ladder_centres = {}
    market_ps = {}
    
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
        
        # Determine observations
        if not rung.subject:
            obs = deduplicate_observations([metric_sample.side_a, metric_sample.side_b, metric_sample.h2h])
        else:
            side = determine_side(rung.subject, fixture)
            obs = metric_sample.side_a if side == "side_a" else metric_sample.side_b
            
        # Limit to SOFA_SAMPLE_N (10)
        # obs = obs[:config.sample_n]  # Do not cap combined sample here
        
        n = len(obs)
        if n < config.min_sample:
            # We don't generate rows for samples that are too small
            continue
            
        values = [o.value for o in obs]
        mean = statistics.mean(values)
        if n > 1:
            variance = statistics.variance(values)
            sample_sd = statistics.stdev(values)
        else:
            variance = 0.0
            sample_sd = 0.0
            
        hits = 0 # Not calculated yet, need logic for hits for OVER/UNDER.
        
        # 6.2 Środek
        prior = get_prior(baselines, rung.market, fixture.competition_id)
        if prior is not None:
            w_c = n / (n + k_centre) # K_CENTRE
            centre = w_c * mean + (1 - w_c) * prior
        else:
            centre = mean
            
        pred_sd = predictive_sd(variance, mean, n)
        
        for direction in ("OVER", "UNDER"):
            # If the rung only has one side, it might be None, but we still generate the row 
            # if we can. Wait, if it doesn't have odds for this direction, should we generate the row?
            # Yes, we generate the row to show our p_central etc. But `offered_odds` will be None.
            offered_odds = rung.over_odds if direction == "OVER" else rung.under_odds
            # We don't strictly skip if offered_odds is None, because the row might still be LEAN or VALUE if it had a price, 
            # but wait, if it has no price, verdict is NO_PRICE.
            
            boundary = winning_boundary(rung.line, direction)
            p_cent = calc_p_central(centre, pred_sd, boundary, direction)
            
            # Count hits
            if direction == "OVER":
                hits = sum(1 for v in values if v > rung.line)
            else:
                hits = sum(1 for v in values if v < rung.line)
                
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
                force_weight_0=force_weight_0
            )
            
            req_odds = get_required_odds(p_bar, "LEAN") # Hardcoded LEAN tier margin for E8
            
            lc = ladder_centres.get((rung.market, rung.subject))
            l_sigma = None
            if lc is not None and sample_sd > 0:
                l_sigma = abs(centre - lc) / sample_sd
                
            edge = p_cent - m_p if m_p is not None else None
            surplus = offered_odds - req_odds if offered_odds is not None else None
            
            verdict = "BELOW_BAR"
            if offered_odds is None:
                verdict = "NO_PRICE"
            elif surplus is not None and surplus > 0:
                if l_sigma is not None and l_sigma <= max_ladder_sigma:
                    verdict = "VALUE"
                elif l_sigma is None: # If ladder_sigma couldn't be calculated (no crossing 0.5), it's still VALUE?
                    verdict = "VALUE" # "VALUE <=> surplus > 0 i ladder_sigma <= MAX_LADDER_SIGMA". If no ladder_sigma? It passes.
                else:
                    verdict = "LEAN"
            
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
                p_central=round(p_cent, 4),
                market_p=round(m_p, 4) if m_p is not None else None,
                ladder_centre=round(lc, 4) if lc is not None else None,
                ladder_sigma=round(l_sigma, 4) if l_sigma is not None else None,
                p_bar=round(p_bar, 4),
                bar_reason=bar_reason,
                required_odds=round(req_odds, 4),
                offered_odds=offered_odds,
                edge=round(edge, 4) if edge is not None else None,
                surplus=round(surplus, 4) if surplus is not None else None,
                verdict=verdict,
                notes=[]
            )
            rows.append(row)
            
    return rows

def main():
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
                
            rows = process_fixture(fixture, fixture_samples, offer, baselines, reliability, engine_constants, vetoes, config)
            all_rows.extend(rows)
            
        sheet_path = runs_dir / "05_sheet.json"
        
        with open(sheet_path, "w", encoding="utf-8") as f:
            json.dump([r.model_dump(mode="json") for r in all_rows], f, indent=2, ensure_ascii=False)
            
    except Exception as e:
        logger.exception("Error generating sheet")
        sys.exit(2)
        
    # Summary
    verdict_counts = {}
    for r in all_rows:
        verdict_counts[r.verdict] = verdict_counts.get(r.verdict, 0) + 1
        
    summary = {
        "stage": "SHEET",
        "verdict": "OK",
        "metrics": {
            "rows_generated": len(all_rows),
            "verdicts": verdict_counts
        },
        "output_path": str(sheet_path)
    }
    print(f"SOFA_SUMMARY: {json.dumps(summary)}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
