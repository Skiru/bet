"""A chat slip (AKO) to a target price from the day's coupon - outside the
pipeline: no stage calls it, it changes nothing that prints, it sizes no
stake and prices no slip.

Why (operator 2026-10-20, "mniej nóg większym kursem"): every printed leg
loses about the same share of its price in every odds band (13_results.json
10-13..10-19, match bootstrap: 1.10-1.30 ROI -5.1% [-5.9, -4.3] on 22,663
legs, 1.30-1.70 -4.2% [-6.2, -2.3] on 5,544, difference +0.9 pp [-1.0,
+2.8]), so a slip pays that loss once per leg: at a fixed target price fewer
legs lose less. The builder therefore maximises the slip's measured chance
under "product of leg prices >= target" - that objective itself picks the
fewest, longest legs - with one leg per match (two legs of one match are a
Bet Builder, priced by Superbet's screen only).

A leg's measured chance stands on its own statistics only:
    min(confidence, 1/odds for a leg above its price)
- the confidence already carries the leg's line evidence (offset and
price-band cap), and a leg of any sport more than `price_gap.GAP` above its
price (or flagged `price_gap`) is read at its price, never above it
(CLAUDE.md; `measured_chance`). The operator 2026-10-31 removed the
families' record of the printed legs ("rodzina na plusie",
`family_record.json`): no family, sport or tier shortfall, no family
preference - one search over every leg, the analysts' reads deciding which
legs stay.

The least-loss flow (operator's go 2026-10-31; backtest walk-forward
10-13..10-26, hold-out 10-27..10-30, morning print prices, Polish 12%
turnover tax - `docs/sofa/evidence/slip_flow_backtest_2026-10-31.md`): no
flow cleared zero after tax. Hold-out, after tax: singles -16.6%, random
2-leg slips -19.0%, 3 legs -30.2%, 2-4 legs at ~3 -28.5%, the old objective
at up to 5 legs -31.5%; Bet Builders -16.6% (dev) / -45.8% (hold-out). So a
slip is 2 legs by default (`MAX_LEGS`; the operator may raise it and the
answer then states each extra leg's measured cost), builders are opt-in, a
target the leg limit cannot reach is said first and the closest slip under
it is built (never a silent extra leg), a low-margin leg is preferred in a
near-tie (`LOW_MARGIN_TIE`) and every slip carries the honest money line
`expected_return` - what a leg of the coupon realised against its price,
after tax - never a return computed from our confidence.
"""

from __future__ import annotations

import datetime
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

from bet.sofa.config import SofaConfig
from bet.sofa.price_gap import GAP as PRICE_GAP
from bet.sofa.price_gap import annotate as price_gap_of
from bet.sofa.sport_day import MAX_PRICE_AGE as SPORT_PRICE_AGE
from bet.sofa.veto import read_refusal, veto_matches

# A leg's analyst read (reads.json / vetoes.json, matched like a veto; or
# the reads the coupon carries): KEEP, unread, or refused - a refused leg
# never enters a slip, so the next search takes the next best leg.
READ_KEEP = "KEEP"  # the slip's own read (reads_slip.json)
READ_KEEP_DAY = "KEEP (kupon dnia)"  # the day's C3 read - may be hours old
READ_NONE = "nie"
# a slip read older than this (an earlier request's, maybe before lineups) is
# shown with its local time, "KEEP (10:42)"; like the day's read it does not
# count as read for the slip (operator 2026-10-21: the morning KEEPs of a
# 16-18 slip missed a reserve goalie and a 12-games wall) - unread_legs
SLIP_READ_FRESH = datetime.timedelta(hours=3)
# the search's tie-break for a read leg: +0.25% relative chance (review 5: a
# slip of two KEEP legs at 0.2385 lost to two unread legs at 0.2388)
READ_TIE = math.log(1.0025)
REFUSING = frozenset({"WATCH", "NO_BET"})

# Defaults (tolerances, not fitted constants): the measured bands end at
# 2.00 (above it the coupon holds few legs), a leg starting within
# START_MARGIN cannot be placed in time, and the search files log prices in
# STEP buckets.
MIN_LEG_ODDS = 1.10
MAX_LEG_ODDS = 2.00
# 2 legs by default (operator 2026-10-31): each leg pays the coupon's loss to
# the price once more (`REALISED_PER_LEG`), and the hold-out ranked singles /
# 2 legs above 3+ legs after tax (evidence doc above). --max-legs raises it.
MAX_LEGS = 2
CROWD_LEGS = 3  # a slip with this many legs of one market type is named
START_MARGIN = datetime.timedelta(minutes=15)  # = the analysts' started-skip
# a leg starting sooner is marked: an analyst round takes ~20-30 min
READ_MARGIN = datetime.timedelta(minutes=45)
STEP = 0.0001
LOCAL = ZoneInfo("Europe/Warsaw")  # the operator's clock
# The pipeline's own price-age limits: CONFIDENCE refuses a football / tennis
# price older than SofaConfig.price_max_age_min (STALE_PRICE), SPORT_CONFIDENCE
# a measured sport's older than sport_day.MAX_PRICE_AGE. The coupon is not
# rebuilt for a chat slip, so a leg past its limit is flagged, not refused -
# the screen's price decides.
SHEET_PRICE_AGE = datetime.timedelta(minutes=SofaConfig.price_max_age_min)

