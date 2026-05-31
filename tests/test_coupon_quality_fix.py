"""Tests for coupon quality fixes (pipeline-coupon-quality-fix.plan.md).

Covers:
- Task 1.1: Negative EV hard rejection
- Task 1.2: Safety floor filter
- Task 1.3: MS sport diversity enforcement
- Task 1.4: Non-discountable gates + pipeline warnings
- Task 2.2: Extended pool empty entry filtering
- Task 3.1: Hit% fraction parsing
"""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Task 1.1: Negative EV hard reject in gate_checker
# ---------------------------------------------------------------------------

class TestNegativeEVHardReject:
    """Gate checker must hard-reject picks with EV < 0."""

    def _make_candidate(self, ev: float, safety: float = 0.5):
        return {
            "home_team": "Team A",
            "away_team": "Team B",
            "sport": "football",
            "best_market": {
                "name": "total_goals_over",
                "safety_score": safety,
                "ev": ev,
                "direction": "over",
                "line": 2.5,
                "hit_rate_l10": "7/10",
                "hit_rate_l5": "4/5",
            },
            "odds": {"market_best": 1.85},
            "ev": ev,
        }

    @patch("scripts.gate_checker._build_fixture_lookup")
    def test_negative_ev_triggers_hard_reject(self, mock_lookup):
        """EV < 0 must produce hard_reject=True in run_gate output."""
        from scripts.gate_checker import run_gate

        candidate = self._make_candidate(ev=-0.05)
        mock_lookup.return_value = (set(), set())  # Skip ghost filter
        result = run_gate([candidate], "2026-05-31")

        # Should end up in rejected
        rejected = result["gate_results"]["rejected"]
        assert len(rejected) >= 1
        reject_reasons = [r.get("rejection_reason", "") for r in rejected]
        assert any("NEGATIVE_EV" in r for r in reject_reasons)

    @patch("scripts.gate_checker._build_fixture_lookup")
    def test_positive_ev_no_reject(self, mock_lookup):
        """EV >= 0 should not trigger negative-EV rejection."""
        from scripts.gate_checker import run_gate

        candidate = self._make_candidate(ev=0.05)
        mock_lookup.return_value = (set(), set())  # Skip ghost filter
        result = run_gate([candidate], "2026-05-31")

        # Should not be rejected for negative EV
        rejected = result["gate_results"]["rejected"]
        for r in rejected:
            assert "NEGATIVE_EV" not in (r.get("rejection_reason") or "")


# ---------------------------------------------------------------------------
# Task 1.2: Safety floor filter in coupon_builder
# ---------------------------------------------------------------------------

class TestSafetyFloorFilter:
    """Coupon builder must exclude picks below hard safety floor."""

    def _make_pick(self, safety: float, sport: str = "football"):
        return {
            "home_team": "Home",
            "away_team": "Away",
            "sport": sport,
            "best_market": {
                "name": "total_corners",
                "safety_score": safety,
                "ev": 0.1,
            },
            "odds": {"market_best": 1.80},
            "risk_tier": "MS",
            "advisory_tier": "MODERATE",
        }

    def test_safety_below_floor_excluded(self):
        """Picks with safety < 0.30 go to extended pool."""
        from scripts.coupon_builder import build_coupons

        gate_results = {
            "date": "2026-05-31",
            "gate_results": {
                "approved": [self._make_pick(0.09), self._make_pick(0.55)],
                "extended_pool": [],
                "rejected": [],
            },
        }
        config = {"hard_safety_floor": 0.30, "bankroll_pln": 50.0}
        result = build_coupons(gate_results, config)

        # The 0.09 pick must end up in extended_pool
        extended = result.get("extended_pool", [])
        safety_reasons = [p.get("extended_pool_reason", "") for p in extended]
        assert any("SAFETY_FLOOR" in r for r in safety_reasons)


# ---------------------------------------------------------------------------
# Task 1.3: MS sport diversity
# ---------------------------------------------------------------------------

