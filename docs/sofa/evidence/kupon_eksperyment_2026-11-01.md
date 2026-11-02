# Eksperyment /kupon - pilot 2026-11-01

Zlecenie operatora (01.11, ~14:00): wygenerować N kuponów na dziś promptem
`/kupon` z różnymi kursami, godzinami i parametrami, tak żeby jutro można je
było rozliczyć i poprawić działanie prompta. Dokumentacja, iteracyjne
poprawki, weryfikacja.

Pliki: plan `kupon_eksperyment_2026-11-01/plan.json`, harness
`scripts/sofa/slip_experiment.py` (test `tests/sofa/test_slip_experiment.py`),
wyniki dnia `runs/sofa/2026-11-01/slip_experiment/r<runda>/`, hipoteza
`T-KUPON-PROMPT-VS-CONTROL` w `config/sofa_test_registry.json` (PROPOSED).

## Co da się zmierzyć z jednego dnia - uczciwie

Jeden dzień to kilkadziesiąt różnych nóg, mocno skorelowanych (te same
najlepsze nogi wchodzą do wielu konfiguracji, nogi jednego meczu i jednego
dnia są zależne). Wynik W/L jednego dnia **nie rozstrzyga niczego o przewadze**
- backtest 31.10 (`kupon_od_nowa_2026-10-31.md`, ~1 800 komórek) już pokazał,
że żaden ranking nie bije losowego przy tej samej cenie. Dlatego pilot mierzy
przede wszystkim **jakość procesu prompta**, a wyniki traktuje jako pierwszy
punkt serii:

1. **Proces (dziś, bez wyników)**: czy argumenty działają, ile kuponów dzień
   daje na dany cel, co odrzuca pula, ile nóg trzeba czytać, czas rundy
   analityków, ile nóg odczyt wymienia, czy świeży kurs udaje się dopytać,
   czy nogi zaczynają się przed końcem odczytu.
2. **Wyniki (jutro, `settle`)**: kupony W/L/zwrot obok zmierzonej szansy i
   1/iloczynu; nogi: trafienia obok Σ 1/kurs; **CLV** (kurs wzięty / ostatni
   kurs Superbetu przed startem z `closing.jsonl`, piłka / tenis) - silniejszy
   sygnał niż W/L przy tej liczbie nóg.
3. **Ramiona**: prompt runda 1 (przed odczytem), prompt runda końcowa (po
   odczytach), **kontrola losowa** (ta sama pula i filtry, każda noga w ±5%
   kursu odpowiadającej nogi prompta, inny mecz, ziarno = id konfiguracji).
   Różnica prompt − kontrola przy tej samej cenie to jedyna miara, czy wybór
   prompta coś daje. Nogi wymienione przez odczyt (wypadły / weszły) ocenione
   osobno.

Osąd (`T-KUPON-PROMPT-VS-CONTROL`) dopiero przy 600 nogach na ramię, tylko z
dni od 02.11 (reguła rejestru: dane późniejsze niż zapis hipotezy); dzisiejszy
dzień to pilot, nigdy nie sumowany z serią.

## Plan konfiguracji (14 wywołań /kupon)

| id | okno | cel | nogi | kupony | inne |
|---|---|---|---|---|---|
| C01 | 16-18 | ~2 | 2 | 3 | domyślny |
| C02 | 18-20 | ~2 | 2 | 3 | domyślny |
| C03 | 20-24 | ~2 | 2 | 3 | domyślny |
| C04 | 16-24 | ~1.5 | 1 | 3 | single |
| C05 | 16-24 | ~3 | 2 | 2 | |
| C06 | 16-24 | ~3 | 3 | 2 | "3 nogi" |
| C07 | 16-24 | ~5 | 2 | 1 | cel nieosiągalny |
| C08 | 16-24 | ~5 | 4 | 1 | |
| C09 | 16-24 | ~2 | 2 | 2 | buildery |
| C10 | 16-24 | ~2 | 2 | 2 | `--allow-no-sample` |
| C11 | 16-24 | ~10 | 6 | 1 | długi |
| C12 | 18-21 | ~2.5 | 3 | 2 | |
| C13 | 16-24 | ~2.5 | 2 | 2 | nogi od 1.50 |
| C14 | 16-24 | ~2 | 3 | 2 | nogi do 1.30 |

Procedura (= pętla skilla `bet-slip-audit`, tylko zbiorczo): runda n -
`slip_experiment.py run` (14 × `build_slip.py --json-out`), suma zestawów do
czytania per sport w kawałkach po ≤ 10 nóg (mecz w jednym kawałku), analitycy
równolegle dokładnie promptem skilla, `merge_reads.py --slip`, runda n+1 -
aż `do przeczytania: nic` albo 3 rundy. Po ostatniej rundzie `control`.

