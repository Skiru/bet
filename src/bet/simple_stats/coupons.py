"""Assemble one betting day's stats sheet into singles and Bet Builder slips.

This is the last computation in the chain, and it is code rather than an agent's
prose for the same reason ``wilson_lower_bound`` is: the numbers it produces are
thresholds a human bets money against. A threshold free-handed in a report
cannot be audited, reproduced, or caught when it slips by a decimal place.

What it does **not** do, and cannot be made to
----------------------------------------------
* **No combined price.** ``BetBuilderDraft.combined_price`` is typed ``None``,
  and nothing here computes one. Corners, cards, fouls and shots in one match
  are strongly positively correlated -- a foul-heavy match is a card-heavy
  match -- so the product of the legs understates the slip's real probability,
  in the direction that flatters the bet. Superbet's own price already accounts
  for the correlation; a number computed here would not, and would read as a
  second opinion confirming the first.
* **No stake.** Not a size, not a fraction of a bankroll, not a Kelly figure.
* **No EV.** EV needs a price, and the only real price is on the operator's own
  screen.

Every coupon is therefore *conditional*: "this lean is worth taking **if** the
screen shows at least X.XX". The operator supplies the price and the decision.

The one number that ranks everything
------------------------------------
``p_low`` -- the Wilson lower bound already on every row. Never ``hit_rate``:
4/4 is a hit rate of 1.00 and a ``p_low`` of 0.51, which is the whole point of
using it. Nothing in this module recomputes it; it is read from the artifact.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field

from bet.simple_stats.bet_builder_draft import (
    BetBuilderDraft,
    Tier,
    draft_legs,
    step_tier_down,
    tier_for_row,
)
from bet.discovery.team_aliases import resolve_team_alias
from bet.simple_stats.contracts import (
    EventListV1,
    MarketContextV1,
    StatsSheetRow,
    StatsSheetV1,
    SuperbetOfferV1,
)
from bet.simple_stats.superbet_offer import lookup_line
from bet.strict_model import StrictBaseModel
from bet.utils import normalize_team_name

# docs/PLAN_BOGATE_STATYSTYKI.md Faza 5d.
_COMPETITION_TIER_MAP_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "competition_tier_map.json"
)
_COMPETITION_TIER_CACHE: dict[str, str] | None = None
_COMPETITION_TIER_LOCK = threading.Lock()


def _competition_tier_map() -> dict[str, str]:
    """``{competition: tier}`` from config/competition_tier_map.json, read once.

    Exact-name pin only, matching the same rule the ESPN and SportDB
    competition maps already follow (discover.py). A missing or malformed file
    yields an empty map rather than raising -- a config problem must not
    exclude every fixture from the coupon.
    """
    global _COMPETITION_TIER_CACHE
    with _COMPETITION_TIER_LOCK:
        if _COMPETITION_TIER_CACHE is not None:
            return _COMPETITION_TIER_CACHE
    tiers: dict[str, str] = {}
    try:
        document = json.loads(_COMPETITION_TIER_MAP_PATH.read_text(encoding="utf-8"))
        tiers = {
            str(name): str(tier)
            for name, tier in (document.get("tiers") or {}).items()
        }
    except (OSError, ValueError, AttributeError):
        tiers = {}
    with _COMPETITION_TIER_LOCK:
        if _COMPETITION_TIER_CACHE is None:
            _COMPETITION_TIER_CACHE = tiers
        return _COMPETITION_TIER_CACHE


def reset_competition_tier_cache() -> None:
    """Forget the cached competition-tier map. For tests only."""
    global _COMPETITION_TIER_CACHE
    with _COMPETITION_TIER_LOCK:
        _COMPETITION_TIER_CACHE = None


def competition_tier(competition: str) -> str | None:
    """This competition's tier, or None when it is not in the map at all.

    None is deliberately not TIER_3 or any other guess: an unclassified
    competition is left alone rather than excluded on a pattern match, exactly
    the overconfident-mapping mistake the pinned ESPN competition map was
    fixed for on 2026-08-28.
    """
    return _competition_tier_map().get(competition)

# Human-readable market labels. Sourced from the row's own ``market`` field
# rather than from STANDARD_MARKET_LINES, because that table is keyed by display
# name ("Corners Total") while a row carries the canonical name
# ("corners_total") -- and the mapping between them is not one-to-one for the
# per-team family.
MARKET_LABELS: dict[str, str] = {
    "corners_total": "rożne (mecz)",
    "cards_total": "kartki (mecz)",
    "fouls_total": "faule (mecz)",
    "shots_on_target_total": "strzały celne (mecz)",
    "shots_total": "strzały (mecz)",
    "goals_total": "gole (mecz)",
    "goals_1h_total": "gole (1. połowa)",
    "goals_2h_total": "gole (2. połowa)",
    "corners_for": "rożne drużyny",
    "cards_for": "kartki drużyny",
    "fouls_for": "faule drużyny",
    "shots_on_target_for": "strzały celne drużyny",
    "shots_for": "strzały drużyny",
    "goals_for": "gole drużyny",
    "offsides_total": "spalone (mecz)",
    "offsides_for": "spalone drużyny",
    "red_cards_total": "czerwone kartki (mecz)",
    "player_total_shots": "strzały zawodnika",
    "player_shots_on_target": "strzały celne zawodnika",
    "player_fouls": "faule zawodnika",
    "player_was_fouled": "faulowany",
    "player_cards": "kartka zawodnika",
    "total_games": "gemy (mecz)",
    "aces_total": "asy (mecz)",
    "total_sets": "sety",
    "double_faults_total": "podwójne błędy (mecz)",
    "breaks_total": "przełamania",
    "aces_for": "asy zawodnika",
    "double_faults_for": "podwójne błędy zawodnika",
    "games_won": "gemy zawodnika",
}

# A single must clear this before it is worth an operator's attention.
#
# 0.50 is not arbitrary and is not a probability threshold in disguise: below it
# the fair odds exceed 2.00, and once the tier margin is applied the required
# price passes what these markets realistically pay. A row at p_low 0.35 needs
# 3.14 on a corners line that is quoted near 2.30 -- reporting it as a "bet" is
# reporting something unplaceable.
MIN_SINGLE_P_LOW = 0.50

# Low-line UNDER props are trivially clearable and dominate a p_low sort:
# "player carded UNDER 0.5" at 10/10 lands near 0.72, above almost every corners
# row, because most players are not carded in most matches -- which is also
# exactly why that side is priced near 1.05 and is not a bet. They are not
# dropped (the read is real) but they never lead, and the file says why.
TRIVIAL_UNDER_MAX_LINE = 1.5


class AnalystVeto(StrictBaseModel):
    """One row bet-analyst disagreed with, from ``<date>_analyst_vetoes.json``.

    docs/PLAN_BOGATE_STATYSTYKI.md Faza 5e, Wariant A: the analyst has no
    Write tool by design (it must not rewrite the artifacts it evaluates), so
    this is text it returns alongside its usual markdown report; the
    orchestrator running ``run-day.md`` is what persists it to a file.
    ``build_coupons.py --vetoes`` is the only thing that reads it, and it never
    touches ``p_low`` -- ``VETO`` removes a row from the coupon outright,
    ``DOWNGRADE`` steps its tier down once via the same ceiling
    ``context_flags`` uses, in both cases with the analyst's own reason
    reported in the coupon file's header so nothing is struck silently.
    """

    event_id: str
    market: str
    line: float
    direction: Literal["OVER", "UNDER"]
    action: Literal["VETO", "DOWNGRADE"]
    reason: str


class CouponSingle(StrictBaseModel):
    """One standalone bet, with the price that would justify it."""

    rank: int
    event_id: str
    match: str
    competition: str
    kickoff: str
    sport: str
    market: str
    market_label: str
    line: float
    direction: str
    subject: str | None = None
    tier: str
    p_low: float
    hit_rate: float
    hits: int
    sample_size: int
    cross_provider_agreement: str
    fair_odds: float
    min_acceptable_odds: float
    market_verdict: str | None = None
    market_price: float | None = None
    market_bookmaker: str | None = None
    tipster: str | None = None
    caveats: list[str] = Field(default_factory=list)
    # --- the operator's own book (SUPERBET, 2026-08-31) --------------------
    #
    # ``min_acceptable_odds`` above has always been a number the operator had
    # to go and check by hand. These fields are that check, done: the price on
    # Superbet for this exact (market, line, direction, subject), or the reason
    # there isn't one.
    #
    # ``superbet_verdict`` is VALUE only when a live, active Superbet price is
    # at or above ``min_acceptable_odds``. It is not a probability and it never
    # touches p_low; it answers "can this be taken, and is it worth taking at
    # the price on the screen".
    superbet_availability: str | None = None
    superbet_verdict: str | None = None
    superbet_price: float | None = None
    # price - min_acceptable_odds, in odds. Positive is the whole point.
    superbet_surplus: float | None = None
    # Set when the market exists but our line does not: the closest rung of
    # Superbet's ladder, so a systematic line mismatch is visible in the file
    # a human reads rather than only in an audit artifact.
    superbet_nearest_line: float | None = None
    superbet_nearest_price: float | None = None
    # p_low minus the market-implied probability. Set only when both numbers
    # exist for this exact row (Faza 5c) -- never interpolated, never derived
    # from a different line. None is what puts a row in the "no market
    # reference" section: not excluded, just not comparable to the market.
    edge: float | None = None


class CouponSlip(StrictBaseModel):
    """One match's Bet Builder draft, with its match identity resolved."""

    rank: int
    event_id: str
    match: str
    competition: str
    kickoff: str
    draft: BetBuilderDraft
    # Slips are ranked by their weakest leg, not their average or their best.
    # A four-leg slip settles on every leg, so its evidence is the evidence of
    # the leg you are least sure about -- averaging would let three strong legs
    # carry a fourth nobody should be betting.
    weakest_leg_p_low: float


