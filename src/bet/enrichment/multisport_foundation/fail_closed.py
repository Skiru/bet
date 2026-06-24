from __future__ import annotations

PASS_B_STATUSES: tuple[str, ...] = (
    "SOURCE_BOUND_SHADOW_READY",
    "REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT",
    "BLOCKED_PROVIDER_ACCESS",
    "BLOCKED_NO_CREDENTIALS",
    "BLOCKED_PROVIDER_TERMS_OR_SCOPE",
    "BLOCKED_PROVIDER_MAPPING_NOT_FOUND",
)

BLOCKED_STATUSES = {status for status in PASS_B_STATUSES if status.startswith("BLOCKED_")}
VALID_FAIL_CLOSED_STATUSES = set(PASS_B_STATUSES) - {"SOURCE_BOUND_SHADOW_READY"}
FORBIDDEN_SUCCESS_TERMS: tuple[str, ...] = (
    "fallback score accepted",
    "fallback provider id accepted",
    "production_ready",
    "production selectable",
    "betting decision allowed",
    "edge accepted",
    "pick accepted",
)


def is_valid_pass_b_status(status: str) -> bool:
    return status in PASS_B_STATUSES


def assert_no_forbidden_success_text(payload: object) -> None:
    blob = str(payload).lower()
    found = [term for term in FORBIDDEN_SUCCESS_TERMS if term in blob]
    if found:
        raise AssertionError(f"forbidden success terms present: {found}")
