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

from bet.api_clients.bzzoiro import BzzoiroClient, _parse_prediction_row
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


def test_the_day_listing_replaces_the_per_event_prediction_call(monkeypatch, tmp_path):
    """One call for the slate's forecasts instead of one per fixture.

    The saving is the point, but the *substitution* is what has to be safe: the
    prefetched prediction must be the same object the per-event endpoint would
    have produced, which is why both go through ``_parse_prediction_row``.
    """
    listing = {
        "count": 2,
        "results": [
            {"event": {"id": 587902, "event_date": "2026-08-28T18:00:00Z"},
             "markets": PREDICTION_PAYLOAD["markets"],
             "model": PREDICTION_PAYLOAD.get("model", {})},
            {"event": {"id": 587903, "event_date": "2026-08-28T20:00:00Z"},
             "markets": PREDICTION_PAYLOAD["markets"],
             "model": PREDICTION_PAYLOAD.get("model", {})},
        ],
    }
    client, calls = _collecting_client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        client, "get_predictions_list_result",
        lambda *, date, limit=200, offset=0: SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value={"predictions": {
                str(r["event"]["id"]): _parse_prediction_row(r) for r in listing["results"]
            }},
            provider="bzzoiro", operation="model_prediction_listing", http_status=200,
        ),
    )

    context = market_context.collect_market_context(
        _event_list(_football_event(), _football_event("evt-2", "587903")),
        RateLimiter(usage_dir=tmp_path / "u"),
    )

    assert all(event.predictions is not None for event in context.events)
    per_event_calls = [c for c in calls if c[0].endswith("/prediction/")]
    assert per_event_calls == [], "the listing was fetched and the per-event endpoint called anyway"


def test_a_fixture_the_listing_missed_still_falls_back_to_its_own_call(monkeypatch, tmp_path):
    """The listing is an optimisation, not a replacement.

    The model publishes closer to kickoff, so a slate is routinely part-covered.
    A fixture the listing does not carry must still get its forecast.
    """
    client, calls = _collecting_client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        client, "get_predictions_list_result",
        lambda *, date, limit=200, offset=0: SourceOperationResult(
            status=SourceResultStatus.VALID_EMPTY, value={"predictions": {}},
            provider="bzzoiro", operation="model_prediction_listing", http_status=200,
        ),
    )

    context = market_context.collect_market_context(
        _event_list(_football_event()), RateLimiter(usage_dir=tmp_path / "u")
    )

    assert context.events[0].predictions is not None
    assert any(c[0].endswith("/prediction/") for c in calls)


def test_tennis_never_enters_the_per_event_price_loop(monkeypatch, tmp_path):
    """Tennis gets a model and no prices, and this is the half that says "no
    prices".

    ``bzzoiro-tennis`` is a separate quota bucket that ENRICH already spends
    against, and roughly six enriched fixtures exhausts it. Per-event odds would
    cost one call each out of that allowance, so ``eligible_events`` -- which
    gates the four-call-per-fixture loop -- stays football-only.

    Since 2026-08-30 tennis *is* reached, but by exactly one call for the whole
    slate (``_collect_tennis_predictions``), which is a different path and is
    tested in ``test_bzzoiro_bulk_endpoints``.
    """
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


# --- triangulation --------------------------------------------------------


def _row(market="corners_total", line=8.5, direction="OVER", event_id="evt-1", **overrides):
    kwargs = dict(
        event_id=event_id, sport="football", market=market, line=line,
        direction=direction, hits=7, sample_size=10, hit_rate=0.7,
        p_low=0.42, mean=9.8, median=10.0, sources=["bzzoiro"],
        cross_provider_agreement="SINGLE_SOURCE", confidence="MEDIUM",
        data_quality="PARTIAL",
    )
    kwargs.update(overrides)
    return StatsSheetRow(**kwargs)


def _context_for_tests(**overrides):
    kwargs = dict(
        event_id="evt-1",
        provider_event_id="587902",
        odds=[
            MarketOddsLine(market="total_corners", outcome="over", line=8.5,
                           price=1.44, bookmaker_slug="10bet"),
            MarketOddsLine(market="total_corners", outcome="under", line=8.5,
                           price=2.75, bookmaker_slug="unibet"),
        ],
        predictions=ModelPrediction(
            prob_corners_over_85=0.575, prob_corners_over_95=0.457,
            prob_corners_over_105=0.339, model_version="dc-blend-v1",
        ),
        comparison_entitlement="ENTITLED",
    )
    kwargs.update(overrides)
    return EventMarketContext(**kwargs)


