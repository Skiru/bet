"""Our rating against Superbet's picture of the match (operator, 2026-11-04):
bet.sofa.rating_market_gap - the market fit, D, the dependent legs, the note
parser, missing data, the epoch switch, the sentence, and its place in the
coupon (annotation only). Measurement:
docs/sofa/evidence/rating_vs_market_disagreement_2026-11-04.md."""

from __future__ import annotations

import datetime
from typing import Any

import pytest

from bet.sofa import coupon_html as ch
from bet.sofa import epochs, football_result
from bet.sofa import rating_market_gap as rmg
from scripts.sofa.build_coupon import assemble, render_md
from scripts.sofa.build_coupon_pdf import rating_market_gap_label

UTC = datetime.UTC
R = 7.586


def _note_total(h: float, a: float) -> list[str]:
    return [f"FOOTBALL_RATING: centre {h + a:.2f} from the rating (home {h:.2f} "
            f"+ away {a:.2f}, league 668 (n=372)) at W=0.5 (W_FOOTBALL_RATING)"]


def _note_side(side: str, v: float) -> list[str]:
    return [f"FOOTBALL_RATING: centre {v:.2f} from the rating ({side} {v:.2f}, "
            "league 668 (n=372)) at W=0.95"]


def _sheet(eid: int, home: str, away: str, rh: float, ra: float,
           total: bool = True) -> list[dict[str, Any]]:
    rows = [
        {"sofascore_event_id": eid, "sport": "football", "market": "goals_for",
         "subject": home, "notes": _note_side("home", rh)},
        {"sofascore_event_id": eid, "sport": "football", "market": "goals_for",
         "subject": away, "notes": _note_side("away", ra)},
    ]
    if total:
        rows.append({"sofascore_event_id": eid, "sport": "football",
                     "market": "goals_total", "subject": "",
                     "notes": _note_total(rh, ra)})
    return rows


def _rungs(raw: list[list[Any]]) -> list[dict[str, Any]]:
    return [{"market": m, "subject": s, "line": ln, "over_odds": o, "under_odds": u}
            for m, s, ln, o, u in raw]


# 04_offer.json rungs of FC Seoul - Thể Công - Viettel, 2026-11-04
# (sofa:16864091, Seoul at home) and 2026-10-28 (sofa:16864128, Viettel at home)
SEOUL_1104 = _rungs([
    ["double_chance", "X2", 0.5, 5.0, 1.1], ["result_1x2", "1", 0.5, 1.1, 5.0],
    ["double_chance", "12", 0.5, 1.03, 8.4], ["result_1x2", "2", 0.5, 13.0, None],
    ["goals_total", "", 1.5, 1.08, 5.2], ["goals_total", "", 2.5, 1.35, 2.72],
    ["goals_total", "", 3.5, 1.95, 1.74], ["goals_total", "", 4.5, 2.95, 1.29],
    ["goals_total", "", 5.5, 4.85, 1.09], ["goals_for", "fc seoul", 1.5, 1.16, 3.9],
    ["goals_for", "fc seoul", 2.5, 1.59, 2.15],
    ["goals_for", "fc seoul", 3.5, 2.45, 1.44],
    ["goals_for", "viettel", 0.5, 2.17, 1.57], ["goals_for", "viettel", 1.5, 6.2, 1.04],
    ["goals_for", "viettel", 2.5, 16.0, None],
    ["goals_for", "fc seoul", 0.5, 1.02, 13.0],
])
SEOUL_1028 = _rungs([
    ["double_chance", "X2", 0.5, 1.15, 4.4], ["result_1x2", "1", 0.5, 4.4, 1.15],
    ["double_chance", "12", 0.5, 1.2, 3.75], ["double_chance", "1X", 0.5, 2.02, 1.64],
    ["result_1x2", "2", 0.5, 1.64, 2.02], ["goals_total", "", 0.5, None, 8.6],
    ["goals_total", "", 1.5, 1.2, 3.55], ["goals_total", "", 2.5, 1.71, 2.0],
    ["goals_total", "", 3.5, 2.7, 1.36], ["goals_total", "", 4.5, 4.6, 1.11],
    ["goals_for", "viettel", 0.5, 1.47, 2.4], ["goals_for", "viettel", 1.5, 3.15, 1.26],
    ["goals_for", "viettel", 2.5, 7.3, 1.02], ["goals_for", "fc seoul", 0.5, 1.1, 4.65],
    ["goals_for", "fc seoul", 1.5, 1.67, 2.02],
    ["goals_for", "fc seoul", 2.5, 2.95, 1.29],
])


