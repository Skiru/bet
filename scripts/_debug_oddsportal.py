import os
import time
import argparse
import random
from pathlib import Path
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright, Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
    from playwright_stealth import Stealth
except ImportError:
    print("FATAL: Playwright or playwright_stealth not installed.")
    print("Run: pip install playwright playwright-stealth && playwright install")
    exit(1)

try:
    from stealth_utils import USER_AGENTS, BROWSER_ARGS
except ImportError:
    print("WARNING: stealth_utils not found, using fallback UA and args")
    USER_AGENTS = ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"]
    BROWSER_ARGS = ['--disable-blink-features=AutomationControlled', '--disable-infobars', '--no-sandbox']

SPORT_URLS = {
    "football": "https://www.oddsportal.com/matches/football/",
    "tennis": "https://www.oddsportal.com/matches/tennis/",
    "basketball": "https://www.oddsportal.com/matches/basketball/",
    "hockey": "https://www.oddsportal.com/matches/hockey/",
}

def dump_hierarchy(page):
    """Walk DOM body up to depth 4, printing first 100 elements with tag + id + classes."""
    return page.evaluate("""() => {
        let count = 0;
        let result = [];
        
        function walk(node, depth) {
            if (count >= 100 || depth > 4 || !node) return;
            
            let indent = "  ".repeat(depth);
            let tag = node.tagName ? node.tagName.toUpperCase() : "TEXT";
            if (tag === "TEXT" || tag === "SCRIPT" || tag === "STYLE") return;
            
            let id = node.id ? "#" + node.id : "";
            let classes = (node.className && typeof node.className === 'string') ? "." + node.className.split(" ").filter(c=>c).join(".") : "";
            result.push(`${indent}${tag}${id}${classes}`);
            count++;
            
            let children = node.children;
            if (children) {
                for (let i = 0; i < children.length; i++) {
                    walk(children[i], depth + 1);
                }
            }
        }
        
        walk(document.body, 0);
        return result.join("\\n");
    }""")

