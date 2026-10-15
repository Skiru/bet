# Krzywe nowych rynków - instalacja i E2E, noc 2026-10-14/15

Plan: `PLAN_KRZYWE_NOWE_RYNKI_2026-10-14.md`, sekcja „Plan nocy (aktualny)”.
Decyzje operatora: bramka jednostronna (18:55Z), instalacja wszystkiego, co
wypisze instalator, także CS2 rundy serii mimo ostrzeżenia z linii
Superbetu (~19:20Z). Dowody bramek:
`docs/sofa/evidence/new_market_curves_2026-10-15.md`,
`football_1x2_dnb_phase_2026-10-15.md`, `cs2_series_rounds_2026-10-15.md`.

## N1 - stan przed instalacją

00:10Z: wszystkie wyniki agentów na `main` (HEAD `fecbd266`, drzewo czyste
poza dokumentami tej nocy); bramki z 2026-10-14 ~20:50Z na tym samym HEAD:
pytest 4 757 passed / 2 skipped, ruff, mypy strict, rejestr 0 uwag.
`install_new_market_curves.py --dry-run`: **29 kluczy ADD**, jak oczekiwano.

## N2 - instalacja

- **00:10Z, pierwsza próba `--confirm`: testy nie przeszły (8), instalator
  przywrócił config z kopii** (md5 trzech plików jak przed). Wszystkie 8 to
  testy-strażnicy napisane przed instalacją, które sprawdzały, że
  zainstalowany config **nie ma** krzywych nowych rynków
  (`test_installed_curves_and_evidence_give_*_nothing`,
  `test_confidence_refuses_the_leg_no_line_evidence` x3,
  `test_nothing_prints_today_every_derived_key_is_no_line_evidence`) - stan,
  który instalacja z założenia zmienia. Żaden test logiki nie padł.
- Poprawka: strażnicy opisują stan po instalacji - klucz z listy instalatora
  czyta własną krzywą (`market:<klucz>`, klasa `women` / `tennis_women`),
  klucz odrzucony przez bramkę dalej jej nie ma; testy reguły „brak krzywej i
  linii = NO_LINE_EVIDENCE” czytają kopię kalibracji bez danego rynku
  (`tests/sofa/calibration_without.py`, `--calibration`), więc reguła jest
  dalej sprawdzana. Odczyt line evidence wyjęty ze strażników (dzienny
  stan, poranne odświeżenie go zmienia; strażnik sportów pomija klucz, który
  ma już własne linie). Pełny pytest z `SOFA_CONFIG_DIR` = config po
  instalacji: 4 757 passed.
- **00:17:09Z: `--confirm` - zainstalowane, testy instalatora przeszły**
  (4 757 passed / 2 skipped). Kopia: `config/backup_2026-10-15_new_markets/`.
  md5 nowych plików = md5 kopii configu użytej w E2E (N4), czyli E2E
  sprawdził dokładnie to, co jest zainstalowane:
  `sofa_confidence_calibration.json` 560c3916…,
  `sofa_sport_confidence_calibration.json` d7423178…,
  `.next.json` eeda3142….
- Bramki po instalacji: pytest 4 757 passed, ruff (src, scripts i zmienione
  testy), mypy strict (261 plików), rejestr 0 uwag.

## N3 - epoka ledgera

Grupa „od 10-15” już istniała (`audit_ledger.EPOCH_GROUPS`, przełączniki
planu tożsamości od 10-14 11:30Z): 10-15 jest pierwszym dniem budowanym na
nowych krzywych, a 10-14 zostaje „10-14 mieszany”. Instalacja przed budową
10-15 nie tworzy dnia mieszanego, więc nowej grupy nie trzeba; zmieniony
tylko komentarz w `audit_ledger.py`.

## N4 - E2E na kopii 10-14

Kopia artefaktów 10-14 (dzień, migawki SHADOW / CS2) w katalogu scratch,
zegar `SOFA_NOW` = zegar budowy 15:13:51Z, CONFIDENCE + SPORT_CONFIDENCE +
COUPON_ASSEMBLY dwa razy na tych samych wejściach: z konfiguracją
zainstalowaną przed nocą (kontrola) i z kopią konfiguracji, do której
instalator wgrał 29 kluczy (`--config-dir` scratch). Przełączniki
1X2/DNB i CS2 rund serii działają od 10-15, więc tu ich nie widać (osobno
niżej).

Wynik: **110 nowych nóg, 0 nóg znikło, pewność 1 211 wspólnych nóg bez
zmian** (różnica 0 na każdej).

