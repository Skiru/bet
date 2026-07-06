# Tipster Source Certification Matrix

This document tracks the certification status and next development passes for all sports-tipping sources in the registry. 

## Source Rescue Policy
> "Do not reject any source without explicit proof of compliance violation. If a source is blocked from live scraping, preserve its parser for manual review or local fixture snapshot parsing."

## Source Status & Future Passes

### 1. CERTIFIED_SHADOW_LIVE
- **Source:** `zawodtyper`
- **Recommended Next Pass:** `ZAWODTYPER_ORCHESTRATOR_PRODUCTION_HANDOFF`
- **Actions:** Maintain public-XHR schema coverage, verify ephemeral cookie boundaries.

### 2. LIVE_CANDIDATE_NEEDS_ROBOTS_TERMS
- **Sources:** `sportsgambler`, `windrawwin`
- **Recommended Next Passes:**
  - `SPORTSGAMBLER_STATIC_PREVIEW_CERTIFICATION`
  - `WINDRAWWIN_STATIC_TABLE_CERTIFICATION`
- **Actions:** Formal robots.txt check, Terms of Service legality verify, test live GET probes.

### 3. PUBLIC_XHR_CANDIDATE_NEEDS_NETWORK_AUDIT
- **Sources:** `typersi`, `bettingclosed`
- **Recommended Next Passes:**
  - `TYPERSI_PUBLIC_READ_AUDIT`
  - `FEEDINCO_SHADOW_NOISE_FILTER_AUDIT`
  - `BETTINGCLOSED_JS_PUBLIC_AUDIT`
- **Actions:** Perform clean, no-stealth network XHR trace to identify public read APIs similar to ZawodTyper.

### 4. FIXTURE_ONLY_ROBOTS_OR_TERMS_BLOCKED
- **Sources:** `forebet`, `predictz`
- **Recommended Next Pass:** `FOREBET_PREDICTZ_FIXTURE_SNAPSHOT_MAINTENANCE`
- **Actions:** Validate the offline snapshot execution directory pipelines, maintain parsing strategies.

### 5. MANUAL_REVIEW_ONLY
- **Sources:** `betmines`, `sportytrader`, `pickswise`, `betideas`, `olbg`, `bettingexpert`
- **Recommended Next Pass:** `PICKSWISE_OLBG_BETTINGEXPERT_MANUAL_REVIEW`
- **Actions:** Keep restricted to manual/expert review context. Do not write scrapers.
