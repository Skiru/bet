"""The four listing/table endpoints wired on 2026-08-30, and the traps in them.

Payload shapes captured live from sports.bzzoiro.com that day. Three findings
drive these tests and each one silently loses data if it regresses:

* ``/predictions/`` compares ``date_to`` against a **datetime**, so a naive
  ``date_from == date_to`` asks for fixtures kicking off at exactly midnight.
  Measured: 1 row the naive way against 46 the correct way, and the naive
  answer looks exactly like a day the model has not forecast yet.
* ``/leagues/{id}/standings/`` has **two shapes**. A grouped competition
  carries no ``standings`` key at all, only ``groups``.
* the list and the per-event prediction endpoints must parse **identically**,
  or the corners signal would change with how many fixtures the day had.
"""
import pytest

from bet.api_clients.bzzoiro import BzzoiroClient
from bet.api_clients.rate_limiter import RateLimiter
from bet.integration.source_result import SourceOperationResult, SourceResultStatus
from bet.simple_stats import providers
from bet.simple_stats.contracts import ModelPrediction
from bet.simple_stats.market_context import (
    SIGNAL_MARKETS,
    _model_probability,
)
from bet.simple_stats.providers import (
    RunBudget,
    fetch_bzzoiro_league_table,
    reset_bzzoiro_standings_cache,
)

MARKETS_BLOCK = {
    "match_result": {"prob_home": 38.5, "prob_draw": 29.1, "prob_away": 32.3, "predicted": "H"},
    "expected_goals": {"home": 1.33, "away": 1.2},
    "over_under": {"prob_over_15": 70.6, "prob_over_25": 46.4, "prob_over_35": 25.5},
    "btts": {"prob_yes": 52.9},
    "score": {"most_likely": "1-1"},
    "draw_no_bet": {"prob_home": 54.5},
    "corners": {"prob_over_85": 62.4, "prob_over_95": 50.7, "prob_over_105": 39.2},
}

PREDICTIONS_LIST = {
    "count": 3,
    "results": [
        {
            "id": 2022,
            "created_at": "2026-08-24T02:15:18Z",
            "event": {"id": 209553, "event_date": "2026-08-30T13:00:00Z"},
            "markets": MARKETS_BLOCK,
            "model": {"confidence": 0.3851, "version": "dc-blend-v1"},
        },
        {
            "id": 2023,
            "created_at": "2026-08-24T02:15:18Z",
            # The row the inclusive upper bound always drags in: midnight on the
            # following day.
            "event": {"id": 999999, "event_date": "2026-08-31T00:00:00Z"},
            "markets": MARKETS_BLOCK,
            "model": {"version": "dc-blend-v1"},
        },
        {"id": 2024, "event": {}, "markets": MARKETS_BLOCK},  # unkeyable
    ],
}

STANDINGS_FLAT = {
    "league_id": 1,
    "season": {"id": 1058},
    "grouped": False,
    "standings": [
        {
            "position": 1, "team_id": 12, "team_name": "Manchester City",
            "played": 2, "pts": 6, "gf": 6, "ga": 2,
            "xgf": 3.8, "xga": 1.2, "xgd": 2.6, "xg_games": 2, "form": "WWLDW",
        }
    ],
}

STANDINGS_GROUPED = {
    "league_id": 85,
    "season": {"id": 1635},
    "grouped": True,
    "groups": {
        "Group A": [
            {
                "position": 1, "team_id": 2397, "team_name": "Vélez Sarsfield",
                "played": 23, "pts": 41, "xgf": 25.6, "xga": 25.1,
                "xgd": 0.4, "xg_games": 23, "form": "DDDDW",
            }
        ],
        "Group B": [
            {
                "position": 1, "team_id": 774, "team_name": "Independiente Rivadavia",
                "played": 23, "pts": 40, "xgf": 29.7, "xga": 18.4,
                "xgd": 11.3, "xg_games": 23, "form": "WWDLW",
            }
        ],
    },
}

