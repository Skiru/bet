"""SUPERBET: what the operator's own book offers, and how our sheet compares.

The question this stage answers
-------------------------------
``market_context`` answers "what does the market think". This answers a
different and, as it turned out, more consequential question: **can the
operator actually take this bet, and at what price**.

They are not the same question because Superbet is not in bzzoiro's grid of
~88 bookmakers, and because a bookmaker's ladder of offered lines is its own
product decision. A row can be perfectly well evidenced, agree with the market
consensus, and still be unbettable because the line does not exist on the
screen.

Measured once, on the 2026-08-31 night slate, before this stage existed:

===========================================  =========================
Our line                                     Superbet's ladder
===========================================  =========================
``shots_on_target_total`` 4.5                starts at 7.5
``shots_total`` 19.5                         starts at 24.5
``offsides_total`` 1.5                       starts at 2.5
tennis ``total_sets`` 2.5 (best-of-three)    3.5 / 4.5 for every ATP slam tie
tennis ``total_games`` 19.5-23.5             24.5-46.5 for the same ties
===========================================  =========================

Eight of fifteen singles on that coupon were unbettable for this reason, and
nothing upstream could see it. ``LINE_NOT_OFFERED`` and the ``line_coverage``
block exist to make it the first thing anybody reads.

Three traps in the Polish market names
--------------------------------------
The mapping from Superbet's prose to a market code is the part most likely to
be wrong, so the wrong answers are enumerated rather than left to a fuzzy
match:

1. **"Liczba strzałów w obramowanie bramki" is not shots on target.**
   *Obramowanie bramki* is the woodwork -- the frame. A substring matcher that
   sees "strzałów" and "bramki" maps it to ``shots_on_target`` and then reports
   Remo over 1.5 shots on target at **10.00**, which is a shots-on-woodwork
   price wearing a shots-on-target label. This one shipped in the first draft
   and is the reason ``BANNED_SUBSTRINGS`` exists at all.
2. **Combination markets read exactly like simple ones.** "Powyżej 2.5 gola w
   meczu; Powyżej 27.5 strzałów w meczu" contains both a goals phrase and a
   shots phrase. Any name containing ``;`` is a parlay Superbet has pre-priced
   and is never a single outcome.
3. **Period markets are prefixed, not suffixed.** "1. połowa - liczba goli" is
   a first-half market and must not answer a full-match query, so mapping is by
   *exact* normalised name against a closed table, never by substring.

Kickoff times, and why tennis gets a wide tolerance
---------------------------------------------------
Superbet publishes tennis start times as court-order estimates. On the slate
above, Dimitrov-Popyrin was ours at 20:40 and Superbet's at 22:25 -- one hour
forty-five apart, same match. A football fixture drifting that far is a
different fixture; a tennis fixture drifting that far is Tuesday. Hence
``KICKOFF_TOLERANCE_MINUTES`` per sport, and hence ``kickoff_delta_minutes``
recorded on every match so the tolerance can be audited rather than trusted.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from statistics import NormalDist
from typing import Any

from bet.discovery.team_aliases import resolve_team_alias
from bet.simple_stats.bet_builder_draft import TIER_MARGIN, tier_for_row, required_odds
from bet.simple_stats.contracts import (
    EventListV1,
    EventRecord,
    StatsSheetRow,
    StatsSheetV1,
    SuperbetColumn,
    SuperbetBoardEvent,
    SuperbetComparisonRow,
    SuperbetComparisonV1,
    SuperbetEventOffer,
    SuperbetLine,
    SuperbetOfferV1,
    SuperbetResultLine,
)
from bet.simple_stats.offered_lines import resolve_player_names
from bet.utils import normalize_team_name

# Same constants the coupon uses. Imported rather than restated so a threshold
# can never drift between the two files: a Superbet verdict that disagrees with
# the coupon's own min_acceptable_odds is worse than no verdict.
# Re-exported, never redefined. The margins are one policy and they were
# written out in six places -- twice as a named constant and three times as an
# inline literal inside coupons.py alone -- so a change to CALL's 1.05 would
# have left the coupon file internally inconsistent: the price reported on a
# single, the price its VALUE verdict was decided against, and the price its
# ranking probe used all came from different copies. All six were identical
# when this was collapsed; that is luck, not a guarantee.
TIER_MARGINS = TIER_MARGIN
UNBETTABLE_TIERS = frozenset({"WEAK", "DROP"})

# Football fixtures are scheduled to the minute; tennis is scheduled by court
# order and its published time is an estimate. See the module docstring.
KICKOFF_TOLERANCE_MINUTES = {"football": 45.0, "tennis": 240.0}

# Player-scope markets. These are now **read**, which they were not before
# 2026-09-01: the original note here said joining Superbet's player strings to
# our ids "would be a guess rather than a lookup", and on the first live run
# these were 7,891 of 12,193 supposedly-missing markets. That was true of a
# day-wide join and false of a per-fixture one -- inside a matched event the
# candidate set is one squad, and the join refuses rather than guesses when two
# names fit (``offered_lines.resolve_player_names``).
#
# The measured cost of not reading them: 20,852 of the 30,054 rows on the
# 2026-08-31 sheet were player props, and every one carried
# ``SCOPE_NOT_SUPPORTED`` -- 69% of the sheet could not reach a coupon at any
# price. The set is kept as the list of markets whose lines are player-scoped,
# because ``lookup_line`` still has to key them differently.
PLAYER_SCOPE_MARKETS = frozenset({
    "player_total_shots",
    "player_shots_on_target",
    "player_fouls",
    "player_was_fouled",
    "player_cards",
    "player_tackles",
    "player_assists",
    "player_offsides",
})

# --- market-name mapping ---------------------------------------------------
#
# Closed tables, matched on the *exact* normalised name. Substring matching was
# tried and produced the woodwork bug in the module docstring; nothing here
# falls back to it.

MATCH_MARKET_NAMES: dict[str, str] = {
    # football, match totals
    "liczba goli": "goals_total",
    "liczba rzutow roznych": "corners_total",
    # Booking points, not yellows. Superbet settles this market with a
    # straight red as 2 and a second-yellow dismissal as 3, and our
    # ``cards_total`` is every provider's ``yellow_cards`` -- so pointing this
    # name at it priced a smaller quantity than the one that pays. Found
    # 2026-09-03 on Grêmio-Internacional, where the last three meetings read
    # 7/7/4 in yellows and 10/9/4 in the quantity this market settles.
    # ``cards_total`` is still collected and still has no market name.
    "liczba kartek": "cards_points_total",
    "liczba celnych strzalow": "shots_on_target_total",
    "liczba strzalow": "shots_total",
    "liczba spalonych": "offsides_total",
    "liczba fauli": "fouls_total",
    "liczba czerwonych kartek": "red_cards_total",
    "1.polowa - liczba goli": "goals_1h_total",
    "1. polowa - liczba goli": "goals_1h_total",
    "2.polowa - liczba goli": "goals_2h_total",
    "2. polowa - liczba goli": "goals_2h_total",
    # tennis, match totals
    "liczba asow": "aces_total",
    "liczba podwojnych bledow": "double_faults_total",
    "liczba gemow": "total_games",
    "liczba setow": "total_sets",
}

# Player-scope markets, matched on the *exact* normalised name for the same
# reason the match table is exact: Superbet ships five sub-population variants
# of every shot market ("... glowa", "... lewa noga", "... spoza pola karnego")
# and bzzoiro does not split a player's shots by body part, so a substring rule
# would price a header prop off a total-shots sample. They are absent from this
# table and stay banned.
#
# "liczba odbiorow na zawodniku" is deliberately **not** here: it is 212
# outcomes on a big fixture and it is not clear whether it settles on
# ``challenge_lost``, ``total_contest`` or something else. One settled fixture
# would decide it; until then it is an unmapped market, which is a diagnostic,
# rather than a wrong one, which is a bet.
PLAYER_MARKET_NAMES: dict[str, str] = {
    "zawodnik - liczba strzalow": "player_total_shots",
    "zawodnik - liczba celnych strzalow": "player_shots_on_target",
    "zawodnik - liczba popelnionych fauli": "player_fouls",
    "zawodnik - liczba fauli na zawodniku": "player_was_fouled",
    "zawodnik - liczba odbiorow": "player_tackles",
    "zawodnik - liczba asyst": "player_assists",
    "zawodnik - liczba spalonych": "player_offsides",
}

# Player markets Superbet writes as a yes/no rather than an over/under: the
# outcome name is the player and nothing else. They are the same bet as an
# "over 0.5" and are normalised to one so the sheet has a single shape.
# "otrzyma czerwona kartke" is not here -- a straight red is rare enough that a
# ten-match sample is almost always 0/10, and a p_low off that is noise wearing
# a number.
PLAYER_YES_NO_MARKETS: dict[str, tuple[str, float]] = {
    "zawodnik - otrzyma kartke": ("player_cards", 0.5),
}

# Team-scope markets. Each entry is (regex over the normalised name, market),
# with the team name captured as group "team". Superbet is not consistent about
# whether the club goes before or after the phrase, so both shapes are listed
# explicitly rather than guessed at.
TEAM_MARKET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(?P<team>.+?) - liczba rzutow roznych$"), "corners_for"),
    (re.compile(r"^(?P<team>.+?) - liczba kartek$"), "cards_points_for"),
    (re.compile(r"^(?P<team>.+?) - liczba goli$"), "goals_for"),
    (re.compile(r"^liczba celnych strzalow - (?P<team>.+?)$"), "shots_on_target_for"),
    (re.compile(r"^liczba strzalow (?P<team>.+?)$"), "shots_for"),
    (re.compile(r"^liczba fauli - (?P<team>.+?)$"), "fouls_for"),
    (re.compile(r"^spalone - (?P<team>.+?)$"), "offsides_for"),
    # Superbet writes this one with no separator at all -- "Liczba czerwonych
    # kartek West Ham" -- which is a fourth shape on top of the three above.
    # It was the only genuinely mapped market missing from a live 4,172-outcome
    # fixture on 2026-09-01, and it must be matched *before* "liczba kartek"
    # would be, or a red-card line gets filed as a booking line.
    (re.compile(r"^liczba czerwonych kartek (?P<team>.+?)$"), "red_cards_for"),
    # Tennis, where "per team" is "per player" -- the same mechanism, told
    # apart by ``team_name``, and the same three canonical metrics ANALYZE
    # already emits per side (``_TEAM_MARKET_STAT_TO_CANONICAL``).
    #
    # Superbet writes these with the player's name and no separator: "Alex
    # Michelsen liczba asow". Twenty of them went unmapped on 2026-09-02 across
    # a slate whose *one* genuinely-priced row was a tennis ``aces_total``, so
    # this is the second and less-glued view of exactly the market that
    # survived the analyst -- per-player aces measured on that player's own
    # serve rather than on both players summed.
    #
    # These sit after every football pattern and match a whole name against a
    # phrase no football market uses, so they cannot capture a club. The
    # combined "liczba asow + podwojnych bledow" is deliberately absent: there
    # is no canonical metric that adds the two, and inventing one here would
    # price a market nothing measured.
    (re.compile(r"^(?P<team>.+?) liczba asow$"), "aces_for"),
    (re.compile(r"^(?P<team>.+?) liczba podwojnych bledow$"), "double_faults_for"),
    (re.compile(r"^(?P<team>.+?) liczba gemow$"), "games_won"),
]

# --- the result family -----------------------------------------------------
#
# Markets this pipeline does not price and will not start pricing here, mapped
# so that "offered and not modelled" is a thing the artifact can say. Every name
# is verified against a live 4,279-outcome fixture (Raków-Górnik, eventId
# 13573272, fetched 2026-09-03).
#
# Exact-name matching, and for a sharper reason than the totals tables have. The
# outcome shape is not enough to identify these: on that same fixture
# "Najwięcej kartek" -- most *cards*, not the result -- is quoted as 1/X/2, and
# "Wynik dowolnej połowy meczu" is quoted with the two club names exactly as a
# half 1X2 is. A rule that read the outcomes and inferred the market would file
# both as a match result. That is the woodwork trap in the module docstring,
# one market family over.
#
# The halves are listed here even though ``BANNED_SUBSTRINGS`` catches
# "1.polowa -": like the two mapped half-goal totals, this table is consulted
# *before* the ban, and for the same reason. Slip 3 of the 2026-09-03 SUPERBETS
# board was two legs of "1.połowa - podwójna szansa" and nothing else.
RESULT_MARKET_NAMES: dict[str, str] = {
    "mecz": "1x2",
    "1.polowa - 1x2": "1x2_1h",
    "2.polowa - 1x2": "1x2_2h",
    "podwojna szansa": "double_chance",
    "1.polowa - podwojna szansa": "double_chance_1h",
    "2.polowa - podwojna szansa": "double_chance_2h",
    "obie druzyny strzela": "btts",
    "1.polowa - obie druzyny strzela": "btts_1h",
    "2.polowa - obie druzyny strzela": "btts_2h",
    "zaklad bez remisu": "draw_no_bet",
    "1.polowa - zaklad bez remisu": "draw_no_bet_1h",
    "2.polowa - zaklad bez remisu": "draw_no_bet_2h",
}

# The outcome vocabularies, folded. Superbet writes the same three results four
# ways depending on the market, so the spelling is normalised once here rather
# than compared downstream.
RESULT_OUTCOME_CODES: dict[str, str] = {
    "1": "HOME",
    "x": "DRAW",
    "2": "AWAY",
    "remis": "DRAW",
    "1x": "1X",
    "x2": "X2",
    "12": "12",
    "tak": "YES",
    "nie": "NO",
}


# A name containing any of these is never a plain match or team total, whatever
# else it looks like. Each entry earned its place against live data.
BANNED_SUBSTRINGS: tuple[str, ...] = (
    # The woodwork. Not shots on target. See the module docstring.
    "obramowanie bramki",
    # Goalkeeper saves.
    "obronionych strzalow",
    # Shots from outside the box, headers, left/right foot: sub-populations.
    "spoza pola karnego",
    "glowa",
    "lewa noga",
    "prawa noga",
    # Free-text player markets ("Carrillo, Guido powyzej 0.5 celnych strzalow").
    # Matching "Surname, Forename" to our player ids would be a guess.
    "zawodnik",
    "ktorykolwiek",
    "kazda z druzyn",
    "kazdy bramkarz",
    "kazdy z bramkarzy",
    "najwiecej",
    # Aggregations and shapes that are not an over/under on a count.
    "przedzial",
    "dokladn",
    "nieparzyst",
    "handicap",
    "h2h",
    "od 0:00",
    "od 1:00",
    "od 10:00",
    "do x minuty",
    "1. gol",
    "1. faul",
    "1. strzal",
    "1. celny strzal",
    "1. spalony",
    "ostatni",
    "kto wykona",
    # Per-set tennis scope.
    "1. set",
    "2. set",
    "3. set",
    "x. set",
    # Per-half football scope, except the two whole-half goal totals that are
    # mapped explicitly above and checked before this list is consulted.
    "1. polowa -",
    "1.polowa -",
    "2. polowa -",
    "2.polowa -",
    "1.polowa-",
    "polowa/mecz",
    "polowa liczba",
    "polowa lub",
)

# Superbet writes "powyżej 8.5" / "poniżej 8.5". Both spellings of ż survive
# the ascii fold as "z", so the pattern matches the folded form.
_OUTCOME_RE = re.compile(r"^(?P<side>ponizej|powyzej)\s+(?P<line>\d+(?:[.,]\d+)?)\b")


# NFKD decomposes ż, ó, ć and friends into a base letter plus a combining
# mark, which the ascii fold then drops cleanly. It does **not** decompose
# ł/Ł -- that is a distinct letter, not an l with an accent -- so the ascii
# fold deletes it outright and "strzałów" becomes "strzaow". Every Polish
# market name in this module contains at least one ł, so without this table the
# entire mapping silently matches nothing. Ą/ę are listed for completeness even
# though NFKD handles them, so the table reads as "the Polish alphabet" rather
# than "the two that happened to break".
_POLISH_FOLD = str.maketrans({
    "ł": "l", "Ł": "l",
    "ą": "a", "Ą": "a",
    "ć": "c", "Ć": "c",
    "ę": "e", "Ę": "e",
    "ń": "n", "Ń": "n",
    "ó": "o", "Ó": "o",
    "ś": "s", "Ś": "s",
    "ź": "z", "Ź": "z",
    "ż": "z", "Ż": "z",
})


def fold(text: str | None) -> str:
    """Lowercase, strip diacritics, squeeze whitespace. Nothing else.

    Deliberately not ``normalize_team_name``: that one strips club-form words
    like ``CA`` and ``SC``, which is right for matching *clubs* and destructive
    for matching *market names* -- "Liczba celnych strzałów - CA Platense"
    would lose the club it names.
    """
    if not text:
        return ""
    folded = text.translate(_POLISH_FOLD)
    folded = unicodedata.normalize("NFKD", folded)
    folded = folded.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", folded).strip().lower()


def is_banned_market(folded_name: str) -> bool:
    return ";" in folded_name or any(bad in folded_name for bad in BANNED_SUBSTRINGS)


# Words that make a market name worth reporting as unparsed. ``liczba`` alone
# was the whole test until 2026-09-05, which misses the markets that name the
# thing counted without ever saying "liczba". Kept a closed vocabulary rather
# than "report everything": a big fixture carries ~900 exotic outcomes and a
# diagnostic nobody can read is the same as no diagnostic.
#
# Only the market *name* is consulted, never the outcome text. "powyzej" would
# make the test vacuous -- it appears on every total ever posted -- and a
# diagnostic that fires on everything names nothing.
#
# Note what is deliberately *not* reachable here: ``is_banned_market`` runs
# first, and ``BANNED_SUBSTRINGS`` refuses "kazda z druzyn", "najwiecej",
# "handicap" and "h2h" on purpose. Those families are declined, not missed, and
# listing them as unparsed would report a decision as a failure. Reporting
# declined families is a separate job with a separate name; see
# ``derived_markets.py``, which already prices three of them.
_TOTAL_ISH_WORDS = (
    "liczba", "rozn", "strzal", "kartek", "fauli", "spalonych", "goli",
)


def _record_unmapped(
    unmapped: dict[str, None], raw: dict, team_names: Iterable[str] = ()
) -> None:
    """Note a market this parser could not read, if it looks like a total.

    Keyed on the market name, so one fixture's twenty rungs collapse to one
    entry, and with either side's club name replaced by ``{team}`` so the two
    per-team renderings of one family collapse to one entry as well.

    That last step is what keeps the diagnostic legible. Measured on the seven
    fixture screens captured 2026-09-05, this branch surfaces 118 market names
    of which 92 -- 78% -- are the same six families written once per club
    ("Antwerp wygra lub poniżej X goli", then Standard Liège, then the other
    twelve clubs of the day). Across a 184-event slate that is some eight
    hundred entries saying twenty-six things.
    """
    name = raw.get("marketName") or ""
    folded = fold(name)
    if not folded or is_banned_market(folded):
        return
    if not any(word in folded for word in _TOTAL_ISH_WORDS):
        return
    # Longest first: a club whose name contains another's must not leave the
    # shorter one behind ("Manchester United" before "Manchester City").
    for team in sorted((t for t in team_names if t), key=len, reverse=True):
        if team in name:
            name = name.replace(team, "{team}")
            break
    unmapped.setdefault(name, None)


def parse_outcome(name: str | None) -> tuple[str, float] | None:
    """``"powyżej 8.5"`` -> ``("OVER", 8.5)``. None for anything else."""
    match = _OUTCOME_RE.match(fold(name))
    if not match:
        return None
    direction = "UNDER" if match.group("side") == "ponizej" else "OVER"
    return (direction, float(match.group("line").replace(",", ".")))


def classify_market(market_name: str | None) -> tuple[str, str | None] | None:
    """``"Remo - liczba kartek"`` -> ``("cards_for", "Remo")``.

    Returns ``(market_code, team_name_or_None)``, or None when this is not a
    market this pipeline prices. The explicit map is consulted *before* the
    banned list so the two mapped half-goal markets survive the "1. polowa -"
    ban that exists for every other period market.
    """
    folded = fold(market_name)
    if not folded:
        return None
    mapped = MATCH_MARKET_NAMES.get(folded)
    if mapped is not None:
        return (mapped, None)
    if is_banned_market(folded):
        return None
    for pattern, market in TEAM_MARKET_PATTERNS:
        found = pattern.match(folded)
        if found:
            team = (found.group("team") or "").strip()
            if not team:
                return None
            return (market, team)
    return None


def classify_player_market(market_name: str | None) -> tuple[str, float | None] | None:
    """``"Zawodnik - liczba odbiorów"`` -> ``("player_tackles", None)``.

    The second element is a line Superbet does not write into the outcome: it is
    ``0.5`` for the yes/no markets and None for the over/under ones, where the
    line comes from the outcome string instead. Consulted before the banned list,
    like the match table, because every one of these names contains "zawodnik".
    """
    folded = fold(market_name)
    if not folded:
        return None
    mapped = PLAYER_MARKET_NAMES.get(folded)
    if mapped is not None:
        return (mapped, None)
    yes_no = PLAYER_YES_NO_MARKETS.get(folded)
    if yes_no is not None:
        return yes_no
    return None


def parse_player_outcome(
    name: str | None, *, forced_line: float | None = None
) -> tuple[str, str, float] | None:
    """``"Lodi, Renan - powyżej 0.5"`` -> ``("Lodi, Renan", "OVER", 0.5)``.

    Split on the **last** ``" - "``, not the first: Superbet writes surnames
    with commas and occasionally with hyphens ("Alves - Santos, Joao"), and the
    over/under clause is always the tail. The head is returned verbatim, in
    Superbet's own spelling -- resolving it to one of our players is
    ``offered_lines``' job and needs the whole squad to do safely.

    With ``forced_line`` set, the entire name is the player and the market is a
    yes/no ("Zawodnik - otrzyma kartkę"), normalised to OVER at that line.
    """
    text = (name or "").strip()
    if not text:
        return None
    if forced_line is not None:
        # A yes/no outcome carrying an over/under clause would mean Superbet
        # changed the market's shape; refuse rather than mis-file it.
        if parse_outcome(text.rsplit(" - ", 1)[-1]) is not None:
            return None
        return (text, "OVER", float(forced_line))
    if " - " not in text:
        return None
    head, tail = text.rsplit(" - ", 1)
    outcome = parse_outcome(tail)
    if outcome is None or not head.strip():
        return None
    direction, line = outcome
    return (head.strip(), direction, line)


# --- normalisation ---------------------------------------------------------


def _parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def sport_of(raw_event: dict[str, Any]) -> str | None:
    from bet.api_clients.superbet import SPORT_BY_ID

    return SPORT_BY_ID.get(raw_event.get("sportId"))


def _team_resolver(ours: dict[str, str]):
    """Map Superbet's spelling of a club onto ours, or to None.

    Exact normalised match first. Then containment in **one** direction at a
    time, and only when exactly one of our two sides matches -- Superbet writes
    "Estudiantes La Plata" where DISCOVER has "Estudiantes", and
    "Deportes La Serena" where we have "La Serena", so a strict equality gate
    silently halved the per-team coverage on both of those fixtures.

    The uniqueness requirement is the safety rail: on a fixture between two
    sides that share a token -- an "Atletico" derby, a reserve tie -- a
    containment match is ambiguous, and a per-team line filed against the wrong
    side is worse than no per-team line at all.
    """

    def resolve(superbet_team: str) -> str | None:
        key = normalize_team_name(resolve_team_alias(superbet_team))
        if not key:
            return None
        if key in ours:
            return ours[key]
        hits = [value for candidate, value in ours.items()
                if candidate and (candidate in key or key in candidate)]
        if len(hits) == 1:
            return hits[0]
        # Last: the same tokens in a different order, and still only when it
        # is unique. Superbet writes Chinese names given-name-last -- it has
        # "Yunchaokete Bu" and "Yibing Wu" where the draw has "Bu Yunchaokete"
        # and "Wu Yibing" -- so neither string contains the other and the pass
        # above declines. A bag of tokens has no order to disagree about, and
        # two people in one fixture cannot share one bag without being the
        # same person, so this cannot file a line against the wrong side.
        # It took 6 of the 198 tennis per-player markets on 2026-09-02, and it
        # is the systematic 6: every name written in that order fails without
        # it.
        bag = frozenset(key.split())
        if bag:
            same = [
                value for candidate, value in ours.items()
                if frozenset(candidate.split()) == bag
            ]
            if len(same) == 1:
                return same[0]
        return None

    return resolve


def normalize_result_lines(
    raw_event: dict[str, Any],
    *,
    team_names: Iterable[str] = (),
) -> list[SuperbetResultLine]:
    """Every offered outcome in the result family on one Superbet event.

    Deliberately a second pass rather than a branch inside ``normalize_lines``.
    That function's whole contract is "every mapped over/under outcome", and
    everything it returns has a line and a direction; a 1X2 has neither, and
    widening ``SuperbetLine`` to hold one would put a market with no line into
    the same list every consumer already reads as priced totals.

    ``team_names`` are our spellings of the two sides, used only to read the
    half-1X2 and draw-no-bet outcomes -- Superbet writes those with the clubs'
    own names rather than 1/X/2. When neither side resolves, the outcome is
    skipped: an unattributable price is worse than a missing one, because the
    operator cannot tell which team he is being quoted.

    Best active price wins per (family, outcome), matching ``normalize_lines``:
    Superbet quotes the same result under several market groupings and the last
    one seen is an artefact of feed ordering.
    """
    ours = {
        normalize_team_name(resolve_team_alias(name)): name
        for name in team_names
        if name
    }
    resolve_team = _team_resolver(ours)
    home_name, away_name = (list(team_names) + ["", ""])[:2]
    best: dict[tuple[str, str], SuperbetResultLine] = {}

    for raw in raw_event.get("odds") or []:
        if not isinstance(raw, dict):
            continue
        family = RESULT_MARKET_NAMES.get(fold(raw.get("marketName")))
        if family is None:
            continue
        try:
            price = float(raw.get("price"))
        except (TypeError, ValueError):
            continue
        if price <= 1.0:
            continue

        folded_outcome = fold(raw.get("name"))
        outcome = RESULT_OUTCOME_CODES.get(folded_outcome)
        if outcome is None:
            # A half 1X2 and a draw-no-bet name the clubs instead of using
            # 1/X/2. Resolved through the same matcher the team totals use, so
            # a spelling this pipeline cannot place is dropped rather than
            # guessed at.
            resolved = resolve_team(raw.get("name") or "")
            if resolved and home_name and resolved == home_name:
                outcome = "HOME"
            elif resolved and away_name and resolved == away_name:
                outcome = "AWAY"
        if outcome is None:
            continue

        candidate = SuperbetResultLine(
            family=family,
            outcome=outcome,
            price=price,
            status=str(raw.get("status") or "active"),
            source_market_name=str(raw.get("marketName") or ""),
            source_outcome_name=str(raw.get("name") or ""),
        )
        slot = (family, outcome)
        current = best.get(slot)
        if current is None:
            best[slot] = candidate
        elif current.status != "active" and candidate.status == "active":
            best[slot] = candidate
        elif current.status == candidate.status and candidate.price > current.price:
            best[slot] = candidate

    return list(best.values())


def normalize_lines(
    raw_event: dict[str, Any],
    *,
    team_names: Iterable[str] = (),
) -> tuple[list[SuperbetLine], list[str]]:
    """Every mapped over/under outcome on one Superbet event.

    ``team_names`` are our spellings of the two sides. A team-scope market whose
    captured club matches neither is dropped rather than filed under Superbet's
    spelling: a ``cards_for`` row that names a team our sheet has never heard of
    can be joined to nothing and would only ever inflate the coverage counts.

    Best price wins per (market, line, direction, team). Superbet quotes the
    same outcome under several market groupings and taking the last one seen
    would make the result depend on feed ordering.
    """
    ours = {normalize_team_name(resolve_team_alias(name)): name for name in team_names if name}
    resolve_team = _team_resolver(ours)
    best: dict[tuple[str, float, str, str | None, str | None], SuperbetLine] = {}
    unmapped: dict[str, None] = {}
    # Superbet's *own* spellings, not ours: the market names being collapsed in
    # ``_record_unmapped`` are strings Superbet wrote, so "Antwerp" is what
    # appears in them and "Royal Antwerp FC" is what we call the same club.
    from bet.api_clients.superbet import split_match_name

    board_sides = split_match_name(raw_event.get("matchName"))

    def offer(
        *,
        market: str,
        line: float,
        direction: str,
        team_name: str | None,
        player_name: str | None,
        price: float,
        raw: dict[str, Any],
    ) -> None:
        slot = (market, line, direction, team_name, player_name)
        candidate = SuperbetLine(
            market=market,
            line=line,
            direction=direction,
            team_name=team_name,
            player_name=player_name,
            price=price,
            status=str(raw.get("status") or "active"),
            source_market_name=str(raw.get("marketName") or ""),
            source_outcome_name=str(raw.get("name") or ""),
        )
        current = best.get(slot)
        # An active quote always beats a blocked one, whatever the price says.
        if current is None:
            best[slot] = candidate
        elif current.status != "active" and candidate.status == "active":
            best[slot] = candidate
        elif current.status == candidate.status and candidate.price > current.price:
            best[slot] = candidate

    for raw in raw_event.get("odds") or []:
        if not isinstance(raw, dict):
            continue
        try:
            price = float(raw.get("price"))
        except (TypeError, ValueError):
            continue
        if price <= 1.0:
            # A price of 1.0 or below cannot be taken and is how Superbet
            # renders a shut market on lines like "poniżej 6.5 goli".
            continue

        # Player scope first: its outcome string carries the player *and* the
        # line ("Lodi, Renan - powyżej 0.5"), so ``parse_outcome`` alone -- which
        # anchors at the start of the string -- rejects every one of them.
        player_market = classify_player_market(raw.get("marketName"))
        if player_market is not None:
            market, forced_line = player_market
            parsed = parse_player_outcome(raw.get("name"), forced_line=forced_line)
            if parsed is None:
                continue
            player_text, direction, line = parsed
            offer(
                market=market, line=line, direction=direction,
                team_name=None, player_name=player_text, price=price, raw=raw,
            )
            continue

        outcome = parse_outcome(raw.get("name"))
        if outcome is None:
            # A market whose *name* reads as a total but whose outcome does not
            # -- "powyżej 8.5 - tak" is one shape no over/under regex matches.
            # Until 2026-09-05 this branch returned before the diagnostic below
            # could see the name, so such a market was missing from ``lines``
            # and from ``unmapped_markets`` alike: not declined, just gone.
            _record_unmapped(unmapped, raw, board_sides)
            continue
        classified = classify_market(raw.get("marketName"))
        if classified is None:
            _record_unmapped(unmapped, raw, board_sides)
            continue
        market, superbet_team = classified
        team_name: str | None = None
        if superbet_team is not None:
            team_name = resolve_team(superbet_team)
            if team_name is None:
                continue
        direction, line = outcome
        offer(
            market=market, line=line, direction=direction,
            team_name=team_name, player_name=None, price=price, raw=raw,
        )
    return (list(best.values()), sorted(unmapped))


# --- fixture matching ------------------------------------------------------


def _sides(event: EventRecord) -> tuple[str, str]:
    if event.sport == "tennis":
        return (event.player_one or "", event.player_two or "")
    return (event.home_team or "", event.away_team or "")


def _side_key(names: Iterable[str]) -> tuple[str, ...]:
    """Order-insensitive, alias-resolved identity of the two participants.

    Order-insensitive because Superbet's home/away can disagree with ours on a
    neutral-ground fixture, and because a tennis "home" side is an arbitrary
    draw position rather than a fact about the match.
    """
    return tuple(sorted(normalize_team_name(resolve_team_alias(name)) for name in names if name))


def _tokens(name: str) -> frozenset[str]:
    return frozenset(part for part in re.split(r"[^a-z0-9]+", name) if part)


def sides_compatible(ours: str, theirs: str) -> bool:
    """Are these two normalised names plausibly the same club or player?

    Equality first. Then containment, then a token overlap of at least half the
    shorter name. All three are needed because a book and a discovery feed
    disagree about club long-forms constantly, and the exact-equality gate on
    its own lost real fixtures on the first live run:

    * "Estudiantes" vs "Estudiantes La Plata"   (containment)
    * "La Serena" vs "Deportes La Serena"       (containment)
    * "FC Copenhagen" vs "FC Kobenhavn"         (neither -- still misses, and
      that is correct: this function must not start guessing at translations)

    A single-token name is required to match exactly or by containment, never
    by overlap: "Inter" would otherwise pair with "Inter Turku" *and* "Inter
    Miami", and a fixture matched to the wrong club prices the wrong match.
    """
    if not ours or not theirs:
        return False
    if ours == theirs:
        return True
    if ours in theirs or theirs in ours:
        return True
    left, right = _tokens(ours), _tokens(theirs)
    if not left or not right:
        return False
    if min(len(left), len(right)) < 2:
        return False
    shared = len(left & right)
    return shared * 2 >= min(len(left), len(right)) * 2 and shared >= 2


def _minutes_between(ours: str, theirs: datetime | None) -> float:
    """Kickoff gap with no tolerance gate. For a pass that already has an id.

    Reported rather than judged: on an id match the delta is a *diagnostic*
    about the two feeds' clocks, not a reason to reject the pairing, and a
    fixture Superbet publishes three hours off is exactly the case the id pass
    was added to keep.
    """
    mine = _parse_kickoff(ours)
    if mine is None or theirs is None:
        return 0.0
    return abs((theirs - mine).total_seconds()) / 60.0


def _kickoff_ok(sport: str, ours: str, theirs: datetime | None) -> float | None:
    """Minutes apart, or None when the two clocks are too far to be one match."""
    mine = _parse_kickoff(ours)
    if theirs is None or mine is None:
        return 0.0
    delta = abs((theirs - mine).total_seconds()) / 60.0
    tolerance = KICKOFF_TOLERANCE_MINUTES.get(sport, 45.0)
    return delta if delta <= tolerance else None


def match_offer_events(
    event_list: EventListV1,
    raw_events: Iterable[dict[str, Any]],
    *,
    betradar_by_event_id: Mapping[str, str] | None = None,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Join Superbet's fixtures to ours.

    Returns ``(by_event_id, unmatched_superbet_rows, our_event_ids_without_offer)``.

    Three passes. The first is exact identity and is optional; the other two
    compare names, and the second of those exists because the first is not
    enough.

    **Pass zero** consumes ``betradar_by_event_id`` -- our event id to the
    Betradar fixture id, built by ``superbet_identity`` from OddsPapi. Superbet
    publishes ``betradarId`` on every real event it lists, so this pass is an
    integer comparison and needs neither a name nor a clock. It runs first and
    what it claims is never revisited: an id match outranks any name match. On
    a real 179-fixture slate on 2026-09-01 it took the match count from 115 to
    123 and disagreed with the name matcher on none of the 115 both could
    name -- the eight it added were clubs the two feeds simply call different
    things ("U Cluj" / "Universitatea Cluj", "Amsterdamsche" / "Afc \'34").

    When the mapping is absent -- no OddsPapi key, no quota, provider down --
    this pass simply matches nothing and the two below behave exactly as they
    did before it existed.

    **Pass one** keys on the exact normalised, alias-resolved pair of
    participants plus a per-sport kickoff tolerance. Exact because two
    Argentine reserve sides can share a normalised name on the same night, and
    with a clock because a name alone is not a fixture.

    **Pass two** retries whatever is left with ``sides_compatible`` -- the
    tolerant comparison -- and accepts only where **exactly one** Superbet
    fixture is compatible with **exactly one** of ours. The first live run lost
    Estudiantes-Newell's and Union La Calera-La Serena to nothing more than
    "Estudiantes La Plata" and "Deportes La Serena", which is not a data
    problem worth losing a fixture over. The uniqueness requirement on both
    sides is what keeps that from becoming a guess.

    Where several Superbet rows match one event -- which happens, because the
    by-date feed carries the same tie under both a tournament and a "specials"
    grouping -- the closest kickoff wins, and ties break on market count so the
    richer offer is the one that is read.
    """
    from bet.api_clients.superbet import split_match_name

    exact_index: dict[tuple[str, tuple[str, ...]], list[EventRecord]] = {}
    for event in event_list.events:
        exact_index.setdefault((event.sport, _side_key(_sides(event))), []).append(event)

    # (raw, sport, normalised sides) for everything the feed offered in a sport
    # this pipeline reads. Computed once: pass two scans it per leftover event.
    offered: list[tuple[dict[str, Any], str, tuple[str, ...], datetime | None]] = []
    for raw in raw_events:
        sport = sport_of(raw)
        if sport is None:
            continue
        home, away = split_match_name(raw.get("matchName"))
        offered.append((raw, sport, _side_key((home, away)), _parse_kickoff(raw.get("utcDate"))))

    scored: dict[str, list[tuple[float, int, dict[str, Any]]]] = {}
    matched_by: dict[str, str] = {}
    consumed: set[int] = set()

    # --- pass zero: exact identity via Betradar ----------------------------
    # Indexed rather than scanned because the by-date feed carries ~3,200 rows
    # and this runs once per event. A Betradar id claimed by two Superbet rows
    # is not an identity, so it is dropped from the index rather than picked
    # between -- the name passes below will handle those events instead.
    if betradar_by_event_id:
        by_betradar: dict[str, int] = {}
        duplicated: set[str] = set()
        for index, (raw, _sport, _key, _kickoff) in enumerate(offered):
            key = str(raw.get("betradarId") or "").strip()
            if not key:
                continue
            if key in by_betradar:
                duplicated.add(key)
                continue
            by_betradar[key] = index
        for key in duplicated:
            by_betradar.pop(key, None)

        for event in event_list.events:
            betradar_id = str(betradar_by_event_id.get(event.event_id) or "").strip()
            if not betradar_id:
                continue
            index = by_betradar.get(betradar_id)
            if index is None or index in consumed:
                continue
            raw, sport, _key, kickoff = offered[index]
            if sport != event.sport:
                # The id says these are one fixture and the sports disagree.
                # That is a bug in one of the two feeds, not a match.
                continue
            consumed.add(index)
            delta = _minutes_between(event.start_time, kickoff)
            scored.setdefault(event.event_id, []).append(
                (delta, int(raw.get("marketCount") or 0), raw)
            )
            matched_by[event.event_id] = "betradar_id"

    # --- pass one: exact ---------------------------------------------------
    for index, (raw, sport, key, kickoff) in enumerate(offered):
        if index in consumed:
            continue
        candidates = exact_index.get((sport, key)) or []
        best: tuple[float, EventRecord] | None = None
        for event in candidates:
            if event.event_id in matched_by:
                continue
            delta = _kickoff_ok(sport, event.start_time, kickoff)
            if delta is None:
                continue
            if best is None or delta < best[0]:
                best = (delta, event)
        if best is None:
            continue
        consumed.add(index)
        scored.setdefault(best[1].event_id, []).append(
            (best[0], int(raw.get("marketCount") or 0), raw)
        )

    # --- pass two: tolerant, and only where it is unambiguous --------------
    leftovers = [
        (index, entry) for index, entry in enumerate(offered) if index not in consumed
    ]
    for event in event_list.events:
        if event.event_id in scored:
            continue
        mine = _side_key(_sides(event))
        if len(mine) != 2:
            continue
        hits: list[tuple[int, float, dict[str, Any]]] = []
        for index, (raw, sport, theirs, kickoff) in leftovers:
            if sport != event.sport or len(theirs) != 2:
                continue
            delta = _kickoff_ok(sport, event.start_time, kickoff)
            if delta is None:
                continue
            straight = (
                sides_compatible(mine[0], theirs[0]) and sides_compatible(mine[1], theirs[1])
            )
            crossed = (
                sides_compatible(mine[0], theirs[1]) and sides_compatible(mine[1], theirs[0])
            )
            if straight or crossed:
                hits.append((index, delta, raw))
        if len(hits) != 1:
            continue
        index, delta, raw = hits[0]
        # And the reverse check: this Superbet fixture must not be compatible
        # with any *other* event of ours, or the pairing is a coin flip.
        rivals = 0
        for other in event_list.events:
            if other.sport != event.sport:
                continue
            theirs = offered[index][2]
            candidate = _side_key(_sides(other))
            if len(candidate) != 2:
                continue
            if _kickoff_ok(other.sport, other.start_time, offered[index][3]) is None:
                continue
            if (
                (sides_compatible(candidate[0], theirs[0]) and sides_compatible(candidate[1], theirs[1]))
                or (sides_compatible(candidate[0], theirs[1]) and sides_compatible(candidate[1], theirs[0]))
            ):
                rivals += 1
        if rivals != 1:
            continue
        consumed.add(index)
        scored.setdefault(event.event_id, []).append(
            (delta, int(raw.get("marketCount") or 0), raw)
        )

    by_event: dict[str, dict[str, Any]] = {}
    unmatched: list[dict[str, Any]] = []
    for event_id, rows in scored.items():
        rows.sort(key=lambda row: (row[0], -row[1]))
        by_event[event_id] = {
            "raw": rows[0][2],
            "delta_minutes": rows[0][0],
            "matched_by": matched_by.get(event_id, "name_and_kickoff"),
        }
        # Anything we did not choose is still a real Superbet fixture; report it
        # rather than dropping it, so a duplicate grouping is visible.
        unmatched.extend(row[2] for row in rows[1:])
    unmatched.extend(raw for index, (raw, _, _, _) in enumerate(offered) if index not in consumed)

    without_offer = [e.event_id for e in event_list.events if e.event_id not in by_event]
    return (by_event, unmatched, without_offer)


