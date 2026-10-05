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

NC_POINTS = (
    "brak historii punkt po punkcie (Sofascore /point-by-point nie jest pobierane do cache): "
    "wyniku nie widać ani w historii, ani w SETTLE - model punktu dałby liczbę, której nie da się "
    "skalibrować ani rozliczyć"
)
NC_GAME_ORDER = (
    "brak historii gem po gemie: wynik seta nie mówi, kto wygrał który gem ani jaki był stan po "
    "N gemach (/point-by-point nie w cache); model z częstości utrzymań serwisu (serviceGamesWon) "
    "dałby liczbę, której nie da się skalibrować ani rozliczyć"
)
NC_EVENT_ORDER = (
    "brak kolejności/minuty zdarzeń innych niż gole i kartki "
    "(incydenty Sofascore nie zawierają rożnych, fauli, strzałów, autów, wybić, spalonych)"
)
NC_SHOT_DETAIL = (
    "brak części ciała / miejsca strzałów niebędących golem (shotmap nie w cache; "
    "/lineups podaje tylko sumy)"
)
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
    _n(r"zawodnik - liczba (?:celnych )?strzalow (?:glowa|lewa noga|prawa noga|spoza pola karnego)"
       r"|#\+ celnych strzalow spoza pola karnego",
       "fb.player_shot_detail", NC_SHOT_DETAIL),
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
    _n(r"pierwszy gem serwisowy " + S + r" - dokladny wynik #:# po # pierwszych punktach"
       r"|dokladny wynik - wynik po # punktach w [0-9]+\. gemie serwisowym " + S
       + r"|" + S + r" [0-9]+\. gem serwisowy - (?:dokladny wynik|wynik po # punktach)"
       r"|dokladny wynik - " + S + r" [0-9]+\. gem serwisowy - " + S + r" do #",
       "tn.points_in_game", NC_POINTS),
    _n(r"[123]\.\s?set - (?:bedzie prowadzic po # gemach|dokladny wynik po # gemach(?:: #:#)?)"
       r"|remis po # gemach w [123]\.\s?secie"
       r"|" + S + r" [0-9]+\. gem serwisowy - (?:zwyciezca|" + S + r" wygra|" + S + r" przelamie)"
       r"|" + S + r" wygra swoj [0-9]+\. gem serwisowy"
       r"|" + S + r" przelamie [0-9]+\. gem serwisowy wykonywany przez " + S,
       "tn.game_order", NC_GAME_ORDER),
    # Any other question about one numbered game ("1. set - 5. gem - ...",
    # "x set - x i y gem", "gem 5. i 6.", "x.gem - zwyciezca: {a}"): points
    # inside it, or who won it.
    _n(r".*(?:\b(?:\d+|x|y)\.?\s?gem(?:ie|ow)?\b|\bgem (?:\d+|x)\.).*(?:punkt|rownowag|przewag|przelaman|do #).*",
       "tn.points_in_game", NC_POINTS),
    _n(r".*(?:\b(?:\d+|x|y)\.?\s?gem(?:ie|ow)?\b|\bgem (?:\d+|x)\.).*", "tn.game_order", NC_GAME_ORDER),
    _n(r"[123x]\.?\s?set tiebreak (?:\d+|x)\. punkt - zwyciezca|[123x]\.?\s?set - (?:\d+|x)\. as serwisowy",
       "tn.points_in_game", NC_POINTS),
    _n(r"[123x]\.?\s?set - kto pierwszy wygra x gemy", "tn.game_order", NC_GAME_ORDER),
]

_RULES_BY_SPORT: dict[str, list[Rule]] = {
    "football": COMMON_RULES + FOOTBALL_RULES,
    "tennis": COMMON_RULES + TENNIS_RULES,
}


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
