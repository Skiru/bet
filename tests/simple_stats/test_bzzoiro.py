"""Bzzoiro provider: client parsing, the home/away split, and player props.

Every payload shape here was captured live from sports.bzzoiro.com on
2026-08-28 (Olympique Lyonnais 1-2 Fenerbahçe, event 587706, Champions League
qualifying) and trimmed to the fields under test. Two of these shapes are the
reason the code around them looks the way it does, so they are asserted rather
than assumed:

* ``/teams/{id}/fixtures/`` pages **ascending** and ignores ``ordering``;
* ``/players/{id}/stats/`` pages **descending** and carries no date at all.
"""
from types import SimpleNamespace

import pytest

from bet.api_clients.bzzoiro import BzzoiroClient
from bet.api_clients.env import limit_env_var
from bet.api_clients.rate_limiter import API_DAILY_LIMITS, RateLimiter
from bet.integration.source_result import SourceOperationResult, SourceResultStatus
from bet.simple_stats import providers
from bet.simple_stats.analyze import analyze_dossier
from bet.simple_stats.contracts import (
    EventDossierV1,
    EventRecord,
    MetricObservation,
    PlayerMetricObservation,
    ProviderValue,
)
from bet.simple_stats.enrich import _build_tasks, _dossier_for_event
from bet.simple_stats.providers import (
    RUN_BUDGET_OVERRIDES,
    FetchOutcome,
    RunBudget,
    fetch_bzzoiro_history,
    fetch_bzzoiro_player_history,
)

# --- live-shaped payloads -------------------------------------------------

STATS_PAYLOAD = {
    "event_id": 587706,
    "stats": {
        "home": {
            "fouls": 12,
            "corner_kicks": 5,
            "yellow_cards": 1,
            "total_shots": 17,
            "shots_on_target": 6,
            "ball_possession": 59,
            "red_cards": None,
            # Object-valued, as several real fields are.
            "dribbles": {"value": 7, "total": 13, "pct": 54},
        },
        "away": {
            "fouls": 17,
            "corner_kicks": 7,
            "yellow_cards": 3,
            "total_shots": 16,
            "shots_on_target": 7,
            "ball_possession": 41,
            "red_cards": None,
        },
        # Half splits sit alongside home/away in the same object and must not
        # be read as a third team.
        "first_half": {"home": {"corner_kicks": 3}, "away": {"corner_kicks": 4}},
        "second_half": {"home": {"corner_kicks": 2}, "away": {"corner_kicks": 3}},
    },
}


def _fixture_row(
    event_id, date, home_id, away_id, home="H", away="A", status="finished",
    home_score_ht=None, away_score_ht=None,
):
    row = {
        "id": event_id,
        "league_id": 7,
        "season_id": 1,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_team": home,
        "away_team": away,
        "home_score": 1,
        "away_score": 0,
        "event_date": date,
        "status": status,
    }
    if home_score_ht is not None and away_score_ht is not None:
        row["home_score_ht"] = home_score_ht
        row["away_score_ht"] = away_score_ht
    return row


def _client(monkeypatch, tmp_path, payloads):
    """A BzzoiroClient whose HTTP layer replays ``{endpoint: payload}``.

    Patched at ``_request_with_evidence`` rather than at ``requests.get`` so the
    tests exercise this client's own parsing without also asserting the shared
    evidence/quota machinery, which has its own tests.
    """
    import json as _json

    client = BzzoiroClient(rate_limiter=RateLimiter(usage_dir=tmp_path / "usage"))
    client.api_key = "test-key"
    calls = []

    def _fake(*, endpoint, params, operation, source_event_id=None):
        calls.append((endpoint, dict(params or {})))
        payload = payloads.get(endpoint)
        if payload is None:
            return SourceOperationResult(
                status=SourceResultStatus.NOT_FOUND,
                provider="bzzoiro",
                operation=operation,
                error_code="http_404",
            )
        if callable(payload):
            payload = payload(dict(params or {}))
        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=_json.loads(_json.dumps(payload)),
            provider="bzzoiro",
            operation=operation,
            http_status=200,
        )

    monkeypatch.setattr(client, "_request_with_evidence", _fake)
    return client, calls


@pytest.fixture(autouse=True)
def _clear_bzzoiro_caches():
    """The stats and fixture caches are module-level and process-wide.

    Without this, a test that stubs a payload would be answered from another
    test's cached result -- and would pass while asserting nothing.
    """
    providers._BZZOIRO_STATS_CACHE.clear()
    providers._BZZOIRO_FIXTURES_CACHE.clear()
    yield
    providers._BZZOIRO_STATS_CACHE.clear()
    providers._BZZOIRO_FIXTURES_CACHE.clear()


