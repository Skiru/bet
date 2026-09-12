"""Tests for bet.simple_stats.discover: dedup merging and identity classification."""
from datetime import datetime, timezone

import pytest

from bet.discovery.dedup import DeduplicationEngine
from bet.discovery.models import DiscoveredEvent, MergedFixture, SourceRef

from bet.simple_stats.discover import (
    DISCOVERY_SOURCES_BY_SPORT,
    _canonicalize_competition_names,
    _competition_canonical_map,
    _dedup_by_event_identity,
    _detect_ambiguous,
    _event_id,
    _fetch_source_events,
    _normalize_name,
    _to_event_record,
    reset_competition_canonical_cache,
)

_KICKOFF = datetime(2026, 6, 23, 15, 0, tzinfo=timezone.utc)


def _event(source, external_id, sport="football", home="Norway", away="Senegal", kickoff=_KICKOFF):
    return DiscoveredEvent(
        source=source,
        external_id=external_id,
        sport=sport,
        competition="World Cup 2026",
        home_team=home,
        away_team=away,
        kickoff=kickoff,
        status="scheduled",
    )


class _FakeAdapter:
    def __init__(self, name, supported_sports):
        self.name = name
        self.supported_sports = supported_sports
        self.calls: list[str] = []

    def fetch_events(self, date, sport):
        self.calls.append(sport)
        return [_event(self.name, f"{self.name}-{sport}", sport=sport)]


def test_football_discovery_sources():
    """Football queries all rostered sources in DISCOVERY_SOURCES_BY_SPORT:
    bzzoiro and superbet."""
    highlightly = _FakeAdapter("highlightly", ["football"])
    bzzoiro = _FakeAdapter("bzzoiro", ["football"])
    superbet = _FakeAdapter("superbet", ["football"])

    assert _fetch_source_events(highlightly, "2026-09-04", ["football"]) == []
    assert highlightly.calls == []

    events = _fetch_source_events(bzzoiro, "2026-09-04", ["football"])
    assert len(events) == 1
    assert bzzoiro.calls == ["football"]

    assert len(_fetch_source_events(superbet, "2026-09-04", ["football"])) == 1
    assert superbet.calls == ["football"]


def test_tennis_discovery_sources():
    """Tennis queries all rostered sources in DISCOVERY_SOURCES_BY_SPORT:
    odds-api, superbet-tennis-challenger, and superbet."""
    odds_api = _FakeAdapter("odds-api", ["tennis"])
    superbet_challenger = _FakeAdapter("superbet-tennis-challenger", ["tennis"])
    superbet = _FakeAdapter("superbet", ["tennis"])
    highlightly = _FakeAdapter("highlightly", ["tennis"])

    events = _fetch_source_events(odds_api, "2026-09-04", ["tennis"])
    assert len(events) == 1
    assert odds_api.calls == ["tennis"]

    events = _fetch_source_events(superbet_challenger, "2026-09-04", ["tennis"])
    assert len(events) == 1
    assert superbet_challenger.calls == ["tennis"]

    assert len(_fetch_source_events(superbet, "2026-09-04", ["tennis"])) == 1
    assert superbet.calls == ["tennis"]

    assert _fetch_source_events(highlightly, "2026-09-04", ["tennis"]) == []
    assert highlightly.calls == []


def test_discovery_sources_by_sport_uses_get_not_indexing():
    """--sports is free text with no argparse choices, and OddsAPIEventsAdapter
    declares basketball and hockey too -- a sport with no entry in the roster
    must fall back to "nothing", not raise a KeyError."""
    basketball = _FakeAdapter("odds-api", ["basketball"])
    assert "basketball" not in DISCOVERY_SOURCES_BY_SPORT
    assert _fetch_source_events(basketball, "2026-09-04", ["basketball"]) == []


def test_merges_two_sources_into_one_event():
    events_by_source = {
        "odds-api": [_event("odds-api", "abc123")],
        "highlightly": [_event("highlightly", "456")],
    }

    merged = DeduplicationEngine().merge(events_by_source)
    assert len(merged) == 1
    assert merged[0].source_count == 2

    record = _to_event_record(merged[0])
    assert record.status == "ACTIVE"
    assert record.source_ids == {"odds-api": "abc123", "highlightly": "456"}
    assert record.identity_confidence in ("CONFIRMED", "FUZZY_MATCHED")
    assert record.home_team == "Norway"
    assert record.away_team == "Senegal"


def test_ambiguous_identity_blocked():
    events_by_source = {
        "odds-api": [_event("odds-api", "1", sport="football")],
        "highlightly": [_event("highlightly", "2", sport="tennis")],
    }

    blocked_records, filtered = _detect_ambiguous(events_by_source)

    assert len(blocked_records) == 1
    record = blocked_records[0]
    assert record.status == "BLOCKED_IDENTITY"
    assert record.identity_confidence == "AMBIGUOUS"
    assert "sport" in record.terminal_reason
    assert record.source_ids == {"odds-api": "1", "highlightly": "2"}

    # the ambiguous raw events are pulled out of the pool before dedup
    assert filtered["odds-api"] == []
    assert filtered["highlightly"] == []


