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
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import RootModel

from bet.sofa.clv import CLOSE_MAX_MINUTES, CLOSE_MIN_MINUTES
from bet.sofa.confidence import (
    coupon_artifact,
    is_sheet_sport,
    printed_builders,
    printed_singles,
)
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture, FixtureOffer
from bet.sofa.cs2 import append_records
from bet.sofa.offer import OfferFetcher
from bet.sofa.superbet import SuperbetClient
from scripts.sofa.cs2_daily import _command_of, already_running

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
        # The official coupon is the coupon artifact (11_coupon.json on a
        # stats-only day, K3); its measured-sport legs close from their own
        # snapshots, not from this football / tennis offer fetch.
        path = coupon_artifact(day_dir) if variant == "official" else day_dir / name
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        out += [(variant, leg) for leg in printed_singles(doc) if is_sheet_sport(leg)]
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
    # Why an event has no offer. A fetch that failed is not a market Superbet
    # pulled: audit_clv must be able to skip it and keep an earlier good close
    # (a failed last pass used to erase it - 1 of 96 legs on 2026-10-01).
    errors: dict[int, str] = {}
    for e in wanted:
        if e not in fixtures:
            continue
        # One event at a time: a pulled event or a timeout must not cost the
        # others their close (the leg is recorded as missing instead).
        seen = len(getattr(fetcher, "errors", []) or [])
        try:
            for o in fetcher.fetch_offers([fixtures[e]]):
                offers[o.sofascore_event_id] = o
        except Exception as exc:  # noqa: BLE001 - network: log and go on
            errors[e] = repr(exc)[:200]
            print(json.dumps({"fetch_failed": e, "error": errors[e]}), flush=True)
            continue
        # OfferFetcher keeps a listing's error to itself and drops a fixture
        # whose every listing raised; that is a failed fetch too.
        new_errors = (getattr(fetcher, "errors", []) or [])[seen:]
        if e not in offers and new_errors:
            errors[e] = "; ".join(f"{sid}: {msg}" for sid, msg in new_errors)[:200]
    records: list[dict[str, Any]] = []
    for variant, leg in legs:
        offer = offers.get(leg["sofascore_event_id"])
        rec = close_record(variant, leg, offer, now) if offer else None
        if rec is None:
            rec = {"variant": variant, "leg_key": leg_key(leg),
                   "sofascore_event_id": leg["sofascore_event_id"],
                   "missing": True, "fetched_at_utc": now.isoformat(),
                   "minutes_before": round(minutes_to(leg["kickoff_utc"], now), 1)}
            if leg["sofascore_event_id"] in errors:
                rec["error"] = errors[leg["sofascore_event_id"]]
            # Superbet already had the match under way: its live odds are not
            # a close (superbet.odds_items drops them), so the earlier pre-match
            # record stands - say why this one is empty.
            if offer is not None and offer.superbet_started_utc is not None:
                rec["started"] = True
        records.append(rec)
    # Whole lines under a lock, newline-repairing a torn tail, as every
    # snapshot appender does.
    append_records(day_dir / "closing.jsonl", records)
    return len(records)


PID_FILE = "capture_closing.pid"


def loop_holder(
    day_dir: Path, command_of: Callable[[int], str] = _command_of
) -> int | None:
    """The pid of a live loop for this day, else None (a stale file is not one).

    Two loops for one day doubled every closing request; the second refuses,
    the way cs2_daily / shadow_daily do - through the same check, which reads
    the pid's command line: after a reboot the number can belong to anything,
    and a live-but-foreign pid made a fresh loop refuse with exit 2.
    """
    return already_running(
        day_dir / PID_FILE, day_dir.name, command_of, "capture_closing.py"
    )


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
