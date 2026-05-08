"""Betting database layer — connection, models, and repositories.

Usage:
    from bet.db import get_db, FixtureRepo, TeamRepo
    with get_db() as conn:
        repo = FixtureRepo(conn)
        ...
"""

from bet.db.connection import get_db, get_async_db  # noqa: F401
from bet.db.repositories import (  # noqa: F401
    AnalysisRawDataRepo,
    AnalysisResultRepo,
    AthleteRepo,
    CompetitionRepo,
    CouponRepo,
    DecisionOutcomeRepo,
    DecisionSnapshotRepo,
    ESPNPredictionRepo,
    FixtureRepo,
    GateResultRepo,
    LeagueProfileRepo,
    OddsRepo,
    PipelineRepo,
    PlayerGamelogRepo,
    PlayerSplitRepo,
    PowerIndexRepo,
    ScanResultRepo,
    SourceHealthRepo,
    SportRepo,
    StandingRepo,
    StatsRepo,
    TeamATSRepo,
    TeamOURepo,
    TeamRepo,
    TeamRosterRepo,
    TransactionRepo,
)
