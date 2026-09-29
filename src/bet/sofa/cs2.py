"""CS2 shadow measurement: Superbet prices graded against Sofascore results.

Outside the coupon on purpose (2026-09-28). The question it answers has to
come before any model: on the CS2 markets Superbet posts, does the devigged
price already match what happens, and what does staking a side at the posted
price return? If the price is as good as it is in football, a sample has
nothing to add and the sport does not earn a place on the coupon.

Two stages use this module, neither in DEFAULT_SEQUENCE:

    CS2         scripts/sofa/run_cs2.py     Superbet only, several times a day
    CS2_SETTLE  scripts/sofa/settle_cs2.py  Sofascore via the bridge, D-1

and `scripts/sofa/audit_cs2.py` reports on what they wrote.

Sources, and what each was checked against (2026-09-28):

- Superbet sportId 55 is "Counter-Strike 2" (its /v2/pl-PL/struct). 84 of the
  95 CS2 events started that day were "Winners series 1x1" / "H2H Liga", the
  same three or four sides looping every few minutes; Sofascore carries none.
- Sofascore keeps one esports team per title (Ninjas in Pyjamas is a LoL, a
  Dota 2 and a CS entity), so a listing only counts in category
  "Counter Strike".
- A map's `display` score includes overtime and so do its player rows:
  Ancient 19-17 of magic - GamerLegion (2026-09-26) is 5+7+7 / 7+5+5 with 24
  normaltime + 12 overtime rounds, and sFade8 32-28, REZ 28-27, as on
  dust2.us; Cache of the same series matches dust2.us row for row.
- Superbet's rules (Regulamin, 5.D-5.E): a market says "(z dogrywką)" when it
  counts overtime; a walkover is not a result; an event not played within 48 h
  is void; so is a bet on a player who did not take part, and one whose
  condition cannot be met (a third map in a 2-0).

Only markets Sofascore's per-map data grades without interpretation are
parsed. AWP kills (not published), combos, boosts, exact scores, round-N and
pistol-round markets are skipped.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from rapidfuzz import fuzz

from bet.sofa.engine import devig
from bet.sofa.names import DIACRITICS_FOLD
from bet.sofa.resolve import NAME_MATCH_THRESHOLD

SUPERBET_CS2_SPORT_ID = 55
SOFASCORE_CS_CATEGORY = "Counter Strike"

# Sofascore's kickoff and Superbet's disagree by minutes, and tier-2 series
# start late; a later start is not a different match between the same sides.
MATCH_WINDOW = timedelta(hours=6)
# Regulamin 5.E.1.a: not played within 48 h of the original time -> void.
VOID_AFTER = timedelta(hours=48)
# A best-of-three runs ~2.5 h; settling earlier only finds it unfinished.
SETTLE_AFTER = timedelta(hours=4)
# Five a side. A map with fewer rows cannot grade a team's kills.
TEAM_SIZE = 5

PLAYER_STATS = {
    "zabójstw": "kills",
    "śmierci": "deaths",
    "headshotów": "headshots",
    "asyst": "assists",
}
FAMILIES = (
    "match_winner",
    "maps_total",
    "maps_handicap",
    "team_maps",
    "rounds_total",
    "rounds_handicap",
    "team_rounds",
    "map_winner",
    "map_rounds_total",
    "map_rounds_handicap",
    "map_team_rounds",
    "team_kills",
    "player_kills",
    "player_deaths",
    "player_headshots",
    "player_assists",
)
PARTNER = {"OVER": "UNDER", "UNDER": "OVER", "T1": "T2", "T2": "T1"}

# Full matches, each ending "(z dogrywką)". A map-level market without that
# suffix counts regulation rounds only (Regulamin 5.D.3.a), and a prefix match
# once let "1.mapa - Liczba rund w 1. połowie" in as the whole map's rounds.
_OT = r" \(z dogrywką\)$"
_PLAYER_MARKET = re.compile(
    r"^(\d)\.\s?mapa - liczba (zabójstw|śmierci|headshotów|asyst) zawodnika" + _OT
)
_TEAM_KILLS = re.compile(r"^(\d)\.\s?mapa - (.+?) - liczba zabójstw" + _OT)
_MAP_ROUNDS = re.compile(r"^(\d)\.\s?mapa - Liczba rund" + _OT)
_MAP_TEAM_ROUNDS = re.compile(r"^(\d)\.\s?mapa - (.+?) liczba rund" + _OT)
_MAP_ROUND_HCP = re.compile(r"^(\d)\.\s?mapa - Handicap rund" + _OT)
_HCP_IN_NAME = re.compile(r"\((-?\d+(?:\.\d+)?)\)")
# Series- and map-winner markets. An outcome naming neither side (a draw)
# makes the market three-way, and a two-way devig of it would be wrong.
WINNER_MARKETS = ("Zwycięzca (z dogrywką)", "Mapa X - zwycięzca (z dogrywką)")
_TEAM_ROUNDS = re.compile(r"^(.+?) liczba rund \(z dogrywką\)$")
_TEAM_MAPS = re.compile(r"^(.+?) liczba map$")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def esports_name(name: str) -> str:
    """A team or player name folded for comparison, and nothing more.

    Not `normalize_name`: that one rewrites Polish exonyms anywhere in the
    name and turns a trailing "B"/"II"/"2" into a reserve marker - right for
    football clubs, wrong for "BIG Academy" or a nickname like "Snax".
    """
    for char, repl in DIACRITICS_FOLD.items():
        name = name.replace(char, repl).replace(char.upper(), repl.upper())
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return _NON_ALNUM.sub(" ", name.lower()).strip()


@dataclass(frozen=True)
class Cs2Line:
    """One side of one two-way Superbet line."""

    superbet_event_id: str
    family: str
    map_nr: int  # 0 = the whole series
    subject: str  # player or team name; "" for series/map-level markets
    line: float | None  # a total, or team1's handicap; None for a winner
    side: str  # OVER / UNDER / T1 / T2
    odds: float

    def key(self) -> tuple[str, int, str, float | None]:
        return (self.family, self.map_nr, self.subject, self.line)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _num(raw: object) -> float | None:
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _direction(text: str) -> str | None:
    lowered = text.lower()
    under, over = "poniż" in lowered, "powyż" in lowered
    if under == over:
        return None
    return "UNDER" if under else "OVER"


def _team_side(text: str, team1: str, team2: str) -> str | None:
    """Which team a winner/handicap outcome names. The longer name wins when
    one contains the other, so "Team X Academy" is not read as "Team X"."""
    hits = [(len(t), s) for t, s in ((team1, "T1"), (team2, "T2")) if t and t in text]
    return max(hits)[1] if hits else None


def _handicap_side(name: str, hcp: float | None, team1: str, team2: str) -> str | None:
    """The side of a handicap outcome, if its name agrees with the specifier.

    Superbet quotes both outcomes under team1's `hcp`: "NiP (-1.5)" and
    "GamerLegion (1.5)" both carry hcp -1.5. An outcome whose own number is
    not hcp (team1) or -hcp (team2) breaks that convention and is dropped
    rather than graded against the wrong line.
    """
    side = _team_side(name, team1, team2)
    m = _HCP_IN_NAME.search(name)
    if side is None or hcp is None or m is None:
        return None
    expected = hcp if side == "T1" else -hcp
    return side if float(m.group(1)) == expected else None


def team_of(subject: str, team1: str, team2: str) -> str | None:
    subject = subject.strip()
    if subject == team1:
        return "T1"
    if subject == team2:
        return "T2"
    return None


def parse_line(
    item: dict[str, Any], event_id: str, team1: str, team2: str
) -> Cs2Line | None:
    """One Superbet odds item as a gradeable line, or None if it is not one."""
    market = str(item.get("marketName") or "").strip()
    if not market or market == "Boost" or ";" in market:
        return None
    # A boosted price is Superbet's promotion, not its price for the line.
    if "price_boost" in str(item.get("tags") or ""):
        return None
    if item.get("status") not in (None, "active"):
        return None
    odds = _num(item.get("price"))
    if odds is None or odds <= 1.0:
        return None
    spec = item.get("specifiers") or {}
    name = str(item.get("name") or "")
    info = str(item.get("info") or "")
    total = _num(spec.get("total"))
    hcp = _num(spec.get("hcp"))
    mapnr = int(_num(spec.get("mapnr")) or 0)

    def make(
        family: str, map_nr: int, subject: str, value: float | None, side: str | None
    ) -> Cs2Line | None:
        if side is None:
            return None
        if family != "match_winner" and family != "map_winner" and value is None:
            return None
        return Cs2Line(event_id, family, map_nr, subject, value, side, odds)

    if market == "Zwycięzca (z dogrywką)":
        return make("match_winner", 0, "", None, _team_side(name, team1, team2))
    if market == "Mapa X - zwycięzca (z dogrywką)":
        if mapnr < 1:
            return None
        return make("map_winner", mapnr, "", None, _team_side(name, team1, team2))
    if market == "Liczba map":
        return make("maps_total", 0, "", total, _direction(name))
    if market == "Handicap map":
        return make(
            "maps_handicap", 0, "", hcp, _handicap_side(name, hcp, team1, team2)
        )
    if market == "Liczba rund (z dogrywką)":
        return make("rounds_total", 0, "", total, _direction(name))
    if market == "Handicap rund (z dogrywką)":
        side = _handicap_side(name, hcp, team1, team2)
        return make("rounds_handicap", 0, "", hcp, side)

    if m := _PLAYER_MARKET.match(market):
        player = str(spec.get("player") or "").strip()
        if not player:
            return None
        family = "player_" + PLAYER_STATS[m.group(2)]
        return make(
            family, int(m.group(1)), player, total, _direction(name + " " + info)
        )
    if m := _MAP_ROUND_HCP.match(market):
        side = _handicap_side(name, hcp, team1, team2)
        return make("map_rounds_handicap", int(m.group(1)), "", hcp, side)
    if m := _MAP_ROUNDS.match(market):
        return make("map_rounds_total", int(m.group(1)), "", total, _direction(name))
    if (m := _TEAM_KILLS.match(market)) and team_of(m.group(2), team1, team2):
        subject = m.group(2).strip()
        return make("team_kills", int(m.group(1)), subject, total, _direction(name))
    if (m := _MAP_TEAM_ROUNDS.match(market)) and team_of(m.group(2), team1, team2):
        subject = m.group(2).strip()
        return make(
            "map_team_rounds", int(m.group(1)), subject, total, _direction(info)
        )
    if (m := _TEAM_ROUNDS.match(market)) and team_of(m.group(1), team1, team2):
        return make("team_rounds", 0, m.group(1).strip(), total, _direction(info))
    if (m := _TEAM_MAPS.match(market)) and team_of(m.group(1), team1, team2):
        return make("team_maps", 0, m.group(1).strip(), total, _direction(info))
    return None


def _names_neither_side(item: dict[str, Any], team1: str, team2: str) -> bool:
    """A live, priced outcome of a winner market that is neither team - a
    draw. A suspended, boosted or unpriced copy of a side is not one."""
    if item.get("status") not in (None, "active"):
        return False
    if "price_boost" in str(item.get("tags") or ""):
        return False
    odds = _num(item.get("price"))
    if odds is None or odds <= 1.0:
        return False
    return _team_side(str(item.get("name") or ""), team1, team2) is None


def parse_event(
    items: list[dict[str, Any]], event_id: str, team1: str, team2: str
) -> list[Cs2Line]:
    """Every gradeable line of an event whose two sides are both quoted.

    A side quoted twice (two outcome ids for one line) makes the pair
    ambiguous, and the whole line is dropped rather than guessed.
    """
    by_key: dict[tuple[str, int, str, float | None], dict[str, list[Cs2Line]]] = {}
    three_way: set[tuple[str, int]] = set()
    for item in items:
        parsed = parse_line(item, event_id, team1, team2)
        market = str(item.get("marketName") or "").strip()
        if (
            parsed is None
            and market in WINNER_MARKETS
            and _names_neither_side(item, team1, team2)
        ):
            mapnr = int(_num((item.get("specifiers") or {}).get("mapnr")) or 0)
            family = "match_winner" if market == WINNER_MARKETS[0] else "map_winner"
            three_way.add((family, mapnr))
        if parsed is not None:
            by_key.setdefault(parsed.key(), {}).setdefault(parsed.side, []).append(
                parsed
            )
    out: list[Cs2Line] = []
    for key, sides in by_key.items():
        if (key[0], key[1]) in three_way:
            continue
        if set(sides) not in ({"OVER", "UNDER"}, {"T1", "T2"}):
            continue
        if any(len(v) != 1 for v in sides.values()):
            continue
        out.extend(v[0] for v in sides.values())
    return out


def fair_probability(odds: float, partner_odds: float) -> float | None:
    """The devigged probability of a side, by the pipeline's own devig."""
    pair = devig(odds, partner_odds)
    return None if pair is None else pair[0]


