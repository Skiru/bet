#!/usr/bin/env python3
"""Discover events for all 5 sports via ESPN API and persist to betting.db.

Supplements api-football discovery with ESPN data for basketball, hockey, tennis.
ESPN API is free, no key required.

Usage:
    python3 scripts/espn_discover_all.py --date 2026-05-20
    python3 scripts/espn_discover_all.py --date 2026-05-20 --sports tennis,basketball
    python3 scripts/espn_discover_all.py --date 2026-05-20 --limit 500
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import create_engine, event as sa_event, text
from sqlalchemy.orm import sessionmaker
import unicodedata
from bet.utils import normalize_team_name


def _resolve_team_normalized(session, name: str, sport_id: int) -> int | None:
    """Resolve team with diacritics normalization + suffix stripping fallback. Returns team_id or None."""
    # 1. Exact match
    row = session.execute(
        text("SELECT id FROM teams WHERE name = :name AND sport_id = :sid"),
        {"name": name, "sid": sport_id},
    ).fetchone()
    if row:
        return row[0]

    # 2. Alias match
    row = session.execute(
        text(
            "SELECT t.id FROM teams t, json_each(t.aliases) AS a "
            "WHERE t.sport_id = :sid AND a.value = :name"
        ),
        {"sid": sport_id, "name": name},
    ).fetchone()
    if row:
        return row[0]

    # 3. Normalized diacritics match + suffix stripping
    import re
    normalized_input = (
        unicodedata.normalize("NFKD", name)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
        .strip()
    )
    suffix_stripped_input = normalize_team_name(name)
    # Guard: don't suffix-match if name has identity markers (reserves/youth/women)
    _identity_re = re.compile(r"\b(U2[0-9]|U1[7-9]|II|III|IV|B|W|Reserves?|Youth|Women|Juniors?)\b", re.IGNORECASE)
    has_identity_marker = bool(_identity_re.search(name))

    if normalized_input and len(normalized_input) >= 3:
        rows = session.execute(
            text("SELECT id, name FROM teams WHERE sport_id = :sid"),
            {"sid": sport_id},
        ).fetchall()
        for r in rows:
            canonical_norm = (
                unicodedata.normalize("NFKD", r[1])
                .encode("ascii", "ignore")
                .decode("ascii")
                .lower()
                .strip()
            )
            if canonical_norm == normalized_input:
                # Auto-add as alias
                session.execute(
                    text(
                        "UPDATE teams SET aliases = json_insert("
                        "COALESCE(aliases, '[]'), '$[#]', :alias"
                        ") WHERE id = :tid"
                    ),
                    {"alias": name, "tid": r[0]},
                )
                return r[0]
            # Suffix-stripped comparison — skip if identity markers differ
            if suffix_stripped_input and len(suffix_stripped_input) >= 3 and not has_identity_marker:
                candidate_has_marker = bool(_identity_re.search(r[1]))
                if not candidate_has_marker:
                    canonical_suffix_stripped = normalize_team_name(r[1])
                    if canonical_suffix_stripped == suffix_stripped_input:
                        session.execute(
                            text(
                                "UPDATE teams SET aliases = json_insert("
                                "COALESCE(aliases, '[]'), '$[#]', :alias"
                                ") WHERE id = :tid"
                            ),
                            {"alias": name, "tid": r[0]},
                        )
                        return r[0]

    # 4. Create new
    session.execute(
        text("INSERT OR IGNORE INTO teams (name, sport_id) VALUES (:name, :sid)"),
        {"name": name, "sid": sport_id},
    )
    row = session.execute(
        text("SELECT id FROM teams WHERE name = :name AND sport_id = :sid"),
        {"name": name, "sid": sport_id},
    ).fetchone()
    return row[0] if row else None
from sqlalchemy.pool import StaticPool

from bet.scrapers.engine import Base
from bet.api_clients.espn import ESPNClient, ESPN_LEAGUES, ESPN_SPORT_MAP
from bet.discovery.models import DiscoveredEvent, MergedFixture, SourceRef
from bet.discovery.repository import FixtureSourceRepo

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("espn_discover")

DB_PATH = Path(__file__).parent.parent / "betting" / "data" / "betting.db"
DATA_DIR = Path(__file__).parent.parent / "betting" / "data"


def get_session():
    engine = create_engine(f"sqlite:///{DB_PATH}", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @sa_event.listens_for(engine, "connect")
    def _pragma(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    return Session()


def discover_espn_events(date: str, sports: list[str] | None = None, limit: int = 0) -> dict:
    """Discover events from ESPN for specified sports."""
    target_sports = sports or ["football", "basketball", "hockey", "tennis", "volleyball"]
    all_fixtures: list[dict] = []

    for sport in target_sports:
        leagues = ESPN_LEAGUES.get(sport, [])
        if not leagues:
            continue
        sport_count = 0
        for league in leagues:
            try:
                client = ESPNClient(sport=sport, league=league)
                fixtures = client.get_fixtures(date)
                for f in fixtures:
                    if f.status in ("STATUS_POSTPONED", "STATUS_CANCELED"):
                        continue
                    all_fixtures.append({
                        "sport": sport,
                        "competition": f.competition_name or league,
                        "home_team": f.home_team_name,
                        "away_team": f.away_team_name,
                        "kickoff": f.kickoff,
                        "external_id": f.external_id,
                        "source": f"espn-{sport}",
                        "status": "scheduled" if f.status in ("STATUS_SCHEDULED", "scheduled") else f.status,
                    })
                    sport_count += 1
            except Exception as e:
                log.debug("  %s/%s: %s", sport, league, e)

        log.info("%s: %d events across %d leagues", sport, sport_count, len(leagues))

        if limit and len(all_fixtures) >= limit:
            all_fixtures = all_fixtures[:limit]
            break

    return {"fixtures": all_fixtures, "total": len(all_fixtures)}


def persist_to_db(date: str, fixtures: list[dict]) -> int:
    """Persist discovered fixtures to betting.db."""
    session = get_session()
    now = datetime.now(timezone.utc).isoformat()
    fs_repo = FixtureSourceRepo(session)
    count = 0

    for f in fixtures:
        try:
            nested = session.begin_nested()

            # Resolve sport
            sport_row = session.execute(
                text("SELECT id FROM sports WHERE name = :name"), {"name": f["sport"]}
            ).fetchone()
            if not sport_row:
                session.execute(
                    text("INSERT OR IGNORE INTO sports (name, tier) VALUES (:name, 1)"),
                    {"name": f["sport"]},
                )
                sport_row = session.execute(
                    text("SELECT id FROM sports WHERE name = :name"), {"name": f["sport"]}
                ).fetchone()
            sport_id = sport_row[0]

            # Resolve teams (with diacritics normalization)
            home_id = _resolve_team_normalized(session, f["home_team"], sport_id)
            away_id = _resolve_team_normalized(session, f["away_team"], sport_id)

            if not home_id or not away_id:
                nested.rollback()
                continue

            # Resolve competition
            comp_name = f.get("competition", "Unknown")
            session.execute(
                text("INSERT OR IGNORE INTO competitions (name, sport_id) VALUES (:name, :sid)"),
                {"name": comp_name, "sid": sport_id},
            )
            comp_row = session.execute(
                text("SELECT id FROM competitions WHERE name = :name AND sport_id = :sid"),
                {"name": comp_name, "sid": sport_id},
            ).fetchone()
            comp_id = comp_row[0] if comp_row else None

            # Upsert fixture
            kickoff_str = f["kickoff"]
            existing = session.execute(
                text(
                    "SELECT id FROM fixtures "
                    "WHERE sport_id = :sid AND home_team_id = :hid "
                    "AND away_team_id = :aid AND kickoff = :ko"
                ),
                {"sid": sport_id, "hid": home_id, "aid": away_id, "ko": kickoff_str},
            ).fetchone()

            if existing:
                fixture_id = existing[0]
            else:
                result = session.execute(
                    text(
                        "INSERT INTO fixtures "
                        "(sport_id, competition_id, home_team_id, away_team_id, "
                        "kickoff, status, external_id, source, fetched_at) "
                        "VALUES (:sid, :cid, :hid, :aid, :ko, :st, :eid, :src, :fa)"
                    ),
                    {
                        "sid": sport_id, "cid": comp_id,
                        "hid": home_id, "aid": away_id,
                        "ko": kickoff_str, "st": f["status"],
                        "eid": f["external_id"],
                        "src": f["source"],
                        "fa": now,
                    },
                )
                fixture_id = result.lastrowid

            # Source cross-reference
            fs_repo.upsert(
                fixture_id=fixture_id,
                source=f["source"],
                external_id=f["external_id"],
                confidence=0.9,
            )

            # scan_results for pipeline compatibility
            session.execute(
                text(
                    "INSERT OR IGNORE INTO scan_results "
                    "(betting_date, sport, source_domain, event_key, "
                    "home_team, away_team, competition, kickoff, scan_timestamp) "
                    "VALUES (:bd, :sp, :sd, :ek, :ht, :at, :comp, :ko, :ts)"
                ),
                {
                    "bd": date, "sp": f["sport"],
                    "sd": f["source"],
                    "ek": f"{f['home_team']} vs {f['away_team']}",
                    "ht": f["home_team"], "at": f["away_team"],
                    "comp": comp_name,
                    "ko": kickoff_str, "ts": now,
                },
            )

            nested.commit()
            count += 1
        except Exception as e:
            log.warning("Failed to persist %s vs %s: %s", f.get("home_team"), f.get("away_team"), e)
            try:
                nested.rollback()
            except Exception:
                pass

    session.commit()
    session.close()
    return count


def main():
    parser = argparse.ArgumentParser(description="ESPN Event Discovery (all sports)")
    parser.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    parser.add_argument("--sports", help="Comma-separated sports (default: all 5)")
    parser.add_argument("--limit", type=int, default=0, help="Max events to persist (0=all)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    sports = args.sports.split(",") if args.sports else None
    result = discover_espn_events(args.date, sports, args.limit)

    log.info("Discovered %d total events", result["total"])

    # Persist
    persisted = persist_to_db(args.date, result["fixtures"])
    log.info("Persisted %d events to DB", persisted)

    # Write JSON for compatibility
    json_path = DATA_DIR / f"{args.date}_espn_discovery.json"
    with open(json_path, "w") as f:
        json.dump(result, f, indent=2, default=str)

    # AGENT_SUMMARY
    by_sport = {}
    for fix in result["fixtures"]:
        by_sport[fix["sport"]] = by_sport.get(fix["sport"], 0) + 1

    print(f"\n{'='*60}")
    print("AGENT_SUMMARY:" + json.dumps({
        "verdict": "OK" if persisted > 0 else "FAILED",
        "total_discovered": result["total"],
        "persisted": persisted,
        "by_sport": by_sport,
    }))


if __name__ == "__main__":
    main()
