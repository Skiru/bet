# Tipster Source Certification Matrix

This document tracks the certification status and next development passes for all sports-tipping sources in the registry. 

## Source Rescue Policy
> "Do not reject any source without explicit proof of compliance violation. If a source is blocked from live scraping, preserve its parser for manual review or local fixture snapshot parsing."

## Source Status & Future Passes

### 1. CERTIFIED_SHADOW_LIVE
- **Sources:** `zawodtyper`, `typersi`
- **Recommended Next Pass:** `ZAWODTYPER_TYPERSI_ORCHESTRATOR_PRODUCTION_HANDOFF`
- **Actions:** Maintain public-XHR schema coverage, verify ephemeral cookie boundaries, and audit static BS4 table parsing.

### 2. LIVE_CANDIDATE_NEEDS_ROBOTS_TERMS
- **Sources:** `sportsgambler`, `windrawwin`
- **Recommended Next Passes:**
  - `SPORTSGAMBLER_STATIC_PREVIEW_CERTIFICATION`
  - `WINDRAWWIN_STATIC_TABLE_CERTIFICATION`
- **Notes:** Sportsgambler is retained as a candidate because its deep-detail reasoning quality (72%) is below our strict 80% threshold for shadow certified promotion. Its index page picks are 100% rejected.

### 3. OPERATOR_RISK_PUBLIC_READ
- **Sources:** `protipster`
- **Recommended Next Pass:** `PROTIPSTER_OPERATOR_RISK_PUBLIC_READ_DISCOVERY`
- **Notes:** ProTipster is classified strictly as an operator-risk public-read candidate. Its public cards are extracted successfully, and all AKO combo/bonus leakages are fully rejected. No automatic shadow certification is allowed.

### 4. FIXTURE_ONLY_ROBOTS_OR_TERMS_BLOCKED
- **Sources:** `forebet`, `predictz`
- **Recommended Next Pass:** `FOREBET_PREDICTZ_FIXTURE_SNAPSHOT_MAINTENANCE`
- **Actions:** Validate the offline snapshot execution directory pipelines, maintain parsing strategies.

### 5. MANUAL_REVIEW_ONLY
- **Sources:** `betmines`, `sportytrader`, `pickswise`, `betideas`, `olbg`, `bettingexpert`
- **Recommended Next Pass:** `PICKSWISE_OLBG_BETTINGEXPERT_MANUAL_REVIEW`
- **Actions:** Keep restricted to manual/expert review context. Do not write scrapers.
