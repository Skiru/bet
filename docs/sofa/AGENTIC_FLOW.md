# `sofa` — orkiestracja agentowa

Jak przeprowadzić dzień **rękami agentów**, a nie jedną sesją robiącą wszystko
inline. Ten plik opisuje konfigurację w `.claude/`: kto co uruchamia, w jakiej
kolejności, co wolno każdemu z osobna i gdzie dokładnie przebiega przekazanie.

Mechanika etapów jest w [`PIPELINE.md`](PIPELINE.md). Tutaj są **role**.

---

## 1. Inwentarz — co jest w `.claude/`

### Komendy (`/…`) — punkty wejścia operatora

| komenda | co robi | sieć |
|---|---|---|
| `/sofa-day [data]` | cały dzień: most (ensure_bridge) → SETTLE D-1 + `audit_settle_identity` → dziennik (record_results, audit_ledger, audit_clv) → BOARD…COUPON → CONFIDENCE (piłka, tenis) → świeże migawki SHADOW i CS2 → SPORT_IDENTITY → SPORT_CONFIDENCE → COUPON_ASSEMBLY (`11_coupon.json`) → analitycy na nogach do przeczytania → scalenie wet i odczytów → przebudowa od CONFIDENCE → PDF → audit_coupon + audit_variants → sofa-verifier → odczyty weryfikatora → przebudowa → raport | Sofascore (most) + Superbet |
| `/sofa-analyze [data]` | analitycy nad gotowym kuponem (`11_coupon.json`), także pozycje „dodatkowo: …” operatora (`read_requests.json`), scalenie wet i odczytów (`reads.json`), przebudowa | tylko Superbet (opcjonalnie) |
| `/sofa-rebuild [data]` | przebudowa kuponu i PDF z artefaktów z dysku jednym poleceniem `rebuild_day.py` (stare ceny najpierw; FIXTURE_CHECK i SPORT_IDENTITY potrzebują mostu) | Superbet (gdy cena stara), most dla FIXTURE_CHECK / SPORT_IDENTITY |
| `/sofa-verify [data]` | adwersaryjna weryfikacja zbudowanego dnia | Superbet (ceny na żywo) + web |
| `/sofa-settle [data]` | rozliczenie dnia zakończonego i decyzja o fitowaniu | Sofascore (most) |

Argument to `dzisiaj` / `wczoraj` / `YYYY-MM-DD`; pusty znaczy dzisiaj.
**Doba kuponu jest w UTC dla każdego sportu:** kupon dnia D to nogi ze
startem w [D 00:00Z, D+1 00:00Z) (`run_sport_confidence.py`, `day_window`).

### Jeden kupon (od 2026-10-05)

Produktem dnia jest **jeden** plik `runs/sofa/<d>/KUPON_<d>.pdf` dla
wszystkich sportów. Łańcuch artefaktów:

```
05_sheet.json ─→ CONFIDENCE (run_confidence.py) ─→ 08_confidence.json          (piłka, tenis)
SHADOW/CS2 snapshot ─→ SPORT_IDENTITY ─→ sport_fixtures.json
                    └→ SPORT_CONFIDENCE ─→ 08_confidence_sports.json           (hokej, kosz, siatka, CS2)
08_confidence.json + 08_confidence_sports.json + vetoes.json + reads.json + read_requests.json
  ─→ COUPON_ASSEMBLY (build_coupon.py) ─→ 11_coupon.json ─→ PDF (build_coupon_pdf.py) ─→ KUPON_<d>.pdf + 12_printed.json
```

- `11_coupon.json` jest jedynym artefaktem kuponu; każdy czytelnik idzie
  przez `confidence.coupon_artifact()` (11, a dla dni bez niego
  `08_confidence.json`). Kolejność `confidence.coupon_order`: pewność
  malejąco, potem wcześniejszy start, nogi jednego meczu razem (blok na
  miejscu najlepszej nogi), pozycje 1..N; nogi zablokowane z wcześniejszego
  wydruku na górze, bez numeru; buildery B1.. na osobnych stronach PDF.
- `12_printed.json` zapisuje PDF: to, co naprawdę wydrukowano. Następna
  przebudowa blokuje z niego nogi, których mecz już się zaczął; noga zdjęta
  przed startem zostaje zdjęta.
- Pewność jest wyłącznie ze statystyk (piłka, tenis: krzywe
  `config/sofa_confidence_calibration.json`; sporty mierzone: krzywe
  `config/sofa_sport_confidence_calibration.json` nad modelem wyników /
  silnikiem CS2). Cena to tylko warunek zakładu: x = pewność × kurs ≥ 0,90,
  marża drabinki/grupy ≤ 15%, `ODDS_TOO_LOW`, mecz niezaczęty, świeża cena.
  `forecast_p` („model”, nieskalibrowany) stoi obok i niczego nie bramkuje.
- `06_coupon.json` (selektor VALUE, `p_bar`, `required_odds`) zostaje cenowy i
  **nie jest kuponem**.

Nogi sportów mierzonych czyta `sofa-analyst-sport`.

### Agenci — wykonawcy z własnym kontekstem

