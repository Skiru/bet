"""Volleyball "1.Set/Mecz" (Superbet 230059) behind epochs.VB_SET1_MATCH_FROM_UTC
- plan docs/sofa/history/PLAN_NOWE_RYNKI_2026-11-20.md section 5. Offline, fast.

The odds are Superbet's own, as SHADOW's unmapped_prices recorded them
(runs/sofa/2026-11-15/unmapped_prices/volleyball_20261114T070138.253746Z.jsonl.gz,
event 15721202 "ABEL/Moda (K)" - "Brasilia (K)", fetched 2026-11-14 07:02Z:
1.75 / 7.9 / 4.7 / 4.4 - a team name holding a "/"). The results are
Sofascore's (minimal payloads of 16562455 AET with a golden set, 17267101
1-3, 17193834 3-2, and a 3-0).
"""

from __future__ import annotations

import gzip
import hashlib
import importlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from bet.sofa import cs2, epochs, leg_identity, leg_relations, shadow, superbet_names
from bet.sofa import sport_confidence as scf
from bet.sofa import vb_point_pricer as vpp
from bet.sofa import volleyball_point_model as vpm
from bet.sofa.config import config_path
from bet.sofa.shadow import SPORTS, ShadowLine, actual_value, build_result, grade

VB = SPORTS["volleyball"]
ON = datetime(2026, 11, 22, 0, 0, tzinfo=UTC)
T1, T2 = "ABEL/Moda (K)", "Brasilia (K)"
QUOTES = {f"{T1}/{T1}": 1.75, f"{T1}/{T2}": 7.9, f"{T2}/{T1}": 4.7, f"{T2}/{T2}": 4.4}


def _item(name: str, price: float, mid: int = 230059, market: str = "1.Set/Mecz",
          code: str | None = None, status: str = "active") -> dict[str, Any]:
    return {"marketId": mid, "marketName": market, "name": name, "price": price,
            "status": status, "offerStateId": 1, "code": code}


def _winner() -> list[dict[str, Any]]:
    return [{"marketId": 745, "marketName": "Zwycięzca", "name": T1, "price": 1.28,
             "status": "active", "code": "1", "info": "", "specifiers": None,
             "tags": ""},
            {"marketId": 745, "marketName": "Zwycięzca", "name": T2, "price": 3.4,
             "status": "active", "code": "2", "info": "", "specifiers": None,
             "tags": ""}]


def _items() -> list[dict[str, Any]]:
    return _winner() + [_item(n, p) for n, p in QUOTES.items()]


# --- the switch -----------------------------------------------------------------------


def test_the_switch_starts_on_the_22nd_and_needs_the_rally_model(
        monkeypatch: pytest.MonkeyPatch) -> None:
    assert epochs.VB_SET1_MATCH_FROM_UTC == ON
    assert epochs.VB_SET1_MATCH_MARKETS == frozenset({230059})
    assert not epochs.vb_set1_match("2026-11-21", ON + timedelta(hours=5))
    assert not epochs.vb_set1_match("2026-11-22", ON - timedelta(minutes=1))
    assert epochs.vb_set1_match("2026-11-22", ON)
    monkeypatch.setattr(epochs, "VB_POINT_MODEL_FROM_UTC", None)
    assert not epochs.vb_set1_match("2026-11-22", ON)


def test_the_rally_scope_is_the_union_and_the_market_is_not_in_markets() -> None:
    assert vpp.in_scope("volleyball", 230059)
    assert all(vpp.in_scope("volleyball", m) for m in epochs.VB_POINT_MODEL_MARKETS)
    assert not vpp.in_scope("hockey", 230059)
    # its own table: never shadow.MARKETS (market_coverage / the allow-list
    # tests read that one), always spec_of
    assert 230059 not in shadow.MARKETS["volleyball"]
    spec = shadow.spec_of("volleyball", 230059)
    assert spec is not None and (spec.family, spec.kind, spec.scope) == (
        "set1_match", "set_match", "sets")
    assert shadow.group_shape("volleyball", 230059) == "joint"


# --- SHADOW: off byte for byte, on the four sides ------------------------------------


