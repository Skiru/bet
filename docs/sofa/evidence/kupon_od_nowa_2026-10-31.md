# /kupon od nowa - backtest, wybór, hold-out, wdrożenie (2026-10-31)

Zlecenie: `docs/sofa/history/PROMPT_KUPON_OD_NOWA_2026-10-31.md`. Skrypty, komórki
i wyjścia: `docs/sofa/evidence/kupon_od_nowa_2026-10-31/` (bez `legs.pkl`,
`signals.pkl` i kopii bazy - zostały w `data/kupon_redesign_2026-10-31/`).

**W skrócie: przewagi nad ceną nie ma.** Żadna definicja „nogi mocnej
statystycznie” (własna próbka, co traci rywal, mecze obu drużyn, udział ligi,
h2h, sędzia, model, pewność nad 1/kurs, ich zgodność, k z n) nie odróżnia
dobrej nogi od złej przy tej samej cenie; żaden ranking kuponu nie bije
losowego; każdy kupon traci po podatku. Wdrożone jako **filtr jakości**, nie
przewaga: pula z własną próbką meczu ≥ 8, świeży kurs tuż przed odpowiedzią
(noga, której kurs urósł > 2%, wypada), kolumny dowodów obok 1/kurs, zdanie
„przewagi nad ceną nie ma”. Linia pieniędzy 0,88 × 0,96^n − 1.

## 1. Dane i protokół

- Nogi: wydruki dnia (`printed/*.json`) 10-13..10-30, **89 472 nogi**;
  moment decyzji = ostatnia migawka ≥ 30 min przed startem; kurs zamknięcia z
  `closing.jsonl` (pobrany przed startem); wynik z `13_results.json` albo
  `sofa_settled_row`. Nogi zdjęte odczytem poza pulą.
- Sygnały (piłka, rynki liczone): funkcjami `bet.sofa.dossier` cięte na start
  meczu (`team_games(before_ts=kickoff)`), liga na 00:00Z dnia, sędzia - jego
  mecze sprzed startu. Kopia bazy `VACUUM INTO` (54 GB), nigdy baza żywa.
- Podział: **dev 10-13..10-24** (szukanie), **walidacja 10-25..10-28**
  (wybór), **hold-out 10-29..10-30** (10-31 nierozliczony) - raz, po
  zamrożeniu reguł; `bt_lib.load('hold')` odmawia bez tokenu = sha256 pliku
  reguł.
- Miary: lift = trafienie − średnie 1/kurs; **nadwyżka** = lift komórki −
  lift całego splitu w tym samym paśmie 1/kurs (0,05), ważona nogami komórki
  („dobra 1,20 vs zła 1,20”); kupon: wypłata 0,88 × iloczyn (Bet Builder
  0,90 × iloczyn); CI bootstrap po meczu (1000), kupony po dniu i po kuponie;
  BH q = 0,10; n < 100 = podejrzenie. Protokół zapisany przed obejrzeniem
  sygnałów: `PROTOCOL.md`.

## 2. Komórki (workflow: 6 partii, każda z niezależnym weryfikatorem)

| partia | co | komórek |
|---|---|---|
| A pula | rodzina, kierunek, pasmo ceny, marża, próbka, źródło pewności | 339 (+86 cienkich) |
| B dowody piłki | własna próbka, rywal, obie drużyny, liga, h2h, sędzia, zgodność, k z n | 416 |
| C dowody reszty | źródło pewności, stawka ligi, offset linii, gracze, sporty | 315 |
| D ruch ceny | wzrost / spadek kursu do zamknięcia, progi 2-8% | 243 |
| E kupony | ranking × pula × liczba nóg × cel | 344 |
| F kontrole, buildery | losowe, obecny /kupon, pojedyncze, buildery | 154 |

Razem ≈ 1 811 komórek. Weryfikatorzy przeliczyli każdą czołową komórkę
dokładnie i nie znaleźli przecieku z przyszłości (drobna uwaga: `ladder_agree`
liczone po filtrze statusu - nieużywane). Liczby czołowych komórek
sprawdzone lokalnie jeszcze raz (`select/holdout.py`).

**BH**: 1 056 komórek nóg z n ≥ 100 na dev, **24 odkrycia** - wszystkie poza
czterema to jedna grupa: `forecast_source = league_rate` (unders karnych /
czerwonych kartek - ta sama liczba ligi dla każdego meczu). Pozostałe:
rożne OVER (+3,95 dev → +1,52 walidacja, CI przez zero), wiele szczebli
drabinki (+1,89 → +1,08), CS2 rundy (+8,48 → −0,90), pule cienkie. **Partia B
(zgodność statystyk) - zero odkryć**: „obie strony nad ceną”, „własna próbka
≥ cena”, k z n nie niosą informacji. 78 komórek istotnie ujemnych na dev
(gracze jednostronni, mikropróbki, nogi z kursem rosnącym).

