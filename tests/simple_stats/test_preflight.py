"""Provider-quota preflight: refuse a run that cannot reach any provider, and
say honestly how many events the remaining quota actually corroborates."""
import pytest

from bet.api_clients.rate_limiter import RateLimiter

from bet.simple_stats.contracts import EventListV1, EventRecord
from bet.simple_stats.preflight import (
    KNOWN_DEAD_PROVIDERS,
    enrich_preflight,
    provider_quota,
    providers_for,
)


def _event(sport="football", status="ACTIVE", event_id=None, competition="Premier League"):
    kwargs = dict(
        event_id=event_id or f"evt-{sport}-{status}",
        sport=sport,
        competition=competition,
        start_time="2026-08-25T18:00:00+00:00",
        identity_confidence="CONFIRMED",
        status=status,
    )
    if sport == "tennis":
        kwargs.update(player_one="P1", player_two="P2")
    else:
        kwargs.update(home_team="A", away_team="B")
    return EventRecord(**kwargs)


def _list(*events):
    return EventListV1(run_id="r", generated_at="x", date="2026-08-25", sports=["football"], events=list(events))


def _limiter(tmp_path, limits):
    return RateLimiter(usage_dir=tmp_path / "usage", limits=limits, rate_limits={})


def test_unlimited_provider_is_not_reported_as_exhausted(tmp_path):
    """RateLimiter.get_remaining() returns 0 for an API with no configured
    limit while can_request() returns True. Reading get_remaining() alone
    would have marked every unconfigured provider dead."""
    quota = provider_quota(_limiter(tmp_path, {}), "tennis-abstract")
    assert quota["unlimited"] is True
    assert quota["available"] is True
    assert quota["remaining"] is None


def test_exhausted_provider_is_reported_unavailable(tmp_path):
    limiter = _limiter(tmp_path, {"highlightly": 2})
    for _ in range(2):
        limiter.record_request("highlightly", "/statistics", 1)
    quota = provider_quota(limiter, "highlightly")
    assert quota["available"] is False
    assert quota["remaining"] == 0


def test_preflight_blocks_when_no_provider_is_reachable(tmp_path):
    """Every football provider either exhausted or upstream-dead -> starting
    would spend a full pass over the events to produce only data_gaps."""
    limits = {p: 1 for p in providers_for(["football"])}
    limiter = _limiter(tmp_path, limits)
    for provider in limits:
        limiter.record_request(provider, "/x", 1)

    result = enrich_preflight(_list(_event()), limiter)
    assert result["verdict"] == "PRECONDITION_FAILED"
    assert result["usable_providers"] == []
    assert "no provider available" in result["reason"]


def test_preflight_passes_when_one_provider_survives(tmp_path):
    """A partially exhausted roster is OK -- combining what is left is the
    whole point, and each missing provider becomes a recorded data_gap."""
    limits = {p: 1 for p in providers_for(["football"])}
    limits["espn-football"] = 10_000
    limiter = _limiter(tmp_path, limits)
    for provider in limits:
        if provider != "espn-football":
            limiter.record_request(provider, "/x", 1)

    result = enrich_preflight(_list(_event()), limiter)
    assert result["verdict"] == "OK"
    assert "espn-football" in result["usable_providers"]


def test_preflight_blocks_an_event_list_with_nothing_active(tmp_path):
    blocked = _event(status="BLOCKED_IDENTITY")
    result = enrich_preflight(_list(blocked), _limiter(tmp_path, {}))
    assert result["verdict"] == "PRECONDITION_FAILED"
    assert "no ACTIVE events" in result["reason"]


def test_dead_providers_are_distinguished_from_exhausted_ones(tmp_path):
    """A quota clears at midnight; a 404'd upstream repository does not. An
    agent must be able to tell those apart before scheduling a retry."""
    result = enrich_preflight(_list(_event()), _limiter(tmp_path, {}))
    kinds = {b["provider"]: b["kind"] for b in result["blocked"]}
    for provider in KNOWN_DEAD_PROVIDERS:
        if provider in kinds:
            assert kinds[provider] == "upstream_unavailable"


