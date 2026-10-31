# Test papierowy: handicap punktowy koszykówki, kurs Superbetu x p otwarcia bet365 - prerejestracja 2026-10-31

Zgoda operatora: 2026-10-31. Test **papierowy**: żadnej stawki, nic nie jest
stawiane ani drukowane, żaden plik kuponu go nie czyta. Rejestr:
`T-PAPER-BB-HANDICAP-B365-OPEN` (`config/sofa_test_registry.json`,
`docs/sofa/REJESTR_TESTOW.md`).

## Reguła (zamrożona 2026-10-31, `RULE_ID` `PAPER-BB-HANDICAP-B365-OPEN-T0`)

Kod: `src/bet/sofa/paper_bb_handicap.py` (reguła), `scripts/sofa/paper_bb_handicap.py`
(dzień i zapis przed startem). Arytmetyka przepisana 1:1 z backtestu (`secondprice2/rows.py`
`sport_rows`, `run.py` `fire`), nie wymyślona na nowo. **Okno do przodu różni się od
backtestu tylko źródłem danych bet365** (punkt 2): linia i kurs otwarcia takie, jakie były
widoczne PRZED startem, nie po meczu.

1. **Kurs Superbetu**: wiersz SHADOW_SETTLE koszykówki (`runs/sofa/shadow/basketball/<plik>/settled.json`),
   rodzina `handicap`, okres 0 (cały mecz z dogrywką), strona T1 / T2, wynik WIN / LOSS -
   kurs z **ostatniego snapshotu SHADOW przed startem** (`shadow.latest_pre_kickoff`).
   `line` to handicap drużyny 1 po obu stronach. Mecz ze stanem innym niż SETTLED nie wchodzi.
2. **bet365**: Sofascore `/event/{id}/odds/1/all` (dostawca 1 = bet365). Rynki `isLive`
   odrzucone; jeden rynek „Point spread” bez `choiceGroup`, dwa wybory.
   - **Okno do przodu (od 10-31)**: tylko **najnowszy zapis pobrany przed startem**
     (wcześniejszy z: start Superbetu z rekordu SHADOW, start Sofascore). Zapisuje go pętla
     `paper_bb_handicap.py --capture --date <D> --loop` (co 15 min, każdy przypięty mecz
     koszykówki dnia D jeszcze nierozpoczęty i startujący w ciągu 3 h; startuje ją
     `shadow_daily.py`, `day_status` ostrzega `loop:paper_capture`, gdy jej brak). Każdy zapis
     zostaje (`runs/sofa/paper/bb_handicap/prestart/<D>/<id>.json`, lista `captures` z
     `fetched_at_utc` = chwila odpowiedzi, przycięta do rynków Point spread / Full time /
     Game total). Zapis pobrany w chwili startu lub później nigdy nie jest czytany. Mecz bez
     zapisu przed startem jest **wyłączony** i liczony jako „brak bet365 przed startem”
     (`no_b365_prestart`); po meczu nic nie jest pobierane.
   - **Backtest (do 10-30)**: payload pobrany **po meczu**, jak w backteście, raz na mecz,
     `runs/sofa/paper/bb_handicap/odds/<id>.json` - oznaczony `post_match_lookahead`.
3. **Dopasowanie linii**: pierwszy wybór bet365 to gospodarz, „(+16.0) Nazwa”. Linia pasuje,
   gdy ta liczba równa się linii Superbetu po stronie gospodarza Sofascore (linia drużyny 1,
   gdy gospodarz = drużyna 1, inaczej jej przeciwność). Strona Superbetu po stronie gospodarza
   -> wybór 0, gościa -> wybór 1. Inna linia bet365 = brak kandydata.
4. **Uczciwe p**: kurs **otwarcia** (`initialFractionalValue`) obu wyborów, ułamek + 1,
   overround 1,00..1,25, marża zdjęta metodą potęgową (p_i = (1/o_i)^k, k w [1; 8], 60 bisekcji).
5. **Wybór**: kurs Superbetu x p > 1 + t, **t = 0**.
6. **Rozliczenie**: wynik wiersza SHADOW_SETTLE; jednostka po kursie Superbetu: WIN = kurs - 1,
   LOSS = -1; po podatku 12% WIN = kurs x 0,88 - 1.
7. **Dzień**: okno sportowe (`sport_identity.day_window`, D = [end(D-1), end(D))): mecze plików
   D i D+1 z startem w oknie. Mecz nierozliczony = oczekujący;
   ten sam (mecz, linia, strona) liczony raz, w pierwszym dniu.

