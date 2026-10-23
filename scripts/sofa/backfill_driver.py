#!/usr/bin/env python3
"""Run history backfills stage by stage in --max-minutes chunks - data only.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_driver.py \\
        (--preset night | --plan <plan.json>) --log runs/sofa/backfill/<name>.log \\
        [--chunk-minutes 7] [--max-hops 2] [--recover-hours 6] [--yield-to-build] \\
        [--after-log <log> --after-text "driver end"] [--start-at <stage>] [--dry-run]

Promoted from the ad-hoc runs/sofa/backfill/{backfill,night}_driver.py of
2026-10-22. It runs backfill_listings.py / backfill_event_stats.py /
backfill_football_lineups.py (or any script that prints the same JSON lines:
a plan line first, a `"final": true` line last) and never a rebuild, SHEET,
refit or anything that changes what prints.

A stage ends when
- its plan line says nothing is left (`left_key` == 0, or no plan count and
  exit 0) - DONE;
- a listings stage has seen more than `max_hops` seeds: backfill_listings.py
  advances its seed after every run that walks its whole queue, so each
  completed run opens one more hop of opponents and the queue never empties
  by itself - DONE (hops);
- `stall_chunks` chunks in a row leave the same count - DONE (no progress);
- `stall_chunks` chunks in a row fail without a circuit-open (a crash) -
  SKIPPED.

A circuit-open exit (2 with `"circuit_open": true`) waits `--breaker-wait-min`
and retries; `--breaker-stops` in a row mean the bridge is refusing. On
2026-10-22 that was a Sofascore 403 "challenge" (the tab's x-captcha), which
the page clears by itself minutes to hours later. So instead of dying the
driver then probes the bridge (one live request, as check_bridge.py does)
every `--probe-every-min` for up to `--recover-hours` and resumes the stage
when Sofascore answers 200 with JSON. Only after that does it log `STOP:` and
exit 2 (day_status.py WARNs on a `STOP` in a driver log of the last 12 h).
It never reloads a tab or refreshes a token (CLAUDE.md, the bridge).

Before every chunk it waits while a blocker runs (a rebuild, settle, record,
line-evidence refresh, regrade: never two writers beside those) and, with
`--yield-to-build`, while a run_pipeline.py of today runs any of BOARD ..
SHEET (the morning build shares the bridge; the loops' own SHADOW / CS2 /
SPORT_IDENTITY steps do not block).

One driver per log: `<log>.lock` beside it (flock) refuses a second one.

Plan file: {"chunk_minutes": 7, "stages": [{"name": "listings hockey",
"args": ["scripts/sofa/backfill_listings.py", "--sport", "hockey", ...],
"left_key": "entities_to_deepen", "max_hops": 2}, ...]}; `left_key` defaults
from the script (listings -> entities_to_deepen, else targets), `max_hops`
applies to listings stages only (default --max-hops).

Exit 0 every stage done, 1 another driver holds the lock or a stage was
skipped, 2 STOP (bridge refused past --recover-hours) or a bad plan.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shlex
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

REPO = Path(__file__).resolve().parents[2]

LISTINGS = "scripts/sofa/backfill_listings.py"
STATS = "scripts/sofa/backfill_event_stats.py"
LINEUPS = "scripts/sofa/backfill_football_lineups.py"

# Writers that must not share the DB and the bridge with a backfill.
BLOCKERS: tuple[str, ...] = (
    "rebuild_day.py", "record_results.py", "refresh_line_evidence.py",
    "resettle_sweep.py", "regrade_settled.py", "--only SETTLE",
    "--only SHADOW_SETTLE", "--only CS2_SETTLE")
# The morning build: the stages that ask the bridge for today's coupon.
BUILD_STAGES = frozenset({"BOARD", "RESOLVE", "OFFER", "SAMPLES", "SHEET"})

PROBE_URL = "https://api.sofascore.com/api/v1/sport/football/events/live"
PROBE_TIMEOUT_S = 60.0

Probe = Literal["OK", "CHALLENGE", "REFUSED", "NO_ANSWER"]
Outcome = Literal["CONTINUE", "BREAKER", "FAILED", "DONE", "DONE_HOPS",
                  "DONE_STALL", "SKIPPED"]


@dataclass(frozen=True)
class Stage:
    name: str
    args: tuple[str, ...]
    left_key: str
    max_hops: int | None = None


@dataclass(frozen=True)
class Progress:
    """One stage's state between chunks."""
    chunks: int = 0
    last_left: int | None = None
    stalls: int = 0
    failures: int = 0
    seeds: frozenset[str] = field(default_factory=frozenset)