## 3. Wybór na walidacji i hold-out (reguły zamrożone)

`frozen_rules.json`, sha256
`a3b8ae035cc7bde9221a18170a8a82a53ba921093372640a6917d830d2b3f1a0`.

Nogi (nadwyżka w pp, CI 95%):

| reguła | dev | walidacja | hold-out |
|---|---|---|---|
| cała pula | 0,00 (n 57 540) | 0,00 (n 19 021) | 0,00 (n 7 292) |
| L1 stawka ligi (`league_rate`) | +3,80 [+0,92; +6,76] n 870 | +7,08 [+3,42; +10,57] n 523 | +5,99 [−1,38; +12,97] n 157 |
| L2 = L1 i pewność < 1/kurs | +3,74 [+0,67; +6,66] | +6,24 [+2,63; +10,00] | +5,26 [−2,46; +11,99] n 119 |
| P1 zdjęte (kurs urósł > 2%), po cenie kuponu | −3,78 [−5,94; −1,80] n 3 860 | −5,70 [−9,76; −1,88] n 1 134 | −3,05 [−11,31; +5,42] n 261 |
| P1 zostawione, po kursie zamknięcia | −0,03 | +0,16 | −0,17 |

L1 jako pojedyncza po podatku: −12,5% / −8,4% / **−11,4%**. Hold-out nie
potwierdził żadnej reguły na poziomie istotności (CI przez zero przy n 157 /
261); kierunek obu się utrzymał.

Kupony, ROI po podatku (dev / walidacja / hold-out):

| konfiguracja | dev | walidacja | hold-out |
|---|---|---|---|
| S1 (protokół: L1, losowo, 3 nogi, cel 3) | −34,7% | +18,3% | −7,2% (81 kuponów) |
| S2 (L1, 2 nogi) | −15,6% | −0,9% | −28,4% (13) |
| C1 obecny /kupon | −29,0% | −22,6% | −21,3% (18) |
| C2 losowe 2 nogi | −21,8% | −17,7% | −28,4% |
| C3 losowa pojedyncza | −17,0% | −13,8% | −17,2% |

CI kontroli losowych (20 ziaren zebranych razem) są za wąskie - porównuj
punkty, nie przedziały. E: z 98 konfiguracji z ≥ 30 kuponami na obu splitach
**żadna nie jest nad zero na dev i walidacji naraz**; obecny /kupon gorszy od
losowego na dev. Buildery: 48 komórek, średnio −4,4% dev / −16,1% walidacja;
dwie dodatnie na obu splitach (n 108 / 36, CI przez zero), te najlepsze na
dev (+19,1%) odwracają się na walidacji (−21,7%).

## 4. Komórki jakości (po fakcie - etykieta „post hoc”, nie wybór)

`select/quality_posthoc.py`, nadwyżka pp:

| komórka | dev | walidacja | hold-out |
|---|---|---|---|
| próbka meczu ≥ 8 | +0,64 [0,00; +1,26] n 27 741 | +1,32 [+0,26; +2,42] | −0,02 n 3 803 |
| próbka 0 (stawka ligi / sam model) | −0,57 | −1,04 | +0,01 |
| mikropróbka 1-7 | −9,8 (n 86) | −23,2 (n 25) | n 6 |
| gracz jednostronny | −7,0 [−13,9; −0,5] (n 190) | −11,1 (n 51) | −1,9 (n 25) |
| próbka ≥ 8 i własny odsetek ≥ 1/kurs | +0,57 | +1,19 | −0,26 |
| próbka ≥ 8 i własny odsetek < 1/kurs | +0,72 | +1,14 | −0,07 |

Losowy podzbiór 10% nóg daje ±1,5-2 pp - to poziom szumu.

## 5. Co wdrożone i dlaczego

1. **Pula = własna próbka meczu ≥ 8** (`slip_builder.MIN_SAMPLE`, „bez próbki
   meczu” / „mikropróbka” w linii Odrzucone; CS2 silnik bez próbki
   przechodzi). Nie przewaga (hold-out −0,02) - wycina mikropróbki (−9,8 /
   −23,2) i gracza jednostronnego. `--allow-no-sample` tylko na prośbę
   operatora (L1 jest najmniej złą grupą, ale traci jako pojedyncza).
2. **Świeży kurs tuż przed odpowiedzią** (P1): wybrane nogi dopytane - piłka
   / tenis przez `OfferFetcher` (bezpiecznik Superbetu respektowany, błąd =
   „nie dopytano”), sporty z najnowszej migawki pętli sprzed startu; kurs >
   1,02 × kurs kuponu albo noga zeszła z oferty = wypada, kupon składa się bez
   niej (do 4 rund); niższy kurs zastępuje kuponowy. Progi 2 / 5 / 8% są
   ujemne na dev i walidacji (−3,8 / −7,3 / −9,8 dev; −5,7 / −12,6 / −19,2
   walidacja); 2% obejmuje najwięcej nóg (n 3 860 dev).
