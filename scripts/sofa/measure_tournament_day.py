#!/usr/bin/env python3
"""Tournament-day match backtest (identity plan K3; read-only evidence, but
it ASKS THE BRIDGE: one request per (unique tournament, day) not yet in
sofa_day_listing).

For hockey / basketball / volleyball events of the window whose Superbet
tournament the entity map knows (sofa_tournament_map), the tournament's
games of the day are fetched once (bet.sofa.day_listing, cached), and
day_listing.tournament_day_match is graded over a grid of thresholds:

- precision on IDENTIFIED events: their ids hidden, the names alone must
  pick the pinned game (every wrong pick listed - one is a wrong leg);
- recovery on NOT_IDENTIFIED events where neither side has an id today:
  what the rule would identify (listed for a manual read; SHADOW_SETTLE's
  later find compared where it exists).

Only the tournament-days of the second group are asked, plus at most
--precision-days more of IDENTIFIED events for a precision sample. A
refusal stops the run (no retry); what was fetched stays cached.

  PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tournament_day.py \
      --from 2026-10-05 --to 2026-10-14 [--precision-days 60] [--offline] \
      [--md-out f] [--json-out f]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import day_listing as dl  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.db import get_connection, migrate  # noqa: E402
from bet.sofa.errors import CircuitOpenError, ProviderError  # noqa: E402
from bet.sofa.sport_identity import TeamResolver  # noqa: E402
from scripts.sofa import measure_day_anchor as mda  # noqa: E402

SPORTS = {
    "hockey": "ice-hockey",
    "basketball": "basketball",
    "volleyball": "volleyball",
}
MIN_SCORES = (50.0, 60.0, 70.0, 82.0)
LEADS = (10.0, 20.0, 30.0)


def _kick(r: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(str(r["kickoff_utc"]).replace("Z", "+00:00"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--from", dest="first", required=True)
    ap.add_argument("--to", dest="last", required=True)
    ap.add_argument("--precision-days", type=int, default=60)
    ap.add_argument("--offline", action="store_true", help="cache only, no request")
    ap.add_argument("--md-out", default=None)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()
    config = SofaConfig.from_env()
    migrate(config.db_path)
    conn = get_connection(config.db_path)
    resolver = TeamResolver(conn, int(time.time()), learned=True)
    tmap: dict[tuple[str, str], set[int]] = defaultdict(set)
    for sp, t, c in conn.execute(
        "SELECT sport, superbet_tournament, competition_id FROM sofa_tournament_map"
    ):
        tmap[(sp, t)].add(int(c))
    recs = [
        r
        for r in mda.records(config.runs_dir, args.first, args.last)
        if r.get("sport") in SPORTS
    ]
    settled = mda.settle_found(config.runs_dir)
    target, control = [], []
    for r in recs:
        comps = tmap.get((r["sport"], str(r.get("tournament"))))
        if not comps:
            continue
        if r["status"] == "IDENTIFIED":
            control.append(r)
        elif all(
            resolver.team_id(r["sport"], n) is None for n in (r["team1"], r["team2"])
        ):
            target.append(r)
    want = {
        (c, str(r["kickoff_utc"])[:10])
        for r in target
        for c in tmap[(r["sport"], str(r["tournament"]))]
    }
    control_days = sorted(
        {
            (c, str(r["kickoff_utc"])[:10])
            for r in control
            for c in tmap[(r["sport"], str(r["tournament"]))]
        }
        - want
    )
    random.Random(20261014).shuffle(control_days)
    want |= set(control_days[: args.precision_days])
    client = None
    if not args.offline:
        from bet.sofa.client import SofascoreClient

        client = SofascoreClient(config)
    listings: dict[tuple[int, str], list[dict[str, Any]]] = {}
    asked = served = 0
    refused: str | None = None
    # A fixed shuffle, not sorted: 2026-10-14's first run met a lone 403 on
    # the first (lowest) tournament id and stopped with nothing.
    order = sorted(want)
    random.Random(1014).shuffle(order)
    for ut, day in order:
        hit = dl.cached(conn, dl.TOURNAMENT_DAY, str(ut), day)
        if hit is not None:
            listings[(ut, day)] = list(hit.get("events") or [])
            served += 1
            continue
        if client is None or refused:
            continue
        try:
            events, _ = dl.tournament_day_events(client, conn, ut, day)
            conn.commit()
            listings[(ut, day)] = events
            asked += 1
        except (ProviderError, CircuitOpenError) as exc:
            refused = str(exc)
    res: dict[str, Any] = {
        "first": args.first,
        "last": args.last,
        "asked": asked,
        "from_cache": served,
        "refused": refused,
        "tournament_days": len(want),
        "grid": {},
    }

    def candidates(r: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for c in tmap[(r["sport"], str(r["tournament"]))]:
            out += listings.get((c, str(r["kickoff_utc"])[:10]), [])
        return out

    for ms in MIN_SCORES:
        for ld in LEADS:
            prec: Counter[str] = Counter()
            wrong = []
            for r in control:
                ev = candidates(r)
                if not ev:
                    prec["no_listing"] += 1
                    continue
                f = dl.tournament_day_match(
                    r["sport"],
                    r["team1"],
                    r["team2"],
                    _kick(r),
                    ev,
                    SPORTS[r["sport"]],
                    ms,
                    ld,
                )
                if f["status"] != "IDENTIFIED":
                    prec[f["reason"]] += 1
                elif int(f["event"]["id"]) == int(r["sofascore_event_id"]):
                    prec["correct"] += 1
                else:
                    prec["WRONG"] += 1
                    wrong.append(
                        {
                            "match": r["match_name"],
                            "kickoff": r["kickoff_utc"],
                            "pinned": r["sofascore_event_id"],
                            "picked": f["event"]["id"],
                            "picked_match": f"{f['event']['homeTeam']['name']} - "
                            f"{f['event']['awayTeam']['name']}",
                        }
                    )
            rec: Counter[str] = Counter()
            picks = []
            for r in target:
                ev = candidates(r)
                if not ev:
                    rec["no_listing"] += 1
                    continue
                f = dl.tournament_day_match(
                    r["sport"],
                    r["team1"],
                    r["team2"],
                    _kick(r),
                    ev,
                    SPORTS[r["sport"]],
                    ms,
                    ld,
                )
                rec[f["status"] if f["status"] == "IDENTIFIED" else f["reason"]] += 1
                if f["status"] == "IDENTIFIED":
                    s = settled.get(str(r["superbet_event_id"]))
                    picks.append(
                        {
                            "sport": r["sport"],
                            "match": r["match_name"],
                            "kickoff": r["kickoff_utc"],
                            "reason": r.get("reason"),
                            "picked": f["event"]["id"],
                            "picked_match": f"{f['event']['homeTeam']['name']} - "
                            f"{f['event']['awayTeam']['name']}",
                            "scores": f["name_scores"],
                            "rival": f["rival_score"],
                            "settle": None if s is None else s["sofascore_event_id"],
                        }
                    )
            res["grid"][f"min{ms:g}_lead{ld:g}"] = {
                "control": dict(prec),
                "wrong": wrong,
                "target": dict(rec),
                "picks": picks,
            }
    res["control_events"], res["target_events"] = len(control), len(target)
    lines = [
        f"# Tournament-day match {args.first}..{args.last}",
        "",
        f"Tournament-days {len(want)}: asked {asked}, from cache {served}, "
        f"refused {refused}. IDENTIFIED controls {len(control)}, targets "
        f"(no side with an id) {len(target)}.",
        "",
        "| min score | lead | IDENTIFIED, ids hidden | targets |",
        "|---|---|---|---|",
    ]
    for key, g in res["grid"].items():
        ms_s, ld_s = key.removeprefix("min").split("_lead")
        lines.append(f"| {ms_s} | {ld_s} | {g['control']} | {g['target']} |")
    for key, g in res["grid"].items():
        for w in g["wrong"]:
            lines.append(f"- {key} WRONG: {w}")
    md = "\n".join(lines) + "\n"
    print(md)
    if args.md_out:
        Path(args.md_out).write_text(md, encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8"
        )
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
