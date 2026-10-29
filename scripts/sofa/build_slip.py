#!/usr/bin/env python3
"""A chat slip (AKO) to a target price from the day's coupon
(bet.sofa.slip_builder) - outside the pipeline. It prints no price of ours
and sizes no stake, but it is not read-only: it refreshes family_record.json
and, with --read-set-dir, asks Sofascore (bridge) for h2h and pre-match
lineups and writes dossiers (--no-h2h / --no-lineups / --no-dossier skip).

Fewest legs that reach the target with the highest measured chance, one leg
per match (families on the plus first, or every market with --any-family);
the first line always says how many of the requested slips stand on
families on the plus alone ("say no first"). No slip price, no stake.

--check "<mecz>|<rynek Superbetu>|<wybór>" (repeat per leg) [--screen-odds X]:
the operator's own Bet Builder of one match against our numbers instead
(each leg's measured chance beside 1/odds, family, match-up, the legs' joint
history in both sides' games, the screen price); read-only.

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

Exit 0: every requested slip is supported (--any-family: found); 1: fewer
(the answer says so); 2: no 11_coupon.json, no family_record.json or bad
arguments. --check: 0.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import (  # noqa: E402  # noqa: E402
    dossier,
    h2h,
    prematch_lineups,
    priced_rows,
    priced_view,
    timeutil,  # noqa: E402
)
from bet.sofa import family_record as fr  # noqa: E402
from bet.sofa import slip_builder as sb  # noqa: E402
from bet.sofa.confidence import COUPON_ARTIFACT, coupon_artifact  # noqa: E402
from bet.sofa.superbet_names import board_sides, names  # noqa: E402
from bet.sofa.timeutil import now as utc_now  # noqa: E402
from bet.sofa.veto import load_reads, load_vetoes  # noqa: E402
from scripts.sofa.build_family_record import ensure_quietly  # noqa: E402
from scripts.sofa.merge_reads import SLIP_READS, SLIP_VETOES  # noqa: E402
from scripts.sofa.read_set import FIELDS  # noqa: E402

LOCAL = ZoneInfo("Europe/Warsaw")


def not_printed(run: Path, coupon: dict[str, Any]) -> list[dict[str, Any]]:
    """The day's legs that are not on the coupon, each with `why`: removed by
    a read (its reasons), or refused by a gate (08_refusals*.json, named in
    Superbet's words) - `--check` says why a leg of the operator's builder is
    missing instead of only that it is."""
    out: list[dict[str, Any]] = []
    for g in coupon.get("removed_by_reads") or []:
        why = "; ".join(f"{r.get('verdict')} {r.get('author')}: {r.get('reason')}"
                        for r in g.get("reads") or []
                        if r.get("verdict") in ("WATCH", "NO_BET"))
        out.append({**g, "why": "zdjęta odczytem - " + (why or str(g.get("refusal")))})
    sides = board_sides(run)
    for name in (priced_rows.FILE, priced_rows.SPORTS_FILE):
        doc = priced_rows.load(run / name)
        for row in priced_rows.rows_as_dicts(doc) if doc else []:
            if not row.get("reason"):
                continue
            leg = priced_view._named(row, sides)
            eid = row.get("sofascore_event_id")
            got = names(leg, sides.get(eid) if isinstance(eid, int) else None)
            if got is None:
                continue
            out.append({**leg, "superbet_market": got[0], "superbet_selection": got[1],
                        "why": f"odrzucona: {row['reason']} (kurs {row.get('odds')}"
                        + (f", pewność {row['confidence']}"
                           if row.get("confidence") is not None else "") + ")"})
    return out


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
                   fetch_h2h: bool = True,
                   fetch_lineups: bool = True) -> dict[str, int]:
    """read_set_slip_<sport>.json of the unread slip and reserve legs; with
    `run`, each match's dossier too (`bet.sofa.dossier`, the leg's `dossier`),
    its head-to-head asked of Sofascore first (`bet.sofa.h2h`) unless
    `fetch_h2h` is off, and its pre-match line-up (`bet.sofa.prematch_lineups`)
    unless `fetch_lineups` is off."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("read_set_slip_*.json"):
        stale.unlink()
    by_sport: dict[str, list[dict[str, object]]] = {}
    for why, slips in (("slip", result.slips), ("slip_reserve", result.reserve)):
        for leg in (g for x in sb.unread_legs(slips) for g in sb.leg_rows(x)):
            compact = {k: leg[k] for k in FIELDS if leg.get(k) is not None}
            sport = str(leg.get("sport") or "football")
            compact.update(sport=sport, in_set=why)
            by_sport.setdefault(sport, []).append(compact)
    if run is not None and by_sport:
        every = [x for legs in by_sport.values() for x in legs]
        if fetch_h2h:
            print(h2h.fetch_for_legs(run, every))
        if fetch_lineups:
            print(prematch_lineups.fetch_for_legs(run, every))
        print(dossier.attach(run, every, db_path))
    for sport, legs in by_sport.items():
        (out_dir / f"read_set_slip_{sport}.json").write_text(
            json.dumps(legs, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return {sport: len(legs) for sport, legs in by_sport.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--target", type=float, default=None,
                    help="the slip's target price (required unless --check)")
    ap.add_argument("--slips", type=int, default=1)
    ap.add_argument("--max-legs", type=int, default=sb.MAX_LEGS)
    ap.add_argument("--min-odds", type=float, default=sb.MIN_LEG_ODDS)
    ap.add_argument("--max-odds", type=float, default=sb.MAX_LEG_ODDS)
    ap.add_argument(
        "--allow-rest",
        action="store_true",
        help="fill missing slips from legs outside families on the plus",
    )
    ap.add_argument(
        "--any-family",
        action="store_true",
        help="search every leg in one pass, families on the plus not preferred",
    )
    ap.add_argument(
        "--builders",
        action="store_true",
        help="add the day's Bet Builders, priced as the product of their legs",
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
    ap.add_argument("--no-lineups", action="store_true",
                    help="no Sofascore pre-match line-up request")
    ap.add_argument(
        "--no-refresh-record",
        action="store_true",
        help="read family_record.json as it is (no ledger / database access)",
    )
    ap.add_argument("--runs-dir", default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa"))
    ap.add_argument("--md-out", default=None)
    ap.add_argument("--check", action="append", default=[],
                    help="'<mecz>|<rynek Superbetu>|<wybór>': a leg of the operator's "
                    "own builder (repeat); prints the check instead of a slip")
    ap.add_argument("--screen-odds", type=float, default=None,
                    help="--check: the builder's price on Superbet's screen")
    args = ap.parse_args(argv)
    frozen = timeutil.frozen_clock_refusal(args.runs_dir)
    if frozen:
        print(frozen, file=sys.stderr)
        return 2
    if args.target is None and not args.check:
        ap.error("--target is required (unless --check)")
    if ((args.target is not None and args.target <= 1.0) or args.slips < 1
            or args.max_legs < 1 or args.reserve < 0):
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
    singles = coupon.get("singles") or []
    if args.check:
        try:
            picked = [g for spec in args.check
                      if (g := sb.find_leg(singles, spec)[0]) is not None]
        except ValueError as exc:
            ap.error(str(exc))
        if len({g.get("sofascore_event_id") for g in picked}) > 1:
            ap.error("--check: nogi z różnych meczów - builder jest z jednego "
                     "meczu; podaj pełną nazwę meczu")
        db = args.db_path or dossier.DB_PATH
        matchups = dossier.matchups_for_legs(run, picked, db_path=db)
        joint = dossier.joint_history(run, picked, db_path=db) if picked else None
        text = sb.render_check(args.check, singles, record, args.screen_odds,
                               matchups, joint, not_printed(run, coupon))
        if args.md_out:
            Path(args.md_out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.md_out).write_text(text, encoding="utf-8")
        print(text)
        return 0 if len(picked) == len(args.check) else 1
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
        any_family=args.any_family,
        builders=(coupon.get("builders") or []) if args.builders else (),
    )
    text = sb.render(
        result,
        day=args.date,
        target=args.target,
        record=record,
        now=now,
        built_at=coupon.get("created_at_utc"),
        matchups=dossier.matchups_for_legs(
            run, [g for s in result.slips + result.reserve for x in s.legs
                  for g in sb.leg_rows(x)],
            db_path=args.db_path or dossier.DB_PATH),
    )
    if args.md_out:
        Path(args.md_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md_out).write_text(text, encoding="utf-8")
    print(text)
    if args.read_set_dir:
        out_dir = Path(args.read_set_dir)
        written = write_read_set(out_dir, result, None if args.no_dossier else run,
                                 args.db_path, not args.no_h2h,
                                 not args.no_lineups)
        for sport, n in sorted(written.items()):
            path = out_dir / f"read_set_slip_{sport}.json"
            print(f"do przeczytania: {sport} {sb.legs_pl(n)} -> {path}")
        if not written:
            print(
                "do przeczytania: nic - każda noga ma KEEP analityka"
                if result.slips
                else "do przeczytania: nic - brak kuponu"
            )
    found = len(result.slips) if args.any_family else result.supported
    return 0 if found >= args.slips else 1


if __name__ == "__main__":
    sys.exit(main())
