# Połówki kartek na centrum całego meczu, karne / czerwone strony z przewagą drużyny (2026-10-21)

Przełącznik: `FOOTBALL_CARD_HALVES_TERMS_FROM_UTC` (`bet.sofa.epochs`, znacznik
`card_halves_terms_v1` w `incident_rule`), od 2026-10-21 00:00Z, przed budową
dnia 10-21. Źródło: audyt 2026-10-21 (sekcja „Połówki kartek” i „Karne /
czerwone strony”). Pomiar: `scripts/sofa/measure_football_side_terms.py`
(tylko odczyt), wynik `scratchpad/side_terms.json` sesji.

## Metoda

Historia w kolejności czasu (933 309 meczów), wszystko czytane przed meczem
(mecze jednej sekundy startu dodawane razem). Dopasowanie 2025-08-01..02-28,
test 2026-03-01..10-13. Przedziały 95%: bootstrap po meczach (500 powtórzeń).
Log-loss: niżej = lepiej, różnica „kandydat − dzisiaj”.

## 1. Karne i czerwone strony

Dzisiaj: p = as-of częstość rozgrywek (ściągnięta do płci, `BASE_M` 30) – każda
drużyna Ligi Mistrzów 10-20 miała `penalties_for` pon. 0,5 = 0,8314 (w tym
pomiarze; 0,8358 w audycie). Kandydaci: intensywność ligi λ_L = −ln(1 − p_L)
× exp(β · x), β z pseudo-wiarygodności Poissona na liczbach zdarzeń okna
dopasowania.

| rynek (0,5) | cecha | β | Δ log-loss [95%] | UNDER ≥ 0,70: p / zrealizowane |
|---|---|---|---|---|
| penalties_for | płasko | – | – (0,37311) | 0,8698 / 0,8736 |
| | **przewaga (oczek. różnica bramek)** | 0,276 | **−0,00367 [−0,00434, −0,00306]** | 0,8678 / 0,8739 |
| | bramki strony / liga (`league_rates`) | 0,655 | −0,00278 [−0,00340, −0,00227] | 0,8731 / 0,8736 |
| | bramki + własna częstość | 0,643 / 0,177 | −0,00354 [−0,00423, −0,00293] | 0,8734 / 0,8737 |
| | własna częstość | 0,279 | −0,00028 [−0,00052, −0,00003] | 0,8704 / 0,8735 |
| penalties_1h_for | **przewaga** | 0,308 | **−0,00176 [−0,00225, −0,00125]** | 0,9409 / 0,9446 |
| | bramki / liga | 0,729 | −0,00128 [−0,00173, −0,00090] | 0,9440 / 0,9446 |
| penalties_1h_total | przewaga (średnia mnożników stron) | – | +0,00021 [−0,00002, +0,00046] | 0,8858 / 0,8936 |
| | własna częstość | – | −0,00016 [−0,00025, −0,00007] | 0,8896 / 0,8936 |
| red_cards_for | **przewaga** | −0,172 | **−0,00067 [−0,00097, −0,00033]** | 0,8991 / 0,9048 |
| | przewaga + własna + faule + sędzia | | −0,00095 [−0,00133, −0,00054] | 0,8992 / 0,9049 |
| | faule / sędzia / własna osobno | | CI obejmuje 0 lub ≈ 0 | |
| red_cards_1h_for | przewaga | −0,199 | −0,00013 [−0,00030, +0,00006] | – |
| red_cards_1h_total | każda | | gorzej (+0,0001..+0,0003) | – |

Wybór: przewaga drużyny (najprostsza, najlepsza lub równa najlepszej, czyta to
samo `FootballForecast.supremacy` co GAME_STATE) dla `penalties_for`,
`penalties_1h_for`, `red_cards_for` na linii 0,5. Linia 1,5 czerwonych,
`red_cards_1h_for` i sumy 1. połowy: bez zmian (nic nie jest lepsze z
przedziałem poza zerem; „własna częstość” w `penalties_1h_total` −0,00016 nie
rozróżnia meczów – SD p bez zmian – pominięta). Odchylenie p między stronami
`penalties_for` rośnie z 0,039 do 0,049. 10-20, LM: `penalties_for` pon. 0,5
od 0,655 (AS Roma) do 0,923; Porto 0,695 / PSV 0,911 (było 0,8314 obie).

## 2. Połówki kartek: centrum całego meczu

Dzisiaj: strona = centrum ratingu `cards_points_for` × udział połowy.
Kandydat: centrum na żywo całego meczu (`fit_count_stretch.walk` – centrum
SHEET – × GAME_STATE × sędzia × bliskość, zainstalowane tabele) × ten sam
udział; r połowy dopasowane na oknie dopasowania dla każdego modelu.
50 058 meczów (25 241 w teście).

