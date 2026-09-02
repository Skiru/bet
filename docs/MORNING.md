# Rano: uruchomienie dnia

Cztery kroki. Pierwszy nic nie kosztuje — i to on decyduje, czy w ogóle warto
uruchamiać resztę.

---

## 1. Sprawdź providerów (0 zapytań, ~2 s)

```bash
python3 scripts/simple/run_pipeline.py --preflight
```

```
provider                 left   limit  status
----------------------------------------------------------------
espn-football           10000   10000  usable
api-football                0     100  quota_exhausted
highlightly                 0     100  quota_exhausted
sportdb                   210     300  usable
tennis-abstract           inf     inf  usable
espn-tennis             10000   10000  usable

  football   two-provider coverage: 7 events
  tennis     two-provider coverage: 400 events

GO with --max-events 7 (quota corroborates 7, not the 40 planned).
```

Ostatnia linia to Twoja decyzja. Trzy możliwe:

| Werdykt | Co znaczy | Co robisz |
|---|---|---|
| `GO: quota corroborates all 40...` | Wszystko gra | Krok 3, bez zmian |
| `GO with --max-events N` | Limitów starczy na N zdarzeń z korroboracją | Krok 3 z `--max-events N` |
| `GO, but nothing will be corroborated` | Jeden provider na sport — wszystko wyjdzie `SINGLE_SOURCE` / `LOW` | Krok 2, albo świadomie akceptujesz słabe dane |
| `NO-GO: no usable provider` | Zero providerów | Krok 2. Bez tego nie ma sensu startować |

**„two-provider coverage" to liczba zdarzeń, które zobaczy DWÓCH providerów.**
Nie zasięg najhojniejszego. Dwóch to próg, którego wymaga `READY`
i `cross_provider_agreement` — czyli jedyny powód, dla którego ten pipeline
istnieje. Jeden provider zawsze pokaże 400 zdarzeń i zawsze będzie bezużyteczny.

---

## 2. Napraw to, co preflight wytknął

Każdy zablokowany provider ma `kind`, i tylko on mówi, czy czekanie pomoże:

### `quota_exhausted`
Limit dobowy. Sam się zresetuje o północy UTC. Trzy wyjścia:

```bash
# a) limit w kodzie jest zaniżony — prawdziwy jest w dashboardzie providera
#    .env:
BET_LIMIT_HIGHLIGHTLY=250

# b) podmieniłeś klucz — licznik pamięta zużycie STAREGO klucza
python3 scripts/simple/reset_provider_quota.py --provider highlightly

# c) po prostu poczekaj do jutra
```

Reset **niczego nie zmienia u providera** — kasuje wyłącznie naszą księgowość.
Jeśli klucz jest ten sam, a limit realnie wyczerpany, reset tylko sprawi, że
dostaniesz `HTTP 429` zamiast czystej odmowy przed wydaniem.

### `missing_credentials`
Komunikat podaje nazwę zmiennej. Wpisz ją do `.env` — to **jedyne** miejsce,
z którego czytane są klucze:

```bash
HIGHLIGHTLY_API_KEY=...
```

Nie trzeba restartować niczego; `.env` jest przeładowywany po zmianie pliku.

### `upstream_unavailable`
`understat` (pakiet się nie buduje). **Nie naprawisz tego dziś rano.** Ignoruj
— to znany, stały stan.

`sackmann` zniknął z listy 2026-08-28: repozytoria `JeffSackmann/tennis_atp`
i `tennis_wta` zwracają 404 (nie same CSV — całe repozytoria), więc provider
nie jest już w ogóle deklarowany dla tenisa. Jeśli zobaczysz go w preflight,
ktoś dopisał go z powrotem — to błąd, nie stan przejściowy.

### Tenis: co znaczą linie o „Benoit Paire"
`tennis-abstract` trzyma ATP i WTA na **różnych trasach**, a trasa ATP odpowiada
kodem 200 cudzą stroną, gdy pytasz o zawodniczkę. Taka para linii jest
normalna i znaczy, że zabezpieczenie działa:

```
[tennis-abstract] player-classic served 'Benoit Paire' for 'Iga Swiatek' -- refusing the page
[tennis-abstract] 125 matches for 'Iga Swiatek' via jsmatches (page names 'Iga Swiatek')
```

Pierwsza linia to odrzucenie trasy ATP, druga to trasa WTA. Odrzucenie **bez**
kolejnej udanej linii znaczy, że serwis nie ma strony, którą potrafi
udowodnić — zawodnik jest wtedy nierozpoznany i to jest poprawny wynik.

