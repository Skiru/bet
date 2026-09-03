"""Assemble one betting day's stats sheet into singles and Bet Builder slips.

This is the last computation in the chain, and it is code rather than an agent's
prose for the same reason ``wilson_lower_bound`` is: the numbers it produces are
thresholds a human bets money against. A threshold free-handed in a report
cannot be audited, reproduced, or caught when it slips by a decimal place.

What it does **not** do, and cannot be made to
----------------------------------------------
* **No combined price.** ``BetBuilderDraft.combined_price`` is still typed
  ``None``: no endpoint serves Superbet's Bet Builder price, and it cannot be
  derived from the legs because the book's combination margin is not
  observable from them. The operator reads it off the screen.

  What *is* computed, since 2026-09-03, is the **bar** for that price --
  ``min_acceptable_combined_odds``. The reason it could not be computed before
  was a claim about correlation that has since been measured and did not hold:
  over 12,555 same-fixture leg pairs settled against real results, legs land
  together 1.009x as often as independence implies (95% CI [1.005, 1.013]),
  and 1.006x for non-nested markets. See ``bet_builder_draft`` for the table.
  A coefficient that small is a coefficient, not a reason to refuse the
  arithmetic.
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

**Ranking and the price bar are two different questions, and since 2026-09-03
they are answered by two different numbers.** ``p_low`` still orders the file:
between two rows it is the honest statement of which is better evidenced, and
a lower bound is the right tool for that. It is the wrong tool for dividing
into 1 to get a price, because it is wrong by +16 to +22pp in one direction on
every row -- so ``bar_basis`` now defaults to ``p_central``, which measures
-0.000 against realised results. See ``bet_builder_draft.BAR_BASES``.
"""
from __future__ import annotations

import json
import math
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from pydantic import Field

