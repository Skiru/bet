# Resume / Stop Gates

These are the reusable gates for coordinated bet workflows.

## Stop Conditions

- Stop if the upstream artifact is missing, stale, or malformed.
- Stop if a required validation gate failed and has not been fixed.
- Stop if the task needs a user decision before the next stage can continue.
- Stop if a specialist returned incomplete output that does not match the handoff contract.

## Resume Conditions

- Resume after the missing input, artifact, or correction is available.
- Resume after the specialist returned a complete verdict and the downstream stage has the right context.
- Resume after a paused session has a saved checkpoint or short handoff note.

## Workflow Notes

- If the same context will be reused by the next stage, persist the summary once and move on.
- If a late data change alters the thesis, pause the current stage and re-run the most relevant specialist instead of forcing the old result through.