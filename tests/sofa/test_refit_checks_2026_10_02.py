"""Defects found by the 2026-10-02 refit pre-install checks.

1. fit_confidence rebuilt p from the raw sample_mean / sample_sd while
   run_confidence looks a leg up at its stored (SHEET) p_central; and the cache
   replay's stored p was a support-floored normal on the unscaled variance for
   every market, not SHEET's NB / scaled-variance estimator.
3. The tennis per-set games markets would have reached the coupon by the
   refit alone (new curves to 0.925), and holes inside a per-set market's
   range were filled from the tennis pool.
4. The half-match coherence check compared live-only half pools with
   replay-dominated full-match pools; and a half pool from one league stood
   as the global prior.
"""

from __future__ import annotations

import json
import math
import sqlite3
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.confidence import TENNIS_SET_GAMES, Calibration
from bet.sofa.engine import (
    calc_p_central_raw,
    nb_survival,
    p_empirical_centred_raw,
    predictive_sd,
    support_floor_for,
    uses_negative_binomial,
    winning_boundary,
)
from bet.sofa.fit_meta import OPERATOR_KEYS, carry_operator_keys
from scripts.sofa import calibrate_from_cache
from scripts.sofa.calibrate_from_cache import Played, _settle_sample

REPO = Path(__file__).resolve().parents[2]


# --- 1a: fit_confidence keys every row on its stored p_central ---------------


