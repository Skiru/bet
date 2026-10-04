# Porównywalność historii — raport z 2026-10-04

*(punkt wyjścia: SC Farense – Chaves, gole w meczu poniżej 3.5 @1.29, przegrane 0:4 w drugą stronę, 4:0)*

Polecenie operatora: przejrzeć cały pipeline pod kątem błędów tej samej klasy, naprawić
wszystkie z testami, przejść flow na żywo i porównać wyniki starego i nowego systemu,
udokumentować i wypchnąć na main. Refit i instalacja konfiguracji zostają decyzją operatora.

## W jednym akapicie

- **Proces widział problem, ale nie miał jak go zatrzymać.** Analityk dał nodze Farense – Chaves
  WATCH, weryfikator wpisał ją na swoją listę, a nic nie miało pola w danych ani skutku. Tak było
  do dziś.
- **Teraz każdy werdykt jest zapisany i działa:** WATCH zdejmuje nogę z oficjalnego kuponu,
  NO_BET zdejmuje ją wszędzie.
- **Wspólna reguła dla historii:** wszystkie miejsca, które czytają historię meczów, korzystają z
  jednej reguły „czy ten mecz się liczy”. Turnieje przedsezonowe i pokazówki nie wchodzą już do
  próbek, ratingów ani krzywych.
- **Próbki goli:** biorą tylko mecze ligowe tych samych rozgrywek. Zmierzone na 677 tys.
  przypadków, poprawa przy rożnych i faulach się nie pokazała, więc tam zmiany nie ma.
- **Mecz zaległy, długa przerwa i natłok meczów** są wykrywane i widoczne w PDF. Pomiar nie
  wykazał, że przez mecz zaległy próbka myli się systematycznie.
- **Odtworzenie na żywo dni 10-01…10-03, stary kod obok nowego:** wynik prawie ten sam. Oficjalny
  kupon +1.10 → +1.85 j., WARIANT −65.5 → −59.8 j. To szum, a nie nowa przewaga.
- **Dlaczego wynik się nie zmienił:** to poprawki poprawności. Przewagi nad ceną nadal nie ma
  (`ANALIZA_WYNIKOW_2026-10-04.md`).
- **Refitu nie instalowałem.** Krzywe pewności są fitowane na replayu po starej regule, a decyzja
  o nowej epoce należy do ciebie.

## 1. Co poszło źle przy Farense – Chaves (fakty)

- Noga: `goals_total` 3.5 UNDER, kurs 1.29, pewność 0.781, model 0.786, cena rynku bez marży 0.745.
  Kurs zamknięcia 1.27 (rynek przesunął się *w naszą* stronę), wynik 4:0.
- Rynek przy cenie 0.745 dawał OVER 3.5 około 1 do 4. Żaden OVER na tym meczu nie miał dodatniej
  wartości przy cenie rynku (powyżej 1.5 @1.29 −3.9%, powyżej 2.5 @1.92 −8%, powyżej 3.5 @3.25 −17%).
- Model różnił się od rynku głównie atakiem Farense (model 1.14 gola, rynek ~1.5), bo próbka
  Farense mieszała: dwa mecze barażu o utrzymanie z maja (0:0, 1:0), koniec poprzedniego sezonu
  i mecz pucharowy z niższą ligą; próbka Chaves zawierała letni turniej towarzyski
  (Torneio de Verão Póvoa de Varzim, id 36573), którego nie było na liście towarzyskich.
- Mecz był zaległym meczem 5. kolejki (przełożony 2026-09-06 przez infekcję w kadrze Farense).
  Pipeline widział przełożony mecz tylko jako lukę w próbce.
- **Analityk ocenił nogę jako WATCH**, a weryfikator wpisał ją na listę „nie stawiałbym” (model
  o 9 pp nad trafnością własnej próbki). Ani WATCH, ani lista weryfikatora nie miały pola w
  danych ani żadnego skutku — noga została w PDF. (W pierwszej odpowiedzi błędnie napisałem, że
  analityk meczu nie czytał; sprostowane.)

## 2. Cztery klasy błędu i co zrobiono z każdą

