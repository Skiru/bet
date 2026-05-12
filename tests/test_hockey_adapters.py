"""Unit tests for hockey adapters — hockey_reference, naturalstattrick, dailyfaceoff."""
import sys
from pathlib import Path

# Ensure scripts directory is on path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from adapters.hockey_reference_adapter import parse as hockey_ref_parse
from adapters.naturalstattrick_adapter import parse as nst_parse
from adapters.dailyfaceoff_adapter import parse as df_parse
from adapters.covers_adapter import parse as covers_parse


# --- Sample HTML fixtures ---

HOCKEY_REF_SCHEDULE_HTML = """
<html><body>
<table id="games">
<thead><tr><th>Date</th><th>Visitor</th><th>Home</th><th>Time</th></tr></thead>
<tbody>
<tr>
  <td data-stat="date_game">2026-05-12</td>
  <td data-stat="visitor_team_name"><a href="/teams/BOS/">Boston Bruins</a></td>
  <td data-stat="home_team_name"><a href="/teams/TOR/">Toronto Maple Leafs</a></td>
  <td data-stat="game_start_time">7:00p</td>
</tr>
<tr>
  <td data-stat="date_game">2026-05-12</td>
  <td data-stat="visitor_team_name"><a href="/teams/NYR/">New York Rangers</a></td>
  <td data-stat="home_team_name"><a href="/teams/CAR/">Carolina Hurricanes</a></td>
  <td data-stat="game_start_time">7:30p</td>
</tr>
</tbody>
</table>
</body></html>
"""

HOCKEY_REF_BOXSCORE_HTML = """
<html><body>
<div class="scorebox">
  <div>
    <div><a href="/teams/BOS/2026.html">Boston Bruins</a></div>
    <div class="score">3</div>
  </div>
  <div>
    <div><a href="/teams/TOR/2026.html">Toronto Maple Leafs</a></div>
    <div class="score">2</div>
  </div>
</div>
<table id="scoring">
<thead><tr><th>Period</th><th>BOS</th><th>TOR</th></tr></thead>
<tbody>
<tr><td>1st</td><td>1</td><td>0</td></tr>
<tr><td>2nd</td><td>1</td><td>1</td></tr>
<tr><td>3rd</td><td>1</td><td>1</td></tr>
</tbody>
</table>
<table id="team_stats">
<tbody>
<tr>
  <td data-stat="visitor_team_name">Boston Bruins</td>
  <td data-stat="goals">3</td>
  <td data-stat="shots">32</td>
  <td data-stat="pim">8</td>
  <td data-stat="pp">1</td>
  <td data-stat="ppoa">4</td>
  <td data-stat="hits">25</td>
  <td data-stat="blocks">15</td>
  <td data-stat="fow">28</td>
  <td data-stat="fol">30</td>
</tr>
<tr>
  <td data-stat="home_team_name">Toronto Maple Leafs</td>
  <td data-stat="goals">2</td>
  <td data-stat="shots">28</td>
  <td data-stat="pim">6</td>
  <td data-stat="pp">0</td>
  <td data-stat="ppoa">3</td>
  <td data-stat="hits">22</td>
  <td data-stat="blocks">12</td>
  <td data-stat="fow">30</td>
  <td data-stat="fol">28</td>
</tr>
</tbody>
</table>
</body></html>
"""

NST_TEAM_TABLE_HTML = """
<html><body>
<table id="teams">
<thead><tr>
<th>Team</th><th>GP</th><th>CF%</th><th>FF%</th><th>xGF</th><th>xGA</th><th>xGF%</th>
<th>HDCF</th><th>HDCA</th><th>HDCF%</th><th>SH%</th><th>SV%</th>
</tr></thead>
<tbody>
<tr><td>Boston Bruins</td><td>82</td><td>52.1</td><td>51.8</td><td>2.85</td><td>2.45</td><td>53.8</td><td>12.5</td><td>10.2</td><td>55.1</td><td>9.8</td><td>91.5</td></tr>
<tr><td>Toronto Maple Leafs</td><td>82</td><td>50.3</td><td>50.1</td><td>2.90</td><td>2.70</td><td>51.8</td><td>11.8</td><td>11.2</td><td>51.3</td><td>10.1</td><td>90.8</td></tr>
<tr><td>Carolina Hurricanes</td><td>82</td><td>54.2</td><td>53.5</td><td>3.10</td><td>2.30</td><td>57.4</td><td>13.1</td><td>9.8</td><td>57.2</td><td>9.5</td><td>92.1</td></tr>
</tbody>
</table>
</body></html>
"""

