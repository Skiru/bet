"""Debug: check basketball match DOM for participant selectors."""
import sys
sys.stdout.reconfigure(line_buffering=True)

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

p = sync_playwright().start()
browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
ctx = browser.new_context(
    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/136.0.0.0",
    viewport={"width": 1920, "height": 1080},
    locale="en-GB",
)
page = ctx.new_page()
Stealth().apply_stealth_sync(page)

# ── Basketball: inspect first match's HTML ──
print("=== BASKETBALL: first match raw HTML ===", flush=True)
page.goto("https://www.flashscore.com/basketball/", wait_until="domcontentloaded", timeout=30000)
page.wait_for_timeout(5000)
try:
    c = page.locator("#onetrust-accept-btn-handler")
    if c.is_visible(timeout=2000): c.click()
except: pass
page.wait_for_timeout(500)

data = page.evaluate("""() => {
    const result = {};
    const matches = document.querySelectorAll('.event__match');
    result.total_matches = matches.length;
    
    if (matches.length > 0) {
        const m = matches[0];
        result.first_match_html = m.innerHTML.substring(0, 800);
        result.first_match_id = m.id;
        result.first_match_classes = m.className;
        
        // Test various selectors
        const selectors = [
            '.event__homeParticipant',
            '.event__awayParticipant',
            '.event__participant--home',
            '.event__participant--away',
            '.event__participant',
            '[class*="participant"]',
        ];
        
        for (const sel of selectors) {
            const el = m.querySelector(sel);
            result['selector_' + sel] = el ? el.textContent.trim().substring(0, 40) : 'NOT_FOUND';
        }
        
        // Check parent .sportName class
        const parent = m.parentElement;
        result.parent_class = parent ? parent.className.substring(0, 60) : 'NO_PARENT';
        
        // Check if matches are inside .sportName groups
        const sportGroups = document.querySelectorAll('.sportName');
        result.sportName_groups = sportGroups.length;
        
        // Count matches inside sportName groups vs loose
        let insideCount = 0;
        for (const sg of sportGroups) {
            insideCount += sg.querySelectorAll('.event__match').length;
        }
        result.matches_inside_sportName = insideCount;
        result.matches_outside_sportName = matches.length - insideCount;
    }
    
    return result;
}""")

for k, v in data.items():
    print(f"  {k}: {v}", flush=True)

# Also check hockey
print("\n=== HOCKEY: first match selectors ===", flush=True)
page.goto("https://www.flashscore.com/hockey/", wait_until="domcontentloaded", timeout=30000)
page.wait_for_timeout(5000)

hockey = page.evaluate("""() => {
    const result = {};
    const matches = document.querySelectorAll('.event__match');
    result.total = matches.length;
    
    if (matches.length > 0) {
        const m = matches[0];
        result.id = m.id;
        result.html = m.innerHTML.substring(0, 600);
        
        const selectors = [
            '.event__homeParticipant',
            '.event__awayParticipant',
            '.event__participant--home',
            '.event__participant--away',
        ];
        for (const sel of selectors) {
            const el = m.querySelector(sel);
            result['sel_' + sel] = el ? el.textContent.trim().substring(0, 40) : 'NOT_FOUND';
        }
        
        // Is it in sportName group?
        result.parent_class = m.parentElement ? m.parentElement.className.substring(0, 60) : 'NO_PARENT';
    }
    return result;
}""")

for k, v in hockey.items():
    print(f"  {k}: {v}", flush=True)

browser.close()
p.stop()
print("\nDONE", flush=True)
