"""AUDIT — did Superbet's boosts come in as often as their price needed?

The operator's suspicion (2026-09-23): Superbet picks what to boost so that it
loses. The measurement is the boosts' realised hit rate against two
break-evens: 1/boosted (what the boost needed to be worth taking) and
1/original (what the book itself asked before boosting). A boost selected to
lose hits below even the original break-even.

Graded from `10_boosts.json` (run_boosts.py) and `sofa_settled_row`: a leg is
graded only where its fixture was on that day's board and its rung was on the
sheet, so coverage is printed before the result - a boost set we could only
grade the football corners of is not "the boosts".

    PYTHONPATH=src:. python scripts/sofa/audit_boosts.py \\
        --from 2026-09-23 --to 2026-10-10
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, "src")

from bet.sofa.boosts import Boost, grade_boost  # noqa: E402
from scripts.sofa.run_boosts import (  # noqa: E402
    BOOSTS_JSON,
    load_boosts,
    superbet_to_sofascore,
)

SettledKey = tuple[int, str, str, float, str]


@dataclass
class BoostGrade:
    offered: int = 0
    graded: int = 0
    won: int = 0
    units_boosted: float = 0.0
    units_original: float = 0.0
    breakeven_boosted: float = 0.0
    breakeven_original: float = 0.0
    n_original: int = 0
    unsettled: Counter[str] = field(default_factory=Counter)

    def add(self, boost: Boost, outcome: str, reason: str | None) -> None:
        self.offered += 1
        if outcome == "UNSETTLED" or boost.original_price is None:
            self.unsettled[reason or "NO_ORIGINAL_PRICE"] += 1
            return
        self.graded += 1
        win = outcome == "WIN"
        self.won += win
        self.units_boosted += (boost.boosted_price - 1.0) if win else -1.0
        self.units_original += (boost.original_price - 1.0) if win else -1.0
        self.breakeven_boosted += 1.0 / boost.boosted_price
        self.breakeven_original += 1.0 / boost.original_price
        self.n_original += 1


def settled_index(
    rows: Iterable[Mapping[str, Any]],
) -> dict[SettledKey, Mapping[str, Any]]:
    return {
        (int(r["sofascore_event_id"]), r["market"], r.get("subject") or "",
         float(r["line"]), r["direction"]): r
        for r in rows
    }


def grade_day(
    boosts: list[Boost],
    fixtures: list[dict[str, Any]],
    settled: Iterable[Mapping[str, Any]],
    grades: dict[str, BoostGrade] | None = None,
) -> dict[str, BoostGrade]:
    """Accumulate one day's boosts into `grades`, keyed "kombinacje"/"pojedyncze"."""
    grades = grades if grades is not None else {}
    su2so = superbet_to_sofascore(fixtures)
    index = settled_index(settled)
    for b in boosts:
        outcome, reason = grade_boost(b, su2so.get(b.superbet_event_id), index)
        grades.setdefault("kombinacje" if b.combo else "pojedyncze",
                          BoostGrade()).add(b, outcome, reason)
    return grades


def _pct(x: float, n: int) -> str:
    return f"{100.0 * x / n:.1f}%" if n else "—"


def render(grades: Mapping[str, BoostGrade], heading: str) -> list[str]:
    out = [heading, ""]
    if not grades:
        out += ["Tego dnia nie zapisano migawki boostów (`run_boosts.py`).", ""]
        return out
    out.append(
        "Boost jest wart wzięcia, gdy trafia częściej niż `próg po podbiciu` "
        "(1/kurs po podbiciu). Trafienia poniżej `progu przed podbiciem` "
        "znaczyłyby, że Superbet podbija zakłady słabsze nawet od własnej "
        "ceny. Oceniane są tylko boosty, których każda noga była w arkuszu "
        "`sofa` i została rozliczona.")
    out.append("")
    header = ["", "zaoferowane", "ocenione", "weszło", "% trafień",
              "próg po podbiciu", "próg przed podbiciem", "ROI po podbiciu",
              "ROI bez podbicia"]
    out.append("| " + " | ".join(header) + " |")
    out.append("|" + "|".join("---" for _ in header) + "|")
    for name, g in sorted(grades.items()):
        out.append("| " + " | ".join([
            name, str(g.offered), str(g.graded), str(g.won),
            _pct(g.won, g.graded), _pct(g.breakeven_boosted, g.graded),
            _pct(g.breakeven_original, g.n_original),
            _pct(g.units_boosted, g.graded), _pct(g.units_original, g.graded),
        ]) + " |")
    out.append("")
    reasons: Counter[str] = Counter()
    for g in grades.values():
        reasons.update(g.unsettled)
    if reasons:
        out.append("Nieocenione: " + ", ".join(
            f"`{k}` {v}" for k, v in reasons.most_common()) + ". `NOT_ON_BOARD` "
            "to mecz spoza tablicy `sofa` (inny sport, liga kobiet, inna data); "
            "`UNMAPPED_LEG` to noga, której `sofa` nie czyta (1X2, dokładny "
            "wynik, strzelec).")
        out.append("")
    out.append("Kilkadziesiąt boostów to wciąż anegdota: odchylenie trafień "
               "przy n=30 i p=0,4 to około ±9 pp.")
    out.append("")
    return out


def audit_day(run_dir: Path, settled: list[dict[str, Any]]) -> dict[str, BoostGrade]:
    path = run_dir / BOOSTS_JSON
    if not path.exists():
        return {}
    fixtures_path = run_dir / "02_fixtures.json"
    fixtures = json.loads(fixtures_path.read_text()) if fixtures_path.exists() else []
    return grade_day(load_boosts(path), fixtures, settled)


def main() -> int:
    from bet.sofa.config import SofaConfig
    from scripts.sofa.audit_vetoes import load_settled

    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    config = SofaConfig.from_env()
    day, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    grades: dict[str, BoostGrade] = {}
    days: list[str] = []
    while day <= end:
        run_dir = Path(config.runs_dir) / day.isoformat()
        path = run_dir / BOOSTS_JSON
        if path.exists():
            fixtures_path = run_dir / "02_fixtures.json"
            fixtures = (json.loads(fixtures_path.read_text())
                        if fixtures_path.exists() else [])
            grade_day(load_boosts(path), fixtures,
                      load_settled(config.db_path, day.isoformat()), grades)
            days.append(day.isoformat())
        day += timedelta(days=1)

    lines = [f"# Audyt boostów Superbeta — {args.start} … {args.end}", "",
             f"Dni z migawką: {', '.join(days) or 'brak'}.", ""]
    lines += render(grades, "## Czy boosty wchodzą")
    out = Path(args.out) if args.out else (
        Path("reports") / f"sofa_audyt_boostow_{args.start}_{args.end}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"WROTE {out} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