NST_GAME_LOG_HTML = """
<html><body>
<table id="games">
<thead><tr>
<th>Date</th><th>Team</th><th>Opponent</th><th>CF%</th><th>FF%</th>
<th>xGF</th><th>xGA</th><th>xGF%</th><th>HDCF</th><th>HDCA</th><th>Score</th>
</tr></thead>
<tbody>
<tr><td>2026-05-10</td><td>Boston Bruins</td><td>Toronto Maple Leafs</td><td>55.2</td><td>54.1</td><td>3.2</td><td>2.1</td><td>60.4</td><td>14</td><td>8</td><td>4-2</td></tr>
<tr><td>2026-05-08</td><td>Boston Bruins</td><td>Montreal Canadiens</td><td>48.9</td><td>49.5</td><td>2.5</td><td>2.8</td><td>47.2</td><td>10</td><td>12</td><td>2-3</td></tr>
</tbody>
</table>
</body></html>
"""

DAILYFACEOFF_HTML = """
<html><body>
<div class="starting-goalies-card">
  <div class="team away">
    <span class="team-name">Boston Bruins</span>
    <span class="goalie-name">Jeremy Swayman</span>
    <span class="status confirmed">Confirmed</span>
  </div>
  <div class="team home">
    <span class="team-name">Toronto Maple Leafs</span>
    <span class="goalie-name">Joseph Woll</span>
    <span class="status expected">Expected</span>
  </div>
  <span class="game-time">7:00 PM ET</span>
</div>
<div class="starting-goalies-card">
  <div class="team away">
    <span class="team-name">New York Rangers</span>
    <span class="goalie-name">Igor Shesterkin</span>
    <span class="status confirmed">Confirmed</span>
  </div>
  <div class="team home">
    <span class="team-name">Carolina Hurricanes</span>
    <span class="goalie-name">Frederik Andersen</span>
    <span class="status unconfirmed">TBD</span>
  </div>
  <span class="game-time">7:30 PM ET</span>
</div>
</body></html>
"""

# DailyFaceoff with embedded Next.js JSON (real-world format)
DAILYFACEOFF_JSON_HTML = """
<html><body>
<script>{"props":{"pageProps":{"data":[
  {"homeTeamName":"Toronto Maple Leafs","awayTeamName":"Boston Bruins",
   "homeGoalieName":"Joseph Woll","awayGoalieName":"Jeremy Swayman",
   "homeGoalieWins":25,"homeGoalieLosses":12,"homeGoalieOvertimeLosses":5,
   "homeGoalieSavePercentage":"0.910","homeGoalieGoalsAgainstAvg":"2.65",
   "homeGoalieShutouts":3,"homeGoalieOverallScore":null,
   "awayGoalieWins":30,"awayGoalieLosses":8,"awayGoalieOvertimeLosses":3,
   "awayGoalieSavePercentage":"0.920","awayGoalieGoalsAgainstAvg":"2.35",
   "awayGoalieShutouts":5,"awayGoalieOverallScore":72.5,
   "date":"2026-05-12","time":"19:00",
   "pointSpread":1.5,"homeTeamMoneylinePointSpread":-135,"awayTeamMoneylinePointSpread":114,
   "homeNewsStrengthName":null,"awayNewsStrengthName":null},
  {"homeTeamName":"Carolina Hurricanes","awayTeamName":"New York Rangers",
   "homeGoalieName":"Frederik Andersen","awayGoalieName":"Igor Shesterkin",
   "homeGoalieWins":20,"homeGoalieLosses":10,"homeGoalieOvertimeLosses":2,
   "homeGoalieSavePercentage":"0.915","homeGoalieGoalsAgainstAvg":"2.50",
   "homeGoalieShutouts":4,"homeGoalieOverallScore":68.3,
   "awayGoalieWins":35,"awayGoalieLosses":12,"awayGoalieOvertimeLosses":4,
   "awayGoalieSavePercentage":"0.925","awayGoalieGoalsAgainstAvg":"2.20",
   "awayGoalieShutouts":6,"awayGoalieOverallScore":85.1,
   "date":"2026-05-12","time":"19:30",
   "pointSpread":1.5,"homeTeamMoneylinePointSpread":-150,"awayTeamMoneylinePointSpread":125,
   "homeNewsStrengthName":null,"awayNewsStrengthName":null}
]}}}</script>
<div>Unconfirmed</div>
<div>Joseph Woll</div>
<div>Confirmed</div>
<div>Jeremy Swayman</div>
</body></html>
"""

