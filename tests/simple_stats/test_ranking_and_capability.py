"""Regressions for the five defects found reviewing the 2026-08-25 run.

Each test names the failure it locks out, because every one of these shipped a
sheet that looked finished: a ranking key that existed only in prose, a push
buying a confidence tier, a date format silently disabling corroboration, and a
provider searching Saudi clubs in the Premier League.
"""
from __future__ import annotations

import pytest

from bet.simple_stats.analyze import (
    _cross_provider_agreement,
    _day_key,
    compute_hit_rate,
    wilson_lower_bound,
    corroborated_matches,
)
from bet.simple_stats.contracts import ProviderValue


class TestWilsonLowerBound:
    def test_empty_sample_is_the_floor_not_a_missing_value(self):
        assert wilson_lower_bound(0, 0) == 0.0

    def test_a_perfect_thin_sample_is_not_certainty(self):
        """4/4 is a hit_rate of 1.00. Ranking on that put four observations at
        the top of the sheet, which is the whole reason this function exists."""
        assert wilson_lower_bound(4, 4) == pytest.approx(0.5101, abs=1e-4)

    def test_more_evidence_at_the_same_rate_ranks_higher(self):
        """The property the ranking actually needs: same ratio, bigger sample,
        strictly higher floor."""
        assert wilson_lower_bound(3, 4) < wilson_lower_bound(9, 12) < wilson_lower_bound(75, 100)

    def test_it_never_exceeds_the_point_estimate(self):
        for hits, n in ((1, 1), (4, 4), (9, 12), (50, 100), (0, 7)):
            assert wilson_lower_bound(hits, n) <= hits / n

    def test_it_stays_in_the_unit_interval(self):
        for hits, n in ((0, 1), (0, 30), (1, 30), (30, 30)):
            assert 0.0 <= wilson_lower_bound(hits, n) <= 1.0


class TestPushesDoNotCount:
    def test_a_value_on_the_line_settles_nothing(self):
        """A whole-number line: 10 is neither over nor under 10."""
        hits, settled, pushes = compute_hit_rate([8.0, 10.0, 12.0], 10.0, "OVER")
        assert (hits, settled, pushes) == (1, 2, 1)

    def test_both_sides_of_a_line_agree_on_the_settled_count(self):
        values = [8.0, 10.0, 10.0, 12.0]
        over_hits, over_n, _ = compute_hit_rate(values, 10.0, "OVER")
        under_hits, under_n, _ = compute_hit_rate(values, 10.0, "UNDER")
        assert over_n == under_n == 2
        # With pushes removed, the two sides partition the settled sample.
        assert over_hits + under_hits == over_n

    def test_football_half_lines_never_push(self):
        hits, settled, pushes = compute_hit_rate([8.0, 9.0, 10.0, 11.0], 9.5, "OVER")
        assert (hits, settled, pushes) == (2, 4, 0)

    def test_an_all_push_sample_settles_nothing_rather_than_reporting_zero_hits(self):
        """sample_size 0 is what analyze_dossier skips on. Reporting 0/3 here
        would instead publish a 0% row built entirely from pushes."""
        assert compute_hit_rate([5.0, 5.0, 5.0], 5.0, "UNDER") == (0, 0, 3)


class TestDayKey:
    def test_iso_with_a_time_and_zone(self):
        assert _day_key("2026-08-22T10:30:00.000Z") == "2026-08-22"

    def test_bare_iso_date(self):
        assert _day_key("2026-08-22") == "2026-08-22"

    @pytest.mark.parametrize(
        "stamp",
        ["22/08/2026", "22.08.2026", "22-08-2026", "2026/08/22", "22 Aug 2026"],
    )
    def test_non_iso_formats_land_on_the_same_day(self, stamp):
        assert _day_key(stamp) == "2026-08-22"

    def test_unparseable_is_empty_not_a_bucket(self):
        """"" is what _cross_provider_agreement treats as "cannot tell which
        match this is". A junk string must not group with other junk."""
        assert _day_key("last tuesday") == ""
        assert _day_key(None) == ""
        assert _day_key("") == ""

    def test_two_providers_stamping_differently_still_corroborate(self):
        """The bug this closes: bucketing on raw[:10] put 22/08/2026 in its own
        bucket, so a corroborated match reported SINGLE_SOURCE -- which looks
        exactly like a provider that had nothing to say."""
        observations = [
            ProviderValue(
                provider="sportdb", value=9.0, match_id="m1",
                match_date="2026-08-22T10:30:00.000Z", opponent="Al-Fayha",
                observed_at="2026-08-25T12:00:00Z",
            ),
            ProviderValue(
                provider="highlightly", value=9.0, match_id="m1-other-id",
                match_date="22/08/2026", opponent="Al Fayha",
                observed_at="2026-08-25T12:00:00Z",
            ),
        ]
        # Asserted on the corroboration count, not on AGREE: the bug being
        # closed is the date bucketing, and one corroborated match is below
        # MIN_CORROBORATED_MATCHES for reasons that have nothing to do with
        # date formats.
        assert corroborated_matches("corners_total", observations) == 1

    def test_a_real_disagreement_still_surfaces(self):
        observations = [
            ProviderValue(
                provider="sportdb", value=4.0, match_id="m1",
                match_date="2026-08-22T10:30:00.000Z", opponent="Al-Fayha",
                observed_at="2026-08-25T12:00:00Z",
            ),
            ProviderValue(
                provider="highlightly", value=11.0, match_id="m2",
                match_date="22/08/2026", opponent="Al Fayha",
                observed_at="2026-08-25T12:00:00Z",
            ),
        ]
        assert _cross_provider_agreement("corners_total", observations) == "DISAGREE"


