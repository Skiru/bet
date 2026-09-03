"""2026-09-03: the card market was priced against yellows, not booking points.

The audit row was Grêmio-Internacional ``cards_total`` 8.5 UNDER at 20/20, which
read as +20% EV. Superbet's "Liczba kartek" settles a straight red as 2 and a
player dismissed for a second yellow as 3 in total; our ``cards_total`` is every
provider's ``yellow_cards`` aliased onto one name. In the quantity the book
settles, the last three Grenals were 10, 9 and 4 -- two of the three OVER 8.5 --
against the 7, 7 and 4 the sheet printed.

Every payload below was captured live from sports.bzzoiro.com on 2026-09-03 and
trimmed to the fields under test. The three fixtures are the H2H the audit read:

    event   date        yellows  reds                cards_total  points
    2606    2025-09-21  7        1 straight + 1 2Y   7            10
    7099    2026-04-11  7        1 straight          7             9
    587786  2026-08-27  4        none                4             4

10 rather than the 11 the handoff note predicted, and the arithmetic is in
``test_grenal_h2h_reads_ten_nine_four``: bzzoiro's ``yellow_cards`` already
counts the second yellow of a dismissal, and its ``red_cards`` already counts
that dismissal, so charging the pair 2 + 2 double-counts by one. It also
excludes the card shown to Mano Menezes, which is what a manager's card is
worth in this market -- nothing.

No network: the whole point of a regression test for a provider-shaped defect is
that it can be re-run months from now, and ``tests-could-spend-the-quota`` is
why it must not touch a rate limiter that writes to the production counter.
"""
import json

import pytest

from bet.api_clients.bzzoiro import BzzoiroClient
from bet.api_clients.rate_limiter import RateLimiter
from bet.integration.source_result import SourceOperationResult, SourceResultStatus
from bet.simple_stats import providers
from bet.simple_stats.contracts import COUNT_METRICS
from bet.simple_stats.providers import (
    _BZZOIRO_FOR_ALIASES,
    _BZZOIRO_TOTAL_ALIASES,
    _ESPN_FOOTBALL_ALIASES,
    _HIGHLIGHTLY_NORMALIZED_ALIASES,
    _bzzoiro_match_stats,
    card_points,
    reset_bzzoiro_incidents_cache,
    reset_bzzoiro_stats_cache,
)
from bet.simple_stats.settle import settle_row
from bet.simple_stats.superbet_offer import classify_market
from bet.stats.market_ranking import standard_market_lines

# --- live-shaped payloads, captured 2026-09-03 ----------------------------

STATS = {
    # Internacional 2-3 Grêmio, 2025-09-21. Home is Internacional.
    "2606": {
        "event_id": 2606,
        "stats": {
            "home": {"fouls": 18, "corner_kicks": 8, "yellow_cards": 5, "red_cards": 1},
            "away": {"fouls": 15, "corner_kicks": 1, "yellow_cards": 2, "red_cards": 1},
        },
    },
    # Internacional 0-0 Grêmio, 2026-04-11.
    "7099": {
        "event_id": 7099,
        "stats": {
            "home": {"yellow_cards": 4, "red_cards": 0},
            "away": {"yellow_cards": 3, "red_cards": 1},
        },
    },
    # Internacional 0-0 Grêmio, 2026-08-27 -- the first leg. ``red_cards`` is
    # absent from both sides, which is this provider's way of saying there was
    # no red card at all; the incidents feed confirms it.
    "587786": {
        "event_id": 587786,
        "stats": {
            "home": {"yellow_cards": 2},
            "away": {"yellow_cards": 2},
        },
    },
}

