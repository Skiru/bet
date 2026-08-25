"""ANALYZE: STATS_SHEET_V1 hit-rate rows over STANDARD_MARKET_LINES.

See docs/PIPELINE_SIMPLIFICATION_PLAN.md section 2 (Krok 2).
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone

from bet.stats.market_ranking import STANDARD_MARKET_LINES

from bet.simple_stats.providers import _normalize_team_name, _team_matches

from bet.simple_stats.contracts import (
    PERCENTAGE_METRICS,
    EventDossierListV1,
    EventDossierV1,
    ProviderValue,
    StatsSheetRow,
    StatsSheetV1,
)

# STANDARD_MARKET_LINES' "stat" field uses the pre-existing (non-"_total")
# taxonomy; MetricObservation keys use our canonical, always-combined-total
# names (section 5). Only is_combined=True markets are analyzed here: a
# "Team Corners" (is_combined=False) market would need one side's value in
# isolation, which this pipeline does not track separately from the
# match-total metrics ENRICH already combines.
_MARKET_STAT_TO_CANONICAL = {
    "corners": "corners_total",
    "yellow_cards": "cards_total",
    "fouls": "fouls_total",
    "shots_on_target": "shots_on_target_total",
    "shots": "shots_total",
    "goals": "goals_total",
    "total_games": "total_games",
    "aces": "aces_total",
    "sets_won": "total_sets",
    "double_faults": "double_faults_total",
}

_CONFIDENCE_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_hit_rate(values: list[float], line: float, direction: str) -> tuple[int, int, int]:
    """Count how many values are over/under the line, tracking pushes.

    Extracted verbatim from scripts/compute_safety_scores.py:357-380 (a pure
    function with no other repo coupling) rather than imported: scripts/ has
    no __init__.py and is not an importable package from src/bet/.

    Args:
        values: list of stat values
        line: the betting line (e.g., 9.5)
        direction: "OVER" or "UNDER"

    Returns: (hits, total, pushes)
        pushes = values exactly on the line (relevant for whole-number lines)
    """
    if not values:
        return 0, 0, 0

    hits = 0
    pushes = 0
    for v in values:
        if v == line:
            pushes += 1
        elif direction == "OVER" and v > line:
            hits += 1
        elif direction == "UNDER" and v < line:
            hits += 1

    return hits, len(values), pushes


def _all_values(obs) -> list[ProviderValue]:
    """Every observation for one metric, each historical match counted once.

    The three buckets overlap by construction. A league fixture the two sides
    already played this season is in team_a's last-10 *and* team_b's last-10
    *and* h2h, so before deduplication one match contributed three values to
    sample_size, hit_rate, mean and median -- and sample_size is exactly what
    _confidence reads to award HIGH (>=8) or LOW (<5). A 4-match sample read
    as 12 is not a rounding error, it is a confidence tier bought with
    duplicates.

    The key is (provider, match_id), not match_id: two providers reporting the
    same match is the corroboration that _cross_provider_agreement exists to
    check, and must survive. Observations with no match_id are all kept, since
    without an id there is nothing to prove they are the same match.
    """
    seen: set[tuple[str, str]] = set()
    unique: list[ProviderValue] = []
    for pv in (*obs.team_a_l10, *obs.team_b_l10, *obs.h2h):
        if not pv.match_id:
            unique.append(pv)
            continue
        key = (pv.provider, pv.match_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(pv)
    return unique


def _cross_provider_agreement(metric: str, observations: list[ProviderValue]) -> str:
    """Classify whether providers agree on the same historical match.

    Providers spell opponents differently ("Ulsan Hyundai FC" vs "Ulsan HD",
    "Real Betis" vs "Betis") and stamp dates in different formats, so
    observations are bucketed by calendar day and then clustered within the day
    by fuzzy opponent match. Keying on the raw opponent string instead made
    every cross-provider pair look like SINGLE_SOURCE, which silently disabled
    the agreement check this pipeline exists to surface.

    Disagreeing values are never averaged away: they drive the AGREE/DISAGREE
    verdict and both stay in the dossier.
    """
    by_day: dict[str, list[ProviderValue]] = {}
    for pv in observations:
        by_day.setdefault((pv.match_date or "")[:10], []).append(pv)

    threshold = 5.0 if metric in PERCENTAGE_METRICS else 1.0
    saw_single = False
    saw_multi = False
    for day, day_observations in by_day.items():
        if not day:
            # No usable date: cannot tell which match this belongs to, so it
            # cannot corroborate or contradict anything.
            saw_single = True
            continue
        for cluster in _cluster_by_opponent(day_observations):
            providers = {pv.provider for pv in cluster}
            if len(providers) < 2:
                saw_single = True
                continue
            saw_multi = True
            values = [pv.value for pv in cluster]
            if max(values) - min(values) > threshold:
                return "DISAGREE"

    if saw_multi:
        return "AGREE"
    if saw_single:
        return "SINGLE_SOURCE"
    return "NOT_APPLICABLE"


def _cluster_by_opponent(observations: list[ProviderValue]) -> list[list[ProviderValue]]:
    """Greedily group same-day observations whose opponent names refer to the
    same team, using the provider-abbreviation-tolerant matcher from
    providers.py."""
    clusters: list[list[ProviderValue]] = []
    for pv in observations:
        name = _normalize_team_name(pv.opponent)
        for cluster in clusters:
            if _team_matches(name, _normalize_team_name(cluster[0].opponent)):
                cluster.append(pv)
                break
        else:
            clusters.append([pv])
    return clusters


def _confidence(agreement: str, sample_size: int) -> str:
    """Explicit 1->2->3 evaluation order (section 2): DISAGREE or a thin
    sample is LOW regardless of anything else; AGREE/SINGLE_SOURCE/
    NOT_APPLICABLE all get the same treatment past that point, since none of
    them is itself a quality problem."""
    if agreement == "DISAGREE" or sample_size < 5:
        return "LOW"
    if sample_size >= 8:
        return "HIGH"
    return "MEDIUM"


def analyze_dossier(dossier: EventDossierV1) -> list[StatsSheetRow]:
    """STATS_SHEET_V1 rows for one event. BLOCKED dossiers never enter
    ANALYZE (section 2)."""
    if dossier.readiness == "BLOCKED":
        return []

    rows: list[StatsSheetRow] = []
    for market_def in STANDARD_MARKET_LINES.get(dossier.sport, []):
        if not market_def.get("is_combined", False):
            continue
        canonical = _MARKET_STAT_TO_CANONICAL.get(market_def["stat"])
        if canonical is None:
            continue
        obs = dossier.metrics.get(canonical)
        if obs is None:
            continue
        observations = _all_values(obs)
        values = [pv.value for pv in observations]
        if not values:
            continue

        sources = sorted({pv.provider for pv in observations})
        agreement = _cross_provider_agreement(canonical, observations)

        for line in market_def["lines"]:
            for direction in ("OVER", "UNDER"):
                hits, sample_size, _pushes = compute_hit_rate(values, line, direction)
                if sample_size == 0:
                    continue
                rows.append(
                    StatsSheetRow(
                        event_id=dossier.event_id,
                        sport=dossier.sport,
                        market=canonical,
                        line=float(line),
                        direction=direction,
                        hits=hits,
                        sample_size=sample_size,
                        hit_rate=hits / sample_size,
                        mean=statistics.fmean(values),
                        median=statistics.median(values),
                        sources=sources,
                        cross_provider_agreement=agreement,
                        confidence=_confidence(agreement, sample_size),
                        data_quality=dossier.readiness,
                    )
                )
    return rows


def analyze_dossiers(dossier_list: EventDossierListV1) -> StatsSheetV1:
    rows: list[StatsSheetRow] = []
    for dossier in dossier_list.dossiers:
        rows.extend(analyze_dossier(dossier))
    rows.sort(key=lambda r: (_CONFIDENCE_ORDER[r.confidence], -r.hit_rate))
    return StatsSheetV1(
        run_id=dossier_list.run_id,
        date=dossier_list.date,
        generated_at=_now_iso(),
        rows=rows,
    )