def test_non_conflicting_events_are_not_ambiguous():
    events_by_source = {
        "odds-api": [_event("odds-api", "1")],
        "highlightly": [_event("highlightly", "2")],
    }

    blocked_records, filtered = _detect_ambiguous(events_by_source)

    assert blocked_records == []
    assert filtered["odds-api"] == events_by_source["odds-api"]
    assert filtered["highlightly"] == events_by_source["highlightly"]


def test_provider_team_ids_are_carried_from_source_raw_data():
    """Highlightly's /statistics endpoint hard-fails without its own native
    team ids, so discovery must carry them onto the EventRecord; without this
    ENRICH cannot call that provider at all."""
    hl = _event("highlightly", "1336361826")
    hl.raw_data = {
        "provider_match_id": "1336361826",
        "home_team_id": "3662637",
        "away_team_id": "16819097",
    }
    events_by_source = {"odds-api": [_event("odds-api", "abc123")], "highlightly": [hl]}
    merged = DeduplicationEngine().merge(events_by_source)
    record = _to_event_record(merged[0])

    assert record.provider_team_ids["highlightly"] == {"home": "3662637", "away": "16819097"}


def test_provider_team_ids_omitted_when_ids_are_missing_or_identical():
    """A source with no ids, or the same id on both sides, must not produce a
    provider_team_ids entry -- Highlightly rejects identical ids outright."""
    hl = _event("highlightly", "1336361826")
    hl.raw_data = {"home_team_id": "999", "away_team_id": "999"}
    merged = DeduplicationEngine().merge({"highlightly": [hl]})
    assert _to_event_record(merged[0]).provider_team_ids == {}


def test_odds_api_events_adapter_reads_the_free_events_endpoint():
    """The paid /odds endpoint answers 401 OUT_OF_USAGE_CREDITS once the
    monthly quota is spent, which zeroed out discovery; /events is free and
    carries every field EVENT_LIST_V1 needs."""
    import bet.simple_stats.discover as discover_module

    captured = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return [
                {
                    "id": "evt-1",
                    "sport_title": "EPL",
                    "commence_time": "2026-06-23T15:00:00Z",
                    "home_team": "Norway",
                    "away_team": "Senegal",
                },
                {  # different date -- must be filtered out
                    "id": "evt-2",
                    "sport_title": "EPL",
                    "commence_time": "2026-06-24T15:00:00Z",
                    "home_team": "A",
                    "away_team": "B",
                },
            ]

    def _fake_get(url, params=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["params"] = params
        return _Resp()

    original = discover_module.requests.get
    discover_module.requests.get = _fake_get
    try:
        adapter = discover_module.OddsAPIEventsAdapter(api_key="k")
        events = adapter._fetch_for_key("soccer_epl", "football", "2026-06-23")
    finally:
        discover_module.requests.get = original

    assert captured["url"].endswith("/sports/soccer_epl/events")
    assert "markets" not in captured["params"]  # no odds requested, no credits spent
    assert [e.external_id for e in events] == ["evt-1"]


def _bzzoiro_events_payload():
    return {
        "count": 2,
        "results": [
            {
                "id": 587706,
                "league_id": 7,
                "season_id": 1,
                "home_team_id": 100,
                "away_team_id": 134,
                "home_team": "Olympique Lyonnais",
                "away_team": "Fenerbahçe",
                "home_score": None,
                "away_score": None,
                "event_date": "2026-08-26T19:00:00+00:00",
                "status": "notstarted",
            },
            {  # unusable: both sides are the same team id
                "id": 999,
                "league_id": 7,
                "season_id": 1,
                "home_team_id": 5,
                "away_team_id": 5,
                "home_team": "X",
                "away_team": "X",
                "event_date": "2026-08-26T19:00:00+00:00",
                "status": "notstarted",
            },
        ],
    }


def _stub_bzzoiro_adapter(monkeypatch, events_payload, leagues_payload):
    """A BzzoiroDiscoveryAdapter whose client replays two canned responses."""
    from bet.api_clients.rate_limiter import RateLimiter
    from bet.integration.source_result import SourceOperationResult, SourceResultStatus

    from bet.simple_stats.discover import BzzoiroDiscoveryAdapter

    adapter = BzzoiroDiscoveryAdapter(RateLimiter())
    adapter._client.api_key = "test-key"

    def _fake(*, endpoint, params, operation, source_event_id=None):
        payload = {"/events/": events_payload, "/leagues/": leagues_payload}.get(endpoint)
        if payload is None:
            return SourceOperationResult(
                status=SourceResultStatus.NOT_FOUND, provider="bzzoiro", operation=operation
            )
        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=payload,
            provider="bzzoiro",
            operation=operation,
            http_status=200,
        )

    monkeypatch.setattr(adapter._client, "_request_with_evidence", _fake)
    return adapter


