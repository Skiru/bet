# S3 Enforcement Hardening — Implementation Plan

## Task Details

| Field            | Value                                                                                                  |
| ---------------- | ------------------------------------------------------------------------------------------------------ |
| Title            | Enforce mandatory statistical analysis steps with parseable templates and mechanical verification       |
| Description      | Agents skip §3.0 ranking, §3.0c H2H-stat validation, and three-way cross-check despite rules existing |
| Priority         | Critical — root cause of PSG vs Bayern cards pick failure (2026-04-28)                                 |
| Related Research | PSG vs Bayern Over 4.5 cards approved without ranking table, H2H for alternatives, or output file      |

## Proposed Solution

Replace "mandatory" labels with **mechanically enforceable structures**:

1. **Rigid per-candidate template** with numbered section markers (§S3.1-§S3.10) that the orchestrator counts — missing marker = automatic rejection
2. **Banned words list** ("checked", "verified", "—") — if any appears as sole cell content, structural violation
3. **Numeric validation** — Safety scores, L10/H2H/L5 values must be numbers, not text
4. **Source provenance** — every stat must name the source and exact data point
5. **Multi-market tables for all 14 sports** — no sport can claim "no template available"
6. **Self-verification protocol** in the statistician agent — checks own output before submitting
7. **Analysis Depth Proof** section — forces the agent to quantify its own work

The key insight: an agent can easily write "checked" or skip a section, but it cannot fake a table with 3+ rows of numbers, source URLs, and cross-referenced safety scores without actually doing the analysis.

## Current Implementation Analysis

### Already Implemented

- §3.0 Statistical Market Ranking Protocol — [analysis-methodology.instructions.md](../../.github/instructions/analysis-methodology.instructions.md) — rules exist but not enforced via template
- §3.0b Bettable Statistical Markets table — same file — market lists per sport exist
- §3.0c H2H Market-Specific Validation — same file — rules exist but no structured output format
- Three-Way Cross-Check — same file — rules exist but no parseable template
- §3.1M-§3.5M Multi-Market Tables — [sport-analysis-protocols.instructions.md](../../.github/instructions/sport-analysis-protocols.instructions.md) — Football, Tennis, Basketball, Hockey (partial), Volleyball
- Structural Output Verification after S3 — [orchestrate-betting-day.prompt.md](../../.github/prompts/orchestrate-betting-day.prompt.md) — 7 qualitative checks exist
- 9 mandatory sections in bet-statistician constraints — [bet-statistician.agent.md](../../.github/agents/bet-statistician.agent.md) — listed but no template format

### To Be Modified

- `analysis-methodology.instructions.md` — Add §3.0d data provenance rule, §3.0e per-candidate output template, Zero Tolerance #16, Common Mistakes update
- `sport-analysis-protocols.instructions.md` — Add §3.4M, §3.6M-§3.14M mandatory multi-market tables (10 sports)
- `orchestrate-betting-day.prompt.md` — Replace S3 structural verification with mechanical verification using markers/counts/banned words
- `bet-statistician.agent.md` — Add self-verification protocol, update domain-standards to reference template

### To Be Created

- Nothing — all changes are modifications to existing files

## Open Questions

| #   | Question                                                                             | Answer                                                                                     | Status      |
| --- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------ | ----------- |
| 1   | Should the template be in analysis-methodology or a separate template file?          | In analysis-methodology — single source of truth, loaded by agents via instructions         | ✅ Resolved |
| 2   | Should banned words cause auto-rejection or warning?                                 | Auto-rejection — warnings were already being ignored                                       | ✅ Resolved |
| 3   | Should MMA have 3 markets minimum given limited stat markets?                        | Minimum 3 for all sports. MMA has rounds O/U, method, ITD — exactly 3. Sufficient.         | ✅ Resolved |
| 4   | Should the orchestrator re-read the full S3 file or just count markers?              | Count markers AND scan cells — full mechanical verification. Cost is worth enforcement.     | ✅ Resolved |

## Implementation Plan

### Phase 1: Foundation — Per-Candidate Template + Data Provenance

> **File:** `.github/instructions/analysis-methodology.instructions.md`
> **Dependency:** None — this is the foundation for all other phases.

#### Task 1.1 - [MODIFY] Add §3.0d DATA PROVENANCE rule

**Description:** Insert a new subsection after §3.0c that defines data provenance requirements and banned words. This prevents agents from writing "checked" or "verified" without citing actual sources and numbers.

**Location:** After the §3.0c THREE-WAY CROSS-CHECK block (after the "ALL THREE must support..." line), before the `---` separator that starts STEP 3B.

**Content to add:**

