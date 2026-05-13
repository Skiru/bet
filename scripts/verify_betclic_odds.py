#!/usr/bin/env python3
"""Verify Betclic odds for pending picks by navigating to match pages with Playwright.

Reads pending picks from picks-ledger.csv for a given betting day,
searches Betclic for each match, navigates to the match page,
and extracts the target market odds (Over/Under totals, game totals, etc.).

Usage:
    python3 scripts/verify_betclic_odds.py --betting-day 2026-04-22
    python3 scripts/verify_betclic_odds.py  # defaults to today

Outputs: betting/data/betclic_verified_odds.json
"""
import sys
import json
import re
import csv
import time
import random
import argparse
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import quote

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from betclic_helpers import load_selectors, USER_AGENTS, STORAGE_DIR

DATA_DIR = BASE.parent / "betting" / "data"
LEDGER_PATH = BASE.parent / "betting" / "journal" / "picks-ledger.csv"

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright not available. Install: pip install playwright && playwright install chromium")
    sys.exit(1)

from bs4 import BeautifulSoup

ODDS_RE = re.compile(r"\b(\d+[.,]\d{2})\b")

MARKET_TAB_KEYWORDS = {
    "totals": ["Gole", "Bramki", "Totals", "Over/Under", "Liczba goli"],
    "game_totals": ["Gemy", "Games", "Total gems", "Gems"],
    "btts": ["Obie strzel", "BTTS", "Both Teams"],
    "corners": ["Rzuty rozne", "Corners"],
}

SPORT_PATHS = {
    "football": "pilka-nozna-s1",
    "tennis": "tenis-s2",
    "basketball": "koszykowka-s4",
    "hockey": "hokej-na-lodzie-s13",
    "volleyball": "siatkowka-s18",
}

DEFAULT_THRESHOLDS = {
    "Over 2.5": 1.30,
    "Under 2.5": 1.40,
    "Over 20.5": 1.30,
    "Over 3.5": 1.40,
    "Under 3.5": 1.30,
}


def parse_threshold_from_notes(notes):
    """Extract acceptance threshold from pick notes like 'accept if >= 1.38'."""
    m = re.search(r"accept if >= (\d+\.\d+)", notes or "")
    if m:
        return float(m.group(1))
    return None


