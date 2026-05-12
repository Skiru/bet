"""Minimal Playwright helpers for Betclic-specific scripts.

Extracted from the deleted fetch_with_playwright.py during Beast Mode migration.
Only contains constants and utilities needed by betclic_login.py, 
fetch_betclic_bets.py, and verify_betclic_odds.py.
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
SELECTORS_PATH = BASE / "site_selectors.json"
STORAGE_DIR = BASE / "playwright_storage"

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]


def load_selectors() -> dict:
    """Load CSS selectors for cookie/consent handling from site_selectors.json."""
    try:
        with open(SELECTORS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"default": []}
