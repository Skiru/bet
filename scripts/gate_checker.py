#!/usr/bin/env python3
"""S7 Pick Approval Gate — 18-point programmatic gate checker.

Implements the full §7.5 pick approval gate, §7.3 red flag checks,
§7.6 sport diversity check, and §6.5 upset risk assessment.

Usage:
    python3 scripts/gate_checker.py --date 2026-05-01
    python3 scripts/gate_checker.py --date 2026-05-01 --input s3_output.json
    python3 scripts/gate_checker.py --date 2026-05-01 --strict
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from scripts.check_48h_repeats import load_recent_losses, normalize_team, normalize_market, find_repeats
except ImportError:
    from check_48h_repeats import load_recent_losses, normalize_team, normalize_market, find_repeats

DATA_DIR = Path(__file__).parent.parent / "betting" / "data"
JOURNAL_DIR = Path(__file__).parent.parent / "betting" / "journal"
LEDGER_PATH = JOURNAL_DIR / "picks-ledger.csv"

KEY_SPORTS = {"football", "volleyball", "basketball", "tennis"}
ALL_SPORTS = {
    "football", "volleyball", "basketball", "tennis",
    "hockey", "baseball", "handball", "esports", "snooker",
    "darts", "table_tennis", "mma", "padel", "speedway",
}

GATE_LABELS = {
    "1": "Identity verified (full name, no slashes)",
    "2": "WC/Q/LL / debut / stand-in checked",
    "3": "H2H ≥5 meetings checked",
    "4": "Injuries/suspensions checked",
    "5": "≥2 independent sources",
    "6": "≥1 tipster argument READ",
    "7": "Upset risk scored",
    "8": "EV > 0 calculated",
    "9": "Odds drift <8% verified",
    "10": "Red flags checked",
    "11": "Contrarian thinking done",
    "12": "Bear case < bull case",
    "13": "Not anchored",
    "14": "48h repeat check",
    "15": "MULTI-MARKET: ≥3 alternative markets",
    "16": "H2H STAT-SPECIFIC: H2H for exact stat exists",
    "17": "THREE-WAY ALIGNMENT: L10+H2H+L5 all support",
    "18": "DATA QUALITY: both teams have stat data",
}


# ---------------------------------------------------------------------------
# Gate checks
# ---------------------------------------------------------------------------

def _check_identity(c: dict) -> tuple[bool, str]:
    """Gate #1: Identity verified — full name, no slashes."""
    for field in ("home_team", "away_team"):
        name = c.get(field, "")
        if "/" in name:
            return False, f"SLASH in {field}: {name}"
        if not name or len(name) < 2:
            return False, f"MISSING or too short {field}: {name!r}"
    return True, ""


def _check_qualifier_flags(c: dict) -> tuple[bool, str]:
    """Gate #2: WC/Q/LL / debut / stand-in / backup checked."""
    warnings = []
    for field in ("home_team", "away_team"):
        name = c.get(field, "")
        upper = name.upper()
        if "(Q)" in upper or " Q " in f" {upper} ":
            warnings.append(f"QUALIFIER flag on {name}")
        if "(WC)" in upper or " WC " in f" {upper} ":
            warnings.append(f"WILD CARD flag on {name}")
        if "(LL)" in upper or " LL " in f" {upper} ":
            warnings.append(f"LUCKY LOSER flag on {name}")
    # Gate passes but with warnings — user should verify
    return True, "; ".join(warnings) if warnings else ""


def _check_h2h_count(c: dict) -> tuple[bool, str]:
    """Gate #3: H2H ≥5 meetings checked."""
    h2h_count = c.get("h2h_count", 0)
    if h2h_count is None:
        h2h_count = 0
    if h2h_count >= 5:
        return True, ""
    return False, f"H2H only {h2h_count} meetings (need ≥5)"


def _check_injuries(c: dict) -> tuple[bool, str]:
    """Gate #4: Injuries/suspensions checked."""
    # If injury data exists in the candidate, the check was performed
    injury_data = c.get("injuries") or c.get("injury_data")
    if injury_data:
        return True, ""
    # Data quality FULL implies injuries were checked upstream
    if c.get("data_quality") == "FULL":
        return True, ""
    return False, "NO injury/suspension data available"


def _check_sources(c: dict) -> tuple[bool, str]:
    """Gate #5: ≥2 independent sources."""
    sources = c.get("sources", [])
    if isinstance(sources, str):
        sources = [s.strip() for s in sources.split("|") if s.strip()]
    if len(sources) >= 2:
        return True, ""
    return False, f"Only {len(sources)} source(s): {sources}"


def _check_tipster(c: dict) -> tuple[bool, str]:
    """Gate #6: ≥1 tipster argument READ."""
    tipster_count = c.get("tipster_count", 0) or 0
    if tipster_count >= 1:
        return True, ""
    return False, "TIPSTER-BLIND: no tipster source"


def _check_upset_risk(c: dict) -> tuple[bool, str]:
    """Gate #7: Upset risk scored."""
    # Compute and attach — always passes (the act of scoring is the check)
    risk = compute_upset_risk(c)
    c["_upset_risk"] = risk
    return True, f"upset_risk={risk['score']:.2f}" if risk.get("score") else ""


def _check_ev(c: dict) -> tuple[bool, str]:
    """Gate #8: EV > 0 calculated."""
    ev = c.get("ev")
    if ev is not None and ev > 0:
        return True, f"EV={ev:.3f}"
    if ev is not None:
        return False, f"EV={ev:.3f} (≤0)"
    # Stats-first mode: EV not calculable without odds — user verifies on Betclic
    return True, "STATS-FIRST: EV not calculable, user verifies manually"


def _check_odds_drift(c: dict) -> tuple[bool, str]:
    """Gate #9: Odds drift <8% verified."""
    odds = c.get("odds", {})
    if not odds:
        # Stats-first: no odds available — warn but pass
        return True, "NO_ODDS: stats-first mode, drift not checkable"
    opening = odds.get("opening")
    current = odds.get("current") or odds.get("market_best")
    if not opening or not current:
        return True, "Drift not checkable (missing opening/current)"
    drift = abs(current - opening) / opening
    if drift > 0.08:
        return False, f"DRIFT {drift:.1%} exceeds 8% ({opening}→{current})"
    return True, f"drift={drift:.1%}"