class TestMSSportDiversity:
    """MS coupons must have max 2 legs from same sport."""

    def test_ms_coupon_relabeled_when_too_many_same_sport(self):
        """A coupon labeled MS with 3+ legs of same sport → relabeled HR."""
        from scripts.coupon_builder import assign_picks_to_core

        # Create picks: 3 football + 1 tennis
        picks = []
        for i in range(3):
            picks.append({
                "home_team": f"Football{i}",
                "away_team": f"Opponent{i}",
                "sport": "football",
                "best_market": {"name": f"market_{i}", "safety_score": 0.6, "ev": 0.05},
                "odds": {"market_best": 1.80},
                "risk_tier": "MS",
                "_is_night": False,
                "kickoff": "2026-05-31T15:00:00",
            })
        picks.append({
            "home_team": "Tennis1",
            "away_team": "Tennis2",
            "sport": "tennis",
            "best_market": {"name": "games_total", "safety_score": 0.55, "ev": 0.04},
            "odds": {"market_best": 1.90},
            "risk_tier": "MS",
            "_is_night": False,
            "kickoff": "2026-05-31T14:00:00",
        })

        config = {
            "max_same_sport_in_ms": 2,
            "max_same_sport_legs_in_coupon": 2,
            "bankroll_pln": 50.0,
            "min_legs_per_coupon": 2,
            "max_legs_per_coupon": 5,
            "max_core_coupons": 4,
        }
        coupons = assign_picks_to_core(picks, config)

        # Any coupon labeled MS should have ≤2 legs of same sport
        for c in coupons:
            if c.get("tier") == "MS":
                from collections import Counter
                sports = Counter(leg.get("sport") for leg in c.get("legs", []))
                assert all(count <= 2 for count in sports.values()), \
                    f"MS coupon has >2 same-sport legs: {dict(sports)}"


# ---------------------------------------------------------------------------
# Task 1.4: Non-discountable gates
# ---------------------------------------------------------------------------

class TestNonDiscountableGates:
    """Gates 6 and 8 must NOT be discounted by systemic discount."""

    def _make_candidates_all_failing_gate6(self, n=5):
        """Create n candidates that all fail gate 6 (no tipster data)."""
        return [{
            "home_team": f"Team Home {i}",
            "away_team": f"Team Away {i}",
            "sport": "football",
            "best_market": {"name": "total_goals_over", "safety_score": 0.5, "ev": 0.05,
                           "hit_rate_l10": "7/10", "hit_rate_l5": "4/5",
                           "direction": "over", "line": 2.5},
            "odds": {"market_best": 1.80},
            "tipster_count": 0,
        } for i in range(n)]

    @patch("scripts.gate_checker._build_fixture_lookup")
    def test_gate_6_emits_pipeline_warning(self, mock_lookup):
        """When gate 6 fails for >80% of candidates, pipeline_warnings should be set."""
        from scripts.gate_checker import run_gate

        candidates = self._make_candidates_all_failing_gate6(5)
        mock_lookup.return_value = (set(), set())  # Skip ghost filter
        result = run_gate(candidates, "2026-05-31")

        # pipeline_warnings should mention gate 6 as a pipeline prerequisite failure
        warnings = result.get("pipeline_warnings", [])
        assert any("Gate #6" in w or "PIPELINE_PREREQUISITE" in w for w in warnings), \
            f"Expected pipeline warning about gate 6, got: {warnings}"

    @patch("scripts.gate_checker._build_fixture_lookup")
    def test_pipeline_warnings_field_exists(self, mock_lookup):
        """run_gate output must always include pipeline_warnings field."""
        from scripts.gate_checker import run_gate

        candidates = [{
            "home_team": "Team A",
            "away_team": "Team B",
            "sport": "football",
            "best_market": {"name": "x", "safety_score": 0.5, "ev": 0.05,
                           "hit_rate_l10": "7/10", "hit_rate_l5": "4/5",
                           "direction": "over", "line": 2.5},
            "odds": {"market_best": 1.80},
        }]
        mock_lookup.return_value = (set(), set())  # Skip ghost filter
        result = run_gate(candidates, "2026-05-31")
        assert "pipeline_warnings" in result


# ---------------------------------------------------------------------------
# Task 3.1: Hit% fraction string parsing
# ---------------------------------------------------------------------------

class TestHitRateParsing:
    """Market matrix must handle '7/10' hit_rate_l10 strings."""

    def test_fraction_string_renders_correctly(self):
        """'7/10' should render as '7/10 (70%)'."""
        from scripts.coupon_builder import _market_matrix_rows

        approved = [{
            "home_team": "X",
            "away_team": "Y",
            "sport": "football",
            "best_market": {
                "name": "corners_total",
                "safety_score": 0.6,
                "hit_rate_l10": "7/10",
                "direction": "over",
                "line": 9.5,
            },
            "odds": {"market_best": 1.85},
        }]
        rows = _market_matrix_rows(approved, [])
        assert len(rows) >= 1
        assert "7/10" in rows[0]
        assert "70%" in rows[0]

    def test_numeric_hit_rate_renders_percent(self):
        """Numeric 0.7 should render as '70%'."""
        from scripts.coupon_builder import _market_matrix_rows

        approved = [{
            "home_team": "X",
            "away_team": "Y",
            "sport": "football",
            "best_market": {
                "name": "corners_total",
                "safety_score": 0.6,
                "hit_rate_l10": 0.7,
                "direction": "over",
                "line": 9.5,
            },
            "odds": {"market_best": 1.85},
        }]
        rows = _market_matrix_rows(approved, [])
        assert len(rows) >= 1
        assert "70%" in rows[0]


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

