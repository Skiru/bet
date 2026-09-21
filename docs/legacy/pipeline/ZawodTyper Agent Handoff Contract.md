# ZawodTyper Agent Handoff Contract

## 1. Context & Purpose
ZawodTyper is a Polish sports prediction portal. This contract defines how the autonomous public XHR NP_ajax.php transport is orchestrated, verified, and safely handed off to downstream pipeline steps without introducing any compliance risks.

## 2. Orhchestrator Execution Commands

### Running ZawodTyper Individually:
To trigger ZawodTyper crawling directly and compile the evidence handoff:
```fish
.venv-tipster-v2/bin/python scripts/pipeline_steps/s2_tipsters_v2_live_dry_run.py \
  --date 2026-07-06 \
  --terms-reviewed-json docs/pipeline/tipster_terms_review.local.json \
  --source zawodtyper \
  --max-pages-per-source 3 \
  --timeout-seconds 12 \
  --out betting/data/2026-07-06_zawodtyper.json \
  --sqlite-db betting/data/tipsters.sqlite \
  --handoff-out betting/data/2026-07-06_tipster_handoff.json
```

### Running with Certified Shadow Opt-in:
Certified shadow sources are omitted from the default core run. To include them safely:
```fish
.venv-tipster-v2/bin/python scripts/pipeline_steps/s2_tipsters_v2_live_dry_run.py \
  --date 2026-07-06 \
  --terms-reviewed-json docs/pipeline/tipster_terms_review.local.json \
  --include-certified-shadow \
  --handoff-out betting/data/2026-07-06_tipster_handoff.json
```

## 3. Strict Compliance Guardrails
- **No Playwright in Production:** Fetching uses Python's native `urllib.request` with standard cookie jars. Playwright is strictly prohibited as a production transport.
- **Zero Stealth/Bypass:** No fake headers, Cloudflare/captcha bypass, or hidden browser attributes.
- **No User cookies/Session state:** Only ephemeral, technical first-party cookies (e.g. `SRV` for server balancing) are transmitted. No WordPress login session cookies or personal user profile credentials may be stored or sent.
- **Evidence-Only:** Output picks are labeled `decision_boundary="evidence_only_not_a_bet"` and cannot under any circumstance be converted into final betting placement parameters.
