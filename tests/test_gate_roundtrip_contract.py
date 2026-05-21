import json
import sqlite3
from contextlib import contextmanager
from csv import DictWriter
from pathlib import Path
from unittest.mock import patch

import pytest


ROOT_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT_DIR / "src" / "bet" / "db" / "schema.sql"
DATE = "2099-05-21"


@contextmanager
def _db_context(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _init_db(db_path: Path) -> None:
    with _db_context(db_path) as conn:
        conn.executescript(SCHEMA_PATH.read_text())


def _patch_repo_db(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    import bet.db.connection as db_connection

    def fake_get_db(_db_path=None):
        return _db_context(db_path)

    monkeypatch.setattr(db_connection, "get_db", fake_get_db)


def _seed_fixture(
    db_path: Path,
    *,
    sport: str,
    home_team: str,
    away_team: str,
    competition: str,
    kickoff: str | None = None,
) -> int:
    from bet.db.models import Fixture
    from bet.db.repositories import CompetitionRepo, FixtureRepo, SportRepo, TeamRepo

    with _db_context(db_path) as conn:
        sport_repo = SportRepo(conn)
        sport_repo.seed_defaults()
        sport_row = sport_repo.get_by_name(sport)
        assert sport_row is not None

        team_repo = TeamRepo(conn)
        home = team_repo.find_or_create(home_team, sport_row.id)
        away = team_repo.find_or_create(away_team, sport_row.id)
        competition_id = CompetitionRepo(conn).find_or_create(competition, sport_row.id)

        fixture = Fixture(
            id=None,
            sport_id=sport_row.id,
            competition_id=competition_id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff=kickoff or f"{DATE}T18:00:00+00:00",
            status="scheduled",
            source="test",
            fetched_at=f"{DATE}T10:00:00+00:00",
        )
        return FixtureRepo(conn).upsert(fixture)


def _candidate(**overrides) -> dict:
    candidate = {
        "sport": "football",
        "home_team": "Liverpool",
        "away_team": "Arsenal",
        "competition": "Premier League",
        "kickoff": f"{DATE}T18:00:00+00:00",
        "best_market": {
            "name": "Fouls Total O/U 22.5",
            "direction": "OVER",
            "line": 22.5,
            "safety_score": 0.78,
            "source": "api",
            "hit_rate_l10": "7/10",
        },
        "market_count": 3,
        "h2h_count": 5,
        "data_quality": {"score": 8, "label": "FULL"},
        "ev": 0.12,
        "odds": {"market_best": 1.85},
        "sources": ["src-a", "src-b"],
        "tipster_count": 1,
        "three_way_alignment": "3/3 ALIGNED",
        "three_way_check": {"alignment": "3/3 ALIGNED", "l10_avg": 24.0, "l5_avg": 23.0},
        "context_flags": [],
        "ranking": [],
        "warnings": [],
    }

    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(candidate.get(key), dict):
            candidate[key] = {**candidate[key], **value}
        else:
            candidate[key] = value
    return candidate


def _gate_entry(
    *,
    home_team: str,
    away_team: str,
    sport: str,
    competition: str,
    fixture_id: int | None,
    bucket: str,
    status: str,
    kickoff: str | None = None,
    reason: str | None = None,
) -> dict:
    entry = {
        "fixture_id": fixture_id,
        "sport": sport,
        "home_team": home_team,
        "away_team": away_team,
        "competition": competition,
        "kickoff": kickoff or f"{DATE}T18:00:00+00:00",
        "bucket": bucket,
        "status": status,
        "gate_score": "15/18",
        "advisory_tier": "STRONG" if bucket == "approved" else "FLAGGED",
        "best_market": {
            "name": "Fouls Total O/U 22.5",
            "line": 22.5,
            "direction": "OVER",
            "safety_score": 0.74,
            "source": "api",
            "hit_rate_l10": "7/10",
        },
        "ev": 0.12 if bucket != "rejected" else -0.05,
        "risk_tier": "LR" if bucket == "approved" else "HR",
        "gate_details": {
            "1": {
                "passed": True,
                "message": "",
                "label": "Identity verified",
            }
        },
        "odds": {"market_best": 1.85},
    }
    if bucket == "extended_pool":
        entry["extended_pool_reason"] = reason or "SYNTHETIC_DATA: source=db-synthetic"
    if bucket == "rejected":
        entry["rejection_reason"] = reason or "STRICT mode: 2 gate failures"
    return entry


def _config_file(tmp_path: Path) -> Path:
    config_path = tmp_path / "betting_config.json"
    config_path.write_text(
        json.dumps(
            {
                "working_bankroll_pln": 47,
                "suggested_daily_allocation_range_pln": [5, 15],
                "min_legs_per_coupon": 2,
                "max_same_sport_legs_in_coupon": 2,
            }
        ),
        encoding="utf-8",
    )
    return config_path


def _write_ledger_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = DictWriter(
            handle,
            fieldnames=["betting_day", "pick_id", "event", "sport", "market", "selection", "status"],
        )
        writer.writeheader()
        writer.writerows(rows)


def _read_pipeline_step(db_path: Path, date: str, step: str) -> tuple[str, dict | None]:
    with _db_context(db_path) as conn:
        row = conn.execute(
            "SELECT status, stats FROM pipeline_runs WHERE date = ? AND step = ?",
            (date, step),
        ).fetchone()
    assert row is not None
    return row["status"], json.loads(row["stats"]) if row["stats"] else None


def _seed_repeat_handoff(db_path: Path, *, repeat_loss_count: int = 0, findings: list[dict] | None = None, status: str = "completed") -> None:
    findings = findings or []
    payload = {
        "date": DATE,
        "step": "s7_6_repeat_loss_check",
        "window_hours": 48,
        "candidate_source": "json",
        "artifact_path": f"repeat_loss_handoff_{DATE}.json",
        "checked_candidates_count": 1,
        "recent_losses_count": repeat_loss_count,
        "repeat_loss_count": repeat_loss_count,
        "clear": repeat_loss_count == 0,
        "findings": findings,
        "checked_at": f"{DATE}T10:00:00+00:00",
    }
    with _db_context(db_path) as conn:
        conn.execute(
            "INSERT INTO pipeline_runs (date, step, status, started_at, completed_at, stats) VALUES (?, ?, ?, ?, ?, ?)",
            (DATE, "s7_6_repeat_loss_check", status, f"{DATE}T09:55:00+00:00", f"{DATE}T10:00:00+00:00", json.dumps(payload)),
        )


@pytest.mark.parametrize(
    ("overrides", "reason_fragment"),
    [
        ({"data_quality": {"score": 1, "label": "MINIMAL"}}, "Minimal data"),
        ({"best_market": {"source": "db-synthetic"}}, "SYNTHETIC_DATA"),
        ({"market_count": 2}, "INSUFFICIENT_MARKETS"),
        ({"best_market": {"hit_rate_l10": "5/10"}}, "COIN_FLIP"),
    ],
)
def test_gate_checker_routes_current_watch_list_paths_to_extended_pool(overrides, reason_fragment, monkeypatch, tmp_path):
    import scripts.gate_checker as gate_checker

    monkeypatch.setattr(gate_checker, "LEDGER_PATH", tmp_path / "picks-ledger.csv")
    with patch.object(gate_checker, "_build_fixture_lookup", return_value=(set(), set())), patch.object(
        gate_checker,
        "load_48h_repeats",
        return_value=[],
    ):
        result = gate_checker.run_gate([_candidate(**overrides)], DATE)

    extended = result["gate_results"]["extended_pool"]
    assert len(extended) == 1
    entry = extended[0]
    assert entry["bucket"] == "extended_pool"
    assert entry["status"] == "EXTENDED"
    assert reason_fragment in entry["extended_pool_reason"]


def test_gate_checker_outputs_keep_extended_pool_visible(tmp_path, monkeypatch):
    import scripts.gate_checker as gate_checker

    monkeypatch.setattr(gate_checker, "DATA_DIR", tmp_path)
    monkeypatch.setattr(gate_checker, "LEDGER_PATH", tmp_path / "picks-ledger.csv")
    with patch.object(gate_checker, "_build_fixture_lookup", return_value=(set(), set())), patch.object(
        gate_checker,
        "load_48h_repeats",
        return_value=[],
    ):
        result = gate_checker.run_gate([_candidate(data_quality={"score": 1, "label": "MINIMAL"})], DATE)

    json_path = gate_checker._write_json(result, DATE)
    markdown_path = gate_checker._write_markdown(result, DATE)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    extended_entry = payload["gate_results"]["extended_pool"][0]
    assert extended_entry["bucket"] == "extended_pool"
    assert extended_entry["status"] == "EXTENDED"

    markdown = markdown_path.read_text(encoding="utf-8")
    assert "## Extended Pool" in markdown
    assert "EXTENDED" in markdown


def test_gate_results_round_trip_through_db_preserves_bucket_semantics(monkeypatch, tmp_path):
    import scripts.db_data_loader as loader
    from bet.db.repositories import GateResultRepo

    db_path = tmp_path / "betting.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _init_db(db_path)
    _patch_repo_db(monkeypatch, db_path)
    monkeypatch.setattr(loader, "DATA_DIR", data_dir)

    _seed_fixture(
        db_path,
        sport="football",
        home_team="Liverpool",
        away_team="Arsenal",
        competition="Premier League",
        kickoff=f"{DATE}T18:00:00+00:00",
    )
    _seed_fixture(
        db_path,
        sport="football",
        home_team="Chelsea",
        away_team="Spurs",
        competition="Premier League",
        kickoff=f"{DATE}T20:00:00+00:00",
    )

    resolved_fixture = _seed_fixture(
        db_path,
        sport="football",
        home_team="Liverpool",
        away_team="Arsenal",
        competition="Premier League",
    )
    explicit_fixture = _seed_fixture(
        db_path,
        sport="hockey",
        home_team="Rangers",
        away_team="Bruins",
        competition="NHL",
    )

    saved = loader.save_gate_results_to_db(
        DATE,
        [
            _gate_entry(
                home_team="Liverpool",
                away_team="Arsenal",
                sport="football",
                competition="Premier League",
                fixture_id=None,
                bucket="approved",
                status="APPROVED",
            ),
            _gate_entry(
                home_team="Rangers",
                away_team="Bruins",
                sport="hockey",
                competition="NHL",
                fixture_id=explicit_fixture,
                bucket="extended_pool",
                status="EXTENDED",
                reason="SYNTHETIC_DATA: source=db-synthetic",
            ),
            _gate_entry(
                home_team="Lakers",
                away_team="Celtics",
                sport="basketball",
                competition="NBA",
                fixture_id=None,
                bucket="rejected",
                status="REJECTED",
                reason="STRICT mode: 2 gate failures",
            ),
        ],
    )
    assert saved == 3

    approved = loader.load_gate_results_from_db_only(DATE, status="approved")
    extended = loader.load_gate_results_from_db_only(DATE, status="extended")
    rejected = loader.load_gate_results_from_db_only(DATE, status="rejected")
    assert len(approved) == 1
    assert len(extended) == 1
    assert len(rejected) == 1
    assert approved[0]["status"] == "APPROVED"
    assert extended[0]["status"] == "EXTENDED"
    assert extended[0]["extended_pool_reason"] == "SYNTHETIC_DATA: source=db-synthetic"
    assert rejected[0]["status"] == "REJECTED"
    assert rejected[0]["rejection_reason"] == "STRICT mode: 2 gate failures"

    with _db_context(db_path) as conn:
        repo = GateResultRepo(conn)
        assert len(repo.get_approved(DATE)) == 1
        assert len(repo.get_extended(DATE)) == 1
        assert len(repo.get_rejected(DATE)) == 1

        persisted_statuses = {
            row["status"]
            for row in conn.execute(
                "SELECT status FROM gate_results WHERE betting_date = ?",
                (DATE,),
            ).fetchall()
        }
        assert persisted_statuses == {"APPROVED", "EXTENDED", "REJECTED"}

        resolved_row = conn.execute(
            "SELECT fixture_id FROM gate_results WHERE betting_date = ? AND status = 'APPROVED'",
            (DATE,),
        ).fetchone()
        assert resolved_row["fixture_id"] == resolved_fixture

        fixture_count = conn.execute("SELECT COUNT(*) AS count FROM fixtures").fetchone()["count"]
        assert fixture_count >= 3


def test_gate_loader_json_fallback_reads_nested_buckets(monkeypatch, tmp_path):
    import bet.db.connection as db_connection
    import scripts.db_data_loader as loader

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(loader, "DATA_DIR", data_dir)

    def failing_get_db(_db_path=None):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(db_connection, "get_db", failing_get_db)

    payload = {
        "date": DATE,
        "gate_results": {
            "approved": [
                _gate_entry(
                    home_team="Liverpool",
                    away_team="Arsenal",
                    sport="football",
                    competition="Premier League",
                    fixture_id=1,
                    bucket="approved",
                    status="APPROVED",
                )
            ],
            "extended_pool": [
                _gate_entry(
                    home_team="Rangers",
                    away_team="Bruins",
                    sport="hockey",
                    competition="NHL",
                    fixture_id=2,
                    bucket="extended_pool",
                    status="EXTENDED",
                    reason="SYNTHETIC_DATA: source=db-synthetic",
                )
            ],
            "rejected": [
                _gate_entry(
                    home_team="Lakers",
                    away_team="Celtics",
                    sport="basketball",
                    competition="NBA",
                    fixture_id=3,
                    bucket="rejected",
                    status="REJECTED",
                    reason="STRICT mode: 2 gate failures",
                )
            ],
        },
    }
    (data_dir / f"{DATE}_s7_gate_results.json").write_text(json.dumps(payload), encoding="utf-8")

    approved = loader.load_gate_results_from_db(DATE, status="approved")
    extended = loader.load_gate_results_from_db(DATE, status="extended")
    rejected = loader.load_gate_results_from_db(DATE, status="rejected")
    assert approved[0]["bucket"] == "approved"
    assert extended[0]["bucket"] == "extended_pool"
    assert extended[0]["status"] == "EXTENDED"
    assert rejected[0]["bucket"] == "rejected"
    assert rejected[0]["status"] == "REJECTED"


def test_gate_checker_uses_canonical_s3_loader_and_preserves_tipster_metadata(monkeypatch, tmp_path):
    import scripts.db_data_loader as loader
    import scripts.gate_checker as gate_checker
    from bet.db.repositories import AnalysisResultRepo

    db_path = tmp_path / "betting.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _init_db(db_path)
    _patch_repo_db(monkeypatch, db_path)
    monkeypatch.setattr(loader, "DATA_DIR", data_dir)

    json_analyses = [
        {
            "sport": "football",
            "home_team": "Liverpool",
            "away_team": "Arsenal",
            "competition": "Premier League",
            "kickoff": f"{DATE}T18:00:00+00:00",
            "has_data": True,
            "data_quality": {"score": 8, "label": "FULL"},
            "best_market": {
                "name": "Corners Total O/U 10.5",
                "direction": "OVER",
                "line": 10.5,
                "safety_score": 0.78,
                "source": "api",
                "hit_rate_l10": "7/10",
            },
            "markets_evaluated": 3,
            "stats_a_summary": {"sources": ["src-a"], "l10_avg": {"corners": 6.0}},
            "stats_b_summary": {"sources": ["src-b"], "l10_avg": {"corners": 5.0}},
            "h2h_summary": {"has_data": True, "meetings_count": 5},
            "ranking": [{"name": "Corners Total O/U 10.5", "safety_score": 0.78}],
            "three_way_check": {"alignment": "3/3 ALIGNED", "l10_avg": 11.0, "l5_avg": 10.8},
            "warnings": [],
            "tipster_support": {"count": 2, "tips": [{"source": "tipster-a"}, {"source": "tipster-b"}]},
            "tipster_count": 2,
        },
        {
            "sport": "football",
            "home_team": "Chelsea",
            "away_team": "Spurs",
            "competition": "Premier League",
            "kickoff": f"{DATE}T20:00:00+00:00",
            "has_data": True,
            "data_quality": {"score": 7, "label": "FULL"},
            "best_market": {
                "name": "Fouls Total O/U 23.5",
                "direction": "OVER",
                "line": 23.5,
                "safety_score": 0.74,
                "source": "api",
                "hit_rate_l10": "6/10",
            },
            "markets_evaluated": 3,
            "stats_a_summary": {"sources": ["src-c"], "l10_avg": {"fouls": 12.0}},
            "stats_b_summary": {"sources": ["src-d"], "l10_avg": {"fouls": 11.0}},
            "h2h_summary": {"has_data": True, "meetings_count": 4},
            "ranking": [{"name": "Fouls Total O/U 23.5", "safety_score": 0.74}],
            "three_way_check": {"alignment": "2/3 ALIGNED", "l10_avg": 23.0, "l5_avg": 22.5},
            "warnings": [],
            "tipster_support": {"count": 1, "tips": [{"source": "tipster-c"}]},
            "tipster_count": 1,
        },
        {
            "sport": "hockey",
            "home_team": "Rangers",
            "away_team": "Bruins",
            "competition": "NHL",
            "kickoff": f"{DATE}T21:00:00+00:00",
            "has_data": True,
            "data_quality": {"score": 6, "label": "PARTIAL"},
            "best_market": {
                "name": "Shots Total O/U 61.5",
                "direction": "OVER",
                "line": 61.5,
                "safety_score": 0.69,
                "source": "api",
                "hit_rate_l10": "6/10",
            },
            "markets_evaluated": 2,
            "stats_a_summary": {"sources": ["src-e"], "l10_avg": {"shots": 32.0}},
            "stats_b_summary": {"sources": ["src-f"], "l10_avg": {"shots": 31.0}},
            "h2h_summary": {"has_data": False, "meetings_count": 0},
            "ranking": [{"name": "Shots Total O/U 61.5", "safety_score": 0.69}],
            "three_way_check": {"alignment": "2/3 ALIGNED", "l10_avg": 63.0, "l5_avg": 62.0},
            "warnings": [],
            "tipster_support": {"count": 1, "tips": [{"source": "tipster-json-only"}]},
            "tipster_count": 1,
        },
    ]
    (data_dir / f"{DATE}_s3_deep_stats.json").write_text(
        json.dumps({"analyses": json_analyses}),
        encoding="utf-8",
    )

    saved = loader.save_analysis_results_to_db(DATE, json_analyses[:2])
    assert saved == 2

    with _db_context(db_path) as conn:
        repo = AnalysisResultRepo(conn)
        for home_team, ev, context_flag, risk_level in [
            ("Liverpool", 0.12, "WEATHER:wind", "LOW"),
            ("Chelsea", 0.05, "INJURY:key player", "ELEVATED"),
        ]:
            fixture_id = conn.execute(
                "SELECT f.id FROM fixtures f "
                "JOIN teams ht ON f.home_team_id = ht.id "
                "WHERE ht.name = ?",
                (home_team,),
            ).fetchone()["id"]
            existing = repo.get_by_fixture(fixture_id, DATE)
            summary = existing.stats_summary_json or {}
            summary["ev"] = ev
            summary["context_flags"] = [context_flag]
            summary["upset_risk"] = {"level": risk_level, "factor_count": 1}
            repo.update_stats_summary(fixture_id, DATE, summary)
        conn.commit()

    candidates, metadata = gate_checker._load_s3_output(DATE)

    assert len(candidates) == 3
    assert metadata["source"] == "json_with_db_overlay"
    assert metadata["parity"]["status"] == "db_subset_of_json"
    assert metadata["counts"]["canonical"] == 3
    assert metadata["counts"]["db"] == 2
    assert metadata["counts"]["json"] == 3

    by_home = {candidate["home_team"]: candidate for candidate in candidates}
    assert by_home["Liverpool"]["tipster_support"]["count"] == 2
    assert by_home["Liverpool"]["tipster_count"] == 2
    assert by_home["Liverpool"]["data_quality"]["label"] == "FULL"
    assert by_home["Liverpool"]["ev"] == 0.12
    assert by_home["Liverpool"]["context_flags"] == ["WEATHER:wind"]
    assert by_home["Liverpool"]["upset_risk"]["level"] == "LOW"

    assert by_home["Rangers"]["tipster_support"]["tips"][0]["source"] == "tipster-json-only"
    assert by_home["Rangers"]["tipster_count"] == 1


def test_coupon_builder_db_resume_preserves_extended_pool_and_parity_metrics(monkeypatch, tmp_path):
    import scripts.coupon_builder as coupon_builder
    import scripts.db_data_loader as loader

    db_path = tmp_path / "betting.db"
    data_dir = tmp_path / "data"
    coupon_dir = tmp_path / "coupons"
    data_dir.mkdir()
    coupon_dir.mkdir()
    _init_db(db_path)
    _patch_repo_db(monkeypatch, db_path)
    monkeypatch.setattr(loader, "DATA_DIR", data_dir)
    monkeypatch.setattr(coupon_builder, "DATA_DIR", data_dir)
    monkeypatch.setattr(coupon_builder, "COUPON_DIR", coupon_dir)
    monkeypatch.setattr(coupon_builder, "CONFIG_PATH", _config_file(tmp_path))

    approved_fixture = _seed_fixture(
        db_path,
        sport="football",
        home_team="Liverpool",
        away_team="Arsenal",
        competition="Premier League",
    )
    extended_fixture = _seed_fixture(
        db_path,
        sport="hockey",
        home_team="Rangers",
        away_team="Bruins",
        competition="NHL",
    )
    rejected_fixture = _seed_fixture(
        db_path,
        sport="basketball",
        home_team="Lakers",
        away_team="Celtics",
        competition="NBA",
    )

    loader.save_gate_results_to_db(
        DATE,
        [
            _gate_entry(
                home_team="Liverpool",
                away_team="Arsenal",
                sport="football",
                competition="Premier League",
                fixture_id=approved_fixture,
                bucket="approved",
                status="APPROVED",
            ),
            _gate_entry(
                home_team="Rangers",
                away_team="Bruins",
                sport="hockey",
                competition="NHL",
                fixture_id=extended_fixture,
                bucket="extended_pool",
                status="EXTENDED",
                reason="SYNTHETIC_DATA: source=db-synthetic",
            ),
            _gate_entry(
                home_team="Lakers",
                away_team="Celtics",
                sport="basketball",
                competition="NBA",
                fixture_id=rejected_fixture,
                bucket="rejected",
                status="REJECTED",
                reason="STRICT mode: 2 gate failures",
            ),
        ],
    )

    gate_results = coupon_builder._load_gate_results_for_build(DATE)
    assert gate_results["gate_parity"]["source"] == "db"
    assert gate_results["gate_parity"]["loaded_counts"] == {
        "approved": 1,
        "extended": 1,
        "rejected": 1,
    }

    coupons = coupon_builder.build_coupons(gate_results, coupon_builder.load_config())
    assert coupons["gate_parity"]["loaded_counts"]["extended"] == 1
    assert coupons["summary"]["gate_input_counts"] == {
        "approved": 1,
        "extended": 1,
        "rejected": 1,
    }
    assert any(pick["home_team"] == "Rangers" for pick in coupons["extended_pool"])


def test_coupon_builder_uses_json_fallback_when_db_is_empty(monkeypatch, tmp_path):
    import scripts.coupon_builder as coupon_builder

    data_dir = tmp_path / "data"
    coupon_dir = tmp_path / "coupons"
    data_dir.mkdir()
    coupon_dir.mkdir()
    monkeypatch.setattr(coupon_builder, "DATA_DIR", data_dir)
    monkeypatch.setattr(coupon_builder, "COUPON_DIR", coupon_dir)
    monkeypatch.setattr(coupon_builder, "CONFIG_PATH", _config_file(tmp_path))

    payload = {
        "date": DATE,
        "gate_results": {
            "approved": [
                _gate_entry(
                    home_team="Liverpool",
                    away_team="Arsenal",
                    sport="football",
                    competition="Premier League",
                    fixture_id=1,
                    bucket="approved",
                    status="APPROVED",
                )
            ],
            "extended_pool": [
                _gate_entry(
                    home_team="Rangers",
                    away_team="Bruins",
                    sport="hockey",
                    competition="NHL",
                    fixture_id=2,
                    bucket="extended_pool",
                    status="EXTENDED",
                    reason="SYNTHETIC_DATA: source=db-synthetic",
                )
            ],
            "rejected": [
                _gate_entry(
                    home_team="Lakers",
                    away_team="Celtics",
                    sport="basketball",
                    competition="NBA",
                    fixture_id=3,
                    bucket="rejected",
                    status="REJECTED",
                    reason="STRICT mode: 2 gate failures",
                )
            ],
        },
    }
    (data_dir / f"{DATE}_s7_gate_results.json").write_text(json.dumps(payload), encoding="utf-8")

    gate_results = coupon_builder._load_gate_results_for_build(DATE)
    assert gate_results["gate_parity"]["source"] == "json"

    coupons = coupon_builder.build_coupons(gate_results, coupon_builder.load_config())
    assert coupons["summary"]["gate_input_counts"] == {
        "approved": 1,
        "extended": 1,
        "rejected": 1,
    }
    assert any(pick["home_team"] == "Rangers" for pick in coupons["extended_pool"])


def test_coupon_builder_blocks_on_gate_parity_mismatch(monkeypatch, tmp_path, capsys):
    import scripts.coupon_builder as coupon_builder
    import scripts.db_data_loader as loader

    db_path = tmp_path / "betting.db"
    data_dir = tmp_path / "data"
    coupon_dir = tmp_path / "coupons"
    data_dir.mkdir()
    coupon_dir.mkdir()
    _init_db(db_path)
    _patch_repo_db(monkeypatch, db_path)
    monkeypatch.setattr(loader, "DATA_DIR", data_dir)
    monkeypatch.setattr(coupon_builder, "DATA_DIR", data_dir)
    monkeypatch.setattr(coupon_builder, "COUPON_DIR", coupon_dir)
    monkeypatch.setattr(coupon_builder, "CONFIG_PATH", _config_file(tmp_path))

    approved_fixture = _seed_fixture(
        db_path,
        sport="football",
        home_team="Liverpool",
        away_team="Arsenal",
        competition="Premier League",
    )
    extended_fixture = _seed_fixture(
        db_path,
        sport="hockey",
        home_team="Rangers",
        away_team="Bruins",
        competition="NHL",
    )

    loader.save_gate_results_to_db(
        DATE,
        [
            _gate_entry(
                home_team="Liverpool",
                away_team="Arsenal",
                sport="football",
                competition="Premier League",
                fixture_id=approved_fixture,
                bucket="approved",
                status="APPROVED",
            ),
            _gate_entry(
                home_team="Rangers",
                away_team="Bruins",
                sport="hockey",
                competition="NHL",
                fixture_id=extended_fixture,
                bucket="extended_pool",
                status="EXTENDED",
                reason="SYNTHETIC_DATA: source=db-synthetic",
            ),
        ],
    )

    mismatched_payload = {
        "date": DATE,
        "gate_results": {
            "approved": [
                _gate_entry(
                    home_team="Liverpool",
                    away_team="Arsenal",
                    sport="football",
                    competition="Premier League",
                    fixture_id=approved_fixture,
                    bucket="approved",
                    status="APPROVED",
                )
            ],
            "extended_pool": [],
            "rejected": [],
        },
    }
    (data_dir / f"{DATE}_s7_gate_results.json").write_text(json.dumps(mismatched_payload), encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.argv", ["coupon_builder.py", "--date", DATE]):
            coupon_builder.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Blocking gate parity mismatch" in f"{captured.out}\n{captured.err}"


def test_check_48h_repeats_persists_clear_db_handoff(monkeypatch, tmp_path):
    import scripts.check_48h_repeats as repeat_check

    db_path = tmp_path / "betting.db"
    data_dir = tmp_path / "data"
    ledger_path = tmp_path / "journal" / "picks-ledger.csv"
    data_dir.mkdir()
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    _init_db(db_path)
    _patch_repo_db(monkeypatch, db_path)
    monkeypatch.setattr(repeat_check, "DATA_DIR", data_dir)

    payload = {
        "date": DATE,
        "gate_results": {
            "approved": [
                _gate_entry(
                    home_team="Liverpool",
                    away_team="Arsenal",
                    sport="football",
                    competition="Premier League",
                    fixture_id=1,
                    bucket="approved",
                    status="APPROVED",
                )
            ],
            "extended_pool": [],
            "rejected": [],
        },
    }
    (data_dir / f"{DATE}_s7_gate_results.json").write_text(json.dumps(payload), encoding="utf-8")
    _write_ledger_rows(ledger_path, [])

    with pytest.raises(SystemExit) as exc_info:
        with patch(
            "sys.argv",
            [
                "check_48h_repeats.py",
                "--date",
                DATE,
                "--ledger",
                str(ledger_path),
                "--format",
                "json",
            ],
        ):
            repeat_check.main()

    assert exc_info.value.code == 0

    artifact = json.loads((data_dir / f"repeat_loss_handoff_{DATE}.json").read_text(encoding="utf-8"))
    assert artifact["repeat_loss_count"] == 0
    assert artifact["checked_candidates_count"] == 1
    assert artifact["clear"] is True

    status, stats = _read_pipeline_step(db_path, DATE, repeat_check.REPEAT_LOSS_STEP)
    assert status == "completed"
    assert stats is not None
    assert stats["repeat_loss_count"] == 0
    assert stats["clear"] is True


def test_check_48h_repeats_persists_matching_loss_handoff(monkeypatch, tmp_path):
    import scripts.check_48h_repeats as repeat_check

    db_path = tmp_path / "betting.db"
    data_dir = tmp_path / "data"
    ledger_path = tmp_path / "journal" / "picks-ledger.csv"
    data_dir.mkdir()
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    _init_db(db_path)
    _patch_repo_db(monkeypatch, db_path)
    monkeypatch.setattr(repeat_check, "DATA_DIR", data_dir)

    payload = {
        "date": DATE,
        "gate_results": {
            "approved": [
                _gate_entry(
                    home_team="Liverpool",
                    away_team="Arsenal",
                    sport="football",
                    competition="Premier League",
                    fixture_id=1,
                    bucket="approved",
                    status="APPROVED",
                )
            ],
            "extended_pool": [],
            "rejected": [],
        },
    }
    (data_dir / f"{DATE}_s7_gate_results.json").write_text(json.dumps(payload), encoding="utf-8")
    _write_ledger_rows(
        ledger_path,
        [
            {
                "betting_day": DATE,
                "pick_id": "PK-001",
                "event": "Liverpool vs Arsenal",
                "sport": "football",
                "market": "Fouls Total O/U 22.5",
                "selection": "OVER",
                "status": "loss",
            }
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        with patch(
            "sys.argv",
            [
                "check_48h_repeats.py",
                "--date",
                DATE,
                "--ledger",
                str(ledger_path),
                "--format",
                "json",
            ],
        ):
            repeat_check.main()

    assert exc_info.value.code == 1

    artifact = json.loads((data_dir / f"repeat_loss_handoff_{DATE}.json").read_text(encoding="utf-8"))
    assert artifact["repeat_loss_count"] == 1
    assert artifact["clear"] is False
    finding = artifact["findings"][0]
    assert finding["home_team"] == "Liverpool"
    assert finding["market_name"] == "Fouls Total O/U 22.5"
    assert finding["action"] == "HARD_REJECT"

    status, stats = _read_pipeline_step(db_path, DATE, repeat_check.REPEAT_LOSS_STEP)
    assert status == "completed"
    assert stats is not None
    assert stats["repeat_loss_count"] == 1
    assert stats["findings"][0]["matched_loss"]["pick_id"] == "PK-001"


def test_coupon_builder_consumes_betclic_sidecar_and_clear_repeat_handoff(monkeypatch, tmp_path):
    import scripts.coupon_builder as coupon_builder

    db_path = tmp_path / "betting.db"
    data_dir = tmp_path / "data"
    coupon_dir = tmp_path / "coupons"
    data_dir.mkdir()
    coupon_dir.mkdir()
    _init_db(db_path)
    _patch_repo_db(monkeypatch, db_path)
    monkeypatch.setattr(coupon_builder, "DATA_DIR", data_dir)
    monkeypatch.setattr(coupon_builder, "COUPON_DIR", coupon_dir)
    monkeypatch.setattr(coupon_builder, "CONFIG_PATH", _config_file(tmp_path))

    _seed_repeat_handoff(db_path)
    (data_dir / f"betclic_market_validation_{DATE}.json").write_text(
        json.dumps(
            {
                "validation": [
                    {
                        "event": "Liverpool - Arsenal",
                        "market": "Fouls Total O/U 22.5",
                        "market_type": "fouls",
                        "betclic_available": True,
                        "betclic_note": "available",
                    }
                ],
                "events": [],
            }
        ),
        encoding="utf-8",
    )
    payload = {
        "date": DATE,
        "gate_results": {
            "approved": [
                _gate_entry(
                    home_team="Liverpool",
                    away_team="Arsenal",
                    sport="football",
                    competition="Premier League",
                    fixture_id=1,
                    bucket="approved",
                    status="APPROVED",
                )
            ],
            "extended_pool": [],
            "rejected": [],
        },
    }
    (data_dir / f"{DATE}_s7_gate_results.json").write_text(json.dumps(payload), encoding="utf-8")

    with patch("sys.argv", ["coupon_builder.py", "--date", DATE]):
        coupon_builder.main()

    coupon_payload = json.loads((coupon_dir / f"{DATE}.json").read_text(encoding="utf-8"))
    controls = coupon_payload["pre_coupon_controls"]
    assert controls["betclic_market_validation"]["consumed"] is True
    assert controls["betclic_market_validation"]["mode"] == "validation"
    assert controls["repeat_loss_handoff"]["consumed"] is True
    assert controls["repeat_loss_handoff"]["repeat_loss_count"] == 0


def test_coupon_builder_fails_when_betclic_sidecar_is_missing(monkeypatch, tmp_path, capsys):
    import scripts.coupon_builder as coupon_builder

    db_path = tmp_path / "betting.db"
    data_dir = tmp_path / "data"
    coupon_dir = tmp_path / "coupons"
    data_dir.mkdir()
    coupon_dir.mkdir()
    _init_db(db_path)
    _patch_repo_db(monkeypatch, db_path)
    monkeypatch.setattr(coupon_builder, "DATA_DIR", data_dir)
    monkeypatch.setattr(coupon_builder, "COUPON_DIR", coupon_dir)
    monkeypatch.setattr(coupon_builder, "CONFIG_PATH", _config_file(tmp_path))

    _seed_repeat_handoff(db_path)
    payload = {
        "date": DATE,
        "gate_results": {
            "approved": [
                _gate_entry(
                    home_team="Liverpool",
                    away_team="Arsenal",
                    sport="football",
                    competition="Premier League",
                    fixture_id=1,
                    bucket="approved",
                    status="APPROVED",
                )
            ],
            "extended_pool": [],
            "rejected": [],
        },
    }
    (data_dir / f"{DATE}_s7_gate_results.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.argv", ["coupon_builder.py", "--date", DATE]):
            coupon_builder.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Missing mandatory S7.5 Betclic validation sidecar" in f"{captured.out}\n{captured.err}"


def test_coupon_builder_fails_when_betclic_sidecar_is_malformed(monkeypatch, tmp_path, capsys):
    import scripts.coupon_builder as coupon_builder

    db_path = tmp_path / "betting.db"
    data_dir = tmp_path / "data"
    coupon_dir = tmp_path / "coupons"
    data_dir.mkdir()
    coupon_dir.mkdir()
    _init_db(db_path)
    _patch_repo_db(monkeypatch, db_path)
    monkeypatch.setattr(coupon_builder, "DATA_DIR", data_dir)
    monkeypatch.setattr(coupon_builder, "COUPON_DIR", coupon_dir)
    monkeypatch.setattr(coupon_builder, "CONFIG_PATH", _config_file(tmp_path))

    _seed_repeat_handoff(db_path)
    (data_dir / f"betclic_market_validation_{DATE}.json").write_text("{not-json", encoding="utf-8")
    payload = {
        "date": DATE,
        "gate_results": {
            "approved": [
                _gate_entry(
                    home_team="Liverpool",
                    away_team="Arsenal",
                    sport="football",
                    competition="Premier League",
                    fixture_id=1,
                    bucket="approved",
                    status="APPROVED",
                )
            ],
            "extended_pool": [],
            "rejected": [],
        },
    }
    (data_dir / f"{DATE}_s7_gate_results.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.argv", ["coupon_builder.py", "--date", DATE]):
            coupon_builder.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Malformed S7.5 Betclic validation sidecar" in f"{captured.out}\n{captured.err}"


def test_coupon_builder_applies_repeat_loss_hard_reject(monkeypatch, tmp_path):
    import scripts.coupon_builder as coupon_builder

    db_path = tmp_path / "betting.db"
    data_dir = tmp_path / "data"
    coupon_dir = tmp_path / "coupons"
    data_dir.mkdir()
    coupon_dir.mkdir()
    _init_db(db_path)
    _patch_repo_db(monkeypatch, db_path)
    monkeypatch.setattr(coupon_builder, "DATA_DIR", data_dir)
    monkeypatch.setattr(coupon_builder, "COUPON_DIR", coupon_dir)
    monkeypatch.setattr(coupon_builder, "CONFIG_PATH", _config_file(tmp_path))

    _seed_repeat_handoff(
        db_path,
        repeat_loss_count=1,
        findings=[
            {
                "fixture_id": 1,
                "home_team": "Liverpool",
                "away_team": "Arsenal",
                "market_name": "Fouls Total O/U 22.5",
                "market_normalized": "fouls total o/u 22.5",
                "event_key": "liverpool|arsenal",
                "matched_loss": {"pick_id": "PK-001", "lost_on": DATE},
                "action": "HARD_REJECT",
            }
        ],
    )
    (data_dir / f"betclic_market_validation_{DATE}.json").write_text(
        json.dumps({"validation": [], "events": []}),
        encoding="utf-8",
    )
    payload = {
        "date": DATE,
        "gate_results": {
            "approved": [
                _gate_entry(
                    home_team="Liverpool",
                    away_team="Arsenal",
                    sport="football",
                    competition="Premier League",
                    fixture_id=1,
                    bucket="approved",
                    status="APPROVED",
                )
            ],
            "extended_pool": [],
            "rejected": [],
        },
    }
    (data_dir / f"{DATE}_s7_gate_results.json").write_text(json.dumps(payload), encoding="utf-8")

    with patch("sys.argv", ["coupon_builder.py", "--date", DATE]):
        coupon_builder.main()

    coupon_payload = json.loads((coupon_dir / f"{DATE}.json").read_text(encoding="utf-8"))
    assert coupon_payload["no_bet"] is True
    assert coupon_payload["pre_coupon_controls"]["repeat_loss_handoff"]["excluded_count"] == 1
    assert any(pick["rejection_reason"] == "S7.6 repeat-loss HARD REJECT" for pick in coupon_payload["rejected"])


def test_coupon_builder_fails_on_malformed_repeat_handoff(monkeypatch, tmp_path, capsys):
    import scripts.coupon_builder as coupon_builder

    db_path = tmp_path / "betting.db"
    data_dir = tmp_path / "data"
    coupon_dir = tmp_path / "coupons"
    data_dir.mkdir()
    coupon_dir.mkdir()
    _init_db(db_path)
    _patch_repo_db(monkeypatch, db_path)
    monkeypatch.setattr(coupon_builder, "DATA_DIR", data_dir)
    monkeypatch.setattr(coupon_builder, "COUPON_DIR", coupon_dir)
    monkeypatch.setattr(coupon_builder, "CONFIG_PATH", _config_file(tmp_path))

    with _db_context(db_path) as conn:
        conn.execute(
            "INSERT INTO pipeline_runs (date, step, status, started_at, completed_at, stats) VALUES (?, ?, ?, ?, ?, ?)",
            (DATE, "s7_6_repeat_loss_check", "completed", f"{DATE}T09:55:00+00:00", f"{DATE}T10:00:00+00:00", json.dumps({"date": DATE, "repeat_loss_count": 1, "findings": "bad"})),
        )

    (data_dir / f"betclic_market_validation_{DATE}.json").write_text(
        json.dumps({"validation": [], "events": []}),
        encoding="utf-8",
    )
    payload = {
        "date": DATE,
        "gate_results": {
            "approved": [
                _gate_entry(
                    home_team="Liverpool",
                    away_team="Arsenal",
                    sport="football",
                    competition="Premier League",
                    fixture_id=1,
                    bucket="approved",
                    status="APPROVED",
                )
            ],
            "extended_pool": [],
            "rejected": [],
        },
    }
    (data_dir / f"{DATE}_s7_gate_results.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.argv", ["coupon_builder.py", "--date", DATE]):
            coupon_builder.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Malformed S7.6 handoff" in f"{captured.out}\n{captured.err}"