class CouponSet(StrictBaseModel):
    """COUPONS artifact for one betting day."""

    run_id: str = ""
    date: str = ""
    generated_at: str
    singles: list[CouponSingle] = Field(default_factory=list)
    slips: list[CouponSlip] = Field(default_factory=list)
    # Deliberately typed None, never a number. See the module docstring.
    combined_price: None = None
    rows_considered: int = 0
    events_considered: int = 0
    # The kickoff cutoff this set was built against, or None when the caller
    # asked for every fixture regardless of clock. Recorded so a file can still
    # be audited after the fact: "why is that match missing" has an answer here.
    not_before: str | None = None
    excluded: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def market_label(market: str) -> str:
    return MARKET_LABELS.get(market, market.replace("_", " "))


def _subject(row: StatsSheetRow) -> str | None:
    """Whose line this is: a player, a team, or nobody (a match total)."""
    if row.player_name:
        return row.player_name
    if row.team_name:
        return row.team_name
    return None


def _is_trivial_under(row: StatsSheetRow) -> bool:
    return row.direction == "UNDER" and row.line <= TRIVIAL_UNDER_MAX_LINE


def _has_market_reference(row: StatsSheetRow) -> bool:
    """Whether this row can be ranked against a price rather than just p_low.

    Not the same question as "does market_signal exist": a NO_MARKET_DATA
    verdict still carries a MarketSignalColumn, just with
    ``market_implied_probability`` unset. Today only corners_total and
    goals_total (SIGNAL_MARKETS) can ever answer True.
    """
    return (
        row.market_signal is not None
        and row.market_signal.market_implied_probability is not None
    )


