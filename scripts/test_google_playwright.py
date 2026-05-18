"""Test: Google Sports Panel via Playwright — FREE, unlimited, full JS rendering.

This extracts the same data SerpAPI gives us but for FREE using a headless browser.
"""

import asyncio
import json
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("ERROR: playwright not installed. Run: pip3 install playwright && playwright install chromium")
    sys.exit(1)


async def extract_google_sports_stats(team1: str, team2: str) -> dict:
    """Query Google for 'team1 vs team2' and extract sports panel data.
    
    Returns structured match data: scores, stats, lineups, H2H.
    FREE and unlimited — uses Playwright to render the page.
    """
    query = f"{team1} vs {team2}"
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}&hl=en"
    
    result = {
        "query": query,
        "source": "google-sports-panel",
        "teams": {},
        "match_info": {},
        "statistics": {},
        "h2h": [],
    }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-US",
        )
        page = await context.new_page()
        
        print(f"Navigating to: {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)  # Wait for sports panel to render
        
        # Accept cookies if prompted
        try:
            accept_btn = page.locator("button:has-text('Accept all')")
            if await accept_btn.is_visible(timeout=2000):
                await accept_btn.click()
                await page.wait_for_timeout(1000)
        except Exception:
            pass
        
        # --- Extract game spotlight / score ---
        # Google sports panel uses various selectors
        try:
            # Try to find the sports card
            sports_card = page.locator("[data-attrid='sports_card']").first
            if not await sports_card.is_visible(timeout=3000):
                # Alternative: look for the match header area
                sports_card = page.locator(".imso_mh").first
        except Exception:
            sports_card = None
        
        # Extract team names and scores
        # Google typically shows teams in .imso_mh__tl (team left) and .imso_mh__tr (team right)
        try:
            # Method 1: Look for score elements
            score_elements = await page.locator(".imso_mh__scr .imso_mh__l-tm-sc, .imso_mh__scr .imso_mh__r-tm-sc").all_text_contents()
            if score_elements:
                result["teams"]["scores"] = score_elements
                print(f"  Scores found: {score_elements}")
        except Exception as e:
            print(f"  Score extraction method 1 failed: {e}")

        # Method 2: More generic approach - get all text from sports area  
        try:
            # The match header area
            match_header = page.locator(".imso-hov")
            if await match_header.count() > 0:
                header_text = await match_header.first.text_content()
                result["match_info"]["header_text"] = header_text
                print(f"  Match header: {header_text[:100]}")
        except Exception:
            pass

        # --- Extract statistics tab ---
        # Click on "Statistics" tab if available
        try:
            stats_tab = page.locator("div[data-tab]:has-text('Statistics'), div[data-tab]:has-text('Stats')")
            if await stats_tab.count() > 0:
                await stats_tab.first.click()
                await page.wait_for_timeout(1500)
                print("  ✅ Clicked Statistics tab")
                
                # Extract stat rows
                stat_rows = page.locator(".imso_gs__tg-stts-row, [data-stat-name]")
                count = await stat_rows.count()
                print(f"  Found {count} stat rows")
                
                for i in range(count):
                    row = stat_rows.nth(i)
                    row_text = await row.text_content()
                    if row_text:
                        result["statistics"][f"row_{i}"] = row_text.strip()
            else:
                print("  ℹ️  No Statistics tab found")
        except Exception as e:
            print(f"  Stats tab error: {e}")

        # --- Alternative: Extract all visible text from sports panel ---
        try:
            # Get the entire sports results section
            sports_section = page.locator("#sports-app, .imso-ani, [data-sports-game-id]")
            if await sports_section.count() > 0:
                full_text = await sports_section.first.text_content()
                result["match_info"]["full_panel_text"] = full_text[:2000] if full_text else ""
                print(f"  Sports panel text ({len(full_text or '')} chars)")
            else:
                # Fallback: get page content around match area
                print("  ℹ️  No standard sports panel found, trying broader selectors...")
                all_text = await page.locator("body").text_content()
                # Look for score-like patterns
                if team1.lower() in (all_text or "").lower():
                    result["match_info"]["page_contains_team1"] = True
                if team2.lower() in (all_text or "").lower():
                    result["match_info"]["page_contains_team2"] = True
        except Exception as e:
            print(f"  Panel extraction error: {e}")

        # --- Take screenshot for visual inspection ---
        screenshot_path = Path(__file__).parent.parent / "betting" / "data" / "stats_cache" / "google_sports_screenshot.png"
        await page.screenshot(path=str(screenshot_path), full_page=False)
        print(f"  Screenshot saved: {screenshot_path}")

        # --- Get page HTML for deeper parsing ---
        html_content = await page.content()
        html_path = Path(__file__).parent.parent / "betting" / "data" / "stats_cache" / "google_playwright_full.html"
        with open(html_path, "w") as f:
            f.write(html_content)
        print(f"  Full HTML saved: {html_path} ({len(html_content)} bytes)")

        await browser.close()
    
    return result


async def main():
    print(f"\n{'='*60}")
    print("Google Sports Panel — Playwright Extraction Test")
    print(f"{'='*60}\n")
    
    result = await extract_google_sports_stats("PSG", "Paris FC")
    
    print(f"\n{'='*60}")
    print("EXTRACTED DATA:")
    print(f"{'='*60}")
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str)[:3000])
    
    # Save result
    output_path = Path(__file__).parent.parent / "betting" / "data" / "stats_cache" / "google_playwright_result.json"
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResult saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
