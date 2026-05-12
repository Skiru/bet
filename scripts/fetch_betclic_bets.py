#!/usr/bin/env python3
"""Fetch placed coupons from Betclic /my-bets page using Playwright.

Logs into Betclic, navigates to the My Bets page, scrolls to load all
bets, captures the page HTML snapshot for analysis, and extracts
structured coupon data.

Usage:
    python3 scripts/fetch_betclic_bets.py --user USER --password PASS
    python3 scripts/fetch_betclic_bets.py --user USER --password PASS --headless
"""
import sys
import json
import argparse
import time
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from betclic_helpers import USER_AGENTS, STORAGE_DIR, load_selectors

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright not available. Install: pip install playwright && playwright install chromium")
    sys.exit(1)

DATA_DIR = BASE.parent / "betting" / "data"
DOMAIN = "betclic.pl"


def login_and_fetch_bets(user: str, password: str, headless: bool = False):
    """Login to Betclic and fetch the /my-bets page content."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    storage_file = STORAGE_DIR / f"{DOMAIN}.json"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx_kwargs = {
            "user_agent": USER_AGENTS[0],
            "viewport": {"width": 1280, "height": 900},
            "locale": "pl-PL",
        }

        ctx = browser.new_context(**ctx_kwargs)
        page = ctx.new_page()

        # Step 1: Go directly to /my-bets and check if logged in
        print("[1/5] Navigating to /my-bets to check auth...")
        page.goto("https://www.betclic.pl/my-bets", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)
        html = page.content()

        # If we see the unlogged state, we need to login
        needs_login = "zaloguj się" in html.lower() or "my-bets-unlogged" in html.lower()

        if needs_login:
            print("[2/5] Not authenticated. Logging in...")
            page.goto("https://www.betclic.pl/login", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # Handle cookie consent if present
            selectors_map = load_selectors()
            selectors = selectors_map.get(DOMAIN, []) + selectors_map.get("default", [])
            for sel in selectors:
                try:
                    el = page.query_selector(sel)
                    if el:
                        el.click(timeout=3000)
                        page.wait_for_timeout(600)
                except Exception:
                    continue

            # Try multiple login form strategies for Angular SPA
            login_success = False

            # Strategy 1: standard input fields
            try:
                email_input = page.query_selector('input[type="email"], input[name="email"], input[id="email"], input[data-qa="email-input"], input[placeholder*="email" i], input[placeholder*="login" i], input[placeholder*="e-mail" i]')
                pass_input = page.query_selector('input[type="password"], input[name="password"], input[id="password"], input[data-qa="password-input"]')

                if email_input and pass_input:
                    email_input.click()
                    page.wait_for_timeout(300)
                    email_input.fill(user)
                    page.wait_for_timeout(300)
                    pass_input.click()
                    page.wait_for_timeout(300)
                    pass_input.fill(password)
                    page.wait_for_timeout(500)

                    # Try clicking login button
                    login_btn = page.query_selector('button[type="submit"], button[data-qa="login-button"], button[class*="login" i], .login-button, button:has-text("Zaloguj"), button:has-text("Login")')
                    if login_btn:
                        login_btn.click()
                        page.wait_for_timeout(5000)
                        login_success = True
                    else:
                        # Try pressing Enter
                        pass_input.press("Enter")
                        page.wait_for_timeout(5000)
                        login_success = True
            except Exception as e:
                print(f"  Login strategy 1 failed: {e}")

            if not login_success:
                print("  Could not find login form automatically.")
                print("  Please log in manually in the browser window.")
                print("  Press Enter here when done...")
                input()

            # Wait for redirect and verify login
            page.wait_for_timeout(5000)

            # Navigate to /my-bets again after login
            page.goto("https://www.betclic.pl/my-bets", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
            html = page.content()
            logged_in = "my-bets-unlogged" not in html.lower() and "zaloguj się i szybko znajdź" not in html.lower()

            if logged_in:
                print("  Login successful!")
                ctx.storage_state(path=str(storage_file))
            else:
                print("  WARNING: Login may have failed. Saving debug HTML...")
                debug_path = DATA_DIR / "betclic_login_debug.html"
                debug_path.write_text(html, encoding="utf-8")
                print(f"  Debug HTML saved to: {debug_path}")
                print("  Please log in manually in the browser window, then press Enter...")
                input()
                page.goto("https://www.betclic.pl/my-bets", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)
                ctx.storage_state(path=str(storage_file))
        else:
            print("  Already authenticated!")

        # Step 3: Navigate to My Bets and wait for full render
        print("[3/5] Navigating to /my-bets...")
        page.goto("https://www.betclic.pl/my-bets", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)

        # Wait for bet cards or tabs to appear (Angular SPA needs time)
        try:
            page.wait_for_selector('bet-card, my-bets-filters, .tab_item', timeout=15000)
            print("  Page elements loaded!")
        except Exception:
            print("  Waiting longer for Angular to render...")
            page.wait_for_timeout(5000)

        # Always save a debug HTML snapshot first
        debug_html = page.content()
        debug_path = DATA_DIR / "betclic_mybets_debug.html"
        debug_path.write_text(debug_html, encoding="utf-8")
        print(f"  Debug snapshot: {debug_path} ({len(debug_html)} chars)")

        # Step 4: Scroll to load all bets, then expand each card
        print("[4/5] Scrolling to load all bets...")
        prev_height = 0
        scroll_attempts = 0
        max_scrolls = 50

        while scroll_attempts < max_scrolls:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)
            curr_height = page.evaluate("document.body.scrollHeight")

            # Check for "load more" buttons
            load_more = page.query_selector('button:has-text("Pokaż więcej"), button:has-text("Load more"), button:has-text("Więcej"), [data-qa="load-more"], .load-more')
            if load_more:
                try:
                    load_more.click()
                    page.wait_for_timeout(3000)
                    scroll_attempts += 1
                    continue
                except Exception:
                    pass

            if curr_height == prev_height:
                page.wait_for_timeout(2000)
                final_height = page.evaluate("document.body.scrollHeight")
                if final_height == curr_height:
                    break
            prev_height = curr_height
            scroll_attempts += 1

        print(f"  Loaded after {scroll_attempts} scroll(s)")

        # Expand all bet cards to reveal event details
        cards = page.query_selector_all('bet-card .betCard')
        print(f"  Found {len(cards)} bet cards. Expanding each...")
        for idx, card in enumerate(cards):
            try:
                # Click the card to expand it
                card.click()
                page.wait_for_timeout(800)
            except Exception:
                pass
            if (idx + 1) % 20 == 0:
                print(f"    Expanded {idx + 1}/{len(cards)}...")
        print(f"  Expanded all {len(cards)} cards")

        all_html_parts = []
        all_bets_data = []

        def scroll_fully():
            """Scroll to the bottom to load all cards."""
            prev_height = 0
            for _ in range(100):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)
                curr = page.evaluate("document.body.scrollHeight")
                load_more = page.query_selector('button:has-text("Pokaż więcej"), button:has-text("Więcej")')
                if load_more:
                    try:
                        load_more.click()
                        page.wait_for_timeout(3000)
                        continue
                    except Exception:
                        pass
                if curr == prev_height:
                    break
                prev_height = curr

        def expand_and_extract():
            """Click each card to expand, then extract event data via JS."""
            cards = page.query_selector_all('bet-card')
            print(f"  Found {len(cards)} bet cards. Expanding and extracting...")
            results = []

            for idx, card in enumerate(cards):
                try:
                    # Click to expand
                    card.scroll_into_view_if_needed()
                    card.click()
                    page.wait_for_timeout(1000)

                    # Extract data via JavaScript from the expanded card
                    data = card.evaluate("""(el) => {
                        const d = {};

                        // Bet type (AKO, single, etc.)
                        const header = el.querySelector('.betCard_headerTitle');
                        d.bet_type = header ? header.textContent.trim() : '';

                        // Status from wrapper div classes
                        const wrapper = el.querySelector('.betCard');
                        if (wrapper) {
                            d.is_won = wrapper.classList.contains('is-won');
                            d.is_lost = wrapper.classList.contains('is-lost');
                            d.is_pending = wrapper.classList.contains('is-pending') || wrapper.classList.contains('is-open');
                            d.is_cashout = wrapper.classList.contains('is-cashout');
                        }

                        // Status tag
                        const tag = el.querySelector('.tag .tag_label');
                        d.status_label = tag ? tag.textContent.trim() : '';

                        // Reference ID (data-qa on wrapper)
                        d.ref_id = wrapper ? wrapper.getAttribute('data-qa') : '';

                        // Summary: combined odds, stake, winnings
                        const totalOdds = el.querySelector('.is-totalOdds .summaryBets_listItemValue');
                        d.total_odds = totalOdds ? totalOdds.textContent.trim().replace(',', '.') : '';

                        const stake = el.querySelector('.is-stake .summaryBets_listItemValue');
                        d.stake = stake ? stake.textContent.trim() : '';

                        const winnings = el.querySelector('.is-winnings .summaryBets_listItemValue');
                        d.winnings = winnings ? winnings.textContent.trim() : '';

                        // Footer: ref + date
                        const footerInfos = el.querySelector('.betCard_footerInfos');
                        if (footerInfos) {
                            const spans = footerInfos.querySelectorAll('span');
                            d.footer_ref = spans[0] ? spans[0].textContent.trim() : '';
                            d.footer_date = spans[1] ? spans[1].textContent.trim() : '';
                        }

                        // Status per leg
                        const statusItems = el.querySelectorAll('.statusBets_listItem span');
                        d.leg_statuses = Array.from(statusItems).map(s => {
                            if (s.classList.contains('icon_betWinner')) return 'won';
                            if (s.classList.contains('icon_betLost')) return 'lost';
                            if (s.classList.contains('icon_liveMatch')) return 'live';
                            if (s.classList.contains('icon_betCancelled')) return 'cancelled';
                            return 'unknown';
                        });

                        // Events/legs (expanded content)
                        d.events = [];
                        const eventEls = el.querySelectorAll('bet-card-event');
                        for (const ev of eventEls) {
                            const e = {};

                            // Event info
                            const info = ev.querySelector('bet-card-event-info');
                            if (info) {
                                // Teams
                                const c1 = info.querySelector('[data-qa="contestant-1-label"]');
                                const c2 = info.querySelector('[data-qa="contestant-2-label"]');
                                e.home = c1 ? c1.textContent.trim() : '';
                                e.away = c2 ? c2.textContent.trim() : '';

                                // Score
                                const score = info.querySelector('[data-qa="scoreboard-score"]');
                                e.score = score ? score.textContent.trim() : '';

                                // Time/date
                                const time = info.querySelector('.event_infoTime');
                                e.time = time ? time.textContent.trim() : '';

                                // Full info text
                                e.info_text = info.textContent.trim().replace(/\\s+/g, ' ');
                            }

                            // Market
                            const market = ev.querySelector('bet-card-event-market, bet-card-market, bet-card-market-classic, bet-card-market-combo');
                            if (market) {
                                e.market_text = market.textContent.trim().replace(/\\s+/g, ' ');

                                // Title (market name)
                                const title = market.querySelector('.marketBets_title');
                                e.market_title = title ? title.textContent.trim() : '';

                                // Selection (what was bet on)
                                const label = market.querySelector('.marketBets_label');
                                e.market_selection = label ? label.textContent.trim() : '';

                                // Odds
                                const oddsEl = market.querySelector('.marketBets_value, bet-card-market-odds');
                                e.odds = oddsEl ? oddsEl.textContent.trim().replace(',', '.') : '';

                                // All label-value pairs
                                const labels = market.querySelectorAll('.marketBets_label');
                                const values = market.querySelectorAll('.marketBets_value');
                                e.market_details = [];
                                for (let i = 0; i < labels.length; i++) {
                                    e.market_details.push({
                                        label: labels[i].textContent.trim(),
                                        value: values[i] ? values[i].textContent.trim() : ''
                                    });
                                }
                            }

                            // Event status
                            const evStatus = ev.querySelector('.icon_betWinner, .icon_betLost, .icon_betCancelled');
                            if (evStatus) {
                                if (evStatus.classList.contains('icon_betWinner')) e.status = 'won';
                                else if (evStatus.classList.contains('icon_betLost')) e.status = 'lost';
                                else if (evStatus.classList.contains('icon_betCancelled')) e.status = 'cancelled';
                            }

                            d.events.push(e);
                        }

                        // If no events found, try bet-card-list children
                        if (d.events.length === 0) {
                            const betList = el.querySelector('.betCard_betList');
                            if (betList) {
                                d.raw_bet_list = betList.textContent.trim().replace(/\\s+/g, ' ');
                            }
                        }

                        return d;
                    }""")

                    results.append(data)
                    if (idx + 1) % 20 == 0:
                        print(f"    Processed {idx + 1}/{len(cards)}...")
                except Exception as e:
                    print(f"    Card {idx + 1} extraction failed: {e}")

            return results

        # Step 4: Process each tab
        print("[4/5] Processing tabs...")

        # Wait for tabs to appear
        page.wait_for_timeout(3000)

        # Try to find and click tabs by their IDs
        tab_configs = [
            ("ongoing", "Otwarte"),
            ("ended", "Zakończone"),
        ]

        for tab_id, tab_name in tab_configs:
            print(f"\n  === Processing tab: {tab_name} ===")
            # Try multiple selector strategies
            tab_el = page.query_selector(f'#{tab_id}')
            if not tab_el:
                tab_el = page.query_selector(f'li.tab_item:has-text("{tab_name}")')
            if not tab_el:
                tab_el = page.query_selector(f'li:has(span:text("{tab_name}"))')
            if not tab_el:
                # Try evaluating in JS
                tab_el = page.evaluate_handle(f"""
                    () => {{
                        const items = document.querySelectorAll('.tab_item, li');
                        for (const item of items) {{
                            if (item.textContent.includes('{tab_name}')) return item;
                        }}
                        return null;
                    }}
                """)
                if tab_el:
                    try:
                        tab_el = tab_el.as_element()
                    except Exception:
                        tab_el = None

            if tab_el:
                tab_el.click()
                page.wait_for_timeout(4000)
                scroll_fully()
                bets = expand_and_extract()
                all_bets_data.extend(bets)
                print(f"  [{tab_name}] Extracted {len(bets)} bets")
                # Save HTML snapshot too
                all_html_parts.append((tab_name, page.content()))
            else:
                print(f"  WARNING: Could not find '{tab_name}' tab")

        # Step 5: Save HTML snapshots and extracted data
        print("[5/5] Saving data...")
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snapshot_dir = DATA_DIR / "betclic_mybets"
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        saved_files = []
        for label, html_content in all_html_parts:
            safe_label = label.replace(" ", "_").replace("/", "_")[:30]
            fpath = snapshot_dir / f"{ts}_{safe_label}.html"
            fpath.write_text(html_content, encoding="utf-8")
            saved_files.append(str(fpath))
            print(f"  HTML saved: {fpath} ({len(html_content)} chars)")

        # Save extracted bet data as JSON
        json_path = DATA_DIR / "betclic_bets_history.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(all_bets_data, f, ensure_ascii=False, indent=2)
        saved_files.append(str(json_path))
        print(f"  JSON saved: {json_path} ({len(all_bets_data)} bets)")

        # Save session state
        try:
            ctx.storage_state(path=str(storage_file))
        except Exception:
            pass

        browser.close()
        return saved_files


def main():
    parser = argparse.ArgumentParser(description="Fetch Betclic bet history")
    parser.add_argument("--user", required=True, help="Betclic username/email")
    parser.add_argument("--password", required=True, help="Betclic password")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    args = parser.parse_args()

    saved = login_and_fetch_bets(args.user, args.password, headless=args.headless)
    print(f"\nDone! Saved {len(saved)} HTML snapshot(s).")
    for f in saved:
        print(f"  {f}")


if __name__ == "__main__":
    main()
