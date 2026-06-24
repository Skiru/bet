from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"


def test_multisport_import_does_not_eagerly_require_pandas() -> None:
    script = r'''
import importlib.abc
import sys

class BlockPandas(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "pandas" or fullname.startswith("pandas."):
            raise ModuleNotFoundError("blocked pandas during multisport import isolation test")
        return None

sys.meta_path.insert(0, BlockPandas())
import bet.enrichment.multisport_foundation.source_inventory as source_inventory
assert source_inventory.TARGET_SPORTS
assert "pandas" not in sys.modules
'''
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    script = f"import sys; sys.path.insert(0, {str(SRC)!r});" + script
    result = subprocess.run(
        [sys.executable, "-S", "-c", script],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout


def test_parent_enrichment_exports_are_lazy_and_declared() -> None:
    script = r'''
import importlib.abc
import sys

class BlockPandas(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "pandas" or fullname.startswith("pandas."):
            raise ModuleNotFoundError("blocked pandas during lazy export declaration test")
        return None

sys.meta_path.insert(0, BlockPandas())
import bet.enrichment as enrichment
assert "RawFootballDataBundle" in enrichment.__all__
assert "compute_schema_fingerprint" in enrichment.__all__
assert "pandas" not in sys.modules
'''
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    script = f"import sys; sys.path.insert(0, {str(SRC)!r});" + script
    result = subprocess.run(
        [sys.executable, "-S", "-c", script],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