# The honest money line (operator 2026-10-31). Measured, not fitted: a printed
# leg of the coupon 2026-10-20..2026-10-30 (13_results.json, won / lost, n
# 49,189) hit 0.782 against 1/odds 0.827 - it returned ~0.946 of its price
# per unit staked (the morning print, deduplicated: 0.946; every graded row:
# 0.945). Polish betting tax: 12% of the stake (payout = 0.88 x stake x the
# product of the prices when every leg wins). Expected return after tax of an
# n-leg slip ~= (1 - TAX) x REALISED_PER_LEG**n - 1, whatever our confidence
# says - the slips realise at the price, not at our chance.
REALISED_PER_LEG = 0.946
REALISED_SOURCE = "nogi kuponu 10-20..10-30, n 49 189"
TAX = 0.12
# a single below this price pays back less than the stake even when it wins
SINGLE_CASH_FLOOR = 1.0 / (1.0 - TAX)
# A leg whose two-sided ladder / group overround is below LOW_MARGIN gains
# LOW_MARGIN_TIE in the search only (a small explicit preference, the size of
# READ_TIE: +0.25% relative chance; the printed chance is never touched).
# Measured on dev 10-13..10-26: two-sided legs with overround < 0.08 -3.1%
# before tax vs -5.4% for all, +2.2 pp [+0.1, +4.2] within market; NOT held
# out (10-27..10-30: -5.8% vs -5.2%) - hence a near-tie-break, never a gate.
# One-sided legs (no overround) gain nothing.
LOW_MARGIN = 0.08
LOW_MARGIN_TIE = math.log(1.0025)
# Bet Builders after tax, priced at 0.90 x the product of their legs (an
# assumption - Superbet does not price a builder as the product): dev
# 10-13..10-26 n 88, hold-out 10-27..10-30 n 10.
BUILDERS_MEASURED = ("Bet Buildery zmierzone po podatku: −16,6% stawki "
                     "(10-13..10-26, n 88) i −45,8% (hold-out 10-27..10-30, n 10), "
                     "przy założeniu kursu 0,90 × iloczyn nóg")


def expected_return(n: int) -> float:
    """Expected return per unit staked after tax of an n-leg slip, by what
    the coupon's legs realised against their price (REALISED_PER_LEG)."""
    return (1.0 - TAX) * REALISED_PER_LEG**n - 1.0


def money_line(n: int) -> str:
    """The honest money line of an n-leg slip, in Polish."""
    per = f"{REALISED_PER_LEG:g}".replace(".", ",")
    keep = f"{1.0 - TAX:.2f}".replace(".", ",")
    pct = f"{expected_return(n) * 100:+.1f}%".replace(".", ",").replace("-", "−")
    return (f"oczekiwany zwrot po podatku ≈ {keep} × {per}^{n} − 1 = {pct} stawki "
            f"(zmierzone: {REALISED_SOURCE}; podatek {TAX * 100:.0f}%)")


def legs_needed(legs: Sequence[Leg], target: float, limit: int = 20) -> int | None:
    """The fewest legs (one per match, each at its match's longest price)
    whose price product reaches `target`; None when `limit` legs cannot."""
    best: dict[str, float] = {}
    for x in legs:
        best[x.match_key] = max(best.get(x.match_key, 1.0), x.odds)
    product = 1.0
    for k, odds in enumerate(sorted(best.values(), reverse=True)[:limit], 1):
        product *= odds
        if product >= target - 1e-9:
            return k
    return None


def reach(legs: Sequence[Leg], max_legs: int) -> float:
    """The highest price product `max_legs` legs of distinct matches reach."""
    best: dict[str, float] = {}
    for x in legs:
        best[x.match_key] = max(best.get(x.match_key, 1.0), x.odds)
    return math.prod(sorted(best.values(), reverse=True)[:max_legs])


@dataclass(frozen=True)
class Leg:
    leg: Mapping[str, Any]
    odds: float
    chance: float
    chance_source: str
    read: str = READ_NONE
    price_age: datetime.timedelta | None = None
    age_is_floor: bool = False  # no fetch time on the leg: age since the build

    @property
    def stale(self) -> bool:
        sport = str(self.leg.get("sport") or "football")
        limit = SHEET_PRICE_AGE if sport in ("football", "tennis") else SPORT_PRICE_AGE
        return self.price_age is not None and self.price_age > limit

    @property
    def match_key(self) -> str:
        return str(self.leg.get("group_key") or self.leg.get("sofascore_event_id"))

    @property
    def overround(self) -> float | None:
        """The two-sided ladder / group overround the coupon carries on the
        leg; None for a one-sided leg (and a builder)."""
        raw = self.leg.get("overround")
        return float(raw) if raw is not None and _finite(raw) else None

    @property
    def low_margin(self) -> bool:
        return self.overround is not None and self.overround < LOW_MARGIN

    @property
    def cost(self) -> float:
        """Chance given up per unit of log price: lower buys price cheaper."""
        return -math.log(self.chance) / math.log(self.odds)


@dataclass
class Slip:
    legs: list[Leg]
    # set when the target needs more legs than the limit: this slip is the
    # closest under the target with the limit's legs, and the target would
    # need this many (operator 2026-10-31: never a silent extra leg)
    needs_legs: int | None = None

    @property
    def chance(self) -> float:
        return math.prod(x.chance for x in self.legs)

    @property
    def price_product(self) -> float:
        """Only to test the target - never a price of the slip."""
        return math.prod(x.odds for x in self.legs)

    @property
    def has_builder(self) -> bool:
        return any(x.leg.get("builder_legs") for x in self.legs)

    @property
    def rows(self) -> int:
        """The coupon rows the slip stands on (a builder counts its legs) -
        the n of the money line."""
        return sum(len(leg_rows(x)) for x in self.legs)

    @property
    def reached(self) -> bool:
        return self.needs_legs is None


@dataclass
class Result:
    slips: list[Slip]
    requested: int
    candidates: int  # legs (and builders) the search could take
    refused: dict[str, int] = field(default_factory=dict)
    reachable: float = 1.0  # the highest price product the pool's legs reach
    reserve: list[Slip] = field(default_factory=list)
    max_legs: int = MAX_LEGS
    builders: bool = False  # the day's Bet Builders were offered to the search


def family_key(leg: Mapping[str, Any]) -> str:
    """A leg's market type (sport, market, direction) - only to name a slip
    crowded on one of them (`concentration`), never a selection."""
    return "|".join((str(leg.get("sport") or "football"), str(leg.get("market") or ""),
                     str(leg.get("direction") or "")))


