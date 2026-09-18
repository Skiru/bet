import json
import re
import unicodedata
from pathlib import Path

DIACRITICS_FOLD = {
    "ø": "o",
    "ł": "l",
    "đ": "d",
    "ı": "i",
    "æ": "ae",
    "ß": "ss",
    "ð": "d",
    "þ": "th",
}

_ALIASES_CACHE: dict[str, str] = {}
_ALIASES_LOADED = False

# Every spelling of "this is the women's team" either source uses, collapsed to
# one. Anchored at the end because it is a suffix; "Women's United" is a club
# name, not a marker.
_GENDER_MARKER = re.compile(
    r"\s*(?:\((?:k|w|f)\)|\bkobiety\b|\bwomen\b|\bfemale\b)\s*$",
    re.IGNORECASE,
)


def is_womens_name(name: str) -> bool:
    """True when the normalised name carries the women's marker."""
    return normalize_name(name).endswith("(w)")


def get_aliases() -> dict[str, str]:
    global _ALIASES_LOADED
    if not _ALIASES_LOADED:
        config_path = (
            Path(__file__).parent.parent.parent.parent
            / "config"
            / "sofa_name_aliases.json"
        )
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                _ALIASES_CACHE.update(json.load(f))
        _ALIASES_LOADED = True
    return _ALIASES_CACHE


def normalize_name(name: str) -> str:
    name = name.strip()

    # 1. Custom diacritics fold before NFD
    for char, replacement in DIACRITICS_FOLD.items():
        name = name.replace(char, replacement)
        name = name.replace(char.upper(), replacement.upper())

    # 2. NFD normalization and remove non-ASCII
    name = unicodedata.normalize("NFD", name)
    name = name.encode("ascii", "ignore").decode("ascii")

    name = name.lower()

    # 3. Gender marker — normalised to one form, "(w)", and KEPT.
    #
    # It used to map " (k)" to " w", dropping the brackets, while Superbet's
    # English "(w)" kept them. So "Millonarios (K)" became "millonarios w" and
    # Sofascore's own "Arsenal (W)" became "arsenal (w)": two strings that can
    # never be equal, and 47 of the 54 marked names on the board went to
    # sofa_entity_miss. Resolution for women's football fell from the slate's
    # ~78% to 13% (F16).
    #
    # The marker stays in the name, and therefore in the cache key, on purpose.
    # A women's side and a men's side of the same club are two different teams
    # with one name; keeping the marker is what stops them sharing an entity
    # even when their kickoffs agree, which is the residual risk F25 leaves
    # open.
    name = _GENDER_MARKER.sub(" (w)", name)

    aliases = get_aliases()

    # Extract prefixes to map if they exist in aliases
    words = name.split()
    if words:
        # Check first word
        if words[0] in aliases:
            words[0] = aliases[words[0]]
        # Check first two words (e.g., "stany zjednoczone")
        elif len(words) >= 2:
            two_words = f"{words[0]} {words[1]}"
            if two_words in aliases:
                words[0] = aliases[two_words]
                del words[1]

        name = " ".join(words)

    # 4. Reserves marker — normalised to an explicit "(r)", never removed.
    #
    # Anchored to the END of the name on purpose. A reserve marker is a suffix:
    # "Boca Juniors II", "Real Madrid B", "Bayern U21". Matching the token
    # anywhere turns "1899 Hoffenheim II" into a reserve side correctly, but
    # also turns every standalone "b" in the middle of a name into one — and a
    # false reserve match is worse than no match, because it silently builds a
    # dossier from the wrong squad.
    name = re.sub(r"\s+(?:ii|b|u21|u-21)\s*$", " (r)", name)

    # Collapse repeated or nested markers left by an already-marked name.
    name = re.sub(r"\(\(r\)\)", "(r)", name)
    name = re.sub(r"(?:\s*\(r\))+\s*$", " (r)", name)

    return re.sub(r"\s+", " ", name).strip()
