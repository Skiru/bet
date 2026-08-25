"""Tests for bet.simple_stats.enrich: multi-provider combine + fail-open concurrency.

Reuses the real captured Highlightly/SportDB payloads from
tests/fixtures/reports/football_data_foundation/live_response_corpus (Norway
vs Senegal, WC 2026) instead of hand-written mocks.
"""
import json
from pathlib import Path

import bet.simple_stats.enrich as enrich_module
from bet.simple_stats import providers
from bet.simple_stats.analyze import _cross_provider_agreement
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
    assert _cross_provider_agreement("corners_total", observations) == "AGREE"


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
