from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from bet.enrichment.football_data_foundation.fusion.output import FusionRunSummary

SECRETISH = re.compile(r"(?i)(api[_-]?key|secret|token|authorization|x-api-key|x-auth-token)")
RAWISH = re.compile(r"(?i)(raw_payload|response_body|json_raw|raw_html|<html|payload)")


@dataclass(frozen=True)
class FootballEnrichmentCertificationResult:
    status: str
    selectable_for_production: bool = False
    manual_authorization_required: bool = True
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _clean_text_for_check(text: str) -> str:
    clean = text
    clean = re.sub(r"(?i)manual\s+authorization", "man_auth", clean)
    clean = re.sub(r"(?i)manual_authorization_required", "man_auth", clean)
    clean = clean.replace("payload_policy", "pay_pol")
    clean = clean.replace("payload_hash", "pay_hash")
    clean = clean.replace("payload_byte_count", "pay_bytes")
    clean = clean.replace("payload_record_count", "pay_records")
    return clean


def certify_shadow_football_enrichment(
    summary: FusionRunSummary,
    artifact_paths: Sequence[Path | str]
) -> FootballEnrichmentCertificationResult:
    blockers: list[str] = []
    warnings: list[str] = []

    # 1. artifacts missing => blocker
    if not artifact_paths:
        blockers.append("No artifact paths provided")
    else:
        for path_str in artifact_paths:
            path = Path(path_str)
            if not path.exists():
                blockers.append(f"Artifact does not exist: {path.name}")
            else:
                # 2. raw/secret markers => blocker
                try:
                    text = path.read_text(encoding="utf-8")
                    check_text = _clean_text_for_check(text)
                    if SECRETISH.search(check_text):
                        blockers.append(f"Artifact {path.name} contains secret-like marker")
                    if RAWISH.search(check_text):
                        blockers.append(f"Artifact {path.name} contains raw-payload-like marker")
                except Exception as e:
                    blockers.append(f"Failed to read artifact {path.name}: {e}")

    # 3. required facts missing => blocker
    if summary.missing_fact_types:
        for m_t in summary.missing_fact_types:
            blockers.append(f"Required fact type missing from fusion: {m_t.value}")

    # 4. conflicts => blocker/warning for manual review
    if summary.conflicts:
        for conf in summary.conflicts:
            msg = f"Fusion conflict in {conf.fact_type.value}: {conf.reason}"
            blockers.append(msg)

    # Status determination
    status = (
        "SHADOW_BLOCKED_FOR_MANUAL_REVIEW"
        if blockers
        else "SHADOW_READY_FOR_MANUAL_REVIEW"
    )

    return FootballEnrichmentCertificationResult(
        status=status,
        selectable_for_production=False,
        manual_authorization_required=True,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )
