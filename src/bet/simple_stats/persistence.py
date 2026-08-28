"""Persist EVENT_LIST_V1 / EVENT_DOSSIER_V1 / STATS_SHEET_V1 to the DB.

See docs/PIPELINE_SIMPLIFICATION_PLAN.md section 8. Deliberately does not use
launch_bridge.py's promote_shadow_results() (built for gate_results/
decision_snapshots, which this pipeline never writes) nor
fixture_capability_observation (requires a NOT NULL team_id FK that tennis
singles has no clean equivalent for without treating a player as a "team" --
which is exactly what fixtures.home_team_id/away_team_id already do
elsewhere in this codebase, so analysis_raw_data is used instead).
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from bet.db.connection import get_db
from bet.db.models import AnalysisRawData, AnalysisResult, Fixture
from bet.db.repositories import (
    AnalysisRawDataRepo,
    AnalysisResultRepo,
    CompetitionRepo,
    FixtureRepo,
    SportRepo,
    TeamRepo,
)

from bet.simple_stats.contracts import (
    EventDossierListV1,
    EventDossierV1,
    EventListV1,
    EventRecord,
    ProviderValue,
    StatsSheetRow,
    StatsSheetV1,
)


# bet.db.connection._resolve_db_path deliberately refuses to guess an
# operational database ("There is no implicit operational database
# fallback"), so it needs BET_DB_PATH/DATABASE_URL set or an explicit
# argument. Rather than weaken that shared invariant, this package resolves
# its own default and passes it down connection.py's explicit-argument path.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = _REPO_ROOT / "betting" / "data" / "betting.db"


def default_db_path() -> str:
    """The DB the simple_stats CLIs write to unless told otherwise:
    ``BET_DB_PATH``/``DATABASE_URL`` if the environment sets one, else the
    repo's operational ``betting/data/betting.db``."""
    for var in ("BET_DB_PATH", "DATABASE_URL"):
        value = os.environ.get(var)
        if value:
            return value
    return str(DEFAULT_DB_PATH)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _side_names(event: EventRecord) -> tuple[str, str]:
    if event.sport == "tennis":
        return event.player_one or "", event.player_two or ""
    return event.home_team or "", event.away_team or ""


def _provider_value_to_dict(pv: ProviderValue) -> dict:
    return {
        "provider": pv.provider,
        "match_id": pv.match_id,
        "match_date": pv.match_date,
        "opponent": pv.opponent,
        "value": pv.value,
        "observed_at": pv.observed_at,
    }


def _stats_row_to_dict(row: StatsSheetRow) -> dict:
    return {
        "market": row.market,
        "line": row.line,
        "direction": row.direction,
        # Whitelisted for the same reason p_low below is: the analyst is told to
        # cross-check the DB for other run_ids of the same day, and a "corners_for
        # OVER 4.5" row that arrives there without a team -- or a prop without a
        # player -- names no bet at all. Omitted when absent, so a match-total row
        # is unchanged rather than gaining three nulls.
        **({"team_name": row.team_name} if row.team_name else {}),
        **({"player_id": row.player_id} if row.player_id else {}),
        **({"player_name": row.player_name} if row.player_name else {}),
        **({"lineup_status": row.lineup_status} if row.lineup_status else {}),
        "hits": row.hits,
        "sample_size": row.sample_size,
        "pushes": row.pushes,
        "hit_rate": row.hit_rate,
        # The ranking key travels with the row. This dict is a whitelist, so a
        # new field is dropped unless named here -- and a row reachable only
        # through the DB (which the analyst is told to cross-check for other
        # run_ids of the same day) would otherwise arrive without the one
        # number it is sorted by, leaving hit_rate as the only available
        # proxy: exactly the small-sample inversion p_low exists to prevent.
        "p_low": row.p_low,
        "mean": row.mean,
        "median": row.median,
        "sources": row.sources,
        "cross_provider_agreement": row.cross_provider_agreement,
        "confidence": row.confidence,
        "data_quality": row.data_quality,
        # Carried into ranking_json because the analyst is told to cross-check
        # the DB for other run_ids of the same day, and rows reachable only
        # there would otherwise lose the column the artifact shows. Omitted
        # entirely when absent, so a pre-TIPSTERS row is unchanged rather than
        # gaining a null that reads as "checked, nobody agreed".
        **({"tipster": row.tipster.model_dump(mode="json")} if row.tipster else {}),
    }


