"""Bzzoiro tennis provider: box score, the cheap listing, and the date trap.

Payload shapes captured live from sports.bzzoiro.com/tennis/api/v2 on
2026-08-28 (Alejandro Tabilo 2-1 Ben Shelton, match 44426, Washington ATP 500)
and trimmed to the fields under test.

Three live facts drive the code and are asserted here rather than assumed:

* the tennis product has its **own 100-a-day quota bucket**, not football's 7500;
* ``/matches/{id}/h2h/`` returns both players' recent form *and* the meetings, so
  one request serves all three enrichment slots;
* those form lists are relative to **now**, not to the match -- asked about a
  fixture dated 2026-08-01 the live API returned matches from 2026-08-15.
"""
import json as _json

import pytest

from bet.api_clients.bzzoiro_tennis import BzzoiroTennisClient
from bet.api_clients.env import limit_env_var
from bet.api_clients.rate_limiter import API_DAILY_LIMITS, RateLimiter
from bet.discovery.dedup import DeduplicationEngine
from bet.integration.source_result import SourceOperationResult, SourceResultStatus
from bet.simple_stats import providers
from bet.simple_stats.analyze import analyze_dossier
from bet.simple_stats.contracts import (
    EventDossierV1,
    EventRecord,
    MetricObservation,
    ProviderValue,
)
from bet.simple_stats.discover import _to_event_record
from bet.simple_stats.enrich import _build_tasks
from bet.simple_stats.preflight import CREDENTIAL_ENV_VARS
from bet.simple_stats.providers import (
    RunBudget,
    _bzzoiro_tennis_match_metrics,
    fetch_bzzoiro_tennis_history,
)

# --- live-shaped payloads -------------------------------------------------


def _player(pid, name, ranking=None):
    return {
        "id": pid,
        "name": name,
        "short_name": name,
        "country_code": "US",
        "country_name": "USA",
        "gender": "M",
        "current_ranking": {"position": ranking, "points": 1, "type": "ATP"}
        if ranking
        else None,
    }


TOURNAMENT = {
    "id": 121,
    "name": "Washington",
    "circuit": "ATP",
    "category": "atp_500",
    "surface": "hard",
}

BOX_SCORE = {
    "id": 44426,
    "tournament": TOURNAMENT,
    "player1": _player(208, "Alejandro Tabilo", 29),
    "player2": _player(504, "Ben Shelton", 6),
    "is_doubles": False,
    "match_date": "2026-08-01T01:15:00+00:00",
    "status": "finished",
    "player1_sets": 2,
    "player2_sets": 1,
    "sets_detail": [{"p1": 4, "p2": 6}, {"p1": 7, "p2": 5}, {"p1": 6, "p2": 4}],
    "p1_aces": 6,
    "p1_double_faults": 4,
    "p1_first_serve_pct": 60.86956521739131,
    "p1_first_serve_won_pct": 80.35714285714286,
    "p1_break_points_saved_pct": 57.14285714285714,
    "p1_break_points_converted_pct": 66.66666666666666,
    "p1_service_games": 16,
    "p1_service_games_won": 13,
    "p1_games_won": 17,
    "p2_aces": 5,
    "p2_double_faults": 3,
    "p2_first_serve_pct": 63.63636363636363,
    "p2_first_serve_won_pct": 75.0,
    "p2_break_points_saved_pct": 33.33333333333333,
    "p2_break_points_converted_pct": 42.857142857142854,
    "p2_service_games": 15,
    "p2_service_games_won": 12,
    "p2_games_won": 15,
}


def _form_row(match_id, date, opponent_id, opponent_name):
    return {
        "id": match_id,
        "date": date,
        "tournament": TOURNAMENT,
        "surface": "hard",
        "round": "Round of 32",
        "opponent": _player(opponent_id, opponent_name),
        "score": [{"p1": 6, "p2": 2}],
        "won": True,
    }


H2H_PAYLOAD = {
    "match_id": 44426,
    "player1": _player(208, "Alejandro Tabilo", 29),
    "player2": _player(504, "Ben Shelton", 6),
    "h2h": None,
    # Relative to *now*, not to the 2026-08-01 fixture: the first two postdate it.
    "player1_last5": [
        _form_row(46532, "2026-08-17", 781, "Rafael Jodar"),
        _form_row(46103, "2026-08-15", 359, "Jan-Lennard Struff"),
        _form_row(45001, "2026-07-30", 900, "Terence Atmane"),
    ],
    "player2_last5": [_form_row(45500, "2026-07-28", 901, "Frances Tiafoe")],
}


