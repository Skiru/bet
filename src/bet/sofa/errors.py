class SofaError(Exception):
    """Base class for Sofa pipeline errors."""

    pass


class ProviderError(SofaError):
    """Error from the provider."""

    pass


class CircuitOpenError(SofaError):
    """Circuit breaker is open."""

    pass


class TransportError(SofaError):
    """The request did not complete: timeout, connection failure, dead bridge.

    Separate from ProviderError on purpose. The retry in ``_execute`` caught
    ``curl_cffi.RequestsError``, which only the direct transport ever raised;
    the browser bridge — the only working transport since 2026-09-17 — raises
    ProviderError for everything, so it landed in the catch-all branch and
    there were no retries at all (F21). Measured: 30.3 s between the last log
    row and the failure, where a retry would have made it ~61 s.

    A transport failure is worth retrying because it says nothing about the
    request. A ProviderError — HTTP 403, HTML where JSON was promised — is a
    semantic answer, and asking again immediately is how a rate limit becomes
    a ban.
    """
