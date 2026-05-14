# System Dziennych Kuponow I Raportow

Ten zestaw plikow zamienia Twoje środowisko i asystentów AI w zautomatyzowany, oparty na agentach workflow do analizy bukmacherskiej dla małego bankrollu. Celem nie jest znalezienie jak najwiekszej liczby typow, tylko statystycznie uzasadniona i ustrukturyzowana selekcja rynków we wskazanych sportach.

## Instalacja

```bash
# Utworzenie i aktywacja środowiska wirtualnego
python3 -m venv .venv
source .venv/bin/activate

# Instalacja pakietu i zależności
pip install -e .
# Opcjonalnie: narzędzia deweloperskie
pip install -e ".[dev]"
```

## Architektura

Nowy system opiera kod w `src/bet/` i wykorzystuje podejście agent-driven (Model A), w którym asystent działa jako orchestrator wykonujący dedykowane skrypty z `scripts/`. 

Podstawowe moduły źródłowe (`src/bet/`):
- `src/bet/db/` — schemat, połączenie (wzorzec `get_db()`), modele, repozytoria (oparte na SQLite WAL)
- `src/bet/discovery/` — odkrywanie wydarzeń (~30s, tysiące zdarzeń z SofaScore, Odds API, API-Football)
- `src/bet/scrapers/` — pakiet 19 scraperów dla 5 sportów (FBref, NBA API, NHL API, ESPN, Flashscore, itd.)
- `src/bet/stats/` — normalizacja statystyk, oceny bezpieczeństwa (safety scores), ranking rynków
- `scripts/odds_sources/` — zintegrowane moduły pobierające kursy bukmacherskie (the-odds-api, odds-api.io, api-football)

## Pipeline (Model A)

Pipeline jest w pełni oparty na agentach — Orchestrator uruchamia skrypty krok po kroku i asynchronicznie deleguje ich wyniki do specjalistycznych asystentów, którzy je analizują. 
Główne kroki:
- **S0 (Settlement)**: Rozliczenie wczorajszych wyników (`settle_on_finish.py`)
- **S1 (Scan & Discovery)**: Odkrywanie dostępnych wydarzeń (`discover_events.py`)
- **S2 (Shortlist & Scrapers)**: Budowa shortlisty (`build_shortlist.py`) i głębokie scrapowanie (`run_scrapers.py`, `data_enrichment_agent.py`)
- **S3 (Deep Stats)**: Dokładna analiza statystyczna (`deep_stats_report.py`)
- **S4 (Odds Evaluation)**: Ewaluacja rynkowa kursów (`odds_evaluator.py`, `fetch_odds_multi.py`, itp.)
- **S5 & S6 (Context & Upset Risk)**: Weryfikacje pozasportowe i ocena ryzyka (`context_checks.py`, `upset_risk.py`)
- **S7 (18-point Gate)**: Finalna wielokryteriowa selekcja (`gate_checker.py`)
- **S8 (Coupons)**: Ostateczne układanie wyników na kupony (`coupon_builder.py`)

## Skrypty Aktywnego Pipeline'u

| Skrypt | Przeznaczenie |
|--------|--------------|
| `discover_events.py` | S1 Odkrywanie wydarzeń dla wszystkich głównych sportów |
| `run_scrapers.py` | S2.3 Automatyczne scrapowanie bogatych statystyk drużyn/lig |
| `data_enrichment_agent.py` | S2.5 Agent wzbogacania danych (wypełnianie luk z różnych API) |
| `build_shortlist.py` | S2 Filtrowanie i budowanie podstawowej listy do analiz |
| `deep_stats_report.py` | S3 Właściwa analiza statystyczna kandydata |
| `odds_evaluator.py` | S4 Ewaluacja kursowa i sprawdzanie expected value |
| `context_checks.py` | S5 Analiza kontekstu (pogoda, motywacja, kontuzje) |
| `upset_risk.py` | S6 Kalkulator ryzyka niespodzianek na dany mecz |
| `gate_checker.py` | S7 18-punktowa bramka jakości oceniająca pick |
| `coupon_builder.py` | S8 Budowanie optymalnych kuponów na podstawie logiki dyspersji ryzyka |
| `settle_on_finish.py` | S0 Rozliczenie rozegranych meczów na koniec dnia/z rana |
| `fetch_odds_api.py` / `_io.py` / `fetch_odds_multi.py` | Kaskadowe narzędzia zaciągające kursy do bazy |

