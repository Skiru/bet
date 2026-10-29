#!/usr/bin/env python3
"""Read the results ledger across days - per variant, never pooled.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_ledger.py \\
        --from 2026-09-19 --to 2026-09-30
    ... --variant official            # one variant

The reader of runs/sofa/ledger/results.jsonl (record_results.py writes it).
Every variant is its own table: the coupon (official, by epoch), the legs
removed by reads, and - on days up to the morning of 2026-10-05 - the
retired variants the ledger still holds; the measurements are a separate
table (price against outcome, two-way favourite side). Nothing here adds one
variant's units to another's. Offline. Exit 0, or 2 on a missing ledger.
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

from bet.sofa.clv import MIN_CLUSTERS, cluster_ratio_interval  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from scripts.sofa.record_results import ledger_path  # noqa: E402


def load(runs_dir: str, start: str, end: str) -> list[dict[str, Any]]:
    path = ledger_path(runs_dir)
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [r for r in rows if start <= r["date"] <= end]


def totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """One variant's days summed - positions graded at their own prices."""
    t: dict[str, Any] = {
        "days": len(rows),
        "positions": 0,
        "settled": 0,
        "won": 0,
        "lost": 0,
        "units": 0.0,
    }
    for r in rows:
        for k in ("positions", "settled", "won", "lost"):
            t[k] += int((r.get("total") or {}).get(k, 0))
        t["units"] += float((r.get("total") or {}).get("units", 0.0))
    t["units"] = round(t["units"], 4)
    t["roi"] = round(t["units"] / t["settled"], 4) if t["settled"] else None
    return t


# Bets for a 3% edge to show at 2 sigma when one bet's return has sd ~1
# (practitioner arithmetic, 2026-10-01 review): (2 / 0.03)^2.
BETS_FOR_3PCT = 4400


def match_clusters(
    rows: list[dict[str, Any]],
) -> dict[str, tuple[float, int]] | None:
    """{match: (units, settled)} over a variant's days, merged by match (a
    leg graded a day late is still its match). None when a day with settled
    positions carries no per-match record (written before 2026-10-01, or a
    rule replay, which records only its totals) - its positions cannot be
    clustered, and dropping them would bias the interval."""
    out: dict[str, tuple[float, int]] = {}
    for r in rows:
        settled = int((r.get("total") or {}).get("settled", 0) or 0)
        matches = r.get("by_match")
        if matches is None:
            if settled:
                return None
            continue
        for key, (units, count) in matches.items():
            u, c = out.get(key, (0.0, 0))
            out[key] = (u + float(units), c + int(count))
    return out


def roi_interval(rows: list[dict[str, Any]], seed: int = 7,
                 n: int = 2000) -> tuple[float, float] | None:
    """95% interval of ROI from resampling whole MATCHES - legs of one match
    share its game script, and a day is not the unit either: with two days
    the old by-day bootstrap could only return the two days' own ROIs.
    None without a per-match record, or under MIN_CLUSTERS matches."""
    clusters = match_clusters(rows)
    if clusters is None:
        return None
    return cluster_ratio_interval(clusters, seed, n)


def interval_text(rows: list[dict[str, Any]]) -> str:
    clusters = match_clusters(rows)
    if clusters is None:
        return "- (no per-match record)"
    ci = cluster_ratio_interval(clusters)
    if ci is None:
        return f"- (<{MIN_CLUSTERS} matches)"
    return f"[{ci[0]:+.1%}, {ci[1]:+.1%}]"


def estimated_text(rows: list[dict[str, Any]]) -> str:
    """Units of the builders graded at the haircut estimate (no screen
    price recorded) - audit_settlement 7c's "(szac.)". "?" counts the days
    whose record predates the field but had builders."""
    units = 0.0
    settled = unknown = 0
    for r in rows:
        est = r.get("estimated_builders")
        if est is None:
            if int((r.get("builders") or {}).get("positions", 0) or 0):
                unknown += 1
            continue
        units += float(est.get("units", 0.0))
        settled += int(est.get("settled", 0))
    text = "-" if not settled else f"{units:+.2f} in {settled}"
    if unknown:
        text += f" (+? on {unknown} unrecorded day{'s' if unknown > 1 else ''})"
    return text