# --- snapshots ---------------------------------------------------------------


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


@dataclass
class SnapshotEvent:
    """One Superbet event, with each side at the last price seen pre-start."""

    superbet_event_id: str
    match_name: str
    team1: str
    team2: str
    kickoff_utc: str
    tournament: str | None
    sides: dict[tuple[str, int, str, float | None, str], Cs2Line] = field(
        default_factory=dict
    )
    fetched_at: dict[tuple[str, int, str, float | None, str], str] = field(
        default_factory=dict
    )


def latest_pre_kickoff(snapshots: list[dict[str, Any]]) -> dict[str, SnapshotEvent]:
    """Fold snapshot records into each event's last pre-start price per side.

    The kickoff is the one of the latest record: a rescheduled series keeps
    its newest time, and a record taken at or after that time is not a
    pre-match price.
    """
    latest: dict[str, tuple[str, str]] = {}  # event -> (fetched_at, kickoff)
    for snap in snapshots:
        eid = snap["superbet_event_id"]
        if eid not in latest or snap["fetched_at_utc"] >= latest[eid][0]:
            latest[eid] = (snap["fetched_at_utc"], snap["kickoff_utc"])
    events: dict[str, SnapshotEvent] = {}
    for snap in sorted(snapshots, key=lambda s: str(s["fetched_at_utc"])):
        eid = snap["superbet_event_id"]
        kickoff = latest[eid][1]
        if _utc(snap["fetched_at_utc"]) >= _utc(kickoff):
            continue
        ev = events.setdefault(
            eid,
            SnapshotEvent(
                eid,
                snap["match_name"],
                snap["team1"],
                snap["team2"],
                kickoff,
                snap.get("tournament"),
            ),
        )
        for raw in snap["lines"]:
            line = Cs2Line(**raw)
            key = (*line.key(), line.side)
            ev.sides[key] = line
            ev.fetched_at[key] = snap["fetched_at_utc"]
    return events


