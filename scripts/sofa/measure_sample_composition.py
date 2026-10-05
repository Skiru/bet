#!/usr/bin/env python3
"""Which past matches should a football sample hold? Measured on the cache.

2026-10-04, Farense - Chaves: Farense's ten-match sample held two legs of
the previous season's relegation play-off, a cup tie against an amateur side
and three matches from the end of the previous season; the league matches of
the current season alone said what the price said. The question this script
answers is whether that is a pattern: does a sample built from a different
set of past matches predict the fixture better than the one SAMPLES builds?

For every finished REGULAR league match in the cache (comparability.match_kind,
from --start on) each side's last ``--n`` matches before kick-off that carry
the statistic are taken under each rule:

  R0  all       - every non-friendly match (what SAMPLES does today)
  R1  no_ko     - no KNOCKOUT match (cup rounds, play-offs, qualifiers)
  R2  same_comp - only REGULAR matches of the fixture's own competition
  R3  no_ko_season   - R1, and only the current season's matches when the
                       side has at least --min of them
  R4  same_comp_season - R2 with the same season rule

A rule that leaves a side fewer than --min matches falls back to R0 for that
side (a sample is never emptied by the rule). The forecast of a ``*_total``
is the mean of the two sides' pooled totals (the sample mean SAMPLES reports
for a total row); of a ``*_for`` the side's own mean, scored once per side.
It is scored with the Poisson log-loss, the Brier score of P(value > line)
for each line of the metric, and the squared error. Each rule is compared to
R0 on the same matches (paired), with a 95% interval from resampling matches
and the two event-id halves apart.

Measurement only: the DB is opened read-only and nothing the pipeline reads
is written.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sample_composition.py \\
        [--start 2025-08-01] [--end 2026-10-03] \\
        [--metrics goals_total goals_for corners_total ...] [--out report.md]
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import sqlite3
import sys
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from bet.sofa.comparability import MatchKind, competition_id, match_kind
from bet.sofa.metrics import is_extra_time_event, regulation_score

DB = Path("data/sofa.db")
# confidence.MAX_BUILDER_SAMPLE_AGE_DAYS
MAX_AGE_S = 180 * 86400

# Base statistic -> its /statistics key (period ALL). "goals" comes from the
# listing score. Keys as in bet.sofa.metrics.
STATS: dict[str, str | None] = {
    "goals": None,
    "goals_1h": None,
    "goals_2h": None,
    "corners": "cornerKicks",
    "fouls": "fouls",
    "yellow_cards": "yellowCards",
    "shots": "totalShotsOnGoal",
    "shots_on_target": "shotsOnGoal",
    "offsides": "offsides",
}

LINES: dict[str, tuple[float, ...]] = {
    "goals_total": (1.5, 2.5, 3.5),
    "goals_for": (0.5, 1.5, 2.5),
    "goals_1h_total": (0.5, 1.5),
    "goals_1h_for": (0.5,),
    "goals_2h_total": (0.5, 1.5, 2.5),
    "goals_2h_for": (0.5, 1.5),
    "corners_total": (8.5, 9.5, 10.5),
    "corners_for": (3.5, 4.5, 5.5),
    "fouls_total": (21.5, 23.5, 25.5),
    "fouls_for": (10.5, 11.5, 12.5),
    "yellow_cards_total": (3.5, 4.5, 5.5),
    "yellow_cards_for": (1.5, 2.5),
    "shots_total": (21.5, 23.5, 25.5),
    "shots_for": (10.5, 12.5),
    "shots_on_target_total": (6.5, 7.5, 8.5),
    "shots_on_target_for": (3.5, 4.5),
    "offsides_total": (2.5, 3.5, 4.5),
    "offsides_for": (1.5, 2.5),
}


def split_metric(metric: str) -> tuple[str, str]:
    """"shots_on_target_total" -> ("shots_on_target", "total")."""
    stat, _, scope = metric.rpartition("_")
    if stat not in STATS or scope not in ("total", "for"):
        raise ValueError(f"unknown metric {metric!r}")
    return stat, scope


@dataclass(frozen=True, slots=True)
class Past:
    """One past match from one side's point of view."""

    ts: int
    event_id: int
    competition: int
    season: int | None
    kind: MatchKind
    values: dict[str, tuple[float, float]]  # stat -> (for, against)
    # Sofascore category (a country for a domestic league); None where the
    # caller did not ask for it (measure_model_defects reads it).
    category: int | None = None

    def value(self, metric: str) -> float | None:
        stat, scope = split_metric(metric)
        pair = self.values.get(stat)
        if pair is None:
            return None
        return pair[0] + pair[1] if scope == "total" else pair[0]


