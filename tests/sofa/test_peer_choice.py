"""Which of two near-priced legs of a match is the surer one, and what a match
is played for (operator, 2026-10-08): bet.sofa.peer_choice, bet.sofa.stakes,
their place in the coupon (annotation only), the epoch switch, the PDF, and the
pure parts of the measurement behind them."""

from __future__ import annotations

import datetime
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import KeepTogether, Paragraph, Table

from bet.sofa import epochs, peer_choice, stakes
from bet.sofa.confidence import printed_builders
from scripts.sofa import measure_peer_choice as mpc
from scripts.sofa.build_coupon import assemble

UTC = datetime.UTC
KO = "2026-10-08T22:30:00Z"


def leg(
    eid: int,
    conf: float,
    market: str,
    line: float,
    direction: str,
    odds: float,
    subject: str = "",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid,
        "confidence": conf,
        "kickoff_utc": KO,
        "market": market,
        "subject": subject,
        "line": line,
        "direction": direction,
        "offered_odds": odds,
        "match": f"M{eid}",
        "sport": "football",
        "display_market": market,
        **extra,
    }


def corinthians_pair() -> list[dict[str, Any]]:
    """The 2026-10-07 case: total cards over 3.5 beside the side's cards under
    4.5, three cents apart."""
    return [
        leg(1, 0.8119, "cards_points_total", 3.5, "OVER", 1.16, sample_size=20),
        leg(
            1,
            0.8821,
            "cards_points_for",
            4.5,
            "UNDER",
            1.19,
            subject="corinthians",
            sample_size=10,
        ),
    ]


# ------------------------------------------------------------- peer choice


def test_the_surer_of_two_near_priced_legs_is_the_one_starred() -> None:
    legs = corinthians_pair()
    assert peer_choice.annotate(legs) == 2
    total, side = legs
    assert side["peer"]["preferred"] is True
    assert total["peer"]["preferred"] is False
    assert total["peer"]["d_confidence"] == pytest.approx(0.8119 - 0.8821, abs=1e-4)
    assert total["peer"]["best"]["subject"] == "corinthians"
    assert total["peer"]["best"]["sample_size"] == 10
    assert side["peer"]["peers"] == 1 and side["peer"]["d_confidence"] == 0
    text = peer_choice.label(total)
    assert text == ("słabsza o 0.070 niż ★ cards_points_for corinthians 4.5 UNDER "
                    "(kurs 1.19)")
    assert peer_choice.label(side).startswith("★ najpewniejsza z 2 nóg")


def test_the_proposal_is_the_confidence_not_the_price_or_the_sample_size() -> None:
    cheap_sure = leg(1, 0.90, "goals_total", 4.5, "UNDER", 1.12, sample_size=10)
    dear_unsure = leg(1, 0.80, "corners_total", 7.5, "OVER", 1.17, sample_size=20)
    legs = [dear_unsure, cheap_sure]
    peer_choice.annotate(legs)
    assert cheap_sure["peer"]["preferred"] and not dear_unsure["peer"]["preferred"]


def test_legs_far_apart_in_price_or_in_different_matches_are_not_peers() -> None:
    far = [
        leg(1, 0.88, "goals_total", 4.5, "UNDER", 1.10),
        leg(1, 0.81, "corners_total", 6.5, "OVER", 1.30),
    ]
    assert peer_choice.annotate(far) == 0 and "peer" not in far[0]
    other_match = [
        leg(1, 0.88, "goals_total", 4.5, "UNDER", 1.20),
        leg(2, 0.81, "goals_total", 4.5, "UNDER", 1.20),
    ]
    assert peer_choice.annotate(other_match) == 0
    edge = [
        leg(1, 0.88, "goals_total", 4.5, "UNDER", 1.20),
        leg(1, 0.81, "corners_total", 6.5, "OVER", 1.26),
    ]
    assert peer_choice.annotate(edge) == 2  # exactly PEER_BAND apart
    just_out = [
        leg(1, 0.88, "goals_total", 4.5, "UNDER", 1.20),
        leg(1, 0.81, "corners_total", 6.5, "OVER", 1.27),
    ]
    assert peer_choice.annotate(just_out) == 0


