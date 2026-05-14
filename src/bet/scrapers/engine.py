from __future__ import annotations

from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent.parent / "betting" / "data" / "betting.db"

class Base(DeclarativeBase):
    pass

_ENGINE = None
_SESSION_FACTORY = None

def get_engine(db_path=DEFAULT_DB_PATH):
    global _ENGINE
    if _ENGINE is None:
        db_url = f"sqlite:///{db_path}"
        _ENGINE = create_engine(
            db_url,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False}
        )

        @event.listens_for(_ENGINE, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()
            
    return _ENGINE

def get_session_factory(db_path=DEFAULT_DB_PATH):
    global _SESSION_FACTORY
    if _SESSION_FACTORY is None:
        engine = get_engine(db_path)
        _SESSION_FACTORY = sessionmaker(bind=engine, expire_on_commit=False)
    return _SESSION_FACTORY

def init_scraper_db(db_path=DEFAULT_DB_PATH):
    engine = get_engine(db_path)
    from bet.scrapers.models import _reflect_existing_tables
    _reflect_existing_tables(engine)
    Base.metadata.create_all(engine)
