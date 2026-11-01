#!/usr/bin/env python3
"""A chat slip (AKO) to a target price from the day's coupon
(bet.sofa.slip_builder) - outside the pipeline. It prints no price of ours
and sizes no stake. Without --read-set-dir it writes nothing but --md-out;
with it, it asks Sofascore (bridge) for h2h and pre-match lineups and writes
dossiers (--no-h2h / --no-lineups / --no-dossier skip).

Fewest legs that reach the target with the highest measured chance, one leg
per match, one search over every leg of the coupon - each leg on its own
statistics, never above its price (min(confidence, 1/odds)) and the analysts'
reads; the first line says how many of the requested slips the day gives
("say no first": "dzień cienki - masz N" / "dziś żadnego"). No slip price,
no stake.

The least-loss flow (operator 2026-10-31, docs/sofa/evidence/
slip_flow_backtest_2026-10-31.md): 2 legs by default (--max-legs raises it;
the answer then lists each extra leg's measured cost), Bet Builders only with
--builders (the answer names their measured -16.6% / -45.8%), a target the
leg limit cannot reach said in the first line with the closest slip under it
(never a silent extra leg), a leg of a two-sided ladder with overround < 0.08
preferred in a near-tie (column "marża"), and the second line the honest
money line: expected return after tax = 0.88 x 0.960^n - 1 (what the /kupon
pool's legs realised against their price 10-13..10-30, n 36,940).

The redesign (2026-10-31, docs/sofa/evidence/kupon_od_nowa_2026-10-31.md): no
statistic told a good leg from a bad one at the same price, so the evidence
is shown, never ranked; a leg needs its match's own sample (>= 8 games;
--allow-no-sample admits a leg with none, e.g. the league-rate penalty /
red-card unders), and the chosen legs' prices are asked again right before
the answer - football / tennis from Superbet's offer (OfferFetcher, its
breaker respected), the measured sports from their loop's newest pre-start
snapshot - and a leg priced more than 2% above the coupon drops out, the
slips rebuilt without it (--no-fresh-price: the coupon's prices, marked "nie
dopytano"). Each leg's row carries its fresh price beside the coupon's, its
own sample, the model, the match-up, the league share, h2h and the referee
(bet.sofa.slip_evidence) next to 1/odds.

--check "<mecz>|<rynek Superbetu>|<wybór>" (repeat per leg) [--screen-odds X]:
the operator's own Bet Builder of one match against our numbers instead
(each leg's measured chance beside 1/odds, match-up, the legs' joint history
in both sides' games, the screen price); read-only.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_slip.py \\
        --date 2026-10-20 --target 3 [--slips 2] [--max-legs 2] [--builders] \\
        [--min-odds 1.10] [--max-odds 2.00] [--start-from 10:00 --start-to 12:00] \\
        [--reserve 1] [--read-set-dir runs/sofa/<d>/read_set_slip] [--md-out f]

--start-from / --start-to: kickoff window in the operator's local time
(Europe/Warsaw), [from, to).

Analysts' reads: a leg a veto or a WATCH / NO_BET read refuses (vetoes.json,
reads.json, the slip's own vetoes_slip.json / reads_slip.json written by
`merge_reads.py --slip`, or the reads the coupon carries) never enters a
slip, so after the merge a re-run takes the next best leg. --read-set-dir
writes the unread legs of the slips and of the --reserve slips (the next
disjoint ones, the buffer a refusal falls back on) as
read_set_slip_<sport>.json in read_set.py's compact form, for one analyst per
sport; stale files of an earlier call are removed.

--any-family, --allow-rest and --no-refresh-record are accepted and ignored
(the families' record was removed by the operator 2026-10-31; every search
covers every leg and nothing is refreshed).

Exit 0: every requested slip found at the target; 1: fewer, or a slip only
the closest under a target the leg limit cannot reach (the answer says so);
2: no 11_coupon.json or bad arguments. --check: 0 (1 when a leg is not on the
coupon).
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

from bet.sofa import (  # noqa: E402
    analyses,
    dossier,
    h2h,
    prematch_lineups,
    priced_rows,
    priced_view,
    slip_evidence,
    sport_day,
    timeutil,  # noqa: E402
)
from bet.sofa import slip_builder as sb  # noqa: E402
from bet.sofa.confidence import COUPON_ARTIFACT, coupon_artifact  # noqa: E402
from bet.sofa.superbet_names import board_sides, names  # noqa: E402
from bet.sofa.timeutil import now as utc_now  # noqa: E402
from bet.sofa.veto import load_reads, load_vetoes  # noqa: E402
from scripts.sofa.merge_reads import SLIP_READS, SLIP_VETOES  # noqa: E402
from scripts.sofa.read_set import FIELDS, PRIOR_FIELDS  # noqa: E402

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


def _utc(raw: Any) -> datetime.datetime | None:
    if not raw:
        return None
    return datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))


def _same_line(leg: dict[str, Any] | Any, row: dict[str, Any]) -> bool:
    """A measured sport's coupon leg against one snapshot line."""
    def num(v: Any) -> float | None:
        return None if v is None else float(v)
    if (leg.get("market_id") is not None and row.get("market_id") is not None
            and int(leg["market_id"]) != int(row["market_id"])):
        return False
    return (str(row.get("family") or "") == str(leg.get("family") or "")
            and str(row.get("subject") or "") == str(leg.get("subject") or "")
            and num(row.get("line")) == num(leg.get("line"))
            and str(row.get("side") or "") == str(leg.get("side") or "")
            and int(row.get("period") or 0) == int(leg.get("period") or 0)
            and int(row.get("map_nr") or 0) == int(leg.get("map_nr") or 0))


