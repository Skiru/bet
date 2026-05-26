"""Dataclass row models for the betting database."""

from dataclasses import dataclass, field


@dataclass
class Sport:
    id: int | None
    name: str
    tier: int
    stat_keys: list[str] = field(default_factory=list)


@dataclass
class TeamNews:
    id: int | None
    team_id: int
    sport_id: int
    betting_date: str
    injuries_json: list = field(default_factory=list)
    news_json: list = field(default_factory=list)
    coaching_json: list = field(default_factory=list)
    morale_json: list = field(default_factory=list)
    sources_json: list = field(default_factory=list)
    confidence: float = 0.0
    fetched_at: str = ""
    source: str = "gemini"



@dataclass
class FixtureSource:
    id: int | None
    fixture_id: int
    source: str
    external_id: str
    confidence: float = 1.0
    raw_data: str = ""
    fetched_at: str = ""


@dataclass
class Competition:
    id: int | None
    sport_id: int
    name: str
    country: str = ""
    importance: int = 3
    season: str = ""


@dataclass
class Team:
    id: int | None
    sport_id: int
    name: str
    aliases: list[str] = field(default_factory=list)
    country: str = ""
    venue: str = ""
    style_tags: list[str] = field(default_factory=list)


@dataclass
class Fixture:
    id: int | None
    sport_id: int
    competition_id: int | None
    home_team_id: int
    away_team_id: int
    kickoff: str
    status: str = "scheduled"
    score_home: int | None = None
    score_away: int | None = None
    external_id: str = ""
    source: str = ""
    fetched_at: str = ""


@dataclass
class MatchStat:
    id: int | None
    fixture_id: int
    team_id: int
    stat_key: str
    stat_value: float
    source: str = ""
    fetched_at: str = ""


@dataclass
class TeamForm:
    id: int | None
    team_id: int
    sport_id: int
    stat_key: str
    l10_values: list[float] = field(default_factory=list)
    l5_values: list[float] = field(default_factory=list)
    l10_avg: float | None = None
    l5_avg: float | None = None
    h2h_values: list[float] = field(default_factory=list)
    h2h_opponent_id: int | None = None
    trend: str = ""
    updated_at: str = ""
    source: str = ""


@dataclass
class OddsRecord:
    id: int | None
    fixture_id: int
    bookmaker: str
    market: str
    selection: str
    odds: float
    line: float | None = None
    fetched_at: str = ""
    is_closing: bool = False


@dataclass
class Coupon:
    id: int | None
    coupon_id: str
    coupon_type: str = "AKO"
    total_odds: float | None = None
    stake_pln: float | None = None
    status: str = "pending"
    pnl_pln: float | None = None
    placed_at: str = ""
    settled_at: str = ""
    betclic_ref: str = ""
    version: int = 1
    created_at: str = ""


@dataclass
class Bet:
    id: int | None
    coupon_id: int
    fixture_id: int | None
    sport: str
    event_name: str
    market: str
    selection: str
    odds: float
    min_odds: float | None = None
    safety_score: float | None = None
    hit_rate: float | None = None
    status: str = "pending"
    pnl_pln: float | None = None
    settled_at: str = ""
    market_pl: str = ""
    navigation_hint: str = ""
    stats_detail: dict | None = None


@dataclass
class PipelineRun:
    id: int | None
    date: str
    step: str
    status: str = "pending"
    started_at: str = ""
    completed_at: str = ""
    error_message: str = ""
    stats: dict | None = None


@dataclass
class SourceHealth:
    id: int | None
    source_name: str
    last_success: str = ""
    last_failure: str = ""
    consecutive_failures: int = 0
    total_requests: int = 0
    total_failures: int = 0
    avg_response_ms: float | None = None


@dataclass
class LeagueProfile:
    id: int | None
    competition_id: int
    stat_key: str
    season: str = ""
    avg_value: float = 0.0
    median_value: float | None = None
    std_dev: float | None = None
    sample_size: int = 0
    updated_at: str = ""


@dataclass
class MarketCandidate:
    """A scored market candidate for coupon building. Not persisted — computed."""

    fixture: Fixture
    home_team: Team
    away_team: Team
    sport_name: str
    competition_name: str
    market_name: str
    direction: str  # 'OVER' or 'UNDER'
    line: float
    safety_score: float
    hit_rate_l10: float
    hit_rate_h2h: float | None
    hit_rate_l5: float
    three_way_aligned: bool
    min_odds: float  # 1 / hit_rate
    best_odds: float | None
    ev: float | None  # (hit_rate * odds) - 1
    betclic_hit_rate: float | None  # from Betclic history (advisory)
    l10_values: list[float] = field(default_factory=list)
    l5_values: list[float] = field(default_factory=list)
    trend: str = ""