def _fit(tmp_path: Path, rows: list[tuple[Any, ...]]) -> dict[str, Any]:
    db = tmp_path / "sofa.db"
    con = sqlite3.connect(db)
    con.execute("""create table sofa_settled_row (market text, line real,
        direction text, sample_size int, sample_mean real, sample_sd real,
        actual_value real, p_central real, sport text, sofascore_event_id int)""")
    con.executemany("insert into sofa_settled_row values (?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    out = tmp_path / "cal.json"
    proc = subprocess.run(
        [sys.executable, "scripts/sofa/fit_confidence.py", "--db-path", str(db),
         "--out", str(out)],
        cwd=REPO, capture_output=True, text=True,
        env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, proc.stderr
    doc: dict[str, Any] = json.loads(out.read_text())
    return doc


def test_a_row_is_bucketed_on_its_stored_p_not_on_its_raw_sample(
    tmp_path: Path,
) -> None:
    # Raw sample: mean 20, sd 3, n 10, UNDER 28.5 - re-priced from the raw
    # sample this is ~0.99. SHEET's stored p (after the K_CENTRE shrink toward
    # a higher prior) is 0.72, and that is what run_confidence looks up.
    raw = predictive_sd(9.0, 20.0, 10)
    raw_p = calc_p_central_raw(
        20.0, raw, winning_boundary(28.5, "UNDER"), "UNDER",
        support_floor_for("throw_ins_total"),
    )
    assert raw_p > 0.95
    rows = [("throw_ins_total", 28.5, "UNDER", 10, 20.0, 3.0,
             25.0 if i % 4 else 30.0, 0.72, "football", i) for i in range(800)]
    doc = _fit(tmp_path, rows)
    curve = doc["by_market"]["throw_ins_total"]
    assert list(curve) == ["0.700-0.750"]
    assert curve["0.700-0.750"]["n"] == 800
    under = doc["by_market_direction"]["throw_ins_total|UNDER"]
    assert under["0.700-0.750"]["n"] == 800


def test_fit_confidence_opens_the_db_read_only(tmp_path: Path) -> None:
    rows = [("goals_total", 2.5, "UNDER", 10, 2.0, 1.2, 1.0, 0.8, "football", 1)]
    db = tmp_path / "sofa.db"
    # A read-only file and a mode=ro connection: the fit must need no write.
    con = sqlite3.connect(db)
    con.execute("""create table sofa_settled_row (market text, line real,
        direction text, sample_size int, sample_mean real, sample_sd real,
        actual_value real, p_central real, sport text, sofascore_event_id int)""")
    con.executemany("insert into sofa_settled_row values (?,?,?,?,?,?,?,?,?,?)",
                    rows * 300)
    con.commit()
    con.close()
    db.chmod(0o444)
    out = tmp_path / "cal.json"
    proc = subprocess.run(
        [sys.executable, "scripts/sofa/fit_confidence.py", "--db-path", str(db),
         "--out", str(out)],
        cwd=REPO, capture_output=True, text=True,
        env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, proc.stderr
    source = (REPO / "scripts/sofa/fit_confidence.py").read_text()
    assert "sqlite3.connect(args.db_path)" not in source


# --- 1b: the replay's stored p is SHEET's p -----------------------------------


def _played(sport: str = "football") -> Played:
    return Played(event_id=1, timestamp=0, home_id=1, away_id=2, sport=sport,
                  competition_id=7, values={})


def _sheet_p(market: str, sport: str, sample: list[float], prior: float,
             k: float, line: float, direction: str) -> float:
    """SHEET's estimator written out by hand (run_sheet.process_fixture):
    shrink, scale the variance by centre/mean for football counts, Poisson
    floor, (1 + 1/n), NB for NB metrics else the floored normal."""
    n = len(sample)
    mean = statistics.mean(sample)
    var = statistics.variance(sample)
    centre = n / (n + k) * mean + k / (n + k) * prior
    scale = centre / mean if sport == "football" else 1.0
    var_pred = max(var * scale, mean * scale) * (1 + 1 / n)
    boundary = winning_boundary(line, direction)
    if uses_negative_binomial(market):
        over = nb_survival(centre, var_pred, math.floor(boundary))
        return over if direction == "OVER" else 1 - over
    return calc_p_central_raw(centre, math.sqrt(var_pred), boundary,
                              direction, -0.5)


@pytest.mark.parametrize("market", ["goals_total", "corners_for", "shots_total"])
def test_the_replay_prices_a_rung_the_way_sheet_does(market: str) -> None:
    sample = [1.0, 3.0, 0.0, 2.0, 5.0, 1.0, 2.0, 4.0, 0.0, 3.0]
    if market == "shots_total":
        sample = [v * 6 + 10 for v in sample]
    prior = statistics.mean(sample) * 1.4  # the shrink moves the centre a lot
    baselines = {market: {"global": {"mean": prior, "n": 1000}}}
    constants = {"K_CENTRE": {"by_sport": {"football": 20.0}}}
    rows = _settle_sample(_played(), market, "", 2.0, sample, baselines, constants)
    assert rows
    for row in rows:
        want = _sheet_p(market, "football", sample, prior, 20.0, row.line,
                        row.direction)
        assert row.p_central == pytest.approx(want, abs=1e-6), (row.line, row.direction)


def test_the_replay_nb_p_is_not_the_old_unscaled_normal() -> None:
    """The test above bites: for an NB metric the old replay formula differs."""
    sample = [1.0, 3.0, 0.0, 2.0, 5.0, 1.0, 2.0, 4.0, 0.0, 3.0]
    prior = 3.0
    baselines = {"goals_total": {"global": {"mean": prior, "n": 1000}}}
    constants = {"K_CENTRE": {"by_sport": {"football": 20.0}}}
    rows = _settle_sample(_played(), "goals_total", "", 2.0, sample, baselines,
                          constants)
    n, mean = len(sample), statistics.mean(sample)
    centre = n / (n + 20) * mean + 20 / (n + 20) * prior
    old_sd = predictive_sd(statistics.variance(sample), mean, n)
    gaps = [
        abs(r.p_central - calc_p_central_raw(
            centre, old_sd, winning_boundary(r.line, r.direction),
            r.direction, -0.5))
        for r in rows
    ]
    assert max(gaps) > 0.02


def test_the_replay_prices_an_empirical_market_from_its_frequency() -> None:
    """games_won_for is an EMPIRICAL_FREQUENCY_METRIC in SHEET; the replay
    priced it with a normal."""
    sample = [6.0, 6.0, 2.0, 7.0, 6.0, 4.0, 6.0, 3.0, 6.0, 12.0]
    rows = _settle_sample(_played("tennis"), "games_won_for", "1", 6.0, sample,
                          {}, {})
    assert rows
    for row in rows:
        want = p_empirical_centred_raw(
            sample, winning_boundary(row.line, row.direction),
            row.direction, 0.0)
        assert row.p_central == pytest.approx(want, abs=1e-6)


def test_the_replay_imports_no_estimator_of_its_own() -> None:
    names = set(vars(calibrate_from_cache))
    assert "sheet_count_p_raw" in names and "sheet_predictive_sd" in names
    assert "calc_p_central_raw" not in names


# --- 3: tennis per-set games markets need an admission; no pool inside range --


def _cal_doc(tmp_path: Path, doc: dict[str, Any]) -> Path:
    path = tmp_path / "cal.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_a_curved_tennis_set_market_is_not_admitted_by_default(tmp_path: Path) -> None:
    curve = {"0.750-0.800": {"realised_lo95": 0.77, "n": 900}}
    cal = Calibration.load(_cal_doc(tmp_path, {"by_market": {
        m: curve for m in TENNIS_SET_GAMES}}))
    assert TENNIS_SET_GAMES == {"games_set1_total", "games_set2_total",
                                "games_won_set1_for", "games_won_set2_for"}
    for market in TENNIS_SET_GAMES:
        assert cal.tennis_set_market_not_admitted(market)
    for market in ("games_total", "games_won_for", "player_shots_for"):
        assert not cal.tennis_set_market_not_admitted(market)


def test_the_operator_admits_a_tennis_set_market_by_name(tmp_path: Path) -> None:
    cal = Calibration.load(_cal_doc(
        tmp_path, {"admitted_tennis_set_markets": ["games_set1_total"]}))
    assert not cal.tennis_set_market_not_admitted("games_set1_total")
    assert cal.tennis_set_market_not_admitted("games_won_set2_for")


def test_run_confidence_refuses_an_unadmitted_set_market() -> None:
    source = (REPO / "scripts/sofa/run_confidence.py").read_text()
    i = source.index('cal.tennis_set_market_not_admitted(row["market"])')
    assert 'refused["TENNIS_SET_MARKET_NOT_ADMITTED"]' in source[i:i + 200]
    # Before the curve lookup, like the player-prop admission.
    assert i < source.index("else cal.realised(")


def test_the_admission_list_survives_a_refit() -> None:
    assert "admitted_tennis_set_markets" in OPERATOR_KEYS
    new: dict[str, Any] = {"by_market": {}}
    carry_operator_keys(new, {"admitted_tennis_set_markets": ["games_set2_total"]})
    assert new["admitted_tennis_set_markets"] == ["games_set2_total"]


def _holed(market: str) -> Calibration:
    own = {"0.600-0.700": {"realised_lo95": 0.62, "n": 700},
           "0.750-0.800": {"realised_lo95": 0.76, "n": 500}}
    pool = {"0.700-0.750": {"realised_lo95": 0.72, "n": 9000},
            "0.750-0.800": {"realised_lo95": 0.77, "n": 9000}}
    return Calibration(pooled={}, by_market={market: own},
                       pooled_by_sport={"tennis": pool})


@pytest.mark.parametrize("market", ["games_set1_total", "games_won_set2_for",
                                    "aces_set1_for"])
def test_a_per_set_market_does_not_fill_a_hole_from_the_pool(market: str) -> None:
    cal = _holed(market)
    assert cal.realised(market, 0.72, "tennis") is None  # the hole
    assert cal.realised(market, 0.77, "tennis") == (0.76, f"market:{market}", 500)


def test_a_full_match_market_still_fills_a_hole_from_the_pool() -> None:
    cal = _holed("games_total")
    assert cal.realised("games_total", 0.72, "tennis") == (0.72, "pooled:tennis", 9000)


def test_a_per_set_market_without_a_curve_reads_no_pool() -> None:
    pool = {"0.700-0.750": {"realised_lo95": 0.72, "n": 9000}}
    cal = Calibration(
        pooled=pool,
        by_market={"games_won_for": {"0.800-0.825": {"realised_lo95": 0.78, "n": 500}}},
        pooled_by_sport={"tennis": pool},
    )
    assert cal.realised("games_set2_total", 0.72, "tennis") is None
    assert cal.realised("tiebreaks_total", 0.72, "tennis") is not None


# --- 4: half-match coherence over the same matches; one-league half pools -----


def _settled(rows: list[tuple[Any, ...]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE sofa_settled_row (
               competition_id INTEGER, market TEXT, subject TEXT,
               sofascore_event_id INTEGER, actual_value REAL,
               sport TEXT DEFAULT 'football')""")
    conn.executemany(
        "INSERT INTO sofa_settled_row (competition_id, market, subject,"
        " sofascore_event_id, actual_value) VALUES (?,?,?,?,?)", rows)
    return conn


def test_coherence_compares_halves_and_whole_over_the_same_matches() -> None:
    from scripts.sofa.fit_constants import (
        check_half_match_coherence,
        fit_baselines,
        same_match_baselines,
    )

    rows: list[tuple[Any, ...]] = []
    # 60 live matches with both halves and the whole: 1 + 1.2 = 2.2 goals.
    for e in range(60):
        rows += [(1 + e % 3, "goals_total", "", e, 2.2),
                 (1 + e % 3, "goals_1h_total", "", e, 1.0),
                 (1 + e % 3, "goals_2h_total", "", e, 1.2)]
    # 3000 replayed matches, whole match only, from a higher-scoring history.
    rows += [(4 + e % 5, "goals_total", "", 10_000 + e, 3.0) for e in range(3000)]
    conn = _settled(rows)
    # The shipped pools mix two populations: a false -26% "incoherence".
    assert any("goals_total" in f for f in check_half_match_coherence(
        fit_baselines(conn)))
    same = same_match_baselines(conn)
    assert same["goals_total"]["global"] == {"mean": 2.2, "n": 60}
    assert same["goals_1h_total"]["global"]["n"] == 60
    assert check_half_match_coherence(same) == []


def test_same_match_coherence_still_reports_a_real_split() -> None:
    from scripts.sofa.fit_constants import (
        check_half_match_coherence,
        same_match_baselines,
    )

    rows: list[tuple[Any, ...]] = []
    for e in range(60):
        for subj in ("A", "B"):
            # 2H takes 70% of the corners: a real artifact, same matches.
            rows += [(1 + e % 2, "corners_for", subj, e, 5.0),
                     (1 + e % 2, "corners_1h_for", subj, e, 1.5),
                     (1 + e % 2, "corners_2h_for", subj, e, 3.5)]
    findings = check_half_match_coherence(same_match_baselines(_settled(rows)))
    assert any("corners_for: second half is 70.0%" in f for f in findings)


def test_a_half_pool_from_one_competition_is_not_a_global_prior() -> None:
    from scripts.sofa.fit_constants import (
        MIN_BASELINE_OBSERVATIONS,
        baseline_totals,
        fit_baselines,
        leave_match_out_prior,
    )

    n = MIN_BASELINE_OBSERVATIONS
    rows = [(1, "fouls_1h_total", "", e, 11.0) for e in range(n)]
    rows += [(1, "fouls_total", "", e, 24.0) for e in range(n)]
    conn = _settled(rows)
    out = fit_baselines(conn)
    # The league entry stands; the one-league pool does not.
    assert out["fouls_1h_total"] == {"1": {"mean": 11.0, "n": n}}
    # A full-match pool from one league is unchanged.
    assert out["fouls_total"]["global"] == {"mean": 24.0, "n": n}
    totals = baseline_totals(conn)
    assert "fouls_1h_total" not in totals[1]
    # Another league's row reads no prior (fit_baselines wrote none for it);
    # the league's own row still reads its league.
    assert leave_match_out_prior(
        {"market": "fouls_1h_total", "competition_id": 2}, totals) is None
    rows += [(1, "fouls_1h_total", "", 100 + e, 11.0) for e in range(2)]
    assert leave_match_out_prior(
        {"market": "fouls_1h_total", "competition_id": 1, "own_sum": 11.0,
         "own_n": 1}, baseline_totals(_settled(rows))) == 11.0


def test_a_half_pool_from_two_competitions_is_global() -> None:
    from scripts.sofa.fit_constants import MIN_BASELINE_OBSERVATIONS, fit_baselines

    n = MIN_BASELINE_OBSERVATIONS
    rows = [(1 + e % 2, "fouls_1h_total", "", e, 11.0) for e in range(n)]
    assert fit_baselines(_settled(rows))["fouls_1h_total"]["global"]["n"] == n