def test_no_signal_is_ever_attached_to_a_market_bzzoiro_cannot_price(monkeypatch):
    """The feed publishes fourteen markets and none of them is cards, fouls or
    shots on target, and the model publishes probabilities for none of them
    either. Those rows can never get a real signal, so they must never get a
    fabricated one -- the field stays unset, exactly as on a run without this
    stage."""
    context = _context_for_tests()
    for market in ("cards_total", "fouls_total", "shots_on_target_total", "corners_for"):
        assert market_context.market_signal_for_row(_row(market=market), context) is None


def test_a_line_the_model_never_published_gets_no_interpolated_probability():
    """The model serves 8.5, 9.5 and 10.5. STANDARD_MARKET_LINES also prices
    11.5, and over 10.5 is not weak evidence about over 11.5 -- it is evidence
    about a different bet."""
    context = _context_for_tests(
        odds=[
            MarketOddsLine(market="total_corners", outcome="over", line=11.5, price=3.1),
            MarketOddsLine(market="total_corners", outcome="under", line=11.5, price=1.35),
        ]
    )
    signal = market_context.market_signal_for_row(_row(line=11.5), context)
    assert signal.verdict == "NO_MARKET_DATA"
    assert signal.model_probability is None
    assert "no model probability at line 11.5" in signal.reason


def test_quotes_at_another_line_do_not_answer_this_rows_line():
    """The market has 8.5 and the row is 9.5. Reaching one line over is the
    single easiest way to manufacture agreement, and the two settle differently."""
    context = _context_for_tests()
    signal = market_context.market_signal_for_row(_row(line=9.5), context)
    assert signal.verdict == "NO_MARKET_DATA"
    assert signal.market_implied_probability is None
    assert signal.market_price is None
    assert "no market quote at line 9.5" in signal.reason


def test_the_implied_probability_has_the_overround_removed():
    """1/1.44 is 0.694 and 1/2.75 is 0.364 -- they sum to 1.058, and that 5.8%
    is the bookmaker's margin, not probability. Reporting the raw figure would
    turn the margin itself into agreement, always in the direction of confirming
    whatever the row already says."""
    context = _context_for_tests()
    signal = market_context.market_signal_for_row(_row(line=8.5, direction="OVER"), context)
    raw = 1 / 1.44
    assert signal.market_implied_probability == pytest.approx(raw / (raw + 1 / 2.75))
    assert signal.market_implied_probability < raw
    # The two directions of one line are complementary once de-vigged.
    under = market_context.market_signal_for_row(_row(line=8.5, direction="UNDER"), context)
    assert signal.market_implied_probability + under.market_implied_probability == pytest.approx(1.0)


def test_a_one_sided_line_yields_a_price_but_no_probability():
    """The price is real and worth reporting. A probability derived from it is
    not: with only one leg there is nothing to normalize the margin against."""
    context = _context_for_tests(
        odds=[MarketOddsLine(market="total_corners", outcome="over", line=8.5, price=1.44)]
    )
    signal = market_context.market_signal_for_row(_row(line=8.5), context)
    assert signal.verdict == "NO_MARKET_DATA"
    assert signal.market_price == 1.44
    assert signal.market_implied_probability is None
    assert "one side only" in signal.reason


def test_both_signals_are_required_before_any_verdict():
    """One agreeing number is not triangulation. The model and the market are
    frequently fitted to overlapping information, so a single supporting figure
    is the easiest thing in the world to find for a direction already chosen."""
    no_model = _context_for_tests(predictions=None)
    assert market_context.market_signal_for_row(_row(), no_model).verdict == "NO_MARKET_DATA"
    no_market = _context_for_tests(odds=[])
    assert market_context.market_signal_for_row(_row(), no_market).verdict == "NO_MARKET_DATA"


def test_the_verdict_reads_both_sources_against_this_rows_direction():
    context = _context_for_tests()
    # Model 0.575 over, market ~0.656 over: both back OVER 8.5.
    assert market_context.market_signal_for_row(_row(direction="OVER"), context).verdict == "CONFIRMS"
    # The same two numbers, read for the opposite side, must contradict it.
    assert market_context.market_signal_for_row(_row(direction="UNDER"), context).verdict == "CONTRADICTS"


def test_a_disagreement_between_model_and_market_is_split_not_a_lean():
    """The model says under, the market says over. Picking whichever agrees with
    the row is the whole failure mode this column exists to prevent."""
    context = _context_for_tests(
        predictions=ModelPrediction(prob_corners_over_85=0.40, model_version="dc-blend-v1")
    )
    signal = market_context.market_signal_for_row(_row(direction="OVER"), context)
    assert signal.verdict == "SPLIT"
    assert signal.model_probability == pytest.approx(0.40)
    assert signal.market_implied_probability > 0.5


