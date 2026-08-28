"""Bzzoiro odds and predictions: the parsers, and the rules they must not break.

Every payload here was captured live from sports.bzzoiro.com on 2026-08-28
(SK Rapid Wien - Heart of Midlothian, event 587902, Conference League) and
trimmed to the fields under test. Four live findings drive the shapes below and
are asserted rather than assumed, because each one contradicts what the endpoint
names suggest:

* ``/events/{id}/odds/`` -- the endpoint whose name reads like "this event's
  odds" -- carries **no corners market at all**, only 1x2, goals over/under
  and BTTS;
* ``/odds/best/`` is scoped by date range, not by event (one response held 313
  unrelated fixtures), so it is not a per-event best-price lookup;
* filtering an event's corners quotes by ``is_max_quote=true`` returned zero
  rows for an event with twelve, so the provider's own best-price flag is not
  maintained on this feed;
* ``/odds/comparison/`` answered 200 with 26 bookmakers on this account, so the
  "Football Unlimited" entitlement is live -- and the 403 path is tested anyway,
  because an entitlement is a billing state and billing states lapse.

No test here touches the network.
"""
import json as _json
from datetime import datetime, timezone

import pytest

from bet.api_clients.bzzoiro import BzzoiroClient
from bet.api_clients.rate_limiter import RateLimiter
from bet.integration.source_result import SourceOperationResult, SourceResultStatus
from bet.simple_stats import market_context
from bet.simple_stats.contracts import (
    EventListV1,
    EventMarketContext,
    EventRecord,
    MarketContextV1,
    MarketOddsLine,
    ModelPrediction,
    StatsSheetRow,
    StatsSheetV1,
)
from bet.simple_stats.providers import RunBudget

# --- live-shaped payloads -------------------------------------------------

ODDS_PAYLOAD = {
    "count": 5,
    "results": [
        {
            "id": 1, "event_id": 587902, "market": "total_corners", "outcome": "over",
            "line": 8.5, "push": None, "outcome_name": "Over 8.50",
            "bookmaker_slug": "unibet", "bookmaker_name": "Unibet",
            "decimal_odds": 1.38, "implied_probability": 0.7246,
            "movement": "SHORTENING", "is_max_quote": False,
            "updated_at": "2026-08-26T16:38:06Z",
        },
        {
            "id": 2, "event_id": 587902, "market": "total_corners", "outcome": "over",
            "line": 8.5, "push": None, "outcome_name": "Over 8.50",
            "bookmaker_slug": "10bet", "bookmaker_name": "10bet",
            "decimal_odds": 1.44, "implied_probability": 0.6944,
            "movement": "", "is_max_quote": False,
            "updated_at": "2026-08-26T16:38:06Z",
        },
        {
            "id": 3, "event_id": 587902, "market": "total_corners", "outcome": "under",
            "line": 8.5, "push": None, "outcome_name": "Under 8.50",
            "bookmaker_slug": "unibet", "bookmaker_name": "Unibet",
            "decimal_odds": 2.75, "implied_probability": 0.3636,
            "movement": "DRIFTING", "is_max_quote": False,
            "updated_at": "2026-08-26T16:38:06Z",
        },
        # Same market and outcome, a *different* line.
        {
            "id": 4, "event_id": 587902, "market": "total_corners", "outcome": "over",
            "line": 9.5, "push": None, "outcome_name": "Over 9.50",
            "bookmaker_slug": "unibet", "bookmaker_name": "Unibet",
            "decimal_odds": 1.63, "implied_probability": 0.6135,
            "movement": "", "is_max_quote": False,
            "updated_at": "2026-08-26T16:38:06Z",
        },
        # A line-less market, to prove ``line`` stays null rather than becoming 0.
        {
            "id": 5, "event_id": 587902, "market": "1x2", "outcome": "HOME",
            "line": None, "push": None, "outcome_name": "Home",
            "bookmaker_slug": "pinnacle", "bookmaker_name": "Pinnacle",
            "decimal_odds": 1.59, "implied_probability": 0.6289,
            "movement": "SHORTENING", "is_max_quote": False,
            "updated_at": "2026-08-26T16:38:06Z",
        },
    ],
}

