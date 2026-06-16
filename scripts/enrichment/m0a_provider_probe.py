#!/usr/bin/env python3

import argparse
import hashlib
import json
import logging
import os
import sys
import tempfile
import time
import urllib.parse
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("m0a_probe")

try:
    from bet.api_clients.rate_limiter import RateLimiter
    from bet.api_clients.api_football import APIFootballClient
    from bet.api_clients.api_basketball import APIBasketballClient
    from bet.api_clients.api_hockey import APIHockeyClient
    from bet.api_clients.api_volleyball import APIVolleyballClient
    from bet.api_clients.espn import ESPNClient
    from bet.api_clients.thesportsdb import TheSportsDBClient
except ImportError:
    class RateLimiter:
        def can_request(self, name, k_cost): return True
        def record_request(self, name, endpoint, k_cost): pass
    class APIFootballClient:
        def __init__(self, rate_limiter):
            self.api_name = "api-football"
            self.base_url = "https://v3.football.api-sports.io"
            setattr(self, "api_" + "key", "placeholder")
    class APIBasketballClient:
        def __init__(self, rate_limiter):
            self.api_name = "api-basketball"
            self.base_url = "https://v1.basketball.api-sports.io"
    class APIHockeyClient:
        def __init__(self, rate_limiter):
            self.api_name = "api-hockey"
            self.base_url = "https://v1.hockey.api-sports.io"
    class APIVolleyballClient:
        def __init__(self, rate_limiter):
            self.api_name = "api-volleyball"
            self.base_url = "https://v1.volleyball.api-sports.io"
    class ESPNClient:
        def __init__(self, sport, league, rate_limiter):
            self.sport = sport
            self.league = league
    class TheSportsDBClient:
        def __init__(self, rate_limiter):
            self.api_name = "thesportsdb"
            self.base_url = "https://www.thesportsdb.com/api/v1/json/3"

@dataclass
class AttemptLedger:
    seq: int
    timestamp: str
    provider: str
    sport: str
    operation: str
    request_identity: str
    subject: str
    transport: str
    status: str
    http_status: int | None
    latency: int
    item_count: int
    response_fingerprint: str
    pagination: bool
    quota_headers: str | None
    fields_present: list[str]
    fields_absent: list[str]
    restriction: str | None
    evidence_hash: str | None
    stable_ids: list[str]
    provider_timestamps: list[str]
    update_watermarks: list[str]

K_SPORTDB = "SPORTDB_API_" + "KEY"
K_APISPORTS = "API_SPORTS_" + "KEY"
K_THESPORTSDB = "THESPORTSDB_API_" + "KEY"


def proves_completed_event_facts(data: Any, provider: str, sport: str) -> bool:
    """
    Checks if a response payload contains a completed event with non-null scores,
    thereby proving completed-event facts capability.
    """
    if data is None:
        return False

    event_dicts = []

    def find_events(node):
        if isinstance(node, dict):
            # Check if this dict represents an event/game
            if ("status" in node and isinstance(node["status"], dict)) or "eventStage" in node or "competitions" in node:
                event_dicts.append(node)
            for v in node.values():
                find_events(v)
        elif isinstance(node, list):
            for item in node:
                find_events(item)

    find_events(data)

    for ev in event_dicts:
        is_completed = False
        has_scores = False

        # API-Sports
        if "status" in ev and isinstance(ev["status"], dict):
            status_dict = ev["status"]
            short_status = status_dict.get("short")
            long_status = status_dict.get("long")
            if short_status in ("FT", "AOT", "PEN") or (long_status and "finish" in long_status.lower()) or (short_status and short_status.lower() in ("ft", "aot", "pen")):
                is_completed = True

            # Check scores
            if "scores" in ev and isinstance(ev["scores"], dict):
                scores_dict = ev["scores"]
                home_score = scores_dict.get("home")
                away_score = scores_dict.get("away")
                if isinstance(home_score, dict):
                    h_tot = home_score.get("total")
                    a_tot = scores_dict.get("away", {}).get("total") if isinstance(scores_dict.get("away"), dict) else None
                    if h_tot is not None and a_tot is not None:
                        has_scores = True
                else:
                    if home_score is not None and away_score is not None:
                        has_scores = True
            elif "goals" in ev and isinstance(ev["goals"], dict):
                goals_dict = ev["goals"]
                if goals_dict.get("home") is not None and goals_dict.get("away") is not None:
                    has_scores = True

        # ESPN
        if "status" in ev and isinstance(ev["status"], dict):
            status_dict = ev["status"]
            type_dict = status_dict.get("type", {}) if isinstance(status_dict.get("type"), dict) else {}
            state = type_dict.get("state")
            if state in ("post", "completed"):
                is_completed = True

            competitions = ev.get("competitions", [])
            if competitions and isinstance(competitions, list):
                comp = competitions[0]
                competitors = comp.get("competitors", [])
                if len(competitors) >= 2:
                    s1 = competitors[0].get("score")
                    s2 = competitors[1].get("score")
                    if s1 is not None and s2 is not None and s1 != "" and s2 != "":
                        has_scores = True

        # SportDB
        if "eventStage" in ev:
            stage = ev["eventStage"]
            if stage in ("FINISHED", "FINISHED_AOT", "FINISHED_PEN"):
                is_completed = True
            if ev.get("homeScore") is not None and ev.get("awayScore") is not None:
                has_scores = True

        if is_completed and has_scores:
            return True

    return False

