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

Football actuals come from bzzoiro (``/events/{id}/stats/`` for counts,
``/events/{id}/`` for the score) and are cached to disk, so re-running after a
code change costs no requests at all. Tennis settles from ESPN's per-date
tennis scoreboard instead -- tennis fixtures carry no bzzoiro id at all -- and
covers the length markets only (total games, total sets, a player's games).
Aces and double faults stay uncovered rather than guessed: ESPN answers
``statsSource: none`` for tennis.

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
from bet.simple_stats.artifact_io import load_market_context, write_json_atomic  # noqa: E402
from bet.simple_stats.contracts import (  # noqa: E402
    EventDossierListV1,
    EventListV1,
    MarketContextV1,
    StatsSheetV1,
    SuperbetOfferV1,
    TipsterSignalV1,
)
from bet.simple_stats.bet_builder_draft import BAR_BASES  # noqa: E402
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
    # ``get_event_result`` returns a *bundle*: the fixture row is at
    # ``value["event"]``, so the score is one level deeper than this function
    # read for its entire existence. The cost was silent and total -- all 301
    # fixtures in ``runs/_backtest_actuals.json`` carried zero goals keys, so
    # ``goals_total``, ``goals_1h_total``, ``goals_2h_total`` and every
    # ``goals_*_for`` had never settled for any row on any slate. Goals are the
    # largest priced family (300 of 391 priced candidate rows on 2026-09-01),
    # which means every backtest conclusion in this repo -- including the
    # "77 settled bets" behind ``tier_for_row``'s tier revert -- was measured
    # on corners and cards alone.
    #
    # The unwrapped shape is still accepted, so a caller that already reached
    # into ``value["event"]`` keeps working and the cached actuals of either
    # vintage settle.
    inner = event_payload.get("event")
    score = (inner.get("score") if isinstance(inner, dict) else None) or event_payload.get("score") or {}
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


FINISHED_STATUSES = frozenset({"finished", "ft", "aet", "after_penalties", "awarded"})


def _is_finished(event_payload: dict) -> tuple[bool, str | None]:
    """``(finished?, status)`` for the fixture row bzzoiro returns.

    ``/events/{id}/stats/`` answers for a match in play exactly as it answers
    for a finished one -- there is no marker on the stats block itself, so a
    partial count is indistinguishable from a full-time one. The 2026-09-02
    slate settled that way: every one of its twelve fixtures was in
    ``2nd_half`` when the backtest ran, eleven rows were graded against
    ~70-minute counts, and the run reported hit 36.4% against a claimed 56.3%.
    The corners rows were the worst of it -- Burnley "lost" corners over 7.5 on
    3 corners with half an hour still to play.

    ``match_status`` was in the payload the whole time, one level in at
    ``value["event"]``, next to the score this function already reads.
    """
    inner = event_payload.get("event")
    inner = inner if isinstance(inner, dict) else event_payload
    status = inner.get("match_status")
    if not isinstance(status, str) or not status:
        return False, None
    return status.strip().lower() in FINISHED_STATUSES, status


def _fetch_one(client, bzz_id: str) -> tuple[dict, list[str]]:
    """``({"home":…, "away":…, "total":…}, gaps)`` for one finished fixture.

    Refuses anything not full-time. An unfinished fixture returns no actuals at
    all, so the caller neither settles nor caches it -- the cache is on disk
    forever and a mid-match snapshot in it would poison every later run of
    every later day.
    """
    gaps: list[str] = []
    try:
        event = client.get_event_result(bzz_id)
        payload = event.value if getattr(event, "value", None) else {}
    except Exception as exc:  # noqa: BLE001
        return {}, [f"{bzz_id}: event error: {exc}"]
    payload = payload if isinstance(payload, dict) else {}
    finished, status = _is_finished(payload)
    if not finished:
        return {}, [f"{bzz_id}: not full-time (match_status={status or 'unknown'})"]
    try:
        stats, gap, _card_flags = _bzzoiro_match_stats(client, bzz_id)
    except Exception as exc:  # noqa: BLE001 - one fixture must not abort a slate
        return {}, [f"{bzz_id}: stats error: {exc}"]
    if gap:
        gaps.append(f"{bzz_id}: {gap}")
    actuals = {
        "home": dict(stats.get("home") or {}),
        "away": dict(stats.get("away") or {}),
        "total": dict(stats.get("total") or {}),
    }
    goals = _score_actuals(payload)
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


def _cache_entry_is_current(entry: dict) -> bool:
    """Whether a cached actuals blob was built by the current metric set.

    The cache is on disk forever and is keyed only by fixture id, so a metric
    added after an entry was written answers NO_DATA for that fixture until the
    entry is refetched -- silently, and only for the older half of the slates,
    which is the shape of bias a backtest can least afford.

    ``cards_points_total`` is the discriminator today: every entry written
    before 2026-09-03 has ``cards_total`` and cannot have it. A fixture that
    genuinely published no card statistics has neither and is not refetched.
    """
    total = entry.get("total")
    if not isinstance(total, dict):
        return True
    if "cards_total" in total and "cards_points_total" not in total:
        return False
    return True


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
            gaps.append("{} v {}: no bzzoiro id".format(*_sides_of(event)))
            continue
        cached = cache.get(str(bzz_id))
        if cached is not None and _cache_entry_is_current(cached):
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


def _sides_of(event) -> tuple[str, str]:
    """The two competitors' names, whichever pair of fields the sport uses.

    EVENT_LIST_V1 stores a football fixture as ``home_team``/``away_team`` and
    a tennis match as ``player_one``/``player_two``, and every settlement site
    here read only the first pair. For tennis that made ``settle.team_side``
    resolve against ``None``/``None``, so it returned None and **every
    per-player row settled NO_DATA** -- a player's games, aces and double
    faults, 702 of the 2,824 tennis rows on the four slates on disk -- no
    matter what actuals were fetched. It read as missing coverage and was a
    field name.
    """
    return (
        event.home_team or event.player_one or "",
        event.away_team or event.player_two or "",
    )


def _tennis_actuals_from_row(row: dict) -> dict[str, dict[str, float]]:
    """One parsed ESPN competition as the shape ``settle`` reads.

    Only what the published result actually states: the two players' games, the
    match total and the number of sets. Aces and double faults are **not**
    invented from it -- ESPN answers ``statsSource: none`` for tennis and its
    ``/summary`` route 400s, so those rows stay uncovered rather than guessed,
    the same rule ``fetch_actuals`` follows for football.

    Side attribution comes from ``stats["games_won"]``, which espn.py builds
    from each competitor's own ``linescores`` after ordering them by
    ``homeAway`` -- not from the published score line, which is written from
    the winner's perspective and would silently transpose the two players on
    every match the favourite lost. The client already refuses any competition
    where those two transcriptions disagree.
    """
    stats = row.get("stats") or {}
    games = stats.get("games_won") or {}
    home, away = games.get("home"), games.get("away")
    if home is None or away is None:
        return {}
    sets = (stats.get("total_sets") or {}).get("home")
    total: dict[str, float] = {"total_games": float(home) + float(away)}
    if sets is not None:
        total["total_sets"] = float(sets)
    return {
        "home": {"games_won": float(home)},
        "away": {"games_won": float(away)},
        "total": total,
    }


def fetch_tennis_actuals(
    events: EventListV1, date: str, cache: dict
) -> tuple[dict[str, dict], list[str]]:
    """``{event_id: actuals}`` for the slate's tennis fixtures, off one scoreboard.

    A tennis event carries no bzzoiro id -- discovery gets the whole tennis
    slate from odds-api -- so the football path cannot settle any of it, and
    until now the backtest reported every tennis row as uncovered. That is what
    left ``tier_for_row``'s READY-to-CALL promotion measured on football only.

    ESPN's tennis scoreboard is per *date* and returns the whole draw of every
    tournament running, so a slate costs one request rather than one per
    fixture, and the client caches it. Matching is by both players' names
    against both sides of the competition, in either order; a fixture that
    matches two competitions is refused rather than settled against a guess.
    """
    gaps: list[str] = []
    tennis = [e for e in events.events if e.sport == "tennis"]
    if not tennis:
        return {}, gaps

    from bet.api_clients.espn import _iter_tennis_competitions, _parse_tennis_competition
    from bet.simple_stats.providers import _normalize_team_name, _team_matches

    client = get_client("espn-tennis", rate_limiter=RateLimiter())
    payload = client._scoreboard_for_date(date.replace("-", ""))
    if payload is None:
        return {}, [f"espn-tennis: no scoreboard for {date}"]

    parsed: list[dict] = []
    for event, grouping, comp in _iter_tennis_competitions(payload):
        row = _parse_tennis_competition(event, grouping, comp)
        if row is not None:
            parsed.append(row)

    resolved: dict[str, dict] = {}
    for event in tennis:
        name_a, name_b = _sides_of(event)
        want_a = _normalize_team_name(name_a)
        want_b = _normalize_team_name(name_b)
        hits = []
        for row in parsed:
            got_a = _normalize_team_name(row.get("home_team", ""))
            got_b = _normalize_team_name(row.get("away_team", ""))
            straight = _team_matches(want_a, got_a) and _team_matches(want_b, got_b)
            crossed = _team_matches(want_a, got_b) and _team_matches(want_b, got_a)
            if straight or crossed:
                hits.append((row, crossed))
        if not hits:
            gaps.append(f"{name_a} v {name_b}: not on the ESPN scoreboard")
            continue
        if len(hits) > 1:
            gaps.append(
                f"{name_a} v {name_b}: {len(hits)} scoreboard "
                "matches; refusing to guess which"
            )
            continue
        row, crossed = hits[0]
        if not row.get("completed", True):
            gaps.append(f"{name_a} v {name_b}: did not finish")
            continue
        actuals = _tennis_actuals_from_row(row)
        if not actuals:
            gaps.append(f"{name_a} v {name_b}: scoreboard states no games")
            continue
        if crossed:
            # The slate and the scoreboard list the two players in opposite
            # order, so the per-side figures have to follow the slate's order
            # -- ``settle.team_side`` resolves a row's subject against the
            # *event's* home/away, not the scoreboard's.
            actuals["home"], actuals["away"] = actuals["away"], actuals["home"]
        resolved[event.event_id] = actuals
        cache[f"tennis:{event.event_id}"] = actuals
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
        sheet = attach_market_context_column(sheet, _load_recorded_market_context(paths["market"]))
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


def _load_recorded_market_context(path: Path) -> MarketContextV1:
    """Recorded artifacts are historical documents; the live schema moves on.

    Skipping the artifact instead is not an option -- see the caller's comment.
    ``coupons._has_market_reference`` reads ``market_signal`` and it decides
    which of the file's two sections a row lands in, so a rebuild without this
    column selects a different fifteen singles and the comparison would be
    measuring the missing artifact.
    """
    context, dropped = load_market_context(path)
    if dropped:
        print(
            f"  note: {path.name} carries {len(dropped)} prediction field(s) this "
            f"schema no longer has, dropped for the replay: {', '.join(dropped)}",
            file=sys.stderr,
        )
    return context


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
    date: str,
    sheet: StatsSheetV1,
    events: EventListV1,
    *,
    max_singles: int = 15,
    bar_basis: str = "p_low",
    shrink_k: float | None = None,
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
        bar_basis=bar_basis,
        shrink_k=shrink_k,
    )


