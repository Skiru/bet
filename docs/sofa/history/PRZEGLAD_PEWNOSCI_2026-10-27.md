# Przegląd liczenia pewności - 2026-10-27

Zlecenie operatora (wieczór 10-27): "Nie ma błędu w liczeniu pewności? Upewnij
się w literaturze, zrób głęboki 3 iteracje przeglądu dla każdego sportu,
sprawdź testy i popraw wszystkie błędy", potem "Rób refit i wszystko co
potrzeba", "otestuj i zweryfikuj e2e".

## Jak

Cztery przeglądy (piłka, tenis, hokej / koszykówka / siatkówka, CS2), każdy w
trzech iteracjach: (1) zestawienie każdego elementu ze standardem z literatury,
(2) odtworzenie każdego podejrzenia offline / zapytaniem tylko do odczytu,
odrzucenie nieodtworzonych i udokumentowanych decyzji, (3) przypadek
wywołujący, poprawka, szkic testu, wpływ na druk. Literatura m.in.: Dixon-Coles
1997, Karlis-Ntzoufras 2003, Klaassen-Magnus 2001, Newton-Keller 2005,
Kovalchik 2016, Stern 1994, Thomas 2007, Buttrey 2016, Beaudoin-Swartz 2010,
Ferrante-Fonseca 2014, Zadrozny-Elkan 2002, Niculescu-Mizil-Caruana 2005,
Wilson 1927, efekt schematu Kisha.

Żaden przegląd nie znalazł grubego błędu tłumaczącego wynik kuponu. Brak nóg
na strzały / faule w meczach wieczoru to nie błąd: Superbet stawia te linie przy
medianie (kursy 1.6-2.2), pewność nie dochodzi do 0.70.

## Potwierdzone defekty i decyzje

| # | sport | defekt | pomiar (95% bootstrap po meczu / serii) | decyzja |
|---|---|---|---|---|
| R1 | piłka | strona rynku łączonego bez drabinki Superbetu dostawała centrum bez korekty rywala, GAME_STATE, rozciągnięć, sędziego, fazy sezonu (replay krzywych je miał) | nasze dni 10-21..10-26, 4 102 wiersze / 1 370 meczów: log loss -0.0000 [-0.0025, +0.0025] - neutralnie | **włączone od 10-28 00:00Z** jako poprawka spójności (live = replay), nie przewaga |
| R2 | tenis | handicap gemów w secie jako niezależny joint (rho 0): remisowy wynik seta 0.256 zamiast 0.0002, +1.5: 0.747 zamiast 0.574 | historia 442 470 wierszy: +0.0646 [+0.0613, +0.0680]; linie Superbetu 5 260: +0.0442 [+0.0215, +0.0668]; koszyk 0.70-0.75 trafiał 0.623, teraz 0.725 | **włączone od 10-28 00:00Z** |
| R3 | hokej | gol do pustej bramki doliczany ponad średnią 3. tercji (P3 2.189 zamiast 2.05) | surowe p: P3 lepiej na 30 dniach, nie na 12 miesiącach; pełny mecz minimalnie gorzej; refit z R3 gorszy od krzywej 10-24 | kod w repo, **wyłączone** |
| R4 | CS2 | mapa 3 w Bo3 liczona jak mapa 1, a gra się ją tylko przy 1:1 (posterior Beta (pK+1)/(K+2)) | surowe p: luka -4.8 -> +0.15 pp, log loss -0.00243 [-0.00449, -0.00040]; refit CS2 z R4 nie lepszy od krzywej 10-24 | kod w repo, **wyłączone** do refitu CS2, który to poprawi |
| R5 | piłka | podział "pierwszy gol" przez Poissona przy golach NB (faworyt +0.7-0.9 pp) | surowe p bez zmian; krzywa po reficie gorsza (+0.0012) | kod w repo, **wyłączone** |
| F1 | wszystkie | krzywe nie zawsze rosną z p (dolna granica Wilsona przy cienkich koszykach) | koszykówka -0.00012 [-0.00017, -0.00007], CS2 -0.00005 [-0.00009, -0.00001] na liniach Superbetu; piłka / tenis -2e-8 | **koszykówka i CS2 od 10-28** (`config/sofa_sport_confidence_calibration.next.2026-10-28.json`); reszta bez zmian |
| F2 | sporty / CS2 | dolna granica krzywej bez efektu schematu (CS2 deff 1.75-3.4) | pełny refit z F1+F2 nie lepszy w żadnym sporcie | kod w `fit_sport_confidence.py` (domyślnie włączony dla przyszłych refitów), nic nie zainstalowane |
| F3 | CS2 | start Elo w oknie dopasowania | wypalenie 30-150 dni pogarsza holdout | odrzucone |
| T-BO5 | tenis | dopasowanie ratingu brało tylko 3:0 z meczów do 3 setów (selekcja na wyniku) | neutralnie (-0.9e-5) | poprawiona populacja na przyszłe dopasowania; nic nie wystawione |

Podejrzenia bez pomiaru (otwarte): tenis - sąsiedzi faworytów poza ITF słabsi o
5-8 pp, format super tie-breaka w ITF; piłka - średnie lig nie "as of";
koszykówka - wydrukowane nogi 0.590 vs 0.740 (znany "printable gap", kalibracja
na liniach w kwantylach modelu, nie w liniach Superbetu).

## E2E

Kopia dnia 10-27 w `data/refit_2026-10-27/e2e/`, kod z przełącznikami
przesuniętymi na 10-27, kopia bazy: SHEET (61 670 wierszy, OK), CONFIDENCE
(3 204 nogi, OK), SPORT_CONFIDENCE (czyta `.next.2026-10-27` = krzywe PAV, OK),
COUPON_ASSEMBLY (OK). Kontrolny SHEET z wyłączonymi przełącznikami na tej samej
bazie: p zmienia się wyłącznie w wierszach R1 (326, średnio +0.0003) i R2
(1 012, średnio +0.0008, p5..p95 -0.35..+0.35). Prawdziwy kupon 10-27
nietknięty (md5 bez zmian). Bramki: `tests/sofa` 6133+ zielone, ruff, mypy
--strict, rejestr testów.

Nie sprawdzone: wynik na rozliczonych nogach po 10-28 (pierwsza ocena po kilku
dniach w grupie ledgera "od 10-28").