### K1. „Czy ten mecz z historii się liczy” — osiem różnych odpowiedzi
**Było:** decyzję podejmowało osiem miejsc, każde po swojemu.
- Próbki i rating brały sparingi tylko z listy id.
- Replay kalibracji (wiersze, na których fitowane są krzywe pewności) nie miał żadnego filtra.
- Model graczy i jego fit oraz historia CS2 nie miały filtra.
- Hokej, koszykówka i siatkówka sprawdzały tylko słowo „friendly” w nazwie, więc przepuszczały
  „NHL Preseason”, „NBA Summer League” i „ABA Liga Preseason”.
- Tenis wpuszczał pokazówki (Kooyong Classic, Six Kings Slam) do ratingu i priorów.

**Jest:** jeden predykat `bet.sofa.comparability.is_friendly_event`, używany wszędzie:
- piłka: przejrzana lista id;
- pozostałe sporty: znaczniki w nazwie (friendly, preseason, exhibition, all-star, summer league, legends);
- tenis dodatkowo: kategorie „Exhibition” i „Legends”.

Do listy doszły 32 rozgrywki, każda sprawdzona ręcznie na przykładowym meczu z cache
(`docs/sofa/evidence/preseason_competitions_2026-10-04.json`), m.in.:
- Torneio de Verão, Como Cup, Emirates Cup, Telekom Cup, Atlantic Cup;
- memoriały przedsezonowe i turnieje młodzieżowe;
- FIFA Series (towarzyskie reprezentacji);
- Kings League (inny format gry);
- trening noworoczny Cracovii.

Celowo nie dodałem:
- angielskich pucharów hrabstw z „Memorial” w nazwie, bo to prawdziwe puchary;
- superpucharów;
- Baltic Cup i turnieju w Tulonie.

Nowy skaner `scripts/sofa/find_friendly_competitions.py` proponuje kandydatów po nazwie i po
kształcie (krótki sezon, mało meczów na klub, kluby z różnych lig). Każdego kandydata decyduje
człowiek. W danych CS2 nie było ani jednego showmatchu, ale filtr działa także tam.

### K2. Próbka nie czytała rundy ani rozgrywek
**Pomiar przed zmianą** (`scripts/sofa/measure_sample_composition.py`, każdy mecz ligowy
2025-08…2026-10, mecze czytane tak samo jak w SAMPLES; log-loss, przedział 95% z losowania meczów):

| rynek | tylko liga tych samych rozgrywek (R2) | bez pucharów i baraży (R1) | tylko bieżący sezon |
|---|---|---|---|
| gole drużyny | **−0.00555 [−0.00632; −0.00487]** | −0.0002 | **gorzej** (+0.0041) |
| gole drużyny, 1. połowa | **−0.00194** | −0.0005 | gorzej |
| gole drużyny, 2. połowa | **−0.00158** | −0.0002 | gorzej |
| gole w meczu | **−0.00070 [−0.00115; −0.00023]** | −0.0001 | gorzej |
| rożne total / drużyny | +0.0011 / +0.0019 (gorzej) | +0.0007 / +0.0010 | gorzej |
| faule, kartki, strzały, spalone | bez różnicy albo gorzej | bez różnicy | gorzej |

Ujemna wartość oznacza lepszą prognozę. Obie połówki event id dają ten sam znak.

**Wnioski:**
- **Liczba goli niesie poziom rywala.** Mecz pucharowy z amatorami czy baraż opisuje inny mecz.
- **Rożne i faule opisują styl gry drużyny**, więc dla nich ważniejsza jest świeżość próbki.
- **Ograniczenie do bieżącego sezonu szkodzi wszędzie.** Intuicja z Farense („poprzedni sezon
  myli”) się nie potwierdziła; problemem był *rodzaj* meczu, a nie sezon.

**Zmiana:**
- Próbka dla `goals_total`, `goals_for`, `goals_1h_for` i `goals_2h_for` to 10 najnowszych
  meczów ligowych tych samych rozgrywek, jeśli strona ma ich co najmniej 5. W przeciwnym razie
  zostaje zwykła próbka.
- Gole czytane są z wyniku w liście meczów, więc nie ma żadnego nowego zapytania do Sofascore.
- Replay kalibracji wybiera mecze tak samo.
- Pozostałe rynki bez zmian.

**Kontrola własnych liczb:**
- Pierwsza wersja pomiaru liczyła gole z dogrywką, tak jak `current` w liście meczów, i zawyżała
  efekt dla goli w meczu około 8 razy (−0.0056 zamiast −0.0007).
- Po poprawce pomiar czyta gole tak samo jak pipeline (`regulation_score`), a wyniki w tabeli są już po poprawce.