def _view(mh: float, ma: float, rh: float, ra: float) -> rmg.EventView:
    return rmg.EventView(mh, ma, 10, 0.01, rmg.RatingView(rh, ra, rmg.SOURCE_TOTAL),
                         {"home fc": "home", "away fc": "away"}, "Home FC", "Away FC")


def leg(market: str, subject: str, direction: str, eid: int = 1,
        line: float = 2.5, **kw: Any) -> dict[str, Any]:
    return {"sofascore_event_id": eid, "sport": "football", "market": market,
            "subject": subject, "line": line, "direction": direction,
            "confidence": 0.80, "offered_odds": 1.30, "match": f"M{eid}",
            "kickoff_utc": "2026-11-04T18:00:00Z", "group_key": f"sofa:{eid}",
            "overround": 0.05, **kw}


# ------------------------------------------------------------ the market fit


def test_the_nb_size_is_the_result_models() -> None:
    assert rmg.nb_r() == football_result.load_config().nb_r == R


def test_the_fit_recovers_known_rates_from_fair_nb_ladders() -> None:
    t = rmg._tables(R)
    ih, ia = 70, 30          # GRID 1.80 / 0.80
    assert (rmg.GRID[ih], rmg.GRID[ia]) == (1.8, 0.8)
    rungs = [
        {"market": "result_1x2", "subject": "1", "line": 0.5,
         "over_odds": 1 / t.p_hwin[ih, ia], "under_odds": 1 / (1 - t.p_hwin[ih, ia])},
        {"market": "result_1x2", "subject": "2", "line": 0.5,
         "over_odds": 1 / t.p_awin[ih, ia], "under_odds": 1 / (1 - t.p_awin[ih, ia])},
    ]
    for line in (0.5, 1.5, 2.5):
        i = int(line)
        for subj, p in (("h", t.surv[ih, i]), ("a", t.surv[ia, i])):
            rungs.append({"market": "goals_for", "subject": subj, "line": line,
                          "over_odds": 1 / p, "under_odds": 1 / (1 - p)})
    for line in (1.5, 2.5, 3.5):
        p = t.p_tot_over[line][ih, ia]
        rungs.append({"market": "goals_total", "subject": "", "line": line,
                      "over_odds": 1 / p, "under_odds": 1 / (1 - p)})
    obs = rmg.market_observations(rungs, {"h": "home", "a": "away"})
    assert len(obs) == 2 + 6 + 3 and rmg.fit_ok(obs)
    fit = rmg.fit_market(obs, R)
    assert fit is not None
    assert fit[:3] == (1.8, 0.8, 11) and fit[3] == pytest.approx(0.0, abs=1e-12)


def test_devig_is_proportional_and_needs_both_prices() -> None:
    assert rmg.devig(2.0, 2.0) == pytest.approx(0.5)
    assert rmg.devig(1.5, 3.0) == pytest.approx((1 / 1.5) / (1 / 1.5 + 1 / 3.0))
    assert rmg.devig(13.0, None) is None and rmg.devig(None, 1.2) is None


def test_a_fit_needs_the_measurements_ok_rule() -> None:
    home_win = [("hwin", 0.5, 0.6)]
    assert not rmg.fit_ok(home_win)
    assert not rmg.fit_ok([("hwin", 0.5, 0.6), ("t_over", 2.5, 0.5)])
    assert rmg.fit_ok([("hwin", 0.5, 0.6), ("awin", 0.5, 0.2)])
    assert rmg.fit_ok([("h_over", 0.5, 0.7), ("a_over", 0.5, 0.6)])
    assert rmg.fit_market([("t_over", 9.5, 0.1)], R) is None  # nothing usable


# ------------------------------------------------------------- the Seoul case


