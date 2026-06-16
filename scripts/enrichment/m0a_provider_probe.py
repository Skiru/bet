#!/usr/bin/env python3
"""M0A Provider Probe - live reconnaissance of sports data providers."""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("m0a_probe")

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

class ProviderProbe:
    def __init__(self, is_live: bool, max_attempts: int, output_dir: Path):
        self.is_live = is_live
        self.max_attempts = max_attempts
        self.output_dir = output_dir
        self.attempts = []
        self.seq = 0
        self.session = requests.Session()

    def check_budget(self) -> bool:
        if self.seq >= self.max_attempts:
            logger.warning("Max attempts budget reached.")
            return False
        return True

    def redact_url(self, url: str) -> str:
        for env_var in ["SPORTDB_API_KEY", "API_SPORTS_KEY", "THESPORTSDB_API_KEY"]:
            val = os.environ.get(env_var)
            if val and val in url:
                url = url.replace(val, "***REDACTED***")
        return url

    def redact_headers(self, headers: dict) -> dict:
        redacted = dict(headers)
        for k in ["x-apisports-key", "x-rapidapi-key", "authorization"]:
            for key in redacted.keys():
                if key.lower() == k:
                    redacted[key] = "***REDACTED***"
        return redacted

    def probe(self, provider: str, sport: str, operation: str, url: str, subject: str, headers: dict = None, expected_fields: list = None) -> AttemptLedger:
        if not self.check_budget():
            return None

        self.seq += 1
        headers = headers or {}

        redacted_url = self.redact_url(url)
        req_identity = f"GET {redacted_url}"

        logger.info(f"[{self.seq}/{self.max_attempts}] {provider} {sport} {operation}: {req_identity}")

        start_t = time.time()
        status = "DRY_RUN"
        http_status = None
        item_count = 0
        fingerprint = ""
        pagination = False
        quota = None
        present = []
        absent = []
        restriction = None
        ev_hash = None

        if self.is_live:
            try:
                resp = self.session.get(url, headers=headers, timeout=10)
                latency = int((time.time() - start_t) * 1000)
                http_status = resp.status_code

                # Check quota headers
                q_headers = {k: v for k, v in resp.headers.items() if "rate" in k.lower() or "limit" in k.lower()}
                if q_headers:
                    quota = json.dumps(q_headers)

                if resp.status_code == 200:
                    status = "SUCCESS"
                    try:
                        data = resp.json()
                        fingerprint = str(type(data).__name__)
                        if isinstance(data, dict):
                            fingerprint += " " + ",".join(sorted(data.keys())[:5])
                            if "response" in data and isinstance(data["response"], list):
                                item_count = len(data["response"])
                            elif "events" in data and isinstance(data["events"], list):
                                item_count = len(data["events"])
                            elif "teams" in data and isinstance(data["teams"], list):
                                item_count = len(data["teams"])

                            pagination = "paging" in data or "pagination" in data
                        elif isinstance(data, list):
                            item_count = len(data)

                        if expected_fields and isinstance(data, dict):
                            # simple top-level or single-level check
                            flat = json.dumps(data)
                            for f in expected_fields:
                                if f in flat:
                                    present.append(f)
                                else:
                                    absent.append(f)

                        # Save evidence to temp
                        ev_data = json.dumps(data)
                        ev_hash = hashlib.sha256(ev_data.encode()).hexdigest()[:8]
                        # Don't actually write evidence file as per rules unless required, but we must not commit it.
                        ev_path = self.output_dir / f"ev_{self.seq}_{ev_hash}.json"
                        ev_path.write_text(ev_data)

                    except json.JSONDecodeError:
                        status = "PARSE_ERROR"
                        restriction = "Response not JSON"
                elif resp.status_code in (401, 403):
                    status = "UNAUTHORIZED"
                    restriction = "Missing or invalid credentials"
                    latency = int((time.time() - start_t) * 1000)
                elif resp.status_code == 429:
                    status = "RATE_LIMITED"
                    restriction = "Rate limit exceeded"
                    latency = int((time.time() - start_t) * 1000)
                else:
                    status = f"HTTP_ERROR_{resp.status_code}"
                    latency = int((time.time() - start_t) * 1000)

            except requests.RequestException as e:
                latency = int((time.time() - start_t) * 1000)
                status = "NETWORK_ERROR"
                restriction = str(e)
        else:
            latency = 0

        # Pacing
        if self.is_live:
            time.sleep(0.5)

        ledger = AttemptLedger(
            seq=self.seq,
            timestamp=datetime.now(timezone.utc).isoformat(),
            provider=provider,
            sport=sport,
            operation=operation,
            request_identity=req_identity,
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
            evidence_hash=ev_hash
        )
        self.attempts.append(ledger)
        return ledger

