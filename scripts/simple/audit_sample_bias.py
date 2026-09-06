#!/usr/bin/env python3
"""Does each market's sample measure the quantity the book settles?

    python3 scripts/simple/audit_sample_bias.py
    python3 scripts/simple/audit_sample_bias.py --check      # exit 1 on drift

Why this exists. Every other check in this repo asks whether a *probability*
was right. This one asks something prior and cheaper to get wrong: whether the
sample is counting the same thing the bookmaker counts. When it is not, nothing
downstream can notice -- ``p_low``, ``p_central``, the shrink and the ladder
gates are all internally consistent with a sample that measures the wrong
quantity, and the rows lose in a way that looks like bad luck.

That failure has happened here. ``cards_total`` counted yellows only while
Superbet counted reds too; it took a hand audit of one Grêmio-Internacional
slip to find, and the replacement (``cards_points_total``, off ``/incidents/``)
was written in September 2026. This script is what would have caught it in a
line of output: over the slates on disk ``cards_total`` still comes in 0.60
cards *under* what actually happens (+19%), while ``cards_points_total`` sits
at -0.00.

The test is a paired one and deliberately dull. For every (fixture, market,
subject) the sheet priced and the actuals cover, take ``actual - sample mean``.
If the sample measures the right quantity that difference is centred on zero,
whatever the model does with it afterwards. ``z = mean(delta) / SE`` and
``--check`` fails at |z| > 3, which is Bonferroni-safe across the ~17 markets
tested at once and does not fire on the honest noise of a small slate.

**One row per fixture, not per rung.** A ladder contributes eight rows to the
sheet and one match to reality; counting the rungs would shrink every standard
error by a factor of three and make noise look like drift.

It reads no network and costs no provider requests: sheets from ``runs/`` and
actuals from ``runs/_backtest_actuals.json``, which ``backtest_slate.py``
populates.

Exit codes: 0 = every market is centred (or reported), 1 = drift, 2 = no data.
"""
from __future__ import annotations

import argparse
import gc
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bet.simple_stats.contracts import EventListV1  # noqa: E402
from bet.simple_stats.settle import actual_value, team_side  # noqa: E402

DEFAULT_CACHE = ROOT / "runs" / "_backtest_actuals.json"

# Below this a market is reported and never failed on: the SE is too wide for
# |z| > 3 to mean anything, and a market that has just been added would
# otherwise block every run until it accumulated a history.
MIN_FIXTURES = 25

# Bonferroni-safe across the markets tested together (~17): a two-sided z of 3
# is p < 0.003 per market, so a clean repo fails this by chance about once in
# twenty full audits, not once a week.
MAX_ABS_Z = 3.0

# How many of the newest slates define "a market you can bet". See
# ``priced_markets``.
_OFFER_DATES_FOR_PRICED = 2


def priced_markets(runs_dir: Path) -> set[str]:
    """Markets Superbet has actually posted a line on, across every offer on disk.

    ``--check`` fails only on these, and the rule is not a convenience. A
    market the book does not price cannot be settled against the book's own
    definition and cannot cost money whatever its sample measures. The live
    case is ``cards_total``: it is yellow-only, it drifts +0.42 a match against
    what happens, and every card line Superbet posts now maps to
    ``cards_points_*`` instead -- so the drift is real, reported, and unable to
    reach a bet. Failing a run on it would train the operator to ignore this
    script, which is the one outcome that makes a guard worse than nothing.

    **Only the most recent offers count**, and ``cards_total`` is exactly why.
    Superbet's card lines mapped to it on 2026-09-01 and 09-02 and to
    ``cards_points_*`` from 09-03 on; a set built from all history would keep
    failing on a mapping that was fixed, which is how a guard becomes noise.
    Two dates rather than one so a single thin slate cannot retire a market
    that is merely absent that day.
    """
    dates = sorted(
        {path.parent.name for path in runs_dir.glob("*/[0-9]*_superbet_offer.json")}
    )[-_OFFER_DATES_FOR_PRICED:]
    markets: set[str] = set()
    for path in sorted(runs_dir.glob("*/[0-9]*_superbet_offer.json")):
        if path.parent.name not in dates:
            continue
        try:
            offer = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for event in offer.get("events") or []:
            for line in event.get("lines") or []:
                market = line.get("market")
                if market:
                    markets.add(market)
    return markets


def _sheet_rows(date: str, runs_dir: Path):
    path = runs_dir / date / f"{date}_event_dossiers_stats_sheet.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))["rows"]


def _events(date: str, runs_dir: Path):
    path = runs_dir / date / f"{date}_event_list.json"
    if not path.exists():
        return None
    return EventListV1.model_validate_json(path.read_text(encoding="utf-8"))


# Markets whose *sample* definition changed on a date, and the date it changed.
#
# This audit compares a sheet's ``mean`` against what the match returned. Both
# sides have to be built by the same rules or the drift it reports is a diff
# between two versions of this repo rather than a fault in the data.
#
# ``red_cards_total`` is the case that forced this. Until 2026-09-06 the
# provider's omission of ``red_cards`` on a match with no red card left that
# match out of the sample entirely, so the sample was built only from matches
# that had one and read 0.280 against a truth of 0.146. ``_fill_absent_red_cards``
# writes the zero now, and a re-enrichment of the 2026-09-06 slate moved the
# red-to-card observation ratio from 0.55 to 1.02 and the mean to 0.170.
#
# A slate enriched before that date cannot be compared and is skipped rather
# than reported as drift: its sheet is a historical document and the fixtures
# in it are long finished, so there is no re-enrichment that would fix it. The
# check is on the *artifact's* generation date, not on today's, so this stops
# being a skip the moment a slate is enriched by current code.
SAMPLE_DEFINITION_CHANGED_ON = {
    "red_cards_total": "2026-09-06",
    "red_cards_1h_total": "2026-09-06",
    "red_cards_2h_total": "2026-09-06",
}


