"""5-step pipeline orchestrator with resume capability.

Steps:
1. DISCOVER — find fixtures + fetch odds
2. ENRICH — incremental stat fetching
3. ANALYZE — safety scores + market ranking
4. BUILD — coupon construction + shopping list
5. SETTLE — settle previous day's bets
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from bet.config import BettingConfig
from bet.db.connection import get_db
from bet.db.repositories import (
    CouponRepo,
    FixtureRepo,
    PipelineRepo,
    SportRepo,
    StatsRepo,
    TeamRepo,
)
from bet.db.schema import init_db
from bet.pipeline.progress import PipelineProgress

logger = logging.getLogger(__name__)

PIPELINE_STEPS = ["discover", "enrich", "analyze", "build", "settle"]


async def run_pipeline(
    target_date: date,
    config: BettingConfig,
    db_path: str | None = None,
    resume: bool = False,
    skip_settle: bool = False,
) -> dict:
    """Run the 5-step pipeline.

    If resume=True, skip steps already completed for target_date.

    Returns: {"steps_completed": [...], "coupons_built": N, "total_fixtures": M}
    """
    path = db_path or config.db_path
    progress = PipelineProgress(total_steps=len(PIPELINE_STEPS))
    results: dict = {
        "steps_completed": [],
        "coupons_built": 0,
        "total_fixtures": 0,
    }

    # Shared state dict for passing data between steps (e.g., candidates)
    shared_state: dict = {}

    with get_db(path) as conn:
        init_db(conn)
        conn.commit()
        pipeline_repo = PipelineRepo(conn)

        completed = set()
        if resume:
            completed = set(pipeline_repo.get_completed_steps(target_date.isoformat()))
            if completed:
                progress.update(f"Resuming — skipping: {', '.join(completed)}")

        steps_to_run = [
            s for s in PIPELINE_STEPS
            if s not in completed and not (s == "settle" and skip_settle)
        ]

        for step in steps_to_run:
            try:
                pipeline_repo.start_step(target_date.isoformat(), step)
                conn.commit()

                step_stats = await _run_step(
                    step, target_date, config, conn, progress,
                    shared_state=shared_state,
                )

                pipeline_repo.complete_step(
                    target_date.isoformat(), step, step_stats,
                )
                conn.commit()

                results["steps_completed"].append(step)
                if step == "discover":
                    results["total_fixtures"] = step_stats.get("total_fixtures", 0)
                elif step == "build":
                    results["coupons_built"] = step_stats.get("coupons_built", 0)

            except Exception as e:
                logger.exception("Pipeline step %s failed", step)
                pipeline_repo.fail_step(
                    target_date.isoformat(), step, str(e),
                )
                conn.commit()
                progress.error(step, str(e))
                break

        progress.final_summary(results)

    return results


async def _run_step(
    step: str,
    target_date: date,
    config: BettingConfig,
    db_conn,
    progress: PipelineProgress,
    shared_state: dict | None = None,
) -> dict:
    """Execute a single pipeline step."""
    state = shared_state if shared_state is not None else {}
    if step == "discover":
        return await _step_discover(target_date, config, db_conn, progress)
    elif step == "enrich":
        return await _step_enrich(target_date, config, db_conn, progress)
    elif step == "analyze":
        return await _step_analyze(target_date, config, db_conn, progress, state)
    elif step == "build":
        return await _step_build(target_date, config, db_conn, progress, state)
    elif step == "settle":
        return await _step_settle(target_date, config, db_conn, progress)
    else:
        raise ValueError(f"Unknown step: {step}")


async def _step_discover(
    target_date: date,
    config: BettingConfig,
    db_conn,
    progress: PipelineProgress,
) -> dict:
    """STEP 1: Discover fixtures + fetch odds."""
    progress.start_step("discover", "Scanning fixtures and odds")

    from bet.scanner.discovery import discover_fixtures

    sport_counts = await discover_fixtures(
        target_date=target_date,
        sports=config.sports,
        db_conn=db_conn,
    )

    total = sum(sport_counts.values())
    for sport, count in sorted(sport_counts.items()):
        progress.update(f"{sport}: {count} fixtures")

    # Fetch odds (non-critical — catch and log errors)
    try:
        from bet.scanner.odds_fetcher import fetch_odds

        odds_stats = await fetch_odds(
            target_date=target_date,
            sports=config.sports,
            db_conn=db_conn,
        )
        progress.update(f"Odds: {odds_stats.get('matched', 0)} matched")
    except Exception as e:
        logger.warning("Odds fetch failed (non-critical): %s", e)
        progress.update(f"Odds: skipped ({e})")

    stats = {"total_fixtures": total, **sport_counts}
    progress.complete_step("discover", stats)
    return stats


async def _step_enrich(
    target_date: date,
    config: BettingConfig,
    db_conn,
    progress: PipelineProgress,
) -> dict:
    """STEP 2: Enrich fixtures with team stats.

    Prioritizes important fixtures to stay within API rate limits (100 req/day).
    Enriches top 40 fixtures by competition importance, covering all 7 sports.
    """
    progress.start_step("enrich", "Fetching team statistics")

    from bet.stats.enrichment import enrich_fixtures

    fixture_repo = FixtureRepo(db_conn)
    all_fixtures = fixture_repo.get_by_date(target_date.isoformat())

    # Prioritize fixtures: sort by competition importance, ensure sport diversity
    # Each sport gets at most 4 fixtures enriched (16 total = 32 teams max)
    sport_buckets: dict[int, list] = {}
    for fix in all_fixtures:
        sport_buckets.setdefault(fix.sport_id, []).append(fix)

    priority_fixtures = []
    # First pass: 4 per sport
    for sport_id, fixes in sport_buckets.items():
        priority_fixtures.extend(fixes[:4])
    # Cap at 16 total
    priority_fixtures = priority_fixtures[:16]

    progress.update(
        f"Enriching {len(priority_fixtures)}/{len(all_fixtures)} priority fixtures"
    )

    counters = await enrich_fixtures(fixtures=priority_fixtures, db_conn=db_conn)

    progress.complete_step("enrich", counters)
    return counters


async def _step_analyze(
    target_date: date,
    config: BettingConfig,
    db_conn,
    progress: PipelineProgress,
    shared_state: dict,
) -> dict:
    """STEP 3: Compute safety scores and rank candidates."""
    progress.start_step("analyze", "Computing safety scores")

    import statistics as stats_mod

    from bet.db.models import TeamForm
    from bet.stats.market_ranking import SPORT_STAT_KEYS
    from bet.stats.safety_scores import compute_all_markets

    fixture_repo = FixtureRepo(db_conn)
    sport_repo = SportRepo(db_conn)
    team_repo = TeamRepo(db_conn)
    stats_repo = StatsRepo(db_conn)

    fixtures = fixture_repo.get_by_date(target_date.isoformat())
    all_candidates = []

    for fixture in fixtures:
        sport = sport_repo.get_by_name(
            _sport_id_to_name(fixture.sport_id, sport_repo)
        )
        if not sport:
            continue

        home_team = team_repo.get_by_id(fixture.home_team_id)
        away_team = team_repo.get_by_id(fixture.away_team_id)
        if not home_team or not away_team:
            continue

        # Gather form data per stat key
        home_form: dict[str, TeamForm] = {}
        away_form: dict[str, TeamForm] = {}
        h2h_form: dict[str, list[float]] = {}

        for stat_key in SPORT_STAT_KEYS.get(sport.name, []):
            # Home form
            l10 = stats_repo.get_form(home_team.id, stat_key, 10)
            l5 = stats_repo.get_form(home_team.id, stat_key, 5)
            if l10:
                home_form[stat_key] = TeamForm(
                    id=None,
                    team_id=home_team.id,
                    sport_id=sport.id,
                    stat_key=stat_key,
                    l10_values=l10,
                    l5_values=l5,
                    l10_avg=stats_mod.mean(l10) if l10 else None,
                    l5_avg=stats_mod.mean(l5) if l5 else None,
                )

            # Away form
            l10 = stats_repo.get_form(away_team.id, stat_key, 10)
            l5 = stats_repo.get_form(away_team.id, stat_key, 5)
            if l10:
                away_form[stat_key] = TeamForm(
                    id=None,
                    team_id=away_team.id,
                    sport_id=sport.id,
                    stat_key=stat_key,
                    l10_values=l10,
                    l5_values=l5,
                    l10_avg=stats_mod.mean(l10) if l10 else None,
                    l5_avg=stats_mod.mean(l5) if l5 else None,
                )

            # H2H
            h2h_vals = stats_repo.get_h2h_stats(
                home_team.id, away_team.id, stat_key, 10
            )
            if h2h_vals:
                h2h_form[stat_key] = h2h_vals

        # Get competition name
        comp_name = ""
        if fixture.competition_id:
            from bet.db.repositories import CompetitionRepo

            comp_repo = CompetitionRepo(db_conn)
            row = db_conn.execute(
                "SELECT name FROM competitions WHERE id = ?",
                (fixture.competition_id,),
            ).fetchone()
            if row:
                comp_name = row["name"]

        candidates = compute_all_markets(
            fixture=fixture,
            home_form=home_form,
            away_form=away_form,
            h2h_form=h2h_form,
            sport=sport.name,
            home_team=home_team,
            away_team=away_team,
            competition_name=comp_name,
        )

        # Filter by minimum safety score — only real data candidates pass
        candidates = [
            c for c in candidates
            if c.safety_score >= config.min_safety_score and c.safety_score > 0.0
        ]
        all_candidates.extend(candidates)

    # Store candidates in shared state for the BUILD step
    shared_state["candidates"] = all_candidates

    stats = {
        "fixtures_analyzed": len(fixtures),
        "candidates": len(all_candidates),
    }
    progress.complete_step("analyze", stats)
    return stats


async def _step_build(
    target_date: date,
    config: BettingConfig,
    db_conn,
    progress: PipelineProgress,
    shared_state: dict,
) -> dict:
    """STEP 4: Build coupons and write shopping list."""
    progress.start_step("build", "Building coupons")

    from bet.coupon.builder import build_coupons
    from bet.coupon.shopping_list import write_shopping_list

    candidates = shared_state.get("candidates", [])
    coupon_pairs = build_coupons(candidates, config)

    # Persist to DB
    coupon_repo = CouponRepo(db_conn)
    for coupon, bets in coupon_pairs:
        coupon_db_id = coupon_repo.create_coupon(coupon)
        for bet in bets:
            bet.coupon_id = coupon_db_id
            coupon_repo.add_bet(bet)

    # Write shopping list
    output_path = write_shopping_list(
        coupon_pairs, config, total_candidates=len(candidates),
    )

    stats = {
        "coupons_built": len(coupon_pairs),
        "total_legs": sum(len(bets) for _, bets in coupon_pairs),
        "shopping_list": str(output_path),
    }
    progress.complete_step("build", stats)
    return stats


async def _step_settle(
    target_date: date,
    config: BettingConfig,
    db_conn,
    progress: PipelineProgress,
) -> dict:
    """STEP 5: Settle PREVIOUS day's bets."""
    progress.start_step("settle", "Settling previous day")

    from bet.settlement.settler import settle_day

    previous_date = target_date - timedelta(days=1)
    result = await settle_day(previous_date, db_conn)

    progress.complete_step("settle", result)
    return result


def get_pipeline_status(target_date: date, db_conn) -> list[dict]:
    """Query pipeline_runs for the given date. Returns step statuses."""
    pipeline_repo = PipelineRepo(db_conn)
    return pipeline_repo.get_run_status(target_date.isoformat())


def _sport_id_to_name(sport_id: int, sport_repo: SportRepo) -> str:
    """Look up sport name from ID."""
    for sport in sport_repo.get_all():
        if sport.id == sport_id:
            return sport.name
    return ""
