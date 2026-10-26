# Audyt warstwy agentowej - analitycy (2026-10-26)

Zakres: agenci `sofa-analyst-football`, `sofa-analyst-tennis`, `sofa-analyst-sport`
(oraz weryfikator tam, gdzie dzieli kontrakt), ich umiejętności, koszt, zapis
wyników w plikach oraz na kuponie PDF / HTML. Materiał źródłowy w tym katalogu:
`analyst_measurement.md` (pomiar wartości i kosztu odczytów 10-13..10-25),
`lit_review.md` (literatura), `sources_football_tennis.md`,
`sources_measured_sports.md` (źródła per sport, sprawdzone 2026-10-26).

## 1. Co pokazał pomiar (10-13..10-25, 13 dni)

Wartość odczytów (single, wszystkie sporty, mieszane epoki, stawka 1 j. po
wydrukowanym kursie):

| grupa | nogi | mecze | trafienie − 1/kurs | ROI |
|---|---|---|---|---|
| zdjęte odczytem (WATCH + NO_BET) | 1 104 | 331 | −3,0 pp | −3,9% |
| w tym NO_BET | 32 | 13 | −23,0 pp | −29,0% |
| KEEP (przeczytane, wydrukowane) | 9 198 | 848 | −2,5 pp | −3,0% |
| nieczytane (wydrukowane) | 53 912 | 6 532 | −4,6 pp | −5,5% |

- Bootstrap po meczach (2000 losowań), ROI zdjętych minus KEEP:
  **−0,9 pp [−5,9; +4,2]**. Piłka +1,1 [−4,0; +6,1], tenis −8,4 [−28,4; +8,2],
  sporty mierzone −12,1 [−33,2; +11,5]. **Żaden przedział nie wyklucza zera.**
  Zdjęte nogi realizują się względem kursu tak samo jak zostawione. Odczyty
  nie mają zmierzonej przewagi, ale też niczego nie psują.
- NO_BET (32 nogi) wypadł wyraźnie słabo (−29%), tylko n jest małe.
- Koszt: 204 raporty, 6,4 MB, 11 658 wpisów odczytu. Rundy re-read dochodziły
  do 13 dziennie (10-25: 45 raportów, 1,4 MB). Dokładne powtórne odczyty tej
  samej nogi to tylko 1,1%. Ten sam mecz w więcej niż jednym raporcie: ~11%
  odczytów meczu. Wtedy cały dossier i przegląd web robiono od nowa.
- Przegląd web: 14% sekcji meczu nie miało żadnego `[WEB:]`, średnio ~2,5
  źródła na mecz. 31% sekcji kończy się „nic istotnego”.
- Zapis: powód odczytu na PDF był ucięty do 140 znaków. Pełna analiza meczu
  żyła tylko w jednym z ~50 plików `.md` dnia, nikt jej nie znajdował przy nodze.

## 2. Literatura (skrót, szczegóły: `lit_review.md`, kontrakt: `literature.md`)

- Kurs zamknięcia to najlepsza publiczna prognoza. Typerzy i eksperci nie
  biją go po marży; wybór „dobrych” typerów nie pomaga.
- Wartość analityka przy kursie sprowadza się do dwóch rzeczy: **defekt nogi
  tak, jak ją wydrukowano** (tożsamość, zakres, format, rynek rozliczany inaczej)
  oraz **fakt nowszy niż cena** działający przez zmienną nogi.
- Siła sygnałów kontekstu: ABSENCES / ROTATION > SCHEDULE > CONDITIONS
  (tylko ekstremalne) > MOTIVATION ≈ MORALE ≈ DERBY ≈ 0.
- Na sport: bramkarz w hokeju (sv% .905 → .897 przy jednym dniu odpoczynku),
  raport kontuzji i back-to-back w koszykówce (~2,3 pkt), piątka i pula map
  w CS2, szóstka w siatkówce (niepublikowana przed meczem), długi poprzedni
  mecz w tenisie (Elo-adjusted 61% → 32%, Wielki Szlem mężczyzn).

