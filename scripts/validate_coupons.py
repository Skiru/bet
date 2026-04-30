#!/usr/bin/env python3
"""Coupon markdown file validator — structural integrity + arithmetic checks.

Validates:
1. Combined odds arithmetic (multiply legs, ±2% tolerance)
2. Unique event per core coupon (COMBO-prefixed coupons exempt)
3. Pick ID cross-reference against picks-ledger.csv
4. Polish description presence in each leg
"""

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

# Polish betting terms expected in leg descriptions
POLISH_TERMS = {
    "powyżej", "poniżej", "bramek", "gemów", "rzutów", "rożnych",
    "setów", "kartek", "zwycięstwo", "handicap", "łączna", "strzelą",
    "punktów", "framów", "goli", "runów", "mapowy", "setowy",
    "drużyny", "szansa", "remis", "podwójna",
}

# Pattern to extract per-leg odds from description
LEG_ODDS_RE = re.compile(r"@\s*([\d.]+)")

# Pattern to extract event names from description
# Matches: "Team A vs Team B (Competition)" or "Team A vs Team B"
EVENT_RE = re.compile(
    r"([A-ZÀ-Ža-zà-ž0-9\s.'&\-]+?)\s+vs\s+([A-ZÀ-Ža-zà-ž0-9\s.'&\-]+?)"
    r"\s*(?:\([^)]+\))?\s*(?:—|–|-)"
)


def parse_coupon_tables(md_text: str) -> list[dict]:
    """Extract all coupon entries from markdown tables."""
    coupons = []

    for line in md_text.split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue

        # Split by pipe and strip
        parts = [p.strip() for p in line.split("|")]
        # Remove empty first/last from leading/trailing pipes
        parts = [p for p in parts if p != ""]

        # We need at least 6 columns: #, Kupon, Co, Kurs, Stawka, Zwrot
        if len(parts) < 6:
            continue

        # Column 1 must be a number
        try:
            row_num = int(parts[0])
        except ValueError:
            continue

        coupon_id = parts[1].strip()
        description = parts[2].strip()

        # Skip separator/header rows
        if coupon_id.startswith("-") or coupon_id.lower() in ("kupon", "#"):
            continue

        # Must contain a coupon-like ID (CP-, COMBO-, CK-COMBO-, EXT-)
        if not re.match(r"(?:CP|COMBO|CK-COMBO|EXT)", coupon_id, re.IGNORECASE):
            continue

        # Parse numeric columns (combined odds, stake, return)
        try:
            combined_odds = float(parts[3])
            stake = float(parts[4])
            potential_return = float(parts[5])
        except (ValueError, IndexError):
            continue

        # Extract per-leg odds
        legs_odds = [float(o) for o in LEG_ODDS_RE.findall(description)]

        # Extract event names from description
        # Split by <br> to get individual legs
        legs_text = re.split(r"<br\s*/?>", description)
        events = []
        for leg_text in legs_text:
            # Try to extract "X vs Y" pattern
            ev_match = EVENT_RE.search(leg_text)
            if ev_match:
                event_name = f"{ev_match.group(1).strip()} vs {ev_match.group(2).strip()}"
                events.append(normalize_event(event_name))
            else:
                # Fallback: use first part before "—" as event identifier
                parts = re.split(r"\s*(?:—|–)\s*", leg_text, maxsplit=1)
                if parts:
                    events.append(normalize_event(parts[0].strip()))

        # Determine if core or combo
        is_combo = bool(re.search(r"(?:COMBO|CK-COMBO|EXT)", coupon_id, re.IGNORECASE))

        coupons.append({
            "row_num": row_num,
            "coupon_id": coupon_id,
            "description": description,
            "legs_text": legs_text,
            "legs_odds": legs_odds,
            "combined_odds_stated": combined_odds,
            "stake": stake,
            "potential_return": potential_return,
            "events": events,
            "is_combo": is_combo,
        })

    return coupons


def normalize_event(name: str) -> str:
    """Normalize event name for comparison."""
    name = name.lower().strip()
    name = re.sub(r"\s+", " ", name)
    # Remove common prefixes
    for prefix in ["fc ", "sc ", "ac ", "ss ", "bv ", "ud "]:
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name


