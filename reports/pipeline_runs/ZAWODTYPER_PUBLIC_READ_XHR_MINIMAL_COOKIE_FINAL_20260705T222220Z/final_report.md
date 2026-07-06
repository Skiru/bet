# Final Report

## Decision

`CERTIFIED_SHADOW_LIVE_CANDIDATE_WITH_PUBLIC_READ_XHR`

## Evidence Summary

- Public daily page: `https://www.zawodtyper.pl/typy-dnia-6-lipca-poniedzialek/`
- Static HTML result before XHR transport: `0` picks, `NEEDS_PUBLIC_XHR_REVIEW`
- Observed same-origin XHR endpoint: `POST /wp-content/NP_ajax.php`
- Observed cookie names: `SRV`, `_ga`, `_ga_WQ0W4KSFWX`
- Observed auth/session/private cookie names: none
- Minimal replay result: `no_cookie` succeeds first and therefore wins
- Final live dry run: `14` picks, `14` SQLite rows, `coverage_status=FULL_OR_ACCEPTABLE`

## Why This Passes

- Public read-only XHR exists and is stable enough to replay with a plain HTTP client.
- The winning transport does not send cookies at all.
- No login, no auth/session/private cookies, no nonce/csrf, no bookmaker redirect usage, and no Playwright in production path.
- Emitted artifacts remain evidence-only and exclude forbidden bet-construction fields.

## Top 10 Sanitized Picks

1. `bouzkova vs mertens` | `1 set over 7.5 + over 20.5 gema w meczu` | `1.65`
2. `Austin FC II vs Colorado Rapids II` | `1 + Colorado Rapids II poniżej 1,5 goli` | `1.55`
3. `Pacific FC vs HFX Wanderers` | `powyżej 0,5 goli + X2` | `1.55`
4. `Meksyk vs Anglia` | `Harry Kane liczba celnych strzałów powyżej 0.5 + Anglia liczba rzutów różnych powyżej 1.5` | `1.50`
5. `Alex De Minaur vs Flavio Cobolli` | `Ilość podwójnych błędów - poniżej 10,5` | `1.65`
6. `De Minaur vs Cobolli` | `Poniżej 10.5 DF` | `1.60`
7. `Meksyk vs Anglia` | `1X - Meksyk wygra lub zremisuje mecz` | `1.55`
8. `Portugalia vs Hiszpania` | `Hiszpania +0.5 gola + Portugalia -2.5 gola + Awans Hiszpania` | `1.50`
9. `Dimitrov vs Fery` | `Dimitrov wygra 3:0` | `3.15`
10. `Anglia vs Meksyk` | `Anglia awans` | `1.71`

## Residual Notes

- Raw public XHR item counts drifted slightly during the pass because this is a live public page. The transport itself remained stable and the selected no-cookie replay kept succeeding.
- Coverage is acceptable for shadow live use because the XHR transport is active, JSON is parsed fail-closed, and emitted picks are real fixtures/markets rather than shell content or promo noise.