# The comparability groups a variant's days fall in (plan 2026-10-05, K7):
# the rules changed on the morning of 10-05 (official dials) and again at the
# stats-only cutover (bet.sofa.epochs), and again with the refit installed
# 2026-10-08 23:42Z, effective 2026-10-09 00:00Z (COUNT_DISPERSION /
# PER_MARKET_K / TENNIS_SCOPED_TABLE): days from 10-09 are never summed with
# earlier ones; and again from 2026-10-12 00:00Z (football player legs print
# as singles - ONE_SIDED_SINGLES - from starts-only samples and curves,
# PLAYER_STARTS_ONLY, token name match); and again from 2026-10-14 00:00Z
# (audit 2026-10-13: measured-sport friendlies / thin competitions refused -
# LEAGUE_RATE_RULE - and a no-curve key's bucket design effect -
# BUCKET_DESIGN_EFFECT). 2026-10-13 itself is a mixed day: the football /
# tennis refit of the audit (curves on the A6 replay with B1 / B2 / B5 / B14 /
# C1, and the CS2 switches B10 / B12) was installed into it at an exact time,
# so its legs printed before stay locked under the old curves - its own
# group, added to neither neighbour. One table row per (variant, group),
# never summed across groups.
EPOCH_GROUPS = ("do 10-04", "10-05 rano", "stats_only", "od 10-09", "od 10-12",
                "10-13 mieszany", "10-14 mieszany", "od 10-15", "10-16 mieszany",
                "10-17 mieszany", "od 10-18", "10-18 mieszany", "od 10-19",
                "od 10-21", "10-21 mieszany", "od 10-22", "od 10-23", "od 10-24",
                "od 10-27", "od 10-28", "od 10-30")