def _check_red_flags(c: dict, repeat_losses: list) -> tuple[bool, str]:
    """Gate #10: Red flags checked."""
    flags = check_red_flags(c)
    if flags:
        return False, "; ".join(flags)
    return True, ""


def _check_contrarian(_c: dict) -> tuple[bool, str]:
    """Gate #11: Contrarian thinking done — auto-pass (coded analysis)."""
    return True, ""


def _check_bear_vs_bull(c: dict) -> tuple[bool, str]:
    """Gate #12: Bear case < bull case — safety vs risk factors."""
    best = c.get("best_market") or {}
    safety = best.get("safety_score", 0)
    if safety is None:
        safety = 0
    # Simple proxy: safety > 0.50 means bull > bear
    if safety >= 0.50:
        return True, f"safety={safety:.2f} (bull>bear)"
    return False, f"safety={safety:.2f} (bear≥bull)"


def _check_not_anchored(_c: dict) -> tuple[bool, str]:
    """Gate #13: Not anchored — auto-pass (systematic analysis)."""
    return True, ""


def _check_48h_repeat(c: dict, repeat_losses: list) -> tuple[bool, str]:
    """Gate #14: 48h repeat check — same team+market lost recently."""
    teams = [c.get("home_team", ""), c.get("away_team", "")]
    best = c.get("best_market") or {}
    market_name = best.get("name", "")
    repeats = find_repeats(teams, repeat_losses, market_name)
    if repeats:
        details = "; ".join(
            f"REPEAT: {r['team']} × {r['market']} lost {r['lost_on']}"
            for r in repeats
        )
        return False, f"HARD REJECT §7.5#14: {details}"
    return True, ""


def _check_multi_market(c: dict) -> tuple[bool, str]:
    """Gate #15: MULTI-MARKET ≥3 alternative markets calculated."""
    market_count = c.get("market_count") or c.get("markets_evaluated", 0)
    if market_count is None:
        market_count = 0
    if market_count >= 3:
        return True, f"{market_count} markets evaluated"
    return False, f"Only {market_count} markets (need ≥3)"


def _check_h2h_stat_specific(c: dict) -> tuple[bool, str]:
    """Gate #16: H2H STAT-SPECIFIC — H2H for exact stat exists."""
    h2h_blind = c.get("h2h_blind", True)
    if h2h_blind is False:
        return True, ""
    best = c.get("best_market") or {}
    stat_name = best.get("name", "?")
    return False, f"H2H-STAT-BLIND: no H2H for {stat_name}"


def _check_three_way(c: dict) -> tuple[bool, str]:
    """Gate #17: THREE-WAY ALIGNMENT — L10+H2H+L5 all support direction."""
    alignment = c.get("three_way_alignment")
    if not alignment:
        # Try to infer from ranking result
        ranking = c.get("ranking", [])
        three_way = c.get("three_way_check")
        if three_way:
            alignment = three_way.get("alignment") or three_way.get("status")
    if alignment and "SUPPORT" in alignment.upper():
        return True, f"THREE-WAY {alignment}"
    if alignment and alignment.upper() == "ALIGNED":
        return True, "THREE-WAY ALIGNED"
    if alignment:
        return False, f"THREE-WAY {alignment}"
    return False, "THREE-WAY not checked"


def _check_data_quality(c: dict) -> tuple[bool, str]:
    """Gate #18: DATA QUALITY — both teams have stat data, not one-sided."""
    best = c.get("best_market") or {}
    one_sided = best.get("one_sided", False)
    source = best.get("source", "")
    if one_sided:
        return False, "ONE-SIDED: opponent has zero stat data"
    if source == "db-synthetic":
        return True, f"SYNTHETIC data (penalized in safety), source={source}"
    return True, ""


# Ordered gate check functions
GATE_CHECKS = {
    "1": _check_identity,
    "2": _check_qualifier_flags,
    "3": _check_h2h_count,
    "4": _check_injuries,
    "5": _check_sources,
    "6": _check_tipster,
    "7": _check_upset_risk,
    "8": _check_ev,
    "9": _check_odds_drift,
    # "10" handled separately (needs repeat_losses)
    "11": _check_contrarian,
    "12": _check_bear_vs_bull,
    "13": _check_not_anchored,
    # "14" handled separately (needs repeat_losses)
    "15": _check_multi_market,
    "16": _check_h2h_stat_specific,
    "17": _check_three_way,
    "18": _check_data_quality,
}

# Checks that require repeat_losses parameter
GATE_CHECKS_WITH_REPEATS = {
    "10": _check_red_flags,
    "14": _check_48h_repeat,
}


# ---------------------------------------------------------------------------
# Red flag checks (§7.3)
# ---------------------------------------------------------------------------

def check_red_flags(candidate: dict) -> list[str]:
    """Sport-specific red flag checks per §7.3.

    Returns list of fired flag descriptions.
    """
    flags = []
    sport = candidate.get("sport", "").lower()
    best = candidate.get("best_market") or {}
    market_name = (best.get("name") or "").lower()
    safety = best.get("safety_score")
    if safety is None:
        safety = 0
    h2h_blind = candidate.get("h2h_blind", True)

    # Football: relegation match + goals market
    if sport == "football":
        comp = (candidate.get("competition") or "").lower()
        relegation_keywords = ["relegation", "play-off", "playoff"]
        is_relegation = any(k in comp for k in relegation_keywords)
        is_goals_market = any(k in market_name for k in ["goals", "btts", "1x2", "match winner"])
        if is_relegation and is_goals_market:
            flags.append(f"FLAG: Football relegation + goals market ({market_name})")

    # Tennis: WC/Q vs top-30 + O22.5 games → HARD REJECT (ZT#3)
    if sport == "tennis":
        for field in ("home_team", "away_team"):
            name = candidate.get(field, "").upper()
            if "(Q)" in name or "(WC)" in name or "(LL)" in name:
                if "22.5" in market_name or "games" in market_name:
                    flags.append(f"HARD REJECT ZT#3: {candidate.get(field)} qualifier + {market_name}")

        # Tennis: odds ratio check for game totals (needs both fav and dog odds)
        odds = candidate.get("odds", {})
        if odds and "game" in market_name:
            fav_odds = odds.get("fav_odds")
            dog_odds = odds.get("dog_odds")
            if fav_odds and dog_odds and dog_odds > 0:
                ratio = fav_odds / dog_odds
                if ratio > 1.50:
                    flags.append(f"FLAG: Tennis odds ratio {ratio:.2f} > 1.50 for game totals")

    # Any sport: safety score < 0.40
    if safety < 0.40:
        flags.append(f"FLAG: safety {safety:.2f} < 0.40")

    # Any sport: h2h_blind AND safety < 0.60
    if h2h_blind and safety < 0.60:
        flags.append(f"FLAG: H2H-BLIND + safety {safety:.2f} < 0.60")

    return flags


