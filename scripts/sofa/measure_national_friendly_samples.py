#!/usr/bin/env python3
"""Which goal sample should a national-team FRIENDLY read? Measured on the cache.

Pre-registered in docs/sofa/evidence/national_friendly_samples_2026-10-13.md.
For a national-team friendly (851 men, 852 women) SAMPLES' same-competition
rule (comparability.pick_same_competition) takes the newest ten matches of the
friendly competition itself - for Argentina's women it reached 822 days back
past two Copa America tournaments. 851 has been on the friendly exclusion list
since 2026-10-04, so a men's friendly gets its competitive sample live (D);
852 is on the `allowed` list, so a women's friendly reads friendlies only (A).

Per side (n = 10, minimum 5):

  A  same-competition pick (today's rule for 852), else B
  B  newest ten national-team matches, friendlies and competitive together
  C  every pool match inside A's window (A's oldest .. kick-off), else B
  D  newest ten competitive matches (no 851 / 852), else B - the live men's rule

Centre: the sample mean shrunk toward the fixture competition's league
baseline with K (calibrate_from_cache.shrunk_centre without its Played);
a total pools both sides' match totals, a shared match once. Scored with the
NB log-loss at the actual count (alpha from config/sofa_count_dispersion.json)
and the squared error; every variant minus A (and B / C minus D), match
bootstrap 2000, seed 0.

Read-only: the DB is opened mode=ro; nothing is written but --json-out.

    PYTHONPATH=src:. .venv/bin/python \\
        scripts/sofa/measure_national_friendly_samples.py \\
        [--from 2015-01-01] [--to 2026-10-12] [--prior baseline|asof] [--json-out f]
"""

from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
import statistics
import sys
import time
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.centre_replay import boot_by_group, nb_logloss  # noqa: E402
from bet.sofa.comparability import (  # noqa: E402
    FRIENDLY_COMPETITION_IDS,
    competition_id,
    is_knockout,
    pick_same_competition,
)
from bet.sofa.count_dispersion import DispersionTable, load_table  # noqa: E402
from bet.sofa.metrics import regulation_score  # noqa: E402
from bet.sofa.samples import INDEXED_HISTORY_LIMIT  # noqa: E402
from scripts.sofa.calibrate_from_cache import (  # noqa: E402
    k_centre_for,
    load_baselines,
    prior_for,
)

DB = _REPO / "data" / "sofa.db"
FRIENDLIES: dict[int, str] = {851: "men", 852: "women"}
SAMPLE_N = 10
MINIMUM = 5
N_BOOT = 2000
SEED = 0
RECENT_FROM = "2024-10-13"
VARIANTS: tuple[str, ...] = ("A", "B", "C", "D")
MARKETS: tuple[str, ...] = ("goals_total", "goals_for")


@dataclass(frozen=True, slots=True)
class Past:
    """One past national-team match from one side's point of view."""

    ts: int
    event_id: int
    competition: int | None
    regular: bool
    goals_for: float
    goals_against: float

    @property
    def total(self) -> float:
        return self.goals_for + self.goals_against


@dataclass(frozen=True, slots=True)
class Target:
    ts: int
    event_id: int
    competition: int
    knockout: bool
    home: int
    away: int
    home_goals: float
    away_goals: float


def in_pool(competition: int | None, excluded: frozenset[int]) -> bool:
    """A past match the measurement's pool holds: everything SAMPLES admits,
    plus the two senior friendly competitions under study."""
    return competition in FRIENDLIES or competition not in excluded


def before(history: Sequence[Past], ts: int) -> list[Past]:
    """Matches strictly before ``ts``, newest first, at most
    INDEXED_HISTORY_LIMIT of them (what SAMPLES' pool can reach)."""
    keys = [p.ts for p in history]
    cut = bisect.bisect_left(keys, ts)
    lo = max(0, cut - INDEXED_HISTORY_LIMIT)
    return list(reversed(history[lo:cut]))


