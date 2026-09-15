"""SackmannClient: ATP/WTA Tour match stats via stats.tennismylife.org.

Restored 2026-09-15 pointed at a new host (the original GitHub repos 404'd
2026-08-28). These tests fix the contract that matters to the rest of the
pipeline: the stats dict's keys (``aces``, ``double_faults``, ``games_won``,
``total_games``, ``total_sets``) are exactly what
``simple_stats/providers.py``'s ``_TENNIS_MATCH_STAT_ALIASES`` expects --
the same table tennis-abstract feeds -- so this client plugs into it without
a second alias table.
"""
from __future__ import annotations

import pytest

from bet.api_clients.rate_limiter import RateLimiter
from bet.api_clients.sackmann_adapter import SackmannClient


@pytest.fixture
def isolated_cache_dir(tmp_path, monkeypatch):
    from bet.api_clients import base_client

    cache_dir = tmp_path / "stats_cache"
    monkeypatch.setattr(base_client, "CACHE_DIR", cache_dir)
    return cache_dir


@pytest.fixture
def client(isolated_cache_dir):
    return SackmannClient(RateLimiter())


_HEADER = (
    "tourney_id,tourney_name,surface,draw_size,tourney_level,indoor,tourney_date,"
    "match_num,winner_id,winner_seed,winner_entry,winner_name,winner_hand,winner_ht,"
    "winner_ioc,winner_age,winner_rank,winner_rank_points,loser_id,loser_seed,"
    "loser_entry,loser_name,loser_hand,loser_ht,loser_ioc,loser_age,loser_rank,"
    "loser_rank_points,score,best_of,round,minutes,w_ace,w_df,w_svpt,w_1stIn,"
    "w_1stWon,w_2ndWon,w_SvGms,w_bpSaved,w_bpFaced,l_ace,l_df,l_svpt,l_1stIn,"
    "l_1stWon,l_2ndWon,l_SvGms,l_bpSaved,l_bpFaced"
)


def _row(
    winner="Jiri Lehecka",
    loser="Novak Djokovic",
    score="6-4 6-4",
    tourney_id="2026-580",
    match_num="1",
    surface="Hard",
    tourney_date="20260904",
    tourney_name="US Open",
    tourney_level="G",
) -> str:
    return (
        f"{tourney_id},{tourney_name},{surface},128,{tourney_level},,{tourney_date},"
        f"{match_num},100,1,,{winner},R,188,CZE,24.0,10,3000,200,2,,{loser},R,188,SRB,"
        f"38.0,5,2000,{score},3,R32,105,7,3,80,50,35,15,10,3,4,5,6,70,40,25,12,9,2,5"
    )


def _csv(*rows: str) -> str:
    return "\n".join([_HEADER, *rows])


def _mock_get(monkeypatch, url_to_body: dict[str, tuple[int, str]]):
    """Route requests.get by URL to a (status_code, body) pair. Unlisted URLs 404."""
    import requests

    class _Resp:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text

    def fake_get(url, headers=None, timeout=None):
        status, body = url_to_body.get(url, (404, ""))
        return _Resp(status, body)

    monkeypatch.setattr(requests, "get", fake_get)


def test_finds_a_player_and_reads_aces_and_double_faults(client, monkeypatch):
    from bet.scrapers.constants import SACKMANN_ATP_ONGOING_URL, SACKMANN_ATP_URL

    _mock_get(monkeypatch, {
        SACKMANN_ATP_ONGOING_URL: (200, _csv()),
        SACKMANN_ATP_URL.format(year="2026"): (200, _csv(_row())),
    })

    fixtures = client.get_team_last_fixtures("Jiri Lehecka", last_n=5)
    assert len(fixtures) == 1
    assert fixtures[0].away_team == "Novak Djokovic"

    stats = client.get_fixture_stats(fixtures[0].fixture_id)
    assert stats is not None
    assert stats.stats["aces"] == 7
    assert stats.stats["double_faults"] == 3
    # Winner's own games from "6-4 6-4": 6+6 = 12; total_games = 12+8 = 20; 2 sets.
    assert stats.stats["games_won"] == 12.0
    assert stats.stats["total_games"] == 20.0
    assert stats.stats["total_sets"] == 2.0
    assert stats.stats["surface"] == "Hard"


def test_loser_side_reads_the_loser_prefix_and_games(client, monkeypatch):
    from bet.scrapers.constants import SACKMANN_ATP_ONGOING_URL, SACKMANN_ATP_URL

    _mock_get(monkeypatch, {
        SACKMANN_ATP_ONGOING_URL: (200, _csv()),
        SACKMANN_ATP_URL.format(year="2026"): (200, _csv(_row())),
    })

    fixtures = client.get_team_last_fixtures("Novak Djokovic", last_n=5)
    assert len(fixtures) == 1
    stats = client.get_fixture_stats(fixtures[0].fixture_id)
    assert stats.stats["aces"] == 5  # l_ace
    assert stats.stats["double_faults"] == 6  # l_df
    assert stats.stats["games_won"] == 8.0  # loser's games from "6-4 6-4"
    assert stats.stats["result"] == "L"


