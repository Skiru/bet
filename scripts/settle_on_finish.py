#!/usr/bin/env python3
"""
Generic settlement script for pending picks and coupons.

Usage:
  python3 scripts/settle_on_finish.py                          # settle all pending
  python3 scripts/settle_on_finish.py --match "Team A vs Team B"  # settle specific match
  python3 scripts/settle_on_finish.py --betting-day 2026-04-21    # settle specific day

Notes:
- Polls Flashscore for final scores.
- Auto-settles: match winner/1X2, totals (any line), BTTS, double chance.
- Football stat markets (corners, cards, fouls, shots): auto-settled via canonical DB match_stats when
  coverage exists (Branch B); tagged manual_verification_required when coverage is missing.
- Other markets (handicaps, MyCombi) are left as 'pending' for manual verification.
- Does NOT auto-push to git. Run git commands manually after verification.
"""
import csv
import json
import re
import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing dependencies. Run: pip install requests beautifulsoup4")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bet.utils import names_match

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
    # DB-first: try loading odds from DB
    try:
        from db_data_loader import load_odds_from_db
        from datetime import date as _date_cls
        _today = _date_cls.today().isoformat()
        odds_data = load_odds_from_db(_today)
        if odds_data and odds_data.get("events"):
            print(f"[settle] DB: loaded {len(odds_data['events'])} odds events")
            home_lower = home.lower()
            away_lower = away.lower()
            for event in odds_data["events"]:
                eh = (event.get("home_team") or "").lower()
                ea = (event.get("away_team") or "").lower()
                # Use names_match for robust matching (handles aliases, diacritics)
                h_match = names_match(home_lower, eh, threshold=70) >= 70
                a_match = names_match(away_lower, ea, threshold=70) >= 70
                h_match_swapped = names_match(home_lower, ea, threshold=70) >= 70
                a_match_swapped = names_match(away_lower, eh, threshold=70) >= 70
                if not (h_match and a_match) and not (h_match_swapped and a_match_swapped):
                    continue
                if not event.get("completed"):
                    continue
                scores = event.get("scores")
                if not scores or len(scores) < 2:
                    continue
                score_map = {s["name"].lower(): int(s["score"]) for s in scores if s.get("score") and s["score"].isdigit()}
                if eh in score_map and ea in score_map:
                    if h_match and a_match:
                        # Direct: our home = event home
                        return score_map[eh], score_map[ea]
                    else:
                        # Swapped: our home = event away
                        return score_map[ea], score_map[eh]
    except Exception as e:
        print(f"[settle] DB odds lookup failed, falling back to JSON: {e}")

    # JSON fallback
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
            # Use names_match for robust matching
            h_match = names_match(home_lower, eh, threshold=70) >= 70
            a_match = names_match(away_lower, ea, threshold=70) >= 70
            h_match_swapped = names_match(home_lower, ea, threshold=70) >= 70
            a_match_swapped = names_match(away_lower, eh, threshold=70) >= 70
            if not (h_match and a_match) and not (h_match_swapped and a_match_swapped):
                continue
            if not event.get("completed"):
                continue
            scores = event.get("scores")
            if not scores or len(scores) < 2:
                continue
            score_map = {s["name"].lower(): int(s["score"]) for s in scores if s.get("score") and s["score"].isdigit()}
            if eh in score_map and ea in score_map:
                # Return in home/away order as requested
                if h_match and a_match:
                    # Direct: our home = event home
                    return score_map[eh], score_map[ea]
                else:
                    # Swapped: our home = event away
                    return score_map[ea], score_map[eh]
    return None


def search_cached_html(home, away, sport=None):
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
                        if _validate_score(s1, s2, sport=sport):
                            return (s2, s1) if swap else (s1, s2)
            except Exception:
                continue
    return None