@dataclass
class AnalysisResult:
    id: int | None
    fixture_id: int
    betting_date: str
    has_data: bool = False
    best_market_name: str = ""
    best_market_line: float | None = None
    best_market_direction: str = ""
    best_safety_score: float | None = None
    markets_evaluated: int = 0
    ranking_json: list = field(default_factory=list)
    three_way_check_json: dict | None = None
    warnings_json: list = field(default_factory=list)
    stats_summary_json: dict | None = None
    source: str = ""
    created_at: str = ""


@dataclass
class GateResult:
    id: int | None
    fixture_id: int
    betting_date: str
    status: str = "pending"
    gate_score: int = 0
    gate_details_json: dict = field(default_factory=dict)
    best_market_name: str = ""
    best_market_line: float | None = None
    best_market_direction: str = ""
    best_safety_score: float | None = None
    ev: float | None = None
    risk_tier: str = ""
    rejection_reasons_json: list = field(default_factory=list)
    source: str = ""
    created_at: str = ""


@dataclass
class AnalysisRawData:
    id: int | None
    fixture_id: int
    betting_date: str
    team_a_l10_json: dict = field(default_factory=dict)
    team_b_l10_json: dict = field(default_factory=dict)
    h2h_meetings_json: dict = field(default_factory=dict)
    per_market_details_json: list = field(default_factory=list)
    safety_input_json: dict | None = None
    created_at: str = ""


@dataclass
class DecisionSnapshot:
    id: int | None
    bet_id: int
    fixture_id: int
    betting_date: str
    chosen_market: str
    chosen_line: float | None = None
    chosen_direction: str = ""
    safety_score: float | None = None
    all_markets_considered_json: list = field(default_factory=list)
    reasoning_json: dict = field(default_factory=dict)
    thresholds_json: dict = field(default_factory=dict)
    flip_conditions_json: dict = field(default_factory=dict)
    team_a_snapshot_json: dict = field(default_factory=dict)
    team_b_snapshot_json: dict = field(default_factory=dict)
    h2h_snapshot_json: dict = field(default_factory=dict)
    three_way_check_json: dict | None = None
    created_at: str = ""


@dataclass
class DecisionOutcome:
    id: int | None
    bet_id: int
    fixture_id: int
    betting_date: str
    sport: str
    competition: str = ""
    market: str = ""
    line: float | None = None
    direction: str = ""
    predicted_value: float | None = None
    actual_value: float | None = None
    deviation: float | None = None
    deviation_pct: float | None = None
    result: str = ""
    prediction_accuracy_json: dict = field(default_factory=dict)
    pattern_tags_json: list = field(default_factory=list)
    notes: str = ""
    created_at: str = ""


@dataclass
class ScanResult:
    id: int | None
    betting_date: str
    sport: str
    source_domain: str
    event_key: str
    home_team: str = ""
    away_team: str = ""
    competition: str = ""
    kickoff: str = ""
    raw_data: dict = field(default_factory=dict)
    scan_timestamp: str = ""


@dataclass
class ScanRunStats:
    id: int | None
    betting_date: str
    sport: str
    scanner_group: str
    events_found: int = 0
    sources_ok: int = 0
    sources_failed: int = 0
    deep_links_found: int = 0
    duration_seconds: float = 0.0
    validation_passed: bool = True
    gaps_description: list[str] = field(default_factory=list)
    scan_timestamp: str = ""


@dataclass
class Athlete:
    id: int | None
    external_id: str
    sport_id: int
    team_id: int | None
    name: str
    position: str = ""
    jersey: str = ""
    age: int | None = None
    height: str = ""
    weight: str = ""
    status: str = "active"
    source: str = "espn"
    updated_at: str = ""


@dataclass
class PlayerGamelog:
    id: int | None
    athlete_id: int
    fixture_id: int | None
    game_date: str
    opponent: str = ""
    result: str = ""
    stats_json: str = "{}"
    source: str = "espn"