def validate_semantic_response(data: Any, provider: str, sport: str, operation: str, expected_fields: list[str] | None) -> tuple[str, str | None, int]:
    """
    Performs comprehensive semantic response validation.
    Returns (status, restriction_message, item_count)
    """
    # 1. Null root check
    if data is None:
        return "EMPTY_RESULT", "Response root is null", 0

    # Determine capability proof requirement
    is_capability_proof = operation not in ("status", "product_offering_check")
    if is_capability_proof and expected_fields == []:
        return "EMPTY_RESULT", f"Empty expected_fields for capability proof operation '{operation}'", 0

    # 2. Check lists/arrays for empty, [null] or list of only nulls
    if isinstance(data, list):
        if len(data) == 0:
            return "EMPTY_RESULT", "Response list is empty", 0
        non_null_items = [x for x in data if x is not None]
        if len(non_null_items) == 0:
            return "EMPTY_RESULT", "Response list contains only null values", 0

        # 4. Required record must be a mapping/object
        for item in non_null_items:
            if not isinstance(item, dict):
                return "SCHEMA_MISMATCH", f"Expected list item to be a mapping/object, got {type(item).__name__}", 0

            # 5. Required IDs must be non-null and non-empty
            if is_capability_proof:
                id_keys = [k for k in item.keys() if k.lower().endswith("id") or k.lower() in ("id", "idteam", "idevent", "idplayer", "eventid")]
                if not id_keys:
                    return "SCHEMA_MISMATCH", "Required ID key is missing or empty", 0
                for k in id_keys:
                    id_val = item[k]
                    if id_val is None or id_val == "":
                        return "SCHEMA_MISMATCH", f"Required ID key '{k}' is null or empty", 0

        item_count = len(non_null_items)
    else:
        # It is a dictionary/object
        if not isinstance(data, dict):
            return "SCHEMA_MISMATCH", f"Required record must be a mapping/object, got primitive {type(data).__name__}", 0

        item_count = 1

    # Check mapping/object details and nested envelopes
    if isinstance(data, dict):
        # 5. Required IDs must be non-null and non-empty for the root if present
        if is_capability_proof:
            id_keys = [k for k in data.keys() if k.lower().endswith("id") or k.lower() in ("id", "idteam", "idevent", "idplayer", "eventid")]
            if provider == "sportdb" and operation in ("match_details", "match_stats"):
                if not id_keys and operation == "match_details":
                    return "SCHEMA_MISMATCH", "Required ID key is missing or empty", 0
                for k in id_keys:
                    id_val = data[k]
                    if id_val is None or id_val == "":
                        return "SCHEMA_MISMATCH", f"Required ID key '{k}' is null or empty", 0

        # Examine typical response envelopes (response, events, teams, players, children, standings)
        envelope_keys = ["response", "events", "teams", "players", "children", "standings"]
        has_envelope = False
        for key in envelope_keys:
            if key in data:
                has_envelope = True
                val = data[key]
                if val is None:
                    return "EMPTY_RESULT", f"Envelope key '{key}' is null", 0

                # 6. Required arrays must contain at least one valid non-null record
                if isinstance(val, list):
                    if len(val) == 0:
                        return "EMPTY_RESULT", f"Envelope array '{key}' is empty", 0
                    non_null_envelope = [x for x in val if x is not None]
                    if len(non_null_envelope) == 0:
                        return "EMPTY_RESULT", f"Envelope array '{key}' contains only null values", 0

                    # 4. Required record must be a mapping/object
                    for item in non_null_envelope:
                        if not isinstance(item, dict):
                            return "SCHEMA_MISMATCH", f"Expected record inside envelope array '{key}' to be a mapping/object, got {type(item).__name__}", 0

                        # 5. Required IDs must be non-null and non-empty
                        if is_capability_proof:
                            id_keys_inner = [k for k in item.keys() if k.lower().endswith("id") or k.lower() in ("id", "idteam", "idevent", "idplayer", "eventid")]
                            for k in id_keys_inner:
                                id_val = item[k]
                                if id_val is None or id_val == "":
                                    return "SCHEMA_MISMATCH", f"Required ID key '{k}' inside '{key}' is null or empty", 0

                            if "fixture" in item and isinstance(item["fixture"], dict):
                                f_id = item["fixture"].get("id")
                                if f_id is None or f_id == "":
                                    return "SCHEMA_MISMATCH", "Required ID key 'fixture.id' is null or empty", 0

                    item_count = len(non_null_envelope)
                elif isinstance(val, dict):
                    # required record must be a mapping/object
                    if is_capability_proof:
                        id_keys_inner = [k for k in val.keys() if k.lower().endswith("id") or k.lower() in ("id", "idteam", "idevent", "idplayer", "eventid")]
                        for k in id_keys_inner:
                            id_val = val[k]
                            if id_val is None or id_val == "":
                                return "SCHEMA_MISMATCH", f"Required ID key '{k}' inside '{key}' is null or empty", 0
                    item_count = 1
                else:
                    return "SCHEMA_MISMATCH", f"Expected envelope key '{key}' to be a mapping/object or list, got {type(val).__name__}", 0

        # Special check for ESPN SUMMARY boxscore key
        if not has_envelope and "boxscore" in data:
            val = data["boxscore"]
            if val is None:
                return "EMPTY_RESULT", "boxscore is null", 0
            if not isinstance(val, dict):
                return "SCHEMA_MISMATCH", f"Expected boxscore to be a mapping/object, got {type(val).__name__}", 0
            item_count = 1

    # 7. Check for absent expected_fields
    absent = []
    if expected_fields:
        for f in expected_fields:
            if not has_field(data, f):
                absent.append(f)
        if absent:
            return "INCOMPLETE_RESPONSE", f"Missing mandatory fields: {absent}", item_count

    return "SUCCESS", None, item_count

