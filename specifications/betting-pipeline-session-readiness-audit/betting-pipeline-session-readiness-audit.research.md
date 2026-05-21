# Betting Pipeline Session Readiness Audit - Analysis Result

## Task Details

| Field | Value |
|---|---|
| Jira ID | N/A - prompt-defined cross-repository meta-task |
| Title | Betting pipeline session readiness audit for 2026-05-21 |
| Description | Audit full session readiness of `/Users/mkoziol/projects/bet` across the `.github` customization layer, S0-S10 pipeline scripts, DB/file handoffs, and verification surfaces. Use `/Users/mkoziol/work/copilot-collections` only as a reference baseline for orchestration patterns. No proposed changes or implementation scope live there. |
| Priority | High |
| Reporter | User prompt |
| Created Date | 2026-05-21 |
| Due Date | 2026-05-21 |
| Labels | betting, session-readiness, pipeline, orchestration, db-first, contract-audit |
| Estimated Effort | Research artifact only; implementation planning intentionally deferred |

## Business Impact

The current session does not depend only on whether the orchestrator prompt is well-written. It depends on whether the entire betting workflow can be resumed, validated, and trusted from settlement through coupon delivery without silent producer/consumer mismatches, stale fallback logic, or DB/JSON drift.

The operational question is narrower and more concrete than the previous audit: if a real betting session starts today, can the coordinator safely run S0-S10 using the current repo state? That requires `.github` orchestration truth, script/dataflow truth, and validation truth to agree on the same artifacts, step order, and bucket semantics.

## Gathered Information

### Knowledge Base & Task Management Tools

- No Jira, Confluence, Figma, or PDF artifacts were referenced for this task. The source of truth is the bet repository, the existing research artifact, and repository memory.
- Scope was explicitly corrected to `bet` only. `copilot-collections` is reference-only and was used only to compare orchestration patterns and model-routing discipline.
- Repository memory in `bet/memories/repo/pipeline-knowledge-base.md`, `bet/memories/repo/pipeline-bugs-and-fixes.md`, and `bet/memories/repo/pipeline-lessons-learned.md` confirms recent fixes around orchestration, Betclic validation, rich-stat rollout, and known producer/consumer failures.
- Memory interactions are in scope because the bet prompt/agent layer explicitly loads repo/session memory before orchestration and instructs agents to write session learnings back after runtime work.
- The task is research-only. No code changes, no plan file, and no rollout proposal are part of the requested output.

### Codebase

#### Primary Repository: bet

- The runtime stack is Python 3.11 plus SQLite at `betting/data/betting.db`, with a DB-first plus JSON-fallback pattern across most pipeline scripts.
- Canonical DB access is `src/bet/db/connection.py:get_db()`. Repository coverage is broad: fixtures, scan results, odds history, team form, match stats, analysis results, gate results, coupons, bets, pipeline runs, league profiles, tipster data, standings, rosters, and team news all have repository support.
- The pipeline is not DB-only. JSON artifacts remain operationally important at S1, S1d, S1e, S2, S3, S7, and S8, and some steps intentionally prefer JSON because DB coverage can be narrower than the full working candidate set.
- Session control is split across the `.github` customization layer, Python scripts in `scripts/`, DB repositories in `src/bet/db/`, operational artifacts in `betting/data/`, and memory files under `memories/`.
- Observability is code-backed: `inspect_pipeline.py`, `validate_phase.py`, `verify_scan.py`, `db_report.py`, `agent_protocol.py`, and `agent_output.py` all participate in defining what the coordinator thinks is ready.

#### Reference Repository: copilot-collections

- The reference repo is useful as a baseline for prompt/agent layering, coordinator/worker separation, and explicit model-routing discipline.
- `tsh-research.prompt.md` and related reference artifacts were used to structure this document, but not to define runtime truth.
- The reference repo is not a runtime analog for the betting pipeline. It helps evaluate orchestration artifact quality, but it does not replace direct analysis of bet script contracts or DB/file handoffs.

#### `.github` Customization Layer in bet

- `orchestrate-betting-day.prompt.md` is the current session entry point. It defines official step order, specialist delegation, memory preloads, and validation checkpoints.
- `bet-orchestrator.agent.md` mirrors the prompt with command tables, a script-to-DB matrix, and model/tool declarations.
- Specialist agents and internal prompts are operationally relevant because they shape assumptions about what the orchestrator has already run, what files or DB tables exist, what metrics should be extracted, and what gets written to memory.
- Memory surfaces referenced by the workflow are real: `/memories/repo/pipeline-knowledge-base.md`, `/memories/repo/pipeline-bugs-and-fixes.md`, `/memories/repo/pipeline-lessons-learned.md`, and the latest `/memories/session/` note. These are advisory inputs to orchestration quality, not substitutes for DB/file validation.
- Model routing is inconsistent inside bet itself: agent files hard-pin `Claude Opus 4.6 (Copilot)`, while `agent-execution-protocol.instructions.md` still says execution is driven by `Gemini 3.1 Pro (Preview)`. The current session model baseline is GPT-5.4. This matters for orchestration predictability, but it is not the core dataflow blocker.

#### Concrete End-to-End Pipeline Map (S0-S10)

