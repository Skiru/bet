#!/usr/bin/env python3
"""Gemini Deep Analyst — per-candidate "second opinion" using Gemini with deep thinking.

For each candidate event, feeds ALL available data to Gemini and gets back structured
analysis: market rankings, bear/bull cases, upset risk, recommended markets.

IMPORTANT: This COMPLEMENTS Python safety scores. It does NOT replace them.
agreement_score tracks when Python and Gemini agree → higher confidence.

Feature flag: --gemini flag on deep_stats_report.py.

Usage:
    python3 scripts/gemini_deep_analyst.py --date 2026-05-12 --verbose
    python3 scripts/gemini_deep_analyst.py --date 2026-05-12 --event "Arsenal vs Chelsea"
    python3 scripts/gemini_deep_analyst.py --date 2026-05-12 --top 20
"""

import argparse
import datetime
import json
import logging
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from bet.schemas.gemini_responses import CandidateDeepAnalysis, MarketAnalysis
from bet.db.connection import get_db
from api_clients.gemini_client import GeminiClient, GeminiNotConfiguredError, GeminiError

logger = logging.getLogger(__name__)

DATA_DIR = ROOT_DIR / "betting" / "data"

SYSTEM_PROMPT = """You are a professional sports betting analyst with deep expertise in statistical 
markets. You are given comprehensive statistical data for a sporting event and must produce 
a structured analysis.

Your analysis MUST:
1. Recommend STATISTICAL markets FIRST (corners, fouls, cards, shots, totals, games, sets, 
   points, aces, blocks) BEFORE outcome markets (winner, ML, 1X2). Statistical markets 
   accumulate, are style-driven, survive in-match chaos, and are mispriced by bookmakers.
   This is the core betting edge.

2. For each recommended market: provide a clear bull_case (why it wins), bear_case (why it 
   loses), key supporting stats, and risk factors.

3. Assess upset risk (0-1 scale) with specific reasoning: motivation, injuries, travel, 
   historical patterns, venue factors.

4. Flag context factors: motivation_low, key_player_out, derby_match, relegation_battle, 
   dead_rubber, fixture_congestion, weather_factor, etc.

5. Set overall confidence (0-1) reflecting data quality and analysis certainty. If data 
   is insufficient, say so explicitly and lower confidence accordingly.

6. Assess data quality: FULL (>7/10 stat keys available), PARTIAL (4-6/10), MINIMAL (<4/10).

Base your analysis ONLY on the data provided. Do NOT invent statistics or cite sources 
not in the input. If a field is empty or null, note the data gap."""


def analyze_candidate(
    candidate: dict,
    stats_data: dict | None = None,
    model: str | None = None,
) -> CandidateDeepAnalysis | None:
    """Deep per-candidate analysis using Gemini.

    Args:
        candidate: Candidate dict with event info, stats, safety scores
        stats_data: Additional stats from DB (team_form, standings, etc.)
        model: Override model (default: deep_analysis_model from config)

    Returns:
        CandidateDeepAnalysis or None on failure
    """
    try:
        client = GeminiClient()
    except Exception:
        logger.warning("Gemini not available for deep analysis")
        return None

    # Build the data prompt
    event_name = candidate.get("event", candidate.get("event_name", "Unknown"))
    sport = candidate.get("sport", "unknown")

    data_prompt = _build_data_prompt(candidate, stats_data)

    full_prompt = f"""{SYSTEM_PROMPT}

--- EVENT DATA ---
Event: {event_name}
Sport: {sport}
Competition: {candidate.get('competition', 'Unknown')}

{data_prompt}
--- END DATA ---

Analyze this event. Recommend markets with full bull/bear cases."""

    try:
        target_model = model or client.deep_analysis_model
        response = client.generate(
            prompt=full_prompt,
            model=target_model,
            response_schema=CandidateDeepAnalysis,
        )

        if response.parsed and isinstance(response.parsed, CandidateDeepAnalysis):
            analysis = response.parsed
            analysis.event = event_name
            analysis.sport = sport
            analysis.competition = candidate.get("competition", "")
            logger.info(
                f"[{event_name}] Gemini analysis: "
                f"{len(analysis.recommended_markets)} markets, "
                f"confidence={analysis.overall_confidence:.2f}, "
                f"upset_risk={analysis.upset_risk_score:.2f}"
            )
            return analysis

        # Try text parsing fallback
        if response.text:
            try:
                analysis = CandidateDeepAnalysis.model_validate_json(response.text)
                analysis.event = event_name
                analysis.sport = sport
                return analysis
            except Exception:
                pass

        logger.warning(f"[{event_name}] No structured analysis from Gemini")
        return None

    except GeminiNotConfiguredError:
        logger.warning("Gemini not configured")
        return None
    except GeminiError as e:
        logger.error(f"[{event_name}] Gemini error: {e}")
        return None
    except Exception as e:
        logger.error(f"[{event_name}] Unexpected error: {e}")
        return None