def build_event_offer(
    raw_event: dict[str, Any],
    *,
    event: EventRecord | None,
    delta_minutes: float | None,
    matched_by: str = "name_and_kickoff",
) -> SuperbetEventOffer:
    from bet.api_clients.superbet import split_match_name

    sport = sport_of(raw_event) or (event.sport if event else "football")
    team_names = _sides(event) if event is not None else split_match_name(raw_event.get("matchName"))
    lines, unmapped = normalize_lines(raw_event, team_names=team_names)
    result_lines = normalize_result_lines(raw_event, team_names=team_names)
    quality = "UNMATCHED"
    if event is not None:
        if matched_by == "betradar_id":
            # ID_MATCHED outranks both. The clock delta is still recorded --
            # a three-hour gap on an id match is a real fact about one of the
            # two feeds -- but it no longer downgrades the pairing, because the
            # pairing was never made on the clock.
            quality = "ID_MATCHED"
        else:
            # EXACT when the two clocks agree to the minute; FUZZY when the
            # fixture is the same but the published time is not, which is the
            # normal state for tennis and an anomaly worth seeing for football.
            quality = "EXACT" if (delta_minutes or 0.0) <= 1.0 else "FUZZY"
    return SuperbetEventOffer(
        superbet_event_id=str(raw_event.get("eventId") or raw_event.get("offerId") or ""),
        superbet_match_name=str(raw_event.get("matchName") or ""),
        sport=sport,
        kickoff=str(raw_event.get("utcDate") or ""),
        event_id=event.event_id if event is not None else None,
        match_quality=quality,  # type: ignore[arg-type]
        kickoff_delta_minutes=round(delta_minutes, 1) if delta_minutes is not None else None,
        market_count=int(raw_event.get("marketCount") or 0),
        status=(raw_event.get("metadata") or {}).get("status") if isinstance(raw_event.get("metadata"), dict) else None,
        lines=lines,
        unmapped_markets=unmapped,
        result_market_lines=result_lines,
    )