## 3. Źródła per sport

Pełne listy, sprawdzone 2026-10-26 (dostęp OK / R / zablokowane), w
`.claude/skills/sofa-analysis-core/references/sources-<sport>.md`. Każda lista
ma obowiązkowe sprawdzenia w kolejności, checklistę „co przesuwa / jaki dowód /
co może unieść” i źródła z dostępnością. Źródła zablokowane (HLTV, Liquipedia
HTML, volleybox, EuroLeague…) są nazwane z alternatywą, żeby agent nie tracił
na nie zapytań. Zgodnie z zasadą „tylko Sofascore i Superbet” żadna lista nie
każe brać **liczb** od innego dostawcy. Recenzja usunęła statshub (stawki
sędziów), tennisabstract (Elo, szybkość nawierzchni) i naturalstattrick /
moneypuck.

## 4. Zmiany w umiejętnościach i agentach

- `sofa-analysis-core`: przegląd kontekstu przepisany (`context-pass.md`).
  Kolejność: punkt wyjścia → **fakty zabójcze przed wyszukiwaniem** → wyszukiwanie
  (~6 zapytań) → werdykt przez zmienną nogi. Tabela wag i ranking źródeł.
  Zasada operatora bez zmian: jedna domena albo opinia daje najwyżej WATCH,
  NO_BET wymaga dwóch domen albo defektu w artefakcie.
- **Przegląd delty**: noga meczu przeczytanego wcześniej tego dnia ma
  `prior_analysis` (raport, czas, `full_pass_at_utc`). Analityk czyta tamtą
  sekcję i sprawdza tylko, co się zmieniło (~2 zapytania). Pełny przegląd
  powtarza, gdy ostatni pełny przegląd z źródłem web jest starszy niż 6 h;
  sekcja delty tego zegara nie przestawia.
- Nowa umiejętność `sport-analysis` (hokej / kosz / siatka / CS2): co wyceniło
  nogę, tożsamość i zakres najpierw, decydujące fakty sportu, szablon sekcji.
- Szablony sekcji meczu (piłka, tenis, sporty mierzone): nagłówek z tokenem
  `· sofa:<id>`, zwięźle, najwyżej ~4 000 znaków, bez kopiowania tabel z artefaktów.
- Stare przykłady w `veto-contract.md` / `evidence-rules.md` uzgodnione z nowymi wagami.
- Runda re-read: pliki sportów mierzonych z łącznie ≤ 6 meczami czyta jedna
  instancja `sofa-analyst-sport` (raport `<d>_analiza_sports_r<n>.md`).

## 5. Zapis: pliki, PDF, HTML

- `merge_reads.py` stempluje każdy scalony odczyt `read_at_utc` (czas scalenia)
  i odkłada sekcje meczów każdego raportu do **`analyses.json`**
  (`bet.sofa.analyses`, po id Sofascore, najnowsze pierwsze).
  `build_analyses.py --date <d>` odbudowuje plik z raportów na dysku.
- **HTML**: przy każdej nodze notatka odczytu (werdykt, autor, godzina, tag,
  pełny powód), a pod nią **zwinięta pełna analiza meczu** (każdy raport osobno,
  renderowana dopiero po rozwinięciu). Nodze nieczytanej z przeczytanego
  meczu też pokazuje się analiza meczu.
- **PDF**: przy nodze pełny powód (do 600 znaków; łącznie do 700 na komórkę,
  bo wiersz tabeli nie może przejść na następną stronę), godzina i tag, wskaźnik
  „A<n>” do **aneksu „Aneks: analizy meczów”** z najnowszą sekcją analityka i
  weryfikatora każdego wydrukowanego przeczytanego meczu.
- `report_check` (hook po zapisie raportu) zgłasza sekcję czytanego meczu bez
  tokenu `sofa:<id>` w nagłówku.
- Wszystko to jest wyświetlaniem: nic nie zmienia tego, co się drukuje, ani C3,
  ani księgi.

## 6. Testy i przeglądy

