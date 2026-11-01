**Nie - nawet znajomość ruchu kursu z góry (najlepszy kwintyl ruchu do "zamknięcia") nie przebija podatku 12%: górna granica przedziału ROI po podatku to −11,6% w piłce i −7,3% w tenisie.**

# Ruch kursu - czy czas daje przewagę nad Superbetem (2026-11-01)

Tylko pomiar. Etap 0-1 z `docs/sofa/history/PROMPT_RUCH_KURSU_2026-11-01.md`
(wersja 2). Etap 1 skończył się na "nie", więc etapu 2 (Q2-Q5) nie było i nie
ma `PROTOCOL.md`. Nic w kuponie, `/kupon`, krzywych ani w teście papierowym
koszykówki nie zmieniono.

Skrypty i wyniki: `docs/sofa/evidence/ruch_kursu_2026-11-01/`.

## Etap 0

`runs/sofa/2026-10-31/13_results.json`: `computed_at_utc`
2026-11-01T08:44:22Z; won 9 873, lost 2 570, refund 96, unknown 168
(12 707 nóg). Dzień rozliczony.

## Co już było wiadomo (cytat, nie liczone od nowa)

- `docs/sofa/evidence/kupon_od_nowa_2026-10-31.md`: przy tej samej cenie
  statystyka meczu nie odróżnia dobrej nogi od złej; sygnał "kurs urósł > 2%"
  w hold-oucie −3,05 [−11,31; +5,42] n 261 - przedział przez zero.
- `slip_flow_backtest_2026-10-31/iter_a_clv.out` (10-13..10-26, przed
  podatkiem): najlepszy kwintyl ruchu −1,5% [−3,4; +0,3].

## Etap 1.1 - CLV wydrukowanych nóg (`audit_clv.out`)

`audit_clv.py --from 2026-10-13 --to 2026-10-31`, power devig, przedział
z losowania po meczu. Uwaga: `audit_clv.py` liczy CLV na `odds_taken`
(cena po przebudowach), nie na cenie wydruku.

| grupa | nogi | mecze | średni CLV (bez marży) | 95% | nad zamknięciem |
|---|---|---|---|---|---|
| piłka + tenis (`official`) | 55 197 | 7 639 | −3,73% | [−3,77; −3,70] | 24% |
| hokej | 4 869 | 977 | −5,72% | [−6,05; −5,39] | 22% |
| koszykówka | 214 | 144 | −5,39% | [−6,56; −4,33] | 43% |
| siatkówka | 568 | 292 | −3,88% | [−4,14; −3,62] | 32% |
| CS2 | 310 | 74 | −3,73% | [−4,61; −3,07] | 31% |

Na cenie **wydruku** (pierwszy `printed/<ts>.json`, `iter_a_clv.out`,
`two_way_close`, nogi z ceną partnera): piłka −3,75% [−3,79; −3,71] n 46 190,
nad zamknięciem 29,7%; tenis −3,60% [−3,67; −3,52] n 5 117, 21,5%.

## Etap 1.2 - sufit (`iter_a_clv.out`, `load.out`)

Kopie `load.py`, `lib.py`, `iter_a_clv.py` z `slip_flow_backtest_2026-10-31/`
(oryginały nietknięte). Zmiany: dni 10-13..10-31; "zamknięcie" = najnowszy
rekord `closing.jsonl` z `minutes_before` w 3-30 min (`bet.sofa.clv.is_close`),
bez `missing` / `started` / `error`; wszystkie dni (bez cięcia DEV), podatek
obok; piłka i tenis osobno; ruch też na cenie bez marży (`market_p` wydruku
vs `two_way_close` zamknięcia). Kurs wzięty = `odds` z `morning()` (pierwszy
wydruk, ≥ 15 min przed startem). Ruch = kurs wydruku / kurs zamknięcia − 1
(> 0 = kurs skrócił się po wydruku). Przedziały: bootstrap po meczu, 1000.

Ile wypadło:
- nogi piłki / tenisa z porannego wydruku: 87 964; z rekordem w
  `closing.jsonl`: 78 868; z ważnym zamknięciem: 73 730 (reguła 3-30 min nie
  odcięła żadnej - `capture_closing.py` i tak pisze tylko w tym oknie;
  odpadły rekordy `missing` / `error`); rozliczone won / lost: 72 618;
- nogi dodane w późniejszym wydruku (`first_snap > 0`, inna chwila decyzji,
  poza tabelą): 5 950;
- rekordy odrzucone dzień po dniu: `closing_drops.json`. 10-31: 23 966
  z 61 859 z `missing` (z tego 23 754 z `error`, DNSError). Dziura dotyczy
  **głównie całych meczów**: 260 z 1 026 meczów bez żadnego dobrego rekordu
  (19 015 złych rekordów), 157 meczów częściowo (4 951)
  (`hole_2026-10-31.out`).
- `odds_taken` = cena wydruku tylko w 72,1% nóg piłki i 79,6% tenisa -
  potwierdza pułapkę z promptu.

