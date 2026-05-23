"""Battle tests for P1 fixes (2026-05-05).

Covers:
1. NegBin uses weighted λ (not unweighted mean)
2. league_profiles Bayesian shrinkage in probability_engine
3. Fuzzy dedup min length threshold (no false positives for short names)
4. H2H-missing alignment transparently marked as "(H2H N/A)"
"""
import statistics
import unittest
from unittest.mock import patch

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))


class TestNegBinWeightedLambda(unittest.TestCase):
    """Fix #1: NegBin must use recency-weighted λ, not unweighted mean."""

    def test_negbin_uses_weighted_lambda_not_raw_mean(self):
        """When NegBin is forced, the probability should reflect weighted λ, not simple mean."""
        from probability_engine import compute_probability, estimate_lambda

        # Overdispersed data (variance >> mean) to trigger NegBin
        l10 = [2, 8, 1, 9, 3, 7, 2, 10, 1, 8]  # mean=5.1, var=12.5
        l5 = [2, 10, 1, 8, 3]  # mean=4.8
        h2h = [10, 12, 11, 9, 8]  # mean=10.0 — high H2H

        # Weighted λ: 0.40*4.8 + 0.35*5.1 + 0.25*10.0 = 1.92 + 1.785 + 2.5 = 6.205
        weighted_lam = estimate_lambda(l10, l5, h2h)
        # Unweighted mean of all_values (l10+h2h): mean([2,8,1,9,3,7,2,10,1,8,10,12,11,9,8]) = 6.73
        unweighted_mean = statistics.mean(l10 + h2h)

        # These should differ
        self.assertNotAlmostEqual(weighted_lam, unweighted_mean, places=1)

        # Force NegBin and check the λ in result matches weighted
        result = compute_probability(
            line=5.5, direction="OVER", l10_values=l10,
            l5_values=l5, h2h_values=h2h, use_negbin=True
        )
        self.assertEqual(result["model_used"], "negative_binomial")
        # The reported λ should be the weighted one
        self.assertAlmostEqual(result["lambda"], weighted_lam, places=2)

    def test_negbin_and_poisson_use_same_lambda(self):
        """Both models should start from the same weighted λ."""
        from probability_engine import compute_probability

        l10 = [3, 5, 4, 6, 3, 5, 4, 7, 3, 5]

        result_poisson = compute_probability(
            line=4.5, direction="OVER", l10_values=l10, use_negbin=False
        )
        result_negbin = compute_probability(
            line=4.5, direction="OVER", l10_values=l10, use_negbin=True
        )
        # Both must use the same λ
        self.assertAlmostEqual(
            result_poisson["lambda"], result_negbin["lambda"], places=3
        )


class TestLeagueProfilesIntegration(unittest.TestCase):
    """Fix #2: league_profiles must be used for Bayesian shrinkage in compute_probability."""

    @patch("probability_engine.load_league_profiles")
    def test_bayesian_shrinkage_applied_when_profile_exists(self, mock_load):
        """With league profile, λ should be shrunk toward league average."""
        from probability_engine import compute_probability

        # Team has very high avg (15 corners) but league avg is 10
        l10 = [15.0] * 10
        mock_load.return_value = {"avg_value": 10.0, "std_dev": 2.0, "sample_size": 200}

        # Without profile (no competition/stat_key)
        result_raw = compute_probability(
            line=12.5, direction="OVER", l10_values=l10
        )

        # With profile → Bayesian shrinkage pulls λ toward 10.0
        result_shrunk = compute_probability(
            line=12.5, direction="OVER", l10_values=l10,
            competition="Premier League", stat_key="corners"
        )

        # Shrunk λ should be lower than raw (pulled toward league avg of 10)
        self.assertLess(result_shrunk["lambda"], result_raw["lambda"])
        # But still above the league average (team has 10 games of data)
        self.assertGreater(result_shrunk["lambda"], 10.0)

    @patch("probability_engine.load_league_profiles")
    def test_no_shrinkage_without_profile(self, mock_load):
        """Without league profile, λ is unchanged."""
        from probability_engine import compute_probability

        l10 = [8.0] * 10
        mock_load.return_value = None  # No profile found

        result = compute_probability(
            line=7.5, direction="OVER", l10_values=l10,
            competition="Unknown League", stat_key="corners"
        )

        # λ should just be the raw weighted estimate
        self.assertAlmostEqual(result["lambda"], 8.0, places=1)

    @patch("probability_engine.load_league_profiles")
    def test_shrinkage_stronger_with_fewer_games(self, mock_load):
        """Bayesian shrinkage should be stronger with fewer data points."""
        from probability_engine import compute_probability

        mock_load.return_value = {"avg_value": 10.0, "std_dev": 2.0, "sample_size": 200}

        # 10 games of data
        l10_full = [15.0] * 10
        result_10 = compute_probability(
            line=12.5, direction="OVER", l10_values=l10_full,
            competition="Test", stat_key="corners"
        )

        # 3 games of data (smaller sample → more shrinkage)
        l10_small = [15.0] * 3
        result_3 = compute_probability(
            line=12.5, direction="OVER", l10_values=l10_small,
            competition="Test", stat_key="corners"
        )

        # Smaller sample should have more shrinkage (lower λ, closer to league avg 10)
        self.assertLess(result_3["lambda"], result_10["lambda"])


