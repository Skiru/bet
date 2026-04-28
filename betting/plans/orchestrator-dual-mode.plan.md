# Orchestrator Dual-Mode Operation — Implementation Plan

## Task Details

| Field            | Value                                                                                         |
| ---------------- | --------------------------------------------------------------------------------------------- |
| Jira ID          | N/A                                                                                           |
| Title            | Enhance bet-orchestrator for dual-mode operation (pipeline + ad-hoc question routing)         |
| Description      | Add intent classification, knowledge domain routing, and ad-hoc question delegation to the orchestrator agent so it serves as the single entry point for all betting interactions |
| Priority         | High                                                                                          |
| Related Research | N/A                                                                                           |

## Proposed Solution

Extend `bet-orchestrator.agent.md` with four new behavioral sections that enable it to classify incoming user messages into one of four intents (PIPELINE, QUESTION, ACTION, STATUS) and route accordingly:

- **PIPELINE** → existing S0→S8 4-pass flow (unchanged)
- **QUESTION** → delegate to the specialist agent that owns the knowledge domain, passing context files and session state
- **ACTION** → delegate to the specialist agent with explicit action instructions
- **STATUS** → orchestrator answers directly by reading artifacts (no delegation)

A new prompt file `ask-betting.prompt.md` provides the entry point for question/action/status interactions, complementing the existing `orchestrate-betting-day.prompt.md` for pipeline interactions.

```
┌─────────────────────────────────────────────────────┐
│                  USER MESSAGE                       │
│        (via /bet-orchestrator or prompt)             │
└──────────────────────┬──────────────────────────────┘
                       │
              ┌────────▼────────┐
              │ INTENT CLASSIFY │ (sequential-thinking for ambiguous)
              └────────┬────────┘
                       │
       ┌───────────────┼───────────────┬──────────────┐
       │               │               │              │
  ┌────▼────┐   ┌──────▼──────┐  ┌─────▼─────┐  ┌────▼─────┐
  │PIPELINE │   │  QUESTION   │  │  ACTION   │  │  STATUS  │
  │(existing)│   │  route to   │  │ route to  │  │ answer   │
  │S0→S8    │   │  specialist │  │ specialist│  │ directly │
  └─────────┘   │  + context  │  │ + action  │  └──────────┘
                └─────────────┘  └───────────┘
```

The design adds **no changes** to existing pipeline logic. All new sections are additive. The existing `<agent-role>`, `<collaboration>`, and `<constraints>` sections receive targeted additions that don't alter current behavior.

## Current Implementation Analysis

### Already Implemented

- `bet-orchestrator.agent.md` — `.github/agents/bet-orchestrator.agent.md` — Full S0→S8 pipeline orchestration with 4-pass protocol, gate conditions, delegation map, error escalation
- `orchestrate-betting-day.prompt.md` — `.github/prompts/orchestrate-betting-day.prompt.md` — Pipeline entry point prompt with session parameters
- All 7 specialist agents — `.github/agents/bet-{settler,scanner,statistician,scout,valuator,challenger,builder}.agent.md` — Domain expertise, already listed in orchestrator's `agents:` frontmatter
- Pipeline step prompts — `.github/prompts/s{0-8}*.prompt.md` — Per-step prompts for pipeline execution
- Session state artifacts — `betting/data/YYYYMMDD_s{N}_*.md` — Pipeline step outputs used for state discovery
- Coupon artifacts — `betting/coupons/YYYY-MM-DD*.md` — Version tracking source
- Ledger files — `betting/data/picks-ledger.csv`, `betting/data/coupons-ledger.csv` — Settlement and history data

### To Be Modified

- `bet-orchestrator.agent.md` — `.github/agents/bet-orchestrator.agent.md` — Add intent classification, domain map, session state discovery, ad-hoc delegation template, multi-domain triage, update collaboration and constraints sections

### To Be Created

- `ask-betting.prompt.md` — `.github/prompts/ask-betting.prompt.md` — Question-mode entry point prompt

## Open Questions

