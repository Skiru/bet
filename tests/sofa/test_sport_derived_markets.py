"""The measured sports' derived markets behind
epochs.SPORT_DERIVED_MARKETS_FROM_UTC (None): hockey / basketball double
chance, volleyball's team sets and sets count. Offline and fast.

The hockey shape is Superbet's own (tests/sofa/golden/
superbet_hockey_double_chance_2026-10-13.json, Kitchener - London and
Montreal - Buffalo, pre-match 2026-10-13): "Podwójna szansa" 606 1X / X2 / 12
(codes 10 / 02 / 12) beside "Mecz" 640, "1. tercja - podwójna szansa" 616
with `periodnr`. Basketball and volleyball are read by name; their items here
are built from the market-coverage probe's names (no payload was at hand).
"""

from __future__ import annotations

import importlib
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import cs2, epochs, leg_relations, shadow
from bet.sofa import sport_confidence as scf
from bet.sofa.line_evidence import LineEvidence
from bet.sofa.score_model import line_probability
from bet.sofa.shadow import (
    SPORTS,
    GameResult,
    ShadowLine,
    SnapshotEvent,
    actual_value,
    grade,
    parse_event,
    settle_event,
)
from bet.sofa.superbet import odds_items, split_match_name

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests/sofa/golden/superbet_hockey_double_chance_2026-10-13.json"
HOCKEY, BASKETBALL, VOLLEYBALL = (
    SPORTS["hockey"], SPORTS["basketball"], SPORTS["volleyball"])
ON = datetime(2026, 10, 15, 0, 0, tzinfo=UTC)


def _events() -> list[dict[str, Any]]:
    doc = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return list(doc["events"])


def _parse(ev: dict[str, Any], derived: bool) -> list[ShadowLine]:
    t1, t2 = split_match_name(ev["matchName"])
    assert t1 and t2
    return parse_event(odds_items(ev), "hockey", str(ev["eventId"]), t1, t2, derived)


def _item(market: str, name: str, price: float, market_id: int = 999001,
          code: str | None = None, spec: dict[str, str] | None = None
          ) -> dict[str, Any]:
    return {"marketId": market_id, "marketName": market, "name": name,
            "price": price, "code": code, "specifiers": spec, "status": "active",
            "tags": "v2", "info": ""}


# --- the switch ------------------------------------------------------------------


def test_switch_is_on_from_the_operators_time() -> None:
    # operator 2026-10-14: on from 14:50Z into the built day (mixed)
    on = datetime(2026, 10, 14, 14, 50, 0, tzinfo=UTC)
    assert epochs.SPORT_DERIVED_MARKETS_FROM_UTC == on
    assert epochs.sport_derived_markets("2026-10-14", on)
    assert not epochs.sport_derived_markets("2026-10-13", on)
    assert epochs.SPORT_DERIVED_MARKETS == "sport_derived_v1"


def test_switch_reads_the_day_and_the_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "SPORT_DERIVED_MARKETS_FROM_UTC", ON)
    assert epochs.sport_derived_markets("2026-10-15", ON)
    assert not epochs.sport_derived_markets("2026-10-14", ON)
    assert not epochs.sport_derived_markets("2026-10-15", datetime(2026, 10, 14, 23,
                                                                   tzinfo=UTC))


# --- SHADOW: reading -------------------------------------------------------------


def test_hockey_double_chance_read_from_the_real_payload() -> None:
    kitchener, montreal = _events()
    off = _parse(kitchener, False)
    on = _parse(kitchener, True)
    assert not any(ln.family.endswith("double_chance") for ln in off)
    extra = [ln for ln in on if ln not in off]
    assert [ln for ln in on if ln in off] == off  # the rest untouched, in order
    game = {ln.side: ln.odds for ln in extra if ln.market_id == 606}
    assert game == {"1X": 1.6, "X2": 1.39, "12": 1.17}
    assert all(ln.family == "double_chance" and ln.period == 0 and ln.line is None
               for ln in extra if ln.market_id == 606)
    period = {(ln.period, ln.side): ln.odds for ln in extra if ln.market_id == 616}
    assert period == {(1, "1X"): 1.42, (1, "12"): 1.35, (1, "X2"): 1.33}
    assert {ln.family for ln in extra} == {"double_chance", "period_double_chance"}
    mtl = {ln.side: ln.odds for ln in _parse(montreal, True) if ln.market_id == 606}
    assert mtl == {"1X": 1.32, "X2": 1.66, "12": 1.19}


