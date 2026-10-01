"""Experimental per-sport coupons for CS2, hockey, basketball and volleyball.

The operator's experiment, ordered 2026-09-30: one coupon per measured sport,
built beside the measurement and never beside the coupon. Four facts decide
what such a coupon can honestly be:

- Hockey, basketball and volleyball have no model at all - no SAMPLES, no
  SHEET, no CONFIDENCE. The only probability on record is Superbet's own
  price with the margin taken out (`fair_p`, the pipeline's devig, over the
  market's whole outcome group - two sides, a 1X2, or an exact-score set).
- CS2's engine needs Sofascore team ids that exist only after the series has
  been resolved at settle time, and measured about the base rate; a model
  disagreeing with the price is an anti-signal in every sofa sport measured.
- The first settled hockey day (2026-09-29, 1,138 sides) matched the price
  within noise and lost -7.0% flat at a 8.3% margin.
- Short prices lose least (93.5k football/tennis rows: -3.8% at 1.00-1.15,
  -32.1% above 3.00).

So the selector is price-only and says so: per event, the one side whose
devigged probability clears FLOOR on a market whose margin is at most
MAX_OVERROUND, ranked by `fair_p * odds` - the share of a fair price the
side pays back, i.e. the cheapest side on the board. Nothing here claims an
edge; expected value at the fair price is negative by the margin, and the
coupon prints that beside every leg.

The day's window is Warsaw's: from the build to 06:00 Warsaw the next
morning, read from the day's snapshot file AND the next day's (a 01:00
Warsaw NHL game is 23:00Z or later and lands in D+1's file). A leg that has
started stays on the coupon when it is rebuilt later in the day (`locked`),
so the day's record never loses what was printed.

A leg is graded from the stored RESULT (settled.json), not by looking its
line up among the measurement's graded rows: those hold only the lines of the
last pre-start snapshot, and a line Superbet took down after the coupon
printed it would otherwise never be graded.

Hard boundaries, each guarded by a test:

- Files go to the measurement's own day directory (runs/sofa/cs2/<d>/,
  runs/sofa/shadow/<sport>/<d>/), never to runs/sofa/<d>/, so no stage that
  builds the real coupon can read them; the result is never pooled with it.
- Singles only. No combined price is ever computed or printed.
- No stake.
- Player lines are left out: none has a settled record of 30 games yet.
- Every constant below is chosen, not fitted, and is written into the
  artifact as UNFITTED_CONSTANTS.
"""

from __future__ import annotations

import fcntl
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from bet.sofa import cs2, shadow
from bet.sofa.confidence import MAX_OVERROUND, MIN_ODDS_FOR_CEILING
from bet.sofa.resolve import NAME_MATCH_THRESHOLD

SportKey = Literal["cs2", "hockey", "basketball", "volleyball"]
SPORT_KEYS: tuple[SportKey, ...] = ("cs2", "hockey", "basketball", "volleyball")

FLOOR = 0.70  # the official coupon's confidence floor, applied to fair_p
MIN_ODDS = MIN_ODDS_FOR_CEILING  # 1/0.9202, as the official coupon
MAX_LEGS = 10
KICKOFF_MARGIN = timedelta(minutes=15)  # as coupon/confidence
MAX_PRICE_AGE = timedelta(hours=3)
DAY_END_HOUR_WARSAW = 6  # the coupon of D covers kickoffs until 06:00 D+1
WARSAW = ZoneInfo("Europe/Warsaw")
# A leg nobody can grade is not a measurement (2026-10-01). Superbet lists
# events Sofascore never has: volleyball 30 of 50 settled events were
# NOT_ON_SOFASCORE on 09-29/30, every club friendly among them (6/6), and the
# 09-30 volleyball coupon printed 8 legs of which 6 can never be graded; CS2's
# "Winners series 1x1" went 30/30. So the coupon leaves out a friendly, and a
# tournament the measurement has already failed to find on Sofascore in at
# least UNSETTLEABLE_SHARE of UNSETTLEABLE_MIN_EVENTS or more events over the
# last UNSETTLEABLE_LOOKBACK_DAYS settled days. An unseen tournament is
# allowed: there is no evidence against it yet.
FRIENDLY_MARKERS = ("towarzysk",)  # Superbet's "Mecze towarzyskie"
UNSETTLEABLE_SHARE = 0.5
UNSETTLEABLE_MIN_EVENTS = 2
# ...and a tournament whose every seen event so far was unsettleable, from
# this many on (audit 2026-10-01: the 10-01 volleyball coupon printed two
# legs of "Brazylia - Paulista U19" and one of "Szwecja - Puchar Ligi", each
# with a single earlier event, not found - 1/1 slipped under the >=2 rule).
UNSETTLEABLE_ALL_MIN_EVENTS = 1
UNSETTLEABLE_LOOKBACK_DAYS = 14
NOT_FOUND_STATES = frozenset({"NOT_ON_SOFASCORE"})
UNFITTED_CONSTANTS = (
    "FLOOR",
    "MAX_OVERROUND",
    "MAX_LEGS",
    "MAX_PRICE_AGE",
    "RANK_BY_FAIR_P_TIMES_ODDS",
    "UNSETTLEABLE_SHARE",
    "UNSETTLEABLE_MIN_EVENTS",
    "UNSETTLEABLE_ALL_MIN_EVENTS",
)

