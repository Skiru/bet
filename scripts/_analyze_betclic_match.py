#!/usr/bin/env python3
"""Focused analysis of Betclic MATCH DETAIL page structure.

Examines: tabs, market groups, odds structure, MyCombi.
"""
from pathlib import Path
from bs4 import BeautifulSoup

CACHE_DIR = Path(__file__).resolve().parent.parent / "betting" / "data" / "html_cache"


def analyze_match(filepath: Path):
    html = filepath.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    print(f"File: {filepath.name} ({len(html):,} bytes)")

    # 1. TABS
    print("\n=== MARKET TABS ===")
    tab_items = soup.select("[data-qa='tab-btn']")
    for i, tab in enumerate(tab_items):
        text = tab.get_text(strip=True)
        is_active = "isActive" in (tab.get("class") or [])
        print(f"  Tab {i}: '{text}' {'[ACTIVE]' if is_active else ''}")

    # 2. MARKET SECTIONS (sports-markets-single-market)
    print("\n=== MARKET SECTIONS (sports-markets-single-market) ===")
    markets = soup.select("sports-markets-single-market")
    for i, mkt in enumerate(markets):
        head = mkt.select_one(".marketBox_headTitle")
        title = head.get_text(strip=True) if head else "?"
        
        # Odds in this market
        labels = mkt.select(".marketBox_label")
        odds_spans = mkt.select(".marketBox_lineSelection")
        
        label_texts = [l.get_text(strip=True) for l in labels]
        odds_texts = []
        for os in odds_spans:
            btn = os.select_one("bcdk-bet-button-label.btn_label:not(.is-top)")
            if btn:
                odds_texts.append(btn.get_text(strip=True))
        
        is_cols = ""
        body = mkt.select_one(".marketBox_body")
        if body:
            body_classes = body.get("class", [])
            if "is-3col" in body_classes:
                is_cols = "[3-col]"
            elif "is-2col" in body_classes:
                is_cols = "[2-col]"
            elif "is-main" in body_classes:
                is_cols = "[main]"
        
        print(f"\n  Market {i}: {title} {is_cols}")
        for j, (lbl, odd) in enumerate(zip(label_texts, odds_texts)):
            print(f"    {lbl:40s} → {odd}")
        if len(label_texts) > len(odds_texts):
            for lbl in label_texts[len(odds_texts):]:
                print(f"    {lbl:40s} → (no odds)")

    # 3. MYCOMBI (bet builder)
    print("\n=== MYCOMBI (bet builder) ===")
    combi_cards = soup.select("sports-my-combi-card")
    print(f"  Found {len(combi_cards)} MyCombi cards")
    for i, card in enumerate(combi_cards):
        title = card.select_one(".market_title, [class*='title']")
        odds_el = card.select_one("[class*='odds']")
        labels = card.select(".market_odds bcdk-bet-button-label.btn_label:not(.is-top)")
        top_labels = card.select(".market_odds bcdk-bet-button-label.btn_label.is-top")
        
        title_text = title.get_text(strip=True) if title else "?"
        
        top_texts = [t.get_text(strip=True) for t in top_labels]
        odds_texts = [l.get_text(strip=True) for l in labels]
        
        print(f"  Card {i}: {title_text}")
        for t, o in zip(top_texts, odds_texts):
            print(f"    {t:30s} → {o}")

    # 4. MARKET CONTAINER STRUCTURE
    print("\n=== MARKET CONTAINER HIERARCHY ===")
    match_markets = soup.select("sports-match-markets")
    print(f"  sports-match-markets: {len(match_markets)}")
    
    matrix_markets = soup.select("sports-matrix-markets")
    print(f"  sports-matrix-markets: {len(matrix_markets)}")
    
    match_page = soup.select_one("sports-match-page-desktop")
    if match_page:
        # Find direct children components
        children = [c.name for c in match_page.children if hasattr(c, 'name') and c.name and '-' in c.name]
        print(f"  sports-match-page-desktop children: {children}")

    # 5. TAB CONTENT STRUCTURE
    print("\n=== TAB CONTENT AREAS ===")
    # Look for container with is-active / is-visible patterns
    for attr in ["is-active", "is-visible", "active"]:
        active_els = soup.select(f"[class*='{attr}']")
        for el in active_els[:5]:
            if el.name and '-' in el.name:
                print(f"  {el.name} class={el.get('class')} (has {attr})")

    # 6. FORM RESULTS (last 5 matches)
    print("\n=== FORM / LAST RESULTS ===")
    form = soup.select("sports-events-event-form-results")
    print(f"  Form result sections: {len(form)}")
    for fr in form:
        items = fr.select("[class*='result'], [class*='form']")
        texts = [i.get_text(strip=True) for i in items if i.get_text(strip=True)]
        print(f"  Results: {texts[:10]}")

    # 7. BREADCRUMB (league info)
    print("\n=== BREADCRUMB (league path) ===")
    breadcrumbs = soup.select("bcdk-breadcrumb-item .breadcrumb_itemLabel")
    for b in breadcrumbs:
        print(f"  → {b.get_text(strip=True)}")


def main():
    # Find match files
    files = sorted(CACHE_DIR.glob("*_betclic_match_*.html"))
    if not files:
        print("No match detail files found. Run _fetch_betclic_match.py first.")
        return
    
    for f in files:
        analyze_match(f)
        print()


if __name__ == "__main__":
    main()
