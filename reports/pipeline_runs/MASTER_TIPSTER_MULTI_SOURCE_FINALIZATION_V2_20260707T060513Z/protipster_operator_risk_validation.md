# ProTipster Operator Risk Validation

ProTipster PL has been successfully integrated as an **Operator-Risk** public-read discovery source.

### Compliance Separation Verification
- **Compliance Tier:** Labeled strictly as `compliance_tier="operator_risk_public_read"`.
- **Evidence Use:** Labeled strictly as `evidence_use="manual_review_only_or_low_trust_context"`.
- **Promotion Allowed:** `False` (hard-coded; cannot be promoted without explicit operator confirmation).
- **AKO/Kupon Rejection:** 100% verified. Multiple AKO blocks were detected on public tip-cards and successfully rejected (0 AKO leaks into the parsed picks).
- **PT Score:** Excluded from influencing final bets and mapped purely to `source_quality` metadata under `valuable_signals`.
