# Agent contract

The working agreement for this repository lives in **[`CLAUDE.md`](CLAUDE.md)**
and is tool-agnostic: read it first, whatever agent runtime you are.

Two things to know before anything else:

1. **The only pipeline in service is `sofa`** — Sofascore statistics, Superbet
   prices, and the product of a day is **one coupon**,
   `runs/sofa/<date>/KUPON_<date>.pdf`: football and tennis, and since
   2026-10-05 08:30Z hockey, basketball, volleyball and CS2. Stages:
   `BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON`, then
   `CONFIDENCE` (`08_confidence.json`); `SPORT_IDENTITY` and
   `SPORT_CONFIDENCE` (`08_confidence_sports.json`) for the measured sports;
   `COUPON_ASSEMBLY` (`11_coupon.json`, the one coupon artifact) and the PDF
   (which writes `12_printed.json`); `FIXTURE_CHECK` in a rebuild before
   CONFIDENCE. `SETTLE` and `FIT` are deliberately outside the daily
   sequence. Confidence comes from the statistics alone (since 2026-10-05
   07:15Z); the price is only the betting condition. Retired 2026-10-05:
   WARIANT and WARIANT WSZYSTKIE (07:15Z) and the separate sport coupons
   (08:30Z); their files up to that morning stay and are graded as before.
2. **There is no `DISCOVER`, `ENRICH`, `ANALYZE`, `MARKET_CONTEXT` or
   `TIPSTERS` stage.** Those belong to the retired `simple` pipeline
   (deleted from the repository 2026-10-05). The two share no vocabulary.

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
was deleted with it (2026-10-05).