COUPON_FILE = "sport_coupon.json"
COUPON_MD = "sport_coupon.md"
BUILDS_FILE = "sport_coupon_builds.jsonl"
VETOES_FILE = "vetoes.json"

SPORT_PL: dict[SportKey, str] = {
    "cs2": "CS2",
    "hockey": "HOKEJ",
    "basketball": "KOSZYKÓWKA",
    "volleyball": "SIATKÓWKA",
}
PDF_SUFFIX: dict[SportKey, str] = {
    "cs2": "_CS2",
    "hockey": "_HOKEJ",
    "basketball": "_KOSZYKOWKA",
    "volleyball": "_SIATKOWKA",
}

# What each family is, in the operator's language. A test holds this complete
# against shadow.MARKETS and cs2.FAMILIES.
FAMILY_PL: dict[SportKey, dict[str, str]] = {
    "hockey": {
        "winner": "zwycięzca (z dogrywką i karnymi)",
        "total": "liczba goli (czas podstawowy)",
        "team_total": "liczba goli drużyny (czas podstawowy)",
        "handicap": "handicap (czas podstawowy)",
        "period_total": "liczba goli",
        "period_team_total": "liczba goli drużyny",
        "period_handicap": "handicap",
        "period_dnb": "remis bez zakładu",
        "result_1x2": "1X2 (czas podstawowy)",
        "period_1x2": "1X2",
    },
    "basketball": {
        "winner": "zwycięzca (z dogrywką)",
        "total": "liczba punktów (z dogrywką)",
        "team_total": "liczba punktów drużyny (z dogrywką)",
        "handicap": "handicap (z dogrywką)",
        "h1_total": "1. połowa - liczba punktów",
        "h1_team_total": "1. połowa - liczba punktów drużyny",
        "h1_handicap": "1. połowa - handicap",
        "h1_dnb": "1. połowa - remis bez zakładu",
        "h2_total": "2. połowa - liczba punktów",
        "h2_team_total": "2. połowa - liczba punktów drużyny",
        "h2_handicap": "2. połowa - handicap",
        "h2_dnb": "2. połowa - remis bez zakładu",
        "quarter_total": "liczba punktów",
        "quarter_team_total": "liczba punktów drużyny",
        "quarter_handicap": "handicap",
        "quarter_dnb": "remis bez zakładu",
        "result_1x2": "1X2 (czas podstawowy)",
        "h1_1x2": "1. połowa - 1X2",
        "h2_1x2": "2. połowa - 1X2",
        "quarter_1x2": "1X2",
        "odd_even": "parzystość punktów (z dogrywką)",
        "team_odd_even": "parzystość punktów drużyny (z dogrywką)",
    },
    "volleyball": {
        "winner": "zwycięzca meczu",
        "sets_total": "liczba setów",
        "set_handicap": "handicap setów",
        "points_total": "liczba punktów w meczu",
        "points_handicap": "handicap punktów",
        "set_winner": "zwycięzca seta",
        "set_points_total": "liczba punktów w secie",
        "exact_sets": "dokładny wynik w setach",
        "points_odd_even": "parzystość punktów w meczu",
        "set_points_odd_even": "parzystość punktów w secie",
        "set_extra_points": "set rozstrzygnięty na przewagi",
    },
    "cs2": {
        "match_winner": "zwycięzca meczu",
        "maps_total": "liczba map",
        "maps_handicap": "handicap map",
        "team_maps": "liczba map drużyny",
        "rounds_total": "liczba rund (z dogrywką)",
        "rounds_handicap": "handicap rund (z dogrywką)",
        "team_rounds": "liczba rund drużyny (z dogrywką)",
        "map_winner": "zwycięzca mapy",
        "map_rounds_total": "liczba rund (z dogrywką)",
        "map_rounds_handicap": "handicap rund (z dogrywką)",
        "map_team_rounds": "liczba rund drużyny (z dogrywką)",
        "team_kills": "liczba zabójstw drużyny (z dogrywką)",
        "map_rounds_odd_even": "parzystość rund (z dogrywką)",
        "exact_maps": "dokładny wynik w mapach",
    },
}
PERIOD_PL = {"hockey": "tercja", "basketball": "kwarta", "volleyball": "set"}
SIDE_PL = {"ODD": "nieparzysta", "EVEN": "parzysta", "YES": "tak", "NO": "nie"}