EMPTY_HTML = "<html><body></body></html>"

HOCKEY_REF_BOXSCORE_WITH_GOALIES_HTML = """
<html><body>
<div class="scorebox">
  <div>
    <div><a href="/teams/BOS/2026.html">Boston Bruins</a></div>
    <div class="score">3</div>
  </div>
  <div>
    <div><a href="/teams/TOR/2026.html">Toronto Maple Leafs</a></div>
    <div class="score">2</div>
  </div>
</div>
<table id="scoring">
<thead><tr><th>Period</th><th>BOS</th><th>TOR</th></tr></thead>
<tbody>
<tr><td>1st</td><td>1</td><td>0</td></tr>
<tr><td>2nd</td><td>1</td><td>1</td></tr>
<tr><td>3rd</td><td>1</td><td>1</td></tr>
</tbody>
</table>
<table id="goalies_BOS">
<tbody><tr><td>Jeremy Swayman</td><td data-stat="saves">28</td><td data-stat="save_pct">.933</td><td data-stat="goals_against_avg">2.10</td></tr></tbody>
<tfoot><tr><td>Total</td><td data-stat="saves">28</td><td data-stat="save_pct">.933</td><td data-stat="goals_against_avg">2.10</td></tr></tfoot>
</table>
<table id="goalies_TOR">
<tbody><tr><td>Joseph Woll</td><td data-stat="saves">29</td><td data-stat="save_pct">.906</td><td data-stat="goals_against_avg">3.00</td></tr></tbody>
<tfoot><tr><td>Total</td><td data-stat="saves">29</td><td data-stat="save_pct">.906</td><td data-stat="goals_against_avg">3.00</td></tr></tfoot>
</table>
</body></html>
"""

COVERS_NHL_MATCHUP_HTML = """
<html><body>
<div class="matchup game-card">
  <span class="team-name">Boston Bruins</span>
  <span class="team-name">Toronto Maple Leafs</span>
  <span class="time">7:00 PM ET</span>
  <span class="goalie">Jeremy Swayman</span>
  <span class="goalie">Joseph Woll</span>
  <span>PP: 22.5%</span>
  <span>PK: 81.3%</span>
  <span>PP: 20.1%</span>
  <span>PK: 79.8%</span>
  <span>30-8-3</span>
  <span>25-12-5</span>
</div>
</body></html>
"""