def test_rungs_of_one_variable_are_a_ladder_not_peers() -> None:
    rungs = [
        leg(1, 0.90, "goals_total", 3.5, "UNDER", 1.18),
        leg(1, 0.85, "goals_total", 4.5, "UNDER", 1.20),
        leg(1, 0.80, "corners_total", 8.5, "OVER", 1.21),
    ]
    peer_choice.annotate(rungs)
    # the corners leg compares with the BEST rung of the goals variable only
    corners = rungs[2]
    assert corners["peer"]["peers"] == 1
    assert corners["peer"]["best"]["line"] == 3.5
    # the two goals rungs never name each other
    assert rungs[0]["peer"]["best"]["market"] == "goals_total"
    assert rungs[0]["peer"]["preferred"] is True
    # the second rung is surer than the corners leg too: starred, never "weaker
    # than its own sibling"
    assert (
        rungs[1]["peer"]["preferred"] is True
        and rungs[1]["peer"]["best"]["line"] == 4.5
    )


def test_a_leg_with_three_peers_names_the_surest() -> None:
    legs = [
        leg(1, 0.70 + i / 100, m, 2.5, "UNDER", 1.20 + i / 100)
        for i, m in enumerate(
            ["goals_total", "corners_total", "shots_total", "saves_total"]
        )
    ]
    peer_choice.annotate(legs)
    weakest = legs[0]["peer"]
    assert weakest["preferred"] is False and weakest["peers"] == 3
    assert weakest["best"]["market"] == "saves_total"
    assert legs[3]["peer"]["preferred"] is True


def test_reannotating_clears_the_old_marks_and_skips_unpriced_legs() -> None:
    legs = corinthians_pair()
    peer_choice.annotate(legs)
    legs[1]["offered_odds"] = 1.50
    peer_choice.annotate(legs)
    assert "peer" not in legs[0] and "peer" not in legs[1]
    unpriced = [
        {**leg(1, 0.9, "goals_total", 2.5, "UNDER", 1.2), "offered_odds": None},
        leg(1, 0.8, "corners_total", 8.5, "OVER", 1.2),
    ]
    assert peer_choice.annotate(unpriced) == 0


def test_a_measured_sport_leg_reads_the_same_way() -> None:
    a = {
        "sofascore_event_id": 5,
        "sport": "hockey",
        "match": "A - B",
        "family": "total",
        "period": 0,
        "subject": "",
        "line": 5.5,
        "side": "UNDER",
        "direction": "UNDER",
        "confidence": 0.81,
        "odds": 1.20,
    }
    b = {
        "sofascore_event_id": 5,
        "sport": "hockey",
        "match": "A - B",
        "family": "team_total",
        "period": 0,
        "subject": "T1",
        "line": 3.5,
        "side": "UNDER",
        "direction": "UNDER",
        "confidence": 0.77,
        "odds": 1.22,
    }
    legs = [a, b]
    assert peer_choice.annotate(legs) == 2
    assert a["peer"]["preferred"] and not b["peer"]["preferred"]


# ------------------------------------------------------------ in the coupon


def _conf(singles: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "profile": "standard",
        "epoch": "stats_only",
        "created_at_utc": "x",
        "singles": singles,
        "legs": singles,
        "builders": [],
    }


def _day() -> list[dict[str, Any]]:
    return [
        *corinthians_pair(),
        leg(2, 0.90, "goals_total", 2.5, "UNDER", 1.20),
        leg(3, 0.75, "goals_total", 2.5, "UNDER", 1.20),
        leg(3, 0.74, "corners_total", 8.5, "OVER", 1.22),
    ]


def test_the_coupon_is_the_same_with_and_without_the_annotation() -> None:
    off = assemble(_conf(_day()), None, [], {}, "now", "2026-10-08")
    on = assemble(
        _conf(_day()),
        None,
        [],
        {},
        "now",
        "2026-10-08",
        peer_active=True,
        stakes_by_event={1: [f"{stakes.SIX_POINTER}(73% sezonu)"]},
    )
    key = lambda d: [
        (
            s["sofascore_event_id"],
            s["market"],
            s["line"],  # noqa: E731
            s["direction"],
            s["position"],
            s["confidence"],
        )
        for s in d["singles"]
    ]
    assert key(on) == key(off)
    assert all("peer" not in s and "stakes" not in s for s in off["singles"])
    assert off["peer_choice"]["active"] is False
    assert on["peer_choice"]["active"] is True
    assert on["peer_choice"]["legs_with_peers"] == 4
    assert on["peer_choice"]["preferred"] == 2
    assert on["peer_choice"]["stakes_fixtures"] == 1
    side = next(s for s in on["singles"] if s["market"] == "cards_points_for")
    assert side["stakes"]["flags"][0].startswith(stakes.SIX_POINTER)
    assert side["stakes"]["effect"] == "przeciw"
    total = next(s for s in on["singles"] if s["market"] == "cards_points_total")
    assert total["stakes"]["effect"] == "za"
    # a match with no flags carries none
    assert all("stakes" not in s for s in on["singles"] if s["sofascore_event_id"] != 1)


