import re
import os
import sys

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "betting", "data")

# fetch_odds.py - get odds from OddsPortal match pages
if len(sys.argv) > 1 and sys.argv[1] == "fetch":
    from playwright.sync_api import sync_playwright
    
    # Direct match page URLs on OddsPortal (these have odds)
    match_urls = [
        ("Betis-Real", "https://www.oddsportal.com/football/spain/laliga/real-betis-real-madrid-20260424/"),
        ("Leipzig-Union", "https://www.oddsportal.com/football/germany/bundesliga/rb-leipzig-union-berlin-20260424/"),
        ("Basaksehir-Kasimpasa", "https://www.oddsportal.com/football/turkey/super-lig/istanbul-basaksehir-kasimpasa-20260424/"),
        ("Lubin-Termalica", "https://www.oddsportal.com/football/poland/ekstraklasa/zaglebie-lubin-bruk-bet-termalica-nieciecza-20260424/"),
        ("Brest-Lens", "https://www.oddsportal.com/football/france/ligue-1/stade-brestois-29-rc-lens-20260424/"),
        ("Leicester-Millwall", "https://www.oddsportal.com/football/england/championship/leicester-millwall-20260424/"),
        ("Jagiellonia-Gornik", "https://www.oddsportal.com/football/poland/ekstraklasa/jagiellonia-bialystok-gornik-zabrze-20260424/"),
    ]
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        
        for name, url in match_urls:
            page = ctx.new_page()
            try:
                page.goto(url, wait_until="networkidle", timeout=20000)
                page.wait_for_timeout(2000)
                content = page.content()
                fpath = os.path.join(DATA, f"op_{name.lower()}_apr24.html")
                with open(fpath, "w") as f:
                    f.write(content)
                
                # Extract odds from page
                odds = re.findall(r'"odds":\s*"?(\d+\.\d+)"?', content)
                title = re.search(r"<title>([^<]+)</title>", content)
                title_text = title.group(1) if title else "?"
                print(f"{name}: {len(content)//1024}KB, title={title_text[:60]}, odds_found={odds[:6]}")
            except Exception as e:
                print(f"{name}: ERROR {e}")
            finally:
                page.close()
        
        browser.close()
    sys.exit(0)

def clean(html):
    text = re.sub(r"<[^>]+>", "\n", html)
    return [l.strip() for l in text.split("\n") if l.strip()]

PCT = chr(37)
DOLLAR = chr(36)

# 1. ZawodTyper Apr 24 tips
zt_file = os.path.join(DATA, "zt_typy_dnia_24_apr24.html")
if os.path.exists(zt_file):
    with open(zt_file) as f:
        html = f.read()
    lines = clean(html)
    print("=== ZawodTyper Apr 24 Tips ===")
    # Find tip entries - look for match names and tip text
    for i, l in enumerate(lines):
        if " - " in l and 10 < len(l) < 80:
            # Check if it's a match name (not navigation)
            if any(c.isupper() for c in l[:5]) and not any(kw in l.lower() for kw in ["serwis", "cookie", "login", "menu", "strona"]):
                # Get context around it for tips
                ctx = lines[max(0, i-3):min(len(lines), i+15)]
                # Look for odds and tip text
                odds_in_ctx = [x for x in ctx if re.match(r"^\d+\.\d{2}" + DOLLAR, x)]
                tip_kw = [x for x in ctx if any(kw in x.lower() for kw in ["over", "under", "btts", "obie", "powy", "poni", "handicap", "korner", "corner", "kartek", "card", "foule", "foul", "gole", "goal", "wynik", "wygra", "remis"])]
                if odds_in_ctx or tip_kw:
                    print(f"\n  MATCH: {l}")
                    for c in ctx:
                        if any(kw in c.lower() for kw in ["over", "under", "btts", "obie", "powy", "poni", "handicap", "korner", "corner", "kartek", "card", "foule", "foul", "wynik", "wygra"]) or re.match(r"^\d+\.\d{2}" + DOLLAR, c):
                            print(f"    TIP: {c}")
                    for c in ctx:
                        if re.match(r"^\d+" + DOLLAR, c) and not re.match(r"^\d+\.\d", c):
                            pass  # skip pure numbers
                        elif PCT in c:
                            print(f"    STAT: {c}")

# 2. BetExplorer leagues - find Apr 24 matches with odds
for league, fp in [
    ("Italy Serie A", "be_napoli_cremonese_apr24.html"),
    ("France Ligue 1", "be_brest_lens_apr24.html"),
    ("Poland Ekstraklasa", "be_jagiellonia_apr24.html"),
    ("Spain LaLiga2", "be_spain2_apr24.html"),
]:
    fullpath = os.path.join(DATA, fp)
    if not os.path.exists(fullpath):
        continue
    with open(fullpath) as f:
        html = f.read()
    
    print(f"\n=== BetExplorer {league} ===")
    # Find matches with data-dt for Apr 24
    rows = re.findall(r'data-dt="24,4,2026[^"]*"', html)
    print(f"  Apr 24 rows: {len(rows)}")
    
    # Find match links with odds
    # Pattern: team name in link + odds
    match_blocks = re.findall(r'<tr[^>]*data-dt="24,4,2026[^"]*"[^>]*>(.*?)</tr>', html, re.DOTALL)
    if not match_blocks:
        # Try finding Apr 24 matches differently
        # Look for data-dt with Apr 24
        all_rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
        for row in all_rows:
            if '24,4,2026' in row:
                names = re.findall(r'class="in-match"[^>]*>([^<]+)', row)
                odds = re.findall(r'data-odd="([^"]+)"', row)
                if names or odds:
                    print(f"  Match: {' vs '.join(names)} | Odds: {odds}")
    else:
        for block in match_blocks:
            names = re.findall(r'class="in-match"[^>]*>([^<]+)', block)
            odds = re.findall(r'data-odd="([^"]+)"', block)
            time_m = re.findall(r'(\d{2}:\d{2})', block)
            if names:
                print(f"  {' vs '.join(names)} | Time: {time_m} | Odds: {odds}")

# 3. OLBG tips
olbg_file = os.path.join(DATA, "olbg_tomorrow_apr24.html")
if os.path.exists(olbg_file):
    with open(olbg_file) as f:
        html = f.read()
    lines = clean(html)
    print(f"\n=== OLBG Football ===")
    count = 0
    for l in lines:
        if " v " in l and 10 < len(l) < 60 and count < 15:
            print(f"  {l}")
            count += 1

# 4. BetIdeas
bi_file = os.path.join(DATA, "betideas_tomorrow_apr24.html")
if os.path.exists(bi_file):
    with open(bi_file) as f:
        html = f.read()
    lines = clean(html)
    print(f"\n=== BetIdeas Tomorrow ===")
    count = 0
    for l in lines:
        if " vs " in l.lower() or " v " in l and 10 < len(l) < 60 and count < 15:
            print(f"  {l}")
            count += 1
    # Look for tip categories
    for l in lines:
        if any(kw in l.lower() for kw in ["btts", "corner", "over", "under", "card"]) and len(l) < 80:
            if count < 25:
                print(f"  TIP: {l}")
                count += 1
