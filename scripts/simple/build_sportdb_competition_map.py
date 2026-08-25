#!/usr/bin/env python
"""Verify and pin every seeded competition in config/sportdb_competition_map.json.

Nothing this script writes is a guess, and no fuzzy comparison takes part in
any decision. Per seeded league three things are asserted by hand: the country,
the exact name(s) Flashscore uses, and a handful of member clubs. The script
then enumerates that country's real competitions, keeps only those whose name
*exactly* equals an asserted one after folding, and accepts a candidate only
once its real season results contain at least two of the asserted clubs.

Both halves are needed, as the first build of this map demonstrated. Ordering
candidates by name similarity and taking the first with two club hits pinned
Belgium's top flight to "Belgian Cup Women" (women's sides carry the same club
names), Portugal's to "Liga 3" (reserve sides likewise) and both Swedish tiers
to "Svenska Cupen". Requiring the exact asserted name kills all four, and
requiring real clubs in real results kills a name that exists but is not the
competition we mean.

Failing loudly is the point: if none of the asserted names exists in that
country, the script writes nothing and says so, because the fix belongs in the
assertion, not in a looser comparison.

    .venv/bin/python scripts/simple/build_sportdb_competition_map.py --max-calls 80
    .venv/bin/python scripts/simple/build_sportdb_competition_map.py --only "saudi pro league"
    .venv/bin/python scripts/simple/build_sportdb_competition_map.py --refresh

Runs are resumable: an already-verified entry is skipped unless --refresh is
given, so a quota-limited run can be continued the next day. Whatever the
budget cut short is listed explicitly at the end -- a partial map must never
read as a complete one.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from bet.api_clients.sportdb_mcp import SportDBMCPClient  # noqa: E402
from bet.simple_stats.providers import (  # noqa: E402
    _fold,
    _normalize_team_name,
    _season_candidates,
    _team_matches,
)

MAP_PATH = REPO_ROOT / "config" / "sportdb_competition_map.json"

# The free SportDB plan rejects above 3 req/s with a 429 that comes back as a
# *string* payload rather than an exception, which reads downstream as "no such
# league". Pacing is therefore correctness, not politeness.
_MIN_SECONDS_BETWEEN_CALLS = 0.40

# Distinct asserted clubs that must appear in a season before it is accepted.
_REQUIRED_TEAM_HITS = 2

# Cohort and tier markers. A competition whose name carries one of these is a
# different competition sharing the same club names, which is precisely what
# fooled the first build. Matched as whole words against the folded name.
_COHORT_MARKERS = frozenset(
    {
        "women", "woman", "womens", "female", "girls",
        "u17", "u18", "u19", "u20", "u21", "u23", "youth", "junior", "juniors",
        "reserve", "reserves", "futsal", "beach", "friendly", "friendlies",
    }
)


class Budget:
    """Hard call ceiling with pacing. Exhaustion is reported, never silent."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.spent = 0
        self._last_call = 0.0

    def take(self) -> bool:
        if self.spent >= self.limit:
            return False
        elapsed = time.monotonic() - self._last_call
        if elapsed < _MIN_SECONDS_BETWEEN_CALLS:
            time.sleep(_MIN_SECONDS_BETWEEN_CALLS - elapsed)
        self._last_call = time.monotonic()
        self.spent += 1
        return True


def _call(client, budget: Budget, tool: str, args: dict) -> dict | None:
    """One MCP call, returning the payload dict or None. A 429 arrives as a
    plain string, so anything that is not a dict is treated as a failure rather
    than as an empty result."""
    if not budget.take():
        return None
    try:
        payload = client.call_tool(tool, args)
    except Exception as exc:  # noqa: BLE001
        print(f"      ! {tool} raised: {exc}")
        return None
    if not isinstance(payload, dict):
        print(f"      ! {tool} returned a non-dict payload: {str(payload)[:120]}")
        return None
    return payload


def _countries(client, budget: Budget, cache: dict) -> list[dict]:
    if "countries" not in cache:
        payload = _call(client, budget, "flashscore_list_countries", {"sport": "football"})
        data = (payload or {}).get("data") or []
        cache["countries"] = [c for c in data if isinstance(c, dict)]
    return cache["countries"]


