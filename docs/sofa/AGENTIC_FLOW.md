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
| `/sofa-day [data]` | cały dzień: most → SETTLE D-1 → BOARD…COUPON → analitycy → przebudowa → PDF → weryfikacja | Sofascore (most) + Superbet |
| `/sofa-analyze [data]` | analitycy nad gotowym arkuszem, scalenie wet, przebudowa | tylko Superbet (opcjonalnie) |
| `/sofa-rebuild [data]` | przebudowa kuponu i PDF z artefaktów z dysku | tylko Superbet (opcjonalnie) |
| `/sofa-verify [data]` | adwersaryjna weryfikacja zbudowanego dnia | Superbet (ceny na żywo) + web |
| `/sofa-settle [data]` | rozliczenie dnia zakończonego i decyzja o fitowaniu | Sofascore (most) |

Argument to `dzisiaj` / `wczoraj` / `YYYY-MM-DD`; pusty znaczy dzisiaj.
**Doba zakładowa jest w UTC.**

### Agenci — wykonawcy z własnym kontekstem

| agent | rola | narzędzia | pisze pliki? |
|---|---|---|---|
| `sofa-runner` | właściciel przebiegu: uruchamia etapy, deleguje, scala weta, melduje | Bash, Read, Glob, Grep, **Task** | nie (brak Edit/Write; dane pisze przez Bash) |
| `sofa-analyst-football` | piłkarski odczyt meczu, którego kod nie zrobi + weta | Read/Glob/Grep/Bash, Web, **bzzoiro MCP** | nie — zwraca tekst |
| `sofa-analyst-tennis` | to samo dla tenisa | Read/Glob/Grep/Bash, Web | nie — zwraca tekst |
| `sofa-verifier` | rozbiera zbudowany dzień na części, adwersaryjnie | Read/Glob/Grep/Bash, Web | nie |
| `sofa-settler` | pętla rozliczenie → kalibracja, higiena konfiguracji | Bash, Read, Glob, Grep | nie (uruchamia fitter, nie edytuje stałej ręcznie) |
| `sofa-market-scout` | czy da się to postawić i czy warto tej ceny; ślepa plama `unmapped_markets` | Read, Glob, Grep, Bash, WebFetch | nie |

**Żaden agent `sofa` nie ma `Write` ani `Edit`.** To nie przeoczenie: przebieg,
który potrzebował edycji pliku, potrzebuje człowieka. Dane (jak `vetoes.json`)
powstają przez Bash — to zapisywanie danych, nie naprawianie kodu.

### Umiejętności (skills) — wiedza wstrzykiwana do kontekstu

| skill | do czego | wczytany do |
|---|---|---|
| `sofa-pipeline` | etapy, artefakty, arytmetyka, pułapki | każdego agenta `sofa` |
| `sofa-analysis-core` | kontrakt analityka: kolejność artefaktów, schemat wet, punkt decyzyjny, format raportu | obu analityków |
| `football-analysis` | metoda piłkarska (runda, stawka, sędzia, scenariusz meczu, rozkład ponad średnią) | `sofa-analyst-football` |
| `tennis-analysis` | metoda tenisowa (nawierzchnia, format, hold/break, arytmetyka wyniku) | `sofa-analyst-tennis` |
| `bet-slip-audit` | wycena kuponu/slipa, który operator przysłał z ekranu | na żądanie |

Hierarchia, gdy dwa źródła mówią co innego: **artefakt > skill > plik agenta**.
Skill wygrywa na metodzie, artefakt na faktach, plik agenta mówi tylko, jak
przebiega *jego* przebieg.

> **Definicje agentów wczytują się na starcie sesji.** Przepisanego pliku
> agenta **nie da się przetestować w tej samej sesji, w której go napisano** —
> trzeba nowej. Nie pisz, że poprawka „już działa"; napisz, że wejdzie
> w następnej sesji.

---

## 2. Pełny dzień agentowo

