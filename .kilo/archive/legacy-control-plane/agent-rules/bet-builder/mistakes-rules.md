# Betting Mistakes — Builder Reference

## ⛔ HARD RULES (check every coupon leg)

1. **CORRELATION_001 (CRITICAL):** MAX 1 coupon per unique pick. NEVER repeat same bet across multiple coupons. If a pick fails, it kills EVERY coupon it's in.
2. **TENNIS_SETS_001:** O3.5 sets needs: ranking ≤15 gap + competitive H2H + <60% straight-set.
3. **TENNIS_GAMES_001:** Underdog games Over: gap <50 + hold >50% + odds ≤2.00.
4. **HANDBALL_001:** Handball ML only at implied ≥70% (odds ≤1.43). NEVER same handball pick in 2+ coupons. Prefer totals/HC.
5. **GOALS_001:** Combined L5 > line + 0.5. Below → UNDER or skip.
6. **UNDER_GOALS_001:** U2.5 forbidden: team needs win + L5 > 2.5 + odds ≥2.00.
7. **LOWER_LEAGUE_001:** No ML below 3rd tier in AKO.
8. **SOT_001:** Combined L5 SOT > line + 1.5.
9. **CORNERS_CONTEXT_001:** Dead rubber → subtract 2.5.
10. **BTTS_CONTEXT_001:** Relegation = NO BTTS. Never BTTS live at 0-0 30'+ in tight match.
11. **SAFETY_FLOOR_001:** Below threshold (config/betting_config.json) → Extended Pool only.

## Coupon Validation Checklist
- [ ] No event appears in >1 core coupon
- [ ] No same-match legs in any coupon
- [ ] Same-sport ≤2 legs per coupon
- [ ] Combined odds arithmetic shown (multiply explicitly)
- [ ] All Polish descriptions match Betclic terminology
- [ ] Full team names with competition
- [ ] Stakes within limits (LR ≤3.00, HR ≤2.00 PLN)
- [ ] P(coupon) calculated
- [ ] Weakest leg identified
- [ ] Catastrophe scenario written

## Team Identity Check (MANDATORY post-build)
For EACH pick: verify the team described IS the team in the event.
Check: home/away not swapped? Player games not confused between P1/P2?

## Hallucination Check (MANDATORY post-build)
For EACH stat cited: trace back to actual source (DB/JSON).
L10_avg=87.7 does NOT mean "hits O87.5 every game" — count actual values above line.
