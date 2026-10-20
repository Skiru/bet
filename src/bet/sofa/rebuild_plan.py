"""The rebuild of one day, as a plan: which steps run, in which order, and why.

`scripts/sofa/rebuild_day.py` runs the plan; this module only decides it, so
the decision is testable offline (plan 2026-10-05 production grade, F0.2).

Before F0.2 the rebuild was a manual sequence in `/sofa-rebuild`, and on
2026-10-05 two rebuilds ran on stale prices: CONFIDENCE on an offer older
than its 45-minute limit emptied 08_confidence.json down to the locked legs
(STALE_PRICE everywhere, which reads like a modelling result), and SHADOW
with its default 3 h horizon skipped a hockey game starting at 15:30Z (an
event already on file and starting beyond the horizon is not fetched again),
so its leg went STALE_PRICE too. The plan refreshes a price BEFORE the gate
that would refuse it, with a margin for the rebuild's own duration:

1. freshness, only while the day is live - OFFER when the oldest rung of a
   fixture that can still be bet is older than the CONFIDENCE limit minus
   OFFER_REFRESH_MARGIN; SHADOW (with a horizon to the farthest open start)
   and CS2 when an open event's newest price is older than
   sport_day.MAX_PRICE_AGE minus SPORT_REFRESH_MARGIN, or a SHADOW event
   lagged the latest snapshot because it started beyond the horizon; then
   SPORT_IDENTITY (bridge) after a fresh snapshot;
2. SHEET only when CONFIDENCE would refuse the sheet (a stats-only build of a
   sheet not built under that rule: bet.sofa.epochs.sheet_epoch); COUPON
   (06_coupon.json, the priced selector audit_coupon checks - not the
   coupon) only when it is older than the sheet / vetoes / reads;
3. FIXTURE_CHECK (bridge), CONFIDENCE, SPORT_CONFIDENCE, COUPON_ASSEMBLY,
   PDF, then the audits.

A day that is over (every match started) refreshes nothing - its prices are
historical and every gate downstream refuses them, which is correct - and
the plan says so in its notes.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from bet.sofa import epochs, sheet_config, sport_day
from bet.sofa import fixture_status as fs
from bet.sofa import referees as referee_terms
from bet.sofa import sport_identity as si
from bet.sofa.football_score_markets import MARKETS as SCORE_MARKETS
from bet.sofa.locked_print import starts_after
from bet.sofa.tennis_sets import SET_SCORE_NOT
from bet.sofa.tennis_winner import MATCH_WON_FOR

# run_offer.py --min-minutes-to-kickoff: a fixture starting sooner is not
# re-priced (CONFIDENCE refuses it at 15 min anyway).
OFFER_MIN_MINUTES_TO_KICKOFF = 20
# Refresh the offer this long BEFORE it reaches CONFIDENCE's limit: OFFER,
# FIXTURE_CHECK and a SHEET take minutes, and the limit is checked when
# CONFIDENCE runs, not when the rebuild starts.
OFFER_REFRESH_MARGIN = timedelta(minutes=15)
# The same for the measured sports' 3 h limit (SPORT_CONFIDENCE).
SPORT_REFRESH_MARGIN = timedelta(minutes=30)
# scripts/sofa/run_shadow.py DEFAULT_HORIZON_H (a test pins the two).
SHADOW_DEFAULT_HORIZON_H = 3.0
# An open SHADOW event whose newest record is this much older than the
# file's newest snapshot was skipped by that snapshot (beyond its horizon).
SHADOW_LAG = timedelta(minutes=15)
# ...and only counts when its own price is at least this old: shadow_daily
# snapshots every ~30 min with the 3 h horizon, so right after a rebuild's
# full-horizon SHADOW the loop's next snapshot made every later event look
# "skipped" while its price was 18 min old (10-05 12:01Z: 13 hockey and 15
# basketball events, a needless SHADOW on every rebuild).
SHADOW_LAG_MIN_AGE = timedelta(minutes=60)
SHADOW_SPORTS = ("hockey", "basketball", "volleyball")
SPORTS = (*SHADOW_SPORTS, "cs2")

PY = "PYTHON"  # replaced by the interpreter in the runner


@dataclass(frozen=True)
class SportState:
    """One measured sport's snapshot of the day, as SPORT_CONFIDENCE reads it."""

    sport: str
    events: int = 0  # day-window events with a price on file
    open_events: int = 0  # ... not yet inside the kickoff margin
    oldest_open_price: datetime | None = None  # min over open events of newest
    farthest_open_kickoff: datetime | None = None
    lagging_events: int = 0  # SHADOW: skipped by the latest snapshot (horizon)
    newest_snapshot: datetime | None = None