def _edge(row: StatsSheetRow) -> float:
    """p_low minus the market's own implied probability for this exact row.

    Positive means the model's floor sits above what the market prices in --
    the read the market has not caught up to. Never called on a row without a
    market reference; see ``_has_market_reference``.
    """
    return row.p_low - row.market_signal.market_implied_probability


def _caveats(row: StatsSheetRow) -> list[str]:
    notes: list[str] = []
    if row.cross_provider_agreement == "SINGLE_SOURCE":
        notes.append("jedno źródło — nic tego nie potwierdza")
    if row.cross_provider_agreement == "DISAGREE":
        notes.append("providerzy się nie zgadzają — wartości nieuśrednione")
    if row.player_id and (row.lineup_status or "") != "confirmed":
        notes.append(f"skład {row.lineup_status or 'nieznany'} — premisa to zgadywanka")
    if row.sample_size < 8:
        notes.append(f"mała próba (n={row.sample_size})")
    if _is_trivial_under(row):
        notes.append("niska linia UNDER — łatwa do trafienia i zwykle wyceniana ~1.05")
    return notes


def _kickoff_passed(kickoff: str, not_before: datetime | None) -> bool:
    """True when this fixture has already started and is no longer bettable.

    An unparseable or missing kickoff returns False. Not knowing when a match
    starts is not evidence that it started -- dropping it would silently hide a
    live fixture, which is the failure this check exists to prevent.
    """
    if not_before is None or not kickoff:
        return False
    try:
        start = datetime.fromisoformat(kickoff)
    except ValueError:
        return False
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return start <= not_before


