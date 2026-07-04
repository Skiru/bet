# ZawodTyper Fixture Snapshot Requirements

This document defines the guidelines and format requirements for the ZawodTyper static test fixtures and snapshots.

## 1. Static HTML Fixtures
* **Format**: Standard HTML5.
* **Requirements**:
  * Must contain realistic structural card blocks using `id="match-name{ID}"` and `id="type{ID}"` inside `class="searched-in"` divs.
  * Match text must represent valid Polish diacritic team names (e.g., `Śląsk Wrocław`, `ŁKS Łódź`).
  * Must contain an accuracy or rating block with `Skuteczność: XX%` and `Kurs: X.XX` for parser verification.
* **Sanitization**: Remove all Google Analytics scripts, tracking pixels, ad scripts, cookie banners, external CDN links, and user session cookies.

## 2. XHR JSON Fixtures (NP_ajax.php)
* **Format**: Valid RFC 8259 JSON.
* **Requirements**:
  * Outer structure must be a JSON object containing `"success": true` and a `"data"` array.
  * Each item in `"data"` must have keys: `"comment_id"`, `"comment_type"`, `"match_name"`, `"content"`, `"discipline"`, `"type"`, `"rate"`, `"author_name"`, and `"author_stats"` (with keys `"bet_count"` and `"ratio"`).
  * Values must be realistic and align with the existing parser expectations (e.g., `"discipline"` value mapped via `DISCIPLINE_MAP`).
* **Sanitization**:
  * Never commit actual user cookies, authorization headers, CSRF tokens, or private session keys.
  * Anonymize tipster names where appropriate.
  * Ensure all numeric values (odds, counts) are pure reference and sanitized.