@dataclass(frozen=True)
class DayState:
    """What the plan needs to know about the day on disk, at `now`."""

    date: str
    now: datetime
    price_max_age: timedelta
    has_fixtures: bool = True
    has_sheet: bool = True
    has_offer: bool = True
    sheet_epoch: str | None = epochs.STATS_ONLY
    # every 05_sheet.json row rated under the shared-league link rule
    sheet_link_shared: bool = True
    # every 05_sheet.json row priced under epochs.COUNT_DISPERSION
    sheet_dispersion: bool = True
    # every 05_sheet.json row priced under epochs.CARDS_CORRELATION
    sheet_cards: bool = True
    # every 05_sheet.json row priced under epochs.PER_MARKET_K
    sheet_k: bool = True
    # every tennis 05_sheet.json row priced under epochs.TENNIS_SCOPED_TABLE
    sheet_tennis_table: bool = True
    # every 05_sheet.json row priced under epochs.SAMPLE_OPPONENT_CORRECTION
    sheet_opponent: bool = True
    # the audit 2026-10-13 switches' markers: every row the rule applies to
    # (football / tennis, epochs.sheet_has_marker) carries it
    sheet_game_state: bool = True
    sheet_rated_scope: bool = True
    sheet_venue_prior: bool = True
    sheet_season_phase: bool = True
    sheet_rating_weight: bool = True
    sheet_tennis_set: bool = True
    sheet_cup_strength: bool = True
    sheet_sample_cup: bool = True
    sheet_goals_stretch: bool = True
    sheet_count_stretch: bool = True
    sheet_player_stretch: bool = True
    sheet_referee: bool = True
    sheet_player_share: bool = True
    sheet_closeness_stretch: bool = True
    sheet_tennis_aces: bool = True
    # bet.sofa.sheet_config: the fingerprint the sheet's rows carry (None: a
    # sheet written before the stamp; "mixed": rows disagree) and the files'
    # as they stand
    sheet_config_sha: str | None = None
    config_sha: str | None = None
    # D2 (epochs.TENNIS_MATCH_WINNER): a tennis fixture is priced on
    # 04_offer.json; the offer / the sheet carry a match_won_for rung / row
    offer_has_tennis: bool = False
    offer_has_winner: bool = True
    sheet_has_winner: bool = True
    # epochs.FOOTBALL_SCORE_MARKETS / TENNIS_SET_COMPLEMENTS (switched on
    # into the built day 2026-10-16 07:46Z): a football fixture is priced on
    # 04_offer.json; the offer / the sheet carry a score-market rung / row,
    # a tennis set_score_not rung / row
    offer_has_football: bool = False
    offer_has_score: bool = True
    sheet_has_score: bool = True
    offer_has_set_not: bool = True
    sheet_has_set_not: bool = True
    offer_fixtures: int = 0  # fixtures on 04_offer.json with a rung
    open_fixtures: int = 0  # ... a refresh would re-price and CONFIDENCE gate
    oldest_open_rung: datetime | None = None
    newest_rung: datetime | None = None
    sports: Mapping[str, SportState] = field(default_factory=dict)
    has_sport_fixtures: bool = True
    # 06_coupon.json (the priced VALUE selector audit_coupon checks, not the
    # coupon) missing or older than the sheet / vetoes / reads it reads.
    coupon06_stale: bool = False
    # epochs.FOOTBALL_REFEREE (audit 2026-10-21 D7): open football fixtures
    # whose cards / fouls rows say NO_REFEREE while the DB now names their
    # referee (a label, or the /event RESOLVE / FIXTURE_CHECK cached)
    referee_now_known: tuple[int, ...] = ()


@dataclass(frozen=True)
class Step:
    name: str
    argv: tuple[str, ...]  # PY stands for the interpreter
    reason: str
    # A soft step's FAILED makes the rebuild PARTIAL and does not stop it:
    # no bridge is UNVERIFIED / NOT_IDENTIFIED downstream, nothing refused,
    # and a failed sport snapshot leaves only the sport legs STALE_PRICE.
    soft: bool = False


@dataclass
class Plan:
    date: str
    epoch: str
    sports_on_coupon: bool
    steps: list[Step] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    refusal: str | None = None

    def names(self) -> list[str]:
        return [s.name for s in self.steps]


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(UTC)


def _age_min(now: datetime, t: datetime | None) -> str:
    return "none" if t is None else f"{(now - t).total_seconds() / 60:.0f} min"


def _z(t: datetime | None) -> str | None:
    return None if t is None else t.astimezone(UTC).isoformat().replace("+00:00", "Z")


# --- observation -------------------------------------------------------------


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def observe_offer(
    fixtures: list[Mapping[str, Any]],
    offers: list[Mapping[str, Any]],
    status: Mapping[int, Mapping[str, Any]],
    now: datetime,
) -> tuple[int, int, datetime | None, datetime | None]:
    """(fixtures with a rung, open ones, oldest open rung, newest rung).

    Open = a refresh with --min-minutes-to-kickoff re-prices it AND
    CONFIDENCE would not refuse it as kicked off: one predicate for both,
    locked_print.starts_after (every clock CONFIDENCE holds, with
    FIXTURE_CHECK's fresh start), and Superbet not reporting it under way.
    Only an open fixture's price can be refreshed and only its age empties a
    coupon. Until 10-05 this also required RESOLVE's two frozen clocks to be
    ahead (run_offer's old filter): a match moved later (Gaubas, 12:30Z ->
    13:30Z) was not open, so its stale price triggered no refresh.
    """
    by_id = {f.get("sofascore_event_id"): f for f in fixtures}
    cutoff = now + timedelta(minutes=OFFER_MIN_MINUTES_TO_KICKOFF)
    priced = open_n = 0
    oldest: datetime | None = None
    newest: datetime | None = None
    for o in offers:
        stamps = [_utc(str(r["fetched_at_utc"])) for r in o.get("rungs") or []
                  if r.get("fetched_at_utc")]
        if not stamps:
            continue
        priced += 1
        top = max(stamps)
        newest = top if newest is None or top > newest else newest
        eid = o.get("sofascore_event_id")
        fx = by_id.get(eid)
        if fx is None or o.get("superbet_started_utc"):
            continue
        entry = status.get(int(eid)) if eid is not None else None
        if not starts_after(fx, o.get("superbet_kickoff_seen_utc"), entry, cutoff):
            continue
        open_n += 1
        low = min(stamps)
        oldest = low if oldest is None or low < oldest else oldest
    if not offers:
        # No offer yet: open is what a first OFFER would price.
        open_n = sum(
            1 for fx in fixtures
            if starts_after(fx, None, status.get(int(fx["sofascore_event_id"]))
                            if fx.get("sofascore_event_id") is not None else None,
                            cutoff))
    return priced, open_n, oldest, newest


