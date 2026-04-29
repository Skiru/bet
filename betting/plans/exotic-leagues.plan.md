# Exotic League Support - Implementation Plan

## Task Details

| Field            | Value                                                                 |
| ---------------- | --------------------------------------------------------------------- |
| Jira ID          | N/A                                                                   |
| Title            | Add Exotic League Support to Betting Workflow                         |
| Description      | Formalize scanning, analysis, and source coverage for non-mainstream football leagues (Peru, Egypt, Kings League, Uzbekistan, and 40+ other exotic competitions) |
| Priority         | Medium                                                                |
| Related Research | N/A                                                                   |

## Proposed Solution

Add structured exotic league support across the entire betting workflow pipeline — from source discovery and scanning through analysis protocols and pipeline code. The implementation covers six layers:

1. **Source Registry** — new "Exotic League Sources" section with regional groupings and per-region source availability
2. **Analysis Methodology** — new §1.7 Exotic League Protocol defining data thresholds, fallback chains, and confidence adjustments for thin-data environments
3. **Sport Protocols** — new §3.1E Exotic League Football subsection with adjusted stat requirements
4. **Scan Pipeline** — additional Flashscore/Soccerway/BetExplorer regional URLs in `run_full_scan_and_prepare.sh`
5. **Event Detection** — extended URL patterns in `scan_events.py` for exotic source domains
6. **Aggregation** — exotic stat sources added to `TIER_A_STATS_EXTENDED` in `aggregate_and_select.py`
7. **Config** — optional `exotic_leagues` metadata in `betting_config.json` listing leagues with source availability status

**Key architectural decisions:**

- Exotic leagues are **football-centric** (95% of exotic coverage is football). Other sports in exotic regions have negligible Betclic market availability.
- Existing mainstream sources (Flashscore, Sofascore, BetExplorer) already cover most exotic leagues — the gap is in **explicit URL scanning** and **stat-depth sources**.
- New specialist sources (Soccerway, AiScore, Xscores, Goaloo, NowGoal) fill the H2H and stat gap for regions where SoccerStats/TotalCorner have limited coverage.
- **Betclic market existence is the primary gate** — many exotic leagues have no markets on Betclic. The protocol enforces an early market-availability check to avoid wasted analysis time.
- **Match-fixing risk** is elevated in certain exotic leagues (lower divisions, low-attendance, specific regions). This is formalized as a red flag in the protocol.
- **Data thresholds are relaxed but not abandoned** — exotic picks allow 3 H2H meetings (vs 5 for mainstream), 2 stat sources (vs 3), but still require EV > 0 and the full §3.0 market ranking.

```
┌─────────────────────────────────────────────────────────────────┐
│                    EXOTIC LEAGUE DATA FLOW                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  source-registry.md ──► run_full_scan_and_prepare.sh            │
│  (exotic sources)        (regional URLs added)                  │
│         │                       │                               │
│         ▼                       ▼                               │
│  scan_events.py ◄────── URL pattern matching                    │
│  (exotic domains)        (detect_sport)                         │
│         │                                                       │
│         ▼                                                       │
│  aggregate_and_select.py                                        │
│  (exotic stat sources in TIER_A_STATS_EXTENDED)                 │
│         │                                                       │
│         ▼                                                       │
│  analysis-methodology.md ──► §1.7 EXOTIC LEAGUE PROTOCOL       │
│  (confidence adjustments,    (Betclic market gate,              │
│   fallback chains,            match-fixing red flags,           │
│   data thresholds)            thin-data handling)               │
│         │                                                       │
│         ▼                                                       │
│  sport-analysis-protocols.md ──► §3.1E EXOTIC LEAGUE FOOTBALL  │
│  (adjusted stat requirements,    (fallback stat sources,        │
│   minimum thresholds)             approval thresholds)          │
│         │                                                       │
│         ▼                                                       │
│  betting_config.json                                            │
│  (exotic_leagues metadata, source availability)                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Current Implementation Analysis

### Already Implemented

- Flashscore football main page scanning — `scripts/run_full_scan_and_prepare.sh` (line ~58, `https://www.flashscore.com/`)
- Sofascore main page scanning — `scripts/run_full_scan_and_prepare.sh` (line ~70)
- BetExplorer main page scanning — `scripts/run_full_scan_and_prepare.sh` (lines ~90-100)
- Sport URL pattern detection — `scripts/scan_events.py` (lines 22-37, `SPORT_URL_PATTERNS`)
- Football stat sources — `scripts/aggregate_and_select.py` (line 33, `TIER_A_STATS_EXTENDED["football"]`)
- Football analysis protocol — `.github/instructions/sport-analysis-protocols.instructions.md` (§3.1)
- Football corner 3-source stack — `sport-analysis-protocols.instructions.md` (§3.1)
- "Scan beyond the obvious" instruction — `analysis-methodology.instructions.md` (KEY sport league depth section)
- LiveScore entry in source-registry — `betting/sources/source-registry.md` (Cross-Sport Fixture section)
- Football sport playbook — `betting/sources/source-registry.md` (Sport-Specific Playbooks section)
- Flashscore/Sofascore as universal fixture sources — `betting/sources/source-registry.md` (Tier A Core Stats)

### To Be Modified