### K3. Mecz zaległy, odpoczynek, natłok meczów
Nowy moduł `bet.sofa.schedule` liczy z danych w cache (bez zapytań):
- **mecz zaległy**: przełożony, odwołany lub przerwany mecz tej samej pary w tych samych rozgrywkach;
- **odpoczynek**: dni od ostatniego meczu o stawkę, przy czym liczy się też mecz bez statystyk;
- **natłok**: liczba meczów w ostatnich 7 i 14 dniach.

Wynik trafia:
- do `03_samples.json` (pole `schedule`);
- na nogi (`context_flags`: `MAKEUP_FIXTURE`, `LONG_LAYOFF`, `CONGESTED`);
- do PDF.

Na Farense – Chaves moduł daje `MAKEUP_FIXTURE(postponed 2026-09-06, event 16451028)`.

**Pomiar** (`scripts/sofa/measure_schedule_context.py`, 293 tys. meczów ligowych; reszta to
wynik minus średnia próbki):

| kontekst | gole: reszta [95%] | rożne: reszta [95%] |
|---|---|---|
| wszystkie | +0.014 [+0.007; +0.022] | −0.015 [−0.044; +0.017] |
| mecz zaległy | +0.024 [−0.001; +0.048] | +0.035 [−0.071; +0.140] |
| obie strony ≥ 21 dni przerwy | **−0.122 [−0.155; −0.092]** | **−0.280 [−0.452; −0.108]** |

- **Mecz zaległy: brak systematycznego błędu próbki.** Flaga jest tylko informacją.
- **Po długiej przerwie** (początek sezonu, pauza) padło mniej goli i rożnych, niż mówi próbka.
  To odchylenie od próbki, nie od ceny. Nie wiem, czy rynek go nie wycenia, więc **nie ma
  bramki**: jest flaga i kandydat do pomiaru względem ceny.

### K4. Ostrzeżenia analityka i weryfikatora bez skutku
- **Nowy kanał `runs/sofa/<data>/reads.json`** (`contracts.LegRead`) zapisuje werdykt KEEP /
  WATCH / NO_BET dla każdej nogi, z autorem (analityk albo weryfikator) i powodem.
- **Skutek werdyktów:**
  - NO_BET usuwa nogę wszędzie, tak jak weto.
  - **WATCH usuwa nogę z oficjalnego kuponu i zostawia ją w WARIANCIE**, z oznaczeniem w PDF.
    Taką decyzję podjąłeś 2026-10-04, żeby rejestr zmierzył, czy WATCH ma rację.
  - KEEP tylko zapisuje, że nogę przeczytano.
- **Kontrola C3 w `audit_variants.py`** (od 10-05): każda noga oficjalnego PDF ma odczyt
  analityka, a żadna nie ma WATCH ani NO_BET.
- **Automatyczny WATCH dla piłki (`MODEL_ABOVE_OWN_SAMPLE`):** gdy model przekracza trafność
  własnej próbki nogi o więcej niż 0.15, noga wypada z oficjalnego kuponu i zostaje oznaczona w
  WARIANCIE.
  - Próg pochodzi z kontraktu weryfikatora i był zapisany *przed* pomiarem.
  - Pomiar (`scripts/sofa/measure_own_sample_gap.py`, 51 567 rozliczonych wierszy piłkarskich
    z kursem i p ≥ 0.65, dni 09-19…10-03): rozjazd powyżej 0.15 wypadł 2.1 pp poniżej ceny
    [−3.9; −0.3], ROI −8.2% [−11.2; −5.5]. W pozostałych przedziałach ROI wynosił od −3.6% do −5.3%.
  - Wynik był gorszy niż reszta w 11 z 15 dni.
  - W tenisie efektu nie ma, więc bramka obejmuje tylko piłkę.
- **Każda noga ma teraz `sample_hit_rate`.**
- **Farense – Chaves nie spełnia tego progu:** rozjazd 0.786 − 0.70 = 0.086. Tę nogę zatrzymałby
  dopiero WATCH analityka, który teraz ma skutek.
- **Bramka UNDER ≥ 0.05, rozważana i odrzucona.** Ten próg pochodził z podziału po fakcie i wypadł
  gorzej tylko w 10 z 15 dni, więc go nie wprowadziłem.
