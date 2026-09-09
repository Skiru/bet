# Football event protocol — the fifteen steps and the report they produce

Method §34 prescribes fifteen iterations per top event. This maps each to the
artifact or tool that answers it here, and to the Polish section it becomes.
Steps are ordered by the evidence hierarchy (§64); a hard fail early ends the
analysis with `NO BET` and no later step may reopen it.

## Selection: which fixtures get the full protocol

1. Every fixture with at least one `VALUE` row in
   `<date>_superbet_comparison.json` (your sport).
2. Every fixture whose rows you intend to VETO or DOWNGRADE.
3. Fixtures with a `CALL` row priced within 5% of its bar (a refreshed offer
   may put them over) — one paragraph, not the full protocol.
4. Everything else: one line in *Pozostałe mecze*.

## The fifteen steps

| # | Step (method §) | Where the answer is | What you write |
|---|---|---|---|
| I1 | Event, competition, stage (§34.1, §96) | `event_list` (competition, start_time UTC, source_ids) + `get_match_detail` (`status`, `event_date`, `round_name`, `previous_leg_event_id`). Live day: anything but `notstarted` → VETO all lines. Past-day re-read: `finished` is expected, not a veto, and the result is off-limits | one line: "Liga X, kolejka N / Puchar, 1/4 finału, **rewanż**, pierwszy mecz 0-0 (587786)"; `[BZZOIRO-MCP]` tag; kickoff in UTC and Europe/Warsaw |
| I2 | Season baseline (§11) | `season_form` (`xgf/xga/xg_games/position/form`); when it is `[]` (cups have no table; some READY dossiers still arrive empty) fall back to `get_standings(league_id)` for the sides' league rows, tagged; `market_priors` via `shrunk_mean` | both sides' xG per game with `xg_games`; position (group?) |
| I3 | Recent form L10 (§11, §25) | dossier buckets `team_a_l10 / team_b_l10` per metric, `sample_excluded` | retained observations per side after scoping; what was excluded and why |
| I4 | Venue split (§11) | `row.venue`, observation `venue` fields, prior's home/away | sample venue mix vs tonight |
| I5 | Opponent adjustment (§11, §67) | opponent's own `*_for`, `goals_against`, model xG per side (`market_context`) | proxy statement, labelled as proxy; opponent class of the sample's matches (`opponent` field) |
| I6 | Distribution (§15, §16) | `mean/median/mode/min/max/dispersion`; raw values from the dossier | "typowo Q25–Q75, ogon do max; linia względem mody i maksimum"; when `mean ≫ median`, name the observations and opponents that make the gap |
| I7 | Current form / stakes (§25, §22) | `form` string, `get_standings`, `get_team_fixtures` | table stakes, congestion, rotation risk |
| I8 | Squad / lineup / injury / fatigue (§20–§22) | `squad_availability`, `lineup_status`, `get_match_lineups`, `get_team_squad` | per side: count, names that matter, unknown count; props: confirmed vs predicted, expected minutes |
| I9 | Tactical / matchup (§17) | style from the metrics (shots vs SOT ratio, corners vs shots, fouls), manager (`get_manager_detail`) | one paragraph on mechanism: who has the ball, who blocks, who fouls |
| I10 | Game script A/B/C/D (§24) | 1X2 + xG from `market_context` / `compare_odds` / `get_predictions` | `SCENARIO ROBUSTNESS: A … B … C … D …` per market, and which is modal |
| I11 | Independent models (§27, §30, §71) | `market_signal` (corners/goals only), bzzoiro model, `cross_provider_agreement` | how many *independent* signals agree; label DERIVED where they share inputs |
| I12 | Expert consensus (§29) | `tipster` column, `tipster_signal.json`, `tipster_claims.json` | `agree/oppose/exact/considered`, records; a sentence, never a number in the read |
| I13 | Exact Superbet line, odds, value (§4, §26, §38, §89) | `row.superbet` (`availability`, `price`), comparison `min_acceptable_odds`, `generated_at` | ladder table: rung / p_low / p_central / hits / bar / price / verdict; probability quality vs value quality separately |
| I14 | Correlation / contradiction / tail (§16, §39–§42, §76, §91–§93) | the fixture's other rows; `bet_builder_draft.py` output | shared mechanism, the killing scenario, tail both ways; no product |
| I15 | Fresh eyes (§79) | the 15 questions | `KEEP / WATCH / NO BET`, §32 grade, veto entry |

Buy case / kill case (§69) and the data-conflict matrix (§70) sit between I13
and I15: write the single strongest fact each way and say which wins.

## Report template (Polish)

