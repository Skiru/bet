from pathlib import Path


PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / ".kilo"
    / "docs"
    / "betting_run_primary_executor.md"
)


def test_executor_start_prompt_enforces_staged_lossless_run() -> None:
    prompt = PROMPT_PATH.read_text(encoding="utf-8")

    required_markers = (
        "Create and use a fresh RUN_ID",
        "max_events_per_chunk=15` is only a technical shard size",
        "SQLite is the runtime source of truth",
        "JSON is an immutable",
        "At every boundary compare input event IDs",
        "Execute exactly one bounded canonical stage",
        "REQUIRED REPORT AFTER EVERY STAGE",
        "S9 is human-only",
    )
    for marker in required_markers:
        assert marker in prompt

    forbidden_actions = (
        "Never reuse, overwrite, or mutate the historical",
        "Never run the legacy",
        "Do not place bets",
        "Do not invent fixtures",
    )
    for marker in forbidden_actions:
        assert marker in prompt