def fixture_ids_by_event_id(conn: sqlite3.Connection, event_ids: set[str]) -> dict[str, int]:
    """Look up already-persisted fixtures.id by EventRecord.event_id (stored
    as fixtures.external_id by persist_event_list). Lets run_analyze.py
    persist STATS_SHEET_V1 without needing the original EVENT_LIST_V1 on
    hand, since fixtures were already written in the DISCOVER/ENRICH steps."""
    if not event_ids:
        return {}
    placeholders = ",".join("?" for _ in event_ids)
    rows = conn.execute(
        f"SELECT external_id, id FROM fixtures WHERE external_id IN ({placeholders})",
        tuple(event_ids),
    ).fetchall()
    return {row["external_id"]: row["id"] for row in rows}


def persist_event_list(event_list: EventListV1, conn: sqlite3.Connection) -> dict[str, int]:
    """Persist EVENT_LIST_V1 to fixtures/fixture_sources (already-existing
    tables, no migration). Returns event_id -> fixtures.id for the two
    persist functions below. BLOCKED_IDENTITY events are skipped: there is no
    single canonical pair of teams to key a fixture row on."""
    sport_repo = SportRepo(conn)
    team_repo = TeamRepo(conn)
    competition_repo = CompetitionRepo(conn)
    fixture_repo = FixtureRepo(conn)

    fixture_ids: dict[str, int] = {}
    for event in event_list.events:
        if event.status != "ACTIVE":
            continue
        sport_row = sport_repo.get_by_name(event.sport)
        if sport_row is None:
            sport_repo.seed_defaults()
            sport_row = sport_repo.get_by_name(event.sport)
        sport_id = sport_row.id

        team_a_name, team_b_name = _side_names(event)
        team_a = team_repo.find_or_create(team_a_name, sport_id)
        team_b = team_repo.find_or_create(team_b_name, sport_id)
        competition_id = competition_repo.find_or_create(event.competition, sport_id)

        fixture = Fixture(
            id=None,
            sport_id=sport_id,
            competition_id=competition_id,
            home_team_id=team_a.id,
            away_team_id=team_b.id,
            kickoff=event.start_time,
            status="scheduled",
            external_id=event.event_id,
            source="+".join(sorted(event.source_ids)) or "simple_stats",
            fetched_at=_now(),
        )
        fixture_id = fixture_repo.upsert(fixture)
        fixture_ids[event.event_id] = fixture_id
        _persist_fixture_sources(event, fixture_id, conn)
    return fixture_ids


def _persist_fixture_sources(event: EventRecord, fixture_id: int, conn: sqlite3.Connection) -> None:
    """Write one fixture_sources row per discovery source that saw this event.

    Section 8 lists fixture_sources alongside fixtures as EVENT_LIST_V1's
    destination: it is what records *which* sources agreed on an event, the
    lineage behind identity_confidence. The table's uq_fixture_source
    (fixture_id, source) constraint makes the upsert idempotent across reruns.
    Highlightly's native team ids ride along in raw_data so ENRICH can be
    replayed from the DB alone.
    """
    now = _now()
    for source, external_id in sorted(event.source_ids.items()):
        raw = event.provider_team_ids.get(source)
        conn.execute(
            """
            INSERT INTO fixture_sources (fixture_id, source, external_id, confidence, raw_data, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(fixture_id, source) DO UPDATE SET
                external_id = excluded.external_id,
                confidence = excluded.confidence,
                raw_data = excluded.raw_data,
                fetched_at = excluded.fetched_at
            """,
            (
                fixture_id,
                source,
                external_id,
                1.0 if event.identity_confidence == "CONFIRMED" else 0.8,
                json.dumps(raw) if raw else None,
                now,
            ),
        )


def persist_event_dossier(
    dossier: EventDossierV1,
    fixture_id: int,
    betting_date: str,
    conn: sqlite3.Connection,
    run_id: str = "",
) -> None:
    """Persist one EVENT_DOSSIER_V1 to analysis_raw_data. Each JSON column is
    a dict keyed by canonical metric name (section 8), not a flat list, so a
    reader never has to guess which metric a value belongs to."""
    team_a_l10_json = {name: [_provider_value_to_dict(pv) for pv in obs.team_a_l10] for name, obs in dossier.metrics.items()}
    team_b_l10_json = {name: [_provider_value_to_dict(pv) for pv in obs.team_b_l10] for name, obs in dossier.metrics.items()}
    h2h_meetings_json = {name: [_provider_value_to_dict(pv) for pv in obs.h2h] for name, obs in dossier.metrics.items()}

    raw = AnalysisRawData(
        id=None,
        fixture_id=fixture_id,
        betting_date=betting_date,
        team_a_l10_json=team_a_l10_json,
        team_b_l10_json=team_b_l10_json,
        h2h_meetings_json=h2h_meetings_json,
        per_market_details_json=[],
        safety_input_json={
            "run_id": run_id,
            "readiness": dossier.readiness,
            "data_gaps": dossier.data_gaps,
        },
        created_at=_now(),
    )
    AnalysisRawDataRepo(conn).save(raw)


def persist_stats_sheet(
    stats_sheet: StatsSheetV1, fixture_ids: dict[str, int], betting_date: str, conn: sqlite3.Connection
) -> None:
    run_id = stats_sheet.run_id
    """Persist STATS_SHEET_V1 to analysis_results: one row per event,
    ranking_json holding every event x market x line x direction row.
    cross_provider_agreement/confidence/data_quality travel inside that JSON
    since analysis_results has no dedicated columns for them (section 8)."""
    result_repo = AnalysisResultRepo(conn)
    rows_by_event: dict[str, list[StatsSheetRow]] = {}
    for row in stats_sheet.rows:
        rows_by_event.setdefault(row.event_id, []).append(row)

    for event_id, rows in rows_by_event.items():
        fixture_id = fixture_ids.get(event_id)
        if fixture_id is None:
            continue
        best = rows[0]  # stats_sheet.rows is already sorted confidence desc, hit_rate desc
        result = AnalysisResult(
            id=None,
            fixture_id=fixture_id,
            betting_date=betting_date,
            has_data=True,
            best_market_name=best.market,
            best_market_line=best.line,
            best_market_direction=best.direction,
            best_safety_score=None,
            markets_evaluated=len(rows),
            ranking_json=[_stats_row_to_dict(r) for r in rows],
            three_way_check_json=None,
            warnings_json=[],
            stats_summary_json={"run_id": run_id, "row_count": len(rows)},
            source="simple_stats",
            created_at=_now(),
        )
        result_repo.save(result)


def persist_pipeline_run(
    event_list: EventListV1,
    dossier_list: EventDossierListV1 | None,
    stats_sheet: StatsSheetV1 | None,
    betting_date: str,
    db_path: str | Path | None = None,
) -> dict[str, int]:
    """Persist whichever artifacts are available for one pipeline run, in one
    transaction. Safe to call once per step (DISCOVER-only, then ENRICH,
    then ANALYZE) or once at the end with everything at hand."""
    with get_db(db_path or default_db_path()) as conn:
        fixture_ids = persist_event_list(event_list, conn)
        if dossier_list is not None:
            dossiers_by_id = {d.event_id: d for d in dossier_list.dossiers}
            for event_id, fixture_id in fixture_ids.items():
                dossier = dossiers_by_id.get(event_id)
                if dossier is not None:
                    persist_event_dossier(
                        dossier, fixture_id, betting_date, conn, run_id=dossier_list.run_id
                    )
        if stats_sheet is not None:
            persist_stats_sheet(stats_sheet, fixture_ids, betting_date, conn)
    return fixture_ids
