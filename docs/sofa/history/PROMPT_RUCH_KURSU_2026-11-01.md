# Prompt na nową sesję - ruch kursu: kiedy Superbet się myli (2026-11-01, wersja 2)

Wersja 2 (2026-11-01, po audycie wersji 1): najpierw tani etap 0-1 (sufit po
podatku na danych z dysku, bez agentów). Etap 2 (pełne Q1-Q5) tylko wtedy, gdy
sufit wyjdzie dodatni. Poprawione: kurs wzięty z wydruku zamiast `odds_taken`,
"zamknięcie" = 3-30 min przed startem (`bet.sofa.clv.is_close`), hold-out naprzód zamiast spalonych dni
10-29..10-30, ścieżka ceny bez błędu przeżywalności, istniejące narzędzia
(`audit_clv.py`, `iter_a_clv.py`), usunięte liczby bez źródła.

Uruchomienie: otwórz nową sesję Claude Code w `/Users/mkoziol/projects/bet` i wklej:

> Przeczytaj docs/sofa/history/PROMPT_RUCH_KURSU_2026-11-01.md i wykonaj
> wszystko, co jest pod kreską. To jest moje zadanie na tę sesję. Najpierw
> sprawdź, czy 2026-10-31 jest rozliczony w runs/sofa/2026-10-31/13_results.json;
> jeśli nie, powiedz mi i poczekaj.

Bez słowa "ultracode": etap 0-1 to kilka poleceń. Workflow tylko w etapie 2
i tylko na moje wyraźne "tak".

---

Zmierz, czy da się przebić cenę Superbetu **czasem** (wziąć cenę, zanim rynek
się przesunie), a nie statystyką meczu. **Tylko pomiar.** Nic nie zmieniaj
w kuponie dnia, w `/kupon`, w krzywych ani w teście papierowym koszykówki
(`T-PAPER-BB-HANDICAP-B365-OPEN`). Narracja: jedna linia na krok.

## Co już wiadomo (nie mierz tego od nowa, zacytuj)

- Backtest 31.10 (`docs/sofa/evidence/kupon_od_nowa_2026-10-31.md`): przy tej
  samej cenie żadna statystyka meczu nie odróżnia dobrej nogi od złej.
  Sygnał "kurs urósł > 2%" (P1, linia 73): dev −3,78 [−5,94; −1,80] n 3 860,
  walidacja −5,70 [−9,76; −1,88] n 1 134, **hold-out −3,05 [−11,31; +5,42]
  n 261 - przedział przez zero**. To podejrzenie, nie potwierdzony sygnał.
- Ruch do zamknięcia (`docs/sofa/evidence/slip_flow_backtest_2026-10-31/iter_a_clv.out`,
  10-13..10-26, 54 824 nogi, zwroty **przed podatkiem**, `lib.leg_profit(tax=False)`):
  kurs się ruszył w 55,7% nóg (skrócił 29,1%, wydłużył 26,6%).
  Najlepszy kwintyl ruchu, czyli wybór z wiedzą o przyszłości, po kursie porannym:
  **−1,5% [−3,4; +0,3]**. Po podatku 12% (0,88 × (1 + ROI) − 1) to ok. **−13%**.
  Korelacja ruchu z cechami porannymi: pewność − 1/kurs 0,088, marża −0,02,
  pewność −0,014, kurs 0,071, godziny do startu 0,003.
- Wniosek roboczy, do sprawdzenia w etapie 1: nawet doskonała prognoza ruchu
  nie przebija podatku na tej puli.

## Etap 0 - warunek startu

`runs/sofa/2026-10-31/13_results.json`: podaj `computed_at_utc` i liczby
statusów (won / lost / refund / unknown). Brak pliku = powiedz i czekaj.

## Etap 1 - sufit po podatku (bez agentów, jedna sesja, ~kilka poleceń)

1. **CLV wydrukowanych nóg**: `PYTHONPATH=src:. .venv/bin/python
   scripts/sofa/audit_clv.py --from 2026-10-13 --to 2026-10-31`, wynik do
   pliku, w raporcie tylko podsumowanie (średni CLV bez marży, udział nóg nad
   zamknięciem, przedział z losowania po meczu, osobno piłka / tenis / sporty).