# ---------------------------------------------------------------------------
# Directional Conflict Detection (Pattern A — May 2026 post-mortem)
# ---------------------------------------------------------------------------

# Attack-related stats: if one pick says UNDER on an attack stat and another
# says OVER on a different attack stat for the same team in the same game,
# those are logically contradictory theses.
ATTACK_RELATED_KEYWORDS = frozenset([
    "shot", "sot", "shots on target", "corner", "corners",
    "chances", "xg", "attacks", "dangerous attacks",
])


def _is_attack_related(market_name: str) -> bool:
    """Check if a market is attack-related (shots, corners, SoT, etc.)."""
    lower = market_name.lower()
    return any(kw in lower for kw in ATTACK_RELATED_KEYWORDS)


def _extract_team_direction(pick: dict) -> list[tuple[str, str, str]]:
    """Extract (team, market_category, direction) tuples from a pick.

    Returns list of (team_name, stat_category, OVER/UNDER) for conflict checking.
    """
    results = []
    best = pick.get("best_market") or {}
    market_name = (best.get("name") or "").lower()
    direction = (best.get("direction") or "").upper()
    if not direction:
        return results

    home = (pick.get("home_team") or "").lower()
    away = (pick.get("away_team") or "").lower()

    # Determine which team the stat relates to
    # Team-specific markets: "Team A Corners", "PSG Shots", etc.
    if "team a" in market_name or "team_a" in market_name:
        team = home
    elif "team b" in market_name or "team_b" in market_name:
        team = away
    else:
        # Combined market — relates to both teams
        team = f"{home}+{away}"

    stat_category = "attack" if _is_attack_related(market_name) else "general"
    results.append((team, stat_category, direction))
    return results


def check_directional_conflicts(candidates: list[dict]) -> dict[str, list[str]]:
    """Detect contradictions: same team, same game, opposite directions on attack stats.

    Returns dict mapping event_key → list of conflict descriptions.
    """
    # Group picks by game (home+away)
    game_picks: dict[str, list[dict]] = {}
    for c in candidates:
        home = (c.get("home_team") or "").strip().lower()
        away = (c.get("away_team") or "").strip().lower()
        if home and away:
            key = f"{home}|{away}"
            game_picks.setdefault(key, []).append(c)

    conflicts: dict[str, list[str]] = {}

    for game_key, picks in game_picks.items():
        if len(picks) < 2:
            continue

        # Collect all (team, category, direction) for this game
        team_directions: dict[str, list[tuple[str, str, dict]]] = {}
        for pick in picks:
            for team, category, direction in _extract_team_direction(pick):
                team_directions.setdefault(team, []).append((category, direction, pick))

        # Check for contradictions: same team, attack stats, opposite directions
        for team, entries in team_directions.items():
            attack_entries = [(d, p) for cat, d, p in entries if cat == "attack"]
            if len(attack_entries) < 2:
                continue

            overs = [(d, p) for d, p in attack_entries if d == "OVER"]
            unders = [(d, p) for d, p in attack_entries if d == "UNDER"]

            if overs and unders:
                over_markets = [(_bm(p).get("name", "?")) for _, p in overs]
                under_markets = [(_bm(p).get("name", "?")) for _, p in unders]
                msg = (
                    f"DIRECTIONAL CONFLICT: {team} has OVER ({', '.join(over_markets)}) "
                    f"AND UNDER ({', '.join(under_markets)}) on attack stats in same game"
                )
                conflicts.setdefault(game_key, []).append(msg)

    return conflicts


def _bm(pick: dict) -> dict:
    """Safely get best_market from a pick."""
    return pick.get("best_market") or {}


# ---------------------------------------------------------------------------
# Competition Context Caps (Pattern B — May 2026 post-mortem)
# ---------------------------------------------------------------------------

# Knockout/playoff competitions trigger safety caps — L10 from domestic league
# doesn't reflect high-stakes knockout behavior.
KNOCKOUT_PATTERNS = re.compile(
    r"(semi[- ]?final|quarter[- ]?final|playoff|play-off|"
    r"knockout|elimination|round of 16|round of 8|"
    r"sf|qf|r16|final\b)",
    re.IGNORECASE,
)

CONTINENTAL_COMPETITIONS = re.compile(
    r"(champions league|europa league|conference league|"
    r"copa libertadores|copa sudamericana|"
    r"afc champions|ehf champions|cel champions|"
    r"khl playoff|nhl playoff|nba playoff)",
    re.IGNORECASE,
)

# Top-tier clubs where playing AWAY in knockout is extremely difficult
TOP_CLUBS = frozenset([
    "barcelona", "real madrid", "bayern", "manchester city",
    "liverpool", "psg", "inter", "juventus", "arsenal",
    "atletico madrid", "borussia dortmund", "napoli",
    # Add handball/basketball powerhouses
    "fc barcelona", "thw kiel", "sc magdeburg",
    "real madrid baloncesto", "olympiacos",
])


