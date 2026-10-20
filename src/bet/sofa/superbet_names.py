"""A coupon leg named the way Superbet's screen names it.

The operator stakes from the screen, not from our family names. On
2026-10-15 a chat slip listed "Tampa - Seattle, Seattle +1.5 w 3. tercji"
(our `period_handicap -1.5 T2`, Superbet's "1. tercja - handicap" with the
outcome "Seattle Kraken (1.5)"), and the bet placed was the market next to
it on the screen, "3. tercja - Seattle Kraken - liczba goli: Poniżej 1.5" -
a different bet at a different price (1.21, not 1.26). A leg therefore
carries two strings in Superbet's own words:

    superbet_market     "3. tercja - Seattle Kraken - liczba goli"
    superbet_selection  "poniżej 1.5"

`names(leg, sides)` returns them, or None for a market this table does not
know (the caller keeps its old label - nothing is guessed). The market names
were read from Superbet's live offer (event odds `marketName` / outcome
`name`) on 2026-10-16: hockey 15243670, basketball 14845020, volleyball
15243619, CS2 15473681, tennis 15474093, football 14127682; the hockey /
basketball player names are SHADOW's own (`shadow.PLAYER_MARKETS`).

`sides` is (Superbet's team 1, team 2) - the board's `side_a` / `side_b`
for football and tennis (`board_sides`), where a leg's subject is Superbet's
name folded ("atletico madryt"); a measured sport's `match` already holds
Superbet's names, T1 first. A handicap outcome is written as Superbet writes
it, the side's own handicap in brackets with no plus sign ("Seattle Kraken
(1.5)", "Ingolstadt (-1.5)"): a measured sport's `line` is team 1's handicap
(`coupon_sports.display_line`), a tennis `handicap_games` line the subject's.
This module adds no number and changes no leg; it only names one.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from bet.sofa.market_mapper import fold

Sides = tuple[str, str]

_OU = {"OVER": "powyżej", "UNDER": "poniżej"}

# --- football / tennis: whole-match counts -----------------------------------
TOTALS: dict[str, str] = {
    "goals_total": "Liczba goli",
    "goals_1h_total": "1.połowa - liczba goli",
    "goals_2h_total": "2.połowa - liczba goli",
    "corners_total": "Liczba rzutów rożnych",
    "corners_1h_total": "1. połowa - liczba rzutów rożnych",
    "corners_2h_total": "2. połowa - liczba rzutów rożnych",
    "cards_points_total": "Liczba kartek",
    "shots_on_target_total": "Liczba celnych strzałów",
    "shots_on_target_1h_total": "1. połowa - liczba celnych strzałów",
    "shots_on_target_2h_total": "2. połowa - liczba celnych strzałów",
    "shots_total": "Liczba strzałów",
    "shots_1h_total": "1. połowa - liczba strzałów",
    "shots_2h_total": "2. połowa - liczba strzałów",
    "offsides_total": "Liczba spalonych",
    "offsides_1h_total": "1. połowa - liczba spalonych",
    "offsides_2h_total": "2. połowa - liczba spalonych",
    "fouls_total": "Liczba fauli",
    "fouls_1h_total": "1. połowa - liczba fauli",
    "fouls_2h_total": "2. połowa - liczba fauli",
    "saves_total": "Liczba obronionych strzałów przez bramkarza",
    "saves_1h_total": "1. połowa - liczba obronionych strzałów przez bramkarza",
    "throw_ins_total": "Liczba rzutów z autu",
    "throw_ins_1h_total": "1. połowa - liczba rzutów z autu",
    "throw_ins_2h_total": "2. połowa - liczba rzutów z autu",
    "goal_kicks_total": "Liczba wybić od bramki",
    "goal_kicks_1h_total": "1. połowa - liczba wybić od bramki",
    "goal_kicks_2h_total": "2. połowa - liczba wybić od bramki",
    "tackles_total": "Liczba odbiorów",
    "red_cards_total": "Liczba czerwonych kartek",
    "penalties_total": "Liczba przyznanych rzutów karnych",
    "games_total": "Liczba gemów",
    "games_set1_total": "1. set - liczba gemów",
    "games_set2_total": "2. set - liczba gemów",
    "sets_total": "Liczba setów",
    "tiebreaks_total": "Liczba tiebreaków",
    "aces_total": "Liczba asów",
    "aces_set1_total": "1. set - liczba asów",
    "aces_set2_total": "2. set - liczba asów",
    "double_faults_total": "Liczba podwójnych błędów",
    "double_faults_set1_total": "1. set - liczba podwójnych błędów",
    "double_faults_set2_total": "2. set - liczba podwójnych błędów",
    "serve_points_total": "Liczba asów + podwójnych błędów",
    "serve_points_set1_total": "1. set - liczba asów + podwójnych błędów",
    "serve_points_set2_total": "2. set - liczba asów + podwójnych błędów",
}

# --- football / tennis: one side's count ({T} = the side, Superbet's name) ---
SIDE_COUNTS: dict[str, str] = {
    "goals_for": "{T} - liczba goli",
    "goals_1h_for": "1.połowa - {T} - liczba goli",
    "goals_2h_for": "2.połowa - {T} - liczba goli",
    "corners_for": "{T} - liczba rzutów rożnych",
    "corners_1h_for": "1. połowa - {T} liczba rzutów rożnych",
    "corners_2h_for": "2. połowa - {T} liczba rzutów rożnych",
    "cards_points_for": "{T} - liczba kartek",
    "shots_on_target_for": "Liczba celnych strzałów - {T}",
    "shots_on_target_1h_for": "1. połowa - {T} liczba celnych strzałów",
    "shots_on_target_2h_for": "2. połowa - {T} liczba celnych strzałów",
    "shots_for": "Liczba strzałów {T}",
    "shots_1h_for": "1. połowa - {T} liczba strzałów",
    "shots_2h_for": "2. połowa - {T} liczba strzałów",
    "fouls_for": "Liczba fauli - {T}",
    "fouls_1h_for": "1. połowa - {T} liczba fauli",
    "fouls_2h_for": "2. połowa - {T} liczba fauli",
    "offsides_for": "Spalone - {T}",
    "offsides_1h_for": "1. połowa - {T} liczba spalonych",
    "offsides_2h_for": "2. połowa - {T} liczba spalonych",
    "saves_for": "{T} - liczba obronionych strzałów przez bramkarza",
    "saves_1h_for": "1. połowa - {T} - liczba obronionych strzałów przez bramkarza",
    "throw_ins_for": "Liczba rzutów z autu - {T}",
    "throw_ins_1h_for": "1. połowa - {T} liczba rzutów z autu",
    "throw_ins_2h_for": "2. połowa - {T} liczba rzutów z autu",
    "goal_kicks_for": "Liczba wybić z bramki {T}",
    "tackles_for": "{T} - Liczba odbiorów",
    "games_won_for": "{T} liczba gemów",
    "games_won_set1_for": "1. set - {T} liczba gemów",
    "games_won_set2_for": "2. set - {T} liczba gemów",
    "games_won_set3_for": "3. set - {T} liczba gemów",
    "aces_for": "{T} liczba asów",
    "aces_set1_for": "1. set - {T} liczba asów",
    "aces_set2_for": "2. set - {T} liczba asów",
    "double_faults_for": "{T} liczba podwójnych błędów",
    "double_faults_set1_for": "1. set - {T} - liczba podwójnych błędów",
    "double_faults_set2_for": "2. set - {T} - liczba podwójnych błędów",
    "serve_points_for": "{T} liczba asów + podwójnych błędów",
    "serve_points_set1_for": "1. set - {T} liczba asów + podwójnych błędów",
    "serve_points_set2_for": "2. set - {T} liczba asów + podwójnych błędów",
}

# --- football players (the subject is Superbet's "Surname, Name") ------------
PLAYER_COUNTS: dict[str, str] = {
    "player_shots_for": "Zawodnik - liczba strzałów",
    "player_shots_on_target_for": "Zawodnik - liczba celnych strzałów",
    "player_assists_for": "Zawodnik - liczba asyst",
    "player_fouls_for": "Zawodnik - liczba popełnionych fauli",
    "player_tackles_for": "Zawodnik - liczba odbiorów",
    "player_interceptions_for": "Zawodnik - liczba przechwytów",
    "player_offsides_for": "Zawodnik - liczba spalonych",
    "player_fouls_drawn_for": "Zawodnik - liczba fauli na zawodniku",
    "player_shots_outside_box_for": "Zawodnik - liczba strzałów spoza pola karnego",
    "player_sot_outside_box_for":
        "Zawodnik - liczba celnych strzałów spoza pola karnego",
    "player_headed_shots_for": "Zawodnik - liczba strzałów głową",
    "player_sot_headed_for": "Zawodnik - liczba celnych strzałów głową",
    "player_left_foot_shots_for": "Zawodnik - liczba strzałów lewą nogą",
    "player_sot_left_foot_for": "Zawodnik - liczba celnych strzałów lewą nogą",
    "player_right_foot_shots_for": "Zawodnik - liczba strzałów prawą nogą",
    "player_sot_right_foot_for": "Zawodnik - liczba celnych strzałów prawą nogą",
}

# --- measured sports, by Superbet market id ----------------------------------
# {N} the period / quarter / set, {T1} / {T2} the teams. A selection kind:
# "ou" over / under, "hcp" a handicap, "code" 1 / X / 2 / 1X ..., "named" the
# team's name, "period_code" "1.tercja - 1", "period_named" "1. kwarta -
# <team>", "parity", "yes_no".
SPORT_MARKETS: dict[str, dict[int, tuple[str, str]]] = {
    "hockey": {
        630: ("Zwycięzca (z dogrywką i rzutami karnymi)", "code"),
        623: ("Liczba goli", "ou"),
        658: ("{T1} - liczba goli", "ou"),
        652: ("{T2} - liczba goli", "ou"),
        604: ("Handicap", "hcp"),
        649: ("{N}. tercja - liczba goli", "ou"),
        674: ("{N}. tercja - {T1} liczba goli", "ou"),
        638: ("{N}. tercja - {T2} - liczba goli", "ou"),
        678: ("{N}. tercja - handicap", "hcp"),
        662: ("X.tercja - zakład bez remisu", "period_named:{N}.tercja"),
        640: ("Mecz", "code"),
        660: ("X.tercja - zwycięzca", "period_code:{N}.tercja"),
        606: ("Podwójna szansa", "code"),
        616: ("{N}. tercja - podwójna szansa", "code"),
    },
    "basketball": {
        759: ("Zwycięzca (z dogrywką)", "code"),
        753: ("Liczba punktów (z dogrywką)", "ou"),
        768: ("Handicap (z dogrywką)", "hcp"),
        758: ("{T1} liczba punktów (z dogrywką)", "ou"),
        776: ("{T2} liczba punktów (z dogrywką)", "ou"),
        748: ("1. połowa - liczba punktów", "ou"),
        773: ("1. połowa - handicap", "hcp"),
        200804: ("1. połowa - liczba punktów {T1}", "ou"),
        200797: ("1. połowa - liczba punktów {T2}", "ou"),
        765: ("1. połowa - zakład bez remisu", "named"),
        233404: ("2. połowa - liczba punktów", "ou"),
        233405: ("2. połowa - handicap", "hcp"),
        233806: ("2. połowa - {T1} liczba punktów", "ou"),
        233807: ("2. połowa - {T2} liczba punktów", "ou"),
        233499: ("2. połowa - zakład bez remisu", "named"),
        788: ("{N}. kwarta - liczba punktów", "ou"),
        774: ("{N}. kwarta - handicap", "hcp"),
        200802: ("{N}. kwarta - {T1} liczba punktów", "ou"),
        200795: ("{N}. kwarta - {T2} liczba punktów", "ou"),
        772: ("X kwarta - zakład bez remisu", "period_named:{N}. kwarta"),
        777: ("Mecz", "code"),
        763: ("1.Połowa - 1X2", "code"),
        233400: ("2.Połowa - 1X2", "named"),
        779: ("X. kwarta - 1X2", "period_code:{N}. kwarta"),
        775: ("Nieparzysta/parzysta liczba punktów (z dogrywką)", "parity"),
        230634: ("{T1} nieparzysta/parzysta liczba punktów (z dogrywką)", "parity"),
        230640: ("{T2} nieparzysta/parzysta liczba punktów (z dogrywką)", "parity"),
        # read by name (shadow.DERIVED_MARKETS), synthetic ids
        -1: ("Podwójna szansa", "code"),
        -2: ("1. połowa - podwójna szansa", "code"),
        -3: ("2. połowa - podwójna szansa", "code"),
        -4: ("{N}. kwarta - podwójna szansa", "code"),
    },
    "volleyball": {
        745: ("Zwycięzca", "code"),
        230058: ("Liczba setów", "ou"),
        100082: ("Handicap setowy", "hcp"),
        230060: ("Liczba punktów", "ou"),
        1069: ("Handicap punkty", "hcp"),
        744: ("X set - zwycięzca", "period_named:{N}. set"),
        782: ("{N}. set - liczba punktów", "ou"),
        785: ("Dokładny wynik", "raw"),
        200896: ("Nieparzysta/Parzysta liczba punktów", "parity"),
        781: ("{N}. set -nieparzysta/parzysta liczba punktów", "parity"),
        100077: ("Czy {N}. set zostanie rozstrzygnięty na dodatkowe punkty "
                 "przewagi?", "yes_no"),
        -11: ("{T1} wygra seta", "yes_no"),
        -12: ("{T2} wygra seta", "yes_no"),
        -13: ("{T1} wygra dokładnie {K}", "yes_no"),
        -14: ("{T2} wygra dokładnie {K}", "yes_no"),
        -15: ("Dokładna liczba setów", "sets_count"),
    },
}

# CS2 by family ({N} the map, {S} the subject - a team or a player).
CS2_MARKETS: dict[str, tuple[str, str]] = {
    "match_winner": ("Zwycięzca (z dogrywką)", "named"),
    "map_winner": ("Mapa X - zwycięzca (z dogrywką)", "period_named:{N}."),
    "maps_total": ("Liczba map", "ou"),
    "maps_handicap": ("Handicap map", "hcp"),
    "exact_maps": ("Dokładny wynik", "raw"),
    "rounds_total": ("Liczba rund (z dogrywką)", "ou"),
    "rounds_handicap": ("Handicap rund (z dogrywką)", "hcp"),
    "team_rounds": ("{S} liczba rund (z dogrywką)", "ou"),
    "team_maps": ("{S} liczba map", "ou"),
    "map_rounds_total": ("{N}.mapa - Liczba rund (z dogrywką)", "ou"),
    "map_rounds_handicap": ("{N}. mapa - Handicap rund (z dogrywką)", "hcp"),
    "map_team_rounds": ("{N}.mapa - {S} liczba rund (z dogrywką)", "ou"),
    "map_rounds_odd_even": ("X mapa - nieparzysta/parzysta liczba rund "
                            "(z dogrywką)", "parity:{N}."),
    "team_kills": ("{N}.mapa - {S} - liczba zabójstw (z dogrywką)", "ou"),
    "player_kills": ("{N}.mapa - liczba zabójstw zawodnika (z dogrywką)", "player"),
    "player_deaths": ("{N}.mapa - liczba śmierci zawodnika (z dogrywką)", "player"),
    "player_assists": ("{N}.mapa - liczba asyst zawodnika (z dogrywką)", "player"),
    "player_headshots": ("{N}.mapa - liczba headshotów zawodnika (z dogrywką)",
                         "player"),
}

FIELD_MARKET = "superbet_market"
FIELD_SELECTION = "superbet_selection"


def _num(value: Any) -> str:
    return f"{float(value):g}"


def _strip_women(name: str) -> str:
    folded = fold(name)
    return folded[:-4].strip() if folded.endswith(" (k)") else folded


def side_of(subject: str, sides: Sides) -> int | None:
    """0 / 1 for the side a folded subject names, None when neither or both."""
    want = _strip_women(subject)
    if not want:
        return None
    hits = [i for i, s in enumerate(sides) if _strip_women(s) == want]
    if len(hits) == 1:
        return hits[0]
    # a token-wise containment for names the board shortens or extends
    # ("heerenveen" / "SC Heerenveen"); both sides matching is no answer
    tokens = set(want.split())
    hits = [i for i, s in enumerate(sides)
            if tokens and (tokens <= set(_strip_women(s).split())
                           or set(_strip_women(s).split()) <= tokens)]
    return hits[0] if len(hits) == 1 else None


def _match_sides(leg: Mapping[str, Any]) -> Sides | None:
    parts = str(leg.get("match") or "").split(" - ", 1)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else None


def _name(subject: str, sides: Sides | None) -> str:
    """The side a subject names, in Superbet's spelling where it is known;
    else the subject as written (a player's own name), capitalised if
    folded."""
    if sides is not None:
        i = side_of(subject, sides)
        if i is not None:
            return sides[i]
    return subject if subject != subject.lower() else subject.title()


def _code(code: str, sides: Sides | None) -> str:
    """A 1 / X / 2 / 1X / X2 / 12 selection with the teams it stands for."""
    if sides is None:
        return code
    home, away = sides
    meaning = {"1": home, "2": away, "X": "remis", "1X": f"{home} lub remis",
               "X2": f"remis lub {away}", "12": f"{home} lub {away}"}.get(code)
    return f"{code} ({meaning})" if meaning else code


def _hcp(side: str, line: Any, sides: Sides | None) -> str | None:
    if side not in ("T1", "T2") or line is None or sides is None:
        return None
    own = float(line) if side == "T1" else -float(line)
    return f"{sides[0 if side == 'T1' else 1]} ({own:g})"


def _football_tennis(leg: Mapping[str, Any], sides: Sides | None
                     ) -> tuple[str, str] | None:
    from bet.sofa import football_score_markets as fsm
    from bet.sofa import tennis_sets

    market = str(leg.get("market") or "")
    subject = str(leg.get("subject") or "")
    direction = str(leg.get("direction") or "")
    line = leg.get("line")
    ou = _OU.get(direction)

    if market in TOTALS and ou and line is not None:
        return TOTALS[market], f"{ou} {_num(line)}"
    if market in SIDE_COUNTS and ou and line is not None and subject:
        return (SIDE_COUNTS[market].format(T=_name(subject, sides)),
                f"{ou} {_num(line)}")
    if market in PLAYER_COUNTS and ou and line is not None and subject:
        return PLAYER_COUNTS[market], f"{subject} - {ou} {_num(line)}"

    if market == "double_chance" and subject in ("1X", "X2", "12"):
        if direction == "OVER":
            return "Podwójna szansa", _code(subject, sides)
        left_out = {"1X": "2", "X2": "1", "12": "X"}[subject]
        return "Mecz", _code(left_out, sides)
    if market == "result_1x2" and subject in ("1", "2"):
        if direction == "OVER":
            return "Mecz", _code(subject, sides)
        return "Podwójna szansa", _code("X2" if subject == "1" else "1X", sides)
    if market == "draw_no_bet" and sides is not None and direction in _OU:
        return "Zakład bez remisu", sides[0 if direction == "OVER" else 1]
    if market == "first_goal" and subject in ("1", "2") and sides is not None:
        return "1. gol", sides[0 if subject == "1" else 1]

    if market in ("match_won_for", "set1_won_for", "set2_won_for") \
            and sides is not None and direction in _OU:
        i = side_of(subject, sides)
        if i is None:
            return None
        winner = sides[i if direction == "OVER" else 1 - i]
        if market == "match_won_for":
            return "Zwycięzca", f"{'1' if winner == sides[0] else '2'} ({winner})"
        n = market[3]
        return "X. set - zwycięzca", f"{n}. set - {winner}"
    if market == tennis_sets.SET_SCORE and direction == "OVER" and sides is not None:
        parsed = tennis_sets.split_score_subject(subject)
        i = side_of(parsed[0], sides) if parsed else None
        if parsed is None or i is None:
            return None
        score = parsed[1] if i == 0 else tennis_sets.flip(parsed[1])
        return "Dokładny wynik", f"{score} ({parsed[0]} {parsed[1]})"
    if market == "handicap_games" and direction == "OVER" and line is not None:
        return "Handicap gemy", f"{_name(subject, sides)} ({float(line):g})"
    if market == "most_games" and direction == "OVER" and subject:
        return "Najwięcej gemów", _name(subject, sides)

    # football score markets and set_score_not: their own Superbet wording
    label = fsm.display_market(leg)
    if label is None:
        return None
    if label.endswith(" (Tak)"):
        return label[: -len(" (Tak)")], "Tak"
    head, sep, tail = label.partition(": ")
    return (head, tail) if sep else (label, "")


def _selection(kind: str, leg: Mapping[str, Any], sides: Sides | None,
               n: int) -> str | None:
    side = str(leg.get("side") or leg.get("direction") or "")
    line = leg.get("line")
    kind, _, scope = kind.partition(":")
    scope = scope.format(N=n)
    if kind in ("ou", "player"):
        ou = _OU.get(side)
        if ou is None or line is None:
            return None
        pick = f"{ou} {_num(line)}"
        return f"{leg.get('subject')} - {pick}" if kind == "player" else pick
    if kind == "hcp":
        return _hcp(side, line, sides)
    if kind in ("code", "period_code"):
        code = {"T1": "1", "T2": "2", "DRAW": "X"}.get(side, side)
        if code not in ("1", "2", "X", "1X", "X2", "12"):
            return None
        return f"{scope} - {_code(code, sides)}" if scope else _code(code, sides)
    if kind in ("named", "period_named"):
        if sides is None:
            return None
        name = {"T1": sides[0], "T2": sides[1], "DRAW": "remis"}.get(side)
        if name is None:
            return None
        return f"{scope} - {name}" if scope else name
    if kind == "parity":
        word = {"ODD": "nieparzysta", "EVEN": "parzysta"}.get(side)
        if word is None:
            return None
        return f"{scope} - {word}" if scope else word
    if kind == "yes_no":
        return {"YES": "Tak", "NO": "Nie", "OVER": "Tak", "UNDER": "Nie"}.get(side)
    if kind == "sets_count":
        return side.split("=", 1)[1] if side.startswith("SETS=") else None
    if kind == "raw":
        return side or None
    return None


def _sport(leg: Mapping[str, Any]) -> tuple[str, str] | None:
    from bet.sofa.shadow import PLAYER_MARKETS

    sport = str(leg.get("sport") or "")
    sides = _match_sides(leg)
    family = str(leg.get("family") or leg.get("market") or "")
    if sport == "cs2":
        spec = CS2_MARKETS.get(family)
        n = int(leg.get("map_nr") or leg.get("period") or 0)
        if spec is None:
            return None
        market = spec[0].format(N=n, S=leg.get("subject") or "")
        pick = _selection(spec[1], leg, sides, n)
        return (market, pick) if pick is not None else None
    mid = leg.get("market_id")
    if mid is None:
        return None
    mid = int(mid)
    n = int(leg.get("period") or 0)
    player = PLAYER_MARKETS.get(sport, {}).get(mid)  # type: ignore[call-overload]
    if player is not None:
        pick = _selection("player", leg, sides, n)
        name = str(player.name)
        return (name[:1].upper() + name[1:], pick) if pick is not None else None
    base = -(abs(mid) // 100) if mid < -100 else mid  # a DC pair's own id
    spec = SPORT_MARKETS.get(sport, {}).get(base)
    if spec is None or sides is None:
        return None
    k = ""
    if base in (-13, -14) and leg.get("line") is not None:
        sets = int(float(leg["line"]))
        k = f"{sets} {'set' if sets == 1 else 'sety'}"
    market = spec[0].format(N=n, T1=sides[0], T2=sides[1], K=k)
    pick = _selection(spec[1], leg, sides, n)
    return (market, pick) if pick is not None else None


def names(leg: Mapping[str, Any], sides: Sides | None = None
          ) -> tuple[str, str] | None:
    """(Superbet's market name, the selection) of a leg, or None.
    `sides`: Superbet's (team 1, team 2) for a football / tennis leg."""
    sport = str(leg.get("sport") or "football")
    if sport in ("football", "tennis"):
        return _football_tennis(leg, sides or _match_sides(leg))
    return _sport(leg)


def label(leg: Mapping[str, Any]) -> str | None:
    """"<market>: <selection>" as stamped on the leg (`annotate`), or None."""
    market, pick = leg.get(FIELD_MARKET), leg.get(FIELD_SELECTION)
    if not market:
        return None
    return f"{market}: {pick}" if pick else str(market)


def board_sides(run: Path) -> dict[int, Sides]:
    """Sofascore event id -> Superbet's (side_a, side_b), from the day's
    02_fixtures.json (the Superbet ids RESOLVE joined) and 01_board.json.
    {} when either file is missing or unreadable."""
    try:
        board = json.loads((run / "01_board.json").read_text(encoding="utf-8"))
        fixtures = json.loads((run / "02_fixtures.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    by_sb = {str(b.get("superbet_event_id")): (str(b.get("side_a") or ""),
                                               str(b.get("side_b") or ""))
             for b in board if isinstance(b, dict)}
    out: dict[int, Sides] = {}
    for f in fixtures if isinstance(fixtures, list) else []:
        sid = f.get("sofascore_event_id") if isinstance(f, dict) else None
        for sb in f.get("superbet_event_ids") or [] if isinstance(f, dict) else []:
            sides = by_sb.get(str(sb))
            if isinstance(sid, int) and sides and all(sides):
                out[sid] = sides
                break
    return out


def annotate(doc: dict[str, Any], sides_by_event: Mapping[int, Sides]) -> int:
    """Stamp `superbet_market` / `superbet_selection` on every single, leg,
    builder leg and removed leg of a coupon artifact (in place); a leg this
    module cannot name loses stale fields. Returns how many were named."""
    named = 0
    # (legs, the context a builder leg lacks: its builder's event and match)
    pools: list[tuple[Any, Mapping[str, Any]]] = [
        (doc.get(k) or [], {}) for k in ("singles", "legs", "removed_by_reads")]
    pools += [(b.get("legs") or [],
               {"sofascore_event_id": b.get("sofascore_event_id"),
                "match": b.get("match")})
              for b in doc.get("builders") or [] if isinstance(b, dict)]
    for pool, context in pools:
        for leg in pool:
            if not isinstance(leg, dict):
                continue
            seen = {**context, **leg}
            eid = seen.get("sofascore_event_id")
            got = names(seen, sides_by_event.get(eid) if isinstance(eid, int)
                        else None)
            if got is None:
                leg.pop(FIELD_MARKET, None)
                leg.pop(FIELD_SELECTION, None)
                continue
            leg[FIELD_MARKET], leg[FIELD_SELECTION] = got
            named += 1
    _name_references(doc)
    return named


def _ref_key(eid: Any, ref: Mapping[str, Any]) -> tuple[Any, ...]:
    line = ref.get("line")
    return (eid, str(ref.get("market") or ref.get("family") or ""),
            str(ref.get("subject") or ""),
            None if line is None else float(line),
            str(ref.get("direction") or ref.get("side") or ""),
            int(ref.get("period") or 0))


def _name_references(doc: dict[str, Any]) -> None:
    """The legs a single's peer note and a ladder's header point at
    (`peer.best`, `ladders[].rungs`, which carry no event id of their own)
    take the names of the singles they are; a ladder whose rungs share one
    market name carries it as its own."""
    singles = [s for s in doc.get("singles") or [] if isinstance(s, dict)]
    idx = {_ref_key(s.get("sofascore_event_id"), s): (s[FIELD_MARKET],
                                                      s.get(FIELD_SELECTION))
           for s in singles if s.get(FIELD_MARKET)}

    def stamp(eid: Any, ref: dict[str, Any]) -> str | None:
        got = idx.get(_ref_key(eid, ref))
        if got is None:
            ref.pop(FIELD_MARKET, None)
            ref.pop(FIELD_SELECTION, None)
            return None
        ref[FIELD_MARKET], ref[FIELD_SELECTION] = got
        return str(got[0])

    for s in singles:
        best = (s.get("peer") or {}).get("best")
        if isinstance(best, dict):
            stamp(s.get("sofascore_event_id"), best)
    for lad in doc.get("ladders") or []:
        if not isinstance(lad, dict):
            continue
        key = str(lad.get("group_key") or "")
        eid: Any = int(key[5:]) if key.startswith("sofa:") and key[5:].isdigit() \
            else None
        shown = {stamp(eid, r) for r in lad.get("rungs") or [] if isinstance(r, dict)}
        if len(shown) == 1 and None not in shown:
            lad[FIELD_MARKET] = shown.pop()
        else:
            lad.pop(FIELD_MARKET, None)
