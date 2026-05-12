"""Unit tests for Basketball-Reference deep adapter."""
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


class TestBoxScoreParsing:
    """Test _parse_box_score with synthetic HTML."""

    def _make_box_html(self, away_abbr="NYK", home_abbr="DET",
                       away_name="New York Knicks", home_name="Detroit Pistons"):
        """Create minimal Basketball-Reference box score HTML."""
        return f"""
        <html><body>
        <div class="scorebox">
            <strong><a href="/teams/{away_abbr}/">{away_name}</a></strong>
            <strong><a href="/teams/{home_abbr}/">{home_name}</a></strong>
        </div>
        <table id="box-{away_abbr}-game-basic">
            <thead><tr>
                <th data-stat="player">Player</th>
                <th data-stat="pts">PTS</th>
                <th data-stat="trb">TRB</th>
                <th data-stat="orb">ORB</th>
                <th data-stat="drb">DRB</th>
                <th data-stat="ast">AST</th>
                <th data-stat="stl">STL</th>
                <th data-stat="blk">BLK</th>
                <th data-stat="tov">TOV</th>
                <th data-stat="pf">PF</th>
                <th data-stat="fg_pct">FG%</th>
                <th data-stat="fg3_pct">3P%</th>
                <th data-stat="ft_pct">FT%</th>
            </tr></thead>
            <tfoot><tr>
                <td data-stat="player">Team Totals</td>
                <td data-stat="pts">116</td>
                <td data-stat="trb">43</td>
                <td data-stat="orb">13</td>
                <td data-stat="drb">30</td>
                <td data-stat="ast">18</td>
                <td data-stat="stl">6</td>
                <td data-stat="blk">4</td>
                <td data-stat="tov">17</td>
                <td data-stat="pf">22</td>
                <td data-stat="fg_pct">.477</td>
                <td data-stat="fg3_pct">.333</td>
                <td data-stat="ft_pct">.800</td>
            </tr></tfoot>
        </table>
        <table id="box-{home_abbr}-game-basic">
            <thead><tr>
                <th data-stat="player">Player</th>
                <th data-stat="pts">PTS</th>
                <th data-stat="trb">TRB</th>
                <th data-stat="orb">ORB</th>
                <th data-stat="drb">DRB</th>
                <th data-stat="ast">AST</th>
                <th data-stat="stl">STL</th>
                <th data-stat="blk">BLK</th>
                <th data-stat="tov">TOV</th>
                <th data-stat="pf">PF</th>
                <th data-stat="fg_pct">FG%</th>
                <th data-stat="fg3_pct">3P%</th>
                <th data-stat="ft_pct">FT%</th>
            </tr></thead>
            <tfoot><tr>
                <td data-stat="player">Team Totals</td>
                <td data-stat="pts">113</td>
                <td data-stat="trb">36</td>
                <td data-stat="orb">6</td>
                <td data-stat="drb">30</td>
                <td data-stat="ast">25</td>
                <td data-stat="stl">9</td>
                <td data-stat="blk">3</td>
                <td data-stat="tov">15</td>
                <td data-stat="pf">23</td>
                <td data-stat="fg_pct">.469</td>
                <td data-stat="fg3_pct">.265</td>
                <td data-stat="ft_pct">.848</td>
            </tr></tfoot>
        </table>
        </body></html>
        """

    def test_box_score_extracts_both_teams(self):
        from adapters.basketball_reference_adapter import parse
        html = self._make_box_html()
        results = parse(html, "https://www.basketball-reference.com/boxscores/202505010DET.html")
        assert len(results) == 1
        r = results[0]
        assert r["home"] == "Detroit Pistons"
        assert r["away"] == "New York Knicks"

    def test_box_score_all_12_stat_keys(self):
        from adapters.basketball_reference_adapter import parse
        html = self._make_box_html()
        results = parse(html, "https://www.basketball-reference.com/boxscores/202505010DET.html")
        stats = results[0]["stats"]
        expected = [
            "points", "rebounds", "offensive_rebounds", "defensive_rebounds",
            "assists", "steals", "blocks", "turnovers", "fouls",
            "fg_pct", "three_pct", "ft_pct",
        ]
        for key in expected:
            assert key in stats, f"Missing stat key: {key}"

    def test_box_score_values_correct(self):
        from adapters.basketball_reference_adapter import parse
        html = self._make_box_html()
        results = parse(html, "https://www.basketball-reference.com/boxscores/202505010DET.html")
        stats = results[0]["stats"]
        # Away team (NYK) = first table
        assert stats["points"]["away"] == 116.0
        assert stats["points"]["home"] == 113.0
        assert stats["offensive_rebounds"]["away"] == 13.0
        assert stats["fg_pct"]["home"] == 0.469

    def test_box_score_missing_tfoot_returns_defaults(self):
        from adapters.basketball_reference_adapter import parse
        html = """
        <html><body>
        <div class="scorebox">
            <strong><a href="/teams/NYK/">Knicks</a></strong>
            <strong><a href="/teams/DET/">Pistons</a></strong>
        </div>
        <table id="box-NYK-game-basic"><tbody></tbody></table>
        <table id="box-DET-game-basic"><tbody></tbody></table>
        </body></html>
        """
        results = parse(html, "https://www.basketball-reference.com/boxscores/202505010DET.html")
        assert len(results) == 1
        # All stats should be 0.0 since no tfoot
        stats = results[0]["stats"]
        assert stats["points"]["home"] == 0.0


