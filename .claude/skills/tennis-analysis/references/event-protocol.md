# Tennis event protocol — the steps, and the report they produce

## Which matches get the full protocol

1. Every tennis fixture with a `verdict == "VALUE"` row in `05_sheet.json`.
2. Every tennis fixture appearing in `08_confidence.json` — especially as a
   builder. **These are the ones actually staked.**
3. Every fixture you intend to veto.
4. Everything else: one line in *Pozostałe mecze*.

Tennis is usually two thirds of the board, so the triage matters more here than
in football. Order the queue by what is staked, not by surplus.

## The steps

| # | Step | Where the answer is | What you write |
|---|---|---|---|
| T1 | Format and surface | `default_period_count` (**the real best-of**), `ground_type` | "BO3, mączka" — or **"format/nawierzchnia nieznana, zakres próbki nie zadziałał"**. Null here means the scope silently did nothing. |
| T2 | Both clocks | `kickoff_utc`, `superbet_kickoff_utc`, `kickoff_disagreement_h` | both times and the gap. On ITF a gap of hours is normal and `CONFIRMED`; take the **earlier**. |
| T3 | Order of play | web, two domains | round, court, and whether the match has started `[WEB: domain, fetched …]`. One domain alone is "unconfirmed". Qualifying is BO3 even at a slam. |
| T4 | Sample, per side | `03_samples.json` → `side_a` / `side_b` / `h2h` | scoped n per side, date range, opponents. **A side at 0–3 is not a sample. A total with one side at zero is one player's history wearing a match's name.** |
| T5 | Shrinkage share | `n/(n+2)` | at n=10 the sample owns 83% of the centre |
| T6 | Opponent class | the `opponent` names, looked up | the class of the sample's opposition against tonight's opponent |
| T7 | Serve / return | `aces_for`, `double_faults_for`, `serve_points_for` + web hold% | high-hold competitive OVER, breaks-and-three-sets OVER, or one-sided UNDER. Aces ≠ tie-breaks. |
| T8 | Distribution | the observations | min, max, median, **mode**; for `games_won_for` say explicitly where the 12-wall sits relative to the line |
| T9 | Scoreline arithmetic | by hand | the concrete scorelines that settle each rung: `6-3 6-4` = 19; `7-6 6-7 7-6` = 39; a player's games in `6-2 6-3` = 5. **Which rung does the modal scoreline land on?** |
| T10 | Schedule and fatigue | web | previous match score, date, duration; back-to-back days; a qualifier's extra matches; a recent retirement |
| T11 | Scenario matrix | | favourite pulls away / underdog holds / both first serves work / tie-break or deciding set. Which is modal, which kills the market. **No match-odds price exists in the artifacts.** |
| T12 | Ladder and tail | `04_offer.json` + the sheet | every rung with `p_central`, `p_bar`, `offered`, `required`, `surplus`. A third set adds 12–15 games — the tail is huge and one-sided. |
| T13 | Price, last | | and often nothing checks it: a one-sided rung has `market_p` null and `p_bar` is just `p`. Say so. |
| T14 | Buy / kill | | strongest fact for, strongest against, which wins |
| T15 | Verdict | | `KEEP / WATCH / NO BET` + veto entry |

## The match section, in Polish

```markdown
### <Zawodnik A> – <Zawodnik B> — <turniej>, <runda>
**Format:** BO3 (`default_period_count = 3`) · **Nawierzchnia:** hard (`ground_type`)
**Start:** 2026-09-21 11:00Z (Superbet 11:00Z; rozjazd 0.0 h) · **identity:** CONFIRMED
**Weryfikacja:** on order of play `[WEB: itftennis.com, fetched …]` + `[WEB: …]`

**Próbka.** games_total: A n=8 po zakresie (2026-06-02 … 2026-09-14),
B n=10. Wartości A: 17 19 20 20 21 22 23 26 (mediana 20,5, moda 20).
Rywale A: <names, class>. **Udział próbki w centrum:** 10/12 = 83%.

**Serw i return.** <aces, DF, serve points per side; hold% from the web, tagged>

**Arytmetyka wyników.** 6-3 6-4 = 19 · 6-4 7-5 = 22 · 7-6 6-7 7-6 = 39.
Modalny wynik <…> ląduje na szczeblu <…>.

**Drabina.**
| linia | kier. | p_central | p_bar | oferta | próg | nadwyżka | uwagi |
|---|---|---|---|---|---|---|---|

**Za / Przeciw:** FAKT → RACHUNEK → IMPLIKACJA → RYZYKO

**Werdykt:** KEEP / WATCH / NO BET — <one sentence>
```

## Rules for the section

- State **once** in the day's header that tennis has no source of record — not
  once per match.
- Never present a `FUZZY` tennis identity as confirmed. Names collide.
- When `ground_type` or `default_period_count` is null, say the scope did not
  run. That is a fact about the sample, and it is the single most common way a
  tennis row is quietly wrong.
- On any `games_won_for` row, say where 11.5 sits relative to the wall at 12.
- On any confident `games_won_for` row, say that the market has no measured
  calibration bucket above 0.825.
- A two-UNDER tennis builder is one bet with two prices. Say so.
- What you could not verify goes in **NIE PODANO**, never silently omitted.
