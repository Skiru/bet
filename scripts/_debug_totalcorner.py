#!/usr/bin/env python3
"""Debug DOM structure for TotalCorner (totalcorner.com).

Dumps container hierarchy, match table structure, corner prediction cells,
and dangerous attack columns. Run BEFORE implementing the client.

Usage: PYTHONPATH=src python3 scripts/_debug_totalcorner.py [--detail-id ID]
"""
import argparse
import random
import sys

try:
    from scripts.stealth_utils import USER_AGENTS, BROWSER_ARGS
except ImportError:
    USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    ]
    BROWSER_ARGS = ['--disable-blink-features=AutomationControlled', '--disable-infobars', '--no-sandbox']


def main():
    parser = argparse.ArgumentParser(description="Debug TotalCorner DOM")
    parser.add_argument("--detail-id", help="Match ID for detail page (e.g., 12345)")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    try:
        from playwright_stealth import Stealth
    except ImportError:
        Stealth = None
        print("WARN: playwright_stealth not available, proceeding without stealth")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        ctx = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1920, "height": 1080},
        )
        page = ctx.new_page()
        if Stealth:
            Stealth().apply_stealth_sync(page)

        # ── 1. Listing page ──────────────────────────────────────────────
        listing_url = "https://www.totalcorner.com/match/today"
        print(f"\n{'='*60}")
        print(f"LISTING PAGE: {listing_url}")
        print(f"{'='*60}")

        page.goto(listing_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(5000)

        # Block detection
        body_text = page.inner_text('body')
        print(f"\nBody text length: {len(body_text)}")
        if len(body_text) < 500:
            print("WARNING: Possibly blocked — body text too short")
            print(f"First 300 chars: {body_text[:300]}")

        # Container hierarchy (top 80 elements with classes)
        hierarchy = page.evaluate("""() => {
            const dump = [];
            const walk = (el, depth) => {
                if (depth > 5) return;
                const classes = el.className && typeof el.className === 'string' ? el.className : '';
                const id = el.id || '';
                if (classes || id) {
                    dump.push('  '.repeat(depth) + el.tagName + (id ? '#' + id : '') + (classes ? '.' + classes.split(' ').join('.') : ''));
                }
                for (const child of el.children) walk(child, depth + 1);
            };
            walk(document.body, 0);
            return dump.slice(0, 80);
        }""")
        print("\nCONTAINER HIERARCHY (first 80 with classes):")
        for line in hierarchy:
            print(line)

        # Look for table structures
        tables_info = page.evaluate("""() => {
            const tables = document.querySelectorAll('table');
            return Array.from(tables).map((t, i) => ({
                index: i,
                id: t.id || '',
                className: t.className || '',
                rows: t.rows ? t.rows.length : 0,
                firstRowHTML: t.rows && t.rows[0] ? t.rows[0].innerHTML.substring(0, 300) : '',
            }));
        }""")
        print(f"\n\nTABLES FOUND: {len(tables_info)}")
        for t in tables_info[:5]:
            print(f"  Table #{t['index']}: id={t['id']} class={t['className']} rows={t['rows']}")
            if t['firstRowHTML']:
                print(f"    First row (300ch): {t['firstRowHTML']}")

        # Look for match rows with various selectors
        match_selectors = [
            'tr[class*="match"]',
            'tr[class*="corner"]',
            'div[class*="match"]',
            'div[class*="fixture"]',
            '.match-row',
            '.match-item',
            'tr.odd, tr.even',
            '[data-id]',
            'tr[onclick]',
        ]
        print("\n\nMATCH ROW SEARCH:")
        for sel in match_selectors:
            count = page.evaluate(f'() => document.querySelectorAll("{sel}").length')
            if count > 0:
                first_html = page.evaluate(f'''() => {{
                    const el = document.querySelector("{sel}");
                    return el ? el.innerHTML.substring(0, 400) : '';
                }}''')
                print(f"  {sel}: {count} elements")
                print(f"    First (400ch): {first_html}")

        # Specifically look for corner-related content
        corner_elements = page.evaluate("""() => {
            const results = [];
            const all = document.querySelectorAll('*');
            for (const el of all) {
                const text = el.textContent || '';
                const cls = el.className && typeof el.className === 'string' ? el.className : '';
                if ((cls.toLowerCase().includes('corner') || cls.toLowerCase().includes('attack'))
                    && text.length < 200 && text.length > 0) {
                    results.push({
                        tag: el.tagName,
                        class: cls,
                        text: text.substring(0, 100),
                    });
                }
                if (results.length >= 20) break;
            }
            return results;
        }""")
        print(f"\n\nCORNER/ATTACK ELEMENTS: {len(corner_elements)}")
        for ce in corner_elements:
            print(f"  {ce['tag']}.{ce['class']}: {ce['text']}")

        # Dump first 2000 chars of body text for pattern recognition
        print(f"\n\nBODY TEXT (first 2000 chars):")
        print(body_text[:2000])

        # ── 2. Detail page (if ID provided) ──────────────────────────────
        if args.detail_id:
            detail_url = f"https://www.totalcorner.com/match/{args.detail_id}/corner/"
            print(f"\n\n{'='*60}")
            print(f"DETAIL PAGE: {detail_url}")
            print(f"{'='*60}")

            page.goto(detail_url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(5000)

            detail_body = page.inner_text('body')
            print(f"\nBody text length: {len(detail_body)}")
            print(f"\nDetail body text (first 3000 chars):")
            print(detail_body[:3000])

            # Look for stat values
            stat_elements = page.evaluate("""() => {
                const results = [];
                const tds = document.querySelectorAll('td, th, .stat, [class*="stat"], [class*="corner"]');
                for (const td of tds) {
                    const text = td.textContent.trim();
                    if (text && text.length < 50) {
                        results.push({
                            tag: td.tagName,
                            class: td.className || '',
                            text: text,
                        });
                    }
                    if (results.length >= 40) break;
                }
                return results;
            }""")
            print(f"\n\nSTAT ELEMENTS: {len(stat_elements)}")
            for se in stat_elements:
                print(f"  {se['tag']}.{se['class']}: {se['text']}")
        else:
            # Try to find a match link to use for detail page
            match_links = page.evaluate("""() => {
                const links = document.querySelectorAll('a[href*="/match/"]');
                return Array.from(links).slice(0, 5).map(a => ({
                    href: a.href,
                    text: a.textContent.trim().substring(0, 80),
                }));
            }""")
            print(f"\n\nMATCH LINKS (for --detail-id):")
            for ml in match_links:
                print(f"  {ml['href']} → {ml['text']}")

        ctx.close()
        browser.close()

    print("\n\nDONE ✓")


if __name__ == "__main__":
    main()
