# Rynki zawodników NBA: dlaczego nie drukują się nogi i cztery pomiary (2026-10-26)

Pytanie operatora (10-26): kupon 10-25 nie miał żadnej nogi zawodnika NBA.
Czy to brak danych, brak trendu / formy w modelu, czy coś innego? Wszystkie
pomiary są offline, na bazie tylko do odczytu (`mode=ro`) albo jej kopii.
**Nic nie zostało zainstalowane ani przełączone.** Skrypty i wyniki:
`docs/sofa/evidence/nba_player_model_2026-10-26/` (skrypty czytały ścieżki ze
scratchpada sesji - to zapis metody, nie gotowe narzędzie).

## 1. Dlaczego 10-25 nie miał nóg zawodników NBA

`08_refusals_sports.json` 10-25, cztery mecze NBA, 1 554 wiersze zawodników:
`NO_LINE_EVIDENCE` 665, `BELOW_FLOOR` 445, `NO_MODEL_P` 444; **żaden** wiersz
nie miał pewności >= 0,70.

- Linie bukmachera leżą przy medianie. W `config/sofa_superbet_line_evidence.json`
  `player_points OVER`: 1 439 linii w kubełku p < 0,60, 131 w 0,60-0,70, 12 w
  0,70-0,75 (UNDER: 1 218 / 297 / 45). Wysoka pewność jest rzadka z konstrukcji.
- Rynki dodane 23.10 (rzuty wolne, z gry, za 2 i 3, straty, faule) mają ok. 25
  meczów historii; kubełek >= 0,70 ma po kilka linii, a bramka chce 50.
- Model jest w górnych kubełkach zbyt pewny (UNDER p 0,7-0,8 realnie 0,61).

## 2. Pomiary (nowe względem zainstalowanego `player_rate_v3`)

Replay historii koszykówki zainstalowanym modelem (770 944 gier zawodników,
44 tys. meczów), bootstrap po meczu >= 2000, `k` i kalibracje dopasowane
**tylko na treningu** (przed 2026-07-01), potem zamrożone.

| próba | wynik |
|---|---|
| **Forma** (średni błąd modelu z 5 poprzednich meczów -> następny mecz) | nachylenie +0,127 [+0,114; +0,139] test, +0,149 od 10-01; NBA 2025-26 +0,150; **NBA 2026-27 (41 meczów) -0,059 [-0,147; +0,041]**. Korekta średniej `k` x błąd: log-loss -0,0017 [-0,0021; -0,0013] (test), NBA 2026-27 +0,0017 (nieistotnie), rozliczone linie Superbetu -0,0004 (nieistotnie). Liczba linii p >= 0,70: 372 -> 337 |
| **Kalibracja kierunkowa** (a + b logit p per rynek i strona; wariant C z kurczeniem >= 0,70) | test -0,00095 [-0,00115; -0,00075]; ECE 0,012 -> 0,006; **NBA 2026-27 gorzej +0,0026 (przedział bez zera, 41 meczów)**; rozliczone linie Superbetu +0,0001 (nieistotnie); UNDER >= 0,7 dalej zbyt pewny (hit 0,60 przy p 0,74) |
| **Dociąganie historii przeniesionym zawodnikom** (< 5 własnych meczów -> do 20 występów tego samego id w innych drużynach) | pokrycie 59% cienkich gier w teście, NBA 2026-27 94% (278 z 296); lepsze od średniej ligi o -0,132 log-loss; gorsze od zwykłego p (0,663 vs 0,645, ECE 0,020 vs 0,009); rozliczone linie Superbetu: log-loss 0,719 (> 0,693), p >= 0,70 trafia 0,593 przy p 0,771 |

**Wniosek:** żadna z trzech korekt nie odblokowuje rynków zawodników; w NBA
2026-27 wszystkie wypadają gorzej lub nieistotnie (41 meczów, początek
sezonu, składy po zmianach). Prawdziwy problem to zbyt pewne p w górnych
kubełkach i znak odwrócony w tym sezonie (OVER -5 pp, UNDER +5 pp), nie
trend.