# --- resolving the series on Sofascore ----------------------------------------


Resolution = tuple[dict[str, Any], bool]


# Organisation affixes one source prints and the other drops ("Masonic" /
# "Masonic Esports", "33" / "33 Esports"). "academy", "junior", "prospects"
# are NOT here: they name a different roster, and must keep two names apart.
ESPORTS_AFFIXES = frozenset({"esports", "esport", "gaming", "team", "club", "clan"})


def _core(name: str) -> str:
    words = [w for w in name.split() if w not in ESPORTS_AFFIXES]
    return " ".join(words) if words else name


def esports_score(a: str, b: str) -> float:
    """Name similarity with no subset reading.

    Not `resolve.name_score`: its token-set half scores "big" against "big
    academy" 100, and an esports organisation's academy plays in the same
    tier-2 events as its main roster. Word order may differ; word sets may not.
    """
    a, b = _core(a), _core(b)
    return max(fuzz.ratio(a, b), fuzz.token_sort_ratio(a, b))


def _orientation(
    event: dict[str, Any], team1: str, team2: str
) -> tuple[float, bool | None]:
    """(how well the event's sides match team1/team2, home is team1).

    Orientation is None when the two readings score the same - "Team Spirit"
    against "Team Spirit Academy" either way round - because grading a tie
    either way is a coin toss on every team-side line.
    """
    home = esports_name(str((event.get("homeTeam") or {}).get("name") or ""))
    away = esports_name(str((event.get("awayTeam") or {}).get("name") or ""))
    t1, t2 = esports_name(team1), esports_name(team2)
    straight = min(esports_score(t1, home), esports_score(t2, away))
    crossed = min(esports_score(t1, away), esports_score(t2, home))
    if straight == crossed:
        return straight, None
    return max(straight, crossed), straight > crossed


