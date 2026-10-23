"""scripts/sofa/backfill_driver.py - the backfill stage runner's decisions.

Promoted 2026-10-22 from the ad-hoc runs/sofa/backfill drivers. Two things bit
that night: a Sofascore 403 "challenge" opened the circuit three times and the
driver died instead of waiting for the tab to mint a fresh token, and the
listings seed moves after every completed run, so a listings stage never ends
by its own count. These tests pin the pure decisions and the recovery loop.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.sofa import backfill_driver as bd

LISTINGS = bd.Stage("listings hockey", (bd.LISTINGS, "--sport", "hockey"),
                    "entities_to_deepen", max_hops=2)
STATS = bd.Stage("stats hockey", (bd.STATS, "--sport", "hockey"), "targets")
OPEN = {"final": True, "circuit_open": True}


def test_parse_output_takes_the_first_plan_and_the_final_line() -> None:
    out = "\n".join([json.dumps({"targets": 5}), "noise", "[1]",
                     json.dumps({"targets": 9}),
                     json.dumps({"final": True, "done": 5})])
    plan, final = bd.parse_output(out)
    assert plan == {"targets": 5}
    assert final == {"final": True, "done": 5}


def test_nothing_left_is_done() -> None:
    _, out = bd.judge_chunk(STATS, bd.Progress(), 0, {"targets": 0}, {})
    assert out == "DONE"
    # an empty plan line count but a clean exit is done too
    _, out = bd.judge_chunk(STATS, bd.Progress(), 0, {"run_id": "x"}, {})
    assert out == "DONE"


def test_three_chunks_without_progress_end_the_stage() -> None:
    p = bd.Progress()
    outs = []
    for _ in range(4):
        p, out = bd.judge_chunk(STATS, p, 0, {"targets": 4}, {"final": True})
        outs.append(out)
    assert outs == ["CONTINUE", "CONTINUE", "CONTINUE", "DONE_STALL"]


def test_progress_resets_the_stall_count() -> None:
    p = bd.Progress()
    for left in (10, 10, 8, 8, 8):
        p, out = bd.judge_chunk(STATS, p, 1, {"targets": left}, {})
    assert out == "CONTINUE" and p.stalls == 2


def test_circuit_open_is_a_breaker_not_a_failure() -> None:
    p, out = bd.judge_chunk(STATS, bd.Progress(), 2, {"targets": 7}, OPEN)
    assert out == "BREAKER" and p.failures == 0


def test_a_crash_is_retried_then_skipped() -> None:
    p = bd.Progress()
    outs = []
    for _ in range(3):
        p, out = bd.judge_chunk(STATS, p, 1, {}, {})  # traceback: no plan line
        outs.append(out)
    assert outs == ["FAILED", "FAILED", "SKIPPED"]
    _, out = bd.judge_chunk(STATS, bd.Progress(), 2, {}, {})  # argparse error
    assert out == "FAILED"


def test_listings_stop_after_max_hops_on_the_moving_seed() -> None:
    p = bd.Progress()
    seeds = ["2026-10-22T19:00", "2026-10-22T19:00", "2026-10-22T19:10",
             "2026-10-22T19:20"]
    outs = []
    for i, seed in enumerate(seeds):
        p, out = bd.judge_chunk(LISTINGS, p, 0,
                                {"entities_to_deepen": 50 - i, "seed_before": seed},
                                {})
        outs.append(out)
    assert outs == ["CONTINUE", "CONTINUE", "CONTINUE", "DONE_HOPS"]


def test_the_hop_past_the_limit_is_planned_not_walked(tmp_path: Path) -> None:
    # 2026-10-23 audit: the night driver saw the third seed only in the plan
    # line of a chunk that had already walked that hop, and logged that
    # chunk's own count ("740 left") as the queue it left behind.
    args = bd.argparse.Namespace(
        log=str(tmp_path / "d.log"), yield_to_build=False, blocker_wait_min=5.0,
        breaker_wait_min=15.0, breaker_stops=3, recover_hours=1.0,
        probe_every_min=15.0, stall_chunks=3, after_log=None,
        after_text="driver end")
    d = bd.Driver(args, [LISTINGS], 7.0)
    walked: list[str] = []
    chunks = iter([(0, {"entities_to_deepen": 50, "seed_before": "s1"}, {}),
                   (0, {"entities_to_deepen": 40, "seed_before": "s2"}, {})])

    def run_chunk(stage: bd.Stage) -> tuple[int, dict[str, Any], dict[str, Any]]:
        rc, plan, final = next(chunks)
        walked.append(str(plan["seed_before"]))
        return rc, plan, final

    d.sleep = lambda s: None  # type: ignore[method-assign]
    d.blocked = lambda: None  # type: ignore[method-assign]
    d.run_chunk = run_chunk  # type: ignore[method-assign]
    d.plan_chunk = lambda stage: {  # type: ignore[method-assign]
        "entities_to_deepen": 1611, "seed_before": "s3"}
    assert d.run() == 0
    assert walked == ["s1", "s2"]
    log = (tmp_path / "d.log").read_text()
    assert "1611 at the next hop, not walked" in log


def test_hop_limit_reached_only_on_a_new_seed_past_the_limit() -> None:
    p = bd.Progress(seeds=frozenset({"s1", "s2"}))
    assert bd.hop_limit_reached(LISTINGS, p, {"seed_before": "s3"})
    assert not bd.hop_limit_reached(LISTINGS, p, {"seed_before": "s2"})
    assert not bd.hop_limit_reached(STATS, p, {"seed_before": "s3"})


def test_hops_do_not_bound_a_stats_stage() -> None:
    p = bd.Progress()
    for i in range(5):
        p, out = bd.judge_chunk(STATS, p, 0,
                                {"targets": 50 - i, "seed_before": f"s{i}"}, {})
    assert out == "CONTINUE"


def test_breaker_count_decides_retry_or_recover() -> None:
    assert bd.after_breaker(1, 3) == "RETRY"
    assert bd.after_breaker(2, 3) == "RETRY"
    assert bd.after_breaker(3, 3) == "RECOVER"


@pytest.mark.parametrize("status,body,want", [
    (200, '{"events": []}', "OK"),
    (200, "<html>", "REFUSED"),
    (403, '{"error": {"code": 403, "reason": "challenge"}}', "CHALLENGE"),
    (403, "forbidden", "REFUSED"),
    (429, "", "REFUSED"),
    (None, "", "NO_ANSWER"),
])
def test_probe_classification(status: int | None, body: str, want: str) -> None:
    assert bd.classify_probe(status, body) == want


def test_recovery_resumes_on_ok_and_gives_up_at_the_limit() -> None:
    assert bd.recovery_step("OK", 0, 3600) == "RESUME"
    assert bd.recovery_step("OK", 99999, 3600) == "RESUME"
    assert bd.recovery_step("CHALLENGE", 900, 3600) == "WAIT"
    assert bd.recovery_step("CHALLENGE", 3600, 3600) == "GIVE_UP"
    assert bd.recovery_step("NO_ANSWER", 0, 0) == "GIVE_UP"


TODAY = "2026-10-23"


@pytest.mark.parametrize("cmd,want", [
    (f"python scripts/sofa/run_pipeline.py --date {TODAY}", True),
    ("python scripts/sofa/run_pipeline.py", True),
    (f"python scripts/sofa/run_pipeline.py --date {TODAY} --only SAMPLES", True),
    (f"python scripts/sofa/run_pipeline.py --date={TODAY} --from-stage OFFER", True),
    (f"python scripts/sofa/run_pipeline.py --date {TODAY} --only SHADOW", False),
    (f"run_pipeline.py --date {TODAY} --only SPORT_IDENTITY", False),
    (f"python scripts/sofa/run_pipeline.py --date {TODAY} --from-stage COUPON", False),
    ("python scripts/sofa/run_pipeline.py --date 2026-10-22", False),
    ("python scripts/sofa/shadow_daily.py", False),
])
def test_todays_build(cmd: str, want: bool) -> None:
    assert bd.is_todays_build(cmd, TODAY) is want


def test_blockers_and_yield_to_build() -> None:
    build = f"python scripts/sofa/run_pipeline.py --date {TODAY}"
    assert bd.blocking_reason([build], TODAY, yield_to_build=False) is None
    assert bd.blocking_reason([build], TODAY, yield_to_build=True) is not None
    rebuild = "python scripts/sofa/rebuild_day.py --date 2026-10-23"
    assert bd.blocking_reason([rebuild], TODAY, False) == "rebuild_day.py"
    settle = "python scripts/sofa/run_pipeline.py --date 2026-10-22 --only SETTLE"
    assert bd.blocking_reason([settle], TODAY, False) == "--only SETTLE"
    shadow_settle = "run_pipeline.py --date 2026-10-22 --only SHADOW_SETTLE"
    assert bd.blocking_reason([shadow_settle], TODAY, False) == "--only SHADOW_SETTLE"
    # the driver's own command line never blocks it
    me = "python scripts/sofa/backfill_driver.py --log rebuild_day.py.log"
    assert bd.blocking_reason([me], TODAY, True) is None


def test_plan_file_defaults_and_refusals() -> None:
    stages, chunk = bd.load_plan({"chunk_minutes": 5, "stages": [
        {"name": "l", "args": [bd.LISTINGS, "--sport", "tennis"]},
        {"args": [bd.STATS, "--sport", "tennis"]},
        {"name": "l0", "args": [bd.LISTINGS], "max_hops": None},
    ]}, max_hops=2)
    assert chunk == 5.0
    assert stages[0].left_key == "entities_to_deepen" and stages[0].max_hops == 2
    assert stages[1].left_key == "targets" and stages[1].max_hops is None
    assert stages[1].name == "stage 2"
    assert stages[2].max_hops is None
    for bad in ({}, {"stages": [{"args": ["scripts/sofa/rebuild_day.py"]}]},
                {"stages": [{"args": [bd.STATS, "--max-minutes", "3"]}]}):
        with pytest.raises(ValueError):
            bd.load_plan(bad, 2)


def test_presets_match_the_2026_10_22_night() -> None:
    night = bd.preset("night", 2)
    assert [s.name for s in night][:5] == [
        "listings hockey", "listings volleyball", "listings basketball",
        "listings tennis", "listings football"]
    assert night[-1].args[0] == bd.LINEUPS
    assert all(s.max_hops == 2 for s in night if bd.is_listings(s))
    with pytest.raises(ValueError):
        bd.preset("nope", 2)


def _driver(tmp_path: Path, chunks: list[tuple[int, dict[str, Any], dict[str, Any]]],
            probes: list[bd.Probe], **kw: Any) -> tuple[bd.Driver, list[float]]:
    args = bd.argparse.Namespace(
        log=str(tmp_path / "d.log"), yield_to_build=False, blocker_wait_min=5.0,
        breaker_wait_min=15.0, breaker_stops=3, recover_hours=1.0,
        probe_every_min=15.0, stall_chunks=3, after_log=None,
        after_text="driver end", **kw)
    d = bd.Driver(args, [STATS], 7.0)
    sleeps: list[float] = []
    it, pr = iter(chunks), iter(probes)
    d.sleep = sleeps.append  # type: ignore[method-assign]
    d.blocked = lambda: None  # type: ignore[method-assign]
    d.run_chunk = lambda stage: next(it)  # type: ignore[method-assign]
    d.probe = lambda: next(pr)  # type: ignore[method-assign]
    return d, sleeps


def test_a_challenge_stop_waits_for_the_bridge_and_resumes(tmp_path: Path) -> None:
    br = (2, {"targets": 9}, OPEN)
    d, sleeps = _driver(tmp_path, [br, br, br, (0, {"targets": 0}, {})],
                        ["CHALLENGE", "CHALLENGE", "OK"])
    assert d.run() == 0
    log = (tmp_path / "d.log").read_text()
    assert "BREAKER" in log and "resuming" in log and "STOP" not in log
    assert sleeps == [900.0, 900.0, 900.0, 900.0]  # two retries, two probes


def test_a_bridge_that_never_answers_stops(tmp_path: Path) -> None:
    br = (2, {"targets": 9}, OPEN)
    d, _ = _driver(tmp_path, [br, br, br],
                   ["CHALLENGE", "CHALLENGE", "CHALLENGE", "CHALLENGE", "CHALLENGE"])
    assert d.run() == 2
    assert "STOP: circuit open 3 times" in (tmp_path / "d.log").read_text()


def test_dry_run_prints_the_preset(capsys: pytest.CaptureFixture[str],
                                   tmp_path: Path) -> None:
    rc = bd.main(["--preset", "listings", "--log", str(tmp_path / "x.log"),
                  "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "listings football" in out and "--max-minutes 7" in out
    assert not (tmp_path / "x.log").exists()


def test_day_status_warns_on_a_recent_driver_stop(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from scripts.sofa.day_status import OK, WARN, backfill_check

    now = datetime(2026, 10, 23, 8, 0, tzinfo=UTC)
    assert backfill_check(tmp_path, now).status == OK  # no backfill dir
    d = tmp_path / "backfill"
    d.mkdir()
    (d / "old.log").write_text(
        "2026-10-22T19:45:29Z STOP: circuit open 3 times in a row\n")  # 12.2 h
    (d / "night.log").write_text(
        "2026-10-23T01:00:00Z stats tennis chunk 4: rc=2 left=9 final={}\n"
        "2026-10-23T01:00:01Z BREAKER: circuit open 3 times in a row - probing\n")
    assert backfill_check(tmp_path, now).status == OK
    with (d / "night.log").open("a") as f:
        f.write("2026-10-23T07:00:01Z STOP: circuit open 3 times in a row and "
                "the bridge did not answer in 6 h\n")
    c = backfill_check(tmp_path, now)
    assert c.status == WARN and "night.log" in c.detail and "60 min" in c.detail
    with (d / "night.log").open("a") as f:
        f.write("2026-10-23T07:30:00Z driver start (11 stages, chunk 7 min)\n")
    c = backfill_check(tmp_path, now)
    assert c.status == OK and "1 restarted" in c.detail