3. **Kolumny dowodów obok 1/kurs**: kurs kuponu → teraz, model, próbka k/n
   (pogrubiona poniżej 1/kurs), zestawienie, liga, h2h, sędzia
   (`bet.sofa.slip_evidence`, cięte na start). Tylko podgląd - ranking
   zostaje min(pewność, 1/kurs), bo ranking po dowodach nie pobił losowego.
4. **Linia pieniędzy** 0,88 × 0,96^n − 1: pula (próbka ≥ 8) zwraca 0,9597
   ceny (n 36 940) wobec 0,9466 wszystkich nóg; każda noga ok. −4%.
5. Zdanie „przewagi nad ceną nie ma” w linii pieniędzy - zawsze.

Bez epoki: kupon z czatu nie zmienia wydruku. Nic nie przefitowane ani
zainstalowane.

## 6. Czego nie obiecujemy

- Że kupon z puli wygra częściej, niż mówi cena - nie wygrywa (hold-out 0,00).
- Że dopytanie złapie każdy ruch: kurs może urosnąć później niż odpowiedź
  (niżej Bernau). Kupon podany > 30 min przed startem - puścić jeszcze raz
  przed postawieniem.
- Że L1 / P1 działają - zarejestrowane do pomiaru naprzód
  (`T-KUPON-LEAGUE-RATE-UNDER`, `T-KUPON-PRICE-RISE-DROP`), od 2026-11-01.

## 7. Porażki (komórki, które nie przeszły)

- Zgodność statystyk (partia B): zero odkryć BH z 336 komórek n ≥ 100.
- „Pewność nad 1/kurs”, model, h2h, sędzia, liga - w szumie.
- Rożne OVER, wiele szczebli, CS2 rundy - odkrycia dev, które nie przeszły
  walidacji.
- Wszystkie rankingi kuponu (pewność, dowody, zgodność, marża, cena krótka /
  długa) - żaden nad zero na obu splitach.
- Buildery - najlepsze na dev odwracają się na walidacji.
- S1 (protokół) - +18,3% na walidacji, −7,2% na hold-oucie: wybór na 36
  kuponach to szum.

## 8. E2E

**Odtworzenie 31.10, `/kupon 19:30-22:00` jak o 18:47** (wydruk 12:01Z jako
kupon; świeże ceny sportów z migawek sprzed 17:47Z, piłka „nie dopytano”, bo
oferta z przeszłości nie wraca):

| noga operatora | wtedy | po przebudowie |
|---|---|---|
| karne poniżej 0.5 (Milan - Inter, Anderlecht - Westerlo) | w kuponie | **poza pulą** - bez próbki meczu (`league_rate`) |
| Byfield punkty w przewadze poniżej 0.5 | w kuponie | **poza pulą** - bez próbki; kurs i tak urósł 1,27 → 1,30 |
| Sudosa-Desto 4. set | w kuponie, 1,58 | **zostaje**, kurs 1,58 → 1,53, próbka 3/8 (37,5%) pogrubiona przy 1/kurs 65% |
| Bernau zwycięzca | w kuponie, 1,52 | **zostaje** - migawki 1,52 do 18:04Z, wzrost do 1,65 po odpowiedzi |

Luki: (a) próbka rywala nie stoi przy nodze sportu (Hagen: 4 mecze) - nie
wdrożone, propozycja na dalej; (b) ruch Bernau przyszedł po odpowiedzi -
stąd rada „puść jeszcze raz przed postawieniem”; (c) Sudosa przechodzi, bo
próbka 8 ≥ 8 - jej niski odsetek to podgląd, nie bramka (zmierzone: własny
odsetek < 1/kurs nie jest gorszy).

**Żywy przebieg** 2026-10-31 20:17Z, okno 22-02, po `ensure_bridge.py`: exit
0, 2 z 2 kuponów; świeże ceny działały (piłka z oferty: Llaneros 1,33 → 1,33;
siatkówka z migawek), nogi hokeja ECHL „nie dopytano”; read set zapisany
(`runs/sofa/2026-10-31/read_set_slip_e2e_redesign/`). **Pętla analityków nie
została puszczona** - kupon testowy, nie do grania; nie sprawdzona w tym
przebiegu.

## 9. Bramki

`pytest tests/sofa` 6 282 passed, `ruff` czysto, `mypy --strict
--no-incremental` 356 plików bez błędów, `check_test_registry.py` czysto.
Nowe testy: `tests/sofa/test_slip_builder.py` (próbka, wzrost kursu, oferta
zeszła / nie dopytano, kolumny dowodów, migawka sportu, pogrubienie),
`tests/sofa/test_slip_evidence.py` (h2h i sędzia cięte na start).
