# Full Analytical Session Release Package Quality

## Package Outcome

- package path: `/private/tmp/premerge_probability_release_smoke_a/data/2026-06-29_s8_coupon_drafts.json`
- package type: `RESEARCH_GAP_PACKAGE`
- drafts emitted: `0`
- analytical ready candidates: `0`
- blocked probability missing: `11`
- blocked identity missing: `18`
- blocked stats missing: `0`

## Candidate Quality Verdict

- event identity propagation: partial
  - fixture identity survived, but `18` candidates still lacked a contract-safe `market_family` handoff.
- market-family mapping: fail-closed
  - no candidate with missing market family was promoted.
- model probability quality: fail-closed
  - `11` candidates were kept as research gaps with exact reason `NO_STATS_DATA_FOR_MODEL_PROBABILITY`.
- bookmaker implied probability as model probability: blocked
  - no candidate in the emitted package used bookmaker implied probability as promoted model probability.
- low-confidence guidance: blocked
  - the repaired bridge would not promote `LOW`/`MINIMAL` confidence as analytical-ready.

## Why No Analytical Suggestion Was Emitted

- no candidate satisfied the joint requirements for:
  - market-family mapping,
  - contract-safe market line/direction semantics,
  - model probability backed by stats,
  - supporting evidence pack.

## Placement Safety

- manual operator quote checklist present: `not applicable`
  - no candidate reached `ANALYTICAL_ONLY` or manual quote review state.
- `BETTABLE_MANUAL_ONLY` candidates present: `0`
- reason package is not placement-ready:
  - upstream data gaps prevented any candidate from reaching a reviewable analytical state.