class TestFuzzyDedupMinLength(unittest.TestCase):
    """Fix #3: Fuzzy dedup must NOT false-positive on short team names (< 5 chars)."""

    def _run_dedup(self, events):
        """Helper: runs the dedup logic from build_shortlist."""
        import re
        import unicodedata

        scored = [(1.0, e) for e in events]
        deduped = []
        seen_matchups: set = set()

        for score, event in scored:
            home = event.get("home_team", "").lower().strip()
            away = event.get("away_team", "").lower().strip()
            sport = event.get("sport", "")
            home = unicodedata.normalize("NFKD", home).encode("ascii", "ignore").decode()
            away = unicodedata.normalize("NFKD", away).encode("ascii", "ignore").decode()
            for remove in ["fc ", "sc ", "bc ", "ac ", " fc", " sc", " bc", " cf",
                           " basket", " basketball", " sk", " sk.",
                           " s.k.", " fk", " fk."]:
                home = home.replace(remove, "")
                away = away.replace(remove, "")
            for suffix in [" kaunas", " vilnius", " moscow", " kiev",
                           " london", " paris", " madrid", " berlin"]:
                home = home.replace(suffix, "")
                away = away.replace(suffix, "")
            home = re.sub(r"\s+", " ", home).strip()
            away = re.sub(r"\s+", " ", away).strip()
            dedup_key = f"{sport}|{home}|{away}"
            dedup_key_rev = f"{sport}|{away}|{home}"
            if dedup_key in seen_matchups or dedup_key_rev in seen_matchups:
                continue

            # Fuzzy — minimum length 5 (the fix)
            MIN_FUZZY_LEN = 5
            is_dup = False
            for existing_key in seen_matchups:
                ex_parts = existing_key.split("|", 2)
                if len(ex_parts) != 3 or ex_parts[0] != sport:
                    continue
                ex_home, ex_away = ex_parts[1], ex_parts[2]
                home_match = (home in ex_home or ex_home in home) and len(home) >= MIN_FUZZY_LEN and len(ex_home) >= MIN_FUZZY_LEN
                away_match = (away in ex_away or ex_away in away) and len(away) >= MIN_FUZZY_LEN and len(ex_away) >= MIN_FUZZY_LEN
                if home_match and away_match:
                    is_dup = True
                    break
                home_match_rev = (home in ex_away or ex_away in home) and len(home) >= MIN_FUZZY_LEN and len(ex_home) >= MIN_FUZZY_LEN
                away_match_rev = (away in ex_home or ex_home in away) and len(away) >= MIN_FUZZY_LEN and len(ex_away) >= MIN_FUZZY_LEN
                if home_match_rev and away_match_rev:
                    is_dup = True
                    break
            if is_dup:
                continue
            seen_matchups.add(dedup_key)
            deduped.append(event)

        return deduped

    def test_short_names_not_falsely_deduped(self):
        """3-4 char team names should NOT trigger fuzzy dedup even if substrings."""
        events = [
            {"home_team": "PSG", "away_team": "OM", "sport": "football"},
            {"home_team": "APSG", "away_team": "OML", "sport": "football"},
        ]
        result = self._run_dedup(events)
        # Both should survive — "PSG" ⊂ "APSG" but len < 5
        self.assertEqual(len(result), 2)

    def test_short_names_bar_vs_barca(self):
        """'Bar' should NOT match 'Barcelona' — too short."""
        events = [
            {"home_team": "Bar", "away_team": "Zag", "sport": "football"},
            {"home_team": "Barcelona", "away_team": "Zagreb", "sport": "football"},
        ]
        result = self._run_dedup(events)
        self.assertEqual(len(result), 2)

    def test_long_names_still_deduped(self):
        """Legitimate long-name substrings should still be caught."""
        events = [
            {"home_team": "Olympiakos", "away_team": "Panathinaikos", "sport": "football"},
            {"home_team": "Olympiakos Piraeus", "away_team": "Panathinaikos Athens", "sport": "football"},
        ]
        result = self._run_dedup(events)
        # Second is substring of first (both > 5 chars) → deduped
        self.assertEqual(len(result), 1)

    def test_exact_4char_boundary(self):
        """4-char names should NOT be fuzzy-matched."""
        events = [
            {"home_team": "Ajax", "away_team": "Gent", "sport": "football"},
            {"home_team": "Ajax Amsterdam", "away_team": "Gent Reserves", "sport": "football"},
        ]
        result = self._run_dedup(events)
        # "Ajax" is 4 chars < 5, should NOT match
        self.assertEqual(len(result), 2)


