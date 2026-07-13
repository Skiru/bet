"""Tests for Superbet manual quote contract constraints."""
from __future__ import annotations

from pathlib import Path


def test_s7_has_no_automated_operator_validator():
    from scripts.pipeline_steps import s7_validate

    assert s7_validate.SCRIPTS == []