def observe_sport(runs_dir: str, sport: str, date: str, now: datetime) -> SportState:
    """The sport's day-window events as SPORT_CONFIDENCE reads them
    (si.snapshot_events, newest price per event, Superbet's start)."""
    start, end = si.day_window(date)
    events = si.snapshot_events(runs_dir, sport, date, now)
    n = open_n = lagging = 0
    oldest: datetime | None = None
    farthest: datetime | None = None
    newest_any: datetime | None = None
    rows: list[tuple[datetime, datetime]] = []
    for ev in events.values():
        if not ev.fetched_at:
            continue
        top = max(_utc(t) for t in ev.fetched_at.values())
        newest_any = top if newest_any is None or top > newest_any else newest_any
        kickoff = _utc(ev.kickoff_utc)
        if not (start <= kickoff < end):
            continue
        n += 1
        if kickoff - now < sport_day.KICKOFF_MARGIN:
            continue
        open_n += 1
        rows.append((kickoff, top))
        oldest = top if oldest is None or top < oldest else oldest
        farthest = kickoff if farthest is None or kickoff > farthest else farthest
    if sport in SHADOW_SPORTS and newest_any is not None:
        horizon = timedelta(hours=SHADOW_DEFAULT_HORIZON_H)
        lagging = sum(1 for kickoff, top in rows
                      if newest_any - top > SHADOW_LAG
                      and now - top >= SHADOW_LAG_MIN_AGE
                      and kickoff - newest_any > horizon)
    return SportState(sport, n, open_n, oldest, farthest, lagging, newest_any)


AUDIT_MARKERS: tuple[tuple[str, str, str], ...] = (
    epochs.GAME_STATE_MARKER, epochs.FOOTBALL_RATED_SCOPE_MARKER,
    epochs.FOOTBALL_VENUE_PRIOR_MARKER, epochs.SEASON_PHASE_MARKER,
    epochs.FOOTBALL_RATING_WEIGHT_MARKER, epochs.TENNIS_SET_RATING_PRICES_MARKER,
    epochs.FOOTBALL_CUP_STRENGTH_MARKER, epochs.SAMPLE_CUP_STRENGTH_MARKER,
    epochs.FOOTBALL_GOALS_STRETCH_MARKER, epochs.FOOTBALL_COUNT_STRETCH_MARKER,
    epochs.FOOTBALL_PLAYER_STRETCH_MARKER, epochs.TENNIS_ACES_OPPONENT_MARKER,
    epochs.FOOTBALL_REFEREE_MARKER,
    epochs.FOOTBALL_PLAYER_SHARE_MARKER,
    epochs.FOOTBALL_CLOSENESS_STRETCH_MARKER,
)


def audit_sheet_stale(state: DayState) -> list[str]:
    """The audit 2026-10-13 switches on for the day and the clock whose
    marker the sheet's football / tennis rows lack - each a reason to re-run
    SHEET (the switch condition SHEET itself reads, stats-only included)."""
    d, now = state.date, state.now
    if not epochs.stats_only(d, now):
        return []
    checks = (
        (epochs.game_state_enabled(d, now), state.sheet_game_state,
         "football side centres carry the game-state term "
         "(epochs.game_state_enabled)"),
        (epochs.football_rated_scope(d, now), state.sheet_rated_scope,
         "the rating also prices RATED_SCOPE_MARKETS "
         "(epochs.football_rated_scope)"),
        (epochs.football_venue_prior(d, now), state.sheet_venue_prior,
         "sample-only football centres read the league venue multiplier "
         "(epochs.football_venue_prior)"),
        (epochs.season_phase_enabled(d, now), state.sheet_season_phase,
         "football goals centres carry the season-phase term "
         "(epochs.season_phase_enabled)"),
        (epochs.football_rating_weight(d, now), state.sheet_rating_weight,
         "rated football centres read their market's own rating weight "
         "(epochs.football_rating_weight)"),
        # SHEET reads it only on top of the rating prices
        (epochs.tennis_rating_prices(d, now)
         and epochs.tennis_set_rating_prices(d, now), state.sheet_tennis_set,
         "tennis per-set games and sets_total read off the rating's "
         "neighbours (epochs.tennis_set_rating_prices)"),
        (epochs.football_cup_strength(d, now), state.sheet_cup_strength,
         "the football rating reads the league strength learnt in "
         "international club cups (epochs.football_cup_strength)"),
        # SHEET reads it only on top of B15 and the cup strength
        (epochs.sample_opponent_correction(d, now)
         and epochs.football_cup_strength(d, now)
         and epochs.sample_cup_strength(d, now), state.sheet_sample_cup,
         "the football sample correction reads the cup league strength "
         "(epochs.sample_cup_strength)"),
        (epochs.football_goals_stretch(d, now), state.sheet_goals_stretch,
         "football goals centres carry the supremacy stretch "
         "(epochs.football_goals_stretch)"),
        (epochs.football_count_stretch(d, now), state.sheet_count_stretch,
         "football count centres carry the supremacy stretch "
         "(epochs.football_count_stretch)"),
        (epochs.football_player_stretch(d, now), state.sheet_player_stretch,
         "footballers' shots centres carry the supremacy stretch "
         "(epochs.football_player_stretch)"),
        (epochs.football_player_share(d, now), state.sheet_player_share,
         "footballers' shots centres are their share of the side's team centre "
         "(epochs.football_player_share)"),
        (epochs.football_closeness_stretch(d, now),
         state.sheet_closeness_stretch,
         "football count centres carry the closeness term "
         "(epochs.football_closeness_stretch)"),
        (epochs.tennis_aces_opponent(d, now), state.sheet_tennis_aces,
         "tennis aces centres read the returner's factor "
         "(epochs.tennis_aces_opponent)"),
        (epochs.football_referee(d, now), state.sheet_referee,
         "football cards / fouls centres carry the referee term "
         "(epochs.football_referee)"),
    )
    return [why for on, has, why in checks if on and not has]


