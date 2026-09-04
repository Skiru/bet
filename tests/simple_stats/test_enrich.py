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
from bet.simple_stats.contracts import (
    EventListV1,
    EventRecord,
    MetricObservation,
    ProviderValue,
)
from bet.simple_stats.enrich import _compute_readiness, enrich_events
from bet.api_clients.rate_limiter import RateLimiter
from bet.simple_stats.providers import FetchOutcome, metric_capable_providers

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


def _obs(canonical_name, pairs, h2h=()):
    """A MetricObservation from (provider, match_id, side) triples."""
    def pv(provider, match_id):
        return ProviderValue(
            provider=provider, match_id=match_id, match_date="2026-08-31",
            opponent="X", value=1.0, observed_at="2026-08-31T00:00:00+00:00",
        )
    return MetricObservation(
        canonical_name=canonical_name,
        team_a_l10=[pv(p, m) for p, m, side in pairs if side == "a"],
        team_b_l10=[pv(p, m) for p, m, side in pairs if side == "b"],
        h2h=[pv(p, m) for p, m in h2h],
    )


def _tennis_metrics(providers_per_metric, depth=5):
    """One dossier's three tennis priority metrics, each with a given roster."""
    return {
        name: _obs(
            name,
            [(prov, f"{name}-{prov}-{side}-{i}", side)
             for prov in roster for side in ("a", "b") for i in range(depth)],
        )
        for name, roster in providers_per_metric.items()
    }


def test_tennis_ready_is_reachable_at_all():
    """The bar tennis could never clear: aces/double faults have one provider.

    espn-tennis serves total games and total sets and nothing else, so a rule
    demanding 2+ providers on all three priority metrics asked for 3 where the
    ceiling is 1. Every tennis dossier was PARTIAL by construction.
    """
    assert len(metric_capable_providers("tennis", "aces_total")) == 1
    assert len(metric_capable_providers("tennis", "double_faults_total")) == 1
    assert len(metric_capable_providers("tennis", "total_games")) == 2

    metrics = _tennis_metrics({
        "total_games": ("tennis-abstract", "espn-tennis"),
        "aces_total": ("tennis-abstract",),
        "double_faults_total": ("tennis-abstract",),
    })
    assert _compute_readiness("tennis", metrics) == "READY"


def test_tennis_single_source_metric_still_needs_depth():
    """Depth replaces the impossible second opinion; it does not waive it.

    Four matches a side on the single-sourced metrics is below the same floor
    the primary branch asks of bzzoiro, so this stays PARTIAL.
    """
    metrics = _tennis_metrics({
        "total_games": ("tennis-abstract", "espn-tennis"),
        "aces_total": ("tennis-abstract",),
        "double_faults_total": ("tennis-abstract",),
    }, depth=4)
    assert _compute_readiness("tennis", metrics) == "PARTIAL"


def test_tennis_one_sided_sample_is_not_ready():
    """A metric covering only one of the two players is not a readable fixture.

    This is the 2026-08-31 dossier whose first player had no aces sample at
    all -- the depth floor is per side precisely so it cannot pass.
    """
    metrics = _tennis_metrics({
        "total_games": ("tennis-abstract", "espn-tennis"),
        "aces_total": ("tennis-abstract",),
        "double_faults_total": ("tennis-abstract",),
    })
    metrics["aces_total"] = _obs(
        "aces_total", [("tennis-abstract", f"m{i}", "b") for i in range(10)]
    )
    assert _compute_readiness("tennis", metrics) == "PARTIAL"


def test_tennis_corroboratable_metric_still_needs_two_providers():
    """total_games *can* have a second opinion, so one provider is not enough."""
    metrics = _tennis_metrics({
        "total_games": ("tennis-abstract",),
        "aces_total": ("tennis-abstract",),
        "double_faults_total": ("tennis-abstract",),
    })
    assert _compute_readiness("tennis", metrics) == "PARTIAL"


