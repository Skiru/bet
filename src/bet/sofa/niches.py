"""NICHES - is Superbet's price systematically wrong somewhere, out of sample?

The operator's hypothesis: some leagues carry a pattern the price has not
absorbed ("every match there has 10+ corners", "amateurs foul a lot"). A
pattern the price already carries is not a niche - a league where every match
has 10+ corners and Superbet posts 11.5 is a league where the pattern is
priced. So a niche is a cell

    group (competition | country/tier) x market x direction [x price band]

whose realised hit rate beats the devigged price by more than the cell's own
margin, on days the cell was NOT chosen on. Everything here is a measurement:
nothing feeds COUPON, CONFIDENCE, SHEET or the vetoes, and no constant moves.

The four places where a scan like this manufactures a niche, and what stops
each one:

  * selection on the day it is scored - walk-forward: day D's cells are chosen
    from days < D only, and the shrinkage weight K used on D is itself chosen
    on scored days < D (`walk_forward`).
  * small-n cell means - a cell's bias is shrunk toward its market's bias,
    n/(n+K) with n = distinct matches (`shrunk_bias`); K is fitted by Brier on
    out-of-sample days, the same proper score K_CENTRE is fitted by.
  * rows counted as evidence - one match settles both sides of several nested
    lines. One rung per (event, market, subject, direction) survives
    (`dedupe`), every count is of distinct matches, and every interval
    resamples whole matches.
  * the margin - a cell must beat its OWN printed price: its predicted EV is
    mean((market_p + bias) x odds) - 1, which is positive only when the bias
    clears the side's share of the margin, 1/odds - market_p. For a power
    devig the two sides' shares add to the pair margin 1/o_over + 1/o_under - 1
    (`pair_margins`), which the report prints per cell.

And the one that is left after all four: scanning hundreds of cells finds some
that pass by chance. Candidates are Benjamini-Hochberg at FDR `FDR_Q` over
every cell scanned in every grouping (`benjamini_hochberg`). BH was chosen
over "persistence across k disjoint windows" because eleven priced days cannot
supply k windows of `MIN_TRAIN_MATCHES` matches for any cell but a handful;
BH uses all the out-of-sample data and still controls the false discoveries.

`run_date = 'cache-calibration'` rows carry no price; they can describe how
stable a league's raw pattern is, never whether it is priced. Nothing in this
module reads them.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from statistics import NormalDist
from typing import Any

# ---- scope ------------------------------------------------------------------

# Market families the scan is about, by sport. A market is in scope when its
# name starts with a family and ends in `_total` or `_for` - which takes in the
# per-half and per-set scopes (corners_1h_total, games_won_set2_for) and leaves
# the rest out.
FOOTBALL_FAMILIES: tuple[str, ...] = (
    "corners", "fouls", "cards_points", "goals", "shots_on_target", "shots",
)
TENNIS_FAMILIES: tuple[str, ...] = ("games",)

# Derived joint markets and player props: their price is a joint of two
# quantities or a player's minutes, and a league cell on them would be a cell on
# the joint model, not on the league. Skipped and counted in the report.
SKIPPED_PREFIXES: tuple[str, ...] = ("player_", "both_over_", "most_", "handicap_")

# ---- named constants ---------------------------------------------------------

# A cell is scanned only once its TRAINING window holds this many distinct
# matches. At n = 20 the standard error of a hit rate near 0.5 is
# 0.5/sqrt(20) = 11 pp - already larger than any edge a price leaves - and
# below it the "every match has 10+ corners" cells are what small numbers
# produce by themselves. Lower it on the command line to look, never to decide.
MIN_TRAIN_MATCHES = 20

# The z test on a cell's out-of-sample profit is a normal approximation over
# per-match profits at odds near 2; below ~30 clusters it is not one. A cell
# with fewer out-of-sample matches gets p = 1 and cannot be a candidate.
MIN_OOS_MATCHES = 30

# A cell with positive out-of-sample ROI joins the watch list from this many
# out-of-sample matches - below it the ROI is one or two results.
WATCH_MIN_OOS_MATCHES = 10

# Benjamini-Hochberg false discovery rate over all cells scanned.
FDR_Q = 0.10

# Days of priced data that must precede the first scored day.
MIN_TRAIN_DAYS = 2

# Shrinkage is two-level: a cell's bias is pulled toward its market's bias,
# and the market's bias toward zero - the price. K is in matches of the cell,
# K_MARKET in matches of the market. Both are scored on the out-of-sample days.
# K = 0 is the raw cell mean - the operator's illusion, kept in the grid so the
# fit shows what it costs; K = inf is "every league is its market"; K_MARKET =
# inf is "the market is its price". (inf, inf) is the bare price.
#
# The second level is not decoration: on 2026-09-17..28 (competition grouping,
# 52,232 scored units), setting every league to its market's training bias
# scored a WORSE Brier than the bare price (0.240734 against 0.239239), and the
# raw cell mean worse still (0.274084) - yesterday's bias did not carry forward.
K_GRID: tuple[float, ...] = (0.0, 10.0, 25.0, 50.0, 100.0, 200.0, 400.0, math.inf)
K_MARKET_GRID: tuple[float, ...] = (0.0, 250.0, 1000.0, 4000.0, math.inf)

# Price bands on the printed odds, for the banded grouping.
PRICE_BANDS: tuple[tuple[str, float, float], ...] = (
    ("<1.60", 1.0, 1.60),
    ("1.60-2.20", 1.60, 2.20),
    ("2.20-3.20", 2.20, 3.20),
    (">=3.20", 3.20, math.inf),
)
NO_BAND = ""

BOOTSTRAP_SIMS = 2000
BOOTSTRAP_SEED = 7
POWER = 0.80
P_CLIP = 1e-3

CellKey = tuple[str, str, str, str]  # group, market, direction, band
MarketKey = tuple[str, str, str]  # market, direction, band
PairKey = tuple[int, str, str, float]  # event, market, subject, line
KPair = tuple[float, float]  # (K, K_MARKET)


def market_family(market: str) -> str | None:
    """The scanned family of `market`, or None when it is out of scope."""
    if market.startswith(SKIPPED_PREFIXES):
        return None
    if not (market.endswith("_total") or market.endswith("_for")):
        return None
    for fam in FOOTBALL_FAMILIES + TENNIS_FAMILIES:
        if market == fam or market.startswith(fam + "_"):
            # shots_on_target_* must not be filed under shots
            if fam == "shots" and market.startswith("shots_on_target"):
                continue
            return fam
    return None


def in_scope(sport: str, market: str) -> bool:
    fam = market_family(market)
    if fam is None:
        return False
    return fam in (FOOTBALL_FAMILIES if sport == "football" else TENNIS_FAMILIES)


def price_band(odds: float) -> str:
    for label, lo, hi in PRICE_BANDS:
        if lo <= odds < hi:
            return label
    return PRICE_BANDS[-1][0]


# ---- rows and units ----------------------------------------------------------


@dataclass(frozen=True)
class SettledRow:
    """One priced, graded row of `sofa_settled_row`."""

    day: str
    event: int
    sport: str
    competition: int
    market: str
    subject: str
    line: float
    direction: str
    market_p: float
    odds: float
    won: bool
    p_central: float = 0.5


@dataclass(frozen=True)
class Unit:
    """One bet the scan could have made: one rung of one side of one question."""

    day: str
    event: int
    sport: str
    group: str
    market: str
    subject: str
    direction: str
    band: str
    line: float
    market_p: float
    odds: float
    won: bool

    @property
    def cell(self) -> CellKey:
        return (self.group, self.market, self.direction, self.band)

    @property
    def market_key(self) -> MarketKey:
        return (self.market, self.direction, self.band)

    @property
    def profit(self) -> float:
        return self.odds - 1.0 if self.won else -1.0

    @property
    def residual(self) -> float:
        """Realised minus the devigged price, in probability."""
        return float(self.won) - self.market_p

    @property
    def hurdle(self) -> float:
        """The bias this side needs to break even at its printed odds."""
        return 1.0 / self.odds - self.market_p


def pair_margins(rows: Iterable[SettledRow]) -> dict[PairKey, float]:
    """Superbet's margin on every line both of whose sides were settled.

    1/o_over + 1/o_under - 1, from the two printed prices of the same event,
    market, subject and line. A line with one side only has no margin here.
    """
    sides: dict[PairKey, dict[str, float]] = defaultdict(dict)
    for r in rows:
        sides[(r.event, r.market, r.subject, r.line)][r.direction] = r.odds
    out: dict[PairKey, float] = {}
    for key, s in sides.items():
        if "OVER" in s and "UNDER" in s and s["OVER"] > 1.0 and s["UNDER"] > 1.0:
            out[key] = 1.0 / s["OVER"] + 1.0 / s["UNDER"] - 1.0
    return out


def _distance(r: SettledRow) -> float:
    """How far the rung sits from evens, read on the OVER side.

    Both sides of one line must score identically, so the distance is taken
    from one side's price and rounded: |0.45 - 0.5| and |0.55 - 0.5| differ in
    the last bit, and the two stored market_p of a pair need not sum to 1.
    """
    p_over = r.market_p if r.direction == "OVER" else 1.0 - r.market_p
    return round(abs(p_over - 0.5), 6)


# A stored market_p further than this from the devig of the row's own printed
# pair is from another price snapshot. Measured on 2026-09-17..28: 2.7% of
# 87,446 pairs off by > 1 pp, up to 13.7 pp - the offer was refreshed and one
# of the two numbers was not. Residuals must be against the price that was bet.
PRICE_SNAPSHOT_TOL = 0.005


def reprice_from_pairs(rows: Sequence[SettledRow]) -> tuple[list[SettledRow], int]:
    """market_p re-derived from the printed OVER/UNDER pair (power devig).

    The residual realised - market_p and the hurdle 1/odds - market_p are only
    meaningful if market_p is the devig of the odds the row was bet at. Where
    both sides of a line are on the table, market_p is recomputed from them
    with the pipeline's own `devig_many`; a one-sided row keeps its stored
    value. Returns the rows and how many moved by more than
    `PRICE_SNAPSHOT_TOL`.
    """
    from bet.sofa.engine import devig_many

    sides: dict[PairKey, dict[str, SettledRow]] = defaultdict(dict)
    for r in rows:
        sides[(r.event, r.market, r.subject, r.line)][r.direction] = r
    fair_of: dict[tuple[PairKey, str], float] = {}
    for key, s in sides.items():
        if "OVER" in s and "UNDER" in s:
            fair = devig_many([1.0 / s["OVER"].odds, 1.0 / s["UNDER"].odds])
            if fair is not None:
                fair_of[(key, "OVER")] = fair[0]
                fair_of[(key, "UNDER")] = fair[1]
    out: list[SettledRow] = []
    moved = 0
    for r in rows:
        fair_p = fair_of.get(((r.event, r.market, r.subject, r.line), r.direction))
        if fair_p is None:
            out.append(r)
            continue
        if abs(fair_p - r.market_p) > PRICE_SNAPSHOT_TOL:
            moved += 1
        out.append(replace(r, market_p=fair_p))
    return out, moved


def dedupe(
    rows: Iterable[SettledRow],
    group_of: Callable[[SettledRow], str | None],
    banded: bool = False,
) -> list[Unit]:
    """One rung per (event, market, subject, direction[, band]).

    The rule: the line whose price is nearest evens, ties to the lower line,
    lines quoted on both sides first. Nearest-to-evens is the rung the price is
    least extreme on, so the least exposed to the devig's treatment of long
    shots. Unbanded, the rung is chosen once per question (event, market,
    subject) and both directions take it, so an OVER unit and an UNDER unit of
    one match are the two sides of one bet, never two rungs; a direction not
    quoted there falls back to its own nearest line. Banded, each (direction,
    band) keeps its own nearest rung - the two sides of a line sit in different
    bands. Rows `group_of` maps to None are dropped.
    """
    rows = list(rows)
    best: dict[tuple[int, str, str, str, str], SettledRow] = {}
    for r in rows:
        band = price_band(r.odds) if banded else NO_BAND
        key = (r.event, r.market, r.subject, r.direction, band)
        cur = best.get(key)
        if cur is None or (_distance(r), r.line) < (_distance(cur), cur.line):
            best[key] = r
    if not banded:
        by_line: dict[tuple[int, str, str], dict[float, dict[str, SettledRow]]] = (
            defaultdict(lambda: defaultdict(dict)))
        for r in rows:
            by_line[(r.event, r.market, r.subject)][r.line][r.direction] = r
        for (ev, market, subject), lines in by_line.items():
            line = min(lines, key=lambda ln: (len(lines[ln]) < 2,
                                              _distance(next(iter(lines[ln].values()))),
                                              ln))
            for direction, r in lines[line].items():
                best[(ev, market, subject, direction, NO_BAND)] = r
    units: list[Unit] = []
    for (_, _, _, _, band), r in best.items():
        group = group_of(r)
        if group is None:
            continue
        units.append(Unit(
            day=r.day, event=r.event, sport=r.sport, group=group, market=r.market,
            subject=r.subject, direction=r.direction, band=band, line=r.line,
            market_p=r.market_p, odds=r.odds, won=r.won,
        ))
    units.sort(key=lambda u: (u.day, u.event, u.market, u.subject, u.direction, u.band))
    return units


# ---- accumulators ------------------------------------------------------------


@dataclass
class Acc:
    """Sums over a set of units, with distinct matches kept."""

    events: set[int] = field(default_factory=set)
    units: int = 0
    s_residual: float = 0.0
    s_mp_odds: float = 0.0
    s_odds: float = 0.0
    s_hurdle: float = 0.0
    s_profit: float = 0.0
    wins: int = 0

    def add(self, u: Unit) -> None:
        self.events.add(u.event)
        self.units += 1
        self.s_residual += u.residual
        self.s_mp_odds += u.market_p * u.odds
        self.s_odds += u.odds
        self.s_hurdle += u.hurdle
        self.s_profit += u.profit
        self.wins += int(u.won)

    @property
    def matches(self) -> int:
        return len(self.events)

    @property
    def bias(self) -> float:
        return self.s_residual / self.units if self.units else 0.0

    @property
    def hurdle(self) -> float:
        return self.s_hurdle / self.units if self.units else 0.0

    @property
    def roi(self) -> float:
        return self.s_profit / self.units if self.units else 0.0

    def predicted_ev(self, bias: float) -> float:
        """Mean EV per unit at the printed odds if the true rate is market_p + bias."""
        if not self.units:
            return -1.0
        return (self.s_mp_odds + bias * self.s_odds) / self.units - 1.0


def accumulate(
    units: Iterable[Unit],
) -> tuple[dict[CellKey, Acc], dict[MarketKey, Acc]]:
    cells: dict[CellKey, Acc] = defaultdict(Acc)
    markets: dict[MarketKey, Acc] = defaultdict(Acc)
    for u in units:
        cells[u.cell].add(u)
        markets[u.market_key].add(u)
    return dict(cells), dict(markets)


def _toward(n: int, value: float, k: float, target: float) -> float:
    """n/(n+k) x value + k/(n+k) x target; k = inf is the target itself."""
    if n <= 0 or math.isinf(k):
        return target
    return (n * value + k * target) / (n + k)


def shrunk_bias(
    cell: Acc | None, market: Acc | None, k: float, k_market: float = math.inf,
) -> float:
    """The cell's bias, shrunk toward its market's, shrunk toward the price.

    n = distinct matches at both levels: rows of one match are one piece of
    evidence, and so are both teams' `_for` rows.
    """
    target = 0.0
    if market is not None:
        target = _toward(market.matches, market.bias, k_market, 0.0)
    if cell is None:
        return target
    return _toward(cell.matches, cell.bias, k, target)


def _clip(p: float) -> float:
    return min(1.0 - P_CLIP, max(P_CLIP, p))


# ---- walk-forward ------------------------------------------------------------


@dataclass
class WalkForward:
    grouping: str
    days: list[str]
    days_scored: list[str] = field(default_factory=list)
    days_bet: list[str] = field(default_factory=list)
    k_by_day: dict[str, KPair] = field(default_factory=dict)
    # Brier sums over every scored test unit, per (K, K_MARKET), and for the
    # bare price.
    brier_sum: dict[KPair, float] = field(default_factory=dict)
    brier_price: float = 0.0
    brier_n: int = 0
    selections: dict[str, list[CellKey]] = field(default_factory=dict)
    selector_bets: list[Unit] = field(default_factory=list)
    baseline_bets: list[Unit] = field(default_factory=list)
    cells_scanned: set[CellKey] = field(default_factory=set)


def best_k(brier_sum: dict[KPair, float]) -> KPair | None:
    """The (K, K_MARKET) with the lowest summed Brier; ties to more shrinkage."""
    if not brier_sum:
        return None
    return min(brier_sum, key=lambda k: (brier_sum[k], -k[1], -k[0]))


def walk_forward(
    units: Sequence[Unit],
    grouping: str,
    min_matches: int = MIN_TRAIN_MATCHES,
    min_train_days: int = MIN_TRAIN_DAYS,
    k_grid: Sequence[float] = K_GRID,
    k_market_grid: Sequence[float] = K_MARKET_GRID,
) -> WalkForward:
    """Choose each day's cells from the days before it; score them on it.

    For every day D past `min_train_days`:
      1. train = units of days < D, test = units of day D. Nothing of D is read
         before step 4.
      2. K_D = the (K, K_MARKET) with the best Brier summed over the scored
         days BEFORE D;
         the first scored day has none, so it is scored and not bet.
      3. a cell is selected when it holds >= `min_matches` training matches and
         its shrunk bias gives a positive predicted EV at its training odds.
      4. the selector bets every day-D unit of a selected cell; the baseline
         bets every day-D unit of the same (market, direction, band), with no
         league selection. Then every K is scored on day D.
    """
    days = sorted({u.day for u in units})
    wf = WalkForward(grouping=grouping, days=days)
    by_day: dict[str, list[Unit]] = defaultdict(list)
    for u in units:
        by_day[u.day].append(u)
    train_cells: dict[CellKey, Acc] = defaultdict(Acc)
    train_markets: dict[MarketKey, Acc] = defaultdict(Acc)
    for i, day in enumerate(days):
        test = by_day[day]
        if i >= min_train_days:
            k_day = best_k(wf.brier_sum)
            if k_day is not None:
                wf.k_by_day[day] = k_day
                chosen: list[CellKey] = []
                for key, acc in train_cells.items():
                    if acc.matches < min_matches:
                        continue
                    wf.cells_scanned.add(key)
                    b = shrunk_bias(acc, train_markets.get(key[1:]), *k_day)
                    if acc.predicted_ev(b) > 0.0:
                        chosen.append(key)
                chosen.sort()
                wf.selections[day] = chosen
                wf.days_bet.append(day)
                chosen_set = set(chosen)
                chosen_markets = {c[1:] for c in chosen}
                for u in test:
                    if u.cell in chosen_set:
                        wf.selector_bets.append(u)
                    if u.market_key in chosen_markets:
                        wf.baseline_bets.append(u)
            # score every K on this day, trained on days before it
            for u in test:
                y = float(u.won)
                cell = train_cells.get(u.cell)
                market = train_markets.get(u.market_key)
                for km in k_market_grid:
                    target = 0.0 if market is None else _toward(
                        market.matches, market.bias, km, 0.0)
                    for k in k_grid:
                        b = target if cell is None else _toward(
                            cell.matches, cell.bias, k, target)
                        p = _clip(u.market_p + b)
                        wf.brier_sum[(k, km)] = (wf.brier_sum.get((k, km), 0.0)
                                                 + (p - y) ** 2)
                wf.brier_price += (_clip(u.market_p) - y) ** 2
                wf.brier_n += 1
            wf.days_scored.append(day)
        # only now does day D join the training window
        for u in test:
            train_cells[u.cell].add(u)
            train_markets[u.market_key].add(u)
    return wf


# ---- uncertainty -------------------------------------------------------------

Cluster = tuple[float, float]  # (numerator, denominator) summed over one match


def clusters(units: Iterable[Unit], value: Callable[[Unit], float]) -> list[Cluster]:
    """Per-match (sum of value, number of units), in event order."""
    by_ev: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for u in units:
        c = by_ev[u.event]
        c[0] += value(u)
        c[1] += 1.0
    return [(v[0], v[1]) for _, v in sorted(by_ev.items())]


def bootstrap_ratio(
    data: Sequence[Cluster], sims: int = BOOTSTRAP_SIMS, seed: int = BOOTSTRAP_SEED
) -> tuple[float, float] | None:
    """95% interval of sum(num)/sum(den), resampling whole matches."""
    if len(data) < 5:
        return None
    rng = random.Random(seed)
    m = len(data)
    stats: list[float] = []
    for _ in range(sims):
        num = den = 0.0
        for _ in range(m):
            a, b = data[rng.randrange(m)]
            num += a
            den += b
        if den:
            stats.append(num / den)
    stats.sort()
    return stats[int(0.025 * len(stats))], stats[int(0.975 * len(stats)) - 1]


def bootstrap_ratio_diff(
    data: Sequence[tuple[float, float, float, float]],
    sims: int = BOOTSTRAP_SIMS,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float] | None:
    """95% interval of ROI_a - ROI_b, resampling matches jointly.

    Each tuple is one match: (profit_a, units_a, profit_b, units_b). Used for
    the selector against the baseline, whose bets it is a subset of.
    """
    if len(data) < 5:
        return None
    rng = random.Random(seed)
    m = len(data)
    stats: list[float] = []
    for _ in range(sims):
        pa = ua = pb = ub = 0.0
        for _ in range(m):
            a, b, c, d = data[rng.randrange(m)]
            pa += a
            ua += b
            pb += c
            ub += d
        if ua and ub:
            stats.append(pa / ua - pb / ub)
    if not stats:
        return None
    stats.sort()
    return stats[int(0.025 * len(stats))], stats[int(0.975 * len(stats)) - 1]


def ratio_z_pvalue(
    data: Sequence[Cluster], min_clusters: int = MIN_OOS_MATCHES,
) -> float:
    """One-sided p for "sum(num)/sum(den) > 0", cluster-robust.

    Linearised ratio estimator over matches: d_j = num_j - R x den_j,
    SE = sqrt(m/(m-1) x sum d_j^2) / sum den. Returns 1.0 below
    `min_clusters`, where the normal approximation is not one.
    """
    m = len(data)
    if m < min_clusters:
        return 1.0
    num = sum(a for a, _ in data)
    den = sum(b for _, b in data)
    if den <= 0:
        return 1.0
    r = num / den
    ss = sum((a - r * b) ** 2 for a, b in data)
    if ss <= 0:
        return 0.0 if r > 0 else 1.0
    se = math.sqrt(ss * m / (m - 1)) / den
    return 1.0 - NormalDist().cdf(r / se)


def benjamini_hochberg(pvalues: dict[Any, float], q: float = FDR_Q) -> set[Any]:
    """The keys BH rejects at false discovery rate q (step-up)."""
    items = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(items)
    cut = 0
    for i, (_, p) in enumerate(items, start=1):
        if p <= q * i / m:
            cut = i
    return {k for k, _ in items[:cut]}


def matches_needed(
    edge_per_unit: float,
    sd_per_match: float,
    units_per_match: float,
    alpha: float,
    power: float = POWER,
) -> float | None:
    """Distinct matches before a true edge (ROI per unit) is detectable.

    One-sided test at `alpha` with `power`, on per-match profit:
    n = ((z_{1-alpha} + z_power) x sd / (edge x units_per_match))^2.
    """
    if edge_per_unit <= 0 or sd_per_match <= 0 or units_per_match <= 0:
        return None
    nd = NormalDist()
    z = nd.inv_cdf(1.0 - alpha) + nd.inv_cdf(power)
    return (z * sd_per_match / (edge_per_unit * units_per_match)) ** 2


def match_profit_sd(units: Iterable[Unit]) -> tuple[float, float]:
    """(SD of per-match profit, mean units per match)."""
    cl = clusters(units, lambda u: u.profit)
    if len(cl) < 2:
        return 0.0, 0.0
    xs = [a for a, _ in cl]
    mean = sum(xs) / len(xs)
    var = sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var), sum(b for _, b in cl) / len(cl)


# ---- summaries ---------------------------------------------------------------


def roi_summary(units: Sequence[Unit]) -> dict[str, Any]:
    cl = clusters(units, lambda u: u.profit)
    n = len(units)
    profit = sum(u.profit for u in units)
    ci = bootstrap_ratio(cl)
    return {
        "bets": n,
        "matches": len(cl),
        "won": sum(1 for u in units if u.won),
        "units_profit": round(profit, 4),
        "roi": round(profit / n, 4) if n else None,
        "roi_ci95": [round(ci[0], 4), round(ci[1], 4)] if ci else None,
    }


def selector_vs_baseline(wf: WalkForward) -> dict[str, Any]:
    sel_keys = {(u.event, u.market, u.subject, u.direction, u.band)
                for u in wf.selector_bets}
    per_match: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    for u in wf.baseline_bets:
        c = per_match[u.event]
        c[2] += u.profit
        c[3] += 1.0
        if (u.event, u.market, u.subject, u.direction, u.band) in sel_keys:
            c[0] += u.profit
            c[1] += 1.0
    data = [(a, b, c, d) for a, b, c, d in per_match.values() if d]
    diff = bootstrap_ratio_diff(data) if wf.selector_bets else None
    return {
        "selector": roi_summary(wf.selector_bets),
        "baseline": roi_summary(wf.baseline_bets),
        "diff_ci95": [round(diff[0], 4), round(diff[1], 4)] if diff else None,
    }


def k_label(k: float) -> float | str:
    """K for JSON: inf has no JSON spelling."""
    return "inf" if math.isinf(k) else k


def kpair_label(k: KPair) -> list[float | str]:
    return [k_label(k[0]), k_label(k[1])]


def k_fit(wf: WalkForward) -> dict[str, Any]:
    n = wf.brier_n
    rows = [
        {"k": k_label(k), "k_market": k_label(km), "brier": round(s / n, 6)}
        for (k, km), s in sorted(wf.brier_sum.items())
    ] if n else []
    k_final = best_k(wf.brier_sum)
    return {
        "scored_units": n,
        "brier_by_k": rows,
        "brier_price_only": round(wf.brier_price / n, 6) if n else None,
        "k_final": None if k_final is None else kpair_label(k_final),
    }


def cell_label(key: CellKey) -> dict[str, str]:
    group, market, direction, band = key
    return {"group": group, "market": market, "direction": direction, "band": band}


def cell_report(
    key: CellKey,
    in_sample: Acc,
    market: Acc | None,
    k: KPair,
    oos: Sequence[Unit],
    margins: Sequence[float],
    cell_units: Sequence[Unit],
    m_tests: int,
) -> dict[str, Any]:
    """Everything the report says about one cell (`cell_units` = its units)."""
    b_shrunk = shrunk_bias(in_sample, market, *k)
    ev = in_sample.predicted_ev(b_shrunk)
    raw_ev = in_sample.predicted_ev(in_sample.bias)
    bias_ci = bootstrap_ratio(clusters(cell_units, lambda u: u.residual))
    sd, upm = match_profit_sd(cell_units)
    oos_cl = clusters(oos, lambda u: u.profit)
    oos_summary = roi_summary(oos)
    # "if the raw in-sample edge were true": the claim a watch-list cell makes
    need_single = matches_needed(raw_ev, sd, upm, 0.05) if raw_ev > 0 else None
    need_bh = (matches_needed(raw_ev, sd, upm, FDR_Q / max(m_tests, 1))
               if raw_ev > 0 else None)
    need_5 = matches_needed(0.05, sd, upm, FDR_Q / max(m_tests, 1))
    return {
        **cell_label(key),
        "matches": in_sample.matches,
        "units": in_sample.units,
        "raw_bias": round(in_sample.bias, 4),
        "raw_bias_ci95": ([round(bias_ci[0], 4), round(bias_ci[1], 4)]
                          if bias_ci else None),
        "shrunk_bias": round(b_shrunk, 4),
        "market_bias": round(market.bias, 4) if market else None,
        "hurdle": round(in_sample.hurdle, 4),
        "pair_margin": round(sum(margins) / len(margins), 4) if margins else None,
        "pair_margin_n": len(margins),
        "predicted_ev": round(ev, 4),
        "raw_ev": round(raw_ev, 4),
        "in_sample_roi": round(in_sample.roi, 4),
        "oos": oos_summary,
        "oos_p": round(ratio_z_pvalue(oos_cl), 6),
        "matches_needed_single_test": (None if need_single is None
                                       else math.ceil(need_single)),
        "matches_needed_bh": None if need_bh is None else math.ceil(need_bh),
        "matches_needed_bh_edge_5pp": None if need_5 is None else math.ceil(need_5),
    }


# ---- context (in-sample, labelled as such) ------------------------------------


def market_bias_table(units: Sequence[Unit]) -> list[dict[str, Any]]:
    """Per (market, direction): realised minus price and ROI. In-sample context."""
    _, markets = accumulate(u for u in units if u.band == NO_BAND)
    out = []
    for (market, direction, _), acc in sorted(markets.items()):
        out.append({
            "market": market, "direction": direction, "matches": acc.matches,
            "units": acc.units, "bias": round(acc.bias, 4),
            "hurdle": round(acc.hurdle, 4), "roi": round(acc.roi, 4),
        })
    return out


def split_half_persistence(
    units: Sequence[Unit], family: str, direction: str = "OVER", min_matches: int = 10,
) -> dict[str, Any]:
    """Does a group's bias on the first half of the days predict the second half?

    Pearson correlation (unweighted) over groups with >= `min_matches` in both
    halves, and
    what the first half's positive groups then did in the second half. The
    halves are the first floor(n/2) distinct days and the rest.
    """
    fam_units = [u for u in units
                 if market_family(u.market) == family and u.direction == direction]
    days = sorted({u.day for u in fam_units})
    if len(days) < 2:
        return {"family": family, "groups": 0}
    first = set(days[: len(days) // 2])
    a: dict[str, Acc] = defaultdict(Acc)
    b: dict[str, Acc] = defaultdict(Acc)
    for u in fam_units:
        (a if u.day in first else b)[u.group].add(u)
    groups = [g for g in a if g in b and a[g].matches >= min_matches
              and b[g].matches >= min_matches]
    xs = [a[g].bias for g in groups]
    ys = [b[g].bias for g in groups]
    corr = _pearson(xs, ys)
    pos = [g for g in groups if a[g].bias > 0]
    later = Acc()
    for u in fam_units:
        if u.day not in first and u.group in pos:
            later.add(u)
    return {
        "family": family, "direction": direction,
        "first_days": [min(first), max(first)],
        "second_days": [days[len(first)], days[-1]],
        "groups": len(groups), "corr": None if corr is None else round(corr, 3),
        "first_positive_groups": len(pos),
        "their_second_half_bias": round(later.bias, 4) if later.units else None,
        "their_second_half_roi": round(later.roi, 4) if later.units else None,
        "their_second_half_units": later.units,
    }


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def row_level_bias(
    rows: Iterable[SettledRow], market: str, direction: str,
    day_from: str = "", day_to: str = "9999",
) -> dict[str, Any]:
    """Realised minus price over RAW rows (every rung, both sides kept).

    Kept only to reproduce figures quoted elsewhere at row level; the scan
    itself never reads rows, only deduplicated units.
    """
    n = 0
    s_res = 0.0
    events: set[int] = set()
    for r in rows:
        if (r.market == market and r.direction == direction
                and day_from <= r.day <= day_to):
            n += 1
            s_res += float(r.won) - r.market_p
            events.add(r.event)
    return {"market": market, "direction": direction, "from": day_from or None,
            "to": None if day_to == "9999" else day_to, "rows": n,
            "matches": len(events), "bias": round(s_res / n, 4) if n else None}


def disagreement_roi(
    rows: Iterable[SettledRow], market: str, threshold: float = 0.10,
) -> dict[str, Any]:
    """Row-level ROI where p_central sits >= threshold above the break-even 1/odds.

    A proxy for "the raw team sample is 10 pp above break-even": the settled
    table keeps p_central (the shrunk model), not the raw sample frequency.
    """
    n = 0
    profit = 0.0
    for r in rows:
        if r.market == market and r.p_central - 1.0 / r.odds >= threshold:
            n += 1
            profit += (r.odds - 1.0) if r.won else -1.0
    return {"market": market, "threshold": threshold, "bets": n,
            "roi": round(profit / n, 4) if n else None}


# ---- the scan ----------------------------------------------------------------


@dataclass
class Scan:
    grouping: str
    units: list[Unit]
    wf: WalkForward
    cells: dict[CellKey, Acc]
    markets: dict[MarketKey, Acc]
    k_final: KPair


def run_scan(
    rows: Sequence[SettledRow],
    grouping: str,
    group_of: Callable[[SettledRow], str | None],
    banded: bool,
    min_matches: int = MIN_TRAIN_MATCHES,
    min_train_days: int = MIN_TRAIN_DAYS,
) -> Scan:
    units = dedupe(rows, group_of, banded=banded)
    wf = walk_forward(units, grouping, min_matches=min_matches,
                      min_train_days=min_train_days)
    cells, markets = accumulate(units)
    k = best_k(wf.brier_sum)
    return Scan(grouping, units, wf, cells, markets,
                (math.inf, math.inf) if k is None else k)


def power_table(scan: Scan | None, m_tests: int,
                edges: Sequence[float] = (0.03, 0.05, 0.08, 0.10)) -> dict[str, Any]:
    """How many distinct matches one cell needs before an edge is visible.

    Per-bet profit SD pooled over the scan's units (one bet per match), at a
    single test (alpha 0.05) and at BH's threshold for a lone discovery among
    `m_tests` cells (alpha = FDR_Q / m). Set beside the largest cells and how
    fast they grow, this is the answer to "what would change the verdict".
    """
    if scan is None or len(scan.units) < 2:
        return {}
    profits = [u.profit for u in scan.units]
    mean = sum(profits) / len(profits)
    sd = math.sqrt(sum((x - mean) ** 2 for x in profits) / (len(profits) - 1))
    n_days = max(len(scan.wf.days), 1)
    # one row per (group, market): both directions of a cell hold the same matches
    seen: set[tuple[str, str]] = set()
    biggest: list[tuple[CellKey, Acc]] = []
    for key, acc in sorted(scan.cells.items(), key=lambda kv: (-kv[1].matches, kv[0])):
        if (key[0], key[1]) not in seen and len(biggest) < 5:
            seen.add((key[0], key[1]))
            biggest.append((key, acc))
    alpha_bh = FDR_Q / max(m_tests, 1)
    rows = []
    for e in edges:
        one = matches_needed(e, sd, 1.0, 0.05)
        bh = matches_needed(e, sd, 1.0, alpha_bh)
        rows.append({"edge_roi": e,
                     "matches_single_test": None if one is None else math.ceil(one),
                     "matches_bh": None if bh is None else math.ceil(bh)})
    return {
        "grouping": scan.grouping,
        "sd_profit_per_bet": round(sd, 4),
        "alpha_bh": alpha_bh,
        "rows": rows,
        "days": n_days,
        "largest_cells": [
            {**cell_label(k), "matches": acc.matches,
             "matches_per_day": round(acc.matches / n_days, 2)}
            for k, acc in biggest
        ],
    }


def scan_all(
    rows: Sequence[SettledRow],
    groupings: dict[str, tuple[Callable[[SettledRow], str | None], bool]],
    min_matches: int = MIN_TRAIN_MATCHES,
    min_train_days: int = MIN_TRAIN_DAYS,
    watch_limit: int = 15,
) -> dict[str, Any]:
    """Every grouping, one BH family across all of them, candidates and watch list."""
    scoped, repriced = reprice_from_pairs(
        [r for r in rows if in_scope(r.sport, r.market)])
    margins = pair_margins(scoped)
    scans = [run_scan(scoped, name, fn, banded, min_matches, min_train_days)
             for name, (fn, banded) in groupings.items()]

    # per cell: its out-of-sample bets and p-value; the BH family is every cell
    # that reached min_matches in some training window, in any grouping.
    pvals: dict[tuple[str, CellKey], float] = {}
    oos_by_cell: dict[tuple[str, CellKey], list[Unit]] = defaultdict(list)
    for s in scans:
        for u in s.wf.selector_bets:
            oos_by_cell[(s.grouping, u.cell)].append(u)
        for key in s.wf.cells_scanned:
            oos = oos_by_cell.get((s.grouping, key), [])
            pvals[(s.grouping, key)] = ratio_z_pvalue(clusters(oos, lambda u: u.profit))
    m_tests = len(pvals)
    rejected = benjamini_hochberg(pvals) if pvals else set()

    out_scans: list[dict[str, Any]] = []
    all_candidates: list[dict[str, Any]] = []
    for s in scans:
        by_cell: dict[CellKey, list[Unit]] = defaultdict(list)
        for u in s.units:
            by_cell[u.cell].append(u)

        def report(key: CellKey, s: Scan = s,
                   by_cell: dict[CellKey, list[Unit]] = by_cell) -> dict[str, Any]:
            cell_units = by_cell[key]
            # the pair margin is the same whichever side the cell bets
            cell_margins = [margins[(u.event, u.market, u.subject, u.line)]
                            for u in cell_units
                            if (u.event, u.market, u.subject, u.line) in margins]
            rep = cell_report(
                key, s.cells[key], s.markets.get(key[1:]), s.k_final,
                oos_by_cell.get((s.grouping, key), []), cell_margins,
                cell_units, m_tests)
            rep["grouping"] = s.grouping
            return rep

        final_positive = {
            key for key, acc in s.cells.items()
            if acc.matches >= min_matches
            and acc.predicted_ev(
                shrunk_bias(acc, s.markets.get(key[1:]), *s.k_final)) > 0
        }
        # promising in-sample in the operator's sense: the raw cell mean clears
        # its own margin on enough matches. Watched, never proven by this.
        raw_positive = {
            key for key, acc in s.cells.items()
            if acc.matches >= min_matches and acc.predicted_ev(acc.bias) > 0
        }
        candidates: list[dict[str, Any]] = []
        watch: list[dict[str, Any]] = []
        for key in sorted(set(s.cells)):
            tag = (s.grouping, key)
            oos = oos_by_cell.get(tag, [])
            oos_roi = (sum(u.profit for u in oos) / len(oos)) if oos else None
            is_candidate = (tag in rejected and oos_roi is not None and oos_roi > 0
                            and key in final_positive)
            if is_candidate:
                candidates.append(report(key))
            elif key in final_positive or key in raw_positive or (
                oos_roi is not None and oos_roi > 0
                and len({u.event for u in oos}) >= WATCH_MIN_OOS_MATCHES
            ):
                watch.append(report(key))
        # by the claim the cell makes in-sample; the shrunk EV is ~ -hurdle
        # for every cell once the fit says "trust the price", so it cannot rank
        watch.sort(key=lambda r: (-r["raw_ev"], -r["matches"]))
        raw_top = sorted(
            (key for key, acc in s.cells.items() if acc.matches >= 5),
            key=lambda k: -(s.cells[k].bias - s.cells[k].hurdle),
        )[:10]
        all_candidates.extend(candidates)
        out_scans.append({
            "grouping": s.grouping,
            "units": len(s.units),
            "matches": len({u.event for u in s.units}),
            "days": s.wf.days,
            "days_scored": s.wf.days_scored,
            "days_bet": s.wf.days_bet,
            "k_by_day": {d: kpair_label(k) for d, k in s.wf.k_by_day.items()},
            "k_fit": k_fit(s.wf),
            "cells_total": len(s.cells),
            "cells_scanned": len(s.wf.cells_scanned),
            "cells_selected_by_day": {d: len(c) for d, c in s.wf.selections.items()},
            "headline": selector_vs_baseline(s.wf),
            "candidates": candidates,
            "watch": watch[:watch_limit],
            "watch_total": len(watch),
            "raw_top": [
                {**cell_label(k), "matches": s.cells[k].matches,
                 "raw_bias": round(s.cells[k].bias, 4),
                 "hurdle": round(s.cells[k].hurdle, 4),
                 "shrunk_bias": round(shrunk_bias(s.cells[k], s.markets.get(k[1:]),
                                                  *s.k_final), 4),
                 "in_sample_roi": round(s.cells[k].roi, 4)}
                for k in raw_top
            ],
        })

    # context tables read the plain competition grouping, whatever else ran
    plain = [s for s in scans if s.grouping == "competition"]
    comp_units = plain[0].units if plain else (scans[0].units if scans else [])
    all_margins = list(margins.values())
    return {
        "power": power_table(plain[0] if plain else (scans[0] if scans else None),
                             m_tests),
        "verdict": "NISZA_ZNALEZIONA" if all_candidates else "BRAK_NISZY",
        "candidates": all_candidates,
        "bh": {"m": m_tests, "q": FDR_Q, "rejected": len(rejected)},
        "scans": out_scans,
        "repriced_rows": repriced,
        "margin": {
            "pairs": len(all_margins),
            "mean": (round(sum(all_margins) / len(all_margins), 4)
                     if all_margins else None),
        },
        "context": {
            "market_bias": market_bias_table(comp_units),
            "persistence": [split_half_persistence(comp_units, fam, min_matches=5)
                            for fam in ("corners", "goals", "fouls", "cards_points",
                                        "shots", "shots_on_target", "games")],
            "disagreement_proxy": [disagreement_roi(scoped, m)
                                   for m in ("corners_total", "corners_for")],
            "row_level_corners_total": [
                row_level_bias(scoped, "corners_total", d, lo, hi)
                for d in ("OVER", "UNDER")
                for lo, hi in (("", "9999"), ("", "2026-09-22"), ("2026-09-23", "9999"))
            ],
        },
    }