def test_off_reads_nothing_new_and_the_odds_stay_unmapped() -> None:
    off = shadow.parse_event(_items(), "volleyball", "15721202", T1, T2, True)
    assert off == shadow.parse_event(_winner(), "volleyball", "15721202", T1, T2, True)
    assert all(not shadow.reads_market(it, "volleyball", T1, T2, True)
               for it in _items() if it["marketId"] == 230059)
    assert shadow.parse_line(_item(f"{T1}/{T1}", 1.75), "volleyball", "e", T1, T2,
                             True) is None


def test_on_reads_the_four_sides_by_their_exact_names() -> None:
    lines = shadow.parse_event(_items(), "volleyball", "15721202", T1, T2, True,
                               set1_match=True)
    joint = {ln.side: ln.odds for ln in lines if ln.market_id == 230059}
    assert joint == {"T1/T1": 1.75, "T1/T2": 7.9, "T2/T1": 4.7, "T2/T2": 4.4}
    one = next(ln for ln in lines if ln.side == "T1/T1")
    assert (one.family, one.period, one.subject, one.line) == ("set1_match", 0, "",
                                                               None)
    assert all(shadow.reads_market(it, "volleyball", T1, T2, True, set1_match=True)
               for it in _items())
    # the margin over the four (the 15% rule judges it) and a fair p summing to 1
    assert cs2.group_overround(joint) == pytest.approx(0.1381, abs=1e-4)
    fair = cs2.group_fair(joint, "joint")
    assert fair is not None and sum(fair.values()) == pytest.approx(1.0)
    assert fair["T1/T1"] > fair["T2/T2"] > fair["T2/T1"] > fair["T1/T2"]


def test_an_incomplete_group_or_an_unknown_name_is_not_read() -> None:
    three = _winner() + [_item(n, p) for n, p in list(QUOTES.items())[:3]]
    lines = shadow.parse_event(three, "volleyball", "e", T1, T2, set1_match=True)
    assert not [ln for ln in lines if ln.market_id == 230059]
    assert not cs2.complete_group({"T1/T1", "T1/T2", "T2/T1"}, "joint")
    # a fuzzy name ("ABEL/Moda/ABEL/Moda", no "(K)") is never matched
    assert shadow.parse_line(_item("ABEL/Moda/ABEL/Moda", 1.75), "volleyball", "e",
                             T1, T2, set1_match=True) is None
    # suspended / a boost: not a line
    assert shadow.parse_line(_item(f"{T1}/{T1}", 1.75, status="suspended"),
                             "volleyball", "e", T1, T2, set1_match=True) is None
    # a code of a known form must agree with the name
    assert shadow.parse_line(_item(f"{T1}/{T2}", 7.9, code="12"), "volleyball", "e",
                             T1, T2, set1_match=True) is not None
    assert shadow.parse_line(_item(f"{T1}/{T2}", 7.9, code="21"), "volleyball", "e",
                             T1, T2, set1_match=True) is None
    # two teams whose names make one string twice: no answer
    assert shadow._set_match_side("A/A", "A", "A") is None
    # a name containing "/" that makes "A" + "/" + "A/A" == "A/A" + "/" + "A"
    assert shadow._set_match_side("A/A/A", "A", "A/A") is None
    # the real pair's four strings are four distinct sides (names hold "/")
    sides = {shadow._set_match_side(n, T1, T2) for n in QUOTES}
    assert sides == set(cs2.SET_MATCH_SET)


def _board_payload() -> dict[str, Any]:
    return {"odds": [dict(it, tags="") for it in _items()]}


class _Board:
    def events_by_date(self, start: datetime, end: datetime, offer_state: str
                       ) -> list[dict[str, Any]]:
        return [{"sportId": 1, "eventId": 15721202, "matchName": f"{T1}·{T2}",
                 "utcDate": "2026-11-22T22:00:00Z", "tournamentId": 208}]

    def event_odds(self, event_id: str) -> dict[str, Any]:
        return _board_payload()

    def _get_json(self, path: str) -> dict[str, Any]:
        return {"data": {"tournaments": []}}


