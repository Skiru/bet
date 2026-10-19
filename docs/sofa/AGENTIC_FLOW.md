# `sofa` — orkiestracja agentowa

Kto co uruchamia, w jakiej kolejności, co wolno każdemu agentowi i gdzie
przebiega przekazanie. Mechanika etapów: [`PIPELINE.md`](PIPELINE.md);
kolejność dnia i „co jeśli”: [`RUNBOOK.md`](RUNBOOK.md). Tutaj są **role**.
Źródłem prawdy są pliki w `.claude/` — ten dokument je streszcza.

---

## 1. Inwentarz — co jest w `.claude/`

### Jeden właściciel każdej procedury

| procedura | właściciel (plik, który ją opisuje) | kto ją uruchamia |
|---|---|---|
| cały dzień | `.claude/commands/sofa-day.md` | sesja główna (`/sofa-day`) albo agent `sofa-runner`, który czyta ten sam plik |
| odczyt analityków | `.claude/commands/sofa-analyze.md` | `/sofa-analyze`; kroki 5–7 dnia powtarzają tylko jego polecenia |
| przebudowa | `.claude/commands/sofa-rebuild.md` | `/sofa-rebuild`; każdy krok dnia, który przebudowuje |
| rozliczenie D-1 | `.claude/agents/sofa-settler.md` | `/sofa-settle` i krok 1 dnia uruchamiają agenta |
| weryfikacja | `.claude/agents/sofa-verifier.md` | `/sofa-verify` i krok 8 dnia uruchamiają agenta, potem scalają i przebudowują |

Procedura jest zapisana raz. Komenda, która uruchamia agenta, mówi tylko,
**co** ma być zrobione i w jakiej kolejności; polecenia zna właściciel.

### Komendy (`/…`)

| komenda | co robi | sieć |
|---|---|---|
| `/sofa-day [data]` | most → `sofa-settler` (D-1) → dowody linii → BOARD…COUPON → CONFIDENCE → SHADOW / CS2 → SPORT_IDENTITY → SPORT_CONFIDENCE → COUPON_ASSEMBLY → analitycy → `merge_reads.py` → `rebuild_day.py` (PDF) → pętla C3 → `sofa-verifier` → przebudowa → `day_status.py` → raport | Sofascore (most) + Superbet |
| `/sofa-analyze [data] [dodatkowo: …]` | prośby operatora do `read_requests.json`, `read_set.py`, analitycy, `merge_reads.py`, przebudowa, pętla C3 | Superbet (gdy cena stara) |
| `/sofa-rebuild [data]` | przebudowa z artefaktów jednym poleceniem `rebuild_day.py` | Superbet (stara cena), most dla FIXTURE_CHECK / SPORT_IDENTITY |
| `/sofa-verify [data]` | `sofa-verifier`, scalenie jego odczytów, przebudowa | Superbet (ceny na żywo) + web |
| `/sofa-settle [data]` | `sofa-settler` dla dnia zakończonego | Sofascore (most) |

Argument: `dzisiaj` / `wczoraj` / `YYYY-MM-DD`; pusty = dzisiaj. **Doba
kuponu jest w UTC dla każdego sportu.**

### Agenci

| agent | rola | model | pisze |
|---|---|---|---|
| `sofa-runner` | dzień jako podagent: czyta i wykonuje `sofa-day.md`, zwraca raport dnia | sesji | dane tylko przez skrypty |
| `sofa-analyst-football` / `-tennis` | odczyt nóg ze swojego pliku `read_set`, weta + jeden odczyt na nogę | sesji | **tylko swój raport** |
| `sofa-analyst-sport` | to samo dla jednego sportu mierzonego (hokej / kosz / siatka / CS2); tylko odczyty (strona, okres) | sesji | tylko swój raport |
| `sofa-verifier` | adwersaryjna weryfikacja zbudowanego dnia; nogi, których by nie postawił, jako odczyty `author: "verifier"` | sesji | tylko swój raport |
| `sofa-settler` | rozliczenie D-1, audyty, dziennik, opinia o refitowaniu (domyślnie „nie”) | `sonnet` | nic |
| `sofa-market-scout` | czy da się postawić i czy warto tej ceny; ślepa plama `unmapped_markets` | `sonnet` | `runs/sofa/<d>/market_coverage.json` / `.md` przez `report_market_coverage.py` (gdy ich brak) |