# --- client ---------------------------------------------------------------


def test_quota_is_read_from_the_providers_own_headers():
    """The one provider whose real ceiling is visible to us. Reading it wrong
    means preflight reports a guess while calling it measured."""
    metadata = BzzoiroClient._extract_quota_metadata(
        {
            "ratelimit": '"football";r=7475;t=59760',
            "ratelimit-policy": '"football";q=7500;w=86400',
        }
    )
    assert metadata["daily_remaining"] == 7475
    assert metadata["daily_limit"] == 7500
    assert metadata["window_seconds"] == 86400
    assert metadata["reset_seconds"] == 59760


def test_missing_quota_headers_report_nothing_rather_than_zero():
    assert BzzoiroClient._extract_quota_metadata({}) == {}
    assert BzzoiroClient._extract_quota_metadata(None) == {}


def test_statistics_keeps_the_home_away_split(monkeypatch, tmp_path):
    """The reason this provider exists. Collapsing the two sides in the client
    -- which every other client here does -- would make a per-team market
    unpriceable no matter what the rest of the pipeline did."""
    client, _ = _client(monkeypatch, tmp_path, {"/events/587706/stats/": STATS_PAYLOAD})
    result = client.get_statistics_result("587706")
    assert result.status is SourceResultStatus.SUCCESS

    by_side = {}
    for row in result.value["statistics"]:
        side = by_side.setdefault(row["side"], {})
        side[row["normalized_metric_name"]] = row["value"]

    assert set(by_side) == {"home", "away"}
    assert by_side["home"]["corners"] == 5
    assert by_side["away"]["corners"] == 7


def test_statistics_half_splits_get_their_own_metric_name(monkeypatch, tmp_path):
    """docs/PLAN_BOGATE_STATYSTYKI.md Faza 3: first_half/second_half sit
    alongside home/away in the same /stats/ object. A half-split value must
    not collide with (or silently overwrite) the full-match figure -- so it
    gets a distinct normalized_metric_name, "corners_1h"/"corners_2h", never
    plain "corners"."""
    client, _ = _client(monkeypatch, tmp_path, {"/events/587706/stats/": STATS_PAYLOAD})
    result = client.get_statistics_result("587706")
    assert result.status is SourceResultStatus.SUCCESS

    by_side_metric = {}
    for row in result.value["statistics"]:
        by_side_metric[(row["side"], row["normalized_metric_name"])] = row["value"]

    assert by_side_metric[("home", "corners")] == 5
    assert by_side_metric[("away", "corners")] == 7
    assert by_side_metric[("home", "corners_1h")] == 3
    assert by_side_metric[("away", "corners_1h")] == 4
    assert by_side_metric[("home", "corners_2h")] == 2
    assert by_side_metric[("away", "corners_2h")] == 3


def test_null_and_object_valued_stats_are_absent_not_zero(monkeypatch, tmp_path):
    """``"red_cards": null`` on a match with no red card, and object-valued
    fields like dribbles. A null recorded as 0 would let an UNDER line bank an
    observation the provider never made."""
    client, _ = _client(monkeypatch, tmp_path, {"/events/587706/stats/": STATS_PAYLOAD})
    result = client.get_statistics_result("587706")
    names = {row["normalized_metric_name"] for row in result.value["statistics"]}
    assert "red_cards" not in names
    assert "dribbles" in result.value["unknown_metrics"]


def test_h2h_comes_from_the_fixture_and_excludes_it(monkeypatch, tmp_path):
    """``/events/{id}/`` embeds the pair's meetings, so H2H costs no listing
    call -- and the listing includes *this* fixture, which must not end up in
    its own evidence sample."""
    payload = dict(_fixture_row(587706, "2026-08-26T19:00:00+00:00", 100, 134))
    payload["head_to_head"] = {
        "total_matches": 2,
        "recent_matches": [
            {
                "event_id": 587706,
                "date": "2026-08-26T19:00:00+00:00",
                "home": "Olympique Lyonnais",
                "away": "Fenerbahçe",
                "score": "1-2",
                "home_team_id": 100,
                "away_team_id": 134,
                "home_score": 1,
                "away_score": 2,
            },
            {
                "event_id": 587701,
                "date": "2026-08-18T19:00:00+00:00",
                "home": "Fenerbahçe",
                "away": "Olympique Lyonnais",
                "score": "1-1",
                "home_team_id": 134,
                "away_team_id": 100,
                "home_score": 1,
                "away_score": 1,
            },
        ],
    }
    client, _ = _client(monkeypatch, tmp_path, {"/events/587706/": payload})
    result = client.get_event_result("587706")
    ids = [m["provider_match_id"] for m in result.value["matches"]]
    assert ids == ["587701"]


