"""Evidence from one league carried into another without an adjustment.

2026-09-30: FK Aktobe (women, Kazakhstan: 20-0, 15-0, 12-0 at home) met Ajax
(women) in the UEFA Europa Cup a week after losing to them 0-8. The football
rating kept one attack/defence ratio per team, relative to the league of the
match it was earned in, and multiplied it by the Europa Cup's rate: Aktobe
2.59 - Ajax 1.45, goals UNDER 6.5 onto the PDF at 0.823. Its confidence came
from a curve fitted almost entirely on men's football.

These tests pin the four repairs: a league-strength term learnt only from
matches between leagues; a capped surprise so one blowout cannot move a ratio
far; a flag (and a CONFIDENCE refusal) for a fixture whose two sides share
nothing the model holds; and a women's leg read from women's curves only.
"""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from bet.sofa.confidence import (
    CLASS_TENNIS_TEAM_CUP,
    CLASS_WOMEN,
    Calibration,
    has_cross_league_unlinked_note,
    match_class,
)
from bet.sofa.football_rating import (
    ALPHA_BY_METRIC,
    CROSS_LEAGUE_UNLINKED_NOTE,
    LINK_MIN_MATCHES,
    LINKED,
    LINKED_BY_STRENGTH,
    MAX_SURPRISE,
    MIN_STRENGTH_LINKS,
    UNLINKED,
    FootballForecast,
    FootballResult,
    RatingBook,
    parse_event,
    replay,
)
from bet.sofa.samples import FRIENDLY_COMPETITION_IDS

DAY = 86400
WEAK, STRONG, CUP = 10, 20, 30


def _m(eid, ts, comp, home, away, goals):
    return FootballResult(eid, ts, comp, home, away, {"goals_for": goals})


def _league(comp, teams, rounds, score, start, eid0):
    """A round robin in `comp`; the first team wins every match by `score`."""
    out, eid, t = [], eid0, start
    for _ in range(rounds):
        for i, h in enumerate(teams):
            for a in teams[i + 1:]:
                goals = score if h == teams[0] else (1.0, 1.0)
                out.append(_m(eid, t, comp, h, a, goals))
                eid += 1
                t += 3600
    return out, eid, t


def _two_leagues(cross_matches: int = 0):
    """Team 1 dominates a weak league; team 101 is average in a strong one.

    `cross_matches` cup matches between the two leagues' other teams, which
    the strong league wins 3-0 - the only evidence of the gap.
    """
    weak = [1, 2, 3, 4, 5, 6]
    strong = [101, 102, 103, 104, 105, 106]
    h1, eid, t = _league(WEAK, weak, 4, (6.0, 0.0), 0, 0)
    h2, eid, t = _league(STRONG, strong, 4, (1.0, 1.0), 0, eid)
    history = h1 + h2
    t = max(r.ts for r in history) + DAY
    for i in range(cross_matches):
        history.append(_m(eid, t, CUP, strong[1 + i % 5], weak[1 + i % 5], (3.0, 0.0)))
        eid += 1
        t += DAY
    return sorted(history, key=lambda r: (r.ts, r.event_id)), t


def test_two_sides_that_share_no_league_are_unlinked():
    history, t = _two_leagues()
    book = replay(history, cut_ts=t + DAY)
    assert book.linked(2, 3)
    assert not book.linked(1, 101)
    assert book.link(1, 101, "goals_for") == (UNLINKED, 0.0)
    forecast = FootballForecast(book, CUP, 1, 101)
    assert forecast.fixture_link() == UNLINKED
    centre = forecast.centre("goals_total", None)
    assert centre is not None and "UNLINKED" in centre[1]


def test_teams_of_one_league_are_linked_and_unadjusted():
    history, t = _two_leagues()
    book = replay(history, cut_ts=t + DAY)
    assert book.link(1, 2, "goals_for") == (LINKED, 0.0)


