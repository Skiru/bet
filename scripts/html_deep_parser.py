#!/usr/bin/env python3
"""HTML Deep Parser — extracts rich statistical data from saved Playwright snapshots.

Reads HTML snapshots from betting/data/{domain}/ directories, applies domain-specific
extraction profiles, and enriches scan_results + team_form in the DB.

This fills the gap where adapters extract only {home, away, time} but HTML contains
much richer data: match IDs, odds for all markets, statistical averages, form indicators,
dangerous attack counts, corner/card/foul averages, etc.

Usage:
    python3 scripts/html_deep_parser.py --date 2026-05-08
    python3 scripts/html_deep_parser.py --date 2026-05-08 --domains flashscore.com,totalcorner.com
    python3 scripts/html_deep_parser.py --date 2026-05-08 --dry-run
    python3 scripts/html_deep_parser.py --date 2026-05-08 --report
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bs4 import BeautifulSoup

try:
    from bet.db.connection import get_db
    from bet.db.repositories import ScanResultRepo, StatsRepo, TeamRepo
    _HAS_DB = True
except ImportError:
    _HAS_DB = False

DATA_DIR = Path(__file__).parent.parent / "betting" / "data"


# ============================================================================
# EXTRACTION PROFILES — domain-specific rules for deep HTML parsing
# ============================================================================

class ExtractionProfile:
    """Base class for domain-specific HTML extraction profiles."""
    domain: str = ""
    sport_filter: str | None = None  # None = all sports

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        """Extract enriched data from HTML. Returns list of enrichment dicts."""
        raise NotImplementedError


class FlashscoreProfile(ExtractionProfile):
    """Flashscore — extract match IDs, scores, league hierarchy, form, and deep data.

    Flashscore match elements have `id='g_1_XXXXXXXX'` which is the internal match ID.
    This ID can be used for Flashscore API calls to get H2H, stats, lineups.

    Deep extraction rules:
    - Recent form: from "formTable" or "formRow" elements with W/L/D results
    - H2H data: from dedicated H2H sections with match scores
    - Standings: from league position markers in header/context elements
    - Injury markers: from "lineUp" sections with "injury" or "miss" markers
    """
    domain = "flashscore.com"

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        results = []

        # Build league context by iterating all relevant elements in DOM order
        # Headers (headerLeague) precede match blocks (event__match with g_1_* ids)
        league_context = {}  # match_id -> (country, league)
        last_country = ""
        last_league = ""

        # Find all headers and match elements, preserving DOM order
        all_elements = soup.find_all(True, class_=re.compile(
            r"headerLeague|event__match", re.I
        ))
        for el in all_elements:
            el_classes = " ".join(el.get("class", []))
            if "headerLeague" in el_classes and "event__match" not in el_classes:
                cat_el = el.find(True, class_=re.compile(r"category-text", re.I))
                title_el = el.find(True, class_=re.compile(r"title-text", re.I))
                if cat_el:
                    last_country = cat_el.get_text(strip=True).rstrip(":")
                if title_el:
                    last_league = title_el.get_text(strip=True)
            elif "event__match" in el_classes:
                el_id = el.get("id", "")
                if el_id and el_id.startswith("g_"):
                    league_context[el_id] = (last_country, last_league)

        # Find all match elements with IDs
        match_els = soup.find_all(True, id=re.compile(r"^g_\d+_"))
        for el in match_els:
            match_id = el.get("id", "")  # e.g., "g_1_Aa7EKVFd"

            home_el = el.find(True, class_=re.compile(r"homeParticipant", re.I))
            away_el = el.find(True, class_=re.compile(r"awayParticipant", re.I))

            if not home_el or not away_el:
                continue

            home = home_el.get_text(strip=True)
            away = away_el.get_text(strip=True)

            if not home or not away or len(home) < 2 or len(away) < 2:
                continue

            # Extract scores if available
            score_home_el = el.find(True, class_=re.compile(r"score--home", re.I))
            score_away_el = el.find(True, class_=re.compile(r"score--away", re.I))
            score_home = score_home_el.get_text(strip=True) if score_home_el else None
            score_away = score_away_el.get_text(strip=True) if score_away_el else None

            # Extract time
            time_el = el.find(True, class_=re.compile(r"event__time", re.I))
            time_str = time_el.get_text(strip=True) if time_el else None

            # Extract part scores (set/period scores)
            part_scores = []
            for part in el.find_all(True, class_=re.compile(r"event__part", re.I)):
                txt = part.get_text(strip=True)
                if txt and txt not in ["-", ""]:
                    part_scores.append(txt)

            # Get league context for this match
            ctx_country, ctx_league = league_context.get(match_id, ("", ""))

            enrichment = {
                "home": home,
                "away": away,
                "source_domain": "flashscore.com",
                "enrichments": {
                    "flashscore_match_id": match_id,
                },
            }
            if ctx_country:
                enrichment["enrichments"]["country"] = ctx_country
            if ctx_league:
                enrichment["enrichments"]["league"] = ctx_league

            if time_str:
                enrichment["time"] = time_str

            if score_home and score_home != "-":
                enrichment["enrichments"]["score_home"] = score_home
            if score_away and score_away != "-":
                enrichment["enrichments"]["score_away"] = score_away
            if part_scores:
                enrichment["enrichments"]["part_scores"] = part_scores

            results.append(enrichment)

        # --- Deep extraction: form indicators ---
        # Look for form elements (WLWWD patterns)
        for form_el in soup.find_all(True, class_=re.compile(r"form|formRow", re.I)):
            form_text = form_el.get_text(strip=True)
            # Extract W/L/D sequence
            form_chars = re.findall(r'[WLD]', form_text, re.I)
            if len(form_chars) >= 3:
                # Find closest team name
                parent = form_el.parent
                team_el = None
                if parent:
                    team_el = parent.find(True, class_=re.compile(r"participant|team", re.I))
                team_name = team_el.get_text(strip=True) if team_el else ""
                if team_name:
                    results.append({
                        "team": team_name,
                        "source_domain": "flashscore.com",
                        "stat_type": "recent_form",
                        "enrichments": {
                            "form_sequence": "".join(form_chars[:10]),
                            "wins": form_chars.count("W"),
                            "draws": form_chars.count("D"),
                            "losses": form_chars.count("L"),
                        },
                    })

        # --- Deep extraction: standings/league position ---
        for standing_el in soup.find_all(True, class_=re.compile(
            r"standings?|tableLeague|table__row", re.I
        )):
            cells = standing_el.find_all(["td", "div"])
            if len(cells) >= 4:
                pos_text = cells[0].get_text(strip=True) if cells else ""
                team_cell = standing_el.find(True, class_=re.compile(r"participant|team", re.I))
                team_link = standing_el.find("a")
                t_name = ""
                if team_cell:
                    t_name = team_cell.get_text(strip=True)
                elif team_link:
                    t_name = team_link.get_text(strip=True)

                if t_name and pos_text.isdigit():
                    standing_data = {"league_position": int(pos_text)}
                    # Extract W/D/L/GF/GA from table cells
                    for i, cell in enumerate(cells[1:], 1):
                        txt = cell.get_text(strip=True)
                        if txt.isdigit() and i <= 8:
                            standing_data[f"col_{i}"] = int(txt)
                    results.append({
                        "team": t_name,
                        "source_domain": "flashscore.com",
                        "stat_type": "standings",
                        "enrichments": standing_data,
                    })

        # --- Deep extraction: injury markers ---
        for lineup_el in soup.find_all(True, class_=re.compile(
            r"lineup|lineUp|missPlayers|injured", re.I
        )):
            player_els = lineup_el.find_all(True, class_=re.compile(
                r"player|name|miss|injury", re.I
            ))
            for p_el in player_els:
                p_name = p_el.get_text(strip=True)
                if not p_name or len(p_name) < 2:
                    continue
                # Check for injury indicator
                injury_indicator = p_el.find(True, class_=re.compile(
                    r"injur|miss|absent|suspend", re.I
                ))
                icon_el = p_el.find("svg") or p_el.find("i", class_=re.compile(r"icon", re.I))
                if injury_indicator or icon_el:
                    status = "OUT"
                    indicator_text = injury_indicator.get_text(strip=True) if injury_indicator else ""
                    if "doubt" in indicator_text.lower() or "question" in indicator_text.lower():
                        status = "DOUBTFUL"
                    results.append({
                        "team": "",  # context-dependent
                        "source_domain": "flashscore.com",
                        "stat_type": "injury",
                        "enrichments": {
                            "player": p_name,
                            "status": status,
                        },
                    })

        return results


class TotalCornerProfile(ExtractionProfile):
    """TotalCorner — extract dangerous attacks, half-time corners, card counts.

    TotalCorner HTML contains much richer data than the adapter extracts:
    - Dangerous attack counts per team
    - Half-time corner counts
    - Yellow/red card counts embedded in team cells
    - Multiple bookmaker corner handicap lines
    """
    domain = "totalcorner.com"
    sport_filter = "football"

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        results = []

        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 7:
                continue

            home_td = tr.find("td", class_="match_home")
            away_td = tr.find("td", class_="match_away")

            if not home_td or not away_td:
                continue

            home_link = home_td.find("a")
            away_link = away_td.find("a")
            home = (home_link.get_text(strip=True) if home_link
                    else home_td.get_text(strip=True))
            away = (away_link.get_text(strip=True) if away_link
                    else away_td.get_text(strip=True))

            # Clean ranking brackets
            home = re.sub(r"\[\d+\]", "", home).strip()
            away = re.sub(r"\[\d+\]", "", away).strip()

            if not home or not away:
                continue

            enrichment = {
                "home": home,
                "away": away,
                "source_domain": "totalcorner.com",
                "enrichments": {},
            }

            # Extract yellow/red card counts from team cells
            # Format: team name + card icons or spans with counts
            for label, td in [("home", home_td), ("away", away_td)]:
                yellow_spans = td.find_all("span", class_=re.compile(r"yellow", re.I))
                red_spans = td.find_all("span", class_=re.compile(r"red", re.I))
                if yellow_spans:
                    for s in yellow_spans:
                        txt = s.get_text(strip=True)
                        if txt.isdigit():
                            enrichment["enrichments"][f"yellow_cards_{label}"] = int(txt)
                if red_spans:
                    for s in red_spans:
                        txt = s.get_text(strip=True)
                        if txt.isdigit():
                            enrichment["enrichments"][f"red_cards_{label}"] = int(txt)

            # Extract dangerous attacks — look for cells with DA data
            # TotalCorner shows DA as colored bars or numbers
            for td in tds:
                td_class = " ".join(td.get("class", []))
                td_text = td.get_text(strip=True)
                # Dangerous attack indicators
                if "attack" in td_class.lower() or "danger" in td_class.lower():
                    m = re.match(r"(\d+)\s*[-:]\s*(\d+)", td_text)
                    if m:
                        enrichment["enrichments"]["dangerous_attacks_home"] = int(m.group(1))
                        enrichment["enrichments"]["dangerous_attacks_away"] = int(m.group(2))

            # Extract all corner-related cells more deeply
            corner_cells = []
            for td in tds:
                txt = td.get_text(strip=True)
                # Pattern: corner count "5 - 3(4-2)" has FT and HT parts
                m = re.match(r"(\d+)\s*-\s*(\d+)\s*\((\d+)\s*-\s*(\d+)\)", txt)
                if m:
                    enrichment["enrichments"]["corners_ft_home"] = int(m.group(1))
                    enrichment["enrichments"]["corners_ft_away"] = int(m.group(2))
                    enrichment["enrichments"]["corners_ht_home"] = int(m.group(3))
                    enrichment["enrichments"]["corners_ht_away"] = int(m.group(4))
                    break

            # Extract league position from team cells (e.g., [3] or [12])
            for label, td in [("home", home_td), ("away", away_td)]:
                full_text = td.get_text(strip=True)
                pos_match = re.search(r"\[(\d+)\]", full_text)
                if pos_match:
                    enrichment["enrichments"][f"league_position_{label}"] = int(pos_match.group(1))

            if enrichment["enrichments"]:
                results.append(enrichment)

        return results


class SoccerStatsProfile(ExtractionProfile):
    """SoccerStats — extract per-team/league averages from legacy HTML tables.

    SoccerStats uses old-school <tr class="trow1|trow2"> rows with positional columns.
    No th elements, no data attributes. Stats are identified by table context
    (nearby bold/strong text) and column position.
    """
    domain = "soccerstats.com"
    sport_filter = "football"

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        results = []

        # Strategy 1: Parse alternating data rows (trow1/trow2)
        for row in soup.find_all("tr", class_=re.compile(r"^trow[12]$")):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            # Find the team name — usually a cell with a link or just text >3 chars
            team_name = ""
            team_cell_idx = -1
            for idx, cell in enumerate(cells):
                link = cell.find("a")
                if link:
                    name = link.get_text(strip=True)
                    if name and len(name) > 2 and not name.isdigit():
                        team_name = name
                        team_cell_idx = idx
                        break
                else:
                    txt = cell.get_text(strip=True)
                    if txt and len(txt) > 2 and not txt.isdigit() and not re.match(r"^[\d.]+$", txt):
                        team_name = txt
                        team_cell_idx = idx
                        break

            if not team_name:
                continue

            # Extract all numeric values from the remaining cells
            stats = {}
            for idx, cell in enumerate(cells):
                if idx == team_cell_idx:
                    continue
                txt = cell.get_text(strip=True)
                # Try title attribute (some cells have descriptive titles)
                title = cell.get("title", "")
                try:
                    val = float(txt)
                    key = f"col_{idx}"
                    if title:
                        # Use title as stat name
                        title_clean = re.sub(r'[^a-zA-Z0-9_]', '_', title.lower())[:30]
                        key = title_clean
                    stats[key] = val
                except ValueError:
                    if txt and len(txt) < 20 and txt != team_name:
                        stats[f"col_{idx}"] = txt

            if stats:
                results.append({
                    "team": team_name,
                    "source_domain": "soccerstats.com",
                    "stat_type": "league_stats",
                    "enrichments": stats,
                })

        # Strategy 2: Parse league links for navigation context
        for link in soup.find_all("a", href=re.compile(r"latest\.asp\?league=")):
            league_name = link.get_text(strip=True)
            if league_name and len(league_name) > 3:
                results.append({
                    "team": league_name,
                    "source_domain": "soccerstats.com",
                    "stat_type": "league_link",
                    "enrichments": {
                        "league": league_name,
                        "url": link.get("href", ""),
                    },
                })

        # Strategy 3: Title-attribute cells (original approach, kept as fallback)
        for cell in soup.find_all("td", title=re.compile(
            r"corner|card|foul|goal|shot|over|under", re.I
        )):
            title = cell.get("title", "")
            text = cell.get_text(strip=True)
            row = cell.find_parent("tr")
            if not row:
                continue

            row_cells = row.find_all("td")
            team_name = None
            for rc in row_cells:
                rc_text = rc.get_text(strip=True)
                if rc_text and len(rc_text) > 2 and not re.match(r"^\d", rc_text) and rc != cell:
                    team_name = rc_text
                    break

            if team_name and text:
                results.append({
                    "team": team_name,
                    "source_domain": "soccerstats.com",
                    "stat_type": "team_average",
                    "enrichments": {"stat_title": title, "stat_value": text},
                })

        return results


class ForebetProfile(ExtractionProfile):
    """Forebet — ensure avg_stat, correct_score predictions, and all probabilities extracted.

    Forebet pages contain per-match prediction data that is partially parsed by the adapter.
    Deep parsing recovers: avg_goals/games/sets, correct score prediction, weather conditions,
    and BTTS/Over-Under probabilities.
    """
    domain = "forebet.com"

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        results = []

        # Find all match prediction rows via the tnmscn links
        for link in soup.find_all("a", class_="tnmscn"):
            home_el = link.find("span", class_="homeTeam")
            away_el = link.find("span", class_="awayTeam")

            if not home_el or not away_el:
                continue

            home = home_el.get_text(strip=True)
            away = away_el.get_text(strip=True)

            if not home or not away:
                continue

            # Walk up to row container
            row = link.parent
            if row:
                row = row.parent
            if row:
                row = row.parent

            enrichment = {
                "home": home,
                "away": away,
                "source_domain": "forebet.com",
                "enrichments": {},
            }

            if row:
                # Extract avg stat (avg goals/games/sets)
                avg_el = row.find("div", class_="avg_sc")
                if avg_el:
                    avg_text = avg_el.get_text(strip=True)
                    try:
                        enrichment["enrichments"]["avg_stat"] = float(avg_text)
                    except ValueError:
                        enrichment["enrichments"]["avg_stat_raw"] = avg_text

                # Extract predicted score
                score_el = row.find("div", class_="ex_sc")
                if score_el:
                    score_spans = score_el.find_all("span")
                    score_text = score_el.get_text(strip=True)
                    enrichment["enrichments"]["predicted_score"] = score_text

                # Extract probability spans more thoroughly
                fprc_el = row.find("div", class_=re.compile(r"fprc"))
                if fprc_el:
                    spans = fprc_el.find_all("span", recursive=True)
                    prob_values = []
                    for s in spans:
                        txt = s.get_text(strip=True)
                        if txt and txt.replace("%", "").isdigit():
                            prob_values.append(int(txt.replace("%", "")))
                    if len(prob_values) == 3:
                        enrichment["enrichments"]["prob_home"] = prob_values[0]
                        enrichment["enrichments"]["prob_draw"] = prob_values[1]
                        enrichment["enrichments"]["prob_away"] = prob_values[2]
                    elif len(prob_values) == 2:
                        enrichment["enrichments"]["prob_home"] = prob_values[0]
                        enrichment["enrichments"]["prob_away"] = prob_values[1]

                # Extract BTTS prediction
                btts_el = row.find("div", class_=re.compile(r"btts|both", re.I))
                if btts_el:
                    enrichment["enrichments"]["btts_prediction"] = btts_el.get_text(strip=True)

                # Extract Over/Under prediction
                ou_el = row.find("div", class_=re.compile(r"ou_|over_under", re.I))
                if ou_el:
                    enrichment["enrichments"]["over_under_prediction"] = ou_el.get_text(strip=True)

                # Extract weather if present
                weather_el = row.find("div", class_=re.compile(r"weather", re.I))
                if weather_el:
                    enrichment["enrichments"]["weather"] = weather_el.get_text(strip=True)

            if enrichment["enrichments"]:
                results.append(enrichment)

        return results


class BetExplorerProfile(ExtractionProfile):
    """BetExplorer — extract structured odds from table-main rows.

    BetExplorer uses <table class="table-main"> with plain <tr> rows (no class).
    Tournament context comes from <tr class="js-tournament"> header rows.
    Odds are in <td class="table-main__odds"> with <button> text content.
    """
    domain = "betexplorer.com"

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        results = []
        current_league = ""
        current_country = ""

        for table in soup.find_all("table", class_=re.compile(r"table-main")):
            for row in table.find_all("tr"):
                # Tournament header row
                if "js-tournament" in " ".join(row.get("class", [])):
                    tourn_link = row.find("a", class_=re.compile(r"table-main__tournament"))
                    if tourn_link:
                        # Country from flag image
                        img = tourn_link.find("img")
                        if img:
                            current_country = img.get("alt", "")
                        current_league = tourn_link.get_text(strip=True)
                        # Remove country prefix if duplicated
                        if current_country and current_league.startswith(current_country + ":"):
                            current_league = current_league[len(current_country)+1:].strip()
                    continue

                # Match data row — find the team link cell
                team_cell = row.find("td", class_=re.compile(r"h-text-left"))
                if not team_cell:
                    continue

                # Time
                time_span = team_cell.find("span", class_=re.compile(r"table-main__time"))
                match_time = time_span.get_text(strip=True) if time_span else ""

                # Teams from link text: "Home - Away"
                team_link = team_cell.find("a", href=True)
                if not team_link:
                    continue
                team_text = team_link.get_text(strip=True)
                parts = re.split(r"\s*[-–—]\s*", team_text, maxsplit=1)
                if len(parts) != 2:
                    continue
                home, away = parts[0].strip(), parts[1].strip()
                if not home or not away:
                    continue

                enrichment = {
                    "home": home,
                    "away": away,
                    "source_domain": "betexplorer.com",
                    "enrichments": {},
                }

                if current_league:
                    enrichment["enrichments"]["league"] = current_league
                if current_country:
                    enrichment["enrichments"]["country"] = current_country
                if match_time:
                    enrichment["enrichments"]["time"] = match_time

                # Match URL for detail page
                href = team_link.get("href", "")
                if href:
                    enrichment["enrichments"]["match_url"] = href

                # Odds from button elements inside table-main__odds cells
                odds_cells = row.find_all("td", class_=re.compile(r"table-main__odds"))
                odds_keys = ["odds_1", "odds_x", "odds_2"]
                for i, cell in enumerate(odds_cells):
                    btn = cell.find("button")
                    if btn:
                        try:
                            val = float(btn.get_text(strip=True))
                            if i < len(odds_keys):
                                enrichment["enrichments"][odds_keys[i]] = val
                        except ValueError:
                            pass
                    # Also check data-oid attribute
                    oid = cell.get("data-oid", "")
                    if oid and i < len(odds_keys):
                        enrichment["enrichments"][f"{odds_keys[i]}_oid"] = oid

                # Result cells if available
                result_cell = row.find("td", class_=re.compile(r"table-main__result"))
                if result_cell:
                    enrichment["enrichments"]["result"] = result_cell.get_text(strip=True)

                partial_cell = row.find("td", class_=re.compile(r"table-main__partial"))
                if partial_cell:
                    enrichment["enrichments"]["partial_scores"] = partial_cell.get_text(strip=True)

                if enrichment["enrichments"]:
                    results.append(enrichment)

        return results


class CoversProfile(ExtractionProfile):
    """Covers — US sports odds/matchups. Note: most saved HTML is homepage-only.
    For actual match pages, parse structured sections from sport subpages."""
    domain = "covers.com"

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        results = []

        # Covers sport pages use covers-MatchupCard or covers-GameCard
        for card in soup.find_all(True, class_=re.compile(
                r"MatchupCard|GameCard|covers-ScoreboardCard", re.I)):
            teams = card.find_all(True, class_=re.compile(r"team-name|teamName", re.I))
            if len(teams) < 2:
                continue

            home = teams[1].get_text(strip=True)  # home is usually second
            away = teams[0].get_text(strip=True)

            if not home or not away or len(home) < 2:
                continue

            enrichment = {
                "home": home, "away": away,
                "source_domain": "covers.com",
                "enrichments": {},
            }

            # Odds from odds containers
            for el in card.find_all(True, class_=re.compile(r"odds|line|spread|total", re.I)):
                val = el.get_text(strip=True)
                cls = " ".join(el.get("class", [])).lower()
                if val and len(val) < 25:
                    if "spread" in cls:
                        enrichment["enrichments"]["spread"] = val
                    elif "total" in cls or "over" in cls:
                        enrichment["enrichments"]["total_line"] = val
                    elif "money" in cls:
                        enrichment["enrichments"]["moneyline"] = val

            if enrichment["enrichments"]:
                results.append(enrichment)

        # Fallback: parse any table rows with team data
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue
                # Look for team links
                link = row.find("a", href=re.compile(r"/teams/|/matchups/"))
                if link:
                    team_name = link.get_text(strip=True)
                    if team_name and len(team_name) > 2:
                        # Try to extract numeric stats from other cells
                        stats = {}
                        for i, cell in enumerate(cells[1:], 1):
                            txt = cell.get_text(strip=True)
                            try:
                                stats[f"col_{i}"] = float(txt)
                            except ValueError:
                                if txt:
                                    stats[f"col_{i}"] = txt
                        if stats:
                            results.append({
                                "team": team_name,
                                "source_domain": "covers.com",
                                "enrichments": stats,
                            })

        return results


class BasketballReferenceProfile(ExtractionProfile):
    """Basketball-Reference — extract deep stats from data-stat attributes."""
    domain = "basketball-reference.com"
    sport_filter = "basketball"

    # NBA abbreviation → full team name for DB matching
    _ABBREV = {
        "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BRK": "Brooklyn Nets",
        "CHI": "Chicago Bulls", "CHO": "Charlotte Hornets", "CLE": "Cleveland Cavaliers",
        "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets", "DET": "Detroit Pistons",
        "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
        "LAC": "Los Angeles Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies",
        "MIA": "Miami Heat", "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves",
        "NOP": "New Orleans Pelicans", "NYK": "New York Knicks", "OKC": "Oklahoma City Thunder",
        "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHO": "Phoenix Suns",
        "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs",
        "TOR": "Toronto Raptors", "UTA": "Utah Jazz", "WAS": "Washington Wizards",
    }

    @staticmethod
    def _clean_team(raw: str) -> str:
        """Strip seed/playoff markers: 'DET*(1)' → 'Detroit Pistons', 'East' → skip."""
        import re
        cleaned = re.sub(r'\*|\(\d+\)', '', raw).strip()
        if not cleaned or cleaned.lower() in ("east", "west", "eastern", "western",
                                               "atlantic", "central", "southeast",
                                               "northwest", "pacific", "southwest"):
            return ""
        return BasketballReferenceProfile._ABBREV.get(cleaned, cleaned)

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        results = []

        for table in soup.find_all("table"):
            table_id = table.get("id", "")

            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                row_data = {}
                team_name = None

                for cell in cells:
                    stat = cell.get("data-stat", "")
                    val = cell.get_text(strip=True)
                    if stat and val:
                        row_data[stat] = val
                        if stat in ("team_name", "team_id"):
                            team_name = val

                if not team_name:
                    link = row.find("a")
                    if link:
                        team_name = link.get_text(strip=True)

                if team_name:
                    team_name = self._clean_team(team_name)

                if team_name and len(row_data) > 2:
                    enrichment = {
                        "team": team_name,
                        "source_domain": "basketball-reference.com",
                        "stat_type": "season_stats",
                        "enrichments": {
                            "table_id": table_id,
                            "stats": row_data,
                        },
                    }
                    results.append(enrichment)

        return results


class HockeyReferenceProfile(ExtractionProfile):
    """Hockey-Reference — extract deep stats from data-stat attributes."""
    domain = "hockey-reference.com"
    sport_filter = "hockey"

    _ABBREV = {
        "ANA": "Anaheim Ducks", "ARI": "Arizona Coyotes", "BOS": "Boston Bruins",
        "BUF": "Buffalo Sabres", "CAR": "Carolina Hurricanes", "CBJ": "Columbus Blue Jackets",
        "CGY": "Calgary Flames", "CHI": "Chicago Blackhawks", "COL": "Colorado Avalanche",
        "DAL": "Dallas Stars", "DET": "Detroit Red Wings", "EDM": "Edmonton Oilers",
        "FLA": "Florida Panthers", "LAK": "Los Angeles Kings", "MIN": "Minnesota Wild",
        "MTL": "Montreal Canadiens", "NJD": "New Jersey Devils", "NSH": "Nashville Predators",
        "NYI": "New York Islanders", "NYR": "New York Rangers", "OTT": "Ottawa Senators",
        "PHI": "Philadelphia Flyers", "PIT": "Pittsburgh Penguins", "SEA": "Seattle Kraken",
        "SJS": "San Jose Sharks", "STL": "St. Louis Blues", "TBL": "Tampa Bay Lightning",
        "TOR": "Toronto Maple Leafs", "UTA": "Utah Hockey Club", "VAN": "Vancouver Canucks",
        "VEG": "Vegas Golden Knights", "WPG": "Winnipeg Jets", "WSH": "Washington Capitals",
    }

    @staticmethod
    def _clean_team(raw: str) -> str:
        """Strip playoff markers: 'BUF*' → 'Buffalo Sabres'."""
        import re
        cleaned = re.sub(r'\*|\(\d+\)', '', raw).strip()
        if not cleaned or cleaned.lower() in ("east", "west", "eastern", "western",
                                               "atlantic", "metropolitan", "central",
                                               "pacific"):
            return ""
        return HockeyReferenceProfile._ABBREV.get(cleaned, cleaned)

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        results = []

        for table in soup.find_all("table"):
            table_id = table.get("id", "")

            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                row_data = {}
                team_name = None

                for cell in cells:
                    stat = cell.get("data-stat", "")
                    val = cell.get_text(strip=True)
                    if stat and val:
                        row_data[stat] = val
                        if stat in ("team_name", "team_id"):
                            team_name = val

                if not team_name:
                    link = row.find("a")
                    if link:
                        team_name = link.get_text(strip=True)

                if team_name:
                    team_name = self._clean_team(team_name)

                if team_name and len(row_data) > 2:
                    enrichment = {
                        "team": team_name,
                        "source_domain": "hockey-reference.com",
                        "stat_type": "season_stats",
                        "enrichments": {
                            "table_id": table_id,
                            "stats": row_data,
                        },
                    }
                    results.append(enrichment)

        return results


class HLTVProfile(ExtractionProfile):
    """HLTV — extract CS2 match details, player ratings, format info."""
    domain = "hltv.org"
    sport_filter = "esports"

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        results = []

        # HLTV match elements
        for match_el in soup.find_all(True, class_=re.compile(r"match|upcomingMatch", re.I)):
            teams = match_el.find_all(True, class_=re.compile(r"team", re.I))
            if len(teams) < 2:
                continue

            home = teams[0].get_text(strip=True)
            away = teams[1].get_text(strip=True)

            if not home or not away or len(home) < 2:
                continue

            enrichment = {
                "home": home,
                "away": away,
                "source_domain": "hltv.org",
                "enrichments": {},
            }

            # Extract format (BO1, BO3, BO5)
            format_el = match_el.find(True, class_=re.compile(r"bestof|format|matchMeta", re.I))
            if format_el:
                fmt_text = format_el.get_text(strip=True)
                if re.search(r"bo\d|best.of.\d", fmt_text, re.I):
                    enrichment["enrichments"]["format"] = fmt_text

            # Extract event/tournament name
            event_el = match_el.find(True, class_=re.compile(r"event|tournament", re.I))
            if event_el:
                enrichment["enrichments"]["tournament"] = event_el.get_text(strip=True)

            # Extract team rankings
            for i, team_el in enumerate(teams[:2]):
                rank_el = team_el.find(True, class_=re.compile(r"rank", re.I))
                if rank_el:
                    rank_text = rank_el.get_text(strip=True)
                    label = "home" if i == 0 else "away"
                    enrichment["enrichments"][f"rank_{label}"] = rank_text

            # Extract star ratings / match importance
            stars_el = match_el.find(True, class_=re.compile(r"star|importance", re.I))
            if stars_el:
                stars = len(stars_el.find_all(True, class_=re.compile(r"star", re.I)))
                if stars:
                    enrichment["enrichments"]["match_importance"] = stars

            if enrichment["enrichments"]:
                results.append(enrichment)

        return results


class BetclicProfile(ExtractionProfile):
    """Betclic — extract match names and odds from Angular HTML + JSON blocks.

    Betclic uses Angular with data-qa attributes and embeds JSON data in
    <script type="application/json"> blocks.
    """
    domain = "betclic.pl"

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        results = []

        # Strategy 1: Parse JSON data blocks
        for script in soup.find_all("script", type="application/json"):
            try:
                data = json.loads(script.string or "")
                self._extract_from_json(data, results)
            except (json.JSONDecodeError, TypeError):
                pass

        # Strategy 2: Parse scoreboard elements with data-qa
        for scoreboard in soup.find_all(True, class_=re.compile(r"scoreboard")):
            match_name_el = scoreboard.find(True, attrs={"data-qa": re.compile(r"match-name|event-name")})
            if not match_name_el:
                match_name_el = scoreboard.find("span", attrs={"data-qa": True})
            if not match_name_el:
                continue

            match_text = match_name_el.get_text(strip=True)
            if not match_text:
                continue

            enrichment = {
                "home": match_text,  # full match/league name
                "away": "",
                "source_domain": "betclic.pl",
                "enrichments": {"match_name": match_text},
            }

            # Try splitting into home-away
            parts = re.split(r"\s*[-–—vs.]+\s*", match_text, maxsplit=1)
            if len(parts) == 2:
                enrichment["home"] = parts[0].strip()
                enrichment["away"] = parts[1].strip()

            # Date/time from scoreboard
            date_el = scoreboard.find(True, class_=re.compile(r"scoreboard_date|date"))
            if date_el:
                enrichment["enrichments"]["date"] = date_el.get_text(strip=True)

            results.append(enrichment)

        # Strategy 3: Parse event cards
        for event in soup.find_all(True, class_=re.compile(r"cardEvent|eventCard")):
            # Find participant names
            participants = event.find_all(True, class_=re.compile(r"participant|competitor|team"))
            if len(participants) >= 2:
                home = participants[0].get_text(strip=True)
                away = participants[1].get_text(strip=True)
                if home and away:
                    enrichment = {
                        "home": home, "away": away,
                        "source_domain": "betclic.pl",
                        "enrichments": {},
                    }
                    # Look for odds within the card
                    for odds_el in event.find_all(True, class_=re.compile(r"oddValue|odd_value|rate")):
                        val = odds_el.get_text(strip=True).replace(",", ".")
                        try:
                            enrichment["enrichments"].setdefault("odds", []).append(float(val))
                        except ValueError:
                            pass
                    if enrichment["enrichments"] or (home and away):
                        results.append(enrichment)

        return results

    def _extract_from_json(self, data: object, results: list) -> None:
        """Recursively extract match/event data from JSON blobs."""
        if isinstance(data, dict):
            # Look for event-like objects
            has_name = "name" in data or "label" in data or "matchName" in data
            has_odds = "odds" in data or "selections" in data or "markets" in data
            if has_name:
                name = data.get("name") or data.get("label") or data.get("matchName") or ""
                if isinstance(name, str) and len(name) > 3:
                    enrichment = {
                        "home": name, "away": "",
                        "source_domain": "betclic.pl",
                        "enrichments": {"event_name": name},
                    }
                    parts = re.split(r"\s*[-–—vs.]+\s*", name, maxsplit=1)
                    if len(parts) == 2:
                        enrichment["home"] = parts[0].strip()
                        enrichment["away"] = parts[1].strip()

                    # Extract odds
                    if has_odds:
                        odds_data = data.get("odds") or data.get("selections") or []
                        if isinstance(odds_data, list):
                            for od in odds_data[:3]:
                                if isinstance(od, dict):
                                    val = od.get("odds") or od.get("value") or od.get("price")
                                    if val:
                                        try:
                                            enrichment["enrichments"].setdefault("odds", []).append(float(str(val).replace(",", ".")))
                                        except ValueError:
                                            pass

                    if enrichment["home"]:
                        results.append(enrichment)

            for v in data.values():
                self._extract_from_json(v, results)
        elif isinstance(data, list):
            for item in data:
                self._extract_from_json(item, results)


class TennisExplorerProfile(ExtractionProfile):
    """TennisExplorer — extract match data from paired rows (sN + sNb).

    HTML structure: table with alternating tr.one/tr.two. Match rows come in pairs:
    - Player 1 row: <tr id="s0" class="one fRow"> with td.first.time, td.t-name, td.result, td.score, td.course
    - Player 2 row: <tr id="s0b" class="one"> (shares rowspan cells)
    Tournament headers: <tr class="head"> with td.t-name colspan
    """
    domain = "tennisexplorer.com"
    sport_filter = "tennis"

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        results = []

        # Find the main results table
        for table in soup.find_all("table", class_=re.compile(r"result")):
            current_tournament = ""
            rows = table.find_all("tr")
            i = 0
            while i < len(rows):
                row = rows[i]
                row_classes = " ".join(row.get("class", []))

                # Tournament header
                if "head" in row_classes:
                    name_cell = row.find("td", class_="t-name")
                    if name_cell:
                        current_tournament = name_cell.get_text(strip=True)
                    i += 1
                    continue

                # Player 1 row (has time cell with rowspan)
                row_id = row.get("id", "")
                if not row_id or row_id.endswith("b"):
                    i += 1
                    continue

                # Check for fRow marker or time cell
                time_cell = row.find("td", class_=re.compile(r"time|first"))
                if not time_cell:
                    i += 1
                    continue

                # Player 1 name
                p1_cell = row.find("td", class_="t-name")
                if not p1_cell:
                    i += 1
                    continue
                p1_link = p1_cell.find("a")
                player1 = p1_link.get_text(strip=True) if p1_link else p1_cell.get_text(strip=True)

                # Player 1 country
                p1_flag = p1_cell.find("span", class_=re.compile(r"^fl\b"))
                p1_country = ""
                if p1_flag:
                    for cls in p1_flag.get("class", []):
                        if cls.startswith("fl-") and cls != "fl":
                            p1_country = cls[3:].upper()

                # Scores from player 1 row
                score_cells = row.find_all("td", class_="score")
                p1_scores = [c.get_text(strip=True) for c in score_cells]

                # Result
                result_cell = row.find("td", class_="result")
                p1_result = result_cell.get_text(strip=True) if result_cell else ""

                # Odds from course cells
                odds_cells = row.find_all("td", class_="course")
                odds = [c.get_text(strip=True) for c in odds_cells]

                # Match detail link
                detail_link = row.find("a", href=re.compile(r"match-detail"))
                match_id = ""
                if detail_link:
                    m = re.search(r"id=(\d+)", detail_link.get("href", ""))
                    if m:
                        match_id = m.group(1)

                match_time = time_cell.get_text(strip=True)

                # Player 2 row (next row with id ending in "b")
                player2 = ""
                p2_country = ""
                p2_scores = []
                if i + 1 < len(rows):
                    row2 = rows[i + 1]
                    row2_id = row2.get("id", "")
                    if row2_id == row_id + "b":
                        p2_cell = row2.find("td", class_="t-name")
                        if p2_cell:
                            p2_link = p2_cell.find("a")
                            player2 = p2_link.get_text(strip=True) if p2_link else p2_cell.get_text(strip=True)
                            p2_flag = p2_cell.find("span", class_=re.compile(r"^fl\b"))
                            if p2_flag:
                                for cls in p2_flag.get("class", []):
                                    if cls.startswith("fl-") and cls != "fl":
                                        p2_country = cls[3:].upper()
                        p2_score_cells = row2.find_all("td", class_="score")
                        p2_scores = [c.get_text(strip=True) for c in p2_score_cells]
                        i += 1  # skip player 2 row

                if not player1 or not player2:
                    i += 1
                    continue

                enrichment = {
                    "home": player1,
                    "away": player2,
                    "source_domain": "tennisexplorer.com",
                    "enrichments": {},
                }

                if current_tournament:
                    enrichment["enrichments"]["tournament"] = current_tournament
                if match_time:
                    enrichment["enrichments"]["time"] = match_time
                if match_id:
                    enrichment["enrichments"]["match_id"] = match_id
                if p1_country:
                    enrichment["enrichments"]["country_home"] = p1_country
                if p2_country:
                    enrichment["enrichments"]["country_away"] = p2_country

                # Set scores
                if p1_scores:
                    enrichment["enrichments"]["scores_home"] = p1_scores
                if p2_scores:
                    enrichment["enrichments"]["scores_away"] = p2_scores
                if p1_result:
                    enrichment["enrichments"]["sets_won_home"] = p1_result

                # Odds
                if odds:
                    try:
                        if len(odds) >= 1 and odds[0]:
                            enrichment["enrichments"]["odds_home"] = float(odds[0])
                        if len(odds) >= 2 and odds[1]:
                            enrichment["enrichments"]["odds_away"] = float(odds[1])
                    except ValueError:
                        pass

                # Surface detection from tournament name or page context
                for surface in ["Hard", "Clay", "Grass", "Carpet"]:
                    if surface.lower() in current_tournament.lower():
                        enrichment["enrichments"]["surface"] = surface
                        break

                results.append(enrichment)
                i += 1

        return results


# ============================================================================
# NEW PROFILES — Added for missing domains
# ============================================================================

class SofascoreProfile(ExtractionProfile):
    """Sofascore — extract structured data from __NEXT_DATA__ JSON blob."""
    domain = "sofascore.com"

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        results = []

        # Primary: parse __NEXT_DATA__ JSON
        next_data = soup.find("script", id="__NEXT_DATA__", type="application/json")
        if next_data and next_data.string:
            try:
                data = json.loads(next_data.string)
                self._walk_json(data, results)
            except (json.JSONDecodeError, TypeError):
                pass

        return results

    def _walk_json(self, data: object, results: list, depth: int = 0) -> None:
        if depth > 15:
            return
        if isinstance(data, dict):
            # Look for event objects (have homeTeam/awayTeam)
            home_team = data.get("homeTeam", {})
            away_team = data.get("awayTeam", {})
            if isinstance(home_team, dict) and isinstance(away_team, dict):
                home_name = home_team.get("name", "")
                away_name = away_team.get("name", "")
                if home_name and away_name:
                    enrichment = {
                        "home": home_name, "away": away_name,
                        "source_domain": "sofascore.com",
                        "enrichments": {},
                    }
                    # Tournament info
                    tournament = data.get("tournament", {})
                    if isinstance(tournament, dict):
                        enrichment["enrichments"]["tournament"] = tournament.get("name", "")
                        cat = tournament.get("category", {})
                        if isinstance(cat, dict):
                            enrichment["enrichments"]["country"] = cat.get("name", "")
                    # Status
                    status = data.get("status", {})
                    if isinstance(status, dict):
                        enrichment["enrichments"]["status"] = status.get("description", "")
                    # Score
                    home_score = data.get("homeScore", {})
                    away_score = data.get("awayScore", {})
                    if isinstance(home_score, dict):
                        enrichment["enrichments"]["score_home"] = home_score.get("current", home_score.get("display"))
                    if isinstance(away_score, dict):
                        enrichment["enrichments"]["score_away"] = away_score.get("current", away_score.get("display"))
                    # Start time
                    if "startTimestamp" in data:
                        enrichment["enrichments"]["start_timestamp"] = data["startTimestamp"]
                    # Sofascore event ID
                    if "id" in data:
                        enrichment["enrichments"]["sofascore_id"] = data["id"]
                    results.append(enrichment)

            # Look for player objects (rankings pages)
            if "player" in data and isinstance(data.get("player"), dict):
                player = data["player"]
                name = player.get("name", "")
                if name:
                    enrichment = {
                        "team": name,
                        "source_domain": "sofascore.com",
                        "enrichments": {},
                    }
                    if "ranking" in data:
                        enrichment["enrichments"]["ranking"] = data["ranking"]
                    if "points" in data:
                        enrichment["enrichments"]["points"] = data["points"]
                    if "team" in player and isinstance(player["team"], dict):
                        enrichment["enrichments"]["team_name"] = player["team"].get("name", "")
                    results.append(enrichment)

            for v in data.values():
                self._walk_json(v, results, depth + 1)
        elif isinstance(data, list):
            for item in data:
                self._walk_json(item, results, depth + 1)


class OddsPortalProfile(ExtractionProfile):
    """OddsPortal — extract event data from Vue.js SSR with data-testid attributes."""
    domain = "oddsportal.com"

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        results = []
        current_league = ""

        # League headers
        for league_el in soup.find_all(True, attrs={"data-testid": "sport-country-league-item"}):
            league_text = league_el.get_text(strip=True)
            if league_text:
                current_league = league_text

        # Event rows
        for event_row in soup.find_all("div", class_=re.compile(r"eventRow")):
            # Extract text content — team names are in the row
            text = event_row.get_text(" | ", strip=True)
            if not text or len(text) < 5:
                continue

            enrichment = {
                "home": text[:80],  # truncate for safety
                "away": "",
                "source_domain": "oddsportal.com",
                "enrichments": {},
            }

            if current_league:
                enrichment["enrichments"]["league"] = current_league

            # Event ID from id attribute
            row_id = event_row.get("id", "")
            if row_id:
                enrichment["enrichments"]["event_id"] = row_id

            # Set attribute
            set_val = event_row.get("set", "")
            if set_val:
                enrichment["enrichments"]["set_id"] = set_val

            # Try to parse team names from links within the row
            links = event_row.find_all("a", href=True)
            for link in links:
                href = link.get("href", "")
                if re.search(r"/[a-z]+-[a-z]+/[a-z]+-[a-z]+/", href):
                    link_text = link.get_text(strip=True)
                    parts = re.split(r"\s*[-–—vs.]+\s*", link_text, maxsplit=1)
                    if len(parts) == 2 and len(parts[0]) > 1 and len(parts[1]) > 1:
                        enrichment["home"] = parts[0].strip()
                        enrichment["away"] = parts[1].strip()
                        break

            results.append(enrichment)

        return results


class Scores24Profile(ExtractionProfile):
    """Scores24 — extract data from React Query dehydrated state."""
    domain = "scores24.live"

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        results = []

        # Strategy 1: Parse window.__REACT_QUERY_STATE__
        for script in soup.find_all("script"):
            if not script.string:
                continue
            for pattern in [r'__REACT_QUERY_STATE__\s*=\s*JSON\.parse\("(.+?)"\)',
                            r'__URQL__PREFETCH__\s*=\s*JSON\.parse\("(.+?)"\)']:
                m = re.search(pattern, script.string)
                if m:
                    try:
                        raw = m.group(1).encode().decode('unicode_escape')
                        data = json.loads(raw)
                        self._walk_json(data, results)
                    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
                        pass

        # Strategy 2: Parse data-testid elements
        for el in soup.find_all(True, attrs={"data-testid": True}):
            testid = el.get("data-testid", "")
            if "match" in testid.lower() or "event" in testid.lower():
                text = el.get_text(strip=True)
                if text and len(text) > 3:
                    results.append({
                        "home": text[:80],
                        "away": "",
                        "source_domain": "scores24.live",
                        "enrichments": {"testid": testid, "raw_text": text[:200]},
                    })

        return results

    def _walk_json(self, data: object, results: list, depth: int = 0) -> None:
        if depth > 12:
            return
        if isinstance(data, dict):
            # Look for sport event patterns
            home = data.get("homeTeam") or data.get("home_team") or data.get("team1")
            away = data.get("awayTeam") or data.get("away_team") or data.get("team2")
            if isinstance(home, dict) and isinstance(away, dict):
                h_name = home.get("name", "")
                a_name = away.get("name", "")
                if h_name and a_name:
                    results.append({
                        "home": h_name, "away": a_name,
                        "source_domain": "scores24.live",
                        "enrichments": {
                            "sport": data.get("sport", {}).get("slug", "") if isinstance(data.get("sport"), dict) else "",
                            "status": data.get("status", ""),
                        },
                    })
            for v in data.values():
                self._walk_json(v, results, depth + 1)
        elif isinstance(data, list):
            for item in data:
                self._walk_json(item, results, depth + 1)


class WhoScoredProfile(ExtractionProfile):
    """WhoScored — extract match previews from table.grid and Hypernova JSON."""
    domain = "whoscored.com"
    sport_filter = "football"

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        results = []
        current_league = ""
        current_date = ""

        # Strategy 1: Parse table.grid for match previews
        for table in soup.find_all("table", class_="grid"):
            for row in table.find_all("tr"):
                # Date header
                date_cell = row.find("td", class_="previews-date")
                if date_cell:
                    current_date = date_cell.get_text(strip=True)
                    continue

                # League row
                league_link = row.find("a", class_=re.compile(r"level-2"))
                if league_link:
                    current_league = league_link.get_text(strip=True)
                    # Country from flag span
                    flag = league_link.find("span", class_=re.compile(r"country"))
                    country = flag.get("title", "") if flag else ""
                    if country:
                        current_league = f"{country}: {current_league}"
                    continue

                # Match row
                time_cell = row.find("td", class_="time")
                match_link = row.find("a", href=re.compile(r"/matches/\d+/preview/"))
                if match_link:
                    match_text = match_link.get_text(strip=True)
                    parts = re.split(r"\s+vs\s+", match_text, maxsplit=1)
                    if len(parts) != 2:
                        parts = re.split(r"\s*[-–—]\s*", match_text, maxsplit=1)
                    if len(parts) == 2:
                        home, away = parts[0].strip(), parts[1].strip()
                        # Match ID from URL
                        m = re.search(r"/matches/(\d+)/", match_link.get("href", ""))
                        match_id = m.group(1) if m else ""

                        enrichment = {
                            "home": home, "away": away,
                            "source_domain": "whoscored.com",
                            "enrichments": {},
                        }
                        if current_league:
                            enrichment["enrichments"]["league"] = current_league
                        if current_date:
                            enrichment["enrichments"]["date"] = current_date
                        if time_cell:
                            enrichment["enrichments"]["time"] = time_cell.get_text(strip=True)
                        if match_id:
                            enrichment["enrichments"]["whoscored_id"] = match_id
                        results.append(enrichment)

        # Strategy 2: Parse Hypernova JSON blocks
        for script in soup.find_all("script", attrs={"data-hypernova-key": True}):
            key = script.get("data-hypernova-key", "")
            if script.string:
                # Hypernova wraps JSON in HTML comments: <!--{...}-->
                content = script.string.strip()
                if content.startswith("<!--") and content.endswith("-->"):
                    content = content[4:-3]
                try:
                    data = json.loads(content)
                    # Look for match data in the JSON
                    if isinstance(data, dict):
                        for v in data.values():
                            if isinstance(v, list):
                                for item in v:
                                    if isinstance(item, dict) and "home" in item and "away" in item:
                                        results.append({
                                            "home": str(item["home"]),
                                            "away": str(item["away"]),
                                            "source_domain": "whoscored.com",
                                            "enrichments": {"hypernova_key": key, "data": item},
                                        })
                except (json.JSONDecodeError, TypeError):
                    pass

        return results


class CueTrackerProfile(ExtractionProfile):
    """CueTracker — extract snooker tournament info and player data."""
    domain = "cuetracker.net"
    sport_filter = "snooker"

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        results = []

        # Extract current tournament info
        for table in soup.find_all("table", class_=re.compile(r"table-small|table")):
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                # Tournament links
                for cell in cells:
                    link = cell.find("a", href=re.compile(r"/tournaments/"))
                    if link:
                        tournament_name = link.get_text(strip=True)
                        if tournament_name:
                            enrichment = {
                                "team": tournament_name,
                                "source_domain": "cuetracker.net",
                                "stat_type": "tournament",
                                "enrichments": {
                                    "tournament": tournament_name,
                                    "url": link.get("href", ""),
                                },
                            }
                            # Country from flag
                            flag = cell.find("img", class_=re.compile(r"flag"))
                            if flag:
                                for cls in flag.get("class", []):
                                    if cls.startswith("flag-") and cls != "flag":
                                        enrichment["enrichments"]["country"] = cls[5:]
                            results.append(enrichment)

                    # Player links
                    player_link = cell.find("a", href=re.compile(r"/players/"))
                    if player_link:
                        player_name = player_link.get_text(strip=True)
                        if player_name and len(player_name) > 2:
                            results.append({
                                "team": player_name,
                                "source_domain": "cuetracker.net",
                                "stat_type": "player",
                                "enrichments": {
                                    "player": player_name,
                                    "url": player_link.get("href", ""),
                                },
                            })

        # Extract match results from table rows
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            for row in rows:
                links = row.find_all("a", href=re.compile(r"/players/"))
                if len(links) >= 2:
                    p1 = links[0].get_text(strip=True)
                    p2 = links[1].get_text(strip=True)
                    if p1 and p2:
                        enrichment = {
                            "home": p1, "away": p2,
                            "source_domain": "cuetracker.net",
                            "enrichments": {},
                        }
                        # Score from cells
                        cells = row.find_all("td")
                        for cell in cells:
                            txt = cell.get_text(strip=True)
                            m = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", txt)
                            if m:
                                enrichment["enrichments"]["score"] = txt
                        results.append(enrichment)

        return results


class DartsOrakelProfile(ExtractionProfile):
    """DartsOrakel — extract match results, player averages, and predictions."""
    domain = "dartsorakel.com"
    sport_filter = "darts"

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        results = []

        # Parse #latest-results-table
        table = soup.find("table", id="latest-results-table")
        if not table:
            # Fallback: any DataTable with darts data
            table = soup.find("table", class_=re.compile(r"dataTable|new-design-table"))

        if table:
            for row in table.find_all("tr", class_=re.compile(r"odd|even|cursor")):
                cells = row.find_all("td", class_=re.compile(r"new-design-table-data|"))
                if not cells:
                    cells = row.find_all("td")
                if len(cells) < 3:
                    continue

                # Players from links
                player_links = row.find_all("a", class_=re.compile(r"player-name"))
                if not player_links:
                    player_links = row.find_all("a", href=re.compile(r"/player/details/"))

                players = [l.get_text(strip=True) for l in player_links if l.get_text(strip=True)]

                # Averages from span.player-avg
                averages = []
                for span in row.find_all("span", class_=re.compile(r"player-avg")):
                    txt = span.get_text(strip=True).strip("()")
                    try:
                        averages.append(float(txt))
                    except ValueError:
                        pass

                if len(players) >= 2:
                    enrichment = {
                        "home": players[0], "away": players[1],
                        "source_domain": "dartsorakel.com",
                        "enrichments": {},
                    }
                    if len(averages) >= 1:
                        enrichment["enrichments"]["avg_home"] = averages[0]
                    if len(averages) >= 2:
                        enrichment["enrichments"]["avg_away"] = averages[1]

                    # Tournament from first cell
                    first_cell = cells[0].get_text(strip=True) if cells else ""
                    if first_cell and len(first_cell) > 2:
                        enrichment["enrichments"]["tournament"] = first_cell

                    # Date from second cell
                    if len(cells) > 1:
                        date_txt = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                        if re.match(r"\d{4}-\d{2}-\d{2}", date_txt):
                            enrichment["enrichments"]["date"] = date_txt

                    # Match URL from onclick
                    onclick = row.get("onclick", "")
                    m = re.search(r"match/stats/(\d+)", onclick)
                    if m:
                        enrichment["enrichments"]["match_id"] = m.group(1)

                    results.append(enrichment)
                elif len(players) == 1:
                    # Single player row (standings/rankings)
                    enrichment = {
                        "team": players[0],
                        "source_domain": "dartsorakel.com",
                        "stat_type": "player_stats",
                        "enrichments": {},
                    }
                    if averages:
                        enrichment["enrichments"]["avg"] = averages[0]
                    results.append(enrichment)

        return results


class SpeedwayProfile(ExtractionProfile):
    """SpeedwayEkstraliga — extract team and rider data from Next.js RSC payloads."""
    domain = "speedwayekstraliga.pl"
    sport_filter = "speedway"

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        results = []

        # Strategy 1: Parse JSON from Next.js RSC script payloads
        for script in soup.find_all("script"):
            if not script.string:
                continue
            # Look for team data in self.__next_f push calls
            for m in re.finditer(r'"label"\s*:\s*"([^"]+)"[^}]*"url"\s*:\s*"([^"]*druzyny[^"]*)"', script.string):
                team_name = m.group(1)
                team_url = m.group(2)
                if team_name and "druzyny" in team_url:
                    results.append({
                        "team": team_name,
                        "source_domain": "speedwayekstraliga.pl",
                        "stat_type": "team",
                        "enrichments": {"url": team_url, "team": team_name},
                    })

        # Strategy 2: Parse Tailwind tables
        for table in soup.find_all("table", class_=re.compile(r"w-full|table-auto")):
            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) < 3:
                    continue
                # Look for team/rider names
                link = row.find("a")
                name = link.get_text(strip=True) if link else ""
                if not name:
                    for cell in cells:
                        txt = cell.get_text(strip=True)
                        if txt and len(txt) > 2 and not txt.isdigit():
                            name = txt
                            break
                if name and len(name) > 2:
                    stats = {}
                    for idx, cell in enumerate(cells):
                        txt = cell.get_text(strip=True)
                        try:
                            stats[f"col_{idx}"] = float(txt)
                        except ValueError:
                            pass
                    if stats:
                        results.append({
                            "team": name,
                            "source_domain": "speedwayekstraliga.pl",
                            "enrichments": stats,
                        })

        return results


class GosuGamersProfile(ExtractionProfile):
    """GosuGamers — extract esports match data from URL patterns and MUI components."""
    domain = "gosugamers.net"
    sport_filter = "esports"

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        results = []

        # Parse match URLs: /{game}/tournaments/{id}/matches/{id}-{team1}-vs-{team2}
        for link in soup.find_all("a", href=re.compile(r"/matches/\d+-.*-vs-")):
            href = link.get("href", "")
            m = re.search(r"/(\w+)/tournaments/(\d+)-([^/]*)/matches/(\d+)-(.+)-vs-(.+?)(?:\?|$|#)", href)
            if m:
                game = m.group(1)
                tournament_id = m.group(2)
                tournament_slug = m.group(3).replace("-", " ").title()
                match_id = m.group(4)
                team1 = m.group(5).replace("-", " ").title()
                team2 = m.group(6).replace("-", " ").title()

                results.append({
                    "home": team1, "away": team2,
                    "source_domain": "gosugamers.net",
                    "enrichments": {
                        "game": game,
                        "tournament": tournament_slug,
                        "tournament_id": tournament_id,
                        "match_id": match_id,
                        "url": href,
                    },
                })

        return results


class TennisAbstractProfile(ExtractionProfile):
    """TennisAbstract — extract Elo ratings and player rankings from clean tables."""
    domain = "tennisabstract.com"
    sport_filter = "tennis"

    def extract(self, html: str, url: str, soup: BeautifulSoup) -> list[dict]:
        results = []

        # Main data table (jQuery tablesorter)
        table = soup.find("table", id="reportable")
        if not table:
            table = soup.find("table", class_=re.compile(r"tablesorter"))

        if table:
            # Get column headers
            headers = []
            header_row = table.find("thead")
            if header_row:
                for th in header_row.find_all("th"):
                    headers.append(th.get_text(strip=True).lower())

            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue

                # Player name from link
                player_link = row.find("a", href=re.compile(r"/cgi-bin/[w]?player\.cgi"))
                if not player_link:
                    player_link = row.find("a")

                player_name = player_link.get_text(strip=True) if player_link else ""
                if not player_name:
                    player_name = cells[0].get_text(strip=True) if cells else ""

                if not player_name or len(player_name) < 2:
                    continue

                enrichment = {
                    "team": player_name,
                    "source_domain": "tennisabstract.com",
                    "stat_type": "elo_rating",
                    "enrichments": {},
                }

                # Map cells to headers
                for idx, cell in enumerate(cells):
                    val = cell.get_text(strip=True)
                    if not val:
                        continue
                    key = headers[idx] if idx < len(headers) else f"col_{idx}"
                    try:
                        enrichment["enrichments"][key] = float(val)
                    except ValueError:
                        enrichment["enrichments"][key] = val

                # Player URL
                if player_link:
                    href = player_link.get("href", "")
                    if href:
                        enrichment["enrichments"]["profile_url"] = href

                if len(enrichment["enrichments"]) > 1:
                    results.append(enrichment)

        return results


# ============================================================================
# PROFILE REGISTRY
# ============================================================================

PROFILES: dict[str, ExtractionProfile] = {
    # Multi-sport (Tier A stats sources)
    "flashscore.com": FlashscoreProfile(),
    "sofascore.com": SofascoreProfile(),
    "scores24.live": Scores24Profile(),
    # Multi-sport (Tier A odds sources)
    "betexplorer.com": BetExplorerProfile(),
    "oddsportal.com": OddsPortalProfile(),
    "betclic.pl": BetclicProfile(),
    # Football
    "totalcorner.com": TotalCornerProfile(),
    "soccerstats.com": SoccerStatsProfile(),
    "forebet.com": ForebetProfile(),
    "whoscored.com": WhoScoredProfile(),
    # US sports
    "covers.com": CoversProfile(),
    "basketball-reference.com": BasketballReferenceProfile(),
    "hockey-reference.com": HockeyReferenceProfile(),
    # Tennis
    "tennisexplorer.com": TennisExplorerProfile(),
    "tennisabstract.com": TennisAbstractProfile(),
    # NOTE: Removed sport profiles (hltv.org, cuetracker.net, dartsorakel.com,
    # speedwayekstraliga.pl, gosugamers.net) kept in code but excluded from
    # registry — pipeline now covers 5 sports only.
}


# ============================================================================
# MAIN PARSER ENGINE
# ============================================================================

# Plausibility ranges for extracted numeric values (stat_key -> (min, max))
PLAUSIBLE_RANGES = {
    "corners_ft_home": (0, 20),
    "corners_ft_away": (0, 20),
    "corners_ht_home": (0, 12),
    "corners_ht_away": (0, 12),
    "yellow_cards_home": (0, 10),
    "yellow_cards_away": (0, 10),
    "red_cards_home": (0, 4),
    "red_cards_away": (0, 4),
    "dangerous_attacks_home": (0, 150),
    "dangerous_attacks_away": (0, 150),
    "league_position_home": (1, 40),
    "league_position_away": (1, 40),
    "odds_1": (1.01, 100.0),
    "odds_x": (1.01, 100.0),
    "odds_2": (1.01, 100.0),
    "prob_home": (0, 100),
    "prob_draw": (0, 100),
    "prob_away": (0, 100),
    "avg_stat": (0.0, 50.0),
    "seed_home": (1, 500),
    "seed_away": (1, 500),
}


def _validate_enrichments(enrichments: list[dict]) -> dict:
    """Validate extracted enrichments for plausibility.

    Returns validation report with:
    - total: count of enrichment dicts
    - values_checked: total numeric values inspected
    - out_of_range: list of {key, value, expected_range, item} for implausible values
    - empty_enrichments: count of items where enrichments dict is empty
    - field_coverage: {field_name: count} — how many items have each field
    """
    values_checked = 0
    out_of_range = []
    empty_count = 0
    field_counts: dict[str, int] = defaultdict(int)

    for item in enrichments:
        enrich = item.get("enrichments", {})
        if not enrich:
            empty_count += 1
            continue

        for key, val in enrich.items():
            field_counts[key] += 1

            # Only range-check numeric values
            if not isinstance(val, (int, float)):
                continue

            values_checked += 1
            lo, hi = PLAUSIBLE_RANGES.get(key, (None, None))
            if lo is not None and hi is not None:
                if val < lo or val > hi:
                    out_of_range.append({
                        "key": key,
                        "value": val,
                        "expected_range": [lo, hi],
                        "home": item.get("home", item.get("team", "")),
                        "away": item.get("away", ""),
                    })

    return {
        "total": len(enrichments),
        "values_checked": values_checked,
        "out_of_range_count": len(out_of_range),
        "out_of_range": out_of_range[:20],  # cap to avoid huge reports
        "empty_enrichments": empty_count,
        "field_coverage": dict(sorted(field_counts.items(), key=lambda x: -x[1])),
    }


def _cross_reference_db(enrichments: list[dict], domain: str, date: str) -> dict:
    """Cross-reference enrichments against existing scan_results in DB.

    First tries matching within the same source_domain. If that domain has 0
    rows in scan_results (e.g. basketball-reference.com is an enrichment source,
    not a scan source), falls back to matching by team names across ALL domains.

    Returns:
    - scan_results_total: how many scan_results exist for this domain+date
    - matched: how many enrichments found a matching scan_result
    - unmatched: how many enrichments had no DB match (extraction may be stale/wrong)
    - match_rate: percentage of enrichments that linked to existing data
    - sample_unmatched: first 5 unmatched items for agent inspection
    - cross_domain: True if fallback to all-domain matching was used
    """
    if not _HAS_DB:
        return {"status": "no_db", "matched": 0, "unmatched": len(enrichments)}

    try:
        with get_db() as conn:
            # Count total scan_results for this domain+date
            c = conn.execute(
                "SELECT COUNT(*) FROM scan_results WHERE betting_date = ? AND source_domain = ?",
                (date, domain),
            )
            total_in_db = c.fetchone()[0]

            # If this domain has 0 rows in scan_results, it's an enrichment-only
            # source (e.g. basketball-reference.com, hockey-reference.com).
            # Fall back to matching by team names across ALL source_domains.
            cross_domain = total_in_db == 0 and len(enrichments) > 0
            domain_filter = "" if cross_domain else "AND source_domain = ?"

            matched = 0
            unmatched = 0
            sample_unmatched = []

            for item in enrichments:
                home = item.get("home", "")
                away = item.get("away", "")
                team = item.get("team", "")

                found = False
                if home and away:
                    if cross_domain:
                        c = conn.execute(
                            """SELECT COUNT(*) FROM scan_results
                               WHERE betting_date = ?
                               AND (lower(home_team) LIKE ? OR lower(away_team) LIKE ?
                                    OR lower(home_team) LIKE ? OR lower(away_team) LIKE ?)""",
                            (date, f"%{home.lower()}%", f"%{home.lower()}%",
                             f"%{away.lower()}%", f"%{away.lower()}%"),
                        )
                    else:
                        c = conn.execute(
                            f"""SELECT COUNT(*) FROM scan_results
                               WHERE betting_date = ? AND source_domain = ?
                               AND (lower(home_team) LIKE ? OR lower(away_team) LIKE ?
                                    OR lower(home_team) LIKE ? OR lower(away_team) LIKE ?)""",
                            (date, domain, f"%{home.lower()}%", f"%{home.lower()}%",
                             f"%{away.lower()}%", f"%{away.lower()}%"),
                        )
                    found = c.fetchone()[0] > 0
                elif team:
                    if cross_domain:
                        c = conn.execute(
                            """SELECT COUNT(*) FROM scan_results
                               WHERE betting_date = ?
                               AND (lower(home_team) LIKE ? OR lower(away_team) LIKE ?)""",
                            (date, f"%{team.lower()}%", f"%{team.lower()}%"),
                        )
                    else:
                        c = conn.execute(
                            f"""SELECT COUNT(*) FROM scan_results
                               WHERE betting_date = ? AND source_domain = ?
                               AND (lower(home_team) LIKE ? OR lower(away_team) LIKE ?)""",
                            (date, domain, f"%{team.lower()}%", f"%{team.lower()}%"),
                        )
                    found = c.fetchone()[0] > 0

                if found:
                    matched += 1
                else:
                    unmatched += 1
                    if len(sample_unmatched) < 5:
                        sample_unmatched.append({"home": home, "away": away} if home else {"team": team})

            total = matched + unmatched
            match_rate = round(matched / total * 100, 1) if total else 0.0

            return {
                "scan_results_in_db": total_in_db,
                "enrichments_total": total,
                "matched": matched,
                "unmatched": unmatched,
                "match_rate_pct": match_rate,
                "sample_unmatched": sample_unmatched,
                "cross_domain": cross_domain,
            }
    except Exception as e:
        return {"status": "error", "error": str(e), "matched": 0, "unmatched": len(enrichments)}


def _compute_domain_verdict(domain_result: dict, validation: dict, xref: dict) -> dict:
    """Compute a PASS/WARN/FAIL verdict for a domain extraction.

    Rules:
    - FAIL: >20% values out of range, OR match_rate <30% (extracted data doesn't match DB)
    - WARN: 5-20% out of range, OR match_rate 30-60%, OR 0 enrichments from non-zero snapshots
    - PASS: <5% out of range AND match_rate >60%
    """
    status = domain_result.get("status", "no_profile")
    if status != "ok":
        return {"verdict": "SKIP", "reason": f"Domain status: {status}"}

    extractions = domain_result.get("unique_extractions", 0)
    snapshots = domain_result.get("snapshots_processed", 0)

    # Zero extractions from existing snapshots = profile may be broken
    if extractions == 0 and snapshots > 0:
        return {
            "verdict": "WARN",
            "reason": f"0 extractions from {snapshots} snapshots — profile may need updating (HTML structure changed?)",
            "action": "Agent should inspect a sample HTML file to check if CSS selectors still match",
        }

    if extractions == 0:
        return {"verdict": "SKIP", "reason": "No snapshots available"}

    issues = []

    # Check out-of-range values
    oor_count = validation.get("out_of_range_count", 0)
    values_checked = validation.get("values_checked", 0)
    if values_checked > 0:
        oor_pct = oor_count / values_checked * 100
        if oor_pct > 20:
            return {
                "verdict": "FAIL",
                "reason": f"{oor_count}/{values_checked} values ({oor_pct:.0f}%) out of plausible range",
                "action": "Agent should review out_of_range items — extraction logic may be parsing wrong cells",
                "out_of_range_samples": validation.get("out_of_range", [])[:5],
            }
        if oor_pct > 5:
            issues.append(f"{oor_pct:.0f}% values out of range")

    # Check DB match rate
    # Cross-domain enrichment sources (no scan_results under their domain) never FAIL.
    # Non-cross-domain sources with real extractions WARN at low match — the profile
    # is working (data extracted) but names may not align with fixture names.
    # Only FAIL if the domain is a PRIMARY scan source AND match rate is very low.
    match_rate = xref.get("match_rate_pct", 100)
    is_cross_domain = xref.get("cross_domain", False)
    enrichments_total = xref.get("enrichments_total", 0)

    # Primary scan sources (high fixture-to-enrichment correlation expected)
    PRIMARY_SCAN_DOMAINS = {
        "flashscore.com", "totalcorner.com", "forebet.com",
        "betexplorer.com", "whoscored.com",
    }
    is_primary = domain_result.get("domain", "") in PRIMARY_SCAN_DOMAINS

    min_fail = 30 if is_primary else 0   # only primary scan sources can FAIL on match rate
    min_warn = 60 if is_primary else 15  # enrichment/reference sources get low WARN threshold

    if match_rate < min_fail and enrichments_total > 10:
        return {
            "verdict": "FAIL",
            "reason": f"Only {match_rate}% of enrichments matched DB scan_results — extracted data may be stale or from wrong page",
            "action": "Agent should verify snapshot dates match betting date, check if domain layout changed",
            "sample_unmatched": xref.get("sample_unmatched", []),
        }
    if match_rate < min_warn and enrichments_total > 5:
        issues.append(f"Low DB match rate: {match_rate}%" + (" (cross-domain enrichment source)" if is_cross_domain else ""))

    if issues:
        return {
            "verdict": "WARN",
            "reason": "; ".join(issues),
            "action": "Agent should review warnings but can proceed",
        }

    return {
        "verdict": "PASS",
        "reason": f"{extractions} enrichments, {match_rate}% DB match, values within range",
    }


def find_snapshots(domain: str, date: str) -> list[Path]:
    """Find HTML snapshots for a domain from a specific date."""
    domain_dir = DATA_DIR / domain
    if not domain_dir.exists():
        return []

    # Date format in filenames: 20260508THHMMSSZ
    date_prefix = date.replace("-", "")

    snapshots = []
    for f in domain_dir.iterdir():
        if not f.suffix == ".html":
            continue
        # Match date prefix in filename
        if f.name.startswith(date_prefix):
            snapshots.append(f)

    # If no date-specific files, get the most recent ones
    if not snapshots:
        all_html = sorted(domain_dir.glob("*.html"), key=lambda p: p.name, reverse=True)
        # Take files from the last 24 hours
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        for f in all_html:
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                if mtime >= cutoff:
                    snapshots.append(f)
            except OSError:
                pass

    return sorted(snapshots)


def parse_domain(domain: str, date: str, dry_run: bool = False) -> dict:
    """Run deep parsing for a single domain. Returns extraction report."""
    profile = PROFILES.get(domain)
    if not profile:
        return {"domain": domain, "status": "no_profile", "extractions": 0}

    snapshots = find_snapshots(domain, date)
    if not snapshots:
        return {"domain": domain, "status": "no_snapshots", "extractions": 0}

    all_enrichments = []
    errors = []

    for snapshot in snapshots:
        try:
            html = snapshot.read_text(encoding="utf-8", errors="replace")
            soup = BeautifulSoup(html, "html.parser")
            enrichments = profile.extract(html, str(snapshot), soup)
            all_enrichments.extend(enrichments)
        except Exception as e:
            errors.append({"file": str(snapshot), "error": str(e)})

    # Deduplicate by (home, away) or team
    seen = set()
    unique = []
    for e in all_enrichments:
        key = (e.get("home", ""), e.get("away", ""), e.get("team", ""))
        if key not in seen:
            seen.add(key)
            unique.append(e)

    if not dry_run and _HAS_DB and unique:
        _write_to_db(unique, domain, date)

    # Run validation and cross-reference
    validation = _validate_enrichments(unique)
    xref = _cross_reference_db(unique, domain, date) if _HAS_DB else {}

    result = {
        "domain": domain,
        "status": "ok",
        "snapshots_processed": len(snapshots),
        "raw_extractions": len(all_enrichments),
        "unique_extractions": len(unique),
        "errors": errors,
        "sample": unique[:3] if unique else [],
        "validation": validation,
        "db_cross_reference": xref,
    }

    # Compute verdict
    result["verdict"] = _compute_domain_verdict(result, validation, xref)

    return result


def _write_to_db(enrichments: list[dict], domain: str, date: str):
    """Write enrichment data to DB — update scan_results raw_data and team_form."""
    try:
        with get_db() as conn:
            repo = ScanResultRepo(conn)

            for e in enrichments:
                home = e.get("home", "")
                away = e.get("away", "")
                team = e.get("team", "")
                enrich_data = e.get("enrichments", {})

                if home and away:
                    # Update scan_results raw_data with enrichments
                    event_key_pattern = f"{home}|{away}|%".lower()
                    rows = conn.execute(
                        """SELECT id, raw_data FROM scan_results
                           WHERE betting_date = ? AND source_domain = ?
                           AND lower(event_key) LIKE ?
                           LIMIT 1""",
                        (date, domain, event_key_pattern),
                    ).fetchall()

                    for row in rows:
                        existing = json.loads(row[1]) if row[1] else {}
                        existing.setdefault("deep_parse", {})
                        existing["deep_parse"].update(enrich_data)
                        existing["deep_parse"]["parsed_at"] = datetime.now(
                            timezone.utc
                        ).isoformat()
                        conn.execute(
                            "UPDATE scan_results SET raw_data = ? WHERE id = ?",
                            (json.dumps(existing, ensure_ascii=False), row[0]),
                        )

                elif team:
                    # Team-level stat: store in scan_results as a team_stat entry
                    # (team_form table uses team_id FK, so we store enrichments
                    # as scan_results with stat_type marker for downstream processing)
                    stat_type = e.get("stat_type", "")
                    sport = e.get("sport", "football")
                    stat_data = json.dumps(enrich_data, ensure_ascii=False)
                    now_ts = datetime.now(timezone.utc).isoformat()

                    # Try to update existing scan_result for this team
                    rows = conn.execute(
                        """SELECT id, raw_data FROM scan_results
                           WHERE betting_date = ? AND source_domain = ?
                           AND (lower(home_team) = lower(?) OR lower(away_team) = lower(?))
                           LIMIT 5""",
                        (date, domain, team, team),
                    ).fetchall()

                    for row in rows:
                        existing = json.loads(row[1]) if row[1] else {}
                        existing.setdefault("deep_parse", {})
                        existing["deep_parse"][f"{stat_type}_data"] = enrich_data
                        existing["deep_parse"]["parsed_at"] = now_ts
                        conn.execute(
                            "UPDATE scan_results SET raw_data = ? WHERE id = ?",
                            (json.dumps(existing, ensure_ascii=False), row[0]),
                        )

            conn.commit()
    except Exception as e:
        print(f"[deep-parser] DB write error for {domain}: {e}")


def run_deep_parse(date: str, domains: list[str] | None = None,
                   dry_run: bool = False) -> dict:
    """Run deep parsing for all configured domains."""
    target_domains = domains or list(PROFILES.keys())

    report = {
        "date": date,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "domains": {},
        "totals": {"snapshots": 0, "extractions": 0, "errors": 0},
        "verdicts": {},
    }

    for domain in target_domains:
        if domain not in PROFILES:
            print(f"[deep-parser] No profile for {domain}, skipping")
            continue

        print(f"[deep-parser] Processing {domain}...")
        result = parse_domain(domain, date, dry_run=dry_run)
        report["domains"][domain] = result

        report["totals"]["snapshots"] += result.get("snapshots_processed", 0)
        report["totals"]["extractions"] += result.get("unique_extractions", 0)
        report["totals"]["errors"] += len(result.get("errors", []))

        # Print verdict
        verdict = result.get("verdict", {})
        verdict_label = verdict.get("verdict", "?")
        verdict_reason = verdict.get("reason", "")
        report["verdicts"][domain] = verdict_label

        count = result.get("unique_extractions", 0)
        snaps = result.get("snapshots_processed", 0)
        xref = result.get("db_cross_reference", {})
        match_rate = xref.get("match_rate_pct", "n/a")

        icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌", "SKIP": "⏭"}.get(verdict_label, "?")
        print(f"  {icon} {verdict_label}: {count} enrichments from {snaps} snapshots | DB match: {match_rate}%")
        if verdict_label in ("WARN", "FAIL"):
            print(f"     Reason: {verdict_reason}")
            action = verdict.get("action", "")
            if action:
                print(f"     Action: {action}")

    # Write report
    report_path = DATA_DIR / f"{date.replace('-', '')}_deep_parse_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    # Write agent review input (follows agent_protocol.py pattern)
    _write_agent_review(date, report)

    # Print summary
    pass_count = sum(1 for v in report["verdicts"].values() if v == "PASS")
    warn_count = sum(1 for v in report["verdicts"].values() if v == "WARN")
    fail_count = sum(1 for v in report["verdicts"].values() if v == "FAIL")

    print(f"\n[deep-parser] Report: {report_path}")
    print(f"[deep-parser] Totals: {report['totals']['snapshots']} snapshots → "
          f"{report['totals']['extractions']} enrichments, "
          f"{report['totals']['errors']} errors")
    print(f"[deep-parser] Verdicts: {pass_count} PASS, {warn_count} WARN, {fail_count} FAIL")

    if fail_count > 0:
        print(f"\n  {'='*60}")
        print(f"  [AGENT-REVIEW-REQUIRED] Agent: bet-scanner")
        print(f"  {fail_count} domain(s) FAILED validation.")
        print(f"  Agent must inspect HTML snapshots and verify extraction profiles.")
        print(f"  Review file: betting/data/agent_reviews/{date}/s1_html_deep_input.json")
        print(f"  {'='*60}\n")

    return report


def _write_agent_review(date: str, report: dict):
    """Write structured agent review input following agent_protocol.py pattern."""
    reviews_dir = DATA_DIR / "agent_reviews" / date
    reviews_dir.mkdir(parents=True, exist_ok=True)

    # Build per-domain action items for the agent
    action_items = []
    for domain, domain_data in report["domains"].items():
        verdict = domain_data.get("verdict", {})
        v_label = verdict.get("verdict", "SKIP")
        if v_label in ("WARN", "FAIL"):
            action_items.append({
                "domain": domain,
                "verdict": v_label,
                "reason": verdict.get("reason", ""),
                "action": verdict.get("action", ""),
                "snapshots": domain_data.get("snapshots_processed", 0),
                "extractions": domain_data.get("unique_extractions", 0),
                "match_rate_pct": domain_data.get("db_cross_reference", {}).get("match_rate_pct", None),
                "out_of_range_samples": verdict.get("out_of_range_samples", []),
                "sample_unmatched": verdict.get("sample_unmatched",
                    domain_data.get("db_cross_reference", {}).get("sample_unmatched", [])),
            })

    # Summary of fields extracted across all domains
    all_fields = defaultdict(int)
    for domain_data in report["domains"].values():
        for field, cnt in domain_data.get("validation", {}).get("field_coverage", {}).items():
            all_fields[field] += cnt

    payload = {
        "step_id": "s1_html_deep",
        "date": date,
        "agent": "bet-scanner",
        "task": (
            "Validate HTML deep parsing results. For each WARN/FAIL domain: "
            "(1) Read a sample HTML snapshot from betting/data/{domain}/ "
            "(2) Check if CSS selectors in the extraction profile still match the HTML structure "
            "(3) Verify that extracted values (team names, scores, odds, stats) are correct "
            "(4) If profile is broken, report which selectors need updating "
            "(5) For PASS domains, spot-check 2-3 random enrichments against the source HTML"
        ),
        "metrics": {
            "total_snapshots": report["totals"]["snapshots"],
            "total_enrichments": report["totals"]["extractions"],
            "total_errors": report["totals"]["errors"],
            "verdicts": report["verdicts"],
            "pass_count": sum(1 for v in report["verdicts"].values() if v == "PASS"),
            "warn_count": sum(1 for v in report["verdicts"].values() if v == "WARN"),
            "fail_count": sum(1 for v in report["verdicts"].values() if v == "FAIL"),
        },
        "action_items": action_items,
        "field_coverage_global": dict(sorted(all_fields.items(), key=lambda x: -x[1])[:30]),
        "artifacts": [
            str(DATA_DIR / f"{date.replace('-', '')}_deep_parse_report.json"),
        ],
        "verification_protocol": {
            "for_each_FAIL_domain": [
                "1. List HTML snapshots: ls betting/data/{domain}/*.html | tail -3",
                "2. Open most recent snapshot and search for key CSS classes from the profile",
                "3. If classes are found → extraction logic is wrong → inspect profile code",
                "4. If classes are NOT found → HTML structure changed → profile needs updating",
                "5. Report findings with specific CSS selectors that need to change",
            ],
            "for_each_WARN_domain": [
                "1. Check out_of_range_samples — are these real parsing errors or legitimate outliers?",
                "2. Check sample_unmatched — are these events from a different date or different source?",
                "3. If match_rate <60%, verify snapshot file dates match the betting date",
            ],
            "for_PASS_domains": [
                "1. Spot-check: pick 2 random enrichments from the sample",
                "2. Find the corresponding HTML in the snapshot and verify values match",
                "3. Confirm field_coverage makes sense for this domain",
            ],
        },
        "expected_output": {
            "status": "approved | flagged | needs_fix",
            "domains_reviewed": "list of domains with per-domain verdict",
            "broken_profiles": "list of profiles that need CSS selector updates",
            "false_positives": "values flagged as out_of_range that are actually correct",
        },
        "written_at": datetime.now(timezone.utc).isoformat(),
    }

    out_path = reviews_dir / "s1_html_deep_input.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"[deep-parser] Agent review: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="HTML Deep Parser")
    parser.add_argument("--date", required=True, help="Betting date YYYY-MM-DD")
    parser.add_argument("--domains", help="Comma-separated domains to parse")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    parser.add_argument("--report", action="store_true", help="Show detailed report")
    args = parser.parse_args()

    domains = args.domains.split(",") if args.domains else None
    report = run_deep_parse(args.date, domains, dry_run=args.dry_run)

    if args.report:
        print("\n" + json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
