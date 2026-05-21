from pathlib import Path
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import db_report


def test_db_report_rich_coverage_surfaces_shortlist_bucket_assignments(monkeypatch, capsys):
    required_keys = db_report.RICH_COMPLETION_POLICY["basketball"]["required_rich_keys"]
    rows_by_team = {
        "Lakers": [(key, "api-basketball") for key in required_keys],
        "Celtics": [("points", "league-profile-baseline")],
        "Knicks": [("rebounds", "api-basketball")],
        "Bulls": [],
    }

    class FakeConn:
        def execute(self, query, params=None):
            if "SELECT id FROM sports" in query:
                return SimpleNamespace(fetchone=lambda: (1,))
            if "JOIN teams t ON t.id IN (f.home_team_id, f.away_team_id)" in query:
                return SimpleNamespace(fetchall=lambda: [(1, "Lakers"), (2, "Celtics"), (3, "Knicks"), (4, "Bulls")])
            if "FROM team_form WHERE team_name = ? AND sport_id = ?" in query:
                team_name = params[0]
                return SimpleNamespace(fetchall=lambda: rows_by_team[team_name])
            if "FROM team_form WHERE team_id = ? AND sport_id = ?" in query:
                team_id = params[0]
                team_name = {
                    1: "Lakers",
                    2: "Celtics",
                    3: "Knicks",
                    4: "Bulls",
                }[team_id]
                return SimpleNamespace(fetchall=lambda: rows_by_team[team_name])
            raise AssertionError(f"Unexpected query: {query}")

    class FakeDB:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(db_report, "get_db", lambda: FakeDB())
    monkeypatch.setattr(
        db_report,
        "_load_shortlist_teams_by_sport",
        lambda betting_date: {"basketball": ["Lakers", "Celtics", "Knicks", "Bulls"]},
    )

    db_report.report_rich_coverage("2026-05-21", "basketball")
    output = capsys.readouterr().out

    assert "Shortlist scope:" in output
    assert "teams: 4" in output
    assert "Shortlist bucket assignments:" in output
    assert "rich          : Lakers" in output
    assert "baseline only : Celtics" in output
    assert "partial       : Knicks" in output
    assert "no data       : Bulls" in output
    assert "Still-missing shortlist teams:" in output
    assert "[baseline_only] Celtics" in output
    assert "[partial] Knicks" in output
    assert "[no_data] Bulls" in output