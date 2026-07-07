# Combined Certified and Operator Risk Run Validation

A combined run was executed successfully using the `--combine-certified-and-risk` option.

### Verification Highlights
- **Total Picks:** 65 (40 certified, 25 operator risk).
- **Handoff Classification:** The handoff object correctly marked mixed events with `source_risk_mix="mixed"`.
- **Quality Downgrading:** Mixed events were prevented from having high `evidence_quality` solely because of ProTipster's presence.
- **Safety:** Certified and operator-risk sources remain completely separable under the `source_ids`, `certified_sources`, and `operator_risk_sources` arrays.
- **No Forbidden Actions:** Checked and confirmed. Zero EV/stake/coupon/final bet/combined odds fields are present.
