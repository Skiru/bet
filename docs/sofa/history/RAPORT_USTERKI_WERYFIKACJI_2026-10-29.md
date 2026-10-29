# Usterki z weryfikacji 2026-10-29 - poprawki i pomiary

Źródło: lista usterek kontraktów i kodu z weryfikacji dnia 2026-10-29
(raport `runs/sofa/2026-10-29/*_weryfikacja*.md`).

## Poprawione

| usterka | poprawka | od kiedy | test |
|---|---|---|---|
| Walkowery 0:0 w próbkach (Maardu: 15514355 Kalev, 15514366 Kalju U21) | `comparability.is_awarded_event` (`isAwarded` Sofascore); próbki (`samples.admit`, `peer_history`) i historia ratingu piłki w SHEET (`FootballResult.awarded`, `without_awarded`) pomijają mecz przyznany przy stoliku | przełącznik `AWARDED_EXCLUDED` 2026-10-30 00:00Z (zmienia druk), grupa księgi „od 10-30” | `tests/sofa/test_awarded_excluded.py` |
| Fałszywy alarm merge_reads przy pustym bloku `[]` | ostrzeżenie tylko, gdy raport nie ma bloku ```json reads wcale | od razu | `test_an_empty_reads_block_is_no_broken_contract` |
| Agent weryfikatora uznawał notę TENNIS_RATING na gemach w secie za defekt | `.claude/agents/sofa-verifier.md`: `SET_RATING_PRICED_MARKETS` (gemy w secie, `sets_total`) wyceniane ratingiem od 10-13 18:10Z | następna sesja (agenci ładują się przy starcie) | - |
| Zdublowany mecz Prat - Sant Rafel (17136469 / 17336477) w dossier | `dossier.team_games` przez `samples.one_listing_per_match` (forma, odbudowana tabela, styl, zestawienie) | od razu (tylko widok) | `test_one_match_listed_under_two_ids_is_one_game` |
| Analitycy uruchomieni w tle | `/sofa-analyze`, `/sofa-day`, `/sofa-verify`: jeśli agent i tak wróci jako zadanie w tle, czekać na powiadomienie i sprawdzić plik raportu przed `merge_reads.py` | następna sesja | - |

Skala walkowerów w cache (listingi `last`, 10-29): piłka 6 065 zdarzeń
`isAwarded` ze statusem 100, koszykówka 537 (20:0), siatkówka 62, hokej 59.
Model wyników sportów ich nie czyta (brak tercji / kwart / setów), co
sprawdza test.

## Zmierzone - bez zmian

- **Pomost ratingu w pucharach** (Prat - Athletic, Ribadesella - Racing):
  podejrzenie „rating za płytki” **niepotwierdzone**. 12 825 meczów pucharów
  krajowych od 2025-07-01, odtworzenie książki jak w SHEET, bootstrap po
  meczach: przy przewadze 1,5-2 gola (Prat - Athletic 1,69) różnica
  zrealizowana minus przewidziana +0,03 [-0,13; +0,19], N 1 204; przy >= 2
  gole -0,46 [-0,58; -0,33], N 2 008 - rating jest tam za stromy, nie za
  płytki. Nasze rozliczone nogi pucharowe z luką siły >= 0,3: 738 nóg / 75
  meczów, trafienia minus pewność -0,001 [-0,042; +0,037]. Kandydat na
  przyszłość: ściąganie przewagi faworyta w pucharze powyżej ~2 goli
  (otwarte, model-state.md (e)).
- **Liga drużyny po awansie / spadku** (Arka 202, Deportivo 54): zgodnie z
  regułą (`RatingBook.domain` = najczęstsza liga z 40 meczów w 365 dniach),
  zmiana dopiero po ~18-20 meczach w nowej lidze; Arka - Stal wyceniony jako
  para międzyligowa, choć obie grają w 1. Lidze. Niezmierzone - propozycja
  (liga z bieżącego sezonu po >= 3 meczach) czeka na pomiar i zgodę
  operatora (model-state.md (e)).

## Pytania z weryfikacji - odpowiedzi

- **Tenis KICKED_OFF wg zegara Superbetu** (Bokova 17430858, Podrez
  17432140, Hennemann 17431367, Haavisto 17431425): Superbet 10:09-10:11Z,
  Sofascore 11:00Z. Bokova zaczęła o 10:34:13Z - zegar Sofascore był
  spóźniony; reguła „najwcześniejszy zegar” zadziałała słusznie. Trzech
  pozostałych startów cache nie zna. Bez zmian.
- **Everton - Preston, 0 kartek** (16798259): pełny feed (46 pozycji
  statystyk, obie połowy, składy, 4 gole zgodne z wynikiem 0:4, 10 zmian, 9
  fauli), żadnej kartki w incydentach; Sofascore pomija pozycję „Yellow
  cards” przy zerze. Prawdziwe 0, nie brak danych.
- **`sb:hockey:player_pp_points|UNDER`**: rynek dwustronny, więc próg 300
  linii (reguła jednostronna) nie dotyczy; pewność to dolna granica Wilsona
  własnych linii w kubełku p z poprawką `deff`, kubełki 142-392 linii /
  93-162 mecze, powyżej `MIN_EVIDENCE_BUCKET` 50 i `MIN_EVIDENCE_GAMES` 15.
  Przeliczone (n=319 -> 0,875, druk 0,876). Zgodnie z regułą; ryzyko to
  skupienie wielu nóg w kilku meczach NHL.

## Bramki

`pytest tests/sofa` 6188 passed, 2 skipped; ruff, mypy --strict,
`check_test_registry.py` czyste.
