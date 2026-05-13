#!/usr/bin/env python3
"""Debug script to discover Soccerway DOM structure.

Soccerway is a JS SPA — test both HTTP API endpoints and Playwright rendering.

Run: PYTHONPATH=src .venv/bin/python scripts/_debug_soccerway.py
"""
import requests
from bs4 import BeautifulSoup
import json
import re
import sys

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.soccerway.com/",
    "Origin": "https://www.soccerway.com",
}


def try_api_endpoints():
    """Try known Soccerway API patterns."""
    endpoints = [
        # Modern SPA API patterns
        "https://www.soccerway.com/api/matches/?date=2026-05-13",
        "https://www.soccerway.com/api/v1/matches/?date=2026-05-13",
        "https://api.soccerway.com/v1/matches/?date=2026-05-13",
        "https://www.soccerway.com/a/block_competition_matches_summary?block_id=page_matches_1_block_competition_matches_summary_1&callback_params=%7B%22date%22%3A%222026-05-13%22%7D&action=changePage&params=%7B%22page%22%3A0%7D",
        # Legacy Soccerway AJAX
        "https://www.soccerway.com/a/block_competition_matches_summary",
        # Try int subdomain
        "https://int.soccerway.com/a/block_competition_matches_summary?block_id=page_matches_1_block_competition_matches_summary_1&callback_params=%7B%22date%22%3A%222026-05-13%22%7D&action=changePage&params=%7B%22page%22%3A0%7D",
    ]

    print("=" * 60)
    print("PHASE 1: API Endpoint Discovery")
    print("=" * 60)

    for url in endpoints:
        print(f"\n  Trying: {url[:100]}...")
        try:
            resp = requests.get(url, headers=API_HEADERS, timeout=10, allow_redirects=False)
            print(f"    Status: {resp.status_code}")
            print(f"    Content-Type: {resp.headers.get('Content-Type', 'N/A')}")
            print(f"    Content length: {len(resp.text)}")
            if resp.status_code == 200 and len(resp.text) > 100:
                # Try JSON parse
                try:
                    data = resp.json()
                    print(f"    ✅ JSON response! Keys: {list(data.keys())[:10]}")
                    if isinstance(data, dict):
                        for k, v in list(data.items())[:3]:
                            print(f"      {k}: {str(v)[:200]}")
                    return data
                except json.JSONDecodeError:
                    # Check if HTML with match data
                    if "<table" in resp.text or "team-a" in resp.text or "match" in resp.text.lower():
                        print(f"    ✅ HTML with potential match data!")
                        soup = BeautifulSoup(resp.text, "html.parser")
                        # Try common selectors
                        for sel in ["td.team-a", "td.team-b", "td.score-time", "tr.match", "table.matches"]:
                            found = soup.select(sel)
                            if found:
                                print(f"      {sel}: {len(found)} elements")
                                print(f"        Sample: {str(found[0])[:200]}")
                        return resp.text
                    else:
                        print(f"    Preview: {resp.text[:300]}")
            elif resp.status_code in (301, 302):
                print(f"    Redirect to: {resp.headers.get('Location', 'N/A')}")
        except Exception as e:
            print(f"    Error: {e}")

    return None


def try_playwright():
    """Use Playwright to render the SPA and discover the DOM."""
    print("\n" + "=" * 60)
    print("PHASE 2: Playwright SPA Rendering")
    print("=" * 60)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  Playwright not installed, skipping.")
        return

    try:
        from playwright_stealth import Stealth
    except ImportError:
        Stealth = None

    try:
        from scripts.stealth_utils import USER_AGENTS, BROWSER_ARGS
    except ImportError:
        USER_AGENTS = ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"]
        BROWSER_ARGS = ["--disable-blink-features=AutomationControlled"]

    import random

    url = "https://www.soccerway.com/matches/2026/05/13/"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        ctx = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1920, "height": 1080},
        )
        page = ctx.new_page()
        if Stealth:
            Stealth().apply_stealth_sync(page)

        # Intercept API calls
        api_calls = []

        def handle_response(response):
            url = response.url
            if "api" in url or "match" in url.lower() or "block" in url:
                api_calls.append(
                    {
                        "url": url,
                        "status": response.status,
                        "content_type": response.headers.get("content-type", ""),
                    }
                )

        page.on("response", handle_response)

        print(f"\n  Navigating to {url}...")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(8000)  # Wait for SPA to render

        # Check final URL
        print(f"  Final URL: {page.url}")

        # Body text
        body = page.inner_text("body")
        print(f"  Body text length: {len(body)}")

        # Intercepted API calls
        print(f"\n  Intercepted API/match calls: {len(api_calls)}")
        for call in api_calls[:15]:
            print(f"    {call['status']} {call['content_type'][:30]:30s} {call['url'][:120]}")

        # DOM hierarchy
        hierarchy = page.evaluate(
            """() => {
            const dump = [];
            const walk = (el, depth) => {
                if (depth > 5) return;
                const classes = el.className && typeof el.className === 'string' ? el.className : '';
                const id = el.id || '';
                const tag = el.tagName || '';
                if ((classes || id) && dump.length < 80) {
                    dump.push('  '.repeat(depth) + tag + (id ? '#' + id : '') + (classes ? '.' + classes.split(' ').slice(0,3).join('.') : ''));
                }
                for (const child of (el.children || [])) walk(child, depth + 1);
            };
            walk(document.body, 0);
            return dump;
        }"""
        )
        print(f"\n  DOM hierarchy ({len(hierarchy)} nodes):")
        for line in hierarchy[:60]:
            print(f"    {line}")

        # Try to find match rows
        for sel in [
            "tr.match",
            "tr[class*=match]",
            "div[class*=match]",
            "div[class*=Match]",
            "div[class*=event]",
            "div[class*=Event]",
            "a[class*=match]",
            "table.matches tr",
            "[data-match-id]",
            "td.team-a",
            "td.team-b",
            "td.score-time",
        ]:
            try:
                found = page.query_selector_all(sel)
                if found:
                    print(f"\n  ✅ {sel}: {len(found)} elements")
                    first = found[0]
                    text = first.inner_text()
                    print(f"     Text: {text[:200]}")
                    html = first.evaluate("el => el.outerHTML")
                    print(f"     HTML: {html[:300]}")
            except Exception:
                pass

        # Body text sample (match-related)
        lines = body.split("\n")
        match_lines = [l.strip() for l in lines if any(kw in l.lower() for kw in ["vs", " - ", "premier", "league", "serie", "bundesliga", "ligue"])]
        if match_lines:
            print(f"\n  Match-related lines ({len(match_lines)}):")
            for line in match_lines[:20]:
                print(f"    {line[:120]}")
        else:
            print(f"\n  Body text preview (first 1500 chars):")
            print(body[:1500])

        ctx.close()
        browser.close()


if __name__ == "__main__":
    result = try_api_endpoints()
    try_playwright()
