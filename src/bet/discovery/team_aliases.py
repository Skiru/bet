"""Clubs two feeds call by genuinely different names.

Not a fuzzy matcher, and deliberately not extensible by similarity. Every entry
is a pair the 2026-08-28 slate proved was one fixture -- same kickoff, same
competition, same two clubs -- that no amount of normalization can join, because
the two names share no distinguishing token:

    "Stade Lavallois" / "Laval"          the town, and the club named for it
    "Shanghai SIPG" / "Shanghai Port"    a rebrand both feeds still use
    "Sporting Lisbon" / "Sporting CP"    an English exonym
    "Nautico PE" / "Nautico Recife"      state abbreviation vs city
    "Erzurum BB" / "Erzurumspor FK"      two renderings of one Turkish club

The *qualifier* case -- "Genk" / "KRC Genk", "Alaves" / "Deportivo Alaves" -- is
not here and must not be added: token containment already answers it in
dedup.py, and a table that also held those would grow with every feed rather
than only with every genuinely renamed club.

Aliases are keyed on the lightly folded name, before ``normalize_team_name``
strips club words. That ordering is not cosmetic: normalization turns "Sporting
CP" into "cp" and "Sporting Lisbon" into "lisbon", so a table keyed after it
would have to assert that the token "cp" means this club -- which is how a
table starts guessing.
"""
from __future__ import annotations

import re
import unicodedata

from bet.utils.common import SPECIAL_CHAR_MAP


def fold_club_name(name: str) -> str:
    """Lowercase, ASCII-folded, punctuation-free form. No club words removed.

    Apostrophes are *deleted* rather than turned into a space, which the rest of
    the punctuation is. Splitting on one produces "patrick s" from "Patrick's",
    a token the other feed's "Patricks" can never match -- and since this fold
    runs before ``normalize_team_name``, it would undo that function's own
    apostrophe handling.

    ``SPECIAL_CHAR_MAP`` is applied *before* NFKD and is not optional. NFKD
    decomposes ó and ę into a base letter plus a combining mark, which the next
    line drops cleanly, but it does **not** decompose ł, ø, đ, ß or ħ -- those
    are distinct letters, not accented ones. Without the map they survive NFKD,
    fail the ``[a-z0-9]`` class, and are replaced by a *space*, so "Wisła Płock"
    folds to "wis a p ock" and can never equal the "wisla plock" the English
    feeds publish. Measured on the 2026-09-01 football slate: ten of the 104
    fixtures Superbet was carrying had no price for exactly this reason --
    Wisła Kraków, Zagłębie Lubin, Wigry Suwałki, Puszcza Niepołomice and the
    rest of the Polish league. ``normalize_team_name`` already carried the
    same table; this fold runs first and undid it.
    """
    folded = (name or "").casefold().translate(SPECIAL_CHAR_MAP)
    folded = unicodedata.normalize("NFKD", folded)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = folded.replace("'", "").replace("\u2019", "")
    return re.sub(r"[^a-z0-9]+", " ", folded).strip()


# Canonical club name -> every other rendering a feed has been seen to use.
# Both sides are written as ordinary names and folded at import.
TEAM_ALIASES: dict[str, set[str]] = {
    "Laval": {"Stade Lavallois"},
    "Shanghai Port": {"Shanghai SIPG", "Shanghai SIPG FC"},
    "Sporting CP": {"Sporting Lisbon", "Sporting Lisboa"},
    "Nautico": {"Nautico PE", "Nautico Recife"},
    "Erzurumspor FK": {"Erzurum BB", "Erzurum Buyuksehir Belediyesi"},
}

# Reverse index, built once. A rendering listed under two canonical clubs is a
# table bug -- it would make the alias step itself ambiguous -- so it raises at
# import rather than being settled by dict order.
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for _canonical, _aliases in TEAM_ALIASES.items():
    _canonical_folded = fold_club_name(_canonical)
    for _alias in {_canonical, *_aliases}:
        _key = fold_club_name(_alias)
        _existing = _ALIAS_TO_CANONICAL.get(_key)
        if _existing is not None and _existing != _canonical_folded:
            raise ValueError(
                f"team alias {_key!r} maps to both {_existing!r} and {_canonical_folded!r}"
            )
        _ALIAS_TO_CANONICAL[_key] = _canonical_folded


def resolve_team_alias(name: str) -> str:
    """The canonical rendering of a club name, folded. Unknown names pass through.

    Pass-through is the overwhelmingly common case: this resolves renames, not
    spellings, and the returned string is meant to be handed to
    ``normalize_team_name`` exactly as the original would have been.
    """
    folded = fold_club_name(name)
    return _ALIAS_TO_CANONICAL.get(folded, folded)
