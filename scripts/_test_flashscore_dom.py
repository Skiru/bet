"""Test Flashscore DOM extraction — structured data from events.

Now that we know Playwright DOM works (225 events found), extract:
1. Fixtures: league, teams, time, date
2. Match detail: stats (corners, fouls, shots, etc.)
3. H2H data from match detail page
"""
import sys
import json
import logging
import re

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def extract_fixtures(sport: str = "football"):
    """Extract fixtures from Flashscore sport listing page."""
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    url = f"https://www.flashscore.com/{sport}/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-GB",
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        logger.info(f"Loading {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)

        # Cookie consent
        try:
            consent = page.locator("#onetrust-accept-btn-handler")
            if consent.is_visible(timeout=3000):
                consent.click()
                page.wait_for_timeout(1000)
        except Exception:
            pass

        # Extract event data from DOM
        fixtures = page.evaluate("""() => {
            const results = [];
            let currentLeague = '';
            let currentCountry = '';
            
            // Get all event title headers (league headers) and matches
            const container = document.querySelector('.leagues--live') || document.querySelector('.event');
            if (!container) return results;
            
            // Walk through all direct children to maintain league context
            const allElements = container.querySelectorAll('.event__header, .event__match, div[id^="g_1_"]');
            
            for (const el of allElements) {
                // League header
                if (el.classList.contains('event__header') || el.querySelector('.event__title')) {
                    const titleEl = el.querySelector('.event__title--name') || el.querySelector('.event__titleBox');
                    if (titleEl) {
                        currentLeague = titleEl.textContent.trim();
                    }
                    const countryEl = el.querySelector('.event__title--type');
                    if (countryEl) {
                        currentCountry = countryEl.textContent.trim();
                    }
                    continue;
                }
                
                // Match row
                const home = el.querySelector('.event__homeParticipant, .event__participant--home');
                const away = el.querySelector('.event__awayParticipant, .event__participant--away');
                const time = el.querySelector('.event__time');
                const scoreHome = el.querySelector('.event__score--home');
                const scoreAway = el.querySelector('.event__score--away');
                const stage = el.querySelector('.event__stage--block');
                
                if (home && away) {
                    const matchId = el.id || '';
                    results.push({
                        id: matchId,
                        league: currentLeague,
                        country: currentCountry,
                        home: home.textContent.trim(),
                        away: away.textContent.trim(),
                        time: time ? time.textContent.trim() : '',
                        score_home: scoreHome ? scoreHome.textContent.trim() : '',
                        score_away: scoreAway ? scoreAway.textContent.trim() : '',
                        stage: stage ? stage.textContent.trim() : '',
                        is_live: el.classList.contains('event__match--live'),
                    });
                }
            }
            
            return results;
        }""")

        logger.info(f"Extracted {len(fixtures)} fixtures")
        
        # Show first 20
        for i, fix in enumerate(fixtures[:20]):
            logger.info(f"  [{i}] {fix['league']}: {fix['home']} vs {fix['away']} @ {fix['time']} {'LIVE' if fix['is_live'] else ''}")
        
        # Get a match ID for the stats test  
        match_ids = [f['id'] for f in fixtures if f['id'] and not f['is_live']]
        
        browser.close()
        
        return fixtures, match_ids


def extract_match_detail(match_id: str):
    """Extract match stats and H2H from a Flashscore match detail page."""
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    # Match ID format: g_1_XXXXXXXX → extract the event ID part
    event_id = match_id.replace("g_1_", "")
    url = f"https://www.flashscore.com/match/{event_id}/#/match-summary"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-GB",
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        logger.info(f"Loading match detail: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)

        # Cookie consent
        try:
            consent = page.locator("#onetrust-accept-btn-handler")
            if consent.is_visible(timeout=3000):
                consent.click()
                page.wait_for_timeout(1000)
        except Exception:
            pass

        # Extract basic match info
        match_info = page.evaluate("""() => {
            const info = {};
            
            // Teams
            const home = document.querySelector('.duelParticipant__home .participant__participantName');
            const away = document.querySelector('.duelParticipant__away .participant__participantName');
            info.home = home ? home.textContent.trim() : '';
            info.away = away ? away.textContent.trim() : '';
            
            // Tournament
            const tournament = document.querySelector('.tournamentHeader__country');
            info.tournament = tournament ? tournament.textContent.trim() : '';
            
            // Date/time
            const startTime = document.querySelector('.duelParticipant__startTime');
            info.start_time = startTime ? startTime.textContent.trim() : '';
            
            return info;
        }""")
        
        logger.info(f"Match: {match_info.get('home', '?')} vs {match_info.get('away', '?')}")
        logger.info(f"Tournament: {match_info.get('tournament', '?')}")

        # Now try to navigate to statistics tab
        stats_url = f"https://www.flashscore.com/match/{event_id}/#/match-summary/match-statistics/0"
        logger.info(f"Loading stats tab: {stats_url}")
        page.goto(stats_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)

        # Extract statistics
        stats = page.evaluate("""() => {
            const stats = [];
            
            // Try multiple selector strategies for stats
            // Strategy 1: Modern stat rows
            const statRows = document.querySelectorAll('[class*="stat__row"], [class*="statRow"], .stat__row');
            for (const row of statRows) {
                const category = row.querySelector('[class*="stat__category"], [class*="categoryName"]');
                const homeVal = row.querySelector('[class*="stat__homeValue"], [class*="homeValue"]');
                const awayVal = row.querySelector('[class*="stat__awayValue"], [class*="awayValue"]');
                
                if (category && homeVal && awayVal) {
                    stats.push({
                        category: category.textContent.trim(),
                        home: homeVal.textContent.trim(),
                        away: awayVal.textContent.trim()
                    });
                }
            }
            
            // Strategy 2: wcl-statistics pattern
            if (stats.length === 0) {
                const wclRows = document.querySelectorAll('[class*="wcl-statistics"]');
                for (const row of wclRows) {
                    const cells = row.querySelectorAll('[class*="value"], span');
                    if (cells.length >= 3) {
                        stats.push({
                            category: cells[1]?.textContent.trim() || '',
                            home: cells[0]?.textContent.trim() || '',
                            away: cells[2]?.textContent.trim() || ''
                        });
                    }
                }
            }
            
            // Strategy 3: General fallback - look for stat-like containers  
            if (stats.length === 0) {
                // Dump interesting classes on the page for debugging
                const allClasses = new Set();
                document.querySelectorAll('*').forEach(el => {
                    el.classList.forEach(c => {
                        if (c.includes('stat') || c.includes('Stat'))
                            allClasses.add(c);
                    });
                });
                stats.push({debug_classes: Array.from(allClasses)});
            }
            
            return stats;
        }""")
        
        logger.info(f"Statistics ({len(stats)} rows):")
        for s in stats:
            if 'debug_classes' in s:
                logger.info(f"  DEBUG classes: {s['debug_classes']}")
            else:
                logger.info(f"  {s['category']}: {s['home']} - {s['away']}")

        # Try H2H tab
        h2h_url = f"https://www.flashscore.com/match/{event_id}/#/h2h/overall"
        logger.info(f"Loading H2H tab: {h2h_url}")
        page.goto(h2h_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)

        h2h = page.evaluate("""() => {
            const h2h = [];
            
            // H2H match rows
            const rows = document.querySelectorAll('[class*="h2h__row"], [class*="rows"] .h2h__section .event__match, [class*="h2h"] [class*="event__match"]');
            for (const row of rows) {
                const home = row.querySelector('[class*="homeParticipant"], [class*="participant--home"]');
                const away = row.querySelector('[class*="awayParticipant"], [class*="participant--away"]');
                const scoreH = row.querySelector('[class*="score--home"]');
                const scoreA = row.querySelector('[class*="score--away"]');
                const date = row.querySelector('[class*="date"], [class*="time"]');
                
                if (home && away) {
                    h2h.push({
                        home: home.textContent.trim(),
                        away: away.textContent.trim(),
                        score_home: scoreH ? scoreH.textContent.trim() : '',
                        score_away: scoreA ? scoreA.textContent.trim() : '',
                        date: date ? date.textContent.trim() : ''
                    });
                }
            }
            
            // Debug if nothing found
            if (h2h.length === 0) {
                const allClasses = new Set();
                document.querySelectorAll('*').forEach(el => {
                    el.classList.forEach(c => {
                        if (c.includes('h2h') || c.includes('H2H') || c.includes('head'))
                            allClasses.add(c);
                    });
                });
                h2h.push({debug_classes: Array.from(allClasses)});
            }
            
            return h2h;
        }""")
        
        logger.info(f"H2H ({len(h2h)} rows):")
        for h in h2h[:10]:
            if 'debug_classes' in h:
                logger.info(f"  DEBUG classes: {h['debug_classes']}")
            else:
                logger.info(f"  {h.get('date','')} {h['home']} {h.get('score_home','')} - {h.get('score_away','')} {h['away']}")

        # Dump page structure for stats area
        page_structure = page.evaluate("""() => {
            const main = document.querySelector('#detail') || document.querySelector('.detail') || document.body;
            const divs = main.querySelectorAll('div[class]');
            const classes = [];
            for (const d of divs) {
                const c = d.className;
                if (c && !c.includes('ad') && !c.includes('banner') && (c.length < 60)) {
                    classes.push(c);
                }
            }
            return [...new Set(classes)].sort().slice(0, 80);
        }""")
        logger.info(f"Page structure classes ({len(page_structure)}):")
        for c in page_structure[:40]:
            logger.info(f"  .{c}")

        browser.close()
        
        return match_info, stats, h2h


if __name__ == "__main__":
    # Step 1: Extract fixtures
    fixtures, match_ids = extract_fixtures("football")
    
    print(f"\n{'='*60}")
    print(f"Total fixtures: {len(fixtures)}")
    print(f"Match IDs available: {len(match_ids)}")
    
    # Step 2: Try match detail on a scheduled match
    if match_ids:
        # Pick one of the first scheduled matches
        test_id = match_ids[0]
        print(f"\nTesting match detail for: {test_id}")
        print("="*60)
        match_info, stats, h2h = extract_match_detail(test_id)
    else:
        print("No scheduled match IDs found to test detail page")