def _validate_score(s1, s2, max_total=30, sport=None):
    """Reject clearly impossible scores. Sport-aware thresholds."""
    sport_limits = {
        "basketball": (300, 200),  # max_total, max_single
        "volleyball": (5, 3),     # set-based score (max 3-2)
        "tennis": (7, 5),          # set-based score (max 3-2 or 7-6 tiebreak sets)
        "hockey": (30, 20),
    }
    if sport and sport.lower() in sport_limits:
        mt, ms = sport_limits[sport.lower()]
        return s1 + s2 <= mt and s1 <= ms and s2 <= ms
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

        for (h, a), score in self._cache.items():
            # Use names_match for robust matching
            if names_match(home_lower, h, threshold=70) >= 70 and names_match(away_lower, a, threshold=70) >= 70:
                return score
            if names_match(home_lower, a, threshold=70) >= 70 and names_match(away_lower, h, threshold=70) >= 70:
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
                       "volleyball"]

        try:
            with sync_playwright() as p:
                try:
                    from playwright_stealth import Stealth
                except ImportError:
                    Stealth = None
                
                browser = p.chromium.launch(
                    headless=True,
                    args=['--disable-blink-features=AutomationControlled', '--disable-infobars', '--no-sandbox']
                )
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080}
                )
                page = context.new_page()
                if Stealth:
                    Stealth().apply_stealth_sync(page)

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
                            self._parse_scores(text, sport=sport)
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

    def _parse_scores(self, text, sport=None):
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
                    if _validate_score(s1, s2, sport=sport):
                        self._cache[(home_team.lower(), away_team.lower())] = (s1, s2)
                i += 5  # skip past this match block
            else:
                i += 1


_flashscore_batch_cache = _FlashscoreBatchFetcher()


def search_flashscore(home, away, sport=None):
    q = quote(f"{home} {away}")
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
            if _validate_score(s1, s2, sport=sport):
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
_SETTLEMENT_DB_MATCH_STATS_SOURCE = "db_match_stats_settlement"
_SETTLEMENT_MANUAL_SOURCE = "manual_verification_required"
_STAT_MARKET_KEYWORDS = (
    "corner",
    "card",
    "foul",
    "shot",
    "booking",
    "yellow",
    "red",
    "throw-in",
    "offside",
    "free kick",
)


def _settlement_date_candidates(betting_day: str | None) -> list[str]:
    if not betting_day:
        return []

    candidates = [betting_day]
    try:
        betting_date = datetime.fromisoformat(betting_day).date()
    except ValueError:
        return candidates

    for offset in (1, -1):
        candidate = (betting_date + timedelta(days=offset)).isoformat()
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _settlement_is_stat_market(market: str) -> bool:
    normalized = (market or "").lower()
    return any(keyword in normalized for keyword in _STAT_MARKET_KEYWORDS)


def _fetch_settlement_db_match_stats(
    home: str,
    away: str,
    sport: str,
    betting_day: str | None,
) -> dict | None:
    """Fetch canonical settlement stats from the local match_stats table."""
    try:
        src_path = str(BASE.parent / "src")
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        from bet.db.connection import get_db
        from bet.db.repositories import FixtureRepo, SportRepo, StatsRepo
    except ImportError:
        return None

    try:
        with get_db() as conn:
            sport_repo = SportRepo(conn)
            fixture_repo = FixtureRepo(conn)
            stats_repo = StatsRepo(conn)
            sport_obj = sport_repo.get_by_name(sport.lower())
            if not sport_obj:
                return None

            fixture = None
            for candidate_day in _settlement_date_candidates(betting_day):
                fixture = fixture_repo.get_by_teams_and_date(home, away, candidate_day, sport_obj.id)
                if fixture:
                    break

            if not fixture:
                return None

            rows = stats_repo.get_match_stats(fixture.id)
            if not rows:
                return None

            stats: dict[str, dict[str, float]] = {}
            for row in rows:
                stat_key = row.stat_key
                bucket = stats.setdefault(stat_key, {})
                if row.team_id == fixture.home_team_id:
                    bucket["home"] = float(row.stat_value)
                elif row.team_id == fixture.away_team_id:
                    bucket["away"] = float(row.stat_value)

            normalized = {
                stat_key: stat_value
                for stat_key, stat_value in stats.items()
                if "home" in stat_value and "away" in stat_value
            }
            return normalized or None
    except Exception as e:
        log(f"  [db-settlement] Error fetching stats for {home} vs {away}: {e}")
        return None


