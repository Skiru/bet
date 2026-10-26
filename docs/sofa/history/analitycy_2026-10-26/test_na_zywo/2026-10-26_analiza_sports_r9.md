# Analiza sportów mierzonych — 2026-10-26 — runda ponownego odczytu r9 (hokej, siatkówka)

**Pliki:** `read_set_hockey_live.json` (11 nóg, required), `read_set_volleyball_live.json` (3 nogi, required); `11_coupon.json` epoch `stats_only`; nóg przeczytanych 14/14 (required 14, buffer 0, operator 0), 2 mecze, zablokowanych 0. Zrzut Superbetu: 07:07Z (drugi zrzut dnia, po 04:52Z). `UNFITTED_CONSTANTS` na każdej nodze (m.in. MIN_OFFSET_ROWS, PRICE_BANDS, MIN_EVIDENCE_BUCKET) — liczby pewności niosą niedopasowane stałe.
**Najpierw:** obie analizy to **delta pass** — pełny przegląd z sieci zrobiono o 07:06:27Z (`prior_analysis.full_pass_at_utc`, < 6 h temu); od tego czasu nic się nie zmieniło: ceny nóg bez ruchu, bramkarze NHL wciąż „Unconfirmed”, brak wiadomości o składzie w siatkówce. Wszystkie nogi KEEP; w hokeju 11 nóg to jeden scenariusz (wysoki wynik Toronto).

## Mecze

### Calgary Flames – Toronto Maple Leafs — NHL · sofa:16550635
**Start:** 2026-10-27 00:30Z (noga 00:30Z, sport_fixtures 00:30Z, start_gap_h 0.0, FIXTURE_CHECK `notstarted` 00:30Z sprawdzone 07:08Z) · teraz 07:13Z, delta ~17.3 h · `source_date` 2026-10-27 (okno `late`)
**Tożsamość:** IDENTIFIED (LISTING_ID_AND_NAME), „Calgary Flames·Toronto Maple Leafs” = „Calgary Flames - Toronto Maple Leafs”, name_scores 100/100, home_is_team1 true (T1 = Calgary), turniej NHL.
**Cena:** zrzuty 04:52Z i 07:07Z, 131 linii w obu, **0 zmian** (porównanie linia po linii); żadna grupa nóg nie zniknęła ani nie jest zawieszona.
**Punkt wyjścia:** pewność 0.72–0.85. [wcześniej: 2026-10-26_analiza_hockey.md, 2026-10-26T07:06:27Z] oczekiwanie z dossier `avg_periods`: 1. tercja ~2.0 gola, 3. tercja ~2.2; Toronto w 3. tercji ~1.4, w 1. ~1.1; Calgary w 1. ~0.9, w 2. ~1.2.
**Fakty zabójcze (przed siecią):** potwierdzony bramkarz awaryjny/trzeci Calgary zamiast Cooleya/Wolfa (UNDER-y Toronto, Calgary +1.5, UNDER-y tercji); Farabee poza składem lub poza PP1; przełożenie.

**Dossier.** [wcześniej: 2026-10-26_analiza_hockey.md] — forma, odpoczynek (brak back-to-back; Toronto 3 mecze w 7 dni, w podróży na zachodzie), h2h (Toronto 6-0, 2× +3 w 2. tercji) bez zmian. Zmieniło się: dossier przebudowane 07:12Z, `market.moved` 0; skład Sofascore nadal NOT_PUBLISHED (pytany 06:49Z).

**Kontekst (web).** Delta pass (1 pobranie): starterzy — Calgary Devin Cooley, Toronto Sergei Bobrovsky, oba nadal „Unconfirmed”, 0 z 6 potwierdzonych na 26.10 [WEB: dailyfaceoff.com, publ. 2026-10-26 (bez znacznika czasu), fetched 2026-10-26 07:14Z] — to samo co o 06:52Z. Cooley to bramkarz tandemu, nie awaryjny [wcześniej: 2026-10-26_analiza_hockey.md, 07:06:27Z]. Poranny trening Calgary (~10:30 czasu lokalnego = ~16:30Z) jeszcze się nie odbył — linie/PP z 10-25 (Farabee PP1, 1. linia) pozostają najnowsze. Brak wiadomości o przełożeniu. Nic istotnego dla tych nóg; bramkarz do potwierdzenia wieczorem (re-read po ~17:00Z ma sens dla nóg zależnych od bramkarza).

