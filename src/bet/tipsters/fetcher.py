"""Compliance-first HTTP fetcher for tipster scraper v2.

This is intentionally minimal and conservative. The production repo may replace
it with Scrapy/httpx, but it must preserve the same gates: robots, ToS review,
rate limit, max bytes, content type, no auth/premium/anti-bot bypass.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .compliance import DomainRateLimiter, RobotsCache, compliance_check
from .contracts import ComplianceVerdict, RawDocument, SourcePolicy


@dataclass(frozen=True)
class FetchConfig:
    user_agent: str = "skiru-bet-research-bot/2.3 (+contact: repo-maintainer)"
    timeout_seconds: float = 12.0
    max_bytes: int = 2_000_000
    accepted_content_types: tuple[str, ...] = ("text/html", "application/xhtml+xml")


@dataclass(frozen=True)
class FetchOutcome:
    allowed: bool
    document: RawDocument | None = None
    reason: str = ""
    status_code: int | None = None


def fetch_public_html(
    policy: SourcePolicy,
    url: str,
    *,
    robots: RobotsCache,
    limiter: DomainRateLimiter,
    terms_reviewed: bool,
    config: FetchConfig = FetchConfig(),
    review_data: dict[str, Any] | None = None,
) -> FetchOutcome:
    parsed = urlparse(url)
    if not parsed.scheme.startswith("http") or not parsed.netloc:
        return FetchOutcome(False, reason="invalid_url")

    # Check XHR gate if this is an NP_ajax.php / live XHR request
    if "NP_ajax.php" in url:
        is_allowed = False
        reason = "allow_public_xhr_capture_required"
        if review_data:
            review = review_data.get("source_reviews", {}).get("zawodtyper", {})
            if isinstance(review, dict):
                allow_public_xhr_capture = review.get("allow_public_xhr_capture", False) is True
                reviewed_by = str(review.get("reviewed_by", "")).strip()
                reviewed_at_utc = str(review.get("reviewed_at_utc", "")).strip()
                notes = str(review.get("notes", "")).lower()
                status = str(review.get("status", "")).lower()
                
                # Check all compliance requirements
                has_flags = (
                    review.get("terms_reviewed") is True and
                    review.get("robots_reviewed") is True and
                    review.get("public_html_only") is True and
                    review.get("no_auth_no_premium_no_bypass") is True
                )
                
                import re
                valid_ts = bool(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", reviewed_at_utc))
                placeholders = {"", "REPLACE_WITH_OPERATOR", "REPLACE_WITH_UTC_TIMESTAMP"}
                valid_attestation = (
                    reviewed_by not in placeholders and
                    reviewed_at_utc not in placeholders and
                    valid_ts
                )
                
                valid_notes = "np_ajax.php" in notes or "public xhr review" in notes
                valid_status = status in ("allow_live_dry_run", "allow_shadow_dry_run")
                
                if allow_public_xhr_capture and has_flags and valid_attestation and valid_notes and valid_status:
                    is_allowed = True
                else:
                    if not allow_public_xhr_capture:
                        reason = "allow_public_xhr_capture_required"
                    elif not has_flags:
                        reason = "missing_required_review_flags"
                    elif not valid_attestation:
                        reason = "INVALID_REVIEW_ATTESTATION"
                    elif not valid_notes:
                        reason = "zawodtyper_xhr_review_notes_must_mention_np_ajax_or_public_xhr_review"
                    elif not valid_status:
                        reason = f"invalid_review_status:{status}"
        
        if not is_allowed:
            return FetchOutcome(False, reason=f"compliance_block:BLOCK_XHR:{reason}")
    check = compliance_check(policy, url, robots=robots, terms_reviewed=terms_reviewed)
    if check.verdict != ComplianceVerdict.ALLOW:
        return FetchOutcome(False, reason=f"compliance_block:{check.verdict}:{check.reason}")
    limiter.wait(url)
    request = Request(url, headers={"User-Agent": config.user_agent, "Accept": "text/html,application/xhtml+xml"})
    try:
        with urlopen(request, timeout=config.timeout_seconds) as response:  # nosec B310: gated public fetcher
            status = getattr(response, "status", None)
            ctype = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if ctype and ctype not in config.accepted_content_types:
                return FetchOutcome(False, reason=f"unsupported_content_type:{ctype}", status_code=status)
            body = response.read(config.max_bytes + 1)
            if len(body) > config.max_bytes:
                return FetchOutcome(False, reason="response_too_large", status_code=status)
            html = body.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
            return FetchOutcome(
                True,
                document=RawDocument(
                    source_id=policy.source_id,
                    url=url,
                    final_url=response.geturl(),
                    fetched_at_utc=datetime.now(timezone.utc).isoformat(),
                    html=html,
                    status_code=status,
                    content_type=ctype,
                ),
                status_code=status,
            )
    except HTTPError as exc:
        return FetchOutcome(False, reason=f"http_error:{exc.code}", status_code=exc.code)
    except URLError as exc:
        return FetchOutcome(False, reason=f"url_error:{exc.reason}")
    except TimeoutError:
        return FetchOutcome(False, reason="timeout")