2. **Sufit**: skopiuj `load.py`, `lib.py` i `iter_a_clv.py` z
   `docs/sofa/evidence/slip_flow_backtest_2026-10-31/` do katalogu wyników
   (oryginałów nie ruszaj). W kopiach:
   - `load.py`: `DAYS` na 10-13..10-31 (oryginał kończy na 10-30). Rekord
     zamknięcia = najnowszy z `minutes_before` w 3-30 min
     (`bet.sofa.clv.CLOSE_MIN_MINUTES` / `CLOSE_MAX_MINUTES`), bez
     `started` / `missing` / `error`. Oryginał bierze najnowszy rekord bez
     tego filtra. Policz, ile nóg wypadło.
   - `iter_a_clv.py`: wszystkie dni zamiast `DEV`, `tax=True` obok
     `tax=False`, osobno piłka i tenis.

   `odds` w `load.py` to już cena nogi z pierwszego wydruku dnia
   (`morning()`: `first_snap == 0`, ≥ 15 min przed startem) - to jest "kurs
   wzięty". Tabela: skrócone / bez ruchu / wydłużone i kwintyle ruchu: n,
   trafienia, średnie 1/kurs, ROI przed i po podatku z przedziałem
   (bootstrap po meczu, 1000).
3. **Decyzja**:
   - górna granica przedziału ROI po podatku w najlepszym kwintylu < 0 → koniec
     pomiaru: raport "nie - nawet znajomość ruchu z góry nie przebija podatku",
     bez etapu 2;
   - górna granica ≥ 0 → zapytaj mnie, czy robić etap 2 (podaj liczby).

## Etap 2 - tylko po moim "tak"

Pytania (kolejność bez zmian):

- **Q2 Czy ruch da się przewidzieć** z cech znanych w chwili decyzji: godziny
  do startu, sport, rodzina / kierunek, poziom rozgrywek, marża drabinki,
  pewność − 1/kurs, `forecast_p` − 1/kurs, próbka, pasmo ceny, godzina, dzień
  tygodnia, linia główna / boczna. **Trzy klasy** (skróci / bez zmian /
  wydłuży), miara: AUC jeden-przeciw-reszcie i trafność względem
  przewidywania "bez zmian". Prosty model (logistyczna, płytkie drzewo).
- **Q3 Czy to zarabia**: reguła "bierz nogi, którym Q2 przewiduje skrócenie",
  zwrot pojedynczej po podatku i lift ponad pasmo ceny vs losowa noga z pasma.
- **Q4 Momentum / odwrót**: czy pierwszy ruch przewiduje dalszy. Ścieżka:
  powtarzane rekordy `closing.jsonl` (mediana 5 na nogę, tylko ostatnie
  30 min) i kolejne `printed/<ts>.json` - **uwaga na przeżywalność**: wydruk
  pokazuje nogę tylko, gdy przeszła bramki, a noga, której cena się
  pogorszyła, z niego wypada. `legs` w `printed/<ts>.json` to prawie tylko
  nogi wydrukowane (ostatni wydruk 10-31: 12 899 `legs` wobec 12 651
  `singles`, 20 ponad nie), plus `removed_by_reads`. Licz więc tylko pary
  wydruków, w których noga jest w obu, a wypadnięte nogi raportuj jako
  osobną grupę z wynikiem. Wynik Q4 = podejrzenie.
- **Q5 Druga strona na prawdziwej cenie**: zwrot drugiej strony krótkich nóg
  (1,00-1,15) na `partner_close` po podatku. Podaj pokrycie dzień po dniu -
  `partner_close` jest w 98% rekordów 10-13, 67% 10-24, 43% 10-31 (70% po
  odrzuceniu `missing`) - i sprawdź, czy nogi bez partnera różnią się ceną
  od reszty. Nie cytuj "−36% z marży" - ta liczba nie ma źródła w raportach.

Wykonanie: najwyżej 1 agent liczący + 1 niezależny weryfikator (dostaje kod
i dane, nie wnioski). Workflow wielu agentów tylko na moje wyraźne słowo.

## Pola i pułapki (sprawdzone 2026-11-01)

- `runs/sofa/<d>/closing.jsonl` (`capture_closing.py`): tylko wydrukowane nogi
  **piłki i tenisa**, kilka rekordów na nogę (czytaj najnowszy na nogę, jak
  `audit_clv.py`). "Zamknięcie" = rekord z `minutes_before` w 3-30 min
  (`bet.sofa.clv.is_close`), nie prawdziwe zamknięcie; tak to nazywaj.
  Rekordy z `missing` / `started` / `error` odrzuć i policz (10-31: 23 966
  z 61 871 z `missing`). Zanim liczysz 10-31, sprawdź, czy dziura dotyczy
  całych meczów, czy pojedynczych rynków.
