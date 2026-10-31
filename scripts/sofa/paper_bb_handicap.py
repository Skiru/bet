#!/usr/bin/env python3
"""The basketball handicap PAPER test, one sport day at a time (operator's go
2026-10-31; the frozen rule: `bet.sofa.paper_bb_handicap`; pre-registration
docs/sofa/evidence/paper_bb_handicap_preregistration_2026-10-31.md).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/paper_bb_handicap.py --date <D> \\
        [--pending] [--runs-dir runs/sofa] [--odds-cache DIR] [--no-fetch]
    ... --report            # the forward summary in Polish (no network)
    ... --capture --date <D> [--loop]   # bet365 before tip-off (the forward data)

Day D is the measured sports' day window (sport_identity.day_window): the
games of SHADOW's basketball files D and D+1 starting in [end(D-1), end(D)).

Where bet365 comes from (pb.PRESTART_FROM splits it):
- from PRESTART_FROM (forward): the capture. `--capture --date D` asks
  `/event/{id}/odds/1/all` for every pinned basketball game of D's window
  (SPORT_IDENTITY's sport_fixtures.json of D and D+1) not started and
  starting within CAPTURE_HORIZON_H (3 h); `--loop` repeats every
  CAPTURE_EVERY_MIN (15 min) until the window ends (one loop a day: pid file
  prestart/<D>/capture.pid; shadow_daily.py starts it). Every capture is
  kept: prestart/<D>/<id>.json {"captures": [{fetched_at_utc, payload}]},
  each payload trimmed to pb.CAPTURE_MARKETS. The day's run reads only the
  newest capture fetched before the game's start (pb.start_clock); a game
  without one is excluded, counted `no_b365_prestart`. Nothing is asked
  after the game.
- before it (backtest): a SETTLED game is asked once after the game - as
  the backtest read it, a look-ahead - and cached in <odds-cache>/<id>.json
  (an answer with no market or a 404 is cached too and never asked again;
  an error writes nothing).
A game not yet settled is PENDING. --pending
also re-runs every earlier day file still PARTIAL (the daily step:
`--date <D-1> --pending`).

Writes only runs/sofa/paper/bb_handicap/: <D>.json (idempotent: the same
inputs give the same bytes) and ledger.json (rebuilt from every day file,
forward and backtest apart). Nothing the coupon reads. No stake, no placement.

Exit 0 OK, 1 PARTIAL (a game pending or a fetch gap), 2 FAILED.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import paper_bb_handicap as pb  # noqa: E402
from bet.sofa import shadow, sport_day, timeutil  # noqa: E402
from bet.sofa import sport_identity as si  # noqa: E402
from bet.sofa.coupon_sports import pinned_seed  # noqa: E402
from bet.sofa.errors import CircuitOpenError, ProviderError  # noqa: E402

SPORT: Literal["basketball"] = "basketball"
PAPER_DIR = Path("paper") / "bb_handicap"
LEDGER_FILE = "ledger.json"
PRESTART_DIR = "prestart"
CAPTURE_PID = "capture.pid"
CAPTURE_LOG = "capture.log"
# A game captured less than this ago is not asked again (a hand run beside
# the loop must not double the requests).
CAPTURE_MIN_GAP = timedelta(minutes=pb.CAPTURE_EVERY_MIN - 1)
# SHADOW_SETTLE gives a game up after 7 days (settle_shadow.GIVE_UP_AFTER);
# a game still not terminal a day after that is no longer pending.
PENDING_GIVE_UP = timedelta(days=8)


class OddsClient(Protocol):
    def event_odds(self, id: int) -> Any | None: ...


def paper_dir(runs_dir: str) -> Path:
    return Path(runs_dir) / PAPER_DIR


def next_day(date: str) -> str:
    return (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _load_settled(runs_dir: str, src: str) -> dict[str, dict[str, Any]]:
    path = shadow.shadow_day_dir(runs_dir, SPORT, src) / shadow.SETTLED_FILE
    if not path.exists():
        return {}
    events: dict[str, dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))[
        "events"
    ]
    return events


def _snapshot_handicaps(runs_dir: str, src: str) -> dict[str, Any]:
    """Superbet events of file `src` with a full-game handicap at their last
    pre-start snapshot."""
    path = shadow.shadow_day_dir(runs_dir, SPORT, src) / shadow.SNAPSHOTS_FILE
    if not path.exists():
        return {}
    events = shadow.latest_pre_kickoff(sport_day.load_snapshots(path))
    return {
        eid: ev
        for eid, ev in events.items()
        if any(
            ln.family == pb.FAMILY and ln.period == pb.PERIOD
            for ln in ev.sides.values()
        )
    }


def collect(runs_dir: str, date: str, now: datetime) -> dict[str, Any]:
    """The day's games: settled records to evaluate (with their file and
    position), pending games, and counts of the rest."""
    lo, hi = si.day_window(date)
    pinned = {
        **pinned_seed(runs_dir, SPORT, date),
        **pinned_seed(runs_dir, SPORT, next_day(date)),
    }
    chosen: dict[str, tuple[str, int, dict[str, Any] | None, Any]] = {}
    files = 0
    for src in (date, next_day(date)):
        settled = _load_settled(runs_dir, src)
        snaps = _snapshot_handicaps(runs_dir, src)
        files += bool(settled) + bool(snaps)
        for idx, (eid, record) in enumerate(settled.items()):
            have = chosen.get(eid)
            if have is None or (have[2] or {}).get("state") != "SETTLED":
                chosen[eid] = (src, idx, record, snaps.get(eid))
        for eid, ev in snaps.items():
            if eid not in chosen:
                chosen[eid] = (src, len(settled), None, ev)
    settled_rows: list[tuple[str, int, dict[str, Any]]] = []
    pending: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for eid, (src, idx, rec, snap) in chosen.items():
        kickoff_raw = str(
            (rec or {}).get("kickoff_utc") or (snap.kickoff_utc if snap else "")
        )
        if not kickoff_raw:
            continue
        kickoff = _utc(kickoff_raw)
        if not lo <= kickoff < hi:
            continue
        state = (rec or {}).get("state")
        if state == "SETTLED":
            if not pb.handicap_rows(rec or {}):
                counts["no_handicap_row"] += 1
                continue
            if not (rec or {}).get("sofascore_event_id"):
                counts["no_sofascore_id"] += 1
                continue
            settled_rows.append((src, idx, rec or {}))
            continue
        if rec is None and snap is None:
            continue
        if state is not None and shadow.is_terminal(state):
            counts[f"excluded:{shadow.base_state(state)}"] += 1
            continue
        if rec is not None and not pb.handicap_rows(rec) and snap is None:
            counts["no_handicap_row"] += 1
            continue
        if now - kickoff > PENDING_GIVE_UP:
            counts[f"excluded:stale_{state or 'NO_SETTLE_RECORD'}"] += 1
            continue
        lines = sorted(
            (
                {"t1_line": ln.line, "side": ln.side, "odds": ln.odds}
                for ln in (snap.sides.values() if snap else [])
                if ln.family == pb.FAMILY and ln.period == pb.PERIOD
            ),
            key=lambda d: (d["t1_line"], d["side"]),
        )
        pin = pinned.get(eid) or {}
        pending.append(
            {
                "superbet_event_id": eid,
                "source_date": src,
                "match": (rec or {}).get("match_name")
                or (snap.match_name if snap else None),
                "kickoff_utc": kickoff_raw,
                "state": state or "NOT_SETTLED",
                "sofascore_event_id": (rec or {}).get("sofascore_event_id")
                or pin.get("sofascore_event_id"),
                "superbet_handicap_last_snapshot": lines,
            }
        )
    settled_rows.sort(key=lambda r: (r[0], r[1]))
    pending.sort(key=lambda p: (p["kickoff_utc"], p["superbet_event_id"]))
    return {
        "settled": settled_rows,
        "pending": pending,
        "counts": counts,
        "files": files,
        "window": [si.iso(lo), si.iso(hi)],
    }


def read_cached(cache: Path, event_id: int) -> tuple[bool, Any]:
    path = cache / f"{event_id}.json"
    if not path.exists():
        return False, None
    return True, json.loads(path.read_text(encoding="utf-8"))


def fetch_odds(
    ids: Sequence[int],
    cache: Path,
    client_factory: Callable[[], OddsClient] | None,
) -> tuple[dict[int, Any], list[int]]:
    """Each id's payload, cached first; (payloads, ids not had)."""
    out: dict[int, Any] = {}
    gaps: list[int] = []
    client: OddsClient | None = None
    stopped = False
    for ev in ids:
        ok, payload = read_cached(cache, ev)
        if ok:
            out[ev] = payload
            continue
        if client_factory is None or stopped:
            gaps.append(ev)
            continue
        if client is None:
            client = client_factory()
        try:
            payload = client.event_odds(ev)
        except CircuitOpenError:
            stopped = True
            gaps.append(ev)
            continue
        except ProviderError as exc:
            if "403" in str(exc) or "429" in str(exc):
                stopped = True
            gaps.append(ev)
            continue
        cache.mkdir(parents=True, exist_ok=True)
        tmp = cache / f"{ev}.json.tmp"
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(cache / f"{ev}.json")
        out[ev] = payload
    return out, gaps