def test_football_readiness_unchanged_by_the_tennis_repair():
    """Football has a primary, so it never reaches the capability branch."""
    deep = {
        name: _obs(name, [("bzzoiro", f"{name}-{side}-{i}", side)
                          for side in ("a", "b") for i in range(5)])
        for name in ("corners_total", "cards_total", "shots_total")
    }
    assert _compute_readiness("football", deep) == "READY"
    thin = {
        name: _obs(name, [("bzzoiro", f"{name}-{side}-{i}", side)
                          for side in ("a", "b") for i in range(4)])
        for name in ("corners_total", "cards_total", "shots_total")
    }
    assert _compute_readiness("football", thin) == "PARTIAL"
    # Two corroborators on every metric cannot buy READY without the primary's
    # own sample: the primary branch is not a fallback.
    corroborated = {
        name: _obs(name, [(prov, f"{name}-{prov}-{side}-{i}", side)
                          for prov in ("espn-football", "highlightly")
                          for side in ("a", "b") for i in range(10)])
        for name in ("corners_total", "cards_total", "shots_total")
    }
    assert _compute_readiness("football", corroborated) == "PARTIAL"


def test_one_provider_failure_does_not_abort_run(monkeypatch):
    event = EventRecord(
        event_id="evt1",
        sport="football",
        competition="Test League",
        home_team="Team A",
        away_team="Team B",
        start_time="2026-08-25T18:00:00+00:00",
        # Carries bzzoiro identity because espn-football is a *corroborator*
        # since 2026-09-02: _build_tasks does not schedule one for a fixture the
        # primary provider never saw, so an event with empty source_ids would
        # never reach the exploding provider and the test would pass vacuously.
        source_ids={"bzzoiro": "m1"},
        provider_team_ids={"bzzoiro": {"home": "1", "away": "2"}},
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


# ── The slate gate ──────────────────────────────────────────────────────────
#
# What it is defending against, measured on the 2026-09-02 run: 325 dossiers,
# of which 113 were already past kickoff when ENRICH ran, 155 had no Superbet
# offer, and 235 of the 287 football fixtures were never discovered by bzzoiro.
# Every one of those was enriched at full provider cost and could not reach a
# coupon.


def _gate_event(
    event_id="e1",
    *,
    sport="football",
    competition="Premier League",
    start_time="2999-01-01T18:00:00+00:00",
    bzzoiro=True,
):
    return EventRecord(
        event_id=event_id,
        sport=sport,
        competition=competition,
        home_team="Team A",
        away_team="Team B",
        start_time=start_time,
        source_ids={"bzzoiro": "m1"} if bzzoiro else {"highlightly": "h1"},
        provider_team_ids={"bzzoiro": {"home": "1", "away": "2"}} if bzzoiro else {},
        identity_confidence="CONFIRMED",
        status="ACTIVE",
    )


def _offer(*, priced_event_ids=(), our_events=()):
    """A SUPERBET_OFFER_V1 carrying markets for exactly ``priced_event_ids``."""
    from bet.simple_stats.contracts import SuperbetEventOffer, SuperbetOfferV1

    return SuperbetOfferV1(
        generated_at="2026-09-02T10:00:00+00:00",
        date="2026-09-02",
        events=[
            SuperbetEventOffer(
                superbet_event_id=f"sb-{event_id}",
                superbet_match_name="A - B",
                sport="football",
                kickoff="2026-09-02T18:00:00Z",
                event_id=event_id,
                market_count=3 if event_id in priced_event_ids else 0,
            )
            for event_id in our_events
        ],
    )


def _gate_for(events, offer=None, **kwargs):
    from bet.simple_stats.enrich import build_slate_gate

    event_list = EventListV1(
        generated_at="x", date="2026-09-02", sports=["football"], events=events
    )
    return build_slate_gate(event_list, offer, **kwargs)


NOW = datetime(2026, 9, 2, 18, 0, tzinfo=timezone.utc)


def test_a_fixture_the_primary_provider_never_saw_is_not_enriched():
    """bzzoiro serves 55 metrics a match; a corroborator serves 6. A fixture
    only the corroborator has is not a thin sample, it is a different sheet."""
    event = _gate_event(bzzoiro=False)
    reason = _gate_for([event]).verdict(event, NOW)
    assert "bzzoiro did not discover this fixture" in reason


def test_a_fixture_already_under_way_is_not_enriched():
    event = _gate_event(start_time="2026-09-02T17:00:00+00:00")
    assert "kickoff already passed" in _gate_for([event]).verdict(event, NOW)


def test_a_past_day_is_enriched_despite_every_kickoff_having_passed():
    """A backfill or a re-analysis runs over a finished day. Enforcing kickoff
    there would empty the slate rather than protect it."""
    event = _gate_event(start_time="2026-09-02T17:00:00+00:00")
    gate = _gate_for([event], enforce_kickoff=False)
    assert gate.verdict(event, NOW) == ""


def test_an_unpriced_fixture_is_dropped_when_superbet_prices_its_competition():
    priced = _gate_event("priced", competition="Copa Colombia")
    unpriced = _gate_event("unpriced", competition="Copa Colombia")
    gate = _gate_for(
        [priced, unpriced],
        _offer(priced_event_ids={"priced"}, our_events=["priced", "unpriced"]),
    )
    assert gate.verdict(priced, NOW) == ""
    assert "prices other fixtures of 'Copa Colombia'" in gate.verdict(unpriced, NOW)


def test_a_competition_superbet_priced_nothing_of_is_not_read_as_a_refusal():
    """The join is by name and kickoff, so one fixture's absence is ambiguous.
    A whole competition's is not -- and when Superbet matched none of it, the
    silence is more likely our matcher than the book.

    2026-09-02: this is what keeps Sint-Truidense - Union Saint-Gilloise
    (Belgian Pro League, nothing of which the matcher joined) while still
    dropping Atletico Nacional - Deportivo Cali (Copa Colombia, whose other
    fixture Superbet priced).
    """
    priced = _gate_event("priced", competition="Copa Colombia")
    elsewhere = _gate_event("elsewhere", competition="Pro League")
    gate = _gate_for(
        [priced, elsewhere],
        _offer(priced_event_ids={"priced"}, our_events=["priced", "elsewhere"]),
    )
    assert gate.verdict(elsewhere, NOW) == ""


def test_a_fixture_already_under_way_when_the_board_was_read_is_not_read_as_unpriced():
    """The defect that would have deleted the best half of a tennis slate.

    Superbet is read with ``offerState=prematch``, which stops carrying a
    fixture the moment it goes live -- so on the 2026-09-02 offer, collected at
    17:40 UTC, every US Open match starting before then was absent from the
    board. Read as a refusal to price, rule 3 dropped 19 of 38, among them Ben
    Shelton - Hubert Hurkacz and Jessica Pegula - Sofia Kenin. They were not
    unpriced; they were under way, which is rule 2's verdict and not rule 3's.
    """
    from bet.simple_stats.contracts import SuperbetOfferV1

    priced = _gate_event("priced", competition="ATP US Open",
                         start_time="2026-09-02T18:00:00+00:00", bzzoiro=False, sport="tennis")
    started = _gate_event("started", competition="ATP US Open",
                          start_time="2026-09-02T15:00:00+00:00", bzzoiro=False, sport="tennis")
    later = _gate_event("later", competition="ATP US Open",
                        start_time="2026-09-02T19:00:00+00:00", bzzoiro=False, sport="tennis")
    offer = _offer(priced_event_ids={"priced"}, our_events=["priced", "started", "later"])
    offer = SuperbetOfferV1(**{
        **offer.model_dump(),
        "generated_at": "2026-09-02T17:40:00+00:00",
    })
    gate = _gate_for([priced, started, later], offer)

    morning = datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc)
    # Absent from the board *and* already under way when it was read: rule 3
    # has nothing to say, and on a live clock rule 2 answers it instead.
    assert gate.verdict(started, morning) == ""
    assert "kickoff already passed" in gate.verdict(
        started, datetime(2026, 9, 2, 17, 40, tzinfo=timezone.utc)
    )
    # Absent from a board that was still carrying it: a real refusal.
    assert "prices other fixtures of 'ATP US Open'" in gate.verdict(later, morning)


