from sqlalchemy import text
import bet.scrapers.engine as scraper_engine

def test_engine_creation(tmp_db_path):
    engine = scraper_engine.get_engine(tmp_db_path)
    assert engine is not None
    assert "sqlite" in engine.url.drivername

def test_sqlite_pragmas(session_factory):
    with session_factory() as session:
        # Test WAL mode
        res = session.execute(text("PRAGMA journal_mode")).fetchone()
        assert res[0].lower() == "wal"
        
        # Test Foreign Keys
        res = session.execute(text("PRAGMA foreign_keys")).fetchone()
        assert res[0] == 1
