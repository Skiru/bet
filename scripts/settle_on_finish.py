#!/usr/bin/env python3
"""
Generic settlement script for pending picks and coupons.

Usage:
  python3 scripts/settle_on_finish.py                          # settle all pending
  python3 scripts/settle_on_finish.py --match "Team A vs Team B"  # settle specific match
  python3 scripts/settle_on_finish.py --betting-day 2026-04-21    # settle specific day

Notes:
- Polls Sofascore and Flashscore for final scores.
- Auto-settles: match winner/1X2, totals (any line), BTTS, double chance.
- Other markets (corners, cards, handicaps, MyCombi) are left as 'pending' for manual verification.
- Does NOT auto-push to git. Run git commands manually after verification.
"""
import csv
import json
import sys
import time
import re
import argparse
from datetime import datetime
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing dependencies. Run: pip install requests beautifulsoup4")
    sys.exit(1)

BASE = Path(__file__).resolve().parent
LEDGER = BASE.parent / "betting" / "journal" / "picks-ledger.csv"
COUPONS_LEDGER = BASE.parent / "betting" / "journal" / "coupons-ledger.csv"
LOG_FILE = BASE.parent / "settle_log.txt"
ODDS_API_SNAPSHOT = BASE.parent / "betting" / "data" / "odds_api_snapshot.json"
POLL_INTERVAL = 120  # seconds
MAX_POLLS = 60  # max number of poll attempts
REQUEST_HEADERS = {"User-Agent": "settle-bot/2.0 (educational project)"}


def log(msg):
    ts = datetime.now().isoformat()
    line = f"{ts} {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_csv(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows


def write_csv(path, rows):
    if not rows:
        return
    # Collect all fieldnames across all rows to avoid dropping keys
    all_fields = dict.fromkeys(rows[0].keys())  # preserve first row order
    for row in rows[1:]:
        for k in row:
            if k not in all_fields:
                all_fields[k] = None
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_fields.keys()), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def fetch_result_from_source(home, away, source_fn):
    """Try to find a final score for the given match."""
    try:
        return source_fn(home, away)
    except Exception as e:
        log(f"  Source error: {e}")
        return None


