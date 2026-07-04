# Legacy Source Selector Design for S2 tipsters

This document defines the safe design for adding a source selector to the legacy tipster aggregator and cross-reference pipelines.

## Motivation
Currently, running `scripts/tipster_aggregator.py` fetches and aggregates all configured S2 tipster sources in parallel. With the introduction of Pass C safe transports and compliance-first gates, we need a way to selectively run and test specific legacy sources (e.g., `--source zawodtyper`) without triggering broad live fetches across unreviewed or restricted websites.

## Proposed Command Line Interface (CLI)

Both `scripts/pipeline_steps/s2_tipsters.py` and `scripts/tipster_aggregator.py` will accept an optional `--source` / `--source-id` parameter.

```bash
# Aggregator specific target run
.venv-tipster-v2/bin/python scripts/tipster_aggregator.py \
  --date 2026-07-04 \
  --source zawodtyper
```

```bash
# Wrapper integration step run
.venv-tipster-v2/bin/python scripts/pipeline_steps/s2_tipsters.py \
  --date 2026-07-04 \
  --source zawodtyper
```

## Implementation Strategy

### 1. Update `scripts/tipster_aggregator.py`

Modify the `ArgumentParser` to accept `--source`:
```python
parser.add_argument("--source", action="append", help="Filter/restrict aggregation to specific source IDs (repeatable)")
```

Inside `run_tipster_aggregation`, apply the source filter to the list of tasks/sites to process:
```python
def run_tipster_aggregation(date_str, max_workers=5, sport_filter=None, use_gemini=False, source_filter=None):
    # Retrieve all configured S2 contracts
    contracts = list(TIPSTER_SOURCE_CONTRACTS)
    
    # If a source filter is supplied, restrict the contracts list
    if source_filter:
        source_filter_set = {s.lower().strip() for s in source_filter}
        contracts = [c for c in contracts if c.source_id in source_filter_set]
        
    # Proceed with parallel execution only for the selected contracts
    # ...
```

### 2. Update `scripts/pipeline_steps/s2_tipsters.py`

Modify the `main` entrypoint of the step wrapper to pass `--source` downstream:
```python
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", "--betting-day", dest="date", help="YYYY-MM-DD", default=None)
    p.add_argument("--source", action="append", help="Source ID filter passed down to aggregator", default=None)
    # ...
    args = p.parse_args()

    # Pass the source filter downstream to the aggregator script args
    aggregator_args = []
    if args.source:
        for s in args.source:
            aggregator_args.extend(["--source", s])

    # Run scripts with inherited arguments safely
    # ...
```

## Security & Verification Benefits
1. **Granular Verification**: Enables rapid, isolated testing of safe transports during development.
2. **Fail-Closed Default**: Ensures that running the aggregator doesn't fetch unreviewed sources by allowing operators to only fetch those that have been audited and certified.
3. **No Unintentional Net Traffic**: Safe shadow-only and evidence-only validation is fully isolated and decoupled.