| #   | Question                                                                 | Answer                                                    | Status       |
| --- | ------------------------------------------------------------------------ | --------------------------------------------------------- | ------------ |
| 1   | Should the orchestrator log ad-hoc questions to a journal file?          | Out of scope for this plan — can be added later           | ✅ Resolved  |
| 2   | Should the ask-betting prompt accept a `domain` hint parameter?          | No — let the orchestrator classify automatically          | ✅ Resolved  |
| 3   | Can existing specialist agents handle ad-hoc questions without changes?  | Yes — they already have read tools and domain knowledge   | ✅ Resolved  |

## Implementation Plan

### Phase 1: Orchestrator Agent Enhancement

All tasks in this phase modify `.github/agents/bet-orchestrator.agent.md`. Execute sequentially — each task adds or modifies a specific section of the file.

#### Task 1.1 — [MODIFY] Update YAML Frontmatter

**Description**: Update the `description` field to reflect dual-mode capability. Add `argument-hint` examples for both modes.

**Changes**:
```yaml
# FROM:
description: "Orchestrates the daily betting pipeline — delegates S0-S8 steps to specialized agents, manages 4-pass error correction, enforces gate conditions between steps, handles session types and rerun versioning."
argument-hint: "run_date=2026-04-27 session=full"

# TO:
description: "Single entry point for all betting interactions — orchestrates the S0-S8 daily pipeline AND routes ad-hoc questions, actions, and status queries to the correct specialist agent."
argument-hint: 'Pipeline: "run_date=2026-04-28 session=full" | Question: "why did pick X fail the gate?"'
```

**Definition of Done**:
- [ ] `description` mentions both pipeline orchestration and question routing
- [ ] `argument-hint` shows examples of both pipeline and question usage
- [ ] No changes to `tools`, `agents`, or `model` fields

---

#### Task 1.2 — [MODIFY] Extend `<agent-role>` Section

**Description**: Add question routing to the orchestrator's responsibilities list and approach description. Insert after the existing bullet list items, before `<approach>`.

**Changes**: Add these bullet points to the "You focus on areas covering" list:
```markdown
- Classifying user intent (PIPELINE / QUESTION / ACTION / STATUS) before taking any action
- Routing ad-hoc questions to the specialist agent that owns the relevant knowledge domain
- Discovering current session state (date, version, pipeline progress) before delegating
- Synthesizing multi-domain answers when a question spans multiple specialist areas
```

Add to `<approach>` after the existing "Session Parity Rule" paragraph:
```markdown
**Dual-Mode Rule:** When invoked via `ask-betting` prompt or with a question/action/status message, classify intent FIRST. Only enter pipeline mode when intent is explicitly PIPELINE. Default to QUESTION for interrogative messages.
```

**Definition of Done**:
- [ ] Responsibility list includes intent classification, question routing, state discovery, multi-domain synthesis
- [ ] `<approach>` contains the Dual-Mode Rule
- [ ] Existing pipeline responsibilities unchanged
- [ ] Existing Session Parity Rule, pipeline sequence, and 4-Pass Protocol unchanged

---

#### Task 1.3 — [MODIFY] Add `<intent-classification>` Section

**Description**: Insert a new `<intent-classification>` section immediately after `</agent-role>` and before `<skills-usage>`. This section defines the four intent types, their triggers, and classification behavior.

**Content to insert**:
```markdown
<intent-classification>

## Intent Classification Protocol

Classify EVERY incoming message before taking action. Use `sequential-thinking` for ambiguous messages.

| Intent   | Trigger Patterns                                                                 | Behavior                                              |
|----------|---------------------------------------------------------------------------------|-------------------------------------------------------|
| PIPELINE | Via `orchestrate-betting-day` prompt; "run session"; "start pipeline"; "execute S0-S8"; "run full/day/night" | Enter existing 4-pass pipeline                        |
| QUESTION | Interrogative form ("why", "what", "how", "which", "show me", "explain", "tell me", "compare") | Route to specialist via knowledge domain map          |
| ACTION   | Imperative + domain verb ("re-evaluate X", "rebuild coupon", "recalculate EV", "update stats", "re-run gate") | Route to specialist with action context               |
| STATUS   | State queries ("current bankroll", "pipeline progress", "how many picks", "what version", "today's session") | Orchestrator answers directly from artifacts          |

### Classification Rules

1. **PIPELINE takes priority** when invoked via `orchestrate-betting-day` prompt — ignore intent classification entirely.
2. **STATUS is self-served** — read artifacts directly, never delegate to a specialist.
3. **Ambiguous messages** → use `sequential-thinking` to analyze keywords against the knowledge domain map. If still ambiguous after analysis, ask the user with `vscode/askQuestions`.
4. **Compound messages** (e.g., "show me the stats and rebuild the coupon") → split into QUESTION + ACTION, handle sequentially.
5. **Default intent** for interrogative sentences = QUESTION. Default for imperative sentences = ACTION.

</intent-classification>
```

