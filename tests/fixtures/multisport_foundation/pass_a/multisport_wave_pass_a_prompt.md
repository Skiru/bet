MODEL=gemini-3.5-flash
REASONING_LEVEL=HIGH
PHASE_ID=MULTISPORT_ENRICHMENT_WAVE_PASS_A_KERNEL_PROFILES

MISSION
Create the profile-driven multisport enrichment foundation for: basketball, cs2, dota2, hockey, tennis, valorant, volleyball.

Use the football enrichment result only as architectural precedent. Do not copy football-specific fixture assumptions.

GLOBAL GUARDRAILS
REQ-GLOBAL-001 no production routing activation
REQ-GLOBAL-002 no betting decisions / picks / stakes / edges
REQ-GLOBAL-003 no production DB writes
REQ-GLOBAL-004 no betting/data writes
REQ-GLOBAL-005 no raw headers, cookies, tokens, API keys or secrets in reports
REQ-GLOBAL-006 no fake success: missing data must be UNKNOWN or BLOCKED
REQ-GLOBAL-007 no fallback provider IDs, scores, status, venue or roster values
REQ-GLOBAL-008 public raw line table required after push
REQ-GLOBAL-009 status may be fail-closed observation and still pass verifier

PASS MODEL
- Pass A: kernel + sport profiles + provider matrix.
- Pass B: provider corpus/replay + source-bound shadow per sport.
- Pass C: activation candidate + live/fail-closed observation per sport.
- Pass D: final merge gate only.

PASS A ALLOWED PATHS
src/bet/enrichment/multisport_foundation/**
tests/enrichment/multisport_foundation/test_ms_a_*.py
reports/multisport_foundation/pass_a/**
docs/multisport_enrichment/**

PASS A SUCCESS CRITERIA
- seven sport profiles exist and are importable;
- provider matrix covers every sport;
- no fake success status exists;
- blocked/fail-closed status is a valid first-class outcome;
- no production route, betting decision or DB write exists;
- compileall and pytest pass;
- public raw line table is printed after push.