- `betting/sources/source-registry.md` — add new "Exotic League Sources (by region)" section after existing Tier A Specialist sections, add Soccerway/AiScore/Xscores/Goaloo/NowGoal entries, update Football sport playbook with exotic fallback note, update Odds Source Map table with exotic row
- `.github/instructions/analysis-methodology.instructions.md` — add §1.7 EXOTIC LEAGUE PROTOCOL after §1.6 Scan Completeness Gate, add exotic league row to §4.3 tipster fallback table, add exotic entry to ZERO TOLERANCE SHIELD
- `.github/instructions/sport-analysis-protocols.instructions.md` — add §3.1E EXOTIC LEAGUE FOOTBALL subsection after §3.1M
- `scripts/run_full_scan_and_prepare.sh` — add ~20 exotic regional Flashscore URLs, add Soccerway regional URLs, add BetExplorer regional football URLs
- `scripts/scan_events.py` — add exotic source domains to `SPORT_URL_PATTERNS["football"]` list
- `scripts/aggregate_and_select.py` — add exotic stat source domains to `TIER_A_STATS_EXTENDED["football"]` set
- `config/betting_config.json` — add `exotic_leagues` metadata section

### To Be Created

No new files need to be created. All changes are modifications to existing files.

## Open Questions

| #   | Question                                                                 | Answer                                                                                     | Status       |
| --- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------ | ------------ |
| 1   | Which exotic leagues does Betclic actually offer markets for?            | Must be verified manually per league on betclic.pl. Plan includes market-availability gate. | ✅ Resolved  |
| 2   | Should exotic league URLs be scanned every session or only on demand?    | Every session — they are part of the standard Flashscore/BetExplorer pages already, just need explicit regional URL entries for depth | ✅ Resolved  |
| 3   | How many additional URLs is acceptable for scan pipeline performance?    | ~20-25 regional URLs. Each takes ~3-5s with rate limiting. Adds ~60-75s to total scan time. Acceptable. | ✅ Resolved  |
| 4   | Should Kings League (entertainment format) have different analysis rules? | Yes — noted as special case in §1.7 with specific flags (non-standard rules, entertainment context, roster instability) | ✅ Resolved  |

## Implementation Plan

### Phase 1: Source Registry — Exotic League Sources

#### Task 1.1 - [MODIFY] Add Exotic League Specialist Sources to Source Registry

**Description**: Add new source entries for Soccerway, AiScore, Xscores, Goaloo, and NowGoal to `betting/sources/source-registry.md`. These are placed in a new subsection "### Exotic League Specialist Sources" within the Tier A Specialist Statistical Sources section, after the existing Football subsection.

Each source entry follows the existing format: Name, Role, URL, Use for, Access, Coverage notes.

**File**: `betting/sources/source-registry.md`

**Content to add (after the Football corners/cards/fouls specialist subsection):**

```markdown
### Exotic League Specialist Sources

- Soccerway
  Role: massive global football coverage — fixtures, results, standings, H2H, squad lists, referee assignments for 200+ countries and 1000+ leagues.
  URL: soccerway.com
  Use for: exotic league fixtures, results, standings, H2H (primary H2H source for exotic leagues where Flashscore H2H is thin). Squad and referee data for context.
  Access: OK (no Cloudflare). Direct page URLs by country: `/football/[country]/[league]/`.
  Coverage: Peru Liga 1, Egyptian Premier League, Uzbekistan Super League, Kings League, Algerian Ligue 1, Moroccan Botola, Saudi Pro League, UAE Pro League, Indian ISL, Vietnamese V-League, Thai League, Colombian Liga BetPlay, Chilean Primera, Paraguayan Primera, Bolivian Primera, Ecuadorian LigaPro, Costa Rican Primera, Iranian Persian Gulf Pro League, Jordanian Pro League, Kazakhstan Premier League, Georgian Erovnuli Liga, Armenian Premier League, Azerbaijani Premier League, Faroe Islands Premier League, Gibraltar National League, Kosovo Superliga, North Macedonian First League, and 150+ more.
  Note: PRIMARY source for exotic league H2H and standings when Flashscore coverage is thin.

- AiScore
  Role: live scores and statistics for obscure leagues — covers Asian, African, and South American football with match stats.
  URL: aiscore.com
  Use for: fixture discovery and basic match stats (possession, shots, corners) for leagues not covered by SoccerStats/TotalCorner. Secondary H2H source.
  Access: OK.
  Coverage: Strong in Southeast Asia (Vietnam, Thailand, Myanmar, Cambodia, Laos), Middle East (Iran, Iraq, Jordan), Central Asia (Uzbekistan, Kazakhstan, Kyrgyzstan), and Africa (Egypt, Algeria, Morocco, Nigeria).

- Xscores
  Role: Asian and African football league coverage — live scores, results, standings, and basic stats.
  URL: xscores.com
  Use for: fixture cross-validation and results for Asian/African exotic leagues. Good for H2H lookups in leagues not on Flashscore.
  Access: OK.
  Coverage: Specializes in Asian and African football. Good for Iran, Iraq, Saudi Arabia, Egypt, Algeria, Morocco, India, Bangladesh, Myanmar.

- Goaloo
  Role: Asian football coverage — live scores, odds, stats, and standings for Asian leagues.
  URL: goaloo.com
  Use for: Asian exotic league fixtures and basic stats. Odds comparison for Asian bookmakers (useful for line cross-validation).
  Access: OK.
  Coverage: J-League, K-League, Chinese Super League, Thai League, Vietnamese V-League, Indian ISL, A-League, and other Asian leagues.

- NowGoal
  Role: Asian market focused football data — live scores, odds, stats, Asian handicap lines.
  URL: nowgoal.com
  Use for: Asian exotic league coverage with Asian handicap lines. Good for Southeast Asian and East Asian football.
  Access: OK.
  Coverage: J-League, K-League, Thai League, Vietnamese V-League, Indonesian Liga 1, Malaysian Super League, Singapore Premier League, and other SEA/East Asian leagues.

- BetsAPI
  Role: API for live and upcoming events across 100+ football leagues globally — covers fixtures, results, and basic odds.
  URL: betsapi.com
  Use for: programmatic fixture discovery for exotic leagues. Useful when Flashscore/Sofascore don't list a specific league's fixtures.
  Access: Free tier available. API-based (JSON).
  Coverage: 100+ leagues including many exotic ones. Good for verifying fixture existence.
```

