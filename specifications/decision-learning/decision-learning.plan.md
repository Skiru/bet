# Decision Learning System — Implementation Plan

**Date:** 2026-05-06  
**Author:** Architect  
**Status:** Draft  
**Scope:** Store full analysis context at decision time, compare predictions to outcomes post-settlement, and surface learning patterns by sport/market/league/team.

---

## 1. Solution Architecture

### Problem

The S3 deep analysis (`deep_stats_report.py`) produces rich statistical data — L10 match-by-match values, H2H meeting details, per-market rankings with three-way checks — but only stores a summary in `analysis_results`. When a bet is placed and later settled, we cannot reconstruct:

- **Why** that specific market was chosen over alternatives
- **What** the raw L10/H2H values were at decision time
- **How far off** our prediction was from reality
- **Whether** there are systematic biases (e.g., "corners in La Liga overestimated by 15%")

### Target Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  DECISION LEARNING DATA FLOW                    │
│                                                                 │
│  S3 deep_stats_report.py                                       │
│       │                                                         │
│       ├── analysis_results (existing — summary)                 │
│       └── analysis_raw_data (NEW — full L10/H2H/per-market)    │
│                    │                                            │
│  S8 coupon_builder.py                                          │
│       │                                                         │
│       ├── bets.stats_detail (populated with key snapshot)       │
│       └── decision_snapshots (NEW — full reasoning chain)       │
│                    │                                            │
│  settle_on_finish.py                                           │
│       │                                                         │
│       └── evaluate_decisions.py (NEW — post-settlement)         │
│                    │                                            │
│                    └── decision_outcomes (NEW — pred vs actual)  │
│                              │                                  │
│  historical_learning.py (ENHANCED)                              │
│       └── queries decision_outcomes for bias patterns           │
└─────────────────────────────────────────────────────────────────┘
```

### New Tables

```
analysis_raw_data          decision_snapshots          decision_outcomes
─────────────────          ──────────────────          ─────────────────
fixture_id (FK)            bet_id (FK)                 bet_id (FK)
betting_date               fixture_id (FK)             fixture_id (FK)
team_a_l10_json            betting_date                betting_date
team_b_l10_json            chosen_market               predicted_value
h2h_meetings_json          chosen_line                 predicted_line
per_market_details_json    chosen_direction             actual_value
safety_input_json          safety_score                deviation
                           all_markets_considered_json  deviation_pct
                           reasoning_json              result
                           thresholds_json             prediction_accuracy_json
                           flip_conditions_json        pattern_tags_json
```

### Key Design Decisions

1. **Separate `analysis_raw_data` from `analysis_results`** — The existing table stores processed summaries; raw data (match-by-match arrays) is bulky and not needed for pipeline reads. Separate table keeps existing queries fast.

2. **`decision_snapshots` linked to `bets`** — Created at coupon build time (S8), captures the specific reasoning for the chosen market. Only exists for bets that were actually placed.

3. **`decision_outcomes` written post-settlement** — Requires actual match stats. Fetched from the same sources settle_on_finish.py already uses, plus match_stats table.

4. **JSON columns for flexibility** — Consistent with existing pattern (ranking_json, gate_details_json). Allows schema evolution without migrations.

---

## 2. File Tree (Created / Modified)

```
[CREATE] src/bet/db/migrations/003_decision_learning.sql
[MODIFY] src/bet/db/schema.sql                          — add 3 new tables + indexes
[MODIFY] src/bet/db/models.py                           — add 3 new dataclasses
[MODIFY] src/bet/db/repositories.py                     — add 3 new repo classes
[MODIFY] scripts/deep_stats_report.py                   — store raw data in analysis_raw_data
[MODIFY] scripts/db_data_loader.py                      — add save/load functions for new tables
[MODIFY] scripts/coupon_builder.py                      — populate decision_snapshots + bets.stats_detail
[CREATE] scripts/evaluate_decisions.py                  — post-settlement outcome evaluation
[MODIFY] scripts/settle_on_finish.py                    — call evaluate_decisions after settlement
[MODIFY] scripts/historical_learning.py                 — add learning queries from decision_outcomes
```

---

## 3. Phase 1: Schema + Models

### Task 1.1 — Create migration SQL [CREATE]

**File:** `src/bet/db/migrations/003_decision_learning.sql`

```sql
-- Migration 003: Decision Learning System
-- Adds tables for storing full analysis context and learning from outcomes

CREATE TABLE IF NOT EXISTS analysis_raw_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
    betting_date TEXT NOT NULL,
    team_a_l10_json TEXT NOT NULL DEFAULT '{}',
    team_b_l10_json TEXT NOT NULL DEFAULT '{}',
    h2h_meetings_json TEXT NOT NULL DEFAULT '{}',
    per_market_details_json TEXT NOT NULL DEFAULT '[]',
    safety_input_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(fixture_id, betting_date)
);