| sport | rynek | nogi | mecze | kurs (mediana, zakres) | pewność (mediana) | pewność < 1/kurs | śr. pewność - 1/kurs |
|---|---|---|---|---|---|---|---|
| piłka | `double_chance` OVER | 78 | 68 | 1,23 (1,10-1,32) | 0,774 | 71 | -3,5 pp |
| piłka | `red_cards_total` UNDER | 12 | 12 | 1,18 (1,09-1,28) | 0,823 | 12 | -2,9 pp |
| piłka | `penalties_total` UNDER | 6 | 6 | 1,21 (1,17-1,27) | 0,808 | 6 | -3,2 pp |
| piłka | `first_goal` OVER (jednostronny singiel) | 1 | 1 | 1,29 | 0,718 | 1 | -5,7 pp |
| tenis | `set1_won_for` | 2 | 2 | 1,19 (1,18-1,20) | 0,787 | 2 | -5,3 pp |
| tenis | `set2_won_for` | 2 | 2 | 1,15 / 1,29 | 0,80 | 1 | -2,0 pp |
| hokej | `period_double_chance` 1X | 6 | 6 | 1,25 (1,12-1,27) | 0,742 | 6 | -6,2 pp |
| hokej | `double_chance` 1X | 3 | 3 | 1,22 (1,20-1,24) | 0,760 | 3 | -6,0 pp |

- **102 ze 110 nowych nóg ma pewność poniżej ceny Superbetu (1/kurs) - na
  minusie według naszych własnych liczb**; przechodzą, bo bramka to
  pewność x kurs >= 0,90, nie >= 1. To ten sam wzór co reszta kuponu, nie
  przewaga. Czy nowe rynki biją kurs, nie jest zmierzone (brak
  rozliczonych linii).
- `first_goal` drukuje się jako singiel jednostronny (`overround` brak,
  `calibrated_on` = `market:first_goal|OVER`, n krzywej 4 487) - reguła
  `confidence.one_sided_single` działa.
- Strzały lewą / prawą nogą: 0 nóg. 29 wierszy OVER z p >= 0,75 i ceną:
  12 x < 0,90, 6 ODDS_TOO_LOW, 4 LINE_BEYOND_SAMPLE, 4
  THIN_SAMPLE_FOR_BUILDER, 3 poniżej progu - zwykłe bramki, nie błąd.
- Tenis `set_score`, siatkówka (`team_wins_set`, `team_sets_exact`),
  koszykówka `double_chance`: 0 nóg w tym dniu (siatkówka 0 także w
  kontroli - patrz niżej).
- Kontrola odtwarza prawdziwe `08_confidence_sports.json` dla hokeja (154),
  koszykówki (8) i CS2 (6); siatkówka daje 0 zamiast 10 - prognozy sportów
  czytają `data/sofa.db` w stanie z wieczoru (historia siatkówki zmieniła
  się od budowy), więc porównanie robione jest tylko kontrola vs nowe
  krzywe na tych samych wejściach.
- md5 prawdziwych plików 10-14 (`08_confidence*.json`, `11_coupon.json`,
  `12_printed.json`, PDF) - bez zmian przed i po.

### N4b - próbna budowa 10-15 w katalogu scratch (00:21-00:37Z)

Pełny łańcuch na prawdziwych danych 10-15 (`SOFA_RUNS_DIR` scratch, zegar
na żywo, po instalacji; BOARD → ... → COUPON, SHADOW, CS2, SPORT_IDENTITY,
`rebuild_day.py` do PDF), żeby zobaczyć na żywej ofercie to, czego kopia
10-14 nie mogła: 1X2 / DNB i CS2 rundy serii (przełączniki od 10-15 00:00Z).
Wszystkie etapy OK / PARTIAL (normalny kształt), most bez odmowy;
prawdziwy katalog `runs/sofa/2026-10-15/` nietknięty (tylko pętle sportów).

- SHEET: 58 811 wierszy; nowe rynki z ceną: `double_chance` 352,
  `result_1x2` 238, `draw_no_bet` 236, `first_goal` 244, `red_cards_total`
  102, `penalties_total` 104, `set1/set2_won_for` 346 / 342, `set_score` 619,
  strzały zawodnika według miejsca / części ciała 4 685.
- Kupon (o 00:37Z, dzień jeszcze cały przed nami): 1 609 singli, sporty:
  hokej 176, kosz 2, siatkówka 0, CS2 19. **Nowe rynki: 157 nóg, z czego 133
  z pewnością poniżej 1/kurs (na minusie według naszych liczb):**

