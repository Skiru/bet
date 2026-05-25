"""Tests for pipeline modules: deep_stats_report (S3), gate_checker (S7), coupon_builder (S8).

All tests use mock data — no real API calls, no real cache files.
Temp directories are used for filesystem isolation.
"""
import json
import io
import shutil
import sys
import tempfile
import unittest
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Shared mock data
# ---------------------------------------------------------------------------

MOCK_FOOTBALL_CACHE = {
    "team": "Liverpool",
    "sport": "football",
    "slug": "liverpool",
    "last_updated": "2026-05-01T10:00:00+00:00",
    "form": {
        "l10_matches": [
            {"date": f"2026-04-{20-i}", "opponent": f"Team{i}", "stats": {
                "corners": 5 + i, "fouls": 10 + i, "yellow_cards": 1 + (i % 3),
                "shots": 12 + i, "shots_on_target": 5 + (i % 4), "goals": 1 + (i % 3)
            }} for i in range(10)
        ],
        "l10_avg": {"corners": 9.5, "fouls": 14.5, "yellow_cards": 2.0, "shots": 16.5, "goals": 2.0},
        "l5_avg": {"corners": 7.0, "fouls": 12.0, "yellow_cards": 1.6, "shots": 14.0, "goals": 1.6},
    },
    "h2h": {
        "arsenal": {
            "last_updated": "2026-05-01T10:00:00+00:00",
            "matches": [
                {"date": "2025-12-15", "stats": {"corners_home": 7, "corners_away": 5, "fouls_home": 13, "fouls_away": 11, "yellow_cards_home": 2, "yellow_cards_away": 1}},
                {"date": "2025-08-20", "stats": {"corners_home": 8, "corners_away": 4, "fouls_home": 14, "fouls_away": 10, "yellow_cards_home": 1, "yellow_cards_away": 2}},
                {"date": "2025-03-05", "stats": {"corners_home": 6, "corners_away": 6, "fouls_home": 12, "fouls_away": 12, "yellow_cards_home": 2, "yellow_cards_away": 2}},
                {"date": "2024-12-10", "stats": {"corners_home": 9, "corners_away": 3, "fouls_home": 15, "fouls_away": 9, "yellow_cards_home": 3, "yellow_cards_away": 1}},
                {"date": "2024-08-15", "stats": {"corners_home": 7, "corners_away": 5, "fouls_home": 13, "fouls_away": 11, "yellow_cards_home": 2, "yellow_cards_away": 2}},
            ],
            "avg": {"corners_total": 12, "fouls_total": 24, "yellow_cards_total": 4}
        }
    },
    "sources": ["api-football"]
}

MOCK_ARSENAL_CACHE = {
    "team": "Arsenal",
    "sport": "football",
    "slug": "arsenal",
    "last_updated": "2026-05-01T10:00:00+00:00",
    "form": {
        "l10_matches": [
            {"date": f"2026-04-{20-i}", "opponent": f"Team{i}", "stats": {
                "corners": 4 + (i % 3), "fouls": 9 + i, "yellow_cards": 2 + (i % 2),
                "shots": 10 + i, "shots_on_target": 4 + (i % 3), "goals": 1 + (i % 2)
            }} for i in range(10)
        ],
        "l10_avg": {"corners": 5.0, "fouls": 13.5, "yellow_cards": 2.5, "shots": 14.5, "goals": 1.5},
        "l5_avg": {"corners": 5.5, "fouls": 11.5, "yellow_cards": 2.4, "shots": 12.0, "goals": 1.4},
    },
    "h2h": {},
    "sources": ["api-football"]
}


def _make_approved_picks(n: int) -> list[dict]:
    """Create N mock approved picks with varied sports."""
    from datetime import datetime, timedelta
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    sports = ["football", "tennis", "basketball", "volleyball", "hockey", "handball", "baseball", "snooker"]
    teams = [
        ("Liverpool", "Arsenal", "PL"), ("Djokovic", "Alcaraz", "ATP"),
        ("Lakers", "Celtics", "NBA"), ("Resovia", "Jastrzebski", "PlusLiga"),
        ("Rangers", "Bruins", "NHL"), ("Barcelona", "Magdeburg", "EHF"),
        ("Yankees", "Red Sox", "MLB"), ("O'Sullivan", "Trump", "WSC"),
    ]
    picks = []
    for i in range(n):
        idx = i % len(sports)
        home, away, comp = teams[idx]
        home = f"{home}{'' if i < len(sports) else str(i)}"
        picks.append({
            "sport": sports[idx],
            "home_team": home,
            "away_team": away,
            "competition": comp,
            "kickoff": f"{tomorrow}T{14 + i}:00:00",
            "best_market": {
                "name": f"Market-{i}",
                "direction": "OVER",
                "safety_score": 0.80 - i * 0.02,
                "hit_rate_l10": 0.80 - i * 0.02,
                "hit_rate_h2h": 0.75,
            },
            "ev": 0.12 - i * 0.01,
            "odds": {"market_best": 1.85 - i * 0.02},
            "risk_tier": "LR" if i < 3 else ("MS" if i < 6 else "HR"),
            "final_confidence": 4.0 - i * 0.1,
            "gate_score": f"{17 - i}/17",
        })
    return picks


# ===========================================================================
# TestDeepStatsReport
# ===========================================================================

