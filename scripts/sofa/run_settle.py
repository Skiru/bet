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
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

from bet.sofa.cache import SofaCache
from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import GapReason
from bet.sofa.db import get_connection, migrate
from bet.sofa.errors import CircuitOpenError, ProviderError
from bet.sofa.market_mapper import DERIVED_BASE_TO_SIDE_METRIC, derived_base, is_derived
from bet.sofa.metrics import extract_flat_statistics, extract_metric
from bet.sofa.names import normalize_name
from bet.sofa.players import (
    extract_player_metric,
    is_player_metric,
    match_player,
    squad_statistics,
)
from bet.sofa.resolve import NAME_MATCH_THRESHOLD, name_score
from bet.sofa.samples import fetch_lineups
from bet.sofa.settle import (
    SettledRow,
    insert_settled_rows,
    is_completed_event,
)
from bet.sofa.settle import settle as settle_value
from bet.sofa.stage import current_stage, set_stage
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
    return _named_side(subject, fixture["home_name"], fixture["away_name"])


def _named_side(subject: str, home_name: str, away_name: str) -> bool | None:
    """True for home, False for away, None when the subject names neither.

    The subject is normalised the way the fixture names are. Until 2026-09-25
    it was compared raw, so a Polish exonym never had its alias applied:
    "niemcy" scored 46 against "germany" and 100 once normalised. All 740
    SUBJECT_NOT_MATCHED rows of 2026-09-24 were national teams - every
    per-team market on an international was priced by SHEET (whose
    `determine_side` does normalise) and never graded, which is a biased hole
    in the population every fit reads.
    """
    subject = normalize_name(subject)
    home = normalize_name(home_name)
    away = normalize_name(away_name)
    if not subject or not home or not away:
        return None
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


def unfinished_reason(event: dict[str, Any]) -> str:
    """Why an event that is not a normal finish cannot be settled.

    One label used to cover all of it, so a retirement that will never be
    graded and an interrupted match that resumes tomorrow read the same: on
    2026-09-24 the 859 NOT_FINISHED rows were 305 retirements, 360
    interruptions, 140 not started and 54 abandoned. Only NOT_FINISHED is worth
    re-running SETTLE for.
    """
    status = event.get("status") or {}
    kind = str(status.get("type", "")).lower()
    if kind == "finished":
        # Retirement, walkover, awarded: over, but not a comparable result.
        return "FINISHED_ABNORMALLY"
    if kind in ("canceled", "abandoned", "postponed"):
        return kind.upper()
    return "NOT_FINISHED"


def _event_payload(
    client: SofascoreClient, cache: SofaCache, event_id: int
) -> tuple[dict, dict | None, dict | None] | str:
    """(listing event, statistics, incidents), or a string saying why not."""
    detail = client.event(event_id)
    event = (detail or {}).get("event")
    if not event:
        return "NO_EVENT"
    if not is_completed_event(event):
        return unfinished_reason(event)

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
            # SHEET prices a named side too (derived.resolve_subject): tennis
            # most_games/most_aces with a player, football most_corners with a
            # club. Only "1"/"2" were read here, so 412 named rows of
            # 2026-09-24 went unsettled while their `__draw__` leg settled.
            side = _handicap_side(subject, row, event)
            if side is None:
                return "DERIVED_SUBJECT"
            won = home > away if side == "home" else away > home
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


def _settle_player(
    row: dict[str, Any], squads: dict[bool, dict[str, Any] | None] | None
) -> tuple[float, str] | str:
    """Grade one player row against the fixture's own squad lists (F54).

    Returns (value, outcome) or a skip reason. The player is matched against
    each squad exactly the way SAMPLES matched him against the historical
    ones — same function, same threshold — so a row that could be sampled and
    a row that can be settled are the same set. A different matcher here
    would settle a subject the sheet never priced.

    A player who did not take the pitch is PLAYER_DID_NOT_PLAY, not a zero:
    Superbet voids that bet, so settling it as a loss would invent a result
    the operator never had.
    """
    if not squads:
        return "PLAYER_NO_LINEUPS"
    subject = (row["subject"] or "").strip()
    if not subject:
        return "SUBJECT_NOT_MATCHED"

    for squad in (squads.get(True), squads.get(False)):
        if not squad:
            continue
        matched = match_player(subject, squad)
        if matched is None:
            continue
        value = extract_player_metric(row["market"], squad[matched])
        if value is GapReason.EVENT_NOT_FINISHED:
            return "PLAYER_DID_NOT_PLAY"
        if isinstance(value, GapReason):
            return f"{row['market']}:{value.value}"
        return float(value), settle_value(
            float(value), row["line"], row["direction"]
        )
    return "PLAYER_NOT_MATCHED"


