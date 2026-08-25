# BET PIPELINE V5 — External Acceptance Harness

This directory contains the reproducible acceptance harness for evaluating requirements ACC-001 through ACC-038 against any checkout of the repository.

## Usage

```bash
python3 tools/v5_acceptance/external_acceptance.py --repo-root . --json-out /tmp/acc_report.json --junit-out /tmp/acc_junit.xml
```

Arguments:
- `--repo-root` (or `--target`): Path to repository root.
- `--json-out`: Path to write the JSON report.
- `--junit-out`: Path to write the JUnit XML report.