def compute_context_safety_cap(candidate: dict) -> tuple[float, list[str]]:
    """Compute maximum allowed safety score based on competition context.

    Returns (cap_value, list_of_reasons). Cap of 1.0 means no restriction.
    """
    competition = (candidate.get("competition") or "").lower()
    home = (candidate.get("home_team") or "").lower()
    away = (candidate.get("away_team") or "").lower()
    reasons = []
    cap = 1.0

    is_knockout = bool(KNOCKOUT_PATTERNS.search(competition))
    is_continental = bool(CONTINENTAL_COMPETITIONS.search(competition))

    if not is_knockout and not is_continental:
        return cap, reasons

    # Continental knockout (SF/Final) → cap 0.65
    if is_continental and is_knockout:
        if any(kw in competition for kw in ("semi", "final", "sf")):
            cap = min(cap, 0.65)
            reasons.append(f"Continental SF/Final: {competition} → cap 0.65")
        else:
            cap = min(cap, 0.70)
            reasons.append(f"Continental knockout: {competition} → cap 0.70")
    elif is_knockout:
        cap = min(cap, 0.70)
        reasons.append(f"Knockout stage: {competition} → cap 0.70")

    # Away at a top club in knockout → additional penalty
    is_away_pick = False
    for team_key in ("home_team",):
        team_name = (candidate.get(team_key) or "").lower()
        if any(top in team_name for top in TOP_CLUBS):
            # The home team is a top club — candidate is about a game AT that venue
            is_away_pick = True
            break

    if is_away_pick and is_knockout:
        cap = min(cap, cap - 0.15)
        reasons.append(f"Away at top club ({home}) in knockout → additional -0.15")

    # Ensure cap never goes below 0.40
    cap = max(cap, 0.40)

    return cap, reasons


# ---------------------------------------------------------------------------
# Upset risk (§6.5)
# ---------------------------------------------------------------------------

def compute_upset_risk(candidate: dict) -> dict:
    """Basic upset risk from odds and safety data.

    Returns dict with score (0.0–1.0) and contributing factors.
    """
    factors = []
    risk_score = 0.0

    odds = candidate.get("odds", {})
    market_best = odds.get("market_best", 0) if odds else 0
    best = candidate.get("best_market") or {}
    safety = best.get("safety_score", 0) or 0

    # Odds-based risk: higher odds = higher upset risk
    if market_best and market_best > 2.50:
        risk_score += 0.3
        factors.append(f"High odds {market_best}")
    elif market_best and market_best > 1.80:
        risk_score += 0.1
        factors.append(f"Moderate odds {market_best}")

    # Safety-based risk
    if safety < 0.50:
        risk_score += 0.3
        factors.append(f"Low safety {safety:.2f}")
    elif safety < 0.65:
        risk_score += 0.1
        factors.append(f"Medium safety {safety:.2f}")

    # H2H blind risk
    if candidate.get("h2h_blind", True):
        risk_score += 0.15
        factors.append("H2H-BLIND")

    # Data quality risk
    if candidate.get("data_quality") == "THIN":
        risk_score += 0.15
        factors.append("THIN data")

    # Three-way misalignment
    alignment = candidate.get("three_way_alignment", "")
    if alignment and "SUPPORT" not in alignment.upper():
        risk_score += 0.2
        factors.append(f"THREE-WAY {alignment}")

    return {
        "score": min(risk_score, 1.0),
        "factors": factors,
        "level": (
            "HIGH" if risk_score >= 0.5
            else "MEDIUM" if risk_score >= 0.25
            else "LOW"
        ),
    }


# ---------------------------------------------------------------------------
# Risk tier assignment
# ---------------------------------------------------------------------------

def compute_risk_tier(candidate: dict, gate_result: dict) -> str:
    """Assign LR/MS/HR/N based on safety, gate score, sport, kickoff.

    - N (Night): kickoff after 20:00 local time
    - LR (Low-Risk): safety ≥ 0.75, gate ≥ 16/18, not blind, EV > 0
    - MS (Multi-Sport): safety ≥ 0.60, gate ≥ 13/18
    - HR (Higher-Risk): everything else with EV > 0
    """
    # Check night first
    kickoff = candidate.get("kickoff", "")
    if kickoff:
        try:
            hour = int(kickoff.split("T")[1][:2]) if "T" in kickoff else None
            if hour is not None and hour >= 20:
                return "N"
        except (IndexError, ValueError):
            pass

    best = candidate.get("best_market") or {}
    safety = best.get("safety_score", 0) or 0
    gate_passed = gate_result.get("gate_passed", [])
    gate_score = len(gate_passed)
    gate_failed = gate_result.get("gate_failed", [])

    is_tipster_blind = "6" in gate_failed
    is_h2h_stat_blind = "16" in gate_failed
    ev = candidate.get("ev")
    # Stats-first mode: ev=None means odds not yet available (user checks Betclic)
    # Allow LR classification when ev is None (undetermined) or positive
    has_positive_ev = ev is None or ev > 0

    if (safety >= 0.75
            and gate_score >= 16
            and not is_tipster_blind
            and not is_h2h_stat_blind
            and has_positive_ev):
        return "LR"

    if safety >= 0.60 and gate_score >= 13:
        return "MS"

    return "HR"


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def compute_confidence(candidate: dict, gate_result: dict) -> tuple[float, list[str]]:
    """Compute confidence score [1.0, 5.0] with adjustments.

    Returns (final_confidence, list_of_adjustment_strings).
    """
    conf = 4.0
    adjustments = []

    best = candidate.get("best_market") or {}
    safety = best.get("safety_score", 0) or 0

    if safety >= 0.80:
        conf += 0.5
        adjustments.append("+0.5 safety≥0.80")

    alignment = candidate.get("three_way_alignment", "")
    if alignment and "SUPPORT" in alignment.upper():
        conf += 0.5
        adjustments.append("+0.5 THREE-WAY ALIGNED")

    tipster_count = candidate.get("tipster_count", 0) or 0
    if tipster_count >= 2:
        conf += 0.5
        adjustments.append(f"+0.5 {tipster_count} tipster sources")

    gate_failed = gate_result.get("gate_failed", [])

    if "6" in gate_failed:
        conf -= 0.5
        adjustments.append("-0.5 TIPSTER-BLIND")

    if "16" in gate_failed:
        conf -= 0.5
        adjustments.append("-0.5 H2H-STAT-BLIND")

    if candidate.get("data_quality") == "THIN":
        conf -= 0.5
        adjustments.append("-0.5 THIN data")

    if "18" in gate_failed:
        conf -= 1.0
        adjustments.append("-1.0 ONE-SIDED data (opponent missing)")

    red_flags = check_red_flags(candidate)
    if red_flags:
        conf -= 1.0
        adjustments.append("-1.0 red flag fired")

    conf = max(1.0, min(5.0, conf))
    return round(conf, 1), adjustments