def samples(
    pool: Sequence[Past], target_competition: int, knockout: bool,
    n: int = SAMPLE_N, minimum: int = MINIMUM,
) -> dict[str, list[Past]]:
    """Each variant's sample for one side, newest first (see the docstring)."""
    b = list(pool[:n])
    picked = None if knockout else pick_same_competition(
        pool, target_competition, n, lambda p: p.competition, lambda p: p.regular,
        minimum,
    )
    a = picked if picked is not None else b
    if picked is not None:
        oldest = min(p.ts for p in picked)
        c = [p for p in pool if p.ts >= oldest]
    else:
        c = b
    competitive = [p for p in pool if p.competition not in FRIENDLIES][:n]
    d = competitive if len(competitive) >= minimum else b
    return {"A": a, "B": b, "C": c, "D": d}


def pooled_totals(side_a: Sequence[Past], side_b: Sequence[Past]) -> list[float]:
    """calibrate_from_cache.pooled_total_sample: one shared match once."""
    seen: set[int] = set()
    out: list[float] = []
    for p in (*side_a, *side_b):
        if p.event_id in seen:
            continue
        seen.add(p.event_id)
        out.append(p.total)
    return out


def shrunk(values: Sequence[float], prior: float | None, k: float) -> float:
    """SHEET's centre without the rating: mean shrunk toward the prior."""
    mean = statistics.mean(values)
    if prior is None:
        return mean
    w = len(values) / (len(values) + k)
    return w * mean + (1.0 - w) * prior


@dataclass
class Case:
    population: str
    market: str
    event_id: int
    ts: int
    differs: bool  # A's sample is not B's
    nb: dict[str, float]
    sq: dict[str, float]


def score_target(
    t: Target,
    history: Mapping[int, list[Past]],
    baselines: Mapping[str, Any],
    table: DispersionTable,
    k: float,
    asof: AsOfPrior | None = None,
) -> list[Case]:
    """The goals_total case and the two goals_for cases of one friendly."""
    pools = {s: before(history.get(s, []), t.ts) for s in (t.home, t.away)}
    picks = {s: samples(pools[s], t.competition, t.knockout) for s in pools}
    population = FRIENDLIES[t.competition]
    out: list[Case] = []

    def alpha(market: str) -> float:
        cell = table.read("football", market, t.competition)
        return cell.alpha if cell is not None else 0.0

    def case(market: str, y: float, centres: dict[str, float], differs: bool) -> Case:
        a = alpha(market)
        return Case(
            population, market, t.event_id, t.ts, differs,
            {v: nb_logloss(y, c, a) for v, c in centres.items()},
            {v: (c - y) ** 2 for v, c in centres.items()},
        )

    full = {s: len(picks[s]["B"]) >= MINIMUM for s in picks}
    prior_t = prior_for(dict(baselines), "goals_total", t.competition)
    prior_f = prior_for(dict(baselines), "goals_for", t.competition)
    if asof is not None:
        running = asof.total(t.competition)
        if running is not None:
            prior_t, prior_f = running, running / 2.0
    if full[t.home] and full[t.away]:
        centres = {
            v: shrunk(pooled_totals(picks[t.home][v], picks[t.away][v]), prior_t, k)
            for v in VARIANTS
        }
        differs = any(
            [p.event_id for p in picks[s]["A"]] != [p.event_id for p in picks[s]["B"]]
            for s in picks
        )
        out.append(case("goals_total", t.home_goals + t.away_goals, centres, differs))
    for side, y in ((t.home, t.home_goals), (t.away, t.away_goals)):
        if not full[side]:
            continue
        centres = {
            v: shrunk([p.goals_for for p in picks[side][v]], prior_f, k)
            for v in VARIANTS
        }
        differs = ([p.event_id for p in picks[side]["A"]]
                   != [p.event_id for p in picks[side]["B"]])
        out.append(case("goals_for", y, centres, differs))
    return out


class AsOfPrior:
    """Sensitivity prior: a friendly competition's mean match total over its
    own matches strictly before the one priced (``observe`` after scoring),
    None below ``minimum`` matches - then the baseline file is read."""

    def __init__(self, minimum: int = 30) -> None:
        self.minimum = minimum
        self._sum: dict[int, float] = defaultdict(float)
        self._n: dict[int, int] = defaultdict(int)

    def total(self, competition: int) -> float | None:
        n = self._n[competition]
        return self._sum[competition] / n if n >= self.minimum else None

    def observe(self, competition: int, total: float) -> None:
        self._sum[competition] += total
        self._n[competition] += 1


