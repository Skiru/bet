"""Audit 2026-10-13 A7: the basketball history curve on lines placed where
the market stood (operator O2: the historical odds give the POSITION of a
line only, p stays the score model's).

bet.sofa.market_lines reads a cached Sofascore odds payload into a game's
total and home-spread lines (no price kept); sport_confidence.walk_forward_rows
with `market_lines` scores total / handicap / team total on those lines only;
without it (epochs.MARKET_POSITIONED_LINES_FROM_UTC None) the replay is
byte-identical. scripts/sofa/backfill_event_odds.py is resumable and writes
no price."""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import sport_confidence as scf
from bet.sofa.errors import ProviderError
from bet.sofa.market_lines import (
    MarketLines,
    load_market_lines,
    parse_lines,
    trim_markets,
)
from bet.sofa.score_model import build_model, line_probability
from bet.sofa.shadow import SPORTS, ShadowLine
from scripts.sofa import backfill_event_odds as bfo
from scripts.sofa.fit_sport_confidence import market_lines_for

BASKETBALL = SPORTS["basketball"]
DAY = 86400


def _odds_body(home_first: bool = True) -> dict[str, Any]:
    spread = [
        {"name": "(+11.5) Mersin", "fractionalValue": "20/27",
         "initialFractionalValue": "5/6"},
        {"name": "(-11.5) Fenerbahçe", "fractionalValue": "20/21",
         "initialFractionalValue": "5/6"},
    ]
    if not home_first:
        spread.reverse()
    return {"markets": [
        {"marketName": "Full time", "marketPeriod": "Match", "isLive": False,
         "choices": [{"name": "1", "fractionalValue": "11/2"},
                     {"name": "2", "fractionalValue": "1/10"}]},
        {"marketName": "Point spread", "marketPeriod": "Match", "isLive": False,
         "choices": spread},
        {"marketName": "Game total", "marketPeriod": "Match",
         "choiceGroup": "154.5", "isLive": False,
         "choices": [{"name": "Over", "fractionalValue": "5/6", "winning": False},
                     {"name": "Under", "fractionalValue": "5/6",
                      "winning": True}]},
        {"marketName": "Game total", "marketPeriod": "Match",
         "choiceGroup": "170.5", "isLive": True,
         "choices": [{"name": "Over", "fractionalValue": "5/6"}]},
    ]}


# --- parsing: the position only -------------------------------------------------


def test_trim_keeps_lines_and_drops_every_price() -> None:
    kept = trim_markets(_odds_body())
    assert {m["marketName"] for m in kept} == {"Point spread", "Game total"}
    text = json.dumps(kept)
    assert "fractionalValue" not in text and "FractionalValue" not in text


def test_spread_is_assigned_by_team_name_not_order() -> None:
    for home_first in (True, False):
        ml = parse_lines(1, trim_markets(_odds_body(home_first)),
                         ["Fenerbahçe"], ["Mersin"])
        assert ml is not None
        assert ml.home_handicaps == (-11.5,)  # home Fenerbahçe gives 11.5
        assert ml.totals == (154.5,)          # the live 170.5 is not a line
    away_home = parse_lines(1, trim_markets(_odds_body()), ["Mersin"],
                            ["Fenerbahce"])
    assert away_home is not None and away_home.home_handicaps == (11.5,)


def test_unnamed_spread_team_is_left_out() -> None:
    ml = parse_lines(1, trim_markets(_odds_body()), ["Other A"], ["Other B"])
    assert ml is not None
    assert ml.home_handicaps == () and ml.totals == (154.5,)
    assert parse_lines(2, [], ["A"], ["B"]) is None


def test_team_totals_split_the_two_market_lines() -> None:
    ml = MarketLines(1, (154.5,), (-11.5,))
    assert ml.team_totals() == {"T1": (83.0 - 0.5, 83.0 + 0.5),
                                "T2": (71.5,)}
    assert MarketLines(1, (154.5,), ()).team_totals() == {}
    assert MarketLines(1, (150.5, 154.5), (-3.5,)).team_totals() == {}


# --- the replay ------------------------------------------------------------------