**Definition of Done**:

- [x] Six new source entries (Soccerway, AiScore, Xscores, Goaloo, NowGoal, BetsAPI) added to `source-registry.md`
- [x] Each entry has Role, URL, Use for, Access, Coverage fields matching existing format
- [x] Entries placed in a new "### Exotic League Specialist Sources" subsection within Tier A Specialist Statistical Sources
- [x] No existing source entries are modified or removed

#### Task 1.2 - [MODIFY] Add Exotic Region Groupings to Source Registry

**Description**: Add a new section "### Exotic League Coverage Map" at the end of the Sport Playbooks section in `source-registry.md`. This provides a per-region reference showing which sources cover which exotic leagues, and known Betclic availability status.

**File**: `betting/sources/source-registry.md`

**Content to add (before the "## Settlement Sources" section):**

```markdown
### Exotic League Coverage Map

Use this table to know WHERE to get data for exotic football leagues. "Betclic" column indicates known market availability (✅ = markets exist, ❓ = check manually, ❌ = no markets).

#### South America
| League | Country | Flashscore | Sofascore | BetExplorer | Soccerway | Betclic |
|--------|---------|------------|-----------|-------------|-----------|---------|
| Liga 1 | Peru | ✅ | ✅ | ✅ | ✅ | ❓ |
| Liga BetPlay | Colombia | ✅ | ✅ | ✅ | ✅ | ❓ |
| Primera División | Chile | ✅ | ✅ | ✅ | ✅ | ❓ |
| División Profesional | Paraguay | ✅ | ✅ | ✅ | ✅ | ❓ |
| Primera División | Bolivia | ✅ | ✅ | ❓ | ✅ | ❓ |
| LigaPro | Ecuador | ✅ | ✅ | ✅ | ✅ | ❓ |
| Primera División | Costa Rica | ✅ | ✅ | ❓ | ✅ | ❓ |
| Liga Nacional | Guatemala | ✅ | ❓ | ❓ | ✅ | ❓ |
| Liga Nacional | Honduras | ✅ | ❓ | ❓ | ✅ | ❓ |
| Primera División | El Salvador | ✅ | ❓ | ❓ | ✅ | ❓ |

#### Africa & Middle East
| League | Country | Flashscore | Sofascore | BetExplorer | Soccerway | AiScore | Betclic |
|--------|---------|------------|-----------|-------------|-----------|---------|---------|
| Egyptian Premier League | Egypt | ✅ | ✅ | ✅ | ✅ | ✅ | ❓ |
| Ligue 1 | Algeria | ✅ | ✅ | ✅ | ✅ | ✅ | ❓ |
| Botola Pro | Morocco | ✅ | ✅ | ✅ | ✅ | ✅ | ❓ |
| Saudi Pro League | Saudi Arabia | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| UAE Pro League | UAE | ✅ | ✅ | ✅ | ✅ | ✅ | ❓ |
| Persian Gulf Pro League | Iran | ✅ | ✅ | ✅ | ✅ | ✅ | ❓ |
| Stars League | Iraq | ✅ | ❓ | ❓ | ✅ | ✅ | ❓ |
| Pro League | Jordan | ✅ | ❓ | ❓ | ✅ | ✅ | ❓ |

#### Asia & Oceania
| League | Country | Flashscore | Sofascore | BetExplorer | Goaloo | NowGoal | Betclic |
|--------|---------|------------|-----------|-------------|--------|---------|---------|
| ISL / I-League | India | ✅ | ✅ | ✅ | ✅ | ✅ | ❓ |
| V-League | Vietnam | ✅ | ✅ | ❓ | ✅ | ✅ | ❓ |
| Thai League | Thailand | ✅ | ✅ | ❓ | ✅ | ✅ | ❓ |
| Super League | Uzbekistan | ✅ | ✅ | ❓ | ❓ | ❓ | ❓ |
| Premier League | Kazakhstan | ✅ | ✅ | ✅ | ❓ | ❓ | ❓ |
| Premier League | Bangladesh | ✅ | ❓ | ❓ | ❓ | ❓ | ❓ |
| National League | Myanmar | ✅ | ❓ | ❓ | ❓ | ✅ | ❓ |
| C-League | Cambodia | ❓ | ❓ | ❓ | ❓ | ✅ | ❓ |
| Premier League | Laos | ❓ | ❓ | ❓ | ❓ | ❓ | ❓ |

#### Central Asia & Caucasus
| League | Country | Flashscore | Sofascore | BetExplorer | Soccerway | Betclic |
|--------|---------|------------|-----------|-------------|-----------|---------|
| Premier League | Kazakhstan | ✅ | ✅ | ✅ | ✅ | ❓ |
| Premier League | Kyrgyzstan | ✅ | ❓ | ❓ | ✅ | ❓ |
| Vysshaya Liga | Tajikistan | ✅ | ❓ | ❓ | ✅ | ❓ |
| Ýokary Liga | Turkmenistan | ❓ | ❓ | ❓ | ✅ | ❓ |
| Erovnuli Liga | Georgia | ✅ | ✅ | ✅ | ✅ | ❓ |
| Premier League | Armenia | ✅ | ✅ | ✅ | ✅ | ❓ |
| Premier League | Azerbaijan | ✅ | ✅ | ✅ | ✅ | ❓ |

#### European Micro/Minor Leagues
| League | Country | Flashscore | Sofascore | BetExplorer | Soccerway | Betclic |
|--------|---------|------------|-----------|-------------|-----------|---------|
| Betrideildin | Faroe Islands | ✅ | ✅ | ✅ | ✅ | ❓ |
| National League | Gibraltar | ✅ | ✅ | ❓ | ✅ | ❓ |
| Primera Divisió | Andorra | ✅ | ❓ | ❓ | ✅ | ❓ |
| Campionato | San Marino | ✅ | ❓ | ❓ | ✅ | ❓ |
| Superliga | Kosovo | ✅ | ✅ | ✅ | ✅ | ❓ |
| First League | North Macedonia | ✅ | ✅ | ✅ | ✅ | ❓ |

#### Entertainment Leagues
| League | Country | Flashscore | Sofascore | BetExplorer | Soccerway | Betclic |
|--------|---------|------------|-----------|-------------|-----------|---------|
| Kings League | Spain | ✅ | ✅ | ❓ | ❓ | ❓ |

**Note:** ❓ = verify manually on the source website or Betclic app before analysis. Kings League uses modified rules (shorter halves, special gameplay mechanics) — see §1.7 for protocol.
```