def test_seoul_2026_11_04_market_sees_seoul_two_goals_stronger() -> None:
    v = rmg.event_view(_sheet(16864091, "fc seoul", "viettel", 1.58, 1.13),
                       SEOUL_1104, R, "FC Seoul", "Thể Công - Viettel")
    assert v is not None
    assert v.favourite == "home"
    assert (v.market_home, v.market_away) == pytest.approx((3.10, 0.575))
    # the report: market +2.53, rating +0.45, D = +2.08
    assert v.d == pytest.approx(2.075, abs=1e-9)
    under = leg("goals_for", "fc seoul", "UNDER", 16864091, 3.5)
    entry = rmg.annotate(under, v)
    assert entry is not None and entry["group"] == rmg.FAV_TT_UNDER
    assert entry["d"] == pytest.approx(2.08, abs=0.006)
    assert entry["favourite_name"] == "FC Seoul"
    # the market's side is never flagged
    assert rmg.annotate(leg("goals_for", "fc seoul", "OVER", 16864091, 1.5), v) is None


def test_seoul_2026_10_28_d_is_one_and_a_half_goals() -> None:
    v = rmg.event_view(_sheet(16864128, "viettel", "fc seoul", 1.63, 1.01),
                       SEOUL_1028, R, "Thể Công - Viettel", "FC Seoul")
    assert v is not None and v.favourite == "away"
    assert (v.market_home, v.market_away) == pytest.approx((1.05, 1.90))
    assert v.d == pytest.approx(1.47, abs=1e-9)   # the report: D = +1.47
    lost = [leg("goals_for", "fc seoul", "UNDER", line=2.5),
            leg("goals_for", "viettel", "OVER", line=0.5),
            leg("result_or_under", "1", "OVER", line=3.5),
            leg("result_or_under", "X", "OVER", line=4.5)]
    assert all(rmg.annotate(x, v) is not None for x in lost)
    # match total under is measured apart, never flagged
    assert rmg.annotate(leg("goals_total", "", "UNDER", line=4.5), v) is None


# ------------------------------------------------------------ D and the legs


def test_d_sign_and_threshold() -> None:
    # market +1.0 for home, rating level: D = +1.0 -> flagged (>=)
    v = _view(1.8, 0.8, 1.3, 1.3)
    assert v.d == pytest.approx(1.0)
    assert rmg.annotate(leg("goals_for", "home fc", "UNDER"), v) is not None
    # 0.99 goals: not
    v = _view(1.8, 0.81, 1.3, 1.3)
    assert rmg.annotate(leg("goals_for", "home fc", "UNDER"), v) is None
    # our rating backs the market's favourite more than the market: D < 0
    v = _view(1.8, 0.8, 2.5, 0.5)
    assert v.d == pytest.approx(-1.0)
    assert rmg.annotate(leg("goals_for", "home fc", "UNDER"), v) is None
    # our rating sees the other side stronger: D = 1.0 + 0.4
    v = _view(0.8, 1.8, 1.5, 1.1)
    assert v.favourite == "away" and v.rating_margin == pytest.approx(-0.4)
    assert v.d == pytest.approx(1.4)


@pytest.mark.parametrize("market,subject,direction,group", [
    # home is the market's favourite
    ("goals_for", "home fc", "UNDER", rmg.FAV_TT_UNDER),
    ("goals_for", "home fc", "OVER", None),
    ("goals_for", "away fc", "OVER", rmg.DOG_TT_OVER),
    ("goals_for", "away fc", "UNDER", None),
    ("goals_for", "someone", "UNDER", None),          # no side known
    ("result_1x2", "2", "OVER", rmg.DOG_RESULT),
    ("result_1x2", "X", "OVER", rmg.DOG_RESULT),
    ("result_1x2", "1", "OVER", None),
    ("result_1x2", "2", "UNDER", None),
    ("double_chance", "X2", "OVER", rmg.DOG_RESULT),
    ("double_chance", "1X", "OVER", None),
    ("double_chance", "12", "OVER", None),
    ("double_chance", "X2", "UNDER", None),
    ("draw_no_bet", "1", "UNDER", rmg.DOG_RESULT),     # DNB away
    ("draw_no_bet", "1", "OVER", None),                # DNB home
    ("result_handicap", "2", "OVER", rmg.DOG_RESULT),
    ("result_handicap", "1", "OVER", None),
    ("result_or_under", "2", "OVER", rmg.DOG_OR_UNDER),
    ("result_or_under", "X", "OVER", rmg.DOG_OR_UNDER),
    ("result_or_under", "1", "OVER", None),
    ("result_or_over", "2", "OVER", None),
    ("dc_and_under", "1X", "OVER", None),               # home is the favourite
    ("goals_total", "", "UNDER", None),
    ("goals_1h_for", "home fc", "UNDER", None),         # halves measured apart
    ("corners_total", "", "OVER", None),
])
def test_dependent_legs_home_favourite(market: str, subject: str,
                                       direction: str, group: str | None) -> None:
    v = _view(2.0, 0.8, 1.3, 1.3)
    assert rmg.leg_group(leg(market, subject, direction), v) == group


