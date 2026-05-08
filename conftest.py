"""Pytest configuration — ensure scripts/ and src/ are importable.

The adapters use ``from adapters import dedup_results`` (absolute import within
``scripts/``).  When pytest runs from the project root, ``scripts/`` is not on
``sys.path`` by default, so we add it here.  ``src/`` is added so that
``from bet.…`` imports work without ``pip install -e .``.
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent
for _subdir in ("scripts", "src"):
    _path = str(_root / _subdir)
    if _path not in sys.path:
        sys.path.insert(0, _path)
