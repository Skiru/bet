"""What the tipster community picked repeatedly -- an appendix, never a bet.

TIPSTERS already runs and already matches picks to fixtures, but almost nothing
it collects reaches the operator. The reason is structural rather than a
failure: the pipeline only keeps a pick it can *count*, meaning a total with a
readable line and direction, because only such a claim can be compared to a
stats-sheet row. Measured on 2026-09-03: **55 picks ingested, 39 matched to a
fixture, 2 countable.** The other 37 were 1X2, both-teams-to-score or
inseparable combos -- a different market from the totals this sheet prices, and
one nothing here can convert into the other.

So they were dropped, and the coupon's *Typerzy* column read `brak` on every
row that mattered. That is throwing away the one thing the crowd is actually
informative about: **repetition.** One tipster on a home win is noise. Three
tipsters converging on the same side of the same fixture is a fact about what
the public sees, even when it says nothing about our corners line.

This module aggregates that and nothing else. Hard boundaries, because an
appendix that drifts into looking like a recommendation is worse than no
appendix:

* It never produces a probability, a `p_low`, a fair price or a minimum odds.
  There is no model here -- these are other people's opinions, counted.
* It never enters ranking, tiering, vetoing or the value test. Nothing in
  `coupons.py` reads this module.
* It reports a *different market* from the singles above it, and says so in the
  rendered text every time.

**Why counting only `direction` and not re-parsing claims.** The pick already
carries a parsed `direction`; this module groups on that and stops. The one
exception is a claim that is nothing but a bare 1X2 symbol with cosmetic noise
around it -- `1(Superzprzewage)` on Gent-Leuven 2026-09-03, which the parser
left as `OTHER` while an identical `Winner: 1` from another source became
`HOME`. Recovering those is `_bare_1x2_direction`, and it is deliberately
narrow: any combo marker or over/under token disqualifies the claim outright,
because `1 + OVER 1,5 gola` also starts with a `1` and is emphatically not a
home-win pick. Everything it cannot read is counted and reported, never
guessed.
"""
from __future__ import annotations

import re
import statistics

from bet.simple_stats.contracts import StrictBaseModel, TipsterSignalV1

# How many *distinct* tipsters must land on the same side before it is
# repetition rather than one person's opinion. Two is the lowest number that
# can be called agreement at all; on 2026-09-03 raising it to three would have
# emptied the section (the deepest agreement that day was two).
CONSENSUS_MIN_TIPSTERS = 2

# Directions that describe an outcome unambiguously *given the fixture*, so a
# count over them is a count over one claim.
#
# `OVER`/`UNDER` are absent on purpose: without a line they are not a claim.
# Two tipsters saying "over" about a match while one means 1.5 goals and the
# other 4.5 cards agree about nothing, and this module has no business
# inventing the line. A total with a line is handled below.
#
# `WIN`, `OTHER` and `DC` are absent because they need a subject the artifact
# does not carry -- `Tabilo` and `Wygra Tabilo` on Popyrin-Tabilo 2026-09-03
# both parsed as `WIN` with `subjects: []`, and which player is meant lives
# only in the claim text.
_SELF_DESCRIBING = frozenset({"HOME", "AWAY", "DRAW", "BTTS_YES", "BTTS_NO"})

_DIRECTION_LABEL = {
    "HOME": "gospodarz wygra (1)",
    "AWAY": "gość wygra (2)",
    "DRAW": "remis (X)",
    "HOME_OR_DRAW": "gospodarz lub remis (1X)",
    "AWAY_OR_DRAW": "gość lub remis (X2)",
    "HOME_OR_AWAY": "bez remisu (12)",
    "BTTS_YES": "obie drużyny strzelą",
    "BTTS_NO": "obie drużyny nie strzelą",
}


# Marks a direction recovered from a multi-leg pick. Two tipsters agreeing on a
# leg of their respective accumulators is weaker evidence than two tipsters
# agreeing on a single, and the file must not print them as the same thing.
_COMBO_SUFFIX = " (noga kombinacji)"