def test_bzzoiro_adapter_names_the_competition_from_the_league_catalogue(monkeypatch):
    """``/events/`` gives only ``league_id``, and EventRecord.competition feeds
    the event id, the dedup key and every downstream competition lookup. One
    cached catalogue call resolves all of a day's leagues."""
    leagues = {
        "count": 1,
        "results": [{"id": 7, "name": "Champions League", "country": "Europe"}],
    }
    adapter = _stub_bzzoiro_adapter(monkeypatch, _bzzoiro_events_payload(), leagues)

    events = adapter._fetch_events_impl("2026-08-26", "football")
    assert len(events) == 1  # the same-team-id row is rejected
    assert events[0].competition == "Champions League"
    assert events[0].raw_data["home_team_id"] == "100"
    assert events[0].raw_data["away_team_id"] == "134"

    # Second call must not re-fetch the catalogue.
    assert adapter._league_name("7") == "Champions League"


def test_bzzoiro_competition_stays_unique_when_the_catalogue_is_unavailable(monkeypatch):
    """An empty competition name would collapse every fixture of the day into
    one competition -- and the dedup key and event id are built from it."""
    adapter = _stub_bzzoiro_adapter(monkeypatch, _bzzoiro_events_payload(), None)
    events = adapter._fetch_events_impl("2026-08-26", "football")
    assert events[0].competition == "bzzoiro-league-7"
    assert adapter.last_errors


def test_bzzoiro_qualifies_a_generic_league_name_with_its_country(monkeypatch):
    """bzzoiro's catalogue calls the French top flight plain "Ligue 1", and the
    ESPN table refuses that key on purpose (Algeria and Tunisia play one too).
    Football discovery is bzzoiro-only since 2026-09-04, so unqualified here
    means unresolvable everywhere: measured on that day's live run, 14 of 45
    fixtures -- PSG-Monaco and Genoa-Como among them -- lost espn-football,
    which is where a goal comes from after step 5 of the consolidation."""
    from bet.api_clients.espn import get_espn_league_for_competition

    leagues = {"count": 1, "results": [{"id": 7, "name": "Ligue 1", "country": "France"}]}
    adapter = _stub_bzzoiro_adapter(monkeypatch, _bzzoiro_events_payload(), leagues)

    events = adapter._fetch_events_impl("2026-08-26", "football")
    assert events[0].competition == "France Ligue 1"
    assert get_espn_league_for_competition(events[0].competition) == "fra.1"


def test_bzzoiro_leaves_a_specific_league_name_alone(monkeypatch):
    """The qualification is a closed list of generic names, not a blanket
    prefix: the pin maps hold "Eredivisie" and "LaLiga" bare, so prefixing
    every name would break resolutions that work today."""
    leagues = {"count": 1, "results": [{"id": 7, "name": "Eredivisie", "country": "Netherlands"}]}
    adapter = _stub_bzzoiro_adapter(monkeypatch, _bzzoiro_events_payload(), leagues)

    events = adapter._fetch_events_impl("2026-08-26", "football")
    assert events[0].competition == "Eredivisie"


def test_bzzoiro_a_league_with_no_country_keeps_its_bare_name(monkeypatch):
    """A catalogue row missing ``country`` must not produce " Superliga"."""
    leagues = {"count": 1, "results": [{"id": 7, "name": "Superliga", "country": None}]}
    adapter = _stub_bzzoiro_adapter(monkeypatch, _bzzoiro_events_payload(), leagues)

    events = adapter._fetch_events_impl("2026-08-26", "football")
    assert events[0].competition == "Superliga"


def test_bzzoiro_does_not_repeat_a_country_already_in_the_name(monkeypatch):
    leagues = {
        "count": 1,
        "results": [{"id": 7, "name": "Denmark Superliga", "country": "Denmark"}],
    }
    adapter = _stub_bzzoiro_adapter(monkeypatch, _bzzoiro_events_payload(), leagues)

    events = adapter._fetch_events_impl("2026-08-26", "football")
    assert events[0].competition == "Denmark Superliga"


def test_the_generic_name_qualification_is_one_rule_for_every_adapter(monkeypatch):
    """Highlightly and bzzoiro must not drift: the pin maps are keyed on the
    name and cannot tell which provider produced it."""
    from bet.simple_stats.discover import (
        _highlightly_competition_name,
        _qualified_competition_name,
    )

    for name, country in (("Serie A", "Italy"), ("Pro League", "Belgium"), ("Cup", "Poland")):
        assert _highlightly_competition_name(
            {"name": name}, {"name": country}
        ) == _qualified_competition_name(name, country)