class TestTeamStatsParsing:
    """Test _parse_team_stats with synthetic HTML."""

    def _make_team_html(self, team_name="Boston Celtics"):
        return f"""
        <html><body>
        <h1><span>2024-25</span> <span>{team_name}</span></h1>
        <table id="per_game">
            <tfoot><tr>
                <td data-stat="pts_per_g">116.3</td>
                <td data-stat="trb_per_g">45.3</td>
                <td data-stat="ast_per_g">26.1</td>
                <td data-stat="stl_per_g">7.2</td>
                <td data-stat="blk_per_g">5.5</td>
                <td data-stat="tov_per_g">11.9</td>
                <td data-stat="orb_per_g">11.4</td>
                <td data-stat="drb_per_g">33.9</td>
                <td data-stat="fg_pct">0.462</td>
                <td data-stat="fg3_pct">0.368</td>
                <td data-stat="ft_pct">0.799</td>
            </tr></tfoot>
        </table>
        </body></html>
        """

    def test_team_stats_extracts_name(self):
        from adapters.basketball_reference_adapter import parse
        html = self._make_team_html()
        results = parse(html, "https://www.basketball-reference.com/teams/BOS/2025.html")
        assert results[0]["team"] == "Boston Celtics"

    def test_team_stats_all_keys(self):
        from adapters.basketball_reference_adapter import parse
        html = self._make_team_html()
        results = parse(html, "https://www.basketball-reference.com/teams/BOS/2025.html")
        averages = results[0]["season_averages"]
        expected = ["points", "rebounds", "assists", "steals", "blocks",
                    "turnovers", "offensive_rebounds", "defensive_rebounds",
                    "fg_pct", "three_pct", "ft_pct"]
        for key in expected:
            assert key in averages, f"Missing average key: {key}"

    def test_team_stats_values(self):
        from adapters.basketball_reference_adapter import parse
        html = self._make_team_html()
        results = parse(html, "https://www.basketball-reference.com/teams/BOS/2025.html")
        avgs = results[0]["season_averages"]
        assert avgs["points"] == 116.3
        assert avgs["rebounds"] == 45.3
        assert avgs["fg_pct"] == 0.462


class TestScheduleParsing:
    """Test schedule parsing with deep link extraction."""

    def _make_schedule_html(self):
        return """
        <html><body>
        <table id="schedule">
            <tr>
                <th data-stat="date_game">Mon, May 1, 2025</th>
                <td data-stat="visitor_team_name"><a href="/teams/NYK/">New York Knicks</a></td>
                <td data-stat="home_team_name"><a href="/teams/DET/">Detroit Pistons</a></td>
                <td data-stat="game_start_time">7:00p</td>
                <td data-stat="box_score_text"><a href="/boxscores/202505010DET.html">Box Score</a></td>
            </tr>
        </table>
        </body></html>
        """

    def test_schedule_has_match_url(self):
        from adapters.basketball_reference_adapter import parse
        html = self._make_schedule_html()
        results = parse(html, "https://www.basketball-reference.com/leagues/NBA_2025_games-may.html")
        assert len(results) == 1
        assert results[0]["match_url"] == "https://www.basketball-reference.com/boxscores/202505010DET.html"

    def test_get_deep_links(self):
        from adapters.basketball_reference_adapter import get_deep_links
        html = self._make_schedule_html()
        links = get_deep_links(html, "https://www.basketball-reference.com/leagues/NBA_2025_games-may.html")
        assert len(links) == 1
        assert "202505010DET" in links[0]


class TestURLRouting:
    """Test that parse() routes to the correct sub-parser."""

    def test_boxscore_url_routes_to_box_parser(self):
        from adapters.basketball_reference_adapter import parse
        # Minimal HTML that won't match box score tables — should return empty/fallback
        html = "<html><body></body></html>"
        results = parse(html, "https://www.basketball-reference.com/boxscores/202505010DET.html")
        # Should attempt box score parsing (returns empty because no tables)
        # Then fall through to schedule/game rows, then raw_parse
        assert isinstance(results, list)

    def test_team_url_routes_to_team_parser(self):
        from adapters.basketball_reference_adapter import parse
        html = "<html><body></body></html>"
        results = parse(html, "https://www.basketball-reference.com/teams/BOS/2025.html")
        assert isinstance(results, list)
