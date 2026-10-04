"""Every history reader follows comparability (2026-10-04).

The cache replay (the rows the confidence curves are fitted on), the player
model, the per-sport friendly tests, the PDF's marks for a WATCH or a context
flag, the audit's read coverage (C3) and the measurement scripts' own
arithmetic.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import player_model as pm
from bet.sofa.comparability import MatchKind
from scripts.sofa.build_coupon_pdf import context_label, watch_label
from scripts.sofa.calibrate_from_cache import Played, iter_rows
from scripts.sofa.find_friendly_competitions import (
    is_named_friendly,
    shaped_like_invitational,
)
from scripts.sofa.measure_sample_composition import (
    Past,
    Target,
    make_rules,
    poisson_over,
)

# --- the cache replay ----------------------------------------------------------


def _match(eid: int, ts: int, home: int, away: int, goals: tuple[float, float],
           comp: int = 17, kind: str = MatchKind.REGULAR) -> Played:
    return Played(eid, ts, home, away, "football", comp, {"goals": goals}, kind)


def _rows(played: list[Played], market: str) -> list[Any]:
    return [r for r in iter_rows(played, {}) if r.market == market]


def test_a_friendly_never_enters_a_replayed_history() -> None:
    played = [_match(i, 100 + i, 1, 50 + i, (1.0, 0.0)) for i in range(10)]
    played += [_match(90 + i, 200 + i, 1, 70 + i, (9.0, 0.0), comp=853,
                      kind=MatchKind.FRIENDLY) for i in range(5)]
    played.append(_match(999, 1_000, 1, 2, (1.0, 0.0)))
    rows = [r for r in _rows(played, "goals_for") if r.event_id == 999
            and r.subject == "1"]
    assert rows and {r.sample_mean for r in rows} == {1.0}


def test_a_replayed_goal_sample_comes_from_the_fixture_competition() -> None:
    played = [_match(i, 100 + i, 1, 50 + i, (1.0, 0.0)) for i in range(8)]
    # newer cup ties, five goals each, another competition
    played += [_match(90 + i, 200 + i, 1, 70 + i, (5.0, 0.0), comp=336,
                      kind=MatchKind.KNOCKOUT) for i in range(4)]
    played.append(_match(999, 1_000, 1, 2, (1.0, 0.0)))
    goals_for = [r for r in _rows(played, "goals_for") if r.event_id == 999
                 and r.subject == "1"]
    assert goals_for and {r.sample_mean for r in goals_for} == {1.0}


def test_corners_keep_the_newest_matches_whatever_the_competition() -> None:
    def corners(eid: int, ts: int, comp: int, kind: str, h: float) -> Played:
        return Played(eid, ts, 1, 50 + eid, "football", comp, {"corners": (h, 0.0)},
                      kind)

    played = [corners(i, 100 + i, 17, MatchKind.REGULAR, 4.0) for i in range(8)]
    played += [corners(90 + i, 200 + i, 336, MatchKind.KNOCKOUT, 8.0)
               for i in range(4)]
    played.append(Played(999, 1_000, 1, 2, "football", 17, {"corners": (4.0, 0.0)}))
    rows = [r for r in iter_rows(played, {}) if r.market == "corners_for"
            and r.event_id == 999 and r.subject == "1"]
    # the newest ten: four cup ties (8) and six league matches (4)
    assert rows and {round(r.sample_mean, 3) for r in rows} == {5.6}


# --- the player model ----------------------------------------------------------


def test_the_player_model_skips_a_preseason_game(tmp_path: Path) -> None:
    con = sqlite3.connect(tmp_path / "p.db")
    con.execute("CREATE TABLE sofa_listing_event (entity_id INTEGER, kind TEXT, "
                "event_id INTEGER, start_ts INTEGER, fetched_at TEXT)")
    con.execute("CREATE TABLE sofa_listed_event (event_id INTEGER PRIMARY KEY, "
                "sport TEXT, start_ts INTEGER, fetched_at TEXT, event_json TEXT)")
    for eid, ts, name in ((1, 100, "NHL"), (2, 200, "NHL Preseason"), (3, 300, "NHL")):
        con.execute("INSERT INTO sofa_listing_event VALUES (7, 'last', ?, ?, '')",
                    (eid, ts))
        con.execute("INSERT INTO sofa_listed_event VALUES (?, 'ice-hockey', ?, '', ?)",
                    (eid, ts, json.dumps({"id": eid, "tournament": {
                        "category": {"sport": {"slug": "ice-hockey"}},
                        "uniqueTournament": {"id": 1, "name": name}}})))
    # one listed game whose payload is not in the index is kept
    con.execute("INSERT INTO sofa_listing_event VALUES (7, 'last', 4, 400, '')")
    games = pm.listed_games(con, 7, 1_000, None)
    assert [g[0] for g in games] == [4, 3, 1]


# --- the PDF's marks -------------------------------------------------------------


def test_the_pdf_marks_a_kept_watch_and_a_context_flag() -> None:
    leg = {"reads": [{"verdict": "WATCH", "author": "verifier",
                      "reason": "model 9 pp over its sample <b>"}],
           "context_flags": ["MAKEUP_FIXTURE(postponed 2026-09-06, event 1)"]}
    assert "WATCH (verifier)" in watch_label(leg)
    assert "&lt;b&gt;" in watch_label(leg)  # escaped for the PDF markup
    assert "MAKEUP_FIXTURE" in context_label(leg)
    assert watch_label({}) == "" and context_label({}) == ""
    assert watch_label({"reads": [{"verdict": "KEEP", "author": "analyst",
                                   "reason": "x"}]}) == ""


# --- the friendly scanner --------------------------------------------------------


@pytest.mark.parametrize("name", [
    "Torneio de Verão Póvoa de Varzim", "Club Friendly Games", "MLS Preseason",
    "Memorial Vito Scafidi", "Trofeo de Verano"])
def test_the_scanner_proposes_friendly_names(name: str) -> None:
    assert is_named_friendly(name)


def test_the_scanner_shape_test() -> None:
    day = 86_400
    # one weekend, four clubs of three leagues
    invitational = {2026: [(0, 1, 2), (day, 3, 4), (2 * day, 1, 3)]}
    leagues = {1: 10, 2: 20, 3: 10, 4: 30}
    assert shaped_like_invitational(invitational, leagues, 21, 4)
    # a season-long competition
    league = {2026: [(0, 1, 2), (200 * day, 3, 4)]}
    assert not shaped_like_invitational(league, leagues, 21, 4)
    # one league's clubs only (a domestic cup final)
    assert not shaped_like_invitational(invitational, dict.fromkeys(leagues, 10),
                                        21, 4)


# --- the composition measurement's arithmetic -----------------------------------


def test_the_measured_rules_pick_what_they_say() -> None:
    def past(eid: int, comp: int, kind: MatchKind, ts: int) -> Past:
        return Past(ts, eid, comp, 1, kind, {"goals": (1.0, 0.0)})

    newest_first = [past(i, 336, MatchKind.KNOCKOUT, 100 - i) for i in range(3)]
    newest_first += [past(10 + i, 239, MatchKind.REGULAR, 90 - i) for i in range(6)]
    newest_first.insert(0, past(99, 853, MatchKind.FRIENDLY, 200))
    t = Target(1_000, 1, 239, 1, 1, 2, {"goals": (1.0, 0.0)})
    rules = make_rules({})
    assert [p.event_id for p in rules["R0_all"](newest_first, t, 10, 5)][:3] == [
        0, 1, 2]
    assert {p.event_id for p in rules["R2_same_comp"](newest_first, t, 10, 5)} == {
        10, 11, 12, 13, 14, 15}
    assert 99 not in {p.event_id for p in rules["R0_all"](newest_first, t, 10, 5)}


def test_poisson_over() -> None:
    assert poisson_over(2.5, 2.5) == pytest.approx(1 - 0.5438131, abs=1e-6)


# --- the audit's read coverage (C3) ----------------------------------------------


def _printed_doc() -> dict[str, Any]:
    single = {"sofascore_event_id": 5, "match": "A - B", "market": "goals_total",
              "subject": "", "line": 3.5, "direction": "UNDER", "confidence": 0.78,
              "offered_odds": 1.29, "overround": 0.08,
              "kickoff_utc": "2099-01-01T10:00:00Z"}
    return {"profile": "standard", "singles": [single], "pdf_max_singles": 30,
            "builders": [], "prints_builders": True}


def _write_reads(run: Path, reads: list[dict[str, Any]]) -> None:
    (run / "reads.json").write_text(json.dumps(reads))


def _read(verdict: str, author: str = "analyst") -> dict[str, Any]:
    return {"sofascore_event_id": 5, "market": None, "subject": None, "line": None,
            "direction": None, "verdict": verdict, "author": author, "reason": "r"}


def test_c3_names_an_unread_leg_and_a_missing_file(tmp_path: Path) -> None:
    from scripts.sofa.audit_variants import audit_reads

    doc = _printed_doc()
    assert "reads.json missing" in audit_reads(tmp_path, doc, "official")[0]
    _write_reads(tmp_path, [_read("KEEP", author="verifier")])
    assert any("without an analyst's read" in f
               for f in audit_reads(tmp_path, doc, "official"))
    _write_reads(tmp_path, [_read("KEEP")])
    assert audit_reads(tmp_path, doc, "official") == []
    _write_reads(tmp_path, [_read("KEEP"), _read("WATCH", author="verifier")])
    assert any("despite WATCHED" in f for f in audit_reads(tmp_path, doc, "official"))


# --- the replay clock --------------------------------------------------------------


def test_sofa_now_freezes_the_clock_and_says_so(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from datetime import UTC, datetime

    from bet.sofa import timeutil

    monkeypatch.delenv("SOFA_NOW", raising=False)
    assert abs((timeutil.now() - datetime.now(UTC)).total_seconds()) < 5
    monkeypatch.setattr(timeutil, "_warned", False)
    monkeypatch.setenv("SOFA_NOW", "2026-10-04T06:45:00Z")
    assert timeutil.now() == datetime(2026, 10, 4, 6, 45, tzinfo=UTC)
    assert "frozen" in capsys.readouterr().err


def test_a_frozen_clock_is_refused_on_the_real_runs_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Review 2026-10-04: only run_pipeline refused SOFA_NOW; CONFIDENCE, the
    # PDF and WSZYSTKIE would time their kickoff gates on a frozen clock in
    # the real day.
    from bet.sofa import timeutil

    monkeypatch.delenv("SOFA_NOW", raising=False)
    assert timeutil.frozen_clock_refusal(timeutil.REAL_RUNS_DIR) is None
    monkeypatch.setenv("SOFA_NOW", "2026-10-04T06:45:00Z")
    assert "REFUSED" in (timeutil.frozen_clock_refusal(timeutil.REAL_RUNS_DIR) or "")
    assert timeutil.frozen_clock_refusal(tmp_path) is None  # a replay's scratch
    for script in ("run_confidence", "build_coupon_pdf", "run_multi_coupon"):
        src = (Path(timeutil.__file__).parents[3] / "scripts" / "sofa"
               / f"{script}.py").read_text(encoding="utf-8")
        assert "frozen_clock_refusal(" in src, script