# --- comparison ------------------------------------------------------------


def min_acceptable_odds(
    row: StatsSheetRow,
    tier: str,
    *,
    basis: str = "p_low",
    market_probability: float | None = None,
) -> float | None:
    """1/p x tier margin, or None when the row is not bettable at all.

    Returns None rather than a very large number for ``p_low == 0``: a row that
    never hit has no minimum price, it has no bet, and printing 1/0 as "inf"
    invites somebody to compare a real price against it.

    ``market_probability`` is the book's own devigged number for this outcome
    and is passed by the comparison, which has the offer in hand. It must be:
    this function's whole contract is that it computes the number the coupon
    computes, and since 2026-09-03 that number depends on the market prior.
    Omitting it here would have made the comparison artifact report VALUE on
    rows the coupon then declined -- two thresholds, one of them printed for
    the operator.
    """
    if tier in UNBETTABLE_TIERS or row.p_low <= 0:
        return None
    return required_odds(
        row, tier, basis=basis, market_probability=market_probability
    )


def _nearest(
    ladder: list[SuperbetLine], line: float
) -> tuple[float | None, float | None]:
    if not ladder:
        return (None, None)
    closest = min(ladder, key=lambda candidate: (abs(candidate.line - line), candidate.line))
    return (closest.line, closest.price)


