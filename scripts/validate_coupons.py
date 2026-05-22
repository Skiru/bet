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
LEG_ODDS_RE = re.compile(r"(?:@\s*|[\(\[])([\d.]+)[\)\]]?")

# Pattern to extract event names from description
# Matches: "Team A vs Team B: ..." or "Team A vs Team B (Competition) —"
EVENT_RE = re.compile(
    r"([A-ZÀ-Ža-zà-ž0-9\s.'&\-]+?)\s+vs\s+([A-ZÀ-Ža-zà-ž0-9\s.'&\-]+?)"
    r"\s*(?:\([^)]+\))?\s*(?:—|–|-|:)"
)


def _split_table_cells(line: str) -> list[str] | None:
    """Split a markdown table row into cells, preserving positional info."""
    line = line.strip()
    if not line.startswith("|"):
        return None
    cells = line.split("|")
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return [c.strip() for c in cells]


def _is_separator_row(cells: list[str]) -> bool:
    """Check if cells form a markdown table separator row (|---|---|)."""
    return all(re.match(r"^-+$", c.strip()) for c in cells if c.strip())


def _is_header_row(cells: list[str]) -> bool:
    """Detect header rows by absence of data indicators."""
    joined = " ".join(cells).lower()
    if any(ind in joined for ind in [" vs ", "≥", "@", "razem", " pln"]):
        return False
    if re.search(r"noga\s+\d", joined):
        return False
    if any(re.match(r"(?:CP|COMBO|CK-COMBO|EXT)-", c.strip(), re.I) for c in cells):
        return False
    return True


def _extract_odds_value(text: str) -> float | None:
    """Extract odds from text like '≥1.68' or '@2.50'."""
    m = re.match(r"^[≥@]\s*([\d.]+)$", text.strip())
    return float(m.group(1)) if m else None


def _extract_single_row_meta(coupon: dict, cells: list[str]):
    """Extract combined odds, stake, return from single-row coupon format.

    Expected format: | # | CP-ID | description | combined_odds | stake PLN | return PLN |
    """
    # Find cells that look like plain numbers (combined odds) or PLN amounts
    for cell in cells:
        c = cell.replace("**", "").strip()
        if not c:
            continue
        # Plain float (not in description cell) = combined odds
        if re.match(r"^\d+\.\d+$", c) and not re.search(r"\svs\.?\s", c, re.I):
            val = float(c)
            # Combined odds are typically > 1.5 and not already set
            if coupon["combined_odds_stated"] == 0.0 and val > 1.0:
                coupon["combined_odds_stated"] = val
                continue
        # PLN amount
        pln_match = re.match(r"^([\d.]+)\s*PLN$", c)
        if pln_match:
            val = float(pln_match.group(1))
            if coupon["stake"] == 0.0:
                coupon["stake"] = val
            elif coupon["potential_return"] == 0.0:
                coupon["potential_return"] = val


def _new_coupon(idx: int, coupon_id: str, is_combo: bool = False) -> dict:
    """Create a fresh coupon dict."""
    return {
        "row_num": idx,
        "coupon_id": coupon_id,
        "description": "",
        "legs_text": [],
        "legs_odds": [],
        "combined_odds_stated": 0.0,
        "stake": 0.0,
        "potential_return": 0.0,
        "events": [],
        "is_combo": is_combo,
        "is_single": False,
    }


def _extract_leg(coupon: dict, cells: list[str]):
    """Extract leg data from table cells by content detection."""
    event = ""
    market = ""
    odds = None

    for cell in cells:
        c = cell.replace("**", "").strip()
        if not c:
            continue
        if re.match(r"^\d+$", c):
            continue
        if re.match(r"^Noga\s+\d+$", c, re.I):
            continue
        if re.match(r"^(?:CP|EXT|COMBO|CK-COMBO)-", c, re.I):
            continue
        if c.startswith("\u2705") or c.upper().startswith("SPRAWDŹ"):
            continue

        # Multi-leg cell: split on " + " when surrounded by event-like content
        if " + " in c and re.search(r"\svs\.?\s", c, re.I):
            sub_legs = re.split(r"\s\+\s", c)
            for sub_leg in sub_legs:
                sub_leg = sub_leg.strip()
                if not sub_leg:
                    continue
                sub_odds = LEG_ODDS_RE.findall(sub_leg)
                if sub_odds:
                    coupon["legs_odds"].append(float(sub_odds[-1]))
                coupon["legs_text"].append(sub_leg)
                ev = EVENT_RE.search(sub_leg)
                if ev:
                    coupon["events"].append(
                        normalize_event(f"{ev.group(1).strip()} vs {ev.group(2).strip()}")
                    )
                if not coupon.get("description"):
                    coupon["description"] = sub_leg
                else:
                    coupon["description"] += " + " + sub_leg
            continue

        odds_val = _extract_odds_value(c)
        if odds_val is not None:
            odds = odds_val
            continue

        if re.search(r"\svs\.?\s", c, re.I) and not event:
            event = c
            continue

        if not market and any(t in c.lower() for t in POLISH_TERMS):
            market = c
            continue

        if not event and " " in c and len(c) > 5:
            event = c
        elif not market:
            market = c

    if not event and not market:
        return

    leg = f"{event} — {market}" if event and market else (event or market)
    coupon["legs_text"].append(leg)

    if odds:
        coupon["legs_odds"].append(odds)

    ev = EVENT_RE.search(event or leg)
    if ev:
        coupon["events"].append(
            normalize_event(f"{ev.group(1).strip()} vs {ev.group(2).strip()}")
        )

    if coupon["description"]:
        coupon["description"] += " + "
    coupon["description"] += leg


