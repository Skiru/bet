"""The cache replay prices the football joints (both_over_ / most_ /
handicap_) from the marginal rows' centres, as SHEET does since
epochs.DERIVED_MARGINAL_CENTRES_FROM_UTC, and grades them as
run_settle._settle_derived does. Opt-in (--derived)."""

from __future__ import annotations

import math
import random
import statistics

import pytest

from bet.sofa.derived import SideStats, load_side_correlations, marginal_centred_stats
from bet.sofa.derived import probability as derived_probability
from bet.sofa.joint import build_joint
from scripts.sofa.calibrate_from_cache import (
    JOINT_BASES,
    MIN_SAMPLE,
    SAMPLE_N,
    Played,
    iter_rows,
    k_centre_for,
    prior_for,
)

DAY = 86400
BASELINES = {"goals_for": {"global": {"mean": 1.3, "n": 5000}}}


def _played() -> list[Played]:
    rng = random.Random(11)
    out = []
    for i in range(60):
        h, a = (1, 2) if i % 2 == 0 else (2, 1)
        out.append(Played(
            event_id=100 + i, timestamp=i * DAY, home_id=h, away_id=a,
            sport="football", competition_id=17,
            values={"goals": (float(rng.randint(0, 4)), float(rng.randint(0, 3)))}))
    return out


def _joint_rows(joint_bases: frozenset[str]):
    return [r for r in iter_rows(_played(), BASELINES, None, joint_bases)
            if r.market.split("_")[0] in ("both", "most", "handicap")]


def test_goals_is_a_joint_base_and_default_is_none() -> None:
    assert "goals" in JOINT_BASES
    assert _joint_rows(frozenset()) == []


def test_a_joint_row_is_the_joint_of_the_marginal_centres() -> None:
    played = _played()
    target = played[-1]
    rows = [r for r in iter_rows(played, BASELINES, None, frozenset({"goals"}))
            if r.event_id == target.event_id
            and r.market in ("both_over_goals", "handicap_goals", "most_goals")]
    assert rows
    # rebuild the sides' samples as the replay sees them
    before = played[:-1]
    own = {1: [], 2: []}
    for m in before:
        own[m.home_id].append(m.values["goals"][0])
        own[m.away_id].append(m.values["goals"][1])
    sa, sb = own[target.home_id][-SAMPLE_N:], own[target.away_id][-SAMPLE_N:]
    assert min(len(sa), len(sb)) >= MIN_SAMPLE
    k = k_centre_for("football")
    prior = prior_for(BASELINES, "goals_for", 17)
    assert prior is not None
    raw, cs = [], []
    for s_ in (sa, sb):
        w = len(s_) / (len(s_) + k)
        cs.append(w * statistics.mean(s_) + (1 - w) * prior)
        raw.append(SideStats(len(s_), statistics.mean(s_),
                             statistics.variance(s_), statistics.stdev(s_)))
    st = [marginal_centred_stats(raw[i], "goals_for", cs[i]) for i in (0, 1)]
    rho = load_side_correlations().get("goals") or 0.0
    joint = build_joint(st[0].mean, st[0].variance, st[1].mean, st[1].variance, rho)
    checked = 0
    for r in rows:
        if r.market == "both_over_goals":
            want = derived_probability(joint, r.market, r.line, r.direction, None)
        else:
            continue
        assert r.p_central == pytest.approx(want, abs=2e-6)
        checked += 1
    assert checked >= 4


def test_joints_settle_like_run_settle() -> None:
    played = {m.event_id: m for m in _played()}
    rows = _joint_rows(frozenset({"goals"}))
    assert {r.market for r in rows} == {"both_over_goals", "handicap_goals",
                                        "most_goals"}
    for r in rows:
        home, away = played[r.event_id].values["goals"]
        if r.market == "both_over_goals":
            hit = min(home, away) >= math.floor(r.line) + 1
            assert r.actual == min(home, away)
            assert (r.outcome == "WIN") == (hit if r.direction == "OVER" else not hit)
        elif r.market == "handicap_goals":
            m = played[r.event_id]
            margin = home - away if r.subject == str(m.home_id) else away - home
            assert r.actual == margin and margin != -r.line  # no pushes written
            assert (r.outcome == "WIN") == (margin > -r.line)
        else:
            assert r.actual == home - away and r.direction == "OVER"
    subjects = {r.subject for r in rows if r.market == "most_goals"}
    # a side's win only: the draw is a different event and would share its
    # curve (fit_confidence keys by market and direction) - review 2026-10-07
    assert subjects >= {"1", "2"} and "__draw__" not in subjects