def measured_chance(leg: Mapping[str, Any], odds: float) -> tuple[float, str]:
    """min(confidence, 1/odds for a leg above its price): the leg's own
    statistics (the confidence carries its line evidence), but a leg of any
    sport whose confidence exceeds 1/odds by more than `price_gap.GAP` - or
    that carries `price_gap` - is read at its price, never above it. Such
    legs realise about at their price wherever measured (football / tennis
    -10.0 pp, CS2 -18.6 pp, `bet.sofa.price_gap`; volleyball ~16 pp over at
    confidence >= 0.70, model-state.md); hockey / basketball / volleyball
    carry no flag, so the gap itself decides (2026-10-31: volleyball set
    handicaps read at 82% against 57% at the price topped a ~3 slip)."""
    confidence = float(leg["confidence"])
    bounds = [(confidence, "pewność")]
    if leg.get("price_gap"):
        bounds.append((1.0 / odds, "cena (price_gap)"))
    elif confidence - 1.0 / odds > PRICE_GAP:
        bounds.append((1.0 / odds, "cena (pewność ponad cenę)"))
    chance, source = min(bounds, key=lambda b: b[0])
    return max(min(chance, 0.999), 1e-6), source


def row_key(leg: Mapping[str, Any]) -> dict[str, Any]:
    line = leg.get("line")
    period = leg.get("period")
    return {
        "sofascore_event_id": int(leg["sofascore_event_id"]),
        "market": str(leg["market"]),
        "subject": str(leg.get("subject") or ""),
        "line": None if line is None else float(line),
        "direction": str(leg["direction"]),
        "period": None if period is None else int(period),
    }


def _harder_rung_refused(leg: Mapping[str, Any], refusals: Iterable[Any]) -> bool:
    """A refusal of an OVER at line L also refuses the leg's harder rungs of
    the same variable (OVER above L; an UNDER below L): the analyst's reason
    holds a fortiori, and without it a refused rung's neighbour enters the
    next round unread."""
    key = row_key(leg)
    direction, line = key["direction"], key["line"]
    if direction not in ("OVER", "UNDER") or line is None:
        return False
    for r in refusals:
        r_line = getattr(r, "line", None)
        if r_line is None or not veto_matches(r, **{**key, "line": float(r_line)}):
            continue
        if (direction == "OVER" and line >= r_line) or (
            direction == "UNDER" and line <= r_line
        ):
            return True
    return False


def read_status(
    leg: Mapping[str, Any],
    reads: Sequence[Any] = (),
    vetoes: Sequence[Any] = (),
    slip_reads: Sequence[Any] = (),
    now: datetime.datetime | None = None,
) -> str | None:
    """None when a veto or a WATCH / NO_BET read refuses the leg or a lower
    rung of it (the day's files, the slip's own, or carried on the leg - the
    rebuild's matching rule); else READ_KEEP when the slip's own analyst read
    covers it ("KEEP (HH:MM)" when that read is older than SLIP_READ_FRESH at
    `now`), READ_KEEP_DAY when only the day's C3 read does, READ_NONE."""
    key = row_key(leg)
    every = [*reads, *slip_reads]
    covering = [r for r in every if veto_matches(r, **key)]
    if any(veto_matches(v, **key) for v in vetoes) or read_refusal(covering):
        return None
    refusals = [*vetoes, *(r for r in every if r.verdict in REFUSING)]
    if _harder_rung_refused(leg, refusals):
        return None
    carried = [r for r in leg.get("reads") or [] if isinstance(r, Mapping)]
    if {str(r.get("verdict")) for r in carried} & REFUSING:
        return None
    own = [r for r in slip_reads if r.author == "analyst" and veto_matches(r, **key)]
    if own:
        stamps = [r.read_at_utc for r in own if getattr(r, "read_at_utc", None)]
        if now is None or len(stamps) < len(own):
            return READ_KEEP
        latest = max(
            datetime.datetime.fromisoformat(s.replace("Z", "+00:00")) for s in stamps
        )
        if now - latest <= SLIP_READ_FRESH:
            return READ_KEEP
        return f"{READ_KEEP} ({latest.astimezone(LOCAL):%H:%M})"
    if any(r.author == "analyst" for r in covering) or any(
        r.get("author") == "analyst" for r in carried
    ):
        return READ_KEEP_DAY
    return READ_NONE


def candidates(
    singles: Iterable[Mapping[str, Any]],
    now: datetime.datetime,
    *,
    min_odds: float = MIN_LEG_ODDS,
    max_odds: float = MAX_LEG_ODDS,
    exclude_matches: Iterable[str] = (),
    window: tuple[datetime.datetime, datetime.datetime] | None = None,
    reads: Sequence[Any] = (),
    vetoes: Sequence[Any] = (),
    built_at: str | None = None,
    slip_reads: Sequence[Any] = (),
    competitions: Sequence[str] = (),
) -> tuple[list[Leg], dict[str, int]]:
    """The legs a slip may take, and the count of every refusal. A football
    / tennis leg carries no fetch time (CONFIDENCE reads it from 04_offer.json
    and refuses one older than its limit), so its price is at least as old as
    the coupon's build (`built_at`). `competitions`, when given, keeps only
    legs whose competition contains one of them (case-insensitive)."""
    wanted = [c.casefold() for c in competitions]
    skip = set(exclude_matches)
    out: list[Leg] = []
    refused: dict[str, int] = defaultdict(int)
    seen: set[tuple[Any, ...]] = set()
    for s in singles:
        if s.get("sofascore_event_id") is None:
            refused["brak id meczu"] += 1
            continue
        ident = (
            s.get("sofascore_event_id"),
            s.get("group_key"),
            s.get("market"),
            s.get("subject"),
            s.get("line"),
            s.get("direction"),
            s.get("side"),
            s.get("period"),
            s.get("map_nr"),
        )
        if ident in seen:
            continue
        seen.add(ident)
        odds = s.get("offered_odds") or s.get("odds")
        if s.get("locked") and not s.get("kickoff_utc"):
            refused["rozpoczęty lub za chwilę"] += 1
            continue
        kickoff = s.get("kickoff_utc")
        if odds is None or not _finite(s.get("confidence")) or not _finite(odds):
            refused["brak ceny lub pewności"] += 1
            continue
        start = (
            datetime.datetime.fromisoformat(str(kickoff).replace("Z", "+00:00"))
            if kickoff
            else None
        )
        if start is None or start <= now + START_MARGIN:
            refused["rozpoczęty lub za chwilę"] += 1
            continue
        if window is not None and not window[0] <= start < window[1]:
            refused["start poza oknem"] += 1
            continue
        if wanted and not any(
            w in str(s.get("competition") or "").casefold() for w in wanted
        ):
            refused["poza wybranymi rozgrywkami"] += 1
            continue
        if not min_odds <= float(odds) <= max_odds:
            refused["kurs poza przedziałem"] += 1
            continue
        mc = measured_chance(s, float(odds))
        read = read_status(s, reads, vetoes, slip_reads, now)
        if read is None:
            refused["odrzucona przez analityka (WATCH / NO_BET / weto)"] += 1
            continue
        fetched = s.get("price_fetched_at_utc") or built_at
        age = (
            now - datetime.datetime.fromisoformat(str(fetched).replace("Z", "+00:00"))
            if fetched
            else None
        )
        floor = not s.get("price_fetched_at_utc") and age is not None
        leg = Leg(s, float(odds), mc[0], mc[1], read, age, floor)
        if leg.match_key in skip:
            continue
        out.append(leg)
    return out, dict(refused)


