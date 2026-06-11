"""Shared utilities for the bet package.

Functions relocated from scripts/utils.py for proper import from src/bet/.
"""

import re
import unicodedata
from typing import Sequence


# Regex to strip emoji (Unicode emoji ranges)
_EMOJI_RE = re.compile(
    "["
    "\U0001F1E0-\U0001F1FF"  # flags (iOS)
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F700-\U0001F77F"  # alchemical
    "\U0001F780-\U0001F7FF"  # geometric shapes ext
    "\U0001F800-\U0001F8FF"  # supplemental arrows C
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U0001FA70-\U0001FAFF"  # symbols & pictographs ext-A
    "\U00002702-\U000027B0"  # dingbats
    "\U000024C2-\U0000257F"  # enclosed chars
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0000200D"             # zero width joiner
    "]+",
    flags=re.UNICODE,
)

# Characters that NFKD doesn't decompose but have obvious ASCII equivalents
_SPECIAL_CHAR_MAP = str.maketrans({
    "Ł": "L", "ł": "l",
    "Ø": "O", "ø": "o",
    "Đ": "D", "đ": "d",
    "ß": "ss",
    "Ħ": "H", "ħ": "h",
    "Ŧ": "T", "ŧ": "t",
})


def strip_emoji(text: str) -> str:
    """Remove all emoji characters from text."""
    return _EMOJI_RE.sub("", text)


def normalize_team_name(name: str) -> str:
    """Normalize team/player name for fuzzy matching across sources.

    Strips emoji, diacritics, removes common club suffixes (FC, SC, United, etc.),
    parenthetical qualifiers, age/gender/reserve suffixes, and extra whitespace.
    Returns lowercase.
    """
    if not name:
        return ""
    # Strip emoji first
    s = strip_emoji(name)
    # Handle characters NFKD doesn't decompose (Ł, Ø, Đ, ß)
    s = s.translate(_SPECIAL_CHAR_MAP)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\s*\([^)]*\)\s*", " ", s)
    # Remove age/gender/reserve suffixes
    s = re.sub(r"\b(U21|U19|U20|U23|U18|U17|W|II|III|B|Reserves?|Youth|Women|Juniors?)\b", "", s, flags=re.IGNORECASE)
    s = re.sub(
        r"\b(FC|SC|CF|CD|SK|FK|AS|AC|US|SS|SV|TSV|VfB|VfL|BSC|"
        r"IF|BK|IFK|AIK|FF|GIF|AFC|RFC|SFC|CFC|United|Utd|City|"
        r"Town|Rovers|Wanderers|Athletic|Athletico|Sporting|"
        r"SP|SE|CE|EC|AA|CR|CA|AP|RB)\b",
        "",
        s,
        flags=re.IGNORECASE,
    )
    # Remove esports org suffixes
    s = re.sub(r"\b(Gaming|Esports|eSports|e-Sports|Clan|Organization)\b", "", s, flags=re.IGNORECASE)
    s = s.replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s.lower()


def normalize_for_matching(name: str) -> str:
    """Aggressive normalization for cross-source name matching.

    Like normalize_team_name but also:
    - Strips commas and reorders "Last, First" → "first last"
    - Handles tennis-style "Surname, First" formats
    - Strips all punctuation except spaces
    """
    if not name:
        return ""
    s = strip_emoji(name)
    # Handle characters NFKD doesn't decompose (Ł, Ø, Đ, ß)
    s = s.translate(_SPECIAL_CHAR_MAP)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    # Handle "Last, First" format → "first last"
    if "," in s:
        parts = [p.strip() for p in s.split(",", 1)]
        if len(parts) == 2 and parts[1]:
            s = f"{parts[1]} {parts[0]}"
    # Remove parenthetical qualifiers
    s = re.sub(r"\s*\([^)]*\)\s*", " ", s)
    # Remove all punctuation except spaces
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.lower()


def _surname_tokens(normalized_name: str) -> set[str]:
    """Extract likely surname tokens from a normalized name (last token, or all if single)."""
    tokens = normalized_name.split()
    if not tokens:
        return set()
    if len(tokens) == 1:
        return {tokens[0]}
    # For "first last" → surname is last; for "first middle last" → last
    return {tokens[-1]}


