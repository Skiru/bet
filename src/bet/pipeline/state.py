"""Pipeline state machine — tracks position, decisions, and flags across agent calls.

Design:
- state.json is a POINTER + SUMMARY, never >50 lines of JSON
- Candidate data lives in DB (unlimited rows)
- State enables session resume after context reset between phases
- 2-phase model: DATA (S0-S2.9) → ANALYSIS_BUILD (S3-S10)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Literal

# Phase transition boundary
_PHASE_BOUNDARY = "S3"  # S3 and above = ANALYSIS_BUILD

# Valid step progression
STEP_ORDER = [
    "S0", "S1", "S1e", "S2", "S2.3", "S2.5", "S2.7", "S2.9",
    "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10",
]

DATA_DIR = Path("betting/data")


def _determine_phase(step: str) -> str:
    """Determine phase from step position."""
    idx = STEP_ORDER.index(step) if step in STEP_ORDER else 0
    boundary_idx = STEP_ORDER.index(_PHASE_BOUNDARY)
    return "ANALYSIS_BUILD" if idx >= boundary_idx else "DATA"


@dataclass
class PipelineState:
    """Pipeline state — serialized to {date}_state.json."""

    date: str
    phase: Literal["DATA", "ANALYSIS_BUILD"] = "DATA"
    position: str = "S0"
    data_summary: dict = field(default_factory=dict)
    decisions: list[str] = field(default_factory=list)
    flags: dict[str, bool] = field(default_factory=dict)
    completed_steps: list[str] = field(default_factory=list)
    last_updated: str = ""

    @classmethod
    def load(cls, date: str) -> PipelineState:
        """Load state from disk, or create fresh state for new session."""
        if not date or "/" in date or ".." in date:
            raise ValueError(f"Invalid date format: {date!r}")
        path = DATA_DIR / f"{date}_state.json"
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                date=raw["date"],
                phase=raw.get("phase", "DATA"),
                position=raw.get("position", "S0"),
                data_summary=raw.get("data_summary", {}),
                decisions=raw.get("decisions", []),
                flags=raw.get("flags", {}),
                completed_steps=raw.get("completed_steps", []),
                last_updated=raw.get("last_updated", ""),
            )
        return cls(date=date, last_updated=datetime.now().isoformat(timespec="seconds"))

    def save(self) -> Path:
        """Persist state to disk. Returns path written."""
        self.last_updated = datetime.now().isoformat(timespec="seconds")
        path = DATA_DIR / f"{self.date}_state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path

    def advance(self, step: str, summary: dict | None = None) -> None:
        """Mark step as completed and advance position.

        Args:
            step: Step identifier (e.g. "S3")
            summary: Optional dict merged into data_summary
        """
        if step not in STEP_ORDER:
            raise ValueError(f"Unknown step: {step}. Valid: {STEP_ORDER}")

        if step not in self.completed_steps:
            self.completed_steps.append(step)

        # Advance position to next step
        idx = STEP_ORDER.index(step)
        if idx + 1 < len(STEP_ORDER):
            self.position = STEP_ORDER[idx + 1]
        else:
            self.position = step  # Terminal step

        # Update phase based on new position
        self.phase = _determine_phase(self.position)

        # Merge summary data namespaced by step
        if summary is not None:
            self.data_summary[step] = summary

        self.save()

    def can_proceed(self, next_step: str) -> bool:
        """Check if pipeline can proceed to next_step.

        Rules:
        - Steps must follow STEP_ORDER (no skipping)
        - Cannot re-run completed steps (use force=True in advance for reruns)
        """
        if next_step not in STEP_ORDER:
            return False

        next_idx = STEP_ORDER.index(next_step)

        # First step always allowed
        if next_idx == 0:
            return True

        # Previous step must be completed
        prev_step = STEP_ORDER[next_idx - 1]
        return prev_step in self.completed_steps

    def add_decision(self, decision: str) -> None:
        """Record an analytical decision (e.g. 'skip_esports_no_tipster_data')."""
        if decision not in self.decisions:
            self.decisions.append(decision)
            self.save()

    def set_flag(self, flag: str, value: bool) -> None:
        """Set a pipeline flag (e.g. 'tipster_fetch_partial': True)."""
        self.flags[flag] = value
        self.save()

    @property
    def is_fresh(self) -> bool:
        """True if no steps completed yet."""
        return len(self.completed_steps) == 0

    @property
    def is_data_phase(self) -> bool:
        return self.phase == "DATA"

    @property
    def is_analysis_phase(self) -> bool:
        return self.phase == "ANALYSIS_BUILD"

    def __repr__(self) -> str:
        return (
            f"PipelineState(date={self.date!r}, phase={self.phase!r}, "
            f"position={self.position!r}, steps={len(self.completed_steps)})"
        )
