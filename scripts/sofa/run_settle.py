"""SETTLE — grade a finished day's sheet against Sofascore, with the price.

The stage that was missing (F53). The pipeline ran BOARD -> RESOLVE -> OFFER ->
SAMPLES -> SHEET -> COUPON and then forgot the day: nothing ever compared a
priced row to what happened. `sofa_settled_row` had exactly one writer,
`run_backfill`, which replays cached events and therefore carries
``market_p = NULL`` by construction (PLAN §A9).

`fit_k_price` selects on ``market_p IS NOT NULL``. So its input set was empty,
had always been empty, and could never stop being empty — which is why every
row of every sheet carried ``UNFITTED_CONSTANTS: K_PRICE``. The same held for
MAX_LADDER_SIGMA, whose column carries the comment "live settlement can" beside
a live settlement that did not exist.

This closes the loop. Run it for a past date, once the day's matches are over:

    python scripts/sofa/run_pipeline.py --date 2026-09-18 --only SETTLE

or the stage on its own, with the repository root on the path:

    PYTHONPATH=src:. python scripts/sofa/run_settle.py --date 2026-09-18

It costs three requests per finished fixture and caches all of them
permanently, so a second run over the same day is free.
"""

import argparse
import json
import math
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from bet.sofa.cache import SofaCache
from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import GapReason
from bet.sofa.db import get_connection, migrate
from bet.sofa.errors import CircuitOpenError, ProviderError
from bet.sofa.market_mapper import DERIVED_BASE_TO_SIDE_METRIC, derived_base, is_derived
from bet.sofa.metrics import extract_flat_statistics, extract_metric
from bet.sofa.names import normalize_name
from bet.sofa.resolve import NAME_MATCH_THRESHOLD, name_score
from bet.sofa.settle import (
    SettledRow,
    insert_settled_rows,
    is_completed_event,
)
from bet.sofa.settle import settle as settle_value
from bet.sofa.stage import set_stage
from bet.sofa.timeutil import now

# /statistics is only fetched for a terminal event, so the cache entry is
# immutable and this status set is what "terminal" means.
_CACHEABLE_STATUS = ("finished", "canceled", "abandoned")


# Subjects the derived-market mapper writes instead of a team name: the side
# of a "who takes more" proposition. They name a side, not a squad, and
# `extract_metric` has no reading for them, so they are refused by name here
# rather than falling through into a fuzzy match against a club.
_DERIVED_SUBJECTS = frozenset({"1", "2", "__draw__"})


def _subject_is_home(subject: str, fixture: dict) -> bool | None:
    """Which side a per-team row is about, or None when it names neither.

    Returning None rather than guessing is the point. `is_home` decides which
    column of a (home, away) statistic the row settles against, so a guess here
    does not degrade the measurement, it inverts it — the settled row would
    then say the wrong team's corners, and be used to fit constants.

    Matched with `name_score`, not `fuzz.ratio`, and for the same reason
    RESOLVE is: Superbet's subject is the bare club and Sofascore's fixture
    name carries the affix. On the 2026-09-18 sheet 738 of 4,492 per-team rows
    scored under 85 on a bare ratio — "verl" against "sc verl" is 72.7 — and a
    strict gate here would have thrown all of them away unsettled.
    """
    if not subject:
        return True  # a total: the flag is unused
    if subject in _DERIVED_SUBJECTS:
        return None
    home = normalize_name(fixture["home_name"])
    away = normalize_name(fixture["away_name"])
    if subject == home:
        return True
    if subject == away:
        return False

    score_home = name_score(subject, home)
    score_away = name_score(subject, away)
    # Both a floor and a margin. The floor keeps a subject that names neither
    # side out; the margin keeps a derby of two similarly named clubs from
    # being decided by a rounding difference.
    if max(score_home, score_away) <= NAME_MATCH_THRESHOLD:
        return None
    if abs(score_home - score_away) < 5.0:
        return None
    return score_home > score_away


def _event_payload(
    client: SofascoreClient, cache: SofaCache, event_id: int
) -> tuple[dict, dict | None, dict | None] | str:
    """(listing event, statistics, incidents), or a string saying why not."""
    detail = client.event(event_id)
    event = (detail or {}).get("event")
    if not event:
        return "NO_EVENT"
    if not is_completed_event(event):
        return "NOT_FINISHED"

    cached = cache.get_event_stats(event_id)
    if cached:
        statistics, incidents, _ = cached
        return event, statistics, incidents

    statistics = client.event_statistics(event_id)
    incidents = client.event_incidents(event_id)
    status_type = event.get("status", {}).get("type", "finished")
    if status_type in _CACHEABLE_STATUS:
        cache.save_event_stats(event_id, statistics, incidents, status_type)
    return event, statistics, incidents