def test_bzzoiro_native_ids_reach_the_event_record(monkeypatch):
    """Same generic lift as Highlightly's, with no provider-specific code in
    ``_to_event_record``: without these ids ENRICH builds no bzzoiro task."""
    leagues = {"count": 1, "results": [{"id": 7, "name": "Champions League", "country": "Europe"}]}
    adapter = _stub_bzzoiro_adapter(monkeypatch, _bzzoiro_events_payload(), leagues)
    discovered = adapter._fetch_events_impl("2026-08-26", "football")

    merged = DeduplicationEngine().merge({"bzzoiro": discovered})
    record = _to_event_record(merged[0])
    assert record.provider_team_ids["bzzoiro"] == {"home": "100", "away": "134"}
    assert record.source_ids["bzzoiro"] == "587706"


# docs/PLAN_BOGATE_STATYSTYKI.md Faza 6: competition-name canonicalization.


@pytest.fixture(autouse=True)
def _clear_competition_canonical_cache():
    reset_competition_canonical_cache()
    yield
    reset_competition_canonical_cache()


def test_competition_canonical_map_is_exact_pin_only():
    """The real config file: known duplicate spellings are pinned, and bare
    ambiguous names (which the ESPN table also refuses to pin, for the same
    reason) are NOT silently folded into a guessed country."""
    canonical = _competition_canonical_map()
    assert canonical["EPL"] == "Premier League"
    assert canonical["Veikkausliiga - Finland"] == "Veikkausliiga"
    assert canonical["Danish Superliga"] == "Denmark Superliga"
    assert canonical["Allsvenskan - Sweden"] == "Allsvenskan"
    # Romania and Denmark both call their top flight "Superliga" -- folding
    # the bare name to either country would repeat the 2026-08-28 incident.
    assert "Superliga" not in canonical


def test_canonicalize_competition_names_unifies_a_known_duplicate_pair():
    """Two providers naming the same real match "EPL" and "Premier League"
    must produce the same event_id once canonicalized, or the merge/ESPN
    layers downstream see two fixtures instead of one."""
    epl = _event("odds-api", "1", home="Aston Villa", away="Arsenal")
    epl.competition = "EPL"
    prem = _event("highlightly", "2", home="Aston Villa", away="Arsenal")
    prem.competition = "Premier League"
    events_by_source = {"odds-api": [epl], "highlightly": [prem]}

    _canonicalize_competition_names(events_by_source)

    assert epl.competition == "Premier League"
    assert prem.competition == "Premier League"
    participants = "aston villa|arsenal"
    epl_id = _event_id(
        "football", epl.competition, participants, epl.kickoff.isoformat()
    )
    prem_id = _event_id(
        "football", prem.competition, participants, prem.kickoff.isoformat()
    )
    assert epl_id == prem_id


def test_canonicalize_competition_names_leaves_unknown_names_untouched():
    ev = _event("odds-api", "1")
    ev.competition = "Some League Nobody Has Pinned Yet"
    events_by_source = {"odds-api": [ev]}

    _canonicalize_competition_names(events_by_source)

    assert ev.competition == "Some League Nobody Has Pinned Yet"


def test_canonicalize_competition_names_never_guesses_bare_superliga():
    """Regression guard for the 2026-08-28 incident: bare "Superliga" must
    reach ESPN resolution unresolved, not silently become Denmark's or
    Romania's."""
    ev = _event("odds-api", "1")
    ev.competition = "Superliga"
    events_by_source = {"odds-api": [ev]}

    _canonicalize_competition_names(events_by_source)

    assert ev.competition == "Superliga"


# Stakes context (round_name/group_name/previous_leg_event_id) carried
# through from bzzoiro's raw fixture row, at zero extra request cost.


def test_fixture_context_survives_a_missing_referee_id():
    """A fixture context field earns the whole block by source, not by
    referee_id being set: a fixture whose referee is not yet assigned must
    not lose is_local_derby/weather/stakes context along with it. Verified
    live 2026-08-31: Sutton United - Wealdstone had referee_id=None and
    is_local_derby=True at the same time."""
    ev = _event("bzzoiro", "1")
    ev.raw_data = {
        "referee_id": None,
        "is_local_derby": True,
        "round_name": "Final",
        "group_name": None,
        "previous_leg_event_id": "999",
    }
    merged = DeduplicationEngine().merge({"bzzoiro": [ev]})
    record = _to_event_record(merged[0])

    assert record.fixture_context is not None
    assert record.fixture_context.referee_id is None
    assert record.fixture_context.is_local_derby is True
    assert record.fixture_context.round_name == "Final"
    assert record.fixture_context.previous_leg_event_id == "999"


