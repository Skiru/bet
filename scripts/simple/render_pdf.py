#!/usr/bin/env python3
"""Render a day's coupon file (and optionally the analysis) to one PDF.

    python3 scripts/simple/render_pdf.py --date 2026-09-06
    python3 scripts/simple/render_pdf.py --date 2026-09-06 --with-analysis

Why a script and not a browser. The 2026-09-05 report was printed by hand out
of Chrome, which leaves no record of what was in it and no way to tell whether
the file on disk matches the artifact it claims to render. This does the same
conversion -- pandoc to HTML, headless Chrome to PDF, because Chrome is the one
renderer on this machine that lays out the markdown tables correctly -- and
then **reads the PDF back and checks it against the JSON**, which is the part a
manual print cannot do.

Exit codes: 0 = rendered and verified, 1 = the PDF disagrees with the artifact
or a section is missing, 2 = bad input or a missing tool.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

# Print stylesheet. Tables are the whole document, so they get the attention:
# fixed layout so a long market name cannot squeeze the odds column to nothing,
# and repeated headers so a table broken across pages stays readable.
CSS = """
@page { size: A4; margin: 14mm 12mm 16mm 12mm; }
body { font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
       font-size: 9.4pt; line-height: 1.45; color: #17181c; }
h1 { font-size: 19pt; margin: 0 0 2mm; border-bottom: 2px solid #17181c;
     padding-bottom: 2mm; }
h2 { font-size: 13pt; margin: 7mm 0 2mm; page-break-after: avoid; }
h3 { font-size: 11pt; margin: 6mm 0 2mm; page-break-after: avoid;
     border-left: 3px solid #17181c; padding-left: 2.5mm; }
h4 { font-size: 10pt; margin: 5mm 0 2mm; page-break-after: avoid; }
/* ``auto`` and not ``fixed``. Fixed layout plus a hard first-column width was
   written for the singles tables, whose first column is a rank -- and it
   wrecked the supply-funnel table, whose first column is a phrase: the label
   "wzbogacone (mecze z wierszami)" wrapped one letter per line inside 3.5em
   while the number beside it kept the rest of the page. Auto layout sizes each
   column to its own content, which is what both shapes need. Caught by
   rendering a page to PNG and looking at it; ``pdftotext`` called the same
   file clean, because every word was present and only the geometry was wrong. */
table { border-collapse: collapse; width: 100%; margin: 2.5mm 0 4mm;
        font-size: 8.3pt; table-layout: auto; page-break-inside: auto; }
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #ccced3; padding: 1.4mm 1.8mm; text-align: left;
         overflow-wrap: break-word; }
th { background: #eef0f4; font-weight: 600; }
blockquote { margin: 2.5mm 0; padding: 2mm 3mm; border-left: 3px solid #b9bcc4;
             background: #f6f7f9; color: #3c3f47; font-size: 8.4pt; }
code { background: #eef0f4; padding: 0.3mm 1mm; border-radius: 2px;
       font-size: 8.2pt; }
strong { font-weight: 650; }
hr { border: 0; border-top: 1px solid #ccced3; margin: 6mm 0; }
"""


def _pdf_text(pdf: Path) -> str:
    """Whatever text we can read back out, for the verification pass."""
    for tool, args in (("pdftotext", [str(pdf), "-"]),
                       ("mutool", ["draw", "-F", "txt", str(pdf)])):
        if shutil.which(tool):
            done = subprocess.run([tool, *args], capture_output=True, text=True)
            if done.returncode == 0 and done.stdout.strip():
                return done.stdout
    return ""


def verify(pdf: Path, markdown: Path, coupons: Path) -> list[str]:
    """Everything that can be checked without a human opening the file."""
    problems: list[str] = []
    if not pdf.exists() or pdf.stat().st_size < 20_000:
        problems.append(f"PDF nie powstał albo jest pusty ({pdf})")
        return problems

    text = _pdf_text(pdf)
    if not text:
        problems.append("nie da się odczytać tekstu z PDF-a — pomijam weryfikację treści")
        return problems

    flat = re.sub(r"\s+", " ", text)
    data = json.loads(coupons.read_text(encoding="utf-8"))
    playable = [s for s in data["singles"] if s["superbet_verdict"] == "VALUE"]

    # 1. Polish diacritics survived the pipeline. A mojibake'd PDF still has
    #    the right page count and the right numbers, which is exactly why this
    #    is checked first.
    if not any(ch in text for ch in "ąćęłńóśźż"):
        problems.append("brak polskich znaków — podejrzenie mojibake")
    if "Â" in text or "�" in text:
        problems.append("uszkodzone kodowanie znaków w PDF")

    # 2. Every section the operator acts on is present.
    for heading in ("Warte swojej ceny", "Gdy złożysz je w kupon",
                    "Poniżej progu"):
        if heading not in flat:
            problems.append(f"brak sekcji: {heading}")

    # 3. Every bettable row reached the page, with its price. This is the
    #    check a hand-print cannot make and the one that matters: a table
    #    silently truncated at a page break loses rows, not formatting.
    for row in playable:
        price = f"{row['superbet_price']:.2f}"
        if price not in flat:
            problems.append(
                f"kurs {price} ({row['match']} {row['market']}) nie występuje w PDF"
            )
    if f"({len(playable)})" not in flat:
        problems.append(
            f"nagłówek nie potwierdza liczby grywalnych wierszy ({len(playable)})"
        )

    # 4. The source markdown and the PDF describe the same file.
    md = markdown.read_text(encoding="utf-8")
    for match in re.findall(r"\*\*(\d+) singli\*\*", md):
        if match not in flat:
            problems.append(f"liczba singli ({match}) nie zgadza się z PDF-em")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--date", required=True)
    parser.add_argument("--runs-dir", default=str(ROOT / "runs"))
    parser.add_argument("--with-analysis", action="store_true",
                        help="Append <date>_analiza.md after the coupons")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    if not shutil.which("pandoc"):
        print("brak pandoc", file=sys.stderr)
        return 2
    if not CHROME.exists():
        print(f"brak Chrome ({CHROME})", file=sys.stderr)
        return 2

    run_dir = Path(args.runs_dir) / args.date
    markdown = run_dir / f"{args.date}_kupony.md"
    coupons = run_dir / f"{args.date}_coupons.json"
    if not markdown.exists() or not coupons.exists():
        print(f"brak {markdown} albo {coupons}", file=sys.stderr)
        return 2

    body = markdown.read_text(encoding="utf-8")
    if args.with_analysis:
        analysis = run_dir / f"{args.date}_analiza.md"
        if analysis.exists():
            body += ("\n\n<div style='page-break-before: always'></div>\n\n"
                     + analysis.read_text(encoding="utf-8"))

    source = run_dir / f".{args.date}_pdf_source.md"
    html = run_dir / f".{args.date}_pdf.html"
    source.write_text(body, encoding="utf-8")
    css = run_dir / f".{args.date}_pdf.css"
    css.write_text(CSS, encoding="utf-8")

    done = subprocess.run(
        ["pandoc", str(source), "-f", "gfm", "-t", "html5", "--standalone",
         # ``pagetitle`` and not ``title``: pandoc's html5 template renders
         # ``title`` as an <h1> of its own, and the markdown already opens
         # with "# Kupony <date>" -- so the first page carried the heading
         # twice. ``pagetitle`` sets only the document <title>.
         "--metadata", f"pagetitle=Kupony {args.date}", "-c", css.name,
         "--embed-resources", "-o", str(html)],
        capture_output=True, text=True,
    )
    if done.returncode != 0:
        print(done.stderr, file=sys.stderr)
        return 2

    output = Path(args.output) if args.output else run_dir / f"{args.date}_raport.pdf"
    done = subprocess.run(
        [str(CHROME), "--headless", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={output}", "--virtual-time-budget=10000",
         html.resolve().as_uri()],
        capture_output=True, text=True,
    )
    for tmp in (source, html, css):
        tmp.unlink(missing_ok=True)
    if done.returncode != 0 or not output.exists():
        print(done.stderr or "Chrome nie wyprodukował PDF-a", file=sys.stderr)
        return 2

    problems = verify(output, markdown, coupons)
    size_kb = output.stat().st_size / 1024
    print(json.dumps({"pdf": str(output), "kb": round(size_kb, 1),
                      "problems": problems}, ensure_ascii=False, indent=1))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
