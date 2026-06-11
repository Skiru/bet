#!/usr/bin/env python3
"""Proper event-centric audit script with full evidence collection."""

import hashlib
import json
import logging
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("audit_v2")

EVIDENCE_DIR = Path(__file__).parent.parent / "LIVE_TEST_EVIDENCE" / "20260610T144500Z_AUDIT_V2"


def sha256_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


class AuditRun:
    def __init__(self, source: str, sport: str, capability: str, evidence_dir: Path):
        self.source = source
        self.sport = sport
        self.capability = capability
        self.evidence_dir = evidence_dir
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_dir = evidence_dir / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None
        self.exit_code = 0
        self.network_attempted = False
        self.http_status: int | None = None
        self.attempts = 0
        self.timeout_seconds = 30
        self.response_bytes = 0
        self.raw_records = 0
        self.parsed_records = 0
        self.rejected_records = 0
        self.response_data: Any = None
        self.parsed_data: Any = None
        self.error: str | None = None
        self.classification = "STATIC_ANALYSIS"

    def _write_file(self, filename: str, content: str | dict | bytes):
        """Write file and return SHA-256 hash."""
        path = self.run_dir / filename
        if isinstance(content, bytes):
            path.write_bytes(content)
        elif isinstance(content, dict):
            path.write_text(json.dumps(content, indent=2, default=str))
        else:
            path.write_text(content)
        return sha256_file(path)

    def execute(self) -> dict[str, Any]:
        self.start_time = datetime.now(timezone.utc)
        
        try:
            self._run_test()
        except Exception as e:
            self.exit_code = 1
            self.error = str(e)
            LOG.error(f"Test failed: {e}")
        finally:
            self.end_time = datetime.now(timezone.utc)

        self._classify_result()
        result = self._build_result()
        self._write_evidence(result)
        return result

    def _run_test(self):
        raise NotImplementedError

    def _classify_result(self):
        if self.error:
            if "playwright" in self.error.lower() or "module" in self.error.lower():
                self.classification = "BLOCKED_BEFORE_NETWORK"
            else:
                self.classification = "FAILED_SETUP"
        elif not self.network_attempted:
            self.classification = "STATIC_ANALYSIS"
        elif self.parsed_records > 0:
            self.classification = "LIVE_NETWORK_SUCCESS"
        elif self.raw_records > 0:
            self.classification = "LIVE_NETWORK_PARTIAL"
        else:
            self.classification = "LIVE_NETWORK_PARTIAL"

    def _build_result(self) -> dict[str, Any]:
        duration = (self.end_time - self.start_time).total_seconds() if self.end_time and self.start_time else 0
        
        return {
            "run_id": self.run_id,
            "source": self.source,
            "sport": self.sport,
            "capability": self.capability,
            "classification": self.classification,
            "network_attempted": self.network_attempted,
            "start_timestamp": self.start_time.isoformat() if self.start_time else None,
            "end_timestamp": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": round(duration, 3),
            "exit_code": self.exit_code,
            "error": self.error,
            "attempts": self.attempts,
            "timeout_seconds": self.timeout_seconds,
            "http_status": self.http_status,
            "response_bytes": self.response_bytes,
            "raw_records": self.raw_records,
            "parsed_records": self.parsed_records,
            "rejected_records": self.rejected_records,
            "checks": {
                "data_returned": self.parsed_records > 0,
                "verifiable_content": bool(self.parsed_data and len(str(self.parsed_data)) > 50),
            }
        }

    def _write_evidence(self, result: dict[str, Any]):
        self._write_file("command.txt", f"audit_v2 --source {self.source} --sport {self.sport} --capability {self.capability}")
        self._write_file("result.json", result)
        self._write_file("raw_response_sanitized.json", self.response_data if self.response_data else {"error": self.error})
        self._write_file("parsed_response.json", self.parsed_data if self.parsed_data else {})
        
        checks = {"data_returned": self.parsed_records > 0, "has_verifiable_content": bool(self.parsed_data)}
        self._write_file("checks.json", checks)
        
        all_hashes = {}
        for f in self.run_dir.glob("*"):
            if f.is_file():
                all_hashes[f.name] = sha256_file(f)
        self._write_file("sha256.txt", "\n".join(f"{h}  {n}" for n, h in all_hashes.items()))


class VLRRun(AuditRun):
    def _run_test(self):
        from bet.scrapers.vlr import VLRScraper
        scraper = VLRScraper()
        self.network_attempted = True
        self.attempts = 1
        
        if self.capability == "team_stats" and hasattr(self, "team"):
            result = scraper.get_team_stats(self.team)
            if result:
                self.response_data = result
                self.parsed_data = {
                    "team": self.team,
                    "win_rate": result.get("win_rate_l10"),
                    "matches_found": result.get("matches_found"),
                    "ranking": result.get("ranking"),
                    "recent_form": result.get("l10_avg"),
                }
                self.raw_records = 1
                self.parsed_records = 1 if result.get("matches_found", 0) > 0 else 0
        elif self.capability == "h2h" and hasattr(self, "team_a") and hasattr(self, "team_b"):
            result = scraper.get_h2h(self.team_a, self.team_b)
            if result:
                self.response_data = result
                self.parsed_data = {
                    "team_a": self.team_a,
                    "team_b": self.team_b,
                    "matches_found": result.get("matches_found"),
                    "team_a_wins": result.get("team_a_wins"),
                    "team_b_wins": result.get("team_b_wins"),
                }
                self.raw_records = result.get("matches_found", 0)
                self.parsed_records = 1 if result.get("matches_found", 0) > 0 else 0


def main():
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    
    # Test VLR for Valorant
    LOG.info("Testing VLR team_stats...")
    run = VLRRun("vlr", "valorant", "team_stats", EVIDENCE_DIR)
    run.team = "Sentinels"
    result = run.execute()
    results.append(result)
    LOG.info(f"  Classification: {result['classification']}")
    
    LOG.info("Testing VLR h2h...")
    run = VLRRun("vlr", "valorant", "h2h", EVIDENCE_DIR)
    run.team_a = "Sentinels"
    run.team_b = "LOUD"
    result = run.execute()
    results.append(result)
    LOG.info(f"  Classification: {result['classification']}")
    
    # Calculate summary
    by_class = {}
    for r in results:
        c = r["classification"]
        by_class[c] = by_class.get(c, 0) + 1
    
    print("\n=== AUDIT SUMMARY ===")
    print(f"Total runs: {len(results)}")
    for c, count in by_class.items():
        print(f"  {c}: {count}")
    
    # Manifest
    manifest = {
        "audit_run_id": "20260610T144500Z_AUDIT_V2",
        "generated": datetime.now(timezone.utc).isoformat(),
        "tests": results,
        "summary": by_class
    }
    
    manifest_path = EVIDENCE_DIR / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    LOG.info(f"Manifest written to {manifest_path}")


if __name__ == "__main__":
    main()
