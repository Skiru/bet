"""Tests for bet.simple_stats.enrich: multi-provider combine + fail-open concurrency.

Reuses the real captured Highlightly/SportDB payloads from
tests/fixtures/reports/football_data_foundation/live_response_corpus (Norway
vs Senegal, WC 2026) instead of hand-written mocks.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import bet.simple_stats.enrich as enrich_module
from bet.simple_stats import providers
from bet.simple_stats.analyze import _cross_provider_agreement, corroborated_matches
from bet.simple_stats.contracts import EventListV1, EventRecord, ProviderValue
from bet.simple_stats.enrich import _compute_readiness, enrich_events
from bet.simple_stats.providers import FetchOutcome

FIXTURE_ROOT = (
    Path(__file__).parent.parent
    / "fixtures/reports/football_data_foundation/live_response_corpus/run_v3_20260623_131229"
)


def _load(relative_path: str) -> dict:
    return json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))


def test_three_providers_populate_same_metric():
    highlightly_payload = _load("highlightly/worldcup2026-norway-senegal_statistics.json")
    sportdb_payload = _load("sportdb/worldcup2026-norway-senegal_match_stats.json")

    highlightly_combined = providers.normalize_highlightly_statistics(highlightly_payload)
    sportdb_combined = providers.normalize_sportdb_match_stats(sportdb_payload)
    # ESPN's own client normalization is exercised elsewhere in the repo;
    # stand in with the same {"home": x, "away": y}-shaped stats dict its
    # client would hand back for this exact match.
    espn_combined = providers._combined_from_dict_stats(
        {"corners": {"home": 5, "away": 4}}, providers._ESPN_FOOTBALL_ALIASES
    )

    assert highlightly_combined["corners_total"] == 9
    assert sportdb_combined["corners_total"] == 9
    assert espn_combined["corners_total"] == 9

    observations = [
        providers._make_values("espn-football", "m1", "2026-06-23", "Senegal", espn_combined)["corners_total"],
        providers._make_values("highlightly", "m1", "2026-06-23", "Senegal", highlightly_combined)["corners_total"],
        providers._make_values("sportdb", "m1", "2026-06-23", "Senegal", sportdb_combined)["corners_total"],
    ]

    assert {o.provider for o in observations} == {"espn-football", "highlightly", "sportdb"}
    # Three providers, but still one corroborated *match* -- and the unit
    # MIN_CORROBORATED_MATCHES counts is matches, because the question it
    # answers is how much of the sample a second source has actually verified.
    # One match out of a ten-match sample is 10% verified whether two providers
    # cover it or five. So the claim here is asserted where it lives: they
    # clustered into one match rather than three single-source ones.
    assert corroborated_matches("corners_total", observations) == 1
    assert _cross_provider_agreement("corners_total", observations) == "SINGLE_SOURCE"


def test_disagreement_not_silently_averaged():
    observations = [
        ProviderValue(
            provider="highlightly", match_id="m1", match_date="2026-06-23",
            opponent="Senegal", value=9.0, observed_at="2026-06-23T00:00:00+00:00",
        ),
        ProviderValue(
            provider="sportdb", match_id="m1", match_date="2026-06-23",
            opponent="Senegal", value=15.0, observed_at="2026-06-23T00:00:00+00:00",
        ),
    ]

    assert _cross_provider_agreement("corners_total", observations) == "DISAGREE"
    # both values survive untouched -- never silently averaged into one
    assert {o.value for o in observations} == {9.0, 15.0}


def test_zero_enrichable_data_yields_blocked():
    assert _compute_readiness("football", {}) == "BLOCKED"


def test_one_provider_failure_does_not_abort_run(monkeypatch):
    event = EventRecord(
        event_id="evt1",
        sport="football",
        competition="Test League",
        home_team="Team A",
        away_team="Team B",
        start_time="2026-08-25T18:00:00+00:00",
        source_ids={},
        identity_confidence="CONFIRMED",
        status="ACTIVE",
    )
    event_list = EventListV1(generated_at="x", date="2026-08-25", sports=["football"], events=[event])

    def _team_metrics(provider, *args, **kwargs):
        if provider == "espn-football":
            raise RuntimeError("provider exploded")
        return FetchOutcome()

    monkeypatch.setattr(enrich_module, "fetch_provider_team_metrics", _team_metrics)
    monkeypatch.setattr(enrich_module, "fetch_provider_h2h_metrics", lambda *a, **kw: FetchOutcome())
    monkeypatch.setattr(enrich_module, "fetch_highlightly_history", lambda *a, **kw: FetchOutcome())
    monkeypatch.setattr(enrich_module, "fetch_sportdb_history", lambda *a, **kw: FetchOutcome())

    dossier_list = enrich_events(event_list)

    assert len(dossier_list.dossiers) == 1
    dossier = dossier_list.dossiers[0]
    assert any("espn-football" in gap and "unhandled error" in gap for gap in dossier.data_gaps)


def test_blocked_identity_event_carried_through_as_blocked_dossier():
    # No ACTIVE events here: enrich_events must skip network entirely and
    # only carry BLOCKED_IDENTITY events through as placeholder dossiers.
    blocked = EventRecord(
        event_id="evt-blocked",
        sport="football",
        competition="Test League",
        home_team="Team C",
        away_team="Team D",
        start_time="2026-08-25T18:00:00+00:00",
        source_ids={},
        identity_confidence="AMBIGUOUS",
        status="BLOCKED_IDENTITY",
        terminal_reason="conflicting start_time across sources",
    )
    event_list = EventListV1(generated_at="x", date="2026-08-25", sports=["football"], events=[blocked])

    dossier_list = enrich_events(event_list)
    ids = {d.event_id: d for d in dossier_list.dossiers}
    assert "evt-blocked" in ids
    assert ids["evt-blocked"].readiness == "BLOCKED"
    assert "conflicting start_time" in ids["evt-blocked"].data_gaps[0]


def _event(event_id: str, start_time: str, **overrides) -> EventRecord:
    return EventRecord(
        event_id=event_id,
        sport="football",
        competition=overrides.pop("competition", "Test League"),
        home_team=overrides.pop("home_team", f"{event_id} home"),
        away_team=overrides.pop("away_team", f"{event_id} away"),
        start_time=start_time,
        source_ids={},
        identity_confidence=overrides.pop("identity_confidence", "FUZZY_MATCHED"),
        status="ACTIVE",
        **overrides,
    )


def test_started_events_sort_behind_upcoming_ones_under_a_cap():
    """2026-08-25: three of five slots went to K League fixtures that kicked off
    at 10:30 UTC while the run ended at 11:56, and Valencia - Real Betis (19:00)
    came back BLOCKED on the cap. Every event was FUZZY_MATCHED with no native
    ids, so the old (confirmed + has_native_ids, start_time) key was a constant
    followed by start_time: earliest kickoff won."""
    now = datetime(2026, 8, 25, 11, 56, tzinfo=timezone.utc)
    kicked_off = _event("k-league", "2026-08-25T10:30:00+00:00")
    imminent = _event("imminent", "2026-08-25T11:58:00+00:00")
    later = _event("valencia", "2026-08-25T19:00:00+00:00")
    evening = _event("lask", "2026-08-25T19:00:00+00:00")

    ordered = sorted(
        [kicked_off, imminent, later, evening],
        key=lambda e: enrich_module._enrichment_priority(e, now),
    )

    # Both 19:00 events share a sort key, so their relative order is just
    # sorted()'s stability -- what matters is that neither started event
    # outranks them.
    assert {e.event_id for e in ordered[:2]} == {"lask", "valencia"}
    assert {e.event_id for e in ordered[2:]} == {"k-league", "imminent"}


def test_corroboration_still_orders_events_with_the_same_kickoff_state():
    now = datetime(2026, 8, 25, 11, 56, tzinfo=timezone.utc)
    fuzzy = _event("fuzzy", "2026-08-25T19:00:00+00:00")
    confirmed = _event(
        "confirmed",
        "2026-08-25T19:00:00+00:00",
        identity_confidence="CONFIRMED",
        provider_team_ids={"highlightly": {"home": "1", "away": "2"}},
    )

    ordered = sorted(
        [fuzzy, confirmed], key=lambda e: enrich_module._enrichment_priority(e, now)
    )
    assert [e.event_id for e in ordered] == ["confirmed", "fuzzy"]


def test_unparseable_start_time_is_not_treated_as_started():
    """A start_time format we have not seen must not demote every event at once."""
    now = datetime(2026, 8, 25, 11, 56, tzinfo=timezone.utc)
    assert enrich_module._has_started(_event("bad", "not-a-timestamp"), now) is False
    assert enrich_module._has_started(_event("naive", "2026-08-25T10:30:00"), now) is True


def test_started_event_dropped_by_the_cap_says_why(monkeypatch):
    monkeypatch.setattr(enrich_module, "fetch_provider_team_metrics", lambda *a, **kw: FetchOutcome())
    monkeypatch.setattr(enrich_module, "fetch_provider_h2h_metrics", lambda *a, **kw: FetchOutcome())
    monkeypatch.setattr(enrich_module, "fetch_highlightly_history", lambda *a, **kw: FetchOutcome())
    monkeypatch.setattr(enrich_module, "fetch_sportdb_history", lambda *a, **kw: FetchOutcome())

    past = _event("past", "2000-01-01T10:30:00+00:00")
    future = _event("future", "2999-01-01T19:00:00+00:00")
    event_list = EventListV1(
        generated_at="x", date="2026-08-25", sports=["football"], events=[past, future]
    )

    dossiers = {d.event_id: d for d in enrich_events(event_list, max_events=1).dossiers}

    # The upcoming event keeps the single slot; the started one is BLOCKED with
    # a reason that names the cause, never silently dropped.
    assert dossiers["past"].readiness == "BLOCKED"
    gap = dossiers["past"].data_gaps[0]
    assert "run capped at 1 events" in gap
    assert "kickoff already passed" in gap
