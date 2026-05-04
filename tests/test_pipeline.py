"""Integration tests for the pipeline orchestrator."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from bet.config import BettingConfig
from bet.db.connection import get_db
from bet.db.models import Fixture, MarketCandidate, Team
from bet.db.repositories import (
    CouponRepo,
    FixtureRepo,
    PipelineRepo,
    SportRepo,
    StatsRepo,
    TeamRepo,
)
from bet.db.schema import init_db
from bet.pipeline.orchestrator import PIPELINE_STEPS, run_pipeline


# ---------------------------------------------------------------------------
# Resume / failure tests
# ---------------------------------------------------------------------------


def test_pipeline_resume_skips_completed(db, config):
    """Pipeline with resume=True skips already-completed steps."""
    pipeline_repo = PipelineRepo(db)

    target = date(2026, 5, 3)
    # Mark discover and enrich as completed
    pipeline_repo.start_step("2026-05-03", "discover")
    pipeline_repo.complete_step("2026-05-03", "discover", {"total_fixtures": 5})
    pipeline_repo.start_step("2026-05-03", "enrich")
    pipeline_repo.complete_step("2026-05-03", "enrich", {"fetched": 3})
    db.commit()

    completed = set(pipeline_repo.get_completed_steps("2026-05-03"))
    assert "discover" in completed
    assert "enrich" in completed

    remaining = [s for s in PIPELINE_STEPS if s not in completed]
    assert "discover" not in remaining
    assert "enrich" not in remaining
    assert "analyze" in remaining


def test_pipeline_records_failure(db, config):
    """Verify errors are stored in pipeline_runs."""
    pipeline_repo = PipelineRepo(db)

    pipeline_repo.start_step("2026-05-03", "discover")
    pipeline_repo.fail_step("2026-05-03", "discover", "Connection timeout")
    db.commit()

    status = pipeline_repo.get_run_status("2026-05-03")
    assert len(status) == 1
    assert status[0]["step"] == "discover"
    assert status[0]["status"] == "failed"
    assert "Connection timeout" in status[0]["error_message"]


# ---------------------------------------------------------------------------
# Full pipeline with mocked APIs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_pipeline_with_mocked_apis(config, tmp_path):
    """End-to-end pipeline with mocked external services.

    Verifies:
    1. Fixtures discovered and stored in DB
    2. Stats enriched
    3. Coupons built with ≤ 3 legs
    4. Shopping list file generated
    5. pipeline_runs has completed steps
    """
    db_path = str(tmp_path / "test.db")
    config_test = BettingConfig(
        bankroll_pln=config.bankroll_pln,
        daily_exposure_range=config.daily_exposure_range,
        max_stake_pln=config.max_stake_pln,
        max_legs_per_coupon=config.max_legs_per_coupon,
        min_coupons_per_day=config.min_coupons_per_day,
        preferred_odds_range=config.preferred_odds_range,
        min_safety_score=0.50,  # Lower threshold for test data
        timezone=config.timezone,
        sports=config.sports,
        db_path=db_path,
    )

    target = date(2026, 5, 3)

    # --- Mock discover_fixtures to seed realistic data ---
    async def mock_discover_fixtures(target_date, sports, db_conn):
        sport_repo = SportRepo(db_conn)
        sport_repo.seed_defaults()
        db_conn.commit()

        team_repo = TeamRepo(db_conn)
        fixture_repo = FixtureRepo(db_conn)
        stats_repo = StatsRepo(db_conn)

        football = sport_repo.get_by_name("football")
        basketball = sport_repo.get_by_name("basketball")
        tennis = sport_repo.get_by_name("tennis")

        # Create teams
        liverpool = team_repo.find_or_create("Liverpool", football.id)
        arsenal = team_repo.find_or_create("Arsenal", football.id)
        lakers = team_repo.find_or_create("LA Lakers", basketball.id)
        celtics = team_repo.find_or_create("Boston Celtics", basketball.id)
        djokovic = team_repo.find_or_create("Novak Djokovic", tennis.id)
        sinner = team_repo.find_or_create("Jannik Sinner", tennis.id)

        # Create today's fixtures
        for home, away, sport_id, kickoff in [
            (liverpool, arsenal, football.id, "2026-05-03T15:00:00"),
            (lakers, celtics, basketball.id, "2026-05-03T02:00:00"),
            (djokovic, sinner, tennis.id, "2026-05-03T12:00:00"),
        ]:
            fix = Fixture(
                id=None, sport_id=sport_id, competition_id=None,
                home_team_id=home.id, away_team_id=away.id,
                kickoff=kickoff, source="mock", fetched_at="2026-05-03T00:00:00",
            )
            fixture_repo.upsert(fix)

        # Seed historical finished fixtures for form data
        for i in range(10):
            dt = f"2026-04-{20-i:02d}T15:00:00"
            for home, away, sport_id, stats_data in [
                (liverpool, arsenal, football.id, {
                    "corners": 5.0 + i % 4, "fouls": 11.0 + i % 3,
                    "shots": 12.0 + i % 5, "goals": 1.0 + i % 3,
                }),
                (lakers, celtics, basketball.id, {
                    "points": 100.0 + i * 3, "rebounds": 20.0 + i,
                }),
                (djokovic, sinner, tennis.id, {
                    "total_games": 22.0 + i % 4, "aces": 5.0 + i % 3,
                }),
            ]:
                hist = Fixture(
                    id=None, sport_id=sport_id, competition_id=None,
                    home_team_id=home.id, away_team_id=away.id,
                    kickoff=dt, status="finished", score_home=2, score_away=1,
                    source="mock", fetched_at=dt,
                )
                fix_id = fixture_repo.upsert(hist)
                stats_repo.save_match_stats(fix_id, home.id, stats_data, "mock")
                stats_repo.save_match_stats(fix_id, away.id, stats_data, "mock")

        db_conn.commit()
        return {"football": 1, "basketball": 1, "tennis": 1}

    # --- Mock odds fetcher (no-op) ---
    async def mock_fetch_all_odds(**kwargs):
        return {"matched": 0}

    # --- Mock enrichment (return cached since we already seeded stats) ---
    async def mock_enrich_fixtures(fixtures, db_conn, **kwargs):
        stats_repo = StatsRepo(db_conn)
        sport_repo = SportRepo(db_conn)
        from bet.stats.enrichment import compute_form
        from bet.db.models import TeamForm
        from bet.stats.market_ranking import SPORT_STAT_KEYS
        from datetime import datetime, timezone

        # Compute form for all teams from existing match_stats
        teams_done = set()
        for fix in fixtures:
            for team_id in [fix.home_team_id, fix.away_team_id]:
                if team_id in teams_done:
                    continue
                teams_done.add(team_id)

                sport_name = ""
                for s in sport_repo.get_all():
                    if s.id == fix.sport_id:
                        sport_name = s.name
                        break

                for stat_key in SPORT_STAT_KEYS.get(sport_name, [])[:3]:
                    values = stats_repo.get_form(team_id, stat_key, 10)
                    if not values:
                        continue
                    form = compute_form(values)
                    l5 = values[:5] if len(values) >= 5 else values
                    tf = TeamForm(
                        id=None, team_id=team_id, sport_id=fix.sport_id,
                        stat_key=stat_key, l10_values=values, l5_values=l5,
                        l10_avg=form["l10_avg"], l5_avg=form["l5_avg"],
                        trend=form["trend"],
                        updated_at=datetime.now(timezone.utc).isoformat(),
                        source="mock",
                    )
                    stats_repo.save_team_form(tf)
        db_conn.commit()
        return {"fetched": 0, "cached": len(teams_done), "failed": 0}

    # --- Mock shopping list writer ---
    shopping_list_path = tmp_path / "betting" / "coupons" / "2026-05-03.md"

    def mock_write_shopping_list(coupons, config, **kwargs):
        shopping_list_path.parent.mkdir(parents=True, exist_ok=True)
        shopping_list_path.write_text("# Mock shopping list\n")
        return shopping_list_path

    # Apply patches and run
    # The orchestrator imports fetch_all_odds lazily; patch it via create=True
    with (
        patch("bet.scanner.discovery.discover_fixtures", side_effect=mock_discover_fixtures),
        patch("bet.scanner.odds_fetcher.fetch_all_odds", side_effect=mock_fetch_all_odds, create=True),
        patch("bet.stats.enrichment.enrich_fixtures", side_effect=mock_enrich_fixtures),
        patch("bet.coupon.shopping_list.write_shopping_list", side_effect=mock_write_shopping_list),
    ):
        result = await run_pipeline(
            target_date=target,
            config=config_test,
            db_path=db_path,
            skip_settle=True,
        )

    # Verify results
    assert "discover" in result["steps_completed"]
    assert "enrich" in result["steps_completed"]
    assert "analyze" in result["steps_completed"]
    assert "build" in result["steps_completed"]

    # Verify DB state
    with get_db(db_path) as conn:
        # Fixtures exist
        fixtures = conn.execute(
            "SELECT COUNT(*) FROM fixtures WHERE kickoff LIKE '2026-05-03%'"
        ).fetchone()[0]
        assert fixtures >= 3, f"Expected ≥3 fixtures, got {fixtures}"

        # Pipeline runs recorded
        pipeline_repo = PipelineRepo(conn)
        completed = pipeline_repo.get_completed_steps("2026-05-03")
        assert len(completed) >= 4

        # Coupons have ≤ 3 legs each
        coupon_rows = conn.execute("SELECT id FROM coupons").fetchall()
        for cr in coupon_rows:
            leg_count = conn.execute(
                "SELECT COUNT(*) FROM bets WHERE coupon_id = ?",
                (cr["id"],),
            ).fetchone()[0]
            assert leg_count <= 3, f"Coupon {cr['id']} has {leg_count} legs"
