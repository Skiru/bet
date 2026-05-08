#!/usr/bin/env python3
"""Agent communication protocol for pipeline steps.

Each pipeline step that requires agent review writes a structured JSON
input file. Agents (via Copilot) read the input, perform qualitative
analysis, and write a review JSON response. The orchestrator reads
agent responses and merges enrichments into the pipeline state.

All files are written to: betting/data/agent_reviews/{date}/
- {step_id}_input.json  — written by pipeline after step completes
- {step_id}_review.json — written by agent (manually or via Copilot)
"""

import json
from datetime import datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).parent.parent
REVIEWS_DIR = ROOT_DIR / "betting" / "data" / "agent_reviews"

# ---------------------------------------------------------------------------
# Step → Agent configuration
# ---------------------------------------------------------------------------
STEP_AGENT_CONFIG = {
    "s1_scan": {
        "agent": "bet-scanner",
        "task": "Verify 14-sport coverage, cross-validate fixtures ≥2 sources, check deep-link discovery yield, flag source failures, ensure ≥50 unique events",
        "required_input": ["scan_summary.json"],
        "output_metrics": ["total_events", "sports_covered", "source_failures", "deep_link_yield"],
    },
    "s1e_shortlist": {
        "agent": "bet-scanner",
        "task": "Review shortlist for sport diversity (≥8 sports), KEY sport coverage (≥60% Football/Tennis/Basketball/Volleyball), verify ALL candidates included, flag missing major leagues",
        "required_input": ["{date}_s2_shortlist.json"],
        "output_metrics": ["total_candidates", "sport_distribution", "key_sport_pct", "missing_leagues"],
    },
    "s2_tipster": {
        "agent": "bet-scout",
        "task": "Read FULL tipster arguments, assess quality, check independence, discover angles stats missed, promote watchlist picks",
        "required_input": ["tipster_aggregation_{date}.json"],
        "output_metrics": ["tipster_count", "event_coverage", "consensus_picks"],
    },
    "s3_deep_stats": {
        "agent": "bet-statistician",
        "task": "Interpret safety scores, find edge mechanisms, fetch missing stats, write ANALYTICAL REASONING per candidate",
        "required_input": ["{date}_s3_deep_stats.json"],
        "output_metrics": ["candidates_analyzed", "avg_safety_score", "top_markets"],
    },
    "s4_odds_eval": {
        "agent": "bet-valuator",
        "task": "Cross-validate pricing across sources, reason about mispricing, assess edge durability, calculate relative value",
        "required_input": ["{date}_s3_deep_stats.json"],
        "output_metrics": ["candidates_with_ev", "avg_ev", "ev_positive_count"],
    },
    "s5_context": {
        "agent": "bet-challenger",
        "task": "Assess REAL market impact of context flags, model motivation effects, identify compounding risk factors",
        "required_input": ["{date}_s3_deep_stats.json", "weather_{date}.json"],
        "output_metrics": ["weather_flags", "injury_flags", "motivation_adjustments"],
    },
    "s6_upset_risk": {
        "agent": "bet-challenger",
        "task": "Score upset risk with sport-specific contextual reasoning, apply Paradox Rule",
        "required_input": ["{date}_s3_deep_stats.json"],
        "output_metrics": ["high_risk_count", "medium_risk_count", "low_risk_count"],
    },
    "s7_gate": {
        "agent": "bet-challenger",
        "task": "Build qualitative bear cases, audit assumptions, find historical analogies, Bayesian-update confidence",
        "required_input": ["{date}_s7_gate_results.json"],
        "output_metrics": ["approved_count", "extended_count", "rejected_count"],
    },
    "s8_coupons": {
        "agent": "bet-builder",
        "task": "Review portfolio strategically, check hidden correlations, adjust stakes by conviction, V1-V10 + §S8.FINAL",
        "required_input": ["{date}.json"],
        "output_metrics": ["coupon_count", "total_legs", "total_stake"],
    },
}


def _reviews_dir(date: str) -> Path:
    """Return the agent reviews directory for a given date, creating it if needed."""
    d = REVIEWS_DIR / date
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_step_output(date: str, step_id: str, metrics: dict, artifacts: list[str], step_config: dict | None = None):
    """Write structured agent input file after a pipeline step completes.

    Args:
        date: Betting date (YYYY-MM-DD).
        step_id: Pipeline step identifier (e.g. "s3_deep_stats").
        metrics: Key numeric metrics produced by the step.
        artifacts: List of file paths to full artifacts the agent should read.
        step_config: Override for STEP_AGENT_CONFIG entry. Uses default if None.
    """
    cfg = step_config or STEP_AGENT_CONFIG.get(step_id, {})
    payload = {
        "step_id": step_id,
        "date": date,
        "agent": cfg.get("agent", "unknown"),
        "task": cfg.get("task", ""),
        "metrics": metrics,
        "artifacts": artifacts,
        "expected_output_metrics": cfg.get("output_metrics", []),
        "written_at": datetime.now(ZoneInfo("Europe/Warsaw")).isoformat(),
    }
    out_path = _reviews_dir(date) / f"{step_id}_input.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(out_path)


def read_agent_review(date: str, step_id: str) -> dict | None:
    """Read agent review response if it exists.

    Returns None if no review file found (pipeline proceeds without agent input).
    """
    review_path = _reviews_dir(date) / f"{step_id}_review.json"
    if not review_path.exists():
        return None
    try:
        return json.loads(review_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def merge_agent_enrichments(state: dict, review: dict) -> dict:
    """Merge agent enrichments into pipeline state.

    The review dict is expected to have:
        - agent: str
        - step_id: str
        - status: "approved" | "flagged" | "enriched"
        - flags: list[str]
        - enrichments: dict
        - timestamp: str

    Enrichments are stored in state["agent_reviews"][step_id].
    Flags are appended to state["errors"] if status == "flagged".
    """
    step_id = review.get("step_id", "unknown")
    state.setdefault("agent_reviews", {})[step_id] = {
        "agent": review.get("agent", "unknown"),
        "status": review.get("status", "unknown"),
        "flags": review.get("flags", []),
        "enrichments": review.get("enrichments", {}),
        "timestamp": review.get("timestamp", ""),
    }

    # Surface agent flags as warnings (non-blocking)
    if review.get("status") == "flagged":
        for flag in review.get("flags", []):
            state.setdefault("errors", []).append(f"[agent:{step_id}] {flag}")

    return state
