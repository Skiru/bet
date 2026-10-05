#!/usr/bin/env python3
"""Record what every variant and every measurement did on a settled day.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/record_results.py --date 2026-09-30
    ... --from 2026-09-28 --to 2026-09-30

One row per (date, variant) in runs/sofa/ledger/results.jsonl - the running
record the next decision about a rule, a floor or a sport is taken from. A
re-run of a date replaces that date's rows, so the ledger is idempotent.

Variants, each graded at its own printed price and never added to another:

    official         KUPON_<d>.pdf singles and builders (audit_settlement 7c);
                     on a stats-only day split by epoch (+ official:pre_stats_only)
                     with one section per sport
    removed:reads    legs a read removed from a stats-only coupon (7h)
    wariant          KUPON_<d>_WARIANT.pdf (7d)
    sport:<sport>    KUPON_<d>_<SPORT>.pdf for cs2 / hockey / basketball / volleyball
    multi            KUPON_<d>_WSZYSTKIE.pdf, its total and its sections

and, not bets but the evidence under the price-only rule:

    measure:<sport>  Superbet's price against the outcome - the favourite side
                     of every graded line (cs2.one_side_per_line), its hit
                     against its devigged probability, Brier and flat ROI

A variant whose artifact does not exist that day is absent, not a zero.
Also `rule:<sport>` - the price-only rule replayed on the day, chosen before
the outcome - so the rule has a record even on a day no coupon was built.

Offline. Exit 0 = recorded (pending legs are shown, not failed); 1 = a
MISMATCH: the coupon's grader and the measurement's disagree on a leg; 2 = a
crash or a missing database (nothing is written then).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import coupon_sports, shadow  # noqa: E402
from bet.sofa import multi_coupon as mc  # noqa: E402
from bet.sofa import sport_coupon as sc  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    PROFILES,
    is_sheet_sport,
    printed_builders,
    printed_singles,
    profile_artifact_path,
)
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.cs2 import one_side_per_line, summarize, write_atomic  # noqa: E402
from bet.sofa.epochs import OLD, STATS_ONLY, artifact_epoch  # noqa: E402
from bet.sofa.locked_print import leg_key, printed_leg_keys  # noqa: E402
from bet.sofa.timeutil import now  # noqa: E402
from scripts.sofa import settle_multi_coupon, settle_sport_coupon  # noqa: E402

LEDGER_DIR = "ledger"
LEDGER_FILE = "results.jsonl"
# SETTLE's final event states; anything else is asked again. One set for
# every measured sport since 2026-10-05 (bet.sofa.shadow, plan B0): UNUSUAL
# is retryable now, and the identity states (DUPLICATE_*, WITHDRAWN,
# ID_CHANGED, MOVED_TO:<d>, AMBIGUOUS_START) are final and never counted.
FINAL_STATES = shadow.TERMINAL


def ledger_path(runs_dir: str) -> Path:
    return Path(runs_dir) / LEDGER_DIR / LEDGER_FILE


def _pending(rows: list[dict[str, Any]]) -> int:
    return sum(1 for r in rows if settle_sport_coupon.is_pending(str(r["outcome"])))


def match_key(row: dict[str, Any]) -> str:
    """The match one graded position belongs to - the cluster audit_ledger
    resamples (legs of one match share its game script and are not
    independent). A Sofascore id for the official / WARIANT positions, a
    Superbet id for a sport coupon's."""
    src = row.get("source") if isinstance(row.get("source"), dict) else row
    assert isinstance(src, dict)
    if src.get("sofascore_event_id") is not None:
        return f"sofa:{src['sofascore_event_id']}"
    if src.get("superbet_event_id") is not None:
        return f"sb:{src['superbet_event_id']}"
    return f"unkeyed:{id(row)}"  # never merges with another position


def by_match(
    rows: list[dict[str, Any]], odds_key: str = "odds"
) -> dict[str, list[float]]:
    """{match: [units, settled]} over the decided positions, graded exactly
    as mc.summarize_units grades them (WIN pays odds - 1, LOSS costs 1)."""
    out: dict[str, list[float]] = {}
    for r in rows:
        if r["outcome"] not in ("WIN", "LOSS"):
            continue
        units = float(r[odds_key]) - 1.0 if r["outcome"] == "WIN" else -1.0
        acc = out.setdefault(match_key(r), [0.0, 0])
        acc[0] = round(acc[0] + units, 4)
        acc[1] += 1
    return out