| Flow | Primary owner / scripts | Main reads | Main writes | Coordinator must validate before proceeding |
|---|---|---|---|---|
| S0 settlement-learning | `settle_on_finish.py`, `analyze_betclic_learning.py`, `evaluate_decisions.py`, `data_rotation.py` | coupons/bets tables, ledgers, `match_stats`, `betclic_bets_history.json` | settled bets/coupons, learning analysis, decision outcomes, cleaned artifacts | Previous day is settled enough to avoid polluting today’s learning and repeat-loss logic. |
| S0.5 readiness diagnostics | `inspect_pipeline.py`, `db_report.py`, `verify_scan.py`, `validate_phase.py` | DB census, data files, state artifacts | stdout/JSON diagnostics only | Use actual DB/file evidence; do not treat missing legacy state files as proof of session failure by themselves. |
| S1 discovery | `discover_events.py`, `src/bet/discovery/coordinator.py` | scan URLs, API feeds, discovery adapters | DB `fixtures`, `scan_results`, `fixture_sources`; `{date}_s1_events.json` | DB fixture counts and `{date}_s1_events.json` represent the same day and sport set. |
| S1-ingest | `ingest_scan_stats.py` | S1 discovery output, scan stats payloads | `stats_cache`, `team_form`, structured summary output | `team_form` and cache were actually updated; do not infer success from scan presence alone. |
| S1a ESPN seed | `seed_espn_data.py` | ESPN endpoints | `standings`, `team_ats_records`, `team_ou_records`, rosters, predictions | Supplemental ESPN tables exist if later context/upset steps are expected to use them. |
| S1b odds, weather, tipsters | `fetch_odds_api.py`, `fetch_odds_api_io.py`, optional `fetch_odds_multi.py`, `fetch_weather.py`, `tipster_aggregator.py` | odds APIs, weather API, tipster sites | `odds_history`, odds snapshots/CSV, `weather_{date}.json`, `tipster_picks`, `tipster_consensus`, JSON fallback files, partial `pipeline_runs` | `odds_history` contains today’s fixtures; tipster consensus exists in DB or JSON; note that `fetch_odds_multi.py` is real but off the official prompt path. |
| S1d market matrix | `generate_market_matrix.py` | fixtures DB, odds DB/snapshots, scan summary, stats cache | `market_matrix_{date}.json`, `market_matrix_{date}.md`, `decision_matrix_{date}.md` | `market_matrix_{date}.json` exists, because `build_shortlist.py` hard-fails without it. |
| S1e shortlist | `build_shortlist.py`, optional `filter_betclic_shortlist.py` | market matrix, fixtures/odds, optional Betclic validation | `{date}_s2_shortlist.json`, `{date}_s2_shortlist.md`, optional bettable shortlist JSON, partial `pipeline_runs` | Downstream steps know which shortlist file is authoritative and whether a Betclic-filtered branch was used. |
| S2 tipster cross-reference | `tipster_xref.py` | shortlist JSON, `TipsterRepo`, JSON fallback tipster data | rewrites the same shortlist JSON with `tipster_support` and `tipster_count` | The in-place shortlist mutation preserved `candidates` structure and did not drop events. |
| S2.3 scrapers | `run_scrapers.py` | scraper registry, modular scraper sources | `league_profiles`, `player_season_stats`, `athletes`, `scraper_runs` | Do not mistake scraper success for `team_form` readiness; S3 still primarily consumes `team_form` and cache. |
| S2.3 bridge helpers | `scraper_to_team_form.py`, `bridge_league_to_team_form.py` | `league_profiles`, fixtures, competitions | baseline `team_form` rows, `AGENT_SUMMARY` | If S2.3 is supposed to improve S3 today, confirm a bridge path ran or accept that S3 still depends mainly on old `team_form` + S2.5. |
| S2.5 enrichment | `data_enrichment_agent.py`, `enrich_tennis_stats.py`, legacy `fetch_api_stats.py` only as deprecated/utility surface | shortlist or DB fixtures, existing `team_form`, caches, fallback chains, optional news enrichment | `team_form`, `match_stats`, `source_health`, `team_news`, structured summary output | Validate actual `team_form`/rich coverage improvement, not just non-zero script logs. |
| S3 deep stats | `deep_stats_report.py` with `normalize_stats.py -> compute_safety_scores.py -> probability_engine.py` | shortlist JSON, `team_form`, `match_stats`, caches, tipster-enriched shortlist | `{date}_s3_deep_stats.json`, `{date}_s3_deep_stats.md`, `analysis_results`, `analysis_raw_data` | JSON and DB candidate counts stay close enough that later DB-first steps do not silently narrow the set. |
| S4 odds / EV | `odds_evaluator.py` | S3 JSON first, DB `analysis_results` fallback, `odds_history` | updates S3 JSON and `analysis_results.stats_summary_json` with EV/odds | EV coverage and candidate parity are known before S5/S6 reuse DB. |
| S5 context | `context_checks.py` | DB `analysis_results` first or S3 JSON if DB empty, `weather_{date}.json`, `team_news`, standings | updates S3 JSON and `analysis_results.stats_summary_json` with `context_flags` | Candidate counts did not silently shrink because DB was only partially populated. |
| S6 upset risk | `upset_risk.py` | DB `analysis_results` first or S3 JSON if DB empty, context flags | updates S3 JSON and `analysis_results.stats_summary_json` with `upset_risk` | Candidate counts still match the intended S4/S5 universe. |
| S7 gate | `gate_checker.py` | `analysis_results` or S3 JSON, S4-S6 enrichments | `{date}_s7_gate_results.json`, `{date}_s7_gate_results.md`, DB `gate_results` | Approved, Extended Pool, and rejected buckets survive the DB/JSON round trip. |
| S7.5 Betclic validation | `validate_betclic_markets.py` | gate/coupon market names, Betclic competition registry, Betclic event pages | `betclic_market_validation_{date}.json`, `betclic_markets`, competition profiles | Output filename and sidecar contract match what `coupon_builder.py` actually loads. |
| S7.6 repeat-loss control | `check_48h_repeats.py` | bets/ledgers/recent losses, team or shortlist inputs | stdout/JSON only, no durable artifact | Coordinator must carry flags forward explicitly because S8 does not ingest them itself. |
| S8 build | `coupon_builder.py` | gate results DB first then JSON fallback, Betclic validation sidecar, config, tipster DB fallback | coupon markdown/JSON, DB coupons/bets/decision snapshots | Core and Extended Pool survive the chosen load path; Betclic validation is actually attached if required. |
| S9 validate | `validate_coupons.py` | coupon files, ledgers | stdout / `AGENT_SUMMARY` validation only | Validation passes and its result is captured for the final session verdict. |
| S10 delivery | `generate_coupon_pdf.py` | coupon markdown and optional JSON | PDF outputs under `betting/coupons/pdf/{date}/` | If S10 is part of today’s session definition, PDFs must exist; the current build gate does not enforce that. |

Additional diagnostic layer:

- `inspect_pipeline.py` is the strongest current read-only state inspector because it checks actual DB/files per step and rich coverage without assuming a single orchestration path.
- `validate_phase.py` is useful but partially legacy: it mixes current DB/file checks with hard requirements on legacy `pipeline_state` files and older step IDs.
- `verify_scan.py` is a targeted scan-quality verifier outside the official prompt flow.
- `db_report.py`, `agent_protocol.py`, and `agent_output.py` expose the intended DB schema and structured-output contracts, but parts of those declared contracts lag the runtime state.

### Relevant Links

- `/Users/mkoziol/projects/bet/.github/copilot-instructions.md`
- `/Users/mkoziol/projects/bet/.github/prompts/orchestrate-betting-day.prompt.md`
- `/Users/mkoziol/projects/bet/.github/agents/bet-orchestrator.agent.md`
- `/Users/mkoziol/projects/bet/.github/internal-prompts/bet-tipsters.prompt.md`
- `/Users/mkoziol/projects/bet/.github/internal-prompts/bet-enrich.prompt.md`
- `/Users/mkoziol/projects/bet/scripts/agent_protocol.py`
- `/Users/mkoziol/projects/bet/scripts/agent_output.py`
- `/Users/mkoziol/projects/bet/src/bet/db/connection.py`
- `/Users/mkoziol/projects/bet/src/bet/db/repositories.py`
- `/Users/mkoziol/projects/bet/scripts/db_data_loader.py`
- `/Users/mkoziol/projects/bet/scripts/discover_events.py`
- `/Users/mkoziol/projects/bet/scripts/verify_scan.py`
- `/Users/mkoziol/projects/bet/scripts/ingest_scan_stats.py`
- `/Users/mkoziol/projects/bet/scripts/generate_market_matrix.py`
- `/Users/mkoziol/projects/bet/scripts/build_shortlist.py`
- `/Users/mkoziol/projects/bet/scripts/filter_betclic_shortlist.py`
- `/Users/mkoziol/projects/bet/scripts/tipster_aggregator.py`
- `/Users/mkoziol/projects/bet/scripts/tipster_xref.py`
- `/Users/mkoziol/projects/bet/scripts/run_scrapers.py`
- `/Users/mkoziol/projects/bet/scripts/scraper_to_team_form.py`
- `/Users/mkoziol/projects/bet/scripts/bridge_league_to_team_form.py`
- `/Users/mkoziol/projects/bet/scripts/data_enrichment_agent.py`
- `/Users/mkoziol/projects/bet/scripts/enrich_tennis_stats.py`
- `/Users/mkoziol/projects/bet/scripts/fetch_api_stats.py`
- `/Users/mkoziol/projects/bet/scripts/deep_stats_report.py`
- `/Users/mkoziol/projects/bet/scripts/normalize_stats.py`
- `/Users/mkoziol/projects/bet/scripts/compute_safety_scores.py`
- `/Users/mkoziol/projects/bet/scripts/probability_engine.py`
- `/Users/mkoziol/projects/bet/scripts/fetch_odds_api.py`
- `/Users/mkoziol/projects/bet/scripts/fetch_odds_api_io.py`
- `/Users/mkoziol/projects/bet/scripts/fetch_odds_multi.py`
- `/Users/mkoziol/projects/bet/scripts/odds_evaluator.py`
- `/Users/mkoziol/projects/bet/scripts/context_checks.py`
- `/Users/mkoziol/projects/bet/scripts/upset_risk.py`
- `/Users/mkoziol/projects/bet/scripts/gate_checker.py`
- `/Users/mkoziol/projects/bet/scripts/validate_betclic_markets.py`
- `/Users/mkoziol/projects/bet/scripts/check_48h_repeats.py`
- `/Users/mkoziol/projects/bet/scripts/coupon_builder.py`
- `/Users/mkoziol/projects/bet/scripts/validate_coupons.py`
- `/Users/mkoziol/projects/bet/scripts/generate_coupon_pdf.py`
- `/Users/mkoziol/projects/bet/scripts/inspect_pipeline.py`
- `/Users/mkoziol/projects/bet/scripts/validate_phase.py`
- `/Users/mkoziol/projects/bet/scripts/db_report.py`
- `/Users/mkoziol/projects/bet/memories/repo/pipeline-knowledge-base.md`
- `/Users/mkoziol/projects/bet/memories/repo/pipeline-bugs-and-fixes.md`
- `/Users/mkoziol/projects/bet/memories/repo/pipeline-lessons-learned.md`
- `/Users/mkoziol/work/copilot-collections/.github/internal-prompts/tsh-research.prompt.md`