- **Żaden agent nie ma `Write` ani `Edit`.** Przebieg, który potrzebuje
  edycji pliku, potrzebuje człowieka. Raport analityk i weryfikator zapisują
  jednym heredokiem przez Bash; dane dnia powstają tylko przez skrypty.
- **Agenci nie dostają `CLAUDE.md`** (`omitClaudeMd: true` w każdym
  `sofa-*`). Ich wspólnym kontraktem jest wczytany skill `sofa-pipeline`;
  `CLAUDE.md` jest dla sesji głównej.
- **Routing modeli:** `sofa-settler` i `sofa-market-scout` biegną na
  `sonnet` (uruchamianie skryptów i raport; refit i tak wymaga zgody
  operatora). Analitycy i weryfikator — na modelu sesji (bez linii `model:`).
- Definicje agentów i skille wczytują się na starcie sesji: poprawka wchodzi
  w **następnej** sesji — nie pisz, że „już działa”.

### Skille

| skill | do czego | wczytany do |
|---|---|---|
| `sofa-pipeline` | wspólny kontrakt: kupon, etapy, reguły druku, kanały (weta, odczyty, prośby), twarde zasady | każdego agenta `sofa` |
| `sofa-analysis-core` | kontrakt analityka: plik `read_set`, kolejność artefaktów, punkt decyzyjny, bloki JSON, raport do pliku | trzech analityków |
| `football-analysis` / `tennis-analysis` | metoda sportowa | analityk danego sportu |
| `bet-slip-audit` | wycena slipa z ekranu operatora | na żądanie |

Gdy dwa źródła mówią co innego: **kod > artefakt > skill > plik agenta**.

---

## 2. Pełny dzień agentowo

```
operator: /sofa-day 2026-10-20
   │
   ├─ 0. most          ensure_bridge.py (liczy się wiek pobrania, nie ok:true)
   ├─ 1. D-1           Task → sofa-settler (sesja główna: w tle, powiadomienie o końcu; podagent:
   │                   pierwszy plan): SETTLE, CS2_SETTLE / SHADOW_SETTLE tylko gdy pętla D-1 nie żyje,
   │                   audit_settle_identity, resettle_sweep, record_results, audit_ledger, audit_clv,
   │                   audit_settlement 7c / 7i; BOARD w sesji głównej obok; RESOLVE po powrocie
   ├─ 1a. dowody linii najpierw część mostowa (refresh_sport_history.py, backfill_event_stats.py —
   │                   pisze data/sofa.db, więc przed RESOLVE), potem dopasowania
   │                   refresh_line_evidence.py --before <D> --skip-history (tylko czytają bazę)
   │                   w tle obok kroku 2; krok 3 czeka na ich „EXIT”
   ├─ 1b. pętle        cs2_daily / shadow_daily --chain (warunki startu: sofa-day.md);
   │                   capture_closing startują pętle same
   ├─ 2. dzisiaj       run_pipeline.py: BOARD (nadaje run_id, odczyt z linii SOFA_SUMMARY)
   │                   → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON (nohup, log, krótkie grep)
   ├─ 3. CONFIDENCE    run_confidence.py (tymczasowy)
   ├─ 4. sporty        SHADOW, CS2 → SPORT_IDENTITY → SPORT_CONFIDENCE → COUPON_ASSEMBLY (11)
   │                   bez PDF: wydruk tymczasowy zablokowałby nieprzeczytane nogi
   ├─ 5. analitycy     read_set.py --buffer 25 --split 12 → jedna instancja na plik,
   │                   wszystkie w JEDNEJ wiadomości, na pierwszym planie
   ├─ 6. scalenie      merge_reads.py --report <ścieżka ZWRÓCONA przez analityka> [--report …] --author analyst
   ├─ 7. przebudowa    rebuild_day.py (pierwszy PDF) → audit_variants C3;
   │                   pętla: read_set.py --unread --split 12 → analitycy (_r<n>) → scalenie
   │                   → przebudowa; najwyżej 3 rundy
   ├─ 8. weryfikacja   Task → sofa-verifier → merge_reads.py --author verifier → rebuild_day.py
   ├─ 9. stan          day_status.py; capture_closing tylko przy WARN; run_boosts.py
   └─ raport           wzór w części 8
```

