#!/usr/bin/env python3
"""
Monitor Real Madrid vs Alaves and settle resolvable picks when match finishes.

Usage: python3 scripts/settle_on_finish.py

Notes:
- This script attempts to poll Sofascore and Flashscore pages for final scores.
- If sites block automated requests, the script will log errors and continue retrying.
- It only auto-settles simple markets: match winner and totals UNDER/OVER 3.5 and simple MyCombi parts.
- Other markets (corners, cards, handicaps) are left as 'pending' for manual verification.
"""
import csv
import time
import re
import subprocess
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

LEDGER = 'betting/journal/picks-ledger.csv'
COUPONS = 'betting/journal/coupons-ledger.csv'
POLL_INTERVAL = 60  # seconds
TIMEOUT = 60 * 60 * 6  # 6 hours


def read_picks():
    picks = []
    with open(LEDGER, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            picks.append(r)
    return picks


def write_picks(picks):
    with open(LEDGER, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=picks[0].keys())
        writer.writeheader()
        writer.writerows(picks)


def fetch_sofascore_result(home, away):
    # Try a simple search by constructing a Sofascore search URL and looking for a finished score
    try:
        q = f"{home} {away}".replace(' ', '%20')
        url = f'https://www.sofascore.com/search?q={q}'
        r = requests.get(url, timeout=15, headers={'User-Agent':'settle-bot/1.0'})
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, 'html.parser')
        # Look for patterns like "2 : 1" or "2-1" near the team names
        text = soup.get_text(separator=' ')
        m = re.search(rf"{home}.*?(\d+)\s*[:\-]\s*(\d+).*?{away}", text, re.IGNORECASE|re.DOTALL)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception as e:
        log(f"sofascore fetch error: {e}")
    return None


def fetch_flashscore_result(home, away):
    try:
        q = f"{home} {away}".replace(' ', '%20')
        url = f'https://www.flashscore.com/search/?q={q}'
        r = requests.get(url, timeout=15, headers={'User-Agent':'settle-bot/1.0'})
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, 'html.parser')
        text = soup.get_text(separator=' ')
        m = re.search(rf"{home}.*?(\d+)\s*[:\-]\s*(\d+).*?{away}", text, re.IGNORECASE|re.DOTALL)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception as e:
        log(f"flashscore fetch error: {e}")
    return None


def log(msg):
    ts = datetime.now().isoformat()
    with open('settle_log.txt', 'a', encoding='utf-8') as f:
        f.write(f"{ts} {msg}\n")
    print(msg)


def settle_match(score_home, score_away, home_name, away_name, picks):
    # Update picks list in-place for resolved markets
    updated = False
    for p in picks:
        if p['status'] not in ('pending','placed'):
            continue
        if home_name in p['event'] and away_name in p['event']:
            market = p['market'].lower()
            sel = p['selection'].lower()
            # match winner markets
            if 'match winner' in market or '1x2' in market or 'wynik meczu' in market.lower():
                if score_home > score_away and 'home' in sel or score_home > score_away and home_name.lower() in sel:
                    p['status'] = 'win'
                    p['pnl_pln'] = str(round((float(p['bookmaker_odds']) - 1) * float(p.get('stake_pln','0') or 0),2))
                elif score_home == score_away:
                    p['status'] = 'push'
                    p['pnl_pln'] = '0.00'
                else:
                    p['status'] = 'loss'
                    p['pnl_pln'] = str(-float(p.get('stake_pln','0') or 0))
                updated = True
            # totals under/over 3.5
            elif 'totals' in market or 'under' in market or 'over' in market:
                goals = score_home + score_away
                if 'under' in market or 'under' in sel:
                    if goals <= 3:
                        p['status'] = 'win'
                        p['pnl_pln'] = str(round((float(p['bookmaker_odds']) - 1) * float(p.get('stake_pln','0') or 0),2))
                    else:
                        p['status'] = 'loss'
                        p['pnl_pln'] = str(-float(p.get('stake_pln','0') or 0))
                    updated = True
                elif 'over' in market or 'over' in sel:
                    if goals > 3:
                        p['status'] = 'win'
                        p['pnl_pln'] = str(round((float(p['bookmaker_odds']) - 1) * float(p.get('stake_pln','0') or 0),2))
                    else:
                        p['status'] = 'loss'
                        p['pnl_pln'] = str(-float(p.get('stake_pln','0') or 0))
                    updated = True
            # MyCombi / combo: try to resolve if it includes match winner or totals
            elif 'mycombi' in market or 'mycombi' in p.get('selection','').lower():
                # simplistic: if contains 'real' and 'over' resolve accordingly
                if 'real' in p['selection'].lower() and 'over' in p['selection'].lower():
                    goals = score_home + score_away
                    if score_home > score_away and goals > 1:
                        p['status'] = 'win'
                        p['pnl_pln'] = str(round((float(p['bookmaker_odds']) - 1) * float(p.get('stake_pln','0') or 0),2))
                    else:
                        p['status'] = 'loss'
                        p['pnl_pln'] = str(-float(p.get('stake_pln','0') or 0))
                    updated = True
            else:
                # Unable to auto-resolve market
                log(f"Unable to auto-resolve market {p['market']} for pick {p['pick_id']}")
    return updated


def git_commit_and_push(msg):
    try:
        subprocess.run(['git','add',LEDGER,COUPONS], check=True)
        subprocess.run(['git','commit','-m',msg], check=True)
        subprocess.run(['git','push','origin','HEAD'], check=True)
        log('Committed and pushed settlement updates')
    except subprocess.CalledProcessError as e:
        log(f'git error: {e}')


def main():
    home = 'Real Madrid'
    away = 'Alaves'
    start = time.time()
    log('Starting monitor for Real Madrid vs Alaves')
    while time.time() - start < TIMEOUT:
        # Try sofascore
        res = fetch_sofascore_result(home, away)
        if not res:
            res = fetch_flashscore_result(home, away)
        if res:
            home_score, away_score = res
            log(f'Found score: {home} {home_score} - {away_score} {away}')
            # Only act if match appears finished (no in-play marker). We assume presence of score implies finish for now.
            picks = read_picks()
            changed = settle_match(home_score, away_score, home, away, picks)
            if changed:
                write_picks(picks)
                git_commit_and_push(f'Settle Real vs Alaves: {home_score}-{away_score} automated')
            else:
                log('No picks auto-resolved; manual verification required for some markets')
            break
        else:
            log('Score not yet available; sleeping')
            time.sleep(POLL_INTERVAL)
    else:
        log('Timeout reached without finding final score')


if __name__ == '__main__':
    main()
