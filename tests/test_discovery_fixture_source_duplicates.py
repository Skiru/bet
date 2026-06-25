from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from bet.db.schema import init_db
from bet.discovery.coordinator import EventDiscoveryCoordinator
from bet.discovery.dedup import DeduplicationEngine
from bet.discovery.models import DiscoveredEvent, MergedFixture, SourceRef, SourceRunStats
from bet.discovery.repository import DuplicateFixtureSourceMappingError, FixtureSourceRepo
from bet.scrapers.engine import Base


@pytest.fixture
def db_session():
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

    raw_conn = engine.raw_connection()
    try:
        raw_conn.row_factory = None
        init_db(raw_conn)
    finally:
        raw_conn.close()

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


def _event(
    *,
    source: str,
    external_id: str,
    home_team: str,
    away_team: str,
    kickoff: str = "2026-06-25T19:00:00+00:00",
    competition: str = "Premier League",
    sport: str = "football",
    odds: dict | None = None,
) -> DiscoveredEvent:
    return DiscoveredEvent(
        source=source,
        external_id=external_id,
        sport=sport,
        competition=competition,
        country="England",
        home_team=home_team,
        away_team=away_team,
        kickoff=datetime.fromisoformat(kickoff),
        odds=odds,
        raw_data={"source": source, "external_id": external_id},
    )


def _fixture(
    *,
    home_team: str,
    away_team: str,
    primary_source: str,
    primary_external_id: str,
    source_refs: list[tuple[str, str]],
    kickoff: str = "2026-06-25T19:00:00+00:00",
) -> MergedFixture:
    return MergedFixture(
        sport="football",
        competition="Premier League",
        country="England",
        home_team=home_team,
        away_team=away_team,
        kickoff=datetime.fromisoformat(kickoff),
        sources=[
            SourceRef(
                source=source,
                external_id=external_id,
                confidence=1.0,
                raw_data={"source": source, "external_id": external_id},
            )
            for source, external_id in source_refs
        ],
        primary_source=primary_source,
        primary_external_id=primary_external_id,
    )


def _seed_fixture_graph(session, kickoff: str = "2026-06-25T19:00:00+00:00") -> None:
    session.execute(text("INSERT INTO sports (id, name, tier) VALUES (1, 'football', 1)"))
    session.execute(text("INSERT INTO teams (id, sport_id, name) VALUES (1, 1, 'Arsenal')"))
    session.execute(text("INSERT INTO teams (id, sport_id, name) VALUES (2, 1, 'Chelsea')"))
    session.execute(text("INSERT INTO teams (id, sport_id, name) VALUES (3, 1, 'Arsenal FC')"))
    session.execute(
        text(
            "INSERT INTO competitions (id, sport_id, name, country, season) "
            "VALUES (1, 1, 'Premier League', 'England', '')"
        )
    )
    session.execute(
        text(
            "INSERT INTO fixtures "
            "(id, sport_id, competition_id, home_team_id, away_team_id, kickoff, fetched_at) "
            "VALUES (1, 1, 1, 1, 2, :kickoff, '2026-06-25T00:00:00+00:00')"
        ),
        {"kickoff": kickoff},
    )
    session.execute(
        text(
            "INSERT INTO fixtures "
            "(id, sport_id, competition_id, home_team_id, away_team_id, kickoff, fetched_at) "
            "VALUES (2, 1, 1, 3, 2, :kickoff, '2026-06-25T00:00:00+00:00')"
        ),
        {"kickoff": kickoff},
    )
    session.commit()


def test_compatible_duplicate_source_refs_merge_into_one_fixture():
    engine = DeduplicationEngine(fuzzy_threshold=85)
    normalized = engine._normalize_duplicate_source_refs(
        [
            _fixture(
                home_team="Arsenal",
                away_team="Chelsea",
                primary_source="api-football",
                primary_external_id="1389107",
                source_refs=[("api-football", "1389107"), ("odds-api", "odds-1")],
            ),
            _fixture(
                home_team="Arsenal FC",
                away_team="Chelsea",
                primary_source="api-football",
                primary_external_id="1389107",
                source_refs=[("api-football", "1389107")],
            ),
        ]
    )

    assert len(normalized) == 1
    assert {(src.source, src.external_id) for src in normalized[0].sources} == {
        ("api-football", "1389107"),
        ("odds-api", "odds-1"),
    }
    assert any("action=merged" in issue for issue in engine.last_issues)
    assert any("source=api-football" in issue for issue in engine.last_issues)


