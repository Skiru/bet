"""Display-only stakes flags for national football groups and tennis Finals
groups (operator 2026-11-18; bet.sofa.stakes_groups, bet.sofa.stakes_state,
epochs.STAKES_GROUPS_FROM_UTC): the frozen state module carried unchanged,
the Nations League check before round 6, the scope / staleness guards, the
tennis RR flag, the switch, and where the flags show (coupon leg, PDF, HTML
row, dossier, read set). Offline."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa import epochs, stakes, stakes_groups, stakes_state
from bet.sofa.dossier import stakes_block
from scripts.sofa.build_coupon import assemble
from scripts.sofa.build_coupon_pdf import stakes_label
from scripts.sofa.read_set import FIELDS

REPO = Path(__file__).resolve().parents[2]
FROZEN = REPO / "docs/sofa/evidence/stakes_football_2026-11-18/stakes_state.py"
FROZEN_SHA = "99e81fe70f6ed6855afb6264e20c8cdf0798126463ca5cba69c958233bee1949"

UNL, SEASON = 10783, 89945
R6 = 1794944700  # 2026-11-17 19:45Z, the Nations League's round 6

# UEFA Nations League 2026/27 as cached (event id, start, home, away, score;
# None = not played before round 6) - the three groups of the operator's check.
GROUPS: dict[int, tuple[str, list[tuple[Any, ...]]]] = {
    64388: ("UEFA Nations League, League A, Gr. 4", [
        (15534097, 1790275500, 4704, "Portugal", 4702, "Wales", 1, 0),
        (15534100, 1790275500, 4475, "Norway", 4476, "Denmark", 3, 2),
        (15534101, 1790524800, 4476, "Denmark", 4702, "Wales", 2, 0),
        (15534096, 1790534700, 4475, "Norway", 4704, "Portugal", 1, 2),
        (15534094, 1790880300, 4476, "Denmark", 4704, "Portugal", 2, 4),
        (15534104, 1790880300, 4702, "Wales", 4475, "Norway", 2, 1),
        (15534095, 1791139500, 4704, "Portugal", 4475, "Norway", 2, 1),
        (15534102, 1791139500, 4702, "Wales", 4476, "Denmark", 0, 1),
        (15534103, 1794675600, 4475, "Norway", 4702, "Wales", 3, 1),
        (15534093, 1794685500, 4704, "Portugal", 4476, "Denmark", 1, 4),
        (15534098, R6, 4702, "Wales", 4704, "Portugal", None, None),
        (15534099, R6, 4476, "Denmark", 4475, "Norway", None, None),
    ]),
    64391: ("UEFA Nations League, League B, Gr. 3", [
        (15534155, 1790275500, 4718, "Austria", 4480, "Israel", 3, 1),
        (15534165, 1790275500, 154426, "Kosovo", 4693, "Ireland", 1, 0),
        (15534162, 1790524800, 4718, "Austria", 154426, "Kosovo", 3, 1),
        (15534156, 1790534700, 4480, "Israel", 4693, "Ireland", 0, 3),
        (15534158, 1790880300, 4480, "Israel", 154426, "Kosovo", 0, 0),
        (15534161, 1790880300, 4693, "Ireland", 4718, "Austria", 2, 2),
        (15534163, 1791129600, 154426, "Kosovo", 4718, "Austria", 1, 1),
        (15534157, 1791139500, 4693, "Ireland", 4480, "Israel", 1, 1),
        (15534159, 1794664800, 154426, "Kosovo", 4480, "Israel", 0, 0),
        (15534160, 1794685500, 4718, "Austria", 4693, "Ireland", 1, 0),
        (15534154, R6, 4480, "Israel", 4718, "Austria", None, None),
        (15534164, R6, 4693, "Ireland", 154426, "Kosovo", None, None),
    ]),
    64393: ("UEFA Nations League, League B, Gr. 4", [
        (15534167, 1790361900, 4703, "Poland", 4479, "Bosnia & Herzegovina", 0, 0),
        (15534178, 1790361900, 4688, "Sweden", 4477, "Romania", 2, 1),
        (15534172, 1790621100, 4688, "Sweden", 4703, "Poland", 3, 1),
        (15534174, 1790621100, 4477, "Romania", 4479, "Bosnia & Herzegovina", 2, 4),
        (15534169, 1790966700, 4703, "Poland", 4477, "Romania", 6, 0),
        (15534175, 1790966700, 4479, "Bosnia & Herzegovina", 4688, "Sweden", 1, 1),
        (15534168, 1791225900, 4479, "Bosnia & Herzegovina", 4703, "Poland", 1, 0),
        (15534177, 1791225900, 4477, "Romania", 4688, "Sweden", 0, 1),
        (15534170, 1794685500, 4477, "Romania", 4703, "Poland", 2, 1),
        (15534176, 1794685500, 4688, "Sweden", 4479, "Bosnia & Herzegovina", 3, 2),
        (15534171, R6, 4703, "Poland", 4688, "Sweden", None, None),
        (15534173, R6, 4479, "Bosnia & Herzegovina", 4477, "Romania", None, None),
    ]),
}


def payload(row: tuple[Any, ...], tid: int, stage: str, ut: int = UNL,
            season: int = SEASON, **extra: Any) -> dict[str, Any]:
    eid, ts, hid, hn, aid, an, hg, ag = row
    done = hg is not None
    event: dict[str, Any] = {
        "id": eid, "startTimestamp": ts,
        "tournament": {"id": tid, "name": stage, "uniqueTournament": {"id": ut}},
        "season": {"id": season},
        "roundInfo": {"round": 1},
        "status": {"type": "finished" if done else "notstarted"},
        "homeTeam": {"id": hid, "name": hn, "gender": "M", "national": True},
        "awayTeam": {"id": aid, "name": an, "gender": "M", "national": True},
    }
    if done:
        event["homeScore"] = {"current": hg, "normaltime": hg}
        event["awayScore"] = {"current": ag, "normaltime": ag}
        event["winnerCode"] = 1 if hg > ag else 2 if ag > hg else 3
    event.update(extra)
    return event


def group(tid: int) -> list[dict[str, Any]]:
    stage, rows = GROUPS[tid]
    return [payload(r, tid, stage) for r in rows]


def fixture(tid: int, eid: int) -> dict[str, Any]:
    return next(e for e in group(tid) if e["id"] == eid)


# ------------------------------------------------------- the frozen module


def _frozen() -> Any:
    spec = importlib.util.spec_from_file_location("frozen_stakes_state", FROZEN)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_frozen_module_is_the_pre_registered_file() -> None:
    assert hashlib.sha256(FROZEN.read_bytes()).hexdigest() == FROZEN_SHA


def test_ported_state_logic_agrees_with_the_frozen_module() -> None:
    frozen = _frozen()
    rng = random.Random(20261118)
    for _ in range(400):
        n = rng.choice([3, 4, 4, 5, 6])
        teams = list(range(1, n + 1))
        pts = {t: rng.randint(0, 15) for t in teams}
        pairs = [(a, b) for a in teams for b in teams if a < b]
        remaining = rng.sample(pairs, k=min(len(pairs), rng.randint(1, 9)))
        match = remaining.pop()
        bounds = sorted(rng.sample(range(1, n), k=rng.randint(1, n - 1)))
        played = [(a, b, rng.randint(0, 3), rng.randint(0, 3))
                  for a, b in rng.sample(pairs, k=len(pairs) // 2)]
        for side in match:
            for use_h2h in (False, True):
                ours = stakes_state.final_state(
                    pts, remaining, match, side, bounds,
                    stakes_state.H2H(played, 1) if use_h2h else None)
                theirs = frozen.final_state(
                    pts, remaining, match, side, bounds,
                    frozen.H2H(played, 1) if use_h2h else None)
                assert ours == theirs


# ----------------------------------------------- national football groups


def test_nations_league_before_round_six() -> None:
    """The operator's check (sanity_unl.txt): Wales DEAD, Norway MUST_WIN,
    Austria SECURED, Sweden SECURED, Poland ALIVE."""
    got = {
        eid: stakes_groups.national_flags(fixture(tid, eid), group(tid))
        for tid, eid in ((64388, 15534098), (64388, 15534099), (64391, 15534154),
                         (64393, 15534171), (64393, 15534173))
    }
    assert got[15534098] == ["STAKES_NATIONAL_DEAD(Wales)",
                             "STAKES_NATIONAL_ALIVE(Portugal)"]
    assert got[15534099] == ["STAKES_NATIONAL_MUST_WIN(Denmark)",
                             "STAKES_NATIONAL_MUST_WIN(Norway; tb)"]
    assert got[15534154] == ["STAKES_NATIONAL_MUST_WIN(Israel)",
                             "STAKES_NATIONAL_SECURED(Austria)"]
    assert got[15534171] == ["STAKES_NATIONAL_ALIVE(Poland)",
                             "STAKES_NATIONAL_SECURED(Sweden)"]
    assert got[15534173] == ["STAKES_NATIONAL_SECURED(Bosnia & Herzegovina)",
                             "STAKES_NATIONAL_MUST_WIN(Romania)"]


def test_an_unsettled_earlier_game_gives_no_flag() -> None:
    events = group(64393)
    stale = next(e for e in events if e["id"] == 15534170)  # Romania - Poland
    stale["status"] = {"type": "notstarted"}
    del stale["homeScore"], stale["awayScore"]
    me = fixture(64393, 15534171)
    assert stakes_groups.national_states(me, events) == "STALE"
    assert stakes_groups.national_flags(me, events) == []
    # a finished copy of the same game beside the stale one wins
    assert stakes_groups.national_flags(me, [*events, *group(64393)])


def test_scope_guards() -> None:
    events = group(64393)
    me = fixture(64393, 15534171)
    women = {**me, "homeTeam": {**me["homeTeam"], "gender": "F"}}
    assert stakes_groups.national_states(women, events) == "NOT_IN_SCOPE"
    knockout = {**me, "roundInfo": {"round": 1, "name": "Final", "cupRoundType": 1}}
    assert stakes_groups.national_states(knockout, events) == "NOT_GROUP_ROUND"
    other = {**me, "tournament": {**me["tournament"], "uniqueTournament": {"id": 7}}}
    assert stakes_groups.national_states(other, events) == "NOT_IN_SCOPE"
    # a qualifier whose last rounds are not listed yet: > 25% inferred
    thin = [e for e in events if e["startTimestamp"] < 1791000000 or e["id"] == me["id"]]
    assert stakes_groups.national_states(me, thin) == "INCOMPLETE_GROUP"


def test_boundaries_are_section_4_2() -> None:
    assert stakes_groups.national_bounds("unl", 4, "League A, Gr. 1") == [1, 2, 3]
    assert stakes_groups.national_bounds("unl", 3, "League D, Gr. 1") == [1]
    assert stakes_groups.national_bounds("top12", 6, "") == [1, 2]
    assert stakes_groups.national_bounds("top2", 4, "") == [2]
    assert stakes_groups.national_bounds("first_last", 4, "") == [1, 3]
    assert stakes_groups.national_bounds("conmebol", 10, "") == [6, 7]


# ------------------------------------------------------------------ tennis


def _rr(eid: int, ts: int, h: tuple[int, str], a: tuple[int, str],
        winner: int | None, stage: str = "WTA Tour Finals, Group A",
        status: str | None = None) -> dict[str, Any]:
    return {
        "id": eid, "startTimestamp": ts,
        "tournament": {"id": 207943, "name": stage, "isGroup": True,
                       "uniqueTournament": {"id": 2}},
        "season": {"id": 1},
        "status": {"type": status or ("finished" if winner else "notstarted")},
        "homeTeam": {"id": h[0], "name": h[1]},
        "awayTeam": {"id": a[0], "name": a[1]},
        **({"winnerCode": winner} if winner else {}),
    }


KOS, GAU, PEG, NOS = (1, "Kostyuk"), (2, "Gauff"), (3, "Pegula"), (4, "Noskova")
RR_GAMES = [
    _rr(10, 100, KOS, NOS, 2), _rr(11, 110, GAU, PEG, 1),
    _rr(12, 200, KOS, PEG, 2), _rr(13, 210, GAU, NOS, 2),
]


def _of(games: list[dict[str, Any]]) -> Any:
    return lambda side: [g for g in games
                         if side in (g["homeTeam"]["id"], g["awayTeam"]["id"])]


def test_tennis_finals_group_decided_sides() -> None:
    me = _rr(20, 300, KOS, GAU, None)
    assert stakes_groups.rr_flags(me, _of(RR_GAMES)) == ["RR_DECIDED_SIDE(Kostyuk 0-2)"]
    me2 = _rr(21, 300, PEG, NOS, None)
    assert stakes_groups.rr_flags(me2, _of(RR_GAMES)) == ["RR_DECIDED_SIDE(Noskova 2-0)"]
    # a group game of the side started and not settled in the cache: none
    stale = [*RR_GAMES[:2], _rr(12, 200, KOS, PEG, None), RR_GAMES[3]]
    assert stakes_groups.rr_flags(me, _of(stale)) == []
    # doubles or not a group / not Finals: none
    dbl = _rr(22, 300, KOS, GAU, None, stage="WTA Tour Finals, Doubles, Group A")
    assert stakes_groups.rr_flags(dbl, _of(RR_GAMES)) == []
    plain = {**me, "tournament": {**me["tournament"], "isGroup": False}}
    assert stakes_groups.rr_flags(plain, _of(RR_GAMES)) == []


# --------------------------------------------------------- the cache reader


def _db(events: list[dict[str, Any]]) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.executescript("""
        CREATE TABLE sofa_listed_event (event_id INTEGER PRIMARY KEY, sport TEXT,
            start_ts INTEGER, fetched_at TEXT NOT NULL, event_json TEXT NOT NULL);
        CREATE TABLE sofa_listing_event (entity_id INTEGER NOT NULL, kind TEXT NOT NULL,
            event_id INTEGER NOT NULL, start_ts INTEGER, fetched_at TEXT NOT NULL,
            PRIMARY KEY (entity_id, kind, event_id));
        CREATE TABLE sofa_entity_events (sofascore_entity_id INTEGER NOT NULL,
            kind TEXT NOT NULL, page INTEGER NOT NULL, fetched_at TEXT NOT NULL,
            events_json TEXT NOT NULL);
        CREATE TABLE sofa_event_detail (sofascore_event_id INTEGER PRIMARY KEY,
            fetched_at TEXT NOT NULL, status_type TEXT, detail_json TEXT NOT NULL);
    """)
    for e in events:
        con.execute("INSERT INTO sofa_listed_event VALUES (?, 'football', ?, 'x', ?)",
                    (e["id"], e["startTimestamp"], json.dumps(e)))
        for side in ("homeTeam", "awayTeam"):
            kind = "last" if e["status"]["type"] == "finished" else "next"
            con.execute("INSERT INTO sofa_listing_event VALUES (?, ?, ?, ?, 'x')",
                        (e[side]["id"], kind, e["id"], e["startTimestamp"]))
    return con


def test_for_day_reads_the_group_from_the_cache_only() -> None:
    # only Poland's own games are on its pages; the walk finds the rest
    con = _db(group(64393))
    fixtures = [{"sport": "football", "sofascore_event_id": 15534171,
                 "competition_id": UNL, "kickoff_utc": "2026-11-17T19:45:00Z"},
                {"sport": "football", "sofascore_event_id": 999,
                 "competition_id": 17, "kickoff_utc": "2026-11-17T19:45:00Z"}]
    assert stakes_groups.for_day(con, fixtures) == {
        15534171: ["STAKES_NATIONAL_ALIVE(Poland)", "STAKES_NATIONAL_SECURED(Sweden)"]}


def test_from_db_reports_an_error_instead_of_raising(tmp_path: Path) -> None:
    got = stakes_groups.from_db(tmp_path / "missing" / "x.db", [])
    assert isinstance(got, str)


def test_merge_keeps_both_lists() -> None:
    assert stakes_groups.merge({1: ["A"]}, {1: ["B", "A"], 2: ["C"]}) == {
        1: ["A", "B"], 2: ["C"]}


# ------------------------------------------------------- where they show


def test_the_switch_is_2026_11_19() -> None:
    at = datetime(2026, 11, 19, 6, 0, tzinfo=UTC)
    assert epochs.STAKES_GROUPS_FROM_UTC == datetime(2026, 11, 19, tzinfo=UTC)
    assert epochs.stakes_groups("2026-11-19", at)
    assert not epochs.stakes_groups("2026-11-18", at)
    assert not epochs.stakes_groups("2026-11-19", datetime(2026, 11, 18, 23, tzinfo=UTC))


def test_sentences() -> None:
    assert stakes.flag_text("STAKES_NATIONAL_DEAD(Wales)") == (
        "Wales: w grupie nie ma już o co grać")
    assert stakes.flag_text("STAKES_NATIONAL_MUST_WIN(Norway; tb)") == (
        "Norway: gra o cel w grupie - bez wygranej (lub punktu) cel przepada"
        " (zależnie od kryteriów przy równej liczbie punktów)")
    assert stakes.flag_text("RR_DECIDED_SIDE(Linda Noskova 2-0)") == (
        "Linda Noskova: bilans w grupie przed ostatnim meczem 2-0")
    # the club flags read as before
    assert stakes.flag_text("STAKES_SIX_POINTER(73% sezonu)") == (
        "mecz o utrzymanie (oba kluby przy linii spadkowej) 73% sezonu")


def _leg(**extra: Any) -> dict[str, Any]:
    return {"sofascore_event_id": 15534171, "confidence": 0.8,
            "kickoff_utc": "2026-11-17T19:45:00Z", "market": "goals_total",
            "subject": "", "line": 2.5, "direction": "UNDER", "offered_odds": 1.3,
            "match": "Poland - Sweden", "sport": "football",
            "display_market": "goals_total", **extra}


def test_coupon_leg_pdf_html_and_dossier_carry_the_flag() -> None:
    conf = {"profile": "standard", "epoch": "stats_only", "created_at_utc": "x",
            "singles": [_leg()], "legs": [_leg()], "builders": []}
    flags = ["STAKES_NATIONAL_ALIVE(Poland)", "STAKES_NATIONAL_SECURED(Sweden)"]
    off = assemble(conf, None, [], {}, "now", "2026-11-17")
    on = assemble(conf, None, [], {}, "now", "2026-11-17", peer_active=True,
                  stakes_by_event={15534171: flags})
    assert [s["confidence"] for s in on["singles"]] == [
        s["confidence"] for s in off["singles"]]
    leg = on["singles"][0]
    assert leg["stakes"] == {"flags": flags, "effect": ""}
    pdf = stakes_label(leg)
    assert "Sweden: cel w grupie już zapewniony" in pdf
    assert stakes.label(leg).startswith("Poland: cel w grupie otwarty")
    block = stakes_block([leg])
    assert block is not None
    assert [f["flag"] for f in block["flags"]] == flags
    assert stakes_block([_leg()]) is None
    assert "stakes" in FIELDS


def test_html_row_carries_the_sentence() -> None:
    from bet.sofa import coupon_html

    flags = ["STAKES_NATIONAL_DEAD(Wales)"]
    conf = {"profile": "standard", "epoch": "stats_only", "created_at_utc": "x",
            "singles": [_leg()], "legs": [_leg()], "builders": []}
    doc = assemble(conf, None, [], {}, "now", "2026-11-17", peer_active=True,
                   stakes_by_event={15534171: flags})
    rows = coupon_html.build_view(doc, "2026-11-17")["rows"]
    assert [r["stakes"] for r in rows] == ["Wales: w grupie nie ma już o co grać"]
    bare = assemble(conf, None, [], {}, "now", "2026-11-17")
    assert [r["stakes"] for r in coupon_html.build_view(bare, "2026-11-17")["rows"]] == [""]
    tmpl = (Path(coupon_html.__file__).parent / "templates/coupon_view.html").read_text(
        encoding="utf-8")
    assert "r.stakes" in tmpl
