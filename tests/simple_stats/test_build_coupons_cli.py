"""CLI-level tests for scripts/simple/build_coupons.py's --vetoes flag.

The library-level behavior (VETO excludes, DOWNGRADE steps a tier once, notes
report the reason) is covered in tests/simple_stats/test_coupons.py. This file
only exercises the argument wiring: a missing/absent vetoes file must behave
like "no vetoes" -- the default healthy state -- not an error.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "simple" / "build_coupons.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_coupons_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def module():
    return _load_module()


def _write_sheet(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "run_id": "RID-1",
                "date": "2026-08-29",
                "generated_at": "2026-08-29T00:00:00+00:00",
                "rows": [
                    {
                        "event_id": "evt-1", "sport": "football", "market": "corners_total",
                        "line": 9.5, "direction": "UNDER", "hits": 9, "sample_size": 12,
                        "hit_rate": 0.75, "p_low": 0.60, "mean": 9.1, "median": 9.0,
                        "sources": ["bzzoiro"], "cross_provider_agreement": "AGREE",
                        "confidence": "HIGH", "data_quality": "READY",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _run_main(module, monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["build_coupons.py", *argv])
    try:
        module.main()
    except SystemExit as exc:
        return exc.code
    return 0


def test_a_missing_vetoes_file_is_not_an_error(module, monkeypatch, tmp_path):
    sheet_path = tmp_path / "sheet.json"
    _write_sheet(sheet_path)
    output = tmp_path / "kupony.md"

    code = _run_main(
        module, monkeypatch,
        [
            "--stats-sheet", str(sheet_path),
            "--output", str(output),
            "--vetoes", str(tmp_path / "does_not_exist.json"),
            "--include-started",
        ],
    )
    assert code == 0
    assert output.exists()
    assert "UNDER" in output.read_text(encoding="utf-8")


def test_a_veto_file_removes_the_matching_row(module, monkeypatch, tmp_path):
    sheet_path = tmp_path / "sheet.json"
    _write_sheet(sheet_path)
    vetoes_path = tmp_path / "vetoes.json"
    vetoes_path.write_text(
        json.dumps([
            {
                "event_id": "evt-1", "market": "corners_total", "line": 9.5,
                "direction": "UNDER", "action": "VETO", "reason": "suspended fixture",
            }
        ]),
        encoding="utf-8",
    )
    output = tmp_path / "kupony.md"

    code = _run_main(
        module, monkeypatch,
        [
            "--stats-sheet", str(sheet_path),
            "--output", str(output),
            "--vetoes", str(vetoes_path),
            "--include-started",
        ],
    )
    # Exit 1: nothing cleared the bar once the only row is vetoed.
    assert code == 1
    rendered = output.read_text(encoding="utf-8")
    assert "suspended fixture" in rendered


def test_a_missing_market_context_file_is_not_an_error(module, monkeypatch, tmp_path):
    """docs/PLAN_BOGATE_STATYSTYKI.md 3bis.6. No --market-context passed at
    all must behave exactly like today: no entitlement warning, no crash."""
    sheet_path = tmp_path / "sheet.json"
    _write_sheet(sheet_path)
    output = tmp_path / "kupony.md"

    code = _run_main(
        module, monkeypatch,
        [
            "--stats-sheet", str(sheet_path),
            "--output", str(output),
            "--market-context", str(tmp_path / "does_not_exist.json"),
            "--include-started",
        ],
    )
    assert code == 0
    rendered = output.read_text(encoding="utf-8")
    assert "Football Unlimited" not in rendered


def test_a_confirmed_lapsed_entitlement_warns_in_the_header(module, monkeypatch, tmp_path):
    sheet_path = tmp_path / "sheet.json"
    _write_sheet(sheet_path)
    market_context_path = tmp_path / "market_context.json"
    market_context_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-08-29T00:00:00+00:00",
                "football_unlimited_entitled": False,
                "events": [
                    {
                        "event_id": "evt-1",
                        "provider_event_id": "p1",
                        "comparison_entitlement": "NOT_ENTITLED",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "kupony.md"

    code = _run_main(
        module, monkeypatch,
        [
            "--stats-sheet", str(sheet_path),
            "--output", str(output),
            "--market-context", str(market_context_path),
            "--include-started",
        ],
    )
    assert code == 0
    rendered = output.read_text(encoding="utf-8")
    assert "Football Unlimited" in rendered
    assert "NOT_ENTITLED" in rendered
    # The warning is a header note, printed before the first single -- not
    # buried after the rows an operator would already be reading.
    assert rendered.index("Football Unlimited") < rendered.index("## Single")
