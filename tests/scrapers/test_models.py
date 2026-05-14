from bet.scrapers.models import ScraperRun, PlayerSeasonStat
from sqlalchemy import text

def test_scraper_run_crud(session_factory):
    with session_factory() as session:
        run = ScraperRun(
            scraper_name="TestScraper",
            sport="football",
            target="ENG-Premier League"
        )
        session.add(run)
        session.commit()
        
        assert run.id is not None
        assert run.status == "running"
        assert run.records_scraped == 0
        
        # Modify
        run.status = "success"
        run.records_inserted = 100
        session.commit()
        
        fetched = session.query(ScraperRun).filter_by(id=run.id).first()
        assert fetched.status == "success"
        assert fetched.records_inserted == 100

def test_player_season_stat_relationships(session_factory, sample_sport_id):
    with session_factory() as session:
        # Need to create athlete first
        session.execute(
            text("INSERT INTO athletes (external_id, sport_id, name, updated_at) VALUES ('ext1', :sid, 'John Doe', 'now')"),
            {"sid": sample_sport_id}
        )
        session.commit()
        athlete_id = session.execute(text("SELECT id FROM athletes WHERE external_id = 'ext1'")).fetchone()[0]

        stat = PlayerSeasonStat(
            athlete_id=athlete_id,
            season="2425",
            source="fbref",
            games_played=10
        )
        session.add(stat)
        session.commit()
        
        fetched = session.query(PlayerSeasonStat).filter_by(id=stat.id).first()
        assert fetched.games_played == 10
        assert fetched.season == "2425"
