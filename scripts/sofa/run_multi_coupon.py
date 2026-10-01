#!/usr/bin/env python3
"""WARIANT WSZYSTKIE - assemble the all-sports variant coupon for one day.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_multi_coupon.py --date 2026-09-30
    ... --build-sports      # rebuild the four sport coupons first (no review!)

Reads, never writes, runs/sofa/<d>/08_confidence.json + KUPON_<d>.pdf (the
official coupon, football + tennis) and each measured sport's sport_coupon.json
+ PDF, and writes runs/sofa/multi/<d>/{multi_coupon.json, multi_coupon.md,
KUPON_<d>_WSZYSTKIE.pdf}. See src/bet/sofa/multi_coupon.py for what is taken
and when a section is refused.

`--build-sports` runs run_sport_coupon's build for every sport first. The
sofa-sport-runner agents are the reviewed way to build them; the flag exists
for an unattended run and says so in the artifact.

No network. Exit: 0 OK (every section in), 1 PARTIAL (a section excluded, or
no position at all), 2 FAILED.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import multi_coupon as mc  # noqa: E402
from bet.sofa import sport_coupon as sc  # noqa: E402
from bet.sofa.atomic import tmp_path  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.cs2 import write_atomic  # noqa: E402
from bet.sofa.timeutil import now  # noqa: E402
from scripts.sofa.run_sport_coupon import local  # noqa: E402


def leg_label(p: dict[str, Any]) -> str:
    src = p["source"]
    if p["section"] == "official":
        subject = f"{src['subject']} - " if src.get("subject") else ""
        side = "powyżej" if src["direction"] == "OVER" else "poniżej"
        return f"{subject}{src['market']}: {side} {src['line']:g}"
    return str(src.get("label") or sc.describe(p["section"], src))


def render_md(doc: dict[str, Any]) -> str:
    out = [
        f"# WARIANT WSZYSTKIE SPORTY - {doc['date']}",
        "",
        "**To nie jest kupon.** Każda pozycja jest dokładnie tym, co wydrukował "
        "kupon jej sportu, po jego kursie. Wynik wariantu nigdy nie jest "
        "sumowany z kuponem (7c) ani z WARIANTEM (7d).",
        "",
        f"Zbudowany {doc['created_at_utc']}; pojedynczych {doc['counts']['singles']}, "
        f"builderów {doc['counts']['builders']}; sekcje wyłączone: "
        f"{', '.join(doc['counts']['sections_excluded']) or 'brak'}"
        + (
            " ; kupony sportów przebudowane bez przeglądu (--build-sports)"
            if doc.get("sports_built_unreviewed")
            else ""
        ),
        "",
    ]
    for key, sec in doc["sections"].items():
        out.append(f"## {mc.SECTION_PL[key]}")
        out.append("")
        if sec["status"] != "OK":
            out += [f"Wyłączona: {sec['reason']}", ""]
            continue
        kind = "pewność" if key == "official" else "fair p (cena bez marży, bez modelu)"
        out.append(f"| start | mecz | zakład | kurs | {kind} | p × kurs |")
        out.append("|---|---|---|---|---|---|")
        for p in sec["singles"]:
            out.append(
                f"| {local(p['kickoff_utc'])}{' (w toku)' if p['started'] else ''} | "
                f"{p['match']} | {leg_label(p)} | {p['odds']:.2f} | "
                f"{p['probability']:.3f} | {p['p_x_odds']:.3f} |"
            )
        if not sec["singles"]:
            out.append("| - | brak pozycji | | | | |")
        for b in sec.get("builders", []):
            src = b["source"]
            out.append(
                f"\nBuilder {src.get('match')}: {src.get('n_legs')} nogi, kurs po "
                f"narzucie {src.get('odds_after_haircut')}, EV po narzucie "
                f"{src.get('ev_after_haircut')}"
            )
        out.append("")
    return "\n".join(out) + "\n"


def render_pdf(doc: dict[str, Any], path: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    from scripts.sofa.build_coupon_pdf import BASE, BOLD, INK, MUTED, WARN

    ss = getSampleStyleSheet()
    h1 = ParagraphStyle(
        "H1", parent=ss["Title"], fontName=BOLD, fontSize=17, textColor=INK
    )
    h2 = ParagraphStyle(
        "H2", parent=ss["Heading2"], fontName=BOLD, fontSize=11.5, textColor=INK
    )
    sub = ParagraphStyle(
        "SUB",
        parent=ss["Normal"],
        fontName=BASE,
        fontSize=8.4,
        textColor=MUTED,
        leading=12,
    )
    body = ParagraphStyle(
        "BODY",
        parent=ss["Normal"],
        fontName=BASE,
        fontSize=8.2,
        textColor=INK,
        leading=11,
    )
    head = ParagraphStyle("HEAD", parent=body, fontName=BOLD)
    warn = WARN.hexval().replace("0x", "#")
    story: list[Any] = [
        Paragraph(f"WARIANT WSZYSTKIE SPORTY — {doc['date']}", h1),
        Paragraph(
            f"Zbudowany {doc['created_at_utc']} &nbsp;•&nbsp; "
            f"{doc['counts']['singles']} pojedynczych, {doc['counts']['builders']} "
            f"builderów &nbsp;•&nbsp; sekcje: {doc['counts']['sections_ok']} z "
            f"{len(doc['sections'])}",
            sub,
        ),
        Spacer(1, 2 * mm),
        Paragraph(
            f"<font color='{warn}'><b>To nie jest kupon.</b></font> Wariant "
            "operatora od 30.09: każda pozycja to dokładnie to, co wydrukował kupon "
            "jej sportu, po jego kursie — nic nie jest tu wybierane od nowa. Piłka "
            "i tenis mają <b>pewność</b> z krzywej kalibracji (dolna granica "
            "zrealizowanego odsetka); CS2, hokej, koszykówka i siatkówka nie mają "
            "modelu — ich liczba to <b>cena Superbet bez marży</b>, więc każda z "
            "tych pozycji traci średnio tyle, ile marża. Dwóch liczb nie należy "
            "porównywać między sekcjami. Wynik wariantu jest jego własny: nigdy "
            "nie sumowany z kuponem ani z WARIANTEM. Tylko pojedyncze i buildery "
            "policzone przez confidence.py; stawka jest decyzją operatora.",
            body,
        ),
    ]
    if doc.get("sports_built_unreviewed"):
        story.append(
            Paragraph(
                f"<font color='{warn}'><b>Kupony sportów przebudowane bez przeglądu "
                "agentów (--build-sports).</b></font>",
                body,
            )
        )
    for key, sec in doc["sections"].items():
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(mc.SECTION_PL[key], h2))
        if sec["status"] != "OK":
            story.append(
                Paragraph(
                    f"<font color='{warn}'><b>Sekcja wyłączona:</b></font> "
                    f"{sec['reason']}",
                    body,
                )
            )
            continue
        if sec.get("unfitted_constants"):
            story.append(
                Paragraph(
                    "UNFITTED_CONSTANTS: "
                    + ", ".join(map(str, sec["unfitted_constants"])),
                    sub,
                )
            )
        kind = "pewność" if key == "official" else "fair p"
        rows: list[list[Any]] = [
            [
                Paragraph(t, head)
                for t in ("start", "mecz / rozgrywki", "zakład", "kurs", kind, "p×kurs")
            ]
        ]
        for p in sec["singles"]:
            rows.append(
                [
                    Paragraph(
                        local(p["kickoff_utc"])
                        + ("<br/>(w toku)" if p["started"] else ""),
                        body,
                    ),
                    Paragraph(
                        f"<b>{p['match']}</b><br/>{p.get('competition') or ''}", body
                    ),
                    Paragraph(leg_label(p), body),
                    Paragraph(f"<b>{p['odds']:.2f}</b>", body),
                    Paragraph(f"{p['probability']:.3f}", body),
                    Paragraph(f"{p['p_x_odds']:.3f}", body),
                ]
            )
        if not sec["singles"]:
            rows.append(
                [Paragraph("—", body), Paragraph("Brak pozycji.", body), "", "", "", ""]
            )
        table = Table(
            rows,
            colWidths=[20 * mm, 52 * mm, 66 * mm, 12 * mm, 15 * mm, 15 * mm],
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.6, INK),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#d0d0d0")),
                ]
            )
        )
        story.append(table)
        for b in sec.get("builders", []):
            src = b["source"]
            legs = "; ".join(
                f"{leg.get('market')} {leg.get('direction')} {leg.get('line')}"
                for leg in src.get("legs") or []
            )
            story.append(
                Paragraph(
                    f"<b>Bet Builder</b> {src.get('match')}: {legs} — kurs po narzucie "
                    f"{src.get('odds_after_haircut')} (szacunek confidence.py), EV po "
                    f"narzucie {src.get('ev_after_haircut')}",
                    body,
                )
            )
    SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=14 * mm,
        bottomMargin=13 * mm,
        title=f"Wariant wszystkie sporty {doc['date']}",
        author="sofa pipeline",
    ).build(story)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--date", required=True)
    parser.add_argument("--build-sports", action="store_true")
    args = parser.parse_args()
    runs_dir = SofaConfig.from_env().runs_dir
    at = now()
    if at >= sc.day_end(args.date):
        print(
            "SOFA_SUMMARY: "
            + json.dumps(
                {
                    "stage": "MULTI_COUPON",
                    "verdict": "FAILED",
                    "error": f"the window of {args.date} closed; its variant is final",
                }
            )
        )
        return 2
    build_errors: dict[str, str] = {}
    if args.build_sports:
        from scripts.sofa import run_sport_coupon

        for sport in sc.SPORT_KEYS:
            try:
                with sc.dir_lock(sc.day_dir(runs_dir, sport, args.date)):
                    sdoc = run_sport_coupon.build(
                        sport, args.date, runs_dir, now(), sc.Rule()
                    )
                    run_sport_coupon.write_outputs(sport, args.date, runs_dir, sdoc)
            except Exception as exc:  # the sport's section is then refused
                build_errors[sport] = f"{type(exc).__name__}: {exc}"
    try:
        doc = mc.assemble(runs_dir, args.date, at)
        doc["sports_built_unreviewed"] = bool(args.build_sports)
        doc["sport_build_errors"] = build_errors
        out = mc.multi_dir(runs_dir, args.date)
        out.mkdir(parents=True, exist_ok=True)
        pdf = out / mc.pdf_name(args.date)
        tmp = tmp_path(pdf)
        render_pdf(doc, tmp)
        doc["pdf_sha256"] = sc.file_sha256(tmp)
        write_atomic(out / mc.MULTI_FILE, json.dumps(doc, ensure_ascii=False, indent=2))
        os.replace(tmp, pdf)
        write_atomic(out / mc.MULTI_MD, render_md(doc))
    except Exception as exc:
        print(
            "SOFA_SUMMARY: "
            + json.dumps(
                {
                    "stage": "MULTI_COUPON",
                    "verdict": "FAILED",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        )
        return 2
    partial = bool(doc["counts"]["sections_excluded"]) or not doc["counts"]["singles"]
    print(
        "SOFA_SUMMARY: "
        + json.dumps(
            {
                "stage": "MULTI_COUPON",
                "verdict": "PARTIAL" if partial else "OK",
                "metrics": {
                    **doc["counts"],
                    "sections": {
                        k: s["status"] if s["status"] == "OK" else s["reason"]
                        for k, s in doc["sections"].items()
                    },
                },
                "output_path": str(pdf),
            },
            ensure_ascii=False,
        )
    )
    return 1 if partial else 0


if __name__ == "__main__":
    sys.exit(main())
