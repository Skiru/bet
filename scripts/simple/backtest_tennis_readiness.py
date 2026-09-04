#!/usr/bin/env python3
"""Does tennis READY predict anything? Settle the sheet and find out.

    python3 scripts/simple/backtest_tennis_readiness.py
    python3 scripts/simple/backtest_tennis_readiness.py --date 2026-09-02 --date 2026-09-03

Why this exists. ``bet_builder_draft.tier_for_row`` hands CALL to a row whose
sport has a *primary provider* and whose dossier is READY. Tennis is excluded
from that clause, and the exclusion has never been an argument about tennis: it
was written when tennis READY was unreachable (``enrich._compute_readiness``
asked for three priority metrics with 2+ providers, against a ceiling of one),
so the clause was a no-op wearing a justification. Tennis can be READY since
2026-09-04, and the honest reason to keep the exclusion is now the only one
left -- the READY-to-CALL promotion was measured on football, and nothing has
ever settled a tennis row.

This settles them. Readiness is **recomputed** from each slate's frozen dossier
with current code rather than read off the sheet: every sheet on disk was
written under the old rule and says PARTIAL on every row, so the column that
would be grouped on is a constant.

Coverage is the length markets -- total games, total sets, a player's games --
which is 60% of the tennis rows on the slates on disk. Aces and double faults
are not settled and are not guessed: ESPN answers ``statsSource: none`` for
tennis, so its scoreboard states no serve counts. Rows this cannot settle are
reported as uncovered and excluded from every rate, never scored as losses.

Exit codes: 0 = report written, 2 = bad input or nothing to settle.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from typing import NamedTuple
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import importlib.util  # noqa: E402

from bet.simple_stats.contracts import EventListV1  # noqa: E402
from bet.simple_stats.enrich import _compute_readiness  # noqa: E402
from bet.simple_stats.providers import PROVIDERS_BY_SPORT  # noqa: E402
from bet.simple_stats.settle import Outcome, settle_row  # noqa: E402

_BT_PATH = ROOT / "scripts" / "simple" / "backtest_slate.py"


def _backtest_module():
    """``backtest_slate`` loaded by path -- it is a script, not a package module."""
    spec = importlib.util.spec_from_file_location("backtest_slate", _BT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _slate_dates() -> list[str]:
    """Every past run directory that holds both an event list and a sheet."""
    out = []
    for path in sorted((ROOT / "runs").glob("2026-*")):
        date = path.name
        if len(date) != 10:
            continue
        if (path / f"{date}_event_list.json").exists() and (
            path / f"{date}_event_dossiers_stats_sheet.json"
        ).exists():
            out.append(date)
    return out


def _wilson_interval(won: int, decided: int) -> tuple[float, float]:
    """95% Wilson bounds. Rows within a match are correlated, so this is a floor
    on the uncertainty rather than the whole of it -- read it as "not even this
    generous interval separates them", never as a p-value."""
    if decided == 0:
        return (0.0, 1.0)
    z = 1.96
    p = won / decided
    denom = 1 + z * z / decided
    centre = (p + z * z / (2 * decided)) / denom
    spread = z * math.sqrt(p * (1 - p) / decided + z * z / (4 * decided * decided)) / denom
    return (max(0.0, centre - spread), min(1.0, centre + spread))


class _Value(NamedTuple):
    """The fields ``_compute_readiness`` reads off a ProviderValue.

    It was two -- provider and match_id -- until 2026-09-04, when readiness
    started measuring itself on the sample ANALYZE will actually read and so
    began consulting ``scope_values``. That filter needs the competition and
    season an observation belongs to (it cannot pin out a friendly or age out
    last season from a match_id), the date that decides which season is
    current, and the opponent it groups by. Omitting them did not silently
    change the count -- the run died with ``AttributeError: '_Value' object
    has no attribute 'surface'`` -- which is the failure mode to prefer.

    ``surface`` and ``match_level`` are carried as None throughout, which is
    correct rather than lazy: ``_scoped_side`` passes neither ``surface`` nor
    ``match_format`` to ``scope_values``, so neither rule can fire, and a
    field stated by no row at all takes ``_share_within_a_match``'s early
    return instead of its pydantic ``model_copy`` path.
    """

    provider: str
    match_id: str
    competition_id: str | None = None
    season_id: str | None = None
    match_date: str = ""
    opponent: str = ""
    surface: str | None = None
    match_level: str | None = None


class _Observation(NamedTuple):
    """A MetricObservation's three buckets, and nothing else."""

    team_a_l10: list
    team_b_l10: list
    h2h: list


# Providers that serve tennis *today*. Slates before 2026-09-02 also carry
# ``bzzoiro-tennis``, which has answered HTTP 402 since 2026-09-01 and was
# removed from the roster and from PROVIDER_NAMES -- so those dossiers cannot
# even be validated by the current contract, and counting their observations
# would measure a world no run can reproduce. They are dropped, which makes
# this the conservative counterfactual: "what would today's rule, with today's
# providers, have said about this fixture".
_LIVE_TENNIS_PROVIDERS = frozenset(PROVIDERS_BY_SPORT.get("tennis", ()))