def file_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def pdf_matches(doc: dict[str, Any], json_path: Path, pdf_path: Path) -> str | None:
    """Why this PDF is not the one this JSON was printed as, or None.

    Since 2026-09-30 the JSON carries `pdf_sha256`, and only an exact match
    passes. A JSON from before then has no hash; its PDF was written in the
    same run, just before it, so it passes when it is at most LEGACY_PDF_SKEW
    older - and never when it is newer by more than that either way.
    """
    if not pdf_path.exists():
        return f"NO_PDF: {pdf_path.name}"
    want = doc.get("pdf_sha256")
    if want:
        if file_sha256(pdf_path) == want:
            return None
        return f"PDF_MISMATCH: {pdf_path.name}"
    skew = json_path.stat().st_mtime - pdf_path.stat().st_mtime
    if abs(skew) > LEGACY_PDF_SKEW_S:
        return f"PDF_NOT_FROM_THIS_BUILD: {pdf_path.name} ({skew:+.0f} s)"
    return None


LEGACY_PDF_SKEW_S = 120.0


def day_dir(runs_dir: str, sport: SportKey, date: str) -> Path:
    """The measurement's own day directory - never runs/sofa/<date>/."""
    if sport == "cs2":
        return cs2.cs2_day_dir(runs_dir, date)
    return shadow.shadow_day_dir(runs_dir, sport, date)


def pdf_name(sport: SportKey, date: str) -> str:
    return f"KUPON_{date}{PDF_SUFFIX[sport]}.pdf"


def next_date(date: str) -> str:
    return (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )


def day_end(date: str) -> datetime:
    """06:00 Warsaw on the morning after `date`."""
    d = datetime.strptime(next_date(date), "%Y-%m-%d")
    return d.replace(hour=DAY_END_HOUR_WARSAW, tzinfo=WARSAW)


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def is_player_family(family: str) -> bool:
    return family.startswith("player_")


def read_snapshots(
    path: Path, upto_lines: int | None = None
) -> tuple[list[dict[str, Any]], int, int]:
    """(records, lines in the file, unreadable lines).

    Read under a shared lock (run_shadow appends under an exclusive one), and
    a line that does not parse - a crash mid-append - is skipped and counted,
    never fatal: one torn line once stopped every later build of its sport.
    `upto_lines` reads only the file's first N lines - what a build saw.
    """
    if not path.exists():
        return [], 0, 0
    with path.open(encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_SH)
        try:
            text = fh.read()
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
    lines = text.splitlines()
    # Only whole lines: a last line with no newline is an append in progress
    # (or torn). Counting it would let a replay read a record the build never
    # saw once the write completes.
    if lines and not text.endswith("\n"):
        lines = lines[:-1]
    if upto_lines is not None:
        lines = lines[:upto_lines]
    rows: list[dict[str, Any]] = []
    bad = 0
    for line in lines:
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            bad += 1
    return rows, len(lines), bad


def load_snapshots(path: Path, upto_lines: int | None = None) -> list[dict[str, Any]]:
    return read_snapshots(path, upto_lines)[0]


