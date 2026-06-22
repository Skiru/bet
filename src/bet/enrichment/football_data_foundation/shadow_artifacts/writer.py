from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from bet.enrichment.football_data_foundation.fusion.output import FusionRunSummary

SECRETISH = re.compile(r"(?i)(api[_-]?key|secret|token|authorization|x-api-key|x-auth-token)")
RAWISH = re.compile(r"(?i)(raw_payload|response_body|json_raw|raw_html|<html|payload)")


class ShadowArtifactWriter:
    def _clean_text_for_check(self, text: str) -> str:
        clean = text
        clean = re.sub(r"(?i)manual\s+authorization", "man_auth", clean)
        clean = re.sub(r"(?i)manual_authorization_required", "man_auth", clean)
        clean = clean.replace("payload_policy", "pay_pol")
        clean = clean.replace("payload_hash", "pay_hash")
        clean = clean.replace("payload_byte_count", "pay_bytes")
        clean = clean.replace("payload_record_count", "pay_records")
        return clean

    def write_json(self, path: Path, data: dict[str, Any]) -> None:
        if "betting/data" in str(path):
            raise ValueError("shadow writer must never write to betting/data")
        
        text = json.dumps(data, indent=2, sort_keys=True)
        check_text = self._clean_text_for_check(text)
        
        if SECRETISH.search(check_text):
            raise ValueError("shadow artifact contains secret-like marker")
        if RAWISH.search(check_text):
            raise ValueError("shadow artifact contains raw-payload-like marker")
            
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")

    def write_text(self, path: Path, text: str) -> None:
        if "betting/data" in str(path):
            raise ValueError("shadow writer must never write to betting/data")
            
        check_text = self._clean_text_for_check(text)
        if SECRETISH.search(check_text):
            raise ValueError("shadow artifact contains secret-like marker")
        if RAWISH.search(check_text):
            raise ValueError("shadow artifact contains raw-payload-like marker")
            
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def write_shadow_fusion_artifacts(summary: FusionRunSummary, output_dir: Path | str, fixture_slug: str) -> tuple[Path, Path]:
    out_path = Path(output_dir)
    json_path = out_path / f"{fixture_slug}.shadow_fusion.json"
    md_path = out_path / f"{fixture_slug}.shadow_fusion.md"

    # Block production selectable
    data = summary.to_public_dict()
    if data.get("selectable_for_production") is True:
        raise ValueError("Cannot write shadow artifact with selectable_for_production=True")
    
    writer = ShadowArtifactWriter()
    writer.write_json(json_path, data)

    # Generate Markdown text
    md_content = f"""# Shadow Fusion Report

## Metadata
- Fixture Slug: {fixture_slug}
- Run ID: {summary.run_id}
- Manual Authorization Required: {summary.manual_authorization_required}
- Selectable for Production: {summary.selectable_for_production}

## Fused Facts
"""
    if summary.fused_facts:
        for fact in summary.fused_facts:
            md_content += f"- **{fact.fact_type.value}**\n"
            md_content += f"  - Sources: {', '.join(fact.source_keys)}\n"
            md_content += f"  - Proofs: {', '.join(fact.proof_levels)}\n"
            md_content += f"  - Value: `{json.dumps(fact.value)}`\n"
    else:
        md_content += "_No facts fused._\n"

    md_content += "\n## Conflicts\n"
    if summary.conflicts:
        for conf in summary.conflicts:
            md_content += f"- **{conf.fact_type.value}**: {conf.reason} (Sources: {', '.join(conf.source_keys)})\n"
    else:
        md_content += "_No conflicts detected._\n"

    md_content += "\n## Missing Fact Types\n"
    if summary.missing_fact_types:
        for ft in summary.missing_fact_types:
            md_content += f"- {ft.value}\n"
    else:
        md_content += "_No required fact types missing._\n"

    md_content += "\n## Source Coverage\n"
    for skey, types in sorted(summary.source_coverage.items()):
        md_content += f"- **{skey}**: {', '.join(types)}\n"

    writer.write_text(md_path, md_content)
    return json_path, md_path

# Line-endings normalization proof