def test_a_double_chance_code_that_disagrees_drops_the_side() -> None:
    kitchener = _events()[0]
    odds = [dict(o) for o in kitchener["odds"]]
    for o in odds:
        if o["marketId"] == 606 and o["name"] == "1X":
            o["code"] = "02"
    lines = _parse({**kitchener, "odds": odds}, True)
    assert not any(ln.market_id == 606 for ln in lines)  # incomplete group


def test_basketball_double_chance_read_by_name() -> None:
    t1, t2 = "Besiktas", "Galatasaray"
    items = [
        *(_item("Podwójna szansa", s, p, code=c) for s, p, c in
          (("1X", 1.08, "10"), ("X2", 2.9, "02"), ("12", 1.03, "12"))),
        *(_item("2. połowa - podwójna szansa", s, p) for s, p in
          (("1X", 1.2), ("X2", 1.9), ("12", 1.05))),
        *(_item("1. kwarta - podwójna szansa", s, p) for s, p in
          (("1X", 1.3), ("X2", 1.7), ("12", 1.1))),
        *(_item("Podwójna szansa (z dogrywką)", s, 1.5) for s in ("1X", "X2", "12")),
    ]
    assert parse_event(items, "basketball", "e", t1, t2) == []
    lines = parse_event(items, "basketball", "e", t1, t2, True)
    got = {(ln.market_id, ln.family, ln.period, ln.side) for ln in lines}
    assert got == {
        *((-1, "double_chance", 0, s) for s in ("1X", "X2", "12")),
        *((-3, "h2_double_chance", 0, s) for s in ("1X", "X2", "12")),
        *((-4, "quarter_double_chance", 1, s) for s in ("1X", "X2", "12")),
    }


def test_volleyball_team_sets_and_sets_count_read_by_name() -> None:
    t1, t2 = "Aras Kargo (K)", "Galatasaray (K)"
    items = [
        _item("Aras Kargo (K) wygra seta", "Tak", 1.4),
        _item("Aras Kargo (K) wygra seta", "Nie", 2.7),
        _item("Galatasaray (K) wygra dokładnie 2 sety", "Tak", 3.5),
        _item("Galatasaray (K) wygra dokładnie 2 sety", "Nie", 1.25),
        _item("Aras Kargo (K) wygra dokładnie 1 set", "Tak", 3.1),
        _item("Aras Kargo (K) wygra dokładnie 1 set", "Nie", 1.3),
        *(_item("Dokładna liczba setów", n, p) for n, p in
          (("3", 2.2), ("4", 2.5), ("5", 3.9))),
    ]
    assert parse_event(items, "volleyball", "e", t1, t2) == []
    lines = parse_event(items, "volleyball", "e", t1, t2, True)
    got = {(ln.market_id, ln.family, ln.subject, ln.line, ln.side) for ln in lines}
    assert got == {
        *((-11, "team_wins_set", "T1", None, s) for s in ("YES", "NO")),
        *((-14, "team_sets_exact", "T2", 2.0, s) for s in ("YES", "NO")),
        *((-13, "team_sets_exact", "T1", 1.0, s) for s in ("YES", "NO")),
        *((-15, "sets_count", "", None, f"SETS={n}") for n in (3, 4, 5)),
    }
    # a name read twice (two Superbet markets under one name) is ambiguous:
    # the group is dropped, never one of the two picked
    twice = [*items, _item("Dokładna liczba setów", "3", 2.0, market_id=999002)]
    assert not any(ln.family == "sets_count"
                   for ln in parse_event(twice, "volleyball", "e", t1, t2, True))
    # an outcome name that is not a count is no side: the group is incomplete
    odd = [*items[:6], *(_item("Dokładna liczba setów", n, 2.5)
                         for n in ("3:0", "4", "5"))]
    assert not any(ln.family == "sets_count"
                   for ln in parse_event(odd, "volleyball", "e", t1, t2, True))


