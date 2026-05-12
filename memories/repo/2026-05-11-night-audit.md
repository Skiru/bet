# 2026-05-11 Night Coupon Audit — Critical Findings

## Date: 2026-05-11

### Problem
Pipeline produced coupons with PHANTOM FIXTURES — teams appearing in multiple different matches on the same day.
Root cause: DB had 7,773 fixtures for one day (6,307 football). Scanners scraped fixtures from multiple league rounds/matchdays.

### Key Metrics
- 966 phantom fixtures detected in night window alone
- 740+ teams appeared in 2+ different matches
- v2-night coupon covered only 2 leagues (Argentina LP, Brazil) — missed CL, EL, PL, WC, La Liga, Serie A, Ligue 1, Bundesliga

### Root Cause
`build_shortlist.py` dedup only removed identical matchups (same home+away pair from different sources).
It did NOT detect when a single team appeared in multiple DIFFERENT matches — which is physically impossible.

### Fix Applied
Added phantom fixture detection pass in `build_shortlist.py` (after line 574):
1. Groups all fixtures by `sport|normalized_team_name`
2. If a team appears in >1 unique matchup, keeps only the highest-scored fixture
3. Removes the rest as phantom fixtures
4. Skips tennis (players legitimately play singles + doubles)
5. Uses shared normalization logic (suffix stripping, NFKD, etc.)

### Additional DB Observations
- `match_stats` table has 8,778 rows but NO data for Arsenal, Bayern, PSG, Chelsea, ManCity
- `h2h_stats` has 0 rows (empty)
- Enrichment yielded PARTIAL (5/10) for 100% of candidates
- All 3-Way checks showed ❌ (likely broken computation)

### Night Coupon v3 Created
- `betting/coupons/2026-05-11-night-v3.md` — rebuilt with:
  - Phantom fixtures removed (8 specific phantoms identified)
  - CL (Arsenal vs Atl.Madrid, Bayern vs PSG) added
  - EL, PL, World Cup, El Clasico added
  - Budget corrected to 23.6% (under 25% cap)
  - 22 verified picks + 6 manual-verification picks