def rebuilt_coupons(
    date: str,
    *,
    max_singles: int = 15,
    bar_basis: str = "p_low",
    shrink_k: float | None = None,
) -> CouponSet | None:
    sheet = rebuild(date)
    if sheet is None:
        return None
    paths = _run_paths(date)
    events = EventListV1.model_validate_json(paths["events"].read_text(encoding="utf-8"))
    return coupons_from_sheet(
        date, sheet, events, max_singles=max_singles, bar_basis=bar_basis,
        shrink_k=shrink_k,
    )


def recorded_sheet_coupons(
    date: str,
    *,
    max_singles: int = 15,
    bar_basis: str = "p_low",
    shrink_k: float | None = None,
) -> CouponSet | None:
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
    return coupons_from_sheet(
        date, sheet, events, max_singles=max_singles, bar_basis=bar_basis,
        shrink_k=shrink_k,
    )


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
                    "event_id": single.event_id,
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
            home_team=_sides_of(event)[0], away_team=_sides_of(event)[1],
        )
        out.append(
            {
                # Carried so a bootstrap can resample *fixtures* rather than
                # rows. Twenty rows off one match are not twenty trials -- they
                # are one match read twenty ways -- and an interval that
                # resamples them independently is narrower than the evidence.
                # Every clustered interval quoted in ``tier_for_row`` is built
                # this way; until now this artifact could not reproduce one.
                "event_id": single.event_id,
                "match": "{} v {}".format(*_sides_of(event)),
                "market": single.market, "line": single.line,
                "direction": single.direction, "subject": single.subject,
                "p_low": single.p_low, "tier": single.tier,
                "price": single.superbet_price,
                "verdict": single.superbet_verdict,
                "outcome": outcome, "actual": actual,
            }
        )
    return out