### Relevant Charts & Diagrams

```text
S0 settlement / learning / cleanup
    -> settled bets/coupons + learning outputs

S1 discovery
    -> DB: fixtures, scan_results, fixture_sources
    -> JSON: {date}_s1_events.json

S1b feeders
    -> DB: odds_history, tipster_picks, tipster_consensus, standings/team records/team_news inputs
    -> Files: odds snapshots, weather_{date}.json

S1d market matrix
    -> market_matrix_{date}.json/md

S1e shortlist
    -> {date}_s2_shortlist.json/md

S2 tipster xref
    -> mutates shortlist JSON with tipster_support + tipster_count

S2.3 scrapers
    -> DB: league_profiles, player_season_stats, athletes
    -> NOT directly team_form

S2.3 bridge helpers / S2.5 enrichment
    -> DB: team_form, match_stats, team_news, source_health

S3 deep stats
    -> {date}_s3_deep_stats.json/md
    -> DB: analysis_results + analysis_raw_data

S4 / S5 / S6
    -> update S3 JSON and analysis_results.stats_summary_json

S7 gate
    -> {date}_s7_gate_results.json/md
    -> DB: gate_results

S7.5 Betclic validation
    -> betclic_market_validation_{date}.json + betclic_markets DB

S7.6 repeat-loss control
    -> stdout/json only (no durable artifact)

S8 build
    -> betting/coupons/{date}.md/json + DB coupons/bets

S9 validate
    -> structural/arithmetic verdict via AGENT_SUMMARY/stdout

S10 delivery
    -> betting/coupons/pdf/{date}/
```

## Current Implementation Status

### Current-State Verdict by Layer

| Layer | Current state | Evidence / notes | Readiness impact |
|---|---|---|---|
| `.github` coordinator layer | Partially aligned | The run-then-delegate model is mostly in place, but step summaries, internal prompts, output filenames, and AGENT_SUMMARY inventory are not fully synchronized with runtime truth | High |
| Script/dataflow layer | Operational but hybrid | Core stages run and persist to DB/JSON, yet several write/read contracts drift across resume and fallback paths | High |
| DB integration layer | Strong but non-singular | Repository support is broad, but raw `sqlite3`/direct SQL remain and some bucket semantics do not round-trip cleanly | High |
| Validation/observability layer | Valuable but mixed-generation | `inspect_pipeline.py` is current; `validate_phase.py` still hard-codes legacy state assumptions; `verify_scan.py` and `db_report.py` are targeted but off the main prompt path | High |
| Memory/model-routing layer | Non-blocking but inconsistent | Memory files exist and are used; model assumptions diverge across prompt/agent/protocol files | Medium |

### Session-Critical Issues For Today’s Run

- `validate_phase.py` can false-fail a healthy run. It still blocks on `betting/data/pipeline_state/pipeline_{date}.json`, and only old state files for `2026-05-12` and `2026-05-13` exist. Its D2 step-check logic still uses older step IDs such as `s1a_discover`, `s1b_parallel`, and `s1c_aggregate`, and D6 treats `analysis_results` as a data-phase candidate proxy even though that is an S3 artifact. The current coordinator cannot safely treat `validate_phase --phase data` as authoritative without cross-checking live DB/files.
- Extended Pool does not round-trip through the DB contract. `gate_checker.py` places Extended Pool entries into the JSON `extended_pool` bucket but still writes `entry["status"] = "APPROVED"`. `save_gate_results_to_db()` persists that status, `GateResultRepo.get_extended()` only reads `UPPER(status) = 'EXTENDED'`, and `coupon_builder.py` loads DB first. Result: Extended Pool/watch-list candidates can disappear from DB-first resumes and coupon artifacts, breaking R3 visibility.
- `db_data_loader.load_gate_results_from_db()` has a dead JSON fallback for S7. It expects a top-level `results` list and filters lowercase status values, while `gate_checker.py` writes bucketed `gate_results` with uppercase-like per-entry semantics. If DB is missing or incomplete, S8 fallback cannot reconstruct S7 correctly.
- S2.3 scraper success is not the same as S3-ready stats. `run_scrapers.py` writes `league_profiles` and `player_season_stats`, not `team_form`. `deep_stats_report.py` still reads `team_form` and cache as its primary stat surface. Bridge scripts (`scraper_to_team_form.py`, `bridge_league_to_team_form.py`) exist but are outside the official orchestration path, so the coordinator can overestimate S2.3 value unless it explicitly bridges or separately validates `team_form` readiness.
- The S3->S6 hybrid source-of-truth can silently narrow the candidate set. `odds_evaluator.py` intentionally uses S3 JSON first because DB can be narrower. `context_checks.py` and `upset_risk.py` read DB first and only fall back when DB is empty, not when DB is partial. A partial DB write after S3 or S4 can therefore shrink the working set before S7 without a loud failure.
- The Betclic and repeat-loss pre-coupon controls are not fully bound into the build contract. The prompt says S7.5 writes `betting/data/{date}_betclic_validation.json`, but runtime writes `betclic_market_validation_{date}.json` and `coupon_builder.py` expects the runtime name. `coupon_builder.py` can still build without this sidecar even though the prompt calls S7.5 mandatory. `check_48h_repeats.py` produces stdout/json only, and `coupon_builder.py` does not ingest it at all, so the coordinator must enforce this filter manually today.

### Important Cleanup / Later Improvements

- `orchestrate-betting-day.prompt.md` still claims several scripts lack `AGENT_SUMMARY`, but `tipster_aggregator.py`, `tipster_xref.py`, `build_shortlist.py`, `data_enrichment_agent.py`, `deep_stats_report.py`, `gate_checker.py`, `coupon_builder.py`, and `fetch_odds_multi.py` now emit structured summaries. Monitoring guidance is stale rather than absent.
- The bottom-line orchestration summary still says `S2 ∥ S2.5`; the real intended parallel point is `S2 ∥ S2.3`, followed by S2.5.
- `bet-tipsters.prompt.md` and `bet-enrich.prompt.md` still narrate older worker responsibilities and older enrichment architecture. They are present enough to confuse specialist analysis even though the top-level orchestrator prompt has moved on.
- `agent_protocol.py` contracts lag runtime reality: `s2_tipster` assumes the consensus file as the main input but not the mutated shortlist; `s2_5_enrich` ignores S2.3/bridge surfaces; `s7_gate` depends only on S3 in the contract even though current orchestration requires S4-S6; `s8_coupons` does not declare the Betclic validation sidecar or PDF output.
- `validate_betclic_markets.py` and `bridge_league_to_team_form.py` still use direct `sqlite3` lifecycles instead of the canonical repository path.
- `validate_phase.py --phase build` does not treat PDF generation as part of the required build gate even though S10 exists in code.
- `fetch_api_stats.py` remains in repo as a legacy utility surface. The official prompt already treats it as deprecated, but it is still another source of conceptual drift.
- `fetch_odds_multi.py` is a real multi-source odds writer to `odds_history`, but it is not in the official orchestrator path. Multi-source cross-validation therefore depends on explicit manual use or previously populated DB state.

