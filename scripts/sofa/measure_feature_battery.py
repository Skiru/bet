#!/usr/bin/env python3
"""One pre-registered battery of candidate statistics ("features") measured in
one pass against the operator's yardstick (2026-11-05): does adding a feature
to the CURRENT model's p bring it closer to Superbet's de-vigged price, out of
sample? Read-only evidence for docs/sofa/evidence/bateria_statystyk_2026-11-05.md.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_feature_battery.py list
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_feature_battery.py build \\
        [--sports football,hockey,...] [--db-path data/sofa.db] [--out <dir>]
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_feature_battery.py \\
        evaluate \\
        [--out <dir>]

`list` prints the frozen battery (FEATURES) as a Markdown table - written into
the report before any result. `build` assembles the dataset: settled Superbet
lines 2026-09-28..2026-11-04 with SETTLE's own grade (football / tennis-free
`sofa_settled_row` rows with a de-vigged `market_p`; the measured sports'
SHADOW_SETTLE / CS2_SETTLE `settled.json` lines with `fair_p`), the current
model's p as the 2026-11-05 yardstick read it (football `p_central`, SHEET's
p before the curve; sport team lines the score model's p of the line-evidence
rows `<sport>_superbet_settled.jsonl`; player and CS2 lines `model_p`), and
every feature computed AS OF the kickoff from the Sofascore cache only: a
past match counts only when it started strictly before the kickoff
(`as_of`), the league pool and the rebuilt table likewise. One canonical side
per line (OVER, T1, YES, ODD; a three-way market's two team sides) so a line
is never counted twice with mirrored features. `evaluate` splits by date
(development < HOLDOUT_FROM, the hold-out touched once), fits per (family,
feature) a logistic recalibration y ~ logit(p) + f (+ a missing indicator) on
development against y ~ logit(p), scores the hold-out (delta Brier and log
loss, match bootstrap, distance to the price), applies Benjamini-Hochberg at
q = 0.10 over every cell tested, and fits the "everything" model per family
(all non-price features, L2 chosen inside development).

The database is opened read-only (`mode=ro`) with keyed reads only (a `VACUUM
INTO` copy does not fit the disk, 56 GB on 2026-11-05). No network. Nothing
is written but the --out directory. The CONFIDENCE stage's refusal record is
not read (tests/sofa/test_priced_rows.py).
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sqlite3
import sys
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from bet.sofa import comparability
from bet.sofa.contracts import GapReason
from bet.sofa.metrics import (
    CARD_INCIDENT_SCOPES,
    FOOTBALL_METRICS,
    extract_flat_statistics,
    extract_metric,
)
from bet.sofa.shadow import PLAYER_MARKETS

FROM_DAY = "2026-09-28"
TO_DAY = "2026-11-04"
HOLDOUT_FROM = "2026-10-23"  # first 25 of 38 days = development
# L2 grid of the "everything" model; widened to 1e5 after the development-only
# dry run (`--dev-check`) picked the old maximum 1e3 in every family
LAMBDA_GRID = (1.0, 10.0, 100.0, 1e3, 1e4, 1e5)
DEV_CHECK_SPLIT = "2026-10-15"  # `evaluate --dev-check`: development split 17 / 8
HISTORY_DAYS = 400
LEAGUE_DAYS = 180
LEAGUE_FLOOR = int(datetime(2026, 9, 28, tzinfo=UTC).timestamp()) - LEAGUE_DAYS * 86400
MIN_HOLD_MATCHES = 100
MIN_DEV_MATCHES = 100
BH_Q = 0.10
BOOT = 1000
RUNS = Path("runs/sofa")
DEFAULT_ROWS_DIR = "data/line_evidence/rows_before_2026-11-05"
DEFAULT_OUT = "data/refit_2026-11-05_battery"
SPORTS = ("football", "hockey", "basketball", "volleyball", "cs2")
SPORT_SLUG = {
    "football": "football",
    "hockey": "ice-hockey",
    "basketball": "basketball",
    "volleyball": "volleyball",
    "cs2": "esports",
}
MAIN_STAT = {
    "football": "goals",
    "hockey": "goals",
    "basketball": "points",
    "volleyball": "sets",
    "cs2": "maps",
}
DAY_S = 86400
# pairs that are not (home, away): flags (x, 0) and (part, whole) ratios
SYMMETRIC = frozenset(
    {
        "p3_share",
        "q4_share",
        "ot",
        "blowout",
        "sets_played",
        "five_set",
        "pts_per_set",
        "extra_sets",
        "map_ot",
        "decider",
    }
)

F, H, B, V, C = "football", "hockey", "basketball", "volleyball", "cs2"
ALL5 = frozenset(SPORTS)
TEAM4 = frozenset({F, H, B, V})
STAT = frozenset({"total", "side", "margin"})
COUNT = frozenset({"total", "side"})
ANY = frozenset({"total", "side", "margin", "player", "other"})
PLAYER = frozenset({"player"})
NOPLAYER = frozenset({"total", "side", "margin", "other"})


@dataclass(frozen=True)
class Feature:
    fid: str
    sports: frozenset[str]
    kinds: frozenset[str]
    text: str
    note: str = ""
    price: bool = False  # derived from the price: a control, out of "everything"
    measured: bool = True


def _f(
    fid: str,
    sports: frozenset[str],
    kinds: frozenset[str],
    text: str,
    note: str = "",
    price: bool = False,
    measured: bool = True,
) -> Feature:
    return Feature(fid, sports, kinds, text, note, price, measured)


# THE FROZEN BATTERY (2026-11-05, before any result). X = the market's own
# statistic in the line's period (goals, corners, points, sets, rounds ...);
# S = the selection's side (a side / margin line), O = the other side, H / A =
# home / away; "l<w>" = the last w matches (maps for a map family) strictly
# before the kickoff; "- L" = minus the line (a margin line: + L, the
# selection clears when margin + L > 0). Oriented features point at S (a
# total line: at the home side).
FEATURES: tuple[Feature, ...] = (
    _f(
        "A01",
        ALL5,
        STAT,
        "szacunek X z l3: strona (S za + O przeciw)/2, suma (H suma + A suma)/2, "
        "margines (S margines - O margines)/2; minus linia",
    ),
    _f("A02", ALL5, STAT, "jak A01 z l5"),
    _f("A03", ALL5, STAT, "jak A01 z l10"),
    _f("A04", ALL5, STAT, "jak A01 z l20"),
    _f("A05", ALL5, STAT, "trend: szacunek l5 - szacunek l20"),
    _f("A06", ALL5, STAT, "odsetek meczów l10 (obie strony razem) z X ponad linią"),
    _f("A07", ALL5, STAT, "jak A06 z l20"),
    _f("A08", ALL5, STAT, "odchylenie standardowe X w l20 (obie strony razem)"),
    _f("A09", ALL5, COUNT, "rozproszenie: wariancja / średnia X w l20"),
    _f("A10", ALL5, STAT, "odległość linii w SD: (szacunek l20 - linia) / A08"),
    _f("A11", ALL5, STAT, "tylko własna produkcja: S za l10 (suma: mecze H) - linia"),
    _f("A12", ALL5, STAT, "tylko strona rywala: O przeciw l10 (suma: mecze A) - linia"),
    _f(
        "A13",
        ALL5,
        STAT,
        "podział dom / wyjazd: S w meczach w tej samej roli, O w przeciwnej, l10 - "
        "linia",
    ),
    _f("A14", ALL5, STAT, "mediana X w l20 (obie strony) - linia"),
    _f(
        "A15",
        ALL5,
        STAT,
        "średnia wykładnicza (półokres 5 meczów) - linia",
        note="ponowny test: pamięć wykładnicza odrzucona 10-08 (półokres 180 dni, "
        "historia); tu jako dodatek do p wobec ceny",
    ),
    _f(
        "A16",
        ALL5,
        STAT,
        "liczba dostępnych wartości X w l20 obu stron (cienka próba)",
    ),
    _f("A17", ALL5, STAT, "ostatni mecz: szacunek z l1 - linia"),
    _f(
        "A18",
        ALL5,
        COUNT,
        "korekta na rywala multiplikatywna: liga x (S za / liga) x (O przeciw / liga)"
        " - linia, l10",
    ),
    _f(
        "A19",
        ALL5,
        frozenset({"side"}),
        "profil rywala: odsetek l10 O, w których rywal O przekroczył linię",
        note="ponowny test podejrzenia 10-29 (nieodporne), teraz poza próbą",
    ),
    _f(
        "L01",
        ALL5,
        STAT,
        "stawka ligi X (rozgrywki, 180 dni przed meczem) - linia; margines: przewaga "
        "gospodarza x orientacja + linia",
    ),
    _f("L02", ALL5, COUNT, "odchylenie strony od ligi: szacunek l20 - stawka ligi"),
    _f("L03", ALL5, STAT, "log(1 + liczba meczów ligi w puli 180 dni)"),
    _f("L04", ALL5, STAT, "średnia przewaga gospodarza w X w lidze (orientowana)"),
    _f("C01", ALL5, ANY, "dni odpoczynku gospodarza (max 21)"),
    _f("C02", ALL5, ANY, "dni odpoczynku gościa (max 21)"),
    _f("C03", ALL5, ANY, "różnica odpoczynku (orientowana)"),
    _f("C04", ALL5, ANY, "mecz dzień po dniu: min odpoczynek <= 1,5 dnia"),
    _f("C05", ALL5, ANY, "zagęszczenie: mecze obu stron w 7 dniach przed"),
    _f("C06", ALL5, ANY, "różnica meczów w 14 dniach (orientowana)"),
    _f(
        "C07",
        TEAM4,
        ANY,
        "podróż gościa: poprzedni mecz gościa w innym mieście niż ten",
    ),
    _f(
        "C08",
        TEAM4,
        ANY,
        "podróż gospodarza: poprzedni mecz gospodarza w innym mieście",
    ),
    _f(
        "C09",
        ALL5,
        ANY,
        "etap sezonu: min liczba meczów stron w tych rozgrywkach i sezonie",
    ),
    _f("C10", ALL5, ANY, "dni od pierwszego meczu sezonu rozgrywek w puli"),
    _f("C11", TEAM4, ANY, "mecz pucharowy / play-off (comparability.is_knockout)"),
    _f(
        "C12",
        ALL5,
        STAT,
        "h2h: średnia X w poprzednich spotkaniach (do 5, 400 dni) - linia",
    ),
    _f("C13", ALL5, ANY, "h2h: liczba spotkań (400 dni)"),
    _f("C14", ALL5, ANY, "h2h: średni margines wyniku (orientowany)"),
    _f(
        "S01",
        ALL5,
        ANY,
        "forma: punkty na mecz l5, różnica (orientowana; poza piłką odsetek zwycięstw)",
    ),
    _f("S02", ALL5, ANY, "jak S01 z l10"),
    _f("S03", ALL5, ANY, "margines wyniku na mecz l10, różnica (orientowana)"),
    _f("S04", ALL5, ANY, "jak S03 z l20"),
    _f(
        "S05",
        ALL5,
        ANY,
        "margines H u siebie l10 - margines A na wyjeździe l10 (orientowany)",
    ),
    _f(
        "S06",
        ALL5,
        ANY,
        "punkty na mecz w tym sezonie rozgrywek, różnica (orientowana)",
    ),
    _f("S07", ALL5, ANY, "punkty na mecz w sezonie, suma (poziom obu stron)"),
    _f(
        "S08",
        ALL5,
        ANY,
        "luka miejsc w tabeli odbudowanej z puli (sezon, przed meczem) / liczba drużyn",
    ),
    _f(
        "S09",
        ALL5,
        ANY,
        "siła z ceny: logit p(wygrana gospodarza) bez marży (orientowany)",
        price=True,
    ),
    _f(
        "S10",
        ALL5,
        ANY,
        "niezgoda ratingu z ceną: reszta logit ceny gospodarza ~ S04 (dopasowana na "
        "rozwoju)",
        note="ponowny test: niezgoda z ceną jako antysygnał (10-08), adnotacja 11-04",
        price=True,
    ),
    _f("S11", ALL5, ANY, "wyrównanie z ceny: |logit p(gospodarz)|", price=True),
    _f(
        "P01",
        ALL5,
        ANY,
        "sama cena: logit ceny bez marży tej strony (KONTROLA)",
        price=True,
    ),
    _f("P02", ALL5, ANY, "marża linii (overround)", price=True),
    _f(
        "P03",
        frozenset({H, B, V, C}),
        ANY,
        "ruch linii: logit p teraz - logit p w pierwszym snapshocie",
        price=True,
    ),
    _f(
        "P04",
        frozenset({H, B, V, C}),
        ANY,
        "minuty przed startem w chwili ceny",
        price=True,
    ),
    _f("P05", ALL5, ANY, "wartość linii"),
    _f(
        "P06",
        frozenset({F}),
        COUNT,
        "z próbki SAMPLES: (średnia - linia) / SD próbki wiersza",
    ),
    _f("P07", frozenset({F}), ANY, "log(1 + liczebność próbki SAMPLES wiersza)"),
    _f(
        "T01",
        frozenset({F}),
        STAT,
        "posiadanie l10: strona S - 50, suma |H - A|, margines S - O",
    ),
    _f("T02", frozenset({F}), STAT, "xG atak l10: S za / H+A za / S - O"),
    _f(
        "T03",
        frozenset({F}),
        STAT,
        "xG obrona l10: O przeciw / H+A przeciw / O przeciw - S przeciw",
    ),
    _f(
        "T04",
        frozenset({F}),
        STAT,
        "wielkie szanse l10 (reguła jednolita: strona (S za + O przeciw)/2, suma - "
        "mecz, margines S - O)",
    ),
    _f("T05", frozenset({F}), STAT, "strzały ogółem l10 (reguła jednolita) - tempo"),
    _f(
        "T06",
        frozenset({F}),
        STAT,
        "rożne na strzał l10 (reguła jednolita, iloraz sum)",
    ),
    _f(
        "T07",
        frozenset({F}),
        STAT,
        "dotknięcia w polu karnym rywala l10 (reguła jednolita)",
    ),
    _f("T08", frozenset({F}), STAT, "wejścia w tercję ataku l10 (reguła jednolita)"),
    _f("T09", frozenset({F}), STAT, "celne dośrodkowania l10 (reguła jednolita)"),
    _f("T10", frozenset({F}), STAT, "celne długie podania l10 (reguła jednolita)"),
    _f("T11", frozenset({F}), STAT, "faule l10 (reguła jednolita)"),
    _f("T12", frozenset({F}), STAT, "żółte kartki l10 (reguła jednolita)"),
    _f(
        "T13",
        frozenset({F}),
        ANY,
        "sędzia: żółte kartki na mecz (jego 30 ostatnich meczów przed)",
    ),
    _f("T14", frozenset({F}), ANY, "sędzia: faule na mecz (jw.)"),
    _f("T15", frozenset({F}), ANY, "sędzia: log(1 + liczba jego meczów w cache)"),
    _f(
        "T16",
        frozenset({H}),
        STAT,
        "hokej strzały atak l10: S za / H+A za / S - O",
        note="B8 (strzały x skuteczność bramkarza w centrum) odrzucone 10-13; tu jako"
        " cecha",
    ),
    _f(
        "T17",
        frozenset({H}),
        STAT,
        "hokej strzały obrona l10: O przeciw / H+A przeciw / O - S przeciw",
    ),
    _f(
        "T18",
        frozenset({H}),
        STAT,
        "hokej skuteczność obrony drużyny l10 (1 - gole / strzały przeciw): O / "
        "średnia / S - O",
    ),
    _f("T19", frozenset({H}), STAT, "hokej minuty kar l10 (reguła jednolita)"),
    _f("T20", frozenset({H}), ANY, "hokej odsetek dogrywek l20 obu stron"),
    _f("T21", frozenset({H}), ANY, "hokej udział goli 3. tercji l20 obu stron"),
    _f("T22", frozenset({H}), STAT, "hokej Corsi% l10: S - 50 / |H - A| / S - O"),
    _f("T23", frozenset({B}), STAT, "kosz straty l10 (reguła jednolita)"),
    _f(
        "T24",
        frozenset({B}),
        STAT,
        "kosz udział punktów z trójek l10 (reguła jednolita, iloraz)",
    ),
    _f("T25", frozenset({B}), STAT, "kosz trafione wolne l10 (reguła jednolita)"),
    _f("T26", frozenset({B}), ANY, "kosz odsetek dogrywek l20 obu stron"),
    _f(
        "T27",
        frozenset({B}),
        ANY,
        "kosz odsetek meczów rozstrzygniętych > 15 pkt l20 (garbage time)",
    ),
    _f("T28", frozenset({B}), ANY, "kosz udział punktów 4. kwarty l20"),
    _f(
        "T29",
        frozenset({B}),
        STAT,
        "kosz zbiórki ofensywne l10 (reguła jednolita)",
        note="B7 tempo x efektywność zmierzone 10-13 (wymaga refitu); tu jako cecha",
    ),
    _f(
        "T30",
        frozenset({V}),
        ANY,
        "siatkówka sety na mecz l10 obu stron",
        note="B9 / C10 długość seta odrzucone 10-13; tu jako cecha",
    ),
    _f("T31", frozenset({V}), ANY, "siatkówka odsetek meczów 5-setowych l20"),
    _f("T32", frozenset({V}), ANY, "siatkówka punkty na set l10"),
    _f(
        "T33",
        frozenset({V}),
        ANY,
        "siatkówka odsetek wygranych setów, różnica (orientowana; suma |H - A|)",
    ),
    _f("T34", frozenset({V}), ANY, "siatkówka odsetek setów na przewagi l20"),
    _f(
        "T35",
        frozenset({V}),
        ANY,
        "siatkówka margines punktów na set, różnica (orientowana; suma |H - A|)",
    ),
    _f("T36", frozenset({C}), ANY, "CS2 rundy na mapę l20 map obu stron"),
    _f(
        "T37",
        frozenset({C}),
        ANY,
        "CS2 odsetek wygranych map l20, różnica (orientowana; suma |H - A|)",
    ),
    _f("T38", frozenset({C}), ANY, "CS2 odsetek map z dogrywką l20"),
    _f(
        "T39",
        frozenset({C}),
        ANY,
        "CS2 wspólna pula map: mapy grane >= 2 razy w 60 dniach przez obie strony",
    ),
    _f("T40", frozenset({C}), ANY, "CS2 odsetek serii Bo3 do trzeciej mapy l20"),
    _f(
        "T41",
        frozenset({C}),
        ANY,
        "CS2 zmiana składu: odsetek graczy l5 map spoza map 6-10 (średnia stron)",
    ),
    _f(
        "T42",
        frozenset({C}),
        ANY,
        "CS2 różnica rund na mapę l20, różnica (orientowana; suma |H - A|)",
    ),
    _f(
        "T43",
        frozenset({C}),
        ANY,
        "CS2 zabójstwa drużyny na rundę l20: S / średnia / S - O",
    ),
    _f("T44", frozenset({C}), ANY, "CS2 dni od ostatniej serii (min stron)"),
    _f(
        "T45",
        frozenset({F}),
        ANY,
        "składy: regularni zawodnicy spoza przewidywanej XI",
        measured=False,
    ),
    _f("Q01", frozenset({H, B, C}), PLAYER, "zawodnik: średnia statystyki l5 - linia"),
    _f("Q02", frozenset({H, B, C}), PLAYER, "zawodnik: l10 - linia"),
    _f("Q03", frozenset({H, B, C}), PLAYER, "zawodnik: l20 - linia"),
    _f(
        "Q04",
        frozenset({H, B, C}),
        PLAYER,
        "zawodnik: trend l5 - l20",
        note="ponowny test: człon formy NBA odrzucony 10-26",
    ),
    _f("Q05", frozenset({H, B, C}), PLAYER, "zawodnik: SD statystyki l10"),
    _f("Q06", frozenset({H, B, C}), PLAYER, "zawodnik: odsetek l10 ponad linią"),
    _f("Q07", frozenset({H, B, C}), PLAYER, "zawodnik: odsetek l20 ponad linią"),
    _f("Q08", frozenset({H, B}), PLAYER, "zawodnik: trend minut l3 - l10"),
    _f("Q09", frozenset({H, B}), PLAYER, "zawodnik: minuty l10"),
    _f("Q10", frozenset({H, B, C}), PLAYER, "zawodnik: udział w wolumenie drużyny l10"),
    _f("Q11", frozenset({H, B, C}), PLAYER, "zawodnik: trend udziału l5 - l20"),
    _f("Q12", frozenset({H, B, C}), PLAYER, "zawodnik: mecze (mapy CS2) w 30 dniach"),
    _f(
        "Q13",
        frozenset({H, B, C}),
        PLAYER,
        "rywal: suma tej statystyki oddana przez O na mecz l10",
    ),
    _f(
        "Q14", frozenset({H, B}), PLAYER, "zawodnik: odsetek meczów drużyny l10 bez gry"
    ),
    _f(
        "Q15",
        frozenset({H, B}),
        PLAYER,
        "średnia modelu zawodnika (player_model.jsonl) - linia",
    ),
    _f("Q16", frozenset({H, B, C}), PLAYER, "zawodnik: ostatni mecz - linia"),
    _f(
        "Q17",
        frozenset({H, B, C}),
        PLAYER,
        "zawodnik: średnia wykładnicza (półokres 5) - linia",
    ),
)
FID = {f.fid: i for i, f in enumerate(FEATURES)}
NF = len(FEATURES)


def fold(text: object) -> str:
    out = comparability.fold(text)
    for a, b in (("ł", "l"), ("ø", "o"), ("đ", "d"), ("ß", "ss"), ("æ", "ae")):
        out = out.replace(a, b)
    return " ".join(out.split())


def ts_of(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def days(a: str, b: str) -> list[str]:
    d0, d1 = date.fromisoformat(a), date.fromisoformat(b)
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def nanmean(a: Sequence[float]) -> float:
    vals = [x for x in a if x == x]
    return sum(vals) / len(vals) if vals else math.nan


# --- history units and the as-of rule ---------------------------------------


@dataclass(frozen=True)
class Unit:
    """One past match (a map for CS2 map units) seen from one team."""

    ts: int
    key: int  # the store's key of the match / map
    home: bool
    opp: int
    comp: int | None
    season: int | None
    city: str | None


def as_of(units: Sequence[Unit], ko: int) -> list[Unit]:
    """Units that started strictly before the kickoff, newest first. The one
    door every history feature goes through (no look-ahead)."""
    return sorted((u for u in units if u.ts < ko), key=lambda u: (-u.ts, -u.key))


class Store:
    """Values of past matches: pair(key, stat) -> (home, away) or None."""

    def __init__(self) -> None:
        self.team_units: dict[int, list[Unit]] = {}
        self.events: dict[int, tuple[int, int, int, int | None, int | None]] = {}
        self.vals: dict[int, dict[str, tuple[float, float] | None]] = {}

    def units(self, team: int) -> list[Unit]:
        return self.team_units.get(team, [])

    def pair(self, key: int, stat: str) -> tuple[float, float] | None:
        return self.vals.get(key, {}).get(stat)

    def comp_keys(self, comp: int | None) -> list[int]:
        idx: dict[int | None, list[int]] = getattr(self, "comp_index", {})
        return idx.get(comp, []) if comp is not None else []

    def league_pool(
        self,
        comp: int | None,
        stat: str,
    ) -> tuple[list[int], np.ndarray, np.ndarray]:
        """The competition's pooled matches carrying the stat, by start time."""
        cache: dict[tuple[int | None, str], tuple[list[int], np.ndarray, np.ndarray]]
        cache = self.__dict__.setdefault("_lg", {})
        k = (comp, stat)
        if k not in cache:
            rows = []
            for key in self.comp_keys(comp):
                ts = self.events[key][0]
                if ts < LEAGUE_FLOOR:
                    continue
                p = self.pair(key, stat)
                if p is not None:
                    rows.append((ts, p[0], p[1]))
            rows.sort()
            cache[k] = (
                [r[0] for r in rows],
                np.array([r[1] for r in rows]),
                np.array([r[2] for r in rows]),
            )
        return cache[k]

    def box(self, key: int) -> dict[int, tuple[bool, dict[str, float]]]:
        return {}


