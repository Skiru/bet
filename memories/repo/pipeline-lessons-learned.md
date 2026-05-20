# Pipeline Lessons Learned

- `team_form` is the downstream contract for S3. Do not treat scraper-only tables as proof that enrichment succeeded.
- DB-first means DB is authoritative when present. JSON is fallback only, not a "larger wins" override.
- `src/bet/stats/fallback_chains.py` is the canonical provider-order source. Docs and prompts should point to it, not duplicate chain order inline.
- Removed scripts must lose their tests and prompt references in the same change. Keeping stale test imports will break pytest collection.
- Branch B settlement is final. Do not reopen settlement behavior while working on unrelated enrichment or documentation slices.
- Flashscore tokenized deep stats feed is retired. Any remaining Flashscore use must be explicit, narrow, and consistent with current policy.
- Betclic learning output is advisory only. Never turn hit-rate summaries into automatic market rejection.
- For broader architecture details, read `pipeline-knowledge-base.md` and `pipeline-bugs-and-fixes.md` alongside this file.