def sport_fresh(runs_dir: str, leg: Any) -> sb.FreshPrice:
    """A measured sport's leg at its loop's newest snapshot taken before the
    start (SHADOW / CS2 snapshots.jsonl of the leg's source day): OK with its
    price, GONE when that snapshot no longer quotes the line, NOT_ASKED when
    no snapshot is newer than the coupon's price."""
    sport = str(leg.get("sport"))
    day = str(leg.get("source_date") or "")
    kickoff = _utc(leg.get("kickoff_utc"))
    if sport not in ("hockey", "basketball", "volleyball", "cs2") or not day:
        return sb.FreshPrice(sb.FRESH_NOT_ASKED)
    path = sport_day.day_dir(runs_dir, sport, day) / "snapshots.jsonl"  # type: ignore[arg-type]
    newest: dict[str, Any] | None = None
    for snap in sport_day.load_snapshots(path):
        if str(snap.get("superbet_event_id")) != str(leg.get("superbet_event_id")):
            continue
        at = _utc(snap.get("fetched_at_utc"))
        if at is None or (kickoff is not None and at >= kickoff):
            continue
        if newest is None or at > (_utc(newest.get("fetched_at_utc")) or at):
            newest = snap
    priced = _utc(leg.get("price_fetched_at_utc"))
    if newest is None or (priced is not None
                          and (_utc(newest.get("fetched_at_utc")) or priced) <= priced):
        return sb.FreshPrice(sb.FRESH_NOT_ASKED)
    for row in newest.get("lines") or []:
        if _same_line(leg, row) and row.get("odds") is not None:
            return sb.FreshPrice(sb.FRESH_OK, float(row["odds"]),
                                 str(newest["fetched_at_utc"]))
    return sb.FreshPrice(sb.FRESH_GONE, None, str(newest["fetched_at_utc"]))


