#!/usr/bin/env python3
"""Live test tennis adapters with real URLs.

Tests: tennisexplorer, atptour, tennisabstract adapters.
Verifies: parse output structure, field presence, logging, data quality.
"""
import json
import logging
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.adapters.tennisexplorer_adapter import parse as te_parse
from scripts.adapters.atptour_adapter import parse as atp_parse
from scripts.adapters.tennisabstract_adapter import parse as ta_parse

logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")
logger = logging.getLogger("live_test_tennis")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

REQUIRED_FIELDS = {"home", "away", "sport", "source"}
TENNIS_DESIRED_FIELDS = {"surface", "source_type", "league"}

TESTS = [
    {
        "name": "TennisExplorer - today's matches",
        "url": "https://www.tennisexplorer.com/matches/",
        "adapter": te_parse,
        "min_results": 1,
    },
    {
        "name": "TennisExplorer - main page",
        "url": "https://www.tennisexplorer.com/",
        "adapter": te_parse,
        "min_results": 1,
    },
    {
        "name": "ATP Tour - current scores",
        "url": "https://www.atptour.com/en/scores/current",
        "adapter": atp_parse,
        "min_results": 0,  # May be empty off-season
    },
    {
        "name": "TennisAbstract - ATP Elo",
        "url": "http://tennisabstract.com/reports/atp_elo_ratings.html",
        "adapter": ta_parse,
        "min_results": 50,
    },
    {
        "name": "TennisAbstract - WTA Elo",
        "url": "http://tennisabstract.com/reports/wta_elo_ratings.html",
        "adapter": ta_parse,
        "min_results": 50,
    },
]


def fetch(url: str, timeout: int = 30) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.error("FETCH FAILED %s: %s", url, e)
        return None


def validate_result(result: dict, test_name: str) -> list[str]:
    issues = []
    missing = REQUIRED_FIELDS - set(result.keys())
    if missing:
        issues.append(f"missing required fields: {missing}")
    if result.get("sport") != "tennis":
        issues.append(f"wrong sport: {result.get('sport')}")
    for field in TENNIS_DESIRED_FIELDS:
        if field not in result:
            issues.append(f"missing desired field: {field}")
    return issues


def run_test(test: dict) -> dict:
    name = test["name"]
    url = test["url"]
    adapter = test["adapter"]
    min_results = test["min_results"]

    logger.info("=" * 60)
    logger.info("TEST: %s", name)
    logger.info("URL:  %s", url)

    start = time.time()
    html = fetch(url)
    fetch_time = time.time() - start

    if html is None:
        return {"name": name, "status": "FETCH_FAILED", "fetch_time": fetch_time}

    logger.info("Fetched %d bytes in %.1fs", len(html), fetch_time)

    start = time.time()
    results = adapter(html, url)
    parse_time = time.time() - start

    logger.info("Parsed %d results in %.3fs", len(results), parse_time)

    # Validate results
    all_issues = []
    for i, r in enumerate(results[:5]):  # Check first 5
        issues = validate_result(r, name)
        if issues:
            all_issues.append(f"  result[{i}]: {issues}")

    # Report
    status = "PASS"
    if len(results) < min_results:
        status = "FAIL"
        logger.warning("FAIL: got %d results, expected >= %d", len(results), min_results)
    if all_issues:
        status = "WARN" if status == "PASS" else status
        for issue in all_issues:
            logger.warning(issue)

    # Show sample
    if results:
        sample = results[0]
        logger.info("Sample: %s", json.dumps(sample, indent=2, ensure_ascii=False)[:500])

    # Check for key fields
    surfaces = [r.get("surface", "") for r in results if r.get("surface")]
    match_urls = [r.get("match_url", "") for r in results if r.get("match_url")]
    source_types = set(r.get("source_type", "") for r in results if r.get("source_type"))
    elo_only = sum(1 for r in results if r.get("_elo_only"))

    logger.info("Surfaces: %d/%d have surface data", len(surfaces), len(results))
    logger.info("Match URLs: %d/%d have match_url", len(match_urls), len(results))
    logger.info("Source types: %s", source_types or "none")
    if elo_only:
        logger.info("Elo-only records: %d", elo_only)

    return {
        "name": name,
        "status": status,
        "count": len(results),
        "min_expected": min_results,
        "fetch_time": round(fetch_time, 2),
        "parse_time": round(parse_time, 3),
        "surfaces": len(surfaces),
        "match_urls": len(match_urls),
        "source_types": list(source_types),
        "elo_only": elo_only,
        "issues": all_issues,
    }


def main():
    logger.info("Tennis Adapter Live Test")
    logger.info("=" * 60)

    results = []
    for test in TESTS:
        result = run_test(test)
        results.append(result)
        logger.info("")

    # Summary
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    passed = sum(1 for r in results if r["status"] == "PASS")
    warned = sum(1 for r in results if r["status"] == "WARN")
    failed = sum(1 for r in results if r["status"] in ("FAIL", "FETCH_FAILED"))

    for r in results:
        logger.info("  [%s] %s — %d results (%.1fs fetch, %.3fs parse)",
                    r["status"], r["name"], r.get("count", 0),
                    r.get("fetch_time", 0), r.get("parse_time", 0))

    logger.info("")
    logger.info("Total: %d PASS, %d WARN, %d FAIL", passed, warned, failed)

    summary = {
        "verdict": "OK" if failed == 0 else "PARTIAL" if passed > 0 else "FAILED",
        "passed": passed,
        "warned": warned,
        "failed": failed,
        "tests": results,
    }
    print(f"AGENT_SUMMARY:{json.dumps(summary)}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
