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
from bet.simple_stats.providers import (
    NATIVE_ID_PROVIDERS_BY_SPORT,
    PRIMARY_PROVIDER_BY_SPORT,
    PROVIDERS_BY_SPORT,
)

# Providers known to have no usable data source at all, independent of quota:
# sackmann's GitHub repo returns 404 and the understat package will not build.
# They are reported separately from "exhausted" so an agent does not read a
# permanent upstream outage as a quota problem that will clear tomorrow.
KNOWN_DEAD_PROVIDERS = {
    # Not the CSVs -- the repositories. github.com/JeffSackmann/tennis_atp and
    # tennis_wta both answer "Not Found" from the GitHub API (checked
    # 2026-08-28) while the account itself is alive and still publishes
    # tennis_MatchChartingProject, so the data was moved or withdrawn rather
    # than the network being at fault. Removed from PROVIDERS_BY_SPORT the same
    # day; kept here so the morning check keeps saying so out loud.
    "sackmann": "upstream repositories tennis_atp/tennis_wta return HTTP 404",
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
    # Tennis is the one entry whose cost is not really per event. ESPN publishes
    # tennis only through the daily scoreboard, one request covers every player
    # in every tournament running that day, and the scan memoises each date for
    # the life of the process -- so the whole slate costs at most one scan per
    # tour (102 requests, see _tennis_scan_offsets) however many fixtures it
    # holds, and each additional event costs the athlete-id lookup and nothing
    # else. Three is that marginal cost. It used to read 25, which was the old
    # design's genuine per-event price: a scan, and then up to twenty more
    # scoreboard fetches for every fixture whose set scores that scan had
    # already parsed and thrown away.
    "espn-tennis": 3,
    "api-football": 25,
    "tennis-abstract": 5,
    "sackmann": 5,
    "understat": 3,
    "highlightly": 35,
    "sportdb": 35,
    # Match stats + both sides' last-ten (a listing call plus one /stats per
    # historical match) + the H2H slot. Player props are *not* counted here:
    # they are opt-in per run (run_enrich.py --player-props) and priced
    # separately, so folding them in would understate how many events a
    # props-free run can afford.
    "bzzoiro": 30,
    # Cheaper per event than football despite being the same provider, because
    # one /h2h/ call serves all three slots (it returns both players' recent
    # form alongside the meetings) and /matches/{id}/ returns the box score
    # without a second stats call: 1 listing + 5 box scores per side + up to 5
    # h2h box scores. Against a 95/day ceiling that is about six fixtures, and
    # preflight saying "six" is the point of this number existing.
}
_DEFAULT_CALLS_PER_EVENT = 20