def _snapshot(tmp_path: Path, at: datetime) -> tuple[dict[str, Any], list[Any]]:
    run_shadow = sys.modules.get("scripts.sofa.run_shadow") or importlib.import_module(
        "scripts.sofa.run_shadow")
    run_shadow.snapshot("2026-11-22", _Board(), str(tmp_path), at=at)
    day = tmp_path / "shadow" / "volleyball" / "2026-11-22"
    (rec,) = [json.loads(x) for x in (day / "snapshots.jsonl").read_text().splitlines()]
    unmapped = []
    for f in sorted((tmp_path / "2026-11-22" / "unmapped_prices").glob("*.jsonl.gz")):
        unmapped += [json.loads(x) for x in gzip.open(f, "rt")]
    return rec, unmapped


def test_snapshot_off_is_what_it_was(tmp_path: Path,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    at = datetime(2026, 11, 22, 12, tzinfo=UTC)
    monkeypatch.setattr(epochs, "VB_SET1_MATCH_FROM_UTC", None)
    rec, unmapped = _snapshot(tmp_path, at)
    assert epochs.VB_SET1_MATCH_LEG_FIELD not in rec
    assert {ln["market_id"] for ln in rec["lines"]} == {745}
    assert sorted(u["name"] for u in unmapped) == sorted(QUOTES)


def test_snapshot_on_records_the_market_and_the_rule(tmp_path: Path) -> None:
    rec, unmapped = _snapshot(tmp_path, datetime(2026, 11, 22, 12, tzinfo=UTC))
    assert rec[epochs.VB_SET1_MATCH_LEG_FIELD] == epochs.VB_SET1_MATCH
    assert {ln["side"] for ln in rec["lines"] if ln["market_id"] == 230059} == (
        cs2.SET_MATCH_SET)
    assert not unmapped  # read: it leaves unmapped_prices


# --- SHADOW_SETTLE: an indicator, never a margin --------------------------------------


def test_grade_side_reads_a_joint_side_as_an_indicator() -> None:
    # regression: "T1/T1" fell to the handicap branch - LOSS on a win, VOID on
    # a loss - whatever happened
    for side in cs2.SET_MATCH_SET:
        assert cs2.grade_side(side, 1.0, None, False) == "WIN"
        assert cs2.grade_side(side, 0.0, None, False) == "LOSS"
    won, decided = vpm.win_loss("T2/T1", np.array([1.0, 0.0]), None)
    assert won.tolist() == [True, False] and decided.all()


def _event(home: list[int], away: list[int], description: str = "Ended",
           winner: int | None = None) -> dict[str, Any]:
    hs = sum(1 for a, b in zip(home, away, strict=True) if a > b)
    aw = len(home) - hs
    def score(pts: list[int], cur: int) -> dict[str, Any]:
        return {"current": cur, "display": cur, "normaltime": cur,
                **{f"period{i + 1}": p for i, p in enumerate(pts)}}
    return {"status": {"type": "finished", "description": description},
            "winnerCode": winner or (1 if hs > aw else 2),
            "homeScore": score(home, hs), "awayScore": score(away, aw)}


def _graded(detail: dict[str, Any], home_is_t1: bool = True) -> dict[str, float]:
    result = build_result(detail, VB, home_is_t1, allow_final_only=True)
    assert result is not None
    out = {}
    for side in sorted(cs2.SET_MATCH_SET):
        ln = ShadowLine("e", 230059, "set1_match", 0, "", None, side, 2.0)
        got = actual_value(ln, result, VB)
        assert got is not None
        out[side] = got
    assert sum(out.values()) == 1.0  # one side of four wins
    return out


@pytest.mark.parametrize("detail, home_is_t1, winner", [
    # 17267101 Deajeon - Suwon 1-3: set 1 25-22 home, the match away
    (_event([25, 22, 23, 33], [22, 25, 25, 35]), True, "T1/T2"),
    (_event([25, 22, 23, 33], [22, 25, 25, 35]), False, "T2/T1"),
    # 17193834 Thunderbelles - Highrisers 3-2: set 1 17-25 away, the match home
    (_event([17, 21, 25, 25, 15], [25, 25, 20, 20, 12]), True, "T2/T1"),
    # a 3-0
    (_event([25, 25, 25], [20, 18, 22]), True, "T1/T1"),
    # 16562455 Lokomotiv Avia - Budva, AET: 3-2 in sets, then a golden set
    # 19-17 the tie's - it counts in nothing
    ({**_event([25, 22, 18, 28, 15], [16, 25, 25, 26, 8], "AET", 1)}, True, "T1/T1"),
])
def test_the_match_is_graded_on_set_one_and_its_own_sets(
        detail: dict[str, Any], home_is_t1: bool, winner: str) -> None:
    got = _graded(detail, home_is_t1)
    assert got[winner] == 1.0
    ln = ShadowLine("e", 230059, "set1_match", 0, "", None, winner, 2.0)
    assert grade(ln, 1.0) == "WIN"


def test_a_golden_set_never_turns_the_match() -> None:
    # 3-1 in sets for home, the golden set (and winnerCode) the away side's
    detail = _event([25, 25, 20, 25], [20, 21, 25, 22], "AGS", 2)
    detail["homeScore"]["overtime"] = 13
    detail["awayScore"]["overtime"] = 15
    assert _graded(detail)["T1/T1"] == 1.0


def test_settle_event_grades_the_group_once_each_side() -> None:
    result = build_result(_event([17, 21, 25, 25, 15], [25, 25, 20, 20, 12]), VB,
                          True, allow_final_only=True)
    assert result is not None
    lines = shadow.parse_event(_items(), "volleyball", "15721202", T1, T2,
                               set1_match=True)
    stamp = "2026-11-22T10:00:00Z"
    ev = shadow.SnapshotEvent("15721202", f"{T1}·{T2}", T1, T2, "2026-11-22T12:00:00Z",
                              None, {(*ln.key(), ln.side): ln for ln in lines},
                              {(*ln.key(), ln.side): stamp for ln in lines})
    rows, _ = shadow.settle_event(ev, result, VB)
    joint = {r["side"]: r for r in rows if r["market_id"] == 230059}
    assert {s: r["outcome"] for s, r in joint.items()} == {
        "T1/T1": "LOSS", "T1/T2": "LOSS", "T2/T1": "WIN", "T2/T2": "LOSS"}
    assert joint["T2/T1"]["overround"] == pytest.approx(0.1381, abs=1e-4)
    assert len(joint["T2/T1"]["group_odds"]) == 4


# --- the rally model: the joint off the same simulations ------------------------------


def _sim() -> vpm.VbSim:
    f = vpm.VbForecast(mu=0.25, var=0.02, sideout=0.66, women=False, rated=(20, 20))
    return vpm.simulate(f, vpp.PARAMS, n=4000, seed=vpp.seed_of(15721202))


def test_the_four_sides_partition_and_their_margins_are_the_read_markets() -> None:
    sim = _sim()
    p = {s: vpm.line_p(sim, 230059, 0, "", None, s) for s in cs2.SET_MATCH_SET}
    assert all(v is not None for v in p.values())
    q = {s: float(v) for s, v in p.items() if v is not None}
    assert sum(q.values()) == pytest.approx(1.0)
    set1 = vpm.line_p(sim, 744, 1, "", None, "T1")
    match = vpm.line_p(sim, 745, 0, "", None, "T1")
    assert set1 is not None and match is not None
    assert q["T1/T1"] + q["T1/T2"] == pytest.approx(set1)
    assert q["T1/T1"] + q["T2/T1"] == pytest.approx(match)
    # Superbet's orientation: the swapped simulation reads the mirror side
    s2 = sim.swapped()
    assert vpm.line_p(s2, 230059, 0, "", None, "T2/T1") == pytest.approx(q["T1/T2"])
    # graded as SHADOW_SETTLE grades the simulated games
    games = [sim.game(i) for i in range(200)]
    ln = ShadowLine("", 230059, "set1_match", 0, "", None, "T1/T1", 1.0)
    vec = vpm.actual_values(sim, 230059, 0, "", None, "T1/T1")
    assert vec is not None
    assert [actual_value(ln, g, VB) for g in games] == vec[0][:200].tolist()


def test_the_pricer_prices_it_in_scope() -> None:
    f = vpm.VbForecast(mu=0.25, var=0.02, sideout=0.66, women=False, rated=(20, 20))
    pricer = vpp.VbPricer({7: f}, sims=500)
    a = pricer.p(7, True, 230059, 0, "", None, "T1/T1")
    b = pricer.p(7, False, 230059, 0, "", None, "T2/T2")
    assert a is not None and a == pytest.approx(b)


# --- SPORT_CONFIDENCE: allowed by the switch, own keys, own curves, the marker --------


def test_the_family_is_allowed_only_under_the_switch() -> None:
    assert scf.family_of("volleyball", 230059, "set1_match", True, True) is None
    assert scf.family_of("volleyball", 230059, "set1_match", True, True,
                         set1_match=True) == "set1_match"
    assert 230059 not in scf.EXTENDED_MARKETS["volleyball"]
    # never a settled-only family: no fit reads its curve off Superbet lines
    assert "set1_match" not in scf.settled_only_families("volleyball")
    assert "set1_match" not in scf.settled_only_families("volleyball", True)
    rsc = importlib.import_module("scripts.sofa.run_sport_confidence")
    ln = ShadowLine("e", 230059, "set1_match", 0, "", None, "T1/T1", 1.75)
    assert rsc._allowed("volleyball", ln, True, True) is None
    assert rsc._allowed("volleyball", ln, True, True, False, True) == "set1_match"


def test_the_keys_are_same_and_split_never_team() -> None:
    assert scf.curve_key("set1_match", "T1/T1") == "set1_match|SAME"
    assert scf.curve_key("set1_match", "T2/T2") == "set1_match|SAME"
    assert scf.curve_key("set1_match", "T1/T2") == "set1_match|SPLIT"
    assert scf.curve_key("set1_match", "T2/T1") == "set1_match|SPLIT"
    # every older side keeps its class
    assert scf.side_class("T1") == "TEAM" and scf.side_class("3:1") == "3:1"


def test_the_leg_carries_both_markers() -> None:
    rsc = importlib.import_module("scripts.sofa.run_sport_confidence")
    fc = rsc.DbForecaster("unused.db", ON + timedelta(hours=8), "2026-11-22")
    joint = ShadowLine("e", 230059, "set1_match", 0, "", None, "T1/T1", 1.75)
    winner = ShadowLine("e", 745, "winner", 0, "", None, "T1", 1.3)
    assert fc.vb_point_rule("volleyball", joint) == {
        "vb_point_model_rule": epochs.VB_POINT_MODEL,
        "vb_set1_match_rule": epochs.VB_SET1_MATCH}
    assert fc.vb_point_rule("volleyball", winner) == {
        "vb_point_model_rule": epochs.VB_POINT_MODEL}


def test_a_margin_over_fifteen_percent_is_refused() -> None:
    rsc = importlib.import_module("scripts.sofa.run_sport_confidence")
    wide = {"T1/T1": 1.6, "T1/T2": 7.0, "T2/T1": 4.2, "T2/T2": 4.0}
    margin = cs2.group_overround(wide)
    assert margin > 0.15
    assert rsc.price_filter(0.8, 1.6, margin) == "MARGIN_TOO_HIGH"
    assert rsc.price_filter(0.8, 1.75, cs2.group_overround(
        {"T1/T1": 1.75, "T1/T2": 7.9, "T2/T1": 4.7, "T2/T2": 4.4})) is None


def _write(path: Path, doc: dict[str, Any]) -> None:
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_the_overlay_adds_its_keys_by_the_clock_and_never_touches_the_rally_file(
        tmp_path: Path) -> None:
    rally = {"vb_point_model_curves": {"keys": ["winner|TEAM"]},
             "curves": {"winner|TEAM": {"0.700-0.750": {"n": 300,
                                                         "realised_lo95": 0.7}}}}
    joint = {"vb_set1_match_curves": {"keys": ["set1_match|SAME"]},
             "curves": {"set1_match|SAME": {"0.800-0.850": {
                 "n": 400, "realised_lo95": 0.8}}}}
    _write(tmp_path / scf.VB_POINT_CURVES_FILE, rally)
    _write(tmp_path / scf.VB_SET1_MATCH_CURVES_FILE, joint)
    before = hashlib.md5((tmp_path / scf.VB_POINT_CURVES_FILE).read_bytes()).hexdigest()
    cal = scf.SportCalibration({"sports": {"volleyball": {"curves": {
        "sets_total|OVER": {"0.0-0.6": {"n": 9}}}}, "hockey": {"curves": {}}}})
    off = scf.with_vb_point_curves(cal, "2026-11-21", ON + timedelta(hours=1), tmp_path)
    early = scf.with_vb_point_curves(cal, "2026-11-22", ON - timedelta(seconds=1),
                                     tmp_path)
    on = scf.with_vb_point_curves(cal, "2026-11-22", ON, tmp_path)
    assert off is not None and early is not None and on is not None
    vb_off = off.doc["sports"]["volleyball"]
    assert set(vb_off["curves"]) == {"sets_total|OVER", "winner|TEAM"}
    assert "vb_set1_match_curves" not in vb_off
    assert early.doc == off.doc  # by the build clock, not the file
    vb_on = on.doc["sports"]["volleyball"]
    assert set(vb_on["curves"]) == {"sets_total|OVER", "winner|TEAM",
                                    "set1_match|SAME"}
    assert vb_on["vb_set1_match_curves"] == joint["vb_set1_match_curves"]
    assert on.doc["sports"]["hockey"] == cal.doc["sports"]["hockey"]
    assert hashlib.md5((tmp_path / scf.VB_POINT_CURVES_FILE).read_bytes()
                       ).hexdigest() == before
    conf = on.lookup("volleyball", "set1_match", "T2/T2", 0.82, require_admitted=False)
    assert conf is not None and conf.value == 0.8


def test_the_installed_curves_are_the_two_keys_on_history() -> None:
    doc = json.loads(config_path(scf.VB_SET1_MATCH_CURVES_FILE).read_text(
        encoding="utf-8"))
    meta = doc["vb_set1_match_curves"]
    assert set(doc["curves"]) <= {"set1_match|SAME", "set1_match|SPLIT"}
    assert "set1_match|SAME" in doc["curves"]
    assert sorted(doc["curves"]) == sorted(meta["keys"])
    assert meta["fitted_from"]["window"] == ["2025-10-01", "2026-09-28"]
    assert meta["holdout"]["passed"] is True
    rally = json.loads(config_path(scf.VB_POINT_CURVES_FILE).read_text(
        encoding="utf-8"))
    assert not any(k.startswith("set1_match") for k in rally["curves"])
    # every bucket has the fit's minimum
    assert all(int(b["n"]) >= scf.MIN_BUCKET for c in doc["curves"].values()
               for b in c.values())


# --- names, identity, relations ------------------------------------------------------


def _leg(side: str, **extra: Any) -> dict[str, Any]:
    return {"sport": "volleyball", "market_id": 230059, "family": "set1_match",
            "period": 0, "subject": "", "line": None, "side": side,
            "match": f"{T1} - {T2}", "group_key": "sofa:1",
            "sofascore_event_id": 1, **extra}


def test_superbets_words_name_the_leg() -> None:
    assert superbet_names.names(_leg("T1/T1")) == ("1.Set/Mecz", f"{T1}/{T1}")
    assert superbet_names.names(_leg("T2/T1")) == ("1.Set/Mecz", f"{T2}/{T1}")


def test_no_identity_with_the_winner_or_set_one() -> None:
    """The joint is the intersection of two read legs (745, 744 set 1), never
    one of them: no SAME_EVENT_DEDUP key."""
    assert leg_identity.event_key(_leg("T1/T1")) is None


def test_relations_a_joint_is_linked_to_the_winner_and_set_one() -> None:
    winner = {**_leg("T1"), "market_id": 745, "family": "winner"}
    set1 = {**_leg("T1"), "market_id": 744, "family": "set_winner", "period": 1}
    assert leg_relations.relate(_leg("T1/T1"), winner).label == leg_relations.DEPENDENT
    assert leg_relations.relate(_leg("T1/T1"), set1).label == leg_relations.DEPENDENT
    same = leg_relations.relate(_leg("T1/T1"), _leg("T2/T2"))
    assert same.label == leg_relations.SAME_VARIABLE_EXCLUSIVE
    assert ("volleyball", "set1_match") in leg_relations.mapped_sport_markets()


# --- line evidence and /kupon ---------------------------------------------------------


def test_the_backfill_prices_its_settled_lines(tmp_path: Path) -> None:
    bf = importlib.import_module("scripts.sofa.backfill_vb_point_p")
    day = tmp_path / "shadow" / "volleyball" / "2026-11-22"
    day.mkdir(parents=True)
    graded = [{"superbet_event_id": "9", "market_id": 230059, "period": 0,
               "subject": "", "line": None, "side": s, "outcome": "WIN"}
              for s in ("T1/T1", "T2/T2")]
    (day / "settled.json").write_text(json.dumps({"events": {"9": {
        "pinned_id": 5, "sofascore_event_id": 5, "graded": graded}}}))
    got = list(bf.settled_lines(tmp_path, "2026-11-23"))
    assert [g["side"] for _, _, g in got] == ["T1/T1", "T2/T2"]
    assert bf.key_of("2026-11-22", got[0][2]) == "2026-11-22|9|230059|0|||T1/T1"


def test_kupon_asks_the_market_with_the_days_switch(
        monkeypatch: pytest.MonkeyPatch) -> None:
    build_slip = importlib.import_module("scripts.sofa.build_slip")

    class Client:
        def event_odds(self, eid: str) -> Any:
            return _board_payload()

    leg = {"sport": "volleyball", "superbet_event_id": "15721202",
           "kickoff_utc": "2026-11-22T22:00:00Z", "source_date": "2026-11-22",
           "market_id": 230059, "family": "set1_match", "subject": "", "line": None,
           "side": "T1/T1", "period": 0}
    got = build_slip.sport_live(Client(), leg, (T1, T2),
                                datetime(2026, 11, 22, 12, tzinfo=UTC))
    assert (got.status, got.odds) == ("OK", 1.75)
    monkeypatch.setattr(epochs, "VB_SET1_MATCH_FROM_UTC", None)
    gone = build_slip.sport_live(Client(), leg, (T1, T2),
                                 datetime(2026, 11, 22, 12, tzinfo=UTC))
    assert gone.status == "GONE"


def test_the_own_sample_counts_each_team_on_its_own_side() -> None:
    class Games:
        def __init__(self, events: list[dict[str, Any]]) -> None:
            self.events = events

        def last(self, team: int, before: int) -> list[dict[str, Any]]:
            return [e for e in self.events
                    if team in (e["homeTeam"]["id"], e["awayTeam"]["id"])]

    def ev(i: int, home: int, away: int, hp: list[int], ap: list[int]
           ) -> dict[str, Any]:
        return {**_event(hp, ap), "id": i, "homeTeam": {"id": home},
                "awayTeam": {"id": away}}

    games = Games([ev(1, 10, 99, [25, 25, 25], [20, 20, 20]),      # 10 won both
                   ev(2, 98, 10, [25, 20, 20, 20], [20, 25, 25, 25]),  # 10 split
                   ev(3, 20, 97, [20, 25, 25, 25], [25, 20, 20, 20])])  # 20 split
    ln = ShadowLine("e", 230059, "set1_match", 0, "", None, "T1/T1", 1.75)
    # team1 (10) as T1: game 1 T1/T1 (win), game 2 T2/T1 (loss); team2 (20) as
    # T2: game 3 from its side is T2/T2 for 20 = "T1/T1" lost
    assert scf.sample_hit_rate(ln, VB, 10, 20, games,  # type: ignore[arg-type]
                               10 ** 10) == (1, 3)