class TestConfigKeys:
    """betting_config.json must have new quality-fix keys."""

    @pytest.fixture
    def config(self):
        config_path = Path(__file__).resolve().parent.parent / "config" / "betting_config.json"
        return json.loads(config_path.read_text())

    def test_hard_safety_floor_exists(self, config):
        assert "hard_safety_floor" in config
        assert config["hard_safety_floor"] == 0.30

    def test_core_coupon_min_safety_exists(self, config):
        assert "core_coupon_min_safety" in config
        assert config["core_coupon_min_safety"] == 0.40

    def test_max_same_sport_in_ms_exists(self, config):
        assert "max_same_sport_in_ms" in config
        assert config["max_same_sport_in_ms"] == 2

    def test_max_same_sport_legs_reduced(self, config):
        assert config["max_same_sport_legs_in_coupon"] == 2


# ---------------------------------------------------------------------------
# Code review improvements
# ---------------------------------------------------------------------------

class TestCoreMinSafetyDemotion:
    """Picks with safety 0.30-0.39 must be demoted to HR tier, not LR/MS."""

    def test_safety_035_demoted_to_hr(self):
        """A pick with safety 0.35 should have risk_tier forced to HR."""
        from scripts.coupon_builder import build_coupons

        gate_results = {
            "date": "2026-05-31",
            "gate_results": {
                "approved": [{
                    "home_team": "DemotedTeam",
                    "away_team": "OtherTeam",
                    "sport": "football",
                    "best_market": {"name": "total_goals", "safety_score": 0.35, "ev": 0.02},
                    "odds": {"market_best": 2.10},
                    "risk_tier": "LR",
                    "advisory_tier": "MODERATE",
                }],
                "extended_pool": [],
                "rejected": [],
            },
        }
        config = {"hard_safety_floor": 0.30, "core_coupon_min_safety": 0.40, "bankroll_pln": 50.0}
        result = build_coupons(gate_results, config)

        # Pick should NOT be in extended pool (it's above hard floor)
        extended_reasons = [p.get("extended_pool_reason", "") for p in result.get("extended_pool", [])]
        assert not any("SAFETY_FLOOR" in r for r in extended_reasons)

        # If pick made it to singles/coupons, it should be HR tier
        all_picks = []
        for s in result.get("singles", []):
            all_picks.extend(s.get("legs", []))
        for c in result.get("core_coupons", []):
            all_picks.extend(c.get("legs", []))
        demoted = [p for p in all_picks if p.get("home_team") == "DemotedTeam"]
        for p in demoted:
            assert p.get("risk_tier") == "HR", f"Expected HR tier but got {p.get('risk_tier')}"


class TestEVFallbackBestMarket:
    """Gate checker should check best_market.ev when top-level ev is None."""

    @patch("scripts.gate_checker._build_fixture_lookup")
    def test_ev_from_best_market_triggers_reject(self, mock_lookup):
        """Negative EV in best_market should still trigger hard reject."""
        from scripts.gate_checker import run_gate

        candidate = {
            "home_team": "Team With Best Market EV",
            "away_team": "Opponent",
            "sport": "football",
            "best_market": {
                "name": "total_goals_over",
                "safety_score": 0.5,
                "ev": -0.08,
                "direction": "over",
                "line": 2.5,
                "hit_rate_l10": "7/10",
                "hit_rate_l5": "4/5",
            },
            "odds": {"market_best": 1.85},
            # No top-level "ev" key — only in best_market
        }
        mock_lookup.return_value = (set(), set())
        result = run_gate([candidate], "2026-05-31")

        rejected = result["gate_results"]["rejected"]
        reject_reasons = [r.get("rejection_reason", "") for r in rejected]
        assert any("NEGATIVE_EV" in r for r in reject_reasons), \
            f"Expected NEGATIVE_EV rejection from best_market.ev, got: {reject_reasons}"


class TestSingleRendering:
    """Singles should render as 'single' not '1-leg combo'."""

    def test_coupon_section_single_label(self):
        """A single bet should show 'single' in header, not 'combo'."""
        from scripts.coupon_builder import _coupon_section

        coupons = [{
            "id": "CP-20260531-LR1v1",
            "tier": "LR",
            "legs": [{"sport": "football", "home_team": "A", "away_team": "B",
                     "best_market": {"name": "corners", "safety_score": 0.6}}],
            "combined_odds": 1.85,
            "stake": 2.0,
            "potential_return": 3.70,
            "stress_test": {},
            "is_single": True,
        }]
        lines = _coupon_section("LOW-RISK", coupons)
        header_lines = [l for l in lines if "CP-20260531-LR1v1" in l]
        assert len(header_lines) >= 1
        assert "single" in header_lines[0].lower()
        assert "combo" not in header_lines[0].lower()
