"""Compliance and crawl-safety gates for tipster sources."""
from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic, sleep
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from .contracts import ComplianceCheck, ComplianceVerdict, SourcePolicy


@dataclass
class DomainRateLimiter:
    min_delay_seconds: float = 2.0
    _last_by_domain: dict[str, float] = field(default_factory=dict)

    def wait(self, url: str) -> None:
        domain = urlparse(url).netloc.lower()
        now = monotonic()
        last = self._last_by_domain.get(domain)
        if last is not None:
            delay = self.min_delay_seconds - (now - last)
            if delay > 0:
                sleep(delay)
        self._last_by_domain[domain] = monotonic()


class RobotsCache:
    def __init__(self, user_agent: str = "skiru-bet-research-bot") -> None:
        self.user_agent = user_agent
        self._cache: dict[str, RobotFileParser] = {}

    def allowed(self, url: str) -> bool | None:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return None
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = self._cache.get(robots_url)
        if parser is None:
            parser = RobotFileParser(robots_url)
            try:
                parser.read()
            except Exception:
                return None
            self._cache[robots_url] = parser
        try:
            return parser.can_fetch(self.user_agent, url)
        except Exception:
            return None


def compliance_check(policy: SourcePolicy, url: str, robots: RobotsCache | None = None, terms_reviewed: bool = False) -> ComplianceCheck:
    if not policy.allow_authenticated and any(token in url.lower() for token in ("login", "account", "member", "premium")):
        return ComplianceCheck(policy.source_id, url, ComplianceVerdict.BLOCK_AUTH_REQUIRED, reason="auth/premium path detected")
    robots_allowed: bool | None = None
    if policy.robots_required:
        robots_allowed = robots.allowed(url) if robots else None
        if robots_allowed is False:
            return ComplianceCheck(policy.source_id, url, ComplianceVerdict.BLOCK_ROBOTS, robots_allowed=False, terms_reviewed=terms_reviewed, reason="robots.txt disallows target")
    if policy.terms_review_required and not terms_reviewed:
        return ComplianceCheck(policy.source_id, url, ComplianceVerdict.UNKNOWN_REVIEW_REQUIRED, robots_allowed=robots_allowed, terms_reviewed=False, reason="terms review not recorded")
    return ComplianceCheck(policy.source_id, url, ComplianceVerdict.ALLOW, robots_allowed=robots_allowed, terms_reviewed=terms_reviewed)
