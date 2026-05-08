#!/usr/bin/env python3
"""S3 Output Structural Validator — validates §S3.1-§S3.10 section completeness and content."""

import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED_SECTIONS = [f"§S3.{i}" for i in range(1, 11)]

BANNED_WORDS = {
    "checked", "verified", "confirmed", "good", "fine",
    "ok", "done", "yes", "\u2014", "n/a", "see above",
}

SPORT_KEYWORDS = {
    "Tennis": ["ATP", "WTA", "ITF", "Grand Slam", "Roland Garros",
               "Wimbledon", "US Open tennis", "Australian Open"],
    "Football": ["Premier League", "La Liga", "Bundesliga", "Serie A",
                 "Ligue 1", "Champions League", "Europa League", "MLS",
                 "Copa", "FIFA", "Eredivisie", "Ekstraklasa", "Conference League",
                 "Super Lig", "Championship", "League One", "League Two",
                 "World Cup", "Primeira Liga", "Süper Lig"],
    "Basketball": ["NBA", "Euroleague", "EuroBasket", "FIBA", "ACB", "ABA Liga"],
    "Volleyball": ["CEV", "PlusLiga", "SuperLega", "Volleyball"],
    "Baseball": ["MLB", "NPB", "KBO"],
    "Hockey": ["NHL", "KHL", "SHL"],
    "CS2": ["CS2", "Counter-Strike", "ESL Pro", "BLAST Premier"],
    "Handball": ["EHF", "Handball"],
}


def detect_sport(text):
    """Detect sport from candidate block content."""
    # Spec format: CANDIDATE: Football — Team vs Team | ...
    m = re.search(r'CANDIDATE:\s*(\w+)\s*[\u2014\u2013-]\s*', text[:500])
    if m:
        sport = m.group(1).strip()
        if sport[0].isupper() and len(sport) > 2:
            return sport

    first_block = text[:1500].upper()
    for sport, keywords in SPORT_KEYWORDS.items():
        for kw in keywords:
            if kw.upper() in first_block:
                return sport
    return "Unknown"


def parse_table_rows(section_text):
    """Extract data rows from a markdown table within section text.

    Returns list of rows, where each row is a list of cell strings.
    """
    lines = section_text.split("\n")
    rows = []
    in_table = False
    found_separator = False

    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            if found_separator and in_table:
                break
            continue

        if re.match(r"^\|[\s\-:|]+\|$", stripped):
            found_separator = True
            in_table = True
            continue

        if found_separator and in_table:
            cells = [c.strip() for c in stripped.split("|")]
            if cells and cells[0] == "":
                cells = cells[1:]
            if cells and cells[-1] == "":
                cells = cells[:-1]
            if cells:
                rows.append(cells)

    return rows


def find_header_cells(section_text):
    """Find header row cells from the first table in section text."""
    lines = section_text.split("\n")
    prev_row = None
    for line in lines:
        stripped = line.strip()
        if re.match(r"^\|[\s\-:|]+\|$", stripped) and prev_row is not None:
            cells = [c.strip() for c in prev_row.split("|")]
            cells = [c for c in cells if c]
            return cells
        if stripped.startswith("|"):
            prev_row = stripped
        else:
            prev_row = None
    return None


def check_banned_words(candidate_text):
    """Check all table cells in the candidate for banned sole-content words."""
    errors = []
    lines = candidate_text.split("\n")
    found_separator = False

    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            found_separator = False
            continue
        if re.match(r"^\|[\s\-:|]+\|$", stripped):
            found_separator = True
            continue
        if found_separator:
            cells = [c.strip() for c in stripped.split("|")]
            cells = [c for c in cells if c]
            for cell in cells:
                normalized = cell.lower().strip("*_ ")
                if normalized in BANNED_WORDS:
                    errors.append(
                        f"Banned word '{cell}' as sole cell content"
                    )

    return errors


def validate_s3_3(section_text, sport):
    """Validate §S3.3 ranking table: row count, safety values, empty cells."""
    errors = []
    warnings = []

    rows = parse_table_rows(section_text)
    min_rows = 4 if sport == "Football" else 3
    if len(rows) < min_rows:
        errors.append(
            f"§S3.3: expected \u2265{min_rows} data rows (sport={sport}), found {len(rows)}"
        )

    header = find_header_cells(section_text)
    safety_idx = None
    if header:
        for i, cell in enumerate(header):
            if "safety" in cell.lower():
                safety_idx = i
                break

    for row_num, row in enumerate(rows, 1):
        for col_num, cell in enumerate(row, 1):
            if cell.strip() == "":
                errors.append(f"§S3.3: empty cell in row {row_num}, column {col_num}")

        if safety_idx is not None and safety_idx < len(row):
            raw = row[safety_idx].strip().strip("*")
            try:
                val = float(raw)
                if not 0.0 <= val <= 1.0:
                    errors.append(
                        f"§S3.3: safety value {raw} outside 0.00-1.00 in row {row_num}"
                    )
            except ValueError:
                errors.append(
                    f"§S3.3: safety value '{raw}' is not a decimal float in row {row_num}"
                )

    return errors, warnings


