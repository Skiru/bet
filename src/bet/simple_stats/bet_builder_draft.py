"""Bet Builder draft: which legs are worth assembling, and what each must pay.

What this is not
----------------
It is not a price. There is no bet-builder endpoint anywhere in bzzoiro's API,
and there is no arithmetic here or elsewhere that turns four leg prices into a
combined one. ``BetBuilderDraft.combined_price`` is typed ``None`` on the
contract itself rather than merely defaulted to it, so nothing downstream can
populate it even by mistake. The operator reads the combined price off their own
Superbet screen; this produces the legs and the thresholds to check it against.

That is not caution for its own sake. Corners, cards, fouls and shots in one
match are strongly positively correlated -- a foul-heavy match is a card-heavy
match -- so the product of the leg probabilities is not the parlay probability,
and it is wrong in the direction that flatters the bet. A bookmaker's own Bet
Builder price already accounts for that; a number computed here would not, and
would read as a second opinion confirming the first.

Why it is code and not prose
----------------------------
``bet-analyst`` has no Write or Edit tool by design, so the alternative is
free-handing this arithmetic in every report. That is exactly the anti-pattern
``wilson_lower_bound`` already exists to avoid: a threshold computed in prose
cannot be audited, reproduced, or tested, and a rounding slip in it is invisible.
So the margins live in a table, the tier rules live in one function, and both
have tests.

The tier rules are ``bet-analyst.md``'s own table, implemented
------------------------------------------------------------
``StatsSheetRow`` carries no tier field -- CALL/LEAN/WEAK/DROP is the analyst's
vocabulary, derived from the row's numbers. ``tier_for_row`` is that derivation
written down once, including the two structural ceilings the doc states: a
single-source row can never be CALL, and a player prop off a predicted XI is
capped at LEAN however large its sample.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Literal

from bet.simple_stats.contracts import StatsSheetRow, StatsSheetV1
from bet.strict_model import StrictBaseModel
from pydantic import Field

Tier = Literal["CALL", "LEAN", "WEAK", "DROP"]

# Low-line UNDER props are trivially clearable and dominate a p_low sort:
# "player carded UNDER 0.5" at 10/10 lands near 0.72, above almost every corners
# row, because most players are not carded in most matches -- which is also
# exactly why that side is priced near 1.05 and is not a bet.
#
# Lives here rather than in ``coupons`` because both consumers need it and they
# disagreed. The singles list pushed these to the end and said so in the file's
# own header; ``draft_legs`` sorted on ``-p_low`` alone, so the same rows *led*
# every Bet Builder. On 2026-09-01 that produced eight slips whose leading legs
# were "goals 1H UNDER 4.5" and "goals 2H UNDER 3.5" at Superbet prices of
# 1.001 and 1.05 -- the header promised they had been demoted while the slips
# below it were built out of nothing else.
TRIVIAL_UNDER_MAX_LINE = 1.5


def is_trivial_under(row: StatsSheetRow) -> bool:
    """A low-line UNDER: real as a read, worthless as a price."""
    return row.direction == "UNDER" and row.line <= TRIVIAL_UNDER_MAX_LINE


class AnalystVeto(StrictBaseModel):
    """One row bet-analyst disagreed with, from ``<date>_analyst_vetoes.json``.

    docs/PLAN_BOGATE_STATYSTYKI.md Faza 5e, Wariant A: the analyst has no
    Write tool by design (it must not rewrite the artifacts it evaluates), so
    this is text it returns alongside its usual markdown report; the
    orchestrator running ``run-day.md`` is what persists it to a file. It never
    touches ``p_low`` -- ``VETO`` removes a row from the coupon outright,
    ``DOWNGRADE`` steps its tier down once via the same ceiling
    ``context_flags`` uses, in both cases with the analyst's own reason
    reported in the coupon file's header so nothing is struck silently.

    ``line`` and ``direction`` are both optional, and **None means "all of
    them"**. A per-line veto could only ever describe a per-line fault, and the
    faults the analyst actually finds are rarely that shape: when six of
    eighteen ``cards_total`` observations are zeros in matches with twenty-plus
    fouls, the sample is broken for every line of that market, not for 4.5 and
    3.5 specifically. On 2026-09-01 exactly that happened -- 4.5 and 3.5 were
    vetoed on Sheffield United - Bolton, 5.5 was not written down, and 5.5 went
    out as a Bet Builder leg graded CALL off the same seven zeros.

    Resolution is most-specific-first, so a file may carry a market-wide veto
    and a per-line exception to it without ambiguity.
    """

    event_id: str
    market: str
    line: float | None = None
    direction: Literal["OVER", "UNDER"] | None = None
    action: Literal["VETO", "DOWNGRADE"]
    reason: str


class VetoIndex:
    """The analyst's vetoes, resolved per row, most specific first.

    Four lookups in a fixed order -- exact line and direction, then either one
    widened, then the whole market. The first hit wins, which is what lets a
    market-wide VETO coexist with a per-line DOWNGRADE on the same market
    without either silently shadowing the other.

    One index, shared by the singles loop and ``draft_legs``. That sharing is
    the entire point of the class existing: on 2026-09-01 the two paths had
    separate implementations of "is this row vetoed" -- one of them being no
    implementation at all -- and the Bet Builder shipped a slip whose every leg
    the analyst had struck.
    """

    __slots__ = ("_by_key",)

    def __init__(self, vetoes: Iterable[AnalystVeto] | None = None) -> None:
        self._by_key: dict[tuple[str, str, float | None, str | None], AnalystVeto] = {}
        for veto in vetoes or ():
            self._by_key.setdefault(
                (veto.event_id, veto.market, veto.line, veto.direction), veto
            )

    def __bool__(self) -> bool:
        return bool(self._by_key)

    def for_row(self, row: StatsSheetRow) -> AnalystVeto | None:
        for line, direction in (
            (row.line, row.direction),
            (None, row.direction),
            (row.line, None),
            (None, None),
        ):
            hit = self._by_key.get((row.event_id, row.market, line, direction))
            if hit is not None:
                return hit
        return None

# One step down, both directions structural rather than about the numbers --
# same shape as the SINGLE_SOURCE/DISAGREE and predicted-lineup ceilings below.
# A row already at WEAK stays WEAK: context can argue a real read down to
# marginal, never all the way to DROP, which is reserved for a sample too thin
# to mean anything at all.
_STEP_DOWN: dict[Tier, Tier] = {"CALL": "LEAN", "LEAN": "WEAK"}


def step_tier_down(tier: Tier) -> Tier:
    """One tier step down, never past WEAK. Shared by ``tier_for_row``'s own
    ``context_flags`` ceiling and ``coupons.build_coupons``'s analyst-veto
    DOWNGRADE action (docs/PLAN_BOGATE_STATYSTYKI.md Faza 5e) -- one rule,
    reused, rather than the same mapping written twice."""
    return _STEP_DOWN.get(tier, tier)

# Margin over fair odds, by tier. A CALL is corroborated and reasonably sampled,
# so it needs less headroom than a LEAN carrying a structural caveat. Both are
# above 1.0 because ``p_low`` is already an optimistic floor: its trials are not
# independent (the sample pools both teams and their h2h), so a price exactly at
# fair odds is a losing bet at the true probability.
TIER_MARGIN: dict[str, float] = {"CALL": 1.05, "LEAN": 1.10}

# Markets whose outcomes in a single football match move together. Any two legs
# drawn from here are positively correlated, which is most of what anyone would
# want to put in a same-game multi.
_CORRELATED_FOOTBALL_FAMILY = frozenset(
    {
        "corners_total", "corners_for",
        "cards_total", "cards_for",
        "fouls_total", "fouls_for",
        "shots_total", "shots_for",
        "shots_on_target_total", "shots_on_target_for",
        "goals_total", "goals_for",
        "goals_1h_total", "goals_2h_total",
        "offsides_total", "offsides_for", "red_cards_total",
        "player_total_shots", "player_shots_on_target",
        "player_fouls", "player_was_fouled", "player_cards",
        "player_tackles", "player_assists", "player_offsides",
    }
)

# The tennis equivalent, and it had no equivalent until 2026-09-01. Every one of
# these grows with match length, so two of them in one slip are close to the
# same bet twice: a straight-sets win settles "under 3.5 sets", "under 34.5
# games", "under 24.5 aces" and "under 12.5 double faults" together.
_CORRELATED_TENNIS_FAMILY = frozenset(
    {
        "total_sets", "total_games", "games_won",
        "aces_total", "aces_for",
        "double_faults_total", "double_faults_for",
        "breaks_total",
    }
)


class BetBuilderLeg(StrictBaseModel):
    """One leg, with the price it must beat on the operator's own screen."""

    event_id: str
    market: str
    line: float
    direction: Literal["OVER", "UNDER"]
    team_name: str | None = None
    player_name: str | None = None
    tier: Tier
    p_low: float
    hit_rate: float
    sample_size: int
    fair_odds: float
    min_acceptable_odds: float
    # Copied from ``row.market_signal`` when the MARKET_CONTEXT stage ran and
    # reached a verdict on this exact row. Reported, never priced with: it does
    # not enter fair_odds or min_acceptable_odds, both of which come from p_low
    # and nothing else.
    market_verdict: str | None = None
    # The operator's own book (SUPERBET, 2026-08-31). ``superbet_availability``
    # is the field that matters: a leg whose line is not on Superbet's ladder
    # cannot go in the slip at any price, and before this existed it went in
    # looking exactly like a leg that could.
    superbet_availability: str | None = None
    superbet_price: float | None = None
    superbet_nearest_line: float | None = None
    caveats: list[str] = Field(default_factory=list)