@dataclass
class Ctx:
    sport: str
    ko: int
    home: int
    away: int
    comp: int | None
    season: int | None
    city: str | None
    knockout: float
    price_home: float  # de-vigged two-way home win probability or nan
    referee: int | None = None
    aux: Any = None  # CS2: (map view, map-level Ctx)
    cache: dict[Any, Any] = field(default_factory=dict)


def hist(store: Store, ctx: Ctx, team: int, n: int = 60) -> list[Unit]:
    k = ("hist", team, n)
    if k not in ctx.cache:
        lo = ctx.ko - HISTORY_DAYS * DAY_S
        ctx.cache[k] = [u for u in as_of(store.units(team), ctx.ko) if u.ts >= lo][:n]
    out: list[Unit] = ctx.cache[k]
    return out


def series(
    store: Store,
    ctx: Ctx,
    team: int,
    stat: str,
    n: int = 20,
) -> tuple[np.ndarray, np.ndarray]:
    """(for, against) of the team's newest n units carrying the stat, and
    whether each was a home match."""
    k = ("ser", team, stat, n)
    if k not in ctx.cache:
        fa: list[tuple[float, float]] = []
        hm: list[bool] = []
        for u in hist(store, ctx, team):
            p = store.pair(u.key, stat)
            if p is None:
                continue
            fa.append((p[0], p[1]) if (u.home or stat in SYMMETRIC) else (p[1], p[0]))
            hm.append(u.home)
            if len(fa) == n:
                break
        ctx.cache[k] = (
            np.array(fa, dtype=float).reshape(-1, 2),
            np.array(hm, dtype=bool),
        )
    out: tuple[np.ndarray, np.ndarray] = ctx.cache[k]
    return out


def league(store: Store, ctx: Ctx, stat: str) -> tuple[np.ndarray, np.ndarray]:
    """(home, away) values of the competition's pooled matches of the last
    LEAGUE_DAYS strictly before the kickoff."""
    k = ("lg", stat)
    if k not in ctx.cache:
        ts, hv, av = store.league_pool(ctx.comp, stat)
        i0 = bisect_left(ts, ctx.ko - LEAGUE_DAYS * DAY_S)
        i1 = bisect_left(ts, ctx.ko)  # strictly before the kickoff
        ctx.cache[k] = (hv[i0:i1], av[i0:i1])
    out: tuple[np.ndarray, np.ndarray] = ctx.cache[k]
    return out


# --- feature computation -----------------------------------------------------


def _m(a: np.ndarray, w: int | None = None) -> float:
    a = a[:w] if w else a
    return float(a.mean()) if len(a) else math.nan


def _ew(a: np.ndarray, hl: float = 5.0) -> float:
    if not len(a):
        return math.nan
    w = 0.5 ** (np.arange(len(a)) / hl)
    return float((a * w).sum() / w.sum())