def compare_sheet_to_offer(
    stats_sheet: StatsSheetV1,
    offer: SuperbetOfferV1,
    event_list: EventListV1 | None = None,
    *,
    min_p_low: float = 0.0,
    generated_at: str | None = None,
    bar_basis: str = "p_central",
) -> SuperbetComparisonV1:
    """Judge every stats-sheet row against the operator's own book.

    Deliberately *aggressive*: it does not stop at the rows the coupon chose.
    Every row above ``min_p_low`` is compared, including per-team rows and
    lines the coupon's one-single-per-market rule would have collapsed away,
    because the question here is "what on this book is mispriced" and that is
    not the same set as "what would we print".

    Pure, and takes ``generated_at`` as an argument for the same reason
    ``build_coupons`` takes ``not_before``: an artifact that stamps itself from
    the clock cannot be diffed against a rerun.

    ``bar_basis`` defaults to ``p_central``, which is what ``build_coupons``
    ships with. It used to default to ``p_low`` here while the coupon used
    ``p_central``, so the two artifacts disagreed about what a row's minimum
    price was -- and this module's own contract is that they must not
    (``min_acceptable_odds``: "a threshold that disagrees with the coupon's is
    worse than no threshold"). Harmless while the difference was only
    conservatism; not harmless once the market prior went on top of it, which
    left this artifact demanding a p_low bar *and* a market prior and reporting
    1 VALUE against the coupon's 7.
    """
    events = {e.event_id: e for e in (event_list.events if event_list else [])}
    offers = {o.event_id: o for o in offer.events if o.event_id}
    our_players: dict[str, set[str]] = {}
    for sheet_row in stats_sheet.rows:
        if sheet_row.player_name:
            our_players.setdefault(sheet_row.event_id, set()).add(sheet_row.player_name)
    aliases = player_alias_index(offer, our_players)

    def identity(event_id: str) -> tuple[str, str]:
        event = events.get(event_id)
        if event is None:
            return (f"[nieznany mecz {event_id[:12]}]", "")
        if event.sport == "tennis":
            return (f"{event.player_one or '?'} – {event.player_two or '?'}", event.start_time)
        return (f"{event.home_team or '?'} – {event.away_team or '?'}", event.start_time)

    rows: list[SuperbetComparisonRow] = []
    counts: dict[str, int] = {}
    # market -> {"our_lines": set, "offered_lines": set, "matched": int}
    coverage: dict[str, dict[str, Any]] = {}

    def note(verdict: str) -> None:
        counts[verdict] = counts.get(verdict, 0) + 1

    considered = 0
    for row in stats_sheet.rows:
        if row.p_low < min_p_low:
            continue
        tier = tier_for_row(row)
        event_offer_for_bar = offers.get(row.event_id)
        implied = devigged_probability(
            event_offer_for_bar,
            market=row.market,
            line=row.line,
            direction=row.direction,
            team_name=row.team_name,
            player_name=row.player_name,
            player_aliases=aliases.get(row.event_id, {}),
        )
        minimum = min_acceptable_odds(
            row, tier, basis=bar_basis, market_probability=implied
        )
        if minimum is None:
            continue
        considered += 1
        match, kickoff = identity(row.event_id)
        event_offer = offers.get(row.event_id)
        cov_key = f"{row.sport}:{row.market}"
        cov = coverage.setdefault(
            cov_key, {"our_lines": set(), "offered_lines": set(), "matched": 0, "rows": 0}
        )
        cov["rows"] += 1
        cov["our_lines"].add(row.line)

        base = dict(
            event_id=row.event_id,
            match=match,
            kickoff=kickoff,
            sport=row.sport,
            market=row.market,
            line=row.line,
            direction=row.direction,
            team_name=row.team_name,
            player_name=row.player_name,
            player_id=row.player_id,
            p_low=row.p_low,
            hits=row.hits,
            sample_size=row.sample_size,
            median=row.median,
            tier=tier,
            min_acceptable_odds=minimum,
            superbet_implied_probability=(
                round(implied, 4) if implied is not None else None
            ),
        )

        availability, exact, near_line, near_price = lookup_line(
            event_offer,
            market=row.market,
            line=row.line,
            direction=row.direction,
            team_name=row.team_name,
            player_name=row.player_name,
            player_aliases=aliases.get(row.event_id, {}),
        )
        if event_offer is not None:
            their_player = aliases.get(row.event_id, {}).get(row.player_name or "")
            for line in event_offer.lines:
                if (
                    line.market == row.market
                    and line.direction == row.direction
                    and line.team_name == (None if row.player_name else row.team_name)
                    and line.player_name == their_player
                ):
                    cov["offered_lines"].add(line.line)

        if availability == "LINE_NOT_OFFERED":
            note("LINE_NOT_OFFERED")
            rows.append(
                SuperbetComparisonRow(
                    **base,
                    verdict="LINE_NOT_OFFERED",
                    nearest_offered_line=near_line,
                    nearest_offered_price=near_price,
                )
            )
            continue

        if availability != "OFFERED" and availability != "SUSPENDED":
            note(availability)
            rows.append(SuperbetComparisonRow(**base, verdict=availability))  # type: ignore[arg-type]
            continue

        cov["matched"] += 1
        assert exact is not None  # both remaining branches resolved a line
        if availability == "SUSPENDED":
            note("OUTCOME_SUSPENDED")
            rows.append(
                SuperbetComparisonRow(
                    **base,
                    verdict="OUTCOME_SUSPENDED",
                    superbet_price=exact.price,
                    superbet_status=exact.status,
                    superbet_market_name=exact.source_market_name,
                )
            )
            continue

        surplus = round(exact.price - minimum, 4)
        verdict = "VALUE" if exact.price >= minimum else "PRICED_BELOW_THRESHOLD"
        note(verdict)
        rows.append(
            SuperbetComparisonRow(
                **base,
                verdict=verdict,  # type: ignore[arg-type]
                superbet_price=exact.price,
                superbet_status=exact.status,
                superbet_market_name=exact.source_market_name,
                odds_surplus=surplus,
            )
        )

    # Value first and by size of surplus, then everything else by evidence.
    # An operator reading this file top-down should hit every bet before the
    # first non-bet, and the diagnostics should still be there underneath.
    rows.sort(
        key=lambda candidate: (
            0 if candidate.verdict == "VALUE" else 1,
            -(candidate.odds_surplus or 0.0) if candidate.verdict == "VALUE" else 0.0,
            -candidate.p_low,
            candidate.event_id,
            candidate.market,
        )
    )

    line_coverage = {
        key: {
            "rows": value["rows"],
            "matched_rows": value["matched"],
            "our_lines": sorted(value["our_lines"]),
            "offered_lines": sorted(value["offered_lines"]),
            # The headline: a market whose generated lines never appear on the
            # book is a line-generator defect, not a thin day.
            #
            # An *intersection* test, and it used to be ``matched == 0``. That
            # is a different question, and on 2026-09-02 the two gave different
            # answers: ``football:red_cards_total`` reported ``no_overlap``
            # while its own ``our_lines`` [0.5, 1.5] and ``offered_lines``
            # [0.5] plainly overlap. Nothing matched because the two rows at
            # 0.5 were on Japanese fixtures Superbet did not carry, and three
            # more asked for 1.5 UNDER on a rung the book quotes OVER-only.
            # Both are real findings and neither is a line generator that
            # cannot hit the ladder -- which is the one thing this field is
            # read as saying, and the thing an operator is told to report as a
            # defect.
            "no_overlap": (
                bool(value["offered_lines"])
                and not (value["our_lines"] & value["offered_lines"])
            ),
        }
        for key, value in sorted(coverage.items())
    }

    return SuperbetComparisonV1(
        run_id=offer.run_id,
        date=offer.date,
        generated_at=generated_at or datetime.now(UTC).isoformat(),
        rows_considered=considered,
        rows_compared=sum(
            count for verdict, count in counts.items()
            if verdict in ("VALUE", "PRICED_BELOW_THRESHOLD", "OUTCOME_SUSPENDED")
        ),
        verdict_counts=dict(sorted(counts.items())),
        line_coverage=line_coverage,
        rows=rows,
    )


