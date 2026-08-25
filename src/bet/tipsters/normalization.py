"""Normalization utilities for tipster extraction.

The goal is to normalize enough for matching while preserving source text in the
pick object. Never use normalized text as user-visible evidence.
"""
from __future__ import annotations

import html
import re
import unicodedata
from difflib import SequenceMatcher

TEAM_NOISE = {
    "prediction", "predictions", "tips", "tip", "best", "best bet", "pick", "odds", "bet", "bets",
    "free", "today", "tomorrow", "yesterday", "view", "read more",
    "results", "fixtures", "statistics", "stats", "preview", "previews",
    "login", "vip", "loading", "home", "bookmakers", "responsible gambling",
    "all tips", "top online bookmakers", "select your language", "casino",
    "predictions football", "football predictions", "follow", "advertise",
}
LEAGUE_WORDS = {
    "premier league", "championship", "la liga", "serie a", "bundesliga",
    "ligue 1", "eredivisie", "mls", "nba", "nhl", "world cup", "euroleague",
}


def strip_tags(text: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<(?:br|/p|/div|/li|/tr|/h[1-6])\b[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def ascii_fold(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text or "")
        if not unicodedata.combining(ch)
    )


def normalize_key(text: str) -> str:
    text = ascii_fold(text).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return collapse_ws(text)


def clean_team_name(raw: str) -> str:
    text = collapse_ws(strip_tags(raw))
    text = re.sub(r"\b(?:vs?\.?|@)\b.*$", "", text, flags=re.I).strip() if len(text) > 80 else text
    # Remove trailing market and UI artifacts without deleting real club names like Real Betis.
    changed = True
    while changed:
        changed = False
        low = normalize_key(text)
        for token in sorted(TEAM_NOISE, key=len, reverse=True):
            if low == token:
                text = ""
                changed = False
                break
            if low.endswith(" " + token):
                next_text = re.sub(r"\s+" + re.escape(token) + r"\s*$", "", text, flags=re.I).strip()
                if next_text == text:
                    changed = False
                    break
                text = next_text
                changed = True
                break
    text = re.sub(r"(?:\s+\(?[12xX]{1,2}\)?|\s+[OU]\d+(?:\.\d+)?\)?)$", "", text).strip()
    return collapse_ws(text[:80])


# Fixture-list scaffolding that the "A vs B" patterns happily swallow when a
# listing page is flattened to text. Live run 2026-08-25 produced Sportsgambler
# "teams" such as "00 Mon 24/08 vs Premier League Fulham Chelsea Expired
# Fulham": a clock time, a weekday, a date, a league name, a status badge and
# two real clubs, all matched as one side. Names carrying any of these markers
# are structurally not club names, whatever else is in them.
_SCAFFOLDING_MARKERS = (
    re.compile(r"\b\d{1,2}[:.]\d{2}\b"),                                        # 19:00
    re.compile(r"\b\d{1,2}\s*/\s*\d{1,2}\b"),                                   # 24/08
    re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b"),                               # 24.08.2026
    re.compile(r"\b(?:mon|tue|wed|thu|fri|sat|sun)\b", re.I),
    re.compile(r"\b(?:expired|postponed|cancelled|canceled|finished|live now|ft|ended)\b", re.I),
)


def is_garbage_team(name: str) -> bool:
    key = normalize_key(name)
    if len(key) < 2 or key in TEAM_NOISE or key in LEAGUE_WORDS:
        return True
    if re.fullmatch(r"\d+", key):
        return True
    # Checked against the raw text, not the normalized key: normalize_key strips
    # the punctuation ("19:00" -> "19 00") that identifies a timestamp.
    if any(pattern.search(name) for pattern in _SCAFFOLDING_MARKERS):
        return True
    if any(league in key for league in LEAGUE_WORDS):
        return True
    words = key.split()
    if len(words) > 7:
        return True
    spam = {"bookmaker", "bookmakers", "bonus", "telegram", "privacy", "cookie", "casino", "signup", "login", "vip", "loading", "zawod", "typer", "spolecznosc", "najwieksza", "bukmacherska"}
    return any(w in spam for w in words)


def names_score(a: str, b: str) -> int:
    ak = normalize_key(a)
    bk = normalize_key(b)
    if not ak or not bk:
        return 0
    if ak == bk:
        return 100
    return round(SequenceMatcher(None, ak, bk).ratio() * 100)
