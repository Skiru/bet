"""Quick test: extract stats data-testid values from a finished Premier League match."""
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# Man City vs Crystal Palace was yesterday — let's find its ID and get stats
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=[
        "--disable-blink-features=AutomationControlled", "--no-sandbox",
    ])
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="en-GB",
    )
    page = context.new_page()
    Stealth().apply_stealth_sync(page)

    # First, find Man City match ID from yesterday
    page.goto("https://www.flashscore.com/football/?d=1", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)
    try:
        consent = page.locator("#onetrust-accept-btn-handler")
        if consent.is_visible(timeout=3000):
            consent.click()
            page.wait_for_timeout(1000)
    except Exception:
        pass

    # Find Man City match
    match_id = page.evaluate("""() => {
        const matches = document.querySelectorAll('.event__match, [id^="g_1_"]');
        for (const m of matches) {
            const text = m.textContent;
            if (text.includes('Manchester City') || text.includes('Crystal Palace')) {
                return m.id;
            }
        }
        return null;
    }""")
    
    logger.info(f"Man City match ID: {match_id}")
    
    if match_id:
        event_id = match_id.replace('g_1_', '')
        
        # Go to stats page
        stats_url = f"https://www.flashscore.com/match/{event_id}/#/match-summary/match-statistics/0"
        logger.info(f"Loading stats: {stats_url}")
        page.goto(stats_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(6000)
        
        # Dump ALL data-testid attributes and their values
        testid_dump = page.evaluate("""() => {
            const result = [];
            const els = document.querySelectorAll('[data-testid]');
            for (const el of els) {
                const testid = el.getAttribute('data-testid');
                const text = el.textContent?.trim()?.substring(0, 100);
                const classes = el.className;
                const tag = el.tagName;
                if (testid.includes('stat') || testid.includes('wcl')) {
                    result.push({testid, text, classes: classes?.substring(0, 80), tag, childCount: el.children.length});
                }
            }
            return result;
        }""")
        
        logger.info(f"Data-testid elements: {len(testid_dump)}")
        for item in testid_dump[:30]:
            logger.info(f"  testid={item['testid']} tag={item['tag']} text='{item.get('text','')[:60]}' children={item.get('childCount')}")
        
        # Try WCL component approach — these might use shadow DOM
        wcl_data = page.evaluate("""() => {
            const result = [];
            // Try wcl-statistics selectors
            const wclRows = document.querySelectorAll('[class*="wcl-statistics"], [class*="wcl-stat"]');
            for (const row of wclRows) {
                result.push({
                    class: row.className?.substring(0, 100),
                    text: row.textContent?.trim()?.substring(0, 200),
                    innerHTML: row.innerHTML?.substring(0, 300),
                    childCount: row.children.length
                });
            }
            
            // Also try the generic approach — find all elements in the statistics section
            const statSection = document.querySelector('[class*="matchStatistics"], [class*="statistic"], .section__statisticContent');
            if (statSection) {
                result.push({
                    section: true,
                    class: statSection.className,
                    text: statSection.textContent?.trim()?.substring(0, 500),
                    childCount: statSection.children.length
                });
            }
            
            // Try innerText on the stats tab content
            const tabContent = document.querySelector('.tabContent__match-summary');
            if (tabContent) {
                result.push({
                    tabContent: true,
                    innerText: tabContent.innerText?.substring(0, 800),
                });
            }
            
            return result;
        }""")
        
        logger.info(f"\nWCL/Stats section data: {len(wcl_data)} items")
        for item in wcl_data:
            if item.get('tabContent'):
                logger.info(f"  TAB CONTENT innerText:\n{item.get('innerText', '')}")
            elif item.get('section'):
                logger.info(f"  SECTION: class={item.get('class','')[:60]} text={item.get('text','')[:200]}")
            else:
                logger.info(f"  WCL: class={item.get('class','')[:60]} text={item.get('text','')[:80]}")

        # Last resort: just get ALL text from the page detail area
        detail_text = page.evaluate("""() => {
            const detail = document.querySelector('#detail');
            return detail ? detail.innerText?.substring(0, 2000) : 'NO #detail FOUND';
        }""")
        logger.info(f"\n#detail innerText:\n{detail_text[:1000]}")
    
    browser.close()