def test_fixture_context_is_absent_for_a_non_bzzoiro_source():
    ev = _event("highlightly", "1")
    ev.raw_data = {"round_name": "Final"}
    merged = DeduplicationEngine().merge({"highlightly": [ev]})
    record = _to_event_record(merged[0])

    assert record.fixture_context is None


# --- the country highlightly sends and the adapter used to drop -------------


def test_a_bare_cup_is_qualified_by_the_country_beside_it():
    """41 fixtures on 2026-09-02 arrived with the competition name "Cup" --
    PAOK-OFI, J-League ties and the rest, all in one bucket. Highlightly puts
    ``country`` beside ``league`` on the fixture row, not inside it, and the
    adapter read only ``league.name``. A name that cannot tell a Greek cup tie
    from a Japanese one can be pinned to nothing and scoped by nothing."""
    from bet.simple_stats.discover import _highlightly_competition_name as name_of

    assert name_of({"name": "Cup"}, {"name": "Greece"}) == "Greece Cup"
    assert name_of({"name": "Superliga"}, {"name": "Denmark"}) == "Denmark Superliga"


def test_a_name_that_already_identifies_a_competition_is_left_alone():
    """The reason this is a closed list and not a rule. Prefixing every name
    would rewrite "LaLiga" to "Spain LaLiga", a key the ESPN and canonical
    tables do not hold -- breaking resolutions that work to fix ones that do
    not."""
    from bet.simple_stats.discover import _highlightly_competition_name as name_of

    assert name_of({"name": "LaLiga"}, {"name": "Spain"}) == "LaLiga"
    # "Serie A" left the left-alone set on 2026-09-02: bare on the wire it was
    # Atletico-MG - Vitoria (Brazil), so the name alone identifies nothing and
    # the Italian rows must carry their country to resolve.
    assert name_of({"name": "Serie A"}, {"name": "Italy"}) == "Italy Serie A"
    # Already carries its country; prefixing again would say it twice.
    assert name_of({"name": "Danish Cup"}, {"name": "Denmark"}) == "Danish Cup"


def test_no_country_means_the_bare_name_survives_unchanged():
    """Inventing a country is worse than a vague name."""
    from bet.simple_stats.discover import _highlightly_competition_name as name_of

    assert name_of({"name": "Cup"}, {}) == "Cup"
    assert name_of({"name": "Cup"}, {"name": ""}) == "Cup"
    assert name_of({}, {"name": "Greece"}) == ""


def test_qualifying_a_generic_name_can_only_help_the_espn_map():
    """Each generic name either resolves the same as before, or better."""
    from bet.api_clients.espn import get_espn_league_for_competition as resolve
    from bet.simple_stats.discover import _highlightly_competition_name as name_of

    for bare, country in (
        ("Premier League", "England"),
        ("Championship", "England"),
        ("Premiership", "Scotland"),
        ("Superliga", "Denmark"),
        ("Super League", "Switzerland"),
    ):
        before = resolve(bare)
        after = resolve(name_of({"name": bare}, {"name": country}))
        assert after == before or (before is None and after is not None), (
            f"{bare!r} + {country!r}: {before!r} -> {after!r}"
        )


# --- SuperbetTennisChallengerDiscoveryAdapter --------------------------------
#
# ATP Challenger singles: odds-api has no key for this tier at all (verified
# live 2026-09-08), and ESPN was tried and ruled out empirically the same day
# (its tennis scoreboard carries only Slams and top-line tour events under
# league="atp"/"wta"; every other league code 400s). Superbet's own
# /events/by-date already lists the pairing directly.


def _superbet_row(
    *,
    event_id=14851993,
    sport_id=2,
    category_id=205,
    tournament_id=80804,
    match_name="Kimmer Coppejans·Pablo Llamas Ruiz",
    match_date="2026-09-08 09:00:00",
    utc_date="2026-09-08T09:00:00Z",
    market_count=60,
    betradar_id="74374920",
):
    return {
        "eventId": event_id,
        "sportId": sport_id,
        "categoryId": category_id,
        "tournamentId": tournament_id,
        "matchName": match_name,
        "matchDate": match_date,
        "utcDate": utc_date,
        "marketCount": market_count,
        "betradarId": betradar_id,
        "metadata": {"status": "NOT_STARTED"},
    }


def _stub_superbet_adapter(monkeypatch, rows):
    from bet.simple_stats.discover import SuperbetTennisChallengerDiscoveryAdapter

    adapter = SuperbetTennisChallengerDiscoveryAdapter()
    monkeypatch.setattr(adapter._client, "events_by_date", lambda *a, **kw: rows)
    return adapter