- **`odds_taken` ≠ kurs wydruku**: to `offered_odds` nogi z `11_coupon.json`
  w chwili pomiaru, po przebudowach (`capture_closing.py:145`; w 10-13..10-26
  tylko 75,6% równe porannemu). Kurs wzięty = `offered_odds` z **pierwszego**
  `printed/<ts>.json`, w którym noga jest (+ `price_fetched_at_utc`), czyli
  `odds` w `load.py`. Wynik = `13_results.json` (klucz `[event, market,
  subject, line, direction]`, temat małymi literami).
- Nogi dodane w późniejszym wydruku (`first_snap > 0`) `morning()` pomija.
  Policz je osobno, bo to inna chwila decyzji.
- CLV i ruch licz na cenie **bez marży** (z `partner_close`, jak `bet.sofa.clv`),
  surowy kurs tylko obok - zmiana marży to nie ruch rynku.
- Sporty (hokej, koszykówka, siatkówka, CS2): `closing.jsonl` ich nie ma.
  Ścieżka z migawek SHADOW / CS2 (`audit_clv.py` czyta je przez
  `bet.sofa.clv.graded_close_rows`). Zawsze osobno, nigdy w puli z piłką.
- `prestart/` testu papierowego: tylko do odczytu.
- Baza tylko przez kopię `VACUUM INTO` do `data/ruch_kursu_2026-11-01/`,
  nigdy żywa `data/sofa.db`.

## Protokół (zapisz w `PROTOCOL.md` przed obejrzeniem wyników etapu 2)

- Podział: dev 10-13..10-24, walidacja 10-25..10-31. **Dni 10-29..10-30 nie
  są hold-outem** - były hold-outem backtestu 31.10 i na nich oglądano sygnał
  ruchu kursu. **Hold-out = naprzód**: dni od 2026-11-01 rozliczone po
  zamrożeniu reguł (minimum 7 dni, najwcześniej po rozliczeniu 11-07),
  uruchomiony raz. Warunek: każdy dzień hold-outu ma `closing.jsonl`
  (pętla `capture_closing.py`, `day_status.py` `loop:capture_closing` bez
  WARN). Dzień bez niego wypada i jest wymieniony w raporcie.
- `docs/sofa/evidence/kupon_od_nowa_2026-10-31/bt_lib.py` ma na sztywno
  `hold = 10-29..10-30` i token starego `frozen_rules.json`. Skopiuj go do
  katalogu wyników, zmień podział i blokadę (nowy `frozen_rules.json`, sha256)
  - oryginału nie ruszaj.
- Moment decyzji = cena z wydruku (pierwszy `printed/<ts>.json`) ≥ 30 min
  przed startem; "zamknięcie" = najnowszy rekord `closing.jsonl` w 3-30 min.
- Ruch nogi = cena wydruku / cena zamknięcia − 1. Klasy Q2: "bez zmian" =
  |ruch| < 1% (próg zapisany przed oglądaniem, nie stroić). Ruch liczony też
  na cenie bez marży, a raport podaje oba.
- CI: bootstrap po meczu (1000). BH q = 0,10 na komórkach n ≥ 100;
  n < 100 = podejrzenie. Podatek 12% w każdym zwrocie (0,88 × kurs).
- Porównanie zawsze w tym samym paśmie ceny (lift komórki − lift pasma).
- Porażki też do raportu.

## Zasady (z CLAUDE.md)

- Tylko Sofascore i Superbet - bet365 tylko w istniejącym teście papierowym.
- Nic, co zmienia wydruk, bez zgody operatora; skrypty `measure_*.py` i kopie
  w katalogu wyników są tylko do odczytu danych.
- Nie wymyślaj liczb: każda liczba z plikiem i n. Liczb z czatu bez pliku nie
  powtarzaj.
- Sprawdź liczby agenta lokalnie, zanim trafią do raportu.
- Wynik rozliczony to fakt o dniu, nie o decyzji.

## Wynik

- Raport po polsku: `docs/sofa/evidence/ruch_kursu_2026-11-01.md`, skrypty
  i wyniki w `docs/sofa/evidence/ruch_kursu_2026-11-01/`.
- Pierwsza linia raportu: jednym zdaniem, czy czas daje przewagę po podatku
  (tak / nie / za mało danych - ile dni potrzeba).
- Etap 1 kończy się na "nie": raport krótki (sufit, CLV, wniosek) i koniec.
- Reguła po hold-oucie naprzód: wpis do rejestru testów jako test naprzód
  (wzór: `T-KUPON-PRICE-RISE-DROP` w `config/sofa_test_registry.json`)
  i propozycja dla `/kupon` - **bez wdrażania**.
- Linia w `memory/` i w `MEMORY.md`.