**Definition of Done**:
- [ ] `<intent-classification>` section exists between `</agent-role>` and `<skills-usage>`
- [ ] All four intents (PIPELINE, QUESTION, ACTION, STATUS) are defined with triggers and behaviors
- [ ] Classification rules include priority order, ambiguity handling, and compound message splitting
- [ ] PIPELINE priority rule preserves backwards compatibility

---

#### Task 1.4 — [MODIFY] Add `<knowledge-domain-map>` Section

**Description**: Insert a new `<knowledge-domain-map>` section immediately after `</intent-classification>` and before `<skills-usage>`. Maps knowledge domains to keywords, primary agents, and context files.

**Content to insert**:
```markdown
<knowledge-domain-map>

## Knowledge Domain Map

Use this map to route QUESTION and ACTION intents to the correct specialist agent. Match user message keywords against the Keywords column. When multiple domains match, use the first match as primary and the second as secondary (see multi-domain triage).

| Domain               | Keywords                                                                                    | Primary Agent      | Context Files                                                               |
|----------------------|--------------------------------------------------------------------------------------------|-------------------|-----------------------------------------------------------------------------|
| Statistics & Markets | stats, H2H, form, market ranking, corners, fouls, cards, shots, safety score, three-way, §3.0, L10, L5 | bet-statistician   | `betting/data/{date}_s3_deep_stats.md`, `betting/data/{date}_s2_shortlist.md` |
| Tipsters & Consensus | tipster, consensus, argument, prediction, ZawodTyper, Meczyki, scout, expert opinion       | bet-scout          | `betting/data/{date}_s4_tipsters.md`, `betting/data/{date}_s1_tipster_prefetch.md` |
| Odds & Pricing       | EV, odds, Kelly, stake, price gap, drift, value, line movement, expected value, Betclic price | bet-valuator       | `betting/data/{date}_s5_odds_ev.md`, `betting/data/odds_api_snapshot.json`   |
| Settlement & History | settle, PnL, bankroll, won, lost, history, hit rate, coupon killer, CLV, drawdown          | bet-settler        | `betting/data/picks-ledger.csv`, `betting/data/coupons-ledger.csv`, `betting/data/betclic_bets_history.json` |
| Events & Sources     | scan, events, matches, sources, BetExplorer, shortlist, excluded, league, fixture, today   | bet-scanner        | `betting/data/{date}_s1_master_events.md`, `betting/data/scan_summary.json`, `betting/data/{date}_s2_shortlist.md` |
| Risk & Challenge     | upset, risk, bear case, red flag, gate, Zero Tolerance, contrarian, 17-point, blocker      | bet-challenger     | `betting/data/{date}_s6_context.md`, `betting/data/{date}_s7_gate.md`       |
| Coupons & Portfolio  | coupon, portfolio, validation, V1-V10, combo, artifact, placement, exposure, concentration  | bet-builder        | `betting/coupons/{date}*.md`, `betting/data/picks-ledger.csv`               |

### File Path Resolution

Replace `{date}` with the current session date in `YYYYMMDD` format (e.g., `20260428`). If the exact file doesn't exist, search for the closest match using `search/fileSearch` with the date prefix.

</knowledge-domain-map>
```

**Definition of Done**:
- [ ] `<knowledge-domain-map>` section exists between `</intent-classification>` and `<skills-usage>`
- [ ] All 7 knowledge domains are mapped (one per specialist agent)
- [ ] Each domain has keywords, primary agent, and at least 2 context file paths
- [ ] File path resolution rule for `{date}` placeholder is documented