@dataclass(frozen=True, slots=True)
class Target:
    ts: int
    event_id: int
    competition: int
    season: int | None
    home: int
    away: int
    values: dict[str, tuple[float, float]]  # stat -> (home, away)
    # Context of the fixture itself, for the context measurements
    # (measure_model_defects): its kind, its league round and its category.
    kind: MatchKind = MatchKind.REGULAR
    round: int | None = None
    category: int | None = None


Rule = Callable[[Sequence[Past], Target, int, int], list[Past]]


def before(history: Sequence[Past], ts: int, metric: str) -> list[Past]:
    """The side's matches strictly before ``ts`` that carry ``metric``,
    newest first."""
    keys = [p.ts for p in history]
    chosen = history[: bisect.bisect_left(keys, ts)]
    return [p for p in reversed(chosen) if p.value(metric) is not None]


def _admitted(p: Past) -> bool:
    return p.kind is not MatchKind.FRIENDLY


def _regular(p: Past) -> bool:
    return p.kind is MatchKind.REGULAR


def pick(
    newest_first: Sequence[Past], keep: Callable[[Past], bool], n: int, minimum: int
) -> list[Past]:
    """The newest ``n`` matches ``keep`` admits; R0's when fewer than ``minimum``."""
    chosen = [p for p in newest_first if keep(p)][:n]
    if len(chosen) >= minimum:
        return chosen
    return [p for p in newest_first if _admitted(p)][:n]


def make_rules(season_start: dict[int, int]) -> dict[str, Rule]:
    def current(t: Target) -> Callable[[Past], bool]:
        start = season_start.get(t.season) if t.season is not None else None
        return (lambda p: True) if start is None else (lambda p: p.ts >= start)

    def r0(b: Sequence[Past], t: Target, n: int, m: int) -> list[Past]:
        return [p for p in b if _admitted(p)][:n]

    def r1(b: Sequence[Past], t: Target, n: int, m: int) -> list[Past]:
        return pick(b, _regular, n, m)

    def r2(b: Sequence[Past], t: Target, n: int, m: int) -> list[Past]:
        return pick(b, lambda p: _regular(p) and p.competition == t.competition, n, m)

    def r3(b: Sequence[Past], t: Target, n: int, m: int) -> list[Past]:
        cur = current(t)
        seasonal = [p for p in b if _regular(p) and cur(p)][:n]
        return seasonal if len(seasonal) >= m else r1(b, t, n, m)

    def r4(b: Sequence[Past], t: Target, n: int, m: int) -> list[Past]:
        cur = current(t)
        seasonal = [
            p for p in b if _regular(p) and p.competition == t.competition and cur(p)
        ][:n]
        return seasonal if len(seasonal) >= m else r2(b, t, n, m)

    def r5(b: Sequence[Past], t: Target, n: int, m: int) -> list[Past]:
        # R2 inside CONFIDENCE's SAMPLE_CROSSES_SEASON window (180 days), so
        # the pick never makes a leg older than the gate allows.
        return pick(
            b,
            lambda p: _regular(p) and p.competition == t.competition
            and t.ts - p.ts <= MAX_AGE_S,
            n, m,
        )

    return {
        "R0_all": r0,
        "R5_same_comp_180d": r5,
        "R1_no_ko": r1,
        "R2_same_comp": r2,
        "R3_no_ko_season": r3,
        "R4_same_comp_season": r4,
    }


def poisson_logloss(lam: float, k: float) -> float:
    lam = max(lam, 0.05)
    return lam - k * math.log(lam) + math.lgamma(k + 1)


def poisson_over(lam: float, line: float) -> float:
    lam = max(lam, 0.05)
    cdf, term = 0.0, math.exp(-lam)
    for k in range(int(math.floor(line)) + 1):
        if k:
            term *= lam / k
        cdf += term
    return 1.0 - cdf


def _statistics(stats_json: str | None) -> dict[str, tuple[float, float]]:
    if not stats_json:
        return {}
    try:
        raw = json.loads(stats_json)
    except ValueError:
        return {}
    wanted = {key: stat for stat, key in STATS.items() if key}
    out: dict[str, tuple[float, float]] = {}
    for period in raw.get("statistics") or []:
        if period.get("period") != "ALL":
            continue
        for group in period.get("groups") or []:
            for item in group.get("statisticsItems") or []:
                stat = wanted.get(item.get("key"))
                h, a = item.get("homeValue"), item.get("awayValue")
                if stat and isinstance(h, (int, float)) and isinstance(a, (int, float)):
                    out[stat] = (float(h), float(a))
    return out


