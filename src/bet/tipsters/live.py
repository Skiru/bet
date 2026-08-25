"""Compliance-gated live tipster ingestion, as an importable module.

This is the logic that used to live only inside
``legacy/pipeline_steps/s2_tipsters_v2_live_dry_run.py``. It moved here for two
reasons. The pipeline needs to *call* it -- shelling out to a file under
``legacy/`` to feed a production column would make the quarantine meaningless --
and eleven tests were already importing it by filesystem path, so they broke the
moment the S0-S10 stack was quarantined. A module has one address; a script
reached by path has as many as there are callers.

Compliance posture is unchanged and deliberately conservative:

* nothing is fetched without a local operator attestation naming a reviewer and
  a timestamp (placeholders are rejected, not warned about);
* robots.txt is honoured through ``RobotFileParser``;
* only public HTML entrypoints and internally-discovered detail links;
* no stealth, no CAPTCHA/Cloudflare bypass, no auth, no premium, no private
  APIs, no bookmaker redirects, no commercial go-links;
* output is evidence, never a bet.

What this module adds beyond the script it replaces is **betting-day
attribution**. Every one of these sources publishes several days on one page.
The old runner kept whatever it parsed, so a run for today ingested yesterday's
and tomorrow's opinions with equal confidence and no field recording which was
which. :func:`filter_picks_for_date` drops what cannot be attributed to the
requested day and reports the count, because a consensus number built partly
from yesterday is not a consensus number.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .compliance import DomainRateLimiter, RobotsCache
from .contracts import ExtractionResult, ExtractorVerdict, TipsterPick
from .extractors import discover_public_detail_links, dispatch_extract
from .fetcher import FetchConfig, fetch_public_html
from .source_registry import CERTIFIED_SHADOW_SOURCE_IDS, SOURCES
from .zawodtyper import (
    build_zawodtyper_daily_url,
    build_zawodtyper_transport_warnings,
    fetch_zawodtyper_public_xhr_document,
)

REVIEWED_AT_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
PLACEHOLDER_REVIEW_VALUES = {"", "REPLACE_WITH_OPERATOR", "REPLACE_WITH_UTC_TIMESTAMP"}

PARSER_VERSION = "tipster_parser_v2.3_final_source_specific"

DEFAULT_REVIEW_PATH = Path("docs/pipeline/tipster_terms_review.local.json")

# Sources whose live parser is verified against a live run. Everything else stays
# out of the default set even when its attestation would allow a fetch: an
# attestation says the operator may look, not that the parser understands what
# it sees. Sportsgambler is attested and fetches cleanly but its listing parser
# produces fixture-list scaffolding rather than clubs (see
# normalization._SCAFFOLDING_MARKERS), so it is excluded until that is rewritten.
DEFAULT_LIVE_SOURCE_IDS: tuple[str, ...] = ("zawodtyper", "typersi")


def load_review_file(path: Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("terms/robots review file must be a JSON object")
    reviews = data.get("source_reviews")
    if not isinstance(reviews, dict):
        raise ValueError("terms/robots review file must contain object key: source_reviews")
    return data


def review_gate_details(review_data: dict[str, Any], source_id: str) -> dict[str, Any]:
    """Decide whether one source may be fetched live, and say precisely why not.

    The structured return (rather than a bool) is what lets the artifact record
    ``required_flags_missing`` and ``invalid_attestation`` per source, so a
    skipped source is visibly skipped instead of looking like a source that
    simply had no picks today.
    """
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

    if source_id == "zawodtyper" and review.get("allow_public_xhr_capture", False) is True:
        notes = str(review.get("notes", "")).lower()
        if "np_ajax.php" not in notes and "public xhr review" not in notes:
            return {
                "allowed": False,
                "reason": "zawodtyper_xhr_review_notes_must_mention_np_ajax_or_public_xhr_review",
                "required_flags_missing": [],
                "invalid_attestation": ["notes"],
            }
        cookie_policy = str(review.get("cookie_policy") or "no_cookie")
        if cookie_policy not in {
            "no_cookie",
            "technical_first_party_only",
            "ephemeral_first_party_public_analytics_allowed",
        }:
            return {
                "allowed": False,
                "reason": f"invalid_cookie_policy:{cookie_policy}",
                "required_flags_missing": [],
                "invalid_attestation": ["cookie_policy"],
            }
        if not isinstance(review.get("allowed_cookie_names", []), list):
            return {
                "allowed": False,
                "reason": "invalid_allowed_cookie_names",
                "required_flags_missing": [],
                "invalid_attestation": ["allowed_cookie_names"],
            }

    return {
        "allowed": True,
        "reason": "review_allows_live_dry_run",
        "required_flags_missing": [],
        "invalid_attestation": [],
    }


def review_allows_source(review_data: dict[str, Any], source_id: str) -> tuple[bool, str]:
    details = review_gate_details(review_data, source_id)
    return bool(details["allowed"]), str(details["reason"])


def _blocked_reason(reason: str) -> str:
    upper = reason.upper()
    for token in ("BLOCK_ROBOTS", "BLOCK_TERMS", "BLOCK_AUTH_REQUIRED"):
        if token in upper:
            return f"{token}:{reason.rsplit(':', 1)[-1]}"
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
    coverage_status: str | None = None,
) -> ExtractionResult:
    return ExtractionResult(
        source_id=source_id,
        url=url,
        verdict=ExtractorVerdict.EMPTY,
        picks=[],
        warnings=[warning],
        parser_version=PARSER_VERSION,
        block_reason=block_reason,
        robots_blocked_live=robots_blocked_live,
        live_fetch_allowed=live_fetch_allowed,
        fallback=fallback,
        skip_reason=skip_reason,
        required_flags_missing=required_flags_missing or [],
        invalid_attestation=invalid_attestation or [],
        expected_visible_count=None,
        extracted_count=0,
        coverage_ratio=None,
        coverage_status=coverage_status
        or ("NEEDS_PUBLIC_XHR_REVIEW" if "allow_public_xhr_capture" in warning or "XHR" in warning or source_id == "zawodtyper" else None),
    )


def resolve_target_entrypoints(source_id: str, date_str: str | None) -> tuple[list[str], str | None]:
    """Primary entrypoints and an optional fallback for one source and day."""
    policy = SOURCES[source_id]
    entrypoints = list(policy.entrypoints)
    fallback = None
    if source_id == "zawodtyper" and date_str:
        try:
            daily_url = build_zawodtyper_daily_url(datetime.strptime(date_str, "%Y-%m-%d"))
        except ValueError:
            return entrypoints, None
        entrypoints = [daily_url]
        fallback = policy.entrypoints[0] if policy.entrypoints else "https://www.zawodtyper.pl/"
    return entrypoints, fallback


# A pick's stated date is in the *source's* timezone, and ours is UTC. ZawodTyper
# publishes in Europe/Warsaw, so a fixture it lists at "2026-08-25 00:30" is
# 22:30 UTC on 2026-08-24, and a 22:30 UTC fixture on our day appears under its
# 2026-08-26. Measured on the live 2026-08-25 payload: 6 of 74 picks (8%) sat in
# that window, so exact date equality both keeps picks from the wrong day and
# drops picks from the right one. One day of tolerance covers every real
# offset; the precise arbiter is the event match, which requires the pick's
# teams to be a fixture in *this* day's event list.
DATE_TOLERANCE_DAYS = 1


def _days_apart(left: str, right: str) -> int | None:
    try:
        a = datetime.strptime(left, "%Y-%m-%d")
        b = datetime.strptime(right, "%Y-%m-%d")
    except ValueError:
        return None
    return abs((a - b).days)


def filter_picks_for_date(
    picks: list[TipsterPick], betting_date: str, *, drop_undated: bool
) -> tuple[list[TipsterPick], dict[str, int]]:
    """Keep picks that could belong to ``betting_date``; report what was dropped.

    ``drop_undated`` is the honest knob. A source that states no fixture date
    (Typersi's tables, every generic HTML parse) cannot be attributed to a day
    from its own content; all we know is that it appeared on a page we requested
    for this day. Keeping those is defensible for a same-day run and indefensible
    for a backfill, so the caller decides and the count is always reported rather
    than folded silently into the total.

    ``adjacent_day_kept`` is counted separately from ``kept`` so a reader can see
    how much of the day leaned on the timezone tolerance rather than on an exact
    match.
    """
    kept: list[TipsterPick] = []
    counts = {
        "kept": 0,
        "exact_day": 0,
        "adjacent_day_kept": 0,
        "wrong_date": 0,
        "undated_kept": 0,
        "undated_dropped": 0,
        "settled": 0,
        "unparseable_date": 0,
    }
    for pick in picks:
        if pick.is_settled:
            counts["settled"] += 1
            continue
        if pick.match_date is None:
            if drop_undated:
                counts["undated_dropped"] += 1
                continue
            counts["undated_kept"] += 1
            kept.append(pick)
            continue
        distance = _days_apart(pick.match_date, betting_date)
        if distance is None:
            counts["unparseable_date"] += 1
            continue
        if distance == 0:
            counts["exact_day"] += 1
        elif distance <= DATE_TOLERANCE_DAYS:
            counts["adjacent_day_kept"] += 1
        else:
            counts["wrong_date"] += 1
            continue
        kept.append(pick)
    counts["kept"] = len(kept)
    return kept, counts


def _operator_risk_authorizes(operator_risk_data: dict[str, Any] | None, source_id: str) -> bool:
    if not operator_risk_data or operator_risk_data.get("operator_ack") is not True:
        return False
    entry = (operator_risk_data.get("allowed_sources") or {}).get(source_id)
    return isinstance(entry, dict) and entry.get("allow_operator_risk_public_read") is True


def fetch_extract_source(
    source_id: str,
    *,
    review_data: dict[str, Any],
    max_pages: int,
    timeout: float = 12.0,
    max_bytes: int = 2_000_000,
    date_str: str | None = None,
    verbose: bool = False,
    operator_risk_data: dict[str, Any] | None = None,
) -> list[ExtractionResult]:
    """Fetch and parse one source. Never raises; fails closed into EMPTY results.

    ``operator_risk_data`` is the ad-hoc research escape hatch retained for
    ``legacy/pipeline_steps/s2_tipsters_v2_live_dry_run.py``. Its own
    acknowledgement file states that a run using it "may ignore robots.txt" and
    "is not production-grade or certified", which is exactly why :func:`run_live`
    -- the only path the pipeline calls -- does not accept the parameter and
    cannot pass it. The capability stays available to an operator who invokes it
    deliberately; it is structurally unreachable from a betting-day run.
    """
    policy = SOURCES[source_id]

    def log(message: str) -> None:
        if verbose:
            print(f"[tipsters-live][{source_id}] {message}")

    risk_authorized = _operator_risk_authorizes(operator_risk_data, source_id)
    if operator_risk_data and not risk_authorized and source_id not in CERTIFIED_SHADOW_SOURCE_IDS:
        reason = f"operator_risk_not_authorized_in_json_for_source_{source_id}"
        log(f"SKIP {reason}")
        return [
            _empty_result(
                source_id,
                policy.entrypoints[0],
                reason,
                live_fetch_allowed=False,
                fallback="manual_review",
                skip_reason=reason,
            )
        ]

    gate = review_gate_details(review_data, source_id)
    if not gate["allowed"] and not risk_authorized:
        log(f"SKIP {gate['reason']}")
        return [
            _empty_result(
                source_id,
                policy.entrypoints[0],
                str(gate["reason"]),
                live_fetch_allowed=False,
                fallback="manual_review",
                skip_reason=str(gate["reason"]),
                required_flags_missing=list(gate["required_flags_missing"]),
                invalid_attestation=list(gate["invalid_attestation"]),
            )
        ]

    entrypoints, fallback_homepage = resolve_target_entrypoints(source_id, date_str)

    if source_id == "zawodtyper":
        page_url = entrypoints[0]
        transport_doc, transport_meta = fetch_zawodtyper_public_xhr_document(
            page_url,
            review_data=review_data,
            timeout_seconds=timeout,
            user_agent=FetchConfig().user_agent,
            max_pages_per_source=max(1, max_pages),
        )
        if transport_doc is None and fallback_homepage and page_url != fallback_homepage:
            # The daily URL is composed from Polish month/weekday names and
            # breaks whenever the site's slug convention shifts; the homepage
            # carries the same public bet list.
            log(f"XHR_FAIL {page_url} reason={transport_meta.get('reason')}; retrying homepage")
            page_url = fallback_homepage
            transport_doc, transport_meta = fetch_zawodtyper_public_xhr_document(
                page_url,
                review_data=review_data,
                timeout_seconds=timeout,
                user_agent=FetchConfig().user_agent,
                max_pages_per_source=max(1, max_pages),
            )
        if transport_doc is None:
            reason = str(transport_meta.get("reason", "public_xhr_failed_closed"))
            log(f"XHR_FAIL {page_url} reason={reason}")
            return [
                _empty_result(
                    source_id,
                    page_url,
                    f"public_xhr_failed:{reason}",
                    block_reason=f"FETCH_BLOCK:{reason}",
                    live_fetch_allowed=False,
                    fallback="public_xhr_failed_closed",
                    coverage_status="NEEDS_PUBLIC_XHR_REVIEW",
                )
            ]
        log(
            f"XHR_OK {page_url} cookie_policy={transport_meta.get('cookie_policy')} "
            f"items={transport_meta.get('item_count', 0)} xhr_calls={transport_meta.get('xhr_call_count', 0)}"
        )
        parsed = dispatch_extract(transport_doc, source_id, review_data=review_data)
        for warning in build_zawodtyper_transport_warnings(transport_meta):
            if warning not in parsed.warnings:
                parsed.warnings.append(warning)
        parsed.expected_visible_count = int(transport_meta.get("item_count") or 0) or None
        parsed.extracted_count = parsed.pick_count
        if parsed.expected_visible_count:
            parsed.coverage_ratio = round(parsed.pick_count / parsed.expected_visible_count, 3)
        log(f"PARSE verdict={parsed.verdict.value} picks={parsed.pick_count}")
        return [parsed]

    robots = RobotsCache(user_agent=FetchConfig().user_agent.split("/")[0])
    limiter = DomainRateLimiter(min_delay_seconds=max(policy.min_delay_seconds, 2.0))
    config = FetchConfig(timeout_seconds=timeout, max_bytes=max_bytes)
    results: list[ExtractionResult] = []
    urls_seen: list[str] = []

    for entrypoint in entrypoints:
        if len(urls_seen) >= max_pages:
            break
        outcome = fetch_public_html(
            policy, entrypoint, robots=robots, limiter=limiter, terms_reviewed=True, config=config,
            review_data=review_data, operator_risk_data=operator_risk_data,
        )
        if not outcome.allowed or outcome.document is None:
            log(f"FETCH_BLOCK {entrypoint} reason={outcome.reason}")
            block_reason = _blocked_reason(outcome.reason)
            results.append(
                _empty_result(
                    source_id,
                    entrypoint,
                    f"fetch_block:{outcome.reason}",
                    block_reason=block_reason,
                    robots_blocked_live="BLOCK_ROBOTS" in block_reason,
                    live_fetch_allowed=False,
                    fallback="fixture_snapshot_only",
                )
            )
            continue

        log(f"FETCH_OK {entrypoint} status={outcome.status_code} bytes={len(outcome.document.html)}")
        urls_seen.append(entrypoint)
        parsed = dispatch_extract(outcome.document, source_id, review_data=review_data)
        parsed.extracted_count = parsed.pick_count
        log(f"PARSE {entrypoint} verdict={parsed.verdict.value} picks={parsed.pick_count}")
        results.append(parsed)

        for detail_url in discover_public_detail_links(outcome.document, source_id):
            if len(urls_seen) >= max_pages:
                break
            if detail_url in urls_seen:
                continue
            detail = fetch_public_html(
                policy, detail_url, robots=robots, limiter=limiter, terms_reviewed=True, config=config,
                review_data=review_data, operator_risk_data=operator_risk_data,
            )
            if not detail.allowed or detail.document is None:
                log(f"DETAIL_BLOCK {detail_url} reason={detail.reason}")
                block_reason = _blocked_reason(detail.reason)
                results.append(
                    _empty_result(
                        source_id,
                        detail_url,
                        f"detail_block:{detail.reason}",
                        block_reason=block_reason,
                        robots_blocked_live="BLOCK_ROBOTS" in block_reason,
                        live_fetch_allowed=False,
                        fallback="fixture_snapshot_only",
                    )
                )
                continue
            urls_seen.append(detail_url)
            parsed_detail = dispatch_extract(detail.document, source_id, review_data=review_data)
            parsed_detail.extracted_count = parsed_detail.pick_count
            log(f"DETAIL_PARSE {detail_url} verdict={parsed_detail.verdict.value} picks={parsed_detail.pick_count}")
            results.append(parsed_detail)

    if not results:
        results.append(_empty_result(source_id, policy.entrypoints[0], "no_fetch_attempts_or_no_entrypoints"))
    return results


def run_live(
    betting_date: str,
    *,
    review_path: Path | str = DEFAULT_REVIEW_PATH,
    source_ids: tuple[str, ...] | list[str] = DEFAULT_LIVE_SOURCE_IDS,
    max_pages_per_source: int = 3,
    timeout: float = 12.0,
    max_bytes: int = 2_000_000,
    drop_undated: bool = False,
    verbose: bool = False,
) -> dict[str, Any]:
    """Run every requested source for one betting day.

    Returns the extraction results alongside the day-attribution counts, so a
    caller can report "42 picks kept, 9 from other days, 3 already settled"
    rather than one opaque total.
    """
    review_data = load_review_file(Path(review_path))
    started_at = datetime.now(timezone.utc).isoformat()

    results: list[ExtractionResult] = []
    for source_id in source_ids:
        if source_id not in SOURCES:
            raise ValueError(f"unknown source_id: {source_id}")
        results.extend(
            fetch_extract_source(
                source_id,
                review_data=review_data,
                max_pages=max(1, max_pages_per_source),
                timeout=timeout,
                max_bytes=max_bytes,
                date_str=betting_date,
                verbose=verbose,
            )
        )

    raw_total = sum(r.pick_count for r in results)
    date_counts: dict[str, int] = {
        "kept": 0, "exact_day": 0, "adjacent_day_kept": 0, "wrong_date": 0,
        "undated_kept": 0, "undated_dropped": 0, "settled": 0, "unparseable_date": 0,
    }
    for result in results:
        kept, counts = filter_picks_for_date(result.picks, betting_date, drop_undated=drop_undated)
        result.picks = kept
        result.extracted_count = len(kept)
        for key, value in counts.items():
            date_counts[key] += value
        # A source whose every pick belonged to another day is not a source with
        # no opinion today; it is a source we could not date. Recorded, not lost.
        dropped = (
            counts["wrong_date"] + counts["undated_dropped"] + counts["settled"] + counts["unparseable_date"]
        )
        if not kept and dropped:
            result.verdict = ExtractorVerdict.EMPTY
            note = (
                "all_picks_dropped_by_date_filter:"
                f"wrong_date={counts['wrong_date']},"
                f"undated={counts['undated_dropped']},"
                f"settled={counts['settled']}"
            )
            if note not in result.warnings:
                result.warnings.append(note)

    return {
        "betting_date": betting_date,
        "started_at_utc": started_at,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_ids": list(source_ids),
        "results": results,
        "raw_pick_count": raw_total,
        "date_filter": date_counts,
        "certified_shadow_sources": [s for s in source_ids if s in CERTIFIED_SHADOW_SOURCE_IDS],
    }
