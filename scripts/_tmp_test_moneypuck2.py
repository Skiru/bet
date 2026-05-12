#!/usr/bin/env python3
"""Explore MoneyPuck CSV structure and test current season."""
import csv
import io
import requests

BASE = "https://moneypuck.com/moneypuck/playerData/seasonSummary"
headers = {"User-Agent": "Mozilla/5.0"}

for season in ["2025", "2024"]:
    for stype in ["regular", "playoffs"]:
        url = f"{BASE}/{season}/{stype}/teams.csv"
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200 and len(r.text) > 200:
                reader = csv.DictReader(io.StringIO(r.text))
                rows = list(reader)
                teams = set(row.get("name", "") for row in rows if row.get("situation") == "all")
                print(f"✅ {season}/{stype}: {len(rows)} rows, {len(teams)} teams (all situation)")
                print(f"   Columns: {', '.join(list(reader.fieldnames)[:15])}...")
                if rows:
                    sample = next(r for r in rows if r.get("situation") == "all")
                    print(f"   Sample: {sample.get('name', '?')} — xG%={sample.get('xGoalsPercentage', '?')}, "
                          f"Corsi%={sample.get('corsiPercentage', '?')}, Fenwick%={sample.get('fenwickPercentage', '?')}, "
                          f"GP={sample.get('games_played', '?')}")
                    # Show all numeric columns
                    numeric_cols = [k for k, v in sample.items() if k != "name" and k != "team" and k != "position" and k != "situation"]
                    print(f"   All stat columns ({len(numeric_cols)}): {', '.join(numeric_cols[:20])}...")
            else:
                print(f"❌ {season}/{stype}: {r.status_code}")
        except Exception as e:
            print(f"❌ {season}/{stype}: {e}")
