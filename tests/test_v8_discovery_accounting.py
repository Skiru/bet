"""Test suite for discovery accounting cases 31-38."""

import pytest
from bet.discovery.accounting import DiscoveryAccountingEngine, DiscoveryAccountingSummary


# C4_CASE_31_GENUINELY_NEW_COUNT
def test_c4_case_31_genuinely_new_count():
    engine = DiscoveryAccountingEngine()
    fetched = [{"canonical_event_id": "evt_new_1", "provider": "p1", "provider_event_id": "p_1"}]
    summary = engine.calculate_accounting(fetched, existing_canonical_ids=set(), existing_source_refs=set())
    assert summary.genuinely_new_events == 1


# C4_CASE_32_EXISTING_UPDATE_COUNT
def test_c4_case_32_existing_update_count():
    engine = DiscoveryAccountingEngine()
    fetched = [{"canonical_event_id": "evt_1", "provider": "p1", "provider_event_id": "p_1", "is_updated": True}]
    summary = engine.calculate_accounting(fetched, existing_canonical_ids={"evt_1"}, existing_source_refs={("p1", "p_1")})
    assert summary.existing_events_updated == 1


# C4_CASE_33_NEW_SOURCE_REF_COUNT
def test_c4_case_33_new_source_ref_count():
    engine = DiscoveryAccountingEngine()
    fetched = [{"canonical_event_id": "evt_1", "provider": "p2", "provider_event_id": "p_2"}]
    summary = engine.calculate_accounting(fetched, existing_canonical_ids={"evt_1"}, existing_source_refs={("p1", "p_1")})
    assert summary.new_provider_refs == 1


# C4_CASE_34_UNCHANGED_COUNT
def test_c4_case_34_unchanged_count():
    engine = DiscoveryAccountingEngine()
    fetched = [{"canonical_event_id": "evt_1", "provider": "p1", "provider_event_id": "p_1"}]
    summary = engine.calculate_accounting(fetched, existing_canonical_ids={"evt_1"}, existing_source_refs={("p1", "p_1")})
    assert summary.unchanged_events == 1


# C4_CASE_35_CONFLICT_COUNT
def test_c4_case_35_conflict_count():
    engine = DiscoveryAccountingEngine()
    fetched = [{"canonical_event_id": "evt_1", "provider": "p1", "provider_event_id": "p_1", "is_conflict": True}]
    summary = engine.calculate_accounting(fetched, existing_canonical_ids=set(), existing_source_refs=set())
    assert summary.identity_conflicts == 1


# C4_CASE_36_INVALID_COUNT
def test_c4_case_36_invalid_count():
    engine = DiscoveryAccountingEngine()
    fetched = [{"canonical_event_id": "", "provider": "p1", "provider_event_id": "p_1", "is_invalid": True}]
    summary = engine.calculate_accounting(fetched, existing_canonical_ids=set(), existing_source_refs=set())
    assert summary.rejected_invalid_events == 1


# C4_CASE_37_SECOND_RUN_IDEMPOTENT
def test_c4_case_37_second_run_idempotent():
    engine = DiscoveryAccountingEngine()
    fetched = [{"canonical_event_id": "evt_1", "provider": "p1", "provider_event_id": "p_1"}]

    # Run 1: new
    summary1 = engine.calculate_accounting(fetched, existing_canonical_ids=set(), existing_source_refs=set())
    assert summary1.genuinely_new_events == 1

    # Run 2: existing
    summary2 = engine.calculate_accounting(fetched, existing_canonical_ids={"evt_1"}, existing_source_refs={("p1", "p_1")})
    assert summary2.genuinely_new_events == 0
    assert summary2.unchanged_events == 1


# C4_CASE_38_ACCOUNTING_EXACT
def test_c4_case_38_accounting_exact():
    engine = DiscoveryAccountingEngine()
    fetched = [
        {"canonical_event_id": "evt_new", "provider": "p1", "provider_event_id": "p1"},
        {"canonical_event_id": "evt_old", "provider": "p2", "provider_event_id": "p2"},
        {"canonical_event_id": "evt_old", "provider": "p1", "provider_event_id": "p1"},
        {"canonical_event_id": "evt_old", "provider": "p1", "provider_event_id": "p1", "is_updated": True},
        {"canonical_event_id": "evt_conf", "provider": "p1", "provider_event_id": "p3", "is_conflict": True},
        {"canonical_event_id": "", "provider": "p1", "provider_event_id": "p4", "is_invalid": True},
    ]
    summary = engine.calculate_accounting(
        fetched,
        existing_canonical_ids={"evt_old"},
        existing_source_refs={("p1", "p1")},
    )
    assert summary.total_fetched == 6
    assert summary.genuinely_new_events + summary.existing_events_updated + summary.new_provider_refs + summary.unchanged_events + summary.identity_conflicts + summary.rejected_invalid_events == 6