def test_coverage_reports_two_provider_reach_not_the_most_generous_one(tmp_path):
    """readiness=READY and cross_provider_agreement both need 2+ providers, so
    the recommendation tracks the *second* best quota. Reporting the best one
    would promise hundreds of events off an unlimited ESPN while the only
    provider that could corroborate it runs dry after a handful.
    """
    # Exactly one generous provider (ESPN) and one thin one (Highlightly); the
    # rest exhausted, so Highlightly is the only thing that can corroborate ESPN.
    limiter = _limiter(
        tmp_path,
        {
            "espn-football": 10_000,
            "highlightly": 70,
            "api-football": 1,
            "understat": 1,
            "bzzoiro": 1,
        },
    )
    limiter.record_request("api-football", "/x", 1)
    limiter.record_request("understat", "/x", 1)
    limiter.record_request("bzzoiro", "/x", 1)

    # Three fixtures, so quota is the binding constraint rather than the size
    # of the slate: coverage can never exceed the events actually on it.
    slate = _list(*(_event(event_id=f"evt-{i}") for i in range(3)))
    result = enrich_preflight(slate, limiter, planned_events=40)
    assert sorted(result["usable_providers"]) == ["espn-football", "highlightly"]

    # ESPN alone covers 10000/25 = 400 events, but Highlightly's 70/35 = 2 is
    # what bounds two-provider coverage, and 2 is what must be reported.
    assert result["coverage_by_sport"]["football"] == 2
    assert result["recommended_max_events"] == 2


def test_coverage_is_bounded_by_what_a_provider_can_actually_serve(tmp_path):
    """Quota is not capability: an unlimited ESPN quota corroborates nothing in
    a competition ESPN has no surface for, which is how 2026-08-25 advertised
    three corroborable events and produced a sheet whose 140 rows were all
    SINGLE_SOURCE.

    The Saudi league was the original example, on the assumption that ESPN could
    not serve it. It can -- as ksa.1, with an 18-team directory; the old sau.1
    pin was simply a dead code. Poland is the honest example now: pol.1 404s, so
    the Ekstraklasa has no ESPN surface under any code, and resolving it returns
    no code at all rather than a pin that fails later."""
    # api-football and highlightly exhausted, exactly as they were that day, so
    # ESPN and SportDB are the only candidates left to corroborate each other.
    # bzzoiro is exhausted alongside them: this test is about ESPN's *reach*, and
    # a second provider with quota to spare would answer the question with its
    # own coverage instead.
    limiter = _limiter(
        tmp_path,
        {
            "espn-football": 10_000,
            "sportdb": 10_000,
            "api-football": 1,
            "highlightly": 1,
            "bzzoiro": 1,
        },
    )
    limiter.record_request("api-football", "/x", 1)
    limiter.record_request("highlightly", "/x", 1)
    limiter.record_request("bzzoiro", "/x", 1)
    slate = _list(
        *(
            _event(event_id=f"polish-{i}", competition="Ekstraklasa - Poland")
            for i in range(3)
        )
    )
    result = enrich_preflight(slate, limiter, planned_events=3)
    assert "espn-football" in result["usable_providers"]
    assert result["coverage_by_sport"]["football"] == 0


def test_thin_quota_is_warned_about_before_the_run(tmp_path):
    limiter = _limiter(tmp_path, {"espn-football": 10_000, "highlightly": 70, "api-football": 10_000})
    result = enrich_preflight(_list(_event()), limiter, planned_events=40)
    thin = {t["provider"]: t for t in result["thin"]}
    assert "highlightly" in thin
    assert thin["highlightly"]["covers_events"] < 40


@pytest.mark.parametrize("sport,expected", [("football", "highlightly"), ("tennis", "tennis-abstract")])
def test_providers_for_covers_both_name_and_native_id_families(sport, expected):
    assert expected in providers_for([sport])


# ── Credentials ──────────────────────────────────────────────────────────

