import json
import os
import pytest

from bet.sofa.coverage import check_coverage_floor

def create_run_data(base_dir: str, date: str, football_ready: int, tennis_ready: int) -> None:
    run_dir = os.path.join(base_dir, date)
    os.makedirs(run_dir, exist_ok=True)
    
    fixtures = []
    samples = []
    
    # Football
    for i in range(football_ready):
        fid = 1000 + i
        fixtures.append({"sofascore_event_id": fid, "sport": "football"})
        samples.append({"sofascore_event_id": fid, "readiness": "READY"})
        
    # Tennis
    for i in range(tennis_ready):
        fid = 2000 + i
        fixtures.append({"sofascore_event_id": fid, "sport": "tennis"})
        samples.append({"sofascore_event_id": fid, "readiness": "READY"})
        
    with open(os.path.join(run_dir, "02_fixtures.json"), "w") as f:
        json.dump(fixtures, f)
        
    with open(os.path.join(run_dir, "03_samples.json"), "w") as f:
        json.dump(samples, f)


def test_coverage_floor_drop(tmp_path):
    runs_dir = str(tmp_path / "runs")
    
    # 5 days of normal history (median ~ 100 football, 50 tennis)
    create_run_data(runs_dir, "2026-09-10", 100, 50)
    create_run_data(runs_dir, "2026-09-11", 110, 48)
    create_run_data(runs_dir, "2026-09-12", 90, 52)
    create_run_data(runs_dir, "2026-09-13", 105, 50)
    create_run_data(runs_dir, "2026-09-14", 95, 49)
    
    # Today: football drops to 40 (>40% drop), tennis stays at 45
    create_run_data(runs_dir, "2026-09-15", 40, 45)
    
    warnings = check_coverage_floor(runs_dir, "2026-09-15")
    assert "football" in warnings
    assert "tennis" not in warnings
    assert "dropped by >40%" in warnings["football"]

def test_coverage_floor_no_drop(tmp_path):
    runs_dir = str(tmp_path / "runs")
    
    create_run_data(runs_dir, "2026-09-10", 100, 50)
    create_run_data(runs_dir, "2026-09-11", 100, 50)
    create_run_data(runs_dir, "2026-09-12", 100, 50)
    
    create_run_data(runs_dir, "2026-09-13", 80, 50) # 20% drop, not 40%
    
    warnings = check_coverage_floor(runs_dir, "2026-09-13")
    assert not warnings
