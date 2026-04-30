"""Shared utilities for betting pipeline scripts."""

import re
import unicodedata


def normalize_team_name(name: str) -> str:
    """Normalize team/player name for fuzzy matching across sources.

    Strips diacritics, removes common club suffixes (FC, SC, United, etc.),
    parenthetical qualifiers, and extra whitespace. Returns lowercase.
    """
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\s*\([^)]*\)\s*", " ", s)
    s = re.sub(
        r"\b(FC|SC|CF|CD|SK|FK|AS|AC|US|SS|SV|TSV|VfB|VfL|BSC|"
        r"IF|BK|IFK|AIK|FF|GIF|AFC|RFC|SFC|CFC|United|Utd|City|"
        r"Town|Rovers|Wanderers|Athletic|Athletico|Sporting)\b",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\s+", " ", s).strip()
    return s.lower()