def default_left_key(args: Sequence[str]) -> str:
    return "entities_to_deepen" if args and args[0].endswith(
        "backfill_listings.py") else "targets"


def is_listings(stage: Stage) -> bool:
    return bool(stage.args) and stage.args[0].endswith("backfill_listings.py")


def preset(name: str, max_hops: int) -> list[Stage]:
    """The stage lists the 2026-10-22 drivers ran."""
    listings = [
        Stage(f"listings {sp}", (LISTINGS, "--sport", sp, "--days", "730",
                                 "--recent-days", "30"),
              "entities_to_deepen", max_hops)
        for sp in ("hockey", "volleyball", "basketball", "tennis", "football")]
    stats = (
        [Stage(f"stats+lineups {sp}", (STATS, "--sport", sp, "--days", "365",
                                       "--with-lineups"), "targets")
         for sp in ("hockey", "volleyball", "basketball")]
        + [Stage("stats tennis", (STATS, "--sport", "tennis", "--days", "365"),
                 "targets"),
           Stage("stats football", (STATS, "--sport", "football", "--days", "365"),
                 "targets"),
           Stage("lineups football", (LINEUPS, "--days", "365"), "targets")])
    presets = {"listings": listings, "stats": stats, "night": listings + stats}
    if name not in presets:
        raise ValueError(f"unknown preset {name!r}; one of {sorted(presets)}")
    return presets[name]


def load_plan(doc: dict[str, Any], max_hops: int) -> tuple[list[Stage], float | None]:
    """Stages (and an optional chunk length) from a plan file's JSON."""
    raw = doc.get("stages")
    if not isinstance(raw, list) or not raw:
        raise ValueError("plan has no 'stages' list")
    stages: list[Stage] = []
    for i, s in enumerate(raw):
        if not isinstance(s, dict):
            raise ValueError(f"stage #{i} is not an object")
        args = s.get("args")
        if not isinstance(args, list) or not args or not all(
                isinstance(a, str) for a in args):
            raise ValueError(f"stage #{i} needs 'args', a list of strings")
        if not args[0].startswith("scripts/sofa/backfill_"):
            raise ValueError(f"stage #{i}: {args[0]} is not a backfill script")
        if "--max-minutes" in args:
            raise ValueError(f"stage #{i}: --max-minutes is the driver's")
        stage = Stage(str(s.get("name") or f"stage {i + 1}"), tuple(args),
                      str(s.get("left_key") or default_left_key(args)))
        if is_listings(stage):
            hops = s.get("max_hops", max_hops)
            stage = replace(stage, max_hops=None if hops is None else int(hops))
        stages.append(stage)
    chunk = doc.get("chunk_minutes")
    return stages, float(chunk) if isinstance(chunk, (int, float)) else None


