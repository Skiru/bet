# Głosy kibiców Sofascore obok ceny Superbetu (2026-11-05)

Zlecenie operatora 2026-11-05 („Sprawdzić!”): czy głosy „kto wygra” z Sofascore
(`/event/{id}/votes`, piłka 1/X/2, tenis 1/2) niosą informację ponad cenę
Superbetu bez marży. Pomiar tylko do odczytu: nic, co czyta pipeline, nie
zostało zmienione. Skrypt: `scripts/sofa/measure_fan_votes.py`
(`population` / `fetch` / `report`), test `tests/sofa/test_measure_fan_votes.py`,
dane surowe `data/fan_votes_2026-11-05/` (`population.jsonl`, `votes.jsonl`,
`report.json`).

## 1. Co już było w cache

- Kod i schemat `data/sofa.db`: słowo „vote” nie występuje nigdzie
  (`src/`, `scripts/`, tabele `sofa_event_detail` / `sofa_event_extra`
  — rodzaje tylko `incidents`, `point_by_point`, `shotmap`). Payload `/event`
  (55 200 wierszy) nie zawiera głosów.
- **Głosów przedmeczowych nie ma nigdzie.** Jedyne źródło to zapytanie dziś.

## 2. Czym jest odpowiedź `/votes` dla minionego meczu

Odpowiedź: `{"vote": {"vote1", "voteX", "vote2"}, "bothTeamsToScoreVote",
"firstTeamToScoreVote", "whoShouldHaveWonVote"}` — **bez znacznika czasu**.
Dla meczu zakończonego to **końcowy stan licznika**, łącznie z głosami
oddanymi w trakcie meczu (look-ahead). Wszystkie 10 722 zapytania tego
pomiaru padły po starcie meczu (`asked_after_kickoff: true` w każdym wierszu).
Dowód, że licznik rośnie po starcie: sekcja 7 (te same mecze zapytane przed
startem i ~90 min później).

**Wobec tego historii NIE uzupełniano jako „przedmeczowej”.** Wynik niżej to
**górna granica**: głosy z wiedzą z przebiegu meczu. Jeżeli nawet one nic nie
dodają do ceny, to głosy przedmeczowe (podzbiór, bez tej wiedzy) tym bardziej.

## 3. Populacja

- Piłka: każde rozliczone zdarzenie, dla którego Superbet przed startem
  wycenił 1 i 2 (`04_offer` `result_1x2`, `fetched_at_utc` < start) oraz
  remis (druga strona `double_chance` 12); 1X2 bez marży metodą sofy
  (`engine.devig_many`, power, trzy drogi); wynik z `07_settled`
  (`result_1x2` 1 / 2: WIN / LOSS; obie LOSS = remis). DNB z
  `draw_no_bet` 1 (obie strony), DC z `double_chance` 1X / X2 / 12.
- Tenis: zwycięzca meczu (`match_won_for`, obie strony), strona domowa z
  `02_fixtures` po nazwisku; wynik z `07_settled` (tylko WIN / LOSS; krecze /
  walkowery poza).
- Dni z kompletem `02/04/07`: 2026-09-17 .. 2026-11-04 (dni bez `04_offer`
  w tym formacie wypadają). Zdarzenie obecne w ofercie dwóch dni liczone raz
  (pierwszy dzień; 44 takie).
- Populacja: piłka 8 282, tenis 2 447 wierszy (10 685 zdarzeń). Zapytano
  wszystkie 10 685 (10 722 zapytania, część dwukrotnie): 10 702 odpowiedzi OK, 20 × 404. Poza analizą zdarzenia z < 20
  głosami.
- **n w analizie: piłka 8 173 (dev 2 381 / hold-out 5 792), tenis 2 405
  (dev 484 / hold-out 1 921).** Mediana głosów: piłka 371 (dev) / 455
  (hold-out), tenis 122 / 90.
- Korelacja udziału głosów na gospodarza z ceną bez marży: 0,84 (piłka),
  0,84-0,85 (tenis). Tłum przecenia gospodarza w piłce średnio o +6 pp.

## 4. Reguły zamrożone przed wynikami

Zapisane w kodzie (`FROZEN_RULES`, `SPLIT_DATE`, progi) przed pobraniem
pierwszego głosu:

- Podział po dacie: dev = dzień zdarzenia < 2026-10-20, hold-out ≥ 2026-10-20.
- Udział głosów = (głosy + 1) / (suma + k), k = 3 (piłka) / 2 (tenis);
  min. 20 głosów.
- **R1 (logistyczna)**, osobno sport × wybór (piłka 1 / X / 2, tenis
  gospodarz): M0: y ~ a + b·logit(p fair); M1: + c·logit(udział głosów).
  Dopasowanie na dev, ocena raz na hold-out: różnica Briera i log-loss
  (M1 − M0, suma po wyborach meczu), bootstrap meczów 95%.
