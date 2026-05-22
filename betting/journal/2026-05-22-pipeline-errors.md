# Pipeline Errors — 2026-05-22

## Error #1: Fiorentina vs Atalanta fouls UNDER passed gate despite being a coinflip

**Symptom:** Pipeline approved Fiorentina vs Atalanta "Fouls Total U21.5" (safety 0.49, gate 11/18). User placed U24.5 at softer line — STILL LOST. The match was 1-1 (tight game = elevated tactical fouling).

**Root Cause:** Pipeline had NO mechanism to cross-check:
1. **Match closeness** (h2h odds: Fiorentina 2.75 / Draw 3.40 / Atalanta 2.55 → P(draw)=29%)
2. **Tight margin** (Combined L10 avg = 24.0 vs line = 24.5 → only 0.5 margin)
3. **Context interaction** (close game + foul/card under = dangerous because tactical fouling increases in tight matches)

The gate scored 11/18 with MULTIPLE red flags (H2H-BLIND, safety<0.60, bear≥bull, confidence 2.5) but still APPROVED mechanically.

**Fix Applied (DEFENSE IN DEPTH — 5 layers):**

### Layer 1: `compute_safety_scores.py` — Tight Margin Penalty
- Added TIGHT MARGIN PENALTY: when avg is within ±1.0 of line for foul/card markets → -0.10 safety
- For other stat markets: within ±0.5 → -0.05 safety
- Added `tight_margin` field to market results dict
- **Effect:** Fiorentina fouls would drop from 0.49 → 0.39 safety (below 0.40 = auto red flag)

### Layer 2: `context_checks.py` — Close Game Detection (S5)
- Added CLOSE GAME DETECTION: queries odds_history for draw odds
- If P(draw) ≥ 25% AND market is fouls/cards → adds `CLOSE_GAME_DANGER` flag
- Also flags corners with `CLOSE_GAME_NOTE` (less severe)
- Stores `close_game` dict on candidate for downstream use
- **Effect:** Would have printed "⚠️ Fiorentina vs Atalanta: CLOSE GAME (29% draw) + foul/card market"

### Layer 3: `upset_risk.py` — Close Game Factor (S6)
- Added Factor 4b: close_game_stat_market_danger
- When CLOSE_GAME_DANGER in context_flags OR P(draw)≥25% + foul/card under → adds risk factor
- **Effect:** Would push from ELEVATED (2 factors) to HIGH (3 factors) → explicit HIGH RISK warning

### Layer 4: `gate_checker.py` — Red Flag ZT#24 (S7)
- Added ZT#24: CLOSE GAME + foul/card UNDER + tight margin
- Checks: P(draw)≥25% + foul/card UNDER + abs(avg-line)≤1.5
- Fires red flag with specific numbers and warning about Serie A/physical leagues
- **Effect:** Would add -1.0 confidence adjustment → net confidence 1.5 → gate score drops to 10/18 or lower

### Layer 5: `sport-analysis-protocols.instructions.md` — Agent Knowledge
- Added F7 red flag: "CLOSE GAME + foul/card UNDER + tight margin → FLAG ZT#24, -1.0 safety"
- Added §3.1 market decision caveat: "When P(draw)≥25% AND foul/card UNDER AND avg±1.5 of line → DO NOT BET"
- **Effect:** Any agent running analysis will know this rule; even without script detection, the analyst agent should catch it

**NEVER REPEAT:**
- Approving foul/card UNDER when draw probability is ≥25%
- Trusting L10 averages for fouls when they're within ±1.0 of the line (coinflip territory)
- Ignoring matchup closeness when evaluating physical stat markets
- Treating Serie A tight games same as regular matches for foul counts
