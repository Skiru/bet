# Operator Risk Local JSON Template

This is a local-only file and MUST NOT be committed to git.

Path: `docs/pipeline/tipster_operator_risk.local.json`

```json
{
  "schema_version": "tipster_operator_risk_v1",
  "operator_ack": true,
  "reviewed_by": "operator:<name>",
  "reviewed_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
  "acknowledgement": "I understand this run may ignore robots.txt for public-read discovery and is not production-grade or certified.",
  "allowed_sources": {
    "windrawwin": {
      "allow_operator_risk_public_read": true,
      "max_pages": 2,
      "notes": "public pages only, no login, no bookmaker redirects"
    },
    "feedinco": {
      "allow_operator_risk_public_read": true,
      "max_pages": 2,
      "notes": "public pages only, no login, no bookmaker redirects"
    },
    "protipster": {
      "allow_operator_risk_public_read": true,
      "max_pages": 6,
      "notes": "public tip cards only, reject bonus/casino/AKO/Zagraj"
    }
  }
}
```
