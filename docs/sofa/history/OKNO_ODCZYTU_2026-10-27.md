# Okno godzin dla analityków - pierwszy przebieg (2026-10-27)

Operator (10-27): „odświeżenie ceny, rebuild i analiza 20 najlepszych z danego
przedziału czasu (jeżeli nie ma 20 - wszystkie, wszystkie rynki)”.

## Co powstało

- `bet.sofa.window_reads` + `scripts/sofa/window_reads.py`: 20 najlepszych meczów
  okna (czas polski, [od, do)) wg `confidence.read_value` najlepszej niezablokowanej
  nogi; wszystkie, gdy mniej; mecz startujący za < 30 min pominięty (15 min marginesu
  `MIN_MINUTES_TO_KICKOFF`, w którym analityk mecz pomija, + 15 min na czytanie);
  każdy jako prośba o cały mecz w `read_requests.json` (bez `market` = każdy rynek,
  pole `window`). Kanał operatora, nie werdykt; druk się nie zmienia - bez przełącznika.
- `/sofa-analyze <dzień> okno 14-17`: `ensure_bridge.py` → `rebuild_day.py` (świeże
  ceny, PDF / HTML, iCloud) → `window_reads.py` → `build_coupon.py` →
  `read_set.py --unread --buffer 0 --split 5` → analitycy → `merge_reads.py` →
  `rebuild_day.py` → pętla C3.
- `read_set.py --unread` pomija mecz startujący w ciągu 15 min (linia `started:`;
  C3 dalej go pokazuje).

## Przebieg (12:21-13:20Z)

| krok | wynik |
|---|---|
| rebuild 1 (12:21-12:47Z) | OFFER świeży dla 450 meczów, +36 meczów z LATE_RESOLVE; C3: 71 nóg (nowe mecze dnia po świeżych cenach) |
| `window_reads.py` 12:48Z | 20 meczów okna 14-17, 20 próśb, `read_requests_unmatched` 0 |
| runda 1 | 5 instancji (piłka x3 po 5 meczów, tenis, hokej), 0,6-8,6 min; 151 odczytów; WATCH 18 (Hertha Wels - WAC, baza ratingu ÖFB-Cup), NO_BET 1 (Al Wehda - Al-Saqer, odwrócony faworyt) |
| rebuild 2 | C3: 33 nogi 3 meczów 13:00Z + 67 nóg 3 nowych meczów wieczornych |
| runda 2 | 2 instancje; 67 KEEP; jedna instancja na mecz już trwający (bez odczytu) |
| rebuild 3 (13:20Z) | C3: tylko 33 nogi 3 meczów 13:00Z (trwają, zablokowane) |

Okno: 17 z 20 meczów przeczytanych w całości; 3 mecze o 13:00Z (Csíkszereda - Bihor,
Montevideo - Albion, Jadran - Brežice) wybrane o 12:48Z wróciły nieczytane - stąd
margines 30 min (był 10) i pomijanie zaczętych w `read_set.py --unread`. Kopia iCloud
równa lokalnej po każdym rebuildzie (`day_status` icloud OK).

## Do decyzji operatora (niezmierzone)

- Dwa mecze ÖFB-Cup tego wieczoru: analityk r3 zdjął 18 nóg Hertha Wels - WAC (centrum
  WAC 4,13 gola przy próbce 1,31), analityk r6 zostawił First Vienna - Rapid z notą
  (Rapid 3,79 przy próbce 2,23). Ten sam mechanizm, różne werdykty. Baza pucharowa
  (ligue 445, n=194, głównie wczesne rundy) - podejrzenie, nie pomiar.
- `03_samples.json`: próbka `goals_2h_total` Cherno More - Septemvri zawiera mecze
  pucharowe (zgodne z regułą `comparability`? - do sprawdzenia).
