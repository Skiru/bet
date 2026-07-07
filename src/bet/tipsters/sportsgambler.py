"""Source-specific parser and fetcher rules for Sportsgambler.

Covers static HTML article extraction, narrative analysis, injuries, lineups,
and prevents false-positive analyst/staff match extraction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from .contracts import ExtractionResult, ExtractorVerdict, RawDocument, TipsterPick
from .html_tools import html_to_text, link_candidates, text_blocks, joined_context
from .market_parser import extract_market_text, market_family, direction, parse_line, extract_odds, stats_cited
from .normalization import clean_team_name, is_garbage_team, collapse_ws
from .extractors import detect_sport, valuable_signals, PARSER_VERSION

# Analyst/author filter to prevent Rafa Hernandez vs Gabriel Oliveira garbage events
FORBIDDEN_TEAM_KEYWORDS = {
    "analyst", "editor", "writer", "staff", "gabriel", "rafael", "oliveira", "hernández", "hernandez",
    "sportsgambler", "tips", "preview", "predictions", "match preview", "match prediction"
}


@dataclass
class SourceCandidate:
    url: str
    event: str
    sport: str
    market: str
    odds: float | None
    home_team: str
    away_team: str
    context: str

    def to_dict(self) -> dict:
        return asdict(self)


def build_sportsgambler_entrypoints(date: str, sports: list[str] | None = None) -> list[str]:
    """Build entrypoint URLs for Sportsgambler."""
    if not sports:
        return ["https://www.sportsgambler.com/betting-tips/football/"]
    
    urls = []
    for sport in sports:
        s = sport.lower()
        if s == "football" or s == "soccer":
            urls.append("https://www.sportsgambler.com/betting-tips/football/")
        else:
            urls.append(f"https://www.sportsgambler.com/betting-tips/{s}/")
    return urls


def is_allowed_sportsgambler_url(url: str) -> bool:
    """Verify url matches Sportsgambler boundaries and has no forbidden terms."""
    parsed = urlparse(url)
    if parsed.netloc != "www.sportsgambler.com":
        return False
    
    # Block list as per rules
    for forbidden in ("/r/", "/odds.php", "/betting-sites/go/", "/login", "/signup", "/account", "/bonus", "/casino"):
        if forbidden in url.lower():
            return False
            
    # Allow only betting tips or predictions detail pages
    path = parsed.path.lower()
    if path.startswith("/betting-tips/") or path.startswith("/predictions/"):
        return True
    return False


def discover_sportsgambler_detail_links(html: str, base_url: str = "https://www.sportsgambler.com", max_links: int = 5) -> list[str]:
    """Scan HTML for allowed Sportsgambler preview details pages."""
    links = []
    for link in link_candidates(html, base_url):
        url = link.url
        if not url.startswith(base_url):
            continue
        if is_allowed_sportsgambler_url(url):
            if url not in links:
                links.append(url)
    return links[:max_links]


def is_valid_sportsgambler_teams(home: str, away: str) -> bool:
    """Check if team names are actual football/sports teams and not staff profiles."""
    home_low = home.lower()
    away_low = away.lower()
    if not any(c.isalpha() for c in home) or not any(c.isalpha() for c in away):
        return False
    if is_garbage_team(home) or is_garbage_team(away):
        return False
    for keyword in FORBIDDEN_TEAM_KEYWORDS:
        if keyword in home_low or keyword in away_low:
            return False
    return True


def parse_sportsgambler_index(html: str, url: str) -> list[SourceCandidate]:
    """Parse listing/index page for upcoming events."""
    blocks = text_blocks(html)
    candidates = []
    EVENT_PATTERNS = [
        re.compile(r"(?P<home>[A-ZÀ-Ž0-9][A-Za-zÀ-ž0-9.' &/-]{1,55}?)\s+(?:vs?\.?|v\.?|@)\s+(?P<away>[A-ZÀ-Ž0-9][A-Za-zÀ-ž0-9.' &/-]{1,55})", re.U),
        re.compile(r"(?P<home>[A-ZÀ-Ž0-9][A-Za-zÀ-ž0-9.' &/-]{1,55}?)\s+[–—-]\s+(?P<away>[A-ZÀ-Ž0-9][A-Za-zÀ-ž0-9.' &/-]{1,55})", re.U),
    ]
    for i, block in enumerate(blocks):
        for pat in EVENT_PATTERNS:
            m = pat.search(block)
            if not m:
                continue
            home = clean_team_name(m.group("home"))
            away = clean_team_name(m.group("away"))
            if not is_valid_sportsgambler_teams(home, away):
                continue
            context = joined_context(blocks[i:i + 8], window=8)
            market = extract_market_text(context)
            odds = extract_odds(context)
            candidates.append(SourceCandidate(
                url=url,
                event=f"{home} vs {away}",
                sport=detect_sport(context, url),
                market=market,
                odds=odds,
                home_team=home,
                away_team=away,
                context=context
            ))
    return candidates


def is_sportsgambler_index_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc not in ("www.sportsgambler.com", "sportsgambler.com"):
        return False
    path = parsed.path.lower().strip("/")
    parts = [p for p in path.split("/") if p]
    if not parts:
        return True
    if parts[0] == "betting-tips":
        if len(parts) <= 2:
            return True
    if parts[0] in ("predictions", "prediction") and len(parts) == 1:
        return True
    return False


def parse_sportsgambler_detail(html: str, url: str) -> list[TipsterPick]:
    """Parse article detail page for robust injury, lineup and qualitative tips."""
    # Check if this is an index/listing page. If it is an index page,
    # we do NOT extract picks, we only extract SourceCandidates!
    if is_sportsgambler_index_url(url):
        return []

    text = html_to_text(html)
    soup = BeautifulSoup(html, "html.parser")
    # Clean up scripts, styles and unwanted elements
    for s in soup(["script", "style", "noscript"]):
        s.decompose()
    # Extract structural blocks cleanly
    blocks = []
    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "td"]):
        txt = collapse_ws(el.get_text()).strip()
        if len(txt) >= 3 and txt not in blocks:
            blocks.append(txt)
    if not blocks:
        blocks = text_blocks(html)
        
    picks = []
    seen = set()
    EVENT_PATTERNS = [
        re.compile(r"(?P<home>[A-ZÀ-Ž0-9][A-Za-zÀ-ž0-9.' &/-]{1,55}?)\s+(?:vs?\.?|v\.?|@)\s+(?P<away>[A-ZÀ-Ž0-9][A-Za-zÀ-ž0-9.' &/-]{1,55})", re.U),
        re.compile(r"(?P<home>[A-ZÀ-Ž0-9][A-Za-zÀ-ž0-9.' &/-]{1,55}?)\s+[–—-]\s+(?P<away>[A-ZÀ-Ž0-9][A-Za-zÀ-ž0-9.' &/-]{1,55})", re.U),
    ]

    # Find author if present
    author = "Sportsgambler Analyst"
    author_m = re.search(r"(?:napisane przez|by|author|autor)[:\s]*([A-Za-z0-9 .'-]+)", text, re.I)
    if author_m:
        author = author_m.group(1).strip()

    for i, block in enumerate(blocks):
        for pat in EVENT_PATTERNS:
            m = pat.search(block)
            if not m:
                continue
            home = clean_team_name(m.group("home"))
            away = clean_team_name(m.group("away"))
            if not is_valid_sportsgambler_teams(home, away):
                continue
            
            context = joined_context(blocks[i:i + 8], window=8)
            market = extract_market_text(context)
            fam = market_family(market + " " + context)
            dirn = direction(market + " " + context)
            reasoning = collapse_ws(context)[:1100]
            
            # Check length of reasoning to prevent empty claims
            quality = len(reasoning) >= 40
            warnings = []
            if market == "N/A":
                warnings.append("market_not_detected")
            if not quality:
                warnings.append("weak_or_empty_reasoning")
                
            signals = valuable_signals(context)
            
            # Boost extraction quality if injuries/lineups are found
            base_quality = 0.40
            if market != "N/A":
                base_quality += 0.20
            if signals:
                base_quality += min(0.20, len(signals) * 0.05)
            if stats_cited(context):
                base_quality += 0.10
                
            key = (home.lower(), away.lower(), market.lower())
            if key in seen:
                continue
            seen.add(key)
            
            picks.append(TipsterPick(
                source_id="sportsgambler",
                source_name="Sportsgambler",
                sport=detect_sport(context, url),
                event=f"{home} vs {away}",
                home_team=home,
                away_team=away,
                market=market,
                market_family=fam,
                direction=dirn,
                line=parse_line(market if market != "N/A" else context),
                odds_decimal=extract_odds(context),
                reasoning=reasoning if len(reasoning) >= 30 else "",
                stats_cited=stats_cited(context),
                source_url=url,
                extraction_quality=round(min(0.96, base_quality), 2),
                warnings=warnings,
                valuable_signals=signals,
                tipster_name=author,
                source_record_type="source_claim_evidence",
            ))
            
    if not picks:
        for pat in EVENT_PATTERNS:
            for m in pat.finditer(text):
                home = clean_team_name(m.group("home"))
                away = clean_team_name(m.group("away"))
                if not is_valid_sportsgambler_teams(home, away):
                    continue
                start = max(0, m.start() - 300)
                end = min(len(text), m.end() + 1050)
                context = collapse_ws(text[start:end])
                market = extract_market_text(context)
                fam = market_family(market + " " + context)
                dirn = direction(market + " " + context)
                reasoning = collapse_ws(context)[:1100]
                
                warnings = []
                if market == "N/A":
                    warnings.append("market_not_detected")
                if len(reasoning) < 40:
                    warnings.append("weak_or_empty_reasoning")
                signals = valuable_signals(context)
                
                key = (home.lower(), away.lower(), market.lower())
                if key in seen:
                    continue
                seen.add(key)
                
                picks.append(TipsterPick(
                    source_id="sportsgambler",
                    source_name="Sportsgambler",
                    sport=detect_sport(context, url),
                    event=f"{home} vs {away}",
                    home_team=home,
                    away_team=away,
                    market=market,
                    market_family=fam,
                    direction=dirn,
                    line=parse_line(market if market != "N/A" else context),
                    odds_decimal=extract_odds(context),
                    reasoning=reasoning if len(reasoning) >= 30 else "",
                    stats_cited=stats_cited(context),
                    source_url=url,
                    extraction_quality=0.52 if reasoning else 0.42,
                    warnings=warnings,
                    valuable_signals=signals,
                    tipster_name=author,
                    source_record_type="source_claim_evidence",
                ))
    return picks


def extract_sportsgambler_documents(docs: list[RawDocument]) -> ExtractionResult:
    """Merge and parse all RawDocuments into a single production ExtractionResult."""
    all_picks = []
    warnings = []
    seen_keys = set()
    
    if not docs:
        return ExtractionResult(
            source_id="sportsgambler",
            url="",
            verdict=ExtractorVerdict.EMPTY,
            picks=[],
            warnings=["empty_documents_list"],
            parser_version=PARSER_VERSION
        )
        
    primary_url = docs[0].url
    for doc in docs:
        picks = parse_sportsgambler_detail(doc.html, doc.url)
        for p in picks:
            key = (p.sport, p.home_team.lower(), p.away_team.lower(), p.market.lower())
            if key in seen_keys:
                continue
            seen_keys.add(key)
            all_picks.append(p)
            
    verdict = ExtractorVerdict.OK if all_picks else ExtractorVerdict.EMPTY
    return ExtractionResult(
        source_id="sportsgambler",
        url=primary_url,
        verdict=verdict,
        picks=all_picks,
        warnings=warnings,
        parser_version=PARSER_VERSION
    )
