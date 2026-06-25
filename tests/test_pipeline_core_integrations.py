from __future__ import annotations

from pathlib import Path

import pytest

from bet.pipeline.core_integration_contracts import live_integrations_allowed
from bet.pipeline.core_integration_inventory import INTEGRATIONS_REVIEWED
from bet.pipeline.integration_artifacts import write_script_evidence
from bet.pipeline.runtime_modes import LIVE_ACK_KEY, LIVE_ACK_VALUE, RuntimeMode
from bet.pipeline.runtime_paths import build_runtime_env
from bet.pipeline.tipster_artifacts import build_tipster_consensus_artifact
from scripts import coupon_builder
from bet.scrapers.betclic import parse_event_page


def _collect_forbidden_keys(payload):
    forbidden = {"edge", "stake", "coupon"}
    found = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in forbidden:
                    found.append(key)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return found


def test_live_integrations_require_runtime_live_ack():
    ok, reason = live_integrations_allowed("S2", environ={"BET_PIPELINE_RUNTIME_MODE": "DRY_RUN"})
    assert ok is False
    assert reason == "BLOCKED_LIVE_NETWORK_ACK_MISSING"

    ok, reason = live_integrations_allowed("S4", environ={"BET_PIPELINE_RUNTIME_MODE": "LIVE_SHADOW"})
    assert ok is False
    assert reason == "BLOCKED_LIVE_NETWORK_ACK_MISSING"

    ok, reason = live_integrations_allowed(
        "S7b",
        environ={
            "BET_PIPELINE_RUNTIME_MODE": "LIVE_SHADOW",
            LIVE_ACK_KEY: LIVE_ACK_VALUE,
        },
    )
    assert ok is True
    assert reason == ""


def test_s8_requires_s7_and_s7b_pass_evidence_when_runtime_managed(tmp_path, monkeypatch: pytest.MonkeyPatch):
    env = build_runtime_env(RuntimeMode.LIVE_SHADOW, "2026-06-25", "run-123", base_dir=tmp_path)
    env[LIVE_ACK_KEY] = LIVE_ACK_VALUE
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    write_script_evidence(
        "S7",
        status="PASS",
        payload={"approved_count": 2},
        sources=("gate_checker",),
        evidence_refs=("s7.json",),
    )
    with pytest.raises(FileNotFoundError, match="S7b"):
        coupon_builder._require_pre_coupon_script_evidence()

    write_script_evidence(
        "S7b",
        status="PASS",
        payload={"total_events": 4},
        sources=("Betclic",),
        evidence_refs=("s7b.json",),
    )
    control = coupon_builder._require_pre_coupon_script_evidence()
    assert control["enforced"] is True
    assert control["steps"] == ["S7", "S7b"]


def test_non_s8_contracts_do_not_emit_coupon_artifacts():
    assert INTEGRATIONS_REVIEWED["S7b"] == ("Betclic",)
    assert INTEGRATIONS_REVIEWED["S8"] == ("coupon-builder",)


def test_pre_gate_artifacts_do_not_emit_internal_edge_stake_coupon_fields():
    tipster_artifact = build_tipster_consensus_artifact(
        date="2026-06-25",
        timestamp="2026-06-25T08:00:00Z",
        all_results=[],
        all_picks=[
            {
                "source_site": "ZawodTyper",
                "tipster_name": "AnalystA",
                "sport": "football",
                "event": "Liverpool vs Arsenal",
                "home_team": "Liverpool",
                "away_team": "Arsenal",
                "market": "Over 9.5 corners",
                "market_type": "statistical",
                "direction": "OVER",
                "reasoning": "backed by corners form",
                "confidence": "medium",
                "fetch_time": "2026-06-25T08:00:00Z",
            }
        ],
        consensus=[],
        enhanced_entries=[],
        errors=[],
        picks_by_sport={"football": 1},
        source_status_by_sport={"football": {"status": "configured"}},
    )
    assert _collect_forbidden_keys(tipster_artifact) == []


def test_betclic_parser_is_fixture_backed():
    fixture = Path(__file__).parent / "fixtures" / "integrations" / "betclic_event_page_template.html"
    html = fixture.read_text(encoding="utf-8").replace("__FILLER__", '"marketName":"Pad"' * 3000)
    info = parse_event_page(html)
    assert info is not None
    assert info.event_name == "Liverpool - Arsenal"
    assert info.has_statistics_tab is True
    assert "corners_total" in info.confirmed_market_types
    assert "cards_total" in info.confirmed_market_types