def test_the_epoch_switch_is_an_exact_time() -> None:
    at = epochs.PEER_CHOICE_FROM_UTC
    assert at is not None
    assert not epochs.peer_choice("2026-10-08", at - datetime.timedelta(seconds=1))
    assert epochs.peer_choice("2026-10-08", at)
    assert epochs.peer_choice("2026-10-09", at)
    assert not epochs.peer_choice("2026-10-07", at + datetime.timedelta(days=1))


# ------------------------------------------------------------------- stakes


def _season(
    table: dict[int, int], rounds: int = 2
) -> list[tuple[int, int, int, int, int]]:
    """A synthetic league: every pair meets `rounds` times; a club's strength
    decides the score, so the order of `table` (club -> strength) is the order
    of the standings."""
    out = []
    ts = 1_000_000
    clubs = sorted(table)
    for _ in range(rounds):
        for i, h in enumerate(clubs):
            for a in clubs[i + 1 :]:
                hg, ag = (1, 0) if table[h] >= table[a] else (0, 1)
                out.append((ts, h, a, hg, ag))
                ts += 1000
    return out


def test_a_six_pointer_is_two_clubs_at_the_relegation_line() -> None:
    strength = {c: 100 - c for c in range(1, 15)}  # 14 clubs: club 1 wins all
    matches = _season(strength)
    tables = {(7, 70): matches}
    last = matches[-1][0] + 1
    # 14 clubs: zone of 3, safe club 11 / first relegated 12 are adjacent on points
    got = stakes.flags(tables, 7, 70, 11, 12, last)
    assert got and got[0].startswith(stakes.SIX_POINTER)
    assert stakes.flags(tables, 7, 70, 1, 12, last) == []  # leader vs a relegation club
    assert stakes.flags(tables, 7, 70, 1, 99, last) == []  # unknown club
    assert stakes.flags(tables, 7, 71, 11, 12, last) == []  # no such season
    assert stakes.flags(tables, 7, None, 11, 12, last) == []
    top = stakes.flags(tables, 7, 70, 4, 5, last)
    assert top and top[0].startswith(stakes.TOP4)