def compute_agreement_score(
    python_top_market: str,
    python_safety: float,
    gemini_analysis: CandidateDeepAnalysis,
) -> float:
    """Compute agreement between Python safety scores and Gemini recommendations.

    Returns 0-1 score where:
    - 1.0 = Both agree on top market
    - 0.5 = Gemini recommends Python's top market but not as #1
    - 0.0 = Complete disagreement
    """
    if not gemini_analysis.recommended_markets:
        return 0.0

    python_market_lower = python_top_market.lower()

    for i, gm in enumerate(gemini_analysis.recommended_markets):
        if _markets_similar(python_market_lower, gm.market_name.lower()):
            # Agreement decays with rank position
            return max(0.0, 1.0 - (i * 0.2))

    return 0.0


def batch_analyze(
    candidates: list[dict],
    date: str,
    top_n: int | None = None,
    event_filter: str | None = None,
) -> list[tuple[dict, CandidateDeepAnalysis | None]]:
    """Batch analyze candidates with Gemini.

    Returns list of (candidate, analysis) tuples.
    """
    # Filter if needed
    if event_filter:
        candidates = [
            c for c in candidates
            if event_filter.lower() in (c.get("event", "") + c.get("event_name", "")).lower()
        ]

    # Sort by safety score and take top N
    if top_n:
        candidates = sorted(
            candidates,
            key=lambda c: c.get("best_safety_score", c.get("safety_score", 0)),
            reverse=True,
        )[:top_n]

    results = []
    for i, c in enumerate(candidates):
        event = c.get("event", c.get("event_name", f"Candidate {i+1}"))
        logger.info(f"[{i+1}/{len(candidates)}] Analyzing: {event}")

        analysis = analyze_candidate(c)
        results.append((c, analysis))

        # Small delay between calls to respect rate limits
        if i < len(candidates) - 1:
            time.sleep(1)

    return results


def _build_data_prompt(candidate: dict, stats_data: dict | None = None) -> str:
    """Build a comprehensive data prompt from candidate and stats."""
    sections = []

    # Basic info
    home = candidate.get("home_team", candidate.get("team_a", ""))
    away = candidate.get("away_team", candidate.get("team_b", ""))
    if home and away:
        sections.append(f"Home: {home}\nAway: {away}")

    # Safety scores from Python
    safety = candidate.get("best_safety_score", candidate.get("safety_score"))
    if safety:
        sections.append(f"Python Safety Score: {safety}")

    best_market = candidate.get("best_market_name", candidate.get("best_market", ""))
    if best_market:
        sections.append(f"Python Top Market: {best_market}")

    # Stats summary
    stats_summary = candidate.get("stats_summary", {})
    if isinstance(stats_summary, str):
        try:
            stats_summary = json.loads(stats_summary)
        except Exception:
            stats_summary = {}

    if stats_summary:
        sections.append(f"Stats Summary: {json.dumps(stats_summary, indent=2)}")

    # Ranking data
    ranking = candidate.get("ranking_json", candidate.get("ranking", ""))
    if ranking:
        if isinstance(ranking, str):
            try:
                ranking = json.loads(ranking)
            except Exception:
                pass
        if isinstance(ranking, (dict, list)):
            sections.append(f"Market Ranking: {json.dumps(ranking, indent=2)}")

    # Additional stats from DB
    if stats_data:
        for key, value in stats_data.items():
            if value:
                sections.append(f"{key}: {json.dumps(value, indent=2) if isinstance(value, (dict, list)) else value}")

    return "\n\n".join(sections) if sections else "Minimal data available."


def _markets_similar(a: str, b: str) -> bool:
    """Check if two market names refer to the same market."""
    # Normalize common variations
    for old, new in [("over", "o"), ("under", "u"), ("_", " "), ("total ", "")]:
        a = a.replace(old, new)
        b = b.replace(old, new)

    a = a.strip()
    b = b.strip()

    if a == b:
        return True
    if a in b or b in a:
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Gemini Deep Analyst (P2)")
    parser.add_argument("--date", default=datetime.datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--event", help="Filter to specific event")
    parser.add_argument("--top", type=int, help="Analyze only top N candidates by safety score")
    parser.add_argument("--input", help="Path to S3 deep stats JSON")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    # Load candidates from S3 output
    input_path = Path(args.input) if args.input else DATA_DIR / f"{args.date}_s3_deep_stats.json"
    if not input_path.exists():
        print(f"ERROR: S3 output not found at {input_path}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(input_path.read_text(encoding="utf-8"))
    candidates = data.get("analyses", data.get("candidates", []))

    logger.info(f"Loaded {len(candidates)} candidates from {input_path.name}")

    results = batch_analyze(candidates, args.date, args.top, args.event)

    # Report
    analyzed = sum(1 for _, a in results if a is not None)
    total_markets = sum(
        len(a.recommended_markets) for _, a in results if a is not None
    )
    avg_confidence = 0.0
    if analyzed > 0:
        avg_confidence = sum(
            a.overall_confidence for _, a in results if a is not None
        ) / analyzed

    if args.verbose:
        for c, a in results:
            if a:
                print(json.dumps(a.model_dump(), ensure_ascii=False, indent=2))

    summary = {
        "verdict": "OK" if analyzed > 0 else "FAILED",
        "candidates_input": len(candidates),
        "candidates_analyzed": analyzed,
        "total_markets_recommended": total_markets,
        "avg_confidence": round(avg_confidence, 3),
    }
    print(f"AGENT_SUMMARY:{json.dumps(summary)}")


if __name__ == "__main__":
    main()
