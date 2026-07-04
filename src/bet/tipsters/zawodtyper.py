"""Safe, direct public-only, compliance-first ZawodTyper transport and parser."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from .contracts import ExtractionResult, ExtractorVerdict, RawDocument, TipsterPick
from .legacy_bridge import convert_legacy_pick_to_v2
from .market_parser import market_family, direction, stats_cited, extract_odds
from .normalization import collapse_ws, clean_team_name, is_garbage_team
from bet.pipeline.tipster_parsers import extract_zawodtyper_bets_payload, parse_zawodtyper_xhr_bets

POLISH_MONTHS = {
    1: "stycznia", 2: "lutego", 3: "marca", 4: "kwietnia",
    5: "maja", 6: "czerwca", 7: "lipca", 8: "sierpnia",
    9: "wrzesnia", 10: "pazdziernika", 11: "listopada", 12: "grudnia",
}

POLISH_WEEKDAYS = {
    0: "poniedzialek", 1: "wtorek", 2: "sroda", 3: "czwartek",
    4: "piatek", 5: "sobota", 6: "niedziela",
}


def build_zawodtyper_daily_url(date: datetime) -> str:
    """Build ZawodTyper daily URL with Polish month/weekday names."""
    day = date.day
    month = POLISH_MONTHS.get(date.month, "")
    weekday = POLISH_WEEKDAYS.get(date.weekday(), "")
    return f"https://www.zawodtyper.pl/typy-dnia-{day}-{month}-{weekday}/"


def extract_zawodtyper(doc: RawDocument, review_data: dict[str, Any] | None = None) -> ExtractionResult:
    """Deterministic extractor for ZawodTyper.

    If the document HTML is a JSON payload from public XHR (e.g. NP_ajax.php),
    we parse it cleanly. Otherwise we parse the static HTML for any embedded
    cards, or emit NEEDS_PUBLIC_XHR_REVIEW if the page is just an empty SPA shell.
    """
    html_stripped = doc.html.strip()
    is_json = False
    if html_stripped.startswith("{") or html_stripped.startswith("["):
        is_json = True

    warnings: list[str] = []
    picks: list[TipsterPick] = []

    if is_json:
        try:
            payload = json.loads(html_stripped)
            bets = extract_zawodtyper_bets_payload(payload)
            if not bets:
                return ExtractionResult(
                    source_id="zawodtyper",
                    url=doc.url,
                    verdict=ExtractorVerdict.EMPTY,
                    picks=[],
                    warnings=["empty_or_invalid_xhr_payload"],
                    parser_version="tipster_parser_v2.3_final_source_specific",
                )

            classify_market_v2 = lambda m, c: market_family(m + " " + c)
            extract_direction_v2 = lambda m, c: direction(m + " " + c)

            raw_picks = parse_zawodtyper_xhr_bets(
                bets,
                now_iso=doc.fetched_at_utc,
                classify_market=classify_market_v2,
                extract_direction=extract_direction_v2,
                extract_stats_cited=stats_cited,
            )

            for p in raw_picks:
                picks.append(convert_legacy_pick_to_v2(p))

            verdict = ExtractorVerdict.OK if picks else ExtractorVerdict.EMPTY
            return ExtractionResult(
                source_id="zawodtyper",
                url=doc.url,
                verdict=verdict,
                picks=picks,
                warnings=warnings,
                parser_version="tipster_parser_v2.3_final_source_specific",
            )
        except Exception as exc:
            return ExtractionResult(
                source_id="zawodtyper",
                url=doc.url,
                verdict=ExtractorVerdict.PARSE_ERROR,
                picks=[],
                warnings=[f"xhr_parse_failed:{str(exc)}"],
                parser_version="tipster_parser_v2.3_final_source_specific",
            )

    else:
        # Method 1: Structural parsing via match-name/type ID pairs
        match_ids = re.findall(r'id="match-name(\d+)"', doc.html)
        seen_events: set[str] = set()

        for mid in match_ids:
            # Robust tag-boundary extraction for match_text
            start_match = doc.html.find(f'id="match-name{mid}"')
            if start_match == -1:
                continue
            tag_end = doc.html.find('>', start_match)
            if tag_end == -1:
                continue
            end_match = doc.html.find('</div>', tag_end)
            if end_match == -1:
                continue
            match_text = doc.html[tag_end+1:end_match].strip()
            match_text = re.sub(r'<[^>]+>', '', match_text).strip()
            if not match_text:
                continue

            # Robust tag-boundary extraction for type_text
            start_type = doc.html.find(f'id="type{mid}"')
            type_text = ""
            if start_type != -1:
                tag_end_type = doc.html.find('>', start_type)
                if tag_end_type != -1:
                    end_type = doc.html.find('</div>', tag_end_type)
                    if end_type != -1:
                        type_text = doc.html[tag_end_type+1:end_type].strip()
                        type_text = re.sub(r'<[^>]+>', '', type_text).strip()

            event_match = re.search(r'(.+?)\s*[-–—]\s*(.+)', match_text)
            if not event_match:
                event_match = re.search(r'(.+?)\s+vs\.?\s+(.+)', match_text, re.IGNORECASE)
            if not event_match:
                continue

            home = clean_team_name(event_match.group(1).strip())
            away = clean_team_name(event_match.group(2).strip())

            if is_garbage_team(home) or is_garbage_team(away) or home.lower() == away.lower():
                continue

            event_key = f"{home.lower()}|{away.lower()}|{type_text.lower()}"
            if event_key in seen_events:
                continue
            seen_events.add(event_key)

            block_start = doc.html.find(f'id="match-name{mid}"')
            block_end = min(len(doc.html), block_start + 3000)
            block = doc.html[block_start:block_end]
            block_text = re.sub(r'<[^>]+>', ' ', block)

            market = type_text if type_text else "N/A"
            if market in ("1", "2", "X", "1X", "X2", "12"):
                market = f"Winner: {market}"

            odds = extract_odds(block_text)
            acc_m = re.search(r'(?:skuteczność|skutecznosc|accuracy|ratio)[:\s]*(\d+)\s*%', block_text, re.I)
            accuracy = int(acc_m.group(1)) if acc_m else None

            sport = "football"
            low_text = (match_text + " " + type_text).lower()
            sport_hints = {
                "tennis": ("tennis", "tenis", "atp", "wta"),
                "basketball": ("basketball", "koszykówka", "koszykowka", "nba"),
                "volleyball": ("volleyball", "siatkówka", "siatkowka"),
                "hockey": ("hockey", "hokej", "nhl"),
            }
            for sp, hints in sport_hints.items():
                if any(h in low_text for h in hints):
                    sport = sp
                    break

            reasoning_parts = []
            if accuracy:
                reasoning_parts.append(f"Tipster accuracy: {accuracy}% (tracked)")
            if type_text and type_text != market:
                reasoning_parts.append(f"Pick: {type_text}")

            analysis_match = re.search(
                r'(?:argument|uzasadnienie|dlaczego|opis|komentarz)[:\s]*(.+?)(?:\n|$)',
                block_text, re.IGNORECASE
            )
            if analysis_match:
                reasoning_parts.append(analysis_match.group(1).strip()[:300])
            reasoning = " | ".join(reasoning_parts) if reasoning_parts else type_text[:200]

            legacy_pick = {
                "source_site": "ZawodTyper",
                "source_id": "zawodtyper",
                "tipster_name": "ZawodTyper",
                "sport": sport,
                "event": f"{home} vs {away}",
                "home_team": home,
                "away_team": away,
                "market": market,
                "odds": odds,
                "reasoning": reasoning,
                "accuracy_pct": accuracy,
                "stats_cited": stats_cited(block_text),
                "fetch_time": doc.fetched_at_utc,
            }
            picks.append(convert_legacy_pick_to_v2(legacy_pick))

        if not picks:
            # Method 2: Fallback to text-based parsing
            text = re.sub(r'<(?:br|hr|/p|/div|/li|/tr)[^>]*>', '\n', doc.html, flags=re.IGNORECASE)
            text = re.sub(r'<[^>]+>', '\n', text)
            text = re.sub(r'\n{3,}', '\n\n', text)

            blocks = re.split(r'(?=(?:Typ dnia|Typer:|Mecz:|Mój typ))', text)
            for block in blocks[:100]:
                if len(block) < 30:
                    continue

                event_match = re.search(
                    r'([A-ZÀ-Ž][A-Za-zÀ-ž\.\s]{2,30}?)\s*[-–—]\s*([A-ZÀ-Ž][A-Za-zÀ-ž\.\s]{2,30})',
                    block
                )
                if not event_match:
                    continue

                home = clean_team_name(event_match.group(1).strip())
                away = clean_team_name(event_match.group(2).strip())

                if is_garbage_team(home) or is_garbage_team(away) or home.lower() == away.lower():
                    continue

                event_key = f"{home.lower()}|{away.lower()}"
                if event_key in seen_events:
                    continue
                seen_events.add(event_key)

                tipster_match = re.search(r'(?:Typer|Tipster|Autor):\s*(\S+)', block, re.IGNORECASE)
                tipster_name = tipster_match.group(1) if tipster_match else "ZawodTyper"

                pick_match = re.search(
                    r'(?:Typ|Pick|Zakład|Mój typ)[:\s]+(.+?)(?:\n|$)',
                    block, re.IGNORECASE
                )
                market = pick_match.group(1).strip() if pick_match else "N/A"

                odds = extract_odds(block)
                acc_m = re.search(r'(?:skuteczność|skutecznosc|accuracy|ratio)[:\s]*(\d+)\s*%', block, re.I)
                accuracy = int(acc_m.group(1)) if acc_m else None

                sport = "football"
                low_block = block.lower()
                sport_hints = {
                    "tennis": ("tennis", "tenis", "atp", "wta"),
                    "basketball": ("basketball", "koszykówka", "koszykowka", "nba"),
                    "volleyball": ("volleyball", "siatkówka", "siatkowka"),
                    "hockey": ("hockey", "hokej", "nhl"),
                }
                for sp, hints in sport_hints.items():
                    if any(h in low_block for h in hints):
                        sport = sp
                        break

                reasoning_match = re.search(
                    r'(?:Argument|Uzasadnienie|Dlaczego|Reasoning|spodziew)[:\s]*(.+?)(?:\n\n|$)',
                    block, re.IGNORECASE | re.DOTALL
                )
                reasoning = reasoning_match.group(1).strip()[:500] if reasoning_match else ""

                legacy_pick = {
                    "source_site": "ZawodTyper",
                    "source_id": "zawodtyper",
                    "tipster_name": tipster_name,
                    "sport": sport,
                    "event": f"{home} vs {away}",
                    "home_team": home,
                    "away_team": away,
                    "market": market,
                    "odds": odds,
                    "reasoning": reasoning,
                    "accuracy_pct": accuracy,
                    "stats_cited": stats_cited(block),
                    "fetch_time": doc.fetched_at_utc,
                }
                picks.append(convert_legacy_pick_to_v2(legacy_pick))

        if not picks:
            warnings.append("NEEDS_PUBLIC_XHR_REVIEW")
            return ExtractionResult(
                source_id="zawodtyper",
                url=doc.url,
                verdict=ExtractorVerdict.EMPTY,
                picks=[],
                warnings=warnings,
                parser_version="tipster_parser_v2.3_final_source_specific",
                fallback="needs_public_xhr_review",
            )

        return ExtractionResult(
            source_id="zawodtyper",
            url=doc.url,
            verdict=ExtractorVerdict.OK,
            picks=picks,
            warnings=warnings,
            parser_version="tipster_parser_v2.3_final_source_specific",
        )
