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
    # Added 2026-09-03. Each was found as a *split pair* in the recorded
    # slates -- one fixture, one kickoff to the second, one side of it matching
    # exactly -- and each scores far below any threshold a matcher may safely
    # use: "Hearts"/"Heart of Midlothian" 40, "QPR"/"Queens Park Rangers" 18,
    # "Wolves"/"Wolverhampton Wanderers" 53, "Lyon"/"Olympique Lyonnais" 36,
    # "Brest"/"Stade Brestois" 53. All five are club nicknames or full legal
    # names, which is this table's stated case; none is a qualifier, which is
    # the case it must not grow to hold.
    #
    # Hearts is the one that forced the question: on the live 2026-09-03 slate
    # Hibernian - Hearts arrived from two feeds as two fixtures, one carrying
    # the bzzoiro id and the other the Superbet price, and since ENRICH gates
    # the slate that deletes the Edinburgh derby rather than duplicating it.
    "Heart of Midlothian": {"Hearts"},
    "Queens Park Rangers": {"QPR"},
    "Wolverhampton Wanderers": {"Wolves"},
    "Olympique Lyonnais": {"Lyon"},
    "Stade Brestois": {"Brest"},
    # Added 2026-09-05, all found the same way: replay the day's own
    # ``unmatched_events`` against the events that got no offer, keep only
    # pairs sharing a kickoff *to the minute* where the board offers exactly
    # one candidate at that minute. Superbet is a Polish book and renders
    # several clubs in Polish, which is the "Sporting Lisbon" case in this
    # table's opening list and not a qualifier.
    #
    # Athletic/Atletico is why this batch exists. It was the only fixture on
    # the board at 14:15 and *neither* side joined: normalization strips the
    # club word from "Athletic Bilbao" and leaves the bare town "bilbao"
    # against our "athletic club", while "Madryt" is simply the Polish for
    # Madrid. La Liga's biggest fixture of the day reached the sheet with 206
    # rows and no price on any of them.
    #
    # Monchengladbach earns its place for the opposite reason to most: after
    # folding, "Borussia M'gladbach" and "Borussia Monchengladbach" share only
    # the token "borussia" -- which Dortmund also carries -- so the overlap
    # rule must never be loosened to join them and a pin is the only safe way.
    "Athletic Club": {"Athletic Bilbao"},
    "Atletico Madrid": {"Atletico Madryt"},
    "FC Bayern Munchen": {"Bayern Monachium", "Bayern Munich"},
    "Borussia Monchengladbach": {"Borussia M'gladbach"},
    "Racing Santander": {"Real Racing Club"},
    "Asteras Tripolis": {"Asteras Aktor"},
    "Royale Union Saint-Gilloise": {"Royale Union SG"},
    # Added 2026-09-08, found the same way and the same case as "Sporting
    # Lisbon": the Finnish club's own name against the initialism-plus-city the
    # book uses. Folded, "turun palloseura" and "tps turku" share **no** token,
    # so neither containment nor overlap can reach it and only a pin can.
    #
    # This one was expensive, and not in the usual way. The offer join failing
    # normally costs a fixture its price; here it fell on ENRICH's priced-gate
    # instead, which reads an unmatched fixture as one the book does not carry
    # and blocks it outright. Turun Palloseura - SJK was on the board at the
    # identical kickoff as `TPS Turku·SJK Seinajoki` and reached the sheet with
    # **zero rows** on a day three other Finnish fixtures made the coupon.
    #
    # Keyed on the whole folded string, which is what keeps it away from Inter
    # Turku -- the club this table's own opening note warns a token-level rule
    # would pair with anything containing "turku".
    "Turun Palloseura": {"TPS Turku", "TPS"},
    # Also 2026-09-08, and these three were *masked*: the Betradar id pass had
    # been quietly carrying them (74 of the day's matches came in by id), so
    # the name table never had to know them. Re-running the offer with the
    # bridge off -- which is the normal state, since OddsPapi is a 250-request
    # lifetime budget -- dropped all three, each with a future kickoff.
    #
    # Two are the "Sporting Lisbon" case verbatim, Superbet being a Polish book
    # rendering foreign cities in Polish, and the table already holds "Atletico
    # Madryt" for exactly this. The third is an initialism of the name we carry.
    #
    #   ours "Real Madrid"        theirs "Real Madryt"   -> {aek..} share 1 token
    #   ours "AEK Athens"         theirs "AEK Ateny"     -> ditto, below overlap
    #   ours "Kuopion Palloseura" theirs "KuPS"          -> no shared token at all
    #
    # Their opponents needed nothing: "Inter" is contained in "Inter Mediolan"
    # and "LASK" in "LASK Linz", which is containment's job and not this table's.
    "Real Madrid": {"Real Madryt"},
    "AEK Athens": {"AEK Ateny"},
    "Kuopion Palloseura": {"KuPS"},
    # Added 2026-09-12, found the same way: replay unmatched_events against
    # our_events_without_offer at an identical kickoff. Two are abbreviations
    # of a Brazilian/Portuguese place name, one is Superbet's Polish rendering
    # of a Romanian city, one is a club initialism -- the same four shapes
    # this table already exists for, none a qualifier.
    #
    #   ours "Atletico Mineiro"        theirs "Atletico MG"      -> share 1 token
    #   ours "FC Rapid Bucuresti"      theirs "Rapid Bukareszt"  -> share 1 token
    #   ours "MAS de Fes"              theirs "Maghreb de Fes"   -> share 2 of 3
    #   ours "Lusitano Ginasio Clube"  theirs "Lusitano Evora"   -> share 1 token
    #
    # Each cost its fixture a real, live Superbet price: Atletico Mineiro -
    # Fluminense, Rapid Bucuresti - Voluntari, Rahimo FC - MAS de Fes (CAF
    # Champions League) and Lusitano Ginasio Clube - SC Covilha all reached
    # ENRICH's competition-priced gate as "no price the operator can take"
    # while the book was pricing them under these names the whole time.
    "Atletico Mineiro": {"Atletico MG"},
    # Not "FC Rapid Bucuresti" alongside it -- that pair is a qualifier
    # ("FC " is a stripped club word both `normalize_team_name` and
    # `fold_club_name` already remove), and this table's own rule above says
    # qualifiers belong to containment, never to this dict.
    "Rapid Bucuresti": {"Rapid Bukareszt"},
    # Only "MAS de Fes" is the pair the 2026-09-12 slate actually proved;
    # "MAS Fes" was never seen and is not added on the strength of a guess.
    "Maghreb de Fes": {"MAS de Fes"},
    # Likewise only "Lusitano Evora" is proven; "Lusitano GC Evora" is not.
    "Lusitano Ginasio Clube": {"Lusitano Evora"},
}
# Deliberately *not* added from the same sweep, and the reasons are the rule:
#
#   "USC Paredes" / "Uniao SC Paredes"      qualifier -- containment's job
#   "Kansas City Current" / "Kansas City"   qualifier
#   "PS Sakiet Eddaier" / "A Sakiet Edayer" a transliteration, not a rename
#   "SC Jacksonville" / "Sporting Jax"      could not confirm one club
#
# And the sweep's own noise, worth recording so the next person does not
# rediscover it as signal: 194 FA Cup ties kick off at 14:00, so a
# one-side-joins heuristic pairs them arbitrarily. It offered "Whitby Town vs
# Ashton United" against "Ashton Adesoro vs Mateo Martinez" -- two tennis
# players. Uniqueness at the kickoff minute is what makes the evidence real.

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
