"""Redacted live probe for OddsPapi Superbet and optional The Odds API Betclic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any, Callable

import requests


TASK_ID = "ODDS_SUPERBET_BETCLIC_PUBLIC_BRANCH_REMEDIATION_B2_CREDENTIAL_PATH"
WORKTREE = Path(__file__).resolve().parents[1]
CONFIG_PATH = WORKTREE / "config" / "api_keys.json"
ABS_ODDSPAPI_KEYS_FILE = Path("/Users/mkoziol/projects/bet/.kilo/worktrees/plume-homburg/config/api_keys.json")
REPORT_PATH = WORKTREE / "reports" / "odds_provider_live_probe_superbet_betclic_v1.json"
ODDSPAPI_STATUSES = {
    "PASS",
    "PASS_EMPTY_DISCOVERY",
    "PASS_EMPTY_ODDS",
    "NOT_RUN_MISSING_KEYS",
    "FAIL_AUTH_OR_PLAN",
    "FAIL_PLAN_NO_SUPERBET_PL",
    "FAIL_PLAN_NO_SPORT_10",
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


def _read_api_keys_from_path(path: Path) -> dict[str, str]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
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


def load_oddspapi_credentials() -> dict[str, Any]:
    env_value = os.getenv("ODDSPAPI_API_KEY", "").strip()
    if env_value:
        return {
            "api_key": env_value,
            "key_source": "env",
            "key_file_path_used": None,
            "key_present": True,
        }

    keys = _read_api_keys_from_path(ABS_ODDSPAPI_KEYS_FILE)
    file_value = keys.get("odds-papi", "").strip()
    if file_value:
        return {
            "api_key": file_value,
            "key_source": "absolute_config_api_keys_json",
            "key_file_path_used": str(ABS_ODDSPAPI_KEYS_FILE),
            "key_present": True,
        }

    return {
        "api_key": None,
        "key_source": "missing",
        "key_file_path_used": None,
        "key_present": False,
    }


def load_oddspapi_source(
    api_key: str,
    import_module: Callable[[str], Any] = importlib.import_module,
) -> Any:
    # The adapter's SOURCE path can read env-backed config during import time.
    os.environ["ODDSPAPI_API_KEY"] = api_key
    module = import_module("scripts.odds_sources.oddspapi")
    return getattr(module, "SOURCE")


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


def _normalize_key_name(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _find_first_value(payload: Any, target_keys: set[str]) -> Any:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if _normalize_key_name(key) in target_keys:
                return value
        for value in payload.values():
            nested = _find_first_value(value, target_keys)
            if nested is not None:
                return nested
    elif isinstance(payload, list):
        for item in payload:
            nested = _find_first_value(item, target_keys)
            if nested is not None:
                return nested
    return None


def _contains_token(payload: Any, token: str) -> bool | None:
    lowered_token = token.lower()
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_name = str(key).lower()
            if lowered_token in key_name:
                return True
            nested = _contains_token(value, token)
            if nested:
                return True
    elif isinstance(payload, list):
        for item in payload:
            nested = _contains_token(item, token)
            if nested:
                return True
    elif isinstance(payload, str):
        if lowered_token in payload.lower():
            return True
    return None


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "active", "enabled"}:
            return True
        if lowered in {"false", "no", "inactive", "disabled"}:
            return False
    return None


def probe_oddspapi_account_direct(api_key: str) -> dict[str, Any]:
    result = {
        "attempted": True,
        "http_status": None,
        "ok": False,
        "response_top_level_keys": [],
        "request_limit": None,
        "request_count": None,
        "current_subscription_active": None,
        "has_superbet_pl": None,
        "has_sport_10": None,
        "error_type": None,
        "error_message_redacted": None,
    }

    try:
        response = requests.get(
            "https://api.oddspapi.io/v4/account",
            params={"apiKey": api_key},
            headers={"Accept": "application/json"},
            timeout=20.0,
        )
        result["http_status"] = int(response.status_code)
        result["ok"] = bool(response.ok)
        try:
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            result["error_type"] = type(exc).__name__
            result["error_message_redacted"] = _safe_exc_message(exc, [api_key])
            return result

        if isinstance(payload, dict):
            result["response_top_level_keys"] = sorted(str(key) for key in payload.keys())
            result["request_limit"] = _find_first_value(payload, {"request_limit", "requests_limit", "limit"})
            result["request_count"] = _find_first_value(payload, {"request_count", "requests_count", "count", "used"})
            result["current_subscription_active"] = _coerce_bool(
                _find_first_value(payload, {"current_subscription_active", "subscription_active", "active", "is_active"})
            )
            result["has_superbet_pl"] = _contains_token(payload, "superbet.pl")
            result["has_sport_10"] = _contains_token(payload, "sport_10") or _contains_token(payload, "sportId:10")
            if result["has_sport_10"] is None:
                sport_id_value = _find_first_value(payload, {"sportid", "sport_id"})
                if sport_id_value is not None:
                    result["has_sport_10"] = str(sport_id_value).strip() == "10"
        elif not response.ok:
            result["error_message_redacted"] = f"OddsPapi account probe returned HTTP {response.status_code}"

        if not response.ok and result["error_message_redacted"] is None:
            result["error_message_redacted"] = f"OddsPapi account probe returned HTTP {response.status_code}"
        return result
    except requests.exceptions.RequestException as exc:
        result["error_type"] = type(exc).__name__
        result["error_message_redacted"] = _safe_exc_message(exc, [api_key])
        return result


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
        "key_file_path_used": None,
        "key_present": configured,
        "account_probe": {
            "attempted": False,
            "http_status": None,
            "ok": False,
            "response_top_level_keys": [],
            "request_limit": None,
            "request_count": None,
            "current_subscription_active": None,
            "has_superbet_pl": None,
            "has_sport_10": None,
            "error_type": None,
            "error_message_redacted": None,
        },
        "billable_calls_attempted": 0,
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
    credential = load_oddspapi_credentials()
    api_key = credential["api_key"]
    result = _provider_stub(bool(credential["key_present"]), str(credential["key_source"]))
    result["key_file_path_used"] = credential["key_file_path_used"]
    result["key_present"] = bool(credential["key_present"])
    result["events"] = 0 if api_key is not None else None
    if api_key is None:
        return result, 0

    account_probe = probe_oddspapi_account_direct(api_key)
    result["account_probe"] = account_probe
    http_status = account_probe.get("http_status")
    if http_status in {401, 403}:
        result.update(
            {
                "status": "FAIL_AUTH_OR_PLAN",
                "error_type": "OddsPapiAccountProbeError",
                "error_message_redacted": (
                    "absolute credential file was read, but /v4/account returned "
                    f"HTTP {http_status}; this indicates key/auth/plan rejection rather than missing local credential path"
                ),
            }
        )
        return result, 0
    if http_status == 429:
        result.update(
            {
                "status": "FAIL_QUOTA_OR_RATE_LIMIT",
                "error_type": "OddsPapiAccountProbeError",
                "error_message_redacted": "OddsPapi account probe returned HTTP 429",
            }
        )
        return result, 0
    if account_probe.get("attempted") and not bool(account_probe.get("ok")):
        result.update(
            {
                "status": "FAIL_NETWORK" if http_status is None else "FAIL_UNEXPECTED",
                "error_type": str(account_probe.get("error_type") or "OddsPapiAccountProbeError"),
                "error_message_redacted": account_probe.get("error_message_redacted"),
            }
        )
        return result, 1

    oddspapi_source = load_oddspapi_source(api_key)
    result["billable_calls_attempted"] = 1

    try:
        events = oddspapi_source.fetch_odds("football", window_start, window_end)
        has_bookmakers, sample_bookmakers = _bookmaker_sample(events)
        result.update(
            {
                "status": "PASS" if events else "PASS_EMPTY_ODDS",
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
    if oddspapi_status == "PASS_EMPTY_ODDS":
        return False, "OddsPapi request completed without schema/auth failure but returned zero normalized events."
    if oddspapi_status == "NOT_RUN_MISSING_KEYS":
        return False, "OddsPapi key missing; live certification was not run."
    if oddspapi_status == "FAIL_AUTH_OR_PLAN":
        account_http_status = oddspapi_result.get("account_probe", {}).get("http_status")
        provider_error = oddspapi_result.get("error_message_redacted")
        if account_http_status in {401, 403}:
            return (
                False,
                "Credential path is proven: absolute credential file was found and key loaded, but OddsPapi /v4/account rejected the credential with HTTP "
                f"{account_http_status}; remaining blocker is provider auth/plan/key validity, not local credential discovery.",
            )
        if account_http_status == 200:
            return (
                False,
                "Credential path is proven: absolute credential file was found, the redacted OddsPapi /v4/account diagnostic returned HTTP 200, and the follow-up odds request was still rejected"
                f" ({provider_error}); remaining blocker is provider access/plan scope rather than local credential discovery.",
            )
        return (
            False,
            "Credential path is proven: absolute credential file was found and key loaded, but the provider still rejected the probe; remaining blocker is provider auth/plan/key validity, not local credential discovery.",
        )
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
