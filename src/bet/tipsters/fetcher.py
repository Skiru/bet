"""Compliance-first HTTP fetcher for tipster scraper v2.

This is intentionally minimal and conservative. The production repo may replace
it with Scrapy/httpx, but it must preserve the same gates: robots, ToS review,
rate limit, max bytes, content type, no auth/premium/anti-bot bypass.
"""
from __future__ import annotations

from dataclasses import dataclass
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
) -> FetchOutcome:
    parsed = urlparse(url)
    if not parsed.scheme.startswith("http") or not parsed.netloc:
        return FetchOutcome(False, reason="invalid_url")
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
