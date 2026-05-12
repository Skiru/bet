"""Unit tests for Flashscore volleyball parsing fix."""

import unittest
from scripts.adapters.flashscore_adapter import parse
from scripts.adapters.raw_adapter import parse as raw_parse


# Sample HTML simulating Flashscore volleyball page with league headers
# merged into the same container as match rows.
VOLLEYBALL_HTML_MERGED_HEADERS = """
<html><body>
<div class="sportName volleyball">
  <div class="event__header">
    <span class="event__title">PlusLiga - Playoffs</span>
  </div>
  <div class="event__match">
    <div class="event__time">18:00</div>
    <div class="event__participant event__participant--home">Jastrzebski Wegiel</div>
    <div class="event__participant event__participant--away">ZAKSA Kedzierzyn-Kozle</div>
  </div>
  <div class="event__match">
    <div class="event__time">20:30</div>
    <div class="event__participant event__participant--home">Resovia Rzeszow</div>
    <div class="event__participant event__participant--away">Trefl Gdansk</div>
  </div>
  <div class="event__header">
    <span class="event__title">Serie A1 - Regular Season</span>
  </div>
  <div class="event__match">
    <div class="event__time">19:00</div>
    <div class="event__participant event__participant--home">Perugia</div>
    <div class="event__participant event__participant--away">Modena</div>
  </div>
</div>
</body></html>
"""

# Volleyball page with NO events (just headers)
VOLLEYBALL_HTML_EMPTY = """
<html><body>
<div class="sportName volleyball">
  <div class="event__header">
    <span class="event__title">PlusLiga - Playoffs</span>
  </div>
  <div class="event__header">
    <span class="event__title">Serie A1</span>
  </div>
</div>
</body></html>
"""

# Non-volleyball (football) HTML that should still parse with existing heuristics
FOOTBALL_HTML = """
<html><body>
<div class="event__match">
  <div class="event__time">21:00</div>
  <div class="event__participant event__participant--home">Real Madrid</div>
  <div class="event__participant event__participant--away">Barcelona</div>
</div>
<div class="event__match">
  <div class="event__participant event__participant--home">Bayern Munich</div>
  <div class="event__participant event__participant--away">Borussia Dortmund</div>
</div>
</body></html>
"""

# HTML where league header text is literally merged into the match row text
# (the original bug: no separate header element, text is concatenated)
VOLLEYBALL_HTML_TEXT_MERGED = """
<html><body>
<div class="event__match">
  <div class="event__header">PlusLiga - Playoffs</div>
  <div class="event__participant event__participant--home">Jastrzebski Wegiel</div>
  <div class="event__participant event__participant--away">ZAKSA Kedzierzyn-Kozle</div>
</div>
</body></html>
"""


class TestFlashscoreVolleyball(unittest.TestCase):
    """Tests for Heuristic 0 targeting Flashscore event__ class structure."""

    def test_volleyball_separates_league_from_teams(self):
        """League headers must NOT appear in home/away fields."""
        results = parse(VOLLEYBALL_HTML_MERGED_HEADERS, "https://www.flashscore.com/volleyball/")
        self.assertTrue(len(results) >= 3, f"Expected >= 3 matches, got {len(results)}")
        for r in results:
            self.assertNotIn("PlusLiga", r["home"])
            self.assertNotIn("Playoffs", r["home"])
            self.assertNotIn("Serie A1", r["home"])
            self.assertNotIn("PlusLiga", r["away"])

    def test_volleyball_time_extracted(self):
        """Time must be extracted from event__time elements."""
        results = parse(VOLLEYBALL_HTML_MERGED_HEADERS, "https://www.flashscore.com/volleyball/")
        times = [r["time"] for r in results]
        self.assertIn("18:00", times)
        self.assertIn("20:30", times)
        self.assertIn("19:00", times)

    def test_volleyball_league_context_tracked(self):
        """Parsed events should have league context when available."""
        results = parse(VOLLEYBALL_HTML_MERGED_HEADERS, "https://www.flashscore.com/volleyball/")
        # First two matches should be under PlusLiga
        plusliga = [r for r in results if r.get("league") and "PlusLiga" in r["league"]]
        self.assertTrue(len(plusliga) >= 2, "Expected at least 2 PlusLiga matches")
        # Last match should be under Serie A1
        serie = [r for r in results if r.get("league") and "Serie A1" in r["league"]]
        self.assertTrue(len(serie) >= 1, "Expected at least 1 Serie A1 match")

    def test_volleyball_correct_team_names(self):
        """Team names must be clean and correct."""
        results = parse(VOLLEYBALL_HTML_MERGED_HEADERS, "https://www.flashscore.com/volleyball/")
        homes = [r["home"] for r in results]
        aways = [r["away"] for r in results]
        self.assertIn("Jastrzebski Wegiel", homes)
        self.assertIn("ZAKSA Kedzierzyn-Kozle", aways)
        self.assertIn("Perugia", homes)
        self.assertIn("Modena", aways)

    def test_empty_volleyball_page(self):
        """A page with only headers and no match rows should not crash."""
        results = parse(VOLLEYBALL_HTML_EMPTY, "https://www.flashscore.com/volleyball/")
        # Should fall back to raw_adapter (may return empty or raw results)
        self.assertIsInstance(results, list)

    def test_football_not_broken(self):
        """Non-volleyball sport parsing must still work."""
        results = parse(FOOTBALL_HTML, "https://www.flashscore.com/football/")
        self.assertTrue(len(results) >= 2, f"Expected >= 2 matches, got {len(results)}")
        homes = [r["home"] for r in results]
        self.assertIn("Real Madrid", homes)
        self.assertIn("Bayern Munich", homes)

    def test_merged_text_header_stripped(self):
        """When header text is merged into match element, it should be stripped."""
        results = parse(VOLLEYBALL_HTML_TEXT_MERGED, "https://www.flashscore.com/volleyball/")
        for r in results:
            self.assertNotIn("PlusLiga", r["home"])
            self.assertNotIn("Playoffs", r["home"])