def test_the_column_names_both_sources_it_used():
    """Which model version and which bookmaker, so a reader can check the claim
    rather than take the verdict's word for it."""
    context = _context_for_tests()
    signal = market_context.market_signal_for_row(_row(), context)
    assert signal.sources == ["model:dc-blend-v1", "market:10bet"]
    # The quoted price is the best available across the feed, and the column
    # names whose it is -- there is no superbet among the 88 books bzzoiro
    # tracks, so it is never the operator's own screen price.
    assert signal.market_price == 1.44
    assert signal.market_bookmaker == "10bet"


def test_an_event_with_no_market_context_is_told_so_rather_than_left_blank():
    signal = market_context.market_signal_for_row(_row(event_id="evt-missing"), None)
    assert signal.verdict == "NO_MARKET_DATA"
    assert signal.reason == "no market context for this event"


# --- attachment -----------------------------------------------------------


def _sheet(*rows):
    return StatsSheetV1(
        run_id="RID-1", date="2026-08-28",
        generated_at="2026-08-28T00:00:00+00:00", rows=list(rows),
    )


def _context_artifact(*events):
    return MarketContextV1(
        run_id="RID-1", date="2026-08-28",
        generated_at="2026-08-28T00:00:00+00:00",
        football_unlimited_entitled=True, events=list(events),
    )


def test_attaching_the_column_changes_exactly_one_field():
    """The invariant this whole design rests on, asserted field by field: a rule
    that is only written down is a rule that erodes. Every number a row uses to
    make its claim is computed with no knowledge that this column exists, and
    attaching it must not be able to touch one of them."""
    rows = [_row(), _row(market="cards_total", line=4.5), _row(line=9.5, direction="UNDER")]
    before = _sheet(*rows)
    after = market_context.attach_market_context_column(
        before, _context_artifact(_context_for_tests())
    )

    assert len(after.rows) == len(before.rows)
    for original, updated in zip(before.rows, after.rows):
        for field in StatsSheetRow.model_fields:
            if field == "market_signal":
                continue
            assert getattr(updated, field) == getattr(original, field), field


def test_row_order_is_preserved_because_the_ranking_is_statistical():
    """A bookmaker does not get a vote in how the sheet is sorted. A reader who
    wants to order by market agreement does it on screen, where the reordering is
    visible."""
    rows = [_row(event_id=f"evt-{i}", p_low=0.4 + i / 100) for i in range(4)]
    before = _sheet(*rows)
    after = market_context.attach_market_context_column(
        before, _context_artifact(_context_for_tests())
    )
    assert [r.event_id for r in after.rows] == [r.event_id for r in before.rows]


def test_a_sheet_with_no_market_context_is_still_a_complete_sheet():
    before = _sheet(_row())
    after = market_context.attach_market_context_column(before, _context_artifact())
    assert after.rows[0].market_signal.verdict == "NO_MARKET_DATA"
    assert after.rows[0].p_low == before.rows[0].p_low


def test_this_stage_slices_the_slate_in_enrichs_own_order():
    """Both stages take a --max-events slice, and taking them in different orders
    wastes both budgets. On the first live run of this stage (2026-08-28,
    --max-events 12) ENRICH ranked by identity confidence then kickoff while this
    stage took event-list order: the slices overlapped on three of twelve
    fixtures, so three quarters of the calls bought context for events that
    produced no row, and three quarters of the rows that could have carried a
    signal read NO_MARKET_DATA."""
    from bet.simple_stats.enrich import _enrichment_priority

    # Listed worst-first, so event-list order and priority order disagree.
    fuzzy_late = _football_event(
        "evt-fuzzy", "1", identity_confidence="FUZZY_MATCHED",
        start_time="2026-08-28T21:00:00+00:00", provider_team_ids={},
    )
    confirmed_early = _football_event(
        "evt-confirmed", "2", identity_confidence="CONFIRMED",
        start_time="2026-08-28T18:00:00+00:00",
        provider_team_ids={"bzzoiro": {"home": "100", "away": "134"}},
    )
    # Clock pinned before both kickoffs -- the same instant the second assertion
    # below already used. Unpinned, this first assertion held all morning on
    # 2026-08-28 and began failing at 18:00 UTC that day, when "evt-confirmed"
    # kicked off and _enrichment_priority correctly demoted it behind the later
    # "evt-fuzzy". What is under test is the corroboration tie-break, not the
    # started-fixture demotion, and a suite whose answer changes with the wall
    # clock cannot tell a regression from an afternoon.
    now = datetime(2026, 8, 28, 12, tzinfo=timezone.utc)
    ordered = market_context.eligible_events(
        _event_list(fuzzy_late, confirmed_early), now=now
    )
    assert [e.event_id for e in ordered] == ["evt-confirmed", "evt-fuzzy"]

    # And it is ENRICH's ranking, not a second one that happens to agree today.
    assert ordered == sorted(ordered, key=lambda e: _enrichment_priority(e, now))
