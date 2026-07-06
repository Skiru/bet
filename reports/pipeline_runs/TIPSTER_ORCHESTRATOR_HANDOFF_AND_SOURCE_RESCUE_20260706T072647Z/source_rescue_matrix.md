# Tipster Source Certification & Rescue Matrix

This document defines the production-grade audit, compliance, and rescue status of all tipster sources in the system. To avoid amateur mistakes, no source is rejected broadly or without proof. Sources that fail live compliance checks remain active as **FIXTURE_ONLY** or **MANUAL_REVIEW** targets to preserve legacy value.

## Rescue Matrix Summary Table

| Source ID | Priority | Classification | Current Registry Status | Allowed Probe Type | Next Certification Step |
|---|---|---|---|---|---|
| **zawodtyper** | P0 | CERTIFIED_SHADOW_LIVE | shadow_live_candidate | clean_network_observation | Maintain public-XHR schema coverage |
| **sportsgambler** | P1 | LIVE_CANDIDATE_NEEDS_ROBOTS_TERMS | production_candidate | static_http_head_get | Verify robots.txt and Terms of Service |
| **forebet** | P1 | FIXTURE_ONLY_ROBOTS_OR_TERMS_BLOCKED | fixture_snapshot_only | fixture_snapshot | Maintain forebet_table offline parser |
| **predictz** | P1 | FIXTURE_ONLY_ROBOTS_OR_TERMS_BLOCKED | fixture_snapshot_only | fixture_snapshot | Maintain predictz_fixture_table offline |
| **windrawwin** | P1 | LIVE_CANDIDATE_NEEDS_ROBOTS_TERMS | production_candidate | static_http_head_get | Verify league prediction tables parser |
| **typersi** | P1 | PUBLIC_XHR_CANDIDATE_NEEDS_NETWORK_AUDIT | legacy_candidate | clean_network_observation | Audit network traffic for public API |
| **feedinco** | P2 | STATIC_HTML_CANDIDATE_NEEDS_FIXTURE_SNAPSHOTS | shadow_candidate | fixture_snapshot | Implement noise filters and date checks |
| **bettingclosed** | P2 | PUBLIC_XHR_CANDIDATE_NEEDS_NETWORK_AUDIT | shadow_candidate | clean_network_observation | Audit network traffic for public XHR |
| **sportytrader** | P2 | MANUAL_REVIEW_ONLY | research_only_next_phase | static_http_head_get | Evaluate static article parsing |
| **betmines** | P3 | MANUAL_REVIEW_ONLY | research_only | none | Maintain manual review path only |
| **pickswise** | P3 | MANUAL_REVIEW_ONLY | legacy_manual_review | none | Retain manual review only |
| **betideas** | P3 | MANUAL_REVIEW_ONLY | legacy_manual_review | none | Retain manual review only |
| **olbg** | P3 | MANUAL_REVIEW_ONLY | manual_review_only | none | Retain manual review only |
| **bettingexpert** | P3 | MANUAL_REVIEW_ONLY | manual_review_only | none | Retain manual review only |

---

## Detailed Classification Descriptions

### 1. CERTIFIED_SHADOW_LIVE
- **Definition:** Fully audited, compliant public JSON/AJAX transport verified in the codebase. Uses ephemeral technical cookies only, no login, zero stealth or bypass mechanisms.
- **Source:** `zawodtyper`

### 2. LIVE_CANDIDATE_NEEDS_ROBOTS_TERMS
- **Definition:** Clean static HTML structures that are prime candidates for live integration once a formal robots.txt and Terms of Service review is signed off.
- **Sources:** `sportsgambler`, `windrawwin`

### 3. FIXTURE_ONLY_ROBOTS_OR_TERMS_BLOCKED
- **Definition:** Sources that contain highly valuable structured data but whose robots.txt or terms prevent automated live fetching. They are preserved by running them in offline mode using static fixture HTML snapshots.
- **Sources:** `forebet`, `predictz`

### 4. PUBLIC_XHR_CANDIDATE_NEEDS_NETWORK_AUDIT
- **Definition:** Dynamic sources that fetch content via AJAX but might have public read-only APIs like ZawodTyper. They require a clean network observation audit.
- **Sources:** `typersi`, `bettingclosed`

### 5. STATIC_HTML_CANDIDATE_NEEDS_FIXTURE_SNAPSHOTS
- **Definition:** Sources with high affiliate/marketing noise that must be validated through local offline fixture snapshots before any production promotion.
- **Source:** `feedinco`

### 6. MANUAL_REVIEW_ONLY
- **Definition:** Sources with heavily dynamic JavaScript hydration, aggressive anti-bot triggers, or highly commercial redirect surfaces. These are restricted to manual expert sentiment checks only.
- **Sources:** `betmines`, `sportytrader`, `pickswise`, `betideas`, `olbg`, `bettingexpert`