def _handicap_side(subject: str, row: dict, event: dict) -> str | None:
    if subject == "1":
        return "home"
    if subject == "2":
        return "away"
    is_home = _named_side(
        subject,
        (event.get("homeTeam") or {}).get("name", ""),
        (event.get("awayTeam") or {}).get("name", ""),
    )
    if is_home is None:
        return None
    return "home" if is_home else "away"


# (listing event, statistics, incidents) - what `_event_payload` returns when
# it could read the event at all.
EventPayload = tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]


class EventFetch(NamedTuple):
    """One event's fetch outcome, separated from grading it.

    Grading is pure arithmetic over a payload; fetching is three bridge
    requests. Keeping them in one loop is what made SETTLE serial, so the two
    phases are now distinct types rather than two halves of one body.

    Exactly one of ``payload`` and ``reason`` is set. ``circuit_open`` is not
    a reason of its own: it means the breaker tripped, which ends the stage,
    where a plain ``PROVIDER_ERROR`` skips one event and carries on.
    """

    event_id: int
    payload: EventPayload | None = None
    reason: str | None = None
    circuit_open: bool = False
    error: str | None = None


def _fetch_one(
    event_id: int, client: SofascoreClient, cache: SofaCache, stage: str
) -> EventFetch:
    # `stage` is a ContextVar and a fresh thread starts from the default, so
    # without this every request a worker makes would be billed to stage
    # "CLIENT" and the per-stage cost accounting would stop working silently.
    set_stage(stage)
    try:
        payload = _event_payload(client, cache, event_id)
    except CircuitOpenError:
        return EventFetch(event_id, reason="PROVIDER_ERROR", circuit_open=True)
    except ProviderError as exc:
        return EventFetch(event_id, reason="PROVIDER_ERROR", error=str(exc))
    if isinstance(payload, str):
        return EventFetch(event_id, reason=payload)
    return EventFetch(event_id, payload=payload)


def fetch_events_concurrently(
    event_ids: list[int],
    client: SofascoreClient,
    cache: SofaCache,
    config: SofaConfig,
) -> Iterator[EventFetch]:
    """One EventFetch per event, in the input's order, yielded as it lands.

    Why a pool: the browser bridge serves K tabs at once - the queue in
    `bridge_server.claim()` is not bound to a tab - and each tab paces itself
    at MIN_INTERVAL_MS. A serial caller therefore has at most one job in
    flight, so every tab goes idle between jobs and roughly half the requests
    pay a full /pull poll cycle (20 s then; 1 s since 663e7102) to be claimed again.
    Measured on
    2026-09-22: SETTLE ran at 0.094 req/s with p50 latency 20,020 ms - the
    poll window, not the network - against a bridge measured at 8.64 req/s,
    and the bridge reported in_flight 1, pending 0 for all 272 requests with
    zero non-200s. Nothing was being refused; the work never queued deep
    enough to keep one tab busy.

    Order is part of the contract, not a nicety: 07_settled.json is read by a
    human and diffed between runs, so the artifact must not depend on which
    worker finished first. `ThreadPoolExecutor.map` yields in submission
    order, which gives us that for free.

    All events are submitted, including the ones after a breaker trip. That
    costs nothing: once the breaker is open `SofascoreClient` raises
    CircuitOpenError without a request, and the caller still stops at the
    first `circuit_open` it reaches in order, exactly as the serial loop did.

    A generator, not a list, and that is the F15 guarantee rather than a
    style choice: the caller grades each event as it lands and inserts what
    it has in a `finally`. Materialising the whole fetch first would mean an
    unexpected exception anywhere in it threw away every row already graded
    and left the day looking unsettled rather than partly settled - which is
    the exact defect F15 was raised for. `Executor.map` cancels the
    not-yet-started futures when this generator is closed, so a crash still
    only waits out the handful of requests already in flight.
    """
    workers = max(1, config.max_concurrency)
    stage = current_stage()
    if workers == 1 or len(event_ids) < 2:
        for event_id in event_ids:
            yield _fetch_one(event_id, client, cache, stage)
        return

    with ThreadPoolExecutor(max_workers=workers) as pool:
        yield from pool.map(lambda e: _fetch_one(e, client, cache, stage), event_ids)