Jutro (02.11, po `/sofa-settle` i `record_results.py` dla 01.11):

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/slip_experiment.py settle \
    --date 2026-11-01 --out-dir runs/sofa/2026-11-01/slip_experiment \
    --md-out docs/sofa/evidence/kupon_eksperyment_2026-11-01/rozliczenie.md
```

## Dziennik

### Runda 1 (14:03 CET)

- Bridge OK (339 ms). 14 konfiguracji, 29 kuponów, 67 nóg (z powtórzeniami);
  do czytania 27 nóg: piłka 17 (2 kawałki), siatkówka 8, koszykówka 2.
- C08-C11 bez nóg do czytania: KEEP z odczytów operatora 13:41-13:57 (okno
  3 h) użyty ponownie - pętla nie płaci drugi raz za tę samą nogę.
- Pula 16-24: 2 157 nóg; z `--allow-no-sample` 4 064 (bez próbki meczu 2 017
  odrzuconych normalnie). C13 (nogi od 1.50): **pula 6 nóg**.
- Analitycy rundy 1 (4 równolegle, start 14:06): koszykówka 2 KEEP (73 s,
  61k tokenów), siatkówka 8 KEEP (104 s, 76k), piłka cz. 2 7 KEEP (352 s,
  143k), piłka cz. 1 9 KEEP + 1 WATCH (522 s, 189k). Każdy raport przeszedł
  `check_analyst_report` i `merge_reads --slip` bez UNMATCHED / LEG_WITHOUT.
  Jedyne zdjęcie: Palermo – L.R. Vicenza „Palermo - liczba kartek: poniżej
  2.5” (RYNEK: rywale Vicenzy pod 2.5 w 4/9 przy pewności 0,70).

### Obserwacje procesu (runda 1)

| # | obserwacja | skutek / decyzja |
|---|---|---|
| O1 | Brak zapisu maszynowego kuponu - tylko markdown | **poprawione**: `build_slip.py --json-out` (SlipRecord.v1, klucz nogi = klucz `13_results.json`); `/kupon` i skill zapisują go zawsze obok `--md-out`; `slip_experiment.py settle --out-dir runs/sofa/<d>/slips` rozlicza kupony operatora |
| O2 | 55 z 67 miejsc nóg ma szansę = 1/kurs (pewność ponad cenę): knapsack w praktyce wybiera po cenie, a remis rozstrzyga niska marża | potwierdza backtest 31.10 (wybór ≈ losowy przy tej cenie); kontrola losowa dopasowana noga do nogi to mierzy |
| O3 | Pula ma mało nóg powyżej ~1.7: 16-24 z 2 nogami najwyżej ~2.93; C13 (nogi od 1.50) - pula 6 nóg | cel ~3 z 2 nogami nieosiągalny tego dnia; skrypt mówi to w 1. linii - zachowanie poprawne |
| O4 | Siatkówka: „nie dopytano” w 17 z 21 miejsc | nie defekt - pętla SHADOW robi migawkę co 30 min, cena kuponu nie jest starsza od najnowszej; reguła „kurs urósł > 2%” dla sportów działa z opóźnieniem do 30 min |
| O5 | Zestaw do czytania z `build_slip.py` nie miał `prior_analysis` (read_set.py go ma): analityk piłki robił pełne sekcje meczów czytanych rano (522 s, 189k tokenów) | **poprawione**: `write_read_set` dodaje `prior_analysis` z `analyses.json` (sekcje kuponu dnia) - analityk robi przebieg delta. Odczyty kuponów z czatu nie trafiają do `analyses.json` (widok KUPON) - otwarte |
| O6 | 9 z 33 różnych nóg ma własną próbkę poniżej 1/kurs (np. siatkówka 9/20 przy pewności 0,72) | tylko podgląd (kolumna pogrubiona) - backtest: próbka nie odróżnia nóg; jutro: trafienia tych nóg osobno |
| O7 | KEEP z odczytów operatora 13:41-13:57 użyty ponownie (C08-C11 bez czytania) | oszczędność działa |

### Runda 2 (14:14)

- 14 konfiguracji; do czytania 1 noga (zastępstwo za Palermo w C02).
- Analityk rundy 2: 1 KEEP (Elche – Valencia „1. połowa - Valencia liczba
  rzutów rożnych: poniżej 2.5”, 253 s, 113k). Napisał „kupon z czatu nie
  sprawdza świeżości ceny” - **nieprawda**: zapis C02 ma `fresh: OK`, 1.39 →
  1.39, dopytane o 14:14. Zestaw do czytania tego nie niósł (O8).

### Runda 3 (14:20) - koniec pętli

- `do przeczytania: nic`; 29 kuponów, 67 miejsc nóg, każda noga KEEP z
  odczytu tego kuponu (≤ 3 h).
- Kontrola (`control --round 3`, po O9): 13 z 14 konfiguracji; C13 bez
  kontroli (poza nogami prompta w puli od 1.50 zostały 2 nogi).

### Obserwacje (runda 2-3)

| # | obserwacja | skutek / decyzja |
|---|---|---|
| O8 | Zestaw do czytania nie niósł świeżego kursu - analityk kazał „sprawdzić kurs”, choć /kupon go dopytał | **poprawione**: noga zestawu ma `slip_price` (kurs kuponu, dopytany, `fresh`, wiek w min); kontrakt analityka (`sofa-analysis-core`) mówi, co z nim robić. Agent wczyta to w następnej sesji |
| O9 | Kontrola losowa dzieliła z promptem do 3 nóg | **poprawione**: nogi prompta wyłączone z losowania; tolerancja 5% → 10% → 20% |
| O10 | Między rundą 1 a końcową konfiguracje zmieniły do 4 nóg, choć odczyt zdjął jedną | to reguła „najpierw nogi z KEEP tego kuponu” (operator 21.10) - knapsack przestawia kupony, gdy przybywa KEEP-ów. Porównanie „runda 1 vs końcowa” mierzy więc odczyt **i** to przestawienie razem - rozliczenie podaje oba zbiory nóg (wypadły / weszły) |
| O11 | C09 (buildery): żaden builder nie wszedł; C11 (6 nóg): iloczyn ~10 osiągnięty | bez uwag |

### Weryfikacja kuponów końcowych (niezależny skrypt, 14:25)

67 miejsc nóg: każda noga jest w `11_coupon.json` z tymi samymi słowami
Superbetu, żaden mecz dwa razy w kuponie, żaden start < 15 min od budowy,
żadna noga zdjęta przez odczyt, szansa nigdy ponad 1/kurs, kupon
„osiągnięty” ma iloczyn ≥ celu, liczba nóg ≤ limitu. **0 uwag.** Bramki:
`tests/sofa` 6 287 passed, ruff, mypy --strict, rejestr testów - czyste.
Nie sprawdzone: ekran Superbetu (żaden kupon nie był stawiany), zgodność
kursu z ekranem po 14:20 (kursy mogą się zmienić do startu - to mierzy CLV).

## Zmiany w prompcie i kodzie (01.11)

1. `build_slip.py --json-out` + `slip_builder.record` (SlipRecord.v1);
   `/kupon` (`.claude/commands/kupon.md`) i skill `bet-slip-audit` zapisują go
   zawsze obok `--md-out`.
2. Zestaw do czytania `/kupon`: `prior_analysis` (przebieg delta zamiast
   pełnego, O5) i `slip_price` (O8); kontrakt `sofa-analysis-core`.
3. `scripts/sofa/slip_experiment.py` (run / control / settle) + test.
4. Hipoteza `T-KUPON-PROMPT-VS-CONTROL` (PROPOSED - operator decyduje o
   codziennym uruchamianiu harnessu; ~30-40 min i ~0,5-0,7 mln tokenów
   analityków na 14 konfiguracji, z czego większość to pierwszy odczyt).

Nie zmieniono niczego, co wybiera nogi (pula, knapsack, progi) - to byłaby
zmiana bez pomiaru; jednodniowy pilot jej nie uzasadni.

## Co sprawdzić jutro (02.11) i jak to czytać

Po `/sofa-settle` dnia 01.11 (13_results.json gotowe):

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/slip_experiment.py settle \
    --date 2026-11-01 --out-dir runs/sofa/2026-11-01/slip_experiment \
    --md-out docs/sofa/evidence/kupon_eksperyment_2026-11-01/rozliczenie.md
```

