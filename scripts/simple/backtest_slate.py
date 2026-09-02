#!/usr/bin/env python3
"""Replay a finished betting day and settle every row against what happened.

    # settle the coupon file this pipeline actually shipped that day
    python3 scripts/simple/backtest_slate.py --date 2026-09-01 --recorded

    # rebuild the day from its frozen dossier with today's code, and settle that
    python3 scripts/simple/backtest_slate.py --date 2026-09-01 --rebuilt

    # both, side by side -- what the change is worth
    python3 scripts/simple/backtest_slate.py --date 2026-08-31 --date 2026-09-01

Why this exists. ``p_low`` claims to be a *lower bound* on a row's win
probability and nothing checked that claim. The 2026-09-01 losses were found by
reading eight slip screenshots by hand; eight is the whole ledger, and six
losses out of seven is consistent with both "the sheet is broken" and "an
unlucky Tuesday". Every fixture in ``runs/`` has since been played, so the same
question can be asked over hundreds of rows with certainty instead.

**RECORDED is the honest before.** It is the artifact the pipeline wrote that
day -- not a reconstruction, not today's code with a flag flipped -- so nothing
about the comparison depends on faithfully un-fixing the fixes. REBUILT is
today's code over the same frozen dossier, same offer, same analyst vetoes.

Actuals come from bzzoiro (``/events/{id}/stats/`` for counts, ``/events/{id}/``
for the score) and are cached to disk, so re-running after a code change costs
no requests at all. Football only: the tennis markets on these slates settle
from a different endpoint and are reported as uncovered rather than guessed.

Exit codes: 0 = report written, 2 = bad input or nothing to settle.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from bet.api_clients import get_client  # noqa: E402
from bet.api_clients.rate_limiter import RateLimiter  # noqa: E402
from bet.simple_stats.analyze import analyze_dossiers  # noqa: E402
from bet.simple_stats.artifact_io import write_json_atomic  # noqa: E402
from bet.simple_stats.contracts import (  # noqa: E402
    EventDossierListV1,
    EventListV1,
    MarketContextV1,
    StatsSheetV1,
    SuperbetOfferV1,
    TipsterSignalV1,
)
from bet.simple_stats.coupons import (  # noqa: E402
    AnalystVeto,
    CouponSet,
    build_coupons,
    reset_competition_tier_cache,
)
from bet.simple_stats.market_context import attach_market_context_column  # noqa: E402
from bet.simple_stats.offered_lines import OfferedLines  # noqa: E402
from bet.simple_stats.providers import _bzzoiro_match_stats  # noqa: E402
from bet.simple_stats.settle import Outcome, hit_rate, profit, settle_row  # noqa: E402
from bet.simple_stats.superbet_offer import attach_superbet_column  # noqa: E402
from bet.simple_stats.tipster_signal import attach_tipster_column  # noqa: E402

DEFAULT_CACHE = ROOT / "runs" / "_backtest_actuals.json"


# --------------------------------------------------------------- actuals


def _score_actuals(event_payload: dict) -> dict[str, float]:
    """Goals from the fixture row, which ``/stats/`` does not carry.

    Same split the history path already applies (``providers`` bzzoiro block):
    a full-time score gives the total and each side's own, a half-time score
    gives the 1H/2H splits. Absent, nothing is invented.
    """
    out: dict[str, float] = {}
    score = event_payload.get("score") or {}
    home, away = score.get("home"), score.get("away")
    if home is None or away is None:
        return out
    home, away = float(home), float(away)
    out["goals_total"] = home + away
    out["__home_goals"] = home
    out["__away_goals"] = away
    home_ht, away_ht = score.get("home_ht"), score.get("away_ht")
    if home_ht is not None and away_ht is not None:
        home_ht, away_ht = float(home_ht), float(away_ht)
        out["goals_1h_total"] = home_ht + away_ht
        out["goals_2h_total"] = (home - home_ht) + (away - away_ht)
        out["__home_goals_1h"] = home_ht
        out["__away_goals_1h"] = away_ht
    return out


def _fetch_one(client, bzz_id: str) -> tuple[dict, list[str]]:
    """``({"home":…, "away":…, "total":…}, gaps)`` for one finished fixture."""
    gaps: list[str] = []
    try:
        stats, gap = _bzzoiro_match_stats(client, bzz_id)
    except Exception as exc:  # noqa: BLE001 - one fixture must not abort a slate
        return {}, [f"{bzz_id}: stats error: {exc}"]
    if gap:
        gaps.append(f"{bzz_id}: {gap}")
    actuals = {
        "home": dict(stats.get("home") or {}),
        "away": dict(stats.get("away") or {}),
        "total": dict(stats.get("total") or {}),
    }
    try:
        event = client.get_event_result(bzz_id)
        payload = event.value if getattr(event, "value", None) else {}
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"{bzz_id}: event error: {exc}")
        payload = {}
    goals = _score_actuals(payload if isinstance(payload, dict) else {})
    for name, value in goals.items():
        if name.startswith("__"):
            continue
        actuals["total"][name] = value
    if "__home_goals" in goals:
        actuals["home"]["goals_for"] = goals["__home_goals"]
        actuals["away"]["goals_for"] = goals["__away_goals"]
        actuals["home"]["goals_against"] = goals["__away_goals"]
        actuals["away"]["goals_against"] = goals["__home_goals"]
    if "__home_goals_1h" in goals:
        actuals["home"]["goals_1h_for"] = goals["__home_goals_1h"]
        actuals["away"]["goals_1h_for"] = goals["__away_goals_1h"]
        actuals["home"]["goals_2h_for"] = goals["__home_goals"] - goals["__home_goals_1h"]
        actuals["away"]["goals_2h_for"] = goals["__away_goals"] - goals["__away_goals_1h"]
    if not any(actuals.values()):
        gaps.append(f"{bzz_id}: no statistics and no score")
        return {}, gaps
    return actuals, gaps


def fetch_actuals(
    events: EventListV1, cache: dict, *, workers: int = 8
) -> tuple[dict[str, dict], list[str]]:
    """``{event_id: actuals}`` for every football fixture with a bzzoiro id.

    Only bzzoiro is used, deliberately. It is the one provider that keeps the
    two sides apart, which is what a ``*_for`` row settles against; a total
    from another provider would settle half the rows and silently leave the
    per-team ones unsettled, which is the family that lost.
    """
    gaps: list[str] = []
    todo: list[tuple[str, str]] = []
    resolved: dict[str, dict] = {}
    for event in events.events:
        if event.sport != "football":
            continue
        bzz_id = (event.source_ids or {}).get("bzzoiro")
        if not bzz_id:
            gaps.append(f"{event.home_team} v {event.away_team}: no bzzoiro id")
            continue
        cached = cache.get(str(bzz_id))
        if cached is not None:
            resolved[event.event_id] = cached
            continue
        todo.append((event.event_id, str(bzz_id)))
    if todo:
        limiter = RateLimiter()
        client = get_client("bzzoiro", rate_limiter=limiter)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_fetch_one, client, bzz_id): (event_id, bzz_id)
                for event_id, bzz_id in todo
            }
            for future in as_completed(futures):
                event_id, bzz_id = futures[future]
                actuals, one_gaps = future.result()
                gaps.extend(one_gaps)
                if actuals:
                    cache[str(bzz_id)] = actuals
                    resolved[event_id] = actuals
    return resolved, gaps


# --------------------------------------------------------------- coupons


def _run_paths(date: str) -> dict[str, Path]:
    base = ROOT / "runs" / date
    return {
        "dossiers": base / f"{date}_event_dossiers.json",
        "events": base / f"{date}_event_list.json",
        "coupons": base / f"{date}_coupons.json",
        "offer": base / f"{date}_superbet_offer.json",
        "vetoes": base / f"{date}_analyst_vetoes.json",
        "market": base / f"{date}_market_context.json",
        "tipsters": base / f"{date}_tipster_signal.json",
        "sheet": base / f"{date}_event_dossiers_stats_sheet.json",
    }


def load_recorded(date: str) -> CouponSet | None:
    path = _run_paths(date)["coupons"]
    if not path.exists():
        return None
    return CouponSet.model_validate_json(path.read_text(encoding="utf-8"))


def rebuild(date: str) -> StatsSheetV1 | None:
    """Today's ANALYZE over the frozen artifacts of ``date``.

    ``not_before=None`` on purpose: every fixture is in the past, and the live
    cutoff would empty the file. That is the one argument that must differ from
    a live run, and it is the reason ``build_coupons`` takes the cutoff as a
    parameter instead of calling ``now()`` -- see its docstring.
    """
    paths = _run_paths(date)
    if not paths["dossiers"].exists() or not paths["events"].exists():
        return None
    dossier_list = EventDossierListV1.model_validate_json(
        paths["dossiers"].read_text(encoding="utf-8")
    )
    events = EventListV1.model_validate_json(paths["events"].read_text(encoding="utf-8"))
    offer = None
    if paths["offer"].exists():
        offer = SuperbetOfferV1.model_validate_json(
            paths["offer"].read_text(encoding="utf-8")
        )
    offered = OfferedLines.from_offer(
        offer,
        player_names_by_event={
            dossier.event_id: [
                observation.player_name
                for observation in dossier.player_metrics
                if observation.player_name
            ]
            for dossier in dossier_list.dossiers
        },
    )
    competitions = {e.event_id: e.competition for e in events.events if e.competition}
    sheet = analyze_dossiers(dossier_list, offered, competitions=competitions)
    # All three optional columns, in run_analyze.py's own order. Attaching the
    # Superbet one and skipping the other two is not a smaller version of the
    # real run: ``coupons._has_market_reference`` reads ``market_signal``, and
    # it decides which of the file's two sections a row lands in -- so a
    # rebuild without it selects a different fifteen and the comparison would
    # be measuring the missing artifact.
    if paths["market"].exists():
        sheet = attach_market_context_column(
            sheet,
            MarketContextV1.model_validate_json(
                paths["market"].read_text(encoding="utf-8")
            ),
        )
    if paths["tipsters"].exists():
        sheet = attach_tipster_column(
            sheet,
            TipsterSignalV1.model_validate_json(
                paths["tipsters"].read_text(encoding="utf-8")
            ),
        )
    if offer is not None:
        sheet = attach_superbet_column(sheet, offer)
    return sheet


def _vetoes_for(date: str) -> list[AnalystVeto] | None:
    path = _run_paths(date)["vetoes"]
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw.get("vetoes", raw) if isinstance(raw, dict) else raw
    return [AnalystVeto.model_validate(v) for v in rows]


def _offer_for(date: str) -> SuperbetOfferV1 | None:
    path = _run_paths(date)["offer"]
    if not path.exists():
        return None
    return SuperbetOfferV1.model_validate_json(path.read_text(encoding="utf-8"))


def coupons_from_sheet(
    date: str, sheet: StatsSheetV1, events: EventListV1, *, max_singles: int = 15
) -> CouponSet:
    """``build_coupons`` over a sheet, with the day's own offer and vetoes.

    ``max_singles`` is raised for the calibration pass: with a budget of 15 the
    file is a *ranking* decision and 15 rows is far too few to say anything
    about calibration, while the same selection at 400 emits the whole
    candidate set -- every row that clears the tier, the floor, the trivial-
    under demotion, the vetoes and the one-per-market-per-fixture rule. Same
    code path either way, which is the point: the candidate set is not
    reimplemented here.
    """
    reset_competition_tier_cache()
    return build_coupons(
        sheet, events,
        superbet_offer=_offer_for(date),
        vetoes=_vetoes_for(date),
        max_singles=max_singles,
        not_before=None,
    )


def rebuilt_coupons(date: str, *, max_singles: int = 15) -> CouponSet | None:
    sheet = rebuild(date)
    if sheet is None:
        return None
    paths = _run_paths(date)
    events = EventListV1.model_validate_json(paths["events"].read_text(encoding="utf-8"))
    return coupons_from_sheet(date, sheet, events, max_singles=max_singles)


def recorded_sheet_coupons(date: str, *, max_singles: int = 15) -> CouponSet | None:
    """Today's selection over the sheet the pipeline wrote that day.

    This is the controlled half of the experiment: selection held constant,
    only the sheet's arithmetic differs. Comparing it against
    ``rebuilt_coupons`` isolates what shrinkage, the venue prior and the count
    model are worth, with the tier rule and every gate identical on both sides.
    """
    paths = _run_paths(date)
    if not paths["sheet"].exists() or not paths["events"].exists():
        return None
    sheet = StatsSheetV1.model_validate_json(paths["sheet"].read_text(encoding="utf-8"))
    events = EventListV1.model_validate_json(paths["events"].read_text(encoding="utf-8"))
    return coupons_from_sheet(date, sheet, events, max_singles=max_singles)


# --------------------------------------------------------------- settling


def _team_subject(single) -> str | None:
    """The single's ``subject`` when it names a *team*, else None.

    ``CouponSingle.subject`` is ``player_name or team_name`` and the artifact
    does not say which (see ``coupons._subject``), so it is disambiguated here
    from the market family -- ``*_for`` is a team's own contribution,
    ``player_*`` is a person, everything else is a match total and names
    nobody. Reading it the other way round would settle a player's shots
    against his team's.
    """
    if single.market.startswith("player_"):
        return None
    if single.market.endswith("_for"):
        return single.subject
    return None


def settle_singles(
    coupons: CouponSet, events: EventListV1, actuals_by_event: dict[str, dict]
) -> list[dict]:
    """One record per single: what it claimed, what happened, at what price."""
    by_id = {e.event_id: e for e in events.events}
    out: list[dict] = []
    for single in coupons.singles:
        event = by_id.get(single.event_id)
        actuals = actuals_by_event.get(single.event_id)
        if event is None or actuals is None:
            out.append(
                {
                    "market": single.market, "line": single.line,
                    "direction": single.direction, "subject": single.subject,
                    "p_low": single.p_low, "tier": single.tier,
                    "price": single.superbet_price, "outcome": "NO_DATA",
                    "actual": None, "reason": "no actuals for this fixture",
                }
            )
            continue
        outcome, actual = settle_row(
            market=single.market, line=single.line, direction=single.direction,
            actuals=actuals, team_name=_team_subject(single),
            home_team=event.home_team, away_team=event.away_team,
        )
        out.append(
            {
                "match": f"{event.home_team} v {event.away_team}",
                "market": single.market, "line": single.line,
                "direction": single.direction, "subject": single.subject,
                "p_low": single.p_low, "tier": single.tier,
                "price": single.superbet_price,
                "verdict": single.superbet_verdict,
                "outcome": outcome, "actual": actual,
            }
        )
    return out


def summarise(label: str, records: list[dict]) -> dict:
    outcomes: list[Outcome] = [r["outcome"] for r in records]
    prices = [r.get("price") for r in records]
    won, decided, rate = hit_rate(outcomes)
    staked, returned, priced = profit(outcomes, prices)
    claimed = [r["p_low"] for r in records if r["outcome"] in ("WON", "LOST")]
    return {
        "label": label,
        "emitted": len(records),
        "counts": dict(Counter(outcomes)),
        "won": won,
        "decided": decided,
        "hit_rate": rate,
        "claimed_p_low": statistics.fmean(claimed) if claimed else None,
        "priced": priced,
        "staked": round(staked, 2),
        "returned": round(returned, 2),
        "roi": round(returned / staked - 1.0, 4) if staked else None,
    }


_CALIBRATION_BUCKETS = ((0.50, 0.55), (0.55, 0.60), (0.60, 0.70), (0.70, 0.85), (0.85, 1.01))


def calibration(records: list[dict]) -> list[dict]:
    """Claimed ``p_low`` against what actually happened, in buckets.

    The one measurement that says whether the sheet's central claim holds.
    ``p_low`` is a *lower* bound, so a well-behaved row wins **at least** as
    often as it claimed: realised >= claimed in every bucket is the pass
    condition, and realised far above claimed is conservatism rather than a
    fault.

    Bucketed rather than fitted because the claim is an inequality, not a
    calibration curve -- a single correlation would hide the case that matters,
    which is one bucket sitting under its own floor.
    """
    out = []
    for low, high in _CALIBRATION_BUCKETS:
        inside = [
            r for r in records
            if low <= r["p_low"] < high and r["outcome"] in ("WON", "LOST")
        ]
        if not inside:
            continue
        won = sum(1 for r in inside if r["outcome"] == "WON")
        out.append({
            "bucket": f"{low:.2f}-{high:.2f}",
            "n": len(inside),
            "claimed": statistics.fmean(r["p_low"] for r in inside),
            "realised": won / len(inside),
            "won": won,
        })
    return out


def _format_calibration(label: str, buckets: list[dict]) -> str:
    lines = [f"  {label}"]
    for b in buckets:
        gap = b["realised"] - b["claimed"]
        mark = "ok " if gap >= 0 else "OVERSTATED"
        lines.append(
            f"    p_low {b['bucket']}  n={b['n']:4d}  claimed {b['claimed']:5.3f}  "
            f"realised {b['realised']:5.3f}  ({gap:+.3f}) {mark}"
        )
    return "\n".join(lines)


def _format(summary: dict) -> str:
    rate = "  n/a" if summary["hit_rate"] is None else f"{summary['hit_rate']:5.1%}"
    claimed = (
        "  n/a" if summary["claimed_p_low"] is None else f"{summary['claimed_p_low']:5.3f}"
    )
    roi = "    n/a" if summary["roi"] is None else f"{summary['roi']:+7.1%}"
    return (
        f"{summary['label']:<28} emitted {summary['emitted']:3d}  "
        f"settled {summary['decided']:3d}  won {summary['won']:3d}  "
        f"hit {rate}  claimed {claimed}  staked {summary['staked']:6.1f}  ROI {roi}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--date", action="append", required=True, help="Run date; repeatable")
    parser.add_argument("--recorded", action="store_true", help="Only settle the recorded coupon file")
    parser.add_argument("--rebuilt", action="store_true", help="Only settle today's rebuild")
    parser.add_argument(
        "--recorded-sheet", action="store_true", dest="recorded_sheet",
        help="Settle today's *selection* over the sheet that day's code wrote. "
             "The controlled half of the experiment: paired with --rebuilt it "
             "isolates the sheet's arithmetic with every gate held constant.",
    )
    parser.add_argument(
        "--max-singles", type=int, default=15,
        help="Budget for the rebuilt/recorded-sheet passes. 15 is the live "
             "file; raise it (400) to emit the whole candidate set, which is "
             "what a calibration measurement needs.",
    )
    parser.add_argument(
        "--calibrate", action="store_true",
        help="Report claimed p_low against realised hit rate in buckets.",
    )
    parser.add_argument("--cache", default=str(DEFAULT_CACHE), help="Actuals cache (JSON)")
    parser.add_argument("--output", default=None, help="Write the full record set here")
    parser.add_argument("--show-rows", action="store_true", help="Print every settled row")
    args = parser.parse_args()

    both = not (args.recorded or args.rebuilt)
    cache_path = Path(args.cache)
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    all_records: dict[str, list[dict]] = {}
    per_slate: list[dict] = []
    all_gaps: list[str] = []
    for date in args.date:
        paths = _run_paths(date)
        if not paths["events"].exists():
            print(f"{date}: no event list, skipped", file=sys.stderr)
            continue
        events = EventListV1.model_validate_json(paths["events"].read_text(encoding="utf-8"))
        actuals, gaps = fetch_actuals(events, cache)
        all_gaps.extend(gaps)
        print(f"{date}: actuals for {len(actuals)} of {len(events.events)} fixtures")
        budget = args.max_singles
        loaders = {
            "recorded": lambda d: load_recorded(d),
            "rebuilt": lambda d: rebuilt_coupons(d, max_singles=budget),
            "recorded_sheet": lambda d: recorded_sheet_coupons(d, max_singles=budget),
        }
        wanted = [w for w in ("recorded", "rebuilt", "recorded_sheet")
                  if (both and w != "recorded_sheet") or getattr(args, w, False)]
        for which in wanted:
            coupons = loaders[which](date)
            if coupons is None:
                print(f"  {which}: unavailable", file=sys.stderr)
                continue
            records = settle_singles(coupons, events, actuals)
            for record in records:
                record["date"] = date
            all_records.setdefault(which, []).extend(records)
            summary = summarise(f"{date} {which}", records)
            per_slate.append(summary)
            print("  " + _format(summary))
            if args.show_rows:
                for r in sorted(records, key=lambda x: -x["p_low"]):
                    price = "   --" if r.get("price") is None else f"{r['price']:5.2f}"
                    actual = " --" if r.get("actual") is None else f"{r['actual']:5.1f}"
                    print(
                        f"      {r['outcome']:<7} p_low {r['p_low']:.3f} @{price} "
                        f"{r['market']} {r['direction']} {r['line']} "
                        f"{r.get('subject') or ''} -> {actual}  ({r.get('match','')})"
                    )

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(cache_path, cache)

    print("\npooled")
    pooled = []
    for which in ("recorded", "recorded_sheet", "rebuilt"):
        if all_records.get(which):
            summary = summarise(f"ALL {which}", all_records[which])
            pooled.append(summary)
            print("  " + _format(summary))
    if args.calibrate:
        print("\ncalibration -- p_low is a lower bound, so realised should be >= claimed")
        for which in ("recorded", "recorded_sheet", "rebuilt"):
            if all_records.get(which):
                print(_format_calibration(f"ALL {which}", calibration(all_records[which])))

    if all_gaps:
        print(f"\ncoverage gaps: {len(all_gaps)} (first 5)")
        for gap in all_gaps[:5]:
            print(f"  {gap}")

    if args.output:
        write_json_atomic(
            Path(args.output),
            {"per_slate": per_slate, "pooled": pooled, "records": all_records,
             "gaps": all_gaps},
        )
    if not any(all_records.values()):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
