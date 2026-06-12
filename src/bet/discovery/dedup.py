"""Deduplication engine for merging events from multiple discovery sources.

Uses normalize_team_name for exact matching, rapidfuzz for fuzzy matching,
and a ±2h kickoff window for temporal matching.
"""

import logging
from datetime import datetime

from rapidfuzz import fuzz

from bet.utils import normalize_team_name

from .esports_aliases import resolve_alias
from .models import DiscoveredEvent, MergedFixture, SourceRef

logger = logging.getLogger(__name__)


class DeduplicationEngine:
    """Merge events from multiple sources into unified fixtures."""

    FUZZY_THRESHOLD = 85
    KICKOFF_WINDOW_HOURS = 2

    def __init__(self, fuzzy_threshold: int = 85):
        self.fuzzy_threshold = fuzzy_threshold

    def merge(
        self, events_by_source: dict[str, list[DiscoveredEvent]]
    ) -> list[MergedFixture]:
        """Merge events from all sources.

        Priority order: odds-api-io (primary) → odds-api (secondary)
        → api-football (tertiary).
        Primary source establishes canonical names.
        Sources not in the priority list are processed last.
        """
        source_priority = [
            "odds-api-io",
            "odds-api",
            "api-football",
            "api-basketball",
            "api-volleyball",
            "api-hockey",
        ]
        merged: list[MergedFixture] = []
        key_index: dict[str, int] = {}  # match_key → index in merged
        id_to_index: dict[int, int] = {}  # id(fixture) → index in merged

        # Process in priority order, then any remaining sources
        ordered_sources = list(source_priority)
        for name in events_by_source:
            if name not in ordered_sources:
                ordered_sources.append(name)

        for source_name in ordered_sources:
            events = events_by_source.get(source_name, [])
            for ev in events:
                match_key = self._match_key(ev)

                # Exact match
                if match_key in key_index:
                    idx = key_index[match_key]
                    if not self._can_attach_source(merged[idx], ev):
                        key_index.pop(match_key, None)
                    else:
                        self._attach_source(merged[idx], ev)
                        continue

                # Fuzzy match against existing merged fixtures
                best_match, confidence = self._fuzzy_match(ev, merged)
                if best_match is not None:
                    if self._can_attach_source(best_match, ev):
                        self._attach_source(best_match, ev, confidence)
                        # Also register exact key for future lookups
                        key_index[match_key] = id_to_index[id(best_match)]
                        continue

                # New fixture
                fixture = MergedFixture(
                    sport=ev.sport,
                    competition=ev.competition,
                    country=ev.country,
                    home_team=ev.home_team,
                    away_team=ev.away_team,
                    kickoff=ev.kickoff,
                    status=ev.status,
                    sources=[
                        SourceRef(
                            source=ev.source,
                            external_id=ev.external_id,
                            confidence=1.0,
                            raw_data=ev.raw_data,
                        )
                    ],
                    primary_source=ev.source,
                    primary_external_id=ev.external_id,
                    odds=ev.odds,
                )
                key_index[match_key] = len(merged)
                id_to_index[id(fixture)] = len(merged)
                merged.append(fixture)

        logger.info(
            "Dedup: %d raw events → %d merged fixtures",
            sum(len(v) for v in events_by_source.values()),
            len(merged),
        )
        return merged

    ESPORTS_SPORTS = {"cs2", "dota2", "valorant"}

    def _match_key(self, event: DiscoveredEvent) -> str:
        """Exact dedup key with 2-hour kickoff bucket to avoid same-day false merges."""
        norm_home = normalize_team_name(event.home_team)
        norm_away = normalize_team_name(event.away_team)
        # For esports, also resolve aliases (NaVi → natus vincere)
        if event.sport in self.ESPORTS_SPORTS:
            norm_home = resolve_alias(norm_home)
            norm_away = resolve_alias(norm_away)
        kickoff_date = event.kickoff.strftime("%Y-%m-%d")
        kickoff_bucket = event.kickoff.hour // self.KICKOFF_WINDOW_HOURS
        return f"{event.sport}|{norm_home}|{norm_away}|{kickoff_date}|{kickoff_bucket}"

    def _fuzzy_match(
        self, event: DiscoveredEvent, candidates: list[MergedFixture]
    ) -> tuple[MergedFixture | None, float]:
        """Find best fuzzy match among candidates. Returns (match, confidence)."""
        if not candidates:
            return None, 0.0

        ev_home = normalize_team_name(event.home_team)
        ev_away = normalize_team_name(event.away_team)
        # For esports, resolve aliases before fuzzy comparison
        if event.sport in self.ESPORTS_SPORTS:
            ev_home = resolve_alias(ev_home)
            ev_away = resolve_alias(ev_away)
        best_match = None
        best_score = 0.0

        for fixture in candidates:
            # Sport must match exactly
            if fixture.sport != event.sport:
                continue

            # Kickoff must be within window
            if not self._kickoff_within_window(event.kickoff, fixture.kickoff):
                continue

            cand_home = normalize_team_name(fixture.home_team)
            cand_away = normalize_team_name(fixture.away_team)
            if event.sport in self.ESPORTS_SPORTS:
                cand_home = resolve_alias(cand_home)
                cand_away = resolve_alias(cand_away)

            home_score = fuzz.token_sort_ratio(ev_home, cand_home)
            away_score = fuzz.token_sort_ratio(ev_away, cand_away)

            combined = min(home_score, away_score)
            if combined >= self.fuzzy_threshold and combined > best_score:
                best_score = combined
                best_match = fixture

        if best_match is not None:
            return best_match, best_score / 100.0

        return None, 0.0

    def _kickoff_within_window(self, t1: datetime, t2: datetime) -> bool:
        """Check if two kickoff times are within ±KICKOFF_WINDOW_HOURS."""
        delta = abs((t1 - t2).total_seconds())
        return delta <= self.KICKOFF_WINDOW_HOURS * 3600

    @staticmethod
    def _can_attach_source(fixture: MergedFixture, event: DiscoveredEvent) -> bool:
        for src in fixture.sources:
            if src.source != event.source:
                continue
            return src.external_id == event.external_id
        return True

    @staticmethod
    def _attach_source(
        fixture: MergedFixture,
        event: DiscoveredEvent,
        confidence: float = 1.0,
    ) -> None:
        """Attach a new source reference to an existing merged fixture."""
        # Don't duplicate sources
        for src in fixture.sources:
            if src.source == event.source:
                return

        fixture.sources.append(
            SourceRef(
                source=event.source,
                external_id=event.external_id,
                confidence=confidence,
                raw_data=event.raw_data,
            )
        )
        # Merge odds if the new event has them and the fixture doesn't
        if event.odds and not fixture.odds:
            fixture.odds = event.odds
