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

from typing import Literal

from bet.simple_stats.contracts import StatsSheetRow, StatsSheetV1
from bet.strict_model import StrictBaseModel
from pydantic import Field

Tier = Literal["CALL", "LEAN", "WEAK", "DROP"]

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
) -> BetBuilderDraft:
    """Draft up to ``max_legs`` legs for one fixture, best-evidenced first.

    Only CALL and LEAN rows are eligible. A WEAK row is three or four
    observations, and ``bet-analyst.md`` already refuses to put a minimum price
    on one -- a threshold computed off four matches reads as precision that is
    not there, and putting it in a multi compounds that against three other legs.

    Ranked by ``p_low``, which is the sheet's own ranking and the only number
    here that is a probability. ``min_acceptable_odds`` is per leg: this is what
    each individual selection must pay, and the operator compares the combined
    Superbet price against their own judgement of the slip, never against a
    product computed from these.
    """
    rows = [row for row in stats_sheet.rows if row.event_id == event_id]
    excluded: dict[str, int] = {}
    eligible: list[tuple[StatsSheetRow, Tier]] = []

    for row in rows:
        tier = tier_for_row(row)
        if tier in ("WEAK", "DROP"):
            excluded[f"tier_{tier.lower()}"] = excluded.get(f"tier_{tier.lower()}", 0) + 1
            continue
        if row.p_low <= 0:
            # 1/0 is not a price, and a row whose lower bound is zero is making
            # no claim to put on a slip.
            excluded["p_low_not_positive"] = excluded.get("p_low_not_positive", 0) + 1
            continue
        eligible.append((row, tier))

    eligible.sort(key=lambda pair: (-pair[0].p_low, pair[0].market, pair[0].line))

    # One leg per market: two lines of the same market in one slip are the same
    # read twice, and Superbet will not accept both anyway.
    legs: list[BetBuilderLeg] = []
    markets_used: set[str] = set()
    for row, tier in eligible:
        if len(legs) >= max_legs:
            excluded["over_max_legs"] = excluded.get("over_max_legs", 0) + 1
            continue
        key = f"{row.market}:{row.team_name or ''}:{row.player_name or ''}"
        if key in markets_used:
            excluded["duplicate_market"] = excluded.get("duplicate_market", 0) + 1
            continue
        markets_used.add(key)
        fair_odds = 1.0 / row.p_low
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
                min_acceptable_odds=round(fair_odds * TIER_MARGIN[tier], 4),
                market_verdict=row.market_signal.verdict if row.market_signal else None,
                caveats=_caveats(row),
            )
        )

    correlated = [leg for leg in legs if leg.market in _CORRELATED_FOOTBALL_FAMILY]
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
