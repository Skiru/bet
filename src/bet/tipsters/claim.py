"""Strict classification of a tipster's *market claim*.

Why this exists separately from :mod:`market_parser`
----------------------------------------------------
``market_parser`` is deliberately permissive: it is fed whole page paragraphs
and is allowed to guess, because a wrong guess there only mislabels an evidence
row nobody adds up. The tipster *column* has the opposite requirement. It is
displayed next to ``p_low`` as "3 of 5 tipsters point the same way", and a
number like that is worthless -- worse, actively misleading -- if a single
mismatched pick can be counted into it.

So this module parses only the claim text itself (ZawodTyper's ``type`` field,
Typersi's tip cell), never the surrounding prose, and it refuses to answer when
the claim is not unambiguous. Everything it cannot pin down comes back with
``countable=False`` and is reported as "no coverage" rather than folded in.

Four distinctions the old classifier collapsed, each of which silently inflated
agreement counts:

* **scope** -- ``"Sabah Baku Over 5,5 rzutów rożnych"`` is *that team's*
  corners, not the match total the stats sheet computes. Counting it as
  agreement on a match-total row is comparing two different bets.
* **combos** -- ``"X2 + Betis powyżej 0,5 gola"`` only pays if both legs land.
  The tipster is not claiming "over 0.5 goals"; they are claiming a parlay.
* **player props** -- ``"Chery, Tjaronn - powyżej 1.5"`` is one player's shots,
  landing in the same family as a match total under the old rules.
* **period** -- ``"Over 1.5 gola w pierwszej połowie"`` is a half, not a match.

The Polish inflection bug this replaces
---------------------------------------
``_STAT_PATTERNS`` matched corners with ``rzut(?:y|ow|ów)?\\s*ro[żz]n\\b``. The
trailing ``\\b`` requires a non-word character after ``rożn``, but every real
Polish form continues the word (``rożnych``, ``rożne``, ``rożnymi``), so the
pattern never fired on live text and the ``goals`` fallback swallowed it. Every
Polish corners pick in the 4417-row history is therefore filed as ``goals``.
Patterns here are stem-anchored at the front and left open at the end.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from .normalization import collapse_ws, names_score, normalize_key

# Canonical metric names, identical to bet.simple_stats.contracts. A claim that
# cannot be mapped onto one of these can never be compared to a stats-sheet row.
CanonicalMarket = Literal[
    "corners_total",
    "cards_total",
    "shots_total",
    "shots_on_target_total",
    "fouls_total",
    "goals_total",
    "total_games",
    "total_sets",
    "aces_total",
    "double_faults_total",
    "points_total",
]

Scope = Literal["MATCH", "TEAM", "PLAYER", "PERIOD", "UNKNOWN"]

ClaimDirection = Literal["OVER", "UNDER", "OTHER"]


# Stems are anchored at the start of a word and left open at the end so Polish
# case endings (rożn-ych/-e/-ymi, kart-ki/-ek, strzal-ow) still match. Order
# matters: the first hit wins, so specific units precede "goals", which is the
# unit most likely to appear incidentally in a sentence about anything else.
_UNIT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("corners_total", re.compile(r"\b(?:corners?|rzut\w*\s+ro[żz]n\w*|ro[żz]n\w*|ck)\b", re.I)),
    ("cards_total", re.compile(r"\b(?:cards?|bookings?|kart\w*|[żz][óo][łl]t\w*|czerwon\w*)\b", re.I)),
    (
        "shots_on_target_total",
        re.compile(r"\b(?:shots?\s+on\s+target|sot|strza[łl]\w*\s+(?:na|w)\s+(?:cel|bramk\w*)|celn\w*\s+strza[łl]\w*)\b", re.I),
    ),
    ("shots_total", re.compile(r"\b(?:shots?|strza[łl]\w*)\b", re.I)),
    ("fouls_total", re.compile(r"\b(?:fouls?|faul\w*|przewinien\w*)\b", re.I)),
    ("aces_total", re.compile(r"\b(?:aces?|as[óo]w\s+serwisow\w*)\b", re.I)),
    ("double_faults_total", re.compile(r"\b(?:double\s+faults?|podw[óo]jn\w*\s+b[łl][ęe]d\w*)\b", re.I)),
    ("total_games", re.compile(r"\b(?:games?|gem[óo]w|gem\w*)\b", re.I)),
    ("total_sets", re.compile(r"\b(?:sets?|set[óo]w)\b", re.I)),
    ("points_total", re.compile(r"\b(?:points?|punkt\w*|pkt)\b", re.I)),
    ("goals_total", re.compile(r"\b(?:goals?|bram\w*|gol\w*)\b", re.I)),
)

# "pow."/"pon." are how ZawodTyper's tipsters actually abbreviate it; the old
# alternation only listed the spelled-out forms and so read "Pow.2,5 gola" as
# having no direction at all.
_OVER = re.compile(r"(?:\bover\b|\bpowy[żz]ej\b|\bpow\.|\bpon[ao]d\b|\bwi[ęe]cej\b|\bo\s*\d|\+\s*\d)", re.I)
_UNDER = re.compile(r"(?:\bunder\b|\bponi[żz]ej\b|\bpon\.|\bmniej\b|\bu\s*\d)", re.I)

# A parlay leg joiner. "+" and " i " are what ZawodTyper's bet builder emits.
_COMBO = re.compile(r"(?:\s\+\s|\+(?=\s*[A-Za-zÀ-ž])|\s&\s|\boraz\b|\band\b(?!\s*more)|\bi\b\s+(?:powy[żz]ej|poni[żz]ej|over|under|btts))", re.I)

# "Nazwisko, Imie" or "N. Nazwisko" ahead of a total: a player prop, not a match
# total. ZawodTyper writes scorer/shot props exactly this way.
_PLAYER_KEYWORD = re.compile(r"\b(?:strzelec|zawodnik|anytime\s+scorer|to\s+score|player)\b", re.I)

# Capitalised market vocabulary. These start a claim as often as a club does
# ("Kartki", "Suma", "Powyżej", "Winner"), so without excluding them the
# proper-noun scan below would read the market name as an entity.
_MARKET_VOCABULARY = frozenset(
    """
    over under powyzej ponizej pow pon ponad mniej wiecej suma total razem
    kartki kartka kartek kartkami zolte zoltych czerwone
    gol gola goli gole bram bramki bramka bramek
    rzut rzuty rzutow roznych rozne rozny
    faul fauli faule przewinienia strzal strzaly strzalow celnych celne
    punkty punktow pkt gem gemy gemow set sety setow
    corners cards shots fouls goals games sets points bookings
    btts tak nie yes no winner wygra remis draw home away
    handicap fora hc ah ou azjan azjatycki
    mecz meczu polowa polowie polowy pierwsza pierwszej druga drugiej
    i oraz and the w z na do plus minus
    """.split()
)

# Half / set / quarter restrictions. A period total is not a match total.
_PERIOD = re.compile(
    r"(?:\b(?:1|2|i{1,2}|pierwsz\w*|drug\w*|first|second)\s*(?:po[łl]ow\w*|half|ht)\b"
    r"|\bpo[łl]ow\w*\b|\bhalf\b|\bht\b"
    r"|\b\d\s*(?:set|kwart\w*|quarter|tercj\w*)\b"
    r"|\b\d(?:set|kwart)\w*)",
    re.I,
)

# A handicap carries a signed line that looks exactly like an over/under
# ("+1.5", "-2,5"), so it needs its own branch: without one it was reported as
# "combo_bet_legs_not_separable", which tells an operator the wrong thing about
# why a source is not contributing.
_HANDICAP = re.compile(r"(?:\bhandicap\b|\bhc\b|\bfora\b|\bah\b|\bazjat\w*|\bspread\b)", re.I)

# Markets that are about *which* event happens, not how many. They can never
# corroborate an over/under row, so they are classified out rather than guessed.
_NOT_A_TOTAL = re.compile(
    r"(?:\b1\.?\s*gol\b|\bfirst\s+goal\b|\bcorrect\s+score\b|\bdok[łl]adn\w*\s+wynik"
    r"|\bhandicap\b|\bhc\b|\bfora\b|\bbtts\b|\bobie\s+(?:dru[żz]yny\s+)?strzel"
    r"|\bwygra\b|\bwin(?:ner)?\b|\bmoneyline\b|\bzwyci[ęe]"
    r"|\bdraw\b|\bremis\b|\bdnb\b|\bdouble\s+chance\b|\bpodw[óo]jna\s+szansa\b)",
    re.I,
)

# The leading \b is load-bearing. Without it the bare "o"/"u" alternatives match
# the last letter of a club name, so "Torino 2 powyżej 9.5 goli" read line=2.0
# from "o 2" and never reached the real 9.5. With it, those alternatives only fire
# as standalone tokens ("o 2.5", "u 3.5"), which is the shorthand they are for.
_LINE = re.compile(
    r"\b(?:powy[żz]ej|poni[żz]ej|pow\.?|pon\.?|over|under|o|u)\s*"
    r"(?P<value>\d{1,3}(?:[.,]\d{1,2})?)",
    re.I,
)
# Fallback: "<number> <unit>", but the number must be separated from the unit.
# "1set" (an ordinal) previously came back as line=1.0.
_LINE_REVERSE = re.compile(
    r"(?P<value>\d{1,3}(?:[.,]\d{1,2})?)\s+"
    r"(?:goals?|corners?|cards?|shots?|fouls?|games?|sets?|points?|pkt"
    r"|bram\w*|gol\w*|kart\w*|strza[łl]\w*|ro[żz]n\w*|punkt\w*)",
    re.I,
)


@dataclass(frozen=True)
class MarketClaim:
    """What a tipster actually claimed, or an explicit refusal to say.

    ``countable`` is the only field the consensus column may branch on. It is
    True exactly when the claim is a plain match-total over/under on a known
    unit at a known line -- the one shape that is directly comparable to a
    ``StatsSheetRow``. ``reject_reason`` records why it was not, so an operator
    reading the artifact can see that a pick was excluded and on what grounds
    instead of wondering where it went.
    """

    raw: str
    market: str | None = None
    direction: ClaimDirection = "OTHER"
    line: float | None = None
    scope: Scope = "UNKNOWN"
    is_combo: bool = False
    countable: bool = False
    reject_reason: str = ""
    notes: list[str] = field(default_factory=list)


def _detect_unit(text: str) -> str | None:
    for market, pattern in _UNIT_PATTERNS:
        if pattern.search(text):
            return market
    return None


def _detect_direction(text: str) -> ClaimDirection:
    """Direction from the claim alone.

    The old path computed direction over ``market + " " + context``, so a
    tipster writing "Pow.2,5 gola" in a paragraph that elsewhere said "mniej"
    came out as UNDER -- the signal inverted by prose it had nothing to do
    with. Ambiguity here resolves to OTHER, never to a coin flip.
    """
    over = bool(_OVER.search(text))
    under = bool(_UNDER.search(text))
    if over and not under:
        return "OVER"
    if under and not over:
        return "UNDER"
    return "OTHER"


def _detect_line(text: str) -> float | None:
    for pattern in (_LINE, _LINE_REVERSE):
        match = pattern.search(text)
        if not match:
            continue
        value = float(match.group("value").replace(",", "."))
        if 0.5 <= value <= 300.0:
            return value
    return None


def _proper_noun_phrases(text: str) -> list[str]:
    """Capitalised runs that are not market vocabulary.

    A plain match total names no entity: "Powyżej 22,5 fauli w meczu". Anything
    that *does* name one is about that entity -- one club's corners, one player's
    shots on target -- and is therefore not the match total the stats sheet
    computes. Extracting the entity and letting the caller decide which kind it
    is replaces two brittle regexes that missed both live cases: a player written
    as "Tjarron Chery" (no comma, no initial) and a club written back-to-front
    ("FK Sabah" against a fixture listing "Sabah FK").
    """
    phrases: list[str] = []
    current: list[str] = []
    for token in text.split():
        # Punctuation becomes a separator, not nothing: deleting it turned
        # "Bodø/Glimt" into the single token "BodøGlimt", which then had to be
        # rescued by a fuzzy score instead of matching the side outright.
        stripped = re.sub(r"[^\w'À-ɏ]+", " ", token, flags=re.U).strip()
        alpha = re.sub(r"[\d_]", "", stripped).strip()
        keep = (
            len(alpha) >= 2
            and alpha[0].isupper()
            and normalize_key(alpha) not in _MARKET_VOCABULARY
        )
        if keep:
            current.append(alpha)
            continue
        if current:
            phrases.append(" ".join(current))
            current = []
    if current:
        phrases.append(" ".join(current))
    return phrases


def _references_side(phrase: str, side: str) -> bool:
    """Does this proper-noun phrase name this fixture side?

    Token-set comparison rather than a sequence ratio, because ``SequenceMatcher``
    is word-order sensitive: it scores "FK Sabah" against "Sabah FK" at 62 and
    "Betis" against "Real Betis" at 67, both well under any usable threshold,
    while the two pairs plainly name the same club. Short tokens ("fc", "fk",
    "al") are excluded from the single-token rule since they are shared by
    hundreds of unrelated clubs.
    """
    phrase_tokens = set(normalize_key(phrase).split())
    side_tokens = set(normalize_key(side).split())
    if not phrase_tokens or not side_tokens:
        return False
    if phrase_tokens <= side_tokens or side_tokens <= phrase_tokens:
        return True
    if any(len(token) >= 4 for token in phrase_tokens & side_tokens):
        return True
    return names_score(phrase, side) >= 85


def _detect_scope(text: str, home: str, away: str) -> tuple[Scope, list[str]]:
    notes: list[str] = []
    if _PERIOD.search(text):
        return "PERIOD", notes
    if _PLAYER_KEYWORD.search(text):
        return "PLAYER", notes

    phrases = _proper_noun_phrases(text)
    if not phrases:
        return "MATCH", notes

    sides_seen: set[str] = set()
    unmatched: list[str] = []
    for phrase in phrases:
        matched = False
        for side, label in ((home, "home"), (away, "away")):
            if side and _references_side(phrase, side):
                sides_seen.add(label)
                matched = True
        if not matched:
            unmatched.append(phrase)

    # An entity we cannot tie to either side is a person: a scorer, a shooter, a
    # card-taker. Checked before the side logic because a claim can name both a
    # player and their club ("Tjarron Chery, Bodø/Glimt - powyżej 0,5").
    if unmatched:
        notes.append("entity:" + ",".join(unmatched[:3]))
        return "PLAYER", notes

    # Naming both sides is just spelling out the fixture, which leaves a match
    # total a match total. Naming exactly one restricts the total to that side.
    if len(sides_seen) >= 2:
        notes.append("fixture_named")
        return "MATCH", notes
    notes.append(f"team_scope:{sorted(sides_seen)[0]}")
    return "TEAM", notes


def classify_claim(market_text: str, home_team: str = "", away_team: str = "") -> MarketClaim:
    """Classify one tipster claim. Never raises; refuses instead."""
    raw = collapse_ws(market_text or "")
    if not raw or raw.upper() == "N/A":
        return MarketClaim(raw=raw, reject_reason="empty_claim")

    scope, notes = _detect_scope(raw, home_team, away_team)
    unit = _detect_unit(raw)
    direction = _detect_direction(raw)
    line = _detect_line(raw)
    is_handicap = bool(_HANDICAP.search(raw))

    explicit_combo = bool(_COMBO.search(raw))
    # An outcome market and a total in the same claim, with no joiner:
    # "Alnassr wygra powyżej 2,5 bramki" is win-AND-over, and would otherwise
    # read as a clean over/under and be counted as agreement on a total the
    # tipster never claimed on its own. Handicaps are excluded because their
    # signed line is not a second leg -- it is the same bet's line.
    implicit_combo = bool(
        not is_handicap
        and _NOT_A_TOTAL.search(raw)
        and direction in ("OVER", "UNDER")
        and line is not None
    )
    is_combo = explicit_combo or implicit_combo

    # Ordered so the reported reason is the most specific thing wrong, which is
    # what an operator needs to know to decide whether a source is worth keeping.
    # An explicit combo comes first: its legs are not separable claims at all,
    # so nothing downstream about unit or line is meaningful.
    if explicit_combo:
        reason = "combo_bet_legs_not_separable"
    elif is_handicap:
        reason = "handicap_not_a_total"
    elif scope == "PLAYER":
        reason = "player_prop_not_a_match_total"
    elif scope == "PERIOD":
        reason = "period_total_not_a_match_total"
    elif scope == "TEAM":
        reason = "team_total_not_a_match_total"
    elif implicit_combo:
        reason = "combo_bet_legs_not_separable"
    elif _NOT_A_TOTAL.search(raw):
        reason = "outcome_market_not_a_total"
    elif unit is None:
        reason = "unit_not_recognised"
    elif direction == "OTHER":
        reason = "direction_ambiguous_in_claim"
    elif line is None:
        reason = "line_absent_from_claim"
    else:
        return MarketClaim(
            raw=raw,
            market=unit,
            direction=direction,
            line=line,
            scope="MATCH",
            is_combo=False,
            countable=True,
            notes=notes,
        )

    return MarketClaim(
        raw=raw,
        market=unit,
        direction=direction,
        line=line,
        scope=scope,
        is_combo=is_combo,
        countable=False,
        reject_reason=reason,
        notes=notes,
    )


def claim_matches_row(claim: MarketClaim, market: str, line: float, direction: str) -> bool:
    """Does a countable claim address exactly this stats-sheet row?

    Line equality is exact. A tipster on over 9.5 corners is not evidence about
    over 10.5: those are different bets that resolve differently, and treating
    them as one is how a "3 of 5" turns into a number nobody can trace back.
    """
    if not claim.countable:
        return False
    return claim.market == market and claim.direction == direction and claim.line == line


def claim_opposes_row(claim: MarketClaim, market: str, line: float, direction: str) -> bool:
    """Same market and line, opposite side -- an active contradiction."""
    if not claim.countable:
        return False
    return claim.market == market and claim.line == line and claim.direction != direction