# --- history: newest-N off an ascending listing ---------------------------


def test_last_ten_comes_from_the_end_of_an_ascending_listing(monkeypatch, tmp_path):
    """This listing pages oldest-first and ignores ``ordering``, so page one is
    the wrong ten. Reading page one and sorting it descending -- the obvious
    implementation -- yields a "last three" from two seasons ago.
    """
    all_rows = [
        _fixture_row(
            1000 + i,
            f"2026-0{1 + i // 3}-{1 + (i % 3) * 9:02d}T18:00:00+00:00",
            100,
            200 + i,
        )
        for i in range(9)
    ]

    def fixtures(params):
        offset, limit = int(params["offset"]), int(params["limit"])
        return {"count": len(all_rows), "results": all_rows[offset : offset + limit]}

    client, calls = _client(
        monkeypatch,
        tmp_path,
        {
            "/teams/100/fixtures/": fixtures,
            **{
                f"/events/{row['id']}/stats/": STATS_PAYLOAD
                for row in all_rows
            },
        },
    )
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    outcome = fetch_bzzoiro_history(
        "100", "134", RateLimiter(usage_dir=tmp_path / "u"), RunBudget(500),
        last_n=3, mode="l10", as_of_date="2026-08-26", event_id="587706",
    )
    dates = sorted(pv.match_date[:10] for pv in outcome.metrics["corners_total"])
    # The three newest of the nine, not the three oldest.
    assert dates == ["2026-03-01", "2026-03-10", "2026-03-19"]
    # One listing call to learn the total, one to reach its end.
    assert [c[1]["offset"] for c in calls if c[0] == "/teams/100/fixtures/"] == [0, 6]


def test_l10_emits_both_the_match_total_and_this_teams_own_side(monkeypatch, tmp_path):
    """Wave 1 and Wave 2 out of one payload: the combined total that lets this
    provider corroborate the others, and the per-side figure that no other
    provider in the roster can supply."""
    rows = [_fixture_row(587701, "2026-08-18T19:00:00+00:00", 100, 134)]
    client, _ = _client(
        monkeypatch,
        tmp_path,
        {
            "/teams/100/fixtures/": lambda p: {"count": 1, "results": rows},
            "/events/587701/stats/": STATS_PAYLOAD,
        },
    )
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    home = fetch_bzzoiro_history(
        "100", "134", RateLimiter(usage_dir=tmp_path / "u"), RunBudget(500),
        last_n=5, mode="l10", as_of_date="2026-08-26", event_id="587706",
    )
    assert home.metrics["corners_total"][0].value == 12  # 5 + 7
    assert home.metrics["corners_for"][0].value == 5  # team 100 was home
    assert home.metrics["cards_for"][0].value == 1
    assert home.metrics["fouls_for"][0].value == 12
    # _fixture_row's default score is home 1, away 0.
    assert home.metrics["goals_total"][0].value == 1
    assert home.metrics["goals_for"][0].value == 1
    assert home.metrics["goals_against"][0].value == 0


def test_l10_emits_half_goals_and_half_corners_when_the_fixture_has_them(monkeypatch, tmp_path):
    """docs/PLAN_BOGATE_STATYSTYKI.md Faza 3: half-time goals ride on the
    fixture's own home_score_ht/away_score_ht (no /stats/ involved), while
    half corners/cards/shots come out of the same /stats/ payload the
    full-match figures already use -- both for zero extra calls."""
    rows = [
        _fixture_row(
            587701, "2026-08-18T19:00:00+00:00", 100, 134,
            home_score_ht=1, away_score_ht=0,
        )
    ]
    client, _ = _client(
        monkeypatch,
        tmp_path,
        {
            "/teams/100/fixtures/": lambda p: {"count": 1, "results": rows},
            "/events/587701/stats/": STATS_PAYLOAD,
        },
    )
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    home = fetch_bzzoiro_history(
        "100", "134", RateLimiter(usage_dir=tmp_path / "u"), RunBudget(500),
        last_n=5, mode="l10", as_of_date="2026-08-26", event_id="587706",
    )
    # _fixture_row's final score is home 1, away 0; HT is also home 1, away 0
    # here, so the second half is scoreless.
    assert home.metrics["goals_1h_total"][0].value == 1
    assert home.metrics["goals_2h_total"][0].value == 0
    assert home.metrics["goals_1h_for"][0].value == 1
    assert home.metrics["goals_2h_for"][0].value == 0
    # Straight from STATS_PAYLOAD's first_half/second_half corner_kicks.
    assert home.metrics["corners_1h_total"][0].value == 7  # 3 + 4
    assert home.metrics["corners_1h_for"][0].value == 3  # team 100 was home
    assert home.metrics["corners_2h_total"][0].value == 5  # 2 + 3
    assert home.metrics["corners_2h_for"][0].value == 2