# =============================================================
# Tournament round tests (event__round must NOT overwrite league)
# =============================================================

VOLLEYBALL_TOURNAMENT_HTML = """
<html><body>
<div class="headerLeague">
  <span class="headerLeague__category-text">World</span>
  <span class="headerLeague__title-text">FIVB World Championship</span>
</div>
<div class="event__round">Final</div>
<div class="event__match" id="g_12_abc123">
  <div class="event__time">20:30</div>
  <div class="event__homeParticipant">Poland</div>
  <div class="event__awayParticipant">Brazil</div>
  <a class="eventRowLink" href="/match/abc123/#/match-summary"></a>
</div>
<div class="event__round">3rd Place</div>
<div class="event__match" id="g_12_def456">
  <div class="event__time">17:00</div>
  <div class="event__homeParticipant">Italy</div>
  <div class="event__awayParticipant">USA</div>
  <a class="eventRowLink" href="/match/def456/#/match-summary"></a>
</div>
</body></html>
"""


class TestFlashscoreTournamentRound(unittest.TestCase):
    """Tests that event__round labels go to 'round' field, NOT 'league'."""

    def test_round_not_in_league(self):
        """Round labels like 'Final' must NOT appear in the league field."""
        results = parse(VOLLEYBALL_TOURNAMENT_HTML, "https://www.flashscore.com/volleyball/")
        self.assertEqual(len(results), 2)
        for r in results:
            league = r.get("league", "")
            self.assertNotIn("Final", league)
            self.assertNotIn("3rd Place", league)

    def test_round_stored_as_metadata(self):
        """Round labels should be in entry['round']."""
        results = parse(VOLLEYBALL_TOURNAMENT_HTML, "https://www.flashscore.com/volleyball/")
        self.assertEqual(results[0].get("round"), "Final")
        self.assertEqual(results[1].get("round"), "3rd Place")

    def test_league_from_header(self):
        """League should come from headerLeague, not from event__round."""
        results = parse(VOLLEYBALL_TOURNAMENT_HTML, "https://www.flashscore.com/volleyball/")
        for r in results:
            self.assertEqual(r.get("league"), "FIVB World Championship")

    def test_match_id_from_element_id(self):
        """match_id should be extracted from the element id attribute."""
        results = parse(VOLLEYBALL_TOURNAMENT_HTML, "https://www.flashscore.com/volleyball/")
        ids = [r.get("match_id") for r in results]
        self.assertIn("abc123", ids)
        self.assertIn("def456", ids)


# =============================================================
# match_id fallback from eventRowLink URL
# =============================================================

VOLLEYBALL_NO_ID_HTML = """
<html><body>
<div class="headerLeague">
  <span class="headerLeague__category-text">Belgium</span>
  <span class="headerLeague__title-text">1st League</span>
</div>
<div class="event__match">
  <div class="event__time">20:30</div>
  <div class="event__homeParticipant">Maaseik</div>
  <div class="event__awayParticipant">Roeselare</div>
  <a class="eventRowLink" href="/match/xyz789/#/match-summary"></a>
</div>
</body></html>
"""


class TestFlashscoreMatchIdFallback(unittest.TestCase):
    """Tests that match_id is extracted from eventRowLink when element id is absent."""

    def test_match_id_from_url(self):
        """When no element id, match_id should come from the match URL path."""
        results = parse(VOLLEYBALL_NO_ID_HTML, "https://www.flashscore.com/volleyball/")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["match_id"], "xyz789")

    def test_match_url_set(self):
        """match_url should be the full URL from eventRowLink."""
        results = parse(VOLLEYBALL_NO_ID_HTML, "https://www.flashscore.com/volleyball/")
        self.assertIn("/match/xyz789/", results[0]["match_url"])


# =============================================================
# raw_parse fallback sport propagation
# =============================================================

RAW_FALLBACK_HTML = """
<html><body>
<div>Maaseik - Roeselare 20:30</div>
</body></html>
"""


class TestFlashscoreRawFallbackSport(unittest.TestCase):
    """Tests that sport is propagated when falling back to raw_parse."""

    def test_sport_propagated_in_fallback(self):
        """raw_parse fallback should still have sport='volleyball' from URL."""
        results = parse(RAW_FALLBACK_HTML, "https://www.flashscore.com/volleyball/")
        # raw_parse may or may not find matches, but if it does, sport should be set
        for r in results:
            self.assertEqual(r.get("sport"), "volleyball")


if __name__ == "__main__":
    unittest.main()
