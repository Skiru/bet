#!/usr/bin/env python3
"""S8 Coupon Builder — Builds betting coupons from S7 gate-approved picks.

Implements §8.1 core portfolio, §8.1b combo menu, §8.2 stress test,
stake calculation (Kelly 1/4), and Polish-language coupon output.

Usage:
    python3 scripts/coupon_builder.py --date 2026-05-01
    python3 scripts/coupon_builder.py --date 2026-05-01 --input s7_gate_results.json
"""

import argparse
import json
import re
import sys
from datetime import datetime
from itertools import combinations
from pathlib import Path

import zoneinfo

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "betting" / "data"
COUPON_DIR = ROOT_DIR / "betting" / "coupons"
CONFIG_PATH = ROOT_DIR / "config" / "betting_config.json"

# ---------------------------------------------------------------------------
# Polish market descriptions
# ---------------------------------------------------------------------------

MARKET_PL = {
    "Corners Total O/U": "Rzuty rożne łącznie",
    "Fouls Total O/U": "Faule łącznie",
    "Cards Total O/U": "Kartki łącznie",
    "Shots Total O/U": "Strzały łącznie",
    "Goals Total O/U": "Bramki łącznie",
    "Total Games O/U": "Gemy łącznie",
    "Total Sets O/U": "Sety łącznie",
    "Total Points O/U": "Punkty łącznie",
    "Total Frames O/U": "Frejmy łącznie",
    "Total Runs O/U": "Rundy łącznie",
    "Total Maps O/U": "Mapy łącznie",
    "Total 180s O/U": "180-tki łącznie",
    "Total Legs O/U": "Legi łącznie",
    "Total Goals O/U": "Bramki łącznie",
    "Total Rebounds O/U": "Zbiórki łącznie",
    "Total Aces O/U": "Asy łącznie",
    "Team A Corners O/U": "Rzuty rożne drużyny",
    "Team B Corners O/U": "Rzuty rożne drużyny",
    "Team A Fouls O/U": "Faule drużyny",
    "Team B Fouls O/U": "Faule drużyny",
    "Match Winner": "Zwycięzca meczu",
    "1X2": "1X2",
    "Double Chance": "Podwójna szansa",
    "Draw No Bet": "Remis bez zakładu",
    "BTTS": "Obie strzelą",
    "Handicap": "Handicap",
    "Set Handicap": "Handicap setowy",
    "Game Handicap": "Handicap gemowy",
}

DIRECTION_PL = {
    "OVER": "powyżej",
    "UNDER": "poniżej",
}

SPORT_EMOJI = {
    "football": "⚽",
    "basketball": "🏀",
    "tennis": "🎾",
    "volleyball": "🏐",
    "hockey": "🏒",
    "baseball": "⚾",
    "handball": "🤾",
    "esports": "🎮",
    "snooker": "🎱",
    "table_tennis": "🏓",
    "darts": "🎯",
    "mma": "🥊",
    "padel": "🏸",
    "speedway": "🏍️",
}

TIER_ORDER = {"LR": 0, "MS": 1, "HR": 2, "N": 3}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Load betting config from JSON."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Polish formatting helpers
# ---------------------------------------------------------------------------

def format_market_polish(market_name: str, direction: str, line: float | None = None) -> str:
    """Convert English market name + direction to Polish description."""
    # Try to find base market name (strip trailing numbers/line)
    base = market_name
    extracted_line = line

    # Extract line from market name like "Fouls Total O/U 22.5"
    m = re.search(r'(\d+\.?\d*)\s*$', market_name)
    if m:
        base = market_name[:m.start()].strip()
        if extracted_line is None:
            extracted_line = float(m.group(1))

    pl_name = MARKET_PL.get(base, base)
    dir_pl = DIRECTION_PL.get(direction.upper(), direction) if direction else ""

    if extracted_line is not None and dir_pl:
        return f"{dir_pl} {extracted_line} {pl_name}"
    elif dir_pl:
        return f"{dir_pl} {pl_name}"
    return pl_name


def _pick_description_pl(pick: dict) -> str:
    """Full Polish description of a single pick for coupon display."""
    home = pick.get("home_team", "?")
    away = pick.get("away_team", "?")
    best = pick.get("best_market") or {}
    market_name = best.get("name", "?")
    direction = best.get("direction", "")
    odds = (pick.get("odds") or {}).get("market_best", 0) or 0
    line = best.get("line")  # Use structured data instead of regex

    pl = format_market_polish(market_name, direction, line)
    return f"{home} vs {away}: {pl} ({odds:.2f})"


