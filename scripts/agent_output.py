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

        # V5: Auto-validate summary structure
        validation_warnings = self.validate_summary(payload)
        if validation_warnings:
            for vw in validation_warnings:
                all_issues.append({"level": "validation_warning", "message": vw})
            # Re-assign issues in payload since we modified all_issues
            payload["issues"] = all_issues[:50]

        # Always JSON for the summary — agent parses this
        print(f"\nAGENT_SUMMARY:{json.dumps(payload, ensure_ascii=False, default=str)}", flush=True)

    @staticmethod
    def validate_summary(payload: dict) -> list[str]:
        """Validate AGENT_SUMMARY structure. Returns list of warning strings (empty = valid).
        
        Checks:
        - verdict is one of OK, PARTIAL, FAILED
        - metrics is a dict with ≥1 entry
        - issues is a list
        - step is a non-empty string
        """
        warnings = []
        
        valid_verdicts = {"OK", "PARTIAL", "FAILED"}
        verdict = payload.get("verdict")
        if verdict not in valid_verdicts:
            warnings.append(f"Invalid verdict '{verdict}' — expected one of {valid_verdicts}")
        
        metrics = payload.get("metrics")
        if not isinstance(metrics, dict):
            warnings.append(f"metrics should be dict, got {type(metrics).__name__}")
        elif len(metrics) == 0:
            warnings.append("metrics dict is empty — should contain ≥1 metric")
        
        issues = payload.get("issues")
        if not isinstance(issues, list):
            warnings.append(f"issues should be list, got {type(issues).__name__}")
        
        step = payload.get("step")
        if not step or not isinstance(step, str):
            warnings.append(f"step should be non-empty string, got '{step}'")
        
        return warnings

    @classmethod
    def validate_input_contract(cls, step_id: str, date: str,
                                contracts: dict | None = None) -> dict:
        """Check whether expected input files/DB tables exist for a pipeline step.
        
        Args:
            step_id: Pipeline step identifier (e.g. 's3_deep_stats', 's7_gate')
            date: Betting date YYYY-MM-DD
            contracts: Optional explicit contracts dict. If None, lazy-imports
                       DATA_FLOW_CONTRACTS from agent_protocol.
        
        Returns:
            {"status": "OK"|"PARTIAL"|"MISSING"|"UNKNOWN",
             "found": [...], "missing": [...], "warnings": [...]}
        """
        from pathlib import Path
        import re
        
        result = {"status": "OK", "found": [], "missing": [], "warnings": []}
        
        # Validate date format to prevent path traversal
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            result["status"] = "UNKNOWN"
            result["warnings"].append(f"Invalid date format: {date!r}")
            return result
        
        # Load contracts
        if contracts is None:
            try:
                from agent_protocol import DATA_FLOW_CONTRACTS
                contracts = DATA_FLOW_CONTRACTS
            except ImportError:
                result["status"] = "UNKNOWN"
                result["warnings"].append("Could not import DATA_FLOW_CONTRACTS from agent_protocol")
                return result
        
        contract = contracts.get(step_id)
        if contract is None:
            result["status"] = "UNKNOWN"
            result["warnings"].append(f"No contract defined for step '{step_id}'")
            return result
        
        requires = contract.get("requires", {})
        
        # Check required files
        root = Path(__file__).resolve().parent.parent
        for file_pattern in requires.get("files", []):
            file_path = root / file_pattern.replace("{date}", date)
            if file_path.exists():
                result["found"].append(str(file_pattern))
            else:
                result["missing"].append(str(file_pattern))
        
        # Check required DB tables
        required_tables = requires.get("db", [])
        if required_tables:
            try:
                import sys as _sys
                src_path = str(root / "src")
                if src_path not in _sys.path:
                    _sys.path.insert(0, src_path)
                from bet.db.connection import get_db
                with get_db() as conn:
                    for table in required_tables:
                        try:
                            row = conn.execute(
                                f"SELECT COUNT(*) FROM {table} WHERE betting_date = ?",
                                (date,)
                            ).fetchone()
                            if row and row[0] > 0:
                                result["found"].append(f"db:{table}")
                            else:
                                # Try without date filter (some tables don't have betting_date)
                                row2 = conn.execute(
                                    f"SELECT COUNT(*) FROM {table}"
                                ).fetchone()
                                if row2 and row2[0] > 0:
                                    result["found"].append(f"db:{table} (no date filter)")
                                else:
                                    result["missing"].append(f"db:{table}")
                        except Exception as e:
                            result["warnings"].append(f"DB check failed for {table}: {e}")
            except Exception as e:
                result["warnings"].append(f"DB connection failed: {e}")
        
        # Determine status
        if result["missing"]:
            if result["found"]:
                result["status"] = "PARTIAL"
            else:
                result["status"] = "MISSING"
        
        return result

    # ── Utility ──────────────────────────────────────────────────────

    @property
    def has_errors(self) -> bool:
        return self._error_count > 0

    @property
    def issues(self) -> list[dict]:
        return list(self._issues)