- Nowe testy: `tests/sofa/test_analyses.py` (21), poprawione
  `test_history_readers_follow_comparability.py`, `test_report_check.py`.
- Runda 1 przeglądu kodu: 4 potwierdzone błędy, wszystkie naprawione z testem.
  - Za długie odczyty na jednej nodze wywalały PDF (`LayoutError`).
  - `md()` zapętlał się na wciętym `#`.
  - `<!--` w sekcji czyścił całą stronę HTML (`\!` to niepoprawny escape JSON).
  - Nagłówki raportu („Nagłówek”, „Zdjęte”) były zapisywane jako sekcje meczu.
  - Do tego: bloki ```, CRLF, kolejność sekcji, ręcznie zepsuty store,
    znacznik czasu przy `--slip`.
- Runda 1 przeglądu kontraktów: NO_BET na jednej domenie w czterech plikach
  sportów (naprawione: dwie domeny, inaczej WATCH), sprzeczność wag nastrojów z
  regułą operatora (przywrócone „najwyżej WATCH”), liczby od innych dostawców
  (usunięte), zły `jq` do wcześniejszej sekcji, łańcuch delt bez pełnego
  przeglądu (`full_pass_at_utc`), cytaty literatury niezgodne z materiałem
  (poprawione), stare przykłady, rozbieżne budżety długości.
- Runda 2 i weryfikacja na żywo: sekcja 8.

## 7. Decyzje dla operatora (nie wdrożone)

1. **Zakres odczytów.** Odczyty nie mają zmierzonej przewagi
   (−0,9 pp [−5,9; +4,2]). Najtańsza zmiana kosztu to mniejszy zakres C3 (np.
   20 zamiast 30 meczów) albo tańszy model dla analityków sportów mierzonych.
   To zmienia, co się drukuje nieczytane, więc decyzja należy do operatora.
2. **NO_BET** (32 nogi, −29%) wygląda na jedyny sygnał. Warto go dalej mierzyć
   (audit 7e / 7i), zanim cokolwiek się na nim oprze.
3. Nowe reguły, które mogą przesunąć zdjęcia (zmiana trenera, sprawa ESIC,
   Questionable / GTD w NBA, budżet delty ~2 zapytania), są sformułowane jako
   „może unieść WATCH przez zmienną nogi”, w granicach dotychczasowej reguły
   operatora. Ich wpływ zmierzy audit tagów po ~2 tygodniach.

## 8. Runda 2 i weryfikacja na żywo

### Runda 2 przeglądu (świeży recenzent, kod + kontrakty)

Bez awarii PDF i bez crashy; poprawki rundy 1 sprawdzone (aneks z sekcją
29 000 znaków, tabelą 60 kolumn i znakami sterującymi buduje się; 10 odczytów
po 600 znaków na nodze mieści się w komórce). Znalezione i naprawione:

- odbudowa `analyses.json` z dysku brała raporty kuponów czatowych `_kupon_`
  (10-20..10-25: 39 plików, 82 sekcje), które jako najnowsze stawały się
  sekcją aneksu i `prior_analysis` - wykluczone, z testem;
- łańcuch delt gubił pełny przegląd (trzeci odczyt meczu widział tylko deltę)
  - `prior_analysis.full_pass_report` i `jq` czytający obie sekcje;
- weryfikator nie pisał sekcji meczu - kontrakt weryfikatora ma teraz sekcję
  `### … · sofa:<id>` dla każdej nogi, której by nie postawił;
- pełny przegląd zakończony uczciwym `UNVERIFIED` (ITF, szóstka siatkówki)
  liczy się jako pełny; hook i parser czytają token tak samo; odnośnik „A<n>”
  tylko do meczu, który aneks drukuje; dwie domeny przy NO_BET w piłce.
- Rozmiar: PDF 10-25 urósł z 437 do 556 stron bez aneksu (pełne powody,
  odczyty także przy zablokowanych nogach) i 627 z aneksem; render 22,9 s
  zamiast 22,2 s. HTML 9,5 → 10,3 MB. 10-26: 310 stron, aneks od strony 291.

