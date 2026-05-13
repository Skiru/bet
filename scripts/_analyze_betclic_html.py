#!/usr/bin/env python3
"""Deep analysis of Betclic HTML structure across all sport pages.

Reads cached HTML files and extracts DOM patterns, selectors, and data
structures for each sport to guide parser development.

Usage:
    python3 scripts/_analyze_betclic_html.py
"""
import re
from pathlib import Path
from bs4 import BeautifulSoup

CACHE_DIR = Path(__file__).resolve().parent.parent / "betting" / "data" / "html_cache"

def analyze_sport_page(filepath: Path):
    """Analyze a single Betclic sport listing page."""
    html = filepath.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    
    sport = filepath.stem.split("_")[-1]  # e.g., "football"
    
    print(f"\n{'='*80}")
    print(f"SPORT: {sport.upper()} ({filepath.name}, {len(html):,} bytes)")
    print(f"{'='*80}")
    
    # 1. Event cards
    event_cards = soup.select("sports-events-event-card")
    print(f"\n[1] Event cards (sports-events-event-card): {len(event_cards)}")
    
    events = []
    for i, card in enumerate(event_cards):
        event = {}
        
        # Match link
        link = card.select_one("a.cardEvent")
        if link:
            event["href"] = link.get("href", "")
            event["is_live"] = "is-live" in link.get("class", [])
        
        # Team names
        home = card.select_one('[data-qa="contestant-1-label"]')
        away = card.select_one('[data-qa="contestant-2-label"]')
        event["home"] = home.get_text(strip=True) if home else "?"
        event["away"] = away.get_text(strip=True) if away else "?"
        
        # Score
        score = card.select_one('[data-qa="scoreboard-score"]')
        event["score"] = score.get_text(strip=True) if score else None
        
        # League (from breadcrumb)
        breadcrumb_items = card.select("bcdk-breadcrumb-item .breadcrumb_itemLabel")
        event["breadcrumb"] = [b.get_text(strip=True) for b in breadcrumb_items if b.get_text(strip=True)]
        
        # Time
        time_el = card.select_one(".event_infoTime")
        event["time"] = time_el.get_text(strip=True) if time_el else None
        
        # Odds buttons
        odds_labels = card.select("bcdk-bet-button-label.btn_label")
        odds_values = []
        for lbl in odds_labels:
            text = lbl.get_text(strip=True)
            # Skip labels that are team name abbreviations (in the .is-top label)
            if "is-top" in lbl.get("class", []):
                continue
            # Parse odds like "8,25" or "1.50"
            text = text.replace(",", ".").strip()
            try:
                val = float(text)
                odds_values.append(val)
            except ValueError:
                pass
        event["odds"] = odds_values
        
        # Top labels (team abbreviations on buttons)
        top_labels = card.select("bcdk-bet-button-label.btn_label.is-top")
        event["odds_labels"] = [t.get_text(strip=True) for t in top_labels]
        
        # Market count badge
        market_count = card.select_one("sports-events-event-market-count")
        if market_count:
            mc_text = market_count.get_text(strip=True)
            mc_match = re.search(r"\d+", mc_text)
            event["market_count"] = int(mc_match.group()) if mc_match else None
        
        events.append(event)
    
    # Print first 5 events
    for i, ev in enumerate(events[:5]):
        print(f"\n  Event {i+1}:")
        print(f"    Home: {ev['home']}")
        print(f"    Away: {ev['away']}")
        print(f"    Score: {ev.get('score')}")
        print(f"    Time: {ev.get('time')}")
        print(f"    League: {ev.get('breadcrumb')}")
        print(f"    Odds: {ev.get('odds')} ({ev.get('odds_labels')})")
        print(f"    Markets: {ev.get('market_count')}")
        print(f"    Link: {ev.get('href')}")
        print(f"    Live: {ev.get('is_live')}")
    
    if len(events) > 5:
        print(f"\n  ... and {len(events) - 5} more events")
    
    # 2. Competition groups
    print(f"\n[2] Competition groups:")
    groups = soup.select(".groupEvents")
    print(f"  Found {len(groups)} group(s)")
    for i, grp in enumerate(groups[:5]):
        head = grp.select_one(".groupEvents_headTitle")
        cards_in_group = grp.select("sports-events-event-card")
        is_live = "is-live" in grp.get("class", [])
        print(f"  Group {i+1}: '{head.get_text(strip=True) if head else '?'}' ({len(cards_in_group)} events) {'[LIVE]' if is_live else ''}")
    
    # 3. Competition list (sidebar/navigation)
    print(f"\n[3] Competition list (sports-competition-list):")
    comp_lists = soup.select("sports-competition-list")
    print(f"  Found {len(comp_lists)} competition list(s)")
    for cl in comp_lists[:2]:
        items = cl.select("a[href]")
        print(f"  Links in list: {len(items)}")
        for item in items[:8]:
            href = item.get("href", "")
            text = item.get_text(strip=True)
            if text:
                print(f"    → {text[:60]} ({href[:80]})")
    
    # 4. Sports details sections  
    print(f"\n[4] Sports details sections:")
    details = soup.select("sports-details")
    print(f"  Found {len(details)} sports-details section(s)")
    
    # 5. All unique data-qa attributes
    print(f"\n[5] Unique data-qa attributes:")
    data_qa_els = soup.select("[data-qa]")
    qa_counts = {}
    for el in data_qa_els:
        qa = el.get("data-qa")
        qa_counts[qa] = qa_counts.get(qa, 0) + 1
    for qa, count in sorted(qa_counts.items(), key=lambda x: -x[1])[:15]:
        print(f"  {qa}: {count}")
    
    # 6. All links that look like match pages
    print(f"\n[6] Match page links (containing event IDs):")
    all_links = soup.select("a[href]")
    match_links = []
    for a in all_links:
        href = a.get("href", "")
        if re.search(r"-m\d{10,}", href) or re.search(r"-e\d{5,}", href):
            text = a.get_text(strip=True)[:60]
            match_links.append({"href": href, "text": text})
    print(f"  Found {len(match_links)} match links")
    for ml in match_links[:10]:
        print(f"    → {ml['text'][:40]:40s} | {ml['href'][:80]}")
    
    # 7. Button structure for odds
    print(f"\n[7] Odds button structure:")
    buttons = soup.select("button[bcdkbetbutton]")
    print(f"  Found {len(buttons)} bet buttons")
    if buttons:
        btn = buttons[0]
        labels_in_btn = btn.select("bcdk-bet-button-label")
        print(f"  First button has {len(labels_in_btn)} labels:")
        for lbl in labels_in_btn:
            classes = lbl.get("class", [])
            text = lbl.get_text(strip=True)
            print(f"    class={classes} text='{text}'")
        
        # Trends bar
        trends = btn.select("bcdk-bet-button-trends-bar")
        if trends:
            print(f"  Has trends bar: {trends[0].get_text(strip=True)[:50]}")
    
    # 8. Check for pinned competitions
    print(f"\n[8] Pinned competitions:")
    pinned = soup.select("[data-qa^='pinned-competition']")
    for p in pinned[:10]:
        text = p.get_text(strip=True)[:60]
        href = p.get("href", "") or (p.select_one("a") or {}).get("href", "")
        print(f"  {p.get('data-qa')}: '{text}' → {href[:60]}")

    return {
        "sport": sport,
        "event_count": len(events),
        "events": events,
        "match_links": len(match_links),
        "competition_groups": len(groups),
    }


def main():
    print("BETCLIC HTML DEEP ANALYSIS")
    print(f"Cache dir: {CACHE_DIR}")
    
    files = sorted(CACHE_DIR.glob("2026-05-13_betclic_*.html"))
    if not files:
        files = sorted(CACHE_DIR.glob("*_betclic_*.html"))
    
    if not files:
        print("No cached HTML files found!")
        return
    
    print(f"Found {len(files)} cached file(s)")
    
    summaries = []
    for f in files:
        summary = analyze_sport_page(f)
        summaries.append(summary)
    
    # Cross-sport summary
    print(f"\n{'='*80}")
    print("CROSS-SPORT SUMMARY")
    print(f"{'='*80}")
    total_events = 0
    total_links = 0
    for s in summaries:
        total_events += s["event_count"]
        total_links += s["match_links"]
        print(f"  {s['sport']:15s} | {s['event_count']:3d} events | {s['match_links']:3d} match links | {s['competition_groups']:2d} groups")
    print(f"  {'TOTAL':15s} | {total_events:3d} events | {total_links:3d} match links")


if __name__ == "__main__":
    main()