def _extract_summary(coupon: dict, cells: list[str]):
    """Extract combined odds, stake, return from RAZEM / summary row."""
    full = " ".join(c.replace("**", "") for c in cells)

    eq_matches = re.findall(r"=\s*([\d.]+)", full)
    if eq_matches:
        coupon["combined_odds_stated"] = float(eq_matches[-1])

    pln_matches = re.findall(r"([\d.]+)\s*PLN", full)
    if len(pln_matches) >= 2:
        coupon["stake"] = float(pln_matches[0])
        coupon["potential_return"] = float(pln_matches[1])
    elif len(pln_matches) == 1:
        if "stawka" in full.lower():
            coupon["stake"] = float(pln_matches[0])
        else:
            coupon["potential_return"] = float(pln_matches[0])


def _parse_legacy_coupons(lines: list[str]) -> list[dict]:
    """Parse legacy single-row coupon format (one row per coupon)."""
    coupons = []
    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.split("|")]
        parts = [p for p in parts if p != ""]
        if len(parts) < 6:
            continue
        try:
            row_num = int(parts[0])
        except ValueError:
            continue
        coupon_id = parts[1].strip()
        description = parts[2].strip()
        if coupon_id.startswith("-") or coupon_id.lower() in ("kupon", "#"):
            continue
        if not re.match(r"(?:CP|COMBO|CK-COMBO|EXT)", coupon_id, re.I):
            continue
        try:
            combined_odds = float(parts[3])
            stake = float(re.sub(r"[^\d.]", "", parts[4]))
            potential_return = float(re.sub(r"[^\d.]", "", parts[5]))
        except (ValueError, IndexError):
            continue
        legs_odds = [float(o) for o in LEG_ODDS_RE.findall(description)]
        legs_text = re.split(r"<br\s*/?>|\s\+\s", description)
        legs_text = [lt.strip() for lt in legs_text if lt.strip()]
        events = []
        for leg_text in legs_text:
            ev_match = EVENT_RE.search(leg_text)
            if ev_match:
                event_name = (
                    f"{ev_match.group(1).strip()} vs {ev_match.group(2).strip()}"
                )
                events.append(normalize_event(event_name))
            else:
                parts_split = re.split(
                    r"\s*(?:—|–|:)\s*", leg_text, maxsplit=1
                )
                if parts_split:
                    events.append(normalize_event(parts_split[0].strip()))
        is_combo = bool(
            re.search(r"(?:COMBO|CK-COMBO|COMB\d|EXT)", coupon_id, re.I)
        )
        is_single = bool(re.search(r"SINGLE", coupon_id, re.I))
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
            "is_single": is_single,
        })
    return coupons


def parse_coupon_tables(md_text: str) -> list[dict]:
    """Extract coupon entries from markdown tables.

    Supports:
    - Multi-row format: CP-/EXT- ID in first column, legs as rows, RAZEM summary
    - Heading format: ### CP-xxx / ### COMBO-xxx heading followed by table
    - Legacy single-row format: row number + coupon ID + description in one row
    """
    coupons = []
    lines = md_text.split("\n")

    pending_id = None   # coupon ID from ### heading
    current = None      # coupon dict being built
    idx = 0

    for line_raw in lines:
        line = line_raw.strip()

        # --- Detect coupon heading (### CP-xxx, ### COMBO-xxx) ---
        hm = re.match(
            r"^#{2,4}\s+((?:CP|COMBO|CK-COMBO|EXT)-[^\s\u2014\u2013\-]+)", line
        )
        if hm:
            if current and current["legs_text"]:
                coupons.append(current)
                current = None
            pending_id = hm.group(1).strip()
            continue

        # --- Non-table row ---
        if not line.startswith("|"):
            if line and current and current["legs_text"]:
                coupons.append(current)
                current = None
            continue

        # --- Table row ---
        cells = _split_table_cells(line)
        if not cells or _is_separator_row(cells):
            continue
        if _is_header_row(cells):
            continue

        joined = " ".join(c.replace("**", "") for c in cells).lower()

        # --- RAZEM / summary row ---
        is_summary = "razem" in joined or (
            "kurs" in joined and "=" in joined
            and ("pln" in joined or "stawka" in joined)
        )
        if is_summary:
            if current:
                _extract_summary(current, cells)
                coupons.append(current)
                current = None
                pending_id = None
            continue

        # --- Coupon start from first or second column (CP-xxx in cells[0] or cells[1]) ---
        # Require date segment (YYYYMMDD) to avoid matching verification tables
        id_match = re.match(r"((?:CP|EXT)-\d{8}-\S+)", cells[0])
        if not id_match and len(cells) > 1:
            # Also check cells[1] — SINGLE BETS table has row# in cells[0]
            cleaned = cells[1].replace("🏆", "").strip()
            id_match = re.match(r"((?:CP|EXT)-\d{8}-\S+)", cleaned)
        if id_match:
            if current and current["legs_text"]:
                coupons.append(current)
            idx += 1
            coupon_id = id_match.group(1)
            current = _new_coupon(idx, coupon_id)
            current["is_single"] = bool(re.search(r"SINGLE", coupon_id, re.I))
            _extract_leg(current, cells)
            # For single-row format: extract combined odds, stake, return from remaining cells
            _extract_single_row_meta(current, cells)
            pending_id = None
            continue

        # --- Create coupon from heading if needed ---
        if pending_id and not current:
            idx += 1
            is_combo = bool(re.search(r"COMBO|CK-COMBO", pending_id, re.I))
            current = _new_coupon(idx, pending_id, is_combo=is_combo)

        # --- Add leg to current coupon ---
        if current:
            _extract_leg(current, cells)

    # Finalize pending coupon
    if current and current["legs_text"]:
        coupons.append(current)

    # Legacy fallback
    if not coupons:
        coupons = _parse_legacy_coupons(lines)

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
    core_coupons = [c for c in coupons if not c["is_combo"] and not c.get("is_single")]

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


