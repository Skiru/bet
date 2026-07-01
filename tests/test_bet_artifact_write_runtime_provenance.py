import json
import subprocess
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOL_PATH = PROJECT_ROOT / ".kilo" / "tool" / "bet_artifact_write.ts"
PLUGIN_PATH = PROJECT_ROOT / ".kilo" / "plugin" / "bet_artifact_write.ts"
PLUGIN_TOOL_DIST = PROJECT_ROOT / ".kilo" / "node_modules" / "@kilocode" / "plugin" / "dist" / "tool.js"


def read_tool_content() -> str:
    return TOOL_PATH.read_text(encoding="utf-8")


def read_plugin_content() -> str:
    return PLUGIN_PATH.read_text(encoding="utf-8")


def _prepare_repo_root(repo_root: Path) -> None:
    (repo_root / ".kilo" / "state").mkdir(parents=True, exist_ok=True)
    (repo_root / "reports" / "betting-demo").mkdir(parents=True, exist_ok=True)
    (repo_root / "reports" / "betting").mkdir(parents=True, exist_ok=True)
    (repo_root / "reports" / "pipeline_runs").mkdir(parents=True, exist_ok=True)


def _runner_source() -> str:
    return """
import { pathToFileURL } from "node:url"

async function main() {
  const [, , harnessPath, repoRoot, rawArgs] = process.argv
  const toolModule = await import(pathToFileURL(harnessPath).href)
  const toolDef = toolModule.default
  const args = JSON.parse(rawArgs)

  const result = await toolDef.execute(args, {
    sessionID: "pytest-session",
    messageID: "pytest-message",
    agent: "pytest",
    directory: repoRoot,
    worktree: repoRoot,
    abort: new AbortController().signal,
    metadata() {},
    ask() {
      throw new Error("ask must not be called")
    },
  })

  const parsed = typeof result === "string" ? JSON.parse(result) : JSON.parse(result.output)
  process.stdout.write(JSON.stringify(parsed))
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
""".strip()


def invoke_active_tool_in_repo(repo_root: Path, args: dict) -> dict:
    _prepare_repo_root(repo_root)

    harness_path = repo_root / "bet_artifact_write.harness.ts"
    source = read_tool_content().replace(
        'from "@kilocode/plugin/tool"',
        f'from {json.dumps(PLUGIN_TOOL_DIST.as_uri())}',
    )
    harness_path.write_text(source, encoding="utf-8")

    runner_path = repo_root / "invoke.ts"
    runner_path.write_text(_runner_source(), encoding="utf-8")

    command = [
        "npx",
        "-y",
        "tsx",
        str(runner_path),
        str(harness_path),
        str(repo_root),
        json.dumps(args),
    ]
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def invoke_active_tool(args: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="bet-artifact-write-provenance-") as tmpdir:
        return invoke_active_tool_in_repo(Path(tmpdir), args)


def test_active_tool_source_has_version_marker_and_report_root() -> None:
    content = read_tool_content()

    assert 'const TOOL_VERSION = "standalone-pipeline-runs-v2"' in content
    assert 'const SCHEMA_VERSION = 2' in content
    assert '"reports/pipeline_runs"' in content
    assert "allowed_report_roots" in content
    assert "supports_reports_pipeline_runs" in content
    assert "security" in content
    assert "plugin_version" not in content


def test_success_response_exposes_runtime_provenance() -> None:
    response = invoke_active_tool(
        {
            "path": "reports/pipeline_runs/test-run/runtime-provenance.json",
            "content": json.dumps({"status": "ok"}),
            "content_type": "json",
            "create_only": True,
        }
    )

    assert response["status"] == "success"
    assert response["schema_version"] == 2
    assert response["tool"] == "bet_artifact_write"
    assert response["tool_version"] == "standalone-pipeline-runs-v2"
    assert response["supports_reports_pipeline_runs"] is True
    assert "reports/pipeline_runs" in response["allowed_report_roots"]
    assert response["security"] == {
        "path_traversal_blocked": True,
        "secret_detection_enabled": True,
        "json_validation_enabled": True,
        "extension_validation_enabled": True,
        "cas_overwrite_protection_enabled": True,
    }


def test_path_not_allowed_response_includes_allowed_roots() -> None:
    response = invoke_active_tool(
        {
            "path": "reports/other/test-run/outside.json",
            "content": json.dumps({"status": "blocked"}),
            "content_type": "json",
            "create_only": True,
        }
    )

    assert response["status"] == "blocked"
    assert response["error_code"] == "PATH_NOT_ALLOWED"
    assert response["tool_version"] == "standalone-pipeline-runs-v2"
    assert response["allowed_report_roots"] == [
        "reports/betting-demo",
        "reports/betting",
        "reports/pipeline_runs",
    ]


def test_security_guards_remain_intact() -> None:
    traversal = invoke_active_tool(
        {
            "path": "reports/pipeline_runs/test-run/../../escape.json",
            "content": json.dumps({"status": "blocked"}),
            "content_type": "json",
            "create_only": True,
        }
    )
    assert traversal["error_code"] == "PATH_TRAVERSAL"

    secret = invoke_active_tool(
        {
            "path": "reports/pipeline_runs/test-run/secret.md",
            "content": "token: secret_value",
            "content_type": "markdown",
            "create_only": True,
        }
    )
    assert secret["error_code"] == "CONTENT_SECRET_DETECTED"

    invalid_json = invoke_active_tool(
        {
            "path": "reports/pipeline_runs/test-run/invalid.json",
            "content": "{invalid}",
            "content_type": "json",
            "create_only": True,
        }
    )
    assert invalid_json["error_code"] == "CONTENT_INVALID_JSON"

    wrong_extension = invoke_active_tool(
        {
            "path": "reports/pipeline_runs/test-run/wrong.txt",
            "content": json.dumps({"status": "blocked"}),
            "content_type": "json",
            "create_only": True,
        }
    )
    assert wrong_extension["error_code"] == "EXTENSION_MISMATCH"


def test_cas_overwrite_protection_remains_intact() -> None:
    with tempfile.TemporaryDirectory(prefix="bet-artifact-write-cas-") as tmpdir:
        repo_root = Path(tmpdir)

        first = invoke_active_tool_in_repo(
            repo_root,
            {
                "path": "reports/pipeline_runs/test-run/cas.json",
                "content": json.dumps({"status": "first"}),
                "content_type": "json",
                "create_only": True,
            }
        )
        assert first["status"] == "success"

        second = invoke_active_tool_in_repo(
            repo_root,
            {
                "path": "reports/pipeline_runs/test-run/cas.json",
                "content": json.dumps({"status": "second"}),
                "content_type": "json",
                "create_only": False,
            }
        )
        assert second["error_code"] == "EXPECTED_HASH_REQUIRED"
        assert second["security"]["cas_overwrite_protection_enabled"] is True


def test_disabled_plugin_preserves_provenance_without_registration() -> None:
    content = read_plugin_content()

    assert "export default tool(" not in content
    assert 'registers_tool_name: false' in content
    assert 'single_source_strategy: "STANDALONE_TOOL_SINGLE_SOURCE"' in content