# Common abbreviation/nickname aliases across sports and esports.
# Maps lowercase alias → lowercase canonical form.
_COMMON_ALIASES: dict[str, str] = {
    # Football abbreviations
    "man utd": "manchester united", "man united": "manchester united",
    "man city": "manchester city",
    "spurs": "tottenham hotspur", "tottenham": "tottenham hotspur",
    "wolves": "wolverhampton wanderers", "wolverhampton": "wolverhampton wanderers",
    "villa": "aston villa",
    "newcastle": "newcastle united",
    "west ham": "west ham united",
    "forest": "nottingham forest", "nott forest": "nottingham forest",
    "brighton": "brighton hove albion",
    "palace": "crystal palace",
    "atletico": "atletico madrid", "atleti": "atletico madrid",
    "barca": "barcelona", "fcb": "barcelona",
    "psg": "paris saint germain", "paris sg": "paris saint germain",
    "bayern": "bayern munich", "bayern munchen": "bayern munich",
    "dortmund": "borussia dortmund", "bvb": "borussia dortmund",
    "inter milano": "inter milan",
    "juve": "juventus",
    "napoli": "ssc napoli",
    "benfica": "sl benfica",
    "sporting lisbon": "sporting cp",
    "porto": "fc porto",
    "ajax": "ajax amsterdam",
    "psv": "psv eindhoven",
    "feyenoord": "feyenoord rotterdam",
    "legia": "legia warsaw", "legia warszawa": "legia warsaw",
    "lech": "lech poznan",
    # Esports abbreviations
    "navi": "natus vincere", "na'vi": "natus vincere",
    "g2": "g2 esports",

    "faze": "faze clan",
    "c9": "cloud9", "cloud 9": "cloud9",
    "og": "og esports",
    "t1": "t1 esports",
    "vitality": "team vitality",
    "liquid": "team liquid",
    "spirit": "team spirit",
    "vp": "virtus pro", "virtus.pro": "virtus pro",
    "mouz": "mousesports",
    "col": "complexity", "complexity gaming": "complexity",
    "eg": "evil geniuses",
    "sen": "sentinels",
    "100t": "100 thieves",
    "nrg": "nrg esports",
    "loud": "loud esports",
    # Tennis nicknames (rare but useful)
    "djoko": "novak djokovic", "nole": "novak djokovic",
    "rafa": "rafael nadal",
    "federer": "roger federer",
}


def _resolve_alias(normalized_name: str) -> str:
    """Check if a normalized name is a known alias and return canonical form."""
    return _COMMON_ALIASES.get(normalized_name, normalized_name)


