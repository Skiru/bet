"""Thread-safe domain semaphore for coordinating rate-limited access across parallel scanners."""
import threading
import time
from contextlib import contextmanager


# From existing scan_events.py constants
PARALLEL_SAFE_DOMAINS = {
    "flashscore.com": 3,
    "sofascore.com": 2,
    "betexplorer.com": 2,
    "oddsportal.com": 2,
    "forebet.com": 2,
    "scores24.live": 2,
    "soccerway.com": 2,
}

DOMAIN_DELAY_OVERRIDES = {
    "betclic.pl": 2.0,
    "soccerstats.com": 1.5,
    "totalcorner.com": 1.0,
    "hltv.org": 2.0,
    "dartsorakel.com": 2.0,
}

DEFAULT_CONCURRENT = 2
DEFAULT_DELAY = 0.5


class DomainSemaphoreMap:
    """Manages per-domain semaphores and delays for rate-limited access."""

    def __init__(self):
        self._semaphores: dict[str, threading.Semaphore] = {}
        self._last_access: dict[str, float] = {}
        self._lock = threading.Lock()

    def _get_semaphore(self, domain: str) -> threading.Semaphore:
        """Get or create semaphore for a domain."""
        if domain not in self._semaphores:
            with self._lock:
                if domain not in self._semaphores:
                    max_concurrent = PARALLEL_SAFE_DOMAINS.get(domain, DEFAULT_CONCURRENT)
                    # Rate-limited domains override to 1
                    if domain in DOMAIN_DELAY_OVERRIDES:
                        max_concurrent = min(max_concurrent, 1)
                    self._semaphores[domain] = threading.Semaphore(max_concurrent)
        return self._semaphores[domain]

    def _get_delay(self, domain: str) -> float:
        """Get inter-fetch delay for a domain."""
        return DOMAIN_DELAY_OVERRIDES.get(domain, DEFAULT_DELAY)

    def acquire(self, domain: str) -> None:
        """Acquire domain semaphore, enforcing inter-fetch delay."""
        sem = self._get_semaphore(domain)
        sem.acquire()
        # Enforce delay since last access to this domain
        delay = self._get_delay(domain)
        with self._lock:
            last = self._last_access.get(domain, 0.0)
            elapsed = time.time() - last
            if elapsed < delay:
                time.sleep(delay - elapsed)

    def release(self, domain: str) -> None:
        """Release domain semaphore and record access time."""
        with self._lock:
            self._last_access[domain] = time.time()
        sem = self._get_semaphore(domain)
        sem.release()

    @contextmanager
    def hold(self, domain: str):
        """Context manager: acquires semaphore + enforces delay, releases on exit."""
        self.acquire(domain)
        try:
            yield
        finally:
            self.release(domain)
