# ruff: noqa: E501  - a rule table: regexes and the Polish notes the report prints; wrapped, neither reads.
"""MARKET COVERAGE - one label for every Superbet market name OFFER could not read.

A report, never a pipeline input (plan 2026-10-05 F1.1). OFFER keeps every
market name it cannot classify in ``04_offer.json`` ``unmapped_markets``
(one entry per fixture and name, `offer.classify_odd`); 27,627 of them on
2026-10-05. This module gives each one exactly one label:

* ``MAPPABLE`` - the statistic is already a sofa metric (``bet.sofa.metrics``)
  or a derived market on one (``bet.sofa.derived``), and only the name mapping
  (or a scope on an existing derived shape) is missing. ``note`` is the
  proposed metric.
* ``COMPUTABLE`` - derivable from history the cache already holds (set / half
  scores, goal and card incidents, per-period /statistics, /lineups), but it
  needs a new quantity or a new pricer (a distribution, a joint of two sides,
  a result model). ``note`` says what is needed.
* ``NOT_COMPUTABLE`` - no source we hold records the quantity. ``note`` is
  the reason.
* ``UNCLASSIFIED`` - no rule matched. Counted, never hidden: the criterion
  is that this bucket is empty.

Superbet's own combinations (names joined with ``;`` - its pre-built
SuperBets slips) are classified part by part: NOT_COMPUTABLE when any part
is, UNCLASSIFIED when any part is unknown, COMPUTABLE otherwise (the parts'
joint distribution is what would be needed - a combination is never one
statistic, and its price is Superbet's own, never the product of the legs).

Names are compared folded (`market_mapper.fold`, which handles "ł" that NFKD
cannot) with the fixture's two side names replaced by ``{a}`` / ``{b}`` and
every number but an ordinal ("1. set", "2.polowa") replaced by ``#``.

Nothing here changes what OFFER maps or what the coupon selects: a MAPPABLE
label is a proposal. Mapping a new market adds rows to a build, so it goes
through the epochs (``bet.sofa.epochs``) between days, never mid-day.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from bet.sofa.market_mapper import PLAYER_MARKET_NAMES, classify_market, fold

Label = Literal["MAPPABLE", "COMPUTABLE", "NOT_COMPUTABLE", "UNCLASSIFIED"]
LABELS: tuple[Label, ...] = ("MAPPABLE", "COMPUTABLE", "NOT_COMPUTABLE", "UNCLASSIFIED")

COMBO_FAMILY = "superbet_combo"
UNCLASSIFIED_FAMILY = "unclassified"


@dataclass(frozen=True)
class Rule:
    pattern: re.Pattern[str]
    label: Label
    family: str
    note: str


@dataclass(frozen=True)
class Classification:
    label: Label
    family: str
    note: str
    template: str
    parts: tuple[Classification, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

# An ordinal is kept: "1. set" and "3. set" are different quantities (only
# sets 1 and 2 have declared metrics), so the set / half number must survive.
_ORDINAL_TAIL = re.compile(r"\.\s?[a-z]")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _number_or_ordinal(m: re.Match[str], text: str) -> str:
    if _ORDINAL_TAIL.match(text, m.end()):
        return m.group(0)
    return "#"


def template_of(name: str, sides: Sequence[str]) -> str:
    """The folded name with the sides as {a}/{b} and numbers as '#'."""
    text = fold(name)
    for side, tag in sorted(
        ((fold(s), t) for s, t in zip(sides, _side_tags(len(sides)), strict=True) if s),
        key=lambda x: -len(x[0]),
    ):
        text = re.sub(r"(?<![a-z0-9])" + re.escape(side) + r"(?![a-z0-9])", tag, text)
    text = _NUMBER.sub(lambda m: _number_or_ordinal(m, text), text)
    return re.sub(r"\s+", " ", text).strip()


def _side_tags(n: int) -> list[str]:
    # sides arrive as [a, b, a', b', ...] (board names, then Sofascore names)
    return ["{a}" if i % 2 == 0 else "{b}" for i in range(n)]


# ---------------------------------------------------------------------------
# Rules. Order matters: the first match wins, team patterns ({s}) before the
# loose player patterns that would read a team as a player.
# ---------------------------------------------------------------------------

S = r"\{[ab]\}"  # a side
P = r"(?!\{[ab]\})[^;]+?"  # a player (or a manager) named in the market - never a side
OU = r"(?:powyzej|ponizej)"
H = r"[12]\.\s?polow\w*"  # a half

# Sources, cited in the notes so the report says what each label rests on.
SRC_GOALS = "historia goli (wynik + połowy w listingu, goal_for obu stron)"
SRC_INC = "incydenty Sofascore (gole/kartki z minutą i zawodnikiem, sofa_event_stats.incidents_json)"
SRC_LINEUPS = "/lineups (statystyki zawodnika; w cache ~4,5 tys. meczów piłki)"
SRC_SETS = "wyniki setów (homeScore.periodN + periodNTieBreak w listingu)"
NEED_RESULT = "model wyniku (łączny rozkład goli obu stron) - " + SRC_GOALS
NEED_SET_MODEL = "model setów/gemów z " + SRC_SETS
NEED_JOINT = "łączny rozkład części (jak combined_probability buildera)"

# 2026-10-14: Sofascore's /point-by-point IS a source - every game's server,
# winner and running points (bet.sofa.point_by_point, sofa_event_extra kind
# point_by_point, scripts/sofa/backfill_event_extra.py). Measured
# (scripts/sofa/measure_tennis_game_order.py, ~7,800 matches): a serve-hold
# model forecasts these, but over-states at the top - no curve bucket clears
# 0.70 yet (docs/sofa/evidence/tennis_game_order_2026-10-14.md).
SRC_PBP = "/point-by-point (sofa_event_extra, bet.sofa.point_by_point)"
NEED_POINTS = ("model punktu serwisowego (servicePointsScored) - " + SRC_PBP
               + "; zmierzone: do 0,60 nie dochodzi")
NEED_GAME_ORDER = ("model utrzymań serwisu (serviceGamesWon) - " + SRC_PBP
                   + "; zmierzone: na górze przeszacowuje, żaden kubełek >= 0,70")
NC_EVENT_ORDER = (
    "brak kolejności/minuty zdarzeń innych niż gole i kartki "
    "(incydenty Sofascore nie zawierają rożnych, fauli, strzałów, autów, wybić, spalonych)"
)
# 2026-10-14: every shot's place and body part come from /shotmap
# (bet.sofa.shot_detail, sofa_event_extra kind shotmap); read by OFFER behind
# epochs.SHOT_DETAIL_MARKETS_FROM_UTC (docs/sofa/evidence/shot_detail_2026-10-14.md).
NEED_SHOT_DETAIL = ("miejsce / część ciała strzału z /shotmap (bet.sofa.shot_detail); "
                    "czytane przez OFFER za przełącznikiem SHOT_DETAIL_MARKETS")
NC_VAR = "brak źródła: incydent varDecision zapisuje decyzję, nie podejście sędziego do monitora"
NC_SPECIAL = "brak źródła w danych Sofascore (zdarzenie spoza statystyk meczu)"
NC_BOOST = "promocja Superbetu bez zdefiniowanej wielkości (boost; osobny snapshot run_boosts)"


def _r(pattern: str, label: Label, family: str, note: str) -> Rule:
    return Rule(re.compile("^(?:" + pattern + ")$"), label, family, note)


def _m(pattern: str, family: str, metric: str) -> Rule:
    return _r(pattern, "MAPPABLE", family, metric)


def _c(pattern: str, family: str, need: str) -> Rule:
    return _r(pattern, "COMPUTABLE", family, need)


def _n(pattern: str, family: str, reason: str) -> Rule:
    return _r(pattern, "NOT_COMPUTABLE", family, reason)


COMMON_RULES: list[Rule] = [
    _n(r"boost", "boost", NC_BOOST),
]

FOOTBALL_RULES: list[Rule] = [
    # --- ladders we already price, written the way Superbet's combinations
    # word them (the parts of ";" names) ---------------------------------
    _m(OU + r" # gol[ai] w meczu", "fb.goals_total", "goals_total"),
    _m(OU + r" # gol[ai] w " + H, "fb.goals_half_total", "goals_1h_total / goals_2h_total"),
    _m(S + r" strzeli " + OU + r" # gol[ai]", "fb.goals_for", "goals_for"),
    _m(S + r" strzeli " + OU + r" # gol[ai] w " + H, "fb.goals_half_for", "goals_1h_for / goals_2h_for"),
    _m(r"obie druzyny strzela gola", "fb.btts", "both_over_goals 0.5"),
    _m(OU + r" # rz\.roznych w meczu", "fb.corners_total", "corners_total"),
    _m(S + r" wykona " + OU + r" # rz\.roznych", "fb.corners_for", "corners_for"),
    _m(S + r" wykona wiecej rz\.roznych", "fb.most_corners", "most_corners"),
    _m(r"kazda z druzyn powyzej # rz\.roznych", "fb.both_over_corners", "both_over_corners"),
    _m(OU + r" # kartek w meczu", "fb.cards_total", "cards_points_total"),
    _m(S + r" otrzyma " + OU + r" # kartek", "fb.cards_for", "cards_points_for"),
    _m(r"kazda z druzyn powyzej # kartek", "fb.both_over_cards", "both_over_cards_points"),
    _m(OU + r" # celnych strzalow w meczu", "fb.sot_total", "shots_on_target_total"),
    _m(S + r" " + OU + r" # celnych strzalow", "fb.sot_for", "shots_on_target_for"),
    _m(S + r" najwiecej celnych strzalow", "fb.most_sot", "most_shots_on_target"),
    _m(S + r" otrzyma wiecej kartek", "fb.most_cards", "most_cards_points"),
    _m(r"kazda z druzyn powyzej # celnych strzalow", "fb.both_over_sot", "both_over_shots_on_target"),
    _m(OU + r" # strzalow w meczu", "fb.shots_total", "shots_total"),
    _m(S + r" odda " + OU + r" # strzalow w meczu", "fb.shots_for", "shots_for"),
    _m(OU + r" # spalonych w meczu", "fb.offsides_total", "offsides_total"),
    _m(OU + r" # fauli w meczu", "fb.fouls_total", "fouls_total"),
    _m(S + r" " + OU + r" # fauli", "fb.fouls_for", "fouls_for"),
    _m(OU + r" # odbiorow w meczu", "fb.tackles_total", "tackles_total"),
    _m(S + r" (?:wykona )?" + OU + r" # odbiorow(?: w meczu)?", "fb.tackles_for", "tackles_for"),
    # --- yes/no forms of ladders we hold ---------------------------------
    _m(S + r" strzeli gola", "fb.team_scores", "goals_for OVER 0.5 (tak/nie)"),
    _m(H + r" - " + S + r" strzeli gola", "fb.team_scores_half", "goals_1h_for / goals_2h_for OVER 0.5 (tak/nie)"),
    _m(H + r" - obie druzyny strzela", "fb.btts_half",
       "both_over_goals w połowie (zakres połowy na kształcie both_over; goals_1h_for / goals_2h_for są metrykami)"),
    _m(r"kazda z druzyn powyzej x obronionych strzalow przez bramkarza", "fb.both_over_saves",
       "both_over_saves (saves_for jest metryką; brak nazwy w _DERIVED_METRIC_NAMES)"),
    _m(H + r" - kazda z druzyn powyzej x obronionych strzalow przez bramkarza", "fb.both_over_saves_half",
       "both_over_saves_1h (saves_1h_for jest metryką)"),
    _m(r"kazda druzyna powyzej x rzutow z autu", "fb.both_over_throw_ins",
       "both_over_throw_ins (throw_ins_for; Superbet pisze 'Każda drużyna', nie 'Każda z drużyn')"),
    _m(r"kazda druzyna powyzej x wybic od bramki", "fb.both_over_goal_kicks",
       "both_over_goal_kicks (goal_kicks_for)"),
    _m(r"kazda z druzyn powyzej x odbiorow", "fb.both_over_tackles", "both_over_tackles (tackles_for)"),
    _m(H + r" - rzuty rozne - handicap", "fb.handicap_corners_half",
       "handicap_corners_1h / _2h (corners_1h_for; handicap z zakresem połowy jak most_ w _MOST_SCOPED)"),
    _m(H + r" - liczba strzalow - handicap", "fb.handicap_shots_half", "handicap_shots_1h (shots_1h_for)"),
    _m(r"strzaly - handicap", "fb.handicap_shots", "handicap_shots (shots_for; wzorzec 'liczba X - handicap' nie łapie 'Strzały - Handicap')"),
    # --- player ladders inside combinations (the exact props we map) -------
    _m(P + r" powyzej # celnych strzalow", "fb.player_sot", "player_shots_on_target_for"),
    _m(P + r" powyzej # strzalow", "fb.player_shots", "player_shots_for"),
    _m(P + r" popelni powyzej # fauli", "fb.player_fouls", "player_fouls_for"),
    _m(P + r" powyzej # odbiorow", "fb.player_tackles", "player_tackles_for"),
    _m(H + r" - najwiecej (?:strzalow|celnych strzalow|fauli|rzutow roznych|spalonych)", "fb.most_half",
       "most_<metric>_1h / _2h (_MOST_SCOPED; *_1h_for / *_2h_for są metrykami)"),
    _c(r"awans|sposob awansu druzyny", "fb.advance",
       NEED_RESULT + " + dogrywka / karne (homeScore.overtime / penalties) i wynik pierwszego meczu"),
    _c(S + r" wygra|ktorakolwiek druzyna wygra|kto wygra pozostala czesc (?:meczu|" + H + r") \[#:#\]",
       "fb.result_other", NEED_RESULT),
    _c(H + r" - (?:parzyste/nieparzyste|podwojna szansa & obie druzyny strzela)", "fb.result_half_other", NEED_RESULT),
    _c(r"zawodnik - liczba podan", "fb.player_passes", "klucz totalPass w /lineups; brak metryki - " + SRC_LINEUPS),
    _c(r"zawodnik - strzeli gola do minuty #:#", "fb.player_goal_minute", "gol zawodnika z minutą - " + SRC_INC),
    _c(H + r" ?- liczba strzalow w obramowanie bramki", "fb.woodwork_half",
       "hitWoodwork w okresie 1ST/2ND /statistics (część meczów); brak metryki"),
    _m(r"liczba (?:celnych strzalow|strzalow|fauli|rzutow roznych|kartek|spalonych|asow) - h#h", "fb.most_h2h",
       "most_<metric> (_MOST_H2H; 'h2h' po zamianie cyfr) - classify_derived_market czyta tę nazwę z wyborem"),
    _m(H + r" - liczba (?:celnych strzalow|fauli|strzalow) - handicap", "fb.handicap_half",
       "handicap_<metric>_1h / _2h (metryki połów istnieją; handicap bez zakresu połowy w market_mapper)"),
    _m(H + r" - " + S + r" liczba wybic od bramki", "fb.goal_kicks_half_for",
       "goal_kicks_1h_for / goal_kicks_2h_for (metryki istnieją, brak wzorca nazwy)"),
    _c(r"kazdy z bramkarzy obroni #\+ strzalow w kazdej z polow", "fb.saves_halves",
       "goalkeeperSaves w okresach 1ST/2ND /statistics (saves_2h nie jest metryką)"),
    _c(r"(?:" + S + r" )?liczba podan", "fb.passes",
       "klucz passes w /statistics (dziś tylko znacznik pełnego feedu); brak metryki"),
    _c(H + r" - liczba goli handicap azjatycki", "fb.result_half", NEED_RESULT),
    _c(r"remis w meczu|" + S + r" wygra do zera|przynajmniej jedna z druzyn nie strzeli powyzej # goli",
       "fb.result_other", NEED_RESULT),
    _c(r"sposob (?:zwyciestwa|awansu)(?: druzyny|/ktorakolwiek druzyna)|final - zwyciezca"
       r"|ktora druzyna wygra mecz o 3\.\s?miejsce|czy bedzie seria rzutow karnych\?",
       "fb.advance", NEED_RESULT + " + dogrywka / karne (homeScore.overtime / penalties)"),
    _c(r"[1-9]\. rzut karny zostanie strzelony", "fb.penalties",
       "goal|penalty + inGamePenalty|missed - " + SRC_INC),
    _c(r"ktorykolwiek z zawodnikow odda #\+ (?:celnych )?strzalow", "fb.any_player",
       "maksimum po zawodnikach - " + SRC_LINEUPS),
    _c(P + r" strzeli gola do minuty #:#", "fb.player_goal_minute", "gol zawodnika z minutą - " + SRC_INC),
    _n(r"(?:kto|ktory zawodnik) (?:wykona|popelni|bedzie na) \d+\. (?:rzut rozny|faul|spalonym)(?: \(dodatkowe\))?"
       r"|" + H + r" - wykona \d+\. rzut rozny|\d+\. (?:celny strzal|faul|odbior|spalony|strzal|wybicie od bramki)",
       "fb.non_goal_event_timing", NC_EVENT_ORDER),
    # --- results and goal distributions: a score model on goal history ----
    _c(r"mecz|podwojna szansa|zaklad bez remisu|dokladny wynik|handicap|handicap #x#|multiwynik",
       "fb.result", NEED_RESULT),
    _c(H + r" - (?:#x#|podwojna szansa|zaklad bez remisu|handicap|handicap #x#|dokladny wynik"
       r"|dokladna liczba goli|liczba goli nieparzysta/parzysta|przedzial goli)",
       "fb.result_half", NEED_RESULT),
    _c(r"[12]\.\s?polowa/mecz(?: - .+| & .+)?|[12]\.\s?polowa lub mecz", "fb.ht_ft", NEED_RESULT),
    _c(r"(?:mecz|podwojna szansa) (?:&|lub) .+|mecz lub [12]\.\s?polowa liczba goli \(#\)",
       "fb.result_combo", NEED_RESULT),
    _c(r"obie druzyny strzela gola (?:&|lub) .+|liczba goli & obie druzyny strzela", "fb.btts_combo", NEED_RESULT),
    _c(H + r" liczba goli (?:&|lub) " + H + r" liczba goli|" + H + r" - liczba goli & liczba goli w meczu",
       "fb.goals_halves", NEED_RESULT),
    _c(S + r" - " + H + r" liczba goli (?:&|lub) (?:" + H + r" liczba goli|liczba goli w meczu)",
       "fb.goals_halves_for", NEED_RESULT),
    _c(S + r" - (?:dokladna liczba goli|liczba goli nieparzysta/parzysta|przedzial goli(?: w kazdej polowie)?)",
       "fb.goals_for_distribution", "rozkład goals_for (dokładna liczba, parzystość, przedziały) - " + SRC_GOALS),
    _c(H + r" - " + S + r" (?:przedzial goli|- dokladna liczba goli)", "fb.goals_half_for_distribution",
       "rozkład goals_1h_for / goals_2h_for - " + SRC_GOALS),
    _c(r"przedzial goli(?: w kazdej polowie)?|dokladna liczba goli|nieparzysta/parzysta liczba goli",
       "fb.goals_distribution", "rozkład goals_total (dokładna liczba, parzystość, przedziały) - " + SRC_GOALS),
    _c(r"polowa z (?:wieksza|najwieksza) liczba goli(?: " + S + r")?|w [12]\.\s?polowie padnie wiecej goli"
       r"|wynik dowolnej polowy meczu|remis w obu polowach|remis w jednej z polow|gol w obu polowach"
       r"|obie druzyny strzela gola - [12]\.polowa/[12]\.polowa|obie druzyny strzela w przynajmniej jednej polowie meczu",
       "fb.halves", NEED_RESULT),
    _c(S + r" (?:wygra mecz|wygra lub zremisuje(?: [12]\.\s?polowe)?|wygra obie polowy|wygra przynajmniej jedna polowe"
       r"|wygra jedna z polow|zdobedzie gola w obu polowach|strzeli w obu polowach)|" + S + r" lub " + S
       + r" wygra [12]\.\s?polowe",
       "fb.side_result", NEED_RESULT),
    _c(r"(?:" + S + r" wygra|remis) lub (?:ktorakolwiek druzyna zachowa czyste konto|obie druzyny strzela gola"
       r"|ponizej x goli w meczu|powyzej x goli w meczu)",
       "fb.result_or", NEED_RESULT),
    # --- the order and the minute of goals: goal incidents ------------------
    _c(r"[1-9]\. gol(?: \(przedzialy #-minutowe\)| & mecz)?|ostatni gol|[12]\. polowa - [1-9]\. gol"
       r"|[1-9]\. gol od #:# do #:# minuty|(?:liczba goli|gol|gole|mecz) od #:# do #:# minuty"
       r"|(?:liczba goli|mecz) - do x minuty|dokladny wynik w dowolnym momencie",
       "fb.goal_timing", "minuta/kolejność goli - " + SRC_INC),
    _c(S + r" (?:bedzie prowadzic w dowolnym momencie(?: meczu)?|strzeli co najmniej # gole z rzedu"
       r"|wygra wczesniej przegrywajac|wygra mecz przegrywajac w dowolnym momencie)",
       "fb.goal_sequence", "przebieg wyniku z kolejności goli - " + SRC_INC),
    _c(r"liczba goli samobojczych", "fb.own_goals", "goal|ownGoal - " + SRC_INC),
    _c(r"sposob zdobycia [1-9]\. gola", "fb.goal_method",
       "bodyPart / situation / goalType gola (footballPassingNetworkAction, ~26 tys. meczów) - " + SRC_INC),
    # --- cards, penalties, substitutions: card / goal incidents -------------
    _c(r"(?:" + H + r" - )?liczba czerwonych kartek(?: " + S + r")?", "fb.red_cards", "card|red, card|yellowRed - " + SRC_INC),
    _c(r"[12]\. polowa - (?:" + S + r" )?liczba kartek|" + H + r" - dokladna liczba kartek|dokladna liczba kartek"
       r"|[12]\. polowa - liczba kartek - handicap|[12]\. polowa - najwiecej kartek",
       "fb.cards_half_or_exact", "kartki w połowie / dokładna liczba z minutą kartki - " + SRC_INC),
    _c(r"(?:kartka|kartki|liczba kartek) od #:# do #:# minuty|[12]\. kartka", "fb.card_timing",
       "minuta kartki - " + SRC_INC),
    _c(r"(?:" + H + r" - )?(?:" + S + r" - )?liczba przyznanych rzutow karnych", "fb.penalties",
       "goal|penalty + inGamePenalty|missed - " + SRC_INC),
    _c(r"obie druzyny otrzymaja czerwona kartke|przyznany rzut karny, czerwona kartka & gol samobojczy"
       r"|czerwona kartka lub gol w doliczonym czasie [12]\. polowy"
       r"|ktorykolwiek zawodnik otrzyma kartke w doliczonym czasie [12]\. polowy",
       "fb.incident_specials", SRC_INC + " (addedTime)"),
    _c(r"kazda z druzyn wykorzysta wszystkie # zmian", "fb.substitutions", "substitution - " + SRC_INC),
    # --- distributions of team counts we hold ------------------------------
    _c(r"(?:" + H + r" - )?nieparzysta/parzysta liczba rzutow roznych|" + H + r" - przedzial rzutow roznych"
       r"|" + S + r" - przedzial rzutow roznych|liczba rzutow roznych - przedzialy",
       "fb.corners_distribution", "rozkład corners_* (parzystość, przedziały) z /statistics"),
    _c(r"(?:" + S + r" - )?liczba strzalow w obramowanie bramki", "fb.woodwork",
       "klucz hitWoodwork w /statistics (tylko część meczów - pokrycie do zmierzenia); brak metryki"),
    # --- player markets: lineups / incidents --------------------------------
    _n(r"zawodnik - strzeli gola z przewrotki", "fb.player_goal_detail_unknown",
       "brak źródła: bodyPart gola zna tylko right-foot/left-foot/head/other"),
    _c(r"zawodnik - strzeli (?:gola|#\+ gole|gola w [12]\. polowie|[1-9]\. gola|[1-9]\. gola dla " + S
       + r"|gola w obu polowach|gola z rzutu karnego|gola & zaliczy asyste|gola lub zaliczy asyste)"
       r"|zawodnik rezerwowy strzeli gola|ktorykolwiek z zawodnikow strzeli gola|obaj zawodnicy strzela gola"
       r"|" + P + r" strzeli (?:gola|[12]\. gola|#\+ gole)",
       "fb.player_goals", "gole zawodnika z incydentów (player, minuta, assist1) / " + SRC_LINEUPS),
    _c(r"(?:zawodnik -|" + P + r") strzeli gola (?:glowa|lewa noga|prawa noga|spoza pola karnego|bezposrednio z rzutu wolnego)",
       "fb.player_goal_detail", "bodyPart / situation / współrzędne gola (footballPassingNetworkAction) - " + SRC_INC),
    _c(r"zawodnik - otrzyma (?:[12]\. kartke|czerwona kartke|kartke)", "fb.player_cards",
       "kartki zawodnika z incydentów - " + SRC_INC),
    _c(r"ktorykolwiek z zawodnikow (?:odda powyzej x (?:celnych )?strzalow|strzeli powyzej x goli"
       r"|popelni powyzej x fauli|powyzej x odbiorow|powyzej x spalonych)",
       "fb.any_player", "maksimum po zawodnikach - " + SRC_LINEUPS),
    _c(r"zawodnik - liczba (?:celnych )?strzalow (?:glowa|lewa noga|prawa noga|spoza pola karnego)"
       r"|#\+ celnych strzalow spoza pola karnego",
       "fb.player_shot_detail", NEED_SHOT_DETAIL),
    _c(r"zawodnik - liczba fauli na zawodniku", "fb.player_fouled",
       "klucz wasFouled w /lineups (market_mapper 2026-09-29 uznał, że żaden klucz tego nie dowodzi - do weryfikacji na rozliczeniu) - "
       + SRC_LINEUPS),
    _n(r"zawodnik - liczba odbiorow na zawodniku", "fb.player_tackled",
       "brak klucza: /lineups ma totalTackle (wykonane), nie odbiory na zawodniku"),
    _n(P + r" & " + P + r" sfauluja sie nawzajem", "fb.player_pair_fouled_each_other",
       "brak źródła: /lineups nie mówi, kto kogo sfaulował"),
    _c(P + r" & " + P + r" (?:kazdy odda #\+ celnych strzalow i kazdy zostanie sfaulowany"
       r"|oddadza lacznie #\+ celnych strzalow|popelnia lacznie #\+ fauli)",
       "fb.player_pair", "suma/łączny rozkład dwóch zawodników - " + SRC_LINEUPS),
    _c(P + r" odda strzal w obramowanie bramki", "fb.player_woodwork", "klucz hitWoodwork w /lineups - " + SRC_LINEUPS),
    _c(P + r" & " + P + r" kazdy otrzyma kartke|" + P + r" otrzyma kartke", "fb.person_cards",
       "kartka zawodnika lub trenera (incydent card: player / manager) - " + SRC_INC),
    _c(r"kazdy bramkarz zostanie sfaulowany|ktorykolwiek bramkarz zaliczy asyste", "fb.goalkeeper_specials",
       "wasFouled / goalAssist bramkarza - " + SRC_LINEUPS),
    _c(r"kazdy bramkarz obroni strzal w kazdej polowie", "fb.saves_halves",
       "goalkeeperSaves w okresach 1ST/2ND /statistics (saves_2h nie jest metryką)"),
    # --- the order / minute of everything but goals and cards --------------
    _n(r"kto pierwszy wykona x rzutow roznych|kto wykona [12]\. rzut rozny|ostatni rzut rozny"
       r"|" + H + r" - (?:kto pierwszy wykona # rzuty rozne|wykona [12]\. rzut rozny)"
       r"|[12]\. (?:celny strzal|faul|odbior|spalony|strzal|wybicie od bramki)"
       r"|(?:faul|rzut rozny|rzuty rozne|spalony|wybicie od bramki|liczba celnych strzalow|liczba fauli"
       r"|liczba rzutow roznych|liczba rzutow z autu|liczba wybic od bramki"
       r"|najwiecej (?:celnych strzalow|fauli|rzutow z autu|wybic od bramki)) od #:# do #:# minuty",
       "fb.non_goal_event_timing", NC_EVENT_ORDER),
    # A side Superbet wrote differently inside a combination than on the
    # board ("Grand-Saconnex" for "CS Grand-Saconnex"): the subject is not
    # recognised, the quantity is the side's own.
    _c(P + r" (?:wygra lub zremisuje(?: [12]\.\s?polowe)?|wygra mecz|wygra jedna z polow|strzeli " + OU
       + r" # gol[ai]|strzeli w obu polowach|zdobedzie gola w obu polowach)",
       "fb.unresolved_side", "podmiot spoza nazw tablicy (inna pisownia strony) - " + NEED_RESULT),
    _n(r"sedzia podejdzie do monitora var.*", "fb.var_review", NC_VAR),
    _n(r"strzelec zdejmie koszulke podczas celebrowania gola|kazda druzyna wykona rzut rozny z kazdego naroznika boiska",
       "fb.specials", NC_SPECIAL),
]

TENNIS_RULES: list[Rule] = [
    # --- ladders we already price (combination parts) ---------------------
    _m(r"liczba gemow: " + OU + r" #", "tn.games_total", "games_total"),
    _m(r"[12]\.\s?set - " + OU + r" # gemow", "tn.games_set_total", "games_set1_total / games_set2_total"),
    _m(r"liczba setow: " + OU + r" #", "tn.sets_total", "sets_total"),
    _m(OU + r" # tiebreaks w meczu", "tn.tiebreaks_total", "tiebreaks_total"),
    _m(OU + r" # asow", "tn.aces_total", "aces_total"),
    _m(OU + r" # asow w [12]\.\s?secie", "tn.aces_set_total", "aces_set1_total / aces_set2_total"),
    _m(S + r" " + OU + r" # asow", "tn.aces_for", "aces_for"),
    _m(r"[12]\.\s?set - " + S + r" " + OU + r" # asow", "tn.aces_set_for", "aces_set1_for / aces_set2_for"),
    _m(r"[12]\.\s?set - (?:" + S + r" (?:zdobedzie )?najwiecej asow|obaj zawodnicy tyle samo asow)",
       "tn.most_aces_set", "most_aces_set1 / most_aces_set2"),
    _m(OU + r" # podwojnych bledow", "tn.double_faults_total", "double_faults_total"),
    _m(S + r" " + OU + r" # podwojnych bledow", "tn.double_faults_for", "double_faults_for"),
    _m(S + r" " + OU + r" # podwojnych bledow w [12]\.\s?secie", "tn.double_faults_set_for",
       "double_faults_set1_for / double_faults_set2_for"),
    _m(S + r" liczba gemow - " + OU + r" #", "tn.games_won_for", "games_won_for"),
    _m(r"[123]\.\s?set - " + S + r" liczba gemow - " + OU + r" #", "tn.games_won_set_for",
       "games_won_set1_for / _set2_ / _set3_"),
    _m(r"handicap gemy: " + S + r" \(-?#\)", "tn.handicap_games", "handicap_games"),
    _m(r"[12]\.\s?set - handicap gemy(?:: " + S + r" \(-?#\))?", "tn.handicap_games_set",
       "handicap_games_set1 / _set2 (games_won_set1_for; handicap z zakresem seta jak most_ w _MOST_SCOPED)"),
    _m(r"zostanie rozegrany [345]\. set", "tn.deciding_set_played",
       "sets_total OVER 2.5 (Bo3) / 4.5 (Bo5) - odpowiedź tak/nie na drabinie, którą już wyceniamy"),
    # --- set scores: everything a set-by-set score answers ------------------
    _c(r"3\.\s?set - " + OU + r" # gemow", "tn.games_set3_total",
       "games_set3_total - NIE jest metryką (tylko set 1 i 2); wynik 3. seta jest w listingu"),
    _c(r"zwyciezca(?: - " + S + r")?|zwyciezca & kazdy z graczy wygra seta|zwyciezcy setow", "tn.winner",
       "model zwycięzcy (tennis_rating - forecast bez kalibracji) / " + SRC_SETS),
    _c(r"x\.\s?set - zwyciezca|[123]\.\s?set - zwyciezca(?: - " + S + r"| & liczba gemow)?|[123]\.\s?set/mecz",
       "tn.set_winner", NEED_SET_MODEL),
    _c(r"[123]\.\s?set - (?:dokladny wynik(?: #:#)?|multiwynik|liczba gemow nieparzysta/parzysta)"
       r"|[123]\.\s?set - " + S + r" wygra #:#(?:, #:#)? lub #:#|(?:[123]|#)\. - dokladny wynik: #:#",
       "tn.set_score", "rozkład wyniku seta - " + SRC_SETS),
    _c(S + r" (?:wygra seta|wygra bez straty seta|wygra wczesniej przegrywajac w setach|liczba setow"
       r"|wygra dokladnie # sety?)"
       r"|kazdy z zawodnikow wygra przynajmniej jednego seta|dokladny wynik|mecz zakonczy sie wynikiem #:#"
       r"|handicap setowy(?:: " + S + r" \(-?#\))?|dokladna liczba setow|liczba wygranych setow do #",
       "tn.sets", NEED_SET_MODEL),
    _c(r"nieparzysta/parzysta liczba gemow|mecz & liczba gemow|roznica zwyciestwa \(gemy\)"
       r"|set z najwieksza liczba gemow \(# sety\)|ktorykolwiek set zakonczy sie do zera",
       "tn.games_distribution", "rozkład gemów z " + SRC_SETS),
    _c(r"tiebreak lub super tiebreak w decydujacym secie|tiebreak w x\.\s?secie", "tn.tiebreak_set",
       "tie-break w secie N z " + SRC_SETS),
    _c(r"podwojne bledy", "tn.double_faults_unknown_shape",
       "double_faults_* są metrykami, ale kształt wyborów tego rynku nie jest zapisany w 04_offer - "
       "sprawdzić payload przed mapowaniem"),
    _c(r"[123]\.\s?set - " + S + r" liczba punktow|" + S + r" liczba wygranych punktow", "tn.points",
       "pointsTotal w /statistics (ALL i okresy setów); brak metryki"),
    _c(r"(?:" + S + r" )?liczba serwisow", "tn.service_points",
       "punkty serwisowe zawodnika = mianownik firstServeAccuracy w /statistics (\"62/87\" -> 87); brak metryki"),
    _m(r"czy bedzie tiebreak", "tn.any_tiebreak",
       "tiebreaks_total OVER 0.5 (tak/nie; market_mapper celowo nie mapuje - brak linii)"),
    _m(r"3\.\s?set - handicap gemy(?:: " + S + r" \(-?#\))?", "tn.handicap_games_set3",
       "handicap_games_set3 (games_won_set3_for jest metryką)"),
    _c(r"3\.\s?set - liczba gemow", "tn.games_set3_total",
       "games_set3_total - NIE jest metryką; wynik 3. seta jest w listingu"),
    _c(r"3\.\s?set - (?:" + S + r" -? ?)?liczba (?:asow(?: \+ podwojnych bledow)?|podwojnych bledow)"
       r"|3\.\s?set - " + S + r" " + OU + r" # asow|" + S + r" " + OU + r" # podwojnych bledow w 3\.\s?secie"
       r"|" + OU + r" # asow w 3\.\s?secie",
       "tn.serve_set3", "asy / podwójne błędy w okresie 3RD /statistics; brak metryk *_set3"),
    _c(r"[123]\.\s?set tiebreak - (?:liczba punktow(?: - handicap)?|zwyciezca|dokladny wynik|nieparzysta/parzysta liczba)",
       "tn.tiebreak_points", "punkty tie-breaka seta (periodNTieBreak w listingu)"),
    _m(r"podwojne bledy - handicap", "tn.handicap_double_faults",
       "handicap_double_faults (double_faults_for; wzorzec 'liczba X - handicap' nie łapie tej nazwy)"),
    # --- inside a game: points and game order ------------------------------
    _c(r"pierwszy gem serwisowy " + S + r" - dokladny wynik #:# po # pierwszych punktach"
       r"|dokladny wynik - wynik po # punktach w [0-9]+\. gemie serwisowym " + S
       + r"|" + S + r" [0-9]+\. gem serwisowy - (?:dokladny wynik|wynik po # punktach)"
       r"|dokladny wynik - " + S + r" [0-9]+\. gem serwisowy - " + S + r" do #",
       "tn.points_in_game", NEED_POINTS),
    _c(r"[123]\.\s?set - (?:bedzie prowadzic po # gemach|dokladny wynik po # gemach(?:: #:#)?)"
       r"|remis po # gemach w [123]\.\s?secie"
       r"|" + S + r" [0-9]+\. gem serwisowy - (?:zwyciezca|" + S + r" wygra|" + S + r" przelamie)"
       r"|" + S + r" wygra swoj [0-9]+\. gem serwisowy"
       r"|" + S + r" przelamie [0-9]+\. gem serwisowy wykonywany przez " + S,
       "tn.game_order", NEED_GAME_ORDER),
    # Any other question about one numbered game ("1. set - 5. gem - ...",
    # "x set - x i y gem", "gem 5. i 6.", "x.gem - zwyciezca: {a}"): points
    # inside it, or who won it.
    _c(r".*(?:\b(?:\d+|x|y)\.?\s?gem(?:ie|ow)?\b|\bgem (?:\d+|x)\.).*(?:punkt|rownowag|przewag|przelaman|do #).*",
       "tn.points_in_game", NEED_POINTS),
    _c(r".*(?:\b(?:\d+|x|y)\.?\s?gem(?:ie|ow)?\b|\bgem (?:\d+|x)\.).*", "tn.game_order", NEED_GAME_ORDER),
    _c(r"[123x]\.?\s?set tiebreak (?:\d+|x)\. punkt - zwyciezca|[123x]\.?\s?set - (?:\d+|x)\. as serwisowy",
       "tn.points_in_game", NEED_POINTS),
    _c(r"[123x]\.?\s?set - kto pierwszy wygra x gemy", "tn.game_order", NEED_GAME_ORDER),
]

# ---------------------------------------------------------------------------
# Measured sports (night plan 2026-10-12 C5). SHADOW (hockey, basketball,
# volleyball) reads a market by its `marketId` (shadow.MARKETS /
# PLAYER_MARKETS) and CS2 by its name (cs2.parse_line); neither records what
# it skipped, so these rules label the names a probe of Superbet's offer
# finds unread (`sport_payload_names`). Written against the 10-13 offer
# (52 events fetched 2026-10-12) and shadow.py's own "Not read" list.
# ---------------------------------------------------------------------------

OT = r"(?: \(z dogrywka(?: i rzutami karnymi)?\))?"  # Superbet's overtime scope
SRC_BOX = "box score zawodników (/event/{id}/lineups, który SHADOW_SETTLE już czyta) albo /statistics drużyny"
NEED_SCORE_MODEL = "model wyniku (sport_confidence / score_model) - "
NC_SCORE_ORDER = (
    "kolejność zdobywania punktów/goli: SHADOW_SETTLE trzyma wynik per okres, "
    "incydenty / play-by-play Sofascore nie są pobierane do cache"
)

HOCKEY_RULES: list[Rule] = [
    _c(r"(?:[123]\. tercja - )?podwojna szansa" + OT, "hk.double_chance",
       NEED_SCORE_MODEL + "suma wyników 1X2, które czytamy (wyniki nakładające się, nie partycja - shadow.py: nie czytane)"),
    _n(r"(?:[123]\. tercja - )?1\. gol" + OT + r"|druzyna zdobedzie 1\.\s?gola w meczu" + OT
       + r"|wyscig do x goli" + OT, "hk.goal_order", NC_SCORE_ORDER),
    _c(r"(?:" + S + r" - )?liczba goli \(z dogrywka i rzutami karnymi\)"
       + r"|handicap \(z dogrywka i rzutami karnymi\)", "hk.ot_so_scope",
       "zakres z dogrywką i karnymi (NHL tylko tak): model wyniku liczy czas regulaminowy; "
       "potrzebny rozkład dogrywki/karnych z historii (current vs normaltime)"),
    _c(r"(?:[123]\. tercja - )?dokladny wynik" + OT + r"|(?:[123]\. tercja - )?nieparzysta/parzysta.*",
       "hk.score_distribution", NEED_SCORE_MODEL + "rozkład wyniku (dokładny wynik, parzystość)"),
]

BASKETBALL_RULES: list[Rule] = [
    _c(r"(?:[12]\. polowa - |[1-4]\. kwarta - )?podwojna szansa" + OT, "bb.double_chance",
       NEED_SCORE_MODEL + "suma wyników 1X2, które czytamy (wyniki nakładające się, nie partycja - shadow.py: nie czytane)"),
    _n(r"wyscig do x punktow" + OT + r"|(?:[1-4]\. kwarta - )?kto (?:pierwszy )?zdobedzie .*",
       "bb.score_order", NC_SCORE_ORDER),
    _m(r"(?:punkty|asysty|zbiorki|punkty \+ zbiorki \+ asysty|trafione rzuty za #pkt) zawodnika" + OT,
       "bb.player_milestone",
       "player_points / _assists / _rebounds / _pts_reb_ast / _threes OVER N-0,5 (próg 'N+'; "
       "jednostronny - brak devigu, p z player_model)"),
    _c(r"zawodnik - double double" + OT, "bb.double_double",
       "pięć kluczy box score zawodnika naraz (shadow.py: nie sprawdzone wobec sum drużyny) - " + SRC_BOX),
    _c(r"(?:" + S + r" - )?liczba (?:zbiorek|defensywnych zbiorek|ofensywnych zbiorek|asyst|trafionych rzutow za #pkt"
       r"|trafionych rzutow wolnych|strat|przechwytow|blokow|fauli)" + OT
       + r"|najwiecej (?:zbiorek|asyst|trafionych rzutow za #pkt|trafionych rzutow wolnych|strat|przechwytow|blokow)" + OT,
       "bb.team_box", "statystyka drużyny bez metryki i historii - " + SRC_BOX),
]

VOLLEYBALL_RULES: list[Rule] = [
    _m(r"dokladna liczba setow", "vb.sets_count",
       "suma dokładnych wyników w setach (exact_sets 785 jest czytany)"),
    _m(S + r" wygra seta|czy bedzie [45]\. set\?|" + S + r" wygra dokladnie # set[y]?",
       "vb.exact_sets_derived", "funkcja dokładnego wyniku w setach (exact_sets 785 jest czytany)"),
    _c(r"[1-5]\.\s?set/mecz", "vb.set_and_match",
       NEED_SCORE_MODEL + "łączny rozkład zwycięzcy seta i meczu"),
    _c(r"[1-5]\. set - handicap punkty", "vb.set_points_handicap",
       NEED_SCORE_MODEL + "różnica punktów w secie (czytamy sumę punktów seta 782 i handicap punktów meczu 1069)"),
]

_CS2_PLAYER_STAT = r"(?:zabojstw|smierci|asyst|headshotow)"
CS2_RULES: list[Rule] = [
    # Parts of Superbet's combinations, worded as statements; each one a
    # family CS2 already reads (cs2.parse_line).
    _m(S + r" wygra [123x]\. mape", "cs2.map_winner", "map_winner (czytany)"),
    _m(S + r" wygra mecz", "cs2.match_winner", "match_winner (czytany)"),
    _m(P + r" " + OU + r" # " + _CS2_PLAYER_STAT + r" na [123x]\. mapie", "cs2.player_map",
       "zabójstwa / śmierci / asysty / headshoty zawodnika na mapie (CS2_EXTENDED_FAMILIES, czytane)"),
    _c(r"druzyna - najwiecej wygranych rund w meczu" + OT + r"|liczba rund" + OT
       + r"|" + S + r" - liczba rund" + OT + r"|handicap rund" + OT, "cs2.series_rounds",
       "rundy serii (rounds_* / team_rounds; wycena od epochs.CS2_SERIES_ROUNDS_FROM_UTC, w kombinacjach nieczytane)"),
    _c(r"(?:[123x]\.\s?mapa - )?nieparzysta/parzysta liczba rund" + OT, "cs2.round_parity",
       "parzystość rund (bez wyceny; cs2_map trzyma wynik rund map)"),
    _c(r"liczba dogrywek", "cs2.overtimes",
       "dogrywka mapy = wynik rund mapy ponad regulamin (cs2_map); brak rodziny"),
    _c(r"[123x]\.\s?mapa - liczba zabojstw" + OT, "cs2.map_kills_total",
       "suma zabójstw obu drużyn na mapie (cs2_player_map); brak rodziny"),
    _c(r"[123x]\.\s?mapa - zwyciezca i liczba rund" + OT, "cs2.map_winner_rounds",
       "łączny rozkład zwycięzcy mapy i liczby rund (wyścig rund)"),
    _c(r"[123x]\.\s?mapa - dokladny wynik" + OT, "cs2.map_exact",
       "rozkład wyniku rund mapy (wyścig rund, cs2_map)"),
    _c(r"x\.\s?mapa - zwyciezca #-drogowo", "cs2.map_winner_3way",
       "zwycięzca mapy z remisem (format bez dogrywki) - rozkład wyniku mapy"),
]

_RULES_BY_SPORT: dict[str, list[Rule]] = {
    "football": COMMON_RULES + FOOTBALL_RULES,
    "tennis": COMMON_RULES + TENNIS_RULES,
    "hockey": COMMON_RULES + HOCKEY_RULES,
    "basketball": COMMON_RULES + BASKETBALL_RULES,
    "volleyball": COMMON_RULES + VOLLEYBALL_RULES,
    "cs2": COMMON_RULES + CS2_RULES,
}
MEASURED_SPORTS: tuple[str, ...] = ("hockey", "basketball", "volleyball", "cs2")


def classify_template(template: str, sport: str) -> Classification:
    """One template (no ';') -> its label; UNCLASSIFIED when no rule matches."""
    for rule in _RULES_BY_SPORT.get(sport, COMMON_RULES):
        if rule.pattern.match(template):
            return Classification(rule.label, rule.family, rule.note, template)
    return Classification("UNCLASSIFIED", UNCLASSIFIED_FAMILY, "", template)


# offer.classify_odd appends these to a name the mapper read but whose line it
# could not use: "<name> (no line)", "<name> (unparseable line: '...')".
_LINE_SUFFIX = re.compile(r"\s\((?:no line|unparseable line: .*)\)$")


def classify_market_name(name: str, sport: str, sides: Sequence[str]) -> Classification:
    """One unmapped Superbet market name of one fixture -> exactly one label."""
    suffix = _LINE_SUFFIX.search(name)
    base = name[: suffix.start()] if suffix else name
    mapped = classify_market(base)
    player = PLAYER_MARKET_NAMES.get(fold(base))
    if mapped is not None or player is not None:
        # Today's mapper reads the name: on an older day's file it was a
        # mapping gap since closed; with a suffix OFFER read the name and
        # refused the line (an odd/even or a yes/no, or a malformed line).
        metric = mapped[0] if mapped is not None else str(player)
        template = template_of(name, sides)
        if suffix:
            return Classification(
                "MAPPABLE", "mapper.line_refused",
                f"{metric}: nazwę czyta market_mapper, OFFER odrzucił linię ({suffix.group(0).strip()})",
                template,
            )
        return Classification(
            "MAPPABLE", "mapper.current", f"{metric}: mapowane przez obecny market_mapper", template
        )
    if suffix:
        name = base
    template = template_of(name, sides)
    side_refused = _side_name_refused(template)
    if side_refused is not None:
        return Classification(
            "MAPPABLE", "mapper.side_name_refused",
            f"{side_refused}: wzorzec pasuje, strażnik podmiotu odrzucił nazwę strony (np. '&' w nazwie drużyny)",
            template,
        )
    return _template_or_combination(template, sport)


def _template_or_combination(template: str, sport: str) -> Classification:
    """A template's label; a Superbet combination (';') by its parts."""
    if ";" not in template:
        return classify_template(template, sport)
    parts = tuple(classify_template(p.strip(), sport) for p in template.split(";") if p.strip())
    labels = {p.label for p in parts}
    if "NOT_COMPUTABLE" in labels:
        blocking = next(p for p in parts if p.label == "NOT_COMPUTABLE")
        return Classification(
            "NOT_COMPUTABLE", COMBO_FAMILY, f"część {blocking.family}: {blocking.note}", template, parts
        )
    if "UNCLASSIFIED" in labels:
        return Classification("UNCLASSIFIED", COMBO_FAMILY, "część bez reguły", template, parts)
    return Classification("COMPUTABLE", COMBO_FAMILY, NEED_JOINT, template, parts)