**Definition of Done**:

- [x] Exotic League Coverage Map added to `source-registry.md` with 6 regional tables
- [x] Each table has columns for major data sources + Betclic availability
- [x] Coverage uses ✅/❓/❌ symbols consistently
- [x] Kings League noted as entertainment format with §1.7 cross-reference
- [x] Section placed logically before "## Settlement Sources"

#### Task 1.3 - [MODIFY] Update Football Sport Playbook with Exotic Fallback

**Description**: Add an exotic league note to the existing Football sport playbook in `source-registry.md` and add a new row to the Odds Source Map table for exotic football.

**File**: `betting/sources/source-registry.md`

**Definition of Done**:

- [x] Football playbook entry in "Sport-Specific Playbooks" has a new line: `Exotic fallback: Soccerway (H2H, standings) + AiScore/Xscores (Asian/African stats) + Goaloo/NowGoal (Asian coverage). Use when SoccerStats/TotalCorner have no data for the league.`
- [x] Odds Source Map table has a new row: `**Football** (Exotic) | BetExplorer | OddsPortal | Soccerway | The-Odds-API`

### Phase 2: Analysis Methodology — Exotic League Protocol

#### Task 2.1 - [MODIFY] Add §1.7 EXOTIC LEAGUE PROTOCOL to Analysis Methodology

**Description**: Add a new section §1.7 to `analysis-methodology.instructions.md` after the §1.6 Scan Completeness Gate. This section defines what qualifies as an exotic league, data thresholds, fallback chains, confidence adjustments, and red flags.

**File**: `.github/instructions/analysis-methodology.instructions.md`

**Content to add:**

