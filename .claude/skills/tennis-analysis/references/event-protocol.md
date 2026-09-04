# Tennis event protocol — master matrix, scenario matrix, template, verdict mapping

Method §34's fifteen iterations, §81's master matrix and §82's scenario
matrix, mapped to what this pipeline holds and to the Polish section they
become. Order follows §64 and §113: data integrity → market definition →
surface → format → recent quality-adjusted form → serve/return → distribution
→ opponent quality → fatigue → H2H (decayed) → ranking → price.

## Selection

1. Every tennis fixture with a `VALUE` row in `<date>_superbet_comparison.json`.
2. Every fixture whose rows you intend to VETO or DOWNGRADE.
3. Fixtures with a `LEAN` row priced within 5% of its bar — one paragraph.
4. Everything else — one line in *Pozostałe mecze*.

## The fifteen steps

| # | Step (method §) | Where the answer is | What you write |
|---|---|---|---|
| I1 | Event, surface, competition, stage, format (§34.1, §66, §96) | `event_list.competition` (pin → surface/format), WebFetch order of play ×2 domains | tour, BO3/BO5, surface (pinned/unknown), round, verified time (or "godzina sporna: X vs Y") |
| I2 | Season baseline (§11) | none in artifacts beyond the scoped sample; web season record on surface | one line, tagged, or "brak" |
| I3 | Recent form L10/L5 (§11, §72) | dossier buckets per player: dates, `surface`, `match_level`, `opponent`, values | retained-on-surface n per player; the scorelines behind them (web) |
| I4 | Surface split (§66) | observation `surface`; `sample_excluded.SURFACE_MISMATCH` | fraction of each sample on tonight's surface; whether the competition is pinned |
| I5 | Opponent quality of the sample (§67–§68) | `opponent` names → WebFetch rankings | `LOW / MEDIUM / HIGH` for the sample vs tonight's opponent |
| I6 | Distribution (§15, §16, §88) | `mean/median/mode/min/max/dispersion`, raw values | Q25–Q75, tail, where each rung sits; scoreline arithmetic |
| I7 | Current tournament / form (§25) | web: results in this event | R1/R2 scores, minutes, sets |
| I8 | Fitness / fatigue (§22, §73) | web: previous match duration, date; retirements last 30 d | asymmetry statement; void risk |
| I9 | Serve / return interaction (§18, §84–§86) | `aces_for`, `double_faults_for`, `first_serve_pct`, `break_points_faced` in the dossier + web hold/return/TB on surface | hold support vs break risk; which over-path (high hold or breaks+3 sets) |
| I10 | Scenario matrix A/B/C/D + §82 | book's match odds (`result_market_lines`); when empty, the games-ladder median per player as a proxy | `A faworyt odjeżdża · B underdog trzyma serwis · C oba serwisy działają · D tie-break/decider`, modal scenario, each market's survival |
| I11 | Independent models (§27, §71) | none for tennis (no model, no market signal, no MCP) | say "brak niezależnego modelu; jedyny sygnał to próba" — once |
| I12 | Expert consensus (§29) | `tipster` column / `tipster_signal.json` | agree/oppose/exact, records; a sentence |
| I13 | Exact Superbet line, odds, value (§4, §26, §38, §89) | `row.superbet`, comparison `min_acceptable_odds`, offer `generated_at`, `match_quality` | full ladder table; probability vs value separately |
| I14 | Correlation / contradiction / tail (§40–§42, §76, §91–§93) | the fixture's other rows | shared length mechanism; the killing scoreline; tail both ways |
| I15 | Fresh eyes (§79) | the 15 questions | `KEEP / WATCH / NO BET`, §32 grade, veto entry |

Buy case / kill case (§69) and the data-conflict matrix (§70) between I13 and
I15.

## Master matrix (§81) — fill what you can, mark the rest `n/d`

```
| kategoria                | A | B | przewaga | źródło |
| rekord 2026 na nawierzchni |   |   |          | [WEB]  |
| obecny turniej (wyniki)   |   |   |          | [WEB]  |
| L10 (na nawierzchni, n)   |   |   |          | dossier|
| jakość rywali w próbie    |   |   |          | [WEB]  |
| hold % (nawierzchnia)     |   |   |          | [WEB] lub n/d |
| 1. serwis %               |   |   |          | dossier first_serve_pct |
| asy / mecz (mediana)      |   |   |          | dossier aces_for |
| DF / mecz (mediana)       |   |   |          | dossier double_faults_for |
| BP faced / mecz           |   |   |          | dossier break_points_faced |
| TB częstość               |   |   |          | [WEB] lub n/d |
| 20+ / 22+ / 24+ gemów (%) |   |   |          | dossier total_games bucket |
| 3-set rate                |   |   |          | dossier total_sets bucket |
| zmęczenie / ostatni mecz  |   |   |          | [WEB] |
| H2H (ważone)              |   |   |          | dossier h2h + decay |
```

