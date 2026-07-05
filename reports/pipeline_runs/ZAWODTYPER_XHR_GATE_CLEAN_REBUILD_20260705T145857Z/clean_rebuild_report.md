# ZawodTyper XHR Gate Clean Rebuild

Decision: NOT_PRODUCTION_GRADE_NEEDS_MANUAL_XHR_EVIDENCE

This clean branch contains only safe code/test/doc/report artifacts:
- daily URL resolver,
- false-positive filtering,
- coverage metadata,
- pre-network XHR gate,
- ZawodTyper review template with allow_public_xhr_capture=false,
- isolated tests,
- fish summary helper.

ZawodTyper is NOT a production-grade live scraper yet.
Static public HTML returns 0 picks.
XHR live is disabled.
XHR requires explicit operator evidence before any live request.
No SQLite/raw HTML/raw XHR payloads are committed.