---

## 3. Uruchom

```bash
python3 scripts/simple/run_pipeline.py -v
python3 scripts/simple/run_pipeline.py -v --max-events 7      # jeśli preflight tak radził
```

Jedna komenda robi DISCOVER → ENRICH → ANALYZE pod jednym `run_id`. Trwa
zwykle 30 s – kilka minut, zależnie od `--max-events`. Bez `-v` dostajesz
czytelne linie; z `-v` strumień JSON-a do parsowania.

**Nigdy nie dawaj `--skip-preflight`.** Produkuje artefakt z samymi lukami,
który wygląda jak wynik.

Jeśli coś padnie w połowie — wznów bez powtarzania tego, co się udało:

```bash
python3 scripts/simple/run_pipeline.py --start-at enrich
```

Wznowienie przejmuje `run_id` z artefaktu, więc restart nie gubi tożsamości runu
w bazie.

---

## 4. Przeczytaj wynik

Ostatnia linia to `AGENT_SUMMARY:{...}`. Kod wyjścia: `0` = OK, `1` = PARTIAL,
`2` = FAILED / PRECONDITION_FAILED.

```bash
jq '{verdict, rows: .metrics.analyze_metrics.total_rows,
     agreement: .metrics.analyze_metrics.rows_by_agreement,
     confidence: .metrics.analyze_metrics.rows_by_confidence}' \
  runs/$(date -u +%F)/$(date -u +%F)_run_summary.json
```

Twój deliverable:

```
runs/<data>/<data>_event_dossiers_stats_sheet.json
```

Posortowany po `confidence` malejąco. Czego szukać:

- **`cross_provider_agreement=AGREE`** — dwóch lub więcej providerów podało ten
  sam mecz historyczny w tolerancji (±1 dla zliczeń, ±5 pp dla procentów). **To
  jest sygnał, któremu można ufać.**
- **`DISAGREE`** — providerzy się kłócą. Obie wartości zostają w dossier i nigdy
  nie są uśredniane. Zajrzyj do dossier, zanim użyjesz wiersza.
- **`SINGLE_SOURCE`** — jeden provider. Częste, nie jest błędem, ale nic tego nie
  potwierdza.
- **`sample_size`** — liczba obserwacji zebranych z obu stron i wszystkich
  providerów. **To nie jest liczba niezależnych meczów.** Nie czytaj jej jak
  wielkości próby.

Nie ma tu kursu, EV ani pola `bettable` — celowo. Linię wybierasz ręcznie
w Superbet Bet Builder, a każdy typ pozostaje warunkowy do momentu, aż zobaczysz
kurs na ekranie operatora.

---

## Gdy coś nie gra

| Objaw | Przyczyna | Reakcja |
|---|---|---|
| `PRECONDITION_FAILED` przy starcie | Preflight odmówił — zero providerów | Krok 2. Nie ponawiaj |
| `FAILED` na DISCOVER | Zero ACTIVE zdarzeń na dziś | Sprawdź datę. Weekend/przerwa w rozgrywkach? |
| `verdict: PARTIAL`, wszystko `SINGLE_SOURCE` | Za mało providerów | Normalne przy wyczerpanych limitach. Dane są słabsze, nie błędne |
| `persisted: false` | Zapis do bazy padł | Artefakt JSON jest poprawny; `persist_error` mówi dlaczego |
| `could not resolve team identity` | ESPN nie zna tej ligi | Znane ograniczenie — mapowane są tylko ligi z `COMPETITION_TO_ESPN_LEAGUE` |
| `no season results for '<liga>'` | SportDB nie dopasował ligi z pewnością | **Celowe.** Dane z niewłaściwej ligi byłyby gorsze niż ich brak |

Pełna operatorka: [SIMPLE_STATS_RUNBOOK.md](SIMPLE_STATS_RUNBOOK.md).

---

## Ściąga

```bash
python3 scripts/simple/run_pipeline.py --preflight            # 1. czy warto (0 zapytań)
python3 scripts/simple/reset_provider_quota.py --status       # ile zostało
python3 scripts/simple/reset_provider_quota.py --provider X   # po podmianie klucza
python3 scripts/simple/run_pipeline.py -v                     # 2. bieg
python3 scripts/simple/run_pipeline.py --start-at enrich      # wznowienie
```

W Kilo: `/run-day` robi to samo agentem `bet-simple`.