| agent | rola | narzędzia | pisze pliki? |
|---|---|---|---|
| `sofa-runner` | właściciel przebiegu: uruchamia etapy, deleguje, scala weta i odczyty, melduje | Bash, Read, Glob, Grep, **Task** | nie (brak Edit/Write; dane pisze przez Bash) |
| `sofa-analyst-football` | piłkarski odczyt meczu, którego kod nie zrobi + weta + jeden odczyt (KEEP/WATCH/NO_BET) na każdą nogę do przeczytania | Read/Glob/Grep/Bash, Web (bez bzzoiro — sofa czyta tylko Sofascore i Superbet) | nie — zwraca tekst |
| `sofa-analyst-tennis` | to samo dla tenisa | Read/Glob/Grep/Bash, Web | nie — zwraca tekst |
| `sofa-analyst-sport` | to samo dla jednego sportu mierzonego (hokej / koszykówka / siatkówka / CS2), jedna instancja na sport; tożsamość meczu z `sport_fixtures.json`, cena z surowej migawki; tylko odczyty (strona i okres w `LegRead`) | Read/Glob/Grep/Bash, Web | nie — zwraca tekst |
| `sofa-verifier` | rozbiera zbudowany dzień na części, adwersaryjnie; wiersze, których by nie postawił, oddaje jako odczyty JSON | Read/Glob/Grep/Bash, Web | nie — zwraca tekst |
| `sofa-settler` | pętla rozliczenie → kalibracja, higiena konfiguracji | Bash, Read, Glob, Grep | nie (uruchamia fitter, nie edytuje stałej ręcznie) |
| `sofa-market-scout` | czy da się to postawić i czy warto tej ceny; ślepa plama `unmapped_markets` | Read, Glob, Grep, Bash, WebFetch | nie |

**Żaden agent `sofa` nie ma `Write` ani `Edit`.** To nie przeoczenie: przebieg,
który potrzebował edycji pliku, potrzebuje człowieka. Dane (jak `vetoes.json`,
`reads.json`, `read_requests.json`) powstają przez Bash — to zapisywanie
danych, nie naprawianie kodu.

### Umiejętności (skills) — wiedza wstrzykiwana do kontekstu

| skill | do czego | wczytany do |
|---|---|---|
| `sofa-pipeline` | etapy, artefakty, arytmetyka, pułapki | każdego agenta `sofa` |
| `sofa-analysis-core` | kontrakt analityka: kolejność artefaktów, schemat wet i odczytów, punkt decyzyjny, format raportu | trzech analityków |
| `football-analysis` | metoda piłkarska (runda, stawka, sędzia, scenariusz meczu, rozkład ponad średnią) | `sofa-analyst-football` |
| `tennis-analysis` | metoda tenisowa (nawierzchnia, format, hold/break, arytmetyka wyniku) | `sofa-analyst-tennis` |
| `bet-slip-audit` | wycena kuponu/slipa, który operator przysłał z ekranu | na żądanie |

Hierarchia, gdy dwa źródła mówią co innego: **artefakt > skill > plik agenta**.
Skill wygrywa na metodzie, artefakt na faktach, plik agenta mówi tylko, jak
przebiega *jego* przebieg.

> **Definicje agentów wczytują się na starcie sesji.** Przepisanego pliku
> agenta **nie da się przetestować w tej samej sesji, w której go napisano** —
> trzeba nowej. Nie pisz, że poprawka „już działa"; napisz, że wejdzie
> w następnej sesji. Dotyczy to też `sofa-analyst-sport` (nowy 2026-10-05).

---

## 2. Pełny dzień agentowo

```
operator: /sofa-day 2026-10-06
   │
   ├─ 0. most            ensure_bridge.py — podnosi most, potem check_bridge;
   │                     liczy się WIEK pobrania, martwa karta nadal melduje ok:true
   │
   ├─ 1. SETTLE D-1      → sofa-settler (albo inline)
   │                       run_pipeline --only SETTLE; CS2_SETTLE / SHADOW_SETTLE (pętle dnia)
   │                       audit_settlement §7c = prawdziwy wynik kuponu (per sport + suma),
   │                       §7i nogi zdjęte przez odczyt (osobno); zwroty liczone osobno
   │                       audit_settle_identity.py --from <D-1> --to <D-1>
   │   1a. dziennik      record_results.py (D-8..D-1) → audit_ledger.py → audit_clv.py
   │   1b. pętle dnia    cs2_daily.py --chain, shadow_daily.py --chain (zostają u orkiestratora;
   │                     robią migawki cen i poranne SETTLE pomiaru)
   │
   ├─ 2. dzisiaj         run_pipeline.py: BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON
   │                     jeden --run-id na cały dzień
   │
   ├─ 3. CONFIDENCE      run_confidence.py --date <d>  → 08_confidence.json (piłka, tenis)
   │
   ├─ 4. sporty          run_pipeline --only SHADOW, --only CS2   (świeże migawki Superbetu)
   │                     → SPORT_IDENTITY (most)   → sport_fixtures.json
   │                     → SPORT_CONFIDENCE        → 08_confidence_sports.json
   │
   ├─ 5. COUPON_ASSEMBLY build_coupon.py --date <d>  → 11_coupon.json
   │
   ├─ 6. analitycy       nogi z confidence.legs_requiring_read: pierwsze 30 pozycji
   │                     niezablokowanych + każda noga wydrukowanego buildera + read_requests.json
   │                     Task → sofa-analyst-football   ┐
   │                     Task → sofa-analyst-tennis     │ w JEDNEJ wiadomości,
   │                     Task → sofa-analyst-sport ×k   ┘ jeden na sport obecny wśród tych nóg
   │                        ↓ każdy zwraca markdown + tablice JSON: weta (piłka, tenis), odczyty
   │                     markdown → runs/sofa/<data>/<data>_analiza_<sport>.md
   │                     walidacja → vetoes.json; dopisanie + walidacja → reads.json
   │
   ├─ 7. przebudowa      rebuild_day.py --date <d> (jedno polecenie, F0.2): [OFFER, gdy cena
   │                     blisko 45 min] → [SHADOW z horyzontem do najdalszego startu / CS2,
   │                     gdy ceny sportów blisko 3 h] → [SPORT_IDENTITY] → [SHEET, gdy epoka lub brak znaczników pakietów, dzień >= 10-09]
   │                     → FIXTURE_CHECK (most) → run_confidence.py → SPORT_CONFIDENCE
   │                     → build_coupon.py → build_coupon_pdf.py (KUPON_<d>.pdf + 12_printed.json)
   │                     → audit_variants.py + audit_coupon.py
   │                     → capture_closing.py --loop (CLV) + run_boosts.py
   │
   ├─ 8. audyty          audit_coupon.py (05/06, arytmetyka) + audit_variants.py (C1–C3, U1–U3)
   │
   ├─ 9. weryfikacja     sofa-verifier (NIE jest opcjonalna) — kończy listą nóg, których
   │                     NIE postawiłby, prozą i jako tablica odczytów JSON (author "verifier")
   │                     → dopisanie do reads.json → przebudowa jak w kroku 7
   │                     → audit_variants (C1, C3, U1–U3 czyste)
   │
   └─ 10. raport         jeden kupon, sekcje per sport, top 30 przeczytane, liczba nóg poza
                         top 30, nogi zdjęte (removed_by_reads) z powodem — wzór w części 8
```