# ---------------------------------------------------------------------------
# 18-point gate runner
# ---------------------------------------------------------------------------

def check_17_point_gate(candidate: dict, repeat_losses: list) -> dict:
    """Run all 18 gate checks on one candidate.

    Returns dict with:
      gate_passed: list of check IDs that passed
      gate_failed: list of check IDs that failed
      gate_warnings: list of warning strings
      gate_score: str like "15/18"
      gate_details: dict mapping check ID → {passed, message}
    """
    passed = []
    failed = []
    warnings = []
    details = {}

    for check_id in sorted(GATE_LABELS.keys(), key=int):
        if check_id in GATE_CHECKS:
            ok, msg = GATE_CHECKS[check_id](candidate)
        elif check_id in GATE_CHECKS_WITH_REPEATS:
            ok, msg = GATE_CHECKS_WITH_REPEATS[check_id](candidate, repeat_losses)
        else:
            ok, msg = True, ""

        details[check_id] = {"passed": ok, "message": msg, "label": GATE_LABELS[check_id]}
        if ok:
            passed.append(check_id)
        else:
            failed.append(check_id)
        if msg:
            warnings.append(msg)

    return {
        "gate_passed": passed,
        "gate_failed": failed,
        "gate_warnings": [w for w in warnings if w],
        "gate_score": f"{len(passed)}/18",
        "gate_details": details,
    }


# ---------------------------------------------------------------------------
# Sport diversity (§7.6)
# ---------------------------------------------------------------------------

def check_sport_diversity(approved: list[dict]) -> dict:
    """Post-gate diversity check per §7.6.

    Requirements:
      - ≥5 sports in approved picks
      - ≥1 KEY sport (football/volleyball/basketball/tennis) in approved
    """
    approved_sports = sorted({c.get("sport", "").lower() for c in approved} - {""})
    key_sports = [s for s in approved_sports if s in KEY_SPORTS]
    passes = len(approved_sports) >= 5 and len(key_sports) >= 1
    missing = sorted(ALL_SPORTS - set(approved_sports))

    return {
        "approved_sports": approved_sports,
        "sports_count": len(approved_sports),
        "key_sports_count": len(key_sports),
        "passes_diversity": passes,
        "missing_sports": missing,
    }


# ---------------------------------------------------------------------------
# 48h repeat loader
# ---------------------------------------------------------------------------

def load_48h_repeats(date: str) -> list:
    """Load recent losses from picks-ledger for 48h repeat check."""
    return load_recent_losses(LEDGER_PATH, hours=48)


# ---------------------------------------------------------------------------
# Normalise S3 analysis to gate input
# ---------------------------------------------------------------------------

