# ▲ i stawka meczu na kuponie - raport z prac 2026-10-08

Polecenie operatora (po przegranej 10-07): zbadać mechanizm wyboru z dwóch nóg po
podobnym kursie na wszystkich sportach i rynkach, poprawić, przetestować e2e i
przebudować dzisiejszy kupon. Dowody: `docs/sofa/evidence/peer_choice_2026-10-08.md`.

## Wynik pomiaru (skrót)

- Pewność wskazuje lepszą z dwóch nóg jednego meczu w pasie ±0,06 kursu w
  53,4% [52,2; 54,7] z 57 791 rozstrzygniętych par (piłka + tenis, 20 dni). W
  hokeju, koszykówce, siatkówce: 49,7% [45,9; 53,6] na 2 894 parach - brak przewagi.
- Nic nie poprawia tego poza próbą: rozmiar próbki, własny odsetek trafień,
  bliskie pudła, margines, miejsce meczu, ostatnie 5, popularność turnieju,
  flagi rezerwy / kobiet / pucharu.
- Stawka z tabeli ligi (mecz o utrzymanie) ma efekt prawdziwy i mały: +0,20
  kartki, +0,86 faulu, -0,15 gola, -0,96 strzału (0,08-0,16 sd), nieskorygowany o
  słabość klubów strefy spadkowej.
- Internacional - Corinthians 10-07 jest flagowany jako mecz o utrzymanie (73%
  sezonu, 2 pkt od linii); ▲ zostaje przy nodze o wyższej pewności (Corinthians
  poniżej 4,5), obok flaga „efekt stawki idzie przeciw tej nodze".

## Zmiany

- `bet.sofa.peer_choice`, `bet.sofa.stakes`, `epochs.PEER_CHOICE_FROM_UTC`
  (2026-10-08 08:10Z, przesunięte przez operatora; 10-08 to dzień mieszany).
  **Adnotacja - żadna noga nie jest dodana, zdjęta ani przestawiona, żadna
  pewność się nie rusza**; sprawdzone: 721 nóg w tej samej kolejności przed i po.
- `build_coupon.py` (pola `peer`, `stakes`, `peer_choice`), PDF (▲ i legenda;
  Arial nie ma U+2605, stąd trójkąt), `11_coupon.md` (kolumna uwagi).
- `scripts/sofa/measure_peer_choice.py` (tylko odczyt), test `T-PEER-CHOICE-edge`
  w rejestrze (od 2026-10-09), CLAUDE.md, PIPELINE.md, kontrakty analityków
  (żywe od następnej sesji).
- Testy: `tests/sofa/test_peer_choice.py` (21); `tests/sofa` 3592 passed, 2 skipped;
  ruff i mypy czyste; `check_test_registry` 6 / 0.

## E2E i przebudowa dnia

Kopia folderu dnia (build + PDF, bez dotykania prawdziwego kuponu), potem
`rebuild_day.py --date 2026-10-08` na żywo: OFFER, SHADOW, CS2, SPORT_IDENTITY
(PARTIAL), FIXTURE_CHECK (385 sprawdzonych, 2 UNVERIFIED bez nóg na kuponie),
CONFIDENCE, SPORT_CONFIDENCE, COUPON_ASSEMBLY, PDF, audyty. C3 wskazał jedną
nogę przesuniętą do pierwszych 30 pozycji (Athletico - Mineiro, celne strzały
≥ 7,5): odczyt analityka KEEP dopisany do `reads.json`, drugi rebuild:
`audit_variants` 0 znalezisk. Kupon: 715 pojedynczych (tenis 340, piłka 169,
hokej 168, koszykówka 36, siatkówka 2), 471 z adnotacją ▲, dziś żaden mecz bez
flagi stawki. Nie testowane: zachowanie na kuponie w dniu z meczem flagowanym
(poza testem jednostkowym i 10-07 offline).
