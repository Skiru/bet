import json
import subprocess


def test_cli_e2e(tmp_path):
    db_path = tmp_path / "test.db"

    # Run bootstrap
    res = subprocess.run([
        "/Users/mkoziol/projects/bet/.venv/bin/python", "-m", "scripts.enrichment.football_history",
        "bootstrap",
        "--db", str(db_path),
        "--competition-id", "39",
        "--season", "2023",
        "--from", "2023-01-01",
        "--to", "2023-01-02"
    ], capture_output=True, text=True, env={"PYTHONPATH": "src", "MOCK_CLI_ACQUISITION": "1"})

    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data["mode"] == "BOOTSTRAP"
    assert "status" in data

    # Run incremental
    res2 = subprocess.run([
        "/Users/mkoziol/projects/bet/.venv/bin/python", "-m", "scripts.enrichment.football_history",
        "incremental-sync",
        "--db", str(db_path),
        "--competition-id", "39",
        "--season", "2023"
    ], capture_output=True, text=True, env={"PYTHONPATH": "src", "MOCK_CLI_ACQUISITION": "1"})
    assert res2.returncode == 0

    # Run replay
    res3 = subprocess.run([
        "/Users/mkoziol/projects/bet/.venv/bin/python", "-m", "scripts.enrichment.football_history",
        "replay",
        "--db", str(db_path),
        "--evidence-bundle", "b1"
    ], capture_output=True, text=True, env={"PYTHONPATH": "src", "MOCK_CLI_ACQUISITION": "1"})
    assert res3.returncode == 0

    # Run snapshot
    res4 = subprocess.run([
        "/Users/mkoziol/projects/bet/.venv/bin/python", "-m", "scripts.enrichment.football_history",
        "build-snapshot",
        "--db", str(db_path),
        "--canonical-target-fixture-id", "1",
        "--analysis-cutoff-at", "2023-01-01T00:00:00Z",
        "--policy-version", "1"
    ], capture_output=True, text=True, env={"PYTHONPATH": "src", "MOCK_CLI_ACQUISITION": "1"})
    assert res4.returncode == 0

    # Run inspect
    res5 = subprocess.run([
        "/Users/mkoziol/projects/bet/.venv/bin/python", "-m", "scripts.enrichment.football_history",
        "inspect",
        "--db", str(db_path),
        "--fixture-id", "1"
    ], capture_output=True, text=True, env={"PYTHONPATH": "src", "MOCK_CLI_ACQUISITION": "1"})
    assert res5.returncode == 0

