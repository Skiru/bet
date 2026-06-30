# Unified Live Analyst Recommendation Quality Gate Review

## Answers to Review Questions

### 1. Why did numeric/placeholder event labels enter Top Recommendations?
- **Root Cause**: The function `_event_label(obj)` retrieves the event label from keys like `event_label`, `match`, `fixture_label`, or `name`. If these are missing or simply contain numeric IDs/generic candidate IDs (such as `"78"` or `"event_1278"`), they are returned directly. The pipeline previously lacked any validation on `event_label` to ensure it represents a complete event identity (i.e. containing non-numeric, descriptive text such as actual team names/participants, and sport/competition detail). Thus, purely numeric or candidate ID labels were promoted to Top Recommendations.

### 2. Why did no-evidence fallback text become “Why it may work”?
- **Root Cause**: In `build_ideas_from_candidate()`, `evidence_summary` defaults to a generic string (`"No exact quantitative summary available in artifacts; idea is based on event/market context only."`) when the `evidence` list is empty. Then, the field `why_it_may_work` is initialized as:
  ```python
  why_work = obj.get("why_it_may_work") or evidence_summary
  ```
  Since the source candidate object either lacked `why_it_may_work` or contained a generic fallback, this generic text bypassed validation and became the printed reason under "Why it may work" for a Top Recommendation.

### 3. Why was Confidence B allowed without real quantitative or contextual evidence?
- **Root Cause**: Confidence assignment in `assign_confidence` allowed Confidence `"B"` if `data_quality` was `"HIGH"` or `"MEDIUM"` and either `evidence_count >= 2` or `hint_score >= 2`. However, `grade_data_quality` evaluated `data_quality` as `"MEDIUM"` even with empty evidence if `has_hydrated` or `has_model_probability` were True. Also, the pipeline did not verify whether the supporting evidence itself consisted solely of duplicated or generic fallback strings. Consequently, low-quality or completely placeholder candidates were graded as `"MEDIUM"` and assigned Confidence `"B"`.

### 4. Why was UNKNOWN counter-evidence allowed in Top Recommendations?
- **Root Cause**: The counter-evidence parsing logic in `build_ideas_from_candidate()` falls back to a list containing `"UNKNOWN — no explicit counter-evidence available in source artifacts; confidence downgraded."` if no counter-evidence is provided. This generic string counts as a valid counter-evidence entry, meaning `bool(counter_list)` evaluates to `True`, which in turn allowed `assign_confidence` to award Confidence `"B"` or `"A"` without any real, non-generic counter-evidence.

### 5. What exact gate prevents this from recurring?
- **Resolution**: We are implementing three distinct, strict quality gates:
  1. **Event Identity Gate**: `is_event_identity_complete(idea) -> bool` ensures `event_label` is not empty, numeric, or a candidate ID, and contains real participants/teams plus sport and competition.
  2. **Evidence Gate**: `recommendation_has_actionable_evidence(idea) -> bool` ensures `evidence_summary` is not the generic fallback, `why_it_may_work` has at least one real source-bound reason, and `counter_evidence` contains more than just the generic `UNKNOWN` placeholder.
  3. **Confidence Gate**: Enforces that Confidence `"B"` or `"C"` cannot be awarded to any ideas that fail these gates, capping them to max `"D"` and forcing `suggested_use` to `"WATCHLIST_ONLY"`.

---

## Finding Classifications

### [P0_PLACEHOLDER_EVENT_IN_TOP_RECOMMENDATIONS] — CRITICAL
- **File**: `src/bet/pipeline/unified_live_analyst_session.py` (lines 341-350, 455)
- **Finding**: Numeric IDs/generic strings such as `"78"` were accepted as event labels without validating that they contain real team or participant names.

### [P0_NO_EVIDENCE_TOP_RECOMMENDATION] — CRITICAL
- **File**: `src/bet/pipeline/unified_live_analyst_session.py` (lines 467-469)
- **Finding**: Generic fallback text `"No exact quantitative summary available..."` was allowed to propagate into `why_it_may_work` for Top Recommendations.

### [P1_CONFIDENCE_OVERSTATED] — HIGH
- **File**: `src/bet/pipeline/unified_live_analyst_session.py` (lines 323-330, 451)
- **Finding**: Confidence B was allowed on candidates with low data quality and placeholder evidence by failing to inspect the content of the evidence.

### [P1_COUNTER_EVIDENCE_MISSING] — HIGH
- **File**: `src/bet/pipeline/unified_live_analyst_session.py` (lines 444-451)
- **Finding**: The system accepted the generic `"UNKNOWN — no explicit counter-evidence..."` fallback as positive counter-evidence for scoring and high confidence levels.

### [P1_MARKDOWN_MISSING_MATCH_CONTEXT] — HIGH
- **File**: `src/bet/pipeline/unified_live_analyst_session.py` (lines 774-792)
- **Finding**: Top Recommendations listed in markdown lacked a structured **Match Context** block containing all specific match metadata.