def parse_output(stdout: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """(plan line, final line) of a backfill script's stdout."""
    plan: dict[str, Any] = {}
    final: dict[str, Any] = {}
    for ln in stdout.splitlines():
        try:
            j = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(j, dict):
            continue
        if j.get("final"):
            final = j
        elif not plan:
            plan = j
    return plan, final


def hop_limit_reached(stage: Stage, progress: Progress,
                      plan: dict[str, Any]) -> bool:
    """Would a chunk with this (dry-run) plan open a hop past the stage's
    limit? Asked before the chunk runs: a chunk's own plan line comes after it
    has already walked that hop (2026-10-23 audit, "740 left")."""
    seed = plan.get("seed_before")
    return (is_listings(stage) and stage.max_hops is not None
            and isinstance(seed, str) and seed not in progress.seeds
            and len(progress.seeds) + 1 > stage.max_hops)


def judge_chunk(stage: Stage, progress: Progress, rc: int,
                plan: dict[str, Any], final: dict[str, Any],
                stall_chunks: int = 3) -> tuple[Progress, Outcome]:
    """What one chunk's exit means for its stage. Pure - the tests hold it."""
    p = replace(progress, chunks=progress.chunks + 1)
    if rc == 2 and final.get("circuit_open") is True:
        return p, "BREAKER"
    if rc not in (0, 1) or (rc == 1 and not plan):
        failures = p.failures + 1
        p = replace(p, failures=failures)
        return p, "SKIPPED" if failures >= stall_chunks else "FAILED"
    p = replace(p, failures=0)
    seed = plan.get("seed_before")
    if isinstance(seed, str):
        p = replace(p, seeds=p.seeds | {seed})
    raw = plan.get(stage.left_key)
    left = int(raw) if isinstance(raw, (int, float)) else None
    if stage.max_hops is not None and len(p.seeds) > stage.max_hops:
        return p, "DONE_HOPS"
    if left == 0 or (left is None and rc == 0):
        return p, "DONE"
    stalls = p.stalls + 1 if p.chunks > 1 and left == p.last_left else 0
    p = replace(p, stalls=stalls, last_left=left)
    if stalls >= stall_chunks:
        return p, "DONE_STALL"
    return p, "CONTINUE"


def after_breaker(breakers: int, limit: int) -> Literal["RETRY", "RECOVER"]:
    """`breakers` circuit-open exits in a row: wait and retry, or probe."""
    return "RECOVER" if breakers >= limit else "RETRY"


def classify_probe(status: int | None, body: str) -> Probe:
    """One live request through the bridge: did Sofascore answer?"""
    if status is None:
        return "NO_ANSWER"
    if status == 200:
        try:
            json.loads(body)
        except ValueError:
            return "REFUSED"
        return "OK"
    if status == 403 and "challenge" in body.lower():
        return "CHALLENGE"
    return "REFUSED"


def recovery_step(verdict: Probe, waited_s: float, max_s: float
                  ) -> Literal["RESUME", "WAIT", "GIVE_UP"]:
    if verdict == "OK":
        return "RESUME"
    return "GIVE_UP" if waited_s >= max_s else "WAIT"


def _flag(tokens: Sequence[str], name: str) -> str | None:
    for i, t in enumerate(tokens):
        if t == name and i + 1 < len(tokens):
            return tokens[i + 1]
        if t.startswith(name + "="):
            return t.split("=", 1)[1]
    return None


def is_todays_build(command: str, today: str) -> bool:
    """A run_pipeline.py command line that runs a stage of BOARD .. SHEET
    for `today` (no --date is today)."""
    if "run_pipeline.py" not in command:
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    date = _flag(tokens, "--date")
    if date is not None and date != today:
        return False
    only = _flag(tokens, "--only")
    if only is not None:
        return only in BUILD_STAGES
    start = _flag(tokens, "--from-stage")
    if start is not None:
        return start in BUILD_STAGES
    return True


def blocking_reason(commands: Sequence[str], today: str,
                    yield_to_build: bool,
                    blockers: Sequence[str] = BLOCKERS) -> str | None:
    """Why the next chunk must wait, from `ps` command lines (None: go)."""
    lines = [c for c in commands if "backfill_driver" not in c]
    for b in blockers:
        if any(b in c for c in lines):
            return b
    if yield_to_build:
        for c in lines:
            if is_todays_build(c, today):
                return "today's build (run_pipeline.py)"
    return None


# ---------------------------------------------------------------- effects


class Driver:
    def __init__(self, args: argparse.Namespace, stages: list[Stage],
                 chunk_minutes: float) -> None:
        self.a = args
        self.stages = stages
        self.chunk = chunk_minutes
        self.log_path = Path(args.log)
        self.env = {**os.environ, "PYTHONPATH": "src:."}
        self.sleep: Callable[[float], None] = time.sleep

    def log(self, msg: str) -> None:
        line = f"{datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}"
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(line, flush=True)

    def blocked(self) -> str | None:
        out = subprocess.run(["ps", "-axo", "command"], capture_output=True,
                             text=True, check=False).stdout
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        return blocking_reason(out.splitlines(), today, self.a.yield_to_build)

    def plan_chunk(self, stage: Stage) -> dict[str, Any]:
        """The plan line of the stage's --dry-run (network-free, the cache
        read-only, the seed not recorded - backfill_listings.py)."""
        p = subprocess.run([sys.executable, *stage.args, "--dry-run"], cwd=REPO,
                           env=self.env, capture_output=True, text=True,
                           check=False)
        return parse_output(p.stdout)[0]

    def run_chunk(self, stage: Stage) -> tuple[int, dict[str, Any], dict[str, Any]]:
        cmd = [sys.executable, *stage.args, "--max-minutes", f"{self.chunk:g}"]
        p = subprocess.run(cmd, cwd=REPO, env=self.env, capture_output=True,
                           text=True, check=False)
        plan, final = parse_output(p.stdout)
        if p.returncode not in (0, 1, 2) or (not plan and p.returncode):
            self.log(f"   stderr tail: {p.stderr.strip()[-400:]}")
        return p.returncode, plan, final

    def probe(self) -> Probe:
        from bet.sofa.bridge_transport import BrowserBridgeTransport
        from bet.sofa.errors import ProviderError, TransportError
        try:
            resp = BrowserBridgeTransport().get(PROBE_URL, timeout=PROBE_TIMEOUT_S)
        except (ProviderError, TransportError, OSError):
            return "NO_ANSWER"
        return classify_probe(resp.status_code, resp.text)

    def recover(self) -> bool:
        max_s = self.a.recover_hours * 3600.0
        every = self.a.probe_every_min * 60.0
        self.log(f"BREAKER: circuit open {self.a.breaker_stops} times in a row "
                 f"- probing the bridge every {self.a.probe_every_min:g} min for "
                 f"up to {self.a.recover_hours:g} h")
        waited = 0.0
        while True:
            verdict = self.probe() if max_s > 0 else "NO_ANSWER"
            step = recovery_step(verdict, waited, max_s)
            self.log(f"   probe after {waited / 60:.0f} min: {verdict} -> {step}")
            if step == "RESUME":
                return True
            if step == "GIVE_UP":
                return False
            self.sleep(every)
            waited += every

    def wait_for_after_log(self) -> None:
        if not self.a.after_log:
            return
        path = Path(self.a.after_log)
        self.log(f"waiting for {self.a.after_text!r} in {path}")
        while True:
            try:
                if self.a.after_text in path.read_text(encoding="utf-8"):
                    return
            except OSError:
                pass
            self.sleep(300)

    def run(self) -> int:
        self.wait_for_after_log()
        self.log(f"driver start ({len(self.stages)} stages, chunk "
                 f"{self.chunk:g} min, yield to build "
                 f"{'on' if self.a.yield_to_build else 'off'})")
        breakers = 0
        skipped = 0
        for stage in self.stages:
            progress = Progress()
            while True:
                b = self.blocked()
                if b:
                    self.log(f"{stage.name}: waiting, {b} is running")
                    self.sleep(self.a.blocker_wait_min * 60)
                    continue
                if (is_listings(stage) and stage.max_hops is not None
                        and len(progress.seeds) >= stage.max_hops):
                    ahead = self.plan_chunk(stage)
                    if hop_limit_reached(stage, progress, ahead):
                        raw = ahead.get(stage.left_key)
                        progress = replace(progress, last_left=int(raw) if isinstance(
                            raw, (int, float)) else None)
                        self.log(f"{stage.name}: "
                                 f"{describe('DONE_HOPS', stage, progress)}")
                        break
                rc, plan, final = self.run_chunk(stage)
                progress, outcome = judge_chunk(stage, progress, rc, plan, final,
                                                self.a.stall_chunks)
                self.log(f"{stage.name} chunk {progress.chunks}: rc={rc} "
                         f"left={plan.get(stage.left_key)} "
                         f"final={json.dumps(final)[:300]}")
                if outcome == "BREAKER":
                    breakers += 1
                    if after_breaker(breakers, self.a.breaker_stops) == "RETRY":
                        self.sleep(self.a.breaker_wait_min * 60)
                        continue
                    if not self.recover():
                        self.log(f"STOP: circuit open {breakers} times in a row "
                                 f"and the bridge did not answer in "
                                 f"{self.a.recover_hours:g} h")
                        return 2
                    self.log(f"{stage.name}: bridge answers - resuming")
                    breakers = 0
                    continue
                breakers = 0
                if outcome == "FAILED":
                    self.sleep(60)
                    continue
                if outcome == "CONTINUE":
                    continue
                if outcome == "SKIPPED":
                    skipped += 1
                self.log(f"{stage.name}: {describe(outcome, stage, progress)}")
                break
        self.log("driver end: all stages done"
                 + (f" ({skipped} skipped)" if skipped else ""))
        return 1 if skipped else 0


def describe(outcome: Outcome, stage: Stage, p: Progress) -> str:
    if outcome == "DONE_HOPS":
        return (f"DONE ({stage.max_hops} hops, {p.last_left} at the next hop, "
                "not walked)")
    if outcome == "DONE_STALL":
        return f"DONE (no progress in {p.stalls} chunks, {p.last_left} left)"
    if outcome == "SKIPPED":
        return f"SKIPPED (failed {p.failures} chunks in a row)"
    return "DONE"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--preset", choices=("listings", "stats", "night"))
    src.add_argument("--plan", help="JSON plan file (see the module docstring)")
    ap.add_argument("--log", required=True, help="driver log (lock: <log>.lock)")
    ap.add_argument("--chunk-minutes", type=float, default=None,
                    help="--max-minutes of each chunk (default: plan's, else 7)")
    ap.add_argument("--max-hops", type=int, default=2,
                    help="listings stages: stop after this many seed hops")
    ap.add_argument("--stall-chunks", type=int, default=3)
    ap.add_argument("--breaker-wait-min", type=float, default=15.0)
    ap.add_argument("--breaker-stops", type=int, default=3,
                    help="circuit-open exits in a row before probing")
    ap.add_argument("--recover-hours", type=float, default=6.0,
                    help="probe the bridge this long before STOP (0: stop at once)")
    ap.add_argument("--probe-every-min", type=float, default=15.0)
    ap.add_argument("--blocker-wait-min", type=float, default=5.0)
    ap.add_argument("--yield-to-build", action="store_true",
                    help="also wait while today's run_pipeline.py BOARD..SHEET runs")
    ap.add_argument("--after-log", default=None,
                    help="start only once --after-text appears in this log")
    ap.add_argument("--after-text", default="driver end")
    ap.add_argument("--start-at", default=None, help="skip stages before this name")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the stages and exit")
    args = ap.parse_args(argv)

    try:
        if args.plan:
            doc = json.loads(Path(args.plan).read_text(encoding="utf-8"))
            if not isinstance(doc, dict):
                raise ValueError("plan is not a JSON object")
            stages, plan_chunk = load_plan(doc, args.max_hops)
        else:
            stages, plan_chunk = preset(args.preset, args.max_hops), None
        if args.start_at:
            names = [s.name for s in stages]
            if args.start_at not in names:
                raise ValueError(f"--start-at {args.start_at!r} not in {names}")
            stages = stages[names.index(args.start_at):]
    except (OSError, ValueError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2
    chunk = args.chunk_minutes or plan_chunk or 7.0
    if args.dry_run:
        for s in stages:
            hops = f" (max {s.max_hops} hops)" if s.max_hops is not None else ""
            print(f"{s.name}: {' '.join(s.args)} --max-minutes {chunk:g} "
                  f"[{s.left_key}]{hops}")
        return 0
    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lock = log_path.with_suffix(log_path.suffix + ".lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(f"another driver holds {lock.name} - exiting", file=sys.stderr)
        return 1
    return Driver(args, stages, chunk).run()


if __name__ == "__main__":
    sys.exit(main())