def rows_to_consider(sheet: list[dict], *, include_unpriced: bool) -> list[dict]:
    """Which sheet rows this run will try to grade.

    Priced-only by default: a row with no price cannot answer the question
    this stage exists for, since K_PRICE is fitted on ``market_p`` and
    ``market_p`` comes from the offer. ``include_unpriced`` widens it to the
    whole board — those rows are real forecasts we made and stand behind, and
    grading them is the only way a backfill can account for every market
    considered rather than only the part that carried a price.
    """
    if include_unpriced:
        return list(sheet)
    return [r for r in sheet if r.get("offered_odds")]


def main() -> int:
    set_stage("SETTLE")
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD", default=now().strftime("%Y-%m-%d"))
    parser.add_argument(
        "--include-unpriced",
        action="store_true",
        help=(
            "Also settle rows Superbet never quoted (verdict NO_PRICE). They "
            "cannot reach the K_PRICE fitter — market_p is NULL for them by "
            "construction — but they are real forecasts we made, and grading "
            "them is the only way a backfill can say what the day's whole "
            "board did rather than just the part that carried a price."
        ),
    )
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

    # A row with no price cannot answer the question this stage exists for —
    # K_PRICE needs market_p, and market_p comes from the offer. So the
    # default is priced-only. --include-unpriced widens it to the whole
    # board, for a backfill that has to account for every market considered.
    considered = rows_to_consider(sheet, include_unpriced=args.include_unpriced)
    by_event: dict[int, list[dict]] = {}
    for row in considered:
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
    # An event with no fixture is never fetched: the skip is decided from
    # local state, and asking the bridge for it would spend a request to
    # learn nothing.
    to_fetch: list[int] = []
    for event_id, event_rows in sorted(by_event.items()):
        if event_id in fixtures:
            to_fetch.append(event_id)
        else:
            skipped["NO_FIXTURE"] += len(event_rows)

    try:
        for fetched in fetch_events_concurrently(to_fetch, client, cache, config):
            event_id = fetched.event_id
            event_rows = by_event[event_id]
            fixture = fixtures[event_id]
            if fetched.circuit_open:
                skipped["PROVIDER_ERROR"] += len(event_rows)
                breaker_open = True
                break
            if fetched.reason is not None:
                if fetched.error:
                    print(
                        f"PROVIDER_ERROR event={event_id}: {fetched.error}",
                        file=sys.stderr,
                    )
                skipped[fetched.reason] += len(event_rows)
                continue
            assert fetched.payload is not None
            event, statistics, incidents = fetched.payload
            flat = extract_flat_statistics(statistics) if statistics else {}
            if isinstance(flat, GapReason):
                flat = {}
            competition_id = (
                (event.get("tournament") or {}).get("uniqueTournament") or {}
            ).get("id")
            events_settled += 1

            # F54. One squad list grades every player row on this fixture.
            # Fetched lazily, and only when the sheet actually carries one:
            # on 2026-09-22 that was 4 fixtures of 270, so SETTLE's cost per
            # day is four requests, not one per event.
            squads: dict[bool, dict[str, Any] | None] | None = None
            if any(is_player_metric(r["market"]) for r in event_rows):
                lineups = fetch_lineups(client, cache, event)
                squads = {
                    True: squad_statistics(lineups, is_home=True),
                    False: squad_statistics(lineups, is_home=False),
                }

            for row in event_rows:
                if is_player_metric(row["market"]):
                    graded = _settle_player(row, squads)
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
        "rows_in_sheet": len(sheet),
        "rows_considered": len(considered),
        "include_unpriced": args.include_unpriced,
        "priced_rows_in_sheet": sum(1 for r in sheet if r.get("offered_odds")),
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

    # The skip counter, in full and on disk. SOFA_SUMMARY carries the top
    # twelve, which is enough to see whether the stage worked and not enough
    # to audit it: the reason a row went ungraded is the whole answer to "why
    # did it not come in", and reconstructing it later from the artifacts
    # means guessing. A guess collapses "the match was postponed" and "the
    # provider has no reading of that statistic" into one bucket, and those
    # two are not the same fact about the day.
    skips_path = run_dir / "07_settle_skips.json"
    with open(skips_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "date": args.date,
                "include_unpriced": args.include_unpriced,
                "rows_considered": len(considered),
                "rows_settled": len(rows),
                "events_in_sheet": len(by_event),
                "events_settled": events_settled,
                "breaker_open": breaker_open,
                "skipped": dict(sorted(skipped.items(), key=lambda kv: -kv[1])),
            },
            f,
            indent=2,
        )

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
                "skips_path": str(skips_path),
            }
        ),
        flush=True,
    )
    return {"OK": 0, "PARTIAL": 1, "FAILED": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