CREATE TABLE IF NOT EXISTS decision_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bet_id INTEGER NOT NULL REFERENCES bets(id),
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
    betting_date TEXT NOT NULL,
    chosen_market TEXT NOT NULL,
    chosen_line REAL,
    chosen_direction TEXT NOT NULL,
    safety_score REAL,
    all_markets_considered_json TEXT NOT NULL DEFAULT '[]',
    reasoning_json TEXT NOT NULL DEFAULT '{}',
    thresholds_json TEXT NOT NULL DEFAULT '{}',
    flip_conditions_json TEXT NOT NULL DEFAULT '{}',
    team_a_snapshot_json TEXT NOT NULL DEFAULT '{}',
    team_b_snapshot_json TEXT NOT NULL DEFAULT '{}',
    h2h_snapshot_json TEXT NOT NULL DEFAULT '{}',
    three_way_check_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(bet_id)
);

CREATE TABLE IF NOT EXISTS decision_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bet_id INTEGER NOT NULL REFERENCES bets(id),
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
    betting_date TEXT NOT NULL,
    sport TEXT NOT NULL,
    competition TEXT,
    market TEXT NOT NULL,
    line REAL,
    direction TEXT NOT NULL,
    predicted_value REAL,
    actual_value REAL,
    deviation REAL,
    deviation_pct REAL,
    result TEXT NOT NULL,
    prediction_accuracy_json TEXT NOT NULL DEFAULT '{}',
    pattern_tags_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(bet_id)
);

-- Indexes for common learning queries
CREATE INDEX IF NOT EXISTS idx_analysis_raw_fixture ON analysis_raw_data(fixture_id);
CREATE INDEX IF NOT EXISTS idx_analysis_raw_date ON analysis_raw_data(betting_date);
CREATE INDEX IF NOT EXISTS idx_decision_snapshots_fixture ON decision_snapshots(fixture_id);
CREATE INDEX IF NOT EXISTS idx_decision_snapshots_date ON decision_snapshots(betting_date);
CREATE INDEX IF NOT EXISTS idx_decision_outcomes_sport ON decision_outcomes(sport);
CREATE INDEX IF NOT EXISTS idx_decision_outcomes_market ON decision_outcomes(market);
CREATE INDEX IF NOT EXISTS idx_decision_outcomes_date ON decision_outcomes(betting_date);
CREATE INDEX IF NOT EXISTS idx_decision_outcomes_result ON decision_outcomes(result);
```

**Definition of Done:**
- [ ] SQL file exists and is valid SQLite syntax
- [ ] All FKs reference existing tables
- [ ] `UNIQUE` constraints prevent duplicate entries
- [ ] Indexes cover the primary query patterns (by sport, market, date, result)

---

### Task 1.2 — Update main schema.sql [MODIFY]

**File:** `src/bet/db/schema.sql`

Append the 3 new `CREATE TABLE IF NOT EXISTS` statements and indexes (same as migration SQL) at the end of the file, before any trailing comments.

**Definition of Done:**
- [ ] Fresh `init_database.py` run creates all 3 new tables
- [ ] Existing tables are unchanged
- [ ] `PRAGMA integrity_check` passes

---

### Task 1.3 — Add dataclass models [MODIFY]

**File:** `src/bet/db/models.py`

Add three new dataclasses:

```python
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
    chosen_line: float | None
    chosen_direction: str
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
```

**Definition of Done:**
- [ ] All 3 dataclasses importable from `bet.db.models`
- [ ] Field types match the SQL column types (TEXT↔str, REAL↔float|None, JSON↔dict/list)
- [ ] Existing model imports are unbroken

---

### Task 1.4 — Add repository classes [MODIFY]

**File:** `src/bet/db/repositories.py`

Add three new repository classes following existing patterns (parameterized queries, json.dumps on write, json.loads on read):

#### AnalysisRawDataRepo

```python
class AnalysisRawDataRepo:
    def __init__(self, conn): ...
    def save(self, raw: AnalysisRawData) -> None: ...
    def get_by_fixture(self, fixture_id: int, betting_date: str) -> AnalysisRawData | None: ...
    def get_by_date(self, betting_date: str) -> list[AnalysisRawData]: ...
```

#### DecisionSnapshotRepo

```python
class DecisionSnapshotRepo:
    def __init__(self, conn): ...
    def save(self, snapshot: DecisionSnapshot) -> None: ...
    def get_by_bet(self, bet_id: int) -> DecisionSnapshot | None: ...
    def get_by_fixture(self, fixture_id: int) -> list[DecisionSnapshot]: ...
    def get_by_date(self, betting_date: str) -> list[DecisionSnapshot]: ...