def _settled(
    row: dict,
    run_date: str,
    event_id: int,
    competition_id: int | None,
    value: float,
    outcome: str,
    settled_at: str,
) -> SettledRow:
    return SettledRow(
        run_date=run_date,
        sofascore_event_id=event_id,
        sport=row["sport"],
        competition_id=competition_id,
        market=row["market"],
        subject=row["subject"] or "",
        line=row["line"],
        direction=row["direction"],
        sample_size=row["sample_size"],
        sample_mean=row["sample_mean"],
        sample_sd=row["sample_sd"],
        p_central=row["p_central"],
        p_bar=row["p_bar"],
        market_p=row.get("market_p"),
        actual_value=value,
        outcome=outcome,  # type: ignore[arg-type]
        settled_at=settled_at,
        ladder_sigma=row.get("ladder_sigma"),
        offered_odds=row["offered_odds"],
        verdict=row["verdict"],
    )


def _settle_derived(
    row: dict, sport: str, flat: dict, incidents: dict | None, event: dict
) -> tuple[float, str] | str:
    """Grade a both-teams / most / handicap row, or say why it cannot be.

    These are functions of the same two per-side counts the marginal path
    already reads, so nothing new is fetched and nothing is modelled — the
    outcome is arithmetic on (home, away).

    Without this they are silently unsettleable, which is not a small corner:
    on 2026-09-18 five of the coupon's 33 singles were derived rows, so 15% of
    what was actually staked could never be measured, and none of it could
    reach the fitter.

    Returns ``(actual_value, outcome)`` where ``actual_value`` is the quantity
    the market is about — min(a, b) for both_over, a - b for a handicap — so a
    settled derived row reads like any other.
    """
    base = derived_base(row["market"])
    if base is None:
        return "NOT_DERIVED"
    side_metric = DERIVED_BASE_TO_SIDE_METRIC.get(base, f"{base}_for")

    home = extract_metric(side_metric, sport, flat, incidents, event, True)
    away = extract_metric(side_metric, sport, flat, incidents, event, False)
    if isinstance(home, GapReason):
        return f"{side_metric}:{home.value}"
    if isinstance(away, GapReason):
        return f"{side_metric}:{away.value}"

    line = row["line"]
    subject = (row["subject"] or "").strip()

    if row["market"].startswith("both_over_"):
        # `probability` reads "powyżej 3.5" on a count as ">= 4"; settlement
        # has to read it the same way or the two disagree at every integer.
        threshold = math.floor(line) + 1
        both = min(home, away) >= threshold
        won = both if row["direction"] == "OVER" else not both
        return float(min(home, away)), ("WIN" if won else "LOSS")

    if row["market"].startswith("most_"):
        if subject == "__draw__":
            won = home == away
        elif subject == "1":
            won = home > away
        elif subject == "2":
            won = away > home
        else:
            return "DERIVED_SUBJECT"
        return float(home - away), ("WIN" if won else "LOSS")

    if row["market"].startswith("handicap_"):
        # The selection's own line already carries the sign, and the side it
        # belongs to wins when its own count beats the opponent's by more than
        # -line. Mirrors `probability`'s two branches exactly.
        side = _handicap_side(subject, row, event)
        if side is None:
            return "DERIVED_SUBJECT"
        margin = (home - away) if side == "home" else (away - home)
        if margin == -line:
            return "PUSH"
        return float(margin), ("WIN" if margin > -line else "LOSS")

    return "NOT_DERIVED"


def _handicap_side(subject: str, row: dict, event: dict) -> str | None:
    if subject == "1":
        return "home"
    if subject == "2":
        return "away"
    home = normalize_name((event.get("homeTeam") or {}).get("name", ""))
    away = normalize_name((event.get("awayTeam") or {}).get("name", ""))
    if not subject or not home or not away:
        return None
    score_home, score_away = name_score(subject, home), name_score(subject, away)
    if max(score_home, score_away) <= NAME_MATCH_THRESHOLD:
        return None
    if abs(score_home - score_away) < 5.0:
        return None
    return "home" if score_home > score_away else "away"