@pytest.mark.parametrize("market,subject,direction,group", [
    ("result_1x2", "1", "OVER", rmg.DOG_RESULT),
    ("double_chance", "1X", "OVER", rmg.DOG_RESULT),
    ("draw_no_bet", "1", "OVER", rmg.DOG_RESULT),
    ("result_handicap", "1", "OVER", rmg.DOG_RESULT),
    ("result_or_under", "1", "OVER", rmg.DOG_OR_UNDER),
    ("dc_and_under", "1X", "OVER", rmg.DOG_OR_UNDER),    # home is the underdog
    ("goals_for", "away fc", "UNDER", rmg.FAV_TT_UNDER),
    ("goals_for", "home fc", "OVER", rmg.DOG_TT_OVER),
])
def test_dependent_legs_away_favourite(market: str, subject: str,
                                       direction: str, group: str | None) -> None:
    v = _view(0.8, 2.0, 1.3, 1.3)
    assert rmg.leg_group(leg(market, subject, direction), v) == group


def test_other_sports_are_never_flagged() -> None:
    v = _view(2.5, 0.5, 1.3, 1.3)
    assert rmg.annotate(leg("goals_for", "home fc", "UNDER", sport="hockey"), v) is None
    assert rmg.annotate(leg("goals_for", "home fc", "UNDER"), None) is None


# ------------------------------------------------------------- the notes


def test_the_goals_total_note_comes_first() -> None:
    rows = _sheet(1, "a", "b", 1.40, 1.20)
    rows[0]["notes"] = _note_side("home", 1.90)  # a goals_for note disagrees
    rows.append({"market": "result_1x2", "subject": "1",
                 "notes": ["... on the pure rating centres home 1.577 / "
                           "away 1.130; ..."]})
    view, smap = rmg.rating_view(rows)
    assert view == rmg.RatingView(1.40, 1.20, rmg.SOURCE_TOTAL)
    assert smap == {"a": "home", "b": "away"}


def test_both_goals_for_notes_then_the_pure_centres() -> None:
    rows = _sheet(1, "a", "b", 1.45, 0.95, total=False)
    assert rmg.rating_view(rows)[0] == rmg.RatingView(1.45, 0.95, rmg.SOURCE_SIDES)
    pure = [{"market": "result_1x2", "subject": "1",
             "notes": ["FOOTBALL_RESULT_1X2_DNB: 1X2 1 win p 0.4700 from NB goals "
                       "(r 7.586) on the pure rating centres home 1.577 / "
                       "away 1.130;"]}]
    assert rmg.rating_view(pure)[0] == rmg.RatingView(1.577, 1.13, rmg.SOURCE_PURE)


def test_one_side_named_names_the_other() -> None:
    rows = _sheet(1, "a", "b", 1.45, 0.95, total=False)
    rows[1]["notes"] = ["NO_LEAGUE_RATE: ..."]
    view, smap = rmg.rating_view(rows)
    assert smap == {"a": "home", "b": "away"}
    assert view is None   # one rated side is not our view


# --------------------------------------------------------- missing data


def test_missing_data_is_no_entry() -> None:
    sheet = _sheet(16864091, "fc seoul", "viettel", 1.58, 1.13)
    assert rmg.event_view(sheet, None, R) is None               # no offer
    assert rmg.event_view([], SEOUL_1104, R) is None            # no rating
    only_home = [r for r in SEOUL_1104 if r["market"] != "goals_for"]
    # 1X2 "2" has no under price, so neither 1X2 pair nor both team totals
    assert rmg.event_view(sheet, only_home, R) is None
    views = rmg.views_by_event(sheet, [{"sofascore_event_id": 16864091,
                                        "rungs": SEOUL_1104}], [16864091, 5], r=R)
    assert set(views) == {16864091}


# ------------------------------------------------------------- the switch


