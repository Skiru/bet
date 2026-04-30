"""Pytest configuration — ensure scripts/ is importable as a package root.

The adapters use ``from adapters import dedup_results`` (absolute import within
``scripts/``).  When pytest runs from the project root, ``scripts/`` is not on
``sys.path`` by default, so we add it here.
"""
import sys
from pathlib import Path

_scripts_dir = str(Path(__file__).resolve().parent / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)
