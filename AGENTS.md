# Agent contract

The working agreement for this repository lives in **[`CLAUDE.md`](CLAUDE.md)**
and is tool-agnostic: read it first, whatever agent runtime you are.

Two things to know before anything else:

1. **The only pipeline in service is `sofa`** — Sofascore statistics, Superbet
   prices, football and tennis, and the product of a day is
   `runs/sofa/<date>/KUPON_<date>.pdf`. Stages:
   `BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON`, then
   `CONFIDENCE` and the PDF; `SETTLE` and `FIT` are deliberately outside the
   daily sequence.
2. **There is no `DISCOVER`, `ENRICH`, `ANALYZE`, `MARKET_CONTEXT` or
   `TIPSTERS` stage.** Those belong to the retired `simple` pipeline
   (`docs/legacy/`). The two share no code and no vocabulary.

| | |
|---|---|
| orchestration: agents, commands, skills, handoffs | [`docs/sofa/AGENTIC_FLOW.md`](docs/sofa/AGENTIC_FLOW.md) |
| the pipeline in full detail | [`docs/sofa/PIPELINE.md`](docs/sofa/PIPELINE.md) |
| running a day | [`docs/sofa/RUNBOOK.md`](docs/sofa/RUNBOOK.md) |
| verifying a built day | [`docs/sofa/VERIFY_PROTOCOL.md`](docs/sofa/VERIFY_PROTOCOL.md) |
| constants and the calibration loop | [`docs/sofa/CONFIG.md`](docs/sofa/CONFIG.md) |
| where the code lives | [`ARCHITECTURE.md`](ARCHITECTURE.md) |

Runtime configuration: Claude Code loads `.claude/agents`, `.claude/commands`
and `.claude/skills`. Kilocode's configuration drove the retired pipeline and
is parked, unloaded, in `.kilo/legacy/`.