def test_without_an_offer_the_gate_keeps_its_first_two_rules_only():
    """A skipped or failed SUPERBET must not read as "the book prices nothing"."""
    event = _gate_event()
    gate = _gate_for([event], None)
    assert gate.have_offer is False
    assert gate.verdict(event, NOW) == ""


def test_an_empty_offer_cannot_delete_the_slate():
    """The direction this has to fail in.

    A SUPERBET step that failed, ran before the board was posted, or matched
    nothing yields an offer with no priced fixtures -- and therefore no priced
    competitions, so rule 3 has nothing to fire on. The alternative reading
    ("Superbet prices nothing today") would refuse every fixture of the day.
    """
    events = [_gate_event("a"), _gate_event("b", competition="Serie A")]
    gate = _gate_for(events, _offer(priced_event_ids=set(), our_events=["a", "b"]))
    assert gate.have_offer is True
    assert gate.priced_competitions == frozenset()
    assert all(gate.verdict(e, NOW) == "" for e in events)


def test_a_priced_competition_in_one_sport_does_not_gate_another(monkeypatch):
    """``priced_competitions`` is keyed by (sport, competition). A bare name is
    not unique across sports, and a football fixture must not be refused
    because a tennis tournament of the same name was priced."""
    football = _gate_event("f", sport="football", competition="Open")
    tennis = _gate_event("t", sport="tennis", competition="Open", bzzoiro=False)
    priced_tennis = _gate_event("t2", sport="tennis", competition="Open", bzzoiro=False)
    gate = _gate_for(
        [football, tennis, priced_tennis],
        _offer(priced_event_ids={"t2"}, our_events=["f", "t", "t2"]),
    )
    assert gate.verdict(football, NOW) == ""
    assert "prices other fixtures of 'Open'" in gate.verdict(tennis, NOW)