def pick_event(
    candidates: list[dict[str, Any]], team1: str, team2: str, kickoff: datetime
) -> Resolution | Literal["AMBIGUOUS"] | None:
    """The one Counter Strike event between these two sides near this kickoff.

    Both names must clear the pipeline's name threshold - one side alone
    matches every other series that team plays that week. Two different
    events that both fit is AMBIGUOUS, never a coin toss.
    """
    fits: dict[int, Resolution] = {}
    for e in candidates:
        category = ((e.get("tournament") or {}).get("category") or {}).get("name")
        if category != SOFASCORE_CS_CATEGORY:
            continue
        start = datetime.fromtimestamp(
            int(e.get("startTimestamp") or 0), kickoff.tzinfo
        )
        if abs(start - kickoff) > MATCH_WINDOW:
            continue
        score, home_is_t1 = _orientation(e, team1, team2)
        if score <= NAME_MATCH_THRESHOLD:
            continue
        if home_is_t1 is None:
            return "AMBIGUOUS"
        fits[int(e["id"])] = (e, home_is_t1)
    if len(fits) > 1:
        return "AMBIGUOUS"
    return next(iter(fits.values()), None)


# --- the result ----------------------------------------------------------------


@dataclass(frozen=True)
class MapResult:
    t1_rounds: int
    t2_rounds: int
    # (team "T1"/"T2", esports_name(player)) -> stat -> value; empty when
    # Sofascore has no complete statistics for the map. Keyed by side too:
    # two players may share a nickname across the two rosters.
    players: dict[tuple[str, str], dict[str, int]]

    def player(self, name: str) -> dict[str, int] | None:
        """One player's row by name, or None - also when the nickname is on
        both rosters, since the line does not say which of them it means."""
        rows = [s for (_, n), s in self.players.items() if n == esports_name(name)]
        return rows[0] if len(rows) == 1 else None

    def team_total(self, side: str, stat: str) -> int | None:
        """The side's total of `stat`, or None unless five rows carry it.

        A row without the stat is missing data, not a zero: four players at
        20 kills and one row without `kills` is not 80 kills.
        """
        values = [
            s[stat] for (t, _), s in self.players.items() if t == side and stat in s
        ]
        return sum(values) if len(values) >= TEAM_SIZE else None


