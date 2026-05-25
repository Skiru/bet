"""Shared utilities for the bet package.

Functions relocated from scripts/utils.py for proper import from src/bet/.
"""

import re
import unicodedata


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
        if na in nb or nb in na:
            return 85.0
        return 0.0

    na = normalize_for_matching(name_a)
    nb = normalize_for_matching(name_b)

    if not na or not nb:
        return 0.0

    # Strategy 1: exact match after normalization
    if na == nb:
        return 100.0

    # Strategy 2: token_sort_ratio (handles word reordering)
    score_sort = fuzz.token_sort_ratio(na, nb)
    if score_sort >= threshold:
        return score_sort

    # Strategy 3: token_set_ratio (handles extra tokens gracefully)
    # "jones" vs "emerson jones" → high score because "jones" is subset
    score_set = fuzz.token_set_ratio(na, nb)
    if score_set >= 85:
        return score_set

    # Strategy 4: Containment — one name is fully contained in the other
    # Handles: "swiatek" is in "iga swiatek", "jones" is in "emerson jones"
    tokens_a = set(na.split())
    tokens_b = set(nb.split())
    if tokens_a and tokens_b:
        # Check if the shorter set of tokens is a subset of the longer
        shorter, longer = (tokens_a, tokens_b) if len(tokens_a) <= len(tokens_b) else (tokens_b, tokens_a)
        if shorter.issubset(longer) and len(shorter) >= 1:
            # Surname-only match — award 85 if the surname token matches
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
