"""Test Flashscore DOM extraction — finished match stats + league extraction fix."""
import sys
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def test_league_extraction_and_finished_match():
    """Test improved league header extraction + stats from yesterday's matches."""
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

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

        # Load yesterday's results to get finished matches  
        url = "https://www.flashscore.com/football/?d=1"  # d=1 means yesterday
        logger.info(f"Loading yesterday's results: {url}")
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

        # Improved fixture extraction with league headers
        data = page.evaluate("""() => {
            const results = [];
            let currentLeague = '';
            let currentCountry = '';
            
            // All divs in the main container
            const container = document.querySelector('.sportName.soccer') 
                || document.querySelector('.leagues--live') 
                || document.querySelector('.event');
            if (!container) return {fixtures: [], debug: 'No container found'};
            
            // Iterate ALL children — headers and matches interleaved
            const children = container.children;
            for (let i = 0; i < children.length; i++) {
                const el = children[i];
                const cls = el.className || '';
                
                // League header — identified by event__header class
                if (cls.includes('event__header')) {
                    // Country span + league link
                    const countryEl = el.querySelector('.event__title--type');
                    const leagueEl = el.querySelector('.event__title--name a') || el.querySelector('.event__title--name');
                    
                    if (countryEl) currentCountry = countryEl.textContent.trim().replace(/:$/, '');
                    if (leagueEl) currentLeague = leagueEl.textContent.trim();
                    continue;
                }
                
                // Match row
                if (cls.includes('event__match') || el.id?.startsWith('g_')) {
                    const home = el.querySelector('.event__homeParticipant, .event__participant--home');
                    const away = el.querySelector('.event__awayParticipant, .event__participant--away');
                    const time = el.querySelector('.event__time');
                    const scoreHome = el.querySelector('.event__score--home');
                    const scoreAway = el.querySelector('.event__score--away');
                    const stage = el.querySelector('.event__stage--block');
                    
                    if (home && away) {
                        results.push({
                            id: el.id || '',
                            league: currentLeague,
                            country: currentCountry,
                            home: home.textContent.trim(),
                            away: away.textContent.trim(),
                            time: time ? time.textContent.trim() : '',
                            score_home: scoreHome ? scoreHome.textContent.trim() : '',
                            score_away: scoreAway ? scoreAway.textContent.trim() : '',
                            stage: stage ? stage.textContent.trim() : '',
                            is_finished: cls.includes('event__match--last') || (stage && stage.textContent.includes('FT')),
                        });
                    }
                }
            }
            
            return {fixtures: results, count: results.length};
        }""")

        fixtures = data.get("fixtures", [])
        logger.info(f"Extracted {len(fixtures)} fixtures from yesterday")
        
        # Show first 15 with league info
        for i, fix in enumerate(fixtures[:15]):
            status = "FT" if fix.get('is_finished') else fix.get('stage', '?')
            logger.info(f"  [{i}] {fix.get('country','?')}: {fix.get('league','?')} | {fix['home']} {fix.get('score_home','-')} - {fix.get('score_away','-')} {fix['away']} ({status})")

        # Find a finished match to test stats
        finished = [f for f in fixtures if f.get('is_finished') and f.get('id')]
        logger.info(f"\nFinished matches with IDs: {len(finished)}")
        
        if not finished:
            logger.warning("No finished matches found!")
            browser.close()
            return

        # Pick a top-league finished match
        test_match = finished[0]
        event_id = test_match['id'].replace('g_1_', '')
        logger.info(f"\nTesting stats for: {test_match['home']} vs {test_match['away']} (ID: {event_id})")

        # Navigate to match stats page  
        stats_url = f"https://www.flashscore.com/match/{event_id}/#/match-summary/match-statistics/0"
        page.goto(stats_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)

        # Dump all visible text to find stat patterns
        stats_area = page.evaluate("""() => {
            const result = {stats: [], debug_selectors: [], page_text_sample: ''};
            
            // Try direct stat selectors
            const selectors = [
                '.stat__row',
                '[class*="statRow"]',
                '[class*="stat__"]',
                '.wcl-statisticsRow',
                '.statisticsRow',
                // Try data-testid patterns
                '[data-testid*="stat"]',
                // Generic rows in tab content
                '.section .rows .row',
                '.tabContent__match-summary .rows',
            ];
            
            for (const sel of selectors) {
                const els = document.querySelectorAll(sel);
                if (els.length > 0) {
                    result.debug_selectors.push({selector: sel, count: els.length});
                    for (const el of els) {
                        result.stats.push({
                            selector: sel,
                            text: el.textContent.trim().substring(0, 200),
                            classes: el.className,
                            childrenCount: el.children.length,
                        });
                    }
                }
            }
            
            // Also get all class names with 'stat' or 'row' in them
            const allClasses = new Set();
            document.querySelectorAll('*').forEach(el => {
                el.classList.forEach(c => {
                    if (c.includes('stat') || c.includes('Stat') || c.includes('row') || c.includes('Row'))
                        allClasses.add(c);
                });
            });
            result.stat_row_classes = Array.from(allClasses).sort();
            
            // Get the tab content area text
            const tabContent = document.querySelector('#detail .section') || document.querySelector('.detailTab');
            if (tabContent) {
                result.page_text_sample = tabContent.textContent.substring(0, 1000);
            }
            
            return result;
        }""")

        logger.info(f"Debug selectors matched: {stats_area.get('debug_selectors', [])}")
        logger.info(f"Stat/Row classes on page: {stats_area.get('stat_row_classes', [])}")
        logger.info(f"Stats found: {len(stats_area.get('stats', []))}")
        for s in stats_area.get('stats', [])[:10]:
            logger.info(f"  [{s.get('selector')}] {s.get('text')[:100]}")
        
        if stats_area.get('page_text_sample'):
            logger.info(f"\nPage text sample (stats area):")
            logger.info(stats_area['page_text_sample'][:500])

        # Test H2H with improved selectors
        h2h_url = f"https://www.flashscore.com/match/{event_id}/#/h2h/overall"
        page.goto(h2h_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)

        h2h_data = page.evaluate("""() => {
            const result = {matches: [], debug: []};
            
            // Find all rows in the H2H section
            const rows = document.querySelectorAll('.rows .h2h__row, .h2h__section .rows .event__match, .rows [class*="event__match"]');
            
            for (const row of rows) {
                const cells = row.querySelectorAll('span, div, a');
                const texts = [];
                for (const c of cells) {
                    const t = c.textContent.trim();
                    if (t) texts.push(t);
                }
                
                const home = row.querySelector('.h2h__homeParticipant, [class*="homeParticipant"]');
                const away = row.querySelector('.h2h__awayParticipant, [class*="awayParticipant"]');
                const scoreH = row.querySelector('.h2h__result span:first-child, [class*="score--home"]');
                const scoreA = row.querySelector('.h2h__result span:last-child, [class*="score--away"]');
                const date = row.querySelector('.h2h__date, [class*="date"]');
                
                if (home || away) {
                    result.matches.push({
                        home: home ? home.textContent.trim() : '',
                        away: away ? away.textContent.trim() : '',
                        score_home: scoreH ? scoreH.textContent.trim() : '',
                        score_away: scoreA ? scoreA.textContent.trim() : '',
                        date: date ? date.textContent.trim() : '',
                        all_text: texts.slice(0, 10),
                    });
                }
            }
            
            // Debug: find h2h-related classes
            const allClasses = new Set();
            document.querySelectorAll('*').forEach(el => {
                el.classList.forEach(c => {
                    if (c.includes('h2h') || c.includes('H2H') || c.includes('versus'))
                        allClasses.add(c);
                });
            });
            result.h2h_classes = Array.from(allClasses).sort();
            
            // Get section text
            const section = document.querySelector('.h2h') || document.querySelector('#detail .section') || document.querySelector('.detailTab');
            if (section) {
                result.section_text = section.textContent.substring(0, 800);
            }
            
            return result;
        }""")
        
        logger.info(f"\nH2H classes: {h2h_data.get('h2h_classes', [])}")
        logger.info(f"H2H matches: {len(h2h_data.get('matches', []))}")
        for m in h2h_data.get('matches', [])[:8]:
            logger.info(f"  {m.get('date','')} {m['home']} {m.get('score_home','?')}-{m.get('score_away','?')} {m['away']}")
            if m.get('all_text'):
                logger.info(f"    raw: {m['all_text'][:8]}")
        
        if h2h_data.get('section_text'):
            logger.info(f"\nH2H section text:")
            logger.info(h2h_data['section_text'][:500])

        # Also test team results page for form data
        # Let's use the home team from the test match  
        team_slug = test_match['home'].lower().replace(' ', '-').replace('.', '')
        team_results_url = f"https://www.flashscore.com/team/{team_slug}/results/"
        logger.info(f"\nTesting team results: {team_results_url}")
        page.goto(team_results_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)

        team_results = page.evaluate("""() => {
            const results = [];
            const rows = document.querySelectorAll('.event__match, [id^="g_"]');
            for (const row of rows) {
                const home = row.querySelector('.event__homeParticipant, .event__participant--home');
                const away = row.querySelector('.event__awayParticipant, .event__participant--away');
                const scoreH = row.querySelector('.event__score--home');
                const scoreA = row.querySelector('.event__score--away');
                const time = row.querySelector('.event__time');
                
                if (home && away) {
                    results.push({
                        home: home.textContent.trim(),
                        away: away.textContent.trim(),
                        score_home: scoreH ? scoreH.textContent.trim() : '',
                        score_away: scoreA ? scoreA.textContent.trim() : '',
                        time: time ? time.textContent.trim() : ''
                    });
                }
            }
            return results;
        }""")

        logger.info(f"Team results: {len(team_results)} matches")
        for r in team_results[:10]:
            logger.info(f"  {r.get('time','')} {r['home']} {r.get('score_home','-')}-{r.get('score_away','-')} {r['away']}")

        browser.close()


if __name__ == "__main__":
    test_league_extraction_and_finished_match()