def test_matches_between_leagues_teach_the_gap_and_it_is_used():
    history, t = _two_leagues(cross_matches=MIN_STRENGTH_LINKS + 10)
    book = replay(history, cut_ts=t + DAY)
    status, gap = book.link(101, 1, "goals_for")
    assert status == LINKED_BY_STRENGTH
    assert gap > 0  # the strong league's side is the stronger one
    strong_d, weak_d = book.domain(101), book.domain(1)
    assert (strong_d, weak_d) == (STRONG, WEAK)
    sigma = {d: book.strength[(d, "goals_for")].sigma for d in (STRONG, WEAK)}
    assert sigma[STRONG] > sigma[WEAK]
    home, away = book.expected(CUP, 101, 1, "goals_for", gap)
    plain = book.expected(CUP, 101, 1, "goals_for")
    assert home > plain[0] and away < plain[1]
    centre = FootballForecast(book, CUP, 101, 1).centre("goals_for", "side_a")
    assert centre is not None and "log strength gap" in centre[1]


def test_too_few_matches_between_leagues_leave_the_gap_unmeasured():
    history, t = _two_leagues(cross_matches=MIN_STRENGTH_LINKS - 5)
    book = replay(history, cut_ts=t + DAY)
    assert book.link(101, 1, "goals_for")[0] == UNLINKED


def test_one_blowout_cannot_move_a_ratio_further_than_the_cap():
    history, t = _two_leagues()
    book = replay(history, cut_ts=t + DAY)
    before = book.teams[(2, "goals_for")].attack
    book.update(_m(10**6, t + DAY, WEAK, 2, 3, (12.0, 0.0)))
    after = book.teams[(2, "goals_for")].attack
    alpha = ALPHA_BY_METRIC["goals_for"]
    assert after - before <= alpha * (MAX_SURPRISE - before) + 1e-9


def test_a_friendly_is_neither_history_nor_a_rated_fixture():
    friendly = min(FRIENDLY_COMPETITION_IDS)
    event = {
        "id": 5, "startTimestamp": 1000,
        "tournament": {"id": 77, "uniqueTournament": {"id": friendly},
                       "category": {"sport": {"slug": "football"}}},
        "status": {"type": "finished", "code": 100},
        "homeTeam": {"id": 1}, "awayTeam": {"id": 2},
        "homeScore": {"current": 9, "period1": 5, "period2": 4},
        "awayScore": {"current": 0, "period1": 0, "period2": 0},
    }
    assert parse_event(event) is None
    history, t = _two_leagues()
    book = replay(history, cut_ts=t + DAY)
    assert FootballForecast(book, friendly, 1, 2).centre("goals_total", None) is None


def test_the_friendly_list_covers_every_friendly_in_the_evidence():
    repo = Path(__file__).resolve().parents[2]
    evidence = json.loads(
        (repo / "docs/sofa/evidence/friendly_competitions_2026-09-30.json").read_text())
    cfg = json.loads((repo / "config/sofa_friendly_competitions.json").read_text())
    excluded = {e["competition_id"] for e in cfg["excluded"]}
    allowed = {e["competition_id"] for e in cfg["allowed"]}
    assert not excluded & allowed
    for comp in evidence["competitions"]:
        assert comp["competition_id"] in excluded | allowed, comp["name"]
    for entry in cfg["allowed"]:
        assert entry["reason"]
    assert excluded == set(FRIENDLY_COMPETITION_IDS)


# --- SHEET and CONFIDENCE -----------------------------------------------------


def test_sheet_flags_every_row_of_an_unlinked_fixture():
    from tests.sofa.test_football_rating import _rows

    history, t = _two_leagues()
    book = replay(history, cut_ts=t + DAY)
    rows = _rows(FootballForecast(book, CUP, 1, 101))
    assert rows and all(
        any(n.startswith(CROSS_LEAGUE_UNLINKED_NOTE) for n in r.notes) for r in rows)
    linked_rows = _rows(FootballForecast(book, WEAK, 1, 2))
    assert linked_rows and not any(
        n.startswith(CROSS_LEAGUE_UNLINKED_NOTE) for r in linked_rows for n in r.notes)


