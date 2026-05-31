"""Structured output helpers for pipeline scripts.

Each pipeline step emits a structured JSON file to `betting/data/` following a standard
envelope format. Agents receive these files as pre-computed input — they reason about
the data but never re-compute it.

Usage:
    from bet.pipeline.structured_output import StructuredOutput

    output = StructuredOutput(step="S3", date="2026-05-30")
    output.add_candidate(fixture_id=123, data={...})
    output.finalize(summary={"total": 45, "with_data": 32})
    # Writes betting/data/2026-05-30_s3_structured.json
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path("betting/data")


class StructuredOutput:
    """Standard envelope for pipeline step output.

    Structure:
    {
        "step": "S3",
        "date": "2026-05-30",
        "generated_at": "2026-05-30T14:30:00",
        "summary": {...},
        "candidates": [...]
    }
    """

    def __init__(self, step: str, date: str):
        if not date or "/" in date or ".." in date:
            raise ValueError(f"Invalid date format: {date!r}")
        self.step = step
        self.date = date
        self.candidates: list[dict[str, Any]] = []
        self.summary: dict[str, Any] = {}
        self._generated_at = datetime.now().isoformat(timespec="seconds")

    def add_candidate(self, fixture_id: int | str, data: dict[str, Any]) -> None:
        """Add a processed candidate with pre-computed analysis data."""
        entry = {"fixture_id": fixture_id, **data}
        self.candidates.append(entry)

    def finalize(self, summary: dict[str, Any] | None = None) -> Path:
        """Write structured JSON to disk. Returns path."""
        if summary is not None:
            self.summary = summary

        envelope = {
            "step": self.step,
            "date": self.date,
            "generated_at": self._generated_at,
            "summary": self.summary,
            "candidates": self.candidates,
        }

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = DATA_DIR / f"{self.date}_{self.step.lower()}_structured.json"
        path.write_text(
            json.dumps(envelope, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(cls, step: str, date: str) -> dict[str, Any]:
        """Load a previously written structured output."""
        path = DATA_DIR / f"{date}_{step.lower()}_structured.json"
        if not path.exists():
            raise FileNotFoundError(f"No structured output for {step} on {date}: {path}")
        return json.loads(path.read_text(encoding="utf-8"))