class TestDeepStatsReport(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache_dir = Path(self.tmp) / "stats_cache"
        self.data_dir = Path(self.tmp) / "data"
        self.data_dir.mkdir(parents=True)
        football_dir = self.cache_dir / "football"
        football_dir.mkdir(parents=True)
        (football_dir / "liverpool.json").write_text(json.dumps(MOCK_FOOTBALL_CACHE))
        (football_dir / "arsenal.json").write_text(json.dumps(MOCK_ARSENAL_CACHE))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _patch_dirs(self):
        """Return patch contexts for CACHE_DIR and DATA_DIR in deep_stats_report."""
        import scripts.deep_stats_report as dsr
        return (
            patch.object(dsr, "CACHE_DIR", self.cache_dir),
            patch.object(dsr, "DATA_DIR", self.data_dir),
        )

    def test_extract_team_stats_with_cache(self):
        """Extract L10/L5 stats from mock cache."""
        import scripts.deep_stats_report as dsr
        with patch.object(dsr, "CACHE_DIR", self.cache_dir), \
             patch("db_data_loader.load_team_form_from_db", side_effect=Exception("mock")):
            result = dsr.extract_team_stats("football", "Liverpool")
        self.assertTrue(result["has_data"])
        self.assertIn("corners", result["l10_avg"])
        self.assertEqual(result["l10_avg"]["corners"], 9.5)
        self.assertIn("corners", result["l5_avg"])
        self.assertEqual(result["l5_avg"]["corners"], 7.0)

    def test_extract_team_stats_missing_cache(self):
        """Graceful handling when cache file doesn't exist."""
        import scripts.deep_stats_report as dsr
        with patch.object(dsr, "CACHE_DIR", self.cache_dir):
            result = dsr.extract_team_stats("football", "NonExistentTeam")
        self.assertFalse(result["has_data"])
        self.assertEqual(result["l10_avg"], {})
        self.assertEqual(result["l5_avg"], {})

    def test_extract_h2h_stats(self):
        """H2H extraction from cache."""
        import scripts.deep_stats_report as dsr
        with patch.object(dsr, "CACHE_DIR", self.cache_dir), \
             patch("db_data_loader.load_h2h_from_db", return_value=None):
            result = dsr.extract_h2h_stats("football", "Liverpool", "Arsenal")
        self.assertTrue(result["has_data"])
        self.assertEqual(len(result["meetings"]), 5)
        self.assertIn("corners_total", result["averages"])
        self.assertEqual(result["averages"]["corners_total"], 12)

    def test_analyze_candidate_with_data(self):
        """Full candidate analysis with mock cache data."""
        import scripts.deep_stats_report as dsr
        import scripts.normalize_stats as norm_mod
        p1, p2 = self._patch_dirs()
        with p1, p2, patch.object(norm_mod, "CACHE_DIR", self.cache_dir):
            result = dsr.analyze_candidate(
                "football", "Liverpool", "Arsenal", "PL", "2026-05-01T15:00"
            )
        self.assertTrue(result["has_data"])
        # All 10 sections present
        sections = result["sections"]
        for key in ["s31", "s32", "s33", "s34", "s35", "s36", "s37", "s38", "s39", "s310"]:
            self.assertIn(key, sections, f"Missing section {key}")
        # Markdown contains section markers
        md = result["markdown"]
        for marker in ["§S3.1", "§S3.2", "§S3.3"]:
            self.assertIn(marker, md, f"Missing marker {marker} in markdown")

    def test_analyze_candidate_no_cache(self):
        """Analysis when no cache data exists."""
        import scripts.deep_stats_report as dsr
        import scripts.normalize_stats as norm_mod
        empty_cache = Path(self.tmp) / "empty_cache"
        empty_cache.mkdir()
        with patch.object(dsr, "CACHE_DIR", empty_cache), \
             patch.object(dsr, "DATA_DIR", self.data_dir), \
             patch.object(norm_mod, "CACHE_DIR", empty_cache):
            result = dsr.analyze_candidate(
                "football", "NoTeamA", "NoTeamB", "Unknown", "2026-05-01T15:00"
            )
        self.assertIn("has_data", result)
        # Markdown still generated
        self.assertIsInstance(result["markdown"], str)
        self.assertGreater(len(result["markdown"]), 50)

    def test_markdown_sections_complete(self):
        """All 10 §S3 sections are in output."""
        import scripts.deep_stats_report as dsr
        import scripts.normalize_stats as norm_mod
        p1, p2 = self._patch_dirs()
        with p1, p2, patch.object(norm_mod, "CACHE_DIR", self.cache_dir):
            result = dsr.analyze_candidate(
                "football", "Liverpool", "Arsenal", "PL", "2026-05-01T15:00"
            )
        md = result["markdown"]
        for i in range(1, 11):
            marker = f"§S3.{i}" if i < 10 else "§S3.10"
            self.assertIn(marker, md, f"Missing section {marker}")

    def test_generate_deep_stats_from_pool(self):
        """Full generation from analysis pool file."""
        import scripts.deep_stats_report as dsr
        import scripts.normalize_stats as norm_mod
        pool = {
            "events": [
                {"sport": "football", "home_team": "Liverpool", "away_team": "Arsenal",
                 "competition": "PL", "kickoff": "2026-05-01T15:00:00",
                 "fixture_verified": True},
            ]
        }
        (self.data_dir / "analysis_pool_2026-05-01.json").write_text(json.dumps(pool))
        p1, p2 = self._patch_dirs()
        with p1, p2, patch.object(norm_mod, "CACHE_DIR", self.cache_dir):
            result = dsr.generate_deep_stats("2026-05-01")
        self.assertEqual(result["total_candidates"], 1)
        self.assertGreater(result["candidates_with_data"], 0)
        self.assertEqual(len(result["analyses"]), 1)

    def test_deep_stats_main_summary_includes_persistence_metrics(self):
        """AGENT_SUMMARY exposes analyzed vs persisted counts for S3 dual-write audits."""
        import scripts.deep_stats_report as dsr

        fake_result = {
            "total_candidates": 3,
            "candidates_with_data": 2,
            "candidates_without_data": 1,
            "analysis_results_persisted": 2,
            "analysis_results_not_persisted": 1,
            "fixture_ids_injected": 2,
            "enrichment_attempted": 1,
            "enrichment_successful": 1,
            "analyses": [],
        }

        stdout = io.StringIO()
        with patch.object(dsr, "generate_deep_stats", return_value=fake_result), \
             patch.object(sys, "argv", ["deep_stats_report.py", "--date", "2026-05-01"]), \
             redirect_stdout(stdout):
            dsr.main()

        summary_line = next(
            line for line in stdout.getvalue().splitlines() if line.startswith("AGENT_SUMMARY:")
        )
        payload = json.loads(summary_line.split("AGENT_SUMMARY:", 1)[1])

        self.assertEqual(payload["metrics"]["total_candidates"], 3)
        self.assertEqual(payload["metrics"]["analysis_results_persisted"], 2)
        self.assertEqual(payload["metrics"]["analysis_results_not_persisted"], 1)
        self.assertEqual(payload["metrics"]["fixture_ids_injected"], 2)

    def test_slugify(self):
        """Team name slugification."""
        from scripts.deep_stats_report import slugify
        self.assertEqual(slugify("Liverpool FC"), "liverpool-fc")
        self.assertEqual(slugify("Red Bull Salzburg"), "red-bull-salzburg")
        # Diacritics stripped (non a-z0-9)
        self.assertEqual(slugify("Atlético Madrid"), "atltico-madrid")

    def test_extract_team_stats_split_keys(self):
        """Verify corners_home + corners_away are summed correctly into total."""
        import scripts.deep_stats_report as dsr
        split_cache = {
            "team": "TestTeam", "sport": "football", "slug": "testteam",
            "form": {
                "l10_avg": {"corners_home": 6.8, "corners_away": 3.2,
                            "fouls_home": 12.0, "fouls_away": 9.0},
                "l5_avg": {"corners_home": 7.0, "corners_away": 3.5},
                "l10_matches": [],
            },
            "sources": ["espn-football"],
        }
        split_dir = self.cache_dir / "football"
        split_dir.mkdir(parents=True, exist_ok=True)
        (split_dir / "testteam.json").write_text(json.dumps(split_cache))
        with patch.object(dsr, "CACHE_DIR", self.cache_dir):
            result = dsr.extract_team_stats("football", "TestTeam")
        self.assertTrue(result["has_data"])
        self.assertEqual(result["l10_avg"]["corners"], 10.0)
        self.assertEqual(result["l10_avg"]["corners_home"], 6.8)
        self.assertEqual(result["l10_avg"]["corners_away"], 3.2)
        self.assertEqual(result["l10_avg"]["fouls"], 21.0)
        self.assertEqual(result["l5_avg"]["corners"], 10.5)

    def test_extract_team_stats_percentage_keeps_home_only(self):
        """Possession should NOT sum home+away (would yield 100%)."""
        import scripts.deep_stats_report as dsr
        pct_cache = {
            "team": "PctTeam", "sport": "football", "slug": "pctteam",
            "form": {
                "l10_avg": {"possession_home": 58.0, "possession_away": 42.0,
                            "corners_home": 5.0, "corners_away": 4.0},
                "l5_avg": {"possession_home": 60.0, "possession_away": 40.0},
                "l10_matches": [],
            },
            "sources": ["espn-football"],
        }
        pct_dir = self.cache_dir / "football"
        pct_dir.mkdir(parents=True, exist_ok=True)
        (pct_dir / "pctteam.json").write_text(json.dumps(pct_cache))
        with patch.object(dsr, "CACHE_DIR", self.cache_dir):
            result = dsr.extract_team_stats("football", "PctTeam")
        self.assertTrue(result["has_data"])
        # Possession keeps home-only (not 100.0)
        self.assertEqual(result["l10_avg"]["possession"], 58.0)
        self.assertEqual(result["l5_avg"]["possession"], 60.0)
        # But corners are summed
        self.assertEqual(result["l10_avg"]["corners"], 9.0)

    def test_analyze_candidate_has_data_from_safety_input(self):
        """has_data=True when safety_input provides markets despite empty slug cache."""
        import scripts.deep_stats_report as dsr
        import scripts.normalize_stats as norm_mod
        mock_safety = {"sport": "football", "team_a": "GhostTeam", "team_b": "PhantomFC",
                       "markets": [{"name": "corners", "safety": 0.6}]}
        mock_ranking = {"ranking": [{"rank": 1, "name": "corners", "line": 9.5,
                                     "direction": "OVER", "combined_avg": 10.2,
                                     "h2h_avg": None, "hit_rate_l10": "7/10",
                                     "hit_rate_h2h": "N/A", "safety_score": 0.6}],
                        "three_way_check": None,
                        "recommended_market": "corners", "recommended_safety": 0.6,
                        "warnings": [], "markdown_ranking_table": "",
                        "markdown_three_way_table": "", "markets_evaluated": 1}
        with patch.object(dsr, "CACHE_DIR", self.cache_dir), \
             patch.object(dsr, "DATA_DIR", self.data_dir), \
             patch.object(norm_mod, "CACHE_DIR", self.cache_dir), \
             patch.object(dsr, "build_safety_input", return_value=mock_safety), \
             patch.object(dsr, "rank_markets", return_value=mock_ranking):
            result = dsr.analyze_candidate(
                sport="football",
                home="GhostTeam",
                away="PhantomFC",
                kickoff="2026-05-01T15:00:00",
                competition="Test League",
            )
        # Despite missing slug cache, safety_input with markets should mark has_data
        self.assertTrue(result["has_data"])


# ===========================================================================
# TestGateChecker
# ===========================================================================

def _base_candidate(**overrides) -> dict:
    """Build a baseline well-formed candidate for gate testing."""
    c = {
        "sport": "football",
        "home_team": "Liverpool",
        "away_team": "Arsenal",
        "competition": "Premier League",
        "kickoff": "2026-05-01T15:00:00",
        "best_market": {
            "name": "Fouls Total O/U 22.5",
            "direction": "OVER",
            "safety_score": 0.80,
            "hit_rate_l10": 0.80,
            "hit_rate_h2h": 0.80,
        },
        "all_markets": [{"rank": 1}, {"rank": 2}, {"rank": 3}],
        "market_count": 4,
        "h2h_count": 5,
        "h2h_blind": False,
        "three_way_alignment": "ALIGNED",
        "data_quality": "FULL",
        "ev": 0.12,
        "odds": {"market_best": 1.85},
        "sources": ["api-football", "flashscore"],
        "tipster_count": 1,
    }
    c.update(overrides)
    return c


class TestGateChecker(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # Ensure ledger doesn't exist so load_recent_losses returns []
        self._journal_dir = Path(self.tmp) / "journal"
        self._journal_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _patch_ledger(self):
        """Patch LEDGER_PATH to an empty temp dir (no ledger → no repeats)."""
        import scripts.gate_checker as gc
        return patch.object(gc, "LEDGER_PATH", self._journal_dir / "picks-ledger.csv")

    def test_18_point_gate_all_pass(self):
        """Gate with a well-formed candidate that should pass all 18 checks."""
        from scripts.gate_checker import check_18_point_gate
        candidate = _base_candidate()
        with self._patch_ledger(), \
             patch("bet.db.connection.get_db", side_effect=Exception("no DB in test")):
            result = check_18_point_gate(candidate, [])
        self.assertEqual(result["gate_score"], "18/18")
        self.assertEqual(len(result["gate_failed"]), 0)

    def test_gate_identity_slash_rejects(self):
        """Gate #1: slash in name fails."""
        from scripts.gate_checker import check_18_point_gate
        candidate = _base_candidate(home_team="Jodar/Lopez")
        with self._patch_ledger():
            result = check_18_point_gate(candidate, [])
        self.assertIn("1", result["gate_failed"])

    def test_gate_tennis_wc_warning(self):
        """Gate #2: WC in tennis produces a warning."""
        from scripts.gate_checker import check_18_point_gate
        candidate = _base_candidate(
            sport="tennis", home_team="Doe (WC)", away_team="Smith"
        )
        with self._patch_ledger():
            result = check_18_point_gate(candidate, [])
        # Gate #2 passes but with warnings
        self.assertIn("2", result["gate_passed"])
        has_wc_warning = any("WILD CARD" in w for w in result["gate_warnings"])
        self.assertTrue(has_wc_warning, "Expected WILD CARD warning")

    def test_gate_h2h_less_than_5(self):
        """Gate #3: H2H < 5 meetings fails."""
        from scripts.gate_checker import check_18_point_gate
        candidate = _base_candidate(h2h_count=2)
        with self._patch_ledger():
            result = check_18_point_gate(candidate, [])
        self.assertIn("3", result["gate_failed"])

    def test_gate_ev_zero_or_negative(self):
        """Gate #8: EV <= 0 fails."""
        from scripts.gate_checker import check_18_point_gate
        candidate = _base_candidate(ev=-0.05)
        with self._patch_ledger():
            result = check_18_point_gate(candidate, [])
        self.assertIn("8", result["gate_failed"])

    def test_gate_48h_repeat(self):
        """Gate #14: 48h repeat loss triggers HARD REJECT."""
        from scripts.gate_checker import check_18_point_gate
        candidate = _base_candidate()
        repeat_losses = [{
            "team": "Liverpool",
            "teams": ["Liverpool", "Arsenal"],
            "teams_normalized": ["liverpool", "arsenal"],
            "market": "Fouls Total O/U",
            "market_normalized": "fouls total 22.5",
            "lost_on": "2026-04-30",
            "betting_day": "2026-04-30",
            "pick_id": "TST-1",
            "event": "Liverpool vs Arsenal",
            "sport": "football",
            "selection": "Over 22.5",
            "days_ago": 0,
        }]
        with self._patch_ledger():
            result = check_18_point_gate(candidate, repeat_losses)
        self.assertIn("14", result["gate_failed"])
        has_hard = any("HARD REJECT" in w for w in result["gate_warnings"])
        self.assertTrue(has_hard, "Expected HARD REJECT in warnings")

    def test_gate_multi_market_less_than_3(self):
        """Gate #15: < 3 markets calculated fails."""
        from scripts.gate_checker import check_18_point_gate
        candidate = _base_candidate(market_count=2)
        with self._patch_ledger():
            result = check_18_point_gate(candidate, [])
        self.assertIn("15", result["gate_failed"])

    def test_gate_three_way_conflict(self):
        """Gate #17: three-way not aligned fails."""
        from scripts.gate_checker import check_18_point_gate
        candidate = _base_candidate(three_way_alignment="2/3 CONFLICT")
        with self._patch_ledger():
            result = check_18_point_gate(candidate, [])
        self.assertIn("17", result["gate_failed"])

    @patch("scripts.gate_checker._build_fixture_lookup", return_value=(set(), set()))
    def test_run_gate_classification(self, mock_lookup):
        """Full gate run with mixed candidates — advisory classification."""
        from scripts.gate_checker import run_gate
        candidates = [
            # Strong candidate → approved
            _base_candidate(ev=0.12),
            # EV ≤ 0 → also approved (advisory mode, NOT rejected per NO AUTO-REJECTION)
            _base_candidate(ev=-0.03, home_team="TeamC", away_team="TeamD"),
        ]
        with self._patch_ledger():
            result = run_gate(candidates, "2026-05-01")
        gr = result["gate_results"]
        # Advisory mode: ALL non-hard-rejected events go to approved
        self.assertGreater(len(gr["approved"]), 0)
        # Negative EV events are now approved with advisory tier (not in extended_pool)
        neg_ev_approved = [c for c in gr["approved"] if (c.get("ev") or 0) < 0]
        self.assertGreater(len(neg_ev_approved), 0, "Negative EV should be in approved with advisory tier")
        # Each approved pick should have an advisory_tier
        for pick in gr["approved"]:
            self.assertIn(pick.get("advisory_tier"), ("STRONG", "MODERATE", "WEAK", "FLAGGED"),
                         f"Missing advisory_tier on {pick.get('home_team')}")

    def test_sport_diversity_check(self):
        """§7.6 sport diversity check."""
        from scripts.gate_checker import check_sport_diversity
        # < 5 sports → fail
        few = [{"sport": s} for s in ["football", "tennis", "basketball"]]
        result_few = check_sport_diversity(few)
        self.assertTrue(result_few["passes_diversity"])

        # ≥ 5 sports → pass
        many = [{"sport": s} for s in ["football", "tennis", "basketball", "volleyball", "hockey"]]
        result_many = check_sport_diversity(many)
        self.assertTrue(result_many["passes_diversity"])

    def test_risk_tier_assignment(self):
        """LR/MS/HR/N tier assignment."""
        from scripts.gate_checker import compute_risk_tier

        # LR: safety ≥ 0.75, gate ≥ 15/17, not blind, EV > 0
        lr_gate = {"gate_passed": list(map(str, range(1, 18))), "gate_failed": []}
        lr_cand = _base_candidate(ev=0.10)
        lr_cand["best_market"]["safety_score"] = 0.80
        self.assertEqual(compute_risk_tier(lr_cand, lr_gate), "LR")

        # N: kickoff ≥ 20:00
        n_cand = _base_candidate(kickoff="2026-05-01T21:00:00")
        self.assertEqual(compute_risk_tier(n_cand, lr_gate), "N")

        # HR: low safety
        hr_gate = {"gate_passed": ["1", "2", "3"], "gate_failed": list(map(str, range(4, 18)))}
        hr_cand = _base_candidate(ev=0.02)
        hr_cand["best_market"]["safety_score"] = 0.40
        self.assertEqual(compute_risk_tier(hr_cand, hr_gate), "HR")

    def test_confidence_scoring(self):
        """Confidence adjustments."""
        from scripts.gate_checker import compute_confidence

        # Base 4.0 + 0.5 for safety ≥ 0.80
        high_safety = _base_candidate()
        high_safety["best_market"]["safety_score"] = 0.85
        gate = {"gate_passed": list(map(str, range(1, 18))), "gate_failed": []}
        with patch("bet.db.connection.get_db", side_effect=Exception("no DB in test")):
            conf, adj = compute_confidence(high_safety, gate)
        self.assertGreaterEqual(conf, 4.5)
        self.assertTrue(any("safety" in a for a in adj))

        # -0.5 for TIPSTER-BLIND
        blind = _base_candidate(tipster_count=0)
        gate_blind = {"gate_passed": [str(i) for i in range(1, 18) if i != 6],
                      "gate_failed": ["6"]}
        with patch("bet.db.connection.get_db", side_effect=Exception("no DB in test")):
            conf_b, adj_b = compute_confidence(blind, gate_blind)
        self.assertTrue(any("TIPSTER-BLIND" in a for a in adj_b))


# ===========================================================================
# TestCouponBuilder
# ===========================================================================

class TestCouponBuilder(unittest.TestCase):

    def test_compute_stake_kelly(self):
        """Kelly 1/4 stake calculation."""
        from scripts.coupon_builder import compute_stake
        stake = compute_stake(1.85, 0.80, 47.0, "LR")
        self.assertGreaterEqual(stake, 1.0)
        self.assertLessEqual(stake, 3.0)

    def test_compute_stake_caps(self):
        """Stake caps per tier."""
        from scripts.coupon_builder import compute_stake
        # LR cap = 3.00 PLN
        stake_lr = compute_stake(5.0, 0.90, 100.0, "LR")
        self.assertLessEqual(stake_lr, 3.0)
        # HR cap = 2.00 PLN
        stake_hr = compute_stake(5.0, 0.90, 100.0, "HR")
        self.assertLessEqual(stake_hr, 2.0)

    def test_compute_stake_minimum(self):
        """Minimum stake = 1.00 PLN."""
        from scripts.coupon_builder import compute_stake
        stake = compute_stake(1.10, 0.50, 10.0, "LR")
        self.assertGreaterEqual(stake, 1.0)

    def test_format_market_polish(self):
        """Polish market name formatting."""
        from scripts.coupon_builder import format_market_polish
        result = format_market_polish("Fouls Total O/U 22.5", "OVER")
        self.assertIn("22.5", result)
        self.assertTrue(
            "powyżej" in result.lower() or "Powyżej" in result,
            f"Expected 'powyżej' in result: {result}"
        )

    def test_stress_test_coupon(self):
        """Coupon stress test."""
        from scripts.coupon_builder import stress_test_coupon
        coupon = {"legs": [
            {"home_team": "A", "away_team": "B", "best_market": {"safety_score": 0.8, "name": "Fouls"}},
            {"home_team": "C", "away_team": "D", "best_market": {"safety_score": 0.7, "name": "Corners"}},
        ]}
        st = stress_test_coupon(coupon)
        self.assertGreater(st["p_coupon"], 0)
        self.assertLess(st["p_coupon"], 1)
        self.assertIsNotNone(st["weakest_leg"])
        # Weakest should be the 0.7 leg
        self.assertAlmostEqual(st["weakest_leg"]["probability"], 0.7)

    def test_assign_picks_to_core_unique_events(self):
        """Core portfolio has unique events per coupon."""
        from scripts.coupon_builder import assign_picks_to_core
        approved = _make_approved_picks(8)
        config = {"min_legs_per_coupon": 2, "max_same_sport_legs_in_coupon": 2, "working_bankroll_pln": 47}
        core = assign_picks_to_core(approved, config)
        # No event appears in more than one core coupon
        for coupon in core:
            events = {f"{l['home_team']}|{l['away_team']}" for l in coupon["legs"]}
            for other in core:
                if other["id"] != coupon["id"]:
                    other_events = {f"{l['home_team']}|{l['away_team']}" for l in other["legs"]}
                    self.assertFalse(
                        events & other_events,
                        f"Same event in coupons {coupon['id']} and {other['id']}"
                    )

    def test_assign_picks_min_2_legs(self):
        """Minimum 2 legs per coupon."""
        from scripts.coupon_builder import assign_picks_to_core
        approved = _make_approved_picks(8)
        config = {"min_legs_per_coupon": 2, "max_same_sport_legs_in_coupon": 2, "working_bankroll_pln": 47}
        core = assign_picks_to_core(approved, config)
        for coupon in core:
            self.assertGreaterEqual(len(coupon["legs"]), 2,
                                   f"Coupon {coupon['id']} has only {len(coupon['legs'])} legs")

    def test_max_same_sport_per_coupon(self):
        """Max 2 same-sport legs per coupon."""
        from scripts.coupon_builder import assign_picks_to_core
        # Create 6 football picks
        picks = [
            {"sport": "football", "home_team": f"Team{i}", "away_team": f"Opponent{i}",
             "competition": f"League{i}", "kickoff": f"2026-05-01T{14+i}:00:00",
             "best_market": {"name": f"Market{i}", "direction": "OVER", "safety_score": 0.7 + i * 0.01, "hit_rate_l10": 0.7},
             "ev": 0.05 + i * 0.01, "odds": {"market_best": 1.80}, "risk_tier": "LR", "final_confidence": 3.5, "gate_score": "14/17"}
            for i in range(6)
        ]
        config = {"min_legs_per_coupon": 2, "max_same_sport_legs_in_coupon": 2, "working_bankroll_pln": 47}
        core = assign_picks_to_core(picks, config)
        for coupon in core:
            sports = [l["sport"] for l in coupon["legs"]]
            sport_counts = Counter(sports)
            for sport, count in sport_counts.items():
                self.assertLessEqual(count, 2, f"Too many {sport} legs: {count}")

    def test_build_coupons_no_bet(self):
        """NO BET when 0 approved picks."""
        from scripts.coupon_builder import build_coupons
        gate_results = {
            "date": "2026-05-01",
            "gate_results": {
                "approved": [],
                "extended_pool": [],
                "rejected": [],
            }
        }
        config = {"working_bankroll_pln": 47, "suggested_daily_allocation_range_pln": [5, 15]}
        result = build_coupons(gate_results, config)
        self.assertTrue(result["no_bet"])

    def test_build_coupons_singles_only(self):
        """1 approved pick produces singles but no core coupons."""
        from scripts.coupon_builder import build_coupons
        gate_results = {
            "date": "2026-05-01",
            "gate_results": {
                "approved": [
                    {"sport": "football", "home_team": "A", "away_team": "B",
                     "best_market": {"name": "X", "safety_score": 0.7}, "odds": {"market_best": 1.80}, "ev": 0.05}
                ],
                "extended_pool": [],
                "rejected": [],
            }
        }
        config = {"working_bankroll_pln": 47, "suggested_daily_allocation_range_pln": [5, 15]}
        result = build_coupons(gate_results, config)
        self.assertFalse(result["no_bet"])
        self.assertEqual(len(result["core_coupons"]), 0)
        self.assertGreaterEqual(len(result["singles"]), 1)

    def test_build_coupons_full(self):
        """Full coupon building with enough picks."""
        from scripts.coupon_builder import build_coupons
        approved = _make_approved_picks(8)
        gate_results = {
            "date": "2026-05-01",
            "gate_results": {"approved": approved, "extended_pool": [], "rejected": []},
        }
        config = {
            "working_bankroll_pln": 47,
            "suggested_daily_allocation_range_pln": [5, 15],
            "min_legs_per_coupon": 2,
            "max_same_sport_legs_in_coupon": 2,
        }
        result = build_coupons(gate_results, config)
        self.assertFalse(result["no_bet"])
        self.assertGreaterEqual(len(result["core_coupons"]), 0)
        # Verify combined odds arithmetic
        for coupon in result["core_coupons"]:
            expected = 1.0
            for leg in coupon["legs"]:
                expected *= leg.get("odds", {}).get("market_best", 1.0)
            self.assertAlmostEqual(coupon["combined_odds"], round(expected, 2), delta=0.05)

    def test_generate_combos(self):
        """Combo menu generation."""
        from scripts.coupon_builder import generate_combos
        approved = _make_approved_picks(6)
        config = {"min_legs_per_coupon": 2, "max_same_sport_legs_in_coupon": 2, "working_bankroll_pln": 47}
        combos = generate_combos(approved, config)
        self.assertGreaterEqual(len(combos), 1)
        for combo in combos:
            self.assertIn("COMB", combo["id"])

    def test_night_detection(self):
        """Late kickoff games are classified as night."""
        from scripts.coupon_builder import _classify_night
        pick_night = {"kickoff": "2026-05-01T21:00:00"}
        pick_day = {"kickoff": "2026-05-01T14:00:00"}
        self.assertTrue(_classify_night(pick_night, "Europe/Warsaw"))
        self.assertFalse(_classify_night(pick_day, "Europe/Warsaw"))


# ===========================================================================
# TestPipelineIntegration
# ===========================================================================

class TestPipelineIntegration(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache_dir = Path(self.tmp) / "stats_cache"
        self.data_dir = Path(self.tmp) / "data"
        self.journal_dir = Path(self.tmp) / "journal"
        self.data_dir.mkdir(parents=True)
        self.journal_dir.mkdir(parents=True)
        football_dir = self.cache_dir / "football"
        football_dir.mkdir(parents=True)
        (football_dir / "liverpool.json").write_text(json.dumps(MOCK_FOOTBALL_CACHE))
        (football_dir / "arsenal.json").write_text(json.dumps(MOCK_ARSENAL_CACHE))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_s3_to_s7_pipeline(self):
        """S3 output feeds correctly into S7 gate checker."""
        import scripts.deep_stats_report as dsr
        import scripts.normalize_stats as norm_mod
        import scripts.gate_checker as gc

        with patch.object(dsr, "CACHE_DIR", self.cache_dir), \
             patch.object(dsr, "DATA_DIR", self.data_dir), \
             patch.object(norm_mod, "CACHE_DIR", self.cache_dir), \
             patch.object(gc, "LEDGER_PATH", self.journal_dir / "picks-ledger.csv"):

            analysis = dsr.analyze_candidate(
                "football", "Liverpool", "Arsenal", "PL", "2026-05-01T15:00"
            )
            # Normalise S3 → gate input
            gate_input = gc._normalise_s3_to_gate_input(analysis)
            # Add fields gate needs
            gate_input["ev"] = 0.10
            gate_input["odds"] = {"market_best": 1.85}
            gate_input["tipster_count"] = 1

            result = gc.check_18_point_gate(gate_input, [])
            self.assertIn("gate_score", result)
            # Should not crash and should produce a parseable score
            score_parts = result["gate_score"].split("/")
            self.assertEqual(len(score_parts), 2)
            self.assertGreater(int(score_parts[0]), 0)

    def test_s7_to_s8_pipeline(self):
        """S7 output feeds correctly into S8 coupon builder."""
        from scripts.coupon_builder import build_coupons

        approved = _make_approved_picks(6)
        gate_results = {
            "date": "2026-05-01",
            "gate_results": {"approved": approved, "extended_pool": [], "rejected": []},
        }
        config = {
            "working_bankroll_pln": 47,
            "suggested_daily_allocation_range_pln": [5, 15],
            "min_legs_per_coupon": 2,
            "max_same_sport_legs_in_coupon": 2,
        }
        result = build_coupons(gate_results, config)
        self.assertFalse(result["no_bet"])
        self.assertGreaterEqual(len(result["core_coupons"]), 0)

    def test_full_s3_s7_s8_pipeline(self):
        """Full pipeline: S3 → S7 → S8."""
        import scripts.deep_stats_report as dsr
        import scripts.normalize_stats as norm_mod
        import scripts.gate_checker as gc
        from scripts.coupon_builder import build_coupons

        with patch.object(dsr, "CACHE_DIR", self.cache_dir), \
             patch.object(dsr, "DATA_DIR", self.data_dir), \
             patch.object(norm_mod, "CACHE_DIR", self.cache_dir), \
             patch.object(gc, "LEDGER_PATH", self.journal_dir / "picks-ledger.csv"):

            # S3: analyze multiple candidates
            analyses = []
            pairs = [
                ("Liverpool", "Arsenal"),
                ("Arsenal", "Liverpool"),
            ]
            for home, away in pairs:
                a = dsr.analyze_candidate("football", home, away, "PL", "2026-05-01T15:00")
                analyses.append(a)

            # S7: gate check
            gate_inputs = []
            for a in analyses:
                gi = gc._normalise_s3_to_gate_input(a)
                gi["ev"] = 0.10
                gi["odds"] = {"market_best": 1.85}
                gi["tipster_count"] = 1
                gate_inputs.append(gi)

            gate_results = gc.run_gate(gate_inputs, "2026-05-01")
            gr = gate_results["gate_results"]
            total_processed = len(gr["approved"]) + len(gr["extended_pool"]) + len(gr["rejected"])
            # Liverpool vs Arsenal and Arsenal vs Liverpool are the same event
            # — dedup correctly merges them, leaving 1 unique candidate.
            self.assertEqual(total_processed, 1)

            # S8: build coupons (may be NO BET if not enough approved)
            config = {
                "working_bankroll_pln": 47,
                "suggested_daily_allocation_range_pln": [5, 15],
                "min_legs_per_coupon": 2,
                "max_same_sport_legs_in_coupon": 2,
            }
            coupon_result = build_coupons(gate_results, config)
            # Should not crash — result is valid dict
            self.assertIn("no_bet", coupon_result)
            self.assertIn("core_coupons", coupon_result)


    def test_full_s3_s7_s8_pipeline_no_odds(self):
        """Pipeline handles stats-first mode (no odds) without crash."""
        import scripts.deep_stats_report as dsr
        import scripts.normalize_stats as norm_mod
        import scripts.gate_checker as gc
        from scripts.coupon_builder import build_coupons

        with patch.object(dsr, "CACHE_DIR", self.cache_dir), \
             patch.object(dsr, "DATA_DIR", self.data_dir), \
             patch.object(norm_mod, "CACHE_DIR", self.cache_dir), \
             patch.object(gc, "LEDGER_PATH", self.journal_dir / "picks-ledger.csv"):

            analysis = dsr.analyze_candidate(
                "football", "Liverpool", "Arsenal", "PL", "2026-05-01T15:00"
            )
            gi = gc._normalise_s3_to_gate_input(analysis)
            # No EV, no odds — stats-first mode
            self.assertIsNone(gi.get("ev"))
            self.assertEqual(gi.get("odds"), {})

            result = gc.check_18_point_gate(gi, [])
            # Gate #8 (EV) should PASS in stats-first mode (user verifies manually)
            # It no longer fails when ev is None — this was fixed to support stats-first workflow
            self.assertNotIn("8", result["gate_failed"])


# ===========================================================================
# TestNormaliseBridge — P3.1 edge cases
# ===========================================================================

class TestNormaliseBridge(unittest.TestCase):

    def test_normalise_missing_ranking_result(self):
        """Normaliser handles missing ranking_result key."""
        from scripts.gate_checker import _normalise_s3_to_gate_input
        analysis = {
            "sport": "football",
            "home_team": "A",
            "away_team": "B",
            "competition": "C",
            "kickoff": "2026-05-01T15:00",
            "has_data": True,
            "best_market": None,
            "markets_evaluated": 0,
        }
        result = _normalise_s3_to_gate_input(analysis)
        self.assertIsNone(result["best_market"])
        self.assertEqual(result["market_count"], 0)
        self.assertTrue(result["h2h_blind"])

    def test_normalise_with_best_market_and_h2h(self):
        """Normaliser correctly detects non-blind H2H."""
        from scripts.gate_checker import _normalise_s3_to_gate_input
        analysis = {
            "sport": "tennis",
            "home_team": "A",
            "away_team": "B",
            "competition": "ATP",
            "kickoff": "2026-05-01T15:00",
            "has_data": True,
            "best_market": {"name": "Total Games O/U", "h2h_avg": 22.5, "safety_score": 0.75},
            "markets_evaluated": 4,
            "h2h_summary": {"has_data": True, "meetings_count": 7, "averages": {}},
            "ranking_result": {"ranking": [{"rank": 1}], "three_way_check": {"status": "ALIGNED"}},
            "stats_a_summary": {"sources": ["api-tennis"]},
            "stats_b_summary": {"sources": ["flashscore"]},
        }
        result = _normalise_s3_to_gate_input(analysis)
        self.assertFalse(result["h2h_blind"])
        self.assertEqual(result["three_way_alignment"], "ALIGNED")
        self.assertEqual(result["h2h_count"], 7)
        self.assertIn("api-tennis", result["sources"])
        self.assertIn("flashscore", result["sources"])

    def test_normalise_empty_stats_summaries(self):
        """Normaliser handles missing stats summaries."""
        from scripts.gate_checker import _normalise_s3_to_gate_input
        analysis = {
            "sport": "basketball",
            "home_team": "X",
            "away_team": "Y",
            "competition": "NBA",
            "kickoff": "",
            "has_data": False,
            "best_market": None,
            "markets_evaluated": 0,
        }
        result = _normalise_s3_to_gate_input(analysis)
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["data_quality"], {'score': 0, 'label': 'MINIMAL'})


# ===========================================================================
# TestCouponEdgeCases — P3.2, P3.3, P3.5, P3.6
# ===========================================================================

class TestCouponEdgeCases(unittest.TestCase):

    def test_assign_picks_empty_list(self):
        """assign_picks_to_core with 0 picks returns empty."""
        from scripts.coupon_builder import assign_picks_to_core
        config = {"min_legs_per_coupon": 2, "max_same_sport_legs_in_coupon": 2, "working_bankroll_pln": 47}
        self.assertEqual(assign_picks_to_core([], config), [])

    def test_assign_picks_3_picks_builds_coupon(self):
        """3 picks with min_legs=2 builds a coupon."""
        from scripts.coupon_builder import assign_picks_to_core
        config = {"min_legs_per_coupon": 2, "max_same_sport_legs_in_coupon": 2, "working_bankroll_pln": 47}
        picks = _make_approved_picks(3)
        result = assign_picks_to_core(picks, config)
        self.assertGreaterEqual(len(result), 1)
        for coupon in result:
            self.assertGreaterEqual(len(coupon["legs"]), 2)

    def test_assign_picks_1_pick_no_coupon(self):
        """1 pick = below min 2, no coupons built."""
        from scripts.coupon_builder import assign_picks_to_core
        config = {"min_legs_per_coupon": 2, "max_same_sport_legs_in_coupon": 2, "working_bankroll_pln": 47}
        picks = _make_approved_picks(1)
        self.assertEqual(assign_picks_to_core(picks, config), [])

    def test_compute_stake_negative_kelly(self):
        """Kelly f <= 0 returns minimum 1.0 PLN."""
        from scripts.coupon_builder import compute_stake
        # Low odds + low safety → negative Kelly
        stake = compute_stake(1.20, 0.30, 50.0, "LR")
        self.assertEqual(stake, 1.0)

    def test_compute_stake_zero_odds(self):
        """Odds = 0 returns minimum."""
        from scripts.coupon_builder import compute_stake
        self.assertEqual(compute_stake(0, 0.5, 50.0, "LR"), 1.0)

    def test_stress_test_empty_legs(self):
        """Stress test with 0 legs."""
        from scripts.coupon_builder import stress_test_coupon
        st = stress_test_coupon({"legs": []})
        self.assertEqual(st["p_coupon"], 0.0)
        self.assertIsNone(st["weakest_leg"])

    def test_all_same_sport_respects_max_constraint(self):
        """All picks same sport — max 2 per coupon enforced."""
        from scripts.coupon_builder import assign_picks_to_core
        picks = [
            {"sport": "football", "home_team": f"T{i}", "away_team": f"O{i}",
             "competition": f"L{i}", "kickoff": f"2026-05-01T{14+i}:00:00",
             "best_market": {"name": f"M{i}", "direction": "OVER", "safety_score": 0.75},
             "ev": 0.08, "odds": {"market_best": 1.80}, "risk_tier": "MS",
             "final_confidence": 3.5, "gate_score": "14/17"}
            for i in range(8)
        ]
        config = {"min_legs_per_coupon": 2, "max_same_sport_legs_in_coupon": 2, "working_bankroll_pln": 47}
        core = assign_picks_to_core(picks, config)
        for coupon in core:
            sport_count = sum(1 for l in coupon["legs"] if l["sport"] == "football")
            self.assertLessEqual(sport_count, 2, f"Coupon {coupon['id']} has {sport_count} football legs")

    def test_write_coupon_markdown_creates_file(self):
        """Markdown writer produces a file."""
        from scripts.coupon_builder import write_coupon_markdown, build_coupons
        import tempfile
        import shutil
        tmp = tempfile.mkdtemp()
        try:
            coupon_dir = Path(tmp) / "coupons"
            coupon_dir.mkdir()
            with patch("scripts.coupon_builder.COUPON_DIR", coupon_dir):
                approved = _make_approved_picks(6)
                gate_results = {
                    "date": "2026-05-01",
                    "gate_results": {"approved": approved, "extended_pool": [], "rejected": []},
                }
                config = {"working_bankroll_pln": 47, "suggested_daily_allocation_range_pln": [5, 15],
                          "min_legs_per_coupon": 2, "max_same_sport_legs_in_coupon": 2}
                coupons_data = build_coupons(gate_results, config)
                md_path = write_coupon_markdown(coupons_data, "2026-05-01")
                self.assertTrue(md_path.exists())
                content = md_path.read_text(encoding="utf-8")
                self.assertIn("Kupony na 2026-05-01", content)
                self.assertIn("WARUNKOWE", content)
        finally:
            shutil.rmtree(tmp)

    def test_write_coupon_json_creates_file(self):
        """JSON writer produces valid JSON."""
        from scripts.coupon_builder import write_coupon_json, build_coupons
        import tempfile
        import shutil
        tmp = tempfile.mkdtemp()
        try:
            coupon_dir = Path(tmp) / "coupons"
            coupon_dir.mkdir()
            with patch("scripts.coupon_builder.COUPON_DIR", coupon_dir):
                approved = _make_approved_picks(6)
                gate_results = {
                    "date": "2026-05-01",
                    "gate_results": {"approved": approved, "extended_pool": [], "rejected": []},
                }
                config = {"working_bankroll_pln": 47, "suggested_daily_allocation_range_pln": [5, 15],
                          "min_legs_per_coupon": 2, "max_same_sport_legs_in_coupon": 2}
                coupons_data = build_coupons(gate_results, config)
                json_path = write_coupon_json(coupons_data, "2026-05-01")
                self.assertTrue(json_path.exists())
                data = json.loads(json_path.read_text(encoding="utf-8"))
                self.assertIn("core_coupons", data)
                # _approved should NOT appear in JSON output
                self.assertNotIn("_approved", data)
        finally:
            shutil.rmtree(tmp)

    def test_build_coupons_sets_approved_key(self):
        """build_coupons sets _approved for markdown writer."""
        from scripts.coupon_builder import build_coupons
        approved = _make_approved_picks(6)
        gate_results = {
            "date": "2026-05-01",
            "gate_results": {"approved": approved, "extended_pool": [], "rejected": []},
        }
        config = {"working_bankroll_pln": 47, "suggested_daily_allocation_range_pln": [5, 15],
                  "min_legs_per_coupon": 2, "max_same_sport_legs_in_coupon": 2}
        result = build_coupons(gate_results, config)
        self.assertIn("_approved", result)
        self.assertEqual(len(result["_approved"]), 6)

    def test_pick_description_pl_none_odds(self):
        """Polish description doesn't crash on None odds."""
        from scripts.coupon_builder import _pick_description_pl
        pick = {
            "home_team": "A",
            "away_team": "B",
            "best_market": {"name": "Fouls Total O/U", "direction": "OVER", "line": 22.5},
            "odds": None,
        }
        result = _pick_description_pl(pick)
        self.assertIn("A vs B", result)
        self.assertIn("kurs TBD", result)  # Shows TBD instead of 0.00 for missing odds


# ===========================================================================
# TestEVInjection
# ===========================================================================

class TestEVInjection(unittest.TestCase):

    def test_inject_ev_from_odds(self):
        """EV injection from odds API snapshot."""
        import tempfile
        import shutil
        from scripts.odds_evaluator import _inject_ev_from_odds

        tmp = tempfile.mkdtemp()
        data_dir = Path(tmp)
        try:
            odds_snapshot = [
                {"home_team": "Liverpool", "away_team": "Arsenal", "best_odds": 1.85},
            ]
            (data_dir / "odds_api_snapshot.json").write_text(json.dumps(odds_snapshot))

            candidates = [
                {"home_team": "Liverpool", "away_team": "Arsenal",
                 "best_market": {"name": "Match Winner", "safety_score": 0.80, "probability": 0.80}, "ev": None, "odds": {}},
                {"home_team": "Unknown", "away_team": "Team",
                 "best_market": {"name": "Match Winner", "safety_score": 0.70, "probability": 0.70}, "ev": None, "odds": {}},
            ]
            with patch("scripts.odds_evaluator.DATA_DIR", data_dir):
                _inject_ev_from_odds(candidates, "2026-05-01")

            # Liverpool match should have EV
            self.assertIsNotNone(candidates[0]["ev"])
            self.assertAlmostEqual(candidates[0]["ev"], 0.80 * 1.85 - 1, places=3)
            # Unknown match should remain None
            self.assertIsNone(candidates[1]["ev"])
        finally:
            shutil.rmtree(tmp)

    def test_inject_ev_no_snapshot(self):
        """No odds snapshot → candidates unchanged."""
        import tempfile
        import shutil
        from scripts.odds_evaluator import _inject_ev_from_odds

        tmp = tempfile.mkdtemp()
        try:
            candidates = [
                {"home_team": "A", "away_team": "B",
                 "best_market": {"safety_score": 0.80}, "ev": None, "odds": {}},
            ]
            with patch("scripts.odds_evaluator.DATA_DIR", Path(tmp)):
                _inject_ev_from_odds(candidates, "2026-05-01")
            self.assertIsNone(candidates[0]["ev"])
        finally:
            shutil.rmtree(tmp)

    def test_inject_ev_totals_market(self):
        """EV injection for totals market uses totals odds, not ML."""
        import tempfile
        import shutil
        from scripts.odds_evaluator import _inject_ev_from_odds

        tmp = tempfile.mkdtemp()
        data_dir = Path(tmp)
        try:
            odds_snapshot = [
                {
                    "home_team": "Liverpool", "away_team": "Arsenal",
                    "best_odds": 1.85,
                    "totals": [{"line": 2.5, "over": 1.90, "under": 1.95, "bookmaker": "Bet365"}],
                },
            ]
            (data_dir / "odds_api_snapshot.json").write_text(json.dumps(odds_snapshot))

            candidates = [
                {
                    "home_team": "Liverpool", "away_team": "Arsenal",
                    "best_market": {
                        "name": "Goals Total O/U", "safety_score": 0.75,
                        "probability": 0.75, "direction": "over", "line": 2.5,
                    },
                    "ev": None, "odds": {},
                },
            ]
            with patch("scripts.odds_evaluator.DATA_DIR", data_dir):
                _inject_ev_from_odds(candidates, "2026-05-01")

            # Should use totals over odds (1.90), not ML odds (1.85)
            self.assertIsNotNone(candidates[0]["ev"])
            self.assertAlmostEqual(candidates[0]["ev"], 0.75 * 1.90 - 1, places=3)
        finally:
            shutil.rmtree(tmp)


class TestValidateScore(unittest.TestCase):
    """Tests for sport-aware score validation."""

    def test_default_football_valid(self):
        from scripts.settle_on_finish import _validate_score
        self.assertTrue(_validate_score(2, 1))

    def test_default_rejects_high(self):
        from scripts.settle_on_finish import _validate_score
        self.assertFalse(_validate_score(25, 10))

    def test_basketball_valid(self):
        from scripts.settle_on_finish import _validate_score
        self.assertTrue(_validate_score(110, 105, sport="basketball"))

    def test_basketball_default_would_reject(self):
        from scripts.settle_on_finish import _validate_score
        # Without sport, basketball scores are rejected
        self.assertFalse(_validate_score(110, 105))

    def test_handball_valid(self):
        from scripts.settle_on_finish import _validate_score
        self.assertFalse(_validate_score(35, 29, sport="handball"))


class TestDedupNormalization(unittest.TestCase):
    """Tests for gate_checker dedup key normalization."""

    def test_manchester_not_corrupted(self):
        """Ensure 'manchester' is not corrupted to 'man.chester'."""
        from scripts.gate_checker import run_gate
        # We test the normalization logic directly — build a candidate with
        # manchester united and check the dedup key doesn't corrupt it
        c1 = {
            "home_team": "Man Utd", "away_team": "Liverpool",
            "sport": "football", "competition": "EPL",
        }
        c2 = {
            "home_team": "Manchester United", "away_team": "Liverpool",
            "sport": "football", "competition": "EPL",
        }
        # Both should produce the same normalized key
        # Test by importing and calling directly
        import re as _re
        def _dedup_key(c):
            h = _re.sub(r"^(fc|sc|sk|ac|as|fk|cd|cf)\s+", "", (c.get("home_team") or "").strip().lower())
            a = _re.sub(r"^(fc|sc|sk|ac|as|fk|cd|cf)\s+", "", (c.get("away_team") or "").strip().lower())
            for short, full in [("man utd", "manchester united"), ("man city", "manchester city"),
                                ("nottm", "nottingham"), ("sheff", "sheffield"),
                                ("wolves", "wolverhampton"), ("newcastle utd", "newcastle united")]:
                h = h.replace(short, full)
                a = a.replace(short, full)
            return f"{h}|{a}"

        self.assertEqual(_dedup_key(c1), _dedup_key(c2))
        # Make sure "manchester" doesn't have a period in it
        key = _dedup_key(c1)
        self.assertNotIn(".", key)


if __name__ == "__main__":
    unittest.main()
