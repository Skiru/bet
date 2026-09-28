"""CS2 shadow measurement: Superbet prices graded against Sofascore results.

Outside the sofa pipeline on purpose (2026-09-28). The question it answers is
the one that has to come before any model: on the CS2 markets Superbet posts,
does the devigged price already match what happens, and what does staking a
side at the posted price return? If the price is as good as it is in football
there is nothing for a sample to add, and the sport is not worth a pipeline.

Superbet sportId 55 ("Counter-Strike 2"). Sofascore keeps an esports team per
game title (Ninjas in Pyjamas is a LoL, a Dota and a CS entity), so a candidate
only counts when its events sit in the "Counter Strike" category.

Only markets that Sofascore's per-map data grades without interpretation are
parsed: match / map winner, maps total and handicap, rounds total and handicap
(match and per map), a team's rounds or maps, a team's kills on a map, and a
player's kills / deaths / headshots / assists on a map. AWP kills (Sofascore
does not publish them), combos, boosts and exact scores are skipped.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from bet.sofa.engine import devig
from bet.sofa.names import normalize_name

SUPERBET_CS2_SPORT_ID = 55
SOFASCORE_CS_CATEGORY = "Counter Strike"

PLAYER_STATS = {
    "zabójstw": "kills",
    "śmierci": "deaths",
    "headshotów": "headshots",
    "asyst": "assists",
}

_PLAYER_MARKET = re.compile(
    r"^(\d)\.\s?mapa - liczba (zabójstw|śmierci|headshotów|asyst) zawodnika"
)
_TEAM_KILLS = re.compile(r"^(\d)\.\s?mapa - (.+?) - liczba zabójstw")
_MAP_ROUNDS = re.compile(r"^(\d)\.\s?mapa - Liczba rund")
_MAP_TEAM_ROUNDS = re.compile(r"^(\d)\.\s?mapa - (.+?) liczba rund")
_MAP_ROUND_HCP = re.compile(r"^(\d)\.\s?mapa - Handicap rund")
_TEAM_ROUNDS = re.compile(r"^(.+?) liczba rund \(z dogrywką\)$")
_TEAM_MAPS = re.compile(r"^(.+?) liczba map$")


@dataclass(frozen=True)
class Cs2Line:
    """One side of one two-way Superbet line."""

    superbet_event_id: str
    family: str
    map_nr: int  # 0 = the whole match
    subject: str  # player or team name; "" for match-level markets
    line: float | None  # total or team1's handicap; None for a winner
    side: str  # OVER / UNDER / T1 / T2
    odds: float

    def key(self) -> tuple[str, str, int, str, float | None]:
        return (
            self.superbet_event_id,
            self.family,
            self.map_nr,
            self.subject,
            self.line,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _num(raw: object) -> float | None:
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _direction(text: str) -> str | None:
    lowered = text.lower()
    if "poniż" in lowered:
        return "UNDER"
    if "powyż" in lowered:
        return "OVER"
    return None


def _team_side(text: str, team1: str, team2: str) -> str | None:
    """Which team a winner/handicap outcome names. The longer name wins a tie,
    so "Team X Academy" is not read as "Team X"."""
    hits = [(len(t), s) for t, s in ((team1, "T1"), (team2, "T2")) if t and t in text]
    if not hits:
        return None
    return max(hits)[1]


def _team_of(subject: str, team1: str, team2: str) -> str | None:
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
    if "extra" in item and "price_boost" in str(item.get("tags") or ""):
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

    def line(
        family: str, map_nr: int, subject: str, value: float | None, side: str | None
    ) -> Cs2Line | None:
        if side is None:
            return None
        return Cs2Line(event_id, family, map_nr, subject, value, side, odds)

    if market == "Zwycięzca (z dogrywką)":
        return line("match_winner", 0, "", None, _team_side(name, team1, team2))
    if market == "Mapa X - zwycięzca (z dogrywką)":
        return line("map_winner", mapnr, "", None, _team_side(name, team1, team2))
    if market == "Liczba map":
        return line("maps_total", 0, "", total, _direction(name))
    if market == "Handicap map":
        return line("maps_handicap", 0, "", hcp, _team_side(name, team1, team2))
    if market == "Liczba rund (z dogrywką)":
        return line("rounds_total", 0, "", total, _direction(name))
    if market == "Handicap rund (z dogrywką)":
        return line("rounds_handicap", 0, "", hcp, _team_side(name, team1, team2))

    m = _PLAYER_MARKET.match(market)
    if m:
        player = str(spec.get("player") or "").strip()
        if not player:
            return None
        family = "player_" + PLAYER_STATS[m.group(2)]
        return line(
            family, int(m.group(1)), player, total, _direction(name + " " + info)
        )
    m = _MAP_ROUND_HCP.match(market)
    if m:
        return line(
            "map_rounds_handicap",
            int(m.group(1)),
            "",
            hcp,
            _team_side(name, team1, team2),
        )
    m = _MAP_ROUNDS.match(market)
    if m:
        return line("map_rounds_total", int(m.group(1)), "", total, _direction(name))
    m = _TEAM_KILLS.match(market)
    if m and _team_of(m.group(2), team1, team2):
        return line(
            "team_kills", int(m.group(1)), m.group(2).strip(), total, _direction(name)
        )
    m = _MAP_TEAM_ROUNDS.match(market)
    if m and _team_of(m.group(2), team1, team2):
        return line(
            "map_team_rounds",
            int(m.group(1)),
            m.group(2).strip(),
            total,
            _direction(info),
        )
    m = _TEAM_ROUNDS.match(market)
    if m and _team_of(m.group(1), team1, team2):
        return line("team_rounds", 0, m.group(1).strip(), total, _direction(info))
    m = _TEAM_MAPS.match(market)
    if m and _team_of(m.group(1), team1, team2):
        return line("team_maps", 0, m.group(1).strip(), total, _direction(info))
    return None


def parse_event(
    items: list[dict[str, Any]], event_id: str, team1: str, team2: str
) -> list[Cs2Line]:
    """Every gradeable line of an event whose two sides are both quoted."""
    lines = [
        parsed
        for item in items
        if (parsed := parse_line(item, event_id, team1, team2)) is not None
    ]
    by_key: dict[tuple[str, str, int, str, float | None], dict[str, Cs2Line]] = {}
    for ln in lines:
        by_key.setdefault(ln.key(), {})[ln.side] = ln
    out: list[Cs2Line] = []
    for sides in by_key.values():
        if set(sides) in ({"OVER", "UNDER"}, {"T1", "T2"}):
            out.extend(sides.values())
    return out


def fair_probability(line: Cs2Line, partner_odds: float) -> float | None:
    """The devigged probability of this side, by the pipeline's own devig."""
    pair = devig(line.odds, partner_odds)
    return None if pair is None else pair[0]