def readiness_by_event(date: str) -> dict[str, str]:
    """``{event_id: readiness}`` recomputed from the frozen dossier.

    Read as raw JSON rather than through EventDossierListV1: a frozen artifact
    is a record of what a past run wrote, and a contract that has legitimately
    narrowed since (``bzzoiro-tennis`` left PROVIDER_NAMES) must not make the
    day unreadable. Only the fields the readiness rule actually consults are
    reconstructed -- see ``_Value``, which grew on 2026-09-04.
    """
    path = ROOT / "runs" / date / f"{date}_event_dossiers.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    dossiers = payload if isinstance(payload, list) else payload.get("dossiers", [])
    out: dict[str, str] = {}
    for dossier in dossiers:
        if dossier.get("sport") != "tennis":
            continue
        metrics = {}
        for name, obs in (dossier.get("metrics") or {}).items():
            buckets = []
            for bucket in ("team_a_l10", "team_b_l10", "h2h"):
                buckets.append(
                    [
                        _Value(
                            pv.get("provider", ""),
                            pv.get("match_id", ""),
                            pv.get("competition_id"),
                            pv.get("season_id"),
                            pv.get("match_date") or "",
                            pv.get("opponent") or "",
                        )
                        for pv in (obs.get(bucket) or [])
                        if pv.get("provider") in _LIVE_TENNIS_PROVIDERS
                    ]
                )
            metrics[name] = _Observation(*buckets)
        out[dossier["event_id"]] = _compute_readiness(
            "tennis", metrics, bool(dossier.get("player_metrics"))
        )
    return out


def settle_slate(date: str, module) -> list[dict]:
    """Every settleable tennis sheet row for one slate, tagged with readiness."""
    base = ROOT / "runs" / date
    events = EventListV1.model_validate_json(
        (base / f"{date}_event_list.json").read_text(encoding="utf-8")
    )
    sheet = json.loads(
        (base / f"{date}_event_dossiers_stats_sheet.json").read_text(encoding="utf-8")
    )
    actuals, _gaps = module.fetch_tennis_actuals(events, date, {})
    by_id = {e.event_id: e for e in events.events}
    readiness = readiness_by_event(date)

    out: list[dict] = []
    for row in sheet.get("rows", []):
        if row.get("sport") != "tennis":
            continue
        event = by_id.get(row.get("event_id"))
        if event is None or row.get("event_id") not in actuals:
            continue
        name_a, name_b = module._sides_of(event)
        outcome, actual = settle_row(
            market=row["market"],
            line=row["line"],
            direction=row["direction"],
            actuals=actuals[row["event_id"]],
            team_name=row.get("team_name"),
            home_team=name_a,
            away_team=name_b,
        )
        out.append(
            {
                "date": date,
                "event_id": row["event_id"],
                "market": row["market"],
                "outcome": outcome,
                "actual": actual,
                "p_low": row.get("p_low"),
                "p_central": row.get("p_central"),
                "sample_size": row.get("sample_size"),
                "readiness": readiness.get(row["event_id"], "UNKNOWN"),
            }
        )
    return out


def _rate(records: list[dict]) -> tuple[int, int, float | None]:
    outcomes: list[Outcome] = [r["outcome"] for r in records]
    won = sum(1 for o in outcomes if o == "WON")
    decided = won + sum(1 for o in outcomes if o == "LOST")
    return won, decided, (won / decided if decided else None)


def _report(label: str, records: list[dict]) -> None:
    won, decided, rate = _rate(records)
    if not decided:
        print(f"  {label:34} {len(records):5} rows  nothing settled")
        return
    low, high = _wilson_interval(won, decided)
    claimed = [r["p_low"] for r in records if r["p_low"] is not None]
    claim = sum(claimed) / len(claimed) if claimed else float("nan")
    print(
        f"  {label:34} {decided:5} settled  {won:5} won  "
        f"hit {rate:6.1%}  [{low:.1%}, {high:.1%}]  claimed {claim:.3f}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", action="append", default=[])
    parser.add_argument(
        "--min-p-low",
        type=float,
        default=0.50,
        help="only rows the sheet would put forward (default 0.50, as the "
             "football measurement used); 0 for every row",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    dates = args.date or _slate_dates()
    module = _backtest_module()

    records: list[dict] = []
    for date in dates:
        try:
            rows = settle_slate(date, module)
        except FileNotFoundError:
            continue
        print(f"{date}: {len(rows)} tennis rows against a finished scoreboard")
        records.extend(rows)

    if not records:
        print("nothing to settle", file=sys.stderr)
        return 2

    covered = [r for r in records if r["outcome"] != "NO_DATA"]
    uncovered = len(records) - len(covered)
    print(
        f"\n{len(records)} rows, {len(covered)} settleable, "
        f"{uncovered} uncovered (aces/double faults: ESPN states no serve counts)"
    )

    bar = [r for r in covered if (r["p_low"] or 0) >= args.min_p_low]
    print(f"\nrows at p_low >= {args.min_p_low:.2f}")
    _report("all", bar)
    by_readiness: dict[str, list[dict]] = defaultdict(list)
    for r in bar:
        by_readiness[r["readiness"]].append(r)
    for key in sorted(by_readiness):
        _report(f"readiness={key}", by_readiness[key])

    print("\nsame, restricted to n >= 8 (the CALL clause's own condition)")
    deep = [r for r in bar if (r["sample_size"] or 0) >= 8]
    _report("all n>=8", deep)
    deep_by: dict[str, list[dict]] = defaultdict(list)
    for r in deep:
        deep_by[r["readiness"]].append(r)
    for key in sorted(deep_by):
        _report(f"n>=8 readiness={key}", deep_by[key])

    print("\nby market")
    by_market: dict[str, list[dict]] = defaultdict(list)
    for r in bar:
        by_market[r["market"]].append(r)
    for key in sorted(by_market):
        _report(key, by_market[key])

    if args.json_out:
        args.json_out.write_text(json.dumps(records, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
