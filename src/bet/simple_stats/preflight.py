"""Provider quota preflight for ENRICH.

ENRICH costs roughly a dozen provider calls per event and the binding
constraint is a *daily* quota, not anything about the fixtures. Discovering
that mid-run means half the budget is already burnt and the artifact is
lopsided: some events enriched from three providers, the rest from none. This
module answers "is it worth starting?" before any of it is spent.
"""
from __future__ import annotations

from bet.api_clients.env import ENV_PATH, get_env, limit_env_var

from bet.api_clients.rate_limiter import RateLimiter

from bet.simple_stats.contracts import EventListV1
from bet.simple_stats.providers import NATIVE_ID_PROVIDERS_BY_SPORT, PROVIDERS_BY_SPORT

# Providers known to have no usable data source at all, independent of quota:
# sackmann's GitHub repo returns 404 and the understat package will not build.
# They are reported separately from "exhausted" so an agent does not read a
# permanent upstream outage as a quota problem that will clear tomorrow.
KNOWN_DEAD_PROVIDERS = {
    "sackmann": "upstream repository returns HTTP 404",
    "understat": "python package not installed (aiohttp fails to build)",
}

# Rough calls-per-event, per provider. These are estimates, not contracts:
# a name-based provider spends ~1 resolve + 1 listing + one stats call per
# historical match, across three slots (team_a / team_b / h2h); Highlightly and
# SportDB additionally pay one /statistics call per historical match on both
# sides plus H2H. They exist so preflight can say "your remaining quota covers
# ~4 events, you asked for 40" instead of letting a run discover that halfway
# through, which is how a lopsided artifact gets produced.
ESTIMATED_CALLS_PER_EVENT = {
    "espn-football": 25,
    "espn-tennis": 25,
    "api-football": 25,
    "tennis-abstract": 5,
    "sackmann": 5,
    "understat": 3,
    "highlightly": 35,
    "sportdb": 35,
}
_DEFAULT_CALLS_PER_EVENT = 20

# The .env variable each provider's credential is read from, and whether the
# provider needs one at all. ESPN and the two tennis scrapers are keyless, so
# demanding a credential from them would block a working provider.
CREDENTIAL_ENV_VARS = {
    "api-football": ("API_FOOTBALL_KEY",),
    "highlightly": ("HIGHLIGHTLY_API_KEY", "RAPIDAPI_KEY"),
    "sportdb": ("SPORTDB_API_KEY", "SPORTDB_KEY"),
    "google-sports": ("SERPAPI_KEY",),
}
KEYLESS_PROVIDERS = frozenset({"espn-football", "espn-tennis", "tennis-abstract", "sackmann", "understat"})


def has_credentials(provider: str) -> tuple[bool, str]:
    """(ok, env_var_names) for one provider's credential.

    A missing key used to surface only as a data_gap partway through ENRICH,
    indistinguishable from "the provider had nothing for this team". Checking it
    up front turns it back into what it is: a configuration error.
    """
    variables = CREDENTIAL_ENV_VARS.get(provider)
    if not variables:
        return True, ""
    return bool(get_env(*variables)), " / ".join(variables)


def provider_quota(rate_limiter: RateLimiter, provider: str) -> dict:
    """Quota snapshot for one provider.

    ``RateLimiter`` treats an unconfigured API as unlimited in ``can_request``
    but reports ``get_remaining() == 0`` for it, so the two disagree. Reading
    the effective limit first is what keeps an unlimited provider (ESPN) from
    being reported as exhausted.
    """
    limit, window = rate_limiter._effective_limit(provider)
    credentials_ok, credential_vars = has_credentials(provider)
    base = {
        "provider": provider,
        "window": window,
        "has_credentials": credentials_ok,
        "credential_env": credential_vars,
        "limit_env": limit_env_var(provider),
    }
    if limit is None:
        return {
            **base,
            "limit": None,
            "remaining": None,
            "unlimited": True,
            "available": credentials_ok,
        }
    remaining = rate_limiter.get_remaining(provider)
    return {
        **base,
        "limit": limit,
        "remaining": remaining,
        "used_hint": max(0, limit - remaining),
        "unlimited": False,
        "available": credentials_ok and rate_limiter.can_request(provider, 1),
    }


def providers_for(sports: list[str]) -> list[str]:
    """Every provider ENRICH would call for these sports, deduplicated."""
    providers: list[str] = []
    for sport in sports:
        for provider in (*PROVIDERS_BY_SPORT.get(sport, ()), *NATIVE_ID_PROVIDERS_BY_SPORT.get(sport, ())):
            if provider not in providers:
                providers.append(provider)
    return providers


def affordable_events(quota: dict) -> int | None:
    """How many events this provider's remaining quota covers, or None when
    the provider has no configured limit."""
    if quota["unlimited"] or quota["remaining"] is None:
        return None
    per_event = ESTIMATED_CALLS_PER_EVENT.get(quota["provider"], _DEFAULT_CALLS_PER_EVENT)
    return quota["remaining"] // per_event if per_event else None


