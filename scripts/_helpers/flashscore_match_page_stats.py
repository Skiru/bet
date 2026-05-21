#!/usr/bin/env python3
"""Shared Flashscore match-page stats extraction helpers.

This module extracts the public Flashscore search/results-page fallback and
match-statistics HTML parsing flow so settlement and enrichment can share the
same implementation.
"""

from __future__ import annotations

import re
import time
import unicodedata
from urllib.parse import quote

try:
    from flashscore_enricher import (
        _FS_HEADERS as _FLASHSCORE_RESULTS_HEADERS,
        _FS_IMPERSONATE as _FLASHSCORE_IMPERSONATE,
        _get_flashscore_entity,
    )
except ImportError:  # pragma: no cover - guarded in call sites/tests
    _FLASHSCORE_RESULTS_HEADERS = {}
    _FLASHSCORE_IMPERSONATE = "chrome110"

    def _get_flashscore_entity(team_name: str, sport: str):
        return None, None, None


FLASHSCORE_SEARCH_HEADERS = {
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}
FLASHSCORE_SPORT_IDS = {
    "football": 1,
    "tennis": 2,
    "basketball": 3,
    "hockey": 4,
    "volleyball": 12,
}
FLASHSCORE_FOOTBALL_STAT_KEYS = (
    "corners",
    "yellow_cards",
    "red_cards",
    "shots",
    "shots_on_target",
    "fouls",
    "possession",
)


def normalize_flashscore_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def extract_flashscore_match_id_from_url(url: str) -> str | None:
    if not url:
        return None

    match = re.search(r"/match/([^/#?]+)/", url)
    if match:
        return match.group(1)

    match = re.search(r"-([A-Za-z0-9]{8})(?:/|[#?]|$)", url)
    if match:
        return match.group(1)

    return None


def result_type_name(result: dict) -> str:
    result_type = result.get("type")
    if isinstance(result_type, dict):
        for key in ("name", "value", "label"):
            value = result_type.get(key)
            if isinstance(value, str) and value:
                return value.lower()
        return ""

    if isinstance(result_type, str):
        return result_type.lower()

    return ""


def result_matches_flashscore_participants(result: dict, home: str, away: str) -> bool:
    home_norm = normalize_flashscore_text(home)
    away_norm = normalize_flashscore_text(away)
    if not home_norm or not away_norm:
        return True

    search_parts: list[str] = []
    for key in ("name", "title", "text", "url", "homeName", "awayName"):
        value = result.get(key)
        if isinstance(value, str) and value:
            search_parts.append(value)

    participants = result.get("participants")
    if isinstance(participants, list):
        for participant in participants:
            if isinstance(participant, str) and participant:
                search_parts.append(participant)
                continue
            if not isinstance(participant, dict):
                continue
            for key in ("name", "participantName"):
                value = participant.get(key)
                if isinstance(value, str) and value:
                    search_parts.append(value)

    haystack = " ".join(normalize_flashscore_text(part) for part in search_parts if part)
    return home_norm in haystack and away_norm in haystack


def select_flashscore_match_id(results: list[dict], home: str, away: str) -> str | None:
    fallback_match_id = None

    for result in results:
        if not isinstance(result, dict):
            continue

        url = str(result.get("url") or "")
        type_name = result_type_name(result)
        is_event_like = type_name in {"event", "match", "fixture", "game"}
        if not is_event_like and "/match/" not in url and not isinstance(result.get("participants"), list):
            continue

        match_id = extract_flashscore_match_id_from_url(url)
        if not match_id:
            result_id = result.get("id")
            if isinstance(result_id, str) and result_id.strip():
                match_id = result_id.strip()
        if not match_id:
            continue

        if result_matches_flashscore_participants(result, home, away):
            return match_id

        if fallback_match_id is None:
            fallback_match_id = match_id

    return fallback_match_id


def select_flashscore_match_id_from_results_page(
    html: str,
    home: str,
    away: str,
    team_entity_id: str | None = None,
) -> str | None:
    if "~AA÷" not in html:
        return None

    for match_block in html.split("~AA÷")[1:]:
        event_id, separator, remainder = match_block.partition("¬")
        if not separator or not event_id:
            continue

        fields = {"AA": event_id.strip()}
        for field in remainder.split("¬"):
            if "÷" not in field:
                continue
            key, _, value = field.partition("÷")
            fields[key] = value

        if team_entity_id and team_entity_id not in {fields.get("PX"), fields.get("PY")}:
            continue

        if fields.get("AB") and fields.get("AB") != "3":
            continue

        candidate = {
            "name": f"{fields.get('AE', '')} - {fields.get('AF', '')}",
            "homeName": fields.get("AE") or fields.get("FH") or fields.get("WM"),
            "awayName": fields.get("AF") or fields.get("FK") or fields.get("WN"),
            "participants": [
                value
                for key in ("AE", "AF", "FH", "FK", "WM", "WN", "WU", "WV")
                if (value := fields.get(key))
            ],
        }
        if result_matches_flashscore_participants(candidate, home, away):
            return fields["AA"]

    return None