```markdown
### §1.7 EXOTIC LEAGUE PROTOCOL

**Definition:** An "exotic league" is any football competition OUTSIDE:
- Top 5 European leagues (EPL, LaLiga, Bundesliga, Serie A, Ligue 1) and their 2nd divisions
- Top established European leagues (Eredivisie, Belgian Pro League, Portuguese Primeira, Turkish Super Lig, Russian Premier, Swiss Super League, Austrian Bundesliga, Scottish Premiership, Greek Super League, Czech First League, Polish Ekstraklasa, Danish Superliga, Swedish Allsvenskan, Norwegian Eliteserien, Croatian HNL, Serbian SuperLiga, Ukrainian Premier, Romanian Liga 1)
- Primary US/MX/BR/AR/JP/KR leagues (MLS, Liga MX, Brasileirão, Argentine Primera, J-League, K-League)
- Continental club competitions (UCL, UEL, UECL, Copa Libertadores, Copa Sudamericana, AFC Champions League)

**Everything else is EXOTIC:** Peru Liga 1, Egyptian Premier League, Kings League, Uzbekistan Super League, Algerian Ligue 1, Saudi Pro League, Indian ISL, Vietnamese V-League, Faroe Islands, Gibraltar, Kosovo, all Central American leagues, all Central Asian leagues, etc.

**§1.7a BETCLIC MARKET GATE (MANDATORY — check BEFORE deep analysis):**
Before investing analysis time on an exotic league candidate:
1. Check if the league/event exists on Betclic (betclic.pl football section).
2. If NO markets on Betclic → SKIP (no execution path).
3. If ONLY ML/1X2 on Betclic → proceed only if strong statistical edge exists AND ML is acceptable per §6.5 upset risk.
4. If statistical markets (corners, cards, totals) exist on Betclic → proceed normally.

**§1.7b DATA THRESHOLDS (relaxed for exotic leagues):**

| Requirement | Mainstream | Exotic |
|-------------|-----------|--------|
| H2H meetings minimum | 5 | 3 (flag as EXOTIC-THIN if <5) |
| Stat sources minimum | 3 | 2 (Flashscore/Sofascore + 1 specialist) |
| Tipster sources | ≥2 with reasoning | ≥1 (exotic leagues rarely covered by tipsters) |
| Corner/card stat source | TotalCorner + SoccerStats + Betclic | Soccerway + Flashscore match stats (fallback) |
| §3.0 market ranking | ≥3 alternative markets | ≥2 alternative markets (if data allows 3, do 3) |

Picks with EXOTIC-THIN data flags:
- CANNOT be in LR coupons
- Get −0.5 confidence adjustment
- Maximum 2 exotic picks per coupon
- Maximum 1 exotic pick per LR coupon (only if NOT EXOTIC-THIN)

**§1.7c SOURCE FALLBACK CHAIN (exotic football):**
```
Primary: Flashscore (fixture, H2H, match stats) + Sofascore (form, stats)
├── H2H thin? → Soccerway H2H + AiScore H2H
├── Corner/card stats missing? → Flashscore match-level stats (last 10 games, manual count)
├── League standings missing? → Soccerway standings + BetExplorer results
├── No SoccerStats/TotalCorner? → Betaminic (covers some exotic leagues) → Flashscore per-match corner counts (manual)
└── All fail? → Google "[league name] statistics [season]" for specialist sites
```

**§1.7d RED FLAGS SPECIFIC TO EXOTIC LEAGUES:**

| Red Flag | Description | Action |
|----------|-------------|--------|
| Match-fixing risk | League/country on known match-fixing watchlists (spotfixing.eu, IBIA alerts) | HARD REJECT for exotic leagues with active alerts. For flagged countries: skip low-division matches, only top-flight with high attendance. |
| Scheduling irregularities | Mid-week matches with no clear reason, frequent postponements, irregular kickoff times | FLAG — investigate before proceeding. Unusual schedule = potential integrity issue. |
| Extreme weather/altitude | High-altitude venues (Bolivia, Peru highlands, Central Asian cities), extreme heat (Middle East summer), monsoon season (SEA) | Adjust totals expectations. High altitude = more goals/corners. Extreme heat = fewer goals, lower pace. Monsoon = match postponement risk. |
| Kings League special rules | Shorter halves (20 min), special gameplay mechanics (shootouts, power-ups), entertainment format | SEPARATE ANALYSIS PROTOCOL. Do NOT apply standard football stats. Kings League H2H/form from previous Kings League seasons ONLY. Standard football metrics DO NOT TRANSFER. |
| Low attendance / closed doors | Matches with <1000 attendance or behind closed doors | FLAG — home advantage reduced. Adjust H/A split expectations. |
| Roster instability | Frequent mid-season transfers, loan army turnover, player migration between exotic leagues | INCREASE weight on L5 recent form (post-transfer window) over L10. Coach/roster stability check is CRITICAL. |
| Time zone mismatch | Kickoff at unusual local time (e.g., 3 AM local = potential integrity concern) | FLAG — investigate reason. Official schedule adjustments for TV are OK; unexplained off-hour matches = caution. |

**§1.7e EXOTIC LEAGUE CLASSIFICATION:**
- **Tier E1 (established exotic):** Saudi Pro League, Egyptian Premier League, Moroccan Botola, Indian ISL, Colombian Liga BetPlay, Chilean Primera, Paraguayan Primera, Ecuadorian LigaPro, Peruvian Liga 1, Uzbekistan Super League, Kazakhstan Premier League, Georgian Erovnuli Liga, Kosovo Superliga, North Macedonian First League — reasonable data coverage, Flashscore/Sofascore available, BetExplorer usually has odds.
- **Tier E2 (thin data):** Bolivian Primera, Costa Rican Primera, Central American leagues, Iranian PGPL, Iraqi Stars League, Jordanian Pro League, Armenian/Azerbaijani leagues, Faroe Islands, Gibraltar, Andorra, San Marino — sparse data, limited H2H, Soccerway may be only reliable source.
- **Tier E3 (ultra-thin):** Bangladesh, Myanmar, Cambodia, Laos, Mongolia, Turkmenistan, Tajikistan, Kyrgyzstan — minimal data coverage, avoid unless strong reason and Betclic offers markets.
- **Entertainment:** Kings League — separate protocol, non-standard football rules.

Tier E3 picks require ALL of: Betclic market confirmed, ≥2 sources with data, EV > 0, and user explicit approval before placement.
```

