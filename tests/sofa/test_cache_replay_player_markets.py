"""The cache replay writes football player-market rows (2026-10-03).

Until then calibrate_from_cache wrote no player row, so fit_confidence never
had a curve for a player prop and AWAITING_OWN_CURVE could not lapse. The
replay rebuilds a player's sample as SAMPLES / SHEET do - the side's indexed
listing before kickoff, samples.finish_history, players.squad_statistics /
match_player / extract_player_metric per historical squad, the majority
side, min_sample, the all-zero refusal, engine.sheet_count_p_raw - prices
every line Superbet printed for the metric (runs/sofa/*/04_offer.json) in
both directions and settles it against the player's value in the match.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import sys
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.db import migrate
from bet.sofa.engine import (
    outside_model_resolution,
    sheet_count_p_raw,
    sheet_predictive_sd,
    winning_boundary,
)
from bet.sofa.listing_index import index_page
from scripts.sofa import calibrate_from_cache as cfc

DAY = 86_400
KICKOFF = 1_790_000_000
COMPETITION = 17
HOME, AWAY = 1, 2
LADDER = {"player_shots_for": [0.5, 1.5, 2.5], "player_fouls_for": [0.5, 1.5]}


def _event(eid: int, home: int, away: int, ts: int,
           score: tuple[int, int] = (1, 0)) -> dict[str, Any]:
    return {
        "id": eid, "startTimestamp": ts,
        "status": {"type": "finished", "code": 100},
        "homeTeam": {"id": home, "name": f"Team {home}"},
        "awayTeam": {"id": away, "name": f"Team {away}"},
        "homeScore": {"current": score[0]}, "awayScore": {"current": score[1]},
        "tournament": {"uniqueTournament": {"id": COMPETITION},
                       "category": {"sport": {"slug": "football"}}},
    }


def _player(name: str, **stats: float) -> dict[str, Any]:
    return {"player": {"name": name}, "statistics": dict(stats)}


def _statistics(home: dict[str, float], away: dict[str, float]) -> dict[str, Any]:
    keys = sorted(set(home) | set(away))
    return {"statistics": [{"period": "ALL", "groups": [{"statisticsItems": [
        {"key": k, "homeValue": home.get(k, 0), "awayValue": away.get(k, 0)}
        for k in keys
    ]}]}]}


class Cache:
    """A tiny sofa.db: listings in the index, stats and lineups per event."""

    def __init__(self, tmp_path: Path) -> None:
        self.db = tmp_path / "sofa.db"
        migrate(str(self.db))
        self.listings: dict[int, list[dict[str, Any]]] = {}

    def match(
        self,
        event: dict[str, Any],
        home_players: list[dict[str, Any]] | None,
        away_players: list[dict[str, Any]] | None,
        team_stats: tuple[dict[str, float], dict[str, float]] = ({}, {}),
    ) -> None:
        for side in ("homeTeam", "awayTeam"):
            self.listings.setdefault(event[side]["id"], []).append(event)
        lineups = None
        if home_players is not None or away_players is not None:
            lineups = {"home": {"players": home_players or []},
                       "away": {"players": away_players or []}}
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "INSERT INTO sofa_event_stats (sofascore_event_id, fetched_at,"
                " statistics_json, incidents_json, status_type, lineups_json)"
                " VALUES (?, '2026-10-01', ?, NULL, 'finished', ?)",
                (event["id"], json.dumps(_statistics(*team_stats)),
                 json.dumps(lineups) if lineups is not None else None))

    def index(self) -> None:
        with sqlite3.connect(self.db) as conn:
            for entity, events in self.listings.items():
                index_page(conn, entity, "last", "2026-10-01T00:00:00+00:00",
                           {"events": events})


KOWALSKI_SHOTS = [2, 0, 1, 3, 1, 2, 4]   # HOME's 7 matches, newest first
KOWALSKI_FOULS = [1, None, 2, 0, None, 1, 3]  # None: key absent


def _fixture(tmp_path: Path) -> Cache:
    cache = Cache(tmp_path)
    for i, (shots, fouls) in enumerate(zip(KOWALSKI_SHOTS, KOWALSKI_FOULS,
                                           strict=True)):
        eid = 100 + i
        stats: dict[str, float] = {"totalShots": shots, "minutesPlayed": 90}
        if fouls is not None:
            stats["fouls"] = fouls
        team_fouls = (fouls or 0) + 5
        # The team figure closes the sum (proves an absent key zero) in every
        # match but 104, where it does not: there the absent key is a gap.
        if eid == 104:
            team_fouls += 1
        cache.match(
            _event(eid, HOME, 50 + i, KICKOFF - (i + 1) * 7 * DAY),
            [_player("Jan Kowalski", **stats),
             _player("Ole Rest", minutesPlayed=90, fouls=5, totalShots=0),
             _player("Bench Guy", totalShots=0)],
            [],
            ({"fouls": team_fouls, "totalShotsOnGoal": 5},
             {"fouls": 9, "totalShotsOnGoal": 3}),
        )
    # AWAY: only four matches with a squad - thin for anyone on it - and the
    # transfer case: "Piotr Zielinski" appears for AWAY in all four.
    for i in range(4):
        cache.match(
            _event(200 + i, AWAY, 60 + i, KICKOFF - (i + 1) * 7 * DAY - 3600),
            [_player("Adam Nowak", minutesPlayed=90, totalShots=1),
             _player("Piotr Zielinski", minutesPlayed=90, totalShots=2)],
            [],
        )
    # After the target's kickoff: must never enter its sample.
    cache.match(
        _event(300, HOME, 70, KICKOFF + 3 * DAY),
        [_player("Jan Kowalski", minutesPlayed=90, totalShots=40)], [],
    )
    # The target: Kowalski played (3 shots, no fouls key, team sum closes);
    # Bench Guy did not; Zielinski now plays for HOME (his history is AWAY's).
    cache.match(
        _event(999, HOME, AWAY, KICKOFF, (2, 1)),
        [_player("Jan Kowalski", minutesPlayed=88, totalShots=3),
         _player("Ole Rest", minutesPlayed=90, fouls=4, totalShots=0),
         _player("Piotr Zielinski", minutesPlayed=60, totalShots=1),
         _player("Bench Guy", totalShots=0)],
        [_player("Adam Nowak", minutesPlayed=90, totalShots=2)],
        ({"fouls": 4}, {"fouls": 0}),
    )
    return cache


def _expected(metric: str, sample: list[float], actual: float,
              lines: list[float]) -> dict[tuple[float, str], tuple[float, str]]:
    n = len(sample)
    mean = statistics.mean(sample)
    sd = sheet_predictive_sd(metric, "football", mean, statistics.variance(sample),
                             n, mean)
    out: dict[tuple[float, str], tuple[float, str]] = {}
    for line in lines:
        for direction in ("OVER", "UNDER"):
            p = sheet_count_p_raw(metric, mean, sd, winning_boundary(line, direction),
                                  direction)
            if outside_model_resolution(p):
                continue
            won = actual > line if direction == "OVER" else actual < line
            out[(line, direction)] = (round(p, 6), "WIN" if won else "LOSS")
    return out


def _target_rows(rows: list[cfc.SettledRow]) -> list[cfc.SettledRow]:
    """The target match's rows (every historical match with a squad is a
    target of its own too)."""
    return [r for r in rows if r.event_id == 999]


def _rows(tmp_path: Path) -> tuple[list[cfc.SettledRow], dict[str, int]]:
    cache = _fixture(tmp_path)
    cache.index()
    rows, counts = cfc.build_player_rows(cache.db, LADDER, sample_n=10, min_sample=5)
    return _target_rows(rows), dict(counts)


def test_player_rows_rebuild_the_sheet_sample_and_settle_both_directions(
    tmp_path: Path,
) -> None:
    rows, counts = _rows(tmp_path)
    assert {(r.subject, r.market) for r in rows} == {
        ("jan kowalski", "player_shots_for"),
        ("jan kowalski", "player_fouls_for"),
        ("ole rest", "player_fouls_for"),
    }, (
        "Nowak is thin (4 < 5), Bench Guy never came on, Zielinski's history "
        "is the other side's, Ole Rest's shots are all zero"
    )
    # Zielinski's shots: his history is AWAY's. (His fouls have no sample at
    # all - AWAY's matches carry no team figure to prove an absent key zero.)
    assert counts["majority_on_other_side"] == 1
    assert counts["thin_sample"] >= 2  # Nowak, both metrics (and earlier targets)
    assert counts["all_zero_sample"] >= 1  # Ole Rest's shots

    shots = {(r.line, r.direction): (r.p_central, r.outcome)
             for r in rows if r.market == "player_shots_for"}
    expected = _expected("player_shots_for", [float(v) for v in KOWALSKI_SHOTS],
                         3.0, LADDER["player_shots_for"])
    assert shots == expected
    assert {d for _, d in shots} == {"OVER", "UNDER"}
    one = next(r for r in rows if r.market == "player_shots_for")
    assert (one.event_id, one.sport, one.competition_id, one.sample_size,
            one.actual) == (999, "football", COMPETITION, 7, 3.0)


def test_team_sum_proves_an_absent_zero_and_a_gap_stays_a_gap(tmp_path: Path) -> None:
    rows, _ = _rows(tmp_path)
    fouls = [r for r in rows
             if r.market == "player_fouls_for" and r.subject == "jan kowalski"]
    # 101 absent and proven zero; 104 absent and NOT proven -> out of the
    # sample, not a zero. The target's absent key is proven zero too.
    sample = [1.0, 0.0, 2.0, 0.0, 1.0, 3.0]
    assert {r.sample_size for r in fouls} == {6}
    assert {(r.line, r.direction): (r.p_central, r.outcome) for r in fouls} == (
        _expected("player_fouls_for", sample, 0.0, LADDER["player_fouls_for"]))
    assert {r.actual for r in fouls} == {0.0}


def test_the_sample_never_reaches_past_kickoff_or_into_a_relisted_copy(
    tmp_path: Path,
) -> None:
    cache = _fixture(tmp_path)
    # The target re-listed under another id an hour earlier, with a result
    # that would move the sample: it is the match itself.
    cache.match(
        # 20 h earlier: another UTC day, so one_listing_per_match keeps both.
        _event(998, HOME, AWAY, KICKOFF - 20 * 3600, (2, 1)),
        [_player("Jan Kowalski", minutesPlayed=88, totalShots=30)], [],
    )
    cache.index()
    rows, counts = cfc.build_player_rows(cache.db, LADDER, sample_n=10, min_sample=5)
    target = [r for r in _target_rows(rows) if r.market == "player_shots_for"]
    assert target and {r.sample_size for r in target} == {7}
    assert {r.sample_mean for r in target} == {
        round(statistics.mean(KOWALSKI_SHOTS), 4)}
    assert counts["history_same_match_dropped"] >= 1


def test_sample_n_caps_the_side_history_not_the_appearances(tmp_path: Path) -> None:
    cache = _fixture(tmp_path)
    cache.index()
    rows, _ = cfc.build_player_rows(cache.db, LADDER, sample_n=5, min_sample=5)
    shots = [r for r in _target_rows(rows) if r.market == "player_shots_for"]
    assert {r.sample_size for r in shots} == {5}
    assert {r.sample_mean for r in shots} == {
        round(statistics.mean(KOWALSKI_SHOTS[:5]), 4)}


def test_no_printed_ladder_means_no_player_rows(tmp_path: Path) -> None:
    cache = _fixture(tmp_path)
    cache.index()
    rows, counts = cfc.build_player_rows(cache.db, {}, sample_n=10, min_sample=5)
    assert rows == [] and counts["no_printed_player_ladder"] == 1


def test_printed_ladder_reads_every_player_line_of_every_offer(tmp_path: Path) -> None:
    for day, rungs in {
        "2026-09-30": [{"market": "player_shots_for", "line": 1.5},
                       {"market": "corners_total", "line": 9.5},
                       {"market": "player_shots_for", "line": 0.5}],
        "2026-10-01": [{"market": "player_shots_for", "line": 1.5},
                       {"market": "player_assists_for", "line": 0.5}],
    }.items():
        (tmp_path / day).mkdir()
        (tmp_path / day / "04_offer.json").write_text(
            json.dumps([{"sofascore_event_id": 1, "rungs": rungs}]))
    (tmp_path / "2026-10-02").mkdir()
    (tmp_path / "2026-10-02" / "04_offer.json").write_text("not json")
    assert cfc.printed_player_ladder(tmp_path) == {
        "player_assists_for": [0.5], "player_shots_for": [0.5, 1.5]}


def _db_rows(db: Path) -> list[tuple[Any, ...]]:
    with sqlite3.connect(db) as conn:
        return conn.execute(
            "SELECT run_date, sofascore_event_id, sport, competition_id, market,"
            " subject, line, direction, sample_size, sample_mean, sample_sd,"
            " p_central, p_bar, market_p, actual_value, outcome, ladder_sigma"
            " FROM sofa_settled_row ORDER BY sofascore_event_id, market, subject,"
            " line, direction").fetchall()


def _main(monkeypatch: pytest.MonkeyPatch, db: Path, runs: Path, players: str,
          config_dir: Path) -> None:
    monkeypatch.setenv("SOFA_CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(sys, "argv", [
        "calibrate_from_cache", "--db-path", str(db), "--runs-dir", str(runs),
        "--players", players])
    assert cfc.main() == 0


def test_main_writes_player_rows_marked_as_cache_rows_and_team_rows_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs = tmp_path / "runs"
    (runs / "2026-10-01").mkdir(parents=True)
    (runs / "2026-10-01" / "04_offer.json").write_text(json.dumps([{
        "sofascore_event_id": 999,
        "rungs": [{"market": m, "line": x} for m, xs in LADDER.items() for x in xs]}]))
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    with_players = tmp_path / "a"
    without = tmp_path / "b"
    for where in (with_players, without):
        where.mkdir()
        _fixture(where).index()
    _main(monkeypatch, with_players / "sofa.db", runs, "include", config_dir)
    _main(monkeypatch, without / "sofa.db", runs, "skip", config_dir)

    a = _db_rows(with_players / "sofa.db")
    b = _db_rows(without / "sofa.db")
    team_a = [r for r in a if not r[4].startswith("player_")]
    assert team_a, "without team rows the comparison would mean nothing"
    assert team_a == b, "the team-market rows are byte-for-byte what they were"

    player = [r for r in a if r[4].startswith("player_")]
    assert player and all(r[0] == "cache-calibration" for r in player)
    assert all(r[12] == r[11] and r[13] is None and r[16] is None for r in player), (
        "p_bar = p_central, market_p and ladder_sigma NULL - the team replay's marking")
    assert {r[5] for r in player} == {"jan kowalski", "ole rest"}

    # --players only touches no team row of an earlier run.
    _main(monkeypatch, without / "sofa.db", runs, "only", config_dir)
    assert _db_rows(without / "sofa.db") == a


def test_a_player_baseline_stops_the_player_replay(tmp_path: Path) -> None:
    from bet.sofa.config import SofaConfig

    out: list[cfc.SettledRow] = []
    metrics = cfc.replay_players(
        tmp_path / "missing.db", tmp_path, {"player_shots_for": {"global": 1.0}},
        SofaConfig(), out)
    assert out == [] and str(metrics["player_replay"]).startswith("SKIPPED")
