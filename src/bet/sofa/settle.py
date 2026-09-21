"""E10 — settlement and backfill (PLAN §A9, §E10).

Sofascore's history reaches back two decades, so any past day can be replayed:
build the sample as it stood *before* kickoff, price it, and settle it against
the real result. That gives calibration at scale before the first bet is placed.

The limit of the method, stated plainly: we have no historical Superbet prices.
Backwards you can measure **probability calibration** (does 85% mean 85%). You
cannot measure **ROI**. Do not report the second from the first.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from bet.sofa.contracts import Direction, GapReason
from bet.sofa.engine import (
    bar_probability,
    calc_p_central_raw,
    calculate_p_low,
    outside_model_resolution,
    p_empirical_raw,
    predictive_sd,
    support_floor_for,
    uses_empirical_frequency,
    uses_poisson_floor,
    winning_boundary,
)
from bet.sofa.metrics import (
    EXTRA_TIME_STATUS_CODES,
    check_identities,
    extract_flat_statistics,
    extract_metric,
)

Outcome = Literal["WIN", "LOSS", "PUSH"]

# The one status code that means "played to a normal end", read off real
# payloads: docs/sofa/evidence/* carries code 100 "Ended" on 130
# events and code 91 "Walkover" on one. Everything else that still calls
# itself `finished` — walkover, retirement, default — ended abnormally and
# its statistics do not describe a completed contest.
#
# The rule is stated as an allow-list on purpose. A deny-list would have to
# enumerate abnormal codes we have never seen, and the one we missed would
# quietly become a settled row.
NORMAL_FINISH_STATUS_CODE = 100


def settle(actual: float, line: float, direction: Direction) -> Outcome:
    """Settle one rung against the realised value.

    An integer line pushes on an exact hit — the stake comes back and neither
    side won. Reading it as a win for one side is how a PUSH becomes fictitious
    edge (T30).
    """
    if actual == line:
        return "PUSH"
    if direction == "OVER":
        return "WIN" if actual > line else "LOSS"
    return "WIN" if actual < line else "LOSS"


def is_completed_event(event: dict[str, Any]) -> bool:
    """Did this event run to a normal, settleable finish?

    Looks only at ``status.type`` / ``status.code`` / ``winnerCode``. The string
    ``"ret"`` appears inside ``"Berrettini"``; searching for it in a name is how
    `simple` blocked every tennis backtest it ever attempted (L31, T32).
    """
    status = event.get("status")
    if not isinstance(status, dict):
        return False
    if str(status.get("type", "")).lower() != "finished":
        return False
    code = status.get("code")
    if code is None:
        # A finished event without a code: accept, since `type == "finished"`
        # is the contract the rest of the pipeline already relies on.
        return True
    if code == NORMAL_FINISH_STATUS_CODE:
        return True
    # Extra time and penalties: admitted so their goals can be recovered from
    # normaltime, and refused metric by metric in extract_metric.
    return bool(code in EXTRA_TIME_STATUS_CODES)


@dataclass(frozen=True)
class SettledRow:
    """One settled forecast — the unit of ground truth."""

    run_date: str
    sofascore_event_id: int
    sport: str
    competition_id: int | None
    market: str
    subject: str
    line: float
    direction: Direction
    sample_size: int
    sample_mean: float
    sample_sd: float
    p_central: float
    p_bar: float
    market_p: float | None
    actual_value: float
    outcome: Outcome
    settled_at: str
    ladder_sigma: float | None = None
    offered_odds: float | None = None
    verdict: str | None = None


def historical_sample(
    events: list[dict[str, Any]],
    *,
    before_utc: datetime,
    entity_id: int,
    sport: str,
    metric: str,
    metrics_by_event: dict[int, dict[str, Any] | None],
    incidents_by_event: dict[int, dict[str, Any] | None],
    sample_n: int,
    excluded_competition_ids: frozenset[int] = frozenset(),
    ground_type: str | None = None,
    best_of: int | None = None,
) -> list[tuple[int, float]]:
    """``(event_id, value)`` for events strictly before ``before_utc``.

    The event id travels with the value so the caller can enforce "one
    historical match, one observation" when pooling two teams' histories (L13).

    T31: this is the backfill's own leak guard. It is deliberately a separate
    implementation from the live one (T12) because it is separate code — a
    backfill that samples the day it is predicting scores perfectly and means
    nothing.
    """
    if before_utc.tzinfo is None:
        raise ValueError("before_utc must be timezone-aware")

    ordered = sorted(events, key=lambda e: e.get("startTimestamp") or 0, reverse=True)

    values: list[tuple[int, float]] = []
    seen: set[int] = set()
    for event in ordered:
        if len(values) >= sample_n:
            break
        if not is_completed_event(event):
            continue

        start_ts = event.get("startTimestamp")
        if not start_ts:
            continue
        if datetime.fromtimestamp(start_ts, UTC) >= before_utc:
            continue

        event_id = event.get("id")
        if event_id is None or event_id in seen:
            continue

        home_id = event.get("homeTeam", {}).get("id")
        away_id = event.get("awayTeam", {}).get("id")
        if home_id != entity_id and away_id != entity_id:
            continue

        if sport == "tennis":
            if ground_type is not None and event.get("groundType") != ground_type:
                continue
            if best_of is not None and event.get("defaultPeriodCount") != best_of:
                continue
        else:
            comp = event.get("tournament", {}).get("uniqueTournament", {}).get("id")
            if isinstance(comp, int) and comp in excluded_competition_ids:
                continue

        stats = metrics_by_event.get(int(event_id))
        incidents = incidents_by_event.get(int(event_id))
        flat = extract_flat_statistics(stats)
        if check_identities(flat, incidents, event, sport) is not None:
            continue

        value = extract_metric(
            metric, sport, flat, incidents, event, is_home=(home_id == entity_id)
        )
        if isinstance(value, GapReason):
            continue

        seen.add(int(event_id))
        values.append((int(event_id), value))

    return values


def line_grid(centre: float, sample_sd: float) -> list[float]:
    """Lines on a half-point ladder around the sample centre.

    A grid centred on our own sample is the only honest one available backwards:
    without historical Superbet ladders there is no market line to price
    against, and a fixed grid would measure a different market in Argentina
    than in England.

    Integer rungs are included deliberately. They are the ones that can PUSH,
    and a calibration set that never contains a push cannot tell you whether
    pushes are being handled (T30, L10).

    ``sample_sd`` widens the ladder so a high-variance market is probed over
    the range it actually occupies rather than over a fixed ±1.
    """
    # Scale the probe by the sample's own spread, not by a fixed ±1: corners
    # live around 10 with sd ~3 and goals around 2.7 with sd ~1.5, so a fixed
    # ladder would probe one market's tail and the other's centre (L15).
    span = max(1.0, sample_sd)
    raw = [centre + factor * span for factor in (-1.0, -0.5, 0.0, 0.5, 1.0)]
    # Snap to the half-point ladder bookmakers actually quote.
    grid = {round(value * 2.0) / 2.0 for value in raw}
    return sorted(line for line in grid if line > 0)


def settle_metric(
    *,
    run_date: str,
    event: dict[str, Any],
    sport: str,
    metric: str,
    actual_value: float,
    sample_values: list[float],
    min_sample: int,
    k_centre: float,
    k_price: float,
    prior: float | None,
    subject: str = "",
) -> list[SettledRow]:
    """Forecast a grid of lines from the pre-kickoff sample and settle each one."""
    n = len(sample_values)
    if n < min_sample:
        return []

    mean = statistics.mean(sample_values)
    if n > 1:
        variance = statistics.variance(sample_values)
        sample_sd = statistics.stdev(sample_values)
    else:
        variance = 0.0
        sample_sd = 0.0

    if prior is not None:
        w_c = n / (n + k_centre)
        centre = w_c * mean + (1.0 - w_c) * prior
    else:
        centre = mean

    # The same estimator policy as run_sheet, from the same place: a backtest
    # that measures a different estimator than the one that ships measures
    # nothing (F30).
    pred_sd = predictive_sd(
        variance, mean, n, apply_poisson_floor=uses_poisson_floor(metric)
    )
    settled_at = datetime.now(UTC).isoformat()
    competition_id = event.get("tournament", {}).get("uniqueTournament", {}).get("id")

    rows: list[SettledRow] = []
    for line in line_grid(centre, sample_sd):
        for direction in ("OVER", "UNDER"):
            boundary = winning_boundary(line, direction)
            p_low = calculate_p_low(centre, sample_sd, n, boundary, direction)
            if direction == "OVER":
                hits = sum(1 for v in sample_values if v > line)
            else:
                hits = sum(1 for v in sample_values if v < line)

            if uses_empirical_frequency(metric):
                p_raw = p_empirical_raw(hits, n)
            else:
                p_raw = calc_p_central_raw(
                    centre, pred_sd, boundary, direction, support_floor_for(metric)
                )

            # F35: the same refusal as SHEET. If the backtest kept scoring the
            # rungs the sheet will no longer produce, it would be measuring a
            # population that never ships — the F30 mistake, repeated.
            if outside_model_resolution(p_raw):
                continue

            p_central = p_raw

            # No historical Superbet price exists, so there is nothing to shrink
            # toward: market_p is NULL backwards, by construction (A9).
            p_bar, _reason = bar_probability(
                p_central=p_central,
                hits=hits,
                n=n,
                p_low_val=p_low,
                market_p=None,
                k_price=k_price,
            )

            rows.append(
                SettledRow(
                    run_date=run_date,
                    sofascore_event_id=int(event["id"]),
                    sport=sport,
                    competition_id=competition_id
                    if isinstance(competition_id, int)
                    else None,
                    market=metric,
                    subject=subject,
                    line=line,
                    direction=direction,
                    sample_size=n,
                    sample_mean=round(mean, 4),
                    sample_sd=round(sample_sd, 4),
                    p_central=round(p_central, 6),
                    p_bar=round(p_bar, 6),
                    market_p=None,
                    actual_value=actual_value,
                    outcome=settle(actual_value, line, direction),
                    settled_at=settled_at,
                )
            )
    return rows


def insert_settled_rows(conn: Any, rows: list[SettledRow]) -> int:
    """Persist settled rows. Idempotent on the row's natural key."""
    inserted = 0
    for row in rows:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO sofa_settled_row (
                run_date, sofascore_event_id, sport, competition_id,
                market, subject, line, direction, sample_size, sample_mean,
                sample_sd, p_central, p_bar, market_p, actual_value, outcome,
                settled_at, ladder_sigma, offered_odds, verdict
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.run_date,
                row.sofascore_event_id,
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
                row.p_bar,
                row.market_p,
                row.actual_value,
                row.outcome,
                row.settled_at,
                row.ladder_sigma,
                row.offered_odds,
                row.verdict,
            ),
        )
        inserted += cursor.rowcount if cursor.rowcount > 0 else 0
    conn.commit()
    return inserted
