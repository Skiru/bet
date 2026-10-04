# Noc 3/4.10.2026 — raport dla operatora

*(wersja końcowa, 04:25Z 2026-10-04; dowody i skrypty w `data/night_2026-10-03/<temat>/`, narzędzia nocy w `data/night_2026-10-03/tools/`)*

## Najważniejsze w trzech zdaniach

1. **Kupon trafia dokładnie tyle, ile mówi cena rynkowa.** Na 64 tys. wycenionych i rozliczonych
   wierszy (09-17..10-02) reguła oficjalna drukuje pewność ~0.805, realnie trafia 0.745, a
   zdewigowana cena mówiła 0.742 — więc ROI ≈ marża (−4%). CLV 10-02/03: oficjalny −4.47%
   [−5.00; −3.91], kursy do zamknięcia prawie się nie ruszają. Żadna reguła selekcji (ani w piłce,
   ani w tenisie, ani w czterech sportach mierzonych) nie przebiła marży poza próbą.
2. **Propsy graczy: nie ma gdzie na nich zarobić — rekomendacja: zdjąć wszystkie 7 z
   `admitted_player_markets`.** W ciemno −45.8%, każdy rynek, każdy przedział kursu, każda liga na
   minusie; Superbet wycenia je bez związku z rzeczywistością (np. rezerwowy „powyżej 0.5 strzału”
   po 1.003). Mapowanie sprawdzone na żywej ofercie — to nie nasz błąd.
3. **Sporty mierzone (hokej, kosz, siatka, CS2) nie są gotowe do głównego kuponu.** Dwóch
   kandydatów do formalnego testu: handicap w koszykówce (b = +0.55 [+0.13; +1.11]) i suma goli w
   hokeju. Proponuję z góry zarejestrowane kryterium przyjęcia (niżej) — najwcześniej ~10-09..10-18.

## Co weszło na main tej nocy (wszystko z testami; pytest/mypy zielone)

| commit | co | wpływ na jutrzejszy dzień |
|---|---|---|
| f019519b | `gap_shrink_k` — korekta pewności o odległość od ceny | **wyłączona** (decyzja operatora) |
| bf10f06c | noga z p < 0.60 nigdy nie drukuje się przez dolny kubełek krzywej | zabezpieczenie; 0 zmian na 09-20..10-03 |
| c2350786 | odtworzenie połówek z cache (opt-in), cienkie kubełki ograniczają pulę, strumieniowy replay i fit K | dopiero od następnego refitu |
| dee958dd, fc9dba0e, 236147ad | strażnik `ZERO_NOT_RECORDED` — 0-0, które feed pokazuje jako niezliczone, nie jest obserwacją ani podstawą rozliczenia | **tak**: próbki, rating, SETTLE; pierwszy SHEET przeparsuje historię (~10 min) |
| e859d97f | 851 (towarzyskie reprezentacji) + 6 innych id na liście towarzyskich | **tak**: nogi 851 odrzucane jako FRIENDLY_FIXTURE |
| 57b80635, 953adf45 | model siatkówki + narzędzia pomiaru sportów mierzonych | tylko pomiar |
| 2e7846c3, ff2a7c4c | skrypty refitu tenisa; **zainstalowane** nowe `sofa_tennis_tier_baselines.json` | **tak**: ITF games_total −1.3 gema (stary plik sprzed poprawki tiebreaka) |
| 03dfec96 | SHADOW_SETTLE: lepsze dopasowanie meczów | rozliczenia sportów mierzonych |
| dd76a9d4 | poprawki z przeglądu: replay commituje partiami, `--calibration` nie nadpisze prawdziwego dnia | brak |
| 67777ec7 | SHADOW_SETTLE: orientacja meczu z pary, która go potwierdziła (2. runda przeglądu) | rozliczenia sportów mierzonych |
| (41ef5edb) | **kartki tylko z prawdziwego zapisu kartek**: w niepełnych feedach lista incydentów bez zmian zawiera same czerwone — mecz z 7 kartkami liczył się jako 2 pkt (4 338 meczów); przywrócone prawdziwe 0-0 spalonych/żółtych, które feed z połowami pomija (1 554 + 727 meczów — próbki były zawyżone); „dokładnie 1 rożny” w niepełnym feedzie odrzucany (970 vs oczekiwane 70) | **tak**: próbki i rozliczenia kartek/spalonych/rożnych; HISTORY_PARSER_VERSION 2026-10-04.2 |

**Dyskusyjne w 41ef5edb:** kartki 0-0 w niepełnym feedzie bez zmian w incydentach są odrzucane,
choć ok. 30% z nich (≈760 z 2 517) to prawdopodobnie prawdziwe 0-0. Uzasadnienie: w tym feedzie
0-0 zawsze daje wartość, a mecz z kartkami tylko w ~1/4 przypadków — więc bez reguły 32% wartości
kartek z tego feedu to zera. Do przejrzenia.