def _client(monkeypatch, tmp_path, payloads):
    client = BzzoiroTennisClient(rate_limiter=RateLimiter(usage_dir=tmp_path / "usage"))
    client.api_key = "test-key"
    calls = []

    def _fake(*, endpoint, params, operation, source_event_id=None):
        calls.append((endpoint, dict(params or {})))
        payload = payloads.get(endpoint)
        if payload is None:
            return SourceOperationResult(
                status=SourceResultStatus.NOT_FOUND,
                provider="bzzoiro-tennis",
                operation=operation,
                error_code="http_404",
            )
        if callable(payload):
            payload = payload(dict(params or {}))
        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=_json.loads(_json.dumps(payload)),
            provider="bzzoiro-tennis",
            operation=operation,
            http_status=200,
        )

    monkeypatch.setattr(client, "_request_with_evidence", _fake)
    return client, calls


@pytest.fixture(autouse=True)
def _clear_caches():
    """These caches are module-level and process-wide; without clearing, a test
    would be answered from another test's result and assert nothing."""
    for cache in (
        providers._BZZOIRO_TENNIS_CACHE,
        providers._BZZOIRO_TENNIS_LISTING_CACHE,
        providers._BZZOIRO_TENNIS_HEADERS,
    ):
        cache.clear()
    yield
    for cache in (
        providers._BZZOIRO_TENNIS_CACHE,
        providers._BZZOIRO_TENNIS_LISTING_CACHE,
        providers._BZZOIRO_TENNIS_HEADERS,
    ):
        cache.clear()


# --- quota: a different bucket from football ------------------------------


def test_the_tennis_quota_is_read_as_tennis_not_inherited_from_football():
    """One account, two products, two ceilings 75x apart. Inheriting football's
    7500 here would promise a slate of tennis that 100 calls cannot enrich."""
    metadata = BzzoiroTennisClient._extract_quota_metadata(
        {
            "ratelimit": '"tennis";r=97;t=57114',
            "ratelimit-policy": '"tennis";q=100;w=86400',
        }
    )
    assert metadata["daily_limit"] == 100
    assert metadata["daily_remaining"] == 97


def test_tennis_stays_capped_while_football_does_not():
    """The sharpest thing to get wrong here. One account, one key, and the PRO
    upgrade lifted the football ceiling while leaving tennis at 100 a day
    (verified live 2026-08-28, after the upgrade). If tennis inherited football's
    now-absent limit, a run would promise a tennis slate and hit HTTP 429 six
    fixtures in, with the budget already spent.
    """
    assert API_DAILY_LIMITS["bzzoiro-tennis"] < 100  # backstop under the real 100
    assert "bzzoiro" not in API_DAILY_LIMITS  # football: no local ceiling


def test_the_two_products_share_a_credential_but_not_a_counter():
    """Separate provider keys, because the quota buckets are separate
    server-side: a tennis call must not decrement the football counter."""
    assert CREDENTIAL_ENV_VARS["bzzoiro-tennis"] == ("BZZORIO_KEY",)
    assert CREDENTIAL_ENV_VARS["bzzoiro"] == ("BZZORIO_KEY",)
    assert limit_env_var("bzzoiro-tennis") == "BET_LIMIT_BZZOIRO_TENNIS"


def test_the_key_is_read_from_bzzorio_key(monkeypatch, tmp_path):
    monkeypatch.setenv("BZZORIO_KEY", "from-env")
    client = BzzoiroTennisClient(RateLimiter(usage_dir=tmp_path / "u"))
    assert client.api_key == "from-env"
    assert client._build_headers()["Authorization"] == "Token from-env"


# --- box score ------------------------------------------------------------


def test_the_box_score_keeps_the_per_player_split(monkeypatch, tmp_path):
    """Already p1_*/p2_* in the payload, so tennis gets the split in one wave --
    football needed a second one to stop summing the sides."""
    client, _ = _client(monkeypatch, tmp_path, {"/matches/44426/": BOX_SCORE})
    result = client.get_match_result("44426")
    assert result.status is SourceResultStatus.SUCCESS
    assert result.value["sides"]["p1"]["aces"] == 6
    assert result.value["sides"]["p2"]["aces"] == 5