def run_probes(probe: ProviderProbe, target_provider: str = None, target_sport: str = None):
    # ESPN (Free, no auth)
    espn_sports = {
        "football": "soccer/eng.1",
        "basketball": "basketball/nba",
        "hockey": "hockey/nhl",
        "tennis": "tennis/atp",
        "volleyball": "volleyball/mens-college-volleyball"
    }
    if not target_provider or target_provider == "espn":
        for sport, path in espn_sports.items():
            if target_sport and sport != target_sport: continue
            url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
            probe.probe("espn", sport, "scoreboard", url, "recent_events")

    # API-Sports (Requires Key)
    api_sports = {
        "football": "v3.football.api-sports.io",
        "basketball": "v1.basketball.api-sports.io",
        "hockey": "v1.hockey.api-sports.io",
        "tennis": "v1.tennis.api-sports.io",
        "volleyball": "v1.volleyball.api-sports.io"
    }
    key = os.environ.get("API_SPORTS_KEY", "dummy")
    if not target_provider or target_provider == "api-sports":
        for sport, host in api_sports.items():
            if target_sport and sport != target_sport: continue
            url = f"https://{host}/status"
            probe.probe("api-sports", sport, "status", url, "system_status", headers={"x-apisports-key": key})

    # TheSportsDB (Free Tier is '3')
    tsdb_sports = {
        "football": "Soccer",
        "basketball": "Basketball",
        "hockey": "Ice Hockey",
        "tennis": "Tennis",
        "volleyball": "Volleyball"
    }
    key = os.environ.get("THESPORTSDB_API_KEY", "3")
    if not target_provider or target_provider == "thesportsdb":
        for sport, sname in tsdb_sports.items():
            if target_sport and sport != target_sport: continue
            url = f"https://www.thesportsdb.com/api/v1/json/{key}/searchteams.php?t=Arsenal"
            probe.probe("thesportsdb", sport, "team_search", url, "Arsenal")

    # SportDB.dev
    key = os.environ.get("SPORTDB_API_KEY", "dummy")
    if not target_provider or target_provider == "sportdb":
        for sport in ["football", "basketball", "hockey", "tennis", "volleyball"]:
            if target_sport and sport != target_sport: continue
            url = f"https://api.sportdb.dev/v1/{sport}/matches?date=2026-06-10"
            probe.probe("sportdb", sport, "matches", url, "recent_matches", headers={"Authorization": f"Bearer {key}"})

    # MCP explicitly asked to be noted
    if not target_provider or target_provider == "sportdb":
        if target_sport is None or target_sport == "football":
            probe.attempts.append(AttemptLedger(
                seq=probe.seq + 1,
                timestamp=datetime.now(timezone.utc).isoformat(),
                provider="sportdb",
                sport="football",
                operation="mcp_explore",
                request_identity="MCP sportdb.dev",
                subject="mcp_support",
                transport="MCP",
                status="UNAVAILABLE",
                http_status=None,
                latency=0,
                item_count=0,
                response_fingerprint="",
                pagination=False,
                quota_headers=None,
                fields_present=[],
                fields_absent=[],
                restriction="No MCP server configured in kilo.json",
                evidence_hash=None
            ))
            probe.seq += 1

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--provider", type=str)
    parser.add_argument("--sport", type=str)
    parser.add_argument("--max-attempts", type=int, default=50)
    parser.add_argument("--output-dir", type=str, default="reports/enrichment")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Store evidence in temp
    tmp_dir = Path("/tmp/m0a_evidence")
    tmp_dir.mkdir(exist_ok=True)

    probe = ProviderProbe(is_live=args.live, max_attempts=args.max_attempts, output_dir=tmp_dir)
    run_probes(probe, target_provider=args.provider, target_sport=args.sport)

    matrix = [asdict(a) for a in probe.attempts]

    with open(out_dir / "m0a_provider_matrix.json", "w") as f:
        json.dump(matrix, f, indent=2)

    print(f"Recorded {len(matrix)} attempts to {out_dir}/m0a_provider_matrix.json")

if __name__ == "__main__":
    main()