def _find_country(client, budget: Budget, cache: dict, name: str) -> dict | None:
    """The Flashscore country whose name equals the asserted one. Exact fold
    match only: the country is asserted knowledge, so there is nothing to
    guess, and a near-miss here would silently reintroduce the whole problem
    this map exists to remove."""
    wanted = _fold(name)
    for country in _countries(client, budget, cache):
        if _fold(str(country.get("name") or "")) == wanted:
            return country
    return None


def _competitions(client, budget: Budget, cache: dict, country: dict) -> list[dict]:
    key = f"comps:{country.get('slug')}"
    if key not in cache:
        payload = _call(
            client, budget, "flashscore_list_competitions",
            {"sport": "football", "country_slug": country.get("slug"), "country_id": country.get("id")},
        )
        data = (payload or {}).get("data") or []
        cache[key] = [c for c in data if isinstance(c, dict)]
    return cache[key]


def _refs_from_link(item: dict) -> dict | None:
    """Structured refs from a competition link:
    /api/flashscore/football/england:198/premier-league:dYlOSQOD"""
    parts = [p for p in str(item.get("link") or "").split("/") if p]
    if len(parts) < 4 or ":" not in parts[-1] or ":" not in parts[-2]:
        return None
    country_slug, _, country_id = parts[-2].partition(":")
    competition_slug, _, competition_id = parts[-1].partition(":")
    if not (country_slug and country_id and competition_slug and competition_id):
        return None
    try:
        country_id_value: object = int(country_id)
    except ValueError:
        country_id_value = (item.get("country") or {}).get("id")
    return {
        "sport": "football",
        "country_slug": country_slug,
        "country_id": country_id_value,
        "competition_slug": competition_slug,
        "competition_id": competition_id,
    }


def _matched_teams(rows: list[dict], expect: list[str]) -> list[str]:
    """Which asserted clubs actually appear in these season results."""
    seen = set()
    for row in rows:
        for side in ("homeName", "awayName"):
            name = _normalize_team_name(str(row.get(side) or ""))
            if not name:
                continue
            for team in expect:
                if team not in seen and _team_matches(name, _normalize_team_name(team)):
                    seen.add(team)
    return [t for t in expect if t in seen]


def _season_labels(season: str) -> list[str]:
    """The span label and the bare-year label, in that order.

    Not the first two of _season_candidates: those are two *spans*
    ("2026-2027", "2025-2026"), so a calendar-year league was never asked about
    "2026" at all. That alone is why the first build failed to verify K League
    1, Eliteserien, both Brazilian tiers, MLS and Liga MX.
    """
    candidates = _season_candidates(season)
    spans = [c for c in candidates if "-" in c]
    years = [c for c in candidates if "-" not in c]
    return ([spans[0]] if spans else []) + ([years[0]] if years else [])


def _verify(client, budget, cache, refs, expect, season):
    """Page a candidate's season results and report which asserted clubs are in
    them. Returns (matched_teams, label), the string "provider-error", or None.

    A provider error is reported apart from a genuine miss: the first build
    printed "fewer than 2 asserted clubs, rejected" for a run of upstream 500s,
    which reads as evidence about the league when it is evidence about nothing.
    """
    saw_error = False
    for label in _season_labels(season):
        rows = None
        for attempt in range(2):
            payload = _call(
                client, budget, "flashscore_get_competition_results",
                {**refs, "season": label, "page": 1},
            )
            if payload is None:
                saw_error = True
                continue
            rows = payload.get("data")
            break
        if not isinstance(rows, list) or not rows:
            continue
        matched = _matched_teams([r for r in rows if isinstance(r, dict)], expect)
        if len(matched) >= _REQUIRED_TEAM_HITS:
            return matched, label
    return "provider-error" if saw_error else None


