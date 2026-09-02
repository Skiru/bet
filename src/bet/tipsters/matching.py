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
#
# Grouped into classes rather than compared as bare tokens, because sources
# render the same distinction differently: ZawodTyper writes the women's side as
# "Servette K" where the event list writes "Servette Women". Comparing tokens
# made those two disagree (a false veto) while "Servette K" against the *men's*
# "Servette FC" saw no marker at all and scored 86 -- one point under threshold
# on the 2026-09-02 slate, so a women's pick reaching the men's fixture was luck
# rather than design. Classes fix both directions at once.
#
# The age groups are deliberately one class each: a U19 side and a U21 side are
# not two renderings of one team.
_MARKER_CLASSES: dict[str, str] = {
    **{token: "reserve2" for token in "b ii 2 res reserve reserves am amateurs".split()},
    **{token: "reserve3" for token in "c iii 3".split()},
    **{token: "youth" for token in "juniors junior youth academy akademia".split()},
    **{token: token for token in "u17 u18 u19 u20 u21 u23".split()},
    **{
        token: "women"
        for token in "w women womens ladies feminin femenino frauen kobiet kobiety dames".split()
    },
}

# Polish sources mark a women's fixture with a trailing "K" -- "Servette K",
# "Sparta Praga [K]". Rewritten before tokenizing rather than added to the class
# table above, because position is what makes it a marker: Belgian clubs carry a
# *leading* "K" (Koninklijke) that means nothing of the sort.
_TRAILING_WOMEN_MARKER = re.compile(r"\s+k$", re.I)

# Two or more single letters each closed by a dot: "F.C.", "A.C.", "S.S.".
_DOTTED_ABBREVIATION = re.compile(r"\b(?:[A-Za-z]\.){2,}")

# How *tipster sources* render clubs the event list carries under another name.
#
# Separate from ``bet.discovery.team_aliases`` on purpose. That table is the
# feed-to-feed one and is keyed to fixtures a slate proved; this one exists
# because two of the three sources publish in Polish, so they translate the city
# ("Bayern Monachium", "Sparta Praga") where every provider feed keeps it. Those
# are deterministic translations rather than the club renames that table holds,
# and confining them here keeps the fix off the Superbet join, which never sees
# a Polish rendering.
#
# Every entry below was confirmed against the 2026-09-02 slate: same kickoff,
# same competition, same two clubs. Keys are folded at lookup, so both sides are
# written here as ordinary names.
_TIPSTER_RENDERINGS: dict[str, str] = {
    fold_club_name(source): canonical
    for source, canonical in {
        "Bayern Monachium": "Bayern Munich",
        "Red Bull Salzburg": "RB Salzburg",
        "Rapid Vienna": "Rapid Wien",
        "SK Rapid": "Rapid Wien",
        "MK Dons": "Milton Keynes Dons",
        "AEL Larissa": "Larisa",
        "Larissa": "Larisa",
        "Mardin 1969": "Mardin BB",
        # The slate carries this fixture twice, once per spelling, so the
        # canonical form has to be the one containment can reach from both.
        "Royale Union SG": "Royale Union Saint-Gilloise",
        "Union SG": "Royale Union Saint-Gilloise",
        "St Truiden": "Sint Truiden",
        "Sint-Truidense VV": "Sint Truiden",
        # The Egyptian club's English name against the Arabic one the feed uses.
        "Arab Contractors": "El Mokawloon",
    }.items()
}

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


def _fold(name: str, *, person: bool = False) -> str:
    """Alias-resolved, Polish-safe fold. Empty for anything unusable."""
    raw = name or ""
    if not person:
        # "F.C." survives the fold as the two tokens "f" and "c", and "c" is how
        # a third team is written -- so "Falkirk F.C." was marker-vetoed against
        # "Falkirk" and scored 0. Rejoining the letters restores the single "fc"
        # token, which the generic-club set already knows carries no identity.
        # Person mode is excluded: the same collapse turns "Cirstea J. C." into
        # "cirstea jc" and destroys the initials _person_score reads.
        raw = _DOTTED_ABBREVIATION.sub(lambda m: m.group(0).replace(".", ""), raw)
    resolved = resolve_team_alias(_TIPSTER_RENDERINGS.get(fold_club_name(raw), raw))
    return _TRAILING_WOMEN_MARKER.sub(" women", resolved)