def summarize_offer(offer: SuperbetOfferV1) -> dict[str, Any]:
    """AGENT_SUMMARY metrics for the SUPERBET step."""
    lines = sum(len(event.lines) for event in offer.events)
    unmapped: set[str] = set()
    # Counted per fixture, not per outcome: "on how many of today's fixtures is
    # the market the operator actually bets on being offered and not priced by
    # us" is the number that answers the question, and it is 1 per fixture
    # rather than the ~30 outcomes the family spans.
    result_family_events = 0
    result_family_lines = 0
    result_families: set[str] = set()
    for event in offer.events:
        unmapped.update(event.unmapped_markets)
        if event.result_market_lines:
            result_family_events += 1
            result_family_lines += len(event.result_market_lines)
            result_families.update(line.family for line in event.result_market_lines)
    fuzzy = [e for e in offer.events if e.match_quality == "FUZZY"]
    return {
        "events_on_offer": offer.events_on_offer,
        "events_matched": offer.events_matched,
        "events_unmatched": offer.events_unmatched,
        "our_events_without_offer": len(offer.our_events_without_offer),
        "our_events_kicked_off": len(offer.our_events_kicked_off),
        "events_capped": offer.events_capped,
        "fuzzy_kickoff_matches": len(fuzzy),
        "max_kickoff_delta_minutes": max(
            (e.kickoff_delta_minutes or 0.0 for e in offer.events), default=0.0
        ),
        "priced_lines": lines,
        "unmapped_market_names": sorted(unmapped)[:20],
        # Offered, understood, deliberately unpriced. Reported next to
        # ``priced_lines`` so a day whose sheet has no VALUE rows cannot be
        # read as a day with nothing on it: on 2026-09-03 every leg of the
        # SUPERBETS board that was not a total lived here and was invisible.
        "result_family_events": result_family_events,
        "result_family_lines": result_family_lines,
        "result_families": sorted(result_families),
        "requests_made": offer.requests_made,
    }