def test_a_truncated_board_cannot_call_a_fixture_unpriced():
    """SUPERBET caps how many matched fixtures it fetches lines for, and the
    ones it skips land in ``our_events_without_offer`` beside genuine absences.
    Rule 3 cannot tell them apart, so a truncated offer switches it off.

    Measured on the live 2026-09-03 run: a cap of 30 made 9 priced fixtures
    read as unpriced. The cap was the ENRICH quota cap, shared with SUPERBET
    for no reason other than that it was the number to hand.
    """
    from bet.simple_stats.contracts import SuperbetOfferV1

    priced = _gate_event("priced", competition="Serie A")
    unpriced = _gate_event("unpriced", competition="Serie A")
    offer = _offer(priced_event_ids={"priced"}, our_events=["priced", "unpriced"])

    intact = _gate_for([priced, unpriced], offer)
    assert "prices other fixtures" in intact.verdict(unpriced, NOW)

    truncated = SuperbetOfferV1(**{**offer.model_dump(), "events_capped": 7})
    gate = _gate_for([priced, unpriced], truncated)
    assert gate.have_offer is False
    assert gate.verdict(unpriced, NOW) == ""


def test_events_skipped_by_the_cap_are_not_counted_as_gate_refusals():
    """"We chose not to" and "we could not afford to" are different facts, and
    conflating them is how a shrinking slate stops being readable. On the live
    2026-09-03 run 13 of 25 not-enriched entries were cap skips reported as
    unclassified gate drops."""
    from bet.simple_stats.enrich import gate_drop_kind

    assert gate_drop_kind("not enriched: run capped at 30 events") == "capped"
    # The cap's own message can contain a gate phrase. The cap is the operative
    # fact -- the event was never refused, it lost a ranking -- so it wins.
    assert gate_drop_kind(
        "not enriched: run capped at 30 events (kickoff already passed, "
        "deprioritized: not bettable pre-match)"
    ) == "capped"