from bet.simple_stats.bet_builder_draft import (
    required_odds,
    TIER_MARGIN,
    AnalystVeto,
    BetBuilderDraft,
    Tier,
    VetoIndex,
    draft_legs,
    is_trivial_under,
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
from bet.simple_stats.superbet_offer import lookup_line, player_alias_index
from bet.simple_stats.tipster_consensus import TipsterConsensus
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
    "player_tackles": "odbiory zawodnika",
    "player_assists": "asysty zawodnika",
    "player_offsides": "spalone zawodnika",
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

# How far above the operator's own book this sheet may claim to be before the
# row stops being a lean and starts being a question about the sample.
#
# The gate it guards is not symmetric, and that asymmetry is the point. p_low is
# a *lower* bound, so sitting below the market is expected and harmless. Sitting
# far above it means one of two things: an edge the book has not priced, or a
# sample that is not measuring this fixture -- and the 2026-09-01 file is a
# clean experiment on which of those is more common. The one row where the gap
# was largest (Superbet 2.27 against a min of 1.38) was the ATP best-of-five
# tie priced off best-of-three data, and it was ranked first precisely because
# it disagreed most.
#
# 0.25, and the number changed meaning before it changed value -- see
# ``disagreement``, which now measures ``p_central`` rather than ``p_low``.
#
# Against ``p_low`` no threshold could work, and 2026-09-01 is the arithmetic
# proof rather than the anecdote. VALUE means ``price >= margin/p_low``, which
# devigs to ``p_low - implied >= p_low*(1 - 1/(margin*overround))`` -- +0.081 for
# a LEAN at p_low 0.50, +0.130 at 0.80. Every VALUE row therefore disagreed with
# the book by at least that much *by construction*, whatever its sample held. A
# threshold above the band (0.15, which is what shipped) is a no-op; one below
# it (0.08, which is where the losses appear to point) is a blanket ban on ever
# outbidding the book. There is no third setting. The gate was measuring our own
# conservatism.
#
# Against ``p_central`` it measures the disagreement itself, and the run-wide
# distribution says so: over that day's 3928 two-sided rows the median gap is
# -0.000 -- the sheet and the devigged book agree, on average, which is the
# calibration check the old number could never have passed. p75 is +0.081, p90
# +0.173, p95 +0.239.
#
# 0.25 is that p95, chosen from the distribution and not from the casualties.
# What it does to the casualties is the check, not the input: the seven singles
# that day's file admitted came out at +0.504, +0.487, +0.418, +0.357, +0.316,
# +0.263 and +0.129, and the eight it rejected at +0.256 or less. So 0.25 flags
# six of the seven losers and three rejected rows that were already unbettable
# on price -- and the seventh, Lincoln, is caught upstream by
# ``count_model_bound`` instead, which is the right place for it: at ladder
# ratio 1.135 it agreed with the book about where the market sat and was simply
# priced too short.
#
# **What this threshold does changed on 2026-09-02: it annotates, it no longer
# demotes.** The sentence above -- flagging a good row costs it its rank -- was
# true and the trade it described was not. A row whose floor sits far above the
# book's devigged price at its own rung is not a broken sample; that gap *is*
# what a bet worth taking looks like from the inside. Demoting on it, against a
# 15-single cap, deletes value from the file in the name of caution: it took
# the day's one real row (WTA aces_total 5.5 OVER at 2.07 vs a 1.8146 floor)
# off the end. The *centre* disagreement -- MAX_LADDER_SIGMA below -- is the
# one with settled evidence behind it and the one that still demotes.
MAX_MARKET_DISAGREEMENT = 0.25

# How far the sample's own centre may sit from the centre the book's ladder
# implies before the sample stops being a description of this fixture --
# measured in the sample's own standard deviations.
#
# This is the check 2026-09-01 needed and did not have. The pipeline downloads
# Superbet's whole ladder and reads it only one rung at a time, to ask "is this
# price above my threshold". Read *whole*, the ladder is a devigged
# distribution, and it contradicted the losing samples outright:
#
#     Sheffield United corners   mean  2.80  ladder median  5.76   z -1.77  ->  5
#     Birmingham shots           mean  8.20  ladder median 13.18   z -1.74  -> 16
#     Preston shots on target    mean  2.00  ladder median  3.88   z -1.33  ->  4
#     Torino/Monza corners       mean  6.33  ladder median  8.60   z -0.90  -> 16
#     Lincoln shots on target    mean  9.60  ladder median  8.46   z +0.37  ->  3
#
# The last column is what the match returned. In the four losing UNDERs the
# book's median was the better estimate and our sample was the one betting
# against it. No internal statistic can catch that: those samples are
# self-consistent, tight and unanimous. They are simply not measuring the
# quantity being priced -- venue, competition and five observations of it will
# do that.
#
# **In standard deviations and not as a ratio.** The first version of this gate
# compared ``mean/ladder_median`` against a 0.75-1.35 band, and that is the
# wrong shape: it fired on 29.6% of the day's 382 comparable samples, but
# unevenly -- 53% of ``goals_for`` and 0% of ``corners_total``, because a
# 0.3-goal gap is a third of a half-time total and a thirtieth of a shots
# total. It was measuring the size of the mean, not the size of the
# disagreement. Divided by ``row.dispersion`` the median |z| is 0.13-0.58 in
# every market on the board, so one threshold means the same thing everywhere.
#
# 1.25 sits near p97 of that distribution (p50 0.267, p95 0.954, p99 1.738) and
# fires on 3.1% of samples. It takes Sheffield, Birmingham and Preston.
# Torino and Lincoln are left to ``count_model_bound``, which is the right
# layer for them: Lincoln at z +0.37 *agreed* with the book about where the
# market sat and was simply priced too short, and a gate that flagged it would
# be punishing the sample for being correct.
MAX_LADDER_SIGMA = 1.25

# A ladder has to have at least two devigged rungs straddling even money
# before it implies a median at all. One rung gives a probability, not a
# location; a ladder entirely on one side of 0.5 puts the median outside the
# range the book posted, where interpolating it would be invention.
_LADDER_MIN_RUNGS = 2

# What ``ladder_sigma`` reports for a zero-dispersion sample whose mean is not
# the ladder's median: the true value is unbounded, but Infinity is not strict
# JSON and every value past MAX_LADDER_SIGMA reads the same to the gate. Large
# enough that no real sample reaches it (2026-09-01's worst was under 2σ).
_LADDER_SIGMA_SATURATED = 99.0


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
    # Whether ``subject`` names a team or a person. ``_subject`` returns
    # ``player_name or team_name`` and the two are indistinguishable in the
    # artifact, so every machine consumer had to re-derive it from the market
    # taxonomy -- ``*_for`` is a team, ``player_*`` is a person, everything
    # else names nobody. ``settle.py`` needs exactly this distinction and
    # getting it backwards settles a player's shots against his team's, so it
    # is stated here rather than inferred there.
    subject_kind: Literal["team", "player"] | None = None
    # The provider's own id for a player subject, so the artifact names one
    # human. ``subject`` is a display name and a squad can contain two of
    # them -- see ``_ambiguous_player_names``. None for a team, whose name is
    # its identity in this pipeline.
    subject_id: str | None = None
    tier: str
    p_low: float
    # The sheet's own estimate with no bound and no margin in it, carried so
    # ``market_disagreement`` can be checked by hand: the gap is exactly this
    # minus the devigged Superbet price at the same rung. Without it the
    # operator reads a gap he cannot reconstruct, which is how the old
    # p_low-based version of that number went four days unquestioned.
    p_central: float | None = None
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
    # p_low minus Superbet's own devigged probability for this exact outcome,
    # set when both sides of the line are on the operator's screen. Different
    # from ``edge`` on purpose: ``edge`` compares against a reference book out
    # of bzzoiro's ~88 and exists for only two markets, this compares against
    # the book the operator actually bets into and works on every market it
    # prices both ways.
    #
    # Positive is not automatically good. Past MAX_MARKET_DISAGREEMENT it is
    # the reason the row is *not* at the top of the file.
    market_disagreement: float | None = None
    # ``(mean - ladder_median) / dispersion``: how far the sample's own centre
    # sits from the centre the book's whole devigged ladder implies, in the
    # sample's own standard deviations. 0.0 is agreement about where this
    # market sits, and the sign says which way we lean. The disagreement that
    # matters is here rather than in ``market_disagreement``, which compares
    # one rung's price. Reported even when inside the band, because a reader
    # checking a row needs to see the number that cleared it, not only the
    # ones that did not.
    #
    # None when the book posted fewer than two two-sided rungs for the sample,
    # or a ladder that never crosses even money -- then no median can be read
    # and the gate is inert for that row.
    ladder_sigma: float | None = None
    # True when ``market_disagreement`` exceeded the threshold. Such a row is
    # kept and ranked last rather than dropped: "we and the book are far apart
    # here" is information the operator should have, and deleting it would hide
    # the one class of row most worth a second look.
    needs_review: bool = False


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
    # What the tipster community picked repeatedly, as an appendix. Typed as a
    # separate model that carries no probability and no price, and nothing in
    # this module reads it -- it cannot reach ranking, tiering or the value
    # test. See ``tipster_consensus``. None means the artifact was not passed.
    tipster_consensus: TipsterConsensus | None = None


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


def _subject_key(row: StatsSheetRow) -> tuple[str | None, str | None]:
    """Whose line this is, as an *identity* rather than as a display name.

    The one-per-market-per-fixture rule dedupes on this, and it used to dedupe
    on ``_subject`` -- the display name. Juventude fielded two players called
    Marcos Paulo on 2026-09-01 (bzzoiro ids 187 and 17556, ten appearances
    each, means of 1.3 and 0.8 shots), so their rows were indistinguishable:
    the second was counted as ``duplicate_market_for_event`` and dropped, and
    which of the two survived depended on the ranking order. 46 rows on that
    slate collided this way.

    Teams keep the name, because a team name *is* its identity here -- the
    dossier has exactly two of them and ``_side_for_team`` matches on the name.
    """
    if row.player_id or row.player_name:
        return (row.player_id, row.player_name)
    return (None, row.team_name)


def _ambiguous_player_names(rows: list[StatsSheetRow]) -> set[tuple[str, str]]:
    """``{(event_id, player_name)}`` naming more than one person.

    A bet the operator cannot identify is not a bet. Superbet's ladder is
    keyed by *its* spelling of a player and ``player_alias_index`` resolves
    ours to theirs by name, so with two Marcos Paulos in one squad both of our
    rows join to whichever single line Superbet posted -- one of them is
    certainly being priced against the other's market. That is the
    Benoit-Paire failure shape: real numbers, real table, wrong human.

    So the rows are kept on the sheet, where the analyst can see them, and
    refused a place in the coupon.
    """
    by_name: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        if not row.player_name:
            continue
        by_name.setdefault((row.event_id, row.player_name), set()).add(row.player_id or "")
    return {key for key, ids in by_name.items() if len(ids) > 1}


def _subject_kind(row: StatsSheetRow) -> str | None:
    """Whether ``_subject`` returned a person or a team.

    Read off the row's own identity fields, not off the market name: a market
    taxonomy is a naming convention and this is a fact the row carries.
    """
    if row.player_name:
        return "player"
    if row.team_name:
        return "team"
    return None


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


def required_price(row: StatsSheetRow, tier: str, *, basis: str = "p_low") -> float:
    """``min_acceptable_odds`` for one row, in exactly one place.

    The arithmetic is ``1/p_low`` times the tier margin, rounded to four
    decimals -- and it used to be written out three separate times inside
    ``build_coupons``: once in the ``require_superbet_value`` probe, once in the
    body that fills ``CouponSingle.min_acceptable_odds``, and once in
    ``_superbet_surplus`` for the ranking. Three copies of the number the
    operator actually acts on, one of which decides the ordering and another of
    which is printed. They agreed; nothing made them agree.
    """
    return required_odds(row, tier, basis=basis)


def _edge(row: StatsSheetRow) -> float:
    """This row's own probability minus the market's, for this exact row.

    Measured on ``p_central`` and not ``p_low``, for the same reason
    ``disagreement`` is (see its docstring). ``market_implied_probability`` is
    a *devigged* number -- a central estimate -- and ``p_low`` is a lower
    bound, so subtracting one from the other compared two different kinds of
    quantity and called the remainder an edge. It is the ranking key for the
    whole second group of singles and it is printed in the coupon file as
    "Przewaga", so the mismatch reached the operator twice over: Torino/Monza's
    corners went out on 2026-09-01 labelled +9.7pp when this row's actual
    disagreement with the devigged market was +31.6pp.

    Understating it is not the safe direction. The number is read as "how much
    of an edge is here", and a floor-versus-centre subtraction makes a large
    disagreement look like a small one -- which is the reading that gets a
    broken sample staked.

    Ranking by it descending is legitimate *because* it is now comparable and
    bounded: ``over_disagreement`` removes everything past
    ``MAX_MARKET_DISAGREEMENT`` first, and inside that band the run-wide median
    gap between ``p_central`` and the devigged price is -0.000, so the sheet is
    not systematically on either side of the market. Ranking an *unbounded*
    disagreement descending is what put six losers at the top of that day's
    file.

    Falls back to ``p_low`` on a row written before ``p_central`` existed,
    which reproduces the old number rather than inventing one. Never called on
    a row without a market reference; see ``_has_market_reference``.
    """
    ours = row.p_central if row.p_central is not None else row.p_low
    return ours - row.market_signal.market_implied_probability


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
    if row.hits >= row.sample_size and row.sample_size > 0:
        # No miss in the sample, so the *Wilson* half of p_low is a function of
        # n alone. It used to say that p_low was therefore identical on every
        # line above the sample's maximum and that only the price could rank
        # the rungs -- which was true, was the 2026-09-01 defect, and is no
        # longer true: ``count_model_bound`` caps Wilson with the line's own
        # distance from the sample, so the rungs are ordered again. What
        # survives is the narrower and still important warning: a sample with
        # no miss reports no observed failure rate, so everything separating
        # these rungs is now model rather than measurement.
        notes.append(
            f"brak pudła w próbie ({row.hits}/{row.sample_size}) — próba nie "
            "pokazuje ani jednej porażki, więc szczeble tego rynku rozdziela "
            "rozkład dopasowany do próby, nie zmierzony odsetek trafień"
        )
    if is_trivial_under(row):
        notes.append("niska linia UNDER — łatwa do trafienia i zwykle wyceniana ~1.05")
    return notes


def _veto_scope(veto: AnalystVeto) -> str:
    """How wide this veto is, in the coupon file's own words.

    A market-wide veto printed as "cards_total 4.5 UNDER" would read as though
    the analyst had struck one line, which is the misreading that let a second
    line of the same broken market ship as a Bet Builder leg.
    """
    line = "wszystkie linie" if veto.line is None else f"{veto.line}"
    direction = veto.direction or "OVER+UNDER"
    return f"{veto.market} {line} {direction}"


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
    """Agreement on this row, or -- failing that -- presence on this fixture.

    The two are different claims and are written differently on purpose. "2/3"
    means three tipsters addressed *this bet* and two took this side. Nothing
    else in this cell ever reads as a ratio.

    A ratio is also the rare case. Tipsters price goals, corners and games; the
    rows that reach a coupon are per-team shots and corners, so the two land on
    the same row only by coincidence -- zero of fifteen singles on 2026-09-01.
    What is far from rare is a tipster having covered the fixture at all, which
    on the same day was true of nine of those fifteen. That is worth showing,
    and showing it as "mecz: 4" rather than as a fraction is what stops it being
    mistaken for agreement the row does not have.
    """
    column = row.tipster
    if column is None:
        return None
    if column.verdict != "NO_COVERAGE":
        cell = f"{column.agree}/{column.agree + column.oppose}"
        # A ratio says how many agreed. It does not say whether the ones who
        # agreed have ever been right, and an unqualified "2/3" is exactly what
        # lets a tipster on 25% from eight bets read as support. So when the
        # backers published a record, the floor on it joins the cell as
        # "2/3 · rek. 61%", and a record that does not clear a coin flip is
        # named rather than quietly averaged in.
        #
        # The opposing side gets the same treatment under a "przeciw" label,
        # and only when nobody agreed. A credible tipster arguing against the
        # row is news of the same size as one arguing for it; on a split cell
        # the agreement is what the row is claiming, so that is what the
        # record qualifies.
        parts = []
        if column.agree_record_low is not None:
            parts.append(f"rek. {column.agree_record_low * 100:.0f}%")
        if column.agree_unproven:
            parts.append(f"{column.agree_unproven} bez rekordu")
        if not parts and column.agree == 0:
            if column.oppose_record_low is not None:
                parts.append(f"przeciw rek. {column.oppose_record_low * 100:.0f}%")
            if column.oppose_unproven:
                parts.append(f"przeciw: {column.oppose_unproven} bez rekordu")
        return " · ".join([cell, *parts])
    if not column.considered:
        return None
    # Nobody addressed this bet. Say who was there and, if the fixture drew a
    # 1X2 or BTTS lean, what it was -- a different market, never this one.
    lean = " ".join(f"{side} {count}" for side, count in column.lean.items())
    return f"mecz: {column.considered}" + (f" · {lean}" if lean else "")


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
    bar_basis: str = "p_central",
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
    # Superbet spells players its own way, so a prop row cannot find its price
    # without this. Built from the sheet's own player names -- the exact set the
    # lookups below will ask about -- and shared by singles and slip legs so the
    # two can never resolve the same prop to different humans.
    our_players: dict[str, set[str]] = {}
    for sheet_row in stats_sheet.rows:
        if sheet_row.player_name:
            our_players.setdefault(sheet_row.event_id, set()).add(sheet_row.player_name)
    player_aliases = (
        player_alias_index(superbet_offer, our_players) if superbet_offer else {}
    )

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
            player_name=row.player_name,
            player_aliases=player_aliases.get(row.event_id, {}),
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

    def superbet_implied(row: StatsSheetRow) -> float | None:
        """Superbet's own probability for this outcome, margin removed.

        Both sides of the line, or nothing. ``1/price`` alone is not the book's
        probability -- it carries the whole overround, which on these markets
        runs 8-9% -- and using it would understate every disagreement by about
        that much, in the direction that lets a bad row through the gate below.
        Two prices give the pair's overround exactly, and dividing it out is
        arithmetic rather than an assumption.

        Returns None when the opposite side is not posted, which is common on
        one-way markets. None disables the disagreement gate for that row: we
        cannot say the book disagrees with us if we cannot read what it thinks.
        """
        if superbet_offer is None:
            return None
        event_offer = superbet_events.get(row.event_id)
        aliases = player_aliases.get(row.event_id, {})
        opposite = "UNDER" if row.direction == "OVER" else "OVER"
        prices: list[float] = []
        for direction in (row.direction, opposite):
            availability, exact, _, _ = lookup_line(
                event_offer,
                market=row.market,
                line=row.line,
                direction=direction,
                team_name=row.team_name,
                player_name=row.player_name,
                player_aliases=aliases,
            )
            if availability != "OFFERED" or exact is None or exact.price <= 1.0:
                return None
            prices.append(exact.price)
        overround = sum(1.0 / price for price in prices)
        if overround <= 0:
            return None
        return (1.0 / prices[0]) / overround

    def disagreement(row: StatsSheetRow) -> float | None:
        """How far this row's own opinion sits above the operator's book.

        Measured against ``p_central`` and not ``p_low``. The floor is a lower
        bound and ``min_acceptable_odds`` stacks a 5-10% tier margin on top of
        it, so ``p_low - implied`` is dominated by our own conservatism: it is
        pinned above +0.08 for *every* row that clears its price, whatever the
        sample says. A gate on that number can be a no-op or a blanket ban and
        nothing in between, which is how 2026-09-01 shipped with the threshold
        at 0.15 -- above six of its seven losers -- and looked calibrated.

        ``p_central`` carries no margin and no bound, so the difference is a
        disagreement about the outcome and nothing else. Rows written before
        the field existed fall back to ``p_low``, which reproduces the old
        number exactly rather than inventing one.
        """
        implied = superbet_implied(row)
        if implied is None:
            return None
        ours = row.p_central if row.p_central is not None else row.p_low
        return round(ours - implied, 4)

    # Every line **the book posted** for one sample, taken from the offer and
    # deliberately not from the sheet.
    #
    # The sheet is the wrong source and would make the check unreliable in
    # exactly the cases it is for: ``select_lines`` trims an offer-driven
    # ladder to ``MAX_OFFERED_LINES_PER_SAMPLE`` rungs closest to the sample's
    # own median, so a sample sitting far from the book's centre -- the defect
    # being hunted -- is the one whose sheet rows cover least of the ladder.
    # Reading the sheet would have let the gate go quietly inert on the worst
    # rows and left no trace that it had.
    #
    # Keyed on the offer's own spelling of a player, which is what
    # ``lookup_line`` resolves ours to; team names are ours already.
    ladder_lines: dict[tuple, set[float]] = {}
    for event_offer in (superbet_offer.events if superbet_offer else []):
        if not event_offer.event_id:
            continue
        for offered in event_offer.lines:
            ladder_lines.setdefault(
                (event_offer.event_id, offered.market, offered.team_name,
                 offered.player_name),
                set(),
            ).add(offered.line)

    def _rungs_for(row: StatsSheetRow) -> set[float]:
        """Every line the book posted for this row's sample.

        A player row has to be looked up under *their* spelling: the alias map
        is ours-to-theirs, and the offer is filed under theirs.
        """
        their_name = row.player_name
        if their_name is not None:
            their_name = player_aliases.get(row.event_id, {}).get(their_name, their_name)
        return ladder_lines.get(
            (row.event_id, row.market, row.team_name, their_name), set()
        )

    _ladder_median_cache: dict[tuple, float | None] = {}

    def ladder_median(row: StatsSheetRow) -> float | None:
        """The median of the distribution Superbet's whole ladder implies.

        Each rung with both sides posted devigs to ``P(X < line)`` exactly as
        ``superbet_implied`` does for one line. Together they are a CDF sampled
        at the book's own half-points, and the median is where it crosses 0.5,
        linearly interpolated between the two rungs that straddle it.

        Interpolated and not fitted: a two-parameter fit would put a shape
        assumption between the operator and a number he is being asked to bet
        against, and the crossing point needs no shape. Linear interpolation
        over a half-point step is accurate to well inside the band it feeds.

        Returns None when the book posted too little to locate a median --
        fewer than two two-sided rungs, or a ladder that never crosses 0.5.
        None disables the check, on the same principle as ``superbet_implied``:
        not being able to read the book is not evidence against the sample.
        """
        key = (row.event_id, row.market, row.team_name, row.player_name)
        if key in _ladder_median_cache:
            return _ladder_median_cache[key]
        cdf: dict[float, float] = {}
        for line in sorted(_rungs_for(row)):
            prices: list[float] = []
            for direction in ("UNDER", "OVER"):
                availability, exact, _, _ = lookup_line(
                    superbet_events.get(row.event_id),
                    market=row.market,
                    line=line,
                    direction=direction,
                    team_name=row.team_name,
                    player_name=row.player_name,
                    player_aliases=player_aliases.get(row.event_id, {}),
                )
                if availability != "OFFERED" or exact is None or exact.price <= 1.0:
                    break
                prices.append(exact.price)
            if len(prices) == 2:
                overround = sum(1.0 / price for price in prices)
                if overround > 0:
                    cdf[line] = (1.0 / prices[0]) / overround
        result: float | None = None
        if len(cdf) >= _LADDER_MIN_RUNGS:
            rungs = sorted(cdf)
            for lower, upper in zip(rungs, rungs[1:]):
                below, above = cdf[lower], cdf[upper]
                if below < 0.5 <= above and above > below:
                    result = lower + (0.5 - below) / (above - below) * (upper - lower)
                    break
        _ladder_median_cache[key] = result
        return result

    def ladder_sigma(row: StatsSheetRow) -> float | None:
        """``(sample mean - ladder median) / dispersion``, signed.

        Signed rather than absolute because the direction is the diagnosis: a
        negative z is a sample that thinks this market runs colder than the
        book does, which is what every one of 2026-09-01's losing UNDERs was.

        A zero dispersion does not disable the check. The floor is
        ``sqrt(mean)``, so dispersion is 0 exactly when the sample is all
        zeros -- the provider-fabrication class from 2026-09-01 -- and such a
        sample sitting away from a readable ladder median is *infinitely* far
        from the book in its own units, not unreadable. Returning None here
        made the most broken sample possible the only one the gate could not
        touch, and it shipped at rank 1. Saturated to a finite value so the
        artifact stays strict JSON; anything past MAX_LADDER_SIGMA reads the
        same to the gate.
        """
        centre = ladder_median(row)
        if centre is None or row.mean is None:
            return None
        if not row.dispersion:
            if row.mean == centre:
                return 0.0
            return math.copysign(_LADDER_SIGMA_SATURATED, row.mean - centre)
        return round((row.mean - centre) / row.dispersion, 4)

    def off_ladder(row: StatsSheetRow) -> bool:
        """Whether the sample and the book disagree about *where* the
        distribution is, as opposed to how heavy its tail is.

        Only the first disagreement is disqualifying. A sample that agrees
        with the book about the centre and differs about the tail is the shape
        a real edge has; a sample whose centre is nearly two of its own
        standard deviations from the book's is describing another fixture,
        another venue or another competition, and its tail is not evidence
        about anything.
        """
        sigma = ladder_sigma(row)
        return sigma is not None and abs(sigma) > MAX_LADDER_SIGMA

    def over_disagreement(row: StatsSheetRow) -> bool:
        """Whether this row disagrees with the operator's own book too much to
        lead the file -- on the price of its line, or on where its market sits.

        **The saturation exemption is gone, and it is why 2026-09-01 lost.**
        It read: a row that has not missed once carries a ``p_low`` that
        depends only on ``n``, identical at every line above the sample's
        maximum -- Sheffield United's corners scored 0.565508505247919 at 4.5,
        5.5, 6.5 and 7.5 alike off a sample whose highest value was 4 -- so
        ``p_low - market`` tracked the price and nothing else, and the gate
        would have fired hardest on whichever rung paid best. All of that was
        true. The conclusion drawn from it was to stop gating those rows.

        What it should have been was to stop ``p_low`` being constant, because
        the constancy was the defect and the gate was the alarm. Exempting the
        saturated rows disabled the alarm on precisely the rows that had it:
        five of the seven singles that day were saturated, every one of them
        cleared the gate, and every one of them lost.

        ``p_low`` is now line-aware -- ``analyze.count_model_bound`` caps
        Wilson with a bound that reads the line's distance from the sample -- so
        a saturated row no longer carries the same number down the ladder and
        the gap means what the gate always assumed it meant. The exemption has
        nothing left to correct for.

        The ladder check is the second half, and it is independent. A row can
        sit within ``MAX_MARKET_DISAGREEMENT`` on its own rung and still be
        built on a sample whose centre is nowhere near the book's; four of that
        day's six losers were exactly that.
        """
        if off_ladder(row):
            return True
        gap = disagreement(row)
        return gap is not None and gap > MAX_MARKET_DISAGREEMENT

    veto_index = VetoIndex(vetoes)
    applied_vetoes: list[str] = []
    # One note per analyst *decision*, not per row it lands on. The sheet holds
    # several rows with the same (event_id, market, line, direction) -- that is
    # what ``duplicate_market_for_event`` counts -- so appending inside the row
    # loop printed the same downgrade twice in the coupon header. On 2026-09-01
    # Leicester's ``goals_for 1.5 UNDER`` appeared as two identical DOWNGRADE
    # notes, which reads as two separate findings against one fixture.
    reported_vetoes: set[tuple[str, str, float | None, str | None, str]] = set()

    def note_veto_once(veto: AnalystVeto, note: str) -> None:
        key = (veto.event_id, veto.market, veto.line, veto.direction, veto.action)
        if key in reported_vetoes:
            return
        reported_vetoes.add(key)
        applied_vetoes.append(note)

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
        # The *day*, not the timestamp: two feeds publish the same kickoff a
        # minute or a timezone-spelling apart ("Z" vs "+00:00"), and a raw
        # string here would give one match two keys and the coupon the same
        # bet at two ranks. (bucket, day) is the identity rule the rest of
        # simple_stats already matches fixtures by.
        return (event.sport, (event.start_time or "")[:10], names)

    # Resolved once, before either the singles loop or draft_legs sees a row:
    # both paths must refuse the same rows, which is the invariant the whole
    # 2026-09-01 Bet Builder failure came from breaking.
    ambiguous_players = _ambiguous_player_names(stats_sheet.rows)
    # ``draft_legs`` takes a sheet, not a row, so the refusal has to be applied
    # to the sheet it takes. "Every gate a single passes, a leg passes too" is
    # the invariant, and it is the one the 2026-09-01 Bet Builder failure came
    # from breaking -- thirty legs went out that day past gates the singles
    # loop applied and the leg path did not.
    buildable = stats_sheet
    if ambiguous_players:
        buildable = stats_sheet.model_copy(update={
            "rows": [
                row for row in stats_sheet.rows
                if not (
                    row.player_name
                    and (row.event_id, row.player_name) in ambiguous_players
                )
            ]
        })

    excluded: dict[str, int] = {}

    def exclude(reason: str) -> None:
        excluded[reason] = excluded.get(reason, 0) + 1

    # --- singles ----------------------------------------------------------
    candidates: list[tuple[StatsSheetRow, str]] = []
    for row in stats_sheet.rows:
        tier: Tier = tier_for_row(row)
        veto = veto_index.for_row(row)
        # DOWNGRADE is applied before the tier gate below, not after: a CALL
        # the analyst steps to WEAK is excluded by that same check, exactly
        # like a context flag's downgrade would be -- no second exclusion path
        # needed for it.
        if veto is not None and veto.action == "DOWNGRADE":
            new_tier = step_tier_down(tier)
            note_veto_once(
                veto,
                f"DOWNGRADE analityka: {_veto_scope(veto)} "
                f"({row.event_id[:12]}) {tier}→{new_tier} — {veto.reason}",
            )
            tier = new_tier
        if tier in ("WEAK", "DROP"):
            exclude(f"tier_{tier.lower()}")
            continue
        if veto is not None and veto.action == "VETO":
            exclude("analyst_veto")
            note_veto_once(
                veto,
                f"WETO analityka: {_veto_scope(veto)} "
                f"({row.event_id[:12]}) — {veto.reason}",
            )
            continue
        if row.p_low < min_p_low:
            exclude("p_low_below_threshold")
            continue
        if row.player_name and (row.event_id, row.player_name) in ambiguous_players:
            exclude("ambiguous_player_name")
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
                probe = superbet_for(row, required_price(row, tier, basis=bar_basis))
                if probe.get("superbet_verdict") != "VALUE":
                    exclude("superbet_not_value")
                    continue
            key = (fixture_key(row.event_id), row.market, _subject_key(row))
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
            if row.p_low <= 0:
                # Same refusal ``draft_legs`` makes: 1/0 is not a price, and a
                # row whose lower bound is zero is making no claim to rank.
                exclude("p_low_not_positive")
                continue
            fair = 1.0 / row.p_low
            minimum = required_price(row, tier, basis=bar_basis)
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
                    subject_kind=_subject_kind(row),
                    subject_id=row.player_id,
                    tier=tier,
                    p_low=row.p_low,
                    p_central=row.p_central,
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
                    caveats=_caveats(row) + (
                        [
                            "rynek wycenia to znacznie niżej niż my — najpierw "
                            "sprawdź próbkę, potem kurs"
                        ] if over_disagreement(row) and not off_ladder(row) else []
                    ) + (
                        [
                            "próbka opisuje inny środek rozkładu niż cała "
                            f"drabinka Superbetu (średnia {row.mean:.2f} vs "
                            f"mediana rynku {ladder_median(row):.2f}, "
                            f"{ladder_sigma(row):+.2f}σ) — to nie jest spór o "
                            "ogon, to spór o to, gdzie ten rynek leży"
                        ] if off_ladder(row) else []
                    ),
                    edge=round(_edge(row), 4) if _has_market_reference(row) else None,
                    market_disagreement=disagreement(row),
                    ladder_sigma=ladder_sigma(row),
                    needs_review=over_disagreement(row),
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
        info = superbet_for(row, required_price(row, tier, basis=bar_basis))
        return info.get("superbet_surplus") if info.get("superbet_verdict") == "VALUE" else None

    # The ladder gate, and it is a *demotion*, not an exclusion.
    #
    # Nothing is deleted, because the gate cannot tell an edge from a broken
    # sample and must not pretend to. What it can do is stop the file
    # presenting the second as the first, ranked number one.
    #
    # Only the *ladder* disagreement demotes. The per-rung one annotates.
    #
    # They were one gate and they are not one finding. ``off_ladder`` says the
    # sample's centre is nowhere near the centre the book's whole devigged
    # ladder implies -- four of 2026-09-01's six losers were exactly that, and
    # a sample measuring another venue or another competition has a tail that
    # is not evidence about anything. ``disagreement`` says our floor sits more
    # than MAX_MARKET_DISAGREEMENT above the devigged price *at this row's own
    # rung*, and that is not a defect at all: it is the definition of value. A
    # gate that demotes on it demotes the thing the file exists to find.
    #
    # It cost exactly that on 2026-09-02. Of the day's 82 bettable rows, 78
    # were the best-of-five artifact and one -- WTA ``aces_total`` 5.5 OVER at
    # 2.07 against a 1.8146 floor -- was real. It disagreed with the book by
    # more than 25%, which is why it was worth taking, was demoted to the tail
    # for it, and fell off the far side of the 15-single cap. The file shipped
    # with nothing.
    #
    # Both still carry their caveat onto the row, so nothing is quieter than
    # before; what changed is which of the two moves a row's rank.
    flagged = [c for c in candidates if off_ladder(c[0])]
    flagged_ids = {id(c) for c in flagged}
    trusted = [c for c in candidates if id(c) not in flagged_ids]

    superbet_value = [c for c in trusted if _superbet_surplus(c) is not None]
    value_ids = {id(c) for c in superbet_value}
    rest = [c for c in trusted if id(c) not in value_ids]
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
            key=lambda pair: (is_trivial_under(pair[0]), -pair[0].p_low, pair[0].event_id),
        )
    )
    # Last, and only if the budget above did not run out. Ranked by how far the
    # sample's centre sits from the book's, widest first -- read as a to-check
    # list, not a shortlist. On |sigma| rather than on the price gap, because
    # the price gap no longer puts anything in this group.
    _append_singles(
        sorted(
            flagged,
            key=lambda pair: (
                -abs(ladder_sigma(pair[0]) or 0.0), -pair[0].p_low, pair[0].event_id
            ),
        )
    )

    # --- slips ------------------------------------------------------------
    #
    # Every gate the singles loop above applies, this loop applies too. Before
    # 2026-09-01 it applied two of eight, and the file gave no sign of it: the
    # analyst's vetoes, the ``min_p_low`` floor, the Superbet price check and
    # the duplicate-fixture guard all stopped at the singles list, while the
    # slips were drafted straight off the raw sheet. They are passed *into*
    # ``draft_legs`` rather than re-checked afterwards, because a leg excluded
    # after drafting would still have consumed one of ``max_legs``.
    def leg_price(row: StatsSheetRow) -> tuple[str | None, float | None]:
        if superbet_offer is None:
            return (None, None)
        # Same lookup as the singles, so a leg and a single on the same
        # (market, line, direction) can never disagree about whether the book
        # carries it.
        availability, exact, _, _ = lookup_line(
            superbet_events.get(row.event_id),
            market=row.market,
            line=row.line,
            direction=row.direction,
            team_name=row.team_name,
            player_name=row.player_name,
            player_aliases=player_aliases.get(row.event_id, {}),
        )
        return (availability, exact.price if exact else None)

    slips: list[CouponSlip] = []
    # Deduplicated by real-world fixture, not by event_id. Two dossiers can
    # describe one match (two feeds spelling a club differently), and the
    # singles list has resolved that since 2026-08-28 while this loop still
    # keyed on the raw id -- so the same match could occupy two slips and an
    # operator working down the file would have staked it twice believing he
    # had diversified. ``fixture_key`` is the same resolver the singles use.
    seen_fixtures: set[tuple] = set()
    for event_id in sorted({row.event_id for row in stats_sheet.rows}):
        fixture = fixture_key(event_id)
        if fixture in seen_fixtures:
            exclude("duplicate_fixture_for_slip")
            continue
        draft = draft_legs(
            buildable,
            event_id,
            max_legs=max_legs,
            vetoes=veto_index,
            min_p_low=min_p_low,
            price_for=leg_price if superbet_offer is not None else None,
            require_value=require_superbet_value,
            bar_basis=bar_basis,
        )
        # A one-leg "slip" is a single wearing a different hat, and printing it
        # in both sections would double-count the same read.
        if len(draft.legs) < 2:
            continue
        match, competition, kickoff = identity(event_id)
        if _kickoff_passed(kickoff, not_before):
            exclude("kickoff_passed_slip")
            continue
        if competition_tier(competition) in ("YOUTH", "FRIENDLY"):
            exclude("competition_youth_or_friendly_slip")
            continue
        seen_fixtures.add(fixture)
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

    def _slip_value_legs(slip: CouponSlip) -> int:
        """How many of this slip's legs the operator's own book prices at or
        above their own threshold."""
        return sum(
            1
            for leg in slip.draft.legs
            if leg.superbet_price is not None
            and leg.superbet_price >= leg.min_acceptable_odds
        )

    # Value first, one level up from the legs and for the same reason. Ranking
    # slips on ``weakest_leg_p_low`` alone actively undid the leg ranking below
    # it: promoting the one leg worth its price *lowers* a slip's weakest
    # ``p_low``, so the slip carrying it sank in this sort and was cut by
    # ``max_slips``. Measured 2026-09-01: fixing the leg order alone dropped the
    # Sheffield United and Preston slips out of the file entirely and replaced
    # them with slips made of 1.01-priced near-certainties. A slip with a leg
    # that can pay outranks one where nothing can, whatever its weakest leg's
    # certainty; within each group the weakest leg still decides.
    slips.sort(
        key=lambda s: (-_slip_value_legs(s), -s.weakest_leg_p_low, s.event_id)
    )
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
    if any(is_trivial_under(r) for r, _ in candidates):
        notes.append(
            "Niskie linie UNDER (≤1.5) zepchnięto na koniec — i listy singli, "
            "i kolejności nóg w Bet Builderach: przy 10/10 wychodzą wysoko w "
            "p_low, ale rynek wycenia je ~1.05."
        )
    if flagged:
        # Reported from the *candidates*, not from the rows that made the file.
        # max_singles is 15 against thousands of candidates, so a demoted row is
        # almost always pushed off the end -- and a row removed from the top of
        # the coupon without a word is the same silent edit this gate exists to
        # stop. One line per fixture+market: the same read at four lines is one
        # thing to go and check, not four.
        worst: dict[tuple, tuple[StatsSheetRow, float]] = {}
        for row, _tier in flagged:
            gap = abs(ladder_sigma(row) or 0.0)
            key = (fixture_key(row.event_id), row.market, _subject_key(row))
            if key not in worst or gap > worst[key][1]:
                worst[key] = (row, gap)
        listed = sorted(worst.values(), key=lambda pair: -pair[1])
        shown = listed[:8]
        detail = "; ".join(
            f"{identity(row.event_id)[0]} {market_label(row.market)} {row.line} "
            f"{row.direction} ({gap:.2f}σ)"
            for row, gap in shown
        )
        notes.append(
            f"{len(listed)} czytań zepchnięto na koniec listy, bo środek próbki "
            f"leży dalej niż {MAX_LADDER_SIGMA:.2f} jej własnego odchylenia od "
            "środka, który implikuje cała odmarżowiona drabinka Superbetu — przy "
            f"limicie {max_singles} singli zwykle znaczy to, że w ogóle nie "
            "weszły. To nie jest spór o ogon rozkładu, tylko o to, gdzie ten "
            "rynek leży, a taka próbka opisuje inny mecz, inny teren albo inne "
            "rozgrywki. Najszersze rozjazdy: "
            + detail
            + (f" (+{len(listed) - len(shown)} więcej)" if len(listed) > len(shown) else "")
            + ". Sprawdź próbkę, zanim sprawdzisz kurs."
        )
    scoped: dict[str, int] = {}
    for row in stats_sheet.rows:
        for reason, count in (row.sample_excluded or {}).items():
            scoped[reason] = scoped.get(reason, 0) + count
    if scoped:
        notes.append(
            "Obserwacje odrzucone z prób PRZED policzeniem p_low: "
            + ", ".join(f"{count}× {reason}" for reason, count in sorted(scoped.items()))
            + ". Sparing przedsezonowy i mecz z poprzedniego sezonu nie są próbą "
            "dzisiejszych rozgrywek; do 2026-09-01 liczyły się na równi z meczem "
            "ligowym i podnosiły p_low. MATCH_FORMAT_MISMATCH to mecz do dwóch "
            "wygranych setów w próbce meczu do trzech, a MATCH_FORMAT_UNKNOWN — "
            "mecz, o którym dostawca nie powiedział, z jakiej drabinki pochodzi; "
            "oba dotyczą wyłącznie rynków zależnych od długości meczu (gemy, "
            "sety, asy, podwójne błędy) w meczach ATP."
        )
    slip_legs = [leg for slip in slips for leg in slip.draft.legs]
    if slip_legs:
        below = [leg for leg in slip_legs if leg.superbet_price is not None
                 and leg.superbet_price < leg.min_acceptable_odds]
        notes.append(
            f"Bet Builder: {len(slip_legs)} nóg, każda z linią realnie wystawioną "
            f"na Superbecie"
            + (
                f"; {len(below)} z nich poniżej własnego progu — to nie są typy, "
                "trzymane tylko jako kontekst dla reszty kuponu."
                if below else " i każda powyżej swojego progu."
            )
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
