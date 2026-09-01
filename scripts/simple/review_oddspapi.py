#!/usr/bin/env python3
"""What OddsPapi can actually do for this account, today, in one command.

Usage:
    python3 scripts/simple/review_oddspapi.py                 # 1 request
    python3 scripts/simple/review_oddspapi.py --probe         # + 2 requests
    python3 scripts/simple/review_oddspapi.py --probe --sport tennis

Why this exists rather than a note in a doc
-------------------------------------------
The last written record of this provider said ``/v4/fixtures`` and ``/v4/odds``
were "403, the plan covers ``/account`` only", and it was wrong: the 403 names a
*bookmaker* (``superbet.pl``), both endpoints work, and the provider sat unused
for a month on the strength of that sentence. A claim about a provider that
cannot be re-run is a claim that rots. This one re-runs.

Cost, stated up front because the free plan is 250 requests **in total**:

* default: **one** request (``/account``), and it prints how many are left;
* ``--probe``: two more (``/fixtures`` for one sport, ``/odds`` for one fixture),
  which is what it takes to prove the two endpoints answer.

Exit codes: 0 = the plan can do what the pipeline needs, 1 = it cannot, 2 = the
credential is missing or the account call failed.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from bet.api_clients.oddspapi import (  # noqa: E402
    SUPERBET_BOOKMAKER_SLUGS,
    OddsPapiClient,
    OddsPapiError,
    OddsPapiRestrictedError,
    OddspapiConfig,
    superbet_event_id,
)

# Below this, the identity bridge stops running of its own accord. Printed so
# the review answers "will tonight's pipeline use it" and not just "is it up".
from bet.simple_stats.superbet_identity import MIN_QUOTA_RESERVE  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Review OddsPapi access for this account")
    parser.add_argument(
        "--probe", action="store_true",
        help="Also call /fixtures and /odds to prove they answer. Two requests.",
    )
    parser.add_argument("--sport", default="football", help="Sport to probe (default: football)")
    parser.add_argument("--date", default=None, help="Probe window start, YYYY-MM-DD (default: today)")
    parser.add_argument("--fixture-id", default=None, help="Probe this exact fixture instead of a chosen one")
    args = parser.parse_args()

    try:
        config = OddspapiConfig.from_env()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL  no usable credential: {exc}")
        sys.exit(2)

    api = OddsPapiClient(config)
    try:
        account = api.account()
    except OddsPapiError as exc:
        print(f"FAIL  /v4/account: {exc}")
        sys.exit(2)

    print("== account ==")
    print(f"  plan            {account.plan}")
    print(f"  requests        {account.request_count} / {account.request_limit}"
          f"   ({account.remaining} left)")
    print(f"  active          {account.active}")
    print(f"  bookmakers      {len(account.bookmakers)} entitled")
    print(f"  sports          {len(account.sport_ids)} ids, football(10)="
          f"{10 in account.sport_ids}, tennis(12)={12 in account.sport_ids}")

    print("== superbet storefronts ==")
    for slug in SUPERBET_BOOKMAKER_SLUGS:
        mark = "yes" if account.serves(slug) else "NO "
        note = ""
        if slug == "superbet.pl":
            note = "  <- the book the operator actually bets into"
        elif slug == "superbet":
            note = "  <- clone of superbet.ro; same event ids, ~1% different price"
        print(f"  {mark}  {slug}{note}")
    usable = account.first_served(SUPERBET_BOOKMAKER_SLUGS)
    print(f"  usable slug     {usable or 'none'}")

    verdict_ok = True
    print("== what this means for the pipeline ==")
    if account.serves("superbet.pl"):
        print("  superbet.pl IS entitled: OddsPapi could serve the operator's own")
        print("  prices directly. That is a change from 2026-09-01 and is worth")
        print("  revisiting -- see bet.simple_stats.superbet_identity.")
    else:
        print("  superbet.pl is NOT entitled, so OddsPapi supplies identity only.")
        print("  The price of record stays superbet.pl's own public offer feed.")
    if account.remaining - 2 < MIN_QUOTA_RESERVE:
        print(f"  quota below the bridge's reserve ({MIN_QUOTA_RESERVE}): SUPERBET will")
        print("  skip the bridge and match fixtures by name, as it did before.")
        verdict_ok = False
    else:
        runs = (account.remaining - MIN_QUOTA_RESERVE) // 3
        print(f"  quota is fine: roughly {runs} more bridged pipeline runs "
              f"(3 requests each, worst case).")

    if args.probe:
        day = datetime.fromisoformat(f"{args.date}T00:00:00+00:00") if args.date else datetime.now(UTC)
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        print("== endpoint probe ==")
        try:
            fixtures = api.fixtures(args.sport, start, start + timedelta(days=1))
        except OddsPapiError as exc:
            print(f"  FAIL  /v4/fixtures: {exc}")
            sys.exit(1)
        with_betradar = [item for item in fixtures if item.betradar_id]
        share = (100 * len(with_betradar) / len(fixtures)) if fixtures else 0.0
        print(f"  OK    /v4/fixtures  {len(fixtures)} {args.sport} fixtures, "
              f"{len(with_betradar)} with a betradarId ({share:.0f}%)")
        if not fixtures:
            print("  (no fixtures in the window; nothing to probe /v4/odds with)")
            sys.exit(0 if verdict_ok else 1)

        # Pick the fixture from the busiest tournament in the window rather than
        # the first row. The first row is whatever kicks off soonest, which on a
        # European morning is a college or reserve tie that Superbet does not
        # price at all -- a true "0 markets" that reads like a broken probe.
        pool = with_betradar or fixtures
        busiest = Counter(item.tournament_id for item in pool)
        target = max(pool, key=lambda item: (busiest[item.tournament_id], item.fixture_id))
        if args.fixture_id:
            target = next((item for item in pool if item.fixture_id == args.fixture_id), target)
        try:
            payload = api.odds_for_fixture(target.fixture_id, bookmaker=usable or "superbet")
        except OddsPapiRestrictedError as exc:
            print(f"  FAIL  /v4/odds restricted for {', '.join(exc.bookmakers) or 'the slug asked for'}")
            sys.exit(1)
        except OddsPapiError as exc:
            print(f"  FAIL  /v4/odds: {exc}")
            sys.exit(1)
        markets = (payload.get("bookmakerOdds", {}).get(usable or "superbet", {}) or {}).get("markets") or {}
        event_id = superbet_event_id(payload, bookmaker=usable or "superbet")
        print(f"  OK    /v4/odds      {target.home} v {target.away} "
              f"({target.tournament_name}): {len(markets)} markets")
        if event_id:
            print(f"        superbet eventId {event_id}   betradarId {target.betradar_id}")
            print("        (that eventId is the same integer superbet.pl's own feed uses)")
        else:
            # Not a failure: the endpoint answered, this bookmaker simply does
            # not price this fixture. Said out loud so it is not read as one.
            print(f"        this bookmaker does not carry this fixture "
                  f"(betradarId {target.betradar_id}); the endpoint answered fine")

    print(f"== requests spent by this review: {api.request_count} ==")
    sys.exit(0 if verdict_ok else 1)


if __name__ == "__main__":
    main()