- **R2 (zakład)**, d = p fair − udział głosów wyboru (DNB na udziałach
  znormalizowanych do dwóch stron, DC na sumie udziałów):
  ANTI_CROWD — graj, gdy d > t (tłum niedoszacowuje),
  PRO_CROWD — graj, gdy −d > t (za tłumem, wbrew cenie).
  t z {0,05; 0,10; 0,15; 0,20} wybrane na dev po ROI po podatku (min. 50
  zakładów), hold-out raz z tym t. Komórki: piłka 1X2 / DNB / DC, tenis
  zwycięzca × 2 kierunki = 8. ROI przed i po podatku (zwrot 0,88 × kurs;
  zwrot DNB przy remisie = 0), zrealizowane − p fair, bootstrap meczów,
  p jednostronne (ROI po podatku ≤ 0), Benjamini-Hochberg q = 0,05.
  Werdykt „przewaga” tylko gdy dolna granica ROI po podatku na hold-out > 0
  i komórka przechodzi BH.

**Zastrzeżenie uczciwości:** pierwszy przebieg `fetch` zatrzymał się po
2 240 zdarzeniach (błąd licznika „left”, poprawiony) i `report` został
uruchomiony raz na tym niepełnym zbiorze — 2 213 zdarzeń, wyłącznie
hold-out (najnowsze dni), dev pusty, więc t = 0,10 domyślne. Reguły po tym
nie zostały zmienione (jedyna zmiana kodu analizy: zdarzenie z dwóch dni
liczone raz — poprawka poprawności); `report` odmawia teraz pracy na
niepełnym pobraniu. Ten przypadkowy podgląd pokazał w piłce PRO_CROWD 1X2
zrealizowane − p fair +4,1 pp [+1,4; +6,8] przy t = 0,10 (ROI po podatku
−11,3% [−17,1; −5,3]); na pełnym hold-out z t z dev ta różnica znika
(niżej). Podaję dla kompletności.

## 5. Wyniki (hold-out, raz)

### R1 — czy głosy poprawiają prognozę ceny

| sport | n hold-out | Brier M0 | Brier cena | ΔBrier M1−M0 [95%] | Δlog-loss M1−M0 [95%] |
|---|---|---|---|---|---|
| piłka (1/X/2, suma) | 5 792 | 0,5767 | 0,5767 | +0,00026 [−0,00030; +0,00079] | +0,00049 [−0,00088; +0,00188] |
| tenis | 1 921 | 0,1976 | 0,1977 | +0,00006 [−0,00028; +0,00041] | +0,00055 [−0,00030; +0,00145] |

Dodanie głosów **nie poprawia** prognozy (różnice dodatnie = gorzej, CI
obejmują 0). Współczynniki c na dev: piłka 1: +0,085, X: −0,148, 2: +0,097,
tenis: −0,046 (przy b ≈ 0,9-1,3 dla ceny) — głosy niemal w całości są
odbiciem ceny.

### R2 — zakład według rozbieżności głosów i ceny

| komórka | t (dev) | n | zrealiz. − p fair [95%] | ROI przed podatkiem [95%] | ROI po podatku [95%] | BH |
|---|---|---|---|---|---|---|
| piłka 1X2 ANTI_CROWD | 0,05 | 7 405 | −0,3 pp [−1,2; +0,5] | −14,0% [−16,8; −11,1] | −24,3% [−26,8; −21,7] | nie |
| piłka 1X2 PRO_CROWD | 0,20 | 1 753 | +0,6 pp [−1,6; +3,0] | −6,4% [−11,6; −0,9] | −17,7% [−22,2; −12,8] | nie |
| piłka DNB ANTI_CROWD | 0,05 | 4 486 | −1,6 pp [−3,1; −0,1] | −14,5% [−17,4; −11,8] | −21,7% [−24,3; −19,3] | nie |
| piłka DNB PRO_CROWD | 0,20 | 1 374 | +0,4 pp [−2,4; +3,3] | −7,1% [−10,5; −3,5] | −14,9% [−17,9; −11,8] | nie |
| piłka DC ANTI_CROWD | 0,15 | 2 777 | +0,1 pp [−1,7; +1,9] | −11,6% [−14,6; −8,4] | −22,2% [−24,9; −19,4] | nie |
| piłka DC PRO_CROWD | 0,20 | 392 | +2,2 pp [−2,2; +6,8] | −8,3% [−15,7; −0,8] | −19,3% [−25,8; −12,7] | nie |
| tenis ANTI_CROWD | 0,20 | 393 | +1,9 pp [−2,8; +6,8] | −5,2% [−15,0; +4,6] | −16,6% [−25,2; −7,9] | nie |
| tenis PRO_CROWD | 0,15 | 732 | −0,9 pp [−4,4; +2,7] | −9,8% [−16,9; −2,3] | −20,6% [−26,9; −14,0] | nie |

p jednostronne ≈ 1,0 we wszystkich 8 komórkach; żadna nie przechodzi BH,
żadna dolna granica ROI po podatku nie jest > 0. Zrealizowane − p fair: 7 z 8
CI obejmuje 0 (DNB ANTI_CROWD lekko ujemne). Ujemne ROI przed podatkiem to
marża Superbetu (wyższa na kursach dalekich i remisach), nie sygnał.

## 6. Werdykt

