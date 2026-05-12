#!/usr/bin/env python3
"""Temporary script to test NaturalStatTrick rendering with various approaches."""
import sys


URL = "https://www.naturalstattrick.com/teamtable.php?fromseason=20242025&thession=20242025&stype=2&sit=5v5&score=all&rate=n&team=all&loc=B&gpf=410&fd=&td="
MONEYPUCK_URL = "https://moneypuck.com/data/2024/2025/teamstats.csv"


def test_cloudscraper():
    """Test cloudscraper which handles Cloudflare JS challenges."""
    import cloudscraper
    scraper = cloudscraper.create_scraper()
    
    print("Testing cloudscraper against NaturalStatTrick...")
    try:
        resp = scraper.get(URL, timeout=30)
        print(f"  Status: {resp.status_code}")
        print(f"  Size: {len(resp.text)} bytes")
        has_table = "<table" in resp.text.lower()
        has_cf = "Attention Required" in resp.text
        print(f"  Has <table>: {has_table}")
        print(f"  Has CF block: {has_cf}")
        
        if has_table and not has_cf:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            tables = soup.find_all("table")
            print(f"  Tables found: {len(tables)}")
            for i, t in enumerate(tables[:3]):
                rows = t.find_all("tr")
                print(f"    Table {i}: {len(rows)} rows, id={t.get('id', 'none')}")
            
            # Try parsing with our adapter
            sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
            from adapters.naturalstattrick_adapter import parse
            results = parse(resp.text, URL)
            print(f"  Adapter results: {len(results)} events")
            if results:
                r = results[0]
                print(f"    Sample: {r.get('home', '?')} — corsi: {r.get('stats', {}).get('corsi_pct', '?')}")
            return True
        else:
            # Show first 500 chars for diagnosis
            print(f"  Preview: {resp.text[:500]}")
            return False
    except Exception as e:
        print(f"  Error: {e}")
        return False


def test_moneypuck():
    """Test MoneyPuck CSV data (alternative source)."""
    import requests
    
    print("\nTesting MoneyPuck CSV (alternative data source)...")
    try:
        resp = requests.get(MONEYPUCK_URL, timeout=15,
                           headers={"User-Agent": "Mozilla/5.0"})
        print(f"  Status: {resp.status_code}")
        print(f"  Size: {len(resp.text)} bytes")
        
        if resp.status_code == 200 and len(resp.text) > 100:
            lines = resp.text.strip().split("\n")
            print(f"  Rows: {len(lines)}")
            if lines:
                print(f"  Headers: {lines[0][:200]}")
                if len(lines) > 1:
                    print(f"  Sample row: {lines[1][:200]}")
            return True
        return False
    except Exception as e:
        print(f"  Error: {e}")
        return False


def main():
    cs_ok = test_cloudscraper()
    mp_ok = test_moneypuck()
    
    print("\n--- RESULTS ---")
    print(f"cloudscraper + NST: {'✅ WORKS' if cs_ok else '❌ BLOCKED'}")
    print(f"MoneyPuck CSV:      {'✅ WORKS' if mp_ok else '❌ BLOCKED'}")


if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()
