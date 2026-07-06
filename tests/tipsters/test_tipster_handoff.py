from __future__ import annotations

import json
from pathlib import Path
from bet.tipsters.contracts import TipsterPick
from bet.tipsters.storage import build_payload
from bet.tipsters.handoff import build_tipster_evidence_handoff, write_handoff_artifact
from bet.tipsters.agent_readiness import analyze_pick_readiness


def test_tipster_handoff_structure_and_enforcement():
    # 1. Standard pick (valid)
    p1 = TipsterPick(
        source_id="zawodtyper",
        source_name="ZawodTyper",
        sport="football",
        event="Arsenal vs Chelsea",
        home_team="Arsenal",
        away_team="Chelsea",
        market="over 2.5 goals",
        market_family="goals",
        direction="OVER",
        line=2.5,
        odds_decimal=1.85,
        reasoning="Arsenal scored in last 10 matches, Chelsea form is very weak. Statistics back high goals.",
        extraction_quality=0.85,
    )

    # 2. Ambiguous event pick (requires match resolution)
    p2 = TipsterPick(
        source_id="zawodtyper",
        source_name="ZawodTyper",
        sport="football",
        event="SingleParticipantNameOnly",
        home_team="SingleParticipantNameOnly",
        away_team="",
        market="Winner: 1",
        market_family="winner",
        direction="HOME",
        odds_decimal=2.1,
        reasoning="This event cannot be cleanly split as there is only one team in the event name.",
        extraction_quality=0.75,
    )

    # 3. Short reasoning pick (requires manual review)
    p3 = TipsterPick(
        source_id="zawodtyper",
        source_name="ZawodTyper",
        sport="football",
        event="Real Madrid vs Barcelona",
        home_team="Real Madrid",
        away_team="Barcelona",
        market="BTTS: Yes",
        market_family="btts",
        direction="BTTS_YES",
        odds_decimal=1.65,
        reasoning="Too short",
        extraction_quality=0.8,
    )

    # Compile into payload (simulating build_payload)
    from bet.tipsters.contracts import ExtractionResult, ExtractorVerdict
    r = ExtractionResult(
        source_id="zawodtyper",
        url="https://example.test",
        verdict=ExtractorVerdict.OK,
        picks=[p1, p2, p3],
    )
    payload = build_payload([r])

    # Assert agent_readiness exists on picks
    for p in payload["all_picks"]:
        assert "agent_readiness" in p
        assert "forbidden_actions" in p["agent_readiness"]

    # Generate handoff
    handoff = build_tipster_evidence_handoff(payload)

    assert handoff["schema_version"] == "tipster_evidence_handoff_v1"
    assert handoff["contract"] == "evidence_only_not_betting_decision"
    assert "S3 contextual cross-check" in handoff["allowed_consumers"]

    # Verify that forbidden actions are absent from all event structures
    for forbidden in handoff["forbidden_actions"]:
        for ev in handoff["events"]:
            assert forbidden not in ev
            assert forbidden.lower() not in ev

    # We should have 3 event groups
    assert len(handoff["events"]) == 3

    # Resolve event keys & look up statuses
    event_map = {ev["event"]: ev for ev in handoff["events"]}

    # Verify p1 details
    ev1 = event_map["Arsenal vs Chelsea"]
    assert ev1["needs_match_resolution"] is False
    assert ev1["needs_manual_review"] is False
    assert ev1["evidence_quality"] == "HIGH"

    # Verify p2 (ambiguous match resolution)
    ev2 = event_map["SingleParticipantNameOnly"]
    assert ev2["needs_match_resolution"] is True

    # Verify p3 (manual review)
    ev3 = event_map["Real Madrid vs Barcelona"]
    assert ev3["needs_manual_review"] is True


def test_tipster_handoff_fail_closed_on_zero_picks():
    payload = {
        "sources": [],
        "total_picks": 0,
        "all_picks": [],
        "consensus": [],
        "blocked_sources": [],
        "skipped_sources": [],
        "pipeline_consumers": [],
        "fail_closed": False,
    }
    handoff = build_tipster_evidence_handoff(payload)
    assert handoff["fail_closed"] is True


def test_write_handoff_artifact(tmp_path):
    p = TipsterPick(
        source_id="zawodtyper",
        source_name="ZawodTyper",
        sport="football",
        event="Bayern vs PSG",
        home_team="Bayern",
        away_team="PSG",
        market="over 2.5 goals",
        market_family="goals",
        direction="OVER",
        line=2.5,
        odds_decimal=1.85,
        reasoning="Good statistics support a goal festival here today.",
        extraction_quality=0.85,
    )
    from bet.tipsters.contracts import ExtractionResult, ExtractorVerdict
    r = ExtractionResult(
        source_id="zawodtyper",
        url="https://example.test",
        verdict=ExtractorVerdict.OK,
        picks=[p],
    )
    payload = build_payload([r])
    out_file = tmp_path / "handoff.json"
    write_handoff_artifact(payload, out_file)

    assert out_file.exists()
    content = json.loads(out_file.read_text(encoding="utf-8"))
    assert content["schema_version"] == "tipster_evidence_handoff_v1"