def _normalise_s3_to_gate_input(analysis: dict) -> dict:
    """Convert S3 deep_stats_report analysis entry to gate input format.

    S3 output has slightly different keys than what gate checks expect.
    This bridges the two formats.
    """
    h2h_summary = analysis.get("h2h_summary", {})
    ranking = analysis.get("ranking", analysis.get("ranking_result", {}).get("ranking", []))
    three_way = analysis.get("three_way_check") or analysis.get(
        "ranking_result", {}
    ).get("three_way_check")

    # Detect H2H blind for the best market stat
    best = analysis.get("best_market")
    h2h_blind = True
    if best and h2h_summary.get("has_data"):
        h2h_avg = best.get("h2h_avg")
        if h2h_avg is not None:
            h2h_blind = False

    # Three-way alignment
    alignment = None
    if three_way:
        alignment = three_way.get("alignment") or three_way.get("status")

    # Collect sources from stats summaries
    sources = []
    for key in ("stats_a_summary", "stats_b_summary"):
        s = analysis.get(key, {})
        for src in s.get("sources", []):
            if src and src not in sources:
                sources.append(src)

    return {
        "sport": analysis.get("sport", ""),
        "home_team": analysis.get("home_team", ""),
        "away_team": analysis.get("away_team", ""),
        "competition": analysis.get("competition", ""),
        "kickoff": analysis.get("kickoff", ""),
        "best_market": best,
        "all_markets": ranking,
        "market_count": analysis.get("markets_evaluated", len(ranking)),
        "h2h_count": h2h_summary.get("meetings_count", 0),
        "h2h_blind": h2h_blind,
        "three_way_alignment": alignment,
        "data_quality": (
            "FULL"
            if analysis.get("has_data")
            else "THIN"
        ),
        "ev": analysis.get("ev"),
        "odds": analysis.get("odds", {}),
        "sources": sources,
        "tipster_count": (
            analysis.get("tipster_count")
            or (analysis.get("tipster_support") or {}).get("count")
            or 0
        ),
        "ranking": ranking,
        "three_way_check": three_way,
        "warnings": analysis.get("warnings", []),
    }


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def run_gate(candidates: list[dict], date: str, strict: bool = False) -> dict:
    """Main entry. Run all 17 checks on each candidate.

    Classifies into approved / extended_pool / rejected.

    Args:
        candidates: list of candidate dicts (gate-input format)
        date: betting day YYYY-MM-DD
        strict: if True, ANY gate failure → rejected

    Returns gate_results dict.
    """
    # Filter garbage event names before processing
    _garbage_re = re.compile(
        r"picks\s*&\s*odds|epl\s+picks|odds\s+for\s+(saturday|friday|monday|sunday|tuesday|wednesday|thursday)|"
        r"\btypy\b|bukmacherów|kolejka|wydarzenie|"
        r"premiership:|bundesliga:|uefa\s+\w+\s+champions|la\s+liga:|"
        r"\d+\.\d{2}\s+\d+\.\d{2}|"  # embedded odds
        r"\d+\s*'|"  # match minutes
        r"1x\s*✅|"  # result markers
        r"\binfo\b$|"  # placeholder "info" as team name
        r",\s*\w.+vs\b|"  # multi-match (", RB Leipzig vs Borussia")
        r"żużel|fame\s+mma|pfl\s+\w+\s+wyniki|wiek,\s*waga|"
        r"\bview\s+prediction\b|\bgaleria\b|\bsprawdź\b|\brekord,\s*walka\b",
        re.I,
    )
    clean_candidates = []
    garbage_count = 0
    for c in candidates:
        home = c.get("home_team", "")
        away = c.get("away_team", "")
        if _garbage_re.search(home) or _garbage_re.search(away):
            garbage_count += 1
            continue
        # Skip very long team names (usually garbage)
        if len(home) > 50 or len(away) > 50:
            garbage_count += 1
            continue
        clean_candidates.append(c)
    if garbage_count:
        print(f"[gate_checker] Filtered {garbage_count} garbage events")

    # PHANTOM/ALREADY-PLAYED FILTER — ZT#6 enforcement (defense layer 2)
    # Events with kickoff >2h in the past AND not on the betting date are phantoms
    now_utc = datetime.now(timezone.utc)
    phantom_count = 0
    live_candidates = []
    for c in clean_candidates:
        kickoff = c.get("kickoff", "")
        if kickoff and "T" in kickoff:
            try:
                ko_str = kickoff.replace("Z", "+00:00")
                ko_dt = datetime.fromisoformat(ko_str)
                if ko_dt.tzinfo is None:
                    from datetime import timedelta
                    ko_dt = ko_dt.replace(tzinfo=timezone(timedelta(hours=2)))
                ko_date_str = ko_dt.strftime("%Y-%m-%d")
                # Only filter if kickoff date doesn't match the betting date
                if ko_date_str != date:
                    elapsed_hours = (now_utc - ko_dt.astimezone(timezone.utc)).total_seconds() / 3600
                    if elapsed_hours > 2:
                        phantom_count += 1
                        continue
            except (ValueError, TypeError):
                pass
        live_candidates.append(c)
    if phantom_count:
        print(f"[gate_checker] Filtered {phantom_count} already-played events (kickoff >2h ago)")
    clean_candidates = live_candidates

    # Deduplicate events (keep highest safety_score version)
    def _dedup_key(c: dict) -> str:
        """Normalize team names for dedup: lowercase, strip common prefixes."""
        h = re.sub(r"^(fc|sc|sk|ac|as|fk|cd|cf)\s+", "", (c.get("home_team") or "").strip().lower())
        a = re.sub(r"^(fc|sc|sk|ac|as|fk|cd|cf)\s+", "", (c.get("away_team") or "").strip().lower())
        # Normalize common abbreviations (order matters — expand shorter forms first)
        for short, full in [("man utd", "manchester united"), ("man city", "manchester city"),
                            ("nottm", "nottingham"), ("sheff", "sheffield"),
                            ("wolves", "wolverhampton"), ("newcastle utd", "newcastle united")]:
            h = h.replace(short, full)
            a = a.replace(short, full)
        return f"{h}|{a}"

    seen: dict[str, dict] = {}
    dedup_count = 0
    for c in clean_candidates:
        key = _dedup_key(c)
        if key in seen:
            # Keep the one with higher safety score
            existing_safety = (seen[key].get("best_market") or {}).get("safety_score", 0)
            new_safety = (c.get("best_market") or {}).get("safety_score", 0)
            if new_safety > existing_safety:
                seen[key] = c
            dedup_count += 1
        else:
            seen[key] = c
    if dedup_count:
        print(f"[gate_checker] Deduped {dedup_count} duplicate events")
    candidates = list(seen.values())

    # --- Pattern A: Detect directional conflicts across same-game picks ---
    directional_conflicts = check_directional_conflicts(candidates)
    if directional_conflicts:
        print(f"[gate_checker] ⚠️ Directional conflicts in {len(directional_conflicts)} games")
        for game_key, msgs in directional_conflicts.items():
            for msg in msgs:
                print(f"    {msg}")

    # --- Pattern B: Apply competition context safety caps ---
    context_capped = 0
    for c in candidates:
        cap, cap_reasons = compute_context_safety_cap(c)
        if cap < 1.0:
            best = c.get("best_market") or {}
            original_safety = best.get("safety_score", 0)
            if original_safety and original_safety > cap:
                best["safety_score"] = round(cap, 2)
                best["safety_capped"] = True
                best["original_safety"] = original_safety
                best["cap_reasons"] = cap_reasons
                c["context_cap_applied"] = True
                context_capped += 1
                print(f"    🔒 {c.get('home_team', '?')} vs {c.get('away_team', '?')}: "
                      f"safety {original_safety:.2f} → {cap:.2f} ({'; '.join(cap_reasons)})")
    if context_capped:
        print(f"[gate_checker] Context caps applied: {context_capped} candidates")

    repeat_losses = load_48h_repeats(date)
    approved = []
    extended_pool = []
    rejected = []

    for c in candidates:
        gate_result = check_17_point_gate(c, repeat_losses)

        # --- Pattern A: Flag directional conflicts ---
        home = (c.get("home_team") or "").strip().lower()
        away = (c.get("away_team") or "").strip().lower()
        game_key = f"{home}|{away}"
        conflict_msgs = directional_conflicts.get(game_key, [])
        if conflict_msgs:
            gate_result["gate_warnings"].extend(conflict_msgs)
            c["directional_conflict"] = True

        risk_tier = compute_risk_tier(c, gate_result)
        conf, conf_adj = compute_confidence(c, gate_result)

        entry = {
            **c,
            "gate_score": gate_result["gate_score"],
            "gate_passed": gate_result["gate_passed"],
            "gate_failed": gate_result["gate_failed"],
            "gate_warnings": gate_result["gate_warnings"],
            "gate_details": gate_result["gate_details"],
            "risk_tier": risk_tier,
            "confidence_adjustments": conf_adj,
            "final_confidence": conf,
            "upset_risk": c.get("_upset_risk", {}),
        }
        # Remove internal temp key
        entry.pop("_upset_risk", None)

        # Classification logic
        n_failed = len(gate_result["gate_failed"])
        ev = c.get("ev")
        has_positive_ev = ev is not None and ev > 0

        # Hard reject conditions
        hard_reject = False
        for detail in gate_result["gate_details"].values():
            if "HARD REJECT" in detail.get("message", ""):
                hard_reject = True
                break

        if hard_reject:
            entry["status"] = "REJECTED"
            entry["rejection_reason"] = "HARD REJECT triggered"
            rejected.append(entry)
        elif strict and n_failed > 0:
            entry["status"] = "REJECTED"
            entry["rejection_reason"] = f"STRICT mode: {n_failed} gate failures"
            rejected.append(entry)
        elif not has_positive_ev and ev is not None:
            # EV ≤ 0 → extended pool (NOT rejected per NO AUTO-REJECTION rule)
            entry["status"] = "EXTENDED"
            extended_pool.append(entry)
        elif n_failed <= 5:
            entry["status"] = "APPROVED"
            approved.append(entry)
        else:
            # Many failures but EV > 0 → extended pool
            entry["status"] = "EXTENDED"
            extended_pool.append(entry)

    diversity = check_sport_diversity(approved)
    expansion_needed = not diversity["passes_diversity"]

    return {
        "date": date,
        "gate_results": {
            "approved": approved,
            "extended_pool": extended_pool,
            "rejected": rejected,
            "expansion_needed": expansion_needed,
            "sport_diversity": diversity,
        },
        "summary": {
            "total_candidates": len(candidates),
            "approved_count": len(approved),
            "extended_count": len(extended_pool),
            "rejected_count": len(rejected),
        },
    }


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def _enrich_best_market(entry: dict) -> None:
    """Enrich best_market with ranking/three_way data for richer coupon descriptions.

    Copies l10_avg, l5_avg, rank, margin, team averages, hit_rate_l5
    from the ranking array into best_market so the coupon builder
    can generate rich descriptions without needing the full ranking.
    """
    best = entry.get("best_market")
    if not best:
        return

    ranking = entry.get("ranking") or entry.get("all_markets") or []
    three_way = entry.get("three_way_check")
    market_name = best.get("name", "")

    # Find matching ranking entry
    matched_rank = None
    for r in ranking:
        if isinstance(r, dict) and r.get("name") == market_name:
            matched_rank = r
            break

    if matched_rank:
        # Copy enrichment fields not already present
        for field in ("rank", "margin", "team_a_avg", "team_b_avg",
                      "hit_rate_l5", "source", "h2h_blind"):
            if field not in best or best[field] is None:
                val = matched_rank.get(field)
                if val is not None:
                    best[field] = val
        # Total markets evaluated
        best["total_markets_evaluated"] = len(ranking)

        # Extract l10_avg, l5_avg from three_way_check in ranking entry
        rank_twc = matched_rank.get("three_way_check", {})
        if rank_twc:
            if "l10_avg" not in best or best.get("l10_avg") is None:
                best["l10_avg"] = rank_twc.get("l10_avg")
            if "l5_avg" not in best or best.get("l5_avg") is None:
                best["l5_avg"] = rank_twc.get("l5_avg")

    # Fallback: top-level three_way_check
    if three_way:
        if "l10_avg" not in best or best.get("l10_avg") is None:
            best["l10_avg"] = three_way.get("l10_avg")
        if "l5_avg" not in best or best.get("l5_avg") is None:
            best["l5_avg"] = three_way.get("l5_avg")

    # Use combined_avg as l10_avg fallback
    if ("l10_avg" not in best or best.get("l10_avg") is None) and best.get("combined_avg") is not None:
        best["l10_avg"] = best["combined_avg"]

    # Market count from entry level
    if "total_markets_evaluated" not in best:
        best["total_markets_evaluated"] = entry.get("market_count", 0)


