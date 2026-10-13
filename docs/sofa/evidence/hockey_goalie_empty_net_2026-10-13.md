# B8: hokej - strzały x skuteczność (save% drużyny) i pusta bramka (audyt 2026-10-13)

Pozycja B8 listy napraw `docs/sofa/history/AUDYT_RYNKOW_KONTEKST_2026-10-13.md`
(P2/M po V3-6; skala danych po V3-3). Przełączniki w `bet.sofa.epochs`
(domyślnie `None`): `HK_SHOTS_FROM_UTC` (strzały x skuteczność) i
`HK_EMPTY_NET_FROM_UTC` (pusta bramka dopasowana na historii). Skrypt pomiaru
(tylko odczyt): `scripts/sofa/measure_hockey_goalie_empty_net.py`.

## Diagnoza (zweryfikowana w kodzie, 2026-10-13)

- `score_model.parse_event` (`src/bet/sofa/score_model.py:219-269`) czyta z
  listingu tylko gole po tercjach; `_metrics` (`:306-310`) dla hokeja to jedno
  `hk_reg_for`; `ScoreModel.expected` (`:552-593`) = stawka ligi x atak x
  obrona na golach. `load_box_scores` / `attach_box` (`:177-209`) są tylko dla
  koszykówki (`sport_confidence.parse_history`, `sport.key == "basketball"`).
  W modelu wyniku hokeja nie ma strzałów, bramkarza (save%) ani przewag.
- Pusta bramka **jest** w symulacji, ale jako stała wybrana z siatki, nie
  dopasowana: `SimParams.hk_late_lead` 0,2 / `hk_late_trail` 0,05
  (`:349-350`), w `_hockey` (`:662-668`) ta sama dla prowadzenia 1 i 2 goli.

## Dane (kopia `data/refit_2026-10-13/sofa_replay.db`, tylko odczyt)

Z 29 516 meczów historii hokeja 22 368 ma wiersz w `sofa_event_stats`:

- `Shots` (strzały celne, cały mecz): **6 798** meczów - NHL 2 798, Liiga 1 078,
  Extraliga 836, SHL 804, Tipsport Liga 752, CHL 202, KHL 140, reszta
  pojedynczo. Inne ligi praktycznie bez strzałów.
- `saves`: 3 835 (bez NHL); save% drużyny i tak wynika z goli i strzałów
  rywala, więc `saves` nie jest potrzebne.
- `PowerPlayPercentage`: 3 154 (NHL 2 789).
- `emptyNetGoals`: **1 021, tylko NHL**, zapisywane tylko gdy niezerowe (brak
  par 0/0), czyli mecz NHL ze statystykami bez klucza = 0 goli do pustej.
  `incidents_json` hokeja puste - **nie ma czasu goli**.
- `lineups_json`: 7 751 meczów; lista bramkarzy pobrana po meczu (wszyscy
  ubrani bramkarze, `confirmed`). **Bramkarz startowy przed meczem nie jest
  znany** z niczego, co mamy (`probe_lineup_availability.py` nie uruchomiony,
  zakaz mostka w tej sesji), więc save% jest save% **drużyny** (mieszanka jej
  bramkarzy, jak grała dotąd) - nie bramkarza startowego.
- Pokrycie po miesiącach: 2024-10..2025-04 i 2025-09..2026-04 ok. 55-75%
  meczów z jakimkolwiek wierszem statystyk; **2026-10: 0** w kopii (dociąganie
  statystyk hokeja z ostatnich 60 dni idzie teraz do `data/sofa.db`, nie do
  kopii; poranny refresh pobiera je od commita a0d2aa7b).

Przewag (power play) nie modeluję: strzały je zawierają, a rozbicie na grę
5 na 5 i przewagi wymagałoby osobnego modelu kar (3,1 tys. meczów, prawie
same NHL) - poza zakresem tego testu, zapisane jako otwarte.

## Rejestracja (zapisana 2026-10-13 PRZED uruchomieniem pomiaru)

### Wariant S - strzały x skuteczność (save% drużyny)

- Dwie nowe metryki w tym samym `RatingBook` co gole: `hk_shots` (strzały
  celne strony; atak = własne strzały, obrona = strzały dopuszczane) i
  `hk_conv` (gole regulaminu / strzały; atak = skuteczność strony, obrona =
  1 - save% drużyny rywala). Strzały meczu z dogrywką skalowane do regulaminu
  x 60/65 (jedna 5-minutowa dogrywka zakładana). Mecz z którąkolwiek stroną
  poza 5..80 strzałów albo bez `Shots`: brak strzałów.
- Oczekiwane gole regulaminu strony = E[strzały strony] x E[skuteczność
  strony] (ta sama mechanika: stawka ligi ścisła, link / siła ligi,
  `MIN_TEAM_MATCHES`), podział na tercje tymi samymi udziałami.