@contextmanager
def dir_lock(directory: Path) -> Iterator[None]:
    """One writer per sport directory at a time: two runners (or a runner and
    an operator) rebuilding the same coupon would otherwise interleave their
    JSON, PDF and build log."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".sport_coupon.lock").open("a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def latest_events(sport: SportKey, snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    if sport == "cs2":
        return dict(cs2.latest_pre_kickoff(snapshots))
    return dict(shadow.latest_pre_kickoff(snapshots))


def prev_date(date: str) -> str:
    return (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )


def _newest(ev: Any) -> datetime | None:
    return max((_utc(t) for t in ev.fetched_at.values()), default=None)


def day_events(
    runs_dir: str,
    sport: SportKey,
    date: str,
    stats: dict[str, Any] | None = None,
    upto_lines: dict[str, int] | None = None,
) -> tuple[dict[str, Any], int]:
    """The events of D's and D+1's snapshot files, each tagged with the file
    (`source_date`) its result will be settled into. An event in both files
    (a game moved across midnight UTC) keeps the record with the newer price.
    Returns (events, snapshot records read); `stats` gets each file's line
    count - what a replay must read - and the unreadable lines."""
    out: dict[str, Any] = {}
    read = 0
    lines: dict[str, int] = {}
    bad = 0
    for source in (date, next_date(date)):
        snaps, n_lines, n_bad = read_snapshots(
            day_dir(runs_dir, sport, source) / cs2.SNAPSHOTS_FILE,
            None if upto_lines is None else upto_lines.get(source, 0),
        )
        read += len(snaps)
        lines[source] = n_lines
        bad += n_bad
        for eid, ev in latest_events(sport, snaps).items():
            ev.source_date = source
            have = out.get(eid)
            if have is None or (_newest(ev) or datetime.min.replace(tzinfo=WARSAW)) > (
                _newest(have) or datetime.min.replace(tzinfo=WARSAW)
            ):
                out[eid] = ev
    if stats is not None:
        stats["snapshot_lines"] = lines
        stats["unreadable_snapshot_lines"] = bad
    return out, read


def describe(sport: SportKey, leg: dict[str, Any]) -> str:
    """One line of the coupon in Polish: market, then the side."""
    fam = str(leg["family"])
    label = FAMILY_PL[sport].get(fam, fam)
    period = int(leg.get("map_nr") or leg.get("period") or 0)
    if period:
        unit = "mapa" if sport == "cs2" else PERIOD_PL[sport]
        label = f"{period}. {unit} - {label}"
    team1, team2 = str(leg["team1"]), str(leg["team2"])
    subject = str(leg.get("subject") or "")
    subject = {"T1": team1, "T2": team2}.get(subject, subject)
    if subject:
        label = f"{subject} - {label}"
    side, value = str(leg["side"]), leg.get("line")
    if side == "OVER":
        return f"{label}: powyżej {value:g}"
    if side == "UNDER":
        return f"{label}: poniżej {value:g}"
    if side in SIDE_PL:
        return f"{label}: {SIDE_PL[side]}"
    if side == "DRAW":
        return f"{label}: remis"
    score = cs2.exact_score(side)
    if score is not None:
        return f"{label}: {team1} {score[0]}:{score[1]} {team2}"
    team = team1 if side == "T1" else team2
    if value is None:
        return f"{label}: {team}"
    hcp = float(value) if side == "T1" else -float(value)
    return f"{label}: {team} ({hcp:+g})"


@dataclass(frozen=True)
class Rule:
    floor: float = FLOOR
    max_overround: float = MAX_OVERROUND
    min_odds: float = MIN_ODDS
    max_legs: int = MAX_LEGS

    def as_dict(self) -> dict[str, Any]:
        return {
            "floor": self.floor,
            "max_overround": self.max_overround,
            "min_odds": round(self.min_odds, 4),
            "max_legs": self.max_legs,
            "kickoff_margin_min": int(KICKOFF_MARGIN.total_seconds() // 60),
            "max_price_age_min": int(MAX_PRICE_AGE.total_seconds() // 60),
            "day_end": f"{DAY_END_HOUR_WARSAW:02d}:00 Europe/Warsaw, D+1",
            "rank": "fair_p * odds, then fair_p",
        }


def side_filter(
    fair_p: float | None, odds: float, margin: float, rule: Rule
) -> str | None:
    """Why a side cannot be a leg, or None if it can."""
    if fair_p is None:
        return "NO_DEVIG"
    if fair_p < rule.floor:
        return "BELOW_FLOOR"
    if odds < rule.min_odds:
        return "BELOW_MIN_ODDS"
    if margin > rule.max_overround:
        return "MARGIN_TOO_HIGH"
    if margin < 0:
        # the book never pays out more than it takes in: a negative margin is
        # a stale or misread group, not a price
        return "NEGATIVE_MARGIN"
    return None


# Families a leg cannot come from: the coupon grades from the stored result,
# and settled.json keeps only each map's rounds, not the players' kills.
EXCLUDED_FAMILIES = frozenset({"team_kills"})


# Keys a veto may narrow itself by; an absent key matches anything. Without
# any, the veto removes the whole event.
VETO_KEYS = ("family", "side", "market_id", "period", "map_nr", "subject", "line")


VETO_FIELDS = frozenset({"superbet_event_id", "reason", "source", *VETO_KEYS})


def veto_matches(v: dict[str, Any], leg: dict[str, Any]) -> bool:
    """A veto with a key it does not know (a typo, "event_id") matches
    nothing - it is reported as unmatched, never silently widened."""
    if set(v) - VETO_FIELDS:
        return False
    if str(v.get("superbet_event_id")) != str(leg["superbet_event_id"]):
        return False
    return all(v[k] == leg.get(k) for k in VETO_KEYS if v.get(k) is not None)


def _vetoed(leg: dict[str, Any], vetoes: list[dict[str, Any]]) -> str | None:
    for v in vetoes:
        if veto_matches(v, leg):
            return str(v.get("reason") or "veto")
    return None


def _rank(leg: dict[str, Any]) -> tuple[float, float, float, str, str]:
    """Best first when sorted descending: the cheapest side (unrounded), then
    the likelier, then the lower margin, then - so that a tie at the cut is
    never decided by file order - the earlier kickoff and the lower event id
    (both inverted, being strings)."""
    return (
        leg["_x"] if "_x" in leg else leg["fair_p"] * leg["odds"],
        leg.get("_p", leg["fair_p"]),
        -float(leg.get("overround") or 0.0),
        _inv(str(leg.get("kickoff_utc") or "")),
        _inv(str(leg["superbet_event_id"]).rjust(12, "0")),
    )


def _inv(text: str) -> str:
    return "".join(chr(0x10FFFF - ord(c)) for c in text)


def _bump(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def is_friendly(tournament: str | None) -> bool:
    folded = (tournament or "").casefold()
    return any(marker in folded for marker in FRIENDLY_MARKERS)


def unsettleable_tournaments(
    runs_dir: str, sport: SportKey, date: str
) -> dict[str, str]:
    """Tournaments the measurement could not find on Sofascore, from the
    settled days strictly before `date` - never the day itself, whose
    outcome is not known when its coupon is built. Value: "<n>/<total>"."""
    total: dict[str, int] = {}
    missing: dict[str, int] = {}
    day = date
    for _ in range(UNSETTLEABLE_LOOKBACK_DAYS):
        day = prev_date(day)
        settled = load_settled(runs_dir, sport, day)
        for ev in ((settled or {}).get("events") or {}).values():
            name = ev.get("tournament")
            if not name:
                continue
            total[name] = total.get(name, 0) + 1
            state = ev.get("state")
            if state in NOT_FOUND_STATES or ev.get("gave_up_on") in NOT_FOUND_STATES:
                missing[name] = missing.get(name, 0) + 1
    return {
        name: f"{missing.get(name, 0)}/{n}"
        for name, n in sorted(total.items())
        if (
            n >= UNSETTLEABLE_MIN_EVENTS
            and missing.get(name, 0) / n >= UNSETTLEABLE_SHARE
        )
        or (n >= UNSETTLEABLE_ALL_MIN_EVENTS and missing.get(name, 0) == n)
    }


def ungradeable_reason(
    tournament: str | None, unsettleable: dict[str, str] | None
) -> str | None:
    if is_friendly(tournament):
        return "friendly_tournament"
    if unsettleable and tournament in unsettleable:
        return "unsettleable_tournament"
    return None


def cs2_known_team_names(db_path: str) -> list[str]:
    """Every team name the CS2 series store (cs2_series) has seen, folded
    with cs2.esports_name. Read-only: opened mode=ro, so a coupon build can
    never write, lock or create the database; a missing DB or table is []."""
    import sqlite3

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        rows = conn.execute(
            "SELECT home_name FROM cs2_series UNION SELECT away_name FROM cs2_series"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return sorted({cs2.esports_name(str(r[0])) for r in rows if r[0]})


def cs2_unseen_team_events(
    events: dict[str, Any], known_names: list[str]
) -> dict[str, str]:
    """Superbet event id -> "unseen_team" for every CS2 event with a side
    the series store has never seen (cs2.esports_score above the pipeline's
    name threshold, as CS2_SETTLE matches). A team Sofascore has never
    listed is one CS2_SETTLE will not find either - the 09-30 "Winners
    series 1x1" went 30/30 NOT_ON_SOFASCORE. Computed once per build and
    recorded, so a replay refuses exactly what the build refused; an empty
    store refuses nothing (no evidence yet, as for an unseen tournament)."""
    if not known_names:
        return {}
    known = set(known_names)
    seen: dict[str, bool] = {}

    def is_known(name: str) -> bool:
        folded = cs2.esports_name(name)
        if folded not in seen:
            seen[folded] = folded in known or any(
                cs2.esports_score(folded, k) > NAME_MATCH_THRESHOLD
                for k in known_names
            )
        return seen[folded]

    return {
        str(ev.superbet_event_id): "unseen_team"
        for ev in events.values()
        if not (is_known(ev.team1) and is_known(ev.team2))
    }


def candidates(
    sport: SportKey,
    events: dict[str, Any],
    at: datetime,
    rule: Rule,
    counts: dict[str, int],
    until: datetime | None = None,
    check_clock: bool = True,
    since: datetime | None = None,
    unsettleable: dict[str, str] | None = None,
    refused_events: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Every side of every event in the window that the rule admits.

    The window is [max(at + KICKOFF_MARGIN, since), until): `since` is the
    previous day's `day_end`, so a night game belongs to one day's coupon
    only, however early the next one is built. Only the event's most recent
    snapshot is read - a line Superbet has taken down since is not a price -
    and it must be under MAX_PRICE_AGE. A side's probability is devigged over
    its whole outcome group; an incomplete group is no price. An event
    nobody will be able to grade (`ungradeable_reason`) is left out whole.
    """
    out: list[dict[str, Any]] = []
    for ev in events.values():
        kickoff = _utc(ev.kickoff_utc)
        if check_clock and kickoff - at < KICKOFF_MARGIN:
            _bump(counts, "started_or_too_close")
            continue
        if until is not None and kickoff >= until:
            _bump(counts, "after_day_end")
            continue
        if since is not None and kickoff < since:
            _bump(counts, "previous_days_window")
            continue
        if not ev.fetched_at:
            continue
        why_not = ungradeable_reason(ev.tournament, unsettleable)
        if sport == "cs2" and why_not is None:
            if not ev.tournament:
                # run_cs2 leaves the tournament None when Superbet's struct
                # fetch fails; neither the friendly nor the unsettleable gate
                # can read such an event, so it is refused, not waved through.
                why_not = "no_tournament"
            elif refused_events and str(ev.superbet_event_id) in refused_events:
                why_not = refused_events[str(ev.superbet_event_id)]
        if why_not is not None:
            _bump(counts, why_not)
            continue
        newest = max(ev.fetched_at.values(), key=_utc)
        if check_clock and at - _utc(newest) > MAX_PRICE_AGE:
            _bump(counts, "stale_price_event")
            continue
        current = {k: ln for k, ln in ev.sides.items() if ev.fetched_at[k] == newest}
        groups: dict[tuple[Any, ...], dict[str, Any]] = {}
        for key, line in current.items():
            groups.setdefault(key[:4], {})[line.side] = line
        for key, line in current.items():
            if is_player_family(line.family):
                _bump(counts, "player_line")
                continue
            if line.family in EXCLUDED_FAMILIES:
                _bump(counts, "ungradeable_family")
                continue
            group_odds = {s: ln.odds for s, ln in groups[key[:4]].items()}
            shape = (
                cs2.group_shape(line.family)
                if sport == "cs2"
                else shadow.group_shape(sport, line.market_id)
            )
            fair = cs2.group_fair(group_odds, shape)
            if fair is None:
                _bump(counts, "incomplete_group")
                continue
            fair_p = fair[line.side]
            margin = cs2.group_overround(group_odds)
            why = side_filter(fair_p, line.odds, margin, rule)
            if why is not None:
                _bump(counts, why)
                continue
            out.append(
                {
                    **line.as_dict(),
                    "group_odds": group_odds,
                    "fair_p": round(fair_p, 4),
                    "overround": round(margin, 4),
                    "fair_p_x_odds": round(fair_p * line.odds, 4),
                    "_x": fair_p * line.odds,
                    "_p": fair_p,
                    "match_name": ev.match_name,
                    "team1": ev.team1,
                    "team2": ev.team2,
                    "tournament": ev.tournament,
                    "kickoff_utc": ev.kickoff_utc,
                    "source_date": getattr(ev, "source_date", None),
                    "price_fetched_at_utc": newest,
                    "price_age_min": round((at - _utc(newest)).total_seconds() / 60),
                }
            )
    return out


