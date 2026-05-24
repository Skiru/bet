"""Shared utilities for the bet package.

Functions relocated from scripts/utils.py for proper import from src/bet/.
"""

import re
import unicodedata


def normalize_team_name(name: str) -> str:
    """Normalize team/player name for fuzzy matching across sources.

    Strips diacritics, removes common club suffixes (FC, SC, United, etc.),
    parenthetical qualifiers, age/gender/reserve suffixes, and extra whitespace.
    Returns lowercase.
    """
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name)
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


def is_same_event(home_a: str, away_a: str, home_b: str, away_b: str, threshold: int = 80) -> bool:
    """Check if two events refer to the same match using fuzzy matching.

    Uses rapidfuzz for Levenshtein ratio comparison on normalized team names.
    Returns True if both home and away teams match above threshold.
    """
    try:
        from rapidfuzz import fuzz
    except ImportError:
        # Fallback: exact normalized match
        return (normalize_team_name(home_a) == normalize_team_name(home_b) and
                normalize_team_name(away_a) == normalize_team_name(away_b))

    nh_a, na_a = normalize_team_name(home_a), normalize_team_name(away_a)
    nh_b, na_b = normalize_team_name(home_b), normalize_team_name(away_b)

    home_score = fuzz.ratio(nh_a, nh_b)
    away_score = fuzz.ratio(na_a, na_b)

    return home_score >= threshold and away_score >= threshold
