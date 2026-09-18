from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from curl_cffi import requests

from bet.sofa.config import SofaConfig
from bet.sofa.timeutil import now

DEFAULT_BASE_URL = "https://production-superbet-offer-pl.freetls.fastly.net"
DEFAULT_LANG = "pl-PL"
MATCH_NAME_SEPARATOR = "·"

SPORT_IDS = {"football": 5, "tennis": 2}
SPORT_BY_ID = {value: key for key, value in SPORT_IDS.items()}

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class SuperbetClient:
    # Class-level default so a client built without a configured run id -
    # tests stub __init__ - still logs a well-formed row.
    run_id: str = ""

    def __init__(self, base_url: str = DEFAULT_BASE_URL) -> None:
        self.base_url = base_url.strip().rstrip("/")
        self.session: requests.Session[Any] = requests.Session(
            impersonate="chrome124"
        )
        self.session.headers.update({"User-Agent": _USER_AGENT})

        config = SofaConfig.from_env()
        self.log_path = Path(config.runs_dir) / "run.log.jsonl"
        self.run_id = config.run_id
        self._log_lock = threading.Lock()

    def _log(
        self,
        stage: str,
        method: str,
        url: str,
        status: int | None,
        elapsed_ms: int,
        cache_hit: bool,
        breaker_state: str,
    ) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts_utc": now().isoformat().replace("+00:00", "Z"),
            "run_id": self.run_id,
            "stage": stage,
            "method": method,
            "url": url,
            "status": status,
            "elapsed_ms": elapsed_ms,
            "cache_hit": cache_hit,
            "breaker_state": breaker_state,
        }
        with self._log_lock:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        start_t = time.monotonic()
        try:
            response = self.session.get(url, params=params, timeout=25.0)
            elapsed = int((time.monotonic() - start_t) * 1000)
            status = response.status_code
            self._log("BOARD", "GET", url, status, elapsed, False, "CLOSED")
            response.raise_for_status()
        except Exception as e:
            elapsed = int((time.monotonic() - start_t) * 1000)
            status = getattr(e, "response", None)
            if status is not None:
                status = status.status_code
            self._log("BOARD", "GET", url, status, elapsed, False, "CLOSED")
            raise

        try:
            body = response.json()
        except ValueError:
            return None

        if not isinstance(body, dict):
            return body

        if "data" in body:
            return body["data"]
        return body

    def events_by_date(
        self,
        window_start: datetime,
        window_end: datetime,
        *,
        offer_state: str = "prematch",
    ) -> list[dict[str, Any]]:
        fmt = "%Y-%m-%d %H:%M:%S"

        # Superbet expects the dates as strings like '2026-09-17 00:00:00'
        def format_window(d: datetime) -> str:
            if not d.tzinfo:
                d = d.replace(tzinfo=UTC)
            return d.astimezone(UTC).strftime(fmt)

        data = self._get_json(
            f"/v2/{DEFAULT_LANG}/events/by-date",
            {
                "startDate": format_window(window_start),
                "endDate": format_window(window_end),
                "offerState": offer_state,
            },
        )
        return data if isinstance(data, list) else []

    def event_odds(self, event_id: int | str) -> dict[str, Any] | None:
        data = self._get_json(f"/v2/{DEFAULT_LANG}/events/{event_id}")
        if not data:
            return None
        first = data[0] if isinstance(data, list) else data
        return first if isinstance(first, dict) else None


def split_match_name(match_name: str | None) -> tuple[str, str]:
    if not match_name:
        return ("", "")
    parts = [part.strip() for part in match_name.split(MATCH_NAME_SEPARATOR)]
    side_a = parts[0]
    side_b = parts[1] if len(parts) > 1 else ""
    return side_a, side_b