```
operator: /sofa-day 2026-09-21
   │
   ├─ 0. most            check_bridge.py — trzy linie OK, i liczy się WIEK pobrania
   │                     martwa karta nadal melduje ok:true
   │
   ├─ 1. SETTLE D-1      → sofa-settler (albo inline)
   │                       audit_settlement §7c = prawdziwy wynik PDF-kuponu
   │                       §7 i §7b to materiał wejściowy, NIE zakłady
   │
   ├─ 2. dzisiaj         BOARD (tylko Superbet — może iść, gdy SETTLE trzyma most)
   │                     … RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON
   │                     jeden --run-id na cały dzień
   │
   ├─ 3. analitycy       Task → sofa-analyst-football   ┐ w JEDNEJ wiadomości,
   │                     Task → sofa-analyst-tennis     ┘ żeby szły równolegle
   │                        ↓ każdy zwraca markdown + jedną tablicę JSON
   │                     walidacja → runs/sofa/<data>/vetoes.json
   │
   ├─ 4. przebudowa      OFFER (jeśli cena > 45 min) → COUPON → CONFIDENCE → PDF
   │                     bo vetoes.json czytają COUPON I CONFIDENCE
   │
   └─ 5. weryfikacja     → sofa-verifier  (NIE jest opcjonalna)
                           kończy listą wierszy, których NIE postawiłby
```

### Punkt wstawienia, który czyni tę ścieżkę agentową prawdziwą

Jedynym miejscem, w którym osąd agenta wchodzi do produktu, jest
**`vetoes.json` między SHEET a COUPON**. Nic więcej z pracy analityka nie
dociera do maszyny — reszta jest raportem dla operatora.

Z tego wynikają trzy rzeczy, które trzeba robić dokładnie tak:

1. **Analitycy biegną po SHEET, przed COUPON.** Sekwencja domyślna uruchomi już
   COUPON — to normalne, przebuduje się go w kroku 4.
2. **Po zapisaniu wet trzeba przebudować OBA produkty.** `vetoes.json` czytają
   COUPON **i** CONFIDENCE. Przebudowanie samych singli zostawia zawetowany
   szczebel jako nogę Bet Buildera, czyli w pliku, który się stawia. Tak było
   do 2026-09-21.
3. **Weto, które nie trafiło, musi zostać zgłoszone.** Oba etapy drukują
   `UNMATCHED_VETO`; cichy no-op czyta się identycznie jak weto uszanowane.

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
`event_id`) wywraca **cały plik**, a COUPON rusza wtedy z **zerem** wet
i melduje zero — wygląda to identycznie jak dzień bez zastrzeżeń.

---

## 3. Kontrakt analityka

**Wejście:** data, `run_id`, werdykty etapów, liczba wierszy VALUE w jego
sporcie, i to, co się wywaliło. **Nie** opinia zlecającego o konkretnym meczu —
to byłaby prośba o potwierdzenie, nie o analizę.

**Wyjście:** markdown po polsku + **jedna** ogrodzona tablica JSON z wetami.
`[]` to normalna, zdrowa odpowiedź.

**Kolejność pracy** (z `sofa-analysis-core`):

1. **Inwentarz.** Mecze swojego sportu, udział READY, VALUE **policzone
   samodzielnie z `05_sheet.json`**, ile dochodzi do singli, ile do nóg, ile do
   *stakeable* buildera.
2. **Punkt decyzyjny — przed jakimkolwiek narzędziem webowym/MCP.** Oba zegary,
   `now`, różnica. Mecz, który się zaczął, wypada **tutaj**, a nie po
   researchu: tytuły i snippety wyszukiwarki **są treścią**, więc analiza
   spóźniona jest wystawiona na wynik. Jeśli wynik przecieknie — nazwij to
   i oznacz twierdzenie `CANNOT VERIFY`.
