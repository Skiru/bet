#!/usr/bin/env python3
"""The deterministic per-leg defect screen of a built day - the checks the
sofa-verifier used to paste as ad-hoc snippets, run over the analysts' read
set (default) or over every printed leg of 11_coupon.json (--all), so every
market gets the mechanical checks at no reading cost.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/verify_legs.py --date <d> \\
        [--all] [--live [--limit-fixtures N]] [--out-dir <dir>] [--runs-dir runs/sofa]

Checks, per leg (DEFECT = a leg the rules should not have printed as it is;
NOTE = worth a look, not a defect; CANNOT_VERIFY = the check could not run):

  sheet_row     a football / tennis leg's (event, market, subject, line,
                direction) has a 05_sheet.json row
  side          run_sheet.determine_side for the subject against an
                independent token match of the subject to 02_fixtures' two
                sides (names.normalize_name, comparability.fold)
  sheet_notes   P_SHRUNK_TO_PRICE / CENTRE_SHRUNK_TO_LADDER /
                CROSS_LEAGUE_UNLINKED on the leg's sheet row; day level:
                rebuild_plan.audit_sheet_stale at the build clock
  own_sample    confidence.model_above_own_sample on a football leg (the
                sample CONFIDENCE reads: opponent_correction.gate_values)
  clocks        locked_print.kickoff_clocks (RESOLVE, Superbet seen,
                FIXTURE_CHECK's fresh start; sport legs: the leg's and
                sport_fixtures' clocks): an unlocked leg whose earliest start
                is at or before 11_coupon.json's created_at_utc, Superbet's
                start signal before it or a fixture not as scheduled; a
                locked leg printed after its earliest start; a clock gap
                over 1 h (NOTE); inside the kickoff margin at build (NOTE)
  sport_identity sport_fixtures.json: IDENTIFIED, the same Sofascore id,
                home_is_team1 known, |start_gap_h| <= 1
  sport_market  sport_confidence.family_of under the day's switches and
                line_in_fit
  confidence    a measured-sport leg's confidence re-read from its
                forecast_p (run_sport_confidence.read_confidence, as audit
                U3); football / tennis is not a pure call - not re-derived
  live          (--live) football / tennis legs re-asked from Superbet with
                OFFER's own fetcher (offer.day_flags): OK / CHANGED / MISSING
                / STARTED / CANNOT_VERIFY; one fetch per fixture; sport legs
                are not re-asked

Writes <out-dir>/verify_legs.jsonl (one record per leg) and verify_legs.md
(legs with a finding, counts per check, the day's anti-selection summary and
a candidate ```json reads block: NO_BET, author verifier, for hard defects
of unlocked legs only - contracts.LegRead, validated). Default out-dir
${TMPDIR}/sofa_verify_<d>. Read-only on the day's artifacts; never changes
what prints. Exit 0 no defect, 1 a defect or CANNOT_VERIFY, 2 artifacts
missing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pydantic import RootModel  # noqa: E402

from bet.sofa import epochs  # noqa: E402
from bet.sofa import fixture_status as fs  # noqa: E402
from bet.sofa.comparability import fold  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    COUPON_ARTIFACT,
    model_above_own_sample,
    printed_builders,
    printed_singles,
    too_close_to_kickoff,
)
from bet.sofa.contracts import Fixture, LegRead  # noqa: E402
from bet.sofa.locked_print import kickoff_clocks  # noqa: E402
from bet.sofa.names import normalize_name  # noqa: E402
from bet.sofa.opponent_correction import gate_values  # noqa: E402
from bet.sofa.players import is_player_metric, player_observations  # noqa: E402
from bet.sofa.tennis_sets import split_score_subject  # noqa: E402
from scripts.sofa import read_set as rs  # noqa: E402
from scripts.sofa.run_sheet import determine_side  # noqa: E402

DEFECT, NOTE, CANNOT = "DEFECT", "NOTE", "CANNOT_VERIFY"
CHECKS = ("sheet_row", "side", "sheet_notes", "own_sample", "clocks",
          "sport_identity", "sport_market", "confidence", "live")
# The sheet notes a printed leg must not carry (prefixes).
BAD_NOTES = ("P_SHRUNK_TO_PRICE", "CENTRE_SHRUNK_TO_LADDER", "CROSS_LEAGUE_UNLINKED")
# A subject that names an outcome, not a side (1X2 / DC / first goal codes).
CODE_SUBJECTS = frozenset({"", "1", "X", "2", "12", "1X", "X2", "nikt", "T1", "T2"})
MAX_CLOCK_GAP = timedelta(hours=1)
MAX_START_GAP_H = 1.0
CONF_TOL = 5e-5 * 2  # the printed confidence is rounded to 4 dp
# Defects that make a leg wrong to take as printed: the candidate NO_BET.
HARD = frozenset({"sheet_row", "side", "sheet_notes", "own_sample", "clocks",
                  "sport_identity", "sport_market", "live"})
# Generic club words: they say nothing about which side a subject is.
STOP_TOKENS = frozenset({
    "fc", "cf", "sc", "ac", "cd", "fk", "sk", "afc", "club", "de", "la", "el",
    "the", "sv", "if", "bk", "ca", "cs", "ud", "rc", "us", "as", "ks", "nk",
    "and", "of", "w", "k", "u19", "u20", "u21", "u23"})
TABLE_LIMIT = 150


@dataclass
class Leg:
    raw: dict[str, Any]
    kind: str  # single | builder
    in_set: str = "all"
    findings: list[dict[str, str]] = field(default_factory=list)
    ran: list[str] = field(default_factory=list)
    live: dict[str, Any] | None = None

    def add(self, check: str, level: str, detail: str) -> None:
        self.findings.append({"check": check, "level": level, "detail": detail})

    @property
    def sport(self) -> str:
        return str(self.raw.get("sport") or "football")

    @property
    def eid(self) -> int:
        return int(self.raw["sofascore_event_id"])

    @property
    def odds(self) -> float | None:
        v = self.raw.get("offered_odds", self.raw.get("odds"))
        return None if v is None else float(v)

    def sheet_key(self) -> tuple[int, str, str, float | None, str]:
        line = self.raw.get("line")
        return (self.eid, str(self.raw["market"]), str(self.raw.get("subject") or ""),
                None if line is None else float(line), str(self.raw["direction"]))


def _utc(raw: object) -> datetime:
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))


def _z(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# --- population --------------------------------------------------------------


def printed_legs(doc: dict[str, Any], fixtures: Mapping[int, Mapping[str, Any]]
                 ) -> list[Leg]:
    """Every printed single and every printed builder's leg (with its
    fixture's event id, match and sport)."""
    out = [Leg(dict(s), "single") for s in printed_singles(doc)]
    for i, b in enumerate(printed_builders(doc), 1):
        eid = int(b["sofascore_event_id"])
        sport = str((fixtures.get(eid) or {}).get("sport") or "football")
        for x in b.get("legs") or []:
            leg = {**x, "sofascore_event_id": eid, "match": b.get("match"),
                   "competition": b.get("competition"),
                   "kickoff_utc": b.get("kickoff_utc"), "sport": sport,
                   "locked": bool(b.get("locked")),
                   "printed_at_utc": b.get("printed_at_utc")}
            out.append(Leg(leg, f"builder B{i}"))
    return out