```

#### DecisionOutcomeRepo

```python
class DecisionOutcomeRepo:
    def __init__(self, conn): ...
    def save(self, outcome: DecisionOutcome) -> None: ...
    def get_by_bet(self, bet_id: int) -> DecisionOutcome | None: ...
    def get_by_sport(self, sport: str, limit: int = 100) -> list[DecisionOutcome]: ...
    def get_by_market(self, market: str, limit: int = 100) -> list[DecisionOutcome]: ...
    def get_by_sport_and_market(self, sport: str, market: str, limit: int = 100) -> list[DecisionOutcome]: ...
    def get_by_competition(self, competition: str, limit: int = 100) -> list[DecisionOutcome]: ...
    def get_all_settled(self, limit: int = 500) -> list[DecisionOutcome]: ...
    def get_deviation_stats(self, sport: str | None, market: str | None) -> dict: ...
```

The `get_deviation_stats` method should return aggregated stats:
```python
{
    "count": int,
    "avg_deviation": float,
    "avg_deviation_pct": float,
    "overestimate_count": int,
    "underestimate_count": int,
    "won_count": int,
    "lost_count": int,
}
```

**Definition of Done:**
- [ ] All 3 repos instantiable with a sqlite3.Connection
- [ ] `save()` uses INSERT OR REPLACE with parameterized queries
- [ ] JSON columns serialized with `json.dumps()` on write, `json.loads()` on read
- [ ] All query methods return typed model objects
- [ ] `get_deviation_stats` returns aggregate dict computed via SQL

---

### Task 1.5 — Apply migration to existing DB [CREATE/MODIFY]

**File:** `scripts/migrate_data.py` (add new function) or inline in `init_database.py`

Add function `apply_decision_learning_migration()` that:
1. Reads `src/bet/db/migrations/003_decision_learning.sql`
2. Executes against the DB connection
3. Logs tables created

**Definition of Done:**
- [ ] Running migration on existing DB adds the 3 tables without affecting existing data
- [ ] Running migration twice is idempotent (`CREATE TABLE IF NOT EXISTS`)
- [ ] `init_database.py` includes the new tables via updated schema.sql

---

## 4. Phase 2: Populate Decision Data

### Task 2.1 — Enhance deep_stats_report to store raw data [MODIFY]

**File:** `scripts/deep_stats_report.py`

**Changes:**

1. In `analyze_candidate()`, after computing stats_a, stats_b, h2h, and ranking_result, build a raw data dict:

```python
raw_data = {
    "team_a_l10": {
        "team": stats_a["team"],
        "l10_avg": stats_a["l10_avg"],       # {stat: avg}
        "l5_avg": stats_a["l5_avg"],         # {stat: avg}
        "l10_matches": stats_a["l10_matches"],  # full match-by-match data
        "sources": stats_a["sources"],
    },
    "team_b_l10": {
        "team": stats_b["team"],
        "l10_avg": stats_b["l10_avg"],
        "l5_avg": stats_b["l5_avg"],
        "l10_matches": stats_b["l10_matches"],
        "sources": stats_b["sources"],
    },
    "h2h_meetings": {
        "has_data": h2h["has_data"],
        "meetings": h2h["meetings"],         # full meeting details
        "averages": h2h["averages"],
    },
    "per_market_details": [
        {
            "name": mkt["name"],
            "line": mkt["line"],
            "direction": mkt["direction"],
            "safety_score": mkt["safety_score"],
            "combined_avg": mkt["combined_avg"],
            "h2h_avg": mkt.get("h2h_avg"),
            "hit_rate_l10": mkt["hit_rate_l10"],
            "hit_rate_h2h": mkt["hit_rate_h2h"],
            "margin": mkt.get("margin"),
            "three_way_check": mkt.get("three_way_check"),
            "one_sided": mkt.get("one_sided", False),
            "h2h_blind": mkt.get("h2h_blind", False),
        }
        for mkt in ranking_result.get("ranking", [])
    ],
    "safety_input": safety_input,  # the raw input to rank_markets()
}
```

2. Return `raw_data` as a new key in the `analyze_candidate()` return dict.

3. In `save_analysis_results_to_db()` in `db_data_loader.py`, after saving to `analysis_results`, also save to `analysis_raw_data`:

```python
from bet.db.repositories import AnalysisRawDataRepo
from bet.db.models import AnalysisRawData

