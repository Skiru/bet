"""F4.2-F4.4 (plan 2026-10-05 production grade) on the coupon: the relations
and ladders 11_coupon.json carries, the "ta sama zmienna" groups on the PDF,
the exposure per match, the OFF-by-default coupon form, and the builders'
screen price - annotation now, a gate only from 2026-10-06."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

import pytest
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import KeepTogether, Paragraph, Table

from bet.sofa import builder_screen as bs
from bet.sofa import coupon_form as cf
from bet.sofa.confidence import is_stakeable, printed_builders
from bet.sofa.epochs import builder_screen_price_required, coupon_form_active
from bet.sofa.leg_relations import RELATIONS
from scripts.sofa.build_coupon import assemble
from scripts.sofa.coupon_structure_pdf import LADDER_PHRASE

UTC = datetime.UTC
KO = "2026-10-07T18:00:00Z"


def _single(eid: int, conf: float, market: str, line: float, direction: str,
            odds: float = 1.3, subject: str = "", **extra: Any) -> dict[str, Any]:
    return {"sofascore_event_id": eid, "confidence": conf, "kickoff_utc": KO,
            "market": market, "subject": subject, "line": line,
            "direction": direction, "offered_odds": odds, "match": f"M{eid}",
            "display_market": market, **extra}


def _builder(eid: int = 1, p: float = 0.80, after: float = 1.20,
             **extra: Any) -> dict[str, Any]:
    return {"sofascore_event_id": eid, "match": f"M{eid}", "kickoff_utc": KO,
            "competition": "L", "legs": [
                {"market": "goals_total", "subject": "", "line": 3.5,
                 "direction": "UNDER", "confidence": 0.9, "odds": 1.2},
                {"market": "corners_total", "subject": "", "line": 12.5,
                 "direction": "UNDER", "confidence": 0.9, "odds": 1.15}],
            "n_legs": 2, "combined_probability": p, "fair_odds": 1.25,
            "odds_if_product": 1.38, "haircut": 0.12, "odds_after_haircut": after,
            "ev_after_haircut": p * after - 1, "stakeable_rule": "x>=0.90",
            "best_for_fixture": True, **extra}


def _conf(singles: list[dict[str, Any]],
          builders: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"profile": "standard", "epoch": "stats_only", "created_at_utc": "x",
            "singles": singles, "legs": singles, "builders": builders or []}


def _ladder_day() -> list[dict[str, Any]]:
    return [
        _single(1, 0.92, "goals_total", 3.5, "UNDER", 1.10),
        _single(1, 0.85, "goals_total", 2.5, "UNDER", 1.40),
        _single(1, 0.80, "goals_total", 0.5, "OVER", 1.15),
        _single(1, 0.78, "corners_total", 9.5, "UNDER", 1.30),
        _single(2, 0.90, "goals_total", 2.5, "UNDER", 1.20),
        _single(2, 0.75, "goals_for", 1.5, "UNDER", 1.30, subject="Home"),
        _single(3, 0.70, "corners_total", 8.5, "OVER", 1.40),
    ]


def test_every_pair_of_a_matchs_legs_has_a_label_and_nothing_moves() -> None:
    plain = assemble(_conf(_ladder_day()), None, [], {}, "now", "2026-10-07")
    doc = assemble(_conf(_ladder_day()), None, [], {}, "now", "2026-10-07",
                   form=cf.CouponForm(), form_active=True)
    # annotation only: the same positions in the same order
    assert [(s["sofascore_event_id"], s["line"], s["position"]) for s in doc["singles"]
            ] == [(s["sofascore_event_id"], s["line"], s["position"])
                  for s in plain["singles"]]
    by_match: dict[str, int] = {}
    for s in doc["singles"]:
        by_match[s["group_key"]] = by_match.get(s["group_key"], 0) + 1
    need = sum(n * (n - 1) // 2 for n in by_match.values())
    pairs = [p for m in doc["relations"] for p in m["pairs"]]
    assert len(pairs) == need == 6 + 1
    assert all(p["relation"] in RELATIONS for p in pairs)
    # one ladder: goals_total of match 1, three rungs, OVER and UNDER
    assert len(doc["ladders"]) == 1
    lad = doc["ladders"][0]
    assert lad["n_rungs"] == 3 and lad["over_under_pair"]
    assert sorted(r["position"] for r in lad["rungs"]) == [
        s["position"] for s in doc["singles"]
        if s.get("ladder_no") == lad["ladder_no"]]
    assert doc["removed_by_coupon_form"] == []


def test_exposure_per_match_and_the_top_positions() -> None:
    doc = assemble(_conf(_ladder_day(), [_builder(1)]), None, [], {}, "now",
                   "2026-10-07")
    exp = doc["exposure"]
    assert exp["positions"] == 7 and exp["matches"] == 3
    assert exp["max_positions_per_match"] is None
    first = exp["per_match"][0]
    assert first["group_key"] == "sofa:1" and first["n_positions"] == 4
    assert first["share_of_positions"] == round(4 / 7, 4)
    assert first["confidence_sum"] == round(0.92 + 0.85 + 0.80 + 0.78, 3)
    # every leg of the match and its printed builder lose together
    assert first["builders"] == ["B1"] and first["worst_case_lost"] == 5
    assert exp["top_positions_matches"] == 3


def test_the_coupon_form_is_off_by_default_and_gated() -> None:
    one = cf.CouponForm(ladder_form=cf.LADDER_FORM_ONE_RUNG)
    before = assemble(_conf(_ladder_day()), None, [], {}, "now", "2026-10-07",
                      form=one, form_active=False)
    assert before["positions"] == 7 and before["removed_by_coupon_form"] == []
    assert before["coupon_form"]["applied"] is False
    after = assemble(_conf(_ladder_day()), None, [], {}, "now", "2026-10-07",
                     form=one, form_active=True)
    # match 1's goals_total keeps 2.5 UNDER (x = 0.85 x 1.40 = 1.19)
    kept = [(s["sofascore_event_id"], s["market"], s["line"]) for s in after["singles"]]
    assert (1, "goals_total", 2.5) in kept
    assert (1, "goals_total", 3.5) not in kept and (1, "goals_total", 0.5) not in kept
    assert {x["refusal"] for x in after["removed_by_coupon_form"]} == {
        "LADDER_FORM_ONE_RUNG"}
    assert after["positions"] == 5 and after["ladders"] == []
    capped = assemble(_conf(_ladder_day()), None, [], {}, "now", "2026-10-07",
                      form=cf.CouponForm(max_positions_per_match=2), form_active=True)
    assert max(r["n_positions"] for r in capped["exposure"]["per_match"]) == 2
    assert [x["confidence"] for x in capped["removed_by_coupon_form"]] == [0.80, 0.78]


def test_coupon_form_file_is_validated(tmp_path: Path) -> None:
    assert cf.load_coupon_form(tmp_path / "missing.json").is_default()
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"ladder_form": "one_rung", "max_positions_per_match": 3}))
    form = cf.load_coupon_form(p)
    assert form.ladder_form == "one_rung" and form.max_positions_per_match == 3
    for bad in ({"ladder_form": "best"}, {"max_positions_per_match": 0},
                {"max_positions_per_match": True}, {"ladder": "group"}):
        p.write_text(json.dumps(bad))
        with pytest.raises(ValueError):
            cf.load_coupon_form(p)


def test_the_epoch_gates_start_on_the_6th() -> None:
    at = datetime.datetime(2026, 10, 6, 0, 30, tzinfo=UTC)
    assert not builder_screen_price_required("2026-10-05", at)
    assert builder_screen_price_required("2026-10-06", at)
    assert not builder_screen_price_required(
        "2026-10-06", datetime.datetime(2026, 10, 5, 23, 0, tzinfo=UTC))
    assert coupon_form_active("2026-10-06", at)
    assert not coupon_form_active("2026-10-05", at)


def _prices(tmp_path: Path, doc: dict[str, Any]) -> dict[str, bs.ScreenPrice]:
    p = tmp_path / bs.SCREEN_PRICES_FILE
    p.write_text(json.dumps(doc))
    return bs.load_screen_prices(p)


def test_screen_prices_file_is_validated(tmp_path: Path) -> None:
    assert bs.load_screen_prices(tmp_path / "none.json") == {}
    legacy = _prices(tmp_path, {"1": 1.6})
    assert legacy["1"].odds == 1.6 and legacy["1"].fetched_at_utc is None
    for bad in ({"x": 1.6}, {"1": 0.9}, {"1": True}, {"1": {"odds": 1.6}},
                {"1": {"odds": "1.6", "source": "op"}},
                {"1": {"odds": 1.6, "source": "op", "fetched_at_utc": "yesterday"}},
                {"1": {"odds": 1.6, "source": "op", "legs": [{"market": "x"}]}}):
        with pytest.raises(ValueError):
            _prices(tmp_path, bad)
    # the settlement readers see odds either way
    p = tmp_path / bs.SCREEN_PRICES_FILE
    timed = {"odds": 1.7, "source": "op", "fetched_at_utc": "2026-10-07T10:00:00Z"}
    p.write_text(json.dumps({"1": 1.6, "2": timed}))
    assert bs.screen_odds_by_event(p) == {"1": 1.6, "2": 1.7}


def test_before_the_rule_a_builder_only_carries_its_screen_price(
        tmp_path: Path) -> None:
    prices = _prices(tmp_path, {"1": {"odds": 1.5, "source": "op",
                                      "fetched_at_utc": "2026-10-07T10:00:00Z"}})
    doc = assemble(_conf(_ladder_day(), [_builder(1), _builder(2)]), None, [], {},
                   "now", "2026-10-07", screen_prices=prices, screen_required=False)
    assert [b.get("builder_no") for b in doc["builders"]] == ["B1", "B2"]
    assert doc["builders"][0]["screen_odds"] == 1.5
    assert "builder_price_rule" not in doc["builders"][1]
    assert doc["builders_refused"] == []


def test_under_the_rule_a_builder_needs_a_valid_screen_price(tmp_path: Path) -> None:
    prices = _prices(tmp_path, {
        "1": {"odds": 1.25, "source": "op", "fetched_at_utc": "2026-10-07T10:00:00Z"},
        "3": 1.4,  # untimed
        "4": {"odds": 1.4, "source": "op", "fetched_at_utc": "2026-10-07T18:05:00Z"},
        "5": {"odds": 1.4, "source": "op", "fetched_at_utc": "2026-10-07T10:00:00Z",
              "legs": [{"market": "goals_total", "line": 2.5, "direction": "UNDER"}]},
        "6": {"odds": 1.05, "source": "op", "fetched_at_utc": "2026-10-07T10:00:00Z"},
    })
    builders = [_builder(e) for e in (1, 2, 3, 4, 5, 6)]
    builders.append(_builder(7, locked=True))
    doc = assemble(_conf(_ladder_day(), builders), None, [], {}, "now", "2026-10-07",
                   screen_prices=prices, screen_required=True)
    by = {b["sofascore_event_id"]: b for b in doc["builders"]}
    # 1: screen 1.25 x p 0.80 = 1.00 >= 0.90 - printed at the screen price
    assert by[1]["builder_no"] and by[1]["screen_odds"] == 1.25
    assert is_stakeable(by[1])
    refused = {b["sofascore_event_id"]: b["refusal"] for b in doc["builders_refused"]}
    assert refused == {2: bs.NO_SCREEN_PRICE, 3: bs.UNTIMED, 4: bs.AFTER_START,
                       5: bs.OTHER_SLIP, 6: bs.X_BELOW}
    for e in refused:
        assert "builder_no" not in by[e] and not is_stakeable(by[e])
    # a locked builder (printed before its start) is never touched
    assert "refusal" not in by[7] and "builder_price_rule" not in by[7]
    assert {b["sofascore_event_id"] for b in printed_builders(doc)} == {1, 7}
    assert doc["builder_screen_prices"]["printed_with_screen_price"] == 1


def test_a_matching_slip_prices_the_builder(tmp_path: Path) -> None:
    legs = [{"market": "corners_total", "subject": "", "line": 12.5,
             "direction": "UNDER"},
            {"market": "goals_total", "line": 3.5, "direction": "UNDER"}]
    prices = _prices(tmp_path, {"1": {"odds": 1.3, "source": "op", "legs": legs,
                                      "fetched_at_utc": "2026-10-07T10:00:00Z"}})
    out = bs.apply_screen_prices([_builder(1)], prices, True, 0.90)
    assert out[0]["screen_odds"] == 1.3 and "refusal" not in out[0]


def _texts(flowable: Any) -> list[str]:
    if isinstance(flowable, Paragraph):
        return [flowable.text]
    if isinstance(flowable, KeepTogether):
        return [t for f in flowable._content for t in _texts(f)]
    if isinstance(flowable, Table):
        out = []
        for row in flowable._cellvalues:
            out.append(" | ".join(
                c.text if isinstance(c, Paragraph) else str(c) for c in row))
        return out
    return []


def test_no_ladder_prints_as_independent_positions_without_a_description() -> None:
    """The criterion of F4.2: every ladder has one 'ta sama zmienna' header
    listing its rungs, and every rung row names its ladder."""
    from scripts.sofa.build_coupon_pdf import render_stats_only

    singles = _ladder_day()
    singles.append({**_single(9, 0.95, "goals_total", 2.5, "UNDER"), "locked": True,
                    "printed_at_utc": "2026-10-07T09:00:00Z"})
    singles.append({**_single(9, 0.94, "goals_total", 3.5, "UNDER"), "locked": True,
                    "printed_at_utc": "2026-10-07T09:00:00Z"})
    doc = assemble(_conf(singles, [_builder(1)]), None, [], {}, "now", "2026-10-07")
    assert len(doc["ladders"]) == 2
    ss = getSampleStyleSheet()
    story: list[Any] = []
    render_stats_only(story, doc, doc["singles"], printed_builders(doc), {},
                      datetime.datetime(2026, 10, 7, 9, 0, tzinfo=UTC),
                      ss["Normal"], ss["Normal"], ss["Heading2"], ss["Normal"], 0.15)
    rows = [t for f in story for t in _texts(f)]
    for lad in doc["ladders"]:
        tag = f"{LADDER_PHRASE} Z{lad['ladder_no']}"
        headers = [r for r in rows if r.startswith(f"<b>{tag}</b>")]
        assert len(headers) == 1, tag
        for rung in lad["rungs"]:
            assert f"{rung['line']} {rung['direction']}" in headers[0]
        marked = [r for r in rows if tag in r and not r.startswith("<b>")]
        assert len(marked) == lad["n_rungs"]
    # a leg off every ladder is not marked
    corners = [r for r in rows if "corners_total" in r and "9.5" in r]
    assert corners and LADDER_PHRASE not in corners[0]
    joined = "\n".join(rows)
    assert "Ekspozycja na mecz" in joined and "Pozycje 1-30 stoją na" in joined
    assert "brak kursu z ekranu" in joined  # B1 has no screen price recorded


def test_a_malformed_screen_price_file_refuses_the_assembly(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    from tests.sofa.test_build_coupon import _build_coupon, _coupon, _three_matches
    from tests.sofa.test_stats_only_confidence import DAY, _run

    runs = _three_matches(tmp_path)
    assert _run(runs, monkeypatch) == 0
    (runs / DAY / bs.SCREEN_PRICES_FILE).write_text(json.dumps({"1": "1.6"}))
    assert _build_coupon(runs, monkeypatch) == 2
    assert "09_screen_prices.json" in capsys.readouterr().err
    (runs / DAY / bs.SCREEN_PRICES_FILE).write_text(json.dumps({}))
    assert _build_coupon(runs, monkeypatch) == 1
    doc = _coupon(runs)
    # a day after 10-06: the rule is on, and the artifact says so
    assert doc["builder_screen_prices"]["required"] is True
    assert doc["coupon_form"]["active"] is True and not doc["coupon_form"]["applied"]
    assert {"relations", "ladders", "exposure"} <= set(doc)
