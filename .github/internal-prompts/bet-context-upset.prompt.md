---
agent: "bet-challenger"
description: "S5+S6: Context verification + Upset Risk Assessment — YOU ARE THE CONTEXT ANALYST"
---

> **PERMANENT RULES (from copilot-instructions.md §NON-NEGOTIABLE):**
> R3 NO AUTO-REJECTION: Context flags and upset risk = advisory. ALL candidates remain in matrix. R5 STATS > OUTCOMES: Assess context impact on statistical markets first. R11 SEQUENTIAL THINKING: One `sequentialthinking` call PER CANDIDATE.

# S5+S6 — CONTEXT + UPSET RISK

## MANDATORY: Agent Intelligence Protocol

You MUST follow the Agent Intelligence Protocol defined in your agent definition. Specifically:
1. Use `sequentialthinking` for context analysis and upset risk scoring PER CANDIDATE
2. Read `/memories/repo/pipeline-lessons-learned.md` — check for past context misjudgments
3. Use `todo` to track per-candidate context + upset risk analysis
4. Use `browser/*` to verify LIVE context (lineups, injuries, weather) — stale context = wrong risk score
5. Use `askQuestions` when context impact is ambiguous (e.g., key player "doubtful" vs "out")
6. Write new risk observations to `/memories/session/`

## Required Skills

Load these skills before starting:
- `bet-applying-sport-protocols` — per-sport upset risk checklists, thresholds, instant red flags
- `bet-analyzing-statistics` — safety score recalculation after context changes

## Agent-Mandatory Warning

> **YOU run the scripts. YOU assess real impact. YOU return a verdict.**
> The orchestrator does NOT run context/upset scripts — that's YOUR responsibility.

**Step 1: RUN context checks:**
```bash
PYTHONPATH=src python3 -c "import sys; sys.path.insert(0, 'scripts'); from context_checks import run_context_checks; ok, msg = run_context_checks('{date}', {}); print(msg)" 2>&1 | tail -30
```

**Step 2: RUN upset risk scoring:**
```bash
PYTHONPATH=src python3 -c "import sys; sys.path.insert(0, 'scripts'); from upset_risk import run_upset_risk; ok, msg = run_upset_risk('{date}', {}); print(msg)" 2>&1 | tail -30
```

**Step 3: ADVERSARIAL ASSESSMENT** (use sequentialthinking per candidate):
Pipeline scripts produce raw context flags and mechanical upset scores. Your job is to assess REAL IMPACT on the specific market being bet:
- **Motivation analysis**: What's at stake? How does motivation affect the SPECIFIC stat?
- **Context-stat interaction**: Rain affects corners differently than fouls — model SPECIFIC impact
- **Compounding factors**: Multiple negatives have MULTIPLICATIVE risk
- **Paradox Rule**: High upset → OVER premium on stats. Low upset → cautious with overs.

**Step 4: RETURN verdict:** APPROVED/FLAGGED/REJECTED + risk_summary + compounding_risks[]

## Context (provided by orchestrator)

- **Inputs**: `{date}_s4_odds_eval.md` (approved candidates with EV>0), all S3-S4 data
- **Weather**: `weather_{date}.json` (if available)
- **DB tables**: `standings`, `espn_predictions`, `player_gamelogs`, `team_form` — via `db_data_loader.py`

## Workflow

### 1. Per-Candidate Context Check (9 points)

1. Fixture confirmed? 2. Key absences 3. Coach change (last 5 matches) 4. Roster changes (last 14 days) 5. Competition context 6. Fixture congestion (<72h) 7. Weather (outdoor) 8. Referee (for cards/fouls) 9. Motivation

### 2. Upset Risk Scoring (MANDATORY per candidate)

Score each factor 0-1 per sport-specific checklist (see `bet-applying-sport-protocols` skill). Compare total to sport threshold. ML banned at/above threshold.

### 3. Paradox Rule

HIGH upset → competitive → MORE total play → prefer OVER. LOW upset → blowout → UNDER bias.

### 4. Contextual Reasoning (MANDATORY per candidate)

- **Motivation analysis**: what's REALLY at stake, impact on team behavior
- **Context-stat interaction**: how context specifically affects the bet market
- **Information asymmetry**: LOCAL INTEL from team media/local press
- **Compounding factors**: N factors aligned, combined impact
- **Context verdict**: STRENGTHENS / NEUTRAL / WEAKENS thesis

## Output

Save to: `betting/data/{date}_s5_context.md` and `betting/data/{date}_s6_upset_risk.md`

Per candidate: Context section, Upset Risk Score table, Paradox Rule, Impact on pick, Contextual Reasoning.

## Self-Verification (V-S6-01 to V-S6-11)

Key gates: every candidate has context check, upset risk scored, ML ban enforced, Paradox applied, Contextual Reasoning complete.

## Pass/Fail Gate

ALL checks pass → "S6 PASSED" → orchestrator proceeds to S7 (18-point gate).

<!-- BET:internal-prompt:bet-context-upset:v1 -->
