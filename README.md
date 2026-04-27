# System Dziennych Kuponow I Raportow

Ten zestaw plikow zamienia Copilota w uporzadkowany workflow do malego bankrollu. Celem nie jest znalezienie jak najwiekszej liczby typow, tylko wybranie malej liczby zakladow, ktore maja sens statystyczny i kursowy.

## Co System Robi Przy Kazdym Uruchomieniu

- rozlicza poprzedni betting day
- aktualizuje learning-log i source-log
- sprawdza dostepnosc zrodel
- buduje shortlist wydarzen
- odrzuca slabe ceny i slabe rynki
- zapisuje raport dzienny i skrot kuponow
- aktualizuje ledgery pickow i kuponow

## Najwazniejsze Zasady

- limit ekspozycji dziennej jest konfigurowalny (zobacz config/betting_config.json); domyślnie stosujemy "smart allocation" i nie zawsze wykorzystujemy cały bankroll
- nie ma obowiazku wykorzystania calego bankrollu
- Betclic to miejsce wykonania kuponu, nie glowne zrodlo analizy
- preferowane sa rynki statystyczne: over i under, BTTS, team totals, DNB, double chance, spreads, linie setow i gemow, linie punktowe
- zrodla tipsterskie i community moga tylko wspierac decyzje
- jeden pick musi miec minimum 1 zrodlo Tier A statystyczne lub meczowe i minimum 1 zrodlo Tier A rynkowe
- przy braku jakosciowego edge system ma prawo zwrocic dzien bez zakladu
- betting day jest liczony w strefie Europe/Warsaw od 06:00 do 05:59 nastepnego dnia

## Dlaczego Czesc Plikow Jest Po Angielsku

Pliki instrukcyjne, prompty, agent i pola w CSV sa po angielsku celowo. Copilot zwykle stabilniej trzyma format, nazwy pol i workflow, kiedy instrukcje operacyjne sa zapisane po angielsku. README jest po polsku, bo sluzy Tobie, a nie modelowi.

## Struktura Katalogow

- .github/copilot-instructions.md
- .github/instructions/betting-artifacts.instructions.md
- .github/agents/bet-analyst.agent.md
- .github/prompts/orchestrate-betting-day.prompt.md
- betting/sources/source-registry.md
- betting/journal/learning-log.md
- betting/journal/picks-ledger.csv
- betting/journal/coupons-ledger.csv
- betting/journal/source-log.csv
- betting/reports/
- betting/coupons/

## Jak Wdrozyc

1. Wklej wszystkie pliki do docelowego repo.
2. Upewnij sie, ze VS Code widzi prompty i custom agents z katalogu .github.
3. Otworz Copilot Chat.
4. Sprawdz, czy po wpisaniu / widzisz prompt orchestrate-betting-day.
5. Sprawdz, czy na liscie agentow widzisz bet-analyst.

## Jak Uruchamiac

### Rekomendowany sposob: Orchestrator (4-pass pipeline)

Orchestrator uruchamia pelny pipeline S0→S1→S2→S3→S4→S5→S6→S7→S3B→S8 w 4 przejsciach (Discovery → Fixes → Polish → Final). **Kazda sesja przechodzi IDENTYCZNY proces — rozni sie TYLKO okno czasowe wydarzen.**

**Pelna sesja (06:00 → 05:59 nastepnego dnia):**
```
@workspace /prompt orchestrate-betting-day run_date=2026-04-27 session=full version=v1
```

**Sesja dzienna (06:00 → 21:59):**
```
@workspace /prompt orchestrate-betting-day run_date=2026-04-27 session=day version=v1
```

**Sesja nocna (22:00 → 05:59 nastepnego dnia):**
```
@workspace /prompt orchestrate-betting-day run_date=2026-04-27 session=night version=v1
```

**Sesja poranna (06:00 → 14:59):**
```
@workspace /prompt orchestrate-betting-day run_date=2026-04-27 session=morning version=v1
```

**Na kilka dni (rozszerzony horyzont):**
Ustaw `betting_window_days` > 1 w `config/betting_config.json`, potem:
```
@workspace /prompt orchestrate-betting-day run_date=2026-04-27 session=full version=v1
```

**Rerun tego samego dnia (poprawiona wersja):**
```
@workspace /prompt orchestrate-betting-day run_date=2026-04-27 session=full version=v2
```

### Wazne: Sesja NIE wplywa na glebokosc analizy

Kazda sesja — full, day, night, morning — wykonuje:
- Skanowanie wszystkich 14 sportow
- Pelna analiza STEP 3-7 kazdego kandydata (H2H, tipsterzy, kontuzje, bear case, 17-point gate)
- Pelna walidacja V1-V10
- Weryfikacja mechaniczna §S8.FINAL
- Minimum 4 kupony lub deklaracja NO BET

Jedyna roznica to filtr czasowy w STEP 2 (ktore mecze wchodza do shortlisty).

### Opcjonalnie: Pipeline skanowania przed orchestratorem

```bash
# 1. Uruchom pipeline skanowania (pobiera dane ze zrodel + tipsterow)
bash scripts/run_full_scan_and_prepare.sh

# 2. Pobierz kursy z The-Odds-API (jesli klucz skonfigurowany)
python3 scripts/fetch_odds_api.py

# 3. Uruchom orchestrator
@workspace /prompt orchestrate-betting-day run_date=2026-04-27 session=full version=v1
```

