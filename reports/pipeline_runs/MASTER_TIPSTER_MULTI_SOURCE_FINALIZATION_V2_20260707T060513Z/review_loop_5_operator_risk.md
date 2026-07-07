# Review Loop 5 — Operator Risk Mode

## Key Audit Points
- **Local JSON Authorization:** Enforced strictly. If the flag `--allow-operator-risk-public-read` is provided without a valid local JSON file via `--operator-risk-json`, the dry-run script fails closed.
- **Unlisted Source Safety:** Sources not listed or list-approved in the operator-risk JSON are skipped automatically.
- **Separation of Risk Records:** All operator-risk picks are tagged with `compliance_tier="operator_risk_public_read"`, `evidence_use="manual_review_only_or_low_trust_context"`, and `promotion_allowed=false`.
- **Accidental Certified Shadow Prevention:** Operator-risk sources are strictly blocked from entering `CERTIFIED_SHADOW_SOURCE_IDS` or being marked as certified shadow.
- **Outcome:** PASS.