EVENT_PLAYER_STATS = {
    "event_id": 209554,
    "count": 2,
    "player_stats": [
        {
            "player_id": 703, "team_id": 4, "minutes_played": 90, "rating": 7.2,
            "expected_assists": 0.022984, "total_shots": 0, "shots_on_target": 0,
            "fouls": 0, "was_fouled": 1, "yellow_card": 0, "red_card": 0,
        },
        {
            # Unused substitute: a box score of zeroes that would make every
            # UNDER prop look like a lock if it were counted.
            "player_id": 704, "team_id": 4, "minutes_played": 0, "rating": None,
            "total_shots": 0, "shots_on_target": 0, "fouls": 0,
            "was_fouled": 0, "yellow_card": 0, "red_card": 0,
        },
    ],
}

def _client(monkeypatch, tmp_path, payloads, cls=BzzoiroClient, provider="bzzoiro"):
    import json as _json

    client = cls(rate_limiter=RateLimiter(usage_dir=tmp_path / "usage"))
    client.api_key = "test-key"
    calls = []

    def _fake(*, endpoint, params, operation, source_event_id=None):
        calls.append((endpoint, dict(params or {})))
        payload = payloads.get(endpoint)
        if payload is None:
            return SourceOperationResult(
                status=SourceResultStatus.NOT_FOUND, provider=provider,
                operation=operation, error_code="http_404",
            )
        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=_json.loads(_json.dumps(payload)),
            provider=provider, operation=operation, http_status=200,
        )

    monkeypatch.setattr(client, "_request_with_evidence", _fake)
    return client, calls


@pytest.fixture(autouse=True)
def _clear_caches():
    reset_bzzoiro_standings_cache()
    yield
    reset_bzzoiro_standings_cache()


# --- predictions listing --------------------------------------------------


def test_prediction_window_asks_for_the_next_day_not_the_same_day(monkeypatch, tmp_path):
    """The whole reason this method takes a day rather than a range.

    ``date_to`` is compared against a datetime, so passing the betting day on
    both sides asks for fixtures kicking off at exactly 00:00 -- and returns a
    day that looks unforecast when it is fully forecast.
    """
    client, calls = _client(monkeypatch, tmp_path, {"/predictions/": PREDICTIONS_LIST})
    client.get_predictions_list_result(date="2026-08-30")

    _endpoint, params = calls[0]
    assert params["date_from"] == "2026-08-30"
    assert params["date_to"] == "2026-08-31"


def test_prediction_listing_drops_the_next_day_row_the_bound_drags_in(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path, {"/predictions/": PREDICTIONS_LIST})
    result = client.get_predictions_list_result(date="2026-08-30")

    predictions = result.value["predictions"]
    assert set(predictions) == {"209553"}, "a fixture from another day was attributed to this one"
    assert result.parser_diagnostics["off_day_dropped"] == 1


def test_listing_and_per_event_prediction_parse_identically(monkeypatch, tmp_path):
    """The property that makes the prefetch safe to substitute.

    If these drifted, the corners signal would depend on whether the day's
    listing happened to cover a fixture -- a number changing for a reason that
    has nothing to do with football.
    """
    per_event = {"markets": MARKETS_BLOCK, "model": {"confidence": 0.3851, "version": "dc-blend-v1"},
                 "created_at": "2026-08-24T02:15:18Z"}
    client, _ = _client(
        monkeypatch, tmp_path,
        {"/predictions/": PREDICTIONS_LIST, "/events/209553/prediction/": per_event},
    )

    from_list = client.get_predictions_list_result(date="2026-08-30").value["predictions"]["209553"]
    from_event = client.get_prediction_result(209553).value["prediction"]

    assert from_list == from_event
    # And both are constructible as the contract the artifact carries.
    assert ModelPrediction(**from_list).prob_corners_over_95 == pytest.approx(0.507)