def test_confidence_refuses_an_unlinked_leg():
    assert has_cross_league_unlinked_note([f"{CROSS_LEAGUE_UNLINKED_NOTE}: x"])
    assert not has_cross_league_unlinked_note(["FOOTBALL_RATING: ..."])
    assert not has_cross_league_unlinked_note(None)
    repo = Path(__file__).resolve().parents[2]
    src = (repo / "scripts/sofa/run_confidence.py").read_text()
    assert 'refused["CROSS_LEAGUE_UNLINKED"]' in src
    assert "match_class(" in src
    # NO_CLASS_CURVE counts only legs the unclassed curves would have served
    assert 'refused["NO_CLASS_CURVE"]' in src
    assert "hit is None and klass is not None and cal.realised(" in src


# --- match class -------------------------------------------------------------


def test_the_match_class_is_read_from_the_board_or_the_competition():
    board = ("Aktobe (K)", "Ajax Amsterdam (K)")
    assert match_class("football", "Premier League", board) == CLASS_WOMEN
    assert match_class("football", "UEFA Europa Cup, Women", None) == CLASS_WOMEN
    assert match_class("football", "NWSL", ("Portland", "Seattle")) == CLASS_WOMEN
    assert match_class("football", "Premier League", ("Arsenal", "Chelsea")) is None
    assert match_class("tennis", "ATP", ("A (K)", "B")) is None
    assert match_class("tennis", "Davis Cup") == CLASS_TENNIS_TEAM_CUP
    assert match_class("tennis", "Billie Jean King Cup") == CLASS_TENNIS_TEAM_CUP
    assert match_class("tennis", "Exhibition") == CLASS_TENNIS_TEAM_CUP
    assert match_class("tennis", "ITF Men") is None


def _curve(realised_lo: float, n: int = 1000) -> dict:
    return {"0.800-0.825": {"n": n, "realised": realised_lo + 0.01,
                            "realised_lo95": realised_lo}}


def test_a_womens_leg_reads_the_womens_curve_and_nothing_else():
    cal = Calibration(
        pooled=_curve(0.80), by_market={"goals_total": _curve(0.81)},
        pooled_by_sport={"football": _curve(0.80)},
        by_class={CLASS_WOMEN: {"by_market": {"goals_total": _curve(0.78)},
                                "by_market_direction": {}, "pooled_by_sport": {}}},
    )
    men = cal.realised("goals_total", 0.81, "football", "UNDER")
    women = cal.realised("goals_total", 0.81, "football", "UNDER", CLASS_WOMEN)
    assert men is not None and men[0] == pytest.approx(0.81)
    assert women is not None and women[0] == pytest.approx(0.78)
    assert women[1].startswith(f"{CLASS_WOMEN}:")
    # No class curve for this market, no class pool: refused, never the men's.
    assert cal.realised("corners_total", 0.81, "football", "UNDER", CLASS_WOMEN) is None


def test_a_file_without_the_class_refuses_the_class():
    cal = Calibration(pooled=_curve(0.80), by_market={"goals_total": _curve(0.81)})
    assert cal.realised("goals_total", 0.81, "football", "UNDER", CLASS_WOMEN) is None