# --- SHADOW: the snapshot is byte-identical off -------------------------------------


class _Board:
    def __init__(self) -> None:
        self.ev = _events()[0]

    def events_by_date(self, start: datetime, end: datetime, offer_state: str
                       ) -> list[dict[str, Any]]:
        return [{"sportId": 3, "eventId": self.ev["eventId"],
                 "matchName": self.ev["matchName"],
                 "utcDate": "2026-10-15T23:00:00Z", "tournamentId": 127}]

    def event_odds(self, event_id: str) -> dict[str, Any]:
        return {"odds": self.ev["odds"]}

    def _get_json(self, path: str) -> dict[str, Any]:
        return {"data": {"tournaments": []}}


def _snapshot(tmp_path: Path) -> dict[str, Any]:
    if "scripts.sofa.run_shadow" in sys.modules:
        run_shadow = sys.modules["scripts.sofa.run_shadow"]
    else:
        run_shadow = importlib.import_module("scripts.sofa.run_shadow")
    at = datetime(2026, 10, 15, 20, tzinfo=UTC)
    run_shadow.snapshot("2026-10-15", _Board(), str(tmp_path), at=at)
    path = tmp_path / "shadow" / "hockey" / "2026-10-15" / "snapshots.jsonl"
    (rec,) = [json.loads(x) for x in path.read_text().splitlines()]
    return dict(rec)


def test_snapshot_off_is_what_it_was(tmp_path: Path,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "SPORT_DERIVED_MARKETS_FROM_UTC", None)
    rec = _snapshot(tmp_path)
    assert "derived_rule" not in rec
    assert rec["lines"] == [ln.as_dict() for ln in _parse(_events()[0], False)]


def test_snapshot_on_adds_the_derived_lines(tmp_path: Path,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "SPORT_DERIVED_MARKETS_FROM_UTC", ON)
    rec = _snapshot(tmp_path)
    assert rec["derived_rule"] == "sport_derived_v1"
    assert {ln["market_id"] for ln in rec["lines"]} >= {606, 616}


# --- prices: devig, margin, the model --------------------------------------------


def test_double_chance_devigs_to_two_and_its_margin_is_halved() -> None:
    odds = {"1X": 1.35, "X2": 1.66, "12": 1.26}
    fair = cs2.group_fair(odds, "double")
    assert fair is not None and abs(sum(fair.values()) - 2.0) < 1e-12
    total = 1 / 1.35 + 1 / 1.66 + 1 / 1.26
    assert abs(cs2.group_overround(odds) - (total / 2 - 1)) < 1e-12
    assert 0.06 < cs2.group_overround(odds) < 0.075
    assert cs2.group_fair({"1X": 1.35, "X2": 1.66}, "double") is None
    # every other group's margin is what it was
    assert abs(cs2.group_overround({"T1": 1.9, "T2": 1.9}) - (2 / 1.9 - 1)) < 1e-12


def test_sets_count_is_a_partition() -> None:
    fair = cs2.group_fair({"SETS=3": 2.2, "SETS=4": 2.5, "SETS=5": 3.9}, "count")
    assert fair is not None and abs(sum(fair.values()) - 1.0) < 1e-9
    assert cs2.group_fair({"SETS=3": 2.2, "SETS=4": 2.5}, "count") is None


def _hockey(t1: tuple[int, ...], t2: tuple[int, ...], t1f: int, t2f: int,
            winner: str | None) -> GameResult:
    return GameResult(t1, t2, t1f, t2f, winner, (t1f, t2f) != (sum(t1), sum(t2)))  # type: ignore[arg-type]