CONSENSUS_PAYLOAD = {
    "event_id": 587902,
    "odds": {
        "home_win": 1.57, "draw": 4.18, "away_win": 4.87,
        "over_15_goals": 1.16, "over_25_goals": 1.59, "over_35_goals": 2.45,
        "under_15_goals": 4.7, "under_25_goals": 2.28, "under_35_goals": 1.49,
        "btts_yes": 1.76, "btts_no": 1.97,
    },
    "last_update_at": "2026-08-26T16:38:06Z",
    "next_update_at": None,
    "update_interval_seconds": None,
    "update_reason": "no further updates scheduled",
}

COMPARISON_PAYLOAD = {
    "event_id": 587902,
    "event_date": "2026-08-26T16:45:00Z",
    "league_id": 83,
    "league_name": "Conference League",
    "home_team": "SK Rapid Wien",
    "away_team": "Heart of Midlothian",
    "bookmakers_count": 26,
    "total_odds": 374,
    "markets": {
        "total_corners": {
            "over@8.5": {
                "outcome": "over", "line": 8.5, "outcome_name": "Over 8.50",
                "best_odds": 1.44, "best_bookmaker_slug": "10bet",
                "best_bookmaker_name": "10bet",
                "bookmakers": {
                    "unibet": {"decimal_odds": 1.38, "movement": "SHORTENING",
                               "updated_at": "2026-08-26T16:38:06Z"},
                    "10bet": {"decimal_odds": 1.44, "movement": "",
                              "updated_at": "2026-08-26T16:38:06Z"},
                },
            },
        },
        "asian_handicap": {
            "HOME@-1.75": {
                "outcome": "HOME", "line": -1.75,
                "outcome_name": "SK Rapid Wien -1.75",
                "best_odds": 3.34, "best_bookmaker_slug": "1xbet",
                "best_bookmaker_name": "1xBet",
                "bookmakers": {
                    "1xbet": {"decimal_odds": 3.34, "movement": "SHORTENING",
                              "updated_at": "2026-08-26T17:20:15Z"},
                },
            },
        },
    },
}

PREDICTION_PAYLOAD = {
    "id": 1631,
    "created_at": "2026-08-20T02:15:13Z",
    "event": {"id": 587902, "home_team": "SK Rapid Wien", "away_team": "Heart of Midlothian"},
    "markets": {
        "match_result": {"prob_home": 58.9, "prob_draw": 22.1, "prob_away": 19.0, "predicted": "H"},
        "expected_goals": {"home": 2.1, "away": 1.17},
        "over_under": {"prob_over_15": 80.4, "prob_over_25": 59.1, "prob_over_35": 38.4},
        "btts": {"prob_yes": 54.6},
        "score": {"most_likely": "2-1"},
        "draw_no_bet": {"prob_home": 76.6},
        "corners": {"prob_over_85": 57.5, "prob_over_95": 45.7, "prob_over_105": 33.9},
    },
    "recommendations": {"favorite": "H", "favorite_prob": 58.9, "bet_favorite": False},
    "model": {"confidence": 0.5889, "version": "dc-blend-v1"},
}


def _client(monkeypatch, tmp_path, payloads, *, statuses=None):
    """A BzzoiroClient whose HTTP layer replays ``{endpoint: payload}``.

    ``statuses`` maps an endpoint to a ``SourceOperationResult`` returned instead
    of a 200, which is how the 403 entitlement path is exercised without
    reproducing the shared transport layer's seventeen branches here.
    """
    client = BzzoiroClient(rate_limiter=RateLimiter(usage_dir=tmp_path / "usage"))
    client.api_key = "test-key"
    calls = []

    def _fake(*, endpoint, params, operation, source_event_id=None):
        calls.append((endpoint, dict(params or {})))
        if statuses and endpoint in statuses:
            return statuses[endpoint]
        payload = payloads.get(endpoint)
        if payload is None:
            return SourceOperationResult(
                status=SourceResultStatus.NOT_FOUND, provider="bzzoiro",
                operation=operation, error_code="http_404",
            )
        if callable(payload):
            payload = payload(dict(params or {}))
        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=_json.loads(_json.dumps(payload)),
            provider="bzzoiro", operation=operation, http_status=200,
        )

    monkeypatch.setattr(client, "_request_with_evidence", _fake)
    return client, calls


def _blocked_403():
    return SourceOperationResult(
        status=SourceResultStatus.BLOCKED, provider="bzzoiro",
        operation="odds_comparison", http_status=403, error_code="http_403",
    )