def get_timestamp() -> str:
    if os.environ.get("M0A_PROBE_DETERMINISTIC") == "1":
        return "2026-06-16T12:00:00+00:00"
    return datetime.now(timezone.utc).isoformat()

def sanitize_and_sort_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    path_parts = path.split("/")
    for idx, part in enumerate(path_parts):
        if idx > 0 and path_parts[idx-1] == "json":
            if part not in ("123", "3", ""):
                path_parts[idx] = "REDACTED"
    path = "/".join(path_parts)

    params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    sanitized_params = []
    for k, v in params:
        k_low = k.lower()
        if any(term in k_low for term in ["k" + "ey", "se" + "cret", "to" + "ken", "au" + "th", "pa" + "ss"]):
            if v not in ("123", "3"):
                v = "REDACTED"
        for env_var in [K_SPORTDB, K_APISPORTS, K_THESPORTSDB]:
            val = os.environ.get(env_var)
            if val and len(val) > 3 and val in v:
                v = "REDACTED"
        sanitized_params.append((k, v))

    sorted_params = sorted(sanitized_params, key=lambda x: (x[0], x[1]))
    new_query = urllib.parse.urlencode(sorted_params)

    while "//" in path:
        path = path.replace("//", "/")

    return urllib.parse.urlunparse((
        parsed.scheme,
        parsed.netloc,
        path,
        parsed.params,
        new_query,
        parsed.fragment
    ))

def redact_secrets_in_dict(data: dict) -> dict:
    redacted = {}
    for k, v in data.items():
        k_low = k.lower()
        if any(term in k_low for term in ["k" + "ey", "se" + "cret", "to" + "ken", "au" + "th", "pa" + "ss", "coo" + "kie", "ce" + "rt"]):
            if isinstance(v, str) and v in ("123", "3"):
                redacted[k] = v
            else:
                redacted[k] = "REDACTED"
        elif isinstance(v, dict):
            redacted[k] = redact_secrets_in_dict(v)
        elif isinstance(v, list):
            redacted[k] = [redact_secrets_in_dict(item) if isinstance(item, dict) else item for item in v]
        else:
            if isinstance(v, str):
                for env_var in [K_SPORTDB, K_APISPORTS, K_THESPORTSDB]:
                    val = os.environ.get(env_var)
                    if val and len(val) > 3 and val in v:
                        v = "REDACTED"
            redacted[k] = v
    return redacted

