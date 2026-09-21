# TIPSTER_SCRAPER_V2.3_FINAL_RC — implementation bundle

Generated: 2026-07-03 Europe/Warsaw context.

## Verdict

This bundle is a release-candidate implementation package for a shadow-only, compliance-first tipster scraper layer in Skiru/bet. It is not a production promotion. Production promotion requires repo-local robots/terms evidence, source fixture snapshots, live dry-run artifacts, and post-run review.

## Why this exists

Legacy S2 currently delegates to monolithic tipster aggregation/cross-reference scripts. That shape makes source-specific parser quality, compliance gates, fixture coverage, and pipeline decision boundaries harder to audit. V2.3 introduces isolated typed contracts, source-specific extractors, deterministic tests, artifact/SQLite persistence, and a controlled live dry-run harness.

## Selected sources

### Core production-candidate after review

Observed local dry-run status matters more than bundle intent. In the current repo state, `forebet` and `predictz` must be treated as `fixture_snapshot_only/manual_review/no_live_fetch` because live entrypoints are not eligible for promotion after review-gate tightening and prior robots-block observations.

1. Sportsgambler — narrative/team-news/statistical context. Extracts fixture, market claim, reasoning, injuries, predicted lineups, xG/xGA/xA/PPDA, form and odds/weather context.
2. Forebet — structured model table. Extracts 1/X/2 probabilities, predicted outcome, correct score, avg goals and model-signal fields from fixture snapshots; no live-fetch promotion.
3. PredictZ — daily market/form table. Extracts market page context, last-5 form, displayed odds and score/BTTS/O-U context from fixture snapshots; no live-fetch promotion.
4. WinDrawWin — broad league/correct-score/stat source. Extracts score-based market inference, BTTS/O-U/winner context and score model fields.

### Shadow-only/high-noise

5. Feedinco — broad sports/market coverage but high affiliate/noise. Strict garbage gate; no production promotion in v2.3.
6. BettingClosed — index/detail guard only. Never fabricate picks from loading/index/count pages.

### Research/manual review only

BetMines and SportyTrader remain research-only. PicksWise, OLBG and bettingexpert remain manual-review-only, not production scrape targets in v2.3.

## Added files

```text
src/bet/tipsters/contracts.py
src/bet/tipsters/compliance.py
src/bet/tipsters/fetcher.py
src/bet/tipsters/html_tools.py
src/bet/tipsters/normalization.py
src/bet/tipsters/market_parser.py
src/bet/tipsters/extractors.py
src/bet/tipsters/pipeline_adapter.py
src/bet/tipsters/source_registry.py
src/bet/tipsters/storage.py
scripts/pipeline_steps/s2_tipsters_v2.py
scripts/pipeline_steps/s2_tipsters_v2_live_dry_run.py
tests/tipsters/test_compliance.py
tests/tipsters/test_extractors.py
tests/tipsters/test_pipeline_adapter.py
tests/tipsters/test_storage.py
docs/pipeline/tipster_terms_review.example.json
install_tipster_scraper_v2_3.fish
```

## Contract

All records are `source_claim_evidence` or source-specific evidence rows. Pipeline consumers must treat them as:

- S2 tipster evidence;
- S3 context/cross-source sanity check;
- S4 market sanity/reference-only support;
- manual Superbet quote review context.

They must not be treated as:

- EV calculation source of truth;
- bettable decision;
- stake instruction;
- coupon construction;
- bookmaker combined odds.

The JSON artifact includes:

```json
{
  "schema_version": "tipster_consensus_v2.3",
  "contract": "evidence_only_not_betting_decision",
  "all_picks": [],
  "consensus": [],
  "pipeline_consumers": ["S3 contextual cross-check", "S4 market sanity", "manual Superbet quote review"],
  "fail_closed": true
}
```

Each legacy-compatible pick includes `decision_boundary=evidence_only_not_a_bet`.

## Compliance model

- `RobotsCache` uses `urllib.robotparser.RobotFileParser`.
- `fetch_public_html` requires `terms_reviewed=True` and compliance allow.
- `s2_tipsters_v2_live_dry_run.py` requires local `tipster_terms_review.local.json` with source-specific attestations.
- `docs/pipeline/tipster_terms_review.local.json` is operator-local only and must not be committed; keep `docs/pipeline/tipster_terms_review.example.json` in git instead.
- Placeholder attestation values such as `REPLACE_WITH_OPERATOR` and `REPLACE_WITH_UTC_TIMESTAMP` are invalid and must produce `INVALID_REVIEW_ATTESTATION`.
- Auth/premium/member/login/VIP paths are blocked.
- Commercial redirect/go/bookmaker paths are blocked in discovery.
- Playwright is not used in v2.3. Stealth and anti-bot bypass are forbidden.

## Parser strategy

- False negatives are acceptable.
- False positives are not acceptable.
- Generic parser exists only as fallback for safe public HTML.
- Valuable source-specific fields must be preserved in `valuable_signals`, `stats_cited`, `source_record_type` and `pipeline_use`.
- Low-quality extraction is surfaced as warning/verdict, not silently promoted.

## Test status from bundle generation

```text
20 passed
compileall PASS
```

## Install command

```fish
fish ~/Downloads/install_tipster_scraper_v2_3.fish --repo=/Users/mkoziol/projects/bet --zip=~/Downloads/tipster_scraper_bundle_v2_3_final.zip --branch=feat/tipster-scraper-v2-3-final
```

## Required live dry-run after implementation

Minimum: `forebet` + `predictz`, one page each, only after local robots/terms/public-only review.

```fish
cd /Users/mkoziol/projects/bet
set -x PYTHONPATH src
set -l RUN_DATE (date +%F)
python3 scripts/pipeline_steps/s2_tipsters_v2_live_dry_run.py \
  --date $RUN_DATE \
  --terms-reviewed-json docs/pipeline/tipster_terms_review.local.json \
  --source forebet \
  --source predictz \
  --max-pages-per-source 1 \
  --timeout-seconds 12 \
  --out /tmp/tipster_consensus_v2_live_$RUN_DATE.json \
  --sqlite-db /tmp/tipster_consensus_v2_live_$RUN_DATE.sqlite
```

The agent must return full stdout/stderr, JSON summary, SQLite counts and block reasons to ChatGPT.

Repo-local summary helper:

```fish
fish scripts/pipeline_steps/tipster_live_summary.fish --json /tmp/tipster_consensus_v2_live_$RUN_DATE.json --sqlite-db /tmp/tipster_consensus_v2_live_$RUN_DATE.sqlite
```
