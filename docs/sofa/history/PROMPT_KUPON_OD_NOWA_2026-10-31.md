# Prompt na nową sesję - /kupon od nowa (2026-10-31)

Skopiuj wszystko poniżej linii do nowej sesji Claude Code w `/Users/mkoziol/projects/bet`.

---

Zaprojektuj od nowa, zaimplementuj i przetestuj `/kupon` (kupon z czatu: AKO na
okno godzin z kuponu dnia). Użyj workflow (wielu agentów równolegle) do partii
scenariuszy backtestu. Pracuj aż do końca: projekt → backtest setek wariantów →
wybór na danych walidacyjnych → jednorazowy hold-out → implementacja z testami →
E2E na prawdziwym dniu → raport. Narracja: linia na krok.

## Dlaczego od nowa

Obecny `/kupon` (`src/bet/sofa/slip_builder.py`, `scripts/sofa/build_slip.py`,
`.claude/commands/kupon.md`, skill `bet-slip-audit`) to stary knapsack pod cel
kursu z szansą nogi = min(pewność, 1/kurs). Przycięcie do ceny wyrzuciło
statystyki z wyboru: wszystkie nogi mają szansę = cenę, więc wygrywa cena i
marża. Skutek 31.10 wieczorem: kupony z karnymi poniżej 0.5 (`forecast_source:
league_rate`, próbka meczu 0 - ta sama liczba dla każdego meczu), Byfield
punkty w przewadze (próbka 0, pewność tylko z linii Superbetu), set siatkówki z
trafieniem próbki 50%, Bernau zwycięzca przy 4 meczach Hagen w próbce - a kurs
Bernau urósł przed startem z 1.52 do 1.65 (rynek szedł przeciw) i nikt tego nie
sprawdził. Operator: "pipeline powstał po to, aby głęboko analizować i bazować
na statystykach" - wieczór ma setki nóg ze statystykami (rożne, strzały,
celne, faule, kartki, spalone...), a kupon ich nie wybiera.

## Czego brakowało (zrób to)

Definicji "nogi mocnej statystycznie" i pomiaru, czy odróżnia dobrą nogę od złej
**przy tej samej cenie**. Dotąd sprawdzono tylko "pewność > cena + 3 pp" (bez
przewagi) - nie sprawdzono zgodności wielu niezależnych statystyk meczu.

## Materiał (rozliczone wyniki - dużo)

- Rozliczone wiersze arkusza: `sofa_settled_row` w `data/sofa.db` (każdy wiersz
  SHEET z oceną; dziesiątki tysięcy dziennie) - pracuj na kopii (`VACUUM INTO`
  do `data/kupon_redesign_<data>/`), nigdy na żywej bazie.
- Nogi dnia: `runs/sofa/<d>/08_confidence.json`, `08_confidence_sports.json`,
  `11_coupon.json` (pola: `confidence`, `offered_odds`, `forecast_p`,
  `forecast_source`, `model_p`, `sample_size`, `sample_hit_rate`,
  `calibrated_on`, `calibration_n`, `overround`, `market`, `line`,
  `direction`), wyniki `13_results.json`, ledger `runs/sofa/ledger/results.jsonl`;
  sporty: tabele SHADOW_SETTLE / CS2_SETTLE.
- Próbki `03_samples.json`, arkusz `05_sheet.json`, dossier (`bet.sofa.dossier`,
  offline z cache: forma, `style`, `style.matchup` - własne k/n vs co traci
  rywal / mecze obu drużyn / liczba ligi, h2h, sędzia, składy przed meczem).
- Ceny: wydruk poranny, `capture_closing.py` (zamknięcie), migawki SHADOW,
  `unmapped_prices/` - ruch ceny od wydruku do startu jest mierzalny.
- Poprzednie badanie (punkt wyjścia, nie powtarzaj go 1:1):
  `docs/sofa/evidence/slip_flow_backtest_2026-10-31.md`,
  `data/research_2026-10-31/flow/` (~133 reguły, nic nad zero po podatku;
  noga kuponu realizuje ~0.946 ceny, n 49 189), pamięć
  `slip-flow-and-second-price-2026-10-31`.

**Pułapka look-ahead:** dossier / matchup / forma dla dnia z przeszłości musi
brać tylko mecze sprzed startu meczu (as-of). Sprawdź to w kodzie dossier
i w teście; jeśli czyta "ostatnie 10" bez cięcia na start - dopisz cięcie as-of
do backtestu. Cena tylko sprzed startu (`fetched_at_utc` < start).

## Scenariusze - setki kombinacji

Wymiary (krzyżuj sensownie, licz każdą komórkę):
1. **Pula:** `forecast_source` (football_rating, tennis_rating, score_model,
   cs2_engine, player_model, league_rate), min. mecze w próbce każdej strony
   (0/5/8/10/15), sporty, rodziny rynków (liczbowe: rożne, strzały, celne,
   faule, kartki, spalone, auty, wykopy...; wynikowe; gracze; sety / mapy),
   kierunek OVER/UNDER, linia główna vs boczna, pasmo kursu, marża drabinki.
