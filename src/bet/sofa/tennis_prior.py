"""A tennis shrink target by gender, tier and surface, fitted from the cache.

Tennis shrinks toward the price ladder only where one can be fitted
(K_TENNIS_LADDER_CENTRE) - on the 2026-09-25 sheet that was 132 of 11,360
rows. Every other tennis row fell through to the football path, which looks
up a baseline keyed on the competition id. For tennis that id is one week of
one event, so no entry ever existed and the row shrank toward a global pool -
men and women, ITF and ATP together (`sets_total` n=101, `aces_for` 2.96 for
everyone).

The cache already holds the quantity: its player listings carry 131,680
finished singles matches with set scores, category and surface, and serve
statistics sit in `sofa_event_stats` where the cache has them. Every value goes
through `extract_metric`, so the prior is the same quantity the sample
measures.

Keyed on gender x tier x surface family. Gender because a women's match is
not a men's match on aces; tier is `tennis_rating.tier_group` (ITF / CH /
TOUR), surface is `tennis_rating.surface_family`. Only completed best-of-three
singles enter: a retirement truncates every count, a best-of-five is a
different quantity, and doubles is a different sport. Only the metrics in
TIER_PRIOR_METRICS use it.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from bet.sofa.contracts import GapReason
from bet.sofa.metrics import (
    TENNIS_METRICS,
    extract_flat_statistics,
    extract_metric,
    infer_best_of,
)
from bet.sofa.tennis_rating import surface_family, tier_group

# The same evidence bar a league baseline is held to
# (fit_constants.MIN_BASELINE_OBSERVATIONS); a test pins the two together.
MIN_TIER_OBSERVATIONS = 30

# Only the metrics where it was MEASURED to beat what the sheet does today.
# Fit before 2026-09-01, scored on the matches from it, against the global
# pool production shrinks these toward (config/sofa_league_baselines.json):
#
#     metric                n     MAE tier   MAE global (production)
#     aces_for           6,932     1.952      2.353
#     aces_total         3,466     3.023      3.833
#     double_faults_for  6,932     2.014      2.059
#     double_faults_total 3,466    3.107      3.217
#     games_total        5,212     5.223      5.294
#     sets_total         5,212     0.411      0.415
#
# Left out on evidence: games_won_for LOSES (3.708 vs 3.633) - it is bimodal,
# the winner's count at twelve and up, so a level mean fits neither mode.
# Left out for want of it: every metric production has NO prior for (per-set
# games, per-set serve counts, tiebreaks, serve points). There the question is
# "shrunk centre vs the raw sample", which was not measured, and the 2026-09-25
# rerun showed what an unmeasured prior costs - games_won_set2_for moved by a
# median 9 pp (max 31 pp) on no measured gain (MAE 1.8113 vs 1.8113).
TIER_PRIOR_METRICS = frozenset(
    {
        "aces_for",
        "aces_total",
        "double_faults_for",
        "double_faults_total",
        "games_total",
        "sets_total",
    }
)

TierBaselines = dict[str, dict[str, dict[str, float | int]]]


def gender_of(category_name: str) -> str:
    """'W' for a women's event, 'M' otherwise, from the Sofascore category."""
    name = category_name.strip()
    if "Women" in name or name.startswith("WTA") or name == "Billie Jean King Cup":
        return "W"
    return "M"


def tier_key(category_name: str | None, ground_type: str | None) -> str | None:
    """`tennis:<gender>:<tier>:<surface>`, or None without a category."""
    if not category_name:
        return None
    return (
        f"tennis:{gender_of(category_name)}:{tier_group(category_name)}:"
        f"{surface_family(ground_type)}"
    )


def _is_countable(event: Mapping[str, Any]) -> bool:
    home, away = event.get("homeTeam") or {}, event.get("awayTeam") or {}
    if home.get("type") != 1 or away.get("type") != 1:
        return False  # doubles
    status = event.get("status") or {}
    if status.get("type") != "finished" or status.get("description") != "Ended":
        return False
    return infer_best_of(dict(event)) == 3


def fit_tier_baselines(
    events: Iterable[Mapping[str, Any]],
    statistics_for: Callable[[int], dict[str, Any] | None],
    metrics: Iterable[str] | None = None,
) -> TierBaselines:
    """Per metric, per tier key: the mean realised value and its n.

    `events` may repeat a match (it sits in both players' listings); each is
    counted once. A `_for` metric contributes both players' values - two
    observations of "a player's count at this level" - and a `_total` one.
    """
    wanted = [
        m
        for m in (list(metrics) if metrics is not None else sorted(TENNIS_METRICS))
        if m in TIER_PRIOR_METRICS
    ]
    values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    seen: set[int] = set()
    for event in events:
        event_id = event.get("id")
        if not isinstance(event_id, int) or event_id in seen:
            continue
        tournament = event.get("tournament") or {}
        category = tournament.get("category") or {}
        if (category.get("sport") or {}).get("slug") != "tennis":
            continue
        if not _is_countable(event):
            continue
        key = tier_key(str(category.get("name") or ""), event.get("groundType"))
        if key is None:
            continue
        seen.add(event_id)
        flat = extract_flat_statistics(statistics_for(event_id))
        listing = dict(event)
        for metric in wanted:
            sides = (True,) if metric.endswith("_total") else (True, False)
            for is_home in sides:
                v = extract_metric(metric, "tennis", flat, None, listing, is_home)
                if isinstance(v, GapReason):
                    continue
                values[metric][key].append(float(v))

    out: TierBaselines = {}
    for metric in sorted(values):
        entry = {
            key: {"mean": round(statistics.mean(vs), 4), "n": len(vs)}
            for key, vs in sorted(values[metric].items())
            if len(vs) >= MIN_TIER_OBSERVATIONS
        }
        if entry:
            out[metric] = entry
    return out


def tier_prior(
    tier_baselines: Mapping[str, Any],
    metric: str,
    category_name: str | None,
    ground_type: str | None,
) -> tuple[float, str] | None:
    """The fitted mean for this fixture's gender x tier x surface, with a note."""
    key = tier_key(category_name, ground_type)
    if key is None or metric not in TIER_PRIOR_METRICS:
        return None
    entry = (tier_baselines.get(metric) or {}).get(key)
    if not isinstance(entry, Mapping) or not isinstance(entry.get("mean"), int | float):
        return None
    mean, n = float(entry["mean"]), entry.get("n")
    return mean, (
        f"PRIOR_FROM_TENNIS_TIER: {key} mean {mean:.4g} over {n} observations "
        "(no ladder; tier baseline fitted from the cache)"
    )
