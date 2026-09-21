# Football Golden Vertical V3.1 — Phase External Review Gate

Use this prompt at the end of every implementation phase.

Before starting the next phase, stop and prepare the current phase for external
code review.

Do not continue to the next phase.

1. Re-read the current phase requirements and exit gate from the binding V3.1
   contract.

2. Verify that the phase changes are strictly scoped and do not include:

   - unrelated sports;
   - unrelated refactors;
   - generated ZIP files;
   - prompt copies;
   - `.DS_Store`;
   - credentials;
   - large transient logs;
   - repository-wide Ruff cleanup.

3. Update:

`.kilo/artifacts/football_golden_v3/checkpoint.json`

4. Run only the tests and checks required by the current phase.

5. Review the complete staged diff before committing.

6. Create one atomic commit with the format:

`phase(PXX): <concise completed outcome>`

If the phase gate failed but a diagnostic commit is required, use:

`wip(PXX): <exact unresolved blocker>`

7. Push the commit to the current review branch.

8. Do not squash previous phase commits.

9. Do not begin the next phase until the commit has been externally reviewed
   and explicitly accepted.

Return only:

```text
PHASE:
PHASE_GATE: PASS | FAIL
COMMIT_SHA:
PARENT_SHA:
COMMIT_URL:
CHECKPOINT:
TESTS:
LIVE_REQUESTS:
BUNDLE_IDS:
EVIDENCE_PATHS:
GIT_STATUS:
UNCOMMITTED_UNRELATED_FILES:
NEXT_PHASE: BLOCKED_PENDING_EXTERNAL_REVIEW
BLOCKER:
```
