
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state="scripts/playwright_storage/betclic.pl.json")
    page = context.new_page()
    
    # Check Sheffield Utd page - what tabs are available
    url = "https://www.betclic.pl/pilka-nozna-sfootball/anglia-championship-c28/sheffield-united-blackburn-m1072460594561024"
    page.goto(url, timeout=20000)
    page.wait_for_timeout(5000)
    
    body = page.inner_text("body")
    lines = body.split(chr(10))
    
    # Print first 60 meaningful lines to see the page structure
    count = 0
    for line in lines:
        s = line.strip()
        if s and len(s) > 2:
            print(s[:200])
            count += 1
            if count > 80:
                break
    
    # Also save the full page for analysis
    with open("betting/data/betclic_verify/SHEF_UTD_page.html", "w") as f:
        f.write(page.content())
    print("Page saved")
    
    browser.close()