def test_totals_and_per_player_metrics_are_both_derived(monkeypatch, tmp_path):
    """Hand-checked against the live payload: 6+5 aces, 4+3 double faults,
    17+15 games, 2+1 sets."""
    client, _ = _client(monkeypatch, tmp_path, {"/matches/44426/": BOX_SCORE})
    totals, per_side, gap = _bzzoiro_tennis_match_metrics(client, "44426")

    assert gap is None
    assert totals["aces_total"] == 11
    assert totals["double_faults_total"] == 7
    assert totals["total_games"] == 32
    assert totals["total_sets"] == 3
    assert per_side["p1"]["aces_for"] == 6
    assert per_side["p2"]["aces_for"] == 5
    assert per_side["p1"]["games_won"] == 17
    assert round(per_side["p1"]["first_serve_pct"], 2) == 60.87


def test_breaks_come_from_service_game_integers_not_from_a_percentage(
    monkeypatch, tmp_path
):
    """(16-13) + (15-12) = 6, which the 4-6 / 7-5 / 6-4 set scores bear out. The
    payload also carries break_points_saved_pct = 57.14285714285714; recovering
    "4 of 7" from that float means guessing a denominator, and a market priced
    off a guessed denominator is a fabricated market."""
    client, _ = _client(monkeypatch, tmp_path, {"/matches/44426/": BOX_SCORE})
    totals, _, _ = _bzzoiro_tennis_match_metrics(client, "44426")
    assert totals["breaks_total"] == 6


def test_breaks_are_absent_when_service_games_are_not_reported(monkeypatch, tmp_path):
    payload = {
        key: value
        for key, value in BOX_SCORE.items()
        if "service_games" not in key
    }
    client, _ = _client(monkeypatch, tmp_path, {"/matches/44426/": payload})
    totals, _, _ = _bzzoiro_tennis_match_metrics(client, "44426")
    assert "breaks_total" not in totals
    assert totals["aces_total"] == 11


def test_half_a_total_is_omitted_rather_than_reported_as_the_total(
    monkeypatch, tmp_path
):
    """One side's aces is not a smaller total, it is the wrong number -- and it is
    the number an UNDER line would bank on."""
    payload = {key: value for key, value in BOX_SCORE.items() if key != "p2_aces"}
    client, _ = _client(monkeypatch, tmp_path, {"/matches/44426/": payload})
    totals, per_side, _ = _bzzoiro_tennis_match_metrics(client, "44426")
    assert "aces_total" not in totals
    assert per_side["p1"]["aces_for"] == 6


def test_a_walkover_reports_no_box_score_rather_than_zeroes(monkeypatch, tmp_path):
    walkover = {
        "id": 48069,
        "tournament": TOURNAMENT,
        "player1": _player(4598, "Lucia Gale"),
        "player2": _player(4161, "Laquisa Khan"),
        "is_doubles": False,
        "match_date": "2026-08-28T00:00:00+00:00",
        "status": "walkover",
        "player1_sets": None,
        "player2_sets": None,
    }
    client, _ = _client(monkeypatch, tmp_path, {"/matches/48069/": walkover})
    result = client.get_match_result("48069")
    assert result.status is SourceResultStatus.SCHEMA_ERROR
    assert result.error_code == "statistics_empty"


# --- the listing: one request for three slots ----------------------------


def test_one_h2h_request_serves_all_three_slots(monkeypatch, tmp_path):
    """The whole reason this provider fits inside a 100-call day. Two ?player=
    listings would cost two requests and carry less (no meetings, and the
    opponent/date needed to place a box score in time)."""
    payloads = {"/matches/44426/h2h/": H2H_PAYLOAD, "/matches/45001/": BOX_SCORE}
    client, calls = _client(monkeypatch, tmp_path, payloads)
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    budget = RunBudget(200)
    limiter = RateLimiter(usage_dir=tmp_path / "u")
    for slot_player in ("208", "504"):
        fetch_bzzoiro_tennis_history(
            "44426", slot_player, limiter, budget, mode="l10", as_of_date="2026-08-01"
        )
    fetch_bzzoiro_tennis_history(
        "44426", "", limiter, budget, mode="h2h", as_of_date="2026-08-01"
    )

    listing_calls = [c for c in calls if c[0] == "/matches/44426/h2h/"]
    assert len(listing_calls) == 1


