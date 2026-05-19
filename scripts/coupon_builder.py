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
from datetime import datetime, timezone
from pathlib import Path

import zoneinfo

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "betting" / "data"
COUPON_DIR = ROOT_DIR / "betting" / "coupons"
CONFIG_PATH = ROOT_DIR / "config" / "betting_config.json"

# Ensure src/ is importable
sys.path.insert(0, str(ROOT_DIR / "src"))

_NOW = lambda: datetime.now(timezone.utc).isoformat()

# ---------------------------------------------------------------------------
# Polish market descriptions (from canonical source)
# ---------------------------------------------------------------------------

from bet.stats.market_ranking import MARKET_PL, DIRECTION_PL
from utils import normalize_team_name as _normalize_team


class _FallbackOutput:
    """Fallback output that prints when AgentOutput is not available."""
    def info(self, msg): print(f"[INFO] {msg}")
    def warning(self, msg): print(f"[WARN] {msg}")
    def event(self, *a, **kw): pass


# Module-level output — overridden in main() with AgentOutput
out = _FallbackOutput()


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
    odds_str = f"{odds:.2f}" if odds > 1.0 else "kurs TBD"
    return f"{home} vs {away}: {pl} ({odds_str})"


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

    # Tipster insight section
    tipster_section = _build_tipster_insight(pick)
    if tipster_section:
        lines.append("")
        lines.append(tipster_section)

    return "\n".join(lines)


def _build_tipster_insight(pick: dict) -> str:
    """Build tipster insight section showing tipster predictions for this event.

    Shows what tipsters predicted (source, market, reasoning) and compares
    with our analysis when they disagree.
    """
    tipster_support = pick.get("tipster_support") or {}
    tips = tipster_support.get("tips", [])

    # DB fallback if tipster_support not present in gate output
    if not tips:
        tips = _get_tipster_data_fallback(
            pick.get("home_team", ""),
            pick.get("away_team", ""),
            pick.get("betting_date", ""),
        )

    if not tips:
        return ""

    lines = ["🎯 TIPSTER INSIGHT:"]

    our_market = (pick.get("best_market") or {}).get("name", "")
    our_direction = (pick.get("best_market") or {}).get("direction", "")
    our_line = (pick.get("best_market") or {}).get("line")
    our_safety = (pick.get("best_market") or {}).get("safety_score")
    our_l10_avg = (pick.get("best_market") or {}).get("l10_avg")

    any_agrees = False
    for tip in tips[:4]:  # Max 4 tipsters shown
        source = tip.get("source_site") or tip.get("tipster") or tip.get("source") or "?"
        accuracy = tip.get("accuracy_pct")
        market = tip.get("market") or tip.get("market_type") or ""
        direction = tip.get("direction") or ""
        odds = tip.get("odds")
        reasoning = tip.get("reasoning") or ""

        # Format source with accuracy
        source_str = source
        if accuracy is not None:
            source_str = f"{source} ({accuracy}% acc)"

        # Format market prediction
        market_str = f"{market} {direction}" if direction else market
        if odds:
            market_str += f" @{_safe_float(odds):.2f}"

        # Truncate reasoning
        reasoning_str = ""
        if reasoning:
            r = reasoning.strip().replace("\n", " ")
            reasoning_str = f' — "{r[:80]}{"..." if len(r) > 80 else ""}"'

        lines.append(f"• {source_str}: {market_str}{reasoning_str}")

        # Check if tipster agrees with our pick (require >=5 char overlap + matching direction)
        if market and our_market and len(market) >= 5:
            tip_market_lower = market.lower().replace("_", " ").replace("-", " ")
            our_market_lower = our_market.lower().replace("_", " ").replace("-", " ")
            market_overlap = tip_market_lower in our_market_lower or our_market_lower in tip_market_lower
            direction_match = (not direction or not our_direction or
                               direction.lower() == our_direction.lower())
            if market_overlap and direction_match:
                any_agrees = True

    # Show our pick comparison
    if our_market:
        our_desc = format_market_polish(our_market, our_direction, our_line)
        details = []
        if our_safety:
            details.append(f"safety {our_safety:.2f}")
        if our_l10_avg:
            details.append(f"L10 avg {our_l10_avg:.1f}")
        detail_str = f" ({', '.join(details)})" if details else ""

        if any_agrees:
            lines.append(f"✓ ZGODNOŚĆ: Nasz wybór {our_desc}{detail_str} wspierany przez tipsterów")
        else:
            lines.append(f"↔ NASZ WYBÓR: {our_desc}{detail_str}")
            # Brief explanation why our pick differs
            if our_safety and our_safety >= 0.60:
                lines.append(f"   Różnica: Nasz rynek ma wyższy safety score — dane statystyczne mocniejsze niż opinia tipsterów")
            elif our_l10_avg and our_line and our_l10_avg > our_line:
                margin = round((our_l10_avg / our_line - 1) * 100)
                lines.append(f"   Różnica: L10 średnia {margin}% powyżej linii — statystyczny margines bezpieczeństwa")

    return "\n".join(lines)


def _get_tipster_data_fallback(home: str, away: str, date: str) -> list:
    """DB fallback: query TipsterRepo when tipster_support not in gate output."""
    if not home or not away or not date:
        return []
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import TipsterRepo
        from rapidfuzz import fuzz

        with get_db() as conn:
            repo = TipsterRepo(conn)
            all_picks = repo.get_picks_by_date(date)
            if not all_picks:
                return []

            home_lower = home.strip().lower()
            away_lower = away.strip().lower()
            matched = []
            for p in all_picks:
                p_home = (p.home_team or "").strip().lower()
                p_away = (p.away_team or "").strip().lower()
                # Exact match
                if p_home == home_lower and p_away == away_lower:
                    matched.append(_tipster_pick_to_dict(p))
                    continue
                # Fuzzy match
                score_h = fuzz.token_sort_ratio(home_lower, p_home)
                score_a = fuzz.token_sort_ratio(away_lower, p_away)
                if score_h >= 70 and score_a >= 70:
                    matched.append(_tipster_pick_to_dict(p))
            return matched
    except Exception as exc:
        import logging as _log
        _log.getLogger(__name__).warning(
            "tipster DB fallback failed for %s vs %s: %s", home, away, exc
        )
        return []


def _tipster_pick_to_dict(p) -> dict:
    """Convert TipsterPick model to dict for rendering."""
    return {
        "source_site": p.source_site,
        "tipster_name": p.tipster_name,
        "market": p.market,
        "market_type": p.market_type,
        "direction": p.direction,
        "odds": p.odds,
        "reasoning": p.reasoning,
        "accuracy_pct": p.accuracy_pct,
    }


