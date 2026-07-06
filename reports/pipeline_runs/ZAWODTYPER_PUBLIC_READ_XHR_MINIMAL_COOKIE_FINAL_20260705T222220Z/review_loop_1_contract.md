# Review Loop 1 Contract

- Live artifact `live_zawodtyper_public_read_xhr.json` uses `schema_version=tipster_consensus_v2.3` and `contract=evidence_only_not_betting_decision`.
- `total_picks=14`, `sources_with_picks=1`, `coverage_status=FULL_OR_ACCEPTABLE`.
- Transport marker warnings confirm `public_xhr_transport:selected_cookie_policy=no_cookie`, `cookie_names_sent=none`, `observed_cookie_names=SRV`, `xhr_calls=2`, `observed_items=64`.
- Forbidden output fields check on the emitted live artifact found no `stake`, `coupon`, `final_bet`, `expected_value`, `superbet_combined`, `bookmaker`, or `support_link` fields.
- `pipeline_use` remains evidence-only (`s2_tipster_evidence`, `s3_context_cross_check`, `legacy_bridge_reference_only`).
- Odds remain reference-only and accuracy remains source-quality metadata only, enforced through `legacy_bridge_evidence_only`, `odds_reference_only`, and `accuracy_pct_reference_only` warnings.
- Contract verdict: PASS.