def main() -> int:
    set_stage("SETTLE")
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD", default=now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    config = SofaConfig.from_env()
    migrate(config.db_path)
    client = SofascoreClient(config)
    cache = SofaCache(config)

    run_dir = Path(config.runs_dir) / args.date
    sheet_path = run_dir / "05_sheet.json"
    fixtures_path = run_dir / "02_fixtures.json"
    if not sheet_path.exists() or not fixtures_path.exists():
        print(f"{sheet_path} or {fixtures_path} missing", file=sys.stderr)
        return 2

    with open(sheet_path, encoding="utf-8") as f:
        sheet = json.load(f)
    with open(fixtures_path, encoding="utf-8") as f:
        fixtures = {x["sofascore_event_id"]: x for x in json.load(f)}

    # A row with no price cannot answer the question this stage exists for.
    priced = [r for r in sheet if r.get("offered_odds")]
    by_event: dict[int, list[dict]] = {}
    for row in priced:
        by_event.setdefault(row["sofascore_event_id"], []).append(row)

    settled_at = datetime.now(UTC).isoformat()
    rows: list[SettledRow] = []
    skipped: Counter[str] = Counter()
    events_settled = 0
    breaker_open = False

    # F15, applied here: the insert used to sit after the loop, so any
    # unexpected failure — one malformed payload, a sqlite lock — threw away
    # every row already graded and left the day looking unsettled. A partial
    # settlement is worth exactly as much as it says it is; none is worth
    # nothing, and costs the fetches again.
    inserted = 0
    try:
        for event_id, event_rows in sorted(by_event.items()):
            fixture = fixtures.get(event_id)
            if not fixture:
                skipped["NO_FIXTURE"] += len(event_rows)
                continue
            try:
                payload = _event_payload(client, cache, event_id)
            except CircuitOpenError:
                skipped["PROVIDER_ERROR"] += len(event_rows)
                breaker_open = True
                break
            except ProviderError as exc:
                print(f"PROVIDER_ERROR event={event_id}: {exc}", file=sys.stderr)
                skipped["PROVIDER_ERROR"] += len(event_rows)
                continue
            if isinstance(payload, str):
                skipped[payload] += len(event_rows)
                continue

            event, statistics, incidents = payload
            flat = extract_flat_statistics(statistics) if statistics else {}
            if isinstance(flat, GapReason):
                flat = {}
            competition_id = (
                (event.get("tournament") or {}).get("uniqueTournament") or {}
            ).get("id")
            events_settled += 1

            for row in event_rows:
                if is_derived(row["market"]):
                    graded = _settle_derived(row, row["sport"], flat, incidents, event)
                    if isinstance(graded, str):
                        skipped[graded] += 1
                        continue
                    value, outcome = graded
                    rows.append(
                        _settled(
                            row,
                            args.date,
                            event_id,
                            competition_id,
                            value,
                            outcome,
                            settled_at,
                        )
                    )
                    continue

                is_home = _subject_is_home(row["subject"] or "", fixture)
                if is_home is None:
                    reason = (
                        "DERIVED_SUBJECT"
                        if (row["subject"] or "") in _DERIVED_SUBJECTS
                        else "SUBJECT_NOT_MATCHED"
                    )
                    skipped[reason] += 1
                    continue
                value = extract_metric(
                    row["market"], row["sport"], flat, incidents, event, is_home
                )
                if isinstance(value, GapReason):
                    skipped[f"{row['market']}:{value.value}"] += 1
                    continue
                outcome = settle_value(float(value), row["line"], row["direction"])
                if outcome is None:
                    skipped["PUSH"] += 1
                    continue
                rows.append(
                    _settled(
                        row,
                        args.date,
                        event_id,
                        competition_id,
                        float(value),
                        outcome,
                        settled_at,
                    )
                )

    finally:
        with get_connection(config.db_path) as conn:
            inserted = insert_settled_rows(conn, rows)

    with_price = sum(1 for r in rows if r.market_p is not None)
    won = sum(1 for r in rows if r.outcome == "WIN")
    staked = [r for r in rows if r.verdict == "VALUE" and r.offered_odds]
    value_return = sum(
        (r.offered_odds - 1.0) if r.outcome == "WIN" else -1.0 for r in staked
    )

    metrics = {
        "priced_rows_in_sheet": len(priced),
        "events_settled": events_settled,
        "events_in_sheet": len(by_event),
        "rows_settled": len(rows),
        "rows_inserted": inserted,
        "rows_with_market_price": with_price,
        "win_rate": round(won / len(rows), 4) if rows else None,
        "value_rows_settled": len(staked),
        "value_roi": round(value_return / len(staked), 4) if staked else None,
        "breaker_open": breaker_open,
        "skipped": dict(skipped.most_common(12)),
    }

    if not rows:
        verdict = "FAILED" if by_event and not breaker_open else "PARTIAL"
    elif breaker_open or skipped:
        verdict = "PARTIAL"
    else:
        verdict = "OK"

    out_path = run_dir / "07_settled.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            [
                {
                    **{k: v for k, v in vars(r).items()},
                }
                for r in rows
            ],
            f,
            indent=2,
        )

    print(
        "SOFA_SUMMARY: "
        + json.dumps(
            {
                "stage": "SETTLE",
                "verdict": verdict,
                "metrics": metrics,
                "output_path": str(out_path),
            }
        ),
        flush=True,
    )
    return {"OK": 0, "PARTIAL": 1, "FAILED": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