BUILDER_MARKET = "bet_builder"


def builder_candidates(
    builders: Iterable[Mapping[str, Any]],
    now: datetime.datetime,
    *,
    min_odds: float = MIN_LEG_ODDS,
    max_odds: float = MAX_LEG_ODDS,
    window: tuple[datetime.datetime, datetime.datetime] | None = None,
    reads: Sequence[Any] = (),
    vetoes: Sequence[Any] = (),
    built_at: str | None = None,
    slip_reads: Sequence[Any] = (),
    competitions: Sequence[str] = (),
) -> tuple[list[Leg], dict[str, int]]:
    """The day's Bet Builders as one more option of their match (operator
    2026-10-26: "wybieraj bet buildery tez i przyjmij zasade mnozenia"). The
    builder's odds are the product of its legs' single prices - the
    operator's rule for reaching the target; Superbet prices a builder below
    that product (measured markup 8.8-19.6%), so the answer says so and the
    screen decides. Its measured chance is `combined_probability` lowered by
    each leg's own price cap (measured chance / confidence: a leg above its
    price by `price_gap.GAP` read at its price), never raised. A builder
    enters only when no read refuses any of its legs; it is KEEP only when
    the slip's own fresh read keeps every leg."""
    wanted = [c.casefold() for c in competitions]
    out: list[Leg] = []
    refused: dict[str, int] = defaultdict(int)
    for b in builders:
        kickoff = b.get("kickoff_utc")
        event = b.get("sofascore_event_id")
        legs = [g for g in b.get("legs") or [] if isinstance(g, Mapping)]
        if not kickoff or event is None or len(legs) < 2:
            refused["builder: brak danych"] += 1
            continue
        start = datetime.datetime.fromisoformat(str(kickoff).replace("Z", "+00:00"))
        if start <= now + START_MARGIN:
            refused["builder: rozpoczęty lub za chwilę"] += 1
            continue
        if window is not None and not window[0] <= start < window[1]:
            refused["builder: start poza oknem"] += 1
            continue
        if wanted and not any(
            w in str(b.get("competition") or "").casefold() for w in wanted
        ):
            refused["builder: poza wybranymi rozgrywkami"] += 1
            continue
        full = [
            {
                **g,
                "sport": "football",
                "sofascore_event_id": event,
                "group_key": f"sofa:{event}",
                "match": b.get("match"),
                "competition": b.get("competition"),
                "kickoff_utc": kickoff,
                "offered_odds": g.get("offered_odds") or g.get("odds"),
            }
            for g in legs
        ]
        if not all(_finite(g.get("offered_odds")) and _finite(g.get("confidence"))
                   for g in full):
            refused["builder: brak ceny lub pewności"] += 1
            continue
        for g in full:
            # the artifact's builder legs carry no price_gap: the pipeline's
            # own rule (bet.sofa.price_gap) marks a leg above its price, read
            # at its price like a single
            if not g.get("price_gap") and (pg := price_gap_of(g)):
                g["price_gap"] = pg
        odds = math.prod(float(g["offered_odds"]) for g in full)
        if not min_odds <= odds <= max_odds:
            refused["builder: kurs poza przedziałem"] += 1
            continue
        ratio = math.prod(
            min(measured_chance(g, float(g["offered_odds"]))[0]
                / float(g["confidence"]), 1.0)
            for g in full)
        reads_ = [read_status(g, reads, vetoes, slip_reads, now) for g in full]
        if any(r is None for r in reads_):
            refused["builder: noga odrzucona przez analityka"] += 1
            continue
        read = (
            READ_KEEP
            if all(r == READ_KEEP for r in reads_)
            else READ_NONE
            if READ_NONE in reads_
            else READ_KEEP_DAY
        )
        p = float(b.get("combined_probability") or 0.0) * ratio
        if p <= 0.0:
            refused["builder: brak łącznej szansy"] += 1
            continue
        built = str(built_at).replace("Z", "+00:00") if built_at else None
        age = now - datetime.datetime.fromisoformat(built) if built else None
        leg = {
            "sport": "football",
            "market": BUILDER_MARKET,
            "direction": "",
            "sofascore_event_id": event,
            "group_key": f"sofa:{event}",
            "match": b.get("match"),
            "competition": b.get("competition"),
            "kickoff_utc": kickoff,
            "confidence": float(b.get("combined_probability") or 0.0),
            "superbet_market": "Bet Builder",
            "superbet_selection": " + ".join(
                f"{g.get('superbet_market')}: {g.get('superbet_selection')} "
                f"({float(g['offered_odds']):.2f})"
                for g in full
            ),
            "builder_legs": full,
        }
        out.append(
            Leg(leg, odds, max(min(p, 0.999), 1e-6), "builder: łączna × cena nóg",
                read, age, age is not None)
        )
    return out, dict(refused)