def test_superbet_challenger_adapter_keeps_only_the_challenger_category(monkeypatch):
    """categoryId=205 is Superbet's own field, empirically verified against
    two live Challenger draws on 2026-09-08 -- not documented, so this test
    is the guard against silently widening (or narrowing) which tier gets
    discovered."""
    rows = [
        _superbet_row(event_id=1, category_id=205, match_name="A·B"),  # ATP Challenger: kept
        _superbet_row(event_id=2, category_id=3, match_name="C·D"),  # ATP main tour
        _superbet_row(event_id=3, category_id=2, match_name="E·F"),  # WTA main tour
        _superbet_row(event_id=4, category_id=1877, match_name="G·H"),  # ITF
    ]
    adapter = _stub_superbet_adapter(monkeypatch, rows)

    events = adapter._fetch_events_impl("2026-09-08", "tennis")

    assert [e.external_id for e in events] == ["1"]
    assert events[0].competition == "ATP Challenger"
    assert events[0].home_team == "A"
    assert events[0].away_team == "B"


def test_superbet_challenger_adapter_skips_doubles(monkeypatch):
    """This tier's doubles ladder is a single line with no per-player
    breakdown -- nothing this pipeline's tennis samples could key on -- so
    doubles are dropped rather than discovered and later found useless."""
    rows = [
        _superbet_row(event_id=1, match_name="Kimmer Coppejans·Pablo Llamas Ruiz"),
        _superbet_row(
            event_id=2,
            match_name="B.Carpico/N.S.Filin·R.Ram/J.Salisbury",
        ),
    ]
    adapter = _stub_superbet_adapter(monkeypatch, rows)

    events = adapter._fetch_events_impl("2026-09-08", "tennis")

    assert [e.external_id for e in events] == ["1"]


def test_superbet_challenger_adapter_uses_utc_date_not_local_match_date(monkeypatch):
    """``matchDate`` is unlabeled local time (the same trap
    pipeline-timestamps-are-local-not-utc already warns about elsewhere in
    this pipeline); ``utcDate`` carries an explicit ``Z`` and is what kickoff
    must be built from."""
    rows = [
        _superbet_row(
            match_date="2026-09-08 23:30:00",  # would read as a different UTC day if used
            utc_date="2026-09-08T21:30:00Z",
        )
    ]
    adapter = _stub_superbet_adapter(monkeypatch, rows)

    events = adapter._fetch_events_impl("2026-09-08", "tennis")

    assert len(events) == 1
    assert events[0].kickoff.isoformat() == "2026-09-08T21:30:00+00:00"


def test_superbet_challenger_adapter_filters_to_the_requested_date(monkeypatch):
    rows = [
        _superbet_row(event_id=1, utc_date="2026-09-08T21:30:00Z"),
        _superbet_row(event_id=2, utc_date="2026-09-09T02:00:00Z"),
    ]
    adapter = _stub_superbet_adapter(monkeypatch, rows)

    events = adapter._fetch_events_impl("2026-09-08", "tennis")

    assert [e.external_id for e in events] == ["1"]


def test_superbet_challenger_adapter_ignores_other_sports(monkeypatch):
    rows = [_superbet_row(sport_id=5, category_id=205)]  # football's sportId, same categoryId
    adapter = _stub_superbet_adapter(monkeypatch, rows)

    assert adapter._fetch_events_impl("2026-09-08", "tennis") == []


def test_superbet_challenger_adapter_drops_a_row_with_no_away_side(monkeypatch):
    """A walkover-shaped or malformed matchName ("Coppejans·") must not
    become a one-sided fixture -- split_match_name falls back to a
    single-sided split rather than raising, so the adapter has to guard it."""
    rows = [_superbet_row(match_name="Kimmer Coppejans·")]
    adapter = _stub_superbet_adapter(monkeypatch, rows)

    assert adapter._fetch_events_impl("2026-09-08", "tennis") == []


def test_superbet_challenger_adapter_drops_a_row_with_no_event_id(monkeypatch):
    rows = [_superbet_row(event_id=None)]
    adapter = _stub_superbet_adapter(monkeypatch, rows)

    assert adapter._fetch_events_impl("2026-09-08", "tennis") == []


def test_superbet_challenger_adapter_drops_a_row_with_an_unparseable_utc_date(monkeypatch):
    rows = [_superbet_row(utc_date="not-a-date")]
    adapter = _stub_superbet_adapter(monkeypatch, rows)

    assert adapter._fetch_events_impl("2026-09-08", "tennis") == []


def test_superbet_challenger_adapter_carries_superbets_own_status_through(monkeypatch):
    """Superbet's own metadata.status (e.g. a match already interrupted or
    postponed at discovery time) must not be flattened to a fixed
    "scheduled", unlike odds-api's /events endpoint, which genuinely carries
    no status field to lose."""
    rows = [_superbet_row(event_id=1)]
    rows[0]["metadata"] = {"status": "POSTPONED"}
    adapter = _stub_superbet_adapter(monkeypatch, rows)

    events = adapter._fetch_events_impl("2026-09-08", "tennis")

    assert events[0].status == "POSTPONED"


