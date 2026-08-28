#!/usr/bin/env python
"""Re-prove every ESPN league code the competition table asserts, live.

The table in api_clients/espn.py is a set of claims about a provider we do not
control, and it was true on the day it was written. Nothing in the repo could
tell you when it stopped being true. The 18 dead codes it used to assert were
found by hand; a hand-kept blocklist of the codes someone happened to probe
cannot catch the nineteenth, and the runtime gate only notices per fixture,
after the slate has already lost the provider.

So the table gets what config/sportdb_competition_map.json has: a script that
re-derives its evidence from the provider and fails loudly when the evidence
stops agreeing. Same shape as build_sportdb_competition_map.py -- names are
asserted from knowledge, codes are proved from provider data, and a mismatch is
reported rather than smoothed over.

Three things are checked per code, and each one is a failure the table has
actually shipped:

  1. ESPN serves a non-empty team directory for it.  sau.1 404s; cze.1, fin.1
     and usa.w.1 answer 200 with zero teams, which is the same thing wearing a
     success code. Both shapes surfaced downstream as "could not resolve team
     identity for '<club>'" -- a league failure wearing a team-name label.
  2. ESPN's own name for the code does not contradict any competition name
     pinned to it, judged by the production gate itself
     (_espn_pin_contradicted). Running the *runtime* check here rather than a
     second copy of it is the point: a row the gate would reject at run time is
     a dead row, and it should fail in CI rather than silently cost a provider
     on match day.
  3. Every code the discovery sweep enumerates (ESPN_LEAGUES) is equally live,
     because a dead code there is a guaranteed 404 on every sweep.

What comes out is config/espn_competition_map_verification.json: an allowlist
of codes proved live, with ESPN's name and team count for each. The test suite
asserts the table is covered by it, which inverts the old arrangement -- a code
added to the table without a probe now fails the suite instead of waiting to be
noticed.

    .venv/bin/python scripts/simple/verify_espn_competition_map.py
    .venv/bin/python scripts/simple/verify_espn_competition_map.py --refresh
    .venv/bin/python scripts/simple/verify_espn_competition_map.py --only ksa.1
    .venv/bin/python scripts/simple/verify_espn_competition_map.py --max-age-days 30

Exit codes: 0 all good, 1 drift found (a code died, or a name now contradicts
its pins), 2 the run could not be completed (bad arguments, budget exhausted
before anything was proved).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from bet.api_clients.espn import (  # noqa: E402
    _ESPN_FOOTBALL_COMPETITIONS,
    _ESPN_OTHER_COMPETITIONS,
    ESPN_LEAGUES,
)
from bet.api_clients.rate_limiter import RateLimiter  # noqa: E402
from bet.simple_stats.providers import (  # noqa: E402
    _espn_league_directory,
    _espn_pin_contradicted,
)

ARTIFACT_PATH = REPO_ROOT / "config" / "espn_competition_map_verification.json"

# ESPN publishes no rate limit and enforces none we have hit, but ~110 probes
# in a burst is impolite and indistinguishable from a scraper. Pacing costs a
# few seconds on a script that runs by hand.
_MIN_SECONDS_BETWEEN_CALLS = 0.20

# Entries older than this are reported as stale. They are only an *error* under
# --max-age-days, because a stale entry is still evidence -- just ageing
# evidence, and the whole complaint this script answers is that nobody could
# tell how old the table's evidence was.
_STALE_AFTER_DAYS = 30


def _pins_by_code() -> dict[str, list[str]]:
    """code -> every competition name the football table pins to it."""
    pins: dict[str, list[str]] = {}
    for name, code in _ESPN_FOOTBALL_COMPETITIONS.items():
        pins.setdefault(code, []).append(name)
    return pins


def _age_days(verified_on: str, today: datetime) -> int | None:
    try:
        then = datetime.strptime(verified_on, "%Y-%m-%d").replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None
    return (today - then).days


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", default=[],
                        help="probe only these league codes (repeatable)")
    parser.add_argument("--refresh", action="store_true",
                        help="re-probe codes that already carry a verification")
    parser.add_argument("--max-calls", type=int, default=200,
                        help="hard ceiling on ESPN requests (default 200)")
    parser.add_argument("--max-age-days", type=int, default=0,
                        help="fail if a kept verification is older than this "
                             "many days (default 0: report, do not fail)")
    parser.add_argument("--dry-run", action="store_true",
                        help="probe and report, write nothing")
    args = parser.parse_args()

    today = datetime.now(UTC)
    pins = _pins_by_code()
    table_codes = set(pins)
    sweep_codes = set(ESPN_LEAGUES["football"])
    wanted = sorted(table_codes | sweep_codes)

    if args.only:
        unknown = [c for c in args.only if c not in wanted]
        if unknown:
            print(f"not asserted anywhere in the table or the sweep: {unknown}")
            return 2
        wanted = sorted(args.only)

    document: dict = {"codes": {}, "refuted": {}}
    if ARTIFACT_PATH.exists():
        document = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
        document.setdefault("codes", {})
        document.setdefault("refuted", {})
    known = document["codes"]

    todo = [c for c in wanted if args.refresh or c not in known]
    print(
        f"{len(table_codes)} codes pinned by the table, {len(sweep_codes)} swept, "
        f"{len(wanted)} distinct; {len(todo)} to probe "
        f"(budget {args.max_calls})\n"
    )

    limiter = RateLimiter()
    spent = 0
    dead: list[tuple[str, str]] = []
    contradictions: list[tuple[str, str, str]] = []
    unattempted: list[str] = []
    proved: list[str] = []

    for code in todo:
        if spent >= args.max_calls:
            unattempted.append(code)
            continue
        if spent:
            time.sleep(_MIN_SECONDS_BETWEEN_CALLS)
        spent += 1
        directory = _espn_league_directory("football", code, limiter)
        if not directory.usable:
            why = (
                "404 / no directory" if not directory.served
                else "200 with zero teams"
            )
            print(f"   DEAD        {code}: {why}")
            dead.append((code, why))
            known.pop(code, None)
            document["refuted"][code] = {
                "reason": why,
                "espn_name": directory.league_name,
                "verified_on": today.strftime("%Y-%m-%d"),
            }
            continue

        # ESPN's name is the only provider-side evidence about *which* league a
        # code points at, so this is where a code pasted onto the wrong table
        # row dies -- the failure that never raises at run time because the
        # wrong division inside the right country answers with real clubs.
        rejected = [
            (name, _espn_pin_contradicted(name, code, directory.league_name))
            for name in pins.get(code, [])
        ]
        rejected = [(name, why) for name, why in rejected if why]
        for name, why in rejected:
            print(f"   CONTRADICTS {code}: {name!r} -- {why}")
            contradictions.append((code, name, why))
        if rejected:
            known.pop(code, None)
            continue

        document["refuted"].pop(code, None)
        known[code] = {
            "espn_name": directory.league_name,
            "team_count": directory.team_count,
            "verified_on": today.strftime("%Y-%m-%d"),
            "pinned_by": sorted(pins.get(code, [])),
            "swept": code in sweep_codes,
        }
        proved.append(code)
        print(
            f"   ok          {code}: {directory.league_name!r}, "
            f"{directory.team_count} teams"
        )

    # Entries for codes nobody asserts any more are evidence about nothing.
    if not args.only:
        for code in sorted(set(known) - (table_codes | sweep_codes)):
            print(f"   DROPPED     {code}: no longer asserted by table or sweep")
            known.pop(code)

    missing = sorted((table_codes | sweep_codes) - set(known))
    stale = []
    for code, entry in sorted(known.items()):
        age = _age_days(str(entry.get("verified_on") or ""), today)
        if age is None or age >= _STALE_AFTER_DAYS:
            stale.append((code, age))

    print(
        f"\nproved {len(proved)}, dead {len(dead)}, contradicted "
        f"{len(contradictions)}, not attempted {len(unattempted)}, "
        f"requests spent {spent}/{args.max_calls}"
    )
    for code in unattempted:
        print(f"   NOT TRIED   {code}: budget exhausted -- rerun to continue")
    if missing:
        print(
            f"   UNPROVED    {len(missing)} asserted codes carry no verification:"
        )
        print(f"               {', '.join(missing)}")
    if stale:
        oldest = max((a for _, a in stale if a is not None), default=None)
        print(
            f"   STALE       {len(stale)} verifications are "
            f"{_STALE_AFTER_DAYS}+ days old (oldest {oldest}) -- rerun --refresh"
        )
    if _ESPN_OTHER_COMPETITIONS:
        print(
            f"   NOTE        {len(_ESPN_OTHER_COMPETITIONS)} non-football names "
            f"({', '.join(sorted({*_ESPN_OTHER_COMPETITIONS.values()}))}) are not "
            f"probed: ESPN's non-football /teams surface was never asserted, and "
            f"they are kept out of ESPN_FOOTBALL_LEAGUE_CODES for that reason."
        )
    pinned_unswept = sorted(table_codes - sweep_codes)
    if pinned_unswept:
        print(
            f"   NOTE        {len(pinned_unswept)} codes are pinned but never "
            f"swept, so they can be enriched but not discovered: "
            f"{', '.join(pinned_unswept)}"
        )

    if args.dry_run:
        print("\n--dry-run: nothing written")
    else:
        document["verified_by"] = "scripts/simple/verify_espn_competition_map.py"
        document["probe"] = (
            "GET http://site.api.espn.com/apis/site/v2/sports/soccer/<code>/teams; "
            "a code counts as live only with a non-empty team directory"
        )
        document["last_run"] = today.strftime("%Y-%m-%d")
        ARTIFACT_PATH.write_text(
            json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"\nwrote {ARTIFACT_PATH.relative_to(REPO_ROOT)}")

    if dead or contradictions:
        print(
            "\nDRIFT: fix the table, not this script. A code ESPN stopped "
            "serving must be removed or replaced with the code it moved to; a "
            "contradiction means the name and the code disagree about which "
            "league they mean."
        )
        return 1
    if missing and not args.only:
        print("\nINCOMPLETE: some asserted codes were never proved (see UNPROVED).")
        return 1
    if args.max_age_days and stale:
        cutoff = args.max_age_days
        overdue = [c for c, a in stale if a is None or a >= cutoff]
        if overdue:
            print(f"\nSTALE: {len(overdue)} verifications older than {cutoff} days.")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