---

#### Task 1.5 — [MODIFY] Add `<session-state-discovery>` Section

**Description**: Insert a new `<session-state-discovery>` section immediately after `</knowledge-domain-map>` and before `<skills-usage>`. Defines how the orchestrator discovers current session state before delegating any ad-hoc query.

**Content to insert**:
```markdown
<session-state-discovery>

## Session State Discovery Protocol

Before delegating any QUESTION or ACTION intent, discover the current session state. This provides context to the specialist agent.

### Discovery Steps

1. **CURRENT_DATE**: Derive from the most recent `s{N}` file in `betting/data/` (pattern: `YYYYMMDD_s*`). Fall back to today's calendar date if no artifacts exist.
2. **CURRENT_VERSION**: Parse the highest version number from coupon files in `betting/coupons/` matching the current date (pattern: `{YYYY-MM-DD}*v{N}*`). If no coupons exist for today, version is `v0` (pre-pipeline).
3. **PIPELINE_STATE**: List which `s{N}` artifact files exist for the current date. Report as a set (e.g., `{s0, s1, s2, s3}` = pipeline completed through S3).
4. **LATEST_SETTLEMENT**: Read the last non-empty row from `betting/data/picks-ledger.csv` to determine the last settled date and bankroll.

### State Summary Format

Pass this to every specialist delegation:
```
Session State:
- Date: {CURRENT_DATE}
- Version: {CURRENT_VERSION}  
- Pipeline: {PIPELINE_STATE}
- Last Settlement: {LATEST_SETTLEMENT}
```

### Skip Conditions

- For STATUS queries: discover state, answer directly, do NOT delegate.
- For PIPELINE queries: state discovery is handled by the pipeline preflight (§STEP -1) — do NOT duplicate it here.

</session-state-discovery>
```

**Definition of Done**:
- [ ] `<session-state-discovery>` section exists between `</knowledge-domain-map>` and `<skills-usage>`
- [ ] All four discovery steps are defined (CURRENT_DATE, CURRENT_VERSION, PIPELINE_STATE, LATEST_SETTLEMENT)
- [ ] State summary format is specified
- [ ] Skip conditions preserve pipeline independence

---

#### Task 1.6 — [MODIFY] Add `<adhoc-delegation>` Section

**Description**: Insert a new `<adhoc-delegation>` section immediately after `</session-state-discovery>` and before `<skills-usage>`. Defines the template for delegating questions and actions to specialists.

**Content to insert**:
```markdown
<adhoc-delegation>

## Ad-Hoc Delegation Protocol

When routing a QUESTION or ACTION to a specialist agent:

### Delegation Template

Pass these four elements to the specialist:

1. **User Query** — the user's exact question or action request, unmodified
2. **Context Files** — the files listed in the knowledge domain map for the matched domain, with `{date}` resolved
3. **Session State** — the state summary from session state discovery
4. **Mode Instruction** — explicit instruction to the specialist:
   - For QUESTION: "Answer this question directly using the provided context. Do NOT execute a full pipeline step. Do NOT produce step artifacts."
   - For ACTION: "Execute this specific action using the provided context. Produce only the artifacts directly related to this action. Do NOT execute a full pipeline step."

### Delegation Rules

1. Always resolve context file paths before delegating — verify files exist using `search/fileSearch`
2. If a required context file is missing, inform the user which pipeline step needs to run first
3. The specialist's response is the final answer — the orchestrator forwards it to the user without modification unless multi-domain triage applies
4. Never pass raw user input as terminal commands to specialist agents

</adhoc-delegation>
```

**Definition of Done**:
- [ ] `<adhoc-delegation>` section exists between `</session-state-discovery>` and `<skills-usage>`
- [ ] Delegation template specifies all four elements (query, context files, session state, mode instruction)
- [ ] Mode instructions differentiate QUESTION from ACTION
- [ ] Delegation rules include file existence check, missing context handling, and input safety

---

#### Task 1.7 — [MODIFY] Add `<multi-domain-triage>` Section

**Description**: Insert a new `<multi-domain-triage>` section immediately after `</adhoc-delegation>` and before `<skills-usage>`. Defines how cross-domain questions are handled.