def _event(eid: int, ts: int, home: int, away: int, rng: random.Random
           ) -> dict[str, Any]:
    hp = [rng.randint(18, 30) for _ in range(4)]
    ap = [rng.randint(18, 30) for _ in range(4)]
    hs, as_ = sum(hp), sum(ap)
    if hs == as_:
        hp[3] += 1
        hs += 1
    return {
        "id": eid, "startTimestamp": ts,
        "tournament": {"id": 9, "name": "L",
                       "uniqueTournament": {"id": 5, "name": "L"},
                       "category": {"sport": {"slug": "basketball"}}},
        "status": {"type": "finished", "description": "Ended"},
        "homeTeam": {"id": home, "name": f"T{home}", "gender": "M"},
        "awayTeam": {"id": away, "name": f"T{away}", "gender": "M"},
        "homeScore": {**{f"period{i + 1}": v for i, v in enumerate(hp)},
                      "current": hs, "normaltime": hs},
        "awayScore": {**{f"period{i + 1}": v for i, v in enumerate(ap)},
                      "current": as_, "normaltime": as_},
        "winnerCode": 1 if hs > as_ else 2,
    }


def _history() -> list[scf.HistoryGame]:
    rng = random.Random(3)
    ev: dict[int, dict[str, Any]] = {}
    eid = 1
    for d in range(60):
        for k, (h, a) in enumerate(((101, 102), (103, 104), (102, 103))):
            ev[eid] = _event(eid, d * DAY + k * 7200, h, a, rng)
            eid += 1
    return scf.parse_history(ev, BASKETBALL)


def _rows(market: dict[int, MarketLines] | None, max_games: int | None = 10
          ) -> list[scf.Row]:
    return scf.walk_forward_rows(_history(), BASKETBALL, 40 * DAY, 60 * DAY, 30,
                                 max_games, "t", market_lines=market)


def test_the_switch_is_on_from_10_14() -> None:
    # turned on with the A7 basketball curve staged from 2026-10-14 (audit
    # standing go, docs/sofa/evidence/market_positioned_lines_2026-10-13.md)
    assert epochs.MARKET_POSITIONED_LINES_FROM_UTC == datetime(2026, 10, 14, tzinfo=UTC)
    assert not epochs.market_positioned_lines("2026-10-13")


def test_switch_off_rows_are_identical(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "MARKET_POSITIONED_LINES_FROM_UTC", None)
    assert not epochs.market_positioned_lines("2026-10-14")
    a = scf.walk_forward_rows(_history(), BASKETBALL, 40 * DAY, 60 * DAY, 30,
                              10, "t")
    b = _rows(None)
    assert a == b and a
    assert not any("line_source" in r for r in a)


def test_fit_reads_no_cache_while_the_switch_is_off(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "MARKET_POSITIONED_LINES_FROM_UTC", None)
    assert market_lines_for("basketball", "2026-10-14", None) is None
    assert market_lines_for("hockey", "2026-10-14", "/nonexistent") is None


def _market() -> dict[int, MarketLines]:
    # two games of the window: one inside the thinned sample, one outside
    return {g.rating.event_id: MarketLines(g.rating.event_id, (150.5,), (-2.5,))
            for g in _history() if g.rating.ts >= 40 * DAY}


def test_positioned_families_sit_on_the_market_lines_only() -> None:
    off = _rows(None)
    on = _rows(_market())
    positioned = {"total", "handicap", "team_total"}
    # every other family: the same rows
    assert ([r for r in off if r["family"] not in positioned]
            == [r for r in on if r["family"] not in positioned])
    mk = [r for r in on if r["family"] in positioned]
    assert mk and all(r["line_source"] == "market" for r in mk)
    assert {r["line"] for r in mk if r["family"] == "total"} == {150.5}
    assert {r["line"] for r in mk if r["family"] == "handicap"} == {-2.5}
    tt = {(r["subject"], r["line"]) for r in mk if r["family"] == "team_total"}
    assert tt == {("T1", 76.5), ("T2", 74.0 - 0.5), ("T2", 74.0 + 0.5)}
    # every window game with market lines is scored, not only the thinned
    window_games = {f"h:{eid}" for eid in _market()}
    assert {r["game"] for r in mk if r["family"] == "total"} == window_games
    assert len({r["game"] for r in off}) < len(window_games)


def test_a_game_without_market_lines_gives_no_positioned_row() -> None:
    market = dict(list(_market().items())[:3])
    on = _rows(market)
    games = {r["game"] for r in on
             if r["family"] in ("total", "handicap", "team_total")}
    assert games == {f"h:{eid}" for eid in market}