- **SB (mieszanka):** sqrt(centrum goli x centrum strzałów) na stronę.
- Powrót do centrum goli (bez zmian), gdy: któraś strona ma < 5 meczów ze
  strzałami, któraś nie grała meczu ze strzałami w ostatnich 60 dniach
  (wybrane, nie dopasowane - jak `PACE_FRESH_S` B7), rozgrywki nie mają
  stawki strzałów (< 30 meczów), albo para jest UNLINKED na metrykach
  strzałów.
- α: `hk_shots` z {0,02; 0,05; 0,10}, `hk_conv` z {0,01; 0,02; 0,05}; wybrane
  na oknie strojenia **2024-10-01..2025-06-01** kwadratem błędu goli
  regulaminu strony one step ahead (tylko mecze na ścieżce strzałów); potem
  zamrożone. Ta sama α dla S i SB.

### Wariant E - pusta bramka dopasowana na historii

- Struktura `_hockey` bez zmian poza tym, że prawdopodobieństwa zależą od
  prowadzenia: przy prowadzeniu 1 gola prowadzący dostaje gola do pustej z
  `e1`, przegrywający wyrównuje z `t`; przy prowadzeniu 2 goli prowadzący
  z `e2`, przegrywający zmniejsza na 1 z `t`.
- Dopasowanie momentami na rozkładzie końcowego wyniku (czasu goli nie ma):
  na oknie strojenia **2024-10-01..2025-06-01** (wszystkie ligi, książka
  aktualizowana mecz po meczu) dla każdego meczu rozkład |różnicy| regulaminu
  PRZED końcówką z modelu (Skellam z centrum dzisiejszego modelu, analitycznie)
  - średnie P0..P3 - wobec udziałów historii F0, F2, F3:
  `t = (F0 - P0) / P1`, `e2 = (F3 - P3) / P2`,
  `e1 = (F2 - P2 (1 - e2 - t)) / P1`; każde ucięte do [0; 0,6]. Kontrola
  (raportowana, nie użyta): NHL `emptyNetGoals` - odsetek meczów z golem do
  pustej prowadzącego przy różnicy przed nim 1 / 2.

### Porównanie

Model dzisiejszy: `build_model` hokeja bez zmian (`hk_late_lead` 0,2,
`hk_late_trail` 0,05), reguła stawki ligi ścisła (A2, na żywo od 2026-10-14)
w obu ramionach.

**Test A - historia (główny).** Okno **2025-10-01..2026-06-01**, walk-forward:
model przebudowany co 30 dni, między przebudowami książka aktualizowana mecz
po meczu; co n-ty mecz do 6 000; 1 000 symulacji na mecz i model, to samo
ziarno. Linie standardowe ustalone z góry (nie z ceny): suma regulaminu 4,5 /
5,5 / 6,5; gole strony 1,5 / 2,5 / 3,5; różnica regulaminu (gospodarz -
gość) -2,5 / -1,5 / -0,5 / 0,5 / 1,5 / 2,5; zwycięzca z dogrywką i karnymi.
Metryki: log-loss (główna) i Brier na mecz po liniach rodziny `total`,
`team_total`, `handicap`, `winner`; dodatkowo 1X2 regulaminu (log-loss
trójdrogowy, raportowany). Różnica w parach wariant - dziś, przedział z
bootstrapu po meczach (2 000 losowań, ziarno 0). Raportowane też: podzbiór
meczów na ścieżce strzałów, kalibracja p >= 0,70.

**Test B - linie Superbetu.** Rozliczone linie hokeja 2026-09-29..2026-10-12
(`runs/sofa/shadow/hockey/<d>/settled.json`), model na 00:00Z dnia
(`settled_shadow_rows`), p wyłącznie z modelu (cena nigdy nie wchodzi do p);
rodziny `total`, `team_total`, `handicap`, `winner`; log-loss i Brier w parach,
bootstrap po meczach. Strzałów z października kopia nie ma (patrz Dane).

**Progi (O4/O5, zapisane z góry):**

- S i SB (dwa warianty jednej osi -> Bonferroni, przedział **97,5%**):
  Test A `total` log-loss: górna granica < 0; strażnicy Test A: `winner` i
  `handicap` log-loss - dolna granica <= 0 (nie gorzej). Test B: `total` i
  `winner` log-loss - przedział nie leży w całości powyżej zera. Gdy przejdą
  oba, wybieram ten z niższym log-loss `total` w Teście A.
- E (przedział **95%**): Test A `handicap` log-loss: górna granica < 0;
  strażnicy Test A: `total` i `winner` - dolna granica <= 0. Test B:
  `handicap` i `winner` - przedział nie w całości powyżej zera.
- Wariant spełniający próg -> refit krzywej hokeja na kopii
  (`fit_sport_confidence.py --sport hockey --before 2026-10-13 --dry-run`,
  `data/refit_2026-10-13/hk_b8/`) z flagą wariantu i bazowy bez niej
  (`data/refit_2026-10-13/hk_base/`), compare w parach (log-loss pewności na
  holdoucie historii i na liniach Superbetu, luka nóg >= 0,70). Konfiguracji
  nie zapisuję; decyzję o instalacji opisuję dla sesji nadrzędnej.
  Niespełniony -> przełącznik zostaje `None`, kod jako wyłączona opcja
  (model bajt w bajt identyczny).