class BetBuilderDraft(StrictBaseModel):
    """A slip to hand-assemble, and every reason to be careful with it."""

    event_id: str
    legs: list[BetBuilderLeg] = Field(default_factory=list)
    # Typed None, not defaulted to None. There is no value this may ever hold:
    # multiplying leg prices is wrong for correlated legs, and no endpoint
    # serves a real one. The operator reads it off their own screen.
    combined_price: None = None
    correlation_risk: Literal["HIGH", "LOW", "NOT_APPLICABLE"] = "NOT_APPLICABLE"
    correlation_note: str = ""
    excluded: dict[str, int] = Field(default_factory=dict)


def tier_for_row(row: StatsSheetRow) -> Tier:
    """The evidence tier from ``bet-analyst.md``'s table, plus its two ceilings.

    | CALL | n>=8, AGREE          |
    | LEAN | n>=8 single-source, or n>=5 AGREE |
    | WEAK | n 3-4                |
    | DROP | data_quality BLOCKED or n<3 |

    Ceilings, both structural rather than about the numbers: a row nothing
    corroborates can never be CALL however large its sample, and a player prop
    drawn from a predicted XI is capped at LEAN because the sample is fine and
    the premise -- that he starts -- is a guess.
    """
    if row.data_quality == "BLOCKED" or row.sample_size < 3:
        return "DROP"
    if row.sample_size < 5:
        return "WEAK"

    corroborated = row.cross_provider_agreement == "AGREE"
    if row.sample_size >= 8 and corroborated:
        tier: Tier = "CALL"
    elif row.sample_size >= 8 or corroborated:
        tier = "LEAN"
    else:
        # n of 5-7, uncorroborated: a direction worth knowing, not a call.
        tier = "LEAN"

    if row.cross_provider_agreement in ("SINGLE_SOURCE", "DISAGREE"):
        tier = "LEAN" if tier == "CALL" else tier
    if row.player_id and (row.lineup_status or "") != "confirmed":
        tier = "LEAN" if tier == "CALL" else tier
    # Context (referee, injuries, form, derby, weather) may argue a row down,
    # never up and never into p_low itself -- see contracts.ContextFlag. One
    # step regardless of how many flags fired: a fixture is not worse for
    # having two reasons to doubt it than for having one.
    if any(flag.direction == "ARGUES_AGAINST" for flag in row.context_flags):
        tier = step_tier_down(tier)
    return tier