def settle_stat_market(
    pick,
    match_stats: dict,
    home_name: str,
    away_name: str,
    settlement_source: str = _SETTLEMENT_DB_MATCH_STATS_SOURCE,
) -> bool:
    """Try to settle a statistical market (corners, cards, shots) using match stats.

    Returns True if settled, False otherwise.
    """
    market = (pick.get("market") or "").lower()
    sel = (pick.get("selection") or "").lower()

    # Determine which stat key this market refers to
    stat_key = None
    if "corner" in market:
        stat_key = "corners"
    elif "card" in market or "booking" in market or "yellow" in market:
        stat_key = "yellow_cards"
    elif "red card" in market:
        stat_key = "red_cards"
    elif "shot" in market:
        stat_key = "shots_on_target" if "target" in market else "shots"
    elif "foul" in market:
        stat_key = "fouls"

    if not stat_key or stat_key not in match_stats:
        return False

    stat = match_stats[stat_key]
    total = stat["home"] + stat["away"]

    # Check for over/under pattern
    direction, line = parse_totals_line(market, sel)
    if direction and line is not None:
        if direction == "under":
            if total < line:
                pick["status"] = "win"
            elif total == line:
                pick["status"] = "push"
            else:
                pick["status"] = "loss"
        else:  # over
            if total > line:
                pick["status"] = "win"
            elif total == line:
                pick["status"] = "push"
            else:
                pick["status"] = "loss"

        pick["pnl_pln"] = compute_pnl(pick["status"], pick.get("bookmaker_odds"), pick.get("stake_pln"))
        pick["settlement_source"] = settlement_source
        return True

    return False


