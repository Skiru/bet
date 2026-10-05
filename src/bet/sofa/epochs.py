"""Comparability epochs of the coupon rule.

From 2026-10-05 (docs/sofa/history/PLAN_2026-10-05_SETTLE_I_KUPON.md, part 3, K0) the
coupon's confidence comes from the statistics alone: the price no longer
enters `p_central`, the order or the choice of Bet Builders, and is only the
condition for placing the bet (confidence x odds >= 0.90, ladder margin <=
15%). A build is in the `stats_only` epoch when its day is 2026-10-05 or later
AND it was built at or after STATS_ONLY_FROM_UTC - the moment between the last
morning build of 10-05 (08_confidence.json created 2026-10-05T06:13:33Z) and
the stats-only rebuild of that day. Everything before reads exactly as it did.

`build_at` is `timeutil.now()`, which honours SOFA_NOW: an as-of replay of an
older day (prepare_refit) stays under the old rule.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from bet.sofa import timeutil

STATS_ONLY = "stats_only"
OLD = "old"

STATS_ONLY_DATE = "2026-10-05"
# Entered in the commit right before the 10-05 stats-only rebuild (K9):
# after the last morning build (08_confidence.json created
# 2026-10-05T06:13:33Z, WARIANT 06:13:34Z), before the rebuild started.
STATS_ONLY_FROM_UTC = datetime(2026, 10, 5, 7, 15, 0, tzinfo=UTC)


# The installation of plan part 5 (F7): from this build time the measured
# sports (hockey, basketball, volleyball, CS2) print on the one coupon and
# their separate experimental coupons (run_sport_coupon.py) stop. None until
# F7 is installed - until then the separate coupons are the only record of
# those sports, so they are not stopped earlier (K5).
# Installed 2026-10-05 08:30Z, with the 10-05 rebuild that put the first
# hockey legs on the coupon.
SPORTS_ON_COUPON_FROM_UTC: datetime | None = datetime(2026, 10, 5, 8, 30, 0, tzinfo=UTC)


def sports_on_coupon(date: str, build_at: datetime | None = None) -> bool:
    """Do the measured sports print on the coupon for this build (F7)?"""
    if SPORTS_ON_COUPON_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return date >= STATS_ONLY_DATE and at >= SPORTS_ON_COUPON_FROM_UTC


def stats_only(date: str, build_at: datetime | None = None) -> bool:
    """Is a build of `date` at `build_at` (default: now) in the stats-only epoch?"""
    at = build_at if build_at is not None else timeutil.now()
    return date >= STATS_ONLY_DATE and at >= STATS_ONLY_FROM_UTC


def epoch_name(date: str, build_at: datetime | None = None) -> str:
    return STATS_ONLY if stats_only(date, build_at) else OLD


def artifact_epoch(doc: Mapping[str, Any] | None) -> str:
    """The epoch an artifact (or a locked leg's `printed_under`) was built in;
    no key is the old rule."""
    if not doc:
        return OLD
    return str(doc.get("epoch") or OLD)


def sheet_epoch(rows: list[Mapping[str, Any]]) -> str | None:
    """The epoch every row of a 05_sheet.json carries, OLD for rows without
    one, None when the rows disagree (a sheet assembled from two builds)."""
    seen = {str(r.get("epoch") or OLD) for r in rows}
    if not seen:
        return None
    return seen.pop() if len(seen) == 1 else None


# Plan docs/sofa/PLAN_2026-10-05_PRODUCTION_GRADE.md F2.1: "a curve that fails
# stops printing". measure_calibration.py --write-config --before <d> lists the
# curves whose printed confidence measurably missed their realised rate in
# config/sofa_curve_status.json (bet.sofa.curve_status); CONFIDENCE and
# SPORT_CONFIDENCE refuse a leg read off a listed curve with
# CURVE_FAILED_CALIBRATION - but only for a build at or after this moment.
#
# None = disabled: the file may exist and nothing is refused. The operator
# enables it BETWEEN DAYS, never mid-day (a curve refused halfway through a
# day makes the morning and afternoon prints two experiments), by setting it
# to a UTC moment before that day's first build, in its own commit - like
# STATS_ONLY_FROM_UTC. The day it starts is a new epoch for the ledger.
CURVE_STATUS_FROM_UTC: datetime | None = None


def curve_status_enforced(date: str, build_at: datetime | None = None) -> bool:
    """Does a build of `date` at `build_at` (default: now) refuse the curves
    config/sofa_curve_status.json lists? False while CURVE_STATUS_FROM_UTC is
    None."""
    if CURVE_STATUS_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= CURVE_STATUS_FROM_UTC.strftime("%Y-%m-%d")
            and at >= CURVE_STATUS_FROM_UTC)
