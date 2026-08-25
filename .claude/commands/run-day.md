---
description: Run a betting day end to end and write the per-match analysis to runs/<date>/<date>_analiza.md, sorted by confidence.
argument-hint: dzisiaj | jutro | YYYY-MM-DD
---

Run one betting day and write the analysis to a file. The user passes only the
day.

## Resolve the day first

`$ARGUMENTS` is one of `dzisiaj` / `today`, `jutro` / `tomorrow`, or an explicit
`YYYY-MM-DD`. Empty means today. Resolve it in **UTC**, because the pipeline's
betting day is UTC:

```bash
date -u +%F                        # dzisiaj
date -u -v+1d +%F                  # jutro (macOS)
```

State the resolved date before doing anything else. If the user passed something
you cannot parse, ask — do not guess a day and spend quota on it.

Two things to say out loud when the day is tomorrow: provider quotas reset at
midnight UTC, so a tomorrow-run spends **today's** remaining budget; and
discovery for tomorrow is usually thinner than for today, because fewer fixtures
are published.

## 1. Run it — agent `bet-simple`

Preflight first, quote the advice line, then the run. Never `--skip-preflight`.

```bash
python3 scripts/simple/run_pipeline.py --preflight
python3 scripts/simple/run_pipeline.py --date <resolved> -v [--max-events N]
```

`TIPSTERS` runs between ENRICH and ANALYZE and fills the *Typerzy* column. It is
optional and excluded from the run verdict, so a `tipsters: FAILED` or `PARTIAL`
in `step_verdicts` is not a reason to stop — report it in *Czego zabrakło* and
carry on. Pass `--skip-tipsters` to omit the column entirely.

Take `--max-events` from preflight's `recommended_max_events`. Raise it above
that only with a stated reason — and say plainly that events beyond the
recommendation cannot be corroborated, so they will come back `SINGLE_SOURCE`.
One reason that recurs: when `confirmed_identity_events` is 0 the cap sorts by
kickoff, so fixtures that have already started can eat the budget.

If the verdict is `PRECONDITION_FAILED` or `FAILED`, stop. Report what a human
must change and write no file — an analysis file with no analysis in it is worse
than its absence.

## 2. Analyse it — agent `bet-analyst`

Standard obligations from the agent definition: cross-check the DB for other
`run_id`s on that date, print the per-side `a/b/h2h` split for every row, probe
before claiming DB depth, verify with WebFetch that each fixture is still on.

## 3. Write `runs/<date>/<date>_analiza.md`

**You write this file, not the analyst.** `bet-analyst` is read-only by
construction -- it has no Write tool, because an agent that can rewrite the
artifacts it is judging can quietly launder a bad day into a good one. It returns
the markdown body; you save it.

Polish, because the operator reads it. Overwrite if it exists; the artifacts it
describes were overwritten too.

**Confidence % is `p_low` x 100** — the Wilson lower bound at 95% on
`hits`/`sample_size`, never the raw `hit_rate`. It is the sort key for the whole
file, descending.

Do not compute it yourself: it is a field on every `StatsSheetRow`, written by
`wilson_lower_bound()` in `src/bet/simple_stats/analyze.py`, and it is already
the order the artifact's rows arrive in. Read `row.p_low` and multiply by 100.

It penalises thin samples on its own, which is why nothing is sorted on
`hit_rate`: 4/4 is a hit rate of 1.00 but a `p_low` of 0.51, and 9/12 is 0.75
but 0.47. Those are the real figures at z=1.96 — three misses cost the
twelve-match sample more than eight extra observations earn it, so **4/4 ranks
above 9/12**. An earlier version of this file claimed 9/12 landed at 58% and
outranked 4/4; that was arithmetically wrong in both the number and the
ordering. If the ranking ever looks wrong to you, check `p_low` against the
function, not against this paragraph.

`sample_size` counts only observations that settle: a value sitting exactly on
the line is a push, reported in `row.pushes` and excluded from both `hits` and
`sample_size`, because it resolves neither side of that line.

````markdown
# Analiza <data>

**Run:** `<run_id>` · **Werdykt:** `<OK|PARTIAL>` · **Wygenerowano:** <UTC>
**Pokrycie:** <n> odkrytych → <n> wzbogaconych → <n> odciętych limitem
**Providerzy:** <ci, którzy realnie dali dane> · **Niedostępni:** <nazwa (kind)>

> Sortowanie po kolumnie *Pewność* — to dolna granica Wilsona 95%, nie surowy
> hit rate. `sample_size` łączy obie drużyny i h2h, więc obserwacje nie są
> niezależne i ta liczba jest optymistyczną podłogą, nie gwarancją.

## Ranking

| # | Pewność | Mecz | Rynek | Strona | Surowo | n | a/b/h2h | Zgodność | Typerzy | Min. kurs | Tier |
|--:|--------:|------|-------|--------|-------:|--:|---------|----------|---------|----------:|------|
| 1 | 51.0% | FC Seoul – Bucheon | kartki 3.5 | OVER | 4/4 | 4 | 0/4/0 | SINGLE_SOURCE | brak | — | WEAK |
| 2 | 46.8% | Valencia – Betis | rożne 10.5 | UNDER | 9/12 | 12 | 6/6/0 | AGREE | 2/2 | 1.90 | CALL |

`WEAK` nie dostaje minimalnego kursu — próg policzony z czterech obserwacji
udaje precyzję, której tam nie ma.

Kolumna *Typerzy* to `row.tipster` — ilu publicznych typerów obstawiło **ten sam
rynek, tę samą linię i tę samą stronę** (`agree/agree+oppose`), albo `brak`, gdy
żaden. Nie wchodzi do *Pewności* i nie zmienia tieru: typ to opinia, nie próbka,
często wyliczona z tych samych publicznych danych, czasem z afiliacją do
bukmachera. Stoi obok, żebyś sam zdecydował, czy zgodność Cię cieszy, czy
niepokoi. Nigdy nie podawaj jej jako procentu — procent czyta się jak
prawdopodobieństwo.

## Mecze

### <Gospodarz> – <Gość> · <liga> · <HH:MM UTC>
<wiersze tego meczu, mean/median, co mówią surowe obserwacje, luki z data_gaps,
weryfikacja z sieci z tagiem [WEB: domena, data]>

## Sprzeczne (DISAGREE)
<obie wartości, obaj providerzy, bez rozstrzygania>

## Zdanie publiczności (inny rynek)
<tylko gdy typerzy pokryli mecze z rankingu: `public_lean` z
`<data>_tipster_signal.json`, czyli 1X2/BTTS. Zaznacz wyraźnie, że to inny rynek
niż totale powyżej i że jednego nie przelicza się na drugie. Pomiń sekcję, gdy
krok TIPSTERS nie działał.>

## Czego zabrakło
<jeden konkret, który najbardziej osłabił dzień, i akcja, która to naprawia>

---
Bez kursu, EV i stawki — celowo. Kurs sprawdzasz sam; typ poniżej minimalnego
kursu nie jest typem.
````

## 4. Report back

The file path, the verdict, how many rows landed in each tier, and the single
biggest weakness of the day. Do not paste the whole table into the chat — the
file is the deliverable.

Never invent a number, a fixture or an odds quote. No stake sizing, no placement.
