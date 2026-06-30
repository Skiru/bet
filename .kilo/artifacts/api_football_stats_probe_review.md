# API-Football Stats Probe & Integration Review

## 1. API-Football Client Verification
The codebase contains a full-featured API-Football Client wrapper located at `src/bet/api_clients/api_football.py`. This client extends `APISportsClient` and implements several core football-specific endpoints.

### Key Configuration
* **Base URL:** `https://v3.football.api-sports.io`
* **API Key Configured:** The key is retrieved via the environment variable `API_FOOTBALL_KEY` or from `.env` file via `get_api_key()`.
* **API Key Redaction:** Both the python tests and configuration scripts redact any raw API keys before printing or logging to comply with security guidelines.

---

## 2. Supported Endpoints & Functionality

| Endpoint | Method / Function | Purpose |
|---|---|---|
| `/teams` | `resolve_team_id(team_name)` | Searches for a team by name and returns the API team ID. Uses memory/file cache for 7 days. |
| `/fixtures` | `get_fixtures(date)` | Fetches all fixtures on a given date. Cache duration is 6 hours. |
| `/fixtures` | `get_team_last_fixtures(team_id)` | Fetches fixtures for a specific team. Cache duration is 12 hours. |
| `/fixtures/statistics` | `get_fixture_stats(fixture_id)` | Fetches team statistics for a specific fixture (e.g. shots, corners, possession). Cache duration is 168 hours (7 days). |
| `/fixtures/headtohead` | `get_h2h(team1_id, team2_id)` | Fetches historical head-to-head matches between two teams. |

---

## 3. Review of S3 Stats Integration
Currently, the pipeline step `S3` (`scripts/deep_stats_report.py` and `scripts/pipeline_steps/s3_stats.py`) does **not** call the live `APIFootballClient` directly during standard pipeline execution. Instead, it relies on:
1. **SQLite team_form tables:** Populated by upstream databases or batch scripts.
2. **Local stats_cache JSON files:** Populated under `betting/data/stats_cache/football/`.

This separation is intentional for two reasons:
- **Request Budget Safety:** Avoids burning external API requests (which are rate-limited or billed per-call) during active simulation or backtesting.
- **Reproducibility:** Ensures S3 can run purely offline using the sandboxed/replay data without needing external API credentials.

---

## 4. Shadow Client/Stats Probe Implementation
For debugging and ad-hoc verification, `scripts/probe_api_football.py` acts as a minimal shadow stats probe. It safely queries the endpoints (fixtures, statistics, and H2H) using the environment's `API_FOOTBALL_KEY` without altering any production state.
- **Budget Compliance:** Safe, rate-limited, single-call-oriented structure.
- **Fallback Recovery:** Includes support for season-based recovery when date-based queries yield no results.