def _event_key(pick: dict) -> str:
    """Unique event key — same match = same key."""
    home = (pick.get("home_team") or "").strip().lower()
    away = (pick.get("away_team") or "").strip().lower()
    return f"{home}|{away}"


# ---------------------------------------------------------------------------
# Stakes — Kelly 1/4
# ---------------------------------------------------------------------------

def compute_stake(odds: float, safety: float, bankroll: float, tier: str) -> float:
    """Kelly 1/4 stake calculation with tier caps.

    f = (b*p - q) / b  where b = odds - 1, p = safety_score, q = 1-p
    stake = bankroll * f / 4
    """
    if odds <= 1.0 or safety <= 0:
        return 1.0

    b = odds - 1.0
    p = safety
    q = 1.0 - p
    f = (b * p - q) / b

    if f <= 0:
        return 1.0

    stake = bankroll * f / 4.0

    # Tier caps
    cap = 3.0 if tier in ("LR",) else 2.0
    stake = min(stake, cap)

    # Minimum 1.00 PLN
    stake = max(stake, 1.0)

    return round(stake, 2)


# ---------------------------------------------------------------------------
# Stress test (§8.2)
# ---------------------------------------------------------------------------

def stress_test_coupon(coupon: dict) -> dict:
    """Stress test a coupon: P(coupon), weakest leg, catastrophe scenario."""
    legs = coupon.get("legs", [])
    if not legs:
        return {"p_coupon": 0.0, "weakest_leg": None, "catastrophe": "Brak nóg"}

    probabilities = []
    weakest = None
    weakest_p = 1.0

    for leg in legs:
        safety = leg.get("best_market", {}).get("safety_score", 0.5)
        probabilities.append(safety)
        if safety < weakest_p:
            weakest_p = safety
            weakest = leg

    p_coupon = 1.0
    for p in probabilities:
        p_coupon *= p

    catastrophe = "Brak danych"
    if weakest:
        wm = weakest.get("best_market", {})
        event = f"{weakest.get('home_team', '?')} vs {weakest.get('away_team', '?')}"
        market = wm.get("name", "?")
        catastrophe = f"Przegrywa jeśli {event} — {market} nie trafi (p={weakest_p:.0%})"

    return {
        "p_coupon": round(p_coupon, 4),
        "weakest_leg": {
            "event": f"{weakest.get('home_team', '?')} vs {weakest.get('away_team', '?')}" if weakest else None,
            "market": weakest.get("best_market", {}).get("name") if weakest else None,
            "probability": weakest_p,
        },
        "catastrophe": catastrophe,
    }


# ---------------------------------------------------------------------------
# Core portfolio builder (§8.1)
# ---------------------------------------------------------------------------

def _classify_night(pick: dict, tz_name: str) -> bool:
    """Check if kickoff ≥ 20:00 in configured timezone."""
    kickoff_str = pick.get("kickoff", "")
    if not kickoff_str:
        return False
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
        if "T" in kickoff_str:
            dt = datetime.fromisoformat(kickoff_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=zoneinfo.ZoneInfo("UTC"))
            local = dt.astimezone(tz)
            return local.hour >= 20
    except Exception:
        pass
    return False


def _determine_coupon_count(n_picks: int) -> int:
    """Determine how many core coupons to build from N approved picks."""
    if n_picks < 4:
        return 0  # NO BET
    if n_picks <= 5:
        return 2
    if n_picks <= 7:
        return 3
    if n_picks <= 9:
        return 4
    return 5