raw_repo = AnalysisRawDataRepo(conn)
raw_model = AnalysisRawData(
    id=None,
    fixture_id=fixture_id,
    betting_date=betting_date,
    team_a_l10_json=a.get("raw_data", {}).get("team_a_l10", {}),
    team_b_l10_json=a.get("raw_data", {}).get("team_b_l10", {}),
    h2h_meetings_json=a.get("raw_data", {}).get("h2h_meetings", {}),
    per_market_details_json=a.get("raw_data", {}).get("per_market_details", []),
    safety_input_json=a.get("raw_data", {}).get("safety_input"),
    created_at=_NOW(),
)
raw_repo.save(raw_model)
```

**Definition of Done:**
- [ ] `analyze_candidate()` returns a `raw_data` key with full L10 matches, H2H meetings, per-market details
- [ ] `save_analysis_results_to_db()` writes to both `analysis_results` AND `analysis_raw_data`
- [ ] Running S3 (`deep_stats_report.py --date YYYY-MM-DD`) populates `analysis_raw_data` table
- [ ] Existing pipeline behavior unchanged (all existing tests pass)

---

### Task 2.2 — Enhance coupon_builder to create decision_snapshots [MODIFY]

**File:** `scripts/coupon_builder.py`

**Changes:**

1. After creating each `Bet` row and getting its `bet_id`, build a `DecisionSnapshot`:

```python
def _build_decision_snapshot(bet_id: int, fixture_id: int, betting_date: str, pick: dict) -> DecisionSnapshot:
    """Build decision snapshot from gate-approved pick data."""
    best = pick.get("best_market") or {}
    analysis = pick.get("analysis_data") or {}  # from analysis_results
    raw = pick.get("raw_data") or {}            # from analysis_raw_data

    # All markets considered (from ranking_json in analysis_results)
    all_markets = analysis.get("ranking_json", [])

    # Reasoning chain
    reasoning = {
        "chosen_because": f"Highest safety score ({best.get('safety_score')}) among {len(all_markets)} evaluated markets",
        "runner_up": all_markets[1] if len(all_markets) > 1 else None,
        "three_way_alignment": pick.get("three_way_alignment"),
        "gate_score": pick.get("gate_score"),
        "gate_details": pick.get("gate_details"),
    }

    # Thresholds applied
    thresholds = {
        "min_safety_score": 0.55,  # from config
        "min_gate_score": 10,
        "min_margin": 0.05,
        "ev_threshold": 0.0,
    }

    # What would flip the decision
    flip_conditions = _compute_flip_conditions(best, all_markets)

    return DecisionSnapshot(
        id=None,
        bet_id=bet_id,
        fixture_id=fixture_id,
        betting_date=betting_date,
        chosen_market=best.get("name", ""),
        chosen_line=best.get("line"),
        chosen_direction=best.get("direction", ""),
        safety_score=best.get("safety_score"),
        all_markets_considered_json=all_markets,
        reasoning_json=reasoning,
        thresholds_json=thresholds,
        flip_conditions_json=flip_conditions,
        team_a_snapshot_json=raw.get("team_a_l10", {}),
        team_b_snapshot_json=raw.get("team_b_l10", {}),
        h2h_snapshot_json=raw.get("h2h_meetings", {}),
        three_way_check_json=analysis.get("three_way_check_json"),
        created_at=_NOW(),
    )
```

2. Add `_compute_flip_conditions()` helper:

```python
def _compute_flip_conditions(best_market: dict, all_markets: list) -> dict:
    """Compute what changes would have flipped the decision."""
    flip = {}

    # Safety score gap to #2
    if len(all_markets) >= 2:
        gap = (best_market.get("safety_score", 0) or 0) - (all_markets[1].get("safety_score", 0) or 0)
        flip["safety_gap_to_runner_up"] = round(gap, 3)
        flip["runner_up_market"] = all_markets[1].get("name", "")

    # What L10 average would have made this UNDER the line
    line = best_market.get("line")
    combined_avg = best_market.get("combined_avg")
    if line and combined_avg and best_market.get("direction") == "OVER":
        flip["l10_avg_flip_threshold"] = line  # if avg dropped below line, direction flips
        flip["current_margin_over_line"] = round(combined_avg - line, 2)

    return flip
```

3. Before saving the bet, fetch `analysis_raw_data` for the fixture and attach to the pick dict so the snapshot has full data.

4. Populate `bets.stats_detail` with a compact version:

```python
stats_detail = {
    "safety_score": best.get("safety_score"),
    "l10_avg": best.get("combined_avg"),
    "h2h_avg": best.get("h2h_avg"),
    "hit_rate_l10": best.get("hit_rate_l10"),
    "three_way": pick.get("three_way_alignment"),
    "margin": best.get("margin"),
    "markets_evaluated": pick.get("market_count"),
    "rank": best.get("rank", 1),
}
```

**Definition of Done:**
- [ ] Every bet created by coupon_builder has a corresponding `decision_snapshots` row
- [ ] `bets.stats_detail` is populated with key decision metrics (no longer NULL)
- [ ] `decision_snapshots.flip_conditions_json` shows safety gap and margin info
- [ ] `decision_snapshots.reasoning_json` explains why the market was chosen
- [ ] Coupon builder loads `analysis_raw_data` for the fixture (DB read) and includes in snapshot

---

### Task 2.3 — Add db_data_loader functions for new tables [MODIFY]

**File:** `scripts/db_data_loader.py`

Add functions:

```python
def load_analysis_raw_data(fixture_id: int, betting_date: str) -> dict | None:
    """Load full raw analysis data for a fixture."""

def save_decision_snapshot(snapshot_data: dict) -> bool:
    """Save a decision snapshot after bet creation."""

def save_decision_outcome(outcome_data: dict) -> bool:
    """Save a decision outcome after settlement."""

def load_decision_outcomes(sport: str = None, market: str = None, limit: int = 100) -> list[dict]:
    """Load decision outcomes for learning queries."""

