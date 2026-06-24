from __future__ import annotations

from .contracts import MultisportPlan, OutcomeStatus, PassDefinition, PassKind
from .profiles import build_sport_profiles
from .providers import build_provider_profiles

GLOBAL_GUARDRAILS = (
    "no production routing activation",
    "no betting decisions / picks / stakes / edges",
    "no production DB writes",
    "no betting/data writes",
    "no raw headers, cookies, tokens, API keys or secrets in reports",
    "no fake success: missing data must be UNKNOWN or BLOCKED",
    "no fallback provider IDs, scores, status, venue or roster values",
    "public raw line table required after push",
    "status may be fail-closed observation and still pass verifier",
)

COMMON_FORBIDDEN = (
    ".env",
    "betting/**",
    "config/**",
    "configs/**",
    "src/bet/db/**",
    "src/bet/pipeline/**",
    "src/bet/api_clients/**",
)


def build_multisport_wave_plan() -> MultisportPlan:
    passes = (
        PassDefinition(
            pass_kind=PassKind.KERNEL_PROFILES,
            objective="Create shared multisport kernel, sport profiles, provider capability matrix and fail-closed contracts.",
            allowed_paths=(
                "src/bet/enrichment/multisport_foundation/**",
                "tests/enrichment/multisport_foundation/test_ms_a_*.py",
                "reports/multisport_foundation/pass_a/**",
                "docs/multisport_enrichment/**",
            ),
            forbidden_paths=COMMON_FORBIDDEN,
            required_gates=(
                "profile completeness for all seven sports",
                "provider matrix coverage",
                "no fallback-success statuses",
                "compileall",
                "pytest targeted",
                "public raw reviewability",
            ),
            success_statuses=(OutcomeStatus.REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT,),
            agent_must_not=("call live providers", "write production DB", "invent sport-specific schemas"),
        ),
        PassDefinition(
            pass_kind=PassKind.PROVIDER_CORPUS_SHADOW,
            objective="Capture/replay provider responses and build source-bound shadow artifacts per sport profile.",
            allowed_paths=(
                "src/bet/enrichment/multisport_foundation/provider_capture/**",
                "src/bet/enrichment/multisport_foundation/source_bound_shadow/**",
                "tests/enrichment/multisport_foundation/test_ms_b_*.py",
                "reports/multisport_foundation/pass_b/**",
            ),
            forbidden_paths=COMMON_FORBIDDEN,
            required_gates=(
                "real HTTP/replay envelope proof",
                "sanitized cache only",
                "per-sport blocked statuses allowed",
                "no fake mapped fixture",
                "compileall",
                "pytest targeted",
                "public raw line table",
            ),
            success_statuses=(
                OutcomeStatus.SOURCE_BOUND_SHADOW_READY,
                OutcomeStatus.REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT,
                OutcomeStatus.BLOCKED_PROVIDER_ACCESS,
                OutcomeStatus.BLOCKED_NO_CREDENTIALS,
            ),
            agent_must_not=("promote docs-only provider to real proof", "write raw headers", "generate fallback IDs"),
        ),
        PassDefinition(
            pass_kind=PassKind.ACTIVATION_LIVE_OBSERVATION,
            objective="Create shadow-only activation candidates and bounded live/fail-closed observation reports per sport.",
            allowed_paths=(
                "src/bet/enrichment/multisport_foundation/activation/**",
                "src/bet/enrichment/multisport_foundation/live_observation/**",
                "tests/enrichment/multisport_foundation/test_ms_c_*.py",
                "reports/multisport_foundation/pass_c/**",
            ),
            forbidden_paths=COMMON_FORBIDDEN,
            required_gates=(
                "activation candidate remains shadow-only",
                "live observation accepts fail-closed blocked outcome",
                "no betting decisions",
                "no production selectable flag",
                "compileall",
                "pytest targeted",
                "public raw line table",
            ),
            success_statuses=(
                OutcomeStatus.ACTIVATION_CANDIDATE_SHADOW_ONLY,
                OutcomeStatus.REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT,
            ),
            agent_must_not=("force COMPLETE", "activate production route", "write prediction text"),
        ),
        PassDefinition(
            pass_kind=PassKind.FINAL_MERGE_GATE,
            objective="Merge multisport foundation to main only after source-bound evidence, tests and public raw gates pass.",
            allowed_paths=("no code edits; merge only",),
            forbidden_paths=COMMON_FORBIDDEN,
            required_gates=(
                "feature head exact check",
                "main worktree clean",
                "merge --no-commit",
                "post-merge compileall",
                "post-merge pytest targeted",
                "artifact evidence check",
                "public main raw table",
            ),
            success_statuses=(OutcomeStatus.ACTIVATION_CANDIDATE_SHADOW_ONLY,),
            agent_must_not=("repair code during merge", "delete feature branch", "push main before gates"),
        ),
    )
    return MultisportPlan(
        profiles=build_sport_profiles(),
        providers=build_provider_profiles(),
        passes=passes,
        global_guardrails=GLOBAL_GUARDRAILS,
    )