def test_l10_without_a_half_time_score_emits_no_half_goals(monkeypatch, tmp_path):
    """Most of the roster never carries home_score_ht/away_score_ht -- absent
    is absent, not a half assumed to be 0-0."""
    rows = [_fixture_row(587701, "2026-08-18T19:00:00+00:00", 100, 134)]
    client, _ = _client(
        monkeypatch,
        tmp_path,
        {
            "/teams/100/fixtures/": lambda p: {"count": 1, "results": rows},
            "/events/587701/stats/": STATS_PAYLOAD,
        },
    )
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    home = fetch_bzzoiro_history(
        "100", "134", RateLimiter(usage_dir=tmp_path / "u"), RunBudget(500),
        last_n=5, mode="l10", as_of_date="2026-08-26", event_id="587706",
    )
    assert "goals_1h_total" not in home.metrics
    assert "goals_2h_total" not in home.metrics


def test_the_away_side_gets_its_own_figures_not_the_home_ones(monkeypatch, tmp_path):
    """The same historical match, read for the other team. If the side lookup
    were wrong this would silently report Lyon's five corners as Fenerbahçe's."""
    rows = [_fixture_row(587701, "2026-08-18T19:00:00+00:00", 100, 134)]
    client, _ = _client(
        monkeypatch,
        tmp_path,
        {
            "/teams/134/fixtures/": lambda p: {"count": 1, "results": rows},
            "/events/587701/stats/": STATS_PAYLOAD,
        },
    )
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    away = fetch_bzzoiro_history(
        "134", "100", RateLimiter(usage_dir=tmp_path / "u"), RunBudget(500),
        last_n=5, mode="l10", as_of_date="2026-08-26", event_id="587706",
    )
    assert away.metrics["corners_for"][0].value == 7
    assert away.metrics["corners_total"][0].value == 12
    # The same 1-0 match, read for the away side: goals_for is the away
    # score, not the home one.
    assert away.metrics["goals_for"][0].value == 0
    assert away.metrics["goals_against"][0].value == 1


def test_h2h_never_emits_a_per_team_metric(monkeypatch, tmp_path):
    """An H2H bucket carries no marker for which side a value belongs to, so a
    "_for" value there would mix the two teams' samples in the one place it
    could not be noticed."""
    payload = dict(_fixture_row(587706, "2026-08-26T19:00:00+00:00", 100, 134))
    payload["head_to_head"] = {
        "recent_matches": [
            {
                "event_id": 587701,
                "date": "2026-08-18T19:00:00+00:00",
                "home": "Fenerbahçe",
                "away": "Olympique Lyonnais",
                "score": "1-1",
                "home_team_id": 134,
                "away_team_id": 100,
                "home_score": 1,
                "away_score": 1,
            }
        ]
    }
    client, _ = _client(
        monkeypatch,
        tmp_path,
        {"/events/587706/": payload, "/events/587701/stats/": STATS_PAYLOAD},
    )
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    outcome = fetch_bzzoiro_history(
        "100", "134", RateLimiter(usage_dir=tmp_path / "u"), RunBudget(500),
        mode="h2h", as_of_date="2026-08-26", event_id="587706",
    )
    assert "corners_total" in outcome.metrics
    assert not [name for name in outcome.metrics if name.endswith("_for")]
    assert "goals_against" not in outcome.metrics
    # The h2h meeting itself: 1-1.
    assert outcome.metrics["goals_total"][0].value == 2
    # head_to_head.recent_matches carries no home_score_ht/away_score_ht
    # (unlike /teams/{id}/fixtures/), so h2h never gets half-time goals --
    # same limitation as goals_for/goals_against above.
    assert "goals_1h_total" not in outcome.metrics
    assert "goals_2h_total" not in outcome.metrics