def get_deviation_stats(sport: str = None, market: str = None, competition: str = None) -> dict:
    """Get aggregate deviation statistics for learning."""
```

**Definition of Done:**
- [ ] All functions follow DB-first pattern (try DB, handle exceptions gracefully)
- [ ] Functions use parameterized queries (no string interpolation)
- [ ] Return types are plain dicts (not models) for script compatibility

---

## 5. Phase 3: Outcome Evaluation

### Task 3.1 — Create evaluate_decisions.py [CREATE]

**File:** `scripts/evaluate_decisions.py`

**Purpose:** After settlement, for each settled bet, fetch actual match stats and compare to prediction.

**Logic:**

```python
def evaluate_settled_bets(betting_date: str) -> list[dict]:
    """For each settled bet on the given date, create a decision_outcome."""
    
    # 1. Load settled bets for the date
    settled_bets = load_settled_bets(betting_date)
    
    outcomes = []
    for bet in settled_bets:
        # 2. Load the decision snapshot for this bet
        snapshot = load_decision_snapshot(bet["id"])
        if not snapshot:
            continue
        
        # 3. Fetch actual match stats from match_stats table
        actual_stats = load_actual_match_stats(bet["fixture_id"])
        
        # 4. Extract the actual value for the chosen market
        actual_value = extract_actual_value(
            actual_stats,
            snapshot["chosen_market"],
            snapshot["chosen_line"],
            bet["sport"],
        )
        
        # 5. Compute deviation
        predicted_value = extract_predicted_value(snapshot)
        deviation = actual_value - predicted_value if actual_value and predicted_value else None
        deviation_pct = (deviation / predicted_value * 100) if deviation and predicted_value else None
        
        # 6. Generate pattern tags
        pattern_tags = generate_pattern_tags(
            sport=bet["sport"],
            market=snapshot["chosen_market"],
            competition=bet.get("competition", ""),
            deviation_pct=deviation_pct,
            result=bet["status"],
        )
        
        # 7. Build prediction accuracy breakdown
        prediction_accuracy = {
            "predicted_l10_avg": predicted_value,
            "predicted_h2h_avg": snapshot.get("h2h_snapshot_json", {}).get("averages", {}).get(snapshot["chosen_market"]),
            "predicted_safety_score": snapshot.get("safety_score"),
            "actual_value": actual_value,
            "line": snapshot["chosen_line"],
            "direction": snapshot["chosen_direction"],
            "line_hit": _did_line_hit(actual_value, snapshot["chosen_line"], snapshot["chosen_direction"]),
        }
        
        # 8. Save outcome
        outcome = DecisionOutcome(
            id=None,
            bet_id=bet["id"],
            fixture_id=bet["fixture_id"],
            betting_date=betting_date,
            sport=bet["sport"],
            competition=bet.get("competition", ""),
            market=snapshot["chosen_market"],
            line=snapshot["chosen_line"],
            direction=snapshot["chosen_direction"],
            predicted_value=predicted_value,
            actual_value=actual_value,
            deviation=deviation,
            deviation_pct=deviation_pct,
            result=bet["status"],
            prediction_accuracy_json=prediction_accuracy,
            pattern_tags_json=pattern_tags,
            created_at=_NOW(),
        )
        save_decision_outcome(outcome)
        outcomes.append(outcome)
    
    return outcomes
```

**Helper: `extract_actual_value()`**

For combined markets (corners, fouls, etc.): sum both teams' actual stat values.  
For team-specific markets: use the relevant team's value.

```python
def extract_actual_value(match_stats: dict, market: str, line: float, sport: str) -> float | None:
    """Extract the actual match value for a market from match_stats data.
    
    match_stats: {team_id: {stat_key: value}}
    market: e.g., "corners", "fouls", "total_games"
    """
    # Map market name to stat_key
    stat_key = MARKET_TO_STAT_KEY.get(market, market)
    
    # Sum both teams for combined markets
    total = 0.0
    found = False
    for team_id, stats in match_stats.items():
        if stat_key in stats:
            total += stats[stat_key]
            found = True
    
    return total if found else None
```

**Helper: `generate_pattern_tags()`**

```python
def generate_pattern_tags(sport, market, competition, deviation_pct, result) -> list[str]:
    """Generate searchable pattern tags for learning queries."""
    tags = [sport, market]
    if competition:
        tags.append(competition)
    if result:
        tags.append(result)
    if deviation_pct is not None:
        if deviation_pct > 15:
            tags.append("overestimate_large")
        elif deviation_pct > 5:
            tags.append("overestimate_small")
        elif deviation_pct < -15:
            tags.append("underestimate_large")
        elif deviation_pct < -5:
            tags.append("underestimate_small")
        else:
            tags.append("accurate")
    return tags