def run_debug(sport: str, detail_url: str = None, save_html: bool = False):
    print(f"\n═══ ODDSPORTAL DEBUG — {sport.upper()} ═══\n")
    
    url = detail_url if detail_url else SPORT_URLS[sport]
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        ua = random.choice(USER_AGENTS)
        context = browser.new_context(
            user_agent=ua,
            viewport={"width": 1920, "height": 1080},
            locale="en-GB"
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        
        try:
            print(f"Navigating to {url} ...")
            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
            except PlaywrightTimeoutError:
                print("Networkidle timeout hit, waiting for 8 seconds explicitly...")
                page.wait_for_timeout(8000)
            except PlaywrightError as e:
                print(f"Navigation error: {e}")
                
            page.wait_for_timeout(3000)  # Extra buffer for SPA hydration

            # [1/6] BLOCK CHECK
            print("\n[1/6] BLOCK CHECK")
            try:
                body_text = page.inner_text("body")
                length = len(body_text)
                print(f"Body text length: {length}")
                if length < 500:
                    print("Status: BLOCKED (possible Cloudflare/Datadome challenge)")
                else:
                    print("Status: OK")
            except Exception as e:
                print(f"Status: ERROR reading body - {e}")
            
            # [2/6] COOKIE BANNER
            print("\n[2/6] COOKIE BANNER")
            cookie_selectors = [
                '#onetrust-accept-btn-handler',
                'button[id*="accept"]',
                '[class*="cookie"] button',
                '.gdpr-consent button',
                'button:has-text("Accept")',
                'button:has-text("I accept")'
            ]
            accepted = False
            for sel in cookie_selectors:
                try:
                    if page.locator(sel).is_visible(timeout=1000):
                        page.locator(sel).click()
                        print(f"Tried: {sel} — FOUND, clicked")
                        page.wait_for_timeout(1000)
                        accepted = True
                        break
                    else:
                        print(f"Tried: {sel} — not found")
                except Exception as e:
                    print(f"Tried: {sel} — error: {e}")
            if not accepted:
                print("No cookie banner accepted.")

            # [3/6] CONTAINER HIERARCHY
            print("\n[3/6] CONTAINER HIERARCHY (first 100 elements up to depth 4)")
            hierarchy = dump_hierarchy(page)
            print(hierarchy)
            print("...")

            # [4/6] MATCH ROWS
            print("\n[4/6] MATCH ROWS")
            row_selectors = [
                '[class*="match"]', 
                '[class*="event"]', 
                '[class*="sportEvent"]', 
                'div[class*="border"]', 
                '[class*="game"]',
                'tr'
            ]
            
            match_elements = None
            found_selector = None
            
            for sel in row_selectors:
                count = page.locator(sel).count()
                print(f'Selector "{sel}": found {count} elements')
                if count > 5 and not found_selector:
                    # we pick the first one that gives reasonable > 5 elements, but we continue printing counts
                    match_elements = page.locator(sel).all()
                    found_selector = sel
            
            if match_elements:
                print(f"\nUsing selector '{found_selector}' to sample rows:")
                for i in range(min(5, len(match_elements))):
                    try:
                        inner = match_elements[i].evaluate("el => el.innerHTML")
                        print(f"Row {i+1} innerHTML (500 chars): {inner[:500].strip()}...")
                    except Exception as e:
                        print(f"Row {i+1} error: {e}")
            else:
                print("No match rows found using known selectors.")

            # [5/6] TEAM NAMES + ODDS
            print("\n[5/6] TEAM NAMES + ODDS")
            first_match_href = None
            if match_elements:
                for i in range(min(5, len(match_elements))):
                    try:
                        row = match_elements[i]
                        text = row.inner_text().replace('\\n', ' | ')
                        print(f"Match {i+1} raw text: {text[:100]}")
                        
                        # Try to find a link for detail page
                        links = row.locator("a").all()
                        for link in links:
                            href = link.get_attribute("href")
                            if href and ("/" in href) and first_match_href is None:
                                first_match_href = href
                    except Exception as e:
                        print(f"Match {i+1} extraction error: {e}")

            # [6/6] DETAIL PAGE
            print("\n[6/6] DETAIL PAGE")
            if detail_url:
                target_detail_url = detail_url
                print(f"Using provided detail URL: {target_detail_url}")
            elif first_match_href:
                target_detail_url = f"https://www.oddsportal.com{first_match_href}" if first_match_href.startswith("/") else first_match_href
                print(f"Found detail URL from listing: {target_detail_url}")
            else:
                target_detail_url = None
                print("No detail URL provided or found.")

            if target_detail_url:
                print(f"Navigating to {target_detail_url} ...")
                try:
                    page.goto(target_detail_url, wait_until="networkidle", timeout=30000)
                except PlaywrightTimeoutError:
                    print("Networkidle timeout hit, waiting for 8 seconds explicitly...")
                    page.wait_for_timeout(8000)
                
                page.wait_for_timeout(3000)
                
                # Check for odds table
                table_count = page.locator("table").count()
                odds_divs = page.locator('div[class*="odds"]').count()
                print(f"Odds table found: YES ({table_count} tables, {odds_divs} odds divs) / NO" if (table_count > 0 or odds_divs > 0) else "Odds table found: NO")
                
                # Bookmakers
                bookies = page.locator('a[class*="bookmaker"]').count()
                if bookies == 0:
                    bookies = page.locator('img[alt*="bookmaker"]').count()
                print(f"Bookmakers found: {bookies}")
                
                # Market tabs
                tabs = page.locator('ul[class*="tab"] li, div[class*="tab"] a').all()
                tab_names = [t.inner_text() for t in tabs if t.inner_text()]
                print(f"Market tabs found: {tab_names[:10]}")

            if save_html:
                html_content = page.content()
                os.makedirs("betting/data/debug", exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = f"betting/data/debug/oddsportal_{sport}_{timestamp}.html"
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                print(f"\nSaved raw HTML to {save_path}")

        finally:
            print("\nCleaning up browser resources...")
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug OddsPortal DOM structure")
    parser.add_argument("--sport", default="football", choices=["football", "tennis", "basketball", "hockey"])
    parser.add_argument("--detail-url", help="Specific match detail URL to debug")
    parser.add_argument("--save-html", action="store_true", help="Save raw HTML to file")
    
    args = parser.parse_args()
    
    try:
        run_debug(sport=args.sport, detail_url=args.detail_url, save_html=args.save_html)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        print(f"\nUnhandled error: {e}")