def test_the_switch_starts_on_2026_11_04_at_midnight() -> None:
    at = datetime.datetime(2026, 11, 4, 0, 0, tzinfo=UTC)
    assert epochs.rating_market_gap("2026-11-04", at) is True
    assert epochs.rating_market_gap("2026-11-05", at) is True
    assert epochs.rating_market_gap("2026-11-03", at) is False
    before = at - datetime.timedelta(minutes=1)
    assert epochs.rating_market_gap("2026-11-04", before) is False


def test_inactive_clears_and_active_sets() -> None:
    v = {1: _view(2.5, 0.5, 1.3, 1.3)}
    legs = [leg("goals_for", "home fc", "UNDER"),
            {**leg("goals_for", "home fc", "OVER"), "rating_market_gap": {"d": 9}}]
    assert rmg.annotate_legs(legs, v, True) == 1
    assert "rating_market_gap" in legs[0] and "rating_market_gap" not in legs[1]
    assert rmg.annotate_legs(legs, v, False) == 0
    assert all("rating_market_gap" not in x for x in legs)


# ------------------------------------------------------- the sentence, coupon


def test_the_sentence_carries_the_reports_numbers() -> None:
    x = leg("goals_for", "home fc", "UNDER")
    x["rating_market_gap"] = rmg.annotate(x, _view(3.1, 0.575, 1.58, 1.13))
    text = rmg.label(x)
    assert "Home FC" in text and "2,1 gola" in text
    assert "rynek +2,53" in text and "rating +0,45" in text
    assert "-3,4 pp" in text and "[-9,3; +2,6]" in text and "25.10-3.11" in text
    assert rmg.label(leg("goals_for", "home fc", "UNDER")) == ""
    assert len(text) < 260


def test_the_coupon_is_the_same_and_says_it() -> None:
    flagged = leg("goals_for", "home fc", "UNDER", 1)
    flagged["rating_market_gap"] = rmg.annotate(flagged, _view(2.5, 0.5, 1.3, 1.3))
    plain = leg("corners_total", "", "OVER", 2, line=8.5)
    conf = {"profile": "standard", "epoch": "stats_only", "created_at_utc": "x",
            "singles": [flagged, plain], "legs": [flagged, plain], "builders": [],
            "rating_market_gap": {"active": True, "legs": 99}}
    bare = {**conf, "singles": [{k: v for k, v in s.items()
                                 if k != "rating_market_gap"} for s in conf["singles"]]}
    on = assemble(conf, None, [], {}, "now", "2026-11-04")
    off = assemble(bare, None, [], {}, "now", "2026-11-04")

    def key(d: dict[str, Any]) -> list[tuple[Any, ...]]:
        return [(s["sofascore_event_id"], s["market"], s["position"],
                 s["confidence"]) for s in d["singles"]]

    assert key(on) == key(off)
    assert on["rating_market_gap"]["legs"] == 1
    by_ev = {s["sofascore_event_id"]: s for s in on["singles"]}
    assert "mocniej niż nasz rating" in rating_market_gap_label(by_ev[1])
    assert rating_market_gap_label(by_ev[2]) == ""
    rows = {r["match"]: r for r in ch.build_view(on, "2026-11-04", None)["rows"]}
    assert "mocniej" in rows["M1"]["rating_market_gap"]
    assert rows["M2"]["rating_market_gap"] == ""
    assert "mocniej niż nasz rating" in render_md(on, "2026-11-04")


def test_safe_views_never_raises_and_names_the_failure() -> None:
    class Boom:
        def __iter__(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("sheet unreadable")

    views, warn = rmg.safe_views(Boom(), [], [1, 2])
    assert views == {}
    assert warn is not None and "RuntimeError" in warn and "no leg annotated" in warn


def test_safe_views_warns_when_no_match_parses_on_a_full_day() -> None:
    ids = list(range(rmg.MIN_MATCHES_FOR_DRIFT))
    sheet = [{"sport": "football", "sofascore_event_id": e, "market": "goals_total",
              "notes": ["note wording SHEET no longer writes"]} for e in ids]
    views, warn = rmg.safe_views(sheet, [], ids)
    assert views == {} and warn is not None and "no longer parse" in warn
    # a thin day says nothing: no views on 3 matches is not a drift
    assert rmg.safe_views(sheet[:3], [], ids[:3]) == ({}, None)
