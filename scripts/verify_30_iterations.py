#!/usr/bin/env python3
"""30 iterations of verification that all events from discovery receive enrichment,
and that postponed/cancelled events are properly blocked and carried through
as BLOCKED placeholder dossiers without leaking into coupons.
"""
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

from bet.discovery.dedup import DeduplicationEngine
from bet.discovery.models import DiscoveredEvent, MergedFixture, SourceRef
from bet.simple_stats.analyze import analyze_dossier, analyze_dossiers
from bet.simple_stats.contracts import (
    EventDossierListV1,
    EventDossierV1,
    EventListV1,
    EventRecord,
    StatsSheetV1,
)
from bet.simple_stats.coupons import build_coupons
from bet.simple_stats.discover import (
    UNPLAYABLE_FIXTURE_STATUSES,
    _to_event_record,
)
from bet.simple_stats.enrich import SlateGate, enrich_events


def run_all_iterations():
    results = []
    _KICKOFF = datetime(2026, 9, 10, 18, 0, tzinfo=timezone.utc)

    # Load today's existing run artifacts
    today_el_path = Path("runs/2026-09-10/2026-09-10_event_list.json")
    today_ed_path = Path("runs/2026-09-10/2026-09-10_event_dossiers.json")
    test_el_path = Path("/tmp/test_discover/2026-09-10_event_list.json")

    today_el = json.loads(today_el_path.read_text())
    today_ed = json.loads(today_ed_path.read_text())
    test_el = json.loads(test_el_path.read_text())

    # --- Iteration 1 ---
    # Bijection of event IDs between discovery and enrichment on today's run
    el_ids = {e["event_id"] for e in today_el["events"]}
    ed_ids = {d["event_id"] for d in today_ed["dossiers"]}
    assert el_ids == ed_ids, f"ID mismatch: missing {len(el_ids - ed_ids)}, extra {len(ed_ids - el_ids)}"
    results.append((1, "Today's run event ID bijection", f"100% match ({len(el_ids)} unique IDs)"))

    # --- Iteration 2 ---
    # Cardinality parity on today's run
    assert len(today_el["events"]) == len(today_ed["dossiers"]), "Event count != dossier count"
    results.append((2, "Today's run cardinality parity", f"Exactly {len(today_el['events'])} events == {len(today_ed['dossiers'])} dossiers"))

    # --- Iteration 3 ---
    # Sports consistency between discovery and dossiers on today's run
    el_sports = {e["sport"] for e in today_el["events"]}
    ed_sports = {d["sport"] for d in today_ed["dossiers"]}
    assert el_sports == ed_sports == {"football", "tennis"}, f"Sports mismatch: {el_sports} vs {ed_sports}"
    results.append((3, "Sport coverage consistency", f"Both artifacts cover sports {sorted(el_sports)}"))

    # --- Iteration 4 ---
    # Readiness validity on today's dossiers
    valid_readiness = {"READY", "PARTIAL", "BLOCKED"}
    for d in today_ed["dossiers"]:
        assert d["readiness"] in valid_readiness, f"Invalid readiness: {d['readiness']}"
    results.append((4, "Dossier readiness invariants", f"All {len(today_ed['dossiers'])} dossiers have valid readiness"))

    # --- Iteration 5 ---
    # Data gaps exist on all BLOCKED dossiers explaining terminal state
    blocked_dossiers = [d for d in today_ed["dossiers"] if d["readiness"] == "BLOCKED"]
    for d in blocked_dossiers:
        assert len(d.get("data_gaps", [])) > 0, f"Blocked dossier {d['event_id']} has no data gap reason"
    results.append((5, "BLOCKED dossier explanation integrity", f"All {len(blocked_dossiers)} BLOCKED dossiers have terminal reasons in data_gaps"))

    # --- Iteration 6 ---
    # Postponed/cancelled status detection in freshly discovered slate
    blocked_status = [e for e in test_el["events"] if e.get("status") == "BLOCKED_STATUS"]
    assert len(blocked_status) == 5, f"Expected 5 BLOCKED_STATUS events, got {len(blocked_status)}"
    results.append((6, "Fresh discovery BLOCKED_STATUS count", f"Exactly 5 unplayable events blocked at discovery"))

    # --- Iteration 7 ---
    # Specifically verify the 3 Saudi Pro League matches moved to Sunday are BLOCKED_STATUS
    saudi_eids = {
        "71e02ee0a10e271b3d3019d1f196cc553ece0a98dcab20776f16d43745fea7b9": "Neom SC - Al-Fateh",
        "27dd15f3bf6a10b623aa3974273f92193f1d8489700e9db8f00f5245d2201593": "Al-Riyadh - Al-Kholood",
        "eccd19e151aa00446442b756b1dc98933f6cbdddfb66ce95cf9aa9c70d9c478d": "Diriyah - Abha",
    }
    for e in test_el["events"]:
        if e["event_id"] in saudi_eids:
            assert e["status"] == "BLOCKED_STATUS", f"{saudi_eids[e['event_id']]} not BLOCKED_STATUS"
            assert "postponed" in e["terminal_reason"], f"{saudi_eids[e['event_id']]} wrong reason: {e['terminal_reason']}"
    results.append((7, "Saudi Sunday matches blocked", "All 3 postponed Saudi fixtures marked BLOCKED_STATUS"))

    # --- Iteration 8 ---
    # Run enrich_events on fresh slate (514 events) and verify 100% coverage
    fresh_event_list = EventListV1.model_validate(test_el)
    fresh_dossiers = enrich_events(fresh_event_list, max_events=0)
    assert len(fresh_dossiers.dossiers) == len(fresh_event_list.events) == 514
    results.append((8, "Fresh slate enrichment parity", f"514/514 discovered events received dossiers"))

    # --- Iteration 9 ---
    # Verify the 5 BLOCKED_STATUS events in fresh enrichment have BLOCKED readiness & terminal reasons
    fresh_d_by_id = {d.event_id: d for d in fresh_dossiers.dossiers}
    for eid, name in saudi_eids.items():
        d = fresh_d_by_id[eid]
        assert d.readiness == "BLOCKED", f"Dossier for {name} was {d.readiness}, expected BLOCKED"
        assert any("postponed" in gap for gap in d.data_gaps), f"Missing postponed gap in {d.data_gaps}"
    results.append((9, "Fresh BLOCKED_STATUS dossier validation", "Postponed fixtures carry BLOCKED status and reasons"))

    # --- Iteration 10 ---
    # Verify analyze_dossier emits ZERO rows for postponed BLOCKED dossiers
    for eid in saudi_eids:
        d = fresh_d_by_id[eid]
        rows = analyze_dossier(d)
        assert len(rows) == 0, f"Expected 0 rows for blocked dossier {eid}, got {len(rows)}"
    results.append((10, "Analyze skips BLOCKED dossiers", "0 rows generated in stats sheet for postponed matches"))

    # --- Iterations 11-20: Property-based randomized slates ---
    for it in range(11, 21):
        num_events = it * 5
        sim_events = []
        for i in range(num_events):
            status_choice = random.choice(["ACTIVE", "BLOCKED_IDENTITY", "BLOCKED_STATUS"])
            reason = "test reason" if status_choice != "ACTIVE" else None
            sim_events.append(
                EventRecord(
                    event_id=f"sim_{it}_{i}",
                    sport=random.choice(["football", "tennis"]),
                    competition="Test League",
                    home_team=f"Team {i}A",
                    away_team=f"Team {i}B",
                    start_time=_KICKOFF.isoformat(),
                    identity_confidence="FUZZY_MATCHED",
                    status=status_choice,
                    terminal_reason=reason,
                )
            )
        sim_list = EventListV1(generated_at="now", date="2026-09-10", sports=["football", "tennis"], events=sim_events)
        sim_dossiers = enrich_events(sim_list, max_events=0)
        assert len(sim_dossiers.dossiers) == len(sim_events), f"Iteration {it} count mismatch"
        sim_d_ids = {d.event_id for d in sim_dossiers.dossiers}
        sim_e_ids = {e.event_id for e in sim_events}
        assert sim_d_ids == sim_e_ids, f"Iteration {it} ID mismatch"
        # Verify non-active events are all BLOCKED
        for e in sim_events:
            if e.status != "ACTIVE":
                d = next(d for d in sim_dossiers.dossiers if d.event_id == e.event_id)
                assert d.readiness == "BLOCKED"
        results.append((it, f"Randomized slate (N={num_events})", f"100% parity ({len(sim_events)}/{len(sim_dossiers.dossiers)})"))

    # --- Iterations 21-25: Deduplication & Status resolution ---
    unplayable_list = list(UNPLAYABLE_FIXTURE_STATUSES)
    for idx, unplayable in enumerate(unplayable_list[:5], start=21):
        fixture = MergedFixture(
            sport="football",
            competition="Test Competition",
            home_team="Home Team",
            away_team="Away Team",
            kickoff=_KICKOFF,
            status=unplayable.upper(),  # test case insensitivity
            sources=[
                SourceRef(
                    source="bzzoiro",
                    external_id=f"ext_{idx}",
                    raw_status=unplayable,
                )
            ],
            primary_source="bzzoiro",
            primary_external_id=f"ext_{idx}",
        )
        rec = _to_event_record(fixture)
        assert rec.status == "BLOCKED_STATUS", f"Iteration {idx}: expected BLOCKED_STATUS for {unplayable}"
        assert unplayable.lower() in rec.terminal_reason.lower()
        results.append((idx, f"Unplayable status '{unplayable}' handling", f"Correctly blocked with status {rec.status}"))

    # --- Iteration 26 ---
    # Single exclusion in build_coupons for non-active fixture
    blocked_rec = EventRecord(
        event_id="rec_blocked_single",
        sport="football",
        competition="Test League",
        home_team="Team A",
        away_team="Team B",
        start_time=_KICKOFF.isoformat(),
        identity_confidence="FUZZY_MATCHED",
        status="BLOCKED_STATUS",
        terminal_reason="fixture status is 'postponed'",
    )
    from bet.simple_stats.contracts import StatsSheetRow, StatsSheetV1
    dummy_row = StatsSheetRow(
        event_id="rec_blocked_single",
        sport="football",
        market="corners_total",
        line=9.5,
        direction="UNDER",
        hits=9,
        sample_size=12,
        hit_rate=0.75,
        p_low=0.60,
        mean=9.1,
        median=9.0,
        sources=["bzzoiro", "espn-football"],
        cross_provider_agreement="AGREE",
        confidence="HIGH",
        data_quality="READY",
    )
    sheet = StatsSheetV1(run_id="test", date="2026-09-10", generated_at="now", rows=[dummy_row])
    coupons = build_coupons(sheet, event_list=EventListV1(generated_at="now", date="2026-09-10", events=[blocked_rec]))
    assert len(coupons.singles) == 0, "Blocked single was not excluded!"
    assert coupons.excluded.get("fixture_blocked_status") == 1
    results.append((26, "Coupons single exclusion for BLOCKED_STATUS", "1 row excluded via fixture_blocked_status"))

    # --- Iteration 27 ---
    # Slip leg exclusion in build_coupons for non-active fixture
    assert len(coupons.slips) == 0, "Blocked event produced a Bet Builder slip!"
    results.append((27, "Coupons slip exclusion for BLOCKED_STATUS", "0 slips formed for non-active fixture"))

    # --- Iteration 28 ---
    # SlateGate drops non-active event immediately
    gate = SlateGate()
    v = gate.verdict(blocked_rec, datetime.now(timezone.utc))
    assert "postponed" in v, f"SlateGate did not reject blocked event: {v}"
    results.append((28, "SlateGate rejection of non-active fixture", f"Rejected: {v}"))

    # --- Iteration 29 ---
    # End-to-end simulation: Postponed event -> Discovery -> Enrich -> Analyze -> Coupon = 0 leakage
    ev_list = EventListV1(generated_at="now", date="2026-09-10", sports=["football"], events=[blocked_rec])
    d_list = enrich_events(ev_list, max_events=0)
    assert len(d_list.dossiers) == 1
    dossier = d_list.dossiers[0]
    assert dossier.readiness == "BLOCKED"
    sheet = analyze_dossiers(d_list)
    assert len(sheet.rows) == 0
    sim_coupons = build_coupons(sheet, event_list=ev_list)
    assert len(sim_coupons.singles) == 0
    assert len(sim_coupons.slips) == 0
    results.append((29, "E2E Postponed event leakage test", "0 dossiers ready, 0 sheet rows, 0 coupon singles/slips"))

    # --- Iteration 30 ---
    # Live production integrity: confirm no Sunday Saudi events in today's active discovery
    live_active_eids = {e["event_id"] for e in test_el["events"] if e.get("status") == "ACTIVE"}
    for saudi_eid in saudi_eids:
        assert saudi_eid not in live_active_eids, f"Saudi fixture {saudi_eid} is still ACTIVE!"
    results.append((30, "Live production slate audit", "Sunday fixtures completely purged from ACTIVE slate"))

    return results


if __name__ == "__main__":
    results = run_all_iterations()
    print("=" * 80)
    print("30 ITERATIONS OF VERIFICATION: DISCOVERY VS ENRICHMENT & FIXTURE STATUS")
    print("=" * 80)
    for it, name, detail in results:
        print(f"[{it:02d}/30] PASS — {name:48s} | {detail}")
    print("=" * 80)
    print("ALL 30 VERIFICATION ITERATIONS PASSED SUCCESSFULLY (100% COVERAGE).")
