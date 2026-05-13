#!/usr/bin/env python3
"""S0.2 — Parse Betclic cached HTML into structured events + odds.

Reads HTML cache files produced by daily_odds_warmup.py (S0.1) and extracts:
- Listing pages: events with teams, league, kickoff, listing odds (1X2/ML)
- Match detail pages: full market data with all selections and odds

Outputs:
  betting/data/betclic_parsed_{date}.json  (structured JSON)
  betting.db → fixtures + odds_history     (DB upsert, unless --no-db)

Usage:
    python3 scripts/parse_betclic_html.py --date 2026-05-13 --verbose
    python3 scripts/parse_betclic_html.py --date 2026-05-13 --no-db --sport football
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from bs4 import BeautifulSoup, Tag

from agent_output import AgentOutput, add_agent_args, add_sport_filter_arg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CACHE_DIR = ROOT_DIR / "betting" / "data" / "html_cache"
OUTPUT_DIR = ROOT_DIR / "betting" / "data"
CORE_SPORTS = ["football", "basketball", "tennis", "volleyball", "hockey"]

# Sports with 3-button 1X2 listing odds (Home / Draw / Away)
THREE_WAY_SPORTS = {"football", "hockey"}

# ---------------------------------------------------------------------------
# Polish locale utilities
# ---------------------------------------------------------------------------


def polish_decimal(text: str) -> float | None:
    """Convert Polish comma-decimal odds text to float.

    "8,25" → 8.25, "1,07" → 1.07, "12" → 12.0
    Returns None on failure.
    """
    cleaned = text.strip().replace("\xa0", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_match_id(href: str) -> str | None:
    """Extract Betclic match ID from URL: m + 13-16 digits."""
    m = re.search(r"m(\d{10,20})", href)
    return f"m{m.group(1)}" if m else None


def extract_competition_id(href: str) -> str | None:
    """Extract Betclic competition ID from URL: c + 3-8 digits."""
    m = re.search(r"c(\d{3,8})", href)
    return f"c{m.group(1)}" if m else None


def parse_ou_line(selection_text: str) -> tuple[str, float | None]:
    """Parse O/U and Yes/No selection labels.

    "Powyżej 2,5" → ("Over", 2.5)
    "Poniżej 9,5" → ("Under", 9.5)
    "Tak" → ("Yes", None)
    "Nie" → ("No", None)
    """
    text = selection_text.strip()
    m = re.match(r"(Powyżej|Poniżej)\s+(\d+[,.]\d+)", text)
    if m:
        direction = "Over" if m.group(1) == "Powyżej" else "Under"
        line = polish_decimal(m.group(2))
        return direction, line
    if text.lower() in ("tak", "yes"):
        return "Yes", None
    if text.lower() in ("nie", "no"):
        return "No", None
    return text, None


# ---------------------------------------------------------------------------
# Market name mapping — Polish → English
# ---------------------------------------------------------------------------

MARKET_NAME_MAP: dict[str, dict[str, str]] = {
    "football": {
        "Wynik meczu (z wyłączeniem dogrywki)": "1X2",
        "Wynik meczu": "1X2",
        "Podwójna Szansa": "Double Chance",
        "Gole Powyżej/Poniżej": "Goals O/U",
        "Oba zespoły strzelą gola": "BTTS",
        "1. połowa Wynik": "1st Half Result",
        "Dokładny wynik": "Correct Score",
        "Która drużyna strzeli pierwszego gola?": "First to Score",
        "Bezpieczny wynik": "Safe Result",
        "Połowa/Koniec meczu": "HT/FT",
        "Zwycięstwo do zera": "Win to Nil",
        "Remis i oba strzelą": "Draw & BTTS",
        "Strzelec gola (dowolny)": "Anytime Goalscorer",
        "Strzelec pierwszego gola": "First Goalscorer",
        "Strzelec ostatniego gola": "Last Goalscorer",
        "Strzelec 2+ goli": "2+ Goals Scorer",
        "Parzyste/Nieparzyste gole": "Odd/Even Goals",
        "Multi-Gol": "Multi-Goal",
        "Pierwszy gol - metoda": "First Goal Method",
        "Ostatni gol - metoda": "Last Goal Method",
        "Handicap europejski": "European Handicap",
        "Handicap azjatycki": "Asian Handicap",
        "Remis nie stawia": "Draw No Bet",
        "Rzuty rożne Powyżej/Poniżej": "Corners O/U",
        "Kartki Powyżej/Poniżej": "Cards O/U",
        "Strzały na bramkę Powyżej/Poniżej": "Shots on Target O/U",
        "Faule Powyżej/Poniżej": "Fouls O/U",
        "Przewaga": "Win by N or Win",
    },
    "basketball": {
        "Zwycięzca meczu": "ML",
        "Wynik handicap": "Handicap",
        "Suma punktów": "Total Points",
        "Przewaga": "Win by N or Win",
        "Margines zwycięstwa": "Winning Margin",
        "Parzyste/Nieparzyste": "Odd/Even Points",
    },
    "tennis": {
        "Zwycięzca meczu": "ML",
        "Łączna liczba gemów": "Total Games",
        "Wynik w setach": "Set Score",
        "Handicap setowy": "Set Handicap",
        "Czy obaj zawodnicy wygrają seta": "Both Win a Set",
        "Czy obaj wygrają seta": "Both Win a Set",
        "Handicap gemowy": "Game Handicap",
    },
    "volleyball": {
        "Zwycięzca meczu": "ML",
        "Handicap setowy": "Set Handicap",
        "Suma punktów": "Total Points",
        "Wynik w setach": "Set Score",
        "Handicap punktowy": "Point Handicap",
        "Parzyste/Nieparzyste": "Odd/Even Points",
    },
    "hockey": {
        "Wynik meczu (czas regulam.)": "1X2 (Reg. Time)",
        "Wynik meczu": "1X2 (Reg. Time)",
        "Zwycięzca meczu": "ML (incl. OT)",
        "Gole Powyżej/Poniżej": "Goals O/U",
        "Puck Line": "Puck Line",
        "Oba zespoły strzelą gola": "BTTS",
        "Podwójna Szansa": "Double Chance",
        "Dokładny wynik": "Correct Score",
    },
}

# Dynamic market patterns: "{Team} Something" → strip team name and match
_DYNAMIC_PATTERNS: dict[str, str] = {
    "Gole Powyżej/Poniżej": "Team Goals O/U",
    "Suma punktów": "Team Total Points",
    "Rzuty rożne Powyżej/Poniżej": "Team Corners O/U",
    "Kartki Powyżej/Poniżej": "Team Cards O/U",
    "Zwycięzca": "Period Winner",
}


def map_market_name(
    polish_name: str,
    sport: str,
    home_team: str = "",
    away_team: str = "",
) -> str:
    """Map Polish market name to English equivalent.

    Handles dynamic team-prefixed names like "{Team} Gole Powyżej/Poniżej".
    Falls back to "[PL] {name}" if no mapping found.
    """
    name = polish_name.strip()
    sport_map = MARKET_NAME_MAP.get(sport, {})

    # Direct lookup
    if name in sport_map:
        return sport_map[name]

    # Strip team names for dynamic markets
    stripped = name
    for team in (home_team, away_team):
        if team and team in stripped:
            stripped = stripped.replace(team, "").strip()

    if stripped in sport_map:
        return sport_map[stripped]

    # Check dynamic patterns (partial match on the base pattern)
    for pattern, en_name in _DYNAMIC_PATTERNS.items():
        if pattern in name:
            return en_name

    # Quarter/set/period patterns
    qm = re.match(r"(\d+)\.\s*(kw|set|tercja|poł)\w*\s+(.+)", name)
    if qm:
        period_num = qm.group(1)
        period_type = qm.group(2)
        base = qm.group(3).strip()
        base_en = sport_map.get(base, base)
        period_map = {"kw": "Quarter", "set": "Set", "tercja": "Period", "poł": "Half"}
        period_en = period_map.get(period_type, period_type)
        return f"{period_en} {period_num} {base_en}"

    return f"[PL] {name}"


# ---------------------------------------------------------------------------
# Listing page parser
# ---------------------------------------------------------------------------


def _extract_button_odds(button: Tag) -> tuple[str, float | None]:
    """Extract selection name and odds from a Betclic bet button.

    Button structure:
      bcdk-bet-button-label.btn_label.is-top → selection name (split span.ellipsis + span.clip)
      bcdk-bet-button-label.btn_label (no is-top) → odds value
    """
    sel_name = ""
    odds_val = None

    for label_el in button.find_all("bcdk-bet-button-label"):
        classes = label_el.get("class", [])
        if "is-top" in classes:
            # Use separator to avoid "ManawatuJets" from split span.ellipsis + span.clip
            sel_name = label_el.get_text(separator=" ", strip=True)
            # Collapse multiple spaces
            sel_name = re.sub(r"\s+", " ", sel_name).strip()
        else:
            odds_val = polish_decimal(label_el.get_text(strip=True))

    return sel_name, odds_val


def parse_listing_page(
    html_path: Path,
    sport: str,
    date: str,
    out: AgentOutput,
) -> list[dict]:
    """Parse a Betclic listing page and extract events with listing odds."""
    html = html_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")

    cards = soup.find_all("sports-events-event-card")
    if not cards:
        out.warning(f"No event cards found in {html_path.name}")
        return []

    events: list[dict] = []
    seen_ids: set[str] = set()

    for card in cards:
        link = card.find("a", class_="cardEvent")
        if not link:
            continue

        href = link.get("href", "")
        match_id = extract_match_id(href)
        comp_id = extract_competition_id(href)

        # Team names — extract early so dedup fallback can use them
        home_el = card.find(attrs={"data-qa": "contestant-1-label"})
        away_el = card.find(attrs={"data-qa": "contestant-2-label"})
        home_team = home_el.get_text(strip=True) if home_el else ""
        away_team = away_el.get_text(strip=True) if away_el else ""

        # Deduplicate by match_id (primary) or team pair (fallback)
        if match_id:
            if match_id in seen_ids:
                continue
            seen_ids.add(match_id)
        else:
            pair_key = (home_team, away_team)
            if pair_key in seen_ids:
                continue
            seen_ids.add(pair_key)

        if not home_team or not away_team:
            out.warning(f"Missing team name in {href}")
            continue

        # League name — from last breadcrumb with is-ellipsis
        comp_name = ""
        breadcrumb = card.find("bcdk-breadcrumb-item", class_="is-ellipsis")
        if breadcrumb:
            label_el = breadcrumb.find(class_="breadcrumb_itemLabel")
            if label_el:
                comp_name = label_el.get_text(strip=True)
                # Clean up "• Dzień N" suffixes
                comp_name = re.sub(r"\s*[•·]\s*Dzień\s*\d+.*$", "", comp_name).strip()
                comp_name = re.sub(r"\s*[•·]\s*Grupa\s+\w+.*$", "", comp_name).strip()

        # Live status
        link_classes = link.get("class", [])
        is_live = "is-live" in link_classes

        # Kickoff time
        kickoff = ""
        if is_live:
            kickoff = f"{date}T00:00:00"  # approximate for live
        else:
            hour_el = card.find(class_="scoreboard_hour") or card.find(class_="event_infoTime")
            if hour_el:
                time_text = hour_el.get_text(strip=True)
                tm = re.match(r"(\d{1,2}:\d{2})", time_text)
                if tm:
                    kickoff = f"{date}T{tm.group(1)}:00"

        if not kickoff:
            kickoff = f"{date}T00:00:00"

        # Live score
        live_score = None
        if is_live:
            score_el = card.find(attrs={"data-qa": "scoreboard-score"})
            if score_el:
                scores = score_el.find_all("span", class_=re.compile(r"scoreboard_score"))
                if len(scores) >= 2:
                    live_score = f"{scores[0].get_text(strip=True)}-{scores[1].get_text(strip=True)}"

        # Market count
        market_count = None
        bets_num = card.find(class_="event_betsNum")
        if bets_num:
            mc = re.search(r"(\d+)", bets_num.get_text())
            if mc:
                market_count = int(mc.group(1))

        # Listing odds from bet buttons
        listing_odds: list[dict] = []
        buttons = card.find_all("button", attrs={"betbuttontype": "odd"})

        if sport in THREE_WAY_SPORTS:
            # 1X2: positions are Home, Draw, Away
            position_labels = ["1", "X", "2"]
        else:
            # ML: positions are Home, Away
            position_labels = ["Home", "Away"]

        for i, btn in enumerate(buttons):
            sel_name, odds_val = _extract_button_odds(btn)
            if odds_val is not None:
                selection = position_labels[i] if i < len(position_labels) else sel_name
                listing_odds.append({
                    "selection": selection,
                    "label": sel_name,
                    "odds": odds_val,
                })

        events.append({
            "sport": sport,
            "match_id": match_id,
            "competition_id": comp_id,
            "competition_name": comp_name,
            "home_team": home_team,
            "away_team": away_team,
            "kickoff": kickoff,
            "is_live": is_live,
            "live_score": live_score,
            "market_count": market_count,
            "listing_odds": listing_odds,
            "url": href,
        })

    out.event(
        "listing_parsed",
        sport=sport,
        events=len(events),
        live=sum(1 for e in events if e["is_live"]),
        with_odds=sum(1 for e in events if e["listing_odds"]),
    )
    return events


# ---------------------------------------------------------------------------
# Match detail page parser
# ---------------------------------------------------------------------------


def parse_match_detail_page(
    html_path: Path,
    sport: str,
    out: AgentOutput,
) -> tuple[str, str, list[dict]]:
    """Parse a Betclic match detail page and extract all markets.

    Returns (home_team, away_team, markets_list).
    """
    html = html_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")

    # Extract team names from the match detail header
    c1 = soup.find(attrs={"data-qa": "contestant-1-label"})
    c2 = soup.find(attrs={"data-qa": "contestant-2-label"})
    home_team = c1.get_text(strip=True) if c1 else ""
    away_team = c2.get_text(strip=True) if c2 else ""

    market_sections = soup.find_all("sports-markets-single-market")
    if not market_sections:
        out.warning(f"No market sections in {html_path.name}")
        return home_team, away_team, []

    markets: list[dict] = []

    for section in market_sections:
        title_el = section.find(class_="marketBox_headTitle")
        if not title_el:
            continue

        market_name_pl = title_el.get_text(strip=True)
        market_name_en = map_market_name(market_name_pl, sport, home_team, away_team)

        # Find selections — each .marketBox_lineSelection contains one selection row
        line_selections = section.find_all(class_="marketBox_lineSelection")

        # Also find labels for this market (for O/U lines etc.)
        all_labels = section.find_all(class_="marketBox_label")

        selections: list[dict] = []

        if line_selections:
            # Paired structure: marketBox_label + marketBox_lineSelection side by side
            for idx, line_sel in enumerate(line_selections):
                btn = line_sel.find("button", attrs={"betbuttontype": "odd"})
                if not btn:
                    continue

                sel_name, odds_val = _extract_button_odds(btn)
                if odds_val is None:
                    continue

                # Try to get label from corresponding marketBox_label
                label_text = ""
                if idx < len(all_labels):
                    label_text = all_labels[idx].get_text(strip=True)

                # Parse O/U line from label
                direction, line_val = parse_ou_line(label_text) if label_text else (sel_name, None)

                selections.append({
                    "label": label_text or sel_name,
                    "selection": direction,
                    "odds": odds_val,
                    "line": line_val,
                })
        else:
            # Flat layout (e.g., 1X2 main) — buttons directly in marketBox_body
            buttons = section.find_all("button", attrs={"betbuttontype": "odd"})
            for btn in buttons:
                sel_name, odds_val = _extract_button_odds(btn)
                if odds_val is None:
                    continue
                selections.append({
                    "label": sel_name,
                    "selection": sel_name,
                    "odds": odds_val,
                    "line": None,
                })

        if selections:
            markets.append({
                "market_name_pl": market_name_pl,
                "market_name_en": market_name_en,
                "sport": sport,
                "selections": selections,
            })

    out.event(
        "detail_parsed",
        sport=sport,
        home=home_team,
        away=away_team,
        markets=len(markets),
        selections=sum(len(m["selections"]) for m in markets),
    )
    return home_team, away_team, markets


# ---------------------------------------------------------------------------
# DB integration
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def persist_to_db(
    events: list[dict],
    detail_markets: dict[str, tuple[str, str, list[dict]]],
    conn,
    out: AgentOutput,
    *,
    date: str,
) -> dict:
    """Upsert fixtures + odds from parsed data into the DB."""
    from bet.db.repositories import (
        SportRepo,
        TeamRepo,
        CompetitionRepo,
        FixtureRepo,
        OddsRepo,
    )
    from bet.db.models import Fixture, OddsRecord

    sport_repo = SportRepo(conn)
    team_repo = TeamRepo(conn)
    comp_repo = CompetitionRepo(conn)
    fixture_repo = FixtureRepo(conn)
    odds_repo = OddsRepo(conn)

    metrics = {
        "fixtures_upserted": 0,
        "odds_listing_saved": 0,
        "odds_detail_saved": 0,
        "skipped_no_sport": 0,
    }

    fixture_id_map: dict[str, int] = {}  # match_id → fixture_id

    for ev in events:
        try:
            sport = sport_repo.get_by_name(ev["sport"])
            if not sport or sport.id is None:
                metrics["skipped_no_sport"] += 1
                continue

            comp_id = None
            if ev["competition_name"]:
                comp_id = comp_repo.find_or_create(
                    name=ev["competition_name"],
                    sport_id=sport.id,
                )

            home = team_repo.find_or_create(name=ev["home_team"], sport_id=sport.id)
            away = team_repo.find_or_create(name=ev["away_team"], sport_id=sport.id)

            fixture = Fixture(
                id=None,
                sport_id=sport.id,
                competition_id=comp_id,
                home_team_id=home.id,
                away_team_id=away.id,
                kickoff=ev["kickoff"],
                status="live" if ev["is_live"] else "scheduled",
                external_id=ev["match_id"] or "",
                source="betclic",
                fetched_at=_now(),
            )
            fid = fixture_repo.upsert(fixture)
            metrics["fixtures_upserted"] += 1

            if ev["match_id"]:
                fixture_id_map[ev["match_id"]] = fid

            # Save listing odds
            market_name = "1X2" if ev["sport"] in THREE_WAY_SPORTS else "ML"
            for sel in ev.get("listing_odds", []):
                odds_repo.save(OddsRecord(
                    id=None,
                    fixture_id=fid,
                    bookmaker="betclic",
                    market=market_name,
                    selection=sel["selection"],
                    odds=sel["odds"],
                    fetched_at=_now(),
                ))
                metrics["odds_listing_saved"] += 1
        except Exception as exc:
            logger.warning("Failed to persist event %s: %s", ev.get("match_id", "?"), exc)
            continue

    # Save match detail odds — match by team names
    for sport_name, (home, away, markets) in detail_markets.items():
        if not home or not away or not markets:
            continue

        sport = sport_repo.get_by_name(sport_name)
        if not sport or sport.id is None:
            continue

        # Find fixture_id by matching team names
        fixture = fixture_repo.get_by_teams_and_date(home, away, date, sport.id)
        if not fixture or fixture.id is None:
            # Try partial matching via events list
            fid = None
            for ev in events:
                if ev["sport"] == sport_name:
                    if len(home) >= 4 and len(away) >= 4 and \
                       (home in ev["home_team"] or ev["home_team"] in home) and \
                       (away in ev["away_team"] or ev["away_team"] in away):
                        fid = fixture_id_map.get(ev["match_id"])
                        break
            if not fid:
                out.warning(f"No fixture match for detail page: {home} vs {away}")
                continue
        else:
            fid = fixture.id

        for mkt in markets:
            for sel in mkt["selections"]:
                odds_repo.save(OddsRecord(
                    id=None,
                    fixture_id=fid,
                    bookmaker="betclic",
                    market=mkt["market_name_en"],
                    selection=sel["selection"],
                    odds=sel["odds"],
                    line=sel.get("line"),
                    fetched_at=_now(),
                ))
                metrics["odds_detail_saved"] += 1

    return metrics


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------


def write_output_json(data: dict, date: str) -> Path:
    """Write parsed data to JSON file."""
    out_path = OUTPUT_DIR / f"betclic_parsed_{date}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Parse Betclic cached HTML into structured events + odds",
    )
    parser.add_argument("--date", required=True, help="Date to parse (YYYY-MM-DD)")
    parser.add_argument("--no-db", action="store_true", help="Skip DB writes, JSON only")
    add_agent_args(parser)
    add_sport_filter_arg(parser)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    out = AgentOutput(
        "s0_betclic_parse",
        verbose=args.verbose,
        stop_on_error=args.stop_on_error,
    )

    date = args.date
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        parser.error("--date must be YYYY-MM-DD")
    sports = [args.sport] if args.sport else CORE_SPORTS

    all_events: list[dict] = []
    all_detail_markets: dict[str, tuple[str, str, list[dict]]] = {}
    sport_summaries: dict[str, dict] = {}

    for sport in sports:
        # Parse listing page
        listing_path = CACHE_DIR / f"{date}_betclic_{sport}.html"
        events: list[dict] = []
        if listing_path.exists():
            events = parse_listing_page(listing_path, sport, date, out)
        else:
            out.warning(f"No listing HTML for {sport}: {listing_path.name}")

        # Parse match detail page
        detail_path = CACHE_DIR / f"{date}_betclic_match_{sport}.html"
        detail_home, detail_away, detail_mkts = "", "", []
        if detail_path.exists():
            detail_home, detail_away, detail_mkts = parse_match_detail_page(
                detail_path, sport, out
            )
            all_detail_markets[sport] = (detail_home, detail_away, detail_mkts)
        else:
            logger.debug("No match detail HTML for %s", sport)

        all_events.extend(events)
        sport_summaries[sport] = {
            "events": list(events),
            "markets": detail_mkts,
            "event_count": len(events),
            "market_count": len(detail_mkts),
            "detail_match": f"{detail_home} vs {detail_away}" if detail_home else None,
        }

    # DB persistence
    db_metrics: dict = {}
    if not args.no_db:
        try:
            from bet.db.connection import get_db
            with get_db() as conn:
                db_metrics = persist_to_db(all_events, all_detail_markets, conn, out, date=date)
        except Exception as exc:
            out.error(f"DB write failed: {exc}", recoverable=True)
            db_metrics = {"error": str(exc)}

    # JSON output
    output_data = {
        "date": date,
        "parsed_at": _now(),
        "sports": sport_summaries,
        "totals": {
            "total_events": len(all_events),
            "total_markets": sum(s["market_count"] for s in sport_summaries.values()),
            "sports_parsed": len(sport_summaries),
            "sports_with_listing": sum(1 for s in sport_summaries.values() if s["event_count"] > 0),
            "sports_with_detail": sum(1 for s in sport_summaries.values() if s["market_count"] > 0),
            "live_events": sum(1 for e in all_events if e["is_live"]),
        },
    }
    json_path = write_output_json(output_data, date)
    logger.info("JSON output: %s", json_path)

    # AGENT_SUMMARY
    total_events = output_data["totals"]["total_events"]
    sports_with_listing = output_data["totals"]["sports_with_listing"]
    sports_requested = len(sports)

    if total_events == 0:
        verdict = "FAILED"
    elif sports_with_listing < sports_requested:
        verdict = "PARTIAL"
    else:
        verdict = "OK"

    out.summary(
        verdict=verdict,
        metrics={
            **output_data["totals"],
            **db_metrics,
        },
        issues=[],
    )


if __name__ == "__main__":
    main()
