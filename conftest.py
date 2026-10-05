"""Pytest configuration - make the repo root and src/ importable.

`scripts.sofa.*` is imported as a package from the repo root and `bet.sofa`
from src/, without `pip install -e .`. Everything else lives in
tests/sofa/conftest.py.
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent
for _path in (str(_root), str(_root / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)
