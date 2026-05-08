#!/usr/bin/env python3
"""S6 Upset Risk Scoring — sport-specific heuristics.

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


def run_upset_risk(date: str, state: dict) -> tuple[bool, str]:
    """S6: Upset risk scoring per candidate with sport-specific heuristics."""
    s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
    if not s3_path.exists():
        return True, "S6: No S3 data — skipping upset risk scoring"

    # Sport-specific upset risk thresholds
    UPSET_THRESHOLDS = {
        "football": {"safety_low": 0.55, "h2h_min": 3, "form_diverge": 0.15},
        "tennis": {"safety_low": 0.50, "h2h_min": 2, "form_diverge": 0.20},
        "basketball": {"safety_low": 0.50, "h2h_min": 3, "form_diverge": 0.10},
        "volleyball": {"safety_low": 0.50, "h2h_min": 3, "form_diverge": 0.15},
        "hockey": {"safety_low": 0.50, "h2h_min": 3, "form_diverge": 0.15},
        "handball": {"safety_low": 0.50, "h2h_min": 2, "form_diverge": 0.15},
        "baseball": {"safety_low": 0.45, "h2h_min": 3, "form_diverge": 0.10},
        "esports": {"safety_low": 0.45, "h2h_min": 2, "form_diverge": 0.20},
    }
    DEFAULT_THRESHOLDS = {"safety_low": 0.50, "h2h_min": 2, "form_diverge": 0.15}

    try:
        s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
        analyses = s3_data.get("analyses", [])
        scored = 0
        elevated = 0
        high_risk = 0

        for analysis in analyses:
            sport = analysis.get("sport", "").lower()
            thresholds = UPSET_THRESHOLDS.get(sport, DEFAULT_THRESHOLDS)
            risk_factors = []

            ranking = analysis.get("ranking", analysis.get("ranking_result", {}).get("ranking", []))
            top_market = ranking[0] if ranking else {}
            safety = top_market.get("safety_score", 0)

            # Factor 1: Low safety score (sport-specific threshold)
            if safety < thresholds["safety_low"]:
                risk_factors.append(f"safety_below_{thresholds['safety_low']} ({safety})")

            # Factor 2: L5 trend diverging from L10 (form instability)
            l5_avg = top_market.get("combined_avg_l5", top_market.get("l5_avg"))
            l10_avg = top_market.get("combined_avg", top_market.get("l10_avg"))
            if l5_avg and l10_avg and l10_avg != 0:
                divergence = abs(l5_avg - l10_avg) / abs(l10_avg)
                if divergence > thresholds["form_diverge"]:
                    direction = "declining" if l5_avg < l10_avg else "surging"
                    risk_factors.append(f"form_{direction} ({divergence:.0%} L5 vs L10)")

            # Factor 3: Missing H2H data
            h2h = analysis.get("h2h", {})
            h2h_meetings = len(h2h.get("meetings", []))
            if h2h_meetings < thresholds["h2h_min"]:
                risk_factors.append(f"h2h_insufficient ({h2h_meetings}/{thresholds['h2h_min']} meetings)")

            # Factor 4: Context flags (weather, injuries)
            context_flags = analysis.get("context_flags", [])
            if any("INJURY" in f for f in context_flags):
                risk_factors.append("key_injury_flagged")
            if any("WEATHER" in f for f in context_flags):
                risk_factors.append("adverse_weather")

            # Factor 5: No EV data (stats-first mode = higher uncertainty)
            if analysis.get("ev") is None:
                risk_factors.append("no_ev_data_statsFirst")

            # Score upset risk
            risk_count = len(risk_factors)
            if risk_count >= 3:
                risk_level = "HIGH"
                high_risk += 1
            elif risk_count >= 1:
                risk_level = "ELEVATED"
                elevated += 1
            else:
                risk_level = "LOW"

            analysis["upset_risk"] = {
                "level": risk_level,
                "factors": risk_factors,
                "factor_count": risk_count,
            }
            analysis.setdefault("flags", [])
            if risk_level != "LOW":
                analysis["flags"].append(f"upset_risk_{risk_level.lower()}")
            scored += 1

            # Verbose per-candidate output
            home = analysis.get("home_team", "?")
            away = analysis.get("away_team", "?")
            marker = {"LOW": "🟢", "ELEVATED": "🟡", "HIGH": "🔴"}[risk_level]
            print(f"    {marker} {home} vs {away} [{sport}]: {risk_level} ({risk_count} factors)")
            if risk_factors:
                for rf in risk_factors[:3]:
                    print(f"       → {rf}")

        s3_path.write_text(
            json.dumps(s3_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return True, f"S6 completed: {scored} candidates scored — {elevated} elevated, {high_risk} high risk"
    except Exception as e:
        return True, f"S6 upset risk error: {e} — continuing without"
