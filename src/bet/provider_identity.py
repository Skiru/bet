"""Provider-specific team identity resolution with durable alias caching."""

from __future__ import annotations

import logging
import re
from typing import Callable

from bet.db.connection import get_db
from bet.db.repositories import SportRepo, TeamRepo, TeamSourceAliasRepo
from bet.utils import normalize_team_name


logger = logging.getLogger(__name__)


def _clean_variant(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip())


def build_provider_team_variants(
    team_name: str,
    sport: str,
    source: str = "",
    extra_names: list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    sport_key = (sport or "").lower().strip()
    raw_candidates = [_clean_variant(team_name)]
    raw_candidates.extend(_clean_variant(name) for name in (extra_names or []))

    variants: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        candidate = _clean_variant(value)
        if not candidate:
            return
        key = candidate.lower()
        if key in seen:
            return
        seen.add(key)
        variants.append(candidate)

    for candidate in raw_candidates:
        add(candidate)

        normalized = normalize_team_name(candidate)
        if normalized:
            add(normalized)
            add(" ".join(token.upper() if len(token) <= 3 else token.title() for token in normalized.split()))

        compact = re.sub(r"[./,_-]+", " ", candidate)
        add(compact)

        if sport_key == "basketball":
            add(re.sub(r"\b(bkb|basket|basketball|club|bc|bk|kk)\b", "", candidate, flags=re.IGNORECASE))
        elif sport_key == "volleyball":
            add(re.sub(r"\b(volley|volleyball|vc|vk)\b", "", candidate, flags=re.IGNORECASE))
        elif sport_key in {"cs2", "valorant", "dota2"}:
            add(re.sub(r"\b(team|esports|eSports|gaming|clan|club)\b", "", candidate, flags=re.IGNORECASE))

    return [variant for variant in variants if len(variant) >= 2]


def resolve_provider_team_id(
    *,
    team_name: str,
    sport: str,
    source: str,
    resolver: Callable[[str], str | int | None],
    competition: str = "",
) -> tuple[str | None, dict]:
    metadata = {
        "status": "unresolved",
        "source": source,
        "team_name": team_name,
        "competition": competition,
        "cache_hit": False,
        "attempted_names": [],
        "provider_team_name": None,
        "cache_error": None,
    }

    team = None
    sport_obj = None
    cached_provider_id: str | None = None
    cached_names: list[str] = []
    failed_names: set[str] = set()
    team_aliases: list[str] = []

    try:
        with get_db() as conn:
            sport_obj = SportRepo(conn).get_by_name((sport or "").lower())
            if sport_obj is not None:
                team = TeamRepo(conn).resolve(team_name, sport_obj.id)
            if team is not None:
                alias_repo = TeamSourceAliasRepo(conn)
                cached_provider_id = alias_repo.get_verified_provider_team_id(team.id, source, competition)
                cached_names = alias_repo.get_candidate_provider_names(team.id, source, competition)
                failed_names = alias_repo.get_failed_provider_names(team.id, source, competition)
                team_aliases = list(team.aliases or [])
    except Exception as exc:
        metadata["cache_error"] = f"lookup:{exc}"
        logger.warning("Provider identity cache lookup failed for %s/%s: %s", source, team_name, exc)

    if cached_provider_id:
        metadata["status"] = "cache_hit"
        metadata["cache_hit"] = True
        return cached_provider_id, metadata

    candidates = build_provider_team_variants(
        team_name,
        sport,
        source=source,
        extra_names=[*cached_names, *team_aliases],
    )
    failed_name_keys = {failed.lower() for failed in failed_names}
    candidates = [candidate for candidate in candidates if candidate.lower() not in failed_name_keys]

    if not candidates and failed_names:
        metadata["status"] = "negative_cache_hit"
        return None, metadata

    for candidate in candidates:
        metadata["attempted_names"].append(candidate)
        provider_team_id = resolver(candidate)
        if provider_team_id in (None, ""):
            continue

        provider_id_str = str(provider_team_id)
        metadata["status"] = "resolved"
        metadata["provider_team_name"] = candidate

        if team is not None and sport_obj is not None:
            try:
                with get_db() as conn:
                    TeamSourceAliasRepo(conn).upsert_alias(
                        team_id=team.id,
                        sport_id=sport_obj.id,
                        source=source,
                        provider_team_name=candidate,
                        provider_team_id=provider_id_str,
                        provider_competition_hint=competition,
                        confidence=1.0,
                        status="verified",
                    )
            except Exception as exc:
                metadata["cache_error"] = f"persist:{exc}"
                logger.warning("Provider identity cache persist failed for %s/%s: %s", source, team_name, exc)

        return provider_id_str, metadata

    if team is not None and sport_obj is not None and metadata["attempted_names"]:
        try:
            with get_db() as conn:
                alias_repo = TeamSourceAliasRepo(conn)
                for candidate in metadata["attempted_names"]:
                    alias_repo.upsert_alias(
                        team_id=team.id,
                        sport_id=sport_obj.id,
                        source=source,
                        provider_team_name=candidate,
                        provider_team_id=None,
                        provider_competition_hint=competition,
                        confidence=0.0,
                        status="failed",
                    )
        except Exception as exc:
            metadata["cache_error"] = f"negative_cache:{exc}"
            logger.warning("Provider identity negative cache persist failed for %s/%s: %s", source, team_name, exc)

    return None, metadata


def remember_provider_team_alias(
    *,
    team_name: str,
    sport: str,
    source: str,
    provider_team_name: str,
    provider_slug: str = "",
    competition: str = "",
    confidence: float = 0.9,
) -> bool:
    try:
        with get_db() as conn:
            sport_obj = SportRepo(conn).get_by_name((sport or "").lower())
            if sport_obj is None:
                return False
            team = TeamRepo(conn).resolve(team_name, sport_obj.id)
            if team is None:
                return False
            TeamSourceAliasRepo(conn).upsert_alias(
                team_id=team.id,
                sport_id=sport_obj.id,
                source=source,
                provider_team_name=provider_team_name,
                provider_team_id=None,
                provider_slug=provider_slug,
                provider_competition_hint=competition,
                confidence=confidence,
                status="candidate",
            )
            return True
    except Exception as exc:
        logger.warning("Provider alias remember failed for %s/%s: %s", source, team_name, exc)
        return False
