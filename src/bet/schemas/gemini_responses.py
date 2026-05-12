"""Pydantic response schemas for Gemini API controlled generation.

These schemas enforce structured JSON output from Gemini calls.
Used as response_schema parameter in GeminiClient methods.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Phase 1: Tipster Reading
# ---------------------------------------------------------------------------

class TipsterPickExtracted(BaseModel):
    """Single pick extracted from a tipster page via Gemini URL reading."""
    sport: str = ""
    home_team: str = ""
    away_team: str = ""
    competition: str = ""
    market: str              # e.g., "Corners O9.5", "Over 2.5 goals"
    market_type: str = ""    # "statistical" or "outcome"
    direction: str = ""      # "OVER", "UNDER", "WIN", "DRAW"
    selection: str = ""      # Full selection text
    odds: Optional[float] = None
    confidence: float = 0.5  # 0-1, extraction confidence
    reasoning: str = ""
    stats_cited: List[str] = Field(default_factory=list)


class TipsterPageResult(BaseModel):
    """All picks extracted from a single tipster page."""
    source_name: str = ""
    url: str = ""
    picks: List[TipsterPickExtracted] = Field(default_factory=list)
    extraction_confidence: float = 0.0


# ---------------------------------------------------------------------------
# Phase 1: Web Research
# ---------------------------------------------------------------------------

class WebResearchResult(BaseModel):
    """Structured result from Gemini search grounding research."""
    query: str = ""
    data_type: str = ""       # "h2h", "injuries", "form", "coach"
    team: str = ""
    sport: str = ""
    findings: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    data_freshness: str = ""  # "today", "this_week", "this_month", "older"


# ---------------------------------------------------------------------------
# Phase 1: News Enrichment
# ---------------------------------------------------------------------------

class InjuryReport(BaseModel):
    """Single injury report for a player."""
    player_name: str
    status: str              # "out", "doubtful", "questionable", "probable"
    injury_type: str = ""
    expected_return: str = ""
    impact: str = "low"      # "critical", "high", "medium", "low"
    source: str = ""


class NewsEnrichmentResult(BaseModel):
    """Injury/news/coaching enrichment from Gemini search."""
    team_name: str
    sport: str = ""
    injuries: List[InjuryReport] = Field(default_factory=list)
    recent_news: List[str] = Field(default_factory=list)
    coaching_changes: List[str] = Field(default_factory=list)
    morale_indicators: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    confidence: float = 0.0


class EventContextResult(BaseModel):
    """Full event context from Gemini search."""
    home_team: str = ""
    away_team: str = ""
    sport: str = ""
    competition: str = ""
    home_news: Optional[NewsEnrichmentResult] = None
    away_news: Optional[NewsEnrichmentResult] = None
    weather: str = ""
    venue_notes: str = ""
    motivation_factors: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase 2: Deep Analysis
# ---------------------------------------------------------------------------

class MarketAnalysis(BaseModel):
    """Gemini's analysis of a single betting market for a candidate."""
    market_name: str
    direction: str = ""
    confidence: float = 0.0   # 0-1
    reasoning: str = ""
    bull_case: str = ""
    bear_case: str = ""
    key_stats: List[str] = Field(default_factory=list)
    risk_factors: List[str] = Field(default_factory=list)


class CandidateDeepAnalysis(BaseModel):
    """Full Gemini deep analysis for a single candidate event."""
    event: str = ""
    sport: str = ""
    competition: str = ""
    recommended_markets: List[MarketAnalysis] = Field(default_factory=list)
    upset_risk_score: float = 0.0   # 0-1
    upset_risk_reasoning: str = ""
    context_flags: List[str] = Field(default_factory=list)
    overall_confidence: float = 0.0  # 0-1
    narrative: str = ""
    data_quality_assessment: str = "MINIMAL"  # FULL, PARTIAL, MINIMAL