# (log chance, exact log price, legs)
_State = tuple[float, float, tuple[Leg, ...]]


def best_slip(
    legs: Sequence[Leg], target: float, max_legs: int = MAX_LEGS
) -> Slip | None:
    """The slip of at most `max_legs` legs, one per match, whose price product
    reaches `target` with the highest measured chance, over every leg given (a
    multiple-choice knapsack). A state carries its exact log price and is
    filed under that price's `STEP` bucket; a bucket keeps the best log chance
    (on a tie the higher price), and a state no better than one in a higher
    bucket is dropped (Pareto - every later leg only adds price and loses
    chance). Every state at or above the target files under one bucket, the
    cap; one below it never does. The only slips it can miss are those whose
    partial state was beaten inside a `STEP`-wide bucket below the target by
    one that later fell short by less than the summed bucket width."""
    log_target = math.log(target)
    cap = math.floor(log_target / STEP) + 1
    by_match: dict[str, list[Leg]] = defaultdict(list)
    for x in legs:
        by_match[x.match_key].append(x)
    empty: tuple[Leg, ...] = ()
    dp: list[dict[int, _State]] = [{0: (0.0, 0.0, empty)}]
    dp += [{} for _ in range(max_legs)]
    for key in sorted(by_match):
        options = _pareto_legs(by_match[key])
        for k in range(max_legs - 1, -1, -1):
            if not dp[k]:
                continue
            nxt = dp[k + 1]
            for score, price, chosen in dp[k].values():
                for x in options:
                    p = price + math.log(x.odds)
                    cand = (score + _search_score(x), p, chosen + (x,))
                    # only a state at or above the target files under the cap,
                    # so one exactly at it never shares a bucket with one below
                    b = (
                        cap
                        if p >= log_target - 1e-12
                        else min(cap - 1, math.floor(p / STEP))
                    )
                    cur = nxt.get(b)
                    if cur is None or (cand[0], cand[1]) > (cur[0], cur[1]):
                        nxt[b] = cand
            dp[k + 1] = _pareto_states(nxt)
    best: tuple[float, int, tuple[Leg, ...]] | None = None
    for k in range(1, max_legs + 1):
        for score, price, chosen in dp[k].values():
            if price < log_target - 1e-12:
                continue
            if best is None or (score, -k) > (best[0], -best[1]):
                best = (score, k, chosen)
    if best is None:
        return None
    return Slip(sorted(best[2], key=lambda x: str(x.leg.get("kickoff_utc"))))


def _search_score(x: Leg) -> float:
    """A leg's log chance in the search: a leg the slip's own fresh read
    keeps gains READ_TIE, so a slip of read legs is not swapped for legs still
    to read over a hair of chance (each swap costs a round of reads); a leg
    of a two-sided ladder with overround < LOW_MARGIN gains LOW_MARGIN_TIE
    (operator 2026-10-31, measured on dev only - a near-tie-break). The
    printed chance is never touched."""
    return (math.log(x.chance) + (READ_TIE if x.read == READ_KEEP else 0.0)
            + (LOW_MARGIN_TIE if x.low_margin else 0.0))


def _finite(value: Any) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _pareto_legs(options: Sequence[Leg]) -> list[Leg]:
    """A match's legs that no other leg beats on both price and chance."""
    ranked = sorted(options, key=lambda x: (-x.odds, -_search_score(x)))
    out: list[Leg] = []
    best_chance = -1.0
    for x in ranked:
        if _search_score(x) > best_chance:
            out.append(x)
            best_chance = _search_score(x)
    return out


def _pareto_states(states: dict[int, _State]) -> dict[int, _State]:
    out: dict[int, _State] = {}
    best = -math.inf
    for b in sorted(states, reverse=True):
        if states[b][0] > best:
            out[b] = states[b]
            best = states[b][0]
    return out


def build(
    singles: Sequence[Mapping[str, Any]],
    now: datetime.datetime,
    target: float,
    slips: int = 1,
    *,
    max_legs: int = MAX_LEGS,
    window: tuple[datetime.datetime, datetime.datetime] | None = None,
    min_odds: float = MIN_LEG_ODDS,
    max_odds: float = MAX_LEG_ODDS,
    reads: Sequence[Any] = (),
    vetoes: Sequence[Any] = (),
    reserve: int = 0,
    built_at: str | None = None,
    slip_reads: Sequence[Any] = (),
    competitions: Sequence[str] = (),
    builders: Sequence[Mapping[str, Any]] = (),
) -> Result:
    """Up to `slips` disjoint slips (no match twice), searched over every
    leg in one pass. `reserve` more disjoint slips on the same terms are the
    analysts' buffer: their legs replace a slip leg a read refuses, so one
    read round covers them. Each slip is searched first over the legs with
    the slip's own fresh KEEP, then over every leg only when those cannot
    reach the target. `builders` adds the day's Bet Builders
    (`builder_candidates`). When the target needs more legs than `max_legs`,
    each slip is the closest under it (`Slip.needs_legs` set) - never an extra
    leg."""
    pool, refused = candidates(
        singles,
        now,
        min_odds=min_odds,
        max_odds=max_odds,
        window=window,
        reads=reads,
        vetoes=vetoes,
        built_at=built_at,
        slip_reads=slip_reads,
        competitions=competitions,
    )
    if builders:
        extra, why = builder_candidates(
            builders,
            now,
            min_odds=min_odds,
            max_odds=max_odds,
            window=window,
            reads=reads,
            vetoes=vetoes,
            built_at=built_at,
            slip_reads=slip_reads,
            competitions=competitions,
        )
        pool += extra
        for k, v in why.items():
            refused[k] = refused.get(k, 0) + v
    used: set[str] = set()
    out: list[Slip] = []
    while len(out) < slips + reserve:
        legs = [x for x in pool if x.match_key not in used]
        # legs the slip's own fresh read keeps come first; a leg still to
        # read enters only when they cannot reach the target (operator
        # 2026-10-21: each round swapped read legs for unread ones)
        kept = [x for x in legs if x.read == READ_KEEP]
        s = best_slip(kept, target, max_legs) or best_slip(legs, target, max_legs)
        if s is None:
            # the leg limit binds (more legs of this pool would reach the
            # target): the closest slip under the target with the limit's
            # legs - the highest product they reach, the best chance at it -
            # and the answer says how many legs the target needs
            need = legs_needed(legs, target)
            if need is None or need <= max_legs:
                break
            top = reach(legs, max_legs)
            s = best_slip(kept, top, max_legs) or best_slip(legs, top, max_legs)
            if s is None:
                break
            s.needs_legs = need
        out.append(s)
        used.update(x.match_key for x in s.legs)
    return Result(out[:slips], slips, len(pool), refused, reach(pool, max_legs),
                  out[slips:], max_legs, bool(builders))


