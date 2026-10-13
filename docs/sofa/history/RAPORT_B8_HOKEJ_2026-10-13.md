# B8 hokej: strzaly x save% i pusta bramka (2026-10-13)

Wynik: **zaden wariant nie spelnil progu z gory**, przelaczniki
`HK_SHOTS_FROM_UTC` i `HK_EMPTY_NET_FROM_UTC` w `bet.sofa.epochs` zostaja
`None` (model bez zmian, nic nie wchodzi do druku).

- Strzaly (zamiana centrum): `total` log-loss +0,00126 [+0,00010, +0,00241]
  gorzej; mieszanka +0,00025 [-0,00033, +0,00084] bez poprawy; oba poprawiaja
  `handicap` i `winner` (np. -0,0017 / -0,0024), ale na 25% meczow (1 485 z
  5 965) ze strzalami.
- Pusta bramka dopasowana (e1 0,219, e2 0,251, t 0,143): `handicap`
  -0,00037 [-0,00074, +0,000006], `total` gorzej +0,00111.
- Pokrycie: strzaly w 6 755 z 29 516 meczow kopii, pazdziernik 2026 = 0
  (dociaganie w toku do `data/sofa.db`).

Kod jest wylaczona opcja (flagi `--hk-shots`, `--hk-empty-net` w
`fit_sport_confidence.py`, `run_sport_confidence.py`); testy
`tests/sofa/test_hockey_shots_empty_net.py`. Szczegoly:
`docs/sofa/evidence/hockey_goalie_empty_net_2026-10-13.md`.
