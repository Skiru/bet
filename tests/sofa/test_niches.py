"""The niche scanner, and the ways a scan like it manufactures a niche.

The operator asked for a tool that searches for league patterns Superbet has
not priced - and that can say "none yet" without flinching. Each test below
plants a known truth in a synthetic table and checks the scanner reports it,
or refuses to report what is not there:

  * a real niche (+8 pp over the price, every day) is found out of sample;
  * a fluke (+15 pp on the first days, at the price after) is not a candidate;
  * pure noise over many leagues yields nothing after Benjamini-Hochberg;
  * nested lines and both sides of one line are one match, not six rows;
  * the margin comes from the OVER/UNDER pair of the same line;
  * day D's own results never reach day D's selection (leakage);
  * nothing on the network is touched, and the database is opened read-only.
"""

from __future__ import annotations

import json
import random
import socket
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import niches
from bet.sofa.db import migrate
from bet.sofa.niches import (
    SettledRow,
    benjamini_hochberg,
    dedupe,
    pair_margins,
    scan_all,
    walk_forward,
)

MARGIN = 0.06


def _days(n: int, start: date = date(2026, 9, 10)) -> list[str]:
    return [(start + timedelta(days=i)).isoformat() for i in range(n)]


def _match_rows(day: str, event: int, comp: int, p_over: float, p_true: float,
                rng: random.Random, market: str = "corners_total",
                line: float = 9.5, subject: str = "") -> list[SettledRow]:
    """Both sides of one line. Odds carry MARGIN proportionally; market_p is
    the devigged price; the outcome is drawn from p_true."""
    over_won = rng.random() < p_true
    rows = []
    for direction, p, won in (("OVER", p_over, over_won),
                              ("UNDER", 1.0 - p_over, not over_won)):
        rows.append(SettledRow(
            day=day, event=event, sport="football", competition=comp, market=market,
            subject=subject, line=line, direction=direction, market_p=p,
            odds=round(1.0 / (p * (1.0 + MARGIN)), 4), won=won,
        ))
    return rows


def _table(plan: dict[int, Any], days: list[str], per_day: int,
           seed: int) -> list[SettledRow]:
    """plan: competition -> function(day_index) -> OVER bias over the price."""
    rng = random.Random(seed)
    rows: list[SettledRow] = []
    ev = 1
    for i, day in enumerate(days):
        for comp, bias_of in plan.items():
            for _ in range(per_day):
                p = 0.45 + 0.1 * rng.random()
                rows.extend(_match_rows(day, ev, comp, p, p + bias_of(i), rng))
                ev += 1
    return rows


def _by_comp(r: SettledRow) -> str:
    return f"{r.sport}:{r.competition}"


GROUP = {"competition": (_by_comp, False)}


# ---- 1. a real niche is found -----------------------------------------------


def test_a_planted_niche_is_found_out_of_sample() -> None:
    days = _days(12)
    plan: dict[int, Any] = {c: (lambda i: 0.0) for c in range(1, 6)}
    plan[99] = lambda i: 0.08
    rows = _table(plan, days, per_day=120, seed=11)

    res = scan_all(rows, GROUP)

    cands = res["candidates"]
    assert res["verdict"] == "NISZA_ZNALEZIONA"
    assert [(c["group"], c["market"], c["direction"]) for c in cands] == [
        ("football:99", "corners_total", "OVER")]
    c = cands[0]
    assert c["oos"]["roi"] > 0
    assert c["oos"]["roi_ci95"] is not None  # the lower bound is reported
    # the pair margin the cell must beat is the one planted
    assert c["pair_margin"] == pytest.approx(MARGIN, abs=1e-3)
    # the selector beats the no-league baseline out of sample
    head = res["scans"][0]["headline"]
    assert head["selector"]["roi"] > head["baseline"]["roi"]


# ---- 2. a fluke is not ----------------------------------------------------------


def test_a_fluke_that_fades_is_never_a_candidate() -> None:
    """+15 pp on the first four days, the price afterwards. In-sample the
    league looks like a niche; out of sample it is the price minus the margin."""
    days = _days(12)
    plan: dict[int, Any] = {c: (lambda i: 0.0) for c in range(1, 6)}
    plan[77] = lambda i: 0.15 if i < 4 else 0.0
    rows = _table(plan, days, per_day=60, seed=5)

    res = scan_all(rows, GROUP)

    assert res["candidates"] == []
    assert res["verdict"] == "BRAK_NISZY"
    # in-sample it still looks like one - which is why it is watched, not proven
    watched = {(c["group"], c["direction"]): c for c in res["scans"][0]["watch"]}
    fluke = watched[("football:77", "OVER")]
    assert fluke["raw_ev"] > 0
    assert fluke["oos"]["roi"] is None or fluke["oos_p"] > 0.01


