# 01 Deep Stats Takeover Status

The orchestrator inspected the active or recent deep stats process.

Status:
- Process is not running (DEEP_STATS_PROCESS_NOT_RUNNING).
- The previous run has completed or was terminated.

Rules:
- Missing injuries table is treated as DATA_GAP_MISSING_INJURIES_TABLE, not as automatic session failure.
- Injuries/standings fields must be UNKNOWN when unavailable.
- No process was killed by this takeover step.
