#!/usr/bin/env python3
"""Fetch a Betclic match detail page with stealth and dump + analyze it.

Finds upcoming (non-live) match from a sport listing page, fetches the match
detail page, and dumps it to html_cache for analysis.

Usage:
    python3 scripts/_fetch_betclic_match.py
    python3 scripts/_fetch_betclic_match.py --sport basketball
    python3 scripts/_fetch_betclic_match.py --url "https://www.betclic.pl/..."
"""
import asyncio
import argparse
import re
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from bs4 import BeautifulSoup

try:
    from stealth_utils import USER_AGENTS, BROWSER_ARGS, is_actually_blocked, random_delay_async
    import random
except ImportError:
    from scripts.stealth_utils import USER_AGENTS, BROWSER_ARGS, is_actually_blocked, random_delay_async
    import random

CACHE_DIR = Path(__file__).resolve().parent.parent / "betting" / "data" / "html_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

SPORT_URLS = {
    "football": "https://www.betclic.pl/pilka-nozna-s1",
    "tennis": "https://www.betclic.pl/tenis-s2",
    "basketball": "https://www.betclic.pl/koszykowka-s4",
    "volleyball": "https://www.betclic.pl/siatkowka-s18",
    "hockey": "https://www.betclic.pl/hokej-na-lodzie-s13",
}