### Cross-Repository Pattern Comparison

| Dimension | bet current runtime truth | copilot-collections reference pattern | Readiness impact |
|---|---|---|---|
| Prompt/runtime consistency | The bet prompt stack still contains internal contradictions around S2 parallelization, S7.5 output naming, S10 meaning, and AGENT_SUMMARY availability | Reference orchestration artifacts are usually closer to runtime truth | High |
| Model routing | bet agents hard-pin Claude Opus 4.6 while the execution protocol still names Gemini 3.1 Pro; current session baseline is GPT-5.4 | Reference artifacts more often declare model assumptions explicitly and consistently | Medium |
| Coordinator/worker separation | bet mostly follows run-then-delegate now, but some internal prompts still carry older run-yourself narration | Reference repo keeps coordinator/worker responsibility boundaries cleaner | Medium-High |

The comparison is now narrower than in the previous audit: `copilot-collections` remains a useful baseline for artifact discipline, but today’s readiness in bet is constrained far more by runtime contract drift than by missing prompt sophistication.

### Real Producer/Consumer Integration Risk

- `build_shortlist.py` is hard-wired to `market_matrix_{date}.json`. Missing matrix output is a real blocking contract, not just a sequencing preference.
- `tipster_aggregator.py` writes tipster DB tables and `pipeline_runs` for `s2_tipster`; `tipster_xref.py` emits `AGENT_SUMMARY` and mutates shortlist JSON but does not populate `pipeline_runs`. Fetch and cross-reference are therefore separate contracts even though the prompt sometimes narrates them as one tipster phase.
- `tipster_xref.py` mutates `{date}_s2_shortlist.json` in place. S3 tipster awareness depends on preserving that exact shortlist filename and `candidates` structure.
- `run_scrapers.py` versus `scraper_to_team_form.py` / `bridge_league_to_team_form.py` is a real ownership boundary. The scraper tables are useful, but they are not the same thing as the `team_form` rows S3 currently consumes.
- `deep_stats_report.py` dual-writes to JSON and DB, then injects `fixture_id` back into the in-memory analysis entries. Later S4-S6 enrichment logic depends on that injected identifier for DB updates.
- `odds_evaluator.py` explicitly avoids DB-only loading because DB coverage can be narrower than JSON coverage for S3 analyses. JSON remains an operational source of truth, not just a report artifact.
- `context_checks.py` and `upset_risk.py` are DB-first and only fall back to JSON when DB is empty, not when DB is partial. A partial DB population can therefore narrow the working set.
- `gate_checker.py` writes bucketed JSON but persists DB rows in a way that loses explicit Extended Pool identity. This is the most important current DB/JSON parity defect.
- `check_48h_repeats.py` produces a JSON-shaped stdout response only. There is no durable file or DB contract for S8 to consume automatically.
- `coupon_builder.py` reads gate results from DB first and direct JSON second, then separately loads `betclic_market_validation_{date}.json`. The build contract is therefore split across DB plus sidecar files.
- `generate_coupon_pdf.py` depends on coupon markdown and optional JSON, but the official build validation path does not currently require PDF success.

### Database Integration Readiness

#### Strengths

- Canonical DB access is well-defined: `get_db()` configures WAL mode, foreign keys, busy timeout, and retry behavior.
- Repository coverage is broad enough to support real DB-first execution: `PipelineRepo`, `AnalysisResultRepo`, `GateResultRepo`, `TipsterRepo`, `LeagueProfileRepo`, `StatsRepo`, and related ESPN/team-news repositories are already in place.
- Discovery, tipster aggregation, enrichment, S3 analysis persistence, S7 gate persistence, and build-time DB loading are all real DB-backed behaviors, not aspirational comments.
- `inspect_pipeline.py` and `db_report.py` already expose enough state to judge same-day DB health and rich coverage.

#### Caveats

- The system is DB-first, not DB-only. JSON remains operationally required for shortlist mutation, full S3 candidate coverage, gate artifacts, coupon artifacts, and some resume paths.
- `pipeline_runs` coverage is partial. In the current script layer, step tracking is visibly written by `build_shortlist.py`, `tipster_aggregator.py`, and `filter_betclic_shortlist.py`, but not by most of the current S1-S10 scripts.
- `validate_phase.py` still depends on legacy `pipeline_state` files despite DB repository support for pipeline runs.
- `gate_results` does not currently round-trip cleanly between JSON buckets and DB status filters.
- Not all DB access follows the canonical repository layer. `validate_betclic_markets.py` and `bridge_league_to_team_form.py` still manage direct `sqlite3` connections.

#### Current verdict

The database integration is strong enough for daily use and far more mature than the old JSON-only flow, but it is not yet a single-source-of-truth system. Today-session readiness still depends on DB and JSON artifacts remaining mutually consistent, especially at S3-S8.

### Post-Enrichment Impact From Recent Multisport Rich-Stat Work

- `data_enrichment_agent.py` now classifies football, basketball, tennis, hockey, and volleyball against sport-specific rich-stat expectations drawn from `RICH_COMPLETION_POLICY`.
- `enriched` no longer means "some cache exists." It now means the sport-specific rich key set has been satisfied; otherwise the status is often `partial`, even when baseline data exists.
- Rich stat data now spans multiple stores: `team_form`, `match_stats`, `league_profiles`, and `player_season_stats`. This makes the S2.3 ownership boundary more important, not less.
- `run_scrapers.py` materially improves the data warehouse, but official S3 analysis still mostly lives on `team_form` and cache. Rich coverage therefore has two questions now: did the data arrive anywhere, and did it arrive in the tables S3/S7 actually read?
- `inspect_pipeline.py` S2 uses `rich_coverage.py` plus `RICH_COMPLETION_POLICY` to summarize shortlist-team coverage into `rich`, `baseline_only`, `partial`, and `no_data` buckets. This is the clearest post-rollout readiness signal currently in repo.
- `db_report.py` can also summarize richness by sport, so the observability to judge post-enrichment quality already exists.

Downstream impact:

- S3 can still run on partial data, but post-rollout readiness should not be judged only by whether S3 ran. It should be judged by whether shortlist teams reached acceptable rich completion by sport and whether that data is actually consumable by S3.
- S7 and S8 now have a more meaningful basis for demoting weak candidates to Extended Pool, because the difference between full, partial, and minimal data is more explicit.
- `validate_phase.py` still focuses mostly on step completion, candidate counts, and `team_form` volume. A nominal PASS can therefore still hide weak post-rollout richness or unbridged scraper data.

### Today-Session-Ready Acceptance Criteria