```markdown
### === <Gospodarz> – <Gość> | <liga / puchar, runda, rewanż?> | <HH:MM UTC (HH:MM PL)> ===

**Status:** `notstarted`, `event_date` zgodne z artefaktem `[BZZOIRO-MCP: get_match_detail, fetched <UTC>]`
**Stawka:** <kolejka / runda / rewanż z wynikiem pierwszego meczu / tabela / derby (flaga vs dystans) / zagęszczenie>
**Sędzia:** <nazwisko>, <n> meczów w sezonie: <ż>/mecz, <cz>/mecz, <faule>/mecz (kariera <n>) — <co to znaczy dla linii>; `centre_note` <jeśli kod już wmieszał>
**Kadry:** <A: k/n niedostępnych (kto ważny), nieznanych m> · <B: …> · składy: <confirmed|predicted>
**Forma sezonowa:** <A: xGF/xGA na <xg_games> meczach, poz. <p>, <form>> · <B: …> · <luka gole–xG, jeśli istotna>
**Okoliczności:** <tylko gdy ważą: neutralny teren, przejazd, wiatr, pogoda>
**Rynek 1X2 / xG (odniesienie, nie Superbet):** <fav p, xG a–b, najbardziej prawdopodobny wynik> `[BZZOIRO-ODDS: <ts>]`

#### <rynek> <linia> <kierunek> — <werdykt §32>
FACT: <n, trafienia, podział a/b/h2h, wykluczenia, rozkład Q25–Q75/moda/min/max>
CALCULATION: <p_low, p_central, shrunk_mean vs mean, gdzie linia względem mody i maksimum, estymand>
IMPLICATION: <co to mówi o tym meczu>
RISK: <największy scenariusz przeciw; ogon; korelacja>
SCENARIO ROBUSTNESS: A <…> · B <…> · C <…> · D <…> · modalny: <…>
Drabinka Superbetu:
| szczebel | p_low | p_central | traf. | próg | Superbet | ocena |
BUY CASE: <jeden najsilniejszy fakt za>
KILL CASE: <jeden najsilniejszy fakt przeciw>
→ **<KEEP | WATCH | NO BET>** · probability = <HIGH/MEDIUM/LOW> · value = <HIGH/MEDIUM/LOW/brak> · <VETO/DOWNGRADE + reason_class, jeśli dotyczy>

#### <rynek 2> …

**Pozostałe wiersze tego meczu:** <jedna linia każdy: prawidłowy odczyt, brak zakładu / brak linii / cena>
```

## Verdict → action mapping

| Finding | Verdict | Veto entry |
|---|---|---|
| fixture not `notstarted` / moved / venue switched | NO BET | `VETO`, line null, direction null, `OTHER` |
| the *hits themselves* are not about this fixture: misses are the h2h, one side ≤3 retained, the sample's matches are a different competition or opponent class **and the conditional record disagrees with the pooled one** | NO BET / WATCH | `DOWNGRADE`, line null, `SAMPLE_NOT_REPRESENTATIVE` (zero weight) |
| the median describes the fixture but the *centre/tier* is one step too generous: a few outliers against weak opposition inflate `shrunk_mean`/`p_central`, `RUNG_SEPARATED_BY_MODEL` carrying the price | WATCH | `DOWNGRADE`, line null, `OTHER` (one tier step) |
| market settles a different quantity than the sample (yellows vs points, pooled vs own) | NO BET | `DOWNGRADE`, line null, `ESTIMAND_WRONG` |
| `DISAGREE` and the disagreement is on the rung | WATCH | `DOWNGRADE`, line null (or the rung), `DATA_CONFLICT` |
| card row, no referee, league spread ≥ a card | WATCH | `DOWNGRADE`, line null, direction null, `MISSING_REFEREE` |
| this rung sits on the mode / sample has crossed it twice, other rungs fine | WATCH on that rung | `DOWNGRADE`, **that line**, `LINE_ON_MODE` |
| stakes/derby/second-leg argument the code's flags missed | WATCH | `DOWNGRADE`, line null, `OTHER`, say the flag that did not fire |
| price below bar, sample fine | WATCH (state the price that would make it) | none |
| everything holds, price clears | KEEP (`HIGH`/`MEDIUM`/`VALUE` per §32) | none |

## Fresh-eyes questions (§79), answered in one line each for every KEEP

1 strongest fact for · 2 strongest fact against · 3 what changed my mind ·
4 what is stale · 5 what is correlated · 6 what kills the builder · 7 safest
rung · 8 best-value rung · 9 still a bet ignoring the odds? · 10 ignoring h2h?
· 11 ignoring the table? · 12 independently supported? · 13 Superbet posts it?
· 14 what would make me reject it now? · 15 KEEP / WATCH / NO BET.