def test_every_gate_reason_has_a_kind():
    """GATE_DROP_KINDS is what the run summary counts, and it is matched against
    the reasons by substring. A reason nobody can count is a slate that shrinks
    with no reported cause -- the exact failure the gate exists to make visible.
    """
    from bet.simple_stats.enrich import gate_drop_kind

    no_primary = _gate_event(bzzoiro=False)
    started = _gate_event(start_time="2026-09-02T17:00:00+00:00")
    priced = _gate_event("priced", competition="Copa Colombia")
    unpriced = _gate_event("unpriced", competition="Copa Colombia")
    gate_with_offer = _gate_for(
        [priced, unpriced], _offer(priced_event_ids={"priced"}, our_events=["priced", "unpriced"])
    )
    plain = _gate_for([no_primary, started], None)

    seen = {
        gate_drop_kind("not enriched: " + plain.verdict(no_primary, NOW)),
        gate_drop_kind("not enriched: " + plain.verdict(started, NOW)),
        gate_drop_kind("not enriched: " + gate_with_offer.verdict(unpriced, NOW)),
    }
    assert seen == {"no_primary_identity", "kickoff_passed", "not_priced"}
    assert gate_drop_kind("highlightly: SCHEMA_ERROR") is None


def test_gated_events_are_reported_as_blocked_with_the_reason(monkeypatch):
    """Never silently dropped: a fixture the gate refused is accounted for in
    the artifact, so a shrinking slate is readable rather than mysterious."""
    kept = _gate_event("kept")
    refused = _gate_event("refused", bzzoiro=False)
    event_list = EventListV1(
        generated_at="x", date="2026-09-02", sports=["football"], events=[kept, refused]
    )
    monkeypatch.setattr(enrich_module, "fetch_provider_team_metrics", lambda *a, **kw: FetchOutcome())
    monkeypatch.setattr(enrich_module, "fetch_provider_h2h_metrics", lambda *a, **kw: FetchOutcome())
    monkeypatch.setattr(enrich_module, "fetch_bzzoiro_history", lambda *a, **kw: FetchOutcome())
    monkeypatch.setattr(enrich_module, "fetch_highlightly_history", lambda *a, **kw: FetchOutcome())
    monkeypatch.setattr(enrich_module, "_fixture_extras_for_event", lambda *a, **kw: enrich_module._FixtureExtras())

    dossiers = enrich_events(
        event_list, slate_gate=_gate_for([kept, refused], None)
    ).dossiers
    by_id = {d.event_id: d for d in dossiers}
    assert len(dossiers) == 2
    assert by_id["refused"].readiness == "BLOCKED"
    assert any(g.startswith("not enriched: ") for g in by_id["refused"].data_gaps)
    assert not any(g.startswith("not enriched: ") for g in by_id["kept"].data_gaps)

class _StaleCacheClient:
    """A tennis-abstract stand-in whose whole scrape stopped in 2018.

    The real shape of the 2026-09-04 failure: 65 of 349 cached players end in
    2018 or earlier, and for Medvedev, Tsitsipas and Tommy Paul every row the
    provider returned was discarded by the age guard.
    """

    def __init__(self, dates):
        self._dates = dates

    def resolve_team_id(self, team_name, **kwargs):
        # tennis-abstract addresses players by name, so the id *is* the name --
        # which is also what lets _opponent_of attribute each row to a side.
        return team_name

    def get_team_last_fixtures(self, team_id, last_n=10, **kwargs):
        return [
            {"id": f"m{i}", "date": d, "home_team": "Daniil Medvedev", "away_team": "X"}
            for i, d in enumerate(self._dates)
        ]

    def get_fixture_stats(self, fixture_id):
        return type("S", (), {"stats": {"aces": 5, "opponent_aces": 3,
                                        "double_faults": 2, "opponent_double_faults": 1,
                                        "total_games": 22, "total_sets": 3,
                                        "score": "6-4 6-3"}})()