- One authoritative coordinator owns the daily workflow, and specialist prompts operate in analysis-only mode for the exact steps the coordinator actually ran.
- Today’s official step map is internally consistent: S2 parallels S2.3, not S2.5; S10 is explicitly defined as summary-only or PDF delivery, and all surrounding artifacts follow the same choice.
- Previous-day settlement and Betclic learning are completed before new scan/build work starts.
- Data-phase readiness is judged from live DB/file surfaces (`fixtures`, `scan_results`, `market_matrix`, shortlist, `team_form`, `odds_history`, tipster tables), not from missing legacy `pipeline_state` alone.
- `build_shortlist.py` input contract is satisfied: `market_matrix_{date}.json` exists and matches the same-day fixture/odds scope.
- The shortlist exists and, if tipster cross-reference ran, the mutated shortlist still carries `tipster_support` and `tipster_count` for downstream S3/S7 use.
- If S2.3 is run for same-day readiness, the coordinator separately confirms either bridge scripts or S2.5 populated S3-consumable `team_form`; scraper tables alone do not count as S3-ready.
- Enrichment quality is acceptable for today’s shortlist teams when checked through `inspect_pipeline.py` rich-coverage reporting, not only by counting `team_form` rows.
- S3 exists in both `{date}_s3_deep_stats.json` and `analysis_results`, and the working candidate universe has not been silently narrowed by DB/JSON divergence.
- S4, S5, and S6 maintain candidate parity or explicitly explain any narrowed set before S7 consumes them.
- S7 gate results exist in both DB and JSON, and the gate surface preserves approved plus Extended Pool candidates instead of collapsing them into one DB status.
- Betclic validation sidecar filename and load path match between S7.5 and S8; if S7.5 is mandatory for today’s run, S8 must fail closed when it is absent.
- 48h repeat-loss findings are durably carried into coupon selection, not just printed to stdout.
- Coupon markdown passes S9 validation, and if PDF delivery is part of today’s session definition, S10 PDF generation is successful for the same date.
- Memory loading and model-routing differences may influence analysis quality, but they do not substitute for these runtime contract checks.

## Gap Analysis

### Hard Requirements For This Meta-Task

- Reframe readiness from a prompt/agent review into a full S0-S10 session-readiness audit grounded in bet runtime contracts.
- Treat `.github` prompts, agents, internal prompts, instructions, and memory interactions as in-scope only insofar as they affect bet session behavior.
- Document authoritative source per step: where DB is primary, where JSON remains required, and where both must stay aligned.
- Explicitly separate today-critical blockers from later cleanup so same-day orchestration decisions are not buried in artifact design commentary.
- Call out current legacy validation and gate round-trip defects as readiness blockers, not as optional cleanup.
- Keep model-routing analysis only where it affects bet orchestration predictability.
- Avoid implementation planning; this document must remain a research artifact.

### Optional Improvements

- Unify step-tracking coverage across scripts or replace legacy `pipeline_state` consumers with live DB/file validation.
- Promote bridge scripts, or direct S3 consumption of scraper tables, into the official S2.3 contract if scraper work is meant to improve same-day analysis.
- Make Betclic validation and 48h repeat-loss checks durable inputs to S8 rather than coordinator-only side knowledge.
- Align internal prompts, AGENT_SUMMARY inventory, and model declarations across `.github` artifacts.
- Include PDF existence in the required build gate if S10 remains a real runtime step.

### Question 1

#### Are there any blocking ambiguities that prevent planning?

No research blocker prevents planning. The codebase is explicit enough to plan against.

Two requirement choices should still be made deliberately during planning: whether S10 officially means final summary or PDF delivery, and whether S2.3 is intended to become a true `team_form` feeder or remain a parallel data reservoir behind bridge/helper steps. Those are planning inputs, not blockers to research completion.

### Question 2

#### Which initial findings were validated or refuted?

Validated:

- The previous audit was too narrow. Orchestration findings remain real, but they are not sufficient to judge session readiness.
- The betting repo still relies on deliberate orchestration behavior, but the main risk is runtime contract drift, not prompt polish alone.
- The real producer/consumer chain is anchored in `db_data_loader.py`, S3/S7 dual-write behavior, and hybrid DB/JSON surfaces.
- The recent multisport rich-stat rollout materially changed what S2.5 readiness should mean.
- The `run_scrapers.py` versus `team_form` ownership boundary is a real hotspot, not just a documentation nuisance.

Refined:

- The biggest risk is not simply "bad prompts" or "wrong model defaults." The biggest risk is hybrid-source drift: DB and JSON surfaces that no longer represent the same candidate universe or the same gate/build state.

Newly surfaced during this audit:

- `validate_phase.py` still anchors readiness to legacy `pipeline_state` files and older step IDs.
- Extended Pool identity is lost on the DB-first S7->S8 path because `gate_checker.py` persists those rows with `status="APPROVED"`.
- `load_gate_results_from_db()` has a dead JSON fallback for current S7 output.
- The prompt/runtime contract for Betclic validation filenames is mismatched.
- `check_48h_repeats.py` has no durable handoff into `coupon_builder.py`.
- Model assumptions are inconsistent across bet prompt/agent/protocol files.

### Question 3

#### What most directly threatens a "today-session-ready" verdict?

The most direct threats are runtime-contract issues rather than orchestration-style issues:

- false validation failures caused by legacy `pipeline_state` gating and stale step IDs,
- S7 bucket loss across DB-first resume paths,
- treating S2.3 scraper success as if it were already S3-consumable `team_form`,
- silent candidate-set narrowing across the S3->S6 JSON-first / DB-first split,
- and pre-coupon controls (Betclic validation, 48h repeat-loss checks) that are not durably bound into S8.

Those are the conditions most likely to make the pipeline look healthy at the customization layer while still being operationally unsafe or incomplete for a real same-day betting session.# Betting Pipeline Session Readiness Audit - Analysis Result

## Task Details

| Field | Value |
|---|---|
| Jira ID | N/A - prompt-defined cross-repository meta-task |
| Title | Betting pipeline session readiness audit for 2026-05-21 |
| Description | Audit the full betting pipeline in `/Users/mkoziol/projects/bet`, not only the orchestration/customization layer, and define what must be true for a today-session-ready end-to-end run. Compare prompt/agent/instruction patterns with `/Users/mkoziol/work/copilot-collections`, but ground the result in the actual S0-S10 script chain, DB contracts, JSON artifacts, and post-enrichment runtime behavior. |
| Priority | High |
| Reporter | User prompt |
| Created Date | 2026-05-21 |
| Due Date | 2026-05-21 |
| Labels | betting, session-readiness, pipeline, orchestration, db-first, contract-audit |
| Estimated Effort | Research artifact only; implementation planning intentionally deferred |

## Business Impact

The current session does not depend only on whether the orchestrator prompt is well-written. It depends on whether the entire betting workflow can be resumed, validated, and trusted from settlement through coupon delivery without silent producer/consumer mismatches, stale fallback logic, or DB/JSON drift.

The business value of this audit is to answer a narrower operational question: if the user starts a real betting session today, is the pipeline ready to execute safely end to end? That requires both coordinator correctness and runtime correctness: inputs exist, intermediate surfaces remain aligned, DB-first paths behave as expected, rich-stat enrichment quality is visible, gate/build outputs are valid, and the official session definition matches the code that actually runs.

## Gathered Information

### Knowledge Base & Task Management Tools

- No Jira, Confluence, Figma, or PDF artifacts were referenced for this task. The source of truth is the codebase, repository memory, and the existing research artifact.
- Repository memory in `bet/memories/repo/pipeline-knowledge-base.md` confirms a current S0-S10 workflow, recent orchestration fixes, and the importance of validating real script/dataflow behavior rather than trusting prompt text alone.
- The task is research-only. No runtime code changes, implementation plan, or rollout proposal are part of the requested output.
- The prior audit artifact was valid as an orchestration review, but too narrow for session-readiness because it did not map the real producer/consumer chain.

### Codebase

#### Primary Repository: bet

