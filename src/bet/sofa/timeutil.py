import os
import sys
from datetime import UTC, datetime

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
