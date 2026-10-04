"""History comparability, schedule context and reads (2026-10-04).

SC Farense - Chaves, goals_total UNDER 3.5 @1.29, lost 4-0. Four classes of
defect, each pinned here:

K1  one predicate for "is this past match a friendly" (comparability), the
    pre-season tournament that leaked (Torneio de Verao, 36573) on the list,
    every history reader on it;
K2  a goal sample is the side's REGULAR matches of the fixture's own
    competition when it has enough (measured; corners etc. untouched);
K3  a make-up fixture, rest and congestion are computed (schedule) and shown;
K4  an analyst's or the verifier's read is persisted (reads.json) and
    consequential: NO_BET removes everywhere, WATCH removes from the official
    coupon and stays, marked, in the WARIANT; a football leg whose model sits
    more than 0.15 over its own sample's hit rate is an automatic WATCH.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from bet.sofa.cache import SofaCache
from bet.sofa.comparability import (
    FRIENDLY_COMPETITION_IDS,
    SAME_COMPETITION_METRICS,
    MatchKind,
    is_friendly_event,
    is_non_competitive_name,
    match_kind,
    pick_same_competition,
)
from bet.sofa.confidence import (
    Calibration,
    model_above_own_sample,
    own_hit_rate,
)
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture, LegRead, SheetRow
from bet.sofa.samples import process_fixture_samples
from bet.sofa.schedule import fixture_schedule, side_schedule
from bet.sofa.veto import load_reads, matching_reads, read_refusal

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "config/sofa_friendly_competitions.json"


def _event(
    eid: int,
    *,
    comp: int = 239,
    stage: str | None = None,
    unique: str = "Liga Portugal 2",
    round_name: str | None = None,
    cup_round_type: int | None = None,
    sport: str = "football",
    category: str = "Portugal",
) -> dict[str, Any]:
    info: dict[str, Any] = {"round": 5}
    if round_name is not None:
        info["name"] = round_name
    if cup_round_type is not None:
        info["cupRoundType"] = cup_round_type
    return {
        "id": eid,
        "tournament": {
            "name": stage or unique,
            "category": {"name": category, "sport": {"slug": sport}},
            "uniqueTournament": {"id": comp, "name": unique,
                                 "category": {"name": category}},
        },
        "roundInfo": info,
    }


# --- K1 -----------------------------------------------------------------------


def test_the_leaked_preseason_tournament_is_a_friendly_now() -> None:
    assert 36573 in FRIENDLY_COMPETITION_IDS
    assert match_kind(_event(1, comp=36573, unique="Torneio de Verão")) is (
        MatchKind.FRIENDLY
    )


def test_every_excluded_id_is_in_the_evidence_file_it_names() -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    for entry in cfg["excluded"]:
        text = (REPO / entry["evidence"]).read_text(encoding="utf-8")
        evidence = json.loads(text)
        if isinstance(evidence, dict) and "competitions" in evidence:
            ids = {c["competition_id"] for c in evidence["competitions"]}
            assert entry["competition_id"] in ids, entry
        else:  # a raw payload (the first entries): the id is in it
            assert f'"id": {entry["competition_id"]}' in text or (
                f'"id":{entry["competition_id"]}' in text), entry


def test_football_reads_the_id_list_not_the_name() -> None:
    # 852 is friendly-named and kept on purpose (the config's `allowed`).
    women = _event(1, comp=852, unique="International Friendly Games Women")
    assert not is_friendly_event(women, "football")
    assert is_friendly_event(_event(2, comp=853, unique="Club Friendly Games"),
                             "football")


@pytest.mark.parametrize(
    ("sport", "name", "category"),
    [
        ("ice-hockey", "NHL Preseason", "North America"),
        ("basketball", "Club Friendly Games", "International"),
        ("basketball", "NBA Summer League", "USA"),
        ("tennis", "Six Kings Slam", "Exhibition"),
        ("tennis", "Roland Garros, Legends Doubles, Women", "Legends"),
    ],
)
def test_other_sports_drop_preseason_and_exhibitions(
    sport: str, name: str, category: str
) -> None:
    assert is_friendly_event(_event(1, comp=1, unique=name, sport=sport,
                                    category=category), sport)


def test_a_competitive_name_is_not_a_friendly() -> None:
    for name in ("NHL", "Laver Cup", "RES Showdown Playoffs", "StarLadder Major"):
        assert not is_non_competitive_name(name)


@pytest.mark.parametrize(
    ("event", "kind"),
    [
        (_event(1), MatchKind.REGULAR),
        (_event(2, stage="Liga Portugal 2, Relegation/Promotion", round_name="Final",
                cup_round_type=1), MatchKind.KNOCKOUT),
        (_event(3, comp=336, unique="Taça de Portugal", round_name="Round 2"),
         MatchKind.KNOCKOUT),
        (_event(4, stage="Premiership, Relegation Round", unique="Premiership"),
         MatchKind.REGULAR),
        (_event(5, stage="Oberliga, Playoffs", unique="Oberliga"),
         MatchKind.KNOCKOUT),
        (_event(6, stage="Liga, Group A", unique="Liga"), MatchKind.REGULAR),
    ],
)
def test_match_kind_reads_the_round(event: dict[str, Any], kind: MatchKind) -> None:
    assert match_kind(event, "football") is kind


# --- K2 -----------------------------------------------------------------------


def test_goal_markets_only_pick_from_their_competition() -> None:
    assert SAME_COMPETITION_METRICS == {
        "goals_for", "goals_1h_for", "goals_2h_for", "goals_total"}
    assert not SAME_COMPETITION_METRICS & {"corners_total", "fouls_for",
                                           "cards_points_total"}


def test_pick_same_competition_falls_back_below_the_minimum() -> None:
    items = [(239, True)] * 4 + [(336, True)] * 6
    pick = pick_same_competition(items, 239, 10, lambda x: x[0], lambda x: x[1])
    assert pick is None  # four of the fixture's competition: keep the usual sample
    items = [(239, True)] * 7 + [(239, False)] * 3 + [(336, True)] * 5
    pick = pick_same_competition(items, 239, 10, lambda x: x[0], lambda x: x[1])
    assert pick is not None and len(pick) == 7


KICKOFF = datetime(2026, 10, 4, 10, 0, tzinfo=UTC)


def _played(eid: int, days_ago: int, home: int, away: int, hs: int, as_: int,
            **kind: Any) -> dict[str, Any]:
    event = _event(eid, **kind)
    event.update({
        "status": {"type": "finished", "code": 100},
        "startTimestamp": int((KICKOFF - timedelta(days=days_ago)).timestamp()),
        "homeTeam": {"id": home, "name": f"T{home}"},
        "awayTeam": {"id": away, "name": f"T{away}"},
        "homeScore": {"current": hs, "period1": 0, "period2": hs, "normaltime": hs},
        "awayScore": {"current": as_, "period1": 0, "period2": as_,
                      "normaltime": as_},
        "season": {"id": 97470},
    })
    return event


def _fixture() -> Fixture:
    return Fixture(
        sofascore_event_id=17009055, superbet_event_ids=["1"], sport="football",
        kickoff_utc=KICKOFF, home_name="SC Farense", away_name="Chaves",
        home_entity_id=2998, away_entity_id=3025,
        competition_name="Liga Portugal 2", competition_id=239, season_id=97470,
        category_name="Portugal", identity="CONFIRMED", round_number=5,
        round_name=None, cup_round_type=None, previous_leg_event_id=None,
        venue_name=None, referee=None, ground_type=None, default_period_count=2,
    )


def _listings() -> dict[int, list[dict[str, Any]]]:
    home = [
        # six league matches, one goal each way
        *(_played(100 + i, 20 + 7 * i, 2998, 500 + i, 1, 0) for i in range(6)),
        # four newer cup ties against amateurs, five goals each
        *(_played(200 + i, 8 + i, 2998, 600 + i, 5, 0, comp=336,
                  unique="Taça de Portugal", round_name="Round 2")
          for i in range(4)),
        # a pre-season tournament, the newest of all
        _played(300, 3, 2998, 700, 7, 0, comp=36573,
                unique="Torneio de Verão Póvoa de Varzim"),
    ]
    postponed = _played(400, 28, 2998, 3025, 0, 0)
    postponed["status"] = {"type": "postponed"}
    postponed["homeScore"] = postponed["awayScore"] = {}
    home.append(postponed)
    away = [_played(800 + i, 6 + 7 * i, 3025, 900 + i, 1, 1) for i in range(10)]
    return {2998: home, 3025: away}


@pytest.fixture
def harness(tmp_path: Path) -> tuple[MagicMock, SofaCache, MagicMock]:
    from bet.sofa.db import migrate

    db = str(tmp_path / "t.db")
    migrate(db)
    cache = SofaCache(SofaConfig(db_path=db))
    client = MagicMock()
    listings = _listings()
    client.entity_events.side_effect = lambda eid, kind, page: (
        {"events": listings[eid], "hasNextPage": False} if page == 0 else None
    )
    client.event_statistics.return_value = {"statistics": []}
    client.event_incidents.return_value = {}
    superbet = MagicMock()
    superbet.event_odds.return_value = {"odds": [{"marketName": "Liczba goli"}]}
    return client, cache, superbet


def test_a_goal_sample_holds_only_league_rounds_of_the_fixture_competition(
    harness: tuple[MagicMock, SofaCache, MagicMock],
) -> None:
    client, cache, superbet = harness
    res = process_fixture_samples(
        _fixture(), client, cache, superbet, SofaConfig(sample_n=10, min_sample=5)
    )
    side_a = res.metrics["goals_total"].side_a
    ids = {o.sofascore_event_id for o in side_a}
    # The four cup ties and the pre-season tournament are newer, and out.
    assert ids == {100, 101, 102, 103, 104, 105}
    assert all(o.value == 1.0 for o in side_a)


def test_the_postponed_meeting_marks_a_make_up_fixture(
    harness: tuple[MagicMock, SofaCache, MagicMock],
) -> None:
    client, cache, superbet = harness
    res = process_fixture_samples(
        _fixture(), client, cache, superbet, SofaConfig(sample_n=10, min_sample=5)
    )
    assert res.schedule is not None
    assert res.schedule.makeup_of == 400
    assert any(f.startswith("MAKEUP_FIXTURE") for f in res.schedule.flags())
    # the friendly does not count as the side's last match: the cup tie does
    assert res.schedule.side_a.rest_days == 8.0


# --- K3 -----------------------------------------------------------------------


def test_side_schedule_counts_rest_and_congestion() -> None:
    k = int(KICKOFF.timestamp())
    events = [_played(i, d, 1, 2, 0, 0) for i, d in enumerate((2, 4, 6, 12, 30))]
    sched = side_schedule(events, k)
    assert (sched.rest_days, sched.matches_7d, sched.matches_14d) == (2.0, 3, 4)


def test_a_postponement_in_another_competition_is_not_a_make_up() -> None:
    k = int(KICKOFF.timestamp())
    cup = _played(1, 10, 1, 2, 0, 0, comp=336, unique="Taça de Portugal")
    cup["status"] = {"type": "postponed"}
    later = _played(2, -3, 1, 2, 0, 0)
    later["status"] = {"type": "postponed"}
    sched = fixture_schedule([cup, later], [], 1, 2, 239, k, 99)
    assert sched.makeup_of is None and sched.flags() == []


# --- K4 -----------------------------------------------------------------------


def _read(**over: Any) -> LegRead:
    base: dict[str, Any] = dict(
        sofascore_event_id=1, market=None, subject=None, line=None, direction=None,
        verdict="WATCH", author="analyst", reason="Chaves 4/5/4/5 goals",
    )
    base.update(over)
    return LegRead(**base)


def test_a_read_needs_a_reason_and_no_extra_keys() -> None:
    with pytest.raises(ValidationError):
        _read(reason="")
    with pytest.raises(ValidationError):
        LegRead.model_validate({**_read().model_dump(), "severity": "high"})


def test_watch_removes_only_where_the_profile_honours_it() -> None:
    watch, nobet, keep = _read(), _read(verdict="NO_BET"), _read(verdict="KEEP")
    assert read_refusal([watch], honours_watch=True) == "WATCHED"
    assert read_refusal([watch], honours_watch=False) is None
    assert read_refusal([nobet], honours_watch=False) == "READ_NO_BET"
    assert read_refusal([keep], honours_watch=True) is None
    assert read_refusal([], honours_watch=True) is None


def test_reads_match_like_vetoes() -> None:
    reads = [_read(market="goals_total", line=3.5, direction="UNDER")]
    hit = matching_reads(reads, sofascore_event_id=1, market="goals_total",
                         subject="", line=3.5, direction="UNDER")
    miss = matching_reads(reads, sofascore_event_id=1, market="goals_total",
                          subject="", line=3.5, direction="OVER")
    assert hit == reads and miss == []


def test_absent_reads_file_is_no_reads(tmp_path: Path) -> None:
    assert load_reads(tmp_path / "reads.json") == []


def test_own_hit_rate_and_the_gap_gate() -> None:
    values = [4.0, 5.0, 4.0, 5.0, 1.0, 1.0, 3.0, 2.0, 1.0, 1.0]
    assert own_hit_rate(values, 3.5, "UNDER") == pytest.approx(0.6)
    assert model_above_own_sample("football", 0.80, values, 3.5, "UNDER") == (
        pytest.approx(0.20))
    assert model_above_own_sample("football", 0.70, values, 3.5, "UNDER") is None
    assert model_above_own_sample("tennis", 0.80, values, 3.5, "UNDER") is None
    assert model_above_own_sample("football", 0.80, values[:4], 3.5, "UNDER") is None


# --- K4 end to end through CONFIDENCE ----------------------------------------

DAY = "2099-01-01"
NOW = datetime.now(UTC)
FAR = "2099-01-01T20:00:00Z"


def _fx(eid: int) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid, "superbet_event_ids": [f"s{eid}"],
        "sport": "football", "kickoff_utc": FAR,
        "home_name": f"Home {eid}", "away_name": f"Away {eid}",
        "home_entity_id": eid * 10, "away_entity_id": eid * 10 + 1,
        "competition_name": "Test League", "competition_id": 9, "season_id": 9,
        "category_name": "Test", "identity": "CONFIRMED",
        "round_number": None, "round_name": None, "cup_round_type": None,
        "previous_leg_event_id": None, "venue_name": None, "referee": None,
        "ground_type": None, "default_period_count": 2,
        "superbet_kickoff_utc": FAR, "kickoff_disagreement_h": 0.0,
    }


def _row(eid: int, p: float, odds: float) -> dict[str, Any]:
    row = {
        "sofascore_event_id": eid, "sport": "football", "market": "goals_total",
        "subject": "", "line": 1.5, "direction": "OVER", "sample_size": 20,
        "sample_mean": 2.6, "sample_sd": 1.2, "centre": 2.6, "p_central": p,
        "market_p": p - 0.03, "ladder_centre": None, "ladder_sigma": None,
        "p_bar": p - 0.02, "bar_reason": "none", "required_odds": 1.0,
        "offered_odds": odds, "edge": 0.0, "surplus": 0.0, "verdict": "BELOW_BAR",
        "notes": [],
    }
    SheetRow.model_validate(row)
    return row


def _samples_doc(eid: int, values: list[int]) -> dict[str, Any]:
    obs = [
        {"sofascore_event_id": eid * 100 + i,
         "match_date_utc": (NOW - timedelta(days=3 + i)).isoformat().replace(
             "+00:00", "Z"),
         "opponent": "X", "value": float(v), "minutes": None,
         "competition_id": 9, "season_id": 9, "venue": None}
        for i, v in enumerate(values)
    ]
    return {"sofascore_event_id": eid, "readiness": "READY", "gaps": [],
            "players": {}, "metrics": {"goals_total": {
                "metric": "goals_total", "side_a": obs[:10], "side_b": obs[10:],
                "h2h": []}}}


def _offer(eid: int, over: float, under: float) -> dict[str, Any]:
    return {"sofascore_event_id": eid, "status": "PRICED", "unmapped_markets": [],
            "price_collisions": [], "rungs": [{
                "market": "goals_total", "subject": "", "line": 1.5,
                "over_odds": over, "under_odds": under,
                "fetched_at_utc": NOW.isoformat().replace("+00:00", "Z")}]}


# 17 of 20 over 1.5 (0.85), and 12 of 20 (0.60) for the gap leg.
HIGH = [2, 3, 2, 3, 4, 2, 1, 3, 2, 2, 2, 3, 1, 2, 5, 2, 1, 3, 2, 2]
LOW = [2, 3, 2, 1, 4, 2, 1, 3, 2, 0, 2, 3, 1, 1, 5, 2, 1, 1, 0, 2]
P_KEEP, ODDS_KEEP = 0.80, 1.45
P_GAP, ODDS_GAP = 0.80, 1.45


@pytest.fixture()
def conf_day(tmp_path: Path) -> Path:
    cal = Calibration.load()
    conf = cal.realised("goals_total", P_KEEP, "football")
    assert conf is not None and conf[0] >= 0.70 and conf[0] * ODDS_KEEP > 1.0, conf
    run = tmp_path / DAY
    run.mkdir()
    (run / "02_fixtures.json").write_text(json.dumps([_fx(1), _fx(2)]))
    (run / "03_samples.json").write_text(json.dumps(
        [_samples_doc(1, HIGH), _samples_doc(2, LOW)]))
    (run / "04_offer.json").write_text(json.dumps(
        [_offer(1, ODDS_KEEP, 2.80), _offer(2, ODDS_GAP, 2.80)]))
    (run / "05_sheet.json").write_text(json.dumps(
        [_row(1, P_KEEP, ODDS_KEEP), _row(2, P_GAP, ODDS_GAP)]))
    (run / "vetoes.json").write_text("[]")
    return tmp_path


def _confidence(runs: Path, *extra: str) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, "scripts/sofa/run_confidence.py", "--date", DAY,
         "--runs-dir", str(runs), *extra],
        cwd=REPO, capture_output=True, text=True,
        env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, proc.stderr
    summary: dict[str, Any] = json.loads(proc.stdout.strip().splitlines()[-1])
    return summary


def _legs(runs: Path, name: str) -> dict[int, dict[str, Any]]:
    doc = json.loads((runs / DAY / name).read_text())
    return {leg["sofascore_event_id"]: leg for leg in doc["legs"]}


def test_the_gap_gate_is_an_automatic_watch(conf_day: Path) -> None:
    summary = _confidence(conf_day)
    assert summary["metrics"]["refused"].get("MODEL_ABOVE_OWN_SAMPLE") == 1
    legs = _legs(conf_day, "08_confidence.json")
    assert set(legs) == {1}
    assert legs[1]["sample_hit_rate"] == pytest.approx(0.85)
    _confidence(conf_day, "--profile", "wariant")
    wariant = _legs(conf_day, "08_confidence_wariant.json")
    assert 2 in wariant
    assert any(f.startswith("MODEL_ABOVE_OWN_SAMPLE")
               for f in wariant[2]["context_flags"])


def test_a_watch_leaves_the_coupon_and_stays_marked_in_the_wariant(
    conf_day: Path,
) -> None:
    (conf_day / DAY / "reads.json").write_text(json.dumps([
        _read(sofascore_event_id=1, market="goals_total").model_dump(),
    ]))
    summary = _confidence(conf_day)
    assert summary["metrics"]["refused"].get("WATCHED") == 1
    assert 1 not in _legs(conf_day, "08_confidence.json")
    _confidence(conf_day, "--profile", "wariant")
    leg = _legs(conf_day, "08_confidence_wariant.json")[1]
    assert leg["reads"] == [{"verdict": "WATCH", "author": "analyst",
                             "reason": "Chaves 4/5/4/5 goals"}]


def test_no_bet_leaves_both_profiles(conf_day: Path) -> None:
    (conf_day / DAY / "reads.json").write_text(json.dumps([
        _read(sofascore_event_id=1, verdict="NO_BET", author="verifier").model_dump(),
    ]))
    _confidence(conf_day)
    _confidence(conf_day, "--profile", "wariant")
    assert 1 not in _legs(conf_day, "08_confidence.json")
    assert 1 not in _legs(conf_day, "08_confidence_wariant.json")


def test_a_read_that_covers_nothing_is_reported(conf_day: Path) -> None:
    (conf_day / DAY / "reads.json").write_text(json.dumps([
        _read(sofascore_event_id=999).model_dump(),
    ]))
    summary = _confidence(conf_day)
    assert summary["metrics"]["reads_unmatched"] == 1
    doc = json.loads((conf_day / DAY / "08_confidence.json").read_text())
    assert doc["reads_unmatched"] == 1 and doc["honours_watch"] is True


# --- review 2026-10-04 -----------------------------------------------------------


def test_a_postponed_meeting_played_since_is_not_owed() -> None:
    k = int(KICKOFF.timestamp())
    postponed = _played(1, 120, 1, 2, 0, 0)
    postponed["status"] = {"type": "postponed"}
    replayed = _played(2, 100, 2, 1, 1, 1)  # the pair met again, either way round
    sched = fixture_schedule([postponed, replayed], [], 1, 2, 239, k, 99)
    assert sched.makeup_of is None
    assert fixture_schedule([postponed], [], 1, 2, 239, k, 99).makeup_of == 1


def test_a_postponement_of_another_season_is_not_a_make_up() -> None:
    k = int(KICKOFF.timestamp())
    postponed = _played(1, 300, 1, 2, 0, 0)
    postponed["status"] = {"type": "postponed"}
    postponed["season"] = {"id": 77801}
    sched = fixture_schedule([postponed], [], 1, 2, 239, k, 99, season=97470)
    assert sched.makeup_of is None


def test_the_gap_gate_leaves_player_props_alone() -> None:
    values = [0.0] * 6 + [2.0] * 4
    assert model_above_own_sample(
        "football", 0.9, values, 0.5, "OVER", "player_shots_for") is None
    assert model_above_own_sample(
        "football", 0.9, values, 0.5, "OVER", "shots_for") is not None


def test_the_pipeline_refuses_a_frozen_clock() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/sofa/run_pipeline.py", "--date", DAY,
         "--only", "BOARD"],
        cwd=REPO, capture_output=True, text=True,
        env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin",
             "SOFA_NOW": "2026-10-04T06:00:00Z"},
    )
    assert proc.returncode == 2 and "SOFA_NOW" in proc.stderr


def test_a_coupon_drop_names_the_read_that_dropped_it() -> None:
    from bet.sofa.coupon import build_coupon

    row = SheetRow.model_validate({
        "sofascore_event_id": 5, "sport": "football", "market": "goals_total",
        "subject": "", "line": 3.5, "direction": "UNDER", "sample_size": 20,
        "sample_mean": 2.4, "sample_sd": 1.6, "centre": 2.3, "p_central": 0.78,
        "market_p": 0.74, "ladder_centre": None, "ladder_sigma": None,
        "p_bar": 0.77, "bar_reason": "none", "required_odds": 1.2,
        "offered_odds": 1.40, "edge": 0.04, "surplus": 0.1, "verdict": "VALUE",
        "notes": []})
    fx = _fixture().model_copy(update={"sofascore_event_id": 5,
                                       "kickoff_utc": KICKOFF + timedelta(days=1)})
    reads = [_read(sofascore_event_id=5, verdict="KEEP", reason="fine"),
             _read(sofascore_event_id=5, verdict="WATCH", author="verifier",
                   reason="model over its own sample")]
    result = build_coupon(
        sheet_rows=[row], fixtures=[fx], offers=[], vetoes=[],
        current_time=KICKOFF, min_kickoff=KICKOFF, max_price_age=timedelta(hours=1),
        reads=reads,
    )
    drop = [d for d in result.dropped if d.reason == "WATCHED"]
    assert drop and drop[0].detail == "model over its own sample"


def test_a_knockout_fixture_keeps_the_newest_ten_goal_sample(
    harness: tuple[MagicMock, SofaCache, MagicMock],
) -> None:
    # Review 2026-10-04: on KNOCKOUT targets the same-competition rule was
    # worse (goals_total +0.00546, goals_for +0.01227 log-loss, 24,777 /
    # 31,738 matches), so a cup round keeps the usual sample.
    client, cache, superbet = harness
    fixture = _fixture().model_copy(update={"round_name": "Quarterfinals",
                                            "cup_round_type": 8})
    res = process_fixture_samples(
        fixture, client, cache, superbet, SofaConfig(sample_n=10, min_sample=5)
    )
    ids = {o.sofascore_event_id for o in res.metrics["goals_total"].side_a}
    assert ids != {100, 101, 102, 103, 104, 105}
    assert {200, 201, 202, 203} <= ids, "the newest matches, cup ties included"


def test_the_replay_reads_a_knockout_target_from_the_newest_ten() -> None:
    from scripts.sofa import calibrate_from_cache as cfc

    def played(eid: int, ts: int, comp: int, kind: str, home: int = 1,
               away: int = 2) -> cfc.Played:
        return cfc.Played(event_id=eid, timestamp=ts, home_id=home, away_id=away,
                          sport="football", competition_id=comp,
                          values={"goals": (1.0, 0.0)}, kind=kind)

    # Team 1: eight old league matches of 239 (the replay's MIN_SAMPLE), then
    # five newer cup ties of 336.
    history = [played(i, i, 239, "REGULAR", away=100 + i) for i in range(8)]
    history += [played(10 + i, 10 + i, 336, "KNOCKOUT", away=200 + i)
                for i in range(5)]
    league = played(50, 50, 239, "REGULAR", away=2)
    cup = played(60, 60, 239, "KNOCKOUT", away=3)
    rows = [r for r in cfc.iter_rows([*history, league, cup], {})
            if r.market == "goals_for" and r.event_id in (50, 60)
            and r.line == 0.5 and r.direction == "OVER"]
    sizes = {r.event_id: r.sample_size for r in rows}
    means = {r.event_id: r.sample_mean for r in rows}
    assert sizes and means[50] == 1.0 and means[60] == 1.0
    # The league target reads its eight league matches; the knockout one the
    # newest ten (cup ties included).
    assert sizes[50] == 8 and sizes[60] == 10