def _direction_label(direction: str) -> str:
    """Human wording for a grouping key, combo marker preserved.

    Totals arrive as ``"OVER cards_total 2.5"`` and are rendered rather than
    looked up, because the market and line are part of the claim and a table of
    every market x line would be a table of the whole vocabulary.
    """
    base, suffix = direction, ""
    if base.endswith(_COMBO_SUFFIX):
        base, suffix = base[: -len(_COMBO_SUFFIX)], _COMBO_SUFFIX
    if base in _DIRECTION_LABEL:
        return _DIRECTION_LABEL[base] + suffix
    parts = base.split(" ")
    if len(parts) >= 3 and parts[0] in {"OVER", "UNDER"}:
        side = "powyżej" if parts[0] == "OVER" else "poniżej"
        line = parts[-1]
        market = " ".join(parts[1:-1])
        return f"{side} {line} — {market}{suffix}"
    return base + suffix

# A claim that is only a 1X2 symbol, optionally wrapped in punctuation or a
# parenthetical aside. Anchored at both ends so a combo cannot match.
_BARE_1X2 = re.compile(r"^\s*([12x])\s*[\(\[]?[^+\d]*[\)\]]?\s*$", re.IGNORECASE)
_SYMBOL_TO_DIRECTION = {"1": "HOME", "2": "AWAY", "X": "DRAW"}

# Tokens whose presence means the claim is a total or a multi-leg bet, and so
# is never a bare 1X2 pick however it starts.
_DISQUALIFYING = re.compile(
    r"[+&]|\bover\b|\bunder\b|\bpowy[żz]ej\b|\bponi[żz]ej\b|\bbtts\b|\bgol\w*\b"
    r"|\bkartk\w*\b|\bro[żz]n\w*\b|\bfaul\w*\b|\bstrza[łl]\w*\b|\bgem\w*\b"
    r"|\bset\w*\b|\bas[óo]w\b|\d[.,]\d",
    re.IGNORECASE,
)


def _bare_1x2_direction(claim: str | None) -> str | None:
    """`1X2` recovered from a claim the parser left unreadable, or None.

    Narrow by construction. `1(Superzprzewage)` yields HOME; `x` yields DRAW;
    `1 + OVER 1,5 gola`, `o2,5` and `Over 4,5 żółtych kartek` all yield None,
    because a claim carrying a combo marker, a decimal or a market word is not
    a bare outcome pick and must not be counted as one.
    """
    if not claim:
        return None
    if _DISQUALIFYING.search(claim):
        return None
    match = _BARE_1X2.match(claim)
    if match is None:
        return None
    return _SYMBOL_TO_DIRECTION[match.group(1).upper()]


def _agent_directions(reading) -> tuple[list[str], str | None]:
    """`(directions, unusable_reason)` from one validated `tipster-reader` entry.

    A combo yields one direction per leg, because the tipster did commit to
    each. They are tagged so consensus can tell a single-leg conviction from a
    leg lifted out of a four-fold -- `_COMBO_SUFFIX` below.

    Legs the agent honestly marked `UNREADABLE`, and legs whose claim this
    vocabulary cannot express (`direction: null`, e.g. "Jagiellonia will
    score"), contribute nothing and say why.
    """
    directions: list[str] = []
    unreadable = 0
    untyped = 0
    for leg in reading.legs:
        if leg.kind == "UNREADABLE":
            unreadable += 1
            continue
        if not leg.direction:
            untyped += 1
            continue
        if leg.kind == "TOTAL":
            subject = f" {leg.subject}" if leg.subject else ""
            directions.append(f"{leg.direction} {leg.market}{subject} {leg.line:g}")
        else:
            directions.append(leg.direction)
    if directions:
        return directions, None
    if unreadable:
        return [], "agent: treść typu nieczytelna"
    if untyped:
        return [], "agent: typ poza naszym słownikiem rynków"
    return [], "agent: odczyt bez nóg"