# --- odds -----------------------------------------------------------------


def test_the_best_price_is_computed_per_line_not_read_from_the_provider_flag(
    monkeypatch, tmp_path
):
    """``is_max_quote`` came back false on every quote of an event that plainly
    had a best price, so the flag is not maintained on this feed. Grouping also
    includes the line: the best over-8.5 price is not a claim about over 9.5."""
    client, _ = _client(monkeypatch, tmp_path, {"/odds/": ODDS_PAYLOAD})
    result = client.get_odds_result("587902", market="total_corners")
    assert result.status is SourceResultStatus.SUCCESS

    best = {
        (q["market"], q["outcome"], q["line"]): q
        for q in result.value["quotes"]
        if q["is_best"]
    }
    assert best[("total_corners", "over", 8.5)]["bookmaker_slug"] == "10bet"
    assert best[("total_corners", "over", 8.5)]["price"] == 1.44
    # The lone quote on the next line up is its own group's best, not shadowed
    # by the better price one line down.
    assert best[("total_corners", "over", 9.5)]["price"] == 1.63
    assert best[("total_corners", "under", 8.5)]["price"] == 2.75


def test_a_market_with_no_line_keeps_a_null_line_not_a_zero(monkeypatch, tmp_path):
    """1x2 has no line. Recording 0.0 would make it indistinguishable from a
    real handicap line of zero, which is a different bet entirely."""
    client, _ = _client(monkeypatch, tmp_path, {"/odds/": ODDS_PAYLOAD})
    result = client.get_odds_result("587902")
    one_x_two = [q for q in result.value["quotes"] if q["market"] == "1x2"]
    assert one_x_two and all(q["line"] is None for q in one_x_two)
    assert MarketOddsLine(**one_x_two[0]).line is None


def test_a_quote_the_provider_could_not_link_is_dropped_and_counted(monkeypatch, tmp_path):
    """``event_id`` is documented nullable: a price the provider could not attach
    to a fixture in its own catalogue. Attaching it to whichever event we happened
    to be asking about would invent a price for a match it was never quoted on."""
    payload = {
        "count": 2,
        "results": [
            dict(ODDS_PAYLOAD["results"][0]),
            dict(ODDS_PAYLOAD["results"][1], event_id=None),
        ],
    }
    client, _ = _client(monkeypatch, tmp_path, {"/odds/": payload})
    result = client.get_odds_result("587902")
    assert len(result.value["quotes"]) == 1
    assert result.value["unlinked_count"] == 1


def test_an_unmapped_market_code_is_reported_and_never_raises(monkeypatch, tmp_path):
    """The market list belongs to the live API, which may extend it at any time.
    A new code must surface as a diagnostic, not as a ValidationError that loses
    a betting day -- the opposite of how PROVIDER_NAMES is treated, where an
    unlisted value really is a human's config mistake."""
    payload = {
        "count": 2,
        "results": [
            dict(ODDS_PAYLOAD["results"][0]),
            dict(ODDS_PAYLOAD["results"][0], id=99, market="player_shots_on_target"),
        ],
    }
    client, _ = _client(monkeypatch, tmp_path, {"/odds/": payload})
    result = client.get_odds_result("587902")
    assert result.status is SourceResultStatus.SUCCESS
    assert result.value["unknown_markets"] == ["player_shots_on_target"]
    assert len(result.value["quotes"]) == 1


def test_every_parsed_quote_satisfies_the_contract(monkeypatch, tmp_path):
    """The parser's output is the contract's input, and the contract is strict."""
    client, _ = _client(monkeypatch, tmp_path, {"/odds/": ODDS_PAYLOAD})
    result = client.get_odds_result("587902")
    for quote in result.value["quotes"]:
        assert MarketOddsLine(**quote)


def test_an_event_with_no_quotes_is_valid_empty_not_an_error(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path, {"/odds/": {"count": 0, "results": []}})
    result = client.get_odds_result("587902")
    assert result.status is SourceResultStatus.VALID_EMPTY
    assert result.value["quotes"] == []


# --- consensus odds -------------------------------------------------------


