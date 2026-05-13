"""Debug: extract country text from headerLeague__wrapper."""
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

page.goto("https://www.flashscore.com/football/", wait_until="domcontentloaded", timeout=30000)
page.wait_for_timeout(5000)
try:
    c = page.locator("#onetrust-accept-btn-handler")
    if c.is_visible(timeout=2000): c.click()
except: pass
page.wait_for_timeout(500)

# Get details from first 5 headers
info = page.evaluate("""() => {
    const headers = document.querySelectorAll('.headerLeague__wrapper');
    const result = [];
    for (let i = 0; i < Math.min(headers.length, 8); i++) {
        const h = headers[i];
        const titleWrapper = h.querySelector('.headerLeague__titleWrapper');
        const leagueTitle = h.querySelector('.headerLeague__title');
        
        // Country is typically after the league title, in the titleWrapper
        // Let's look for it
        const allText = titleWrapper ? titleWrapper.textContent.trim() : '';
        const leagueText = leagueTitle ? leagueTitle.textContent.trim() : '';
        
        // Children of titleWrapper
        const twChildren = [];
        if (titleWrapper) {
            for (const child of titleWrapper.children) {
                twChildren.push({
                    tag: child.tagName,
                    cls: (child.getAttribute('class') || '').substring(0, 60),
                    text: child.textContent.trim().substring(0, 60),
                });
            }
        }
        
        // Try data attributes
        const dataAttrs = {};
        for (const attr of h.attributes) {
            if (attr.name.startsWith('data-')) {
                dataAttrs[attr.name] = attr.value.substring(0, 60);
            }
        }
        
        // Check for country using aria or nested elements
        const countryEl = h.querySelector('[class*="country"]') || h.querySelector('[class*="Country"]');
        
        result.push({
            allText: allText.substring(0, 80),
            leagueText: leagueText,
            countryEl: countryEl ? countryEl.textContent.trim() : 'NOT_FOUND',
            countryClass: countryEl ? countryEl.className.substring(0, 60) : 'N/A',
            dataAttrs,
            twChildren,
        });
    }
    return result;
}""")

for i, h in enumerate(info):
    print(f"\n--- Header {i} ---", flush=True)
    for k, v in h.items():
        print(f"  {k}: {v}", flush=True)

# Now check basketball headers
print("\n\n=== BASKETBALL HEADERS ===", flush=True)
page.goto("https://www.flashscore.com/basketball/", wait_until="domcontentloaded", timeout=30000)
page.wait_for_timeout(5000)

bball = page.evaluate("""() => {
    const headers = document.querySelectorAll('.headerLeague__wrapper');
    const result = [];
    for (let i = 0; i < Math.min(headers.length, 5); i++) {
        const h = headers[i];
        const leagueTitle = h.querySelector('.headerLeague__title');
        const titleWrapper = h.querySelector('.headerLeague__titleWrapper');
        const countryEl = h.querySelector('[class*="country"]') || h.querySelector('[class*="Country"]');
        result.push({
            league: leagueTitle ? leagueTitle.textContent.trim() : 'NOT_FOUND',
            country: countryEl ? countryEl.textContent.trim() : 'NOT_FOUND',
            allText: titleWrapper ? titleWrapper.textContent.trim().substring(0, 80) : 'NO_WRAPPER',
        });
    }
    return result;
}""")
for i, h in enumerate(bball):
    print(f"  Basketball Header {i}: {h}", flush=True)

browser.close()
p.stop()
print("\nDONE", flush=True)
