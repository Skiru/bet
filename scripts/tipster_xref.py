#!/usr/bin/env python3
"""S2 Tipster Cross-Reference — cross-reference picks with tipster consensus.

Extracted from pipeline_orchestrator.py (Phase 3.3).
"""

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (same as orchestrator)
# ---------------------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).parent
ROOT_DIR = SCRIPTS_DIR.parent
DATA_DIR = ROOT_DIR / "betting" / "data"

# Add scripts/ and src/ to path for imports
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(ROOT_DIR / "src"))


def run_tipster_xref(date: str, state: dict) -> tuple[bool, str]:
    """S2: Cross-reference shortlist with tipster consensus data.

    Enriches shortlist candidates with tipster support, consensus %, and arguments.
    """
    tipster_path = DATA_DIR / f"tipster_aggregation_{date}.json"
    consensus_path = DATA_DIR / f"{date}_tipster_consensus.json"

    # Try both possible tipster data files
    tipster_data = None
    for tpath in [tipster_path, consensus_path]:
        if tpath.exists():
            try:
                tipster_data = json.loads(tpath.read_text(encoding="utf-8"))
                print(f"  → Loaded tipster data from {tpath.name}")
                break
            except (json.JSONDecodeError, OSError):
                continue

    if tipster_data is None:
        return True, "No tipster data available — skipping cross-reference"

    # Parse tips into a lookup
    tips = tipster_data if isinstance(tipster_data, list) else tipster_data.get("tips", [])
    tip_lookup: dict[str, list[dict]] = {}
    for tip in tips:
        home = (tip.get("home") or tip.get("home_team") or "").strip().lower()
        away = (tip.get("away") or tip.get("away_team") or "").strip().lower()
        if home and away:
            key = f"{home}|{away}"
            tip_lookup.setdefault(key, []).append(tip)

    # Load shortlist and cross-reference
    shortlist_path = DATA_DIR / f"{date}_s2_shortlist.json"

    matched = 0
    total = 0
    if shortlist_path.exists():
        try:
            shortlist = json.loads(shortlist_path.read_text(encoding="utf-8"))
            candidates = shortlist.get("candidates", shortlist.get("shortlist", []))
            total = len(candidates)

            for c in candidates:
                home = (c.get("home_team") or "").strip().lower()
                away = (c.get("away_team") or "").strip().lower()
                key = f"{home}|{away}"
                matching_tips = tip_lookup.get(key, [])
                if matching_tips:
                    matched += 1
                    tipster_names = list({t.get("tipster", t.get("source", "unknown")) for t in matching_tips})
                    consensus = len(matching_tips)
                    c["tipster_support"] = {
                        "count": consensus,
                        "tipsters": tipster_names,
                        "tips": matching_tips,
                    }
                    # Also set tipster_count directly for gate_checker compatibility
                    c["tipster_count"] = consensus
                    home_disp = c.get("home_team", "?")
                    away_disp = c.get("away_team", "?")
                    print(f"    ✓ {home_disp} vs {away_disp}: {consensus} tips from {', '.join(tipster_names[:3])}")

            # Save enriched shortlist
            shortlist_path.write_text(
                json.dumps(shortlist, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except (json.JSONDecodeError, OSError) as e:
            print(f"  ⚠ Shortlist enrichment error: {e}")

    n_tips = len(tips)
    return True, f"Tipster cross-reference: {n_tips} tips loaded, {matched}/{total} shortlist candidates matched"
