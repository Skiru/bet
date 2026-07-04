#!/usr/bin/env python3
"""S2 tipster scraper v2 live dry-run entrypoint.

This script is intentionally compliance-first and shadow-only:
- it requires an explicit local terms/robots review JSON;
- it respects robots.txt through RobotFileParser;
- it fetches only public HTML entrypoints/detail links;
- it never uses stealth, CAPTCHA/Cloudflare bypass, auth, premium, private APIs,
  bookmaker redirects or commercial go-links;
- it writes evidence-only artifacts that must not become bets/coupons.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bet.tipsters.compliance import DomainRateLimiter, RobotsCache  # noqa: E402
from bet.tipsters.contracts import ExtractionResult, ExtractorVerdict  # noqa: E402
from bet.tipsters.extractors import dispatch_extract, discover_public_detail_links  # noqa: E402
from bet.tipsters.fetcher import FetchConfig, fetch_public_html  # noqa: E402
from bet.tipsters.source_registry import CORE_SOURCE_IDS, SOURCES  # noqa: E402
from bet.tipsters.storage import persist_sqlite, write_json_artifact  # noqa: E402


REVIEWED_AT_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
PLACEHOLDER_REVIEW_VALUES = {"", "REPLACE_WITH_OPERATOR", "REPLACE_WITH_UTC_TIMESTAMP"}


def load_review_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("terms/robots review file must be a JSON object")
    reviews = data.get("source_reviews")
    if not isinstance(reviews, dict):
        raise ValueError("terms/robots review file must contain object key: source_reviews")
    return data


def _review_gate_details(review_data: dict[str, Any], source_id: str) -> dict[str, Any]:
    review = review_data.get("source_reviews", {}).get(source_id, {})
    if not isinstance(review, dict):
        return {
            "allowed": False,
            "reason": "missing_or_invalid_source_review",
            "required_flags_missing": [],
            "invalid_attestation": [],
        }

    required_true = ("terms_reviewed", "robots_reviewed", "public_html_only", "no_auth_no_premium_no_bypass")
    missing = [k for k in required_true if review.get(k) is not True]
    if missing:
        return {
            "allowed": False,
            "reason": "missing_required_review_flags:" + ",".join(missing),
            "required_flags_missing": missing,
            "invalid_attestation": [],
        }

    invalid_attestation: list[str] = []
    reviewed_by = str(review.get("reviewed_by", "")).strip()
    reviewed_at_utc = str(review.get("reviewed_at_utc", "")).strip()
    if reviewed_by in PLACEHOLDER_REVIEW_VALUES:
        invalid_attestation.append("reviewed_by")
    if reviewed_at_utc in PLACEHOLDER_REVIEW_VALUES or not REVIEWED_AT_UTC_RE.match(reviewed_at_utc):
        invalid_attestation.append("reviewed_at_utc")
    if invalid_attestation:
        return {
            "allowed": False,
            "reason": "INVALID_REVIEW_ATTESTATION",
            "required_flags_missing": [],
            "invalid_attestation": invalid_attestation,
        }

    status = str(review.get("status", "")).lower()
    if status not in {"allow_live_dry_run", "allow_shadow_dry_run"}:
        return {
            "allowed": False,
            "reason": f"invalid_review_status:{status or 'empty'}",
            "required_flags_missing": [],
            "invalid_attestation": [],
        }
    return {
        "allowed": True,
        "reason": "review_allows_live_dry_run",
        "required_flags_missing": [],
        "invalid_attestation": [],
    }


def review_allows_source(review_data: dict[str, Any], source_id: str) -> tuple[bool, str]:
    details = _review_gate_details(review_data, source_id)
    return bool(details["allowed"]), str(details["reason"])


def _blocked_reason(reason: str) -> str:
    upper = reason.upper()
    if "BLOCK_ROBOTS" in upper:
        detail = reason.rsplit(":", 1)[-1]
        return f"BLOCK_ROBOTS:{detail}"
    if "BLOCK_TERMS" in upper:
        detail = reason.rsplit(":", 1)[-1]
        return f"BLOCK_TERMS:{detail}"
    if "BLOCK_AUTH_REQUIRED" in upper:
        detail = reason.rsplit(":", 1)[-1]
        return f"BLOCK_AUTH_REQUIRED:{detail}"
    return f"FETCH_BLOCK:{reason}"


def _empty_result(
    source_id: str,
    url: str,
    warning: str,
    *,
    block_reason: str | None = None,
    robots_blocked_live: bool = False,
    live_fetch_allowed: bool = True,
    fallback: str | None = None,
    skip_reason: str | None = None,
    required_flags_missing: list[str] | None = None,
    invalid_attestation: list[str] | None = None,
) -> ExtractionResult:
    return ExtractionResult(
        source_id=source_id,
        url=url,
        verdict=ExtractorVerdict.EMPTY,
        picks=[],
        warnings=[warning],
        parser_version="tipster_parser_v2.3_final_source_specific",
        block_reason=block_reason,
        robots_blocked_live=robots_blocked_live,
        live_fetch_allowed=live_fetch_allowed,
        fallback=fallback,
        skip_reason=skip_reason,
        required_flags_missing=required_flags_missing or [],
        invalid_attestation=invalid_attestation or [],
    )


def fetch_extract_source(source_id: str, *, review_data: dict[str, Any], max_pages: int, timeout: float, max_bytes: int) -> list[ExtractionResult]:
    policy = SOURCES[source_id]
    gate = _review_gate_details(review_data, source_id)
    if not gate["allowed"]:
        reason = str(gate["reason"])
        print(f"[live-dry-run][{source_id}] SKIP {reason}")
        return [
            _empty_result(
                source_id,
                policy.entrypoints[0],
                reason,
                live_fetch_allowed=False,
                fallback="manual_review",
                skip_reason=reason,
                required_flags_missing=list(gate["required_flags_missing"]),
                invalid_attestation=list(gate["invalid_attestation"]),
            )
        ]

    robots = RobotsCache(user_agent="skiru-bet-research-bot")
    limiter = DomainRateLimiter(min_delay_seconds=max(policy.min_delay_seconds, 2.0))
    config = FetchConfig(timeout_seconds=timeout, max_bytes=max_bytes)
    results: list[ExtractionResult] = []
    urls_seen: list[str] = []

    for entrypoint in policy.entrypoints:
        if len(urls_seen) >= max_pages:
            break
        outcome = fetch_public_html(policy, entrypoint, robots=robots, limiter=limiter, terms_reviewed=True, config=config)
        if not outcome.allowed or outcome.document is None:
            print(f"[live-dry-run][{source_id}] FETCH_BLOCK {entrypoint} reason={outcome.reason} status={outcome.status_code}")
            block_reason = _blocked_reason(outcome.reason)
            results.append(_empty_result(
                source_id,
                entrypoint,
                f"fetch_block:{outcome.reason}",
                block_reason=block_reason,
                robots_blocked_live="BLOCK_ROBOTS" in block_reason,
                live_fetch_allowed=False,
                fallback="fixture_snapshot_only",
            ))
            continue
        print(f"[live-dry-run][{source_id}] FETCH_OK {entrypoint} status={outcome.status_code} bytes={len(outcome.document.html)}")
        urls_seen.append(entrypoint)
        parsed = dispatch_extract(outcome.document, source_id)
        print(f"[live-dry-run][{source_id}] PARSE {entrypoint} verdict={parsed.verdict.value} picks={parsed.pick_count} warnings={','.join(parsed.warnings) or '-'}")
        results.append(parsed)

        for detail_url in discover_public_detail_links(outcome.document, source_id):
            if len(urls_seen) >= max_pages:
                break
            if detail_url in urls_seen:
                continue
            detail = fetch_public_html(policy, detail_url, robots=robots, limiter=limiter, terms_reviewed=True, config=config)
            if not detail.allowed or detail.document is None:
                print(f"[live-dry-run][{source_id}] DETAIL_BLOCK {detail_url} reason={detail.reason} status={detail.status_code}")
                block_reason = _blocked_reason(detail.reason)
                results.append(_empty_result(
                    source_id,
                    detail_url,
                    f"detail_block:{detail.reason}",
                    block_reason=block_reason,
                    robots_blocked_live="BLOCK_ROBOTS" in block_reason,
                    live_fetch_allowed=False,
                    fallback="fixture_snapshot_only",
                ))
                continue
            print(f"[live-dry-run][{source_id}] DETAIL_OK {detail_url} status={detail.status_code} bytes={len(detail.document.html)}")
            urls_seen.append(detail_url)
            parsed_detail = dispatch_extract(detail.document, source_id)
            print(f"[live-dry-run][{source_id}] DETAIL_PARSE {detail_url} verdict={parsed_detail.verdict.value} picks={parsed_detail.pick_count} warnings={','.join(parsed_detail.warnings) or '-'}")
            results.append(parsed_detail)

    if not results:
        results.append(_empty_result(source_id, policy.entrypoints[0], "no_fetch_attempts_or_no_entrypoints"))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="Run date in YYYY-MM-DD; used for artifact naming only")
    parser.add_argument("--terms-reviewed-json", required=True, type=Path, help="Local JSON file documenting robots/terms/public-only review per source")
    parser.add_argument("--source", action="append", choices=list(SOURCES.keys()), help="Source id to live dry-run. Repeatable. Defaults to forebet+predictz only.")
    parser.add_argument("--max-pages-per-source", type=int, default=1, help="Hard cap including entrypoint and discovered detail pages")
    parser.add_argument("--timeout-seconds", type=float, default=12.0)
    parser.add_argument("--max-bytes", type=int, default=2_000_000)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--sqlite-db", type=Path, default=None)
    parser.add_argument("--require-at-least-one-pick", action="store_true", help="Exit non-zero when total_picks is zero")
    args = parser.parse_args()

    review_data = load_review_file(args.terms_reviewed_json)
    source_ids = tuple(args.source) if args.source else ("forebet", "predictz")
    all_results: list[ExtractionResult] = []
    started = datetime.now(timezone.utc).isoformat()
    print(f"[live-dry-run] started_at_utc={started} sources={','.join(source_ids)} max_pages_per_source={args.max_pages_per_source}")

    for source_id in source_ids:
        all_results.extend(fetch_extract_source(
            source_id,
            review_data=review_data,
            max_pages=max(1, args.max_pages_per_source),
            timeout=args.timeout_seconds,
            max_bytes=args.max_bytes,
        ))

    out = args.out or Path("betting/data") / f"{args.date}_tipster_consensus_v2_live_dry_run.json"
    write_json_artifact(all_results, out)
    sqlite_counts = None
    if args.sqlite_db:
        sqlite_counts = persist_sqlite(all_results, args.sqlite_db)

    total_picks = sum(r.pick_count for r in all_results)
    sources_with_picks = len({r.source_id for r in all_results if r.pick_count > 0})
    print(f"[live-dry-run] wrote={out} results={len(all_results)} total_picks={total_picks} sources_with_picks={sources_with_picks}")
    if sqlite_counts:
        print(f"[live-dry-run] sqlite persisted picks={sqlite_counts['picks']} consensus={sqlite_counts['consensus']} db={args.sqlite_db}")
    print("[live-dry-run] decision_boundary=evidence_only_not_a_bet; no EV/stake/coupon/final recommendation produced")
    return 1 if args.require_at_least_one_pick and total_picks == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