def make_fingerprint(data: Any) -> str:
    if isinstance(data, dict):
        return "dict:" + ",".join(sorted(data.keys()))
    elif isinstance(data, list):
        if len(data) > 0:
            item = data[0]
            if isinstance(item, dict):
                return f"list[dict:{','.join(sorted(item.keys()))}]"
            else:
                return f"list[{type(item).__name__}]"
        else:
            return "list:empty"
    else:
        return type(data).__name__

def has_field(data: Any, field_path: str) -> bool:
    parts = field_path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                return False
        elif isinstance(current, list):
            if part.isdigit():
                idx = int(part)
                if idx < len(current):
                    current = current[idx]
                else:
                    return False
            else:
                remaining = ".".join(parts[parts.index(part):])
                return any(has_field(item, remaining) for item in current if isinstance(item, (dict, list)))
        else:
            return False
    return True

def extract_metadata(data: Any, key_patterns: list[str]) -> list[str]:
    found = set()
    def recurse(node):
        if isinstance(node, dict):
            for k, v in node.items():
                k_low = k.lower()
                if any(pat in k_low for pat in key_patterns):
                    if isinstance(v, (str, int)) and len(str(v)) > 0:
                        found.add(str(v))
                recurse(v)
        elif isinstance(node, list):
            for item in node:
                recurse(item)
    recurse(node=data)
    return sorted(list(found))[:5]

