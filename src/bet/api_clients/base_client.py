"""Abstract base class for all API clients.

Provides rate limiting, retry with exponential backoff, API key loading,
and stats cache integration.

Adapted from scripts/api_clients/base_client.py for src/bet/ package layout.
"""

import json
import os
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import UTC
from enum import StrEnum
from pathlib import Path
from typing import Any

import requests

from .rate_limiter import RateLimiter
from .env import get_env

# Resolve project root: src/bet/api_clients/base_client.py → project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
CACHE_DIR = PROJECT_ROOT / "betting" / "data" / "stats_cache"

# A 429 whose Retry-After is further away than this is treated as "spent for
# this run" rather than "wait and try again". Ten minutes is comfortably longer
# than any transient burst limit and far shorter than a daily window, so a
# short-fuse throttle still retries while a rolling 86400s bucket does not.
_EXHAUSTION_HORIZON_SECONDS = 600


def _record_source_health(source_name: str, success: bool) -> None:
    """Record API source health to DB (best-effort, non-blocking)."""
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import SourceHealthRepo

        with get_db() as conn:
            repo = SourceHealthRepo(conn)
            if success:
                repo.record_success(source_name, response_ms=0.0)
            else:
                repo.record_failure(source_name)
            conn.commit()
    except Exception:
        pass  # Non-critical — don't break API calls


