"""Safe, direct public-only, compliance-first ZawodTyper transport and parser."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from .contracts import ExtractionResult, ExtractorVerdict, RawDocument, TipsterPick
from .legacy_bridge import convert_legacy_pick_to_v2
from .market_parser import market_family, direction, stats_cited, extract_odds
from .normalization import collapse_ws, clean_team_name, is_garbage_team
from bet.tipsters.parsers import extract_zawodtyper_bets_payload, parse_zawodtyper_xhr_bets

POLISH_MONTHS = {
    1: "stycznia", 2: "lutego", 3: "marca", 4: "kwietnia",
    5: "maja", 6: "czerwca", 7: "lipca", 8: "sierpnia",
    9: "wrzesnia", 10: "pazdziernika", 11: "listopada", 12: "grudnia",
}

POLISH_WEEKDAYS = {
    0: "poniedzialek", 1: "wtorek", 2: "sroda", 3: "czwartek",
    4: "piatek", 5: "sobota", 6: "niedziela",
}

ZAWODTYPER_PUBLIC_XHR_ENDPOINT_PATH = "/wp-content/NP_ajax.php"
ZAWODTYPER_PUBLIC_XHR_ENDPOINT_URL = f"https://zawodtyper.pl{ZAWODTYPER_PUBLIC_XHR_ENDPOINT_PATH}"
ZAWODTYPER_COOKIE_POLICY_NO_COOKIE = "no_cookie"
ZAWODTYPER_COOKIE_POLICY_TECHNICAL = "technical_first_party_only"
ZAWODTYPER_COOKIE_POLICY_ANALYTICS = "ephemeral_first_party_public_analytics_allowed"
ZAWODTYPER_ALLOWED_COOKIE_POLICIES = (
    ZAWODTYPER_COOKIE_POLICY_NO_COOKIE,
    ZAWODTYPER_COOKIE_POLICY_TECHNICAL,
    ZAWODTYPER_COOKIE_POLICY_ANALYTICS,
)
ZAWODTYPER_ALLOWED_TECHNICAL_COOKIES = {"SRV"}


def classify_zawodtyper_cookie_name(name: str) -> str:
    low = name.strip().lower()
    if not low:
        return "UNKNOWN"
    if name == "SRV" or low.startswith(("litespeed", "guest", "vary")) or "cache" in low or "consent" in low:
        return "ALLOWED_TECHNICAL"
    if name == "_ga" or name.startswith("_ga_"):
        return "ALLOWED_ANALYTICS_EPHEMERAL"
    blocked_tokens = (
        "wordpress_logged_in",
        "wp-settings",
        "wp_sec",
        "phpsessid",
        "session",
        "sess",
        "auth",
        "login",
        "user",
        "token",
        "jwt",
        "bearer",
        "nonce",
        "csrf",
    )
    if any(token in low for token in blocked_tokens):
        return "BLOCKED"
    return "UNKNOWN"


def extract_zawodtyper_post_id(html: str) -> int | None:
    for pattern in (r"\bpostid-(\d+)\b", r'"id":(\d+),"categories"'):
        match = re.search(pattern, html)
        if match:
            return int(match.group(1))
    return None


def build_zawodtyper_xhr_payloads(post_id: int, max_pages_per_source: int) -> list[dict[str, int | str]]:
    xhr_budget = max(0, max_pages_per_source - 1)
    payloads: list[dict[str, int | str]] = []
    if xhr_budget >= 1:
        payloads.append({"endpoint": "api_get_bets_by_post_id", "post_id": post_id, "offset": 0, "count": 5})
    if xhr_budget >= 2:
        payloads.append({"endpoint": "api_get_bets_by_post_id", "post_id": post_id, "offset": 5, "count": 505})
    return payloads


def select_zawodtyper_cookie_policy(variants: list[dict[str, Any]]) -> str | None:
    order = (
        "no_cookie",
        "technical_only",
        "technical_plus_analytics_ephemeral",
    )
    for name in order:
        for variant in variants:
            if variant.get("variant") != name:
                continue
            if variant.get("status") == 200 and variant.get("is_json") and variant.get("item_count", 0) > 0 and variant.get("parse_success"):
                return name
    return None


def build_zawodtyper_transport_warnings(meta: dict[str, Any]) -> list[str]:
    warnings = [f"public_xhr_transport:selected_cookie_policy={meta.get('cookie_policy', 'unknown')}"]
    cookie_names_sent = ",".join(sorted(str(name) for name in meta.get("cookie_names_sent", []))) or "none"
    warnings.append(f"public_xhr_transport:cookie_names_sent={cookie_names_sent}")
    observed_cookie_names = ",".join(sorted(str(name) for name in meta.get("observed_cookie_names", []))) or "none"
    warnings.append(f"public_xhr_transport:observed_cookie_names={observed_cookie_names}")
    warnings.append(f"public_xhr_transport:xhr_calls={meta.get('xhr_call_count', 0)}")
    warnings.append(f"public_xhr_transport:observed_items={meta.get('item_count', 0)}")
    return warnings


def _review_allowed_cookie_names(review_data: dict[str, Any] | None) -> list[str]:
    if not review_data:
        return []
    review = review_data.get("source_reviews", {}).get("zawodtyper", {})
    names = review.get("allowed_cookie_names", []) if isinstance(review, dict) else []
    if not isinstance(names, list):
        return []
    return sorted({str(name).strip() for name in names if str(name).strip()})


def _review_cookie_policy(review_data: dict[str, Any] | None) -> str:
    if not review_data:
        return ZAWODTYPER_COOKIE_POLICY_NO_COOKIE
    review = review_data.get("source_reviews", {}).get("zawodtyper", {})
    if not isinstance(review, dict):
        return ZAWODTYPER_COOKIE_POLICY_NO_COOKIE
    policy = str(review.get("cookie_policy") or ZAWODTYPER_COOKIE_POLICY_NO_COOKIE).strip()
    if policy not in ZAWODTYPER_ALLOWED_COOKIE_POLICIES:
        return ZAWODTYPER_COOKIE_POLICY_NO_COOKIE
    return policy


def _cookie_header_for_policy(cookies: list[Any], policy: str, allowed_cookie_names: set[str]) -> tuple[str | None, list[str]]:
    selected: list[tuple[str, str]] = []
    for cookie in cookies:
        name = str(cookie.name)
        if name not in allowed_cookie_names:
            continue
        classification = classify_zawodtyper_cookie_name(name)
        if policy == ZAWODTYPER_COOKIE_POLICY_TECHNICAL and classification != "ALLOWED_TECHNICAL":
            continue
        if policy == ZAWODTYPER_COOKIE_POLICY_ANALYTICS and classification not in {"ALLOWED_TECHNICAL", "ALLOWED_ANALYTICS_EPHEMERAL"}:
            continue
        if all(existing_name != name for existing_name, _ in selected):
            selected.append((name, str(cookie.value)))
    if policy == ZAWODTYPER_COOKIE_POLICY_NO_COOKIE:
        return None, []
    if not selected:
        return None, []
    return "; ".join(f"{name}={value}" for name, value in selected), [name for name, _ in selected]


def fetch_zawodtyper_public_xhr_document(
    page_url: str,
    *,
    review_data: dict[str, Any] | None,
    timeout_seconds: float,
    user_agent: str,
    max_pages_per_source: int,
) -> tuple[RawDocument | None, dict[str, Any]]:
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    page_request = Request(
        page_url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with opener.open(page_request, timeout=timeout_seconds) as response:
            html = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
            final_url = response.geturl()
    except HTTPError as exc:
        return None, {"reason": f"public_page_http_error:{exc.code}"}
    except URLError as exc:
        return None, {"reason": f"public_page_url_error:{exc.reason}"}
    except TimeoutError:
        return None, {"reason": "public_page_timeout"}

    observed_cookie_names = sorted({str(cookie.name) for cookie in jar if "zawodtyper.pl" in str(cookie.domain or "")})
    blocked_cookie_names = [name for name in observed_cookie_names if classify_zawodtyper_cookie_name(name) == "BLOCKED"]
    unknown_cookie_names = [name for name in observed_cookie_names if classify_zawodtyper_cookie_name(name) == "UNKNOWN"]
    allowed_cookie_names = _review_allowed_cookie_names(review_data) or [
        name for name in observed_cookie_names if classify_zawodtyper_cookie_name(name) in {"ALLOWED_TECHNICAL", "ALLOWED_ANALYTICS_EPHEMERAL"}
    ]
    if blocked_cookie_names:
        return None, {"reason": "blocked_cookie_names:" + ",".join(blocked_cookie_names)}
    if unknown_cookie_names:
        return None, {"reason": "unknown_cookie_names:" + ",".join(unknown_cookie_names)}
    disallowed_cookie_names = [name for name in observed_cookie_names if name not in set(allowed_cookie_names)]
    if disallowed_cookie_names:
        return None, {"reason": "unreviewed_cookie_names:" + ",".join(disallowed_cookie_names)}

    post_id = extract_zawodtyper_post_id(html)
    if post_id is None:
        return None, {"reason": "post_id_not_found_in_public_page"}

    payloads = build_zawodtyper_xhr_payloads(post_id, max_pages_per_source)
    if not payloads:
        return None, {"reason": "max_pages_per_source_too_low_for_public_xhr"}

    cookie_policy = _review_cookie_policy(review_data)
    cookie_header, cookie_names_sent = _cookie_header_for_policy(list(jar), cookie_policy, set(allowed_cookie_names))
    if cookie_policy != ZAWODTYPER_COOKIE_POLICY_NO_COOKIE and not cookie_names_sent:
        return None, {"reason": f"cookie_policy_unavailable_in_http_context:{cookie_policy}"}

    combined_items: list[dict[str, Any]] = []
    item_keys: set[str] = set()
    seen_comment_ids: set[str] = set()
    for payload in payloads:
        headers = {
            "User-Agent": user_agent,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://zawodtyper.pl",
            "Referer": page_url,
        }
        if cookie_header:
            headers["Cookie"] = cookie_header
        request = Request(
            ZAWODTYPER_PUBLIC_XHR_ENDPOINT_URL,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310: gated public same-origin transport
                final_xhr_url = response.geturl()
                if ZAWODTYPER_PUBLIC_XHR_ENDPOINT_PATH not in final_xhr_url or "zawodtyper.pl" not in final_xhr_url:
                    return None, {"reason": f"same_origin_xhr_required:{final_xhr_url}"}
                ctype = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
                if ctype != "application/json":
                    return None, {"reason": f"xhr_non_json_content_type:{ctype or 'empty'}"}
                payload_json = json.loads(response.read().decode("utf-8", errors="replace"))
        except HTTPError as exc:
            return None, {"reason": f"xhr_http_error:{exc.code}"}
        except URLError as exc:
            return None, {"reason": f"xhr_url_error:{exc.reason}"}
        except TimeoutError:
            return None, {"reason": "xhr_timeout"}
        except json.JSONDecodeError:
            return None, {"reason": "xhr_invalid_json"}

        bets = extract_zawodtyper_bets_payload(payload_json)
        if not bets:
            continue
        for item in bets:
            item_keys.update(item.keys())
            comment_id = str(item.get("comment_id") or "")
            dedupe_key = comment_id or json.dumps(item, sort_keys=True, ensure_ascii=False)
            if dedupe_key in seen_comment_ids:
                continue
            seen_comment_ids.add(dedupe_key)
            combined_items.append(dict(item))

    if not combined_items:
        return None, {"reason": "xhr_empty_or_schema_mismatch"}

    document = RawDocument(
        source_id="zawodtyper",
        url=page_url,
        final_url=final_url,
        fetched_at_utc=datetime.now(timezone.utc).isoformat(),
        html=json.dumps({"success": True, "data": combined_items}, ensure_ascii=False),
        status_code=200,
        content_type="application/json",
    )
    return document, {
        "cookie_policy": cookie_policy,
        "allowed_cookie_names": allowed_cookie_names,
        "blocked_cookie_names": blocked_cookie_names,
        "observed_cookie_names": observed_cookie_names,
        "cookie_names_sent": cookie_names_sent,
        "item_count": len(combined_items),
        "item_keys": sorted(item_keys),
        "xhr_call_count": len(payloads),
        "payload_keys": sorted({key for payload in payloads for key in payload.keys()}),
        "post_id": post_id,
    }


def build_zawodtyper_daily_url(date: datetime) -> str:
    """Build ZawodTyper daily URL with Polish month/weekday names."""
    day = date.day
    month = POLISH_MONTHS.get(date.month, "")
    weekday = POLISH_WEEKDAYS.get(date.weekday(), "")
    return f"https://www.zawodtyper.pl/typy-dnia-{day}-{month}-{weekday}/"


def _extract_zawodtyper_internal(doc: RawDocument, review_data: dict[str, Any] | None = None) -> ExtractionResult:
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
        allow_xhr = False
        if review_data:
            reviews = review_data.get("source_reviews", {})
            source_review = reviews.get("zawodtyper", {})
            if isinstance(source_review, dict):
                allow_xhr = source_review.get("allow_public_xhr_capture", False) is True

        if not allow_xhr:
            return ExtractionResult(
                source_id="zawodtyper",
                url=doc.url,
                verdict=ExtractorVerdict.EMPTY,
                picks=[],
                warnings=["allow_public_xhr_capture_required_for_xhr_parsing", "NEEDS_PUBLIC_XHR_REVIEW"],
                parser_version="tipster_parser_v2.3_final_source_specific",
                fallback="needs_public_xhr_review",
            )

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

            classify_market_v2 = lambda m, c: market_family(m) if market_family(m) != "unknown" else market_family(m + " " + c)
            extract_direction_v2 = lambda m, c: direction(m) if direction(m) != "OTHER" else direction(m + " " + c)

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


def extract_zawodtyper(doc: RawDocument, review_data: dict[str, Any] | None = None) -> ExtractionResult:
    """Deterministic extractor wrapper for ZawodTyper with coverage tracking."""
    res = _extract_zawodtyper_internal(doc, review_data)

    visible_match = re.search(r'(?:Typów|Typow|Typy|Picks)\s*(?:dnia)?\s*[:\s]*(\d+)', doc.html, re.IGNORECASE)
    expected_visible_count = int(visible_match.group(1)) if visible_match else None
    extracted_count = len(res.picks)

    coverage_ratio = None
    if expected_visible_count is not None and expected_visible_count > 0:
        coverage_ratio = round(extracted_count / expected_visible_count, 4)

    coverage_status = "FULL_OR_ACCEPTABLE"
    if expected_visible_count is not None:
        if extracted_count < expected_visible_count:
            is_very_low = (extracted_count <= 5) or (coverage_ratio is not None and coverage_ratio < 0.3)
            if is_very_low:
                warn_str = f"coverage_under_extraction:expected={expected_visible_count} extracted={extracted_count}"
                if warn_str not in res.warnings:
                    res.warnings.append(warn_str)
                coverage_status = "COVERAGE_UNDER_EXTRACTION"
            else:
                coverage_status = "PARTIAL_PUBLIC_HTML"
    elif "NEEDS_PUBLIC_XHR_REVIEW" in res.warnings:
        coverage_status = "NEEDS_PUBLIC_XHR_REVIEW"

    res.expected_visible_count = expected_visible_count
    res.extracted_count = extracted_count
    res.coverage_ratio = coverage_ratio
    res.coverage_status = coverage_status
    return res
