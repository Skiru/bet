import pytest
import sqlite3
from pathlib import Path
import tempfile
import sqlite3

from bet.db.schema import init_db
from bet.scrapers.engine import get_session_factory, Base
from bet.scrapers.models import _reflect_existing_tables

@pytest.fixture
def tmp_db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    
    # Initialize basic db schema
    with sqlite3.connect(path) as conn:
        init_db(conn)
        
    # In order to make it work with Scraper models, we reset session and engine
    import bet.scrapers.engine as scraper_engine
    scraper_engine._ENGINE = None
    scraper_engine._SESSION_FACTORY = None
    
    # Recreate the declarative mapping with the new schema in place
    engine = scraper_engine.get_engine(path)
    _reflect_existing_tables(engine)
    
    # Initialize scraper_db specifically to create new ORM mapped tables like scraper_runs and player_season_stats
    scraper_engine.init_scraper_db(path)

    yield path

    if path.exists():
        path.unlink()

@pytest.fixture
def session_factory(tmp_db_path):
    import bet.scrapers.engine as scraper_engine
    return scraper_engine.get_session_factory(tmp_db_path)

@pytest.fixture
def sample_sport_id(session_factory) -> int:
    from sqlalchemy import text
    with session_factory() as session:
        session.execute(text("INSERT INTO sports (name) VALUES ('football')"))
        session.commit()
        res = session.execute(text("SELECT id FROM sports WHERE name = 'football'")).fetchone()
        return res[0]