def _avg(*xs: float) -> float:
    vals = [x for x in xs if x == x]
    return sum(vals) / len(vals) if len(vals) == len(xs) else math.nan


def stat_base(store: Store, ctx: Ctx, kind: str, stat: str, o: int) -> dict[str, Any]:
    """Line-free summaries of the line's own statistic: per (kind, stat,
    orientation) once per event."""
    k = ("base", kind, stat, o)
    if k in ctx.cache:
        out: dict[str, Any] = ctx.cache[k]
        return out
    s_team, o_team = (ctx.home, ctx.away) if o >= 0 else (ctx.away, ctx.home)
    hs, hh = series(store, ctx, ctx.home, stat)
    as_, ah = series(store, ctx, ctx.away, stat)
    ss, sh = series(store, ctx, s_team, stat)
    os_, oh = series(store, ctx, o_team, stat)
    s_home = o >= 0
    if kind == "total":
        a1, a2 = hs.sum(axis=1), as_.sum(axis=1)
        own, opp = a1, a2
        v1 = a1[hh] if len(a1) else a1
        v2 = a2[~ah] if len(a2) else a2
    elif kind == "side":
        a1, a2 = ss[:, 0], os_[:, 1]
        own, opp = a1, a2
        v1 = a1[sh == s_home] if len(a1) else a1
        v2 = a2[oh == (not s_home)] if len(a2) else a2
    else:  # margin
        a1, a2 = ss[:, 0] - ss[:, 1], -(os_[:, 0] - os_[:, 1])
        own, opp = a1, a2
        v1 = a1[sh == s_home] if len(a1) else a1
        v2 = a2[oh == (not s_home)] if len(a2) else a2
    est = {w: _avg(_m(a1, w), _m(a2, w)) for w in (1, 3, 5, 10, 20)}
    pooled10 = np.concatenate([a1[:10], a2[:10]])
    pooled20 = np.concatenate([a1[:20], a2[:20]])
    lh, la = league(store, ctx, stat)
    lg_tot = float((lh + la).mean()) if len(lh) else math.nan
    lg_side = float(np.concatenate([lh, la]).mean()) if len(lh) else math.nan
    lg_home_adv = float((lh - la).mean()) if len(lh) else math.nan
    if kind == "total":
        lg = lg_tot
    elif kind == "side":
        lg = lg_side
    else:
        lg = lg_home_adv * (1 if s_home else -1)
    if kind == "total" and lg == lg and lg > 0:
        opp_adj = lg * (_m(own, 10) / lg) * (_m(opp, 10) / lg)
    elif kind == "side" and lg == lg and lg > 0:
        opp_adj = lg * (_m(own, 10) / lg) * (_m(opp, 10) / lg)
    else:
        opp_adj = math.nan
    # h2h: S's past units against O
    h2h: list[float] = []
    for u in hist(store, ctx, s_team):
        if u.opp != o_team:
            continue
        p = store.pair(u.key, stat)
        if p is None:
            continue
        f_, a_ = (p[0], p[1]) if u.home else (p[1], p[0])
        h2h.append(f_ + a_ if kind == "total" else f_ if kind == "side" else f_ - a_)
        if len(h2h) == 5:
            break
    sd20 = float(pooled20.std(ddof=1)) if len(pooled20) > 2 else math.nan
    mu20 = float(pooled20.mean()) if len(pooled20) else math.nan
    out = {
        "est": est,
        "p10": pooled10,
        "p20": pooled20,
        "sd20": sd20,
        "disp": (sd20**2 / mu20) if mu20 == mu20 and mu20 > 0 else math.nan,
        "own10": _m(own, 10),
        "opp10": _m(opp, 10),
        "venue": _avg(_m(v1, 10), _m(v2, 10)),
        "med20": float(np.median(pooled20)) if len(pooled20) else math.nan,
        "ew": _avg(_ew(a1[:20]), _ew(a2[:20])),
        "n": float(len(pooled20)),
        "oppx": os_[:10, 1] if kind == "side" else np.zeros(0),
        "lg": lg,
        "lg_n": math.log1p(len(lh)),
        "lg_ha": lg_home_adv * (1 if s_home else -1),
        "opp_adj": opp_adj,
        "h2h": nanmean(h2h) if h2h else math.nan,
    }
    ctx.cache[k] = out
    return out


def stat_features(base: dict[str, Any], kind: str, line: float) -> dict[str, float]:
    sign = 1.0 if kind == "margin" else -1.0

    def r(x: float) -> float:
        return x + sign * line

    est = base["est"]
    out = {
        "A01": r(est[3]),
        "A02": r(est[5]),
        "A03": r(est[10]),
        "A04": r(est[20]),
        "A05": est[5] - est[20],
        "A06": float((base["p10"] + sign * line > 0).mean())
        if len(base["p10"])
        else math.nan,
        "A07": float((base["p20"] + sign * line > 0).mean())
        if len(base["p20"])
        else math.nan,
        "A08": base["sd20"],
        "A10": (r(est[20]) / base["sd20"])
        if base["sd20"] == base["sd20"] and base["sd20"] > 0
        else math.nan,
        "A11": r(base["own10"]),
        "A12": r(base["opp10"]),
        "A13": r(base["venue"]),
        "A14": r(base["med20"]),
        "A15": r(base["ew"]),
        "A16": base["n"],
        "A17": r(est[1]),
        "L01": r(base["lg"]),
        "L03": base["lg_n"],
        "L04": base["lg_ha"],
        "C12": r(base["h2h"]),
    }
    if kind in COUNT:
        out["A09"] = base["disp"]
        out["A18"] = r(base["opp_adj"])
        out["L02"] = est[20] - base["lg"]
    if kind == "side":
        ox = base["oppx"]
        out["A19"] = float((ox - line > 0).mean()) if len(ox) else math.nan
    return out


def _ppg(sport: str, fa: np.ndarray) -> np.ndarray:
    if not len(fa):
        return np.zeros(0)
    d = fa[:, 0] - fa[:, 1]
    if sport == "football":
        return np.asarray(np.where(d > 0, 3.0, np.where(d == 0, 1.0, 0.0)))
    return np.asarray((d > 0).astype(float))


def event_features(store: Store, ctx: Ctx) -> dict[str, float]:
    """Context / strength features, home-referenced (diffs = home - away)."""
    if "ev" in ctx.cache:
        out: dict[str, float] = ctx.cache["ev"]
        return out
    sp = ctx.sport
    hu, au = hist(store, ctx, ctx.home), hist(store, ctx, ctx.away)
    out = {}
    rest = []
    for tag, us in (("C01", hu), ("C02", au)):
        r_ = min((ctx.ko - us[0].ts) / DAY_S, 21.0) if us else math.nan
        out[tag] = r_
        rest.append(r_)
    out["C03"] = rest[0] - rest[1]
    out["C04"] = (
        float(min(rest) <= 1.5)
        if rest[0] == rest[0] and rest[1] == rest[1]
        else math.nan
    )
    out["C05"] = float(sum(1 for u in hu + au if u.ts >= ctx.ko - 7 * DAY_S))
    out["C06"] = float(
        sum(1 for u in hu if u.ts >= ctx.ko - 14 * DAY_S)
        - sum(1 for u in au if u.ts >= ctx.ko - 14 * DAY_S)
    )
    if ctx.city:
        out["C07"] = float(au[0].city != ctx.city) if au and au[0].city else math.nan
        out["C08"] = float(hu[0].city != ctx.city) if hu and hu[0].city else math.nan
    else:
        out["C07"] = out["C08"] = math.nan
    if ctx.comp is not None and ctx.season is not None:
        nh = sum(1 for u in hu if u.comp == ctx.comp and u.season == ctx.season)
        na = sum(1 for u in au if u.comp == ctx.comp and u.season == ctx.season)
        out["C09"] = float(min(nh, na))
    else:
        out["C09"] = math.nan
    out["C11"] = ctx.knockout
    main = MAIN_STAT[sp]
    hs, hh = series(store, ctx, ctx.home, main)
    as_, ah = series(store, ctx, ctx.away, main)
    out["S01"] = _m(_ppg(sp, hs), 5) - _m(_ppg(sp, as_), 5)
    out["S02"] = _m(_ppg(sp, hs), 10) - _m(_ppg(sp, as_), 10)
    hm = hs[:, 0] - hs[:, 1] if len(hs) else np.zeros(0)
    am = as_[:, 0] - as_[:, 1] if len(as_) else np.zeros(0)
    out["S03"] = _m(hm, 10) - _m(am, 10)
    out["S04"] = _m(hm, 20) - _m(am, 20)
    out["S05"] = _m(hm[hh] if len(hm) else hm, 10) - _m(am[~ah] if len(am) else am, 10)
    h2h = []
    for u in hu:
        if u.opp != ctx.away:
            continue
        p = store.pair(u.key, main)
        if p is not None:
            h2h.append((p[0] - p[1]) if u.home else (p[1] - p[0]))
    out["C13"] = float(len(h2h))
    out["C14"] = nanmean(h2h[:5]) if h2h else math.nan
    # season table from the league pool (as of the kickoff)
    out["C10"] = out["S06"] = out["S07"] = out["S08"] = math.nan
    if ctx.comp is not None and ctx.season is not None:
        pts: dict[int, list[float]] = defaultdict(list)
        first = None
        for key in store.comp_keys(ctx.comp):
            ts, hid, aid, comp, season = store.events[key]
            if season != ctx.season or ts >= ctx.ko:
                continue
            p = store.pair(key, main)
            if p is None:
                continue
            first = ts if first is None else min(first, ts)
            ph = _ppg(sp, np.array([[p[0], p[1]]]))[0]
            pa = _ppg(sp, np.array([[p[1], p[0]]]))[0]
            pts[hid].append(float(ph))
            pts[aid].append(float(pa))
        if first is not None:
            out["C10"] = (ctx.ko - first) / DAY_S
        if ctx.home in pts and ctx.away in pts:
            ph_, pa_ = nanmean(pts[ctx.home]), nanmean(pts[ctx.away])
            out["S06"] = ph_ - pa_
            out["S07"] = ph_ + pa_
            table = sorted(pts, key=lambda t: -nanmean(pts[t]))
            rank = {t: i for i, t in enumerate(table)}
            out["S08"] = (rank[ctx.away] - rank[ctx.home]) / max(len(table), 1)
    ph = ctx.price_home
    out["S09"] = logit(ph) if ph == ph else math.nan
    out["S11"] = abs(out["S09"]) if ph == ph else math.nan
    ctx.cache["ev"] = out
    return out


def uniform(
    store: Store,
    ctx: Ctx,
    stat: str,
    kind: str,
    o: int,
    n: int = 10,
    ratio: tuple[str, str] | None = None,
) -> float:
    """The uniform rule: side (S for + O against)/2, total the match mean
    (both teams), margin S for - O for. With `ratio` the stat is a ratio of
    sums (numerator stat / denominator stat) per team."""

    def team(t: int) -> tuple[float, float]:
        if ratio:
            num, den = paired_sums(store, ctx, t, ratio[0], ratio[1], n)
            if den[0] <= 0 or den[1] <= 0:
                return math.nan, math.nan
            return num[0] / den[0], num[1] / den[1]
        fa, _ = series(store, ctx, t, stat, n)
        if not len(fa):
            return math.nan, math.nan
        return float(fa[:, 0].mean()), float(fa[:, 1].mean())

    hf, ha = team(ctx.home)
    af, aa = team(ctx.away)
    if kind == "side":
        return (hf + aa) / 2 if o >= 0 else (af + ha) / 2
    if kind == "margin":
        return o * (hf - af)
    return (hf + ha + af + aa) / 2


