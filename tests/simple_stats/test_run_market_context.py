import subprocess
import sys
from pathlib import Path
import json

def test_global_exception_handler_on_bad_input_file(tmp_path: Path) -> None:
    """A malformed --event-list file must be caught by the global handler."""
    bad_event_list = tmp_path / "bad_event_list.json"
    bad_event_list.write_text("this is not json")

    # The path to the script to test
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "simple" / "run_market_context.py"

    # Run the script as a subprocess
    result = subprocess.run(
        [sys.executable, str(script_path), "--event-list", str(bad_event_list), "--output-dir", str(tmp_path)],
        capture_output=True,
        text=True,
    )

    # 1. Check that the process exited with code 1 (PARTIAL)
    assert result.returncode == 1, f"Expected exit code 1, but got {result.returncode}. Stderr: {result.stderr}"

    # 2. Check that AGENT_SUMMARY is printed to stdout with the correct verdict
    summary_line = ""
    for line in result.stdout.splitlines():
        if line.startswith("AGENT_SUMMARY:"):
            summary_line = line
            break
    assert summary_line, "AGENT_SUMMARY not found in stdout"

    summary_json = json.loads(summary_line.replace("AGENT_SUMMARY:", ""))
    assert summary_json.get("verdict") == "PARTIAL", f"Expected verdict PARTIAL, but got {summary_json.get('verdict')}"
    assert "error" in summary_json.get("metrics", {}), "Error not in metrics"

    # 3. Check that a traceback was printed to stderr
    assert "Traceback (most recent call last)" in result.stderr, "Traceback not in stderr"