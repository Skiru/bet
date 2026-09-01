"""Redacted, direct-adapter Superbet provider health check."""

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

from bet.api_clients.oddspapi import OddspapiConfig, OddsPapiClient, OddsPapiError


TASK_ID = "SUPERBET_PROVIDER_HEALTHCHECK"
BASE_COMMIT_SHA = "fc5e7188b9f016f891a24346f1dce9c6ab73b455"
WORKTREE = Path(__file__).resolve().parents[1]
CONFIG_PATH = WORKTREE / "config" / "api_keys.json"
REPORT_PATH = Path(os.environ.get("BET_PROVIDER_HEALTH_REPORT", "/tmp/bet-provider-health-superbet.json"))
ODDSPAPI_STATUSES = {
    "PASS",
    "PASS_EMPTY_DISCOVERY",
    "PASS_EMPTY_ODDS",
    "NOT_RUN_MISSING_KEYS",
    "FAIL_AUTH_OR_PLAN",
    "FAIL_PLAN_NO_SUPERBET_PL",
    "FAIL_PLAN_NO_SPORT_10",
    "FAIL_ACCESS_FIXTURES",
    "FAIL_ACCESS_ODDS",
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

    keys = _read_api_keys_from_path(CONFIG_PATH)
    file_value = keys.get("odds-papi", "").strip()
    if file_value:
        return {
            "api_key": file_value,
            "key_source": "config/api_keys.json",
            "key_file_path_used": str(CONFIG_PATH),
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


def _git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=WORKTREE, text=True).strip()


def _git_dirty() -> bool:
    return bool(_git_output("status", "--short"))


def _classify_http_status(http_status: int | None, *, phase: str) -> str:
    if http_status in {401, 403}:
        return "FAIL_AUTH_OR_PLAN" if phase == "account" else f"FAIL_ACCESS_{phase.upper()}"
    if http_status == 429:
        return "FAIL_QUOTA_OR_RATE_LIMIT"
    return "FAIL_UNEXPECTED"


def _provider_stub(configured: bool, key_source: str) -> dict[str, Any]:
    return {
        "configured": configured,
        "key_source": key_source,
        "key_file_path_used": None,
        "key_present": configured,
        "status": "NOT_RUN_MISSING_KEYS" if not configured else "FAIL_UNEXPECTED",
        "reason": None,
        "billable_calls_attempted": 0,
        "account_probe": {
            "attempted": False,
            "http_status": None,
            "ok": False,
            "current_subscription_active": None,
            "request_count": None,
            "request_limit": None,
            "redacted_summary": None,
            "error_type": None,
            "error_message_redacted": None,
        },
        "fixture_probe": {
            "attempted": False,
            "http_status": None,
            "fixture_count": None,
            "error_type": None,
            "error_message_redacted": None,
        },
        "odds_probe": {
            "attempted": False,
            "http_status": None,
            "events": None,
            "sample_bookmakers": [],
            "error_type": None,
            "error_message_redacted": None,
        },
    }


def _account_probe_from_payload(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempted": True,
        "http_status": 200,
        "ok": True,
        "current_subscription_active": summary.get("current_subscription_active"),
        "request_count": summary.get("request_count"),
        "request_limit": summary.get("request_limit"),
        "redacted_summary": summary,
        "error_type": None,
        "error_message_redacted": None,
    }


def _bookmaker_sample(events: list[dict[str, Any]]) -> list[str]:
    if not events:
        return []
    bookmakers = events[0].get("bookmakers") if isinstance(events[0], dict) else []
    if not isinstance(bookmakers, list):
        return []
    sample: list[str] = []
    for bookmaker in bookmakers[:5]:
        if not isinstance(bookmaker, dict):
            continue
        sample.append(str(bookmaker.get("key") or bookmaker.get("title") or ""))
    return sample


def _run_oddspapi_probe(window_start: str, window_end: str) -> tuple[dict[str, Any], int]:
    credential = load_oddspapi_credentials()
    api_key = credential["api_key"]
    result = _provider_stub(bool(credential["key_present"]), str(credential["key_source"]))
    result["key_file_path_used"] = credential["key_file_path_used"]
    result["key_present"] = bool(credential["key_present"])
    if api_key is None:
        result["reason"] = "OddsPapi key missing; live probe not run."
        return result, 0

    client = OddsPapiClient(OddspapiConfig(api_key=api_key))

    try:
        account_payload = client.get_account()
        account_summary = client.summarize_account(account_payload)
        result["account_probe"] = _account_probe_from_payload(account_summary)
    except OddsPapiError as exc:
        http_status = exc.http_status
        result["account_probe"] = {
            "attempted": True,
            "http_status": http_status,
            "ok": False,
            "current_subscription_active": None,
            "request_count": None,
            "request_limit": None,
            "redacted_summary": None,
            "error_type": type(exc).__name__,
            "error_message_redacted": _safe_exc_message(exc, [api_key]),
        }
        result["status"] = _classify_http_status(http_status, phase="account")
        result["reason"] = "OddsPapi /v4/account rejected or blocked the credential/plan."
        return result, 0 if http_status in {401, 403, 429} else 1
    except Exception as exc:  # noqa: BLE001
        result["account_probe"] = {
            "attempted": True,
            "http_status": None,
            "ok": False,
            "current_subscription_active": None,
            "request_count": None,
            "request_limit": None,
            "redacted_summary": None,
            "error_type": type(exc).__name__,
            "error_message_redacted": _safe_exc_message(exc, [api_key]),
        }
        result["status"] = "FAIL_NETWORK" if isinstance(exc, (TimeoutError, socket.timeout)) else "FAIL_UNEXPECTED"
        result["reason"] = "OddsPapi /v4/account probe failed before any billable call."
        return result, 1

    account_summary = result["account_probe"]["redacted_summary"] or {}
    if account_summary.get("has_superbet_pl") is False:
        # Still a FAIL for *this* probe's purpose -- it exists to answer "can
        # OddsPapi serve the operator's own prices", and it cannot. What the
        # reason must not do is imply the provider is unusable: the 403 that
        # follows from asking for superbet.pl names a bookmaker, not an
        # endpoint, and an entitled storefront shares Superbet's event ids and
        # drives the SUPERBET step's identity bridge.
        alternative = account_summary.get("usable_superbet_slug")
        result["status"] = "FAIL_PLAN_NO_SUPERBET_PL"
        result["reason"] = (
            "OddsPapi account response does not show Superbet PL access."
            + (
                f" An entitled Superbet storefront is available ({alternative}); it shares "
                "Superbet's event ids, so /v4/fixtures and /v4/odds remain usable for "
                "fixture identity even though this price source is not."
                if alternative else ""
            )
        )
        return result, 0
    if account_summary.get("has_sport_10") is False:
        result["status"] = "FAIL_PLAN_NO_SPORT_10"
        result["reason"] = "OddsPapi account response does not show football sportId 10 access."
        return result, 0

    try:
        fixtures = client.fetch_fixtures("football", window_start, window_end, bookmaker="superbet.pl")
        result["billable_calls_attempted"] = 1
        result["fixture_probe"] = {
            "attempted": True,
            "http_status": 200,
            "fixture_count": len(fixtures),
            "error_type": None,
            "error_message_redacted": None,
        }
    except OddsPapiError as exc:
        http_status = exc.http_status
        result["billable_calls_attempted"] = 1
        result["fixture_probe"] = {
            "attempted": True,
            "http_status": http_status,
            "fixture_count": None,
            "error_type": type(exc).__name__,
            "error_message_redacted": _safe_exc_message(exc, [api_key]),
        }
        result["status"] = _classify_http_status(http_status, phase="fixtures")
        result["reason"] = "OddsPapi account probe succeeded, but /v4/fixtures was forbidden or failed."
        return result, 0 if http_status in {403, 429} else 1
    except Exception as exc:  # noqa: BLE001
        result["billable_calls_attempted"] = 1
        result["fixture_probe"] = {
            "attempted": True,
            "http_status": None,
            "fixture_count": None,
            "error_type": type(exc).__name__,
            "error_message_redacted": _safe_exc_message(exc, [api_key]),
        }
        result["status"] = "FAIL_NETWORK" if isinstance(exc, (TimeoutError, socket.timeout)) else "FAIL_SCHEMA"
        result["reason"] = "OddsPapi fixtures discovery failed after account success."
        return result, 1

    if not fixtures:
        result["status"] = "PASS_EMPTY_DISCOVERY"
        result["reason"] = "OddsPapi account and fixtures discovery succeeded, but no Superbet PL football fixture was returned in the narrow probe window."
        return result, 0

    fixture_id = fixtures[0].get("fixtureId") or fixtures[0].get("id") or fixtures[0].get("eventId")
    if fixture_id in (None, ""):
        result["status"] = "FAIL_SCHEMA"
        result["reason"] = "OddsPapi fixtures discovery returned a fixture without fixtureId/id."
        return result, 1

    try:
        normalized_events = [event.as_existing_pipeline_dict() for event in client.fetch_fixture_odds(fixture_id, bookmaker="superbet.pl")]
        result["billable_calls_attempted"] = 2
        sample_bookmakers = _bookmaker_sample(normalized_events)
        result["odds_probe"] = {
            "attempted": True,
            "http_status": 200,
            "events": len(normalized_events),
            "sample_bookmakers": sample_bookmakers,
            "error_type": None,
            "error_message_redacted": None,
        }
    except OddsPapiError as exc:
        http_status = exc.http_status
        result["billable_calls_attempted"] = 2
        result["odds_probe"] = {
            "attempted": True,
            "http_status": http_status,
            "events": None,
            "sample_bookmakers": [],
            "error_type": type(exc).__name__,
            "error_message_redacted": _safe_exc_message(exc, [api_key]),
        }
        result["status"] = _classify_http_status(http_status, phase="odds")
        result["reason"] = "OddsPapi account and fixtures discovery succeeded, but /v4/odds by fixtureId was forbidden or failed."
        return result, 0 if http_status in {403, 429} else 1
    except Exception as exc:  # noqa: BLE001
        result["billable_calls_attempted"] = 2
        result["odds_probe"] = {
            "attempted": True,
            "http_status": None,
            "events": None,
            "sample_bookmakers": [],
            "error_type": type(exc).__name__,
            "error_message_redacted": _safe_exc_message(exc, [api_key]),
        }
        result["status"] = "FAIL_NETWORK" if isinstance(exc, (TimeoutError, socket.timeout)) else "FAIL_SCHEMA"
        result["reason"] = "OddsPapi odds-by-fixture probe failed after fixture discovery."
        return result, 1

    if not normalized_events:
        result["status"] = "PASS_EMPTY_ODDS"
        result["reason"] = "OddsPapi odds-by-fixture endpoint succeeded, but no normalized Superbet PL event was produced."
        return result, 0

    has_superbet = any("superbet.pl" == sample for sample in result["odds_probe"]["sample_bookmakers"])
    if has_superbet:
        result["status"] = "PASS"
        result["reason"] = "OddsPapi account, fixtures, and odds-by-fixture flow succeeded with a normalized Superbet PL bookmaker."
        return result, 0

    result["status"] = "FAIL_SCHEMA"
    result["reason"] = "OddsPapi odds-by-fixture succeeded but the normalized event did not contain the expected Superbet PL bookmaker."
    return result, 1


def _live_certification_reason(oddspapi_result: dict[str, Any]) -> tuple[bool, str]:
    oddspapi_status = str(oddspapi_result["status"])
    if oddspapi_status == "PASS":
        return True, "OddsPapi completed the official account -> fixtures -> odds flow with a normalized Superbet PL bookmaker."
    if oddspapi_status == "PASS_EMPTY_DISCOVERY":
        return False, "OddsPapi contract flow is implemented, but the narrow live discovery window returned no Superbet PL football fixture."
    if oddspapi_status == "PASS_EMPTY_ODDS":
        return False, "OddsPapi account and fixture discovery succeeded, but the fixture odds response produced no normalized Superbet PL event."
    if oddspapi_status == "FAIL_ACCESS_FIXTURES":
        return False, "OddsPapi account succeeded, but fixtures discovery is forbidden for this plan/key; keep the branch shadow-only."
    if oddspapi_status == "FAIL_ACCESS_ODDS":
        return False, "OddsPapi account and fixtures discovery succeeded, but fixture odds access is forbidden for this plan/key; keep the branch shadow-only."
    if oddspapi_status == "FAIL_AUTH_OR_PLAN":
        return False, "OddsPapi /v4/account rejected the credential or plan before billable calls."
    if oddspapi_status in ODDSPAPI_STATUSES:
        return False, f"OddsPapi live probe status={oddspapi_status}."
    return False, "OddsPapi live probe returned an unknown status."


def main() -> int:
    now = datetime.now(timezone.utc)
    today_utc = now.date()
    tomorrow_utc = today_utc + timedelta(days=1)
    window_start = datetime.combine(today_utc, datetime.min.time(), tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    window_end = datetime.combine(tomorrow_utc, datetime.min.time(), tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    tested_commit_sha = _git_output("rev-parse", "HEAD")
    worktree_dirty_before_probe = _git_dirty()

    oddspapi_result, oddspapi_exit = _run_oddspapi_probe(window_start, window_end)
    live_certified, reason = _live_certification_reason(oddspapi_result)

    report = {
        "task_id": TASK_ID,
        "base_commit_sha": BASE_COMMIT_SHA,
        "tested_commit_sha": tested_commit_sha,
        "timestamp_utc": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "worktree": str(WORKTREE),
        "branch": _git_output("branch", "--show-current"),
        "worktree_dirty_before_probe": worktree_dirty_before_probe,
        "providers": {
            "oddspapi": oddspapi_result,
        },
        "live_certified": live_certified,
        "live_certification_reason": reason,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    exit_code = oddspapi_exit
    if oddspapi_result["status"] in {"FAIL_AUTH_OR_PLAN", "FAIL_ACCESS_FIXTURES", "FAIL_ACCESS_ODDS", "FAIL_QUOTA_OR_RATE_LIMIT"}:
        exit_code = max(exit_code, 0)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