2. **Dowód nogi** - każdy sygnał względem 1/kurs: prognoza modelu, pewność,
   własna próbka strony A, strony B, co traci rywal (matchup), mecze obu drużyn,
   odsetek ligi, h2h, sędzia (kartki / faule), odpoczynek, zgodność kierunku
   linii przy cenach. Warianty: "wszystkie nad ceną", "k z n", ważona suma,
   minimalny zapas (0/2/5/10 pp), rozrzut sygnałów.
3. **Ruch ceny:** wydruk → zamknięcie; noga, której kurs urósł (rynek przeciw),
   wypada / nie wypada; próg ruchu.
4. **Ranking:** po sile dowodu, po zapasie nad ceną, po zgodności, po cenie (kontrola).
5. **Kupon:** 1-4 nogi, cel ~1.5 / ~2 / ~3 / ~4, jedna noga z meczu, mieszanie
   sportów vs jeden sport, maks. nogi jednego rynku, buildery (tak/nie),
   okna godzinowe (popołudnie / wieczór / noc).
6. **Kontrole:** losowy kupon z tej samej puli, obecny `/kupon`, same single.

## Metodologia (obowiązkowa - setki porównań = łatwo o fałszywe trafienie)

- Podział czasowy: dev 10-13..10-24 (szukanie), walidacja 10-25..10-28 (wybór
  1-3 kandydatów), hold-out 10-29..10-31 (+ 11-01, jeśli rozliczony) -
  **uruchomiony raz**, na końcu, po zamrożeniu reguł (zapisz je w pliku z
  hashem przed hold-outem).
- Miary: trafienie nogi vs 1/kurs w tym samym paśmie ceny (lift w pp),
  zwrot po podatku 12% (wypłata = 0.88 × stawka × iloczyn kursów; Bet Builder:
  0.90 × iloczyn), trafienie kuponu; przedziały bootstrap po meczach (nogi
  jednego meczu nie są niezależne), korekta wielokrotnych porównań (BH / liczba
  komórek podana w raporcie), min. n na komórkę (≥ 100 nóg) - mniejsze to
  "podejrzenie".
- Raportuj też to, co nie zadziałało (wszystkie komórki w tabeli / pliku).
- Liczby subagentów sprawdzaj lokalnie (pamięć: 18 błędów w jednym przebiegu).

## Implementacja (po wyborze)

- Nowy wybór w `slip_builder.py` / `build_slip.py`: pula ze statystyk meczu,
  dowód nogi w tabeli (kolumny ze wszystkimi sygnałami i 1/kurs obok),
  ranking po dowodzie, świeży kurs Superbetu tuż przed podaniem (noga z kursem
  wyżej niż w tabeli o próg z backtestu wypada; `OfferFetcher`, breaker
  szanowany), wykluczenie mikropróbek. Jeśli backtest nic nie potwierdzi -
  wdroż pulę + dowód + ruch ceny jako filtr jakości i powiedz wprost, że
  przewagi nad ceną nie ma.
- Zachowaj: nogi słowami Superbetu (`superbet_market: superbet_selection`),
  analitycy czytają każdą nogę (pętla z `bet-slip-audit`), "powiedz nie
  najpierw", linia zwrotu po podatku tylko zmierzona, nigdy kurs kuponu /
  buildera, brak stawki, brak "na minusie", brak "rodziny na plusie".
- Testy w `tests/sofa/` (offline), wpis w rejestrze
  (`check_test_registry.py`), bramki: pytest tests/sofa, ruff, mypy --strict
  --no-incremental, rejestr. Zaktualizuj `.claude/commands/kupon.md`, skill
  `bet-slip-audit`, CLAUDE.md (wiersz /kupon i reguła czatu), dokument PL w
  `docs/sofa/`. Kupon z czatu nie zmienia wydruku - bez epoki.
- E2E: odtwórz `/kupon 19:30-22:00` dla 2026-10-31 i porównaj z tym, co
  dostał operator (karne, Byfield, set, Bernau); potem żywy przebieg na
  bieżącym dniu (bridge: `ensure_bridge.py` najpierw).

## Raport końcowy

Po polsku, `docs/sofa/evidence/kupon_od_nowa_<data>.md`: projekt, liczba
przetestowanych komórek, tabela najlepszych i kontrolnych na dev / walidacji /
hold-oucie z przedziałami, co wdrożone i dlaczego, czego nie da się
obiecać. Pamięć: nowy plik + linia w MEMORY.md. Commit prosto na main (bez
push). Nie ruszaj cudzych niezacommitowanych plików
(`config/sofa_superbet_line_evidence.json`,
`docs/sofa/history/AUDYT_PIPELINE_2026-10-30.md`), nie używaj `git stash`.

Twarde zasady z CLAUDE.md obowiązują (Sofascore + Superbet only, nigdy
bzzoiro, nigdy `.env`, `MIN_INTERVAL_MS` bez zmian, żadnego refitu ani
instalacji krzywych bez zgody operatora).