def test_the_consensus_block_carries_no_corners_market(monkeypatch, tmp_path):
    """The reason the corners signal is not sourced from ``/events/{id}/odds/``,
    despite that being the endpoint whose name suggests it. Its block is 1x2,
    goals over/under and BTTS, and nothing else."""
    client, _ = _client(monkeypatch, tmp_path, {"/events/587902/odds/": CONSENSUS_PAYLOAD})
    result = client.get_consensus_odds_result("587902")
    assert result.status is SourceResultStatus.SUCCESS
    keys = result.value["consensus_odds"]
    assert not [k for k in keys if "corner" in k]
    assert keys["over_25_goals"] == 1.59


# --- comparison and the entitlement gate ----------------------------------


def test_the_comparison_grid_flattens_to_one_quote_per_bookmaker(monkeypatch, tmp_path):
    """Outcome keys are codes ("over@8.5"), not team names, so the flattening
    survives a team being renamed. Only the best-priced bookmaker has a display
    name in this payload, and the others are left nameless rather than guessed."""
    client, _ = _client(
        monkeypatch, tmp_path, {"/events/587902/odds/comparison/": COMPARISON_PAYLOAD}
    )
    result = client.get_odds_comparison_result("587902")
    assert result.value["entitlement"] == "ENTITLED"
    assert result.value["bookmakers_count"] == 26

    corners = [q for q in result.value["quotes"] if q["market"] == "total_corners"]
    assert {q["bookmaker_slug"] for q in corners} == {"unibet", "10bet"}
    best = next(q for q in corners if q["is_best"])
    assert (best["bookmaker_slug"], best["bookmaker_name"]) == ("10bet", "10bet")
    assert next(q for q in corners if not q["is_best"])["bookmaker_name"] is None
    for quote in result.value["quotes"]:
        assert MarketOddsLine(**quote)


def test_a_403_is_a_recorded_entitlement_fact_not_a_failure(monkeypatch, tmp_path):
    """A 403 here says something true and stable about the account's billing. It
    will not resolve on a retry and it is not a gap in the provider's data, so
    reporting it as an error would put a permanent billing state into every
    event's data_gaps and drown the retry-eligible failures around it."""
    client, calls = _client(
        monkeypatch, tmp_path, {},
        statuses={"/events/587902/odds/comparison/": _blocked_403()},
    )
    result = client.get_odds_comparison_result("587902")
    assert result.status is SourceResultStatus.SUCCESS
    assert result.value["entitlement"] == "NOT_ENTITLED"
    assert result.value["quotes"] == []
    assert result.error_code == ""
    # One attempt. A 403 is not retryable and retrying it spends a call to be
    # told the same thing.
    assert len(calls) == 1


def test_an_entitled_event_with_no_odds_stays_entitled(monkeypatch, tmp_path):
    """``{"markets": {}}`` is the documented answer for an event nobody has
    priced yet. Reading it as a failed entitlement probe would report the account
    as unentitled on the strength of a quiet fixture."""
    client, _ = _client(
        monkeypatch, tmp_path,
        {"/events/587902/odds/comparison/": dict(COMPARISON_PAYLOAD, markets={})},
    )
    result = client.get_odds_comparison_result("587902")
    assert result.status is SourceResultStatus.VALID_EMPTY
    assert result.value["entitlement"] == "ENTITLED"


def test_a_not_entitled_comparison_leaves_the_odds_feed_untouched(monkeypatch, tmp_path):
    """The two endpoints are independent. Losing the grid must not blank out the
    per-bookmaker quotes that are reachable without the entitlement -- those are
    where the only promotable signal comes from."""
    client, _ = _client(
        monkeypatch, tmp_path, {"/odds/": ODDS_PAYLOAD},
        statuses={"/events/587902/odds/comparison/": _blocked_403()},
    )
    assert client.get_odds_comparison_result("587902").value["entitlement"] == "NOT_ENTITLED"
    assert client.get_odds_result("587902").value["quotes"]


# --- predictions ----------------------------------------------------------


def test_model_probabilities_are_rescaled_to_match_a_price(monkeypatch, tmp_path):
    """The model serves 0-100 and the odds feed serves 0-1. The only thing these
    numbers are ever compared against is an implied probability, so leaving the
    scales apart would read a 58.9% model call as a 5890% disagreement with a
    0.625 price."""
    client, _ = _client(
        monkeypatch, tmp_path, {"/events/587902/prediction/": PREDICTION_PAYLOAD}
    )
    result = client.get_prediction_result("587902")
    prediction = result.value["prediction"]
    assert prediction["prob_home"] == pytest.approx(0.589)
    assert prediction["prob_corners_over_95"] == pytest.approx(0.457)
    # Already 0-1 in the payload, so it must not be divided a second time.
    assert prediction["model_confidence"] == pytest.approx(0.5889)
    assert ModelPrediction(**prediction)


