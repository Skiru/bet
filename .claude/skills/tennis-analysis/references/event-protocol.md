# Tennis event protocol — the steps, and the report they produce

## Which matches get the full protocol

Every match of your read-set file, and any match you intend to veto. Tennis
is often most of the board: order the queue by the read-set file, never by
price.

## The steps

| # | Step | Where the answer is | What you write |
|---|---|---|---|
| T1 | Format and surface | `02_fixtures.json` `default_period_count` (**the real best-of**; the dossier has none), `ground_type` | "BO3, mączka" — or **"format/nawierzchnia nieznana"**. A null surface empties the sample (`SURFACE_UNKNOWN`), a null format skips the format scope and the rating then reads the match as BO3; a BO5 is not read by the rating. |
| T2 | Both clocks | `kickoff_utc`, `superbet_kickoff_utc`, `kickoff_disagreement_h` | both times and the gap. On ITF a gap of hours is normal and `CONFIRMED`; take the **earlier**. |
| T3 | Order of play | web, two domains | round, court, and whether the match has started `[WEB: domena, publ. <data>, fetched <czas>]`. One domain alone is "unconfirmed". Qualifying is BO3 even at a slam. |
| T4 | Sample, per side | `03_samples.json` → `side_a` / `side_b` / `h2h` | scoped n per side, date range, opponents; the `side_a` / `side_b` split of a total. A thin side is the code's job, never a veto by count; a veto only when the sample does not measure this match, reason `DEFEKT: 03_samples.json <metric> <side> …` |
| T5 | Which estimator priced the row | SKILL.md table; `model_p` vs `forecast_p` | rating-priced (`model_p == forecast_p`, or none on `handicap_games` / `most_games` / per-set handicap): the próbka k/n is the independent check - a disagreement is a note, never a removal. Sample-priced: `n/(n+8)` - at n=10 the sample owns 56% of the centre |
| T6 | Opponent class | the `opponent` names, looked up | the class of the sample's opposition against tonight's opponent |
| T7 | Serve / return | `aces_for`, `double_faults_for`, `serve_points_for` + web hold% | high-hold competitive OVER, breaks-and-three-sets OVER, or one-sided UNDER. Aces ≠ tie-breaks. |
| T8 | Distribution | the observations | min, max, median, **mode**; for `games_won_for` say explicitly where the 12-wall sits relative to the line |
| T9 | Scoreline arithmetic | by hand | the concrete scorelines that settle each rung: `6-3 6-4` = 19; `7-6 6-7 7-6` = 39; a player's games in `6-2 6-3` = 5; a 10-point match tiebreak counts one game in the code (`6-4 3-6 10-7` = 20; Superbet's count unverified - name it at ITF / UTR / team-cup events). **Which rung does the modal scoreline land on?** |
| T10 | Schedule and fatigue | web; `schedule` block in `03_samples.json` | previous match score, date, duration; back-to-back days; a qualifier's extra matches; a recent retirement (retirement / walkover refund: void risk). Known before the price = a note; a WATCH only through a dated consequence since the price (MTO, withdrawal doubt) |
| T10b | Market drivers | `.claude/skills/sofa-analysis-core/references/market-drivers.md` (read before the first match) | per market family the drivers checked and their values (dossier / artifacts / web) - the **Czynniki rynku** paragraph - a note, never a removal |
| T11 | Scenario matrix | the rating's `forecast_p` on the `match_won_for` sheet row (never a price) | favourite pulls away / underdog holds / both first serves work / tie-break or deciding set. Which is modal, which kills the market |
| T12 | Ladder and tail | `04_offer.json` + the sheet + the coupon legs | rung by rung in prose, only the rungs of the legs read: why this rung against the distribution. No rung table. A third set adds 12–15 games — the tail is huge and one-sided. |
| T13 | Price, only the filter | `offered_odds`, x = confidence x odds, `fetched_at_utc` | a condition the code applied, never a reason; a one-sided rung has `market_p` null - say so. |
| T14 | Buy / kill | | strongest fact for, strongest against, which wins |
| T15 | Verdict | | `KEEP / WATCH / NO_BET` + the read entry per leg of the read set + veto entry; a removal only by the SKILL's "Removals" table (`[WEB: …, publ. …]` newer than the price, or a real `DEFEKT: …`) |