def search_odds_api_snapshot(home, away):
    """Search the Odds API snapshot for completed scores (free, no network call)."""
    if not ODDS_API_SNAPSHOT.exists():
        return None
    try:
        snapshot = json.loads(ODDS_API_SNAPSHOT.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    home_lower = home.lower()
    away_lower = away.lower()
    for event in snapshot.get("events", []):
        eh = (event.get("home_team") or "").lower()
        ea = (event.get("away_team") or "").lower()
        if not ((home_lower in eh or eh in home_lower) and (away_lower in ea or ea in away_lower)):
            # Try reversed order
            if not ((home_lower in ea or ea in home_lower) and (away_lower in eh or eh in away_lower)):
                continue
        if not event.get("completed"):
            continue
        scores = event.get("scores")
        if not scores or len(scores) < 2:
            continue
        # scores is [{"name": "Team", "score": "3"}, ...]
        score_map = {s["name"].lower(): int(s["score"]) for s in scores if s.get("score") and s["score"].isdigit()}
        if eh in score_map and ea in score_map:
            # Return in home/away order as requested
            if home_lower in eh or eh in home_lower:
                return score_map[eh], score_map[ea]
            else:
                return score_map[ea], score_map[eh]
    return None


def search_sofascore(home, away):
    q = f"{home} {away}".replace(" ", "%20")
    url = f"https://www.sofascore.com/search?q={q}"
    r = requests.get(url, timeout=15, headers=REQUEST_HEADERS)
    if r.status_code != 200:
        return None
    text = BeautifulSoup(r.text, "html.parser").get_text(separator=" ")
    # Pattern 1: Home ... score ... Away (correct order)
    m = re.search(
        rf"{re.escape(home)}.*?(\d+)\s*[:\-]\s*(\d+).*?{re.escape(away)}",
        text, re.IGNORECASE | re.DOTALL,
    )
    if m:
        return int(m.group(1)), int(m.group(2))
    # Pattern 2: Away ... score ... Home (reversed — swap scores)
    m = re.search(
        rf"{re.escape(away)}.*?(\d+)\s*[:\-]\s*(\d+).*?{re.escape(home)}",
        text, re.IGNORECASE | re.DOTALL,
    )
    if m:
        return int(m.group(2)), int(m.group(1))  # swap: away_score, home_score
    return None


def search_flashscore(home, away):
    q = f"{home} {away}".replace(" ", "%20")
    url = f"https://www.flashscore.com/search/?q={q}"
    r = requests.get(url, timeout=15, headers=REQUEST_HEADERS)
    if r.status_code != 200:
        return None
    text = BeautifulSoup(r.text, "html.parser").get_text(separator=" ")
    # Pattern 1: Home ... score ... Away (correct order)
    m = re.search(
        rf"{re.escape(home)}.*?(\d+)\s*[:\-]\s*(\d+).*?{re.escape(away)}",
        text, re.IGNORECASE | re.DOTALL,
    )
    if m:
        return int(m.group(1)), int(m.group(2))
    # Pattern 2: Away ... score ... Home (reversed — swap scores)
    m = re.search(
        rf"{re.escape(away)}.*?(\d+)\s*[:\-]\s*(\d+).*?{re.escape(home)}",
        text, re.IGNORECASE | re.DOTALL,
    )
    if m:
        return int(m.group(2)), int(m.group(1))  # swap: away_score, home_score
    return None


def compute_pnl(status, odds_str, stake_str):
    """Compute PnL based on status."""
    try:
        odds = float(odds_str)
        stake = float(stake_str or "0")
    except (ValueError, TypeError):
        return ""
    if status == "win":
        return str(round(stake * (odds - 1), 2))
    elif status == "loss":
        return str(round(-stake, 2))
    elif status == "half_win":
        return str(round(stake * (odds - 1) / 2, 2))
    elif status == "half_loss":
        return str(round(-stake / 2, 2))
    elif status in ("push", "void"):
        return "0.00"
    return ""


def parse_totals_line(market, selection):
    """Extract the totals threshold from market/selection text. E.g., 'UNDER 3.5' -> ('under', 3.5)"""
    combined = f"{market} {selection}".lower()
    m = re.search(r"(under|over)\s+(\d+\.?\d*)", combined)
    if m:
        return m.group(1), float(m.group(2))
    return None, None


def settle_pick(pick, score_home, score_away, home_name, away_name):
    """Try to settle a single pick given the final score. Returns True if settled."""
    market = (pick.get("market") or "").lower()
    sel = (pick.get("selection") or "").lower()

    # Match winner / 1X2
    if any(kw in market for kw in ("match winner", "1x2", "wynik meczu", "moneyline")):
        if score_home > score_away:
            winner = "home"
        elif score_away > score_home:
            winner = "away"
        else:
            winner = "draw"

        if winner == "draw":
            if "draw" in sel or "remis" in sel or "x" == sel.strip():
                pick["status"] = "win"
            else:
                pick["status"] = "loss"
        elif winner == "home" and (home_name.lower() in sel or "home" in sel or "1" == sel.strip()):
            pick["status"] = "win"
        elif winner == "away" and (away_name.lower() in sel or "away" in sel or "2" == sel.strip()):
            pick["status"] = "win"
        else:
            pick["status"] = "loss"

        pick["pnl_pln"] = compute_pnl(pick["status"], pick.get("bookmaker_odds"), pick.get("stake_pln"))
        return True

    # Totals (any line)
    direction, line = parse_totals_line(market, sel)
    if direction and line is not None:
        total_goals = score_home + score_away
        if direction == "under":
            if total_goals < line:
                pick["status"] = "win"
            elif total_goals == line:
                pick["status"] = "push"
            else:
                pick["status"] = "loss"
        else:  # over
            if total_goals > line:
                pick["status"] = "win"
            elif total_goals == line:
                pick["status"] = "push"
            else:
                pick["status"] = "loss"

        pick["pnl_pln"] = compute_pnl(pick["status"], pick.get("bookmaker_odds"), pick.get("stake_pln"))
        return True

    # BTTS
    if "btts" in market or "both teams" in market or "obie drużyny" in market:
        both_scored = score_home > 0 and score_away > 0
        if ("yes" in sel or "tak" in sel) and both_scored:
            pick["status"] = "win"
        elif ("no" in sel or "nie" in sel) and not both_scored:
            pick["status"] = "win"
        else:
            pick["status"] = "loss"

        pick["pnl_pln"] = compute_pnl(pick["status"], pick.get("bookmaker_odds"), pick.get("stake_pln"))
        return True

    # Double chance
    if "double chance" in market or "podwójna szansa" in market:
        if score_home > score_away:
            result = "1"
        elif score_away > score_home:
            result = "2"
        else:
            result = "x"

        win = False
        if ("1x" in sel or "1 x" in sel) and result in ("1", "x"):
            win = True
        elif ("x2" in sel or "x 2" in sel) and result in ("x", "2"):
            win = True
        elif ("12" in sel or "1 2" in sel) and result in ("1", "2"):
            win = True
        # Also handle text like "home or draw", "remis lub away"
        if "remis" in sel or "draw" in sel:
            if home_name.lower() in sel and result in ("1", "x"):
                win = True
            elif away_name.lower() in sel and result in ("x", "2"):
                win = True

        pick["status"] = "win" if win else "loss"
        pick["pnl_pln"] = compute_pnl(pick["status"], pick.get("bookmaker_odds"), pick.get("stake_pln"))
        return True

    # Cannot auto-settle this market
    log(f"  Cannot auto-settle market '{pick.get('market')}' for pick {pick.get('pick_id')}")
    return False


def settle_coupons(picks, coupons):
    """Update coupon statuses based on settled pick statuses."""
    pick_map = {p["pick_id"]: p for p in picks}
    updated = False
    for coupon in coupons:
        if coupon.get("status") not in ("pending", "placed"):
            continue
        pick_ids = (coupon.get("pick_ids") or "").split("|")
        statuses = []
        for pid in pick_ids:
            pid = pid.strip()
            if pid in pick_map:
                statuses.append(pick_map[pid].get("status", "pending"))
            else:
                statuses.append("pending")

        if "pending" in statuses or "placed" in statuses:
            continue  # Not all legs settled yet

        if "loss" in statuses:
            coupon["status"] = "loss"
            coupon["pnl_pln"] = str(round(-float(coupon.get("stake_pln") or 0), 2))
            updated = True
        elif all(s in ("win", "push", "void") for s in statuses):
            # Recalculate effective odds from non-void/push legs
            effective_odds = 1.0
            active_legs = 0
            for pid in pick_ids:
                pid = pid.strip()
                if pid in pick_map:
                    p = pick_map[pid]
                    if p.get("status") == "win":
                        try:
                            effective_odds *= float(p.get("bookmaker_odds", 1))
                            active_legs += 1
                        except (ValueError, TypeError):
                            pass
            stake = float(coupon.get("stake_pln") or 0)
            if active_legs > 0:
                coupon["status"] = "win"
                coupon["pnl_pln"] = str(round(stake * (effective_odds - 1), 2))
            else:
                coupon["status"] = "void"
                coupon["pnl_pln"] = "0.00"
            updated = True

    return updated


def extract_teams(event_str):
    """Extract home and away team names from event string."""
    for sep in [" vs ", " - ", " – ", " — "]:
        if sep in event_str:
            parts = event_str.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    return event_str.strip(), ""


def main():
    parser = argparse.ArgumentParser(description="Settle pending picks and coupons")
    parser.add_argument("--match", type=str, help="Settle only picks for this match (substring match)")
    parser.add_argument("--betting-day", type=str, help="Settle only picks for this betting day (YYYY-MM-DD)")
    parser.add_argument("--no-poll", action="store_true", help="Try once, don't poll repeatedly")
    args = parser.parse_args()

    if not LEDGER.exists():
        log(f"Ledger not found: {LEDGER}")
        sys.exit(1)

    picks = read_csv(LEDGER)
    coupons = read_csv(COUPONS_LEDGER) if COUPONS_LEDGER.exists() else []

    # Find pending picks that need settlement
    pending = []
    for p in picks:
        if p.get("status") not in ("pending", "placed"):
            continue
        if args.betting_day and p.get("betting_day") != args.betting_day:
            continue
        if args.match and args.match.lower() not in (p.get("event") or "").lower():
            continue
        pending.append(p)

    if not pending:
        log("No pending picks to settle.")
        return

    log(f"Found {len(pending)} pending pick(s) to settle")

    # Group by event
    events = {}
    for p in pending:
        event = p.get("event", "")
        if event not in events:
            events[event] = extract_teams(event)

    polls = 0
    max_polls = 1 if args.no_poll else MAX_POLLS

    while polls < max_polls:
        polls += 1
        any_settled = False

        for event, (home, away) in list(events.items()):
            if not home or not away:
                continue

            # Check if all picks for this event are already settled
            event_picks = [p for p in pending if p.get("event") == event and p.get("status") in ("pending", "placed")]
            if not event_picks:
                continue

            log(f"[Poll {polls}] Looking for result: {home} vs {away}")
            # Try Odds API snapshot first (free, offline)
            result = fetch_result_from_source(home, away, search_odds_api_snapshot)
            if not result:
                result = fetch_result_from_source(home, away, search_sofascore)
            if not result:
                result = fetch_result_from_source(home, away, search_flashscore)

            if result:
                score_home, score_away = result
                log(f"  Found score: {home} {score_home} - {score_away} {away}")
                for p in event_picks:
                    if settle_pick(p, score_home, score_away, home, away):
                        log(f"  Settled {p['pick_id']}: {p['status']} (PnL: {p.get('pnl_pln', 'N/A')})")
                        any_settled = True
            else:
                log(f"  Score not yet available for {event}")

        # Check if all pending are now settled
        still_pending = [p for p in pending if p.get("status") in ("pending", "placed")]
        if not still_pending:
            log("All pending picks settled!")
            break

        if polls < max_polls and not args.no_poll:
            log(f"  {len(still_pending)} pick(s) still pending. Sleeping {POLL_INTERVAL}s...")
            time.sleep(POLL_INTERVAL)

    # Settle coupons based on updated pick statuses
    if coupons:
        settle_coupons(picks, coupons)

    # Write updated ledgers
    write_csv(LEDGER, picks)
    log(f"Updated picks ledger: {LEDGER}")

    if coupons:
        write_csv(COUPONS_LEDGER, coupons)
        log(f"Updated coupons ledger: {COUPONS_LEDGER}")

    # Summary
    settled = [p for p in pending if p.get("status") not in ("pending", "placed")]
    still_pending = [p for p in pending if p.get("status") in ("pending", "placed")]
    log(f"Settlement complete: {len(settled)} settled, {len(still_pending)} still pending")


if __name__ == "__main__":
    main()
