from __future__ import annotations
import json
from pathlib import Path
from .single_flight_probe import build_default_single_flight_report, validate_single_flight_report

def write_single_flight_reports(base_dir: str | Path) -> None:
    target = Path(base_dir)
    target.mkdir(parents=True, exist_ok=True)
    report = build_default_single_flight_report()
    errors = validate_single_flight_report(report)
    if errors:
        raise ValueError(errors)

    (target / 'single_flight_probe_by_sport.json').write_text(
        json.dumps(report['single_flight_probe_by_sport'], indent=2, sort_keys=True) + '\n',
        encoding='utf-8'
    )
    (target / 'pass_i_summary.json').write_text(
        json.dumps({k: v for k, v in report.items() if k != 'single_flight_probe_by_sport'}, indent=2, sort_keys=True) + '\n',
        encoding='utf-8'
    )
