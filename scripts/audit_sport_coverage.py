#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from bet.pipeline.sport_coverage import (  # noqa: E402
    build_expected_sport_contract,
    build_sport_coverage_matrix,
    build_tennis_wimbledon_audit,
    render_expected_sport_contract_markdown,
    render_sport_coverage_matrix_markdown,
    render_tennis_wimbledon_audit_markdown,
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate sport coverage and Wimbledon audit artifacts")
    parser.add_argument("--date", required=True, help="Betting day YYYY-MM-DD")
    parser.add_argument("--discovery-path", required=True, help="Path to discovery JSON artifact")
    parser.add_argument("--tennis-discovery-path", default=None, help="Optional tennis-only discovery JSON artifact")
    parser.add_argument("--matrix-path", required=True, help="Path to market matrix JSON artifact")
    parser.add_argument("--contract-output", required=True, help="Markdown output path for sport contract")
    parser.add_argument("--coverage-output", required=True, help="Markdown output path for coverage matrix")
    parser.add_argument("--tennis-output", required=True, help="Markdown output path for tennis audit")
    parser.add_argument("--command-run", required=True, help="Repository command used for tennis audit")
    args = parser.parse_args()

    discovery_artifact = _load_json(Path(args.discovery_path))
    tennis_discovery_artifact = _load_json(Path(args.tennis_discovery_path)) if args.tennis_discovery_path else discovery_artifact
    market_matrix = _load_json(Path(args.matrix_path))
    contract = build_expected_sport_contract()
    coverage_matrix = build_sport_coverage_matrix(discovery_artifact, market_matrix, contract)
    tennis_audit = build_tennis_wimbledon_audit(
        tennis_discovery_artifact,
        market_matrix,
        contract,
        betting_day=args.date,
        command_run=args.command_run,
    )

    outputs = {
        Path(args.contract_output): render_expected_sport_contract_markdown(contract),
        Path(args.coverage_output): render_sport_coverage_matrix_markdown(coverage_matrix),
        Path(args.tennis_output): render_tennis_wimbledon_audit_markdown(
            tennis_audit,
            as_of=datetime.now(timezone.utc).isoformat(),
        ),
    }
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    print(f"SPORT_CONTRACT={args.contract_output}")
    print(f"SPORT_COVERAGE_MATRIX={args.coverage_output}")
    print(f"TENNIS_AUDIT={args.tennis_output}")
    print(f"TENNIS_COVERAGE_STATUS={tennis_audit['tennis_coverage_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
