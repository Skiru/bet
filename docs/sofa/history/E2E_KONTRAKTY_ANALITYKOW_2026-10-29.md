# Test E2E kontraktów analityków - 2026-10-29

Test na żywo commitu 70bd8f1a (poprawki operatora z 29.10: czynniki rynku,
`RYNEK:` WATCH, czytelne raporty, `build_slip --check`) na dniu 2026-10-29,
tylko mecze nierozpoczęte, bez dotykania kuponu (merge wyłącznie
`--dry-run --slip`, raporty w katalogu scratch z datą 2026-10-30).

Mecze: Everton - Newcastle United (`sofa:17118369`, 50 nóg), Fiorentina -
Atalanta (`sofa:16285057`, 62 nogi), Lugano - Lausanne (`sofa:16340946`,
hokej, 7 nóg).

## Wynik przebiegu

| krok | wynik |
|---|---|
| most, md5 kuponu | OK; md5 PDF / HTML / reads / vetoes / 11_coupon / analyses bez zmian po teście |
| dossier | schema 2 z `style.league`, xG i blocked_shots, matchup 46 / 38 wierszy |
| analityk piłki | 112/112 nóg, KEEP 87 / WATCH 1 (`RYNEK:` próg (a): Atalanta oddaje 6 lub mniej rożnych w 5/10, pewność 0.760, luka 0.26) |
| analityk hokeja | 7/7 KEEP; bramkarz w „Kluczowe przed meczem” (UNVERIFIED) |
| check + merge `--dry-run --slip` | oba OK / exit 0 |
| test negatywny „seria 0/4 w h2h” | exit 2, „removals without a fact” |
| `build_slip --check` | exit 0 (3/3 na kuponie), exit 1 (noga spoza kuponu) |
| `day_status.py` | exit 0 |

## Usterki znalezione i poprawione

1. **`RYNEK:` bez sprawdzenia progu.** `report_check` przepuszczał każdy WATCH
   z „RYNEK:” i dowolnym k/n: „RYNEK: h2h: 0/4” i „RYNEK: … 9/10” (powyżej
   pewności 0.76) dały merge exit 0. Teraz `report_check.market_findings`
   sprawdza każdy WATCH `RYNEK:` z wierszem `style.matchup` jego nogi w
   dossier (schemat >= 3): RYNEK ZAKAZANY (h2h / forma / seria / tabela /
   odpoczynek / rating po znaczniku), RYNEK BEZ LINII, RYNEK BEZ DOSSIER,
   RYNEK BEZ WIERSZA, RYNEK PONIŻEJ PROGU (próg (a) / (b) przeliczony z
   wiersza; przy `price_gap` od 1/kurs + 0.03), RYNEK INNE LICZBY (powód nie
   cytuje k/n wiersza). `merge_reads.py` odmawia całego raportu;
   `check_analyst_report.py` (`--date` albo raport w katalogu dnia) i hook
   mówią to samo analitykowi.
2. **Noga łączna liczona jak jednostronna.** „Każda z drużyn powyżej X – nie”
   i „1. połowa obie strzelą: nie” miały w `style.matchup` komórki
   `own` / `opponent_conceded` każdej strony - liczby nie tej nogi, które
   mechanicznie przekraczały próg (a). Model i SETTLE czytają taką nogę jako
   min(gospodarz, gość) („nie” = nie obie powyżej, `run_settle.py`). Dossier
   liczy ją teraz tak samo: wiersz `joint: true`, `games` = min(własne,
   rywala) w meczach każdej strony, liga na min. Na Everton - Newcastle
   (kartki „każda > 2.5 – nie”): 8/10 i 8/10 zamiast 7/10 i 5/10.
3. **`dossier.joint_history` (`build_slip --check`, „Historia łączna”)**
   liczył „każda z drużyn – nie” jako „obie poniżej” - za nisko. Poprawka
   poprawności: min(własne, rywala) jak SETTLE.
4. **Brak ścieżki dla wybranych meczów.** `read_set.py --event-ids <id,...>`
   (wszystkie niezablokowane drukowane nogi tych meczów, `required`; exit 1
   przy id bez nogi) i `--dossier-dir <katalog>` (`dossier.write_for_legs(...,
   out_dir=)`): test albo odczyt scratch nie nadpisuje dossier dnia.
5. **`context` analityka sportowego.** Agent wpisał `"OTHER"`; merge
   odrzucił. Kontrakt (`veto-contract.md`, `sofa-analyst-sport.md`) wymienia
   teraz dozwolone wartości.
6. **Drobne:** w `--check` kolumna „szansa zmierzona < 1/kurs” liczy tak
   samo jak nagłówek (wcześniej „pewność < 1/kurs: nie” obok „poniżej ceny”
   w nagłówku); `football-analysis` każe cytować `referee_read.multiplier`
   (0.901), nie surowy `ratio` (0.839).

Dossier: `SCHEMA_VERSION` 3 - wiersz `style.matchup` niesie `market`,
`subject`, `line`, `direction`, `joint`, `price_gap`. Starsze dossier nie
podpiera `RYNEK:` (RYNEK BEZ DOSSIER), więc dzień 2026-10-30 musi mieć
dossier zbudowane nowym kodem - `read_set.py` / `build_slip.py` budują je
przy każdym odczycie.

Nic z tego nie zmienia pewności, bramek ani tego, co drukuje kupon: dossier to
podgląd. Reguły raportu (W SKRÓCIE, ZESTAWIENIE, PRZECIW, RYNEK, WETO BEZ
FAKTU) operator przesunął po teście z raportów od 2026-10-30 na raporty od
2026-10-29 („od dzisiaj”): odczyty 10-29 nie były jeszcze scalone, a
analitycy dnia zostali anulowani - czytają od nowa na nowych regułach
(`report_check.READABLE_SECTION_DATE`).

## Weryfikacja po poprawkach (żywe artefakty 10-29, scratch)

- `read_set.py --date 2026-10-29 --event-ids 16285057,17118369,16340946
  --dossier-dir <scratch> --no-h2h --no-lineups`: 112 + 7 nóg, dossier w
  schemacie 3 w scratch, dossier dnia / h2h.json / lineups_prematch.json bez
  zmian (md5).
- Prawdziwy raport piłki: `check_analyst_report.py --date 2026-10-29
  --read-set …` OK; merge `--dry-run --slip` przyjmuje WATCH `RYNEK:`.
  Exit 1 tylko przez LEG_WITHOUT_READ: obrony bramkarza Atalanty poniżej 4.5
  jest w szerszym zestawie z `--event-ids`, a nie było jej w read secie dnia.
- Sondy na tym raporcie: „RYNEK: h2h: Fiorentina 0/4” → exit 2 RYNEK
  ZAKAZANY; „… 9/10” i „… 4/10” → exit 2 RYNEK INNE LICZBY (dossier: 5/10).
- `tests/sofa`, ruff, mypy --strict, `check_test_registry.py`: czyste.

Definicje agentów i skille ładują się na starcie sesji - zmienione kontrakty
działają od następnej sesji.
