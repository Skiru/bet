"""Progress reporting for the pipeline. Output goes to stderr."""

from __future__ import annotations

import sys
import time
from datetime import datetime


class PipelineProgress:
    """Progress reporter — prints machine-parseable output to stderr."""

    def __init__(self, total_steps: int = 5):
        self.total_steps = total_steps
        self._current_step = 0
        self._step_start: float | None = None
        self._pipeline_start = time.monotonic()

    def start_step(self, step: str, description: str) -> None:
        """Print step start. E.g., '[1/5] DISCOVER -- Scanning fixtures...'"""
        self._current_step += 1
        self._step_start = time.monotonic()
        self._print(
            f"[{self._current_step}/{self.total_steps}] "
            f"{step.upper()} -- {description}"
        )

    def update(self, message: str) -> None:
        """Print progress within a step."""
        self._print(f"  {message}")

    def complete_step(self, step: str, stats: dict) -> None:
        """Print step completion with stats."""
        elapsed = ""
        if self._step_start is not None:
            dt = time.monotonic() - self._step_start
            elapsed = f" ({dt:.1f}s)"

        stats_str = ", ".join(f"{k}={v}" for k, v in stats.items())
        self._print(f"  OK {step.upper()}{elapsed} [{stats_str}]")

    def error(self, step: str, error: str) -> None:
        """Print step failure."""
        self._print(f"  FAIL {step.upper()}: {error}")

    def final_summary(self, results: dict) -> None:
        """Print pipeline completion summary."""
        total_time = time.monotonic() - self._pipeline_start
        self._print("---")
        self._print(f"Pipeline complete in {total_time:.1f}s")
        for key, value in results.items():
            self._print(f"  {key}: {value}")

    @staticmethod
    def _print(msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg}", file=sys.stderr, flush=True)
