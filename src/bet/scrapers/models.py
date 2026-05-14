from __future__ import annotations

from datetime import datetime, timezone
import json
from sqlalchemy import Column, Integer, String, Float, ForeignKey, text, Table
from bet.scrapers.engine import Base, get_engine


class ScraperRun(Base):
    __tablename__ = "scraper_runs"

    id = Column(Integer, primary_key=True)
    scraper_name = Column(String, nullable=False)
    sport = Column(String, nullable=False)
    target = Column(String, nullable=False)
    status = Column(String, nullable=False, default='running')
    records_scraped = Column(Integer, default=0)
    records_inserted = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    error_message = Column(String)
    started_at = Column(String, nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    finished_at = Column(String)
    duration_seconds = Column(Float)


class PlayerSeasonStat(Base):
    __tablename__ = "player_season_stats"

    id = Column(Integer, primary_key=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False)
    competition_id = Column(Integer, ForeignKey("competitions.id", ondelete="SET NULL"))
    season = Column(String, nullable=False)
    games_played = Column(Integer, default=0)
    games_started = Column(Integer, default=0)
    minutes_played = Column(Float, default=0.0)
    stats_json = Column(String, nullable=False, default='{}')
    per_game_json = Column(String, nullable=False, default='{}')
    advanced_json = Column(String, nullable=False, default='{}')
    source = Column(String, nullable=False)
    updated_at = Column(String, nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())


def _reflect_existing_tables(engine=None):
    if engine is None:
        engine = get_engine()
    
    # We selectively reflect tables that are referred to by Scraper ORM models,
    # or any existing ones, to safely interact with them.
    # Note: `extend_existing=True` ensures we can safely re-reflect or augment.
    Base.metadata.reflect(bind=engine, only=["sports", "competitions", "teams", "fixtures", "athletes"], extend_existing=True)

