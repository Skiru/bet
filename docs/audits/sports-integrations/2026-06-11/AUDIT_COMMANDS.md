# Audit Commands

**Audit Run:** SPORTS-AUDIT-20260611T093602Z-b6a3ced  
**Generated:** 2026-06-11T10:30:00Z

---

## Baseline Commands

### cmd-001: Git status

| Field | Value |
|---|---|
| **Command ID** | cmd-001 |
| **UTC Time** | 2026-06-11T09:36:02Z |
| **Working Directory** | /Users/mkoziol/projects/bet |
| **Command** | `git status --short` |
| **Environment Vars** | None |
| **Timeout** | 10s |
| **Exit Code** | 0 |
| **Result** | M .DS_Store\n?? SPORTS_INTEGRATIONS_PORTFOLIO_AUDIT_CONTRACT.md\n?? sports-integrations-portfolio-audit-kit-v2/ |
| **Evidence IDs** | ev-baseline-001 |

---

### cmd-002: Git commit SHA

| Field | Value |
|---|---|
| **Command ID** | cmd-002 |
| **UTC Time** | 2026-06-11T09:36:02Z |
| **Working Directory** | /Users/mkoziol/projects/bet |
| **Command** | `git rev-parse --short HEAD` |
| **Environment Vars** | None |
| **Timeout** | 10s |
| **Exit Code** | 0 |
| **Result** | b6a3ced |
| **Evidence IDs** | ev-baseline-002 |

---

### cmd-003: API keys inventory

| Field | Value |
|---|---|
| **Command ID** | cmd-003 |
| **UTC Time** | 2026-06-11T09:45:00Z |
| **Working Directory** | /Users/mkoziol/projects/bet |
| **Command** | `python3 -c "import json; keys = json.load(open('config/api_keys.json')); print(list(keys.keys()))"` |
| **Environment Vars** | None |
| **Timeout** | 10s |
| **Exit Code** | 0 |
| **Result** | ['api-football', 'api-basketball', 'api-hockey', 'api-volleyball', 'football-data-org', 'thesportsdb', 'odds-api', 'serpapi', 'odds-api-io', 'brave_search'] |
| **Evidence IDs** | ev-baseline-003 |

---

## Runtime Verification Commands

### cmd-004: CLIENT_REGISTRY verification

| Field | Value |
|---|---|
| **Command ID** | cmd-004 |
| **UTC Time** | 2026-06-11T10:00:00Z |
| **Working Directory** | /Users/mkoziol/projects/bet |
| **Command** | `.venv/bin/python3 -c "from bet.api_clients import CLIENT_REGISTRY; print(sorted(CLIENT_REGISTRY.keys()))"` |
| **Environment Vars** | None |
| **Timeout** | 30s |
| **Exit Code** | 0 |
| **Result** | 26 clients registered |
| **Evidence IDs** | ev-runtime-001 |

---

### cmd-005: SCRAPER_REGISTRY verification

| Field | Value |
|---|---|
| **Command ID** | cmd-005 |
| **UTC Time** | 2026-06-11T10:00:00Z |
| **Working Directory** | /Users/mkoziol/projects/bet |
| **Command** | `.venv/bin/python3 -c "from bet.scrapers import available_scrapers; print(sorted(available_scrapers().keys()))"` |
| **Environment Vars** | None |
| **Timeout** | 30s |
| **Exit Code** | 0 |
| **Result** | 17 scrapers registered |
| **Evidence IDs** | ev-runtime-002 |

---

### cmd-006: Discovery sources verification

| Field | Value |
|---|---|
| **Command ID** | cmd-006 |
| **UTC Time** | 2026-06-11T10:00:00Z |
| **Working Directory** | /Users/mkoziol/projects/bet |
| **Command** | `.venv/bin/python3 -c "from bet.discovery.coordinator import EventDiscoveryCoordinator; sources = EventDiscoveryCoordinator._default_sources(); print([(s.name, s.supported_sports) for s in sources])"` |
| **Environment Vars** | None |
| **Timeout** | 30s |
| **Exit Code** | 0 |
| **Result** | 5 sources: odds-api-io, api-volleyball, api-hockey, odds-api, api-football |
| **Evidence IDs** | ev-runtime-003 |