def build_map_result(
    game: dict[str, Any], lineups: dict[str, Any] | None, home_is_t1: bool
) -> MapResult | None:
    """One finished map, oriented to Superbet's team1/team2, or None."""
    if (game.get("status") or {}).get("type") != "finished":
        return None
    home = (game.get("homeScore") or {}).get("display")
    away = (game.get("awayScore") or {}).get("display")
    if not isinstance(home, int) or not isinstance(away, int) or home == away:
        return None
    t1, t2 = (home, away) if home_is_t1 else (away, home)
    players: dict[tuple[str, str], dict[str, int]] = {}
    for key, is_home in (("homeTeamPlayers", True), ("awayTeamPlayers", False)):
        team = "T1" if is_home == home_is_t1 else "T2"
        for row in (lineups or {}).get(key) or []:
            name = esports_name(str((row.get("player") or {}).get("name") or ""))
            if not name:
                continue
            stats = {
                stat: int(row[stat])
                for stat in PLAYER_STATS.values()
                if isinstance(row.get(stat), int)
            }
            players[(team, name)] = stats
    return MapResult(t1, t2, players)


# A game in Sofascore's list that never started - the third map of a 2-0 - is
# not a map of the series. Anything else unfinished means the data is not in.
NEVER_PLAYED = {"notstarted", "canceled", "cancelled", "postponed"}


def stats_missing(ev: SnapshotEvent, maps: list[MapResult]) -> bool:
    """A player or team-kill line sits on a played map with no player rows yet.

    Sofascore publishes the per-player rows after the score; settling before
    they land would record those lines as ungradeable for good.
    """
    for family, map_nr, *_ in ev.sides:
        if not (family.startswith("player_") or family == "team_kills"):
            continue
        if 1 <= map_nr <= len(maps) and not maps[map_nr - 1].players:
            return True
    return False


EventState = Literal["FINISHED", "PENDING", "VOID", "UNUSUAL"]


def event_state(detail: dict[str, Any], kickoff: datetime, now: datetime) -> EventState:
    """Where the series stands, by Superbet's rules.

    FINISHED only for a plainly ended series. Cancelled, abandoned, or not
    started 48 h after the scheduled start is VOID (Regulamin 5.E.1.a). A
    "finished" whose description is not "Ended" - a walkover, an awarded
    series - is UNUSUAL and never graded: a walkover is not a result (5.D.3.b).
    """
    status = detail.get("status") or {}
    kind = status.get("type")
    if kind == "finished":
        return "FINISHED" if status.get("description") == "Ended" else "UNUSUAL"
    if kind in ("canceled", "cancelled", "abandoned"):
        return "VOID"
    # Only a series that never started is void at 48 h. One still "inprogress"
    # two days on is a stale status, not an unplayed match - it stays PENDING
    # and CS2_SETTLE gives up on it (GAVE_UP, ours) rather than calling it
    # Superbet's void.
    if kind in ("notstarted", "postponed", "delayed") and now - kickoff > VOID_AFTER:
        return "VOID"
    return "PENDING"