## 3. Skąd `NO_MODEL_P` w NBA (340 z 1 396 wierszy, 20 z 75 zawodników)

Wszystkie `THIN_SAMPLE` (< `MIN_APPEARANCES` = 5 własnych meczów). Model czyta
tylko listy meczów dwóch grających drużyn (`player_model.load_appearances`),
więc zawodnik, który zmienił klub, ma w próbce nowego klubu 2-3 mecze:
Jaylen Brown (76ers) ma 3 mecze w liście 76ers i 49 w liście Celtics (lista
Celtics: 61 meczów z lineupami). W innych ligach: 1 272 `THIN_SAMPLE`, 146
`NOT_IN_HISTORY`, 26 `NAME_UNCERTAIN` (nie rozebrane).

## 4. Rozliczanie rynków NBA (SHADOW_SETTLE) - co znalazłem i naprawiłem

Cel operatora: rozliczać **wszystkie** rynki NBA, zawodników też, nawet bez
druku (to źródło dowodów linii). Sprawdzenie `settled.json` 10-01..10-25:

- Wszystkie mecze NBA SETTLED, zawodnicy z pudełkiem `ok` (21 258 wierszy
  zawodników rozliczonych w 10-20..10-25, po naprawie bez żadnej zmiany).
- **Naprawione (poprawność, `src/bet/sofa/shadow.py`, test w
  `tests/sofa/test_settle_verification_2026_10_17.py`):**
  1. *Golden State - Memphis 10-24* (16824734, 853 stron): Sofascore podał
     `normaltime` 182 / 189 przy wyniku 108 / 111 i okresach sumujących się do
     wyniku; `build_result` odrzucał całą grę jako DATA_MISMATCH. Teraz
     `normaltime` większy od wyniku końcowego jest błędem payloadu i SHADOW_SETTLE
     (tylko `allow_final_only`) czyta okresy; czytniki historii dalej odmawiają.
     Gra jest DATA_MISMATCH = retryable (7 dni), więc pętla rozliczy ją sama.
  2. *"PJ Washington" / "Washington, P.J"* wobec "P.J. Washington Jr." w pudełku:
     8 linii UNMATCHED (10-23 Indiana - Dallas, 10-25 Dallas - San Antonio).
     `shadow._bare_name` skleja sąsiednie inicjały (obok zdjęcia przyrostka),
     tylko w SHADOW_SETTLE; próbki piłkarskie bez zmian.
- **Nie naprawione (decyzja):** *Milwaukee - Chicago 10-23*: suma punktów
  pudełka 125 przy wyniku 124 -> pudełko odrzucone, 494 linie zawodników
  bez oceny (`player_retry`, Sofascore może poprawić). Odrzucenie jest celowe
  (bramka: pudełko musi się sumować do wyniku). Tolerancja +-1 punktu
  wymaga osobnego pomiaru - otwarte.
- Reszta "UNMATCHED" w NBA to zawodnicy nieobecni w pudełku Sofascore (Irving,
  Leonard, Thompson, Edgecombe, Reuvers...), których Superbet unieważnia - nie
  błąd nazw.
- Już rozliczone mecze SETTLED nie są oceniane ponownie: 8 linii PJ Washington
  z 10-23 / 10-25 zostaje nieocenione, dopóki ktoś nie uruchomi ponownej oceny.

## 5. Do powtórzenia

Powtórzyć te same pomiary (te same skrypty, ten sam podział) gdy NBA 2026-27
ma ok. 200 meczów (około końca listopada 2026), osobno NBA i reszta
koszykówki. Przy pytaniu "czy dołożyć trend / kalibrację / dociąganie" bez
nowych danych: nie. Otwarte osobno: NBA-specyficzny wyraz kalibracji,
tolerancja pudełka +-1, `NOT_IN_HISTORY` poza NBA.
