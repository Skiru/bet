Zadanie: zaimplementuj, zmierz i - tylko jeśli zaliczy - wdróż poprawkę terminarza / zmęczenia w prognozie piłki i tenisa, według planu `docs/sofa/history/PLAN_KONTEKST_TERMINARZA_PILKA_TENIS_2026-11-08.md`.

## Przeczytaj najpierw (w tej kolejności)
1. `CLAUDE.md` i `.claude/skills/sofa-pipeline/references/model-state.md`.
2. Plan (wyżej) - jest nadrzędny.
3. `docs/sofa/evidence/kontekst_terminarza_2026-11-08/r3_final_review.md` - wiążące: teksty zastępcze D1-D25, **reguła zaliczenia (c)**, **lista kroków (d) 1-34**, sekcja 6 (odwrócony cień).
4. Resztę tego folderu (`r1_*`, `r2_*`) czytaj w miarę potrzeby, przez subagenta, nie w całości do głównego kontekstu.
5. Jeśli istnieje `docs/sofa/history/STAN_KONTEKST_TERMINARZA_*.md` - to kontynuacja: wejdź od zapisanej fazy.

## Cel i definicja sukcesu
Dokładniejsza prognoza (log score, kalibracja) każdego rynku piłki i tenisa dzięki kontekstowi terminarza - **nie** przewaga nad ceną. "Pomogło" = grupa statystyk zalicza regułę (c) z `r3` (P1-P6, Holm, bootstrap klastrowy, efekt >= 3% środka, kalibracja nie gorsza, nie-gorszość pozostałych grup i warstw). Nie ma innej definicji. Nie wolno łagodzić reguły, zmieniać jej po spojrzeniu na wyniki, ani uruchamiać egzaminu drugi raz (G1-G5).

## Decyzje operatora (2026-11-08) - masz je, nie pytaj o nie ponownie
- Zgoda na: kopię bazy, przebiegi odtwarzania, przefitowanie krzywych na kopii i instalację **wyłącznie grup, które zaliczyły (c)**, z przełącznikiem w `bet.sofa.epochs` od **następnego dnia 00:00Z po commicie instalacji**, nigdy w zbudowany dzień. Staged pliki `.next.<D>.json` z `effective_from`, nigdy nadpisanie zainstalowanego pliku.
- Cień odwrócony (r3 sekcja 6): każdy objęty wiersz niesie `p_central` bez poprawki; `T-SCHEDULE-TERM-FORWARD` zarejestrowany przed dniem przełącznika, z regułą wycofania zapisaną z góry.
- Instalujesz zamrożone współczynniki, które zdały egzamin - nie ponownie dopasowane na pełnej historii.
- Żadna grupa nie zalicza -> commit tylko skryptów pomiaru, pre-rejestracji i raportu (po polsku, `docs/sofa/evidence/`), wpis "measured and declined" w model-state.md; bez przełącznika, bez configu. To jest pełnoprawny wynik.
- Przesadna pewność przy kursach >= 1.40 jest poza zakresem - nie ruszaj jej.

## Twarde zasady
- Odtwarzanie i fity tylko na kopii (`VACUUM INTO data/refit_<data>_schedule/...` z `file:data/sofa.db?mode=ro`), `--db-path <kopia>`, `--without-db-backup`; pętle dzienne zostają włączone; mostek do Sofascore niepotrzebny - nie uruchamiaj go.
- Długie przebiegi w tle z logiem w `data/refit_<data>_schedule/`; najpierw próba 5 dni z kontrolą zgodności p do 1e-9 (D4).
- Plik egzaminu z wynikami (`exam_y`) otwiera wyłącznie `measure_schedule_exam.py --spec-sha <sha>`, raz; log egzaminu odmawia drugiego przebiegu.
- Każda zmiana kodu ma test w `tests/sofa/`. Bramki przed każdym commitem: `pytest tests/sofa -q`, `ruff check src/bet/sofa scripts/sofa`, `mypy --strict --no-incremental src/bet/sofa scripts/sofa`, `check_test_registry.py`.
- Drzewo robocze dzielą inne sesje: `git status` na starcie, commit tylko własnych ścieżek (`git add <ścieżki>`, nigdy `-A` / `.`), nigdy `git stash`, commit prosto na `main`, push tylko zweryfikowanego SHA (`git push origin <sha>:main`), przed pushem sprawdź `git log origin/main`.
- Pre-rejestracja (F0) + plan = jeden commit **przed** jakąkolwiek analizą wyników; zawiera tabelę statusów wszystkich C1-C32, M1-M18, D1-D25.
- Nigdy nie zmyślaj liczby; każda liczba w raporcie ma plik źródłowy. Sprawdzaj liczby subagentów lokalnie.
- Commit i push zmian, które zmieniają to, co się drukuje, wyłącznie po zaliczeniu (c), z E2E na kopii dnia (nigdy prawdziwy `runs/sofa/<d>/`; md5 prawdziwych plików przed i po).

## Sposób pracy
- Fazy F0-F8 z planu, kroki (d) 1-34 z `r3` po kolei. Po każdej fazie: krótka linia dla operatora (co zrobione, co dalej, ile potrwa) i aktualizacja `docs/sofa/history/STAN_KONTEKST_TERMINARZA_<data>.md` (faza, SHA, hashe, ścieżki, następny krok).
- Wielofazowe czytanie kodu i pomiary deleguj subagentom; do głównego kontekstu wraca tylko wniosek.
- Jeśli coś blokuje (brak danych, kod nie pozwala, reguła niewykonalna): zatrzymaj się, zapisz stan i opisz blokadę - nie obchodź reguły.

## Raport końcowy (po polsku, do operatora)
Pierwsza linia: werdykt ("wdrożone: <grupy>, od <data> 00:00Z" albo "nic nie zaliczyło - nic nie wdrożone"). Potem tabela grup: Delta z przedziałem, efekt, kalibracja, P1-P6; rodziny rynków objęte / nieobjęte; wszystkie spojrzenia (G5); SHA commitów i push; grupa księgi; co zostało otwarte.