def test_incompatible_duplicate_source_refs_are_quarantined_and_logged():
    engine = DeduplicationEngine(fuzzy_threshold=85)
    fixtures = [
        _fixture(
            home_team="Arsenal",
            away_team="Chelsea",
            primary_source="api-football",
            primary_external_id="1389107",
            source_refs=[("api-football", "1389107"), ("odds-api", "odds-1")],
        ),
        _fixture(
            home_team="Liverpool",
            away_team="Everton",
            primary_source="api-football",
            primary_external_id="1389107",
            source_refs=[("api-football", "1389107")],
        ),
    ]

    normalized = engine._normalize_duplicate_source_refs(fixtures)

    assert len(normalized) == 1
    assert normalized[0].home_team == "Arsenal"
    assert ("api-football", "1389107") in {
        (src.source, src.external_id) for src in normalized[0].sources
    }
    assert any(
        "action=duplicate_source_ref_quarantined" in issue
        for issue in engine.last_issues
    )


def test_discover_reports_duplicate_normalization_issue_and_partial_verdict(
    db_session, monkeypatch, tmp_path: Path
):
    coordinator = EventDiscoveryCoordinator(session=db_session, sources=[])
    monkeypatch.setattr("bet.discovery.coordinator.DATA_DIR", tmp_path / "sandbox-data")

    events = {
        "api-football": [
            _event(
                source="api-football",
                external_id="1389107",
                home_team="Arsenal",
                away_team="Chelsea",
            ),
            _event(
                source="api-football",
                external_id="1389107",
                home_team="Liverpool",
                away_team="Everton",
            ),
        ]
    }
    stats = {
        "api-football": SourceRunStats(
            source="api-football",
            events_fetched=2,
            sports_covered=["football"],
        ),
    }
    monkeypatch.setattr(
        coordinator,
        "_fetch_all_sources",
        lambda date, sports: (events, stats),
    )

    result = coordinator.discover("2026-06-25", sports=["football"])

    assert result.verdict == "PARTIAL"
    assert any("DISCOVERY_DUPLICATE_SOURCE_REF" in issue for issue in result.issues)
    assert any(
        "action=duplicate_source_ref_quarantined" in issue for issue in result.issues
    )


def test_persist_normalized_duplicate_does_not_abort_run(db_session, monkeypatch, tmp_path: Path):
    coordinator = EventDiscoveryCoordinator(session=db_session, sources=[])
    monkeypatch.setattr("bet.discovery.coordinator.DATA_DIR", tmp_path / "sandbox-data")

    merged = coordinator.dedup._normalize_duplicate_source_refs(
        [
            _fixture(
                home_team="Arsenal",
                away_team="Chelsea",
                primary_source="api-football",
                primary_external_id="1389107",
                source_refs=[("api-football", "1389107"), ("odds-api", "odds-1")],
            ),
            _fixture(
                home_team="Arsenal FC",
                away_team="Chelsea",
                primary_source="api-football",
                primary_external_id="1389107",
                source_refs=[("api-football", "1389107")],
            ),
        ]
    )

    persisted = coordinator._persist("2026-06-25", merged)

    fixture_source_rows = db_session.execute(
        text(
            "SELECT source, external_id, COUNT(*) FROM fixture_sources "
            "GROUP BY source, external_id"
        )
    ).fetchall()
    api_football_rows = [row for row in fixture_source_rows if row[0] == "api-football"]

    assert persisted == 1
    assert api_football_rows == [("api-football", "1389107", 1)]
    assert coordinator.last_persist_issues == []
    assert any("DISCOVERY_DUPLICATE_SOURCE_REF" in issue for issue in coordinator.dedup.last_issues)


def test_repository_guard_rejects_cross_fixture_identity_reassignment(db_session):
    _seed_fixture_graph(db_session)
    repo = FixtureSourceRepo(db_session)
    repo.upsert(1, "api-football", "1389107")
    db_session.commit()

    with pytest.raises(DuplicateFixtureSourceMappingError) as exc_info:
        repo.upsert(2, "api-football", "1389107")

    assert "Duplicate fixture_sources mapping" in str(exc_info.value)
    rows = db_session.execute(
        text(
            "SELECT fixture_id, source, external_id FROM fixture_sources "
            "WHERE source = 'api-football' AND external_id = '1389107'"
        )
    ).fetchall()
    assert rows == [(1, "api-football", "1389107")]


def test_non_duplicate_persistence_behavior_is_unchanged(db_session):
    coordinator = EventDiscoveryCoordinator(session=db_session, sources=[])
    fixture = _fixture(
        home_team="Arsenal",
        away_team="Chelsea",
        primary_source="odds-api",
        primary_external_id="odds-1",
        source_refs=[("odds-api", "odds-1"), ("api-football", "1389107")],
    )

    first = coordinator._persist("2026-06-25", [fixture])
    second = coordinator._persist("2026-06-25", [fixture])
    fixture_rows = db_session.execute(text("SELECT COUNT(*) FROM fixtures")).scalar_one()
    source_rows = db_session.execute(
        text("SELECT COUNT(*) FROM fixture_sources WHERE source = 'odds-api' AND external_id = 'odds-1'")
    ).scalar_one()

    assert first == 1
    assert second == 1
    assert fixture_rows == 1
    assert source_rows == 1
