#!/usr/bin/env python3
"""One-time Betclic login helper.

Opens a visible Playwright browser on betclic.pl/login so you can
log in manually.  Once you press Enter in the terminal, the session
cookies are saved to scripts/playwright_storage/betclic.pl.json.
All subsequent headless runs (verify_betclic_odds.py, fetch_with_playwright.py)
will reuse the saved session automatically.

Usage:
    python3 scripts/betclic_login.py          # open login page
    python3 scripts/betclic_login.py --check  # verify saved session is valid
"""
import sys
import argparse
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from betclic_helpers import USER_AGENTS, STORAGE_DIR

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright not available. Install: pip install playwright && playwright install chromium")
    sys.exit(1)

DOMAIN = "betclic.pl"


def do_login():
    """Open a headed browser so the user can log in manually."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    storage_file = STORAGE_DIR / f"{DOMAIN}.json"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx_kwargs = {
            "user_agent": USER_AGENTS[0],
            "viewport": {"width": 1280, "height": 900},
            "locale": "pl-PL",
        }
        if storage_file.exists():
            ctx_kwargs["storage_state"] = str(storage_file)

        ctx = browser.new_context(**ctx_kwargs)
        page = ctx.new_page()
        page.goto("https://www.betclic.pl/login", wait_until="domcontentloaded", timeout=30000)

        print()
        print("=" * 60)
        print("  Betclic login window is open.")
        print("  Log in manually, then press ENTER here to save session.")
        print("=" * 60)
        input()

        # Save session state
        ctx.storage_state(path=str(storage_file))
        print(f"Session saved to: {storage_file}")
        browser.close()


def check_session():
    """Verify a saved session is still valid by loading betclic.pl."""
    storage_file = STORAGE_DIR / f"{DOMAIN}.json"
    if not storage_file.exists():
        print(f"No saved session found at {storage_file}")
        print("Run: python3 scripts/betclic_login.py")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=USER_AGENTS[0],
            viewport={"width": 1920, "height": 1080},
            locale="pl-PL",
            storage_state=str(storage_file),
        )
        page = ctx.new_page()
        page.goto("https://www.betclic.pl/", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)

        html = page.content()
        logged_in = any(kw in html.lower() for kw in [
            "moje konto", "wyloguj", "my account", "logout", "saldo", "balance"
        ])

        if logged_in:
            print("Session is VALID - logged in to Betclic")
        else:
            print("Session EXPIRED or INVALID - please log in again")
            print("Run: python3 scripts/betclic_login.py")

        browser.close()
        return logged_in


def main():
    parser = argparse.ArgumentParser(description="Betclic login helper")
    parser.add_argument("--check", action="store_true", help="Check if saved session is valid")
    args = parser.parse_args()

    if args.check:
        check_session()
    else:
        do_login()


if __name__ == "__main__":
    main()