"""Tests for odds evaluator (extracted from orchestrator)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import db_data_loader
from db_data_loader import load_s3_candidates_with_parity
from odds_evaluator import _convert_espn_odds_to_decimal, run_odds_eval


# ---------------------------------------------------------------------------
# American odds → decimal conversion
# ---------------------------------------------------------------------------


def test_convert_positive_american_odds():
    """+150 → 2.50."""
    result = _convert_espn_odds_to_decimal({
        "moneyline": {"home": "+150"},
    })
    assert result["moneyline"]["home"] == 2.5


def test_convert_negative_american_odds():
    """-200 → 1.50."""
    result = _convert_espn_odds_to_decimal({
        "moneyline": {"home": "-200"},
    })
    assert result["moneyline"]["home"] == 1.5


def test_convert_espn_moneyline():
    """Full moneyline dict with home/away/draw."""
    result = _convert_espn_odds_to_decimal({
        "moneyline": {"home": "-150", "away": "+130", "draw": "+250"},
    })
    ml = result["moneyline"]
    assert "home" in ml
    assert "away" in ml
    assert "draw" in ml
    # -150 → 1 + 100/150 = 1.667
    assert abs(ml["home"] - 1.667) < 0.01
    # +130 → 1 + 130/100 = 2.30
    assert ml["away"] == 2.3
    # +250 → 1 + 250/100 = 3.50
    assert ml["draw"] == 3.5


def test_convert_espn_total():
    """Total with over/under."""
    result = _convert_espn_odds_to_decimal({
        "total": {"line": "2.5", "over_odds": "-110", "under_odds": "+100"},
    })
    total = result["total"]
    assert total["line"] == "2.5"
    # -110 → 1 + 100/110 ≈ 1.909
    assert abs(total["over"] - 1.909) < 0.01
    # +100 → 1 + 100/100 = 2.0
    assert total["under"] == 2.0


def test_convert_espn_spread():
    """Spread with home/away."""
    result = _convert_espn_odds_to_decimal({
        "spread": {
            "home_line": "-3.5", "away_line": "+3.5",
            "home_odds": "-110", "away_odds": "-110",
        },
    })
    spread = result["spread"]
    assert spread["home_line"] == "-3.5"
    assert spread["away_line"] == "+3.5"
    # -110 → 1 + 100/110 ≈ 1.909
    assert abs(spread["home"] - 1.909) < 0.01
    assert abs(spread["away"] - 1.909) < 0.01


def _candidate(home: str, away: str, *, fixture_id: int | None = None, ev=None) -> dict:
    candidate = {
        "sport": "football",
        "home_team": home,
        "away_team": away,
        "kickoff": "2099-01-01T12:00:00",
        "ranking": [{"name": "Corners", "safety_score": 0.7}],
        "context_flags": [],
    }
    if fixture_id is not None:
        candidate["fixture_id"] = fixture_id
    if ev is not None:
        candidate["ev"] = ev
    return candidate


def test_load_s3_candidates_with_parity_exact_overlay(monkeypatch):
    json_candidates = [
        _candidate("Alpha", "Beta", fixture_id=1),
        _candidate("Gamma", "Delta", fixture_id=2),
    ]
    db_candidates = [
        _candidate("Alpha", "Beta", fixture_id=1, ev=0.12),
        _candidate("Gamma", "Delta", fixture_id=2, ev=0.08),
    ]

    monkeypatch.setattr(db_data_loader, "_load_analysis_results_raw_from_db", lambda _: db_candidates)
    monkeypatch.setattr(db_data_loader, "_load_analysis_results_raw_from_json", lambda _: json_candidates)

    candidates, metadata = load_s3_candidates_with_parity("2099-01-01")

    assert len(candidates) == 2
    assert metadata["source"] == "json_with_db_overlay"
    assert metadata["parity"]["status"] == "exact"
    assert candidates[0]["ev"] == 0.12
    assert candidates[1]["ev"] == 0.08


def test_load_s3_candidates_with_parity_preserves_json_universe_on_partial_db(monkeypatch):
    json_candidates = [
        _candidate("Alpha", "Beta", fixture_id=1),
        _candidate("Gamma", "Delta", fixture_id=2),
        _candidate("Eta", "Theta", fixture_id=3),
    ]
    db_candidates = [
        _candidate("Alpha", "Beta", fixture_id=1, ev=0.12),
        _candidate("Gamma", "Delta", fixture_id=2, ev=0.08),
    ]

    monkeypatch.setattr(db_data_loader, "_load_analysis_results_raw_from_db", lambda _: db_candidates)
    monkeypatch.setattr(db_data_loader, "_load_analysis_results_raw_from_json", lambda _: json_candidates)

    candidates, metadata = load_s3_candidates_with_parity("2099-01-01")

    assert len(candidates) == 3
    assert metadata["parity"]["status"] == "db_subset_of_json"
    assert metadata["parity"]["json_only_candidates"] == 1
    assert candidates[2]["home_team"] == "Eta"
    assert "ev" not in candidates[2]


def test_load_s3_candidates_with_parity_uses_json_when_db_empty(monkeypatch):
    json_candidates = [_candidate("Alpha", "Beta", fixture_id=1)]

    monkeypatch.setattr(db_data_loader, "_load_analysis_results_raw_from_db", lambda _: [])
    monkeypatch.setattr(db_data_loader, "_load_analysis_results_raw_from_json", lambda _: json_candidates)

    candidates, metadata = load_s3_candidates_with_parity("2099-01-01")

    assert len(candidates) == 1
    assert metadata["source"] == "json"
    assert metadata["parity"]["status"] == "json_only"


def test_build_analysis_index_keeps_unkeyed_entries_distinct():
    index, stats = db_data_loader._build_analysis_index([
        {"ranking": [{"name": "Corners"}]},
        {"ranking": [{"name": "Shots"}]},
    ])

    assert list(index.keys()) == ["unkeyed:0", "unkeyed:1"]
    assert stats == {
        "input_count": 2,
        "unique_count": 2,
        "duplicate_count": 0,
    }


def test_run_odds_eval_preserves_json_candidate_universe_on_partial_db(monkeypatch, tmp_path):
    date = "2099-01-01"
    s3_path = tmp_path / f"{date}_s3_deep_stats.json"
    s3_path.write_text(
        json.dumps(
            {
                "analyses": [
                    _candidate("Alpha", "Beta", fixture_id=1),
                    _candidate("Gamma", "Delta", fixture_id=2),
                    _candidate("Eta", "Theta", fixture_id=3),
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(db_data_loader, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        db_data_loader,
        "_load_analysis_results_raw_from_db",
        lambda _: [
            _candidate("Alpha", "Beta", fixture_id=1, ev=0.12),
            _candidate("Gamma", "Delta", fixture_id=2, ev=0.08),
        ],
    )

    def _inject_test_ev(candidates, _date):
        for candidate in candidates:
            candidate["ev"] = 0.05
            candidate["ev_source"] = "test"
            candidate["odds"] = {"market_best": 2.0}

    monkeypatch.setattr("odds_evaluator.DATA_DIR", tmp_path)
    monkeypatch.setattr("odds_evaluator._inject_ev_from_odds", _inject_test_ev)

    success, summary = run_odds_eval(date, {})

    assert success is True
    assert "3 with EV data" in summary
    saved = json.loads(s3_path.read_text(encoding="utf-8"))
    assert len(saved["analyses"]) == 3
    assert all(candidate.get("ev") == 0.05 for candidate in saved["analyses"])
