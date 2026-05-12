#!/usr/bin/env python3
"""Diagnose Soccerway HTML structure for adapter development."""
import sys
import os
import re
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

def main():
    url = "https://int.soccerway.com/matches/2026/05/12/"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    print(f"Status: {resp.status_code}, Size: {len(resp.text)} bytes")
    
    soup = BeautifulSoup(resp.text, "html.parser")
    
    # 1. Find all tables and their classes
    tables = soup.find_all("table")
    print(f"\nTables found: {len(tables)}")
    for i, t in enumerate(tables[:10]):
        cls = t.get("class", [])
        tid = t.get("id", "")
        rows = len(t.find_all("tr"))
        print(f"  Table {i}: class={cls} id={tid} rows={rows}")
    
    # 2. Look for common Soccerway class patterns
    for cls_name in ["team-a", "team-b", "score-time", "matches", "match", 
                      "match-main", "result", "event", "game", "fixture"]:
        found = soup.find_all(class_=re.compile(cls_name, re.I))
        if found:
            print(f"\n  class~'{cls_name}': {len(found)} elements, tag={found[0].name}")
            if len(found) > 0:
                sample = found[0].get_text(strip=True)[:80]
                print(f"    Sample text: {sample}")
    
    # 3. Find rows that look like match rows (have 2+ team-name-like links)
    match_rows = 0
    for tr in soup.find_all("tr"):
        links = tr.find_all("a")
        names = [a.get_text(strip=True) for a in links if len(a.get_text(strip=True)) > 2]
        if len(names) >= 2:
            match_rows += 1
            if match_rows <= 3:
                print(f"\n  Match-like row: {names[:4]}")
                # Show row classes
                print(f"    Row class: {tr.get('class', [])}")
                # Show cells
                tds = tr.find_all("td")
                for j, td in enumerate(tds[:6]):
                    cls = td.get("class", [])
                    text = td.get_text(strip=True)[:40]
                    print(f"    td[{j}] class={cls} text='{text}'")
    print(f"\n  Total match-like rows: {match_rows}")
    
    # 4. Find all links with /matches/ in href
    match_links = [a["href"] for a in soup.find_all("a", href=True) 
                   if "/matches/" in a["href"]]
    print(f"\n  Links with /matches/: {len(match_links)}")
    if match_links:
        for ml in match_links[:5]:
            print(f"    {ml}")
    
    # 5. Look for competition/league headers
    headers = soup.find_all(class_=re.compile(r"group|comp|league|tournament|section", re.I))
    print(f"\n  Competition headers: {len(headers)}")
    for h in headers[:5]:
        print(f"    {h.name} class={h.get('class',[])} text={h.get_text(strip=True)[:60]}")


if __name__ == "__main__":
    main()