**Brak sygnału — pytanie zamknięte dla obu reguł.** Nawet końcowy licznik
głosów (górna granica, z wiedzą z przebiegu meczu) nie dodaje nic do ceny
Superbetu bez marży: ani w kalibracji (R1), ani w zakładzie po rozbieżności
w żadną stronę (R2), w piłce i w tenisie. Głosy przedmeczowe są podzbiorem
tego licznika bez informacji z meczu, więc nie mogą zrobić więcej, chyba że
głosy w trakcie meczu *odwracały* sygnał przedmeczowy — mało prawdopodobne,
nie sprawdzone. Nic nie trafia do pipeline'u; brak przełącznika.

## 7. Dowód look-ahead (te same mecze przed i po starcie)

12 meczów 2026-11-05 zapytanych o 17:19Z (11-41 min przed startem) i ponownie
o 18:49Z (49-79 min po starcie):

| sport | event | start | suma głosów 17:19 | suma 18:49 | udział „1” |
|---|---|---|---|---|---|
| tenis | 17494464 | 18:00 | 63 | 66 | 0,92 → 0,92 |
| tenis | 17494469 | 18:00 | 99 | 111 | 0,69 → 0,69 |
| tenis | 17494471 | 18:00 | 74 | 78 | 0,16 → 0,18 |
| piłka | 16653153 | 17:30 | 1 142 | 1 142 | 0,86 → 0,86 |
| piłka | 17024976 | 17:30 | 372 | 388 | 0,70 → 0,70 |
| tenis | 17448175 | 17:30 | 60 | 61 | 0,18 → 0,18 |
| tenis | 17448195 | 17:30 | 53 | 54 | 0,38 → 0,39 |
| tenis | 17448182 | 17:30 | 58 | 58 | 0,14 → 0,14 |
| tenis | 17448825 | 17:30 | 51 | 52 | 0,16 → 0,17 |
| tenis | 17494562 | 17:30 | 62 | 71 | 0,15 → 0,17 |
| tenis | 17495216 | 17:30 | 54 | 55 | 0,85 → 0,84 |
| piłka | 16944501 | 17:45 | 61 287 | 64 339 | 0,08 → 0,08 |

Licznik rośnie po pierwszym zapytaniu (0-15%), ale nie da się rozdzielić
głosów z ostatnich minut przed startem od głosów w trakcie meczu (jeden mecz,
16653153, nie przybrał ani głosu — możliwe, że Sofascore zamyka głosowanie
przy starcie; niezweryfikowane). Udziały przesunęły się o ≤ 0,02. Wniosek:
końcowy licznik jest traktowany jako look-ahead (nie da się tego wykluczyć),
ale w tej próbce różni się od stanu tuż przed startem nieznacznie — więc
wynik z sekcji 5 jest bliski temu, co dałyby głosy przedmeczowe, a nie tylko
luźną górną granicą. n = 12, opis, nie pomiar.

## 8. Projekt przechwytu na przyszłość (nie podłączony)

Jeżeli operator mimo to chce czystego testu przedmeczowego:

- Nowy skrypt `scripts/sofa/capture_fan_votes.py --date D --loop`, osobny od
  `capture_closing.py` (ten jest tylko Superbet, bez mostka; głosy idą przez
  mostek Sofascore, więc `ensure_bridge.py` przed każdą rundą). Uruchamiany
  przez pętle dnia (`shadow_daily.py`, jak `capture_closing`), `day_status`
  WARN `loop:capture_fan_votes`.
- Dwa zapytania na mecz piłki / tenisa z `02_fixtures`: (1) zaraz po OFFER
  (para z ceną `04_offer` o tym samym czasie), (2) w oknie T−60..T−15 min
  (para z ponownym zapytaniem Superbetu o 1X2 / zwycięzcę w tej samej
  chwili — `closing.jsonl` ma tylko wydrukowane nogi). Zapis append-only
  `runs/sofa/<d>/fan_votes.jsonl` z `asked_at_utc`; nic go nie czyta poza
  `measure_fan_votes.py`.
- Liczba zapytań: 02_fixtures 11-02..11-04 to 151-200 meczów piłki i
  213-414 tenisa dziennie → ~400-600 meczów × 2 = **~800-1 200 zapytań
  Sofascore dziennie** (+ tyle samo zapytań Superbetu w oknie T−60) —
  ok. 2 min mostka przy 11 req/s, rozłożone na dzień.
- Test: wpis w `config/sofa_test_registry.json` przed zbieraniem, te same
  reguły R1 / R2, ocena po ≥ 3 000 meczach piłki (~3 tygodnie). Wobec
  wyniku z sekcji 5 rekomendacja: **nie podłączać** — górna granica nic nie
  pokazała.

## 9. Co nie zostało sprawdzone

- Głosy w okresie dev pochodzą z tych samych zapytań co hold-out (wszystkie
  2026-11-05) — licznik końcowy; brak różnicy w czasie zbierania.
- `bothTeamsToScoreVote` / `firstTeamToScoreVote` nie badane (pytanie
  operatora dotyczyło „kto wygra”).
- Brak podziału na ligi / poziomy turniejów (celowo — wiele komórek bez
  hipotezy).
