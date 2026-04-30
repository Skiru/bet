"""Unit tests for BetExplorer HTML adapter."""

import unittest
from scripts.adapters.betexplorer_adapter import parse


# Standard BetExplorer match listing page with odds columns
BETEXPLORER_HTML_STANDARD = """
<html><body>
<table class="table-main">
  <tr>
    <td><a href="/match/1">Real Madrid - Barcelona</a></td>
    <td>21:00</td>
    <td>1.85</td>
    <td>3.60</td>
    <td>4.20</td>
  </tr>
  <tr>
    <td><a href="/match/2">Bayern Munich - Borussia Dortmund</a></td>
    <td>18:30</td>
    <td>1.55</td>
    <td>4.10</td>
    <td>5.50</td>
  </tr>
  <tr>
    <td><a href="/match/3">PSG - Marseille</a></td>
    <td>20:00</td>
    <td>1.40</td>
    <td>4.75</td>
    <td>7.00</td>
  </tr>
</table>
</body></html>
"""

# Page with multiple sports/sections
BETEXPLORER_HTML_MULTI_SPORT = """
<html><body>
<h2>Football</h2>
<table>
  <tr>
    <td><a href="/f/1">Liverpool - Chelsea</a></td>
    <td>15:00</td>
    <td>2.10</td>
    <td>3.40</td>
    <td>3.50</td>
  </tr>
</table>
<h2>Tennis</h2>
<table>
  <tr>
    <td><a href="/t/1">Djokovic - Nadal</a></td>
    <td>14:00</td>
    <td>1.65</td>
    <td>2.20</td>
  </tr>
</table>
</body></html>
"""

# Empty page with no match data
BETEXPLORER_HTML_EMPTY = """
<html><body>
<div class="no-events">No events available</div>
</body></html>
"""

# Page with rows that don't have odds (header rows, etc.)
BETEXPLORER_HTML_HEADER_ROWS = """
<html><body>
<table>
  <tr><th>Match</th><th>Time</th><th>1</th><th>X</th><th>2</th></tr>
  <tr>
    <td><a href="/match/1">Juventus - Inter Milan</a></td>
    <td>20:45</td>
    <td>2.50</td>
    <td>3.20</td>
    <td>2.80</td>
  </tr>
</table>
</body></html>
"""


class TestBetExplorerAdapter(unittest.TestCase):
    """Tests for BetExplorer HTML adapter."""

    def test_standard_match_page(self):
        """Standard table with 3 matches and 1X2 odds."""
        results = parse(BETEXPLORER_HTML_STANDARD, "https://www.betexplorer.com/football/")
        self.assertEqual(len(results), 3)

        r0 = results[0]
        self.assertEqual(r0["home"], "Real Madrid")
        self.assertEqual(r0["away"], "Barcelona")
        self.assertEqual(r0["time"], "21:00")
        self.assertEqual(r0["odds"], ["1.85", "3.60", "4.20"])
        self.assertEqual(r0["source_url"], "https://www.betexplorer.com/football/")

    def test_team_names_and_odds_correct(self):
        """Verify all teams and odds are correctly extracted."""
        results = parse(BETEXPLORER_HTML_STANDARD, "https://www.betexplorer.com/football/")
        self.assertEqual(results[1]["home"], "Bayern Munich")
        self.assertEqual(results[1]["away"], "Borussia Dortmund")
        self.assertEqual(results[1]["time"], "18:30")
        self.assertEqual(results[1]["odds"], ["1.55", "4.10", "5.50"])

        self.assertEqual(results[2]["home"], "PSG")
        self.assertEqual(results[2]["away"], "Marseille")
        self.assertEqual(results[2]["odds"], ["1.40", "4.75", "7.00"])

    def test_multi_sport_page(self):
        """Page with multiple sports should extract all matches."""
        results = parse(BETEXPLORER_HTML_MULTI_SPORT, "https://www.betexplorer.com/")
        self.assertEqual(len(results), 2)
        homes = [r["home"] for r in results]
        self.assertIn("Liverpool", homes)
        self.assertIn("Djokovic", homes)

    def test_empty_page_falls_back(self):
        """Empty page should fall back to raw_adapter."""
        results = parse(BETEXPLORER_HTML_EMPTY, "https://www.betexplorer.com/")
        self.assertIsInstance(results, list)

    def test_header_rows_skipped(self):
        """<th> header rows should not produce matches; only <td> rows."""
        results = parse(BETEXPLORER_HTML_HEADER_ROWS, "https://www.betexplorer.com/")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["home"], "Juventus")
        self.assertEqual(results[0]["away"], "Inter Milan")
        self.assertEqual(results[0]["time"], "20:45")

    def test_result_format(self):
        """All results must have required fields."""
        results = parse(BETEXPLORER_HTML_STANDARD, "https://www.betexplorer.com/football/")
        for r in results:
            self.assertIn("home", r)
            self.assertIn("away", r)
            self.assertIn("time", r)
            self.assertIn("source_url", r)
            self.assertIn("raw", r)


if __name__ == "__main__":
    unittest.main()