# The .env variable each provider's credential is read from, and whether the
# provider needs one at all. ESPN and the two tennis scrapers are keyless, so
# demanding a credential from them would block a working provider.
CREDENTIAL_ENV_VARS = {
    "api-football": ("API_FOOTBALL_KEY",),
    "highlightly": ("HIGHLIGHTLY_API_KEY", "RAPIDAPI_KEY"),
    # Provider name is "bzzoiro" (the site's spelling); the key the provider
    # issues is BZZORIO_KEY. The mismatch is theirs, not a typo here.
    "bzzoiro": ("BZZORIO_KEY",),
    # Same credential, separate provider key: the two products have separate
    # quota buckets, so they need separate daily counters.
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
        # Persisted by the client boundary on an HTTP 402. Carried on every
        # quota dict, including the unlimited branch: a provider with no local
        # cap can still be refused for billing.
        "entitlement_fault": rate_limiter.entitlement_fault(provider),
    }
    if limit is None:
        return {
            **base,
            "limit": None,
            "remaining": None,
            "unlimited": True,
            "available": credentials_ok and not base["entitlement_fault"],
        }
    remaining = rate_limiter.get_remaining(provider)
    return {
        **base,
        "limit": limit,
        "remaining": remaining,
        "used_hint": max(0, limit - remaining),
        "unlimited": False,
        "available": (
            credentials_ok
            and not base["entitlement_fault"]
            and rate_limiter.can_request(provider, 1)
        ),
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


def sports_within_quota(
    event_list: "EventListV1", rate_limiter: "RateLimiter"
) -> frozenset[str]:
    """Sports whose providers can afford their entire slate today.

    Handed to ``enrich._apportion_cap`` so the run cap is spent only where a
    quota is actually scarce. A sport every one of whose providers is unlimited
    -- or has enough left to cover every fixture of that sport on the board --
    is not competing for the budget and must not be trimmed to fund a sport
    that is.

    Tennis is the whole reason: ``tennis-abstract`` is a keyless scrape with no
    daily cap and ``espn-tennis`` allows about 3,300 events a day, against a
    tennis slate that has never exceeded 46. It was still being cut, because
    the split was proportional to slate size and blind to cost -- 9 of 38
    fixtures on the 2026-09-02 board.

    Measured per sport rather than hardcoded, so this stays true if a tennis
    provider gains a limit or a football provider loses one. A sport with no
    usable provider is *not* returned: it has no coverage to protect, and
    exempting it would hand it slots it cannot spend.
    """
    counts: dict[str, int] = {}
    for event in event_list.events:
        if event.status == "ACTIVE":
            counts[event.sport] = counts.get(event.sport, 0) + 1

    out: set[str] = set()
    for sport, needed in counts.items():
        providers = [
            *PROVIDERS_BY_SPORT.get(sport, ()),
            *NATIVE_ID_PROVIDERS_BY_SPORT.get(sport, ()),
        ]
        if not providers:
            continue
        affordable = True
        usable = 0
        for provider in providers:
            quota = provider_quota(rate_limiter, provider)
            if not quota.get("available"):
                # An unusable provider cannot make the sport unaffordable --
                # it simply will not be called. Judge on the ones that can run.
                continue
            usable += 1
            covers = affordable_events(quota)
            if covers is not None and covers < needed:
                affordable = False
                break
        if usable and affordable:
            out.add(sport)
    return frozenset(out)


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
    return preflight_for_sports(
        sports,
        rate_limiter,
        planned_events,
        # Only the event-list entrypoint knows which competitions are on the
        # slate, and capability is per competition. preflight_for_sports is
        # deliberately callable before discovery, so it cannot compute these.
        capability_caps=_capability_caps(event_list, rate_limiter),
    )


def preflight_for_sports(
    sports: list[str],
    rate_limiter: RateLimiter,
    planned_events: int | None = None,
    capability_caps: dict[str, dict[str, int]] | None = None,
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
            # An entitlement fault outranks the quota story even when the
            # counter also reads empty, because the two need opposite actions:
            # a spent quota clears tomorrow or yields to a higher BET_LIMIT_*,
            # a 402 yields only to a purchase. Reporting the second as the
            # first is how an operator spends a morning resetting a counter.
            entitlement = quota.get("entitlement_fault")
            if entitlement:
                blocked.append(
                    {
                        "provider": provider,
                        "reason": (
                            f"entitlement required, not quota: {entitlement}. "
                            f"Raising {quota['limit_env']} and resetting the counter "
                            f"will both do nothing -- this needs a plan change at the provider."
                        ),
                        "kind": "entitlement_required",
                    }
                )
                continue
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
    caps = capability_caps or {}
    coverage_by_sport = {
        sport: _slate_coverage(sport, usable, by_quota, caps.get(sport, {}))
        for sport in sports
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


def _capability_caps(
    event_list: EventListV1, rate_limiter: RateLimiter
) -> dict[str, dict[str, int]]:
    """``{sport: {provider: max events it can actually serve}}``.

    Quota is not capability. Everything below this function reasoned purely
    about how many calls a provider could still afford, which on 2026-08-25
    advertised "football two-provider coverage: 3" off an unlimited ESPN quota
    and then produced a sheet in which all 140 rows were SINGLE_SOURCE: ESPN
    cannot serve the Saudi and Korean leagues that made up the slate at all, so
    the second provider it was counting never existed.

    Football capability is decided per *competition* (espn-football reaches the
    headline leagues and 404s the rest). Tennis capability is decided per
    *player*, which is the same problem wearing a different key: tennis-abstract
    answers 200 for a player it does not have on the route asked -- serving
    Benoit Paire's page for every WTA request -- so "the provider is up" says
    nothing about whether it can serve tonight's names. A tennis slate the
    provider cannot identify is a slate it contributes nothing to, and preflight
    should say that in the morning rather than let ANALYZE discover it.

    Both probes ride on free, unlimited providers and are memoised, so this
    costs unmetered requests only for the distinct leagues and players of one
    day's slate.
    """
    caps: dict[str, dict[str, int]] = {}
    football = _football_capability(event_list, rate_limiter)
    if football is not None:
        caps["football"] = football
    tennis = _tennis_capability(event_list, rate_limiter)
    if tennis is not None:
        caps["tennis"] = tennis
    return caps


def _active(event_list: EventListV1, sport: str) -> list:
    return [e for e in event_list.events if e.status == "ACTIVE" and e.sport == sport]


def _football_capability(
    event_list: EventListV1, rate_limiter: RateLimiter
) -> dict[str, int] | None:
    from bet.api_clients.espn import get_espn_league_for_competition
    from bet.simple_stats.providers import _espn_league_has_team_directory

    football_events = _active(event_list, "football")
    if not football_events:
        return None
    servable = 0
    for event in football_events:
        competition = getattr(event, "competition", "") or ""
        if not competition:
            continue
        league = get_espn_league_for_competition(competition)
        if league and _espn_league_has_team_directory("football", league, rate_limiter):
            servable += 1
    # bzzoiro's capability needs no probe at all: it is addressed by native id,
    # so a fixture it can serve is exactly a fixture it discovered, and
    # discovery already recorded that. This is the number that bounds a
    # readable slate -- espn-football's is the corroborator's reach, which is
    # worth reporting and is not what the run size should be planned against.
    covered = sum(
        1
        for event in football_events
        if getattr(event, "provider_team_ids", {}).get("bzzoiro")
        and getattr(event, "source_ids", {}).get("bzzoiro")
    )
    return {"espn-football": servable, "bzzoiro": covered}


def _tennis_capability(
    event_list: EventListV1, rate_limiter: RateLimiter
) -> dict[str, int] | None:
    """How many of today's tennis fixtures each name-driven provider can identify.

    An event counts only when the provider resolves *both* players: a fixture
    with one side identified yields no comparison, no H2H and no per-side line,
    so counting it would overstate coverage in exactly the direction that
    already burned football.

    Identity is asked for, history is not. Resolution is the step that fails --
    and the step whose failure used to be invisible, because tennis-abstract's
    resolve_team_id echoed the caller's string back and espn-tennis's athlete
    search is the only thing standing between a name and the wrong tour.
    """
    from bet.simple_stats.providers import resolve_tennis_player

    tennis_events = _active(event_list, "tennis")
    if not tennis_events:
        return None

    providers = ("tennis-abstract", "espn-tennis")
    counts = dict.fromkeys(providers, 0)
    for event in tennis_events:
        competition = getattr(event, "competition", "") or ""
        for provider in providers:
            # Tennis carries its sides as player_one/player_two; home/away are
            # the football spelling and are None here (contracts.EventRecord).
            both = all(
                name and resolve_tennis_player(provider, name, competition, rate_limiter)
                for name in (event.player_one, event.player_two)
            )
            if both:
                counts[provider] += 1
    return counts


def _slate_coverage(
    sport: str,
    usable: list[str],
    by_quota: dict[str, dict],
    capability_caps: dict[str, int] | None = None,
) -> int | None:
    """How many events of ``sport`` this run can produce a readable dossier for.

    For a sport with a primary provider (PRIMARY_PROVIDER_BY_SPORT) that is the
    primary's own coverage, bounded by both what it can afford and what it can
    reach. Nothing else can stand in for it: since 2026-09-02 readiness is
    measured on the primary's sample, the slate gate refuses fixtures it never
    discovered, and a corroborator does not make a fixture readable -- it makes
    a readable one checked.

    This used to be ``_two_provider_coverage`` and reported the *second* best
    provider's reach, on the premise that READY needed two providers. It did,
    and the consequence was that football's planned run size was a measurement
    of espn-football's league map: on 2026-09-02 it advertised 114 against a
    bzzoiro-covered slate of 52, and ``recommended_max_events`` of 29 was
    derived from a provider contributing six metrics out of fifty-five.

    Sports with no primary keep the two-provider rule, and there the original
    reasoning still holds exactly: with no source of record, a second provider
    is the only check there is, so the run can only plan for what two of them
    can jointly reach.

    ``capability_caps`` bounds a provider by what it can serve rather than what
    it can afford; an unlimited provider that reaches none of today's leagues
    contributes 0, not infinity. Returns None when the answer is unbounded.
    """
    capability_caps = capability_caps or {}

    def reach(provider: str) -> float:
        covers = affordable_events(by_quota[provider])
        affordable = float("inf") if covers is None else covers
        cap = capability_caps.get(provider)
        return affordable if cap is None else min(affordable, cap)

    primary = PRIMARY_PROVIDER_BY_SPORT.get(sport)
    if primary is not None:
        if primary not in usable:
            return 0
        covered = reach(primary)
        return None if covered == float("inf") else int(covered)

    sport_providers = [
        p
        for p in (*PROVIDERS_BY_SPORT.get(sport, ()), *NATIVE_ID_PROVIDERS_BY_SPORT.get(sport, ()))
        if p in usable
    ]
    if len(sport_providers) < 2:
        return 0

    coverages = [reach(provider) for provider in sport_providers]
    coverages.sort(reverse=True)
    second = coverages[1]
    return None if second == float("inf") else int(second)
