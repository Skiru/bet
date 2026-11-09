"""epochs.SCHEDULE_TERM: the football schedule / fatigue term on the pure
rating goals centres (path (ii); bet.sofa.schedule_term) - the arithmetic,
the forecast wrapper, the windowed feature read against the full calendar,
SHEET's rows with the switch off and on, rebuild_plan, the rating-gap note
and SAME_EVENT_DEDUP."""

from __future__ import annotations

import json
import math
import random
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import football_rating as fr
from bet.sofa import football_sim_markets as fsm
from bet.sofa import football_sim_sheet as fss
from bet.sofa import leg_identity as li
from bet.sofa import rating_market_gap as rmg
from bet.sofa import schedule_term as st
from bet.sofa.config import SofaConfig, config_path
from bet.sofa.contracts import (
    FixtureOffer,
    FixtureSamples,
    MetricSample,
    Observation,
    PricedRung,
)
from bet.sofa.football_incidents import IncidentPricing, IncidentRates
from bet.sofa.football_result import ResultConfig, result_probs
from bet.sofa.football_sim import neutral_params
from bet.sofa.schedule_features import (
    DAY_S,
    FOOTBALL_COLUMNS,
    FootballSideFeatures,
    calendar_from_events,
)
from tests.sofa.test_schedule_features import ev

CFG = ResultConfig(nb_r=7.586, source="test")
PRE_KICKOFF = datetime(2026, 9, 22, tzinfo=UTC)
UCL = 7
FROZEN = Path("docs/sofa/evidence/kontekst_terminarza_2026-11-08/frozen/fr_frozen.json")


def _feat(bucket: str | None = "R3", *, coverage: bool = True, intl: bool = False,
          kind: str | None = None, cont_prev: bool = False, et: bool = False,
          dense: bool = False, cont_next: bool = False) -> FootballSideFeatures:
    return FootballSideFeatures(
        coverage=coverage, rest_d=6.0, rest_bucket=bucket, intl_return=intl,
        layoff_kind=kind, cont_prev4=cont_prev, et_prev=et, dense14=dense,
        cont_next4=cont_next, matches_7d=1, matches_14d=2)


def _terms(**coef: float) -> st.ScheduleTerms:
    return st.ScheduleTerms(FOOTBALL_COLUMNS, coef, frozenset(
        epochs.SCHEDULE_TERM_FLOOR_EXCLUDED))


# --- config and switch --------------------------------------------------------


def test_installed_config_is_the_frozen_exam_file() -> None:
    doc = json.loads(config_path(st.CONFIG_FILE).read_text())
    frozen = json.loads((Path(__file__).parents[2] / FROZEN).read_text())
    assert doc["coef"] == frozen["coef"] and len(doc["coef"]) == 22
    terms = st.load()
    assert terms.columns == FOOTBALL_COLUMNS
    assert dict(terms.coef) == frozen["coef"]
    assert terms.excluded_markets == epochs.SCHEDULE_TERM_FLOOR_EXCLUDED
    assert doc["fitted_from"]["exam_spec_sha"].startswith("87a5087f")
    assert doc["unfitted_constants"] == list(st.UNFITTED_CONSTANTS)
    assert "sofa_schedule_terms.json" in __import__(
        "bet.sofa.sheet_config", fromlist=["x"]).SHEET_OPTIONAL_FILES


def test_a_bad_config_is_refused(tmp_path: Path) -> None:
    good = json.loads(config_path(st.CONFIG_FILE).read_text())
    bad = dict(good, coef={**good["coef"], "own_R9": 0.1})
    p = tmp_path / "c.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="own_R9"):
        st.load(p)
    p.write_text(json.dumps(dict(good, columns=["R1"])))
    with pytest.raises(ValueError, match="columns"):
        st.load(p)