---

## Deterministic Test Commands

### cmd-007: Scraper tests

| Field | Value |
|---|---|
| **Command ID** | cmd-007 |
| **UTC Time** | 2026-06-11T10:05:00Z |
| **Working Directory** | /Users/mkoziol/projects/bet |
| **Command** | `.venv/bin/python3 -m pytest tests/scrapers/ tests/discovery/ -v --tb=short` |
| **Environment Vars** | None |
| **Timeout** | 120s |
| **Exit Code** | 0 |
| **Result** | 69 passed |
| **Evidence IDs** | ev-test-001 |

---

### cmd-008: Enrichment tests

| Field | Value |
|---|---|
| **Command ID** | cmd-008 |
| **UTC Time** | 2026-06-11T10:05:00Z |
| **Working Directory** | /Users/mkoziol/projects/bet |
| **Command** | `.venv/bin/python3 -m pytest tests/test_*_enrichment.py -v --tb=short` |
| **Environment Vars** | None |
| **Timeout** | 120s |
| **Exit Code** | 0 |
| **Result** | 65 passed |
| **Evidence IDs** | ev-test-002 |

---

### cmd-009: Database tests

| Field | Value |
|---|---|
| **Command ID** | cmd-009 |
| **UTC Time** | 2026-06-11T10:05:00Z |
| **Working Directory** | /Users/mkoziol/projects/bet |
| **Command** | `.venv/bin/python3 -m pytest tests/test_db_repositories.py tests/test_stat_validation.py tests/test_fuzzy_match.py -v --tb=short` |
| **Environment Vars** | None |
| **Timeout** | 120s |
| **Exit Code** | 0 |
| **Result** | 52 passed |
| **Evidence IDs** | ev-test-003 |

---

## Live Verification Commands

### cmd-live-001: api-football

| Field | Value |
|---|---|
| **Command ID** | cmd-live-001 |
| **UTC Time** | 2026-06-11T10:10:00Z |
| **Working Directory** | /Users/mkoziol/projects/bet |
| **Command** | `.venv/bin/python3 -c "from bet.api_clients import get_client, RateLimiter; from datetime import date; rl = RateLimiter(); client = get_client('api-football', rl); fixtures = client.get_fixtures(str(date.today())); print(len(fixtures))"` |
| **Environment Vars** | API_FOOTBALL_KEY |
| **Timeout** | 30s |
| **Exit Code** | 0 |
| **Result** | 98 fixtures |
| **Evidence IDs** | ev-live-001 |

---

### cmd-live-002: api-basketball

| Field | Value |
|---|---|
| **Command ID** | cmd-live-002 |
| **UTC Time** | 2026-06-11T10:10:00Z |
| **Working Directory** | /Users/mkoziol/projects/bet |
| **Command** | `.venv/bin/python3 -c "from bet.api_clients import get_client, RateLimiter; from datetime import date; rl = RateLimiter(); client = get_client('api-basketball', rl); fixtures = client.get_fixtures(str(date.today())); print(len(fixtures))"` |
| **Environment Vars** | API_BASKETBALL_KEY |
| **Timeout** | 30s |
| **Exit Code** | 0 |
| **Result** | 31 fixtures |
| **Evidence IDs** | ev-live-002 |

---

### cmd-live-003: espn-football

| Field | Value |
|---|---|
| **Command ID** | cmd-live-003 |
| **UTC Time** | 2026-06-11T10:10:00Z |
| **Working Directory** | /Users/mkoziol/projects/bet |
| **Command** | `.venv/bin/python3 -c "from bet.api_clients import get_client, RateLimiter; rl = RateLimiter(); client = get_client('espn-football', rl); fixtures = client.get_fixtures('2026-06-11'); print(len(fixtures))"` |
| **Environment Vars** | None |
| **Timeout** | 30s |
| **Exit Code** | 0 |
| **Result** | 0 fixtures (NameError in log) |
| **Evidence IDs** | ev-live-003 |

---

### cmd-live-004: api-volleyball

