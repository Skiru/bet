"""Tests for source_health module."""
import json
import tempfile
from pathlib import Path

import pytest
from scripts.source_health import (
    sanitize_csv_field,
    extract_domain,
    detect_sport_from_url,
    parse_scan_results,
    DOMAIN_TO_SOURCE,
)


class TestSanitizeCsvField:
    def test_normal_text_unchanged(self):
        assert sanitize_csv_field("hello") == "hello"
        assert sanitize_csv_field("BetExplorer") == "BetExplorer"

    def test_escapes_formula_injection(self):
        assert sanitize_csv_field("=CMD()") == "'=CMD()"
        assert sanitize_csv_field("+calc") == "'+calc"
        assert sanitize_csv_field("-1+1") == "'-1+1"
        assert sanitize_csv_field("@SUM(A1)") == "'@SUM(A1)"

    def test_empty_string(self):
        assert sanitize_csv_field("") == ""


class TestExtractDomain:
    def test_full_url(self):
        assert extract_domain("https://www.betexplorer.com/foo") == "betexplorer.com"

    def test_strips_www(self):
        assert extract_domain("https://www.flashscore.com/path") == "flashscore.com"

    def test_no_www(self):
        assert extract_domain("https://espn.com/nba") == "espn.com"


class TestDetectSportFromUrl:
    def test_football(self):
        assert detect_sport_from_url("https://betexplorer.com/soccer/england/") == "football"
        assert detect_sport_from_url("https://example.com/pilka-nozna/") == "football"

    def test_tennis(self):
        assert detect_sport_from_url("https://betexplorer.com/tennis/atp/") == "tennis"

    def test_nba(self):
        assert detect_sport_from_url("https://espn.com/nba/odds") == "basketball"

    def test_unknown(self):
        assert detect_sport_from_url("https://example.com/xyz/") == "unknown"


class TestParseScanResults:
    def test_parses_summary_dict_format(self, tmp_path):
        summary = {
            "https://betexplorer.com/soccer/england/": [{"event": "a"}, {"event": "b"}],
            "https://betexplorer.com/tennis/atp/": [{"event": "c"}],
        }
        summary_path = tmp_path / "summary.json"
        summary_path.write_text(json.dumps(summary))
        errors_path = tmp_path / "errors.json"

        records = parse_scan_results(summary_path, errors_path)
        assert len(records) == 2
        assert all(r["status"] == "ok" for r in records)
        # Verify sanitization applied
        for r in records:
            assert not r["source_name"].startswith("=")

    def test_parses_errors(self, tmp_path):
        summary_path = tmp_path / "summary.json"
        errors = [{"url": "https://flashscore.com/match/xyz", "error": "Timeout"}]
        errors_path = tmp_path / "errors.json"
        errors_path.write_text(json.dumps(errors))

        records = parse_scan_results(summary_path, errors_path)
        assert len(records) == 1
        assert records[0]["status"] == "fail"
        assert records[0]["source_name"] == "Flashscore"

    def test_missing_files_returns_empty(self, tmp_path):
        records = parse_scan_results(tmp_path / "nope.json", tmp_path / "nope2.json")
        assert records == []
