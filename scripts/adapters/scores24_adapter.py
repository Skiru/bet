"""Scores24.live adapter — parses match listings, detail pages with H2H,
recent form, odds, and betting trends.

scores24.live URL patterns:
  Listing:  /en/{sport}               — today's matches for a sport
  Detail:   /en/{sport}/m-{date}-{slug}  — match detail (overview)
  Trends:   /en/{sport}/m-{date}-{slug}#trends — betting tips + trends
  Odds:     /en/{sport}/m-{date}-{slug}#odds — bookmaker odds
  Predict:  /en/{sport}/m-{date}-{slug}-prediction — community prediction

Sport slugs: soccer, tennis, basketball, ice-hockey, volleyball,
             american-football, futsal

Data extracted from detail pages:
  - Match info: teams, date, time, venue, surface, tournament, round
  - Odds: W1, X (if 3-way), W2 + handicap + totals from multiple bookmakers
  - H2H: head-to-head record with match scores
  - Latest results: last N matches per team with scores and W/L
  - Trends: structured betting tips with statistical backing
"""
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import re

# Map scores24 sport slugs to our internal sport names
_SPORT_MAP = {
    "soccer": "football",
    "tennis": "tennis",
    "basketball": "basketball",
    "ice-hockey": "hockey",
    "volleyball": "volleyball",
    "american-football": "football",  # NFL
    "futsal": "football",
}

# Regex to detect match detail URLs
_MATCH_URL_RE = re.compile(r"/en/([a-z-]+)/m-(\d{2}-\d{2}-\d{4})-(.+?)(?:#.*)?$")
# Regex to detect listing URLs
_LISTING_URL_RE = re.compile(r"/en/([a-z-]+)/?$")
# Date patterns in page text: DD.MM.YY or DD.MM.YYYY
_DATE_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{2,4})")


def _detect_sport(url: str) -> str:
    """Detect sport from scores24 URL."""
    m = _MATCH_URL_RE.search(url)
    if m:
        return _SPORT_MAP.get(m.group(1), m.group(1))
    m = _LISTING_URL_RE.search(url)
    if m:
        return _SPORT_MAP.get(m.group(1), m.group(1))
    url_lower = url.lower()
    for slug, sport in _SPORT_MAP.items():
        if f"/{slug}" in url_lower:
            return sport
    return "football"


def _is_match_detail(url: str) -> bool:
    """Check if URL is a match detail page."""
    return bool(_MATCH_URL_RE.search(url))


def _parse_listing_page(html: str, url: str) -> List[Dict]:
    """Parse a sport listing page to extract match links and basic info."""
    soup = BeautifulSoup(html, "html.parser")
    sport = _detect_sport(url)
    results = []
    seen = set()

    # Find match detail links: /en/{sport}/m-{date}-{slug}
    sport_slug = url.rstrip("/").split("/")[-1]
    # Match links like /en/tennis/m-30-04-2026-player1-player2
    # Exclude prediction links (ending with -prediction)
    link_re = re.compile(
        rf"/en/{re.escape(sport_slug)}/m-\d{{2}}-\d{{2}}-\d{{4}}-[a-z0-9-]+$"
    )

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        # Skip prediction/odds/trends links
        if href.endswith("-prediction") or "#" in href:
            continue
        if not link_re.match(href):
            continue
        if href in seen:
            continue
        seen.add(href)

        # Extract team names from the link slug
        m = _MATCH_URL_RE.search(href)
        if not m:
            continue

        date_part = m.group(2)  # DD-MM-YYYY
        slug = m.group(3)

        # Parse date
        date_parts = date_part.split("-")
        if len(date_parts) == 3:
            iso_date = f"{date_parts[2]}-{date_parts[1]}-{date_parts[0]}"
        else:
            iso_date = None

        # Try to extract team names from link text or parent context
        link_text = a_tag.get_text(strip=True)

        # Also check parent element text for "Team A - Team B" pattern
        parent_text = ""
        parent = a_tag.parent
        if parent:
            parent_text = parent.get_text(separator=" ", strip=True)

        home, away = _parse_teams_from_slug(slug, link_text)
        if not away and parent_text:
            home, away = _parse_teams_from_slug(slug, parent_text)

        # If still no away team, use the slug as a single name for discovery
        if not away:
            # Score24 slugs are firstname-lastname-firstname-lastname
            # We can't reliably split, so just store the full URL for deep fetch
            home = slug.replace("-", " ").title()
            away = ""

        time_str = None
        current_league = None
        parent = a_tag.parent
        if parent:
            parent_text = parent.get_text(separator=" ", strip=True)
            time_m = re.search(r"\b(\d{1,2}:\d{2})\b", parent_text)
            if time_m:
                time_str = time_m.group(1)

            # Try to grab league from a preceding header
            prev_header = parent.find_previous(["h2", "h3", "div"], class_=re.compile(r"league|tournament|competition", re.I))
            if prev_header:
                current_league = prev_header.get_text(strip=True)
                
        # If no heading found, try to extract from URL if it's a league page
        if not current_league:
            url_parts = url.rstrip("/").split("/")
            if len(url_parts) > 4:
                # e.g. /en/football/england-premier-league
                current_league = url_parts[-1].replace("-", " ").title()

        full_url = f"https://scores24.live{href}"
        results.append({
            "home": home,
            "away": away,
            "time": time_str,
            "date": iso_date,
            "league": current_league or "(unknown league)",
            "sport": sport,
            "source_url": url,
            "detail_url": full_url,
            "detail_url_trends": f"{full_url}#trends",
            "source_type": "scores24"
        })

    return results


