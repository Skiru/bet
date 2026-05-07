"""Integration test for parallel sport scanner dispatch."""
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
ROOT_DIR = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(ROOT_DIR / "src"))


@pytest.fixture
def mock_db(tmp_path, monkeypatch):
    """Set up test DB and patch get_db to use it."""
    from bet.db.schema import SCHEMA_SQL

    db_path = tmp_path / "test.db"

    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.close()

    # Patch get_db to use our test DB path
    from contextlib import contextmanager

    @contextmanager
    def _mock_get_db(db_path_arg=None):
        from bet.db.connection import _configure_connection
        c = sqlite3.connect(str(db_path))
        _configure_connection(c)
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    monkeypatch.setattr("bet.db.connection.get_db", _mock_get_db)
    # Also patch in scanners.merge_results where it's imported
    try:
        import scanners.merge_results as mr
        monkeypatch.setattr(mr, "get_db", _mock_get_db)
    except (ImportError, AttributeError):
        pass

    return db_path


@pytest.fixture
def scan_config(tmp_path):
    """Create a minimal scan config for testing."""
    config = {
        "description": "Test config",
        "sports": {
            "football": {
                "urls": ["https://www.flashscore.com/football/poland/"],
                "timeout_minutes": 1,
                "max_deep_links": 5,
                "dedicated_sources": [],
            },
            "tennis": {
                "urls": ["https://www.flashscore.com/tennis/"],
                "timeout_minutes": 1,
                "max_deep_links": 5,
                "dedicated_sources": [],
            },
            "niche": {
                "urls": ["https://www.flashscore.com/darts/"],
                "timeout_minutes": 1,
                "max_deep_links": 5,
                "dedicated_sources": [],
            },
        },
        "shared_sources": {"flashscore.com": {"parallel": 3}},
        "_legacy_urls": [],
    }
    config_path = tmp_path / "scan_urls.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config_path


class StubScanner:
    """Minimal scanner stub for testing parallel dispatch."""

    def __init__(self, group: str, events: list[dict] | None = None, fail: bool = False, delay: float = 0):
        self._group = group
        self._events = events or []
        self._fail = fail
        self._delay = delay

    @property
    def scanner_group(self) -> str:
        return self._group

    @property
    def sport_name(self) -> str:
        return self._group

    def scan(self, betting_date: str, semaphore_map) -> MagicMock:
        """Simulate a scan run."""
        if self._delay:
            time.sleep(self._delay)
        if self._fail:
            raise RuntimeError(f"Scanner {self._group} intentionally failed")
        stats = MagicMock()
        stats.events_found = len(self._events)
        stats.urls_scanned = 1
        stats.duration_sec = self._delay or 0.1
        return stats