def referee_now_known(runs_dir: str, date: str, now: datetime,
                      db_path: str | Path | None) -> tuple[int, ...]:
    """Football fixtures not yet started whose 05_sheet.json cards / fouls
    rows were priced with no referee (referee_read.status NO_REFEREE) while
    referees.referee_for_event now names one on ``db_path`` (audit
    2026-10-21 D7: Sofascore announces referees late, after the morning
    SHEET). One read-only lookup per such fixture; nothing when the switch
    is off, there is no DB or no sheet. A DB error is no information."""
    if db_path is None or not epochs.football_referee(date, now):
        return ()
    run = Path(runs_dir) / date
    sheet_path, fixtures_path = run / "05_sheet.json", run / "02_fixtures.json"
    if not sheet_path.exists() or not Path(db_path).exists():
        return ()
    waiting = sorted({
        int(r["sofascore_event_id"]) for r in _load_json(sheet_path) or []
        if r.get("sport") == "football"
        and r.get("sofascore_event_id") is not None
        and (r.get("referee_read") or {}).get("status")
        == referee_terms.NO_REFEREE})
    if not waiting:
        return ()
    fixtures = {f.get("sofascore_event_id"): f for f in (
        _load_json(fixtures_path) if fixtures_path.exists() else [])}
    status = fs.load(run)
    known: list[int] = []
    for eid in waiting:
        fx = fixtures.get(eid)
        if fx is None or not starts_after(fx, None, status.get(eid), now):
            continue  # started: its legs are locked or gone, nothing to price
        try:
            found = referee_terms.referee_for_event(db_path, eid)
        except sqlite3.Error:
            return tuple(known)
        if found is not None and found.referee_id is not None:
            known.append(eid)
    return tuple(known)


def referee_sheet_step(date: str, events: tuple[int, ...], run_id: str,
                       where: str) -> Step:
    """SHEET again for the referees named since the sheet (D7)."""
    shown = ", ".join(str(e) for e in events[:5])
    return Step(
        "SHEET", _pipeline(date, "SHEET", run_id),
        f"{len(events)} football fixtures priced with no referee now have one "
        f"{where} (epochs.football_referee; {shown}): their cards / fouls "
        "centres read the referee term")


def after_fixture_check(runs_dir: str, date: str, now: datetime,
                        db_path: str | Path | None,
                        run_id: str = "rebuild") -> list[Step]:
    """The steps a rebuild inserts right after its FIXTURE_CHECK, before
    CONFIDENCE: SHEET again when FIXTURE_CHECK's refreshed /event names the
    referee of an open fixture the sheet priced without one. The plan's own
    SHEET step runs BEFORE FIXTURE_CHECK, so it cannot see that referee."""
    events = referee_now_known(runs_dir, date, now, db_path)
    if not events:
        return []
    return [referee_sheet_step(date, events, run_id,
                               "after FIXTURE_CHECK's /event")]