def _parse_teams_from_slug(slug: str, link_text: str = "") -> tuple:
    """Extract home and away team names from URL slug or link text."""
    # Try link text first: "Team A - Team B" or "Team A vs Team B"
    if link_text:
        for sep in [" - ", " – ", " — ", " vs ", " vs. "]:
            if sep in link_text:
                parts = link_text.split(sep, 1)
                if len(parts) == 2:
                    h = parts[0].strip()
                    a = parts[1].strip()
                    if len(h) > 1 and len(a) > 1:
                        return h, a

    # Fallback: slug is like "team-a-team-b" — hard to split reliably
    # We'll titlecase the slug and return as-is for discovery
    name = slug.replace("-", " ").title()
    return name, ""


def _parse_detail_page(html: str, url: str) -> List[Dict]:
    """Parse a match detail page for deep data extraction.

    Returns a single-element list with rich match data including:
    - match_info: teams, venue, surface, tournament, round, date/time
    - odds: W1/X/W2, handicap lines, totals lines
    - h2h: head-to-head records with scores
    - form_home / form_away: latest results per team
    - trends: structured betting tips with statistical backing
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    sport = _detect_sport(url)

    result = {
        "source": "scores24.live",
        "source_url": url,
        "sport": sport,
    }

    # --- Extract match info ---
    result["match_info"] = _extract_match_info(lines, url)
    home = result["match_info"].get("home", "")
    away = result["match_info"].get("away", "")
    result["home"] = home
    result["away"] = away
    
    if "surface" in result["match_info"]:
        result["surface"] = result["match_info"]["surface"]
    if "venue" in result["match_info"]:
        result["venue"] = result["match_info"]["venue"]
    if "tournament" in result["match_info"]:
        result["league"] = result["match_info"]["tournament"]
        
    result["source_type"] = "scores24"

    # --- Extract odds ---
    result["odds"] = _extract_odds(lines, soup, sport)

    # --- Extract H2H ---
    result["h2h"] = _extract_h2h(lines, home, away)

    # --- Extract latest results (form) ---
    result["form_home"] = _extract_form(lines, home)
    result["form_away"] = _extract_form(lines, away)

    # --- Extract trends / betting tips ---
    result["trends"] = _extract_trends(lines, home, away)

    return [result]


def _extract_match_info(lines: List[str], url: str) -> Dict:
    """Extract match header info: teams, venue, tournament, date, time."""
    info = {}

    # Teams from URL slug
    m = _MATCH_URL_RE.search(url)
    if m:
        date_part = m.group(2)
        dp = date_part.split("-")
        if len(dp) == 3:
            info["date"] = f"{dp[2]}-{dp[1]}-{dp[0]}"

    # Find teams: scores24 uses the pattern:
    #   "Team/Player A"  (line N)
    #   "-"              (line N+1)
    #   "Team/Player B"  (line N+2)
    # Near the top of the page, after tournament info
    for i in range(len(lines) - 2):
        if (lines[i + 1] == "-"
                and len(lines[i]) > 2 and len(lines[i + 2]) > 2
                and len(lines[i]) < 80 and len(lines[i + 2]) < 80
                and not lines[i].startswith("http")
                and not any(w in lines[i].lower() for w in ["cookie", "subscribe", "accept", "match on"])
                and not re.match(r"^\d", lines[i])):
            info["home"] = lines[i]
            info["away"] = lines[i + 2]
            break

    # Fallback: try "Betting Tips: Team A - Team B" line
    if "home" not in info:
        for line in lines:
            if line.lower().startswith("betting tips:"):
                rest = line[len("Betting Tips:"):].strip()
                if " - " in rest:
                    parts = rest.split(" - ", 1)
                    info["home"] = parts[0].strip()
                    info["away"] = parts[1].strip()
                break

    # Tournament — look for known tournament position (before team names)
    for i, line in enumerate(lines):
        if line == "Tournament" and i + 1 < len(lines):
            info["tournament"] = lines[i + 1]
            break
    # Fallback: look for competition name before team names
    if "tournament" not in info:
        for i, line in enumerate(lines):
            if line in ("ATP Madrid", "WTA Madrid") or "Champions League" in line:
                info["tournament"] = line
                break
            # Generic: look for lines like "ATP {city}" just before team names
            if re.match(r"^(ATP|WTA|UEFA|FIFA|NBA|NHL|MLB)\b", line):
                info["tournament"] = line
                break

    # Venue
    for i, line in enumerate(lines):
        if line == "Venue" and i + 2 < len(lines):
            info["venue_country"] = lines[i + 1]
            info["venue"] = lines[i + 2]
            break

    # Surface (tennis)
    for i, line in enumerate(lines):
        if line == "Surface:" and i + 1 < len(lines):
            info["surface"] = lines[i + 1]
            break
        elif line.startswith("Surface:") and len(line) > 9:
            info["surface"] = line.split(":", 1)[1].strip()
            break

    # Round
    for i, line in enumerate(lines):
        if line == "Round:" and i + 1 < len(lines):
            info["round"] = lines[i + 1]
            break
        elif line.startswith("Round:") and len(line) > 7:
            info["round"] = line.split(":", 1)[1].strip()
            break

    # Time — look for HH:MM near date patterns like DD.MM.YY
    for i, line in enumerate(lines[:80]):
        if _DATE_RE.match(line) and i + 1 < len(lines):
            time_m = re.match(r"(\d{1,2}:\d{2})$", lines[i + 1])
            if time_m:
                info["time"] = time_m.group(1)
                break

    return info


def _extract_odds(lines: List[str], soup: BeautifulSoup, sport: str) -> Dict:
    """Extract odds from the page.

    Looks for W1/X/W2 pattern and handicap/totals lines.
    """
    odds = {}

    # Find W1/W2 (and X for 3-way sports)
    for i, line in enumerate(lines):
        if line == "W1" and i + 1 < len(lines):
            try:
                odds["w1"] = float(lines[i + 1])
            except (ValueError, IndexError):
                pass
            # Check for X/x (draw) and W2
            j = i + 2
            while j < min(i + 8, len(lines)):
                if lines[j].lower() == "x" and j + 1 < len(lines):
                    try:
                        odds["x"] = float(lines[j + 1])
                    except ValueError:
                        pass
                if lines[j] == "W2" and j + 1 < len(lines):
                    try:
                        odds["w2"] = float(lines[j + 1])
                    except ValueError:
                        pass
                j += 1
            break

    # Extract handicap and totals from the odds section
    # Look for patterns like "+1.5 1.75" or "> 2.5 1.80"
    odds["handicap_lines"] = []
    odds["total_lines"] = []

    for i, line in enumerate(lines):
        # Handicap: "+X.X ODDS" or "-X.X ODDS"
        hc_m = re.match(r"([+-]\d+\.?\d*)\s*(\d+\.\d+)", line)
        if hc_m:
            odds["handicap_lines"].append({
                "line": hc_m.group(1),
                "odds": float(hc_m.group(2)),
            })
        # Totals: "> X.X ODDS" or "< X.X ODDS"
        tot_m = re.match(r"([><])\s*(\d+\.?\d*)\s*(\d+\.\d+)", line)
        if tot_m:
            direction = "over" if tot_m.group(1) == ">" else "under"
            odds["total_lines"].append({
                "direction": direction,
                "line": float(tot_m.group(2)),
                "odds": float(tot_m.group(3)),
            })

    # Also parse from link text (bookmaker odds in links)
    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href", "")
        if "/dapi/" not in href or "position=calc" not in href:
            continue
        text = a_tag.get_text(strip=True)
        # Pattern: "W1 3.3" or "> 23 1.8" or "+1.5 1.75"
        if not text:
            continue
        # Total over/under from calc links
        tot_link_m = re.match(r"([><])\s*(\d+\.?\d*)\s*(\d+\.\d+)", text)
        if tot_link_m:
            direction = "over" if tot_link_m.group(1) == ">" else "under"
            entry = {
                "direction": direction,
                "line": float(tot_link_m.group(2)),
                "odds": float(tot_link_m.group(3)),
            }
            if entry not in odds["total_lines"]:
                odds["total_lines"].append(entry)
        # Handicap from calc links
        hc_link_m = re.match(r"([+-]\d+\.?\d*)\s*(\d+\.\d+)", text)
        if hc_link_m:
            entry = {
                "line": hc_link_m.group(1),
                "odds": float(hc_link_m.group(2)),
            }
            if entry not in odds["handicap_lines"]:
                odds["handicap_lines"].append(entry)

    return odds


def _extract_h2h(lines: List[str], home: str, away: str) -> Dict:
    """Extract head-to-head record and match history."""
    h2h = {"home_wins": 0, "away_wins": 0, "matches": []}

    # Find H2H section: "X Head-to-Head" or "Head-to-Head"
    h2h_start = None
    for i, line in enumerate(lines):
        if "head-to-head" in line.lower():
            h2h_start = i + 1
            break

    if h2h_start is None:
        return h2h

    # Parse win percentages and counts
    # Pattern after header: "33%" "1 Win" "67%" "2 Wins"
    wins_found = 0
    for j in range(h2h_start, min(h2h_start + 10, len(lines))):
        win_m = re.match(r"(\d+)\s+Wins?$", lines[j])
        if win_m:
            wins = int(win_m.group(1))
            if wins_found == 0:
                h2h["home_wins"] = wins
            else:
                h2h["away_wins"] = wins
            wins_found += 1

    # Parse individual H2H matches
    # Pattern: date (DD.MM.YY), venue, team1, team2, scores (0, 2, 3, 6, 3, 6), ...
    i = h2h_start
    while i < min(h2h_start + 100, len(lines)):
        line = lines[i]

        # Stop conditions
        if "latest result" in line.lower():
            break
        if line.lower().startswith("there are no events"):
            break

        date_m = _DATE_RE.match(line)
        if date_m:
            d, mo, y = date_m.groups()
            if len(y) == 2:
                y = f"20{y}"
            match_data = {"date": f"{y}-{mo}-{d}"}
            i += 1

            # Next line: venue (if not a number and not a date)
            if i < len(lines) and not _DATE_RE.match(lines[i]) and not re.match(r"^\d+$", lines[i]):
                match_data["venue"] = lines[i]
                i += 1

            # Next: team1, team2
            teams = []
            scores = []
            while i < min(h2h_start + 100, len(lines)):
                val = lines[i]
                if _DATE_RE.match(val) or "latest result" in val.lower() or "there are no" in val.lower():
                    break
                if re.match(r"^\d+$", val) and len(val) <= 3:
                    scores.append(int(val))
                elif len(val) > 2 and not re.match(r"^\d", val) and val not in ("W", "L", "D"):
                    if len(teams) < 2:
                        teams.append(val)
                elif val in ("W", "L", "D"):
                    pass  # skip result markers between H2H matches
                i += 1

            if len(teams) >= 2:
                match_data["team1"] = teams[0]
                match_data["team2"] = teams[1]
                match_data["scores"] = scores
                h2h["matches"].append(match_data)
            continue

        i += 1

    return h2h


def _extract_form(lines: List[str], team_name: str) -> List[Dict]:
    """Extract latest results for a specific team."""
    form = []
    if not team_name:
        return form

    # Find "Latest results: {team_name}"
    form_start = None
    team_lower = team_name.lower()
    for i, line in enumerate(lines):
        if line.lower().startswith("latest results:") and team_lower in line.lower():
            form_start = i + 1
            break

    if form_start is None:
        return form

    # Skip "All tournaments" label
    if form_start < len(lines) and lines[form_start].lower() == "all tournaments":
        form_start += 1

    # Parse matches: date, venue, team1, team2, scores, W/L/D
    i = form_start
    current = {}
    max_matches = 10
    while i < min(form_start + 120, len(lines)) and len(form) < max_matches:
        line = lines[i]

        # Stop at next section
        if line.lower().startswith("latest results:") and team_lower not in line.lower():
            break
        if line.lower() in ("betting tips:", "odds", "match info", "subscribe to scores24"):
            break
        if "betting tips:" in line.lower():
            break

        date_m = _DATE_RE.match(line)
        if date_m:
            if current.get("date"):
                if current.get("opponent"):
                    form.append(current)
            d, mo, y = date_m.groups()
            if len(y) == 2:
                y = f"20{y}"
            current = {"date": f"{y}-{mo}-{d}"}
            i += 1
            # Venue
            if i < len(lines) and not _DATE_RE.match(lines[i]):
                venue = lines[i]
                if len(venue) < 80 and not re.match(r"^\d+$", venue):
                    current["venue"] = venue
                    i += 1
            # Teams and scores
            teams = []
            scores = []
            result_marker = None
            while i < min(form_start + 120, len(lines)):
                val = lines[i]
                if _DATE_RE.match(val):
                    break
                if val in ("W", "L", "D"):
                    result_marker = val
                    i += 1
                    continue
                if val.lower().startswith("latest results:"):
                    break
                if val.lower() in ("betting tips:", "odds", "match info"):
                    break
                if re.match(r"^\d+$", val) and len(val) <= 3:
                    scores.append(int(val))
                elif (len(val) > 2 and not re.match(r"^\d", val)
                      and val.lower() not in ("all tournaments", "there are no events")):
                    if len(teams) < 2:
                        teams.append(val)
                else:
                    if teams or scores:
                        break
                i += 1

            if len(teams) >= 2:
                current["team1"] = teams[0]
                current["team2"] = teams[1]
                current["scores"] = scores
                current["result"] = result_marker
                # Determine opponent
                if team_lower in teams[0].lower():
                    current["opponent"] = teams[1]
                elif team_lower in teams[1].lower():
                    current["opponent"] = teams[0]
                else:
                    current["opponent"] = teams[1]  # best guess
            continue
        i += 1

    if current.get("opponent"):
        form.append(current)

    return form


def _extract_trends(lines: List[str], home: str, away: str) -> List[Dict]:
    """Extract structured betting tips/trends.

    scores24 trends structure (each tip):
      "{Player/Team} has {action}"          ← description start
      "in {X} of last"                      ← or "in last"
      "{Y}"                                 ← sample size
      "matches." / "games." / etc.          ← context
      "{Bet Name}"                          ← e.g., "Alexander Zverev Win"
      "{odds}"                              ← e.g., "1.35"
    """
    trends = []

    # Find "Betting Tips:" section
    tips_start = None
    for i, line in enumerate(lines):
        if line.lower().startswith("betting tips:"):
            tips_start = i + 1
            break

    if tips_start is None:
        return trends

    # Parse trend categories and individual tips
    current_category = None
    i = tips_start
    while i < min(tips_start + 200, len(lines)):
        line = lines[i]

        # Stop at chat/subscription sections
        if line.lower() in ("subscribe to scores24", "live chat", "betting offers",
                            "there are no messages", "hide chat"):
            break
        if line == "Telegram":
            break

        # Category headers
        if "predictions" in line.lower() or "both teams" in line.lower():
            current_category = line
            i += 1
            continue

        # Skip odds range lines like "1.35 - 3.3" or count lines like "(2)"
        if re.match(r"^\(?\d+\)?$", line) or re.match(r"^\d+\.\d+\s*-\s*\d+\.\d+$", line):
            i += 1
            continue

        # Look for trend description: lines containing "has won", "has scored",
        # "have won", "have scored", "have not lost", "scored", "conceded", etc.
        has_pattern = re.search(
            r"\b(has |have |scored|conceded|won|lost|not lost)\b",
            line, re.I
        )
        if has_pattern and current_category:
            trend = _parse_single_trend_v2(lines, i, current_category)
            if trend:
                trends.append(trend)
                i = trend.pop("_end_idx", i + 1)
                continue

        i += 1

    return trends


def _parse_single_trend_v2(lines: List[str], start: int, category: str) -> Optional[Dict]:
    """Parse a single trend entry with multi-line description.

    Pattern:
      [start]   "Team has won"                   ← description part 1
      [start+1] "in 6 of last" or "in last"      ← stat context
      [start+2] "7"                              ← sample size (sometimes)
      [start+3] "matches."                       ← context qualifier
      [start+4] "Team Win"                       ← bet name
      [start+5] "1.35"                           ← odds

    There may be multiple "in X of last Y" blocks before the bet name.
    """
    desc_parts = []
    hit_count = None
    sample_size = None
    i = start

    # Collect description and stat lines until we find the bet name + odds
    while i < min(start + 20, len(lines)):
        line = lines[i]

        # Try to see if this line is a bet name (followed by odds on next line)
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            try:
                odds_val = float(next_line)
                # Check this looks like a bet name (contains team/player name or market keyword)
                if (len(line) > 3 and not re.match(r"^\d+\.?\d*$", line)
                        and not line.lower().startswith("in ")
                        and line.lower() not in ("matches.", "games.", "home games.",
                                                  "away games.", "games (europa league).")):
                    return {
                        "category": category,
                        "description": " ".join(desc_parts),
                        "bet_name": line,
                        "odds": odds_val,
                        "hit_count": hit_count,
                        "sample_size": sample_size,
                        "hit_rate": round(hit_count / sample_size, 3) if hit_count and sample_size else None,
                        "_end_idx": i + 2,
                    }
            except (ValueError, IndexError):
                pass

        # Extract stats: "in X of last"
        stat_m = re.match(r"in (\d+) of last", line)
        if stat_m:
            hit_count = int(stat_m.group(1))
            desc_parts.append(line)
            i += 1
            # Next line might be the sample size
            if i < len(lines) and re.match(r"^\d+$", lines[i]):
                sample_size = int(lines[i])
                desc_parts.append(lines[i])
                i += 1
            continue

        # "in last" (streak = 100%)
        streak_m = re.match(r"in last", line)
        if streak_m:
            desc_parts.append(line)
            i += 1
            if i < len(lines) and re.match(r"^\d+$", lines[i]):
                n = int(lines[i])
                hit_count = n
                sample_size = n
                desc_parts.append(lines[i])
                i += 1
            continue

        desc_parts.append(line)
        i += 1

    return None


def parse(html: str, url: str) -> List[Dict]:
    """Main parse entry point — dispatches to listing or detail parser."""
    if _is_match_detail(url):
        return _parse_detail_page(html, url)
    else:
        return _parse_listing_page(html, url)
