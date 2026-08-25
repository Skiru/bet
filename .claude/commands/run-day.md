---
description: Run today's betting day (DISCOVER -> ENRICH -> ANALYZE) and produce the per-match read.
---

Run the betting day, then analyse it. Two agents, in order. Do not skip step 1
and analyse yesterday's artifact.

**1. `bet-simple` — run the day.**
Preflight first (`python3 scripts/simple/run_pipeline.py --preflight`), quote the
advice line, then `python3 scripts/simple/run_pipeline.py -v` (`--date` if the
user named another day, `--max-events N` if preflight recommended a lower cap).
Never `--skip-preflight`.

It must report: the verdict, run_id, discovered-vs-enriched counts, every
provider that was unavailable with its `kind`, and every identity-resolution
failure by club and provider.

If the verdict is `PRECONDITION_FAILED` or `FAILED`, stop here and report what a
human has to change. Do not start the analyst on an artifact that does not exist.

**2. `bet-analyst` — read it.**
Per match: which totals lean OVER/UNDER at which line, the per-side observation
split, the evidence tier, and the minimum odds each lean needs. It cross-checks
the DB for matches from earlier runs of the same day, and may use WebFetch to
confirm a fixture is still on or to resolve a club a provider could not match —
web evidence can veto or caveat a row, never promote one.

**Report both**: the run's verdict and evidence trail, then the per-match read.
Name the run_id and the stats sheet path.

The deliverable is analysis. No price, no EV, no stake, no coupon — the operator
checks the quotes and places the bet by hand.

$ARGUMENTS