## The match section, in Polish

The operator reads it on a phone, folded under the leg. Write it **to be
read**: full Polish sentences, players by full name, every number with its
unit and meaning ("Sinner wygrał 12 lub więcej gemów w 8 z 10 meczów na
hardzie"), technical fields only in **Szczegóły techniczne**, no artifact or
rung tables (the page shows pewność, kurs, x, próbka); ~4,000 characters a
match, a quiet one less.

```markdown
### <Zawodnik A> – <Zawodnik B> — <turniej>, <runda> · sofa:<sofascore_event_id>
**W skrócie:** <2-3 zdania prostym językiem: kto faworytem i czemu, jak mecz się prawdopodobnie ułoży (dwa sety / trzy, tie-breaki), co decyduje o nogach>
**Start:** 2026-09-21 11:00Z (Superbet 11:00Z) · tożsamość potwierdzona · nierozpoczęty o 07:40Z
**Fakty zabójcze (przed siecią):** <wycofanie, uraz, format inny niż linia - 1 linia>
**Kluczowe przed meczem:** <prostym językiem, np. „format: do dwóch wygranych setów, nawierzchnia: twarda, otwarta” [WEB: domena, publ. <data>, fetched <czas>]>

**Czynniki rynku.** <dla każdej rodziny rynku: czynniki z market-drivers.md i ich wartości (serw / return, hold%, klasa rywali); próbka - ile meczów każdego zawodnika, rozkład wokół linii, czy wycenił rating czy próbka; wyniki rozstrzygające czytane szczeble („6-3 6-4 to 19 gemów, 7-6 6-7 7-6 to 39 - najczęstszy wynik ląduje na …”); oczekiwanie w jednostkach rynku wobec linii>
**Kontekst (web).** <kolejność gier, poprzedni mecz, stan zdrowia, warunki; ranking obu i odpoczynek z dossier w 2-3 zdaniach; [WEB: domena, publ. <data>, fetched <czas>] - albo „nic istotnego dla tych nóg”>

**Nogi.**
- <superbet_market: superbet_selection> (<rynek, zawodnik, kierunek>) — KEEP / WATCH / NO_BET: <jedno zdanie>

**Za / Przeciw:** <najmocniejszy argument każdej strony, jedna linia>
**Szczegóły techniczne:** <identity, default_period_count, ground_type, kickoff_disagreement_h, model_p / forecast_p, k/n, calibrated_on, line_offset, notatka (SET_HANDICAP_NEIGHBOURS) - jedna linia>
```

Field names (`default_period_count`, `ground_type`, `model_p` …) only in
**Szczegóły techniczne**; the body is plain Polish. **Nogi** holds one line
per family (market, subject, direction) and every removed leg on its own
line.

A re-read (`prior_analysis`) - the delta section: the same heading; first
body line `**W skrócie:**`, second `[wcześniej: <report>,
<recorded_at_utc>]`; then only what changed, and always a
`**Kontekst (web).**` line ("delta: pełny przegląd <czas>, nic nowego" is
allowed).

## Rules for the section

- State **once** in the day's header that tennis has no source of record — not
  once per match.
- Never present a `FUZZY` tennis identity as confirmed. Names collide.
- When `ground_type` or `default_period_count` is null, say the scope did not
  run. That is a fact about the sample, and it is the single most common way a
  tennis row is quietly wrong.
- On any `games_won_for` row, say where 11.5 sits relative to the wall at 12.
- On every leg, say which estimator priced it (rating or sample).
- A two-UNDER tennis builder is one bet with two prices. Say so.
- What you could not verify goes in the report's **Czego zabrakło**, never silently omitted.
