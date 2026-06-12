from datetime import datetime
from pydantic import BaseModel, Field
from sqlalchemy import Column, Float, Integer, Text, UniqueConstraint
from bet.scrapers.engine import Base

class FixtureSourceModel(Base):
    __tablename__ = "fixture_sources"
    id = Column(Integer, primary_key=True, autoincrement=True)
    fixture_id = Column(Integer, nullable=False)
    source = Column(Text, nullable=False)
    external_id = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False, default=1.0)
    raw_data = Column(Text, nullable=True)
    fetched_at = Column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("fixture_id", "source", name="uq_fixture_source"),)

    def __repr__(self):
        return f"<FixtureSource fixture={self.fixture_id} source={self.source} ext_id={self.external_id}>"
    
    def to_dict(self):
        return {
            "id": self.id, "fixture_id": self.fixture_id, "source": self.source,
            "external_id": self.external_id, "confidence": self.confidence,
            "raw_data": self.raw_data, "fetched_at": self.fetched_at,
        }

class SourceRunStats(BaseModel):
    source: str
    events_fetched: int = 0
    sports_covered: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    available: bool = True

class DiscoveredEvent(BaseModel):
    source: str                     # 'sofascore', 'odds-api', 'api-football'
    external_id: str                # Source-specific event ID
    sport: str                      # 'football', 'basketball', etc.
    competition: str                # League/tournament name
    country: str = ""
    home_team: str
    away_team: str
    kickoff: datetime               # UTC kickoff time
    status: str = "scheduled"
    odds: dict | None = None
    raw_data: dict | None = None

class SourceRef(BaseModel):
    source: str
    external_id: str
    confidence: float = 1.0
    raw_data: dict | None = None

class MergedFixture(BaseModel):
    sport: str
    competition: str
    country: str = ""
    home_team: str
    away_team: str
    kickoff: datetime
    status: str = "scheduled"
    sources: list[SourceRef]
    primary_source: str
    primary_external_id: str
    odds: dict | None = None

    @property
    def source_count(self) -> int:
        return len(self.sources)

class DiscoveryResult(BaseModel):
    date: str
    fixtures: list[MergedFixture]
    total_discovered: int
    total_after_dedup: int
    by_sport: dict[str, int]
    source_stats: dict[str, SourceRunStats]
    issues: list[str] = Field(default_factory=list)
    verdict: str = "OK"