def offer_fresh(run: Path, legs: list[Any], fetcher: Any,
                now: datetime.datetime) -> dict[tuple[Any, ...], sb.FreshPrice]:
    """Football / tennis legs re-asked of Superbet's offer one event at a time
    (capture_closing's rung match): OK with the side's price, GONE when the
    fetched offer no longer quotes it or Superbet shows the match started,
    NOT_ASKED on an error or an open breaker (the coupon's price stands)."""
    from pydantic import RootModel

    from bet.sofa.contracts import Fixture
    from scripts.sofa.capture_closing import close_record

    out: dict[tuple[Any, ...], sb.FreshPrice] = {}
    path = run / "02_fixtures.json"
    if not path.exists():
        return out
    fixtures = {f.sofascore_event_id: f for f in RootModel[list[Fixture]]
                .model_validate_json(path.read_bytes()).root}
    by_event: dict[int, list[Any]] = {}
    for g in legs:
        by_event.setdefault(int(g["sofascore_event_id"]), []).append(g)
    for eid, these in by_event.items():
        offer = None
        if eid in fixtures:
            seen = len(getattr(fetcher, "errors", []) or [])
            try:
                got = fetcher.fetch_offers([fixtures[eid]])
            except Exception:  # noqa: BLE001 - network: the leg stays unasked
                got = []
            failed = (getattr(fetcher, "errors", []) or [])[seen:] or (
                eid in (getattr(fetcher, "not_reached", []) or []))
            offer = next((o for o in got if o.sofascore_event_id == eid), None)
            if offer is None and failed:
                continue
        if offer is None:
            continue
        stamp = now.isoformat().replace("+00:00", "Z")
        for g in these:
            leg = {"sofascore_event_id": eid, "market": g["market"],
                   "subject": g.get("subject") or "", "line": g.get("line"),
                   "direction": g.get("direction"),
                   "offered_odds": g.get("offered_odds"),
                   "kickoff_utc": g.get("kickoff_utc")}
            rec = None if offer.superbet_started_utc is not None else close_record(
                "slip", leg, offer, now)
            out[sb.fresh_key(g)] = (
                sb.FreshPrice(sb.FRESH_OK, float(rec["odds_close"]), stamp)
                if rec else sb.FreshPrice(sb.FRESH_GONE, None, stamp))
    return out