def test_model_double_chance_sums_the_1x2() -> None:
    sims = [_hockey((1, 0, 1), (0, 1, 0), 2, 1, "T1"),
            _hockey((0, 1, 1), (1, 0, 1), 3, 2, "T1"),  # 2-2, OT win
            _hockey((0, 0, 0), (1, 1, 0), 0, 2, "T2"),
            _hockey((1, 1, 0), (0, 0, 0), 2, 0, "T1")]
    p = {s: line_probability(ShadowLine("", 606, "double_chance", 0, "", None, s, 1.0),
                             sims, HOCKEY) for s in ("1X", "X2", "12")}
    one_x_two = {s: line_probability(
        ShadowLine("", 640, "result_1x2", 0, "", None, s, 1.0), sims, HOCKEY)
        for s in ("T1", "DRAW", "T2")}
    assert p["1X"] == pytest.approx(one_x_two["T1"] + one_x_two["DRAW"])  # type: ignore[operator]
    assert p["X2"] == pytest.approx(one_x_two["T2"] + one_x_two["DRAW"])  # type: ignore[operator]
    assert p["12"] == pytest.approx(one_x_two["T1"] + one_x_two["T2"])  # type: ignore[operator]
    assert sum(v for v in p.values() if v is not None) == pytest.approx(2.0)


def test_volleyball_probabilities_from_the_simulated_set_score() -> None:
    def vb(t1: tuple[int, ...], t2: tuple[int, ...]) -> GameResult:
        s1 = sum(a > b for a, b in zip(t1, t2, strict=True))
        return GameResult(t1, t2, s1, len(t1) - s1, "T1" if s1 == 3 else "T2", False)

    sims = [vb((25, 25, 25), (20, 20, 20)),          # 3:0
            vb((25, 20, 25, 25), (20, 25, 20, 20)),  # 3:1
            vb((20, 20, 25, 25, 10), (25, 25, 20, 20, 15))]  # 2:3

    def p(mid: int, side: str, line: float | None = None, subject: str = "") -> float:
        fam = shadow.DERIVED_MARKETS["volleyball"][mid].family
        got = line_probability(ShadowLine("", mid, fam, 0, subject, line, side, 1.0),
                               sims, VOLLEYBALL)
        assert got is not None
        return got

    assert p(-12, "YES", subject="T2") == pytest.approx(2 / 3)
    assert p(-11, "YES", subject="T1") == pytest.approx(1.0)
    assert p(-14, "YES", 2.0, "T2") == pytest.approx(0.0)
    assert p(-14, "YES", 3.0, "T2") == pytest.approx(1 / 3)
    assert p(-13, "YES", 2.0, "T1") == pytest.approx(1 / 3)
    assert [p(-15, f"SETS={n}") for n in (3, 4, 5)] == pytest.approx([1 / 3] * 3)


# --- SHADOW_SETTLE: grading -------------------------------------------------------


def test_hockey_double_chance_grades_on_regulation_like_the_1x2() -> None:
    """2-2 after regulation, won in overtime: the 1X2 640 is a DRAW, so the
    double chance 1X and X2 win and 12 loses (scope "reg", as result_1x2)."""
    result = GameResult((1, 1, 0), (0, 1, 1), 3, 2, "T1", True)
    lines = _parse(_events()[0], True)
    ev = SnapshotEvent("15196264", "K·L", "Kitchener Rangers", "London Knights",
                       "2026-10-13T23:00:00Z", None)
    for ln in lines:
        key = (*ln.key(), ln.side)
        ev.sides[key] = ln
        ev.fetched_at[key] = "2026-10-13T22:00:00Z"
    rows, _ = settle_event(ev, result, HOCKEY)
    got = {(r["market_id"], r["period"], r["side"]): r["outcome"] for r in rows
           if r["market_id"] in (606, 616, 640)}
    assert got[(640, 0, "DRAW")] == "WIN"
    assert got[(606, 0, "1X")] == "WIN" and got[(606, 0, "X2")] == "WIN"
    assert got[(606, 0, "12")] == "LOSS"
    # the first period was 1-0: 1X and 12 win, X2 loses
    assert (got[(616, 1, "1X")], got[(616, 1, "12")], got[(616, 1, "X2")]) == (
        "WIN", "WIN", "LOSS")
    dc = [r for r in rows if r["market_id"] == 606]
    assert sum(r["fair_p"] for r in dc) == pytest.approx(2.0)
    assert all(r["overround"] == pytest.approx(
        (1 / 1.6 + 1 / 1.39 + 1 / 1.17) / 2 - 1) for r in dc)