def _tipster_summary(row: StatsSheetRow) -> str | None:
    if row.tipster is None or row.tipster.verdict == "NO_COVERAGE":
        return None
    return f"{row.tipster.agree}/{row.tipster.agree + row.tipster.oppose}"


# Values that mean "nothing to report" for the entitlement header note below:
# ENTITLED is healthy, and NOT_ATTEMPTED alone (never probed, or the run's
# call budget ran out before reaching it) already surfaces as its own
# data_gap message per event -- it is not evidence the entitlement is gone.
_ENTITLEMENT_HEALTHY = frozenset({"ENTITLED", "NOT_ATTEMPTED"})


def _entitlement_note(market_context: MarketContextV1 | None) -> str | None:
    """docs/PLAN_BOGATE_STATYSTYKI.md 3bis.6.

    A lapsed or missing "Football Unlimited" entitlement takes goals' and
    corners' market price *and* model reference at once -- the two families
    Faza 5c ranks by edge -- and until now that only showed up buried in
    per-event ``data_gaps``. Read straight from ``EventMarketContext.
    comparison_entitlement`` (not the coarser run-level bool, which cannot
    distinguish "never probed" from "probed and errored") so an ERROR state
    is caught too, not just a confirmed NOT_ENTITLED.
    """
    if market_context is None or not market_context.events:
        return None
    seen = sorted({e.comparison_entitlement for e in market_context.events})
    if set(seen) <= _ENTITLEMENT_HEALTHY:
        return None
    return (
        'UWAGA: uprawnienie "Football Unlimited" nie jest w pełni aktywne w tym '
        f"runie (comparison_entitlement: {', '.join(seen)}) — część lub cały "
        "ten kupon powstał BEZ kursu i modelu rynkowego na gole/rożne, więc "
        "ranking po przewadze (edge, Faza 5c) go tam nie widział. Sprawdź "
        "subskrypcję bzzoiro przed obstawieniem."
    )