# ---- 3. noise stays noise ------------------------------------------------------


def test_noise_over_many_leagues_yields_no_candidate() -> None:
    days = _days(12)
    plan: dict[int, Any] = {c: (lambda i: 0.0) for c in range(1, 41)}
    rows = _table(plan, days, per_day=10, seed=2026)

    res = scan_all(rows, GROUP)

    assert res["bh"]["m"] >= 40  # the family really was large
    assert res["candidates"] == []
    assert res["verdict"] == "BRAK_NISZY"


def test_benjamini_hochberg_step_up() -> None:
    p = {"a": 0.001, "b": 0.02, "c": 0.03, "d": 0.5}
    # thresholds q*i/m at q=0.1, m=4: .025 .05 .075 .1 -> a, b, c pass
    assert benjamini_hochberg(p, q=0.10) == {"a", "b", "c"}
    assert benjamini_hochberg({"a": 0.2, "b": 0.3}, q=0.10) == set()


# ---- 4. dedupe ------------------------------------------------------------------


def test_nested_lines_and_both_sides_are_one_match() -> None:
    rng = random.Random(1)
    rows: list[SettledRow] = []
    for line, p in ((8.5, 0.70), (9.5, 0.52), (10.5, 0.33)):
        rows += _match_rows("2026-09-10", 1, 5, p, p, rng, line=line)
    for subject in ("home", "away"):
        for line, p in ((3.5, 0.62), (4.5, 0.47)):
            rows += _match_rows("2026-09-10", 1, 5, p, p, rng, market="corners_for",
                                line=line, subject=subject)
    assert len(rows) == 14

    units = dedupe(rows, _by_comp)

    total = [u for u in units if u.market == "corners_total"]
    assert sorted((u.direction, u.line) for u in total) == [
        ("OVER", 9.5), ("UNDER", 9.5)]
    per_team = [u for u in units if u.market == "corners_for"]
    assert sorted((u.subject, u.direction, u.line) for u in per_team) == [
        ("away", "OVER", 4.5), ("away", "UNDER", 4.5),
        ("home", "OVER", 4.5), ("home", "UNDER", 4.5)]
    cells, _ = niches.accumulate(units)
    # both teams' OVER rows: two units, one match
    acc = cells[("football:5", "corners_for", "OVER", "")]
    assert (acc.units, acc.matches) == (2, 1)


def test_the_rung_tie_goes_to_the_lower_line() -> None:
    rng = random.Random(3)
    rows = (_match_rows("2026-09-10", 1, 5, 0.45, 0.45, rng, line=9.5)
            + _match_rows("2026-09-10", 1, 5, 0.55, 0.55, rng, line=8.5))
    units = dedupe(rows, _by_comp)
    assert {u.line for u in units} == {8.5}


# ---- 5. margin from the pair -----------------------------------------------------


def test_margin_is_taken_from_the_over_under_pair() -> None:
    base = dict(day="2026-09-10", event=1, sport="football", competition=5,
                market="corners_total", subject="", line=9.5, won=True)
    rows = [SettledRow(direction="OVER", market_p=0.53, odds=1.80, **base),
            SettledRow(direction="UNDER", market_p=0.47, odds=2.00, **base),
            # one side only: no margin can be taken from it
            SettledRow(direction="OVER", market_p=0.4, odds=2.3,
                       **{**base, "line": 10.5})]
    m = pair_margins(rows)
    assert m == {(1, "corners_total", "", 9.5): pytest.approx(1 / 1.8 + 1 / 2.0 - 1)}


def test_the_two_hurdles_add_to_the_pair_margin_under_power_devig() -> None:
    """The per-side hurdle 1/odds - market_p is the cell's share of its margin;
    for a power devig the two shares add to the pair's margin exactly."""
    from bet.sofa.engine import devig_many
    o_over, o_under = 1.72, 2.05
    fair = devig_many([1 / o_over, 1 / o_under])
    assert fair is not None
    hurdles = (1 / o_over - fair[0]) + (1 / o_under - fair[1])
    assert hurdles == pytest.approx(1 / o_over + 1 / o_under - 1)