def paired_sums(
    store: Store,
    ctx: Ctx,
    team: int,
    num: str,
    den: str,
    n: int,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Sums of two stats over the team's newest n units carrying BOTH, each
    oriented (for, against)."""
    sn, sd, k = [0.0, 0.0], [0.0, 0.0], 0
    for u in hist(store, ctx, team):
        a, b = store.pair(u.key, num), store.pair(u.key, den)
        if a is None or b is None:
            continue
        i, j = (0, 1) if u.home else (1, 0)
        sn[0] += a[i]
        sn[1] += a[j]
        sd[0] += b[i]
        sd[1] += b[j]
        k += 1
        if k == n:
            break
    return (sn[0], sn[1]), (sd[0], sd[1])


def team_mean(
    store: Store, ctx: Ctx, team: int, stat: str, col: int, n: int = 10
) -> float:
    fa, _ = series(store, ctx, team, stat, n)
    return float(fa[:, col].mean()) if len(fa) else math.nan


def orient_trio(kind: str, o: int, h: float, a: float, center: float = 0.0) -> float:
    """side: S - center; total: |H - A|; margin: S - O."""
    s, ot = (h, a) if o >= 0 else (a, h)
    if kind == "side":
        return s - center
    if kind == "margin":
        return s - ot
    return abs(h - a)


def pooled_rate(store: Store, ctx: Ctx, stat: str, fn: str, n: int = 20) -> float:
    """A share / ratio over both teams' last n units of a flag stat."""
    vals: list[tuple[float, float]] = []
    for t in (ctx.home, ctx.away):
        fa, _ = series(store, ctx, t, stat, n)
        vals.extend((float(x), float(y)) for x, y in fa)
    if not vals:
        return math.nan
    arr = np.array(vals)
    if fn == "flag":
        return float((arr[:, 0] > 0).mean())
    if fn == "ratio":
        return (
            float(arr[:, 0].sum() / arr[:, 1].sum())
            if arr[:, 1].sum() > 0
            else math.nan
        )
    return float(arr.sum(axis=1).mean())


def sport_tempo(store: Store, ctx: Ctx, kind: str, o: int) -> dict[str, float]:
    sp = ctx.sport
    k = ("tempo", kind, o)
    if k in ctx.cache:
        cached: dict[str, float] = ctx.cache[k]
        return cached
    out: dict[str, float] = {}
    st = kind in STAT
    if sp == "football" and st:
        ph, pa = (
            team_mean(store, ctx, t, "possession", 0) for t in (ctx.home, ctx.away)
        )
        out["T01"] = orient_trio(kind, o, ph, pa, 50.0)
        hf, af = (team_mean(store, ctx, t, "xg", 0) for t in (ctx.home, ctx.away))
        ha, aa = (team_mean(store, ctx, t, "xg", 1) for t in (ctx.home, ctx.away))
        if kind == "side":
            out["T02"] = hf if o >= 0 else af
            out["T03"] = aa if o >= 0 else ha
        elif kind == "margin":
            out["T02"] = o * (hf - af)
            out["T03"] = o * (aa - ha)
        else:
            out["T02"] = hf + af
            out["T03"] = ha + aa
        for fid, s in (
            ("T04", "big_chances"),
            ("T05", "shots_raw"),
            ("T07", "box_touches"),
            ("T08", "final_third"),
            ("T09", "crosses"),
            ("T10", "long_balls"),
            ("T11", "fouls_raw"),
            ("T12", "yellow"),
        ):
            out[fid] = uniform(store, ctx, s, kind, o)
        out["T06"] = uniform(
            store, ctx, "", kind, o, ratio=("corners_raw", "shots_raw")
        )
    if sp == "hockey":
        if st:
            hf, af = (
                team_mean(store, ctx, t, "shots", 0) for t in (ctx.home, ctx.away)
            )
            ha, aa = (
                team_mean(store, ctx, t, "shots", 1) for t in (ctx.home, ctx.away)
            )
            if kind == "side":
                out["T16"] = hf if o >= 0 else af
                out["T17"] = aa if o >= 0 else ha
            elif kind == "margin":
                out["T16"] = o * (hf - af)
                out["T17"] = o * (aa - ha)
            else:
                out["T16"] = hf + af
                out["T17"] = ha + aa

            def save(t: int) -> float:
                gl, sh = paired_sums(store, ctx, t, "goals_reg", "shots", 10)
                return 1 - gl[1] / sh[1] if sh[1] > 0 else math.nan

            sv_h, sv_a = save(ctx.home), save(ctx.away)
            if kind == "side":
                out["T18"] = sv_a if o >= 0 else sv_h
            elif kind == "margin":
                out["T18"] = o * (sv_h - sv_a)
            else:
                out["T18"] = _avg(sv_h, sv_a)
            out["T19"] = uniform(store, ctx, "pim", kind, o)
            ch, ca = (
                team_mean(store, ctx, t, "corsi", 0) for t in (ctx.home, ctx.away)
            )
            out["T22"] = orient_trio(kind, o, ch, ca, 50.0)
        out["T20"] = pooled_rate(store, ctx, "ot", "flag")
        out["T21"] = pooled_rate(store, ctx, "p3_share", "ratio")
    if sp == "basketball":
        if st:
            out["T23"] = uniform(store, ctx, "turnovers", kind, o)
            out["T24"] = uniform(
                store, ctx, "", kind, o, ratio=("threes_pts", "points")
            )
            out["T25"] = uniform(store, ctx, "ft_made", kind, o)
            out["T29"] = uniform(store, ctx, "off_reb", kind, o)
        out["T26"] = pooled_rate(store, ctx, "ot", "flag")
        out["T27"] = pooled_rate(store, ctx, "blowout", "flag")
        out["T28"] = pooled_rate(store, ctx, "q4_share", "ratio")
    if sp == "volleyball":
        out["T30"] = pooled_rate(store, ctx, "sets_played", "mean", 10) / 2
        out["T31"] = pooled_rate(store, ctx, "five_set", "flag")
        out["T32"] = pooled_rate(store, ctx, "pts_per_set", "ratio", 10)
        out["T34"] = pooled_rate(store, ctx, "extra_sets", "ratio")
        swh, swa = (
            team_mean(store, ctx, t, "set_share", 0) for t in (ctx.home, ctx.away)
        )
        pmh, pma = (
            team_mean(store, ctx, t, "pt_margin_set", 0) for t in (ctx.home, ctx.away)
        )
        tk = (
            kind
            if kind in ("margin", "total")
            else ("margin" if kind != "total" else "total")
        )
        out["T33"] = orient_trio(tk, o, swh, swa)
        out["T35"] = orient_trio(tk, o, pmh, pma)
    if sp == "cs2" and ctx.aux is not None:
        mv, mc = ctx.aux
        out["T36"] = pooled_rate(mv, mc, "map_rounds", "mean")
        out["T38"] = pooled_rate(mv, mc, "map_ot", "flag")
        out["T40"] = pooled_rate(store, ctx, "decider", "flag")
        wh, wa = (team_mean(mv, mc, t, "map_win", 0, 20) for t in (ctx.home, ctx.away))
        rh, ra = (
            team_mean(mv, mc, t, "map_rounds", 0, 20)
            - team_mean(mv, mc, t, "map_rounds", 1, 20)
            for t in (ctx.home, ctx.away)
        )
        tk = "margin" if kind != "total" else "total"
        out["T37"] = orient_trio(tk, o, wh, wa)
        out["T42"] = orient_trio(tk, o, rh, ra)
        kh, ka = (team_mean(mv, mc, t, "kpr", 0, 20) for t in (ctx.home, ctx.away))
        if kind == "side":
            out["T43"] = kh if o >= 0 else ka
        elif kind == "margin":
            out["T43"] = o * (kh - ka)
        else:
            out["T43"] = _avg(kh, ka)
        out.update(mv.cs2_extra(ctx))
    ctx.cache[k] = out
    return out


def player_features(
    store: Store,
    ctx: Ctx,
    pid: int | None,
    nick: str | None,
    keys: tuple[str, ...],
    line: float,
    model_mean: float,
) -> tuple[dict[str, float], int]:
    """Player rows: the player's own values from the boxes of both teams'
    past units (as of the kickoff). Returns features and the player's side
    (+1 home, -1 away, 0 unknown)."""
    k = ("pl", pid, nick, keys)
    if k not in ctx.cache:
        rows: list[tuple[int, float, float, float]] = []  # ts, value, seconds, team sum
        dnp_units: list[tuple[int, bool]] = []
        side = 0
        opp_allowed: list[float] = []
        for team, sgn in ((ctx.home, 1), (ctx.away, -1)):
            got = False
            for u in hist(store, ctx, team, 40):
                box = store.box(u.key)
                if not box:
                    continue
                mine = u.home
                found = None
                tot = 0.0
                for bid, (is_home, st) in box.items():
                    if is_home != mine:
                        continue
                    val = sum(st.get(x, 0.0) for x in keys)
                    tot += val
                    if pid is not None and bid == pid:
                        found = (val, st.get("secondsPlayed", math.nan))
                if found is not None and (found[1] != found[1] or found[1] > 0):
                    rows.append((u.ts, found[0], found[1], tot))
                    got = True
                dnp_units.append(
                    (u.ts, found is not None and (found[1] != found[1] or found[1] > 0))
                )
            if got:
                side = sgn
                break
            rows, dnp_units = [], []
        if side:
            o_team = ctx.away if side > 0 else ctx.home
            for u in hist(store, ctx, o_team, 10):
                box = store.box(u.key)
                if not box:
                    continue
                opp_allowed.append(
                    sum(
                        sum(st.get(x, 0.0) for x in keys)
                        for _, (ih, st) in box.items()
                        if ih != u.home
                    )
                )
        ctx.cache[k] = (rows[:20], dnp_units[:10], side, opp_allowed)
    rows, dnp_units, side, opp_allowed = ctx.cache[k]
    out: dict[str, float] = {}
    if rows:
        v: np.ndarray = np.array([r[1] for r in rows])
        sec = np.array([r[2] for r in rows])
        share = np.array([r[1] / r[3] if r[3] > 0 else math.nan for r in rows])
        out["Q01"] = _m(v, 5) - line
        out["Q02"] = _m(v, 10) - line
        out["Q03"] = _m(v, 20) - line
        out["Q04"] = _m(v, 5) - _m(v, 20)
        out["Q05"] = float(v[:10].std(ddof=1)) if len(v) > 2 else math.nan
        out["Q06"] = float((v[:10] > line).mean())
        out["Q07"] = float((v[:20] > line).mean())
        if ctx.sport in ("hockey", "basketball"):
            out["Q08"] = (nanmean(list(sec[:3])) - nanmean(list(sec[:10]))) / 60
            out["Q09"] = nanmean(list(sec[:10])) / 60
            out["Q14"] = (
                float(sum(1 for _, played in dnp_units if not played) / len(dnp_units))
                if dnp_units
                else math.nan
            )
        out["Q10"] = nanmean(list(share[:10]))
        out["Q11"] = nanmean(list(share[:5])) - nanmean(list(share[:20]))
        out["Q12"] = float(sum(1 for r in rows if r[0] >= ctx.ko - 30 * DAY_S))
        out["Q16"] = float(v[0]) - line
        out["Q17"] = _ew(v) - line
    out["Q13"] = nanmean(opp_allowed) if opp_allowed else math.nan
    if model_mean == model_mean:
        out["Q15"] = model_mean - line
    return out, side


# --- football store ----------------------------------------------------------

FB_STEMS = sorted(
    {k[:-4] for k in FOOTBALL_METRICS if k.endswith("_for") and k != "xg_for"}
    | {k[:-4] for k in CARD_INCIDENT_SCOPES if k.endswith("_for")}
)
FB_RAW = {
    "possession": "ballPossession",
    "xg": "expectedGoals",
    "big_chances": "bigChanceCreated",
    "shots_raw": "totalShotsOnGoal",
    "box_touches": "touchesInOppBox",
    "final_third": "finalThirdEntries",
    "crosses": "accurateCross",
    "long_balls": "accurateLongBalls",
    "fouls_raw": "fouls",
    "yellow": "yellowCards",
    "corners_raw": "cornerKicks",
}
GOAL_STEMS = {"goals", "goals_1h", "goals_2h"}


def _pair(a: Any, b: Any) -> tuple[float, float] | None:
    ok = all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (a, b))
    return (float(a), float(b)) if ok else None


def parse_event(ev: dict[str, Any], sport: str) -> dict[str, Any] | None:
    try:
        eid = int(ev["id"])
        ts = int(ev["startTimestamp"])
        hid = int(ev["homeTeam"]["id"])
        aid = int(ev["awayTeam"]["id"])
    except (KeyError, TypeError, ValueError):
        return None
    status = ev.get("status") or {}
    if status.get("type") != "finished" or comparability.is_awarded_event(ev):
        return None
    if comparability.is_friendly_event(ev, SPORT_SLUG[sport]):
        return None
    season = (ev.get("season") or {}).get("id")
    city = (((ev.get("venue") or {}).get("city")) or {}).get("name")
    return {
        "id": eid,
        "ts": ts,
        "hid": hid,
        "aid": aid,
        "comp": comparability.competition_id(ev),
        "season": int(season) if isinstance(season, int) else None,
        "city": str(city) if city else None,
        "stub": {k: ev[k] for k in ("status", "homeScore", "awayScore") if k in ev},
    }


