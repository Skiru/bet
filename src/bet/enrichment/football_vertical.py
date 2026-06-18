from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FootballGoldenVerticalExecutor:
    """Single football execution surface used by legacy stats facades.

    The heavy lifting remains in bet.stats.enrichment to avoid broad churn, but
    football entrypoints now pass through one executor so production callsites do
    not bypass the router/executor contract accidentally.
    """

    async def enrich_fixtures(
        self,
        fixtures,
        db_conn,
        playwright_pool=None,
        max_age_hours: int = 12,
    ):
        from bet.stats import enrichment as stats_enrichment

        return await stats_enrichment._enrich_fixtures_impl(
            fixtures,
            db_conn,
            playwright_pool=playwright_pool,
            max_age_hours=max_age_hours,
        )

    def build_fixture_snapshot(
        self,
        db_conn,
        canonical_fixture_id: int,
        analysis_cutoff_at: str | None = None,
    ):
        from bet.stats import enrichment as stats_enrichment

        return stats_enrichment._build_football_fixture_snapshot_impl(
            db_conn,
            canonical_fixture_id,
            analysis_cutoff_at=analysis_cutoff_at,
        )


_EXECUTOR = FootballGoldenVerticalExecutor()


def get_football_golden_vertical_executor() -> FootballGoldenVerticalExecutor:
    return _EXECUTOR
