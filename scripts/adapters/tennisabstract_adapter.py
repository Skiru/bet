"""TennisAbstract adapter — parses Elo rating tables from tennisabstract.com.

This source doesn't contain match fixtures but provides Elo ratings and
surface-specific Elo (hard=hElo, clay=cElo, grass=gElo) for player comparison.

Table structure (table index 5 for ATP, 6 for WTA):
  Columns: Elo Rank, Player, Age, Elo, hElo Rank, hElo, cElo Rank, cElo,
           gElo Rank, gElo, Peak Elo, Peak Month, ATP Rank, Log diff
"""
import logging
from typing import List, Dict
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)


def parse(html: str, url: str) -> List[Dict]:
    """Parse TennisAbstract Elo ratings page.

    Returns player rating entries (not match fixtures) that can be used
    for player lookup during S3 analysis.
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Determine if ATP or WTA from URL
    tour = "atp" if "atp" in url.lower() else "wta"

    # The Elo table has id="reportable" and class="tablesorter"
    elo_table = soup.find("table", id="reportable") or soup.find("table", class_="tablesorter")
    if not elo_table:
        # Fallback: find largest table by direct row count
        tables = soup.find_all("table")
        for t in tables:
            trs = t.find_all("tr", recursive=False)
            if len(trs) > 100:
                elo_table = t
                break

    if not elo_table:
        logger.warning("[tennisabstract] No Elo table found in %s", url)
        return results

    trs = elo_table.find_all("tr")
    # Find header row to get column indices
    header_cells = []
    data_start = 0
    for i, tr in enumerate(trs):
        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if any("Elo" in c for c in cells) and any("Player" in c for c in cells):
            header_cells = cells
            data_start = i + 1
            break

    if not header_cells:
        # Fallback: assume header is embedded in data rows
        data_start = 0

    # Build column index map from headers for robust parsing
    col_idx = {}
    for i, h in enumerate(header_cells):
        h_clean = h.strip()
        if h_clean:
            col_idx[h_clean] = i

    def _col(name, cells_list, cast=float):
        """Safely extract value from cells by column name."""
        idx = col_idx.get(name)
        if idx is None or idx >= len(cells_list):
            return None
        val = cells_list[idx].strip()
        if not val:
            return None
        try:
            return cast(val)
        except (ValueError, TypeError):
            return None

    for tr in trs[data_start:]:
        cells = [c.get_text(strip=True).replace("\xa0", " ") for c in tr.find_all(["td", "th"])]
        if len(cells) < 10:
            continue

        try:
            rank = int(cells[0])
        except (ValueError, IndexError):
            continue

        player = cells[1] if len(cells) > 1 else ""
        if not player or len(player) < 3:
            continue

        try:
            age = float(cells[2]) if cells[2] else None
            elo = _col("Elo", cells) if col_idx else (float(cells[3]) if cells[3] else None)
        except (ValueError, IndexError):
            continue

        # Surface-specific Elo ratings (use header map if available)
        if col_idx:
            h_elo = _col("hElo", cells)
            c_elo = _col("cElo", cells)
            g_elo = _col("gElo", cells)
            peak_elo = _col("Peak Elo", cells) or _col("Peak", cells)
            atp_rank = _col("ATP Rank", cells, cast=int) or _col("Rank", cells, cast=int)
        else:
            # Fallback hardcoded indices (assumes standard 14-column layout)
            h_elo = None
            c_elo = None
            g_elo = None
            try:
                h_elo = float(cells[5]) if len(cells) > 5 and cells[5] else None
                c_elo = float(cells[7]) if len(cells) > 7 and cells[7] else None
                g_elo = float(cells[9]) if len(cells) > 9 and cells[9] else None
            except (ValueError, IndexError):
                pass
            peak_elo = None
            atp_rank = None
            try:
                peak_elo = float(cells[10]) if len(cells) > 10 and cells[10] else None
                atp_rank = int(cells[12]) if len(cells) > 12 and cells[12] else None
            except (ValueError, IndexError):
                pass

        result = {
            "home": player,
            "away": f"{tour.upper()} Elo #{rank}",
            "time": None,
            "source_url": url,
            "raw": f"{player} | Elo {elo:.0f}" if elo else player,
            "sport": "tennis",
            "source_type": "tennisabstract_elo",
            "elo_rank": rank,
            "elo_rating": elo,
        }

        if age:
            result["player_age"] = age
        if h_elo:
            result["hard_elo"] = h_elo
        if c_elo:
            result["clay_elo"] = c_elo
        if g_elo:
            result["grass_elo"] = g_elo
        if peak_elo:
            result["peak_elo"] = peak_elo
        if atp_rank:
            result["official_rank"] = atp_rank
        result["tour"] = tour
        result["source"] = "tennisabstract.com"
        result["_elo_only"] = True

        results.append(result)

    logger.info("[tennisabstract] Parsed %d %s Elo ratings from %s", len(results), tour.upper(), url)
    return results
