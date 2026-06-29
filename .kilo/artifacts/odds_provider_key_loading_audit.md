# Odds Provider Key Loading Precedence Audit

**Audit Date:** 2026-06-29  
**Auditor:** Kilo (gemini-3.5-flash)  
**Status:** COMPLETE  

---

## 1. Key Loading Configuration and Fallback Behaviors

We audited the key loading logic in `src/bet/discovery/sources/odds_api.py`, `src/bet/api_clients/base_client.py` (parent of `OddsAPIioClient`), and `scripts/odds_live_probe_superbet_betclic.py`/`src/bet/api_clients/oddspapi.py`.

### A. The Odds API (`odds-api`)
- **Environment Variable:** `ODDS_API_KEY`
- **Config Key (api_keys.json):** `odds-api`
- **File Fallback:** `config/odds_api_key.txt` (via line 233 of `src/bet/discovery/sources/odds_api.py`)
- **Actual Selected Source:** `config` (loaded from `config/api_keys.json`)
- **Configured Status:** `true`
- **Value Printed:** `false` (never exposed in any logs or outputs)

### B. OddsAPI.io (`odds-api-io`)
- **Environment Variable:** `ODDS_API_IO_KEY` (derived from `api_name.upper().replace("-", "_") + "_KEY"`)
- **Config Key (api_keys.json):** `odds-api-io`
- **File Fallback:** `None`
- **Actual Selected Source:** `config` (loaded from `config/api_keys.json`)
- **Configured Status:** `true`
- **Value Printed:** `false` (never exposed in any logs or outputs)

### C. OddsPapi (`odds-papi`)
- **Environment Variable:** `ODDSPAPI_API_KEY` (also check for client configuration fallback `ODDS_PAPI_KEY`)
- **Config Key (api_keys.json):** `odds-papi`
- **File Fallback:** `ABS_ODDSPAPI_KEYS_FILE` (hardcoded path `/Users/mkoziol/projects/bet/.kilo/worktrees/plume-homburg/config/api_keys.json`) in `scripts/odds_live_probe_superbet_betclic.py`
- **Actual Selected Source:** `config` (loaded from `config/api_keys.json`)
- **Configured Status:** `true`
- **Value Printed:** `false` (never exposed in any logs or outputs)

---

## 2. Environment Precedence & Overrides Classification

```python
THE_ODDS_API_ENV_OVERRIDES_UPDATED_CONFIG=true
```

### Analysis & Precedence Logic:
The adapter implementation in `src/bet/discovery/sources/odds_api.py` loads keys using the following exact priority list:
1. `os.environ.get("ODDS_API_KEY")`
2. `config/api_keys.json` containing key `"odds-api"`
3. `config/odds_api_key.txt`

If an outdated or stale key is configured in the `ODDS_API_KEY` environment variable while a fresh/refreshed key was put inside `config/api_keys.json`, the stale environment key **will override** the fresh configuration key, leading to authentication failures (e.g., HTTP 401).

### Recommendations:
1. **Explicit Precedence Warning:** Unset the environment variable `ODDS_API_KEY` in the shell or `.env` to guarantee that the system falls back to the newly provisioned key in `config/api_keys.json`.
2. **Clear Environment Check:** Add a console warning or developer log when an environment key overrides a config key, noting the source.
