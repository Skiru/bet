"""LLM Response schemas — canonical import point for all AI response models.

Re-exports all schemas from gemini_responses.py (kept for backward compatibility).
New code should import from this module.
"""

from bet.schemas.gemini_responses import (
    CandidateDeepAnalysis,
    EventContextResult,
    MarketAnalysis,
    NewsEnrichmentResult,
    TipsterPageResult,
    TipsterPickExtracted,
    WebResearchResult,
)

__all__ = [
    "CandidateDeepAnalysis",
    "EventContextResult",
    "MarketAnalysis",
    "NewsEnrichmentResult",
    "TipsterPageResult",
    "TipsterPickExtracted",
    "WebResearchResult",
]
