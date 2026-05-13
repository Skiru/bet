#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from bet.api_clients.sofascore import SofascoreClient
from data_enrichment_agent import fetch, _fetch_stealth

def test_stealth_playwright():
    print("Testing stealth playwright direct fetch on Sofascore HTML...")
    html = fetch("https://www.sofascore.com", save_snapshot=False)
    if html and len(html) > 100:
        print(f"Success! HTML length: {len(html)}")
    else:
        print("Failed to fetch HTML.")

    print("\nTesting SofascoreClient stealth fallback...")
    client = SofascoreClient()
    try:
        # Intentionally force playwright fallback by mocking a 403 request or similar, 
        # or we just try to fetch a known URL that often blocks (like Sofascore JSON endpoint directly)
        stats = client.get_fixture_stats("123456") # might return empty if not found, but won't crash
        print("Completed get_fixture_stats gracefully")
    except Exception as e:
        print(f"Failed SofascoreClient: {e}")

if __name__ == "__main__":
    test_stealth_playwright()
