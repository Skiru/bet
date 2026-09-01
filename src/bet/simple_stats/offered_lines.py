"""The lines Superbet actually posts, keyed the way ANALYZE asks for them.

Why the direction is inverted here
----------------------------------
Before this module, ANALYZE picked a line from a fixed grid and SUPERBET was
asked afterwards whether the book carried it. On the 2026-08-31 run that
produced ``LINE_NOT_OFFERED`` on a large share of the sheet, and for some
markets it could never produce anything else: measured on a live fixture,
Superbet quotes **one** line for match fouls (30.5) against our 20.5/22.5/24.5,
one for tackles (28.5), one for per-team tackles (14.5). A fixed grid cannot hit
a line the book picks per fixture, and adding more grid points does not fix it —
it just moves the miss.

So the grid stops being the question. ``OfferedLines`` reads the offer that
SUPERBET already wrote to disk and answers "which lines exist for this event,
this market, this side" — and ANALYZE computes ``p_low`` for exactly those.
``STANDARD_MARKET_LINES`` stays as the fallback for events with no offer at all
(fixtures Superbet does not carry, sports it does not price), so a run without a
SUPERBET step produces the same sheet it always did.

This is a separate module rather than a function in ``superbet_offer`` so that
ANALYZE does not have to import the SUPERBET stage to run. Both stages import
this; neither imports the other.

The player join, and why it lives here
--------------------------------------
Superbet names players inside the outcome string, in its own spelling
("Lodi, Renan - powyżej 0.5"). Our rows carry the dossier's spelling
("Renan Lodi"). Joining the two is the one operation in this pipeline where a
wrong answer is **silent**: a mismatched prop is not an empty column, it is a
plausible-looking row with somebody else's price on it. So the join happens once,
here, under a uniqueness rule strict enough to refuse rather than guess — the
same shape as the two-layer fixture guard, moved down a level.
"""
from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from bet.simple_stats.contracts import SuperbetOfferV1

# How many offered lines one sample may produce rows for. Superbet posts up to
# 16 corner lines on a big fixture where the static grid had 7; taking all of
# them would multiply the sheet without adding a decision, since the lines far
# from the sample's own median are the ones no evidence can speak to. Six is the
# width of the widest static grid (`Team Corners`), so the sheet's size stays in
# the range the rest of the pipeline was sized for.
MAX_OFFERED_LINES_PER_SAMPLE = 6

# Below this, two names are not the same player. Deliberately high: the cost of
# a missed prop is an empty column, and the cost of a wrong one is a priced row
# naming the wrong human.
PLAYER_MATCH_THRESHOLD = 88.0

_OfferedKey = tuple[str, str, str | None, str | None]


# ł and Ø are letters in their own right, not accented bases, so NFKD leaves
# them intact and the combining-mark filter then drops them entirely --
# "Michał" would fold to "micha". Every other Latin diacritic this pipeline
# meets (Portuguese ã/ç, Spanish ñ/á, French é) decomposes correctly.
_LETTER_FOLD = str.maketrans({"ł": "l", "Ł": "l", "ø": "o", "Ø": "o",
                              "đ": "d", "Đ": "d", "ß": "ss"})


def _fold_player(name: str) -> frozenset[str]:
    """A player name as an order-free bag of unaccented lowercase tokens.

    "Lodi, Renan" and "Renan Lodi" fold to the same set, which is the whole
    reason this is a set and not a string: Superbet writes surname-first with a
    comma, the dossier writes forename-first, and every other difference between
    them is punctuation.

    Accents are stripped because the two sources disagree about them constantly
    and never meaningfully -- Superbet writes "Vitao", "Preciado, Angelo" and
    "Perez, Tomas" where bzzoiro has "Vitão", "Ángelo Preciado", "Tomás Pérez".
    Keeping them cost eight of forty-nine joins on the first fixture measured.
    """
    folded = unicodedata.normalize("NFKD", name.translate(_LETTER_FOLD).lower())
    stripped = "".join(char for char in folded if not unicodedata.combining(char))
    cleaned = "".join(
        char if char.isalnum() or char.isspace() else " " for char in stripped
    )
    return frozenset(token for token in cleaned.split() if token)


