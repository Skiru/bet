"""Pure parsers for the brittle tipster sources.

Lives under bet.tipsters, not bet.pipeline: the live TIPSTERS step must not
import the legacy S0-S10 package, whose __init__ validates a manifest that
references agent files deleted in b49258b4. That import chain is what took the
step down every run from 2026-08-31 onward.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Mapping, Sequence


DISCIPLINE_MAP = {
    "piłka nożna": "football",
    "tenis": "tennis",
    "koszykówka": "basketball",
    "siatkówka": "volleyball",
    "hokej": "hockey",
    "piłka ręczna": "handball",
    "baseball": "baseball",
    "mma": "mma",
    "esport": "esport",
    "boks": "boxing",
}


def strip_html_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", text).strip()


def extract_zawodtyper_bets_payload(body: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if not isinstance(body, Mapping) or not body.get("success"):
        return []
    data = body.get("data")
    if not isinstance(data, list) or not data:
        return []
    if not isinstance(data[0], Mapping):
        return []
    if "comment_id" not in data[0] or "match_name" not in data[0]:
        return []
    return [item for item in data if isinstance(item, Mapping)]


def _json_flag(raw: Any) -> bool:
    """Truthiness for a JSON field that may arrive as a string.

    ZawodTyper sends ``settled`` and ``is_betbuilder`` as ``"0"`` / ``"1"``, and
    ``bool("0")`` is True in Python, so a plain ``bool()`` marks every bet on
    the page as already settled. Verified against the live 2026-08-25 payload:
    74 of 74 bets carried ``settled="0"``.
    """
    if raw is None or isinstance(raw, bool):
        return bool(raw)
    if isinstance(raw, (int, float)):
        return raw != 0
    return str(raw).strip().lower() not in {"", "0", "false", "no", "null", "none"}


def _normalize_match_date(raw: Any) -> str | None:
    """Return ZawodTyper's ``match_date`` as ``YYYY-MM-DD``, or None.

    The field arrives as ``YYYY-MM-DD``, ``DD.MM.YYYY`` or ``DD-MM-YYYY``
    depending on which template rendered the bet. Anything else is dropped
    rather than guessed: a wrong date silently attributes yesterday's pick to
    today's fixture, which is the one failure mode a date field exists to stop.
    """
    text = str(raw or "").strip()
    if not text:
        return None
    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if iso:
        return f"{iso.group(1)}-{iso.group(2)}-{iso.group(3)}"
    dotted = re.match(r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", text)
    if dotted:
        return f"{dotted.group(3)}-{int(dotted.group(2)):02d}-{int(dotted.group(1)):02d}"
    return None


def parse_zawodtyper_xhr_bets(
    bets_data: Sequence[Mapping[str, Any]],
    *,
    now_iso: str,
    classify_market: Callable[[str, str], str],
    extract_direction: Callable[[str, str], str],
    extract_stats_cited: Callable[[str], list[str]],
    text_cleaner: Callable[[str], str] = strip_html_text,
) -> list[dict[str, Any]]:
    """One pick per published bet, deduplicated by ``comment_id``.

    This used to collapse to one pick per *match*, keeping whichever bet had the
    longest reasoning. That is defensible for a narrative evidence row and fatal
    for a consensus count: the whole claim the tipster column makes is "N of M
    tipsters point the same way", and collapsing five tipsters on Liverpool -
    Arsenal into one pick makes M equal 1 for every match on the page. The 92
    live items observed on 2026-08-25 came out as 51 picks for exactly this
    reason, with the disagreements thrown away rather than counted.

    ``comment_id`` is ZawodTyper's own per-bet primary key, so deduplicating on
    it removes genuine transport-level repeats (the offset pagination overlaps)
    without touching distinct opinions on the same fixture.
    """
    picks: list[dict[str, Any]] = []
    seen_comment_ids: set[str] = set()

    for bet in bets_data:
        if bet.get("comment_type") != "bet":
            continue
        match_name = str(bet.get("match_name") or "").strip()
        if not match_name:
            continue

        comment_id = str(bet.get("comment_id") or "").strip()
        if comment_id:
            if comment_id in seen_comment_ids:
                continue
            seen_comment_ids.add(comment_id)

        parts = re.split(r"\s*[-–—]\s*", match_name, maxsplit=1)
        if len(parts) != 2:
            parts = re.split(r"\s+vs\.?\s+", match_name, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) != 2:
            continue

        home = parts[0].strip()
        away = parts[1].strip()
        if len(home) < 2 or len(away) < 2:
            continue

        content = text_cleaner(str(bet.get("content") or ""))
        author_stats = bet.get("author_stats") or {}
        bet_count = int(author_stats.get("bet_count", 0) or 0)
        ratio_raw = author_stats.get("ratio")
        ratio = float(ratio_raw) if ratio_raw else 0.0
        accuracy = int(ratio * 100) if ratio > 0 and bet_count >= 3 else None

        author_name = str(bet.get("author_name") or "ZawodTyper")
        reasoning_parts: list[str] = []
        if accuracy and bet_count >= 3:
            reasoning_parts.append(f"Tipster {author_name}: {accuracy}% ({bet_count} bets)")
        if content and len(content) > 30:
            reasoning_parts.append(content)
        reasoning = " | ".join(reasoning_parts) if reasoning_parts else ""

        pick_type = str(bet.get("type") or "").strip()
        sport = DISCIPLINE_MAP.get(str(bet.get("discipline") or "").lower().strip(), "football")
        odds_raw = bet.get("rate")
        try:
            odds = float(odds_raw) if odds_raw is not None else None
        except (TypeError, ValueError):
            odds = None

        # ``is_betbuilder`` and ``settled`` were both already in the payload and
        # both discarded. A bet builder is a parlay whose legs cannot be counted
        # as single-market opinions, and a settled bet is a past claim that must
        # never be presented as a read on an upcoming fixture.
        picks.append(
            {
                "source_site": "ZawodTyper",
                "source_id": "zawodtyper",
                "tipster_name": author_name,
                "sport": sport,
                "event": f"{home} vs {away}",
                "home_team": home,
                "away_team": away,
                "competition": "",
                "market": pick_type or "N/A",
                "market_type": classify_market(pick_type, content),
                "direction": extract_direction(pick_type, content),
                "odds": odds,
                "reasoning": reasoning[:800],
                "accuracy_pct": accuracy,
                "tipster_bet_count": bet_count,
                "confidence": "high"
                if accuracy and accuracy >= 65 and bet_count >= 10
                else ("medium" if accuracy and accuracy >= 55 and bet_count >= 5 else "low"),
                "stats_cited": extract_stats_cited(content),
                "fetch_time": now_iso,
                "match_date": _normalize_match_date(bet.get("match_date")),
                "kickoff_time": str(bet.get("hour") or "").strip() or None,
                "is_combo_source_flag": _json_flag(bet.get("is_betbuilder")),
                "is_settled": _json_flag(bet.get("settled")),
                "source_url": str(bet.get("link") or "").strip() or None,
                "source_comment_id": comment_id or None,
            }
        )

    return picks
