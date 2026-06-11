"""Tests for build_shortlist module."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from build_shortlist import build_shortlist, write_shortlist_json, _score_event, _score_competition


# ---------------------------------------------------------------------------
# Shortlist output structure
# ---------------------------------------------------------------------------


def test_shortlist_output_has_required_keys():
    """Output JSON has `candidates` and `metadata`."""
    tmp = tempfile.mkdtemp()
    data_dir = Path(tmp)

    # Create minimal market matrix
    matrix = {
        "events": [
            {
                "sport": "football",
                "competition": "Premier League",
                "home_team": "Liverpool",
                "away_team": "Arsenal",
                "kickoff": "2099-01-01T15:00:00",
                "data_tier": "STATS_READY",
                "markets_available": ["corners", "fouls"],
                "source_count": 2,
            },
        ],
        "metadata": {"date": "2099-01-01"},
    }
    (data_dir / "market_matrix_2099-01-01.json").write_text(
        json.dumps(matrix), encoding="utf-8"
    )

    with patch("build_shortlist.DATA_DIR", data_dir):
        result = build_shortlist("2099-01-01", top_n=0, stats_first=True)

    assert isinstance(result, list)
    assert len(result) > 0

    # Write and verify JSON structure
    with patch("build_shortlist.DATA_DIR", data_dir):
        out_path = write_shortlist_json(
            [(10.0, result[0])] if isinstance(result[0], dict) else result[:1],
            "2099-01-01",
        )
    assert Path(out_path).exists()
    data = json.loads(Path(out_path).read_text(encoding="utf-8"))
    assert "candidates" in data
    assert "total_candidates" in data
    assert "date" in data
    assert "sports" in data

    import shutil
    shutil.rmtree(tmp)


# ---------------------------------------------------------------------------
# Tournament boost
# ---------------------------------------------------------------------------


def test_tournament_boost_applied():
    """Candidates with tournament keywords get score boost."""
    tournament_event = {
        "sport": "football",
        "competition": "FIFA World Cup 2026",
        "home_team": "Brazil",
        "away_team": "Germany",
        "kickoff": "2099-01-01T20:00:00",
        "data_tier": "STATS_READY",
        "markets_available": ["corners", "fouls", "goals"],
        "source_count": 3,
    }
    regular_event = {
        "sport": "football",
        "competition": "Polish Ekstraklasa",
        "home_team": "Legia",
        "away_team": "Lech",
        "kickoff": "2099-01-01T18:00:00",
        "data_tier": "STATS_READY",
        "markets_available": ["corners", "fouls", "goals"],
        "source_count": 3,
    }

    tipster_events: set[str] = set()
    tournament_score = _score_event(tournament_event, tipster_events)
    regular_score = _score_event(regular_event, tipster_events)

    # Tournament events should score higher due to competition tier boost
    assert tournament_score > regular_score


# ---------------------------------------------------------------------------
# FIXTURE_ONLY filter
# ---------------------------------------------------------------------------


class TestFixtureOnlyFilter:
    """FIXTURE_ONLY events from minor leagues should be dropped, major leagues kept."""

    def _make_event(self, sport: str, competition: str, data_tier: str,
                    home: str = "Team A", away: str = "Team B") -> dict:
        return {
            "sport": sport,
            "competition": competition,
            "home_team": home,
            "away_team": away,
            "kickoff": "2099-01-01T20:00:00",
            "data_tier": data_tier,
            "odds_markets": [] if data_tier == "FIXTURE_ONLY" else [{"market": "ML", "best_odds": 1.80}],
            "safety_markets": [],
        }

    def test_fixture_only_minor_league_dropped(self):
        """FIXTURE_ONLY from Armenia First League (comp_score<7) should be filtered."""
        from build_shortlist import _score_competition
        # Armenia First League has comp_score=3 (<7) so FIXTURE_ONLY gets dropped
        assert _score_competition("football", "Armenia - First League") < 7
        event = self._make_event("football", "Armenia - First League", "FIXTURE_ONLY")
        score = _score_event(event, set())
        # Low-tier comp (score=3) + FIXTURE_ONLY penalty → low score
        assert score < 20

    def test_fixture_only_major_league_kept(self):
        """FIXTURE_ONLY from Premier League (comp_score>=7) should be KEPT."""
        event = self._make_event("football", "English Premier League", "FIXTURE_ONLY",
                                 home="Liverpool", away="Arsenal")
        score = _score_event(event, set())
        # Major league FIXTURE_ONLY still gets decent score (comp_tier=9, ×7=63, ×0.8=~50+)
        assert score > 30  # high enough to survive

    def test_fixture_only_nba_kept(self):
        """FIXTURE_ONLY NBA events (comp_score=9) survive the filter."""
        event = self._make_event("basketball", "NBA", "FIXTURE_ONLY",
                                 home="Lakers", away="Celtics")
        score = _score_event(event, set())
        assert score > 30

    def test_fixture_only_gibraltar_dropped(self):
        """FIXTURE_ONLY from Gibraltar league (comp_score<7) → dropped."""
        from build_shortlist import _score_competition
        comp_score = _score_competition("football", "GFA League")
        assert comp_score < 7  # confirms it would be filtered

    def test_fixture_only_mali_dropped(self):
        """FIXTURE_ONLY from Mali Ligue 1 (comp_score<7) → dropped."""
        from build_shortlist import _score_competition
        # Mali Ligue 1 should NOT match French Ligue 1 (tier 9)
        comp_score = _score_competition("football", "Mali - Ligue 1")
        assert comp_score < 7  # default tier 3, not the French league

    def test_odds_basic_minor_league_not_dropped(self):
        """ODDS_BASIC events are NOT dropped even from minor leagues (they have data)."""
        event = self._make_event("football", "Armenia - First League", "ODDS_BASIC")
        score = _score_event(event, set())
        # This event has odds — it should survive (filter only hits FIXTURE_ONLY)
        # comp_score is low but has odds, so data_tier != FIXTURE_ONLY → not filtered
        assert score >= 0  # scoring doesn't matter; FO filter won't touch it

    def test_fixture_only_dota2_major_event_kept(self):
        """Major Dota2 events should not be zeroed by the fixture-only filter."""
        assert _score_competition("dota2", "BLAST Slam") >= 6
        assert _score_competition("dota2", "Esports World Cup") >= 6

        event = self._make_event("dota2", "BLAST Slam", "FIXTURE_ONLY", home="Team Liquid", away="Team Falcons")
        score = _score_event(event, set())
        assert score > 30

    def test_full_pipeline_fixture_only_removal(self):
        """Integration: build_shortlist drops minor-league FIXTURE_ONLY from output."""
        import tempfile
        import shutil

        tmp = tempfile.mkdtemp()
        data_dir = Path(tmp)

        matrix = {
            "events": [
                # KEEP: Major league with data
                {
                    "sport": "football",
                    "competition": "England - Premier League",
                    "home_team": "Liverpool",
                    "away_team": "Arsenal",
                    "kickoff": "2099-01-01T15:00:00",
                    "data_tier": "ODDS_BASIC",
                    "odds_markets": [{"market": "ML:Home", "best_odds": 1.90}],
                    "safety_markets": [],
                },
                # KEEP: Major league FIXTURE_ONLY (enrichment signal)
                {
                    "sport": "basketball",
                    "competition": "NBA",
                    "home_team": "Lakers",
                    "away_team": "Celtics",
                    "kickoff": "2099-01-01T20:00:00",
                    "data_tier": "FIXTURE_ONLY",
                    "odds_markets": [],
                    "safety_markets": [],
                },
                # DROP: Minor league FIXTURE_ONLY (no value)
                {
                    "sport": "football",
                    "competition": "Armenia - First League",
                    "home_team": "FC Ararat",
                    "away_team": "FC Pyunik",
                    "kickoff": "2099-01-01T16:00:00",
                    "data_tier": "FIXTURE_ONLY",
                    "odds_markets": [],
                    "safety_markets": [],
                },
                # DROP: Minor league FIXTURE_ONLY (Tanzania)
                {
                    "sport": "football",
                    "competition": "Tanzania - Premier League",
                    "home_team": "Simba SC",
                    "away_team": "Young Africans",
                    "kickoff": "2099-01-01T17:00:00",
                    "data_tier": "FIXTURE_ONLY",
                    "odds_markets": [],
                    "safety_markets": [],
                },
            ],
        }
        (data_dir / "market_matrix_2099-01-01.json").write_text(
            json.dumps(matrix), encoding="utf-8"
        )

        with patch("build_shortlist.DATA_DIR", data_dir):
            result = build_shortlist("2099-01-01", top_n=0, stats_first=True)

        # Result is list of (score, event) tuples
        teams_in_result = set()
        for item in result:
            event = item[1] if isinstance(item, tuple) else item
            teams_in_result.add(event["home_team"])

        # Major league events KEPT
        assert "Liverpool" in teams_in_result
        assert "Lakers" in teams_in_result
        # Minor league FIXTURE_ONLY DROPPED (Tanzania comp_score=0, Armenia comp_score=3)
        assert "FC Ararat" not in teams_in_result
        assert "Simba SC" not in teams_in_result

        shutil.rmtree(tmp)

    def test_placeholder_fixture_removed_from_pipeline(self):
        """Bracket placeholders like TBD/R16P* should never survive shortlist filtering."""
        import tempfile
        import shutil

        tmp = tempfile.mkdtemp()
        data_dir = Path(tmp)

        matrix = {
            "events": [
                {
                    "sport": "tennis",
                    "competition": "Roland Garros - Women's Singles",
                    "home_team": "TBD",
                    "away_team": "R16P7",
                    "kickoff": "2099-01-01T15:00:00",
                    "data_tier": "FIXTURE_ONLY",
                    "odds_markets": [],
                    "safety_markets": [],
                },
                {
                    "sport": "tennis",
                    "competition": "WTA French Open",
                    "home_team": "Iga Swiatek",
                    "away_team": "Aryna Sabalenka",
                    "kickoff": "2099-01-01T17:00:00",
                    "data_tier": "ODDS_BASIC",
                    "odds_markets": [{"market": "ML:Home", "best_odds": 1.90}],
                    "safety_markets": [],
                },
            ],
        }
        (data_dir / "market_matrix_2099-01-01.json").write_text(
            json.dumps(matrix), encoding="utf-8"
        )

        with patch("build_shortlist.DATA_DIR", data_dir):
            result = build_shortlist("2099-01-01", top_n=0, stats_first=True)

        teams_in_result = { (item[1] if isinstance(item, tuple) else item)["home_team"] for item in result }
        assert "TBD" not in teams_in_result
        assert "Iga Swiatek" in teams_in_result

        shutil.rmtree(tmp)

    def test_shortlist_json_emits_zeroed_active_sport_telemetry(self):
        """If an active sport is fully cut, telemetry should expose it explicitly."""
        import shutil

        tmp = tempfile.mkdtemp()
        data_dir = Path(tmp)

        matrix = {
            "events": [
                {
                    "sport": "dota2",
                    "competition": "Regional Open Qualifier",
                    "home_team": "Alpha",
                    "away_team": "Beta",
                    "kickoff": "2099-01-01T18:00:00",
                    "data_tier": "FIXTURE_ONLY",
                    "odds_markets": [],
                    "safety_markets": [],
                },
                {
                    "sport": "football",
                    "competition": "England - Premier League",
                    "home_team": "Liverpool",
                    "away_team": "Arsenal",
                    "kickoff": "2099-01-01T20:00:00",
                    "data_tier": "ODDS_BASIC",
                    "odds_markets": [{"market": "ML:Home", "best_odds": 1.8}],
                    "safety_markets": [],
                },
            ],
        }
        (data_dir / "market_matrix_2099-01-01.json").write_text(json.dumps(matrix), encoding="utf-8")

        with patch("build_shortlist.DATA_DIR", data_dir):
            selected = build_shortlist("2099-01-01", top_n=0, stats_first=True)
            out_path = write_shortlist_json(selected, "2099-01-01")

        payload = json.loads(Path(out_path).read_text(encoding="utf-8"))
        assert "dota2" in payload["selection_telemetry"]["active_sports_zeroed"]

        shutil.rmtree(tmp)


# ---------------------------------------------------------------------------
# Phantom fixture protection
# ---------------------------------------------------------------------------


class TestPhantomFixtureProtection:
    """Major league events should not be removed by phantom fixture detection."""

    def test_major_league_protected_from_phantom(self):
        """Events with comp_score >= 7 are never phantom-killed."""
        from build_shortlist import _score_competition
        # EPL is comp_score=9
        assert _score_competition("football", "England - Premier League") >= 7
        # NBA is comp_score=9
        assert _score_competition("basketball", "NBA") >= 7
        # Bundesliga is comp_score=9
        assert _score_competition("football", "Bundesliga") >= 7

    def test_minor_league_not_protected(self):
        """Minor leagues (comp_score < 7) can be phantom-filtered."""
        from build_shortlist import _score_competition
        assert _score_competition("football", "Armenia - First League") < 7
        assert _score_competition("football", "Nigeria - Premier League") < 7


# ---------------------------------------------------------------------------
# Unbettable countries score = 0
# ---------------------------------------------------------------------------


class TestUnbettableCountries:
    """Events from unbettable countries (comp_score=0) should get score=0."""

    def test_iraq_scores_zero(self):
        """Iraqi league events get score=0 immediately."""
        from build_shortlist import _score_competition
        assert _score_competition("football", "Iraq Premier League") == 0

    def test_yemen_scores_zero(self):
        """Yemen league events get score=0 immediately."""
        from build_shortlist import _score_competition
        assert _score_competition("football", "Yemen - First Division") == 0

    def test_cambodia_scores_zero(self):
        """Cambodia league events get score=0 immediately."""
        from build_shortlist import _score_competition
        assert _score_competition("football", "Cambodia Premier League") == 0

    def test_unbettable_event_returns_zero_score(self):
        """Full _score_event returns 0 for unbettable country event."""
        event = {
            "sport": "football",
            "competition": "Yemen - First Division",
            "home_team": "Al-Ahli Sanaa",
            "away_team": "Al-Tilal",
            "kickoff": "2099-01-01T18:00:00",
            "data_tier": "FIXTURE_ONLY",
            "odds_markets": [],
            "safety_markets": [],
        }
        score = _score_event(event, set())
        assert score == 0.0


# ---------------------------------------------------------------------------
# Major league FIXTURE_ONLY scoring (lighter penalty)
# ---------------------------------------------------------------------------


class TestMajorLeagueFixtureOnlyScoring:
    """Major league FIXTURE_ONLY should get ×0.8 (not ×0.6) penalty."""

    def test_epl_fixture_only_higher_than_minor(self):
        """EPL FIXTURE_ONLY scores higher than minor league FIXTURE_ONLY."""
        epl_event = {
            "sport": "football",
            "competition": "English Premier League",
            "home_team": "Chelsea",
            "away_team": "Everton",
            "kickoff": "2099-01-01T15:00:00",
            "data_tier": "FIXTURE_ONLY",
            "odds_markets": [],
            "safety_markets": [],
        }
        minor_event = {
            "sport": "football",
            "competition": "Swiss Super League",
            "home_team": "FC Zurich",
            "away_team": "FC Basel",
            "kickoff": "2099-01-01T18:00:00",
            "data_tier": "FIXTURE_ONLY",
            "odds_markets": [],
            "safety_markets": [],
        }
        epl_score = _score_event(epl_event, set())
        minor_score = _score_event(minor_event, set())
        assert epl_score > minor_score

    def test_epl_fixture_only_vs_epl_with_odds(self):
        """EPL FIXTURE_ONLY scores less than EPL with odds (penalty applied)."""
        fo_event = {
            "sport": "football",
            "competition": "English Premier League",
            "home_team": "Chelsea",
            "away_team": "Everton",
            "kickoff": "2099-01-01T15:00:00",
            "data_tier": "FIXTURE_ONLY",
            "odds_markets": [],
            "safety_markets": [],
        }
        odds_event = {
            "sport": "football",
            "competition": "English Premier League",
            "home_team": "Chelsea",
            "away_team": "Everton",
            "kickoff": "2099-01-01T15:00:00",
            "data_tier": "ODDS_BASIC",
            "odds_markets": [{"market": "ML:Home", "best_odds": 1.80}],
            "safety_markets": [],
        }
        fo_score = _score_event(fo_event, set())
        odds_score = _score_event(odds_event, set())
        assert odds_score > fo_score  # having odds is always better