def diff_groups(
    cases: Sequence[Case], new: str, old: str, field: str,
) -> dict[int, list[float]]:
    """Per-match lists of (new - old) for the bootstrap."""
    groups: dict[int, list[float]] = defaultdict(list)
    for c in cases:
        values = c.nb if field == "nb" else c.sq
        groups[c.event_id].append(values[new] - values[old])
    return dict(groups)


def verdict(intervals: Mapping[str, tuple[float, float, float]]) -> str:
    """Pre-registered: both markets' NB interval wholly below zero = BETTER;
    one = HINT; any wholly above zero and none below = WORSE; else NONE."""
    below = [m for m, (_, _, hi) in intervals.items() if hi < 0]
    above = [m for m, (_, lo, _) in intervals.items() if lo > 0]
    if len(below) == len(intervals) and intervals:
        return "BETTER"
    if below:
        return "HINT"
    if above:
        return "WORSE"
    return "NONE"


COMPARISONS: tuple[tuple[str, str], ...] = (
    ("B", "A"), ("C", "A"), ("D", "A"), ("B", "D"), ("C", "D"),
)


def summarise(cases: Sequence[Case]) -> dict[str, Any]:
    """Every comparison, NB and squared error, per market."""
    out: dict[str, Any] = {}
    for market in MARKETS:
        rows = [c for c in cases if c.market == market]
        if not rows:
            continue
        cell: dict[str, Any] = {
            "cases": len(rows),
            "matches": len({c.event_id for c in rows}),
            "differs": sum(c.differs for c in rows),
            "mean_nb": {v: statistics.mean(c.nb[v] for c in rows) for v in VARIANTS},
            "mean_sq": {v: statistics.mean(c.sq[v] for c in rows) for v in VARIANTS},
        }
        for new, old in COMPARISONS:
            for field in ("nb", "sq"):
                mean, lo, hi, _, _ = boot_by_group(
                    diff_groups(rows, new, old, field), N_BOOT, SEED)
                cell[f"{new}-{old}_{field}"] = (mean, lo, hi)
        out[market] = cell
    return out


# --- loading -----------------------------------------------------------------


def load(db: Path) -> tuple[dict[int, list[Past]], list[Target]]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    excluded = FRIENDLY_COMPETITION_IDS
    history: dict[int, list[Past]] = defaultdict(list)
    targets: list[Target] = []
    seen: set[int] = set()
    query = (
        "SELECT event_json FROM sofa_listed_event WHERE sport = 'football' "
        "AND (event_json LIKE '%\"national\": true%' "
        "OR event_json LIKE '%\"national\":true%')"
    )
    for (js,) in con.execute(query):
        event = json.loads(js)
        target = parse_event(event, excluded, history, seen)
        if target is not None:
            targets.append(target)
    con.close()
    for side in history.values():
        side.sort(key=lambda p: (p.ts, p.event_id))
    targets.sort(key=lambda t: (t.ts, t.event_id))
    return history, targets


def parse_event(
    event: Mapping[str, Any],
    excluded: frozenset[int],
    history: dict[int, list[Past]],
    seen: set[int],
) -> Target | None:
    """Add one listed event to both sides' histories; the Target when it is a
    senior national-team friendly."""
    if (event.get("status") or {}).get("type") != "finished":
        return None
    home_t, away_t = event.get("homeTeam") or {}, event.get("awayTeam") or {}
    if not (home_t.get("national") and away_t.get("national")):
        return None
    eid, ts = event.get("id"), event.get("startTimestamp")
    if not isinstance(eid, int) or not isinstance(ts, int) or eid in seen:
        return None
    try:
        home, away = int(home_t["id"]), int(away_t["id"])
    except (KeyError, TypeError, ValueError):
        return None
    score = regulation_score(dict(event))
    if score is None:
        return None
    seen.add(eid)
    comp = competition_id(event)
    knockout = is_knockout(event)
    if in_pool(comp, excluded):
        hg, ag = score
        history[home].append(Past(ts, eid, comp, not knockout, hg, ag))
        history[away].append(Past(ts, eid, comp, not knockout, ag, hg))
    if comp in FRIENDLIES:
        return Target(ts, eid, comp, knockout, home, away, score[0], score[1])
    return None


