"""Adapter for Betclic (Angular SPA structure).

Betclic uses Angular components with specific CSS classes:
- sports-events-event-card / .cardEvent: event cards
- .scoreboard_contestantLabel: team names (contestant-1 = home, contestant-2 = away)
- .scoreboard_hour: match time
- .btn_label: odds values (excluding .is-top which are selection names)
- .breadcrumb_itemLabel: competition info
"""
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from .raw_adapter import parse as raw_parse

ODDS_RE = re.compile(r"\b\d+[.,]\d{2}\b")


def parse(html: str, url: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Strategy 1: find all contestant-1 / contestant-2 label pairs via data-qa
    home_labels = soup.find_all(attrs={"data-qa": "contestant-1-label"})
    away_labels = soup.find_all(attrs={"data-qa": "contestant-2-label"})

    if home_labels and away_labels and len(home_labels) == len(away_labels):
        for home_el, away_el in zip(home_labels, away_labels):
            home = home_el.get_text(strip=True)
            away = away_el.get_text(strip=True)
            if not home or not away or len(home) < 2 or len(away) < 2:
                continue

            # Walk up to find the enclosing card/link for time and odds
            card = home_el
            for _ in range(15):
                card = card.parent
                if card is None:
                    break
                classes = card.get("class") or []
                tag_name = card.name or ""
                if "cardEvent" in " ".join(classes) or tag_name == "sports-events-event-card":
                    break

            time = None
            odds = []
            competition = ""
            match_url = ""

            if card:
                # Extract time
                time_el = card.find(class_="scoreboard_hour")
                if time_el:
                    time = time_el.get_text(strip=True)

                # Extract competition from breadcrumbs
                for bc in card.find_all(class_="breadcrumb_itemLabel"):
                    t = bc.get_text(strip=True)
                    if t and len(t) > 2:
                        competition = t
                        break

                # Extract odds from btn_label (skip is-top labels)
                for btn in card.find_all(class_="btn_label"):
                    btn_classes = btn.get("class") or []
                    if "is-top" in btn_classes:
                        continue
                    text = btn.get_text(strip=True).replace(",", ".")
                    try:
                        val = float(text)
                        if 1.01 <= val <= 100.0:
                            odds.append(str(round(val, 2)))
                    except (ValueError, TypeError):
                        continue

                # Extract match URL
                link_el = card.find("a", href=True)
                if link_el:
                    href = link_el["href"]
                    if href.startswith("/"):
                        match_url = f"https://www.betclic.pl{href}"
                    else:
                        match_url = href

            results.append({
                "home": home,
                "away": away,
                "time": time,
                "odds": odds,
                "competition": competition,
                "match_url": match_url,
                "source_url": url,
                "raw": f"{home} - {away} ({', '.join(odds)})",
            })

    # Strategy 2: fallback — find scoreboard_contestantLabel class pairs
    if not results:
        labels = soup.find_all(class_="scoreboard_contestantLabel")
        for i in range(0, len(labels) - 1, 2):
            home = labels[i].get_text(strip=True)
            away = labels[i + 1].get_text(strip=True)
            if home and away and len(home) >= 2 and len(away) >= 2:
                results.append({
                    "home": home,
                    "away": away,
                    "time": None,
                    "odds": [],
                    "source_url": url,
                    "raw": f"{home} - {away}",
                })

    if results:
        from adapters import dedup_results
        return dedup_results(
            results,
            key_fn=lambda r: (r.get("home"), r.get("away")),
        )

    return raw_parse(html, url)
