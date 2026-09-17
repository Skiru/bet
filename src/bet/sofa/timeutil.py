from datetime import UTC, datetime


def now() -> datetime:
    """Get current UTC time. Centralized for easy mocking in tests."""
    return datetime.now(UTC)
