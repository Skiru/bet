"""Tests for DomainSemaphoreMap — concurrency limiting and delay enforcement."""
import threading
import time
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE / "scripts"))

from scripts.scanners.domain_semaphore import (
    DEFAULT_CONCURRENT,
    DEFAULT_DELAY,
    DOMAIN_DELAY_OVERRIDES,
    PARALLEL_SAFE_DOMAINS,
    DomainSemaphoreMap,
)


@pytest.fixture
def sem_map():
    return DomainSemaphoreMap()


class TestSemaphoreCreation:
    def test_known_parallel_domain_gets_correct_count(self, sem_map):
        # flashscore.com allows 3 concurrent
        sem = sem_map._get_semaphore("flashscore.com")
        # Semaphore should allow 3 acquires without blocking
        assert sem.acquire(blocking=False)
        assert sem.acquire(blocking=False)
        assert sem.acquire(blocking=False)
        # 4th should fail
        assert not sem.acquire(blocking=False)
        sem.release()
        sem.release()
        sem.release()

    def test_rate_limited_domain_gets_one(self, sem_map):
        # betclic.pl is in DOMAIN_DELAY_OVERRIDES so gets max(1, ...)
        sem = sem_map._get_semaphore("betclic.pl")
        assert sem.acquire(blocking=False)
        # 2nd should fail (limited to 1)
        assert not sem.acquire(blocking=False)
        sem.release()

    def test_unknown_domain_gets_default_concurrent(self, sem_map):
        sem = sem_map._get_semaphore("unknown-site.org")
        # Should allow DEFAULT_CONCURRENT (2) acquires
        assert sem.acquire(blocking=False)
        assert sem.acquire(blocking=False)
        assert not sem.acquire(blocking=False)
        sem.release()
        sem.release()


class TestDelayEnforcement:
    def test_known_domain_delay(self, sem_map):
        assert sem_map._get_delay("betclic.pl") == 2.0
        assert sem_map._get_delay("hltv.org") == 2.0
        assert sem_map._get_delay("soccerstats.com") == 1.5

    def test_unknown_domain_gets_default_delay(self, sem_map):
        assert sem_map._get_delay("unknown.com") == DEFAULT_DELAY

    def test_delay_enforced_between_accesses(self, sem_map):
        """Verify inter-fetch delay is respected."""
        domain = "soccerstats.com"  # 1.5s delay
        t0 = time.time()
        with sem_map.hold(domain):
            pass
        t1 = time.time()
        with sem_map.hold(domain):
            pass
        t2 = time.time()
        # Second access should have waited ~1.5s
        gap = t2 - t1
        assert gap >= 1.4, f"Expected >=1.4s gap, got {gap:.2f}s"


class TestContextManager:
    def test_hold_acquires_and_releases(self, sem_map):
        domain = "flashscore.com"
        # Before: all 3 slots free
        sem = sem_map._get_semaphore(domain)
        with sem_map.hold(domain):
            # One slot taken inside context
            # Two more acquires should succeed
            assert sem.acquire(blocking=False)
            assert sem.acquire(blocking=False)
            # Third should fail (3 total taken: 1 by hold + 2 manual)
            assert not sem.acquire(blocking=False)
            sem.release()
            sem.release()
        # After context: slot released back
        assert sem.acquire(blocking=False)
        sem.release()

    def test_hold_releases_on_exception(self, sem_map):
        domain = "betclic.pl"  # semaphore(1)
        try:
            with sem_map.hold(domain):
                raise ValueError("test error")
        except ValueError:
            pass
        # Should be released — able to acquire again
        sem = sem_map._get_semaphore(domain)
        assert sem.acquire(blocking=False)
        sem.release()


class TestConcurrentAccess:
    def test_concurrent_threads_respect_limit(self, sem_map):
        """11 threads hitting a semaphore(2) domain — max 2 concurrent."""
        domain = "unknown-domain.io"
        max_concurrent_observed = 0
        current_count = 0
        lock = threading.Lock()

        def worker():
            nonlocal max_concurrent_observed, current_count
            with sem_map.hold(domain):
                with lock:
                    current_count += 1
                    if current_count > max_concurrent_observed:
                        max_concurrent_observed = current_count
                time.sleep(0.05)
                with lock:
                    current_count -= 1

        threads = [threading.Thread(target=worker) for _ in range(11)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert max_concurrent_observed <= DEFAULT_CONCURRENT

    def test_rate_limited_domain_serializes(self, sem_map):
        """Rate-limited domain (semaphore=1) should serialize access."""
        domain = "hltv.org"
        max_concurrent_observed = 0
        current_count = 0
        lock = threading.Lock()

        def worker():
            nonlocal max_concurrent_observed, current_count
            with sem_map.hold(domain):
                with lock:
                    current_count += 1
                    if current_count > max_concurrent_observed:
                        max_concurrent_observed = current_count
                time.sleep(0.02)
                with lock:
                    current_count -= 1

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert max_concurrent_observed == 1
