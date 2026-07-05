# Phase 1 Repo Review

- Daily URL resolver exists in `src/bet/tipsters/zawodtyper.py` as `build_zawodtyper_daily_url(date)` and correctly resolves `https://www.zawodtyper.pl/typy-dnia-6-lipca-poniedzialek/` for the current pass date.
- Static HTML still returns `0` picks with `NEEDS_PUBLIC_XHR_REVIEW` on the live daily page. Verified by fetching the public HTML and running `extract_zawodtyper` against the raw page snapshot.
- Observed XHR endpoint is `POST /wp-content/NP_ajax.php` on the same origin.
- Observed cookie names are `SRV`, `_ga`, `_ga_WQ0W4KSFWX`.
- Auth/session/private cookie names observed: none.
- Analytics cookie names observed: `_ga`, `_ga_WQ0W4KSFWX`.
- `_ga` and `_ga_*` must not block public read-only scraping because they are analytics/measurement cookies, not auth/session identity cookies. They are relevant only as a possible last-resort ephemeral fallback, not as a hard blocker.
- Before this pass, production live dry-run only fetched public HTML through `fetch_public_html` and could parse JSON only if some other transport already supplied it. There was no public same-origin NP_ajax transport in the live runner.
- Minimal code change required: fetch the public daily page first, derive `post_id` from public HTML, replay same-origin `api_get_bets_by_post_id` JSON with reviewed payload keys, keep a fresh in-memory cookie jar only for observation, reject blocked/unknown cookie names, default to the smallest certified cookie policy, and feed the combined JSON back into the existing parser bridge.
