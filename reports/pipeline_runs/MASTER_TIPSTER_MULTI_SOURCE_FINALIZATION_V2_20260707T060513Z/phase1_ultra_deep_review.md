# Phase 1: Ultra Deep Review of Public Main and Local Branches

## 1. What is currently public-main certified?
Only `zawodtyper` is currently certified in `origin/main` (`CERTIFIED_SHADOW_SOURCE_IDS = ("zawodtyper",)`). It is verified to be a public same-origin XHR transport with zero persistent cookies and no-cookie replay.

## 2. What is only local/unmerged evidence?
All other sources and features on the local development branches, including:
- `typersi` static table extraction (candidate for promotion).
- `sportsgambler` static article extraction (currently low-quality index-only matching).
- `protipster` public tip cards parsing (retained candidate / operator-risk).
- Any multi-source coverage or consensus calculations.

## 3. Which source-specific modules exist only locally?
- `src/bet/tipsters/typersi.py`
- `src/bet/tipsters/sportsgambler.py`
- `src/bet/tipsters/protipster.py`

## 4. Which reports are trustworthy and which require rerun?
- Previous local execution reports under `reports/pipeline_runs/` are useful historical references of local branches, but do not represent the current production main branch.
- Any live/dry-run results must be rerun on this clean branch to verify compliance, accuracy, and performance under the current state.

## 5. What ZawodTyper guarantees already exist?
- Public-XHR based transport on `https://www.zawodtyper.pl/`.
- No persistent cookies, no active login, zero spoofing of search engines.
- 100% extraction quality and compliance with absolute security guidelines.

## 6. What Typersi guarantees must be revalidated?
- Polish character preservation in BS4 table parsing.
- Safe team and event name cleaning.
- Zero bookmaker redirects or promotional leakages (e.g. Zagraj, casino/bonus blocks).
- Zero final betting fields in parsed output.

## 7. Why Sportsgambler must remain candidate unless deep-detail parser quality improves?
- Index-only header matching on `sportsgambler.com` leads to fake event extraction with low-quality reasoning or missing markets.
- Sportsgambler must only produce picks when parsing deep detail pages or complete article narrative blocks with explicit `event + market + reasoning`.
- If deep-detail parser fails semantic thresholds (e.g., event_ok >= 95%, market_ok >= 90%, reasoning_ok >= 80%), it cannot be certified and must remain a candidate.

## 8. What ProTipster public page exposes and what noise zones exist?
- **Exposed public data:** `Rodzaj zakładu` (market family), date, time, event, pick text, reference odds, and proprietary PT Score.
- **Noise zones / Blockers:** Abundant bookmaker clickouts, affiliate links, casino promotions, "Zagraj/Graj Teraz" CTAs, and AKO/combined coupon suggestions. These must be aggressively identified and rejected to protect the pipeline.

## 9. What operator-risk means and how it differs from certified shadow?
- **Certified Shadow:** Fully compliant sources matching robots.txt, having a repo-local ToS review, and integrated as trustworthy evidence in the S2-S10 pipeline.
- **Operator-Risk:** Sources that the operator manually designates for public-read discovery despite robots.txt or other blocks. 
- **Difference:** Operator-risk data is strictly labeled as `compliance_tier="operator_risk_public_read"`, `evidence_use="manual_review_only_or_low_trust_context"`, and `promotion_allowed=false`. They must never influence final betting actions or EV, nor mix with certified shadow without combined flags.

## 10. What must be true before final merge?
- All source-specific tests must pass (100% success).
- No forbidden fields (EV, stake, coupon, final bet, Superbet combined odds) are generated or passed.
- No compliance rules or security guidelines are violated (zero CAPTCHA solving, no stealth, skiru-bot UA).
- SQLite DB, logs, raw HTML, and other local-only files are excluded from commits.