# --- the result, from Sofascore ---------------------------------------------


@dataclass(frozen=True)
class MapResult:
    t1_rounds: int
    t2_rounds: int
    # normalised player name -> (team "T1"/"T2", stat -> value)
    players: dict[str, tuple[str, dict[str, int]]]


def build_map_result(
    game: dict[str, Any],
    lineups: dict[str, Any] | None,
    sofascore_home_is_t1: bool,
) -> MapResult | None:
    """One finished map, oriented to Superbet's team1/team2."""
    if (game.get("status") or {}).get("type") != "finished":
        return None
    home = (game.get("homeScore") or {}).get("display")
    away = (game.get("awayScore") or {}).get("display")
    if not isinstance(home, int) or not isinstance(away, int):
        return None
    t1, t2 = (home, away) if sofascore_home_is_t1 else (away, home)
    players: dict[str, tuple[str, dict[str, int]]] = {}
    for key, is_home in (("homeTeamPlayers", True), ("awayTeamPlayers", False)):
        team = "T1" if is_home == sofascore_home_is_t1 else "T2"
        for row in (lineups or {}).get(key) or []:
            name = normalize_name(str((row.get("player") or {}).get("name") or ""))
            if not name:
                continue
            stats = {
                stat: int(row[stat])
                for stat in PLAYER_STATS.values()
                if isinstance(row.get(stat), int)
            }
            players[name] = (team, stats)
    return MapResult(t1, t2, players)


def actual_value(
    line: Cs2Line, maps: list[MapResult], team1: str, team2: str
) -> float | None:
    """What happened for this line's quantity; None if it cannot be told."""

    def team_rounds(side: str, rounds: list[MapResult]) -> int:
        return sum(m.t1_rounds if side == "T1" else m.t2_rounds for m in rounds)

    fam = line.family
    if line.map_nr:
        if line.map_nr > len(maps):
            return None  # map not played: the line is void
        mp = maps[line.map_nr - 1]
        if fam in ("map_winner", "map_rounds_handicap"):
            return float(mp.t1_rounds - mp.t2_rounds)
        if fam == "map_rounds_total":
            return float(mp.t1_rounds + mp.t2_rounds)
        side = _team_of(line.subject, team1, team2)
        if fam == "map_team_rounds" and side:
            return float(team_rounds(side, [mp]))
        if fam == "team_kills" and side:
            if not mp.players:
                return None
            return float(
                sum(s.get("kills", 0) for t, s in mp.players.values() if t == side)
            )
        if fam.startswith("player_"):
            hit = mp.players.get(normalize_name(line.subject))
            stat = fam.removeprefix("player_")
            if hit is None or stat not in hit[1]:
                return None
            return float(hit[1][stat])
        return None
    t1_maps = sum(1 for m in maps if m.t1_rounds > m.t2_rounds)
    t2_maps = sum(1 for m in maps if m.t2_rounds > m.t1_rounds)
    if fam in ("match_winner", "maps_handicap"):
        return float(t1_maps - t2_maps)
    if fam == "maps_total":
        return float(len(maps))
    if fam == "rounds_total":
        return float(team_rounds("T1", maps) + team_rounds("T2", maps))
    if fam == "rounds_handicap":
        return float(team_rounds("T1", maps) - team_rounds("T2", maps))
    side = _team_of(line.subject, team1, team2)
    if fam == "team_rounds" and side:
        return float(team_rounds(side, maps))
    if fam == "team_maps" and side:
        return float(t1_maps if side == "T1" else t2_maps)
    return None


def grade(line: Cs2Line, actual: float) -> str:
    """WIN / LOSS / VOID for this side, given the quantity's actual value.

    For winners and handicaps `actual` is team1 minus team2 (maps or rounds)
    and `line.line` is team1's handicap (0 for a winner).
    """
    if line.side in ("OVER", "UNDER"):
        if line.line is None or actual == line.line:
            return "VOID"
        over = actual > line.line
        return "WIN" if over == (line.side == "OVER") else "LOSS"
    margin = actual + (line.line or 0.0)
    if margin == 0:
        return "VOID"
    t1_wins = margin > 0
    return "WIN" if t1_wins == (line.side == "T1") else "LOSS"