def _mark_manual_settlement_source(picks: list[dict]) -> list[dict]:
    marked = []
    for pick in picks:
        if pick.get("status") in ("pending", "placed") and _settlement_is_stat_market(pick.get("market", "")):
            pick["settlement_source"] = _SETTLEMENT_MANUAL_SOURCE
            marked.append(pick)
    return marked


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
    is_stat_market = _settlement_is_stat_market(market)
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
        elif all(s in ("win", "push", "void", "half_win", "half_loss") for s in statuses):
            # Recalculate effective odds from non-void/push legs
            # half_loss leg: multiplier = 0.5 (half stake returned)
            # half_win leg: multiplier = (1 + odds) / 2
            effective_odds = 1.0
            active_legs = 0
            for pid in pick_ids:
                pid = pid.strip()
                if pid in pick_map:
                    p = pick_map[pid]
                    if p.get("status") in ("win", "half_win", "half_loss"):
                        try:
                            leg_odds = float(p.get("bookmaker_odds", 1))
                            if p.get("status") == "half_win":
                                # Half win: half stake returned + half at full odds
                                leg_odds = (1 + leg_odds) / 2
                            elif p.get("status") == "half_loss":
                                # Half loss: half stake returned, half lost
                                leg_odds = 0.5
                            effective_odds *= leg_odds
                            active_legs += 1
                        except (ValueError, TypeError):
                            pass
            stake = float(coupon.get("stake_pln") or 0)
            if active_legs > 0:
                pnl = round(stake * (effective_odds - 1), 2)
                coupon["status"] = "win" if pnl >= 0 else "loss"
                coupon["pnl_pln"] = str(pnl)
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
            home, away = extract_teams(event)
            sport = p.get("sport")
            events[event] = (home, away, sport)

    polls = 0
    max_polls = 1 if args.no_poll else MAX_POLLS

    while polls < max_polls:
        polls += 1
        any_settled = False

        for event, (home, away, sport) in list(events.items()):
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
                result = fetch_result_from_source(home, away, lambda h, a: search_cached_html(h, a, sport=sport))
            # Network fallbacks (Flashscore uses JS — requests often fails)
            if not result:
                result = fetch_result_from_source(home, away, lambda h, a: search_flashscore(h, a, sport=sport))
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

                # Try canonical DB-backed match stats for remaining football stat-market picks.
                still_unsettled = [p for p in event_picks if p.get("status") in ("pending", "placed")]
                if still_unsettled and sport == "football":
                    match_stats = _fetch_settlement_db_match_stats(
                        home,
                        away,
                        sport=sport,
                        betting_day=event_picks[0].get("betting_day"),
                    )
                    if match_stats:
                        for p in still_unsettled:
                            if settle_stat_market(
                                p,
                                match_stats,
                                home,
                                away,
                                settlement_source=_SETTLEMENT_DB_MATCH_STATS_SOURCE,
                            ):
                                log(f"  Settled (stats) {p['pick_id']}: {p['status']} "
                                    f"(PnL: {p.get('pnl_pln', 'N/A')}) [src: db_match_stats]")
                                any_settled = True

                for p in _mark_manual_settlement_source(still_unsettled):
                    log(
                        f"  Manual verification required for {p['pick_id']}: "
                        f"no canonical match_stats coverage"
                    )
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

    # DB settlement: sync settled picks/coupons to DB (dual-write)
    _sync_settlement_to_db(picks, coupons)

    # Post-settlement: evaluate decisions for learning
    betting_day = args.betting_day or datetime.now().strftime("%Y-%m-%d")
    try:
        from evaluate_decisions import evaluate_settled_bets as _evaluate
        outcomes = _evaluate(betting_day)
        if outcomes:
            log(f"[evaluate] Created {len(outcomes)} decision outcomes for learning")
    except Exception as e:
        log(f"[evaluate] Decision evaluation failed (non-blocking): {e}")

    # Summary
    settled = [p for p in pending if p.get("status") not in ("pending", "placed")]
    still_pending = [p for p in pending if p.get("status") in ("pending", "placed")]
    log(f"Settlement complete: {len(settled)} settled, {len(still_pending)} still pending")

    # Task 4.2: Auto-append learning log entry
    if settled:
        _append_learning_log(settled, betting_day)


def _append_learning_log(settled: list[dict], betting_day: str):
    """Auto-append structured settlement summary to learning-log.md."""
    log_path = BASE.parent / "betting" / "journal" / "learning-log.md"
    
    # Idempotent: check if entry for this date already exists
    if log_path.exists():
        content = log_path.read_text(encoding="utf-8")
        if f"## {betting_day}" in content:
            log(f"[learning-log] Entry for {betting_day} already exists — skipping")
            return
    
    wins = sum(1 for p in settled if p.get("status") == "win")
    losses = sum(1 for p in settled if p.get("status") == "loss")
    voids = sum(1 for p in settled if p.get("status") in ("void", "push"))
    
    total_pnl = 0.0
    for p in settled:
        try:
            total_pnl += float(p.get("pnl_pln") or 0)
        except (ValueError, TypeError):
            pass
    
    # Per-market breakdown
    from collections import Counter
    market_wins = Counter()
    market_total = Counter()
    for p in settled:
        market = p.get("market_type") or p.get("market") or "unknown"
        market_total[market] += 1
        if p.get("status") == "win":
            market_wins[market] += 1
    
    best_market = max(market_total.keys(), key=lambda m: market_wins[m] / max(market_total[m], 1), default="N/A")
    worst_market = min(market_total.keys(), key=lambda m: market_wins[m] / max(market_total[m], 1), default="N/A")
    
    entry_lines = [
        f"\n## {betting_day} — Settlement Summary\n",
        f"- **Settled:** {len(settled)} bets ({wins}W / {losses}L / {voids}V)",
        f"- **Day PnL:** {total_pnl:.2f} PLN",
        f"- **Best market:** {best_market} ({market_wins[best_market]}/{market_total[best_market]})",
        f"- **Worst market:** {worst_market} ({market_wins[worst_market]}/{market_total[worst_market]})",
        f"- **Rule changes:** None (auto-generated, review manually)",
    ]
    
    # Drawdown alert
    try:
        cfg = json.loads((BASE.parent / "config" / "betting_config.json").read_text())
        bankroll = cfg.get("bankroll_pln") or cfg.get("working_bankroll_pln", 50)
        if total_pnl < -(bankroll * 0.20):
            entry_lines.append(f"- ⚠️ **DRAWDOWN ALERT:** {total_pnl:.2f} PLN = {total_pnl/bankroll*100:.1f}% of bankroll")
    except Exception:
        pass
    
    entry_lines.append("")
    
    # Append to file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("\n".join(entry_lines))
    
    log(f"[learning-log] Appended entry for {betting_day}")


