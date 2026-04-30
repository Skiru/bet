# v7 Pipeline State — 2026-04-29

## Completed Steps
- **S1 Master Events**: ✅ Created `betting/data/20260429_s1_master_events.md`
  - 595+ events across 13/14 sports (Padel = 0 today)
  - All 14 sports scanned, cross-validated
  - 12 phantoms detected and removed (6 overnight NBA/NHL, 3 ZT wrong-opponent, cycling, padel, unverified tennis)
  
- **S2 Shortlist**: ✅ Created `betting/data/20260429_s2_shortlist.md`
  - 35 candidates across 10 sports
  - KEY sports: 74% (Football 14, Tennis 6, Basketball 4, Volleyball 2)
  - SUPPORT: Hockey 3, Snooker 2, Handball 1, Esports 1, Speedway 1, Baseball 1
  - All fixture-verified ✅
  - 20+ tipster-backed entries included

## v7 Known-Failure Mitigations Applied
- v5 phantoms (overnight NBA/NHL) → all detected via Odds-API cross-check
- v3 ZT statistical picks → all included
- v4 Finnish football fouls → flagged "NOT fouls" on Inter Turku
- v3 Snooker Betclic line mismatch → flagged for S3 verification

## Pending Steps
- S3: Deep statistical analysis (§3.0 multi-market calculation per candidate)
- S4-S10: Full pipeline

## Key Data Files
- Old v1 files preserved as: `20260429_s1_master_events_v1.md`, `20260429_s2_shortlist_v1.md`