- The runtime stack is Python 3.11 plus SQLite at `betting/data/betting.db`, with a DB-first plus JSON-fallback pattern across most pipeline scripts.
- Canonical DB access is `src/bet/db/connection.py:get_db()`. Repository coverage is broad: fixtures, stats, analysis results, gate results, pipeline runs, tipster data, league profiles, standings, rosters, and team news all have repository support.
- The pipeline is not a pure DB-only system. JSON artifacts remain operationally important at S1, S1d, S1e, S3, S7, and S8, and some steps explicitly prefer JSON because DB coverage can be narrower than the full working set.
- The orchestration layer lives in `.github/` and has improved materially, but actual session readiness is controlled just as much by `scripts/db_data_loader.py`, `scripts/inspect_pipeline.py`, `scripts/validate_phase.py`, and the S3-S8 dual-write/update behavior.

#### Reference Repository: copilot-collections

- The reference repo is still useful as the comparison baseline for prompt/agent/instruction layering, coordinator/worker boundaries, and prompt-level model routing.
- `tsh-implement.prompt.md` and several higher-level manager/orchestrator surfaces use `GPT-5.4`, which is the clearest contrast with the betting repo's current agent-default-heavy model strategy.
- The reference repo is not a full runtime analog for the betting pipeline. It helps evaluate customization quality, but it does not replace code-backed analysis of DB adapters, artifacts, and script handoffs.

#### Concrete End-to-End Pipeline Map (S0-S10)

| Stage | Primary scripts | Main reads | Main writes | Current readiness notes |
|---|---|---|---|---|
| S0 foundation | `settle_on_finish.py`, `analyze_betclic_learning.py`, `evaluate_decisions.py`, `data_rotation.py`, `build_league_profiles.py` | coupons/bets tables, `picks-ledger.csv`, `coupons-ledger.csv`, `match_stats`, Betclic history | settled bets/coupons, learning analysis, decision outcomes, cleaned artifacts, `league_profiles` | Previous-day settlement and Betclic learning are genuine pre-session dependencies, not prompt-only rituals. |
| S1 discovery | `discover_events.py` plus `src/bet/discovery/coordinator.py` | SofaScore, Odds API, API-Football | DB `fixtures`, `scan_results`, `fixture_sources`; `{date}_s1_events.json` | Discovery is already DB-backed and not just a thin JSON producer. |
| S1 ingest / auxiliary feeds | `ingest_scan_stats.py`, `seed_espn_data.py`, `fetch_odds_api.py`, `fetch_odds_api_io.py`, `fetch_weather.py`, `tipster_aggregator.py` | S1 events, ESPN APIs, odds APIs, weather APIs, tipster sites | `stats_cache`, `team_form`, `standings`, `rosters`, ATS/OU, `odds_history`, `weather_{date}.json`, tipster DB/JSON | Several important feeders are DB-only or DB-primary and do not surface through one shared artifact. |
| S1d matrix | `generate_market_matrix.py` | fixtures DB, odds DB/JSON, scan summary DB, stats cache | `market_matrix_{date}.json`, `market_matrix_{date}.md`, `decision_matrix_{date}.md` | This is the full decision surface before narrowing to a shortlist. |
| S1e shortlist | `build_shortlist.py` | market matrix, fixtures DB, odds DB, optional Betclic validation | `{date}_s2_shortlist.json`, `{date}_s2_shortlist.md`, optional `{date}_s2_shortlist_bettable.json`, `pipeline_runs` stats | The shortlist JSON becomes the mutation surface for S2 tipster enrichment. |
| S2 tipster cross-reference | `tipster_xref.py` | shortlist JSON, `TipsterRepo`, JSON tipster fallback | rewrites the same shortlist JSON with `tipster_support` and `tipster_count` | In-place shortlist mutation is a real contract dependency. |
| S2.3 / S2.5 enrichment | `run_scrapers.py`, `data_enrichment_agent.py` | shortlist teams, scraper sources, fallback chains, existing `team_form` rows | DB `league_profiles`, `player_season_stats`, `team_form`, `known_missing`; rich-coverage status in process output | Post-rollout readiness now depends on per-sport rich completion, not just non-empty `team_form`. |
| S3 deep stats | `deep_stats_report.py` | shortlist JSON, DB/cache stats, tipster-enriched shortlist | `{date}_s3_deep_stats.md`, `{date}_s3_deep_stats.json`, DB `analysis_results`, raw analysis data | This is the main dual-write step and injects `fixture_id` back into the working analysis set. |
| S4-S6 analysis enrichment | `odds_evaluator.py`, `context_checks.py`, `upset_risk.py` | S3 JSON and/or `analysis_results`, `odds_history`, weather, `team_news` | updated S3 JSON, `analysis_results.stats_summary_json` with EV, context, and upset risk | Readiness depends on DB and JSON staying aligned after S3. |
| S7 gate | `gate_checker.py`, `check_48h_repeats.py` | `analysis_results` or S3 JSON, fixtures DB, `picks-ledger.csv` | `{date}_s7_gate_results.json`, `{date}_s7_gate_results.md`, DB `gate_results` | Approved, extended, and rejected buckets are the build contract for S8. |
| S7.5 / S7.6 validation | `validate_betclic_markets.py`, `check_48h_repeats.py` | Betclic scan, coupon/gate market names, recent losses | `betclic_market_validation_{date}.json`, Betclic market DB side effects | Betclic validation is treated as mandatory in the prompt but optional in some runtime paths. |
| S8 build | `coupon_builder.py` | gate results DB or JSON, Betclic validation sidecar, config, tipster DB fallback | `betting/coupons/{date}.md`, `betting/coupons/{date}.json` | S8 depends on both gate persistence and the presence of the Betclic validation sidecar if market enforcement is expected. |
| S9 validate | `validate_coupons.py` | coupon markdown, `picks-ledger.csv` | validation output via stdout / `AGENT_SUMMARY` | S9 verifies arithmetic, uniqueness, and ledger references, but does not create a durable artifact by default. |
| S10 delivery | `generate_coupon_pdf.py` | coupon markdown and optional coupon JSON | `betting/coupons/pdf/{date}/` full and section PDFs, quick reference PDF | Runtime has a real PDF delivery step even though the current orchestration prompt treats S10 as a summary-only stage. |

Additional diagnostic layer:

- `inspect_pipeline.py` is the read-only state inspector for S0, S1, S1e, S2, S3, S7, and S8.
- `validate_phase.py` is the blocking/non-blocking readiness gate for data, analysis, and build phases.

### Relevant Links

- `/Users/mkoziol/projects/bet/.github/copilot-instructions.md`
- `/Users/mkoziol/projects/bet/.github/prompts/orchestrate-betting-day.prompt.md`
- `/Users/mkoziol/projects/bet/scripts/agent_protocol.py`
- `/Users/mkoziol/projects/bet/src/bet/db/connection.py`
- `/Users/mkoziol/projects/bet/src/bet/db/repositories.py`
- `/Users/mkoziol/projects/bet/scripts/db_data_loader.py`
- `/Users/mkoziol/projects/bet/src/bet/discovery/coordinator.py`
- `/Users/mkoziol/projects/bet/scripts/discover_events.py`
- `/Users/mkoziol/projects/bet/scripts/generate_market_matrix.py`
- `/Users/mkoziol/projects/bet/scripts/build_shortlist.py`
- `/Users/mkoziol/projects/bet/scripts/tipster_xref.py`
- `/Users/mkoziol/projects/bet/scripts/run_scrapers.py`
- `/Users/mkoziol/projects/bet/scripts/data_enrichment_agent.py`
- `/Users/mkoziol/projects/bet/src/bet/stats/fallback_chains.py`
- `/Users/mkoziol/projects/bet/src/bet/stats/rich_coverage.py`
- `/Users/mkoziol/projects/bet/scripts/deep_stats_report.py`
- `/Users/mkoziol/projects/bet/scripts/odds_evaluator.py`
- `/Users/mkoziol/projects/bet/scripts/context_checks.py`
- `/Users/mkoziol/projects/bet/scripts/upset_risk.py`
- `/Users/mkoziol/projects/bet/scripts/gate_checker.py`
- `/Users/mkoziol/projects/bet/scripts/validate_betclic_markets.py`
- `/Users/mkoziol/projects/bet/scripts/coupon_builder.py`
- `/Users/mkoziol/projects/bet/scripts/validate_coupons.py`
- `/Users/mkoziol/projects/bet/scripts/generate_coupon_pdf.py`
- `/Users/mkoziol/projects/bet/scripts/inspect_pipeline.py`
- `/Users/mkoziol/projects/bet/scripts/validate_phase.py`
- `/Users/mkoziol/projects/bet/memories/repo/pipeline-knowledge-base.md`
- `/Users/mkoziol/work/copilot-collections/.github/prompts/tsh-implement.prompt.md`
- `/Users/mkoziol/work/copilot-collections/.github/agents/tsh-copilot-orchestrator.agent.md`