def resolve_player_names(
    ours: Iterable[str],
    theirs: Iterable[str],
) -> dict[str, str]:
    """``{superbet_spelling: our_spelling}`` for pairs that are unambiguous.

    Three passes, each stricter than the one after it, and none overriding an
    earlier one:

    1. **Exact token-bag equality.** "Lodi, Renan" == "Renan Lodi". This covers
       almost everything and cannot be wrong.
    2. **Unique token containment.** "Tressoldi, Ruan" against a squad that
       lists only "Ruan". Exact tokens, not similarity, so it is stricter than
       the fuzzy pass and runs before it.
    3. **Fuzzy, above ``PLAYER_MATCH_THRESHOLD``, unique in both directions.**
       One of our players may claim one of theirs only if no other pairing on
       either side scores as well. A tie is dropped, not broken: on a squad with
       two brothers, or a Silva and a Silva Jr, the wrong pick is unrecoverable
       downstream and an absent price is not.

    A name claimed by an earlier pass leaves both pools before the next one
    runs, so a perfect match can never be stolen by a containment or fuzzy one.
    Measured on the first fixture with both sources in hand (Atletico Mineiro -
    Cruzeiro, 49 Superbet strings against two bzzoiro squads): pass 1 alone
    joined 31, all three join 46, and no two Superbet strings ever claimed the
    same player.
    """
    our_list = [name for name in ours if name and name.strip()]
    their_list = [name for name in theirs if name and name.strip()]
    resolved: dict[str, str] = {}
    if not our_list or not their_list:
        return resolved

    our_bags = {name: _fold_player(name) for name in our_list}
    their_bags = {name: _fold_player(name) for name in their_list}

    # Pass 1: exact token-bag equality, and only when the bag is unique on both
    # sides. Two of our players folding to the same bag is itself ambiguous.
    ours_by_bag: dict[frozenset[str], list[str]] = {}
    for name, bag in our_bags.items():
        ours_by_bag.setdefault(bag, []).append(name)
    theirs_by_bag: dict[frozenset[str], list[str]] = {}
    for name, bag in their_bags.items():
        theirs_by_bag.setdefault(bag, []).append(name)
    for bag, their_names in theirs_by_bag.items():
        our_names = ours_by_bag.get(bag) or []
        if len(their_names) == 1 and len(our_names) == 1:
            resolved[their_names[0]] = our_names[0]

    # Pass 2: one name's tokens are a subset of the other's, uniquely on both
    # sides. Superbet writes "Tressoldi, Ruan" where the squad has "Ruan", and
    # "Pereira, Matheus Felipe Costa" where it has "Matheus Pereira". This is
    # exact token containment, not similarity, so it is *safer* than the fuzzy
    # pass below and runs before it -- and the uniqueness rule is what stops a
    # bare "Silva" attaching itself to both Silvas in a squad.
    remaining_ours = [name for name in our_list if name not in set(resolved.values())]
    remaining_theirs = [name for name in their_list if name not in resolved]
    for their_name in list(remaining_theirs):
        their_bag = their_bags[their_name]
        if not their_bag:
            continue
        ours_fitting = [
            our_name
            for our_name in remaining_ours
            if our_bags[our_name]
            and (our_bags[our_name] <= their_bag or their_bag <= our_bags[our_name])
        ]
        if len(ours_fitting) != 1:
            continue
        our_name = ours_fitting[0]
        our_bag = our_bags[our_name]
        rivals = [
            other
            for other in remaining_theirs
            if other != their_name
            and their_bags[other]
            and (our_bag <= their_bags[other] or their_bags[other] <= our_bag)
        ]
        if rivals:
            continue
        resolved[their_name] = our_name
        remaining_ours.remove(our_name)
        remaining_theirs.remove(their_name)

    if not remaining_ours or not remaining_theirs:
        return resolved

    try:
        from rapidfuzz import fuzz
    except Exception:  # pragma: no cover - rapidfuzz is a hard dependency
        return resolved

    def score(a: str, b: str) -> float:
        return float(fuzz.token_sort_ratio(" ".join(sorted(_fold_player(a))),
                                           " ".join(sorted(_fold_player(b)))))

    for their_name in remaining_theirs:
        scored = sorted(
            ((score(their_name, our_name), our_name) for our_name in remaining_ours),
            key=lambda pair: (-pair[0], pair[1]),
        )
        if not scored or scored[0][0] < PLAYER_MATCH_THRESHOLD:
            continue
        # Ambiguous on our side: two of our players fit theirs equally well.
        if len(scored) > 1 and scored[1][0] >= scored[0][0]:
            continue
        best_ours = scored[0][1]
        # Ambiguous on their side: another of their strings fits our player at
        # least as well, so claiming this one is a coin toss.
        rival = max(
            (
                score(other, best_ours)
                for other in remaining_theirs
                if other != their_name
            ),
            default=0.0,
        )
        if rival >= scored[0][0]:
            continue
        resolved[their_name] = best_ours
    return resolved


