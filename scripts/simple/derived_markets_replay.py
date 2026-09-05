#!/usr/bin/env python3
"""Re-derive the comparative-market calibration from the runs on disk.

    python3 scripts/simple/derived_markets_replay.py
    python3 scripts/simple/derived_markets_replay.py --metric corners_for --verbose
    python3 scripts/simple/derived_markets_replay.py --check

Why this exists. Every constant in ``bet.simple_stats.derived_markets`` --
the base rates, the home deltas, the Brier scores, the gate hit rates and their
bootstrap intervals -- is a measurement, and a measurement copied by hand into a
source file is a claim nobody can check. This script is the measurement, run
against the same artifacts it was first taken from, using the shipped estimator
rather than a private copy of it.

``--check`` re-derives and compares against ``CALIBRATION``, exiting non-zero on
any disagreement outside tolerance. That is what makes the table in that module
an assertion rather than a memory: change the estimator and this fails until the
table is brought back in line.

The replay is honest about time: a dossier written on date D holds only matches
played before D, and the actuals it is scored against are the fixtures of D
itself, so nothing here can see its own answer. It reads no network -- football
actuals come from ``runs/_backtest_actuals.json``, which ``backtest_slate.py``
populated -- and it costs no provider requests.

Exit codes: 0 = agreed (or reported), 1 = a constant disagrees, 2 = bad input.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bet.simple_stats.derived_markets import (  # noqa: E402
    CALIBRATION,
    GATE,
    MIN_SAMPLE,
    REFUSED,
    SHRINK_K,
    Triple,
    shrink,
    skellam_three_way,
)

# The slates with both a dossier and settled actuals. 2026-08-25 has a dossier
# of 235 kB and no football; 09-04 and 09-05 were never settled.
REPLAY_DATES = (
    "2026-08-28",
    "2026-08-29",
    "2026-08-31",
    "2026-09-01",
    "2026-09-02",
    "2026-09-03",
    "2026-09-04",
)

# Everything the module has an opinion about, including the three it refuses --
# a refusal is a measurement too, and it has to keep being true.
REPLAYED_METRICS = (
    "corners_for",
    "shots_for",
    "shots_on_target_for",
    "cards_for",
    "fouls_for",
    "corners_1h_for",
)


def load_rows(runs_dir: Path, metric: str) -> list[dict]:
    """(home sample, away sample, home actual, away actual) per settled fixture."""
    actuals = json.loads((runs_dir / "_backtest_actuals.json").read_text())
    rows: list[dict] = []
    for date in REPLAY_DATES:
        base = runs_dir / date
        events_path = base / f"{date}_event_list.json"
        dossier_path = base / f"{date}_event_dossiers.json"
        if not (events_path.exists() and dossier_path.exists()):
            continue
        events = {
            e["event_id"]: e
            for e in json.loads(events_path.read_text())["events"]
            if e["sport"] == "football"
        }
        for dossier in json.loads(dossier_path.read_text())["dossiers"]:
            event = events.get(dossier["event_id"])
            if event is None:
                continue
            bzz = (event.get("source_ids") or {}).get("bzzoiro")
            actual = actuals.get(str(bzz)) if bzz else None
            if not actual:
                continue
            observation = (dossier.get("metrics") or {}).get(metric)
            if not observation:
                continue
            home = [v["value"] for v in observation.get("team_a_l10") or []]
            away = [v["value"] for v in observation.get("team_b_l10") or []]
            if len(home) < MIN_SAMPLE or len(away) < MIN_SAMPLE:
                continue
            home_actual = actual.get("home", {}).get(metric)
            away_actual = actual.get("away", {}).get(metric)
            if home_actual is None or away_actual is None:
                continue
            # ``team_a`` is the home side. Not assumed: ENRICH builds the two
            # buckets from ``event.home_team`` / ``event.away_team``, and the
            # names are carried on the dossier so this can be checked rather
            # than trusted -- ``--verbose`` reports any row where it fails.
            rows.append(
                {
                    "date": date,
                    "home_team": event["home_team"],
                    "away_team": event["away_team"],
                    "team_a": dossier.get("team_a_name") or "",
                    "sample_home": home,
                    "sample_away": away,
                    "actual_home": float(home_actual),
                    "actual_away": float(away_actual),
                }
            )
    return rows


def outcome_of(row: dict) -> int:
    """0 = home took more, 1 = level, 2 = away took more."""
    if row["actual_home"] > row["actual_away"]:
        return 0
    return 1 if row["actual_home"] == row["actual_away"] else 2


def brier(predictions: list[Triple], outcomes: list[int]) -> float:
    total = 0.0
    for probs, outcome in zip(predictions, outcomes, strict=True):
        truth = [0.0, 0.0, 0.0]
        truth[outcome] = 1.0
        total += sum((p - t) ** 2 for p, t in zip(probs, truth, strict=True))
    return total / len(outcomes)


def measure(rows: list[dict]) -> dict:
    """Everything ``Calibration`` holds, derived from these rows alone."""
    outcomes = [outcome_of(r) for r in rows]
    n = len(rows)
    counts = Counter(outcomes)
    base: Triple = (counts[0] / n, counts[1] / n, counts[2] / n)
    home_delta = (
        sum(r["actual_home"] for r in rows) - sum(r["actual_away"] for r in rows)
    ) / n
    predictions: list[Triple] = []
    for row in rows:
        lam_home = statistics.mean(row["sample_home"]) + home_delta / 2
        lam_away = statistics.mean(row["sample_away"]) - home_delta / 2
        if lam_home <= 0 or lam_away <= 0:
            predictions.append(base)
            continue
        predictions.append(
            shrink(skellam_three_way(lam_home, lam_away), base, SHRINK_K)
        )
    hits = [
        1 if outcome == side else 0
        for probs, outcome in zip(predictions, outcomes, strict=True)
        for side in (0, 2)
        if probs[side] >= GATE
    ]
    # Two intervals: rows resampled independently, and whole slates resampled.
    # The second exists because the rows are not independent -- one slate is
    # 46% of the corner replay -- and an iid bootstrap over them would report a
    # precision the sample does not have.
    hits_by_day: dict[str, list[int]] = {}
    for row, probs, outcome in zip(rows, predictions, outcomes, strict=True):
        for side in (0, 2):
            if probs[side] >= GATE:
                hits_by_day.setdefault(row["date"], []).append(
                    1 if outcome == side else 0
                )
    interval = None
    interval_by_day = None
    if hits:
        random.seed(7)
        draws = sorted(
            statistics.mean(random.choices(hits, k=len(hits))) for _ in range(2000)
        )
        interval = (draws[50], draws[1949])
        blocks = [v for v in hits_by_day.values() if v]
        if len(blocks) > 1:
            random.seed(7)
            block_draws = sorted(
                statistics.mean(
                    [x for _ in blocks for x in random.choice(blocks)]
                )
                for _ in range(2000)
            )
            interval_by_day = (block_draws[50], block_draws[1949])
    return {
        "n": n,
        "base": base,
        "home_delta": home_delta,
        "brier_base": brier([base] * n, outcomes),
        "brier_model": brier(predictions, outcomes),
        "gate_n": len(hits),
        "gate_hits": statistics.mean(hits) if hits else None,
        "gate_ci": interval,
        "gate_ci_by_day": interval_by_day,
        "largest_slate_share": (
            max(len(v) for v in hits_by_day.values()) / len(hits) if hits else 0.0
        ),
        "mean_predicted_home": statistics.mean(p[0] for p in predictions),
        "realised_home": base[0],
        "side_mismatch": sum(
            1
            for r in rows
            if r["team_a"]
            and r["team_a"].split()[0].lower() not in (r["home_team"] or "").lower()
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--runs-dir", type=Path, default=ROOT / "runs")
    parser.add_argument("--metric", action="append", default=[])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    if not (args.runs_dir / "_backtest_actuals.json").exists():
        print(f"brak {args.runs_dir}/_backtest_actuals.json", file=sys.stderr)
        return 2

    metrics = args.metric or list(REPLAYED_METRICS)
    disagreements: list[str] = []
    print(
        f"{'metryka':22s} {'n':>4s} {'baza':>7s} {'model':>7s}"
        f" {'delta':>7s} {'próg':>7s} {'n_próg':>6s}"
    )
    for metric in metrics:
        rows = load_rows(args.runs_dir, metric)
        if len(rows) < 20:
            print(f"{metric:22s} n={len(rows)} - za mało, pomijam")
            continue
        got = measure(rows)
        gate = f"{got['gate_hits']:.3f}" if got["gate_hits"] is not None else "-"
        print(
            f"{metric:22s} {got['n']:4d} {got['brier_base']:7.4f} "
            f"{got['brier_model']:7.4f} {got['home_delta']:+7.2f} "
            f"{gate:>7s} {got['gate_n']:6d}"
        )
        if args.verbose:
            print(
                f"    baza {got['base'][0]:.3f}/{got['base'][1]:.3f}"
                f"/{got['base'][2]:.3f}"
                f"   średnia przewidziana P(gosp) {got['mean_predicted_home']:.3f}"
                f" wobec realnej {got['realised_home']:.3f}"
                f"   wierszy z team_a != gospodarz: {got['side_mismatch']}"
            )
            if got["gate_ci"]:
                print(
                    f"    bootstrap iid 95%: "
                    f"[{got['gate_ci'][0]:.3f}, {got['gate_ci'][1]:.3f}]"
                )
            if got["gate_ci_by_day"]:
                print(
                    f"    bootstrap blokowy po dniach 95%: "
                    f"[{got['gate_ci_by_day'][0]:.3f}, {got['gate_ci_by_day'][1]:.3f}]"
                    "   (największa kolejka to "
                    f"{got['largest_slate_share']:.0%} trafień)"
                )
        if metric in REFUSED:
            if got["brier_model"] < got["brier_base"]:
                disagreements.append(
                    f"{metric}: ODMAWIANA, a bije bazę ({got['brier_model']:.4f} "
                    f"< {got['brier_base']:.4f}) - odmowa jest nieaktualna"
                )
            continue
        cal = CALIBRATION.get(metric)
        if cal is None:
            continue
        for label, want, have, tol in (
            ("n", cal.n, got["n"], 0),
            ("brier_base", cal.brier_base, got["brier_base"], 5e-4),
            ("brier_model", cal.brier_model, got["brier_model"], 5e-4),
            ("home_delta", cal.home_delta, got["home_delta"], 5e-3),
            ("gate_hits", cal.gate_hits, got["gate_hits"], 5e-4),
            ("gate_n", cal.gate_n, got["gate_n"], 0),
        ):
            if have is None or abs(want - have) > tol:
                disagreements.append(
                    f"{metric}.{label}: w kodzie {want}, zmierzone {have}"
                )
        for label, want_ci, have_ci in (
            ("gate_ci", cal.gate_ci, got["gate_ci"]),
            ("gate_ci_by_day", cal.gate_ci_by_day, got["gate_ci_by_day"]),
        ):
            if want_ci is None or have_ci is None:
                continue
            if any(abs(w - h) > 5e-3 for w, h in zip(want_ci, have_ci, strict=True)):
                disagreements.append(
                    f"{metric}.{label}: w kodzie {want_ci}, zmierzone "
                    f"({have_ci[0]:.3f}, {have_ci[1]:.3f})"
                )
        for i, (want, have) in enumerate(zip(cal.base, got["base"], strict=True)):
            if abs(want - have) > 5e-4:
                disagreements.append(
                    f"{metric}.base[{i}]: w kodzie {want}, zmierzone {have:.4f}"
                )

    if disagreements:
        print("\nROZBIEŻNOŚCI:")
        for line in disagreements:
            print(f"  {line}")
        return 1 if args.check else 0
    print("\nWszystkie stałe w CALIBRATION zgadzają się z odtworzonym pomiarem.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