### Weryfikacja na żywo, 2026-10-26

1. **Warstwa plików na prawdziwym dniu.** Dzisiejsza sesja dnia scaliła 9
   raportów już tym kodem: 55 meczów, 55 sekcji, każdy czytany mecz ma swoją
   sekcję z tokenem w nagłówku, 357 / 357 odczytów ze stemplem
   `read_at_utc`; PDF ma aneks, HTML ma analizy pod nogami.
2. **Mechanizm delty, dwie instancje na prawdziwych danych** (raporty w
   scratchu, dzień nietknięty - md5 `reads.json` / `analyses.json` bez zmian):
   - analityk piłki, 2 mecze / 11 nóg (w tym nogi buildera B1): delta, 1-2
     wyszukiwania na mecz, 11 × KEEP, `report_check` czysty, `merge_reads
     --dry-run` 0;
   - łączona instancja sportowa (hokej + siatkówka), 2 mecze / 14 nóg:
     delta, bramkarze NHL sprawdzeni (niepotwierdzeni), 14 × KEEP, walidacja
     czysta;
   - obie sekcje z tokenem, oznaczone jako delta, 2,8-3,6 tys. znaków.
   - Co poprawiono po teście: nogi buildera miały inny kształt (bez
     `kickoff_utc`, `odds` zamiast `offered_odds`) - `read_set.py` je
     wyrównuje (test); delta przy pełnym przeglądzie młodszym niż 1 h nie
     wyszukuje nic; fakty zabójcze delta dziedziczy.
3. **Ocena jakości 9 dzisiejszych raportów** (niezależny recenzent, 6+6
   sprawdzeń faktów i liczb):
   - koszykówka, hokej, siatkówka, CS2: dobre (oficjalny raport kontuzji NBA,
     bramkarz, uczciwe `UNVERIFIED` dla szóstki);
   - **19 z 24 WATCH bez faktu nowszego niż cena** - h2h, seria, forma,
     tabela, luka model-próbka, „BUY ≈ KILL”, most ratingu między ligami;
   - 250 z 338 tagów `[WEB:]` bez daty publikacji; 5 sekcji tenisa bez faktów
     zabójczych; 11 zbiorczych KEEP (`market: null`) na ~300 nogach;
   - fakty z sieci prawdziwe tam, gdzie dało się je znaleźć (3 nie do
     potwierdzenia); 2 błędy liczenia (karty Fenerbahçe „w lidze” liczone z
     pucharami, trzecie tercje Calgary).
   - **Wdrożone**: kontrakt mówi wprost, co musi nazwać powód zdjęcia (fakt
     nowszy niż cena z datą albo `DEFEKT: …`) i czego nie wolno (lista
     powyżej), „BUY ≈ KILL is a WATCH” usunięte; `report_check` (hook) odsyła
     raport przy usunięciu bez faktu, tagu bez daty, braku faktów zabójczych
     i zbiorczym KEEP. Na dzisiejszych raportach wyłapuje dokładnie to, co
     znalazł recenzent (30 usunięć, 11 zbiorczych KEEP, 1 sekcja tenisa).
   - **Skutek dla druku**: mniej zdjęć odczytem, czyli więcej nóg na kuponie.
     Zgodne z pomiarem (zdjęcia ze statystyk realizowały się jak KEEP) i z
     regułą operatora „rozróżniaj w cenie, nie tnij”; zmierzy to audit 7i za
     ~2 tygodnie.

### Bramki

`pytest tests/sofa` 6032 passed / 2 skipped, 1 failed:
`test_basketball_player_v2::test_sport_confidence_takes_them_only_under_the_evidence_and_refuses_them`.
Ten test czyta żywy `config/sofa_superbet_line_evidence.json`, a poranne
odświeżenie 10-26 (inny proces, plik poza tym commitem) dało 18 kombinacjom
rodzin V2 dowody linii. Na configu z HEAD przechodzi; padnie temu, kto
zacommituje odświeżony config - trzeba go uniezależnić od daty. ruff i mypy
--strict czyste, rejestr testów 26 / 0.