### Relevant Charts & Diagrams

```text
S0 foundation
    -> settlement / learning / cleanup / priors

S1 discovery
    -> DB: fixtures, scan_results, fixture_sources
    -> JSON: {date}_s1_events.json

S1 ingest + feeders
    -> stats_cache + team_form + odds_history + standings/rosters/news/weather/tipsters

S1d matrix
    -> market_matrix_{date}.json/md
    -> decision_matrix_{date}.md

S1e shortlist
    -> {date}_s2_shortlist.json/md
    -> S2 mutates this file in place with tipster_support

S2.3/S2.5 enrichment
    -> DB-rich sports data and team_form completeness

S3 deep stats
    -> {date}_s3_deep_stats.json/md
    -> DB: analysis_results

S4/S5/S6
    -> update S3 JSON and analysis_results.stats_summary_json

S7 gate
    -> {date}_s7_gate_results.json/md
    -> DB: gate_results

S7.5 Betclic validation sidecar
    -> betclic_market_validation_{date}.json

S8 build
    -> betting/coupons/{date}.md/json

S9 validate
    -> structural/arithmetic verdict

S10 delivery
    -> betting/coupons/pdf/{date}/
```

## Current Implementation Status

### Existing Components

| Surface | Current state | Evidence / notes | Readiness impact |
|---|---|---|---|
| Orchestration prompt and agents | Improved, but still only one slice of readiness | Strong run-then-delegate rules exist, but prompt/runtime truth can diverge | High |
| Discovery and early data collection | Broadly operational | Discovery already persists fixtures and scan results to DB; matrix and shortlist scripts are concrete downstream consumers | High |
| Shared DB adapter layer | Strong but hybrid | `db_data_loader.py` normalizes DB data back into script-friendly JSON shapes; not all steps rely on it consistently | High |
| Shortlist mutation contract | Operational but brittle | `tipster_xref.py` rewrites `{date}_s2_shortlist.json` in place to add tipster support | High |
| S3 analysis persistence | Dual-write and resilient, but not singular | `deep_stats_report.py` writes markdown, JSON, DB `analysis_results`, and raw data | High |
| S4-S6 enrichment chain | Functional, but source-of-truth drift remains possible | S4 explicitly prefers JSON because DB may be narrower; S5/S6 prefer DB | High |
| Gate and coupon build chain | Operational | S7 writes DB and JSON; S8 reads DB first and JSON second; S9 validates coupon structure | High |
| Betclic market validation | Real runtime dependency with a DB-policy exception | `validate_betclic_markets.py` is a real step before S8 and uses raw `sqlite3` | High |
| PDF delivery | Implemented in code but under-described in orchestration docs | `generate_coupon_pdf.py` exists and is a real output step; current prompt does not reflect it as S10 | Medium-High |
| Diagnostic and readiness gates | Strongest existing session-readiness surfaces | `inspect_pipeline.py` and `validate_phase.py` already encode practical resume/safe-to-proceed checks | High |

### Cross-Repository Pattern Comparison

| Dimension | bet current runtime truth | copilot-collections reference pattern | Readiness impact |
|---|---|---|---|
| Coordinator authority | Strong in instructions and prompt, but runtime readiness also depends on script/dataflow truth | Coordinators own decomposition and synthesis | High |
| Prompt/runtime consistency | Not fully aligned; prompt says S10 summary-only while code has S10 PDF generation | Prompt and runtime surfaces are typically closer in the reference repo | High |
| Prompt-level model routing | Betting prompts usually omit explicit `model:` | High-level prompts commonly declare `model:` and agent choice explicitly | Medium-High |
| Agent/prompt separation | Still more duplicated than ideal | Reference repo keeps prompt, agent, skill, and instruction responsibilities cleaner | Medium-High |
| Worker side effects | Betting specialists still carry more workflow weight than pure analysis workers | Reference workers are typically narrower and more bounded | Medium |
| Runtime validation culture | Strong and code-backed in bet | Less relevant in the reference repo because it is not a live data pipeline | High |

The main conclusion from the comparison is narrower than in the previous audit: the betting repo still has customization-layer cleanup to do, but session readiness today is dominated by runtime contract integrity more than by artifact-design polish.

### Real Producer/Consumer Integration Risk

- `discover_events.py` is not just a scan wrapper. Its real producer surface is DB `fixtures` + `scan_results` plus `{date}_s1_events.json`, and downstream steps consume both. Any change to event shape has two consumers, not one.
- `tipster_xref.py` mutates `{date}_s2_shortlist.json` in place. S3 tipster awareness depends on the exact shortlist filename and the preserved `candidates` structure.
- The historical `all_picks` versus `tips` mismatch has been partially hardened: `tipster_xref.py` now reads both. That specific producer/consumer failure is improved, but the in-place shortlist mutation pattern is still brittle.
- `deep_stats_report.py` dual-writes to JSON and DB, then injects `fixture_id` back into the in-memory analysis entries. Later S4-S6 enrichment logic depends on that identifier for DB updates.
- `odds_evaluator.py` explicitly avoids DB-only loading because DB coverage can be narrower than JSON coverage for S3 analyses. This means JSON remains an operational source of truth for full candidate coverage, not just a report artifact.
- `context_checks.py` and `upset_risk.py` are DB-first and only fall back to JSON when DB is empty, not when DB is partial. If JSON contains a fuller candidate set than DB, downstream enrichment can silently narrow the working set.
- `db_data_loader.load_gate_results_from_db()` has an outdated JSON fallback shape. It expects a top-level `results` list, while `gate_checker.py` writes `gate_results` buckets (`approved`, `extended_pool`, `rejected`). DB loss or DB-unavailable resume paths would misread S7 JSON.
- `coupon_builder.py` reads gate results from DB first and direct JSON second, but Betclic validation comes from a separate sidecar file. If the sidecar is missing, S8 still builds coupons even though the prompt treats S7.5 as mandatory.
- `generate_coupon_pdf.py` depends on coupon markdown and optional JSON, but the official build validation path does not currently treat PDF generation as part of the required build gate.

### Database Integration Readiness

#### Strengths

- Canonical DB access is well-defined: `get_db()` configures WAL mode, foreign keys, busy timeout, and retry behavior.
- Repository coverage is broad enough to support real DB-first execution: `PipelineRepo`, `AnalysisResultRepo`, `GateResultRepo`, `TipsterRepo`, `LeagueProfileRepo`, `StatsRepo`, and many ESPN/team-news repositories are already in place.
- Discovery, ESPN seeding, enrichment, S3 analysis persistence, S7 gate persistence, and build-time DB loading are all real DB-backed behaviors, not aspirational comments.
- `inspect_pipeline.py` and `validate_phase.py` are already DB-first readiness tools and provide the most realistic definition of what "resume safely" means in this repo.