def test_the_class_only_fit_leaves_every_other_curve_untouched(tmp_path: Path):
    db = tmp_path / "sofa.db"
    con = sqlite3.connect(db)
    con.execute("""create table sofa_settled_row (market text, line real,
        direction text, sample_size int, sample_mean real, sample_sd real,
        actual_value real, p_central real, sport text, sofascore_event_id int)""")
    con.execute("create table sofa_entity_events (kind text, events_json text)")
    rows = []
    for i in range(1200):
        eid = 1 if i % 2 else 2  # event 1 is a women's match
        rows.append(("goals_total", 4.5, "UNDER", 10, 2.0, 1.2,
                     2.0 if i % 5 else 6.0, 0.9, "football", eid))
    con.executemany("insert into sofa_settled_row values (?,?,?,?,?,?,?,?,?,?)", rows)
    events = {"events": [
        {"id": 1, "homeTeam": {"gender": "F"}, "awayTeam": {"gender": "F"},
         "tournament": {"category": {"sport": {"slug": "football"}}}},
        {"id": 2, "homeTeam": {"gender": "M"}, "awayTeam": {"gender": "M"},
         "tournament": {"category": {"sport": {"slug": "football"}}}},
    ]}
    con.execute("insert into sofa_entity_events values ('last', ?)",
                (json.dumps(events),))
    con.commit()
    con.close()
    out = tmp_path / "cal.json"
    original = {"_doc": "x", "pooled": {"0.600-0.700": {"n": 1}},
                "by_market": {"corners_total": {}}, "pooled_by_sport": {}}
    out.write_text(json.dumps(original))
    repo = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, "scripts/sofa/fit_confidence.py", "--db-path", str(db),
         "--out", str(out), "--classes-only"],
        cwd=repo, capture_output=True, text=True,
        env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(out.read_text())
    for key, value in original.items():
        assert doc[key] == value
    women = doc["by_class"][CLASS_WOMEN]
    assert "goals_total" in women["by_market"]
    assert sum(b["n"] for b in women["by_market"]["goals_total"].values()) == 600


def test_link_needs_both_sides_in_one_competition():
    book = RatingBook()
    t = 0
    for i in range(LINK_MIN_MATCHES):
        book.update(_m(i, t + i, WEAK, 1, 50 + i, (1.0, 1.0)))
        book.update(_m(100 + i, t + i, WEAK, 2, 60 + i, (1.0, 1.0)))
    assert book.linked(1, 2)
    book2 = RatingBook()
    for i in range(LINK_MIN_MATCHES - 1):
        book2.update(_m(i, i, WEAK, 1, 50 + i, (1.0, 1.0)))
    for i in range(LINK_MIN_MATCHES):
        book2.update(_m(100 + i, i, WEAK, 2, 60 + i, (1.0, 1.0)))
    assert not book2.linked(1, 2)


def test_a_tennis_team_cup_leg_has_no_curve_and_is_refused():
    cal = Calibration(pooled=_curve(0.80), by_market={"games_total": _curve(0.81)},
                      pooled_by_sport={"tennis": _curve(0.80)})
    assert cal.realised("games_total", 0.81, "tennis", "UNDER") is not None
    assert cal.realised(
        "games_total", 0.81, "tennis", "UNDER", CLASS_TENNIS_TEAM_CUP) is None


def test_a_womens_league_without_a_baseline_reads_the_womens_pool():
    from scripts.sofa import run_sheet
    from tests.sofa.test_player_markets import _fixture

    women = _fixture().model_copy(update={
        "competition_id": 777, "competition_name": "Premier Division, Women"})
    men = _fixture().model_copy(update={"competition_id": 778,
                                        "competition_name": "Premier Division"})
    baselines = {"goals_total": {
        "global": {"mean": 3.17, "n": 300000},
        "900": {"mean": 3.6, "n": 250}, "901": {"mean": 3.4, "n": 250},
        "5": {"mean": 2.9, "n": 5000},
    }}
    ids = frozenset({900, 901})
    got = run_sheet.women_global_prior(baselines, "goals_total", women, ids)
    assert got is not None and got[0] == pytest.approx(3.5)
    assert got[1].startswith("PRIOR_GLOBAL_WOMEN")
    assert run_sheet.women_global_prior(baselines, "goals_total", men, ids) is None
    # its own fitted league wins; a thin women's pool is not a measurement
    baselines["goals_total"]["777"] = {"mean": 4.0, "n": 50}
    assert run_sheet.women_global_prior(baselines, "goals_total", women, ids) is None
    del baselines["goals_total"]["777"]
    assert run_sheet.women_global_prior(
        baselines, "goals_total", women, frozenset({900})) is None