def test_unplayed_history_is_one_counted_line_not_a_gap_each(monkeypatch, tmp_path):
    """A fixture the provider covers but published no stats for is coverage, not
    failure -- in practice pre-season friendlies, four of Lyon's newest ten.
    One gap each buried the real gaps under noise."""
    rows = [
        _fixture_row(900 + i, f"2026-07-{1 + i:02d}T18:00:00+00:00", 100, 300 + i)
        for i in range(3)
    ]
    client, _ = _client(
        monkeypatch,
        tmp_path,
        {"/teams/100/fixtures/": lambda p: {"count": 3, "results": rows}},
    )

    def _empty(event_id):
        return SourceOperationResult(
            status=SourceResultStatus.SCHEMA_ERROR,
            provider="bzzoiro",
            operation="detailed_metrics",
            error_code="statistics_empty",
        )

    monkeypatch.setattr(client, "get_statistics_result", _empty)
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    outcome = fetch_bzzoiro_history(
        "100", "134", RateLimiter(usage_dir=tmp_path / "u"), RunBudget(500),
        last_n=3, mode="l10", as_of_date="2026-08-26", event_id="587706",
    )
    # Goals ride on the fixture listing's own score (here 1-0 on all three),
    # never on the /stats/ payload that came back empty -- so a match with a
    # result but no published stats is coverage for goals even though it is
    # still a gap for every metric that lives in /stats/.
    assert set(outcome.metrics) == {"goals_total", "goals_for", "goals_against"}
    assert all(v.value == 1.0 for v in outcome.metrics["goals_total"])
    assert all(v.value == 1.0 for v in outcome.metrics["goals_for"])
    assert all(v.value == 0.0 for v in outcome.metrics["goals_against"])
    assert len(outcome.data_gaps) == 1
    assert "3 of 3" in outcome.data_gaps[0]


# --- player props ---------------------------------------------------------

PLAYER_HISTORY = {
    "count": 4,
    "results": [
        # Started: counts.
        {
            "event_id": 587701, "team_id": 100, "minutes_played": 90, "rating": 6.3,
            "total_shots": 4, "shots_on_target": 1, "fouls": 2, "was_fouled": 2,
            "yellow_card": 1, "red_card": 0,
        },
        # An unused substitute: a box score of zeroes.
        {
            "event_id": 210444, "team_id": 100, "minutes_played": 0, "rating": None,
            "total_shots": 0, "shots_on_target": 0, "fouls": 0, "was_fouled": 0,
            "yellow_card": 0, "red_card": 0,
        },
        {
            "event_id": 220447, "team_id": 100, "minutes_played": 61, "rating": 7.1,
            "total_shots": 3, "shots_on_target": 2, "fouls": 1, "was_fouled": 0,
            "yellow_card": 0, "red_card": 1,
        },
    ],
}


def test_bench_appearances_are_dropped_from_the_prop_sample(monkeypatch, tmp_path):
    """An unused substitute's box score is all zeroes. Counting it makes every
    UNDER prop look like a lock -- the same defect that mapping one player's
    aces onto aces_total produced for tennis."""
    client, _ = _client(monkeypatch, tmp_path, {"/players/2190/stats/": PLAYER_HISTORY})
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    outcome = fetch_bzzoiro_player_history(
        "2190", RateLimiter(usage_dir=tmp_path / "u"), RunBudget(500),
        as_of_date="2026-08-26", exclude_event_id="587706",
    )
    shots = [pv.value for pv in outcome.metrics["player_total_shots"]]
    assert sorted(shots) == [3.0, 4.0]
    assert 0.0 not in shots


def test_card_prop_counts_any_card_not_only_yellows(monkeypatch, tmp_path):
    """"Player to be Carded" settles yes on a straight red. Pricing it off
    yellows alone reports a carded player as not carded in exactly the matches
    where the card was most obvious."""
    client, _ = _client(monkeypatch, tmp_path, {"/players/2190/stats/": PLAYER_HISTORY})
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    outcome = fetch_bzzoiro_player_history(
        "2190", RateLimiter(usage_dir=tmp_path / "u"), RunBudget(500),
        as_of_date="2026-08-26", exclude_event_id="587706",
    )
    by_match = {pv.match_id: pv.value for pv in outcome.metrics["player_cards"]}
    assert by_match["587701"] == 1.0  # one yellow
    assert by_match["220447"] == 1.0  # one red, no yellow