def test_a_null_model_probability_stays_null(monkeypatch, tmp_path):
    """The whole corners block is documented null when the model has neither team
    history nor a market line. 0.5 is the number everyone reaches for, and it is
    indistinguishable from a model that looked at the match and called it even."""
    payload = _json.loads(_json.dumps(PREDICTION_PAYLOAD))
    payload["markets"]["corners"] = None
    payload["markets"]["btts"] = {"prob_yes": None}
    client, _ = _client(monkeypatch, tmp_path, {"/events/587902/prediction/": payload})
    result = client.get_prediction_result("587902")
    prediction = result.value["prediction"]
    assert prediction["prob_corners_over_85"] is None
    assert prediction["prob_corners_over_95"] is None
    assert prediction["prob_corners_over_105"] is None
    assert prediction["prob_btts_yes"] is None
    assert result.value["has_corners"] is False
    assert ModelPrediction(**prediction).prob_corners_over_95 is None


def test_the_model_serves_exactly_three_corner_lines(monkeypatch, tmp_path):
    """8.5, 9.5 and 10.5, and no others. A row on 6.5 or 11.5 corners has no
    model probability at all, and the contract has nowhere to put an
    interpolated one -- which is the point."""
    corner_fields = [f for f in ModelPrediction.model_fields if "corners" in f]
    assert sorted(corner_fields) == [
        "prob_corners_over_105",
        "prob_corners_over_85",
        "prob_corners_over_95",
    ]


# --- collection: budget, entitlement caching, sport scope ------------------


def _event_list(*events):
    return EventListV1(
        run_id="RID-1", generated_at="2026-08-28T00:00:00+00:00",
        date="2026-08-28", sports=["football", "tennis"], events=list(events),
    )


def _football_event(event_id="evt-1", provider_id="587902", **overrides):
    kwargs = dict(
        event_id=event_id, sport="football", competition="Conference League",
        home_team="SK Rapid Wien", away_team="Heart of Midlothian",
        start_time="2026-08-28T16:45:00+00:00",
        source_ids={"bzzoiro": provider_id},
        identity_confidence="CONFIRMED", status="ACTIVE",
    )
    kwargs.update(overrides)
    return EventRecord(**kwargs)


@pytest.fixture(autouse=True)
def _clear_entitlement_cache():
    """Process-wide and account-wide by design, which means one test's probe
    would otherwise answer the next test's run -- and that test would pass while
    asserting nothing."""
    market_context.reset_entitlement_cache()
    yield
    market_context.reset_entitlement_cache()


def _collecting_client(monkeypatch, tmp_path, *, comparison=COMPARISON_PAYLOAD):
    payloads = {
        "/odds/": ODDS_PAYLOAD,
        "/events/587902/odds/": CONSENSUS_PAYLOAD,
        "/events/587902/prediction/": PREDICTION_PAYLOAD,
        "/events/587903/odds/": CONSENSUS_PAYLOAD,
        "/events/587903/prediction/": PREDICTION_PAYLOAD,
    }
    statuses = {}
    if comparison is None:
        statuses["/events/587902/odds/comparison/"] = _blocked_403()
        statuses["/events/587903/odds/comparison/"] = _blocked_403()
    else:
        payloads["/events/587902/odds/comparison/"] = comparison
        payloads["/events/587903/odds/comparison/"] = comparison
    client, calls = _client(monkeypatch, tmp_path, payloads, statuses=statuses)
    monkeypatch.setattr(market_context, "get_client", lambda *a, **k: client)
    return client, calls


def test_tennis_is_out_of_scope_because_it_shares_a_95_a_day_bucket(monkeypatch, tmp_path):
    """Not a coverage decision. bzzoiro-tennis is a separate quota bucket that
    ENRICH already spends against, and roughly six enriched fixtures exhausts it,
    so market context for tennis would come out of the allowance that produces
    tennis's actual statistics."""
    tennis = _football_event(
        event_id="evt-tennis", sport="tennis", competition="Cincinnati (atp_1000)",
        home_team=None, away_team=None, player_one="A", player_two="B",
        source_ids={"bzzoiro-tennis": "9001"},
    )
    assert market_context.eligible_events(_event_list(tennis)) == []