def test_a_stale_market_p_is_repriced_from_the_printed_pair() -> None:
    """market_p from another offer snapshot would measure the bias against a
    price nobody bet. It is re-derived from the pair's own printed odds."""
    from bet.sofa.engine import devig_many
    base = dict(day="2026-09-10", event=1, sport="football", competition=5,
                market="corners_total", subject="", line=9.5, won=True)
    rows = [SettledRow(direction="OVER", market_p=0.40, odds=1.80, **base),
            SettledRow(direction="UNDER", market_p=0.60, odds=2.00, **base),
            SettledRow(direction="OVER", market_p=0.33, odds=2.9,
                       **{**base, "line": 10.5})]
    out, moved = niches.reprice_from_pairs(rows)
    fair = devig_many([1 / 1.8, 1 / 2.0])
    assert fair is not None
    assert moved == 2
    assert [r.market_p for r in out[:2]] == pytest.approx(fair)
    assert out[2].market_p == 0.33  # one-sided: kept as stored


# ---- leakage -------------------------------------------------------------------


def test_day_d_results_never_reach_day_d_selection() -> None:
    """Flip every outcome of one day: that day's selection and K must not move,
    only the days after it may."""
    days = _days(8)
    plan: dict[int, Any] = {c: (lambda i: 0.0) for c in range(1, 4)}
    plan[9] = lambda i: 0.10
    rows = _table(plan, days, per_day=40, seed=8)
    target = days[5]
    flipped = [SettledRow(**{**r.__dict__, "won": not r.won}) if r.day == target else r
               for r in rows]

    a = walk_forward(dedupe(rows, _by_comp), "competition")
    b = walk_forward(dedupe(flipped, _by_comp), "competition")

    assert a.selections[target] == b.selections[target]
    assert a.k_by_day[target] == b.k_by_day[target]
    for d in days[:6]:
        assert a.selections.get(d) == b.selections.get(d)


def test_first_scored_day_is_not_bet() -> None:
    """K is fitted on earlier scored days only, so the first one has no K."""
    days = _days(5)
    rows = _table({1: lambda i: 0.0}, days, per_day=30, seed=1)
    wf = walk_forward(dedupe(rows, _by_comp), "competition", min_train_days=2)
    assert wf.days_scored[0] == days[2]
    assert days[2] not in wf.days_bet
    assert wf.days_bet[0] == days[3]


def test_a_cell_needs_its_training_matches() -> None:
    days = _days(6)
    rows = _table({1: lambda i: 0.3}, days, per_day=3, seed=4)
    wf = walk_forward(dedupe(rows, _by_comp), "competition", min_matches=20)
    # 3 matches a day: the cell reaches 20 only on the 8th day, never here
    assert wf.cells_scanned == set()
    assert wf.selector_bets == []


# ---- 6. no network, read-only database, CLI ------------------------------------


def _write_db(path: Path, rows: list[SettledRow], cache: bool = True) -> None:
    migrate(str(path))
    conn = sqlite3.connect(path)
    for r in rows:
        conn.execute(
            "INSERT INTO sofa_settled_row (run_date, sofascore_event_id, sport,"
            " competition_id, market, subject, line, direction, sample_size,"
            " sample_mean, sample_sd, p_central, p_bar, market_p, actual_value,"
            " outcome, settled_at, offered_odds)"
            " VALUES (?,?,?,?,?,?,?,?,10,9,2,?,?,?,?,?,?,?)",
            (r.day, r.event, r.sport, r.competition, r.market, r.subject, r.line,
             r.direction, r.market_p, r.market_p, r.market_p,
             10.0 if r.won == (r.direction == "OVER") else 8.0,
             "WIN" if r.won else "LOSS", "2026-09-29T00:00:00+00:00", r.odds))
    if cache:  # unpriced rows, as the cache replay writes them
        for ev in range(10_000, 10_030):
            conn.execute(
                "INSERT INTO sofa_settled_row (run_date, sofascore_event_id, sport,"
                " competition_id, market, subject, line, direction, sample_size,"
                " sample_mean, sample_sd, p_central, p_bar, actual_value, outcome,"
                " settled_at) VALUES ('cache-calibration',?, 'football', 99,"
                " 'corners_total', '', 9.5, 'OVER', 10, 9, 2, .5, .5, ?, 'WIN', 'x')",
                (ev, 8.0 + ev % 5))
    conn.commit()
    conn.close()


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: Any, **k: Any) -> Any:
        raise AssertionError("the niche scanner touched the network")

    from bet.sofa import bridge_transport, client, offer, superbet
    monkeypatch.setattr(client.SofascoreClient, "__init__", boom)
    monkeypatch.setattr(client.CurlCffiTransport, "__init__", boom)
    monkeypatch.setattr(bridge_transport.BrowserBridgeTransport, "__init__", boom)
    monkeypatch.setattr(superbet.SuperbetClient, "__init__", boom)
    monkeypatch.setattr(offer.OfferFetcher, "__init__", boom)
    # sockets: tests/sofa/conftest.py's autouse guard already replaces them;
    # assert it is in force rather than trusting it
    with pytest.raises(RuntimeError):
        socket.socket()