def default_window(date: str) -> tuple[datetime, datetime]:
    """The UTC day, plus six hours into the next one.

    South-American football and the US Open night session both run past
    midnight UTC on the betting day they belong to; a window that stops at
    00:00 loses the part of the slate that is still bettable when the operator
    reads the file.
    """
    start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    return (start, start + timedelta(days=1, hours=6))


def collect_superbet_offer(
    event_list: EventListV1,
    *,
    client: Any | None = None,
    max_events: int | None = None,
    window: tuple[datetime, datetime] | None = None,
    generated_at: str | None = None,
    now: datetime | None = None,
    identity_bridge: Any | None = None,
) -> SuperbetOfferV1:
    """Read the book for one betting day and join it to our fixtures.

    Cost model: **one call for the whole day plus one per matched fixture.**
    There is no bulk odds endpoint -- ``by-date`` returns fixtures with
    ``odds: null`` -- so a 40-fixture slate is 41 requests. That is cheap and
    unmetered, but it is not free, hence ``max_events``.

    Only *matched* fixtures are fetched. Superbet's night window carries ~850
    events, the overwhelming majority of them esports and simulated football,
    and fetching odds for a fixture our sheet has no row about would spend a
    request to learn nothing.

    ``identity_bridge`` is an optional ``superbet_identity.IdentityBridge``. It
    only ever *adds* matches -- passing None, or a bridge that found nothing,
    leaves this function's behaviour exactly as it was before the bridge
    existed. Its own cost and notes travel on the artifact rather than in
    ``data_gaps``, because a bridge that could not run is not a degraded day.
    """
    from bet.api_clients.superbet import SuperbetClient

    api = client or SuperbetClient()
    start, end = window or default_window(event_list.date)
    fetched_at = now or datetime.now(UTC)
    gaps: list[str] = []

    try:
        raw_events = api.events_by_date(start, end)
    except Exception as exc:  # noqa: BLE001 - a dead offer host is a data gap
        return SuperbetOfferV1(
            run_id=event_list.run_id,
            date=event_list.date,
            generated_at=generated_at or datetime.now(UTC).isoformat(),
            window_start=start.isoformat(),
            window_end=end.isoformat(),
            requests_made=getattr(api, "request_count", 0),
            data_gaps=[f"by-date: {exc}"],
        )

    by_event, unmatched, without_offer = match_offer_events(
        event_list,
        raw_events,
        betradar_by_event_id=getattr(identity_bridge, "betradar_by_event_id", None),
    )
    events_by_id = {e.event_id: e for e in event_list.events}

    ordered = sorted(by_event.items(), key=lambda item: events_by_id[item[0]].start_time)
    capped = 0
    if max_events is not None:
        skipped = ordered[max_events:]
        ordered = ordered[:max_events]
        if skipped:
            capped = len(skipped)
            gaps.append(f"capped at {max_events} fixtures; {len(skipped)} matched fixtures not priced")
            without_offer = without_offer + [event_id for event_id, _ in skipped]

    offers: list[SuperbetEventOffer] = []
    for event_id, found in ordered:
        raw = found["raw"]
        superbet_id = raw.get("eventId") or raw.get("offerId")
        detailed = raw
        try:
            fetched = api.event_odds(superbet_id)
            if fetched:
                detailed = fetched
        except Exception as exc:  # noqa: BLE001 - one dead fixture is not a dead run
            gaps.append(f"event {superbet_id}: {exc}")
        offers.append(
            build_event_offer(
                detailed,
                event=events_by_id.get(event_id),
                delta_minutes=found["delta_minutes"],
                matched_by=str(found.get("matched_by") or "name_and_kickoff"),
            )
        )

    missing = sorted(set(without_offer))
    # offerState=prematch stops carrying a fixture the moment it goes live, so
    # anything already kicked off is expected to be absent and must not read as
    # a matching failure.
    kicked_off = sorted(
        event_id
        for event_id in missing
        if (started := _parse_kickoff(getattr(events_by_id.get(event_id), "start_time", None)))
        is not None and started <= fetched_at
    )
    # Deliberately not appended to data_gaps: a gap makes the step PARTIAL,
    # and a fixture the book dropped because it started is the expected state
    # of any run after the first kickoff, not a degraded one. It travels as its
    # own field and the step script says it out loud.

    return SuperbetOfferV1(
        run_id=event_list.run_id,
        date=event_list.date,
        generated_at=generated_at or datetime.now(UTC).isoformat(),
        window_start=start.isoformat(),
        window_end=end.isoformat(),
        requests_made=getattr(api, "request_count", 0),
        events_on_offer=len(raw_events),
        events_matched=len(offers),
        events_unmatched=len(unmatched),
        our_events_without_offer=missing,
        our_events_kicked_off=kicked_off,
        events_capped=capped,
        events=offers,
        data_gaps=gaps,
        events_matched_by_id=sum(1 for offer in offers if offer.match_quality == "ID_MATCHED"),
        identity_bridge=(
            identity_bridge.as_metrics() if hasattr(identity_bridge, "as_metrics") else {}
        ),
        unmatched_events=[board_event(raw) for raw in unmatched if sport_of(raw)],
    )