class APIError(Exception):
    """General API error."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class APIRateLimitError(APIError):
    """API rate limit exceeded (HTTP 429 or quota exhausted)."""


class APINotFoundError(APIError):
    """Resource not found (HTTP 404)."""


class APIEntitlementError(APIError):
    """The key is present and the endpoint answered, but the account may not use it.

    Its own class because it is the one failure that must never be reported as
    a data problem. api-sports answers a suspended account with **HTTP 200** and
    ``{"errors": {"access": "Your account is suspended..."}, "response": []}``
    -- an empty result set, indistinguishable at the call site from "no such
    team". On 2026-09-02 that produced 472 ``could not resolve team identity``
    gaps naming Flamengo, Celtic, Udinese, Motherwell and West Brom, none of
    which is a name problem and all of which read as one; api-football
    contributed zero observations to that day's dossiers.
    """


from bet.integration.source_result import SourceResultStatus, SourceOperationResult

class BaseAPIClient(ABC):
    """Abstract base class for sports data API clients."""

    MAX_RETRIES = 3
    TIMEOUT = 15  # seconds
    BACKOFF_BASE = 1  # seconds — retry delays: 1s, 2s, 4s

    def __init__(self, api_name: str, base_url: str, rate_limiter: RateLimiter):
        self.api_name = api_name
        self.base_url = base_url.rstrip("/")
        self.rate_limiter = rate_limiter
        self.api_key = self._load_api_key()

    @abstractmethod
    def get_fixtures(self, date: str) -> list:
        """Get all fixtures/games for a given date (YYYY-MM-DD)."""
        ...

    @abstractmethod
    def get_fixture_stats(self, fixture_id: str) -> list:
        """Get match statistics for a specific fixture."""
        ...

    @abstractmethod
    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """Get head-to-head history between two teams."""
        ...

    def resolve_team_id(self, team_name: str) -> str | None:
        """Resolve a team name to an API-specific team ID. Override in subclasses."""
        return None

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list:
        """Get last N finished fixtures for a team. Override in subclasses."""
        return []

    def is_available(self) -> bool:
        """Return True if the client can make requests (has key or doesn't need one)."""
        return bool(self.api_key)

    #: Extra .env names accepted for a derived variable, because the
    #: api_name -> ENV_VAR convention does not match what .env actually calls
    #: them. Without these a provider whose key IS in .env would read as absent.
    KEY_ENV_ALIASES = {
        "THESPORTSDB_KEY": ("THESPORTSDB_API_KEY",),
        "ODDS_API_IO_KEY": ("ODDS_API_IO_API_KEY",),
        "BRAVE_SEARCH_KEY": ("BRAVE_SEARCH_API_KEY",),
        "ODDS_PAPI_KEY": ("ODDSPAPI_API_KEY",),
        "HIGHLIGHTLY_KEY": ("HIGHLIGHTLY_API_KEY", "RAPIDAPI_KEY"),
        "SPORTDB_KEY": ("SPORTDB_API_KEY",),
        "PANDASCORE_KEY": ("PANDASCORE_TOKEN",),
    }

    def _load_api_key(self) -> str | None:
        """Load this provider's API key from the process env or the project .env.

        Those are the only two sources. The former fallback to
        config/api_keys.json was removed: a key stored in two places drifts, and
        because the fallback was silent the drift showed up as odd provider
        behaviour rather than as a config error. See bet.api_clients.env.
        """
        env_var = self.api_name.upper().replace("-", "_") + "_KEY"
        aliases = self.KEY_ENV_ALIASES.get(env_var, ())
        return get_env(env_var, *aliases) or None

    def _check_api_key(self) -> bool:
        """Check if API key is available. Prints warning if not."""
        if not self.api_key:
            print(f"[{self.api_name}] WARNING: No API key — skipping request")
            return False
        return True

    def _request(
        self, endpoint: str, params: dict | None = None, cost: int = 1
    ) -> dict:
        """Make API request with rate limiting, retry, and error handling."""
        if not self.rate_limiter.can_request(self.api_name, cost):
            # "Daily quota exhausted" is the wrong sentence for a provider that
            # stopped on billing, and it is the sentence the caller turns into
            # a data_gap. Ask why before saying what.
            billing = self.rate_limiter.entitlement_fault(self.api_name)
            if billing:
                raise APIEntitlementError(f"[{self.api_name}] {billing}")
            remaining = self.rate_limiter.get_remaining(self.api_name)
            raise APIRateLimitError(
                f"[{self.api_name}] Daily quota exhausted. Remaining: {remaining}"
            )

        url = f"{self.base_url}{endpoint}"
        last_error = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = requests.get(
                    url,
                    params=params,
                    headers=self._build_headers(),
                    timeout=self.TIMEOUT,
                )

                if response.status_code == 429:
                    raise APIRateLimitError(
                        f"[{self.api_name}] HTTP 429 Too Many Requests",
                        status_code=429,
                    )
                if response.status_code == 404:
                    raise APINotFoundError(
                        f"[{self.api_name}] Not found: {endpoint}",
                        status_code=404,
                    )
                if response.status_code >= 400:
                    raise APIError(
                        (
                            f"[{self.api_name}] HTTP {response.status_code}: "
                            f"{response.text[:200]}"
                        ),
                        status_code=response.status_code,
                    )

                self.rate_limiter.record_request(self.api_name, endpoint, cost)
                return response.json()

            except APIRateLimitError:
                raise
            except APINotFoundError:
                raise
            except APIError:
                raise
            except requests.exceptions.RequestException as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    backoff = self.BACKOFF_BASE * (2 ** (attempt - 1))
                    time.sleep(backoff)

        raise APIError(
            f"[{self.api_name}] Failed after {self.MAX_RETRIES} attempts: {last_error}"
        )

    def _build_headers(self) -> dict:
        """Build request headers. Override in subclasses for custom auth."""
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-apisports-key"] = self.api_key
        return headers

    @staticmethod
    def _validate_cache_key(cache_key: str) -> None:
        """Validate cache_key to prevent path traversal."""
        if not cache_key:
            raise ValueError("cache_key must not be empty")
        if ".." in cache_key or cache_key.startswith("/") or cache_key.startswith("\\"):
            raise ValueError(

                    f"Invalid cache_key '{cache_key}': must not contain '..' "
                    "or start with '/'"

            )

    def _check_cache(self, cache_key: str, ttl_hours: int = 24) -> dict | None:
        """Check stats_cache for a cached response."""
        from datetime import datetime

        self._validate_cache_key(cache_key)
        cache_file = CACHE_DIR / f"{cache_key}.json"
        if not cache_file.exists():
            return None

        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None  # Legacy cache format (raw list) — treat as expired
            last_updated = data.get("last_updated", "")
            if not last_updated:
                return None
            updated_dt = datetime.fromisoformat(last_updated)
            age_hours = (datetime.now(UTC) - updated_dt).total_seconds() / 3600
            if age_hours < ttl_hours:
                return data
        except (json.JSONDecodeError, ValueError, OSError):
            pass

        return None

    def _save_cache(self, cache_key: str, data: dict) -> None:
        """Save response data to stats_cache."""
        from datetime import datetime

        self._validate_cache_key(cache_key)
        cache_file = CACHE_DIR / f"{cache_key}.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        data["last_updated"] = datetime.now(UTC).isoformat()
        cache_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )


class APISportsClient(BaseAPIClient):
    """Shared base for API-Sports family clients.

    Provides common x-apisports-key auth and shared-key fallback loading.
    """

    _SHARES_FOOTBALL_KEY = False

    def _load_api_key(self) -> str | None:
        """Load API key — optionally falls back to the shared api-football key.

        The api-sports.io platform issues one key per sport endpoint, but they
        are frequently the same key, so a sibling client may borrow
        API_FOOTBALL_KEY when its own is unset.
        """
        key = super()._load_api_key()
        if key:
            return key
        if not self._SHARES_FOOTBALL_KEY:
            return None
        return get_env("API_FOOTBALL_KEY") or None

    # Keys api-sports uses in its 200-with-errors envelope that mean "this
    # account may not do this", as opposed to "you asked wrongly". Suspension,
    # a lapsed plan and a bad key all arrive here rather than as an HTTP status.
    _ENTITLEMENT_ERROR_KEYS = frozenset({"access", "token", "plan", "subscription"})

    def _build_headers(self) -> dict:
        """Use x-apisports-key header for authentication."""
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-apisports-key"] = self.api_key
        return headers

    @classmethod
    def entitlement_fault(cls, payload: Any) -> str | None:
        """The account-level reason this payload is empty, if that is why.

        api-sports puts ``errors`` in the body of a 200. When it is a dict with
        one of the entitlement keys, the empty ``response`` is not an answer
        about the question asked -- it is the account being unable to ask. A
        *list* (or an empty dict) is the normal success shape and means nothing.
        """
        if not isinstance(payload, dict):
            return None
        errors = payload.get("errors")
        if not isinstance(errors, dict) or not errors:
            return None
        for key in cls._ENTITLEMENT_ERROR_KEYS:
            if errors.get(key):
                return f"{key}: {errors[key]}"
        return None

    def _request(
        self, endpoint: str, params: dict | None = None, cost: int = 1
    ) -> dict:
        """As the base, but an api-sports entitlement envelope raises.

        Overridden rather than folded into the base because only this family
        answers 200 with an error body; every other client here says what it
        means in the status line.
        """
        payload = super()._request(endpoint, params=params, cost=cost)
        fault = self.entitlement_fault(payload)
        if fault:
            # Same rail bzzoiro's 402 already runs on: record it once, stop
            # calling the provider for the rest of the run, and keep the word
            # "entitlement" attached so preflight does not advise raising a
            # limit that was never the constraint. Without this the run asks
            # once per team and is told the same thing 472 times.
            self.rate_limiter.note_entitlement_fault(
                self.api_name, f"{endpoint} -> {fault}"
            )
            raise APIEntitlementError(f"[{self.api_name}] {fault}", status_code=200)
        return payload

    def _request_with_evidence(
        self,
        endpoint: str,
        params: dict | None = None,
        operation: str = "",
        source_event_id: str | None = None,
        cost: int = 1,
        expects_response_list: bool = False,
    ) -> "SourceOperationResult[dict]":
        """Make API request with evidence capture.

        Returns SourceOperationResult with evidence_refs for audit trail.
        """
        from bet.integration.evidence import EvidenceRef, persist_response_evidence
        from bet.integration.telemetry_wrapper import wrap_request

        if not self.rate_limiter.can_request(self.api_name, cost):
            return SourceOperationResult(
                status=SourceResultStatus.RATE_LIMITED,
                http_status=None,
                retryable=True,
                error_code="quota_exhausted",
                retry_after_seconds=None,
            )

        url = f"{self.base_url}{endpoint}"
        evidence_refs: list[EvidenceRef] = []
        last_error_code = ""
        last_retryable = False
        max_attempts = 2

        for attempt in range(1, max_attempts + 1):
            result = wrap_request(
                provider=self.api_name,
                request_fn=requests.get,
                url=url,
                params=params,
                headers=self._build_headers(),
                timeout=self.TIMEOUT,
                scope_id=endpoint,
            )
            self.rate_limiter.record_request(self.api_name, endpoint, cost)
            quota_metadata = self._extract_quota_metadata(result.headers)
            if result.status_code == 402:
                # Payment Required. The quota headers on this response are not
                # a spend tally and must not touch the counter: bzzoiro's
                # tennis product answers 402 ``addon_required`` *while sending*
                # ``ratelimit: "tennis";r=0``, and believing that wrote
                # "100/95 used" into the day's counter and made preflight
                # advise raising a limit and resetting a count -- neither of
                # which can buy a $5/mo addon. Observed live 2026-09-01.
                self.rate_limiter.note_entitlement_fault(
                    self.api_name,
                    f"HTTP 402 from {endpoint}: provider requires a paid entitlement, "
                    f"not more quota",
                )
            else:
                # The provider just stated how much of its quota is left. Believe it
                # over our own tally: the tally counts what *this* process spent,
                # while the quota belongs to the key, and any second user of that
                # key is invisible here. Providers that send nothing (bzzoiro's
                # football product on PRO) reconcile to nothing and are unaffected.
                self.rate_limiter.reconcile_from_provider(self.api_name, quota_metadata)
                if quota_metadata.get("daily_remaining") == 0:
                    self.rate_limiter.note_provider_exhausted(
                        self.api_name,
                        f"ratelimit header reports 0 of "
                        f"{quota_metadata.get('daily_limit')} remaining",
                    )

            if result.status_code is not None:
                try:
                    evidence_ref = persist_response_evidence(
                        operation=operation,
                        url=url,
                        params=params,
                        response=result,
                        source_event_id=source_event_id,
                    )
                    evidence_refs.append(replace(evidence_ref, retry_count=attempt - 1))
                except Exception:
                    return SourceOperationResult(
                        status=SourceResultStatus.EVIDENCE_ERROR,
                        http_status=result.status_code,
                        retryable=False,
                        error_code="evidence_persist_failed",
                        evidence_refs=evidence_refs,
                        retry_count=attempt - 1,
                        quota_metadata=quota_metadata,
                    )

            if result.error and result.error.retryable and attempt < max_attempts:
                last_error_code = result.error.type or "transport_error"
                last_retryable = True
                time.sleep(self._retry_delay_seconds(attempt))
                continue

            if result.error and result.status_code is None:
                return SourceOperationResult(
                    status=SourceResultStatus.TRANSPORT_ERROR,
                    http_status=None,
                    retryable=bool(result.error.retryable),
                    error_code=result.error.type or "transport_error",
                    evidence_refs=evidence_refs,
                    retry_count=attempt - 1,
                    quota_metadata=quota_metadata,
                )

            status_code = result.status_code or 0

            if status_code == 401:
                return SourceOperationResult(
                    status=SourceResultStatus.AUTHENTICATION_ERROR,
                    http_status=401,
                    error_code="http_401",
                    evidence_refs=evidence_refs,
                    retry_count=attempt - 1,
                    quota_metadata=quota_metadata,
                )
            if status_code == 403:
                error_status = SourceResultStatus.BLOCKED
                error_code = "http_403"
                if result.body:
                    try:
                        err_payload = json.loads(result.body.decode("utf-8", errors="ignore"))
                        parsed_err = self._classify_provider_payload_error(err_payload)
                        if parsed_err:
                            if parsed_err["status"] == SourceResultStatus.PLAN_RESTRICTED:
                                error_status = SourceResultStatus.PLAN_RESTRICTED
                                error_code = parsed_err["error_code"]
                            elif parsed_err["status"] == SourceResultStatus.AUTHENTICATION_ERROR:
                                error_status = SourceResultStatus.AUTHENTICATION_ERROR
                                error_code = parsed_err["error_code"]
                    except Exception:
                        pass
                return SourceOperationResult(
                    status=error_status,
                    http_status=403,
                    error_code=error_code,
                    evidence_refs=evidence_refs,
                    retry_count=attempt - 1,
                    quota_metadata=quota_metadata,
                )
            if status_code == 404:
                return SourceOperationResult(
                    SourceResultStatus.NOT_FOUND,
                    http_status=404,
                    error_code="http_404",
                    evidence_refs=evidence_refs,
                    retry_count=attempt - 1,
                    quota_metadata=quota_metadata,
                )
            if status_code == 429:
                retry_after = None
                if result.headers:
                    val = result.headers.get("Retry-After") or result.headers.get(
                        "retry-after"
                    )
                    if val:
                        try:
                            retry_after = float(val)
                        except (TypeError, ValueError):
                            pass
                # A 429 that will not clear inside this run is exhaustion, not
                # back-pressure, and the difference decides whether the rest of
                # the slate is worth attempting. Bzzoiro's tennis window is
                # 86400s, so its Retry-After is measured in hours: retrying
                # into that spends the remaining events discovering the same
                # wall one call at a time and leaves exactly the lopsided
                # artifact preflight is meant to prevent.
                if retry_after is None or retry_after > _EXHAUSTION_HORIZON_SECONDS:
                    self.rate_limiter.note_provider_exhausted(
                        self.api_name,
                        f"HTTP 429"
                        + (f", retry after {retry_after:.0f}s" if retry_after else ""),
                    )
                return SourceOperationResult(
                    SourceResultStatus.RATE_LIMITED,
                    http_status=429,
                    retryable=True,
                    error_code="http_429",
                    retry_after_seconds=retry_after,
                    evidence_refs=evidence_refs,
                    retry_count=attempt - 1,
                    quota_metadata=quota_metadata,
                )
            if status_code in {502, 503, 504} and attempt < max_attempts:
                last_error_code = f"http_{status_code}"
                last_retryable = True
                time.sleep(self._retry_delay_seconds(attempt))
                continue
            if status_code >= 500:
                return SourceOperationResult(
                    SourceResultStatus.UPSTREAM_ERROR,
                    http_status=status_code,
                    retryable=status_code in {502, 503, 504},
                    error_code=f"http_{status_code}",
                    evidence_refs=evidence_refs,
                    retry_count=attempt - 1,
                    quota_metadata=quota_metadata,
                )
            if status_code >= 400:
                return SourceOperationResult(
                    SourceResultStatus.UPSTREAM_ERROR,
                    http_status=status_code,
                    retryable=False,
                    error_code=f"http_{status_code}",
                    evidence_refs=evidence_refs,
                    retry_count=attempt - 1,
                    quota_metadata=quota_metadata,
                )

            try:
                payload = json.loads(result.body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return SourceOperationResult(
                    SourceResultStatus.PARSE_ERROR,
                    http_status=status_code,
                    retryable=False,
                    error_code="json_decode_error",
                    evidence_refs=evidence_refs,
                    retry_count=attempt - 1,
                    quota_metadata=quota_metadata,
                )

            if not isinstance(payload, dict):
                return SourceOperationResult(
                    SourceResultStatus.SCHEMA_ERROR,
                    http_status=status_code,
                    retryable=False,
                    error_code="payload_not_object",
                    evidence_refs=evidence_refs,
                    retry_count=attempt - 1,
                    quota_metadata=quota_metadata,
                )

            provider_error = self._classify_provider_payload_error(payload)
            if provider_error is not None:
                return SourceOperationResult(
                    status=provider_error["status"],
                    http_status=status_code,
                    retryable=False,
                    error_code=provider_error["error_code"],
                    evidence_refs=evidence_refs,
                    retry_count=attempt - 1,
                    quota_metadata=quota_metadata,
                )

            if expects_response_list and not isinstance(payload.get("response"), list):
                return SourceOperationResult(
                    SourceResultStatus.SCHEMA_ERROR,
                    http_status=status_code,
                    retryable=False,
                    error_code="response_not_list",
                    evidence_refs=evidence_refs,
                    retry_count=attempt - 1,
                    quota_metadata=quota_metadata,
                )

            return SourceOperationResult(
                SourceResultStatus.SUCCESS,
                value=payload,
                http_status=status_code,
                evidence_refs=evidence_refs,
                retry_count=attempt - 1,
                quota_metadata=quota_metadata,
            )

        return SourceOperationResult(
            SourceResultStatus.TRANSPORT_ERROR,
            http_status=None,
            retryable=last_retryable,
            error_code=last_error_code or "max_retries_exceeded",
            evidence_refs=evidence_refs,
            retry_count=max_attempts - 1,
        )

    @staticmethod
    def _retry_delay_seconds(attempt: int) -> float:
        base = 1 * (2 ** (attempt - 1))
        return base + random.uniform(0.05, 0.25)

    @staticmethod
    def _extract_quota_metadata(
        headers: dict[str, Any] | None,
    ) -> dict[str, int | str | None]:
        if not headers:
            return {}
        normalized = {str(key).lower(): value for key, value in headers.items()}
        header_map = {
            "x-ratelimit-limit": "minute_limit",
            "x-ratelimit-remaining": "minute_remaining",
            "x-ratelimit-requests-limit": "minute_limit",
            "x-ratelimit-requests-remaining": "minute_remaining",
            "x-ratelimit-day-limit": "daily_limit",
            "x-ratelimit-day-remaining": "daily_remaining",
        }
        metadata: dict[str, int | str | None] = {}
        for header_name, field_name in header_map.items():
            if header_name not in normalized:
                continue
            raw_value = normalized[header_name]
            try:
                metadata[field_name] = int(str(raw_value))
            except (TypeError, ValueError):
                metadata[field_name] = str(raw_value)
        return metadata

    @staticmethod
    def _classify_provider_payload_error(
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        errors = payload.get("errors")
        if errors in (None, {}, [], ""):
            return None

        if isinstance(errors, dict):
            flattened = " | ".join(
                f"{key}:{value}" for key, value in sorted(errors.items())
            )
        elif isinstance(errors, list):
            flattened = " | ".join(str(item) for item in errors)
        else:
            flattened = str(errors)

        lowered = flattened.lower()
        if "rate limit" in lowered or "too many" in lowered:
            return {
                "status": SourceResultStatus.RATE_LIMITED,
                "error_code": "provider_rate_limited",
            }
        if any(
            token in lowered
            # "suspend" is here because api-football answers a suspended
            # account with exactly this envelope and nothing else -- HTTP 200,
            # empty response, one sentence in `errors.access`. Without the
            # token it fell through to `provider_error_payload`, which reads
            # as an upstream hiccup worth retrying rather than a bill to pay.
            for token in ("free plans", "subscription", "access denied", "plan", "suspend")
        ):
            return {
                "status": SourceResultStatus.PLAN_RESTRICTED,
                "error_code": "provider_plan_restricted",
            }
        if any(
            token in lowered
            for token in ("invalid key", "unauthorized", "forbidden", "authentication")
        ):
            return {
                "status": SourceResultStatus.AUTHENTICATION_ERROR,
                "error_code": "provider_authentication_error",
            }
        return {
            "status": SourceResultStatus.UPSTREAM_ERROR,
            "error_code": "provider_error_payload",
        }
