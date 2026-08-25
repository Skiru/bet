---
description: Run today's betting day end to end (DISCOVER -> ENRICH -> ANALYZE) and report the stats sheet.
agent: bet-simple
---

First run `python3 scripts/simple/run_pipeline.py --preflight` and report its advice line. It spends nothing.

Then run `python3 scripts/simple/run_pipeline.py -v` (add `--date YYYY-MM-DD` if the user named a day other than today, and `--max-events N` if preflight recommended a lower cap).

Do not modify project files. Do not pass `--skip-preflight`.

Report per the bet-simple output schema. Name the run_id, the stats sheet path, the readiness split, and every unavailable provider with its `kind`. If the verdict is `PRECONDITION_FAILED`, stop and report what a human has to change — do not retry.
