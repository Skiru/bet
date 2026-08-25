"""Source-specific parser and fetcher rules for Typersi.

Covers static HTML table extraction, Polish character preservation, Polish market normalization,
and aggressive team name and event metadata stripping.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse
from bs4 import BeautifulSoup

from .contracts import ExtractionResult, ExtractorVerdict, RawDocument, TipsterPick
from .normalization import clean_team_name, is_garbage_team, collapse_ws
from bet.pipeline.tipster_parsers import DISCIPLINE_MAP
from .market_parser import market_family, direction, parse_line, extract_odds, stats_cited
from .extractors import detect_sport, PARSER_VERSION


@dataclass
class ParsedTypersiRow:
    tipster_name: str
    time: str
    bookmaker_name: str
    event: str
    market: str
    odds: float | None
    result: str | None
    sport: str


def build_typersi_entrypoints(date: str) -> list[str]:
    """Build entrypoint URLs for Typersi."""
    return ["https://typersi.pl/"]


def is_allowed_typersi_url(url: str) -> bool:
    """Verify url matches Typersi boundaries and has no forbidden terms."""
    parsed = urlparse(url)
    if parsed.netloc not in ("typersi.pl", "www.typersi.pl"):
        return False
    # Block list as per rules
    for forbidden in ("/r/", "/odds.php", "/betting-sites/go/", "/login", "/signup", "/account", "/bonus", "/casino"):
        if forbidden in url.lower():
            return False
    return True


def clean_typersi_team_name(name: str) -> str:
    """Strip Polish match metadata, rounds and update markers from club names."""
    text = name.strip()
    # Strip "- XX kolejka..." and round info
    text = re.sub(r"\s+[-–—]\s+\d+\s+kolejka.*$", "", text, flags=re.I)
    text = re.sub(r"\s+[-–—]\s+kolejka\s+\d+.*$", "", text, flags=re.I)
    text = re.sub(r"\s+kolejka\s+\d+.*$", "", text, flags=re.I)
    text = re.sub(r"\s+[-–—]\s+round\s+\d+.*$", "", text, flags=re.I)
    text = re.sub(r"\s+[-–—]?\s*Aktualizacja.*$", "", text, flags=re.I)
    text = re.sub(r"\s*Aktualizacja.*$", "", text, flags=re.I)
    text = re.sub(r"\s+[-–—]\s+Analiza.*$", "", text, flags=re.I)
    text = re.sub(r"\s+[-–—]\s+\d{2}\.\d{2}\.\d{4}.*$", "", text, flags=re.I) # strip dates
    return clean_team_name(text)


def normalize_typersi_row(row_text: str) -> ParsedTypersiRow:
    """Parse a single row text from Typersi into structured fields."""
    return ParsedTypersiRow(
        tipster_name="Unknown",
        time="",
        bookmaker_name="Metadata Only",
        event=row_text,
        market="N/A",
        odds=None,
        result=None,
        sport="football"
    )


def parse_typersi_static_tables(html: str, url: str) -> list[TipsterPick]:
    """Parse index page tables statically using BeautifulSoup.

    Finds rows in blocks:
    - Typy najlepszej piątki z rankingu typerów,
    - Typy bukmacherskie najskuteczniejszych typerów,
    - Typy na dziś.
    """
    soup = BeautifulSoup(html, "html.parser")
    picks = []
    seen = set()

    # Iterate over all tables on the page
    tables = soup.find_all("table")
    for table in tables:
        # Find preceding heading or section title if possible
        section_text = ""
        prev = table.find_previous(["h1", "h2", "h3", "h4", "div"])
        if prev:
            section_text = prev.get_text().lower()

        # Reject promo, casino, affiliate, and disclaimer tables
        if any(tok in section_text for tok in ("promocje", "bonus", "kasyno", "bukmacherskie-promocje")):
            continue

        rows = table.find_all("tr")
        for r in rows:
            cells = [c.get_text(separator=" ").strip() for c in r.find_all(["td", "th"])]
            if len(cells) < 4:
                continue

            # Typersi rows typically contain:
            # - Hour/Time (e.g., "18:00")
            # - Tipster/User
            # - Event Name (e.g., "Sandecja - KKS Kalisz")
            # - Tip/Pick (e.g., "1X", "over 2.5")
            # - Odds/Kurs (e.g., "1.85")
            # - Bookmaker Name or logo

            # Let's map cells based on simple heuristic matching:
            # Cell 0/1 usually has time, cell 1/2 user, cell 2/3 event, cell 3/4 tip, cell 4/5 odds
            event_idx = -1
            for idx, val in enumerate(cells[:5]):
                if "-" in val or " vs " in val or " v " in val:
                    event_idx = idx
                    break

            if event_idx == -1:
                continue

            # Safely extract event teams
            event_raw = cells[event_idx]
            parts = re.split(r'\s+-\s+|\s+vs\.?\s+|\s+v\.?\s+', event_raw, maxsplit=1, flags=re.I)
            if len(parts) != 2:
                continue

            home = clean_typersi_team_name(parts[0])
            away = clean_typersi_team_name(parts[1])
            if is_garbage_team(home) or is_garbage_team(away) or home.lower() == away.lower():
                continue

            # Extract tipster name. Scanning back to the first *meaningful* cell
            # rather than taking event_idx-1 blindly: the live row layout is
            # ['', 'Kasia', '11:00', '', 'Orix Buffaloes - Rakuten G', ...], so
            # the immediately preceding cell is the empty bookmaker-logo column
            # and every pick came out attributed to "Typersi". A consensus whose
            # members are all one name cannot be weighted by who said it.
            tipster = "Typersi"
            for cell in reversed(cells[:event_idx]):
                candidate = collapse_ws(cell)
                if not candidate:
                    continue
                if re.fullmatch(r"\d{1,2}[:.]\d{2}", candidate):  # kickoff time
                    continue
                if re.fullmatch(r"[\d.,]+", candidate):  # odds or a count
                    continue
                tipster = candidate
                break

            # Extract market/pick
            market = "N/A"
            if event_idx + 1 < len(cells):
                market = cells[event_idx + 1] or "N/A"

            # Extract odds
            odds = None
            if event_idx + 2 < len(cells):
                odds = extract_odds(cells[event_idx + 2])

            # Extract bookmaker name as metadata only
            bookmaker = "Metadata Only"
            if event_idx + 3 < len(cells):
                bookmaker = cells[event_idx + 3] or "Metadata Only"

            # The site states the discipline in its own cell, last in the row
            # ("Piłka nożna", "Tenis", "Baseball"). Reading it beats inferring
            # from the team names, which is what detect_sport did: it has no
            # football keyword to find in "Semenistaja D. - Kinoshita H." and so
            # returned its "football" default for every row. The live run of
            # 2026-08-25 labelled 29 of 29 picks football, tennis and NPB
            # baseball fixtures included. A mislabelled sport cannot match a
            # discovered event -- sport equality is exact by design -- so the
            # pick was silently dropped rather than wrongly attributed.
            sport = ""
            for cell in reversed(cells[event_idx + 1:]):
                mapped = DISCIPLINE_MAP.get(collapse_ws(cell).lower())
                if mapped:
                    sport = mapped
                    break
            warnings = ["weak_or_empty_reasoning", "odds_reference_only"]
            if not sport:
                # Fall back to the old inference, but say that it was a guess.
                sport = detect_sport(event_raw, url)
                warnings.append("sport_inferred_no_discipline_cell")

            # Map double chance and basic outcome markets
            normalized_market = market
            if market in ("1", "X", "2", "1X", "X2", "12"):
                normalized_market = f"Winner: {market}"

            fam = market_family(normalized_market)
            dirn = direction(normalized_market)

            # Formulate reasoning-free row context
            reasoning = "" # No narrative reasoning text is present in the table itself

            key = (home.lower(), away.lower(), normalized_market.lower())
            if key in seen:
                continue
            seen.add(key)

            # Typersi is Polish community site, we preserve Polish chars
            picks.append(TipsterPick(
                source_id="typersi",
                source_name="Typersi",
                sport=sport,
                event=f"{home} vs {away}",
                home_team=home,
                away_team=away,
                market=normalized_market,
                market_family=fam,
                direction=dirn,
                line=parse_line(normalized_market),
                odds_decimal=odds,
                reasoning=reasoning,
                stats_cited=stats_cited(event_raw + " " + normalized_market),
                tipster_name=tipster,
                source_url=url,
                extraction_quality=0.48, # table context only, no narrative reasoning
                warnings=warnings,
                valuable_signals={"bookmaker_metadata": [bookmaker]},
                source_record_type="source_claim_evidence",
            ))

    return picks


def extract_typersi_document(doc: RawDocument) -> ExtractionResult:
    """Parse RawDocument into production-grade ExtractionResult."""
    picks = parse_typersi_static_tables(doc.html, doc.url)
    verdict = ExtractorVerdict.OK if picks else ExtractorVerdict.EMPTY
    return ExtractionResult(
        source_id="typersi",
        url=doc.url,
        verdict=verdict,
        picks=picks,
        warnings=[],
        parser_version=PARSER_VERSION
    )
