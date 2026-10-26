"""Audit 2026-10-13 (docs/sofa/history/AUDYT_RYNKOW_KONTEKST_2026-10-13.md):
one test module for the fixes and switches the implementing session adds,
item by item (A2, C21, ...). Offline and fast."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs, shadow
from bet.sofa import sport_day as sd
from scripts.sofa import run_sport_confidence as rsc

# --- C21: a volleyball set never played is a refund ---------------------------


def _vb_leg(market_id: int, family: str, period: int, side: str,
            line: float | None) -> dict[str, Any]:
    return {"superbet_event_id": "9", "market_id": market_id, "family": family,
            "period": period, "subject": "", "line": line, "side": side,
            "odds": 1.8}


def _vb_event(t1: list[int], t2: list[int]) -> dict[str, Any]:
    won1 = sum(1 for a, b in zip(t1, t2, strict=True) if a > b)
    return {"state": "SETTLED", "t1_periods": t1, "t2_periods": t2,
            "t1_full": won1, "t2_full": len(t1) - won1,
            "winner": "T1" if won1 * 2 > len(t1) else "T2", "overtime": False}


def test_a_volleyball_set_never_played_is_a_refund() -> None:
    ev = _vb_event([25, 25, 25], [20, 18, 22])  # 3-0: no set 4
    for market_id, family, side, line in (
        (744, "set_winner", "T1", None),
        (782, "set_points_total", "OVER", 44.5),
        (781, "set_points_odd_even", "ODD", None),
        (100077, "set_extra_points", "YES", None),
    ):
        assert sd._grade_leg("volleyball", _vb_leg(market_id, family, 4, side, line),
                             ev) == "VOID"
    # a set that was played is graded as before
    played = _vb_leg(782, "set_points_total", 3, "OVER", 44.5)
    assert sd._grade_leg("volleyball", played, ev) == "WIN"
    # a whole-match line is never a set not played
    match = _vb_leg(230060, "points_total", 0, "OVER", 130.5)
    assert sd._grade_leg("volleyball", match, ev) == "WIN"


def test_set_not_played_only_for_volleyball_sets() -> None:
    vb = shadow.SPORTS["volleyball"]
    result = shadow.GameResult((25, 25, 25), (20, 18, 22), 3, 0, "T1", False)
    line = shadow.ShadowLine("9", 782, "set_points_total", 5, "", 44.5, "OVER", 1.8)
    assert shadow.set_not_played(line, result, vb)
    assert not shadow.set_not_played(
        shadow.ShadowLine("9", 782, "set_points_total", 3, "", 44.5, "OVER", 1.8),
        result, vb)
    # basketball's quarter 4 always exists: never a "set not played"
    bb = shadow.SPORTS["basketball"]
    q = shadow.GameResult((20, 20, 20), (20, 20, 20), 60, 60, None, False)
    assert not shadow.set_not_played(
        shadow.ShadowLine("9", 788, "quarter_total", 4, "", 40.5, "OVER", 1.8), q, bb)


# --- A2: a competition with no rate of its own; friendlies (operator O1) -------


def _thin_book() -> Any:
    from bet.sofa import football_rating as fr

    book = fr.RatingBook()
    # a league with plenty of matches, both sides rated in it
    for i in range(60):
        book.update(fr.FootballResult(i, i * 3600, 5, 100 + i % 4, 200 + i % 4,
                                      {"goals_for": (2.0, 1.0)}))
    return book


def test_a_thin_competition_has_no_rate_only_under_the_rule() -> None:
    from bet.sofa import football_rating as fr

    book = _thin_book()
    assert book.league_rates(999, "goals_for") is not None  # the all-league mean
    assert book.league_rates(999, "goals_for", strict=True) is None
    assert book.league_rates(5, "goals_for", strict=True) is not None
    old = fr.FootballForecast(book, 999, 100, 200)
    new = fr.FootballForecast(book, 999, 100, 200, strict_league_rate=True)
    assert old.centre("goals_for", "side_a") is not None
    assert new.centre("goals_for", "side_a") is None
    assert new.no_league_rate("goals_for") and not old.no_league_rate("goals_for")
    # an unrated market is never "no league rate": it had no rating anyway
    assert not new.no_league_rate("corners_total")
    in_league = fr.FootballForecast(book, 5, 100, 200, strict_league_rate=True)
    assert in_league.centre("goals_for", "side_a") is not None


def test_the_rule_never_changes_what_the_rating_learns() -> None:
    from bet.sofa import football_rating as fr

    book = _thin_book()
    before = {k: (t.attack, t.defence, t.n) for k, t in book.teams.items()}
    # a match in a thin competition still updates the ratios as before
    book.update(fr.FootballResult(99, 10**6, 999, 100, 200, {"goals_for": (3.0, 0.0)}))
    after = {k: (t.attack, t.defence, t.n) for k, t in book.teams.items()}
    assert after[(100, "goals_for")] != before[(100, "goals_for")]


def test_the_score_model_withholds_a_thin_competition() -> None:
    from bet.sofa import score_model as sm

    hockey = shadow.SPORTS["hockey"]
    history = []
    for i in range(200):
        vals = {f"p{k + 1}_for": (1.0, 0.8) for k in range(3)}
        vals[sm.REG_METRIC["hockey"]] = (3.0, 2.4)
        history.append(sm.FootballResult(i, i * 3600, 5, 100 + i % 6, 200 + i % 6,
                                         vals))
    old = sm.build_model(history, hockey, cut_ts=10**9)
    new = sm.build_model(history, hockey, cut_ts=10**9, strict_league_rate=True)
    assert old.expected(999, 100, 200) is not None
    assert new.expected(999, 100, 200) is None and new.no_league_rate(999)
    assert new.expected(5, 100, 200) is not None and not new.no_league_rate(5)
    assert not old.no_league_rate(999)


def _sport_setup(tmp: Path, tournament: str, competition_id: int = 55) -> None:
    from tests.sofa import test_run_sport_confidence as t

    t._write(tmp, "basketball", [t._snapshot(lines=[
        t._line(753, "total", "OVER", 1.30, 220.5),
        t._line(753, "total", "UNDER", 3.40, 220.5)])])
    t._fixtures(tmp, [t._fixture(sport="basketball", competition_id=competition_id,
                                 sofascore_tournament=tournament)])


class _Forecaster:
    def __init__(self, refuse: str | None = None) -> None:
        self.refuse = refuse

    def refusal(self, sport: str, fixture: Any) -> str | None:
        return self.refuse

    def probability(self, sport: str, fixture: Any, ev: Any, line: Any) -> float:
        return 0.81 if line.side == "OVER" else 0.19

    def sample(self, sport: str, fixture: Any, ev: Any, line: Any) -> tuple[int, int]:
        return 7, 10


def _sport_build(tmp: Path, forecaster: Any) -> dict[str, Any]:
    from tests.sofa import test_run_sport_confidence as t

    cal = t._calibration(tmp, {"basketball": ["total|OVER", "total|UNDER"]})
    doc, _ = rsc.build(t.DATE, str(tmp), cal, forecaster, t.AT, sports=("basketball",))
    return doc


def test_a_preseason_game_is_refused_like_a_football_friendly(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _sport_setup(tmp_path, "NBA Preseason")
    monkeypatch.setattr(epochs, "LEAGUE_RATE_RULE_FROM_UTC", None)
    assert _sport_build(tmp_path, _Forecaster())["legs"]  # the old rule prices it
    monkeypatch.setattr(epochs, "LEAGUE_RATE_RULE_FROM_UTC",
                        datetime(2026, 10, 6, tzinfo=UTC))
    doc = _sport_build(tmp_path, _Forecaster())
    assert doc["legs"] == []
    assert doc["sports"]["basketball"]["refused"]["FRIENDLY_FIXTURE"] == 2


def test_a_game_without_a_league_rate_is_refused(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _sport_setup(tmp_path, "NBA")
    monkeypatch.setattr(epochs, "LEAGUE_RATE_RULE_FROM_UTC",
                        datetime(2026, 10, 6, tzinfo=UTC))
    assert _sport_build(tmp_path, _Forecaster())["legs"]  # a regular league prints
    doc = _sport_build(tmp_path, _Forecaster(rsc.NO_LEAGUE_RATE))
    assert doc["legs"] == []
    assert doc["sports"]["basketball"]["refused"]["NO_LEAGUE_RATE"] == 2


def test_the_league_rate_rule_reads_the_day_and_the_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "LEAGUE_RATE_RULE_FROM_UTC",
                        datetime(2026, 10, 14, tzinfo=UTC))
    late = datetime(2026, 10, 14, 6, tzinfo=UTC)
    assert epochs.league_rate_rule("2026-10-14", late)
    assert not epochs.league_rate_rule("2026-10-13", late)  # never an older day
    early = datetime(2026, 10, 13, 23, tzinfo=UTC)
    assert not epochs.league_rate_rule("2026-10-14", early)
    assert epochs.league_rate_rule(None, late)


# --- A4: a no-curve key's bucket reads its own design effect -----------------


def test_a_bucket_of_one_line_a_game_is_not_shrunk_by_the_sports_design_effect(
        ) -> None:
    from bet.sofa import line_evidence as le

    rows = [{"sport": "football", "key": "both_over_corners|OVER", "p": 0.77,
             "y": 1 if i % 100 < 85 else 0, "game": f"g{i}", "base": None}
            for i in range(80)]
    # another key whose lines cluster in games: the sport's design effect > 1
    rows += [{"sport": "football", "key": "corners_total|OVER", "p": 0.8,
              "y": 1 if (i // 10) % 2 else 0, "game": f"h{i // 10}", "base": 0.8}
             for i in range(200)]
    fit = le.fit(rows)
    doc = {"keys": fit["keys"], "bands": {}, "design_effect": fit["design_effect"],
           "min_evidence_games": 15}
    assert fit["design_effect"]["football"] > 2
    bucket = fit["keys"]["football"]["both_over_corners|OVER"]["buckets"][
        "0.750-0.800"]
    assert bucket["deff"] == 1.0
    old = le.LineEvidence(doc, v2=True).read("football", "both_over_corners|OVER",
                                             0.78, None)
    new = le.LineEvidence(doc, v2=True, bucket_deff=True).read(
        "football", "both_over_corners|OVER", 0.78, None)
    assert old is not None and new is not None and new.value > old.value
    assert new.value == round(le.wilson_lo(bucket["k"], bucket["n"]), 4)
    # an older file without `deff` reads the sport's, as before
    del bucket["deff"]
    again = le.LineEvidence(doc, v2=True, bucket_deff=True).read(
        "football", "both_over_corners|OVER", 0.78, None)
    assert again == old


def test_the_bucket_design_effect_switch_reads_day_and_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "BUCKET_DESIGN_EFFECT_FROM_UTC",
                        datetime(2026, 10, 14, tzinfo=UTC))
    late = datetime(2026, 10, 14, 1, tzinfo=UTC)
    assert epochs.bucket_design_effect("2026-10-14", late)
    assert not epochs.bucket_design_effect("2026-10-13", late)


def test_the_audit_epoch_from_10_14_is_never_added_to_earlier_days() -> None:
    from scripts.sofa import audit_ledger

    assert audit_ledger.epoch_group(
        {"date": "2026-10-12", "epoch": "stats_only"}) == "od 10-12"
    # the identity switches moved into 10-14 (11:30Z): mixed, then od 10-15
    assert audit_ledger.epoch_group(
        {"date": "2026-10-14", "epoch": "stats_only"}) == "10-14 mieszany"
    assert audit_ledger.epoch_group(
        {"date": "2026-10-15", "epoch": "stats_only"}) == "od 10-15"
    # the cup-strength refit (before 10-16's build) and the score markets
    # moved into the built day 10-16 at 07:46Z: mixed, then od 10-17
    assert audit_ledger.epoch_group(
        {"date": "2026-10-16", "epoch": "stats_only"}) == "10-16 mieszany"
    # the supremacy stretches moved into the built day 10-17: mixed,
    # then od 10-18
    assert audit_ledger.epoch_group(
        {"date": "2026-10-17", "epoch": "stats_only"}) == "10-17 mieszany"
    # the curves per line moved into the built day 10-18: mixed, then od 10-19
    assert audit_ledger.epoch_group(
        {"date": "2026-10-18", "epoch": "stats_only"}) == "10-18 mieszany"
    # the football curves per line from 2026-10-19 00:00Z: od 10-19
    assert audit_ledger.epoch_group(
        {"date": "2026-10-19", "epoch": "stats_only"}) == "od 10-19"
    # the CS2 player share from 2026-10-21 00:00Z: od 10-21
    assert audit_ledger.epoch_group(
        {"date": "2026-10-20", "epoch": "stats_only"}) == "od 10-19"
    # ... but the late RESOLVE pass moved into the built day 10-21: mixed
    assert audit_ledger.epoch_group(
        {"date": "2026-10-21", "epoch": "stats_only"}) == "10-21 mieszany"
    # RESOLVE's reserve / youth retry from 2026-10-22 00:00Z: od 10-22
    assert audit_ledger.epoch_group(
        {"date": "2026-10-22", "epoch": "stats_only"}) == "od 10-22"
    # the measured sports' rolling day window from 2026-10-23 00:00Z: od 10-23
    assert audit_ledger.epoch_group(
        {"date": "2026-10-23", "epoch": "stats_only"}) == "od 10-23"
    # no installed curve fitted from live rows alone from 2026-10-24 00:00Z
    assert audit_ledger.epoch_group(
        {"date": "2026-10-24", "epoch": "stats_only"}) == "od 10-24"
    # the analyst audit's read scope / removal rule from 2026-10-27 00:00Z
    assert audit_ledger.epoch_group(
        {"date": "2026-10-27", "epoch": "stats_only"}) == "od 10-27"
    assert audit_ledger.EPOCH_GROUPS[-11:] == (
        "10-16 mieszany", "10-17 mieszany", "od 10-18", "10-18 mieszany", "od 10-19",
        "od 10-21", "10-21 mieszany", "od 10-22", "od 10-23", "od 10-24",
        "od 10-27")


def test_the_mixed_refit_day_10_13_is_its_own_ledger_group() -> None:
    from scripts.sofa import audit_ledger

    assert audit_ledger.epoch_group(
        {"date": "2026-10-13", "epoch": "stats_only"}) == "10-13 mieszany"
    groups = audit_ledger.EPOCH_GROUPS
    assert groups.index("od 10-12") < groups.index("10-13 mieszany") < \
        groups.index("10-14 mieszany") < groups.index("od 10-15")


# --- B10: a CS2 team's rounds on a map from the round race --------------------


def test_team_rounds_from_the_race_follow_the_map_winner() -> None:
    from bet.sofa import cs2_engine as ce

    strong = ce.team_rounds_from_race(0.8, 0, 12.5, True)
    weak = ce.team_rounds_from_race(0.8, 1, 12.5, True)
    assert strong is not None and weak is not None
    # >= 13 rounds is the map won (or overtime): the favourite's OVER is likely
    assert strong > 0.75 > 0.3 > weak
    # the two sides of one line add up (no push on a .5 line)
    under = ce.team_rounds_from_race(0.8, 0, 12.5, False)
    assert under is not None and abs(strong + under - 1.0) < 1e-9
    # a lower line is easier to clear
    low = ce.team_rounds_from_race(0.8, 1, 6.5, True)
    assert low is not None and low > weak


def test_model_probability_reads_the_race_only_under_the_switch() -> None:
    from bet.sofa import cs2_engine as ce
    from bet.sofa.cs2 import Cs2Line

    book = ce.EloBook()
    for _ in range(30):
        book.update(1, 2)  # team 1 keeps beating team 2
    ratings = ce.RatingModel(book)
    line = Cs2Line("1", "map_team_rounds", 1, "A", 12.5, "OVER", 1.9)
    old = ce.model_probability(line, 1, 2, "A", "B", 3, [], ratings, True)
    new = ce.model_probability(line, 1, 2, "A", "B", 3, [], ratings, True,
                               team_rounds_race=True)
    assert old is None  # no own maps in the history: the old estimator has nothing
    assert new is not None and new.model == "round_race" and new.p > 0.6


def test_the_cs2_race_switch_reads_day_and_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "CS2_TEAM_ROUNDS_RACE_FROM_UTC",
                        datetime(2026, 10, 15, tzinfo=UTC))
    late = datetime(2026, 10, 15, 1, tzinfo=UTC)
    assert epochs.cs2_team_rounds_race("2026-10-15", late)
    assert not epochs.cs2_team_rounds_race("2026-10-14", late)


# --- B13: who a sample value was earned against --------------------------------


def test_an_observation_carries_its_opponent_and_old_samples_still_parse() -> None:
    from bet.sofa.contracts import Observation
    from bet.sofa.samples import _against, _team_id

    old = {"sofascore_event_id": 1, "match_date_utc": "2026-10-01T18:00:00Z",
           "opponent": "B", "value": 2.0, "competition_id": 5, "season_id": 9,
           "venue": "home"}
    obs = Observation.model_validate_json(__import__("json").dumps(old))
    assert obs.opponent_id is None and obs.against is None
    event = {"homeTeam": {"id": 10}, "awayTeam": {"id": 20},
             "homeScore": {"normaltime": 3, "current": 3},
             "awayScore": {"normaltime": 1, "current": 1}}
    assert _team_id(event["awayTeam"]) == 20 and _team_id({}) is None
    # the opponent's goals in the same match; a total has no "against"
    assert _against("goals_for", "football", {}, None, event, True) == 1.0
    assert _against("goals_for", "football", {}, None, event, False) == 3.0
    assert _against("goals_total", "football", {}, None, event, True) is None


# --- A3 + C8 + A8: basketball overtime and noise --------------------------------


def test_off_the_basketball_simulation_draws_exactly_as_before() -> None:
    import random as rnd

    from bet.sofa import score_model as sm

    mu1, mu2 = [20.0] * 4, [20.0] * 4
    a = [sm._basketball(rnd.Random(3), mu1, mu2, 6.0) for _ in range(200)]
    b = [sm._basketball(rnd.Random(3), mu1, mu2, 6.0, sm.SimParams(), None)
         for _ in range(200)]
    assert a == b


def test_twelve_minute_quarters_and_the_tie_pull() -> None:
    import random as rnd

    from bet.sofa import score_model as sm

    assert sm.quarter_minutes_for(132) == 12.0 and sm.quarter_minutes_for(9) == 10.0
    mu1, mu2 = [25.0] * 4, [25.0] * 4
    games = 4000

    def ot_points(qm: float | None) -> float:
        rng = rnd.Random(1)
        tot = n = 0
        for _ in range(games):
            g = sm._basketball(rng, mu1, mu2, 6.0, sm.SimParams(), qm)
            if g.overtime:
                tot += g.t1_full + g.t2_full - sum(g.t1_periods) - sum(g.t2_periods)
                n += 1
        return tot / n
    # an NBA overtime is 5/12 of a quarter, not 5/10
    assert ot_points(12.0) < ot_points(None)

    def draws(pull: float) -> float:
        rng = rnd.Random(2)
        prm = sm.SimParams(bb_tie_pull=pull)
        sims = [sm._basketball(rng, mu1, mu2, 6.0, prm) for _ in range(games)]
        return sum(1 for g in sims if sum(g.t1_periods) == sum(g.t2_periods)) / games
    assert draws(0.5) > draws(0.0) + 0.02
    assert sm.overtime_params(None, "basketball", True) == sm.SimParams(
        bb_tie_pull=sm.BB_TIE_PULL)
    assert sm.overtime_params(None, "hockey", True) is None
    assert sm.overtime_minutes(132, "basketball", False) is None


def test_the_one_step_residuals_change_only_the_noise_fit() -> None:
    import random as rnd

    from bet.sofa import score_model as sm

    rng = rnd.Random(5)
    history = []
    for i in range(400):
        hq = [20 + rng.gauss(0, 4.0) for _ in range(4)]
        aq = [19 + rng.gauss(0, 4.0) for _ in range(4)]
        vals = {f"p{k + 1}_for": (hq[k], aq[k]) for k in range(4)}
        vals[sm.REG_METRIC["basketball"]] = (sum(hq), sum(aq))
        history.append(sm.FootballResult(i, i * 3600, 5, 100 + i % 6, 200 + i % 6,
                                         vals))
    bb = shadow.SPORTS["basketball"]
    old = sm.build_model(history, bb, cut_ts=10**9)
    new = sm.build_model(history, bb, cut_ts=10**9,
                         params=sm.SimParams(bb_resid_one_step=True))
    assert old.shares == new.shares
    assert old.expected(5, 100, 200) == new.expected(5, 100, 200)
    assert old.params.bb_quarter_sd != new.params.bb_quarter_sd


def test_the_morning_refresh_also_fetches_the_measured_sports_statistics() -> None:
    import importlib.util
    import sys as _sys

    path = Path(__file__).resolve().parents[2] / "scripts/sofa/refresh_line_evidence.py"
    spec = importlib.util.spec_from_file_location("rle_stats", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    _sys.modules["rle_stats"] = mod
    spec.loader.exec_module(mod)
    cmds = mod.stats_commands()
    assert [c[3] for c in cmds] == ["hockey", "basketball", "volleyball"]
    assert all("--with-lineups" in c and "backfill_event_stats.py" in c[1]
               for c in cmds)