INCIDENTS = {
    "2606": {
        "event_id": 2606,
        "incidents": [
            {"type": "card", "minute": 90, "is_home": False, "card_type": "yellow"},
            {"type": "card", "minute": 90, "is_home": False, "card_type": "yellow"},
            {"type": "card", "minute": 90, "is_home": True, "card_type": "yellow"},
            # A. Bernabei's second yellow. His first is the 33' below.
            {"type": "card", "minute": 90, "is_home": True, "card_type": "yellowRed"},
            {"type": "card", "minute": 77, "is_home": True, "card_type": "yellow"},
            {"type": "card", "minute": 73, "is_home": False, "card_type": "red"},
            {"type": "card", "minute": 60, "is_home": True, "card_type": "yellow"},
            {"type": "card", "minute": 33, "is_home": True, "card_type": "yellow"},
            # Mano Menezes, the away manager.
            {
                "type": "card", "minute": 0, "is_home": False,
                "card_type": "yellow", "is_manager": True,
            },
            {"type": "goal", "minute": 62, "is_home": False},
        ],
    },
    "7099": {
        "event_id": 7099,
        "incidents": [
            {"type": "card", "minute": 90, "is_home": True, "card_type": "yellow"},
            {"type": "card", "minute": 89, "is_home": False, "card_type": "red"},
            {"type": "card", "minute": 76, "is_home": True, "card_type": "yellow"},
            {"type": "card", "minute": 70, "is_home": False, "card_type": "yellow"},
            {"type": "card", "minute": 57, "is_home": True, "card_type": "yellow"},
            {"type": "card", "minute": 56, "is_home": False, "card_type": "yellow"},
            {"type": "card", "minute": 8, "is_home": False, "card_type": "yellow"},
            {"type": "card", "minute": 5, "is_home": True, "card_type": "yellow"},
        ],
    },
    "587786": {
        "event_id": 587786,
        "incidents": [
            {"type": "card", "minute": 70, "is_home": True, "card_type": "yellow"},
            {"type": "card", "minute": 44, "is_home": True, "card_type": "yellow"},
            {"type": "card", "minute": 61, "is_home": False, "card_type": "yellow"},
            {"type": "card", "minute": 20, "is_home": False, "card_type": "yellow"},
        ],
    },
}


@pytest.fixture(autouse=True)
def _clean_caches():
    reset_bzzoiro_stats_cache()
    reset_bzzoiro_incidents_cache()
    yield
    reset_bzzoiro_stats_cache()
    reset_bzzoiro_incidents_cache()


def _client(tmp_path, *, incidents=True, event_ids=("2606", "7099", "587786")):
    """A BzzoiroClient replaying the payloads above and nothing else."""
    client = BzzoiroClient(rate_limiter=RateLimiter(usage_dir=tmp_path / "usage"))
    client.api_key = "test-key"
    routes = {}
    for event_id in event_ids:
        routes[f"/events/{event_id}/stats/"] = STATS[event_id]
        if incidents:
            routes[f"/events/{event_id}/incidents/"] = INCIDENTS[event_id]

    def _fake(*, endpoint, params, operation, source_event_id=None):
        payload = routes.get(endpoint)
        if payload is None:
            return SourceOperationResult(
                status=SourceResultStatus.NOT_FOUND,
                provider="bzzoiro",
                operation=operation,
                error_code="http_404",
            )
        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=json.loads(json.dumps(payload)),
            provider="bzzoiro",
            operation=operation,
            http_status=200,
        )

    client._request_with_evidence = _fake  # type: ignore[method-assign]
    return client


# --- the arithmetic --------------------------------------------------------


def test_grenal_h2h_reads_ten_nine_four(tmp_path):
    """The three meetings the audit read, in the quantity the book settles."""
    client = _client(tmp_path)
    got = {}
    for event_id in ("2606", "7099", "587786"):
        stats, gap, flags = _bzzoiro_match_stats(client, event_id)
        assert gap is None
        assert flags == {}, f"{event_id} should resolve cleanly, got {flags}"
        got[event_id] = (
            stats["total"]["cards_total"],
            stats["total"]["cards_points_total"],
        )

    assert got["2606"] == (7.0, 10.0)
    assert got["7099"] == (7.0, 9.0)
    assert got["587786"] == (4.0, 4.0)


def test_the_line_the_audit_priced_flips_side():
    """8.5 UNDER was 3/3 in yellows and is 1/3 in booking points.

    This is the whole finding, stated as a hit count: the sheet's 20/20 was a
    count of the wrong events, and two of the three meetings it read as UNDER
    are OVER.
    """
    yellows = [7.0, 7.0, 4.0]
    points = [10.0, 9.0, 4.0]
    assert sum(1 for v in yellows if v < 8.5) == 3
    assert sum(1 for v in points if v < 8.5) == 1


def test_a_second_yellow_is_three_points_not_four_and_a_straight_red_is_two():
    """Both of a dismissed player's yellows are already in ``yellow_cards``.

    The naive reading -- yellows plus twice the reds -- charges a second-yellow
    dismissal 4 where the book charges 3. Internacional's own side of event
    2606 is the case: 5 yellows and 1 red is 7 that way, and 6 in fact.
    """
    second_yellow = card_points(5.0, 1.0, {"yellow": 4, "red": 0, "yellow_red": 1})
    assert second_yellow == (6.0, None)

    straight = card_points(2.0, 1.0, {"yellow": 2, "red": 1, "yellow_red": 0})
    assert straight == (4.0, None)

    no_reds = card_points(4.0, 0.0, {"yellow": 4, "red": 0, "yellow_red": 0})
    assert no_reds == (4.0, None)


