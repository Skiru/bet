# M0A_TRADITIONAL_SPORTS_PROVIDER_REALITY_MAP

This document outlines the final provider decisions, live-proven evidence, and capability matrix for our sports enrichment pipeline, correcting and clarifying all supplement evaluations.

---

## 1. Core Definitions & Status Taxonomy

To preserve pipeline integrity, all provider capabilities are strictly classified using the following taxonomy:

*   **Authenticated**: Access credentials have been verified and validated.
*   **Discovered**: Basic event listing, lookup, or discovery operations have returned successful payloads.
*   **Completed-Event Proven**: Payloads physically contain at least one completed event with non-null scores.
*   **Detailed-Stats Proven**: Payloads physically contain granular field-level or team-level match statistics.
*   **Documented but Untested**: Capability is referenced in public developer documentation but has not been verified in any supplement run.
*   **Empty Result**: API returned a valid JSON envelope, but the payload list or stats field was empty or comprised only of `null` values.
*   **Unproven**: Insufficient or no physical evidence exists to verify capability.
*   **Candidate Role**: Potential future role pending canonical-event matching or higher-tier subscription certification.
*   **Accepted Production Role**: Explicitly certified role for production implementation.

---

## 2. Corrected Provider Capability Decisions

### 2.1 SportDB.database Decisions
*   **Multisport Live Discovery**: **PROVEN**. (Active endpoints return event lists for football, basketball, hockey, tennis, and volleyball).
*   **Football Basic Match Identity**: **PARTIALLY_PROVEN**. (Match details endpoint returns home/away identifiers, but relies on Flashscore IDs).
*   **Football Match Statistics**: **UNPROVEN / EMPTY_RESULT**.
    *   *Correction*: The committed `sportdb_football_stats.json` containing `[null]` does not represent valid statistics and is classified as `EMPTY_RESULT`.
*   **Football Production Fallback**: **NOT_APPROVED**. (The `/api/flashscore/...` routes are classified as an undocumented bridge relative to the public REST contract and are not certified for core fallback).
*   **Other-Sport Deep Statistics**: **UNPROVEN**.
*   **Strategic Disposition**: **DEFERRED** (not marked as REJECTED). SportDB is retained as a future candidate for documented capabilities:
    *   Player profile
    *   Player statistics
    *   Player transfer history
    *   Club players
    *   Lineups
    *   Competition and tournament context
    *   Agent research

### 2.2 API-Sports Decisions
API-Sports is certified as highly predictable with structured JSON payloads, stable IDs, and pagination.

*   **Football**:
    *   Discovery: **PROVEN / PRIMARY**
    *   Completed-Event Facts: **PROVEN / PRIMARY**
    *   Team Match Statistics: **PROVEN / PRIMARY**
    *   Standings: **UNPROVEN** in this supplement (no standings request was performed; prior plan restriction claims are removed as unsupported).
    *   Lineups: **UNPROVEN**
    *   Player Fixture Statistics: **UNPROVEN**
    *   Injuries: **UNPROVEN**
    *   Transfers: **UNPROVEN**
*   **Basketball**:
    *   Discovery/Game Response: **PROVEN**
    *   Completed Event: **PROVEN** (only when a completed status e.g., "FT" and non-null scores are present in the committed response).
    *   Team/Player Deep Statistics: **UNPROVEN**
    *   Standings: **UNPROVEN**
*   **Hockey**:
    *   Discovery/Game Response: **PROVEN**
    *   Completed Event: **PROVEN** (only when a completed status and non-null scores are present, e.g., "AOT").
    *   Team/Player Deep Statistics: **UNPROVEN**
    *   Standings: **UNPROVEN**
*   **Volleyball**:
    *   Discovery/Upcoming Event Identity: **PROVEN**
    *   Completed Event Facts: **UNPROVEN** (the committed event `api_sports_volleyball_fixture.json` is "Not Started" with null scores).
    *   Deep Statistics: **UNPROVEN**
*   **Tennis**:
    *   **NOT_OFFERED** by API-Sports.

### 2.3 ESPN Decisions
*   **Football Classification**: **CANDIDATE_SHADOW**
    *   *Constraint*: ESPN must not be upgraded to an operational SHADOW until a later same-canonical-event comparison proves compatible mappings across:
        *   Event mapping
        *   Team mapping
        *   Kickoff compatibility
        *   Home/Away compatibility
        *   Result compatibility
        *   Field-level statistics compatibility

### 2.4 TheSportsDB Decisions
*   **Football Team Identity & External-ID Crosswalk**: **PROVEN** (cross-walk references observed).
*   **Other-Sport External-ID Crosswalk**: **UNPROVEN**.

---

## 3. Accepted Football Production Roles (First-Slice Decision)

1.  **API-Sports**: **PRIMARY** for completed team match facts.
2.  **ESPN**: **CANDIDATE_SHADOW**, to be certified later against the same canonical events.
3.  **TheSportsDB**: **IDENTITY_ONLY** for the proven football external-ID crosswalk.
4.  **SportDB.dev**: **DEFERRED** for the first match-fact slice and retained as a high-value candidate for player, transfer, lineup, and tournament context.

---

## 4. Logical & Physical Summary Counts

*   **Total Attempt Registry Count**: 38 logical attempts.
*   **Total Physical REST Network Attempts in Supplement**: 16 (0 in this closure phase).
*   **Total Physical MCP Network Attempts in Supplement**: 0.
*   **Zero-Network Guard**: Verified that no external HTTP requests were performed during this integrity closure phase.