## Report template (Polish)

```markdown
### === <Gracz A> – <Gracz B> | <WTA/ATP turniej, runda, BO3/BO5, nawierzchnia> | <HH:MM UTC (HH:MM PL)> — <zweryfikowane 2 źródła | godzina sporna> ===

**Weryfikacja:** brak źródła wzorcowego (bzzoiro-tennis 402) — order of play `[WEB: <domena>, fetched <UTC>]`, korroboracja `[WEB: <domena 2>]`
**Kurs meczu Superbet (opinia bukmachera, nie konsensus):** <A x.xx – B y.yy> ⇒ faworyt <kto>, siła <mocny/umiarkowany/wyrównany>. Gdy `result_market_lines` jest puste (zdarza się — nie każdy mecz ma wystawiony zakład na zwycięzcę), odczytaj siłę faworyta z **drabinki gemów**: mediana szczebla, przy którym `over`/`under` się równoważą, dla obu graczy, i powiedz, że to zastępczy odczyt, nie kurs meczu.
**Próba po zawężeniu:** A: <n> na <nawierzchnia> (wykluczono <k> SURFACE_MISMATCH / MATCH_FORMAT_*), rywale: <LOW/MED/HIGH, przykłady> · B: <…> · h2h: <n, daty, wagi>
**Serwis/return:** <hold, 1. serwis %, asy, DF, BP faced — z tagami> ⇒ <profil meczu: wysokie holdy / przełamania / jednostronny>
**Ostatni mecz / zmęczenie:** A: <wynik, data, czas> · B: <…> · ryzyko krecza: <tak/nie, dlaczego>
**Macierz §81:** <skrót: kto ma przewagę w ilu kategoriach, gdzie konflikt>

#### <rynek> <linia> <kierunek> — <werdykt §32>
FACT: <n, trafienia, rozkład, centre_note (own+own), estymand>
CALCULATION: <p_low, p_central, shrunk_mean vs mean; wyniki setowe, które rozliczają szczebel>
IMPLICATION: <co to mówi o tym meczu>
RISK: <scenariusz zabijający; ogon; krecz>
SCENARIO ROBUSTNESS: A <…> · B <…> · C <…> · D <…> · modalny: <…, np. 6-3 6-4 = 19>
Drabinka Superbetu:
| szczebel | p_low | p_central | traf. | próg | Superbet | ocena |
BUY CASE: <…>
KILL CASE: <…>
→ **<KEEP | WATCH | NO BET>** · probability = <…> · value = <…> · <VETO/DOWNGRADE + reason_class>

**Pozostałe wiersze tego meczu:** <jedna linia każdy>
```

## Verdict → action mapping

| Finding | Verdict | Veto entry |
|---|---|---|
| match not on today's order of play at that time (two domains) / walkover / withdrawal | NO BET | `VETO`, line null, direction null, `OTHER` |
| total's split shows one side with 0 scoped observations; `total_sets` pooled centre leading the sheet | NO BET | `DOWNGRADE`, line null, `ESTIMAND_WRONG` |
| sample opposition class ≠ tonight's opponent (games_won, aces_for) | NO BET / WATCH | `DOWNGRADE`, line null, `ESTIMAND_WRONG` (or `SAMPLE_NOT_REPRESENTATIVE` when the issue is level/surface mix) |
| competition unpinned and the sample is mixed-surface; ≤3 retained on surface for a side | WATCH | `DOWNGRADE`, line null, `SAMPLE_NOT_REPRESENTATIVE` |
| format gate evidently inert (BO3 tautology under BO5 prices) | NO BET | `VETO`, line null, direction null, `OTHER`, and report the gate failure |
| providers disagree on a match on the rung | WATCH | `DOWNGRADE`, `DATA_CONFLICT` |
| rung on the sample's mode / modal scoreline lands on it, other rungs sound | WATCH on that rung | `DOWNGRADE`, **that line**, `LINE_ON_MODE` |
| fatigue asymmetry / retirement risk / old H2H conflicting with surface form | WATCH | `DOWNGRADE`, line null, `OTHER` |
| price below bar, sample sound | WATCH, name the price | none |
| everything holds, price clears | KEEP (`MEDIUM`/`VALUE` — tennis has no `CALL`, so `HIGH` needs a specific justification) | none |

## Fresh-eyes questions (§79), one line each for every KEEP

1 strongest fact for · 2 strongest fact against · 3 what changed my mind ·
4 what is stale · 5 what is correlated · 6 which scoreline kills it · 7 safest
rung · 8 best-value rung · 9 still a bet ignoring the odds? · 10 ignoring
H2H? · 11 ignoring ranking? · 12 independently supported (no — say what that
costs)? · 13 Superbet posts it, at this rung, `OFFERED`? · 14 what would make
me reject it now? · 15 KEEP / WATCH / NO BET.