def test_the_women_competitions_file_is_what_sheet_reads():
    from scripts.sofa import run_sheet

    assert len(run_sheet.WOMEN_COMPETITION_IDS) > 100
    assert 29194 in run_sheet.WOMEN_COMPETITION_IDS  # UEFA Europa Cup, Women


def test_a_thin_womens_league_falls_back_to_the_womens_rate():
    men = [FootballResult(i, i, 1, 100 + 2 * i, 101 + 2 * i,
                          {"goals_for": (1.0, 1.0)}) for i in range(40)]
    women = [FootballResult(1000 + i, 1000 + i, 2, 500 + 2 * i, 501 + 2 * i,
                            {"goals_for": (2.5, 2.5)}, women=True) for i in range(40)]
    thin = [FootballResult(5000 + i, 5000 + i, 3, 900 + 2 * i, 901 + 2 * i,
                           {"goals_for": (2.0, 2.0)}, women=True) for i in range(3)]
    book = replay([*men, *women, *thin], cut_ts=10**9)
    rates = book.league_rates(3, "goals_for")
    assert rates is not None and rates[0] > 2.0  # women's pool, not the men's 1.0
    thin_men = FootballResult(9000, 9000, 4, 950, 951, {"goals_for": (0.0, 0.0)})
    book.update(thin_men)
    men_rates = book.league_rates(4, "goals_for")
    assert men_rates is not None and men_rates[0] < 1.5


def test_womens_tennis_is_a_class_of_its_own():
    from bet.sofa.confidence import CLASS_TENNIS_WOMEN
    from scripts.sofa.fit_confidence import event_class

    assert match_class("tennis", "ITF Women") == CLASS_TENNIS_WOMEN
    assert match_class("tennis", "WTA 125") == CLASS_TENNIS_WOMEN
    assert match_class("tennis", "ATP") is None
    assert match_class("tennis", "Billie Jean King Cup") == CLASS_TENNIS_TEAM_CUP

    def ev(sport, category, gender=None):
        return {"tournament": {"category": {"name": category,
                                            "sport": {"slug": sport}}},
                "homeTeam": {"gender": gender}, "awayTeam": {"gender": gender}}

    assert event_class(ev("tennis", "ITF Women")) == CLASS_TENNIS_WOMEN
    assert event_class(ev("tennis", "Exhibition", "F")) == CLASS_TENNIS_TEAM_CUP
    assert event_class(ev("tennis", "Challenger", "M")) is None
    assert event_class(ev("football", "England", "F")) == CLASS_WOMEN
    assert event_class(ev("football", "England", "M")) is None
    assert event_class(ev("ice-hockey", "Sweden", "F")) is None


def test_sharing_only_the_cup_being_played_is_not_a_link():
    history, t = _two_leagues()
    book = replay(history, cut_ts=t + DAY)
    for i in range(LINK_MIN_MATCHES):
        book.update(_m(10**6 + i, t + i, CUP, 1, 100 + i, (1.0, 1.0)))
        book.update(_m(10**6 + 50 + i, t + i, CUP, 101, 200 + i, (1.0, 1.0)))
    assert book.domain(1) == WEAK and book.domain(101) == STRONG
    assert not book.linked(1, 101)


def test_a_rated_row_names_the_ratings_chosen_constants():
    from bet.sofa.football_rating import RATING_UNFITTED
    from tests.sofa.test_football_rating import _rated_book, _rows

    rows = _rows(FootballForecast(_rated_book(), 1, 1, 2))
    rated = [r for r in rows if any(n.startswith("FOOTBALL_RATING") for n in r.notes)]
    assert rated
    for r in rated:
        unfitted = next(n for n in r.notes if n.startswith("UNFITTED_CONSTANTS"))
        for name in RATING_UNFITTED:
            assert name in unfitted


