"""Debug: understand Flashscore DOM structure for league headers + multi-sport."""
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

# ── Football: check DOM hierarchy ──
print("=== FOOTBALL DOM STRUCTURE ===", flush=True)
page.goto("https://www.flashscore.com/football/", wait_until="domcontentloaded", timeout=30000)
page.wait_for_timeout(5000)
try:
    c = page.locator("#onetrust-accept-btn-handler")
    if c.is_visible(timeout=2000): c.click()
except: pass
page.wait_for_timeout(500)

# Check: are headers and matches siblings?
dom_info = page.evaluate("""() => {
    const result = {};
    
    // Find first match and its parent chain
    const firstMatch = document.querySelector('.event__match');
    if (!firstMatch) return {error: 'No .event__match found'};
    
    result.match_tag = firstMatch.tagName;
    result.match_id = firstMatch.id;
    result.match_parent = firstMatch.parentElement?.tagName + '.' + (firstMatch.parentElement?.className || '').substring(0, 60);
    result.match_grandparent = firstMatch.parentElement?.parentElement?.tagName + '.' + (firstMatch.parentElement?.parentElement?.className || '').substring(0, 60);
    
    // Find first header and its parent chain
    const firstHeader = document.querySelector('.event__header');
    if (!firstHeader) return {...result, error: 'No .event__header found'};
    
    result.header_tag = firstHeader.tagName;
    result.header_parent = firstHeader.parentElement?.tagName + '.' + (firstHeader.parentElement?.className || '').substring(0, 60);
    result.header_grandparent = firstHeader.parentElement?.parentElement?.tagName + '.' + (firstHeader.parentElement?.parentElement?.className || '').substring(0, 60);
    
    // Are they siblings?
    result.same_parent = firstMatch.parentElement === firstHeader.parentElement;
    
    // Check: what's the parent of both?
    const commonParent = firstMatch.parentElement;
    const childTypes = [];
    for (let i = 0; i < Math.min(commonParent.children.length, 20); i++) {
        const child = commonParent.children[i];
        childTypes.push({
            tag: child.tagName,
            cls: (child.getAttribute('class') || '').substring(0, 50),
            id: (child.id || '').substring(0, 20),
        });
    }
    result.parent_children_first20 = childTypes;
    result.parent_total_children = commonParent.children.length;
    
    // Also check: does previousElementSibling from first match hit a header?
    let prev = firstMatch.previousElementSibling;
    const prevChain = [];
    while (prev && prevChain.length < 5) {
        prevChain.push({
            tag: prev.tagName,
            cls: (prev.getAttribute('class') || '').substring(0, 50),
        });
        prev = prev.previousElementSibling;
    }
    result.match_prev_siblings = prevChain;
    
    // Try extracting league info from first header
    const titleType = firstHeader.querySelector('.event__title--type');
    const titleName = firstHeader.querySelector('.event__title--name a') || firstHeader.querySelector('.event__title--name');
    result.first_header_country = titleType ? titleType.textContent.trim() : 'NOT FOUND';
    result.first_header_league = titleName ? titleName.textContent.trim() : 'NOT FOUND';
    result.first_header_html = firstHeader.innerHTML.substring(0, 300);
    
    return result;
}""")

for k, v in dom_info.items():
    print(f"  {k}: {v}", flush=True)

# ── Basketball ──
print("\n=== BASKETBALL ===", flush=True)
page.goto("https://www.flashscore.com/basketball/", wait_until="domcontentloaded", timeout=30000)
page.wait_for_timeout(5000)

bball = page.evaluate("""() => {
    const result = {};
    result.event_match_count = document.querySelectorAll('.event__match').length;
    result.any_g_prefix = document.querySelectorAll('[id^="g_"]').length;
    
    // Check for different sport-specific containers
    const sportContainers = [];
    for (const cls of ['sportName', 'leagues--live', 'event', 'container__livetable']) {
        const el = document.querySelector('.' + cls);
        if (el) sportContainers.push({cls: cls, children: el.children.length});
    }
    result.sport_containers = sportContainers;
    
    // Check for WCL components (newer Flashscore uses Web Component Library)
    result.wcl_participants = document.querySelectorAll('[class*="wcl-participant"]').length;
    result.wcl_matches = document.querySelectorAll('[class*="wcl-match"]').length;
    result.wcl_events = document.querySelectorAll('[class*="wcl-event"]').length;
    
    // Get classes containing 'match', 'event', 'sport', 'game'
    const relevantClasses = new Set();
    document.querySelectorAll('*').forEach(el => {
        if (el.classList) {
            el.classList.forEach(c => {
                if (c.includes('match') || c.includes('event') || c.includes('game') || c.includes('sport') || c.includes('league'))
                    relevantClasses.add(c);
            });
        }
    });
    result.relevant_classes = Array.from(relevantClasses).sort().slice(0, 30);
    
    // Get page title
    result.page_title = document.title;
    
    return result;
}""")

for k, v in bball.items():
    print(f"  {k}: {v}", flush=True)

# ── Hockey ──  
print("\n=== HOCKEY ===", flush=True)
page.goto("https://www.flashscore.com/hockey/", wait_until="domcontentloaded", timeout=30000)
page.wait_for_timeout(5000)

hockey = page.evaluate("""() => {
    return {
        event_match_count: document.querySelectorAll('.event__match').length,
        any_g_prefix: document.querySelectorAll('[id^="g_"]').length,
        page_title: document.title,
        body_text_sample: document.body.innerText.substring(0, 300),
    };
}""")

for k, v in hockey.items():
    print(f"  {k}: {v}", flush=True)

# ── Tennis ──
print("\n=== TENNIS ===", flush=True)
page.goto("https://www.flashscore.com/tennis/", wait_until="domcontentloaded", timeout=30000)
page.wait_for_timeout(5000)

tennis = page.evaluate("""() => {
    return {
        event_match_count: document.querySelectorAll('.event__match').length,
        any_g_prefix: document.querySelectorAll('[id^="g_"]').length,
        page_title: document.title,
        body_text_sample: document.body.innerText.substring(0, 300),
    };
}""")

for k, v in tennis.items():
    print(f"  {k}: {v}", flush=True)

browser.close()
p.stop()
print("\nDONE", flush=True)