Polecenia kroków 3–7 (flagi sprawdzone w skryptach):

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only SHADOW
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only CS2
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_identity.py --date <d>        # albo run_pipeline.py --only SPORT_IDENTITY; most
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_confidence.py --date <d>      # bez mostu
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon.py --date <d>              # COUPON_ASSEMBLY, offline
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_fixture_check.py --date <d>         # tylko w przebudowie, po OFFER, przed CONFIDENCE; most
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <d> [--dry-run] [--skip-audits]   # przebudowa (krok 7): jedyne polecenie, nigdy powyższe skrypty ręcznie
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date <d>
```

Kody wyjścia nowych etapów: SPORT_IDENTITY 1 przy meczu nierozpoznanym albo
odmowie mostu, 2 bez migawki żadnego sportu; SPORT_CONFIDENCE 1, gdy sport
jest `NOT_CALIBRATED` albo brak `sport_fixtures.json` (artefakt i tak
zapisany, kupon piłki i tenisa budowany); FIXTURE_CHECK 1 bez mostu (mecze
`UNVERIFIED`, nic nie odrzucone), 403 przerywa od razu.

### Punkt wstawienia, który czyni tę ścieżkę agentową prawdziwą

Osąd agenta wchodzi do produktu **dwoma plikami** w `runs/sofa/<data>/`:
`vetoes.json` (czytają COUPON, CONFIDENCE i — dla nóg sportów —
COUPON_ASSEMBLY) i `reads.json` (CONFIDENCE i COUPON_ASSEMBLY). Trzeci,
`read_requests.json`, nie zmienia wydruku — mówi tylko, które nogi poza top
30 trzeba przeczytać. Nic więcej z pracy analityka ani weryfikatora nie
dociera do maszyny — reszta jest raportem dla operatora.

- **`vetoes.json`** — werdykt o **próbce** albo kontekście
  (`SAMPLE_UNINFORMATIVE`, `CONTEXT`, `PRICE`, `OTHER`): usuwa wiersz
  **wszędzie**. Kierunek weta to tylko OVER/UNDER, więc weto na nodze sportu
  mierzonego może nazwać tylko cały mecz albo rodzinę rynku; nogę sportu
  zdejmuje się odczytem `NO_BET` (ma stronę i okres).
- **`reads.json`** (od 2026-10-04) — werdykt o **nodze**, `LegRead` w
  `src/bet/sofa/contracts.py` (strict, `extra="forbid"`): `sofascore_event_id`,
  `market` (dla sportu: rodzina), `subject`, `line`, `direction` (OVER/UNDER
  albo strona sportu T1/T2/DRAW/ODD/EVEN/YES/NO albo wynik dokładny „3:1”),
  `verdict`, `author` (`analyst` / `verifier`), `reason`, opcjonalnie
  `context` i `period` (okres / kwarta / set / mapa CS2; `null` obejmuje
  wszystkie). Pole `null` obejmuje każdą wartość.

  | werdykt | skutek na kuponie |
  |---|---|
  | `KEEP` | zostaje; zapis, że nogę przeczytano |
  | `WATCH` | **zdjęta** |
  | `NO_BET` | **zdjęta** |

  Noga, która przeszła wszystkie bramki, a zdjął ją odczyt (albo
  automatyczny `MODEL_ABOVE_OWN_SAMPLE`), trafia do `removed_by_reads` w
  `11_coupon.json` i jest rozliczana osobno: `audit_settlement` sekcja 7i
  („Nogi zdjęte przez odczyt”), dziennik `removed:reads` — nigdy w wyniku
  kuponu. Odczyt, który nic nie trafił, drukuje `UNMATCHED_READ`;
  `run_confidence.py` widzi tylko wiersze piłki i tenisa, więc odczyt nogi
  sportu zawsze jest tam `UNMATCHED_READ` — sprawdza się go w
  `11_coupon.json` (`removed_by_reads`, pole `reads` nogi). Odczytu nigdy się
  nie poprawia ani nie usuwa, tylko dopisuje; WATCH i NO_BET wygrywają z
  KEEP, kto by ich nie napisał.

- **`read_requests.json`** — lista próśb operatora o dodatkowy odczyt; każdy
  wpis ma `requested_by` i `at_utc` oraz albo `{"position": n}`, albo
  `{"group_key": "sofa:<id>", "market"?, "line"?, "direction"?}` (pominięte
  pole obejmuje wszystko). Forma `group_key` jest bezpieczniejsza — pozycje
  przesuwają się po przebudowie. `/sofa-analyze` „dodatkowo: <pozycje>”
  dopisuje wpisy z `requested_by: "operator"`. Nieczytelny plik albo wpis
  bez `requested_by` + `at_utc` zatrzymuje budowę; prośba, która nic nie
  objęła, drukuje `UNMATCHED_READ_REQUEST`.

Powód odczytów: 2026-10-04 SC Farense – Chaves, gole UNDER 3,5 @1,29,
przegrane 4-0. Analityk dał WATCH, weryfikator umieścił nogę na liście „nie
postawiłbym" — żaden z tych osądów nie miał pola ani skutku, więc noga
została w PDF. Był to mecz przełożony z 5. kolejki (2026-09-06, ognisko
wirusowe), czego nic nie oznaczyło.

Obok, automatycznie w kodzie (bez odczytu): `MODEL_ABOVE_OWN_SAMPLE` —
noga piłkarska, której `model_p` przewyższa trafialność jej własnej próbki
(`sample_hit_rate`, na każdej nodze) o ponad 0,15, wypada z kuponu do
`removed_by_reads`. Do `context_flags` trafiają też tagi terminarza z
`bet.sofa.schedule`: `MAKEUP_FIXTURE(...)`, `LONG_LAYOFF(...)` (≥ 21 dni),
`CONGESTED(...)` (≥ 3 mecze w 7 dni) — pokazywane, nie egzekwowane;
`03_samples.json` ma per mecz blok `schedule`. Mecz przełożony, odwołany
albo przerwany po wydruku łapie FIXTURE_CHECK (`fixture_status.json`,
`FIXTURE_NOT_AS_SCHEDULED`, odmowa w CONFIDENCE).

Z tego wynikają rzeczy, które trzeba robić dokładnie tak:

1. **Analitycy biegną po COUPON_ASSEMBLY**, na `11_coupon.json`. Zbiór do
   przeczytania to `confidence.legs_requiring_read` (`READ_REQUIRED_SINGLES`
   = 30): pierwsze 30 pozycji niezablokowanych (od 2026-10-09 00:00Z jednostką jest mecz: wszystkie niezablokowane nogi 30 pierwszych meczów kuponu, `read_unit: "event"` w artefakcie), każda noga wydrukowanego
   buildera i to, o co prosi `read_requests.json`. `audit_variants` C3
   sprawdza ten sam zbiór: każda taka noga ma odczyt `author: "analyst"`
   (także noga zostawiona w spokoju dostaje `KEEP`), a żadna wydrukowana nie
   ma WATCH ani NO_BET. Reszta kuponu drukuje się bez odczytu (decyzja
   operatora 2026-10-05). Nogi zablokowane czyta się w stanie z chwili
   wydruku — odmowa, która dziś je obejmuje, to notatka, nie defekt.
2. **Po zapisaniu wet i odczytów przebudowa idzie od CONFIDENCE** (z
   FIXTURE_CHECK przed nim) przez `build_coupon.py` do PDF — zawsze jednym
   poleceniem `rebuild_day.py`, które najpierw odświeża stare ceny. Strażnik
   `STALE_CONFIDENCE` w `build_coupon_pdf.py` porównuje `08_confidence.json`
   z `05_sheet.json`, `vetoes.json`, `reads.json` i kalibracją;
   `STALE_COUPON` porównuje `11_coupon.json` z `08_confidence.json`,
   `08_confidence_sports.json` i `read_requests.json`. Sam PDF bez
   `build_coupon.py` odmówi. `06_coupon.json` (COUPON) też czyta weta — to
   selektor cenowy, nie kupon; `run_pipeline.py --only COUPON` utrzymuje go
   zgodnym dla `audit_coupon.py` (`rebuild_day.py` robi to, gdy 06 jest
   starszy niż arkusz / weta / odczyty).
3. **Weto i odczyt, które nie trafiły, muszą zostać zgłoszone.** Etapy
   drukują `UNMATCHED_VETO` / `UNMATCHED_READ`; cichy no-op czyta się
   identycznie jak weto uszanowane.
4. **Odczyty weryfikatora też przebudowują dzień.** Dopisane do
   `reads.json` → przebudowa jak w kroku 7 → ponownie `audit_coupon` i
   `audit_variants`. Jeśli przebudowa wstawiła do top 30 nogę, której nikt
   nie przeczytał (pozycje się przesunęły), C3 to pokaże: te nogi wracają do
   analityka danego sportu.

### Scalanie wet — walidacja przed zapisem, zawsze

```python
from pydantic import RootModel
from bet.sofa.contracts import SheetRow, Veto
from bet.sofa.veto import find_unmatched_vetoes