```

**CLI interface:**

```
python3 scripts/evaluate_decisions.py --date 2026-05-01
python3 scripts/evaluate_decisions.py --date 2026-05-01 --verbose
```

**Definition of Done:**
- [ ] Script evaluates all settled bets for a given date
- [ ] Creates `decision_outcomes` row for each settled bet that has a decision_snapshot
- [ ] Gracefully skips bets without snapshots (pre-existing data)
- [ ] Gracefully handles missing actual stats (sets actual_value=None, notes reason)
- [ ] `--verbose` flag prints per-bet comparison
- [ ] Idempotent: re-running doesn't create duplicate outcomes (UNIQUE constraint on bet_id)

---

### Task 3.2 — Hook evaluate_decisions into settlement [MODIFY]

**File:** `scripts/settle_on_finish.py`

**Changes:**

After the settlement loop completes and bets are marked won/lost, call:

```python
from evaluate_decisions import evaluate_settled_bets

# After all bets settled for this day:
try:
    outcomes = evaluate_settled_bets(betting_day)
    if outcomes:
        log(f"[evaluate] Created {len(outcomes)} decision outcomes")
except Exception as e:
    log(f"[evaluate] Decision evaluation failed (non-blocking): {e}")
```

This should be non-blocking — settlement success doesn't depend on evaluation.

**Definition of Done:**
- [ ] Settlement still works even if evaluate_decisions fails
- [ ] After successful settlement, decision_outcomes are created automatically
- [ ] Log message confirms evaluation ran

---

### Task 3.3 — Fetch actual match stats for settled fixtures [MODIFY/CREATE]

**File:** `scripts/evaluate_decisions.py` (included in Task 3.1)

The `load_actual_match_stats()` function should:

1. First check `match_stats` table for the fixture_id
2. If found, return `{team_id: {stat_key: stat_value}}`
3. If not found, attempt to fetch from Flashscore/Sofascore (reuse patterns from settle_on_finish.py)
4. Store fetched stats in `match_stats` for future use

**Stat key mapping (market → stat_key):**

```python
MARKET_TO_STAT_KEY = {
    "corners": "corners",
    "Corners Total O/U": "corners",
    "fouls": "fouls",
    "Fouls Total O/U": "fouls",
    "cards": "yellow_cards",
    "Cards Total O/U": "yellow_cards",
    "shots": "shots",
    "Shots Total O/U": "shots",
    "total_games": "games_won",
    "Total Games O/U": "games_won",
    "total_points": "points",
    "Total Points O/U": "points",
    # ... extend per sport
}
```

**Definition of Done:**
- [ ] For every settled bet with a `decision_snapshots` row, attempt to fetch actual stats
- [ ] match_stats table is populated with actual values (reusable for future evaluations)
- [ ] Missing stats don't crash the evaluation (log warning, set actual_value=None)

---

## 6. Phase 4: Learning Queries

### Task 4.1 — Enhance historical_learning.py with decision-based queries [MODIFY]

**File:** `scripts/historical_learning.py`

**Add new function `analyze_decision_accuracy()`:**

```python
def analyze_decision_accuracy():
    """Query decision_outcomes for systematic prediction biases."""
    
    # Load all outcomes
    outcomes = load_decision_outcomes()
    if not outcomes:
        print("[learning] No decision outcomes available yet")
        return
    
    print("=" * 70)
    print("§ DECISION ACCURACY ANALYSIS")
    print("=" * 70)
    
    # 1. Overall accuracy
    with_values = [o for o in outcomes if o["actual_value"] is not None and o["predicted_value"] is not None]
    print(f"\nOutcomes with actual data: {len(with_values)}/{len(outcomes)}")
    
    if with_values:
        avg_dev = sum(o["deviation"] for o in with_values) / len(with_values)
        avg_dev_pct = sum(o["deviation_pct"] for o in with_values) / len(with_values)
        print(f"Average deviation: {avg_dev:+.2f} (actual - predicted)")
        print(f"Average deviation %: {avg_dev_pct:+.1f}%")
    
    # 2. By sport
    print(f"\n── DEVIATION BY SPORT ──")
    sports = set(o["sport"] for o in with_values)
    for sport in sorted(sports):
        sport_outcomes = [o for o in with_values if o["sport"] == sport]
        avg = sum(o["deviation"] for o in sport_outcomes) / len(sport_outcomes)
        avg_pct = sum(o["deviation_pct"] for o in sport_outcomes) / len(sport_outcomes)
        n = len(sport_outcomes)
        print(f"  {sport:<15} n={n:>3}  avg_dev={avg:+.2f}  avg_dev%={avg_pct:+.1f}%")
    
    # 3. By market
    print(f"\n── DEVIATION BY MARKET ──")
    markets = set(o["market"] for o in with_values)
    for market in sorted(markets):
        market_outcomes = [o for o in with_values if o["market"] == market]
        avg = sum(o["deviation"] for o in market_outcomes) / len(market_outcomes)
        avg_pct = sum(o["deviation_pct"] for o in market_outcomes) / len(market_outcomes)
        n = len(market_outcomes)
        won = sum(1 for o in market_outcomes if o["result"] == "won")
        print(f"  {market:<20} n={n:>3}  avg_dev={avg:+.2f}  avg_dev%={avg_pct:+.1f}%  won={won}/{n}")
    
    # 4. By sport×market (key insight)
    print(f"\n── DEVIATION BY SPORT × MARKET (n≥3) ──")
    from collections import defaultdict
    sport_market = defaultdict(list)
    for o in with_values:
        sport_market[(o["sport"], o["market"])].append(o)
    for (sport, market), group in sorted(sport_market.items()):
        if len(group) < 3:
            continue
        avg = sum(o["deviation"] for o in group) / len(group)
        avg_pct = sum(o["deviation_pct"] for o in group) / len(group)
        n = len(group)
        flag = " ⚠️ BIAS" if abs(avg_pct) > 10 else ""
        print(f"  {sport}×{market:<15} n={n:>3}  avg_dev%={avg_pct:+.1f}%{flag}")
    
    # 5. By competition (league-level insights)
    print(f"\n── DEVIATION BY COMPETITION (n≥3) ──")
    comp_groups = defaultdict(list)
    for o in with_values:
        if o.get("competition"):
            comp_groups[o["competition"]].append(o)
    for comp, group in sorted(comp_groups.items(), key=lambda x: -len(x[1])):
        if len(group) < 3:
            continue
        avg_pct = sum(o["deviation_pct"] for o in group) / len(group)
        n = len(group)
        flag = " ⚠️ BIAS" if abs(avg_pct) > 10 else ""
        print(f"  {comp:<30} n={n:>3}  avg_dev%={avg_pct:+.1f}%{flag}")