**Nogi.**
- 3. tercja - Toronto Maple Leafs - liczba goli: poniżej 2.5 — KEEP: ~1.4 gola Toronto w 3. tercji, bramkarz tandemu, bez zmian od 07:06Z.
- 1. tercja - handicap: Calgary Flames (1.5) — KEEP: przegrywa tylko przy Toronto +2 w 1. tercji (~1.1 vs 0.9 oczekiwane).
- Zawodnik - liczba punktów w przewadze (z dogrywką): Joel Farabee - poniżej 0.5 — KEEP: PP1 i 1. linia wg DailyFaceoff 10-25 — rola, na której opiera się `sb:hockey:player_pp_points|UNDER`; nic nowszego.
- 1. tercja - liczba goli: powyżej 0.5 — KEEP: ~2.0 gola, P(0) ≈ 0.14 (Poisson z `avg_periods`).
- 2. tercja - handicap: Calgary Flames (1.5) — KEEP: najsłabsza z trzech (Toronto 1.9 w 2. tercji), bez faktu przeciw.
- 3. tercja - handicap: Calgary Flames (1.5) — KEEP: Toronto 1.3 zdob. w 3. tercji; brak faktu.
- 3. tercja - liczba goli: poniżej 3.5 — KEEP: ~2.2 oczekiwane; 4+ w 3. tercji 3/18 ligowych.
- 1. tercja - Calgary Flames liczba goli: poniżej 1.5 — KEEP: ~0.9 oczekiwane.
- 1. tercja - liczba goli: poniżej 2.5 — KEEP: ~2.0 oczekiwane; ogon 3+ bez faktu.
- 2. tercja - Calgary Flames liczba goli: poniżej 1.5 — KEEP: ~1.2, blisko linii, bez faktu.
- 1. tercja - Toronto Maple Leafs - liczba goli: poniżej 1.5 — KEEP: ~1.1 oczekiwane.

**Ekspozycja:** 1. tercja handicap Calgary (1.5) i 1. tercja Toronto poniżej 1.5 to w dużej części jeden zakład; podobnie trzy nogi 3. tercji (Toronto <2.5, <3.5, Calgary +1.5). Wszystkie 11 nóg pada w tym samym scenariuszu (Toronto wysoko przy słabym bramkarzu Calgary). Noga Parekha z poprzedniej analizy nie jest w tym pliku ani w `singles` kuponu — nie czytana.

### Sancor Seguros Vôlei Londrina – Sesi Vôlei Bauru — Brazylia, Superliga (K) · sofa:17276105
**Start:** 2026-10-26 21:30Z (noga 21:30Z, sport_fixtures 21:30Z, start_gap_h 0.0, FIXTURE_CHECK `notstarted` 21:30Z sprawdzone 07:08Z) · teraz 07:13Z, delta ~14.3 h
**Tożsamość:** IDENTIFIED (LISTING_ID_AND_NAME), „Sancor Seguros (K)” = „Sancor Seguros Vôlei Londrina”, „SESI Bauru (K)” = „Sesi Vôlei Bauru”, 100/100, home_is_team1 true, oba kobiece, „Superliga, Women” (Sancor = dawne Maringá przeniesione do Londriny [wcześniej: 2026-10-26_analiza_volleyball.md]).
**Cena:** zrzuty 04:52Z i 07:07Z; 13 drobnych ruchów (o 0.01–0.05, np. 2:3 5.60→5.55, 3:2 9.8→10.0, „dokładnie 2 sety: Tak” 5.15→5.10) — ceny trzech nóg bez zmian (1.12 / 1.30 / 1.51). Ruch bez znaczenia, nie werdykt.
**Punkt wyjścia:** pewność 0.77–0.83; [wcześniej: 2026-10-26_analiza_volleyball.md, 07:06:27Z] oczekuję wygranej Bauru, modalnie 0:3 lub 1:3 dla Sancor (Bauru 2.9/1.1 setu śr. z 10; h2h Bauru 6-0, 3:0 ×4).
**Fakty zabójcze (przed siecią):** ogłoszony uraz/odpoczynek atakującej, rozgrywającej lub przyjmującej Bauru (podnosi 2:3 → bije „dokładnie 2 sety: Nie”) albo Sancor (podnosi 0:3 → bije handicap +2.5); przełożenie.

**Dossier.** [wcześniej: 2026-10-26_analiza_volleyball.md] — forma (Sancor 2:3 z Fluminense 20.10; Bauru 9/10, 3:0 z Mackenzie 19.10), odpoczynek 6–7 dni, h2h bez zmian. Zmieniło się tylko `market.moved` 13 (drugi zrzut, ruchy jak wyżej). Składy: dossier `lineups.missing` (siatkówka).

