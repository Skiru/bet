# Execution Spine

This is the reusable coordination loop for bet workflow entry points.

## Spine

1. Establish scope and entry point.
2. Load the canonical instructions and the task-specific domain skill.
3. Gather the minimum context needed to start.
4. Run the step's script or direct lookup.
5. Read the full output before deciding anything.
6. Delegate finished output to the correct specialist using the handoff contract.
7. Apply the matching resume or stop gate.
8. Synthesize the result and persist a short handoff note when useful.
9. Advance only when the next stage has a valid upstream artifact.

## Practical Rule

Keep the execution spine in the workflow skill, not in every prompt. A prompt may name the stage order, but the reusable loop lives here.