def _day(text: str) -> int:
    return int(datetime.fromisoformat(text).replace(tzinfo=UTC).timestamp())


def _fmt(t: tuple[float, float, float]) -> str:
    return f"{t[0]:+.5f} [{t[1]:+.5f}; {t[2]:+.5f}]"


def report(label: str, summary: Mapping[str, Any]) -> list[str]:
    lines = [f"## {label}", ""]
    for market, cell in summary.items():
        lines.append(
            f"### {market}: {cell['cases']} cases, {cell['matches']} matches, "
            f"A != B in {cell['differs']}")
        lines.append("")
        lines.append("| variant | NB log-loss | sq. error |")
        lines.append("|---|---|---|")
        for v in VARIANTS:
            lines.append(
                f"| {v} | {cell['mean_nb'][v]:.5f} | {cell['mean_sq'][v]:.4f} |")
        lines.append("")
        lines.append("| comparison | d NB log-loss [95%] | d sq. error [95%] |")
        lines.append("|---|---|---|")
        for new, old in COMPARISONS:
            lines.append(
                f"| {new} - {old} | {_fmt(cell[f'{new}-{old}_nb'])} | "
                f"{_fmt(cell[f'{new}-{old}_sq'])} |")
        lines.append("")
    for new, old in COMPARISONS:
        v = verdict({m: c[f"{new}-{old}_nb"] for m, c in summary.items()})
        lines.append(f"- {new} vs {old}: **{v}**")
    lines.append("")
    return lines


def subsets_for(pop: str, recent: int) -> list[tuple[str, Callable[[Case], bool]]]:
    """The reported subsets of one population."""

    def everything(c: Case) -> bool:
        return c.population == pop

    def differs(c: Case) -> bool:
        return c.population == pop and c.differs

    def latest(c: Case) -> bool:
        return c.population == pop and c.ts >= recent

    return [
        (f"{pop} - all", everything),
        (f"{pop} - A differs from B", differs),
        (f"{pop} - from {RECENT_FROM}", latest),
    ]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--from", dest="start", default="2015-01-01")
    ap.add_argument("--to", dest="end", default="2026-10-12")
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument(
        "--prior", choices=("baseline", "asof"), default="baseline",
        help="baseline: config/sofa_league_baselines.json as SHEET reads it "
        "(851 has no entry: global); asof: the friendly competition's own "
        "running mean (sensitivity, not pre-registered as primary)",
    )
    args = ap.parse_args(argv)
    if not args.db.exists():
        print(f"no DB at {args.db}", file=sys.stderr)
        return 2
    t0 = time.time()
    history, targets = load(args.db)
    print(f"loaded {sum(map(len, history.values())) // 2} pool matches, "
          f"{len(targets)} friendlies in {time.time() - t0:.0f}s", flush=True)
    start, end = _day(args.start), _day(args.end) + 86400
    baselines = load_baselines()
    table = load_table()
    k = k_centre_for("football")
    asof = AsOfPrior() if args.prior == "asof" else None
    cases: list[Case] = []
    for t in targets:  # time order: the as-of prior sees only earlier ones
        if start <= t.ts < end:
            cases.extend(score_target(t, history, baselines, table, k, asof))
        if asof is not None:
            asof.observe(t.competition, t.home_goals + t.away_goals)
    recent = _day(RECENT_FROM)
    subsets: list[tuple[str, Callable[[Case], bool]]] = []
    for pop in ("women", "men"):
        subsets += subsets_for(pop, recent)
    text = [f"# National-team friendlies, goal samples, {args.start}..{args.end}",
            "", f"prior {args.prior}; K = {k}, n = {SAMPLE_N}, minimum {MINIMUM}; "
            "lower is better; "
            f"match bootstrap {N_BOOT}, seed {SEED}.", ""]
    dump: dict[str, Any] = {}
    for label, keep in subsets:
        summary = summarise([c for c in cases if keep(c)])
        dump[label] = summary
        text += report(label, summary)
    print("\n".join(text))
    if args.json_out:
        args.json_out.write_text(json.dumps(dump, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