def _tokens(folded: str) -> set[str]:
    return {token for token in folded.split() if token}


def _markers(tokens: set[str]) -> set[str]:
    return {_MARKER_CLASSES[token] for token in tokens if token in _MARKER_CLASSES}


def _marker_mismatch(a_tokens: set[str], b_tokens: set[str]) -> bool:
    """Do the two names disagree about being a reserve/youth/women's side?

    Returned as a hard veto rather than a low score. "Barcelona" against
    "Barcelona B" is 90 by sequence ratio -- comfortably over any workable
    threshold -- so leaving this to the fallback would attach a reserve-team
    pick to the senior fixture, which is precisely the attribution error the
    high threshold exists to prevent.
    """
    return _markers(a_tokens) != _markers(b_tokens)


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

# Tokens that attach to a surname without being one. Two players sharing only
# these share nothing.
_NAME_PARTICLES = frozenset(
    "de del della di da das dos do du la le el al bin ben van von der den ter st mc mac".split()
)


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
    # Sharing only something like "de" or "van" is not an identification. The
    # rule used to be a four-character floor, which reads as a proxy for the
    # same thing and is not one: it also threw out every short surname, so
    # "Y. Wu" could not reach "Wu Yibing". Naming the particles says what was
    # actually meant and stops discarding people whose names are simply short.
    if not (shared_full - _NAME_PARTICLES):
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


def _identifying(folded: str) -> str:
    """The folded name with club-structure words removed, if any remain.

    The sequence-ratio fallback measures the whole string, so shared or unshared
    structure words move a score that should turn on the club's actual name.
    "Midtyland" against "FC Midtjylland" scored 78 -- under threshold -- because
    the "fc" the source omitted counted against a spelling that is otherwise a
    two-letter slip. Scoring "midtyland" against "midtjylland" reads 90.

    It also cuts the other way, which is the reason to prefer it over a bare
    ratio rather than merely tolerate it: "Real Madrid" against "Real Sociedad"
    loses the "real" that was inflating it.

    Returns the original when stripping would leave nothing, since a name made
    entirely of structure words is all the identity there is.
    """
    remainder = " ".join(t for t in folded.split() if t not in _GENERIC_CLUB_TOKENS)
    return remainder or folded


def side_score(pick_side: str, event_side: str, *, person: bool = False) -> int:
    """How strongly two renderings name the same team or player, 0-100."""
    a, b = _fold(pick_side, person=person), _fold(event_side, person=person)
    if not a or not b:
        return 0
    if a == b:
        return 100
    a_tokens, b_tokens = _tokens(a), _tokens(b)
    if person:
        # No marker veto here. The markers are club vocabulary, and against a
        # person's name they read the wrong thing entirely: "Shelton B." is a
        # surname and an initial, but "b" is also how a reserve side is written,
        # so every player whose given name starts with b, c or w was vetoed to 0
        # and lost -- Ben Shelton, Brandon Nakashima and Sorana Cirstea on the
        # 2026-09-02 slate alone. _person_score does the discriminating instead,
        # and it is strict: it requires the surnames to agree outright.
        scored = _person_score(a_tokens, b_tokens)
        if scored is not None:
            return scored
    elif _marker_mismatch(a_tokens, b_tokens):
        return 0
    contained = _containment_score(a_tokens, b_tokens)
    if contained is not None:
        return contained
    return round(SequenceMatcher(None, _identifying(a), _identifying(b)).ratio() * 100)


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