def test_superbet_challenger_adapter_maps_unknown_status_to_scheduled(monkeypatch):
    rows = [_superbet_row(event_id=1)]
    rows[0]["metadata"] = {"status": "UNKNOWN"}
    adapter = _stub_superbet_adapter(monkeypatch, rows)

    events = adapter._fetch_events_impl("2026-09-08", "tennis")

    assert events[0].status == "scheduled"


def test_superbet_challenger_adapter_records_error_on_client_failure(monkeypatch):
    from bet.api_clients.superbet import SuperbetError
    from bet.simple_stats.discover import SuperbetTennisChallengerDiscoveryAdapter

    adapter = SuperbetTennisChallengerDiscoveryAdapter()

    def _raise(*a, **kw):
        raise SuperbetError("Superbet offer returned HTTP 500 for /events/by-date")

    monkeypatch.setattr(adapter._client, "events_by_date", _raise)

    events = adapter._fetch_events_impl("2026-09-08", "tennis")

    assert events == []
    assert adapter.last_errors  # the caller can tell this source went dark


def test_superbet_challenger_adapter_is_registered_disjoint_from_odds_api():
    """No categoryId this adapter accepts is one odds-api's main-tour
    discovery ever produces, so the two sources never need to merge or
    disambiguate a Challenger fixture against a main-tour one."""
    from bet.simple_stats.discover import DISCOVERY_SOURCES_BY_SPORT

    assert "odds-api" in DISCOVERY_SOURCES_BY_SPORT["tennis"]
    assert "superbet-tennis-challenger" in DISCOVERY_SOURCES_BY_SPORT["tennis"]
    assert "superbet" in DISCOVERY_SOURCES_BY_SPORT["tennis"]


def test_postponed_fixture_blocked_at_discovery():
    """A postponed fixture must be marked BLOCKED_STATUS so it cannot be enriched
    or placed on coupons."""
    events_by_source = {
        "bzzoiro": [
            DiscoveredEvent(
                source="bzzoiro",
                external_id="postponed_1",
                sport="football",
                competition="Saudi Pro League",
                home_team="Neom SC",
                away_team="Al-Fateh",
                kickoff=_KICKOFF,
                status="postponed",
            )
        ]
    }
    merged = DeduplicationEngine().merge(events_by_source)
    assert len(merged) == 1
    record = _to_event_record(merged[0])

    assert record.status == "BLOCKED_STATUS"
    assert record.terminal_reason == "fixture status is 'postponed'"


def test_cancelled_fixture_blocked_at_discovery():
    """A cancelled fixture must be marked BLOCKED_STATUS."""
    events_by_source = {
        "bzzoiro": [
            DiscoveredEvent(
                source="bzzoiro",
                external_id="cancelled_1",
                sport="football",
                competition="League One",
                home_team="Stevenage",
                away_team="Luton Town",
                kickoff=_KICKOFF,
                status="cancelled",
            )
        ]
    }
    merged = DeduplicationEngine().merge(events_by_source)
    assert len(merged) == 1
    record = _to_event_record(merged[0])

    assert record.status == "BLOCKED_STATUS"
    assert record.terminal_reason == "fixture status is 'cancelled'"


def test_source_raw_status_postponed_blocks_fixture():
    """Even if MergedFixture.status is 'scheduled', if any source flagged it as
    postponed or cancelled, it must be marked BLOCKED_STATUS."""
    fixture = MergedFixture(
        sport="football",
        competition="Saudi Pro League",
        home_team="Al-Riyadh",
        away_team="Al-Kholood",
        kickoff=_KICKOFF,
        status="scheduled",
        sources=[
            SourceRef(
                source="bzzoiro",
                external_id="222826",
                raw_status="postponed",
            )
        ],
        primary_source="bzzoiro",
        primary_external_id="222826",
    )
    record = _to_event_record(fixture)

    assert record.status == "BLOCKED_STATUS"
    assert record.terminal_reason == "fixture marked 'postponed' by bzzoiro"