| Field | Value |
|---|---|
| **Command ID** | cmd-live-004 |
| **UTC Time** | 2026-06-11T10:10:00Z |
| **Working Directory** | /Users/mkoziol/projects/bet |
| **Command** | `.venv/bin/python3 -c "from bet.api_clients import get_client, RateLimiter; from datetime import date; rl = RateLimiter(); client = get_client('api-volleyball', rl); fixtures = client.get_fixtures(str(date.today())); print(len(fixtures))"` |
| **Environment Vars** | API_VOLLEYBALL_KEY |
| **Timeout** | 30s |
| **Exit Code** | 0 |
| **Result** | 6 fixtures |
| **Evidence IDs** | ev-live-004 |

---

### cmd-live-005: api-hockey

| Field | Value |
|---|---|
| **Command ID** | cmd-live-005 |
| **UTC Time** | 2026-06-11T10:10:00Z |
| **Working Directory** | /Users/mkoziol/projects/bet |
| **Command** | `.venv/bin/python3 -c "from bet.api_clients import get_client, RateLimiter; from datetime import date; rl = RateLimiter(); client = get_client('api-hockey', rl); fixtures = client.get_fixtures(str(date.today())); print(len(fixtures))"` |
| **Environment Vars** | API_HOCKEY_KEY |
| **Timeout** | 30s |
| **Exit Code** | 0 |
| **Result** | 0 fixtures |
| **Evidence IDs** | ev-live-005 |

---

### cmd-live-006: tennis-abstract

| Field | Value |
|---|---|
| **Command ID** | cmd-live-006 |
| **UTC Time** | 2026-06-11T10:10:00Z |
| **Working Directory** | /Users/mkoziol/projects/bet |
| **Command** | `.venv/bin/python3 -c "from bet.api_clients import get_client, RateLimiter; rl = RateLimiter(); client = get_client('tennis-abstract', rl); matches = client.get_team_last_fixtures('Jannik Sinner', last_n=5); print(len(matches))"` |
| **Environment Vars** | None |
| **Timeout** | 30s |
| **Exit Code** | 0 |
| **Result** | 5 matches |
| **Evidence IDs** | ev-live-006 |

---

### cmd-live-007: opendota

| Field | Value |
|---|---|
| **Command ID** | cmd-live-007 |
| **UTC Time** | 2026-06-11T10:10:00Z |
| **Working Directory** | /Users/mkoziol/projects/bet |
| **Command** | `.venv/bin/python3 -c "from bet.api_clients.opendota import OpenDotaClient; client = OpenDotaClient(); matches = client.get_pro_matches(limit=5); print(len(matches))"` |
| **Environment Vars** | None |
| **Timeout** | 30s |
| **Exit Code** | 0 |
| **Result** | 5 matches |
| **Evidence IDs** | ev-live-007 |

---

### cmd-live-008: vlr

| Field | Value |
|---|---|
| **Command ID** | cmd-live-008 |
| **UTC Time** | 2026-06-11T10:10:00Z |
| **Working Directory** | /Users/mkoziol/projects/bet |
| **Command** | `.venv/bin/python3 -c "from bet.scrapers.vlr import VLRScraper; scraper = VLRScraper(); matches = scraper.get_upcoming_matches(); print(len(matches))"` |
| **Environment Vars** | None |
| **Timeout** | 30s |
| **Exit Code** | 0 |
| **Result** | 50 matches |
| **Evidence IDs** | ev-live-008 |

---

### cmd-live-009: sackmann ATP

| Field | Value |
|---|---|
| **Command ID** | cmd-live-009 |
| **UTC Time** | 2026-06-11T10:10:00Z |
| **Working Directory** | /Users/mkoziol/projects/bet |
| **Command** | `.venv/bin/python3 -c "from bet.scrapers.constants import SACKMANN_ATP_URL; import requests; url = SACKMANN_ATP_URL.format(year='2025'); resp = requests.head(url, timeout=10); print(resp.status_code)"` |
| **Environment Vars** | None |
| **Timeout** | 30s |
| **Exit Code** | 0 |
| **Result** | 200 |
| **Evidence IDs** | ev-live-009 |

---

## Summary

| Category | Count |
|---|---|
| Baseline Commands | 3 |
| Runtime Verification | 3 |
| Deterministic Tests | 3 |
| Live Verification | 9 |
| **Total** | 18 |
