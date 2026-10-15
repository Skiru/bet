"""Basketball double chance read as two-way pairs against the 1X2, behind
epochs.BASKETBALL_DC_PAIR_FROM_UTC (defect found 2026-10-15). Offline, fast.

Superbet quotes basketball "Podwójna szansa" / "2. połowa - podwójna szansa"
with 1X and X2 only (no 12), so the whole-group rule (cs2.complete_group
"double") dropped every one of them. The golden payload is Superbet's own
(tests/sofa/golden/superbet_basketball_double_chance_2026-10-15.json, fetched
pre-match 2026-10-15: 14175125 Brisbane Bullets - SE Melbourne Phoenix, NBL,
both scopes; 15227146 Horsens IC - Holbaek-Stenhus, 1X blocked at 1.00).
"""

from __future__ import annotations

import importlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from bet.sofa import cs2, epochs, shadow
from bet.sofa import sport_confidence as scf
from bet.sofa.score_model import line_probability
from bet.sofa.shadow import (
    SPORTS,
    GameResult,
    ShadowLine,
    SnapshotEvent,
    grade,
    parse_event,
    settle_event,
)
from bet.sofa.superbet import odds_items, split_match_name

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests/sofa/golden/superbet_basketball_double_chance_2026-10-15.json"
HOCKEY_GOLDEN = ROOT / "tests/sofa/golden/superbet_hockey_double_chance_2026-10-13.json"
BASKETBALL = SPORTS["basketball"]
ON = datetime(2026, 10, 16, 0, 0, tzinfo=UTC)


def _events(path: Path = GOLDEN) -> list[dict[str, Any]]:
    return list(json.loads(path.read_text(encoding="utf-8"))["events"])


def _parse(ev: dict[str, Any], derived: bool = True, dc_pair: bool = True,
           sport: str = "basketball") -> list[ShadowLine]:
    t1, t2 = split_match_name(ev["matchName"])
    assert t1 and t2
    return parse_event(odds_items(ev), sport, str(ev["eventId"]), t1, t2,  # type: ignore[arg-type]
                       derived, dc_pair)


def _groups(lines: list[ShadowLine]) -> dict[int, dict[str, float]]:
    out: dict[int, dict[str, float]] = {}
    for ln in lines:
        out.setdefault(ln.market_id, {})[ln.side] = ln.odds
    return out


# --- the switch ------------------------------------------------------------------


def test_switch_is_on_from_the_next_day() -> None:
    assert epochs.BASKETBALL_DC_PAIR_FROM_UTC == ON
    assert epochs.BASKETBALL_DC_PAIR == "basketball_dc_pair_v1"
    assert epochs.basketball_dc_pair("2026-10-16", ON)
    assert not epochs.basketball_dc_pair("2026-10-15", ON)
    assert not epochs.basketball_dc_pair("2026-10-16", datetime(2026, 10, 15, 23, 59,
                                                                tzinfo=UTC))


