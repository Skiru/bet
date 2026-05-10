#!/usr/bin/env python3
"""Structured agent-friendly output for pipeline scripts.

All pipeline scripts produce output FOR AGENTS that monitor, react, and decide.
This module provides a consistent output layer:

- When verbose=True (--verbose / -v): JSON-line events for real-time agent monitoring.
  Each line is parseable JSON with step, event type, and structured data.
- When verbose=False: human-readable output (backwards compatible).
- Summary is ALWAYS JSON — the agent reads this as the script's final result.

Usage in any script:
    from agent_output import AgentOutput, add_agent_args

    # In argparse setup:
    add_agent_args(parser)

    # After parsing args:
    out = AgentOutput("s1_scan", verbose=args.verbose, stop_on_error=args.stop_on_error)

    # During execution:
    out.progress(5, 20, "flashscore.com football")
    out.event("url_fetched", url="...", events=12)
    out.warning("403 from totalcorner.com", domain="totalcorner.com")
    out.error("timeout", url="...", recoverable=True)

    # At the end:
    out.summary(verdict="OK", metrics={...}, issues=[...])
"""

import argparse
import json
import sys
from datetime import datetime


def add_agent_args(parser: argparse.ArgumentParser) -> None:
    """Add standard agent-friendly arguments to any script's argparse.

    Adds: --verbose/-v, --stop-on-error
    For --sport filtering, call add_sport_filter_arg() separately.
    """
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Agent-friendly JSON-line output (structured events for monitoring agent)",
    )
    parser.add_argument(
        "--stop-on-error", action="store_true",
        help="Stop on first critical error instead of log-and-continue (for agent-monitored runs)",
    )


def add_sport_filter_arg(parser: argparse.ArgumentParser) -> None:
    """Add --sport filter argument for scripts that process per-sport data."""
    parser.add_argument(
        "--sport",
        help="Process only this sport (e.g., football, tennis). Default: all configured sports.",
    )


class AgentOutput:
    """Structured output manager for pipeline scripts.

    Provides consistent logging that agents can parse and react to in real-time.
    """

    def __init__(self, step: str, *, verbose: bool = False, stop_on_error: bool = False):
        self.step = step
        self.verbose = verbose
        self.stop_on_error = stop_on_error
        self._issues: list[dict] = []
        self._error_count = 0
        self._warning_count = 0

    # ── Core output methods ──────────────────────────────────────────

    def event(self, event_type: str, **data) -> None:
        """Emit a structured event. Always prints in verbose mode; human-readable otherwise."""
        if self.verbose:
            payload = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "step": self.step,
                "event": event_type,
                **data,
            }
            print(json.dumps(payload, ensure_ascii=False, default=str), flush=True)
        else:
            # Human-readable fallback
            detail = data.get("detail", data.get("message", ""))
            prefix = f"[{self.step}]"
            if detail:
                print(f"{prefix} {event_type}: {detail}", flush=True)
            elif data:
                parts = " ".join(f"{k}={v}" for k, v in data.items())
                print(f"{prefix} {event_type} — {parts}", flush=True)
            else:
                print(f"{prefix} {event_type}", flush=True)

    def progress(self, current: int, total: int, detail: str = "") -> None:
        """Emit progress event — agent tracks completion percentage."""
        pct = round(current / total * 100) if total > 0 else 0
        if self.verbose:
            self.event("progress", current=current, total=total, pct=pct, detail=detail)
        else:
            tag = f" — {detail}" if detail else ""
            print(f"[{self.step}] [{current}/{total} {pct}%]{tag}", flush=True)

    def warning(self, message: str, **context) -> None:
        """Emit warning — agent should note but not stop."""
        self._warning_count += 1
        self._issues.append({"level": "warning", "message": message, **context})
        if self.verbose:
            self.event("warning", message=message, **context)
        else:
            print(f"[{self.step}] ⚠ {message}", flush=True)

    def error(self, message: str, *, recoverable: bool = True, **context) -> None:
        """Emit error — agent should react. If stop_on_error and not recoverable, exit."""
        self._error_count += 1
        self._issues.append({"level": "error", "message": message, "recoverable": recoverable, **context})
        if self.verbose:
            self.event("error", message=message, recoverable=recoverable, **context)
        else:
            icon = "⚠" if recoverable else "✗"
            print(f"[{self.step}] {icon} ERROR: {message}", flush=True)

        if self.stop_on_error and not recoverable:
            self.summary(verdict="FAILED", metrics={"error_count": self._error_count},
                         issues=[])  # self._issues already merged inside summary()
            sys.exit(2)

    def sport_start(self, sport: str, **context) -> None:
        """Signal start of processing for a sport — agent tracks per-sport progress."""
        self.event("sport_start", sport=sport, **context)

    def sport_done(self, sport: str, **metrics) -> None:
        """Signal completion of a sport — agent evaluates per-sport results."""
        self.event("sport_done", sport=sport, **metrics)

    def candidate(self, event_name: str, sport: str, **data) -> None:
        """Emit per-candidate event — agent monitors analysis quality."""
        self.event("candidate", event_name=event_name, sport=sport, **data)

    # ── Summary (ALWAYS JSON — the agent's final read) ───────────────

    def summary(self, *, verdict: str = "OK", metrics: dict | None = None,
                issues: list | None = None) -> None:
        """Print final structured summary. ALWAYS JSON, both modes.

        verdict: OK (clean), PARTIAL (>0 warnings/recoverable errors), FAILED (critical)
        metrics: key numbers the agent evaluates (counts, rates, scores)
        issues: list of problems found (agent decides severity)
        """
        # Auto-compute verdict if not overridden
        if verdict == "OK" and self._error_count > 0:
            verdict = "PARTIAL"

        all_issues = (issues or []) + self._issues

        payload = {
            "step": self.step,
            "verdict": verdict,
            "metrics": metrics or {},
            "issues": all_issues[:50],  # Cap to avoid massive output
            "counts": {
                "errors": self._error_count,
                "warnings": self._warning_count,
            },
            "ts": datetime.now().isoformat(timespec="seconds"),
        }
        # Always JSON for the summary — agent parses this
        print(f"\nAGENT_SUMMARY:{json.dumps(payload, ensure_ascii=False, default=str)}", flush=True)

    # ── Utility ──────────────────────────────────────────────────────

    @property
    def has_errors(self) -> bool:
        return self._error_count > 0

    @property
    def issues(self) -> list[dict]:
        return list(self._issues)
