import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# A replay of a past day "as of" its build time (2026-10-04: the old and the
# new history rules compared on days already settled) needs every stage to
# read one frozen clock. SOFA_NOW=<ISO-8601 UTC> sets it; nothing in the daily
# flow sets it, and a stage that reads it says so on stderr once, so a frozen
# clock can never pass for a live one.
_ENV = "SOFA_NOW"
_warned = False


def now() -> datetime:
    """Get current UTC time. Centralized for easy mocking in tests."""
    global _warned
    frozen = os.environ.get(_ENV)
    if not frozen:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(frozen.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    if not _warned:
        print(f"SOFA_NOW: the clock is frozen at {parsed.isoformat()} (a replay, "
              "not a live run)", file=sys.stderr)
        _warned = True
    return parsed.astimezone(UTC)


REAL_RUNS_DIR = Path(__file__).resolve().parents[3] / "runs" / "sofa"


def frozen_clock_refusal(runs_dir: str | Path) -> str | None:
    """A refusal message when SOFA_NOW is set and `runs_dir` is the real one.

    Review 2026-10-04: only run_pipeline refused a frozen clock, while
    CONFIDENCE and the PDF time their kickoff and stale-price
    gates on now() - a shell left over from an as-of replay would print
    started matches and stale prices into the real day. A replay writes a
    scratch runs dir; the real one is refused.
    """
    if not os.environ.get(_ENV):
        return None
    if Path(runs_dir).resolve() != REAL_RUNS_DIR.resolve():
        return None
    return (
        f"REFUSED: {_ENV} is set (a frozen replay clock) and the runs dir is "
        f"the real one ({REAL_RUNS_DIR}); unset it, or replay into a scratch "
        "SOFA_RUNS_DIR / --runs-dir"
    )
