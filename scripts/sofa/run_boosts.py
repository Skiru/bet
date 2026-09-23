"""BOOSTS — snapshot Superbet's boosted prices for one day, beside the coupon.

Outside `DEFAULT_SEQUENCE` on purpose, like `fit_constants.py`: it neither
feeds nor gates the coupon. It records what Superbet boosted, at what price
and from what price, so `audit_boosts.py` can grade it once the day settles.
Run it more than once a day - Superbet adds boosts through the day, and a
re-run merges by odd rather than overwriting.

Cost: one `/events/by-date` call plus one `/events/{id}` per boosted event
(7 of 648 events on the evening of 2026-09-23). Superbet only; no bridge, no
Sofascore.

Writes `runs/sofa/<date>/10_boosts.json` and, for the operator,
`10_boosts.md`: each boost's legs against the day's own sheet and confidence
list where the fixture is on the board. It never prints a combined price or
probability of its own - only Superbet's numbers and the per-leg ones sofa
already computed.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_boosts.py --date 2026-09-23
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, "src")

from pydantic import RootModel  # noqa: E402

from bet.sofa.boosts import (  # noqa: E402
    Boost,
    extract_boosts,
    is_boosted_event,
    merge_snapshots,
)
from bet.sofa.confidence import leg_is_ev_positive  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.stage import set_stage  # noqa: E402
from bet.sofa.superbet import SuperbetClient  # noqa: E402
from bet.sofa.timeutil import now  # noqa: E402

BOOSTS_JSON = "10_boosts.json"
BOOSTS_MD = "10_boosts.md"

RowKey = tuple[int, str, str, float, str]


def load_boosts(path: Path) -> list[Boost]:
    if not path.exists() or not path.read_text().strip():
        return []
    return RootModel[list[Boost]].model_validate_json(path.read_text()).root


def superbet_to_sofascore(fixtures: list[dict[str, Any]]) -> dict[str, int]:
    return {
        str(su): int(f["sofascore_event_id"])
        for f in fixtures
        for su in f.get("superbet_event_ids") or []
    }


def _key(eid: int, row: dict[str, Any]) -> RowKey:
    return (eid, row["market"], row.get("subject") or "", float(row["line"]),
            row["direction"])


def leg_view(
    boost: Boost,
    sofa_id: int | None,
    sheet: dict[RowKey, dict[str, Any]],
    legs_conf: dict[RowKey, dict[str, Any]],
) -> list[list[str]]:
    """One table row per leg: what sofa itself holds for that rung."""
    rows = []
    for leg in boost.legs:
        price = f"{leg.leg_price:.2f}" if leg.leg_price else "—"
        if leg.unmapped is not None:
            rows.append([f"{leg.market_name}: {leg.selection}", price,
                         "rynek nieczytany przez sofa", "—", "—", "—"])
            continue
        assert leg.market is not None and leg.line is not None and leg.direction
        what = " ".join(x for x in (leg.market, leg.subject, leg.direction,
                                    f"{leg.line:g}") if x)
        if sofa_id is None:
            rows.append([what, price, "mecz poza tablicą sofa", "—", "—", "—"])
            continue
        key = (sofa_id, leg.market, leg.subject or "", leg.line, leg.direction)
        row = sheet.get(key)
        conf = legs_conf.get(key)
        if row is None:
            rows.append([what, price, "brak wiersza w arkuszu", "—", "—", "—"])
            continue
        rows.append([
            what, price, row.get("verdict") or "—",
            f"{row['p_bar']:.3f}",
            f"{row['market_p']:.3f}" if row.get("market_p") is not None else "—",
            f"{conf['confidence']:.3f}" if conf else "poniżej progu / odrzucona",
        ])
    return rows


def verdict(
    boost: Boost, sofa_id: int | None,
    legs_conf: dict[RowKey, dict[str, Any]], started: bool,
) -> str:
    if started:
        return "**Mecz już się zaczął** — nie jest to zakład."
    if sofa_id is None:
        return ("Mecz jest poza tablicą `sofa` tego dnia: nie mamy własnej "
                "oceny, są tylko ceny Superbeta.")
    confs = []
    for leg in boost.legs:
        if leg.market is None or leg.line is None or leg.direction is None:
            return ("Przynajmniej jednej nogi `sofa` nie czyta — nie ma "
                    "własnej oceny całości.")
        c = legs_conf.get((sofa_id, leg.market, leg.subject or "", leg.line,
                           leg.direction))
        confs.append(c["confidence"] if c else None)
    if not boost.combo:
        c = confs[0]
        if c is None:
            return ("Noga nie przeszła na listę pewnościową (poniżej progu albo "
                    "odrzucona przez bramkę) — `sofa` jej nie proponuje.")
        ok = leg_is_ev_positive(c, boost.boosted_price)
        return (f"pewność × kurs po podbiciu = {c * boost.boosted_price:.3f} "
                + ("(> 1: przechodzi test EV nogi, ten sam co w CONFIDENCE)."
                   if ok else "(≤ 1: nie przechodzi testu EV nogi nawet po podbiciu)."))
    missing = sum(c is None for c in confs)
    head = ("Kombinacja: `sofa` nie liczy dla niej łącznego prawdopodobieństwa "
            "ani ceny.")
    if missing:
        return f"{head} {missing} z {len(confs)} nóg nie ma na liście pewnościowej."
    return (f"{head} Wszystkie {len(confs)} nogi są na liście pewnościowej, "
            "ale łączna szansa zależy od tego, jak nogi są skorelowane — tego "
            "iloczyn nie mówi.")


def render(boosts: list[Boost], run_dir: Path, at: datetime) -> list[str]:
    fixtures_path = run_dir / "02_fixtures.json"
    fixtures = json.loads(fixtures_path.read_text()) if fixtures_path.exists() else []
    su2so = superbet_to_sofascore(fixtures)
    sheet: dict[RowKey, dict[str, Any]] = {}
    sheet_path = run_dir / "05_sheet.json"
    if sheet_path.exists():
        for r in json.loads(sheet_path.read_text()):
            sheet[_key(int(r["sofascore_event_id"]), r)] = r
    legs_conf: dict[RowKey, dict[str, Any]] = {}
    conf_path = run_dir / "08_confidence.json"
    if conf_path.exists():
        for leg in json.loads(conf_path.read_text()).get("legs") or []:
            legs_conf[_key(int(leg["sofascore_event_id"]), leg)] = leg

    out = [f"# Boosty Superbeta — {run_dir.name}", ""]
    out.append(
        f"Migawka z {at:%Y-%m-%d %H:%M} UTC, {len(boosts)} podbitych kursów. "
        "To nie jest kupon i nic stąd nie trafia do PDF. Ceny są Superbeta; "
        "`sofa` nie liczy ceny ani prawdopodobieństwa kombinacji. `pewność` to "
        "dolne ograniczenie zrealizowanego odsetka z `08_confidence.json`.")
    out.append("")
    for b in sorted(boosts, key=lambda x: (x.kickoff_utc or at, x.match_name)):
        started = (b.kickoff_utc is not None
                   and b.kickoff_utc <= at + timedelta(minutes=15))
        sofa_id = su2so.get(b.superbet_event_id)
        pct = f" ({b.boost_pct:+.1%})" if b.boost_pct is not None else ""
        orig = f"{b.original_price:.2f} → " if b.original_price else ""
        kick = f"{b.kickoff_utc:%Y-%m-%d %H:%M} UTC" if b.kickoff_utc else "?"
        out.append(f"## {b.match_name} — {kick}")
        out.append("")
        out.append(f"**{b.label}** — {orig}**{b.boosted_price:.2f}**{pct}"
                   + (" · kombinacja" if b.combo else ""))
        out.append("")
        product = b.leg_price_product
        if product:
            before = (f"{1 - b.original_price / product:.1%}" if b.original_price
                      else "—")
            out.append(
                f"Narzut Superbeta wobec iloczynu kursów nóg ({product:.2f}, to "
                f"nie jest cena): przed podbiciem {before}, po podbiciu "
                f"{1 - b.boosted_price / product:.1%}. Zmierzony narzut Bet "
                "Buildera to 8,8–19,6%.")
            out.append("")
        header = ["noga", "kurs nogi", "werdykt arkusza", "p_bar", "market_p",
                  "pewność"]
        out.append("| " + " | ".join(header) + " |")
        out.append("|" + "|".join("---" for _ in header) + "|")
        for r in leg_view(b, sofa_id, sheet, legs_conf):
            out.append("| " + " | ".join(r) + " |")
        out.append("")
        out.append(verdict(b, sofa_id, legs_conf, started))
        out.append("")
    out.append("Decyzja o postawieniu i o stawce należy do operatora.")
    return out


def main() -> int:
    set_stage("BOOSTS")
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    config = SofaConfig.from_env()
    run_dir = Path(config.runs_dir) / args.date
    run_dir.mkdir(parents=True, exist_ok=True)
    client = SuperbetClient()

    start = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=UTC)
    rows = client.events_by_date(
        start, start + timedelta(days=1), offer_state="prematch")
    boosted = [r for r in rows if is_boosted_event(r)]
    at = now()
    fresh: list[Boost] = []
    failed = 0
    # On 2026-09-24's board 25 of 29 tagged events were tennis matches whose
    # own payload held no boosted odd: the event tag runs ahead of (or wider
    # than) the price. Counted, so "4 boosts" is never read as "4 tagged".
    tagged_without_odd = 0
    for row in boosted:
        event = client.event_odds(row["eventId"])
        if event is None:
            failed += 1
            continue
        found = extract_boosts(event, at)
        tagged_without_odd += not found
        fresh.extend(found)

    path = run_dir / BOOSTS_JSON
    merged = merge_snapshots(load_boosts(path), fresh)
    path.write_text(
        RootModel[list[Boost]](merged).model_dump_json(indent=1), encoding="utf-8")
    (run_dir / BOOSTS_MD).write_text("\n".join(render(merged, run_dir, at)),
                                     encoding="utf-8")
    print(f"BOOSTS: {len(rows)} events, {len(boosted)} boosted, "
          f"{tagged_without_odd} tagged with no boosted odd, "
          f"{len(fresh)} boosts this snapshot, {len(merged)} on file, "
          f"{failed} event fetch(es) failed")
    print(f"WROTE {path} and {run_dir / BOOSTS_MD}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
