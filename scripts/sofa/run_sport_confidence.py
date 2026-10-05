#!/usr/bin/env python3
"""SPORT_CONFIDENCE - the hockey, basketball, volleyball and CS2 legs the
one coupon may print, with a confidence from statistics (plan 2026-10-05,
D1/D2, F3, F7).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_confidence.py \\
        --date 2026-10-06

Reads runs/sofa/<d>/sport_fixtures.json (SPORT_IDENTITY), the day's SHADOW
and CS2 snapshots, config/sofa_sport_confidence_calibration.json
(fit_sport_confidence.py) and the database read-only; writes
runs/sofa/<d>/08_confidence_sports.json and nothing else - never the
settled table, never a curve.

Per Superbet side of an event whose kickoff is in [D 00:00Z, D+1 00:00Z):
an identified fixture (else NOT_IDENTIFIED, or its DUPLICATE_* state), not
started (KICKED_OFF: inside the coupon's kickoff margin of the earlier of
Superbet's and Sofascore's start), the event's newest pre-start snapshot no
older than sport_coupon.MAX_PRICE_AGE (STALE_PRICE), volleyball's
tournament with a SETTLED event in the last 14 days, an allowed market
(sport_confidence.ALLOWED_MARKETS / CS2_FAMILIES), a whole outcome group.
The model's probability (score_model / cs2_engine, no price) is read
through the admitted curve: confidence = the bucket's Wilson lower bound
(else NOT_CALIBRATED). Then the coupon's price filters (D1): confidence >=
the official floor, odds >= 1/0.9202, margin <= 15%, confidence x odds >=
0.90.

Exit: 0 OK; 1 PARTIAL - a sport NOT_CALIBRATED (no calibration file, no
section, nothing admitted) or NOT_IDENTIFIED (no sport_fixtures.json), the
artifact still written; 2 a crash.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import cs2, cs2_engine, shadow, sport_coupon  # noqa: E402
from bet.sofa import sport_confidence as scf  # noqa: E402
from bet.sofa import sport_identity as si  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.confidence import MIN_ODDS_FOR_CEILING, PROFILES  # noqa: E402
from bet.sofa.config import SofaConfig, config_path  # noqa: E402
from bet.sofa.timeutil import frozen_clock_refusal, now  # noqa: E402

ARTIFACT = "08_confidence_sports.json"
MIN_X = PROFILES["standard"].min_ev  # 0.90, the official coupon's
MAX_OVERROUND = PROFILES["standard"].max_overround  # 0.15
FLOOR = PROFILES["standard"].floor  # 0.70
MIN_ODDS = MIN_ODDS_FOR_CEILING  # 1/0.9202

OK, NOT_CALIBRATED, NOT_IDENTIFIED = "OK", "NOT_CALIBRATED", "NOT_IDENTIFIED"


class Forecaster(Protocol):
    def probability(self, sport: str, fixture: Mapping[str, Any], ev: Any,
                    line: Any) -> float | None: ...

    def sample(self, sport: str, fixture: Mapping[str, Any], ev: Any,
               line: Any) -> tuple[int, int]: ...


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


@dataclass
class DbForecaster:
    """The score model / CS2 engine as of `at`, from the database read-only.
    Each sport's history is read once, on its first leg."""

    db_path: str
    at: datetime
    _shadow: dict[str, tuple[Any, scf.TeamGames]] = field(default_factory=dict)
    _sims: dict[tuple[str, str], list[shadow.GameResult] | None] = field(
        default_factory=dict)
    _cs2: tuple[list[cs2_engine.MapRow], dict[int, scf.SeriesRow],
                cs2_engine.RatingModel] | None = None

    def _shadow_model(self, sport: str) -> tuple[Any, scf.TeamGames]:
        if sport not in self._shadow:
            from bet.sofa.score_model import build_model, load_events

            sp = shadow.SPORTS[sport]  # type: ignore[index]
            cut = int(self.at.timestamp())
            events = {k: e for k, e in load_events(self.db_path, sp).items()
                      if isinstance(e.get("startTimestamp"), int)
                      and e["startTimestamp"] < cut}
            history = scf.parse_history(events, sp)
            model = build_model([g.rating for g in history], sp, cut)
            self._shadow[sport] = (model, scf.TeamGames.build(events.values(), sp))
        return self._shadow[sport]

    def _cs2_model(self) -> tuple[list[cs2_engine.MapRow], dict[int, scf.SeriesRow],
                                  cs2_engine.RatingModel]:
        if self._cs2 is None:
            maps, series = scf.load_cs2(self.db_path, int(self.at.timestamp()))
            self._cs2 = (maps, series, cs2_engine.build_ratings(maps))
        return self._cs2

    @staticmethod
    def _teams(fixture: Mapping[str, Any]) -> tuple[int, int]:
        home, away = int(fixture["home_id"]), int(fixture["away_id"])
        return (home, away) if fixture["home_is_team1"] else (away, home)

    def probability(self, sport: str, fixture: Mapping[str, Any], ev: Any,
                    line: Any) -> float | None:
        if sport == "cs2":
            maps, _, ratings = self._cs2_model()
            t1, t2 = self._teams(fixture)
            mp = cs2_engine.model_probability(
                line, t1, t2, ev.team1, ev.team2, int(fixture.get("best_of") or 3),
                maps, ratings, bool(fixture["home_is_team1"]))
            return None if mp is None else mp.p
        from bet.sofa.score_model import line_probability

        sp = shadow.SPORTS[sport]  # type: ignore[index]
        key = (sport, str(fixture["superbet_event_id"]))
        if key not in self._sims:
            model, _ = self._shadow_model(sport)
            comp = fixture.get("competition_id")
            exp = None if comp is None else model.expected(
                int(comp), int(fixture["home_id"]), int(fixture["away_id"]),
                int(_utc(ev.kickoff_utc).timestamp()))
            if exp is None:
                self._sims[key] = None
            else:
                mh, ma = exp
                mu1, mu2 = (mh, ma) if fixture["home_is_team1"] else (ma, mh)
                self._sims[key] = model.simulate(
                    mu1, mu2, seed=int(fixture["sofascore_event_id"]))
        games = self._sims[key]
        return None if games is None else line_probability(line, games, sp)

    def sample(self, sport: str, fixture: Mapping[str, Any], ev: Any,
               line: Any) -> tuple[int, int]:
        t1, t2 = self._teams(fixture)
        if sport == "cs2":
            maps, series, _ = self._cs2_model()
            return scf.cs2_sample_hit_rate(
                line, cs2.team_of(line.subject, ev.team1, ev.team2), t1, t2,
                maps, series)
        _, games = self._shadow_model(sport)
        return scf.sample_hit_rate(line, shadow.SPORTS[sport], t1, t2,  # type: ignore[index]
                                   games, int(_utc(ev.kickoff_utc).timestamp()))


