"""Market parsing for tipster recommendations."""
from __future__ import annotations

import re
from .contracts import Direction, MarketFamily
from .normalization import collapse_ws

_STAT_PATTERNS: list[tuple[MarketFamily, re.Pattern[str]]] = [
    ("corners", re.compile(r"\b(corners?|rzut(?:y|ow|ów)?\s*ro[żz]n|ck)\b", re.I)),
    ("cards", re.compile(r"\b(cards?|yellow|kart(?:ki|ek|ka)|żółt)\b", re.I)),
    ("shots", re.compile(r"\b(shots?|strza(?:ly|ły|l|ł))\b", re.I)),
    ("fouls", re.compile(r"\b(fouls?|faul(?:e|i)?)\b", re.I)),
    ("tennis_games", re.compile(r"\b(games?|gemy?|sets?|sety?|aces?|break points?)\b", re.I)),
    ("basketball_points", re.compile(r"\b(points?|punkty|rebounds?|assists?|steals?)\b", re.I)),
    ("hockey_total", re.compile(r"\b(puck line|power play|shots on goal|penalty minutes|goals?)\b", re.I)),
    ("goals", re.compile(r"\b(goals?|bram(?:ki|ek|ka)|gole?)\b", re.I)),
]


def parse_line(text: str) -> float | None:
    """Extract a betting/stat line, not arbitrary dates, scores or odds.

    Prefer explicit over/under/handicap markers. This intentionally returns
    None for weak contexts instead of hallucinating a line from years/scores.
    """
    explicit = re.search(
        r"\b(?:over|under|powyzej|powyżej|ponizej|poniżej|o/u|total|handicap|asian handicap)\s*([+-]?[0-9]+(?:[.,][0-9]+)?)\b",
        text,
        re.I,
    )
    if explicit:
        val = float(explicit.group(1).replace(",", "."))
        return val if -50.0 <= val <= 250.0 else None
    reverse = re.search(
        r"\b([0-9]+(?:[.,][0-9]+)?)\s*(?:goals?|corners?|cards?|shots?|fouls?|games?|sets?|points?|bramki|kartki|rożne|rozne)\b",
        text,
        re.I,
    )
    if reverse:
        val = float(reverse.group(1).replace(",", "."))
        return val if 0.5 <= val <= 250.0 else None
    return None


def extract_odds(text: str) -> float | None:
    for pat in [
        r"@\s*([1-9]\d?(?:\.\d{1,2})?)",
        r"\b(?:odds|kurs)\s*[:=]?\s*([1-9]\d?(?:\.\d{1,2})?)",
        r"\b([1-9]\d?\.\d{2})\b",
    ]:
        m = re.search(pat, text, re.I)
        if m:
            val = float(m.group(1))
            if 1.01 <= val <= 100.0:
                return val
    m = re.search(r"\(([+-]\d{3,4})\)", text)
    if m:
        american = int(m.group(1))
        return round(1 + american / 100, 2) if american > 0 else round(1 + 100 / abs(american), 2)
    return None


def market_family(text: str) -> MarketFamily:
    low = text.lower()
    if re.search(r"\b(btts|both teams to score|obie strzel)", low):
        return "btts"
    if re.search(r"\b(correct score|dokladny wynik|dokładny wynik)\b", low):
        return "correct_score"
    if re.search(r"\b(handicap|spread|asian handicap|hc)\b", low):
        return "handicap"
    if re.search(r"\b(winner|moneyline|to win|1x2|home win|away win|draw|zwyci|wygra|remis)\b", low):
        return "winner"
    for family, pat in _STAT_PATTERNS:
        if pat.search(text):
            return family
    if re.search(r"\b(over|under|powyzej|powyżej|ponizej|poniżej)\b", low):
        return "goals"
    return "unknown"


def direction(text: str) -> Direction:
    low = text.lower()
    if re.search(r"\b(over|powyzej|powyżej|więcej|wiecej)\b", low):
        return "OVER"
    if re.search(r"\b(under|ponizej|poniżej|mniej)\b", low):
        return "UNDER"
    if re.search(r"\b(btts no|both teams not|obie nie)\b", low):
        return "BTTS_NO"
    if re.search(r"\b(btts|both teams to score|obie strzel)\b", low):
        return "BTTS_YES"
    if re.search(r"\b(draw no bet|dnb)\b", low):
        return "DNB"
    if re.search(r"\b(double chance|1x|x2|12)\b", low):
        return "DC"
    if re.search(r"\b(draw|remis)\b", low):
        return "DRAW"
    if re.search(r"\b(away win|2\s*$)\b", low):
        return "AWAY"
    if re.search(r"\b(home win|1\s*$)\b", low):
        return "HOME"
    if re.search(r"\b(win|winner|moneyline|wygra|zwyci)\b", low):
        return "WIN"
    return "OTHER"


def extract_market_text(context: str) -> str:
    context = collapse_ws(context)
    # Prefer explicit statistical lines.
    patterns = [
        r"(?:over|under|powyżej|poniżej|powyzej|ponizej)\s*\d+(?:[.,]\d+)?\s*(?:goals?|corners?|cards?|shots?|fouls?|games?|sets?|points?|bramki|kartki|rożne)",
        r"(?:corners?|cards?|shots?|fouls?|games?|sets?|points?|bramki|kartki|rożne)\s*(?:over|under|powyżej|poniżej|powyzej|ponizej)\s*\d+(?:[.,]\d+)?",
        r"(?:btts|both teams to score|obie strzelą|obie strzela)",
        r"(?:draw no bet|dnb|double chance|1x|x2|asian handicap|handicap)\s*[+-]?\d*(?:[.,]\d+)?",
        r"(?:home win|away win|draw|moneyline|to win|winner)",
    ]
    for pat in patterns:
        m = re.search(pat, context, re.I)
        if m:
            return collapse_ws(m.group(0))[:120]
    return "N/A"


def stats_cited(text: str) -> list[str]:
    out: list[str] = []
    for pat in [
        r"\d+(?:[.,]\d+)?\s*(?:corners?|cards?|shots?|fouls?|goals?|games?|sets?|points?)",
        r"(?:average|avg|średnio|srednio)\s*[:=]?\s*\d+(?:[.,]\d+)?",
        r"(?:last|ostatnie)\s*\d+\s*(?:matches|games|mecz)",
        r"\d+\s*/\s*\d+",
    ]:
        out.extend(m.group(0) for m in re.finditer(pat, text, re.I))
    seen: list[str] = []
    for item in out:
        c = collapse_ws(item)
        if c not in seen:
            seen.append(c)
    return seen[:12]
