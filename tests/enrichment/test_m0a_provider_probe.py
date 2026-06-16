import json
import os
import sys
from pathlib import Path
from bet.scrapers.constants import *

def test_m0a_probe_dry_run(tmp_path):
    """Test the m0a probe in dry-run mode."""
    import subprocess
    script = Path(__file__).parent.parent.parent / "scripts" / "enrichment" / "m0a_provider_probe.py"
    # Use sys.executable to ensure we use the same virtual environment
    res = subprocess.run([sys.executable, str(script), "--dry-run", "--output-dir", str(tmp_path)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr

    matrix_file = tmp_path / "m0a_provider_matrix.json"
    assert matrix_file.exists()

    data = json.loads(matrix_file.read_text())
    assert len(data) > 0
    assert data[0]["status"] == "DRY_RUN"

def test_m0a_probe_secret_redaction(tmp_path):
    import subprocess
    script = Path(__file__).parent.parent.parent / "scripts" / "enrichment" / "m0a_provider_probe.py"
    env = os.environ.copy()
    env["SPORTDB_API_KEY"] = "supersecret_sportdb"
    env["API_SPORTS_KEY"] = "supersecret_apisports"
    env["THESPORTSDB_API_KEY"] = "supersecret_thesportsdb"

    res = subprocess.run([sys.executable, str(script), "--dry-run", "--output-dir", str(tmp_path)], capture_output=True, text=True, env=env)
    assert res.returncode == 0

    matrix_file = tmp_path / "m0a_provider_matrix.json"
    data = json.loads(matrix_file.read_text())

    for row in data:
        assert "supersecret" not in row["request_identity"]
