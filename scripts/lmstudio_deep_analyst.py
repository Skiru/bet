#!/usr/bin/env python3
"""LM Studio Deep Analyst — per-candidate analysis using local Gemma 4 31B.

For each candidate event, feeds ALL available data to local LLM and gets back structured
analysis: market rankings, bear/bull cases, upset risk, recommended markets.

Replaces gemini_deep_analyst.py. Same interface, same schemas, local inference.

Usage:
    python3 scripts/lmstudio_deep_analyst.py --date 2026-05-27 --verbose
    python3 scripts/lmstudio_deep_analyst.py --date 2026-05-27 --event "Arsenal vs Chelsea"
    python3 scripts/lmstudio_deep_analyst.py --date 2026-05-27 --top 20
"""

import argparse
import datetime
import json
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from bet.schemas.llm_responses import CandidateDeepAnalysis
from bet.api_clients.lmstudio_client import LMStudioClient, LMStudioNotAvailableError, LMStudioError

logger = logging.getLogger(__name__)

DATA_DIR = ROOT_DIR / "betting" / "data"

SYSTEM_PROMPT = """You are a professional sports betting analyst with deep expertise in statistical 
markets. You are given comprehensive statistical data for a sporting event and must produce 
a structured analysis.

Your analysis MUST:
1. Recommend STATISTICAL markets FIRST (corners, fouls, cards, shots, totals, games, sets, 
   points, aces, blocks) BEFORE outcome markets (winner, ML, 1X2). Statistical markets 
   accumulate, are style-driven, survive in-match chaos, and are mispriced by bookmakers.

2. For each recommended market: provide a clear bull_case (why it wins), bear_case (why it 
   loses), key supporting stats, and risk factors.

3. Assess upset risk (0-1 scale) with specific reasoning.

4. Flag context factors: motivation_low, key_player_out, derby_match, relegation_battle, 
   dead_rubber, fixture_congestion, weather_factor, etc.

5. Set overall confidence (0-1) reflecting data quality and analysis certainty.

6. Assess data quality: FULL (>7/10 stat keys available), PARTIAL (4-6/10), MINIMAL (<4/10).

Base your analysis ONLY on the data provided. Do NOT invent statistics."""


def analyze_candidate(
    candidate: dict,
    stats_data: dict | None = None,
    model: str | None = None,
) -> CandidateDeepAnalysis | None:
    """Deep per-candidate analysis using LM Studio.

    Args:
        candidate: Candidate dict with event info, stats, safety scores
        stats_data: Additional stats from DB (team_form, standings, etc.)
        model: Override model name (optional)

    Returns:
        CandidateDeepAnalysis or None on failure
    """
    try:
        client = LMStudioClient()
    except LMStudioNotAvailableError:
        logger.warning("LM Studio not available for deep analysis")
        return None

    event_name = candidate.get("event", candidate.get("event_name", "Unknown"))
    sport = candidate.get("sport", "unknown")

    data_prompt = _build_data_prompt(candidate, stats_data)

    full_prompt = f"""--- EVENT DATA ---
Event: {event_name}
Sport: {sport}
Competition: {candidate.get('competition', 'Unknown')}

{data_prompt}
--- END DATA ---

Analyze this event. Recommend markets with full bull/bear cases."""

    try:
        response = client.generate(
            prompt=full_prompt,
            system_prompt=SYSTEM_PROMPT,
            model=model,
            response_schema=CandidateDeepAnalysis,
        )

        if response.parsed and isinstance(response.parsed, CandidateDeepAnalysis):
            analysis = response.parsed
            analysis.event = event_name
            analysis.sport = sport
            analysis.competition = candidate.get("competition", "")
            logger.info(
                f"[{event_name}] LMStudio analysis: "
                f"{len(analysis.recommended_markets)} markets, "
                f"confidence={analysis.overall_confidence:.2f}, "
                f"upset_risk={analysis.upset_risk_score:.2f}"
            )
            return analysis

        logger.warning(f"[{event_name}] No structured analysis from LM Studio")
        return None

    except LMStudioNotAvailableError:
        logger.warning("LM Studio not available")
        return None
    except LMStudioError as e:
        logger.error(f"[{event_name}] LM Studio error: {e}")
        return None
    except Exception as e:
        logger.error(f"[{event_name}] Unexpected error: {e}")
        return None


def compute_agreement_score(
    python_top_market: str,
    python_safety: float,
    llm_analysis: CandidateDeepAnalysis,
) -> float:
    """Compute agreement between Python safety scores and LLM recommendations.

    Returns 0-1 score where:
    - 1.0 = Both agree on top market
    - 0.5 = LLM recommends Python's top market but not as #1
    - 0.0 = Complete disagreement
    """
    if not llm_analysis.recommended_markets:
        return 0.0

    python_market_lower = python_top_market.lower()

    for i, gm in enumerate(llm_analysis.recommended_markets):
        if _markets_similar(python_market_lower, gm.market_name.lower()):
            return max(0.0, 1.0 - (i * 0.2))

    return 0.0


