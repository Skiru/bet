#!/usr/bin/env python3
"""Record Superbet's closing price of every printed official / WARIANT leg.

For each single on 08_confidence.json (the official PDF) and
08_confidence_wariant.json (the WARIANT) whose kickoff is between
clv.CLOSE_MIN_MINUTES and clv.CLOSE_MAX_MINUTES away, re-ask Superbet through
the same OfferFetcher OFFER uses and append the leg's side and its partner to
runs/sofa/<d>/closing.jsonl. audit_clv.py reads the latest record per leg.
Superbet only - no Sofascore, no bridge. Prints, stakes and changes nothing.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/capture_closing.py --date <d> --loop
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import RootModel

from bet.sofa.clv import CLOSE_MAX_MINUTES, CLOSE_MIN_MINUTES
from bet.sofa.confidence import printed_builders, printed_singles
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture, FixtureOffer
from bet.sofa.offer import OfferFetcher
from bet.sofa.superbet import SuperbetClient

VARIANTS = {"official": "08_confidence.json", "wariant": "08_confidence_wariant.json"}
LOOP_SLEEP_S = 300


def leg_key(leg: dict[str, Any]) -> str:
    return (f"{leg['sofascore_event_id']}|{leg['market']}|{leg.get('subject') or ''}"
            f"|{leg['line']}|{leg['direction']}")


def printed_legs(day_dir: Path) -> list[tuple[str, dict[str, Any]]]:
    """What the PDFs print - confidence.printed_singles / printed_builders, the
    same selection build_coupon_pdf uses - as (variant, leg). A builder's legs
    are their own variant ("<variant>:builder_leg"): Superbet prices the slip,
    not the product of its legs, so a leg's CLV is not the slip's."""
    out: list[tuple[str, dict[str, Any]]] = []
    for variant, name in VARIANTS.items():
        path = day_dir / name
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        out += [(variant, leg) for leg in printed_singles(doc)]
        for b in printed_builders(doc):
            for leg in b.get("legs", []):
                out.append((f"{variant}:builder_leg", {
                    "sofascore_event_id": b["sofascore_event_id"],
                    "kickoff_utc": b["kickoff_utc"], "market": leg["market"],
                    "subject": leg.get("subject") or "", "line": leg["line"],
                    "direction": leg["direction"], "offered_odds": leg["odds"]}))
    return out


def minutes_to(kickoff_utc: str, now: datetime) -> float:
    ko = datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
    return (ko - now).total_seconds() / 60.0


def due(legs: list[tuple[str, dict[str, Any]]], now: datetime
        ) -> list[tuple[str, dict[str, Any]]]:
    return [(v, leg) for v, leg in legs
            if CLOSE_MIN_MINUTES <= minutes_to(leg["kickoff_utc"], now)
            <= CLOSE_MAX_MINUTES]


def close_record(variant: str, leg: dict[str, Any], offer: FixtureOffer,
                 now: datetime) -> dict[str, Any] | None:
    """The leg's side and partner on the re-asked offer, or None if gone."""
    for rung in offer.rungs:
        if (rung.market, rung.subject, rung.line) != (
                leg["market"], leg.get("subject") or "", leg["line"]):
            continue
        over = leg["direction"] == "OVER"
        side, partner = ((rung.over_odds, rung.under_odds) if over
                         else (rung.under_odds, rung.over_odds))
        if side is None:
            return None
        return {
            "variant": variant, "leg_key": leg_key(leg),
            "sofascore_event_id": leg["sofascore_event_id"],
            "odds_taken": leg["offered_odds"], "odds_close": side,
            "partner_close": partner, "fetched_at_utc": now.isoformat(),
            "minutes_before": round(minutes_to(leg["kickoff_utc"], now), 1),
        }
    return None


def run_once(day_dir: Path, fetcher: Any, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    legs = due(printed_legs(day_dir), now)
    if not legs:
        return 0
    raw = (day_dir / "02_fixtures.json").read_bytes()
    fixtures = {f.sofascore_event_id: f
                for f in RootModel[list[Fixture]].model_validate_json(raw).root}
    wanted = sorted({leg["sofascore_event_id"] for _, leg in legs})
    offers: dict[int, FixtureOffer] = {}
    for e in wanted:
        if e not in fixtures:
            continue
        # One event at a time: a pulled event or a timeout must not cost the
        # others their close (the leg is recorded as missing instead).
        try:
            for o in fetcher.fetch_offers([fixtures[e]]):
                offers[o.sofascore_event_id] = o
        except Exception as exc:  # noqa: BLE001 - network: log and go on
            print(json.dumps({"fetch_failed": e, "error": repr(exc)[:200]}),
                  flush=True)
    written = 0
    with (day_dir / "closing.jsonl").open("a", encoding="utf-8") as f:
        for variant, leg in legs:
            offer = offers.get(leg["sofascore_event_id"])
            rec = close_record(variant, leg, offer, now) if offer else None
            if rec is None:
                rec = {"variant": variant, "leg_key": leg_key(leg),
                       "sofascore_event_id": leg["sofascore_event_id"],
                       "missing": True, "fetched_at_utc": now.isoformat(),
                       "minutes_before": round(minutes_to(leg["kickoff_utc"], now), 1)}
            f.write(json.dumps(rec) + "\n")
            written += 1
    return written


PID_FILE = "capture_closing.pid"


def loop_holder(day_dir: Path) -> int | None:
    """The pid of a live loop for this day, else None (a stale file is not one).

    Two loops for one day doubled every closing request; the second refuses,
    the way cs2_daily / shadow_daily do.
    """
    path = day_dir / PID_FILE
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    if pid == os.getpid():
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        return pid
    return pid


def claim_loop(day_dir: Path) -> None:
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / PID_FILE).write_text(str(os.getpid()), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--loop", action="store_true",
                    help=f"repeat every {LOOP_SLEEP_S}s until the last leg starts")
    args = ap.parse_args()
    day_dir = Path(SofaConfig.from_env().runs_dir) / args.date
    if args.loop:
        holder = loop_holder(day_dir)
        if holder is not None:
            print(f"capture_closing loop for {args.date} already runs (pid {holder}); "
                  "not starting a second one", file=sys.stderr)
            return 2
        claim_loop(day_dir)
    fetcher = OfferFetcher(SuperbetClient(
        base_url="https://production-superbet-offer-pl.freetls.fastly.net"))
    while True:
        try:
            n = run_once(day_dir, fetcher)
        except Exception as exc:  # noqa: BLE001 - an unattended loop survives
            print(json.dumps({"pass_failed": repr(exc)[:300]}), flush=True)
            n = 0
        now = datetime.now(UTC)
        print(json.dumps({"ts_utc": now.isoformat(), "closes_written": n}), flush=True)
        legs = printed_legs(day_dir)
        if not args.loop or not legs or all(
                minutes_to(leg["kickoff_utc"], now) < CLOSE_MIN_MINUTES
                for _, leg in legs):
            return 0
        time.sleep(LOOP_SLEEP_S)


if __name__ == "__main__":
    sys.exit(main())
