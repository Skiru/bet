#!/usr/bin/env python3
"""Verify every variant of one day against its own sources.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date 2026-09-30

audit_coupon.py covers the official coupon. This covers what sits beside it:
the four sport coupons and WARIANT WSZYSTKIE. Every check re-derives from the
files on disk, not from the artifact's own fields:

  S1  the sport coupon's JSON names its PDF (sha256)
  S2  every new (unlocked) leg obeys the rule it was printed under: fair_p,
      odds, margin, no player line, kickoff inside the window, price age
  S3  every leg's price and devig recomputed from the raw snapshot record it
      names (price_fetched_at_utc): odds, the whole group, fair_p, margin
  S4  one leg per event, no more than max_legs, no vetoed leg printed
  S5  the selection replayed from the snapshots as they stood at build time
      gives the same legs (locked legs taken as printed)
  M1  WARIANT WSZYSTKIE names its PDF (sha256)
  M2  each section equals its source as the source stands now: the official
      printed singles / builders, each sport's legs - a source rebuilt after
      the assembly makes the variant stale
  M3  nothing of either was written into runs/sofa/<d>/

No network. Exit 0 when nothing is found, 1 with findings, 2 on a bad file.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import cs2, shadow  # noqa: E402
from bet.sofa import multi_coupon as mc  # noqa: E402
from bet.sofa import sport_coupon as sc  # noqa: E402
from bet.sofa.confidence import printed_builders, printed_singles  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402

TOL = 1e-4


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def leg_id(leg: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(leg.get(k) for k in sc.LEG_KEY)


def _shape(sport: sc.SportKey, leg: dict[str, Any]) -> cs2.Shape:
    if sport == "cs2":
        return cs2.group_shape(str(leg["family"]))
    return shadow.group_shape(sport, int(leg["market_id"]))


def _record_group(
    snaps: list[dict[str, Any]], leg: dict[str, Any]
) -> dict[str, float] | None:
    """The leg's whole outcome group in the snapshot record it names."""
    key = [
        k
        for k in ("market_id", "family", "period", "map_nr", "subject", "line")
        if k in leg
    ]
    for rec in snaps:
        if (
            rec["superbet_event_id"] != leg["superbet_event_id"]
            or rec["fetched_at_utc"] != leg["price_fetched_at_utc"]
        ):
            continue
        group = {
            ln["side"]: float(ln["odds"])
            for ln in rec["lines"]
            if all(ln.get(k) == leg.get(k) for k in key)
        }
        if group:
            return group
    return None


def audit_sport(runs_dir: str, sport: sc.SportKey, date: str) -> list[str]:
    d = sc.day_dir(runs_dir, sport, date)
    path = d / sc.COUPON_FILE
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    out: list[str] = []
    why = sc.pdf_matches(doc, path, d / sc.pdf_name(sport, date))
    if why:
        out.append(f"S1 {sport}: {why}")
    rule_doc = doc["rule"]
    rule = sc.Rule(
        rule_doc["floor"],
        rule_doc["max_overround"],
        rule_doc["min_odds"],
        rule_doc["max_legs"],
    )
    at = _utc(doc["created_at_utc"])
    snaps = {
        src: sc.load_snapshots(sc.day_dir(runs_dir, sport, src) / cs2.SNAPSHOTS_FILE)
        for src in (date, sc.next_date(date))
    }
    legs = doc["legs"]
    for leg in legs:
        name = (
            f"{sport} {leg['match_name']} {leg['family']} {leg['side']} "
            f"{leg.get('line')}"
        )
        if leg.get("locked"):
            continue
        if leg["fair_p"] < rule.floor - TOL:
            out.append(f"S2 {name}: fair_p {leg['fair_p']} below floor")
        if leg["odds"] < round(rule.min_odds, 4) - TOL:
            out.append(f"S2 {name}: odds {leg['odds']} below min")
        if leg["overround"] > rule.max_overround + TOL:
            out.append(f"S2 {name}: margin {leg['overround']} above max")
        if sc.is_player_family(str(leg["family"])):
            out.append(f"S2 {name}: a player line")
        kickoff = _utc(leg["kickoff_utc"])
        if kickoff - at < sc.KICKOFF_MARGIN or kickoff >= sc.day_end(date):
            out.append(f"S2 {name}: kickoff outside the window at build")
        if at - _utc(leg["price_fetched_at_utc"]) > sc.MAX_PRICE_AGE:
            out.append(f"S2 {name}: price older than {sc.MAX_PRICE_AGE}")
        src = leg.get("source_date") or date
        group = _record_group(snaps.get(src, []), leg)
        if group is None:
            out.append(
                f"S3 {name}: no snapshot record at {leg['price_fetched_at_utc']}"
            )
            continue
        if group != {k: float(v) for k, v in leg["group_odds"].items()}:
            out.append(f"S3 {name}: group odds {leg['group_odds']} != snapshot {group}")
        if abs(group.get(leg["side"], -1) - leg["odds"]) > TOL:
            out.append(
                f"S3 {name}: odds {leg['odds']} != snapshot {group.get(leg['side'])}"
            )
        fair = cs2.group_fair(group, _shape(sport, leg))
        if fair is None:
            out.append(f"S3 {name}: the snapshot group is not a whole market")
        else:
            if abs(fair[leg["side"]] - leg["fair_p"]) > TOL:
                out.append(
                    f"S3 {name}: fair_p {leg['fair_p']} != {fair[leg['side']]:.4f}"
                )
            if abs(cs2.group_overround(group) - leg["overround"]) > TOL:
                out.append(
                    f"S3 {name}: margin {leg['overround']} recomputes differently"
                )
    events = [leg["superbet_event_id"] for leg in legs]
    if len(events) != len(set(events)):
        out.append(f"S4 {sport}: an event carries two legs")
    if len(legs) > rule.max_legs:
        out.append(f"S4 {sport}: {len(legs)} legs > max {rule.max_legs}")
    vetoes = sc.load_vetoes(d)
    for leg in legs:
        if not leg.get("locked") and any(sc.veto_matches(v, leg) for v in vetoes):
            out.append(f"S4 {sport}: vetoed leg printed: {leg['match_name']}")
    # S5 - replay the selection from the snapshots as they stood at build time.
    events_then: dict[str, Any] = {}
    for src in (date, sc.next_date(date)):
        then = [s for s in snaps[src] if _utc(s["fetched_at_utc"]) <= at]
        for eid, ev in sc.latest_events(sport, then).items():
            if eid not in events_then:
                ev.source_date = src
                events_then[eid] = ev
    counts: dict[str, int] = {}
    cands = sc.candidates(sport, events_then, at, rule, counts, until=sc.day_end(date))
    locked = [leg for leg in legs if leg.get("locked")]
    replay, _ = sc.select(sport, cands, vetoes, rule, locked)
    if {leg_id(x) for x in replay} != {leg_id(x) for x in legs}:
        missing = {leg_id(x) for x in replay} - {leg_id(x) for x in legs}
        extra = {leg_id(x) for x in legs} - {leg_id(x) for x in replay}
        out.append(
            f"S5 {sport}: replayed selection differs: would print {sorted(missing)}, "
            f"printed {sorted(extra)}"
        )
    return out