def test_too_early_or_too_small_is_not_a_stakes_match() -> None:
    strength = {c: 100 - c for c in range(1, 15)}
    matches = _season(strength)
    tables = {(7, 70): matches}
    early = matches[len(matches) // 4][0]
    assert stakes.flags(tables, 7, 70, 11, 12, early) == []  # < MIN_PROGRESS
    small = {(8, 80): _season({c: 100 - c for c in range(1, 9)})}
    assert stakes.flags(small, 8, 80, 6, 7, 10**9) == []  # < MIN_TEAMS


def test_the_table_only_counts_matches_before_the_kickoff() -> None:
    matches = _season({c: 100 - c for c in range(1, 15)})
    tables = {(7, 70): matches}
    last = matches[-1]
    # as of the final match's own kickoff it is not in the table yet
    before = stakes.flags(tables, 7, 70, last[1], last[2], last[0])
    after = stakes.flags(tables, 7, 70, last[1], last[2], last[0] + 1)
    assert isinstance(before, list) and isinstance(after, list)
    pts_before, played_before = stakes._table(matches, last[0])
    pts_after, played_after = stakes._table(matches, last[0] + 1)
    assert sum(played_after.values()) - sum(played_before.values()) == 2
    assert sum(pts_after.values()) > sum(pts_before.values())


def test_the_effect_note_points_the_way_the_measurement_does() -> None:
    six = [f"{stakes.SIX_POINTER}(70% sezonu)"]
    assert stakes.effect_note(six, "cards_points_total", "OVER") == "za"
    assert stakes.effect_note(six, "cards_points_for", "UNDER") == "przeciw"
    assert stakes.effect_note(six, "goals_total", "UNDER") == "za"
    assert stakes.effect_note(six, "goals_total", "OVER") == "przeciw"
    assert stakes.effect_note(six, "saves_total", "OVER") == ""
    top = [f"{stakes.TOP4}(70% sezonu)"]
    assert (
        stakes.effect_note(top, "fouls_total", "OVER") == ""
    )  # not measured for top-4
    assert stakes.effect_note([], "cards_points_total", "OVER") == ""


def test_for_day_reads_the_fixtures_and_survives_junk() -> None:
    matches = _season({c: 100 - c for c in range(1, 15)})
    tables = {(7, 70): matches}
    ko = datetime.datetime.fromtimestamp(matches[-1][0] + 5, UTC).isoformat()
    fixtures = [
        {
            "sport": "football",
            "sofascore_event_id": 11,
            "competition_id": 7,
            "season_id": 70,
            "home_entity_id": 11,
            "away_entity_id": 12,
            "kickoff_utc": ko,
        },
        {"sport": "tennis", "sofascore_event_id": 12, "competition_id": 7},
        {"sport": "football", "sofascore_event_id": 13},  # no ids
        {
            "sport": "football",
            "sofascore_event_id": 14,
            "competition_id": 7,
            "season_id": 70,
            "home_entity_id": 1,
            "away_entity_id": 14,
            "kickoff_utc": ko,
        },
    ]
    got = stakes.for_day(fixtures, tables)
    assert list(got) == [11]


def test_the_history_pickle_is_read_without_the_database(tmp_path: Path) -> None:
    class R:
        def __init__(self, ts: int, h: int, a: int, g: tuple[float, float]) -> None:
            self.event_id, self.ts, self.competition_id = ts, ts, 7
            self.season_id, self.home_id, self.away_id = 70, h, a
            self.values = {"goals_for": g}

    path = tmp_path / "football_history.pkl"
    # a module-level class is needed to pickle; use plain tuples of the shape
    import types

    ns = types.SimpleNamespace
    hist = [
        ns(
            event_id=1,
            ts=10,
            competition_id=7,
            season_id=70,
            home_id=1,
            away_id=2,
            values={"goals_for": (2.0, 1.0)},
        )
    ]
    path.write_bytes(pickle.dumps(("fp", hist)))
    tables = stakes.load_tables(path)
    assert tables == {(7, 70): [(10, 1, 2, 2, 1)]}
    assert stakes.load_tables(tmp_path / "absent.pkl") is None
    (tmp_path / "bad.pkl").write_bytes(b"not a pickle")
    assert stakes.load_tables(tmp_path / "bad.pkl") is None
    assert R(1, 1, 2, (0.0, 0.0)).values["goals_for"] == (0.0, 0.0)


def test_the_measurement_and_the_page_flag_the_same_matches() -> None:
    """scripts/sofa/measure_peer_choice.stakes_tables (the evidence) and
    bet.sofa.stakes.flags (what prints) are one rule."""
    import types

    ns = types.SimpleNamespace
    matches = _season({c: 100 - c for c in range(1, 15)})
    hist = [
        ns(
            event_id=i,
            ts=m[0],
            competition_id=7,
            season_id=70,
            home_id=m[1],
            away_id=m[2],
            values={"goals_for": (float(m[3]), float(m[4]))},
        )
        for i, m in enumerate(matches)
    ]
    tables = stakes.build_tables(hist)
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "h.pkl"
        p.write_bytes(pickle.dumps(("fp", hist)))
        flagged = mpc.stakes_tables(str(p))
    for r in flagged.itertuples():
        got = stakes.flags(
            tables, int(r.comp), int(r.season), int(r.h), int(r.a), int(r.ts)
        )
        assert bool(r.six) == any(f.startswith(stakes.SIX_POINTER) for f in got)
        assert bool(r.top) == any(f.startswith(stakes.TOP4) for f in got)


# ---------------------------------------------------------------------- PDF


def _texts(flowable: Any) -> list[str]:
    if isinstance(flowable, Paragraph):
        return [flowable.text]
    if isinstance(flowable, KeepTogether):
        return [t for f in flowable._content for t in _texts(f)]
    if isinstance(flowable, Table):
        return [
            " | ".join(c.text if isinstance(c, Paragraph) else str(c) for c in row)
            for row in flowable._cellvalues
        ]
    return []


def test_the_page_stars_the_surer_leg_and_says_how_weak_the_proposal_is() -> None:
    from scripts.sofa.build_coupon_pdf import render_stats_only

    day = [*corinthians_pair()]
    doc = assemble(
        _conf(day),
        None,
        [],
        {},
        "now",
        "2026-10-08",
        peer_active=True,
        stakes_by_event={1: [f"{stakes.SIX_POINTER}(73% sezonu)"]},
    )
    ss = getSampleStyleSheet()
    story: list[Any] = []
    render_stats_only(
        story,
        doc,
        doc["singles"],
        printed_builders(doc),
        {},
        datetime.datetime(2026, 10, 8, 9, 0, tzinfo=UTC),
        ss["Normal"],
        ss["Normal"],
        ss["Heading2"],
        ss["Normal"],
        0.15,
    )
    joined = "\n".join(t for f in story for t in _texts(f))
    assert "▲ najpewniejsza z 2 nóg" in joined
    assert "słabsza o 0.070 niż ▲" in joined
    assert "mecz o utrzymanie" in joined and "efekt stawki idzie przeciw" in joined
    assert "nie pewniak" in joined and "nigdy jej nie bramkujący" in joined
    off = assemble(_conf(day), None, [], {}, "now", "2026-10-08")
    story = []
    render_stats_only(
        story,
        off,
        off["singles"],
        printed_builders(off),
        {},
        datetime.datetime(2026, 10, 8, 9, 0, tzinfo=UTC),
        ss["Normal"],
        ss["Normal"],
        ss["Heading2"],
        ss["Normal"],
        0.15,
    )
    plain = "\n".join(t for f in story for t in _texts(f))
    assert "▲" not in plain and "mecz o utrzymanie" not in plain


def test_the_markdown_coupon_carries_the_notes() -> None:
    from scripts.sofa.build_coupon import render_md

    doc = assemble(
        _conf(corinthians_pair()), None, [], {}, "now", "2026-10-08", peer_active=True
    )
    md = render_md(doc, "2026-10-08")
    assert "uwagi" in md and "★ najpewniejsza" in md and "słabsza o 0.070 niż ★" in md


# -------------------------------------------------------------- measurement


def test_boot_ratio_is_a_ratio_with_a_band_that_contains_it() -> None:
    num = np.array([1, 0, 1, 1, 0, 1, 1, 1], float)
    den = np.ones(8)
    p, lo, hi = mpc.boot_ratio(num, den, np.arange(8))
    assert p == pytest.approx(0.75) and lo <= p <= hi
    # one cluster only: the band collapses on the point
    p1, lo1, hi1 = mpc.boot_ratio(num, den, np.zeros(8))
    assert p1 == lo1 == hi1


def _legs_frame() -> pd.DataFrame:
    rows = []
    # match m1: A (y=1, p .9) vs B (y=0, p .8) at the same price; same variable C is skipped
    spec = [
        ("m1", "A", 1.20, 1, 0.90),
        ("m1", "B", 1.22, 0, 0.80),
        ("m1", "A", 1.40, 0, 0.95),  # same variable, far price
        ("m2", "A", 1.20, 0, 0.85),
        ("m2", "B", 1.21, 1, 0.80),
        ("m3", "A", 1.20, 1, 0.80),
        ("m3", "B", 1.20, 1, 0.80),
    ]  # both won
    for m, v, o, y, p in spec:
        rows.append({"day": "d", "ev": m, "var": v, "odds": o, "y": y, "p_bar": p})
    return pd.DataFrame(rows)


def test_pairs_are_different_variables_near_in_price_with_one_winner() -> None:
    pr = mpc.make_pairs(_legs_frame(), ["day", "ev"], "var")
    assert len(pr) == 2 and set(pr.cluster) == {"d|m1", "d|m2"}
    res = mpc.rule_accuracy(pr, pr.p_bar_a, pr.p_bar_b)
    assert res["pairs"] == 2 and res["matches"] == 2
    assert res["acc"] == pytest.approx(0.5)  # m1 higher-p won, m2 higher-p lost
    tie = mpc.rule_accuracy(pr, pr.p_bar_a * 0, pr.p_bar_b * 0)
    assert tie["pairs"] == 0 and tie["acc"] is None


def test_the_logit_fit_recovers_a_slope_and_cv_runs_by_day() -> None:
    rng = np.random.default_rng(1)
    x = rng.normal(size=4000)
    y = (rng.random(4000) < 1 / (1 + np.exp(-(0.3 + 1.5 * x)))).astype(float)
    w = mpc.fit_logit(x[:, None], y, l2=0.01)
    assert w[1] == pytest.approx(1.5, abs=0.2) and w[0] == pytest.approx(0.3, abs=0.15)
    p = mpc.predict(w, x[:, None])
    assert mpc.auc(y, p) > 0.75 and mpc.logloss(y, p) < 0.6
    df = pd.DataFrame({"day": np.repeat(["a", "b", "c", "d"], 1000), "y": y, "lp": x})
    ll, au, n = mpc.cv_by_day(df, ["lp"])
    assert n == 4000 and au > 0.75 and ll < 0.6
