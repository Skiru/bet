# `.kilo/legacy` — the Kilocode configuration of the retired `simple` pipeline

Everything here drove **`simple`** (`scripts/simple/`, `src/bet/simple_stats/`):
`DISCOVER → SUPERBET → ENRICH → MARKET_CONTEXT → TIPSTERS → ANALYZE`, artifacts
in `runs/<date>/`, product `<date>_kupony.md`. That pipeline is retired.

It is parked here, not deleted, and **it is not loaded**: Kilo discovers agents
in `.kilo/agent/`, commands in `.kilo/command/` and skills in `.kilo/skills/`,
and none of those directories exists any more.

| parked | ran |
|---|---|
| `agent/bet-simple.md` | `scripts/simple/run_pipeline.py`, the whole `simple` day |
| `agent/bet-analyst-football.md`, `-tennis.md`, `-baseball.md` | the per-sport read over `simple` dossiers, ranked by `p_low` |
| `agent/superbet-market-matcher.md` | joined `simple` rows to Superbet's screen |
| `agent/tipster-reader.md` | the TIPSTERS stage — `sofa` ingests no third-party opinion |
| `command/run-day.md`, `command/rebuild-coupon.md` | `/run-day`, `/rebuild-coupon` |
| `skills/simple-stats-runtime/` | the `simple` runtime contract |

## The current pipeline is `sofa`, and it is configured for Claude Code

`sofa` (`scripts/sofa/`, `src/bet/sofa/`) shares **zero code and zero stage
names** with `simple`. Its agentic configuration lives in `.claude/`:

| | |
|---|---|
| commands | `/sofa-day`, `/sofa-analyze`, `/sofa-rebuild`, `/sofa-verify`, `/sofa-settle` |
| agents | `sofa-runner`, `sofa-analyst-football`, `sofa-analyst-tennis`, `sofa-verifier`, `sofa-settler`, `sofa-market-scout` |
| skills | `sofa-pipeline`, `sofa-analysis-core`, `football-analysis`, `tennis-analysis`, `bet-slip-audit` |

There is **no Kilo configuration for `sofa`**. Running a `sofa` day from Kilo
would mean porting those files; nothing here is a starting point for that,
because every one of them names `simple` artifacts and `simple` quantities.

Documentation: [`docs/sofa/`](../../docs/sofa/) — start at `PIPELINE.md`.