def read_set_legs(run: Path, every: list[Leg]) -> list[Leg]:
    """The C3 read set (read_set.read_set), each leg matched back to its full
    printed record; a read-set leg the print does not hold keeps its compact
    form."""
    index = {rs.leg_key(x.raw): x for x in every}
    out: list[Leg] = []
    for legs in rs.read_set(run).values():
        for compact in legs:
            full = index.get(rs.leg_key(compact))
            leg = (Leg(full.raw, full.kind) if full is not None
                   else Leg(dict(compact), "read_request"))
            leg.in_set = str(compact.get("in_set") or "required")
            out.append(leg)
    return out


# --- the side --------------------------------------------------------------


def _tokens(name: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", fold(normalize_name(name)))
    return {w for w in words if len(w) >= 2 and w not in STOP_TOKENS}


def _score(subject: set[str], side: set[str]) -> float:
    s = 0.0
    for t in subject:
        if t in side:
            s += 1.0
        elif len(t) >= 4 and any(len(o) >= 4 and (o.startswith(t) or t.startswith(o))
                                 for o in side):
            s += 0.5
    return s


def independent_side(subject: str, home: str, away: str) -> str | None:
    """side_a / side_b by shared name tokens, None when undecided."""
    sub = _tokens(subject)
    a, b = _score(sub, _tokens(home)), _score(sub, _tokens(away))
    if max(a, b) <= 0 or abs(a - b) < 0.5:
        return None
    return "side_a" if a > b else "side_b"


def side_name(leg: Leg) -> str | None:
    """The side name a subject carries, None when it names no side."""
    subject = str(leg.raw.get("subject") or "")
    market = str(leg.raw.get("market") or "")
    if subject in CODE_SUBJECTS or is_player_metric(market):
        return None
    parsed = split_score_subject(subject)
    return parsed[0] if parsed is not None else subject


def check_side(leg: Leg, fixture: Fixture | None) -> None:
    name = side_name(leg)
    if name is None or fixture is None:
        return
    leg.ran.append("side")
    code = determine_side(name, fixture)
    mine = independent_side(name, fixture.home_name, fixture.away_name)
    leg.raw["_side"] = {"code": code, "independent": mine}
    if code is None:
        leg.add("side", DEFECT, f"subject {name!r} matches neither side in "
                f"determine_side ({fixture.home_name} - {fixture.away_name})")
    elif mine is not None and mine != code:
        leg.add("side", DEFECT, f"subject {name!r}: determine_side {code}, "
                f"names say {mine} ({fixture.home_name} - {fixture.away_name})")


# --- sheet checks ------------------------------------------------------------


def check_sheet(leg: Leg, sheet: Mapping[tuple[Any, ...], dict[str, Any]],
                samples: Mapping[int, dict[str, Any]], fixture: Fixture | None
                ) -> None:
    locked = bool(leg.raw.get("locked"))
    row = sheet.get(leg.sheet_key())
    leg.ran.append("sheet_row")
    if row is None:
        # a locked leg was printed from an earlier sheet; SHEET may have
        # been re-run since without its (now started) fixture's row
        leg.add("sheet_row", NOTE if locked else DEFECT,
                "no 05_sheet.json row for the leg's key")
        return
    leg.ran.append("sheet_notes")
    bad = [str(n) for n in row.get("notes") or []
           if str(n).startswith(BAD_NOTES)]
    for n in bad:
        leg.add("sheet_notes", DEFECT, n[:160])
    if leg.sport != "football" or row.get("line") is None:
        return
    leg.ran.append("own_sample")
    if not samples:
        leg.add("own_sample", CANNOT, "no 03_samples.json")
        return
    values = own_values(row, samples, fixture)
    gap = model_above_own_sample(
        "football", float(row["p_central"]), values, float(row["line"]),
        str(row["direction"]), str(row["market"]))
    if gap is not None:
        # a locked leg's confidence may come from an earlier SHEET run
        leg.add("own_sample", NOTE if locked else DEFECT,
                f"model {float(row['p_central']):.3f} is {gap:.3f} above its own "
                f"sample's hit rate (n={len(values)}; MODEL_ABOVE_OWN_SAMPLE)")


def own_values(row: Mapping[str, Any], samples: Mapping[int, dict[str, Any]],
               fixture: Fixture | None) -> list[float]:
    """The sample CONFIDENCE's MODEL_ABOVE_OWN_SAMPLE reads (run_confidence's
    side_observations + sample_values + gate_values)."""
    fx = samples.get(int(row["sofascore_event_id"])) or {}
    market, subject = str(row["market"]), str(row.get("subject") or "")
    obs: list[Any]
    if is_player_metric(market):
        obs = player_observations(fx, market, subject)
    else:
        mv = (fx.get("metrics") or {}).get(market) or {}
        if subject:
            side = determine_side(subject, fixture) if fixture else None
            obs = list(mv.get(side) or []) if side else []
        else:
            seen: set[Any] = set()
            obs = []
            for key in ("side_a", "side_b", "h2h"):
                for o in mv.get(key) or []:
                    if o["sofascore_event_id"] not in seen:
                        seen.add(o["sofascore_event_id"])
                        obs.append(o)
    values = [float(o["value"]) for o in obs if o.get("value") is not None]
    return gate_values(row, values)


# --- clocks ------------------------------------------------------------------


def check_clocks(leg: Leg, clocks: list[datetime], built: datetime,
                 started: str | None, status: Mapping[str, Any] | None,
                 resolve_status: str | None, gated: datetime | None = None
                 ) -> None:
    """`built`: 11_coupon.json's created_at_utc; `gated`: the clock of the
    CONFIDENCE run that admitted the leg (its kickoff margin's `now`)."""
    leg.ran.append("clocks")
    if not clocks:
        leg.add("clocks", DEFECT, "no start clock at all")
        return
    first = min(clocks)
    if max(clocks) - first > MAX_CLOCK_GAP:
        leg.add("clocks", NOTE, "clocks disagree by "
                f"{(max(clocks) - first).total_seconds() / 3600:.1f} h: "
                + ", ".join(sorted({_z(c) for c in clocks})))
    if leg.raw.get("locked"):
        printed = leg.raw.get("printed_at_utc")
        if not printed:
            leg.add("clocks", DEFECT, "locked without printed_at_utc")
            return
        at = _utc(printed)
        if at > first:
            leg.add("clocks", DEFECT, f"printed {_z(at)} after its earliest start "
                    f"{_z(first)}")
        elif started and _utc(started) <= at:
            leg.add("clocks", DEFECT, f"printed {_z(at)} after Superbet's start "
                    f"signal {started}")
        return
    if first <= built:
        leg.add("clocks", DEFECT, f"unlocked, earliest start {_z(first)} at or "
                f"before the build {_z(built)}")
    elif too_close_to_kickoff(clocks, gated or built):
        leg.add("clocks", NOTE, f"unlocked, earliest start {_z(first)} inside the "
                f"kickoff margin of CONFIDENCE {_z(gated or built)}")
    if started and _utc(started) <= built:
        leg.add("clocks", DEFECT, f"unlocked, Superbet reported the match started "
                f"{started}, before the build")
    bad = fs.not_as_scheduled(status, resolve_status)
    if bad:
        leg.add("clocks", DEFECT, f"unlocked, fixture status {bad}")


# --- measured sports ---------------------------------------------------------


@dataclass
class SportDay:
    """What the sport checks read once a day."""
    date: str
    built: datetime | None
    fixtures: dict[tuple[str, str], dict[str, Any]]
    read: Callable[[str, str, str, float, float], Any] | None
    family_of: Callable[[str, Any, str], str | None]
    line_in_fit: Callable[[str, str, Any], bool]


def sport_day(runs_dir: Path, date: str, doc: dict[str, Any],
              legs: Iterable[Leg]) -> SportDay:
    from bet.sofa import sport_confidence as scf
    from bet.sofa.line_evidence import LineEvidence
    from scripts.sofa import run_sport_confidence as rsc

    built_raw = (doc.get("built_from") or {}).get("08_confidence_sports.json")
    at = _utc(built_raw) if built_raw else None
    dates = {date} | {str(x.raw.get("source_date") or date) for x in legs}
    fixtures: dict[tuple[str, str], dict[str, Any]] = {}
    for d in sorted(dates):
        path = runs_dir / d / "sport_fixtures.json"
        if path.exists():
            for f in _load(path).get("fixtures") or []:
                fixtures.setdefault((str(f["sport"]), str(f["superbet_event_id"])), f)
    read = None
    if at is not None:
        cal = scf.SportCalibration.load(scf.calibration_path_for(date))
        evidence = (LineEvidence.load(v2=epochs.line_evidence_v2(date, at),
                                      bucket_deff=epochs.bucket_design_effect(date, at))
                    if epochs.line_evidence(date, at) else None)
        if cal is not None:
            def read(sport: str, family: str, side: str, p: float,
                     odds: float) -> Any:
                return rsc.read_confidence(cal, evidence, sport, family, side,
                                           p, odds)[0]
    extended = epochs.line_evidence(date, at)
    derived = epochs.sport_derived_markets(date, at)
    series = epochs.cs2_series_rounds(date, at)

    def family_of(sport: str, market_id: Any, family: str) -> str | None:
        if sport == "cs2":
            return scf.family_of("cs2", None, family, extended,
                                 series_rounds=series)
        return scf.family_of(sport, None if market_id is None else int(market_id),
                             family, extended, derived)

    return SportDay(date, at, fixtures, read, family_of, scf.line_in_fit)


def check_sport(leg: Leg, day: SportDay) -> list[datetime]:
    """Identity, market and confidence of a measured-sport leg; returns the
    leg's own start clock (the snapshot's)."""
    from scripts.sofa.audit_variants import confidence_reading

    raw, sport = leg.raw, leg.sport
    clocks = [_utc(raw["kickoff_utc"])] if raw.get("kickoff_utc") else []
    leg.ran.append("sport_identity")
    f = day.fixtures.get((sport, str(raw.get("superbet_event_id"))))
    if f is None:
        # no file at all = the check could not run, never a defect to NO_BET
        leg.add("sport_identity", DEFECT if day.fixtures else CANNOT,
                "no sport_fixtures.json record" if day.fixtures
                else "no sport_fixtures.json for the day")
    else:
        # sport_fixtures' kickoff is the clock as pinned (frozen; Superbet
        # swaps CS2 slots after the pin - 10-19 BIG - Private 09:00 vs 12:00):
        # a gap is a note, never a start clock
        if f.get("kickoff_utc") and clocks and abs(
                _utc(f["kickoff_utc"]) - clocks[0]) > MAX_CLOCK_GAP:
            leg.add("sport_identity", NOTE, f"pinned kickoff {f['kickoff_utc']} vs "
                    f"the leg's {raw.get('kickoff_utc')}")
        if f.get("status") != "IDENTIFIED":
            leg.add("sport_identity", DEFECT,
                    f"status {f.get('status')} ({f.get('reason')})")
        elif f.get("sofascore_event_id") != leg.eid:
            leg.add("sport_identity", DEFECT,
                    f"pinned id {f.get('sofascore_event_id')} != leg {leg.eid}")
        else:
            if f.get("home_is_team1") is None:
                leg.add("sport_identity", DEFECT, "home_is_team1 unknown")
            gap = f.get("start_gap_h")
            if gap is not None and abs(float(gap)) > MAX_START_GAP_H:
                leg.add("sport_identity", DEFECT, f"start gap {gap} h "
                        f"({f.get('match_method')})")
        raw["_identity"] = {k: f.get(k) for k in (
            "status", "match_method", "home_is_team1", "start_gap_h")}
    leg.ran.append("sport_market")
    family = str(raw.get("family") or raw.get("market"))
    allowed = day.family_of(sport, raw.get("market_id"), family)
    if allowed is None or allowed != family:
        leg.add("sport_market", DEFECT, f"family {family} (market_id "
                f"{raw.get('market_id')}) not allowed: {allowed}")
    if not day.line_in_fit(sport, family, raw.get("line")):
        leg.add("sport_market", DEFECT, f"line {raw.get('line')} outside the "
                "curve's fit")
    if raw.get("locked") or day.read is None or raw.get("forecast_p") is None:
        return clocks
    leg.ran.append("confidence")
    reader = day.read
    side, odds = str(raw.get("side") or raw["direction"]), float(raw["odds"])
    conf = confidence_reading(
        lambda p_: reader(sport, family, side, p_, odds),
        float(raw["forecast_p"]), float(raw["confidence"]))
    printed = float(raw["confidence"])
    if conf is None or abs(float(conf.value) - printed) > CONF_TOL:
        leg.add("confidence", DEFECT, f"printed {printed} vs re-read "
                f"{None if conf is None else round(float(conf.value), 4)}")
    return clocks


# --- live --------------------------------------------------------------------


def live_check(legs: list[Leg], fixtures: Mapping[int, Fixture], date: str,
               limit: int | None) -> list[str]:
    """Re-ask Superbet once per fixture with OFFER's own fetcher; returns
    the asked event ids' summary lines (stdout is kept short)."""
    from bet.sofa.offer import OfferFetcher, day_flags
    from bet.sofa.superbet import SuperbetClient

    # a locked leg, or one the clocks already show started, is not re-asked
    targets = [x for x in legs if x.sport in ("football", "tennis")
               and not x.raw.get("locked") and x.eid in fixtures
               and not any(f["check"] == "clocks" and f["level"] == DEFECT
                           for f in x.findings)]
    order: list[int] = []
    for x in targets:
        if x.eid not in order:
            order.append(x.eid)
    if limit is not None:
        order = order[:limit]
    if not order:
        return ["live: nothing to ask"]
    fetcher = OfferFetcher(SuperbetClient(), **day_flags(date))
    offers = {o.sofascore_event_id: o
              for o in fetcher.fetch_offers([fixtures[e] for e in order])}
    failed = {str(su) for su, _ in fetcher.errors}
    unreached = set(fetcher.not_reached)
    asked = set(order)
    for x in targets:
        if x.eid not in asked:
            continue
        x.ran.append("live")
        offer = offers.get(x.eid)
        su_ids = set(fixtures[x.eid].superbet_event_ids)
        if offer is None or x.eid in unreached or (
                su_ids & failed and not (offer and offer.rungs)):
            x.live = {"status": CANNOT}
            x.add("live", CANNOT, "Superbet not reached / listing error")
            continue
        if offer.superbet_started_utc is not None:
            x.live = {"status": "STARTED"}
            x.add("live", NOTE, f"Superbet reports it started "
                  f"({_z(offer.superbet_started_utc)})")
            continue
        line = x.raw.get("line")
        rung = next((r for r in offer.rungs if r.market == x.raw["market"]
                     and (r.subject or "") == str(x.raw.get("subject") or "")
                     and line is not None and abs(r.line - float(line)) < 1e-9),
                    None)
        new = None if rung is None else (
            rung.over_odds if x.raw["direction"] == "OVER" else rung.under_odds)
        if new is None:
            x.live = {"status": "MISSING"}
            x.add("live", DEFECT, "the rung is no longer offered")
            continue
        old = x.odds
        if old is not None and abs(float(new) - old) < 1e-9:
            x.live = {"status": "OK", "odds": float(new)}
            continue
        xv = float(x.raw["confidence"]) * float(new)
        x.live = {"status": "CHANGED", "odds": float(new), "was": old,
                  "x": round(xv, 4)}
        x.add("live", NOTE if xv >= 0.90 else DEFECT,
              f"price {old} -> {new}, confidence x odds {xv:.3f}")
    return [f"live: asked {len(order)} fixtures, errors {len(fetcher.errors)}, "
            f"not reached {len(unreached)}"]


# --- report ------------------------------------------------------------------


def leg_label(raw: Mapping[str, Any]) -> str:
    if raw.get("superbet_market"):
        return f"{raw['superbet_market']}: {raw.get('superbet_selection')}"
    period = f" p{raw['period']}" if raw.get("period") else ""
    return (f"{raw.get('market')} {raw.get('subject') or ''} {raw.get('line')} "
            f"{raw.get('direction')}{period}").replace("  ", " ")


def record(leg: Leg) -> dict[str, Any]:
    r = leg.raw
    keys = ("position", "sport", "match", "competition", "kickoff_utc",
            "sofascore_event_id", "market", "subject", "line", "direction",
            "period", "superbet_market", "superbet_selection", "confidence",
            "calibrated_on", "sample_size", "locked", "printed_at_utc")
    out = {k: r.get(k) for k in keys}
    out.update(kind=leg.kind, in_set=leg.in_set, odds=leg.odds,
               checks_run=leg.ran, findings=leg.findings)
    for extra in ("_side", "_identity"):
        if extra in r:
            out[extra.lstrip("_")] = r[extra]
    if leg.live is not None:
        out["live"] = leg.live
    return out


def candidate_reads(legs: list[Leg]) -> list[dict[str, Any]]:
    """NO_BET for an unlocked leg with a hard defect, validated as LegRead."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for x in legs:
        hard = [f for f in x.findings if f["level"] == DEFECT and f["check"] in HARD]
        if not hard or x.raw.get("locked"):
            continue
        r = x.raw
        line = r.get("line")
        measured = x.sport not in ("football", "tennis")
        entry = {
            "sofascore_event_id": x.eid,
            "market": (str(r.get("family") or r["market"]) if measured
                       else str(r["market"])),
            "subject": str(r.get("subject") or ""),
            "line": None if line is None else float(line),
            "direction": str(r.get("side") or r["direction"]) if measured
            else str(r["direction"]),
            "verdict": "NO_BET", "author": "verifier",
            "reason": "verify_legs: " + "; ".join(
                f"{f['check']}: {f['detail']}" for f in hard)[:400],
            "period": int(r["period"]) if measured and r.get("period") is not None
            else None,
        }
        key = tuple(entry[k] for k in ("sofascore_event_id", "market", "subject",
                                       "line", "direction", "period"))
        if key in seen:
            continue
        seen.add(key)
        LegRead.model_validate(entry)
        out.append(entry)
    return out


def day_summary(legs: list[Leg]) -> list[str]:
    """Printed legs by sport, family, curve source, thin sample, competition
    and the matches with >= 3 legs - where an anti-selection would show."""
    singles = [x for x in legs if x.kind == "single"]

    def table(title: str, counts: Counter[str], top: int | None = None) -> list[str]:
        rows = counts.most_common(top)
        return [f"**{title}**: " + ", ".join(f"{k} {v}" for k, v in rows), ""]

    out = ["## Day summary (printed singles)", ""]
    out += table("sport", Counter(x.sport for x in singles))
    out += table("market family (top 15)", Counter(
        str(x.raw.get("family") or x.raw.get("market")) for x in singles), 15)
    out += table("calibrated_on prefix", Counter(
        str(x.raw.get("calibrated_on") or "?").split(":")[0] for x in singles))
    sizes = [(x, int(x.raw.get("sample_size") or 0)) for x in singles]
    thin = [x for x, n in sizes if 0 < n < 8]
    none = sum(1 for _, n in sizes if n == 0)
    out += [f"**sample 1 <= n < 8**: {len(thin)} legs "
            f"({Counter(str(x.raw.get('market')) for x in thin).most_common(5)}); "
            f"no sample (rating-only / sport model): {none}", ""]
    out += table("competition (top 10)", Counter(
        f"{x.raw.get('competition')} ({x.sport})" for x in singles), 10)
    per_match = Counter(str(x.raw.get("match")) for x in singles)
    many = [(m, n) for m, n in per_match.most_common() if n >= 3]
    out += [f"**matches with >= 3 legs**: {len(many)} matches, "
            f"{sum(n for _, n in many)} legs; top: "
            + ", ".join(f"{m} {n}" for m, n in many[:8]), ""]
    return out


def write_md(path: Path, date: str, population: str, legs: list[Leg],
             counts: dict[str, Counter[str]], day_findings: list[str],
             reads: list[dict[str, Any]]) -> None:
    lines = [f"# verify_legs {date} ({population}, {len(legs)} legs)", ""]
    lines += ["| check | legs run | DEFECT | NOTE | CANNOT_VERIFY |",
              "|---|---|---|---|---|"]
    for c in CHECKS:
        k = counts[c]
        lines.append(f"| {c} | {k['run']} | {k[DEFECT]} | {k[NOTE]} | {k[CANNOT]} |")
    lines.append("")
    if day_findings:
        lines += ["## Day-level", ""] + [f"- {d}" for d in day_findings] + [""]
    flagged = [x for x in legs if x.findings]
    flagged.sort(key=lambda x: (0 if any(f["level"] == DEFECT for f in x.findings)
                                else 1, int(x.raw.get("position") or 10**6)))
    lines += [f"## Legs with a finding ({len(flagged)})", "",
              "| pos | sport | match | leg | conf | odds | lock | level "
              "| check: detail |",
              "|---|---|---|---|---|---|---|---|---|"]
    for x in flagged[:TABLE_LIMIT]:
        for f in x.findings:
            lines.append(
                f"| {x.raw.get('position') or x.kind} | {x.sport} "
                f"| {x.raw.get('match')} "
                f"| {leg_label(x.raw)} | {x.raw.get('confidence')} | {x.odds} "
                f"| {'L' if x.raw.get('locked') else ''} | {f['level']} "
                f"| {f['check']}: {f['detail'].replace('|', '/')} |")
    if len(flagged) > TABLE_LIMIT:
        lines.append(f"\n... {len(flagged) - TABLE_LIMIT} more legs in "
                     "verify_legs.jsonl")
    lines.append("")
    lines += day_summary(legs)
    lines += ["## Candidate reads (NO_BET, hard defects of unlocked legs)", "",
              "```json reads", json.dumps(reads, ensure_ascii=False, indent=1),
              "```", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


# --- main --------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    t0 = time.monotonic()
    runs_dir = Path(args.runs_dir)
    run_dir = runs_dir / args.date
    coupon = run_dir / COUPON_ARTIFACT
    needed = [coupon, run_dir / "02_fixtures.json", run_dir / "05_sheet.json"]
    missing = [p.name for p in needed if not p.exists()]
    if missing:
        print(f"verify_legs: artifacts missing: {', '.join(missing)}")
        return 2
    doc = _load(coupon)
    fixtures_raw = {int(f["sofascore_event_id"]): f
                    for f in _load(run_dir / "02_fixtures.json")}
    fx_models = {f.sofascore_event_id: f for f in RootModel[list[Fixture]]
                 .model_validate_json((run_dir / "02_fixtures.json").read_bytes()).root}
    every = printed_legs(doc, fixtures_raw)
    legs = every if args.all else read_set_legs(run_dir, every)
    population = "all printed" if args.all else "read set"

    sheet: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in _load(run_dir / "05_sheet.json"):
        line = row.get("line")
        sheet.setdefault((int(row["sofascore_event_id"]), str(row["market"]),
                          str(row.get("subject") or ""),
                          None if line is None else float(line),
                          str(row["direction"])), row)
    samples_path = run_dir / "03_samples.json"
    samples = ({int(s["sofascore_event_id"]): s for s in _load(samples_path)}
               if samples_path.exists() else {})
    offer_path = run_dir / "04_offer.json"
    offers = _load(offer_path) if offer_path.exists() else []
    seen_ko = {int(o["sofascore_event_id"]): o.get("superbet_kickoff_seen_utc")
               for o in offers}
    started = {int(o["sofascore_event_id"]): str(o["superbet_started_utc"])
               for o in offers if o.get("superbet_started_utc")}
    status = fs.load(run_dir)
    built = _utc(doc["created_at_utc"])
    built_from = doc.get("built_from") or {}
    gated_main = (_utc(built_from["08_confidence.json"])
                  if built_from.get("08_confidence.json") else None)
    sports = sport_day(runs_dir, args.date, doc,
                       [x for x in legs if x.sport not in ("football", "tennis")])

    for x in legs:
        if x.sport in ("football", "tennis"):
            fx = fx_models.get(x.eid)
            check_sheet(x, sheet, samples, fx)
            check_side(x, fx)
            entry = status.get(x.eid)
            clocks = kickoff_clocks(fixtures_raw.get(x.eid), seen_ko.get(x.eid),
                                    fs.refreshed_start(entry))
            check_clocks(x, clocks, built, started.get(x.eid), entry,
                         (fixtures_raw.get(x.eid) or {}).get("sofascore_status"),
                         gated_main)
        else:
            clocks = check_sport(x, sports)
            entry = status.get(x.eid)
            fresh = fs.refreshed_start(entry)
            if fresh:
                clocks.append(_utc(fresh))
            check_clocks(x, clocks, built, None, entry, None, sports.built)

    # The sport confidence is re-read with today's line evidence and curves:
    # on a day built before they were refitted a mismatch is the refit, not
    # a defect (10-17 / 10-18 read 28 / 27 such legs).
    from bet.sofa import sport_confidence as scf
    from bet.sofa.config import config_path
    newer = [p for p in (config_path("sofa_superbet_line_evidence.json"),
                         scf.calibration_path_for(args.date))
             if p.exists() and datetime.fromtimestamp(p.stat().st_mtime, UTC) > built]
    if newer:
        for x in legs:
            for f in x.findings:
                if f["check"] == "confidence" and f["level"] == DEFECT:
                    f["level"] = NOTE
                    f["detail"] += (f" (re-read on {newer[0].name}, newer than "
                                    "the build)")

    out_lines: list[str] = []
    if args.live:
        out_lines += live_check(legs, fx_models, args.date, args.limit_fixtures)

    day_findings: list[str] = []
    try:
        from bet.sofa import rebuild_plan
        state = rebuild_plan.observe(str(runs_dir), args.date, built,
                                     timedelta(minutes=45))
        day_findings = [f"SHEET stale: {why}"
                        for why in rebuild_plan.audit_sheet_stale(state)]
    except Exception as exc:  # noqa: BLE001 - a day-level check, not the screen
        day_findings = ["CANNOT_VERIFY sheet stale markers: "
                        f"{type(exc).__name__}: {exc}"]

    counts: dict[str, Counter[str]] = {c: Counter() for c in CHECKS}
    for x in legs:
        for c in set(x.ran):
            counts[c]["run"] += 1
        for f in x.findings:
            counts[f["check"]][f["level"]] += 1
    reads = candidate_reads(legs)

    out_dir = Path(args.out_dir) if args.out_dir else (
        Path(os.environ.get("TMPDIR") or tempfile.gettempdir())
        / f"sofa_verify_{args.date}")
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "verify_legs.jsonl", "w", encoding="utf-8") as fh:
        for x in legs:
            fh.write(json.dumps(record(x), ensure_ascii=False, default=str) + "\n")
    write_md(out_dir / "verify_legs.md", args.date, population, legs, counts,
             day_findings, reads)

    print(f"verify_legs {args.date}: {population}, {len(legs)} legs, "
          f"{len({x.eid for x in legs})} matches, {time.monotonic() - t0:.1f} s")
    for c in CHECKS:
        k = counts[c]
        if k["run"] or k[CANNOT]:
            print(f"  {c}: run {k['run']}, DEFECT {k[DEFECT]}, NOTE {k[NOTE]}, "
                  f"CANNOT_VERIFY {k[CANNOT]}")
    print("  confidence: football / tennis not re-derived (not a pure call)")
    if args.live:
        print("  live: measured-sport legs not re-asked (v1)")
    for line in out_lines + day_findings[:2]:
        print(f"  {line}"[:200])
    if len(day_findings) > 2:
        print(f"  ... {len(day_findings) - 2} more day-level findings in the .md")
    print(f"  candidate NO_BET reads: {len(reads)}")
    print(f"  out: {out_dir / 'verify_legs.md'}")
    bad = any(f["level"] in (DEFECT, CANNOT) for x in legs for f in x.findings)
    bad = bad or any(d.startswith(("SHEET stale", "CANNOT_VERIFY"))
                     for d in day_findings)
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--date", required=True)
    parser.add_argument("--all", action="store_true",
                        help="every printed single and builder leg, not the read set")
    parser.add_argument("--live", action="store_true",
                        help="re-ask Superbet for football / tennis legs")
    parser.add_argument("--limit-fixtures", type=int, default=None,
                        help="with --live: ask at most this many fixtures")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--runs-dir",
                        default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa"))
    args = parser.parse_args(argv)
    try:
        return run(args)
    except FileNotFoundError as exc:
        print(f"verify_legs: artifacts missing: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
