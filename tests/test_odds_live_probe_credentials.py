from __future__ import annotations

from pathlib import Path
import types

from scripts import provider_healthcheck_superbet as probe
from bet.api_clients.oddspapi import OddsPapiError


def test_load_oddspapi_credentials_uses_local_ignored_file(tmp_path: Path, monkeypatch, capsys) -> None:
    key_file = tmp_path / "api_keys.json"
    key_file.write_text('{"odds-papi": "file-secret-token"}\n', encoding="utf-8")
    monkeypatch.setattr(probe, "CONFIG_PATH", key_file)
    monkeypatch.delenv("ODDSPAPI_API_KEY", raising=False)

    credential = probe.load_oddspapi_credentials()

    assert credential["api_key"] == "file-secret-token"
    assert credential["key_source"] == "config/api_keys.json"
    assert credential["key_file_path_used"] == str(key_file)
    assert credential["key_present"] is True
    captured = capsys.readouterr()
    assert "file-secret-token" not in captured.out
    assert captured.out == ""


def test_load_oddspapi_credentials_prefers_env_over_local_file(tmp_path: Path, monkeypatch) -> None:
    key_file = tmp_path / "api_keys.json"
    key_file.write_text('{"odds-papi": "file-secret-token"}\n', encoding="utf-8")
    monkeypatch.setattr(probe, "CONFIG_PATH", key_file)
    monkeypatch.setenv("ODDSPAPI_API_KEY", "env-secret-token")

    credential = probe.load_oddspapi_credentials()

    assert credential["api_key"] == "env-secret-token"
    assert credential["key_source"] == "env"
    assert credential["key_file_path_used"] is None
    assert credential["key_present"] is True


def test_load_oddspapi_credentials_returns_missing_when_file_absent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(probe, "CONFIG_PATH", tmp_path / "missing.json")
    monkeypatch.delenv("ODDSPAPI_API_KEY", raising=False)

    credential = probe.load_oddspapi_credentials()

    assert credential == {
        "api_key": None,
        "key_source": "missing",
        "key_file_path_used": None,
        "key_present": False,
    }


def test_load_oddspapi_source_sets_env_before_import(monkeypatch) -> None:
    monkeypatch.delenv("ODDSPAPI_API_KEY", raising=False)

    def fake_import(name: str) -> object:
        assert name == "scripts.odds_sources.oddspapi"
        assert probe.os.environ["ODDSPAPI_API_KEY"] == "env-before-import"
        return types.SimpleNamespace(SOURCE="loaded-source")

    source = probe.load_oddspapi_source("env-before-import", import_module=fake_import)

    assert source == "loaded-source"
    assert probe.os.environ["ODDSPAPI_API_KEY"] == "env-before-import"


def test_run_oddspapi_probe_stops_on_account_403(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, config):
            self.config = config

        def get_account(self):
            raise OddsPapiError("OddsPapi request failed with HTTP 403", http_status=403)

    monkeypatch.setattr(
        probe,
        "load_oddspapi_credentials",
        lambda: {
            "api_key": "secret-token",
            "key_source": "config/api_keys.json",
            "key_file_path_used": "/tmp/api_keys.json",
            "key_present": True,
        },
    )
    monkeypatch.setattr(probe, "OddsPapiClient", FakeClient)

    result, exit_code = probe._run_oddspapi_probe("2026-06-26T00:00:00Z", "2026-06-27T00:00:00Z")

    assert exit_code == 0
    assert result["status"] == "FAIL_AUTH_OR_PLAN"
    assert result["billable_calls_attempted"] == 0
    assert result["account_probe"]["http_status"] == 403
    assert result["fixture_probe"]["attempted"] is False
    assert result["odds_probe"]["attempted"] is False


def test_run_oddspapi_probe_stops_when_account_lacks_superbet(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, config):
            self.config = config

        def get_account(self):
            return {"data": {"requestLimit": 250}}

        def summarize_account(self, payload):
            return {
                "current_subscription_active": True,
                "request_limit": 250,
                "request_count": 5,
                "subscription_count": 1,
                "has_superbet_pl": False,
                "has_sport_10": True,
                "bookmaker_slugs_sample": [],
                "sport_ids_sample": [10],
            }

    monkeypatch.setattr(
        probe,
        "load_oddspapi_credentials",
        lambda: {
            "api_key": "secret-token",
            "key_source": "config/api_keys.json",
            "key_file_path_used": "/tmp/api_keys.json",
            "key_present": True,
        },
    )
    monkeypatch.setattr(probe, "OddsPapiClient", FakeClient)

    result, exit_code = probe._run_oddspapi_probe("2026-06-26T00:00:00Z", "2026-06-27T00:00:00Z")

    assert exit_code == 0
    assert result["status"] == "FAIL_PLAN_NO_SUPERBET_PL"
    assert result["billable_calls_attempted"] == 0
    assert result["fixture_probe"]["attempted"] is False


def test_run_oddspapi_probe_classifies_fixture_403_after_account_success(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, config):
            self.config = config

        def get_account(self):
            return {"data": {"requestLimit": 250}}

        def summarize_account(self, payload):
            return {
                "current_subscription_active": True,
                "request_limit": 250,
                "request_count": 5,
                "subscription_count": 1,
                "has_superbet_pl": True,
                "has_sport_10": True,
                "bookmaker_slugs_sample": ["superbet.pl"],
                "sport_ids_sample": [10],
            }

        def fetch_fixtures(self, sport, date_from, date_to, bookmaker="superbet.pl"):
            raise OddsPapiError("OddsPapi request failed with HTTP 403", http_status=403)

    monkeypatch.setattr(
        probe,
        "load_oddspapi_credentials",
        lambda: {
            "api_key": "secret-token",
            "key_source": "absolute_config_api_keys_json",
            "key_file_path_used": "/tmp/api_keys.json",
            "key_present": True,
        },
    )
    monkeypatch.setattr(probe, "OddsPapiClient", FakeClient)

    result, exit_code = probe._run_oddspapi_probe("2026-06-26T00:00:00Z", "2026-06-27T00:00:00Z")

    assert exit_code == 0
    assert result["status"] == "FAIL_ACCESS_FIXTURES"
    assert result["billable_calls_attempted"] == 1
    assert result["fixture_probe"]["http_status"] == 403
