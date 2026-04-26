#!/usr/bin/env python3
"""Extract O/U, BTTS, and other market odds from BetExplorer match pages using Playwright."""
import json, sys, time
from playwright.sync_api import sync_playwright

MATCHES = [
    {
        "name": "Lech Poznan vs Legia",
        "url": "https://www.betexplorer.com/football/poland/ekstraklasa/lech-poznan-legia/UVOpCzg2/",
        "tabs": ["over-under", "btts"],
    },
    {
        "name": "AC Milan vs Juventus",
        "url": "https://www.betexplorer.com/football/italy/serie-a/ac-milan-juventus/xWjqZDDc/",
        "tabs": ["over-under", "btts"],
    },
    {
        "name": "Galatasaray vs Fenerbahce",
        "url": "https://www.betexplorer.com/football/turkey/super-lig/galatasaray-fenerbahce/YiBu5AtC/",
        "tabs": ["over-under", "btts"],
    },
    {
        "name": "Mainz vs Bayern Munich",
        "url": "https://www.betexplorer.com/football/germany/bundesliga/",
        "tabs": ["1x2"],  # We'll find the match link first
        "search_text": "Mainz",
    },
]

def extract_odds_table(page, tab_name):
    """Click a tab and extract the odds table."""
    results = {}
    
    # Try clicking the tab
    tab_selectors = {
        "over-under": ["a:has-text('O/U')", "a[href*='over-under']", ".odds-tabs a:nth-child(2)"],
        "btts": ["a:has-text('BTTS')", "a[href*='btts']"],
        "1x2": ["a:has-text('1X2')"],
    }
    
    for sel in tab_selectors.get(tab_name, []):
        try:
            el = page.query_selector(sel)
            if el:
                el.click()
                time.sleep(2)
                break
        except Exception:
            continue
    
    # Extract table rows with odds
    rows = page.query_selector_all("table.table-main tr, #odds-data-table tr, .odds-table tr, table tr")
    for row in rows:
        try:
            cells = row.query_selector_all("td")
            text = row.inner_text().strip()
            if text and any(c.isdigit() for c in text):
                results[len(results)] = text
        except Exception:
            continue
    
    return results

def main():
    all_results = {}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        
        for match in MATCHES:
            print(f"\n{'='*60}")
            print(f"MATCH: {match['name']}")
            print(f"{'='*60}")
            
            page = context.new_page()
            
            try:
                page.goto(match["url"], wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
                
                # Handle cookie consent
                for sel in ["#onetrust-accept-btn-handler", "button:has-text('Accept')", "button:has-text('I Accept')", ".cookies-btn"]:
                    try:
                        el = page.query_selector(sel)
                        if el:
                            el.click()
                            time.sleep(1)
                            break
                    except Exception:
                        pass
                
                # If we need to search for the match link first
                if "search_text" in match:
                    link = page.query_selector(f"a:has-text('{match['search_text']}')")
                    if link:
                        href = link.get_attribute("href")
                        if href:
                            full_url = f"https://www.betexplorer.com{href}" if href.startswith("/") else href
                            page.goto(full_url, wait_until="domcontentloaded", timeout=30000)
                            time.sleep(2)
                
                match_results = {}
                
                for tab in match["tabs"]:
                    print(f"\n--- Tab: {tab} ---")
                    
                    # Navigate to the tab via URL hash
                    if tab == "over-under":
                        page.goto(match["url"] + "#over-under;2;", wait_until="domcontentloaded", timeout=30000)
                    elif tab == "btts":
                        page.goto(match["url"] + "#btts;2;", wait_until="domcontentloaded", timeout=30000)
                    
                    time.sleep(3)
                    
                    # Try extracting odds from the page
                    # BetExplorer uses specific data attributes and table structures
                    content = page.content()
                    
                    # Look for odds in the rendered page
                    odds_elements = page.query_selector_all("[data-odd]")
                    if odds_elements:
                        print(f"Found {len(odds_elements)} odds elements")
                        for el in odds_elements[:20]:
                            odd = el.get_attribute("data-odd")
                            text = el.inner_text().strip()
                            if odd:
                                print(f"  Odd: {odd} | Text: {text}")
                    
                    # Also check for table content
                    table = page.query_selector("#sortable-1, .table-main, #odds-data-table")
                    if table:
                        table_text = table.inner_text()
                        lines = [l.strip() for l in table_text.split("\n") if l.strip() and any(c.isdigit() for c in l)]
                        print(f"Table rows ({len(lines)}):")
                        for line in lines[:30]:
                            print(f"  {line}")
                        match_results[tab] = lines
                    else:
                        # Fallback: get all text containing odds-like patterns
                        all_text = page.inner_text("body")
                        import re
                        odds_lines = re.findall(r'(?:Over|Under|Yes|No|BTTS|[0-9]\.[0-9]{2}).*', all_text)
                        if odds_lines:
                            print(f"Fallback odds lines ({len(odds_lines)}):")
                            for line in odds_lines[:20]:
                                print(f"  {line}")
                            match_results[tab] = odds_lines
                        else:
                            print("No odds data found on this tab")
                
                all_results[match["name"]] = match_results
                
            except Exception as e:
                print(f"ERROR: {e}")
            finally:
                page.close()
        
        browser.close()
    
    # Save results
    with open("/Users/mkoziol/projects/bet/betting/data/be_extracted_odds.json", "w") as f:
        json.dump(all_results, f, indent=2)
    print("\nSaved to betting/data/be_extracted_odds.json")

if __name__ == "__main__":
    main()
