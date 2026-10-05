"""WARIANT WSZYSTKIE: one variant coupon for every sport sofa prices.

The operator's variant, ordered 2026-09-30: after every sport has run its
full pipeline - football and tennis through BOARD ... CONFIDENCE -> PDF, CS2
and the three shadow sports through their snapshot -> sport coupon - one page
carries all of them.

It is an ASSEMBLY, not a new selector. Every position is exactly what its
own coupon printed, at the price that coupon printed:

- football + tennis: the official PDF's printed singles and printed Bet
  Builders (confidence.printed_singles / printed_builders on
  runs/sofa/<d>/08_confidence.json) - the numbers confidence.py computed;
- cs2 / hockey / basketball / volleyball: the legs of each sport_coupon.json.

So the variant never invents a leg, a price or a probability, and its result
is by construction the sum of its sections. Two probabilities stand side by
side and are never mixed into one ranking: football/tennis `confidence`
(calibrated from settled rows, a lower bound of the realised rate) and the
measured sports' `fair_p` (Superbet's price devigged; no model).

A section is printed only when its source is a coupon of this day that is
not stale:

- official: 08_confidence.json of profile "standard", no newer 05_sheet.json
  or vetoes.json or reads.json (the official PDF builder's own refusal,
  build_coupon_pdf.confidence_older_than_sheet), and KUPON_<d>.pdf present
  and not older than it - the PDF is the coupon;
- sport: sport_coupon.json of this date whose PDF is the one it was printed
  as (sport_coupon.pdf_matches: its sha256), built within MAX_SOURCE_AGE of
  this assembly.

A section that fails is named with its reason and left out; nothing is
patched in from elsewhere.

Boundaries: written to runs/sofa/multi/<d>/ only, never runs/sofa/<d>/; no
combined price beyond the builders confidence.py already computed; no stake;
its result is the variant's own and is never pooled with the coupon (7c) or
with WARIANT (7d).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from bet.sofa import sport_coupon as sc
from bet.sofa import timeutil
from bet.sofa.confidence import (
    PROFILES,
    confidence_artifact,
    printed_builders,
    printed_singles,
)

MULTI_FILE = "multi_coupon.json"
MULTI_MD = "multi_coupon.md"
MULTI_SETTLED = "multi_coupon_settled.json"
MAX_SOURCE_AGE = timedelta(hours=6)

SectionKey = Literal["official", "cs2", "hockey", "basketball", "volleyball"]
SECTIONS: tuple[SectionKey, ...] = (
    "official",
    "cs2",
    "hockey",
    "basketball",
    "volleyball",
)
SECTION_PL: dict[str, str] = {
    "official": "PIŁKA NOŻNA + TENIS (kupon oficjalny)",
    **{k: v for k, v in sc.SPORT_PL.items()},
}
PROBABILITY_KIND = {
    "official": "confidence",  # calibrated, a lower bound of the realised rate
    # Superbet's price devigged, no model; since 2026-10-05 hockey and
    # basketball print it recalibrated (sport_coupon.rule_for)
    "sport": "fair_p",
}


def multi_dir(runs_dir: str, date: str) -> Path:
    """runs/sofa/multi/<date>/ - beside the day, never inside it."""
    return Path(runs_dir) / "multi" / date


def pdf_name(date: str) -> str:
    return f"KUPON_{date}_WSZYSTKIE.pdf"


def official_dir(runs_dir: str, date: str) -> Path:
    return Path(runs_dir) / date


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _newer(a: Path, b: Path) -> bool:
    return a.stat().st_mtime > b.stat().st_mtime


def official_source(
    runs_dir: str, date: str
) -> tuple[dict[str, Any] | None, str | None]:
    """The official confidence artifact, or why it cannot be used."""
    run = official_dir(runs_dir, date)
    name = confidence_artifact(PROFILES["standard"])
    path = run / name
    if not path.exists():
        return None, f"MISSING: {path}"
    doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("profile", "standard") != "standard":
        return None, f"WRONG_PROFILE: {name} was built with {doc.get('profile')!r}"
    for newer in ("05_sheet.json", "vetoes.json", "reads.json"):
        other = run / newer
        if other.exists() and _newer(other, path):
            return None, f"STALE_CONFIDENCE: {name} is older than {newer}"
    pdf = run / f"KUPON_{date}.pdf"
    if not pdf.exists():
        return None, f"NO_PDF: {pdf.name} - the PDF is the coupon"
    if _newer(path, pdf):
        return None, f"PDF_OLDER_THAN_ARTIFACT: {pdf.name} does not print {name}"
    return doc, None


def sport_source(
    runs_dir: str, sport: sc.SportKey, date: str, at: datetime
) -> tuple[dict[str, Any] | None, str | None]:
    """A sport coupon of this day, or why it cannot be used. Read under the
    sport directory's lock, so a rebuild running at the same moment is never
    caught between its JSON and its PDF."""
    d = sc.day_dir(runs_dir, sport, date)
    path = d / sc.COUPON_FILE
    if not path.exists():
        return None, f"MISSING: {path}"
    with sc.dir_lock(d):
        return _sport_source(d, path, sport, date, at)


def _sport_source(
    d: Path, path: Path, sport: sc.SportKey, date: str, at: datetime
) -> tuple[dict[str, Any] | None, str | None]:
    doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("date") != date or doc.get("kind") != "SPORT_COUPON_EXPERIMENT":
        return None, f"WRONG_DAY: {path} is {doc.get('date')!r}"
    why = sc.pdf_matches(doc, path, d / sc.pdf_name(sport, date))
    if why is not None:
        return None, why
    age = at - _utc(str(doc["created_at_utc"]))
    if age > MAX_SOURCE_AGE:
        return None, f"STALE: built {age} before this assembly (max {MAX_SOURCE_AGE})"
    return doc, None


def official_positions(doc: dict[str, Any], at: datetime) -> dict[str, Any]:
    """The official PDF's printed singles and builders, verbatim."""
    singles = [
        {
            "section": "official",
            "sport": s.get("sport") or "football",
            "match": s["match"],
            "competition": s.get("competition"),
            "kickoff_utc": s["kickoff_utc"],
            "odds": s["offered_odds"],
            "probability": s["confidence"],
            "probability_kind": PROBABILITY_KIND["official"],
            "p_x_odds": round(s["confidence"] * s["offered_odds"], 4),
            "started": _utc(s["kickoff_utc"]) <= at,
            "source": s,
        }
        for s in printed_singles(doc)
    ]
    builders = [
        {
            "section": "official",
            "match": b.get("match"),
            "kickoff_utc": b.get("kickoff_utc"),
            "started": bool(b.get("kickoff_utc")) and _utc(str(b["kickoff_utc"])) <= at,
            "source": b,
        }
        for b in printed_builders(doc)
    ]
    return {"singles": singles, "builders": builders}