@dataclass(frozen=True)
class OfferedLines:
    """Which lines the book posts, per (event, market, side, player).

    Empty is a valid instance and means "no offer was loaded" — every lookup
    returns ``None`` and every caller falls back to its static grid. That is the
    same sheet the pipeline produced before this existed, which is what makes
    the SUPERBET step safe to skip.
    """

    by_key: Mapping[_OfferedKey, tuple[float, ...]] = field(default_factory=dict)
    # Superbet player strings this run could not join to one of our players.
    # Reported, never guessed at: an unresolved prop is a coverage gap with a
    # name, not a row to fill in from the nearest candidate.
    unresolved_players: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.by_key)

    @classmethod
    def from_offer(
        cls,
        offer: SuperbetOfferV1 | None,
        *,
        player_names_by_event: Mapping[str, Sequence[str]] | None = None,
    ) -> OfferedLines:
        """Build the index from a SUPERBET artifact.

        ``player_names_by_event`` carries our spelling of each fixture's players,
        which the dossier knows and the offer does not. Without it, player lines
        are indexed under Superbet's own spelling, which nothing will ever match
        — so they are dropped instead, and counted.
        """
        if offer is None:
            return cls()
        names_by_event = player_names_by_event or {}
        grouped: dict[_OfferedKey, set[float]] = {}
        unresolved: set[str] = set()
        for event in offer.events:
            if not event.event_id:
                continue
            their_players = {
                line.player_name for line in event.lines if line.player_name
            }
            mapping = resolve_player_names(
                names_by_event.get(event.event_id, ()), their_players
            )
            unresolved.update(their_players - set(mapping))
            for line in event.lines:
                player = None
                if line.player_name:
                    player = mapping.get(line.player_name)
                    if player is None:
                        continue
                key = (event.event_id, line.market, line.team_name, player)
                grouped.setdefault(key, set()).add(float(line.line))
        return cls(
            by_key={key: tuple(sorted(values)) for key, values in grouped.items()},
            unresolved_players=tuple(sorted(unresolved)),
        )

    def lines_for(
        self,
        *,
        event_id: str,
        market: str,
        team_name: str | None = None,
        player_name: str | None = None,
    ) -> tuple[float, ...] | None:
        """The offered lines for one sample, or None to use the static grid.

        ``None`` and ``()`` are different answers and both are possible: None is
        "the book was not read for this", and an empty tuple cannot occur because
        a key only exists once a line has been filed under it.
        """
        return self.by_key.get((event_id, market, team_name, player_name))


def select_lines(
    lines: Sequence[float],
    *,
    median: float,
    limit: int | None = None,
) -> list[float]:
    """The ``limit`` lines closest to the sample's own median, ascending.

    Closeness to the median rather than to the book's favourite: the sheet's
    only claim is about this sample, and a line four goals clear of everything
    the sample ever produced yields 22/22 and a ``p_low`` that means nothing.
    Ties break on the lower line, so the choice is deterministic across runs.
    """
    ordered = sorted(float(line) for line in lines)
    if limit is None or len(ordered) <= limit:
        return ordered
    nearest = sorted(ordered, key=lambda line: (abs(line - median), line))[:limit]
    return sorted(nearest)