def test_player_history_costs_one_call(monkeypatch, tmp_path):
    """The whole point of this endpoint: the box scores arrive inline and
    newest-first, so there is no listing-then-fetch fan-out and no ascending
    offset dance."""
    client, calls = _client(
        monkeypatch, tmp_path, {"/players/2190/stats/": PLAYER_HISTORY}
    )
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    fetch_bzzoiro_player_history(
        "2190",
        RateLimiter(usage_dir=tmp_path / "u"),
        RunBudget(500),
        as_of_date="2026-08-26",
    )
    assert len(calls) == 1
    assert calls[0][1]["date_to"] == "2026-08-26"


def test_dates_and_opponents_come_from_the_match_context(monkeypatch, tmp_path):
    """Box-score rows carry neither. An appearance outside the context map is
    kept undated rather than dropped: a prop's whole value is its sample."""
    client, _ = _client(monkeypatch, tmp_path, {"/players/2190/stats/": PLAYER_HISTORY})
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    outcome = fetch_bzzoiro_player_history(
        "2190", RateLimiter(usage_dir=tmp_path / "u"), RunBudget(500),
        as_of_date="2026-08-26",
        match_context={"587701": ("2026-08-18T19:00:00+00:00", "Fenerbahçe")},
    )
    by_match = {pv.match_id: pv for pv in outcome.metrics["player_total_shots"]}
    assert by_match["587701"].opponent == "Fenerbahçe"
    assert by_match["587701"].match_date.startswith("2026-08-18")
    assert by_match["220447"].match_date == ""
    assert by_match["220447"].opponent == "unknown"


# --- wiring ---------------------------------------------------------------


def test_run_budget_is_raised_for_bzzoiro_only():
    """At the shared 100-call default this provider runs dry after three or four
    events -- the exact 6-of-181 outcome it was added to fix.

    Since the PRO upgrade this is also the *only* bound on it: the football
    product publishes no daily ceiling, so API_DAILY_LIMITS has no entry and the
    daily limiter treats it as unlimited. The override therefore has to be set
    where it cannot bind a real day while still terminating a loop.
    """
    budget = RunBudget(limit=100)
    override = RUN_BUDGET_OVERRIDES["bzzoiro"]
    assert budget.limit_for("bzzoiro") == override
    assert budget.limit_for("highlightly") == 100

    # At ~30 calls an event, the ceiling must clear a full day's slate (150-180
    # fixtures) with room to spare, or it is rationing rather than guarding.
    assert override // 30 > 400

    # An operator passing a bigger budget meant to raise the ceiling, not lower
    # this provider's.
    assert RunBudget(limit=override + 5000).limit_for("bzzoiro") == override + 5000
    assert RunBudget(limit=50).limit_for("bzzoiro") == override


def test_the_key_is_read_from_bzzorio_key(monkeypatch, tmp_path):
    """The provider is spelled bzzoiro and the key it issues is BZZORIO_KEY.
    Deriving one from the other -- which every other client here can do -- gives
    the wrong variable name and an authentication error that reads as an
    upstream problem."""
    monkeypatch.setenv("BZZORIO_KEY", "from-env")
    assert BzzoiroClient(RateLimiter(usage_dir=tmp_path / "u")).api_key == "from-env"


def test_the_auth_header_is_a_token_scheme(tmp_path):
    client = BzzoiroClient(rate_limiter=RateLimiter(usage_dir=tmp_path / "u"))
    client.api_key = "abc"
    assert client._build_headers()["Authorization"] == "Token abc"


def test_football_has_no_local_daily_cap_since_the_pro_upgrade():
    """No entry means unlimited to this limiter, the same treatment ESPN gets.

    The PRO plan stopped sending rate-limit headers on the football product
    entirely (verified live 2026-08-28 across /leagues/, /events/,
    /events/{id}/stats/ and /coverage/), so the old 7000 was a brake measured
    against a ceiling that no longer exists -- it capped a run at ~230 fixtures
    for no reason the provider was asking for. Reimposing one is a .env
    decision, not a code one.
    """
    assert "bzzoiro" not in API_DAILY_LIMITS
    limit, window = RateLimiter()._effective_limit("bzzoiro")
    assert limit is None


def test_quota_override_env_var_matches_the_provider_name():
    """The key is BZZORIO_KEY and the provider is bzzoiro; the override is
    derived from the provider name, so the two genuinely differ."""
    assert limit_env_var("bzzoiro") == "BET_LIMIT_BZZOIRO"


def _event(**overrides):
    kwargs = dict(
        event_id="evt",
        sport="football",
        competition="Champions League",
        home_team="Olympique Lyonnais",
        away_team="Fenerbahçe",
        start_time="2026-08-26T19:00:00+00:00",
        source_ids={"bzzoiro": "587706"},
        provider_team_ids={"bzzoiro": {"home": "100", "away": "134"}},
        identity_confidence="CONFIRMED",
        status="ACTIVE",
    )
    kwargs.update(overrides)
    return EventRecord(**kwargs)


