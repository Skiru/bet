# Routing Matrix

Use this map when a prompt needs to decide which specialist should handle finished output.

| Intent | Delegate to | Load with it | Notes |
| --- | --- | --- | --- |
| Settlement and bankroll | `bet-settler` | `bet-settling-results`, `bet-formatting-artifacts` | Resolve the previous betting day and learning summary.
| Discovery and shortlist | `bet-scanner` | `bet-navigating-sources` | Build the event pool, then hand off the shortlist.
| Tipster intelligence | `bet-scout` | `bet-navigating-sources` | Use when the question is about opinions, consensus, or argument quality.
| Enrichment and data gaps | `bet-enricher` | `bet-navigating-sources`, `bet-analyzing-statistics` | Use when the issue is coverage, freshness, or bridge visibility.
| Deep statistics | `bet-statistician` | `bet-analyzing-statistics`, `bet-applying-sport-protocols`, `bet-navigating-sources` | Use for S3 and S3B analysis.
| Odds and EV | `bet-valuator` | `bet-evaluating-odds`, `bet-navigating-sources` | Use for pricing, drift, and Kelly staking.
| Context and upset risk | `bet-challenger` | `bet-applying-sport-protocols`, `bet-analyzing-statistics`, `bet-navigating-sources` | Use for S5, S6, and the final gate.
| Portfolio and coupons | `bet-builder` | `bet-building-coupons`, `bet-formatting-artifacts` | Use for S8 and S9.
| DB quality | `bet-db-analyst` | `bet-querying-database` | Use when the pipeline needs readiness or gap triage.
| Time-sensitive recheck | `bet-statistician` | `bet-analyzing-statistics`, `bet-applying-sport-protocols` | Use for late lineups, injuries, weather, or drift.

## Routing Rule

If a task spans more than one intent, pick the primary owner first, then pass the finished output to the secondary specialist with the same handoff contract.