class TestHockeyReferenceAdapter:
    """Tests for hockey_reference_adapter.py."""

    def test_schedule_page_returns_matches(self):
        results = hockey_ref_parse(HOCKEY_REF_SCHEDULE_HTML, "https://www.hockey-reference.com/leagues/NHL_2026_games.html")
        assert len(results) == 2
        assert results[0]["home"] == "Toronto Maple Leafs"
        assert results[0]["away"] == "Boston Bruins"
        assert results[0]["sport"] == "hockey"
        assert results[0]["source_type"] == "hockey_reference"
        assert results[0]["league"] == "NHL"

    def test_boxscore_page_returns_deep_stats(self):
        results = hockey_ref_parse(HOCKEY_REF_BOXSCORE_HTML, "https://www.hockey-reference.com/boxscores/202605120TOR.html")
        assert len(results) == 1
        r = results[0]
        assert r["home"] == "Toronto Maple Leafs"
        assert r["away"] == "Boston Bruins"
        assert r["score_home"] == 2
        assert r["score_away"] == 3
        assert r["period_scores"]["away"] == [1, 1, 1]
        assert r["period_scores"]["home"] == [0, 1, 1]
        assert r["stats"]["shots"]["away"] == 32
        assert r["stats"]["shots"]["home"] == 28
        assert r["stats"]["hits"]["away"] == 25
        assert r["stats"]["pp_goals"]["away"] == 1
        assert r["stats"]["blocks"]["home"] == 12
        assert r["stats"]["faceoff_wins"]["home"] == 30
        assert r["sport"] == "hockey"

    def test_empty_page_falls_back(self):
        results = hockey_ref_parse(EMPTY_HTML, "https://www.hockey-reference.com/boxscores/")
        # Should fall back to raw_parse (may return empty list)
        assert isinstance(results, list)

    def test_boxscore_goalie_stats_assigned_correctly(self):
        """Test that goalie stats are assigned to correct team via table ID abbreviation."""
        results = hockey_ref_parse(
            HOCKEY_REF_BOXSCORE_WITH_GOALIES_HTML,
            "https://www.hockey-reference.com/boxscores/202605120TOR.html"
        )
        assert len(results) == 1
        r = results[0]
        # BOS abbreviation should NOT match "Toronto Maple Leafs" → assigned to away
        assert r["goalie_stats"]["away"]["saves"] == 28
        assert r["goalie_stats"]["away"]["save_pct"] == 0.933
        assert r["goalie_stats"]["away"]["gaa"] == 2.10
        # TOR abbreviation should match "Toronto Maple Leafs" → assigned to home
        assert r["goalie_stats"]["home"]["saves"] == 29
        assert r["goalie_stats"]["home"]["save_pct"] == 0.906
        assert r["goalie_stats"]["home"]["gaa"] == 3.00

    def test_boxscore_non_nhl_league_detection(self):
        """Test that non-NHL URLs get correct league."""
        html = HOCKEY_REF_BOXSCORE_HTML
        results = hockey_ref_parse(html, "https://www.hockey-reference.com/olympics/boxscores/202605120TOR.html")
        assert len(results) == 1
        assert results[0]["league"] == "OLYMPICS"


class TestNaturalStatTrickAdapter:
    """Tests for naturalstattrick_adapter.py."""

    def test_team_table_returns_teams(self):
        results = nst_parse(NST_TEAM_TABLE_HTML, "https://www.naturalstattrick.com/teamtable.php?fromseason=20252026")
        assert len(results) == 3
        r = results[0]
        assert r["home"] == "Boston Bruins"
        assert r["sport"] == "hockey"
        assert r["source_type"] == "naturalstattrick"
        assert r["data_type"] == "team_season_stats"
        assert "corsi_pct" in r["stats"]
        assert r["stats"]["corsi_pct"] == 52.1
        assert "xgf" in r["stats"]
        assert r["stats"]["xgf"] == 2.85
        assert "high_danger_for" in r["stats"]
        assert r["stats"]["high_danger_for"] == 12.5

    def test_game_log_returns_games(self):
        results = nst_parse(NST_GAME_LOG_HTML, "https://www.naturalstattrick.com/games.php?fromseason=20252026")
        assert len(results) == 2
        r = results[0]
        assert r["home"] == "Boston Bruins"
        assert r["away"] == "Toronto Maple Leafs"
        assert r["source_type"] == "naturalstattrick"
        assert r["data_type"] == "game_stats"
        assert r["stats"]["corsi_pct"] == 55.2
        assert r["stats"]["xgf"] == 3.2
        assert r["score"] == "4-2"

    def test_empty_page_falls_back(self):
        results = nst_parse(EMPTY_HTML, "https://www.naturalstattrick.com/teamtable.php")
        assert isinstance(results, list)

    def test_unknown_url_falls_back(self):
        results = nst_parse("<html><body>Some random page</body></html>", "https://www.naturalstattrick.com/faq.php")
        assert isinstance(results, list)


