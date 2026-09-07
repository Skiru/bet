#!/usr/bin/env python3
"""Does each market's sample measure the quantity the book settles?

    python3 scripts/simple/audit_sample_bias.py
    python3 scripts/simple/audit_sample_bias.py --check      # exit 1 on drift
    python3 scripts/simple/audit_sample_bias.py --write      # config/sample_drift.json

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

``--write`` is what stops this being a thing only a hand-run remembers.
Until 2026-09-07 the whole of this knowledge lived in the output above: the
sheet, the forecast and the coupon said nothing, so ``cards_points_total``
carried the forecast's best grade (``MEASURED``) while its sample ran half a
point low, and three of the four card rows on the 2026-09-07 coupon were
UNDERs -- the side that drift inflates. ``--write`` emits
``config/sample_drift.json``, ``forecast.py`` names the drift on the affected
market's card and ``coupons.py`` puts it on every row of that market.

What is written is a *statement*, never a correction. Nothing downstream
subtracts ``delta`` from a centre or a probability, for the reason
``market_priors.json`` already records against fitting a prior per run: the
delta is measured on the same slates it would be applied to, and a fitted
constant is overfitting until ``validate_calibration.py`` shows out of sample
that it helps. Naming a drift costs nothing if it turns out to be noise;
correcting for one that is noise moves every rung on the market.

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
DRIFT_OUT = ROOT / "config" / "sample_drift.json"

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


def collect(
    runs_dir: Path, cache: dict, dates_used: set[str] | None = None
) -> dict[str, list[float]]:
    """``{market: [actual - sample mean, ...]}``, one entry per fixture.

    ``dates_used``, when given, is filled with the slates that contributed at
    least one delta. It exists so ``--write`` can date its own numbers off the
    data rather than off the clock -- a wall-clock stamp would make the config
    differ on every regeneration and lose the byte-for-byte diff that is how a
    config change is reviewed here.
    """
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
        if seen and dates_used is not None:
            dates_used.add(date)
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


def document(rows: list[dict], dates: set[str]) -> dict:
    """The ``config/sample_drift.json`` payload for one audit pass.

    Every market this pass could measure is written, not only the drifted ones.
    A reader has to be able to tell "checked, centred" from "never checked" --
    the second is the state ``red_cards_total`` was in for the whole of the
    period it was shipping a sample built only from matches that had a red card
    -- and a file holding two entries could not say which of the other
    seventeen markets it had looked at.
    """
    dated = sorted(dates)
    return {
        "_purpose": (
            "Whether each market's sample counts the same quantity Superbet "
            "settles, measured over the settled slates in runs/. Read by "
            "simple_stats/forecast.py and simple_stats/coupons.py so a drifted "
            "market says so on its own card and on every coupon row, instead of "
            "the knowledge living in a script somebody has to remember to run. "
            "Rebuild with scripts/simple/audit_sample_bias.py --write."
        ),
        "_reading_it": (
            "delta is signed actual minus sample mean, so POSITIVE means the "
            "sample runs LOW: the match returns more than the sample expected. "
            "A low sample overstates UNDER and understates OVER -- the UNDER "
            "looks likelier than it is, because the line sits further above the "
            "sample's centre than it really sits above the truth. Invert this "
            "sign and every caveat in the pipeline points at the wrong side of "
            "the market while looking like a fix, which is why it is written "
            "here rather than left to be re-derived. z is delta/SE with one row "
            "per fixture, never per rung: a ladder contributes eight rungs to "
            "the sheet and one match to reality, and counting the rungs would "
            "divide every SE by about three and turn noise into drift."
        ),
        "_the_finding": (
            "The card markets, and only the card markets, are both drifted and "
            "bettable. cards_points_total runs 0.55 low a match over 266 "
            "fixtures (z=+3.86) and cards_points_for 0.28 over 525 (z=+3.84); "
            "everything else Superbet prices is centred to within its own "
            "noise. Project memory records the cause as competition mix rather "
            "than transcription -- a hand check found 160 of 160 sampled values "
            "identical to the provider's -- so the sample is reading the right "
            "numbers off the right matches and the matches are simply not the "
            "mix today's fixture comes from. cards_total (+0.42, z=+3.78) and "
            "cards_for (+0.20, z=+3.68) drift too and are reported without "
            "failing anything, because Superbet's card lines have mapped to "
            "cards_points_* since 2026-09-03 and a drift that cannot reach a "
            "bet must not train the operator to ignore this file."
        ),
        "_why_a_caveat_and_not_a_grade": (
            "The forecast states this next to its grade and never as a grade, "
            "and the reason is measured rather than stylistic. The grade "
            "answers two questions -- did the fixture-specific sample beat "
            "predicting the average (skill), and do the rungs realise what they "
            "claim (calibration) -- and on both of them cards_points_total is "
            "genuinely the best football market in market_reliability.json: "
            "skill +9.7%, calibration error 0.0001. Demoting it would delete "
            "two true facts to report a third. The third is independent: the "
            "existing BIASED grade fires on |bias| > 0.25 * actual_sd, a "
            "MATERIALITY test, while this file's |z| > 3 is a CERTAINTY test, "
            "and the two cross. shots_total carries a bias of -0.978, 2.8 times "
            "cards_points_total's, and is not drifted (z=+1.60) because its "
            "spread is huge; red_cards_total is graded BIASED and is centred "
            "here (-0.03) because the audit skips the slates built by the "
            "superseded sample. Neither test subsumes the other. And the part "
            "with money on it is a SIDE -- UNDER overstated, OVER understated "
            "-- which no grade in the file encodes at all."
        ),
        "_why_not_a_correction": (
            "Nothing downstream subtracts delta from a centre, a mean or a "
            "probability, and this file must not be wired to. The delta is "
            "measured on the same slates it would be applied to, so shipping it "
            "as a constant fits the estimator to its own test set -- the "
            "objection market_priors.json already records against computing its "
            "prior per run, and the one project memory records for leaving the "
            "tennis length markets' 25pp overconfidence deliberately "
            "uncorrected. The route to correcting it exists and has a gate: "
            "scripts/simple/validate_calibration.py does leave-one-DATE-out and "
            "exits non-zero when a change does not help out of sample. Name the "
            "drift first; correct it only against that."
        ),
        "_thresholds": (
            "min_fixtures is the floor below which a market is reported and "
            "never failed on, because the SE is too wide for |z| > 3 to mean "
            "anything and a newly added market would otherwise block every run "
            "until it had a history. max_abs_z is Bonferroni-safe across the "
            "~17 markets tested together: a two-sided z of 3 is p < 0.003 per "
            "market, so a clean repo trips this by chance about once in twenty "
            "full audits. priced is read off the two most recent offers on disk "
            "-- see priced_markets in the script for why only the newest count."
        ),
        "_measured_over": (
            f"{len(dated)} settled slates"
            + (f", {dated[0]} to {dated[-1]}" if dated else "")
            + ". Slates whose sample definition predates a change to that "
            "market are skipped rather than reported as drift; see "
            "SAMPLE_DEFINITION_CHANGED_ON in the script."
        ),
        "thresholds": {"min_fixtures": MIN_FIXTURES, "max_abs_z": MAX_ABS_Z},
        "markets": {
            row["market"]: {
                "delta": round(row["delta"], 4),
                "se": round(row["se"], 4),
                "z": round(row["z"], 3),
                "fixtures": row["n"],
                "priced": row["priced"],
                # The one field a consumer is meant to branch on, so that the
                # thresholds are applied once here and not re-decided by every
                # reader. A market drifts only if it is measurable, certain and
                # bettable at once.
                "drifted": (
                    row["n"] >= MIN_FIXTURES
                    and abs(row["z"]) > MAX_ABS_Z
                    and row["priced"]
                ),
                # Which side of this market the drift makes look better than it
                # is. Written out rather than left to the sign, because that is
                # the inversion this whole file exists to prevent.
                "overstated_side": "UNDER" if row["delta"] > 0 else "OVER",
            }
            for row in sorted(rows, key=lambda r: r["market"])
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--runs-dir", default=str(ROOT / "runs"))
    parser.add_argument("--cache", default=str(DEFAULT_CACHE))
    parser.add_argument("--check", action="store_true",
                        help="Exit 1 when a market has drifted")
    parser.add_argument("--write", action="store_true",
                        help=f"Write {DRIFT_OUT.relative_to(ROOT)}")
    parser.add_argument("--out", default=str(DRIFT_OUT),
                        help="Where --write puts the config")
    args = parser.parse_args()

    cache_path = Path(args.cache)
    if not cache_path.exists():
        print("brak runs/_backtest_actuals.json -- uruchom najpierw backtest_slate.py",
              file=sys.stderr)
        return 2
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    runs_dir = Path(args.runs_dir)
    dates_used: set[str] = set()
    deltas = collect(runs_dir, cache, dates_used)
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

    if args.write:
        out_path = Path(args.out)
        out_path.write_text(
            json.dumps(
                document(rows, dates_used), ensure_ascii=False, indent=1
            ) + "\n",
            encoding="utf-8",
        )
        print(
            f"\nzapisano {out_path} — {len(rows)} rynków, "
            f"{sum(1 for r in rows if r['n'] >= MIN_FIXTURES and abs(r['z']) > MAX_ABS_Z and r['priced'])}"
            " z dryfem"
        )

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
