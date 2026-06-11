#!/usr/bin/env python3
"""Non-destructive audit harness for aggregation and enrichment testing.

Usage:
    python3 scripts/audit_harness.py --source hltv --sport cs2 --capability team_stats
    python3 scripts/audit_harness.py --source vlr --sport valorant --capability h2h --team-a "Sentinels" --team-b "LOUD"
    python3 scripts/audit_harness.py --source opendota --sport dota2 --capability team_stats --team "Team Spirit"
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

LOG = logging.getLogger("audit_harness")
LOG.setLevel(logging.INFO)


class AuditRun:
    def __init__(
        self,
        source: str,
        sport: str,
        capability: str,
        evidence_dir: Path,
        event_or_date: str | None = None,
        team_a: str | None = None,
        team_b: str | None = None,
        team: str | None = None,
        timeout: int = 30,
    ):
        self.source = source
        self.sport = sport
        self.capability = capability
        self.event_or_date = event_or_date
        self.team_a = team_a
        self.team_b = team_b
        self.team = team
        self.timeout = timeout
        self.evidence_dir = evidence_dir
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None
        self.exit_code = 0
        self.http_statuses: list[int] = []
        self.attempts = 0
        self.raw_records = 0
        self.parsed_records = 0
        self.rejected_records = 0
        self.response_data: Any = None
        self.error: str | None = None
        self.response_hash: str | None = None

    def execute(self) -> dict[str, Any]:
        self.start_time = datetime.now(timezone.utc)
        try:
            self.response_data = self._run_test()
            self.parsed_records = self._count_records()
        except Exception as e:
            self.exit_code = 1
            self.error = str(e)
            LOG.error(f"Test failed: {e}")
        finally:
            self.end_time = datetime.now(timezone.utc)
        
        return self._build_result()

    def _run_test(self) -> Any:
        if self.source == "hltv":
            return self._test_hltv()
        elif self.source == "vlr":
            return self._test_vlr()
        elif self.source == "opendota":
            return self._test_opendota()
        elif self.source == "sackmann_adapter":
            return self._test_sackmann()
        elif self.source == "espn":
            return self._test_espn()
        elif self.source == "flashscore":
            return self._test_flashscore()
        else:
            raise ValueError(f"Unknown source: {self.source}")

    def _test_hltv(self) -> Any:
        from bet.scrapers.hltv import HLTVScraper
        scraper = HLTVScraper()
        self.attempts = 1
        
        if self.capability == "team_stats" and self.team:
            result = scraper.get_team_stats(self.team)
            if result:
                self.raw_records = 1
                self.parsed_records = 1
            return result
        elif self.capability == "h2h" and self.team_a and self.team_b:
            result = scraper.get_h2h(self.team_a, self.team_b)
            if result:
                self.raw_records = result.get("matches_found", 0)
                self.parsed_records = self.raw_records
            return result
        elif self.capability == "upcoming":
            result = scraper.get_upcoming_matches(days=3)
            self.raw_records = len(result) if result else 0
            self.parsed_records = self.raw_records
            return result
        else:
            raise ValueError(f"Unknown capability: {self.capability}")

    def _test_vlr(self) -> Any:
        from bet.scrapers.vlr import VLRScraper
        scraper = VLRScraper()
        self.attempts = 1
        
        if self.capability == "team_stats" and self.team:
            result = scraper.get_team_stats(self.team)
            if result:
                self.raw_records = 1
                self.parsed_records = 1
            return result
        elif self.capability == "h2h" and self.team_a and self.team_b:
            result = scraper.get_h2h(self.team_a, self.team_b)
            if result:
                self.raw_records = result.get("matches_found", 0)
                self.parsed_records = self.raw_records
            return result
        elif self.capability == "upcoming":
            result = scraper.get_upcoming_matches(days=3)
            self.raw_records = len(result) if result else 0
            self.parsed_records = self.raw_records
            return result
        else:
            raise ValueError(f"Unknown capability: {self.capability}")

    def _test_opendota(self) -> Any:
        from bet.api_clients.opendota import OpenDotaClient
        client = OpenDotaClient()
        self.attempts = 1
        
        if self.capability == "team_stats" and self.team:
            result = client.get_team_stats(self.team)
            if result and result.get("matches_found", 0) > 0:
                self.raw_records = 1
                self.parsed_records = 1
            return result
        else:
            raise ValueError(f"Unknown capability: {self.capability}")

    def _test_sackmann(self) -> Any:
        from bet.api_clients.sackmann_adapter import SackmannClient
        from bet.api_clients.rate_limiter import RateLimiter
        client = SackmannClient(rate_limiter=RateLimiter())
        self.attempts = 1
        
        if self.capability == "player_stats" and self.team:
            result = client.get_player_season_stats(self.team)
            if result:
                self.raw_records = 1
                self.parsed_records = 1
            return result
        else:
            raise ValueError(f"Unknown capability: {self.capability}")

    def _test_espn(self) -> Any:
        from bet.api_clients.espn import ESPNClient
        client = ESPNClient()
        self.attempts = 1
        
        if self.capability == "schedule" and self.sport:
            result = client.get_schedule(self.sport)
            self.raw_records = len(result) if result else 0
            self.parsed_records = self.raw_records
            return result
        elif self.capability == "team_stats" and self.team:
            result = client.get_team_stats(self.sport, self.team)
            if result:
                self.raw_records = 1
                self.parsed_records = 1
            return result
        else:
            raise ValueError(f"Unknown capability: {self.capability}")

    def _test_flashscore(self) -> Any:
        from bet.scrapers.flashscore import FlashscoreScraper
        scraper = FlashscoreScraper()
        self.attempts = 1
        
        if self.capability == "upcoming" and self.sport:
            cls_map = {
                "football": "FootballFlashscoreScraper",
                "basketball": "BasketballFlashscoreScraper",
                "tennis": "TennisFlashscoreScraper",
                "hockey": "HockeyFlashscoreScraper",
                "volleyball": "VolleyballFlashscoreScraper",
            }
            if self.sport not in cls_map:
                raise ValueError(f"Flashscore not supported for sport: {self.sport}")
            result = scraper.get_upcoming_matches(self.sport)
            self.raw_records = len(result) if result else 0
            self.parsed_records = self.raw_records
            return result
        else:
            raise ValueError(f"Unknown capability: {self.capability}")

    def _count_records(self) -> int:
        if isinstance(self.response_data, list):
            return len(self.response_data)
        elif isinstance(self.response_data, dict):
            return self.raw_records
        return 1

    def _build_result(self) -> dict[str, Any]:
        duration = (self.end_time - self.start_time).total_seconds() if self.end_time and self.start_time else 0
        
        response_str = json.dumps(self.response_data, default=str) if self.response_data else ""
        self.response_hash = hashlib.sha256(response_str.encode()).hexdigest()[:16] if response_str else None
        
        result = {
            "run_id": self.run_id,
            "source": self.source,
            "sport": self.sport,
            "capability": self.capability,
            "event_or_date": self.event_or_date,
            "team_a": self.team_a,
            "team_b": self.team_b,
            "team": self.team,
            "command": f"python3 scripts/audit_harness.py --source {self.source} --sport {self.sport} --capability {self.capability}",
            "start_timestamp": self.start_time.isoformat() if self.start_time else None,
            "end_timestamp": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": round(duration, 3),
            "exit_code": self.exit_code,
            "http_statuses": self.http_statuses,
            "attempts": self.attempts,
            "timeout_config_seconds": self.timeout,
            "raw_records": self.raw_records,
            "parsed_records": self.parsed_records,
            "rejected_records": self.rejected_records,
            "response_hash_sha256": self.response_hash,
            "evidence_type": "LIVE_NETWORK" if self.attempts > 0 else "STATIC_ANALYSIS",
            "conclusion": "PASS" if self.exit_code == 0 and self.parsed_records > 0 else "FAIL" if self.exit_code != 0 else "PARTIAL",
            "error": self.error,
        }
        
        return result

    def save_evidence(self, result: dict[str, Any]) -> Path:
        run_dir = self.evidence_dir / self.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        
        with open(run_dir / "result.json", "w") as f:
            json.dump(result, f, indent=2, default=str)
        
        with open(run_dir / "response.json", "w") as f:
            json.dump(self.response_data if self.response_data else {"error": self.error}, f, indent=2, default=str)
        
        return run_dir


def main():
    parser = argparse.ArgumentParser(description="Audit harness for integration testing")
    parser.add_argument("--source", required=True, help="Source name (e.g., hltv, vlr, opendota)")
    parser.add_argument("--sport", required=True, help="Sport name (e.g., cs2, valorant, dota2)")
    parser.add_argument("--capability", required=True, help="Capability to test (e.g., team_stats, h2h, upcoming)")
    parser.add_argument("--event-or-date", help="Event ID or date to test")
    parser.add_argument("--team", help="Team/player name for stats")
    parser.add_argument("--team-a", help="Team A for H2H")
    parser.add_argument("--team-b", help="Team B for H2H")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout in seconds")
    parser.add_argument("--evidence-dir", type=Path, help="Evidence directory")
    
    args = parser.parse_args()
    
    evidence_dir = args.evidence_dir or Path(__file__).parent.parent / "LIVE_TEST_EVIDENCE" / "20260610T135421Z_ACTUAL_AUDIT"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    run = AuditRun(
        source=args.source,
        sport=args.sport,
        capability=args.capability,
        evidence_dir=evidence_dir,
        event_or_date=args.event_or_date,
        team_a=args.team_a,
        team_b=args.team_b,
        team=args.team,
        timeout=args.timeout,
    )
    
    result = run.execute()
    evidence_path = run.save_evidence(result)
    
    print(json.dumps(result, indent=2, default=str))
    print(f"\nEvidence saved to: {evidence_path}")
    
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