```

**Add to CLI:**

```python
if __name__ == "__main__":
    analyze_picks()
    analyze_coupons()
    analyze_decision_accuracy()  # NEW
```

**Definition of Done:**
- [ ] Running `historical_learning.py` now includes decision accuracy section
- [ ] Shows deviation by sport, market, sport×market, and competition
- [ ] Flags systematic biases (>10% average deviation) with ⚠️
- [ ] Gracefully handles zero outcomes (prints "no data yet")

---

### Task 4.2 — Add learning query API to db_data_loader [MODIFY]

**File:** `scripts/db_data_loader.py`

Add convenience functions for querying learning data from other scripts:

```python
def get_market_bias(sport: str, market: str) -> dict | None:
    """Get the average prediction bias for a sport×market combination.
    
    Returns: {
        "count": int,
        "avg_deviation": float,
        "avg_deviation_pct": float,
        "direction": "overestimate" | "underestimate" | "accurate",
        "confidence": "high" | "medium" | "low",  # based on sample size
    }
    """

def get_league_adjustment(competition: str, market: str) -> float | None:
    """Get suggested adjustment factor for a league.
    
    Returns the average deviation_pct as a correction factor.
    E.g., if La Liga corners are overestimated by 12%, returns -0.12
    Only returns if n≥5 outcomes exist.
    """

def get_team_pair_history(home_team: str, away_team: str) -> list[dict]:
    """Get all decision outcomes for a specific team pairing.
    
    Returns list of past outcomes showing prediction vs actual for this matchup.
    """