class DbStore(Store):
    """Team histories from the listing index; values parsed on first use."""

    def __init__(self, con: sqlite3.Connection, sport: str) -> None:
        super().__init__()
        self.con = con
        self.sport = sport
        self.stub: dict[int, dict[str, Any]] = {}
        self.comp_index: dict[int | None, list[int]] = defaultdict(list)
        self.boxes: dict[int, dict[int, tuple[bool, dict[str, float]]]] = {}
        self.loaded: set[int] = set()

    def load_team(self, team: int, lo: int, hi: int) -> None:
        if team in self.team_units:
            return
        units: list[Unit] = []
        for (ej,) in self.con.execute(
            "SELECT e.event_json FROM sofa_listing_event m JOIN sofa_listed_event e "
            "ON e.event_id = m.event_id WHERE m.entity_id = ? AND m.kind = 'last' "
            "AND m.start_ts >= ? AND m.start_ts < ?",
            (team, lo, hi),
        ):
            try:
                ev = json.loads(ej)
            except (TypeError, ValueError):
                continue
            rec = parse_event(ev, self.sport)
            if rec is None or team not in (rec["hid"], rec["aid"]):
                continue
            eid = rec["id"]
            if eid not in self.events:
                self.events[eid] = (
                    rec["ts"],
                    rec["hid"],
                    rec["aid"],
                    rec["comp"],
                    rec["season"],
                )
                self.stub[eid] = rec["stub"]
                self.comp_index[rec["comp"]].append(eid)
            home = rec["hid"] == team
            units.append(
                Unit(
                    rec["ts"],
                    eid,
                    home,
                    rec["aid"] if home else rec["hid"],
                    rec["comp"],
                    rec["season"],
                    rec["city"],
                )
            )
        self.team_units[team] = units

    def _stats(self, key: int) -> tuple[dict[str, dict[str, tuple[float, float]]], Any]:
        row = self.con.execute(
            "SELECT statistics_json, incidents_json FROM sofa_event_stats "
            "WHERE sofascore_event_id = ?",
            (key,),
        ).fetchone()
        if not row:
            return {}, None
        flat = extract_flat_statistics(json.loads(row[0])) if row[0] else {}
        inc = json.loads(row[1]) if (row[1] and self.sport == "football") else None
        return flat, inc

    def pair(self, key: int, stat: str) -> tuple[float, float] | None:
        vals = self.vals.get(key)
        if vals is None or (stat not in vals and key not in self.loaded):
            self._load(key)
            vals = self.vals[key]
        return vals.get(stat)

    def _load(self, key: int) -> None:
        stub = self.stub.get(key, {})
        vals: dict[str, tuple[float, float] | None] = self.vals.setdefault(key, {})
        hs, as_ = stub.get("homeScore") or {}, stub.get("awayScore") or {}
        if self.sport == "football":
            for stem in GOAL_STEMS:
                vals[stem] = self._fb(stem, {}, None, stub) if stub else None
            if key not in self.loaded:
                flat, inc = self._stats(key)
                self.loaded.add(key)
                for stem in FB_STEMS:
                    if stem in GOAL_STEMS:
                        continue
                    vals[stem] = (
                        self._fb(stem, flat, inc, stub) if stub and flat else None
                    )
                allp = flat.get("ALL", {})
                for name, raw in FB_RAW.items():
                    vals[name] = allp.get(raw)
            return
        flat, _ = self._stats(key) if self.sport != "volleyball" else ({}, None)
        self.loaded.add(key)
        allp = flat.get("ALL", {})
        per = [_pair(hs.get(f"period{i}"), as_.get(f"period{i}")) for i in range(1, 6)]
        cur = _pair(hs.get("current"), as_.get("current"))
        if self.sport == "hockey":
            if cur is not None:
                vals["goals"] = cur
            p3 = [x for x in per[:3] if x is not None]
            if len(p3) == 3:
                reg = (sum(x[0] for x in p3), sum(x[1] for x in p3))
                vals["goals_reg"] = reg
                for i in range(3):
                    vals[f"goals_p{i + 1}"] = p3[i]
                tot = reg[0] + reg[1]
                vals["p3_share"] = (p3[2][0] + p3[2][1], tot) if tot > 0 else None
                went_on = "overtime" in hs or "period4" in hs
                if cur is not None and cur[0] + cur[1] != tot:
                    went_on = True
                vals["ot"] = (float(went_on), 0.0)
            for name, raw in (
                ("shots", "Shots"),
                ("pim", "SuspensionMinutes"),
                ("corsi", "corsiPct"),
            ):
                vals[name] = allp.get(raw)
        elif self.sport == "basketball":
            if cur is not None:
                vals["points"] = cur
                vals["blowout"] = (float(abs(cur[0] - cur[1]) > 15), 0.0)
            qq = [x for x in per[:4] if x is not None]
            if len(qq) == 4:
                reg = (sum(x[0] for x in qq), sum(x[1] for x in qq))
                vals["points_reg"] = reg
                vals["points_h1"] = (qq[0][0] + qq[1][0], qq[0][1] + qq[1][1])
                vals["points_h2"] = (qq[2][0] + qq[3][0], qq[2][1] + qq[3][1])
                for i in range(4):
                    vals[f"points_q{i + 1}"] = qq[i]
                tot = reg[0] + reg[1]
                vals["q4_share"] = (qq[3][0] + qq[3][1], tot) if tot > 0 else None
                if cur is not None:
                    vals["ot"] = (float(cur[0] + cur[1] > tot), 0.0)
            for name, raw in (
                ("turnovers", "turnovers"),
                ("ft_made", "freeThrowsScored"),
                ("off_reb", "offensiveRebounds"),
            ):
                vals[name] = allp.get(raw)
            t3 = allp.get("threePointersScored")
            has_pts = vals.get("points") is not None
            vals["threes_pts"] = (3 * t3[0], 3 * t3[1]) if (t3 and has_pts) else None
        elif self.sport == "volleyball":
            sets = [x for x in per if x is not None and (x[0] or x[1])]
            if cur is not None and sets:
                vals["sets"] = cur
                n = len(sets)
                pts = (sum(x[0] for x in sets), sum(x[1] for x in sets))
                vals["points"] = pts
                for i, st in enumerate(sets):
                    vals[f"set_{i + 1}"] = st
                vals["sets_played"] = (float(n), float(n))
                vals["five_set"] = (float(n == 5), 0.0)
                vals["pts_per_set"] = (pts[0] + pts[1], float(n))
                extra = sum(
                    1 for i, st in enumerate(sets) if max(st) > (15 if i == 4 else 25)
                )
                vals["extra_sets"] = (float(extra), float(n))
                vals["set_share"] = (cur[0] / n, cur[1] / n)
                pm = (pts[0] - pts[1]) / n
                vals["pt_margin_set"] = (pm, -pm)

    def _fb(
        self,
        stem: str,
        flat: dict[str, dict[str, tuple[float, float]]],
        inc: Any,
        stub: dict[str, Any],
    ) -> tuple[float, float] | None:
        h = extract_metric(stem + "_for", "football", flat, inc, stub, True)
        a = extract_metric(stem + "_for", "football", flat, inc, stub, False)
        if isinstance(h, GapReason) or isinstance(a, GapReason):
            return None
        return float(h), float(a)

    def _box(self, key: int, lineups_json: str) -> None:
        try:
            lu = json.loads(lineups_json)
        except (TypeError, ValueError):
            return
        out: dict[int, tuple[bool, dict[str, float]]] = {}
        for side, is_home in (("home", True), ("away", False)):
            for p in (lu.get(side) or {}).get("players") or []:
                pid = (p.get("player") or {}).get("id")
                st = p.get("statistics") or {}
                if not isinstance(pid, int) or not st:
                    continue
                out[pid] = (
                    is_home,
                    {
                        k: float(v)
                        for k, v in st.items()
                        if isinstance(v, (int, float)) and not isinstance(v, bool)
                    },
                )
        self.boxes[key] = out

    def box(self, key: int) -> dict[int, tuple[bool, dict[str, float]]]:
        if key not in self.boxes:
            row = self.con.execute(
                "SELECT lineups_json FROM sofa_event_stats WHERE "
                "sofascore_event_id = ?",
                (key,),
            ).fetchone()
            self.boxes[key] = {}
            if row and row[0]:
                self._box(key, row[0])
        return self.boxes[key]

    def referee_rates(self, ref: int, ko: int) -> tuple[float, float, float]:
        ys: list[float] = []
        fs: list[float] = []
        for (eid,) in self.con.execute(
            "SELECT event_id FROM sofa_event_referee WHERE referee_id = ? "
            "AND start_ts < ? "
            "ORDER BY start_ts DESC LIMIT 30",
            (ref, ko),
        ):
            if eid not in self.stub:
                self.stub[eid] = {}
            y = self.pair(eid, "yellow")
            f_ = self.pair(eid, "fouls_raw")
            if y is not None:
                ys.append(y[0] + y[1])
            if f_ is not None:
                fs.append(f_[0] + f_[1])
        return (
            nanmean(ys) if ys else math.nan,
            nanmean(fs) if fs else math.nan,
            math.log1p(len(ys)),
        )


class Cs2Store(Store):
    """CS2 series and maps from cs2_series / cs2_map / cs2_player_map. Two unit
    kinds per team: series (key = event id) and maps (key = -game id)."""

    def __init__(self, con: sqlite3.Connection) -> None:
        super().__init__()
        self.con = con
        self.comp_index: dict[int | None, list[int]] = defaultdict(list)
        self.map_units: dict[int, list[Unit]] = {}
        self.map_names: dict[int, str] = {}
        self.players: dict[int, dict[str, tuple[bool, dict[str, float]]]] = {}
        self._series_maps: dict[int, list[int]] = {}

    def load_team(self, team: int, lo: int, hi: int) -> None:
        if team in self.team_units:
            return
        units: list[Unit] = []
        maps: list[Unit] = []
        for eid, ts, comp, season, hid, aid, hm, am, bo in self.con.execute(
            "SELECT sofascore_event_id, start_ts, unique_tournament_id, season_id, "
            "home_id, "
            "away_id, home_maps, away_maps, best_of FROM cs2_series "
            "WHERE (home_id = ? OR away_id = ?) "
            "AND start_ts >= ? AND start_ts < ? AND status_type = 'finished'",
            (team, team, lo, hi),
        ):
            home = hid == team
            opp = aid if home else hid
            if eid not in self.events:
                self.events[eid] = (ts, hid, aid, comp, season)
                self.comp_index[comp].append(eid)
                v: dict[str, tuple[float, float] | None] = {}
                if hm is not None and am is not None:
                    v["maps"] = (float(hm), float(am))
                    if bo == 3:
                        v["decider"] = (float(hm + am == 3), 0.0)
                rounds = [0.0, 0.0]
                for gid, mts, name, hr, ar, ho, ao, st in self.con.execute(
                    "SELECT game_id, start_ts, map_name, home_rounds, away_rounds, "
                    "home_overtime, away_overtime, status_type FROM cs2_map "
                    "WHERE sofascore_event_id = ? ORDER BY map_order",
                    (eid,),
                ):
                    if hr is None or ar is None or st != "finished":
                        continue
                    rounds[0] += hr
                    rounds[1] += ar
                    mv: dict[str, tuple[float, float] | None] = {
                        "map_rounds": (float(hr), float(ar)),
                        "map_ot": (float(bool(ho) or bool(ao) or hr + ar > 24), 0.0),
                        "map_win": (float(hr > ar), float(ar > hr)),
                    }
                    pl = self._players(gid)
                    kh = sum(s.get("kills", 0.0) for ih, s in pl.values() if ih)
                    ka = sum(s.get("kills", 0.0) for ih, s in pl.values() if not ih)
                    if pl:
                        mv["map_kills"] = (kh, ka)
                        mv["kpr"] = (kh / max(hr + ar, 1), ka / max(hr + ar, 1))
                    self.vals[-gid] = mv
                    self.events[-gid] = (int(mts or ts), hid, aid, comp, season)
                    self.map_names[-gid] = str(name or "")
                    self._series_maps.setdefault(eid, []).append(-gid)
                v["rounds"] = (rounds[0], rounds[1])
                self.vals[eid] = v
            units.append(Unit(ts, eid, home, opp, comp, season, None))
            for mk in self._series_maps.get(eid, []):
                maps.append(Unit(self.events[mk][0], mk, home, opp, comp, season, None))
        self.team_units[team] = units
        self.map_units[team] = maps

    def _players(self, gid: int) -> dict[str, tuple[bool, dict[str, float]]]:
        out: dict[str, tuple[bool, dict[str, float]]] = {}
        for side, pid, name, k, d, a, hs in self.con.execute(
            "SELECT side, player_id, player_name, kills, deaths, assists, headshots "
            "FROM cs2_player_map WHERE game_id = ?",
            (gid,),
        ):
            st = {
                "kills": float(k or 0),
                "deaths": float(d or 0),
                "assists": float(a or 0),
                "headshots": float(hs or 0),
                "_pid": float(pid),
            }
            out[fold(name)] = (side == "home", st)
        self.players[-gid] = out
        return out

    def cs2_extra(self, ctx: Ctx) -> dict[str, float]:
        out: dict[str, float] = {}
        pools = []
        churn = []
        last = []
        for t in (ctx.home, ctx.away):
            mu = [
                u
                for u in as_of(self.map_units.get(t, []), ctx.ko)
                if u.ts >= ctx.ko - 60 * DAY_S
            ]
            cnt: dict[str, int] = defaultdict(int)
            for u in mu:
                cnt[self.map_names.get(u.key, "")] += 1
            pools.append({m for m, c in cnt.items() if c >= 2 and m})
            mu_all = as_of(self.map_units.get(t, []), ctx.ko)[:10]

            def roster(us: list[Unit]) -> set[str]:
                s: set[str] = set()
                for u in us:
                    for nm, (ih, _) in self.players.get(u.key, {}).items():
                        if ih == u.home:
                            s.add(nm)
                return s

            r1, r2 = roster(mu_all[:5]), roster(mu_all[5:10])
            if r1 and r2:
                churn.append(len(r1 - r2) / len(r1))
            su = as_of(self.units(t), ctx.ko)
            if su:
                last.append((ctx.ko - su[0].ts) / DAY_S)
        out["T39"] = float(len(pools[0] & pools[1]))
        out["T41"] = nanmean(churn) if churn else math.nan
        out["T44"] = min(last) if len(last) == 2 else math.nan
        return out


class Cs2MapView(Store):
    """The CS2 store seen through map units (map families)."""

    def __init__(self, base: Cs2Store) -> None:
        super().__init__()
        self.base = base
        self.events = base.events
        self.vals = base.vals
        self.comp_index: dict[int | None, list[int]] = defaultdict(list)
        for k, ev in base.events.items():
            if k < 0:
                self.comp_index[ev[3]].append(k)

    def units(self, team: int) -> list[Unit]:
        return self.base.map_units.get(team, [])

    def cs2_extra(self, ctx: Ctx) -> dict[str, float]:
        return self.base.cs2_extra(ctx)


# --- dataset -----------------------------------------------------------------


