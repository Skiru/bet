---
name: step4-tipster-dive
description: "STEP 4: Deep tipster argument extraction for each candidate. ≥2 argument sites per candidate. Outputs to betting/data/{date}_tipster_dive.md"
agent: bet-analyst
argument-hint: "run_date=2026-04-25 candidates=Arsenal-Newcastle,Liverpool-Palace"
tools:
  - search
  - editFiles
  - memory/*
  - sequentialthinking/*
---

## Inputs
- **run_date** = ${input:run_date:today}
- **candidates** = ${input:candidates} (from step2/step3)

## Task

For EACH candidate, check ≥2 ARGUMENT-BASED tipster sites. Read the FULL WRITTEN ARGUMENT from each tipster — not just their pick. Extract the reasoning.

### Tipster Sites to Check (in order)

#### Polish sites:
1. **ZawodTyper** (zawodtyper.pl) — check "Typy Dnia" section for the match
2. **Typersi** (typersi.pl) — check individual tipster picks for the match
3. **Meczyki** (meczyki.pl/typy-bukmacherskie) — check editorial + user tips

#### International sites:
4. **OLBG** (olbg.com/tips/football or /tips/tennis etc.) — tips with reasoning
5. **PicksWise** (pickswise.com/soccer/predictions/ or /nba/picks/ etc.) — expert analysis
6. **BetIdeas** (betideas.com/tips/football or /tips/btts) — model-based tips
7. **GosuGamers** (gosugamers.net) — esports tips with analysis

#### US Sports:
8. **Covers** (covers.com) — expert picks with reasoning
9. **ScoresAndOdds** (scoresandodds.com) — consensus + line data

### Per-Candidate Protocol

For each candidate event:
1. Search for the match on ≥3 tipster sites (≥2 must have actual tips found)
2. For EACH tip found, extract:
   - **Site name**
   - **Tipster name/handle**
   - **Their specific pick** (market + direction)
   - **Their odds**
   - **Their REASONING** — the actual argument with stats/facts cited. THIS IS THE GOLD.
   - **Accuracy record** if shown (e.g., "Tipster X: 70% accuracy on 30 tips")
3. Calculate **consensus %**: what % of tipsters agree with our market direction?
   - ≥70% agreement → +0.5 confidence boost
   - ≤40% agreement → -1 confidence, investigate why
4. Note any **tipster conflicts**: if a tipster argues AGAINST our direction with specific facts
   - These facts MUST be addressed in the bear case (Step 7)
5. Note any **new angles** discovered from tipster reasoning that weren't in stats

### BLOCKED SITES (do NOT attempt)
- Forebet, FootySupertips, Windrawwin, BettingExpert, Protipster, Oddspedia, SportyTrader, Predictz, Trafiamy, Blogabet, HLTV tips

### Output Format

Save to `betting/data/{run_date}_tipster_dive.md`:

```markdown
# Tipster Deep-Dive — {run_date}

## CANDIDATE: Arsenal vs Newcastle — Corners O9.5

### Tipster 1: ZawodTyper
- Status: NO TIP for this match / TIP FOUND
- Tipster: [name]
- Pick: [market] @ [odds]
- Reasoning: "[exact quote or detailed summary]"
- Stats cited: [list any stats mentioned]

### Tipster 2: Typersi — [tipster_name]
...

### Tipster 3: PicksWise — [expert_name]
...

### CONSENSUS
- Tips found: X/Y sites checked
- Direction agreement: X% support our pick / X% against
- Confidence adjustment: [+0.5 / 0 / -1]
- Key conflict: [tipster X argues... because...]
- New angle discovered: [any insight from tipsters not in our stats]

---
(repeat for each candidate)
```

### Quality Gates
- [ ] ≥2 tipster sites checked per candidate (with actual fetch attempts, not assumed)
- [ ] Every tip has reasoning extracted (not just "Pick: X @ 1.80")
- [ ] Consensus % calculated for each candidate
- [ ] Any conflicts flagged for bear case
- [ ] If 0 tips found for a candidate after checking ≥3 sites → flag as "NO TIPSTER VALIDATION" (confidence -1)
