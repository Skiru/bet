#!/usr/bin/env python3
"""Debug script to discover BetExplorer DOM structure.

Run: PYTHONPATH=src .venv/bin/python scripts/_debug_betexplorer.py
"""
import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime

SPORTS = ["football", "tennis", "basketball", "hockey", "volleyball"]

def fetch_page(sport, date="2026-05-13"):
    url = f"https://www.betexplorer.com/results/{sport}/?year={date[:4]}&month={date[5:7]}&day={date[8:10]}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.betexplorer.com/"
    }
    
    # We might need a date parameter to get specific date, e.g., today's matches
    # but let's just fetch the sport main page which lists upcoming matches
    
    print(f"Fetching {url}...")
    response = requests.get(url, headers=headers, timeout=15)
    
    if response.status_code != 200:
        print(f"Failed to fetch {url} (Status: {response.status_code})")
        return None
        
    return BeautifulSoup(response.text, "html.parser")

def analyze_dom(soup, sport):
    if not soup:
        return
        
    print(f"\n{'='*40}")
    print(f"Analyzing {sport}")
    print(f"{'='*40}")
    
    # Let's find tables
    tables = soup.find_all("table")
    print(f"Found {len(tables)} tables")
    
    # Tables with class 'table-main' are usually the match tables
    match_tables = soup.find_all("table", class_="table-main")
    print(f"Found {len(match_tables)} match lists (table-main)")
    
    if not match_tables:
        print("No match tables found. Exploring general structure...")
        print(f"Body classes: {soup.body.get('class', []) if soup.body else 'No body'}")
        
        # let's look for any links with match-like struct
        links = soup.find_all("a", href=True)
        match_links = [a for a in links if len(a['href'].split('/')) > 4 and "-" in a['href'][-10:]]
        print(f"Found {len(match_links)} potential match links")
        if match_links:
            print(f"Sample match link: {match_links[0]['href']} - {match_links[0].text.strip()}")
            
        return
        
    
    # Pick the first match table to analyze
    table = match_tables[0]
    
    # Let's count rows
    rows = table.find_all("tr")
    print(f"Analyzing first table: {len(rows)} rows")
    
    league_rows = table.find_all("th") 
    print(f"League header structure: {league_rows[0] if league_rows else 'None'}")
    
    # Find match rows - usually they don't have 'th'
    match_rows = [tr for tr in rows if not tr.find("th")]
    print(f"Found {len(match_rows)} data rows")
    
    if match_rows:
        row = match_rows[0]
        print("\n--- Sample Match Row HTML ---")
        print(row.prettify()[:1000] + "...")
        
        print("\n--- Extraction Test ---")
        # Extracting data from the row
        teams_cell = row.find("td", class_="table-main__tt")
        if teams_cell:
            a_tag = teams_cell.find("a")
            if a_tag:
                match_url = a_tag['href']
                match_name = a_tag.text.strip()
                if " - " in match_name:
                    home, away = match_name.split(" - ", 1)
                else:
                    home, away = match_name, "Unknown"
                
                print(f"URL: {match_url}")
                print(f"Teams: {home} vs {away}")
                
        time_cell = row.find("td", class_="table-main__time")
        if time_cell:
            print(f"Time: {time_cell.text.strip()}")
            
        odds_cells = row.find_all("td", class_="table-main__odds")
        odds = []
        for td in odds_cells:
            span = td.find("span")
            odds.append(span.text.strip() if span else td.text.strip())
        print(f"Odds: {odds}")

def main():
    for sport in SPORTS:
        soup = fetch_page(sport, "2026-05-13")
        analyze_dom(soup, sport)

if __name__ == "__main__":
    main()
