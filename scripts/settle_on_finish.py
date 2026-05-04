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
ODDS_API_SCORES = BASE.parent / "betting" / "data" / "odds_api_scores.json"
DATA_DIR = BASE.parent / "betting" / "data"
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
    for snapshot_path in [ODDS_API_SCORES, ODDS_API_SNAPSHOT]:
        if not snapshot_path.exists():
            continue
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        home_lower = home.lower()
        away_lower = away.lower()
        events = snapshot.get("events", [])
        if isinstance(snapshot, list):
            events = snapshot
        for event in events:
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


def search_cached_html(home, away):
    """Search locally cached HTML files from Playwright scans for final scores.

    Only checks files from the last 48h and applies strict proximity + score
    validation to avoid matching random numbers from fixture lists.
    """
    import time as _time

    home_lower = home.lower()
    away_lower = away.lower()
    now_ts = _time.time()
    cutoff_ts = now_ts - 48 * 3600  # only files from last 48h

    for site_dir_name in ["flashscore.com", "sofascore.com"]:
        site_dir = DATA_DIR / site_dir_name
        if not site_dir.is_dir():
            continue
        for html_file in sorted(site_dir.glob("*.html"), reverse=True):
            # Skip old files
            if html_file.stat().st_mtime < cutoff_ts:
                continue
            try:
                text = html_file.read_text(encoding="utf-8", errors="ignore")
                text_lower = text.lower()
                if home_lower not in text_lower or away_lower not in text_lower:
                    continue
                soup = BeautifulSoup(text, "html.parser")
                page_text = soup.get_text(separator=" ")
                # Strict proximity: teams + score must be within 80 chars
                for h, a, swap in [(home, away, False), (away, home, True)]:
                    m = re.search(
                        rf"{re.escape(h)}\s+(\d{{1,3}})\s*[:\-–—]\s*(\d{{1,3}})\s+{re.escape(a)}",
                        page_text, re.IGNORECASE,
                    )
                    if m:
                        s1, s2 = int(m.group(1)), int(m.group(2))
                        if _validate_score(s1, s2):
                            return (s2, s1) if swap else (s1, s2)
            except Exception:
                continue
    return None


def _validate_score(s1, s2, max_total=30):
    """Reject clearly impossible scores (e.g., 0-18 for football)."""
    if s1 + s2 > max_total:
        return False
    if s1 > 20 or s2 > 20:
        return False
    return True


def search_flashscore_playwright(home, away):
    """Use Playwright to fetch live results from Flashscore search."""
    # Delegate to the batch fetcher — results are cached after first call
    return _flashscore_batch_cache.get(home, away)


class _FlashscoreBatchFetcher:
    """Fetches all recent results from Flashscore in one Playwright session,
    then serves individual lookups from the cache."""

    def __init__(self):
        self._cache = {}  # normalized team pair → (home_score, away_score)
        self._fetched = False

    def get(self, home, away):
        if not self._fetched:
            self._fetch_all()
        home_lower = home.lower().strip()
        away_lower = away.lower().strip()

        # Extract key words for fuzzy matching (handles abbreviations, suffixes)
        home_words = set(self._normalize(home_lower))
        away_words = set(self._normalize(away_lower))

        for (h, a), score in self._cache.items():
            h_words = set(self._normalize(h))
            a_words = set(self._normalize(a))

            # Try both orderings: (home→h, away→a) and (home→a, away→h)
            if self._fuzzy_match(home_words, h_words) and self._fuzzy_match(away_words, a_words):
                return score
            if self._fuzzy_match(home_words, a_words) and self._fuzzy_match(away_words, h_words):
                return score[1], score[0]  # swap scores
        return None

    @staticmethod
    def _normalize(name):
        """Extract significant words from a team/player name for fuzzy matching."""
        # Remove common suffixes and abbreviations
        name = re.sub(r'\b(fc|sc|cf|utd|united|city|w\.|l\.|j\.|a\.|c\.|e\.|f\.|h\.|n\.|r\.|m\.|s\.|k\.)\b', '', name)
        # Split into words, filter short ones
        words = [w for w in re.split(r'[\s\.\-]+', name) if len(w) >= 2]
        return words

    @staticmethod
    def _fuzzy_match(query_words, cached_words):
        """Check if query words match cached words (partial matching)."""
        if not query_words or not cached_words:
            return False
        # At least one significant query word must appear (substring) in cached words
        matched = 0
        for qw in query_words:
            for cw in cached_words:
                if qw in cw or cw in qw:
                    matched += 1
                    break
        # Require at least half of query words to match, and at least 1
        return matched >= max(1, len(query_words) * 0.4)

    def _fetch_all(self):
        self._fetched = True
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return

        from datetime import datetime, timedelta

        # Build yesterday's date for Flashscore URL date parameter
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        # Fetch results pages — both today (for overnight games) and yesterday
        sport_slugs = ["football", "tennis", "basketball", "hockey",
                       "baseball", "volleyball", "snooker", "handball"]

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                )

                for sport in sport_slugs:
                    for date_label, url in [
                        ("today", f"https://www.flashscore.com/{sport}/"),
                        ("yesterday", f"https://www.flashscore.com/{sport}/"),
                    ]:
                        try:
                            if date_label == "today":
                                page.goto(url, timeout=15000, wait_until="domcontentloaded")
                                page.wait_for_timeout(3000)

                            # Click FINISHED tab to filter results
                            try:
                                page.click("text=FINISHED", timeout=3000)
                                page.wait_for_timeout(2000)
                            except Exception:
                                pass

                            # For yesterday, click the left arrow button
                            if date_label == "yesterday":
                                try:
                                    page.click(".action-navigation-arrow-left", timeout=3000)
                                    page.wait_for_timeout(3000)
                                except Exception:
                                    continue  # skip if can't navigate

                            text = page.inner_text("body")
                            before = len(self._cache)
                            self._parse_scores(text)
                            added = len(self._cache) - before
                            if added > 0:
                                log(f"  Flashscore {sport}/{date_label}: +{added} results")
                        except Exception as e:
                            log(f"  Flashscore batch error {sport}/{date_label}: {e}")
                            continue

                browser.close()
        except Exception as e:
            log(f"  Flashscore batch fetcher error: {e}")

        log(f"  Flashscore batch: cached {len(self._cache)} match results total")

    def _parse_scores(self, text):
        """Parse finished match scores from Flashscore page text.

        Flashscore format (each on separate line):
            Finished
            HomeTeam
            AwayTeam
            home_score
            away_score
        """
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        i = 0
        while i < len(lines) - 4:
            if lines[i] == "Finished":
                home_team = lines[i + 1]
                away_team = lines[i + 2]
                s1_str = lines[i + 3]
                s2_str = lines[i + 4]
                if s1_str.isdigit() and s2_str.isdigit() and len(home_team) > 1 and len(away_team) > 1:
                    s1, s2 = int(s1_str), int(s2_str)
                    if _validate_score(s1, s2):
                        self._cache[(home_team.lower(), away_team.lower())] = (s1, s2)
                i += 5  # skip past this match block
            else:
                i += 1