def observe(runs_dir: str, date: str, now: datetime,
            price_max_age: timedelta,
            db_path: str | Path | None = None) -> DayState:
    """Read the day's artifacts into a DayState (no network, read-only;
    ``db_path`` is read for the referees only, D7 - None skips it)."""
    run = Path(runs_dir) / date
    fixtures_path, sheet_path, offer_path = (
        run / "02_fixtures.json", run / "05_sheet.json", run / "04_offer.json")
    fixtures = _load_json(fixtures_path) if fixtures_path.exists() else []
    offers = _load_json(offer_path) if offer_path.exists() else []
    sheet_ep: str | None = None
    sheet_link_shared = True
    sheet_dispersion = True
    sheet_cards = True
    sheet_k = True
    sheet_tennis_table = True
    sheet_opponent = True
    sheet_has_winner = True
    sheet_has_score = True
    sheet_has_set_not = True
    markers = {m: True for m in AUDIT_MARKERS}
    sheet_config_sha: str | None = None
    if sheet_path.exists():
        sheet = _load_json(sheet_path)
        sheet_ep = epochs.sheet_epoch(sheet) if sheet else epochs.STATS_ONLY
        sheet_link_shared = epochs.sheet_link_shared(sheet or [])
        sheet_dispersion = epochs.sheet_count_dispersion(sheet or [])
        sheet_cards = epochs.sheet_cards_correlation(sheet or [])
        sheet_k = epochs.sheet_per_market_k(sheet or [])
        sheet_tennis_table = epochs.sheet_tennis_scoped_table(sheet or [])
        sheet_opponent = epochs.sheet_sample_opponent_correction(sheet or [])
        sheet_has_winner = any(
            r.get("market") == MATCH_WON_FOR for r in sheet or [])
        sheet_has_score = any(
            r.get("market") in SCORE_MARKETS for r in sheet or [])
        sheet_has_set_not = any(
            r.get("market") == SET_SCORE_NOT for r in sheet or [])
        markers = {m: epochs.sheet_has_marker(sheet or [], m)
                   for m in AUDIT_MARKERS}
        shas = {r.get("config_sha") for r in sheet or []}
        if len(shas) > 1:
            sheet_config_sha = "mixed"
        elif shas and None not in shas:
            sheet_config_sha = str(next(iter(shas)))
    tennis_ids = {f.get("sofascore_event_id") for f in fixtures
                  if f.get("sport") == "tennis"}
    offer_has_tennis = any(
        o.get("sofascore_event_id") in tennis_ids and o.get("rungs")
        for o in offers)
    offer_has_winner = any(
        r.get("market") == MATCH_WON_FOR
        for o in offers for r in o.get("rungs") or [])
    football_ids = {f.get("sofascore_event_id") for f in fixtures
                    if f.get("sport") == "football"}
    offer_has_football = any(
        o.get("sofascore_event_id") in football_ids and o.get("rungs")
        for o in offers)
    offer_markets = {r.get("market") for o in offers for r in o.get("rungs") or []}
    offer_has_score = bool(offer_markets & set(SCORE_MARKETS))
    offer_has_set_not = SET_SCORE_NOT in offer_markets
    priced, open_n, oldest, newest = observe_offer(
        fixtures, offers, fs.load(run), now)
    sports = ({s: observe_sport(runs_dir, s, date, now) for s in SPORTS}
              if epochs.sports_on_coupon(date, now) else {})
    c06 = run / "06_coupon.json"
    inputs = [p for p in (sheet_path, run / "vetoes.json", run / "reads.json")
              if p.exists()]
    coupon06_stale = not c06.exists() or any(
        p.stat().st_mtime > c06.stat().st_mtime for p in inputs)
    return DayState(
        date=date, now=now, price_max_age=price_max_age,
        has_fixtures=fixtures_path.exists(), has_sheet=sheet_path.exists(),
        has_offer=offer_path.exists(), sheet_epoch=sheet_ep,
        sheet_link_shared=sheet_link_shared,
        sheet_dispersion=sheet_dispersion,
        sheet_cards=sheet_cards,
        sheet_k=sheet_k,
        sheet_tennis_table=sheet_tennis_table,
        sheet_opponent=sheet_opponent,
        sheet_game_state=markers[epochs.GAME_STATE_MARKER],
        sheet_rated_scope=markers[epochs.FOOTBALL_RATED_SCOPE_MARKER],
        sheet_venue_prior=markers[epochs.FOOTBALL_VENUE_PRIOR_MARKER],
        sheet_season_phase=markers[epochs.SEASON_PHASE_MARKER],
        sheet_rating_weight=markers[epochs.FOOTBALL_RATING_WEIGHT_MARKER],
        sheet_tennis_set=markers[epochs.TENNIS_SET_RATING_PRICES_MARKER],
        sheet_cup_strength=markers[epochs.FOOTBALL_CUP_STRENGTH_MARKER],
        sheet_sample_cup=markers[epochs.SAMPLE_CUP_STRENGTH_MARKER],
        sheet_goals_stretch=markers[epochs.FOOTBALL_GOALS_STRETCH_MARKER],
        sheet_count_stretch=markers[epochs.FOOTBALL_COUNT_STRETCH_MARKER],
        sheet_player_stretch=markers[epochs.FOOTBALL_PLAYER_STRETCH_MARKER],
        sheet_referee=markers[epochs.FOOTBALL_REFEREE_MARKER],
        sheet_player_share=markers[epochs.FOOTBALL_PLAYER_SHARE_MARKER],
        sheet_closeness_stretch=markers[
            epochs.FOOTBALL_CLOSENESS_STRETCH_MARKER],
        sheet_tennis_aces=markers[epochs.TENNIS_ACES_OPPONENT_MARKER],
        sheet_config_sha=sheet_config_sha,
        config_sha=sheet_config.fingerprint(),
        offer_has_tennis=offer_has_tennis,
        offer_has_winner=offer_has_winner,
        sheet_has_winner=sheet_has_winner,
        offer_has_football=offer_has_football,
        offer_has_score=offer_has_score,
        sheet_has_score=sheet_has_score,
        offer_has_set_not=offer_has_set_not,
        sheet_has_set_not=sheet_has_set_not,
        offer_fixtures=priced, open_fixtures=open_n,
        oldest_open_rung=oldest, newest_rung=newest, sports=sports,
        has_sport_fixtures=(run / si.FIXTURES_FILE).exists(),
        coupon06_stale=coupon06_stale,
        referee_now_known=referee_now_known(runs_dir, date, now, db_path),
    )


# --- the plan ----------------------------------------------------------------


def _pipeline(date: str, stage: str, run_id: str) -> tuple[str, ...]:
    return (PY, "scripts/sofa/run_pipeline.py", "--date", date, "--only", stage,
            "--run-id", run_id)