def test_same_source_republished_under_two_ids_collapses_to_one_event():
    """Regression for 2026-09-12: verbatim replay of the 4 real tennis pairs
    pulled from that day's runs/2026-09-12/2026-09-12_event_list.json.
    Superbet listed each match twice under two different fixture ids, same
    names/competition/kickoff, no other source involved at all.
    _can_attach_source correctly refuses to let the second id overwrite the
    first fixture's superbet ref, but merge() then spins up a *second*
    MergedFixture sibling for it instead of dropping it -- and both siblings
    hash to the same event_id in _to_event_record, doubling ENRICH's work for
    one real match. The expected event_id prefixes below are the exact
    hashes _to_event_record produced in production that day.
    """
    real_pairs = [
        ("Stefania Bojica", "Melinda Biro", "Tennis Category 37",
         "2026-09-12T07:00:00+00:00", "14941583", "14942047", "59da6ee62e"),
        ("Elza Tomase", "Anne Schaefer", "Tennis Category 37",
         "2026-09-12T08:00:00+00:00", "14927346", "14944518", "57f6feda28"),
        ("Hazem Naw", "Oscar Brown", "Tennis Category 23",
         "2026-09-12T08:30:00+00:00", "14942337", "14942759", "f37a5f012b"),
        ("Patrick Schoen", "Jack Anthrop", "Tennis Category 23",
         "2026-09-12T10:30:00+00:00", "14942738", "14943083", "661c646210"),
    ]

    superbet_events = []
    for home, away, competition, kickoff, id_a, id_b, _ in real_pairs:
        for ext_id in (id_a, id_b):
            superbet_events.append(
                DiscoveredEvent(
                    source="superbet",
                    external_id=ext_id,
                    sport="tennis",
                    competition=competition,
                    home_team=home,
                    away_team=away,
                    kickoff=datetime.fromisoformat(kickoff),
                    status="scheduled",
                )
            )

    merged = DeduplicationEngine().merge({"superbet": superbet_events})
    assert len(merged) == 8, "documents the sibling-fixture bug merge() itself has"

    deduped = _dedup_by_event_identity(merged)
    assert len(deduped) == 4

    records = [_to_event_record(f) for f in deduped]
    assert {r.event_id for r in records} == {
        _event_id(
            "tennis", competition,
            f"{_normalize_name(home)}|{_normalize_name(away)}", kickoff,
        )
        for home, away, competition, kickoff, _, _, _ in real_pairs
    }
    assert {r.event_id[:10] for r in records} == {p[6] for p in real_pairs}


def test_dedup_by_event_identity_merges_sources_instead_of_discarding_the_loser():
    """Regression for a bug the code review found in the fix above: picking
    the sibling with more sources and discarding the other whole would
    reproduce, one step later, exactly the 'no price' failure this session's
    team_aliases.py entries exist to fix -- if the discarded sibling was the
    one actually carrying odds, or a source the survivor lacks, that data
    would silently disappear. The merge must combine sources and keep odds
    from whichever sibling has them, not just pick a winner."""
    fixture_a = MergedFixture(
        sport="tennis", competition="Tennis Category 37",
        home_team="Stefania Bojica", away_team="Melinda Biro",
        kickoff=datetime.fromisoformat("2026-09-12T07:00:00+00:00"),
        status="scheduled",
        sources=[SourceRef(source="superbet", external_id="14941583")],
        primary_source="superbet", primary_external_id="14941583",
        odds=None,
    )
    fixture_b = MergedFixture(
        sport="tennis", competition="Tennis Category 37",
        home_team="Stefania Bojica", away_team="Melinda Biro",
        kickoff=datetime.fromisoformat("2026-09-12T07:00:00+00:00"),
        status="scheduled",
        sources=[SourceRef(source="superbet-tennis-challenger", external_id="99")],
        primary_source="superbet-tennis-challenger", primary_external_id="99",
        odds={"1": 1.9},
    )
    merged = _dedup_by_event_identity([fixture_a, fixture_b])
    assert len(merged) == 1
    survivor = merged[0]
    assert survivor.odds == {"1": 1.9}, "the tie-break must not drop the sibling's odds"
    external_ids = {s.external_id for s in survivor.sources}
    assert external_ids == {"14941583", "99"}, "both sources must survive the merge"


def test_dedup_by_event_identity_ignores_competition_case_and_whitespace():
    """A source can leave one sibling with a placeholder competition label
    and the other with the real one (_attach_source's upgrade only ever
    touches one fixture at a time) -- a raw string comparison would let a
    trivial case/whitespace difference keep two siblings apart."""
    kickoff = datetime.fromisoformat("2026-09-12T07:00:00+00:00")
    fixture_a = MergedFixture(
        sport="football", competition="Tennis Category 37 ",
        home_team="A", away_team="B", kickoff=kickoff, status="scheduled",
        sources=[SourceRef(source="bzzoiro", external_id="1")],
        primary_source="bzzoiro", primary_external_id="1",
    )
    fixture_b = MergedFixture(
        sport="football", competition="tennis category 37",
        home_team="A", away_team="B", kickoff=kickoff, status="scheduled",
        sources=[SourceRef(source="superbet", external_id="2")],
        primary_source="superbet", primary_external_id="2",
    )
    merged = _dedup_by_event_identity([fixture_a, fixture_b])
    assert len(merged) == 1