def test_stale_sample_is_named_not_silent(monkeypatch):
    """A sample discarded as too old must say so, not vanish.

    Before this, the age guard dropped every row and the outcome carried no
    observations *and* no data_gap -- indistinguishable in the artifact from a
    provider that was never asked. Medvedev's dossier read PARTIAL with no
    stated cause.
    """
    client = _StaleCacheClient(["2018-08-27", "2018-10-29", "2017-01-16"])
    monkeypatch.setattr(providers, "_provider_client", lambda *a, **k: client)

    outcome = providers._fetch_l10_generic(
        "tennis-abstract", "Daniil Medvedev", RateLimiter(), competition="ATP US Open"
    )

    assert outcome.metrics == {}
    assert len(outcome.data_gaps) == 1
    gap = outcome.data_gaps[0]
    assert "stale, not missing" in gap
    assert "2018-10-29" in gap  # the newest row, so the reader can judge it
    assert "Daniil Medvedev" in gap


def test_fresh_sample_adds_no_spurious_gap(monkeypatch):
    """The new gap must not fire on a provider that actually delivered."""
    recent = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    client = _StaleCacheClient([recent])
    monkeypatch.setattr(providers, "_provider_client", lambda *a, **k: client)

    outcome = providers._fetch_l10_generic(
        "tennis-abstract", "Daniil Medvedev", RateLimiter(), competition="ATP US Open"
    )

    assert outcome.metrics
    assert not [g for g in outcome.data_gaps if "stale, not missing" in g]


# --- readiness is measured on the sample ANALYZE will actually read ----------
#
# Until 2026-09-04 ENRICH counted every observation a provider returned while
# ANALYZE put each per-team bucket through ``scope_values`` and discarded the
# pre-season friendlies and the previous season's matches. READY was therefore
# a promise about a sample that never reached the sheet, and it was wrong in
# one direction only. On the 2026-09-04 slate ``PRE_SEASON_FRIENDLY`` fired 532
# times on ``corners_total`` across the 22 READY football dossiers, and the
# honest count moved 10 of them to PARTIAL.

_FRIENDLY_COMPETITION = "79"  # bzzoiro club friendlies, per config/observation_scope.json


def _football_obs(canonical_name, per_side):
    """A football metric where each side's matches carry a competition/season.

    ``per_side`` is ``{"a": [(competition_id, season_id, count)], ...}``, which
    is the shape the scope filter actually discriminates on -- a match_id alone
    cannot be pinned out or aged out.
    """
    def bucket(spec):
        out = []
        for competition_id, season_id, count in spec:
            for i in range(count):
                out.append(ProviderValue(
                    provider="bzzoiro",
                    match_id=f"{canonical_name}-{competition_id}-{season_id}-{i}",
                    match_date=f"2026-08-{10 + i:02d}",
                    opponent="X", value=1.0,
                    observed_at="2026-09-04T00:00:00+00:00",
                    competition_id=competition_id, season_id=season_id,
                ))
        return out
    return MetricObservation(
        canonical_name=canonical_name,
        team_a_l10=bucket(per_side.get("a", ())),
        team_b_l10=bucket(per_side.get("b", ())),
    )


def _football_metrics(per_side):
    return {
        name: _football_obs(name, per_side)
        for name in ("corners_total", "cards_total", "shots_total")
    }