- **Kontrakty agentów** (analityk, weryfikator, runner, `/sofa-day`, `/sofa-analyze`,
  `/sofa-verify`) opisują nowy obieg: analityk oddaje `reads`, runner je zapisuje i przebudowuje
  kupon, weryfikator dopisuje swoje odczyty, potem jest kolejna przebudowa i C3. Te definicje
  zadziałają dopiero w następnej sesji.

## 3. Porównanie starego i nowego systemu (A/B na żywo)
**Jak:** `data/analysis_2026-10-04_history/ab/`. Dni 10-01…10-04 odtworzone dwa razy z ich własnych
`01_board`, `02_fixtures`, `04_offer` i `vetoes`, na tej samej bazie i tych samych plikach `config/`,
z zegarem zamrożonym na moment prawdziwej budowy kuponu (`SOFA_NOW`):
- **A:** stary kod (worktree na `1b2e0f78`, podmieniony wyłącznie `timeutil.py`, żeby rozumiał zamrożony zegar);
- **B:** nowy kod.

SAMPLES poszły na żywo przez most, dalej SHEET → COUPON → CONFIDENCE (oba profile) → PDF. Rozliczenie
z `sofa_settled_row`. Prawdziwe `runs/sofa/<d>` są nietknięte (sumy md5 przed i po identyczne).

| profil | A (stary) | B (nowy) | rzeczywisty dzień |
|---|---|---|---|
| oficjalny, single 10-01…10-03 | 40–13, ROI +2.1%, +1.10 j. | 39–12, ROI +3.6%, +1.85 j. | 34–11, +2.6%, +1.16 j. |
| WARIANT, single 10-01…10-03 | 682–322, −6.5%, −65.5 j. | 658–307, −6.2%, −59.8 j. | 747–360, −6.6%, −73.1 j. |

- **Nogi, które B zmienił, dzień po dniu** (pełna tabela: `ab/compare_ab.md`):
  - oficjalny: 10-01 wymienił 1 nogę (przegraną na wygraną), 10-02 wyrzucił 4 wygrane i dodał 2 wygrane,
    10-03 wymienił 3 na 3;
  - WARIANT 10-03: wyrzucił 74 nogi (45–29, −10.6 j.), dodał 42 (26–16, −5.0 j.).
- **10-04** jeszcze nierozliczony. B zmienia 2 nogi oficjalnego kuponu, a w WARIANCIE wyrzuca 94 i
  dodaje 38. Do rozliczenia jutro: `compare_ab.py 2026-10-04` po SETTLE.
- **Farense – Chaves w B:** średnia próbki 2.45 → 2.80, model 0.786 → **0.763** (rynek 0.745), flaga
  `MAKEUP_FIXTURE`. Rozjazd od własnej próbki 0.06 nie przekracza progu, więc noga nadal się drukuje.
  Usunąłby ją dopiero WATCH analityka, który od teraz działa.
- **Ograniczenia:**
  - trzy rozliczone dni to szum;
  - A/B nie odtwarza odczytów analityków, bo `reads.json` jeszcze wtedy nie istniał;
  - oba warianty używają krzywych fitowanych na starym replayu.
- **Incydent:** przy pierwszym przebiegu B (10-04 i 10-01) otworzył się bezpiecznik klienta (CIRCUIT_OPEN, 23 + 13
  meczów). W wyjściu nie było 403, a most działał (277 ms). B wysyłał więcej zapytań niż A, bo
  bez sparingów próbki sięgają po inne mecze, których statystyk nie było w cache. Powtórka B na rozgrzanym
  cache przeszła czysto (0 błędów dostawcy) i tylko ona jest w tabeli.
- **Wydajność replayu z nową regułą** (syntetycznie, 300 tys. meczów): 88.6 s wobec 85.9 s.

## 4. Czego nie zrobiono i dlaczego
- **Refit / nowa epoka nie zainstalowane.** To twoja decyzja. Kiedy: rano po SETTLE, przed dniem,
  `prepare_refit.py --date <d> backup → rebuild-cache-rows → fit → compare`. Dysk jest zajęty w 90%
  (96 GB wolne, kopia bazy 43 GB), więc próby na kopii dziś nie robiłem.
- **Bramka „długa przerwa”:** po ≥ 21 dniach przerwy pada mniej goli i rożnych, niż mówi próbka, ale to
  odchylenie od próbki, nie od ceny. Bez pomiaru względem ceny zostaje tylko flaga.
