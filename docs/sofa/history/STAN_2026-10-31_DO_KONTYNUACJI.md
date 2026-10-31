# Stan 2026-10-31 (popołudnie) - do kontynuacji wieczorem

Sesja: operator po przegranych AKO z builderami z 10-30 kazał szukać sposobu
na budowanie kuponów, które zarabiają. Ten plik mówi, co jest zrobione, co
wisi i od czego zacząć.

## Zrobione i zacommitowane (main)

- `5a923e6c` - usunięta "rodzina na plusie" (`family_record`) z całego
  pipeline'u (decyzja operatora). Szansa nogi w kuponie czatowym = pewność;
  noga dowolnego sportu > 1/kurs + `price_gap.GAP` liczona po cenie.
- `d066c424` - `/kupon` jako wariant najmniejszej straty: 2 nogi domyślnie,
  cel ~2, buildery tylko na prośbę, preferencja marży < 8%, w każdym kuponie
  "oczekiwany zwrot po podatku ≈ 0,88 × 0,946^n − 1". Dowody:
  `docs/sofa/evidence/slip_flow_backtest_2026-10-31.md`. Komenda działa od
  nowej sesji.

## Wyniki pomiarów (wszystko po podatku 12%, bez promocji)

| test | wynik na odłożonych 10-27..10-30 |
|---|---|
| Flow kuponów ze statystyk (~133 reguł) | single −16,6%, AKO 2 nogi −19,0%, 3 nogi −30,2%, stary build_slip −31,5% |
| Druga cena bet365 (Sofascore), piłka, 128 komórek | najlepsza reguła −13,8% |
| bet365 w tenisie / hokeju / koszu / siatce + "spóźniony Superbet", 202 komórki | od −15% do −32%; CS2 bez kursów w Sofascore |
| Spójność wewnętrzna Superbetu (rynki pochodne + drabinki), 6 sportów, 201 komórek | Superbet spójny w granicach marży; nic |
| Literatura | każda udokumentowana przewaga = ceny innych bukmacherów / Pinnacle; przy podatku 12% noga potrzebuje p × kurs ≥ 1,136 |

Jedyny ślad: **handicap meczowy w koszykówce**, kurs Superbetu × uczciwa
szansa z otwarcia bet365 > 1. Dev 10-13..10-26 n=68 +10,2% po podatku
[−11,6, +31,5]; odłożone (post hoc) n=24 +20,5% [−16,5, +51,2]. Podejrzenie,
nie przewaga (1 z ~200 komórek, poniżej progu n ≥ 100).

## Test na sucho handicapu w koszykówce - zacommitowany, działa

Zamrożona reguła: kurs Superbetu (ostatnia migawka SHADOW przed startem) ×
uczciwa szansa z otwarcia bet365 (Sofascore, usunięcie marży metodą potęgową)
> 1. Okno na żywo od **2026-11-01**, ocena przy n ≥ 300, sukces = dolna
granica przedziału po podatku > 0, inaczej porzucić. Rejestr:
`T-PAPER-BB-HANDICAP-B365-OPEN`; dokument:
`docs/sofa/evidence/paper_bb_handicap_preregistration_2026-10-31.md`.

- Wyciek z przyszłości usunięty: zakład na żywo liczy się tylko z kursu bet365
  zapisanego przed startem (`--capture --loop`, co 15 min, 3 h przed meczem,
  `runs/sofa/paper/bb_handicap/prestart/<D>/`). Backtest oznaczony
  `post_match_lookahead` i nigdy nie sumowany z oknem na żywo.
- Pętlę zbierania startuje `shadow_daily.py` (od następnej pętli);
  `day_status.py` ma `loop:paper_capture`. Na 2026-10-31 uruchomiona ręcznie,
  pid 66330.
- Rozliczanie: `/sofa-day` krok 1c (`paper_bb_handicap.py --date <D-1> --pending --report`).
- E2E: replay 10-13..10-30 odtwarza backtest co do zakładu (68 / 24);
  bramki: 6262 testy, ruff, mypy, rejestr - zielone.

**Ryzyko do sprawdzenia wieczorem / jutro:** w pierwszym przebiegu (13:15Z)
tylko 2 z 75 meczów miały "Point spread" w Sofascore przed startem (64 tylko
"Full time", 9 bez kursów). Jeśli bet365 nie wystawia linii przed meczem,
większość meczów wypadnie jako `no_b365_prestart` w `ledger.json`, a 300
zakładów zajmie dużo dłużej - albo test okaże się niewykonalny.

## Wieczorem - kolejność

1. `ps -p 66330`; `tail runs/sofa/paper/bb_handicap/prestart/2026-10-31/capture.log`
   - ile meczów ma "Point spread" przed startem (pokrycie).
2. Jutro rano po rozliczeniu: `PYTHONPATH=src:. .venv/bin/python scripts/sofa/paper_bb_handicap.py --date 2026-10-31 --pending --report`
   - liczba zakładów i `no_b365_prestart`.
3. Jeśli pokrycie bliskie zera - decyzja operatora: porzucić test albo
   zmienić źródło linii (nowy identyfikator w rejestrze).

## Otwarte, nie ruszane

- Pętla shadow z 10-30 padła o 17:41Z; późne mecze NBA z nocy 10-30/31 są w
  pliku 10-31 i rozliczy je poranny krok pętli 10-31 (działa, pid 3082).
  Jeśli nie: `settle_shadow.py --date 2026-10-31 --kickoff-before 2026-10-31T05:00:00Z`.
- Tabela Superbonusu AKO - operator jej nie ma; liczymy bez promocji.

## Gdzie są dane z badań

`data/research_2026-10-31/` (poza gitem, 180 MB): `flow/` (backtest kuponów),
`secondprice/` i `secondprice2/` (kursy bet365 z Sofascore, 10-13..10-30, wszystkie
sporty, skrypty i raporty), `coherence/` (spójność Superbetu, bez dużych jsonl),
`paperbb/` (offline replay testu na sucho). Pamięć:
`slip-flow-and-second-price-2026-10-31`, `no-family-on-plus-2026-10-31`.