```markdown
### §3.0d DATA PROVENANCE (MANDATORY — NEVER SKIP)

**Every stat cited in S3 output MUST include ALL THREE:**
1. **Source name** — the exact website or tool (e.g., "SoccerStats", "TennisAbstract", "Flashscore H2H tab")
2. **Exact data point** — the specific number with context (e.g., "Liverpool avg 11.2 corners/match at home, L10 games")
3. **Fetch reference** — how the data was obtained (e.g., "web-fetch", "Playwright scan", "Odds-API snapshot")

**BANNED WORDS in S3 table cells** — if ANY of these appear as the SOLE content of a table cell, it is a STRUCTURAL VIOLATION and the candidate is REJECTED:
- "checked", "verified", "confirmed", "good", "fine", "OK", "done", "yes", "—", "N/A", "n/a", "see above"

**Examples:**
- ❌ `| Injury check | checked |` → VIOLATION
- ✅ `| Injury check | No injuries — ESPN injury report, 2026-04-28 08:30 |` → VALID
- ❌ `| H2H avg | good |` → VIOLATION
- ✅ `| H2H avg | 5.8 cards (5 meetings, Flashscore H2H) |` → VALID
- ❌ `| Safety | — |` → VIOLATION
- ✅ `| Safety | 0.70 |` → VALID

**Enforcement:** The orchestrator scans every cell in the S3 output. Banned word as sole content → auto-reject that candidate, return to bet-statistician.
```

**Definition of Done:**

- [ ] §3.0d section exists in analysis-methodology.instructions.md after §3.0c
- [ ] Banned words list contains all 11 words specified
- [ ] Three examples of VIOLATION and three of VALID are shown
- [ ] Enforcement mechanism references orchestrator scanning

---

#### Task 1.2 - [MODIFY] Add §3.0e MANDATORY PER-CANDIDATE OUTPUT TEMPLATE

**Description:** Insert a rigid, parseable template with numbered section markers (§S3.1 through §S3.10) that EVERY candidate in the S3 output file MUST follow. The markers enable mechanical counting by the orchestrator.

**Location:** Immediately after the new §3.0d section, before STEP 3B.

**Content to add:**

```markdown
### §3.0e MANDATORY PER-CANDIDATE OUTPUT TEMPLATE

**EVERY candidate in the `{date}_s3_deep_stats.md` file MUST use this exact template.** The section markers (§S3.1-§S3.10) are PARSEABLE — the orchestrator counts them. Missing or empty sections = STRUCTURAL VIOLATION = candidate REJECTED.

```
### ══ CANDIDATE: [Sport] — [TeamA/PlayerA] vs [TeamB/PlayerB] | [Competition] | [Kickoff HH:MM] ══

#### §S3.1 H2H ANALYSIS (MARKET-SPECIFIC)
- Meetings found: [N] (source: [source name], period: [date range])
- H2H results: [list each meeting with date, score, and STAT VALUE for selected market]
  - YYYY-MM-DD: [TeamA] [score] [TeamB] — [stat]: [value]
  - YYYY-MM-DD: [TeamA] [score] [TeamB] — [stat]: [value]
  - (minimum 3 meetings, target 5)
- H2H avg for selected stat: [number]
- H2H-STAT status: ✅ CONFIRMED / ⚠️ H2H-STAT-BLIND (reason: [where looked, why unavailable])

#### §S3.2 FORM & STATS TABLE
[Sport-specific stats table from §3.1-§3.14 — ALL columns filled, split Home/Away]
[Every cell must contain a number or specific text — no "checked" or "—"]