REFIT_EPOCH_FROM_DATE = "2026-10-09"
PLAYER_EPOCH_FROM_DATE = "2026-10-12"
REFIT_1013_MIXED_DATE = "2026-10-13"
AUDIT_EPOCH_FROM_DATE = "2026-10-14"
# The identity plan's switches (entity map, day anchors, tournament day, proven
# absence, player surnames) moved by the operator into 10-14 at 11:30Z: 10-14
# is mixed, and the days after it are their own epoch. "od 10-15" also starts
# the new-market curves (installed 2026-10-15 00:17Z, before 10-15's build)
# and the 1X2 / DNB and CS2 series-rounds switches (2026-10-15 00:00Z).
IDENTITY_1014_MIXED_DATE = "2026-10-14"
IDENTITY_EPOCH_FROM_DATE = "2026-10-15"
# The football refit carrying the league strength learnt in international club
# cups (epochs.FOOTBALL_CUP_STRENGTH_FROM_UTC 2026-10-16 00:00Z), installed
# after 2026-10-15 23:00Z and before 10-16's build - not a mixed day, but a
# refit install starts an epoch; BASKETBALL_DC_PAIR (2026-10-16 00:00Z) too.
# 10-16 itself is the mixed group below (the score markets moved into it).
CUP_STRENGTH_EPOCH_FROM_DATE = "2026-10-16"
# The football score markets and the tennis exact-score complements
# (epochs.FOOTBALL_SCORE_MARKETS / TENNIS_SET_COMPLEMENTS) moved by the
# operator into the built day 2026-10-16 at 07:46Z ("Włącz od teraz"): its
# legs printed before stay locked without them, so 10-16 is mixed - its own
# group, summed with neither "od 10-15" nor "od 10-17"; the days after it
# are the new epoch - which also starts epochs.PLAYER_SAMPLE_GATES
# (2026-10-17 00:00Z: a footballer's lineup-market leg without the sample-
# shape gates); moving either switch must move this boundary.
SCORE_MARKETS_1016_MIXED_DATE = "2026-10-16"
SCORE_MARKETS_EPOCH_FROM_DATE = "2026-10-17"
# The football supremacy stretches (epochs.FOOTBALL_GOALS_STRETCH /
# FOOTBALL_COUNT_STRETCH / FOOTBALL_PLAYER_STRETCH) and the football
# refit carrying them, moved by the operator into the built day
# 2026-10-17 at 13:37Z ("teraz rób wszystko i włączaj"): 10-17 is
# mixed - its own group, summed with neither "od 10-17" (which therefore
# holds no day) nor "od 10-18".
STRETCH_1017_MIXED_DATE = "2026-10-17"
STRETCH_EPOCH_FROM_DATE = "2026-10-18"
# The football history curves per line (epochs.LINE_CURVES_FROM_UTC),
# planned for 2026-10-19 00:00Z and moved by the operator into the built day
# 2026-10-18 at 12:48Z: 10-18 is mixed - its own group, summed with neither
# "od 10-18" (which therefore holds no day) nor "od 10-19".
LINE_CURVES_1018_MIXED_DATE = "2026-10-18"
LINE_CURVES_EPOCH_FROM_DATE = "2026-10-19"
# The CS2 player share (epochs.CS2_PLAYER_SHARE_FROM_UTC, 2026-10-21 00:00Z):
# 40-map share, per-stat shrinkage, headshots from the exposure.
CS2_PLAYER_SHARE_EPOCH_FROM_DATE = "2026-10-21"
# RESOLVE's reserve / youth retry (epochs.SQUAD_SEARCH_RETRY_FROM_UTC) was
# planned for 2026-10-22 00:00Z and moved by the operator into 10-21 09:20Z
# with ENTITY_MISS_PER_DAY (10-21 mixed); "od 10-22" is the first day with
# every switch of 10-21 on from its 00:00Z.
SQUAD_SEARCH_EPOCH_FROM_DATE = "2026-10-22"
# The late RESOLVE pass (epochs.LATE_RESOLVE_FROM_UTC), moved by the operator
# into the built day 2026-10-21 ("Włączaj od razu!"): fixtures RESOLVE missed
# in the morning reach that day's coupon after its first print, so 10-21 is
# mixed - its own group, summed with neither "od 10-21" (which therefore
# holds no day) nor "od 10-22".
LATE_RESOLVE_1021_MIXED_DATE = "2026-10-21"
# The measured sports' rolling day window (epochs.SPORT_LATE_WINDOW_FROM_UTC,
# 2026-10-23 00:00Z, operator 2026-10-22): from 10-23 a day's coupon holds its
# sport games up to D+1 05:00Z (the evening rebuild's), so the coupon's scope
# changes - a new epoch, not a mixed day (the switch is at the day's 00:00Z).
# The same group holds epochs.LEAGUE_SEASON_RESTART_FROM_UTC (2026-10-23
# 00:00Z): basketball's league rate restarts after an off-season, which moves
# basketball p and so what prints.
SPORT_LATE_WINDOW_EPOCH_FROM_DATE = "2026-10-23"
# No installed football / tennis curve fitted from our settled days alone
# (epochs.LIVE_ONLY_CURVE_REFUSED_FROM_UTC, 2026-10-24 00:00Z): the listed
# keys (config/sofa_live_only_curves.json) read as markets without a curve -
# a new epoch, not a mixed day (the switch is at the day's 00:00Z).
# The same group holds the hockey curve refitted 2026-10-23, read from
# 2026-10-24 00:00Z (config/sofa_sport_confidence_calibration.next.2026-10-24
# .json; docs/sofa/history/REFIT_HOKEJ_SIATKOWKA_2026-10-23.md).
# The coverage audit's P-switches (epochs, "Coverage audit 2026-10-23") also
# start 2026-10-24 00:00Z: same group (AUDYT_POKRYCIA_WDROZENIE_2026-10-23.md).
LIVE_ONLY_CURVE_EPOCH_FROM_DATE = "2026-10-24"
# The analyst audit (operator's go 2026-10-26): the read set narrows to 20
# matches (epochs.READ_SCOPE_FROM_UTC, 2026-10-27 00:00Z) and a read removal
# must name a dated fact or an artifact defect (report_check, contract) -
# fewer legs read and fewer removed, so what prints changes: a new epoch.
READ_SCOPE_EPOCH_FROM_DATE = "2026-10-27"
# The confidence review of 2026-10-27 (operator "popraw wszystkie błędy"):
# epochs.JOINT_FILLED_SIDE_CHAIN (R1) and TENNIS_SET_HANDICAP_NEIGHBOURS (R2)
# from 2026-10-28 00:00Z, and the basketball / CS2 curves made monotone
# (config/sofa_sport_confidence_calibration.next.2026-10-28.json) - p and
# confidence move on what prints: a new epoch.
CONFIDENCE_REVIEW_EPOCH_FROM_DATE = "2026-10-28"
# Results awarded at the table out of the football samples and rating
# (epochs.AWARDED_EXCLUDED_FROM_UTC, 2026-10-30 00:00Z; verification of
# 2026-10-29) - football p moves on what prints: a new epoch.
AWARDED_EXCLUDED_EPOCH_FROM_DATE = "2026-10-30"