def test_friendlies_no_longer_count_toward_the_readiness_floor():
    """Stade Lavallois - Red Star, 2026-09-04: 6 matches a side, 4 admissible.

    Ligue 2 had played four rounds. bzzoiro publishes corners and cards for
    July friendlies (US Granville, Stade Malherbe Caen) but no shots, so the
    raw counts read corners 6/6 and shots 4/6 and the fixture was READY on
    corners it would never be priced off.
    """
    metrics = _football_metrics({
        "a": [("182", "1600", 4), (_FRIENDLY_COMPETITION, "1552", 2)],
        "b": [("182", "1600", 4), (_FRIENDLY_COMPETITION, "1552", 2)],
    })
    assert _compute_readiness("football", metrics) == "PARTIAL"


def test_the_previous_season_does_not_count_toward_the_floor_either():
    """Al-Shabab - Al-Hilal: four current matches and two from 25/26."""
    metrics = _football_metrics({
        "a": [("307", "1601", 4), ("307", "1499", 2)],
        "b": [("307", "1601", 4), ("307", "1499", 2)],
    })
    assert _compute_readiness("football", metrics) == "PARTIAL"


def test_a_full_league_sample_is_still_ready():
    """The floor itself did not move: five admissible matches a side pass.

    Without this the change is indistinguishable from having broken READY, and
    the drop from 22 to 12 on 2026-09-04 would not be evidence of anything.
    """
    metrics = _football_metrics({
        "a": [("182", "1600", 5), (_FRIENDLY_COMPETITION, "1552", 3)],
        "b": [("182", "1600", 5), ("182", "1499", 3)],
    })
    assert _compute_readiness("football", metrics) == "READY"


def test_scoping_the_sample_cannot_manufacture_blocked():
    """A dossier whose every match is a friendly is PARTIAL, never BLOCKED.

    BLOCKED is the one verdict ANALYZE acts on destructively -- it drops the
    dossier whole -- so it has to keep meaning "no provider returned any data"
    and not "the data does not survive the scope filter". Those observations
    are still worth the analyst's eyes, and the run has already paid for them.
    """
    metrics = _football_metrics({
        "a": [(_FRIENDLY_COMPETITION, "1552", 8)],
        "b": [(_FRIENDLY_COMPETITION, "1552", 8)],
    })
    assert _compute_readiness("football", metrics) == "PARTIAL"


def test_a_corroborator_seen_only_in_friendlies_is_not_a_second_opinion():
    """The provider set is counted after scoping, not before.

    Tennis's ``total_games`` branch asks for two providers rather than for
    depth. If the scope filter applied to the depth counts but not to the
    roster, the same overstatement would simply move from one branch to the
    other: a provider whose only rows were friendlies would still certify a
    fixture it contributed nothing readable to.
    """
    def pv(provider, match_id, competition_id):
        return ProviderValue(
            provider=provider, match_id=match_id, match_date="2026-07-20",
            opponent="X", value=1.0, observed_at="2026-09-04T00:00:00+00:00",
            competition_id=competition_id, season_id="1552",
        )
    metrics = _tennis_metrics({
        "total_games": ("tennis-abstract",),
        "aces_total": ("tennis-abstract",),
        "double_faults_total": ("tennis-abstract",),
    })
    # espn-tennis is a genuine second opinion on total_games, so on the raw
    # roster this metric would be complete -- but every row it brought is a
    # pinned-out competition.
    metrics["total_games"] = MetricObservation(
        canonical_name="total_games",
        team_a_l10=[
            *metrics["total_games"].team_a_l10,
            *[pv("bzzoiro", f"friendly-a-{i}", _FRIENDLY_COMPETITION) for i in range(6)],
        ],
        team_b_l10=[
            *metrics["total_games"].team_b_l10,
            *[pv("bzzoiro", f"friendly-b-{i}", _FRIENDLY_COMPETITION) for i in range(6)],
        ],
    )
    assert _compute_readiness("tennis", metrics) == "PARTIAL"
