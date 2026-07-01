import json
from pathlib import Path


WORKSPACE_ROOT = Path("/Users/mkoziol/projects/bet")
DOCS = [
    WORKSPACE_ROOT / "docs/pipeline/Unified Orchestrated Analyst Session Contract.md",
    WORKSPACE_ROOT / "docs/pipeline/Orchestrated Session Continuation Protocol.md",
]
REQUIRED_SNIPPETS = [
    "do not repeat model repair",
    "run J2 only",
]


def validate_resume_prompt(path: Path) -> list[str]:
    failures: list[str] = []
    if not path.exists():
        return [f"missing resume prompt: {path}"]
    content = path.read_text(encoding="utf-8")
    for snippet in REQUIRED_SNIPPETS:
        if snippet not in content:
            failures.append(f"resume prompt missing snippet: {snippet}")
    return failures


def main() -> int:
    failures: list[str] = []
    for doc in DOCS:
        if not doc.exists():
            failures.append(f"missing doc: {doc}")

    continuation_doc = WORKSPACE_ROOT / "docs/pipeline/Orchestrated Session Continuation Protocol.md"
    if continuation_doc.exists():
        failures.extend(validate_resume_prompt(continuation_doc))

    payload = {
        "status": "FAIL" if failures else "PASS",
        "validated_path": str(continuation_doc),
        "failures": failures,
    }
    out_path = WORKSPACE_ROOT / ".kilo/artifacts/orchestrated_session_continuation_audit_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Orchestrated continuation audit: {payload['status']}")
    if failures:
        for failure in failures:
            print(f"- {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