**Content to insert**:
```markdown
<multi-domain-triage>

## Multi-Domain Triage Protocol

When a user question or action spans multiple knowledge domains:

### Triage Steps

1. **Identify domains**: Match user message keywords against all domain rows in the knowledge domain map. Rank by number of keyword matches.
2. **Primary delegation**: Route to the highest-ranking domain's agent for data retrieval and initial answer.
3. **Secondary delegation** (if needed): Route to the second-ranking domain's agent for interpretation, cross-reference, or additional data.
4. **Synthesis**: Orchestrator combines both responses into a unified answer for the user. Resolve contradictions by citing which agent provided which data.

### Constraints

- **Maximum 2 agent calls per question** — if more than 2 domains are relevant, answer from the top 2 and note what was not covered.
- **Sequential, not parallel** — call the primary agent first, then secondary, because the secondary may need the primary's output.
- **No cascading** — a specialist agent must NOT delegate to another specialist. Only the orchestrator routes between agents.

### Example

User: "Why did the Madrid Open tennis pick fail the 17-point gate and what was the EV?"
- Domain 1: Risk & Challenge (gate, 17-point) → bet-challenger (primary)
- Domain 2: Odds & Pricing (EV) → bet-valuator (secondary)
- Orchestrator synthesizes both responses

</multi-domain-triage>
```

**Definition of Done**:
- [ ] `<multi-domain-triage>` section exists between `</adhoc-delegation>` and `<skills-usage>`
- [ ] Triage steps define identification, primary/secondary delegation, and synthesis
- [ ] 2-agent-call cap is explicitly stated
- [ ] Sequential ordering is enforced
- [ ] Example demonstrates a realistic cross-domain scenario

---

#### Task 1.8 — [MODIFY] Update `<collaboration>` Section

**Description**: Add an "Ad-hoc delegation map" table to the existing `<collaboration>` section, after the existing "Error escalation" block.

**Content to append** (inside `<collaboration>`, before `</collaboration>`):
```markdown

**Ad-hoc delegation map:**

| Intent   | Routing                                                                                       |
|----------|-----------------------------------------------------------------------------------------------|
| PIPELINE | Existing delegation map (S0→S8 table above)                                                   |
| QUESTION | Knowledge domain map → primary agent + context files + session state + "answer directly" mode  |
| ACTION   | Knowledge domain map → primary agent + context files + session state + "execute action" mode   |
| STATUS   | Self-served — orchestrator reads artifacts directly, no delegation                             |
| MULTI    | Primary agent first, secondary agent second, orchestrator synthesizes (max 2 agents)           |
```

**Definition of Done**:
- [ ] Ad-hoc delegation map table exists inside `<collaboration>`
- [ ] All five routing types are listed (PIPELINE, QUESTION, ACTION, STATUS, MULTI)
- [ ] Existing pipeline delegation map and error escalation block are unchanged

---

#### Task 1.9 — [MODIFY] Update `<constraints>` Section

**Description**: Add question-mode constraints to the existing `<constraints>` section.

**Content to append** (inside `<constraints>`, before `</constraints>`):
```markdown
- Never classify intent without checking the knowledge domain map first
- Never delegate STATUS queries — answer from artifacts directly
- Never execute more than 2 specialist agent calls for a single ad-hoc question
- Never pass raw user input as terminal commands to specialist agents
- Never let a specialist agent delegate to another specialist — only the orchestrator routes between agents
- Never skip session state discovery before ad-hoc delegation
- Never modify pipeline behavior based on question-mode interactions — the two modes are independent
```

**Definition of Done**:
- [ ] Seven new constraints are present in `<constraints>`
- [ ] Existing five pipeline constraints are unchanged
- [ ] Constraints cover: intent classification, STATUS self-service, 2-agent cap, input safety, no cascading, state discovery, mode independence

---

### Phase 2: Prompt File Creation

#### Task 2.1 — [CREATE] `ask-betting.prompt.md`

**Description**: Create a new prompt file at `.github/prompts/ask-betting.prompt.md` that serves as the entry point for question/action/status interactions with the orchestrator.