def verify_arithmetic(
    legs_odds: list[float], stated_combined: float, tolerance: float = 0.02
) -> tuple[bool, float, float]:
    """Verify combined odds = product of leg odds within tolerance.

    Returns (passed, computed_odds, diff_pct).
    """
    if not legs_odds:
        return True, 0.0, 0.0  # Can't verify without leg odds

    computed = 1.0
    for odds in legs_odds:
        computed *= odds

    if stated_combined == 0:
        return False, computed, 100.0

    diff_pct = abs(computed - stated_combined) / stated_combined
    passed = diff_pct <= tolerance
    return passed, round(computed, 3), round(diff_pct * 100, 2)


def check_unique_events(coupons: list[dict]) -> list[str]:
    """Check that core coupons don't share events."""
    errors = []
    core_coupons = [c for c in coupons if not c["is_combo"]]

    event_to_coupons: dict[str, list[str]] = {}
    for coupon in core_coupons:
        for event in coupon["events"]:
            if event not in event_to_coupons:
                event_to_coupons[event] = []
            event_to_coupons[event].append(coupon["coupon_id"])

    for event, coupon_ids in event_to_coupons.items():
        if len(coupon_ids) > 1:
            ids_str = " and ".join(coupon_ids)
            errors.append(
                f"DUPLICATE_EVENT: '{event}' appears in {ids_str} (core portfolio violation)"
            )

    return errors


def check_polish_descriptions(legs_text: list[str]) -> list[str]:
    """Check that each leg contains Polish betting terminology."""
    warnings = []
    for i, leg in enumerate(legs_text, 1):
        leg_lower = leg.lower()
        has_polish = any(term in leg_lower for term in POLISH_TERMS)
        if not has_polish:
            warnings.append(f"MISSING_POLISH: Leg {i} may lack Polish description")
    return warnings


