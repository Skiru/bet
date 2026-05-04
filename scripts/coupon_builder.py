#!/usr/bin/env python3
"""S8 Coupon Builder — Builds betting coupons from S7 gate-approved picks.

Implements §8.1 core portfolio, §8.1b combo menu, §8.2 stress test,
stake calculation (Kelly 1/4), and Polish-language coupon output.

Usage:
    python3 scripts/coupon_builder.py --date 2026-05-01
    python3 scripts/coupon_builder.py --date 2026-05-01 --input s7_gate_results.json
"""

import argparse
import itertools
import json
import re
import sys
from datetime import datetime
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


def _bm(pick: dict) -> dict:
    """Safely get best_market from a pick, handling None values."""
    return pick.get("best_market") or {}


def _safe_float(val, default=0.0):
    """Safely convert a value to float. Handles fractions like '5/7'."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    try:
        s = str(val).strip()
        if "/" in s:
            num, den = s.split("/", 1)
            den_f = float(den)
            return float(num) / den_f if den_f else default
        return float(s)
    except (ValueError, TypeError, ZeroDivisionError):
        return default


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


def _build_rich_description(pick: dict) -> str:
    """Build rich Polish-language description with analysis rationale for a single pick."""
    home = pick.get("home_team", "?")
    away = pick.get("away_team", "?")
    sport = pick.get("sport", "")
    best = pick.get("best_market") or {}
    market_name = best.get("name", "?")
    direction = best.get("direction", "")
    line = best.get("line")
    odds = (pick.get("odds") or {}).get("market_best", 0) or 0

    pl = format_market_polish(market_name, direction, line)
    emoji = SPORT_EMOJI.get(sport, "")

    lines = [f"{emoji} {home} vs {away} — {pl} @{odds:.2f}"]

    # Analysis rationale
    safety = best.get("safety_score")
    hit_rate_l10 = best.get("hit_rate_l10")
    hit_rate_h2h = best.get("hit_rate_h2h")
    hit_rate_l5 = best.get("hit_rate_l5")
    h2h_avg = best.get("h2h_avg")
    combined_avg = best.get("combined_avg")
    l10_avg = best.get("l10_avg") or combined_avg
    l5_avg = best.get("l5_avg")
    team_a_avg = best.get("team_a_avg")
    team_b_avg = best.get("team_b_avg")
    margin = best.get("margin")
    rank = best.get("rank")
    total_markets = best.get("total_markets_evaluated") or pick.get("market_count")
    three_way = pick.get("three_way_alignment")
    gate_score = pick.get("gate_score")
    risk_tier = pick.get("risk_tier")
    h2h_count = pick.get("h2h_count", 0)
    data_quality = pick.get("data_quality")

    analysis_parts = []

    # Market ranking
    if safety is not None:
        rank_text = f"Rynek #{rank}" if rank else "Najlepszy rynek"
        markets_text = f" z {total_markets}" if total_markets else ""
        analysis_parts.append(f"\U0001f4ca {rank_text} wg safety score ({safety:.2f}){markets_text}")

    # L10 average vs line
    if l10_avg is not None and line is not None and line > 0:
        margin_pct = round((l10_avg / line - 1) * 100)
        sign = "+" if margin_pct > 0 else ""
        analysis_parts.append(f"\u2022 L10 \u015brednia: {l10_avg:.1f} vs linia {line} ({sign}{margin_pct}% margines)")

    # H2H average
    if h2h_avg is not None:
        h2h_meetings = f" ({h2h_count} spotkań)" if h2h_count else ""
        analysis_parts.append(f"\u2022 H2H \u015brednia: {h2h_avg:.1f}{h2h_meetings}")

    # Team-level averages
    if team_a_avg is not None and team_b_avg is not None and team_a_avg > 0 and team_b_avg > 0:
        analysis_parts.append(f"\u2022 {home}: {team_a_avg:.1f} | {away}: {team_b_avg:.1f}")

    # Hit rates
    hit_parts = []
    if hit_rate_l10:
        hit_parts.append(f"L10: {hit_rate_l10}")
    if hit_rate_h2h and hit_rate_h2h != "N/A":
        hit_parts.append(f"H2H: {hit_rate_h2h}")
    if hit_rate_l5:
        hit_parts.append(f"L5: {hit_rate_l5}")
    if hit_parts:
        analysis_parts.append(f"\u2022 Trafienia: {' | '.join(hit_parts)}")

    # Three-way alignment
    if three_way:
        alignment_emoji = "\u2705" if "3/3" in str(three_way) else "\u26a0\ufe0f"
        analysis_parts.append(f"\u2022 3-Way Check: {three_way} {alignment_emoji}")

    # L5 trend
    if l5_avg is not None and l10_avg is not None and l10_avg > 0:
        pct_change = (l5_avg - l10_avg) / l10_avg * 100
        if pct_change > 5:
            analysis_parts.append(f"\u2022 Forma \u2197: L5={l5_avg:.1f} vs L10={l10_avg:.1f} (trend rosn\u0105cy)")
        elif pct_change < -5:
            analysis_parts.append(f"\u2022 Forma \u2198: L5={l5_avg:.1f} vs L10={l10_avg:.1f} (trend spadkowy)")
        else:
            analysis_parts.append(f"\u2022 Forma \u2192: L5={l5_avg:.1f} \u2248 L10={l10_avg:.1f} (stabilna)")

    # Gate score and tier
    gate_parts = []
    if gate_score:
        gate_parts.append(f"Gate: {gate_score}")
    if risk_tier:
        gate_parts.append(f"Tier: {risk_tier}")
    if data_quality:
        gate_parts.append(f"Dane: {data_quality}")
    if gate_parts:
        analysis_parts.append(f"\u2022 {' | '.join(gate_parts)}")

    # Margin (distance from line)
    if margin is not None and margin != 1.0:
        margin_pct = round((margin - 1) * 100, 1)
        analysis_parts.append(f"\u2022 Margines bezpieczeństwa: {margin_pct:+.1f}%")

    # EV if available
    ev = pick.get("ev")
    if ev is not None:
        analysis_parts.append(f"\u2022 EV: {ev:+.0%}")

    # Gate warnings (top 2 most relevant)
    warnings = pick.get("gate_warnings", [])
    relevant_warnings = [w for w in warnings if not w.startswith("STATS-FIRST") and "markets evaluated" not in w]
    if relevant_warnings:
        analysis_parts.append(f"\u26a0 {'; '.join(relevant_warnings[:2])}")

    if analysis_parts:
        lines.append("")
        lines.extend(analysis_parts)

    return "\n".join(lines)


def _event_key(pick: dict) -> str:
    """Unique event key — same match = same key."""
    home = (pick.get("home_team") or "").strip().lower()
    away = (pick.get("away_team") or "").strip().lower()
    return f"{home}|{away}"


# ---------------------------------------------------------------------------
# Stakes — Kelly 1/4
# ---------------------------------------------------------------------------

def compute_stake(odds: float, safety: float, bankroll: float, tier: str,
                  probability: float | None = None) -> float:
    """Kelly 1/4 stake calculation with tier caps.

    f = (b*p - q) / b  where b = odds - 1, p = probability (or safety_score), q = 1-p
    stake = bankroll * f / 4
    """
    # Prefer true probability from probability_engine over safety_score hit rate
    p = probability if probability is not None and 0 < probability < 1 else safety
    if odds <= 1.0 or p <= 0:
        return 1.0

    b = odds - 1.0
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
        bm = _bm(leg)
        # Prefer true probability from probability_engine; fall back to safety_score
        p = _safe_float(bm.get("probability") or bm.get("safety_score", 0.5), 0.5)
        probabilities.append(p)
        if p < weakest_p:
            weakest_p = p
            weakest = leg

    p_coupon = 1.0
    for p in probabilities:
        p_coupon *= p

    catastrophe = "Brak danych"
    if weakest:
        wm = _bm(weakest)
        event = f"{weakest.get('home_team', '?')} vs {weakest.get('away_team', '?')}"
        market = wm.get("name", "?")
        catastrophe = f"Przegrywa jeśli {event} — {market} nie trafi (p={weakest_p:.0%})"

    return {
        "p_coupon": round(p_coupon, 4),
        "weakest_leg": {
            "event": f"{weakest.get('home_team', '?')} vs {weakest.get('away_team', '?')}" if weakest else None,
            "market": _bm(weakest).get("name") if weakest else None,
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


def _determine_coupon_count(n_picks: int, config: dict | None = None) -> int:
    """Determine how many core coupons to build from N approved picks."""
    if n_picks < 2:
        return 0
    if n_picks <= 3:
        cap = 1
    elif n_picks <= 5:
        cap = 2
    elif n_picks <= 7:
        cap = 3
    elif n_picks <= 9:
        cap = 4
    elif n_picks <= 12:
        cap = 5
    elif n_picks <= 16:
        cap = 7
    else:
        cap = min(n_picks // 2, 15)  # Scale with picks, cap at 15
    max_core = (config or {}).get("max_core_coupons", 15)
    return min(cap, max_core)


def assign_picks_to_core(approved: list, config: dict) -> list[dict]:
    """Assign approved picks to core coupons (unique event per coupon).

    Sorting: EV desc → confidence desc → safety desc.
    Grouping: LR → LR coupons, MS → MS, HR → HR, night → NIGHT.
    Constraints: min 2 legs, max 2 same sport, no same-match legs.
    Only picks with real odds (>1.0) are eligible for multi-bet coupons.
    """
    # Filter to picks with real odds for multi-bet coupons
    odds_approved = [p for p in approved if ((p.get("odds") or {}).get("market_best") or 0) > 1.0]
    if len(odds_approved) < 2:
        return []

    tz_name = config.get("timezone", "Europe/Warsaw")
    min_legs = config.get("min_legs_per_coupon", 2)
    max_legs = config.get("max_legs_per_coupon", 4)
    # Dynamic max legs: LR-only coupons can have more legs
    base_max_legs = max_legs
    max_same_sport = config.get("max_same_sport_legs_in_coupon", 2)
    bankroll = config.get("bankroll_pln", config.get("working_bankroll_pln", 50.0))

    # Sort: EV desc → confidence desc → safety desc
    sorted_picks = sorted(
        odds_approved,
        key=lambda p: (
            -(p.get("ev") or 0),
            -(p.get("final_confidence") or 0),
            -(_bm(p).get("safety_score") or 0),
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

    n_core = _determine_coupon_count(len(odds_approved), config)
    date_str = _extract_date(odds_approved)

    coupons: list[dict] = []
    all_assigned: set[str] = set()

    # Build coupons tier by tier
    for tier_label in ("LR", "MS", "HR", "NIGHT"):
        picks_in_tier = buckets[tier_label]
        if not picks_in_tier:
            continue

        # How many coupons for this tier? Proportional to picks
        tier_proportion = len(picks_in_tier) / len(odds_approved)
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

            # Allow +1 leg for all-LR coupons, +2 for all-safety>0.75
            all_lr = all(l.get("risk_tier") == "LR" for l in current_legs)
            effective_max = base_max_legs + (1 if all_lr else 0)

            # Check if coupon is full enough to flush
            if len(current_legs) >= effective_max or len(current_legs) >= max(min_legs, len(picks_in_tier) // max(tier_coupons, 1)):
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
            _merge_orphan_legs(current_legs, coupons, max_same_sport, bankroll, max_legs)

    # Handle unassigned picks — try to put them into existing coupons
    unassigned = [p for p in sorted_picks if _event_key(p) not in all_assigned]
    for p in unassigned:
        _try_insert_into_coupon(p, coupons, max_same_sport, bankroll, max_legs)

    return coupons


def _make_coupon(coupon_id: str, tier: str, legs: list, config: dict) -> dict:
    """Build a coupon dict from legs."""
    bankroll = config.get("bankroll_pln", config.get("working_bankroll_pln", 50.0))

    combined_odds = 1.0
    for leg in legs:
        odds = (leg.get("odds") or {}).get("market_best", 1.0) or 1.0
        combined_odds *= odds
    combined_odds = round(combined_odds, 2)

    # Stake: use worst probability/safety among legs for Kelly
    min_safety = min(
        (_bm(leg).get("safety_score", 0.5) for leg in legs),
        default=0.5,
    )
    min_prob = min(
        (_bm(leg).get("probability") or _bm(leg).get("safety_score", 0.5)
         for leg in legs),
        default=None,
    )
    stake = compute_stake(combined_odds, min_safety, bankroll, tier, probability=min_prob)

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


def _merge_orphan_legs(orphans: list, coupons: list, max_same_sport: int, bankroll: float = 50.0,
                       max_legs: int = 4):
    """Merge orphan legs into existing coupons where constraints allow."""
    for leg in orphans:
        _try_insert_into_coupon(leg, coupons, max_same_sport, bankroll, max_legs)


def _try_insert_into_coupon(pick: dict, coupons: list, max_same_sport: int, bankroll: float = 50.0,
                            max_legs: int = 4):
    """Try to insert a pick into an existing coupon respecting constraints."""
    ek = _event_key(pick)
    sport = pick.get("sport", "other")

    for coupon in coupons:
        if len(coupon["legs"]) >= max_legs:
            continue

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
        # Recalculate stake with worst probability/safety among legs
        min_safety = min(
            (_bm(l).get("safety_score", 0.5) for l in coupon["legs"]),
            default=0.5,
        )
        min_prob = min(
            (_bm(l).get("probability") or _bm(l).get("safety_score", 0.5)
             for l in coupon["legs"]),
            default=None,
        )
        coupon["stake"] = compute_stake(combined, min_safety, bankroll, coupon.get("tier", "MS"), probability=min_prob)
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
            kw in (_bm(p).get("name", "") or "").lower()
            for kw in ("corner", "foul", "card", "rzut", "faul", "kartk")
        ),
        "tier": "LR",
    },
    {
        "name": "safe-totals",
        "thesis_pl": "Najwyższe safety score — minimalne ryzyko",
        "sort_key": lambda p: -(_bm(p).get("safety_score", 0)),
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
        "filter": lambda p: (_bm(p).get("direction", "") or "").upper() == "UNDER",
        "tier": "MS",
    },
    {
        "name": "statistical-powerhouse",
        "thesis_pl": "Najwyższe safety score — potwierdzone statystycznie",
        "sort_key": lambda p: -(_bm(p).get("safety_score", 0)),
        "top_n": 4,
        "tier": "LR",
    },
    {
        "name": "over-specialist",
        "thesis_pl": "Wszystkie OVER — korelacja z wysokim tempem gry",
        "filter": lambda p: (_bm(p).get("direction", "") or "").upper() == "OVER",
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
    """Generate combo coupons by remixing approved picks (theme-based + combinatorial)."""
    # Only use picks with real odds for combo coupons
    odds_approved = [p for p in approved if ((p.get("odds") or {}).get("market_best") or 0) > 1.0]
    if len(odds_approved) < 2:
        return []

    date_str = _extract_date(approved)
    min_legs = config.get("min_legs_per_coupon", 2)
    max_legs = config.get("max_legs_per_coupon", 4)
    max_same_sport = config.get("max_same_sport_legs_in_coupon", 2)
    max_combos = config.get("max_combo_coupons", 20)
    combos: list[dict] = []
    combo_num: dict[str, int] = {}

    for theme in COMBO_THEMES:
        if len(combos) >= max_combos:
            break

        selected = list(odds_approved)

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
            for p in sorted(odds_approved, key=lambda x: -(x.get("ev") or 0)):
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

    # Combinatorial combos — all C(n, k) combinations for k = min_legs..max_legs
    existing_signatures = {
        frozenset(_event_key(l) for l in c["legs"])
        for c in combos
    }

    for k in range(min_legs, min(max_legs + 1, 4)):  # 2-leg and 3-leg combos
        if len(combos) >= max_combos:
            break
        for combo_picks in itertools.combinations(odds_approved, k):
            if len(combos) >= max_combos:
                break
            # Check unique events
            event_keys = set()
            valid = True
            for p in combo_picks:
                ek = _event_key(p)
                if ek in event_keys:
                    valid = False
                    break
                event_keys.add(ek)
            if not valid:
                continue

            sig = frozenset(event_keys)
            if sig in existing_signatures:
                continue
            existing_signatures.add(sig)

            # Check sport diversity constraint
            sport_counts_c: dict[str, int] = {}
            for p in combo_picks:
                s = p.get("sport", "other")
                sport_counts_c[s] = sport_counts_c.get(s, 0) + 1
            if any(c > max_same_sport for c in sport_counts_c.values()):
                continue

            combo_num_total = len(combos) + 1
            cid = f"CP-{date_str}-COMB{k}x{combo_num_total}"
            coupon = _make_coupon(cid, "MS", list(combo_picks), config)
            coupon["combo_theme"] = f"combinatorial-{k}-fold"
            coupon["combo_thesis_pl"] = f"Kombinacja {k}-krotna — automatycznie wygenerowana"
            combos.append(coupon)

    # Enrich all combos with richer descriptions
    for coupon in combos:
        legs = coupon["legs"]
        avg_safety = sum(_bm(l).get("safety_score", 0) for l in legs) / max(len(legs), 1)
        sports_in_combo = sorted(set(l.get("sport", "?") for l in legs))
        over_count = sum(1 for l in legs if (_bm(l).get("direction", "") or "").upper() == "OVER")
        under_count = sum(1 for l in legs if (_bm(l).get("direction", "") or "").upper() == "UNDER")
        coupon["combo_description"] = {
            "avg_safety": round(avg_safety, 3),
            "sports": sports_in_combo,
            "direction_balance": f"OVER: {over_count}, UNDER: {under_count}",
            "legs_count": len(legs),
        }

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

    bankroll = config.get("bankroll_pln", config.get("working_bankroll_pln", 50.0))
    alloc_range = config.get("daily_exposure_range", config.get("suggested_daily_allocation_range_pln", [5.0, 15.0]))

    result = {
        "date": date,
        "bankroll": bankroll,
        "daily_allocation_range": alloc_range,
        "approved_count": len(approved),
        "core_coupons": [],
        "combos": [],
        "singles": [],
        "banker": None,
        "extended_pool": extended_pool,
        "rejected": rejected,
        "no_bet": False,
        "no_bet_reason": None,
    }

    # SINGLES — always generate for every approved pick
    date_str = _extract_date(approved) if approved else datetime.now().strftime("%Y%m%d")
    max_singles = config.get("max_singles", 50)
    singles = []
    for i, pick in enumerate(approved[:max_singles], 1):
        odds_val = (pick.get("odds") or {}).get("market_best", 0) or 0
        if odds_val <= 1.0:
            continue
        safety = (pick.get("best_market") or {}).get("safety_score", 0.5)
        prob = (pick.get("best_market") or {}).get("probability")
        stake = compute_stake(odds_val, safety, bankroll, pick.get("risk_tier", "MS"), probability=prob)
        single = {
            "id": f"CP-{date_str}-SINGLE{i}",
            "tier": pick.get("risk_tier", "MS"),
            "legs": [pick],
            "combined_odds": round(odds_val, 2),
            "stake": stake,
            "potential_return": round(stake * odds_val, 2),
            "stress_test": stress_test_coupon({"legs": [pick]}),
            "correlation_flags": [],
            "is_single": True,
        }
        singles.append(single)
    result["singles"] = singles

    # BANKER: highest safety score pick
    if singles:
        banker = max(singles, key=lambda s: (_bm(s["legs"][0])).get("safety_score", 0))
        banker["is_banker"] = True
        result["banker"] = banker

    if len(approved) < 1:
        result["no_bet"] = True
        result["no_bet_reason"] = "Brak zatwierdzonych typów."
        return result

    # Store approved for markdown writer (market matrix)
    result["_approved"] = approved

    # Build core portfolio (requires ≥2 picks)
    core = assign_picks_to_core(approved, config)
    result["core_coupons"] = core

    # Build combo menu (requires ≥2 picks)
    combos = generate_combos(approved, config)
    result["combos"] = combos

    # Compute summary metrics
    core_spend = sum(c.get("stake", 0) for c in core)
    combo_spend = sum(c.get("stake", 0) for c in combos)
    singles_spend = sum(c.get("stake", 0) for c in singles)
    total_return = (
        sum(c.get("potential_return", 0) for c in core)
        + sum(c.get("potential_return", 0) for c in combos)
        + sum(c.get("potential_return", 0) for c in singles)
    )
    best_case = total_return
    # Realistic: assume ~30% hit rate on coupons, ~45% on singles
    realistic = round(
        sum(c.get("potential_return", 0) for c in core + combos) * 0.3
        + sum(c.get("potential_return", 0) for c in singles) * 0.45,
        2,
    )

    result["summary"] = {
        "core_spend": round(core_spend, 2),
        "singles_spend": round(singles_spend, 2),
        "total_spend": round(core_spend + combo_spend + singles_spend, 2),
        "bankroll_after": round(bankroll - core_spend - singles_spend, 2),
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

def _compact_description(pick: dict, is_approved: bool) -> str:
    """Build a compact description for the Uwagi column of the market matrix."""
    best = _bm(pick)
    parts = []

    status = "✅" if is_approved else "📋"

    # No best_market → minimal info
    if not best.get("name"):
        odds = (pick.get("odds") or {}).get("market_best")
        if odds:
            parts.append(f"Kurs {odds:.2f}")
        parts.append("brak analizy")
        return f"{' · '.join(parts)} {status}"

    # L10 avg vs line
    l10 = best.get("l10_avg") or best.get("combined_avg")
    line = best.get("line")
    if l10 is not None and line and line > 0:
        margin = round((l10 / line - 1) * 100)
        parts.append(f"L10:{l10:.1f} ({margin:+d}%)")

    # H2H
    h2h = best.get("h2h_avg")
    if h2h is not None:
        h2h_count = pick.get("h2h_count", 0)
        parts.append(f"H2H:{h2h:.1f}({h2h_count}m)")

    # Three-way alignment
    twa = pick.get("three_way_alignment", "")
    if twa:
        if "3/3" in str(twa):
            parts.append("3W✅")
        elif "2/3" in str(twa):
            parts.append("3W⚠️")
        else:
            parts.append("3W❌")

    # L5 trend arrow
    l5 = best.get("l5_avg")
    if l5 is not None and l10 is not None and l10 > 0:
        pct = (l5 - l10) / l10 * 100
        if pct > 5:
            parts.append("↗")
        elif pct < -5:
            parts.append("↘")
        else:
            parts.append("→")

    # Gate score
    gate = pick.get("gate_score")
    if gate:
        parts.append(f"G:{gate}")

    # EV
    ev = pick.get("ev")
    if ev is not None:
        parts.append(f"EV{ev:+.0%}")

    # Risk tier
    tier = pick.get("risk_tier")
    if tier:
        parts.append(tier)

    return f"{' · '.join(parts)} {status}" if parts else status


def _market_matrix_rows(approved: list, extended: list) -> list[str]:
    """Build full market matrix rows."""
    rows = []
    all_picks = list(approved) + list(extended)
    for i, pick in enumerate(all_picks, 1):
        sport = pick.get("sport", "?")
        emoji = SPORT_EMOJI.get(sport, "❓")
        home = pick.get("home_team", "?")
        away = pick.get("away_team", "?")
        best = _bm(pick)
        market = best.get("name", "-")
        odds = (pick.get("odds") or {}).get("market_best")
        odds_str = f"{_safe_float(odds):.2f}" if odds else "-"
        safety = best.get("safety_score")
        safety_str = f"{_safe_float(safety):.2f}" if safety is not None else "-"
        hit_l10 = best.get("hit_rate_l10")
        hit_str = f"{_safe_float(hit_l10):.0%}" if hit_l10 else "-"
        direction = best.get("direction", "")

        is_approved = pick in approved
        uwagi = _compact_description(pick, is_approved)

        rows.append(
            f"| {i} | {emoji} | {home} vs {away} | {market} | {odds_str} "
            f"| {safety_str} | {hit_str} | {direction} | {uwagi} |"
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

        lines.append(f"**P(kupon):** ~{_safe_float(st.get('p_coupon', 0)):.0%}")
        lines.append(f"**Największe ryzyko:** {st.get('catastrophe', '-')}")

        if c.get("correlation_flags"):
            for flag in c["correlation_flags"]:
                lines.append(f"⚠️ {flag}")

        # Rich analysis per leg
        lines.append("")
        lines.append("### Analiza szczegółowa")
        for leg in c.get("legs", []):
            lines.append("")
            lines.append(_build_rich_description(leg))

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

    # BANKER section
    banker = coupons_data.get("banker")
    if banker:
        lines.append("## 🏆 BANKER (Główny typ dnia)")
        lines.append("")
        leg = banker["legs"][0]
        lines.append(_build_rich_description(leg))
        lines.append("")
        lines.append(f"**Stawka:** {banker['stake']:.2f} PLN | **Kurs:** {banker['combined_odds']:.2f} | **Zwrot:** {banker['potential_return']:.2f} PLN")
        lines.append("")

    # SINGLES section
    singles = coupons_data.get("singles", [])
    if singles:
        lines.append("## SINGLE BETS")
        lines.append("")
        lines.append("| # | ID | Co obstawić | Kurs | Stawka | Zwrot | Tier |")
        lines.append("|---|-----|-------------|------|--------|-------|------|")
        for i, s in enumerate(singles, 1):
            leg = s["legs"][0]
            desc = _pick_description_pl(leg)
            banker_mark = " 🏆" if s.get("is_banker") else ""
            lines.append(
                f"| {i} | {s['id']}{banker_mark} | {desc} "
                f"| {s['combined_odds']:.2f} | {s['stake']:.2f} PLN "
                f"| {s['potential_return']:.2f} PLN | {s['tier']} |"
            )
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
            desc = c.get("combo_description", {})
            if desc:
                lines.append(
                    f"  Avg safety: {_safe_float(desc.get('avg_safety', 0)):.3f} | "
                    f"Sports: {', '.join(desc.get('sports', []))} | "
                    f"{desc.get('direction_balance', '')}"
                )
            lines.append(f"**P(kupon):** ~{_safe_float(st.get('p_coupon', 0)):.0%}")
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
            best = _bm(pick)
            market = best.get("name", "-")
            odds = (pick.get("odds") or {}).get("market_best")
            odds_str = f"{_safe_float(odds):.2f}" if odds else "-"
            ev = pick.get("ev")
            ev_str = f"{_safe_float(ev):+.0%}" if ev else "-"
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
        f"| Singles | {len(singles)} typów, {summary.get('singles_spend', 0):.2f} PLN |",
        f"| Wydatek (core) | {summary.get('core_spend', 0):.2f} PLN |",
        f"| Wydatek (łącznie) | {summary.get('total_spend', 0):.2f} PLN |",
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
            best = _bm(pick)
            market = best.get("name", "-")
            safety = _safe_float(best.get("safety_score", 0.5), 0.5)
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
            best = _bm(pick)
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


def persist_coupons_to_db(coupons_data: dict, date: str) -> int:
    """Persist coupons and bets to SQLite DB (dual-write alongside JSON).

    Returns count of coupons persisted. Fails gracefully with 0 on error.
    """
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from bet.db.connection import get_db
        from bet.db.models import Bet, Coupon
        from bet.db.repositories import CouponRepo

        all_coupons = (
            coupons_data.get("core_coupons", [])
            + coupons_data.get("combos", [])
            + coupons_data.get("singles", [])
        )
        if not all_coupons:
            return 0

        with get_db() as conn:
            repo = CouponRepo(conn)
            persisted = 0
            for coup in all_coupons:
                try:
                    coupon_id_str = coup.get("id", f"CP-{date}-{persisted}")
                    legs = coup.get("legs", [])
                    coupon_type = "SINGLE" if coup.get("is_single") else "AKO"
                    coupon = Coupon(
                        id=None,
                        coupon_id=coupon_id_str,
                        coupon_type=coupon_type,
                        total_odds=coup.get("combined_odds", 0),
                        stake_pln=coup.get("stake", 0),
                        status="pending",
                        version=1,
                    )
                    db_coupon_id = repo.create_coupon(coupon)

                    # Persist individual bets/legs
                    for leg in legs:
                        bet = Bet(
                            id=None,
                            coupon_id=db_coupon_id,
                            fixture_id=None,
                            sport=leg.get("sport", ""),
                            event_name=f"{leg.get('home_team', '?')} vs {leg.get('away_team', '?')}",
                            market=(leg.get("best_market") or {}).get("market", ""),
                            selection=(leg.get("best_market") or {}).get("direction", ""),
                            odds=(leg.get("odds") or {}).get("market_best", 0) or 0,
                            safety_score=(leg.get("best_market") or {}).get("safety_score"),
                            hit_rate=(leg.get("best_market") or {}).get("hit_rate_l10"),
                            status="pending",
                            market_pl=(leg.get("best_market") or {}).get("market_pl", ""),
                        )
                        repo.add_bet(bet)
                    persisted += 1
                except Exception as e:
                    print(f"[coupon_builder] DB: skip coupon {coup.get('id', '?')}: {e}")
            conn.commit()
            print(f"[coupon_builder] DB: persisted {persisted}/{len(all_coupons)} coupons + bets to betting.db")
            return persisted
    except Exception as e:
        print(f"[coupon_builder] DB persistence failed (non-critical): {e}")
        return 0


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
            f"{len(coupons_data.get('singles', []))} singles, "
            f"{len(coupons_data['core_coupons'])} core coupons, "
            f"{len(coupons_data['combos'])} combos"
        )
        if coupons_data.get("banker"):
            bleg = coupons_data["banker"]["legs"][0]
            print(f"  Banker: {bleg.get('home_team', '?')} vs {bleg.get('away_team', '?')}")
        print(f"  Core spend: {s['core_spend']:.2f} PLN")
        print(f"  Total spend: {s['total_spend']:.2f} PLN")
        print(f"  Potential return: {s['total_potential_return']:.2f} PLN")


if __name__ == "__main__":
    main()