def _write_json(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(doc, indent=1, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def run_day(
    runs_dir: str,
    date: str,
    cache: Path,
    client_factory: Callable[[], OddsClient] | None,
    now: datetime,
) -> dict[str, Any]:
    day = collect(runs_dir, date, now)
    prestart = pb.uses_prestart(date)
    ids = [int(rec["sofascore_event_id"]) for _, _, rec in day["settled"]]
    gaps: list[int] = []
    payloads: dict[int, Any] = {}
    fetched_at: dict[int, str] = {}
    no_prestart: list[int] = []
    if prestart:
        for _, _, rec in day["settled"]:
            ev = int(rec["sofascore_event_id"])
            cap = pb.prestart_payload(
                load_captures(runs_dir, date, ev), pb.start_clock(rec)
            )
            if cap is None:
                no_prestart.append(ev)
                continue
            payloads[ev] = cap.get("payload")
            fetched_at[ev] = str(cap["fetched_at_utc"])
    else:
        payloads, gaps = fetch_odds(ids, cache, client_factory)
    source = pb.B365_PRESTART if prestart else pb.B365_POST_MATCH
    candidates: list[dict[str, Any]] = []
    counts: Counter[str] = Counter(day["counts"])
    for src, idx, rec in day["settled"]:
        ev = int(rec["sofascore_event_id"])
        if ev in no_prestart:
            counts["no_b365_prestart"] += 1
            continue
        if ev not in payloads:
            counts["fetch_gap"] += 1
            continue
        status, cands = pb.evaluate_event(rec, payloads[ev], src, idx)
        counts[status.lower()] += 1
        for c in cands:
            c["b365_source"] = source
            c["b365_fetched_at_utc"] = fetched_at.get(ev)
        candidates.extend(cands)
    candidates.sort(key=lambda c: tuple(c["order"]))
    selected = [c for c in candidates if c["selected"]]
    status = (
        "FAILED"
        if not day["files"]
        else ("PARTIAL" if day["pending"] or gaps else "OK")
    )
    return {
        "rule_id": pb.RULE_ID,
        "frozen_at": pb.FROZEN_AT,
        "t": pb.T,
        "date": date,
        "section": pb.section_of(date),
        "window": day["window"],
        "b365_source": source,
        "status": status,
        "counts": dict(sorted(counts.items())),
        "selections": len(selected),
        "won": sum(c["outcome"] == "WIN" for c in selected),
        "candidates": candidates,
        "pending": day["pending"],
        "fetch_gaps": sorted(gaps),
        "no_b365_prestart": sorted(no_prestart),
    }


# --- the pre-start capture -------------------------------------------------------


def prestart_dir(runs_dir: str, date: str) -> Path:
    return paper_dir(runs_dir) / PRESTART_DIR / date


def _prev_day(date: str) -> str:
    return (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )


def load_captures(runs_dir: str, date: str, event_id: int) -> list[dict[str, Any]]:
    """Every capture of a game (its day's directory first, then the
    neighbours: a game moved across a window edge keeps its captures)."""
    out: list[dict[str, Any]] = []
    for d in (date, _prev_day(date), next_day(date)):
        path = prestart_dir(runs_dir, d) / f"{event_id}.json"
        if path.exists():
            out.extend(json.loads(path.read_text(encoding="utf-8"))["captures"])
    return out


def capture_targets(runs_dir: str, date: str, now: datetime) -> list[dict[str, Any]]:
    """Pinned basketball games of D's window not started and starting within
    the horizon; the start is the earlier of Superbet's and Sofascore's."""
    lo, hi = si.day_window(date)
    horizon = now + timedelta(hours=pb.CAPTURE_HORIZON_H)
    seen: dict[int, dict[str, Any]] = {}
    for d in (date, next_day(date)):
        path = Path(runs_dir) / d / "sport_fixtures.json"
        if not path.exists():
            continue
        try:
            fixtures = (
                json.loads(path.read_text(encoding="utf-8")).get("fixtures") or []
            )
        except ValueError:
            continue
        for f in fixtures:
            if f.get("sport") != SPORT or f.get("status") != "IDENTIFIED":
                continue
            if f.get("sofascore_event_id") is None:
                continue
            clock = pb.start_clock(f)
            if not clock:
                continue
            start = _utc(clock)
            if not (lo <= _utc(str(f["kickoff_utc"])) < hi and now < start <= horizon):
                continue
            seen[int(f["sofascore_event_id"])] = {
                "sofascore_event_id": int(f["sofascore_event_id"]),
                "superbet_event_id": str(f["superbet_event_id"]),
                "match": f.get("match_name"),
                "start_utc": clock,
            }
    return sorted(
        seen.values(), key=lambda t: (t["start_utc"], t["sofascore_event_id"])
    )


def capture_pass(
    runs_dir: str,
    date: str,
    client_factory: Callable[[], OddsClient],
    now: datetime,
    stamp: Callable[[], datetime] | None = None,
) -> Counter[str]:
    """One pass: ask each target once, append the capture (trimmed). Only a
    game not yet started at the pass's start is asked (capture_targets); each
    capture is stamped with the clock after its answer (`stamp`, default
    timeutil.now), so one landing after the start is never read as pre-start.
    A refusal stops the pass."""
    counts: Counter[str] = Counter()
    client: OddsClient | None = None
    out = prestart_dir(runs_dir, date)
    for t in capture_targets(runs_dir, date, now):
        ev = t["sofascore_event_id"]
        path = out / f"{ev}.json"
        doc: dict[str, Any] = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else {"sofascore_event_id": ev, "captures": []}
        )
        last = max((str(c["fetched_at_utc"]) for c in doc["captures"]), default="")
        if last and now - _utc(last) < CAPTURE_MIN_GAP:
            counts["recent"] += 1
            continue
        if client is None:
            client = client_factory()
        try:
            payload = client.event_odds(ev)
        except CircuitOpenError:
            counts["breaker"] += 1
            break
        except ProviderError as exc:
            counts["error"] += 1
            if "403" in str(exc) or "429" in str(exc):
                counts["refused"] += 1
                break
            continue
        doc.update(
            {
                "superbet_event_id": t["superbet_event_id"],
                "match": t["match"],
                "start_utc": t["start_utc"],
            }
        )
        doc["captures"].append(
            {
                "fetched_at_utc": si.iso((stamp or timeutil.now)()),
                "payload": pb.trim_payload(payload),
            }
        )
        _write_json(path, doc)
        counts["captured" if payload else "no_odds"] += 1
    return counts


def capture_holder(
    runs_dir: str, date: str, command_of: Callable[[int], str] | None = None
) -> int | None:
    """The pid of the day's live capture loop; `command_of` (a pid's command
    line) is the process-lookup seam, the real one when None."""
    from scripts.sofa.cs2_daily import _command_of, already_running

    return already_running(
        prestart_dir(runs_dir, date) / CAPTURE_PID,
        date,
        command_of or _command_of,
        script="paper_bb_handicap.py",
    )


def capture_loop(
    runs_dir: str,
    date: str,
    client_factory: Callable[[], OddsClient],
    clock: Callable[[], datetime] = timeutil.now,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Passes every CAPTURE_EVERY_MIN until D's window ends."""
    _, end = si.day_window(date)
    while True:
        now = clock()
        if now >= end:
            return 0
        try:
            counts = capture_pass(runs_dir, date, client_factory, now)
            print(f"[{si.iso(now)}] capture {date}: {dict(counts)}", flush=True)
        except Exception as exc:  # noqa: BLE001 - one bad pass, the loop goes on
            print(
                f"[{si.iso(now)}] capture {date}: pass failed - "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
        wait = min(timedelta(minutes=pb.CAPTURE_EVERY_MIN), end - clock())
        if wait.total_seconds() > 0:
            sleep(wait.total_seconds())


def runs_root() -> Path:
    from bet.sofa.config import SofaConfig

    root = Path(SofaConfig.from_env().runs_dir)
    return root if root.is_absolute() else _REPO / root


def spawn_capture_loop(date: str) -> int:
    """`paper_bb_handicap.py --capture --date D --loop` detached (own
    session), appending to prestart/<D>/capture.log; its pid."""
    out = prestart_dir(str(runs_root()), date)
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(_REPO / "src"), str(_REPO), env.get("PYTHONPATH")) if p
    )
    with (out / CAPTURE_LOG).open("a", encoding="utf-8") as fh:
        proc = subprocess.Popen(
            [
                sys.executable,
                "scripts/sofa/paper_bb_handicap.py",
                "--capture",
                "--date",
                date,
                "--loop",
                "--runs-dir",
                str(runs_root()),
            ],
            cwd=_REPO,
            stdout=fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
    return proc.pid


def ensure_capture_loop(
    date: str,
    *,
    spawn: Callable[[str], int] | None = None,
    holder: Callable[[str, str], int | None] | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> str:
    """Make sure D's capture loop runs; one line. Never raises (shadow_daily
    calls it at its start and goes on whatever happens here)."""
    try:
        if not pb.uses_prestart(date):
            return f"paper capture {date}: before {pb.PRESTART_FROM}, not started"
        _, end = si.day_window(date)
        if clock() >= end:
            return f"paper capture {date}: day over, not started"
        root = str(runs_root())
        pid = (holder or capture_holder)(root, date)
        if pid is not None:
            return f"paper capture {date}: already running (pid {pid})"
        started = (spawn or spawn_capture_loop)(date)
        return (
            f"paper capture {date}: started pid {started} "
            f"(log {prestart_dir(root, date) / CAPTURE_LOG})"
        )
    except Exception as exc:  # noqa: BLE001 - the caller's day goes on
        return f"paper capture {date}: NOT started - {type(exc).__name__}: {exc}"


def rebuild_ledger(out_dir: Path) -> dict[str, Any]:
    days = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(out_dir.glob("????-??-??.json"))
    ]
    ledger = pb.build_ledger(days)
    _write_json(out_dir / LEDGER_FILE, ledger)
    return ledger


def _default_client() -> OddsClient:
    from bet.sofa.client import SofascoreClient
    from bet.sofa.config import SofaConfig

    return SofascoreClient(SofaConfig.from_env())


def _print_day(doc: Mapping[str, Any]) -> None:
    print(
        f"{doc['date']} [{doc['section']}] {doc['status']}: "
        f"{doc['selections']} selections, won {doc['won']}, "
        f"pending games {len(doc['pending'])}, fetch gaps {len(doc['fetch_gaps'])}, "
        f"counts {doc['counts']}"
    )
    for c in doc["candidates"]:
        if c["selected"]:
            print(
                f"  {c['kickoff_utc']} {c['match']}: {c['team']} {c['side_line']:+g} "
                f"@ {c['odds']:.2f} p_open {c['p_open']:.3f} edge {c['edge']:+.3f} "
                f"-> {c['outcome']}"
            )


def main(
    argv: Sequence[str] | None = None,
    client_factory: Callable[[], OddsClient] | None = None,
) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date")
    ap.add_argument("--runs-dir", default="runs/sofa")
    ap.add_argument(
        "--odds-cache", default=None, help="default <runs-dir>/paper/bb_handicap/odds"
    )
    ap.add_argument(
        "--no-fetch",
        action="store_true",
        help="read the cache only; a missing payload is a fetch gap",
    )
    ap.add_argument(
        "--pending",
        action="store_true",
        help="also re-run every earlier day file still PARTIAL (grades late games)",
    )
    ap.add_argument(
        "--report", action="store_true", help="print the forward summary in Polish"
    )
    ap.add_argument(
        "--capture",
        action="store_true",
        help="capture bet365 for D's games starting within 3 h (no grading)",
    )
    ap.add_argument(
        "--loop",
        action="store_true",
        help="with --capture: every 15 min until D's window ends",
    )
    args = ap.parse_args(argv)
    if not args.date and not args.report:
        ap.error("--date or --report")
    if args.capture:
        if not args.date:
            ap.error("--capture needs --date")
        return _capture(
            args.runs_dir, args.date, args.loop, client_factory or _default_client
        )
    out_dir = paper_dir(args.runs_dir)
    cache = Path(args.odds_cache) if args.odds_cache else out_dir / "odds"
    code = 0
    if args.date:
        factory = None if args.no_fetch else (client_factory or _default_client)
        dates = [args.date]
        if args.pending:
            dates = pending_days(out_dir, args.date) + dates
        for date in dates:
            day_code, gaps = _run_one(args.runs_dir, date, out_dir, cache, factory)
            code = max(code, day_code)
            if gaps:
                # a refusal or a dead bridge: no further day asks Sofascore
                factory = None
    ledger = rebuild_ledger(out_dir)
    if args.report:
        print(pb.report_pl(ledger))
    return code


def _capture(
    runs_dir: str, date: str, loop: bool, factory: Callable[[], OddsClient]
) -> int:
    if not loop:
        counts = capture_pass(runs_dir, date, factory, timeutil.now())
        print(f"capture {date}: {dict(counts)}")
        return 1 if counts["refused"] or counts["breaker"] else 0
    holder = capture_holder(runs_dir, date)
    if holder is not None:
        print(
            f"paper capture loop for {date} already runs (pid {holder})",
            file=sys.stderr,
        )
        return 2
    pid_file = prestart_dir(runs_dir, date) / CAPTURE_PID
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    try:
        return capture_loop(runs_dir, date, factory)
    finally:
        pid_file.unlink(missing_ok=True)


def pending_days(out_dir: Path, before: str) -> list[str]:
    """Day files before `before` whose status is still PARTIAL."""
    out = []
    for p in sorted(out_dir.glob("????-??-??.json")):
        if (
            p.stem < before
            and json.loads(p.read_text(encoding="utf-8")).get("status") == "PARTIAL"
        ):
            out.append(p.stem)
    return out


def _run_one(
    runs_dir: str,
    date: str,
    out_dir: Path,
    cache: Path,
    factory: Callable[[], OddsClient] | None,
) -> tuple[int, int]:
    """(exit code, fetch gaps) of one day."""
    try:
        doc = run_day(runs_dir, date, cache, factory, timeutil.now())
    except Exception as exc:  # a crash is FAILED, never a half file
        print(f"FAILED {date}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2, 0
    if doc["status"] == "FAILED":
        print(
            f"FAILED: no SHADOW basketball file for {date} / {next_day(date)}",
            file=sys.stderr,
        )
        return 2, 0
    _write_json(out_dir / f"{date}.json", doc)
    _print_day(doc)
    return (1 if doc["status"] == "PARTIAL" else 0), len(doc["fetch_gaps"])


if __name__ == "__main__":
    sys.exit(main())