def assign_picks_to_core(approved: list, config: dict) -> list[dict]:
    """Assign approved picks to core coupons (unique event per coupon).

    Sorting: EV desc → confidence desc → safety desc.
    Grouping: LR → LR coupons, MS → MS, HR → HR, night → NIGHT.
    Constraints: min 2 legs, max 2 same sport, no same-match legs.
    """
    if len(approved) < 4:
        return []

    tz_name = config.get("timezone", "Europe/Warsaw")
    min_legs = config.get("min_legs_per_coupon", 2)
    max_same_sport = config.get("max_same_sport_legs_in_coupon", 2)

    # Sort: EV desc → confidence desc → safety desc
    sorted_picks = sorted(
        approved,
        key=lambda p: (
            -(p.get("ev") or 0),
            -(p.get("final_confidence") or 0),
            -(p.get("best_market", {}).get("safety_score") or 0),
        ),
    )

    # Tag night picks
    for p in sorted_picks:
        p["_is_night"] = _classify_night(p, tz_name)

    # Bucket by tier (night is a separate bucket)
    buckets: dict[str, list] = {"LR": [], "MS": [], "HR": [], "NIGHT": []}
    for p in sorted_picks:
        if p["_is_night"]:
            buckets["NIGHT"].append(p)
        else:
            tier = p.get("risk_tier", "MS")
            if tier not in buckets:
                tier = "MS"
            buckets[tier].append(p)

    n_core = _determine_coupon_count(len(approved))
    date_str = _extract_date(approved)

    coupons: list[dict] = []
    all_assigned: set[str] = set()

    # Build coupons tier by tier
    for tier_label in ("LR", "MS", "HR", "NIGHT"):
        picks_in_tier = buckets[tier_label]
        if not picks_in_tier:
            continue

        # How many coupons for this tier? Proportional to picks
        tier_proportion = len(picks_in_tier) / len(approved)
        tier_coupons = max(1, round(n_core * tier_proportion))

        tier_num = 0
        current_legs: list = []
        sport_counts: dict[str, int] = {}
        event_keys: set[str] = set()

        for pick in picks_in_tier:
            ek = _event_key(pick)
            if ek in all_assigned:
                continue

            sport = pick.get("sport", "other")

            # Check same-match constraint
            if ek in event_keys:
                continue

            # Check same-sport limit
            if sport_counts.get(sport, 0) >= max_same_sport:
                # Try to flush current coupon and start new one
                if len(current_legs) >= min_legs and tier_num < tier_coupons:
                    tier_num += 1
                    cid = f"CP-{date_str}-{tier_label}{tier_num}"
                    coupons.append(_make_coupon(cid, tier_label, current_legs, config))
                    current_legs = []
                    sport_counts = {}
                    event_keys = set()
                elif len(current_legs) >= min_legs:
                    # Already at coupon limit, skip this pick for now
                    continue
                else:
                    continue

            current_legs.append(pick)
            sport_counts[sport] = sport_counts.get(sport, 0) + 1
            event_keys.add(ek)
            all_assigned.add(ek)

            # Check if coupon is full enough to flush
            if len(current_legs) >= max(min_legs, len(picks_in_tier) // max(tier_coupons, 1)):
                if tier_num < tier_coupons:
                    tier_num += 1
                    cid = f"CP-{date_str}-{tier_label}{tier_num}"
                    coupons.append(_make_coupon(cid, tier_label, current_legs, config))
                    current_legs = []
                    sport_counts = {}
                    event_keys = set()

        # Flush remaining legs
        if current_legs and len(current_legs) >= min_legs:
            tier_num += 1
            cid = f"CP-{date_str}-{tier_label}{tier_num}"
            coupons.append(_make_coupon(cid, tier_label, current_legs, config))
        elif current_legs:
            # Not enough legs for own coupon — merge into last coupon of same tier
            # or into the next tier's coupon
            _merge_orphan_legs(current_legs, coupons, max_same_sport)

    # Handle unassigned picks — try to put them into existing coupons
    unassigned = [p for p in sorted_picks if _event_key(p) not in all_assigned]
    for p in unassigned:
        _try_insert_into_coupon(p, coupons, max_same_sport)

    return coupons


def _make_coupon(coupon_id: str, tier: str, legs: list, config: dict) -> dict:
    """Build a coupon dict from legs."""
    bankroll = config.get("working_bankroll_pln", 50.0)

    combined_odds = 1.0
    for leg in legs:
        odds = (leg.get("odds") or {}).get("market_best", 1.0) or 1.0
        combined_odds *= odds
    combined_odds = round(combined_odds, 2)

    # Stake: use worst safety among legs for Kelly
    min_safety = min(
        (leg.get("best_market", {}).get("safety_score", 0.5) for leg in legs),
        default=0.5,
    )
    stake = compute_stake(combined_odds, min_safety, bankroll, tier)

    potential_return = round(stake * combined_odds, 2)

    coupon = {
        "id": coupon_id,
        "tier": tier,
        "legs": legs,
        "combined_odds": combined_odds,
        "stake": stake,
        "potential_return": potential_return,
        "stress_test": stress_test_coupon({"legs": legs}),
    }

    # Correlation check: same competition ≥2 legs
    comps = [leg.get("competition", "") for leg in legs if leg.get("competition")]
    seen = set()
    flags = []
    for c in comps:
        if c in seen:
            flags.append(f"KORELACJA: ≥2 nogi z {c}")
        seen.add(c)
    coupon["correlation_flags"] = flags

    return coupon


def _merge_orphan_legs(orphans: list, coupons: list, max_same_sport: int):
    """Merge orphan legs into existing coupons where constraints allow."""
    for leg in orphans:
        _try_insert_into_coupon(leg, coupons, max_same_sport)


def _try_insert_into_coupon(pick: dict, coupons: list, max_same_sport: int):
    """Try to insert a pick into an existing coupon respecting constraints."""
    ek = _event_key(pick)
    sport = pick.get("sport", "other")

    for coupon in coupons:
        existing_events = {_event_key(l) for l in coupon["legs"]}
        if ek in existing_events:
            continue

        sport_count = sum(1 for l in coupon["legs"] if l.get("sport") == sport)
        if sport_count >= max_same_sport:
            continue

        coupon["legs"].append(pick)
        # Recalculate all derived fields
        combined = 1.0
        for l in coupon["legs"]:
            combined *= (l.get("odds") or {}).get("market_best", 1.0) or 1.0
        coupon["combined_odds"] = round(combined, 2)
        coupon["stress_test"] = stress_test_coupon({"legs": coupon["legs"]})
        # Recalculate stake with worst safety among legs
        min_safety = min(
            (l.get("best_market", {}).get("safety_score", 0.5) for l in coupon["legs"]),
            default=0.5,
        )
        bankroll = 50.0  # Will be recalculated at summary level
        coupon["stake"] = compute_stake(combined, min_safety, bankroll, coupon.get("tier", "MS"))
        coupon["potential_return"] = round(coupon["stake"] * combined, 2)
        return True

    return False


def _extract_date(picks: list) -> str:
    """Extract date string from picks for coupon IDs."""
    for p in picks:
        ko = p.get("kickoff", "")
        if ko and "T" in ko:
            return ko.split("T")[0].replace("-", "")
    return datetime.now().strftime("%Y%m%d")


# ---------------------------------------------------------------------------
# Combo menu generator (§8.1b)
# ---------------------------------------------------------------------------

COMBO_THEMES = [
    {
        "name": "all-corners",
        "thesis_pl": "Wszystkie rzuty rożne/faule — rynki statystyczne się kumulują",
        "filter": lambda p: any(
            kw in (p.get("best_market", {}).get("name", "") or "").lower()
            for kw in ("corner", "foul", "card", "rzut", "faul", "kartk")
        ),
        "tier": "LR",
    },
    {
        "name": "safe-totals",
        "thesis_pl": "Najwyższe safety score — minimalne ryzyko",
        "sort_key": lambda p: -(p.get("best_market", {}).get("safety_score", 0)),
        "top_n": 3,
        "tier": "LR",
    },
    {
        "name": "high-ev",
        "thesis_pl": "Najwyższe EV — matematyczna przewaga",
        "sort_key": lambda p: -(p.get("ev") or 0),
        "top_n": 3,
        "tier": "MS",
    },
    {
        "name": "sport-diversifier",
        "thesis_pl": "Jeden typ na sport — dywersyfikacja",
        "unique_sport": True,
        "tier": "MS",
    },
    {
        "name": "under-specialist",
        "thesis_pl": "Wszystkie UNDER — korelacja z niskim tempem gry",
        "filter": lambda p: (p.get("best_market", {}).get("direction", "") or "").upper() == "UNDER",
        "tier": "MS",
    },
    {
        "name": "statistical-powerhouse",
        "thesis_pl": "Najwyższe safety score — potwierdzone statystycznie",
        "sort_key": lambda p: -(p.get("best_market", {}).get("safety_score", 0)),
        "top_n": 4,
        "tier": "LR",
    },
    {
        "name": "over-specialist",
        "thesis_pl": "Wszystkie OVER — korelacja z wysokim tempem gry",
        "filter": lambda p: (p.get("best_market", {}).get("direction", "") or "").upper() == "OVER",
        "tier": "MS",
    },
    {
        "name": "key-sports-only",
        "thesis_pl": "Tylko sporty kluczowe (Tier 1) — najlepiej pokryte danymi",
        "filter": lambda p: p.get("sport") in ("football", "volleyball", "basketball", "tennis"),
        "tier": "LR",
    },
]


def generate_combos(approved: list, config: dict) -> list[dict]:
    """Generate 4-8 combo coupons by remixing approved picks."""
    if len(approved) < 2:
        return []

    date_str = _extract_date(approved)
    min_legs = config.get("min_legs_per_coupon", 2)
    max_same_sport = config.get("max_same_sport_legs_in_coupon", 2)
    combos: list[dict] = []
    combo_num: dict[str, int] = {}

    for theme in COMBO_THEMES:
        if len(combos) >= 8:
            break

        selected = list(approved)

        # Apply filter
        if "filter" in theme:
            selected = [p for p in selected if theme["filter"](p)]

        # Apply sort + top_n
        if "sort_key" in theme:
            selected = sorted(selected, key=theme["sort_key"])
            top_n = theme.get("top_n", 3)
            selected = selected[:top_n]

        # Sport diversifier: one per sport
        if theme.get("unique_sport"):
            seen_sports: set[str] = set()
            diversified = []
            for p in sorted(approved, key=lambda x: -(x.get("ev") or 0)):
                sport = p.get("sport", "other")
                if sport not in seen_sports:
                    diversified.append(p)
                    seen_sports.add(sport)
            selected = diversified

        # Must have ≥ min_legs
        if len(selected) < min_legs:
            continue

        # Verify no same-match duplicates
        events = set()
        deduped = []
        for p in selected:
            ek = _event_key(p)
            if ek not in events:
                deduped.append(p)
                events.add(ek)
        selected = deduped

        if len(selected) < min_legs:
            continue

        # Enforce max same-sport
        sport_counts: dict[str, int] = {}
        filtered_legs = []
        for p in selected:
            s = p.get("sport", "other")
            if sport_counts.get(s, 0) < max_same_sport:
                filtered_legs.append(p)
                sport_counts[s] = sport_counts.get(s, 0) + 1
        selected = filtered_legs

        if len(selected) < min_legs:
            continue

        tier = theme.get("tier", "MS")
        tier_key = tier
        combo_num[tier_key] = combo_num.get(tier_key, 0) + 1
        cid = f"CP-{date_str}-COMBO-{tier_key}{combo_num[tier_key]}"

        coupon = _make_coupon(cid, tier, selected, config)
        coupon["combo_theme"] = theme["name"]
        coupon["combo_thesis_pl"] = theme["thesis_pl"]
        combos.append(coupon)

    return combos


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_coupons(gate_results: dict, config: dict) -> dict:
    """Main entry: build coupons from gate results.

    Returns full coupons data structure for output.
    """
    date = gate_results.get("date", datetime.now().strftime("%Y-%m-%d"))
    gr = gate_results.get("gate_results", {})
    approved = gr.get("approved", [])
    extended_pool = gr.get("extended_pool", [])
    rejected = gr.get("rejected", [])

    bankroll = config.get("working_bankroll_pln", 50.0)
    alloc_range = config.get("suggested_daily_allocation_range_pln", [5.0, 15.0])

    result = {
        "date": date,
        "bankroll": bankroll,
        "daily_allocation_range": alloc_range,
        "approved_count": len(approved),
        "core_coupons": [],
        "combos": [],
        "extended_pool": extended_pool,
        "rejected": rejected,
        "no_bet": False,
        "no_bet_reason": None,
    }

    if len(approved) < 4:
        result["no_bet"] = True
        result["no_bet_reason"] = (
            f"Tylko {len(approved)} zatwierdzonych typów (min. 4 dla kuponów). "
            "Rozważ poszerzenie skanowania lub obniżenie progów."
        )
        if len(approved) == 0:
            result["no_bet_reason"] = "Brak zatwierdzonych typów. Brak kuponów na dziś."
        return result

    # Store approved for markdown writer (market matrix)
    result["_approved"] = approved

    # Build core portfolio
    core = assign_picks_to_core(approved, config)
    result["core_coupons"] = core

    # Build combo menu
    combos = generate_combos(approved, config)
    result["combos"] = combos

    # Compute summary metrics
    core_spend = sum(c.get("stake", 0) for c in core)
    combo_spend = sum(c.get("stake", 0) for c in combos)
    total_return = sum(c.get("potential_return", 0) for c in core) + sum(
        c.get("potential_return", 0) for c in combos
    )
    best_case = total_return
    # Realistic: assume ~30% hit rate on coupons
    realistic = round(total_return * 0.3, 2)

    result["summary"] = {
        "core_spend": round(core_spend, 2),
        "total_spend": round(core_spend + combo_spend, 2),
        "bankroll_after": round(bankroll - core_spend, 2),
        "total_potential_return": round(total_return, 2),
        "best_case": round(best_case, 2),
        "realistic": realistic,
    }

    # Placement order: sort by tier safety (LR first)
    all_coupons = core + combos
    all_coupons.sort(key=lambda c: (TIER_ORDER.get(c.get("tier", "MS"), 1), -c.get("stress_test", {}).get("p_coupon", 0)))
    result["placement_order"] = [c["id"] for c in all_coupons]

    return result


# ---------------------------------------------------------------------------
# Markdown writer
# ---------------------------------------------------------------------------

def _market_matrix_rows(approved: list, extended: list) -> list[str]:
    """Build full market matrix rows."""
    rows = []
    all_picks = list(approved) + list(extended)
    for i, pick in enumerate(all_picks, 1):
        sport = pick.get("sport", "?")
        emoji = SPORT_EMOJI.get(sport, "❓")
        home = pick.get("home_team", "?")
        away = pick.get("away_team", "?")
        best = pick.get("best_market", {})
        market = best.get("name", "-")
        odds = (pick.get("odds") or {}).get("market_best")
        odds_str = f"{odds:.2f}" if odds else "-"
        safety = best.get("safety_score")
        safety_str = f"{safety:.2f}" if safety else "-"
        hit_l10 = best.get("hit_rate_l10")
        hit_str = f"{hit_l10:.0%}" if hit_l10 else "-"
        direction = best.get("direction", "")
        l10_avg = best.get("l10_avg")
        direction_info = direction
        if l10_avg is not None:
            direction_info = f"{direction} +{l10_avg:.0f}" if direction else "-"
        ev = pick.get("ev")
        ev_str = f"EV {ev:+.0%}" if ev else "-"

        status = "✅" if pick in approved else "📋"
        rows.append(
            f"| {i} | {emoji} | {home} vs {away} | {market} | {odds_str} "
            f"| {safety_str} | {hit_str} | {direction_info} | {ev_str} {status} |"
        )
    return rows


def _coupon_table_row(i: int, coupon: dict) -> str:
    """Build a coupon table row."""
    legs_desc = " + ".join(_pick_description_pl(leg) for leg in coupon["legs"])
    return (
        f"| {i} | {coupon['id']} | {legs_desc} "
        f"| {coupon['combined_odds']:.2f} | {coupon['stake']:.2f} PLN "
        f"| {coupon['potential_return']:.2f} PLN |"
    )


def _coupon_section(title: str, coupons: list[dict]) -> list[str]:
    """Build a markdown section for a group of coupons."""
    if not coupons:
        return []

    lines = [
        f"## {title}",
        "",
        "| # | Kupon ID | Co obstawić | Kurs | Stawka | Zwrot |",
        "|---|----------|-------------|------|--------|-------|",
    ]

    for i, c in enumerate(coupons, 1):
        lines.append(_coupon_table_row(i, c))

    lines.append("")

    for c in coupons:
        st = c.get("stress_test", {})
        thesis = c.get("combo_thesis_pl", "")

        if thesis:
            lines.append(f"**{c['id']}** — _{thesis}_")
        else:
            # Generate logic line from legs
            sports = set(leg.get("sport", "?") for leg in c["legs"])
            logic = f"Kupon {c['tier']} z {len(c['legs'])} nogami ({', '.join(sports)})"
            lines.append(f"**Logika:** {logic}")

        lines.append(f"**P(kupon):** ~{st.get('p_coupon', 0):.0%}")
        lines.append(f"**Największe ryzyko:** {st.get('catastrophe', '-')}")

        if c.get("correlation_flags"):
            for flag in c["correlation_flags"]:
                lines.append(f"⚠️ {flag}")

        lines.append("")

    return lines


def write_coupon_markdown(coupons_data: dict, date: str) -> Path:
    """Write the full coupon markdown file."""
    COUPON_DIR.mkdir(parents=True, exist_ok=True)
    out_path = COUPON_DIR / f"{date}.md"

    bankroll = coupons_data.get("bankroll", 0)
    alloc = coupons_data.get("daily_allocation_range", [5, 15])
    lines = [
        f"# Kupony na {date} | Bankroll: {bankroll:.2f} PLN | Budżet: {alloc[0]:.0f}-{alloc[1]:.0f} PLN",
        "",
        "> Wszystkie typy są WARUNKOWE — zweryfikuj kursy w aplikacji Betclic przed postawieniem.",
        "",
    ]

    if coupons_data.get("no_bet"):
        lines.append(f"## ⚠️ NO BET")
        lines.append("")
        lines.append(coupons_data.get("no_bet_reason", "Brak typów."))
        lines.append("")
        out_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"[coupon_builder] Markdown (NO BET): {out_path}")
        return out_path

    approved = coupons_data.get("_approved", [])
    extended = coupons_data.get("extended_pool", [])

    # PEŁNA MATRYCA RYNKÓW
    if approved or extended:
        lines.append("## PEŁNA MATRYCA RYNKÓW")
        lines.append("")
        lines.append("| # | Sport | Wydarzenie | Rynek | Kurs | Safety | Hit% | Kierunek | Uwagi |")
        lines.append("|---|-------|------------|-------|------|--------|------|----------|-------|")
        lines.extend(_market_matrix_rows(approved, extended))
        lines.append("")

    # Core coupons by tier
    core = coupons_data.get("core_coupons", [])
    tier_groups = {"LR": [], "MS": [], "HR": [], "NIGHT": []}
    for c in core:
        tier = c.get("tier", "MS")
        bucket = tier if tier in tier_groups else "MS"
        tier_groups[bucket].append(c)

    tier_titles = {
        "LR": "LOW-RISK",
        "MS": "MULTI-SPORT",
        "HR": "HIGHER-RISK",
        "NIGHT": "NIGHT",
    }

    for tier_key in ("LR", "MS", "HR", "NIGHT"):
        section = _coupon_section(tier_titles[tier_key], tier_groups[tier_key])
        lines.extend(section)

    # Combo menu
    combos = coupons_data.get("combos", [])
    if combos:
        lines.append("## COMBINATION MENU")
        lines.append("")
        lines.append("| # | Kupon ID | Co obstawić | Kurs | Stawka | Zwrot |")
        lines.append("|---|----------|-------------|------|--------|-------|")
        for i, c in enumerate(combos, 1):
            lines.append(_coupon_table_row(i, c))
        lines.append("")
        for c in combos:
            st = c.get("stress_test", {})
            thesis = c.get("combo_thesis_pl", "")
            lines.append(f"**{c['id']}** — _{thesis}_")
            lines.append(f"**P(kupon):** ~{st.get('p_coupon', 0):.0%}")
            lines.append(f"**Największe ryzyko:** {st.get('catastrophe', '-')}")
            lines.append("")

    # Extended pool
    if extended:
        lines.append("## ROZSZERZONY WYBÓR (EXTENDED POOL)")
        lines.append("")
        lines.append("| # | Wydarzenie | Rynek | Kurs | EV | Gate | Za ✅ | Przeciw ❌ |")
        lines.append("|---|------------|-------|------|----|------|-------|-----------|")
        for i, pick in enumerate(extended, 1):
            home = pick.get("home_team", "?")
            away = pick.get("away_team", "?")
            best = pick.get("best_market", {})
            market = best.get("name", "-")
            odds = (pick.get("odds") or {}).get("market_best")
            odds_str = f"{odds:.2f}" if odds else "-"
            ev = pick.get("ev")
            ev_str = f"{ev:+.0%}" if ev else "-"
            gate = pick.get("gate_score", "-")
            # Pros/cons from gate details
            pros = []
            cons = []
            for gid, gd in (pick.get("gate_details") or {}).items():
                if isinstance(gd, dict):
                    if gd.get("passed"):
                        pros.append(f"G{gid}")
                    else:
                        cons.append(f"G{gid}")
            pros_str = ", ".join(pros[:3]) if pros else "-"
            cons_str = ", ".join(cons[:3]) if cons else "-"
            lines.append(
                f"| {i} | {home} vs {away} | {market} | {odds_str} | {ev_str} "
                f"| {gate} | {pros_str} | {cons_str} |"
            )
        lines.append("")

    # PODSUMOWANIE
    summary = coupons_data.get("summary", {})
    lines.extend([
        "## PODSUMOWANIE",
        "",
        "| Metryka | Wartość |",
        "|---------|--------|",
        f"| Wydatek (core) | {summary.get('core_spend', 0):.2f} PLN |",
        f"| Wydatek (core + combo) | {summary.get('total_spend', 0):.2f} PLN |",
        f"| Bankroll po | {summary.get('bankroll_after', 0):.2f} PLN |",
        f"| Łączny pot. zwrot | {summary.get('total_potential_return', 0):.2f} PLN |",
        f"| Najlepszy scenariusz | {summary.get('best_case', 0):.2f} PLN |",
        f"| Realistyczny | {summary.get('realistic', 0):.2f} PLN |",
        "",
    ])

    # KOLEJNOŚĆ STAWIANIA
    placement = coupons_data.get("placement_order", [])
    if placement:
        lines.append("## KOLEJNOŚĆ STAWIANIA")
        lines.append("")
        for i, cid in enumerate(placement, 1):
            label = "najbezpieczniejszy" if i == 1 else ""
            lines.append(f"{i}. {cid}" + (f" ({label})" if label else ""))
        lines.append("")

    # LISTA OBSERWACYJNA — extended pool picks with min odds
    if extended:
        lines.append("## LISTA OBSERWACYJNA")
        lines.append("")
        lines.append("| Wydarzenie | Rynek | Min kurs | Warunek |")
        lines.append("|------------|-------|----------|---------|")
        for pick in extended[:10]:
            home = pick.get("home_team", "?")
            away = pick.get("away_team", "?")
            best = pick.get("best_market", {})
            market = best.get("name", "-")
            safety = best.get("safety_score", 0.5)
            min_odds = round(1.0 / safety, 2) if safety > 0 else "-"
            lines.append(
                f"| {home} vs {away} | {market} | {min_odds} | "
                f"EV>0 przy kursie ≥{min_odds} |"
            )
        lines.append("")

    # ODRZUCONE (Top 10)
    rejected = coupons_data.get("rejected", [])
    if rejected:
        lines.append("## ODRZUCONE (Top 10)")
        lines.append("")
        lines.append("| Wydarzenie | Rynek | Powód odrzucenia |")
        lines.append("|------------|-------|------------------|")
        for pick in rejected[:10]:
            home = pick.get("home_team", "?")
            away = pick.get("away_team", "?")
            best = pick.get("best_market", {})
            market = best.get("name", "-")
            # Extract rejection reason
            failed_gates = []
            for gid, gd in (pick.get("gate_details") or {}).items():
                if isinstance(gd, dict) and not gd.get("passed"):
                    msg = gd.get("message", gd.get("label", f"Gate {gid}"))
                    failed_gates.append(msg)
            reason = "; ".join(failed_gates[:3]) if failed_gates else pick.get("rejection_reason", "-")
            lines.append(f"| {home} vs {away} | {market} | {reason} |")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[coupon_builder] Markdown: {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# JSON writer
# ---------------------------------------------------------------------------

def write_coupon_json(coupons_data: dict, date: str) -> Path:
    """Write coupon data to JSON."""
    COUPON_DIR.mkdir(parents=True, exist_ok=True)
    out_path = COUPON_DIR / f"{date}.json"

    # Strip internal keys
    clean = json.loads(json.dumps(coupons_data, default=str))
    clean.pop("_approved", None)

    out_path.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[coupon_builder] JSON: {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="S8 Coupon Builder — Build coupons from S7 gate-approved picks"
    )
    parser.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Betting day YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Path to S7 gate results JSON (overrides default path)",
    )

    args = parser.parse_args()

    # Load gate results
    if args.input:
        input_path = Path(args.input)
    else:
        input_path = DATA_DIR / f"{args.date}_s7_gate_results.json"

    if not input_path.exists():
        print(f"[coupon_builder] ERROR: Gate results not found: {input_path}")
        print(f"[coupon_builder] Run gate_checker.py first: python3 scripts/gate_checker.py --date {args.date}")
        sys.exit(1)

    with open(input_path, encoding="utf-8") as f:
        gate_results = json.load(f)

    # Load config
    config = load_config()

    # Build coupons
    coupons_data = build_coupons(gate_results, config)

    # Attach approved for markdown writer (not persisted to JSON)
    coupons_data["_approved"] = gate_results.get("gate_results", {}).get("approved", [])

    # Write outputs
    write_coupon_markdown(coupons_data, args.date)
    write_coupon_json(coupons_data, args.date)

    # Print summary
    if coupons_data.get("no_bet"):
        print(f"\n[coupon_builder] NO BET: {coupons_data['no_bet_reason']}")
    else:
        s = coupons_data["summary"]
        print(
            f"\n[coupon_builder] Done: "
            f"{len(coupons_data['core_coupons'])} core coupons, "
            f"{len(coupons_data['combos'])} combos"
        )
        print(f"  Core spend: {s['core_spend']:.2f} PLN")
        print(f"  Total spend: {s['total_spend']:.2f} PLN")
        print(f"  Potential return: {s['total_potential_return']:.2f} PLN")


if __name__ == "__main__":
    main()
