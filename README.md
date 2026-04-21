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

- limit ekspozycji dziennej to 10 PLN
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
- .github/prompts/daily-betting-cycle.prompt.md
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
4. Sprawdz, czy po wpisaniu / widzisz prompt daily-betting-cycle.
5. Sprawdz, czy na liscie agentow widzisz bet-analyst.

## Jak Uruchamiac

Przyklad pelnego uruchomienia:
 /daily-betting-cycle run_date=2026-04-21 sports_focus=football,basketball,tennis bookmaker=Betclic

Przyklad lzejszego uruchomienia:
 /daily-betting-cycle run_date=2026-04-21 sports_focus=football,basketball bookmaker=Betclic

Przyklad tylko dla pilki:
 /daily-betting-cycle run_date=2026-04-21 sports_focus=football bookmaker=Betclic

## Co Powstaje Po Uruchomieniu

- betting/reports/YYYY-MM-DD.md
  Pelny raport z rozliczeniem poprzedniego dnia, shortlista, finalnymi pickami i podsumowaniem ekspozycji.

- betting/coupons/YYYY-MM-DD.txt
  Szybka wersja do zagrania. Ma byc krotka i praktyczna.

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
  Ile z 10 PLN faktycznie zostalo wystawione i ile zostalo niewykorzystane.

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

Jesli system nie znajdzie sensownego edge, poprawnym wynikiem jest brak zakladu. Dla bankrollu 10 PLN najwiekszym bledem nie jest ominięcie slabego dnia. Najwiekszym bledem jest wymuszenie akcji.