def board_event(raw: dict[str, Any]) -> SuperbetBoardEvent:
    """One raw by-date row reduced to identity. No lines, no request."""
    return SuperbetBoardEvent(
        superbet_event_id=str(raw.get("eventId") or ""),
        match_name=str(raw.get("matchName") or ""),
        sport=sport_of(raw) or "",
        kickoff=str(raw.get("utcDate") or ""),
        betradar_id=(str(raw["betradarId"]) if raw.get("betradarId") else None),
    )


def resolve_board_to_reference(
    board: Iterable[SuperbetBoardEvent],
    reference: Iterable[tuple[str, str, str, str]],
    *,
    sport: str = "football",
    tolerance_minutes: float = 10.0,
) -> tuple[dict[str, str], list[SuperbetBoardEvent], list[str]]:
    """Join the operator's board to the provider of record, fixture by fixture.

    ``reference`` is ``(fixture_id, home, away, kickoff_iso)`` -- bzzoiro's own
    listing for the window, which the discovery adapter already pages and which
    costs no extra request. Returns
    ``(board_event_id -> fixture_id, unresolved board events, unclaimed fixture ids)``.

    Names plus a ten-minute clock, exactly as ``match_offer_events`` joins the
    other direction, and with the same one-to-one requirement: a fixture id is
    claimed once. Exact normalised names win over the tolerant comparison, and
    within each the nearest kickoff wins.

    **What this measured on 2026-09-03, and why it is a report rather than a
    slate expander.** The handoff note's premise was that Superbet's board is
    large and our entry to it is narrow -- 3,691 events against 108 matched --
    and asked for 60% of offered football to resolve to a bzzoiro id. Measured:
    of 4,041 board events in window, 150 are football and 489 tennis; the other
    3,402 are esports, simulated football and sports with no reader here.
    bzzoiro carries **29** football fixtures in that window. This function
    claims 24 of them, 83% of what exists -- and 24 of 150 offered, 16%.

    So the ceiling is the provider of record's league coverage on a Wednesday,
    not the join: bzzoiro listed 153 fixtures on Saturday 2026-08-30 and 28 on
    Wednesday 2026-09-03. No amount of matching reaches a fixture the reference
    provider has never heard of, and pricing one off a book that has no history
    for it is not the alternative. What this does deliver is the number: the
    funnel below is the difference between "the sheet is thin today" and "the
    sheet is as wide as the reference provider was".
    """
    from bet.api_clients.superbet import split_match_name

    candidates: list[tuple[str, tuple[str, ...], datetime | None]] = []
    for fixture_id, home, away, kickoff in reference:
        candidates.append((fixture_id, _side_key((home, away)), _parse_kickoff(kickoff)))

    resolved: dict[str, str] = {}
    claimed: set[str] = set()
    unresolved: list[SuperbetBoardEvent] = []
    for event in board:
        if event.sport != sport:
            continue
        theirs = _parse_kickoff(event.kickoff)
        home, away = split_match_name(event.match_name)
        key = _side_key((home, away))
        best: tuple[tuple[int, float], str] | None = None
        for fixture_id, their_key, their_kickoff in candidates:
            if fixture_id in claimed or theirs is None or their_kickoff is None:
                continue
            delta = abs((their_kickoff - theirs).total_seconds()) / 60.0
            if delta > tolerance_minutes:
                continue
            exact = key == their_key
            if not exact and not (
                len(key) == len(their_key) == 2
                and sides_compatible(key[0], their_key[0])
                and sides_compatible(key[1], their_key[1])
            ):
                continue
            score = (0 if exact else 1, delta)
            if best is None or score < best[0]:
                best = (score, fixture_id)
        if best is None:
            unresolved.append(event)
            continue
        claimed.add(best[1])
        resolved[event.superbet_event_id] = best[1]

    unclaimed = [fixture_id for fixture_id, _, _ in candidates if fixture_id not in claimed]
    return resolved, unresolved, unclaimed


def player_alias_index(
    offer: SuperbetOfferV1,
    our_names_by_event: Mapping[str, Iterable[str]],
) -> dict[str, dict[str, str]]:
    """``{event_id: {our_player_name: superbet_player_name}}``.

    Built once per offer and handed to every ``lookup_line`` call, so a prop
    resolved for the sheet and the same prop resolved for a coupon leg can never
    disagree about which human they mean. The direction is ours-to-theirs
    because that is the direction every caller looks it up in: rows carry our
    spelling.
    """
    index: dict[str, dict[str, str]] = {}
    for event in offer.events:
        if not event.event_id:
            continue
        theirs = {line.player_name for line in event.lines if line.player_name}
        if not theirs:
            continue
        resolved = resolve_player_names(
            our_names_by_event.get(event.event_id, ()), theirs
        )
        index[event.event_id] = {ours: their for their, ours in resolved.items()}
    return index


