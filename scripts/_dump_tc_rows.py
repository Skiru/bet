#!/usr/bin/env python3
"""Quick dump of TotalCorner table row structure."""
import random
import sys

try:
    from scripts.stealth_utils import USER_AGENTS, BROWSER_ARGS
except ImportError:
    USER_AGENTS = ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"]
    BROWSER_ARGS = ['--disable-blink-features=AutomationControlled']

from playwright.sync_api import sync_playwright

try:
    from playwright_stealth import Stealth
except ImportError:
    Stealth = None

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
    ctx = browser.new_context(user_agent=random.choice(USER_AGENTS), viewport={"width": 1920, "height": 1080})
    page = ctx.new_page()
    if Stealth:
        Stealth().apply_stealth_sync(page)

    page.goto("https://www.totalcorner.com/match/today", wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(5000)

    # Dump first 5 data rows from the table
    rows_data = page.evaluate("""() => {
        const table = document.querySelector('#inplay_match_table');
        if (!table) return {error: 'no table found'};
        
        // Get header row
        const headerRow = table.querySelector('tr');
        const headers = headerRow ? Array.from(headerRow.querySelectorAll('th')).map(th => th.textContent.trim()) : [];
        
        // Get first 5 data rows (skip header)
        const dataRows = Array.from(table.querySelectorAll('tr')).slice(1, 8);
        const rows = dataRows.map(row => {
            const cells = Array.from(row.querySelectorAll('td, th'));
            return {
                className: row.className || '',
                cellCount: cells.length,
                cells: cells.map(c => ({
                    class: c.className || '',
                    text: c.textContent.trim().substring(0, 80),
                    html: c.innerHTML.substring(0, 200),
                    colspan: c.getAttribute('colspan') || '',
                })),
                id: row.getAttribute('data-id') || row.id || '',
                onclick: (row.getAttribute('onclick') || '').substring(0, 100),
            };
        });
        
        return {headers, rowCount: table.rows.length, rows};
    }""")

    print("HEADERS:", rows_data.get('headers', []))
    print(f"TOTAL ROWS: {rows_data.get('rowCount', 0)}")
    print()
    
    for i, row in enumerate(rows_data.get('rows', [])):
        print(f"--- ROW {i} (class={row['className']}, id={row['id']}, cells={row['cellCount']}) ---")
        for j, cell in enumerate(row.get('cells', [])):
            print(f"  Cell {j} (class={cell['class']}): text='{cell['text']}' | html='{cell['html']}'")
        if row.get('onclick'):
            print(f"  onclick: {row['onclick']}")
        print()

    # Also look for match detail links
    links = page.evaluate("""() => {
        const links = document.querySelectorAll('#inplay_match_table a[href*="/match/"]');
        return Array.from(links).slice(0, 5).map(a => ({
            href: a.getAttribute('href'),
            text: a.textContent.trim().substring(0, 60),
        }));
    }""")
    print("MATCH DETAIL LINKS:")
    for l in links:
        print(f"  {l['href']} → {l['text']}")

    ctx.close()
    browser.close()
