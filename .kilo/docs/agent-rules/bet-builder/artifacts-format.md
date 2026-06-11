# Artifacts Format — Builder Reference

## Coupon File Structure (`betting/coupons/YYYY-MM-DD.md`)
1. **H1 Header** — date, bankroll, budget + conditional notice
2. **PEŁNA MATRYCA RYNKÓW** — top 30-50 sorted by safety desc
   Columns: # | Sport | Event | Market | Odds | Safety | Hit% | Direction | Uwagi
3. **Per-type coupon tables** — LOW-RISK, MULTI-SPORT, HIGHER-RISK, NIGHT
   Columns: # | Coupon ID | Co obstawić | Kurs | Stawka | Zwrot
4. **COMBINATION MENU** — 4-8 COMBO- prefixed coupons (reuse allowed)
5. **ROZSZERZONY WYBÓR** — Extended Pool with bull/bear cases
6. **Per-coupon reasoning** — logic + P(coupon) + risk + tipster insight
7. **PODSUMOWANIE** — Wydatek, Bankroll po, Łączny pot. zwrot, Stan konta, Scenariusze
8. **KOLEJNOŚĆ STAWIANIA** — placement priority
9. **LISTA OBSERWACYJNA** — backup picks with promotion criteria
10. **ODRZUCONE** — near-misses grouped by rejection category

## Portfolio Rules
- UNIQUE EVENT PER COUPON (core). Combo menu may reuse.
- Min 2 legs per coupon. Max same-sport: 2 per coupon.
- Target: ≥5 core + ≥4 combo coupons. Scale with approved picks.
- Coupon limits: LR max 3.00 PLN, HR max 2.00 PLN.
- Total suggested stakes WILL exceed budget — user picks favorites.

## Polish Market Translations
- Over X.5 corners → Powyżej X.5 rzutów rożnych
- Over X.5 goals → Powyżej X.5 bramek
- Under X.5 goals → Poniżej X.5 bramek
- Over X.5 cards → Powyżej X.5 kartek
- BTTS Yes → Obie drużyny strzelą - Tak
- Team wins → Zwycięstwo [Team]
- Double chance 1X → Podwójna szansa 1X
- Over X.5 total games → Powyżej X.5 gemów łącznie
- Total sets Over 3.5 → Łączna liczba setów powyżej 3.5

## IDs
- Pick: PK-YYYYMMDD-## (unique per version)
- Coupon: CP-YYYYMMDD-{LR|HR|MS|N}{#}v{version}
- risk_level: low-risk | higher-risk
- Statuses: pending, placed, win, loss, push, void, half_win, half_loss, superseded

## Full Names (MANDATORY)
"RB Leipzig (Bundesliga)", "Jiri Lehecka vs Alejandro Tabilo (ATP Madrid R1)"

## Stress Test (per coupon)
1. P(coupon) = multiply leg probabilities. <10% → HR only. <5% → split.
2. Weakest leg — can it be swapped without correlation?
3. Catastrophe sentence: "This fails if [specific scenario]."
4. Betclic market existence verified for every leg.
