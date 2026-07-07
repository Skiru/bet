"""Source-specific parser and fetcher rules for ProTipster.

Enforces static HTTP public card parsing, extracts PT score and tipster statistics,
supports ContextSignals for top matches, and excludes forbidden marketing/bonus/AKO paths.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse
from bs4 import BeautifulSoup

from .contracts import ExtractionResult, ExtractorVerdict, RawDocument, TipsterPick
from .normalization import clean_team_name, is_garbage_team, collapse_ws
from .market_parser import market_family, direction, parse_line, extract_odds, stats_cited, extract_market_text
from .html_tools import html_to_text, text_blocks
from .extractors import detect_sport, PARSER_VERSION


@dataclass
class ContextSignal:
    event: str
    time: str | None = None
    trend_text: str | None = None
    tips_count: int | None = None
    odds_snapshot: str | None = None
    source_url: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TipsterStats:
    username: str
    pt_score: float | None = None
    yield_pct: float | None = None
    win_rate: float | None = None
    followers: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def build_protipster_entrypoints(date: str, sports: list[str] | None = None, markets: list[str] | None = None) -> list[str]:
    """Build entrypoints for ProTipster."""
    return [
        "https://www.protipster.pl/",
        "https://www.protipster.pl/typy-bukmacherskie",
        "https://www.protipster.pl/typy-bukmacherskie/na-dzisiaj",
        "https://www.protipster.pl/typy-bukmacherskie/pilka-nozna",
        "https://www.protipster.pl/typy-bukmacherskie/najlepsze-zaklady-dzisiaj",
        "https://www.protipster.pl/typy-bukmacherskie/btts"
    ]


def is_allowed_protipster_url(url: str) -> bool:
    """Validate ProTipster URL against strict boundary list."""
    parsed = urlparse(url)
    if parsed.netloc not in ("www.protipster.pl", "protipster.pl"):
        return False
        
    path = parsed.path.lower()
    
    # Block list as per rules
    for forbidden in ("/login", "/rejestracja", "/account", "/profile", "/bonus", "/kasyno", "/casino", "/r/", "/go/", "odds.php"):
        if forbidden in path:
            return False
            
    # Allowed paths: /typy-bukmacherskie, /mecze, /newsy-bukmacherskie
    if path == "/" or path.startswith("/typy-bukmacherskie") or path.startswith("/mecze") or path.startswith("/newsy-bukmacherskie"):
        return True
    return False


def parse_protipster_tip_cards(html: str, url: str) -> list[TipsterPick]:
    """Extract individual static tip cards from ProTipster HTML."""
    soup = BeautifulSoup(html, "html.parser")
    picks = []
    seen = set()
    
    # Method 1: BS4 Element Card Parsing
    cards = soup.find_all("div", class_=re.compile(r"(tip-card|feed-item|prediction-card)"))
    for card in cards:
        text = card.get_text(separator=" ").strip()
        # Filter marketing promos, app banners, casino, bonuses, and Trustpilot
        if any(token in text.lower() for token in ("zagraj", "casino", "kasyno", "bonus", "ranking bukmacherów", "trustpilot", "promocja")):
            continue
            
        match = re.search(r"([A-ZÀ-Ž][A-Za-zÀ-ž0-9 .'-]{1,30})\s+(?:vs?\.?|v\.?|–|-)\s+([A-ZÀ-Ž][A-Za-zÀ-ž0-9 .'-]{1,30})", text)
        if not match:
            continue
            
        home = clean_team_name(match.group(1))
        away = clean_team_name(match.group(2))
        if is_garbage_team(home) or is_garbage_team(away) or home.lower() == away.lower():
            continue
            
        odds = extract_odds(text)
        # Check for AKO/Coupon triggers to reject
        if any(ako in text.lower() for ako in ("ako", "kupon", "multi", "accumulator")):
            continue
            
        market = extract_market_text(text)
        if market == "N/A":
            type_m = re.search(r"(?:rodzaj zakładu|typ|zakład)[:\s]+([A-Za-z0-9 .'-]{1,30})", text, re.I)
            if type_m:
                market = type_m.group(1).strip()
                
        tipster_m = re.search(r"\b(?:username|typer|user|autor|napisane przez)\b[:\s]*([@A-Za-z0-9_.-]+)", text, re.I)
        tipster = tipster_m.group(1).strip() if tipster_m else "ProTipster User"
        
        pt_score = None
        score_m = re.search(r"(?:ocena typu|pt score|score|ocena)[:\s]*([0-9]+(?:\.[0-9]+)?)", text, re.I)
        if score_m:
            try:
                pt_score = float(score_m.group(1))
            except ValueError:
                pass
                
        reasoning = ""
        analysis_m = re.search(r"(?:zobacz szczegóły typu|analiza|opis)[:\s]*(.+)", text, re.I)
        if analysis_m:
            reasoning = collapse_ws(analysis_m.group(1))[:1000]
            
        warnings = []
        if not reasoning or len(reasoning) < 30:
            warnings.append("weak_or_empty_reasoning")
            
        valuable_signals = {}
        if pt_score is not None:
            valuable_signals["source_quality"] = [f"pt_score={pt_score}"]
            
        key = (home.lower(), away.lower(), market.lower())
        if key in seen:
            continue
        seen.add(key)
        
        picks.append(TipsterPick(
            source_id="protipster",
            source_name="ProTipster PL",
            sport=detect_sport(text, url),
            event=f"{home} vs {away}",
            home_team=home,
            away_team=away,
            market=market,
            market_family=market_family(market),
            direction=direction(market),
            line=parse_line(market),
            odds_decimal=odds,
            reasoning=reasoning if len(reasoning) >= 30 else "",
            stats_cited=stats_cited(text),
            tipster_name=tipster,
            source_url=url,
            extraction_quality=0.52 if reasoning else 0.42,
            warnings=warnings,
            valuable_signals=valuable_signals,
            source_record_type="source_claim_evidence",
        ))
        
    # Method 2: Fallback text parsing if no specific cards are found but text contains patterns
    if not picks:
        full_text = html_to_text(html)
        blocks = text_blocks(html)
        for i, block in enumerate(blocks):
            if any(tok in block.lower() for tok in ("zagraj", "casino", "kasyno", "bonus", "ranking bukmacherów")):
                continue
            if any(ako in block.lower() for ako in ("ako", "kupon", "multi", "accumulator")):
                continue
                
            match = re.search(r"([A-ZÀ-Ž][A-Za-zÀ-ž0-9 .'-]{1,30})\s+(?:vs?\.?|v\.?|–|-)\s+([A-ZÀ-Ž][A-Za-zÀ-ž0-9 .'-]{1,30})", block)
            if not match:
                continue
                
            home = clean_team_name(match.group(1))
            away = clean_team_name(match.group(2))
            if is_garbage_team(home) or is_garbage_team(away) or home.lower() == away.lower():
                continue
                
            odds = extract_odds(block)
            market = extract_market_text(block)
            pt_score = None
            score_m = re.search(r"(?:ocena typu|pt score|score|ocena)[:\s]*([0-9]+(?:\.[0-9]+)?)", block, re.I)
            if score_m:
                try:
                    pt_score = float(score_m.group(1))
                except ValueError:
                    pass
                    
            valuable_signals = {}
            if pt_score is not None:
                valuable_signals["source_quality"] = [f"pt_score={pt_score}"]
                
            key = (home.lower(), away.lower(), market.lower())
            if key in seen:
                continue
            seen.add(key)
            
            picks.append(TipsterPick(
                source_id="protipster",
                source_name="ProTipster PL",
                sport=detect_sport(block, url),
                event=f"{home} vs {away}",
                home_team=home,
                away_team=away,
                market=market,
                market_family=market_family(market),
                direction=direction(market),
                line=parse_line(market),
                odds_decimal=odds,
                reasoning="",
                stats_cited=stats_cited(block),
                tipster_name="ProTipster User",
                source_url=url,
                extraction_quality=0.42,
                warnings=["weak_or_empty_reasoning"],
                valuable_signals=valuable_signals,
                source_record_type="source_claim_evidence",
            ))
            
    return picks


def parse_protipster_top_matches(html: str, url: str) -> list[ContextSignal]:
    """Parse top matches without explicit tips to serve as ContextSignal context."""
    soup = BeautifulSoup(html, "html.parser")
    signals = []
    
    # Look for top match listing blocks
    blocks = soup.find_all("div", class_=re.compile(r"(top-match|match-row|popular-match)"))
    for block in blocks:
        text = block.get_text(separator=" ").strip()
        match = re.search(r"([A-ZÀ-Ž][A-Za-zÀ-ž0-9 .'-]{2,30})\s+(?:vs?\.?|v\.?|–|-)\s+([A-ZÀ-Ž][A-Za-zÀ-ž0-9 .'-]{2,30})", text)
        if not match:
            continue
            
        home = clean_team_name(match.group(1))
        away = clean_team_name(match.group(2))
        if is_garbage_team(home) or is_garbage_team(away):
            continue
            
        tips_count = None
        count_m = re.search(r"(\d+)\s+(?:typów|typy|tips)", text, re.I)
        if count_m:
            tips_count = int(count_m.group(1))
            
        trend_m = re.search(r"(?:trend|faworyt|popularne)[:\s]+([A-Za-z0-9 .'-]+)", text, re.I)
        trend = trend_m.group(1).strip() if trend_m else None
        
        signals.append(ContextSignal(
            event=f"{home} vs {away}",
            trend_text=trend,
            tips_count=tips_count,
            source_url=url
        ))
        
    return signals


def parse_protipster_tipster_stats(html: str, url: str) -> list[TipsterStats]:
    """Extract tipster track records statically."""
    soup = BeautifulSoup(html, "html.parser")
    stats = []
    
    # Look for tipster cards or listing rows
    profiles = soup.find_all("div", class_=re.compile(r"(tipster-profile|user-card|author-row)"))
    for prof in profiles:
        text = prof.get_text(separator=" ").strip()
        username_m = re.search(r"\b(?:username|typer|user)\b[:\s]*([@A-Za-z0-9_.-]+)", text, re.I)
        if not username_m:
            continue
            
        username = username_m.group(1)
        yield_m = re.search(r"yield[:\s]*([+-]?[0-9]+(?:\.[0-9]+)?)\s*%", text, re.I)
        yield_val = float(yield_m.group(1)) if yield_m else None
        
        win_m = re.search(r"win\s*rate[:\s]*(\d+)\s*%", text, re.I)
        win_val = float(win_m.group(1)) if win_m else None
        
        followers_m = re.search(r"(\d+)\s*(?:obserwujących|followers)", text, re.I)
        followers_val = int(followers_m.group(1)) if followers_m else None
        
        stats.append(TipsterStats(
            username=username,
            yield_pct=yield_val,
            win_rate=win_val,
            followers=followers_val
        ))
        
    return stats


def extract_protipster_document(doc: RawDocument) -> ExtractionResult:
    """Parse RawDocument into candidate-only ExtractionResult."""
    picks = parse_protipster_tip_cards(doc.html, doc.url)
    warnings = ["protipster_candidate_blocked_by_robots_txt_offline_only"]
    verdict = ExtractorVerdict.OK if picks else ExtractorVerdict.EMPTY
    return ExtractionResult(
        source_id="protipster",
        url=doc.url,
        verdict=verdict,
        picks=picks,
        warnings=warnings,
        parser_version=PARSER_VERSION
    )
