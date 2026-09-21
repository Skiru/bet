# Football Golden Vertical V3.1 — P00 Corrective Pass

Continue from commit:

`b7bf898509c887613f1d86aa4ab754a282a84446`

Do not start P01 yet.

External review classified this commit as a preserved legacy worktree snapshot,
not as an acceptable atomic P00 commit.

Do not reset, rebase, force-push, clean, or discard any production work contained
in that commit.

Create one small corrective commit:

`fix(P00): restore auditable security baseline`

## 1. Remove diff suppression

Delete the repository rule:

`/KLUCZE?API: -diff`

Remove `.gitattributes` completely if it contains no other valid rules.

Normal textual diffs must remain visible. Never conceal credential-bearing paths
by marking them binary.

## 2. Remove generated repository noise added by the snapshot

Remove the tracked `.DS_Store` and add:

`.DS_Store`

to `.gitignore`.

Remove the typo directory:

`.kilo/artball_all_providers_final/`

Remove these superseded root-level documents:

- `FOOTBALL_GOLDEN_CERTIFICATION_BUNDLE_REVIEW.md`
- `KILO_FOOTBALL_ALL_PROVIDERS_FINAL_PRODUCTION_CLOSURE.md`
- `KILO_FOOTBALL_GOLDEN_TRUTHFUL_FINAL_CLOSURE.md`
- `KILO_FOOTBALL_PROVIDER_DECOUPLED_FINAL_CLOSURE.md`

Remove the stale pre-V3 certification directory:

`.kilo/artifacts/football_all_providers_final/`

Do not remove production source code, migrations, or tests in this corrective
commit. They remain preserved as unreviewed baseline material for P01.

## 3. Install the binding documents at their final paths

The only active binding contract must be:

`docs/prompts/SPORTS_ENRICHMENT_KERNEL_FOOTBALL_GOLDEN_VERTICAL_FINAL_CONTRACT_V3_1.md`

The launcher must be:

`docs/prompts/SPORTS_ENRICHMENT_KERNEL_FOOTBALL_GOLDEN_VERTICAL_LAUNCHER_V3_1.md`

Verify that the launcher's `@` reference resolves to the committed contract.

There must be exactly one active Football Golden Vertical contract.

## 4. Remove committed local backup material

Delete:

`.kilo/artifacts/football_golden_v3/backup.patch`

Add the minimal ignore rule:

`.kilo/artifacts/**/backup.patch`

Backup patches are local safety material and must not be committed.

## 5. Correct the checkpoint

Update:

`.kilo/artifacts/football_golden_v3/checkpoint.json`

It must truthfully record:

- reviewed public baseline:
  `ad9f6a8a2deefb5541a5ef3bb3ddd486754f58e0`;
- preserved legacy snapshot:
  `b7bf898509c887613f1d86aa4ab754a282a84446`;
- current correction parent:
  `b7bf898509c887613f1d86aa4ab754a282a84446`;
- actual current branch;
- exact changed files of this corrective commit;
- P00 status;
- credential rotation attestation without values or value-derived hashes;
- current-tree scan result;
- diff/artifact scan result;
- explicit note that production code already present in `b7bf898` is
  unreviewed baseline material and will be classified in P01;
- next phase: `P01_PENDING_EXTERNAL_REVIEW`.

Do not claim that `b7bf898` itself was an atomic P00 commit.

## 6. Re-run security and hygiene checks

Scan without printing secret values:

- tracked current tree;
- staged and unstaged diff;
- untracked task artifacts;
- `.kilo/artifacts/football_golden_v3`;
- prompt and configuration files.

Verify:

- no active private credential exists;
- the deleted credential note remains absent;
- no diff suppression remains;
- no `.DS_Store` is tracked;
- no backup patch is tracked;
- exactly one active V3.1 contract exists;
- no old certification artifact can be mistaken for current truth.

Do not rerun the full test suite.

Run only:

- `git diff --check`;
- JSON parse validation for checkpoint;
- binding-contract path existence check;
- secret-safe scan;
- `git status` verification.

## 7. Commit and stop

Stage only the P00 correction files.

Review:

```bash
git diff --cached --stat
git diff --cached --name-only
```

The commit must not include:

- `src/` changes;
- test changes;
- migrations;
- `kilo.jsonc`;
- provider evidence;
- unrelated formatting.

Create and push:

`fix(P00): restore auditable security baseline`

Do not start P01.

Return only:

```text
PHASE: P00-CORRECTION
RESULT: PASS | FAIL
REASONING_USED: MEDIUM
LEGACY_SNAPSHOT: b7bf898509c887613f1d86aa4ab754a282a84446
COMMIT_SHA:
PARENT_SHA:
COMMIT_URL:
CONTRACT_PATH:
SECURITY_SCAN:
DIFF_AUDITABILITY:
REMOVED_STALE_ARTIFACTS:
CHANGED_FILES:
GIT_STATUS:
GATE:
NEXT_PHASE: BLOCKED_PENDING_EXTERNAL_REVIEW
BLOCKER:
```