def test_a_managers_card_is_worth_nothing(tmp_path):
    """Superbet's card markets count cards shown to players.

    ``/stats/`` already excludes them -- event 2606's away side shows 2 yellows
    against 3 yellow-type incidents -- and the incidents parser must agree, or
    ``max`` of the two counts would put the manager back in.
    """
    client = _client(tmp_path)
    result = client.get_incidents_result("2606")
    assert result.status is SourceResultStatus.SUCCESS
    assert result.value["manager_cards"] == 1
    assert result.value["cards"]["away"] == {"yellow": 2, "red": 1, "yellow_red": 0}
    assert result.value["cards"]["home"] == {"yellow": 4, "red": 0, "yellow_red": 1}


def test_reds_that_cannot_be_typed_are_charged_as_straight_and_flagged():
    """The fallback when the incidents feed cannot be read.

    One point high on a second-yellow dismissal, which is adverse to UNDER --
    the side the audit found overstated -- and the flag says so on the row.
    """
    assert card_points(2.0, 1.0, None) == (4.0, "RED_TYPE_UNKNOWN")


def test_an_unestablished_red_count_drops_the_observation():
    """No red information at all leaves the sample rather than scoring zero.

    ``red_cards`` is absent from ``/stats/`` on a match with no red card, so
    "no figure" and "no red" are the same payload -- ``a-zero-that-means-unknown``
    in its purest form. Reading it as zero is right about 50 fixtures in 51 and
    prices every UNDER two points light on the 51st.
    """
    assert card_points(2.0, None, None) == (None, "REDS_UNKNOWN")


def test_the_feeds_disagreeing_takes_the_larger_count_and_says_so():
    """Both feeds omit cards; neither was seen to invent one.

    Measured over 80 fixtures on 2026-09-03: the incidents feed listed fewer
    player cards than ``/stats/`` on 4, and ``/stats/`` reported 0 reds against
    an incident red on 1. So the larger count is the maximum-likelihood reading
    in both directions, not a thumb on the UNDER scale.
    """
    points, flag = card_points(3.0, 1.0, {"yellow": 3, "red": 0, "yellow_red": 0})
    assert (points, flag) == (5.0, "RED_COUNT_CONFLICT")


def test_a_match_with_no_card_stats_costs_no_incidents_request(tmp_path):
    """No cards published means nothing to break down.

    Paying a request per statless friendly to learn that would double the cost
    of the cheapest matches in every sample.
    """
    client = BzzoiroClient(rate_limiter=RateLimiter(usage_dir=tmp_path / "usage"))
    client.api_key = "test-key"
    seen = []

    def _fake(*, endpoint, params, operation, source_event_id=None):
        seen.append(endpoint)
        if endpoint == "/events/999/stats/":
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value={"event_id": 999, "stats": {"home": {"corner_kicks": 4},
                                                  "away": {"corner_kicks": 6}}},
                provider="bzzoiro", operation=operation, http_status=200,
            )
        return SourceOperationResult(
            status=SourceResultStatus.NOT_FOUND, provider="bzzoiro",
            operation=operation, error_code="http_404",
        )

    client._request_with_evidence = _fake  # type: ignore[method-assign]
    stats, gap, flags = _bzzoiro_match_stats(client, "999")
    assert gap is None
    assert flags == {}
    assert "cards_points_total" not in stats["total"]
    assert seen == ["/events/999/stats/"]


def test_one_sides_silence_does_not_become_a_smaller_match_total(tmp_path):
    """A total needs both sides.

    Home resolves, away cannot (yellows but no red figure and no incidents), so
    ``cards_points_total`` must be absent -- a total built from one side's
    points is a smaller number than the match produced, which is the exact
    failure this metric exists to remove.
    """
    client = BzzoiroClient(rate_limiter=RateLimiter(usage_dir=tmp_path / "usage"))
    client.api_key = "test-key"

    def _fake(*, endpoint, params, operation, source_event_id=None):
        if endpoint == "/events/555/stats/":
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value={
                    "event_id": 555,
                    "stats": {
                        "home": {"yellow_cards": 2, "red_cards": 0},
                        "away": {"yellow_cards": 3},
                    },
                },
                provider="bzzoiro", operation=operation, http_status=200,
            )
        return SourceOperationResult(
            status=SourceResultStatus.NOT_FOUND, provider="bzzoiro",
            operation=operation, error_code="http_404",
        )

    client._request_with_evidence = _fake  # type: ignore[method-assign]
    stats, _gap, flags = _bzzoiro_match_stats(client, "555")
    assert stats["home"]["cards_points_for"] == 2.0
    assert "cards_points_for" not in stats["away"]
    assert "cards_points_total" not in stats["total"]
    assert flags["away"] == "REDS_UNKNOWN"
    assert flags["total"] == "REDS_UNKNOWN"