def test_form_after_the_fixture_is_filtered_out(monkeypatch, tmp_path):
    """The live trap. Asked about match 44426 (2026-08-01) the API answered with
    matches from 2026-08-15 and 2026-08-17. Keeping those prices a past date with
    the result of its own future, invisibly -- every number looks ordinary."""
    payloads = {
        "/matches/44426/h2h/": H2H_PAYLOAD,
        "/matches/45001/": BOX_SCORE,
        "/matches/46103/": BOX_SCORE,
        "/matches/46532/": BOX_SCORE,
    }
    client, _ = _client(monkeypatch, tmp_path, payloads)
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    outcome = fetch_bzzoiro_tennis_history(
        "44426", "208", RateLimiter(usage_dir=tmp_path / "u"), RunBudget(200),
        mode="l10", as_of_date="2026-08-01",
    )
    dates = [pv.match_date[:10] for pv in outcome.metrics["aces_total"]]
    assert dates == ["2026-07-30"]


def test_a_later_fixture_sees_the_whole_form_list(monkeypatch, tmp_path):
    """The same filter must not be a blanket truncation: for a fixture after all
    three, all three count."""
    payloads = {
        "/matches/44426/h2h/": H2H_PAYLOAD,
        "/matches/45001/": BOX_SCORE,
        "/matches/46103/": BOX_SCORE,
        "/matches/46532/": BOX_SCORE,
    }
    client, _ = _client(monkeypatch, tmp_path, payloads)
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    outcome = fetch_bzzoiro_tennis_history(
        "44426", "208", RateLimiter(usage_dir=tmp_path / "u"), RunBudget(200),
        mode="l10", as_of_date="2026-09-01",
    )
    assert len(outcome.metrics["aces_total"]) == 3


def test_the_fixture_being_priced_is_never_in_its_own_sample(monkeypatch, tmp_path):
    payload = dict(H2H_PAYLOAD)
    payload["player1_last5"] = [
        _form_row(44426, "2026-07-31", 504, "Ben Shelton"),
        _form_row(45001, "2026-07-30", 900, "Terence Atmane"),
    ]
    client, _ = _client(
        monkeypatch, tmp_path,
        {"/matches/44426/h2h/": payload, "/matches/45001/": BOX_SCORE},
    )
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    outcome = fetch_bzzoiro_tennis_history(
        "44426", "208", RateLimiter(usage_dir=tmp_path / "u"), RunBudget(200),
        mode="l10", as_of_date="2026-08-01",
    )
    assert [pv.match_id for pv in outcome.metrics["aces_total"]] == ["45001"]


def test_h2h_never_emits_a_per_player_metric(monkeypatch, tmp_path):
    """The slot carries no marker for which of the two a per-player value belongs
    to, so attributing one would mix the two players' samples."""
    payload = dict(H2H_PAYLOAD)
    payload["h2h"] = [_form_row(45001, "2026-07-30", 504, "Ben Shelton")]
    client, _ = _client(
        monkeypatch, tmp_path,
        {"/matches/44426/h2h/": payload, "/matches/45001/": BOX_SCORE},
    )
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    outcome = fetch_bzzoiro_tennis_history(
        "44426", "", RateLimiter(usage_dir=tmp_path / "u"), RunBudget(200),
        mode="h2h", as_of_date="2026-08-01",
    )
    assert outcome.metrics["aces_total"][0].value == 11
    assert not [name for name in outcome.metrics if name.endswith("_for")]
    assert not [name for name in outcome.metrics if name.endswith("_pct")]


def test_the_players_own_side_is_read_not_always_p1(monkeypatch, tmp_path):
    """A form-list row names only the opponent, so which side the player was on
    comes from the box score's own header. Reading p1 blindly would report
    Tabilo's six aces as Shelton's."""
    payloads = {"/matches/44426/h2h/": H2H_PAYLOAD, "/matches/45500/": BOX_SCORE}
    client, _ = _client(monkeypatch, tmp_path, payloads)
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    # Shelton (504) is player2 in BOX_SCORE, and 45500 is his form row.
    outcome = fetch_bzzoiro_tennis_history(
        "44426", "504", RateLimiter(usage_dir=tmp_path / "u"), RunBudget(200),
        mode="l10", as_of_date="2026-08-01",
    )
    assert outcome.metrics["aces_for"][0].value == 5
    assert outcome.metrics["games_won"][0].value == 15