def _season_label(today: datetime) -> str:
    start = today.year if today.month >= 7 else today.year - 1
    return f"{start}-{start + 1}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-calls", type=int, default=80,
                        help="hard ceiling on provider calls (default 80)")
    parser.add_argument("--only", action="append", default=[],
                        help="verify only these map keys (repeatable)")
    parser.add_argument("--refresh", action="store_true",
                        help="re-verify entries that already carry a verification block")
    parser.add_argument("--dry-run", action="store_true",
                        help="resolve and report, write nothing")
    args = parser.parse_args()

    document = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    competitions = document["competitions"]
    today = datetime.now(timezone.utc)
    season = _season_label(today)

    keys = args.only or list(competitions)
    unknown = [k for k in keys if k not in competitions]
    if unknown:
        print(f"not in the map: {unknown}")
        return 2

    todo = [k for k in keys if args.refresh or "verification" not in competitions[k]]
    print(f"{len(competitions)} seeded, {len(todo)} to verify, budget {args.max_calls} calls, season {season}\n")

    client = SportDBMCPClient()
    budget = Budget(args.max_calls)
    cache: dict = {}
    verified, failed, unattempted = [], [], []

    for key in todo:
        entry = competitions[key]
        expect = entry["expect_teams"]
        if budget.spent >= budget.limit:
            unattempted.append(key)
            continue

        print(f"{key!r} -> {entry['country']}")
        country = _find_country(client, budget, cache, entry["country"])
        if country is None:
            print("      country not found on Flashscore")
            failed.append((key, "country not found"))
            continue

        candidates = _competitions(client, budget, cache, country)
        if not candidates:
            print("      no competition list for that country")
            unattempted.append(key)
            continue

        accepted = {_fold(n) for n in entry["flashscore_names"]}
        shortlist = []
        for candidate in candidates:
            folded = _fold(str(candidate.get("name") or ""))
            if folded not in accepted:
                continue
            cohort = _COHORT_MARKERS & set(folded.split())
            if cohort:
                print(f"      skipping {candidate.get('name')!r}: {'/'.join(sorted(cohort))} cohort")
                continue
            shortlist.append(candidate)

        if not shortlist:
            available = sorted({str(c.get("name") or "") for c in candidates})
            print(f"      none of {entry['flashscore_names']} exists in {entry['country']}")
            print(f"      available there: {', '.join(available[:12])}"
                  f"{' ...' if len(available) > 12 else ''}")
            failed.append((key, f"asserted name absent; fix the assertion, not the matcher"))
            continue

        won = None
        provider_error = False
        for candidate in shortlist:
            refs = _refs_from_link(candidate)
            if refs is None:
                continue
            if budget.spent >= budget.limit:
                break
            outcome = _verify(client, budget, cache, refs, expect, season)
            name = candidate.get("name")
            if outcome == "provider-error":
                print(f"      {name!r}: provider error, inconclusive")
                provider_error = True
                continue
            if outcome is None:
                print(f"      {name!r} exists but its season has fewer than "
                      f"{_REQUIRED_TEAM_HITS} asserted clubs, rejected")
                continue
            matched, label = outcome
            print(f"      {name!r} VERIFIED on {label}: {', '.join(matched)}")
            won = (refs, name, label, matched)
            break

        if won is None:
            if provider_error:
                print("      inconclusive -- rerun")
                unattempted.append(key)
            else:
                print("      nothing verified")
                failed.append((key, "asserted name exists but the season lacked the asserted clubs"))
            continue

        refs, name, label, matched = won
        entry["refs"] = refs
        entry["verification"] = {
            "flashscore_name": name,
            "flashscore_country": country.get("name"),
            "season": label,
            "matched_teams": matched,
            "verified_on": today.strftime("%Y-%m-%d"),
        }
        verified.append(key)

    print(f"\nverified {len(verified)}, failed {len(failed)}, "
          f"not attempted {len(unattempted)}, calls spent {budget.spent}/{budget.limit}")
    for key, why in failed:
        print(f"   FAILED      {key}: {why}")
    for key in unattempted:
        print(f"   NOT TRIED   {key}: budget exhausted -- rerun to continue")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0
    if verified:
        MAP_PATH.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {MAP_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