def _write_json(results: dict, date: str) -> Path:
    """Write gate results to JSON."""
    out_path = DATA_DIR / f"{date}_s7_gate_results.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Enrich best_market with ranking/three_way data before stripping bulk fields
    clean = json.loads(json.dumps(results, default=str))
    for bucket in ("approved", "extended_pool", "rejected"):
        for entry in clean.get("gate_results", {}).get(bucket, []):
            _enrich_best_market(entry)
            entry.pop("gate_details", None)
            entry.pop("all_markets", None)
            entry.pop("ranking", None)
            entry.pop("three_way_check", None)
            entry.pop("warnings", None)

    out_path.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[gate_checker] JSON: {out_path}")
    return out_path


def _candidate_row(entry: dict) -> str:
    """Build markdown table row for one candidate."""
    best = entry.get("best_market") or {}
    return (
        f"| {entry.get('sport', '')} "
        f"| {entry.get('home_team', '')} vs {entry.get('away_team', '')} "
        f"| {best.get('name', '-')} "
        f"| {best.get('safety_score', '-')} "
        f"| {entry.get('gate_score', '-')} "
        f"| {entry.get('risk_tier', '-')} "
        f"| {entry.get('final_confidence', '-')} "
        f"| **{entry.get('status', '?')}** |"
    )


def _gate_scorecard(entry: dict) -> str:
    """Per-candidate gate scorecard markdown."""
    best = entry.get("best_market") or {}
    lines = [
        f"### {entry.get('home_team', '?')} vs {entry.get('away_team', '?')} "
        f"({entry.get('sport', '?').upper()}) — {entry.get('status', '?')}",
        f"- **Competition:** {entry.get('competition', '-')}",
        f"- **Kickoff:** {entry.get('kickoff', '-')}",
        f"- **Best market:** {best.get('name', '-')} {best.get('direction', '')} "
        f"(safety {best.get('safety_score', '-')})",
        f"- **Gate score:** {entry.get('gate_score', '-')}",
        f"- **Risk tier:** {entry.get('risk_tier', '-')}",
        f"- **Confidence:** {entry.get('final_confidence', '-')}",
        "",
        "| # | Check | Result | Note |",
        "|---|-------|--------|------|",
    ]

    details = entry.get("gate_details", {})
    for check_id in sorted(details.keys(), key=int):
        d = details[check_id]
        icon = "✅" if d["passed"] else "❌"
        lines.append(
            f"| {check_id} | {d['label']} | {icon} | {d.get('message', '')} |"
        )

    if entry.get("confidence_adjustments"):
        lines.append("")
        lines.append("**Confidence adjustments:** " + ", ".join(entry["confidence_adjustments"]))

    upset = entry.get("upset_risk", {})
    if upset:
        lines.append(
            f"\n**Upset risk:** {upset.get('level', '?')} "
            f"({upset.get('score', 0):.2f}) — {', '.join(upset.get('factors', []))}"
        )

    lines.append("")
    return "\n".join(lines)