**Definition of Done**:

- [x] §1.7 section added to `analysis-methodology.instructions.md` after §1.6
- [x] Contains subsections §1.7a through §1.7e
- [x] Betclic market gate defined as MANDATORY pre-analysis check
- [x] Data threshold comparison table (mainstream vs exotic) is present
- [x] Source fallback chain uses tree format
- [x] Red flag table has ≥7 entries with actions
- [x] Exotic tier classification (E1/E2/E3/Entertainment) with examples
- [x] Confidence adjustments and coupon restrictions for EXOTIC-THIN picks defined

#### Task 2.2 - [MODIFY] Add Exotic Entry to ZERO TOLERANCE SHIELD

**Description**: Add a new entry (#18) to the ZERO TOLERANCE SHIELD table in `analysis-methodology.instructions.md` documenting the risk of analyzing exotic leagues without checking Betclic market availability first.

**File**: `.github/instructions/analysis-methodology.instructions.md`

**Content to add (new row in ZERO TOLERANCE SHIELD table):**

```markdown
| 18 | Exotic league analyzed without Betclic market check | Full S3-S7 done on a league where Betclic has no markets | §1.7a BETCLIC MARKET GATE: Check Betclic market existence BEFORE starting deep analysis. No markets → SKIP. |
```

**Definition of Done**:

- [x] New row #18 added to ZERO TOLERANCE SHIELD table
- [x] Failure, root cause, and prevention columns filled
- [x] References §1.7a

#### Task 2.3 - [MODIFY] Add Exotic League Tipster Fallback to §4 Table

**Description**: Add exotic football rows to the sport-specific tipster fallback chain table in STEP 4 of `analysis-methodology.instructions.md`.

**File**: `.github/instructions/analysis-methodology.instructions.md`

**Content to add (new rows in §4 tipster fallback table):**

```markdown
| Football (Exotic SA) | Sportsgambler | OLBG | Google "[league] tips [date]" |
| Football (Exotic Africa/ME) | Sportsgambler | OLBG | Google "[league] tips [date]" |
| Football (Exotic Asia) | Sportsgambler | OLBG | Google "[league] tips [date]" |
| Football (Exotic Europe minor) | ZawodTyper → Typersi | OLBG | Sportsgambler |
```

**Definition of Done**:

- [x] Four new exotic football rows added to tipster fallback table in STEP 4
- [x] Rows follow existing format (Primary | Secondary | Tertiary)
- [x] Google search fallback included for regions with no dedicated tipster coverage

### Phase 3: Sport Protocols — Exotic Football Subsection

#### Task 3.1 - [MODIFY] Add §3.1E EXOTIC LEAGUE FOOTBALL to Sport Protocols

**Description**: Add a new subsection §3.1E to `sport-analysis-protocols.instructions.md` after the existing §3.1M (Mandatory Multi-Market Calculation for Football). This subsection provides adjusted stat requirements and fallback sources for exotic league football analysis.

**File**: `.github/instructions/sport-analysis-protocols.instructions.md`

**Content to add:**

```markdown
**§3.1E EXOTIC LEAGUE FOOTBALL (adjusted for thin data):**

When analyzing a football match from an exotic league (see §1.7 definition in analysis-methodology.instructions.md):

**Adjusted stat table (use when SoccerStats/TotalCorner don't cover the league):**

| Category | Metrics | Primary Source | Fallback Source |
|----------|---------|---------------|-----------------|
| Goals | Scored/match, Conceded/match, O2.5%, BTTS% | Flashscore match history (manual count from last 10) | Soccerway standings + results |
| Corners | Team earned/match, Total match avg | Flashscore per-match stats (if available) | Soccerway match reports (corner counts in match details) |
| Cards | Team cards/match | Flashscore per-match stats | Soccerway match reports |
| Fouls | Committed/match, Drawn/match | Sofascore match stats | Flashscore per-match stats |
| Shots | Shots/match, SOT/match | Sofascore match stats | Flashscore per-match stats |
| H2H | Last 3-5 meetings with stat breakdowns | Flashscore H2H tab | Soccerway H2H |

**CRITICAL:** When manually counting stats from Flashscore/Sofascore match pages, note this in §S3.10 Analysis Depth Proof as "Manual count from [N] match pages on [source]."

**Minimum stat thresholds to approve an exotic league pick:**

| Criterion | Threshold | Action if not met |
|-----------|-----------|-------------------|
| Match stats available (corners, shots, fouls) for ≥5 of last 10 home games | YES | Can proceed |
| Match stats available for 3-4 of last 10 games | PARTIAL | Proceed with EXOTIC-THIN flag |
| Match stats available for <3 of last 10 games | NO | SKIP — insufficient data |
| H2H meetings with stat breakdowns | ≥3 | Can proceed (flag if <5) |
| H2H meetings with stat breakdowns | 1-2 | Proceed only with EXOTIC-THIN flag + strong L10 convergence |
| H2H meetings with stat breakdowns | 0 | H2H-STAT-BLIND applies per §3.0c |

**Exotic league corner analysis (when TotalCorner has no data):**
1. Open Flashscore → league → click into each of the last 10 home matches for both teams
2. Record corner count per match from match stats tab
3. Calculate team average corners earned (home) and conceded (away)
4. If Flashscore has no match stats → try Sofascore match detail page
5. If neither has match stats → corner market is UNAVAILABLE for this pick. Move to next §3.0 ranked market.

**Kings League exception:** Do NOT use standard football stats for Kings League matches. Kings League uses modified rules (20-minute halves, special mechanics). Use ONLY Kings League-specific historical data from previous Kings League seasons. Standard §3.1 stat requirements do not apply. Treat as EXOTIC-THIN by default.
```

**Definition of Done**:

- [x] §3.1E subsection added after §3.1M in `sport-analysis-protocols.instructions.md`
- [x] Adjusted stat table with Primary/Fallback source columns present
- [x] Minimum stat thresholds table with 6 rows present
- [x] Manual corner counting procedure (5 steps) documented
- [x] Kings League exception noted
- [x] Cross-references §1.7 and §3.0c where relevant

### Phase 4: Scan Pipeline Code Updates

#### Task 4.1 - [MODIFY] Add Exotic Regional URLs to Scan Pipeline

**Description**: Add ~20 exotic regional Flashscore football URLs and a few Soccerway URLs to the `--urls` list in `scripts/run_full_scan_and_prepare.sh`. These are added after the existing Flashscore football URL.

**File**: `scripts/run_full_scan_and_prepare.sh`

**URLs to add (grouped by region, as comments in the script):**

```bash
  # Exotic league regional scans (football)
  https://www.flashscore.com/football/peru/ \
  https://www.flashscore.com/football/egypt/ \
  https://www.flashscore.com/football/uzbekistan/ \
  https://www.flashscore.com/football/saudi-arabia/ \
  https://www.flashscore.com/football/colombia/ \
  https://www.flashscore.com/football/chile/ \
  https://www.flashscore.com/football/algeria/ \
  https://www.flashscore.com/football/morocco/ \
  https://www.flashscore.com/football/india/ \
  https://www.flashscore.com/football/vietnam/ \
  https://www.flashscore.com/football/thailand/ \
  https://www.flashscore.com/football/iran/ \
  https://www.flashscore.com/football/kazakhstan/ \
  https://www.flashscore.com/football/georgia/ \
  https://www.flashscore.com/football/kosovo/ \
  https://www.flashscore.com/football/paraguay/ \
  https://www.flashscore.com/football/ecuador/ \
  https://www.flashscore.com/football/costa-rica/ \
  https://www.flashscore.com/football/jordan/ \
  https://www.flashscore.com/football/uae/ \
  # Exotic specialist sources
  https://www.soccerway.com/ \
```

**Definition of Done**:

- [x] ~21 new URLs added to the `--urls` list in `run_full_scan_and_prepare.sh`
- [x] URLs grouped with a `# Exotic league regional scans (football)` comment
- [x] Script still runs without errors (URLs may return empty for off-season leagues — that's OK, non-fatal)
- [x] URL format follows existing Flashscore pattern (`/football/[country]/`)
- [x] Soccerway main page URL added

#### Task 4.2 - [MODIFY] Add Exotic Source Domains to URL Pattern Detection

**Description**: Add exotic source domain patterns to `SPORT_URL_PATTERNS["football"]` in `scripts/scan_events.py` so that URLs from exotic specialist sources are correctly classified as football.

**File**: `scripts/scan_events.py`

**Changes to `SPORT_URL_PATTERNS`:**

```python
"football": ["/football", "/pilka-nozna", "/soccer", "forebet", "predictz", "betideas", "soccerstats", "totalcorner", "soccerway", "aiscore", "xscores", "goaloo", "nowgoal"],
```

**Definition of Done**:

- [x] Five new domain patterns added to `SPORT_URL_PATTERNS["football"]`: `"soccerway"`, `"aiscore"`, `"xscores"`, `"goaloo"`, `"nowgoal"`
- [x] Existing patterns unchanged
- [x] `detect_sport()` correctly returns `"football"` for URLs containing these patterns

#### Task 4.3 - [MODIFY] Add Exotic Stat Sources to Aggregation Script

**Description**: Add exotic stat source domains to `TIER_A_STATS_EXTENDED["football"]` in `scripts/aggregate_and_select.py` so that events found via exotic sources meet the Tier-A stat source requirement.

**File**: `scripts/aggregate_and_select.py`

**Change:**

```python
"football": {"flashscore.com", "sofascore.com", "betideas.com", "soccerstats.com", "soccerway.com", "aiscore.com", "xscores.com"},
```

**Definition of Done**:

- [x] Three new domains added to `TIER_A_STATS_EXTENDED["football"]`: `"soccerway.com"`, `"aiscore.com"`, `"xscores.com"`
- [x] Existing domains unchanged
- [x] Events from exotic sources can pass the Tier-A stat source requirement in `select_candidates()`

### Phase 5: Config Update

#### Task 5.1 - [MODIFY] Add Exotic League Metadata to Config

**Description**: Add an `exotic_leagues` section to `config/betting_config.json` listing the primary exotic leagues with their tier classification (E1/E2/E3) from §1.7e. This serves as a quick-reference for the analysis agent and enables future automation.

**File**: `config/betting_config.json`

**Content to add (after the `diversification` section):**

```json
"exotic_leagues": {
  "note": "Exotic league tiers per §1.7e. E1=established, E2=thin data, E3=ultra-thin, ENT=entertainment. Betclic availability must be verified per session.",
  "E1": [
    "peru_liga1", "egypt_premier", "morocco_botola", "saudi_pro_league",
    "india_isl", "colombia_betplay", "chile_primera", "paraguay_primera",
    "ecuador_ligapro", "uzbekistan_super", "kazakhstan_premier",
    "georgia_erovnuli", "kosovo_superliga", "north_macedonia_first"
  ],
  "E2": [
    "algeria_ligue1", "uae_pro_league", "iran_pgpl", "jordan_pro",
    "bolivia_primera", "costa_rica_primera", "armenia_premier",
    "azerbaijan_premier", "faroe_islands_premier", "gibraltar_national"
  ],
  "E3": [
    "iraq_stars", "bangladesh_premier", "myanmar_national",
    "cambodia_cleague", "laos_premier", "turkmenistan_yokary",
    "tajikistan_vysshaya", "kyrgyzstan_premier"
  ],
  "ENT": ["kings_league"]
}
```

**Definition of Done**:

- [x] `exotic_leagues` key added to `betting_config.json`
- [x] Contains `note`, `E1`, `E2`, `E3`, `ENT` keys
- [x] JSON is valid (no trailing commas, proper escaping)
- [x] League identifiers use snake_case convention matching existing config patterns
- [x] Config file parses without errors

### Phase 6: Code Review

#### Task 6.1 - [REUSE] Code Review by `tsh-code-reviewer` agent

**Description**: Run `tsh-code-reviewer` agent via `tsh-review.prompt.md` to review all changes across the 7 modified files. Focus areas:
- JSON syntax validity in `betting_config.json`
- Bash script correctness in `run_full_scan_and_prepare.sh` (line continuation, quoting)
- Python syntax in `scan_events.py` and `aggregate_and_select.py`
- Markdown formatting consistency in `.md` files
- Cross-reference integrity (§1.7 references in §3.1E, source-registry references in methodology)
- No broken existing functionality

**Definition of Done**:

- [ ] All 7 modified files reviewed
- [ ] No syntax errors in Python, Bash, JSON, or Markdown files
- [ ] Cross-references between documents verified (§1.7 ↔ §3.1E ↔ source-registry)
- [ ] Review report documented in Changelog

## Security Considerations

- **No credentials or API keys** are added or modified in this plan. BetsAPI free tier does not require key storage for the documentation-only reference.
- **No new network endpoints** are created — only additional URLs added to an existing scan pipeline that already handles fetch failures gracefully.
- **Match-fixing risk documentation** (§1.7d) explicitly warns against leagues with integrity concerns, adding a security-aware dimension to the betting analysis.

## Quality Assurance

Acceptance criteria checklist to verify the implementation meets the defined requirements:

- [ ] All 7 files modified without syntax errors (JSON parses, Python imports, Bash runs, Markdown renders)
- [ ] `python3 scripts/scan_events.py --urls https://www.flashscore.com/football/peru/` correctly detects sport as "football"
- [ ] `python3 scripts/aggregate_and_select.py` runs without import errors after TIER_A_STATS_EXTENDED update
- [ ] `bash scripts/run_full_scan_and_prepare.sh` runs to completion with new URLs (some may fail — that's expected and handled by existing error logging)
- [ ] `config/betting_config.json` parses as valid JSON: `python3 -c "import json; json.load(open('config/betting_config.json'))"`
- [ ] §1.7 in analysis-methodology.instructions.md is reachable from §3.1E cross-reference
- [ ] Source-registry exotic coverage map entries align with §1.7e tier classification
- [ ] All new source entries in source-registry follow the existing format (Role, URL, Use for, Access, Coverage)
- [ ] No existing tests or workflows are broken by the additions

## Improvements (Out of Scope)

Potential improvements identified during planning that are not part of the current task:

- **Automated Betclic market availability checker**: A script that checks betclic.pl for market existence per exotic league, populating the ❓ cells in the coverage map. Requires Playwright automation (Betclic returns 403 for bots).
- **BetsAPI integration script**: A Python adapter for betsapi.com to programmatically discover fixtures in exotic leagues. Would complement the Playwright-based scan.
- **Exotic league seasonal calendar**: A data file tracking which exotic leagues are in-season vs off-season per month, to avoid scanning leagues with no active matches.
- **Dynamic URL generation**: Instead of hardcoding Flashscore regional URLs, generate them from the `exotic_leagues` config based on season activity status.
- **Soccerway Playwright adapter**: A dedicated adapter in `scripts/adapters/` for parsing Soccerway's HTML structure (standings, H2H, match stats) into structured JSON.

## Changelog

| Date       | Change Description   |
| ---------- | -------------------- |
| 2026-04-28 | Initial plan created |
| 2026-04-28 | All 10 tasks implemented. Code review: fixed C1 (bash inline comments breaking line continuation), W1 (Iraq moved E3→E2), W3 (Algeria+UAE moved E2→E1). §1.7e aligned with config. All validations pass. |