def test_market_scope_matches_the_code() -> None:
    from bet.sofa.football_1x2_dnb import MARKETS as R12
    from bet.sofa.football_incidents import FIRST_GOAL
    from bet.sofa.football_result import DOUBLE_CHANCE
    from bet.sofa.football_score_markets import MARKETS as SCORE

    assert epochs.SCHEDULE_TERM_MARKETS == (
        set(R12) | set(SCORE) | {DOUBLE_CHANCE, FIRST_GOAL}
        | (fsm.MARKETS - epochs.SCHEDULE_TERM_FLOOR_EXCLUDED))
    assert epochs.SCHEDULE_TERM_FLOOR_EXCLUDED == {
        m for m, _ in epochs.FOOTBALL_SIM_FLOOR_KEYS}
    assert not epochs.SCHEDULE_TERM_MARKETS & epochs.SCHEDULE_TERM_FLOOR_EXCLUDED


def test_switch_reads_the_day_and_the_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    # installed from the next day 00:00Z after the exam's install commit
    at = datetime(2026, 11, 10, tzinfo=UTC)
    assert epochs.SCHEDULE_TERM_FROM_UTC == at
    monkeypatch.setattr(epochs, "SCHEDULE_TERM_FROM_UTC", None)
    assert not epochs.schedule_term("2030-01-01", datetime(2030, 1, 1, tzinfo=UTC))
    monkeypatch.setattr(epochs, "SCHEDULE_TERM_FROM_UTC", at)
    assert epochs.schedule_term("2026-11-10", at)
    assert epochs.schedule_term("2026-11-11", at + timedelta(days=1))
    assert not epochs.schedule_term("2026-11-10", at - timedelta(minutes=1))
    assert not epochs.schedule_term("2026-11-09", at)
    assert epochs.SCHEDULE_TERM_MARKER == ("schedule_term_rule", "schedule_term_v1",
                                           "football")


# --- arithmetic -----------------------------------------------------------------


def test_side_term_sums_own_and_opponent_columns() -> None:
    coef = {"own_R1": -0.1, "own_cont_prev4": -0.2, "own_cont_prev4_x_R1": 0.05,
            "opp_R5_other": 0.3, "opp_dense14": 0.07}
    own = _feat("R1", cont_prev=True)
    opp = _feat("R5", kind="other", dense=True)
    assert st.side_term(coef, own, opp) == pytest.approx(
        -0.1 - 0.2 + 0.05 + 0.3 + 0.07)
    # the reference bucket and absent coefficients add nothing
    assert st.side_term(coef, _feat("R3"), _feat("R3")) == 0.0
    assert st.side_term({}, own, opp) == 0.0
    # R5_season_start has no coefficient: x1
    assert st.side_term({"own_R5_other": 1.0}, _feat("R5", kind="season_start"),
                        _feat()) == 0.0


def test_no_coverage_on_either_side_or_a_national_fixture_is_x1() -> None:
    coef = {"own_R1": -0.5, "opp_R1": 0.5}
    terms = _terms(**coef)
    covered, uncovered = _feat("R1"), _feat("R1", coverage=False)
    assert st.side_term(coef, covered, uncovered) == 0.0
    assert st.side_term(coef, uncovered, covered) == 0.0
    t = st.fixture_term(terms, covered, uncovered, national=False)
    assert (t.status, t.t_home, t.t_away, t.moves) == (st.NO_COVERAGE, 0.0, 0.0, False)
    t = st.fixture_term(terms, covered, covered, national=True)
    assert (t.status, t.moves) == (st.NATIONAL, False)
    t = st.fixture_term(terms, _feat("R1"), _feat("R3"), national=False)
    assert t.status == st.APPLIED and t.t_home == -0.5 and t.t_away == 0.5
    field = t.row_field()
    assert field["home"]["indicators"] == ["R1"] and field["away"]["indicators"] == []
    assert field["home"]["rest_bucket"] == "R1"


# --- the forecast wrapper -------------------------------------------------------


