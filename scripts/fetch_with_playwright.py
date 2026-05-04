#!/usr/bin/env python3
"""Playwright-based fetcher with cookie handling and persistent storage state.

This fetcher auto-clicks common cookie/consent selectors (configured in
`site_selectors.json`), removes overlay elements, persists `storage_state`
per-domain under `scripts/playwright_storage/` and saves HTML snapshots to
`betting/data/<domain>/TIMESTAMP.html` for debugging.

Usage: import `fetch(url)` or run as a script: `python scripts/fetch_with_playwright.py <url>`
"""
import sys
import json
import time
import random
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent
SELECTORS_PATH = BASE / "site_selectors.json"
STORAGE_DIR = BASE / "playwright_storage"
DATA_DIR = BASE.parent / "betting" / "data"
ROOT_DIR = BASE.parent
PROXY_FILE = ROOT_DIR / "config" / "proxies.txt"


def _load_proxies() -> list[str]:
    if not PROXY_FILE.exists():
        return []
    return [line.strip() for line in PROXY_FILE.read_text().splitlines() if line.strip() and not line.startswith("#")]


_proxies = _load_proxies()
_proxy_idx = 0


def _get_next_proxy() -> str | None:
    global _proxy_idx
    if not _proxies:
        return None
    proxy = _proxies[_proxy_idx % len(_proxies)]
    _proxy_idx += 1
    return proxy


CAPTCHA_INDICATORS = [
    "cf-challenge",
    "captcha",
    "recaptcha",
    "hcaptcha",
    "ray id",
    "access denied",
    "please verify",
    "checking your browser",
    "just a moment",
]


def _is_captcha_page(html: str) -> bool:
    """Detect if a page is a CAPTCHA/challenge page."""
    lower = html.lower()
    if len(html) < 5000:
        for indicator in CAPTCHA_INDICATORS:
            if indicator in lower:
                return True
    return False

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None


def load_selectors():
    try:
        with open(SELECTORS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"default": []}


def domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.replace("www.", "")


USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]


def _save_html(domain: str, html: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    d = DATA_DIR / domain
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{ts}.html"
    p.write_text(html, encoding="utf-8")
    return p


def fetch(url: str, headless: bool = True, timeout: int = 30, retries: int = 2, save_snapshot: bool = True) -> str:
    """Fetch a page using Playwright and return HTML content.

    Raises ImportError if Playwright is not installed.
    """
    selectors_map = load_selectors()
    domain = domain_from_url(url)
    selectors = selectors_map.get(domain, []) + selectors_map.get("default", [])
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    storage_file = STORAGE_DIR / f"{domain}.json"

    if sync_playwright is None:
        raise ImportError("playwright.sync_api not available. Install 'playwright' and run 'playwright install chromium'.")

    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            with sync_playwright() as p:
                proxy = _get_next_proxy()
                launch_kwargs = {"headless": headless}
                if proxy:
                    launch_kwargs["proxy"] = {"server": proxy}
                browser = p.chromium.launch(**launch_kwargs)

                context_kwargs = {
                    "user_agent": random.choice(USER_AGENTS),
                    "viewport": {"width": 1920, "height": 1080},
                    "locale": "pl-PL",
                }
                if storage_file.exists():
                    context_kwargs["storage_state"] = str(storage_file)

                ctx = browser.new_context(**context_kwargs)
                page = ctx.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
                except Exception:
                    page.goto(url, wait_until="load", timeout=int(timeout * 1000))

                # try to click known cookie/consent selectors
                for sel in selectors:
                    try:
                        el = page.query_selector(sel)
                        if el:
                            try:
                                el.click(timeout=3000)
                            except Exception:
                                pass
                            try:
                                page.wait_for_timeout(600)
                            except Exception:
                                pass
                    except Exception:
                        continue

                # remove common overlays as a last resort
                try:
                    page.evaluate("() => { const s = document.querySelectorAll('[role=dialog], .cookie, .cc-banner, .cookie-consent, #cookie-banner, .consent-banner, .overlay, .modal'); for (const e of s) e.remove(); }")
                except Exception:
                    pass

                try:
                    page.wait_for_timeout(1200)
                except Exception:
                    pass

                content = page.content()

                # CAPTCHA / challenge detection
                if _is_captcha_page(content):
                    print(f"  ⚠ CAPTCHA detected on {url} (attempt {attempt})", file=sys.stderr)
                    browser.close()
                    if _proxies and attempt < retries:
                        time.sleep(1)
                        continue
                    return None

                if save_snapshot:
                    _save_html(domain, content)

                # persist storage state to avoid repeated prompts
                try:
                    ctx.storage_state(path=str(storage_file))
                except Exception:
                    pass

                browser.close()
                return content

        except Exception as e:
            last_exc = e
            print(f"[fetch_with_playwright] attempt {attempt} failed: {e}", file=sys.stderr)
            time.sleep(1)
            continue

    raise RuntimeError(f"All attempts to fetch {url} failed: {last_exc}")


def main():
    if len(sys.argv) < 2:
        print("Usage: fetch_with_playwright.py <url>")
        sys.exit(2)
    url = sys.argv[1]
    html = fetch(url)
    print(f"Fetched {url} — length {len(html)} chars")


if __name__ == "__main__":
    main()
