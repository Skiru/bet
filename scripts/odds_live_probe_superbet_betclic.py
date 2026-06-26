"""Redacted live probe for OddsPapi Superbet and optional The Odds API Betclic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any


TASK_ID = "ODDS_SUPERBET_BETCLIC_PUBLIC_BRANCH_REMEDIATION_A"
WORKTREE = Path(__file__).resolve().parents[1]
CONFIG_PATH = WORKTREE / "config" / "api_keys.json"
REPORT_PATH = WORKTREE / "reports" / "odds_provider_live_probe_superbet_betclic_v1.json"
ODDSPAPI_STATUSES = {
    "PASS",
    "PASS_EMPTY",
    "NOT_RUN_MISSING_KEYS",
    "FAIL_AUTH_OR_PLAN",
    "FAIL_QUOTA_OR_RATE_LIMIT",
    "FAIL_SCHEMA",
    "FAIL_NETWORK",
    "FAIL_UNEXPECTED",
}


def _read_api_keys() -> dict[str, str]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items() if isinstance(value, str)}


def _resolve_key(env_name: str, aliases: tuple[str, ...]) -> tuple[str | None, str]:
    env_value = os.getenv(env_name, "").strip()
    if env_value:
        return env_value, "env"
    keys = _read_api_keys()
    for alias in aliases:
        value = keys.get(alias, "").strip()
        if value:
            return value, "config/api_keys.json"
    return None, "missing"


def _safe_exc_message(exc: BaseException, secrets: list[str]) -> str | None:
    message = str(exc).strip()
    if not message:
        return None
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[REDACTED]")
    for token in ("apiKey=", "Bearer "):
        if token in message:
            prefix, _, _ = message.partition(token)
            message = f"{prefix}{token}[REDACTED]"
    return message[:240]


def _classify_provider_error(exc: BaseException) -> tuple[str, int]:
    message = str(exc)
    cause = exc.__cause__
    parts = [message.lower()]
    if cause is not None:
        parts.append(str(cause).lower())
    lowered = " ".join(parts)
    if "http 401" in lowered or "http 403" in lowered or "forbidden" in lowered or "unauthorized" in lowered:
        return "FAIL_AUTH_OR_PLAN", 0
    if "http 429" in lowered or "quota" in lowered or "rate limit" in lowered:
        return "FAIL_QUOTA_OR_RATE_LIMIT", 0
    if isinstance(cause, (TimeoutError, socket.timeout)):
        return "FAIL_NETWORK", 1
    try:
        import requests

        request_exception = requests.exceptions.RequestException
    except Exception:
        request_exception = ()
    if request_exception and isinstance(cause, request_exception):
        return "FAIL_NETWORK", 1
    if isinstance(exc, (ValueError, TypeError)) or "non-json" in lowered or "unexpected non-list payload" in lowered:
        return "FAIL_SCHEMA", 1
    if "request failed after retries" in lowered:
        return "FAIL_NETWORK", 1
    return "FAIL_UNEXPECTED", 1


def _provider_stub(configured: bool, key_source: str) -> dict[str, Any]:
    return {
        "configured": configured,
        "key_source": key_source,
        "status": "NOT_RUN_MISSING_KEYS" if not configured else "FAIL_UNEXPECTED",
        "events": None,
        "sample_has_bookmakers": None,
        "sample_bookmakers": [],
        "error_type": None,
        "error_message_redacted": None,
    }


def _bookmaker_sample(events: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    if not events:
        return False, []
    bookmakers = events[0].get("bookmakers") if isinstance(events[0], dict) else []
    if not isinstance(bookmakers, list):
        return False, []
    sample = []
    for bookmaker in bookmakers[:5]:
        if not isinstance(bookmaker, dict):
            continue
        sample.append(str(bookmaker.get("key") or bookmaker.get("title") or ""))
    return bool(bookmakers), sample


def _run_oddspapi_probe(window_start: str, window_end: str) -> tuple[dict[str, Any], int]:
    api_key, key_source = _resolve_key("ODDSPAPI_API_KEY", ("odds-papi",))
    result = _provider_stub(api_key is not None, key_source)
    result["events"] = 0 if api_key is not None else None
    if api_key is None:
        return result, 0

    os.environ["ODDSPAPI_API_KEY"] = api_key
    from scripts.odds_sources.oddspapi import SOURCE as oddspapi_source

    try:
        events = oddspapi_source.fetch_odds("football", window_start, window_end)
        has_bookmakers, sample_bookmakers = _bookmaker_sample(events)
        result.update(
            {
                "status": "PASS" if events else "PASS_EMPTY",
                "events": len(events),
                "sample_has_bookmakers": has_bookmakers,
                "sample_bookmakers": sample_bookmakers,
            }
        )
        return result, 0
    except Exception as exc:  # noqa: BLE001
        status, exit_code = _classify_provider_error(exc)
        result.update(
            {
                "status": status,
                "error_type": type(exc).__name__,
                "error_message_redacted": _safe_exc_message(exc, [api_key]),
            }
        )
        return result, exit_code


def _run_the_odds_probe(window_start: str, window_end: str) -> tuple[dict[str, Any], int]:
    aliases = ("the-odds-api", "the_odds_api", "THE_ODDS_API_KEY")
    api_key, key_source = _resolve_key("THE_ODDS_API_KEY", aliases)
    result = _provider_stub(api_key is not None, key_source)
    if api_key is None:
        return result, 0

    os.environ["THE_ODDS_API_KEY"] = api_key
    from scripts.odds_sources.the_odds_api_betclic import SOURCE as betclic_source

    try:
        events = betclic_source.fetch_odds("football", window_start, window_end)
        has_bookmakers, sample_bookmakers = _bookmaker_sample(events)
        result.update(
            {
                "status": "PASS" if events else "PASS_EMPTY",
                "events": len(events),
                "sample_has_bookmakers": has_bookmakers,
                "sample_bookmakers": sample_bookmakers,
            }
        )
        return result, 0
    except Exception as exc:  # noqa: BLE001
        status, exit_code = _classify_provider_error(exc)
        result.update(
            {
                "status": status,
                "error_type": type(exc).__name__,
                "error_message_redacted": _safe_exc_message(exc, [api_key]),
            }
        )
        return result, exit_code


def _live_certification_reason(oddspapi_result: dict[str, Any], the_odds_result: dict[str, Any]) -> tuple[bool, str]:
    oddspapi_status = str(oddspapi_result["status"])
    the_odds_status = str(the_odds_result["status"])
    if oddspapi_status == "PASS":
        if the_odds_status in {"PASS", "PASS_EMPTY", "NOT_RUN_MISSING_KEYS", "FAIL_AUTH_OR_PLAN", "FAIL_QUOTA_OR_RATE_LIMIT"}:
            return True, "OddsPapi live probe passed with normalized events; optional Betclic fallback did not block certification."
    if oddspapi_status == "PASS_EMPTY":
        return False, "OddsPapi request completed without schema/auth failure but returned zero normalized events."
    if oddspapi_status == "NOT_RUN_MISSING_KEYS":
        return False, "OddsPapi key missing; live certification was not run."
    return False, f"OddsPapi live probe status={oddspapi_status}; branch is not live-certified."


def main() -> int:
    now = datetime.now(timezone.utc)
    today_utc = now.date()
    tomorrow_utc = today_utc + timedelta(days=1)
    window_start = datetime.combine(today_utc, datetime.min.time(), tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    window_end = datetime.combine(tomorrow_utc, datetime.min.time(), tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")

    oddspapi_result, oddspapi_exit = _run_oddspapi_probe(window_start, window_end)
    the_odds_result, the_odds_exit = _run_the_odds_probe(window_start, window_end)
    live_certified, reason = _live_certification_reason(oddspapi_result, the_odds_result)

    report = {
        "task_id": TASK_ID,
        "timestamp_utc": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "worktree": str(WORKTREE),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=WORKTREE, text=True).strip(),
        "commit_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=WORKTREE, text=True).strip(),
        "providers": {
            "oddspapi": oddspapi_result,
            "the-odds-api-betclic": the_odds_result,
        },
        "live_certified": live_certified,
        "live_certification_reason": reason,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    exit_code = max(oddspapi_exit, the_odds_exit)
    if oddspapi_result["status"] in {"FAIL_AUTH_OR_PLAN", "FAIL_QUOTA_OR_RATE_LIMIT"}:
        exit_code = max(exit_code, 0)
    if the_odds_result["status"] in {"FAIL_AUTH_OR_PLAN", "FAIL_QUOTA_OR_RATE_LIMIT", "NOT_RUN_MISSING_KEYS"}:
        exit_code = max(exit_code, 0)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