class TestParallelDispatch:
    """Test parallel sport scanner dispatch."""

    def test_scanners_run_independently(self):
        """Each scanner runs and produces results independently."""
        scanners = [
            StubScanner("football", [{"home": "A", "away": "B"}]),
            StubScanner("tennis", [{"home": "C", "away": "D"}, {"home": "E", "away": "F"}]),
            StubScanner("niche", [{"home": "G", "away": "H"}]),
        ]

        results = {}
        from scanners.domain_semaphore import DomainSemaphoreMap
        semaphore_map = DomainSemaphoreMap()

        with ThreadPoolExecutor(max_workers=len(scanners)) as executor:
            futures = {
                executor.submit(s.scan, "2026-05-07", semaphore_map): s.scanner_group
                for s in scanners
            }
            for future in as_completed(futures):
                group = futures[future]
                stats = future.result(timeout=10)
                results[group] = {"events_found": stats.events_found}

        assert "football" in results
        assert "tennis" in results
        assert "niche" in results
        assert results["football"]["events_found"] == 1
        assert results["tennis"]["events_found"] == 2
        assert results["niche"]["events_found"] == 1

    def test_failing_scanner_does_not_crash_others(self):
        """One failing scanner doesn't prevent others from completing."""
        scanners = [
            StubScanner("football", [{"home": "A", "away": "B"}]),
            StubScanner("tennis", fail=True),
            StubScanner("niche", [{"home": "G", "away": "H"}]),
        ]

        results = {}
        from scanners.domain_semaphore import DomainSemaphoreMap
        semaphore_map = DomainSemaphoreMap()

        with ThreadPoolExecutor(max_workers=len(scanners)) as executor:
            futures = {
                executor.submit(s.scan, "2026-05-07", semaphore_map): s.scanner_group
                for s in scanners
            }
            for future in as_completed(futures):
                group = futures[future]
                try:
                    stats = future.result(timeout=10)
                    results[group] = {"status": "completed", "events_found": stats.events_found}
                except Exception as e:
                    results[group] = {"status": "failed", "error": str(e)}

        assert results["football"]["status"] == "completed"
        assert results["tennis"]["status"] == "failed"
        assert results["niche"]["status"] == "completed"
        assert "intentionally failed" in results["tennis"]["error"]

    def test_parallel_execution_is_concurrent(self):
        """Scanners actually run concurrently (not sequentially)."""
        # Each scanner takes 0.3s. If truly parallel, total < 0.6s.
        scanners = [
            StubScanner("football", [{"home": "A", "away": "B"}], delay=0.3),
            StubScanner("tennis", [{"home": "C", "away": "D"}], delay=0.3),
            StubScanner("niche", [{"home": "E", "away": "F"}], delay=0.3),
        ]

        from scanners.domain_semaphore import DomainSemaphoreMap
        semaphore_map = DomainSemaphoreMap()

        start = time.time()
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(s.scan, "2026-05-07", semaphore_map): s.scanner_group
                for s in scanners
            }
            for future in as_completed(futures):
                future.result(timeout=10)
        elapsed = time.time() - start

        # If sequential, would be ~0.9s. Parallel should be ~0.3s.
        assert elapsed < 0.7, f"Took {elapsed:.2f}s — likely not parallel"

    def test_scan_summary_produced(self, tmp_path, mock_db):
        """merge_scan_results produces scan_summary.json from DB."""
        from scanners.merge_results import merge_scan_results

        # Populate DB with some scan results directly
        import sqlite3
        conn = sqlite3.connect(str(mock_db))
        conn.execute("""
            INSERT INTO scan_results (betting_date, sport, source_domain, event_key, home_team, away_team, kickoff, competition, raw_data, scan_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("2026-05-07", "football", "flashscore.com", "teama|teamb", "TeamA", "TeamB", "18:00", "Premier League", '{"home": "TeamA", "away": "TeamB"}', "2026-05-07T10:00:00Z"))
        conn.execute("""
            INSERT INTO scan_results (betting_date, sport, source_domain, event_key, home_team, away_team, kickoff, competition, raw_data, scan_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("2026-05-07", "tennis", "flashscore.com", "player1|player2", "Player1", "Player2", "14:00", "ATP", '{"home": "Player1", "away": "Player2"}', "2026-05-07T10:00:00Z"))
        conn.commit()
        conn.close()

        # Patch DATA_DIR to tmp
        import scanners.merge_results as mr
        orig_data_dir = mr.DATA_DIR
        mr.DATA_DIR = tmp_path
        try:
            out_path = merge_scan_results("2026-05-07")
            assert out_path.exists()
            data = json.loads(out_path.read_text(encoding="utf-8"))
            assert "flashscore.com" in data
            assert len(data["flashscore.com"]) == 2
        finally:
            mr.DATA_DIR = orig_data_dir

    def test_config_loader_new_format(self, scan_config):
        """Config loader reads sport-grouped format correctly."""
        from scanners.config_loader import load_scan_config, get_urls_for_sport, get_all_sport_groups

        config = load_scan_config(scan_config)
        assert "sports" in config
        groups = get_all_sport_groups(config)
        assert "football" in groups
        assert "tennis" in groups
        assert "niche" in groups

        football_urls = get_urls_for_sport(config, "football")
        assert len(football_urls) == 1
        assert "flashscore.com/football/poland" in football_urls[0]

    def test_config_loader_legacy_format(self, tmp_path):
        """Config loader handles old flat format gracefully."""
        from scanners.config_loader import load_scan_config, get_all_sport_groups, get_all_urls_flat

        legacy_config = {"urls": ["https://example.com/a", "https://example.com/b"]}
        legacy_path = tmp_path / "legacy.json"
        legacy_path.write_text(json.dumps(legacy_config), encoding="utf-8")

        config = load_scan_config(legacy_path)
        assert config["_legacy_urls"] == ["https://example.com/a", "https://example.com/b"]
        assert get_all_sport_groups(config) == []
        assert get_all_urls_flat(config) == ["https://example.com/a", "https://example.com/b"]
