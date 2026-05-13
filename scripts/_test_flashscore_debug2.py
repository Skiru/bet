"""Debug: understand Flashscore league grouping structure."""
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

# Understand .sportName containers (league groups)
info = page.evaluate("""() => {
    const sportNames = document.querySelectorAll('.sportName');
    const groups = [];
    
    for (let i = 0; i < Math.min(sportNames.length, 5); i++) {
        const sn = sportNames[i];
        const group = {
            class: sn.className,
            childCount: sn.children.length,
            children: [],
        };
        
        for (let j = 0; j < Math.min(sn.children.length, 8); j++) {
            const child = sn.children[j];
            const childInfo = {
                tag: child.tagName,
                cls: (child.getAttribute('class') || '').substring(0, 60),
                id: (child.id || '').substring(0, 30),
                textSample: child.textContent.substring(0, 80).replace(/\\n/g, ' ').trim(),
            };
            group.children.push(childInfo);
        }
        groups.push(group);
    }
    
    // Also check for wcl-header or event__header variants
    const headerVariants = [
        '.event__header',
        '.event__title',
        '.sportName__title', 
        '.wcl-header',
        '.heading',
        '.tournamentHeader',
        '.event__expander',
    ];
    const headerInfo = {};
    for (const sel of headerVariants) {
        headerInfo[sel] = document.querySelectorAll(sel).length;
    }
    
    // Check the first sportName children more deeply - find league info
    if (sportNames.length > 0) {
        const first = sportNames[0];
        // Look for text-bearing elements
        const titleEls = first.querySelectorAll('[class*="title"], [class*="name"], [class*="country"], [class*="league"]');
        headerInfo.title_els_in_first = [];
        for (const el of titleEls) {
            headerInfo.title_els_in_first.push({
                cls: (el.getAttribute('class') || '').substring(0, 60),
                text: el.textContent.substring(0, 60).trim(),
            });
        }
    }
    
    return {groups, headerInfo};
}""")

print("=== SPORT NAME GROUPS (first 5) ===", flush=True)
for i, g in enumerate(info['groups']):
    print(f"\nGroup {i}: class={g['class']}, children={g['childCount']}", flush=True)
    for j, child in enumerate(g['children']):
        print(f"  [{j}] {child['tag']}.{child['cls']} id={child['id']}", flush=True)
        print(f"      text: {child['textSample'][:60]}", flush=True)

print("\n=== HEADER VARIANTS ===", flush=True)
for k, v in info['headerInfo'].items():
    if isinstance(v, int):
        print(f"  {k}: {v}", flush=True)
    else:
        print(f"  {k}:", flush=True)
        for item in v:
            print(f"    cls={item['cls']}  text={item['text']}", flush=True)

# Let's also check: what does the first child of .sportName look like (the league container header)?
print("\n=== FIRST SPORTNAME FIRST CHILD - DEEP INSPECT ===", flush=True)
deep = page.evaluate("""() => {
    const sn = document.querySelector('.sportName');
    if (!sn) return {error: 'No .sportName'};
    
    const firstChild = sn.children[0];
    if (!firstChild) return {error: 'No children'};
    
    return {
        tag: firstChild.tagName,
        cls: firstChild.className,
        innerHTML: firstChild.innerHTML.substring(0, 500),
    };
}""")
for k, v in deep.items():
    print(f"  {k}: {v}", flush=True)

browser.close()
p.stop()
print("\nDONE", flush=True)