def check_fixture_status(coupons: list[dict], date: str) -> list[str]:
    """V0: Check that no coupon legs reference postponed/cancelled fixtures.

    Queries the fixtures DB for non-playable statuses (PST, CANC, ABD, AWD, WO, SUSP)
    and cross-references against team names found in coupon legs.
    """
    errors = []
    NON_PLAYABLE = {"PST", "CANC", "ABD", "AWD", "WO", "SUSP"}
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from bet.db.connection import get_db
        with get_db() as conn:
            rows = conn.execute(
                """SELECT t1.name, t2.name, f.status
                   FROM fixtures f
                   JOIN teams t1 ON t1.id = f.home_team_id
                   JOIN teams t2 ON t2.id = f.away_team_id
                   WHERE f.kickoff LIKE ? || '%'
                   AND f.status IN ({})""".format(
                    ",".join(f"'{s}'" for s in NON_PLAYABLE)
                ),
                (date,),
            ).fetchall()
        if not rows:
            return errors

        non_playable_teams = []
        for home, away, status in rows:
            non_playable_teams.append((home.lower(), away.lower(), status))

        # Check each coupon's events against non-playable fixtures
        for coupon in coupons:
            for event in coupon.get("events", []):
                event_lower = event.lower()
                for home, away, status in non_playable_teams:
                    # Use longest word (≥3 chars) from each team for matching
                    # Avoids false positives from common prefixes like "fc", "sc"
                    home_words = [w for w in home.split() if len(w) >= 3]
                    away_words = [w for w in away.split() if len(w) >= 3]
                    home_token = max(home_words, key=len) if home_words else home
                    away_token = max(away_words, key=len) if away_words else away
                    if home_token and away_token and home_token in event_lower and away_token in event_lower:
                        errors.append(
                            f"FIXTURE_{status}: {coupon['coupon_id']} contains "
                            f"'{event}' — match is {status} (postponed/cancelled)"
                        )
                        break
    except Exception:
        pass  # DB not available — skip check gracefully
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
        # On first runs, ledger doesn't exist yet — skip cross-reference (warning, not error)
        return []

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

    # Global check V0: fixture status (PST/CANC/ABD)
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", file_path.name)
    if date_match:
        status_errors = check_fixture_status(coupons, date_match.group(1))
        result["global_errors"].extend(status_errors)

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

        # 4. Minimum legs check (skip for singles — 1-leg is valid)
        if len(coupon["legs_text"]) < 2 and not coupon.get("is_single"):
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
    from agent_output import AgentOutput, add_agent_args

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
    add_agent_args(parser)
    args = parser.parse_args()

    out = AgentOutput("s8_validate_coupons", verbose=args.verbose, stop_on_error=args.stop_on_error)

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

    # AGENT_SUMMARY
    total_checks = sum(r.get("passed", 0) + r.get("failed", 0) for r in all_results)
    total_passed = sum(r.get("passed", 0) for r in all_results)
    total_failed = sum(r.get("failed", 0) for r in all_results)
    total_warnings = sum(
        sum(len(c.get("warnings", [])) for c in r.get("checks", []))
        for r in all_results
    )

    if not all_results:
        verdict = "FAILED"
    elif any_fail:
        verdict = "FAILED"
    else:
        verdict = "OK"

    out.summary(
        verdict=verdict,
        metrics={
            "files_validated": len(all_results),
            "total_checks": total_checks,
            "passed": total_passed,
            "failed": total_failed,
            "warnings": total_warnings,
        },
        issues=[{"level": "error", "message": "No coupon files found to validate"}] if not all_results else [],
    )

    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