def shadow_horizon_h(now: datetime, farthest: datetime | None) -> float:
    """A horizon that reaches the farthest open start (never below the
    default), rounded up to a quarter hour, plus one quarter for the run."""
    if farthest is None:
        return SHADOW_DEFAULT_HORIZON_H
    hours = (farthest - now).total_seconds() / 3600
    return max(SHADOW_DEFAULT_HORIZON_H, math.ceil(hours * 4) / 4 + 0.25)


def build_plan(state: DayState, run_id: str = "rebuild",
               skip_audits: bool = False) -> Plan:
    d, now = state.date, state.now
    stats_only = epochs.stats_only(d, now)
    on_coupon = epochs.sports_on_coupon(d, now)
    plan = Plan(d, epochs.epoch_name(d, now), on_coupon)
    if not state.has_fixtures:
        plan.refusal = ("02_fixtures.json missing: no stage can name a fixture "
                        "- the day needs /sofa-day, not a rebuild")
        return plan
    if not state.has_sheet:
        plan.refusal = ("05_sheet.json missing: nothing to rebuild - the day "
                        "needs /sofa-day")
        return plan

    # 1a. the football / tennis price
    limit = state.price_max_age
    # D2: the switch came on after OFFER read the day - re-read it once
    winner_on = epochs.tennis_match_winner(d, now) and state.offer_has_tennis
    winner_offer_stale = winner_on and not state.offer_has_winner
    # the score markets / set complements came on after OFFER read the day
    # (2026-10-16 07:46Z, into the built day) - re-read it once
    score_on = epochs.football_score_markets(d, now) and state.offer_has_football
    set_not_on = epochs.tennis_set_complements(d, now) and state.offer_has_tennis
    score_offer_stale = ((score_on and not state.offer_has_score)
                         or (set_not_on and not state.offer_has_set_not))
    if state.open_fixtures == 0:
        if not state.has_offer:
            plan.refusal = ("04_offer.json missing and no fixture is still open: "
                            "nothing to price it from")
            return plan
        plan.notes.append(
            f"DAY_OVER football/tennis: none of {state.offer_fixtures} priced "
            "fixtures can still be bet - no OFFER refresh; the prices are "
            "historical and every price gate downstream refuses them "
            "(correct behaviour)")
    elif not state.has_offer or state.oldest_open_rung is None:
        plan.steps.append(Step(
            "OFFER", (PY, "scripts/sofa/run_offer.py", "--date", d,
                      "--min-minutes-to-kickoff", str(OFFER_MIN_MINUTES_TO_KICKOFF)),
            "04_offer.json missing"))
    else:
        age = now - state.oldest_open_rung
        trigger = limit - OFFER_REFRESH_MARGIN
        if age > trigger:
            plan.steps.append(Step(
                "OFFER", (PY, "scripts/sofa/run_offer.py", "--date", d,
                          "--min-minutes-to-kickoff",
                          str(OFFER_MIN_MINUTES_TO_KICKOFF)),
                f"oldest price of {state.open_fixtures} open fixtures is "
                f"{_age_min(now, state.oldest_open_rung)} old > "
                f"{trigger.total_seconds() / 60:.0f} min (CONFIDENCE STALE_PRICE "
                f"at {limit.total_seconds() / 60:.0f} min, minus the rebuild's "
                "margin)"))
        elif winner_offer_stale:
            plan.steps.append(Step(
                "OFFER", (PY, "scripts/sofa/run_offer.py", "--date", d,
                          "--min-minutes-to-kickoff",
                          str(OFFER_MIN_MINUTES_TO_KICKOFF)),
                "04_offer.json carries no tennis winner rung: OFFER reads "
                "\"Zwycięzca\" (epochs.tennis_match_winner)"))
        elif score_offer_stale:
            plan.steps.append(Step(
                "OFFER", (PY, "scripts/sofa/run_offer.py", "--date", d,
                          "--min-minutes-to-kickoff",
                          str(OFFER_MIN_MINUTES_TO_KICKOFF)),
                "04_offer.json carries no football score-market / tennis "
                "set_score_not rung: OFFER reads them "
                "(epochs.football_score_markets / tennis_set_complements)"))
        else:
            plan.notes.append(
                "OFFER fresh: oldest open price "
                f"{_age_min(now, state.oldest_open_rung)} old <= "
                f"{trigger.total_seconds() / 60:.0f} min")

    # 1b. the measured sports' prices and identities
    bridge_planned = False
    if on_coupon:
        refreshed = False
        shadow = [state.sports.get(s, SportState(s)) for s in SHADOW_SPORTS]
        sport_trigger = sport_day.MAX_PRICE_AGE - SPORT_REFRESH_MARGIN

        def stale(s: SportState) -> bool:
            return (s.oldest_open_price is not None
                    and now - s.oldest_open_price > sport_trigger)

        open_shadow = [s for s in shadow if s.open_events]
        if not open_shadow:
            plan.notes.append(
                "DAY_OVER hockey/basketball/volleyball: no open event on file - "
                "no SHADOW refresh")
        else:
            why = [f"{s.sport} oldest open price {_age_min(now, s.oldest_open_price)}"
                   f" > {sport_trigger.total_seconds() / 60:.0f} min"
                   for s in open_shadow if stale(s)]
            why += [f"{s.sport} {s.lagging_events} open events skipped by the "
                    f"last snapshot (start beyond its {SHADOW_DEFAULT_HORIZON_H:g} h "
                    "horizon)" for s in open_shadow if s.lagging_events]
            if why:
                farthest = max(s.farthest_open_kickoff for s in open_shadow
                               if s.farthest_open_kickoff is not None)
                horizon = shadow_horizon_h(now, farthest)
                plan.steps.append(Step(
                    "SHADOW", (PY, "scripts/sofa/run_shadow.py", "--date", d,
                               "--horizon-h", f"{horizon:g}"),
                    "; ".join(why) + f"; horizon {horizon:g} h reaches the "
                    f"farthest open start {_z(farthest)}", soft=True))
                refreshed = True
            else:
                plan.notes.append("SHADOW fresh: every open event priced within "
                                  f"{sport_trigger.total_seconds() / 60:.0f} min")
        cs2 = state.sports.get("cs2", SportState("cs2"))
        if not cs2.open_events:
            plan.notes.append("DAY_OVER cs2: no open event on file - no CS2 refresh")
        elif stale(cs2):
            plan.steps.append(Step(
                "CS2", _pipeline(d, "CS2", run_id),
                f"cs2 oldest open price {_age_min(now, cs2.oldest_open_price)} > "
                f"{sport_trigger.total_seconds() / 60:.0f} min", soft=True))
            refreshed = True
        else:
            plan.notes.append("CS2 fresh")
        if refreshed or not state.has_sport_fixtures:
            plan.steps.append(Step(
                "BRIDGE", (PY, "scripts/sofa/ensure_bridge.py"),
                "SPORT_IDENTITY and FIXTURE_CHECK ask Sofascore", soft=True))
            bridge_planned = True
            plan.steps.append(Step(
                "SPORT_IDENTITY", _pipeline(d, "SPORT_IDENTITY", run_id),
                "a fresh sport snapshot: pin the new events' Sofascore ids"
                if refreshed else "sport_fixtures.json missing", soft=True))

    # 2. SHEET only when CONFIDENCE would refuse it, or when the rating's
    # link rule of this build is not the one the sheet was rated under
    epoch_stale = stats_only and state.sheet_epoch != epochs.STATS_ONLY
    link_stale = (epochs.link_shared_league(d, now)
                  and not state.sheet_link_shared)
    dispersion_stale = (epochs.count_dispersion_enabled(d, now)
                        and not state.sheet_dispersion)
    cards_stale = (epochs.cards_correlation_enabled(d, now)
                   and not state.sheet_cards)
    tennis_table_stale = (epochs.tennis_scoped_table_enabled(d, now)
                          and not state.sheet_tennis_table)
    k_stale = (epochs.per_market_k_enabled(d, now) and not state.sheet_k)
    # a sheet without the row while the offer has (or is about to have) the
    # rung; a day Superbet posts no winner on does not re-run SHEET forever
    winner_stale = (winner_on and not state.sheet_has_winner
                    and (state.offer_has_winner or "OFFER" in plan.names()))
    # the same for the score markets / set complements (SHEET prices them
    # from the rating alone)
    score_stale = (
        (score_on and not state.sheet_has_score
         and (state.offer_has_score or "OFFER" in plan.names()))
        or (set_not_on and not state.sheet_has_set_not
            and (state.offer_has_set_not or "OFFER" in plan.names())))
    opponent_stale = (epochs.sample_opponent_correction(d, now)
                      and not state.sheet_opponent)
    audit_stale = audit_sheet_stale(state)
    # D7: a referee named since SHEET (RESOLVE / an earlier FIXTURE_CHECK);
    # one this rebuild's FIXTURE_CHECK names is after_fixture_check's
    referee_stale = (epochs.football_referee(d, now)
                     and bool(state.referee_now_known))
    sheet_rebuilt = (epoch_stale or link_stale or dispersion_stale or cards_stale
                     or k_stale
                     or tennis_table_stale or opponent_stale or winner_stale
                     or score_stale or bool(audit_stale) or referee_stale)
    if epoch_stale:
        plan.steps.append(Step(
            "SHEET", _pipeline(d, "SHEET", run_id),
            f"05_sheet.json epoch {state.sheet_epoch!r} is not {epochs.STATS_ONLY!r}:"
            " CONFIDENCE refuses it on a stats-only build"))
    elif link_stale:
        plan.steps.append(Step(
            "SHEET", _pipeline(d, "SHEET", run_id),
            "05_sheet.json rated under the old link rule: the football rating "
            "links only through a shared league (epochs.link_shared_league)"))
    elif dispersion_stale:
        plan.steps.append(Step(
            "SHEET", _pipeline(d, "SHEET", run_id),
            "05_sheet.json priced from the sample variance: football counts "
            "read the dispersion fitted on the history "
            "(epochs.count_dispersion_enabled)"))
    elif cards_stale:
        plan.steps.append(Step(
            "SHEET", _pipeline(d, "SHEET", run_id),
            "05_sheet.json priced with independent cards sides: the cards "
            "joints read the measured residual correlation "
            "(epochs.cards_correlation_enabled)"))
    elif k_stale:
        plan.steps.append(Step(
            "SHEET", _pipeline(d, "SHEET", run_id),
            "05_sheet.json priced with the sport's K_CENTRE: football "
            "centres read the K of their own market "
            "(epochs.per_market_k_enabled)"))
    elif tennis_table_stale:
        plan.steps.append(Step(
            "SHEET", _pipeline(d, "SHEET", run_id),
            "05_sheet.json priced from the pooled tennis neighbour table: "
            "tennis reads the table cut by tier x gender "
            "(epochs.tennis_scoped_table_enabled)"))
    elif opponent_stale:
        plan.steps.append(Step(
            "SHEET", _pipeline(d, "SHEET", run_id),
            "05_sheet.json priced from the raw sample: football samples are "
            "corrected for their opponents and domain "
            "(epochs.sample_opponent_correction)"))
    elif winner_stale:
        plan.steps.append(Step(
            "SHEET", _pipeline(d, "SHEET", run_id),
            "05_sheet.json has no tennis winner row: SHEET prices "
            "match_won_for from the rating (epochs.tennis_match_winner)"))
    elif score_stale:
        plan.steps.append(Step(
            "SHEET", _pipeline(d, "SHEET", run_id),
            "05_sheet.json has no football score-market / tennis "
            "set_score_not row: SHEET prices them from the rating "
            "(epochs.football_score_markets / tennis_set_complements)"))
    elif audit_stale:
        plan.steps.append(Step(
            "SHEET", _pipeline(d, "SHEET", run_id),
            "05_sheet.json priced before a switch now on: "
            + "; ".join(audit_stale)))
    elif referee_stale:
        plan.steps.append(referee_sheet_step(
            d, state.referee_now_known, run_id, "on the DB"))
    else:
        plan.notes.append(f"SHEET kept: built under {state.sheet_epoch!r}")
    if (state.sheet_config_sha is not None and state.config_sha is not None
            and state.sheet_config_sha != state.config_sha):
        plan.notes.append(
            f"CONFIG_CHANGED: 05_sheet.json priced on fitted config "
            f"{state.sheet_config_sha}, the files are now {state.config_sha} "
            "(a refit install or a table fit, bet.sofa.sheet_config) - "
            + ("SHEET re-runs on them for another reason above"
               if sheet_rebuilt else
               "SHEET kept: an install never goes into a built day unless "
               "the operator says so; then run_pipeline.py --only SHEET by "
               "hand before the rebuild"))
    if not skip_audits and (sheet_rebuilt or state.coupon06_stale):
        plan.steps.append(Step(
            "COUPON", _pipeline(d, "COUPON", run_id),
            "06_coupon.json older than the sheet / vetoes / reads: keeps "
            "audit_coupon in step (the priced selector, not the coupon)",
            soft=True))

    # 3. the coupon
    if stats_only:
        if not bridge_planned:
            plan.steps.append(Step(
                "BRIDGE", (PY, "scripts/sofa/ensure_bridge.py"),
                "FIXTURE_CHECK asks Sofascore", soft=True))
        plan.steps.append(Step(
            "FIXTURE_CHECK", _pipeline(d, "FIXTURE_CHECK", run_id),
            "fresh /event start and status before CONFIDENCE (K12/K14); "
            "no bridge = UNVERIFIED, nothing refused", soft=True))
    plan.steps.append(Step(
        "CONFIDENCE", (PY, "scripts/sofa/run_confidence.py", "--date", d),
        "football / tennis -> 08_confidence.json"))
    if on_coupon:
        plan.steps.append(Step(
            "SPORT_CONFIDENCE", _pipeline(d, "SPORT_CONFIDENCE", run_id),
            "measured sports -> 08_confidence_sports.json"))
    if stats_only:
        plan.steps.append(Step(
            "COUPON_ASSEMBLY", (PY, "scripts/sofa/build_coupon.py", "--date", d),
            "the one coupon -> 11_coupon.json"))
    else:
        plan.notes.append("old epoch: the PDF renders 08_confidence.json, no "
                          "FIXTURE_CHECK / COUPON_ASSEMBLY")
    plan.steps.append(Step(
        "PDF", (PY, "scripts/sofa/build_coupon_pdf.py", "--date", d),
        "KUPON_<d>.pdf + KUPON_<d>.html + 12_printed.json"))
    if skip_audits:
        plan.notes.append("AUDITS SKIPPED (--skip-audits): audit_variants and "
                          "audit_coupon were not run")
    else:
        plan.steps.append(Step(
            "AUDIT_VARIANTS", (PY, "scripts/sofa/audit_variants.py", "--date", d),
            "C1-C3 / U1-U3 on the coupon artifact"))
        plan.steps.append(Step(
            "AUDIT_COUPON", (PY, "scripts/sofa/audit_coupon.py", "--date", d),
            "06_coupon.json audit (the priced selector, not the coupon)"))
    return plan


def state_summary(state: DayState) -> dict[str, Any]:
    """The observation, JSON-ready, for the dry run and the final summary."""
    return {
        "now": _z(state.now),
        "offer_fixtures": state.offer_fixtures,
        "open_fixtures": state.open_fixtures,
        "oldest_open_rung": _z(state.oldest_open_rung),
        "newest_rung": _z(state.newest_rung),
        "sheet_epoch": state.sheet_epoch,
        "sheet_config_sha": state.sheet_config_sha,
        "config_sha": state.config_sha,
        "sports": {
            k: {"events": s.events, "open": s.open_events,
                "oldest_open_price": _z(s.oldest_open_price),
                "farthest_open_kickoff": _z(s.farthest_open_kickoff),
                "lagging": s.lagging_events}
            for k, s in state.sports.items()
        },
    }