def _pick_direction(pick) -> tuple[str | None, str | None]:
    """`(direction, unusable_reason)` for one pick.

    Exactly one of the two is set, so every pick is either counted or explained.
    """
    direction = (pick.direction or "").upper()
    if direction in _SELF_DESCRIBING:
        return direction, None
    if direction in {"OVER", "UNDER"}:
        # Countable totals keep their line, and a line makes the claim concrete
        # enough to group on. Without one there is nothing to agree about.
        if pick.line is not None and pick.market:
            return f"{direction} {pick.market} {pick.line:g}", None
        return None, "total bez czytelnej linii"
    recovered = _bare_1x2_direction(pick.claim)
    if recovered is not None:
        return recovered, None
    if direction in {"WIN", "DC"}:
        return None, "typ bez wskazanego podmiotu"
    if direction == "OTHER" or not direction:
        return None, "kierunek nieczytelny z treści typu"
    return None, f"kierunek nieobsługiwany ({direction})"


class TipsterConsensusRow(StrictBaseModel):
    """One fixture-and-side that at least ``CONSENSUS_MIN_TIPSTERS`` picked.

    Carries no probability and no threshold, and that is the whole point: a
    count of opinions is not a price. ``odds_seen`` is the median of what the
    tipsters themselves quoted, reported so the operator can see roughly which
    market they were shopping -- it is not our fair odds and not a target.
    """

    event_id: str
    match: str
    direction: str
    direction_label: str
    tipster_count: int
    tipsters: list[str]
    sources: list[str]
    odds_seen: float | None = None
    match_quality: str | None = None
    on_coupon: bool = False


class CoupledFixturePicks(StrictBaseModel):
    """Every tipster pick on a fixture that reached our coupon, verbatim.

    Separate from consensus because it answers a different question. Consensus
    asks "what does the crowd repeat"; this asks "did anyone look at the match
    I am about to bet". A single pick is worth printing here and is not worth
    printing as consensus.
    """

    event_id: str
    match: str
    match_quality: str | None = None
    picks: list[str]


class TipsterConsensus(StrictBaseModel):
    """The whole appendix. Empty is a normal answer, not a failure."""

    rows: list[TipsterConsensusRow] = []
    coupon_fixtures: list[CoupledFixturePicks] = []
    picks_ingested: int = 0
    picks_matched: int = 0
    countable_claims: int = 0
    events_covered: int = 0
    events_with_one_pick: int = 0
    unusable_picks: int = 0
    unusable_by_reason: dict[str, int] = {}
    # How many picks were read by the `tipster-reader` agent rather than the
    # regex path. Reported so the file can say which it leaned on.
    readings_from_agent: int = 0
    sources_with_picks: list[str] = []
    sources_blocked: list[str] = []


def _blocked_label(blocked) -> str:
    """`source: reason` for a source that did not answer.

    The artifact stores a dict with the full URL, and rendering it raw put a
    Python dict literal in the operator's file. Only the source and the reason
    are worth a line there; the URL is in the artifact for whoever is debugging.
    """
    if isinstance(blocked, dict):
        source = blocked.get("source_id") or blocked.get("source_name") or "?"
        reason = str(blocked.get("reason") or "").split(":")[0] or "brak odpowiedzi"
        return f"{source} ({reason})"
    return str(blocked)


def _fixture_name(event) -> str:
    home = getattr(event, "home_team", None)
    away = getattr(event, "away_team", None)
    if home and away:
        return f"{home} – {away}"
    return getattr(event, "event_id", "?")[:12]