**Kontekst (web).** Delta pass (2 wyszukiwania): urazy / absencje obu drużyn — nic z sezonu 2026/27; trafienia to poprzednie sezony (kontuzja Pri Daroit, operacja Dani Lins — nie dotyczą października 2026) [WEB: itatiaia.com.br / volleyballworld.com, publ. 2025-26, fetched 2026-10-26 07:15Z]. Termin: Superliga ruszyła 17.10, 1. tura do 20.12; Sancor grał 1. kolejkę 20.10, Bauru 19.10, następny mecz Bauru 30.10 z Fluminense [WEB: netflu.com.br / lance.com.br, publ. ok. 2026-10, fetched 07:16Z] — mecz 26.10 pasuje do 2. kolejki, brak CEV/pucharu w tym tygodniu, brak powodu rotacji; samej daty 26.10 sieć nie potwierdza osobno (Sofascore, Superbet i FIXTURE_CHECK zgodnie 21:30Z). Szóstka `UNVERIFIED`. Nic istotnego dla tych nóg.

**Nogi.**
- Sancor Seguros (K) wygra dokładnie 2 sety: Nie — KEEP: przegrywa tylko na 2:3; przy oczekiwanym 0:3/1:3 i bez absencji nic nie podnosi tie-breaka.
- Sancor Seguros (K) wygra dokładnie 1 set: Nie — KEEP: przegrywa na 1:3 (h2h 2/6) — ryzyko w rozkładzie, nie wada nogi.
- Handicap setowy: Sancor Seguros (K) (2.5) — KEEP: wygrywa, gdy Sancor weźmie ≥1 set; 0:3 w 4/6 h2h to rozkład, który model zawiera; brak faktu.

**Ekspozycja:** trzy nogi pokrywają rozłączne wyniki przeciwstawnie (0:3 bije handicap +2.5, 1:3 bije „1 set: Nie”, 2:3 bije „2 sety: Nie”); wszystkie trzy razem wygrywają tylko przy wygranej Sancor.

## Zdjęte

Brak — 14 × KEEP.

## Czego zabrakło

- Hokej: potwierdzony starter obu drużyn (DailyFaceoff „Unconfirmed”, Rotowire bez tego meczu wg poprzedniej analizy) — `UNVERIFIED`; poranny trening Calgary jeszcze się nie odbył; druga domena dla linii/PP Farabee brak.
- Siatkówka: szóstka (nie publikuje się przed meczem) — `UNVERIFIED`; data 26.10 nie potwierdzona w sieci osobno.

## NIE PODANO

