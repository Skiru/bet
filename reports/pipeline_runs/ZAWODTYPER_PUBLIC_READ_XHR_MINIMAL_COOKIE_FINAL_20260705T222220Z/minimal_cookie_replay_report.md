# Minimal-Cookie Replay Report

- Variant A `no_cookie`: `200`, JSON, parse success, `71` observed items.
- Variant B `technical_only`: `200`, JSON, parse success, `71` observed items with `SRV` only.
- Variant C `technical_plus_analytics_ephemeral`: not required because a smaller working variant already succeeded.

Selection rule outcome:

- First successful variant was `no_cookie`.
- Therefore the certified transport must not send cookies.
- `SRV` remains an allowed technical cookie name observed on the public page, but it is not required for public JSON bet reads.