def build_consensus(
    signal: TipsterSignalV1 | None,
    coupon_event_ids: frozenset[str] = frozenset(),
    *,
    min_tipsters: int = CONSENSUS_MIN_TIPSTERS,
    claims=None,
) -> TipsterConsensus:
    """Aggregate one day's tipster picks into repetition plus coupon overlap.

    ``coupon_event_ids`` only decorates the output (``on_coupon``, and which
    fixtures get their picks listed verbatim). It never filters consensus: a
    fixture the crowd converges on which our sheet never priced is exactly the
    thing worth seeing, and dropping it would make this section a mirror of the
    coupon instead of a second opinion on the day.

    ``claims`` is an optional validated ``TipsterClaimsV1`` from the
    ``tipster-reader`` agent. Where it has a reading for a pick, that reading
    wins over the regex path -- it is strictly better informed, and it is
    already anchored to the pick's own raw text by ``tipster_claims``. Where it
    has none, the rules still run, so the section degrades to its previous
    behaviour rather than emptying if the agent was not invoked.

    **The counting stays here either way.** The agent describes one pick at a
    time and never sees another; the arithmetic over its output is this
    function, in ordinary deterministic code, so two runs over one day cannot
    disagree about how many people picked a side.
    """
    if signal is None:
        return TipsterConsensus()

    by_pick: dict[tuple[str, str, str], object] = {}
    for reading in getattr(claims, "readings", None) or []:
        by_pick[(reading.event_id, reading.tipster_name, reading.claim)] = reading

    rows: list[TipsterConsensusRow] = []
    coupon_fixtures: list[CoupledFixturePicks] = []
    unusable_by_reason: dict[str, int] = {}
    unusable = 0
    one_pick = 0
    agent_used = 0

    for event in signal.events:
        picks = list(event.picks or [])
        if len(picks) == 1:
            one_pick += 1

        grouped: dict[str, list] = {}
        for pick in picks:
            reading = by_pick.get(
                (event.event_id, pick.tipster_name or "", pick.claim or "")
            )
            if reading is not None:
                agent_used += 1
                directions, reason = _agent_directions(reading)
                suffix = _COMBO_SUFFIX if len(reading.legs) > 1 else ""
                for direction in directions:
                    grouped.setdefault(direction + suffix, []).append(pick)
                if not directions:
                    unusable += 1
                    key = reason or "nieznany"
                    unusable_by_reason[key] = unusable_by_reason.get(key, 0) + 1
                continue
            direction, reason = _pick_direction(pick)
            if direction is None:
                unusable += 1
                key = reason or "nieznany"
                unusable_by_reason[key] = unusable_by_reason.get(key, 0) + 1
                continue
            grouped.setdefault(direction, []).append(pick)

        for direction, agreeing in grouped.items():
            # Distinct *people*, not distinct picks. One tipster posting the
            # same side twice is one opinion, and two sources republishing one
            # tipster is still one opinion.
            names = sorted({p.tipster_name for p in agreeing if p.tipster_name})
            if len(names) < min_tipsters:
                continue
            quoted = [p.odds for p in agreeing if p.odds]
            rows.append(
                TipsterConsensusRow(
                    event_id=event.event_id,
                    match=_fixture_name(event),
                    direction=direction,
                    direction_label=_direction_label(direction),
                    tipster_count=len(names),
                    tipsters=names,
                    sources=sorted({p.source_name for p in agreeing if p.source_name}),
                    odds_seen=round(statistics.median(quoted), 2) if quoted else None,
                    match_quality=getattr(event, "match_quality", None),
                    on_coupon=event.event_id in coupon_event_ids,
                )
            )

        if event.event_id in coupon_event_ids and picks:
            coupon_fixtures.append(
                CoupledFixturePicks(
                    event_id=event.event_id,
                    match=_fixture_name(event),
                    match_quality=getattr(event, "match_quality", None),
                    picks=[
                        # Verbatim, with the quoted price, because the claim
                        # text is the only place a combo's legs survive at all.
                        f"{p.tipster_name or '?'} ({p.source_name or '?'})"
                        + (f" @ {p.odds:g}" if p.odds else "")
                        + f": {p.claim}"
                        for p in picks
                    ],
                )
            )

    # A fixture the crowd agrees on and we are betting sorts first, then by how
    # many people agreed. Depth of agreement is the only quality signal here.
    rows.sort(key=lambda r: (not r.on_coupon, -r.tipster_count, r.match))
    coupon_fixtures.sort(key=lambda f: f.match)

    return TipsterConsensus(
        rows=rows,
        coupon_fixtures=coupon_fixtures,
        picks_ingested=signal.picks_ingested,
        picks_matched=signal.picks_matched,
        countable_claims=signal.countable_claims,
        events_covered=len(signal.events),
        events_with_one_pick=one_pick,
        unusable_picks=unusable,
        unusable_by_reason=dict(sorted(unusable_by_reason.items())),
        readings_from_agent=agent_used,
        sources_with_picks=list(signal.sources_with_picks or []),
        sources_blocked=[_blocked_label(s) for s in (signal.sources_blocked or [])],
    )