def _is_html_blocked(status_code: int, body: str | None) -> bool:
    text = (body or "").lower()
    if status_code in {401, 403, 429, 503}:
        return True
    return len(body or "") < 500 or "just a moment" in text or "access denied" in text or "captcha" in text


def find_flashscore_match_id_via_results_page(
    home: str,
    away: str,
    sport: str,
    c_requests,
    *,
    sleep_seconds: float = 1.5,
    max_requests: int | None = None,
) -> dict:
    requests_used = 0
    blocked = False

    for team_name in (home, away):
        if max_requests is not None and requests_used >= max_requests:
            return {
                "status": "failed",
                "match_id": None,
                "requests_used": requests_used,
                "failure_reason": "request_budget_exhausted",
                "error": None,
            }

        entity_type, slug, entity_id = _get_flashscore_entity(team_name, sport)
        if not entity_type or not slug or not entity_id:
            continue

        results_url = f"https://www.flashscore.com/{entity_type}/{slug}/{entity_id}/results/"
        if sleep_seconds:
            time.sleep(sleep_seconds)

        try:
            resp = c_requests.get(
                results_url,
                headers=_FLASHSCORE_RESULTS_HEADERS,
                impersonate=_FLASHSCORE_IMPERSONATE,
                timeout=15,
            )
            requests_used += 1
        except Exception as exc:
            return {
                "status": "failed",
                "match_id": None,
                "requests_used": requests_used,
                "failure_reason": "html_blocked",
                "error": str(exc),
            }

        if resp.status_code != 200 or _is_html_blocked(resp.status_code, resp.text):
            blocked = True
            continue

        match_id = select_flashscore_match_id_from_results_page(
            resp.text,
            home,
            away,
            team_entity_id=entity_id,
        )
        if match_id:
            return {
                "status": "ok",
                "match_id": match_id,
                "requests_used": requests_used,
                "failure_reason": None,
                "error": None,
            }

    return {
        "status": "failed",
        "match_id": None,
        "requests_used": requests_used,
        "failure_reason": "html_blocked" if blocked else "match_not_found",
        "error": None,
    }


def resolve_flashscore_match_id(
    home: str,
    away: str,
    sport: str = "football",
    *,
    c_requests=None,
    sleep_seconds: float = 1.5,
    max_requests: int | None = None,
    headers: dict | None = None,
) -> dict:
    result = {
        "status": "failed",
        "match_id": None,
        "requests_used": 0,
        "failure_reason": None,
        "error": None,
    }

    if c_requests is None:
        try:
            from curl_cffi import requests as c_requests  # type: ignore[no-redef]
        except ImportError as exc:
            result["failure_reason"] = "dependency_missing"
            result["error"] = str(exc)
            return result

    sport_id = FLASHSCORE_SPORT_IDS.get(sport)
    if sport_id is None:
        result["failure_reason"] = "unsupported_sport"
        return result

    search_q = f"{home} {away}"
    search_url = (
        "https://s.livesport.services/api/v2/search/"
        f"?q={quote(search_q)}&lang=en&sport={sport_id}&category="
    )

    blocked = False
    if max_requests is None or result["requests_used"] < max_requests:
        try:
            resp = c_requests.get(search_url, headers=headers or FLASHSCORE_SEARCH_HEADERS, impersonate="chrome110", timeout=10)
            result["requests_used"] += 1
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    results = data.get("results", [])
                elif isinstance(data, list):
                    results = data
                else:
                    results = []
                match_id = select_flashscore_match_id(results, home, away) if results else None
                if match_id:
                    result.update({"status": "ok", "match_id": match_id})
                    return result
            else:
                blocked = True
        except Exception as exc:
            result["error"] = str(exc)
            blocked = True
    else:
        result["failure_reason"] = "request_budget_exhausted"
        return result

    fallback = find_flashscore_match_id_via_results_page(
        home,
        away,
        sport,
        c_requests,
        sleep_seconds=sleep_seconds,
        max_requests=None if max_requests is None else max_requests - result["requests_used"],
    )
    result["requests_used"] += fallback.get("requests_used", 0)
    if fallback.get("match_id"):
        result.update({"status": "ok", "match_id": fallback["match_id"], "failure_reason": None})
        return result

    result["failure_reason"] = fallback.get("failure_reason") or ("html_blocked" if blocked else "match_not_found")
    if fallback.get("error") and not result.get("error"):
        result["error"] = fallback["error"]
    return result


