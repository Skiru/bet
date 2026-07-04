"""HTML parsing helpers for tipster scraper v2.

The production repo may install selectolax/BeautifulSoup/lxml for speed and
selector ergonomics, but this module deliberately has a stdlib-only fallback so
CI fixtures never need network or optional binary packages.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin

from .normalization import collapse_ws, strip_tags

_SCRIPT_STYLE_RE = re.compile(r"<\s*(script|style|noscript)[^>]*>.*?<\s*/\s*\1\s*>", re.I | re.S)
_BLOCK_RE = re.compile(
    r"<\s*(h1|h2|h3|h4|p|li|tr|td|article|section|div)[^>]*>(.*?)<\s*/\s*\1\s*>",
    re.I | re.S,
)
_LINK_RE = re.compile(r"<a\b[^>]*?href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>", re.I | re.S)


@dataclass(frozen=True)
class LinkCandidate:
    url: str
    label: str
    rel: str = ""


def remove_noise_markup(html_text: str) -> str:
    return _SCRIPT_STYLE_RE.sub(" ", html_text or "")


def html_to_text(html_text: str) -> str:
    return collapse_ws(strip_tags(remove_noise_markup(html_text)))


def text_blocks(html_text: str, min_chars: int = 3) -> list[str]:
    """Return readable text blocks in document order.

    Prefer semantic block tags and fall back to whole-page text. Nested tags are
    acceptable; duplicates are removed to keep extraction deterministic.
    """
    cleaned = remove_noise_markup(html_text)
    blocks: list[str] = []
    for match in _BLOCK_RE.finditer(cleaned):
        block = collapse_ws(strip_tags(match.group(2)))
        if len(block) >= min_chars and block not in blocks:
            blocks.append(block)
    if not blocks:
        whole = html_to_text(cleaned)
        if whole:
            blocks.append(whole)
    return blocks


def joined_context(blocks: Iterable[str], window: int = 6) -> str:
    chosen: list[str] = []
    for block in blocks:
        if block not in chosen:
            chosen.append(block)
        if len(chosen) >= window:
            break
    return collapse_ws(" ".join(chosen))


def link_candidates(html_text: str, base_url: str) -> list[LinkCandidate]:
    out: list[LinkCandidate] = []
    for match in _LINK_RE.finditer(remove_noise_markup(html_text)):
        href = html.unescape(match.group("href")).strip()
        label = collapse_ws(strip_tags(match.group("label")))
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        out.append(LinkCandidate(url=urljoin(base_url, href), label=label))
    return out


def extract_json_ld_event_names(html_text: str) -> list[tuple[str, str]]:
    """Lightweight JSON-LD fallback without depending on extruct.

    This is intentionally conservative: it only returns pairs when both home and
    away team-like names appear close to schema.org SportsEvent keys.
    """
    cleaned = remove_noise_markup(html_text)
    out: list[tuple[str, str]] = []
    script_pat = re.compile(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.I | re.S)
    for script in script_pat.finditer(cleaned):
        payload = html.unescape(script.group(1))
        if "SportsEvent" not in payload and "homeTeam" not in payload:
            continue
        home = re.search(r'"homeTeam"\s*:\s*(?:\{[^{}]*?"name"\s*:\s*)?"([^"]{2,80})"', payload, re.I | re.S)
        away = re.search(r'"awayTeam"\s*:\s*(?:\{[^{}]*?"name"\s*:\s*)?"([^"]{2,80})"', payload, re.I | re.S)
        if home and away:
            out.append((collapse_ws(home.group(1)), collapse_ws(away.group(1))))
    return out
