#!/usr/bin/env python3
"""A chat slip (AKO) to a target price from the day's coupon
(bet.sofa.slip_builder) - outside the pipeline, read-only, no network.

Fewest legs that reach the target with the highest measured chance, one leg
per match, families on the plus first; the first line says how many of the
requested slips the day supports. No slip price, no stake.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_slip.py \\
        --date 2026-10-20 --target 5 [--slips 2] [--max-legs 5] [--allow-rest] \\
        [--min-odds 1.10] [--max-odds 2.00] [--start-from 10:00 --start-to 12:00] \\
        [--reserve 1] [--read-set-dir runs/sofa/<d>/read_set_slip] [--md-out f]

--start-from / --start-to: kickoff window in the operator's local time
(Europe/Warsaw), [from, to).

Analysts' reads: a leg a veto or a WATCH / NO_BET read refuses (vetoes.json,
reads.json, the slip's own vetoes_slip.json / reads_slip.json written by
`merge_reads.py --slip`, or the reads the coupon carries) never enters a
slip, so after the merge a re-run takes the next best leg. The day's
family_record.json is refreshed first when the ledger is newer
(build_family_record.ensure). --read-set-dir writes the
unread legs of the slips and of the --reserve slips (the next disjoint ones,
the buffer a refusal falls back on) as read_set_slip_<sport>.json in
read_set.py's compact form, for one analyst per sport; stale files of an
earlier call are removed.

Exit 0: every requested slip is supported; 1: fewer (the answer says so);
2: no 11_coupon.json, no family_record.json or bad arguments.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import dossier, h2h  # noqa: E402
from bet.sofa import family_record as fr  # noqa: E402
from bet.sofa import slip_builder as sb  # noqa: E402
from bet.sofa.confidence import COUPON_ARTIFACT, coupon_artifact  # noqa: E402
from bet.sofa.timeutil import now as utc_now  # noqa: E402
from bet.sofa.veto import load_reads, load_vetoes  # noqa: E402
from scripts.sofa.build_family_record import ensure_quietly  # noqa: E402
from scripts.sofa.merge_reads import SLIP_READS, SLIP_VETOES  # noqa: E402
from scripts.sofa.read_set import FIELDS  # noqa: E402

LOCAL = ZoneInfo("Europe/Warsaw")


def parse_hhmm(raw: str) -> tuple[int, int]:
    """'11', '11:30', '9:05' or '24' / '24:00' (the next midnight) -> (h, m)."""
    hh, _, mm = raw.strip().partition(":")
    h, m = int(hh), int(mm or 0)
    if not (0 <= h <= 23 and 0 <= m <= 59) and (h, m) != (24, 0):
        raise ValueError(f"not a time of day: {raw!r}")
    return h, m


def window(
    day: str,
    start_from: str | None,
    start_to: str | None,
    now: datetime.datetime | None = None,
) -> tuple[datetime.datetime, datetime.datetime] | None:
    """The kickoff window [from, to) in local time (Europe/Warsaw), as UTC.
    The hours are read on `day`'s local date; an end at or before the start
    crosses midnight (22-02 ends on the next day); a window whose end is
    already past `now` is the same hours of the next local day (a request
    after midnight local, while the coupon of the UTC date still runs)."""
    if start_from is None and start_to is None:
        return None
    base = datetime.date.fromisoformat(day)

    def at(hhmm: str, d: datetime.date) -> datetime.datetime:
        h, m = parse_hhmm(hhmm)
        extra = datetime.timedelta(days=1) if h == 24 else datetime.timedelta()
        local = datetime.datetime.combine(d, datetime.time(h % 24, m), LOCAL)
        return (local + extra).astimezone(datetime.UTC)

    lo_open = datetime.datetime.min.replace(tzinfo=datetime.UTC)
    hi_open = datetime.datetime.max.replace(tzinfo=datetime.UTC)
    for d in (base, base + datetime.timedelta(days=1)):
        lo = at(start_from, d) if start_from else lo_open
        hi = at(start_to, d) if start_to else hi_open
        if start_from and start_to and hi <= lo:
            hi = at(start_to, d + datetime.timedelta(days=1))
        if now is None or hi > now or not start_to:
            return lo, hi
    return lo, hi


def write_read_set(out_dir: Path, result: sb.Result, run: Path | None = None,
                   db_path: str | None = None,
                   fetch_h2h: bool = True) -> dict[str, int]:
    """read_set_slip_<sport>.json of the unread slip and reserve legs; with
    `run`, each match's dossier too (`bet.sofa.dossier`, the leg's `dossier`),
    its head-to-head asked of Sofascore first (`bet.sofa.h2h`) unless
    `fetch_h2h` is off."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("read_set_slip_*.json"):
        stale.unlink()
    by_sport: dict[str, list[dict[str, object]]] = {}
    for why, slips in (("slip", result.slips), ("slip_reserve", result.reserve)):
        for x in sb.unread_legs(slips):
            leg = x.leg
            compact = {k: leg[k] for k in FIELDS if leg.get(k) is not None}
            sport = str(leg.get("sport") or "football")
            compact.update(sport=sport, in_set=why)
            by_sport.setdefault(sport, []).append(compact)
    if run is not None and by_sport:
        every = [x for legs in by_sport.values() for x in legs]
        if fetch_h2h:
            print(h2h.fetch_for_legs(run, every))
        print(dossier.attach(run, every, db_path))
    for sport, legs in by_sport.items():
        (out_dir / f"read_set_slip_{sport}.json").write_text(
            json.dumps(legs, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return {sport: len(legs) for sport, legs in by_sport.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--target", type=float, required=True)
    ap.add_argument("--slips", type=int, default=1)
    ap.add_argument("--max-legs", type=int, default=sb.MAX_LEGS)
    ap.add_argument("--min-odds", type=float, default=sb.MIN_LEG_ODDS)
    ap.add_argument("--max-odds", type=float, default=sb.MAX_LEG_ODDS)
    ap.add_argument(
        "--allow-rest",
        action="store_true",
        help="fill missing slips from legs outside families on the plus",
    )
    ap.add_argument("--start-from", default=None, help="HH:MM local (Europe/Warsaw)")
    ap.add_argument("--start-to", default=None, help="HH:MM local, exclusive")
    ap.add_argument("--reserve", type=int, default=0)
    ap.add_argument(
        "--competition",
        action="append",
        default=[],
        help="keep only legs whose competition contains this (repeatable)",
    )
    ap.add_argument("--read-set-dir", default=None)
    ap.add_argument("--db-path", default=None, help="dossier source")
    ap.add_argument("--no-dossier", action="store_true")
    ap.add_argument("--no-h2h", action="store_true",
                    help="dossiers from the cache only, no Sofascore h2h request")
    ap.add_argument(
        "--no-refresh-record",
        action="store_true",
        help="read family_record.json as it is (no ledger / database access)",
    )
    ap.add_argument("--runs-dir", default="runs/sofa")
    ap.add_argument("--md-out", default=None)
    args = ap.parse_args(argv)
    if args.target <= 1.0 or args.slips < 1 or args.max_legs < 1 or args.reserve < 0:
        ap.error("--target > 1, --slips >= 1, --max-legs >= 1, --reserve >= 0")
    if not 1.0 < args.min_odds <= args.max_odds:
        ap.error("1 < --min-odds <= --max-odds")
    now = utc_now()
    try:
        span = window(args.date, args.start_from, args.start_to, now)
    except ValueError as exc:
        ap.error(f"--start-from / --start-to: {exc}")

    run = Path(args.runs_dir) / args.date
    path = coupon_artifact(run)
    if path.name != COUPON_ARTIFACT or not path.exists():
        print(f"FAILED: no {COUPON_ARTIFACT} in {run}", file=sys.stderr)
        return 2
    coupon = json.loads(path.read_text(encoding="utf-8"))
    problem = "" if args.no_refresh_record else ensure_quietly(args.runs_dir, args.date)
    if problem:
        print(f"WARN: {fr.FILE} not refreshed - {problem}", file=sys.stderr)
    record = fr.load(run, args.date)
    if record is None:
        print(
            f"FAILED: no usable {fr.FILE} for {args.date} - no leg has a measured "
            "chance; build it: scripts/sofa/build_family_record.py --date "
            f"{args.date}",
            file=sys.stderr,
        )
        return 2
    result = sb.build(
        coupon.get("singles") or [],
        record,
        now,
        args.target,
        args.slips,
        max_legs=args.max_legs,
        allow_rest=args.allow_rest,
        min_odds=args.min_odds,
        max_odds=args.max_odds,
        window=span,
        reads=load_reads(run / "reads.json"),
        slip_reads=load_reads(run / SLIP_READS),
        vetoes=load_vetoes(run / "vetoes.json") + load_vetoes(run / SLIP_VETOES),
        reserve=args.reserve,
        built_at=coupon.get("created_at_utc"),
        competitions=args.competition,
    )
    text = sb.render(
        result,
        day=args.date,
        target=args.target,
        record=record,
        now=now,
        built_at=coupon.get("created_at_utc"),
    )
    if args.md_out:
        Path(args.md_out).write_text(text, encoding="utf-8")
    print(text)
    if args.read_set_dir:
        out_dir = Path(args.read_set_dir)
        written = write_read_set(out_dir, result, None if args.no_dossier else run,
                                 args.db_path, not args.no_h2h)
        for sport, n in sorted(written.items()):
            path = out_dir / f"read_set_slip_{sport}.json"
            print(f"do przeczytania: {sport} {sb.legs_pl(n)} -> {path}")
        if not written:
            print(
                "do przeczytania: nic - każda noga ma KEEP analityka"
                if result.slips
                else "do przeczytania: nic - brak kuponu"
            )
    return 0 if result.supported >= args.slips else 1


if __name__ == "__main__":
    sys.exit(main())