def test_final_only_game_grades_the_game_double_chance_from_regulation() -> None:
    result = GameResult((), (), 4, 3, "T1", True, reg_score=(3, 3))
    line = ShadowLine("", 606, "double_chance", 0, "", None, "12", 1.17)
    assert actual_value(line, result, HOCKEY) == 0.0
    assert grade(line, 0.0) == "LOSS"
    period = ShadowLine("", 616, "period_double_chance", 1, "", None, "1X", 1.4)
    assert actual_value(period, result, HOCKEY) is None


def test_volleyball_derived_grading() -> None:
    result = GameResult((25, 20, 25, 25), (20, 25, 20, 20), 3, 1, "T1", False)
    cases = [((-11, "T1", None, "YES"), "WIN"), ((-12, "T2", None, "NO"), "LOSS"),
             ((-14, "T2", 1.0, "YES"), "WIN"), ((-13, "T1", 2.0, "YES"), "LOSS"),
             ((-15, "", None, "SETS=4"), "WIN"), ((-15, "", None, "SETS=3"), "LOSS")]
    for (mid, subject, line, side), want in cases:
        fam = shadow.DERIVED_MARKETS["volleyball"][mid].family
        ln = ShadowLine("", mid, fam, 0, subject, line, side, 2.0)
        actual = actual_value(ln, result, VOLLEYBALL)
        assert actual is not None
        assert grade(ln, actual) == want, (mid, side)


# --- SPORT_CONFIDENCE: allowed only on; no curve, no evidence, nothing prints -----


def test_derived_families_are_allowed_only_when_on() -> None:
    for sport in ("hockey", "basketball", "volleyball"):
        for mid, spec in shadow.DERIVED_MARKETS[sport].items():  # type: ignore[index]
            assert scf.family_of(sport, mid, spec.family, True) is None
            assert scf.family_of(sport, mid, spec.family, True, True) == spec.family
            assert mid not in scf.allowed_markets(sport, extended=True)
    assert scf.side_class("12") == "12" and scf.side_class("1X") == "TEAM"
    assert scf.side_class("SETS=4") == "SETS=4"


# Installed 2026-10-15 00:17Z: the derived keys that passed the one-sided
# holdout gate ("TEAM" = 1X / X2; "12" refused by policy).
INSTALLED_DERIVED = {("hockey", "double_chance", "TEAM"),
                     ("hockey", "period_double_chance", "TEAM"),
                     ("basketball", "double_chance", "TEAM"),
                     ("volleyball", "team_sets_exact", "NO"),
                     ("volleyball", "team_wins_set", "YES")}


def _installed(sport: str, family: str, side: str) -> bool:
    team = "TEAM" if side in ("1X", "X2") else side
    return (sport, family, team) in INSTALLED_DERIVED


