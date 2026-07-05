# Review Loop 2 Security

- Source code grep found no `playwright_stealth`, `--disable-blink-features`, or `Cloudflare` usage in production transport.
- `bearer`, `nonce`, and `csrf` appear only inside the cookie deny-list in `src/bet/tipsters/zawodtyper.py`; this is intentional defensive logic, not transport usage.
- `stake` and `coupon` appear only in `legacy_bridge.py` forbidden-field stripping logic; they are not emitted in the live artifact.
- Artifact grep found no cookie values, no auth/session headers, and no secret material.
- `bookmaker` and `support_link` appear only in observation artifacts as raw XHR item-key evidence; they do not appear in the emitted live picks JSON.
- Security verdict: PASS.