def test_a_player_not_in_the_fixture_is_a_gap_not_a_wrong_answer(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path, {"/matches/44426/h2h/": H2H_PAYLOAD})
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    outcome = fetch_bzzoiro_tennis_history(
        "44426", "99999", RateLimiter(usage_dir=tmp_path / "u"), RunBudget(200),
        mode="l10", as_of_date="2026-08-01",
    )
    assert outcome.metrics == {}
    assert any("not in match" in gap for gap in outcome.data_gaps)


# --- discovery ------------------------------------------------------------


def _listing_payload(rows):
    return {"count": len(rows), "results": rows}


def _match_row(match_id, p1, p2, *, doubles=False, category="atp_500"):
    return {
        "id": match_id,
        "tournament": {**TOURNAMENT, "category": category},
        "player1": _player(*p1),
        "player2": _player(*p2),
        "is_doubles": doubles,
        "match_date": "2026-08-28T12:00:00+00:00",
        "status": "scheduled",
        "player1_sets": None,
        "player2_sets": None,
    }


def _adapter(monkeypatch, rows):
    from bet.simple_stats.discover import BzzoiroTennisDiscoveryAdapter

    adapter = BzzoiroTennisDiscoveryAdapter(RateLimiter())
    adapter._client.api_key = "test-key"

    def _fake(*, endpoint, params, operation, source_event_id=None):
        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=_listing_payload(rows),
            provider="bzzoiro-tennis",
            operation=operation,
            http_status=200,
        )

    monkeypatch.setattr(adapter._client, "_request_with_evidence", _fake)
    return adapter


def test_doubles_are_dropped_at_discovery(monkeypatch):
    """Nothing in the pipeline models a pair -- DiscoveredEvent and EventRecord
    both hold exactly two participants -- so a doubles match let through would
    dedup against a singles fixture between two of the same four players."""
    rows = [
        _match_row(1, (208, "Alejandro Tabilo"), (504, "Ben Shelton")),
        _match_row(2, (208, "Alejandro Tabilo"), (504, "Ben Shelton"), doubles=True),
    ]
    events = _adapter(monkeypatch, rows)._fetch_events_impl("2026-08-28", "tennis")
    assert [e.external_id for e in events] == ["1"]


def test_amateur_tiers_are_dropped_at_discovery(monkeypatch):
    """A quota decision, not a taste one: UTR was 47% of a four-week sample and
    the tennis budget is about six enriched fixtures a day."""
    rows = [
        _match_row(1, (208, "A"), (504, "B"), category="atp_500"),
        _match_row(2, (300, "C"), (301, "D"), category="challenger"),
        _match_row(3, (4598, "E"), (4161, "F"), category="utr"),
    ]
    adapter = _adapter(monkeypatch, rows)
    events = adapter._fetch_events_impl("2026-08-28", "tennis")
    assert {e.external_id for e in events} == {"1", "2"}
    # Reported, not silent: a thin slate and a filtered slate look identical
    # from the outside otherwise.
    assert any("non-tour-level" in err for err in adapter.last_errors)


def test_an_unknown_tier_is_kept(monkeypatch):
    """A denylist, so a tier the provider adds later defaults to visible rather
    than silently vanishing."""
    rows = [_match_row(1, (208, "A"), (504, "B"), category="atp_finals")]
    events = _adapter(monkeypatch, rows)._fetch_events_impl("2026-08-28", "tennis")
    assert len(events) == 1


def test_native_player_ids_reach_the_event_record(monkeypatch):
    """The first native identification tennis has ever had. The keys are named
    home_team_id/away_team_id on purpose: that is what _to_event_record already
    reads, so the generic lift needs no change for a second sport."""
    rows = [_match_row(1, (208, "Alejandro Tabilo"), (504, "Ben Shelton"))]
    discovered = _adapter(monkeypatch, rows)._fetch_events_impl("2026-08-28", "tennis")

    merged = DeduplicationEngine().merge({"bzzoiro-tennis": discovered})
    record = _to_event_record(merged[0])
    assert record.sport == "tennis"
    assert record.player_one == "Alejandro Tabilo"
    assert record.provider_team_ids["bzzoiro-tennis"] == {"home": "208", "away": "504"}
    assert record.source_ids["bzzoiro-tennis"] == "1"
    # The tier is part of the competition name because EventRecord has nowhere
    # else for it, and it is what separates a tour event from a same-named
    # challenger in the dedup key and the event id.
    assert record.competition == "Washington (atp_500)"


# --- enrich wiring --------------------------------------------------------