def _side_name_refused(template: str) -> str | None:
    """The metric the mapper reads once the side's own name is out of the way.

    "Dagenham & Redbridge - liczba goli" is goals_for, but the "&" in the club
    name trips `_SUBJECT_IS_COMBINATION`. With the side as a neutral word the
    same pattern maps - a mapping gap, not a combination.
    """
    if "{a}" not in template and "{b}" not in template:
        return None
    if ";" in template or "#" in template.replace("{a}", "").replace("{b}", ""):
        return None
    probe = classify_market(template.replace("{a}", "qqa").replace("{b}", "qqb"))
    return probe[0] if probe is not None else None


# ---------------------------------------------------------------------------
# The day
# ---------------------------------------------------------------------------

# A derived market whose subject is a selection (most_ / handicap_) is one
# Superbet market for all its selections; a ladder is one market per subject.
_SELECTION_SUBJECT_PREFIXES = ("most_", "handicap_")


def _mapped_instances(rungs: Iterable[Mapping[str, Any]]) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for r in rungs:
        market = str(r.get("market"))
        subject = "" if market.startswith(_SELECTION_SUBJECT_PREFIXES) else str(r.get("subject") or "")
        out.add((market, subject))
    return out


def fixture_sides(
    fixture: Mapping[str, Any], board_by_id: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    """[a, b, a', b', ...]: Superbet's names from every listing, then Sofascore's."""
    sides: list[str] = []
    for sid in fixture.get("superbet_event_ids") or []:
        b = board_by_id.get(str(sid))
        if b:
            sides += [str(b.get("side_a") or ""), str(b.get("side_b") or "")]
    sides += [str(fixture.get("home_name") or ""), str(fixture.get("away_name") or "")]
    return sides


def build_report(
    offers: Sequence[Mapping[str, Any]],
    fixtures: Sequence[Mapping[str, Any]],
    board: Sequence[Mapping[str, Any]],
    *,
    date: str,
    max_examples: int = 3,
) -> dict[str, Any]:
    fixtures_by_id = {int(f["sofascore_event_id"]): f for f in fixtures}
    board_by_id = {str(b["superbet_event_id"]): b for b in board}

    by_label: dict[str, Counter[str]] = {lab: Counter() for lab in LABELS}
    by_sport_label: dict[str, Counter[str]] = defaultdict(Counter)
    family_occ: Counter[tuple[str, str, str]] = Counter()
    family_names: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    family_note: dict[tuple[str, str, str], str] = {}
    family_examples: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    combo_parts: Counter[tuple[str, str, str]] = Counter()
    combo_part_note: dict[tuple[str, str, str], str] = {}
    unclassified: Counter[str] = Counter()
    name_label: dict[str, str] = {}
    mapped_by_market: Counter[str] = Counter()
    mapped_by_sport: Counter[str] = Counter()
    unmapped_by_sport: Counter[str] = Counter()
    missing_fixture = 0

    for offer in offers:
        fixture = fixtures_by_id.get(int(offer["sofascore_event_id"]))
        if fixture is None:
            missing_fixture += 1
            continue
        sport = str(fixture.get("sport"))
        sides = fixture_sides(fixture, board_by_id)
        for market, _subject in _mapped_instances(offer.get("rungs") or []):
            mapped_by_market[market] += 1
            mapped_by_sport[sport] += 1
        for name in offer.get("unmapped_markets") or []:
            c = classify_market_name(str(name), sport, sides)
            unmapped_by_sport[sport] += 1
            by_label[c.label][name] += 1
            by_sport_label[sport][c.label] += 1
            key = (sport, c.label, c.family)
            family_occ[key] += 1
            family_names[key].add(c.template)
            family_note.setdefault(
                key,
                c.note if c.family != COMBO_FAMILY
                else NEED_JOINT if c.label == "COMPUTABLE"
                else "co najmniej jedna część bez etykiety" if c.label == "UNCLASSIFIED"
                else "co najmniej jedna część NOT_COMPUTABLE (rozbicie na części niżej)",
            )
            if len(family_examples[key]) < max_examples and name not in family_examples[key]:
                family_examples[key].append(str(name))
            name_label[str(name)] = c.label
            for p in c.parts:
                pk = (sport, p.label, p.family)
                combo_parts[pk] += 1
                combo_part_note.setdefault(pk, p.note)
            if c.label == "UNCLASSIFIED":
                unclassified[c.template] += 1

    total_unmapped = sum(sum(c.values()) for c in by_label.values())
    total_mapped = sum(mapped_by_market.values())
    distinct_names = len({n for c in by_label.values() for n in c})
    return {
        "date": date,
        "stage": "MARKET_COVERAGE",
        "sources": ["01_board.json", "02_fixtures.json", "04_offer.json"],
        "fixtures": len(offers),
        "fixtures_missing_from_02": missing_fixture,
        "offered_market_instances": total_mapped + total_unmapped,
        "mapped": {
            "instances": total_mapped,
            "by_sport": dict(mapped_by_sport),
            "by_market": dict(mapped_by_market.most_common()),
            "counting": (
                "distinct (fixture, market, subject) over 04_offer rungs; most_/handicap_ "
                "counted once per (fixture, market) - one Superbet market for all selections"
            ),
        },
        "unmapped": {
            "occurrences": total_unmapped,
            "distinct_names": distinct_names,
            "by_sport": dict(unmapped_by_sport),
            "counting": "one occurrence = one (fixture, name) in 04_offer unmapped_markets",
        },
        "by_label": {
            lab: {"occurrences": sum(by_label[lab].values()), "distinct_names": len(by_label[lab])}
            for lab in LABELS
        },
        "by_sport_label": {s: dict(c) for s, c in by_sport_label.items()},
        "families": [
            {
                "sport": k[0],
                "label": k[1],
                "family": k[2],
                "note": family_note.get(k, ""),
                "occurrences": n,
                "distinct_templates": len(family_names[k]),
                "examples": family_examples[k],
            }
            for k, n in sorted(family_occ.items(), key=lambda kv: (LABELS.index(kv[0][1]), -kv[1]))
        ],
        "combo_parts": [
            {"sport": k[0], "label": k[1], "family": k[2], "note": combo_part_note.get(k, ""), "parts": n}
            for k, n in combo_parts.most_common()
        ],
        "unclassified": [{"template": t, "occurrences": n} for t, n in unclassified.most_common()],
    }


def render_markdown(report: Mapping[str, Any], *, top_families: int = 0) -> str:
    """The Polish daily report (operator-facing)."""
    lines: list[str] = []
    a = lines.append
    a(f"# Pokrycie rynków Superbetu - {report['date']}")
    a("")
    a("Raport (nie wejście potoku): każda nazwa rynku Superbetu, której OFFER nie odczytał "
      "(`04_offer.json` `unmapped_markets`), ma dokładnie jedną etykietę "
      "(`bet.sofa.market_coverage`). MAPPABLE = statystykę już liczymy, brakuje tylko mapowania nazwy "
      "(propozycja, nie zmiana); COMPUTABLE = da się policzyć z historii w cache, ale potrzeba nowej "
      "wielkości / wyceny; NOT_COMPUTABLE = brak źródła; UNCLASSIFIED = brak reguły.")
    a("")
    mapped = report["mapped"]
    un = report["unmapped"]
    a(f"- mecze w ofercie: {report['fixtures']} (bez wpisu w 02: {report['fixtures_missing_from_02']})")
    a(f"- rynki oferowane (zmapowane + niezmapowane wystąpienia): {report['offered_market_instances']}")
    a(f"- zmapowane: {mapped['instances']} ({mapped['counting']})")
    a(f"- niezmapowane: {un['occurrences']} wystąpień, {un['distinct_names']} różnych nazw ({un['counting']})")
    a("")
    a("| etykieta | wystąpienia | różne nazwy |")
    a("|---|---|---|")
    for lab in LABELS:
        b = report["by_label"][lab]
        a(f"| {lab} | {b['occurrences']} | {b['distinct_names']} |")
    a("")
    a("| sport | " + " | ".join(LABELS) + " |")
    a("|---|" + "---|" * len(LABELS))
    for sport, c in sorted(report["by_sport_label"].items()):
        a(f"| {sport} | " + " | ".join(str(c.get(lab, 0)) for lab in LABELS) + " |")
    a("")
    a("## Rodziny")
    a("")
    a("| sport | etykieta | rodzina | wystąpienia | szablony | propozycja / potrzeba / powód | przykład |")
    a("|---|---|---|---|---|---|---|")
    fams = report["families"]
    if top_families:
        fams = fams[:top_families]
    for f in fams:
        ex = (f["examples"] or [""])[0].replace("|", "/")
        a(f"| {f['sport']} | {f['label']} | `{f['family']}` | {f['occurrences']} | "
          f"{f['distinct_templates']} | {f['note']} | {ex[:90]} |")
    a("")
    a("## Kombinacje Superbetu (`;`) - części")
    a("")
    a("| sport | etykieta części | rodzina | części |")
    a("|---|---|---|---|")
    for p in report["combo_parts"]:
        a(f"| {p['sport']} | {p['label']} | `{p['family']}` | {p['parts']} |")
    a("")
    a("## UNCLASSIFIED")
    a("")
    if not report["unclassified"]:
        a("Brak - każda nazwa dnia ma etykietę.")
    else:
        for u in report["unclassified"]:
            a(f"- {u['occurrences']} x `{u['template']}`")
    a("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Measured sports (night plan 2026-10-12 C5)
# ---------------------------------------------------------------------------
#
# SHADOW and CS2 write only the lines they read into snapshots.jsonl - no
# record of a market they skipped, unlike OFFER's unmapped_markets. The
# inventory of the unread names therefore needs the raw Superbet payloads: a
# probe of the offer (scripts/sofa/report_market_coverage.py --sports), which
# sees a match only before it starts. What the snapshots do record - events
# and lines per family - is reported beside it (`snapshot_inventory`).


def classify_sport_market_name(name: str, sport: str, sides: Sequence[str]) -> Classification:
    """One unread market name of a measured sport's event -> exactly one label."""
    return _template_or_combination(template_of(name, sides), sport)


def _reader_reads(items: Sequence[Mapping[str, Any]], sport: str, team1: str, team2: str) -> bool:
    """Does SHADOW / CS2 read this market (any of its odds) at all?

    SHADOW identifies a market by `marketId` (shadow.MARKETS / PLAYER_MARKETS);
    CS2 by its name and selection (cs2.parse_line), asked here as if the odd
    were active and unboosted, so a suspended market still counts as read.
    """
    from bet.sofa import cs2, shadow

    if sport == "cs2":
        return any(
            cs2.parse_line(
                {**it, "status": "active", "tags": "", "price": 2.0}, "", team1, team2
            ) is not None
            for it in items
        )
    if sport not in shadow.MARKETS:
        return False
    key: shadow.SportKey = sport
    known = set(shadow.MARKETS[key]) | set(shadow.PLAYER_MARKETS[key])
    for it in items:
        try:
            if int(it.get("marketId") or 0) in known:
                return True
        except (TypeError, ValueError):
            continue
    return False


def sport_payload_names(
    payload: Mapping[str, Any], sport: str
) -> tuple[tuple[str, str], list[str], list[str]]:
    """((team1, team2), names read, names not read) of one raw event payload.

    Pre-match odds only (`superbet.odds_items`), so a live market never counts.
    """
    from bet.sofa.superbet import odds_items, split_match_name

    team1, team2 = split_match_name(str(payload.get("matchName") or ""))
    by_name: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in odds_items(dict(payload)):
        name = str(item.get("marketName") or "").strip()
        if name:
            by_name[name].append(item)
    read: list[str] = []
    unread: list[str] = []
    for name, items in sorted(by_name.items()):
        (read if _reader_reads(items, sport, team1, team2) else unread).append(name)
    return (team1, team2), read, unread


def snapshot_inventory(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """What one sport's snapshots.jsonl recorded: events, and the lines of each
    event's LAST snapshot per family (a snapshot is re-taken several times a
    day; the last one is what the day ended on)."""
    last: dict[str, Mapping[str, Any]] = {}
    for rec in records:
        eid = str(rec.get("superbet_event_id") or "")
        if not eid:
            continue
        prev = last.get(eid)
        if prev is None or str(rec.get("fetched_at_utc") or "") >= str(prev.get("fetched_at_utc") or ""):
            last[eid] = rec
    by_family: Counter[str] = Counter()
    for rec in last.values():
        for line in rec.get("lines") or []:
            by_family[str(line.get("family"))] += 1
    return {
        "events": len(last),
        "lines": sum(by_family.values()),
        "by_family": dict(by_family.most_common()),
    }


def build_sports_report(
    events: Sequence[Mapping[str, Any]],
    *,
    date: str,
    snapshots: Mapping[str, Mapping[str, Any]] | None = None,
    source: str = "",
    max_examples: int = 3,
) -> dict[str, Any]:
    """The measured sports' inventory. `events`: one entry per probed event,
    {sport, superbet_event_id, team1, team2, read: [names], unread: [names]}."""
    by_label: dict[str, Counter[str]] = {lab: Counter() for lab in LABELS}
    by_sport_label: dict[str, Counter[str]] = defaultdict(Counter)
    family_occ: Counter[tuple[str, str, str]] = Counter()
    family_names: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    family_note: dict[tuple[str, str, str], str] = {}
    family_examples: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    combo_parts: Counter[tuple[str, str, str]] = Counter()
    unclassified: Counter[tuple[str, str]] = Counter()
    probed: Counter[str] = Counter()
    read_occ: Counter[str] = Counter()
    unread_occ: Counter[str] = Counter()
    names: list[dict[str, Any]] = []
    seen_templates: set[tuple[str, str]] = set()

    for ev in events:
        sport = str(ev.get("sport"))
        sides = [str(ev.get("team1") or ""), str(ev.get("team2") or "")]
        probed[sport] += 1
        read_occ[sport] += len(ev.get("read") or [])
        for name in ev.get("unread") or []:
            c = classify_sport_market_name(str(name), sport, sides)
            unread_occ[sport] += 1
            by_label[c.label][f"{sport}|{name}"] += 1
            by_sport_label[sport][c.label] += 1
            key = (sport, c.label, c.family)
            family_occ[key] += 1
            family_names[key].add(c.template)
            family_note.setdefault(
                key,
                c.note if c.family != COMBO_FAMILY
                else NEED_JOINT if c.label == "COMPUTABLE"
                else "co najmniej jedna część bez etykiety" if c.label == "UNCLASSIFIED"
                else "co najmniej jedna część NOT_COMPUTABLE",
            )
            if len(family_examples[key]) < max_examples and name not in family_examples[key]:
                family_examples[key].append(str(name))
            for p in c.parts:
                combo_parts[(sport, p.label, p.family)] += 1
            if c.label == "UNCLASSIFIED":
                unclassified[(sport, c.template)] += 1
            if (sport, c.template) not in seen_templates:
                seen_templates.add((sport, c.template))
                names.append({"sport": sport, "template": c.template, "label": c.label,
                              "family": c.family, "example": str(name)})

    return {
        "date": date,
        "stage": "MARKET_COVERAGE_SPORTS",
        "source": source,
        "probed_events": dict(probed),
        "read_names": dict(read_occ),
        "unread_names": dict(unread_occ),
        "counting": "one occurrence = one (event, market name) the sport's reader does not read",
        "snapshots": dict(snapshots or {}),
        "by_label": {
            lab: {"occurrences": sum(by_label[lab].values()), "distinct_names": len(by_label[lab])}
            for lab in LABELS
        },
        "by_sport_label": {s: dict(c) for s, c in by_sport_label.items()},
        "families": [
            {
                "sport": k[0], "label": k[1], "family": k[2], "note": family_note.get(k, ""),
                "occurrences": n, "distinct_templates": len(family_names[k]),
                "examples": family_examples[k],
            }
            for k, n in sorted(family_occ.items(), key=lambda kv: (kv[0][0], LABELS.index(kv[0][1]), -kv[1]))
        ],
        "combo_parts": [
            {"sport": k[0], "label": k[1], "family": k[2], "parts": n}
            for k, n in combo_parts.most_common()
        ],
        "templates": sorted(names, key=lambda r: (r["sport"], r["label"], r["template"])),
        "unclassified": [
            {"sport": s, "template": t, "occurrences": n} for (s, t), n in unclassified.most_common()
        ],
    }


def render_sports_markdown(report: Mapping[str, Any]) -> str:
    """The Polish report of the measured sports' unread markets."""
    lines: list[str] = []
    a = lines.append
    a(f"# Pokrycie rynków Superbetu - sporty mierzone - {report['date']}")
    a("")
    a("Raport (nie wejście potoku). SHADOW (hokej, koszykówka, siatkówka) i CS2 zapisują w "
      "`snapshots.jsonl` tylko linie, które czytają - nazw pominiętych rynków nie zapisuje nic. "
      "Nazwy poniżej pochodzą z próby oferty Superbetu (surowe payloady meczów przed startem); "
      "każda nieczytana nazwa ma jedną etykietę (`bet.sofa.market_coverage`): MAPPABLE = wielkość "
      "już liczymy, brakuje odczytu; COMPUTABLE = da się policzyć, potrzeba nowej wielkości / "
      "wyceny; NOT_COMPUTABLE = brak źródła; UNCLASSIFIED = brak reguły.")
    a("")
    a(f"- źródło: {report.get('source') or '-'}")
    a(f"- liczenie: {report['counting']}")
    a("")
    a("| sport | mecze w próbie | nazwy czytane | nazwy nieczytane | " + " | ".join(LABELS) + " |")
    a("|---|---|---|---|" + "---|" * len(LABELS))
    for sport in MEASURED_SPORTS:
        c = report["by_sport_label"].get(sport, {})
        a(f"| {sport} | {report['probed_events'].get(sport, 0)} | {report['read_names'].get(sport, 0)} | "
          f"{report['unread_names'].get(sport, 0)} | " + " | ".join(str(c.get(lab, 0)) for lab in LABELS) + " |")
    a("")
    snaps = report.get("snapshots") or {}
    if snaps:
        a("## Co zapisały snapshoty dnia (ostatni snapshot meczu)")
        a("")
        a("| sport | mecze | linie | rodziny (linie) |")
        a("|---|---|---|---|")
        for sport in MEASURED_SPORTS:
            s = snaps.get(sport)
            if not s:
                a(f"| {sport} | brak pliku | - | - |")
                continue
            fams = ", ".join(f"{f} {n}" for f, n in list(s["by_family"].items())[:12])
            a(f"| {sport} | {s['events']} | {s['lines']} | {fams} |")
        a("")
    a("## Rodziny nieczytanych nazw")
    a("")
    a("| sport | etykieta | rodzina | wystąpienia | szablony | propozycja / potrzeba / powód | przykład |")
    a("|---|---|---|---|---|---|---|")
    for f in report["families"]:
        ex = (f["examples"] or [""])[0].replace("|", "/")
        a(f"| {f['sport']} | {f['label']} | `{f['family']}` | {f['occurrences']} | "
          f"{f['distinct_templates']} | {f['note']} | {ex[:90]} |")
    a("")
    a("## UNCLASSIFIED")
    a("")
    if not report["unclassified"]:
        a("Brak - każda nieczytana nazwa próby ma etykietę.")
    else:
        for u in report["unclassified"]:
            a(f"- {u['sport']}: {u['occurrences']} x `{u['template']}`")
    a("")
    return "\n".join(lines)