async def fetch_and_analyze(sport: str = "football", direct_url: str = None):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=BROWSER_ARGS,
        )
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1920, "height": 1080},
            locale="pl-PL",
        )
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)
        
        if direct_url:
            match_url = direct_url
        else:
            # Find a non-live upcoming match from the sport listing
            sport_url = SPORT_URLS.get(sport, SPORT_URLS["football"])
            print(f"[1] Fetching sport listing: {sport_url}")
            await page.goto(sport_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            
            # Scroll to load more
            for _ in range(3):
                await page.mouse.wheel(0, 800)
                await page.wait_for_timeout(500)
            
            html = await page.content()
            
            # Find upcoming (non-live) match links
            pattern = re.compile(r'href="(/[^"]*-m\d{10,}[^"]*)"')
            all_links = pattern.findall(html)
            
            if not all_links:
                print("No match links found!")
                await browser.close()
                return
            
            # Prefer non-live matches (they have more market tabs)
            soup = BeautifulSoup(html, "html.parser")
            non_live_links = []
            live_links = []
            for card in soup.select("sports-events-event-card"):
                a = card.select_one("a.cardEvent")
                if not a:
                    continue
                href = a.get("href", "")
                if "is-live" in a.get("class", []):
                    live_links.append(href)
                else:
                    non_live_links.append(href)
            
            target_href = (non_live_links or live_links or all_links)[0]
            match_url = f"https://www.betclic.pl{target_href}" if target_href.startswith("/") else target_href
            
            await random_delay_async(3, 5)
        
        print(f"[2] Fetching match detail: {match_url}")
        resp = await page.goto(match_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)
        
        # Scroll and wait for dynamic content
        for _ in range(2):
            await page.mouse.wheel(0, 500)
            await page.wait_for_timeout(800)
        
        match_html = await page.content()
        status = resp.status if resp else 0
        
        if is_actually_blocked(match_html, status):
            print(f"BLOCKED (HTTP {status}, {len(match_html)} bytes)")
            await browser.close()
            return
        
        # Save to cache
        today = datetime.now().strftime("%Y-%m-%d")
        out_file = CACHE_DIR / f"{today}_betclic_match_{sport}.html"
        out_file.write_text(match_html, encoding="utf-8")
        print(f"[3] Saved {len(match_html):,} bytes to {out_file.name}")
        
        # Analyze the match detail page
        soup = BeautifulSoup(match_html, "html.parser")
        
        print(f"\n{'='*80}")
        print(f"MATCH DETAIL ANALYSIS ({match_url})")
        print(f"{'='*80}")
        
        # Team names
        home = soup.select_one('[data-qa="contestant-1-label"]')
        away = soup.select_one('[data-qa="contestant-2-label"]')
        print(f"\nTeams: {home.get_text(strip=True) if home else '?'} vs {away.get_text(strip=True) if away else '?'}")
        
        # Score
        score = soup.select_one('[data-qa="scoreboard-score"]')
        print(f"Score: {score.get_text(strip=True) if score else 'N/A'}")
        
        # All Angular components  
        print(f"\n[A] Angular components:")
        all_tags = {}
        for tag in soup.find_all(True):
            name = tag.name
            if '-' in name:
                all_tags[name] = all_tags.get(name, 0) + 1
        for tag, count in sorted(all_tags.items(), key=lambda x: -x[1])[:30]:
            print(f"  {tag}: {count}")
        
        # Market tabs
        print(f"\n[B] Market tabs/sections:")
        tabs = soup.select("button[role='tab'], .tab_item, .market-tab, [class*='tab']")
        for t in tabs[:20]:
            text = t.get_text(strip=True)[:60]
            classes = t.get("class", [])
            active = "is-active" in classes or "active" in classes
            print(f"  {'[ACTIVE]' if active else '       '} {text}")
        
        # Market groups
        print(f"\n[C] Market groups:")
        market_groups = soup.select("[class*='marketGroup'], [class*='market-group'], sports-market-group, sports-market")
        if not market_groups:
            market_groups = soup.select("[class*='Market']")
        print(f"  Found {len(market_groups)} market group elements")
        for mg in market_groups[:10]:
            title = mg.select_one("[class*='title'], [class*='Title'], h3, h4")
            title_text = title.get_text(strip=True) if title else mg.get_text(strip=True)[:60]
            print(f"  → {title_text[:60]}")
        
        # Odds buttons on match page
        print(f"\n[D] Bet buttons:")
        bet_buttons = soup.select("button[bcdkbetbutton]")
        print(f"  Found {len(bet_buttons)} bet buttons")
        
        # Group odds by parent market sections
        markets_data = {}
        for btn in bet_buttons:
            labels = btn.select("bcdk-bet-button-label")
            top_label = ""
            odds_val = ""
            for lbl in labels:
                if "is-top" in lbl.get("class", []):
                    top_label = lbl.get_text(strip=True)
                else:
                    odds_val = lbl.get_text(strip=True)
            
            # Find parent market section
            parent = btn.parent
            for _ in range(10):
                if parent is None:
                    break
                classes = parent.get("class", [])
                class_str = " ".join(classes) if isinstance(classes, list) else str(classes)
                if "market" in class_str.lower():
                    market_key = class_str
                    break
                parent = parent.parent
            else:
                market_key = "unknown"
            
            if top_label or odds_val:
                if market_key not in markets_data:
                    markets_data[market_key] = []
                markets_data[market_key].append(f"{top_label}: {odds_val}")
        
        for market, items in list(markets_data.items())[:8]:
            print(f"\n  Market section ({market[:60]}):")
            for item in items[:6]:
                print(f"    {item}")
        
        # Data attributes
        print(f"\n[E] data-qa attributes:")
        qa_els = soup.select("[data-qa]")
        qa_counts = {}
        for el in qa_els:
            qa = el.get("data-qa")
            qa_counts[qa] = qa_counts.get(qa, 0) + 1
        for qa, count in sorted(qa_counts.items(), key=lambda x: -x[1])[:20]:
            print(f"  {qa}: {count}")
        
        # Find over/under, BTTS, handicap market markers
        print(f"\n[F] Market keywords in page text:")
        page_text = soup.get_text().lower()
        keywords = ["over", "under", "powyżej", "poniżej", "btts", "obie strzel",
                     "handicap", "1x2", "wynik meczu", "suma goli", "corners",
                     "rzuty rożne", "karty", "cards", "total", "set", "gem",
                     "moneyline", "spread", "podwójna szansa", "double chance"]
        for kw in keywords:
            count = page_text.count(kw)
            if count > 0:
                print(f"  '{kw}': {count} occurrences")
        
        await browser.close()
        print(f"\n✅ Analysis complete. HTML saved to: {out_file}")


def main():
    parser = argparse.ArgumentParser(description="Fetch + analyze Betclic match detail page")
    parser.add_argument("--sport", default="football", choices=list(SPORT_URLS.keys()))
    parser.add_argument("--url", help="Direct match URL to fetch")
    args = parser.parse_args()
    asyncio.run(fetch_and_analyze(sport=args.sport, direct_url=args.url))


if __name__ == "__main__":
    main()
