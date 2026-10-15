"""Hockey A7 measurement (2026-10-16): bet.sofa.market_lines reads hockey's
full-game total "Match goals" as a total line, and the history replay scores
hockey's regulation total (623) on it; the handicap and the team totals stay
on the synthetic lines (Sofascore publishes no hockey spread). Basketball's
lines are what they were before the change. Hockey is a measurement: a fit
reads its cache only with an explicit --market-lines
(sport_confidence.MARKET_LINE_DEFAULT_SPORTS)."""

from __future__ import annotations

import json
import random
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import sport_confidence as scf
from bet.sofa.market_lines import MarketLines, load_market_lines, parse_lines
from bet.sofa.shadow import SPORTS
from scripts.sofa.fit_sport_confidence import market_lines_for

HOCKEY = SPORTS["hockey"]
DAY = 86400

# Real cache records (data/a7_odds/*.jsonl), copied verbatim.
HOCKEY_RECORD: dict[str, Any] = json.loads(
    '{"event_id": 16499769, "ts": 1792029600, "competition_id": 844, '
    '"tournament": "AHL", "user_count": 1615, "women": false, '
    '"home_names": ["San Diego Gulls", "San Diego"], '
    '"away_names": ["Ontario Reign", "Ontario"], '
    '"fetched_at": "2026-10-15T09:41:28+00:00", "status": "ok", '
    '"markets": [{"marketId": 9, "marketName": "Match goals", '
    '"marketPeriod": "Match", "marketGroup": "Match goals", '
    '"choiceGroup": "5.5", "isLive": false, '
    '"choices": [{"name": "Over", "winning": false}, '
    '{"name": "Under", "winning": true}]}]}')
BASKETBALL_RECORD: dict[str, Any] = json.loads(
    '{"event_id": 17174392, "ts": 1791847800, "competition_id": 1680, '
    '"tournament": "Argentina Liga Nacional", "user_count": 1464, '
    '"women": false, "home_names": ["Argentino de Jun\\u00edn", "Argentino"], '
    '"away_names": ["Gimnasia Comodoro Rivadavia", "Gimnasia CR"], '
    '"fetched_at": "2026-10-13T13:20:25+00:00", "status": "ok", '
    '"markets": [{"marketId": 16, "marketName": "Point spread", '
    '"marketPeriod": "Match", "marketGroup": "Point spread", "isLive": false, '
    '"choices": [{"name": "(+7.5) Argentino de Jun\\u00edn"}, '
    '{"name": "(-7.5) Gimnasia Comodoro Rivadavia"}]}, '
    '{"marketId": 18, "marketName": "Game total", "marketPeriod": "Match", '
    '"marketGroup": "Over/Under", "choiceGroup": "158.5", "isLive": false, '
    '"choices": [{"name": "Over", "winning": true}, '
    '{"name": "Under", "winning": false}]}]}')


def _parse(rec: dict[str, Any]) -> MarketLines | None:
    return parse_lines(rec["event_id"], rec["markets"], rec["home_names"],
                       rec["away_names"])


def test_hockey_match_goals_is_a_total_line() -> None:
    assert _parse(HOCKEY_RECORD) == MarketLines(16499769, (5.5,), ())
    # no spread, so no team-total split either
    ml = _parse(HOCKEY_RECORD)
    assert ml is not None and ml.team_totals() == {}


def test_basketball_lines_are_unchanged() -> None:
    ml = _parse(BASKETBALL_RECORD)
    assert ml == MarketLines(17174392, (158.5,), (7.5,))
    assert ml is not None and ml.team_totals() == {"T1": (75.5,),
                                                   "T2": (83.0 - 0.5, 83.0 + 0.5)}


def test_a_live_or_period_match_goals_is_not_a_line() -> None:
    m = dict(HOCKEY_RECORD["markets"][0])
    assert parse_lines(1, [{**m, "isLive": True}], ["A"], ["B"]) is None
    assert parse_lines(1, [{**m, "marketPeriod": "1st period"}], ["A"],
                       ["B"]) is None


def test_load_reads_both_sports(tmp_path: Any) -> None:
    path = tmp_path / "cache.jsonl"
    path.write_text(json.dumps(HOCKEY_RECORD) + "\n"
                    + json.dumps(BASKETBALL_RECORD) + "\n", encoding="utf-8")
    got = load_market_lines(path)
    assert got == {16499769: MarketLines(16499769, (5.5,), ()),
                   17174392: MarketLines(17174392, (158.5,), (7.5,))}


# --- the replay ------------------------------------------------------------------


def _event(eid: int, ts: int, home: int, away: int, rng: random.Random
           ) -> dict[str, Any]:
    hp = [rng.randint(0, 2) for _ in range(3)]
    ap = [rng.randint(0, 2) for _ in range(3)]
    hs, as_ = sum(hp), sum(ap)
    if hs == as_:
        hp[2] += 1
        hs += 1
    return {
        "id": eid, "startTimestamp": ts,
        "tournament": {"id": 9, "name": "L",
                       "uniqueTournament": {"id": 5, "name": "L"},
                       "category": {"sport": {"slug": "ice-hockey"}}},
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
    rng = random.Random(5)
    ev: dict[int, dict[str, Any]] = {}
    eid = 1
    for d in range(60):
        for k, (h, a) in enumerate(((101, 102), (103, 104), (102, 103))):
            ev[eid] = _event(eid, d * DAY + k * 7200, h, a, rng)
            eid += 1
    return scf.parse_history(ev, HOCKEY)


def _rows(market: dict[int, MarketLines] | None) -> list[scf.Row]:
    return scf.walk_forward_rows(_history(), HOCKEY, 40 * DAY, 60 * DAY, 30,
                                 10, "t", market_lines=market)


def test_only_the_regulation_total_sits_on_the_market_line() -> None:
    hist = _history()
    assert hist
    market = {g.rating.event_id: MarketLines(g.rating.event_id, (5.5,), ())
              for g in hist if g.rating.ts >= 40 * DAY}
    off, on = _rows(None), _rows(market)
    # every family but the full-game total - handicap and team totals
    # included - keeps its synthetic rows
    assert ([r for r in off if not (r["family"] == "total" and r["period"] == 0)]
            == [r for r in on if not (r["family"] == "total"
                                      and r["period"] == 0)])
    mk = [r for r in on if r.get("line_source") == "market"]
    assert mk and {r["market_id"] for r in mk} == {623}
    assert {r["line"] for r in mk} == {5.5}
    assert {r["side"] for r in mk} == {"OVER", "UNDER"}
    assert {r["game"] for r in mk} == {f"h:{eid}" for eid in market}
    assert not any(r["market_id"] == 623 and "line_source" not in r for r in on)


def test_hockey_cache_only_with_an_explicit_flag(tmp_path: Any) -> None:
    # the switch is on for 10-16, but hockey is a measurement: no default cache
    assert epochs.market_positioned_lines("2026-10-16")
    assert scf.MARKET_LINE_DEFAULT_SPORTS == frozenset({"basketball"})
    assert market_lines_for("hockey", "2026-10-16", None) is None
    path = tmp_path / "hockey.jsonl"
    path.write_text(json.dumps(HOCKEY_RECORD) + "\n", encoding="utf-8")
    assert market_lines_for("hockey", "2026-10-16", str(path)) == {
        16499769: MarketLines(16499769, (5.5,), ())}
    with pytest.raises(SystemExit):
        market_lines_for("hockey", "2026-10-16", str(tmp_path / "missing"))