def parse_flashscore_match_stats_html(html: str) -> dict | None:
    stats = {}
    stat_patterns = {
        "corners": r"(\d+)\s*(?:Corner Kicks?|Corners?)\s*(\d+)",
        "yellow_cards": r"(\d+)\s*(?:Yellow Cards?|Żółte kartki)\s*(\d+)",
        "red_cards": r"(\d+)\s*(?:Red Cards?|Czerwone kartki)\s*(\d+)",
        "shots_on_target": r"(\d+)\s*(?:Shots on Target|Strzały celne)\s*(\d+)",
        "shots": r"(\d+)\s*(?:Total Shots|Shots|Strzały)\s*(\d+)",
        "fouls": r"(\d+)\s*(?:Fouls?|Faule)\s*(\d+)",
        "possession": r"(\d+)\s*%?\s*(?:Ball Possession|Possession|Posiadanie piłki)\s*(\d+)\s*%?",
    }

    for key, pattern in stat_patterns.items():
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            stats[key] = {"home": int(match.group(1)), "away": int(match.group(2))}

    return stats if stats else None


def fetch_flashscore_match_page_stats(
    home: str,
    away: str,
    sport: str = "football",
    *,
    c_requests=None,
    sleep_seconds: float = 1.5,
    max_requests: int | None = None,
    headers: dict | None = None,
) -> dict:
    result = {
        "source": "flashscore-html",
        "sport": sport,
        "home_team": home,
        "away_team": away,
        "status": "failed",
        "match_id": None,
        "stats": None,
        "rich_keys_found": [],
        "failure_reason": None,
        "error": None,
        "requests_used": 0,
    }

    if c_requests is None:
        try:
            from curl_cffi import requests as c_requests  # type: ignore[no-redef]
        except ImportError as exc:
            result["failure_reason"] = "dependency_missing"
            result["error"] = str(exc)
            return result

    match_result = resolve_flashscore_match_id(
        home,
        away,
        sport,
        c_requests=c_requests,
        sleep_seconds=sleep_seconds,
        max_requests=max_requests,
        headers=headers,
    )
    result["requests_used"] = match_result.get("requests_used", 0)
    result["match_id"] = match_result.get("match_id")
    if not match_result.get("match_id"):
        result["failure_reason"] = match_result.get("failure_reason") or "match_not_found"
        result["error"] = match_result.get("error")
        return result

    if max_requests is not None and result["requests_used"] >= max_requests:
        result["failure_reason"] = "request_budget_exhausted"
        return result

    if sleep_seconds:
        time.sleep(sleep_seconds)
    stats_url = f"https://www.flashscore.com/match/{result['match_id']}/#/match-summary/match-statistics/0"
    try:
        resp = c_requests.get(
            stats_url,
            headers=headers or FLASHSCORE_SEARCH_HEADERS,
            impersonate="chrome110",
            timeout=15,
        )
        result["requests_used"] += 1
    except Exception as exc:
        result["failure_reason"] = "html_blocked"
        result["error"] = str(exc)
        return result

    if resp.status_code != 200 or _is_html_blocked(resp.status_code, resp.text):
        result["failure_reason"] = "html_blocked"
        return result

    stats = parse_flashscore_match_stats_html(resp.text)
    if not stats:
        result["failure_reason"] = "stats_missing"
        return result

    result.update(
        {
            "status": "ok",
            "stats": stats,
            "rich_keys_found": [key for key in FLASHSCORE_FOOTBALL_STAT_KEYS if key in stats],
            "failure_reason": None,
            "error": None,
        }
    )
    return result


__all__ = [
    "FLASHSCORE_FOOTBALL_STAT_KEYS",
    "extract_flashscore_match_id_from_url",
    "fetch_flashscore_match_page_stats",
    "find_flashscore_match_id_via_results_page",
    "normalize_flashscore_text",
    "parse_flashscore_match_stats_html",
    "resolve_flashscore_match_id",
    "result_matches_flashscore_participants",
    "result_type_name",
    "select_flashscore_match_id",
    "select_flashscore_match_id_from_results_page",
]