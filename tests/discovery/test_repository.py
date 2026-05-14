import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from bet.db.schema import init_db
from bet.discovery.repository import FixtureSourceRepo
from bet.discovery.models import FixtureSourceModel
from bet.scrapers.engine import Base


@pytest.fixture
def sa_session():
    """In-memory SQLAlchemy session with full schema."""
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    # Apply raw SQL schema first (for fixtures, sports, teams, etc.)
    raw_conn = engine.raw_connection()
    try:
        raw_conn.row_factory = None
        init_db(raw_conn)
    finally:
        raw_conn.close()

    # Create SA-managed tables (fixture_sources)
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()

    # Seed required data
    session.execute(text("INSERT INTO sports (name, tier) VALUES ('football', 1)"))
    session.execute(text("INSERT INTO teams (sport_id, name) VALUES (1, 'Team A')"))
    session.execute(text("INSERT INTO teams (sport_id, name) VALUES (1, 'Team B')"))
    session.execute(text(
        "INSERT INTO fixtures (sport_id, home_team_id, away_team_id, kickoff, fetched_at) "
        "VALUES (1, 1, 2, '2026-05-14T10:00:00Z', '2026-05-14')"
    ))
    session.commit()

    yield session
    session.close()


@pytest.fixture
def repo(sa_session):
    return FixtureSourceRepo(sa_session)


def test_fixture_source_upsert(sa_session, repo):
    obj = repo.upsert(1, "sofascore", "ext_123", confidence=0.9, raw_data={"a": 1})
    sa_session.commit()
    assert obj.id is not None
    assert obj.source == "sofascore"
    assert obj.external_id == "ext_123"

    # update
    obj2 = repo.upsert(1, "sofascore", "ext_123", confidence=0.95, raw_data={"a": 2})
    sa_session.commit()
    assert obj2.id == obj.id
    assert obj2.confidence == 0.95
    assert '"a": 2' in obj2.raw_data


def test_fixture_source_get_by_fixture(sa_session, repo):
    repo.upsert(1, "odds-api", "oa_1")
    repo.upsert(1, "api-football", "af_1")
    sa_session.commit()

    records = repo.get_by_fixture(1)
    assert len(records) == 2
    sources = [r.source for r in records]
    assert "odds-api" in sources
    assert "api-football" in sources


def test_fixture_source_get_by_source_id(sa_session, repo):
    repo.upsert(1, "odds-api", "unique_id_x")
    sa_session.commit()

    record = repo.get_by_source_id("odds-api", "unique_id_x")
    assert record is not None
    assert record.fixture_id == 1
    assert record.external_id == "unique_id_x"

    assert repo.get_by_source_id("odds-api", "not_exist") is None


def test_fixture_source_bulk_upsert(sa_session, repo):
    records = [
        (1, "source_1", "ext_1", 1.0, {"key": "val1"}),
        (1, "source_2", "ext_2", 0.8, None),
    ]
    count = repo.bulk_upsert(records)
    sa_session.commit()
    assert count == 2

    all_recs = repo.get_by_fixture(1)
    assert len(all_recs) == 2


def test_fixture_source_fk_constraint(sa_session, repo):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        repo.upsert(999, "sofascore", "ext_123")
        sa_session.flush()
