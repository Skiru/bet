#!/usr/bin/env python3
"""Deep-link discovery module — extracts tournament/league sub-links from landing pages.

Given an HTML page and its URL, discovers sub-pages (tournament detail pages,
league match listings) that should be scanned for additional events.

Usage:
    from deep_link_discovery import discover_deep_links
    links = discover_deep_links(html, "https://www.flashscore.com/football/", "flashscore.com")
"""

import re
from urllib.parse import urljoin, urlparse

# Domain-specific link patterns
DOMAIN_PATTERNS = {
    "flashscore.com": {
        "include": [
            # Football country/league pages
            re.compile(r"/football/[a-z-]+/[a-z0-9-]+/?$"),
            # Other sport tournament pages
            re.compile(r"/tennis/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/basketball/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/volleyball/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/hockey/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/handball/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/baseball/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/esports/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/snooker/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/darts/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/table-tennis/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/mma/[a-z-]+/[a-z0-9-]+/?$"),
            # Football country landing pages (list all leagues)
            re.compile(r"/football/[a-z-]+/?$"),
        ],
        "exclude": [
            re.compile(r"/results/"),
            re.compile(r"/standings/"),
            re.compile(r"/news/"),
            re.compile(r"/archive/"),
            re.compile(r"/draw/"),
            re.compile(r"/fixtures/"),
            re.compile(r"/#"),
            re.compile(r"/player/"),
            re.compile(r"/team/"),
        ],
    },
    "betexplorer.com": {
        "include": [
            re.compile(r"/soccer/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/tennis/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/basketball/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/volleyball/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/hockey/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/handball/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/snooker/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/esports/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/darts/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/table-tennis/[a-z-]+/[a-z0-9-]+/?$"),
        ],
        "exclude": [
            re.compile(r"/results/"),
            re.compile(r"/statistics/"),
            re.compile(r"/news/"),
        ],
    },
    "sofascore.com": {
        "include": [
            re.compile(r"/tournament/[a-z-]+/\d+"),
            re.compile(r"/football/[a-z-]+/"),
            re.compile(r"/tennis/[a-z-]+/"),
            re.compile(r"/basketball/[a-z-]+/"),
            re.compile(r"/volleyball/[a-z-]+/"),
        ],
        "exclude": [
            re.compile(r"/player/"),
            re.compile(r"/team/"),
            re.compile(r"/news/"),
        ],
    },
    "oddsportal.com": {
        "include": [
            re.compile(r"/football/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/tennis/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/basketball/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/volleyball/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/hockey/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/handball/[a-z-]+/[a-z0-9-]+/?$"),
            re.compile(r"/baseball/[a-z-]+/[a-z0-9-]+/?$"),
        ],
        "exclude": [
            re.compile(r"/results/"),
            re.compile(r"/news/"),
            re.compile(r"/history/"),
        ],
    },
    "soccerway.com": {
        "include": [
            re.compile(r"/national/[a-z-]+/[a-z0-9-]+/"),
            re.compile(r"/matches/"),
            re.compile(r"/international/[a-z-]+/"),
        ],
        "exclude": [
            re.compile(r"/news/"),
            re.compile(r"/player/"),
            re.compile(r"/coach/"),
            re.compile(r"/venue/"),
        ],
    },
    "scores24.live": {
        "include": [
            # Match detail pages: /en/{sport}/m-{DD-MM-YYYY}-{slug}
            re.compile(r"/en/[a-z-]+/m-\d{2}-\d{2}-\d{4}-[a-z0-9-]+$"),
        ],
        "exclude": [
            # Prediction pages (community votes, not data)
            re.compile(r"-prediction$"),
            # Hash fragments (trends/odds tabs — same page, no need to re-fetch)
            re.compile(r"#"),
            # Static/non-match pages
            re.compile(r"/privacy"),
            re.compile(r"/terms"),
            re.compile(r"/about"),
        ],
    },
}

# Non-event page indicators
NON_EVENT_KEYWORDS = [
    "login", "register", "signup", "contact", "about", "privacy",
    "terms", "cookie", "legal", "help", "faq", "sitemap",
    "twitter.com", "facebook.com", "instagram.com", "youtube.com",
]