## Baza Danych

Dane są składowane w lokalnej bazie `betting/data/betting.db`. Całość obwarta jest o tryb WAL (Write-Ahead Logging), liczy obecnie 28 tabel dla 6 domen tematycznych (skan, statystyki, kursy, rozkłady, itp.). Pełny dostęp zalecany jest za pomocą wzorca połączenia konfigurowanego przez funkcję `get_db()`.

## 5 Głównych Sportów

System koncentruje się wyłącznie na 5 wiodących dyscyplinach Tier 1:
- Piłka nożna (Football)
- Koszykówka (Basketball)
- Siatkówka (Volleyball)
- Hokej (Hockey)
- Tenis (Tennis)

Wszystkie zasady limitów, portfeli oraz obsługiwanych dyscyplin można dopasować wedle uznania edytując plik `config/betting_config.json`.

## Jak Uruchamiać

System **NIE** uruchamia się na raz ślepym skryptem `pipeline_orchestrator.py`. Działa interaktywnie jako proces Agent-Driven. Przejść do panelu Copilot w VS Code:

Dzienny przebieg inicjuje komenda skierowana w chat do narzędzi agentowych:
```
@workspace /prompt orchestrate-betting-day run_date=2026-05-14 session=full version=v1
```

Następnie współpracujesz z modelem, który uruchamia skrypty jako narzędzia w shellu i prosi agentów dziedzinowych o analizę wyjść ze skryptów.

## Co Powstaje Po Uruchomieniu

- `betting/reports/` — Pełne dzienne raporty Markdown dokumentujące decyzje
- `betting/coupons/` — Kompaktowe wycinki do wyklikania na stronie lub aplikacji Betclic
- `betting/journal/picks-ledger.csv` — Rejestr wszystkich wystawionych decyzji i ich statusów
- `betting/journal/coupons-ledger.csv` — Rejestr całościowych kuponów
- `betting/journal/learning-log.md` — Zapis adaptacji bazujący na wygranych i przegranych

## Najwazniejsze Zasady

- Zawsze rozliczaj poprzedni dzień przed skanowaniem kolejnego
- Kursy to fundament selekcji — nigdy nie zgaduj ani nie wymyślaj linii dla bukmachera
- Brak "Auto-Odrzucań" (No Auto-Rejection) na wczesnych etapach — pozwól modułom ze statystykami przedstawić pełne dane. Użytkownik i ostateczna tablica ryzyka podejmują decyzję
- Brak agresywnego odcinania słabszych rynków (No Aggressive Narrowing); niszowe ligi z pełnym pokryciem stats dają najlepsze Value (zysk)
- Wybory polegają warunkowo (Conditional) na ostatecznej ofercie Betclic
- Wszystkie pojedyncze analizy na kandydatach muszą odbywać się sekwencyjnie z głębokim rezonowaniem
- Limit dzienny jest konfigurowalny na poziomie pliku konfiguracyjnego

## Struktura Katalogow

```
betting/
    coupons/
    data/          (lokacja pliku betting.db)
    journal/
    reports/
    sources/
config/            (betting_config.json)
scripts/           (aktywny pipeline S0-S8)
specifications/    (zrzuty procesów / plany integracji)
src/
    bet/           (główny folder src)
```

## Dobre Praktyki

- Nie dodawaj czwartego lub piątego zdarzenia tylko po to, żeby podbić kurs
- Nie duplikuj tej samej ekspozycji w singlu i kuponie bez wyraznego powodu
- Nie graj kursu wyraznie gorszego od rynku tylko dlatego, że pasuje do narracji
- Raz w tygodniu przeanalizuj statystyki rozliczeń i uaktualniaj wagi sportów / poszczególnych rynków