def enrich_preflight(
    event_list: EventListV1, rate_limiter: RateLimiter, planned_events: int | None = None
) -> dict:
    """Decide whether ENRICH can produce a meaningful artifact.

    Returns ``{"verdict", "quotas", "usable_providers", "blocked", "reason"}``.

    ``PRECONDITION_FAILED`` is reserved for the case where *no* provider can
    serve any sport in the list -- running then would produce an artifact of
    nothing but data_gaps while still costing a full pass over the events.
    A partially exhausted roster is ``OK``: combining whatever providers are
    left is exactly what this pipeline is for, and every gap is recorded.
    """
    sports = sorted({event.sport for event in event_list.events if event.status == "ACTIVE"})
    if not sports:
        return {
            "verdict": "PRECONDITION_FAILED",
            "reason": "event list contains no ACTIVE events to enrich",
            "quotas": [],
            "usable_providers": [],
            "blocked": [],
            "thin": [],
            "coverage_by_sport": {},
            "recommended_max_events": 0,
        }
    return preflight_for_sports(sports, rate_limiter, planned_events)


def preflight_for_sports(
    sports: list[str], rate_limiter: RateLimiter, planned_events: int | None = None
) -> dict:
    """The same check, addressed by sport rather than by event list.

    Split out so the roster can be checked *before* discovery has run -- the
    morning question is "is today's run worth starting", and answering it should
    not require first spending discovery calls to obtain an event list.
    """
    if not sports:
        return {
            "verdict": "PRECONDITION_FAILED",
            "reason": "no sports to check",
            "quotas": [],
            "usable_providers": [],
            "blocked": [],
            "thin": [],
            "coverage_by_sport": {},
            "recommended_max_events": 0,
        }

    quotas = [provider_quota(rate_limiter, provider) for provider in providers_for(sports)]

    usable: list[str] = []
    blocked: list[dict] = []
    thin: list[dict] = []
    for quota in quotas:
        provider = quota["provider"]
        dead_reason = KNOWN_DEAD_PROVIDERS.get(provider)
        if dead_reason:
            blocked.append({"provider": provider, "reason": dead_reason, "kind": "upstream_unavailable"})
            continue
        if not quota["has_credentials"]:
            blocked.append(
                {
                    "provider": provider,
                    "reason": f"no credential: set {quota['credential_env']} in {ENV_PATH}",
                    "kind": "missing_credentials",
                }
            )
            continue
        if not quota["available"]:
            blocked.append(
                {
                    "provider": provider,
                    "reason": (
                        f"quota exhausted ({quota['used_hint']}/{quota['limit']} per {quota['window']}). "
                        f"Raise {quota['limit_env']} in .env, or after rotating the key run: "
                        f"python3 scripts/simple/reset_provider_quota.py --provider {provider}"
                    ),
                    "kind": "quota_exhausted",
                }
            )
            continue
        usable.append(provider)

        covers = affordable_events(quota)
        quota["covers_events"] = covers
        if planned_events and covers is not None and covers < planned_events:
            thin.append(
                {
                    "provider": provider,
                    "covers_events": covers,
                    "planned_events": planned_events,
                    "reason": (
                        f"remaining quota ({quota['remaining']}) covers about {covers} events, "
                        f"but {planned_events} are planned"
                    ),
                }
            )

    if not usable:
        return {
            "verdict": "PRECONDITION_FAILED",
            "reason": f"no provider available for {', '.join(sports)}",
            "quotas": quotas,
            "usable_providers": [],
            "blocked": blocked,
            "thin": [],
            "coverage_by_sport": {},
            "recommended_max_events": 0,
        }

    by_quota = {q["provider"]: q for q in quotas}
    coverage_by_sport = {
        sport: _two_provider_coverage(sport, usable, by_quota) for sport in sports
    }
    finite = [c for c in coverage_by_sport.values() if c is not None]

    return {
        "verdict": "OK",
        "reason": "",
        "quotas": quotas,
        "usable_providers": usable,
        "blocked": blocked,
        "thin": thin,
        "coverage_by_sport": coverage_by_sport,
        "recommended_max_events": min(finite) if finite else None,
    }


def _two_provider_coverage(sport: str, usable: list[str], by_quota: dict[str, dict]) -> int | None:
    """How many events of ``sport`` can still be seen by *two* providers.

    Two is the number that matters: readiness=READY needs 2+ independent
    providers per priority metric, and cross_provider_agreement needs 2 to say
    anything at all. Reporting the single most generous provider's coverage
    instead would promise 400 events off an unlimited ESPN quota while the only
    provider that could corroborate it runs dry after 7.

    Returns None when at least two of this sport's providers are unlimited.
    """
    sport_providers = [
        p
        for p in (*PROVIDERS_BY_SPORT.get(sport, ()), *NATIVE_ID_PROVIDERS_BY_SPORT.get(sport, ()))
        if p in usable
    ]
    if len(sport_providers) < 2:
        return 0

    coverages = []
    for provider in sport_providers:
        covers = affordable_events(by_quota[provider])
        coverages.append(float("inf") if covers is None else covers)
    coverages.sort(reverse=True)
    second = coverages[1]
    return None if second == float("inf") else int(second)
