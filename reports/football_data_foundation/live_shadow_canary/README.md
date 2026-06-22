# Live Shadow Canary Report Directory

This directory contains reports and results for the bounded live shadow canary run of the football enrichment engine.

## Operating Rules

- **Bounded Live Shadow Only**: This execution is strictly a sandboxed run to verify the integrated pipeline and contracts.
- **No Production Selection Allowed**: All reports and certifications are flagged with false selectability. No manual selection can promote these.
- **No Betting Selections or Choices**: No betting selections or decisions are made or written.
- **No Database Modification**: Absolutely no database writes, no inserts, no updates, and no deletes are made to any database.
- **Single Official Web-Page Context Call**: A maximum of one request is made to the official FIFA scores URL to retrieve live context.
- **Single Provider Endpoint Call**: A maximum of one request per credentialed provider is allowed.
- **Credential Key Gate**: Missing credential keys (such as API keys/tokens) will cause providers to be skipped gracefully rather than triggering a failure.
- **Official Context Only**: FIFA data serves strictly as reference metadata context.
- **Canary Scenario**: World Cup 2026 is strictly used as a canary test case context; the domain logic itself remains generic for any football match context.
