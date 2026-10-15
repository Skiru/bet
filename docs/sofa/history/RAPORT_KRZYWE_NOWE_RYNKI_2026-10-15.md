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

<!-- N4b -->

## N5 - dokumentacja

CLAUDE.md: akapit „New-market curves installed 2026-10-15 00:17Z” (lista
kluczy, bramka jednostronna, wynik E2E), zdania „no curve /
NO_LINE_EVIDENCE” przy przełącznikach z 10-14 poprawione, CS2 rundy serii i
DNB „installed”, Comparability: „od 10-15” zaczyna też nowe krzywe, kopia
na liście backupów. `audit_ledger.py`: komentarz przy „od 10-15”.