vetoes = RootModel[list[Veto]].model_validate(merged).root      # NAJPIERW
rows = RootModel[list[SheetRow]].model_validate_json(
    open(f"runs/sofa/{date}/05_sheet.json").read()).root
unmatched = find_unmatched_vetoes(rows, vetoes)                 # potem raport
```

`Veto` ma `extra="forbid"`. Jeden wymyślony klucz (`action`, `player`,
`event_id`) wywraca **cały plik** i **zatrzymuje przebudowę** (`LegRead`
w `reads.json` tak samo — walidacja `RootModel[list[LegRead]]`, potem
`load_reads`): COUPON rzuca
wyjątek (`run_pipeline.py` melduje FAILED, kod 2), a `run_confidence.py`
pada na nieprzechwyconym `ValidationError` z kodem 1 — co czyta się jak
PARTIAL, jeśli nie przeczyta się tracebacku. Żaden z nich nie zapisuje
artefaktu, więc na dysku zostają poprzednie 06/08/11 i PDF, wyglądające na
aktualne. Waliduj przed każdą przebudową.

---

### Dziennik i rozliczenie D-1 — domyślnie

Każdy `/sofa-day` robi, bez pytania, po SETTLE / CS2_SETTLE / SHADOW_SETTLE:
`audit_settlement.py` (7c per sport, 7i), `audit_settle_identity.py`
(przypięte id sportów mierzonych: `ID_USED_TWICE`, `MOVED_GRADED`,
`NAME_BELOW`, `ORIENTATION_IDS`, `ID_CHANGED`, `IDENTITY_STATE`,
`IDENTITY_PENDING`), `audit_shadow.py`, `audit_cs2.py` i `record_results.py`
(dziennik `runs/sofa/ledger/results.jsonl`, jeden wiersz na dzień i grupę:
`official`, `official:pre_stats_only`, `removed:reads`, `measure:<sport>`),
czytany przez `audit_ledger.py` — grupy epok (do 10-04 /
10-05 rano / stats_only), nigdy łącznie. Kod 0 także przy pozycjach
oczekujących (widać je w tabeli); 1 tylko przy `MISMATCH` albo nieczytelnym
pliku; 2 przy awarii lub braku bazy.

## 3. Kontrakt analityka

**Wejście:** data, `run_id`, werdykty etapów, lista nóg jego sportu do
przeczytania (z `confidence.legs_requiring_read` nad `11_coupon.json`, w tym
pozycje z `read_requests.json`), i to, co się wywaliło. **Nie** opinia zlecającego o konkretnym meczu —
to byłaby prośba o potwierdzenie, nie o analizę.

**Wyjście:** markdown po polsku + **dwie** ogrodzone tablice JSON: weta
(`[]` to normalna, zdrowa odpowiedź), potem odczyty — jeden `LegRead`
(`author: "analyst"`) na każdą nogę do przeczytania: pierwsze 30 pozycji
`11_coupon.json`, każdą nogę wydrukowanego buildera i pozycje z
`read_requests.json` — w jego sporcie. `sofa-analyst-sport` oddaje tylko
odczyty (weto nie ma strony ani okresu). Na nodze stoją trzy liczby i tylko
jedna jest pewnością: **pewność** (`confidence`, ze statystyk,
skalibrowana), **próbka** (k z n, `sample_hit_rate`), **model**
(`forecast_p`, nieskalibrowany); cena jest tylko filtrem. WATCH to noga, której by nie postawił, choć nie
umie nazwać jej zepsutą; zepsuta próbka to nadal weto, nie NO_BET.

**Kolejność pracy** (z `sofa-analysis-core`):

1. **Inwentarz.** Mecze swojego sportu, udział READY, nogi jego sportu w
   `11_coupon.json` **policzone samodzielnie** (pozycje, zablokowane, nogi
   builderów, `removed_by_reads`), ile z nich jest do przeczytania.
2. **Punkt decyzyjny — przed jakimkolwiek narzędziem webowym.** Oba zegary,
   `now`, różnica. Mecz, który się zaczął, wypada **tutaj**, a nie po
   researchu: tytuły i snippety wyszukiwarki **są treścią**, więc analiza
   spóźniona jest wystawiona na wynik. Jeśli wynik przecieknie — nazwij to
   i oznacz twierdzenie `CANNOT VERIFY`.
3. **Weryfikacja tożsamości.** Ani w piłce, ani w tenisie **nie ma źródła
   prawdy** poza artefaktami: `sofa` czyta statystyki Sofascore i ceny
   Superbet, a bzzoiro **nie jest źródłem i nie wolno go wołać** (do
   2026-09-23 ten punkt kazał piłce pytać bzzoiro o status meczu — instrukcja
   sprzeczna z kontraktem agenta). Tożsamość i zegary: `02_fixtures.json`
   (`identity`, oba zegary); resztę web, dwie niezależne domeny, tag
   `[WEB: domena, fetched <UTC>]` — a „niezweryfikowane" jest często odpowiedzią
   uczciwą i tak trzeba je podać.
4. **Protokół per mecz** z odpowiedniego skilla sportowego, w jego kolejności.
   Cena **ostatnia**.
5. **Blok wet, potem blok odczytów.**

**Terminarz i skład próbki są od 2026-10-04 w artefaktach.** Blok
`schedule` w `03_samples.json` i `context_flags` na nogach mówią, czy mecz
jest przełożony (`MAKEUP_FIXTURE` — wtedy trzeba ustalić, *dlaczego*:
choroba, pogoda, boisko), ile dni odpoczynku miała każda strona i ile
meczów w 7 / 14 dniach. Historia nie zawiera już sparingów ani turniejów
przedsezonowych (`bet.sofa.comparability`), a próbki goli w piłce
(`goals_total`, `goals_for`, `goals_1h_for`, `goals_2h_for`) biorą tylko
regularne mecze rozgrywek tego meczu, gdy jest ich co najmniej pięć — mecz
pucharowy albo sparing w takiej próbce to defekt do zgłoszenia.

**Kupon, nie tylko arkusz.** Odczyt, który ocenia wiersze arkusza i nigdy nie
otwiera `11_coupon.json`, opisuje dzień, którego nikt nie postawił. Trzeba
ocenić też **legi i buildery**, a przed stwierdzeniem „tego wiersza nie ma"
zajrzeć do `06_dropped.json`.

**Priorytety ponad obowiązkowy zbiór** (niedziela to 1000+ meczów piłki i nikt
ich nie przeczyta; obowiązkowy jest tylko zbiór C3):

1. nogi z `legs_requiring_read` — top 30, nogi wydrukowanych builderów,
   prośby operatora;
2. pozostałe nogi `11_coupon.json`, od najwyższej pozycji;
3. piłka: rynki `*_1h_*` / `*_2h_*` (cienkie bazy; przy n=8 wiersz jest w 76%
   priorem ligowym). Tenis: mecze z `ground_type` albo
   `default_period_count` = `null` — zakres próbki wtedy **nie zadziałał**.

**Gdzie skończyłeś — powiedz.** Mecz nieprzeczytany to `NIE PODANO`, nigdy
milczenie.

**Czego analitykowi nie wolno:**

- wetować za bramkę, którą kod już stosuje (`STALE_PRICE`, `STALE_SAMPLE`,
  `ODDS_TOO_LOW`, `KICKOFF_TOO_SOON`, `MODE_LOSES`, `LINE_BEYOND_SAMPLE`,
  `THIN_SAMPLE_FOR_BUILDER`, a w piłce
  `MODEL_ABOVE_OWN_SAMPLE`) — to dopisuje szum, w którym giną prawdziwe powody;
- podawać `FUZZY` jako potwierdzoną tożsamość;
- brać ceny z otwartego webu ani z innego bukmachera czy agregatora — jedyna
  cena w `sofa` to Superbet (`04_offer.json`, a w arkuszu `market_p`);
- podawać własnej ceny łączonej;
- proponować stawki.

**Szerokość weta trzeba policzyć przed wysłaniem.** Nie ma pola „zawodnik";
weto z `subject: null` obejmuje **każdy podmiot** na tym meczu — odczyt WATCH
albo NO_BET tak samo. Jeśli trafia szerzej, niż zamierzałeś — zawęź go, a jeśli
się nie da, opisz prozą i powiedz, że nie zostało zastosowane.

---

## 4. Kontrakt weryfikatora

`sofa-verifier` pracuje **iteracyjnie**: znajdź problem, zgłoś, weryfikuj **od
nowa**, aż pełna runda nie przyniesie nowego znaleziska. Protokół:
[`VERIFY_PROTOCOL.md`](VERIFY_PROTOCOL.md).

Sedno podziału pracy: `audit_coupon.py` sprawdza wiersz **wobec niego samego**.
Wiersz, którego wszystkie pola są wzajemnie spójne i wszystkie zbudowane na
złej próbce, przechodzi ten audyt. Agent robi więc cztery rzeczy, których
skrypt nie umie: odtwarza wiersz z `03_samples.json`, sprawdza, czy `subject`
wskazuje stronę, którą twierdzi, dopytuje Superbet o **żywą** cenę tym samym
`OfferFetcher`, i testuje rozkłady dnia pod kątem antyselekcji.

Weryfikuje `11_coupon.json` i PDF: top 30, nogi builderów i nogi sportów
mierzonych. `audit_variants.py` robi część mechaniczną: C1 (świeżość
artefaktu i PDF), C2 (każdy wydrukowany singiel spełnia swoje pokrętła;
noga zablokowana wobec `printed_under`), C3 (odczyty), U1 (kolejność
`coupon_order`, pozycje 1..N, zablokowane na górze bez numeru), U2 (każdy
świeży singiel piłki i tenisa ma epokę `stats_only`), U3 (każda świeża noga
sportu odtworzona z surowej migawki Superbetu z chwili budowy
`08_confidence_sports.json`: kurs, czas i wiek ceny, marża grupy ≤ 15%,
x ≥ 0,90, pewność = kubełek kalibracji `forecast_p`). Nogi zablokowanej nie
oznacza się `NO_BET` za to, że dziś by nie przeszła — jest zapisem wydruku.

**Produktem jest lista wierszy, których NIE postawiłby, mimo że pipeline je
wybrał.** Nie lista poleconych. Od 2026-10-04 oddaje ją także jako
ogrodzoną tablicę `LegRead` (`author: "verifier"`): `NO_BET` za defekt
(zła strona, nieaktualna albo błędna cena, arytmetyka, która się nie
odtwarza), `WATCH` za osąd. Sam nie pisze pliku — zlecający dopisuje
tablicę do `reads.json` i przebudowuje dzień (krok 9 wyżej). Porównanie
`model_p` z trafialnością własnej próbki dla piłki robi już kod
(`MODEL_ABOVE_OWN_SAMPLE`); oficjalna noga piłkarska ponad tą luką to
defekt. `audit_variants` C3 sprawdza, że każda noga z `legs_requiring_read`
ma odczyt analityka i żadna wydrukowana nie ma WATCH ani NO_BET. Na koniec werdykt i **żadnej rekomendacji
stawki** — `K_PRICE` i `MAX_LADDER_SIGMA` są `NOT_FITTED` i każdy wiersz o tym
mówi; decyzja o stawce należy do operatora.

---

## 5. Kontrakt rozliczającego

`sofa-settler` jest właścicielem jedynej pętli między dniami. Jego dwie
decyzje: **czy rozliczenie jest wiarygodne** i **czy fitować stałe** — przy
czym drugą odpowiedzią jest zwykle „nie".

- **Nigdy w środku dnia.** `fit_constants.py` stoi poza `DEFAULT_SEQUENCE`
  celowo.
- Fituj, gdy: rozliczona tabela urosła istotnie, kontrola spójności nie
  przechodzi, albo baza jest demonstracyjnie zła. **Nie dlatego, że dzień
  poszedł źle.**
- Po fitowaniu raportuj **zawsze**: `fitted_from` i o ile się ruszyło,
  `half_match_coherence`, status **każdej** stałej. `null` ze statusem
  `NOT_FITTED` to **poprawny wynik, nie luka**.
- Nigdy nie edytuj stałej ręcznie. Fituj albo zgłoś.
- Co dzień rozlicza D-1: 7c kuponu per sport + suma kuponu (nogi sportów
  mierzonych po kursie z wydruku i po przypiętym id, inaczej
  `NOT_GRADED:ID_CHANGED`), zwroty osobno (`MOVED_BEYOND_VOID` — mecz
  przesunięty o > 48 h, `AWARDED` — walkower; 0 j., nigdy przegrana i nigdy
  `sofa_settled_row`), 7i `removed_by_reads` osobno; `audit_settle_identity.py`;
  dziennik `record_results.py` (`runs/sofa/ledger/results.jsonl`, jeden
  wiersz na dzień i grupę); wyniki nigdy się nie sumują. Noga wydrukowana
  bez wiersza arkusza rozlicza się do `07_settled_printed.json`, nie do
  `sofa_settled_row`; nogi sportów nigdy nie trafiają do `sofa_settled_row`
  ani `fit_confidence`.

Szczegóły higieny plików konfiguracyjnych: [`CONFIG.md`](CONFIG.md).

### Skaner nisz — po rozliczeniu, jako dowód, nie lista zakładów

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_niches.py --from 2026-09-17 --to <D-1>
```

