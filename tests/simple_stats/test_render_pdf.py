"""The PDF renderer's verification pass.

The 2026-09-05 report was printed by hand out of a browser, which leaves no
record of what was in it. What made a script worth writing is not the
conversion -- it is that a script can read the PDF back and check it against
the JSON, and a manual print cannot.

Two failures found the first time it ran, both invisible to text extraction and
both caught only by rendering a page to PNG and looking at it: the supply-funnel
table wrapped its first column one letter per line, and the title appeared
twice. Text extraction called that file clean. So the checks below cover what
extraction *can* see, and the docstring records what it cannot.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "simple" / "render_pdf.py"


@pytest.fixture(scope="module")
def renderer():
    spec = importlib.util.spec_from_file_location("render_pdf", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _artifacts(tmp_path: Path, price: float = 1.61):
    markdown = tmp_path / "d_kupony.md"
    markdown.write_text("# Kupony\n\n**15 singli**, 8 kuponów BB\n", encoding="utf-8")
    coupons = tmp_path / "d_coupons.json"
    coupons.write_text(json.dumps({"singles": [{
        "match": "A – B", "market": "corners_total", "superbet_verdict": "VALUE",
        "superbet_price": price,
    }]}), encoding="utf-8")
    return markdown, coupons


class TestVerify:
    def test_a_missing_pdf_is_reported_not_ignored(self, renderer, tmp_path) -> None:
        markdown, coupons = _artifacts(tmp_path)
        problems = renderer.verify(tmp_path / "nope.pdf", markdown, coupons)
        assert problems and "nie powstał" in problems[0]

    def test_a_truncated_pdf_is_refused_on_size(self, renderer, tmp_path) -> None:
        # A Chrome run that dies mid-write leaves a small, valid-looking file.
        pdf = tmp_path / "d.pdf"
        pdf.write_bytes(b"%PDF-1.4\n" + b"0" * 100)
        markdown, coupons = _artifacts(tmp_path)
        assert renderer.verify(pdf, markdown, coupons)

    def test_it_notices_a_bettable_row_whose_price_never_reached_the_page(
        self, renderer, tmp_path, monkeypatch
    ) -> None:
        # The failure that matters: a table silently truncated at a page break
        # loses rows, not formatting, and the file still opens fine.
        pdf = tmp_path / "d.pdf"
        pdf.write_bytes(b"%PDF" + b"0" * 30_000)
        markdown, coupons = _artifacts(tmp_path, price=1.61)
        monkeypatch.setattr(
            renderer, "_pdf_text",
            lambda _p: "Warte swojej ceny (1) Gdy złożysz je w kupon "
                       "Poniżej progu 15 singli — kurs 9.99 zażółć gęślą jaźń",
        )
        problems = renderer.verify(pdf, markdown, coupons)
        assert any("1.61" in p for p in problems)

    def test_it_notices_mojibake(self, renderer, tmp_path, monkeypatch) -> None:
        # A mojibake'd PDF has the right page count and the right numbers.
        pdf = tmp_path / "d.pdf"
        pdf.write_bytes(b"%PDF" + b"0" * 30_000)
        markdown, coupons = _artifacts(tmp_path)
        monkeypatch.setattr(
            renderer, "_pdf_text",
            lambda _p: "Warte swojej ceny (1) Gdy zlozysz je w kupon "
                       "Ponizej progu 15 singli 1.61",
        )
        problems = renderer.verify(pdf, markdown, coupons)
        assert any("polskich znaków" in p for p in problems)

    def test_a_complete_pdf_passes(self, renderer, tmp_path, monkeypatch) -> None:
        pdf = tmp_path / "d.pdf"
        pdf.write_bytes(b"%PDF" + b"0" * 30_000)
        markdown, coupons = _artifacts(tmp_path)
        monkeypatch.setattr(
            renderer, "_pdf_text",
            lambda _p: "Warte swojej ceny (1) Gdy złożysz je w kupon "
                       "Poniżej progu 15 singli kurs 1.61 zażółć",
        )
        assert renderer.verify(pdf, markdown, coupons) == []


class TestAgainstTheRealReport:
    def test_todays_report_matches_its_own_coupon_file(self, renderer) -> None:
        run = ROOT / "runs" / "2026-09-06"
        pdf = run / "2026-09-06_raport.pdf"
        if not pdf.exists():
            pytest.skip("no report rendered")
        assert renderer.verify(
            pdf, run / "2026-09-06_kupony.md", run / "2026-09-06_coupons.json"
        ) == []
