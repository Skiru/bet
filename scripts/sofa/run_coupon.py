import argparse
import json
import logging
import sys
from datetime import datetime, UTC, timedelta
from pathlib import Path

from pydantic import RootModel

from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture, SheetRow, FixtureOffer, Veto, Coupon, CouponRow
from bet.sofa.timeutil import now
from bet.sofa.market_mapper import get_mechanism_family

logger = logging.getLogger(__name__)

def read_file(path: Path) -> bytes | None:
    if not path.exists():
        return None
    with open(path, "rb") as f:
        return f.read()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD", default=now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    
    config = SofaConfig.from_env()
    runs_dir = Path(config.runs_dir) / args.date
    
    sheet_path = runs_dir / "05_sheet.json"
    fixtures_path = runs_dir / "02_fixtures.json"
    offer_path = runs_dir / "04_offer.json"
    vetoes_path = runs_dir / "vetoes.json"
    
    sheet_data = read_file(sheet_path)
    fixtures_data = read_file(fixtures_path)
    offer_data = read_file(offer_path)
    
    if not sheet_data or not fixtures_data or not offer_data:
        print("Missing required artifacts", file=sys.stderr)
        sys.exit(2)
        
    fixtures = RootModel[list[Fixture]].model_validate_json(fixtures_data).root
    sheet_rows = RootModel[list[SheetRow]].model_validate_json(sheet_data).root
    offers = RootModel[list[FixtureOffer]].model_validate_json(offer_data).root
    
    vetoes = []
    vetoes_data = read_file(vetoes_path)
    if vetoes_data:
        vetoes = RootModel[list[Veto]].model_validate_json(vetoes_data).root
        
    veto_keys = {(v.sofascore_event_id, v.market, v.subject, v.line, v.direction) for v in vetoes}
    
    fixtures_by_id = {f.sofascore_event_id: f for f in fixtures}
    
    # Map price fetched_at_utc
    fetched_at_by_key = {}
    for offer in offers:
        for rung in offer.rungs:
            key_base = (offer.sofascore_event_id, rung.market, rung.subject, rung.line)
            if rung.over_odds is not None:
                fetched_at_by_key[key_base + ("OVER",)] = rung.fetched_at_utc
            if rung.under_odds is not None:
                fetched_at_by_key[key_base + ("UNDER",)] = rung.fetched_at_utc
                
    current_time = now()
    
    candidates = []
    
    for row in sheet_rows:
        if row.verdict != "VALUE":
            continue
            
        fixture = fixtures_by_id.get(row.sofascore_event_id)
        if not fixture:
            continue
            
        if fixture.kickoff_utc <= current_time + timedelta(minutes=15):
            continue
            
        if row.offered_odds is None or row.offered_odds < 1.25:
            continue
            
        key = (row.sofascore_event_id, row.market, row.subject, row.line, row.direction)
        if key in veto_keys:
            continue
            
        fetched_at = fetched_at_by_key.get(key)
        if not fetched_at or current_time - fetched_at > timedelta(minutes=config.price_max_age_min):
            continue
            
        candidates.append((row, fixture))
        
    # Sort candidates by surplus descending
    candidates.sort(key=lambda x: x[0].surplus if x[0].surplus is not None else 0.0, reverse=True)
    
    selected_singles = []
    selected_per_fixture = {}
    selected_families_per_fixture = {}
    
    for row, fixture in candidates:
        if len(selected_singles) >= 40: # MAX_SINGLES
            break
            
        fid = row.sofascore_event_id
        if selected_per_fixture.get(fid, 0) >= 3: # MAX_PER_FIXTURE
            continue
            
        family = get_mechanism_family(row.market)
        families = selected_families_per_fixture.get(fid, set())
        
        if family in families:
            continue
            
        selected_singles.append(CouponRow(
            sofascore_event_id=row.sofascore_event_id,
            match_name=f"{fixture.home_name} - {fixture.away_name}",
            kickoff_utc=fixture.kickoff_utc,
            sport=row.sport,
            market=row.market,
            subject=row.subject,
            line=row.line,
            direction=row.direction,
            offered_odds=row.offered_odds,
            required_odds=row.required_odds,
            edge=row.edge,
            surplus=row.surplus
        ))
        
        selected_per_fixture[fid] = selected_per_fixture.get(fid, 0) + 1
        families.add(family)
        selected_families_per_fixture[fid] = families
        
    coupon = Coupon(
        created_at_utc=current_time,
        singles=selected_singles
    )
    
    coupon_json_path = runs_dir / "06_coupon.json"
    coupon_md_path = runs_dir / "06_coupon.md"
    
    with open(coupon_json_path, "w", encoding="utf-8") as f:
        json.dump(coupon.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
        
    with open(coupon_md_path, "w", encoding="utf-8") as f:
        f.write(f"# Kupon ({current_time.strftime('%Y-%m-%d %H:%M:%S')} UTC)\n\n")
        if not selected_singles:
            f.write("Brak zakładów (pusty slate lub wszystkie odrzucone).\n")
        else:
            f.write("## Single\n\n")
            f.write("| Mecz | Kickoff | Rynek | Linia | Kurs | Nadwyżka |\n")
            f.write("|---|---|---|---|---|---|\n")
            for r in selected_singles:
                subject_str = f" ({r.subject})" if r.subject else ""
                market_display = f"{r.market}{subject_str} {r.line} {r.direction}"
                f.write(f"| {r.match_name} | {r.kickoff_utc.strftime('%H:%M')} | {market_display} | {r.line} | **{r.offered_odds:.2f}** | +{r.surplus:.4f} |\n")
                
    # Also write a template vetoes.json if it doesn't exist (to establish VETO_V1)
    if not vetoes_path.exists():
        with open(vetoes_path, "w", encoding="utf-8") as f:
            f.write("[]\n")
            
    summary = {
        "stage": "COUPON",
        "verdict": "OK",
        "metrics": {
            "candidates": len(candidates),
            "selected": len(selected_singles)
        },
        "output_path": str(coupon_json_path)
    }
    print(f"SOFA_SUMMARY: {json.dumps(summary)}")

if __name__ == "__main__":
    main()