def locked_legs(
    previous: dict[str, Any] | None,
    at: datetime,
    current_kickoff: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Legs of an earlier build of the same day that can no longer be
    replaced - started, or inside the kickoff margin. They stay on the coupon
    exactly as printed. The kickoff is the EARLIER of the printed one and the
    one the snapshots say now: a game moved forward and already in play is
    locked, not dropped from the record."""
    if not previous:
        return []
    now_ko = current_kickoff or {}
    out = []
    for leg in previous.get("legs", []):
        kickoff = _utc(leg["kickoff_utc"])
        moved = now_ko.get(str(leg["superbet_event_id"]))
        if moved is not None:
            kickoff = min(kickoff, _utc(moved))
        if kickoff - at < KICKOFF_MARGIN:
            out.append({**leg, "locked": True})
    return out


def select(
    sport: SportKey,
    cands: list[dict[str, Any]],
    vetoes: list[dict[str, Any]],
    rule: Rule,
    locked: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """One leg per event, the best-ranked unvetoed side; locked legs first,
    then the best new ones until max_legs.

    A veto on one side leaves the event's other sides in the running: it
    removes what it names, nothing more."""
    locked = locked or []
    taken = {leg["superbet_event_id"] for leg in locked}
    vetoed: list[dict[str, Any]] = []
    best: dict[str, dict[str, Any]] = {}
    for leg in cands:
        if leg["superbet_event_id"] in taken:
            continue
        why = _vetoed(leg, vetoes)
        if why is not None:
            vetoed.append({**leg, "veto": why})
            continue
        eid = leg["superbet_event_id"]
        if eid not in best or _rank(leg) > _rank(best[eid]):
            best[eid] = leg
    room = max(0, rule.max_legs - len(locked))
    ranked = sorted(best.values(), key=_rank, reverse=True)
    fresh = ranked[:room]
    if (
        0 < room < len(ranked)
        and _rank(ranked[room - 1])[:3] == _rank(ranked[room])[:3]
    ):
        for leg in fresh:
            if _rank(leg)[:3] == _rank(ranked[room])[:3]:
                leg["tie_at_cut"] = True
    for leg in fresh:
        leg["label"] = describe(sport, leg)
        leg.pop("_x", None)
        leg.pop("_p", None)
    chosen = [*locked, *fresh]
    chosen.sort(key=lambda leg: (leg["kickoff_utc"], leg["match_name"]))
    return chosen, vetoed


def unmatched_vetoes(
    vetoes: list[dict[str, Any]],
    cands: list[dict[str, Any]],
    event_ids: set[str],
) -> list[dict[str, Any]]:
    """Vetoes that name nothing - an event id not in the day's snapshots, or
    keys that match no candidate of an event that still has candidates.
    Printed, never dropped silently. A veto on an event that has since
    started, or has no candidate left, is spent, not wrong."""
    live = {c["superbet_event_id"] for c in cands}
    out = []
    for v in vetoes:
        eid = str(v.get("superbet_event_id"))
        if eid not in event_ids:
            out.append(v)
        elif eid in live and not any(veto_matches(v, c) for c in cands):
            out.append(v)
    return out


def load_vetoes(directory: Path) -> list[dict[str, Any]]:
    path = directory / VETOES_FILE
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = doc.get("vetoes", []) if isinstance(doc, dict) else doc
    return [r for r in rows if isinstance(r, dict) and r.get("superbet_event_id")]


def load_settled(runs_dir: str, sport: SportKey, date: str) -> dict[str, Any] | None:
    path = day_dir(runs_dir, sport, date) / cs2.SETTLED_FILE
    if not path.exists():
        return None
    doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return doc


# --- what the rule would have done on the settled days ---------------------------


def rule_history(
    runs_dir: str, sport: SportKey, dates: list[str], rule: Rule
) -> dict[str, Any]:
    """The rule replayed on settled days, one side per event, chosen BEFORE
    the outcome is looked at.

    The choice is made on the day's snapshots at the last pre-start price
    (what SETTLE grades), and the chosen side is then graded from the stored
    result like a printed leg (`grade_coupon`). Choosing among SETTLE's graded
    rows instead would skip a pushed pick and take the event's next side -
    selection on the outcome. A push is VOID and stays out of n.

    Graded at the last pre-start price, not a printed one: the rule's record,
    not a coupon's, and kept apart from the coupon's own result.
    """
    picks: list[dict[str, Any]] = []
    days: list[str] = []
    for date in dates:
        settled = load_settled(runs_dir, sport, date)
        if settled is None:
            continue
        days.append(date)
        snaps = load_snapshots(day_dir(runs_dir, sport, date) / cs2.SNAPSHOTS_FILE)
        events = latest_events(sport, snaps)
        for eid, stored in (settled.get("events") or {}).items():
            ev = events.get(eid)
            if ev is None or stored.get("state") != "SETTLED":
                continue
            # The clock SETTLE used: Sofascore's start where it was earlier.
            start = stored.get("sofascore_start_utc")
            at = (
                min(_utc(ev.kickoff_utc), _utc(start))
                if start
                else _utc(ev.kickoff_utc)
            )
            ev_now = latest_events(
                sport,
                [
                    x
                    for x in snaps
                    if x["superbet_event_id"] == eid and _utc(x["fetched_at_utc"]) < at
                ],
            ).get(eid)
            if ev_now is None:
                continue
            counts: dict[str, int] = {}
            cands = candidates(
                sport,
                {eid: ev_now},
                _utc(max(ev_now.fetched_at.values(), key=_utc)),
                rule,
                counts,
                check_clock=False,
            )
            if not cands:
                continue
            leg = max(cands, key=_rank)
            outcome = _grade_leg(sport, leg, stored)
            picks.append({**leg, "outcome": outcome})
    by_family: dict[str, list[dict[str, Any]]] = {}
    for row in picks:
        by_family.setdefault(str(row["family"]), []).append(row)
    return {
        "days": days,
        **summarize(picks),
        "void": sum(1 for r in picks if r["outcome"] == "VOID"),
        "ungradeable": sum(1 for r in picks if r["outcome"] == "UNGRADEABLE"),
        "by_family": {
            fam: summarize(rows)
            for fam, rows in sorted(by_family.items(), key=lambda kv: -len(kv[1]))
        },
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    decided = [r for r in rows if r.get("outcome") in ("WIN", "LOSS")]
    n = len(decided)
    if not n:
        return {"n": 0}
    wins = sum(1 for r in decided if r["outcome"] == "WIN")
    profit = sum(r["odds"] - 1.0 if r["outcome"] == "WIN" else -1.0 for r in decided)
    return {
        "n": n,
        "wins": wins,
        "hit": round(wins / n, 4),
        "mean_fair_p": round(sum(r["fair_p"] for r in decided) / n, 4),
        "roi": round(profit / n, 4),
    }


# --- the coupon's own result ---------------------------------------------------

LEG_KEY = (
    "superbet_event_id",
    "market_id",
    "family",
    "period",
    "map_nr",
    "subject",
    "line",
    "side",
)


def _leg_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(row.get(k) for k in LEG_KEY)


# SETTLE's final states other than SETTLED / VOID: the event will not be
# graded. Everything else is asked again, so the leg is still pending.
TERMINAL_UNGRADED = frozenset({"UNUSUAL", "GAVE_UP", "NO_PRE_START_PRICE"})
# SETTLE gives up on an event it could not grade within this long of its start
# (settle_shadow / settle_cs2 GIVE_UP_AFTER) - but only if it is ever run on
# that date again, and the daily loops settle D and D-1 only. So a
# NOT_ON_SOFASCORE leg stayed PENDING for ever (2026-10-01: 6 of the 09-30
# volleyball coupon's 8 legs). The coupon's grader applies the same deadline
# itself: past it, a leg still waiting is NOT_GRADED:GAVE_UP.
GIVE_UP_AFTER = timedelta(days=7)


def _stored_winner(ev: dict[str, Any]) -> Literal["T1", "T2"] | None:
    """Sofascore's winner as SHADOW_SETTLE stored it (since 2026-09-30), else
    from the score where the score can tell (never after a shootout)."""
    if ev.get("winner") in ("T1", "T2"):
        return ev["winner"]  # type: ignore[no-any-return]
    if ev.get("status") == "AP":
        return None
    if ev.get("overtime"):
        a, b = ev["t1_full"], ev["t2_full"]
    else:
        a, b = sum(ev["t1_periods"]), sum(ev["t2_periods"])
    return None if a == b else ("T1" if a > b else "T2")


def _grade_leg(sport: SportKey, leg: dict[str, Any], ev: dict[str, Any]) -> str:
    """One leg against a SETTLED event's stored result."""
    if sport == "cs2":
        maps = [cs2.MapResult(int(a), int(b), {}) for a, b in ev.get("maps") or []]
        if not maps:
            return "UNGRADEABLE"
        # Settled from the series score alone (cs2.series_only_maps): its
        # placeholder rounds answer the series families and nothing else.
        if ev.get("series_only") and leg["family"] not in cs2.SERIES_FAMILIES:
            return "UNGRADEABLE"
        line = cs2.Cs2Line(
            leg["superbet_event_id"],
            leg["family"],
            int(leg.get("map_nr") or 0),
            str(leg.get("subject") or ""),
            leg.get("line"),
            leg["side"],
            float(leg["odds"]),
        )
        actual = cs2.actual_value(line, maps, leg["team1"], leg["team2"])
        return "UNGRADEABLE" if actual is None else cs2.grade(line, actual)
    spec_sport = shadow.SPORTS[sport]
    spec = shadow.MARKETS[sport].get(int(leg.get("market_id") or 0))
    if spec is None:
        return "UNGRADEABLE"
    if ev.get("orientation_unclear") and (
        spec.kind not in shadow.ORIENTATION_FREE or spec.team is not None
    ):
        return "UNGRADEABLE"
    result = shadow.GameResult(
        tuple(ev["t1_periods"]),
        tuple(ev["t2_periods"]),
        int(ev["t1_full"]),
        int(ev["t2_full"]),
        _stored_winner(ev),
        bool(ev.get("overtime")),
    )
    sline = shadow.ShadowLine(
        leg["superbet_event_id"],
        int(leg["market_id"]),
        leg["family"],
        int(leg.get("period") or 0),
        str(leg.get("subject") or ""),
        leg.get("line"),
        leg["side"],
        float(leg["odds"]),
    )
    actual = shadow.actual_value(sline, result, spec_sport)
    if actual is None:
        return "UNGRADEABLE"
    return shadow.grade(sline, actual, spec.kind == "three_way")


def _priced_in_play(leg: dict[str, Any], ev: dict[str, Any]) -> bool:
    start = ev.get("sofascore_start_utc")
    priced = leg.get("price_fetched_at_utc")
    return bool(start and priced) and _utc(str(priced)) >= _utc(str(start))


def grade_coupon(
    coupon: dict[str, Any],
    settled_by_date: dict[str, dict[str, Any] | None],
    at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Each printed leg graded at the PRINTED price, from the stored result of
    the file its event settles into (`source_date`, else the coupon's date).

    WIN / LOSS / VOID (a push, or a map / set never played); UNGRADEABLE when
    the result cannot answer the line (an ambiguous overtime, an unclear
    orientation); VOID when SETTLE voided the event; NOT_GRADED:<state> for
    an event SETTLE gave up on; IN_PLAY_PRICE when the printed price was
    taken after Sofascore's real start; PENDING / PENDING:<state> until it
    is settled - and, when `at` is given, NOT_GRADED:GAVE_UP once a leg
    still waiting is more than GIVE_UP_AFTER past its kickoff. Where the
    measurement graded the same side too, a disagreement is MISMATCH - it
    means one of the two graders is wrong, and neither result is counted.
    """
    sport: SportKey = coupon["sport"]
    out: list[dict[str, Any]] = []
    for leg in coupon.get("legs", []):
        source = leg.get("source_date") or coupon["date"]
        events = (settled_by_date.get(source) or {}).get("events") or {}
        ev = events.get(leg["superbet_event_id"])
        if ev is None:
            outcome = "PENDING"
        elif ev.get("state") == "SETTLED" and _priced_in_play(leg, ev):
            # the printed price was taken after the game really began: not a
            # pre-match price, never counted (the measurement's
            # NO_PRE_START_PRICE)
            outcome = "IN_PLAY_PRICE"
        elif ev.get("state") == "SETTLED":
            outcome = _grade_leg(sport, leg, ev)
            if outcome == "UNGRADEABLE" and sport == "cs2" and ev.get("pending_sides"):
                # CS2_SETTLE graded part of the series and asks again for the
                # rest (series_only round scores, late player rows): not yet
                # an answer, so pending until the record is final or the
                # leg passes GIVE_UP_AFTER below.
                outcome = f"PENDING:{ev.get('pending_reason') or 'PARTIAL'}"
            measured = {_leg_key(r): r["outcome"] for r in ev.get("graded") or []}
            other = measured.get(_leg_key(leg))
            if other is not None and outcome in ("WIN", "LOSS") and other != outcome:
                outcome = "MISMATCH"
        elif ev.get("state") == "VOID":
            outcome = "VOID"
        elif ev.get("state") in TERMINAL_UNGRADED:
            outcome = f"NOT_GRADED:{ev.get('state')}"
        else:  # a state SETTLE asks again (settle_shadow / settle_cs2 RETRYABLE)
            outcome = f"PENDING:{ev.get('state')}"
        if (
            at is not None
            and outcome.startswith("PENDING")
            and at - _utc(leg["kickoff_utc"]) > GIVE_UP_AFTER
        ):
            outcome = "NOT_GRADED:GAVE_UP"
        out.append({**leg, "outcome": outcome})
    return out