def check_pick_ids(coupons: list[dict], ledger_path: Path) -> list[str]:
    """Cross-reference pick_ids from coupon descriptions against picks-ledger."""
    errors = []
    if not ledger_path.exists():
        return [f"LEDGER_MISSING: {ledger_path} not found — cannot cross-reference pick IDs"]

    # Load pick IDs from ledger
    ledger_ids = set()
    try:
        with open(ledger_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "pick_id" in row:
                    ledger_ids.add(row["pick_id"].strip())
    except Exception as e:
        return [f"LEDGER_ERROR: Could not read ledger: {e}"]

    # Extract pick IDs from coupon file (PK-YYYYMMDD-## pattern)
    pk_pattern = re.compile(r"PK-\d{8}-\d+")
    for coupon in coupons:
        found_ids = pk_pattern.findall(coupon["description"])
        for pk_id in found_ids:
            if pk_id not in ledger_ids:
                errors.append(
                    f"MISSING_PICK_ID: {pk_id} in {coupon['coupon_id']} not found in picks-ledger"
                )

    return errors


def check_return_arithmetic(coupon: dict) -> list[str]:
    """Verify that potential return ≈ combined_odds × stake."""
    errors = []
    expected_return = coupon["combined_odds_stated"] * coupon["stake"]
    if coupon["potential_return"] > 0 and expected_return > 0:
        diff = abs(expected_return - coupon["potential_return"])
        if diff > 0.05:  # 5 grosz tolerance
            errors.append(
                f"RETURN_MISMATCH: stated return {coupon['potential_return']:.2f} "
                f"but odds({coupon['combined_odds_stated']}) × stake({coupon['stake']}) "
                f"= {expected_return:.2f}"
            )
    return errors


def validate_file(file_path: Path, ledger_path: Path) -> dict:
    """Validate a single coupon file."""
    result = {
        "file": file_path.name,
        "coupons_found": 0,
        "passed": 0,
        "failed": 0,
        "checks": [],
        "global_errors": [],
    }

    if not file_path.exists():
        result["global_errors"].append(f"File not found: {file_path}")
        return result

    md_text = file_path.read_text(encoding="utf-8")
    coupons = parse_coupon_tables(md_text)
    result["coupons_found"] = len(coupons)

    if not coupons:
        result["global_errors"].append("No coupon tables found in file")
        return result

    # Global check: unique events across core coupons
    dup_errors = check_unique_events(coupons)
    result["global_errors"].extend(dup_errors)

    # Global check: pick ID cross-reference
    pk_errors = check_pick_ids(coupons, ledger_path)
    result["global_errors"].extend(pk_errors)

    # Per-coupon checks
    for coupon in coupons:
        check = {
            "coupon_id": coupon["coupon_id"],
            "type": "combo" if coupon["is_combo"] else "core",
            "legs": len(coupon["legs_text"]),
            "legs_odds": coupon["legs_odds"],
            "combined_odds_stated": coupon["combined_odds_stated"],
            "errors": [],
            "warnings": [],
        }

        # 1. Arithmetic check
        if coupon["legs_odds"]:
            passed, computed, diff_pct = verify_arithmetic(
                coupon["legs_odds"], coupon["combined_odds_stated"]
            )
            check["combined_odds_computed"] = computed
            check["tolerance_pct"] = diff_pct
            if not passed:
                check["errors"].append(
                    f"ARITHMETIC: stated combined odds {coupon['combined_odds_stated']} "
                    f"but computed {computed} (diff {diff_pct}%, tolerance ±2%)"
                )
        else:
            check["warnings"].append(
                "NO_LEG_ODDS: Could not extract individual leg odds from description"
            )

        # 2. Return arithmetic check
        ret_errors = check_return_arithmetic(coupon)
        check["errors"].extend(ret_errors)

        # 3. Polish description check
        polish_warnings = check_polish_descriptions(coupon["legs_text"])
        check["warnings"].extend(polish_warnings)

        # 4. Minimum legs check
        if len(coupon["legs_text"]) < 2:
            check["errors"].append(
                f"MIN_LEGS: Coupon has {len(coupon['legs_text'])} leg(s), minimum is 2"
            )

        # Determine status
        check["status"] = "FAIL" if check["errors"] else "PASS"
        if check["status"] == "PASS":
            result["passed"] += 1
        else:
            result["failed"] += 1

        result["checks"].append(check)

    return result


def format_text(result: dict) -> str:
    """Format validation result as human-readable text."""
    lines = []
    lines.append(f"═══ Coupon Validation: {result['file']} ═══")
    lines.append(
        f"Coupons: {result['coupons_found']}  "
        f"Passed: {result['passed']}  Failed: {result['failed']}"
    )

    if result["global_errors"]:
        lines.append("")
        lines.append("  Global errors:")
        for err in result["global_errors"]:
            lines.append(f"    ⚠ {err}")

    lines.append("")
    for check in result["checks"]:
        status_icon = "✓" if check["status"] == "PASS" else "✗"
        odds_info = ""
        if "combined_odds_computed" in check:
            odds_info = (
                f" [stated: {check['combined_odds_stated']}, "
                f"computed: {check['combined_odds_computed']}, "
                f"diff: {check['tolerance_pct']}%]"
            )
        lines.append(
            f"  {status_icon} {check['coupon_id']} ({check['type']}, "
            f"{check['legs']} legs){odds_info} → {check['status']}"
        )
        for err in check["errors"]:
            lines.append(f"    ERROR: {err}")
        for warn in check["warnings"]:
            lines.append(f"    WARN: {warn}")

    any_fail = result["failed"] > 0 or result["global_errors"]
    lines.append("")
    lines.append(f"Result: {'FAIL' if any_fail else 'PASS'}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Validate coupon markdown files — arithmetic, structure, cross-references."
    )
    parser.add_argument(
        "files", nargs="+", type=Path,
        help="Path(s) to coupon markdown file(s)"
    )
    parser.add_argument(
        "--format", choices=["json", "text"], default="json",
        help="Output format (default: json)"
    )
    parser.add_argument(
        "--ledger", type=Path,
        default=Path("betting/journal/picks-ledger.csv"),
        help="Path to picks-ledger.csv for cross-reference"
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Treat warnings as errors"
    )
    args = parser.parse_args()

    all_results = []
    any_fail = False

    for file_path in args.files:
        result = validate_file(file_path, args.ledger)
        all_results.append(result)

        if result["failed"] > 0 or result["global_errors"]:
            any_fail = True
        if args.strict:
            for check in result["checks"]:
                if check["warnings"]:
                    any_fail = True

    # Output
    if args.format == "text":
        for result in all_results:
            print(format_text(result))
    else:
        output = all_results if len(all_results) > 1 else all_results[0]
        print(json.dumps(output, indent=2, ensure_ascii=False))

    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
