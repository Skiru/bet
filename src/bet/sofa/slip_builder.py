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
import itertools
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from bet.sofa import family_record as fr

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
# START_MARGIN cannot be placed in time, and the search keeps the POOL legs
# that buy price most cheaply.
MIN_LEG_ODDS = 1.10
MAX_LEG_ODDS = 2.00
MAX_LEGS = 5
START_MARGIN = datetime.timedelta(minutes=10)
POOL = 28

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
) -> tuple[list[Leg], dict[str, int]]:
    fam, sport = shortfalls(record)
    plus = frozenset(
        k for k, e in ((record or {}).get("families") or {}).items() if fr.on_plus(e)
    )
    skip = set(exclude_matches)
    out: list[Leg] = []
    refused: dict[str, int] = defaultdict(int)
    seen: set[tuple[Any, ...]] = set()
    for s in singles:
        ident = (
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
        kickoff = s.get("kickoff_utc")
        if odds is None or s.get("confidence") is None:
            refused["brak ceny lub pewności"] += 1
            continue
        if (
            not kickoff
            or datetime.datetime.fromisoformat(str(kickoff).replace("Z", "+00:00"))
            <= now + START_MARGIN
        ):
            refused["rozpoczęty lub za chwilę"] += 1
            continue
        if not min_odds <= float(odds) <= max_odds:
            refused["kurs poza przedziałem"] += 1
            continue
        t = tier(s, plus)
        mc = measured_chance(s, float(odds), fam, sport, t)
        if mc is None:
            refused["brak pomiaru rodziny / sportu"] += 1
            continue
        leg = Leg(s, float(odds), mc[0], mc[1], t)
        if leg.match_key in skip:
            continue
        out.append(leg)
    return out, dict(refused)


def best_slip(
    legs: Sequence[Leg], target: float, max_legs: int = MAX_LEGS, pool: int = POOL
) -> Slip | None:
    """The slip of at most `max_legs` legs, one per match, whose price product
    reaches `target` with the highest measured chance. The search keeps each
    match's cheapest leg and the `pool` cheapest of those."""
    per_match: dict[str, Leg] = {}
    for x in legs:
        cur = per_match.get(x.match_key)
        if cur is None or (x.cost, -x.odds) < (cur.cost, -cur.odds):
            per_match[x.match_key] = x
    ranked = sorted(
        per_match.values(),
        key=lambda x: (x.cost, -x.odds, str(x.leg.get("kickoff_utc"))),
    )[:pool]
    need = math.log(target)
    best: tuple[float, int, list[Leg]] | None = None
    for k in range(1, max_legs + 1):
        for combo in itertools.combinations(ranked, k):
            if sum(math.log(x.odds) for x in combo) < need - 1e-9:
                continue
            score = sum(math.log(x.chance) for x in combo)
            if best is None or (score, -k) > (best[0], -best[1]):
                best = (score, k, list(combo))
    if best is None:
        return None
    return Slip(sorted(best[2], key=lambda x: str(x.leg.get("kickoff_utc"))))


def build(
    singles: Sequence[Mapping[str, Any]],
    record: Mapping[str, Any] | None,
    now: datetime.datetime,
    target: float,
    slips: int = 1,
    *,
    max_legs: int = MAX_LEGS,
    allow_rest: bool = False,
    min_odds: float = MIN_LEG_ODDS,
    max_odds: float = MAX_LEG_ODDS,
) -> Result:
    """Up to `slips` disjoint slips (no match twice). Supported slips use only
    legs of families on the plus; with `allow_rest` the shortfall is filled
    from the rest of the coupon, each such slip marked unsupported."""
    pool, refused = candidates(
        singles, record, now, min_odds=min_odds, max_odds=max_odds
    )
    counts: dict[int, int] = defaultdict(int)
    for x in pool:
        counts[x.tier] += 1
    used: set[str] = set()
    out: list[Slip] = []
    supported = 0
    for allowed in (
        (TIER_SELECTION, TIER_FAMILY_PLUS),
        (TIER_SELECTION, TIER_FAMILY_PLUS, TIER_REST),
    ):
        if allowed[-1] == TIER_REST and not allow_rest:
            break
        while len(out) < slips:
            legs = [x for x in pool if x.tier in allowed and x.match_key not in used]
            s = best_slip(legs, target, max_legs)
            if s is None:
                break
            out.append(s)
            supported += s.supported
            used.update(x.match_key for x in s.legs)
    best_per_match: dict[str, float] = {}
    for x in pool:
        if x.tier < TIER_REST:
            best_per_match[x.match_key] = max(
                best_per_match.get(x.match_key, 1.0), x.odds
            )
    reachable = math.prod(sorted(best_per_match.values(), reverse=True)[:max_legs])
    return Result(out, slips, supported, dict(counts), refused, reachable)


def legs_pl(n: int) -> str:
    few = n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14)
    return f"{n} {'noga' if n == 1 else 'nogi' if few else 'nóg'}"


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%".replace(".", ",")


def render(
    result: Result,
    *,
    day: str,
    target: float,
    record: Mapping[str, Any] | None,
    now: datetime.datetime,
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
        lines.append(
            f"**Dziś żadnego kuponu na ~{target:g} z nóg rodzin na plusie** "
            f"(najwyżej ~{result.reachable:.2f} w jednym kuponie)."
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
        f"`runs/sofa/{day}/11_coupon.json`, stan na {now:%Y-%m-%d %H:%M}Z. "
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
            "| start (UTC) | mecz | zakład (słowami Superbetu) | kurs | 1/kurs | "
            "szansa | źródło | pewność | grupa | czytana |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for x in s.legs:
            g = x.leg
            reads = g.get("reads") or []
            read = ", ".join(sorted({str(r.get("verdict")) for r in reads})) or "nie"
            start = str(g.get("kickoff_utc"))[5:16].replace("T", " ")
            bet = f"{g.get('superbet_market')}: {g.get('superbet_selection')}"
            lines.append(
                f"| {start} | {g.get('match')} | {bet} | {x.odds:.2f} | "
                f"{_pct(1 / x.odds)} | {_pct(x.chance)} | {x.chance_source} | "
                f"{_pct(float(g['confidence']))} | {TIER_NAMES[x.tier]} | {read} |"
            )
        lines += [
            "",
            f"Iloczyn kursów nóg {s.price_product:.2f} służy tylko sprawdzeniu "
            f"celu - to nie jest kurs kuponu.",
            "",
        ]
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