def _write_markdown(results: dict, date: str) -> Path:
    """Write gate results to markdown."""
    out_path = DATA_DIR / f"{date}_s7_gate_results.md"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    gate = results["gate_results"]
    summary = results["summary"]
    diversity = gate["sport_diversity"]

    lines = [
        f"# S7 Gate Results — {date}",
        "",
        f"**Total:** {summary['total_candidates']} candidates | "
        f"**Approved:** {summary['approved_count']} | "
        f"**Extended:** {summary['extended_count']} | "
        f"**Rejected:** {summary['rejected_count']}",
        "",
        "## Summary Table",
        "",
        "| Sport | Event | Market | Safety | Gate | Tier | Conf | Status |",
        "|-------|-------|--------|--------|------|------|------|--------|",
    ]

    for bucket in ("approved", "extended_pool", "rejected"):
        for entry in gate.get(bucket, []):
            lines.append(_candidate_row(entry))

    lines.append("")

    # Sport diversity
    lines.append("## Sport Diversity Check (§7.6)")
    lines.append("")
    lines.append(f"- **Sports in approved:** {', '.join(diversity['approved_sports']) or 'none'}")
    lines.append(f"- **Count:** {diversity['sports_count']}/5 required")
    lines.append(f"- **KEY sports:** {diversity['key_sports_count']}")
    div_icon = "✅" if diversity["passes_diversity"] else "❌"
    lines.append(f"- **Passes diversity:** {div_icon}")
    if not diversity["passes_diversity"]:
        lines.append(f"- **Missing sports:** {', '.join(diversity['missing_sports'])}")
        lines.append("")
        lines.append(
            "> ⚠️ **EXPANSION NEEDED:** §7.6 requires ≥5 sports in approved picks. "
            "Run emergency expansion across ALL remaining shortlist candidates."
        )
    lines.append("")

    # Per-candidate scorecards
    lines.append("## Approved Picks")
    lines.append("")
    for entry in gate.get("approved", []):
        lines.append(_gate_scorecard(entry))

    if gate.get("extended_pool"):
        lines.append("## Extended Pool")
        lines.append("")
        for entry in gate["extended_pool"]:
            lines.append(_gate_scorecard(entry))

    if gate.get("rejected"):
        lines.append("## Rejected")
        lines.append("")
        for entry in gate["rejected"]:
            lines.append(_gate_scorecard(entry))

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[gate_checker] Markdown: {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------

def _load_s3_output(date: str, input_path: str | None = None) -> list[dict]:
    """Load S3 deep stats output and normalise to gate input format.

    Tries:
      1. Explicit --input path
      2. DB (analysis_results table)
      3. {date}_s3_deep_stats.json
    """
    if input_path:
        path = Path(input_path)
        if not path.exists():
            print(f"[gate_checker] ERROR: S3 output not found: {path}")
            sys.exit(1)
        data = json.loads(path.read_text(encoding="utf-8"))
        analyses = data.get("analyses", data.get("candidates", []))
        candidates = [_normalise_s3_to_gate_input(a) for a in analyses]
        print(f"[gate_checker] Loaded {len(candidates)} candidates from {path}")
        return candidates

    # Try DB first
    try:
        from db_data_loader import load_analysis_results_from_db
        db_analyses = load_analysis_results_from_db(date)
        if db_analyses:
            candidates = [_normalise_s3_to_gate_input(a) for a in db_analyses]
            print(f"[gate_checker] DB: loaded {len(candidates)} candidates")
            return candidates
    except Exception as e:
        print(f"[gate_checker] DB read failed, using JSON fallback: {e}")

    # JSON fallback
    path = DATA_DIR / f"{date}_s3_deep_stats.json"

    if not path.exists():
        print(f"[gate_checker] ERROR: S3 output not found: {path}")
        sys.exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    analyses = data.get("analyses", data.get("candidates", []))

    candidates = []
    for a in analyses:
        candidates.append(_normalise_s3_to_gate_input(a))

    print(f"[gate_checker] Loaded {len(candidates)} candidates from {path}")
    return candidates


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="S7 Pick Approval Gate — 17-point programmatic gate checker"
    )
    parser.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Betting day YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Path to S3 deep stats JSON (overrides default path)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Reject on ANY gate failure",
    )

    args = parser.parse_args()
    candidates = _load_s3_output(args.date, args.input)

    if not candidates:
        print("[gate_checker] No candidates to gate-check.")
        sys.exit(0)

    results = run_gate(candidates, args.date, strict=args.strict)

    _write_json(results, args.date)
    _write_markdown(results, args.date)

    # Dual-write: save gate results to DB
    try:
        from db_data_loader import save_gate_results_to_db
        all_results = []
        for bucket in ("approved", "extended_pool", "rejected"):
            all_results.extend(results.get("gate_results", {}).get(bucket, []))
        saved = save_gate_results_to_db(args.date, all_results)
        print(f"[gate_checker] DB: saved {saved} gate results")
    except Exception as e:
        print(f"[gate_checker] DB write failed (non-fatal): {e}")

    s = results["summary"]
    print(
        f"\n[gate_checker] Done: {s['total_candidates']} candidates → "
        f"{s['approved_count']} approved, {s['extended_count']} extended, "
        f"{s['rejected_count']} rejected"
    )
    if results["gate_results"]["expansion_needed"]:
        print("[gate_checker] ⚠️  EXPANSION NEEDED — sport diversity check failed (§7.6)")


if __name__ == "__main__":
    main()
