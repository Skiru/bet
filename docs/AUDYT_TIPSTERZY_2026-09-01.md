# Audyt tipsterów — 2026-09-01

Wykonany w osobnym worktree (`bet-tipster-audit`, gałąź `audit/tipsters-deep-2026-09-01`).
Główne repo nietknięte; wszystkie uruchomienia szły z `--no-persist` i pisały do scratchpada.

Dane: prawdziwy `runs/2026-09-01/2026-09-01_event_list.json` (217 zdarzeń: 179 piłka, 38 tenis)
i prawdziwe pobranie z zawodtyper + typersi (86 picków).

---

## 1. Dlaczego failuje za każdym razem — przyczyna źródłowa

**To nie jest problem ze scraperami.** Krok umierał przy **imporcie**.

```
run_tipsters.py
  -> bet.tipsters.live -> extractors -> zawodtyper
    -> bet.pipeline.tipster_parsers
      -> bet/pipeline/__init__.py -> state.py
        -> STEP_ORDER = get_step_order()      # na poziomie modułu
          -> waliduje manifest S0-S10
            -> sprawdza .kilo/agents/*.md     # usunięte w b49258b4
              -> PipelineManifestError
```

`b49258b4 "remove kilo"` (2026-08-31 08:40 CEST) skasował `.kilo/agents/*.md`.
Ostatni udany TIPSTERS: **2026-08-31 06:38 UTC** — tuż przed tym commitem. Od tego
momentu 100% awarii.

`typersi.py` importował ten sam moduł, więc **oba domyślne źródła** były zatrute.

### Dlaczego wyglądało to na awarię „bez śladu"
Wyjątek leciał **przed** `argparse` i **przed** blokiem `try`, który miał czynić ten krok
nieszkodliwym. Dlatego:

