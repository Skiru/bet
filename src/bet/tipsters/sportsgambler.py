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


# One fixture's prediction page, as linked from the tips listing. The listing
# itself publishes no tip at all -- only fixture, kickoff and a "Predictions"
# button -- which is why the old link scan came back with nav entries like
# /betting-tips/ and /betting-tips/football/premier-league-predictions/ and the
# source produced zero picks while fetching cleanly. The anchors that matter
# carry class "betlist-item" and nothing else on the page does.
_DETAIL_LINK_SELECTOR = "a.betlist-item[href]"

# ".../parma-vs-cremonese-prediction-lineups-odds-2026-09-01/" -- the fixture
# date is in the slug, which is the only place the detail page states it in a
# form that does not depend on the reader's timezone widget.
_SLUG_DATE = re.compile(r"-(\d{4}-\d{2}-\d{2})/?$")


def discover_sportsgambler_detail_links(
    html: str, base_url: str = "https://www.sportsgambler.com", max_links: int = 5
) -> list[str]:
    """Fixture prediction pages linked from a tips listing."""
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for anchor in soup.select(_DETAIL_LINK_SELECTOR):
        url = urljoin(base_url, anchor["href"])
        if not url.startswith(base_url) or not is_allowed_sportsgambler_url(url):
            continue
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


# "Parma vs Cremonese Prediction, Betting Tips, Lineups & Odds | 01 Sep 2026"
_TITLE_FIXTURE = re.compile(r"^(?P<home>.+?)\s+vs\s+(?P<away>.+?)\s+Prediction\b", re.I)

# The headline selection, rendered as its own heading: "Parma To Win @ 2.16".
_MAIN_PICK = re.compile(r"^(?P<claim>.+?)\s*@\s*(?P<odds>\d+(?:\.\d+)?)\s*$")


def _fixture_from_detail(soup: BeautifulSoup, url: str) -> tuple[str, str, str | None]:
    """Home, away and the fixture date, or ("", "", None) if this is not a fixture page."""
    heading = soup.find("h1")
    match = _TITLE_FIXTURE.match(collapse_ws(heading.get_text(" ")) if heading else "")
    if not match:
        return "", "", None
    home = clean_team_name(match.group("home"))
    away = clean_team_name(match.group("away"))
    slug_date = _SLUG_DATE.search(url)
    return home, away, (slug_date.group(1) if slug_date else None)


def _bet_builder_legs(soup: BeautifulSoup) -> list[tuple[str, float | None]]:
    """One (claim_text, own_price) per leg of the site's bet builder.

    Each leg is emitted as a *separate* claim rather than as one parlay, and the
    distinction is not a liberty: every leg carries its own individual price in
    its own ``a.odbtn``. ZawodTyper publishes "2X + powyżej 1.5 goli @ 2.94" --
    one combined price for a ticket whose legs were never separately endorsed,
    and which stays uncountable. Sportsgambler publishes "Total Goals / Under
    2.5 / 1.62" beside "Full-Time Result / Parma / 2.16": three markets the site
    prices and recommends one by one, then suggests combining them. Refusing
    those would discard the only totals this source publishes, since its
    headline pick is a 1X2 on every fixture observed.

    The claim text is assembled as "<market> <selection>" so the existing
    classifier reads it unchanged: "Total Goals Under 2.5" is a match total,
    "Team Corners Wolfsberger Over 4.5" scopes to that team, and "Asian Handicap
    Bolton +0.75" is still refused as a handicap.
    """
    legs: list[tuple[str, float | None]] = []
    for item in soup.select("div.bb_list div.bb_list_item"):
        spans = [collapse_ws(sp.get_text(" ")) for sp in item.find_all("span", recursive=False)]
        parts = [sp for sp in spans if sp]
        if len(parts) < 2:
            continue
        price_tag = item.select_one("a.odbtn")
        price = None
        if price_tag:
            try:
                price = float(collapse_ws(price_tag.get_text()).replace(",", "."))
            except ValueError:
                price = None
        legs.append((collapse_ws(" ".join(parts)), price))
    return legs


def parse_sportsgambler_detail(html: str, url: str) -> list[TipsterPick]:
    """Picks from one fixture's prediction page.

    A listing page yields nothing here on purpose: it carries the fixture, the
    kickoff and a button, and no tip whatsoever. The picks live one click away,
    which is why this source fetched cleanly and produced zero picks for as long
    as only the listing was parsed.
    """
    if is_sportsgambler_index_url(url):
        return []

    soup = BeautifulSoup(html, "html.parser")
    for junk in soup(["script", "style", "noscript"]):
        junk.decompose()

    home, away, match_date = _fixture_from_detail(soup, url)
    if not home or not away or not is_valid_sportsgambler_teams(home, away):
        return []

    # This source is registered with data_role "narrative_team_news_stats", and
    # the detail page is where that narrative lives: absences, probable XI, xG
    # and recent form. The picks are read structurally, but the surrounding
    # prose is still the evidence the rest of the pipeline stores.
    page_signals = valuable_signals(html_to_text(html))

    sport = detect_sport(f"{home} {away}", url) or "football"
    event = f"{home} vs {away}"
    claims: list[tuple[str, float | None, str]] = []

    legs = _bet_builder_legs(soup)
    for text, price in legs:
        claims.append((text, price, "bet_builder_leg"))

    # The headline pick, but only when the builder gave us nothing. It is the
    # same selection as one of the legs, written as prose instead of as a row --
    # "LASK To Win @ 1.76" beside "Full-Time Result / LASK / 1.76", identical
    # price on every fixture observed. Emitting both counted one opinion twice,
    # which inflates ``considered`` and, for the 1X2 picks that dominate this
    # source, would have doubled every entry in public_lean.
    if not legs:
        for heading in soup.find_all(["h2", "h3"]):
            main = _MAIN_PICK.match(collapse_ws(heading.get_text(" ")))
            if main:
                claims.append((main.group("claim"), float(main.group("odds")), "main_prediction"))
                break

    picks: list[TipsterPick] = []
    seen: set[str] = set()
    for text, price, origin in claims:
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        picks.append(TipsterPick(
            source_id="sportsgambler",
            source_name="Sportsgambler",
            sport=sport,
            event=event,
            home_team=home,
            away_team=away,
            market=text,
            market_family=market_family(text),
            direction=direction(text),
            line=parse_line(text),
            odds_decimal=price,
            confidence_label="source_claim",
            reasoning=f"sportsgambler {origin}",
            stats_cited=stats_cited(text),
            valuable_signals=page_signals,
            source_url=url,
            match_date=match_date,
            # Each leg is separately named and separately priced, so it is a
            # standalone selection. See _bet_builder_legs.
            is_combo=False,
            warnings=[origin],
            extraction_quality=0.9,
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