def concentration(slip: Slip) -> tuple[str, int] | None:
    """The market type (`family_key`) holding at least CROWD_LEGS legs of the
    slip, or all of a slip of two or more legs, with its count; else None.
    Legs of one market type win or lose together more than the measured
    chance says (one model), so the answer names it - a warning, never a
    gate."""
    count: dict[str, int] = defaultdict(int)
    rows = [g for x in slip.legs for g in leg_rows(x)]
    for g in rows:
        count[family_key(g)] += 1
    fam, n = max(count.items(), key=lambda kv: kv[1], default=("", 0))
    if n >= CROWD_LEGS or (n == len(rows) >= 2):
        return fam, n
    return None


def unread_legs(slips: Iterable[Slip]) -> list[Leg]:
    """Legs the slip's analysts must still read: every leg without the slip's
    own KEEP within SLIP_READ_FRESH - the day's morning read ("KEEP (kupon
    dnia)") and an older slip read ("KEEP (10:42)") included, both possibly
    before lineups."""
    return [x for s in slips for x in s.legs if x.read != READ_KEEP]


def leg_rows(x: Leg) -> list[Mapping[str, Any]]:
    """The coupon rows a slip leg stands for: a builder's legs, else itself -
    what an analyst reads and a read is keyed to."""
    return list(x.leg.get("builder_legs") or [x.leg])


def legs_pl(n: int) -> str:
    few = n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14)
    return f"{n} {'noga' if n == 1 else 'nogi' if few else 'nóg'}"


def _legs_gen(n: int) -> str:
    """'trzeba 3 nóg' (genitive)."""
    return f"{n} {'nogi' if n == 1 else 'nóg'}"


def _legs_ins(n: int) -> str:
    """'z 2 nogami' (instrumental)."""
    return f"{n} {'nogą' if n == 1 else 'nogami'}"


def _local(raw: Any) -> str:
    """An ISO UTC time as the operator's HH:MM (with the date when not
    today's), or "?"."""
    if not raw:
        return "?"
    at = datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    return f"{at.astimezone(LOCAL):%d.%m %H:%M}"


