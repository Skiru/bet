"""Letters that are letters, not accents, and the fixtures they used to lose.

``fold_club_name`` runs *before* ``normalize_team_name`` and used to undo it.
Its NFKD pass strips combining marks -- correct for ó, ę, ç -- but ł, ø, đ, ß,
ı, þ, ð and æ are not accented bases and survive NFKD intact. The next line,
``re.sub(r"[^a-z0-9]+", " ", ...)``, then replaced each of them with a **space**,
so "Wisła Płock" folded to "wis a p ock": three tokens, none of them a club.

``normalize_team_name`` already carried the transliteration table that fixes
this and had done since long before. The fold simply ran first and threw the
letters away before that table could ever see them.

Measured cost, on the 2026-09-01 football slate, of exactly this bug: ten of
the 104 fixtures Superbet was carrying could not be matched to our own event
list, and every one of them was a Polish club -- Wisła Kraków, Zagłębie Lubin,
Wigry Suwałki, Puszcza Niepołomice, Wisła Płock II, Sandecja Nowy Sącz. Nine
point six percent of the slate, silently unpriced.

These are regression tests for a *matching* property, so each one asserts that
the two feeds' spellings land on the same key -- not that the key has any
particular shape.
"""
from __future__ import annotations

import pytest

from bet.discovery.team_aliases import fold_club_name, resolve_team_alias
from bet.utils import normalize_team_name


def key(name: str) -> str:
    """The join key the whole pipeline compares clubs on."""
    return normalize_team_name(resolve_team_alias(name))


# (an English feed's spelling, the local spelling, the letter that used to break it)
SAME_CLUB = [
    ("Wisla Plock", "Wisła Płock", "ł"),
    ("Wisla Krakow", "Wisła Kraków", "ł"),
    ("Zaglebie Lubin", "Zagłębie Lubin", "ł"),
    ("Wigry Suwalki", "Wigry Suwałki", "ł"),
    ("Puszcza Niepolomice", "Puszcza Niepołomice", "ł"),
    ("Sandecja Nowy Sacz", "Sandecja Nowy Sącz", "ą"),
    ("Brondby", "Brøndby", "ø"),
    ("Dong A Thanh Hoa", "Đông Á Thanh Hóa", "Đ"),
    ("Besiktas", "Beşiktaş", "ş"),
    ("Kizilcabolukspor", "Kızılcabölükspor", "ı"),
    ("Thor Akureyri", "Þór Akureyri", "Þ"),
]


@pytest.mark.parametrize("ascii_form,local_form,letter", SAME_CLUB, ids=[c[1] for c in SAME_CLUB])
def test_the_two_spellings_of_one_club_fold_to_one_key(ascii_form, local_form, letter):
    assert key(ascii_form) == key(local_form), (
        f"{letter!r} is being dropped rather than transliterated, so "
        f"{local_form!r} can never match {ascii_form!r}"
    )
    assert key(local_form), "the club folded away to nothing"


@pytest.mark.parametrize("ascii_form,local_form,letter", SAME_CLUB, ids=[c[1] for c in SAME_CLUB])
def test_a_special_letter_never_becomes_a_word_break(ascii_form, local_form, letter):
    """The specific old failure: a space where a letter used to be.

    "Wisła" -> "wis a" is not a near miss a fuzzier matcher would rescue; it is
    two tokens where there was one, and ``sides_compatible`` scores token
    overlap, so the stray "a" counts as a shared word with any club that also
    lost a letter.

    Stated as "the same word count as the ASCII spelling" rather than "no
    one-letter tokens", because a one-letter token can be genuine -- "Á" is a
    word in "Đông Á Thanh Hóa".
    """
    assert len(fold_club_name(local_form).split()) == len(fold_club_name(ascii_form).split()), (
        f"{local_form!r} folded to {fold_club_name(local_form)!r} but "
        f"{ascii_form!r} folded to {fold_club_name(ascii_form)!r}: {letter!r} "
        f"was replaced by a space instead of a letter"
    )


def test_the_fold_still_removes_punctuation_and_case():
    assert fold_club_name("  FC  Bayern-München  ") == "fc bayern munchen"


def test_apostrophes_are_still_deleted_rather_than_split_on():
    """Splitting produces "patrick s", which no other feed's spelling matches."""
    assert fold_club_name("St Patrick's Athletic") == "st patricks athletic"
    assert fold_club_name("AFC '34") == "afc 34"


def test_the_alias_table_is_reachable_through_the_new_fold():
    """The reverse index is built with this same function, so a change to it
    that broke the table would silently disable every rename in it."""
    assert key("Stade Lavallois") == key("Laval")
    assert key("Shanghai SIPG") == key("Shanghai Port")
    assert key("Sporting Lisbon") == key("Sporting CP")


def test_two_different_clubs_do_not_collide_through_the_transliteration():
    """The point is to recover letters, not to blur clubs together."""
    assert key("Wisła Kraków") != key("Wisła Płock")
    assert key("Zagłębie Lubin") != key("Zagłębie Sosnowiec")
