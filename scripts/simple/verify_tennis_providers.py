#!/usr/bin/env python
"""Re-prove, live, that every tennis provider we assert can serve real players.

The tennis roster in PROVIDERS_BY_SPORT is a set of claims about providers we
do not control, and on 2026-08-28 all three of them were false in a different
way:

  * ``tennis-abstract`` answered HTTP 200 for every WTA player with Benoit
    Paire's page -- the same 605 KB body for Sabalenka, Swiatek, Gauff, Kostyuk
    and Shnaider -- and the client parsed his ``var matchmx`` and filed his
    serve line under her name. Nothing raised. Nothing was empty. The sheet
    just had numbers in it that belonged to someone else.
  * ``sackmann`` read two GitHub repositories that no longer exist. It could
    not have returned a row for anybody since the day they went, and nothing
    in the repo would have said so.
  * ``espn-tennis`` returned matches with the player recorded as his own
    opponent whenever ESPN listed him first, and returned nothing at all for
    most ATP players because its scan sampled every third or fourth day and
    landed either side of every match they played.

None of that shows up as an error, a 404, or an empty artifact. It shows up as
a *plausible* number, which is the only kind of wrong this pipeline cannot
survive. So tennis gets what the ESPN competition table got in
verify_espn_competition_map.py: a script that re-derives the claim from the
provider and fails loudly when the evidence stops agreeing.

What is checked per (provider, player), all of it through the production client
and the production resolve/fetch path, because a check that re-implements what
it checks proves only itself:

  1. The provider resolves the player at all.
  2. It returns finished matches for him.
  3. Every row it returns is named for *him*, judged against the provider's own
     name field -- tennis-abstract's ``var fullname``, ESPN's scoreboard
     ``displayName`` for the competitor carrying the resolved athlete id -- and
     never against a similarity score. Fuzzy matching is how the WTA
     fabrication survived as long as it did; the provider states the name
     outright, so the name is compared, not scored.
  4. The newest match is recent enough to be somebody's current form. Identity
     is necessary but not sufficient: tennisabstract still serves
     /jsmatches/JannikSinner.js and its last row is from November 2018, so a
     route can be the right player and the wrong era.

Output is config/tennis_provider_verification.json: per tour, per provider, the
players proved and what the provider called them. The test suite asserts every
provider in PROVIDERS_BY_SPORT["tennis"] carries a passing entry, which inverts
the old arrangement -- a provider asserted without a probe now fails the suite
instead of waiting to be noticed on a live slate.

    .venv/bin/python scripts/simple/verify_tennis_providers.py
    .venv/bin/python scripts/simple/verify_tennis_providers.py --refresh
    .venv/bin/python scripts/simple/verify_tennis_providers.py --tour wta
    .venv/bin/python scripts/simple/verify_tennis_providers.py --player "Iga Swiatek"
    .venv/bin/python scripts/simple/verify_tennis_providers.py --from-events runs/<id>/event_list.json

Exit codes: 0 all good, 1 drift found (a provider stopped resolving, started
naming someone else, or went stale), 2 the run could not be completed.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from bet.api_clients.rate_limiter import RateLimiter  # noqa: E402
from bet.simple_stats.providers import (  # noqa: E402
    PROVIDERS_BY_SPORT,
    probe_tennis_identity,
)

ARTIFACT_PATH = REPO_ROOT / "config" / "tennis_provider_verification.json"

# A handful of players per tour, chosen to exercise the routes rather than to
# be a ranking: an ATP name and a WTA name are served by *different* pages on
# tennis-abstract and different tours on ESPN, and the WTA half is the half
# that was silently fabricating. Diacritics are represented on purpose -- the
# identity check folds them, and a check that only ever sees ASCII names would
# not prove that it does.
ROSTER: dict[str, tuple[str, ...]] = {
    "atp": (
        "Jannik Sinner",
        "Novak Djokovic",
        "Alexander Zverev",
        "Jiří Lehečka",
    ),
    "wta": (
        "Aryna Sabalenka",
        "Iga Świątek",
        "Coco Gauff",
        "Marta Kostyuk",
    ),
}

# The competition string is what scopes the provider client, so a tour probe
# must carry the marker the production map reads (api_clients/espn.py).
COMPETITION_FOR_TOUR = {"atp": "ATP Tour", "wta": "WTA Tour"}

# A provider whose freshest match for a player is older than this is reported,
# not silently accepted. It is generous on purpose: injured and returning
# players legitimately have gaps, and the failure being hunted here is a route
# stuck years in the past, not a fortnight's rest.
_STALE_AFTER_DAYS = 120

_FAILING = {"UNRESOLVED", "MISIDENTIFIED", "NO_MATCHES"}


def _age_days(date_str: str, today: datetime) -> int | None:
    try:
        then = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None
    return (today - then).days


def _roster_from_events(path: Path) -> dict[str, tuple[str, ...]]:
    """Today's actual slate instead of the asserted roster.

    The asserted roster proves the providers work. This proves they work on the
    names that are about to be priced, which is the only question that matters
    on a run day.
    """
    document = json.loads(path.read_text(encoding="utf-8"))
    by_tour: dict[str, list[str]] = {}
    for event in document.get("events", []):
        if event.get("sport") != "tennis" or event.get("status") != "ACTIVE":
            continue
        competition = str(event.get("competition") or "")
        tour = "wta" if "WTA" in competition.upper() else "atp"
        for key in ("player_one", "player_two"):
            name = event.get(key)
            if name and name not in by_tour.setdefault(tour, []):
                by_tour[tour].append(name)
    return {tour: tuple(names) for tour, names in by_tour.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tour", action="append", default=[], choices=["atp", "wta"],
                        help="probe only this tour (repeatable)")
    parser.add_argument("--player", action="append", default=[],
                        help="probe only these players (repeatable)")
    parser.add_argument("--from-events", type=Path, default=None,
                        help="take the roster from a DISCOVER event_list.json "
                             "instead of the asserted one")
    parser.add_argument("--provider", action="append", default=[],
                        help="probe only these providers (repeatable)")
    parser.add_argument("--refresh", action="store_true",
                        help="re-probe pairs that already carry a verification")
    parser.add_argument("--last-n", type=int, default=10,
                        help="how many matches to ask for per player (default 10)")
    parser.add_argument("--dry-run", action="store_true",
                        help="probe and report, write nothing")
    args = parser.parse_args()

    today = datetime.now(UTC)
    providers = tuple(args.provider) if args.provider else PROVIDERS_BY_SPORT["tennis"]
    if not providers:
        print("PROVIDERS_BY_SPORT['tennis'] is empty: nothing is asserted, "
              "so there is nothing to verify.")
        return 2

    if args.from_events:
        if not args.from_events.exists():
            print(f"no such event list: {args.from_events}")
            return 2
        roster = _roster_from_events(args.from_events)
        if not roster:
            print(f"{args.from_events} holds no ACTIVE tennis events")
            return 2
    else:
        roster = ROSTER

    if args.tour:
        roster = {tour: names for tour, names in roster.items() if tour in args.tour}
    if args.player:
        wanted = {p.casefold() for p in args.player}
        roster = {
            tour: tuple(n for n in names if n.casefold() in wanted)
            for tour, names in roster.items()
        }
        roster = {tour: names for tour, names in roster.items() if names}
        if not roster:
            print(f"none of {args.player} are in the roster")
            return 2

    document: dict = {"tours": {}, "refuted": {}}
    if ARTIFACT_PATH.exists():
        document = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
        document.setdefault("tours", {})
        document.setdefault("refuted", {})

    limiter = RateLimiter()
    failures: list[tuple[str, str, str, str]] = []
    stale: list[tuple[str, str, int | None]] = []
    proved = 0

    for tour, players in roster.items():
        competition = COMPETITION_FOR_TOUR.get(tour, "")
        tour_entry = document["tours"].setdefault(tour, {})
        print(f"\n=== {tour.upper()} ({competition}) -- {len(players)} players, "
              f"{len(providers)} providers")
        for provider in providers:
            entries = tour_entry.setdefault(provider, {})
            for player in players:
                if player in entries and not args.refresh:
                    print(f"   kept        {provider:<16} {player} "
                          f"(verified {entries[player].get('verified_on')})")
                    continue

                evidence = probe_tennis_identity(
                    provider, player, competition, limiter, last_n=args.last_n
                )
                key = f"{tour}/{provider}/{player}"

                if evidence.verdict in _FAILING:
                    label = evidence.verdict
                    print(f"   {label:<11} {provider:<16} {player}: {evidence.detail}")
                    failures.append((tour, provider, player, f"{label}: {evidence.detail}"))
                    entries.pop(player, None)
                    document["refuted"][key] = {
                        "verdict": evidence.verdict,
                        "detail": evidence.detail,
                        "resolved": evidence.resolved,
                        "provider_name": evidence.provider_name,
                        "verified_on": today.strftime("%Y-%m-%d"),
                    }
                    continue

                age = _age_days(evidence.newest_match, today)
                if age is None or age > _STALE_AFTER_DAYS:
                    stale.append((f"{provider}/{player}", evidence.newest_match, age))

                document["refuted"].pop(key, None)
                entries[player] = {
                    "resolved": evidence.resolved,
                    "provider_name": evidence.provider_name,
                    "match_count": evidence.match_count,
                    "newest_match": evidence.newest_match,
                    "verified_on": today.strftime("%Y-%m-%d"),
                }
                proved += 1
                print(f"   ok          {provider:<16} {player}: "
                      f"{evidence.match_count} matches as "
                      f"{evidence.provider_name or evidence.resolved!r}, "
                      f"newest {evidence.newest_match or 'unknown'}")

    print(f"\nproved {proved}, failed {len(failures)}, stale {len(stale)}")
    for name, newest, age in stale:
        print(f"   STALE       {name}: newest match {newest or 'unknown'} "
              f"({age if age is not None else '?'} days old)")

    # A provider that proved nothing anywhere is not a thin provider, it is an
    # absent one, and it is being asserted in PROVIDERS_BY_SPORT as though it
    # were carrying half a sport.
    dead_providers = [
        provider
        for provider in providers
        if not any(
            document["tours"].get(tour, {}).get(provider)
            for tour in document["tours"]
        )
    ]
    for provider in dead_providers:
        print(f"   DEAD        {provider}: proved no player on any tour")

    if args.dry_run:
        print("\n--dry-run: nothing written")
    else:
        document["verified_by"] = "scripts/simple/verify_tennis_providers.py"
        document["probe"] = (
            "resolve the player through the production client, fetch his last "
            "matches, and require every returned row to be named for him by "
            "the provider's own name field"
        )
        document["last_run"] = today.strftime("%Y-%m-%d")
        ARTIFACT_PATH.write_text(
            json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"\nwrote {ARTIFACT_PATH.relative_to(REPO_ROOT)}")

    if failures or dead_providers:
        print(
            "\nDRIFT: fix the roster, not this script. MISIDENTIFIED means the "
            "provider is serving someone else's matches and must be repaired or "
            "dropped before the next run -- it is the only failure here that "
            "puts a fabricated number on a sheet. UNRESOLVED and NO_MATCHES "
            "across a whole tour mean the provider no longer covers it."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
