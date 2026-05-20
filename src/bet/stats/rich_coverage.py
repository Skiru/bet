"""Shared helpers for rich-stat coverage classification.

The probe, report, and inspector paths all need the same bucket semantics.
Keeping the classification logic here avoids drift between read-only callers.
"""

from __future__ import annotations

from collections import Counter

BASELINE_SOURCE = "league-profile-baseline"


def _normalize_required_keys(required_keys) -> list[str]:
    return [str(key) for key in required_keys]


def _rich_keys_found(
    rows,
    required_keys: list[str],
    allowed_sources: set[str] | None,
    baseline_source: str,
) -> list[str]:
    required_set = set(required_keys)
    allowed_set = set(allowed_sources) if allowed_sources is not None else None
    found: list[str] = []
    seen: set[str] = set()

    for row in rows or []:
        if not row:
            continue
        stat_key = str(row[0] or "")
        source = str(row[1] or "")
        if not stat_key or stat_key in seen or stat_key not in required_set:
            continue
        if source in {"", baseline_source}:
            continue
        if allowed_set is not None and source not in allowed_set:
            continue
        seen.add(stat_key)
        found.append(stat_key)

    return found


def classify_rich_coverage(
    rows,
    required_keys,
    allowed_sources: set[str] | None = None,
    baseline_source: str = BASELINE_SOURCE,
) -> dict:
    required_keys = _normalize_required_keys(required_keys)
    rows = list(rows or [])
    stat_keys = {str(row[0]) for row in rows if row and row[0] is not None}
    sources = {str(row[1] or "") for row in rows if row}
    rich_keys_found = _rich_keys_found(rows, required_keys, allowed_sources, baseline_source)
    missing_rich_keys = [key for key in required_keys if key not in rich_keys_found]

    if not rows:
        bucket = "no_data"
    elif len(rich_keys_found) == len(required_keys):
        bucket = "rich"
    else:
        non_baseline_sources = {source for source in sources if source not in {"", baseline_source}}
        if not non_baseline_sources:
            bucket = "baseline_only"
        elif stat_keys:
            bucket = "partial"
        else:
            bucket = "no_data"

    return {
        "bucket": bucket,
        "eligible": bucket in {"baseline_only", "partial"},
        "stat_keys": sorted(stat_keys),
        "sources": sorted(source for source in sources if source),
        "rich_keys_found": rich_keys_found,
        "missing_rich_keys": missing_rich_keys,
    }


def summarize_rich_coverage(team_details: list[dict] | None) -> dict:
    details = list(team_details or [])
    buckets = Counter(detail.get("bucket", "no_data") for detail in details)
    total = len(details)
    rich = buckets.get("rich", 0)
    eligible = buckets.get("baseline_only", 0) + buckets.get("partial", 0)

    return {
        "total": total,
        "rich": rich,
        "eligible": eligible,
        "baseline_only": buckets.get("baseline_only", 0),
        "partial": buckets.get("partial", 0),
        "no_data": buckets.get("no_data", 0),
        "completion_rate": round((rich / total) * 100, 1) if total else 0.0,
        "team_details": details,
    }