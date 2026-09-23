"""AUDIT — what the analysts' vetoes removed, and whether removing it was right.

A veto is the one channel a human read has into `sofa`, and until 2026-09-23
nothing ever graded it. SETTLE grades every sheet row, vetoed or not, so the
answer was on disk the whole time: a vetoed row that lost was a good veto, one
that won was a bet the analyst talked us out of.

The yardstick is money at the printed price, not the hit rate — every leg class
loses about the same share to the margin, so a hit rate says nothing on its
own (L: hit rate is the wrong yardstick). The comparison is the same day's
priced rows that were *not* vetoed, over the same odds floor CONFIDENCE uses,
because a row below that floor could never have reached the PDF and removing
it removed nothing.

Two things make a veto measurement lie, and both are handled here rather than
left to the reader:

  * **a veto written after its fixture started** may have been written with
    the result in view (L: the web index runs ahead of the decision). Such
    rows are counted apart and never enter the grade. The write time is the
    file's modification time — a later rebuild that rewrites the file makes
    earlier fixtures' vetoes look late, which errs toward excluding them.
  * **one fixture is not many observations.** A match-wide veto covers every
    rung of one match, and those rungs win or lose together. The fixture
    count and the largest fixture's share are printed beside every grade.

    PYTHONPATH=src:. python scripts/sofa/audit_vetoes.py \\
        --from 2026-09-21 --to 2026-09-23
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, "src")

from bet.sofa.confidence import MIN_ODDS_FOR_CEILING  # noqa: E402
from bet.sofa.contracts import Veto  # noqa: E402
from bet.sofa.veto import load_vetoes, veto_matches  # noqa: E402

# CONFIDENCE refuses a row under this price before it looks at the vetoes
# (`run_confidence.MIN_ODDS`), so a veto on such a row changed nothing.
MIN_ODDS = MIN_ODDS_FOR_CEILING

BASELINE = "NIE ZAWETOWANE"

# ROI is monotone in the price band (-3.8% at 1.00-1.15, -32.1% above 3.00 on
# 93.5k settled rows), so a group of vetoes on long prices "loses more than
# the rest" by construction. On 2026-09-17..22 the OTHER vetoes read -44.9%
# against -13.6% and hit 12.1% where the price expected 11.2%: the analysts
# had removed long shots, not found anything. The fair comparison is the rest
# of the board re-weighted to the group's own mix of bands.
PRICE_BANDS = (1.5, 2.0, 3.0)


def price_band(odds: float) -> int:
    return sum(odds >= edge for edge in PRICE_BANDS)


def veto_group(veto: Veto) -> str:
    """`CONTEXT/ROTATION`, or the bare class when no context tag is set."""
    return f"{veto.reason_class}/{veto.context}" if veto.context else veto.reason_class


def _specificity(veto: Veto) -> int:
    fields = (veto.market, veto.subject, veto.line, veto.direction)
    return sum(x is not None for x in fields)


def attribute(row: Mapping[str, Any], vetoes: Iterable[Veto]) -> Veto | None:
    """The veto a row is charged to, or None.

    A row can match a match-wide veto and a narrow one at once. It is charged
    to the most specific, because the narrow veto is the deliberate statement
    about that rung; ties go to the first in the file. Charging it to both
    would count one bet twice in the total.
    """
    best: Veto | None = None
    for v in vetoes:
        if not veto_matches(
            v,
            sofascore_event_id=int(row["sofascore_event_id"]),
            market=row["market"],
            subject=row.get("subject") or "",
            line=float(row["line"]),
            direction=row["direction"],
        ):
            continue
        if best is None or _specificity(v) > _specificity(best):
            best = v
    return best


@dataclass
class Grade:
    rows: int = 0
    won: int = 0
    units: float = 0.0
    market_p_sum: float = 0.0
    market_p_n: int = 0
    per_fixture: Counter[int] = field(default_factory=Counter)
    band_rows: Counter[int] = field(default_factory=Counter)
    band_units: dict[int, float] = field(default_factory=dict)

    def add(self, row: Mapping[str, Any]) -> None:
        odds = float(row["offered_odds"])
        band = price_band(odds)
        result = odds - 1.0 if row["outcome"] == "WIN" else -1.0
        self.rows += 1
        self.per_fixture[int(row["sofascore_event_id"])] += 1
        self.band_rows[band] += 1
        self.band_units[band] = self.band_units.get(band, 0.0) + result
        self.units += result
        if row["outcome"] == "WIN":
            self.won += 1
        if row.get("market_p") is not None:
            self.market_p_sum += float(row["market_p"])
            self.market_p_n += 1

    @property
    def roi(self) -> float | None:
        return self.units / self.rows if self.rows else None

    @property
    def hit(self) -> float | None:
        return self.won / self.rows if self.rows else None

    @property
    def market_p(self) -> float | None:
        """What the devigged price expected these rows to hit."""
        return self.market_p_sum / self.market_p_n if self.market_p_n else None

    def roi_at_mix(self, mix: Mapping[int, int]) -> float | None:
        """This grade's ROI re-weighted to another grade's price-band mix.

        None when a band the mix needs has no rows here - an honest blank
        rather than a baseline silently computed on fewer bands.
        """
        total = sum(mix.values())
        if not total or any(self.band_rows[b] == 0 for b in mix if mix[b]):
            return None
        return sum(
            (n / total) * self.band_units[b] / self.band_rows[b]
            for b, n in mix.items() if n
        )

    @property
    def largest_fixture_share(self) -> float | None:
        return max(self.per_fixture.values()) / self.rows if self.rows else None


@dataclass
class VetoAudit:
    groups: dict[str, Grade] = field(default_factory=dict)
    baseline: Grade = field(default_factory=Grade)
    after_kickoff: Counter[str] = field(default_factory=Counter)
    below_min_odds: int = 0
    unpriced: int = 0

    def group(self, name: str) -> Grade:
        return self.groups.setdefault(name, Grade())


def earliest_kickoff(fixture: Mapping[str, Any]) -> datetime | None:
    """The earlier of the two clocks, as COUPON and CONFIDENCE gate on."""
    clocks = [
        datetime.fromisoformat(t.replace("Z", "+00:00"))
        for t in (fixture.get("kickoff_utc"), fixture.get("superbet_kickoff_utc"))
        if t
    ]
    return min(clocks) if clocks else None


def grade_vetoes(
    vetoes: list[Veto],
    settled: Iterable[Mapping[str, Any]],
    *,
    kickoff_by_event: Mapping[int, datetime],
    written_at: datetime | None,
    audit: VetoAudit | None = None,
) -> VetoAudit:
    """Grade one day's vetoes against its settled rows; accumulate into `audit`.

    Only priced, decided rows at or above MIN_ODDS count, vetoed or not. A
    vetoed row whose fixture had started before `written_at` is set apart;
    with `written_at=None` (unknown) nothing is set apart, and the caller must
    say so.
    """
    audit = audit if audit is not None else VetoAudit()
    for row in settled:
        if row["outcome"] not in ("WIN", "LOSS"):
            continue
        veto = attribute(row, vetoes)
        if row.get("offered_odds") is None:
            if veto is not None:
                audit.unpriced += 1
            continue
        if float(row["offered_odds"]) < MIN_ODDS:
            if veto is not None:
                audit.below_min_odds += 1
            continue
        if veto is None:
            audit.baseline.add(row)
            continue
        kickoff = kickoff_by_event.get(int(row["sofascore_event_id"]))
        if written_at is not None and (kickoff is None or written_at >= kickoff):
            audit.after_kickoff[veto_group(veto)] += 1
            continue
        audit.group(veto_group(veto)).add(row)
    return audit


def _f(x: float | None, fmt: str) -> str:
    return "—" if x is None else format(x, fmt)


def render(audit: VetoAudit, *, heading: str, written_at_known: bool) -> list[str]:
    """The report section, in Polish, operator-facing."""
    out: list[str] = [heading, ""]
    out.append(
        "Każdy zawetowany wiersz i tak jest rozliczany, więc wiadomo, co weto "
        "wycięło. Miarą są pieniądze po wydrukowanym kursie, nie % trafień. "
        f"Liczą się tylko wiersze z ceną ≥ {MIN_ODDS:.4f} (poniżej CONFIDENCE "
        "odrzuca je przed wetami, więc weto niczego nie zmieniało). Punktem "
        "odniesienia są niezawetowane wiersze z tych samych dni."
    )
    out.append("")
    header = ["grupa", "wierszy", "meczów", "największy mecz", "weszło",
              "cena oczekiwała", "ROI przy 1 j.", "ROI reszty, te same kursy"]
    b = audit.baseline
    rows: list[list[str]] = []
    for name, g in sorted(audit.groups.items(), key=lambda kv: -kv[1].rows):
        rows.append([name, str(g.rows), str(len(g.per_fixture)),
                     _f(g.largest_fixture_share, ".0%"), _f(g.hit, ".1%"),
                     _f(g.market_p, ".1%"), _f(g.roi, "+.1%"),
                     _f(b.roi_at_mix(g.band_rows), "+.1%")])
    rows.append([BASELINE, str(b.rows), str(len(b.per_fixture)),
                 _f(b.largest_fixture_share, ".0%"), _f(b.hit, ".1%"),
                 _f(b.market_p, ".1%"), _f(b.roi, "+.1%"), "—"])
    out.append("| " + " | ".join(header) + " |")
    out.append("|" + "|".join("---" for _ in header) + "|")
    out += ["| " + " | ".join(r) + " |" for r in rows]
    out.append("")
    out.append(
        "Weto działa, gdy ROI grupy jest **niższe** niż `ROI reszty, te same "
        "kursy` — niezawetowane wiersze przeważone do tego samego rozkładu "
        "przedziałów kursu (<1,5 / 1,5–2 / 2–3 / ≥3). Porównanie z gołym ROI "
        "reszty kłamie: ROI spada z długością kursu, więc weta na długich "
        "kursach „przegrywają więcej” z samej konstrukcji. `cena oczekiwała` "
        "to średnie "
        "`market_p` — trafienia wyraźnie poniżej niego znaczą, że weto "
        "znalazło coś, czego cena nie widziała. Wiersze jednego meczu wygrywają "
        "i przegrywają razem: grupa z kilkoma meczami to anegdota, nie pomiar."
    )
    out.append("")
    if audit.after_kickoff:
        total = sum(audit.after_kickoff.values())
        parts = ", ".join(f"{k} {v}" for k, v in audit.after_kickoff.most_common())
        out.append(
            f"**Wierszy poza pomiarem: {total}** — ich mecz zaczął się, zanim "
            f"`vetoes.json` zapisano po raz ostatni ({parts}). Takie weto mogło "
            "powstać ze znanym wynikiem, więc nie jest oceniane."
        )
        out.append("")
    if not written_at_known:
        out.append(
            "**Czas zapisu wet nieznany** — nic nie zostało wyłączone jako "
            "napisane po starcie meczu. Ten test nie został wykonany."
        )
        out.append("")
    if audit.below_min_odds or audit.unpriced:
        out.append(
            f"Pominięte zawetowane wiersze: {audit.below_min_odds} poniżej "
            f"progu kursu, {audit.unpriced} bez ceny."
        )
        out.append("")
    return out


def load_settled(db_path: str, run_date: str) -> list[dict[str, Any]]:
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM sofa_settled_row WHERE run_date = ?", (run_date,)
        )]
    finally:
        conn.close()


def audit_day(
    run_dir: Path, settled: list[dict[str, Any]], audit: VetoAudit | None = None
) -> tuple[VetoAudit, bool]:
    """Grade one day from its run directory. Returns the audit and whether the
    vetoes' write time was known."""
    path = run_dir / "vetoes.json"
    vetoes = load_vetoes(path)
    fixtures_path = run_dir / "02_fixtures.json"
    fixtures = json.loads(fixtures_path.read_text()) if fixtures_path.exists() else []
    kickoffs = {
        int(f["sofascore_event_id"]): k
        for f in fixtures
        if (k := earliest_kickoff(f)) is not None
    }
    written_at = (
        datetime.fromtimestamp(path.stat().st_mtime, tz=UTC) if path.exists() else None
    )
    audit = grade_vetoes(vetoes, settled, kickoff_by_event=kickoffs,
                         written_at=written_at, audit=audit)
    return audit, written_at is not None or not vetoes


def main() -> int:
    from bet.sofa.config import SofaConfig

    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    config = SofaConfig.from_env()
    day, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    audit = VetoAudit()
    days: list[str] = []
    all_known = True
    while day <= end:
        run_dir = Path(config.runs_dir) / day.isoformat()
        settled = load_settled(config.db_path, day.isoformat())
        if (run_dir / "vetoes.json").exists() and settled:
            _, known = audit_day(run_dir, settled, audit)
            all_known = all_known and known
            days.append(day.isoformat())
        day += timedelta(days=1)

    lines = [f"# Audyt wet analityków — {args.start} … {args.end}", ""]
    lines.append(f"Dni z wetami i rozliczeniem: {', '.join(days) or 'brak'}.")
    lines.append("")
    lines += render(audit, heading="## Co wycięły weta", written_at_known=all_known)
    out = Path(args.out) if args.out else (
        Path("reports") / f"sofa_audyt_wet_{args.start}_{args.end}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"WROTE {out} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
