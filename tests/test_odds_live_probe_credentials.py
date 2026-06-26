from __future__ import annotations

from pathlib import Path
import types

from scripts import odds_live_probe_superbet_betclic as probe


def test_load_oddspapi_credentials_prefers_absolute_file(tmp_path: Path, monkeypatch, capsys) -> None:
    key_file = tmp_path / "api_keys.json"
    key_file.write_text('{"odds-papi": "file-secret-token"}\n', encoding="utf-8")
    monkeypatch.setattr(probe, "ABS_ODDSPAPI_KEYS_FILE", key_file)
    monkeypatch.delenv("ODDSPAPI_API_KEY", raising=False)

    credential = probe.load_oddspapi_credentials()

    assert credential["api_key"] == "file-secret-token"
    assert credential["key_source"] == "absolute_config_api_keys_json"
    assert credential["key_file_path_used"] == str(key_file)
    assert credential["key_present"] is True
    captured = capsys.readouterr()
    assert "file-secret-token" not in captured.out
    assert captured.out == ""


def test_load_oddspapi_credentials_prefers_env_over_absolute_file(tmp_path: Path, monkeypatch) -> None:
    key_file = tmp_path / "api_keys.json"
    key_file.write_text('{"odds-papi": "file-secret-token"}\n', encoding="utf-8")
    monkeypatch.setattr(probe, "ABS_ODDSPAPI_KEYS_FILE", key_file)
    monkeypatch.setenv("ODDSPAPI_API_KEY", "env-secret-token")

    credential = probe.load_oddspapi_credentials()

    assert credential["api_key"] == "env-secret-token"
    assert credential["key_source"] == "env"
    assert credential["key_file_path_used"] is None
    assert credential["key_present"] is True


def test_load_oddspapi_credentials_returns_missing_when_file_absent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(probe, "ABS_ODDSPAPI_KEYS_FILE", tmp_path / "missing.json")
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