def validate_s3_4(section_text):
    """Validate §S3.4 three-way check: 3 rows, numeric values, verdict."""
    errors = []
    warnings = []

    rows = parse_table_rows(section_text)
    if len(rows) < 3:
        errors.append(
            f"§S3.4: expected 3 data rows (L10, H2H, L5), found {len(rows)}"
        )

    has_verdict = bool(
        re.search(r"\bSUPPORT\b|\bCONFLICT\b|\bREJECT\b", section_text, re.IGNORECASE)
    )
    if not has_verdict:
        errors.append("§S3.4: missing alignment verdict (SUPPORT/CONFLICT/REJECT)")

    header = find_header_cells(section_text)
    value_idx = None
    if header:
        for i, cell in enumerate(header):
            if "value" in cell.lower():
                value_idx = i
                break

    if value_idx is not None:
        for row_num, row in enumerate(rows, 1):
            if value_idx < len(row):
                val = row[value_idx].strip()
                if not re.search(r"\d", val):
                    low = val.lower()
                    if not any(w in low for w in ("n/a", "missing", "blind", "none")):
                        errors.append(
                            f"§S3.4: no numeric value in Value column, row {row_num}: '{val}'"
                        )

    return errors, warnings


def validate_s3_9(section_text):
    """Validate §S3.9 sources table: ≥2 rows."""
    errors = []
    rows = parse_table_rows(section_text)
    if len(rows) < 2:
        errors.append(f"§S3.9: expected \u22652 source rows, found {len(rows)}")
    return errors


def validate_s3_10(section_text):
    """Validate §S3.10 depth proof: ≥5 metric rows with numeric values."""
    errors = []
    rows = parse_table_rows(section_text)
    if len(rows) < 5:
        errors.append(f"§S3.10: expected \u22655 metric rows, found {len(rows)}")

    numeric_rows = sum(1 for row in rows if any(re.search(r"\d", c) for c in row))
    if rows and numeric_rows < len(rows):
        errors.append(
            f"§S3.10: only {numeric_rows}/{len(rows)} rows contain numeric values"
        )

    return errors


def get_section_text(content, section_marker):
    """Extract text for a section from its header to the next §S3.X or END CANDIDATE."""
    pattern = re.escape(section_marker)
    match = re.search(rf"^(?:#{{{2,3}}}\s*)?{pattern}\b.*$", content, re.MULTILINE)
    if not match:
        return None

    start = match.end()
    end_match = re.search(
        r"^(?:#{2,3}\s*)?(?:§S3\.\d+|══\s*END CANDIDATE)",
        content[start:],
        re.MULTILINE,
    )
    if end_match:
        return content[start : start + end_match.start()]
    return content[start:]


def split_candidates(content):
    """Split file content into (header_line, block_text) tuples."""
    start_re = re.compile(r"^(?:#{2,3}\s*)?══\s*CANDIDATE\b", re.MULTILINE)
    end_re = re.compile(r"^(?:#{2,3}\s*)?══\s*END CANDIDATE\b", re.MULTILINE)

    candidates = []
    for m in start_re.finditer(content):
        header_end = content.index("\n", m.start())
        header_line = content[m.start() : header_end].strip()
        block_start = m.start()

        end_match = end_re.search(content, header_end)
        if end_match:
            block_end = content.index("\n", end_match.start()) + 1
        else:
            block_end = len(content)

        candidates.append((header_line, content[block_start:block_end]))

    return candidates


def extract_candidate_name(header_line):
    """Extract readable name from candidate header."""
    # ## ══ CANDIDATE T5: Daniil Medvedev vs Flavio Cobolli ══
    m = re.search(r"CANDIDATE\s+\w+:\s*(.+?)\s*══", header_line)
    if m:
        return m.group(1).strip()
    # ### ══ CANDIDATE: Football — Liverpool vs Arsenal | Premier League | 16:30 ══
    m = re.search(r"CANDIDATE:\s*(.+?)\s*══", header_line)
    if m:
        return m.group(1).strip()
    return header_line