- Nie pytano Sofascore ponownie o skład NHL (praca analityka nie uruchamia pipeline'u); `lineups_prematch.json` z 06:49Z NOT_PUBLISHED.

```json vetoes
[]
```

```json reads
[
{"sofascore_event_id": 16550635, "market": "period_team_total", "subject": "T2", "line": 2.5, "direction": "UNDER", "period": 3, "verdict": "KEEP", "author": "analyst", "reason": "oczekuję ~1.4 gola Toronto w 3. tercji (dossier avg_periods: TOR 1.3 zdob. × CGY 1.5 strac.); bramkarze nadal Unconfirmed, Cooley to bramkarz tandemu [WEB: dailyfaceoff.com, fetched 07:14Z]; delta: nic istotnego, ceny bez ruchu"},
{"sofascore_event_id": 16550635, "market": "period_handicap", "subject": "", "line": 1.5, "direction": "T1", "period": 1, "verdict": "KEEP", "author": "analyst", "reason": "przegrywa tylko przy Toronto +2 w 1. tercji; oczekiwane ~1.1 vs 0.9 (dossier), taki wynik 3/18 ligowych; delta: bramkarze Unconfirmed bez zmian [WEB: dailyfaceoff.com, fetched 07:14Z], nic istotnego"},
{"sofascore_event_id": 16550635, "market": "player_pp_points", "subject": "Joel Farabee", "line": 0.5, "direction": "UNDER", "period": 0, "verdict": "KEEP", "author": "analyst", "reason": "Farabee PP1 i 1. linia (DailyFaceoff 10-25) - rola, którą wycenia sb:hockey:player_pp_points|UNDER; Calgary w dossier 2.5 gola śr.; delta: brak nowej wiadomości o składzie przed porannym treningiem"},
{"sofascore_event_id": 16550635, "market": "period_total", "subject": "", "line": 0.5, "direction": "OVER", "period": 1, "verdict": "KEEP", "author": "analyst", "reason": "oczekuję ~2.0 gola w 1. tercji (dossier avg_periods), P(0)≈0.14, 0:0 w 1. tercji 1× w dossier; delta: nic istotnego, ceny bez ruchu 04:52Z→07:07Z"},
{"sofascore_event_id": 16550635, "market": "period_handicap", "subject": "", "line": 1.5, "direction": "T1", "period": 2, "verdict": "KEEP", "author": "analyst", "reason": "Toronto w 2. tercji najmocniejsze (1.9 zdob. śr., dossier), h2h 2× +3 - najsłabsza noga, ale bez faktu przeciw; delta: bramkarze Unconfirmed, nic istotnego"},
{"sofascore_event_id": 16550635, "market": "period_handicap", "subject": "", "line": 1.5, "direction": "T1", "period": 3, "verdict": "KEEP", "author": "analyst", "reason": "Toronto 1.3 zdob. w 3. tercji vs Calgary 1.5 strac. (dossier), oczekiwana różnica <1 gola; delta: nic istotnego, ceny bez ruchu"},
{"sofascore_event_id": 16550635, "market": "period_total", "subject": "", "line": 3.5, "direction": "UNDER", "period": 3, "verdict": "KEEP", "author": "analyst", "reason": "oczekuję ~2.2 gola w 3. tercji (dossier), 4+ w 3/18 ligowych; delta: bramkarz Calgary nadal Cooley Unconfirmed [WEB: dailyfaceoff.com, fetched 07:14Z], nic istotnego"},
{"sofascore_event_id": 16550635, "market": "period_team_total", "subject": "T1", "line": 1.5, "direction": "UNDER", "period": 1, "verdict": "KEEP", "author": "analyst", "reason": "Calgary 0.7 zdob. śr. w 1. tercji (dossier), oczekuję ~0.9 vs linia 1.5; delta: nic istotnego, ceny bez ruchu"},
{"sofascore_event_id": 16550635, "market": "period_total", "subject": "", "line": 2.5, "direction": "UNDER", "period": 1, "verdict": "KEEP", "author": "analyst", "reason": "oczekuję ~2.0 gola w 1. tercji (dossier avg_periods); 3+ to ogon bez faktu; delta: bramkarze Unconfirmed bez zmian, nic istotnego"},
{"sofascore_event_id": 16550635, "market": "period_team_total", "subject": "T1", "line": 1.5, "direction": "UNDER", "period": 2, "verdict": "KEEP", "author": "analyst", "reason": "oczekuję ~1.2 gola Calgary w 2. tercji (1.0 zdob., Toronto traci 1.4 - dossier), blisko linii; delta: nic istotnego"},
{"sofascore_event_id": 16550635, "market": "period_team_total", "subject": "T2", "line": 1.5, "direction": "UNDER", "period": 1, "verdict": "KEEP", "author": "analyst", "reason": "oczekuję ~1.1 gola Toronto w 1. tercji, 2+ w 3/10 (dossier); delta: Cooley Unconfirmed, bez zmian [WEB: dailyfaceoff.com, fetched 07:14Z], nic istotnego"},
{"sofascore_event_id": 17276105, "market": "team_sets_exact", "subject": "T1", "line": 2.0, "direction": "NO", "period": 0, "verdict": "KEEP", "author": "analyst", "reason": "oczekuję 0:3/1:3 dla Sancor (Bauru 2.9/1.1 setu śr., h2h 6-0 - dossier); przegrywa tylko na 2:3; delta: brak absencji w sezonie 2026/27, brak CEV w tygodniu [WEB: netflu.com.br, fetched 07:16Z]"},
{"sofascore_event_id": 17276105, "market": "team_sets_exact", "subject": "T1", "line": 1.0, "direction": "NO", "period": 0, "verdict": "KEEP", "author": "analyst", "reason": "przegrywa na 1:3 (h2h 2/6, dossier) - ryzyko rozkładu, nie wada; oczekiwane 0:3 modalnie; delta: nic istotnego o składach [WEB: itatiaia.com.br, fetched 07:15Z]"},
{"sofascore_event_id": 17276105, "market": "set_handicap", "subject": "", "line": 2.5, "direction": "T1", "period": 0, "verdict": "KEEP", "author": "analyst", "reason": "wygrywa przy ≥1 secie Sancor; Sancor wziął 2 sety Fluminense 20.10, z Bauru 0:3 w 4/6 h2h (dossier) - rozkład w modelu; delta: nic istotnego, cena 1.51 bez ruchu"}
]
```