- exit 1, `verdict: FAILED`, `metrics: {}`, `output_path: null`
- **zero wierszy w `pipeline_runs`** — mimo że `record()` miał je pisać na każdej ścieżce
- obietnica z docstringa („porażka zwraca PARTIAL, nigdy FAILED") była **nieosiągalna**

### Dlaczego testy tego nie złapały
**Żaden test nie dotyka `run_tipsters.py`** (`grep -rn "run_tipsters" tests/` → pusto).
Testy importują `bet.tipsters.*` bezpośrednio, więc nigdy nie przechodzą przez łańcuch,
który padał. Efekt: **213 zielonych testów tipsterów przy 100% awarii w produkcji.**

### Naprawione
Commit `9e2d2f55`: `bet/pipeline/tipster_parsers.py` → `bet/tipsters/parsers.py`.
To czyste funkcje tekstowe bez zależności od pipeline'u — należą do pakietu, który ich używa.
Przenosiny **całkowicie odcinają** żywy krok TIPSTERS od martwej warstwy S0-S10.

Po poprawce: `verdict: OK`, 86 picków, oba źródła działają.

**Świadomie nie ruszone:** sam manifest i 82 moduły testowe, które `remove kilo` też zepsuło
(cały pakiet testów nie potrafi się dziś zebrać). To osobna decyzja — czy warstwa legacy
jest wygaszana, czy przywracana — i naprawa tipsterów nie musi na nią czekać.

---

## 2. Wartość w tym, co mamy — gdzie ucieka

Po naprawie importu krok **działa**, ale dowozi znikomo mało. Realny przebieg na dziś:

| etap | liczba | strata |
|---|---|---|
| picki pobrane | 86 | — |
| dopasowane do fixture'a | 25 | **−61 (71%)** |
| policzalne roszczenia | **1** | −24 |
| zdarzenia pokryte | 21 / 217 | 9,7% |

Czyli: **jedno** użyteczne roszczenie na 217 meczów. To jest właściwy powód, dla którego
tipsterzy „nic nie dają" — nawet gdy krok nie pada.

### 2a. Dopasowanie nazw — 27 z 61 strat jest do odzyskania od ręki

`names_score` to goły `SequenceMatcher` na znormalizowanym kluczu. Bez aliasów, bez
token-set, bez obcinania sufiksów. Próg 82 na obu stronach.

Zmierzone: **27 z 61 niedopasowanych picków ma komplet tokenów krótszej nazwy w dłuższej** —
czyli token-set je odzyskuje bez ryzyka:

```
seq=80 | Birmingham vs Southampton      -> Birmingham City - Southampton
seq=77 | CA Tigre vs Barracas Central   -> Tigre - Barracas Central
seq=70 | West Ham vs Wolverhampton      -> West Ham United - Wolverhampton Wanderers
seq=59 | Portsmouth vs Derby            -> Portsmouth - Derby County
seq=50 | Akron Togliatti vs Lokomotiv M -> Akron - Lokomotiv Moscow
seq=50 | Xamax vs Yverdon               -> Neuchâtel Xamax - Yverdon Sport
```

Samo to podnosi dopasowania **25 → 52 (+108%)**.

W repo **już jest** `src/bet/discovery/team_aliases.py`, używane przez ścieżkę Superbet.
Matcher tipsterów go nie używa w ogóle.

Dalsze ~7 do odzyskania średnim nakładem:
- **tenis, nazwisko + inicjał**: `Sakkari M.` vs `Maria Sakkari`, `Jones F.` vs `Francesca Jones`,
  `F. Cerundolo` vs `Francisco Cerundolo` — potrzeba dopasowania po nazwisku
- **przedrostki/sufiksy klubowe**: `Helsingborg` vs `Helsingborgs IF`, `PARMA/CREMONA` vs `Parma/Cremonese`
- **błąd ekstraktora**: `"Al vs Hilal - Al Ahli"` — splitter „A vs B" rozjeżdża się na myślniku
  w `Al-Hilal - Al-Ahli`; podobnie `"Q. Halys vs F. Diaz vs Acosta"` tnie nazwisko `Diaz Acosta`

Reszta (~27) to realnie nieodkryte fixture'y — nie wina matchera.

### 2b. Klasyfikacja roszczeń — bramka jest przestarzała wobec arkusza

Z 86 picków **tylko 3** są „policzalne". Powody odrzuceń pokazują, że reguła
„tylko czysty total meczowy" nie nadąża za tym, co ANALYZE dziś konsumuje:

- **Niespójność wprost do naprawy.** `'Powyżej 19.5 gemów w meczu'` → **COUNTABLE**,
  ale `'Liczba gemów - poniżej 19,5'` → odrzucone jako `player_prop`. Ten sam rynek,
  ta sama linia, inne sformułowanie. Detektor zakresu myli się jawnie.
- **Totale drużynowe wyrzucane**, choć arkusz je pokrywa:
  `'Barracas Centra over 13,5 fauli'`, `'wiecej kartek: Getafe'`
- **Propsy zawodników wyrzucane**, choć arkusz je pokrywa:
  `'Yamal Lamine celne strzały 2+'`
- **`unit_not_recognised` (13) kłamie w audycie** — to głównie gołe `'x'`, `'1'`, `'X2'`,
  czyli 1X2 bez tekstu rynku; powinny być `outcome_market_not_a_total`.
  Ale jest tam też realna luka słownika: `'over 3,5 seta'`.

Detektor zakresu myli też moneyline z totalem drużynowym (`'Tien wygra'`, `'Buse'`)
i awans z propsem (`'Awans : Legia Warszawa'`).

---

## 3. Kolejne strony — najpierw wyciśnijmy obecne

Zarejestrowanych źródeł: **15**. Z ekstraktorem: **4**. Domyślnie aktywne: **2**.

- `sportsgambler` — ma 331-liniowy ekstraktor **i atestację operatora**, a nie jest
  w `DEFAULT_LIVE_SOURCE_IDS`. Uruchomiony dziś ręcznie: **0 picków, bez blokady**.
  Ekstraktor nie trzyma się już strony, a krok raportuje to nieodróżnialnie od
  „dziś nic nie było". Cicha awaria.
- `protipster` — ma ekstraktor, ale **brak wpisu w pliku atestacji**, więc zostałby zablokowany.
- `forebet`, `predictz` — atestacja ma `reviewed_by: REPLACE_WITH_OPERATOR` (placeholder),
  brak ekstraktorów.

Wniosek: dokładanie stron **teraz** nic nie da — 71% tego, co już pobieramy, ginie
na dopasowaniu, a 96% reszty na klasyfikacji. Najpierw naprawić lejek.

---

## 4. Drobniejsze, ale realne

- **`DEFAULT_REVIEW_PATH` jest ścieżką względną** (`docs/pipeline/tipster_terms_review.local.json`),
  więc krok zależy od cwd. Plik jest gitignorowany — w świeżym klonie/worktree kroku nie da się
  uruchomić bez ręcznego wskazania ścieżki.
- **Krok jest niewidoczny w telemetrii, gdy pada najgorzej.** Awaria importu = brak wiersza
  w `pipeline_runs`, czyli dokładnie ten scenariusz, o który operator pyta („czemu kolumna pusta"),
  nie zostawia śladu. Warto opakować `main()` w `try/except`, który zapisze wiersz i zwróci PARTIAL.
- **Brak testu na entrypoint.** Jeden test uruchamiający `run_tipsters.py` jako podproces
  na fixture'owym event_liście złapałby tę awarię w dniu, w którym powstała.

---

## 5. Rekomendowana kolejność

1. ~~Naprawa importu~~ — **zrobione**, `9e2d2f55`
2. Test na entrypoint (subprocess) — żeby to się nie powtórzyło po cichu
3. Token-set + `team_aliases.py` w `names_score` → **+108% dopasowań**, największy zysk
4. Naprawa detektora zakresu w `claim.py` (gemy, totale drużynowe, propsy) → odblokowuje
   rynki, które arkusz już obsługuje
5. Dopasowanie tenisa po nazwisku + inicjale
6. `record()` na ścieżce awaryjnej + absolutna ścieżka atestacji
7. Naprawa `sportsgambler` (lub jawne oznaczenie jako martwy) — dopiero potem nowe strony
