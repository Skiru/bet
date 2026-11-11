# Mniej złe nogi - pomiar 2026-11-11

Wniosek operatora (2026-11-11): „znaleźć sposób, żeby wiedzieć, które nogi
faktycznie obstawiać" i „lepiej mieć mniejszą cenę, ale stabilny, ogarnięty
system wygrywania". Znacznik `lesser_loss` (`bet.sofa.lesser_loss`) jest na
kuponie od 2026-11-12 00:00Z (`epochs.LESSER_LOSS_MARK_FROM_UTC`). To tylko
adnotacja: żadna noga nie wchodzi, nie wypada i nie zmienia miejsca, a
pewność się nie rusza. Test zarejestrowany z góry: `T-LESSER-LOSS-flag`.

Skrypt (tylko odczyt):

```
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_lesser_loss.py \
    --from 2026-10-30 --to 2026-11-10 --split 2026-11-05
```

## Dane i metoda

- Wydrukowane single `11_coupon.json` z dni 10-30..11-10 z oceną w
  `13_results.json`, tylko WIN / LOSS: 64 546 nóg, 6 787 meczów. Dni z
  kilku grup epok ledgera - to widok wydrukowanych nóg, nie ledger.
- ROI liczone przed podatkiem 12%. Przedział 95% pochodzi z bootstrapu po
  meczach (nogi jednego meczu losowane razem).
- Dziesięć cech nogi pocięto na kwintyle na dni 10-30..11-04 (dev). Te same
  granice odczytano na 11-05..11-10 (hold-out). Sprawdzone cechy:
  - pewność minus 1/kurs;
  - trafność własnej próbki minus 1/kurs;
  - model minus 1/kurs;
  - marża rynku;
  - liczebność próbki;
  - kurs;
  - `price_gap`;
  - `rating_market_gap`;
  - gwiazdka ★;
  - `line_offset`.
- W obu połowach to samo dały trzy cechy: marża rynku, pewność minus 1/kurs
  i liczebność próbki. Progi to granice kwintyli z dev, zamrożone:
  - marża < 8,6%;
  - pewność najwyżej 4,7 pp pod 1/kurs;
  - próbka ≥ 20.
- Reszta niczego nie rozróżnia. Gwiazdka, `price_gap`, `rating_market_gap`,
  sam kurs i `line_offset` przy tej samej cenie dają to samo.

## Wynik

| grupa | dev 10-30..11-04 | hold-out 11-05..11-10 |
|---|---|---|
| wszystkie nogi | −5,4% [−6,1; −4,7], n 32 943 | −5,1% [−6,0; −4,3], n 31 603 |
| mniej złe (oba stopnie) | −3,2% [−5,9; −0,4], n 1 569 / 628 meczów | −1,7% [−4,6; +1,0], n 1 579 / 580 |
| mniej złe, pewność < 0,85 | −4,1% [−7,1; −1,1] | −2,4% [−5,6; +0,9] |
| mniej złe, pewność 0,80-0,85 | −2,1% [−6,1; +1,9], weszło 83,6% | −0,4% [−5,1; +3,6], weszło 84,7% |
| **PEWNE mniej złe (pewność ≥ 0,85)** | **+0,6% [−3,2; +4,2], weszło 90,1%**, n 312 / 237 | **+0,6% [−3,1; +3,9], weszło 90,4%**, n 332 / 231 |
| nieoznaczone | −5,5% | −5,3% |

## Zastrzeżenia

- Trzy cechy wybrano z dziesięciu. Próg 0,85 stopnia „pewna" ustalono po
  obejrzeniu obu połówek (na prośbę operatora o stabilność). Uczciwy werdykt
  da dopiero `T-LESSER-LOSS-flag` na dniach od 11-12.
- Po podatku 12% żaden koszyk nie jest na plusie. „PEWNE" przy +0,6% przed
  podatkiem to około −11% po nim. Znacznik mówi „traci mniej" i „wchodzi
  częściej", nigdy „ma przewagę".
- Noga jednostronna (bez marży) nie jest oznaczana nigdy.
