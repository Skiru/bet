from __future__ import annotations
import json
from pathlib import Path
from .provider_authorization import build_authorization_report, validate_authorization_report

def write_authorization_reports(base_dir: str | Path, env: dict[str, str] | None = None) -> None:
    target = Path(base_dir)
    target.mkdir(parents=True, exist_ok=True)
    report = build_authorization_report(env=env)
    errors = validate_authorization_report(report)
    if errors:
        raise ValueError(errors)
    (target / 'provider_access_by_sport.json').write_text(
        json.dumps(report['provider_access_by_sport'], indent=2, sort_keys=True) + '\n',
        encoding='utf-8'
    )
    (target / 'pass_h_summary.json').write_text(
        json.dumps({k: v for k, v in report.items() if k != 'provider_access_by_sport'}, indent=2, sort_keys=True) + '\n',
        encoding='utf-8'
    )
