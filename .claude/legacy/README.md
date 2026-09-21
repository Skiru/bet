# `.claude/legacy` — the `simple` pipeline's agentic configuration

Everything in this directory drove **`simple`** (`scripts/simple/`,
`src/bet/simple_stats/`): DISCOVER → SUPERBET → ENRICH → MARKET_CONTEXT →
TIPSTERS → ANALYZE, artifacts in `runs/<date>/`, product `<date>_kupony.md`.

It is parked here, not deleted, and it is **not loaded**: Claude Code discovers
agents in `.claude/agents/`, commands in `.claude/commands/` and skills in
`.claude/skills/`, and none of those paths reach into `legacy/`.

The pipeline in current use is **`sofa`** (`scripts/sofa/`, `src/bet/sofa/`):
BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON, then CONFIDENCE and
the PDF. It shares **zero code** with `simple` and none of its stage names. See
`docs/sofascore-api/RUNBOOK.md`.

## What was parked, and what replaced it

| parked | why | replacement |
|---|---|---|
| `agents/bet-simple.md` | ran `scripts/simple/run_pipeline.py`, orchestrated DISCOVER/ENRICH/ANALYZE | `.claude/agents/sofa-runner.md` |
| `agents/bet-analyst-football.md` | read `runs/<date>/*_event_dossiers*`, ranked by `p_low` | `.claude/agents/sofa-analyst-football.md` |
| `agents/bet-analyst-tennis.md` | same, tennis | `.claude/agents/sofa-analyst-tennis.md` |
| `agents/bet-analyst-baseball.md` | MLB via `espn-baseball` | **nothing.** `sofa` is football and tennis only: `SPORT_IDS = {"football": 5, "tennis": 2}` in `src/bet/sofa/superbet.py`, and `Sport` in `contracts.py` admits no third value. A baseball analyst under `sofa` would have no rows to read. |
| `agents/tipster-reader.md` | read the TIPSTERS stage's picks | **nothing.** `sofa` has no TIPSTERS stage and ingests no third-party opinion. |
| `agents/superbet-market-matcher.md` | joined `simple` rows to Superbet's screen, priced comparative markets offline | `.claude/agents/sofa-market-scout.md` — narrower, because `sofa` now generates the derived markets itself (`both_over_*`, `handicap_*`, `most_*` in `src/bet/sofa/derived.py`) |
| `commands/run-day.md` | `/run-day` | `/sofa-day` |
| `commands/rebuild-coupon.md` | `/rebuild-coupon` | `/sofa-rebuild` |
| `skills/bet-analysis-core/` | the analyst contract over `simple` artifacts and `p_low` | `.claude/skills/sofa-analysis-core/` |
| `skills/baseball-analysis/` | MLB runs markets | **nothing** — see above |

`football-analysis` and `tennis-analysis` kept their names and stayed in
`.claude/skills/`: the *method* (surface, format, referee, game script,
distribution over mean, price last) is a property of the sport, not of the
pipeline. Their data references were rewritten for `sofa` artifacts and market
names, so the agents parked here can no longer be run against them unchanged.

## Restoring one

```bash
git mv .claude/legacy/agents/<name>.md .claude/agents/
```

Then check what it reads. Every one of these files names `simple` artifacts
(`<date>_event_dossiers_stats_sheet.json`, `<date>_superbet_comparison.json`,
`<date>_forecast.json`) and `simple` quantities (`p_low`, tiers
`CALL`/`LEAN`/`WEAK`/`DROP`, `event_id` as a 64-char hash). None of those exist
in `sofa`, where a row is keyed by `sofascore_event_id` (an integer) and ranked
by `p_central` → `p_bar`.