@pytest.mark.parametrize(
    "overrides",
    [
        {"provider_team_ids": {}},
        {"source_ids": {}},
        {
            "source_ids": {"highlightly": "9"},
            "provider_team_ids": {"highlightly": {"home": "1", "away": "2"}},
        },
    ],
)
def test_no_bzzoiro_tasks_without_both_native_ids(overrides):
    """The l10 slots need the team ids and the h2h slot needs the fixture id.
    An event another source found alone has neither, and building tasks anyway
    spends calls to receive an authentication-shaped error."""
    tasks = _build_tasks(_event(**overrides))
    assert not [t for t in tasks if t.provider == "bzzoiro"]


def test_bzzoiro_tasks_cover_all_three_slots():
    tasks = _build_tasks(_event())
    slots = {t.slot for t in tasks if t.provider == "bzzoiro"}
    assert slots == {"team_a", "team_b", "h2h"}


def test_dossier_carries_team_names_for_the_per_team_rows():
    """ANALYZE's only input is the dossier file (run_analyze.py takes --dossier
    and nothing else), so a per-team row cannot look its team up later."""
    buckets = {
        "team_a": FetchOutcome(),
        "team_b": FetchOutcome(),
        "h2h": FetchOutcome(),
    }
    dossier = _dossier_for_event(_event(), buckets)
    assert dossier.team_a_name == "Olympique Lyonnais"
    assert dossier.team_b_name == "Fenerbahçe"


# --- analyze --------------------------------------------------------------


def _day(i: int) -> str:
    """A distinct calendar day per observation. The collapse in analyze.py keys
    on (bucket, day) because a side plays at most one match a day, so a fixture
    that stamps one date on six matches describes something impossible and
    collapses to a single observation."""
    return f"2026-08-{i + 1:02d}"


def _pv(value, match_id, provider="bzzoiro", date="2026-08-01"):
    return ProviderValue(
        provider=provider, match_id=match_id, match_date=date,
        opponent="Opponent FC", value=value, observed_at="2026-08-01T00:00:00+00:00",
    )


def _team_dossier():
    return EventDossierV1(
        event_id="evt",
        sport="football",
        team_a_name="Olympique Lyonnais",
        team_b_name="Fenerbahçe",
        metrics={
            "corners_for": MetricObservation(
                canonical_name="corners_for",
                # Team A always well over 4.5, team B always well under it.
                team_a_l10=[_pv(9.0, f"a{i}", date=_day(i)) for i in range(6)],
                team_b_l10=[_pv(1.0, f"b{i}", date=_day(i)) for i in range(6)],
            )
        },
        readiness="PARTIAL",
    )


def test_per_team_rows_are_two_samples_not_one_pooled_one():
    """Pooling the sides the way a match total is pooled would build one
    twelve-match sample out of two different teams -- a number describing
    neither of them, at twice the apparent evidence."""
    rows = [r for r in analyze_dossier(_team_dossier()) if r.market == "corners_for"]
    assert rows

    over_45 = {r.team_name: r for r in rows if r.line == 4.5 and r.direction == "OVER"}
    assert set(over_45) == {"Olympique Lyonnais", "Fenerbahçe"}
    assert over_45["Olympique Lyonnais"].hit_rate == 1.0
    assert over_45["Fenerbahçe"].hit_rate == 0.0
    # Six each, never twelve.
    assert {r.sample_size for r in over_45.values()} == {6}


def test_a_per_team_row_always_names_its_team():
    rows = analyze_dossier(_team_dossier())
    for row in rows:
        if row.market.endswith("_for"):
            assert row.team_name


def test_per_team_row_is_dropped_when_the_dossier_cannot_name_the_team():
    """"corners_for OVER 4.5" naming nobody is not a bet, and two such rows for
    one event are indistinguishable."""
    dossier = _team_dossier().model_copy(
        update={"team_a_name": None, "team_b_name": None}
    )
    assert not [r for r in analyze_dossier(dossier) if r.market == "corners_for"]