def epoch_group(row: dict[str, Any]) -> str:
    if row.get("epoch") == "stats_only":
        if str(row.get("date", "")) >= AWARDED_EXCLUDED_EPOCH_FROM_DATE:
            return "od 10-30"
        if str(row.get("date", "")) >= CONFIDENCE_REVIEW_EPOCH_FROM_DATE:
            return "od 10-28"
        if str(row.get("date", "")) >= READ_SCOPE_EPOCH_FROM_DATE:
            return "od 10-27"
        if str(row.get("date", "")) >= LIVE_ONLY_CURVE_EPOCH_FROM_DATE:
            return "od 10-24"
        if str(row.get("date", "")) >= SPORT_LATE_WINDOW_EPOCH_FROM_DATE:
            return "od 10-23"
        if str(row.get("date", "")) >= SQUAD_SEARCH_EPOCH_FROM_DATE:
            return "od 10-22"
        if str(row.get("date", "")) == LATE_RESOLVE_1021_MIXED_DATE:
            return "10-21 mieszany"
        if str(row.get("date", "")) >= CS2_PLAYER_SHARE_EPOCH_FROM_DATE:
            return "od 10-21"
        if str(row.get("date", "")) >= LINE_CURVES_EPOCH_FROM_DATE:
            return "od 10-19"
        if str(row.get("date", "")) == LINE_CURVES_1018_MIXED_DATE:
            return "10-18 mieszany"
        if str(row.get("date", "")) >= STRETCH_EPOCH_FROM_DATE:
            return "od 10-18"
        if str(row.get("date", "")) == STRETCH_1017_MIXED_DATE:
            return "10-17 mieszany"
        if str(row.get("date", "")) >= SCORE_MARKETS_EPOCH_FROM_DATE:
            return "od 10-17"
        if str(row.get("date", "")) == SCORE_MARKETS_1016_MIXED_DATE:
            return "10-16 mieszany"
        if str(row.get("date", "")) >= IDENTITY_EPOCH_FROM_DATE:
            return "od 10-15"
        if str(row.get("date", "")) == IDENTITY_1014_MIXED_DATE:
            return "10-14 mieszany"
        if str(row.get("date", "")) == REFIT_1013_MIXED_DATE:
            return "10-13 mieszany"
        if str(row.get("date", "")) >= PLAYER_EPOCH_FROM_DATE:
            return "od 10-12"
        if str(row.get("date", "")) >= REFIT_EPOCH_FROM_DATE:
            return "od 10-09"
        return "stats_only"
    if str(row.get("date", "")) < "2026-10-05":
        return "do 10-04"
    return "10-05 rano"