def fresh_asker(run: Path, runs_dir: str, date: str,
                now: datetime.datetime) -> Any:
    """The callable build() re-asks the chosen legs' prices with."""
    fetcher: Any = None

    def ask(legs: Any) -> dict[tuple[Any, ...], sb.FreshPrice]:
        nonlocal fetcher
        out: dict[tuple[Any, ...], sb.FreshPrice] = {}
        sheet = [g for g in legs if not g.get("family")]
        for g in legs:
            if g.get("family"):
                out[sb.fresh_key(g)] = sport_fresh(runs_dir, g)
        if sheet:
            if fetcher is None:
                from bet.sofa.offer import OfferFetcher, day_flags
                from bet.sofa.superbet import SuperbetClient
                fetcher = OfferFetcher(SuperbetClient(
                    base_url="https://production-superbet-offer-pl.freetls.fastly.net"),
                    **day_flags(date))
            out.update(offer_fresh(run, sheet, fetcher, now))
        return out

    return ask


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
    store = analyses.load(run) if run is not None else {}
    for why, slips in (("slip", result.slips), ("slip_reserve", result.reserve)):
        for x, leg in ((x, g) for x in sb.unread_legs(slips) for g in sb.leg_rows(x)):
            compact = {k: leg[k] for k in FIELDS if leg.get(k) is not None}
            sport = str(leg.get("sport") or "football")
            compact.update(sport=sport, in_set=why)
            if not x.leg.get("builder_legs"):
                # the price the slip re-asked: the analyst never tells the
                # operator to check a price this slip already refreshed
                was = x.coupon_odds if x.coupon_odds is not None else x.odds
                compact["slip_price"] = {
                    "coupon_odds": was, "odds": x.odds,
                    "fresh": x.fresh or sb.FRESH_NOT_ASKED,
                    "age_min": None if x.price_age is None
                    else round(x.price_age.total_seconds() / 60)}
            # the match's section of today (read_set.py's field): a delta pass
            prior = analyses.latest(store, leg.get("sofascore_event_id"), "analyst")
            if prior is not None:
                full = analyses.full_pass(store, leg.get("sofascore_event_id")) or {}
                compact["prior_analysis"] = {
                    **{k: prior.get(k) for k in PRIOR_FIELDS},
                    "full_pass_report": full.get("report"),
                    "full_pass_at_utc": full.get("recorded_at_utc")}
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
    ap.add_argument("--max-legs", type=int, default=sb.MAX_LEGS,
                    help=f"legs per slip (default {sb.MAX_LEGS}; each extra leg costs "
                    "~5%% of the return, measured)")
    ap.add_argument("--min-odds", type=float, default=sb.MIN_LEG_ODDS)
    ap.add_argument("--max-odds", type=float, default=sb.MAX_LEG_ODDS)
    # no-ops kept so an older call (a session that loaded the old /kupon
    # contract) still runs: every search covers every leg (operator
    # 2026-10-31 removed the families on the plus)
    for flag in ("--allow-rest", "--any-family", "--no-refresh-record"):
        ap.add_argument(flag, action="store_true", help=argparse.SUPPRESS)
    ap.add_argument(
        "--builders",
        action="store_true",
        help="add the day's Bet Builders, priced as the product of their legs "
        "(opt-in: measured -16.6%% dev / -45.8%% hold-out after tax)",
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
    ap.add_argument("--runs-dir", default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa"))
    ap.add_argument("--md-out", default=None)
    ap.add_argument("--json-out", default=None,
                    help="the slips as data (SlipRecord.v1): legs keyed as "
                         "13_results.json, coupon and fresh price, chance, read")
    ap.add_argument("--no-fresh-price", action="store_true",
                    help="no re-ask of the chosen legs' prices (offline): the "
                    "coupon's prices, marked 'nie dopytano'")
    ap.add_argument("--allow-no-sample", action="store_true",
                    help="admit a leg with no own match sample (league rate / "
                    "model only); a 1-7 game sample stays out")
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
        text = sb.render_check(args.check, singles, args.screen_odds,
                               matchups, joint, not_printed(run, coupon))
        if args.md_out:
            Path(args.md_out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.md_out).write_text(text, encoding="utf-8")
        print(text)
        return 0 if len(picked) == len(args.check) else 1
    result = sb.build(
        coupon.get("singles") or [],
        now,
        args.target,
        args.slips,
        max_legs=args.max_legs,
        min_odds=args.min_odds,
        max_odds=args.max_odds,
        window=span,
        reads=load_reads(run / "reads.json"),
        slip_reads=load_reads(run / SLIP_READS),
        vetoes=load_vetoes(run / "vetoes.json") + load_vetoes(run / SLIP_VETOES),
        reserve=args.reserve,
        built_at=coupon.get("created_at_utc"),
        competitions=args.competition,
        builders=(coupon.get("builders") or []) if args.builders else (),
        fresh_prices=None if args.no_fresh_price else fresh_asker(
            run, args.runs_dir, args.date, now),
        allow_no_sample=args.allow_no_sample,
    )
    shown = [g for s in result.slips + result.reserve for x in s.legs
             for g in sb.leg_rows(x)]
    text = sb.render(
        result,
        day=args.date,
        target=args.target,
        now=now,
        built_at=coupon.get("created_at_utc"),
        matchups=dossier.matchups_for_legs(
            run, shown, db_path=args.db_path or dossier.DB_PATH),
        evidence=slip_evidence.evidence_for_legs(
            run, shown, db_path=args.db_path or dossier.DB_PATH),
    )
    if args.md_out:
        Path(args.md_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md_out).write_text(text, encoding="utf-8")
    print(text)
    if args.json_out:
        params = {k: v for k, v in vars(args).items()
                  if k not in ("check", "screen_odds")}
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps(sb.record(result, now=now, params=params), indent=1,
                       ensure_ascii=False, default=str) + "\n", encoding="utf-8")
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
    return 0 if sum(s.reached for s in result.slips) >= args.slips else 1


if __name__ == "__main__":
    sys.exit(main())
