"""Event discovery coordinator — orchestrates sources, dedup, and persistence.

Uses SQLAlchemy ORM for all database operations.
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .dedup import DeduplicationEngine
from .models import (
    DiscoveredEvent,
    DiscoveryResult,
    FixtureSourceModel,
    MergedFixture,
    SourceRef,
    SourceRunStats,
)
from .repository import FixtureSourceRepo
from .sources import SourceAdapter
from .sources.odds_api_io import OddsAPIioAdapter
from .sources.odds_api import OddsAPIAdapter
from .sources.api_football import APIFootballAdapter

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "betting" / "data"
SPORTS = ["football", "volleyball", "basketball", "tennis", "hockey", "cs2", "dota2", "valorant"]


class EventDiscoveryCoordinator:
    """Orchestrates event discovery from multiple sources."""

    def __init__(
        self,
        session: Session,
        sources: list[SourceAdapter] | None = None,
        dedup_engine: DeduplicationEngine | None = None,
    ):
        self.session = session
        self.sources = sources or self._default_sources()
        self.dedup = dedup_engine or DeduplicationEngine()

    @staticmethod
    def _default_sources() -> list[SourceAdapter]:
        # Odds-API.io (primary, all 5 sports) + The-Odds-API (secondary, 4 sports w/ odds) + API-Football (tertiary, football)
        # Disabled: SofaScore (permanent 403)
        return [OddsAPIioAdapter(), OddsAPIAdapter(), APIFootballAdapter()]

    def discover(
        self,
        date: str,
        sports: list[str] | None = None,
        verbose: bool = False,
    ) -> DiscoveryResult:
        """Run full discovery pipeline."""
        target_sports = sports or SPORTS
        if verbose:
            logging.basicConfig(level=logging.INFO)

        logger.info("Starting discovery for %s — sports: %s", date, target_sports)

        # 1. Fetch from all sources concurrently
        events_by_source, source_stats = self._fetch_all_sources(date, target_sports)

        total_raw = sum(len(v) for v in events_by_source.values())
        logger.info("Total raw events across sources: %d", total_raw)

        # 2. Deduplicate + merge
        merged = self.dedup.merge(events_by_source)
        logger.info("After dedup: %d merged fixtures", len(merged))

        # 3. Persist to DB via SQLAlchemy ORM
        persisted = self._persist(date, merged)
        logger.info("Persisted %d fixtures to DB", persisted)

        # 4. Write backward-compatible JSON
        json_path = self._write_json(date, merged)
        logger.info("JSON written to %s", json_path)

        # 5. Build result
        by_sport: dict[str, int] = {}
        for f in merged:
            by_sport[f.sport] = by_sport.get(f.sport, 0) + 1

        issues: list[str] = []
        for src_name, stats in source_stats.items():
            if stats.errors:
                issues.extend(stats.errors)

        verdict = "OK"
        if total_raw == 0:
            verdict = "FAILED"
        elif persisted == 0 and len(merged) > 0:
            verdict = "PARTIAL"
            issues.append(f"Fetched {len(merged)} fixtures but persisted 0 to DB")
        elif any(not s.available for s in source_stats.values()):
            verdict = "PARTIAL"

        return DiscoveryResult(
            date=date,
            fixtures=merged,
            total_discovered=total_raw,
            total_after_dedup=len(merged),
            by_sport=by_sport,
            source_stats=source_stats,
            issues=issues,
            verdict=verdict,
        )

    def _fetch_all_sources(
        self, date: str, sports: list[str]
    ) -> tuple[dict[str, list[DiscoveredEvent]], dict[str, SourceRunStats]]:
        """Fetch from all sources concurrently using ThreadPoolExecutor."""
        events_by_source: dict[str, list[DiscoveredEvent]] = {}
        source_stats: dict[str, SourceRunStats] = {}

        def _fetch_source(source: SourceAdapter) -> tuple[str, list[DiscoveredEvent], SourceRunStats]:
            all_events: list[DiscoveredEvent] = []
            stats = SourceRunStats(
                source=source.name,
                available=source.is_available(),
            )
            start = time.monotonic()

            for sport in sports:
                if sport not in source.supported_sports:
                    continue
                try:
                    events = source.fetch_events(date, sport)
                    all_events.extend(events)
                    if events:
                        stats.sports_covered.append(sport)
                except Exception as e:
                    stats.errors.append(f"{source.name}/{sport}: {e}")

            stats.events_fetched = len(all_events)
            stats.duration_seconds = round(time.monotonic() - start, 1)
            return source.name, all_events, stats

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(_fetch_source, src): src.name
                for src in self.sources
            }
            for future in as_completed(futures):
                try:
                    name, events, stats = future.result()
                    events_by_source[name] = events
                    source_stats[name] = stats
                except Exception as e:
                    src_name = futures[future]
                    logger.error("Source %s crashed: %s", src_name, e)
                    source_stats[src_name] = SourceRunStats(
                        source=src_name, available=False,
                        errors=[str(e)],
                    )

        return events_by_source, source_stats

    def _persist(self, date: str, fixtures: list[MergedFixture]) -> int:
        """Write merged fixtures to DB using SQLAlchemy ORM.

        Uses nested transactions (savepoints) per fixture so that a single
        failure does not roll back the entire batch.
        """
        now = datetime.now(timezone.utc).isoformat()
        fs_repo = FixtureSourceRepo(self.session)
        count = 0

        for mf in fixtures:
            try:
                nested = self.session.begin_nested()
                # Resolve sport
                sport_row = self.session.execute(
                    text("SELECT id FROM sports WHERE name = :name"),
                    {"name": mf.sport},
                ).fetchone()
                if not sport_row:
                    # Create sport
                    self.session.execute(
                        text("INSERT OR IGNORE INTO sports (name, tier) VALUES (:name, 1)"),
                        {"name": mf.sport},
                    )
                    sport_row = self.session.execute(
                        text("SELECT id FROM sports WHERE name = :name"),
                        {"name": mf.sport},
                    ).fetchone()
                sport_id = sport_row[0]

                # Resolve/create teams
                home_id = self._resolve_team(sport_id, mf.home_team)
                away_id = self._resolve_team(sport_id, mf.away_team)

                # Resolve/create competition
                comp_id = self._resolve_competition(sport_id, mf.competition, mf.country)

                kickoff_str = mf.kickoff.isoformat()

                # Upsert fixture
                existing = self.session.execute(
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
                    result = self.session.execute(
                        text(
                            "INSERT INTO fixtures "
                            "(sport_id, competition_id, home_team_id, away_team_id, "
                            "kickoff, status, external_id, source, fetched_at) "
                            "VALUES (:sid, :cid, :hid, :aid, :ko, :st, :eid, :src, :fa)"
                        ),
                        {
                            "sid": sport_id, "cid": comp_id,
                            "hid": home_id, "aid": away_id,
                            "ko": kickoff_str, "st": mf.status,
                            "eid": mf.primary_external_id,
                            "src": mf.primary_source,
                            "fa": now,
                        },
                    )
                    fixture_id = result.lastrowid

                # Write source cross-references via ORM
                for src_ref in mf.sources:
                    fs_repo.upsert(
                        fixture_id=fixture_id,
                        source=src_ref.source,
                        external_id=src_ref.external_id,
                        confidence=src_ref.confidence,
                        raw_data=src_ref.raw_data if isinstance(src_ref.raw_data, dict) else None,
                    )

                # Write scan_result
                self.session.execute(
                    text(
                        "INSERT OR IGNORE INTO scan_results "
                        "(betting_date, sport, source_domain, event_key, "
                        "home_team, away_team, competition, kickoff, scan_timestamp) "
                        "VALUES (:bd, :sp, :sd, :ek, :ht, :at, :comp, :ko, :ts)"
                    ),
                    {
                        "bd": date, "sp": mf.sport,
                        "sd": mf.primary_source,
                        "ek": f"{mf.home_team} vs {mf.away_team}",
                        "ht": mf.home_team, "at": mf.away_team,
                        "comp": mf.competition,
                        "ko": kickoff_str, "ts": now,
                    },
                )

                nested.commit()
                count += 1
            except Exception as e:
                logger.warning(
                    "Failed to persist %s vs %s: %s",
                    mf.home_team, mf.away_team, e,
                )
                nested.rollback()
                continue

        self.session.commit()
        return count

    def _resolve_team(self, sport_id: int, name: str) -> int:
        """Find or create a team, return its ID.

        Resolution order:
        1. Exact name match (fast, indexed)
        2. Alias match via json_each
        3. Normalized diacritics match (strips accents, compares ASCII)
        4. Only if all fail: create new team entry
        """
        # 1. Exact match
        row = self.session.execute(
            text("SELECT id FROM teams WHERE sport_id = :sid AND name = :name"),
            {"sid": sport_id, "name": name},
        ).fetchone()
        if row:
            return row[0]

        # 2. Alias match
        row = self.session.execute(
            text(
                "SELECT t.id FROM teams t, json_each(t.aliases) AS a "
                "WHERE t.sport_id = :sid AND a.value = :name"
            ),
            {"sid": sport_id, "name": name},
        ).fetchone()
        if row:
            return row[0]

        # 3. Normalized diacritics match + suffix-stripping
        import re
        import unicodedata
        from bet.utils import normalize_team_name

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
            rows = self.session.execute(
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
                    # Auto-add as alias to prevent future table scans
                    self.session.execute(
                        text(
                            "UPDATE teams SET aliases = json_insert("
                            "COALESCE(aliases, '[]'), '$[#]', :alias"
                            ") WHERE id = :tid"
                        ),
                        {"alias": name, "tid": r[0]},
                    )
                    return r[0]
                # Suffix-stripped comparison (FC, SC, United, etc.) — skip if identity markers differ
                if suffix_stripped_input and len(suffix_stripped_input) >= 3 and not has_identity_marker:
                    candidate_has_marker = bool(_identity_re.search(r[1]))
                    if not candidate_has_marker:
                        canonical_suffix_stripped = normalize_team_name(r[1])
                        if canonical_suffix_stripped == suffix_stripped_input:
                            self.session.execute(
                                text(
                                    "UPDATE teams SET aliases = json_insert("
                                    "COALESCE(aliases, '[]'), '$[#]', :alias"
                                    ") WHERE id = :tid"
                                ),
                                {"alias": name, "tid": r[0]},
                            )
                            return r[0]

        # 4. Create new team
        result = self.session.execute(
            text("INSERT INTO teams (sport_id, name) VALUES (:sid, :name)"),
            {"sid": sport_id, "name": name},
        )
        return result.lastrowid

    def _resolve_competition(self, sport_id: int, name: str, country: str = "") -> int | None:
        """Find or create a competition, return its ID."""
        if not name:
            return None

        row = self.session.execute(
            text(
                "SELECT id FROM competitions "
                "WHERE sport_id = :sid AND name = :name AND season = ''"
            ),
            {"sid": sport_id, "name": name},
        ).fetchone()
        if row:
            return row[0]

        result = self.session.execute(
            text(
                "INSERT OR IGNORE INTO competitions "
                "(sport_id, name, country, season) VALUES (:sid, :name, :country, '')"
            ),
            {"sid": sport_id, "name": name, "country": country},
        )
        if result.rowcount > 0:
            return result.lastrowid
        # INSERT OR IGNORE hit a conflict — fetch existing
        row = self.session.execute(
            text(
                "SELECT id FROM competitions "
                "WHERE sport_id = :sid AND name = :name AND season = ''"
            ),
            {"sid": sport_id, "name": name},
        ).fetchone()
        return row[0] if row else None

    def _write_json(self, date: str, fixtures: list[MergedFixture]) -> Path:
        """Write backward-compatible JSON output."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DATA_DIR / f"{date}_s1_events.json"

        data = []
        for mf in fixtures:
            data.append({
                "sport": mf.sport,
                "competition": mf.competition,
                "country": mf.country,
                "home_team": mf.home_team,
                "away_team": mf.away_team,
                "kickoff": mf.kickoff.isoformat(),
                "status": mf.status,
                "source": mf.primary_source,
                "external_id": mf.primary_external_id,
                "source_count": mf.source_count,
                "sources": [
                    {"source": s.source, "external_id": s.external_id, "confidence": s.confidence}
                    for s in mf.sources
                ],
            })

        out_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return out_path
