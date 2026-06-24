# Multisport Enrichment Wave Plan

## Goal
Implement basketball, volleyball, hockey, tennis, CS2, Dota2 and Valorant enrichment as one profile-driven wave, not seven separate mini-football rewrites.

## Sports
- `basketball`: min real mapped providers = 2; providers = sportdb, highlightly, api-sports-family, thesportsdb
- `cs2`: min real mapped providers = 1; providers = pandascore, liquipedia-reference, sportdb
- `dota2`: min real mapped providers = 1; providers = pandascore, liquipedia-reference, sportdb
- `hockey`: min real mapped providers = 2; providers = sportdb, highlightly, api-sports-family, thesportsdb
- `tennis`: min real mapped providers = 2; providers = sportdb, highlightly, thesportsdb
- `valorant`: min real mapped providers = 1; providers = pandascore, liquipedia-reference, sportdb
- `volleyball`: min real mapped providers = 2; providers = highlightly, api-sports-family, thesportsdb

## Passes
### MS-A_KERNEL_PROFILES
Create shared multisport kernel, sport profiles, provider capability matrix and fail-closed contracts.

Required gates:
- profile completeness for all seven sports
- provider matrix coverage
- no fallback-success statuses
- compileall
- pytest targeted
- public raw reviewability

### MS-B_PROVIDER_CORPUS_SHADOW
Capture/replay provider responses and build source-bound shadow artifacts per sport profile.

Required gates:
- real HTTP/replay envelope proof
- sanitized cache only
- per-sport blocked statuses allowed
- no fake mapped fixture
- compileall
- pytest targeted
- public raw line table

### MS-C_ACTIVATION_LIVE_OBSERVATION
Create shadow-only activation candidates and bounded live/fail-closed observation reports per sport.

Required gates:
- activation candidate remains shadow-only
- live observation accepts fail-closed blocked outcome
- no betting decisions
- no production selectable flag
- compileall
- pytest targeted
- public raw line table

### MS-D_FINAL_MERGE_GATE
Merge multisport foundation to main only after source-bound evidence, tests and public raw gates pass.

Required gates:
- feature head exact check
- main worktree clean
- merge --no-commit
- post-merge compileall
- post-merge pytest targeted
- artifact evidence check
- public main raw table

## Global guardrails
- no production routing activation
- no betting decisions / picks / stakes / edges
- no production DB writes
- no betting/data writes
- no raw headers, cookies, tokens, API keys or secrets in reports
- no fake success: missing data must be UNKNOWN or BLOCKED
- no fallback provider IDs, scores, status, venue or roster values
- public raw line table required after push
- status may be fail-closed observation and still pass verifier