- **Bramka UNDER z rozjazdem ≥ 0.05:** odrzucona, bo próg pochodził z podziału po fakcie (10/15 dni).
- **Bramka wieku 180 dni (`SAMPLE_CROSSES_SEASON`) bez zmian:** przy nowej próbce goli odrzuca więcej
  nóg (10-03: oficjalny 44 → 63). Przeliczona na 15 dniach: przedział 180–240 dni wypada −3.0 pp
  wobec ceny [−5.1; −1.1], starsze przedziały bez różnicy. R2 z limitem 180 dni było gorsze od
  obecnej reguły, więc limitu nie wprowadziłem.
- **Gole w połowach (total)** zostały na zwykłej próbce, bo R2 nie pomaga tam. Linie drużyn w połowach
  są na R2, więc w jednym meczu korzystają z innych meczów historycznych niż totale połów.
- **Przeglądu kontraktów agentów nie da się sprawdzić w tej sesji**, bo definicje ładują się przy starcie.
  Pierwszy dzień z odczytami to `/sofa-day` 10-05.
- **Z `excluded_other_sports` celowo nic nie usunąłem** (listy są puste). Hokej, koszykówka i
  siatkówka opierają się na znacznikach w nazwie. Prawdopodobnie przedsezonowe memoriały w gruzińskiej
  koszykówce (Dudu Dadiani, Sakandelidze-Qorqia) przechodzą; to do przejrzenia, jeśli te ligi
  trafią do kuponów sportowych.

## 5. Twoje decyzje
1. **Refit (nowa epoka):** po zmianie próbek goli i replayu krzywe są fitowane na innych próbkach niż
   te, które od 10-05 drukujemy. Rekomenduję refit po rozliczeniu 10-04, zgodnie z sekcją 7 w `CONFIG.md`.
2. **Reguła WATCH:** zostaje tak, jak zdecydowałeś (oficjalny kupon bez nogi, WARIANT z nogą). Po
   7–14 dniach rejestr pokaże, czy WATCH ma rację.
3. **MODEL_ABOVE_OWN_SAMPLE (próg 0.15, piłka):** wdrożony jako automatyczny WATCH. Jeśli wolisz
   najpierw wyłącznie pomiar, wystarczy ustawić `MAX_OWN_SAMPLE_GAP = 1.0`.
4. **Kandydaci do pomiaru względem ceny:** długa przerwa (≥ 21 dni) i bramka wieku przy próbce R2.

## 6. Pliki
- **Kod:** `src/bet/sofa/comparability.py`, `src/bet/sofa/schedule.py`, `contracts.LegRead`,
  `veto.load_reads/matching_reads/read_refusal`, `confidence.model_above_own_sample`, `timeutil.SOFA_NOW`;
  zmiany w `samples.py`, `calibrate_from_cache.py`, `run_confidence.py`, `coupon.py`, `build_coupon_pdf.py`,
  `audit_variants.py` (C3), `multi_coupon.py`, `player_model.py`, `fit_player_model.py`, `score_model.py`,
  `backfill_event_stats.py`, `cs2_engine.py`, `tennis_rating.py`, `tennis_prior.py`, `run_pipeline.py`.
- **Config:** `config/sofa_friendly_competitions.json` (+32), dowody w `docs/sofa/evidence/preseason_competitions_2026-10-04.json`.
- **Pomiary:** `scripts/sofa/measure_sample_composition.py`, `measure_own_sample_gap.py`,
  `measure_schedule_context.py`, `find_friendly_competitions.py`. Wyniki w `data/analysis_2026-10-04_history/`
  (`composition_all_v2.md`, `composition_goals_halves.md`, `composition_goals_180d.md`,
  `own_sample_gap_football.md`, `own_sample_gap_tennis.md`, `schedule_context.md`, `ab/compare_ab.md`).
- **Testy:** `tests/sofa/test_history_comparability_2026_10_04.py` (35), `test_history_readers_follow_comparability.py`
  (15), `test_pdf_refuses_stale_confidence.py` (+1). Całość: pytest zielony, mypy --strict czysty, ruff bez
  nowych błędów (92 sprzed zmian).
- **Kontrakty:** `.claude/agents/*`, `.claude/commands/sofa-{day,analyze,verify,rebuild}.md`, skille
  `sofa-analysis-core`, `football-analysis`, `tennis-analysis`, `sofa-pipeline`; `docs/sofa/AGENTIC_FLOW.md`,
  `docs/sofa/VERIFY_PROTOCOL.md`.
