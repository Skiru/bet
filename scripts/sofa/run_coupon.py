import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

from pydantic import RootModel

from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture, SheetRow, FixtureOffer, Veto
from bet.sofa.timeutil import now
from bet.sofa.coupon import build_coupon
from bet.sofa.veto import find_unmatched_vetoes

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
        
    unmatched_vetoes = find_unmatched_vetoes(sheet_rows, vetoes)
    if unmatched_vetoes:
        # T27: veto, które nie pasuje do żadnego wiersza, jest raportowane jako UNMATCHED_VETO
        print(f"WARNING: UNMATCHED_VETO: Found {len(unmatched_vetoes)} unmatched vetoes:", file=sys.stderr)
        for v in unmatched_vetoes:
            print(f"  - {v}", file=sys.stderr)
            
    current_time = now()
    min_kickoff = current_time + timedelta(minutes=15)
    max_price_age = timedelta(minutes=config.price_max_age_min)
    
    coupon = build_coupon(
        sheet_rows=sheet_rows,
        fixtures=fixtures,
        offers=offers,
        vetoes=vetoes,
        current_time=current_time,
        min_kickoff=min_kickoff,
        max_price_age=max_price_age
    )
    
    coupon_json_path = runs_dir / "06_coupon.json"
    coupon_md_path = runs_dir / "06_coupon.md"
    
    with open(coupon_json_path, "w", encoding="utf-8") as f:
        json.dump(coupon.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
        
    with open(coupon_md_path, "w", encoding="utf-8") as f:
        f.write(f"# Kupon ({current_time.strftime('%Y-%m-%d %H:%M:%S')} UTC)\n\n")
        if not coupon.singles:
            f.write("Brak zakładów (pusty slate lub wszystkie odrzucone).\n")
        else:
            f.write("## Single\n\n")
            f.write("| Mecz | Kickoff | Rynek | Linia | n | Środek | p_central | market_p | p_bar | req_odds | off_odds | Nadwyżka |\n")
            f.write("|---|---|---|---|---|---|---|---|---|---|---|---|\n")
            for r in coupon.singles:
                subject_str = f" ({r.subject})" if r.subject else ""
                market_display = f"{r.market}{subject_str} {r.line} {r.direction}"
                mp_str = f"{r.market_p:.3f}" if r.market_p is not None else "-"
                f.write(f"| {r.match_name} | {r.kickoff_utc.strftime('%H:%M')} | {market_display} | {r.line} | {r.sample_size} | {r.centre:.2f} | {r.p_central:.3f} | {mp_str} | {r.p_bar:.3f} | {r.required_odds:.2f} | **{r.offered_odds:.2f}** | +{r.surplus:.4f} |\n")
                
    if not vetoes_path.exists():
        with open(vetoes_path, "w", encoding="utf-8") as f:
            f.write("[]\n")
            
    summary = {
        "stage": "COUPON",
        "verdict": "OK",
        "metrics": {
            "selected": len(coupon.singles),
            "unmatched_vetoes": len(unmatched_vetoes)
        },
        "output_path": str(coupon_json_path)
    }
    print(f"SOFA_SUMMARY: {json.dumps(summary)}")

if __name__ == "__main__":
    main()