def _age(x: Leg) -> str:
    if x.price_age is None:
        return "?"
    minutes = int(x.price_age.total_seconds() // 60)
    text = f"{minutes} min" if minutes < 120 else f"{minutes // 60} h"
    text = ("≥ " if x.age_is_floor else "") + text
    return f"**{text}**" if x.stale else text


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%".replace(".", ",")


def _signed(v: float) -> str:
    return f"{v * 100:+.1f}%".replace(".", ",").replace("-", "−")


def _margin(x: Leg) -> str:
    """The leg's ladder overround, bold below LOW_MARGIN; "1-str." for a
    one-sided leg, "—" for a builder."""
    if x.leg.get("builder_legs"):
        return "—"
    if x.overround is None:
        return "1-str."
    text = _pct(x.overround)
    return f"**{text}**" if x.low_margin else text


def render(
    result: Result,
    *,
    day: str,
    target: float,
    now: datetime.datetime,
    built_at: str | None = None,
    matchups: Mapping[str, str] | None = None,
) -> str:
    """Polish markdown for the operator. The first line answers the request
    ("say no first", in every mode - a target the leg limit cannot reach
    included), the second the honest money line; no slip price, no stake.
    `matchups`: bet.sofa.dossier.matchups_for_legs, shown beside each
    single."""
    from bet.sofa.dossier import matchup_key

    lines: list[str] = []
    reached = [s for s in result.slips if s.reached]
    short = [s for s in result.slips if not s.reached]
    n = len(reached)
    reach_text = (
        f" (iloczyn kursów najlepszych nóg sięga ~{result.reachable:.2f} - "
        "zasięg, nie kurs kuponu)"
        if result.reachable > 1.0
        else " (w oknie nie ma ani jednej nogi)"
    )
    # say no first (CLAUDE.md): how many of the requested slips the day's
    # legs - each on its own statistics and reads - give; a target the leg
    # limit cannot reach is said before anything else (operator 2026-10-31)
    if short:
        first = short[0]
        cost = round((1.0 - REALISED_PER_LEG) * 100)
        limit = (f"na ~{target:g} trzeba {_legs_gen(first.needs_legs or 0)} - każda "
                 f"kolejna noga to ok. −{cost}% więcej; z "
                 f"{_legs_ins(result.max_legs)} najbliżej ~{first.price_product:.2f} "
                 "(iloczyn kursów nóg, nie kurs kuponu)")
        head = (f"Dzień daje {n} z {result.requested} kuponów na ~{target:g}; "
                f"na kolejny {limit.removeprefix(f'na ~{target:g} ')}" if n
                else limit[0].upper() + limit[1:])
        lines.append(f"**{head}.**")
    elif n >= result.requested:
        lines.append(
            f"**Dzień daje {n} z {result.requested} kuponów na ~{target:g}.**"
        )
    elif n == 0:
        lines.append(f"**Dziś żadnego kuponu na ~{target:g}**{reach_text}.")
    else:
        lines.append(
            f"**Dzień cienki - masz {n} z {result.requested} kuponów na "
            f"~{target:g}**{reach_text}."
        )
    counts = sorted({s.rows for s in result.slips})
    if counts:
        money = "; ".join(
            (f"{legs_pl(k)}: " if len(counts) > 1 else "") + money_line(k)
            for k in counts)
        lines.append(money[0].upper() + money[1:]
                     + " - nasza szansa nie jest przewagą nad ceną.")
    if result.max_legs > MAX_LEGS or any(s.rows > MAX_LEGS for s in result.slips):
        top = max([result.max_legs, *counts])
        lines.append(
            f"Limit nóg {result.max_legs} (domyślnie {MAX_LEGS}): każda kolejna noga "
            f"mnoży zwrot przez {REALISED_PER_LEG:g}".replace(".", ",")
            + " - po podatku "
            + ", ".join(f"{legs_pl(k)} {_signed(expected_return(k))}"
                        for k in range(1, min(top, 10) + 1))
            + ".")
    if result.builders:
        lines.append(BUILDERS_MEASURED + ".")
    lines += [
        "",
        f"Poza pipeline'em: czat nie jest kuponem i nie ma bramek. Nogi z "
        f"`runs/sofa/{day}/11_coupon.json` (zbudowany {_local(built_at)}), "
        f"liczone {now.astimezone(LOCAL):%H:%M}. "
        "Szansa nogi = jej pewność ze statystyk (z dowodem linii Superbetu), "
        "powyżej ceny o > 3 pp (każdy sport) liczona po cenie (1/kurs). "
        "Jedna noga z meczu; przy remisie szansy wygrywa noga z marżą drabinki "
        f"< {LOW_MARGIN * 100:.0f}% (kolumna „marża”, „1-str.” = rynek "
        "jednostronny). "
        "Kurs kuponu: sprawdź na ekranie Superbetu. Stawka jest Twoja.",
        "",
    ]
    for i, s in enumerate(result.slips, 1):
        product = math.prod(x.odds for x in s.legs)
        head = (
            f"### Kupon {i}: {legs_pl(len(s.legs))}, szansa zmierzona {_pct(s.chance)}"
            + (" (builder: iloczyn kursów nóg, Superbet płaci mniej)" if s.has_builder
               else f" przy 1/kurs {_pct(1 / product)}")
            + f" - {money_line(s.rows)}"
        )
        if len(s.legs) == 1 and not s.has_builder and product < SINGLE_CASH_FLOOR:
            head += (f" - wygrana zwraca mniej niż gotówka (kurs < "
                     f"{SINGLE_CASH_FLOOR:.3f}".replace(".", ",")
                     + f" przy podatku {TAX * 100:.0f}%)")
        lines += [
            head,
            "",
            "| start | mecz | zakład (słowami Superbetu) | kurs | 1/kurs | "
            "szansa | źródło | pewność | pewność < 1/kurs | marża | zestawienie | "
            "czytana | cena sprzed |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for x in s.legs:
            g = x.leg
            read = x.read
            start = _local(g.get("kickoff_utc"))
            to_start = (datetime.datetime.fromisoformat(
                str(g.get("kickoff_utc")).replace("Z", "+00:00")) - now
                if g.get("kickoff_utc") else None)
            if to_start is not None and to_start < READ_MARGIN:
                start += f" ⚠ za {int(to_start.total_seconds() // 60)} min"
            bet = f"{g.get('superbet_market')}: {g.get('superbet_selection')}"
            if g.get("builder_legs"):
                odds, implied = f"{x.odds:.2f} iloczyn", "—"
                below = ", ".join(
                    f"{b.get('superbet_market')}: {b.get('superbet_selection')}"
                    for b in g["builder_legs"]
                    if float(b["confidence"]) < 1 / float(b["offered_odds"]))
                below = f"tak: {below}" if below else "nie"
                matchup = "; ".join(
                    t for b in g["builder_legs"]
                    if (t := (matchups or {}).get(matchup_key(b))))
            else:
                odds, implied = f"{x.odds:.2f}", _pct(1 / x.odds)
                below = ("**tak**" if float(g["confidence"]) < 1 / x.odds
                         else "nie")
                matchup = (matchups or {}).get(matchup_key(g), "")
            lines.append(
                f"| {start} | {g.get('match')} | {bet} | {odds} | "
                f"{implied} | {_pct(x.chance)} | {x.chance_source} | "
                f"{_pct(float(g['confidence']))} | {below} | {_margin(x)} | "
                f"{matchup.removeprefix('zestawienie: ') or '—'} | "
                f"{read} | {_age(x)} |"
            )
        lines += [
            "",
            f"Cel ~{target:g} osiągnięty (iloczyn kursów nóg ≥ cel); kurs kuponu "
            "sprawdź na ekranie Superbetu."
            if s.reached
            else f"Cel ~{target:g} NIE osiągnięty: ten kupon to najbliższy z "
            f"{_legs_ins(len(s.legs))} (iloczyn ~{product:.2f}, nie kurs kuponu); na "
            f"~{target:g} trzeba {_legs_gen(s.needs_legs or 0)} - noga więcej tylko na "
            "prośbę operatora (--max-legs).",
        ]
        if any(x.leg.get("builder_legs") for x in s.legs):
            lines.append(
                "Builder: cel liczony iloczynem kursów nóg (zasada operatora 26.10), "
                "ale Superbet płaci mniej - zmierzone 0,85-0,99 iloczynu (28.10), "
                "markup 8,8-19,6%; iloczyn to nie kurs buildera. Kurs buildera "
                "sprawdź na ekranie Superbetu."
            )
        crowd = concentration(s)
        if crowd is not None:
            fam, n = crowd
            lines.append(
                f"Uwaga: {n} z {len(s.legs)} nóg jednego rynku ({fam}) - nogi "
                "jednego rynku wchodzą i padają razem częściej, niż mówi szansa."
            )
        lines.append("")
    stale = [x for s in result.slips for x in s.legs if x.stale]
    if stale:
        lines.append(
            f"**Cena starsza niż limit pipeline'u: {legs_pl(len(stale))}** (piłka / "
            "tenis 45 min, sporty 3 h) - kurs na ekranie mógł się zmienić albo "
            "mecz zejść z oferty - sprawdź kurs na ekranie (kuponu dnia nie "
            "przebudowujemy dla kuponu z czatu)."
        )
    unread = unread_legs(result.slips)
    if result.slips:
        lines.append(
            f"**Nieczytane nogi w kuponach: {len(unread)}** - kupon jest gotowy "
            "dopiero, gdy każda noga ma KEEP analityka dla tego kuponu (ostatnie 3 h; "
            "poranny odczyt kuponu dnia się nie liczy); odrzucona wypada i kupon "
            "liczy się od nowa."
            if unread
            else "Każda noga kuponów ma KEEP analityka."
        )
    if result.reserve:
        names = "; ".join(
            f"{x.leg.get('match')} - {x.leg.get('superbet_market')}: "
            f"{x.leg.get('superbet_selection')} ({x.odds:.2f}, {x.read})"
            for s in result.reserve
            for x in s.legs
        )
        lines.append(f"Zapas do czytania (nie do grania): {names}")
    lines.append(f"Nogi w puli: {result.candidates}")
    if result.refused:
        lines.append(
            "Odrzucone: "
            + ", ".join(f"{k} {v}" for k, v in sorted(result.refused.items()))
        )
    return "\n".join(lines) + "\n"


def find_leg(
    singles: Sequence[Mapping[str, Any]], spec: str,
) -> tuple[Mapping[str, Any] | None, list[Mapping[str, Any]]]:
    """A coupon single by "<match fragment>|<superbet_market>|<selection>"
    (Superbet's words, case folded); else None and the same match's legs of
    that market (what the operator may have meant)."""
    parts = [p.strip().casefold() for p in spec.split("|")]
    if len(parts) != 3:
        raise ValueError(f"--check: '{spec}' - podaj 'mecz|rynek|wybór'")
    match, market, selection = parts
    same = [g for g in singles if match in str(g.get("match") or "").casefold()]
    for g in same:
        if (str(g.get("superbet_market") or "").casefold().strip() == market
                and str(g.get("superbet_selection") or "").casefold().strip()
                == selection):
            return g, []
    near = [g for g in same
            if str(g.get("superbet_market") or "").casefold().strip() == market]
    return None, near or same[:8]


def render_check(
    specs: Sequence[str],
    singles: Sequence[Mapping[str, Any]],
    screen_odds: float | None,
    matchups: Mapping[str, str],
    joint: Mapping[str, Any] | None,
    others: Sequence[Mapping[str, Any]] = (),
) -> str:
    """The operator's own Bet Builder of one match, leg by leg, against our
    numbers: each leg's measured chance beside 1/odds, its match-up, the
    legs' joint history in the two sides' games, and the screen price. No
    price of ours, no stake (CLAUDE.md hard rules)."""
    from bet.sofa.dossier import matchup_key

    lines = ["| zakład (słowami Superbetu) | kurs | 1/kurs | pewność | szansa "
             "zmierzona | szansa zmierzona < 1/kurs | zestawienie |",
             "|---|---|---|---|---|---|---|"]
    below: list[str] = []
    missing: list[str] = []
    for spec in specs:
        g, near = find_leg(singles, spec)
        if g is None and others:
            other, _ = find_leg(others, spec)
            if other is not None:
                missing.append(f"{spec} - nie na kuponie: {other.get('why')}")
                continue
        if g is None:
            hint = "; ".join(
                f"{x.get('superbet_market')}: {x.get('superbet_selection')}"
                for x in near[:6])
            missing.append(f"{spec} - nie ma na kuponie dnia"
                           + (f" (w tym meczu: {hint})" if hint else ""))
            continue
        odds = float(g["offered_odds"])
        chance = measured_chance(g, odds)[0]
        name = f"{g.get('superbet_market')}: {g.get('superbet_selection')}"
        # one rule for the column and the headline (E2E 2026-10-29: a leg
        # whose confidence clears 1/odds but measured chance does not read
        # "nie" in a column beside "poniżej ceny" in the headline)
        is_below = chance < 1 / odds
        if is_below:
            below.append(name)
        lines.append(
            f"| {name} | {odds:.2f} | {_pct(1 / odds)} | "
            f"{_pct(float(g['confidence']))} | "
            f"{_pct(chance)} | {'**tak**' if is_below else 'nie'} | "
            f"{(matchups.get(matchup_key(g)) or '—').removeprefix('zestawienie: ')} |")
    out = [f"**Builder: {len(specs) - len(missing)} z {len(specs)} nóg na kuponie "
           f"dnia, {len(below)} z szansą zmierzoną poniżej ceny.**", ""] + lines + [""]
    if missing:
        out.append("Nie na kuponie (bez szansy zmierzonej - nie dopisuj jej): "
                   + " | ".join(missing))
    if joint and joint.get("n"):
        out.append(
            f"Historia łączna: wszystkie {joint['legs_read']} nogi z historią weszły "
            f"razem w {joint['k']} z {joint['n']} ostatnich meczów obu drużyn "
            "(częstość, nie prawdopodobieństwo)"
            + (f"; bez historii: {', '.join(joint['legs_without_history'])}"
               if joint.get("legs_without_history") else "") + ".")
    elif joint and joint.get("missing"):
        out.append(f"Historia łączna: {joint['missing']}.")
    if screen_odds:
        out.append(
            f"Ekran Superbetu: {screen_odds:.2f} -> 1/kurs {_pct(1 / screen_odds)}. "
            "Builder ma sens tylko wtedy, gdy łączna szansa przekracza 1/kurs; "
            "każda noga w cenie lub poniżej jej tylko ją obniża.")
    if below:
        out.append("Szansa zmierzona poniżej 1/kurs (zamień albo usuń): "
                   + "; ".join(below) + ".")
    return "\n".join(out) + "\n"