def build_series(
    detail: dict[str, Any],
    games: list[dict[str, Any]],
    lineups: dict[int, dict[str, Any] | None],
    home_is_t1: bool,
) -> list[MapResult] | None:
    """Every played map in order, or None if the data does not add up.

    Positional on purpose: Superbet's "2. mapa" is the second map played, so a
    map missing from the middle would shift every later one. And the maps must
    reproduce the series score Sofascore itself reports - a partial games list
    that did not would grade a 2-1 as a 2-0.
    """
    played = [
        g for g in games if (g.get("status") or {}).get("type") not in NEVER_PLAYED
    ]
    ordered = sorted(played, key=lambda g: int(g.get("startTimestamp") or 0))
    maps: list[MapResult] = []
    for g in ordered:
        result = build_map_result(g, lineups.get(int(g.get("id") or 0)), home_is_t1)
        if result is None:
            return None
        maps.append(result)
    home = (detail.get("homeScore") or {}).get("current")
    away = (detail.get("awayScore") or {}).get("current")
    t1_maps = sum(1 for m in maps if m.t1_rounds > m.t2_rounds)
    t2_maps = len(maps) - t1_maps
    expected = (home, away) if home_is_t1 else (away, home)
    if not maps or (t1_maps, t2_maps) != expected:
        return None
    return maps


def actual_value(
    line: Cs2Line, maps: list[MapResult], team1: str, team2: str
) -> float | None:
    """What happened for this line's quantity; None when it cannot be told,
    which Superbet voids (map not played, player absent)."""

    def rounds(side: str, played: list[MapResult]) -> int:
        return sum(m.t1_rounds if side == "T1" else m.t2_rounds for m in played)

    fam = line.family
    side = team_of(line.subject, team1, team2)
    if line.map_nr:
        if line.map_nr > len(maps):
            return None
        mp = maps[line.map_nr - 1]
        if fam in ("map_winner", "map_rounds_handicap"):
            return float(mp.t1_rounds - mp.t2_rounds)
        if fam == "map_rounds_total":
            return float(mp.t1_rounds + mp.t2_rounds)
        if fam == "map_team_rounds" and side:
            return float(rounds(side, [mp]))
        if fam == "team_kills" and side:
            total = mp.team_total(side, "kills")
            return None if total is None else float(total)
        if fam.startswith("player_"):
            row = mp.player(line.subject)
            stat = fam.removeprefix("player_")
            if row is None or stat not in row:
                return None
            return float(row[stat])
        return None
    t1_maps = sum(1 for m in maps if m.t1_rounds > m.t2_rounds)
    t2_maps = len(maps) - t1_maps
    if fam in ("match_winner", "maps_handicap"):
        return float(t1_maps - t2_maps)
    if fam == "maps_total":
        return float(len(maps))
    if fam == "rounds_total":
        return float(rounds("T1", maps) + rounds("T2", maps))
    if fam == "rounds_handicap":
        return float(rounds("T1", maps) - rounds("T2", maps))
    if fam == "team_rounds" and side:
        return float(rounds(side, maps))
    if fam == "team_maps" and side:
        return float(t1_maps if side == "T1" else t2_maps)
    return None


Outcome = Literal["WIN", "LOSS", "VOID"]


def grade(line: Cs2Line, actual: float) -> Outcome:
    """WIN / LOSS / VOID for this side, given the quantity's actual value.

    For winners and handicaps `actual` is team1 minus team2 (maps or rounds)
    and `line.line` is team1's handicap - Superbet quotes both outcomes of a
    handicap under the same team1 specifier ("NiP (-1.5)" / "GamerLegion (1.5)"
    both carry hcp -1.5).
    """
    if line.side in ("OVER", "UNDER"):
        if line.line is None or actual == line.line:
            return "VOID"
        return "WIN" if (actual > line.line) == (line.side == "OVER") else "LOSS"
    margin = actual + (line.line or 0.0)
    if margin == 0:
        return "VOID"
    return "WIN" if (margin > 0) == (line.side == "T1") else "LOSS"