def _event_key(pick: dict) -> str:
    """Unique event key — same match = same key (accent/suffix normalized)."""
    home = _normalize_team(pick.get("home_team") or "")
    away = _normalize_team(pick.get("away_team") or "")
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
        prob_val = bm.get("probability")
        p = _safe_float(prob_val if prob_val is not None else bm.get("safety_score", 0.5), 0.5)
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
    Picks with real odds preferred; in stats-first mode (R10), picks without
    odds are included using min_acceptable_odds = 1/safety_score.
    """
    # Filter to picks with real odds for multi-bet coupons
    odds_approved = [p for p in approved if ((p.get("odds") or {}).get("market_best") or 0) > 1.0]
    stats_first_mode = len(odds_approved) < 2 and len(approved) >= 2

    # Always include top-safety picks even without odds (R10 enhancement)
    sorted_by_safety = sorted(
        approved,
        key=lambda p: (_bm(p).get("safety_score") or 0),
        reverse=True,
    )
    odds_keys = {_event_key(p) for p in odds_approved}
    for p in sorted_by_safety:
        if len(odds_approved) >= 30:
            break
        ek = _event_key(p)
        if ek in odds_keys:
            continue
        if not _bm(p).get("safety_score"):
            continue
        odds_keys.add(ek)
        safety = (_bm(p).get("safety_score") or 0.5)
        p.setdefault("odds", {})["market_best"] = round(1.0 / max(safety, 0.1), 2)
        p["_stats_first_odds"] = True
        p["odds_source"] = "estimated"
        odds_approved.append(p)

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
    has_stats_first = False
    for leg in legs:
        odds = (leg.get("odds") or {}).get("market_best", 1.0) or 1.0
        combined_odds *= odds
        if leg.get("_stats_first_odds"):
            has_stats_first = True
    combined_odds = round(combined_odds, 2)

    # Stake: use worst probability/safety among legs for Kelly
    min_safety = min(
        ((_bm(leg).get("safety_score") or 0.5) for leg in legs),
        default=0.5,
    )
    min_prob = min(
        ((_bm(leg).get("probability") or _bm(leg).get("safety_score") or 0.5)
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
    if has_stats_first:
        coupon["stats_first"] = True

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
            (_bm(l).get("probability") if _bm(l).get("probability") is not None
             else _bm(l).get("safety_score", 0.5)
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
        "sort_key": lambda p: -(_bm(p).get("safety_score") or 0),
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
        "sort_key": lambda p: -(_bm(p).get("safety_score") or 0),
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
    # Include top-safety picks even without odds (R10 stats-first principle).
    # Picks with real odds are used directly; picks without get theoretical odds.
    odds_approved = [p for p in approved if ((p.get("odds") or {}).get("market_best") or 0) > 1.0]

    # Always include top-safety picks (regardless of odds availability)
    # Sort all by safety, take top N that aren't already in odds_approved
    sorted_by_safety = sorted(
        approved,
        key=lambda p: (_bm(p).get("safety_score") or 0),
        reverse=True,
    )
    # Merge: all odds picks + top-safety picks (up to 20 total)
    odds_keys = {_event_key(p) for p in odds_approved}
    for p in sorted_by_safety:
        if len(odds_approved) >= 20:
            break
        ek = _event_key(p)
        if ek in odds_keys:
            continue
        if not _bm(p).get("safety_score"):
            continue
        odds_keys.add(ek)
        # Assign theoretical odds = 1/safety (R10)
        safety = (_bm(p).get("safety_score") or 0.5)
        p.setdefault("odds", {})["market_best"] = round(1.0 / max(safety, 0.1), 2)
        p["_stats_first_odds"] = True
        p["odds_source"] = "estimated"
        odds_approved.append(p)

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

    for k in range(min_legs, max_legs + 1):  # 2-leg up to max_legs combos
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
        avg_safety = sum((_bm(l).get("safety_score") or 0) for l in legs) / max(len(legs), 1)
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
# Pattern D: Concentration warnings (May 2026 post-mortem)
# ---------------------------------------------------------------------------

def compute_concentration_warnings(
    all_coupons: list[dict], bankroll: float, daily_cap: float
) -> list[dict]:
    """Detect picks appearing in multiple coupons and compute max exposure.

    Returns list of warnings with pick details and exposure calculations.
    If same pick is in >2 coupons, or exposure >25% of daily budget, flag it.
    BLOCKING: If same event in >2 core coupons (not combos), the last ones are
    downgraded to combo-only to prevent correlated catastrophic loss.
    """
    # Map event_key → list of (coupon_id, stake, is_core)
    pick_coupons: dict[str, list[tuple[str, float, bool]]] = {}
    pick_display: dict[str, str] = {}  # event_key → display name

    for coupon in all_coupons:
        cid = coupon.get("id", "?")
        stake = coupon.get("stake", 0)
        is_core = "COMBO" not in cid.upper()
        for leg in coupon.get("legs", []):
            ek = _event_key(leg)
            pick_coupons.setdefault(ek, []).append((cid, stake, is_core))
            if ek not in pick_display:
                home = leg.get("home_team", "?")
                away = leg.get("away_team", "?")
                pick_display[ek] = f"{home} vs {away}"

    warnings = []
    max_exposure_pct = 0.25  # 25% of daily cap

    for ek, appearances in pick_coupons.items():
        if len(appearances) <= 1:
            continue

        total_exposure = sum(stake for _, stake, _ in appearances)
        coupon_ids = [cid for cid, _, _ in appearances]
        core_count = sum(1 for _, _, is_core in appearances if is_core)
        exposure_pct = total_exposure / daily_cap if daily_cap > 0 else 0

        warning = {
            "event": pick_display.get(ek, ek),
            "event_key": ek,
            "coupon_ids": coupon_ids,
            "appearances": len(appearances),
            "core_appearances": core_count,
            "total_exposure_pln": round(total_exposure, 2),
            "exposure_pct_of_daily": round(exposure_pct * 100, 1),
            "flagged": core_count > 1 or exposure_pct > max_exposure_pct,
        }

        if warning["flagged"]:
            if core_count > 1:
                warning["recommendation"] = (
                    f"🚫 BLOKADA: {pick_display.get(ek, ek)} w {core_count} kuponach CORE! "
                    f"Każde wydarzenie max 1× w core. Usuń z: {', '.join(cid for cid, _, ic in appearances if ic)}"
                )
            else:
                warning["recommendation"] = (
                    f"⚠️ KONCENTRACJA: {pick_display.get(ek, ek)} w {len(appearances)} kuponach "
                    f"({total_exposure:.2f} PLN = {exposure_pct:.0%} budżetu). "
                    f"Wybierz TYLKO JEDEN z: {', '.join(coupon_ids)}"
                )

        warnings.append(warning)

    # Sort: most concentrated first
    warnings.sort(key=lambda w: -w["total_exposure_pln"])
    return warnings


# ---------------------------------------------------------------------------
# Pattern F: Line sensitivity tables (May 2026 post-mortem)
# ---------------------------------------------------------------------------

# Sports where Betclic commonly offers different lines than pipeline suggests
LINE_SENSITIVE_SPORTS = frozenset([
    "basketball", "tennis", "volleyball",
])


def compute_line_sensitivity_tables(approved: list[dict]) -> list[dict]:
    """For picks in line-sensitive sports, generate P(hit) tables for alternative lines.

    Shows how probability changes ±1, ±2, ±3 from the pipeline line so the user
    can make informed decisions when Betclic offers a different line.
    """
    tables = []

    for pick in approved:
        sport = (pick.get("sport") or "").lower()
        if sport not in LINE_SENSITIVE_SPORTS:
            continue

        best = pick.get("best_market") or {}
        line = best.get("line")
        safety = best.get("safety_score", 0)
        l10_avg = best.get("l10_avg") or best.get("combined_avg")
        direction = (best.get("direction") or "").upper()
        probability = best.get("probability")

        if not line or not l10_avg:
            continue

        # Generate alternative lines: ±0.5, ±1, ±1.5, ±2
        steps = [0, 0.5, 1.0, 1.5, 2.0]
        alt_lines = []

        for step in steps:
            for sign in (1, -1):
                if step == 0 and sign == -1:
                    continue  # Don't duplicate the base line
                alt_line = line + (step * sign)
                if alt_line <= 0:
                    continue

                # Estimate P(hit) using Poisson approximation
                # P(Over X) ≈ based on distance from mean
                if l10_avg > 0:
                    if direction == "OVER":
                        # As line goes up, probability decreases
                        # Simple logistic approximation from normal distribution
                        z = (alt_line - l10_avg) / max(l10_avg * 0.25, 1.0)
                        p_hit = max(0.05, min(0.95, 0.5 * (1.0 - _erf_approx(z / 1.414))))
                    else:
                        # UNDER: as line goes up, probability increases
                        z = (l10_avg - alt_line) / max(l10_avg * 0.25, 1.0)
                        p_hit = max(0.05, min(0.95, 0.5 * (1.0 - _erf_approx(z / 1.414))))
                else:
                    p_hit = safety  # fallback

                min_odds = round(1.0 / p_hit, 2) if p_hit > 0 else 99.0

                # Recommendation
                if p_hit >= 0.75:
                    rec = "✅ PEWNY"
                elif p_hit >= 0.60:
                    rec = "✅ DOBRY"
                elif p_hit >= 0.50:
                    rec = "⚠️ MARGINALNY"
                else:
                    rec = "❌ NIE STAWIAJ"

                alt_lines.append({
                    "line": alt_line,
                    "p_hit": round(p_hit, 3),
                    "min_odds": min_odds,
                    "recommendation": rec,
                    "is_pipeline_line": (step == 0),
                })

        # Sort by line value
        alt_lines.sort(key=lambda x: x["line"])

        tables.append({
            "event": f"{pick.get('home_team', '?')} vs {pick.get('away_team', '?')}",
            "sport": sport,
            "market": best.get("name", "?"),
            "direction": direction,
            "pipeline_line": line,
            "l10_avg": round(l10_avg, 1),
            "alternatives": alt_lines,
        })

    return tables


def _erf_approx(x: float) -> float:
    """Approximate error function for P(hit) estimation.

    Abramowitz and Stegun approximation (max error 1.5×10⁻⁷).
    """
    sign = 1 if x >= 0 else -1
    x = abs(x)
    t = 1.0 / (1.0 + 0.3275911 * x)
    y = 1.0 - (
        (((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592
    ) * t * (2.718281828 ** (-x * x))
    return sign * y


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def _filter_past_events(picks: list) -> list:
    """Remove events whose kickoff has already passed."""
    now = datetime.now(tz=zoneinfo.ZoneInfo("UTC"))
    future = []
    for p in picks:
        ko = p.get("kickoff", "")
        if not ko:
            future.append(p)
            continue
        try:
            dt = datetime.fromisoformat(ko)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=zoneinfo.ZoneInfo("UTC"))
            if dt > now:
                future.append(p)
        except (ValueError, TypeError):
            future.append(p)
    return future


def _filter_quality(picks: list, tier: str = "core") -> tuple[list, list]:
    """Filter picks by data quality for coupon construction.
    
    Returns (quality_picks, demoted_picks).
    Demoted picks go to extended pool with quality warnings.
    
    Core tier requirements:
    - source != "db-synthetic" 
    - markets_evaluated >= 3
    - hit_rate > 50% (not a coin flip)
    - line is not solely from STANDARD_MARKET_LINES defaults
    """
    quality = []
    demoted = []
    
    for pick in picks:
        best = pick.get("best_market") or {}
        source = best.get("source", "")
        # Only check markets_evaluated when the field EXPLICITLY exists in the pick.
        # Absent field = legacy data or pre-S3 stage (not yet tracked) → don't penalize.
        # Explicit 0 = S3 ran but found NOTHING → flag as zero markets.
        _has_market_count = "market_count" in pick or "markets_evaluated" in pick
        markets_eval = pick.get("market_count") or pick.get("markets_evaluated", 0) or 0
        hit_rate_str = best.get("hit_rate_l10", "")
        line_verified = not pick.get("_stats_first_odds", False)
        
        # Parse hit rate using existing _safe_float helper (handles fractions like "5/10")
        hit_rate_val = _safe_float(hit_rate_str, 0.0)
        
        reasons = []
        
        # Check synthetic source
        if source == "db-synthetic":
            reasons.append("⚠️ SYNTETYCZNE: brak prawdziwych danych per-mecz")
        
        # Check minimum markets evaluated — only when field explicitly exists
        # Sport-specific minimums (tennis=2, volleyball=2, others=3)
        _sport = (pick.get("sport") or "").lower()
        _min_mkts = {"football": 3, "basketball": 3, "tennis": 2, "volleyball": 2, "hockey": 3}.get(_sport, 2)
        if _has_market_count:
            if markets_eval < _min_mkts and markets_eval > 0:
                reasons.append(f"⚠️ MAŁO RYNKÓW: {markets_eval}/{_min_mkts} wymagane")
            elif markets_eval == 0:
                reasons.append("⚠️ ZERO RYNKÓW: brak analizy statystycznej")
        
        # Check coin-flip hit rate
        if hit_rate_val > 0 and hit_rate_val <= 0.50:
            reasons.append(f"⚠️ COIN FLIP: {hit_rate_str} (≤50% = brak przewagi)")
        
        if reasons and tier == "core":
            pick["_quality_demoted"] = True
            pick["_quality_reasons"] = reasons
            demoted.append(pick)
        else:
            quality.append(pick)
    
    return quality, demoted

def build_coupons(gate_results: dict, config: dict) -> dict:
    """Main entry: build coupons from gate results.

    Input: gate_results dict from gate_checker.py with keys:
        - gate_results.approved: list of candidates that passed full gate
        - gate_results.extended_pool: candidates with EV>0 but gate-failed
          (data quality < FULL, ZT rules triggered, etc.). Shown to user as
          Watch List ("ROZSZERZONY WYBÓR") — never auto-rejected (R3).
        - gate_results.rejected: negative EV or phantom fixtures

    Returns full coupons data structure for output.
    """
    date = gate_results.get("date", datetime.now().strftime("%Y-%m-%d"))
    gr = gate_results.get("gate_results", {})
    all_approved = _filter_past_events(gr.get("approved", []))
    extended_pool = _filter_past_events(gr.get("extended_pool", []))
    rejected = gr.get("rejected", [])

    # Quality gate: filter synthetic/insufficient data from core coupons (ERROR 6 fix)
    all_approved, quality_demoted = _filter_quality(all_approved, tier="core")
    if quality_demoted:
        for p in quality_demoted:
            p["extended_pool_reason"] = "; ".join(p.get("_quality_reasons", ["quality filter"]))
        extended_pool.extend(quality_demoted)
        out.info(f"Quality filter: {len(quality_demoted)} picks demoted to extended pool "
                 f"(synthetic/insufficient/coin-flip)")

    # Assign risk_tier from safety if missing (JSON gate results don't always have it)
    for p in all_approved:
        if not p.get("risk_tier"):
            s = (_bm(p).get("safety_score") or 0)
            if s >= 0.55:
                p["risk_tier"] = "LR"
            elif s >= 0.40:
                p["risk_tier"] = "MS"
            else:
                p["risk_tier"] = "HR"

    # Split by advisory tier for tiered coupon construction
    strong_picks = [p for p in all_approved if p.get("advisory_tier") == "STRONG"]
    moderate_picks = [p for p in all_approved if p.get("advisory_tier") == "MODERATE"]
    weak_picks = [p for p in all_approved if p.get("advisory_tier") in ("WEAK", "FLAGGED")]
    # Legacy: picks without advisory_tier treated as MODERATE (backward compat)
    untiered = [p for p in all_approved if not p.get("advisory_tier")]
    moderate_picks.extend(untiered)

    # Primary coupon construction uses STRONG + MODERATE
    approved = strong_picks + moderate_picks
    # Sort by safety_score desc so best-analyzed picks come first
    approved.sort(key=lambda p: (_bm(p).get("safety_score") or 0), reverse=True)
    # VALUE/DISCOVERY picks are shown separately
    discovery_picks = weak_picks

    bankroll = config.get("bankroll_pln", config.get("working_bankroll_pln", 50.0))
    alloc_range = config.get("daily_exposure_range", config.get("suggested_daily_allocation_range_pln", [5.0, 15.0]))

    result = {
        "date": date,
        "bankroll": bankroll,
        "daily_allocation_range": alloc_range,
        "approved_count": len(all_approved),
        "strong_count": len(strong_picks),
        "moderate_count": len(moderate_picks),
        "discovery_count": len(discovery_picks),
        "core_coupons": [],
        "combos": [],
        "singles": [],
        "discovery_singles": [],
        "banker": None,
        "extended_pool": extended_pool,
        "rejected": rejected,
        "discovery_pool": discovery_picks,
        "no_bet": False,
        "no_bet_reason": None,
    }

    # SINGLES — always generate for every approved pick
    date_str = _extract_date(approved) if approved else datetime.now().strftime("%Y%m%d")
    max_singles = config.get("max_singles", 50)
    singles = []
    for i, pick in enumerate(approved[:max_singles], 1):
        odds_val = (pick.get("odds") or {}).get("market_best", 0) or 0
        safety = (pick.get("best_market") or {}).get("safety_score", 0.5)
        prob = (pick.get("best_market") or {}).get("probability")
        if odds_val <= 1.0:
            # Stats-first mode: no odds available — include with placeholder
            single = {
                "id": f"CP-{date_str}-SINGLE{i}",
                "tier": pick.get("risk_tier", "MS"),
                "legs": [pick],
                "combined_odds": 0.0,
                "stake": 0.0,
                "potential_return": 0.0,
                "stress_test": stress_test_coupon({"legs": [pick]}),
                "correlation_flags": [],
                "is_single": True,
                "stats_first": True,
            }
            singles.append(single)
            continue
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

    # Task 1.4: Market diversity — max identical thesis (market+direction+line)
    max_identical = config.get("max_identical_thesis", 3)
    from collections import Counter
    thesis_counts: dict[str, list] = {}
    for s in singles:
        leg = s["legs"][0] if s.get("legs") else {}
        bm = _bm(leg)
        thesis_key = f"{bm.get('name', '')}|{bm.get('direction', '')}|{bm.get('line', '')}"
        thesis_counts.setdefault(thesis_key, []).append(s)
    trimmed_singles = []
    for thesis_key, items in thesis_counts.items():
        if len(items) > max_identical and thesis_key != "||":
            trimmed_singles.extend(sorted(items, key=lambda x: -(_bm(x["legs"][0]).get("safety_score", 0)))[:max_identical])
            excess = sorted(items, key=lambda x: -(_bm(x["legs"][0]).get("safety_score", 0)))[max_identical:]
            for ex in excess:
                ex["_trimmed_reason"] = "identical_thesis"
            extended_pool.extend([ex["legs"][0] for ex in excess])
            out.warning(f"⚠️ {len(excess)} singles with identical thesis '{thesis_key}' — trimmed to {max_identical}")
        else:
            trimmed_singles.extend(items)
    singles = trimmed_singles

    result["singles"] = singles

    # BANKER: highest safety score pick (from picks with odds, or any if all stats-first)
    if singles:
        with_odds = [s for s in singles if not s.get("stats_first")]
        banker_pool = with_odds if with_odds else singles
        banker = max(banker_pool, key=lambda s: (_bm(s["legs"][0])).get("safety_score", 0))
        banker["is_banker"] = True
        result["banker"] = banker

    if len(approved) < 1:
        result["no_bet"] = True
        result["no_bet_reason"] = "Brak zatwierdzonych typów."
        return result

    # Store approved for markdown writer (market matrix)
    result["_approved"] = approved

    # Sort by data quality (FULL > PARTIAL > MINIMAL) then safety score
    quality_order = {"FULL": 0, "PARTIAL": 1, "MINIMAL": 2}
    approved.sort(key=lambda c: (
        quality_order.get(
            (c.get("data_quality") or {}).get("label", "MINIMAL")
            if isinstance(c.get("data_quality"), dict)
            else c.get("data_quality", "MINIMAL"),
            2,
        ),
        -(_bm(c).get("safety_score", 0)),
    ))

    # Event deduplication — ensure unique events across core coupons
    used_events: set[str] = set()
    deduped_approved = []
    for c in approved:
        ek = _event_key(c)
        if ek in used_events:
            continue
        used_events.add(ek)
        deduped_approved.append(c)
    approved = deduped_approved

    # MINIMAL quality candidates → Extended Pool only, not core coupons (Task 1.3)
    core_eligible = []
    minimal_moved = 0
    for c in approved:
        dq = c.get("data_quality")
        # If data_quality is absent (legacy/test picks), treat as FULL (already gate-approved)
        label = (dq.get("label", "FULL") if isinstance(dq, dict) else dq) if dq else "FULL"
        if label == "MINIMAL":
            minimal_moved += 1
            extended_pool.append(c)
        else:
            core_eligible.append(c)
    if minimal_moved:
        out.info(f"📊 {minimal_moved} candidates moved to Extended Pool (MINIMAL data quality)")
    if not core_eligible:
        core_eligible = approved  # Fallback: if ALL are MINIMAL, use them anyway (stats-first)

    # Build core portfolio (requires ≥2 picks)
    core = assign_picks_to_core(core_eligible, config)
    result["core_coupons"] = core

    # Build combo menu (requires ≥2 picks)
    combos = generate_combos(core_eligible, config)
    result["combos"] = combos

    # DISCOVERY SINGLES — weak/flagged picks with discounted stakes
    # These are shown to the user for manual evaluation
    discovery_singles = []
    for i, pick in enumerate(discovery_picks[:30], 1):
        odds_val = (pick.get("odds") or {}).get("market_best", 0) or 0
        safety = (pick.get("best_market") or {}).get("safety_score", 0.5)
        prob = (pick.get("best_market") or {}).get("probability")
        if odds_val <= 1.0:
            disc_single = {
                "id": f"CP-{date_str}-DISC{i}",
                "tier": "DISCOVERY",
                "advisory_tier": pick.get("advisory_tier", "WEAK"),
                "legs": [pick],
                "combined_odds": 0.0,
                "stake": 0.0,
                "potential_return": 0.0,
                "stress_test": stress_test_coupon({"legs": [pick]}),
                "correlation_flags": [],
                "is_single": True,
                "stats_first": True,
            }
        else:
            # Discounted stake: 0.25× for WEAK, 0× for FLAGGED (show only)
            tier_discount = 0.25 if pick.get("advisory_tier") == "WEAK" else 0.0
            base_stake = compute_stake(odds_val, safety, bankroll, "HR", probability=prob)
            disc_stake = round(base_stake * tier_discount, 2) if tier_discount > 0 else 0.0
            disc_single = {
                "id": f"CP-{date_str}-DISC{i}",
                "tier": "DISCOVERY",
                "advisory_tier": pick.get("advisory_tier", "WEAK"),
                "legs": [pick],
                "combined_odds": round(odds_val, 2),
                "stake": disc_stake,
                "potential_return": round(disc_stake * odds_val, 2),
                "stress_test": stress_test_coupon({"legs": [pick]}),
                "correlation_flags": [],
                "is_single": True,
            }
        discovery_singles.append(disc_single)
    result["discovery_singles"] = discovery_singles

    # ENFORCE DAILY CAP: trim coupons to stay within daily_exposure_range
    max_daily = alloc_range[1] if isinstance(alloc_range, list) and len(alloc_range) > 1 else 15.0
    core_spend = sum(c.get("stake", 0) for c in core)
    combo_spend = sum(c.get("stake", 0) for c in combos)
    singles_spend = sum(c.get("stake", 0) for c in singles)
    total_spend = core_spend + combo_spend + singles_spend

    if total_spend > max_daily:
        # Task 1.5: Budget hard cap — trim lowest-priority items to Extended Pool
        out.warning(f"⚠️ Budget cap {max_daily:.2f} PLN exceeded ({total_spend:.2f}). Trimming...")
        budget_remaining = max_daily
        # Keep core coupons (highest priority)
        kept_core = []
        for c in core:
            if budget_remaining >= c.get("stake", 0):
                kept_core.append(c)
                budget_remaining -= c.get("stake", 0)
            else:
                for leg in c.get("legs", []):
                    leg["_budget_trimmed"] = True
                    extended_pool.append(leg)
        core = kept_core
        result["core_coupons"] = core
        # Combos are ALTERNATIVES to core, not additive — always keep them as options
        # User picks core OR combo, not both. Show all, let user decide.
        result["combos"] = combos
        # Singles: keep those with real stakes that fit
        kept_singles = []
        trimmed_count = 0
        for s in singles:
            if s.get("stats_first") or s.get("stake", 0) == 0:
                kept_singles.append(s)  # stats-first singles cost nothing
            elif budget_remaining >= s.get("stake", 0):
                kept_singles.append(s)
                budget_remaining -= s.get("stake", 0)
            else:
                trimmed_count += 1
                for leg in s.get("legs", []):
                    leg["_budget_trimmed"] = True
                    extended_pool.append(leg)
        if trimmed_count:
            out.warning(f"  → Trimmed {trimmed_count} singles to Extended Pool (budget cap)")
        singles = kept_singles
        result["singles"] = singles

    # Task 1.6: Event concentration limit — no single event in >5 coupons
    max_event_reuse = config.get("max_event_reuse_across_coupons", 5)
    all_coupons_check = core + combos
    event_usage: dict[str, int] = {}
    for coupon in all_coupons_check:
        for leg in coupon.get("legs", []):
            ek = _event_key(leg)
            event_usage[ek] = event_usage.get(ek, 0) + 1
    concentration_warnings = []
    for ek, count in event_usage.items():
        if count > 3:
            concentration_warnings.append(f"⚠️ KONCENTRACJA: {ek} pojawia się w {count} kuponach")
        if count > max_event_reuse:
            out.warning(f"⚠️ Event {ek} in {count} coupons (max {max_event_reuse})")
    result["_concentration_warnings_extra"] = concentration_warnings

    # Task 1.8: Same-competition correlation check
    comp_correlation_warnings = []
    for coupon in all_coupons_check:
        legs = coupon.get("legs", [])
        comps = [leg.get("competition") or leg.get("league") or "" for leg in legs]
        from collections import Counter as _Counter
        comp_counts = _Counter(c for c in comps if c)
        for comp, count in comp_counts.items():
            if count >= 2:
                comp_correlation_warnings.append({
                    "type": "same_competition_correlation",
                    "competition": comp,
                    "count": count,
                    "coupon_id": coupon.get("id", "?"),
                })
    if comp_correlation_warnings:
        result["_comp_correlation_warnings"] = comp_correlation_warnings
        for w in comp_correlation_warnings[:5]:
            out.warning(f"⚠️ KORELACJA: {w['count']} mecze z {w['competition']} w kuponie {w['coupon_id']}")

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
        "bankroll_after": round(bankroll - core_spend - combo_spend - singles_spend, 2),
        "total_potential_return": round(total_return, 2),
        "best_case": round(best_case, 2),
        "realistic": realistic,
    }

    # Odds source tracking — warn when all odds are estimated
    all_picks = [leg for c in core + combos for leg in c.get("legs", [])] + singles
    source_counts = {"estimated": 0, "api": 0, "betclic": 0}
    for p in all_picks:
        src = p.get("odds_source", "estimated")
        source_counts[src] = source_counts.get(src, 0) + 1
    result["summary"]["odds_sources"] = source_counts
    total_picks = sum(source_counts.values())
    if total_picks > 0 and source_counts.get("estimated", 0) == total_picks:
        result["summary"]["odds_warning"] = "⚠️ ALL odds are estimated (1/safety). Verify on Betclic before placing."

    # Placement order: sort by tier safety (LR first)
    all_coupons = core + combos
    all_coupons.sort(key=lambda c: (TIER_ORDER.get(c.get("tier", "MS"), 1), -c.get("stress_test", {}).get("p_coupon", 0)))
    result["placement_order"] = [c["id"] for c in all_coupons]

    # --- Pattern D: Concentration warnings ---
    result["concentration_warnings"] = compute_concentration_warnings(
        core + combos, bankroll, max_daily
    )

    # --- Pattern F: Line sensitivity tables ---
    result["line_sensitivity"] = compute_line_sensitivity_tables(approved)

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

    # Opponent blocker warning
    if best.get("opponent_blocker"):
        parts.append("⛔OPP")

    return f"{' · '.join(parts)} {status}" if parts else status


def _market_matrix_rows(approved: list, extended: list) -> list[str]:
    """Build full market matrix rows."""
    rows = []
    # Filter out empty entries with no analysis before displaying
    all_picks = [p for p in (list(approved) + list(extended)) if p.get("best_market") and p.get("best_market").get("name")]
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
        line_val = best.get("line")
        combined_avg = best.get("combined_avg") or best.get("l10_avg")
        if line_val is not None and direction:
            direction = f"{direction} {line_val}"
        if combined_avg is not None:
            direction = f"{direction} (śr.{float(combined_avg):.1f})"

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
        if banker.get("stats_first"):
            lines.append(f"**Stawka:** ➜Betclic | **Kurs:** ➜Betclic | **Zwrot:** ➜Betclic")
        else:
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
            if s.get("stats_first"):
                lines.append(
                    f"| {i} | {s['id']}{banker_mark} | {desc} "
                    f"| ➜Betclic | ➜Betclic "
                    f"| ➜Betclic | {s['tier']} |"
                )
            else:
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

    # --- Pattern D: Concentration warnings in output ---
    concentration = coupons_data.get("concentration_warnings", [])
    flagged_concentration = [w for w in concentration if w.get("flagged")]
    if flagged_concentration:
        lines.append("## ⚠️ OSTRZEŻENIE KONCENTRACJI")
        lines.append("")
        lines.append("| Pick | Pojawia się w kuponach | Max ekspozycja | % budżetu |")
        lines.append("|------|----------------------|----------------|-----------|")
        for w in flagged_concentration:
            lines.append(
                f"| {w['event']} | {', '.join(w['coupon_ids'])} "
                f"| {w['total_exposure_pln']:.2f} PLN "
                f"| {w['exposure_pct_of_daily']:.0f}% |"
            )
        lines.append("")
        lines.append("> **Zalecenie:** Jeśli stawiasz wszystkie kupony powyżej, "
                     "wybierz TYLKO JEDEN z nakładających się kuponów aby ograniczyć ryzyko.")
        lines.append("")

    # --- Pattern F: Line sensitivity tables in output ---
    line_sens = coupons_data.get("line_sensitivity", [])
    if line_sens:
        lines.append("## TABELA WRAŻLIWOŚCI NA LINIĘ")
        lines.append("")
        lines.append("> Jeśli Betclic oferuje inną linię niż pipeline, "
                     "sprawdź P(hit) poniżej przed postawieniem.")
        lines.append("")
        for table in line_sens:
            lines.append(f"### {table['event']} — {table['market']} ({table['direction']})")
            lines.append(f"L10 średnia: {table['l10_avg']} | Linia pipeline: {table['pipeline_line']}")
            lines.append("")
            lines.append("| Linia | P(hit) | Min kurs | Rekomendacja |")
            lines.append("|-------|--------|----------|--------------|")
            for alt in table["alternatives"]:
                mark = " ← pipeline" if alt.get("is_pipeline_line") else ""
                lines.append(
                    f"| {alt['line']:.1f} | {alt['p_hit']:.0%} "
                    f"| {alt['min_odds']:.2f} | {alt['recommendation']}{mark} |"
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

    # BETCLIC MARKET AVAILABILITY (if validation data exists)
    betclic_validation = coupons_data.get("betclic_market_validation")
    if betclic_validation:
        lines.append("## ⚠️ WALIDACJA RYNKÓW BETCLIC")
        lines.append("")
        lines.append("> Rynki zweryfikowane automatycznie na betclic.pl. "
                     "Statystyki (rożne, kartki, strzały) dostępne tylko dla meczów z zakładką 'Statystyki'.")
        lines.append("")
        unavailable = [v for v in betclic_validation if v.get("betclic_available") is False]
        available = [v for v in betclic_validation if v.get("betclic_available") is True]
        unknown = [v for v in betclic_validation if v.get("betclic_available") is None]
        if unavailable:
            lines.append("### ❌ RYNKI NIEDOSTĘPNE na Betclic")
            lines.append("")
            lines.append("| Wydarzenie | Rynek | Problem |")
            lines.append("|------------|-------|---------|")
            for v in unavailable:
                lines.append(f"| {v.get('event', '?')} | {v.get('market', '?')} | {v.get('betclic_note', '-')} |")
            lines.append("")
        if unknown:
            lines.append(f"### ⚠️ Nieokreślone ({len(unknown)} typów)")
            lines.append("")
            lines.append("Nie udało się potwierdzić dostępności — zweryfikuj ręcznie w aplikacji.")
            lines.append("")
        if available:
            lines.append(f"### ✅ Potwierdzone ({len(available)} typów)")
            lines.append("")
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
            from bet.db.repositories import FixtureRepo, SportRepo, TeamRepo
            fixture_repo = FixtureRepo(conn)
            sport_repo = SportRepo(conn)
            team_repo = TeamRepo(conn)

            # Build sport name→id cache
            _sport_cache: dict[str, int] = {}
            for s in sport_repo.get_all():
                _sport_cache[s.name] = s.id

            def _resolve_fixture_id(
                home: str, away: str, sport: str, date_str: str
            ) -> int | None:
                """Resolve fixture_id by team names + sport + date."""
                sid = _sport_cache.get(sport)
                if not sid:
                    return None
                try:
                    f = fixture_repo.get_by_teams_and_date(
                        home, away, date_str, sid
                    )
                    return f.id if f else None
                except Exception:
                    return None

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
                        placed_at=_NOW(),
                        version=1,
                    )
                    db_coupon_id = repo.create_coupon(coupon)

                    # Persist individual bets/legs
                    for leg in legs:
                        home_team = leg.get("home_team", "?")
                        away_team = leg.get("away_team", "?")
                        sport = leg.get("sport", "")
                        fixture_id = _resolve_fixture_id(
                            home_team, away_team, sport, date
                        )
                        best_mkt = leg.get("best_market") or {}
                        # Populate stats_detail for learning
                        stats_detail = {
                            "safety_score": best_mkt.get("safety_score"),
                            "l10_avg": best_mkt.get("combined_avg"),
                            "h2h_avg": best_mkt.get("h2h_avg"),
                            "hit_rate_l10": best_mkt.get("hit_rate_l10"),
                            "hit_rate_h2h": best_mkt.get("hit_rate_h2h"),
                            "three_way": leg.get("three_way_alignment"),
                            "margin": best_mkt.get("margin"),
                            "markets_evaluated": leg.get("markets_evaluated", 0),
                            "rank": best_mkt.get("rank", 1),
                            "line": best_mkt.get("line"),
                            "direction": best_mkt.get("direction"),
                        }
                        bet = Bet(
                            id=None,
                            coupon_id=db_coupon_id,
                            fixture_id=fixture_id,
                            sport=sport,
                            event_name=f"{home_team} vs {away_team}",
                            market=best_mkt.get("name", ""),
                            selection=best_mkt.get("direction", ""),
                            odds=(leg.get("odds") or {}).get("market_best", 0) or 0,
                            safety_score=best_mkt.get("safety_score"),
                            hit_rate=best_mkt.get("hit_rate_l10"),
                            status="pending",
                            market_pl=best_mkt.get("market_pl", ""),
                            stats_detail=stats_detail,
                        )
                        bet_id = repo.add_bet(bet)

                        # Create decision snapshot for learning
                        if fixture_id and bet_id:
                            try:
                                from bet.db.models import DecisionSnapshot
                                from bet.db.repositories import DecisionSnapshotRepo, AnalysisRawDataRepo

                                snap_repo = DecisionSnapshotRepo(conn)
                                # Load raw analysis data for this fixture
                                raw_repo = AnalysisRawDataRepo(conn)
                                raw = raw_repo.get_by_fixture(fixture_id, date)

                                # Build all markets considered
                                all_markets = leg.get("ranking", [])
                                if not all_markets and raw:
                                    all_markets = raw.per_market_details_json

                                # Build reasoning
                                reasoning = {
                                    "chosen_because": f"Highest safety score ({best_mkt.get('safety_score')}) among {leg.get('markets_evaluated', '?')} evaluated markets",
                                    "gate_score": leg.get("gate_score"),
                                    "gate_details": leg.get("gate_details"),
                                    "three_way_alignment": leg.get("three_way_alignment"),
                                    "ev": leg.get("ev"),
                                    "risk_tier": leg.get("risk_tier"),
                                }
                                if all_markets and len(all_markets) > 1:
                                    reasoning["runner_up"] = {
                                        "name": all_markets[1].get("name"),
                                        "safety_score": all_markets[1].get("safety_score"),
                                        "line": all_markets[1].get("line"),
                                    }

                                # Build flip conditions
                                flip_conditions = {}
                                if all_markets and len(all_markets) >= 2:
                                    gap = (best_mkt.get("safety_score") or 0) - (all_markets[1].get("safety_score") or 0)
                                    flip_conditions["safety_gap_to_runner_up"] = round(gap, 3)
                                    flip_conditions["runner_up_market"] = all_markets[1].get("name", "")
                                line = best_mkt.get("line")
                                combined_avg = best_mkt.get("combined_avg")
                                if line and combined_avg and best_mkt.get("direction") == "OVER":
                                    flip_conditions["l10_avg_flip_threshold"] = line
                                    flip_conditions["current_margin_over_line"] = round(combined_avg - line, 2)

                                # Build thresholds
                                thresholds = {
                                    "min_safety_score": config.get("min_safety_score", 0.45),
                                    "min_gate_score": 10,
                                    "min_margin": 0.05,
                                }

                                snapshot = DecisionSnapshot(
                                    id=None,
                                    bet_id=bet_id,
                                    fixture_id=fixture_id,
                                    betting_date=date,
                                    chosen_market=best_mkt.get("name", ""),
                                    chosen_line=best_mkt.get("line"),
                                    chosen_direction=best_mkt.get("direction", ""),
                                    safety_score=best_mkt.get("safety_score"),
                                    all_markets_considered_json=all_markets or [],
                                    reasoning_json=reasoning,
                                    thresholds_json=thresholds,
                                    flip_conditions_json=flip_conditions,
                                    team_a_snapshot_json=raw.team_a_l10_json if raw else {},
                                    team_b_snapshot_json=raw.team_b_l10_json if raw else {},
                                    h2h_snapshot_json=raw.h2h_meetings_json if raw else {},
                                    three_way_check_json=leg.get("three_way_check"),
                                    created_at=_NOW(),
                                )
                                snap_repo.save(snapshot)
                            except Exception as e:
                                print(f"[coupon_builder] Decision snapshot failed for bet {bet_id}: {e}")
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
    from agent_output import AgentOutput, add_agent_args

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
    add_agent_args(parser)

    args = parser.parse_args()
    global out
    out = AgentOutput("s8_coupon", verbose=args.verbose, stop_on_error=args.stop_on_error)

    # V5: Input contract pre-check (warning-only, never blocks)
    _contract = AgentOutput.validate_input_contract("s8_coupons", args.date)
    if _contract["status"] != "OK":
        for _w in _contract.get("warnings", []):
            out.warning(f"Input contract: {_w}")
        for _m in _contract.get("missing", []):
            out.warning(f"Missing input: {_m}")

    # Load gate results — DB first, JSON fallback
    gate_results = None

    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            out.error(f"Gate results not found: {input_path}", recoverable=False)
            out.summary(verdict="FAILED", metrics={"error": f"Gate results not found: {input_path}"})
            sys.exit(1)
        with open(input_path, encoding="utf-8") as f:
            gate_results = json.load(f)
    else:
        # DB-first: load gate results from DB (R2)
        try:
            from db_data_loader import load_gate_results_from_db
            approved = load_gate_results_from_db(args.date, status="approved")
            extended = load_gate_results_from_db(args.date, status="extended")
            rejected = load_gate_results_from_db(args.date, status="rejected")
            if approved or extended:
                gate_results = {
                    "date": args.date,
                    "gate_results": {
                        "approved": approved or [],
                        "extended_pool": extended or [],
                        "rejected": rejected or [],
                    },
                    "summary": {
                        "approved_count": len(approved or []),
                        "extended_count": len(extended or []),
                        "rejected_count": len(rejected or []),
                    },
                }
                if args.verbose:
                    out.event("db_load", approved=len(approved or []), extended=len(extended or []))
                else:
                    print(f"[coupon_builder] DB: loaded {len(approved or [])} approved, {len(extended or [])} extended")
        except Exception as e:
            out.warning(f"DB read failed: {e}")

        # Fallback to JSON if DB missing or failed
        if gate_results is None:
            json_path = DATA_DIR / f"{args.date}_s7_gate_results.json"
            if json_path.exists():
                with open(json_path, encoding="utf-8") as f:
                    gate_results = json.load(f)
                if args.verbose:
                    gr = gate_results.get("gate_results", {})
                    out.event("json_load",
                              approved=len(gr.get("approved", [])),
                              extended=len(gr.get("extended_pool", [])))

        # Final fallback — should not reach here if JSON or DB worked
        if gate_results is None:
            out.error(f"Gate results not found for {args.date}. Run gate_checker.py first.", recoverable=False)
            out.summary(verdict="FAILED", metrics={"error": "Gate results not found"})
            sys.exit(1)

    # Load config
    config = load_config()

    # Build coupons
    coupons_data = build_coupons(gate_results, config)

    # Attach approved for markdown writer (not persisted to JSON)
    coupons_data["_approved"] = gate_results.get("gate_results", {}).get("approved", [])

    # Betclic market validation: load from today's validation file if exists
    betclic_validation_path = DATA_DIR / f"betclic_market_validation_{args.date}.json"
    if betclic_validation_path.exists():
        try:
            betclic_data = json.loads(betclic_validation_path.read_text(encoding="utf-8"))
            validation_results = betclic_data.get("validation")
            if validation_results:
                coupons_data["betclic_market_validation"] = validation_results
                unavailable = [v for v in validation_results if v.get("betclic_available") is False]
                if args.verbose:
                    out.event("betclic_validation",
                              total=len(validation_results),
                              unavailable=len(unavailable))
                
                # Hard-reject: remove picks from core that are betclic_unavailable
                # Track (event, market_type) pairs — not just event name
                unavailable_pairs = set()
                for v in validation_results:
                    if v.get("betclic_available") is False:
                        unavailable_pairs.add((v.get("event", "").lower(), v.get("market_type", "")))

                if unavailable_pairs and coupons_data.get("singles"):
                    filtered_singles = []
                    rejected_by_betclic = []
                    for s in coupons_data["singles"]:
                        event_str = f"{s.get('home_team', '')} - {s.get('away_team', '')}".lower()
                        pick_market = s.get("market_type", "")
                        is_unavailable = any(
                            pick_market == up_mt and (ue in event_str or event_str in ue)
                            for ue, up_mt in unavailable_pairs
                        )
                        if is_unavailable:
                            s["rejection_reason"] = "RYNEK NIEDOSTĘPNY NA BETCLIC"
                            rejected_by_betclic.append(s)
                        else:
                            filtered_singles.append(s)
                    if rejected_by_betclic:
                        coupons_data["singles"] = filtered_singles
                        # Add to extended pool
                        ext = coupons_data.setdefault("extended_pool", [])
                        ext.extend(rejected_by_betclic)
                        if args.verbose:
                            out.warning(f"Betclic filter: {len(rejected_by_betclic)} singles moved to Extended Pool")

        except Exception as e:
            if args.verbose:
                out.warning(f"Betclic validation load failed: {e}")

    # Write outputs
    write_coupon_markdown(coupons_data, args.date)
    write_coupon_json(coupons_data, args.date)

    # Structured summary
    if coupons_data.get("no_bet"):
        out.summary(
            verdict="NO_BET",
            metrics={"reason": coupons_data["no_bet_reason"]},
        )
        if not args.verbose:
            print(f"\n[coupon_builder] NO BET: {coupons_data['no_bet_reason']}")
    else:
        s = coupons_data["summary"]
        out.summary(
            verdict="OK",
            metrics={
                "singles": len(coupons_data.get("singles", [])),
                "core_coupons": len(coupons_data["core_coupons"]),
                "combos": len(coupons_data["combos"]),
                "core_spend": round(s["core_spend"], 2),
                "total_spend": round(s["total_spend"], 2),
                "potential_return": round(s["total_potential_return"], 2),
            },
        )
        if not args.verbose:
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