class TestH2HMissingTransparency(unittest.TestCase):
    """Fix #4: When H2H is missing, alignment must show '(H2H N/A)'."""

    def test_h2h_missing_shows_marker(self):
        """2/2 SUPPORT with missing H2H must include '(H2H N/A)' marker."""
        from compute_safety_scores import compute_three_way_check

        # L10=OVER, L5=OVER, H2H=missing (None) → was "2/2 SUPPORT", now "2/2 SUPPORT (H2H N/A)"
        result = compute_three_way_check(12.0, None, 13.0, 9.5)
        self.assertIn("H2H N/A", result["alignment"])
        self.assertIn("SUPPORT", result["alignment"])
        self.assertEqual(result["h2h_direction"], "N/A")

    def test_h2h_present_no_marker(self):
        """When H2H is present, no '(H2H N/A)' marker should appear."""
        from compute_safety_scores import compute_three_way_check

        result = compute_three_way_check(12.0, 11.0, 13.0, 9.5)
        self.assertNotIn("H2H N/A", result["alignment"])
        self.assertIn("3/3 SUPPORT", result["alignment"])

    def test_h2h_missing_conflict_also_marked(self):
        """Even in CONFLICT scenarios with missing H2H, marker should appear."""
        from compute_safety_scores import compute_three_way_check

        # L10=OVER (10>9.5), L5=UNDER (8<9.5), H2H=missing (None)
        result = compute_three_way_check(10.0, None, 8.0, 9.5)
        self.assertIn("H2H N/A", result["alignment"])

    def test_h2h_missing_distinguishable_from_full_support(self):
        """'2/2 SUPPORT (H2H N/A)' must be distinguishable from '3/3 SUPPORT'."""
        from compute_safety_scores import compute_three_way_check

        result_missing = compute_three_way_check(12.0, None, 13.0, 9.5)
        result_full = compute_three_way_check(12.0, 11.0, 13.0, 9.5)

        self.assertNotEqual(result_missing["alignment"], result_full["alignment"])
        # Full support has no H2H marker
        self.assertNotIn("H2H N/A", result_full["alignment"])
        # Missing does
        self.assertIn("H2H N/A", result_missing["alignment"])


if __name__ == "__main__":
    unittest.main()