def test_accent_folded_name_matches_the_ascii_spelling(client, monkeypatch):
    """The whole reason this reuses tennis_abstract's identity_matches: 'Jiří
    Lehečka' (as our own dossiers spell him) must match 'Jiri Lehecka' (as
    tennismylife's CSV states him)."""
    from bet.scrapers.constants import SACKMANN_ATP_ONGOING_URL, SACKMANN_ATP_URL

    _mock_get(monkeypatch, {
        SACKMANN_ATP_ONGOING_URL: (200, _csv()),
        SACKMANN_ATP_URL.format(year="2026"): (200, _csv(_row(winner="Jiri Lehecka"))),
    })

    fixtures = client.get_team_last_fixtures("Jiří Lehečka", last_n=5)
    assert len(fixtures) == 1


def test_a_player_absent_from_every_file_returns_empty_not_an_error(client, monkeypatch):
    """ITF / WTA Challenger names: this provider does not cover that level.
    Absent, not fabricated -- a zero-match result, never an exception."""
    from bet.scrapers.constants import (
        SACKMANN_ATP_CHALLENGER_ONGOING_URL,
        SACKMANN_ATP_CHALLENGER_URL,
        SACKMANN_ATP_ONGOING_URL,
        SACKMANN_ATP_URL,
        SACKMANN_WTA_ONGOING_URL,
        SACKMANN_WTA_URL,
    )

    _mock_get(monkeypatch, {
        SACKMANN_ATP_ONGOING_URL: (200, _csv()),
        SACKMANN_ATP_URL.format(year="2026"): (200, _csv(_row())),
        SACKMANN_ATP_CHALLENGER_ONGOING_URL: (200, _csv()),
        SACKMANN_ATP_CHALLENGER_URL.format(year="2026"): (200, _csv()),
        SACKMANN_WTA_ONGOING_URL: (200, _csv()),
        SACKMANN_WTA_URL.format(year="2026"): (200, _csv()),
    })

    fixtures = client.get_team_last_fixtures("Some ITF Qualifier Nobody", last_n=5)
    assert fixtures == []


def test_a_404_on_one_file_does_not_break_the_others(client, monkeypatch):
    """The ongoing file 404ing (e.g. between tournaments) must not take the
    season file down with it -- each URL is fetched and cached independently."""
    from bet.scrapers.constants import SACKMANN_ATP_ONGOING_URL, SACKMANN_ATP_URL

    _mock_get(monkeypatch, {
        SACKMANN_ATP_ONGOING_URL: (404, ""),
        SACKMANN_ATP_URL.format(year="2026"): (200, _csv(_row())),
    })

    fixtures = client.get_team_last_fixtures("Jiri Lehecka", last_n=5)
    assert len(fixtures) == 1


def test_the_same_match_in_two_files_is_not_double_counted(client, monkeypatch):
    """A tournament in progress can appear in both the ongoing file and (once
    it wraps) the season file. One match, one (tourney_id, match_num) pair,
    one entry -- not two copies inflating a 10-match sample to effectively 9
    distinct matches."""
    from bet.scrapers.constants import SACKMANN_ATP_ONGOING_URL, SACKMANN_ATP_URL

    row = _row()
    _mock_get(monkeypatch, {
        SACKMANN_ATP_ONGOING_URL: (200, _csv(row)),
        SACKMANN_ATP_URL.format(year="2026"): (200, _csv(row)),
    })

    fixtures = client.get_team_last_fixtures("Jiri Lehecka", last_n=10)
    assert len(fixtures) == 1


def test_get_h2h_finds_either_order_and_sorts_newest_first(client, monkeypatch):
    from bet.scrapers.constants import SACKMANN_ATP_ONGOING_URL, SACKMANN_ATP_URL

    older = _row(
        winner="Novak Djokovic", loser="Jiri Lehecka",
        tourney_date="20260115", tourney_id="2026-580", match_num="1",
        tourney_name="Australian Open",
    )
    newer = _row(
        winner="Jiri Lehecka", loser="Novak Djokovic",
        tourney_date="20260904", tourney_id="2026-560", match_num="2",
        tourney_name="US Open",
    )
    _mock_get(monkeypatch, {
        SACKMANN_ATP_ONGOING_URL: (200, _csv()),
        SACKMANN_ATP_URL.format(year="2026"): (200, _csv(older, newer)),
    })

    h2h = client.get_h2h("Jiri Lehecka", "Novak Djokovic", last_n=5)
    assert len(h2h) == 2
    assert h2h[0]["tournament"] == "US Open"  # newest first
    assert h2h[1]["tournament"] == "Australian Open"


def test_get_fixture_stats_returns_none_for_an_unseen_fixture_id(client):
    assert client.get_fixture_stats("sack_never_fetched_1") is None


def test_no_serve_line_is_dropped_not_reported_as_zero(client, monkeypatch):
    """A walkover-shaped row (no svpt) must produce no stats object, the same
    'absent, not fabricated' rule every provider in this pipeline follows --
    not a row claiming zero aces on a match that was never really served."""
    from bet.scrapers.constants import SACKMANN_ATP_ONGOING_URL, SACKMANN_ATP_URL

    header_row = (
        "2026-580,US Open,Hard,128,G,,20260904,1,100,1,,Jiri Lehecka,R,188,CZE,24.0,"
        "10,3000,200,2,,Novak Djokovic,R,188,SRB,38.0,5,2000,W/O,3,R32,,,,,,,,,,,,,,,,,,"
    )
    _mock_get(monkeypatch, {
        SACKMANN_ATP_ONGOING_URL: (200, _csv()),
        SACKMANN_ATP_URL.format(year="2026"): (200, _csv(header_row)),
    })

    fixtures = client.get_team_last_fixtures("Jiri Lehecka", last_n=5)
    assert len(fixtures) == 1
    assert client.get_fixture_stats(fixtures[0].fixture_id) is None