_flashscore_batch_cache = _FlashscoreBatchFetcher()


def search_sofascore(home, away):
    q = f"{home} {away}".replace(" ", "%20")
    url = f"https://www.sofascore.com/search?q={q}"
    r = requests.get(url, timeout=15, headers=REQUEST_HEADERS)
    if r.status_code != 200:
        return None
    text = BeautifulSoup(r.text, "html.parser").get_text(separator=" ")
    for h, a, swap in [(home, away, False), (away, home, True)]:
        m = re.search(
            rf"{re.escape(h)}\s+(\d{{1,3}})\s*[:\-–—]\s*(\d{{1,3}})\s+{re.escape(a)}",
            text, re.IGNORECASE,
        )
        if m:
            s1, s2 = int(m.group(1)), int(m.group(2))
            if _validate_score(s1, s2):
                return (s2, s1) if swap else (s1, s2)
    return None


def search_flashscore(home, away):
    q = f"{home} {away}".replace(" ", "%20")
    url = f"https://www.flashscore.com/search/?q={q}"
    r = requests.get(url, timeout=15, headers=REQUEST_HEADERS)
    if r.status_code != 200:
        return None
    text = BeautifulSoup(r.text, "html.parser").get_text(separator=" ")
    for h, a, swap in [(home, away, False), (away, home, True)]:
        m = re.search(
            rf"{re.escape(h)}\s+(\d{{1,3}})\s*[:\-–—]\s*(\d{{1,3}})\s+{re.escape(a)}",
            text, re.IGNORECASE,
        )
        if m:
            s1, s2 = int(m.group(1)), int(m.group(2))
            if _validate_score(s1, s2):
                return (s2, s1) if swap else (s1, s2)
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

    # Totals (goals/points/game totals only — NOT corners, cards, fouls, shots)
    # Markets like corners, cards, fouls need special stat data and must be settled manually.
    MANUAL_STAT_MARKETS = ("corner", "card", "foul", "shot", "booking", "yellow", "red",
                           "throw-in", "offside", "free kick")
    is_stat_market = any(kw in market for kw in MANUAL_STAT_MARKETS)
    direction, line = parse_totals_line(market, sel)
    if direction and line is not None and not is_stat_market:
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
        log(f"Ledger not found: {LEDGER} — nothing to settle (first run?)")
        return

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
            # Try local sources first (free, no network)
            result = fetch_result_from_source(home, away, search_odds_api_snapshot)
            if not result:
                result = fetch_result_from_source(home, away, search_cached_html)
            # Network fallbacks (Sofascore/Flashscore use JS — requests often fails)
            if not result:
                result = fetch_result_from_source(home, away, search_sofascore)
            if not result:
                result = fetch_result_from_source(home, away, search_flashscore)
            # Playwright-based live search (slow but reliable)
            if not result:
                result = fetch_result_from_source(home, away, search_flashscore_playwright)

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