```

These functions are **advisory only** (per user memory: betclic-learning-advisory-only.md). They provide data for display to the user but MUST NOT auto-reject or auto-penalize picks.

**Definition of Done:**
- [ ] `get_market_bias()` returns bias data or None if insufficient samples
- [ ] `get_league_adjustment()` only returns when n≥5 (avoids noisy small samples)
- [ ] `get_team_pair_history()` returns empty list if no prior outcomes
- [ ] All functions are read-only queries (no side effects)
- [ ] Functions return None/empty gracefully if DB unavailable

---

## 7. Security Considerations

1. **SQL Injection Prevention** — All new queries MUST use parameterized `?` placeholders. No string interpolation for any user-provided or data-derived values.

2. **Data Integrity** — Foreign key constraints (`REFERENCES`) ensure orphan prevention. `UNIQUE` constraints prevent duplicate outcomes.

3. **JSON Validation** — On read, `json.loads()` calls should be wrapped in try/except to handle corrupted data gracefully.

4. **No PII Storage** — Tables store only statistical/betting data. No personal information.

---

## 8. Quality Assurance

### Automated Testing Strategy

1. **Unit tests for new repos** — Test each repository method with an in-memory SQLite DB:
   - `tests/test_decision_repos.py` — CRUD operations for all 3 new repos
   - Test edge cases: NULL values, empty JSON, duplicate inserts

2. **Integration test for evaluate_decisions** — End-to-end test:
   - Create fixture → analysis → bet → settle → evaluate
   - Assert decision_outcome has correct deviation calculation

3. **Regression test for existing pipeline** — Ensure:
   - `deep_stats_report.py` still produces same analysis_results output
   - `coupon_builder.py` still creates valid coupons
   - `settle_on_finish.py` still settles correctly

### Test file:

```
[CREATE] tests/test_decision_learning.py
```

Contents:
- `test_analysis_raw_data_save_load()` — round-trip save/load
- `test_decision_snapshot_creation()` — verify all fields populated
- `test_decision_outcome_deviation()` — verify math (actual - predicted)
- `test_pattern_tags_generation()` — verify tag logic
- `test_deviation_stats_aggregation()` — verify SQL aggregation
- `test_idempotent_outcome_creation()` — verify UNIQUE prevents duplicates
- `test_missing_actual_stats_handled()` — verify graceful degradation

**Definition of Done for all tests:**
- [ ] Tests run with `pytest tests/test_decision_learning.py`
- [ ] Tests use in-memory SQLite (`:memory:`) — no file system dependencies
- [ ] All tests pass on clean state

---

## 9. Summary — Execution Order

| Phase | Task | File | Action | Priority |
|-------|------|------|--------|----------|
| 1 | 1.1 | `src/bet/db/migrations/003_decision_learning.sql` | CREATE | P0 |
| 1 | 1.2 | `src/bet/db/schema.sql` | MODIFY | P0 |
| 1 | 1.3 | `src/bet/db/models.py` | MODIFY | P0 |
| 1 | 1.4 | `src/bet/db/repositories.py` | MODIFY | P0 |
| 1 | 1.5 | `scripts/migrate_data.py` | MODIFY | P0 |
| 2 | 2.1 | `scripts/deep_stats_report.py` | MODIFY | P1 |
| 2 | 2.2 | `scripts/coupon_builder.py` | MODIFY | P1 |
| 2 | 2.3 | `scripts/db_data_loader.py` | MODIFY | P1 |
| 3 | 3.1 | `scripts/evaluate_decisions.py` | CREATE | P2 |
| 3 | 3.2 | `scripts/settle_on_finish.py` | MODIFY | P2 |
| 3 | 3.3 | (included in 3.1) | — | P2 |
| 4 | 4.1 | `scripts/historical_learning.py` | MODIFY | P3 |
| 4 | 4.2 | `scripts/db_data_loader.py` | MODIFY | P3 |
| — | — | `tests/test_decision_learning.py` | CREATE | P1 |

**Dependencies:**
- Phase 2 requires Phase 1 complete (tables must exist)
- Phase 3 requires Phase 2 complete (snapshots must be populated to evaluate)
- Phase 4 requires Phase 3 complete (outcomes must exist to query)
- Tests can be written alongside each phase

---

## 10. JSON Column Schema Reference

### `analysis_raw_data.team_a_l10_json`
```json
{
  "team": "Liverpool",
  "l10_avg": {"corners": 5.8, "fouls": 12.3, "shots": 14.2},
  "l5_avg": {"corners": 6.2, "fouls": 11.8, "shots": 15.0},
  "l10_matches": [
    {"date": "2026-04-28", "opponent": "Arsenal", "corners": 7, "fouls": 11, "shots": 16},
    {"date": "2026-04-21", "opponent": "Chelsea", "corners": 5, "fouls": 14, "shots": 12}
  ],
  "sources": ["flashscore", "sofascore"]
}
```

### `analysis_raw_data.per_market_details_json`
```json
[
  {
    "name": "corners",
    "line": 9.5,
    "direction": "OVER",
    "safety_score": 0.85,
    "combined_avg": 11.2,
    "h2h_avg": 10.5,
    "hit_rate_l10": "8/10",
    "hit_rate_h2h": "6/8",
    "margin": 0.18,
    "three_way_check": {"l10_avg": 11.2, "h2h_avg": 10.5, "l5_avg": 12.0, "alignment": "ALL_SUPPORT"},
    "one_sided": false,
    "h2h_blind": false
  },
  {
    "name": "fouls",
    "line": 22.5,
    "direction": "OVER",
    "safety_score": 0.72,
    "...": "..."
  }
]
```

### `decision_snapshots.reasoning_json`
```json
{
  "chosen_because": "Highest safety score (0.85) among 6 evaluated markets",
  "runner_up": {"name": "fouls", "line": 22.5, "safety_score": 0.72},
  "three_way_alignment": "3/3 ALL_SUPPORT",
  "gate_score": 14,
  "gate_details": {"pass_points": ["EV>0", "safety≥0.55", "3-way aligned"]}
}
```

### `decision_snapshots.flip_conditions_json`
```json
{
  "safety_gap_to_runner_up": 0.13,
  "runner_up_market": "fouls",
  "l10_avg_flip_threshold": 9.5,
  "current_margin_over_line": 1.7
}
```

### `decision_outcomes.prediction_accuracy_json`
```json
{
  "predicted_l10_avg": 11.2,
  "predicted_h2h_avg": 10.5,
  "predicted_safety_score": 0.85,
  "actual_value": 8.0,
  "line": 9.5,
  "direction": "OVER",
  "line_hit": false
}
```

### `decision_outcomes.pattern_tags_json`
```json
["football", "corners", "Premier League", "lost", "overestimate_large"]
```