def _blank_env(tmp_path, monkeypatch, contents=""):
    import bet.api_clients.env as envmod
    path = tmp_path / ".env"
    path.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(envmod, "ENV_PATH", path)
    envmod.reload_env()
    for var in ("HIGHLIGHTLY_API_KEY", "RAPIDAPI_KEY", "SPORTDB_API_KEY",
                "SPORTDB_KEY", "API_FOOTBALL_KEY", "SERPAPI_KEY", "BZZORIO_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_missing_key_is_caught_before_the_run_not_as_a_data_gap(tmp_path, monkeypatch):
    """A missing credential used to surface partway through ENRICH as a
    data_gap indistinguishable from "the provider had no data for this team"."""
    from bet.simple_stats.preflight import has_credentials
    _blank_env(tmp_path, monkeypatch)

    ok, variables = has_credentials("highlightly")
    assert ok is False
    assert "HIGHLIGHTLY_API_KEY" in variables


def test_keyless_providers_are_never_blocked_for_credentials(tmp_path, monkeypatch):
    """ESPN and the tennis scrapers need no key; demanding one would block a
    working provider."""
    from bet.simple_stats.preflight import KEYLESS_PROVIDERS, has_credentials
    _blank_env(tmp_path, monkeypatch)
    for provider in KEYLESS_PROVIDERS:
        assert has_credentials(provider)[0] is True


def test_preflight_reports_missing_credentials_separately_from_exhausted_quota(tmp_path, monkeypatch):
    _blank_env(tmp_path, monkeypatch, "API_FOOTBALL_KEY=present\n")
    limiter = _limiter(tmp_path, {})
    result = enrich_preflight(_list(_event()), limiter)

    kinds = {b["provider"]: b["kind"] for b in result["blocked"]}
    assert kinds.get("highlightly") == "missing_credentials"
    assert kinds.get("bzzoiro") == "missing_credentials"
    assert "api-football" in result["usable_providers"]


def test_quota_exhausted_message_says_how_to_clear_it(tmp_path, monkeypatch):
    """After rotating a key the stale local counter still reads exhausted, so
    the message has to name the reset command and the .env override."""
    _blank_env(tmp_path, monkeypatch, "HIGHLIGHTLY_API_KEY=k\nSPORTDB_API_KEY=k\nAPI_FOOTBALL_KEY=k\n")
    limiter = _limiter(tmp_path, {"highlightly": 1})
    limiter.record_request("highlightly", "/x", 1)

    result = enrich_preflight(_list(_event()), limiter)
    reason = next(b["reason"] for b in result["blocked"] if b["provider"] == "highlightly")
    assert "reset_provider_quota.py" in reason
    assert "BET_LIMIT_HIGHLIGHTLY" in reason


# ── Reset ────────────────────────────────────────────────────────────────

def test_reset_clears_the_counter_so_a_rotated_key_is_usable_again(tmp_path):
    limiter = _limiter(tmp_path, {"highlightly": 2})
    for _ in range(2):
        limiter.record_request("highlightly", "/statistics", 1)
    assert limiter.can_request("highlightly") is False

    discarded = limiter.reset("highlightly")
    assert discarded == 2
    assert limiter.get_remaining("highlightly") == 2
    assert limiter.can_request("highlightly") is True


def test_reset_is_idempotent_on_an_untouched_provider(tmp_path):
    limiter = _limiter(tmp_path, {"highlightly": 5})
    assert limiter.reset("highlightly") == 0
    assert limiter.get_remaining("highlightly") == 5


def test_usage_snapshot_names_the_override_var_and_the_counter_file(tmp_path):
    limiter = _limiter(tmp_path, {"highlightly": 5})
    limiter.record_request("highlightly", "/x", 1)
    snap = limiter.usage_snapshot("highlightly")
    assert snap["used"] == 1
    assert snap["limit"] == 5
    assert snap["limit_env_var"] == "BET_LIMIT_HIGHLIGHTLY"
    assert snap["usage_file"].endswith(".json")


# ── Morning preflight: the roster check that runs before discovery ──────────


def test_preflight_for_sports_needs_no_event_list(monkeypatch, tmp_path):
    """The morning question -- 'is today worth starting' -- must be answerable
    before spending discovery calls to obtain an event list."""
    from bet.simple_stats.preflight import preflight_for_sports

    limiter = _limiter(tmp_path, {})
    monkeypatch.setattr(
        "bet.simple_stats.preflight.has_credentials", lambda p: (True, "X_KEY")
    )
    result = preflight_for_sports(["football"], limiter, planned_events=10)
    assert result["verdict"] == "OK"
    assert result["usable_providers"]


def test_preflight_for_sports_and_enrich_preflight_agree(monkeypatch, tmp_path):
    """enrich_preflight delegates to it; a divergence would mean the morning
    check and the run's own gate could disagree."""
    from bet.simple_stats.preflight import enrich_preflight, preflight_for_sports

    limiter = _limiter(tmp_path, {})
    monkeypatch.setattr(
        "bet.simple_stats.preflight.has_credentials", lambda p: (True, "X_KEY")
    )
    event_list = _list(_event("football"))
    from_events = enrich_preflight(event_list, limiter, planned_events=10)
    from_sports = preflight_for_sports(["football"], limiter, planned_events=10)
    assert from_events["usable_providers"] == from_sports["usable_providers"]
    assert from_events["coverage_by_sport"] == from_sports["coverage_by_sport"]
    assert from_events["recommended_max_events"] == from_sports["recommended_max_events"]


def test_empty_sport_list_is_precondition_failed(tmp_path):
    from bet.simple_stats.preflight import preflight_for_sports

    limiter = _limiter(tmp_path, {})
    result = preflight_for_sports([], limiter)
    assert result["verdict"] == "PRECONDITION_FAILED"
    assert result["recommended_max_events"] == 0
