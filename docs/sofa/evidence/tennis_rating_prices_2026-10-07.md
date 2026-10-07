# Tenis: rating zamiast próbki w cenie gemów — pomiar 2026-10-07

Podstawa przełącznika `epochs.TENNIS_RATING_PRICES_FROM_UTC` (2026-10-07 14:05Z).
Pomiar tylko do odczytu, na historii (nie na naszych rozliczonych dniach).

## Metoda
- Historia singli z bazy: 243 025 meczów do 2026-10-07 (`load_history`).
- Dwa okna walk-forward: W1 = cięcie 03-01, ocena do 06-15; W2 = cięcie 06-15,
  ocena do 10-08. Na każdym cięciu: współczynniki per tier i tabela sąsiadów
  z meczów sprzed cięcia; książka ratingu aktualizowana online, mecz oceniany
  przed dopisaniem (brak wycieku).
- Estymator „próbka" = ścieżka produkcyjna stats-only: ostatnie 10 meczów
  best-of-3 na tej samej powierzchni, K=5, `p_empirical_centred_raw`
  (`games_won_for`) albo NB (`games_total`), joint niezależny dla handicapu
  i `most_`. Wiersze tylko tam, gdzie p próbki jest w [0,05; 0,95].
- Linie: syntetyczna siatka połówkowa (nie drabina Superbetu). Bootstrap po
  meczach, 1000 prób; log-loss z obcięciem p do [0,01; 0,99].

## Wyniki (log-loss, rating minus próbka; ujemny = lepszy rating)
| rodzina | W1 | W2 | razem [95%] |
|---|---|---|---|
| `games_won_for` (n ≈ 1,45 mln wierszy) | −0,0720 | −0,0713 | −0,0716 [−0,0737; −0,0695] |
| `handicap_games` (strona A, n ≈ 206 tys.) | −0,0833 | −0,0804 | −0,0817 [−0,0867; −0,0765] |
| `most_games` (A/B, n ≈ 30 tys.) | −0,0813 | −0,0702 | −0,0753 [−0,0818; −0,0686] |
| `games_total`, 50/50 NB + rating vs sam NB | −0,0088 | −0,0087 | stack W1→W2: −0,0097 [−0,0109; −0,0084] |

- Zysk w każdym tierze (`games_won_for`: TOUR −0,056, CH −0,057, ITF −0,077);
  przeżywa rekalibrację Platta (nie jest tylko luką kalibracji).
- Stos próbka + rating daje ≈ 0,91–0,98 wagi ratingowi i tylko −0,0005..−0,0008
  dodatkowo: rating wystarcza.
- `games_total`: sam rating wiąże się z NB (−0,0002 [−0,0019; +0,0017]); czysta
  częstość empiryczna jest gorsza od NB (+0,0079); NB wyśrodkowany na średniej
  ratingu gorszy (+0,0117). Stąd mieszanka 0,5/0,5 (`W_GAMES_TOTAL_RATING`).
  Mieszanka nie usuwa przeszacowania OVER na liniach centralnych (+3–4 pp).

## Zastrzeżenia
- Remis `most_games` nie był mierzony: zostaje na próbce.
- Rating tylko dla best-of-3 i dla graczy z >= `MIN_RATED` meczów; reszta wraca
  do próbki (ok. 21% wierszy w oknie).
- Współczynniki `config/tennis_rating.json` mają cięcie 2026-10-01, więc mecze
  sprzed niego są dla nich w próbce.
- Po wdrożeniu krzywe tenisa zostały dopasowane na replayu tego samego
  estymatora (`calibrate_from_cache.py`, rating w chwili meczu) — refit
  zainstalowany 2026-10-07 17:51Z.
