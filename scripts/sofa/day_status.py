#!/usr/bin/env python3
"""One status report of a sofa day (plan docs/sofa/PLAN_2026-10-05_PRODUCTION_GRADE.md
F6.2, with F5.2's CLV completeness). Read-only, no network.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/day_status.py --date <d> \\
        [--clv-from 2026-09-19]

Each line is one check, OK / WARN / BROKEN, or NOT_CHECKED for what this
report cannot see without the network (the bridge) - a check it skipped is
named, never shown as passed:

    offer         newest / oldest fetched_at_utc in 04_offer.json
    sport:<s>     newest snapshot in runs/sofa/shadow/<s>/<d>/, runs/sofa/cs2/<d>/
    loop:<name>   capture_closing (its pid file + ps), shadow_daily / cs2_daily
                  (pid file + ps, and the last step time in their log)
    bridge        NOT_CHECKED (no network); the last FIXTURE_CHECK that read
                  through it is shown
    ledger        MISMATCH positions in runs/sofa/ledger/results.jsonl, and
                  whether D-1 is recorded
    clv           printed official legs past their closing window with a
                  close in closing.jsonl (and per day from --clv-from)
    coupon        11_coupon.json / 08_confidence.json against their sources
                  (build_coupon_pdf's own staleness rules)
    fixtures      UNVERIFIED events of fixture_status.json

Exit 0 all OK, 1 a WARN, 2 a BROKEN.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import fixture_status as fs  # noqa: E402
from bet.sofa import timeutil  # noqa: E402
from bet.sofa.clv import CLOSE_MIN_MINUTES  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.epochs import STATS_ONLY_DATE  # noqa: E402
from scripts.sofa.audit_clv import closing_rows  # noqa: E402
from scripts.sofa.build_coupon_pdf import (  # noqa: E402
    confidence_older_than_sheet,
    coupon_older_than_sources,
)
from scripts.sofa.capture_closing import (  # noqa: E402
    leg_key,
    loop_holder,
    minutes_to,
    printed_legs,
)
from scripts.sofa.cs2_daily import _command_of, already_running  # noqa: E402

OK, WARN, BROKEN, NOT_CHECKED = "OK", "WARN", "BROKEN", "NOT_CHECKED"
RANK = {OK: 0, NOT_CHECKED: 0, WARN: 1, BROKEN: 2}
# The same limit OFFER / CONFIDENCE read (SofaConfig.price_max_age_min):
# an offer older than this empties a rebuild to its locked legs.
OFFER_MAX_AGE = timedelta(minutes=SofaConfig.from_env().price_max_age_min)
# SHADOW's snapshot horizon (plan section 1: a 3 h horizon skipped a 15:30Z
# hockey game on 10-05); a sport snapshot older than this while the day is
# still on is a hole.
SPORT_SNAPSHOT_MAX_AGE = timedelta(hours=3)
LOOP_LOG_MAX_AGE = timedelta(hours=1)
MEASURED = ("hockey", "basketball", "volleyball")
_STEP_TS = re.compile(r"^\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[^\]]*)\]")


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


def _utc(raw: str) -> datetime:
    t = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def _age(now: datetime, t: datetime) -> str:
    minutes = (now - t).total_seconds() / 60.0
    if abs(minutes) < 120:
        return f"{minutes:.0f} min"
    return f"{minutes / 60:.1f} h"


def _z(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _day_over(date: str, now: datetime) -> bool:
    return now >= datetime.fromisoformat(date).replace(tzinfo=UTC) + timedelta(days=1)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def last_jsonl_record(path: Path, chunk: int = 1 << 16) -> dict[str, Any] | None:
    """The last complete JSON line of a (possibly large, possibly torn)
    jsonl file, read from its end."""
    with path.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        fh.seek(max(0, size - chunk))
        tail = fh.read().decode("utf-8", errors="replace")
    for line in reversed(tail.splitlines()):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            return rec
    return None


def offer_check(run: Path, now: datetime) -> Check:
    path = run / "04_offer.json"
    if not path.exists():
        return Check("offer", WARN, "04_offer.json absent")
    try:
        offers = _json(path)
    except ValueError as exc:
        return Check("offer", BROKEN, f"04_offer.json unreadable: {exc}")
    stamps = [_utc(str(r["fetched_at_utc"])) for o in offers
              for r in o.get("rungs") or [] if r.get("fetched_at_utc")]
    if not stamps:
        return Check("offer", WARN, f"{len(offers)} offers, no fetched_at_utc")
    newest, oldest = max(stamps), min(stamps)
    status = OK if now - newest <= OFFER_MAX_AGE or _day_over(run.name, now) else WARN
    return Check("offer", status,
                 f"newest {_z(newest)} ({_age(now, newest)} ago), oldest {_z(oldest)} "
                 f"({_age(now, oldest)} ago), {len(offers)} offers; a rebuild needs "
                 f"<= {OFFER_MAX_AGE.total_seconds() / 60:.0f} min")


def sport_checks(runs: Path, date: str, now: datetime) -> list[Check]:
    out = []
    dirs = {s: runs / "shadow" / s / date for s in MEASURED}
    dirs["cs2"] = runs / "cs2" / date
    for sport, d in dirs.items():
        path = d / "snapshots.jsonl"
        if not path.exists():
            out.append(Check(f"sport:{sport}", WARN, f"no {path}"))
            continue
        rec = last_jsonl_record(path)
        if not rec or not rec.get("fetched_at_utc"):
            out.append(Check(f"sport:{sport}", BROKEN, f"{path}: no readable record"))
            continue
        t = _utc(str(rec["fetched_at_utc"]))
        stale = now - t > SPORT_SNAPSHOT_MAX_AGE and not _day_over(date, now)
        out.append(Check(f"sport:{sport}", WARN if stale else OK,
                         f"newest snapshot {_z(t)} ({_age(now, t)} ago)"))
    return out


def _log_last_step(path: Path) -> datetime | None:
    if not path.exists():
        return None
    with path.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        fh.seek(max(0, fh.tell() - (1 << 16)))
        tail = fh.read().decode("utf-8", errors="replace")
    for line in reversed(tail.splitlines()):
        m = _STEP_TS.match(line)
        if m:
            return _utc(m.group(1))
    return None


def loop_checks(runs: Path, date: str, now: datetime,
                command_of: Callable[[int], str] = _command_of) -> list[Check]:
    out = []
    run = runs / date
    holder = loop_holder(run, command_of)
    legs = printed_legs(run) if (run / "02_fixtures.json").exists() else []
    ahead = [leg for v, leg in legs if v.startswith("official")
             and minutes_to(leg["kickoff_utc"], now) >= CLOSE_MIN_MINUTES]
    if holder is not None:
        out.append(Check("loop:capture_closing", OK,
                         f"pid {holder}; {len(ahead)} printed official leg(s) "
                         "still to close"))
    elif ahead:
        out.append(Check("loop:capture_closing", WARN,
                         f"not running, {len(ahead)} printed official leg(s) "
                         "still to close - "
                         "their CLV will be a hole (start capture_closing.py --loop)"))
    else:
        out.append(Check("loop:capture_closing", OK,
                         "not running; no printed official leg left to close"))
    for name, sub in (("shadow_daily", "shadow"), ("cs2_daily", "cs2")):
        state = runs / sub
        pid = already_running(state / f"daily_{date}.pid", date, command_of,
                              f"{name}.py")
        done = (state / f"daily_{date}.done").exists()
        last = _log_last_step(state / f"daily_{date}.log")
        when = "no step logged" if last is None else (
            f"last step {_z(last)} ({_age(now, last)} ago)")
        if pid is not None:
            quiet = last is not None and now - last > LOOP_LOG_MAX_AGE
            out.append(Check(f"loop:{name}", WARN if quiet else OK,
                             f"pid {pid}; {when}"))
        elif done:
            out.append(Check(f"loop:{name}", OK, f"done; {when}"))
        else:
            out.append(Check(f"loop:{name}", WARN, f"not running, not done; {when}"))
    return out


def bridge_check(run: Path) -> Check:
    path = run / fs.FIXTURE_STATUS_FILE
    seen = "no FIXTURE_CHECK on record for the day"
    if path.exists():
        try:
            doc = _json(path)
            events = doc.get("events") or {}
            unverified = sum(1 for e in events.values()
                             if e.get("status") == fs.UNVERIFIED)
            seen = (f"last FIXTURE_CHECK {doc.get('checked_at_utc')}: "
                    f"{len(events) - unverified} read through it, "
                    f"{unverified} UNVERIFIED")
        except ValueError:
            seen = f"{path.name} unreadable"
    return Check("bridge", NOT_CHECKED,
                 f"no network here and no stored check result (check_bridge.py "
                 f"writes none) - {seen}")


def ledger_check(runs: Path, date: str) -> Check:
    path = runs / "ledger" / "results.jsonl"
    if not path.exists():
        return Check("ledger", WARN, f"no {path}")
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            return Check("ledger", BROKEN, f"{path}: unreadable line")
    mism: dict[str, int] = {}
    for r in rows:
        n = int((r.get("outcomes") or {}).get("MISMATCH", 0))
        if n:
            key = f"{r['date']} {r['variant']}"
            mism[key] = mism.get(key, 0) + n
    prev = (datetime.fromisoformat(date) - timedelta(days=1)).strftime("%Y-%m-%d")
    recorded = sorted(r["variant"] for r in rows if r.get("date") == prev)
    detail = (f"{len(rows)} rows; MISMATCH {sum(mism.values())}"
              + (f" ({', '.join(f'{k}: {n}' for k, n in sorted(mism.items()))})"
                 if mism else "")
              + f"; D-1 {prev}: "
              + (f"{len(recorded)} variant(s) recorded" if recorded
                 else "NOT recorded"))
    if mism:
        return Check("ledger", BROKEN, detail)
    return Check("ledger", OK if recorded else WARN, detail)


def clv_coverage(runs: Path, date: str, now: datetime) -> dict[str, Any]:
    """Printed official legs (football / tennis singles and builder legs, as
    capture_closing reads them) whose closing window has passed, and how many
    of them have a usable close (audit_clv.closing_rows)."""
    run = runs / date
    closing = run / "closing.jsonl"
    if not (run / "02_fixtures.json").exists():
        return {"date": date, "built": False, "closing_file": closing.exists()}
    legs = [(v, leg) for v, leg in printed_legs(run) if v.startswith("official")]
    past = {(v, leg_key(leg)) for v, leg in legs
            if minutes_to(leg["kickoff_utc"], now) < CLOSE_MIN_MINUTES}
    closed = {(r.variant, r.leg) for r in closing_rows(runs, date)}
    return {"date": date, "built": True, "closing_file": closing.exists(),
            "printed": len({(v, leg_key(leg)) for v, leg in legs}),
            "past_window": len(past), "with_close": len(past & closed)}


def clv_check(runs: Path, date: str, now: datetime) -> Check:
    c = clv_coverage(runs, date, now)
    if not c["built"]:
        return Check("clv", WARN, "day not built (no 02_fixtures.json)")
    detail = (f"{c['with_close']}/{c['past_window']} printed official legs past their "
              f"window have a close ({c['printed']} printed); closing.jsonl "
              + ("present" if c["closing_file"] else "ABSENT"))
    if c["past_window"] and not c["closing_file"]:
        return Check("clv", BROKEN, detail)
    if c["past_window"] and c["with_close"] < c["past_window"]:
        return Check("clv", WARN, detail)
    return Check("clv", OK, detail)


def coupon_check(run: Path, now: datetime) -> Check:
    eleven = run / "11_coupon.json"
    stats_only_day = run.name >= STATS_ONLY_DATE
    stale = coupon_older_than_sources(run) or confidence_older_than_sheet(
        run, "08_confidence.json")
    if stale:
        return Check("coupon", BROKEN, stale)
    if not eleven.exists():
        if stats_only_day:
            return Check("coupon", WARN, "11_coupon.json absent")
        return Check("coupon", OK,
                     "a day before the stats-only epoch: 08_confidence.json")
    try:
        doc = _json(eleven)
    except ValueError as exc:
        return Check("coupon", BROKEN, f"11_coupon.json unreadable: {exc}")
    created = doc.get("created_at_utc")
    age = f" ({_age(now, _utc(created))} ago)" if created else ""
    built = ", ".join(f"{k} {v}" for k, v in (doc.get("built_from") or {}).items())
    pdf = run / f"KUPON_{run.name}.pdf"
    if pdf.exists() and pdf.stat().st_mtime < eleven.stat().st_mtime:
        return Check("coupon", BROKEN,
                     f"KUPON_{run.name}.pdf is older than 11_coupon.json - re-render")
    return Check("coupon", OK if pdf.exists() else WARN,
                 f"11_coupon.json {created}{age}, not older than its sources ({built})"
                 + ("" if pdf.exists() else f"; KUPON_{run.name}.pdf absent"))


def fixtures_check(run: Path) -> Check:
    status = fs.load(run)
    if not status:
        return Check("fixtures", WARN, "no fixture_status.json (FIXTURE_CHECK not run)")
    unverified = sorted(e for e, v in status.items()
                        if v.get("status") == fs.UNVERIFIED)
    detail = f"{len(status)} checked, UNVERIFIED {len(unverified)}" + (
        f" ({', '.join(str(e) for e in unverified[:10])})" if unverified else "")
    return Check("fixtures", WARN if unverified else OK, detail)


def checks(runs: Path, date: str, now: datetime,
           command_of: Callable[[int], str] = _command_of) -> list[Check]:
    run = runs / date
    return [
        offer_check(run, now),
        *sport_checks(runs, date, now),
        *loop_checks(runs, date, now, command_of),
        bridge_check(run),
        ledger_check(runs, date),
        clv_check(runs, date, now),
        coupon_check(run, now),
        fixtures_check(run),
    ]


def _days(a: str, b: str) -> list[str]:
    d0, d1 = datetime.fromisoformat(a), datetime.fromisoformat(b)
    return [(d0 + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range((d1 - d0).days + 1)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--clv-from", default=None,
                    help="also list CLV completeness per day from this date to --date")
    ap.add_argument("--runs-dir", default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa"))
    ap.add_argument("--now", default=None, help="the clock (ISO UTC); default now")
    args = ap.parse_args()
    runs = Path(args.runs_dir)
    now = _utc(args.now) if args.now else timeutil.now()
    print(f"# day status {args.date} at {_z(now)} (read-only, no network)")
    found = checks(runs, args.date, now)
    for c in found:
        print(f"{c.status:<11} {c.name:<22} {c.detail}")
    if args.clv_from:
        print(f"\n# CLV completeness {args.clv_from}..{args.date} (official, F5.2)")
        print("| day | closing.jsonl | printed | past window | with close |")
        print("|---|---|---|---|---|")
        days_with = days_built = 0
        for d in _days(args.clv_from, args.date):
            cov = clv_coverage(runs, d, now)
            if not cov["built"]:
                print(f"| {d} | {'yes' if cov['closing_file'] else 'no'} | - | - | - |")
                continue
            days_built += 1
            days_with += int(cov["closing_file"])
            print(f"| {d} | {'yes' if cov['closing_file'] else 'NO'} | "
                  f"{cov['printed']} | {cov['past_window']} | {cov['with_close']} |")
        print(f"\ndays with closing.jsonl: {days_with}/{days_built} built days")
    worst = max((RANK[c.status] for c in found), default=0)
    print(f"\nverdict: {['OK', 'WARN', 'BROKEN'][worst]}")
    return worst


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - a crash is BROKEN
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)