def render(rows: list[dict[str, Any]], variant: str | None) -> list[str]:
    out: list[str] = []
    by_variant: dict[str, list[dict[str, Any]]] = {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_variant.setdefault(r["variant"], []).append(r)
        if not str(r["variant"]).startswith("measure:"):
            grouped.setdefault(f"{r['variant']} [{epoch_group(r)}]", []).append(r)
    bets = sorted(
        grouped,
        key=lambda k: (k.rsplit(" [", 1)[0],
                       EPOCH_GROUPS.index(k.rsplit(" [", 1)[1].rstrip("]"))),
    )
    out += [
        "| variant | days | positions | settled | won | lost | units "
        "| of which estimated builders | ROI | ROI 95% (by match) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for v in bets:
        if variant and v.rsplit(" [", 1)[0] != variant:
            continue
        t = totals(grouped[v])
        roi = "-" if t["roi"] is None else f"{t['roi']:+.1%}"
        out.append(
            f"| {v} | {t['days']} | {t['positions']} | {t['settled']} | "
            f"{t['won']} | {t['lost']} | {t['units']:+.2f} | "
            f"{estimated_text(grouped[v])} | {roi} | "
            f"{interval_text(grouped[v])} |"
        )
    out += ["", f"Each variant is split by rule epoch ({' / '.join(EPOCH_GROUPS)}): "
            "the coupon before and after each cutover is not one experiment, "
            "so the groups are never added."]
    out += ["", f"A 3% edge needs ~{BETS_FOR_3PCT} settled positions to show at "
            "2 sigma; a ROI over a few dozen is noise until its interval says "
            "otherwise. CLV (audit_clv.py) answers sooner. An estimated builder "
            "is graded "
            "at odds_if_product x the haircut (no screen price recorded) - "
            "its units are not a price Superbet printed."]
    if variant and variant in by_variant:
        fams: dict[str, dict[str, float]] = {}
        for r in by_variant[variant]:
            for fam, f in (r.get("by_family") or {}).items():
                if not f:
                    continue
                acc = fams.setdefault(fam, {"settled": 0, "won": 0, "units": 0.0})
                acc["settled"] += int(f.get("settled", f.get("n", 0)) or 0)
                acc["won"] += int(f.get("won", f.get("wins", 0)) or 0)
                if "units" in f:
                    acc["units"] += float(f["units"])
                elif "roi" in f and f.get("n"):
                    acc["units"] += float(f["roi"]) * int(f["n"])
        if fams:
            out += [
                "",
                f"## {variant} by family",
                "",
                "| family | settled | won | units | ROI |",
                "|---|---|---|---|---|",
            ]
            for fam, a in sorted(fams.items(), key=lambda kv: -kv[1]["settled"]):
                roi = f"{a['units'] / a['settled']:+.1%}" if a["settled"] else "-"
                out.append(
                    f"| {fam} | {int(a['settled'])} | {int(a['won'])} | "
                    f"{a['units']:+.2f} | {roi} |"
                )
    measures = sorted(v for v in by_variant if v.startswith("measure:"))
    if measures and not variant:
        out += [
            "",
            "| measurement | days | sides | mean fair p | hit | gap pp |",
            "|---|---|---|---|---|---|",
        ]
        for v in measures:
            sides = hit_w = fair_w = 0.0
            days = 0
            for r in by_variant[v]:
                f = r.get("favourite_side") or {}
                n = float(f.get("sides", 0) or 0)
                if n:
                    days += 1
                    sides += n
                    hit_w += n * float(f["hit"])
                    fair_w += n * float(f["mean_fair_p"])
            if sides:
                out.append(
                    f"| {v} | {days} | {int(sides)} | {fair_w / sides:.3f} | "
                    f"{hit_w / sides:.3f} | {100 * (hit_w - fair_w) / sides:+.1f} |"
                )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--variant")
    args = parser.parse_args()
    runs_dir = SofaConfig.from_env().runs_dir
    if not ledger_path(runs_dir).exists():
        print(f"no ledger at {ledger_path(runs_dir)} - run record_results.py first")
        return 2
    rows = load(runs_dir, args.start, args.end)
    print(f"# Ledger {args.start}..{args.end} (each variant alone; never pooled)\n")
    print("\n".join(render(rows, args.variant)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