class TestEspnLeagueCapability:
    """espn-football must refuse a league it cannot serve rather than fall back
    to the eng.1 client, which is how 'Abha Club' came to be searched among
    Premier League teams."""

    def test_unmapped_competition_is_refused(self):
        from bet.api_clients.rate_limiter import RateLimiter
        from bet.simple_stats.providers import (
            ProviderLeagueUnsupported,
            _provider_client,
        )

        with pytest.raises(ProviderLeagueUnsupported, match="no ESPN league code"):
            _provider_client("espn-football", "Superettan - Sweden", RateLimiter())

    def test_missing_competition_is_refused(self):
        from bet.api_clients.rate_limiter import RateLimiter
        from bet.simple_stats.providers import (
            ProviderLeagueUnsupported,
            _provider_client,
        )

        with pytest.raises(ProviderLeagueUnsupported, match="no competition"):
            _provider_client("espn-football", "", RateLimiter())

    def test_a_league_without_a_team_directory_is_refused(self, monkeypatch):
        # Saudi Arabia used to be the example here, on a sau.1 pin. ESPN does
        # serve the Saudi league -- as ksa.1, with an 18-team directory -- so
        # the refusal is now provoked by seeding the probe cache instead of by
        # a code that was dead all along.
        from bet.api_clients.rate_limiter import RateLimiter
        from bet.simple_stats import providers

        monkeypatch.setattr(
            providers,
            "_ESPN_TEAM_DIRECTORY",
            {"ksa.1": providers._ESPNDirectory(served=False)},
        )
        with pytest.raises(providers.ProviderLeagueUnsupported, match="no team directory"):
            providers._provider_client("espn-football", "Saudi Pro League", RateLimiter())

    def test_a_two_hundred_with_an_empty_directory_is_also_refused(self, monkeypatch):
        """ESPN answers 200 with no teams for retired codes (cze.1, fin.1,
        usa.w.1, irl.1 -- verified 2026-08-28). Treating any 200 as success let
        those past this gate, and resolve_team_id then failed as a team-name
        problem."""
        from bet.api_clients.rate_limiter import RateLimiter
        from bet.simple_stats import providers

        monkeypatch.setattr(
            providers,
            "_ESPN_TEAM_DIRECTORY",
            {
                "esp.1": providers._ESPNDirectory(
                    served=True, league_name="Spanish LALIGA", team_count=0
                )
            },
        )
        with pytest.raises(providers.ProviderLeagueUnsupported, match="no team directory"):
            providers._provider_client("espn-football", "La Liga - Spain", RateLimiter())

    def test_a_pin_espns_own_league_name_contradicts_is_refused(self, monkeypatch):
        """The check that catches a wrong division or gender inside the right
        country -- the pin that otherwise answers with a real team and a real
        season and feeds cross_provider_agreement without ever raising."""
        from bet.api_clients.rate_limiter import RateLimiter
        from bet.simple_stats import providers

        monkeypatch.setattr(
            providers,
            "_ESPN_TEAM_DIRECTORY",
            {
                "esp.1": providers._ESPNDirectory(
                    served=True, league_name="Spanish LALIGA", team_count=20
                )
            },
        )
        monkeypatch.setattr(
            "bet.api_clients.espn.get_espn_league_for_competition", lambda _c: "esp.1"
        )
        with pytest.raises(providers.ProviderLeagueUnsupported, match="not trustworthy"):
            providers._provider_client("espn-football", "Serie A - Italy", RateLimiter())

    def test_a_league_with_a_team_directory_is_built_and_scoped(self, monkeypatch):
        from bet.api_clients.rate_limiter import RateLimiter
        from bet.simple_stats import providers

        monkeypatch.setattr(
            providers,
            "_ESPN_TEAM_DIRECTORY",
            {
                "esp.1": providers._ESPNDirectory(
                    served=True, league_name="Spanish LALIGA", team_count=20
                )
            },
        )
        client = providers._provider_client("espn-football", "La Liga - Spain", RateLimiter())
        assert client.league == "esp.1"

    def test_the_directory_probe_runs_once_per_league(self, monkeypatch):
        """ENRICH fans providers out over a thread pool, so an unmemoised probe
        would issue one /teams request per fixture."""
        from bet.api_clients.rate_limiter import RateLimiter
        from bet.simple_stats import providers

        calls = []

        class _Probe:
            def __init__(self, *a, **kw):
                pass

            def _request(self, path):
                calls.append(path)
                return {}

        monkeypatch.setattr(providers, "_ESPN_TEAM_DIRECTORY", {})
        monkeypatch.setattr("bet.api_clients.espn.ESPNClient", _Probe)
        rate_limiter = RateLimiter()
        for _ in range(4):
            providers._espn_league_has_team_directory("football", "xyz.1", rate_limiter)
        assert calls == ["/teams"]

    def test_espn_tennis_keeps_its_unscoped_fallback(self):
        """Tennis resolves players through ESPN's global search API, so refusing
        to build a client would break the only sport that corroborates today."""
        from bet.api_clients.rate_limiter import RateLimiter
        from bet.simple_stats.providers import _provider_client

        client = _provider_client("espn-tennis", "WTA Monterrey Open", RateLimiter())
        assert client is not None