def lookup_line(
    event_offer: SuperbetEventOffer | None,
    *,
    market: str,
    line: float,
    direction: str,
    team_name: str | None,
    player_name: str | None = None,
    player_aliases: Mapping[str, str] | None = None,
) -> tuple[str, SuperbetLine | None, float | None, float | None]:
    """Resolve one row against one fixture's offer.

    Returns ``(availability, exact_line, nearest_line, nearest_price)``. Split
    out of the comparison so ANALYZE, ``build_coupons`` and the comparison
    artifact all answer this question with the same code -- three
    implementations of "is this on the screen" would drift within a week.

    ``player_name`` is **our** spelling and ``player_aliases`` is this fixture's
    ours-to-theirs map from ``player_alias_index``. A player-scope market with no
    alias map is ``SCOPE_NOT_SUPPORTED``, exactly as before this stage learned to
    read props -- a caller that has not been taught to pass the map must not
    start reporting props as missing from the book.
    """
    superbet_player: str | None = None
    if market in PLAYER_SCOPE_MARKETS:
        if player_aliases is None:
            return ("SCOPE_NOT_SUPPORTED", None, None, None)
        if event_offer is None:
            return ("EVENT_NOT_MATCHED", None, None, None)
        superbet_player = player_aliases.get(player_name or "")
        if superbet_player is None:
            # Whose gap is it? If the book prices this market for nobody on
            # the fixture, no spelling of ours could have joined -- that is
            # the book's coverage, and reporting it as a join failure sent
            # the operator chasing name-matching on props that cannot be
            # bought at any spelling (most of a day's PLAYER_NOT_MATCHED
            # rows were exactly this). Only when the market exists for
            # *other* players is the missing alias plausibly ours: Superbet
            # not listing this player, or two of ours fitting its string
            # equally well and the join refusing.
            if not event_offer.lines:
                return ("OFFER_EMPTY", None, None, None)
            if not any(candidate.market == market for candidate in event_offer.lines):
                return ("MARKET_NOT_OFFERED", None, None, None)
            return ("PLAYER_NOT_MATCHED", None, None, None)
        # A prop names a player, not a side; the side lives on the row for
        # reporting and must not narrow the ladder.
        team_name = None
    if event_offer is None:
        return ("EVENT_NOT_MATCHED", None, None, None)
    if not event_offer.lines:
        # The book has the fixture and is pricing nothing on it: kicked off, or
        # the offer pulled. Not a market-coverage gap.
        return ("OFFER_EMPTY", None, None, None)
    family = [
        candidate
        for candidate in event_offer.lines
        if candidate.market == market
        and candidate.direction == direction
        and candidate.team_name == team_name
        and candidate.player_name == superbet_player
    ]
    if not family:
        return ("MARKET_NOT_OFFERED", None, None, None)
    exact = next((candidate for candidate in family if abs(candidate.line - line) < 1e-9), None)
    if exact is None:
        near_line, near_price = _nearest(family, line)
        return ("LINE_NOT_OFFERED", None, near_line, near_price)
    if exact.status != "active":
        return ("SUSPENDED", exact, None, None)
    return ("OFFERED", exact, None, None)


# --- what the book itself thinks ------------------------------------------
#
# Every function below reads the *pair* of prices at one rung and divides the
# overround out. ``1/price`` alone is not a probability: on these markets the
# overround runs 8-9%, so using it would understate every disagreement by about
# that much, in the direction that lets a bad row through a gate. Two prices
# give the pair's overround exactly, and dividing it out is arithmetic rather
# than an assumption.
#
# This lives here, next to ``lookup_line``, because three callers need the same
# number: the SUPERBET comparison artifact (which records it), ``build_coupons``
# (which shrinks toward it), and the ladder check (which locates the book's
# centre from it). Three implementations of "what does the book think" would
# drift within a week, and the one that decides a bar is the one that matters.


def devigged_probability(
    event_offer: SuperbetEventOffer | None,
    *,
    market: str,
    line: float,
    direction: str,
    team_name: str | None,
    player_name: str | None = None,
    player_aliases: Mapping[str, str] | None = None,
) -> float | None:
    """The book's own probability for this exact outcome, margin removed.

    Both sides of the line, or nothing. None when the opposite side is not
    posted, which is common on one-way markets -- and None must disable
    whatever reads it rather than defaulting: we cannot say the book disagrees
    with us if we cannot read what it thinks.
    """
    opposite = "UNDER" if direction == "OVER" else "OVER"
    prices: list[float] = []
    for side in (direction, opposite):
        availability, exact, _, _ = lookup_line(
            event_offer,
            market=market,
            line=line,
            direction=side,
            team_name=team_name,
            player_name=player_name,
            player_aliases=player_aliases,
        )
        if availability != "OFFERED" or exact is None or exact.price <= 1.0:
            return None
        prices.append(exact.price)
    overround = sum(1.0 / price for price in prices)
    if overround <= 0:
        return None
    return (1.0 / prices[0]) / overround


def devigged_ladder(
    event_offer: SuperbetEventOffer | None,
    *,
    market: str,
    team_name: str | None,
    player_name: str | None = None,
    player_aliases: Mapping[str, str] | None = None,
) -> dict[float, float]:
    """``{line: P(X < line)}`` over every two-sided rung the book posted.

    A CDF sampled at the book's own half-points. Rungs posted on one side only
    are absent rather than guessed at.
    """
    if event_offer is None:
        return {}
    their_name = player_name
    if their_name is not None and player_aliases is not None:
        their_name = player_aliases.get(their_name, their_name)
    scope_team = None if market in PLAYER_SCOPE_MARKETS else team_name
    rungs = {
        offered.line
        for offered in event_offer.lines
        if offered.market == market
        and offered.team_name == scope_team
        and offered.player_name == their_name
    }
    cdf: dict[float, float] = {}
    for line in sorted(rungs):
        under = devigged_probability(
            event_offer,
            market=market,
            line=line,
            direction="UNDER",
            team_name=team_name,
            player_name=player_name,
            player_aliases=player_aliases,
        )
        if under is not None:
            cdf[line] = under
    return cdf


def ladder_centre(cdf: Mapping[float, float], *, dispersion: float | None = None) -> float | None:
    """Where the book puts this market's centre, in the market's own units.

    Two paths, and the second is the one added on 2026-09-03.

    **Two or more rungs straddling even money: interpolate.** The devigged
    ladder is a CDF and the median is where it crosses 0.5, found linearly
    between the two rungs that bracket it. Interpolated and not fitted: a
    two-parameter fit would put a shape assumption between the operator and a
    number he is being asked to bet against, and a crossing point needs no
    shape.

    **One rung, or a ladder that never crosses 0.5: read the pivot.** This used
    to return None, and on the 2026-09-03 slate that left ``ladder_sigma`` null
    on 9 of 15 singles -- the check went inert on exactly the thin, single-rung
    markets where a five-observation sample is most likely to be overruling a
    real price. One rung does locate a centre once the sample's own spread is
    known: ``P(X < L) = p`` means ``(L - mu) / sigma = Phi^-1(p)``, so
    ``mu = L - Phi^-1(p) * sigma``.

    That second path *does* assume a shape, and says so: it borrows the normal
    quantile and the sample's own dispersion. It is used only to locate a
    centre for the scale-free comparison in ``coupons.ladder_sigma``, never to
    price anything, and it was checked against the interpolated answer where
    both exist -- the Grenal's ``cards_total`` ladder gives -0.878 interpolated
    and -0.868 from its 7.5 pivot alone.

    ``dispersion`` is required for the single-rung path and ignored by the
    interpolated one. None, zero, or a pivot at exactly even money leaves the
    single-rung path unable to answer, and it returns None rather than a guess.
    """
    if not cdf:
        return None
    rungs = sorted(cdf)
    for lower, upper in zip(rungs, rungs[1:]):
        below, above = cdf[lower], cdf[upper]
        if below < 0.5 <= above and above > below:
            return lower + (0.5 - below) / (above - below) * (upper - lower)
    if not dispersion:
        return None
    # The rung nearest even money carries the most information about where the
    # centre is: a pivot at 0.99 pins the centre only loosely and puts all the
    # weight on the normal tail being the right shape.
    pivot = min(rungs, key=lambda line: (abs(cdf[line] - 0.5), line))
    probability = cdf[pivot]
    if not 0.0 < probability < 1.0:
        return None
    return pivot - NormalDist().inv_cdf(probability) * dispersion


def attach_superbet_column(
    stats_sheet: StatsSheetV1,
    offer: SuperbetOfferV1,
) -> StatsSheetV1:
    """Return a copy of the sheet with every row carrying its Superbet column.

    Pure and total: every row gets a column, including the ones the book does
    not carry. An absent column and an ``EVENT_NOT_MATCHED`` column mean
    different things -- "this run had no Superbet data" versus "the book does
    not have this fixture" -- and collapsing them is how a coverage gap gets
    read as a betting decision.
    """
    offers = {event.event_id: event for event in offer.events if event.event_id}
    # Our spelling of every player the sheet has a row for, per fixture. The
    # sheet is the right source for this: it is exactly the set of players a
    # column will be asked about, so a squad member with no prop row cannot
    # crowd out the join.
    our_players: dict[str, set[str]] = {}
    for row in stats_sheet.rows:
        if row.player_name:
            our_players.setdefault(row.event_id, set()).add(row.player_name)
    aliases = player_alias_index(offer, our_players)
    rows: list[StatsSheetRow] = []
    for row in stats_sheet.rows:
        event_offer = offers.get(row.event_id)
        availability, exact, near_line, near_price = lookup_line(
            event_offer,
            market=row.market,
            line=row.line,
            direction=row.direction,
            team_name=row.team_name,
            player_name=row.player_name,
            player_aliases=aliases.get(row.event_id, {}),
        )
        implied = devigged_probability(
            event_offer,
            market=row.market,
            line=row.line,
            direction=row.direction,
            team_name=row.team_name,
            player_name=row.player_name,
            player_aliases=aliases.get(row.event_id, {}),
        )
        rows.append(
            row.model_copy(
                update={
                    "superbet": SuperbetColumn(
                        availability=availability,  # type: ignore[arg-type]
                        price=exact.price if exact else None,
                        status=exact.status if exact else None,
                        source_market_name=exact.source_market_name if exact else None,
                        nearest_offered_line=near_line,
                        nearest_offered_price=near_price,
                        superbet_event_id=event_offer.superbet_event_id if event_offer else None,
                        implied_probability=(
                            round(implied, 4) if implied is not None else None
                        ),
                    )
                }
            )
        )
    return stats_sheet.model_copy(update={"rows": rows})