@dataclass
class Rows:
    sport: list[str] = field(default_factory=list)
    family: list[str] = field(default_factory=list)
    kind: list[str] = field(default_factory=list)
    day: list[str] = field(default_factory=list)
    match: list[int] = field(default_factory=list)
    y: list[float] = field(default_factory=list)
    p: list[float] = field(default_factory=list)
    q: list[float] = field(default_factory=list)
    x: list[np.ndarray] = field(default_factory=list)

    def add(
        self,
        sport: str,
        family: str,
        kind: str,
        day: str,
        match: int,
        y: float,
        p: float,
        q: float,
        feats: dict[str, float],
    ) -> None:
        row = np.full(NF, np.nan, dtype=np.float32)
        for k, v in feats.items():
            if k in FID and v is not None and v == v and math.isfinite(v):
                row[FID[k]] = v
        self.sport.append(sport)
        self.family.append(family)
        self.kind.append(kind)
        self.day.append(day)
        self.match.append(match)
        self.y.append(y)
        self.p.append(p)
        self.q.append(q)
        self.x.append(row)


def load(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def football_kind(market: str) -> tuple[str, str | None]:
    stems = set(FB_STEMS)
    if market.startswith("player"):
        return "skip", None
    if market in ("result_1x2", "double_chance", "draw_no_bet", "result_handicap"):
        return "margin", "goals"
    for pre in ("most_", "handicap_"):
        if market.startswith(pre) and market[len(pre) :] in stems:
            return "margin", market[len(pre) :]
    if market.endswith("_total") and market[:-6] in stems:
        return "total", market[:-6]
    if market.endswith("_for") and market[:-4] in stems:
        return "side", market[:-4]
    return "other", None


def fb_margin_line(market: str, subject: str, line: float) -> float:
    if market == "double_chance":
        return 0.5
    if market in ("result_1x2", "draw_no_bet") or market.startswith("most_"):
        return 0.0
    return line


def current_event(con: sqlite3.Connection, eid: int) -> dict[str, Any]:
    row = con.execute(
        "SELECT event_json FROM sofa_listed_event WHERE event_id = ?", (eid,)
    ).fetchone()
    if row:
        try:
            ev = json.loads(row[0])
            if isinstance(ev, dict):
                return ev
        except (TypeError, ValueError):
            pass
    row = con.execute(
        "SELECT detail_json FROM sofa_event_detail WHERE sofascore_event_id = ?", (eid,)
    ).fetchone()
    if row:
        try:
            d = json.loads(row[0])
            ev = d.get("event", d) if isinstance(d, dict) else {}
            return ev if isinstance(ev, dict) else {}
        except (TypeError, ValueError):
            pass
    return {}


def ev_meta(ev: dict[str, Any]) -> tuple[str | None, float]:
    city = (((ev.get("venue") or {}).get("city")) or {}).get("name")
    ko = float(comparability.is_knockout(ev)) if ev else math.nan
    return (str(city) if city else None), ko


def build_football(con: sqlite3.Connection, rows: Rows, log: dict[str, Any]) -> None:
    store = DbStore(con, "football")
    q = (
        "SELECT run_date, sofascore_event_id, market, subject, line, sample_size, "
        "sample_mean, "
        "sample_sd, p_central, market_p, offered_odds, outcome FROM sofa_settled_row "
        "WHERE sport = 'football' AND run_date BETWEEN ? AND ? "
        "AND outcome IN ('WIN','LOSS') "
        "AND market_p IS NOT NULL AND direction = 'OVER'"
    )
    by_event: dict[tuple[str, int], list[tuple[Any, ...]]] = defaultdict(list)
    for r in con.execute(q, (FROM_DAY, TO_DAY)):
        by_event[(r[0], int(r[1]))].append(r)
    fixtures: dict[str, dict[int, dict[str, Any]]] = {}
    boards: dict[str, dict[str, dict[str, Any]]] = {}
    for d in days(FROM_DAY, TO_DAY):
        fp, bp = RUNS / d / "02_fixtures.json", RUNS / d / "01_board.json"
        fixtures[d] = {
            int(f["sofascore_event_id"]): f
            for f in (load(fp) if fp.exists() else [])
            if f.get("sport") == "football" and f.get("sofascore_event_id")
        }
        boards[d] = {
            str(b["superbet_event_id"]): b for b in (load(bp) if bp.exists() else [])
        }
    # pass 1: histories
    ctxs: dict[tuple[str, int], Ctx] = {}
    for d, eid in sorted(by_event):
        f = fixtures.get(d, {}).get(eid)
        if not f or not f.get("home_entity_id") or not f.get("away_entity_id"):
            log["fb_no_fixture_events"] = log.get("fb_no_fixture_events", 0) + 1
            continue
        ko = ts_of(f["kickoff_utc"])
        h, a = int(f["home_entity_id"]), int(f["away_entity_id"])
        for t in (h, a):
            store.load_team(
                t,
                ts_of(FROM_DAY + "T00:00:00Z") - (HISTORY_DAYS + 2) * DAY_S,
                ts_of(TO_DAY + "T23:59:59Z"),
            )
        ev = current_event(con, eid)
        city, kn = ev_meta(ev)
        if kn != kn and f.get("cup_round_type") is not None:
            kn = 1.0
        ref = con.execute(
            "SELECT referee_id FROM sofa_event_referee WHERE event_id = ?", (eid,)
        ).fetchone()
        ctxs[(d, eid)] = Ctx(
            "football",
            ko,
            h,
            a,
            f.get("competition_id"),
            f.get("season_id"),
            city,
            kn,
            math.nan,
            int(ref[0]) if ref and ref[0] else None,
        )
    # event-level price: de-vigged home win (DNB "1", else 1X2 1 / (1 + 2))
    for key, rs in by_event.items():
        c = ctxs.get(key)
        if c is None:
            continue
        p1 = {r[3]: r[9] for r in rs if r[2] == "result_1x2"}
        dnb = [r[9] for r in rs if r[2] == "draw_no_bet" and r[3] == "1"]
        if dnb:
            c.price_home = float(dnb[0])
        elif "1" in p1 and "2" in p1 and p1["1"] + p1["2"] > 0:
            c.price_home = float(p1["1"] / (p1["1"] + p1["2"]))
    n_done = 0
    unresolved = 0
    for key in sorted(by_event):
        c = ctxs.get(key)
        if c is None:
            continue
        d, eid = key
        f = fixtures[d][eid]
        names = [
            (boards[d].get(str(s)) or {}) for s in f.get("superbet_event_ids") or []
        ]
        side_a = {fold(b.get("side_a")) for b in names}
        side_b = {fold(b.get("side_b")) for b in names}
        evf = event_features(store, c)
        ref = (
            store.referee_rates(c.referee, c.ko)
            if c.referee
            else (math.nan, math.nan, math.nan)
        )
        for r in by_event[key]:
            (_, _, market, subject, line, n_s, mean_s, sd_s, p, mp, odds, outcome) = r
            kind, stem = football_kind(market)
            if kind == "skip":
                continue
            o = 1
            if kind in ("side", "margin"):
                sj = fold(subject)
                if sj == "x":
                    continue
                if sj in ("1", "1x"):
                    o = 1
                elif sj in ("2", "x2"):
                    o = -1
                elif sj in side_a:
                    o = 1
                elif sj in side_b:
                    o = -1
                else:
                    unresolved += 1
                    continue
                if market == "draw_no_bet" and sj != "1":
                    continue
            feats: dict[str, float] = {}
            lv = float(line)
            if kind in STAT and stem is not None:
                base = stat_base(store, c, kind, stem, o)
                lv_ = fb_margin_line(market, subject, lv) if kind == "margin" else lv
                feats.update(stat_features(base, kind, lv_))
                feats.update(sport_tempo(store, c, kind, o))
                if kind in COUNT and sd_s and sd_s > 0:
                    feats["P06"] = (mean_s - lv) / sd_s
            feats.update(orient(evf, o if kind in ("side", "margin") else 1))
            feats["T13"], feats["T14"], feats["T15"] = ref
            feats["P01"] = logit(mp)
            feats["P02"] = (1.0 / (odds * mp) - 1.0) if odds and mp else math.nan
            feats["P05"] = lv
            feats["P07"] = math.log1p(n_s or 0)
            rows.add(
                "football",
                market,
                kind,
                d,
                eid,
                1.0 if outcome == "WIN" else 0.0,
                float(p),
                float(mp),
                feats,
            )
        n_done += 1
        if n_done % 2000 == 0:
            print(
                f"football {n_done}/{len(ctxs)} events, {len(rows.y)} rows",
                file=sys.stderr,
                flush=True,
            )
        c.cache.clear()
    log["fb_subject_unresolved_rows"] = unresolved
    log["fb_events"] = n_done


ORIENTED = ("C03", "C06", "C14", "S01", "S02", "S03", "S04", "S05", "S06", "S08", "S09")


def orient(evf: dict[str, float], o: int) -> dict[str, float]:
    out = dict(evf)
    for k in ORIENTED:
        if k in out:
            out[k] = out[k] * o
    return out


# --- measured sports ---------------------------------------------------------

SPORT_FAMILY: dict[str, dict[str, tuple[str, str]]] = {
    "hockey": {
        "total": ("total", "goals_reg"),
        "team_total": ("side", "goals_reg"),
        "period_total": ("total", "goals_p{p}"),
        "period_team_total": ("side", "goals_p{p}"),
        "handicap": ("margin", "goals_reg"),
        "winner": ("margin", "goals"),
        "result_1x2": ("margin", "goals_reg"),
        "double_chance": ("margin", "goals_reg"),
        "period_handicap": ("margin", "goals_p{p}"),
        "period_1x2": ("margin", "goals_p{p}"),
        "period_dnb": ("margin", "goals_p{p}"),
        "period_double_chance": ("margin", "goals_p{p}"),
    },
    "basketball": {
        "total": ("total", "points"),
        "team_total": ("side", "points"),
        "handicap": ("margin", "points"),
        "winner": ("margin", "points"),
        "result_1x2": ("margin", "points_reg"),
        "double_chance": ("margin", "points_reg"),
        "h1_total": ("total", "points_h1"),
        "h1_team_total": ("side", "points_h1"),
        "h1_handicap": ("margin", "points_h1"),
        "h1_1x2": ("margin", "points_h1"),
        "h1_dnb": ("margin", "points_h1"),
        "h2_total": ("total", "points_h2"),
        "h2_team_total": ("side", "points_h2"),
        "h2_handicap": ("margin", "points_h2"),
        "quarter_total": ("total", "points_q{p}"),
        "quarter_team_total": ("side", "points_q{p}"),
        "quarter_handicap": ("margin", "points_q{p}"),
        "quarter_1x2": ("margin", "points_q{p}"),
        "quarter_dnb": ("margin", "points_q{p}"),
    },
    "volleyball": {
        "winner": ("margin", "sets"),
        "set_handicap": ("margin", "sets"),
        "sets_total": ("total", "sets"),
        "points_total": ("total", "points"),
        "points_handicap": ("margin", "points"),
        "set_winner": ("margin", "set_{p}"),
        "set_points_total": ("total", "set_{p}"),
    },
    "cs2": {
        "map_rounds_total": ("total", "map_rounds"),
        "map_team_rounds": ("side", "map_rounds"),
        "map_rounds_handicap": ("margin", "map_rounds"),
        "map_winner": ("margin", "map_rounds"),
        "team_kills": ("side", "map_kills"),
        "match_winner": ("margin", "maps"),
        "maps_handicap": ("margin", "maps"),
        "rounds_total": ("total", "rounds"),
        "team_rounds": ("side", "rounds"),
        "rounds_handicap": ("margin", "rounds"),
    },
}
CANON_SIDES = {"OVER", "T1", "YES", "ODD", "1X", "X2"}
THREE_WAY = {"result_1x2", "period_1x2", "quarter_1x2", "h1_1x2"}


def sport_dir(sport: str, day: str) -> Path:
    return RUNS / "cs2" / day if sport == "cs2" else RUNS / "shadow" / sport / day


def margin_line(family: str, side: str, line: Any) -> float:
    if side in ("1X", "X2"):
        return 0.5
    if line is None:
        return 0.0
    return float(line)


def first_fair(
    sport: str, day: str
) -> dict[tuple[str, Any, Any, str, Any, str], float]:
    """De-vigged p of every line in each event's FIRST snapshot."""
    out: dict[tuple[str, Any, Any, str, Any, str], float] = {}
    path = sport_dir(sport, day) / "snapshots.jsonl"
    if not path.exists():
        return out
    seen: set[str] = set()
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            sb = str(rec.get("superbet_event_id"))
            if sb in seen:
                continue
            seen.add(sb)
            groups: dict[tuple[Any, ...], dict[str, float]] = defaultdict(dict)
            for ln in rec.get("lines") or []:
                per = ln.get("map_nr") if sport == "cs2" else ln.get("period")
                if ln.get("odds"):
                    groups[
                        (
                            ln["family"],
                            per,
                            str(ln.get("subject") or ""),
                            ln.get("line"),
                        )
                    ][ln["side"]] = float(ln["odds"])
            for (fam, per, subj, line), sides in groups.items():
                if len(sides) < 2:
                    continue
                inv = {s: 1 / o for s, o in sides.items() if o > 1}
                tot = sum(inv.values())
                for s, v in inv.items():
                    out[(sb, fam, per, subj, line, s)] = v / tot
    return out


def build_sport(
    con: sqlite3.Connection, sport: str, rows: Rows, rows_dir: str, log: dict[str, Any]
) -> None:
    store: Store
    cs2 = sport == "cs2"
    base_store: DbStore | Cs2Store = Cs2Store(con) if cs2 else DbStore(con, sport)
    store = base_store
    map_view: Cs2MapView | None = None
    team_p: dict[tuple[Any, ...], float] = {}
    if not cs2:
        with (Path(rows_dir) / f"{sport}_superbet_settled.jsonl").open(
            encoding="utf-8"
        ) as fh:
            for raw in fh:
                r = json.loads(raw)
                _s, d, sb = r["game"].split(":")
                team_p[
                    (
                        d,
                        sb,
                        int(r["market_id"] or 0),
                        int(r["period"] or 0),
                        str(r["subject"] or ""),
                        r["line"],
                        r["side"],
                    )
                ] = float(r["p"])
    pmodel: dict[tuple[str, str, str], tuple[int | None, float]] = {}
    work: list[tuple[str, str, dict[str, Any], list[dict[str, Any]]]] = []
    lo = ts_of(FROM_DAY + "T00:00:00Z") - (HISTORY_DAYS + 2) * DAY_S
    hi = ts_of(TO_DAY + "T23:59:59Z") + 2 * DAY_S
    for d in days(FROM_DAY, TO_DAY):
        sp = sport_dir(sport, d) / "settled.json"
        if not sp.exists():
            continue
        pm = sport_dir(sport, d) / "player_model.jsonl"
        if pm.exists():
            with pm.open(encoding="utf-8") as fh:
                for raw in fh:
                    r = json.loads(raw)
                    pmodel[
                        (str(r["superbet_event_id"]), r["family"], str(r["subject"]))
                    ] = (
                        r.get("model_player_id"),
                        float(r["model_mean"])
                        if r.get("model_mean") is not None
                        else math.nan,
                    )
        doc = load(sp)
        for sb, ev in (doc.get("events") or {}).items():
            graded = ev.get("graded")
            if not isinstance(graded, list) or not ev.get("sofascore_event_id"):
                continue
            if not ev.get("sofascore_home_id") or not ev.get("sofascore_away_id"):
                continue
            work.append((d, str(sb), ev, graded))
            for t in (int(ev["sofascore_home_id"]), int(ev["sofascore_away_id"])):
                base_store.load_team(t, lo, hi)
    if cs2:
        assert isinstance(base_store, Cs2Store)
        map_view = Cs2MapView(base_store)
    player_keys: dict[str, tuple[str, ...]] = {}
    markets: dict[int, Any] = dict(PLAYER_MARKETS.get(sport, {}))  # type: ignore[call-overload]
    for spec in markets.values():
        player_keys[spec.family] = spec.keys
    stats: dict[str, int] = defaultdict(int)
    snaps: dict[str, dict[tuple[Any, ...], float]] = {}
    for i, (d, sb, ev, graded) in enumerate(work):
        if d not in snaps:
            snaps.clear()
            snaps[d] = first_fair(sport, d)
        ko = ts_of(str(ev.get("sofascore_start_utc") or ev.get("kickoff_utc")))
        eid = int(ev["sofascore_event_id"])
        h, a = int(ev["sofascore_home_id"]), int(ev["sofascore_away_id"])
        h_is_t1 = bool(ev.get("home_is_team1", True))
        comp: int | None
        season: Any
        city: str | None
        if cs2:
            row = con.execute(
                "SELECT unique_tournament_id, season_id FROM cs2_series WHERE "
                "sofascore_event_id = ?",
                (eid,),
            ).fetchone()
            comp, season, city, kn = (
                (row[0], row[1], None, math.nan)
                if row
                else (None, None, None, math.nan)
            )
        else:
            cev = current_event(con, eid)
            comp = comparability.competition_id(cev) if cev else None
            season = (cev.get("season") or {}).get("id") if cev else None
            city, kn = ev_meta(cev)
        # event-level price (home two-way)
        ph = math.nan
        win = {
            g["side"]: g["fair_p"]
            for g in graded
            if g.get("family") in ("winner", "match_winner")
            and not g.get("period")
            and not g.get("map_nr")
            and g.get("fair_p") is not None
        }
        x12 = {
            g["side"]: g["fair_p"]
            for g in graded
            if g.get("family") == "result_1x2"
            and not g.get("period")
            and g.get("fair_p") is not None
        }
        if "T1" in win:
            ph = float(win["T1"])
        elif "T1" in x12 and "T2" in x12:
            ph = float(x12["T1"] / (x12["T1"] + x12["T2"]))
        if ph == ph and not h_is_t1:
            ph = 1 - ph
        ctx = Ctx(
            sport,
            ko,
            h,
            a,
            comp,
            season if isinstance(season, int) else None,
            city,
            kn,
            ph,
        )
        mctx = Ctx(sport, ko, h, a, comp, ctx.season, city, kn, ph) if cs2 else None
        if map_view is not None:
            ctx.aux = (map_view, mctx)
        evf = event_features(store, ctx)
        t1n, t2n = fold(ev.get("team1")), fold(ev.get("team2"))
        for g in graded:
            if g.get("outcome") not in ("WIN", "LOSS") or g.get("fair_p") is None:
                continue
            fam, side = str(g["family"]), str(g["side"])
            is_player = fam.startswith("player")
            if fam in THREE_WAY:
                if side not in ("T1", "T2"):
                    continue
            elif side not in CANON_SIDES:
                stats["side_not_canonical"] += 1
                continue
            per = g.get("map_nr") if cs2 else g.get("period")
            if cs2 or is_player:
                if g.get("model_p") is None:
                    stats["no_model_p"] += 1
                    continue
                p = float(g["model_p"])
            else:
                k = (
                    d,
                    sb,
                    int(g.get("market_id") or 0),
                    int(g.get("period") or 0),
                    str(g.get("subject") or ""),
                    g.get("line"),
                    side,
                )
                if k not in team_p:
                    stats["no_team_p"] += 1
                    continue
                p = team_p[k]
            # orientation: +1 when the selection's team is the home side
            t1 = side in ("T1", "1X") or (
                side not in ("T2", "X2") and str(g.get("subject")) == "T1"
            )
            subj = fold(g.get("subject"))
            if cs2 and subj:
                t1 = subj == t1n if subj in (t1n, t2n) else t1
            o = 1 if t1 == h_is_t1 else -1
            feats: dict[str, float] = {}
            spec = SPORT_FAMILY.get(sport, {}).get(fam)
            kind = "player" if is_player else (spec[0] if spec else "other")
            if kind == "side" and not (
                str(g.get("subject")) in ("T1", "T2") or (cs2 and subj in (t1n, t2n))
            ):
                kind = "other"
            line = g.get("line")
            lv = float(line) if line is not None else 0.0
            if spec and kind in STAT:
                stat = spec[1].replace("{p}", str(per or 0))
                use_map = cs2 and stat.startswith("map_")
                st_: Store = map_view if (use_map and map_view is not None) else store
                cx = mctx if (use_map and mctx is not None) else ctx
                base = stat_base(st_, cx, kind, stat, o if kind != "total" else 1)
                lv_ = margin_line(fam, side, line) if kind == "margin" else lv
                feats.update(stat_features(base, kind, lv_))
            if kind != "player":
                feats.update(sport_tempo(store, ctx, kind, o if kind != "total" else 1))
                feats.update(orient(evf, o if kind in ("side", "margin") else 1))
            else:
                keys = player_keys.get(fam) or ((fam[len("player_") :],) if cs2 else ())
                pid, mmean = pmodel.get(
                    (sb, fam, str(g.get("subject"))), (None, math.nan)
                )
                if cs2:
                    assert map_view is not None and mctx is not None
                    pf, pside = cs2_player(
                        map_view, mctx, fold(g.get("subject")), keys, lv
                    )
                else:
                    pf, pside = player_features(
                        store,
                        ctx,
                        pid if isinstance(pid, int) else None,
                        None,
                        keys,
                        lv,
                        mmean,
                    )
                feats.update(pf)
                feats.update(orient(evf, pside or 1))
                if cs2:
                    feats.update(sport_tempo(store, ctx, "other", 1))
            fair = float(g["fair_p"])
            feats["P01"] = logit(fair)
            feats["P02"] = (
                float(g["overround"]) if g.get("overround") is not None else math.nan
            )
            ff = snaps[d].get((sb, fam, per, str(g.get("subject") or ""), line, side))
            feats["P03"] = logit(fair) - logit(ff) if ff is not None else math.nan
            mb = g.get("minutes_before_kickoff")
            feats["P04"] = float(mb) if mb is not None else math.nan
            feats["P05"] = lv
            rows.add(
                sport,
                fam,
                kind,
                d,
                eid,
                1.0 if g["outcome"] == "WIN" else 0.0,
                p,
                fair,
                feats,
            )
            stats["rows"] += 1
        ctx.cache.clear()
        if mctx is not None:
            mctx.cache.clear()
        if (i + 1) % 1000 == 0:
            print(
                f"{sport} {i + 1}/{len(work)} events, {stats['rows']} rows",
                file=sys.stderr,
                flush=True,
            )
    log[sport] = dict(stats) | {"events": len(work)}


def cs2_player(
    view: Cs2MapView,
    ctx: Ctx,
    nick: str,
    keys: tuple[str, ...],
    line: float,
) -> tuple[dict[str, float], int]:
    """A CS2 player's per-map values (maps of either team, as of the kickoff),
    found by his folded nickname on the team's own side of the map."""
    k = ("cs2pl", nick, keys)
    if k not in ctx.cache:
        vals: list[tuple[int, float, float]] = []
        side = 0
        opp_allowed: list[float] = []
        for team, sgn in ((ctx.home, 1), (ctx.away, -1)):
            for u in hist(view, ctx, team, 40):
                pl = view.base.players.get(u.key, {})
                if nick in pl and pl[nick][0] == u.home:
                    st = pl[nick][1]
                    tot = sum(
                        sum(s.get(x, 0.0) for x in keys)
                        for ih, s in pl.values()
                        if ih == u.home
                    )
                    vals.append((u.ts, sum(st.get(x, 0.0) for x in keys), tot))
            if vals:
                side = sgn
                o_team = ctx.away if sgn > 0 else ctx.home
                for u in hist(view, ctx, o_team, 10):
                    pl = view.base.players.get(u.key, {})
                    if pl:
                        opp_allowed.append(
                            sum(
                                sum(s.get(x, 0.0) for x in keys)
                                for ih, s in pl.values()
                                if ih != u.home
                            )
                        )
                break
        ctx.cache[k] = (vals[:20], side, opp_allowed)
    vals, side, opp_allowed = ctx.cache[k]
    out: dict[str, float] = {}
    if vals:
        v = np.array([r[1] for r in vals])
        share = np.array([r[1] / r[2] if r[2] > 0 else math.nan for r in vals])
        out.update(
            {
                "Q01": _m(v, 5) - line,
                "Q02": _m(v, 10) - line,
                "Q03": _m(v, 20) - line,
                "Q04": _m(v, 5) - _m(v, 20),
                "Q05": float(v[:10].std(ddof=1)) if len(v) > 2 else math.nan,
                "Q06": float((v[:10] > line).mean()),
                "Q07": float((v[:20] > line).mean()),
                "Q10": nanmean(list(share[:10])),
                "Q11": nanmean(list(share[:5])) - nanmean(list(share[:20])),
                "Q12": float(sum(1 for r in vals if r[0] >= ctx.ko - 30 * DAY_S)),
                "Q16": float(v[0]) - line,
                "Q17": _ew(v) - line,
            }
        )
    out["Q13"] = nanmean(opp_allowed) if opp_allowed else math.nan
    return out, side


def cmd_build(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(f"file:{args.db_path}?mode=ro", uri=True)
    log: dict[str, Any] = {"built_at": datetime.now(UTC).isoformat()}
    for sport in args.sports.split(","):
        rows = Rows()
        if sport == "football":
            build_football(con, rows, log)
        else:
            build_sport(con, sport, rows, args.rows_dir, log)
        data = {
            "sport": np.array(rows.sport),
            "family": np.array(rows.family),
            "kind": np.array(rows.kind),
            "day": np.array(rows.day),
            "match": np.array(rows.match, dtype=np.int64),
            "y": np.array(rows.y),
            "p": np.array(rows.p),
            "q": np.array(rows.q),
            "x": np.vstack(rows.x) if rows.x else np.zeros((0, NF), dtype=np.float32),
        }
        with (out / f"rows_{sport}.pkl").open("wb") as fh:
            pickle.dump(data, fh)
        print(f"{sport}: {len(rows.y)} rows", file=sys.stderr, flush=True)
        (out / "build_log.json").write_text(
            json.dumps(log, indent=1, default=str), encoding="utf-8"
        )
    return 0


# --- evaluation --------------------------------------------------------------


def fit_logistic(
    xm: np.ndarray, y: np.ndarray, lam: float = 1e-3, iters: int = 50
) -> np.ndarray:
    """Newton-Raphson logistic regression; L2 `lam` on every column but the first."""
    n, k = xm.shape
    w = np.zeros(k)
    pen = np.full(k, lam)
    pen[0] = 0.0
    for _ in range(iters):
        z = np.clip(xm @ w, -30, 30)
        m = 1 / (1 + np.exp(-z))
        g = xm.T @ (m - y) + pen * w
        hss = (xm * (m * (1 - m))[:, None]).T @ xm + np.diag(pen) + 1e-9 * np.eye(k)
        step = np.linalg.solve(hss, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w


def predict(xm: np.ndarray, w: np.ndarray) -> np.ndarray:
    return np.asarray(1 / (1 + np.exp(-np.clip(xm @ w, -30, 30))))


def design(
    f: np.ndarray | None,
    lp: np.ndarray,
    stats: tuple[float, float, bool] | None,
) -> np.ndarray:
    cols = [np.ones_like(lp), lp]
    if f is not None and stats is not None:
        mu, sd, miss = stats
        z = np.where(np.isnan(f), 0.0, np.clip((f - mu) / sd, -5, 5))
        cols.append(z)
        if miss:
            cols.append(np.isnan(f).astype(float))
    return np.column_stack(cols)


def bh(pvals: Sequence[float], q: float) -> np.ndarray:
    """Benjamini-Hochberg step-up: a boolean mask of the rejected hypotheses."""
    p = np.asarray(pvals, dtype=float)
    m = len(p)
    if not m:
        return np.zeros(0, dtype=bool)
    order = np.argsort(p)
    thresh = q * np.arange(1, m + 1) / m
    passed = p[order] <= thresh
    k = int(np.max(np.nonzero(passed)[0])) + 1 if passed.any() else 0
    mask = np.zeros(m, dtype=bool)
    mask[order[:k]] = True
    return mask


class Boot:
    """Match-level bootstrap weights for one hold-out cell."""

    def __init__(self, matches: np.ndarray, reps: int = BOOT, seed: int = 11) -> None:
        self.uniq, self.inv = np.unique(matches, return_inverse=True)
        rng = np.random.default_rng(seed)
        nm = len(self.uniq)
        self.W = np.stack(
            [np.bincount(rng.integers(0, nm, nm), minlength=nm) for _ in range(reps)]
        ).astype(float)
        self.n_m = np.bincount(self.inv, minlength=nm).astype(float)

    def stats(self, d: np.ndarray) -> tuple[float, float, float, float]:
        """mean, CI low, CI high, one-sided p (H1: mean < 0, cluster z)."""
        g = np.bincount(self.inv, weights=d, minlength=len(self.uniq))
        n = self.n_m.sum()
        mean = float(g.sum() / n)
        bs = (self.W @ g) / (self.W @ self.n_m)
        lo, hi = np.percentile(bs, [2.5, 97.5])
        nm = len(g)
        resid = g - mean * self.n_m
        se = math.sqrt(nm / max(nm - 1, 1) * float((resid**2).sum())) / n
        z = mean / se if se > 0 else 0.0
        pval = 0.5 * math.erfc(-z / math.sqrt(2))
        return mean, float(lo), float(hi), pval


def brier(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.asarray((p - y) ** 2)


def logloss(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.asarray(-(y * np.log(p) + (1 - y) * np.log(1 - p)))


def applicable(sport: str, kind: str) -> list[int]:
    return [
        i
        for i, f in enumerate(FEATURES)
        if f.measured and sport in f.sports and kind in f.kinds
    ]


def everything(
    xd: np.ndarray,
    yd: np.ndarray,
    dd: np.ndarray,
    xh: np.ndarray,
) -> tuple[np.ndarray, float]:
    """L2 logistic on all columns; lambda chosen on the last 30% of the
    development days (time split), then refitted on all development."""
    cut = np.quantile(np.unique(dd).astype("datetime64[D]").astype(int), 0.7)
    di = dd.astype("datetime64[D]").astype(int)
    tr, va = di <= cut, di > cut
    best, best_lam = math.inf, 10.0
    if tr.sum() > 50 and va.sum() > 50:
        for lam in LAMBDA_GRID:
            w = fit_logistic(xd[tr], yd[tr], lam)
            s = float(brier(predict(xd[va], w), yd[va]).mean())
            if s < best:
                best, best_lam = s, lam
    w = fit_logistic(xd, yd, best_lam)
    return predict(xh, w), best_lam


def cmd_evaluate(args: argparse.Namespace) -> int:
    out = Path(args.out)
    results: list[dict[str, Any]] = []
    families: list[dict[str, Any]] = []
    upper: dict[str, Any] = {}
    s10_note: dict[str, Any] = {}
    for sport in SPORTS:
        path = out / f"rows_{sport}.pkl"
        if not path.exists():
            continue
        with path.open("rb") as fh:
            data = pickle.load(fh)
        split = HOLDOUT_FROM
        if args.dev_check:
            # a dry run of the whole method on development days only (the
            # hold-out untouched): its last third plays the hold-out
            keep = data["day"] < HOLDOUT_FROM
            data = {k: v[keep] for k, v in data.items()}
            split = DEV_CHECK_SPLIT
        xa: np.ndarray = data["x"].astype(float)
        dev_all = data["day"] < split
        # S10: residual of logit(price home) ~ S04, fitted on development rows
        s9, s4 = xa[:, FID["S09"]] * 1.0, xa[:, FID["S04"]] * 1.0
        ok = dev_all & ~np.isnan(s9) & ~np.isnan(s4)
        if ok.sum() > 50:
            amat = np.column_stack([np.ones(ok.sum()), s4[ok]])
            coef = np.linalg.lstsq(amat, s9[ok], rcond=None)[0]
            xa[:, FID["S10"]] = s9 - (coef[0] + coef[1] * s4)
            s10_note[sport] = [float(coef[0]), float(coef[1])]
        pooled_h: dict[str, list[np.ndarray]] = defaultdict(list)
        fams = sorted(set(zip(data["family"], data["kind"], strict=True)))
        for fam, kind in fams:
            sel = (data["family"] == fam) & (data["kind"] == kind)
            dev, hold = sel & dev_all, sel & ~dev_all
            n_dev_m = len(np.unique(data["match"][dev]))
            n_hold_m = len(np.unique(data["match"][hold]))
            info: dict[str, Any] = {
                "sport": sport,
                "family": fam,
                "kind": kind,
                "rows_dev": int(dev.sum()),
                "rows_hold": int(hold.sum()),
                "matches_dev": n_dev_m,
                "matches_hold": n_hold_m,
            }
            if n_hold_m < MIN_HOLD_MATCHES or n_dev_m < MIN_DEV_MATCHES:
                info["tested"] = False
                families.append(info)
                continue
            yd, yh = data["y"][dev], data["y"][hold]
            lpd = np.array([logit(v) for v in data["p"][dev]])
            lph = np.array([logit(v) for v in data["p"][hold]])
            qh = np.clip(data["q"][hold], 1e-4, 1 - 1e-4)
            mh = data["match"][hold]
            boot = Boot(mh)
            w0 = fit_logistic(design(None, lpd, None), yd, 1e-3)
            p0 = predict(design(None, lph, None), w0)
            b0, bq = brier(p0, yh), brier(qh, yh)
            braw = brier(np.clip(data["p"][hold], 1e-4, 1 - 1e-4), yh)
            gap0 = boot.stats(b0 - bq)
            info.update(
                {
                    "tested": True,
                    "hit_hold": float(yh.mean()),
                    "brier_raw": float(braw.mean()),
                    "brier_base": float(b0.mean()),
                    "brier_price": float(bq.mean()),
                    "gap_raw_price": boot.stats(braw - bq)[:3],
                    "gap_base_price": gap0[:3],
                }
            )
            cols: list[np.ndarray] = []
            cols_h: list[np.ndarray] = []
            for i in applicable(sport, kind):
                fd = xa[dev, i]
                fh = xa[hold, i]
                nn = ~np.isnan(fd)
                cell: dict[str, Any] = {
                    "sport": sport,
                    "family": fam,
                    "kind": kind,
                    "feature": FEATURES[i].fid,
                    "cover_dev": float(nn.mean()),
                    "cover_hold": float((~np.isnan(fh)).mean()),
                    "price": FEATURES[i].price,
                }
                n_m_ok = len(np.unique(data["match"][dev][nn]))
                sd = float(np.nanstd(fd)) if nn.sum() > 1 else 0.0
                if (
                    nn.sum() < 50
                    or n_m_ok < 30
                    or sd <= 1e-9
                    or (~np.isnan(fh)).sum() < 30
                ):
                    cell["tested"] = False
                    results.append(cell)
                    continue
                st = (float(np.nanmean(fd)), sd, bool((~nn).any()))
                xd_ = design(fd, lpd, st)
                xh_ = design(fh, lph, st)
                w1 = fit_logistic(xd_, yd, 1e-3)
                p1 = predict(xh_, w1)
                b1 = brier(p1, yh)
                db = boot.stats(b1 - b0)
                dl = boot.stats(logloss(p1, yh) - logloss(p0, yh))
                g1 = boot.stats(b1 - bq)
                cell.update(
                    {
                        "tested": True,
                        "coef": float(w1[2]),
                        "d_brier": db[0],
                        "d_brier_ci": [db[1], db[2]],
                        "p_one_sided": db[3],
                        "d_logloss": dl[0],
                        "d_logloss_ci": [dl[1], dl[2]],
                        "gap_after": [g1[0], g1[1], g1[2]],
                        "gap_before": list(gap0[:3]),
                    }
                )
                results.append(cell)
                if not FEATURES[i].price:
                    z = np.where(
                        np.isnan(xa[sel, i]),
                        0.0,
                        np.clip((xa[sel, i] - st[0]) / st[1], -5, 5),
                    )
                    cols.append(z[dev[sel]])
                    cols_h.append(z[hold[sel]])
                    if st[2]:
                        cols.append(np.isnan(fd).astype(float))
                        cols_h.append(np.isnan(fh).astype(float))
            if cols:
                xd_all = np.column_stack([np.ones_like(lpd), lpd, *cols])
                xh_all = np.column_stack([np.ones_like(lph), lph, *cols_h])
                pa, lam = everything(xd_all, yd, data["day"][dev], xh_all)
                ba = brier(pa, yh)
                info["everything"] = {
                    "columns": len(cols),
                    "lambda": lam,
                    "d_brier": boot.stats(ba - b0)[:3],
                    "gap_after": boot.stats(ba - bq)[:3],
                }
                pooled_h["m"].append(mh)
                pooled_h["b0"].append(b0)
                pooled_h["ba"].append(ba)
                pooled_h["bq"].append(bq)
            families.append(info)
            print(
                f"{sport} {fam}: hold {n_hold_m} matches", file=sys.stderr, flush=True
            )
        if pooled_h["m"]:
            m = np.concatenate(pooled_h["m"])
            b0, ba, bq = (np.concatenate(pooled_h[k]) for k in ("b0", "ba", "bq"))
            bt = Boot(m)
            upper[sport] = {
                "rows": int(len(m)),
                "matches": int(len(np.unique(m))),
                "brier_base": float(b0.mean()),
                "brier_all": float(ba.mean()),
                "brier_price": float(bq.mean()),
                "d_all_base": bt.stats(ba - b0)[:3],
                "gap_base_price": bt.stats(b0 - bq)[:3],
                "gap_all_price": bt.stats(ba - bq)[:3],
            }
    tested = [r for r in results if r.get("tested")]
    stat_cells = [r for r in tested if not r["price"]]
    mask = bh([r["p_one_sided"] for r in stat_cells], BH_Q)
    for r, mk in zip(stat_cells, mask, strict=True):
        r["bh_pass"] = bool(mk)
    ctrl = [r for r in tested if r["price"]]
    cmask = bh([r["p_one_sided"] for r in ctrl], BH_Q)
    for r, mk in zip(ctrl, cmask, strict=True):
        r["bh_pass_control"] = bool(mk)
    summary = {
        "holdout_from": DEV_CHECK_SPLIT if args.dev_check else HOLDOUT_FROM,
        "dev_check": bool(args.dev_check),
        "window": [FROM_DAY, TO_DAY],
        "cells_considered": len(results),
        "cells_tested": len(tested),
        "stat_cells_tested": len(stat_cells),
        "bh_q": BH_Q,
        "bh_survivors": int(mask.sum()),
        "unadjusted_p05": int(sum(1 for r in stat_cells if r["p_one_sided"] < 0.05)),
        "expected_p05_under_null": 0.05 * len(stat_cells),
        "control_cells": len(ctrl),
        "control_bh": int(cmask.sum()),
        "s10_fit": s10_note,
    }
    doc = {"summary": summary, "families": families, "cells": results, "upper": upper}
    name = "results_dev_check.json" if args.dev_check else "results.json"
    (out / name).write_text(
        json.dumps(doc, indent=1, default=float), encoding="utf-8"
    )
    print(json.dumps(summary, indent=1))
    return 0


def cmd_list(_: argparse.Namespace) -> int:
    print("| id | sporty | rodzaje rynków | definicja | uwaga |")
    print("|---|---|---|---|---|")
    short = {F: "P", H: "H", B: "K", V: "S", C: "CS2"}
    for f in FEATURES:
        sp = ",".join(short[s] for s in SPORTS if s in f.sports)
        kinds = ",".join(
            k for k in ("total", "side", "margin", "player", "other") if k in f.kinds
        )
        note = "; ".join(
            x
            for x in (
                "cena (kontrola, poza BH i poza modelem 'wszystko')" if f.price else "",
                "NIE MIERZONE" if not f.measured else "",
                f.note,
            )
            if x
        )
        print(f"| {f.fid} | {sp} | {kinds} | {f.text} | {note} |")
    print(
        f"\n{len(FEATURES)} cech, w tym {sum(1 for f in FEATURES if f.price)} cenowych "
        f"(kontrole), {sum(1 for f in FEATURES if not f.measured)} niemierzonych."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else "")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    b = sub.add_parser("build")
    b.add_argument("--sports", default=",".join(SPORTS))
    b.add_argument("--db-path", default="data/sofa.db")
    b.add_argument("--rows-dir", default=DEFAULT_ROWS_DIR)
    b.add_argument("--out", default=DEFAULT_OUT)
    e = sub.add_parser("evaluate")
    e.add_argument("--out", default=DEFAULT_OUT)
    e.add_argument("--dev-check", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "list":
        return cmd_list(args)
    if args.cmd == "build":
        return cmd_build(args)
    return cmd_evaluate(args)


if __name__ == "__main__":
    raise SystemExit(main())
