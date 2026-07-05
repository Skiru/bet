# Cookie Classification

- `SRV`: `ALLOWED_TECHNICAL`
  Reason: first-party server-set technical routing cookie observed on the public daily page.

- `_ga`: `ALLOWED_ANALYTICS_EPHEMERAL`
  Reason: analytics/measurement cookie created in a fresh public browser context; not an auth/session cookie.

- `_ga_WQ0W4KSFWX`: `ALLOWED_ANALYTICS_EPHEMERAL`
  Reason: analytics/measurement cookie variant created in a fresh public browser context; not an auth/session cookie.

- Observed auth/session/private/nonce/csrf cookie names: none.
- Result: no cookie name observed in the public read path required blocking the transport.
