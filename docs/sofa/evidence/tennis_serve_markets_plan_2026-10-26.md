# Asy i podwójne błędy: plan dalszych prac (2026-10-26)

Operator chce włączyć rynki asów / podwójnych błędów / punktów serwisowych.
Pomiar: `tennis_serve_markets_2026-10-26.md` (z dodatkiem). Stan: **wszystkie
rodziny wyłączone**, nic nie zainstalowano.

## Znaleziska (20 367 linii Superbetu, 312 meczów, 09-18..10-25)

1. Obecny model (p z SHEET) przy p >= 0.70: 2 778 nóg / 307 meczów, deklarowane
   0.781, trafione 0.548, 1/kurs 0.608, ROI -10.1% (odtworzone lokalnie).
   Luka: asy -25.4 pp, punkty serwisowe -26.0 pp, podwójne błędy -16.9 pp.
2. Brier walk-forward (7 849 linii / 258 meczów): model - cena +0.0302
   [+0.0205, +0.0401]; model - stała +0.0207 [+0.0116, +0.0304]. Model nic nie
   dodaje do ceny.
3. Krzywa dopasowana na liniach rynkowych nie dochodzi do 0.70 w żadnym kubełku
   (max 0.55; `double_faults_for` 0.669 na 154 wierszach). Nogi
   cena+model przechodzące bramki: 776 nóg, ROI +3.3% [-1.8, +8.4] - to
   krótkie ceny po cenie, pewność = cena.
4. Rynek Superbetu jest skalibrowany względem NASZYCH ocen dla asów i punktów
   serwisowych (realizacja OVER - nv: asy +2.3 / +3.2 pp, punkty serwisowe
   -0.2 / -0.8 pp). Model: punkty serwisowe OVER zawyżone o ok. 5 pp, podwójne
   błędy o 7 pp (dla zawodnika) i 18 pp (łącznie) - to wada środka modelu.
5. Podwójne błędy: linia łącznie 5.79 vs wynik 4.97 (mediana 4), OVER 32.5%
   (305 meczów), równomiernie po koszykach linii; rozjazd malał w czasie
   (-1.27 -> -0.60). UNDER +6.8% [+0.9, +13.5] (3 215 nóg), ale znalezione po
   przejrzeniu, 36 komórek, druga połowa +1.6% [-6.6, +9.5], pewność ok. 0.59.
6. Nasze liczenie nie zaniża podwójnych błędów: statystyki Sofascore 4.87 vs
   point-by-point 4.45 (173 mecze). Źródło rozliczenia Superbetu nieznane
   (tylko Sofascore + Superbet).
7. Wcześniej (10-17 / 10-19): poprawka na returnera zero (+0.006 [-0.025,
   +0.035]); długość meczu to największy brakujący czynnik (wyrocznia), ale
   ekspozycja z ratingu prawie jej nie przewiduje; asy w setach z efektem
   turnieju przechodzą historię, na liniach Superbetu -11.3 pp.

Nie zmierzone: prawdziwy CONFIDENCE (użyto surowego `p_central` i krzywych z
historii - granica optymistyczna); historia bez znaczników czasu; kobiety /
puchary / nawierzchnie; rynki na set i `serve_points` w replayu.

## Plan (kolejność)

A. **Test w przód podwójnych błędów UNDER** (pre-rejestracja): od 2026-10-27,
   `double_faults_total` + `double_faults_for`, UNDER, wszystkie linie, ROI po
   kursie Superbetu, bootstrap po meczach. Reguła decyzji zamrożona teraz:
   >= 400 nóg / >= 120 meczów i dolna granica ROI > 0 -> wtedy dopiero
   dyskusja o regule ceny (nie o krzywej: pewność ~0.59 < 0.70). Proponowane
   id: `T-TENNIS-DF-UNDER-FORWARD`. Dane: `sofa_settled_row`, skrypt do
   napisania na bazie `df1.py` (scratchpad sesji).
B. **Model od dołu** (czeka na go operatora): P(wygrany punkt przy własnym /
   cudzym serwisie) -> rozkład gemów / setów z modelu zwycięzcy -> punkty
   serwisowe; as i podwójny błąd jako ułamek punktów serwisowych serwującego
   (z ewentualnym returnerem i turniejem). Walk-forward na historii i na
   prawdziwych liniach Superbetu, przez prawdziwy SHEET / CONFIDENCE. Cel
   najpierw: czy poprawia środek punktów serwisowych i podwójnych błędów
   (Brier vs cena i vs obecny model). Próg: przedział wykluczający zero.
C. Dopiero po A / B: ewentualny przełącznik w `bet.sofa.epochs` (domyślnie
   następny dzień 00:00Z), krzywe `tennis_serve` na liniach rynkowych,
   refit z flagami - **wymaga go operatora**; nigdy w dzień już zbudowany.
D. Zbadać tournament / tier / porę dla rozjazdu podwójnych błędów, jeśli A
   pokaże sygnał (czy to cecha konkretnych linii Superbetu).

Do nie robienia bez nowych dowodów: ponowne flagi `--tennis-serve-markets` /
`--tennis-aces-opponent` w refitcie; wydruk serve legs na samej krzywej z
historii.
