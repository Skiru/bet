from __future__ import annotations

import json
import math
import time
import random
from abc import ABC, abstractmethod
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from bet.scrapers.constants import USER_AGENTS
from bet.scrapers.models import ScraperRun


class ScraperError(Exception):
    pass


class ScraperRateLimitError(ScraperError):
    pass


class BaseScraper(ABC):
    sport: str
    source_name: str
    _request_delay: tuple[float, float] = (1.0, 3.0)

    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    @abstractmethod
    def scrape_team_season_stats(self, competition: str, season: str) -> int:
        pass

    @abstractmethod
    def scrape_player_season_stats(self, competition: str, season: str) -> int:
        pass

    def scrape_player_match_stats(self, competition: str, season: str) -> int:
        raise NotImplementedError("Player match stats scraping not implemented.")

    def scrape_fixtures(self, date: str) -> int:
        raise NotImplementedError("Fixtures scraping not implemented.")

    def _rate_limit(self) -> None:
        time.sleep(random.uniform(*self._request_delay))

    def _get_headers(self) -> dict:
        return {"User-Agent": random.choice(USER_AGENTS)}

    def _get_session(self):
        return self.session_factory()

    @contextmanager
    def _track_run(self, session, target: str):
        """Context manager for automatic run tracking."""
        run = ScraperRun(
            scraper_name=self.__class__.__name__,
            sport=self.sport,
            target=target,
            status="running",
        )
        session.add(run)
        session.flush()
        try:
            counts = {"scraped": 0, "inserted": 0, "updated": 0}
            yield counts
            run.status = "success"
        except Exception as e:
            run.status = "failed"
            run.error_message = str(e)[:500]
            raise
        finally:
            run.records_scraped = counts.get("scraped", 0)
            run.records_inserted = counts.get("inserted", 0)
            run.records_updated = counts.get("updated", 0)

    def _upsert_league_profiles(self, session, comp_id: int, season: str,
                                 stat_accumulator: dict[str, list[float]]) -> int:
        """Write league averages from accumulated per-team values.

        stat_accumulator maps stat_key → list of per-team values.
        For each key, we compute the mean and upsert into league_profiles.
        """
        now_str = datetime.now(timezone.utc).isoformat()
        inserted = 0
        for sk, values in stat_accumulator.items():
            if not values:
                continue
            avg = sum(values) / len(values)
            session.execute(
                text("""
                    INSERT INTO league_profiles
                    (competition_id, stat_key, season, avg_value, sample_size, updated_at)
                    VALUES (:cid, :sk, :sea, :sv, :ss, :upd)
                    ON CONFLICT(competition_id, stat_key, season) DO UPDATE SET
                        avg_value = :sv, sample_size = :ss, updated_at = :upd
                """),
                {"cid": comp_id, "sk": sk, "sea": season,
                 "sv": avg, "ss": len(values), "upd": now_str},
            )
            inserted += 1
        return inserted

    @staticmethod
    def _safe_json_dumps(obj: dict) -> str:
        """JSON-serialize a dict, handling numpy/pandas types."""
        clean = {}
        for k, v in obj.items():
            if v is None:
                continue
            try:
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    continue
                clean[k] = float(v)
            except (ValueError, TypeError):
                clean[k] = str(v)
        return json.dumps(clean)

    def _log_run(self, session, target: str, status: str, records: dict, error: str = None, run_obj=None):
        if not run_obj:
            run_obj = ScraperRun(
                scraper_name=self.__class__.__name__,
                sport=self.sport,
                target=target,
                status=status
            )
            session.add(run_obj)
        else:
            run_obj.status = status
            if error:
                run_obj.error_message = error

        run_obj.records_scraped = records.get("scraped", 0)
        run_obj.records_inserted = records.get("inserted", 0)
        run_obj.records_updated = records.get("updated", 0)

        session.commit()
        return run_obj

    def _find_or_create_sport(self, session, sport_name: str) -> int:
        res = session.execute(
            text("SELECT id FROM sports WHERE name = :n"),
            {"n": sport_name}
        ).fetchone()
        if res:
            return res[0]
        
        session.execute(
            text("INSERT OR IGNORE INTO sports (name) VALUES (:n)"),
            {"n": sport_name}
        )
        session.commit()
        return session.execute(
            text("SELECT id FROM sports WHERE name = :n"),
            {"n": sport_name}
        ).fetchone()[0]

    def _find_or_create_competition(self, session, sport_id: int, name: str, country: str, season: str) -> int:
        res = session.execute(
            text("SELECT id FROM competitions WHERE sport_id = :sid AND name = :n AND season = :sea"),
            {"sid": sport_id, "n": name, "sea": season}
        ).fetchone()
        if res:
            return res[0]
            
        session.execute(
            text("INSERT OR IGNORE INTO competitions (sport_id, name, country, season) VALUES (:sid, :n, :c, :sea)"),
            {"sid": sport_id, "n": name, "c": country, "sea": season}
        )
        session.commit()
        return session.execute(
            text("SELECT id FROM competitions WHERE sport_id = :sid AND name = :n AND season = :sea"),
            {"sid": sport_id, "n": name, "sea": season}
        ).fetchone()[0]

    def _find_or_create_team(self, session, sport_id: int, name: str, country: str = "") -> int:
        import unicodedata

        # 1. Exact match
        res = session.execute(
            text("SELECT id FROM teams WHERE sport_id = :sid AND name = :n"),
            {"sid": sport_id, "n": name}
        ).fetchone()
        if res:
            return res[0]

        # 2. Alias match
        res = session.execute(
            text(
                "SELECT t.id FROM teams t, json_each(t.aliases) AS a "
                "WHERE t.sport_id = :sid AND a.value = :n"
            ),
            {"sid": sport_id, "n": name}
        ).fetchone()
        if res:
            return res[0]

        # 3. Normalized diacritics match + suffix stripping
        import re
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
            rows = session.execute(
                text("SELECT id, name FROM teams WHERE sport_id = :sid"),
                {"sid": sport_id}
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
                    session.commit()
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
                            session.commit()
                            return r[0]

        # 4. Create new
        session.execute(
            text("INSERT OR IGNORE INTO teams (sport_id, name, country) VALUES (:sid, :n, :c)"),
            {"sid": sport_id, "n": name, "c": country}
        )
        session.commit()
        return session.execute(
            text("SELECT id FROM teams WHERE sport_id = :sid AND name = :n"),
            {"sid": sport_id, "n": name}
        ).fetchone()[0]

    def _find_or_create_athlete(self, session, external_id: str, sport_id: int, name: str, team_id: int = None, position: str = None) -> int:
        res = session.execute(
            text("SELECT id FROM athletes WHERE external_id = :eid AND sport_id = :sid"),
            {"eid": external_id, "sid": sport_id}
        ).fetchone()
        if res:
            return res[0]
            
        from datetime import datetime, timezone
        now_str = datetime.now(timezone.utc).isoformat()
        session.execute(
            text("""
                INSERT OR IGNORE INTO athletes (external_id, sport_id, team_id, name, position, source, updated_at) 
                VALUES (:eid, :sid, :tid, :n, :pos, :src, :upd)
            """),
            {
                "eid": external_id, "sid": sport_id, "tid": team_id, "n": name,
                "pos": position, "src": self.source_name, "upd": now_str
            }
        )
        session.commit()
        return session.execute(
            text("SELECT id FROM athletes WHERE external_id = :eid AND sport_id = :sid"),
            {"eid": external_id, "sid": sport_id}
        ).fetchone()[0]