#### §S3.3 STATISTICAL MARKET RANKING (§3.0)
| # | Market           | TeamA avg | TeamB avg | H2H avg | Line  | Hit L10 | Hit H2H | Safety | Source           |
|---|------------------|-----------|-----------|---------|-------|---------|---------|--------|------------------|
| 1 | [market name]    | [number]  | [number]  | [number]| [X.5] | [X/10]  | [X/5]   | [0.XX] | [source name]    |
| 2 | [market name]    | [number]  | [number]  | [number]| [X.5] | [X/10]  | [X/5]   | [0.XX] | [source name]    |
| 3 | [market name]    | [number]  | [number]  | [number]| [X.5] | [X/10]  | [X/5]   | [0.XX] | [source name]    |
MINIMUM 3 ROWS. For Football, MINIMUM 4 (Fouls + Cards + Corners + Shots).
Safety = min(hit_rate_L10, hit_rate_H2H) as decimal. Higher = better.
SELECTED MARKET: Row [#] — [market name] (highest safety score: [value])

#### §S3.4 THREE-WAY CROSS-CHECK
| Check    | Value    | vs Line [X.5] | Hit Rate  | Direction              |
|----------|----------|----------------|-----------|------------------------|
| L10 avg  | [number] | [over/under]   | [X/10]    | [SUPPORTS / CONFLICTS] |
| H2H avg  | [number] | [over/under]   | [X/5]     | [SUPPORTS / CONFLICTS] |
| L5 trend | [number] | [trend]        | [X/5]     | [UP / DOWN / STABLE]   |
ALIGNMENT: [3/3 SUPPORT ✅ / 2/3 CONFLICT → DOWNGRADE / 3/3 CONFLICT → REJECT]

#### §S3.5 COACH/ROSTER STABILITY
- Coach change in last 5 matches: [YES — name, date, source] / [NO — source: TransferMarkt/Flashscore, checked: YYYY-MM-DD]
- Major roster changes in 14 days: [YES — details, source] / [NO — source: [name], checked: YYYY-MM-DD]
- Stability verdict: [STABLE / VOLATILE — impact on analysis: [1 sentence]]

#### §S3.6 INJURY/SUSPENSION CHECK
| Player         | Status          | Impact on Pick | Source               | Checked At          |
|----------------|-----------------|----------------|----------------------|---------------------|
| [full name]    | [OUT/GTD/PROB]  | [HIGH/MED/LOW] | [source + page]      | [YYYY-MM-DD HH:MM] |
If NO injuries: "No injuries reported — [source name], checked [YYYY-MM-DD HH:MM]"

#### §S3.7 TOP 3 MARKETS (from §S3.3 ranking)
1. **[Market]** — Safety: [0.XX] | L10 hit: [X/10] | H2H hit: [X/5] | Margin: [avg vs line]
2. **[Market]** — Safety: [0.XX] | L10 hit: [X/10] | H2H hit: [X/5] | Margin: [avg vs line]
3. **[Market]** — Safety: [0.XX] | L10 hit: [X/10] | H2H hit: [X/5] | Margin: [avg vs line]

#### §S3.8 RECOMMENDED MARKET
- **Market:** [specific market + line, e.g., "Corners Over 9.5"]
- **Safety score:** [0.XX] (rank [#] of [N] evaluated)
- **Reason:** [2-3 sentences citing specific numbers from §S3.3 and §S3.4 — WHY this market beat alternatives]
- **Key stat:** [The single most important data point supporting this pick]

#### §S3.9 SOURCES USED
| # | Source Name       | Data Collected                    | URL / Access Method          |
|---|-------------------|-----------------------------------|------------------------------|
| 1 | [source name]     | [what was fetched]                | [URL or "Playwright scan"]   |
| 2 | [source name]     | [what was fetched]                | [URL or "Odds-API"]         |
MINIMUM 2 ROWS. Every source that contributed data must be listed.

#### §S3.10 ANALYSIS DEPTH PROOF
| Metric                    | Value                                         |
|---------------------------|-----------------------------------------------|
| Markets evaluated         | [N] markets in §S3.3 ranking table            |
| Sources consulted         | [N] sources ([list names])                    |
| Data points collected     | [N] unique stat values across form + H2H      |
| H2H meetings analyzed     | [N] meetings for [stat], source: [name]       |
| Ranking table completeness| [N] cells filled / [N] total cells = [X]%     |

### ══ END CANDIDATE ══
```

**VALIDATION RULES (for orchestrator):**
1. Every candidate MUST have exactly 10 section markers (§S3.1-§S3.10)
2. §S3.3 MUST have ≥3 data rows (≥4 for football)
3. §S3.4 MUST have 3 data rows (L10, H2H, L5) with numeric values
4. §S3.9 MUST have ≥2 data rows
5. NO cell in ANY table may contain ONLY a banned word (§3.0d)
6. §S3.3 Safety column MUST contain decimal numbers (0.00-1.00)
7. §S3.10 Metrics column MUST contain numbers, not text descriptions
```

**Definition of Done:**

- [ ] §3.0e section exists with complete template showing §S3.1-§S3.10
- [ ] Template shows exact column headers for each table
- [ ] MINIMUM row counts specified for §S3.3 (3, or 4 for football), §S3.4 (3), §S3.9 (2)
- [ ] 7 validation rules listed for orchestrator consumption
- [ ] Template includes CANDIDATE header with sport, teams, competition, kickoff
- [ ] Template includes END CANDIDATE marker for section boundaries
- [ ] §S3.10 ANALYSIS DEPTH PROOF section has 5 metric rows

---

### Phase 2: Sport Coverage — Multi-Market Tables for All 14 Sports

> **File:** `.github/instructions/sport-analysis-protocols.instructions.md`
> **Dependency:** None — independent of Phase 1. Can be done in parallel.

#### Task 2.1 - [MODIFY] Add §3.4M MANDATORY MULTI-MARKET CALCULATION (HOCKEY)

**Description:** Add mandatory multi-market calculation table after the existing §3.4 Hockey section (after the "Context:" line about goalie, B2B, playoffs, trade deadline).

**Content to add:**

```markdown
**§3.4M MANDATORY MULTI-MARKET CALCULATION (HOCKEY):**
Before selecting ANY hockey market, calculate ALL of these:
```
| Market               | TeamA avg | TeamB avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
|----------------------|-----------|-----------|---------|------|---------|---------|--------|
| Period 1 total O/U   |           |           |         |      |         |         |        |
| Game total O/U X.5   |           |           |         |      |         |         |        |
| Shots O/U X.5        |           |           |         |      |         |         |        |
| PP goals O/U 0.5     |           |           |         |      |         |         |        |
| Puck line ±1.5       |           |           |         |      |         |         |        |
```
Pick the market with HIGHEST safety score. **For NHL**: use NaturalStatTrick xG + MoneyPuck. **For other leagues**: use Flashscore + BetExplorer. GOALIE IDENTITY is critical — re-evaluate if goalie changes.
```

**Definition of Done:**

- [ ] §3.4M table exists after §3.4 Hockey section
- [ ] Table has 5 market rows matching §3.0b hockey markets
- [ ] Source guidance for NHL vs other leagues included
- [ ] Goalie dependency noted

---

#### Task 2.2 - [MODIFY] Add §3.6M MANDATORY MULTI-MARKET CALCULATION (ESPORTS)

**Description:** Add mandatory multi-market calculation table after the existing §3.6 Esports section.

**Content to add:**

```markdown
**§3.6M MANDATORY MULTI-MARKET CALCULATION (ESPORTS):**
Before selecting ANY esports market, calculate ALL of these:
```
| Market               | TeamA avg | TeamB avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
|----------------------|-----------|-----------|---------|------|---------|---------|--------|
| Round total O/U X.5  |           |           |         |      |         |         |        |
| Map total O/U 2.5    |           |           |         |      |         |         |        |
| Map HC -1.5/+1.5     |           |           |         |      |         |         |        |
| Kill total O/U X.5   |           |           |         |      |         |         |        |
```
Pick the market with HIGHEST safety score. **Game-specific:** CS2 round totals from HLTV stats. LoL/Dota2 use Liquipedia + GosuGamers for game duration and objective stats. **BO1 = massive variance** — reduce safety score by 0.15 for all markets.
```

**Definition of Done:**

- [ ] §3.6M table exists after §3.6 Esports section
- [ ] Table has 4 market rows matching §3.0b esports markets
- [ ] Game-specific source guidance included
- [ ] BO1 variance penalty noted

---

#### Task 2.3 - [MODIFY] Add §3.7M MANDATORY MULTI-MARKET CALCULATION (SNOOKER)

**Description:** Add mandatory multi-market calculation table after the existing §3.7 Snooker section.

**Content to add:**

```markdown
**§3.7M MANDATORY MULTI-MARKET CALCULATION (SNOOKER):**
Before selecting ANY snooker market, calculate ALL of these:
```
| Market                | P1 avg | P2 avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
|-----------------------|--------|--------|---------|------|---------|---------|--------|
| Frame total O/U X.5   |        |        |         |      |         |         |        |
| Century breaks O/U 0.5|        |        |         |      |         |         |        |
| 50+ breaks O/U X.5    |        |        |         |      |         |         |        |
| Frame HC -X.5/+X.5    |        |        |         |      |         |         |        |
```
Pick the market with HIGHEST safety score. **CueTracker is PRIMARY** for frame stats and break frequency. Format (BO7/BO9/BO11/BO19) dramatically affects frame totals — use format-specific averages, not overall.
```

**Definition of Done:**

- [ ] §3.7M table exists after §3.7 Snooker section
- [ ] Table has 4 market rows matching §3.0b snooker markets
- [ ] CueTracker identified as primary source
- [ ] Format-specific average guidance included

---

#### Task 2.4 - [MODIFY] Add §3.8M MANDATORY MULTI-MARKET CALCULATION (DARTS)

**Description:** Add mandatory multi-market calculation table after the existing §3.8 Darts section.

**Content to add:**

```markdown
**§3.8M MANDATORY MULTI-MARKET CALCULATION (DARTS):**
Before selecting ANY darts market, calculate ALL of these:
```
| Market              | P1 avg | P2 avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
|---------------------|--------|--------|---------|------|---------|---------|--------|
| 180s O/U X.5        |        |        |         |      |         |         |        |
| Total legs O/U X.5  |        |        |         |      |         |         |        |
| Set total O/U X.5   |        |        |         |      |         |         |        |
| Checkout % props    |        |        |         |      |         |         |        |
```
Pick the market with HIGHEST safety score. **DartsOrakel is PRIMARY** for 180s per match and checkout%. Sets vs legs format matters — verify tournament format before calculating. Floor events have higher upset variance.
```

**Definition of Done:**

- [ ] §3.8M table exists after §3.8 Darts section
- [ ] Table has 4 market rows matching §3.0b darts markets
- [ ] DartsOrakel identified as primary source
- [ ] Format verification (sets vs legs) noted

---

#### Task 2.5 - [MODIFY] Add §3.9M MANDATORY MULTI-MARKET CALCULATION (HANDBALL)

**Description:** Add mandatory multi-market calculation table after the existing §3.9 Handball section.

**Content to add:**

```markdown
**§3.9M MANDATORY MULTI-MARKET CALCULATION (HANDBALL):**
Before selecting ANY handball market, calculate ALL of these:
```
| Market               | TeamA avg | TeamB avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
|----------------------|-----------|-----------|---------|------|---------|---------|--------|
| 1H total O/U X.5     |           |           |         |      |         |         |        |
| Game total O/U X.5   |           |           |         |      |         |         |        |
| Team goals O/U X.5   |           |           |         |      |         |         |        |
| Suspensions O/U X.5  |           |           |         |      |         |         |        |
```
Pick the market with HIGHEST safety score. HOME ADVANTAGE is extreme in handball (60-65% home win rate) — factor into team goal calculations. Use Flashscore + EHF/eurohandball for stats. 2nd half typically produces 1-2 more goals than 1st half.
```

**Definition of Done:**

- [ ] §3.9M table exists after §3.9 Handball section
- [ ] Table has 4 market rows matching §3.0b handball markets
- [ ] Home advantage note included
- [ ] Half-split guidance included

---

#### Task 2.6 - [MODIFY] Add §3.10M MANDATORY MULTI-MARKET CALCULATION (TABLE TENNIS)

**Description:** Add mandatory multi-market calculation table after the existing §3.10 Table Tennis section.

**Content to add:**

```markdown
**§3.10M MANDATORY MULTI-MARKET CALCULATION (TABLE TENNIS):**
Before selecting ANY table tennis market, calculate ALL of these:
```
| Market               | P1 avg | P2 avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
|----------------------|--------|--------|---------|------|---------|---------|--------|
| Total pts O/U X.5    |        |        |         |      |         |         |        |
| Set total O/U X.5    |        |        |         |      |         |         |        |
| Set HC -X.5/+X.5     |        |        |         |      |         |         |        |
```
Pick the market with HIGHEST safety score. **HIGH-VARIANCE SPORT** — reduce all safety scores by 0.10. Use ITTF rankings + Flashscore for form. Close ranking (<20 spots) → Over sets is default tendency. BO5 vs BO7 format affects set totals significantly.
```

**Definition of Done:**

- [ ] §3.10M table exists after §3.10 Table Tennis section
- [ ] Table has 3 market rows (minimum for this sport)
- [ ] High-variance penalty noted
- [ ] Format guidance (BO5 vs BO7) included

---

#### Task 2.7 - [MODIFY] Add §3.11M MANDATORY MULTI-MARKET CALCULATION (MMA)

**Description:** Add mandatory multi-market calculation table after the existing §3.11 MMA section.

**Content to add:**

```markdown
**§3.11M MANDATORY MULTI-MARKET CALCULATION (MMA):**
Before selecting ANY MMA market, calculate ALL of these:
```
| Market                | FighterA | FighterB | H2H avg | Line | Hit L10 | Hit H2H | Safety |
|-----------------------|----------|----------|---------|------|---------|---------|--------|
| Total rounds O/U X.5  |          |          |         |      |         |         |        |
| Method of victory     |          |          |         |      |         |         |        |
| ITD Y/N              |          |          |         |      |         |         |        |
```
Pick the market with HIGHEST safety score. **Finish rate is the key stat:** Both >50% finish rate → Under rounds. Both >50% decision rate → Over rounds. HW = highest KO variance — reduce safety by 0.15. Use UFC.com/stats + Sherdog + Tapology. H2H is rarely available (most fighters meet once) — use style-matchup analysis as substitute.
```

**Definition of Done:**

- [ ] §3.11M table exists after §3.11 MMA section
- [ ] Table has 3 market rows (minimum for this sport)
- [ ] Finish rate decision logic included
- [ ] H2H scarcity acknowledged with substitute guidance

---

#### Task 2.8 - [MODIFY] Add §3.12M MANDATORY MULTI-MARKET CALCULATION (BASEBALL)

**Description:** Add mandatory multi-market calculation table after the existing §3.12 Baseball section.

**Content to add:**

```markdown
**§3.12M MANDATORY MULTI-MARKET CALCULATION (BASEBALL):**
Before selecting ANY baseball market, calculate ALL of these:
```
| Market               | TeamA avg | TeamB avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
|----------------------|-----------|-----------|---------|------|---------|---------|--------|
| F5 innings total O/U |           |           |         |      |         |         |        |
| Team total O/U X.5   |           |           |         |      |         |         |        |
| Game total O/U X.5   |           |           |         |      |         |         |        |
| Hits O/U X.5         |           |           |         |      |         |         |        |
| Strikeouts O/U X.5   |           |           |         |      |         |         |        |
| Run line ±1.5        |           |           |         |      |         |         |        |
```
Pick the market with HIGHEST safety score. **F5 innings are most reliable** (removes bullpen variance). Use BaseballSavant for pitcher stats + Baseball-Reference for team offense. **Learned caution:** MLB totals have 33% historical hit rate — apply −0.10 safety penalty to all game totals. MLB overs ≥8.5 → HARD REJECT.
```

**Definition of Done:**

- [ ] §3.12M table exists after §3.12 Baseball section
- [ ] Table has 6 market rows (most markets of any support sport)
- [ ] F5 reliability note included
- [ ] Historical caution (33% hit rate) encoded as safety penalty

---

#### Task 2.9 - [MODIFY] Add §3.13M MANDATORY MULTI-MARKET CALCULATION (PADEL)

**Description:** Add mandatory multi-market calculation table after the existing §3.13 Padel section.

**Content to add:**

```markdown
**§3.13M MANDATORY MULTI-MARKET CALCULATION (PADEL):**
Before selecting ANY padel market, calculate ALL of these:
```
| Market               | PairA avg | PairB avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
|----------------------|-----------|-----------|---------|------|---------|---------|--------|
| Game total O/U X.5   |           |           |         |      |         |         |        |
| Set total O/U 2.5    |           |           |         |      |         |         |        |
| Set HC -1.5/+1.5     |           |           |         |      |         |         |        |
```
Pick the market with HIGHEST safety score. Use PadelFIP + PremierPadel + Sofascore padel. **Partnership duration is critical** — new pair (<6 months) = volatile, reduce safety by 0.15. Ranking gap <1000 → default tendency toward Over 2.5 sets.
```

**Definition of Done:**

- [ ] §3.13M table exists after §3.13 Padel section
- [ ] Table has 3 market rows (minimum for this sport)
- [ ] Partnership duration penalty included
- [ ] Ranking gap guidance included

---

#### Task 2.10 - [MODIFY] Add §3.14M MANDATORY MULTI-MARKET CALCULATION (SPEEDWAY)

**Description:** Add mandatory multi-market calculation table after the existing §3.14 Speedway section.

**Content to add:**

```markdown
**§3.14M MANDATORY MULTI-MARKET CALCULATION (SPEEDWAY):**
Before selecting ANY speedway market, calculate ALL of these:
```
| Market                | TeamA avg | TeamB avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
|-----------------------|-----------|-----------|---------|------|---------|---------|--------|
| Total pts O/U X.5    |           |           |         |      |         |         |        |
| Team HC ±X.5         |           |           |         |      |         |         |        |
```
Pick the market with HIGHEST safety score. **TRACK-SPECIFIC rider averages are most important** — use rider avg AT THIS TRACK, not season avg. Use SpeedwayEkstraliga + SportoweFakty. HOME ADVANTAGE = 70-75%. Calculate team total from rider track-specific averages, not team-level stats.
```

**Definition of Done:**

- [ ] §3.14M table exists after §3.14 Speedway section
- [ ] Table has 2 market rows (limited market availability)
- [ ] Track-specific rider average guidance included
- [ ] Home advantage percentage noted

---

### Phase 3: Enforcement — Mechanical Verification in Orchestrator

> **File:** `.github/prompts/orchestrate-betting-day.prompt.md`
> **Dependency:** Phase 1 (template markers must be defined first).

#### Task 3.1 - [MODIFY] Replace post-S3 Structural Verification with Mechanical Verification

**Description:** Replace the existing "After S3" verification block in the STRUCTURAL OUTPUT VERIFICATION section with a new mechanical verification that counts section markers, scans for banned words, and validates numeric fields. The existing verification is qualitative ("exists", "present") — the new one is quantitative (count rows, check types, grep banned words).

**Location:** In the `STRUCTURAL OUTPUT VERIFICATION` section, replace the entire `### After S3 — Read...` block.

**Content to replace with:**

```markdown
### After S3 — MECHANICAL VERIFICATION of `{date}_s3_deep_stats.md`:

**This is the PRIMARY enforcement mechanism. Use `sequentialthinking` to execute all 7 checks PER candidate.**

```
For EACH candidate block (delimited by ══ CANDIDATE ... ══ and ══ END CANDIDATE ══):

CHECK 1: SECTION MARKER COUNT
  - Count markers §S3.1 through §S3.10 within this candidate block
  - REQUIRED: exactly 10 markers
  - FAIL if <10 → "MISSING SECTIONS: [list missing §S3.N markers]"

CHECK 2: RANKING TABLE ROW COUNT (§S3.3)
  - Count data rows in the §S3.3 table (exclude header row and separator)
  - REQUIRED: ≥3 rows (≥4 for Football)
  - FAIL if <3 → "RANKING TABLE TOO SHORT: [N] rows, need ≥3"

CHECK 3: BANNED WORD SCAN (ALL TABLES)
  - Scan every table cell in §S3.1-§S3.10 for banned words:
    "checked", "verified", "confirmed", "good", "fine", "OK", "done", "yes", "—", "N/A", "n/a", "see above"
  - ONLY flag if the banned word is the SOLE content of the cell (not part of a sentence)
  - FAIL if any found → "BANNED WORD: '[word]' in §S3.[N], row [R], column [C]"

CHECK 4: SAFETY SCORE NUMERIC (§S3.3)
  - Verify every cell in the "Safety" column is a decimal number between 0.00 and 1.00
  - FAIL if any non-numeric → "NON-NUMERIC SAFETY: '[value]' in row [R]"

CHECK 5: THREE-WAY NUMERIC (§S3.4)
  - Verify L10, H2H, L5 rows each have a numeric "Value" cell
  - Verify "Direction" cells contain only: SUPPORTS, CONFLICTS, UP, DOWN, STABLE
  - FAIL if non-numeric value → "NON-NUMERIC THREE-WAY: '[cell]' in row [R]"

CHECK 6: SOURCE TABLE ROW COUNT (§S3.9)
  - Count data rows in the §S3.9 table
  - REQUIRED: ≥2 rows
  - FAIL if <2 → "INSUFFICIENT SOURCES: [N] rows, need ≥2"

CHECK 7: INJURY SOURCE PRESENT (§S3.6)
  - If injury table has rows: verify "Source" column is filled for every row
  - If "No injuries" line: verify it names a source (not just "No injuries")
  - FAIL if source missing → "INJURY CHECK UNSOURCED"

SCORING:
  candidates_passing_all_7 / total_candidates × 100 = DEPTH_%

GATE: DEPTH_% must be 100%.
  If <100%: compile ALL failures into a single message and RETURN to bet-statistician:
  "S3 STRUCTURAL VIOLATIONS — [N] candidates have [M] total failures:
   - [Candidate 1]: CHECK [N] FAIL — [details]
   - [Candidate 2]: CHECK [N] FAIL — [details]
   FIX ALL violations. Do NOT skip any section. Resubmit complete S3 output."

  NEVER proceed to S4 with structural violations. NEVER "accept with warnings."
```
```

**Definition of Done:**

- [ ] The old qualitative "After S3" block is fully replaced
- [ ] 7 numbered checks are defined with specific FAIL messages
- [ ] Banned words list matches §3.0d in analysis-methodology
- [ ] Football exception (≥4 rows) is specified in CHECK 2
- [ ] GATE is 100% — no partial pass allowed
- [ ] Return-to-agent message template includes all violations
- [ ] `sequentialthinking` is referenced for execution

---

### Phase 4: Agent Constraints — Statistician Self-Check

> **File:** `.github/agents/bet-statistician.agent.md`
> **Dependency:** Phase 1 (template sections must be defined).

#### Task 4.1 - [MODIFY] Add SELF-VERIFICATION PROTOCOL to constraints

**Description:** Add a new self-verification checklist to the `<constraints>` section that the statistician agent must run before writing the S3 output file. This is a "last line of defense" — if the orchestrator's check fails, the agent should have caught it first.

**Location:** At the end of the `<constraints>` section, before the closing `</constraints>` tag.

**Content to add:**

```markdown
- **SELF-VERIFICATION PROTOCOL (run before writing S3 output file):**
  For EVERY candidate, verify before submitting:
  ```
  □ 10/10 section markers present (§S3.1-§S3.10)?
  □ §S3.3 ranking table has ≥3 data rows (≥4 for football)?
  □ Every §S3.3 cell contains a number — no "checked", "—", or blanks?
  □ §S3.3 Safety column is decimal (0.00-1.00)?
  □ §S3.4 has 3 rows (L10, H2H, L5) with numeric values?
  □ §S3.4 Alignment verdict is explicit (3/3 SUPPORT / 2/3 CONFLICT / REJECT)?
  □ §S3.9 has ≥2 source rows with actual source names?
  □ §S3.6 injury check names specific source (not "checked")?
  □ §S3.10 Depth Proof has 5 metrics with numbers?
  □ No BANNED WORD (§3.0d) appears as sole cell content anywhere?
  ```
  If ANY □ fails → FIX before writing the output file. Do NOT submit incomplete output.
  SELF-CHECK FAILURE = higher priority than completing more candidates.
```

**Definition of Done:**

- [ ] Self-verification protocol added to constraints section
- [ ] 10 checkbox items covering all template sections
- [ ] References §3.0d for banned words
- [ ] Explicit instruction to fix before submitting
- [ ] Priority note: self-check > more candidates

---

#### Task 4.2 - [MODIFY] Update domain-standards to reference §S3.1-§S3.10

**Description:** Update the `<domain-standards>` section to reference the new mandatory template from §3.0e instead of the current loose list of 7 items.

**Location:** Replace the content of the `<domain-standards>` section.

**Content to replace with:**

```markdown
<domain-standards>

**Per-candidate output MUST follow the §3.0e MANDATORY PER-CANDIDATE OUTPUT TEMPLATE exactly:**

| Section | Content | Validation |
|---------|---------|------------|
| §S3.1 H2H Analysis | H2H meetings for specific stat, H2H avg, BLIND status | ≥3 meetings or H2H-STAT-BLIND flag |
| §S3.2 Form & Stats | Sport-specific stats table, all columns, home/away split | Every cell has data (no blanks) |
| §S3.3 Market Ranking | §3.0 ranking table, all available markets | ≥3 rows (≥4 football), Safety = decimal |
| §S3.4 Three-Way Check | L10 + H2H + L5 with alignment verdict | 3 rows with numeric values |
| §S3.5 Coach/Roster | Coach change check, roster change check | Source named, date checked |
| §S3.6 Injuries | Injury table or explicit "no injuries" with source | Source column always filled |
| §S3.7 Top 3 Markets | Top 3 from ranking with safety scores | 3 markets with hit rates |
| §S3.8 Recommended | Selected market with line, safety, reasoning | Cites §S3.3 numbers |
| §S3.9 Sources | All sources used with data collected | ≥2 rows |
| §S3.10 Depth Proof | Quantified analysis metrics | 5 metric rows with numbers |

**The orchestrator will MECHANICALLY verify all 10 sections exist with real data. Any violation → output is REJECTED and returned for fixing.**

**S3B time-sensitive output must include:**
1. Confirmed lineups (or "not yet available" with expected availability time)
2. Late injury/suspension updates with source
3. Weather impact assessment (outdoor sports)
4. Odds drift calculation: `drift_pct = 100 × ((current/analysis) − 1)`

</domain-standards>
```

**Definition of Done:**

- [ ] Domain-standards references §3.0e template explicitly
- [ ] Table maps all 10 sections to content and validation criteria
- [ ] Mechanical verification warning included
- [ ] S3B requirements preserved

---

### Phase 5: Zero Tolerance + Common Mistakes Updates

> **File:** `.github/instructions/analysis-methodology.instructions.md`
> **Dependency:** None — independent of other phases.

#### Task 5.1 - [MODIFY] Add Zero Tolerance Shield entry #16

**Description:** Add a new entry to the Zero Tolerance Shield table documenting the PSG vs Bayern failure pattern.

**Location:** After row #15 in the Zero Tolerance Shield table.

**Content to add (new table row):**

```markdown
| 16 | PSG vs Bayern cards approved without ranking comparison | S3 output was narrative, not structured. No §3.0 table, no alternative markets compared, no three-way cross-check. | §3.0e template is MANDATORY. If §S3.3 ranking table has <3 rows → STRUCTURAL VIOLATION. Orchestrator mechanically verifies. |
```

**Definition of Done:**

- [ ] Row #16 exists in Zero Tolerance Shield table
- [ ] Root cause identifies "narrative vs structured" problem
- [ ] Prevention references §3.0e and mechanical verification

---

#### Task 5.2 - [MODIFY] Add Common Mistake #21

**Description:** Add a new common mistake entry for narrative shortcuts in S3 analysis.

**Location:** After common mistake #20 in the COMMON MISTAKES list.

**Content to add:**

```markdown
21. Writing narrative analysis instead of filling the §3.0e template — "H2H avg 5.8 cards" in a paragraph is NOT a §S3.3 ranking table. Every candidate needs ALL 10 sections (§S3.1-§S3.10) with real numbers in real tables.
```

**Definition of Done:**

- [ ] Common mistake #21 exists referencing §3.0e template
- [ ] Contrasts narrative paragraph vs structured table
- [ ] References all 10 sections

---

### Phase 6: Validation

> **No file changes — verification only.**
> **Dependency:** All previous phases completed.

#### Task 6.1 - Cross-Reference Consistency Check

**Description:** Verify that all cross-references between files are correct and consistent.

**Definition of Done:**

- [ ] §3.0d banned words list in analysis-methodology matches the banned words in orchestrator CHECK 3
- [ ] §3.0e section markers (§S3.1-§S3.10) match the markers referenced in orchestrator CHECK 1
- [ ] §3.0e minimum row counts match orchestrator CHECK 2 (≥3/≥4), CHECK 5 (3), CHECK 6 (≥2)
- [ ] bet-statistician self-verification 10 items match the 7 orchestrator checks
- [ ] §3.XM tables exist for all 14 sports (Football, Tennis, Basketball, Hockey, Volleyball, Esports, Snooker, Darts, Handball, Table Tennis, MMA, Baseball, Padel, Speedway)
- [ ] bet-statistician domain-standards table has 10 rows matching §S3.1-§S3.10

#### Task 6.2 - Template Dry-Run Verification

**Description:** Mentally trace through a complete S3 analysis for one football and one tennis candidate using the new template to verify completeness and catch ambiguities.

**Definition of Done:**

- [ ] Football candidate: all 10 sections fillable with realistic data
- [ ] Football candidate: §S3.3 has ≥4 rows (Fouls, Cards, Corners, Shots minimum)
- [ ] Tennis candidate: all 10 sections fillable with realistic data
- [ ] Tennis candidate: §S3.3 has ≥3 rows (Games, Sets, Game HC minimum)
- [ ] Both candidates: no section requires data that doesn't exist for common matches
- [ ] Both candidates: §S3.10 Depth Proof is fillable with actual numbers

## Security Considerations

- No security considerations — these are instruction/prompt/agent files with no code execution or data access changes
- The banned words list in §3.0d does not affect any data processing pipelines — it is an LLM instruction for output formatting

## Quality Assurance

Acceptance criteria checklist to verify the implementation meets the defined requirements:

- [ ] PSG vs Bayern scenario: if an agent writes a narrative paragraph about cards H2H without filling the §3.0e template → orchestrator detects missing §S3.1-§S3.10 markers and REJECTS
- [ ] "Checked" shortcut: if an agent writes "checked" in a table cell → orchestrator CHECK 3 catches it and REJECTS
- [ ] Missing ranking table: if an agent writes only 1 market (cards) without comparing alternatives → orchestrator CHECK 2 catches it (<3 rows) and REJECTS
- [ ] Missing H2H for specific stat: if an agent has H2H for match results but not for corners → §S3.1 requires explicit H2H-STAT-BLIND flag, orchestrator verifies
- [ ] Hockey/Snooker/Darts/etc. candidates: agents can now find the mandatory multi-market table for ALL 14 sports — no sport can claim "no template"
- [ ] Self-verification: bet-statistician runs 10-item checklist before submitting, catching errors before orchestrator needs to reject

## Improvements (Out of Scope)

Potential improvements identified during planning that are not part of the current task:

- **Automated S3 output parser script** — a Python script that mechanically validates the S3 markdown file structure (counts markers, scans banned words, validates numbers). Would complement the orchestrator's LLM-based verification with deterministic checking.
- **S3 template linter in pre-commit hook** — a lightweight markdown linter that rejects S3 files without all 10 section markers.
- **Per-sport minimum market count enforcement** — currently ≥3 for all sports (≥4 for football). Could be sport-specific (e.g., baseball ≥5 given 6 available markets).
- **Historical safety score database** — persist safety scores per team/market across sessions to build rolling baselines.
- **Orchestrator verification as a separate agent** — dedicate a `bet-verifier` agent to S3 output validation rather than having the orchestrator do it inline.

## Changelog

| Date       | Change Description   |
| ---------- | -------------------- |
| 2026-04-28 | Initial plan created |
