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

    # 3. Polish team/country names & specific suffixes
    # " (k)" -> " w"
    # " u20" -> " u20" etc (already standard, but ensure we don't mess it up)
    name = name.replace(" (k)", " w")

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
