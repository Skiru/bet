"""One run_id must span DISCOVER -> ENRICH -> ANALYZE.

Without it the only way to ask "what did last night's run produce" was to
correlate file mtimes, and a rerun of one step silently mixed its output with
another run's artifacts.
"""
import sqlite3

import pytest

from bet.simple_stats.analyze import analyze_dossiers
from bet.simple_stats.contracts import (
    EventDossierListV1,
    EventDossierV1,
    EventListV1,
    MetricObservation,
    ProviderValue,
)
from bet.simple_stats.enrich import enrich_events
from bet.simple_stats.run_context import new_run_id, record_pipeline_run


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "run.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE pipeline_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL, step TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            started_at TEXT, completed_at TEXT, error_message TEXT, stats TEXT,
            UNIQUE(date, step)
        )
        """
    )
    conn.commit()
    yield conn
    conn.close()


def test_run_id_is_unique_and_carries_the_date():
    first, second = new_run_id("2026-08-25"), new_run_id("2026-08-25")
    assert first != second
    assert first.startswith("simple_stats-2026-08-25-")


def test_run_id_flows_from_event_list_through_enrich_to_analyze():
    run_id = "simple_stats-2026-08-25-T000000Z-deadbeef"
    event_list = EventListV1(
        run_id=run_id, generated_at="x", date="2026-08-25", sports=["football"], events=[]
    )

    dossier_list = enrich_events(event_list)
    assert dossier_list.run_id == run_id
    assert dossier_list.date == "2026-08-25"

    stats_sheet = analyze_dossiers(dossier_list)
    assert stats_sheet.run_id == run_id
    assert stats_sheet.date == "2026-08-25"


def test_analyze_inherits_date_without_parsing_the_filename():
    """ANALYZE used to recover the betting date from the artifact's filename,
    so a renamed file silently wrote rows under the wrong betting_date."""
    dossier_list = EventDossierListV1(
        run_id="r", date="2026-08-25", generated_at="x",
        dossiers=[
            EventDossierV1(
                event_id="e1", sport="football", readiness="PARTIAL",
                metrics={
                    "corners_total": MetricObservation(
                        canonical_name="corners_total",
                        team_a_l10=[
                            ProviderValue(
                                provider="espn-football", match_id="m1",
                                match_date="2026-08-01", opponent="X", value=9.0,
                                observed_at="2026-08-25T00:00:00+00:00",
                            )
                        ],
                    )
                },
            )
        ],
    )
    sheet = analyze_dossiers(dossier_list)
    assert sheet.date == "2026-08-25"
    assert sheet.rows


def test_each_step_records_itself_and_shares_one_run_id(db):
    run_id = new_run_id("2026-08-25")
    for step, status in (("DISCOVER", "OK"), ("ENRICH", "PARTIAL"), ("ANALYZE", "OK")):
        record_pipeline_run(
            db, date="2026-08-25", step=step, status=status,
            run_id=run_id, stats={"output_sha256": f"sha-{step}"},
        )
    db.commit()

    rows = db.execute(
        "SELECT step, status, stats FROM pipeline_runs WHERE date = ?", ("2026-08-25",)
    ).fetchall()
    assert {r["step"] for r in rows} == {
        "simple_stats:DISCOVER", "simple_stats:ENRICH", "simple_stats:ANALYZE"
    }
    assert all(run_id in r["stats"] for r in rows)


def test_rerunning_a_step_overwrites_rather_than_duplicating(db):
    """UNIQUE(date, step) matches how the rest of this pipeline behaves: a
    rerun for a date replaces that date's result."""
    for status in ("FAILED", "OK"):
        record_pipeline_run(
            db, date="2026-08-25", step="ENRICH", status=status, run_id="r1", stats={}
        )
    db.commit()

    rows = db.execute(
        "SELECT status FROM pipeline_runs WHERE date = ? AND step = ?",
        ("2026-08-25", "simple_stats:ENRICH"),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "OK"


def test_load_run_reads_lineage_back_without_touching_the_filesystem(db, monkeypatch, tmp_path):
    run_id = new_run_id("2026-08-25")
    record_pipeline_run(
        db, date="2026-08-25", step="DISCOVER", status="OK",
        run_id=run_id, stats={"total_events": 39, "output_sha256": "abc"},
    )
    db.commit()

    import bet.simple_stats.run_context as run_context

    class _Ctx:
        def __enter__(self):
            return db

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(run_context, "get_db", lambda *_a, **_k: _Ctx())
    loaded = run_context.load_run("2026-08-25")

    assert loaded["DISCOVER"]["run_id"] == run_id
    assert loaded["DISCOVER"]["total_events"] == 39
    assert loaded["DISCOVER"]["status"] == "OK"