Pytania (każde z nazwanym n - przy ~45 różnych nogach na ramię żadna
różnica jednego dnia nie jest istotna; to punkt serii, nie werdykt):

1. Nogi prompta: trafienia vs Σ 1/kurs; to samo dla kontroli. Różnica
   prompt − kontrola ≈ 0 jest oczekiwana (backtest 31.10).
2. CLV (piłka / tenis): czy nogi prompta zamykają się niżej niż kontrola
   (rynek za nimi) - jedyny sygnał o sensownej mocy przy tym n.
3. Odczyt: noga zdjęta (Palermo, kartki) i nogi „wypadły / weszły” (O10).
4. O6: nogi z próbką poniżej 1/kurs - trafienia osobno (podgląd, nie reguła).
5. Proces: ile nóg „?” (nieocenione) - każda to defekt klucza albo
   rozliczenia, do naprawy jako błąd poprawności.

Rekomendacja na serię: ten sam plan codziennie (albo tylko 4-5
konfiguracji domyślnych, żeby obniżyć koszt odczytu), `settle` każdego
ranka; osąd `T-KUPON-PROMPT-VS-CONTROL` przy 600 nogach na ramię (~2 tyg.).

## Rozliczenie (02.11) - wnioski

Tabele: `kupon_eksperyment_2026-11-01/rozliczenie.md` (`slip_experiment.py
settle`, po SETTLE 05:47 i `record_results.py` 06:24). Pilot - nie sumowany
z serią, nic poniżej nie jest werdyktem.

