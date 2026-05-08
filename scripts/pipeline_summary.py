#!/usr/bin/env python3
"""S10 Pipeline Summary — final summary with full pipeline metrics.

Extracted from pipeline_orchestrator.py (Phase 3.4).
"""

import sys
from datetime import datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Paths (same as orchestrator)
# ---------------------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).parent
ROOT_DIR = SCRIPTS_DIR.parent
DATA_DIR = ROOT_DIR / "betting" / "data"

# Add scripts/ and src/ to path for imports
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(ROOT_DIR / "src"))


def run_summary(date: str, state: dict) -> tuple[bool, str]:
    """S10: Final summary with full pipeline metrics."""
    # Lazy import to avoid circular dependency with orchestrator
    from pipeline_orchestrator import PIPELINE_STEPS

    step_data = state.get("step_data", {})

    # Calculate pipeline duration
    started = state.get("started_at", "")
    now_str = datetime.now(ZoneInfo("Europe/Warsaw")).isoformat()
    duration = "?"
    if started:
        try:
            start_dt = datetime.fromisoformat(started)
            end_dt = datetime.now(ZoneInfo("Europe/Warsaw"))
            elapsed = end_dt - start_dt
            minutes = int(elapsed.total_seconds() // 60)
            seconds = int(elapsed.total_seconds() % 60)
            duration = f"{minutes}m {seconds}s"
        except Exception:
            pass

    summary_lines = [
        "",
        "═══════════════════════════════════════════════════════════",
        f"  PIPELINE COMPLETE — {date}",
        f"  Duration: {duration}",
        "═══════════════════════════════════════════════════════════",
        "",
        "📊 ANALYSIS SUMMARY:",
        f"  S3 Deep Stats: {step_data.get('s3_with_data', '?')}/{step_data.get('s3_count', '?')} candidates analyzed",
        f"  S7 Gate: {step_data.get('s7_approved', '?')} approved, {step_data.get('s7_extended', '?')} extended",
    ]

    if step_data.get("s8_no_bet"):
        summary_lines.append("  S8 Coupons: NO BET DAY")
    else:
        summary_lines.append(
            f"  S8 Coupons: {step_data.get('s8_core', '?')} core, {step_data.get('s8_combos', '?')} combos"
        )

    # Parallel enrichment results
    parallel = step_data.get("parallel_results", {})
    if parallel:
        enrichment_parts = []
        for name, ok in parallel.items():
            enrichment_parts.append(f"{name}: {'✓' if ok else '✗'}")
        summary_lines.append(f"  Enrichment: {', '.join(enrichment_parts)}")

    # Step completion status
    steps_status = state.get("steps", {})
    completed = sum(1 for v in steps_status.values() if isinstance(v, dict) and v.get("status") == "completed")
    failed = sum(1 for v in steps_status.values() if isinstance(v, dict) and v.get("status") == "failed")
    skipped = sum(1 for v in steps_status.values() if isinstance(v, dict) and v.get("status") == "skipped")
    summary_lines.extend([
        "",
        f"📋 STEPS: {completed} completed, {failed} failed, {skipped} skipped",
    ])

    # Errors summary
    errors = state.get("errors", [])
    if errors:
        summary_lines.append(f"  ⚠ {len(errors)} errors logged:")
        for err in errors[-3:]:
            summary_lines.append(f"    - {err[:120]}")

    # Build list of agent checkpoints that completed
    agent_checkpoints = []
    for step in PIPELINE_STEPS:
        agent = step.get("agent_review_required")
        if agent:
            step_status = state.get("steps", {}).get(step["id"], {}).get("status", "")
            if step_status == "completed":
                agent_checkpoints.append((step["id"], agent, step.get("agent_task", "")))

    summary_lines.extend([
        "",
        "📁 OUTPUT FILES:",
        f"  📊 betting/data/{date}_s3_deep_stats.md",
        f"  ✅ betting/data/{date}_s7_gate_results.md",
        f"  🎫 betting/coupons/{date}.md",
        f"  📦 betting/coupons/{date}.json",
    ])

    if agent_checkpoints:
        summary_lines.extend([
            "",
            "═══════════════════════════════════════════════════════════",
            "🤖 AGENT REVIEW CHECKPOINTS (MANDATORY — DO NOT SKIP)",
            "═══════════════════════════════════════════════════════════",
            "",
            "The pipeline produced RAW DATA. The orchestrator MUST now",
            "spawn specialist agents for deep analysis at each checkpoint:",
            "",
        ])
        for step_id, agent, task in agent_checkpoints:
            summary_lines.append(f"  [{step_id}] → {agent}: {task}")
        summary_lines.extend([
            "",
            "Script output is NOT final analysis. Agents add: edge",
            "discovery, cross-source verification, bear cases, strategic",
            "reasoning, and Polish-language coupon descriptions.",
            "═══════════════════════════════════════════════════════════",
        ])
    else:
        summary_lines.append("")
        summary_lines.append("═══════════════════════════════════════════════════════════")

    msg = "\n".join(summary_lines)
    print(msg)

    state["completed_at"] = now_str

    # Save summary metrics to pipeline_runs DB
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import PipelineRepo
        summary_stats = {
            "duration": duration,
            "s3_count": step_data.get("s3_count"),
            "s3_with_data": step_data.get("s3_with_data"),
            "s7_approved": step_data.get("s7_approved"),
            "s7_extended": step_data.get("s7_extended"),
            "s8_core": step_data.get("s8_core"),
            "s8_combos": step_data.get("s8_combos"),
            "s8_no_bet": step_data.get("s8_no_bet", False),
            "completed_steps": completed,
            "failed_steps": failed,
            "skipped_steps": skipped,
            "errors_count": len(errors),
            "parallel_results": step_data.get("parallel_results", {}),
        }
        with get_db() as conn:
            repo = PipelineRepo(conn)
            repo.start_step(date, "s10_summary")
            repo.complete_step(date, "s10_summary", stats=summary_stats)
            conn.commit()
    except Exception as e:
        print(f"  ⚠ DB summary save failed (non-fatal): {e}")

    return True, msg