def test_cli_runs_offline_and_reads_only(tmp_path: Path, no_network: None) -> None:
    from scripts.sofa import audit_niches

    days = _days(10)
    plan: dict[int, Any] = {c: (lambda i: 0.0) for c in range(1, 4)}
    plan[99] = lambda i: 0.08
    rows = _table(plan, days, per_day=40, seed=3)
    db = tmp_path / "sofa.db"
    _write_db(db, rows)
    runs = tmp_path / "runs"
    for d in days:
        (runs / d).mkdir(parents=True)
        fx = [{"sofascore_event_id": e, "sport": "football", "competition_id": c,
               "competition_name": f"Liga {c}", "category_name": f"Kraj {c % 2}"}
              for e, c in {(r.event, r.competition) for r in rows if r.day == d}]
        (runs / d / "02_fixtures.json").write_text(json.dumps(fx))
    before = db.read_bytes()
    out_json = tmp_path / "sofa_nisze_x.json"
    out_md = tmp_path / "n.md"

    code = audit_niches.main(["--from", days[0], "--to", days[-1], "--db-path", str(db),
                              "--runs-dir", str(runs), "--json", str(out_json),
                              "--out", str(out_md)])

    assert code == 0
    assert db.read_bytes() == before
    art = json.loads(out_json.read_text())
    assert art["stage"] == "NICHES"
    assert art["data"]["rows_loaded"] == len(rows)  # cache rows never loaded
    assert {c["group"] for c in art["candidates"]} == {"football:99"}
    # the planted league is described from its unpriced cache rows - 30 matches,
    # a mean of the settled quantity, and no price anywhere in the entry
    desc = {c["competition_id"]: c for c in art["cache_describe"]}
    assert desc[99]["matches"] == 30
    assert desc[99]["mean"] == pytest.approx(10.0)
    assert not any("odds" in k or "market_p" in k for k in desc[99])
    md = out_md.read_text()
    assert md.startswith("# Skaner nisz")
    assert "Decyzja o stawce należy do operatora" in md


def test_connect_ro_refuses_writes(tmp_path: Path) -> None:
    from scripts.sofa.audit_niches import connect_ro
    db = tmp_path / "sofa.db"
    _write_db(db, [], cache=False)
    conn = connect_ro(str(db))
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM sofa_settled_row")
    conn.close()


def test_cli_fails_cleanly_without_rows(tmp_path: Path, no_network: None,
                                        capsys: pytest.CaptureFixture[str]) -> None:
    from scripts.sofa import audit_niches
    db = tmp_path / "sofa.db"
    _write_db(db, [], cache=True)
    code = audit_niches.main(["--from", "2026-09-01", "--to", "2026-09-02",
                              "--db-path", str(db), "--runs-dir", str(tmp_path),
                              "--json", str(tmp_path / "a.json"),
                              "--out", str(tmp_path / "a.md")])
    assert code == 2
    assert '"status": "FAILED"' in capsys.readouterr().out


# ---- 7. audit_settlement section 7h ----------------------------------------------


def test_section_7h_says_brak_danych_without_an_artifact(tmp_path: Path) -> None:
    from scripts.sofa.audit_settlement import section_7h
    lines = section_7h(tmp_path, "2026-09-28")
    assert lines[0].startswith("## 7h.")
    assert any("Brak danych" in x for x in lines)


def test_section_7h_renders_the_latest_artifact_up_to_the_date(tmp_path: Path) -> None:
    from scripts.sofa.audit_settlement import section_7h

    days = _days(8)
    rows = _table({1: lambda i: 0.0, 2: lambda i: 0.0}, days, per_day=20, seed=9)
    res = scan_all(rows, GROUP)
    for to, verdict in (("2026-09-20", "BRAK_NISZY"),
                        ("2026-09-27", "NISZA_ZNALEZIONA"),
                        ("2026-09-30", "BRAK_NISZY")):
        art = {"from": "2026-09-10", "to": to, **res, "verdict": verdict}
        (tmp_path / f"sofa_nisze_{to}.json").write_text(json.dumps(art))

    text = "\n".join(section_7h(tmp_path, "2026-09-28"))

    # the 09-30 artifact is after the report's date and must not be read
    assert "2026-09-10 … 2026-09-27" in text
    assert "NISZA ZNALEZIONA" in text
    assert "nie łączyć z 7c." in text
