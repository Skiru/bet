#!/usr/bin/env python3
"""Coverage review 2026-11-05: offer vs what we read, why priced lines do not
print, statistics coverage in the cache, player markets, and the operator's
yardstick (our p vs Superbet's de-vigged price on settled lines). Read-only
evidence for docs/sofa/evidence/pokrycie_sportow_2026-11-05.md.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_coverage_2026_11_05.py \\
        artifacts --from 2026-10-22 --to 2026-11-04 --json-out <f>
    ... yardstick --from 2026-10-22 --to 2026-11-04 --db-path data/sofa.db \\
        --rows-dir data/line_evidence/rows_before_2026-11-05 --json-out <f>
    ... cache --from 2026-10-22 --to 2026-11-04 --db-path data/sofa.db \\
        --json-out <f>

`artifacts` reads runs/sofa/<d>/ (04_offer, 02_fixtures, 03_samples,
market_coverage.json, 11_coupon.json) and the measured
sports' runs/sofa/shadow/<sport>/<d>/ and runs/sofa/cs2/<d>/ (snapshots,
player_model.jsonl, settled.json). A "line" is one (event, market, period,
subject, line) group - both sides of a two-way line count once. The
CONFIDENCE stage's refusal record is display only and read by no script here
(tests/sofa/test_priced_rows.py); the report's refusal tables were counted
outside the repository.

`yardstick`: football / tennis live `sofa_settled_row` rows of the window
(p_central = SHEET's p before the curve; market_p = the de-vigged price where
both sides are quoted), the sports' settled Superbet lines (team lines: the
score model's p from `<sport>_superbet_settled.jsonl` of the line-evidence
rows joined to SHADOW_SETTLE's `fair_p`; player and CS2 lines: `model_p` /
`fair_p` on the graded line). Brier of our p minus Brier of the price (< 0 =
we beat the price), raw and after an in-sample Platt recalibration (an upper
bound for any curve on these rows), with a game bootstrap.

`cache`: the competitions of the window's identified fixtures; for their
finished events of the 365 days before --to, the share with team statistics,
period scores and player statistics. The database is opened read-only
(`mode=ro`); a `VACUUM INTO` copy does not fit the disk (56 GB, 27 GB free on
2026-11-05), so every query is a keyed read. Nothing is written but --json-out.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

RUNS = Path("runs/sofa")
SPORTS = ("hockey", "basketball", "volleyball", "cs2")
SLUG = {
    "football": "football",
    "hockey": "ice-hockey",
    "basketball": "basketball",
    "volleyball": "volleyball",
    "cs2": "esports",
    "tennis": "tennis",
}

MEASURED_BELOW = {
    "BELOW_CONFIDENCE_FLOOR",
    "BELOW_FLOOR",
    "BELOW_MIN_X",
    "NEGATIVE_LEG_EV",
    "MODE_LOSES",
    "ODDS_TOO_LOW",
    "MARGIN_TOO_HIGH",
    "LINE_BEYOND_SAMPLE",
    "CATCH_ALL_BUCKET",
}
CANNOT_MEASURE = {
    "NO_LINE_EVIDENCE",
    "NO_MODEL_P",
    "NO_LEAGUE_RATE",
    "NOT_IDENTIFIED",
    "NOT_SETTLEABLE",
    "NO_CLASS_CURVE",
    "NOT_CALIBRATED",
    "CROSS_LEAGUE_UNLINKED",
    "ONE_SIDED_NOT_ADMITTED",
    "THIN_SAMPLE_FOR_BUILDER",
    "SAMPLE_CROSSES_SEASON",
    "TOURNAMENT_NEVER_SETTLED",
    "NO_CURVE",
    "LINE_OUTSIDE_FIT",
    "BEST_OF_FIVE_NOT_MODELLED",
    "FRIENDLY_FIXTURE",
    "NO_RATING",
    "ID_CHANGED",
}
PRICE_TIMING = {
    "NO_PRICE",
    "NO_FETCHED_AT",
    "STALE_PRICE",
    "FIXTURE_NOT_AS_SCHEDULED",
    "ALREADY_PRINTED_PREV_DAY",
}
READS = {"WATCHED", "READ_NO_BET", "MODEL_ABOVE_OWN_SAMPLE"}


# the measured sports' records (unmapped_prices sport files, 2026-11-05)
SPORT_FILE_PREFIXES = ("hockey_", "basketball_", "volleyball_", "cs2_")


def category(reason: str | None) -> str:
    if reason is None:
        return "PASSED"
    if reason == "KICKED_OFF":
        return "KICKED_OFF"
    for name, group in (
        ("MEASURED_BELOW", MEASURED_BELOW),
        ("CANNOT_MEASURE", CANNOT_MEASURE),
        ("PRICE_TIMING", PRICE_TIMING),
        ("READS", READS),
    ):
        if reason in group:
            return name
    return "OTHER"


def days(a: str, b: str) -> list[str]:
    d0 = date.fromisoformat(a)
    n = (date.fromisoformat(b) - d0).days
    return [(d0 + timedelta(days=i)).isoformat() for i in range(n + 1)]


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def is_player(sport: str, market: str) -> bool:
    return market.startswith("player") or (
        sport == "football" and market.startswith("any_player")
    )


def sport_dir(sport: str, day: str) -> Path:
    return RUNS / "cs2" / day if sport == "cs2" else RUNS / "shadow" / sport / day


# --- artifacts ---------------------------------------------------------------


def football_day(day: str, out: dict[str, Any]) -> None:
    d = RUNS / day
    fixtures = load(d / "02_fixtures.json")
    sport_of = {f["sofascore_event_id"]: f["sport"] for f in fixtures}
    comp_of = {
        f["sofascore_event_id"]: str(f.get("competition_name")) for f in fixtures
    }
    offer = load(d / "04_offer.json")
    lines: Counter[str] = Counter()
    events = 0
    for fx in offer:
        if sport_of.get(fx["sofascore_event_id"]) != "football":
            continue
        if fx.get("rungs"):
            events += 1
        seen = {
            (r["market"], r.get("subject") or "", r.get("line"))
            for r in fx.get("rungs") or []
        }
        by_comp = out.setdefault("football_player_offer_by_comp", Counter())
        for market, _s, _l in seen:
            lines[market] += 1
            if market.startswith("player"):
                by_comp[comp_of.get(fx["sofascore_event_id"])] += 1
    fam = out.setdefault("football", {}).setdefault("offered", Counter())
    fam.update(lines)
    out["football"].setdefault("events", []).append(events)
    cov_path = d / "market_coverage.json"
    if cov_path.exists():
        cov = load(cov_path)
        um = out["football"].setdefault("unmapped", Counter())
        lab = out["football"].setdefault("unmapped_label", Counter())
        for f in cov["families"]:
            if f["sport"] == "football":
                um[f"{f['label']}|{f['family']}"] += f["occurrences"]
                lab[f["label"]] += f["occurrences"]
        out["football"].setdefault("coverage_days", []).append(day)
    up = out["football"].setdefault("unmapped_prices_files", 0)
    out["football"]["unmapped_prices_files"] = up + len(
        [f for f in (d / "unmapped_prices").glob("*.jsonl.gz")
         if not f.name.startswith(SPORT_FILE_PREFIXES)]
    )
    # samples: player identity gaps
    samples = load(d / "03_samples.json")
    pg = out["football"].setdefault("player_gaps", Counter())
    players_with_sample = out["football"].setdefault("player_samples", Counter())
    for fx in samples:
        if sport_of.get(fx["sofascore_event_id"]) != "football":
            continue
        for key in fx.get("players") or {}:
            players_with_sample[key.split("|")[0]] += 1
        for g in fx.get("gaps") or []:
            metric = g.get("metric") or ""
            if not metric.startswith("player"):
                continue
            detail = g.get("detail") or ""
            if g["reason"] == "NO_ENTITY_FOUND":
                if "never started" in detail:
                    kind = "NO_ENTITY_FOUND:never_started"
                elif "matched no squad member" in detail:
                    kind = "NO_ENTITY_FOUND:no_squad_member"
                else:
                    kind = "NO_ENTITY_FOUND:other"
            else:
                kind = g["reason"]
            pg[kind] += 1
            gap_comp = out.setdefault("football_player_gap_by_comp", Counter())
            gap_comp[(comp_of.get(fx["sofascore_event_id"]), kind)] += 1


def printed_day(day: str, out: dict[str, Any]) -> None:
    c = load(RUNS / day / "11_coupon.json")
    seen: set[tuple[Any, ...]] = set()
    for leg in c.get("legs") or []:
        sport = leg.get("sport")
        market = str(leg.get("family") or leg.get("market"))
        key = (
            sport,
            leg.get("sofascore_event_id"),
            market,
            leg.get("period"),
            leg.get("subject"),
            leg.get("line"),
            leg.get("direction") or leg.get("side"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.setdefault(sport, {}).setdefault("printed", Counter())[market] += 1


def sport_day(sport: str, day: str, out: dict[str, Any]) -> None:
    d = sport_dir(sport, day)
    s = out.setdefault(sport, {})
    last: dict[str, dict[str, Any]] = {}
    for rec in jsonl(d / "snapshots.jsonl"):
        last[str(rec["superbet_event_id"])] = rec
    lines: Counter[str] = Counter()
    for rec in last.values():
        seen = {
            (
                x.get("market_id") or x["family"],
                x["family"],
                x.get("period", x.get("map_nr")),
                x.get("subject") or "",
                x.get("line"),
            )
            for x in rec.get("lines") or []
        }
        for _m, fam, _p, _s, _l in seen:
            lines[fam] += 1
    s.setdefault("offered", Counter()).update(lines)
    s.setdefault("events", []).append(len(last))
    # player model (hockey / basketball)
    pm: dict[tuple[Any, ...], dict[str, Any]] = {}
    for r in jsonl(d / "player_model.jsonl"):
        pm[(r["superbet_event_id"], r["market_id"], r["subject"], r["line"])] = r
    for r in pm.values():
        fam = r["family"]
        s.setdefault("pm_lines", Counter())[fam] += 1
        if r.get("model_p") is not None:
            s.setdefault("pm_p", Counter())[fam] += 1
        else:
            s.setdefault("pm_reason", Counter())[str(r.get("model_reason"))] += 1
        s.setdefault("pm_match", Counter())[str(r.get("model_match"))] += 1
    # settlement
    sp = d / "settled.json"
    if sp.exists():
        doc = load(sp)
        for ev in (doc.get("events") or {}).values():
            s.setdefault("settle_state", Counter())[str(ev.get("state"))] += 1
            for k in (
                "player_no_box",
                "player_unmatched",
                "player_dnp",
                "ungradeable",
                "void",
                "unpaired",
                "stats_pending",
            ):
                try:
                    s.setdefault("settle_counts", Counter())[k] += int(ev.get(k) or 0)
                except (TypeError, ValueError):
                    pass
            graded = ev.get("graded") or []
            if isinstance(graded, str):
                continue
            for g in graded:
                fam = g["family"]
                kind = "player" if fam.startswith("player") else "team"
                s.setdefault("graded", Counter())[(kind, g.get("outcome"))] += 1


def artifacts(a: str, b: str) -> dict[str, Any]:
    out: dict[str, Any] = {"days": days(a, b)}
    for day in out["days"]:
        football_day(day, out)
        printed_day(day, out)
        for sport in SPORTS:
            sport_day(sport, day, out)
    return out


# --- details: where the cannot-measure rows and the lost events are ----------


def details(a: str, b: str) -> dict[str, Any]:
    """Per competition: the settle states that lose an event, the player
    model's refusals and the settle's unmatched player lines."""
    out: dict[str, Any] = {}
    for day in days(a, b):
        for sport in SPORTS:
            d = sport_dir(sport, day)
            tour: dict[str, str] = {}
            for rec in jsonl(d / "snapshots.jsonl"):
                tour[str(rec["superbet_event_id"])] = str(rec.get("tournament"))
            for r in jsonl(d / "player_model.jsonl"):
                t = tour.get(str(r["superbet_event_id"]), "?")
                ok = "P" if r.get("model_p") is not None else str(r.get("model_reason"))
                out.setdefault("pm", Counter())[(sport, t, ok)] += 1
            sp = d / "settled.json"
            if not sp.exists():
                continue
            for ev in (load(sp).get("events") or {}).values():
                t = str(ev.get("tournament"))
                out.setdefault("state", Counter())[
                    (sport, t, str(ev.get("state")))
                ] += 1
                try:
                    um = int(ev.get("player_unmatched") or 0)
                except (TypeError, ValueError):
                    um = 0
                if um:
                    out.setdefault("unmatched", Counter())[(sport, t)] += um
    return out


# --- yardstick ---------------------------------------------------------------


def brier_compare(
    p: np.ndarray,
    q: np.ndarray,
    y: np.ndarray,
    games: np.ndarray,
    reps: int = 300,
    seed: int = 7,
) -> dict[str, Any]:
    """Brier(p) - Brier(q), raw and Platt (in-sample) on p; game bootstrap."""
    p = np.clip(p, 1e-4, 1 - 1e-4)
    q = np.clip(q, 1e-4, 1 - 1e-4)
    pp = platt(p, y)
    d_raw = (p - y) ** 2 - (q - y) ** 2
    d_cal = (pp - y) ** 2 - (q - y) ** 2
    uniq, inv = np.unique(games, return_inverse=True)
    g_raw = np.bincount(inv, d_raw)
    g_cal = np.bincount(inv, d_cal)
    g_n = np.bincount(inv)
    rng = np.random.default_rng(seed)
    bs_raw, bs_cal = [], []
    for _ in range(reps):
        w = np.bincount(rng.integers(0, len(uniq), len(uniq)), minlength=len(uniq))
        n = (w * g_n).sum()
        bs_raw.append((w * g_raw).sum() / n)
        bs_cal.append((w * g_cal).sum() / n)
    return {
        "n": int(len(y)),
        "games": int(len(uniq)),
        "hit": round(float(y.mean()), 4),
        "mean_p": round(float(p.mean()), 4),
        "mean_price": round(float(q.mean()), 4),
        "brier_p": round(float(((p - y) ** 2).mean()), 5),
        "brier_price": round(float(((q - y) ** 2).mean()), 5),
        "d_raw": round(float(d_raw.mean()), 5),
        "d_raw_ci": [
            round(float(np.percentile(bs_raw, 2.5)), 5),
            round(float(np.percentile(bs_raw, 97.5)), 5),
        ],
        "d_platt": round(float(d_cal.mean()), 5),
        "d_platt_ci": [
            round(float(np.percentile(bs_cal, 2.5)), 5),
            round(float(np.percentile(bs_cal, 97.5)), 5),
        ],
    }


def platt(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    x = np.log(p / (1 - p))
    a, b = 1.0, 0.0
    for _ in range(50):
        z = np.clip(a * x + b, -30, 30)
        m = 1 / (1 + np.exp(-z))
        g = np.array([((m - y) * x).sum(), (m - y).sum()])
        w = m * (1 - m)
        h = np.array(
            [[(w * x * x).sum(), (w * x).sum()], [(w * x).sum(), w.sum()]]
        ) + 1e-9 * np.eye(2)
        step = np.linalg.solve(h, g)
        a, b = a - step[0], b - step[1]
        if np.abs(step).max() < 1e-8:
            break
    return np.asarray(1 / (1 + np.exp(-np.clip(a * x + b, -30, 30))))


def football_family(market: str) -> str:
    if market.startswith("player"):
        return "player_*"
    for stem in (
        "corners",
        "cards",
        "goals",
        "shots_on_target",
        "shots",
        "fouls",
        "offsides",
        "throw_ins",
        "goal_kicks",
        "saves",
        "tackles",
        "both_over",
        "result",
        "handicap",
    ):
        if market.startswith(stem):
            return stem + "_*"
    return market


def yardstick(a: str, b: str, db_path: str, rows_dir: str) -> dict[str, Any]:
    res: dict[str, Any] = {}
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    acc: dict[tuple[str, str], list[tuple[float, float, int, int]]] = defaultdict(list)
    q = (
        "select sport, market, sofascore_event_id, p_central, market_p, "
        "offered_odds, outcome "
        "from sofa_settled_row where run_date between ? and ? "
        "and outcome in ('WIN','LOSS')"
    )
    one_sided: dict[tuple[str, str], list[tuple[float, float, int, int]]] = defaultdict(
        list
    )
    for sport, market, ev, p, mp, odds, outcome in con.execute(q, (a, b)):
        y = 1 if outcome == "WIN" else 0
        fam = (
            football_family(market)
            if sport == "football"
            else market.split("_")[0] + "_*"
        )
        if mp is not None:
            acc[(sport, fam)].append((p, mp, y, ev))
            acc[(sport, "ALL")].append((p, mp, y, ev))
        elif odds:
            one_sided[(sport, fam)].append((p, min(1.0, 1 / odds), y, ev))
    for (sport, fam), rows in sorted(acc.items()):
        arr = np.array(rows)
        if len(arr) < 200:
            continue
        res[f"{sport}|{fam}|two_sided"] = brier_compare(
            arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
        )
    for (sport, fam), rows in sorted(one_sided.items()):
        arr = np.array(rows)
        if len(arr) < 200:
            continue
        res[f"{sport}|{fam}|one_sided_1/odds"] = brier_compare(
            arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
        )
    # measured sports
    for sport in SPORTS:
        team: dict[tuple[Any, ...], tuple[float, int]] = {}
        if sport != "cs2":
            for r in jsonl(Path(rows_dir) / f"{sport}_superbet_settled.jsonl"):
                _s, d, sb = r["game"].split(":")
                k = (
                    d,
                    sb,
                    int(r["market_id"] or 0),
                    int(r["period"] or 0),
                    str(r["subject"] or ""),
                    r["line"],
                    r["side"],
                )
                team[k] = (float(r["p"]), int(r["y"]))
        groups: dict[str, list[tuple[float, float, int, int]]] = defaultdict(list)
        all_days = sorted(
            p.name
            for p in (sport_dir(sport, "x").parent).iterdir()
            if p.is_dir() and p.name[:2] == "20" and p.name <= b
        )
        for day in all_days:
            sp = sport_dir(sport, day) / "settled.json"
            if not sp.exists():
                continue
            doc = load(sp)
            for sb, ev in (doc.get("events") or {}).items():
                graded = ev.get("graded") or []
                if isinstance(graded, str):
                    continue
                gid = hash((day, sb)) & 0x7FFFFFFF
                for g in graded:
                    if (
                        g.get("outcome") not in ("WIN", "LOSS")
                        or g.get("fair_p") is None
                    ):
                        continue
                    y = 1 if g["outcome"] == "WIN" else 0
                    fam = g["family"]
                    if sport == "cs2" or fam.startswith("player"):
                        if g.get("model_p") is None:
                            continue
                        p = float(g["model_p"])
                    else:
                        k = (
                            day,
                            str(sb),
                            int(g.get("market_id") or 0),
                            int(g.get("period") or 0),
                            str(g.get("subject") or ""),
                            g.get("line"),
                            g["side"],
                        )
                        hit = team.get(k)
                        if hit is None:
                            continue
                        p = hit[0]
                    groups[fam].append((p, float(g["fair_p"]), y, gid))
                    groups[
                        "ALL_player" if fam.startswith("player") else "ALL_team"
                    ].append((p, float(g["fair_p"]), y, gid))
        for fam, rows in sorted(groups.items()):
            arr = np.array(rows)
            if len(arr) < 200:
                continue
            res[f"{sport}|{fam}"] = brier_compare(
                arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
            )
            res[f"{sport}|{fam}"]["days"] = (
                [all_days[0], all_days[-1]] if all_days else []
            )
    return res


# --- cache -------------------------------------------------------------------


def window_event_ids(a: str, b: str) -> dict[str, set[int]]:
    ids: dict[str, set[int]] = defaultdict(set)
    for day in days(a, b):
        for f in load(RUNS / day / "02_fixtures.json"):
            if f["sport"] == "football":
                ids["football"].add(int(f["sofascore_event_id"]))
        for sport in SPORTS:
            sp = sport_dir(sport, day) / "settled.json"
            if not sp.exists():
                continue
            for ev in (load(sp).get("events") or {}).values():
                try:
                    ids[sport].add(int(ev["sofascore_event_id"]))
                except (KeyError, TypeError, ValueError):
                    pass
    return ids


def ut_of(event: dict[str, Any]) -> int | None:
    t = event.get("tournament") or {}
    u = t.get("uniqueTournament") or {}
    v = u.get("id") or t.get("id")
    return int(v) if v is not None else None


def cache(a: str, b: str, db_path: str) -> dict[str, Any]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    ids = window_event_ids(a, b)
    end = int(datetime.fromisoformat(b + "T00:00:00+00:00").timestamp()) + 86400
    start = end - 365 * 86400
    res: dict[str, Any] = {}
    for sport in ("football", "hockey", "basketball", "volleyball", "cs2"):
        comps: Counter[int] = Counter()
        names: dict[int, str] = {}
        flags: dict[int, Any] = {}
        if sport == "cs2":
            for (eid,) in [(i,) for i in ids[sport]]:
                row = con.execute(
                    "select unique_tournament_id, tournament from cs2_series "
                    "where sofascore_event_id=?",
                    (eid,),
                ).fetchone()
                if row and row[0] is not None:
                    comps[int(row[0])] += 1
                    names[int(row[0])] = str(row[1])
        else:
            for eid in ids[sport]:
                row = con.execute(
                    "select event_json from sofa_listed_event where event_id=?", (eid,)
                ).fetchone()
                if row is None:
                    row = con.execute(
                        "select detail_json from sofa_event_detail where "
                        "sofascore_event_id=?",
                        (eid,),
                    ).fetchone()
                    if row is None:
                        continue
                    ev = json.loads(row[0])
                    ev = ev.get("event", ev)
                else:
                    ev = json.loads(row[0])
                ut = ut_of(ev)
                if ut is None:
                    continue
                comps[ut] += 1
                u = (ev.get("tournament") or {}).get("uniqueTournament") or {}
                names[ut] = str(
                    u.get("name") or (ev.get("tournament") or {}).get("name")
                )
                cat = ((ev.get("tournament") or {}).get("category") or {}).get("name")
                flags[ut] = {
                    "player_stats_flag": u.get("hasEventPlayerStatistics"),
                    "box_flag": u.get("hasBoxScore"),
                    "category": cat,
                    "user_count": u.get("userCount"),
                }
        res[sport] = {
            "window_events": len(ids[sport]),
            "window_events_with_comp": sum(comps.values()),
            "competitions": len(comps),
            "per_comp": {},
        }
        if sport == "cs2":
            q = (
                "select s.sofascore_event_id, s.start_ts, s.unique_tournament_id, "
                "count(m.game_id), sum(m.has_complete_stats), sum(m.has_player_rows), "
                "sum(m.home_rounds is not null) from cs2_series s left join cs2_map m "
                "on m.sofascore_event_id = s.sofascore_event_id "
                "where s.start_ts between ? and ? and s.status_type='finished' "
                "group by s.sofascore_event_id"
            )
            per: dict[int, Counter[str]] = defaultdict(Counter)
            month: dict[str, Counter[str]] = defaultdict(Counter)
            for _eid, ts, ut, maps, full, players, rounds in con.execute(
                q, (start, end)
            ):
                if ut not in comps:
                    continue
                c = per[int(ut)]
                c["finished"] += 1
                c["with_maps"] += 1 if maps else 0
                c["all_maps_stats"] += 1 if maps and full == maps else 0
                c["all_maps_players"] += 1 if maps and players == maps else 0
                c["rounds"] += 1 if rounds else 0
                mo = datetime.fromtimestamp(ts, UTC).strftime("%Y-%m")
                month[mo]["finished"] += 1
                month[mo]["all_maps_players"] += 1 if maps and players == maps else 0
            res[sport]["per_comp"] = {
                str(k): {"name": names.get(k), "window_events": comps[k], **v}
                for k, v in per.items()
            }
            res[sport]["by_month"] = {k: dict(v) for k, v in sorted(month.items())}
            continue
        slug = SLUG[sport]
        per = defaultdict(Counter)
        month = defaultdict(Counter)
        comp_list = ",".join(str(int(k)) for k in comps) or "-1"
        q = (
            "select event_id, start_ts, ut, st, p1, p2 from "
            "(select event_id, start_ts, "
            "json_extract(event_json, '$.tournament.uniqueTournament.id') as ut, "
            "json_extract(event_json, '$.status.type') as st, "
            "json_extract(event_json, '$.homeScore.period1') as p1, "
            "json_extract(event_json, '$.homeScore.period2') as p2 "
            "from sofa_listed_event where sport=? and start_ts between ? and ?) "
            f"where ut in ({comp_list}) and st='finished'"
        )
        candidates: list[tuple[int, int, int, bool]] = [
            (int(eid), int(ts), int(ut), p1 is not None and p2 is not None)
            for eid, ts, ut, _st, p1, p2 in con.execute(q, (slug, start, end))
        ]
        for eid, ts, ut, periods in candidates:
            row = con.execute(
                "select statistics_json is not null "
                "and statistics_json not in ('', 'null', '{}'), "
                "lineups_json is not null and lineups_json not in ('', 'null', '{}'), "
                "case when lineups_json is null then 0 else "
                'instr(lineups_json, \'"statistics": {"\') > 0 end '
                "from sofa_event_stats where sofascore_event_id=?",
                (eid,),
            ).fetchone()
            stats, lineups, pstats = (
                (bool(row[0]), bool(row[1]), bool(row[2]))
                if row
                else (False, False, False)
            )
            for c in (
                per[ut],
                month[datetime.fromtimestamp(ts, UTC).strftime("%Y-%m")],
            ):
                c["finished"] += 1
                c["periods"] += periods
                c["fetched"] += row is not None
                c["team_stats"] += stats
                c["lineups"] += lineups
                c["player_stats"] += pstats
        res[sport]["per_comp"] = {
            str(k): {
                "name": names.get(k),
                "window_events": comps[k],
                **flags.get(k, {}),
                **v,
            }
            for k, v in per.items()
        }
        res[sport]["by_month"] = {k: dict(v) for k, v in sorted(month.items())}
    return res


def jsonable(o: Any) -> Any:
    if isinstance(o, Counter | dict):
        return {
            ("|".join(map(str, k)) if isinstance(k, tuple) else str(k)): jsonable(v)
            for k, v in o.items()
        }
    if isinstance(o, list | tuple | set):
        return [jsonable(v) for v in o]
    return o


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("section", choices=("artifacts", "yardstick", "cache", "details"))
    ap.add_argument("--from", dest="date_from", required=True)
    ap.add_argument("--to", dest="date_to", required=True)
    ap.add_argument("--db-path", default="data/sofa.db")
    ap.add_argument("--rows-dir", default="data/line_evidence/rows_before_2026-11-05")
    ap.add_argument("--json-out", required=True)
    args = ap.parse_args()
    if args.section == "artifacts":
        res = artifacts(args.date_from, args.date_to)
    elif args.section == "yardstick":
        res = yardstick(args.date_from, args.date_to, args.db_path, args.rows_dir)
    elif args.section == "details":
        res = details(args.date_from, args.date_to)
    else:
        res = cache(args.date_from, args.date_to, args.db_path)
    Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json_out).write_text(
        json.dumps(jsonable(res), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