## Wynik

Pomiar 2026-10-13, kopia `data/refit_2026-10-13/sofa_replay.db` (tylko odczyt,
`mode=ro`), `scripts/sofa/measure_hockey_goalie_empty_net.py`, wyniki w
formie punkt [dolna, gorna] granica przedzialu; roznica = wariant - dzis,
ujemna = lepiej. Bootstrap po meczach.

**Pokrycie strzalow (bez zmian wzgledem sekcji Dane):** 29 516 meczow historii,
6 755 ze strzalami; 2026-10: 0 (dociaganie idzie do `data/sofa.db`, nie do
kopii), 2026-09: 262 z 1 365. Test A: 5 965 meczow, w tym **1 485** na sciezce
strzalow (25%); Test B: 42 954 linie, p zmienione w 4 794 (S) / 4 752 (SB) /
20 282 (E) wierszach - bez pazdziernika, wiec Test B dla S / SB mierzy glownie
wrzesien.

**Strojenie (okno 2024-10-01..2025-06-01, 5 422 stron):** najlepsza siatka
alfa strzalow 0,05 / skutecznosci 0,01 (MSE goli 2,8658 wobec 2,8783 samego
centrum goli na tych samych stronach). Pusta bramka (moment): e1 0,2189,
e2 0,2514, t 0,1429 (8 902 meczow; przed koncowka model daje P0 0,165 wobec
F0 0,208 historii). Kontrola NHL `emptyNetGoals`: gol do pustej prowadzacego
w 51,6% meczow przy roznicy 1 (473) i 67,1% przy 2 (289).

**Test A (log-loss, wariant - dzis):**

| wariant | total | handicap | winner | team_total |
|---|---|---|---|---|
| S (replace, 97,5%) | +0,00126 [+0,00010, +0,00241] | -0,00171 [-0,00286, -0,00058] | -0,00241 [-0,00395, -0,00083] | -0,00012 [-0,00095, +0,00069] |
| SB (blend, 97,5%) | +0,00025 [-0,00033, +0,00084] | -0,00121 [-0,00184, -0,00058] | -0,00163 [-0,00253, -0,00077] | -0,00043 [-0,00088, +0,00002] |
| E (95%) | +0,00111 [+0,00055, +0,00167] | -0,00037 [-0,00074, +0,000006] | -0,00012 [-0,00068, +0,00044] | +0,00075 [+0,00042, +0,00111] |

Podzbior na sciezce strzalow, `total` log-loss: S +0,00507 [+0,00065, +0,00956],
SB +0,00100 [-0,00135, +0,00334]; `handicap` S -0,00687, SB -0,00487
(oba przedzialy ponizej zera), `winner` S -0,00968, SB -0,00657.

**Test B (linie Superbetu 2026-09-29..2026-10-12, log-loss):** S `total`
+0,00285 [-0,00103, +0,00656], `winner` -0,00065 [-0,00406, +0,00257]; SB `total`
+0,00078 [-0,00114, +0,00265], `winner` -0,00054 [-0,00243, +0,00118]; E
`handicap` -0,00006 [-0,00170, +0,00162], `winner` +0,00004 [-0,00128, +0,00139].
Linie blisko 50/50 (kurs uczciwy 0,45-0,55): `total` S +0,00833
[+0,00234, +0,01498], SB +0,00342 [+0,00062, +0,00653] - gorzej.

## Werdykt wg progow z gory

- **S: NIE.** Glowny prog (Test A `total`, gorna granica < 0) nie spelniony;
  `total` jest GORSZY (dolna granica > 0). Poprawia `handicap` i `winner`,
  ale to nie byl prog glowny.
- **SB: NIE.** `total` gorna granica +0,00084 > 0 (nie lepiej niz dzis).
- **E: NIE.** `handicap` gorna granica +0,000006 > 0 o wlos; ponadto straznik
  `total` zepsuty (dolna granica +0,00055 > 0) i `team_total` gorszy.
- Przelaczniki `HK_SHOTS_FROM_UTC` i `HK_EMPTY_NET_FROM_UTC` zostaja `None`;
  refitu krzywej hokeja z flaga nie robiono (prog niespelniony). Model przy
  wylaczonych przelacznikach jest bajt w bajt dzisiejszy (test).

Zastrzezenia: strzaly dotycza 25% meczow Testu A (glownie NHL, Liiga, SHL,
Extraliga); save% jest druzyny, nie bramkarza startowego (brak danych przed
meczem); przewag nie modelowano; pusta bramka dopasowana z rozkladu koncowej
roznicy bez czasow goli (e1/e2/t nieidentyfikowalne ponad momenty) - stad
mozliwe przeciazenie `t`. Otwarte: powtorzyc S po dociagnieciu strzalow
hokeja 2026-08..10 do historii (refit przy nastepnym replay).