Polecenia z flagami są w `sofa-day.md`; najważniejsze:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/read_set.py --date <d> [--buffer N] [--unread] [--split K] [--out-dir <dir>]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/merge_reads.py --date <d> --report <md> [--report <md> ...] [--author analyst|verifier] [--dry-run]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <d> [--dry-run] [--skip-audits]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/day_status.py --date <d>
```

### Zbiór do przeczytania — `read_set.py`

Zbiór C3 to `confidence.legs_requiring_read`: niezablokowane nogi 30 meczów
o najlepszej wartości (`read_unit: "event"`, `read_order: "value"`), każda
noga wydrukowanego buildera i każda prośba z `read_requests.json`. Reszta
kuponu drukuje się bez odczytu (decyzja operatora). `read_set.py` zapisuje go
jako `runs/sofa/<d>/read_set/read_set_<sport>[_<i>].json` (zwarte nogi:
pozycja, `group_key`, mecz, rynek, linia, kierunek, okres, nazwa Superbetu,
pewność, kurs, `locked`, `price_gap`, `in_set` = `required` / `buffer`):

- `--buffer N` — także N kolejnych meczów w tej samej kolejności; przebudowa
  tasuje trzydziestkę, więc bufor przeczytany teraz oszczędza rundę C3
  (25 na budowie tymczasowej, 0 na końcowej);
- `--split K` — części po najwyżej K całych meczów, jedna instancja
  analityka na część (dwa krótkie konteksty są tańsze niż jeden długi);
- wypisuje jedną linię na sport / część: `<n> legs, <n> matches (<n>
  required, <n> buffer)` — liczby required / buffer to **nogi**;
- `--unread` — tylko nogi bez odczytu analityka (reguła C3); używane w każdej
  rundzie po przebudowie.

### Kontrakt przekazania analityk → maszyna

1. Zlecający podaje: `date`, `run_id`, sport, ścieżkę pliku `read_set` i
   ścieżkę raportu `runs/sofa/<d>/<d>_analiza_<sport>[_<część>][_r<n>].md`
   (nigdy istniejący plik — następny wolny sufiks). **Żadnej własnej opinii**
   o meczu: to byłaby prośba o potwierdzenie.
2. Analityk zapisuje cały raport (po polsku) jednym heredokiem, z blokami
   ` ```json vetoes ` (tylko piłka i tenis) i ` ```json reads `, i zwraca
   zlecającemu najwyżej 12 linii: ścieżkę, liczbę nóg, KEEP / WATCH / NO_BET,
   liczbę wet i to, na co trzeba zareagować. Innych plików nie pisze.
3. Zlecający uruchamia `merge_reads.py` na ścieżce, którą analityk
   **zwrócił** (może dodać `_r<n>`; jeden plik `read_set` = jeden raport -
   na części dzieli zlecający, `read_set.py --split`, analityk nigdy);
   jedno wywołanie przyjmuje kilka `--report`, nigdy dwa wywołania naraz.
   Nigdy nie przepisuje tekstu ani tablic analityka. Kod wyjścia: 0 scalone;
   1 scalone, ale weto nic nie trafiło (`UNMATCHED_VETO` — zgłosić); 2 odmowa,
   nic nie zapisane — analityk (lub weryfikator) jest uruchamiany ponownie z
   komunikatem i ścieżką `_r<n>`; nikt nie poprawia jego JSON-a; po 2
   ponownych uruchomieniach zgłosić porażkę.
4. Weryfikator tak samo: `runs/sofa/<d>/<d>_weryfikacja[_r<n>].md`,
   scalenie z `--author verifier`.

### Kanały do produktu

Osąd agenta wchodzi do kuponu **tylko** dwoma plikami w `runs/sofa/<d>/`;
trzeci jest prośbą, nie werdyktem:

| plik | co | kto czyta | skutek |
|---|---|---|---|
| `vetoes.json` | weto (`contracts.Veto`) na próbkę lub kontekst: `SAMPLE_UNINFORMATIVE`, `CONTEXT`, `PRICE`, `OTHER` | COUPON, CONFIDENCE, COUPON_ASSEMBLY | wiersz zdjęty wszędzie; kierunek tylko OVER/UNDER, więc nogę sportu mierzonego zdejmuje się odczytem |
| `reads.json` | odczyt (`contracts.LegRead`): KEEP / WATCH / NO_BET, `author` analyst / verifier, dla sportu strona i okres | CONFIDENCE, COUPON_ASSEMBLY | WATCH i NO_BET zdejmują nogę do `removed_by_reads` (rozliczane osobno, 7i, dziennik `removed:reads`); KEEP zapisuje, że przeczytano |
| `read_requests.json` | prośba operatora o odczyt (`requested_by`, `at_utc`, `position` albo `group_key` [+ `market`, `line`, `direction`]) | `legs_requiring_read`, COUPON_ASSEMBLY | poszerza zbiór C3; nic nie zdejmuje |

- Oba schematy są ścisłe (`extra="forbid"`): jeden zły klucz wywraca cały
  plik i zatrzymuje przebudowę, a stare 08 / 11 / PDF zostają na dysku,
  wyglądając na aktualne — dlatego pisze je tylko `merge_reads.py`, który
  waliduje przed zapisem.
- Odczyt się tylko dopisuje; WATCH i NO_BET wygrywają z KEEP, kto by ich nie
  napisał. Wcześniejsze weta przechodzą dalej.
- `subject: null` obejmuje każdy podmiot meczu, `period: null` każdy okres.
- Odczyt sportu mierzonego `run_confidence.py` liczy jako `reads_sport`;
  działa w COUPON_ASSEMBLY (sprawdź `removed_by_reads` w `11_coupon.json`).
  Każdy `UNMATCHED_READ` / `UNMATCHED_VETO` / `UNMATCHED_READ_REQUEST` to
  osąd, który nic nie zrobił — zgłosić.
- Automatycznie, bez odczytu: `MODEL_ABOVE_OWN_SAMPLE` (piłka) też ląduje w
  `removed_by_reads`; `FIXTURE_NOT_AS_SCHEDULED` z FIXTURE_CHECK odmawia w
  CONFIDENCE.

### Pętla C3

`audit_variants` C3 (na końcu każdej przebudowy) sprawdza, że każda noga
zbioru ma odczyt `author: "analyst"` i żadna wydrukowana nie niesie WATCH /
NO_BET. Przebudowa przesuwa pozycje, więc po każdej: `read_set.py --date <d>
--unread --split 12` (`--buffer 5`, gdy wczesne mecze wciągają nowe) →
analitycy tylko na tych plikach → scalenie → przebudowa, aż C3 czyste,
najwyżej 3 rundy. Pusty zbiór przy czerwonym C3 znaczy, że wydrukowana noga
niesie WATCH / NO_BET albo brak `reads.json` — wtedy `rebuild_day.py`, nie
kolejny odczyt.
WATCH na nodze buildera każe builderowi wziąć następnego kandydata — w tej
rundzie analityk czyta wszystkich kandydatów buildera tego meczu. Odmowa na
nodze zablokowanej to notatka, nie defekt. PDF drukuje się mimo znalezisk C3,
więc nogi, które w międzyczasie wystartowały, zostają zablokowane bez
odczytu — raport je wymienia.

---

## 3. Kontrakt analityka

Właściciel: skill `sofa-analysis-core` i pliki `sofa-analyst-*`. W skrócie:

- czyta dokładnie nogi swojego pliku `read_set`, najpierw `required`;
- na nodze waży **pewność** (`confidence`, skalibrowana ze statystyk),
  **próbkę** (k/n) i **model** (`forecast_p`, nieskalibrowany); cena to
  tylko filtr zakładu;
- punkt decyzyjny przed jakimkolwiek wyszukiwaniem: mecz, który się zaczął,
  wypada przed researchem; web — dwie niezależne domeny, otagowane;
  „niezweryfikowane” bywa uczciwą odpowiedzią;
- źródła: tylko Sofascore i Superbet z artefaktów dnia oraz otwarty web;
  **bzzoiro ani żaden inny dostawca**;
- weto i odczyt tylko zdejmują; nie wetuje za bramkę, którą kod już stosuje;
- nie podaje ceny łączonej ani stawki;
- noga nieprzeczytana jest nazwana, nigdy przemilczana.

## 4. Kontrakt weryfikatora

Właściciel: `sofa-verifier.md` (protokół: [`VERIFY_PROTOCOL.md`](VERIFY_PROTOCOL.md)).
Robi to, czego skrypt nie umie: odtwarza nogi z `03_samples.json`, sprawdza
stronę `subject` i tożsamość meczu sportu, dopytuje Superbet o żywą cenę tym
samym klientem, testuje rozkłady dnia pod kątem antyselekcji. Produktem jest
lista nóg, których **nie** postawiłby — w raporcie i jako blok odczytów
(`NO_BET` za defekt, `WATCH` za osąd). Noga zablokowana to zapis wydruku,
nie defekt. Żadnej rekomendacji stawki.

## 5. Kontrakt rozliczającego

Właściciel: `sofa-settler.md`. Rozlicza D-1 (piłka, tenis i sporty
mierzone), czyta 7c (prawdziwy wynik kuponu per sport) i 7i (nogi zdjęte
odczytem) osobno, zwroty po 0 j., zapisuje dziennik per wariant i epoka —
nigdy sumowane. Refit tylko na kopii bazy i tylko za zgodą operatora; nigdy
w środku dnia i nigdy z przebiegu dnia. Higiena konfiguracji:
[`CONFIG.md`](CONFIG.md).

## 6. Kontrakt zwiadowcy rynku

`sofa-market-scout` rozdziela dwie osie, których nie wolno łączyć: **czy da
się to postawić** (mecz na tablicy, rynek, kierunek, obie strony wycenione)
i **czy warto tej ceny** (`required_odds`, nadwyżka — arytmetyka selektora
VALUE z `06_coupon.json`, nie pewność kuponu). Czyta też `unmapped_markets`.

## 7. Zasady wspólne

- **Kuponem jest PDF** z `11_coupon.json`; `06_coupon.json` i
  `08_confidence.json` nie są kuponem.
- Nigdy nie wymyślaj liczby, meczu, ceny ani dostępności.
- Żadnej ceny łączonej / buildera, żadnej stawki, żadnego stawiania.
- Nigdy nie czytaj, nie wypisuj i nie loguj `.env`.
- Nigdy nie usuwaj `UNFITTED_CONSTANTS` z raportu.
- Liczby od podagenta sprawdzaj lokalnie, gdy się da.
- Pominiętą kontrolę nazwij; gładki przebieg znaczy „bezpiecznika nie
  przetestowano”, nie „działa”.
- Oszczędnie z wyjściem narzędzi: nie `cat` dużego JSON-a ani logu; `jq`,
  jednolinijkowy Python, `tail`.

---

## 8. Wzór raportu końcowego dnia

Pełny wzór (po polsku) jest w `sofa-day.md`, część „Report”. Otwiera go
kupon:

```
KUPON:    runs/sofa/<data>/KUPON_<data>.pdf — <n> pozycji (piłka / tenis / hokej / kosz / siatka / CS2), <n> zablokowanych, <n> Bet Builderów
SPORTY:   hokej / kosz / siatka / CS2 <status, refused>
RUN:      <run_id> · werdykt każdego etapu · <n> na tablicy → <n> dopasowanych → <n> READY
SHEET:    <n> wierszy (piłka / tenis), epoka stats_only
ODCZYTY:  przeczytane <n>/<n> wymaganych (+ bufor) · rundy C3 · nieprzeczytane
READS:    analityk / weryfikator · UNMATCHED_READ · weta
ZDJĘTE:   removed_by_reads — noga, autor, powód
POMIAR:   D-1 rozliczone CS2 / hokej / kosz / siatka — pomiar
D-1:      7c per sport · 7i osobno · zwroty · tożsamość · MISMATCH · CLV
STATUS:   day_status · pętle · UNVERIFIED · mostek NOT_CHECKED
AUDYT:    audit_coupon · audit_variants (C3 0)
WERYFIKACJA: arytmetyka · ceny na żywo · odrzucone (w reads.json i przebudowane: tak/nie) · verify_legs --all: nogi, DEFECT, NOTE
UWAGA:    największa słabość dnia
```

Cytuj `run_id` i werdykt **każdego** etapu. Liczby sekcji policz sam z
`11_coupon.json`.