def estimated_builders(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The builders graded at the haircut estimate (odds_if_product x
    BUILDER_HAIRCUT) because no screen price was recorded for them - what
    audit_settlement 7c marks "(szac.)". Their units are an estimate of what
    Superbet would have paid, not a price it printed."""
    return mc.summarize_units([r for r in rows if r.get("odds_measured") is False])


def position_epoch(item: dict[str, Any], artifact_epoch_: str) -> str:
    """The epoch a printed position was selected in: a locked leg's own build
    (`printed_under.epoch`, none = the old rule), else the artifact's."""
    if item.get("locked"):
        return str((item.get("printed_under") or {}).get("epoch") or OLD)
    return artifact_epoch_


def _confidence_row(
    date: str,
    variant: str,
    singles: list[dict[str, Any]],
    builders: list[dict[str, Any]],
    rows: dict[Any, dict[str, Any]],
    epoch: str,
) -> dict[str, Any]:
    by_sport: dict[str, list[dict[str, Any]]] = {}
    for g in [*singles, *builders]:
        sport = str(g["source"].get("sport") or "football")
        by_sport.setdefault(sport, []).append(g)
    return {
        "date": date,
        "variant": variant,
        # bet.sofa.epochs: which rule selected these positions (K7).
        "epoch": epoch,
        "singles": mc.summarize_units(singles),
        "builders": mc.summarize_units(builders),
        "total": mc.summarize_units(singles + builders),
        # One section per sport, never in place of the total (K7).
        "sections": {sp: mc.summarize_units(g) for sp, g in sorted(by_sport.items())},
        "estimated_builders": estimated_builders(builders),
        "by_match": by_match(singles + builders),
        "pending": _pending(singles + builders),
        # moved beyond 48 h / awarded: 0 units, never a loss and
        # never "unsettled" (also in `outcomes` as REFUND)
        "refunded": settle_multi_coupon.refunded(singles + builders),
        "outcomes": _outcomes(singles + builders),
        "settled_rows_in_db": len(rows),
    }


def confidence_rows(runs_dir: str, date: str, db_path: str) -> list[dict[str, Any]]:
    """`official` and `wariant`, graded as 7c / 7d grade them.

    On a day the coupon artifact is stats-only (11_coupon.json, plan
    2026-10-05 K7) the official coupon is split by the rule that selected each
    position: `official` (epoch stats_only - the fresh positions and the
    legs locked from a stats-only build) and `official:pre_stats_only` (legs
    locked from a build before STATS_ONLY_FROM_UTC - on 10-05 the morning's).
    The legs a read removed are `removed:reads`, graded the same way and
    never part of the coupon's result (K6, 7h). The measured sports' legs
    are graded by sport_coupon, not here."""
    out = []
    for variant, profile in (("official", "standard"), ("wariant", "wariant")):
        # The coupon artifact (11_coupon.json on a stats-only day, K3).
        path = profile_artifact_path(mc.official_dir(runs_dir, date), PROFILES[profile])
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc_epoch = artifact_epoch(doc)
        p_singles = [s for s in printed_singles(doc) if is_sheet_sport(s)]
        p_builders = printed_builders(doc)
        ids = {int(x["sofascore_event_id"]) for x in p_singles}
        ids |= {int(x["sofascore_event_id"]) for x in p_builders}
        # The printed keys: the same rows 7c / 7d grade (A5), the A4 file and
        # the refunds (moved beyond 48 h / awarded).
        rows, screen = settle_multi_coupon.official_rows(
            runs_dir, date, db_path, profile, ids,
            keys=printed_leg_keys(doc, sheet_sports_only=True),
        )
        singles, builders = settle_multi_coupon.grade_confidence_positions(
            [{"source": s} for s in p_singles],
            [{"source": b} for b in p_builders],
            rows,
            screen,
            settle_ran=settle_multi_coupon.ran_on(rows, date),
        )
        if doc_epoch != STATS_ONLY:
            out.append(_confidence_row(
                date, variant, singles, builders, rows, doc_epoch))
            continue
        # F7: the measured sports' legs on the coupon, graded at the printed
        # price by sport_coupon, against the identity pinned before the
        # match; one section per sport beside football / tennis.
        sport_legs = [s for s in printed_singles(doc) if not is_sheet_sport(s)]
        if sport_legs:
            singles = singles + [
                {"source": g, "odds": g["odds"], "outcome": g["outcome"]}
                for g in coupon_sports.grade(runs_dir, date, sport_legs, now())
            ]
        for name, keep in ((variant, True), (f"{variant}:pre_stats_only", False)):
            sel_s = [g for g in singles
                     if (position_epoch(g["source"], doc_epoch) == STATS_ONLY) == keep]
            sel_b = [g for g in builders
                     if (position_epoch(g["source"], doc_epoch) == STATS_ONLY) == keep]
            if keep or sel_s or sel_b:
                out.append(_confidence_row(
                    date, name, sel_s, sel_b, rows, STATS_ONLY if keep else OLD))
        all_removed = doc.get("removed_by_reads") or []
        removed = [r for r in all_removed if is_sheet_sport(r)]
        removed_sports = [r for r in all_removed if not is_sheet_sport(r)]
        if removed or removed_sports:
            r_rows: dict[Any, dict[str, Any]] = {}
            r_singles: list[dict[str, Any]] = []
            if removed:
                r_rows, _ = settle_multi_coupon.official_rows(
                    runs_dir, date, db_path, profile,
                    {int(r["sofascore_event_id"]) for r in removed},
                    keys={leg_key(r) for r in removed},
                )
                r_singles, _ = settle_multi_coupon.grade_confidence_positions(
                    [{"source": r} for r in removed], [], r_rows, {},
                    settle_ran=settle_multi_coupon.ran_on(r_rows, date),
                )
            r_singles += [
                {"source": g, "odds": g["odds"], "outcome": g["outcome"]}
                for g in coupon_sports.grade(runs_dir, date, removed_sports, now())
            ]
            row = _confidence_row(date, "removed:reads", r_singles, [], r_rows,
                                  STATS_ONLY)
            row["by_reason"] = {
                reason: mc.summarize_units(
                    [g for g in r_singles if g["source"].get("reason") == reason])
                for reason in sorted(
                    {str(g["source"].get("reason")) for g in r_singles})
            }
            out.append(row)
    return out


def sport_rows(runs_dir: str, date: str) -> list[dict[str, Any]]:
    out = []
    for sport in sc.SPORT_KEYS:
        graded = settle_sport_coupon.settle_day(runs_dir, sport, date)
        if graded is None:
            continue
        out.append(
            {
                "date": date,
                "variant": f"sport:{sport}",
                "total": mc.summarize_units(graded),
                "by_match": by_match(graded),
                "by_family": {
                    fam: mc.summarize_units([g for g in graded if g["family"] == fam])
                    for fam in sorted({g["family"] for g in graded})
                },
                "pending": _pending(graded),
                "outcomes": _outcomes(graded),
            }
        )
    return out


def multi_rows(runs_dir: str, date: str, db_path: str) -> list[dict[str, Any]]:
    res = settle_multi_coupon.settle_day(runs_dir, date, db_path)
    if res is None:
        return []
    sections = {}
    rows: list[dict[str, Any]] = []
    for key, sec in res["sections"].items():
        if "rows" not in sec:
            sections[key] = {"excluded": sec.get("reason")}
            continue
        sections[key] = mc.summarize_units(sec["rows"])
        rows += sec["rows"]
    return [
        {
            "date": date,
            "variant": "multi",
            "total": res["variant_total"],
            "estimated_builders": estimated_builders(rows),
            "by_match": by_match(rows),
            "sections": sections,
            "pending": _pending(rows),
            "refunded": settle_multi_coupon.refunded(rows),
            "outcomes": _outcomes(rows),
        }
    ]


def _favourite(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Price against outcome on the favourite side of every line."""
    stats = summarize(one_side_per_line(rows, "favourite"), "ALL")
    if stats is None:
        return None
    return {
        "events": stats.events,
        "sides": stats.sides,
        "mean_fair_p": round(stats.fair_p, 4),
        "hit": round(stats.hit, 4),
        "gap_pp": round(100 * (stats.hit - stats.fair_p), 2),
        "brier": round(stats.brier, 4),
        "roi": round(stats.roi, 4),
        "median_margin": round(stats.margin, 4),
    }


def _shape(row: dict[str, Any]) -> str:
    if "partner_odds" in row:
        return "two"
    sides = set((row.get("group_odds") or {}).keys())
    return "three" if "DRAW" in sides else "exact"


def measure_rows(runs_dir: str, date: str) -> list[dict[str, Any]]:
    """The price against the outcome, per sport.

    `favourite_side` is the TWO-WAY lines only, the series every day before
    2026-09-30 measured, so it stays comparable across the cutover; 1X2 and
    exact-score groups (favourites at 0.26-0.5) are in `by_shape`, every
    family in `by_family`, and player lines apart in `players`.
    """
    out = []
    for sport in sc.SPORT_KEYS:
        doc = sc.load_settled(runs_dir, sport, date)
        if doc is None:
            continue
        # Only a SETTLED event's lines: an identity state (a duplicate, a
        # record moved to a later file - B4) keeps the rows it had for the
        # audit, and they must not be counted twice or at all.
        graded = [
            r
            for ev in (doc.get("events") or {}).values()
            if ev.get("state") == "SETTLED"
            for r in ev.get("graded") or []
        ]
        team = [r for r in graded if not str(r.get("family", "")).startswith("player_")]
        players = [r for r in graded if str(r.get("family", "")).startswith("player_")]
        states: dict[str, int] = {}
        for ev in (doc.get("events") or {}).values():
            states[str(ev.get("state"))] = states.get(str(ev.get("state")), 0) + 1
        out.append(
            {
                "date": date,
                "variant": f"measure:{sport}",
                "events": states,
                "favourite_side": _favourite([r for r in team if _shape(r) == "two"]),
                "by_shape": {
                    shape: _favourite([r for r in team if _shape(r) == shape])
                    for shape in ("two", "three", "exact")
                    if any(_shape(r) == shape for r in team)
                },
                "by_family": {
                    fam: _favourite([r for r in team if r.get("family") == fam])
                    for fam in sorted({str(r.get("family")) for r in team})
                },
                "players": _favourite(players),
                # events SETTLE would ask again (RETRYABLE); most never settle
                # (not on Sofascore), and the loops re-settle only D and D-1,
                # so they are reported, never counted as pending
                "retryable": sum(
                    n for st, n in states.items() if not shadow.is_terminal(st)
                ),
                # never counted: a doubt about which match the record is
                "excluded": sum(
                    n for st, n in states.items() if shadow.is_excluded(st)
                ),
                "pending": 0,
            }
        )
    return out


def rule_rows(runs_dir: str, date: str) -> list[dict[str, Any]]:
    """What the price-only rule would have done on the day, one side per
    event chosen before the outcome (sport_coupon.rule_history) - recorded
    every settled day, whether or not a coupon was built."""
    out = []
    for sport in sc.SPORT_KEYS:
        if sc.load_settled(runs_dir, sport, date) is None:
            continue
        h = sc.rule_history(runs_dir, sport, [date], sc.rule_for(sport, date))
        n = int(h.get("n", 0))
        wins = int(h.get("wins", 0))
        other = int(h.get("void", 0)) + int(h.get("ungradeable", 0))
        out.append(
            {
                "date": date,
                "variant": f"rule:{sport}",
                "graded_at": "last pre-start price",
                "total": {
                    "positions": n + other,
                    "settled": n,
                    "won": wins,
                    "lost": n - wins,
                    "not_counted": other,
                    "units": round(float(h.get("roi", 0.0)) * n, 4),
                    "roi": h.get("roi") if n else None,
                },
                "by_family": h.get("by_family", {}),
                "pending": 0,
            }
        )
    return out


def _outcomes(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in rows:
        key = str(r["outcome"]).split(":")[0]
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _read_nothing(row: dict[str, Any]) -> bool:
    if "settled_rows_in_db" in row:
        return int(row["settled_rows_in_db"]) == 0
    if "favourite_side" in row:
        return row["favourite_side"] is None and not row.get("by_shape")
    outcomes = row.get("outcomes")
    if outcomes is not None:
        return set(outcomes) <= {"PENDING"}
    return _settled(row) == 0


def _settled(row: dict[str, Any]) -> int:
    total = row.get("total") or {}
    fav = row.get("favourite_side") or {}
    return int(total.get("settled") or fav.get("sides") or 0)


def record(runs_dir: str, date: str, db_path: str) -> list[dict[str, Any]]:
    rows = (
        confidence_rows(runs_dir, date, db_path)
        + sport_rows(runs_dir, date)
        + multi_rows(runs_dir, date, db_path)
        + measure_rows(runs_dir, date)
        + rule_rows(runs_dir, date)
    )
    path = ledger_path(runs_dir)
    with sc.dir_lock(path.parent):
        return _merge(path, date, rows)


def _merge(path: Path, date: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace `date`'s rows in the ledger (under the caller's lock: the
    05:15Z loop and a /sofa-day run may both record the same day)."""
    kept = []
    if path.exists():
        kept = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        old = {r["variant"]: r for r in kept if r.get("date") == date}
        kept = [r for r in kept if r.get("date") != date]
        for i, r in enumerate(rows):
            before = old.get(r["variant"])
            if before is not None and _settled(before) > 0 and _read_nothing(r):
                # a run that read no data (no settled rows for the day, a
                # settled.json not written yet) never replaces a graded row;
                # one that read data does - a regrade to PUSH, a MISMATCH or
                # an in-play price may lower the count, and that is the truth
                print(
                    f"KEPT  {date} {r['variant']}: the ledger has "
                    f"{_settled(before)} settled, this run {_settled(r)}",
                    file=sys.stderr,
                )
                rows[i] = before
    merged = sorted(kept + rows, key=lambda r: (r["date"], r["variant"]))
    write_atomic(
        path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in merged)
    )
    return rows


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--date")
    parser.add_argument("--from", dest="start")
    parser.add_argument("--to", dest="end")
    args = parser.parse_args()
    if args.date:
        dates = [args.date]
    elif args.start and args.end:
        dates = settle_sport_coupon.days(args.start, args.end)
    else:
        parser.error("--date, or --from and --to")
    config = SofaConfig.from_env()
    runs_dir = config.runs_dir
    pending = mismatches = 0
    print(
        "| date | variant | positions | settled | won | lost | units | ROI | pending |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    measures = []
    for date in dates:
        for r in record(runs_dir, date, config.db_path):
            pending += r["pending"]
            mismatches += int((r.get("outcomes") or {}).get("MISMATCH", 0))
            if r["variant"].startswith("measure:"):
                measures.append(r)
                continue
            t = r["total"]
            roi = "-" if t["roi"] is None else f"{t['roi']:+.1%}"
            print(
                f"| {date} | {r['variant']} | {t['positions']} | {t['settled']} | "
                f"{t['won']} | {t['lost']} | {t['units']:+.2f} | {roi} | "
                f"{r['pending']} |"
            )
    if measures:
        print(
            "\n| date | measurement (two-way, favourite side) | sides | fair p "
            "| hit | gap pp | ROI | retryable events |"
        )
        print("|---|---|---|---|---|---|---|---|")
        for r in measures:
            f = r.get("favourite_side") or {}
            roi = "-" if f.get("roi") is None else f"{f['roi']:+.1%}"
            print(
                f"| {r['date']} | {r['variant']} | {f.get('sides', 0)} | "
                f"{f.get('mean_fair_p', '-')} | {f.get('hit', '-')} | "
                f"{f.get('gap_pp', '-')} | {roi} | {r['retryable']} |"
            )
    if mismatches:
        print(
            f"\nMISMATCH: {mismatches} position(s) - two graders disagree; one "
            "of them is wrong, and neither result is counted"
        )
    print(f"\nledger: {ledger_path(runs_dir)}")
    # 1 only for a defect (two graders disagreeing); a pending leg is the
    # normal state of yesterday's night games and is shown, not failed
    return 1 if mismatches else 0


def main() -> int:
    """An unexpected crash is FAILED (2), never read as "pending" (1)."""
    try:
        return _main()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