3. **Weryfikacja tożsamości.** Piłka: `bzzoiro` MCP **po id**
   (`get_match_detail`) — to legalne niezależne źródło właśnie dlatego, że
   `sofa` z niego **nie próbkuje**; tag `[BZZOIRO-MCP: <tool>, fetched <UTC>]`.
   Tenis: **nie ma źródła prawdy** (`bzzoiro-tennis` odpowiada
   `402 addon_required`), więc web, dwie niezależne domeny, tag
   `[WEB: domena, fetched <UTC>]` — a „niezweryfikowane" jest często odpowiedzią
   uczciwą i tak trzeba je podać.
4. **Protokół per mecz** z odpowiedniego skilla sportowego, w jego kolejności.
   Cena **ostatnia**.
5. **Blok wet.**

**Oba produkty, nie tylko arkusz.** Odczyt, który ocenia single i nigdy nie
otwiera `08_confidence.json`, opisuje dzień, którego nikt nie postawił. Trzeba
ocenić też **legi i buildery**, a przed stwierdzeniem „tego wiersza nie ma"
zajrzeć do `06_dropped.json`.

**Priorytety, gdy tablica jest duża** (niedziela to 1000+ meczów piłki i nikt
ich nie przeczyta):

1. mecze z nogą w **stakeable** builderze;
2. mecze z nogą w `08_confidence.json`;
3. single VALUE z nadwyżką **> +0,40** — podejrzane z definicji;
4. piłka: rynki `*_1h_*` / `*_2h_*` (cienkie bazy; przy n=8 wiersz jest w 76%
   priorem ligowym). Tenis: mecze z `ground_type` albo
   `default_period_count` = `null` — zakres próbki wtedy **nie zadziałał**;
5. reszta VALUE po nadwyżce.

**Gdzie skończyłeś — powiedz.** Mecz nieprzeczytany to `NIE PODANO`, nigdy
milczenie.

**Czego analitykowi nie wolno:**

- wetować za bramkę, którą kod już stosuje (`STALE_PRICE`, `STALE_SAMPLE`,
  `ODDS_TOO_LOW`, `KICKOFF_TOO_SOON`, `MODE_LOSES`, `LINE_BEYOND_SAMPLE`,
  `THIN_SAMPLE_FOR_BUILDER`) — to dopisuje szum, w którym giną prawdziwe powody;
- podawać `FUZZY` jako potwierdzoną tożsamość;
- brać ceny z otwartego webu. `bzzoiro compare_odds` to ~88 książek,
  **żadna z nich nie jest Superbetem** — to punkt odniesienia, nie cena;
- podawać własnej ceny łączonej;
- proponować stawki.

**Szerokość weta trzeba policzyć przed wysłaniem.** Nie ma pola „zawodnik";
weto z `subject: null` obejmuje **każdy podmiot** na tym meczu. Jeśli trafia
szerzej, niż zamierzałeś — nie wysyłaj go, opisz prozą i powiedz, że nie
zostało zastosowane.

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

**Produktem jest lista wierszy, których NIE postawiłby, mimo że pipeline je
wybrał.** Nie lista poleconych. Na koniec werdykt i **żadnej rekomendacji
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

Szczegóły higieny plików konfiguracyjnych: [`CONFIG.md`](CONFIG.md).

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
KUPON:    runs/sofa/<data>/KUPON_<data>.pdf — <n> pozycji
SHEET:    <n> wierszy, <n> VALUE (<n> piłka / <n> tenis)
RUN:      <run_id> · <werdykt> · <n> na tablicy → <n> dopasowanych (<x>%) → <n> READY
WETA:     <n> zastosowanych, <n> bez dopasowania
SETTLE:   D-1 <n> wierszy, PDF-kupon <w>/<n> slipów (sekcja 7c)
WERYFIKACJA: <n>/<n> arytmetyka, <n>/<n> ceny na żywo, <n> pozycji odrzuconych
UWAGA:    <największa słabość dnia, jedna>
```

Cytuj `run_id` i werdykt **każdego** etapu, nie tylko porażek. VALUE policz
sam z `05_sheet.json`, per sport.