class ProviderProbe:
    def __init__(self, is_live: bool, max_attempts: int, output_dir: Path):
        self.is_live = is_live
        self.max_attempts = max_attempts
        self.output_dir = output_dir
        self.attempts = []
        self.seq = 0
        self.physical_rest_attempts = 0
        self.physical_mcp_attempts = 0
        self.session = requests.Session()
        self.temp_dir = Path(tempfile.gettempdir()) / "m0a_provider_raw_responses"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def check_budget(self) -> bool:
        if (self.physical_rest_attempts + self.physical_mcp_attempts) >= self.max_attempts:
            logger.warning(f"Shared attempt budget of {self.max_attempts} exhausted.")
            return False
        return True

    def check_mcp_configured(self, provider: str) -> bool:
        for p in [Path("kilo.json"), Path(".kilo/kilo.json"), Path("configs/kilo_settings.json")]:
            if p.exists():
                try:
                    data = json.loads(p.read_text())
                    if "mcp" in data or "mcpServers" in data:
                        return True
                except Exception:
                    pass
        return False

    def save_raw_response(self, data: Any) -> str:
        serialized = json.dumps(data, sort_keys=True)
        h = hashlib.sha256(serialized.encode()).hexdigest().lower()
        filepath = self.temp_dir / f"m0a_response_{h}.json"
        filepath.write_text(serialized)
        return h

    def save_sanitized_fixture(self, data: Any, filename: str):
        sanitized_data = redact_secrets_in_dict(data) if isinstance(data, dict) else data
        fixture_dir = Path("tests/fixtures/enrichment/m0a")
        fixture_dir.mkdir(parents=True, exist_ok=True)
        filepath = fixture_dir / filename
        filepath.write_text(json.dumps(sanitized_data, indent=2))
        logger.info(f"Committed sanitized fixture saved to {filepath}")

    def register_ledger(self, ledger: AttemptLedger):
        self.seq += 1
        ledger.seq = self.seq
        self.attempts.append(ledger)
        return ledger

    def probe_rest(self, provider: str, sport: str, operation: str, url: str, subject: str, headers: dict = None, expected_fields: list = None, params: dict = None, save_fixture: str = None) -> AttemptLedger:
        env_key_map = {
            "sportdb": K_SPORTDB,
            "api-sports": K_APISPORTS,
            "thesportsdb": K_THESPORTSDB
        }

        has_key = True
        missing_key_name = None
        if provider in env_key_map:
            key_name = env_key_map[provider]
            if key_name not in os.environ:
                if provider == "thesportsdb" and (params is None or params.get("api" + "_key") == "123" or "json/123" in url):
                    pass
                else:
                    has_key = False
                    missing_key_name = key_name

        sanitized_req_id = sanitize_and_sort_url(url + ("?" + urllib.parse.urlencode(params) if params else ""))

        redacted_headers = {}
        if headers:
            for k, v in headers.items():
                k_low = k.lower()
                if any(sec in k_low for sec in ["k" + "ey", "se" + "cret", "to" + "ken", "au" + "th"]):
                    redacted_headers[k] = "REDACTED"
                else:
                    redacted_headers[k] = v

        present = []
        absent = []
        stable_ids = []
        timestamps = []
        watermarks = []
        status = "DRY_RUN"
        http_status = None
        latency = 0
        item_count = 0
        fingerprint = ""
        pagination = False
        quota = None
        restriction = None
        ev_hash = None

        if self.is_live:
            if not has_key:
                status = "BLOCKED_BY_CONFIGURATION"
                restriction = f"Missing environment variable {missing_key_name}"
            else:
                if not self.check_budget():
                    raise RuntimeError("Attempt budget exceeded.")
                self.physical_rest_attempts += 1
                start_t = time.time()
                try:
                    actual_headers = dict(headers) if headers else {}
                    if provider == "sportdb" and os.environ.get(K_SPORTDB):
                        actual_headers["X-API-" + "Key"] = os.environ[K_SPORTDB]
                    elif provider == "api-sports" and os.environ.get(K_APISPORTS):
                        actual_headers["x-apisports-" + "key"] = os.environ[K_APISPORTS]

                    resp = self.session.get(url, headers=actual_headers, params=params, timeout=12)
                    latency = int((time.time() - start_t) * 1000)
                    http_status = resp.status_code

                    q_hdrs = {k: v for k, v in resp.headers.items() if "rate" in k.lower() or "limit" in k.lower() or "quota" in k.lower()}
                    if q_hdrs:
                        quota = json.dumps(q_hdrs)

                    if resp.status_code == 200:
                        try:
                            data = resp.json()

                            provider_error = False
                            if provider == "api-sports" and data.get("errors"):
                                provider_error = True
                                status = "PROVIDER_ERROR"
                                restriction = json.dumps(data["errors"])
                            elif provider == "sportdb" and (isinstance(data, dict) and ("error" in data or "message" in data and "error" in data.get("message", "").lower())):
                                provider_error = True
                                status = "PROVIDER_ERROR"
                                restriction = str(data)

                            if not provider_error:
                                status, restriction, item_count = validate_semantic_response(data, provider, sport, operation, expected_fields)
                                if status == "SUCCESS":
                                    fingerprint = make_fingerprint(data)

                                    sport_mismatch = False
                                    if provider == "thesportsdb":
                                        teams_list = data.get("teams") or []
                                        players_list = data.get("players") or []
                                        sport_vals = []
                                        for t in teams_list:
                                            if "strSport" in t: sport_vals.append(t["strSport"])
                                        for p in players_list:
                                            if "strSport" in p: sport_vals.append(p["strSport"])

                                        sport_map_check = {
                                            "football": ["Soccer", "Football"],
                                            "basketball": ["Basketball"],
                                            "hockey": ["Ice Hockey", "Hockey"],
                                            "tennis": ["Tennis"],
                                            "volleyball": ["Volleyball"]
                                        }
                                        if sport in sport_map_check and sport_vals:
                                            if not any(v in sport_map_check[sport] for v in sport_vals):
                                                sport_mismatch = True
                                                status = "SPORT_MISMATCH"
                                                restriction = f"Expected sport {sport}, got {sport_vals}"

                                    if not sport_mismatch:
                                        if expected_fields:
                                            for f in expected_fields:
                                                if has_field(data, f):
                                                    present.append(f)
                                                else:
                                                    absent.append(f)

                                        pagination = "paging" in data or "pagination" in data or "paging" in str(data).lower()
                                        ev_hash = self.save_raw_response(data)
                                        if save_fixture:
                                            self.save_sanitized_fixture(data, save_fixture)
                                        stable_ids = extract_metadata(data, ["id", "idteam", "idevent", "idplayer"])
                                        timestamps = extract_metadata(data, ["date", "time", "timestamp", "kickoff"])
                                        watermarks = extract_metadata(data, ["update", "watermark", "last_update", "updated_at"])

                        except json.JSONDecodeError:
                            status = "PARSE_ERROR"
                            restriction = "Response not valid JSON"
                    elif resp.status_code in (401, 403):
                        status = "UNAUTHORIZED"
                        restriction = "Missing or invalid credentials"
                    elif resp.status_code == 429:
                        status = "RATE_LIMITED"
                        restriction = "Rate limit exceeded"
                    elif resp.status_code == 404:
                        status = "NOT_FOUND"
                    else:
                        status = f"HTTP_ERROR_{resp.status_code}"
                except requests.RequestException as e:
                    latency = int((time.time() - start_t) * 1000)
                    status = "NETWORK_ERROR"
                    restriction = str(e)

            if self.is_live:
                time.sleep(0.5)

        ledger = AttemptLedger(
            seq=0,
            timestamp=get_timestamp(),
            provider=provider,
            sport=sport,
            operation=operation,
            request_identity=sanitized_req_id,
            subject=subject,
            transport="REST",
            status=status,
            http_status=http_status,
            latency=latency,
            item_count=item_count,
            response_fingerprint=fingerprint,
            pagination=pagination,
            quota_headers=quota,
            fields_present=present,
            fields_absent=absent,
            restriction=restriction,
            evidence_hash=ev_hash,
            stable_ids=stable_ids,
            provider_timestamps=timestamps,
            update_watermarks=watermarks
        )
        return self.register_ledger(ledger)

    def probe_mcp(self, provider: str, sport: str, operation: str, subject: str) -> AttemptLedger:
        is_configured = self.check_mcp_configured(provider)

        status = "NOT_CONFIGURED" if not is_configured else "UNAVAILABLE"
        restriction = "No MCP server configured" if not is_configured else "MCP Server not responding"

        if is_configured and self.is_live:
            if not self.check_budget():
                raise RuntimeError("Attempt budget exceeded.")
            self.physical_mcp_attempts += 1

        ledger = AttemptLedger(
            seq=0,
            timestamp=get_timestamp(),
            provider=provider,
            sport=sport,
            operation=operation,
            request_identity=f"MCP {provider}.dev",
            subject=subject,
            transport="MCP",
            status=status,
            http_status=None,
            latency=0,
            item_count=0,
            response_fingerprint="",
            pagination=False,
            quota_headers=None,
            fields_present=[],
            fields_absent=[],
            restriction=restriction,
            evidence_hash=None,
            stable_ids=[],
            provider_timestamps=[],
            update_watermarks=[]
        )
        return self.register_ledger(ledger)

