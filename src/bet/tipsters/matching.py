"""Fixture-name matching for the tipster column.

Why this is not ``normalization.names_score``
---------------------------------------------
``names_score`` is ``SequenceMatcher`` over ``normalize_key``. Both halves of
that are wrong for club names, and the 2026-09-01 slate measured the cost: of
86 picks fetched, 61 matched no fixture, and 27 of those 61 named a team the
event list was carrying under a longer rendering.

**The fold drops Polish letters.** ``normalize_key`` ASCII-folds via NFKD, which
decomposes ó and ę but leaves ł, ø and đ intact -- and the next step replaces
them with a *space*. "Wisła Kraków" becomes "wis a krakow" and "Łódź" becomes
"odz". No Polish club could match reliably, on a slate that is largely Polish.
``fold_club_name`` already solved this for the Superbet join; this module reuses
it rather than keeping a second, worse copy.

**Sequence ratio punishes the true positives.** Sources publish short names and
the event list publishes long ones. "Birmingham" against "Birmingham City"
scores 80, under the threshold of 82; "West Ham" against "West Ham United"
scores 70; "Akron" against "Akron Togliatti" scores 50. Every one of those is
the same club, and the *reason* the score is low -- one name is a prefix of the
other -- is the very thing that makes it a match.

So a side is compared by token containment first and by sequence ratio only as
a fallback, and the containment rule is guarded against the one case where it
would be wrong: a reserve or qualifier marker in the extra tokens.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from bet.discovery.team_aliases import fold_club_name, resolve_team_alias

# Tokens that make a longer name a *different* team rather than a fuller
# rendering of the same one. "Barcelona" is contained in "Barcelona B", and they
# are not the same side; neither are a senior XI and its U19, nor a men's team
# and the women's team, nor a club and its qualifier entry. Containment is only
# allowed to conclude "same team" when the surplus tokens are ordinary name
# words, so these are checked before it can fire.
_DISTINCT_TEAM_MARKERS = frozenset(
    """
    b c ii iii 2 3 res reserve reserves am amateurs akademia academy
    u17 u18 u19 u20 u21 u23 juniors junior youth
    w women womens ladies feminin femenino frauen kobiet kobiety
    """.split()
)

# Ordinary club-structure words. They carry no identity on their own -- every
# league has dozens of each -- so a lone shared token of this kind is not
# evidence that two names are the same club.
_GENERIC_CLUB_TOKENS = frozenset(
    """
    fc fk sc ac cf cd ca sk if bk aik ff sv tsv vfl vfb bsc fsv
    club clube deportivo atletico athletic sporting real united city town
    sport sports association ec sp rj sa mg pe fa afc cfc nk hk gks mks ks lks
    """.split()
)


def _fold(name: str) -> str:
    """Alias-resolved, Polish-safe fold. Empty for anything unusable."""
    return resolve_team_alias(name or "")


def _tokens(folded: str) -> set[str]:
    return {token for token in folded.split() if token}


def _marker_mismatch(a_tokens: set[str], b_tokens: set[str]) -> bool:
    """Do the two names disagree about being a reserve/youth/women's side?

    Returned as a hard veto rather than a low score. "Barcelona" against
    "Barcelona B" is 90 by sequence ratio -- comfortably over any workable
    threshold -- so leaving this to the fallback would attach a reserve-team
    pick to the senior fixture, which is precisely the attribution error the
    high threshold exists to prevent.
    """
    return (a_tokens & _DISTINCT_TEAM_MARKERS) != (b_tokens & _DISTINCT_TEAM_MARKERS)


def _containment_score(a_tokens: set[str], b_tokens: set[str]) -> int | None:
    """Score when one name's tokens are a subset of the other's, else None."""
    if not a_tokens or not b_tokens:
        return None
    if a_tokens == b_tokens:
        return 100
    shorter, longer = (a_tokens, b_tokens) if len(a_tokens) < len(b_tokens) else (b_tokens, a_tokens)
    if not shorter <= longer:
        return None
    # A containment that rests entirely on generic structure words ("FC" inside
    # "FC Zurich") identifies nothing; it would make every club match every other
    # club that shares a prefix word.
    if shorter <= _GENERIC_CLUB_TOKENS:
        return None
    return 95


_INITIAL = re.compile(r"^[a-z]$")


def _person_score(a_tokens: set[str], b_tokens: set[str]) -> int | None:
    """Score for two renderings of one player's name, else None.

    Tennis sources write "Sakkari M.", "M. Sakkari" and "Maria Sakkari" for the
    same person, and abbreviate the *given* name in either position. Containment
    cannot see these as equal because "m" is not "maria". So: the surnames must
    agree outright, and every remaining token must be either shared or an
    initial consistent with a full name on the other side.
    """
    if not a_tokens or not b_tokens:
        return None
    a_full = {t for t in a_tokens if not _INITIAL.match(t)}
    b_full = {t for t in b_tokens if not _INITIAL.match(t)}
    shared_full = a_full & b_full
    # A shared surname is a token of real length. Sharing only something like
    # "de" or "van" is not an identification.
    if not any(len(token) >= 4 for token in shared_full):
        return None
    a_rest, b_rest = a_full - shared_full, b_full - shared_full
    a_initials = {t for t in a_tokens if _INITIAL.match(t)}
    b_initials = {t for t in b_tokens if _INITIAL.match(t)}

    def consistent(rest: set[str], initials: set[str]) -> bool:
        """Every unshared full name is covered by an initial on the other side."""
        return all(any(name.startswith(i) for i in initials) for name in rest)

    if a_rest and not consistent(a_rest, b_initials):
        return None
    if b_rest and not consistent(b_rest, a_initials):
        return None
    return 95 if (a_rest or b_rest or a_initials or b_initials) else 100


def side_score(pick_side: str, event_side: str, *, person: bool = False) -> int:
    """How strongly two renderings name the same team or player, 0-100."""
    a, b = _fold(pick_side), _fold(event_side)
    if not a or not b:
        return 0
    if a == b:
        return 100
    a_tokens, b_tokens = _tokens(a), _tokens(b)
    if _marker_mismatch(a_tokens, b_tokens):
        return 0
    if person:
        scored = _person_score(a_tokens, b_tokens)
        if scored is not None:
            return scored
    contained = _containment_score(a_tokens, b_tokens)
    if contained is not None:
        return contained
    return round(SequenceMatcher(None, a, b).ratio() * 100)


def pair_score(
    pick_home: str, pick_away: str, event_home: str, event_away: str, *, person: bool = False
) -> tuple[int, bool]:
    """Best of straight and swapped orientation, and which one it was.

    Both sides must clear the caller's threshold, so the pair score is the
    weaker of the two: a fixture is not identified by recognising one team.
    """
    straight = min(
        side_score(pick_home, event_home, person=person),
        side_score(pick_away, event_away, person=person),
    )
    swapped = min(
        side_score(pick_home, event_away, person=person),
        side_score(pick_away, event_home, person=person),
    )
    if swapped > straight:
        return swapped, True
    return straight, False
