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

    name = apply_aliases(name)

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


def apply_aliases(name: str) -> str:
    """Rewrite known exonyms and abbreviations anywhere in the name.

    It used to look only at the FIRST word, and only there. That is right for
    the country names the table was built for — "Polska·Niemcy" — and wrong
    for every club, because a club's exonym sits where the city sits, which is
    rarely the front: "Bayern Monachium", "Rapid Wieden", "Obolon Kijow",
    "Sporting Lizbona". Superbet writes the Polish city, Sofascore writes the
    local one, and no fuzzy scorer bridges "monachium" to "munchen" — measured
    66.7, against a threshold of 82 (F50).

    Two-token keys are matched before single tokens so "stany zjednoczone" and
    "papua nowa gwinea" still collapse to one word.
    """
    aliases = get_aliases()
    if not aliases:
        return name

    words = name.split()
    out: list[str] = []
    i = 0
    while i < len(words):
        three = " ".join(words[i : i + 3]) if i + 2 < len(words) else None
        two = " ".join(words[i : i + 2]) if i + 1 < len(words) else None
        if three is not None and three in aliases:
            out.append(aliases[three])
            i += 3
        elif two is not None and two in aliases:
            out.append(aliases[two])
            i += 2
        elif words[i] in aliases:
            out.append(aliases[words[i]])
            i += 1
        else:
            out.append(words[i])
            i += 1
    return " ".join(out)


# Age-group and reserve markers, as they appear once normalise has run.
#
# The reserve suffix rule in `normalize_name` turns a trailing "II"/"B"/
# "U21" into "(r)", but
# an age marker in the MIDDLE of a name survives — "Flamengo de Guarulhos U20"
# — and a senior club's name is a strict token subset of it. Under a token-set
# scorer that scores 100.0, which is how a senior side and an under-20 side of
# the same club become one team.
_AGE_MARKER = re.compile(r"\bu ?-?(14|15|16|17|18|19|20|21|22|23)\b")
_RESERVE_MARKER = re.compile(r"(?:\(r\)|\bii\b|\breserves?\b)")


def team_levels(name: str) -> frozenset[str]:
    """Which squads this name could denote: {"S"}, {"R"}, {"U20"}, ...

    A *set*, not a value, because a name may legitimately carry both — Panama's
    "Plaza Amador Reserves U20" is the reserve side and the under-20 side at
    once, and the board calls it "Plaza Amador (R)". Requiring the two sets to
    intersect keeps that pair together while still separating "Flamengo" from
    "Flamengo de Guarulhos U20".
    """
    found = {"U" + m for m in _AGE_MARKER.findall(name)}
    if _RESERVE_MARKER.search(name):
        found.add("R")
    return frozenset(found) if found else frozenset({"S"})


def levels_compatible(a: str, b: str) -> bool:
    """True when two names could denote the same squad of the same club."""
    return bool(team_levels(a) & team_levels(b))