| rynek | nogi | kurs (mediana) | pewność (mediana) | < 1/kurs |
|---|---|---|---|---|
| piłka `double_chance` OVER | 84 (67 meczów) | 1,24 | 0,774 | 73 |
| piłka `red_cards_total` UNDER | 34 | 1,19 | 0,844 | 26 |
| piłka `draw_no_bet` OVER / UNDER | 11 / 1 | 1,20 / 1,18 | 0,834 / 0,791 | 6 / 1 |
| piłka `penalties_total` UNDER | 6 | 1,27 | 0,753 | 6 |
| piłka `first_goal` OVER (jednostronny) | 1 | 1,29 | 0,718 | 1 |
| tenis `set1_won_for` / `set2_won_for` | 7 / 5 | 1,14-1,23 | 0,76-0,84 | 12 |
| tenis `set_score` OVER | 3 | 1,23 | 0,755 | 3 |
| hokej `period_double_chance` / `double_chance` 1X | 3 / 2 | 1,21-1,23 | 0,76 | 5 |

- `result_1x2`: 0 nóg (bez krzywej, NO_LINE_EVIDENCE) - zgodnie z bramką.
- DNB: pasmo cenowe (`price_band_cap`, pula sportu) obniża 8 z 12 nóg;
  jedna noga (Palmeiras U20 - Botafogo U20 @1,20) ma pewność 0,939, +10,6 pp
  nad ceną - flaga `price_gap`.
- **CS2 rundy serii: 0 nóg.** 76 stron przeczytanych (rounds_handicap 28,
  rounds_total 28, team_rounds 20); najwyższe p modelu 0,65, więc wszystkie
  poniżej progu 0,70; strony UNDER bez krzywej są NO_LINE_EVIDENCE (24).
- Strzały według miejsca / części ciała: 0 nóg (jak na 10-14 - zwykłe
  bramki).

Prawdziwa budowa 10-15 jest rano (z rozliczeniem 10-14 i odświeżonym line
evidence) - liczby się zmienią.

## N5 - dokumentacja

CLAUDE.md: akapit „New-market curves installed 2026-10-15 00:17Z” (lista
kluczy, bramka jednostronna, wynik E2E), zdania „no curve /
NO_LINE_EVIDENCE” przy przełącznikach z 10-14 poprawione, CS2 rundy serii i
DNB „installed”, Comparability: „od 10-15” zaczyna też nowe krzywe, kopia
na liście backupów. `audit_ledger.py`: komentarz przy „od 10-15”.

## Rano 2026-10-15 - rozliczenie 10-14 i nogi z E2E

Rozliczenie 10-14 (SETTLE 04:38Z; SHADOW_SETTLE pętli 05:15Z padł na
odmowie mostu - 403 - i został powtórzony ręcznie 05:22Z: OK; CS2_SETTLE
05:00Z OK; przegląd CS2 10-11 / 10-12 powtórzony 05:26Z po błędach mostu:
OK): **nowe rynki rozliczają się** - piłka / tenis w `07_settled.json`:
`double_chance` 308 (WIN 204 = 2 z 3 wyborów, jak musi), `first_goal` 197,
`red_cards_total` 47, `penalties_total` 46, `set1_won_for` / `set2_won_for`
94 / 94 (po połowie), `set_score` 167, strzały według miejsca / części ciała
2 106 (reszta to starterzy, którzy nie wyszli - `PLAYER_NOT_STARTED`); w
`07_settle_skips.json` żadnej przyczyny rynkowej dla nowych rynków. Hokej:
`double_chance` 126, `period_double_chance` 129 stron (2:1, jak musi);
siatkówka: `team_wins_set` 20, `team_sets_exact` 32, `sets_count` 21.

**Usterka (otwarta): koszykarska podwójna szansa nie jest czytana.**
Superbet wystawia ją tylko jako „1X” / „X2” (bez „12”; sprawdzone na żywo
2026-10-15: 5 z 30 meczów, także „2. połowa - podwójna szansa”), a
`shadow.parse_event` przyjmuje grupę podwójnej szansy tylko jako pełną
{1X, X2, 12} (`cs2.complete_group`, `DOUBLE_CHANCE_SET`) - więc cała grupa
odpada po cichu: 0 linii w 433 migawkach 10-14 / 10-15 po przełączniku,
mimo włączonego `SPORT_DERIVED_MARKETS` i zainstalowanej krzywej
`basketball:double_chance|TEAM`. Para 1X / X2 to nie rozkład (suma = 1 +
P(remis)), więc marży nie da się z niej odczytać bez 1X2 meczu - naprawa to
zmiana reguły marży (jak w piłce: UNDER = pominięty wynik „Mecz”), nie
poprawka na szybko przed budową; do zrobienia z testem i pomiarem. Do tego
czasu 0 nóg tego rynku. Hokej dostaje pełną grupę i działa.

**Nogi E2E (kopia 10-14, nowe krzywe) rozliczone - fakt o dniu, nie wkład
do decyzji:** 110 nóg, 87 wygranych, 23 przegrane, **-4,00 j.** (stawka 1).

| grupa | nogi | wygrane | przegrane | j. | suma pewności | suma 1/kurs |
|---|---|---|---|---|---|---|
| piłka + tenis | 101 | 80 | 21 | -3,62 | 79,7 | 83,2 |
| hokej | 9 | 7 | 2 | -0,38 | 6,8 | 7,35 |