def _book() -> fr.RatingBook:
    history = []
    t = 0
    for i in range(fr.MIN_LEAGUE_MATCHES + 10):
        history.append(fr.FootballResult(
            i * 2, t, 1, 1, 100 + i,
            {"goals_for": (3.0, 1.0), "cards_points_for": (20.0, 30.0)}))
        history.append(fr.FootballResult(
            i * 2 + 1, t + 1, 1, 200 + i, 2,
            {"goals_for": (1.0, 1.0), "cards_points_for": (25.0, 25.0)}))
        t += DAY_S
    return fr.replay(history, cut_ts=10**9)


def _forecast() -> fr.FootballForecast:
    return fr.FootballForecast(_book(), 1, 1, 2)


def test_wrapper_moves_only_the_goals_centres() -> None:
    base = _forecast()
    w = st.ScheduleTermForecast.wrap(base, -0.1, 0.2)
    for side, t in (("side_a", -0.1), ("side_b", 0.2)):
        b, c = base.centre("goals_for", side), w.centre("goals_for", side)
        assert b is not None and c is not None
        assert c[0] == pytest.approx(b[0] * math.exp(t))
        assert st.NOTE in c[1]
        # every other metric and the total are the wrapped forecast's
        for market in ("cards_points_for", "goals_total"):
            assert w.centre(market, side) == base.centre(market, side)
        assert w.supremacy(side) == base.supremacy(side)
    assert w.fixture_link() == base.fixture_link()
    assert w.link_status("goals_for") == base.link_status("goals_for")
    assert w.no_league_rate("goals_for") == base.no_league_rate("goals_for")
    assert w.venue_multiplier("goals_for", "side_a", ["home"]) == (
        base.venue_multiplier("goals_for", "side_a", ["home"]))
    assert st.ScheduleTermForecast.wrap(base, 0.0, 0.0).centre(
        "goals_for", "side_a") == base.centre("goals_for", "side_a")
    # the simulator reads the corrected goals and the uncorrected cards
    c = fss.centres_of(w)
    b = fss.centres_of(base)
    assert c is not None and b is not None and c.cards == b.cards
    assert c.goals[0] == pytest.approx(b.goals[0] * math.exp(-0.1))


# --- the windowed feature read --------------------------------------------------


K = 1_780_000_000 - 1_780_000_000 % DAY_S + 15 * 3600


