"""Quick: find yesterday results on Flashscore and test stats."""
import sys
import traceback
sys.stdout.reconfigure(line_buffering=True)
print("START", flush=True)

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

try:
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/136.0.0.0",
        viewport={"width": 1920, "height": 1080},
        locale="en-GB",
    )
    page = ctx.new_page()
    Stealth().apply_stealth_sync(page)

    # Try the yesterday URL pattern
    urls_to_try = [
        "https://www.flashscore.com/football/?d=-1",
        "https://www.flashscore.com/football/2026-05-12/",
    ]
    
    for url in urls_to_try:
        print(f"\nTrying: {url}", flush=True)
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)
        
        try:
            c = page.locator("#onetrust-accept-btn-handler")
            if c.is_visible(timeout=1500):
                c.click()
                page.wait_for_timeout(500)
        except Exception:
            pass

        count = page.evaluate("""() => {
            return document.querySelectorAll(".event__match[id^='g_1_']").length;
        }""")
        print(f"  Matches found: {count}", flush=True)
        
        if count > 0:
            # Get some with scores (finished)
            data = page.evaluate("""() => {
                const ms = document.querySelectorAll(".event__match[id^='g_1_']");
                const results = [];
                for (const m of ms) {
                    const sh = m.querySelector('.event__score--home');
                    const sa = m.querySelector('.event__score--away');
                    if (sh && sa && sh.textContent.trim() && sa.textContent.trim()) {
                        const home = m.querySelector('.event__homeParticipant');
                        const away = m.querySelector('.event__awayParticipant');
                        results.push({
                            id: m.id,
                            home: home ? home.textContent.trim() : '?',
                            away: away ? away.textContent.trim() : '?',
                            score: sh.textContent.trim() + '-' + sa.textContent.trim(),
                        });
                    }
                    if (results.length >= 5) break;
                }
                return results;
            }""")
            print(f"  Finished matches: {len(data)}", flush=True)
            for d in data:
                print(f"    {d['home']} {d['score']} {d['away']} (ID: {d['id']})", flush=True)
            
            if data:
                # Go to stats for the first finished match
                eid = data[0]["id"].replace("g_1_", "")
                print(f"\n  Stats for: {eid}", flush=True)
                page.goto(f"https://www.flashscore.com/match/{eid}/#/match-summary/match-statistics/0",
                          wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)
                
                detail = page.evaluate("""() => {
                    const d = document.querySelector('#detail');
                    return d ? d.innerText : 'NO DETAIL';
                }""")
                print(f"  Detail ({len(detail)} chars):", flush=True)
                # Print lines containing stat keywords
                for line in detail.split("\n"):
                    line = line.strip()
                    if line and any(kw in line.lower() for kw in [
                        "ball possession", "shots", "corner", "foul", "yellow", "red",
                        "offsides", "saves", "%", "goal attempt", "free kick", "throw",
                        "blocked", "cross", "tackle", "pass"
                    ]):
                        print(f"    STAT: {line}", flush=True)
                
                # Also print raw text around "STATISTICS" keyword
                if "STATISTICS" in detail.upper() or "SUMMARY" in detail.upper():
                    idx = max(detail.upper().find("STATISTICS"), detail.upper().find("STAT"))
                    if idx >= 0:
                        print(f"\n  Text around STATISTICS ({idx}):", flush=True)
                        print(detail[max(0,idx-100):idx+500], flush=True)
                
                # Print first 1500 chars
                print(f"\n  Full detail (first 1500):\n{detail[:1500]}", flush=True)
            break

    browser.close()
    p.stop()
    print("DONE", flush=True)
except Exception as e:
    print(f"ERROR: {e}", flush=True)
    traceback.print_exc()