# --- the wiring ------------------------------------------------------------


def test_no_alias_table_maps_yellow_cards_onto_a_card_points_metric():
    """The handoff note's own acceptance check.

    An alias cannot express booking points: the arithmetic needs the *type* of
    each red, which lives in a different endpoint. Any table that pointed
    ``yellow_cards`` at ``cards_points_*`` would be claiming otherwise.
    """
    tables = {
        "espn-football": _ESPN_FOOTBALL_ALIASES,
        "highlightly": _HIGHLIGHTLY_NORMALIZED_ALIASES,
        "bzzoiro-total": _BZZOIRO_TOTAL_ALIASES,
        "bzzoiro-for": _BZZOIRO_FOR_ALIASES,
    }
    for name, table in tables.items():
        for raw, canonical in table.items():
            assert not canonical.startswith("cards_points"), (
                f"{name} aliases {raw!r} straight onto {canonical!r}; card points "
                f"are derived, never aliased"
            )


def test_liczba_kartek_is_a_booking_points_market():
    assert classify_market("Liczba kartek") == ("cards_points_total", None)
    assert classify_market("Grêmio - liczba kartek") == ("cards_points_for", "gremio")
    # And the red-card market is still its own thing, matched first.
    assert classify_market("Liczba czerwonych kartek") == ("red_cards_total", None)
    assert classify_market("Liczba czerwonych kartek Grêmio") == ("red_cards_for", "gremio")


def test_the_card_markets_price_points_and_nothing_prices_yellows():
    """``cards_total`` survives as a collected metric with no market.

    Providers that only publish yellows keep contributing it, and a future
    yellow-only market could read it -- but no line in the grid may point at it
    while "Liczba kartek" is the market being priced.
    """
    football = standard_market_lines()["football"]
    by_market = {entry["market"]: entry for entry in football}
    assert by_market["Cards Total"]["stat"] == "cards_points"
    assert by_market["Team Cards"]["stat"] == "cards_points"
    assert all(entry["stat"] != "yellow_cards" for entry in football)


def test_card_points_are_count_metrics():
    """So ``cross_provider_agreement`` compares them on the +/-1 tolerance a
    count needs, which is also exactly the gap an untyped red opens between
    bzzoiro and a corroborator."""
    assert "cards_points_total" in COUNT_METRICS
    assert "cards_points_for" in COUNT_METRICS


def test_a_provider_with_reds_but_no_types_corroborates_on_points():
    """espn-football and highlightly can now check the metric that pays.

    Charged straight, so they sit at most one point above bzzoiro per
    second-yellow dismissal -- inside the count tolerance, so a real
    transcription error still reads DISAGREE.
    """
    combined = {"cards_total": 7.0, "red_cards_total": 2.0, "corners_total": 9.0}
    flag = providers._add_untyped_card_points(combined)
    assert combined["cards_points_total"] == 11.0
    assert flag == "RED_TYPE_UNKNOWN"

    # bzzoiro's own reading of the same match (one straight, one second yellow)
    # is 10, and 11 - 10 = 1 is inside the count-metric tolerance.
    assert abs(combined["cards_points_total"] - 10.0) <= 1.0


def test_a_provider_that_does_not_report_reds_emits_no_points():
    combined = {"cards_total": 7.0, "corners_total": 9.0}
    assert providers._add_untyped_card_points(combined) is None
    assert "cards_points_total" not in combined


def test_settlement_reads_the_same_metric_the_row_was_priced_from():
    """``settle.py`` is metric-name-generic, so the fix reaches the backtest
    through ``_bzzoiro_match_stats`` alone -- but the cached actuals on disk
    were built before ``cards_points_*`` existed and answer NO_DATA until they
    are refetched."""
    actuals = {
        "home": {"cards_points_for": 6.0},
        "away": {"cards_points_for": 4.0},
        "total": {"cards_points_total": 10.0, "cards_total": 7.0},
    }
    assert settle_row(
        market="cards_points_total", line=8.5, direction="UNDER", actuals=actuals
    ) == ("LOST", 10.0)
    assert settle_row(
        market="cards_total", line=8.5, direction="UNDER", actuals=actuals
    ) == ("WON", 7.0)

    stale = {"home": {}, "away": {}, "total": {"cards_total": 7.0}}
    assert settle_row(
        market="cards_points_total", line=8.5, direction="UNDER", actuals=stale
    ) == ("NO_DATA", None)