**Kupony (runda końcowa):** prompt 16 W / 12 L / 1 ?, śr. zwrot +35,7%
(Σ 1/iloczyn 12,5 wygranych oczekiwanych); kontrola 8 W / 19 L, −50,2%
(oczekiwane 13,5). Runda 1 (przed odczytem): 20 W / 8 L, +83,1%.
Ta różnica jest **złudzeniem koncentracji**: 29 kuponów prompta stoi na 29
różnych nogach, a dwie przegrane nogi siedzą w 4 kuponach każda
(Regatas Lima (K) „Zwycięzca: 1” @1.58, Nashville „Liczba strzałów
Nashville: poniżej 19.5” @1.42).

**Q1 - nogi unikalne (jedyna miara):**

| ramię | nogi oc. | W | Σ 1/kurs | nadwyżka | z | single ×0,88 |
|---|---|---|---|---|---|---|
| prompt końcowy | 27 | 22 | 19,29 | +2,71 | +1,16 | +0,4% |
| prompt runda 1 | 31 | 26 | 22,21 | +3,79 | | +3,1% |
| kontrola | 54 | 37 | 40,14 | −3,14 | −0,98 | −18,5% |

Różnica nadwyżki na nogę prompt − kontrola +0,158, 95% bootstrap po meczach
[−0,028; +0,332] (24 / 46 meczów) - **przedział obejmuje zero**. Oba ramiona
w granicach szumu wokół ceny, zgodnie z backtestem 31.10.

**Q2 - CLV (najsilniejszy sygnał przy tym n):** prompt +0,36% (17 nóg),
kontrola +0,26% (41) - rynek nie poszedł za wyborem prompta. Brak przewagi.

**Q3 - odczyt:** zdjął / przestawił 5 nóg - wszystkie 5 wygrały (w tym
jedyny WATCH: Palermo „Palermo - liczba kartek: poniżej 2.5” @1.43);
weszła 1 - wygrała. Wszystkie 5 przegranych nóg prompta miały KEEP. Spadek
+83% → +36% to odczyt **razem** z przestawieniem KEEP-first (O10); 5 nóg nie
mówi nic o wartości odczytu (audyt 26.10: odczyty bez przewagi).

**Q4 - O6 (własna próbka < 1/kurs):** prompt 6/9 (oczek. 6,2), kontrola
15/22 (16,4) - brak sygnału, jak w backteście.

**Q5 - nogi „?”:** 2, obie to luki statystyk Sofascore, nie defekt klucza:
ALS Omonia – Nea Salamina „Liczba rzutów rożnych: poniżej 11.5”
(`NO_STATISTICS`, cały cypryjski dzień), RS Berkane – Raja „Liczba rzutów
rożnych: powyżej 6.5” (`STAT_KEY_ABSENT`, Botola bez rożnych). Kupon C14/1
otwarty do `resettle_sweep.py`. Podejrzenie (niezmierzone): /kupon może
wybrać rynek, którego Sofascore w tej lidze nie publikuje - warto zmierzyć
pokrycie rożnych per rozgrywki przed regułą.

**Defekty pomiaru:** (a) kontrola wyklucza nogi prompta tylko w obrębie
konfiguracji - 5 nóg unikalnych jest w obu ramionach; (b) tabela kuponów
`settle` liczy powtórzone nogi wielokrotnie - do serii `settle` powinien
drukować nogi unikalne i bootstrap po meczach jako wynik główny.

**Decyzja:** nic w wyborze nóg się nie zmienia. `T-KUPON-PROMPT-VS-CONTROL`
zostaje PROPOSED - seria tylko na decyzję operatora (koszt ~0,5-0,7 mln
tokenów / dzień przy 14 konfiguracjach).