| model | 1. poł. strona Δ | 1. poł. suma Δ | 2. poł. strona Δ | 2. poł. suma Δ |
|---|---|---|---|---|
| centrum na żywo bez członów | +0,0005 [−0,0002, +0,0012] | +0,0001 [−0,0003, +0,0005] | −0,0017 [−0,0027, −0,0006] | −0,0007 [−0,0012, −0,0001] |
| **na żywo × człony (zainstalowane)** | **−0,0053 [−0,0065, −0,0039]** | **−0,0026 [−0,0036, −0,0016]** | **−0,0087 [−0,0105, −0,0067]** | **−0,0052 [−0,0067, −0,0038]** |
| na żywo × człony dopasowane tylko na oknie dopasowania | −0,0050 [−0,0062, −0,0036] | −0,0021 [−0,0031, −0,0012] | −0,0082 [−0,0099, −0,0063] | −0,0049 [−0,0063, −0,0037] |
| rating × człony (zapas SHEET) | −0,0048 [−0,0060, −0,0036] | −0,0026 [−0,0036, −0,0017] | −0,0052 [−0,0068, −0,0037] | −0,0044 [−0,0057, −0,0031] |

Człony zainstalowane były dopasowane na oknach zachodzących na test (bliskość
i sędzia od 2026-01-01); wersja z członami dopasowanymi tylko na 2025-08..02
(γ_GS −0,076, β_sędzia 0,499, g1 0,045, g2 −0,066) daje prawie to samo – zysk
nie jest artefaktem dopasowania. Kalibracja ≥ 0,70 (zrealizowane − p):
1. poł. suma UNDER +0,14 → −0,40 pp, strona UNDER +1,23 → +0,71 pp; 2. poł.
suma OVER −1,86 → −1,12 pp, strona OVER −0,20 → +0,75 pp.

Wdrożenie: SHEET wycenia połówki po pętli, na centrum wiersza
`cards_points_for` strony; strona bez tego wiersza – rating × trzy człony
(zmierzone lepsze od dzisiaj, wyżej). 10-20: 704 odczytów stron z centrum na
żywo, 84 zapasowe; 10-18: 1 998 / 126.

## 3. Krzywe (zainstalowane 10-21) na nowym p

Replay `fit_incident_set_curves.py --group card_halves --card-terms`
(`data/refit_card_halves_terms_2026-10-21/card_halves/`, przygotowane, nie
zainstalowane).

- **Zainstalowane krzywe czytane na nowym p** (holdout 09-01..10-13, krzywa ≥
  0,70; uwaga: krzywe końcowe były dopasowane z holdoutem, na starym p): 20 z
  20 kluczy przechodzi jednostronnie (n ≥ 300, luka ≥ −2 pp); najgorsze:
  women `cards_points_2h_total|UNDER` −1,85 pp (n 485), women
  `penalties_1h_for|UNDER` −1,51 pp (n 330), `cards_points_1h_total|UNDER`
  −0,89 pp (n 7 978), `cards_points_1h_for|UNDER` −0,82 pp (n 9 609).
- **Bramka od nowa na nowym p** (krzywa z wierszy przed 09-01, holdout
  09-01..10-13): 18 z 20 zainstalowanych kluczy przechodzi;
  `cards_points_2h_for|UNDER` nie (n 1 261 ≥ 0,70, luka −2,12 pp; na starym p
  n 411, +2,56 pp), women `handicap_cards_points_1h|OVER` nie (n 298 < 300).
  Krzywe przygotowane na nowym p czekają na decyzję sesji głównej.

## 4. E2E (zapisane dni 10-18, 10-20)

`process_fixture` z tabelami na żywo, przełącznik wył. / wł.: każdy wiersz
spoza połówek identyczny (122 / 122 i 41 / 41 meczów). Średnie |Δp|: 2. poł.
suma 0,056 (10-18) / 0,109 (10-20), 1. poł. suma 0,038 / 0,053, `penalties_for`
0,026 / 0,064, `red_cards_for` 0,009 / 0,012; sumy 1. połowy karnych /
czerwonych 0.

## Ryzyka

- Ten sam mnożnik całego meczu (sędzia, bliskość, GAME_STATE) w obu
  połowach – zmierzony tak; osobnych członów połówek nie ma.
- `rebuild_plan` nie zna znacznika: włączenie w zbudowany dzień wymaga
  ręcznego SHEET.
- `TEAM_M`, `GOALS_M` pomiaru – wybrane; β przewagi dopasowane na
  2025-08..02, nie dopasowywane ponownie.
- Rekordy zdarzeń pomiaru (pickle) sprzed poprawki −5 czerwonej (88cb8058):
  `red_cards_1h_*` w pomiarze mają ~1% stare liczenie; replay krzywych już
  na poprawionym kodzie.