Ruch: piłka ruszyła się w 57,5% nóg (skrócił 29,8%, wydłużył 27,7%), tenis
40,0% (21,5% / 18,5%).

### Piłka (67 489 nóg, 6 466 meczów)

| grupa | n | trafione | śr. 1/kurs | ROI przed podatkiem | ROI po podatku |
|---|---|---|---|---|---|
| skrócone | 20 132 | 0,791 | 0,820 | −3,5% [−4,6; −2,4] | −15,1% [−16,0; −14,1] |
| bez ruchu | 28 687 | 0,788 | 0,833 | −5,4% [−6,2; −4,7] | −16,8% [−17,5; −16,1] |
| wydłużone | 18 670 | 0,762 | 0,827 | −7,9% [−9,0; −6,8] | −18,9% [−19,9; −18,0] |
| kw. 1 (najmocniej wydłużone) | 7 835 | 0,734 | 0,822 | −10,8% [−12,6; −9,0] | −21,5% [−23,1; −19,9] |
| kw. 2 | 7 774 | 0,798 | 0,848 | −5,9% [−7,3; −4,5] | −17,2% [−18,4; −16,0] |
| kw. 3 | 7 948 | 0,756 | 0,799 | −5,4% [−6,7; −4,0] | −16,8% [−17,9; −15,5] |
| kw. 4 | 7 561 | 0,812 | 0,850 | −4,4% [−5,9; −3,2] | −15,9% [−17,1; −14,8] |
| **kw. 5 (najmocniej skrócone)** | 7 684 | 0,788 | 0,800 | −1,4% [−3,1; +0,4] | **−13,2% [−14,7; −11,6]** |

Kwintyle na cenie bez marży (n 46 183): najlepszy −2,4% [−3,9; −0,8] przed,
−14,1% [−15,4; −12,7] po podatku.

### Tenis (5 129 nóg, 1 310 meczów)

| grupa | n | trafione | śr. 1/kurs | ROI przed podatkiem | ROI po podatku |
|---|---|---|---|---|---|
| skrócone | 1 101 | 0,777 | 0,812 | −4,3% [−8,4; −0,2] | −15,8% [−19,4; −12,2] |
| bez ruchu | 3 077 | 0,794 | 0,833 | −4,8% [−7,1; −2,5] | −16,2% [−18,2; −14,2] |
| wydłużone | 951 | 0,773 | 0,822 | −5,9% [−10,1; −1,7] | −17,2% [−20,9; −13,5] |
| kw. 1 (najmocniej wydłużone) | 412 | 0,735 | 0,816 | −9,7% [−16,0; −3,4] | −20,6% [−26,1; −15,0] |
| kw. 2 | 417 | 0,818 | 0,848 | −3,6% [−8,4; +1,0] | −15,1% [−19,4; −11,1] |
| kw. 3 | 420 | 0,724 | 0,779 | −7,0% [−13,1; −1,2] | −18,2% [−23,5; −13,1] |
| kw. 4 | 395 | 0,823 | 0,849 | −3,1% [−8,0; +1,7] | −14,7% [−19,1; −10,5] |
| **kw. 5 (najmocniej skrócone)** | 408 | 0,777 | 0,792 | −1,8% [−9,8; +5,3] | **−13,6% [−20,6; −7,3]** |

Kwintyle bez marży (n 5 117): najlepszy −2,4% [−6,6; +1,8] przed,
−14,1% [−17,9; −10,4] po podatku.

Sprawdzone lokalnie: ROI najlepszego kwintyla przeliczony wprost z
`legs.pkl` (bez bootstrapu) - piłka −1,36% / −13,19%, tenis −1,76% / −13,55%,
zgodne z tabelą.

## Etap 1.3 - decyzja

Górna granica ROI po podatku w najlepszym kwintylu: piłka −11,6%, tenis
−7,3% - obie < 0. Wybór nóg z wiedzą o przyszłym ruchu, wzięty po cenie
wydruku, traci po podatku co najmniej ~7-12%. Prognoza ruchu (etap 2) nie
może dać więcej niż ten sufit, więc **koniec pomiaru, bez etapu 2**.
Wynik zgadza się z wnioskiem roboczym z 10-26 (teraz na 19 dniach, po
podatku, piłka i tenis osobno).

## Czego nie sprawdzono

- Sufit dla hokeja, koszykówki, siatkówki i CS2: nie liczony (brak
  `closing.jsonl`; ścieżka z migawek SHADOW / CS2 nie była w zakresie etapu 1).
  Dla nich jest tylko CLV z `audit_clv.py` (wszystkie ujemne, wyżej).
- 10-31: ~25% meczów bez zamknięcia (DNSError) - wypadły z tabeli.
- Baza: zamiast `VACUUM INTO` całej `data/sofa.db` (55 GB przy 94 GB wolnego
  miejsca) skopiowano tylko 6 kolumn `sofa_settled_row` (zapasowe rozliczenie
  w `load.py`) do `data/ruch_kursu_2026-11-01/settled.db` (5,8 GB; do usunięcia).