Pyta, czy w jakiejś komórce **liga × rynek × kierunek [× przedział kursu]**
(albo kraj/poziom z `02_fixtures.json`) cena Superbeta jest systematycznie zła
**poza próbą** i **ponad własną marżą** tej komórki. Wzorzec już wyceniony
(„w tej lidze zawsze 10+ rożnych" przy linii 11,5) nie jest niszą.

- **Walk-forward:** komórki na dzień D wybiera się wyłącznie z dni < D; wagę
  ściągania (K, K_rynku) też — dopasowaną Brierem na wcześniejszych dniach.
  Wynik główny to ROI selektora poza próbą przy wydrukowanych kursach, obok
  bazy (te same rynki i kierunki, bez wyboru ligi).
- **Dwupoziomowe ściąganie:** bias komórki → bias rynku → zero (cena).
  Surowa średnia na małym n to dokładnie złudzenie, którego szukamy.
- **Jeden szczebel na pytanie** (linia najbliżej 0,5, remis → niższa), liczone
  są **mecze**, przedziały to bootstrap po meczach; `market_p` przeliczane
  z wydrukowanej pary OVER/UNDER, bo 2,7% par miało je z innego odświeżenia
  oferty.
- **Kandydat** = ściągnięty bias pokonuje marżę na całości **i** ROI poza
  próbą > 0 **i** komórka przechodzi Benjaminiego–Hochberga (FDR 0,10) na
  wszystkich przeskanowanych komórkach. Reszta obiecujących to **lista
  obserwacyjna** z liczbą meczów, jakiej brakuje.
- Wiersze `cache-calibration` nie mają ceny — tylko **opisują** stabilność
  surowego wzorca ligi, nigdy nie są dowodem złej wyceny.

Pisze `reports/sofa_nisze_<to>.md` (po polsku) i `.json`; `audit_settlement`
streszcza ostatni werdykt pod nagłówkiem **7h** („Nogi
zdjęte przez odczyt” to 7i od 2026-10-05, `04094d92`) — osobno od 7c (kupon), nigdy z nim nie łączony. Skaner **niczego nie zasila** (COUPON,
CONFIDENCE, SHEET, weta), nie zmienia stałych i nie jest w `DEFAULT_SEQUENCE`.
Pierwszy przebieg (2026-09-17…28): **brak niszy** — 0 z 1506 komórek po BH;
przewaga +5% ROI wymaga ~7 800 meczów w jednej komórce po korekcie, a największa
ma 58. Czytaj go jako dowód, nie jako listę typów; decyzja o stawce należy do
operatora.

---

## 6. Kontrakt zwiadowcy rynku

`sofa-market-scout` rozdziela dwie osie, których nie wolno łączyć:
**czy DA SIĘ to postawić** (mecz na tablicy, rynek na tym meczu, kierunek
wystawiony, obie strony wycenione, więc devig jest w ogóle możliwy) i **czy
warto tej ceny** (`required_odds`, nadwyżka, i strukturalne zniżki, których
nadwyżka nie pokazuje).

Czyta też ślepą plamę, której nie zapisuje żaden inny artefakt —
`unmapped_markets` (20 851 w ofercie z 2026-09-21; liczba zmienia się
z każdym odświeżeniem, więc bierz ją z artefaktu) — i mówi, do których z nich
sięgnęłaby próbka, którą już mamy, a do których nie.

---

## 7. Zasady wspólne dla każdego agenta w tym repo

- **`06_coupon.json` nie jest kuponem. Kuponem jest PDF.**
- Nigdy nie wymyślaj liczby, meczu, ceny ani dostępności.
- Nigdy nie podawaj ceny łączonej spoza tego, co policzył `confidence.py`.
- Żadnego dobierania stawki, żadnego stawiania automatycznego.
- Nigdy nie czytaj, nie wypisuj i nie loguj `.env`.
- Nigdy nie usuwaj `UNFITTED_CONSTANTS` z raportu.
- **Liczby od podagenta sprawdzaj, gdy da się sprawdzić lokalnie.** Jedno
  adwersaryjne przejście po pliku jednego agenta znalazło osiemnaście błędów,
  z czego dwa odwracały wniosek.
- Pominięta kontrola musi zostać **nazwana**. Milczenie o pominiętej kontroli
  czyta się jak kontrola zdana. Jeśli przebieg poszedł gładko, napisz, że
  bezpiecznika **nie przetestowano** — nie że „działa".

---

## 8. Wzór raportu końcowego dnia

```
KUPON:    runs/sofa/<data>/KUPON_<data>.pdf — <n> pozycji (+ <n> zablokowanych, + <n> builderów B1..) z 11_coupon.json
SEKCJE:   piłka <n> · tenis <n> · hokej <n> · koszykówka <n> · siatkówka <n> · CS2 <n> (sport NOT_CALIBRATED / NOT_IDENTIFIED: <…>)
TOP 30:   przeczytane <n>/30 (+ <n> nóg builderów, + <n> z read_requests.json); poza top 30 drukuje się bez odczytu: <n> nóg
SHEET:    <n> wierszy (<n> piłka / <n> tenis) · epoka stats_only
RUN:      <run_id> · <werdykt> · <n> na tablicy → <n> dopasowanych (<x>%) → <n> READY
SPORTY:   SPORT_IDENTITY <n> IDENTIFIED / <n> NOT_IDENTIFIED · SPORT_CONFIDENCE <werdykt> · FIXTURE_CHECK <n> sprawdzonych, <n> UNVERIFIED, <n> FIXTURE_NOT_AS_SCHEDULED
WETA:     <n> zastosowanych, <n> bez dopasowania
READS:    analityk <n> (KEEP <n> / WATCH <n> / NO_BET <n>) · weryfikator <n> (WATCH <n> / NO_BET <n>) · UNMATCHED_READ <n> (nogi sportów: sprawdzone w 11)
ZDJĘTE:   removed_by_reads <n> — <każda noga: sport, mecz, rynek, linia, kierunek, autor, powód (analyst / verifier / auto)>; rozliczane osobno (7i), nie kupon
ANALIZY:  runs/sofa/<data>/<data>_analiza_<sport>.md (football, tennis, i każdy sport mierzony z nogą do przeczytania)
SETTLE:   D-1 7c per sport + suma kuponu <u> j.; zwroty <n> (MOVED_BEYOND_VOID / AWARDED); 7i <u> j.; audit_settle_identity <n> znalezisk
POMIAR:   D-1 CS2 <n> serii / hokej <n> / kosz <n> / siatka <n> rozliczonych — pomiar ceny, osobno
D-1 DZIENNIK: official <u> j. · removed:reads <u> j. · measure/rule per sport (każdy osobno, nigdy sumowane; grupy epok) · MISMATCH <n> (audit_ledger.py)
CLV D-1:  kupon <x%> [lo; hi] (audit_clv.py)
AUDYTY:   audit_coupon <n> · audit_variants C1–C3, U1–U3 <n> znalezisk (C3: <n> nóg bez odczytu analityka - musi być 0)
WERYFIKACJA: <n>/<n> arytmetyka, <n>/<n> ceny na żywo, <n> pozycji odrzuconych (zapisane w reads.json i przebudowane: tak/nie)
UWAGA:    <największa słabość dnia, jedna>
```

Cytuj `run_id` i werdykt **każdego** etapu, nie tylko porażek. Liczby sekcji
i top 30 policz sam z `11_coupon.json`.