def test_player_rows_carry_the_player_and_which_xi_they_came_from():
    """A prop off a predicted XI has the same arithmetic and a weaker premise,
    and the row is the only place that difference can be recorded."""
    dossier = EventDossierV1(
        event_id="evt",
        sport="football",
        team_a_name="Olympique Lyonnais",
        team_b_name="Fenerbahçe",
        lineup_status="predicted",
        player_metrics=[
            PlayerMetricObservation(
                player_id="2190",
                player_name="Loïs Openda",
                team_side="home",
                canonical_name="player_total_shots",
                l10=[
                    _pv(float(v), f"p{i}", date=_day(i))
                    for i, v in enumerate([3, 2, 4, 1, 2, 3])
                ],
            )
        ],
        readiness="PARTIAL",
    )
    rows = [r for r in analyze_dossier(dossier) if r.market == "player_total_shots"]
    assert rows
    for row in rows:
        assert row.player_id == "2190"
        assert row.player_name == "Loïs Openda"
        assert row.lineup_status == "predicted"
        assert row.team_name == "Olympique Lyonnais"

    over_15 = next(r for r in rows if r.line == 1.5 and r.direction == "OVER")
    assert (over_15.hits, over_15.sample_size) == (5, 6)


def test_a_prop_on_an_unavailable_player_never_reaches_a_row():
    """docs/PLAN_BOGATE_STATYSTYKI.md Faza 4b: a prop on somebody injured is
    void, not losing, and the filter must be in code -- not left to whoever
    reads the sheet to cross-check against squad_availability by hand."""
    from bet.simple_stats.contracts import SquadAvailability

    dossier = EventDossierV1(
        event_id="evt",
        sport="football",
        team_a_name="Olympique Lyonnais",
        team_b_name="Fenerbahçe",
        lineup_status="confirmed",
        squad_availability=[
            SquadAvailability(
                provider_team_id="100",
                side="home",
                unavailable_count=1,
                unavailable=[{"provider_player_id": "2190", "player_name": "Loïs Openda"}],
            )
        ],
        player_metrics=[
            PlayerMetricObservation(
                player_id="2190",
                player_name="Loïs Openda",
                team_side="home",
                canonical_name="player_total_shots",
                l10=[_pv(float(v), f"p{i}", date=_day(i)) for i, v in enumerate([3, 2, 4, 1, 2, 3])],
            ),
            PlayerMetricObservation(
                player_id="9999",
                player_name="Someone Else",
                team_side="home",
                canonical_name="player_total_shots",
                l10=[_pv(float(v), f"q{i}", date=_day(i)) for i, v in enumerate([3, 2, 4, 1, 2, 3])],
            ),
        ],
        readiness="PARTIAL",
    )
    rows = [r for r in analyze_dossier(dossier) if r.market == "player_total_shots"]
    assert rows
    assert all(r.player_id != "2190" for r in rows)
    assert any(r.player_id == "9999" for r in rows)


def test_a_match_total_row_names_neither_a_team_nor_a_player():
    """The three families are told apart by the row's own fields, so a match
    total must leave both unset."""
    dossier = EventDossierV1(
        event_id="evt",
        sport="football",
        metrics={
            "corners_total": MetricObservation(
                canonical_name="corners_total",
                team_a_l10=[
                    _pv(float(v), f"m{i}", date=_day(i))
                    for i, v in enumerate([8, 9, 10, 11, 12, 9])
                ],
            )
        },
        readiness="PARTIAL",
    )
    rows = [r for r in analyze_dossier(dossier) if r.market == "corners_total"]
    assert rows
    assert all(r.team_name is None and r.player_id is None for r in rows)


def test_props_alone_are_partial_so_they_are_not_discarded_at_analyze():
    """ANALYZE drops a BLOCKED dossier whole, so calling a props-only dossier
    BLOCKED would throw away the twenty calls of per-player history the run just
    paid for -- on exactly the events where a prop is the only read left. It is
    still not READY: that tier means two providers agree on three priority
    metrics, and one striker's shot history is neither."""
    buckets = {
        "team_a": FetchOutcome(),
        "team_b": FetchOutcome(),
        "h2h": FetchOutcome(),
    }
    props = SimpleNamespace(
        lineup_status="confirmed",
        observations=[
            PlayerMetricObservation(
                player_id="1", player_name="P", team_side="home",
                canonical_name="player_total_shots", l10=[_pv(3.0, "x")],
            )
        ],
        data_gaps=[],
    )
    dossier = _dossier_for_event(_event(), buckets, None, props)
    assert dossier.readiness == "PARTIAL"
    assert dossier.player_metrics
    assert [r.market for r in analyze_dossier(dossier)] == ["player_total_shots"] * 6

    # Without props the same empty dossier is still BLOCKED.
    assert _dossier_for_event(_event(), buckets).readiness == "BLOCKED"
