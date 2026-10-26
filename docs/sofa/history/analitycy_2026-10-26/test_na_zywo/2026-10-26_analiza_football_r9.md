# Analiza piłki nożnej 2026-10-26 — runda ponownego czytania (delta), r9

**Plik:** `read_set_football_live.json` (11 nóg: 2 mecze, wszystkie `required`, żadna nie zablokowana; 2 nogi Hajfy to nogi buildera B1). `11_coupon.json` epoch `stats_only`. Ceny z 2026-10-26 06:44Z (`04_offer.json`), migawka analizy 07:13-07:20Z.
**Najpierw przeczytaj:** od pełnego przejścia z 07:06Z nic się nie zmieniło: brak nowych absencji, brak przełożenia, skład Hajfy wciąż przewidywany, Paysandú bez składu. Wszystkie 11 nóg KEEP.

Tryb: **przejście delta**. Każda noga ma `prior_analysis`, a `full_pass_at_utc` = 07:06:27Z jest sprzed 7 minut (< 6 h). Dossier i ustalenia kontekstowe przejmuję z `2026-10-26_analiza_football_2.md` i szukam tylko tego, co mogło się zmienić od 07:06Z.

## Mecze

### Maccabi Haifa – Hapoel Be'er Sheva — Ligat ha'Al, 8. kolejka · sofa:16364276
**Start:** 2026-10-26 17:00Z (Superbet 17:00Z; FIXTURE_CHECK 17:00Z notstarted, sprawdzone 07:07:46Z) · **identity:** FUZZY (nazwy zgodne po porównaniu: „Maccabi Haifa” / „Hapoel Be'er Sheva”; nie nazywam tego potwierdzeniem) · nierozpoczęty o 07:13Z, do startu 9h47m.
**Punkt wyjścia:** pewność nóg 0.81 (rożne poniżej 11.5) i 0.88 (1. połowa poniżej 2.5). Oczekuję ~1.3 gola do przerwy i ~8.5 rożnego (dossier/próbki, [wcześniej: 2026-10-26_analiza_football_2.md, 07:06:27Z]).
**Fakty zabójcze (przed siecią):** nowa absencja stopera lub bramkarza po 07:06Z (gole w 1. połowie w górę), przełożenie lub zmiana godziny, rotacja Beer Szewy ogłoszona oficjalnie.

**Dossier.** [wcześniej: 2026-10-26_analiza_football_2.md, 07:06:27Z] Hajfa 1. (18 pkt), Beer Szewa 4. (16). Hajfa po 9 dniach przerwy; Beer Szewa po czwartkowej LE (0-4), 3 mecze w 14 dniach. H2H rożne 6, 8, 13, 17, 5, 8. Brak sędziego (nogi nie są kartkowe). Zmiany od 07:06Z: dossier przebudowane 07:12Z, ale `lineups` to ta sama odpowiedź Sofascore z 06:49:54Z (`confirmed: false`, przewidywany). Brak `line_moves`. Stadion Sammy Ofer, Hajfa, 19:00 czasu lokalnego.
**Próbka.** [wcześniej] Gole w 1. połowie >= 3: Hajfa 2/10, Beer Szewa 1/10. Próbka nogi to 17/20 (0.85). Rożne: Hajfa 6-13 (mediana 8), Beer Szewa 4-15, U11.5 18/20 (0.90). W 1. połowie rynek rożnych nie jest użyty. Kod już zdjął goals_for Hajfy U2.5 i rożne Beer Szewy U5.5 (MODEL_ABOVE_OWN_SAMPLE); tego nie powtarzam.
**Kontekst (web).** Delta, 2 wywołania. (1) Wyszukiwanie po hebrajsku: absencje i przewidywany skład. Najświeższy znaleziony tekst o kontuzjach Hajfy to zapowiedź meczu z Maccabi Tel Awiw [WEB: sport1.maariv.co.il, publ. 2026-04-24 09:38, fetched 2026-10-26 07:16Z]: Gorah, Ohana, Don. Ma pół roku, nie dotyczy dzisiejszego meczu. (2) Pobrałem ten artykuł, żeby sprawdzić datę: nieaktualny. Brak nowej absencji, przełożenia czy oficjalnej rotacji od 07:06Z. Nic istotnego dla tych nóg.
**Scenariusz.** [wcześniej] Modalny D (wyrównany, 1-1 / 2-1). Builder B1 zabija szybki wysoki wynik do przerwy, po którym goniąca drużyna oblega bramkę (A z 3-1 / 4-2).

**Nogi.**
- 1.połowa - liczba goli: poniżej 2.5 — KEEP: ~1.3 gola do przerwy, 3+ do przerwy w 2/10 i 1/10. Delta pusta.
- Liczba rzutów rożnych: poniżej 11.5 — KEEP: ~8.5 rożnego, 18/20 poniżej linii. Delta pusta.
- Builder B1 (obie nogi): wspólny mechanizm to tempo. `combined_probability` 0.7083 to prawdopodobieństwo, nie cena; kurs buildera sprawdź na ekranie Superbetu.

**Za / Przeciw:** FAKT rożne obu stron ~8 → RACHUNEK 18/20 poniżej 11.5 → IMPLIKACJA noga stoi → RYZYKO oblężenie po wczesnym golu (2/20 meczów > 11). Przeciw: FAKT Hajfa 6/10 meczów z 4+ golami → RACHUNEK model 3.22 gola w meczu → IMPLIKACJA ogon goli istnieje, ale do przerwy rzadko 3+ → RYZYKO umiarkowane.

### Paysandú FC – Colón FC — Segunda División Uruguay, 24. kolejka · sofa:17371072
**Start:** 2026-10-26 23:30Z (Superbet 23:30Z; FIXTURE_CHECK 23:30Z notstarted, sprawdzone 07:07:57Z) · **identity:** CONFIRMED · nierozpoczęty o 07:13Z, do startu 16h17m (20:30 czasu Montevideo).
**Punkt wyjścia:** pewność nóg 0.70-0.89. Oczekuję 2.33 gola (Paysandú 1.48 / Colón 0.85) [wcześniej: 2026-10-26_analiza_football_2.md, 07:06:27Z]. Rating widzi Paysandú, drabina Superbetu Colón.
**Fakty zabójcze (przed siecią):** przełożenie lub strajk (w tym sezonie była już zawieszona kolejka), absencja napastnika Paysandú (gol Paysandú, 1X, +1.5), mecz 0-0 lub 1-0 (nogi „lub powyżej 1.5”, 2. połowa z golem).

**Dossier.** [wcześniej] Paysandú 11. (35 pkt, walczy o utrzymanie), Colón 5. (45). Paysandú u siebie 2-2-1; Colón 3-0 i 3-1 w dwóch ostatnich. Odpoczynek 9.3 / 10 dni. H2H 07.2026 3-2, 03.2026 0-2. Zmiany od 07:06Z: skład wciąż NOT_PUBLISHED (zapytanie 06:49:54Z). Brak sędziego, brak stadionu, brak `line_moves`.
**Próbka.** [wcześniej] Gol Paysandú w 7/10 (0 w 3/10). 2. połowa z golem 15/20 (0.75). Próbka Colónu na 2. połowie zawiera 3 mecze Copa Uruguay; rynek nie ma reguły ligowej dla tej metryki, więc to nie defekt. Rynki wynikowe (handicap, „lub”, podwójna szansa) nie mają próbki i są oceniane na scenariuszu.
**Kontekst (web).** Delta, 2 wyszukiwania. (1) Mecz w 24. kolejce, poniedziałek: wynikają tylko wcześniejsze spotkania (0-2 na otwarcie, 3-2 na Parque Palermo) i stara tabela [WEB: montevideo.com.uy, publ. 2026 (różne), fetched 07:17Z]. (2) Zapytanie o zawieszenie / przełożenie w październiku: brak takiej wiadomości. Wcześniej w sezonie jedna kolejka była wstrzymana strajkiem Mutual [WEB: montevideo.com.uy, publ. wcześniej w 2026, fetched 07:18Z]. To stary fakt, nic nie wskazuje na powtórkę. Absencji nie znalazłem; Segunda División nie publikuje składów przed meczem (UNVERIFIED). Nic istotnego dla tych nóg.
**Scenariusz.** [wcześniej] Rozbieżność rating / drabina = scenariusz nieważony. Zabija go wygrana Colónu 2-0 (Paysandú +1.5, 1X, gol Paysandú) albo 1-0 dla któregokolwiek z remisowo-niskim przebiegiem (nogi „lub powyżej 1.5”).

**Nogi.**
- Handicap: Paysandú FC (+1.5) — KEEP: przegrywa tylko przy porażce 2+ golami; h2h 3-2 / 0-2. Delta pusta.
- Mecz lub liczba goli: Paysandú FC lub powyżej 1.5: Tak — KEEP: oczekiwane 2.33 gola. Delta pusta.
- Mecz lub liczba goli: Paysandú FC lub poniżej 2.5: Tak — KEEP: zabija tylko 3+ gole bez wygranej Paysandú. Delta pusta.
- Mecz lub liczba goli: Colón FC lub powyżej 1.5: Tak — KEEP: zabija tylko 1-0 / 0-0 / 1-1 bez wygranej Colónu. Delta pusta.
- Mecz lub liczba goli: remis lub powyżej 1.5: Tak — KEEP: zabija tylko 1-0 / 0-1. Delta pusta.
- 2.połowa - liczba goli: powyżej 0.5 — KEEP: 15/20 meczów z golem w 2. połowie. Delta pusta.
- Podwójna szansa: 12 (Paysandu FC lub Colon FC) — KEEP: zabija remis. Delta pusta.
- Podwójna szansa: 1X (Paysandu FC lub remis) — KEEP: flaga `price_gap`; takie nogi realizowały się około ceny (1/1.47 = 0.68), nie pewności. Delta pusta.
- Paysandu FC - liczba goli: powyżej 0.5 — KEEP: 1.48 oczekiwanego gola u siebie, 7/10. Delta pusta.

**Za / Przeciw:** FAKT Paysandú strzela w 7/10, u siebie 2-2-1 → RACHUNEK oczekiwane 1.48 → IMPLIKACJA nogi Paysandú stoją na próbce i ratingu → RYZYKO Colón 5. i w formie (3-0, 3-1), drabina Superbetu wskazuje Colón. Rozbieżności z ceną nie traktuję jako argumentu.

## Zdjęte

Brak.

## Czego zabrakło

- Hajfa: brak potwierdzonego XI (Sofascore przewidywany z 06:49Z; potwierdzony ~1 h przed 17:00Z). Bieżącej zapowiedzi meczu po hebrajsku nie znalazłem w wynikach wyszukiwania; jedyny trafiony artykuł był z kwietnia.
- Paysandú: skład NOT_PUBLISHED, brak zapowiedzi meczu w sieci, brak tabeli z 24. kolejki z sieci (tabela z dossier).
- Pogody nie sprawdzałem w delcie: nie ma prognozy skrajnej w poprzednim przejściu ani żadnego tropu.

## NIE PODANO

- Sędziowie obu meczów (brak w dossier; nogi nie są kartkowe ani faulowe).
- Absencje Paysandú i Colónu: UNVERIFIED (liga bez publicznych składów przed meczem).

```json vetoes
[]
```

```json reads
[
{"sofascore_event_id": 16364276, "market": "goals_1h_total", "subject": "", "line": 2.5, "direction": "UNDER", "verdict": "KEEP", "author": "analyst", "reason": "1. połowa: oczekuję ~1.3 gola, 3+ do przerwy w 2/10 (Hajfa) i 1/10 (Beer Szewa); dossier: Hajfa 1., Beer Szewa po LE, skład przewidywany 06:49Z; delta 07:16Z: brak nowych absencji ani przełożenia [WEB: sport1.maariv.co.il, publ. 2026-04-24, fetched 07:16Z - nieaktualne]; nic istotnego"},
{"sofascore_event_id": 16364276, "market": "corners_total", "subject": "", "line": 11.5, "direction": "UNDER", "verdict": "KEEP", "author": "analyst", "reason": "rożne: oczekuję ~8.5 (mediany 8 / 8), 18/20 poniżej 11.5; dossier: h2h rożne 6, 8, 13, 17, 5, 8, brak line_moves; delta 07:16Z: brak nowej absencji, rotacji ani przełożenia; nic istotnego dla tej nogi"},
{"sofascore_event_id": 17371072, "market": "result_handicap", "subject": "1", "line": 1.5, "direction": "OVER", "verdict": "KEEP", "author": "analyst", "reason": "oczekuję 1.48 : 0.85 gola, Paysandú +1.5 przegrywa tylko porażką 2+; dossier: h2h 3-2 i 0-2, Paysandú u siebie 2-2-1; delta 07:18Z: brak przełożenia i absencji [WEB: montevideo.com.uy, fetched 07:18Z]; nic istotnego"},
{"sofascore_event_id": 17371072, "market": "result_or_over", "subject": "1", "line": 1.5, "direction": "OVER", "verdict": "KEEP", "author": "analyst", "reason": "oczekuję 2.33 gola w meczu, przegrywa tylko 0-0 / 0-1 / 1-1 bez wygranej Paysandú; dossier: Paysandú 11., odpoczynek 9.3 dnia; delta 07:18Z: brak przełożenia ani absencji, nic istotnego"},
{"sofascore_event_id": 17371072, "market": "result_or_under", "subject": "1", "line": 2.5, "direction": "OVER", "verdict": "KEEP", "author": "analyst", "reason": "oczekuję 2.33 gola, przegrywa tylko 3+ gole bez wygranej Paysandú; dossier: Paysandú u siebie 2-2-1, h2h 3-2 / 0-2; delta 07:18Z: brak przełożenia ani absencji, nic istotnego"},
{"sofascore_event_id": 17371072, "market": "result_or_over", "subject": "2", "line": 1.5, "direction": "OVER", "verdict": "KEEP", "author": "analyst", "reason": "oczekuję 2.33 gola, przegrywa tylko 0-0 / 1-0 / 1-1 bez wygranej Colónu; dossier: Colón 5., 3-0 i 3-1 w ostatnich dwóch; delta 07:18Z: brak przełożenia ani absencji, nic istotnego"},
{"sofascore_event_id": 17371072, "market": "result_or_over", "subject": "X", "line": 1.5, "direction": "OVER", "verdict": "KEEP", "author": "analyst", "reason": "oczekuję 2.33 gola, przegrywa tylko 1-0 / 0-1; dossier: h2h 3-2 i 0-2, odpoczynek 9.3 / 10 dni; delta 07:18Z: brak przełożenia ani absencji, nic istotnego dla tej nogi"},
{"sofascore_event_id": 17371072, "market": "goals_2h_total", "subject": "", "line": 0.5, "direction": "OVER", "verdict": "KEEP", "author": "analyst", "reason": "2. połowa: oczekuję ~1.3 gola, 15/20 meczów z golem po przerwie; dossier: Colón 3-0 i 3-1, Paysandú u siebie 2-2-1; delta 07:18Z: brak przełożenia ani absencji, nic istotnego"},
{"sofascore_event_id": 17371072, "market": "double_chance", "subject": "12", "line": 0.5, "direction": "OVER", "verdict": "KEEP", "author": "analyst", "reason": "oczekuję 1.48 : 0.85 gola, przegrywa tylko remis; dossier: Paysandú walczy o utrzymanie, Colón 5.; delta 07:18Z: brak przełożenia ani absencji, nic istotnego dla tej nogi"},
{"sofascore_event_id": 17371072, "market": "double_chance", "subject": "1X", "line": 0.5, "direction": "OVER", "verdict": "KEEP", "author": "analyst", "reason": "oczekuję 1.48 : 0.85 gola; price_gap: takie nogi realizowały się ~przy cenie (1/1.47 = 0.68), nie przy pewności; dossier: Paysandú u siebie 2-2-1; delta 07:18Z: nic istotnego"},
{"sofascore_event_id": 17371072, "market": "goals_for", "subject": "paysandu fc", "line": 0.5, "direction": "OVER", "verdict": "KEEP", "author": "analyst", "reason": "gole Paysandú: oczekuję 1.48 u siebie, gol w 7/10 meczów próbki; dossier: h2h 3-2 / 0-2, odpoczynek 9.3 dnia; delta 07:18Z: brak absencji napastnika, nic istotnego"}
]
```