def batch_analyze(
    candidates: list[dict],
    date: str,
    top_n: int | None = None,
    event_filter: str | None = None,
) -> list[tuple[dict, CandidateDeepAnalysis | None]]:
    """Batch analyze candidates with LM Studio."""
    if event_filter:
        candidates = [
            c for c in candidates
            if event_filter.lower() in (c.get("event", "") + c.get("event_name", "")).lower()
        ]

    if top_n:
        candidates = sorted(
            candidates,
            key=lambda c: c.get("best_safety_score", c.get("safety_score", 0)),
            reverse=True,
        )[:top_n]

    results = []
    total = len(candidates)
    for i, candidate in enumerate(candidates):
        event_name = candidate.get("event", candidate.get("event_name", "?"))
        logger.info(f"[{i+1}/{total}] Analyzing: {event_name}")

        analysis = analyze_candidate(candidate)
        results.append((candidate, analysis))

        if analysis:
            logger.info(f"  → {len(analysis.recommended_markets)} markets recommended")
        else:
            logger.warning(f"  → Analysis failed")

    return results


def _build_data_prompt(candidate: dict, stats_data: dict | None = None) -> str:
    """Build comprehensive data prompt from candidate and stats."""
    parts = []

    # Basic info
    parts.append(f"Home: {candidate.get('home_team', candidate.get('team_a', 'Unknown'))}")
    parts.append(f"Away: {candidate.get('away_team', candidate.get('team_b', 'Unknown'))}")

    # Safety scores if available
    if candidate.get("markets"):
        parts.append("\n--- MARKET SAFETY SCORES ---")
        for m in candidate["markets"][:10]:
            parts.append(
                f"  {m.get('market', '?')}: safety={m.get('safety', 0):.2f}, "
                f"hit_l10={m.get('hit_rate_l10', '?')}, hit_h2h={m.get('hit_rate_h2h', '?')}, "
                f"line={m.get('line', '?')}"
            )

    # Team form from stats_data
    if stats_data:
        if stats_data.get("home_form"):
            parts.append(f"\n--- HOME TEAM FORM (L10) ---")
            parts.append(json.dumps(stats_data["home_form"], indent=2, ensure_ascii=False)[:2000])
        if stats_data.get("away_form"):
            parts.append(f"\n--- AWAY TEAM FORM (L10) ---")
            parts.append(json.dumps(stats_data["away_form"], indent=2, ensure_ascii=False)[:2000])
        if stats_data.get("h2h"):
            parts.append(f"\n--- H2H DATA ---")
            parts.append(json.dumps(stats_data["h2h"], indent=2, ensure_ascii=False)[:1500])

    # Odds if available
    if candidate.get("odds"):
        parts.append(f"\n--- ODDS ---")
        parts.append(json.dumps(candidate["odds"], indent=2, ensure_ascii=False)[:1000])

    # Data quality
    dq = candidate.get("data_quality", candidate.get("data_quality_score", "UNKNOWN"))
    parts.append(f"\nData quality: {dq}")

    return "\n".join(parts)


def _markets_similar(m1: str, m2: str) -> bool:
    """Check if two market names refer to the same market."""
    normalize = lambda s: s.replace("_", " ").replace("-", " ").replace("over", "o").replace("under", "u").strip()
    return normalize(m1) == normalize(m2) or m1 in m2 or m2 in m1


def main():
    parser = argparse.ArgumentParser(description="LM Studio Deep Analyst (Local Inference)")
    parser.add_argument("--date", default=datetime.datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--event", help="Filter to specific event name")
    parser.add_argument("--top", type=int, help="Analyze top N candidates by safety score")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    # Load candidates from S3 output
    s3_file = DATA_DIR / f"{args.date}_s3_deep_stats.json"
    if not s3_file.exists():
        logger.error(f"S3 output not found: {s3_file}")
        sys.exit(1)

    candidates = json.loads(s3_file.read_text(encoding="utf-8"))
    if isinstance(candidates, dict):
        candidates = candidates.get("candidates", candidates.get("results", []))

    logger.info(f"Loaded {len(candidates)} candidates from S3")

    results = batch_analyze(candidates, args.date, top_n=args.top, event_filter=args.event)

    # Save results
    output_file = DATA_DIR / f"{args.date}_lmstudio_analysis.json"
    output_data = []
    analyzed = 0
    for cand, analysis in results:
        entry = {"event": cand.get("event", cand.get("event_name", "?"))}
        if analysis:
            entry["analysis"] = analysis.model_dump()
            analyzed += 1
        else:
            entry["analysis"] = None
        output_data.append(entry)

    output_file.write_text(json.dumps(output_data, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = {
        "verdict": "OK" if analyzed > 0 else "PARTIAL",
        "candidates_total": len(candidates),
        "candidates_analyzed": analyzed,
        "analysis_success_rate": f"{analyzed/max(len(results),1)*100:.0f}%",
        "output_file": str(output_file),
    }
    print(f"AGENT_SUMMARY:{json.dumps(summary)}")


if __name__ == "__main__":
    main()