def _extract_links_from_html(html: str, base_url: str) -> list[str]:
    """Extract all href links from HTML using regex (no lxml dependency)."""
    links = set()
    for match in re.finditer(r'href=["\']([^"\']+)["\']', html, re.IGNORECASE):
        href = match.group(1)
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        # Resolve relative URLs
        full_url = urljoin(base_url, href)
        # Only keep same-domain links
        base_domain = urlparse(base_url).netloc.replace("www.", "")
        link_domain = urlparse(full_url).netloc.replace("www.", "")
        if base_domain == link_domain:
            # Clean URL — remove query string and fragment
            parsed = urlparse(full_url)
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            links.add(clean_url)
    return sorted(links)


def _is_non_event_url(url: str) -> bool:
    """Check if URL is clearly a non-event page."""
    url_lower = url.lower()
    return any(kw in url_lower for kw in NON_EVENT_KEYWORDS)


def _matches_patterns(path: str, patterns: list) -> bool:
    """Check if URL path matches any of the patterns."""
    return any(p.search(path) for p in patterns)


def discover_deep_links(
    html: str,
    base_url: str,
    domain: str,
    max_links: int = 50,
) -> list[str]:
    """Discover tournament/league sub-links from a landing page.

    Args:
        html: Raw HTML content of the landing page
        base_url: URL that was fetched
        domain: Domain name (e.g., "flashscore.com")
        max_links: Maximum number of links to return

    Returns:
        List of URLs to scan for additional events
    """
    all_links = _extract_links_from_html(html, base_url)

    # Get domain-specific patterns
    domain_clean = domain.replace("www.", "")
    patterns = DOMAIN_PATTERNS.get(domain_clean)

    if not patterns:
        # Generic fallback — look for sport-related paths
        results = []
        for link in all_links:
            if _is_non_event_url(link):
                continue
            path = urlparse(link).path.lower()
            # Generic sports patterns
            if any(sport in path for sport in [
                "/football/", "/tennis/", "/basketball/", "/volleyball/",
                "/hockey/", "/handball/", "/baseball/", "/esports/",
                "/snooker/", "/darts/", "/table-tennis/", "/mma/",
                "/soccer/", "/padel/", "/speedway/",
            ]):
                # Must have at least 2 path segments (not just landing)
                segments = [s for s in path.split("/") if s]
                if len(segments) >= 2:
                    results.append(link)
        return sorted(set(results))[:max_links]

    include_patterns = patterns.get("include", [])
    exclude_patterns = patterns.get("exclude", [])

    results = []
    for link in all_links:
        if _is_non_event_url(link):
            continue
        path = urlparse(link).path
        # Skip if it's the same as the base URL
        if path == urlparse(base_url).path:
            continue
        # Check exclude patterns first
        if exclude_patterns and _matches_patterns(path, exclude_patterns):
            continue
        # Check include patterns
        if include_patterns and _matches_patterns(path, include_patterns):
            results.append(link)

    return sorted(set(results))[:max_links]


def discover_flashscore_tournament_links(html: str, base_url: str) -> list[str]:
    """Flashscore-specific: extract tournament/league links from a sport landing page.

    Flashscore landing pages (e.g., /football/) have league links in sidebar
    and in the main content area. This function specifically targets those.
    """
    links = _extract_links_from_html(html, base_url)
    results = []

    for link in links:
        path = urlparse(link).path.lower()
        # Match country/league patterns across all sports
        if re.match(r"^/(football|tennis|basketball|volleyball|hockey|handball|baseball|esports|snooker|darts|table-tennis|mma)/[a-z-]+/[a-z0-9-]+/?$", path):
            results.append(link)
        # Also match country-level pages (lists all leagues in that country)
        elif re.match(r"^/(football|tennis|basketball|volleyball|hockey|handball|baseball)/[a-z-]+/?$", path):
            results.append(link)

    return sorted(set(results))


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 deep_link_discovery.py <html_file> [base_url]")
        sys.exit(1)

    html_file = sys.argv[1]
    base_url = sys.argv[2] if len(sys.argv) > 2 else "https://www.flashscore.com/"
    domain = urlparse(base_url).netloc.replace("www.", "")

    from pathlib import Path
    html = Path(html_file).read_text(encoding="utf-8", errors="ignore")
    links = discover_deep_links(html, base_url, domain)
    print(f"Discovered {len(links)} deep links from {domain}:")
    for link in links:
        print(f"  {link}")