def settle_slip_legs(
    coupons: CouponSet, events: EventListV1, actuals_by_event: dict[str, dict]
) -> list[dict]:
    """One record per Bet Builder leg -- the two thirds of the file nothing measured.

    ``settle_singles`` covers the singles table, which was 15 rows of the
    2026-09-02 coupon against 32 legs across 8 slips. The legs were never
    settled, so the drafter's own claims had never been checked even once, and
    a Bet Builder is where a bad leg does the most damage: the slip pays
    nothing unless every leg lands.

    Records are shaped exactly like ``settle_singles``' so ``summarise``,
    ``calibration`` and ``profit`` all work on them unchanged. ``price`` is the
    leg's own Superbet price and NOT a slip price -- a leg is settled as the
    independent claim the drafter makes about it, because the combined price is
    deliberately never computed anywhere in this repo (positively correlated
    legs make the product a lie). The ``slip``/``slip_rank`` keys are what lets
    a caller regroup the legs and ask whether a whole slip survived.
    """
    by_id = {e.event_id: e for e in events.events}
    out: list[dict] = []
    for slip in coupons.slips:
        event = by_id.get(slip.event_id)
        actuals = actuals_by_event.get(slip.event_id)
        for leg in slip.draft.legs:
            base = {
                "slip": slip.match, "slip_rank": slip.rank,
                "market": leg.market, "line": leg.line,
                "direction": leg.direction,
                "subject": leg.player_name or leg.team_name,
                "p_low": leg.p_low, "tier": leg.tier,
                "price": leg.superbet_price,
                "verdict": leg.market_verdict,
            }
            if event is None or actuals is None:
                out.append({**base, "outcome": "NO_DATA", "actual": None,
                            "reason": "no actuals for this fixture"})
                continue
            # ``team_name`` is already separate from ``player_name`` on a leg,
            # so unlike a single there is nothing to disambiguate: a player
            # leg settles against the player family, which bzzoiro's match
            # ``/stats/`` does not carry, and reports NO_DATA rather than
            # being scored against his team's figure.
            outcome, actual = settle_row(
                market=leg.market, line=leg.line, direction=leg.direction,
                actuals=actuals, team_name=leg.team_name,
                home_team=_sides_of(event)[0], away_team=_sides_of(event)[1],
            )
            out.append({**base, "match": "{} v {}".format(*_sides_of(event)),
                        "outcome": outcome, "actual": actual})
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
    parser.add_argument(
        "--bar-basis", dest="bar_basis", default="p_low", choices=list(BAR_BASES),
        help="Which probability min_acceptable_odds is derived from, for the "
             "rebuilt/recorded-sheet passes. p_low is what the pipeline ships; "
             "p_central is the arm bet_builder_draft.BAR_BASES exists to "
             "paper-trade and, until this flag, could not be settled at all.",
    )
    parser.add_argument(
        "--shrink-k", dest="shrink_k", type=float, default=None,
        help="Override the market prior's k for every row (Phase 3, "
             "docs/PLAN_EDGE_INTEGRITY_2026-09-03.md). None uses each market's "
             "own value -- 10 for football totals, 20 for the length-dependent "
             "tennis markets. **0 disables the prior**, which is the "
             "pre-2026-09-03 arm. This is how the arms are compared; the value "
             "shipped is not meant to be picked by eye.",
    )
    parser.add_argument("--cache", default=str(DEFAULT_CACHE), help="Actuals cache (JSON)")
    parser.add_argument("--output", default=None, help="Write the full record set here")
    parser.add_argument("--show-rows", action="store_true", help="Print every settled row")
    parser.add_argument(
        "--legs", action="store_true",
        help="Also settle every Bet Builder leg. 32 of the 47 predictions in "
             "the 2026-09-02 coupon were legs and none had ever been settled.",
    )
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
        tennis_actuals, tennis_gaps = fetch_tennis_actuals(events, date, cache)
        actuals.update(tennis_actuals)
        gaps.extend(tennis_gaps)
        all_gaps.extend(gaps)
        # Called out on its own line, not left to be found among a few hundred
        # "no bzzoiro id" gaps: a slate that is still being played reads as a
        # coverage problem but is a *timing* one, and the fix is to wait.
        unfinished = [g for g in gaps if "not full-time" in g]
        print(f"{date}: actuals for {len(actuals)} of {len(events.events)} fixtures")
        if unfinished:
            print(
                f"  {len(unfinished)} fixture(s) not full-time yet -- "
                "not settled, not cached; re-run after they finish"
            )
        budget = args.max_singles
        loaders = {
            "recorded": lambda d: load_recorded(d),
            "rebuilt": lambda d: rebuilt_coupons(
                d, max_singles=budget, bar_basis=args.bar_basis,
                shrink_k=args.shrink_k,
            ),
            "recorded_sheet": lambda d: recorded_sheet_coupons(
                d, max_singles=budget, bar_basis=args.bar_basis,
                shrink_k=args.shrink_k,
            ),
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
            if args.legs:
                legs = settle_slip_legs(coupons, events, actuals)
                for record in legs:
                    record["date"] = date
                all_records.setdefault(f"{which}_legs", []).extend(legs)
                leg_summary = summarise(f"{date} {which} legs", legs)
                per_slate.append(leg_summary)
                print("  " + _format(leg_summary))
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
    for which in ("recorded", "recorded_sheet", "rebuilt",
                  "recorded_legs", "recorded_sheet_legs", "rebuilt_legs"):
        if all_records.get(which):
            summary = summarise(f"ALL {which}", all_records[which])
            pooled.append(summary)
            print("  " + _format(summary))
    if args.calibrate:
        print("\ncalibration -- p_low is a lower bound, so realised should be >= claimed")
        for which in ("recorded", "recorded_sheet", "rebuilt",
                      "recorded_legs", "recorded_sheet_legs", "rebuilt_legs"):
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