def sport_positions(
    sport: sc.SportKey, doc: dict[str, Any], at: datetime
) -> list[dict[str, Any]]:
    return [
        {
            "section": sport,
            "sport": sport,
            "match": leg["match_name"],
            "competition": leg.get("tournament"),
            "kickoff_utc": leg["kickoff_utc"],
            "odds": leg["odds"],
            "probability": leg.get("p", leg["fair_p"]),
            "probability_kind": PROBABILITY_KIND["sport"],
            "p_x_odds": leg.get("p_x_odds", leg["fair_p_x_odds"]),
            "started": _utc(leg["kickoff_utc"]) <= at,
            "source": leg,
        }
        for leg in doc.get("legs", [])
    ]


def assemble(runs_dir: str, date: str, at: datetime) -> dict[str, Any]:
    """Every section's printed positions, each with its source and status."""
    sections: dict[str, Any] = {}
    doc, why = official_source(runs_dir, date)
    if doc is None:
        sections["official"] = {
            "status": "EXCLUDED",
            "reason": why,
            "singles": [],
            "builders": [],
        }
    else:
        sections["official"] = {
            "status": "OK",
            "source_created_at_utc": doc.get("created_at_utc"),
            "unfitted_constants": doc.get("unfitted_constants"),
            **official_positions(doc, at),
        }
    for sport in sc.SPORT_KEYS:
        sdoc, why = sport_source(runs_dir, sport, date, at)
        if sdoc is None:
            sections[sport] = {"status": "EXCLUDED", "reason": why, "singles": []}
            continue
        sections[sport] = {
            "status": "OK",
            "source_created_at_utc": sdoc.get("created_at_utc"),
            "unfitted_constants": sdoc.get("UNFITTED_CONSTANTS"),
            "rule_history": sdoc.get("rule_history"),
            "singles": sport_positions(sport, sdoc, at),
        }
    singles = [p for s in sections.values() for p in s["singles"]]
    return {
        "kind": "MULTI_SPORT_VARIANT",
        "not_the_coupon": True,
        "date": date,
        "created_at_utc": at.isoformat().replace("+00:00", "Z"),
        "sections": sections,
        "counts": {
            "singles": len(singles),
            "builders": len(sections["official"]["builders"]),
            "sections_ok": sum(1 for s in sections.values() if s["status"] == "OK"),
            "sections_excluded": [
                k for k, s in sections.items() if s["status"] != "OK"
            ],
        },
    }


# --- settling ---------------------------------------------------------------------


def grade_sport_section(
    runs_dir: str, sport: sc.SportKey, date: str, section: dict[str, Any]
) -> list[dict[str, Any]]:
    """The sport section graded exactly as its own coupon is (sport_coupon)."""
    legs = [p["source"] for p in section.get("singles", [])]
    sources = {leg.get("source_date") or date for leg in legs} | {date}
    settled = {d: sc.load_settled(runs_dir, sport, d) for d in sources}
    return sc.grade_coupon(
        {"sport": sport, "date": date, "legs": legs}, settled, at=timeutil.now()
    )


def summarize_units(
    rows: list[dict[str, Any]], odds_key: str = "odds"
) -> dict[str, Any]:
    """Flat one unit per position: WIN pays odds - 1, LOSS costs 1, anything
    else is not counted."""
    decided = [r for r in rows if r["outcome"] in ("WIN", "LOSS")]
    wins = sum(1 for r in decided if r["outcome"] == "WIN")
    units = sum(
        float(r[odds_key]) - 1.0 if r["outcome"] == "WIN" else -1.0 for r in decided
    )
    return {
        "positions": len(rows),
        "settled": len(decided),
        "won": wins,
        "lost": len(decided) - wins,
        "not_counted": len(rows) - len(decided),
        "units": round(units, 4),
        "roi": round(units / len(decided), 4) if decided else None,
    }