**Weryfikacja na żywo:** dzień 10-04 zbudowany w nocy (23:11–23:27Z) nowym kodem w katalogu
tymczasowym (prawdziwy `runs/sofa/2026-10-04` nietknięty): BOARD 804 → RESOLVE 706 (recall 87.8%)
→ SHEET → COUPON → CONFIDENCE (111 singli / WARIANT 663) → oba PDF. Weryfikator: arytmetyka
odtwarza się co do 1e-4, 123/123 cen oficjalnych bez zmian przy ponownym zapytaniu, żadna noga po
złej stronie, 0 nóg towarzyskich, strażnik zer zadziałał 22 razy. Jedno podejrzane 0-0 w rożnych w
pełnym feedzie (Morelia–La Paz 26.07, 26 strzałów) — strażnik z założenia go nie łapie.
Weryfikator nie stawiałby m.in. nóg „1. połowa gole poniżej 1.5” (czytają ogólną pulę) i powtórzeń
tej samej tezy na jednym meczu (Castellón ×5, drabinki 11.5/10.5).

End-to-end: SAMPLES→SHEET→COUPON→CONFIDENCE na kopii 10-03 (offline, zegar z 10-03) przechodzi;
CONFIDENCE na nowym kodzie bez strażnika danych daje identyczne nogi jak prawdziwy 10-03.

## Pomiary (szczegóły i skrypty w `data/night_2026-10-03/<temat>/`)

- `antisel/` — anty-selekcja krzywych (pkt 6 listy): w 30/32 komórkach rynek×kierunek pewność spada
  wraz z przewagą modelu nad ceną; korekta poprawia kalibrację (Brier 0.1888→0.1836), ale kupon
  traci (463 nogi, −7.4%). Rating w pucharach (pkt 7): propozycja gorsza na najnowszych danych — bez zmian.
- `g1h/` — goals_1h UNDER: pula nie zawyżała; straty z wybierania wierszy nad ceną (to samo co pkt 6).
- `props/` — propsy (patrz wyżej) + zabezpieczenie dolnego kubełka.
- `edge/` — gdzie model wnosi coś ponad cenę: tylko football goals_total (b = 0.50 [0.26; 0.75],
  od ratingu 09-23); najlepsza reguła +6.7% [−15.9; +29.3] na 160 zakładach — szum.
- `shadow/RAPORT.md` — sporty mierzone, kryterium przyjęcia.
- `tennis/RAPORT.md` — refity tenisa (zainstalowany tylko tier baselines).
- `guards/` — strażnik zer i towarzyskie.
- `matching/` — siatkówka: 48% niedopasowanych to brak meczów w Sofascore (towarzyskie klubów,
  regionalne ligi), nie błąd; naprawione 10 meczów; ponowne rozliczenie 09-29..10-02 wykonane
  (+5 hokej, +4 kosz, +1 siatka), kupony sportowe i rejestr przeliczone.
- Boosty Superbetu: 12 pojedynczych dwustronnych, średnie EV przy zdewigowanej cenie +0.1% — nie źródło zysku.

## Decyzje dla operatora

1. Propsy: zdjąć wszystkie 7 z `admitted_player_markets` (rekomendacja).
2. `gap_shrink_k` (~0.85): włączyć = uczciwe pewności, ale kupon kurczy się do ~10% i traci więcej.
3. WARIANT: tydzień 09-26..10-02 ROI −4.4% [−7.7; −1.1] — strata poza szumem.
4. Kupon HOKEJ: −18.2% [−38.5; −1.8].
5. Sporty mierzone: zatwierdzić kryterium przyjęcia (shadow/RAPORT.md) — test od 10-04, model zamrożony na 953adf45.
6. Football goals_total: czy prowadzić test z góry zarejestrowany (blend model+cena, próg 1.05) — ~2 miesiące.
7. Połówki w replayu przy następnym reficie (`--with-halves`) — zdejmuje AWAITING_OWN_CURVE z rynków połówkowych.
8. 852 (towarzyskie reprezentacji kobiet) — zostawione dozwolone.
9. `refused_markets` += `goals_1h_total|UNDER`? Jego nogi czytają ogólną pulę w dziurze 0.70–0.875;
   własne wiersze nad ceną: 160 szt., realnie .744 przy cenie .779, ROI −8.6%. Cienki kubełek
   (c2350786) to naprawi dopiero po reficie.
10. Limit w PDF: najwyżej jeden szczebel drabinki i 2–3 single na mecz (dziś zdarza się 5 tez na jeden mecz).
11. **Próba refitu na kopii bazy nie skończyła się** (zatrzymana o 04:20Z): wczytanie historii
    do odtwarzania z cache trzyma ~26 GB; z OrbStack (11 GB) i resztą maszyna 48 GB swapowała
    (wolne ~66 MB, 23 mln swap-in), 4.5 h bez postępu. Przed refitem: wyłączyć OrbStack/Docker,
    nie puszczać backfillu równolegle. Kopia bazy: `data/refit_rehearsal_2026-10-04/` (42 GB).
12. Push: nic nie zostało wypchnięte (zgodnie z zasadą „push tylko na prośbę”); wszystkie commity są na lokalnym main.