def load_pending_picks(betting_day):
    """Load pending picks for a betting day from picks-ledger.csv."""
    picks = []
    if not LEDGER_PATH.exists():
        print(f"Ledger not found: {LEDGER_PATH}")
        return picks

    with open(LEDGER_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["betting_day"] != betting_day:
                continue
            if row["status"] not in ("pending", "placed"):
                continue

            event = row["event"]
            parts = event.replace(" vs ", " vs ").split(" vs ")
            if len(parts) == 2:
                # Use last meaningful word from each team (skip short tokens like "R.", "NY", "FC")
                home_words = [w for w in parts[0].strip().split() if len(w) > 2 and not w.endswith('.')]
                away_words = [w for w in parts[1].strip().split() if len(w) > 2 and not w.endswith('.')]
                home_short = home_words[-1] if home_words else parts[0].strip().split()[-1]
                away_short = away_words[-1] if away_words else parts[1].strip().split()[-1]
                search_term = f"{home_short} {away_short}"
            else:
                search_term = event.replace(" vs ", " ").replace(" - ", " ")

            selection = row["selection"]
            market = row["market"]

            threshold = parse_threshold_from_notes(row.get("notes", ""))
            if threshold is None:
                for pattern, default_t in DEFAULT_THRESHOLDS.items():
                    if pattern.lower() in selection.lower():
                        threshold = default_t
                        break
            if threshold is None:
                threshold = 1.30

            sport = row.get("sport", "football")

            picks.append({
                "pick_id": row["pick_id"],
                "event": event,
                "search_term": search_term,
                "sport": sport,
                "sport_path": SPORT_PATHS.get(sport, "pilka-nozna-s1"),
                "market": market,
                "selection": selection,
                "bookmaker_odds": float(row.get("bookmaker_odds", 0) or 0),
                "threshold": threshold,
                "stake": float(row.get("stake_pln", 0) or 0),
            })

    return picks


def extract_target_odds(html, market, selection):
    """Extract specific market odds from a Betclic match page."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    result = {"all_odds": [], "target_odds": None, "market_found": False, "raw_snippet": ""}

    for m in ODDS_RE.finditer(text):
        val = float(m.group(1).replace(",", "."))
        if 1.01 <= val <= 50.0:
            result["all_odds"].append(val)

    sel_lower = selection.lower()

    # Handle BTTS markets (no numeric line)
    if "btts" in sel_lower or "obie" in sel_lower or "both team" in sel_lower:
        is_yes = "yes" in sel_lower or "tak" in sel_lower
        is_no = "no" in sel_lower and "both" not in sel_lower.split("no")[0][-5:]
        # Default to "No" if selection is "BTTS No"
        if "no" in sel_lower:
            is_no = True
            is_yes = False
        btts_patterns = [
            # "Nie 1.89" or "No 2.00" or "Tak 1.81" or "Yes 1.73"
            (r"(?:Nie|No)\s{0,10}?(\d+[.,]\d{2})", is_no),
            (r"(?:Tak|Yes)\s{0,10}?(\d+[.,]\d{2})", is_yes),
            (r"(\d+[.,]\d{2})\s{0,10}?(?:Nie|No)", is_no),
            (r"(\d+[.,]\d{2})\s{0,10}?(?:Tak|Yes)", is_yes),
        ]
        for pat, wanted in btts_patterns:
            if not wanted:
                continue
            hit = re.search(pat, text, re.IGNORECASE)
            if hit:
                val = float(hit.group(1).replace(",", "."))
                if 1.01 <= val <= 15.0:
                    start = max(0, hit.start() - 30)
                    end = min(len(text), hit.end() + 30)
                    result["raw_snippet"] = text[start:end]
                    result["target_odds"] = val
                    result["market_found"] = True
                    break
        return result

    # Handle moneyline markets (no numeric line) — return all_odds for manual inspection
    if "ml" in sel_lower or "moneyline" in sel_lower or "win" in sel_lower:
        # Can't reliably auto-extract ML odds without knowing page layout
        # Return all odds for manual review
        result["market_found"] = bool(result["all_odds"])
        return result

    # Handle Over/Under with numeric line
    line_match = re.search(r"(\d+\.\d)", selection)
    line = line_match.group(1) if line_match else None
    if not line:
        return result

    is_over = "over" in sel_lower
    is_under = "under" in sel_lower

    line_esc = line.replace(".", "[.,]")

    if is_over:
        dw = r"(?:Powy.ej|Over|Pow\.?|Wi.cej)"
    elif is_under:
        dw = r"(?:Poni.ej|Under|Pon\.?|Mniej)"
    else:
        dw = r"(?:Powy.ej|Over|Poni.ej|Under)"

    patterns = [
        rf"{dw}\s*{line_esc}\s{{0,20}}?(\d+[.,]\d{{2}})",
        rf"(\d+[.,]\d{{2}})\s{{0,10}}?{dw}\s*{line_esc}",
        rf"{line_esc}[\s\S]{{0,40}}?(\d+[.,]\d{{2}})",
    ]

    for pat in patterns:
        hit = re.search(pat, text, re.IGNORECASE)
        if hit:
            val = float(hit.group(1).replace(",", "."))
            if 1.01 <= val <= 15.0:
                start = max(0, hit.start() - 30)
                end = min(len(text), hit.end() + 30)
                result["raw_snippet"] = text[start:end]
                result["target_odds"] = val
                result["market_found"] = True
                break

    return result


def save_html_snapshot(html, pick_id):
    """Save HTML snapshot for debugging."""
    d = DATA_DIR / "betclic_verify"
    d.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%H%M%S")
    path = d / f"{pick_id}_{ts}.html"
    path.write_text(html, encoding="utf-8")
    return path


def list_to_batches(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def verify_odds(picks):
    """Navigate Betclic and verify odds for each pick."""
    if not picks:
        print("No pending picks to verify.")
        return []

    selectors_map = load_selectors()
    domain = "betclic.pl"
    selectors = selectors_map.get(domain, []) + selectors_map.get("default", [])
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    storage_file = STORAGE_DIR / f"{domain}.json"

    results = []

    try:
        from playwright_stealth import Stealth
    except ImportError:
        Stealth = None

    try:
        from scripts.stealth_utils import USER_AGENTS, BROWSER_ARGS, is_actually_blocked, random_delay_sync
        import random
    except ImportError:
        try:
            from stealth_utils import USER_AGENTS, BROWSER_ARGS, is_actually_blocked, random_delay_sync
            import random
        except ImportError:
            USER_AGENTS = ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"]
            def random_delay_sync(min_s, max_s):
                import time; time.sleep(min_s)
            def is_actually_blocked(content, status_code):
                return False

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=BROWSER_ARGS if 'BROWSER_ARGS' in dir() else ['--disable-blink-features=AutomationControlled', '--disable-infobars', '--no-sandbox']
        )
        ctx_kwargs = {
            "user_agent": random.choice(USER_AGENTS),
            "viewport": {"width": 1920, "height": 1080},
            "locale": "pl-PL",
        }
        if storage_file.exists():
            ctx_kwargs["storage_state"] = str(storage_file)

        ctx = browser.new_context(**ctx_kwargs)
        page = ctx.new_page()
        if Stealth:
            Stealth().apply_stealth_sync(page)

        print("[verify] Loading Betclic homepage...")
        try:
            page.goto("https://www.betclic.pl/", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
            for sel in selectors:
                try:
                    el = page.query_selector(sel)
                    if el:
                        el.click(timeout=3000)
                        page.wait_for_timeout(500)
                except Exception:
                    pass
        except Exception as e:
            print(f"[verify] Homepage warning: {e}")

        pick_count = 0
        for pick in picks:
            if pick_count > 0 and pick_count % 3 == 0:
                print("[verify] Rotating context...")
                ctx.close()
                ctx_kwargs["user_agent"] = random.choice(USER_AGENTS)
                ctx = browser.new_context(**ctx_kwargs)
                page = ctx.new_page()
                if Stealth:
                    Stealth().apply_stealth_sync(page)

            pick_count += 1
            pid = pick["pick_id"]
            search = pick["search_term"]
            market = pick["market"]
            selection = pick["selection"]
            threshold = pick["threshold"]

            print(f"\n[verify] {pid}: {pick['event']} | {selection}")
            print(f"  Searching: '{search}'...")

            r = {
                "pick_id": pid,
                "event": pick["event"],
                "market": market,
                "selection": selection,
                "estimated_odds": pick["bookmaker_odds"],
                "threshold": threshold,
                "verified_odds": None,
                "passes_threshold": None,
                "match_url": None,
                "status": "not_found",
                "snippet": "",
            }

            try:
                match_url = None
                search_parts = search.lower().split()

                # Strategy 1: Try search (works only when logged in)
                search_url = "https://www.betclic.pl/sport/szukaj?q=" + quote(search)
                page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(3000)
                current = page.url
                if "login" not in current:
                    # Search worked (logged in) — look for match link
                    for link in page.query_selector_all("a[href]"):
                        href = link.get_attribute("href") or ""
                        text = (link.inner_text() or "").lower()
                        if len(search_parts) >= 2 and all(pt in text or pt in href.lower() for pt in search_parts):
                            match_url = href if href.startswith("http") else "https://www.betclic.pl" + href
                            break
                    if not match_url:
                        print("  Search returned no match links")
                else:
                    print("  Search requires login, using sport-page fallback")

                # Strategy 2: Browse sport page (no login needed)
                if not match_url:
                    sport_url = "https://www.betclic.pl/" + pick["sport_path"]
                    page.goto(sport_url, wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(3000)
                    # Scroll down to load more matches
                    for _ in range(3):
                        page.evaluate("window.scrollBy(0, 800)")
                        page.wait_for_timeout(800)
                    html = page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    for a in soup.find_all("a", href=True):
                        text = a.get_text(" ", strip=True).lower()
                        href_lower = a["href"].lower()
                        if len(search_parts) >= 2 and all(pt in text or pt in href_lower for pt in search_parts):
                            href = a["href"]
                            match_url = href if href.startswith("http") else "https://www.betclic.pl" + href
                            break

                # Strategy 3: Try direct URL pattern guess based on team names in slug
                if not match_url:
                    slug = "-".join(search_parts)
                    guess_url = f"https://www.betclic.pl/{pick['sport_path']}/{slug}"
                    page.goto(guess_url, wait_until="domcontentloaded", timeout=10000)
                    page.wait_for_timeout(2000)
                    if page.url != guess_url and "login" not in page.url and "/404" not in page.url:
                        # Betclic may have redirected to the correct match page
                        match_url = page.url
                    elif "login" not in page.url and page.query_selector("[class*=odds], [class*=score], [class*=match]"):
                        match_url = page.url

                if match_url:
                    r["match_url"] = match_url
                    print(f"  Found: {match_url}")

                    for backoff in [5, 12, None]:
                        response = page.goto(match_url, wait_until="domcontentloaded", timeout=15000)
                        status_code = response.status if response else 0
                        page.wait_for_timeout(3000)
                        
                        content = page.content()
                        if "cf-browser-verification" in content or "Just a moment" in content:
                            page.wait_for_timeout(5000)
                            content = page.content()
                            
                        if is_actually_blocked(content, status_code):
                            print(f"  [verify] Blocked on match page (status {status_code}).")
                            if backoff:
                                print(f"  Waiting {backoff}s before retry...")
                                import time; time.sleep(backoff)
                                continue
                            else:
                                break
                        break

                    tab_keywords = MARKET_TAB_KEYWORDS.get(market, [])
                    for kw in tab_keywords:
                        try:
                            tab = page.get_by_text(kw, exact=False).first
                            if tab and tab.is_visible():
                                tab.click(timeout=3000)
                                page.wait_for_timeout(2000)
                                print(f"  Clicked tab: '{kw}'")
                                break
                        except Exception:
                            continue

                    html = page.content()
                    save_html_snapshot(html, pid)
                    odds_data = extract_target_odds(html, market, selection)

                    if odds_data["target_odds"]:
                        r["verified_odds"] = odds_data["target_odds"]
                        r["passes_threshold"] = odds_data["target_odds"] >= threshold
                        r["status"] = "verified"
                        r["snippet"] = odds_data["raw_snippet"]
                        icon = "PASS" if r["passes_threshold"] else "FAIL"
                        print(f"  {icon}: {selection} = {odds_data['target_odds']} (min {threshold})")
                    else:
                        r["status"] = "page_found_no_odds"
                        print(f"  WARN: page found but odds not extracted")
                        if odds_data["all_odds"]:
                            top = sorted(set(odds_data["all_odds"]))[:12]
                            print(f"  Visible odds: {top}")
                else:
                    r["status"] = "not_found"
                    print(f"  NOT FOUND on Betclic")

            except Exception as e:
                r["status"] = "error: " + str(e)[:120]
                print(f"  ERROR: {e}")

            results.append(r)
            random_delay_sync(3, 6)

        try:
            ctx.storage_state(path=str(storage_file))
        except Exception:
            pass
        browser.close()

    out = DATA_DIR / "betclic_verified_odds.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 60)
    print("BETCLIC ODDS VERIFICATION SUMMARY")
    print("=" * 60)
    passed = 0
    failed = 0
    unknown = 0
    for r in results:
        odds_s = str(r["verified_odds"]) if r["verified_odds"] else "N/A"
        if r["passes_threshold"] is True:
            tag = "PASS"
            passed += 1
        elif r["passes_threshold"] is False:
            tag = "FAIL"
            failed += 1
        else:
            tag = "CHECK"
            unknown += 1
        sel_padded = r["selection"].ljust(20)
        print(f"  {r['pick_id']}: {sel_padded} @ {odds_s:>5s}  (min {r['threshold']})  {tag}")

    print(f"\nTotal: {passed} pass, {failed} fail, {unknown} need manual check")
    print(f"Saved to: {out}")
    return results


def main():
    parser = argparse.ArgumentParser(description="Verify Betclic odds for pending picks")
    parser.add_argument("--betting-day", default=datetime.now().strftime("%Y-%m-%d"),
                        help="Betting day to verify (default: today)")
    args = parser.parse_args()

    print(f"Verifying Betclic odds for betting day: {args.betting_day}")
    picks = load_pending_picks(args.betting_day)
    print(f"Found {len(picks)} pending pick(s) to verify")

    if not picks:
        print("Nothing to verify.")
        return

    verify_odds(picks)


if __name__ == "__main__":
    main()