def test_derived_keys_without_a_curve_are_no_line_evidence() -> None:
    """A derived key the gate refused has no curve; with no settled line in
    the installed evidence its every read is NO_LINE_EVIDENCE. A key that
    passed reads its curve somewhere at or above the floor."""
    rsc = importlib.import_module("scripts.sofa.run_sport_confidence")
    date = "2026-10-15"
    cal = scf.SportCalibration.load(scf.calibration_path_for(date))
    assert cal is not None
    evidence = LineEvidence.load(v2=True, bucket_deff=True)
    sides = {"double_chance": ("1X", "X2", "12"), "set_yes_no": ("YES", "NO"),
             "sets_count": ("SETS=3", "SETS=4", "SETS=5")}
    for sport in ("hockey", "basketball", "volleyball"):
        for spec in shadow.DERIVED_MARKETS[sport].values():  # type: ignore[index]
            for side in sides[spec.kind]:
                reads = [rsc.read_confidence(cal, evidence, sport, spec.family,
                                             side, p, 1.3)
                         for p in (0.55, 0.7, 0.8, 0.9, 0.97)]
                if _installed(sport, spec.family, side):
                    assert any(r[0] is not None for r in reads), (
                        sport, spec.family, side)
                    continue
                for conf, _, _, why in reads:
                    if evidence.read(sport, scf.curve_key(spec.family, side),
                                     0.8, None, 1.3) is not None:
                        break  # its own settled lines arrived (morning refresh)
                    assert conf is None and why == "NO_LINE_EVIDENCE", (
                        sport, spec.family, side)


def test_history_replay_scores_only_the_markets_asked() -> None:
    sims = [_hockey((1, 0, 1), (0, 1, 0), 2, 1, "T1")]
    lines = scf.synthetic_lines(HOCKEY, 616, sims, 2)
    assert {(ln.period, ln.side) for ln in lines} == {(2, "1X"), (2, "X2"), (2, "12")}
    assert scf.market_periods(HOCKEY, 616) == (1, 2, 3)
    assert set(scf.DERIVED_HISTORY_MARKETS["volleyball"]) == {-11, -12, -13, -14, -15}
    vb = scf.synthetic_lines(VOLLEYBALL, -13, [], 0)
    assert {(ln.line, ln.side) for ln in vb} == {(1.0, "YES"), (1.0, "NO"),
                                                  (2.0, "YES"), (2.0, "NO")}


# --- the coupon's relations -----------------------------------------------------


def test_double_chance_is_a_difference_interval() -> None:
    one_x = leg_relations.proposition(
        {"sport": "hockey", "family": "double_chance", "side": "1X", "period": 0})
    t1 = leg_relations.proposition(
        {"sport": "hockey", "family": "result_1x2", "side": "T1", "period": 0})
    assert one_x is not None and t1 is not None
    assert one_x.quantity == t1.quantity
    assert (one_x.lo, one_x.hi) == (0.0, None)
    assert leg_relations.proposition(
        {"sport": "hockey", "family": "double_chance", "side": "12"}) is None
    assert leg_relations.proposition(
        {"sport": "volleyball", "family": "sets_count", "side": "SETS=3"}) is None


# --- the measurement (scripts/sofa/measure_sport_derived.py) ----------------------


def test_measurement_summary_against_the_base_rate() -> None:
    msd = importlib.import_module("scripts.sofa.measure_sport_derived")
    rows = [{"family": "double_chance", "period": 0, "subject": "", "line": None,
             "side": "12", "key": "double_chance|12", "p": p, "y": y,
             "game": f"h:{i}"}
            for i, (p, y) in enumerate([(0.9, 1), (0.8, 1), (0.75, 0), (0.6, 1)])]
    base = {("double_chance", 0, "", None, "12"): 0.78}
    out = msd.summarise(rows, base)["double_chance|12"]
    assert out["n"] == 4 and out["games"] == 4
    assert out["printable_n"] == 3
    assert out["printable_realised"] == pytest.approx(2 / 3, abs=1e-4)
    want = (-3 * math.log(0.78) - math.log(0.22)) / 4
    assert out["logloss_base"] == pytest.approx(want, abs=1e-5)
    assert out["diff_lo"] <= out["diff"] <= out["diff_hi"]
    # a line with no base rate is left out, never compared with nothing
    other = {**rows[0], "side": "1X", "key": "double_chance|TEAM"}
    assert msd.summarise([other], base) == {}