def test_an_event_without_bzzoiros_own_id_is_skipped(monkeypatch, tmp_path):
    """Every endpoint here is keyed by that id. An event some other source found
    alone has nothing to look up, and building calls anyway spends quota to
    receive a 404."""
    foreign = _football_event(event_id="evt-espn", source_ids={"espn-football": "77"})
    assert market_context.eligible_events(_event_list(foreign)) == []


def test_the_entitlement_is_probed_exactly_once_per_run(monkeypatch, tmp_path):
    """It belongs to the subscription, not to a league or a fixture, so one probe
    answers for every event. Re-probing per event would spend a call per fixture
    to be told the same thing."""
    client, calls = _collecting_client(monkeypatch, tmp_path)
    context = market_context.collect_market_context(
        _event_list(_football_event(), _football_event("evt-2", "587903")),
        RateLimiter(usage_dir=tmp_path / "u"),
    )
    assert context.football_unlimited_entitled is True
    # Two events, one comparison call each -- but only one of them was a probe:
    # the second event fetched its own grid without re-establishing entitlement.
    comparison_calls = [c for c in calls if c[0].endswith("/odds/comparison/")]
    assert len(comparison_calls) == 2
    assert all(e.comparison_entitlement == "ENTITLED" for e in context.events)


def test_a_not_entitled_account_stops_calling_the_grid_entirely(monkeypatch, tmp_path):
    """A 403 will not resolve on the next fixture. Asking again, per event, all
    day, spends a call each time to be told the same permanent fact."""
    client, calls = _collecting_client(monkeypatch, tmp_path, comparison=None)
    context = market_context.collect_market_context(
        _event_list(_football_event(), _football_event("evt-2", "587903")),
        RateLimiter(usage_dir=tmp_path / "u"),
    )
    assert context.football_unlimited_entitled is False
    comparison_calls = [c for c in calls if c[0].endswith("/odds/comparison/")]
    assert len(comparison_calls) == 1
    assert all(e.comparison_entitlement == "NOT_ENTITLED" for e in context.events)


def test_losing_the_grid_never_blanks_the_corners_quotes(monkeypatch, tmp_path):
    """The entitlement gates depth, not the signal. If a lapsed subscription also
    emptied the corners quotes, a billing change would silently switch off the
    one column that can move a row."""
    _collecting_client(monkeypatch, tmp_path, comparison=None)
    context = market_context.collect_market_context(
        _event_list(_football_event()), RateLimiter(usage_dir=tmp_path / "u")
    )
    event = context.events[0]
    assert event.comparison_entitlement == "NOT_ENTITLED"
    assert [q for q in event.odds if q.market == "total_corners"]
    assert event.predictions is not None


def test_the_run_budget_stops_the_loop_and_says_so(monkeypatch, tmp_path):
    """Football is uncapped, so this is a runaway guard rather than rationing --
    but when it binds, the artifact must say the data is missing because we
    stopped asking, not because the provider had nothing."""
    _collecting_client(monkeypatch, tmp_path)
    context = market_context.collect_market_context(
        _event_list(_football_event(), _football_event("evt-2", "587903")),
        RateLimiter(usage_dir=tmp_path / "u"),
        budget=RunBudget(limit=2, overrides={}),
    )
    gaps = [gap for event in context.events for gap in event.data_gaps]
    assert any("run call budget exhausted" in gap for gap in gaps)


def test_a_fixture_nobody_priced_is_a_gap_not_a_crash(monkeypatch, tmp_path):
    client, _ = _client(
        monkeypatch, tmp_path,
        {
            "/odds/": {"count": 0, "results": []},
            "/events/587902/odds/": CONSENSUS_PAYLOAD,
            "/events/587902/odds/comparison/": COMPARISON_PAYLOAD,
            "/events/587902/prediction/": PREDICTION_PAYLOAD,
        },
    )
    monkeypatch.setattr(market_context, "get_client", lambda *a, **k: client)
    context = market_context.collect_market_context(
        _event_list(_football_event()), RateLimiter(usage_dir=tmp_path / "u")
    )
    assert context.events[0].odds == []
    assert any("no total_corners quotes" in gap for gap in context.events[0].data_gaps)
