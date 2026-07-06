# Phase 5 — Match Resolution & Event Identity Readiness

This report details the sport-aware participant identity and match resolution logic implemented to eliminate ambiguity and prevent duplicate or misaligned fixtures.

## 1. Split and Order-Insensitive Keys
To guarantee that `Meksyk vs Anglia` and `Anglia vs Meksyk` resolve to the same underlying event:
1.  **Sport-Aware Participant Splitting**: Splits event names into independent clean team/player tokens using known separators (`vs`, `v`, `-`, `–`, `—`).
2.  **Double-Barreled Tennis Names**: Recognizes single hyphenated player names (e.g. `Jean-Julien Rojer`) and avoids splitting them when `vs` or space-surrounded dashes are present as main separators.
3.  **Order-Insensitive Joining**: Sorts the normalized ASCII-folded tokens alphabetically and joins them with `|` to form the canonical `normalized_event_key`.
    *   `Meksyk vs Anglia` $\rightarrow$ `anglia|meksyk`
    *   `Anglia vs Meksyk` $\rightarrow$ `anglia|meksyk`
4.  **Ambiguity Flagging**: Adds `order_reversed` to `ambiguity_flags` if the raw event order differs from the canonical alphabetical order. This serves as an early warning for downstream mapping algorithms.

## 2. Reserve / Roman Numeral Preservation
Special squad distinctions must never be stripped because team "II", "U21", or "Women" represent completely different sporting contests than their first-team or men's counterparts.
*   The `clean_team_name` logic explicitly targets only *betting noise* and *market suffixes* (like `[1X]`, `[O2.5]`).
*   Roman numerals like `II` and squad tags are fully preserved (e.g., `Austin FC II` and `Colorado Rapids II` remain exactly as named), ensuring zero identity collisions with senior teams.

## 3. Ambiguity and Resolution Gates
If an event name does not conform to a binary participant split (e.g. "SingleTeamNoSeparator" or promotional text):
*   `requires_match_resolution` is set to `True`.
*   `ambiguity_flags` registers `ambiguous_split`.
*   `agent_use_decision` shifts to `NEEDS_MATCH_ID_RESOLUTION` (blocking auto-use) or `REJECT_GARBAGE`.