def test_mens_leagues_with_a_women_looking_substring_are_not_women():
    for name in ("Liga FUTVE", "2. Liga FBIH", "3. Liga FVRZ", "Gruppenliga Frankfurt",
                 "Premier League"):
        assert match_class("football", name) is None, name
    for name in ("Liga F", "Première Ligue, Féminine", "Frauen-Bundesliga",
                 "UEFA Women's Champions League", "Damallsvenskan", "WSL"):
        assert match_class("football", name) == CLASS_WOMEN, name


def test_tennis_team_cups_include_the_mixed_ones():
    for name in ("United Cup", "Hopman Cup", "Laver Cup"):
        assert match_class("tennis", name) == CLASS_TENNIS_TEAM_CUP


def test_the_fit_and_the_run_classify_tennis_the_same_way():
    from scripts.sofa.fit_confidence import event_class

    girls = {"tournament": {"category": {"name": "Juniors",
                                         "sport": {"slug": "tennis"}}},
             "homeTeam": {"gender": "F"}, "awayTeam": {"gender": "F"}}
    assert event_class(girls) == match_class("tennis", "Juniors") is None


def test_a_zero_away_rate_leaves_the_home_defence_alone():
    book = RatingBook()
    for i in range(40):  # a league where the away side never scores
        book.update(_m(i, i, WEAK, 1 if i % 2 else 2, 50 + i, (1.0, 0.0)))
    before = book.teams[(1, "goals_for")].defence
    away_def = book.teams[(2, "goals_for")].defence
    book.update(_m(999, 999, WEAK, 1, 2, (1.0, 0.0)))
    assert book.league_rates(WEAK, "goals_for")[1] == 0.0
    assert book.teams[(1, "goals_for")].defence == before
    assert away_def is not None


def test_the_unlinked_flag_follows_the_markets_own_metric():
    history, t = _two_leagues(cross_matches=MIN_STRENGTH_LINKS + 10)
    book = replay(history, cut_ts=t + DAY)
    forecast = FootballForecast(book, CUP, 101, 1)
    assert forecast.link_status("goals_total") == LINKED_BY_STRENGTH
    # corners were never counted in these matches: no strength for them
    assert forecast.link_status("corners_total") == UNLINKED
    from scripts.sofa import run_sheet
    src = Path(run_sheet.__file__).read_text()
    assert "football.link_status(rung.market)" in src


def test_a_negative_half_is_no_count_anywhere():
    from bet.sofa.contracts import GapReason
    from bet.sofa.metrics import extract_metric

    event = {  # verbatim shape of cached event 8344189
        "id": 8344189, "startTimestamp": 1000,
        "tournament": {"id": 1, "uniqueTournament": {"id": 8077},
                       "category": {"sport": {"slug": "football"}}},
        "status": {"type": "finished", "code": 100},
        "homeTeam": {"id": 1}, "awayTeam": {"id": 2},
        "homeScore": {"current": 10, "period1": 5, "period2": -5, "normaltime": 0},
        "awayScore": {"current": 1, "period1": 0, "period2": 0, "normaltime": 0},
    }
    got = extract_metric("goals_2h_for", "football", {}, None, event, True)
    assert got == GapReason.INTERNAL_INCONSISTENT
    # Since 2026-10-04 the whole goal score is refused (period1 + period2 !=
    # normaltime, current != normaltime with no extra time): no goal count
    # from this match reaches the rating at all, so nothing can raise.
    r = parse_event(event)
    assert r is None or not any(k.startswith("goals") for k in r.values)
    if r is not None:
        RatingBook().update(r)  # must not raise


