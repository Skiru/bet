from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from curl_cffi import requests

from bet.sofa.config import SofaConfig
from bet.sofa.stage import current_stage
from bet.sofa.timeutil import now

DEFAULT_BASE_URL = "https://production-superbet-offer-pl.freetls.fastly.net"
DEFAULT_LANG = "pl-PL"
MATCH_NAME_SEPARATOR = "·"

SPORT_IDS = {"football": 5, "tennis": 2}
SPORT_BY_ID = {value: key for key, value in SPORT_IDS.items()}

# Superbet's two offer states, keyed by `offerStateId` on every odd and by the
# keys of `offerStateStatus` on the event: "1" pre-match, "2" live. Measured on
# the 2026-10-04 board (3,483 events): a "2" key appears only on STARTED /
# FINISHED events, and 3 of them were STARTED with Superbet's own utcDate still
# in the future - the start clock is not a start signal.
LIVE_OFFER_STATE = "2"
_STARTED_STATUSES = frozenset({"STARTED", "FINISHED"})

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
            self._log(current_stage(), "GET", url, status, elapsed, False, "CLOSED")
            response.raise_for_status()
        except Exception as e:
            elapsed = int((time.monotonic() - start_t) * 1000)
            status = getattr(e, "response", None)
            if status is not None:
                status = status.status_code
            self._log(current_stage(), "GET", url, status, elapsed, False, "CLOSED")
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


def odds_items(odds_data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The priced markets in a Superbet event payload, or an empty list.

    Superbet describes a match it no longer prices as ``{"odds": null}`` — the
    key is present and its value is None. That is the *dominant* shape, not an
    edge case: 68 of the first 69 fixtures on 2026-09-18. A gate that asks
    whether the key exists therefore lets None through, and ``for item in
    None`` took the whole day's coupon down on the first finished match (F32).

    This lives in one place because it used to live in two, and only one of the
    copies was right (samples.py had ``.get("odds") or []`` all along). The
    wrong copy is the one that cost the day.

    A live odd (`offerStateId` 2) is not a pre-match price and is dropped here,
    for every reader at once. Nothing in the repo read the field: the only
    in-play guard was the kickoff clock, and on 2026-10-04 three events were
    STARTED in Superbet's own metadata with its utcDate still ahead - their
    live ladders reached OFFER, SHADOW, CS2 and the closing capture as prices.
    """
    if not odds_data:
        return []
    items = odds_data.get("odds")
    if not items:
        return []
    return [
        item for item in items if isinstance(item, dict) and not is_live_odd(item)
    ]


def is_live_odd(item: dict[str, Any]) -> bool:
    """True for an odd quoted in Superbet's live offer state."""
    return str(item.get("offerStateId")) == LIVE_OFFER_STATE


def superbet_kickoff(odds_data: dict[str, Any] | None) -> datetime | None:
    """The start time an event payload carries now (`utcDate`), or None."""
    raw = (odds_data or {}).get("utcDate")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def event_started(odds_data: dict[str, Any] | None) -> bool:
    """Whether Superbet itself reports the event as under way or over.

    Read from the event, not from a clock: `metadata.status` STARTED or
    FINISHED, or a live offer state of any kind. The pre-match state alone
    says nothing about a start. "stop" is a suspension (15 NOT_STARTED events
    on 2026-10-04). "finished" with no metadata is a delisted duplicate: the
    first version of this read it as a start and flagged Esquiva Banuls -
    Ivanov and Lock - Hemery four hours early, each with a second listing
    still `{"1": "active"}`.
    """
    if not odds_data:
        return False
    meta = odds_data.get("metadata")
    if isinstance(meta, dict) and meta.get("status") in _STARTED_STATUSES:
        return True
    states = odds_data.get("offerStateStatus")
    return isinstance(states, dict) and LIVE_OFFER_STATE in states


def split_match_name(match_name: str | None) -> tuple[str, str]:
    if not match_name:
        return ("", "")
    parts = [part.strip() for part in match_name.split(MATCH_NAME_SEPARATOR)]
    side_a = parts[0]
    side_b = parts[1] if len(parts) > 1 else ""
    return side_a, side_b