@dataclass
class PlayerSplit:
    id: int | None
    athlete_id: int
    split_type: str  # 'home', 'away', 'vs_conference', 'last5', 'last10'
    stats_json: str = "{}"
    season: str = ""
    source: str = "espn"
    updated_at: str = ""


@dataclass
class Standing:
    id: int | None
    competition_id: int
    team_id: int
    season: str = ""
    rank: int | None = None
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    goal_diff: int = 0
    points: int = 0
    form: str = ""
    home_wins: int = 0
    home_draws: int = 0
    home_losses: int = 0
    away_wins: int = 0
    away_draws: int = 0
    away_losses: int = 0
    streak: str = ""
    source: str = "espn"
    updated_at: str = ""


@dataclass
class TeamATSRecord:
    id: int | None
    team_id: int
    sport_id: int
    season: str
    season_type: int = 2
    wins: int = 0
    losses: int = 0
    pushes: int = 0
    home_wins: int = 0
    home_losses: int = 0
    home_pushes: int = 0
    away_wins: int = 0
    away_losses: int = 0
    away_pushes: int = 0
    source: str = "espn"
    updated_at: str = ""


@dataclass
class TeamOURecord:
    id: int | None
    team_id: int
    sport_id: int
    season: str
    season_type: int = 2
    overs: int = 0
    unders: int = 0
    pushes: int = 0
    home_overs: int = 0
    home_unders: int = 0
    home_pushes: int = 0
    away_overs: int = 0
    away_unders: int = 0
    away_pushes: int = 0
    source: str = "espn"
    updated_at: str = ""


@dataclass
class ESPNPrediction:
    id: int | None
    fixture_id: int
    home_win_pct: float | None = None
    away_win_pct: float | None = None
    tie_pct: float | None = None
    predictor_json: str | None = None
    power_index_home: float | None = None
    power_index_away: float | None = None
    source: str = "espn"
    fetched_at: str = ""


@dataclass
class TeamRoster:
    id: int | None
    team_id: int
    athlete_id: int
    position: str = ""
    jersey: str = ""
    status: str = "active"
    depth_rank: int | None = None
    season: str = ""
    updated_at: str = ""


@dataclass
class Transaction:
    id: int | None
    team_id: int
    athlete_id: int | None
    transaction_type: str
    description: str = ""
    transaction_date: str = ""
    source: str = "espn"
    fetched_at: str = ""


@dataclass
class PowerIndex:
    id: int | None
    team_id: int
    sport_id: int
    season: str
    rating: float
    offensive_rating: float | None = None
    defensive_rating: float | None = None
    rank: int | None = None
    source: str = "espn"
    updated_at: str = ""


@dataclass
class TipsterPick:
    id: int | None
    betting_date: str
    source_site: str
    tipster_name: str = ""
    sport: str = ""
    event: str = ""
    home_team: str = ""
    away_team: str = ""
    competition: str = ""
    market: str = ""
    market_type: str = ""
    direction: str = ""
    odds: float | None = None
    reasoning: str = ""
    accuracy_pct: float | None = None
    confidence: str = ""
    stats_cited: list[str] = field(default_factory=list)
    fetch_time: str = ""
    created_at: str = ""


@dataclass
class TipsterConsensus:
    id: int | None
    betting_date: str
    event: str = ""
    sport: str = ""
    competition: str = ""
    home_team: str = ""
    away_team: str = ""
    total_tipsters: int = 0
    consensus_market: str = ""
    consensus_direction: str = ""
    agreement_pct: float = 0.0
    statistical_picks: int = 0
    outcome_picks: int = 0
    has_reasoning: bool = False
    tipster_sources: list[str] = field(default_factory=list)
    confidence_adj: float = 0.0
    created_at: str = ""


@dataclass
class PipelineCandidate:
    id: int | None
    fixture_id: int
    betting_date: str
    rank: int
    score: float = 0.0
    sport: str = ""
    competition: str = ""
    home_team: str = ""
    away_team: str = ""
    kickoff: str = ""
    data_tier: str = "FIXTURE_ONLY"
    comp_score: int = 3
    n_odds_markets: int = 0
    n_safety_markets: int = 0
    odds_markets_json: list = field(default_factory=list)
    safety_markets_json: list = field(default_factory=list)
    fixture_verified: bool = False
    verification_sources_json: list = field(default_factory=list)
    tipster_count: int = 0
    tipster_support_json: dict | None = None
    source: str = "build_shortlist"
    created_at: str = ""