W tym `double_chance` 61 / 17 (-3,47 j.), `red_cards_total` UNDER 9 / 3
(-1,34), `penalties_total` UNDER 5 / 1 (+0,08), sety 4 / 0 (+0,82),
`first_goal` 1 / 0 (+0,29). Jeden dzień: zgodne z pewnością (80 przy 79,7),
poniżej ceny (83,2) - tyle, ile mówiła bramka x >= 0,90 przy pewności poniżej
1/kurs. Kupon 10-14 (ledger, dzień mieszany): 1 177 rozliczonych, 912 / 265,
-67,43 j., ROI -5,7%; zdjęte przez odczyty 57, -10,4%.

## Budowa 2026-10-15 (pierwszy dzień na nowych krzywych)

`run_pipeline.py --date 2026-10-15` (run `sofa_20261015_0621`, 06:21-06:33Z),
`rebuild_day.py`, odczyty analityków (piłka, tenis, hokej, koszykówka, CS2,
pierwsza runda + 6 rund C3, bo każde zdjęcie wpuszcza kolejny mecz do 30
najlepszych), weryfikator (08:01Z), ostatnia przebudowa 08:12-08:15Z:
`audit_variants` C3 0 uwag. Most w tym czasie kilka razy 403 / 504
(operator odświeżał); FIXTURE_CHECK czytał wtedy cache do 60 min.

- **Kupon:** 1 467 singli (10-14: 1 221), z czego 65 zablokowanych (wydrukowane
  o 06:34Z przed swoim startem); 1 builder (B1); 57 nóg zdjętych odczytami.
  Sporty: piłka 888, tenis 360, hokej 191, CS2 24, kosz 3, siatkówka 1.
- **Odczyty:** 587 (528 KEEP / 59 WATCH / 0 NO_BET), 104 weta CONTEXT -
  wszystkie w meczach pucharowych / AFC, w których rating stawia drużynę z
  ligi słabszej wyżej (Lech - Leverkusen, Celje - Omonia, CSKA Sofia -
  Monaco, Egnatia - Midtjylland, Salzburg - Milan na sumach i in.;
  powtarzający się wzorzec Aktobe / Austria Wien - kandydat na pomiar siły
  domen w pucharach, nie poprawka).
- **Nowe rynki na kuponie: 158 nóg, 124 z pewnością poniżej 1/kurs (na
  minusie według naszych liczb):** `double_chance` 95 (kurs 1,24, pewność
  0,782), `red_cards_total` UNDER 28, `draw_no_bet` 12, `penalties_total`
  UNDER 6, hokej `period_double_chance` 5 / `double_chance` 3, tenis
  `set1_won_for` 5 / `set2_won_for` 2 / `set_score` 1, `first_goal` 1
  (singiel jednostronny). Odczyty zdjęły 8 nóg nowych rynków (DC 5, czerwone
  2, DNB 1). **CS2 rundy serii: 0 nóg** (najwyższe p modelu na tablicy < 0,70).
  `result_1x2`, strzały według miejsca / części ciała, siatkówka: 0.
- **Weryfikator:** brak defektu; nowe rynki sprawdzone na surowym ładunku
  Superbetu (160 nóg: wybór, strona, kolejność 1/2, DNB „1” = gospodarz,
  ceny DC zgodne z 1X2). Uwagi (nie defekty): krzywa `double_chance|OVER`
  piłki łączy 1X / X2 / 12 (68 z 97 nóg to „12”; zmierzone na holdoucie:
  log-loss -0,0088 [-0,0103; -0,0072] względem bazy, 0,806 deklarowane /
  0,798 zrealizowane); `first_goal` idzie regułą singla jednostronnego, choć
  jego marża 3-drogowa jest mierzalna (6,6%); notki arkusza DC / kartek /
  karnych mówią jeszcze „no curve installed” (tekst, nie odczyt). 5 WATCH
  weryfikatora: hokejowe punkty w przewagach UNDER na 5-7 meczach.
- **Pętla kursów zamknięcia 10-15 nie działała** (weryfikator, `day_status`
  BROKEN) - uruchomiona 08:01Z.

**Usterki otwarte (do naprawy z testem, osobno):**
1. Koszykarska podwójna szansa nigdy nie czytana (Superbet tylko 1X / X2).
2. `contracts.READ_SIDES` nie zna stron 1X / X2 / 12 - odczyt nogi DC sportu
   nie może nazwać strony (dziś `direction: null`, drukowana była tylko 1X).
3. Notki arkusza nowych rynków („no curve installed”) nieaktualne.
4. Snippet `OfferFetcher` w protokole weryfikatora bez flag nowych rynków.
