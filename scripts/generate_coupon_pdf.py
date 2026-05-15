"""Generate PDF files from coupon markdown for a given betting day."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import markdown_it
from weasyprint import HTML

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

CSS = """
@page {
    size: A4;
    margin: 1.5cm;
}
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 10pt;
    line-height: 1.4;
    color: #1a1a1a;
}
h1 {
    font-size: 16pt;
    border-bottom: 2px solid #2d6cdf;
    padding-bottom: 4pt;
    color: #2d6cdf;
}
h2 {
    font-size: 13pt;
    color: #1a5276;
    margin-top: 16pt;
    border-bottom: 1px solid #ddd;
    padding-bottom: 3pt;
    page-break-after: avoid;
}
h3 {
    font-size: 11pt;
    color: #333;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin: 8pt 0;
    font-size: 9pt;
}
th, td {
    border: 1px solid #ccc;
    padding: 4pt 6pt;
    text-align: left;
}
th {
    background-color: #f0f4f8;
    font-weight: bold;
}
tr:nth-child(even) {
    background-color: #fafbfc;
}
blockquote {
    border-left: 3px solid #e74c3c;
    padding: 6pt 12pt;
    margin: 8pt 0;
    background: #fef9e7;
    font-style: italic;
}
code {
    background: #f4f4f4;
    padding: 1pt 3pt;
    border-radius: 2pt;
    font-size: 9pt;
}
.page-break {
    page-break-before: always;
}
ul, ol {
    padding-left: 16pt;
}
li {
    margin-bottom: 2pt;
}
strong {
    color: #1a5276;
}
"""


def md_to_html(md_text: str) -> str:
    """Convert markdown text to HTML."""
    md = markdown_it.MarkdownIt("commonmark", {"html": True})
    md.enable("table")
    html_body = md.render(md_text)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>{CSS}</style>
</head>
<body>
{html_body}
</body>
</html>"""


def split_sections(md_text: str) -> dict[str, str]:
    """Split markdown into sections by H2 headers."""
    sections = {}
    current_name = "_header"
    current_lines = []

    for line in md_text.split("\n"):
        if line.startswith("## "):
            if current_lines:
                sections[current_name] = "\n".join(current_lines)
            current_name = line[3:].strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        sections[current_name] = "\n".join(current_lines)

    return sections


def generate_full_pdf(md_path: Path, output_path: Path):
    """Generate a single PDF with all coupon content."""
    md_text = md_path.read_text(encoding="utf-8")
    html = md_to_html(md_text)
    HTML(string=html).write_pdf(str(output_path))
    print(f"  ✓ Full PDF: {output_path} ({output_path.stat().st_size / 1024:.0f} KB)")


def generate_section_pdfs(md_path: Path, output_dir: Path):
    """Generate separate PDFs per section for mobile-friendly viewing."""
    md_text = md_path.read_text(encoding="utf-8")
    sections = split_sections(md_text)

    # Header content (title + disclaimer)
    header = sections.get("_header", "")

    # Key sections to export individually
    key_sections = {
        "banker": "BANKER",
        "singles": "SINGLE BETS",
        "combos": "COMBINATION MENU",
        "core": "PEŁNA MATRYCA RYNKÓW",
        "extended": "ROZSZERZONY WYBÓR",
        "placement": "KOLEJNOŚĆ STAWIANIA",
    }

    generated = []
    for filename, section_keyword in key_sections.items():
        matching = [(name, content) for name, content in sections.items()
                    if section_keyword.lower() in name.lower()]
        if not matching:
            continue

        section_name, section_content = matching[0]
        full_md = f"{header}\n\n{section_content}"
        html = md_to_html(full_md)
        out_path = output_dir / f"{filename}.pdf"
        HTML(string=html).write_pdf(str(out_path))
        generated.append(out_path)
        print(f"  ✓ {filename}.pdf ({out_path.stat().st_size / 1024:.0f} KB)")

    return generated


