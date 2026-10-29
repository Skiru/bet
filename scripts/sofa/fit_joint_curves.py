#!/usr/bin/env python3
"""History curves of the football joints SHEET prices from the RAW samples
(both_over_ / handicap_ / most_ of every base outside
epochs.DERIVED_MARGINAL_CENTRES_METRICS: fouls, shots, offsides, saves,
throw-ins, goal kicks, tackles and the per-half goals / corners / shots /
saves), with the one-sided holdout gate - fitted and STAGED, never installed
by this script (scripts/sofa/install_new_market_curves.py, group
`joint_curves`, installs the passing keys).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_joint_curves.py \\
        --db-path data/refit_2026-10-17/sofa_replay.db \\
        --out-dir data/refit_joint_curves_2026-10-21 \\
        [--bases fouls,shots,...] [--holdout-from 2026-09-01] \\
        [--holdout-to 2026-10-14] [--before 2026-10-17] [--jobs 8]

Why: such a joint has no history curve, so CONFIDENCE (epochs.DERIVED_CURVES
on) finds none and line evidence alone reads it - NO_LINE_EVIDENCE below 50
settled lines a bucket: it never prints (operator, 2026-10-21: every market
Superbet offers must be able to print).

The replay is calibrate_from_cache's, for these rows alone (a full refit
replays every market for hours): load_cache (read-only), each side's sample
recent_for (SAMPLE_N, MIN_SAMPLE, the goal metrics' same-competition rule),
a friendly never in a history, and calibrate_from_cache.football_joint_rows
with NO marginal centres - exactly derived.price_derived_rungs' path for a
base outside DERIVED_MARGINAL_CENTRES_METRICS (SHEET reads 03_samples.json's
raw side samples; no prior, rating, opponent correction or dispersion), the
grades of run_settle._settle_derived. The side correlation is the one SHEET
reads (config/sofa_side_correlations.json); a base the file has no measured
number for gets the residual correlation measured here on the training
window (measure_side_correlations.residual_pearson, >= MIN_PAIRS residual
pairs), written into a STAGED copy of the file (`side_correlations.json`) -
the curves are fitted with it, so the two install together or not at all.

Rows: every non-friendly match (fit_meta: FRIENDLY_COMPETITION_IDS out), all
classes, keyed `<market>|<DIR>` - what fit_confidence does with a replayed
joint and what CONFIDENCE reads (Calibration.realised: by_market_direction).
Gate (new_market_gate, one-sided): the curve fitted before --holdout-from is
read on [--holdout-from, --holdout-to) on the forecasts a leg could read it
with - men's matches (a women's leg reads only its class's curves; the
women's matches get their own `women:<key>` curve, fitted and gated on them
alone, installed under by_class); plus
require_final, and (as fit_score_market_curves) no line slice with n >= MIN_N
may overstate by more than MAX_GAP. The final curve: every row before
--before.

Writes <out-dir>/joint_curves/curves.json (the installer's shape),
gate_report.md, side_correlations.json (staged) and correlations.json (what
was measured). Exit 0, 2 on a crash.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import multiprocessing as mp
import pickle
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.comparability import MatchKind  # noqa: E402
from bet.sofa.confidence import CLASS_WOMEN  # noqa: E402
from bet.sofa.config import config_path  # noqa: E402
from bet.sofa.epochs import DERIVED_MARGINAL_CENTRES_METRICS  # noqa: E402
from bet.sofa.line_curves import SECTION as LINE_SECTION  # noqa: E402
from bet.sofa.line_curves import line_label  # noqa: E402
from bet.sofa.samples import FRIENDLY_COMPETITION_IDS  # noqa: E402
from scripts.sofa import new_market_gate as gm  # noqa: E402
from scripts.sofa.calibrate_from_cache import (  # noqa: E402
    MIN_SAMPLE,
    Past,
    Played,
    football_joint_rows,
    load_cache,
    market_name,
    recent_for,
)
from scripts.sofa.fit_confidence import load_event_classes  # noqa: E402
from scripts.sofa.measure_side_correlations import (  # noqa: E402
    MIN_PAIRS,
    residual_pearson,
)

GROUP = "joint_curves"
TARGET = "config/sofa_confidence_calibration.json"
CORRELATIONS_FILE = "sofa_side_correlations.json"
# Every football base whose joints SHEET prices from the raw samples and
# Superbet offers (04_offer.json 10-10..10-20; throw-ins / goal kicks /
# tackles both-over and the shots handicaps from epochs.
# FOOTBALL_STAT_VARIANTS). Never a base of DERIVED_MARGINAL_CENTRES_METRICS:
# those joints read the marginal rows' centres and have their curves.
DEFAULT_BASES: tuple[str, ...] = (
    "fouls", "shots", "offsides", "saves", "throw_ins", "goal_kicks",
    "tackles", "goals_1h", "goals_2h", "corners_1h", "corners_2h",
    "shots_1h", "shots_2h", "saves_1h")

# a fitted row: (p, y, line label)
Obs = tuple[float, int, str]
# a holdout forecast: (p, y, match id, line label)
Holdout = tuple[float, int, int, str]


def _ts(day: str) -> int:
    d = date.fromisoformat(day)
    return int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())


def counted(match: Played) -> bool:
    """A row the fit reads: not a friendly competition (fit_meta.
    friendly_exclusion_sql's rule, by competition id)."""
    return match.competition_id not in FRIENDLY_COMPETITION_IDS


@dataclass
class BaseResult:
    """Bucket counts (train / final) and holdout forecasts of one base."""

    base: str
    rho: float
    train: dict[str, list[Obs]] = field(
        default_factory=lambda: collections.defaultdict(list))
    final: dict[str, list[Obs]] = field(
        default_factory=lambda: collections.defaultdict(list))
    holdout: dict[str, list[Holdout]] = field(
        default_factory=lambda: collections.defaultdict(list))
    matches: int = 0


# One match's joint inputs: the match and both sides' sample values.
Task = tuple[Played, list[float], list[float]]
# One joint row: (key, p, outcome 0/1, line)
JointRow = tuple[str, float, int, float]


def base_tasks(played: Iterable[Played], base: str, cut: int) -> list[Task]:
    """calibrate_from_cache.iter_rows' samples for one raw-sample joint base:
    each counted match before `cut` whose two sides hold MIN_SAMPLE values
    BEFORE it (a match never in its own sample, recent_for's picking), not
    all zero; then the match into the histories unless a friendly."""
    out: list[Task] = []
    for_market = market_name(base, "for")
    history: dict[int, list[Past]] = collections.defaultdict(list)
    for match in played:
        if match.sport != "football" or match.timestamp >= cut:
            continue
        values = match.values.get(base)
        if values is None:
            continue
        sample_competition = (
            match.competition_id if match.kind == MatchKind.REGULAR else None)
        home_recent = recent_for(history[match.home_id], for_market,
                                 sample_competition)
        away_recent = recent_for(history[match.away_id], for_market,
                                 sample_competition)
        if (counted(match) and len(home_recent) >= MIN_SAMPLE
                and len(away_recent) >= MIN_SAMPLE
                and any(p.own for p in (*home_recent, *away_recent))):
            out.append((match, [p.own for p in home_recent],
                        [p.own for p in away_recent]))
        if match.kind == MatchKind.FRIENDLY:
            continue
        home, away = values
        regular = match.kind == MatchKind.REGULAR
        history[match.home_id].append(Past(
            match.timestamp, match.event_id, home, home + away,
            match.competition_id, regular, "home", match.away_id))
        history[match.away_id].append(Past(
            match.timestamp, match.event_id, away, home + away,
            match.competition_id, regular, "away", match.home_id))
    return out


def task_rows(task: Task, base: str, rho: float) -> list[JointRow]:
    """The joints of one match (calibrate_from_cache.football_joint_rows with
    no marginal centres: derived.price_derived_rungs' raw-sample path)."""
    match, home, away = task
    return [(f"{r.market}|{r.direction}", r.p_central,
             1 if r.outcome == "WIN" else 0, r.line)
            for r in football_joint_rows(match, base, home, away,
                                         (None, None), rho)]


def accumulate(out: BaseResult, match: Played, rows: Iterable[JointRow],
               h0: int, h1: int, women: frozenset[int]) -> None:
    """Every row into the unclassed curve (fit_confidence's replayed joints);
    a women's match also into the class's own key; the holdout of each key
    only of the matches that read it (a women's leg reads its class)."""
    out.matches += 1
    is_women = match.event_id in women
    for key, p, y, line in rows:
        label = line_label(line)
        obs = (p, y, label)
        targets = [(key, not is_women)]
        if is_women:
            targets.append((f"{CLASS_WOMEN}:{key}", True))
        for k, hold in targets:
            out.final[k].append(obs)
            if match.timestamp < h0:
                out.train[k].append(obs)
            elif match.timestamp < h1 and hold:
                out.holdout[k].append((p, y, match.event_id, label))


def replay_base(
    played: Iterable[Played], base: str, rho: float, h0: int, h1: int, cut: int,
    women: frozenset[int] = frozenset(),
) -> BaseResult:
    """base_tasks, task_rows and accumulate in one process."""
    out = BaseResult(base, rho)
    for task in base_tasks(played, base, cut):
        accumulate(out, task[0], task_rows(task, base, rho), h0, h1, women)
    return out


def women_from_stored(
    path: Path, ts_by_event: Mapping[int, int], women: frozenset[int],
    h0: int, h1: int, cut: int,
) -> BaseResult:
    """The women's class keys of the joints whose unclassed curves the
    refit already installed (goals / corners / cards / shots on target,
    replayed with the marginal centres by calibrate_from_cache --derived):
    their stored replay rows (CSV: event id, competition id, market, line,
    direction, p_central, outcome) of women's matches, split by the match's
    kickoff (`ts_by_event`), friendly competitions out. The p is the
    replay's, so the curve describes what SHEET prices."""
    out = BaseResult("stored", 0.0)
    with path.open() as fh:
        for rec in csv.reader(fh):
            event, comp, market, line, direction, p, outcome = rec
            eid = int(event)
            if eid not in women or outcome not in ("WIN", "LOSS"):
                continue
            if comp and int(comp) in FRIENDLY_COMPETITION_IDS:
                continue
            ts = ts_by_event.get(eid)
            if ts is None or ts >= cut:
                continue
            key = f"{CLASS_WOMEN}:{market}|{direction}"
            label = line_label(float(line))
            obs = (float(p), 1 if outcome == "WIN" else 0, label)
            out.final[key].append(obs)
            if ts < h0:
                out.train[key].append(obs)
            elif ts < h1:
                out.holdout[key].append((obs[0], obs[1], eid, label))
    return out


def measure_rho(played: Iterable[Played], base: str, before: int
                ) -> tuple[float | None, int, int]:
    """Residual side correlation of `base` on the non-friendly matches
    before `before` (measure_side_correlations' estimator and MIN_PAIRS):
    (correlation or None, pairs, residual pairs)."""
    rows = [(m.home_id, m.away_id, *m.values[base]) for m in played
            if m.sport == "football" and m.timestamp < before
            and base in m.values and m.kind != MatchKind.FRIENDLY]
    if len(rows) < MIN_PAIRS:
        return None, len(rows), 0
    r, n = residual_pearson(rows)
    return (r if n >= MIN_PAIRS else None), len(rows), n


def side_correlations(
    file_doc: Mapping[str, Any], bases: Sequence[str],
    measured: Mapping[str, tuple[float | None, int, int]],
) -> tuple[dict[str, Any], dict[str, float]]:
    """The staged correlations file and the rho each base is replayed with:
    the file's own number where it has one (what SHEET reads today), else
    the measured one (added to the staged file), else 0 (SHEET's default)."""
    doc = json.loads(json.dumps(dict(file_doc)))
    used: dict[str, float] = {}
    for base in bases:
        entry = doc.get(base)
        have = entry.get("correlation") if isinstance(entry, dict) else None
        if isinstance(have, int | float) and not isinstance(have, bool):
            used[base] = float(have)
            continue
        r, pairs, residual = measured.get(base, (None, 0, 0))
        if r is None:
            used[base] = 0.0
            continue
        used[base] = round(r, 4)
        doc[base] = {"correlation": round(r, 4), "raw_correlation": None,
                     "pairs": pairs, "residual_pairs": residual,
                     "measured_by": "scripts/sofa/fit_joint_curves.py "
                                    "(training window, calibrate_from_cache "
                                    "values)"}
    return doc, used


def gate_key(train: Sequence[Obs],
             holdout: Sequence[Holdout],
             final: Sequence[Obs]) -> tuple[dict[str, Any], dict[str, Any]]:
    """(verdict, final curve) of one key: the one-sided gate of the training
    curve on the holdout, require_final, and no overstating line slice."""
    tc = gm.fit_curve((p, y) for p, y, _ in train)
    fc = gm.fit_curve((p, y) for p, y, _ in final)
    g = gm.require_final(
        gm.gate(tc, [(p, y, m) for p, y, m, _ in holdout], reps=300), fc)
    slices: dict[str, Any] = {}
    bad: list[str] = []
    by_line: dict[str, list[gm.Forecast]] = collections.defaultdict(list)
    for p, y, m, label in holdout:
        by_line[label].append((p, y, m))
    for label in sorted(by_line):
        sg = gm.gate(tc, by_line[label], reps=200)
        if not sg.get("n"):
            continue
        slices[label] = {k: sg.get(k) for k in ("n", "gap", "gap_ci95")}
        if (sg["n"] >= gm.MIN_N and sg.get("gap") is not None
                and sg["gap"] < -gm.MAX_GAP - 1e-9):
            bad.append(label)
    if bad and g.get("pass"):
        g["pass"] = False
        g["why"] = f"a line slice overstates: {', '.join(bad)}"
    g["slices"] = slices
    g["rows"] = {"train": len(train), "holdout": len(holdout),
                 "final": len(final)}
    return g, fc


def gate_lines(train: Sequence[Obs], holdout: Sequence[Holdout],
               final: Sequence[Obs]) -> dict[str, tuple[dict[str, Any],
                                                       dict[str, Any]]]:
    """{line label: (verdict, final curve)}: each line's own curve (what
    CONFIDENCE reads first for a men's football leg, by_market_direction_line,
    epochs.LINE_CURVES), fitted on that line's training rows and gated on its
    holdout rows alone (one-sided gate, require_final). The pooled curve of a
    joint hides lines ~5-10 pp apart (both_over_goals_1h UNDER 0.5 -2.9 pp
    beside 1.5 +8.9 pp, 2026-10-21), so a line reads only its own."""
    def split(rows: Iterable[Obs]) -> dict[str, list[tuple[float, int]]]:
        out: dict[str, list[tuple[float, int]]] = collections.defaultdict(list)
        for p, y, label in rows:
            out[label].append((p, y))
        return out
    tr, fi = split(train), split(final)
    ho: dict[str, list[gm.Forecast]] = collections.defaultdict(list)
    for p, y, m, label in holdout:
        ho[label].append((p, y, m))
    verdicts: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for label in sorted(fi):
        fc = gm.fit_curve(fi[label])
        if not fc:
            continue
        g = gm.require_final(gm.gate(gm.fit_curve(tr.get(label, [])),
                                     ho.get(label, []), reps=300), fc)
        g["rows"] = {"train": len(tr.get(label, [])),
                     "holdout": len(ho.get(label, [])), "final": len(fi[label])}
        verdicts[label] = (g, fc)
    return verdicts


_PLAYED: list[Played] = []
_WOMEN: frozenset[int] = frozenset()


def _rows_chunk(job: tuple[str, float, list[Task]]) -> list[list[JointRow]]:
    base, rho, tasks = job
    return [task_rows(t, base, rho) for t in tasks]


def replay_parallel(pool: Any, base: str, rho: float, h0: int, h1: int,
                    cut: int, chunk: int = 400) -> BaseResult:
    """replay_base with the joints (the latent-rho solve is ~40 ms a match)
    computed across the pool; the samples are picked in this process."""
    tasks = base_tasks(_PLAYED, base, cut)
    out = BaseResult(base, rho)
    jobs = [(base, rho, tasks[i:i + chunk]) for i in range(0, len(tasks), chunk)]
    for (_b, _r, part), rows in zip(jobs, pool.imap(_rows_chunk, jobs),
                                    strict=True):
        for task, r in zip(part, rows, strict=True):
            accumulate(out, task[0], r, h0, h1, _WOMEN)
    print(f"{base}: {out.matches} matches, {sum(map(len, out.final.values()))} "
          f"rows", flush=True)
    return out


def class_sections(keys: Mapping[str, tuple[dict[str, Any], dict[str, Any]]]
                   ) -> dict[str, Any]:
    """{class: {"by_market_direction": {key: curve}}} of the passing
    "<class>:<key>" entries (the installer's by_class shape)."""
    out: dict[str, Any] = {}
    for ck, (g, fc) in sorted(keys.items()):
        klass, sep, key = ck.partition(":")
        if sep and g.get("pass"):
            out.setdefault(klass, {"by_market_direction": {}})[
                "by_market_direction"][key] = fc
    return out


def write_group(out: Path, keys: Mapping[str, tuple[dict[str, Any],
                                                    dict[str, Any]]],
                fitted_from: dict[str, Any], rhos: Mapping[str, float],
                lines_by_key: Mapping[str, Mapping[str, tuple[
                    dict[str, Any], dict[str, Any]]]] | None = None) -> None:
    """curves.json (the installer's shape: pooled keys, `by_class`, the
    per-line `by_market_direction_line` with gate keys "<key>@<line>") and
    gate_report.md."""
    out.mkdir(parents=True, exist_ok=True)
    per_line = lines_by_key or {}
    line_gates = {f"{k}@{label}": dict(g)
                  for k, ls in sorted(per_line.items())
                  for label, (g, _) in sorted(ls.items())}
    doc = {"target": TARGET, "group": GROUP, "fitted_from": fitted_from,
           "by_market_direction": {k: fc for k, (g, fc) in sorted(keys.items())
                                   if g.get("pass") and ":" not in k},
           "by_class": class_sections(keys),
           LINE_SECTION: {k: {label: fc for label, (g, fc) in sorted(ls.items())
                              if g.get("pass")}
                          for k, ls in sorted(per_line.items())
                          if any(g.get("pass") for g, _ in ls.values())},
           "gate": {**{k: {x: v for x, v in g.items() if x != "slices"}
                       for k, (g, _) in sorted(keys.items())}, **line_gates},
           "diagnostics": {k: {"slices": g.get("slices"), "rows": g.get("rows")}
                           for k, (g, _) in sorted(keys.items())},
           "side_correlations_used": dict(sorted(rhos.items()))}
    (out / "curves.json").write_text(json.dumps(doc, indent=1) + "\n")
    lines = [f"# Bramka krzywych: {GROUP}", "",
             f"Reguła: {gm.RULE_TEXT}; dodatkowo żaden wycinek linii z n >= "
             f"{gm.MIN_N} nie może zawyżać o więcej niż {gm.MAX_GAP:.0%}.", "",
             f"Źródło: {json.dumps(fitted_from, ensure_ascii=False)}", "",
             "| klucz | n holdout >= 0,70 | mecze | krzywa | realizacja | "
             "luka pp [95%] | wynik |", "|---|---|---|---|---|---|---|"]
    for k, (g, _) in sorted(keys.items()):
        ci = g.get("gap_ci95") or [None, None]
        gap = "" if g.get("gap") is None else (
            f"{100 * g['gap']:+.2f} [{100 * ci[0]:+.2f}, {100 * ci[1]:+.2f}]")
        lines.append(f"| {k} | {g.get('n')} | {g.get('matches')} | "
                     f"{g.get('mean_curve')} | {g.get('realised')} | {gap} | "
                     f"{'PASS' if g.get('pass') else 'FAIL ' + str(g.get('why'))} |")
    lines += ["", "## Krzywe per linia (by_market_direction_line; czytane "
              "pierwsze dla nogi mężczyzn)", "",
              "| klucz@linia | n holdout >= 0,70 | mecze | krzywa | realizacja | "
              "luka pp [95%] | wynik |", "|---|---|---|---|---|---|---|"]
    for k, g in line_gates.items():
        if not g.get("holdout_forecasts"):
            continue
        ci = g.get("gap_ci95") or [None, None]
        gap = "" if g.get("gap") is None else (
            f"{100 * g['gap']:+.2f} [{100 * ci[0]:+.2f}, {100 * ci[1]:+.2f}]")
        lines.append(f"| {k} | {g.get('n')} | {g.get('matches')} | "
                     f"{g.get('mean_curve')} | {g.get('realised')} | {gap} | "
                     f"{'PASS' if g.get('pass') else 'FAIL ' + str(g.get('why'))} |")
    lines += ["", "## Wycinki linii krzywej wspólnej (krzywa treningowa, "
              "holdout)", ""]
    for k, (g, _) in sorted(keys.items()):
        sl = {a: b for a, b in (g.get("slices") or {}).items()
              if b.get("gap") is not None}
        if not sl:
            continue
        lines.append(f"**{k}** - wiersze {g.get('rows')}")
        lines.append("")
        for label, sg in sl.items():
            ci = sg.get("gap_ci95") or [0, 0]
            lines.append(f"- {label}: n {sg['n']}, luka {100 * sg['gap']:+.2f} pp "
                         f"[{100 * ci[0]:+.2f}, {100 * ci[1]:+.2f}]")
        lines.append("")
    (out / "gate_report.md").write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    global _PLAYED, _WOMEN
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--db-path", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--bases", default=",".join(DEFAULT_BASES))
    ap.add_argument("--holdout-from", default="2026-09-01")
    ap.add_argument("--holdout-to", default="2026-10-14")
    ap.add_argument("--before", default="2026-10-17")
    ap.add_argument("--correlations", default=str(config_path(CORRELATIONS_FILE)))
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--use-measured-rho", action="store_true",
                    help="replay a base the correlations file has no number "
                    "for with the residual correlation measured here (and "
                    "stage the file with it); default: SHEET's own reading "
                    "of the installed file (none = independent)")
    ap.add_argument("--stored-rows", help="CSV of the installed joints' "
                    "replay rows (event, competition, market, line, "
                    "direction, p_central, outcome; sofa_settled_row "
                    "run_date 'cache-calibration'): fit only their women's "
                    "class curves (women_from_stored)")
    ap.add_argument("--played-cache", help="pickle of the loaded matches: "
                    "read when present, else written (a later group skips "
                    "the load)")
    ap.add_argument("--awarded-excluded", action="store_true",
                    help="football results awarded at the table (isAwarded) out "
                    "of the replay (calibrate_from_cache --awarded-excluded)")
    args = ap.parse_args(argv)
    bases = [b for b in args.bases.split(",") if b]
    joint_metrics = {b for b in bases if f"{b}_for" in DERIVED_MARGINAL_CENTRES_METRICS}
    if joint_metrics:
        ap.error(f"{sorted(joint_metrics)} read the marginal centres "
                 "(calibrate_from_cache --derived), not the raw samples")
    out = Path(args.out_dir)
    h0, h1, cut = _ts(args.holdout_from), _ts(args.holdout_to), _ts(args.before)
    t0 = datetime.now(UTC)
    cache = Path(args.played_cache) if args.played_cache else None
    if cache is not None and cache.is_file():
        with cache.open("rb") as fh:
            held = pickle.load(fh)
        # a pickle written before --awarded-excluded holds (played, classes)
        # loaded with the awarded results in
        if bool(held[2] if len(held) > 2 else False) != args.awarded_excluded:
            print(f"--played-cache {cache} was loaded with awarded_excluded="
                  f"{not args.awarded_excluded}; delete it or drop the flag",
                  file=sys.stderr)
            return 2
        _PLAYED, classes = held[0], held[1]
    else:
        _PLAYED = load_cache(Path(args.db_path), sports=("football",),
                             until_ts=cut, read_only=True,
                             awarded_out=args.awarded_excluded)
        classes = load_event_classes(args.db_path)
        if cache is not None:
            with cache.open("wb") as fh:
                pickle.dump((_PLAYED, classes, args.awarded_excluded), fh,
                            protocol=5)
    print(f"loaded {len(_PLAYED)} football matches "
          f"({(datetime.now(UTC) - t0).seconds}s)", flush=True)
    _WOMEN = frozenset(e for e, k in classes.items() if k == CLASS_WOMEN)
    print(f"women events {len(_WOMEN)}", flush=True)

    measured = {b: measure_rho(_PLAYED, b, h0) for b in bases}
    file_doc = json.loads(Path(args.correlations).read_text(encoding="utf-8"))
    staged, rhos = side_correlations(
        file_doc, bases, measured if args.use_measured_rho else {})
    out.mkdir(parents=True, exist_ok=True)
    (out / "side_correlations.json").write_text(
        json.dumps(staged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "correlations.json").write_text(json.dumps(
        {b: {"measured": m[0], "pairs": m[1], "residual_pairs": m[2],
             "used": rhos[b]} for b, m in measured.items()}, indent=1) + "\n")
    print(json.dumps({b: [measured[b][0], rhos[b]] for b in bases}), flush=True)

    keys: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    if args.stored_rows:
        ts_by_event = {m.event_id: m.timestamp for m in _PLAYED}
        res = women_from_stored(Path(args.stored_rows), ts_by_event, _WOMEN,
                                h0, h1, cut)
        for key in sorted(res.final):
            keys[key] = gate_key(res.train.get(key, []),
                                 res.holdout.get(key, []), res.final[key])
        fitted_from = {
            "db_path": args.db_path, "stored_rows": args.stored_rows,
            "holdout_from": args.holdout_from, "holdout_to": args.holdout_to,
            "before": args.before,
            "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "script": "scripts/sofa/fit_joint_curves.py --stored-rows",
            "replay": "the installed curves' replay rows (refit 2026-10-17, "
                      "--derived), women's matches only"}
        write_group(out / GROUP, keys, fitted_from, {})
        print(json.dumps({k: (g["pass"], g.get("n"), g.get("gap"))
                          for k, (g, _) in sorted(keys.items())}, indent=1))
        return 0
    with mp.get_context("fork").Pool(args.jobs) as pool:
        results = [replay_parallel(pool, b, rhos[b], h0, h1, cut) for b in bases]
    lines_by_key: dict[str, dict[str, tuple[dict[str, Any], dict[str, Any]]]] = {}
    for res in results:
        for key in sorted(res.final):
            g, fc = gate_key(res.train.get(key, []), res.holdout.get(key, []),
                             res.final[key])
            g["side_correlation"] = res.rho
            keys[key] = (g, fc)
            if ":" not in key:
                # a class leg never reads a line curve (Calibration.realised)
                lines_by_key[key] = gate_lines(
                    res.train.get(key, []), res.holdout.get(key, []),
                    res.final[key])
                # a men's leg reads its own line's curve only: the pooled
                # curve would stand in for a line that failed or was never
                # judged (both_over_saves_1h UNDER 0.5: -20.8 pp on 100
                # holdout lines under a passing pool)
                g["pooled_pass"] = g.get("pass")
                g["pass"] = False
                g["why"] = "not staged: a men's leg reads its line's own curve"
    fitted_from = {
        "db_path": args.db_path, "holdout_from": args.holdout_from,
        "holdout_to": args.holdout_to, "before": args.before,
        "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "script": "scripts/sofa/fit_joint_curves.py",
        "replay": "calibrate_from_cache.football_joint_rows, raw samples "
                  "(no marginal centres), side correlations "
                  "side_correlations.json"}
    write_group(out / GROUP, keys, fitted_from, rhos, lines_by_key)
    print(json.dumps({k: (g["pass"], g.get("n"), g.get("gap"))
                      for k, (g, _) in sorted(keys.items())}, indent=1))
    print(json.dumps({f"{k}@{label}": (g["pass"], g.get("n"), g.get("gap"))
                      for k, ls in sorted(lines_by_key.items())
                      for label, (g, _) in sorted(ls.items())
                      if g.get("pass")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