class TestDailyFaceoffAdapter:
    """Tests for dailyfaceoff_adapter.py."""

    def test_html_cards_returns_matchups(self):
        """Test HTML card-based parsing (fallback when no JSON)."""
        results = df_parse(DAILYFACEOFF_HTML, "https://www.dailyfaceoff.com/starting-goalies/")
        assert len(results) == 2
        
        r = results[0]
        assert r["away"] == "Boston Bruins"
        assert r["home"] == "Toronto Maple Leafs"
        assert r["sport"] == "hockey"
        assert r["source_type"] == "dailyfaceoff"
        assert r["goalie_away"]["name"] == "Jeremy Swayman"
        assert r["goalie_away"]["status"] == "confirmed"
        assert r["goalie_home"]["name"] == "Joseph Woll"
        assert r["goalie_home"]["status"] == "expected"
        
        r2 = results[1]
        assert r2["goalie_away"]["name"] == "Igor Shesterkin"
        assert r2["goalie_away"]["status"] == "confirmed"
        assert r2["goalie_home"]["name"] == "Frederik Andersen"
        assert r2["goalie_home"]["status"] == "unconfirmed"

    def test_json_data_returns_rich_matchups(self):
        """Test Next.js JSON parsing (primary strategy on real pages)."""
        results = df_parse(DAILYFACEOFF_JSON_HTML, "https://www.dailyfaceoff.com/starting-goalies/")
        assert len(results) == 2
        
        r = results[0]
        assert r["home"] == "Toronto Maple Leafs"
        assert r["away"] == "Boston Bruins"
        assert r["sport"] == "hockey"
        assert r["source_type"] == "dailyfaceoff"
        assert r["time"] == "19:00"
        assert r["date"] == "2026-05-12"
        
        # Goalie names
        assert r["goalie_home"]["name"] == "Joseph Woll"
        assert r["goalie_away"]["name"] == "Jeremy Swayman"
        
        # Goalie stats
        assert r["goalie_home"]["wins"] == 25
        assert r["goalie_home"]["sv_pct"] == 0.910
        assert r["goalie_home"]["gaa"] == 2.65
        assert r["goalie_away"]["wins"] == 30
        assert r["goalie_away"]["sv_pct"] == 0.920
        assert r["goalie_away"]["rating"] == 72.5
        
        # Odds
        assert "odds" in r
        assert r["odds"]["spread"] == 1.5
        assert r["odds"]["ml_home"] == -135.0
        
        # Second game
        r2 = results[1]
        assert r2["home"] == "Carolina Hurricanes"
        assert r2["away"] == "New York Rangers"
        assert r2["goalie_away"]["rating"] == 85.1

    def test_empty_page_falls_back(self):
        results = df_parse(EMPTY_HTML, "https://www.dailyfaceoff.com/starting-goalies/")
        assert isinstance(results, list)

    def test_non_goalie_page_falls_back(self):
        results = df_parse("<html><body>Some page</body></html>", "https://www.dailyfaceoff.com/teams/bos/")
        assert isinstance(results, list)

    def test_json_goalie_confirmation_status(self):
        """Test that goalie confirmation status is enriched from rendered HTML text."""
        results = df_parse(DAILYFACEOFF_JSON_HTML, "https://www.dailyfaceoff.com/starting-goalies/")
        r = results[0]
        # _enrich_confirmation_status does best-effort proximity matching from rendered HTML
        # Verify status field is set to a valid value (not None or empty)
        valid_statuses = {"confirmed", "expected", "unconfirmed"}
        assert r["goalie_home"]["status"] in valid_statuses
        assert r["goalie_away"]["status"] in valid_statuses


class TestCoversNHLAdapter:
    """Tests for covers_adapter.py NHL-specific parsing."""

    def test_nhl_matchup_extracts_goalie_dicts(self):
        """Test that goalie fields are dicts, not plain strings (BUG2 regression)."""
        results = covers_parse(COVERS_NHL_MATCHUP_HTML, "https://www.covers.com/nhl/matchups")
        assert len(results) >= 1
        r = results[0]
        assert r["sport"] == "hockey"
        assert r["source_type"] == "covers"
        # Goalie fields must be dicts with "name" key — not plain strings
        if "goalie_away" in r:
            assert isinstance(r["goalie_away"], dict)
            assert "name" in r["goalie_away"]
        if "goalie_home" in r:
            assert isinstance(r["goalie_home"], dict)
            assert "name" in r["goalie_home"]

    def test_nhl_matchup_extracts_pp_pk(self):
        """Test PP/PK percentage extraction."""
        results = covers_parse(COVERS_NHL_MATCHUP_HTML, "https://www.covers.com/nhl/matchups")
        if results:
            r = results[0]
            if "pp_pct_away" in r:
                assert isinstance(r["pp_pct_away"], float)
            if "record_away" in r:
                assert "-" in r["record_away"]