def names_match(name_a: str, name_b: str, threshold: int = 70) -> float:
    """Smart name matching that handles partial names, diacritics, emoji.

    Returns match score (0-100). Handles:
    - Full name vs surname-only (tennis tipsters: "Świątek" vs "Swiatek, Iga")
    - Emoji flags in names ("🇦🇺 Jones" vs "Jones, Emerson")
    - Diacritics (ą→a, ś→s, etc.)
    - Name format differences ("Last, First" vs "First Last")

    Uses multi-strategy matching:
    1. Exact normalized match → 100
    2. token_sort_ratio on full normalized names → score
    3. token_set_ratio (ignores extra tokens) → score
    4. Containment check (surname in full name) → 85
    """
    try:
        from rapidfuzz import fuzz
    except ImportError:
        na = normalize_for_matching(name_a)
        nb = normalize_for_matching(name_b)
        if na == nb:
            return 100.0
        # Check alias resolution
        if _resolve_alias(na) == _resolve_alias(nb):
            return 95.0
        if na in nb or nb in na:
            return 85.0
        return 0.0

    na = normalize_for_matching(name_a)
    nb = normalize_for_matching(name_b)

    if not na or not nb:
        return 0.0

    # Strategy 0: alias resolution (handles abbreviations like "NAVI"→"Natus Vincere")
    na_resolved = _resolve_alias(na)
    nb_resolved = _resolve_alias(nb)

    # Strategy 1: exact match after normalization (including alias resolution)
    if na == nb or na_resolved == nb_resolved:
        return 100.0
    # Cross-check: one is alias of the other's resolved form
    if na == nb_resolved or nb == na_resolved:
        return 95.0
    # Check if resolved forms are similar enough
    if na_resolved != na or nb_resolved != nb:
        # At least one was aliased — compare resolved forms with rapidfuzz
        resolved_score = fuzz.token_sort_ratio(na_resolved, nb_resolved)
        if resolved_score >= 80:
            return resolved_score

    # Strategy 2: token_sort_ratio (handles word reordering)
    score_sort = fuzz.token_sort_ratio(na, nb)
    if score_sort >= threshold:
        return score_sort

    # Strategy 3: token_set_ratio (handles extra tokens gracefully)
    # "jones" vs "emerson jones" → high score because "jones" is subset
    # BUT: guard against short names like "g2" giving 100 for "g2 junior"
    score_set = fuzz.token_set_ratio(na, nb)
    shorter_name = na if len(na) <= len(nb) else nb
    longer_name = nb if len(na) <= len(nb) else na
    shorter_tokens = shorter_name.split()
    longer_tokens = longer_name.split()
    if score_set >= 85:
        # Short name guard: if shorter is <=3 chars and names differ in length significantly,
        # cap the score — "g2" should not get 100 for "g2 junior"
        if len(shorter_name) <= 3 and len(longer_name) > len(shorter_name) + 3:
            score_set = min(score_set, 60)  # Penalize — likely different entity
        # Single-token guard: "inter" (1 token) vs "inter miami" (2 tokens)
        # where the extra token is the distinguishing part → cap score
        elif len(shorter_tokens) == 1 and len(longer_tokens) >= 2 and shorter_tokens[0] in longer_tokens:
            # The shorter is just a common prefix/word — not enough to confirm identity
            # Exception: if shorter resolves via alias to the longer, skip this guard
            if _resolve_alias(shorter_name) != longer_name:
                score_set = min(score_set, 70)  # Conservative — might still match but risky
        else:
            return score_set

    # Strategy 4: Containment — one name is fully contained in the other
    # Handles: "swiatek" is in "iga swiatek", "jones" is in "emerson jones"
    # BUT: prevent false positives for very short names (e.g., "G2" matching "G2 Junior")
    tokens_a = set(na.split())
    tokens_b = set(nb.split())
    if tokens_a and tokens_b:
        # Check if the shorter set of tokens is a subset of the longer
        shorter, longer = (tokens_a, tokens_b) if len(tokens_a) <= len(tokens_b) else (tokens_b, tokens_a)
        # Short name guard: if the shorter name is <=3 chars total, require exact match
        shorter_text = " ".join(sorted(shorter))
        if len(shorter_text) <= 3 and shorter != longer:
            # Very short name (e.g., "g2", "og", "t1") — don't grant subset bonus
            # unless it resolves via alias
            pass
        elif len(shorter) == 1 and len(longer) >= 2 and shorter.issubset(longer):
            # Single common word in a multi-word name (e.g., "inter" in "inter miami")
            # Ambiguous — could refer to multiple entities sharing the word.
            # Only grant full 85 if shorter resolves to longer via alias.
            if _resolve_alias(shorter_text) == " ".join(sorted(longer)):
                return 85.0
            # Otherwise cap: high enough to signal "related" but below typical threshold
            pass  # fall through to surname check or final max
        elif shorter.issubset(longer) and len(shorter) >= 1:
            # Multi-token subset match — award 85 (e.g., "man utd" subset of something)
            return 85.0

    # Strategy 5: surname-based matching for tennis
    # "swiatek" vs "iga swiatek" — surname of one matches surname of other
    surnames_a = _surname_tokens(na)
    surnames_b = _surname_tokens(nb)
    if surnames_a & surnames_b:
        return 82.0

    return max(score_sort, score_set)


def is_same_event(home_a: str, away_a: str, home_b: str, away_b: str, threshold: int = 70) -> bool:
    """Check if two events refer to the same match using smart name matching.

    Handles diacritics, emoji, partial names, name format differences.
    Tries both normal and swapped home/away order.
    """
    home_score = names_match(home_a, home_b, threshold)
    away_score = names_match(away_a, away_b, threshold)

    if home_score >= threshold and away_score >= threshold:
        return True

    # Try swapped order (home/away reversed between sources)
    home_score_swap = names_match(home_a, away_b, threshold)
    away_score_swap = names_match(away_a, home_b, threshold)

    return home_score_swap >= threshold and away_score_swap >= threshold


TEAM_NOISE_PATTERNS: Sequence[re.Pattern] = [
    re.compile(r"\s+(?:odd|odds)\s+\d+(?:\.\d+)?(?:\s+played\s+\d+)?$", re.IGNORECASE),
    re.compile(r"\s+bet\s+[12x]{1,2}(?:\s*odd\s*\d+(?:\.\d+)?)?(?:\s+played\s+\d+)?$", re.IGNORECASE),
    re.compile(r"\s+[12x]{1,2}\s+\d+(?:\.\d+)?(?:\s+\d+)?$", re.IGNORECASE),
    re.compile(r"\s+x\s+\d+(?:\.\d+)?(?:\s+\d+)?$", re.IGNORECASE),
    re.compile(r"\t[12x]?\t?\d+(?:\.\d+)?(?:\t\d+)?$", re.IGNORECASE),
    re.compile(r"(?:\s|\t)+[12x](?:\s|\t)+\d+(?:\.\d+)?(?:(?:\s|\t)+\d+)?$", re.IGNORECASE),
]


def strip_team_noise(raw: str | None) -> str:
    cleaned = (raw or "").replace("\t", " ").strip()
    for pattern in TEAM_NOISE_PATTERNS:
        cleaned = pattern.sub("", cleaned).strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned
