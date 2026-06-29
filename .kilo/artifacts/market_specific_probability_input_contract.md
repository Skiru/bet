# Market-Specific Probability Input Contract

## Schema

```text
MarketProbabilityInput:
  candidate_id: Unique string identifier for the candidate
  sport: Sport name (e.g. "football")
  market_family: Market family mapping (e.g. "GOALS_TOTALS")
  market_type: Sub-market name/type (e.g. "Goals Total O/U")
  selection: Pick outcome name
  direction: OVER or UNDER
  line: Optional numeric line threshold
  team_a_name: Canonical home team name
  team_b_name: Canonical away team name
  team_a_l10: List of Team A's L10 stat occurrences
  team_b_l10: List of Team B's L10 stat occurrences
  h2h_l5: Optional list of H2H stat occurrences
  source_artifact_path: Source file or DB path
  stats_as_of: Timestamp of statistics extraction
  sample_size: Maximum of Team A / Team B sample sizes
  missing_fields: List of missing fields
```

## Validation & Sizing Rules

- **Combined Markets (`GOALS_TOTALS`, `CORNERS`, `CARDS`, `SHOTS`, `SHOTS_ON_TARGET`)**: Require numeric L10 series for BOTH home and away sides.
- **Result Market (`RESULT`)**: Requires goals-for/goals-against or W/D/L form for BOTH home and away sides.
- **Line Enforcement**: If a market family requires a line (all families except `RESULT`), and it is missing, classify `LINE_MISSING`.
- **Sample Size Enforcement**: If the active series length < 5, classify `INSUFFICIENT_SAMPLE_SIZE`.
- **No Odds Manipulation**: No market probability input may be created from bookmaker odds alone.
- **Unsupported Markets**: `player_tackles` and other player props remain blocked and unsupported by the engine.
