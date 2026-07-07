# Certified Shadow Runtime Validation

The `s2_tipsters_shadow_evidence.py` sidecar wrapper was executed successfully under the `LIVE_SHADOW` runtime mode.

### Validation Results
- **Picks Extracted:** 40 (25 ZawodTyper + 15 Typersi)
- **Included Sources:** `zawodtyper`, `typersi` (matching `CERTIFIED_SHADOW_SOURCE_IDS` exactly).
- **Excluded Sources:** `protipster`, `sportsgambler`, and other risk sources are strictly absent from the certified shadow output.
- **Fail-Closed Gate:** Passed. No exceptions or schema drift detected.