def test_a_league_rate_is_not_anchored_on_its_first_match():
    # UAE League Cup: the first cached match was 0-0 and kept 32% of the
    # weight after 57; the rate must be the plain mean while the league is
    # young.
    history = [_m(0, 0, 7, 1, 2, (0.0, 0.0))] + [
        _m(i, i, 7, 10 + 2 * i, 11 + 2 * i, (1.6, 1.5)) for i in range(1, 57)]
    book = replay(history, cut_ts=10**9)
    home, away = book.league_rates(7, "goals_for")
    # a plain mean for the first 50, smoothing after: within 0.1% of the
    # mean, where the old start-at-match-one smoothing sat 32% below it
    assert home == pytest.approx((1.6 * 56) / 57, rel=1e-3)
    assert away == pytest.approx((1.5 * 56) / 57, rel=1e-3)
    assert home > 1.5


def test_ratios_are_shrunk_toward_the_average_across_leagues():
    from bet.sofa.football_rating import CROSS_RATIO_POWER

    history, t = _two_leagues(cross_matches=MIN_STRENGTH_LINKS + 10)
    book = replay(history, cut_ts=t + DAY)
    status, gap = book.link(1, 101, "goals_for")
    assert status == LINKED_BY_STRENGTH and 0 < CROSS_RATIO_POWER < 1
    th, ta = book.teams[(1, "goals_for")], book.teams[(101, "goals_for")]
    rate = book.league_rates(CUP, "goals_for")
    home, _ = book.expected(CUP, 1, 101, "goals_for", gap, cross=True)
    import math
    assert home == pytest.approx(
        rate[0] * math.exp(gap) * (th.attack * ta.defence) ** CROSS_RATIO_POWER)
    linked_home, _ = book.expected(WEAK, 1, 2, "goals_for")
    t1, t2 = book.teams[(1, "goals_for")], book.teams[(2, "goals_for")]
    assert linked_home == pytest.approx(
        book.league_rates(WEAK, "goals_for")[0] * t1.attack * t2.defence)


def test_the_spread_moves_with_the_centre():
    """A rated row whose centre falls keeps the sample's dispersion index,
    not its variance - so an UNDER at a halved centre is not over-claimed."""
    from bet.sofa.engine import calc_p_central_nb_raw, predictive_sd
    from tests.sofa.test_football_rating import _rated_book, _rows

    rows = _rows(FootballForecast(_rated_book(), 1, 1, 2))
    row = next(r for r in rows if r.direction == "UNDER")
    assert row.centre != row.sample_mean
    scale = row.centre / row.sample_mean
    var = row.sample_sd ** 2
    psd = predictive_sd(var * scale, row.sample_mean * scale, row.sample_size)
    boundary = row.line - 0.5 if row.line == int(row.line) else row.line
    expected = calc_p_central_nb_raw(row.centre, psd, boundary, "UNDER")
    assert row.p_central == pytest.approx(expected, abs=1e-3)


def test_one_reading_of_womens_football_for_sheet_and_confidence():
    from bet.sofa.confidence import WOMEN_COMPETITION_IDS
    from scripts.sofa import run_sheet
    from tests.sofa.test_player_markets import _fixture

    comp = next(iter(WOMEN_COMPETITION_IDS))
    plain_name = _fixture().model_copy(update={
        "competition_id": comp, "competition_name": "Premier Division"})
    assert run_sheet.is_womens_fixture(plain_name)  # by id, no marker in the name
    assert match_class("football", "Premier Division", None, comp) == CLASS_WOMEN
    assert match_class("football", "Premier Division", None, -1) is None


def test_the_history_cache_is_reused_only_under_the_same_fingerprint(
    tmp_path, monkeypatch
):
    import bet.sofa.football_rating as fr

    calls = []
    monkeypatch.setattr(fr, "_load_history_uncached", lambda db: calls.append(db) or [])
    fp = {"v": "a"}
    monkeypatch.setattr(fr, "history_fingerprint", lambda db: fp["v"])
    assert fr.load_history("x.db", tmp_path) == [] and len(calls) == 1
    assert fr.load_history("x.db", tmp_path) == [] and len(calls) == 1  # cached
    fp["v"] = "b"  # the listings changed
    assert fr.load_history("x.db", tmp_path) == [] and len(calls) == 2