def _event(**overrides):
    kwargs = dict(
        event_id="evt",
        sport="tennis",
        competition="Washington (atp_500)",
        player_one="Alejandro Tabilo",
        player_two="Ben Shelton",
        start_time="2026-08-01T01:15:00+00:00",
        source_ids={"bzzoiro-tennis": "44426"},
        provider_team_ids={"bzzoiro-tennis": {"home": "208", "away": "504"}},
        identity_confidence="CONFIRMED",
        status="ACTIVE",
    )
    kwargs.update(overrides)
    return EventRecord(**kwargs)


def test_tennis_tasks_cover_all_three_slots():
    slots = {t.slot for t in _build_tasks(_event()) if t.provider == "bzzoiro-tennis"}
    assert slots == {"team_a", "team_b", "h2h"}


@pytest.mark.parametrize(
    "overrides", [{"provider_team_ids": {}}, {"source_ids": {}}]
)
def test_no_tennis_tasks_without_both_native_ids(overrides):
    tasks = _build_tasks(_event(**overrides))
    assert not [t for t in tasks if t.provider == "bzzoiro-tennis"]


# --- analyze --------------------------------------------------------------


def _pv(value, match_id):
    return ProviderValue(
        provider="bzzoiro-tennis",
        match_id=match_id,
        match_date="2026-07-30",
        opponent="Terence Atmane",
        value=value,
        observed_at="2026-08-01T00:00:00+00:00",
    )


def test_new_tennis_totals_produce_rows():
    """double_faults_total and breaks_total were canonical names with no line, so
    ANALYZE emitted nothing for them however good the data was."""
    dossier = EventDossierV1(
        event_id="evt",
        sport="tennis",
        team_a_name="Alejandro Tabilo",
        team_b_name="Ben Shelton",
        metrics={
            name: MetricObservation(
                canonical_name=name,
                team_a_l10=[_pv(float(v), f"{name}{i}") for i, v in enumerate(values)],
            )
            for name, values in {
                "double_faults_total": [7, 6, 8, 5, 9, 7],
                "breaks_total": [6, 4, 5, 7, 3, 6],
            }.items()
        },
        readiness="PARTIAL",
    )
    markets = {row.market for row in analyze_dossier(dossier)}
    assert {"double_faults_total", "breaks_total"} <= markets


def test_per_player_tennis_rows_name_their_player():
    """"Player Aces" is the same mechanism as football's per-team rows: one
    side's own line, one row per side, told apart by team_name."""
    dossier = EventDossierV1(
        event_id="evt",
        sport="tennis",
        team_a_name="Alejandro Tabilo",
        team_b_name="Ben Shelton",
        metrics={
            "aces_for": MetricObservation(
                canonical_name="aces_for",
                team_a_l10=[_pv(9.0, f"a{i}") for i in range(6)],
                team_b_l10=[_pv(2.0, f"b{i}") for i in range(6)],
            )
        },
        readiness="PARTIAL",
    )
    rows = [r for r in analyze_dossier(dossier) if r.market == "aces_for"]
    over = {r.team_name: r for r in rows if r.line == 4.5 and r.direction == "OVER"}
    assert set(over) == {"Alejandro Tabilo", "Ben Shelton"}
    assert over["Alejandro Tabilo"].hit_rate == 1.0
    assert over["Ben Shelton"].hit_rate == 0.0
    # Two samples of six, never one of twelve.
    assert {r.sample_size for r in over.values()} == {6}


def test_a_retirement_is_dropped_rather_than_sampled(monkeypatch, tmp_path):
    """A retired match can carry a *partial* box score -- aces and service games
    up to the point somebody stopped -- which is a real number describing a match
    that was not played. It reads as an unusually short match and drags every
    UNDER line. The form list it arrives in carries no status, so the box score's
    own header is the first place this is knowable.
    """
    retired = {**BOX_SCORE, "id": 45001, "status": "retired"}
    payloads = {"/matches/44426/h2h/": H2H_PAYLOAD, "/matches/45001/": retired}
    client, _ = _client(monkeypatch, tmp_path, payloads)
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    outcome = fetch_bzzoiro_tennis_history(
        "44426", "208", RateLimiter(usage_dir=tmp_path / "u"), RunBudget(200),
        mode="l10", as_of_date="2026-08-01",
    )
    assert outcome.metrics == {}
    # Counted in one line, not one gap per match: these are expected coverage,
    # not a problem to investigate per fixture.
    assert len(outcome.data_gaps) == 1
    assert "walkover" in outcome.data_gaps[0]