def build_coupons(
    stats_sheet: StatsSheetV1,
    event_list: EventListV1 | None = None,
    *,
    max_singles: int = 15,
    max_slips: int = 8,
    max_legs: int = 4,
    min_p_low: float = MIN_SINGLE_P_LOW,
    not_before: datetime | None = None,
    vetoes: list[AnalystVeto] | None = None,
    market_context: MarketContextV1 | None = None,
    superbet_offer: SuperbetOfferV1 | None = None,
    require_superbet_value: bool = False,
) -> CouponSet:
    """Turn a finished stats sheet into the day's singles and slips.

    Pure: no network, no DB, no clock. Given the same artifact *and the same*
    ``not_before`` it returns the same coupons, which is what makes a bad call
    reviewable after the fact -- the cutoff is an argument, never a call to
    ``now()`` inside, precisely so that property survives.

    ``not_before`` drops fixtures that have already kicked off. A coupon file
    is read hours after it is written, and a match in the past is not a bet at
    any price, however good its ``p_low`` looks. Pass ``None`` to keep the
    whole day, which is what a post-hoc review of yesterday wants.

    ``vetoes`` is bet-analyst's read (Faza 5e), applied by exact
    ``(event_id, market, line, direction)`` match. A row with no matching veto
    is unaffected -- an empty or absent list is the default healthy state, not
    a degraded one.

    ``market_context`` is optional and read for exactly one thing: whether the
    "Football Unlimited" entitlement was confirmed missing or erroring
    anywhere in the run (Faza 3bis.6). Absent, it stays silent -- the same
    "unknown is not degraded" rule ``vetoes`` follows.

    ``superbet_offer`` is the operator's own book. It changes the *order* of
    the file and never its arithmetic: a row Superbet actually prices at or
    above ``min_acceptable_odds`` is ranked above one it does not, because that
    is the difference between a bet and a target. Rows the book does not carry
    are kept and labelled rather than dropped -- "Superbet has no 4.5 line for
    shots on target" is the single most useful sentence this pipeline can
    print on a day like 2026-08-31, and dropping those rows would delete it.
    Absent, every superbet_* field stays None and the file is byte-identical
    to the pre-Superbet one.

    ``require_superbet_value`` narrows the file to only what the book will
    actually pay for. Off by default and deliberately so: on a normal day it
    empties the file, and "no coupon" is strictly less information than "a
    coupon in which every row is labelled unbettable and says why".
    """
    events = {e.event_id: e for e in (event_list.events if event_list else [])}
    superbet_events = {
        offer.event_id: offer
        for offer in (superbet_offer.events if superbet_offer else [])
        if offer.event_id
    }

    def superbet_for(
        row: StatsSheetRow, minimum: float | None
    ) -> dict[str, object]:
        """Superbet's answer for one row, in the shape CouponSingle wants.

        Returns an empty dict when no offer artifact was passed, so the fields
        stay None and a pre-Superbet coupon is reproduced exactly.
        """
        if superbet_offer is None:
            return {}
        availability, exact, near_line, near_price = lookup_line(
            superbet_events.get(row.event_id),
            market=row.market,
            line=row.line,
            direction=row.direction,
            team_name=row.team_name,
        )
        verdict: str | None = None
        surplus: float | None = None
        if availability == "OFFERED" and exact is not None and minimum is not None:
            surplus = round(exact.price - minimum, 4)
            verdict = "VALUE" if exact.price >= minimum else "PRICED_BELOW_THRESHOLD"
        elif availability != "OFFERED":
            verdict = availability
        return {
            "superbet_availability": availability,
            "superbet_verdict": verdict,
            "superbet_price": exact.price if exact else None,
            "superbet_surplus": surplus,
            "superbet_nearest_line": near_line,
            "superbet_nearest_price": near_price,
        }

    veto_by_key: dict[tuple[str, str, float, str], AnalystVeto] = {
        (v.event_id, v.market, v.line, v.direction): v for v in (vetoes or [])
    }
    applied_vetoes: list[str] = []

    def identity(event_id: str) -> tuple[str, str, str]:
        event = events.get(event_id)
        if event is None:
            # The sheet alone cannot name a fixture; saying so beats printing a
            # hash at a human.
            return (f"[nieznany mecz {event_id[:12]}]", "", "")
        if event.sport == "tennis":
            match = f"{event.player_one or '?'} – {event.player_two or '?'}"
        else:
            match = f"{event.home_team or '?'} – {event.away_team or '?'}"
        return match, event.competition, event.start_time

    def fixture_key(event_id: str) -> tuple:
        """What real-world match this row is about, independent of event_id.

        Two dossiers can describe one fixture: discovery merges on names, and
        two feeds that spell a club differently produce two events. DISCOVER
        now merges far more of them, but the coupon is the artifact somebody
        *bets from*, so it does not rely on that. On 2026-08-28 a surviving
        pair put Nautico - Athletic Club on the list twice, same market, same
        line, same direction, at two different ranks -- an operator working
        down the file would have staked one bet twice while believing he was
        diversifying.

        Keyed on kickoff plus the two participants, order-insensitive and
        alias-resolved, because that is what identifies a match when the ids
        disagree. An event the sheet cannot name falls back to its event_id,
        which is no worse than today.
        """
        event = events.get(event_id)
        if event is None:
            return ("unknown", event_id)
        if event.sport == "tennis":
            sides = (event.player_one or "", event.player_two or "")
        else:
            sides = (event.home_team or "", event.away_team or "")
        names = tuple(sorted(
            normalize_team_name(resolve_team_alias(name)) for name in sides
        ))
        return (event.sport, event.start_time, names)

    excluded: dict[str, int] = {}

    def exclude(reason: str) -> None:
        excluded[reason] = excluded.get(reason, 0) + 1

    # --- singles ----------------------------------------------------------
    candidates: list[tuple[StatsSheetRow, str]] = []
    for row in stats_sheet.rows:
        tier: Tier = tier_for_row(row)
        veto = veto_by_key.get((row.event_id, row.market, row.line, row.direction))
        # DOWNGRADE is applied before the tier gate below, not after: a CALL
        # the analyst steps to WEAK is excluded by that same check, exactly
        # like a context flag's downgrade would be -- no second exclusion path
        # needed for it.
        if veto is not None and veto.action == "DOWNGRADE":
            new_tier = step_tier_down(tier)
            applied_vetoes.append(
                f"DOWNGRADE analityka: {row.market} {row.line} {row.direction} "
                f"({row.event_id[:12]}) {tier}→{new_tier} — {veto.reason}"
            )
            tier = new_tier
        if tier in ("WEAK", "DROP"):
            exclude(f"tier_{tier.lower()}")
            continue
        if veto is not None and veto.action == "VETO":
            exclude("analyst_veto")
            applied_vetoes.append(
                f"WETO analityka: {row.market} {row.line} {row.direction} "
                f"({row.event_id[:12]}) — {veto.reason}"
            )
            continue
        if row.p_low < min_p_low:
            exclude("p_low_below_threshold")
            continue
        # Faza 5d: youth and reserve/friendly fixtures stay on the full stats
        # sheet but never reach the coupon -- their stats describe a slate
        # nobody is pricing. An unmapped competition is left alone, never
        # guessed at (see competition_tier's own docstring).
        event = events.get(row.event_id)
        if event is not None and competition_tier(event.competition) in ("YOUTH", "FRIENDLY"):
            exclude("competition_youth_or_friendly")
            continue
        candidates.append((row, tier))

    # A fixture contributes at most one single per market family, so one match
    # with a strong corners read cannot occupy six rows of the file at four
    # different lines -- they are the same read, and only the best line of it is
    # a distinct bet.
    seen: set[tuple[tuple, str, str | None]] = set()
    singles: list[CouponSingle] = []

    def _append_singles(ordered: list[tuple[StatsSheetRow, str]]) -> None:
        for row, tier in ordered:
            if require_superbet_value:
                probe = superbet_for(
                    row, round((1.0 / row.p_low) * {"CALL": 1.05, "LEAN": 1.10}[tier], 4)
                )
                if probe.get("superbet_verdict") != "VALUE":
                    exclude("superbet_not_value")
                    continue
            key = (fixture_key(row.event_id), row.market, _subject(row))
            if key in seen:
                exclude("duplicate_market_for_event")
                continue
            seen.add(key)
            match, competition, kickoff = identity(row.event_id)
            # Checked before the max_singles slot is spent: a started match
            # must not push a bettable one off the end of the list.
            if _kickoff_passed(kickoff, not_before):
                exclude("kickoff_passed")
                continue
            if len(singles) >= max_singles:
                exclude("over_max_singles")
                continue
            fair = 1.0 / row.p_low
            margin = {"CALL": 1.05, "LEAN": 1.10}[tier]
            minimum = round(fair * margin, 4)
            singles.append(
                CouponSingle(
                    rank=len(singles) + 1,
                    event_id=row.event_id,
                    match=match,
                    competition=competition,
                    kickoff=kickoff,
                    sport=row.sport,
                    market=row.market,
                    market_label=market_label(row.market),
                    line=row.line,
                    direction=row.direction,
                    subject=_subject(row),
                    tier=tier,
                    p_low=row.p_low,
                    hit_rate=row.hit_rate,
                    hits=row.hits,
                    sample_size=row.sample_size,
                    cross_provider_agreement=row.cross_provider_agreement,
                    fair_odds=round(fair, 4),
                    min_acceptable_odds=minimum,
                    market_verdict=row.market_signal.verdict if row.market_signal else None,
                    market_price=row.market_signal.market_price if row.market_signal else None,
                    market_bookmaker=(
                        row.market_signal.market_bookmaker if row.market_signal else None
                    ),
                    tipster=_tipster_summary(row),
                    caveats=_caveats(row),
                    edge=round(_edge(row), 4) if _has_market_reference(row) else None,
                    **superbet_for(row, minimum),
                )
            )

    # Three rankings now, never merged into one sorted list.
    #
    # Group one is new (SUPERBET, 2026-08-31) and outranks both of the others:
    # a row the operator's own book prices at or above its minimum acceptable
    # odds is a bet he can place at a price worth placing it at. Everything
    # below is a target he still has to go and check, and on a bad day none of
    # it is takeable at all -- which is exactly what the 2026-08-31 night slate
    # turned out to be, with three of 505 comparable rows clearing the bar.
    #
    # Groups two and three are the Faza 5c split, unchanged: a row this sheet
    # can price against bzzoiro's market reference outranks one it cannot,
    # however high the second row's own p_low climbs. max_singles is one shared
    # budget, spent in this order.
    def _superbet_surplus(pair: tuple[StatsSheetRow, str]) -> float | None:
        row, tier = pair
        info = superbet_for(row, round((1.0 / row.p_low) * {"CALL": 1.05, "LEAN": 1.10}[tier], 4))
        return info.get("superbet_surplus") if info.get("superbet_verdict") == "VALUE" else None

    superbet_value = [c for c in candidates if _superbet_surplus(c) is not None]
    value_ids = {id(c) for c in superbet_value}
    rest = [c for c in candidates if id(c) not in value_ids]
    with_reference = [c for c in rest if _has_market_reference(c[0])]
    without_reference = [c for c in rest if not _has_market_reference(c[0])]
    _append_singles(
        sorted(
            superbet_value,
            key=lambda pair: (-(_superbet_surplus(pair) or 0.0), -pair[0].p_low, pair[0].event_id),
        )
    )
    _append_singles(
        sorted(with_reference, key=lambda pair: (-_edge(pair[0]), -pair[0].p_low, pair[0].event_id))
    )
    _append_singles(
        sorted(
            without_reference,
            key=lambda pair: (_is_trivial_under(pair[0]), -pair[0].p_low, pair[0].event_id),
        )
    )

    # --- slips ------------------------------------------------------------
    slips: list[CouponSlip] = []
    for event_id in {row.event_id for row in stats_sheet.rows}:
        draft = draft_legs(stats_sheet, event_id, max_legs=max_legs)
        # A one-leg "slip" is a single wearing a different hat, and printing it
        # in both sections would double-count the same read.
        if len(draft.legs) < 2:
            continue
        if superbet_offer is not None:
            # Same lookup as the singles, so a leg and a single on the same
            # (market, line, direction) can never disagree about whether the
            # book carries it.
            event_superbet = superbet_events.get(event_id)
            annotated = []
            for leg in draft.legs:
                availability, exact, near_line, _ = lookup_line(
                    event_superbet,
                    market=leg.market,
                    line=leg.line,
                    direction=leg.direction,
                    team_name=leg.team_name,
                )
                annotated.append(
                    leg.model_copy(
                        update={
                            "superbet_availability": availability,
                            "superbet_price": exact.price if exact else None,
                            "superbet_nearest_line": near_line,
                        }
                    )
                )
            draft = draft.model_copy(update={"legs": annotated})
        match, competition, kickoff = identity(event_id)
        if _kickoff_passed(kickoff, not_before):
            exclude("kickoff_passed")
            continue
        if competition_tier(competition) in ("YOUTH", "FRIENDLY"):
            exclude("competition_youth_or_friendly")
            continue
        slips.append(
            CouponSlip(
                rank=0,
                event_id=event_id,
                match=match,
                competition=competition,
                kickoff=kickoff,
                draft=draft,
                weakest_leg_p_low=min(leg.p_low for leg in draft.legs),
            )
        )

    slips.sort(key=lambda s: (-s.weakest_leg_p_low, s.event_id))
    slips = [s.model_copy(update={"rank": i + 1}) for i, s in enumerate(slips[:max_slips])]

    notes = []
    entitlement_note = _entitlement_note(market_context)
    if entitlement_note is not None:
        notes.append(entitlement_note)
    notes += [
        "Kurs łączny NIE jest liczony i nie może być — nogi w jednym meczu są "
        "skorelowane dodatnio, więc iloczyn zaniża prawdopodobieństwo kuponu. "
        "Kurs łączny odczytujesz z ekranu Superbetu.",
        "Pewność to dolna granica Wilsona 95% (p_low), nie surowy hit rate. "
        "sample_size liczy mecze, nie obserwacje: drużyna gra najwyżej jeden "
        "mecz dziennie, więc powtórzenia między obiema drużynami, h2h i "
        "dostawcami są zwijane do jednego meczu. Potwierdzenie przez drugiego "
        "dostawcę nie podnosi już pewności — mówi tylko, że wartość jest "
        "wiarygodna. Obserwacje bez czytelnej daty nie dają się przypisać do "
        "meczu i zostają osobno, więc próba może być w rzadkich przypadkach "
        "zawyżona. To podłoga na dowody, nie gwarancja.",
        "Brak stawek i brak EV — celowo. Typ poniżej minimalnego kursu nie jest typem.",
    ]
    if excluded.get("kickoff_passed"):
        notes.append(
            f"Odrzucono {excluded['kickoff_passed']} pozycji, których mecz już "
            f"się rozpoczął (odcięcie {not_before:%H:%M} UTC). Mecz w przeszłości "
            "nie jest typem, choćby jego p_low wyglądało najlepiej w pliku."
        )
    if any(_is_trivial_under(r) for r, _ in candidates):
        notes.append(
            "Niskie linie UNDER (≤1.5) zepchnięto na koniec listy singli: przy "
            "10/10 wychodzą wysoko w p_low, ale rynek wycenia je ~1.05."
        )
    # Superbet coverage, said in the header rather than left to be inferred
    # from a column of dashes. The order is deliberate: what is takeable first,
    # then the reason most of it is not.
    if superbet_offer is not None:
        value = [s for s in singles if s.superbet_verdict == "VALUE"]
        no_line = [s for s in singles if s.superbet_availability == "LINE_NOT_OFFERED"]
        # Every single lands in exactly one bucket, and the buckets are printed
        # in full. A note that accounts for 3 of 15 rows and leaves 12
        # unexplained reads as a bug in the count rather than as a fact about
        # the day -- which is what happened the first time this note shipped.
        buckets = {
            "wystawionych taniej niż próg": "PRICED_BELOW_THRESHOLD",
            "z rynkiem, ale bez naszej linii": "LINE_NOT_OFFERED",
            "bez tego rynku u bukmachera": "MARKET_NOT_OFFERED",
            "których mecz już trwa (oferta zdjęta)": "OFFER_EMPTY",
            "bez meczu w ofercie": "EVENT_NOT_MATCHED",
            "zablokowanych": "SUSPENDED",
            "których nie czytamy (propy zawodników)": "SCOPE_NOT_SUPPORTED",
        }
        counted = {
            label: sum(
                1 for s in singles
                if (s.superbet_verdict == key or s.superbet_availability == key)
                and s.superbet_verdict != "VALUE"
            )
            for label, key in buckets.items()
        }
        breakdown = ", ".join(
            f"{count} {label}" for label, count in counted.items() if count
        )
        notes.append(
            f"Superbet: {len(value)} z {len(singles)} singli osiąga swój minimalny "
            f"kurs na ekranie operatora"
            + (f"; pozostałe: {breakdown}" if breakdown else "")
            + f". Ceny zdjęte {superbet_offer.generated_at[:16]}Z z publicznej "
            "oferty superbet.pl — sprawdź kurs na ekranie, bo się rusza."
        )
        if no_line:
            worst = sorted(
                {(s.market, s.line, s.superbet_nearest_line) for s in no_line
                 if s.superbet_nearest_line is not None}
            )[:6]
            if worst:
                pairs = ", ".join(
                    f"{market} {line}→{nearest}" for market, line, nearest in worst
                )
                notes.append(
                    "Linie, których Superbet nie wystawia (nasza→najbliższa jego): "
                    f"{pairs}. To nie jest zły kurs, to brak rynku — takiego typu "
                    "nie postawisz."
                )
        if singles and not value:
            notes.append(
                "Żaden single nie osiąga minimalnego kursu na Superbecie. To jest "
                "odpowiedź o dniu, nie awaria — wysokie p_low nie jest przewagą, "
                "jeśli rynek stoi wyżej niż ono."
            )
    # Every veto/downgrade the analyst applied, with its reason -- visible in
    # the coupon file's header, not just as an exclusion count (Faza 5e).
    notes.extend(applied_vetoes)

    return CouponSet(
        run_id=stats_sheet.run_id,
        date=stats_sheet.date,
        generated_at=_now_iso(),
        singles=singles,
        slips=slips,
        rows_considered=len(stats_sheet.rows),
        events_considered=len({row.event_id for row in stats_sheet.rows}),
        not_before=not_before.isoformat() if not_before else None,
        excluded=dict(sorted(excluded.items())),
        notes=notes,
    )
