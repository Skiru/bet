"""Deduplication engine for merging events from multiple discovery sources.

Uses normalize_team_name for exact matching, rapidfuzz for fuzzy matching,
and a ±2h kickoff window for temporal matching.
"""

import logging
from collections import defaultdict
from datetime import datetime

from rapidfuzz import fuzz

from bet.utils import normalize_team_name

from .esports_aliases import resolve_alias
from .team_aliases import resolve_team_alias
from .models import DiscoveredEvent, MergedFixture, SourceRef

logger = logging.getLogger(__name__)


def _tokens_contained(a: str, b: str) -> bool:
    """Is one name's token set the other's, plus qualifiers only?

    True for ("genk", "krc genk") and ("alaves", "deportivo alaves"); false for
    ("stade lavallois", "laval") and ("sporting lisbon", "sporting cp"), which
    need an alias table rather than a matcher. Requires the shorter side to be
    non-empty, so a name that normalizes away entirely matches nothing.
    """
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return False
    return ta <= tb or tb <= ta


class DeduplicationEngine:
    """Merge events from multiple sources into unified fixtures."""

    SOURCE_PRIORITY = [
        "odds-api-io",
        "odds-api",
        "api-football",
        "api-basketball",
        "api-volleyball",
        "api-hockey",
    ]
    FUZZY_THRESHOLD = 85
    KICKOFF_WINDOW_HOURS = 2

    def __init__(self, fuzzy_threshold: int = 85):
        self.fuzzy_threshold = fuzzy_threshold
        self.last_issues: list[str] = []

    def merge(
        self, events_by_source: dict[str, list[DiscoveredEvent]]
    ) -> list[MergedFixture]:
        """Merge events from all sources.

        Priority order: odds-api-io (primary) → odds-api (secondary)
        → api-football (tertiary).
        Primary source establishes canonical names.
        Sources not in the priority list are processed last.
        """
        self.last_issues = []
        merged: list[MergedFixture] = []
        key_index: dict[str, int] = {}  # match_key → index in merged
        id_to_index: dict[int, int] = {}  # id(fixture) → index in merged

        # Process in priority order, then any remaining sources
        ordered_sources = list(self.SOURCE_PRIORITY)
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
                            raw_status=ev.status,
                            raw_kickoff=ev.kickoff,
                            raw_home_team=ev.home_team,
                            raw_away_team=ev.away_team,
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
        return self._normalize_duplicate_source_refs(merged)

    ESPORTS_SPORTS = {"cs2", "dota2", "valorant"}

    def _match_key(self, event: DiscoveredEvent) -> str:
        """Exact dedup key with 2-hour kickoff bucket to avoid same-day false merges."""
        norm_home = normalize_team_name(resolve_team_alias(event.home_team))
        norm_away = normalize_team_name(resolve_team_alias(event.away_team))
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

        ev_home = normalize_team_name(resolve_team_alias(event.home_team))
        ev_away = normalize_team_name(resolve_team_alias(event.away_team))
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

            cand_home = normalize_team_name(resolve_team_alias(fixture.home_team))
            cand_away = normalize_team_name(resolve_team_alias(fixture.away_team))
            if event.sport in self.ESPORTS_SPORTS:
                cand_home = resolve_alias(cand_home)
                cand_away = resolve_alias(cand_away)

            home_score = fuzz.token_sort_ratio(ev_home, cand_home)
            away_score = fuzz.token_sort_ratio(ev_away, cand_away)

            combined = min(home_score, away_score)
            if combined >= self.fuzzy_threshold and combined > best_score:
                best_score = combined
                best_match = fixture
                continue

            # Second chance: one feed spells the club with a qualifier the other
            # omits. token_sort_ratio scores that pair on *length*, so the more
            # a source elaborates the lower it scores -- "Genk"/"KRC Genk" is 67,
            # "Alaves"/"Deportivo Alaves" 55, "Boulogne"/"US Boulogne Cote
            # dOpale" 55 -- and all three land below any threshold loose enough
            # to be safe. Measured on the 2026-08-28 slate: 19 groups, 23
            # surplus fixtures, one of which reached the coupon twice as the
            # same market at the same line, so an operator working down the list
            # would have staked it twice believing he was diversifying.
            #
            # Token *containment* is the right question for that shape, and it
            # is paired with an exact-kickoff requirement rather than the ±2h
            # window: containment alone would merge a first team with a reserve
            # or B side, and two genuinely different fixtures starting on the
            # same second in the same sport are rare where two spellings of one
            # fixture are routine. Every one of the 23 shared an exact kickoff.
            if event.kickoff == fixture.kickoff and (
                _tokens_contained(ev_home, cand_home)
                and _tokens_contained(ev_away, cand_away)
            ):
                score = float(self.fuzzy_threshold)
                if score > best_score:
                    best_score = score
                    best_match = fixture

        if best_match is not None:
            return best_match, best_score / 100.0

        return None, 0.0

    def _kickoff_within_window(self, t1: datetime, t2: datetime) -> bool:
        """Check if two kickoff times are within ±KICKOFF_WINDOW_HOURS."""
        delta = abs((t1 - t2).total_seconds())
        return delta <= self.KICKOFF_WINDOW_HOURS * 3600

    def _normalize_duplicate_source_refs(
        self, fixtures: list[MergedFixture]
    ) -> list[MergedFixture]:
        active: list[MergedFixture | None] = list(fixtures)
        max_iterations = max(1, len(fixtures) * max(1, sum(len(f.sources) for f in fixtures)))
        iterations = 0

        while True:
            iterations += 1
            if iterations > max_iterations:
                self.last_issues.append(
                    "DISCOVERY_DUPLICATE_SOURCE_REF action=normalization_guard_triggered "
                    "source=UNKNOWN external_id=UNKNOWN fixtures=[]"
                )
                logger.warning(
                    "Duplicate source ref normalization aborted after %d iterations",
                    max_iterations,
                )
                break
            owners: dict[tuple[str, str], list[int]] = defaultdict(list)
            for idx, fixture in enumerate(active):
                if fixture is None:
                    continue
                for src_ref in fixture.sources:
                    owners[(src_ref.source, src_ref.external_id)].append(idx)

            duplicate_groups = [
                (key, indexes)
                for key, indexes in owners.items()
                if len(set(indexes)) > 1
            ]
            if not duplicate_groups:
                break

            for (source, external_id), indexes in duplicate_groups:
                unique_indexes = sorted(
                    set(indexes),
                    key=lambda idx: self._fixture_rank(active[idx], idx),
                )
                canonical_idx = unique_indexes[0]
                canonical = active[canonical_idx]
                if canonical is None:
                    continue

                for duplicate_idx in unique_indexes[1:]:
                    duplicate = active[duplicate_idx]
                    if duplicate is None:
                        continue

                    if self._fixtures_semantically_compatible(canonical, duplicate):
                        self._merge_fixture(canonical, duplicate)
                        self.last_issues.append(
                            self._duplicate_issue(
                                action="merged",
                                source=source,
                                external_id=external_id,
                                fixtures=(canonical, duplicate),
                            )
                        )
                        active[duplicate_idx] = None
                        self._recanonicalize_fixture(canonical)
                        continue

                    self._remove_source_ref(duplicate, source, external_id)
                    self.last_issues.append(
                        self._duplicate_issue(
                            action="duplicate_source_ref_quarantined",
                            source=source,
                            external_id=external_id,
                            fixtures=(canonical, duplicate),
                        )
                    )
                    if duplicate.sources:
                        self._recanonicalize_fixture(duplicate)
                    else:
                        active[duplicate_idx] = None

        return [fixture for fixture in active if fixture is not None]

    def _fixtures_semantically_compatible(
        self, left: MergedFixture, right: MergedFixture
    ) -> bool:
        if left.sport != right.sport:
            return False
        if not self._kickoff_within_window(left.kickoff, right.kickoff):
            return False

        left_home = normalize_team_name(left.home_team)
        left_away = normalize_team_name(left.away_team)
        right_home = normalize_team_name(right.home_team)
        right_away = normalize_team_name(right.away_team)
        if left.sport in self.ESPORTS_SPORTS:
            left_home = resolve_alias(left_home)
            left_away = resolve_alias(left_away)
            right_home = resolve_alias(right_home)
            right_away = resolve_alias(right_away)

        if left_home == right_home and left_away == right_away:
            return True

        home_score = fuzz.token_sort_ratio(left_home, right_home)
        away_score = fuzz.token_sort_ratio(left_away, right_away)
        return min(home_score, away_score) >= self.fuzzy_threshold

    def _merge_fixture(
        self, canonical: MergedFixture, duplicate: MergedFixture
    ) -> None:
        existing_by_source = {src.source: src for src in canonical.sources}
        for src_ref in duplicate.sources:
            existing = existing_by_source.get(src_ref.source)
            if existing is None:
                canonical.sources.append(src_ref)
                existing_by_source[src_ref.source] = src_ref
                continue

            if existing.external_id == src_ref.external_id:
                if src_ref.confidence > existing.confidence:
                    existing.confidence = src_ref.confidence
                if existing.raw_data is None and src_ref.raw_data is not None:
                    existing.raw_data = src_ref.raw_data
                continue

            if src_ref.confidence > existing.confidence:
                existing.external_id = src_ref.external_id
                existing.confidence = src_ref.confidence
                existing.raw_data = src_ref.raw_data

        if duplicate.odds and not canonical.odds:
            canonical.odds = duplicate.odds

    @classmethod
    def _remove_source_ref(
        cls, fixture: MergedFixture, source: str, external_id: str
    ) -> None:
        fixture.sources = [
            src
            for src in fixture.sources
            if not (src.source == source and src.external_id == external_id)
        ]

    def _recanonicalize_fixture(self, fixture: MergedFixture) -> None:
        best_source = min(
            fixture.sources,
            key=lambda src: (self._source_priority_rank(src.source), src.source, src.external_id),
        )
        fixture.primary_source = best_source.source
        fixture.primary_external_id = best_source.external_id

    def _fixture_rank(self, fixture: MergedFixture | None, index: int) -> tuple:
        if fixture is None:
            return (float("inf"),)
        return (
            -len(fixture.sources),
            self._source_priority_rank(fixture.primary_source),
            0 if fixture.odds else 1,
            fixture.kickoff.isoformat(),
            fixture.home_team,
            fixture.away_team,
            index,
        )

    def _source_priority_rank(self, source: str) -> int:
        try:
            return self.SOURCE_PRIORITY.index(source)
        except ValueError:
            return len(self.SOURCE_PRIORITY)

    @staticmethod
    def _fixture_identity(fixture: MergedFixture) -> str:
        return (
            f"{fixture.sport}|{fixture.home_team}|{fixture.away_team}|"
            f"{fixture.kickoff.isoformat()}"
        )

    def _duplicate_issue(
        self,
        *,
        action: str,
        source: str,
        external_id: str,
        fixtures: tuple[MergedFixture, MergedFixture],
    ) -> str:
        canonical, duplicate = fixtures
        return (
            "DISCOVERY_DUPLICATE_SOURCE_REF "
            f"action={action} source={source} external_id={external_id} "
            f"fixtures=[{self._fixture_identity(canonical)},"
            f"{self._fixture_identity(duplicate)}]"
        )

    @staticmethod
    def _can_attach_source(fixture: MergedFixture, event: DiscoveredEvent) -> bool:
        for src in fixture.sources:
            if src.source != event.source:
                continue
            return src.external_id == event.external_id
        return True

    def deduplicate_events(self, events: list[DiscoveredEvent]) -> list[MergedFixture]:
        """Convenience method for deduplicating a flat list of discovered events."""
        events_by_source: dict[str, list[DiscoveredEvent]] = defaultdict(list)
        for ev in events:
            events_by_source[ev.source].append(ev)
        return self.merge(events_by_source)

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
                raw_status=event.status,
                raw_kickoff=event.kickoff,
                raw_home_team=event.home_team,
                raw_away_team=event.away_team,
            )
        )
        # Merge odds if the new event has them and the fixture doesn't
        if event.odds and not fixture.odds:
            fixture.odds = event.odds