# --- standings ------------------------------------------------------------


def test_flat_standings_carry_season_xg(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path, {"/leagues/1/standings/": STANDINGS_FLAT})
    result = client.get_standings_result(1)

    row = result.value["table"]["12"]
    assert row["xgf"] == 3.8 and row["xga"] == 1.2
    assert row["xg_games"] == 2, "the sample behind the xG must survive"
    assert row["form"] == "WWLDW"
    assert row["group"] is None


def test_grouped_standings_are_not_a_schema_error(monkeypatch, tmp_path):
    """Argentina's Primera has no ``standings`` key at all.

    Treating that as malformed -- which it was until 2026-08-30 -- silently
    drops season xG for every fixture in every grouped competition.
    """
    client, _ = _client(monkeypatch, tmp_path, {"/leagues/85/standings/": STANDINGS_GROUPED})
    result = client.get_standings_result(85)

    assert result.status is SourceResultStatus.SUCCESS
    table = result.value["table"]
    assert set(table) == {"2397", "774"}
    assert table["2397"]["group"] == "Group A"
    assert table["774"]["group"] == "Group B"
    assert result.parser_diagnostics["grouped"] is True


def test_league_table_is_fetched_once_per_league(monkeypatch, tmp_path):
    """A slate is many fixtures drawn from few competitions."""
    client, calls = _client(monkeypatch, tmp_path, {"/leagues/1/standings/": STANDINGS_FLAT})
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)
    rl = RateLimiter(usage_dir=tmp_path / "u")

    first, _ = fetch_bzzoiro_league_table("1", rl)
    second, _ = fetch_bzzoiro_league_table("1", rl)

    assert first == second and first is not None
    assert len(calls) == 1


def test_missing_league_table_is_a_gap_not_a_crash(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path, {})
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    table, gaps = fetch_bzzoiro_league_table("404", RateLimiter(usage_dir=tmp_path / "u"))

    assert table is None
    assert any("standings" in g for g in gaps)


def test_league_table_respects_an_explicit_budget(monkeypatch, tmp_path):
    client, calls = _client(monkeypatch, tmp_path, {"/leagues/1/standings/": STANDINGS_FLAT})
    monkeypatch.setattr(providers, "get_client", lambda *a, **k: client)

    table, gaps = fetch_bzzoiro_league_table(
        "1", RateLimiter(usage_dir=tmp_path / "u"),
        RunBudget(limit=0, overrides={"bzzoiro": 0}),
    )

    assert table is None and calls == []
    assert any("run budget exhausted" in g for g in gaps)


# --- event player stats ---------------------------------------------------


def test_event_player_stats_normalise_to_pipeline_names(monkeypatch, tmp_path):
    client, _ = _client(
        monkeypatch, tmp_path, {"/events/209554/player-stats/": EVENT_PLAYER_STATS}
    )
    result = client.get_event_player_stats_result(209554)

    starter = result.value["players"][0]
    assert starter["player_was_fouled"] == 1.0
    assert starter["player_shots_on_target"] == 0.0
    assert starter["minutes_played"] == 90
    # The zero-minute substitute is still reported, but counted separately.
    assert result.value["played_count"] == 1
    assert len(result.value["players"]) == 2


def test_tennis_is_out_of_market_context_scope_entirely():
    """The property that replaced "tennis has a model but no prices".

    Between 2026-08-30 and 2026-09-02 tennis markets sat in ``SIGNAL_MARKETS``
    so a tennis row would carry the bzzoiro model's probability under a
    ``NO_MARKET_DATA`` verdict. That provider is gone, so there is no tennis
    model and no tennis price -- and a market this stage cannot say anything
    about must return nothing rather than a verdict that implies it looked.
    """
    assert "total_games" not in SIGNAL_MARKETS
    assert "total_sets" not in SIGNAL_MARKETS
    assert set(SIGNAL_MARKETS) == {"corners_total", "goals_total"}