def settle_event(
    ev: SnapshotEvent, maps: list[MapResult]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Grade every priced pair of one event. Both sides of a pair or neither."""
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {"void": 0, "ungradeable": 0, "unpaired": 0}
    for key, line in ev.sides.items():
        partner = ev.sides.get((*key[:4], PARTNER[line.side]))
        if partner is None:
            counts["unpaired"] += 1
            continue
        actual = actual_value(line, maps, ev.team1, ev.team2)
        if actual is None:
            counts["ungradeable"] += 1
            continue
        outcome = grade(line, actual)
        if outcome == "VOID":
            counts["void"] += 1
            continue
        rows.append(
            {
                **line.as_dict(),
                "partner_odds": partner.odds,
                "fair_p": fair_probability(line.odds, partner.odds),
                "fetched_at_utc": ev.fetched_at[key],
                "actual": actual,
                "outcome": outcome,
            }
        )
    return rows, counts


# --- the report ------------------------------------------------------------------


@dataclass(frozen=True)
class FamilyStats:
    family: str
    events: int
    sides: int
    fair_p: float
    hit: float
    brier: float
    roi: float
    margin: float


def summarize(rows: list[dict[str, Any]], label: str) -> FamilyStats | None:
    """Price against outcome for a set of graded sides.

    ROI is flat, one unit per side. With both sides of every line in, a
    pooled ROI is minus the margin by construction; what carries information
    is `hit - fair_p` and how it splits by family and by price.
    """
    rs = [r for r in rows if r.get("fair_p") is not None]
    if not rs:
        return None
    n = len(rs)
    wins = [1.0 if r["outcome"] == "WIN" else 0.0 for r in rs]
    margins = sorted(1 / r["odds"] + 1 / r["partner_odds"] - 1 for r in rs)
    return FamilyStats(
        family=label,
        events=len({r["superbet_event_id"] for r in rs}),
        sides=n,
        fair_p=sum(r["fair_p"] for r in rs) / n,
        hit=sum(wins) / n,
        brier=sum((r["fair_p"] - w) ** 2 for r, w in zip(rs, wins, strict=True)) / n,
        roi=sum((r["odds"] - 1.0) if w else -1.0 for r, w in zip(rs, wins, strict=True))
        / n,
        margin=margins[n // 2],
    )


def _pair_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(
        row.get(k)
        for k in (
            "superbet_event_id",
            "family",
            "market_id",
            "map_nr",
            "period",
            "subject",
            "line",
        )
    )


def one_side_per_line(
    rows: list[dict[str, Any]], pick: str = "favourite"
) -> list[dict[str, Any]]:
    """One graded side of every line, so a gap can show.

    Both sides of a line are graded or neither, their devigged probabilities
    sum to one and exactly one of them wins. Pool both and the mean fair p
    and the hit rate are both 0.500 by construction, whatever the price is
    worth: 500 lines whose favourite won 90% of the time summarised to a gap
    of 0.0. Keeping one side restores it.

    `pick` "favourite" keeps the side with the higher devigged probability
    (OVER / T1 on an exact tie); "fixed" keeps OVER, else T1 - a lean toward
    a direction or toward the first-named team.
    """
    by_line: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for r in rows:
        if r.get("fair_p") is not None:
            by_line.setdefault(_pair_key(r), []).append(r)
    out: list[dict[str, Any]] = []
    for sides in by_line.values():
        first = [r for r in sides if r.get("side") in ("OVER", "T1")]
        if pick == "fixed":
            out.extend(first[:1] or sides[:1])
            continue
        best = max(r["fair_p"] for r in sides)
        top = [r for r in sides if r["fair_p"] == best]
        out.append(next((r for r in top if r in first), top[0]))
    return out


# --- files ------------------------------------------------------------------------

SNAPSHOTS_FILE = "snapshots.jsonl"
SETTLED_FILE = "settled.json"


def cs2_day_dir(runs_dir: str, date: str) -> Path:
    """runs/sofa/cs2/<date>/ - beside the day, never inside it, so nothing CS2
    writes can be read by a stage that builds the coupon."""
    return Path(runs_dir) / "cs2" / date


def write_atomic(path: Path, text: str) -> None:
    """Write through a temporary file, so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