def test_pair_ids_carry_the_double_chance_family_and_scope() -> None:
    pairs = shadow.DC_PAIR_MARKETS["basketball"]
    assert set(pairs) == {-101, -102, -103, -201, -202, -203,
                          -301, -302, -303, -401, -402, -403}
    assert shadow.dc_pair_id(-1, "1X") == -101 and shadow.dc_pair_id(-3, "X2") == -302
    for mid, spec in pairs.items():
        assert spec is shadow.DERIVED_MARKETS["basketball"][-((-mid) // 100)]
        assert shadow.spec_of("basketball", mid) is spec
        assert shadow.group_shape("basketball", mid) == "double"
    assert pairs[-101].family == "double_chance" and pairs[-101].scope == "reg"
    assert pairs[-302].family == "h2_double_chance" and pairs[-302].scope == "h2"
    # hockey and volleyball have no pairs
    assert set(shadow.DC_PAIR_MARKETS) == {"basketball"}


# --- SHADOW: reading -------------------------------------------------------------


def test_the_1x_x2_only_group_is_read_as_pairs_against_the_1x2() -> None:
    brisbane, horsens = _events()
    off = _parse(brisbane, dc_pair=False)
    on = _parse(brisbane)
    assert not any(ln.family.endswith("double_chance") for ln in off)
    assert [ln for ln in on if ln in off] == off  # the rest untouched, in order
    extra = [ln for ln in on if ln not in off]
    # Mecz 1 3.30 / X 13 / 2 1.41; Podwójna szansa 1X 2.57 / X2 1.27;
    # 2.Połowa - 1X2 2.47 / 17 / 1.58; 2. połowa - podwójna szansa 2.15 / 1.45
    assert _groups(extra) == {
        -101: {"1X": 2.57, "2": 1.41}, -102: {"X2": 1.27, "1": 3.3},
        -301: {"1X": 2.15, "2": 1.58}, -302: {"X2": 1.45, "1": 2.47}}
    assert all(ln.period == 0 and ln.subject == "" and ln.line is None
               for ln in extra)
    assert {ln.family for ln in extra if ln.market_id in (-101, -102)} == {
        "double_chance"}
    assert {ln.family for ln in extra if ln.market_id in (-301, -302)} == {
        "h2_double_chance"}
    # 1X blocked (status "block", price 1): only the X2 pair
    assert _groups([ln for ln in _parse(horsens)
                    if ln.family == "double_chance"]) == {-102: {"X2": 12.0, "1": 1.01}}


def test_pairs_need_the_derived_switch_too() -> None:
    brisbane = _events()[0]
    assert _parse(brisbane, derived=False, dc_pair=True) == _parse(
        brisbane, derived=False, dc_pair=False)


def test_pairs_need_the_whole_1x2_of_the_same_scope() -> None:
    brisbane = _events()[0]
    odds = [o for o in brisbane["odds"]
            if not (o["marketId"] == 777 and o["code"] == "0")]
    lines = _parse({**brisbane, "odds": odds})
    got = {ln.market_id for ln in lines}
    assert not got & {-101, -102, 777}  # no draw: neither the 1X2 nor its pairs
    assert {-301, -302} <= got  # the second half's 1X2 is whole


def test_a_whole_basketball_group_keeps_the_whole_group_path() -> None:
    def item(market: str, name: str, price: float, mid: int,
             code: str | None = None) -> dict[str, Any]:
        return {"marketId": mid, "marketName": market, "name": name, "price": price,
                "code": code, "specifiers": None, "status": "active", "tags": "v2",
                "info": ""}

    items = [item("Podwójna szansa", s, p, 201797, c) for s, p, c in
             (("1X", 1.08, "10"), ("X2", 2.9, "02"), ("12", 1.03, "12"))]
    items += [item("Mecz", s, p, 777, c) for s, p, c in
              (("1", 1.2, "1"), ("X", 15.0, "0"), ("2", 4.0, "2"))]
    on = parse_event(items, "basketball", "e", "A", "B", True, True)
    assert on == parse_event(items, "basketball", "e", "A", "B", True, False)
    assert {ln.market_id for ln in on} == {-1, 777}


def test_hockey_and_volleyball_are_unchanged() -> None:
    for ev in _events(HOCKEY_GOLDEN):
        assert _parse(ev, sport="hockey") == _parse(ev, dc_pair=False, sport="hockey")
        # a hockey group missing its 12 is still dropped, never paired
        odds = [o for o in ev["odds"]
                if not (o["marketId"] == 606 and o["name"] == "12")]
        lines = _parse({**ev, "odds": odds}, sport="hockey")
        assert not any(ln.market_id == 606 or ln.side in cs2.DC_PARTNER_SIDES
                       for ln in lines)
    vb = [{"marketId": 999001, "marketName": "Dokładna liczba setów", "name": n,
           "price": p, "code": None, "specifiers": None, "status": "active",
           "tags": "v2", "info": ""} for n, p in (("3", 2.2), ("4", 2.5), ("5", 3.9))]
    assert parse_event(vb, "volleyball", "e", "A", "B", True, True) == parse_event(
        vb, "volleyball", "e", "A", "B", True, False)


# --- prices: the pair is a two-way line --------------------------------------------


def test_the_pair_devigs_as_a_two_way_line_and_its_margin_is_the_sum() -> None:
    pair = {"1X": 2.57, "2": 1.41}
    fair = cs2.group_fair(pair, "double")
    assert fair is not None
    assert fair["1X"] == pytest.approx(cs2.fair_probability(2.57, 1.41))
    assert fair["1X"] + fair["2"] == pytest.approx(1.0)
    assert cs2.group_overround(pair) == pytest.approx(1 / 2.57 + 1 / 1.41 - 1)
    assert 0.09 < cs2.group_overround(pair) < 0.10
    # what is not a pair stays incomplete: the two selections alone, a wrong
    # complement, a selection with a 1X2 outcome it overlaps
    for bad in ({"1X": 2.57, "X2": 1.27}, {"1X": 2.57, "1": 3.3},
                {"X2": 1.27, "2": 1.41}):
        assert not cs2.complete_group(set(bad), "double")
        assert cs2.group_fair(bad, "double") is None
    # the whole group is what it was
    whole = {"1X": 1.35, "X2": 1.66, "12": 1.26}
    assert cs2.group_overround(whole) == pytest.approx(
        (1 / 1.35 + 1 / 1.66 + 1 / 1.26) / 2 - 1)


def _bb(t1: tuple[int, ...], t2: tuple[int, ...], t1f: int, t2f: int) -> GameResult:
    return GameResult(t1, t2, t1f, t2f, "T1" if t1f > t2f else "T2",
                      (t1f, t2f) != (sum(t1), sum(t2)))


def test_the_model_prices_a_pair_side_as_the_double_chance() -> None:
    sims = [_bb((20, 20, 20, 20), (20, 20, 20, 20), 90, 85),  # level, OT
            _bb((25, 20, 20, 20), (20, 20, 20, 20), 85, 80),
            _bb((20, 20, 20, 20), (25, 25, 20, 20), 80, 90)]

    def p(mid: int, family: str, side: str) -> float | None:
        return line_probability(ShadowLine("", mid, family, 0, "", None, side, 1.0),
                                sims, BASKETBALL)

    assert p(-101, "double_chance", "1X") == pytest.approx(
        p(-1, "double_chance", "1X"))  # type: ignore[arg-type]
    assert p(-101, "double_chance", "1X") == pytest.approx(2 / 3)
    assert p(-101, "double_chance", "2") == pytest.approx(
        p(777, "result_1x2", "T2"))  # type: ignore[arg-type]


# --- SHADOW_SETTLE: regulation, the partner is no row ------------------------------


def _event(lines: list[ShadowLine]) -> SnapshotEvent:
    ev = SnapshotEvent("14175125", "B·S", "Brisbane Bullets", "SE Melbourne Phoenix",
                       "2026-10-16T09:30:00Z", None)
    for ln in lines:
        key = (*ln.key(), ln.side)
        ev.sides[key] = ln
        ev.fetched_at[key] = "2026-10-16T08:00:00Z"
    return ev


def test_pairs_grade_on_regulation_and_the_partner_is_no_row() -> None:
    """80-80 after regulation, 90-85 after overtime: the 1X2 777 is a DRAW,
    so 1X and X2 both win; the second half (Q3+Q4) is level too."""
    lines = _parse(_events()[0])
    result = _bb((20, 20, 20, 20), (20, 20, 20, 20), 90, 85)
    assert (sum(result.t1_periods), sum(result.t2_periods)) == (80, 80)
    rows, counts = settle_event(_event(lines), result, BASKETBALL)
    pairs = {(r["market_id"], r["side"]): r for r in rows if r["market_id"] < -100}
    assert set(pairs) == {(-101, "1X"), (-102, "X2"), (-301, "1X"), (-302, "X2")}
    assert not any(r["side"] in cs2.DC_PARTNER_SIDES for r in rows)
    assert counts["unpaired"] == 0
    assert pairs[(-101, "1X")]["outcome"] == "WIN"
    assert pairs[(-102, "X2")]["outcome"] == "WIN"
    assert {r["outcome"] for r in rows if r["market_id"] == 777} == {"WIN", "LOSS"}
    assert next(r for r in rows if r["market_id"] == 777 and r["side"] == "DRAW")[
        "outcome"] == "WIN"
    one_x = pairs[(-101, "1X")]
    assert one_x["partner_odds"] == 1.41
    assert one_x["fair_p"] == pytest.approx(cs2.fair_probability(2.57, 1.41))
    assert one_x["overround"] == pytest.approx(1 / 2.57 + 1 / 1.41 - 1)
    assert pairs[(-301, "1X")]["outcome"] == "WIN"
    assert pairs[(-302, "X2")]["outcome"] == "WIN"
    # a regulation team2 win (80-85, second half 40-45): 1X loses, X2 wins
    rows2, _ = settle_event(_event(lines), _bb((20, 20, 20, 20), (20, 20, 20, 25),
                                                80, 85), BASKETBALL)
    got = {(r["market_id"], r["side"]): r["outcome"] for r in rows2
           if r["market_id"] in (-101, -102, -301, -302)}
    assert got == {(-101, "1X"): "LOSS", (-102, "X2"): "WIN",
                   (-301, "1X"): "LOSS", (-302, "X2"): "WIN"}


def test_a_partner_side_grades_as_the_one_result_it_names() -> None:
    for side, level, t1, t2 in (("2", "LOSS", "LOSS", "WIN"),
                                ("1", "LOSS", "WIN", "LOSS"),
                                ("X", "WIN", "LOSS", "LOSS")):
        ln = ShadowLine("", -101, "double_chance", 0, "", None, side, 1.4)
        assert (grade(ln, 0.0), grade(ln, 3.0), grade(ln, -3.0)) == (level, t1, t2)


# --- SHADOW: the snapshot record -------------------------------------------------


class _Board:
    def __init__(self) -> None:
        self.ev = _events()[0]

    def events_by_date(self, start: datetime, end: datetime, offer_state: str
                       ) -> list[dict[str, Any]]:
        return [{"sportId": 4, "eventId": self.ev["eventId"],
                 "matchName": self.ev["matchName"],
                 "utcDate": "2026-10-16T23:00:00Z", "tournamentId": 127}]

    def event_odds(self, event_id: str) -> dict[str, Any]:
        return {"odds": self.ev["odds"]}

    def _get_json(self, path: str) -> dict[str, Any]:
        return {"data": {"tournaments": []}}


def _snapshot(tmp_path: Path) -> dict[str, Any]:
    if "scripts.sofa.run_shadow" in sys.modules:
        run_shadow = sys.modules["scripts.sofa.run_shadow"]
    else:
        run_shadow = importlib.import_module("scripts.sofa.run_shadow")
    at = datetime(2026, 10, 16, 20, tzinfo=UTC)
    run_shadow.snapshot("2026-10-16", _Board(), str(tmp_path), at=at)
    path = tmp_path / "shadow" / "basketball" / "2026-10-16" / "snapshots.jsonl"
    (rec,) = [json.loads(x) for x in path.read_text().splitlines()]
    return dict(rec)


def test_snapshot_off_is_what_it_was(tmp_path: Path,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "BASKETBALL_DC_PAIR_FROM_UTC", None)
    rec = _snapshot(tmp_path)
    assert "dc_pair_rule" not in rec and rec["derived_rule"] == "sport_derived_v1"
    assert rec["lines"] == [ln.as_dict() for ln in _parse(_events()[0], dc_pair=False)]


def test_snapshot_on_adds_the_pairs(tmp_path: Path) -> None:
    rec = _snapshot(tmp_path)
    assert rec["dc_pair_rule"] == "basketball_dc_pair_v1"
    assert rec["lines"] == [ln.as_dict() for ln in _parse(_events()[0])]
    assert {ln["market_id"] for ln in rec["lines"]} >= {-101, -102, -301, -302}


# --- SPORT_CONFIDENCE: the pair side is a leg, the partner never ---------------------


class _Forecaster:
    def probability(self, sport: str, fixture: Any, ev: Any, line: Any) -> float | None:
        return {"1X": 0.80, "X2": 0.80, "2": 0.20, "1": 0.20}.get(line.side, 0.5)

    def sample(self, sport: str, fixture: Any, ev: Any, line: Any) -> tuple[int, int]:
        return 7, 10


class _Evidence:
    def read(self, sport: str, key: str, p: float, base: Any,
             odds: float | None = None) -> Any:
        if key != "double_chance|TEAM":
            return None
        return SimpleNamespace(value=0.80, n=400, source=f"{sport}:{key}",
                               offset=0.0, band_cap=None)


def test_sport_confidence_prints_the_pair_side_never_the_partner(
        tmp_path: Path) -> None:
    rsc = importlib.import_module("scripts.sofa.run_sport_confidence")
    si = importlib.import_module("bet.sofa.sport_identity")
    date = "2026-10-16"
    at = datetime(2026, 10, 16, 6, 0, tzinfo=UTC)
    pair = [ln.as_dict() for ln in _parse(_events()[0])
            if ln.market_id in (-101, -102)]
    day = tmp_path / "shadow" / "basketball" / date
    day.mkdir(parents=True)
    (day / "snapshots.jsonl").write_text(json.dumps({
        "fetched_at_utc": "2026-10-16T05:50:00Z", "superbet_event_id": "14175125",
        "match_name": "Brisbane Bullets·SE Melbourne Phoenix",
        "team1": "Brisbane Bullets", "team2": "SE Melbourne Phoenix",
        "kickoff_utc": "2026-10-16T09:30:00Z", "tournament": "Australia - NBL",
        "lines": pair}) + "\n")
    fixtures = {"date": date, "sports_run": ["basketball"], "fixtures": [{
        "superbet_event_id": "14175125", "sport": "basketball",
        "status": si.IDENTIFIED, "sofascore_event_id": 9001, "home_id": 10,
        "away_id": 20, "home_is_team1": True, "competition_id": 55,
        "sofascore_start_utc": "2026-10-16T09:30:00Z"}]}
    cal_path = tmp_path / "cal.json"
    curve = {"0.800-0.825": {"n": 400, "realised": 0.84, "realised_lo95": 0.80}}
    cal_path.write_text(json.dumps({
        "min_bucket": 200, "fitted_from": {"before": "2026-10-05"},
        "sports": {"basketball": {"curves": {"double_chance|TEAM": curve},
                                  "admitted": ["double_chance|TEAM"]}}}))
    cal = scf.SportCalibration.load(cal_path)
    entry, legs = rsc.build_sport("basketball", date, str(tmp_path), fixtures, cal,
                                  _Forecaster(), at, evidence=_Evidence())
    assert entry["status"] == "OK"
    got = {(leg["market_id"], leg["side"]): leg for leg in legs}
    # 1X 2.57 x 0.80 and X2 1.27 x 0.80 = 1.016: both print; "1" / "2" never
    assert set(got) == {(-101, "1X"), (-102, "X2")}
    one_x = got[(-101, "1X")]
    assert one_x["family"] == "double_chance" and one_x["subject"] == ""
    assert one_x["overround"] == pytest.approx(1 / 2.57 + 1 / 1.41 - 1, abs=1e-4)
    assert one_x["dc_pair_rule"] == "basketball_dc_pair_v1"
    assert one_x["derived_rule"] == "sport_derived_v1"
    assert "INCOMPLETE_GROUP" not in entry["refused"]
    assert entry["refused"].get("MARKET_NOT_ALLOWED", 0) == 0


def test_pair_ids_are_allowed_only_with_the_derived_markets() -> None:
    for mid, spec in shadow.DC_PAIR_MARKETS["basketball"].items():
        assert scf.family_of("basketball", mid, spec.family, True) is None
        assert scf.family_of("basketball", mid, spec.family, True, True) == spec.family
    # the history replay never scores the pair ids (it scores the double chance)
    assert not set(scf.DERIVED_HISTORY_MARKETS["basketball"]) & set(
        shadow.DC_PAIR_MARKETS["basketball"])
    assert scf.curve_key("double_chance", "1X") == "double_chance|TEAM"
