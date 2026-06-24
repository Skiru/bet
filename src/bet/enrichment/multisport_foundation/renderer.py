from __future__ import annotations

import json
from pathlib import Path

from .plan import build_multisport_wave_plan
from .verifier import verify_plan


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def render_plan_markdown() -> str:
    plan = build_multisport_wave_plan()
    lines = [
        "# Multisport Enrichment Wave Plan",
        "",
        "## Goal",
        "Implement basketball, volleyball, hockey, tennis, CS2, Dota2 and Valorant enrichment as one profile-driven wave, not seven separate mini-football rewrites.",
        "",
        "## Sports",
    ]
    for profile in sorted(plan.profiles.values(), key=lambda item: item.sport.value):
        lines.append(f"- `{profile.sport.value}`: min real mapped providers = {profile.minimum_real_mapped_providers}; providers = {', '.join(profile.provider_candidates)}")
    lines.extend(["", "## Passes"])
    for item in plan.passes:
        lines.extend([
            f"### {item.pass_kind.value}",
            item.objective,
            "",
            "Required gates:",
        ])
        for gate in item.required_gates:
            lines.append(f"- {gate}")
        lines.append("")
    lines.extend(["## Global guardrails"])
    for guardrail in plan.global_guardrails:
        lines.append(f"- {guardrail}")
    return "\n".join(lines)


def render_master_prompt() -> str:
    plan = build_multisport_wave_plan()
    guardrails = "\n".join(f"REQ-GLOBAL-{idx:03d} {item}" for idx, item in enumerate(plan.global_guardrails, start=1))
    sports = ", ".join(sorted(profile.sport.value for profile in plan.profiles.values()))
    return f"""
MODEL=gemini-3.5-flash
REASONING_LEVEL=HIGH
PHASE_ID=MULTISPORT_ENRICHMENT_WAVE_PASS_A_KERNEL_PROFILES

MISSION
Create the profile-driven multisport enrichment foundation for: {sports}.

Use the football enrichment result only as architectural precedent. Do not copy football-specific fixture assumptions.

GLOBAL GUARDRAILS
{guardrails}

PASS MODEL
- Pass A: kernel + sport profiles + provider matrix.
- Pass B: provider corpus/replay + source-bound shadow per sport.
- Pass C: activation candidate + live/fail-closed observation per sport.
- Pass D: final merge gate only.

PASS A ALLOWED PATHS
src/bet/enrichment/multisport_foundation/**
tests/enrichment/multisport_foundation/test_ms_a_*.py
reports/multisport_foundation/pass_a/**
docs/multisport_enrichment/**

PASS A SUCCESS CRITERIA
- seven sport profiles exist and are importable;
- provider matrix covers every sport;
- no fake success status exists;
- blocked/fail-closed status is a valid first-class outcome;
- no production route, betting decision or DB write exists;
- compileall and pytest pass;
- public raw line table is printed after push.
""".strip()


def render_all(out: Path) -> dict[str, str]:
    plan = build_multisport_wave_plan()
    verification = verify_plan()
    outputs = {
        "plan_json": out / "multisport_wave_plan.json",
        "plan_md": out / "multisport_wave_plan.md",
        "master_prompt": out / "multisport_wave_pass_a_prompt.md",
        "verifier_json": out / "verifier_result.json",
    }
    _write_json(outputs["plan_json"], plan.to_json())
    _write_text(outputs["plan_md"], render_plan_markdown())
    _write_text(outputs["master_prompt"], render_master_prompt())
    _write_json(outputs["verifier_json"], verification.to_json())
    return {key: str(value) for key, value in outputs.items()}
