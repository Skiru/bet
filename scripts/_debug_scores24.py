#!/usr/bin/env python3
"""Debug DOM structure for Scores24 (scores24.live).

Dumps listing page match structure, detail page H2H/form/odds/trends sections.
Multi-sport: soccer, tennis, basketball, ice-hockey, volleyball.

Usage: PYTHONPATH=src python3 scripts/_debug_scores24.py [--sport soccer]
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

SPORT_URLS = {
    "soccer": "https://scores24.live/en/soccer",
    "tennis": "https://scores24.live/en/tennis",
    "basketball": "https://scores24.live/en/basketball",
    "ice-hockey": "https://scores24.live/en/ice-hockey",
    "volleyball": "https://scores24.live/en/volleyball",
}


def main():
    parser = argparse.ArgumentParser(description="Debug Scores24 DOM")
    parser.add_argument("--sport", default="soccer", choices=list(SPORT_URLS.keys()))
    parser.add_argument("--detail-url", help="Full detail page URL to inspect")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed")
        sys.exit(1)

    try:
        from playwright_stealth import Stealth
    except ImportError:
        Stealth = None
        print("WARN: playwright_stealth not available")

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
        listing_url = SPORT_URLS[args.sport]
        print(f"\n{'='*60}")
        print(f"LISTING PAGE: {listing_url} (sport={args.sport})")
        print(f"{'='*60}")

        page.goto(listing_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(6000)  # SPA needs time

        body_text = page.inner_text('body')
        print(f"\nBody text length: {len(body_text)}")
        if len(body_text) < 500:
            print("WARNING: Possibly blocked")
            print(f"First 300 chars: {body_text[:300]}")
            # Check page content for Cloudflare
            content = page.content()
            if "Just a moment" in content:
                print("BLOCKED: Cloudflare challenge detected")

        # Container hierarchy
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
            return dump.slice(0, 100);
        }""")
        print("\nCONTAINER HIERARCHY (first 100):")
        for line in hierarchy:
            print(line)

        # Look for match/event elements
        match_search = page.evaluate("""() => {
            const results = [];
            // Try common patterns
            const selectors = [
                '[class*="match"]',
                '[class*="event"]',
                '[class*="game"]',
                '[class*="fixture"]',
                'a[href*="/m-"]',
                'a[href*="match"]',
            ];
            for (const sel of selectors) {
                try {
                    const els = document.querySelectorAll(sel);
                    if (els.length > 0) {
                        const first = els[0];
                        results.push({
                            selector: sel,
                            count: els.length,
                            firstTag: first.tagName,
                            firstClass: (first.className && typeof first.className === 'string') ? first.className.substring(0, 100) : '',
                            firstText: first.textContent.trim().substring(0, 120),
                            firstHref: first.getAttribute('href') || '',
                        });
                    }
                } catch(e) {}
            }
            return results;
        }""")
        print(f"\n\nMATCH ELEMENT SEARCH:")
        for ms in match_search:
            print(f"  {ms['selector']}: {ms['count']} elements")
            print(f"    tag={ms['firstTag']} class={ms['firstClass']}")
            print(f"    text={ms['firstText']}")
            if ms['firstHref']:
                print(f"    href={ms['firstHref']}")

        # Find all links with /m- pattern (match detail links)
        detail_links = page.evaluate("""() => {
            const links = document.querySelectorAll('a[href*="/m-"], a[href*="/en/"]');
            const matchLinks = [];
            for (const a of links) {
                const href = a.getAttribute('href') || '';
                if (href.includes('/m-') || (href.match(/\\/en\\/[a-z-]+\\/[a-z]/) && href.length > 20)) {
                    matchLinks.push({
                        href: href,
                        text: a.textContent.trim().substring(0, 80),
                        class: (a.className && typeof a.className === 'string') ? a.className.substring(0, 60) : '',
                    });
                }
                if (matchLinks.length >= 10) break;
            }
            return matchLinks;
        }""")
        print(f"\n\nDETAIL LINKS ({len(detail_links)}):")
        for dl in detail_links:
            print(f"  {dl['href']} → {dl['text']} (class={dl['class']})")

        # Dump body text for pattern recognition
        print(f"\n\nBODY TEXT (first 3000 chars):")
        print(body_text[:3000])

        # ── 2. Detail page ───────────────────────────────────────────────
        detail_url = args.detail_url
        if not detail_url and detail_links:
            # Use first match detail link
            first_href = detail_links[0]['href']
            if first_href.startswith('/'):
                detail_url = f"https://scores24.live{first_href}"
            elif first_href.startswith('http'):
                detail_url = first_href

        if detail_url:
            print(f"\n\n{'='*60}")
            print(f"DETAIL PAGE: {detail_url}")
            print(f"{'='*60}")

            page.goto(detail_url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(6000)

            detail_body = page.inner_text('body')
            print(f"\nBody text length: {len(detail_body)}")

            # Look for H2H, form, odds, trends sections
            sections = page.evaluate("""() => {
                const results = [];
                const selectors = [
                    '[class*="h2h"]', '[class*="head"]',
                    '[class*="form"]', '[class*="recent"]',
                    '[class*="odds"]', '[class*="coeff"]',
                    '[class*="trend"]', '[class*="stat"]',
                    '[class*="tab"]',
                ];
                for (const sel of selectors) {
                    try {
                        const els = document.querySelectorAll(sel);
                        if (els.length > 0) {
                            results.push({
                                selector: sel,
                                count: els.length,
                                firstClass: (els[0].className && typeof els[0].className === 'string') ? els[0].className.substring(0, 100) : '',
                                firstText: els[0].textContent.trim().substring(0, 150),
                            });
                        }
                    } catch(e) {}
                }
                return results;
            }""")
            print(f"\nSECTION SEARCH:")
            for sec in sections:
                print(f"  {sec['selector']}: {sec['count']} (class={sec['firstClass']})")
                print(f"    text={sec['firstText']}")

            # Dump detail body text for pattern recognition
            print(f"\nDETAIL BODY TEXT (first 5000 chars):")
            print(detail_body[:5000])

            # Try trends tab
            print(f"\n\n--- TRENDS TAB ---")
            trends_url = detail_url.rstrip('/') + '#trends'
            page.goto(trends_url, wait_until="domcontentloaded", timeout=15_000)
            page.wait_for_timeout(4000)

            trends_body = page.inner_text('body')
            if trends_body != detail_body:
                print(f"Trends body text length: {len(trends_body)}")
                # Find unique text in trends (not in detail)
                detail_set = set(detail_body.split('\n'))
                trends_lines = trends_body.split('\n')
                unique = [l for l in trends_lines if l.strip() and l not in detail_set]
                print(f"Unique trends lines: {len(unique)}")
                for ul in unique[:30]:
                    print(f"  {ul.strip()[:120]}")
            else:
                print("No difference from detail page — trends may need JS click")

                # Try clicking a trends tab
                tab_click = page.evaluate("""() => {
                    const tabs = document.querySelectorAll('[class*="tab"], a[href*="trend"], button');
                    for (const tab of tabs) {
                        const text = tab.textContent.trim().toLowerCase();
                        if (text.includes('trend') || text.includes('stats') || text.includes('statist')) {
                            return {found: true, text: tab.textContent.trim(), tag: tab.tagName};
                        }
                    }
                    return {found: false};
                }""")
                print(f"Tab search: {tab_click}")

        ctx.close()
        browser.close()

    print("\n\nDONE ✓")


if __name__ == "__main__":
    main()