def validate_candidate(header_line, content):
    """Validate a single candidate block against all rules."""
    name = extract_candidate_name(header_line)
    sport = detect_sport(content)

    result = {
        "name": name,
        "sport": sport,
        "status": "PASS",
        "sections_found": [],
        "sections_missing": [],
        "errors": [],
        "warnings": [],
    }

    # 1. Section completeness
    for section in REQUIRED_SECTIONS:
        if re.search(rf"{re.escape(section)}\b", content):
            result["sections_found"].append(section)
        else:
            result["sections_missing"].append(section)
            result["errors"].append(f"Missing section: {section}")

    # 2. Banned words in table cells
    result["errors"].extend(check_banned_words(content))

    # 3. §S3.3 ranking table
    s3_3 = get_section_text(content, "§S3.3")
    if s3_3:
        errs, warns = validate_s3_3(s3_3, sport)
        result["errors"].extend(errs)
        result["warnings"].extend(warns)

    # 4. §S3.4 three-way cross-check
    s3_4 = get_section_text(content, "§S3.4")
    if s3_4:
        errs, warns = validate_s3_4(s3_4)
        result["errors"].extend(errs)
        result["warnings"].extend(warns)

    # 5. §S3.9 sources
    s3_9 = get_section_text(content, "§S3.9")
    if s3_9:
        errs = validate_s3_9(s3_9)
        result["errors"].extend(errs)

    # 6. §S3.10 depth proof
    s3_10 = get_section_text(content, "§S3.10")
    if s3_10:
        errs = validate_s3_10(s3_10)
        result["errors"].extend(errs)

    if result["errors"]:
        result["status"] = "FAIL"

    return result


def validate_file(filepath):
    """Validate a single S3 markdown file."""
    path = Path(filepath)
    if not path.exists():
        return {
            "file": str(filepath),
            "total_candidates": 0,
            "passed": 0,
            "failed": 0,
            "candidates": [],
            "error": f"File not found: {filepath}",
        }

    content = path.read_text(encoding="utf-8")

    if not content.strip():
        return {
            "file": path.name,
            "total_candidates": 0,
            "passed": 0,
            "failed": 0,
            "candidates": [],
            "error": "Empty file",
        }

    candidates = split_candidates(content)

    if not candidates:
        return {
            "file": path.name,
            "total_candidates": 0,
            "passed": 0,
            "failed": 0,
            "candidates": [],
            "error": "No candidates found in file",
        }

    results = []
    for header, block in candidates:
        results.append(validate_candidate(header, block))

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")

    return {
        "file": path.name,
        "total_candidates": len(results),
        "passed": passed,
        "failed": failed,
        "candidates": results,
    }


def format_text(report):
    """Format report as human-readable text."""
    lines = [
        f"═══ S3 Validation: {report['file']} ═══",
        f"Candidates: {report['total_candidates']}  "
        f"Passed: {report['passed']}  Failed: {report['failed']}",
    ]

    if "error" in report:
        lines.append(f"ERROR: {report['error']}")

    lines.append("")

    for c in report["candidates"]:
        icon = "\u2713" if c["status"] == "PASS" else "\u2717"
        lines.append(f"  {icon} {c['name']} [{c['sport']}] \u2192 {c['status']}")

        if c["sections_missing"]:
            lines.append(f"    Missing: {', '.join(c['sections_missing'])}")

        for err in c["errors"]:
            lines.append(f"    ERROR: {err}")
        for warn in c["warnings"]:
            lines.append(f"    WARN:  {warn}")

    lines.append("")
    lines.append(f"Result: {'FAIL' if report['failed'] > 0 else 'PASS'}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Validate S3 deep statistical analysis markdown against §3.0e template."
    )
    parser.add_argument("files", nargs="+", help="Path(s) to S3 markdown files")
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 on warnings too",
    )
    args = parser.parse_args()

    all_reports = []
    any_fail = False
    any_warn = False

    for filepath in args.files:
        report = validate_file(filepath)
        all_reports.append(report)
        if report["failed"] > 0:
            any_fail = True
        for c in report.get("candidates", []):
            if c.get("warnings"):
                any_warn = True

    if args.format == "text":
        for report in all_reports:
            print(format_text(report))
    else:
        output = all_reports[0] if len(all_reports) == 1 else all_reports
        print(json.dumps(output, indent=2))

    any_error = any("error" in r for r in all_reports)
    if any_fail or any_error:
        sys.exit(1)
    if args.strict and any_warn:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