def load(
    db: Path, with_stats: bool, target_kind: MatchKind | None = MatchKind.REGULAR
) -> tuple[dict[int, list[Past]], list[Target], dict[int, int]]:
    """``target_kind`` None: every non-friendly match is a target (REGULAR and
    KNOCKOUT, told apart by Target.kind)."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    stats: dict[int, dict[str, tuple[float, float]]] = {}
    if with_stats:
        for eid, js in con.execute(
            "SELECT sofascore_event_id, statistics_json FROM sofa_event_stats "
            "WHERE status_type = 'finished'"
        ):
            values = _statistics(js)
            if values:
                stats[int(eid)] = values
    history: dict[int, list[Past]] = defaultdict(list)
    targets: list[Target] = []
    season_start: dict[int, int] = {}
    seen: set[int] = set()
    for (js,) in con.execute(
        "SELECT event_json FROM sofa_listed_event WHERE sport = 'football'"
    ):
        event = json.loads(js)
        if (event.get("status") or {}).get("type") != "finished":
            continue
        eid, ts = event.get("id"), event.get("startTimestamp")
        comp = competition_id(event)
        if not isinstance(eid, int) or not isinstance(ts, int) or comp is None:
            continue
        if eid in seen:
            continue
        seen.add(eid)
        try:
            home, away = int(event["homeTeam"]["id"]), int(event["awayTeam"]["id"])
        except (KeyError, TypeError, ValueError):
            continue
        # Read as SAMPLES reads a match (bet.sofa.metrics.extract_metric):
        # goals at 90 minutes (normaltime after extra time), halves from
        # period1 / period2, and no statistic of a 120-minute match.
        regulation = regulation_score(event)
        if regulation is None:
            continue
        season = (event.get("season") or {}).get("id")
        season = season if isinstance(season, int) else None
        if season is not None:
            season_start[season] = min(season_start.get(season, ts), ts)
        extra_time = is_extra_time_event(event)
        values = {} if extra_time else dict(stats.get(eid, {}))
        values["goals"] = regulation
        for stat, field in (("goals_1h", "period1"), ("goals_2h", "period2")):
            h = (event.get("homeScore") or {}).get(field)
            a = (event.get("awayScore") or {}).get(field)
            if isinstance(h, int) and isinstance(a, int) and h >= 0 and a >= 0:
                values[stat] = (float(h), float(a))
        kind = match_kind(event, "football")
        category = ((event.get("tournament") or {}).get("category") or {}).get("id")
        category = category if isinstance(category, int) else None
        rnd = (event.get("roundInfo") or {}).get("round")
        rnd = rnd if isinstance(rnd, int) else None
        swapped = {k: (v[1], v[0]) for k, v in values.items()}
        history[home].append(Past(ts, eid, comp, season, kind, values, category))
        history[away].append(Past(ts, eid, comp, season, kind, swapped, category))
        if kind is target_kind or (
            target_kind is None and kind is not MatchKind.FRIENDLY
        ):
            targets.append(Target(ts, eid, comp, season, home, away, values,
                                  kind, rnd, category))
    for side in history.values():
        side.sort(key=lambda p: (p.ts, p.event_id))
    return history, targets, season_start


@dataclass
class Scored:
    names: list[str]
    scores: np.ndarray  # cases x rules x columns
    ids: list[int]
    flagged: list[bool]


def evaluate(
    history: dict[int, list[Past]],
    targets: Sequence[Target],
    season_start: dict[int, int],
    metric: str,
    n: int,
    minimum: int,
) -> Scored:
    """One case per target (``*_total``) or per side (``*_for``)."""
    stat, scope = split_metric(metric)
    lines = LINES.get(metric, ())
    rules = make_rules(season_start)
    names = list(rules)
    rows: list[list[list[float]]] = []
    ids: list[int] = []
    flagged: list[bool] = []

    def score(lam: float, y: float) -> list[float]:
        return [poisson_logloss(lam, y), (lam - y) ** 2] + [
            (poisson_over(lam, line) - (y > line)) ** 2 for line in lines
        ]

    def odd_one_out(sample: Sequence[Past], t: Target) -> bool:
        start = season_start.get(t.season) if t.season is not None else None
        return any(p.kind is not MatchKind.REGULAR for p in sample) or (
            start is not None and any(p.ts < start for p in sample)
        )

    for t in targets:
        pair = t.values.get(stat)
        if pair is None:
            continue
        a_b = before(history.get(t.home, []), t.ts, metric)
        b_b = before(history.get(t.away, []), t.ts, metric)
        base_a = rules["R0_all"](a_b, t, n, minimum)
        base_b = rules["R0_all"](b_b, t, n, minimum)
        if scope == "total":
            if len(base_a) < n or len(base_b) < n:
                continue
            y = pair[0] + pair[1]
            per_rule = []
            for name in names:
                pool = rules[name](a_b, t, n, minimum) + rules[name](b_b, t, n, minimum)
                vals = [p.value(metric) or 0.0 for p in pool]
                per_rule.append(score(sum(vals) / len(vals), y))
            rows.append(per_rule)
            ids.append(t.event_id)
            flagged.append(odd_one_out(base_a + base_b, t))
            continue
        for side_b, base, y in ((a_b, base_a, pair[0]), (b_b, base_b, pair[1])):
            if len(base) < n:
                continue
            per_rule = []
            for name in names:
                own = rules[name](side_b, t, n, minimum)
                vals = [p.value(metric) or 0.0 for p in own]
                per_rule.append(score(sum(vals) / len(vals), y))
            rows.append(per_rule)
            ids.append(t.event_id)
            flagged.append(odd_one_out(base, t))
    return Scored(names, np.asarray(rows), ids, flagged)


def paired_interval(
    diff: np.ndarray, groups: np.ndarray, rng: np.random.Generator, draws: int = 1000
) -> tuple[float, float]:
    """95% interval of the mean difference, resampling whole matches."""
    uniq, inv = np.unique(groups, return_inverse=True)
    sums = np.bincount(inv, weights=diff)
    counts = np.bincount(inv)
    means = np.empty(draws)
    for i in range(draws):
        pick_ = rng.integers(0, len(uniq), size=len(uniq))
        means[i] = sums[pick_].sum() / counts[pick_].sum()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def report(
    scored: Scored, metric: str, label: str, mask: np.ndarray | None
) -> list[str]:
    rng = np.random.default_rng(20261004)
    scores = scored.scores if mask is None else scored.scores[mask]
    ids = np.asarray(scored.ids if mask is None else np.asarray(scored.ids)[mask])
    cols = ["logloss", "sq_err"] + [f"brier_{line}" for line in LINES.get(metric, ())]
    matches = len(set(ids.tolist()))
    out = [f"### {metric} - {label}: {len(ids)} cases, {matches} matches", ""]
    out.append(
        "| rule | " + " | ".join(cols) + " | d logloss vs R0 [95%] | even | odd |"
    )
    out.append("|---" * (len(cols) + 4) + "|")
    parity = ids % 2
    for r, name in enumerate(scored.names):
        means = scores[:, r, :].mean(axis=0)
        diff = scores[:, r, 0] - scores[:, 0, 0]
        lo, hi = paired_interval(diff, ids, rng) if r else (0.0, 0.0)
        even = diff[parity == 0].mean() if (parity == 0).any() else float("nan")
        odd = diff[parity == 1].mean() if (parity == 1).any() else float("nan")
        out.append(
            f"| {name} | " + " | ".join(f"{m:.5f}" for m in means)
            + f" | {diff.mean():+.5f} [{lo:+.5f}; {hi:+.5f}]"
            + f" | {even:+.5f} | {odd:+.5f} |"
        )
    out.append("")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--start", default="2025-08-01")
    ap.add_argument("--end", default="2026-10-03")
    ap.add_argument("--metrics", nargs="+", default=["goals_total", "goals_for"])
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--min", dest="minimum", type=int, default=5)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument(
        "--targets", choices=("regular", "knockout"), default="regular",
        help="which fixtures are scored: league rounds (the 10-04 measurement) "
        "or KNOCKOUT ones (cup rounds, play-offs, qualifiers)",
    )
    args = ap.parse_args(argv)
    target_kind = MatchKind(args.targets.upper())
    for metric in args.metrics:
        split_metric(metric)
    start = int(datetime.fromisoformat(args.start).replace(tzinfo=UTC).timestamp())
    end = int(datetime.fromisoformat(args.end).replace(tzinfo=UTC).timestamp()) + 86400
    if not args.db.exists():
        print(f"no DB at {args.db}", file=sys.stderr)
        return 2
    with_stats = any(STATS[split_metric(m)[0]] is not None for m in args.metrics)
    history, targets, season_start = load(args.db, with_stats, target_kind)
    chosen = [t for t in targets if start <= t.ts < end]
    text = [
        f"# Sample composition, {args.start}..{args.end}",
        "",
        f"n={args.n} per side, fallback to R0 below {args.minimum}; "
        "lower is better in every column. 95% intervals resample whole matches.",
        "",
    ]
    for metric in args.metrics:
        scored = evaluate(history, chosen, season_start, metric, args.n, args.minimum)
        if not scored.ids:
            text += [f"### {metric}: no case had a full sample", ""]
            continue
        text += report(scored, metric, f"all {target_kind} matches", None)
        mask = np.asarray(scored.flagged)
        if mask.any():
            text += report(
                scored, metric,
                "R0 sample held a KNOCKOUT or previous-season match", mask,
            )
        print("\n".join(text[-40:]), flush=True)
    body = "\n".join(text)
    if args.out:
        args.out.write_text(body + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
