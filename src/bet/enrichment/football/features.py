from collections.abc import Sequence
from statistics import mean, median

from bet.enrichment.football.contracts import (
    FootballMetricSample,
    FootballMetricWindow,
    FootballSide,
)


def _normalize_float(val: float) -> float:
    rounded = round(float(val), 6)
    if rounded == -0.0:
        return 0.0
    return rounded

class FootballFeatureBuilder:
    def __init__(self, metrics: list[str]):
        self.metrics = metrics

    def _prepare_samples(self, samples: list[FootballMetricSample]) -> list[FootballMetricSample]:
        # Sort ascending by tie-breaks first, then descending by kickoff (stable sort)
        samples_sorted = sorted(samples, key=lambda s: (s.provider_fixture_id, s.observation_logical_identity))
        sorted_samples = sorted(samples_sorted, key=lambda s: s.kickoff_at, reverse=True)

        # Deduplicate by fixture ID
        seen = set()
        deduped = []
        for s in sorted_samples:
            if s.provider_fixture_id not in seen:
                seen.add(s.provider_fixture_id)
                deduped.append(s)
        return deduped

    def build_windows(
        self,
        home_samples: list[FootballMetricSample],
        away_samples: list[FootballMetricSample],
        target_home_provider_id: str,
        target_away_provider_id: str
    ) -> tuple[FootballMetricWindow, ...]:

        windows = []

        for metric in self.metrics:
            # HOME overall L5, L10
            h_metric_samples = self._prepare_samples([s for s in home_samples if s.metric == metric])
            windows.append(self._create_window(metric, "home_overall_l5", 5, h_metric_samples[:5]))
            windows.append(self._create_window(metric, "home_overall_l10", 10, h_metric_samples[:10]))

            # AWAY overall L5, L10
            a_metric_samples = self._prepare_samples([s for s in away_samples if s.metric == metric])
            windows.append(self._create_window(metric, "away_overall_l5", 5, a_metric_samples[:5]))
            windows.append(self._create_window(metric, "away_overall_l10", 10, a_metric_samples[:10]))

            # HOME H2H L5
            h_h2h = [s for s in h_metric_samples if s.provider_opponent_team_id == target_away_provider_id]
            windows.append(self._create_window(metric, "home_h2h_l5", 5, h_h2h[:5]))

            # AWAY H2H L5
            a_h2h = [s for s in a_metric_samples if s.provider_opponent_team_id == target_home_provider_id]
            windows.append(self._create_window(metric, "away_h2h_l5", 5, a_h2h[:5]))

            # HOME home-only L5
            h_home_only = [s for s in h_metric_samples if s.side == FootballSide.HOME]
            windows.append(self._create_window(metric, "home_home_l5", 5, h_home_only[:5]))

            # AWAY away-only L5
            a_away_only = [s for s in a_metric_samples if s.side == FootballSide.AWAY]
            windows.append(self._create_window(metric, "away_away_l5", 5, a_away_only[:5]))

        return tuple(windows)

    def _create_window(
        self, metric: str, scope: str, requested: int, samples: Sequence[FootballMetricSample]
    ) -> FootballMetricWindow:
        avail = len(samples)
        if avail == 0:
            return FootballMetricWindow(
                metric=metric,
                scope=scope,
                requested_count=requested,
                available_count=0,
                samples=tuple(samples),
                mean=None,
                median=None,
                missing_reason="no_data"
            )

        vals = [s.value for s in samples]
        m_mean = _normalize_float(mean(vals))
        m_med = _normalize_float(median(vals))

        return FootballMetricWindow(
            metric=metric,
            scope=scope,
            requested_count=requested,
            available_count=avail,
            samples=tuple(samples),
            mean=m_mean,
            median=m_med,
            missing_reason=None if avail == requested else "insufficient_samples"
        )