**File content**:
```markdown
---
name: ask-betting
description: "Ask any betting question — routes to the right specialist agent via the orchestrator. Use for questions, actions, and status checks."
agent: bet-orchestrator
---

# ASK BETTING

Route this user message to the appropriate specialist agent.

## USER MESSAGE

{{input}}

## INSTRUCTIONS

1. Classify the intent of the user message (QUESTION / ACTION / STATUS).
   - This is NOT a pipeline invocation — do NOT enter S0→S8 mode.
2. Discover current session state (date, version, pipeline progress, last settlement).
3. Match the message against the knowledge domain map.
4. For STATUS: answer directly from artifacts.
5. For QUESTION/ACTION: delegate to the matched specialist agent with context files and session state.
6. For multi-domain messages: follow the multi-domain triage protocol (max 2 agent calls).
7. Return the specialist's answer to the user.
```

**Definition of Done**:
- [ ] File exists at `.github/prompts/ask-betting.prompt.md`
- [ ] YAML frontmatter has `name: ask-betting`, `agent: bet-orchestrator`
- [ ] Instructions explicitly state this is NOT a pipeline invocation
- [ ] All four intents are referenced (QUESTION, ACTION, STATUS, plus multi-domain)
- [ ] `{{input}}` variable captures the user's message

---

### Phase 3: Validation

#### Task 3.1 — [REUSE] Code Review by `tsh-code-reviewer`

**Description**: Run `tsh-code-reviewer` agent via `tsh-review.prompt.md` on the two modified/created files. Verify backwards compatibility, section ordering, completeness of domain map, and constraint consistency.

**Files to review**:
- `.github/agents/bet-orchestrator.agent.md`
- `.github/prompts/ask-betting.prompt.md`

**Definition of Done**:
- [ ] Code review passes or issues are resolved
- [ ] Review confirms pipeline mode is unchanged
- [ ] Review confirms all 7 knowledge domains are mapped
- [ ] Review confirms intent classification covers all trigger patterns from the requirements

---

## Security Considerations

- **Prompt injection via user questions**: The orchestrator must never pass raw user input as terminal commands. The `<adhoc-delegation>` section's Rule 4 and `<constraints>` explicitly forbid this. Specialist agents receive user text as *context for analysis*, never as executable input.
- **No cascading delegation**: Specialist agents must not delegate to other specialists. Only the orchestrator routes between agents. This prevents unbounded delegation chains that could be exploited.
- **File access scope**: Context files are restricted to the `betting/` directory. The domain map uses explicit file path patterns — no user-controlled paths.

## Quality Assurance

Acceptance criteria checklist to verify the implementation meets the defined requirements:

- [ ] Pipeline mode (via `orchestrate-betting-day` prompt) produces identical behavior to before — no regressions
- [ ] All four intents (PIPELINE, QUESTION, ACTION, STATUS) are classified with clear trigger patterns
- [ ] All 7 specialist agents appear in the knowledge domain map with keywords and context files
- [ ] STATUS queries are self-served without specialist delegation
- [ ] QUESTION and ACTION queries delegate to exactly one specialist (or two for multi-domain)
- [ ] Multi-domain triage caps at 2 agent calls per question
- [ ] Session state discovery runs before every ad-hoc delegation
- [ ] Sequential-thinking is used for ambiguous intent classification
- [ ] `ask-betting.prompt.md` routes to `bet-orchestrator` agent
- [ ] No existing pipeline sections (`<collaboration>` delegation map, `<constraints>`, `<approach>`, 4-Pass Protocol) are removed or altered in meaning

## Improvements (Out of Scope)

Potential improvements identified during planning that are not part of the current task:

- **Question logging**: Log ad-hoc questions and answers to a journal file for learning purposes
- **Domain hint parameter**: Allow users to pass an optional `domain=` parameter to skip auto-classification
- **Conversation memory**: Track multi-turn question sessions for follow-up context
- **Agent health check**: Verify specialist agent availability before delegating
- **Usage analytics**: Track which domains and agents are queried most frequently

## Changelog

| Date       | Change Description                        |
| ---------- | ----------------------------------------- |
| 2026-04-28 | Initial plan created                      |
