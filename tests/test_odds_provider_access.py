from __future__ import annotations

from bet.odds_provider_access import is_odds_source_enabled, odds_source_access_status


def test_oddspapi_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ODDSPAPI_ENABLE_SHADOW", raising=False)
    monkeypatch.delenv("ODDSPAPI_ENABLE_LIVE", raising=False)
    monkeypatch.delenv("ODDSPAPI_LIVE_CERTIFIED", raising=False)

    assert is_odds_source_enabled("oddspapi") is False
    status = odds_source_access_status("oddspapi")
    assert status["enabled"] is False
    assert status["production_selectable"] is False
    assert status["mode"] == "disabled"
    assert status["reason"] == "disabled_by_access_gate_fail_access_fixtures"


def test_oddspapi_shadow_enabled(monkeypatch):
    monkeypatch.setenv("ODDSPAPI_ENABLE_SHADOW", "1")
    monkeypatch.delenv("ODDSPAPI_ENABLE_LIVE", raising=False)
    monkeypatch.delenv("ODDSPAPI_LIVE_CERTIFIED", raising=False)

    assert is_odds_source_enabled("oddspapi") is True
    status = odds_source_access_status("oddspapi")
    assert status["enabled"] is True
    assert status["production_selectable"] is False
    assert status["mode"] == "shadow"


def test_oddspapi_live_requires_certification(monkeypatch):
    monkeypatch.delenv("ODDSPAPI_ENABLE_SHADOW", raising=False)
    monkeypatch.setenv("ODDSPAPI_ENABLE_LIVE", "1")
    monkeypatch.delenv("ODDSPAPI_LIVE_CERTIFIED", raising=False)

    first = odds_source_access_status("oddspapi")
    assert is_odds_source_enabled("oddspapi") is False
    assert first["production_selectable"] is False

    monkeypatch.setenv("ODDSPAPI_LIVE_CERTIFIED", "1")
    second = odds_source_access_status("oddspapi")
    assert is_odds_source_enabled("oddspapi") is True
    assert second["enabled"] is True
    assert second["production_selectable"] is True
    assert second["mode"] == "live"