def _bump(counts: dict[str, int], key: str, n: int = 1) -> None:
    counts[key] = counts.get(key, 0) + n


def _group_key(sport: str, key: tuple[Any, ...]) -> tuple[Any, ...]:
    return key[:4]


def _shape(sport: str, line: Any) -> str:
    if sport == "cs2":
        return cs2.group_shape(line.family)
    return shadow.group_shape(sport, line.market_id)  # type: ignore[arg-type]


def _allowed(sport: str, line: Any) -> str | None:
    if sport == "cs2":
        return scf.family_of("cs2", None, line.family)
    return scf.family_of(sport, line.market_id, line.family)


def sport_status(sport: str, fixtures_doc: Mapping[str, Any] | None,
                 calibration: scf.SportCalibration | None) -> str:
    if fixtures_doc is None:
        return NOT_IDENTIFIED
    run = fixtures_doc.get("sports_run")
    if run is not None and sport not in run:
        return NOT_IDENTIFIED
    if calibration is None or not calibration.has_sport(sport) \
            or not calibration.admitted(sport):
        return NOT_CALIBRATED
    return OK


def build_sport(sport: str, date: str, runs_dir: str,
                fixtures_doc: Mapping[str, Any] | None,
                calibration: scf.SportCalibration | None,
                forecaster: Forecaster, at: datetime
                ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    status = sport_status(sport, fixtures_doc, calibration)
    fixtures = si.fixtures_by_event(fixtures_doc)
    start, end = si.day_window(date)
    events, _ = sport_coupon.day_events(runs_dir, sport, date)  # type: ignore[arg-type]
    settled_tournaments = (
        sport_coupon.settled_tournaments(runs_dir, sport, date)
        if sport in sport_coupon.SETTLED_TOURNAMENT_SPORTS else None)
    refused: dict[str, int] = {}
    legs: list[dict[str, Any]] = []
    for ev in sorted(events.values(), key=lambda e: (e.kickoff_utc,
                                                     str(e.superbet_event_id))):
        sb_kickoff = _utc(ev.kickoff_utc)
        if not (start <= sb_kickoff < end) or not ev.fetched_at:
            continue
        newest = max(ev.fetched_at.values(), key=_utc)
        current = {k: ln for k, ln in ev.sides.items() if ev.fetched_at[k] == newest}
        allowed = {k: ln for k, ln in current.items() if _allowed(sport, ln)}
        _bump(refused, "MARKET_NOT_ALLOWED", len(current) - len(allowed))
        if not allowed:
            continue
        n_sides = len(allowed)
        fixture = fixtures.get((sport, str(ev.superbet_event_id)))
        if status == NOT_IDENTIFIED or fixture is None:
            _bump(refused, NOT_IDENTIFIED, n_sides)
            continue
        if fixture.get("status") != si.IDENTIFIED:
            state = str(fixture.get("status"))
            _bump(refused, NOT_IDENTIFIED if state == si.NOT_IDENTIFIED else state,
                  n_sides)
            continue
        kickoff = sb_kickoff
        if fixture.get("sofascore_start_utc"):
            kickoff = min(kickoff, _utc(str(fixture["sofascore_start_utc"])))
        if kickoff - at < sport_coupon.KICKOFF_MARGIN:
            _bump(refused, "KICKED_OFF", n_sides)
            continue
        if at - _utc(newest) > sport_coupon.MAX_PRICE_AGE:
            _bump(refused, "STALE_PRICE", n_sides)
            continue
        if settled_tournaments is not None and ev.tournament not in settled_tournaments:
            _bump(refused, "TOURNAMENT_NEVER_SETTLED", n_sides)
            continue
        if status == NOT_CALIBRATED:
            _bump(refused, NOT_CALIBRATED, n_sides)
            continue
        assert calibration is not None
        groups: dict[tuple[Any, ...], dict[str, float]] = defaultdict(dict)
        for key, ln in allowed.items():
            groups[_group_key(sport, key)][ln.side] = ln.odds
        for key, ln in sorted(allowed.items(), key=lambda kv: repr(kv[0])):
            group_odds = groups[_group_key(sport, key)]
            if cs2.group_fair(group_odds, _shape(sport, ln)) is None:  # type: ignore[arg-type]
                _bump(refused, "INCOMPLETE_GROUP")
                continue
            family = _allowed(sport, ln)
            assert family is not None
            p = forecaster.probability(sport, fixture, ev, ln)
            if p is None:
                _bump(refused, "NO_MODEL_P")
                continue
            conf = calibration.lookup(sport, family, ln.side, p)
            if conf is None:
                _bump(refused, NOT_CALIBRATED)
                continue
            margin = cs2.group_overround(group_odds)
            why = price_filter(conf.value, ln.odds, margin)
            if why is not None:
                _bump(refused, why)
                continue
            k, n = forecaster.sample(sport, fixture, ev, ln)
            legs.append(leg_dict(sport, ev, fixture, ln, family, conf, p, k, n,
                                 margin, kickoff, newest))
    return {"status": status, "refused": dict(sorted(refused.items())),
            "legs": len(legs)}, legs


def price_filter(confidence: float, odds: float, margin: float) -> str | None:
    """D1's price conditions, the official coupon's numbers; None = passes."""
    if confidence < FLOOR:
        return "BELOW_FLOOR"
    if odds < MIN_ODDS:
        return "ODDS_TOO_LOW"
    if margin > MAX_OVERROUND:
        return "MARGIN_TOO_HIGH"
    if margin < 0:
        return "NEGATIVE_MARGIN"
    if MIN_X is not None and round(confidence * odds, 9) < MIN_X:
        return "BELOW_MIN_X"
    return None


def leg_dict(sport: str, ev: Any, fixture: Mapping[str, Any], ln: Any,
             family: str, conf: scf.Confidence, p: float, k: int, n: int,
             margin: float, kickoff: datetime, fetched: str) -> dict[str, Any]:
    sid = int(fixture["sofascore_event_id"])
    leg: dict[str, Any] = {
        "sport": sport,
        "group_key": f"sofa:{sid}",
        "sofascore_event_id": sid,
        "superbet_event_id": str(ev.superbet_event_id),
        "market_id": None if sport == "cs2" else int(ln.market_id),
        "family": family,
        "period": int(ln.map_nr if sport == "cs2" else ln.period),
        "subject": ln.subject,
        "line": ln.line,
        "side": ln.side,
        "confidence": round(conf.value, 4),
        "calibrated_on": conf.calibrated_on,
        "calibration_n": conf.n,
        "sample_hit_rate": round(k / n, 4) if n else None,
        "sample_k": k,
        "sample_n": n,
        "forecast_p": round(p, 4),
        "forecast_source": "cs2_engine" if sport == "cs2" else "score_model",
        "odds": ln.odds,
        "x": round(conf.value * ln.odds, 4),
        "overround": round(margin, 4),
        "kickoff_utc": si.iso(kickoff),
        "source_date": getattr(ev, "source_date", None),
        "price_fetched_at_utc": fetched,
        "match": f"{ev.team1} - {ev.team2}",
        "competition": ev.tournament,
    }
    if sport == "cs2":
        leg.update({"team1": ev.team1, "team2": ev.team2, "map_nr": int(ln.map_nr)})
    return leg


def build(date: str, runs_dir: str, calibration_path: Path, forecaster: Forecaster,
          at: datetime, sports: tuple[str, ...] = scf.SPORT_KEYS
          ) -> tuple[dict[str, Any], int]:
    fixtures_doc = si.load_fixtures(Path(runs_dir) / date / si.FIXTURES_FILE)
    calibration = scf.SportCalibration.load(calibration_path)
    doc: dict[str, Any] = {
        "created_at_utc": si.iso(at),
        "date": date,
        "calibration_fitted_from": None if calibration is None
        else calibration.fitted_from,
        "rule": {"floor": FLOOR, "min_x": MIN_X, "max_overround": MAX_OVERROUND,
                 "min_odds": round(MIN_ODDS, 4),
                 "kickoff_margin_min": int(
                     sport_coupon.KICKOFF_MARGIN.total_seconds() // 60),
                 "max_price_age_min": int(
                     sport_coupon.MAX_PRICE_AGE.total_seconds() // 60),
                 "day_window_utc": [si.iso(t) for t in si.day_window(date)]},
        "sports": {},
        "legs": [],
    }
    for sport in sports:
        entry, legs = build_sport(sport, date, runs_dir, fixtures_doc, calibration,
                                  forecaster, at)
        doc["sports"][sport] = entry
        doc["legs"] += legs
    doc["legs"].sort(key=lambda g: (-g["confidence"], g["kickoff_utc"],
                                    g["group_key"], g["family"], str(g["line"]),
                                    g["side"]))
    write_atomic(Path(runs_dir) / date / ARTIFACT,
                 json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    code = 0 if all(s["status"] == OK for s in doc["sports"].values()) else 1
    return doc, code


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", required=True)
    args = ap.parse_args()
    config = SofaConfig.from_env()
    frozen = frozen_clock_refusal(config.runs_dir)
    if frozen:
        print(frozen, file=sys.stderr)
        return 2
    at = now()
    # read-only from the first byte: a probe that the file opens mode=ro
    sqlite3.connect(f"file:{config.db_path}?mode=ro", uri=True).close()
    forecaster = DbForecaster(config.db_path, at)
    doc, code = build(args.date, config.runs_dir,
                      config_path(scf.CALIBRATION_FILE), forecaster, at)
    print("SOFA_SUMMARY: " + json.dumps({
        "stage": "SPORT_CONFIDENCE", "verdict": "OK" if code == 0 else "PARTIAL",
        "sports": doc["sports"], "legs": len(doc["legs"]),
        "output_path": str(Path(config.runs_dir) / args.date / ARTIFACT),
    }), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
