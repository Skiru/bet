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

A leg's measured chance is never its confidence alone:
    min(confidence, 1/odds for a `price_gap` leg, 1/odds + family shortfall)
where the shortfall is what the leg's family (sport, market, direction)
realised minus its price on the printed legs of the days before
(`family_record.json`, >= `family_record.MIN_LEGS` legs), else the sport's
pooled shortfall over the same record, never above 0; a leg of a family on
the plus reads its tier's walk-forward shortfall (`TIER_SHORTFALL`; a surplus is the
family's selected past, not its future); with neither the leg has no
measurement and is not used. A slip's measured chance is therefore never
above its price.

"Supported" (CLAUDE.md, chat slips): a slip whose every leg belongs to a
family on the plus (`family_record.on_plus`). Legs are tiered: the view's
selection (`family_record.selected`: x >= 1 and family on the plus), then the
family on the plus, then the rest; the rest enters only when the operator
asks for it and the answer says "dzień cienki" first. The selection's
advantage is not yet shown (T-FAMILY-SELECTION, walk-forward 10-12..10-19:
-0.9% against -5.2% for the rest, +4.3 pp [+0.4, +8.1], 72% of its legs on
one day; the registered window starts 10-19).
"""

from __future__ import annotations

import datetime
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

from bet.sofa import family_record as fr
from bet.sofa.config import SofaConfig
from bet.sofa.sport_day import MAX_PRICE_AGE as SPORT_PRICE_AGE
from bet.sofa.veto import read_refusal, veto_matches

# A leg's analyst read (reads.json / vetoes.json, matched like a veto; or
# the reads the coupon carries): KEEP, unread, or refused - a refused leg
# never enters a slip, so the next search takes the next best leg.
READ_KEEP = "KEEP"  # the slip's own read (reads_slip.json)
READ_KEEP_DAY = "KEEP (kupon dnia)"  # the day's C3 read - may be hours old
READ_NONE = "nie"
# a slip read older than this (an earlier request's, maybe before lineups) is
# shown with its local time, "KEEP (10:42)"; it still counts as read
SLIP_READ_FRESH = datetime.timedelta(hours=3)
# the search's tie-break for a read leg: +0.25% relative chance (review 5: a
# slip of two KEEP legs at 0.2385 lost to two unread legs at 0.2388)
READ_TIE = math.log(1.0025)
REFUSING = frozenset({"WATCH", "NO_BET"})

TIER_SELECTION = 1  # x >= 1 and family on the plus (the HTML view's button)
TIER_FAMILY_PLUS = 2  # family on the plus
TIER_REST = 3
TIER_NAMES = {
    TIER_SELECTION: "x ≥ 1 i rodzina na plusie",
    TIER_FAMILY_PLUS: "rodzina na plusie",
    TIER_REST: "reszta kuponu",
}

# Defaults (tolerances, not fitted constants): the measured bands end at
# 2.00 (above it the coupon holds few legs), a leg starting within
# START_MARGIN cannot be placed in time, and the search files log prices in
# STEP buckets.
MIN_LEG_ODDS = 1.10
MAX_LEG_ODDS = 2.00
MAX_LEGS = 5
CROWD_LEGS = 3  # a slip with this many legs of one family is named
START_MARGIN = datetime.timedelta(minutes=10)
STEP = 0.0001
LOCAL = ZoneInfo("Europe/Warsaw")  # the operator's clock
# The pipeline's own price-age limits: CONFIDENCE refuses a football / tennis
# price older than SofaConfig.price_max_age_min (STALE_PRICE), SPORT_CONFIDENCE
# a measured sport's older than sport_day.MAX_PRICE_AGE. The coupon is not
# rebuilt for a chat slip, so a leg past its limit is flagged, not refused -
# the screen's price decides.
SHEET_PRICE_AGE = datetime.timedelta(minutes=SofaConfig.price_max_age_min)

# Hit minus 1/odds the tiers realised walk-forward (families chosen on the
# days before each day; measure_selection_walk_forward.py --from 2026-10-12
# --to 2026-10-19, docs/sofa/evidence/selection_walk_forward_2026-10-20.md):
# x >= 1 and family on the plus 0.755 vs 0.763 on 1,430 legs, family on the
# plus 0.799 vs 0.815 on 4,996 legs. Measured, not fitted; re-measure as the
# registered test (T-FAMILY-SELECTION) accrues days.
TIER_SHORTFALL = {TIER_SELECTION: -0.008, TIER_FAMILY_PLUS: -0.016}


@dataclass(frozen=True)
class Leg:
    leg: Mapping[str, Any]
    odds: float
    chance: float
    chance_source: str
    tier: int
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
    def cost(self) -> float:
        """Chance given up per unit of log price: lower buys price cheaper."""
        return -math.log(self.chance) / math.log(self.odds)


@dataclass
class Slip:
    legs: list[Leg]

    @property
    def chance(self) -> float:
        return math.prod(x.chance for x in self.legs)

    @property
    def price_product(self) -> float:
        """Only to test the target - never a price of the slip."""
        return math.prod(x.odds for x in self.legs)

    @property
    def supported(self) -> bool:
        return all(x.tier < TIER_REST for x in self.legs)


@dataclass
class Result:
    slips: list[Slip]
    requested: int
    supported: int
    candidates: dict[int, int]
    refused: dict[str, int] = field(default_factory=dict)
    reachable: float = 1.0  # the highest price product the supported legs reach
    reserve: list[Slip] = field(default_factory=list)


def shortfalls(
    record: Mapping[str, Any] | None,
) -> tuple[dict[str, float], dict[str, float]]:
    """(family -> hit minus implied) for families with >= MIN_LEGS legs, and
    (sport -> pooled hit minus implied over all its families)."""
    fam: dict[str, float] = {}
    acc: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for key, e in ((record or {}).get("families") or {}).items():
        n = int(e["legs"])
        if n >= fr.MIN_LEGS:
            fam[key] = float(e["hit"]) - float(e["implied"])
        a = acc[key.split("|", 1)[0]]
        a[0] += n
        a[1] += float(e["hit"]) * n
        a[2] += float(e["implied"]) * n
    sport = {s: (a[1] - a[2]) / a[0] for s, a in acc.items() if a[0] >= fr.MIN_LEGS}
    return fam, sport


def measured_chance(
    leg: Mapping[str, Any],
    odds: float,
    fam: Mapping[str, float],
    sport: Mapping[str, float],
    tier_: int = TIER_REST,
) -> tuple[float, str] | None:
    key = fr.family_key(leg)
    if tier_ in TIER_SHORTFALL:
        # a family above its price is the selection's own past: chosen for it,
        # the selection then realised below its price, so the selection's
        # measured shortfall is carried forward, never the family's surplus
        short, source = TIER_SHORTFALL[tier_], "selekcja (walk-forward)"
    elif key in fam:
        short, source = min(fam[key], 0.0), "rodzina"
    elif key.split("|", 1)[0] in sport:
        short, source = min(sport[key.split("|", 1)[0]], 0.0), "sport"
    else:
        return None
    base = 1.0 / odds + short
    bounds = [(base, source), (float(leg["confidence"]), "pewność")]
    if leg.get("price_gap"):
        bounds.append((1.0 / odds, "cena (price_gap)"))
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


def tier(leg: Mapping[str, Any], plus: frozenset[str]) -> int:
    if fr.selected(leg, plus):
        return TIER_SELECTION
    if fr.family_key(leg) in plus:
        return TIER_FAMILY_PLUS
    return TIER_REST


def candidates(
    singles: Iterable[Mapping[str, Any]],
    record: Mapping[str, Any] | None,
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
    fam, sport = shortfalls(record)
    plus = frozenset(
        k for k, e in ((record or {}).get("families") or {}).items() if fr.on_plus(e)
    )
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
        t = tier(s, plus)
        mc = measured_chance(s, float(odds), fam, sport, t)
        if mc is None:
            refused["brak pomiaru rodziny / sportu"] += 1
            continue
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
        leg = Leg(s, float(odds), mc[0], mc[1], t, read, age, floor)
        if leg.match_key in skip:
            continue
        out.append(leg)
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
    """A leg's log chance in the search: a read leg gains READ_TIE, so a
    slip of read legs is not swapped for unread ones over a hair of chance
    (each swap costs a round of reads). The printed chance is never touched."""
    return math.log(x.chance) + (READ_TIE if x.read != READ_NONE else 0.0)


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
    record: Mapping[str, Any] | None,
    now: datetime.datetime,
    target: float,
    slips: int = 1,
    *,
    max_legs: int = MAX_LEGS,
    allow_rest: bool = False,
    window: tuple[datetime.datetime, datetime.datetime] | None = None,
    min_odds: float = MIN_LEG_ODDS,
    max_odds: float = MAX_LEG_ODDS,
    reads: Sequence[Any] = (),
    vetoes: Sequence[Any] = (),
    reserve: int = 0,
    built_at: str | None = None,
    slip_reads: Sequence[Any] = (),
    competitions: Sequence[str] = (),
) -> Result:
    """Up to `slips` disjoint slips (no match twice). Supported slips use only
    legs of families on the plus; with `allow_rest` the shortfall is filled
    from the rest of the coupon, each such slip marked unsupported. `reserve`
    more disjoint slips on the same terms are the analysts' buffer: their legs
    replace a slip leg a read refuses, so one read round covers them."""
    pool, refused = candidates(
        singles,
        record,
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
    counts: dict[int, int] = defaultdict(int)
    for x in pool:
        counts[x.tier] += 1
    used: set[str] = set()
    out: list[Slip] = []
    for allowed in (
        (TIER_SELECTION, TIER_FAMILY_PLUS),
        (TIER_SELECTION, TIER_FAMILY_PLUS, TIER_REST),
    ):
        if allowed[-1] == TIER_REST and not allow_rest:
            break
        while len(out) < slips + reserve:
            legs = [x for x in pool if x.tier in allowed and x.match_key not in used]
            s = best_slip(legs, target, max_legs)
            if s is None:
                break
            out.append(s)
            used.update(x.match_key for x in s.legs)
    best_per_match: dict[str, float] = {}
    for x in pool:
        if x.tier < TIER_REST:
            best_per_match[x.match_key] = max(
                best_per_match.get(x.match_key, 1.0), x.odds
            )
    reachable = math.prod(sorted(best_per_match.values(), reverse=True)[:max_legs])
    supported = sum(s.supported for s in out[:slips])
    return Result(
        out[:slips], slips, supported, dict(counts), refused, reachable, out[slips:]
    )


def concentration(slip: Slip) -> tuple[str, int] | None:
    """The family holding at least CROWD_LEGS legs of the slip, or all of a
    slip of two or more legs, with its count; else None. One family's legs
    win or lose together more than the measured chance says (one selection,
    one model), so the answer names it - a warning, never a gate."""
    count: dict[str, int] = defaultdict(int)
    for x in slip.legs:
        count[fr.family_key(x.leg)] += 1
    fam, n = max(count.items(), key=lambda kv: kv[1], default=("", 0))
    if n >= CROWD_LEGS or (n == len(slip.legs) >= 2):
        return fam, n
    return None


def unread_legs(slips: Iterable[Slip]) -> list[Leg]:
    return [x for s in slips for x in s.legs if x.read == READ_NONE]


def legs_pl(n: int) -> str:
    few = n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14)
    return f"{n} {'noga' if n == 1 else 'nogi' if few else 'nóg'}"


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


def render(
    result: Result,
    *,
    day: str,
    target: float,
    record: Mapping[str, Any] | None,
    now: datetime.datetime,
    built_at: str | None = None,
) -> str:
    """Polish markdown for the operator. The first line answers the request
    ("say no first"); no slip price, no stake."""
    lines: list[str] = []
    n_ok = result.supported
    if n_ok >= result.requested:
        lines.append(
            f"**Dzień daje {n_ok} z {result.requested} kuponów na ~{target:g} "
            "z nóg rodzin na plusie.**"
        )
    elif n_ok == 0:
        reach = (
            f" (iloczyn kursów najlepszych nóg sięga ~{result.reachable:.2f} - "
            "zasięg, nie kurs kuponu)"
            if result.reachable > 1.0
            else " (w oknie nie ma ani jednej takiej nogi)"
        )
        lines.append(
            f"**Dziś żadnego kuponu na ~{target:g} z nóg rodzin na plusie**{reach}."
        )
    else:
        lines.append(
            f"**Dzień cienki - masz {n_ok} z {result.requested} kuponów na "
            f"~{target:g} z nóg rodzin na plusie.**"
        )
    days = fr.span(record) if record else "brak"
    lines += [
        "",
        f"Poza pipeline'em: czat nie jest kuponem i nie ma bramek. Nogi z "
        f"`runs/sofa/{day}/11_coupon.json` (zbudowany {_local(built_at)}), "
        f"liczone {now.astimezone(LOCAL):%H:%M}. "
        f"Szansa nogi = min(pewność, cena przy price_gap, 1/kurs + luka rodziny "
        f"na wydrukowanych nogach {days}); nigdy sama pewność. Jedna noga z meczu. "
        "Kurs kuponu: sprawdź na ekranie Superbetu. Stawka jest Twoja.",
        "Selekcja rodzin: przewaga niepotwierdzona (T-FAMILY-SELECTION).",
        "",
    ]
    for i, s in enumerate(result.slips, 1):
        tag = "" if s.supported else " - **poza poparciem (reszta kuponu)**"
        head = (
            f"### Kupon {i}: {legs_pl(len(s.legs))}, szansa zmierzona {_pct(s.chance)}"
        )
        lines += [
            head + tag,
            "",
            "| start | mecz | zakład (słowami Superbetu) | kurs | 1/kurs | "
            "szansa | źródło | pewność | grupa | czytana | cena sprzed |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for x in s.legs:
            g = x.leg
            read = x.read
            start = _local(g.get("kickoff_utc"))
            bet = f"{g.get('superbet_market')}: {g.get('superbet_selection')}"
            lines.append(
                f"| {start} | {g.get('match')} | {bet} | {x.odds:.2f} | "
                f"{_pct(1 / x.odds)} | {_pct(x.chance)} | {x.chance_source} | "
                f"{_pct(float(g['confidence']))} | {TIER_NAMES[x.tier]} | {read} | "
                f"{_age(x)} |"
            )
        lines += [
            "",
            f"Cel ~{target:g} osiągnięty (iloczyn kursów nóg ≥ cel); kurs kuponu "
            "sprawdź na ekranie Superbetu.",
        ]
        crowd = concentration(s)
        if crowd is not None:
            fam, n = crowd
            lines.append(
                f"Uwaga: {n} z {len(s.legs)} nóg z jednej rodziny ({fam}) - wynik "
                "zależy od jednej rodziny, jej przewaga niepotwierdzona."
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
            "dopiero, gdy każda noga ma KEEP analityka; odrzucona wypada i kupon "
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
    lines.append(
        "Nogi w puli: "
        + ", ".join(
            f"{TIER_NAMES[t]} {result.candidates.get(t, 0)}" for t in sorted(TIER_NAMES)
        )
    )
    if result.refused:
        lines.append(
            "Odrzucone: "
            + ", ".join(f"{k} {v}" for k, v in sorted(result.refused.items()))
        )
    return "\n".join(lines) + "\n"