def _sync_settlement_to_db(picks: list[dict], coupons: list[dict]):
    """Sync CSV settlement results to the DB (dual-write).

    Matches DB bets by event_name and updates their status + PnL.
    Also updates coupon-level status/PnL in the coupons table.
    """
    try:
        sys.path.insert(0, str(BASE.parent / "src"))
        from bet.db.connection import get_db
        from bet.db.repositories import CouponRepo

        settled_picks = [
            p for p in picks
            if p.get("status") not in ("pending", "placed", "")
        ]
        if not settled_picks:
            return

        with get_db() as conn:
            repo = CouponRepo(conn)
            db_updated_bets = 0
            db_updated_coupons = 0

            # Update individual bets by matching event_name
            for p in settled_picks:
                event = p.get("event", "")
                market = p.get("market", "")
                status = p.get("status", "")
                pnl_str = p.get("pnl_pln", "0")
                try:
                    pnl = float(pnl_str) if pnl_str else 0.0
                except (ValueError, TypeError):
                    pnl = 0.0

                # Find matching bets in DB (event_name + market)
                rows = conn.execute(
                    "SELECT b.id FROM bets b "
                    "LEFT JOIN fixtures f ON b.fixture_id = f.id "
                    "WHERE b.event_name = ? AND b.market = ? AND b.status = 'pending'",
                    (event, market),
                ).fetchall()
                for row in rows:
                    repo.settle_bet(row["id"], status, pnl)
                    db_updated_bets += 1

                # Fallback: match by event_name only if market didn't match
                # Only settle the first match to avoid incorrectly settling
                # multiple markets with the same PnL
                if not rows:
                    row = conn.execute(
                        "SELECT b.id FROM bets b "
                        "WHERE b.event_name = ? AND b.status = 'pending' "
                        "LIMIT 1",
                        (event,),
                    ).fetchone()
                    if row:
                        repo.settle_bet(row["id"], status, pnl)
                        db_updated_bets += 1

            # Update coupon status based on settled bets
            settled_coupon_ids = set()
            for c in coupons:
                if c.get("status") in ("pending", "placed", ""):
                    continue
                coupon_id_str = c.get("coupon_id", "")
                status = c.get("status", "")
                pnl_str = c.get("pnl_pln", "0")
                try:
                    pnl = float(pnl_str) if pnl_str else 0.0
                except (ValueError, TypeError):
                    pnl = 0.0

                rows = conn.execute(
                    "SELECT id FROM coupons WHERE coupon_id = ? AND status = 'pending'",
                    (coupon_id_str,),
                ).fetchall()
                for row in rows:
                    repo.settle_coupon(row["id"], status, pnl)
                    db_updated_coupons += 1
                    settled_coupon_ids.add(row["id"])

            conn.commit()
            if db_updated_bets or db_updated_coupons:
                log(f"DB settlement sync: {db_updated_bets} bets, {db_updated_coupons} coupons updated")
    except Exception as e:
        log(f"DB settlement sync failed (non-critical): {e}")


if __name__ == "__main__":
    main()