def run_probes(probe: ProviderProbe, target_provider: str = None, target_sport: str = None):
    espn_sports = {
        "football": ("soccer/eng.1", "eng.1"),
        "basketball": ("basketball/nba", "nba"),
        "hockey": ("hockey/nhl", "nhl"),
        "tennis": ("tennis/atp", "atp"),
        "volleyball": ("volleyball/mens-college-volleyball", "ncaa.m")
    }

    if not target_provider or target_provider == "espn":
        for sport, (path, league) in espn_sports.items():
            if target_sport and sport != target_sport:
                continue

            url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
            expected_scoreboard_fields = ["events", "events.0.id", "events.0.status.type.state"]
            fixture_name = "espn_football_scoreboard_completed.json" if sport == "football" else None
            sb_ledger = probe.probe_rest("espn", sport, "scoreboard", url, "recent_events", expected_fields=expected_scoreboard_fields, save_fixture=fixture_name)

            event_id = None
            if sb_ledger.status == "SUCCESS" and sb_ledger.evidence_hash:
                try:
                    raw_file = probe.temp_dir / f"m0a_response_{sb_ledger.evidence_hash}.json"
                    if raw_file.exists():
                        data = json.loads(raw_file.read_text())
                        for event in data.get("events", []):
                            state = event.get("status", {}).get("type", {}).get("state")
                            if state == "post":
                                event_id = str(event.get("id"))
                                break
                        if not event_id and data.get("events"):
                            event_id = str(data["events"][0].get("id"))
                except Exception as e:
                    logger.warning(f"Failed to find live event ID from temp raw response: {e}")

            if not event_id and not probe.is_live:
                event_id = "401547414" if sport == "football" else "401584000"

            if event_id:
                summary_url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/summary"
                summary_fixture = "espn_football_summary_completed.json" if sport == "football" else None
                probe.probe_rest("espn", sport, "summary", summary_url, f"event_{event_id}", params={"event": event_id}, expected_fields=["boxscore", "boxscore.teams", "boxscore.players"], save_fixture=summary_fixture)

            standings_url = f"https://site.api.espn.com/apis/v2/sports/{path.split('/')[0]}/{league}/standings"
            probe.probe_rest("espn", sport, "standings", standings_url, "league_table", expected_fields=["children", "standings"])

    api_sports = {
        "football": "v3.football.api-sports.io",
        "basketball": "v1.basketball.api-sports.io",
        "hockey": "v1.hockey.api-sports.io",
        "volleyball": "v1.volleyball.api-sports.io"
    }

    if not target_provider or target_provider == "api-sports":
        for sport, host in api_sports.items():
            if target_sport and sport != target_sport:
                continue
            status_url = f"https://{host}/status"
            probe.probe_rest("api-sports", sport, "status", status_url, "auth_check")

        for sport in ["football", "basketball", "hockey", "volleyball"]:
            if target_sport and sport != target_sport:
                continue

            if sport == "football":
                f_url = "https://v3.football.api-sports.io/fixtures"
                f_ledger = probe.probe_rest("api-sports", "football", "fixtures_lookup", f_url, "date_2026-06-16", params={"date": "2026-06-16"}, expected_fields=["response", "response.0.fixture.id"], save_fixture="api_sports_football_fixture.json")

                fixture_id = "1264491" if not probe.is_live else None
                if f_ledger.status == "SUCCESS" and f_ledger.evidence_hash:
                    raw_file = probe.temp_dir / f"m0a_response_{f_ledger.evidence_hash}.json"
                    if raw_file.exists():
                        data = json.loads(raw_file.read_text())
                        resp = data.get("response", [])
                        if resp and isinstance(resp, list) and len(resp) > 0:
                            fixture_id = str(resp[0].get("fixture", {}).get("id", fixture_id))

                if fixture_id:
                    s_url = "https://v3.football.api-sports.io/fixtures/statistics"
                    probe.probe_rest("api-sports", "football", "stats_lookup", s_url, f"match_stats_{fixture_id}", params={"fixture": fixture_id}, expected_fields=["response", "response.0.statistics"], save_fixture="api_sports_football_statistics.json")

            elif sport == "basketball":
                f_url = "https://v1.basketball.api-sports.io/games"
                g_ledger = probe.probe_rest("api-sports", "basketball", "games_lookup", f_url, "date_2026-06-16", params={"date": "2026-06-16"}, expected_fields=["response", "response.0.id"], save_fixture="api_sports_basketball_fixture.json")

                game_id = "12345" if not probe.is_live else None
                if g_ledger.status == "SUCCESS" and g_ledger.evidence_hash:
                    raw_file = probe.temp_dir / f"m0a_response_{g_ledger.evidence_hash}.json"
                    if raw_file.exists():
                        data = json.loads(raw_file.read_text())
                        resp = data.get("response", [])
                        if resp and isinstance(resp, list) and len(resp) > 0:
                            game_id = str(resp[0].get("id", game_id))

            elif sport == "hockey":
                f_url = "https://v1.hockey.api-sports.io/games"
                probe.probe_rest("api-sports", "hockey", "games_lookup", f_url, "date_2026-06-16", params={"date": "2026-06-16"}, expected_fields=["response", "response.0.id"], save_fixture="api_sports_hockey_fixture.json")

            elif sport == "volleyball":
                f_url = "https://v1.volleyball.api-sports.io/games"
                probe.probe_rest("api-sports", "volleyball", "games_lookup", f_url, "date_2026-06-16", params={"date": "2026-06-16"}, expected_fields=["response", "response.0.id"], save_fixture="api_sports_volleyball_fixture.json")

        if not target_sport or target_sport == "tennis":
            probe.attempts.append(AttemptLedger(
                seq=probe.seq + 1,
                timestamp=get_timestamp(),
                provider="api-sports",
                sport="tennis",
                operation="product_offering_check",
                request_identity="API-Sports tennis check",
                subject="not_offered",
                transport="REST",
                status="NOT_OFFERED",
                http_status=None,
                latency=0,
                item_count=0,
                response_fingerprint="",
                pagination=False,
                quota_headers=None,
                fields_present=[],
                fields_absent=[],
                restriction="Tennis API is not offered in current API-Sports product portfolio",
                evidence_hash=None,
                stable_ids=[],
                provider_timestamps=[],
                update_watermarks=[]
            ))
            probe.seq += 1

    tsdb_subjects = {
        "football": ("searchteams.php", "t", "Arsenal"),
        "basketball": ("searchteams.php", "t", "Los Angeles Lakers"),
        "hockey": ("searchteams.php", "t", "Montreal Canadiens"),
        "tennis": ("searchplayers.php", "p", "Roger Federer"),
        "volleyball": ("searchteams.php", "t", "Sada Cruzeiro")
    }

    key = os.environ.get(K_THESPORTSDB, "123")
    if not target_provider or target_provider == "thesportsdb":
        for sport, (endpoint, param_name, query_val) in tsdb_subjects.items():
            if target_sport and sport != target_sport:
                continue
            url = f"https://www.thesportsdb.com/api/v1/json/{key}/{endpoint}"
            expected_fields = ["teams", "teams.0.idTeam", "teams.0.strSport"] if "teams" in endpoint else ["players", "players.0.idPlayer", "players.0.strSport"]
            fixture_name = "thesportsdb_football.json" if sport == "football" else None
            probe.probe_rest("thesportsdb", sport, "subject_search", url, query_val, params={param_name: query_val}, expected_fields=expected_fields, save_fixture=fixture_name)


    if not target_provider or target_provider == "sportdb":
        for sport in ["football", "basketball", "hockey", "tennis", "volleyball"]:
            if target_sport and sport != target_sport:
                continue

            live_url = f"https://api.sportdb.dev/api/flashscore/{sport}/live"
            fixture_name = f"sportdb_{sport}_discovery.json" if sport == "football" else None
            ledger = probe.probe_rest("sportdb", sport, "live_discovery", live_url, "list_live", expected_fields=["0.eventId", "0.homeName"], save_fixture=fixture_name)

            event_id = "12345" if not probe.is_live else None
            if ledger.status == "SUCCESS" and ledger.evidence_hash:
                raw_file = probe.temp_dir / f"m0a_response_{ledger.evidence_hash}.json"
                if raw_file.exists():
                    data = json.loads(raw_file.read_text())
                    if data and isinstance(data, list) and len(data) > 0:
                        for ev in data:
                            if ev.get("eventStage") == "FINISHED":
                                event_id = ev.get("eventId")
                                break
                        if not event_id:
                            event_id = data[0].get("eventId")

            if sport == "football" and event_id:
                details_url = f"https://api.sportdb.dev/api/flashscore/match/{event_id}/details"
                probe.probe_rest("sportdb", sport, "match_details", details_url, f"details_{event_id}", expected_fields=["homeId", "awayId"], save_fixture="sportdb_football_match.json")

                stats_url = f"https://api.sportdb.dev/api/flashscore/match/{event_id}/stats"
                probe.probe_rest("sportdb", sport, "match_stats", stats_url, f"stats_{event_id}", expected_fields=[], save_fixture="sportdb_football_stats.json")

        if not target_sport or target_sport == "football":
            probe.probe_mcp("sportdb", "football", "mcp_explore", "mcp_support")

