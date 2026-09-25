#!/usr/bin/env python3
"""Measure this model's probability calibration from the cache alone.

`run_backfill.py` does the same job properly — it pulls each league season and
replays it. It also needs Sofascore, and Sofascore is the one thing this
pipeline cannot rely on being reachable. This script needs no network and no
prices: calibration is a question about pairs of (prediction, outcome), and
every pair it needs is already in `sofa.db`.

That distinction is the point. The reason `config/sofa_market_reliability.json`
has been `{}` since the pipeline was written is not that the measurement is
hard, it is that the only path to it went through a provider that has been
403-ing. Every row the sheet produces therefore carries `UNFITTED_CONSTANTS`
and an uncorrected `p_central`, and the coupon inherits the consequence: on
2026-09-18 every one of its rows sat above the devigged market price, median
ratio 1.43, with nothing measured to say whether that is edge or error.

Method, mirroring `run_sheet.py` exactly so that what is measured is what
ships:

  * for each finished match in the cache, rebuild each side's sample from
    matches strictly **before** that match's kickoff — the same chronological
    rule the sampler uses, so no row is scored against its own result;
  * shrink toward the league baseline with the same K_CENTRE;
  * take `predictive_sd` with the same Poisson floor, and
    `calc_p_central_raw` against the same `winning_boundary`;
  * refuse the same rungs `outside_model_resolution` refuses;
  * settle against what actually happened.

`market_p` is NULL on every row: there are no historical Superbet prices
(PLAN §A9). So this supports the calibration curve and K_CENTRE, and it
cannot support K_PRICE or MAX_LADDER_SIGMA, which need a live ladder. Those
stay NOT_FITTED, and `fit_constants.py` already says so.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import sqlite3
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.config import SofaConfig
from bet.sofa.engine import (
    calc_p_central_raw,
    outside_model_resolution,
    predictive_sd,
    support_floor_for,
    uses_poisson_floor,
    winning_boundary,
)
from bet.sofa.metrics import (
    calculate_cards_points,
    extract_flat_statistics,
    stat_is_untracked,
)
from bet.sofa.settle import settle

# Metric base -> Sofascore statistics key. Goals are not here: they come off
# the listing, which covers twenty times more matches than /statistics does.
STAT_KEYS = {
    "corners": "cornerKicks",
    "shots": "totalShotsOnGoal",
    "shots_on_target": "shotsOnGoal",
    "fouls": "fouls",
    "offsides": "offsides",
    # 2026-09-25 coverage audit; see metrics.py. Without these the new
    # metrics would never get a league baseline or a confidence curve.
    "saves": "goalkeeperSaves",
    "throw_ins": "throwIns",
    "goal_kicks": "goalKicks",
    "tackles": "totalTackle",
    "aces": "aces",
    "double_faults": "doubleFaults",
    "games": "gamesWon",
}

SPORT_OF_BASE = {
    "corners": "football",
    "shots": "football",
    "shots_on_target": "football",
    "fouls": "football",
    "offsides": "football",
    "saves": "football",
    "throw_ins": "football",
    "goal_kicks": "football",
    "tackles": "football",
    "cards_points": "football",
    "goals": "football",
    "aces": "tennis",
    "double_faults": "tennis",
    "games": "tennis",
}

# The sheet's own default when nothing is fitted. Calibrating against a
# different value would measure a model that does not ship.
# The pipeline's per-side tennis games market is `games_won_for`, not
# `games_for`. A curve keyed on a name the engine never looks up is a
# correction that silently does nothing, which is worse than no curve at all
# because the artifact then claims to be calibrated.
MARKET_NAME_OVERRIDES = {("games", "for"): "games_won_for"}


def market_name(base: str, suffix: str) -> str:
    return MARKET_NAME_OVERRIDES.get((base, suffix), f"{base}_{suffix}")


# The fallback, used only when nothing has been fitted yet. The shipped value
# is read from config/sofa_engine_constants.json — see k_centre_for.
K_CENTRE = 10.0
SAMPLE_N = 10
MIN_SAMPLE = 8


def k_centre_for(sport: str, constants: dict[str, Any] | None = None) -> float:
    """The K_CENTRE this sport actually ships with.

    This module's docstring promises it mirrors run_sheet "exactly so that what
    is measured is what ships", and until 2026-09-18 it did not: run_sheet read
    the fitted constant while this replayed every row at a hardcoded 10.0. The
    gap became material the moment K was fitted per sport — football ships 25
    and tennis 2 — so the reliability curve was describing a model nobody runs
    (F47, the same family as the two naming breaks this file already records).

    Order matters: the K fit itself recomputes the centre for every K on the
    grid from (sample_mean, sample_size, prior) and never reads the stored
    p_central, so it is unaffected by this. Only the reliability curve is, and
    it is fitted from these rows. Run calibrate -> fit_constants; if K moves,
    run the pair again so the curve describes the new K.
    """
    if constants is None:
        constants = _load_engine_constants()
    entry = constants.get("K_CENTRE")
    if isinstance(entry, dict):
        by_sport = entry.get("by_sport")
        if isinstance(by_sport, dict):
            value = by_sport.get(sport)
            if isinstance(value, int | float) and not isinstance(value, bool):
                return float(value)
        value = entry.get("value")
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    return K_CENTRE


def _load_engine_constants() -> dict[str, Any]:
    path = Path("config/sofa_engine_constants.json")
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


@dataclass(frozen=True)
class Played:
    event_id: int
    timestamp: int
    home_id: int
    away_id: int
    sport: str
    competition_id: int | None
    values: dict[str, tuple[float, float]]


def load_cache(db_path: Path) -> list[Played]:
    conn = sqlite3.connect(str(db_path))
    try:
        identity: dict[int, dict[str, Any]] = {}
        for (events_json,) in conn.execute(
            "SELECT events_json FROM sofa_entity_events"
        ):
            try:
                events = json.loads(events_json)
            except ValueError:
                continue
            if isinstance(events, dict):
                events = events.get("events", [])
            if not isinstance(events, list):
                continue
            for event in events:
                if not isinstance(event, dict):
                    continue
                event_id = event.get("id")
                if not isinstance(event_id, int) or event_id in identity:
                    continue
                identity[event_id] = event

        stats_by_event: dict[int, tuple[str | None, str | None]] = {}
        for event_id, statistics_json, incidents_json in conn.execute(
            "SELECT sofascore_event_id, statistics_json, incidents_json "
            "FROM sofa_event_stats WHERE status_type = 'finished'"
        ):
            stats_by_event[event_id] = (statistics_json, incidents_json)
    finally:
        conn.close()

    played: list[Played] = []
    for event_id, event in identity.items():
        status = event.get("status") or {}
        if status.get("type") != "finished":
            continue
        home = (event.get("homeTeam") or {}).get("id")
        away = (event.get("awayTeam") or {}).get("id")
        started = event.get("startTimestamp")
        if not home or not away or not started:
            continue
        sport = (
            ((event.get("tournament") or {}).get("category") or {}).get("sport") or {}
        ).get("slug")
        if sport not in ("football", "tennis"):
            continue
        unique = ((event.get("tournament") or {}).get("uniqueTournament") or {}).get(
            "id"
        )

        values: dict[str, tuple[float, float]] = {}

        if sport == "football":
            home_goals = (event.get("homeScore") or {}).get("current")
            away_goals = (event.get("awayScore") or {}).get("current")
            if home_goals is not None and away_goals is not None:
                values["goals"] = (float(home_goals), float(away_goals))

        statistics_json, incidents_json = stats_by_event.get(event_id, (None, None))
        if statistics_json:
            try:
                flat = extract_flat_statistics(json.loads(statistics_json))
            except ValueError:
                flat = {}
            all_period = flat.get("ALL", {})
            for base, key in STAT_KEYS.items():
                pair = all_period.get(key)
                # The same placeholder-zero refusal the sheet applies.
                if pair is not None and not stat_is_untracked(key, pair):
                    values[base] = (float(pair[0]), float(pair[1]))
        if incidents_json:
            try:
                points = calculate_cards_points(json.loads(incidents_json))
            except ValueError:
                points = None
            if points is not None and not isinstance(points, str):
                values["cards_points"] = (float(points[0]), float(points[1]))

        if values:
            played.append(
                Played(
                    event_id=event_id,
                    timestamp=int(started),
                    home_id=int(home),
                    away_id=int(away),
                    sport=sport,
                    competition_id=int(unique) if unique else None,
                    values=values,
                )
            )

    played.sort(key=lambda p: p.timestamp)
    return played


def lines_for(centre: float) -> list[float]:
    """A grid of half-lines around the centre, as a bookmaker would post."""
    lowest = max(0, math.floor(centre) - 4)
    return [lowest + 0.5 + step for step in range(9)]


def load_baselines() -> dict[str, Any]:
    path = Path("config/sofa_league_baselines.json")
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def prior_for(
    baselines: dict[str, Any], market: str, competition_id: int | None
) -> float | None:
    entry = baselines.get(market)
    if not isinstance(entry, dict):
        return None
    if competition_id is not None:
        league = entry.get(str(competition_id))
        if isinstance(league, dict) and isinstance(league.get("mean"), int | float):
            return float(league["mean"])
    # Both pool shapes: `{"mean": x, "n": k}` since 2026-09-21, a bare float
    # in every file written before it. Reading only one of them would not
    # error — it would silently return None and recalibrate against a model
    # with no prior at all, which is the worst of the three outcomes.
    overall = entry.get("global")
    if isinstance(overall, dict) and isinstance(overall.get("mean"), int | float):
        return float(overall["mean"])
    if isinstance(overall, int | float) and not isinstance(overall, bool):
        return float(overall)
    return None


@dataclass
class SettledRow:
    event_id: int
    sport: str
    competition_id: int | None
    market: str
    subject: str
    line: float
    direction: str
    sample_size: int
    sample_mean: float
    sample_sd: float
    p_central: float
    actual: float
    outcome: str

    @property
    def won(self) -> bool:
        return self.outcome == "WIN"


def build(played: list[Played], baselines: dict[str, Any]) -> list[SettledRow]:
    # Read once: the constant is per sport and must be the one that ships.
    engine_constants = _load_engine_constants()
    # team -> base -> chronological list of (timestamp, own value, total value)
    history: dict[tuple[int, str], list[tuple[int, float, float]]] = (
        collections.defaultdict(list)
    )
    rows: list[SettledRow] = []

    for match in played:
        for base, (home_value, away_value) in match.values.items():
            total = home_value + away_value
            for team, own, market_suffixes in (
                (match.home_id, home_value, ("for", "total")),
                (match.away_id, away_value, ("for", "total")),
            ):
                del market_suffixes
                past = history[(team, base)]
                if len(past) >= MIN_SAMPLE:
                    rows.extend(
                        _settle_side(
                            match,
                            base,
                            team,
                            own,
                            total,
                            past,
                            baselines,
                            engine_constants,
                        )
                    )

        # Only after settling: a match may never contribute to its own sample.
        for base, (home_value, away_value) in match.values.items():
            total = home_value + away_value
            history[(match.home_id, base)].append(
                (match.timestamp, home_value, total)
            )
            history[(match.away_id, base)].append(
                (match.timestamp, away_value, total)
            )

    return rows


def _settle_side(
    match: Played,
    base: str,
    team: int,
    own_value: float,
    total_value: float,
    past: list[tuple[int, float, float]],
    baselines: dict[str, Any],
    engine_constants: dict[str, Any],
) -> list[SettledRow]:
    out: list[SettledRow] = []
    recent = past[-SAMPLE_N:]

    for suffix, actual, sample in (
        ("for", own_value, [p[1] for p in recent]),
        ("total", total_value, [p[2] for p in recent]),
    ):
        market = market_name(base, suffix)
        n = len(sample)
        if n < MIN_SAMPLE or all(v == 0.0 for v in sample):
            continue
        mean = statistics.mean(sample)
        variance = statistics.variance(sample) if n > 1 else 0.0
        sample_sd = statistics.stdev(sample) if n > 1 else 0.0

        prior = prior_for(baselines, market, match.competition_id)
        if prior is not None:
            k_centre = k_centre_for(match.sport, engine_constants)
            weight = n / (n + k_centre)
            centre = weight * mean + (1.0 - weight) * prior
        else:
            centre = mean

        spread = predictive_sd(
            variance, mean, n, apply_poisson_floor=uses_poisson_floor(market)
        )

        for line in lines_for(centre):
            for direction in ("OVER", "UNDER"):
                boundary = winning_boundary(line, direction)
                p_raw = calc_p_central_raw(
                    centre, spread, boundary, direction, support_floor_for(market)
                )
                if outside_model_resolution(p_raw):
                    continue
                # settle.py owns this vocabulary. Writing "WON"/"LOST" here
                # produced 1.5M rows that fit_constants.py filters out with
                # `outcome IN ('WIN','LOSS')` — it read zero, wrote an empty
                # reliability file over a measured one, and reported success.
                # A half-line cannot PUSH, but the grid is built from a centre
                # and must not assume that.
                outcome = settle(actual, line, direction)
                if outcome == "PUSH":
                    continue
                out.append(
                    SettledRow(
                        event_id=match.event_id,
                        sport=match.sport,
                        competition_id=match.competition_id,
                        market=market,
                        subject=str(team) if suffix == "for" else "",
                        line=line,
                        direction=direction,
                        sample_size=n,
                        sample_mean=round(mean, 4),
                        sample_sd=round(sample_sd, 4),
                        p_central=round(p_raw, 6),
                        actual=actual,
                        outcome=outcome,
                    )
                )
    return out


def reliability_curve(rows: list[SettledRow]) -> dict[str, Any]:
    """Per market, per probability bucket: what we said against what happened.

    The correction the engine consumes is `predicted - realised`, floored at
    zero. The engine may only ever *lower* p, so a market that turns out to be
    underconfident is left alone rather than being handed a discount.
    """
    buckets: dict[str, dict[str, list[SettledRow]]] = collections.defaultdict(
        lambda: collections.defaultdict(list)
    )
    for row in rows:
        index = min(9, int(row.p_central * 10))
        key = f"{index / 10.0:.1f}-{(index + 1) / 10.0:.1f}"
        buckets[row.market][key].append(row)

    pooled: dict[str, list[SettledRow]] = collections.defaultdict(list)
    for row in rows:
        index = min(9, int(row.p_central * 10))
        pooled[f"{index / 10.0:.1f}-{(index + 1) / 10.0:.1f}"].append(row)

    out: dict[str, Any] = {
        "_doc": (
            "Measured by scripts/sofa/calibrate_from_cache.py from finished "
            "matches already in sofa.db, each scored against a sample built "
            "strictly before its own kickoff. `correction` is subtracted from "
            "p_central by the engine and is clamped to >= 0 there and here, so "
            "this file can only ever raise the bar. A bucket below "
            "`_min_rows` is written with correction 0.0 and its count, never "
            "dropped - an absent bucket and a measured-zero bucket must not "
            "look alike."
        ),
        "_min_rows": 150,
        # What a market with too few rows of its own falls back to. The
        # overconfidence being corrected is a property of the estimator — a
        # normal approximation fitted to ten observations — far more than of
        # any one market, so the pooled curve is a better estimate for a thin
        # market than pretending the correction is zero. Measured across every
        # market at once, which is why it is worth having.
        "_pooled": {
            bucket: {
                "rows": len(bucket_rows),
                "predicted": round(
                    statistics.mean(r.p_central for r in bucket_rows), 4
                ),
                "realised": round(
                    sum(1 for r in bucket_rows if r.won) / len(bucket_rows), 4
                ),
                "correction": round(
                    max(
                        0.0,
                        statistics.mean(r.p_central for r in bucket_rows)
                        - sum(1 for r in bucket_rows if r.won) / len(bucket_rows),
                    ),
                    4,
                ),
                "status": "MEASURED" if len(bucket_rows) >= 150 else "TOO_FEW_ROWS",
            }
            for bucket, bucket_rows in sorted(pooled.items())
        },
    }
    for market, by_bucket in sorted(buckets.items()):
        entry: dict[str, Any] = {}
        for bucket, bucket_rows in sorted(by_bucket.items()):
            predicted = statistics.mean(r.p_central for r in bucket_rows)
            realised = sum(1 for r in bucket_rows if r.won) / len(bucket_rows)
            enough = len(bucket_rows) >= 150
            entry[bucket] = {
                "rows": len(bucket_rows),
                "predicted": round(predicted, 4),
                "realised": round(realised, 4),
                "correction": (
                    round(max(0.0, predicted - realised), 4) if enough else 0.0
                ),
                "status": "MEASURED" if enough else "TOO_FEW_ROWS",
            }
        out[market] = entry
    return out


def write_settled(rows: list[SettledRow], db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    written = 0
    try:
        for row in rows:
            conn.execute(
                "INSERT OR REPLACE INTO sofa_settled_row "
                "(run_date, sofascore_event_id, sport, competition_id, market, "
                " subject, line, direction, sample_size, sample_mean, "
                " sample_sd, p_central, p_bar, market_p, actual_value, "
                " outcome, settled_at, ladder_sigma) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "cache-calibration",
                    row.event_id,
                    row.sport,
                    row.competition_id,
                    row.market,
                    row.subject,
                    row.line,
                    row.direction,
                    row.sample_size,
                    row.sample_mean,
                    row.sample_sd,
                    row.p_central,
                    row.p_central,
                    None,
                    row.actual,
                    row.outcome,
                    datetime.now(UTC).isoformat(),
                    None,
                ),
            )
            written += 1
        conn.commit()
    finally:
        conn.close()
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=None)
    parser.add_argument(
        "--out",
        default=None,
        help=(
            "optional path for a raw (ungated) curve, for inspection only. "
            "The curve the engine reads is written by fit_constants.py from "
            "the rows this script inserts."
        ),
    )
    args = parser.parse_args()

    config = SofaConfig.from_env()
    db_path = Path(args.db_path or config.db_path)

    played = load_cache(db_path)
    baselines = load_baselines()
    rows = build(played, baselines)

    curve = reliability_curve(rows)
    if args.out:
        # Off by default. `fit_constants.py` owns
        # config/sofa_market_reliability.json and applies a confidence-interval
        # gate this script does not; two writers on one file meant whichever
        # ran last won, and the first time that happened an empty file
        # overwrote a measured one and reported success.
        Path(args.out).write_text(
            json.dumps(curve, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    written = write_settled(rows, db_path)

    measured = sum(
        1
        for market, entry in curve.items()
        if not market.startswith("_")
        for bucket in entry.values()
        if bucket["status"] == "MEASURED"
    )
    overall_predicted = (
        statistics.mean(r.p_central for r in rows) if rows else 0.0
    )
    overall_realised = (
        sum(1 for r in rows if r.won) / len(rows) if rows else 0.0
    )
    summary = {
        "stage": "CALIBRATE_FROM_CACHE",
        "verdict": "OK" if rows else "PARTIAL",
        "metrics": {
            "matches_replayed": len(played),
            "settled_rows": len(rows),
            "markets": len([m for m in curve if not m.startswith("_")]),
            "measured_buckets": measured,
            "overall_predicted": round(overall_predicted, 4),
            "overall_realised": round(overall_realised, 4),
            "overall_overconfidence": round(
                overall_predicted - overall_realised, 4
            ),
            "rows_written_to_db": written,
            "next_step": "python -m scripts.sofa.fit_constants",
        },
        "output_path": args.out,
    }
    print(f"SOFA_SUMMARY: {json.dumps(summary)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