def _predates_definition_change(market: str, date: str) -> bool:
    """Whether this slate's sample of ``market`` was built by superseded rules."""
    changed_on = SAMPLE_DEFINITION_CHANGED_ON.get(market)
    return changed_on is not None and date < changed_on


def collect(runs_dir: Path, cache: dict) -> dict[str, list[float]]:
    """``{market: [actual - sample mean, ...]}``, one entry per fixture."""
    deltas: dict[str, list[float]] = defaultdict(list)
    for date_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        date = date_dir.name
        events = _events(date, runs_dir)
        if events is None:
            continue
        actuals_by_event = {}
        sides_by_event = {}
        for event in events.events:
            bzz = (event.source_ids or {}).get("bzzoiro")
            entry = cache.get(str(bzz)) if bzz else None
            if entry:
                actuals_by_event[event.event_id] = entry
                sides_by_event[event.event_id] = (event.home_team, event.away_team)
        if not actuals_by_event:
            continue
        rows = _sheet_rows(date, runs_dir)
        if rows is None:
            continue
        # Deduped here rather than after, so one slate's ladder cannot outvote
        # another slate's whole card.
        seen: dict[tuple, float] = {}
        for row in rows:
            actuals = actuals_by_event.get(row["event_id"])
            if actuals is None or row.get("mean") is None:
                continue
            market = row["market"]
            if _predates_definition_change(market, date):
                continue
            subject = row.get("player_name") or row.get("team_name")
            key = (date, row["event_id"], market, str(subject))
            if key in seen:
                continue
            home, away = sides_by_event[row["event_id"]]
            if market.startswith("player_"):
                # A prop's subject is one person and the "sample mean" is his
                # own average; settling it needs the box score, which this
                # audit deliberately does not reach for -- one call per fixture
                # is cheap, one per player is not, and the team markets are
                # where a definition mismatch has actually happened.
                continue
            side = team_side(row.get("team_name"), home, away)
            if row.get("team_name") and side is None:
                continue
            value = actual_value(actuals, market, side)
            if value is None:
                continue
            seen[key] = value - float(row["mean"])
        for (_, _, market, _), delta in seen.items():
            deltas[market].append(delta)
        del rows
        gc.collect()
    return deltas


def report(
    deltas: dict[str, list[float]], priced: set[str] | None = None
) -> tuple[list[dict], list[dict]]:
    out: list[dict] = []
    for market, values in deltas.items():
        n = len(values)
        mean = statistics.mean(values)
        sd = statistics.stdev(values) if n > 1 else 0.0
        se = sd / math.sqrt(n) if sd else 0.0
        out.append({
            "market": market, "n": n, "delta": mean, "se": se,
            "z": (mean / se) if se else 0.0,
            "priced": priced is None or market in priced,
        })
    out.sort(key=lambda r: -r["n"])
    drifted = [r for r in out
               if r["n"] >= MIN_FIXTURES and abs(r["z"]) > MAX_ABS_Z and r["priced"]]
    return out, drifted


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--runs-dir", default=str(ROOT / "runs"))
    parser.add_argument("--cache", default=str(DEFAULT_CACHE))
    parser.add_argument("--check", action="store_true",
                        help="Exit 1 when a market has drifted")
    args = parser.parse_args()

    cache_path = Path(args.cache)
    if not cache_path.exists():
        print("brak runs/_backtest_actuals.json -- uruchom najpierw backtest_slate.py",
              file=sys.stderr)
        return 2
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    runs_dir = Path(args.runs_dir)
    deltas = collect(runs_dir, cache)
    if not deltas:
        print("nie ma czego zmierzyć", file=sys.stderr)
        return 2

    priced = priced_markets(runs_dir)
    rows, drifted = report(deltas, priced or None)
    print(f"{'rynek':<24} {'meczów':>7} {'Δ (wynik − próbka)':>19} {'SE':>7} {'z':>7}  werdykt")
    for row in rows:
        if row["n"] < MIN_FIXTURES:
            verdict = f"za mało meczów (<{MIN_FIXTURES})"
        elif abs(row["z"]) > MAX_ABS_Z and row["priced"]:
            verdict = "PRZESUNIĘTY — próbka mierzy co innego niż rozliczenie"
        elif abs(row["z"]) > MAX_ABS_Z:
            verdict = "przesunięty, ale Superbet tego nie wystawia — nie do obstawienia"
        else:
            verdict = "ok"
        print(f"{row['market']:<24} {row['n']:>7} {row['delta']:>+19.2f} "
              f"{row['se']:>7.2f} {row['z']:>+7.2f}  {verdict}")

    if args.check and drifted:
        print("\nRynki, których próbka nie mierzy tego, co bukmacher rozlicza:",
              file=sys.stderr)
        for row in drifted:
            print(f"  {row['market']}: {row['delta']:+.2f} na mecz "
                  f"(z={row['z']:+.2f}, n={row['n']})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