def audit_multi(runs_dir: str, date: str) -> list[str]:
    out_dir = mc.multi_dir(runs_dir, date)
    path = out_dir / mc.MULTI_FILE
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    out: list[str] = []
    pdf = out_dir / mc.pdf_name(date)
    if not pdf.exists() or sc.file_sha256(pdf) != doc.get("pdf_sha256"):
        out.append("M1 multi: the PDF is not the one the JSON was printed as")
    for key, sec in doc["sections"].items():
        if sec["status"] != "OK":
            continue
        if key == "official":
            conf_path = mc.official_dir(runs_dir, date) / "08_confidence.json"
            conf = json.loads(conf_path.read_text(encoding="utf-8"))
            want = [
                (
                    s["sofascore_event_id"],
                    s["market"],
                    s["line"],
                    s["direction"],
                    s["offered_odds"],
                )
                for s in printed_singles(conf)
            ]
            got = [
                (
                    p["source"]["sofascore_event_id"],
                    p["source"]["market"],
                    p["source"]["line"],
                    p["source"]["direction"],
                    p["odds"],
                )
                for p in sec["singles"]
            ]
            if want != got:
                out.append(
                    "M2 official: the section is not what KUPON prints now "
                    "(rebuild the variant)"
                )
            wb = [b["sofascore_event_id"] for b in printed_builders(conf)]
            if wb != [b["source"]["sofascore_event_id"] for b in sec["builders"]]:
                out.append("M2 official builders differ from KUPON's")
            continue
        sp: sc.SportKey = key
        spath = sc.day_dir(runs_dir, sp, date) / sc.COUPON_FILE
        if not spath.exists():
            out.append(f"M2 {key}: its source coupon is gone")
            continue
        sdoc = json.loads(spath.read_text(encoding="utf-8"))
        want_legs = [(leg_id(x), x["odds"], x["fair_p"]) for x in sdoc["legs"]]
        got_legs = [
            (leg_id(p["source"]), p["odds"], p["probability"]) for p in sec["singles"]
        ]
        if want_legs != got_legs:
            out.append(
                f"M2 {key}: the section is not what its coupon prints now "
                "(rebuild the variant)"
            )
    for name in (mc.MULTI_FILE, mc.pdf_name(date), sc.COUPON_FILE):
        if (mc.official_dir(runs_dir, date) / name).exists():
            out.append(f"M3 {name} found inside runs/sofa/{date}/")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    runs_dir = SofaConfig.from_env().runs_dir
    findings: list[str] = []
    checked: list[str] = []
    try:
        for sport in sc.SPORT_KEYS:
            if (sc.day_dir(runs_dir, sport, args.date) / sc.COUPON_FILE).exists():
                checked.append(sport)
            findings += audit_sport(runs_dir, sport, args.date)
        if (mc.multi_dir(runs_dir, args.date) / mc.MULTI_FILE).exists():
            checked.append("multi")
        findings += audit_multi(runs_dir, args.date)
    except (OSError, ValueError, KeyError) as exc:
        print(f"AUDIT_VARIANTS: bad file: {type(exc).__name__}: {exc}")
        return 2
    print(
        f"# audit_variants {args.date} - checked: {', '.join(checked) or 'nothing'}\n"
    )
    for f in findings:
        print(f"- {f}")
    if not findings:
        print("no findings" + ("" if checked else " (nothing to check - not a pass)"))
    print(
        "\nSOFA_SUMMARY: "
        + json.dumps(
            {
                "stage": "AUDIT_VARIANTS",
                "verdict": "OK" if not findings else "PARTIAL",
                "metrics": {"checked": checked, "findings": len(findings)},
            }
        )
    )
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
