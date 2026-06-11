"""Sports Event Discovery Module — API-first fixture discovery.

Public API:
    discover_events(date, sports=None, verbose=False) → DiscoveryResult
"""

from .models import DiscoveredEvent, DiscoveryResult, MergedFixture, SourceRef

__all__ = [
    "discover_events",
    "DiscoveredEvent",
    "DiscoveryResult",
    "MergedFixture",
    "SourceRef",
]


def discover_events(
    date: str,
    sports: list[str] | None = None,
    verbose: bool = False,
    db_path: str | None = None,
) -> DiscoveryResult:
    """Run full event discovery pipeline.

    Creates a SQLAlchemy session backed by canonical DB bootstrap,
    instantiates default sources, and returns a DiscoveryResult
    with all merged fixtures.
    """
    from sqlalchemy import create_engine, event as sa_event
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from pathlib import Path

    from bet.scrapers.engine import Base
    from bet.db.connection import get_db
    from bet.db.schema import init_db

    if db_path is None:
        db_path = str(
            Path(__file__).parent.parent.parent.parent / "betting" / "data" / "betting.db"
        )

    # Bootstrap the full betting schema via canonical path (WAL, FK, busy_timeout)
    with get_db(db_path) as conn:
        init_db(conn)

    engine = create_engine(
        f"sqlite:///{db_path}",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @sa_event.listens_for(engine, "connect")
    def _pragma(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    # Ensure scraper ORM tables also exist (idempotent)
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()

    try:
        from .coordinator import EventDiscoveryCoordinator

        coordinator = EventDiscoveryCoordinator(session=session)
        return coordinator.discover(date, sports=sports, verbose=verbose)
    finally:
        session.close()