def _synthetic_events(seed: int) -> list[dict[str, Any]]:
    """Two years of a 30-team world: two leagues, a continental cup, a
    domestic cup whose season spans > 150 days, international breaks (>= 30
    national matches a day), extra time, unplayed fixtures."""
    rnd = random.Random(seed)
    out: list[dict[str, Any]] = []
    eid = 1
    teams = list(range(100, 130))
    for day in range(-700, 40):
        ts0 = K + day * DAY_S
        if day % 30 == 7:  # an international break day
            for j in range(31):
                out.append(ev(eid, ts0 + j * 60, 9000 + 2 * j, 9001 + 2 * j,
                              comp=11, season=900 + day // 365, national=True))
                eid += 1
        if day % 120 in range(60, 95):  # an off-season
            continue
        for _ in range(rnd.randint(0, 4)):
            h, a = rnd.sample(teams, 2)
            r = rnd.random()
            comp, season = ((UCL, 70 + day // 365) if r < 0.15
                            else (55, 5) if r < 0.2  # the long cup season
                            else (17, 10 + day // 200))
            status = "finished" if day < 0 else rnd.choice(
                ["notstarted", "finished", "postponed"])
            out.append(ev(eid, ts0 + rnd.randint(-8, 8) * 3600, h, a, comp=comp,
                          season=season, status=status, extra=rnd.random() < 0.05))
            eid += 1
    # a side whose only earlier match of the cup season is ~200 days back,
    # with a winter-free 25-day rest before the fixture: season_start or not
    out.append(ev(eid, K - 200 * DAY_S, 140, 141, comp=55, season=5))
    out.append(ev(eid + 1, K - 25 * DAY_S, 140, 142, comp=17, season=99))
    out.append(ev(eid + 2, K - 100 * DAY_S, 141, 143, comp=17, season=99))
    # no coverage
    out.append(ev(eid + 3, K - 130 * DAY_S, 144, 145, comp=17, season=99))
    out.append(ev(eid + 4, K - 150 * DAY_S - 1, 146, 147, comp=17, season=99))
    return out


def _keys(events: list[dict[str, Any]]) -> list[st.FixtureKey]:
    keys = [st.FixtureKey(e["id"], e["startTimestamp"], e["homeTeam"]["id"],
                          e["awayTeam"]["id"],
                          e["tournament"]["uniqueTournament"]["id"],
                          e["season"]["id"])
            for e in events if K <= e["startTimestamp"] < K + 5 * DAY_S]
    extra = [(140, 150, 55, 5), (141, 151, 17, 99), (144, 145, 17, 99),
             (146, 147, 17, 99)]
    for i, (h, a, comp, season) in enumerate(extra):
        keys.append(st.FixtureKey(10**7 + i, K + 3600, h, a, comp, season))
    return keys


def _db(tmp_path: Path, events: list[dict[str, Any]]) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "x.db")
    conn.execute("CREATE TABLE sofa_listed_event (event_id INTEGER PRIMARY KEY, "
                 "sport TEXT, start_ts INTEGER, fetched_at TEXT NOT NULL, "
                 "event_json TEXT NOT NULL)")
    conn.executemany(
        "INSERT INTO sofa_listed_event VALUES (?, ?, ?, ?, ?)",
        [(e["id"], "football", e["startTimestamp"], "x", json.dumps(e))
         for e in events] + [(10**8, "tennis", K, "x", "{}"),
                             (10**8 + 1, "football", K, "x", "not json")])
    conn.commit()
    return conn


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_windowed_features_equal_the_full_calendar(tmp_path: Path, seed: int) -> None:
    events = _synthetic_events(seed)
    keys = _keys(events)
    assert len(keys) > 4
    full = calendar_from_events(events, "football", continental=[UCL])
    conn = _db(tmp_path, events)
    terms = _terms(**json.loads(config_path(st.CONFIG_FILE).read_text())["coef"])
    got = st.fixture_terms(conn, keys, terms, [UCL])
    win_cal, _ = st.window_calendar(st.listed_events(conn, keys), keys, [UCL])
    assert len(win_cal) < len(full)
    covered = 0
    for k in keys:
        fh, fa = st.side_features(full, k)
        want = st.fixture_term(terms, fh, fa, national=False)
        term = got[k.event_id]
        assert (term.t_home, term.t_away, term.status) == (
            want.t_home, want.t_away, want.status)
        for a, b in ((term.home, fh), (term.away, fa)):
            assert a is not None
            assert a.coverage == b.coverage and a.indicators() == b.indicators()
            if b.coverage:
                assert a == b
                covered += 1
    assert covered > 4
    # the cup-season side: R5 and the season seen ~200 days back (not
    # season_start) - read only through the season clause
    cup = got[10**7]
    assert cup.home is not None and cup.home.rest_bucket == "R5"
    assert cup.home.layoff_kind == "other"
    assert got[10**7 + 2].status == st.NO_COVERAGE
    assert got[10**7 + 3].status == st.NO_COVERAGE


def test_window_edges(tmp_path: Path) -> None:
    """Coverage ends at 120 days, the SQL window at 150: a match 120 days
    back covers, 120 days + 1 s does not, and nothing older than the window
    is needed for a covered side."""
    events = [ev(1, K - 120 * DAY_S, 1, 2), ev(2, K - 120 * DAY_S - 1, 3, 4),
              ev(3, K - 150 * DAY_S, 5, 6, season=2),
              ev(4, K - 150 * DAY_S - 1, 7, 8, season=2),
              ev(5, K - 3 * DAY_S, 2, 9), ev(6, K - 200 * DAY_S, 1, 5, season=3)]
    keys = [st.FixtureKey(100 + i, K, h, a, 17, 1)
            for i, (h, a) in enumerate(((1, 2), (3, 2), (5, 2), (7, 2)))]
    conn = _db(tmp_path, events)
    cal, _ = st.window_calendar(st.listed_events(conn, keys), keys, [UCL])
    ids = {m for m in cal._by_id}  # noqa: SLF001 - the window's content
    assert ids == {1, 2, 3, 5}
    full = calendar_from_events(events, "football", continental=[UCL])
    for k in keys:
        assert st.side_features(cal, k)[0].coverage == (
            st.side_features(full, k)[0].coverage)
    assert [st.side_features(cal, k)[0].coverage for k in keys] == [
        True, False, False, False]
    assert st.side_features(cal, keys[0])[0] == st.side_features(full, keys[0])[0]


def test_a_national_fixture_takes_no_term(tmp_path: Path) -> None:
    events = [ev(1, K - 3 * DAY_S, 1, 2), ev(2, K - 4 * DAY_S, 3, 4),
              ev(3, K, 1, 3, national=True)]
    conn = _db(tmp_path, events)
    terms = _terms(own_R1=-0.5, opp_R1=0.5, own_R2=-0.3)
    key = st.FixtureKey(3, K, 1, 3, 17, 1)
    got = st.fixture_terms(conn, [key], terms, [UCL])[3]
    assert got.status == st.NATIONAL and not got.moves
    plain = st.fixture_terms(conn, [replace(key, event_id=99)], terms, [UCL])[99]
    assert plain.status == st.APPLIED and plain.moves
    flagged = st.fixture_terms(conn, [replace(key, event_id=99, national=True)],
                               terms, [UCL])[99]
    assert flagged.status == st.NATIONAL
    assert st.fixture_terms(conn, [], terms, [UCL]) == {}


# --- SHEET ------------------------------------------------------------------------


def _fixture() -> Any:
    from tests.sofa.test_player_markets import _fixture as fx

    return fx()


def _rungs() -> list[PricedRung]:
    def r(market: str, subject: str, line: float = 0.5, over: float | None = 2.0,
          under: float | None = None) -> PricedRung:
        return PricedRung(market=market, subject=subject, line=line, over_odds=over,
                          under_odds=under, fetched_at_utc=PRE_KICKOFF)
    return [
        r("goals_total", "", 2.5, 1.8, 1.95),
        r("double_chance", "12"),  # X left out
        r("result_1x2", "1", over=2.15, under=1.66),
        r("draw_no_bet", "1", over=1.59, under=2.25),
        r("result_or_over", "X", 2.5),
        r("first_goal", "1"),
        r("htft", "1/1", over=3.1),
        r("btts_any_half", "", over=1.9, under=1.8),  # a floor key: excluded
    ]


def _sheet(term: st.FixtureTerm | None,
           terms: st.ScheduleTerms | None = None) -> list[dict[str, Any]]:
    from scripts.sofa.run_sheet import process_fixture, sheet_row_json

    obs = [Observation(sofascore_event_id=1000 + i,
                       match_date_utc=PRE_KICKOFF - timedelta(days=i + 1),
                       value=float(v), opponent=f"O{i}", venue="home",
                       competition_id=1, season_id=1)
           for i, v in enumerate([2, 3, 1, 4, 2, 3, 2, 1, 3, 2])]
    samples = FixtureSamples(
        sofascore_event_id=1, readiness="READY", gaps=[],
        metrics={"goals_total": MetricSample(
            metric="goals_total", side_a=obs, side_b=obs, h2h=[])})
    offer = FixtureOffer(sofascore_event_id=1, status="PRICED",
                         unmapped_markets=[], rungs=_rungs())
    params = neutral_params()
    rows, _ = process_fixture(
        _fixture(), samples, offer, baselines={}, reliability={},
        engine_constants={}, vetoes=[], config=SofaConfig(), football=_forecast(),
        stats_only=True, result_config=CFG, result_1x2_dnb=CFG, score_markets=CFG,
        incident_pricing=IncidentPricing(IncidentRates({}, {}, {}), CFG),
        sim_pricer=fss.SimPricer(params, sims=1000),
        schedule_term=term,
        schedule_terms=(terms if terms is not None
                        else _terms() if term is not None else None),
        base_sim_pricer=(fss.SimPricer(params, sims=1000)
                         if term is not None else None))
    return [sheet_row_json(r) for r in rows]


def _applied(t_home: float, t_away: float) -> st.FixtureTerm:
    return st.FixtureTerm(st.APPLIED, t_home, t_away, _feat("R1"),
                          _feat("R5", kind="other"))


def _key(r: dict[str, Any]) -> tuple[Any, ...]:
    return (r["market"], r["subject"], r["line"], r["direction"])


def test_switch_off_rows_are_unchanged() -> None:
    off = _sheet(None)
    assert {r["market"] for r in off} >= {"double_chance", "result_1x2", "htft",
                                         "first_goal", "result_or_over"}
    for r in off:
        assert not {"schedule_term_rule", "schedule_term",
                    "p_central_no_schedule_term"} & set(r)
    # a fixture whose t is 0 prices every row as before, only annotated
    zero = _sheet(_applied(0.0, 0.0))
    strip = ("schedule_term", "p_central_no_schedule_term")
    for a, b in zip(off, zero, strict=True):
        if b["market"] in epochs.SCHEDULE_TERM_MARKETS:
            assert b["p_central_no_schedule_term"] == b["p_central"]
            assert b["notes"][-1] == st.unfitted_note()
            b = {k: v for k, v in b.items() if k not in strip}
            b["notes"] = b["notes"][:-1]
        elif b["market"] in epochs.SCHEDULE_TERM_FLOOR_EXCLUDED:
            assert b["schedule_term"]["status"] == st.EXCLUDED_FLOOR
            b = {k: v for k, v in b.items() if k not in strip}
        assert a == b


def test_switch_on_rows_carry_the_term_and_the_shadow() -> None:
    th, ta = -0.08, 0.06
    off = {_key(r): r for r in _sheet(None)}
    on = {_key(r): r for r in _sheet(_applied(th, ta))}
    assert set(on) == set(off)
    base = _forecast()
    hc, ac = base.centre("goals_for", "side_a"), base.centre("goals_for", "side_b")
    assert hc is not None and ac is not None
    lh, la = hc[0], ac[0]
    want_dc = result_probs(lh * math.exp(th), la * math.exp(ta), CFG.nb_r)["12"]
    dc = on[("double_chance", "12", 0.5, "OVER")]
    assert dc["p_central"] == round(want_dc, 4)
    assert dc["p_central_no_schedule_term"] == off[_key(dc)]["p_central"]
    assert dc["p_central"] != dc["p_central_no_schedule_term"]
    assert dc["schedule_term"]["t_home"] == th and dc["schedule_term"]["t_away"] == ta
    assert dc["schedule_term"]["status"] == st.APPLIED
    assert dc["schedule_term"]["home"]["indicators"] == ["R1"]
    assert any(n.startswith(st.NOTE + ":") for n in dc["notes"])
    assert any(n.startswith("UNFITTED_CONSTANTS:") and "SCHEDULE_COVERAGE_DAYS" in n
               for n in dc["notes"])
    for key in (("result_1x2", "1", 0.5, "OVER"), ("draw_no_bet", "1", 0.5, "UNDER"),
                ("result_or_over", "X", 2.5, "OVER"), ("first_goal", "1", 0.5, "OVER"),
                ("htft", "1/1", 0.5, "OVER")):
        row = on[key]
        assert row["p_central_no_schedule_term"] == off[key]["p_central"], key
        assert row["p_central"] != row["p_central_no_schedule_term"], key
    # the simulator's floor keys and the sample rows keep the uncorrected p
    for key, row in on.items():
        if row["market"] in ("btts_any_half", "goals_total"):
            assert row["p_central"] == off[key]["p_central"]
            assert "p_central_no_schedule_term" not in row
    assert on[("btts_any_half", "", 0.5, "OVER")]["schedule_term"]["status"] == (
        st.EXCLUDED_FLOOR)
    assert "schedule_term" not in on[("goals_total", "", 2.5, "OVER")]


def test_main_stamps_the_marker_on_every_football_row() -> None:
    from scripts.sofa.run_sheet import AUDIT_MARKER_FIELDS

    assert "schedule_term_rule" in AUDIT_MARKER_FIELDS
    rows = [{"sport": "football", "schedule_term_rule": epochs.SCHEDULE_TERM},
            {"sport": "tennis"}]
    assert epochs.sheet_has_marker(rows, epochs.SCHEDULE_TERM_MARKER)
    assert not epochs.sheet_has_marker([{"sport": "football"}],
                                       epochs.SCHEDULE_TERM_MARKER)


# --- rebuild_plan -----------------------------------------------------------------


def test_rebuild_reruns_sheet_without_the_marker(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from bet.sofa import rebuild_plan as rp

    now = datetime(2026, 11, 12, 9, tzinfo=UTC)
    td = timedelta

    def state(**kw: Any) -> Any:
        base: dict[str, Any] = dict(
            offer_fixtures=2, open_fixtures=2, oldest_open_rung=now - td(minutes=5),
            newest_rung=now - td(minutes=5), offer_has_football=True)
        base.update(kw)
        return rp.DayState("2026-11-12", now, td(minutes=45), **base)

    assert epochs.SCHEDULE_TERM_MARKER in rp.AUDIT_MARKERS
    monkeypatch.setattr(epochs, "SCHEDULE_TERM_FROM_UTC", None)
    assert not any("epochs.schedule_term" in w
                   for w in rp.audit_sheet_stale(state(sheet_schedule_term=False)))
    monkeypatch.setattr(epochs, "SCHEDULE_TERM_FROM_UTC",
                        datetime(2026, 11, 12, tzinfo=UTC))
    why = rp.audit_sheet_stale(state(sheet_schedule_term=False))
    assert any("epochs.schedule_term" in w for w in why)
    assert "SHEET" in rp.build_plan(state(sheet_schedule_term=False)).names()
    assert not any("epochs.schedule_term" in w
                   for w in rp.audit_sheet_stale(state(sheet_schedule_term=True)))


# --- the rating gap note and SAME_EVENT_DEDUP --------------------------------------


def test_rating_gap_reads_the_uncorrected_centres_from_a_corrected_row() -> None:
    th, ta = -0.08, 0.06
    on = [r for r in _sheet(_applied(th, ta))
          if r["market"] in ("double_chance", "result_1x2")]
    base = _forecast()
    hc, ac = base.centre("goals_for", "side_a"), base.centre("goals_for", "side_b")
    assert hc is not None and ac is not None
    for row in on:
        view, _ = rmg.rating_view([row])
        assert view is not None
        assert (view.home, view.away) == (round(hc[0], 3), round(ac[0], 3))
        note = next(n for n in row["notes"] if "pure rating centres" in n)
        corrected = (f"= home {hc[0] * math.exp(th):.3f} / away "
                     f"{ac[0] * math.exp(ta):.3f}")
        assert corrected in note


def test_same_event_twins_dedup_with_one_twin_corrected() -> None:
    """SAME_EVENT_DEDUP is logic on the market names: a corrected
    result_or_btts and its uncorrected twin goals_for 0.5 are still one
    event, whatever their p."""
    match = "Raith Rovers - Dunfermline Athletic"
    board = ("Raith Rovers", "Dunfermline")
    corrected = {"sport": "football", "match": match, "market": "result_or_btts",
                 "subject": "1", "line": 0.5, "direction": "OVER",
                 "confidence": 0.81, "p_central_no_schedule_term": 0.78,
                 "schedule_term": {"status": st.APPLIED, "t_home": 0.05}}
    twin = {"sport": "football", "match": match, "market": "goals_for",
            "subject": "raith rovers", "line": 0.5, "direction": "OVER",
            "confidence": 0.74}
    a, b = li.event_key(corrected, board), li.event_key(twin, board)
    assert a is not None and a == b
    bare = {k: v for k, v in corrected.items()
            if k not in ("schedule_term", "p_central_no_schedule_term")}
    assert li.event_key(bare, board) == a