def test_p_is_the_models_and_no_price_reaches_a_row() -> None:
    on = _rows(_market())
    for r in on:
        assert not ({"odds", "price", "fair", "market_p"} & set(r))
    # the same line from the synthetic replay has the same p: one simulation
    ml = MarketLines(0, (150.5,), ())
    g = next(g for g in _history() if g.rating.ts >= 40 * DAY)
    model = build_model([h.rating for h in _history()], BASKETBALL, g.rating.ts)
    rows = scf.score_game(BASKETBALL, model, g, 50, "t", market_lines_on=True,
                          market=ml, market_only=True)
    sims = model.simulate(*model.expected(g.rating.competition_id,
                                          g.rating.home_id, g.rating.away_id,
                                          g.rating.ts) or (0.0, 0.0),
                          seed=g.rating.event_id, n=50)
    over = next(r for r in rows if r["side"] == "OVER")
    p = line_probability(ShadowLine("", 753, "total", 0, "", 150.5, "OVER", 1.0),
                         sims, BASKETBALL)
    assert p is not None and over["p"] == round(p, 4)
    assert {r["family"] for r in rows} == {"total"}


# --- the backfill ----------------------------------------------------------------


def test_backfill_targets_put_the_fit_sample_first() -> None:
    history = _history()
    before = 60 * DAY
    targets = bfo.select_targets(history, before, 30, 10, 5, 3)
    assert len(targets) == sum(1 for g in history if g.rating.ts >= before - 30 * DAY)
    prios = [t["prio"] for t in targets]
    assert prios == sorted(prios) and 0 in prios and 1 in prios
    first = {t["event_id"] for t in targets if t["prio"] == 0}
    hold = [g for g in history if before - 10 * DAY <= g.rating.ts < before]
    assert bfo.thinned_ids(hold, 3) <= first


def test_backfill_is_resumable_and_writes_no_price(tmp_path: Path) -> None:
    cache = tmp_path / "basketball.jsonl"
    target = {"event_id": 7, "ts": 1, "competition_id": 5, "tournament": "L",
              "user_count": 50, "women": False, "home_names": ["Fenerbahçe"],
              "away_names": ["Mersin"], "prio": 0}
    lines = [bfo.record(target, _odds_body()),
             bfo.record({**target, "event_id": 8}, None)]
    cache.write_text("".join(json.dumps(r) + "\n" for r in lines)
                     + '{"event_id": 9, "sta', encoding="utf-8")
    assert bfo.asked_ids(cache) == {7, 8}       # a cut line is asked again
    assert "FractionalValue" not in cache.read_text(encoding="utf-8")
    assert "fractionalValue" not in cache.read_text(encoding="utf-8")
    got = load_market_lines(cache)
    assert set(got) == {7} and got[7].home_handicaps == (-11.5,)


class _Client:
    def __init__(self, fail: str | None = None) -> None:
        self.fail = fail
        self.asked: list[int] = []

    def event_odds(self, eid: int) -> Any:
        self.asked.append(eid)
        if self.fail:
            raise ProviderError(self.fail)
        return _odds_body()


def test_a_403_stops_the_run_and_writes_nothing(tmp_path: Path) -> None:
    cache = tmp_path / "c.jsonl"
    runner = bfo.Runner(_Client("HTTP 403"), cache, None)
    t = {"event_id": 1, "ts": 1, "competition_id": 5, "tournament": "L",
         "user_count": None, "women": False, "home_names": [], "away_names": [],
         "prio": 0}
    runner.fetch(t)
    runner.fetch({**t, "event_id": 2})
    assert runner.stop.is_set() and runner.counts["http_403"] == 1
    assert runner.client.asked == [1]
    assert not cache.exists()


def test_tier_of_user_count() -> None:
    assert bfo.tier_of(None).startswith("D")
    assert bfo.tier_of(250_000).startswith("A")
    assert bfo.tier_of(12_000).startswith("B")


def test_the_cache_keeps_hockeys_match_goals() -> None:
    """2026-10-15: hockey's total is "Match goals" on Sofascore; the cache
    trimmed it away and wrote 5,931 hockey games with no market at all."""
    body = {"markets": [
        {"marketId": 1, "marketName": "Full time", "choiceGroup": None,
         "choices": [{"name": "1", "fractionalValue": "1/2"}]},
        {"marketId": 9, "marketName": "Match goals", "marketPeriod": "Match",
         "choiceGroup": "5.5", "isLive": False,
         "choices": [{"name": "Over", "fractionalValue": "4/5", "winning": True},
                     {"name": "Under", "fractionalValue": "1/1", "winning": False}]}]}
    kept = trim_markets(body)
    assert [m["marketName"] for m in kept] == ["Match goals"]
    assert kept[0]["choiceGroup"] == "5.5"
    assert all("fractionalValue" not in c for c in kept[0]["choices"])