#### Caveats

- The system is DB-first, not DB-only. JSON remains operationally required for shortlist mutation, full S3 candidate coverage, human-readable reports, gate artifacts, and coupon artifacts.
- Not all DB usage goes through the repository layer. Discovery uses a SQLAlchemy session plus raw SQL, several scripts use direct SQL queries, and Betclic validation opens raw `sqlite3` explicitly.
- `pipeline_state/pipeline_{date}.json` is still part of the official validation path for data-phase completion, so DB health alone does not establish readiness.
- The stale JSON fallback in `load_gate_results_from_db()` weakens one of the key resilience promises of the DB-first plus JSON-fallback architecture.

#### Current verdict

The database integration is strong enough for daily use and far more mature than the old JSON-only flow, but it is not yet a single-source-of-truth system. Today-session readiness still depends on DB and JSON artifacts remaining mutually consistent.

### Post-Enrichment Impact From Recent Multisport Rich-Stat Work

- `data_enrichment_agent.py` now classifies football, basketball, tennis, hockey, and volleyball against sport-specific rich-stat expectations drawn from `RICH_COMPLETION_POLICY`.
- `enriched` no longer means "some cache exists." It now means the sport-specific rich key set has been satisfied; otherwise the status is often `partial`, even when baseline data exists.
- Football rich completion is now explicitly tied to Flashscore HTML completion helpers. Basketball, tennis, hockey, and volleyball each have their own rich-completion helper modules and per-sport missing-key logic.
- Hockey enrichment can add supplementary advanced stats from MoneyPuck and ScraperNHL after the main chain. This changes the operational meaning of "coverage complete" for hockey compared with earlier audits.
- `inspect_pipeline.py` S2 uses `rich_coverage.py` plus `RICH_COMPLETION_POLICY` to summarize shortlist-team coverage into `rich`, `baseline_only`, `partial`, and `no_data` buckets. This is the clearest post-rollout readiness signal.
- `db_report.py` and related read-only reporting surfaces can now summarize rich completion generically, which means the codebase already has the observability needed to judge enrichment quality by sport.

Downstream impact:

- S3 can still run on partial data, but post-rollout readiness should not be judged only by whether S3 ran. It should be judged by whether shortlist teams reached acceptable rich completion by sport.
- S7 and S8 now have a more meaningful basis for demoting weak candidates to Extended Pool, because the difference between full, partial, and minimal data is more explicit.
- `validate_phase.py` data checks still focus on step completion, candidate counts, and `team_form` volume. They do not yet gate on sport-specific rich completion thresholds. A nominal PASS can therefore still hide weak post-rollout richness.

### Today-Session-Ready Acceptance Criteria

- One authoritative coordinator owns the daily workflow, and no specialist agent undercuts that by exposing an alternate direct-execution path for the same work.
- Previous-day settlement and Betclic learning are completed before new scan/build work starts.
- Data phase passes in practice, not just in prose: `discover_events.py`, shortlist generation, and enrichment have produced the expected DB and file surfaces, and `validate_phase.py --phase data` has no blocking failures.
- S1 discovery exists in both DB and `{date}_s1_events.json`, because downstream consumers still use both forms.
- The shortlist exists and, if tipster cross-reference ran, the mutated shortlist still carries `tipster_support` and `tipster_count` for downstream S3/S7 use.
- Enrichment quality is acceptable for today's shortlist teams when checked through `inspect_pipeline.py` rich-coverage reporting, not only by counting `team_form` rows.
- S3 exists in both `{date}_s3_deep_stats.json` and `analysis_results`, and the working candidate universe has not been silently narrowed by DB/JSON divergence.
- S4, S5, and S6 have populated EV, context, and upset-risk fields in the analysis surface used by S7, and `validate_phase.py --phase analysis` has no blocking failures.
- S7 gate results exist in both DB and JSON, and the gate surface includes approved plus Extended Pool candidates rather than only hard exclusions.
- Betclic validation exists before S8 if the session expects market-availability enforcement rather than advisory-only coupon construction.
- Coupon markdown passes S9 validation, and if PDF delivery is part of today's session definition, S10 PDF generation is successful for the same date.
- The official prompt/agent step map matches runtime truth, especially on S2 parallelization and the meaning of S10.

## Gap Analysis

### Hard Requirements For This Meta-Task

- The readiness definition must expand from "prompt/agent quality" to full runtime readiness across S0-S10.
- The declared step map must be reconciled with code reality, especially S10 (PDF generation exists) and the exact independent-step pairing in S2.
- The project needs an explicit statement of authoritative source per step: where DB is primary, where JSON remains required, and where both must stay aligned.
- Stale fallback contracts such as `load_gate_results_from_db()` must be treated as readiness blockers, not as minor cleanup.
- Post-enrichment readiness must include rich-coverage quality, not only row counts or step-completed flags.
- The customization layer still needs a cleaner coordinator/worker contract and a documented model-routing policy, but those changes should be evaluated against runtime needs rather than in isolation.

### Optional Improvements

- Include PDF generation in the official build-phase validation if S10 remains part of the real session definition.
- Add an explicit validator check for DB-versus-JSON parity after S3-S6, since that is now the most important hybrid-source risk.
- Reduce worker-side artifact writing and duplicated prompt/agent prose to align more closely with the reference repo's cleaner orchestration pattern.
- Replace remaining raw `sqlite3` paths in Betclic validation and related scraper flows if stricter DB-first consistency is desired.

### Question 1

#### Are there any blocking ambiguities that prevent planning?

No blocking ambiguities prevent research completion. The codebase is explicit enough to describe the current workflow, runtime contracts, and session-readiness criteria.

There is one policy ambiguity that matters for acceptance criteria: whether S10 officially means "final summary" or "PDF delivery," because the orchestration prompt and the runtime scripts currently disagree. That does not block research, but it does affect what "today-session-ready" should mean.

### Question 2

#### Which initial findings were validated or refuted?

Validated:

- The previous audit was too narrow. Orchestration findings remain real, but they are not sufficient to judge session readiness.
- The betting repo still relies on deliberate orchestration behavior and would benefit from clearer prompt/agent/model policy.
- The real producer/consumer contract is anchored in `db_data_loader.py`, dual-write S3/S7 behavior, and the existence of hybrid DB/JSON surfaces.
- The recent multisport rich-stat rollout materially changed what S2.5 readiness should mean.

Refined:

- The biggest risk is not simply "bad prompts" or "wrong model defaults." The biggest risk is hybrid-source drift: DB and JSON surfaces that no longer represent the same candidate universe or the same gate/build state.

Newly surfaced during this audit:

- `load_gate_results_from_db()` has an outdated JSON fallback contract.
- `validate_betclic_markets.py` bypasses the canonical DB access pattern with direct `sqlite3`.
- The official prompt's S10 definition does not reflect the existing PDF-generation script.

### Question 3

#### What most directly threatens a "today-session-ready" verdict?

The most direct threats are now runtime-contract issues, not only orchestration-style issues:

- DB/JSON divergence after S3, where S4 treats JSON as fuller than DB but S5/S6 prefer DB.
- The stale JSON fallback for gate results, which weakens resume behavior when DB state is missing or incomplete.
- The mismatch between prompt-level step definitions and the actual runtime pipeline, especially S10 and the Betclic validation dependency.
- The fact that post-enrichment richness is observable but not yet part of the blocking data-phase gate.

Those are the conditions most likely to make the pipeline look healthy at the customization layer while still being operationally unsafe or incomplete for a real same-day betting session.