def _caveats(row: StatsSheetRow) -> list[str]:
    notes: list[str] = []
    if row.cross_provider_agreement == "SINGLE_SOURCE":
        notes.append("single-source: nothing corroborates this row")
    if row.cross_provider_agreement == "DISAGREE":
        notes.append("providers disagree and were never averaged")
    if row.player_id and (row.lineup_status or "") != "confirmed":
        notes.append(
            f"lineup {row.lineup_status or 'unknown'}: the sample is real, the "
            "premise that he starts is a guess"
        )
    if row.sample_size < 8:
        notes.append(f"thin sample (n={row.sample_size})")
    return notes


def draft_legs(
    stats_sheet: StatsSheetV1,
    event_id: str,
    *,
    max_legs: int = 4,
    vetoes: VetoIndex | None = None,
    min_p_low: float = 0.0,
    price_for: Callable[[StatsSheetRow], tuple[str | None, float | None]] | None = None,
    require_value: bool = False,
) -> BetBuilderDraft:
    """Draft up to ``max_legs`` legs for one fixture, best-evidenced first.

    Every gate a single passes, a leg passes too. That sentence is the whole
    change of 2026-09-01, and it is worth stating as an invariant because the
    file it fixes looked correct: the singles list had vetoes, a ``min_p_low``
    floor, a price check and a trivial-under demotion, the Bet Builder had none
    of them, and nothing in the artifact said so. Thirty legs went out that day;
    twenty-eight were priced below their own minimum or had no price at all, and
    the two that cleared were rows the analyst had explicitly struck.

    Only CALL and LEAN rows are eligible. A WEAK row is three or four
    observations, and ``bet-analyst.md`` already refuses to put a minimum price
    on one -- a threshold computed off four matches reads as precision that is
    not there, and putting it in a multi compounds that against three other legs.

    ``vetoes`` is the same ``VetoIndex`` the singles loop resolves against, so
    a struck row cannot reappear here wearing a different hat. ``min_p_low``
    defaults to 0.0 rather than to the singles threshold: a caller that has not
    been taught to pass one keeps the behaviour it had, and ``build_coupons``
    passes its own.

    ``price_for`` answers "what is this on the operator's screen", returning
    ``(availability, price)``. With ``require_value`` it also decides
    eligibility: a leg whose price is below ``min_acceptable_odds``, or which
    has no price at all, is not a leg. Without it the price is annotated and
    reported exactly as before -- the operator sees the number and judges it.

    Ranked by ``p_low`` within a demotion class: a trivial low-line UNDER
    (``is_trivial_under``) never leads a slip, because 20/20 on "under 4.5
    first-half goals" is a fact about football rather than a read on this
    fixture, and it is priced at 1.001 for that reason.
    """
    rows = [row for row in stats_sheet.rows if row.event_id == event_id]
    excluded: dict[str, int] = {}
    eligible: list[tuple[StatsSheetRow, Tier]] = []

    def exclude(reason: str) -> None:
        excluded[reason] = excluded.get(reason, 0) + 1

    for row in rows:
        tier = tier_for_row(row)
        veto = vetoes.for_row(row) if vetoes is not None else None
        # Before the tier gate, exactly as in the singles loop: a DOWNGRADE that
        # reaches WEAK must exclude the leg, and one that only reaches LEAN must
        # raise min_acceptable_odds from the CALL margin to the LEAN margin.
        if veto is not None and veto.action == "DOWNGRADE":
            tier = step_tier_down(tier)
        if tier in ("WEAK", "DROP"):
            exclude(f"tier_{tier.lower()}")
            continue
        if veto is not None and veto.action == "VETO":
            exclude("analyst_veto")
            continue
        if row.p_low <= 0:
            # 1/0 is not a price, and a row whose lower bound is zero is making
            # no claim to put on a slip.
            exclude("p_low_not_positive")
            continue
        if row.p_low < min_p_low:
            exclude("p_low_below_threshold")
            continue
        eligible.append((row, tier))

    # Price every eligible row once, before ranking. Whether a leg beats its own
    # threshold is a property of the leg, so it has to be known to rank it -- and
    # pricing here rather than inside the loop below means ``price_for`` is
    # called once per row instead of twice.
    def _priced(row: StatsSheetRow, tier: Tier) -> tuple[float, str | None, float | None]:
        minimum = round((1.0 / row.p_low) * TIER_MARGIN[tier], 4)
        if price_for is None:
            return minimum, None, None
        availability, price = price_for(row)
        return minimum, availability, price

    priced: dict[int, tuple[float, str | None, float | None]] = {
        id(row): _priced(row, tier) for row, tier in eligible
    }

    def _surplus(pair: tuple[StatsSheetRow, Tier]) -> float | None:
        """How far this leg's price clears its own threshold, or None."""
        minimum, availability, price = priced[id(pair[0])]
        if availability != "OFFERED" or price is None or price < minimum:
            return None
        return round(price - minimum, 4)

    # Value first, exactly as the singles list is ranked in ``coupons.py``: a leg
    # the operator's own book prices at or above its ``min_acceptable_odds``
    # outranks one it does not, however high the second leg's ``p_low``.
    #
    # Ranking on ``-p_low`` alone filled slips with near-tautologies and hid the
    # legs worth taking. Measured 2026-09-01: all eight slips shipped 28 legs and
    # **none** beat its threshold, because "under 3.5 first-half goals" at
    # p_low 0.72 is priced 1.01 and therefore outranked
    # ``corners_for 4.5 UNDER`` at p_low 0.57 priced 2.70 -- a +0.75 surplus,
    # dropped as ``over_max_legs``. A leg that cannot be worth its price is not
    # better evidence than one that is; it is a more certain way to be paid
    # nothing.
    value = [pair for pair in eligible if _surplus(pair) is not None]
    value_ids = {id(pair[0]) for pair in value}
    rest = [pair for pair in eligible if id(pair[0]) not in value_ids]
    value.sort(
        key=lambda pair: (
            -(_surplus(pair) or 0.0), -pair[0].p_low, pair[0].market, pair[0].line
        )
    )
    # Trivial UNDERs sort last, never first. Same key the singles list uses, and
    # applied to the same group: the one with no Superbet value to rank on.
    rest.sort(
        key=lambda pair: (
            is_trivial_under(pair[0]), -pair[0].p_low, pair[0].market, pair[0].line
        )
    )
    eligible = value + rest

    # One leg per market: two lines of the same market in one slip are the same
    # read twice, and Superbet will not accept both anyway.
    legs: list[BetBuilderLeg] = []
    markets_used: set[str] = set()
    for row, tier in eligible:
        if len(legs) >= max_legs:
            exclude("over_max_legs")
            continue
        key = f"{row.market}:{row.team_name or ''}:{row.player_name or ''}"
        if key in markets_used:
            exclude("duplicate_market")
            continue
        fair_odds = 1.0 / row.p_low
        minimum, availability, price = priced[id(row)]
        # Availability is not a value judgement and is not optional. A slip
        # is placed as one unit, so a leg the book does not carry does not
        # make the slip worse -- it makes the slip impossible. Five of the
        # eight slips shipped on 2026-09-01 contained a leg on a line
        # Superbet does not list, and each was presented as a coupon to go
        # and place. Unlike a single, there is no honest way to print that.
        if price_for is not None and availability != "OFFERED":
            exclude(f"superbet_{(availability or 'unknown').lower()}")
            continue
        if require_value and price is not None and price < minimum:
            # Below the bar but on the screen: a real answer about a real
            # market, and the operator may still want to see it. Only dropped
            # when the caller asked for a file of nothing but takeable bets.
            exclude("superbet_priced_below_threshold")
            continue

        markets_used.add(key)
        legs.append(
            BetBuilderLeg(
                event_id=row.event_id,
                market=row.market,
                line=row.line,
                direction=row.direction,
                team_name=row.team_name,
                player_name=row.player_name,
                tier=tier,
                p_low=row.p_low,
                hit_rate=row.hit_rate,
                sample_size=row.sample_size,
                fair_odds=round(fair_odds, 4),
                min_acceptable_odds=minimum,
                market_verdict=row.market_signal.verdict if row.market_signal else None,
                superbet_availability=availability,
                superbet_price=price,
                caveats=_caveats(row),
            )
        )

    correlated = [leg for leg in legs if leg.market in _CORRELATED_FOOTBALL_FAMILY]
    tennis_length = [leg for leg in legs if leg.market in _CORRELATED_TENNIS_FAMILY]
    if len(correlated) >= 2:
        risk = "HIGH"
        note = (
            f"{len(correlated)} of {len(legs)} legs are from the correlated "
            "football family (corners/cards/fouls/shots/goals in one match): a "
            "foul-heavy match is a card-heavy match, so these land together far "
            "more often than independence implies. The combination is therefore "
            "less unlikely than the legs suggest -- and Superbet's own Bet "
            "Builder price already reflects that. Never multiply the legs."
        )
    elif len(tennis_length) >= 2:
        # Added 2026-09-01. "Under 34.5 games" and "under 3.5 sets" were shipped
        # as a LOW-correlation pair, which is close to the most correlated pair
        # tennis has: a match that ends in three sets is a short match almost by
        # definition. There was no tennis family here at all, so every tennis
        # slip fell through to the "not from the same correlated family" branch.
        risk = "HIGH"
        note = (
            f"{len(tennis_length)} of {len(legs)} legs measure the same thing -- "
            "how long the match runs. Sets, games, aces and double faults all "
            "grow together, so a short match settles every one of these UNDERs "
            "at once and a long one settles none. Superbet's own price reflects "
            "that; the legs read as independent and are not. Never multiply them."
        )
    elif len(legs) >= 2:
        risk = "LOW"
        note = "legs are not from the same correlated family, but same-match legs are never fully independent"
    else:
        risk = "NOT_APPLICABLE"
        note = ""

    return BetBuilderDraft(
        event_id=event_id,
        legs=legs,
        correlation_risk=risk,  # type: ignore[arg-type]
        correlation_note=note,
        excluded=dict(sorted(excluded.items())),
    )