### Checkpointy (kazdy MUSI przejsc zanim pipeline rusza dalej)

| Krok | Gate | Minimum |
|------|------|---------|
| S0 | Settlement | Wszystkie pending rozliczone, bankroll zaktualizowany |
| S1 | Scan | ≥50 wydarzen, 14 sportow skanowanych, tipster HTML pobrany |
| S2 | Shortlist | 15-40 kandydatow, ≥8 sportow |
| S3 | Stats | ≥2 zrodla na kandydata, H2H obowiazkowe |
| S4 | Tipsters | ≥2 strony tipsterskie na kandydata, §4.3 watchlist done |
| S5 | Odds/EV | EV > 0 dla kazdego approved |
| S6 | Context | Upset risk scored, kontuzje zweryfikowane |
| S7 | Gate | 17-point gate przeszedl dla kazdego picka |
| S3B | Time-sensitive | Sklady, pogoda, drift kursow sprawdzone |
| S8 | Coupons | V1-V10 all pass, §S8.FINAL weryfikacja mechaniczna |

## Co Powstaje Po Uruchomieniu

- betting/reports/YYYY-MM-DD.md
  Pelny raport z rozliczeniem poprzedniego dnia, shortlista, finalnymi pickami i podsumowaniem ekspozycji.

- betting/coupons/YYYY-MM-DD.md
  Kompaktowe podsumowanie kuponów w Markdown — identyczne z tym co widac na chacie. Szybkie do klikniecia w Betclic.

- betting/journal/picks-ledger.csv
  Historia pojedynczych pickow wraz z rozliczeniem.

- betting/journal/coupons-ledger.csv
  Historia kuponow wraz z rozliczeniem.

- betting/journal/source-log.csv
  Historia dostepnosci i przydatnosci zrodel.

- betting/journal/learning-log.md
  Zmiany procesu na przyszle dni.

## Jak Czytac Raport

- Final Singles
  Najlepsze pojedyncze zaklady z danego dnia.

- Final Coupons
  Wariant low-risk i higher-risk. Kazdy z nich moze byc pominiety, jesli nie ma sensownego edge.

- Candidate Board
  Szersza shortlista wydarzen przed ostateczna selekcja.

- Rejected Picks
  Rynki i wydarzenia odrzucone wraz z powodem.

 - Exposure Summary
  Ile z zaplanowanej ekspozycji faktycznie zostalo wystawione i ile zostalo niewykorzystane (patrz config/betting_config.json).

- price_gap_pct
  To roznica miedzy kursem w Betclic i najlepszym kursem rynkowym.
  Wzor:
  100 * ((kurs Betclic / najlepszy kurs rynkowy) - 1)

  Im nizszy wynik, tym gorsza cena wzgledem rynku.
  Dla low-risk system odrzuca zwykle wszystko gorsze niz -3%.
  Dla higher-risk system odrzuca zwykle wszystko gorsze niz -5%, chyba ze raport wyraznie opisze powod.

## Jak Dziala Uczenie

- System nie trenuje modelu od nowa.
- Uczenie polega na dopisywaniu krotkich zmian procesu do learning-log.
- source-log zapisuje, ktore zrodla byly dostepne i czy realnie pomogly.
- Po kilku dniach widzisz, ktore zrodla sa stabilne, a ktore tylko generuja halas.

## Kiedy Robic Rerun

- rano albo wczesnym popoludniem: pierwszy pelny skan
- 30 do 90 minut przed wazniejszymi startami: rerun dla odswiezenia kursow i lineupow
- rerun tego samego dnia ma aktualizowac pliki, a nie dublowac historii

## Recommended pre-run (install + scan + aggregate)

Before composing final coupons, run the repository orchestrator which installs dependencies, runs a Playwright smoke test, fetches Tier‑A/B pages, and aggregates structured outputs into `betting/data/`.

Quick start (one-liner):
```bash
python3 -m pip install --user -r scripts/requirements.txt
python3 -m playwright install chromium
bash scripts/run_full_scan_and_prepare.sh
```

Or run the individual steps shown above if you prefer manual control.

## Co Robic, Gdy Zrodla Padaja

- jesli wypada jedno zrodlo pomocnicze, system ma przejsc na inne z tej samej roli
- jesli wypada para zrodel Tier A potrzebna do danego sportu, system ma pominac ten sport albo dany mecz
- kazda awaria zrodla powinna trafic do source-log i sekcji Source Availability w raporcie

## Dobre Praktyki

- nie dodawaj czwartego lub piatego zdarzenia tylko po to, zeby podbic kurs
- nie duplikuj tej samej ekspozycji w singlu i kuponie bez wyraznego powodu
- nie graj kursu wyraznie gorszego od rynku tylko dlatego, ze pasuje do narracji
- raz w tygodniu przeczytaj learning-log i source-log i recznie usun z rdzenia te zrodla, ktore stale sa slabe lub niedostepne

## Minimalna Zasada Operacyjna

Jesli system nie znajdzie sensownego edge, poprawnym wynikiem jest brak zakladu. Dla malego, konfigurowalnego bankrollu najwiekszym bledem nie jest ominięcie slabego dnia. Najwiekszym bledem jest wymuszenie akcji.

## Prompt:
"Przeprowadź pełną analizę na dzień 2026-04-22. Użyj Phase 1-8 z analysis-methodology.instructions.md. Na końcu uruchom pełną walidację V1-V10."