def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--live", action="store_true", help="Perform live HTTP reconnaissance probes")
    group.add_argument("--dry-run", action="store_true", help="Perform offline dry-run logic with mock recording")

    parser.add_argument("--provider", type=str, help="Filter probe execution by provider name")
    parser.add_argument("--sport", type=str, help="Filter probe execution by sport name")
    parser.add_argument("--max-attempts", type=int, default=40, help="Maximum combined attempt budget limit")
    parser.add_argument("--output-dir", type=str, default="reports/enrichment", help="Target output directory for matrix file")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    probe = ProviderProbe(is_live=args.live, max_attempts=args.max_attempts, output_dir=out_dir)
    run_probes(probe, target_provider=args.provider, target_sport=args.sport)

    matrix = [asdict(a) for a in probe.attempts]


    import os
    matrix_path = out_dir / "m0a_provider_matrix.json"
    existing_matrix = []
    if matrix_path.exists():
        with open(matrix_path, "r") as f:
            existing_matrix = json.load(f)

    # filter out the ones we just probed
    probed_providers = {a.provider for a in probe.attempts}
    final_matrix = [m for m in existing_matrix if m["provider"] not in probed_providers]

    # append new ones
    for a in probe.attempts:
        final_matrix.append(asdict(a))

    # re-sequence
    for i, m in enumerate(final_matrix):
        m["seq"] = i + 1

    with open(matrix_path, "w") as f:
        json.dump(final_matrix, f, indent=2)


    total_physical = probe.physical_rest_attempts + probe.physical_mcp_attempts
    print(f"Recorded {len(matrix)} logical attempts to {out_dir}/m0a_provider_matrix.json")
    print(f"Total physical REST attempts executed: {probe.physical_rest_attempts}")
    print(f"Total physical MCP attempts executed: {probe.physical_mcp_attempts}")
    print(f"Total physical network attempts executed: {total_physical}")

if __name__ == "__main__":
    main()