**Zajrzenie w przyszłość w backteście**: tam linia „Point spread” to linia bet365 widoczna
po meczu, a jej kurs otwarcia to otwarcie tej linii - w chwili zakładu bet365 mógł stać na
innej linii. Liczby backtestu mogą więc być **zawyżone**. Okno do przodu tego nie dziedziczy:
czyta wyłącznie to, co było widać przed startem. Koszt: mecz, dla którego bet365 nie
wystawił spreadu przed startem (albo pętla go nie zapisała), wypada z testu. Pierwszy zapis
10-31 13:15Z: spread miało 2 z 75 meczów startujących w ciągu 3 h - pokrycie trzeba
obserwować (`no_b365_prestart` w `ledger.json`).

## Backtest (POST HOC, z zajrzeniem w przyszłość, nie dowód)

| okno | n (mecze) | trafione | 1/kurs | ROI przed podatkiem [95% CI] | ROI po podatku [95% CI] |
|---|---|---|---|---|---|
| dev 10-13..10-26 | 68 (68) | 41 | 0,480 | +25,3% [+0,4; +49,4] | +10,2% [-11,6; +31,5] |
| hold-out 10-27..10-30, **post hoc** | 24 (24) | 16 | 0,478 | +36,9% [-5,2; +71,9] | +20,5% [-16,5; +51,2] |

Bootstrap meczów 2000, ziarno 7 (raport backtestu liczył dev na 500 losowaniach: [+1,7; +50,3] / [-10,5; +32,3]). Komórka nie była wybrana regułą prerejestrowaną backtestu
(ten wybrał dla koszykówki „ALL, t = 0”: dev po podatku -19,4%); to jedyna z 81 niepustych komórek dev
testu A (poza czterema z n <= 3) z przedziałem bez podatku powyżej zera, a przy n = 68
nie spełniała nawet progu wyboru backtestu (n >= 100) - wybór po fakcie, a jej hold-out uruchomiono dopiero
po obejrzeniu dev. Przedziały po podatku zawierają zero w obu oknach. **To podejrzenie,
nie przewaga.**

Odtworzenie: skrypt przepuszczony przez dni 10-13..10-30 z tymi samymi payloadami
(`--no-fetch`, cache z `secondprice2/raw`) daje te same 92 typy, w tej samej kolejności,
z tymi samymi kursami, p i wynikami; ROI i przedziały identyczne co do cyfry. Na żywo
2026-10-30 (payloady pobrane na nowo przez mostek): te same 6 typów, 5 trafionych.

## Okno do przodu i kryterium

- Okno: od **2026-11-01** (dni okna sportowego). Operator wskazał 10-31, ale rejestr testów
  nie dopuszcza danych z dnia rejestracji (część meczów 10-31 była rozegrana w chwili
  zamrożenia); 10-31 jest w sekcji backtestu jako `registration_day`, nigdy w oknie do przodu
  - ale już na danych sprzed startu (próba pętli zapisu).
- Dane okna do przodu: wyłącznie bet365 sprzed startu (linia i kurs otwarcia widoczne przed
  pierwszym gwizdkiem); mecze bez takiego zapisu wyłączone i policzone.
- Backtest i okno do przodu są osobnymi sekcjami `ledger.json` - **nigdy nie sumowane**.
- **Punkt oceny: n >= 300** rozliczonych typów okna do przodu (tempo backtestu ~5 dziennie,
  czyli ~2 miesiące). Przed n = 300 żadnej decyzji - `--report` mówi: „ocena dopiero przy
  n >= 300; do tego czasu to nie jest przewaga”.
- **Sukces**: dolna granica 95% CI ROI **po podatku** (bootstrap meczów) > 0. Wtedy rozmowa
  z operatorem - nic nie włącza się samo; reguła nigdy nie staje się krzywą ani bramką kuponu.
- **W przeciwnym razie**: test NIEZALICZONY, reguła odpada (do `model-state.md` (d)), bez
  szukania „lepszego t” czy innej rodziny na tych samych danych.

## Codziennie

`/sofa-day` krok 1c, po rozliczeniu D-1:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/paper_bb_handicap.py --date <D-1> --pending --report
```

Pętla zapisu przed startem dnia D działa sama (start z `shadow_daily.py`); ręcznie:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/paper_bb_handicap.py --capture --date <D> --loop
```

Wynik: `runs/sofa/paper/bb_handicap/<D>.json` (kandydaci z kursem, p, przewagą, wynikiem,
źródłem bet365 i chwilą zapisu; oczekujące mecze; mecze bez bet365 przed startem; luki
pobrania) i `ledger.json`. Kod wyjścia 0 OK / 1 oczekujące albo luka
pobrania / 2 błąd. Testy: `tests/sofa/test_paper_bb_handicap.py` (jednostkowe i E2E na
prawdziwych rekordach 10-27 / 10-28 z nagranymi payloadami; okno do przodu: zapis przed
startem z inną linią niż po meczu -> wybór na linii sprzed startu, zapis po starcie
ignorowany, mecz bez zapisu wyłączony i policzony).