def generate_quick_reference(json_path: Path, output_path: Path):
    """Generate a compact quick-reference PDF from JSON data."""
    with open(json_path) as f:
        data = json.load(f)

    lines = []
    lines.append("# Quick Reference — 2026-05-15")
    lines.append("")
    lines.append("> WARUNKOWE — sprawdź kursy w Betclic przed postawieniem!")
    lines.append("")

    # Banker
    banker = data.get("banker")
    if banker:
        leg = banker["legs"][0]
        bm = leg.get("best_market", {})
        lines.append("## 🏆 BANKER")
        lines.append(f"**{leg.get('home_team')} vs {leg.get('away_team')}**")
        lines.append(f"- Rynek: {bm.get('name')} {bm.get('direction')} {bm.get('line', '')}")
        lines.append(f"- Safety: {bm.get('safety_score')}")
        lines.append("")

    # Core coupons
    lines.append("## CORE COUPONS")
    lines.append("")
    lines.append("| # | Legs | Avg Safety | Kurs | Stawka |")
    lines.append("|---|------|-----------|------|--------|")
    for i, c in enumerate(data.get("core_coupons", []), 1):
        legs = c.get("legs", [])
        avg_s = sum((l.get("best_market", {}).get("safety_score") or 0) for l in legs) / max(len(legs), 1)
        odds = c.get("combined_odds", 0)
        stake = c.get("stake", 0)
        leg_desc = " + ".join(
            f"{l.get('home_team','?')} vs {l.get('away_team','?')}"
            for l in legs
        )
        lines.append(f"| {i} | {leg_desc} | {avg_s:.2f} | {odds:.2f} | {stake:.2f} PLN |")
    lines.append("")

    # Core coupon details
    for i, c in enumerate(data.get("core_coupons", []), 1):
        legs = c.get("legs", [])
        lines.append(f"### Core {i} ({c.get('id', '')})")
        for j, leg in enumerate(legs, 1):
            bm = leg.get("best_market", {})
            lines.append(f"- **Leg {j}:** {leg.get('home_team')} vs {leg.get('away_team')} — "
                        f"{bm.get('name')} {bm.get('direction')} {bm.get('line', '')} "
                        f"(safety: {bm.get('safety_score')})")
        lines.append("")

    # Top 15 singles
    lines.append("## TOP 15 SINGLES")
    lines.append("")
    lines.append("| # | Mecz | Rynek | Safety | Tier |")
    lines.append("|---|------|-------|--------|------|")
    for i, s in enumerate(data.get("singles", [])[:15], 1):
        leg = s["legs"][0]
        bm = leg.get("best_market", {})
        lines.append(
            f"| {i} | {leg.get('home_team')} vs {leg.get('away_team')} | "
            f"{bm.get('name', '')} {bm.get('direction', '')} {bm.get('line', '')} | "
            f"{bm.get('safety_score', '-')} | {s.get('tier', '-')} |"
        )
    lines.append("")

    # Top 5 combos
    lines.append("## TOP 5 COMBOS")
    lines.append("")
    for i, c in enumerate(data.get("combos", [])[:5], 1):
        legs = c.get("legs", [])
        avg_s = sum((l.get("best_market", {}).get("safety_score") or 0) for l in legs) / max(len(legs), 1)
        theme = c.get("combo_theme", "")
        lines.append(f"### Combo {i} — {theme} (avg safety: {avg_s:.2f})")
        for leg in legs:
            bm = leg.get("best_market", {})
            lines.append(f"- {leg.get('home_team')} vs {leg.get('away_team')} — "
                        f"{bm.get('name')} {bm.get('direction')} {bm.get('line', '')}")
        lines.append(f"- **Kurs:** {c.get('combined_odds', 0):.2f} | **Stawka:** {c.get('stake', 0):.2f} PLN")
        lines.append("")

    md_text = "\n".join(lines)
    html = md_to_html(md_text)
    HTML(string=html).write_pdf(str(output_path))
    print(f"  ✓ Quick reference: {output_path} ({output_path.stat().st_size / 1024:.0f} KB)")


def main():
    parser = argparse.ArgumentParser(description="Generate PDF files from coupon data")
    parser.add_argument("--date", default="2026-05-15", help="Betting day (YYYY-MM-DD)")
    parser.add_argument("--output-dir", default=None, help="Output directory for PDFs")
    args = parser.parse_args()

    base_dir = Path("betting/coupons")
    md_path = base_dir / f"{args.date}.md"
    json_path = base_dir / f"{args.date}.json"

    if not md_path.exists():
        print(f"ERROR: {md_path} not found")
        sys.exit(1)

    output_dir = Path(args.output_dir) if args.output_dir else base_dir / "pdf" / args.date
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Generating PDFs for {args.date} ===\n")

    # 1. Full coupon PDF
    print("[1/3] Full coupon (all sections):")
    generate_full_pdf(md_path, output_dir / f"coupon-{args.date}-full.pdf")

    # 2. Section PDFs
    print("\n[2/3] Section PDFs:")
    generate_section_pdfs(md_path, output_dir)

    # 3. Quick reference (from JSON)
    if json_path.exists():
        print("\n[3/3] Quick reference PDF:")
        generate_quick_reference(json_path, output_dir / f"coupon-{args.date}-quick.pdf")

    print(f"\n=== Done! PDFs saved to: {output_dir}/ ===")


if __name__ == "__main__":
    main()
