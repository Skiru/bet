"""Tests for bet.simple_stats.persistence: idempotent DB writes, tennis fixtures.

Uses the root conftest.py's `db_with_sports` fixture (in-memory SQLite,
schema initialized, sports seeded).
"""
from bet.simple_stats.contracts import (
    EventDossierV1,
    EventListV1,
    EventRecord,
    MetricObservation,
    ProviderValue,
    StatsSheetRow,
    StatsSheetV1,
)
from bet.simple_stats.persistence import (
    fixture_ids_by_event_id,
    persist_event_dossier,
    persist_event_list,
    persist_stats_sheet,
)


def _football_event(event_id="evt1"):
    return EventRecord(
        event_id=event_id,
        sport="football",
        competition="Test League",
        home_team="Team A",
        away_team="Team B",
        start_time="2026-08-25T18:00:00+00:00",
        source_ids={"odds-api": "1"},
        identity_confidence="CONFIRMED",
        status="ACTIVE",
    )


def _tennis_event(event_id="evt2"):
    return EventRecord(
        event_id=event_id,
        sport="tennis",
        competition="ATP Test Open",
        player_one="Player One",
        player_two="Player Two",
        start_time="2026-08-25T18:00:00+00:00",
        source_ids={"odds-api": "2"},
        identity_confidence="CONFIRMED",
        status="ACTIVE",
    )


def _dossier(event_id="evt1"):
    return EventDossierV1(
        event_id=event_id,
        sport="football",
        metrics={
            "corners_total": MetricObservation(
                canonical_name="corners_total",
                team_a_l10=[
                    ProviderValue(
                        provider="espn-football",
                        match_id="m1",
                        match_date="2026-01-01",
                        opponent="X",
                        value=9.0,
                        observed_at="2026-01-01T00:00:00+00:00",
                    )
                ],
            )
        },
        readiness="PARTIAL",
        data_gaps=[],
    )


def _stats_sheet(event_id="evt1"):
    return StatsSheetV1(
        generated_at="x",
        rows=[
            StatsSheetRow(
                event_id=event_id,
                sport="football",
                market="corners_total",
                line=9.5,
                direction="OVER",
                hits=1,
                sample_size=1,
                hit_rate=1.0,
                p_low=0.2065,
                mean=9.0,
                median=9.0,
                sources=["espn-football"],
                cross_provider_agreement="SINGLE_SOURCE",
                confidence="LOW",
                data_quality="PARTIAL",
            )
        ],
    )


def test_rerun_is_idempotent(db_with_sports):
    conn = db_with_sports
    event_list = EventListV1(generated_at="x", date="2026-08-25", sports=["football"], events=[_football_event()])

    fixture_ids_1 = persist_event_list(event_list, conn)
    fixture_ids_2 = persist_event_list(event_list, conn)
    conn.commit()

    assert fixture_ids_1 == fixture_ids_2
    assert conn.execute("SELECT COUNT(*) AS c FROM fixtures").fetchone()["c"] == 1

    fixture_id = fixture_ids_1["evt1"]
    dossier = _dossier()
    persist_event_dossier(dossier, fixture_id, "2026-08-25", conn)
    persist_event_dossier(dossier, fixture_id, "2026-08-25", conn)
    conn.commit()
    assert conn.execute("SELECT COUNT(*) AS c FROM analysis_raw_data").fetchone()["c"] == 1

    stats_sheet = _stats_sheet()
    persist_stats_sheet(stats_sheet, fixture_ids_1, "2026-08-25", conn)
    persist_stats_sheet(stats_sheet, fixture_ids_1, "2026-08-25", conn)
    conn.commit()
    assert conn.execute("SELECT COUNT(*) AS c FROM analysis_results").fetchone()["c"] == 1


def test_tennis_dossier_persists_without_team_id(db_with_sports):
    conn = db_with_sports
    event_list = EventListV1(generated_at="x", date="2026-08-25", sports=["tennis"], events=[_tennis_event()])

    fixture_ids = persist_event_list(event_list, conn)
    conn.commit()

    fixture_id = fixture_ids["evt2"]
    row = conn.execute(
        "SELECT home_team_id, away_team_id FROM fixtures WHERE id = ?", (fixture_id,)
    ).fetchone()
    assert row["home_team_id"] is not None
    assert row["away_team_id"] is not None

    names = conn.execute(
        "SELECT name FROM teams WHERE id IN (?, ?)", (row["home_team_id"], row["away_team_id"])
    ).fetchall()
    assert {r["name"] for r in names} == {"Player One", "Player Two"}

    # the dossier itself must persist through analysis_raw_data with no
    # team_id anywhere in the payload (section 8's decision)
    dossier = _dossier(event_id="evt2")
    persist_event_dossier(dossier, fixture_id, "2026-08-25", conn)
    conn.commit()
    assert conn.execute("SELECT COUNT(*) AS c FROM analysis_raw_data").fetchone()["c"] == 1


def test_fixture_ids_by_event_id_looks_up_persisted_fixtures(db_with_sports):
    conn = db_with_sports
    event_list = EventListV1(generated_at="x", date="2026-08-25", sports=["football"], events=[_football_event()])
    fixture_ids = persist_event_list(event_list, conn)
    conn.commit()

    assert fixture_ids_by_event_id(conn, {"evt1"}) == fixture_ids


# --- The tipster column has to survive the trip into analysis_results ---------
#
# bet-analyst is instructed to cross-check the DB for other run_ids of the same
# day, so a row reachable only there would otherwise lose the column that the
# artifact shows.


def test_ranking_json_carries_the_tipster_column_when_present():
    from bet.simple_stats.contracts import StatsSheetRow, TipsterColumn
    from bet.simple_stats.persistence import _stats_row_to_dict

    row = StatsSheetRow(
        event_id="EV1", sport="football", market="corners_total", line=10.5,
        direction="UNDER", hits=9, sample_size=12, hit_rate=0.75, p_low=0.4677, mean=9.0, median=9.0,
        sources=["espn-football"], cross_provider_agreement="AGREE", confidence="HIGH",
        data_quality="READY",
        tipster=TipsterColumn(verdict="CONFIRMS", agree=2, oppose=0, considered=5, sources=["zawodtyper"]),
    )
    payload = _stats_row_to_dict(row)
    assert payload["tipster"]["verdict"] == "CONFIRMS"
    assert payload["tipster"]["agree"] == 2


def test_ranking_json_omits_the_key_entirely_when_no_tipster_ran():
    """Not a null: a null reads as "checked, nobody agreed", which is a different
    statement from "this column was never populated"."""
    from bet.simple_stats.contracts import StatsSheetRow
    from bet.simple_stats.persistence import _stats_row_to_dict

    row = StatsSheetRow(
        event_id="EV1", sport="football", market="corners_total", line=10.5,
        direction="UNDER", hits=9, sample_size=12, hit_rate=0.75, p_low=0.4677, mean=9.0, median=9.0,
        sources=["espn-football"], cross_provider_agreement="AGREE", confidence="HIGH",
        data_quality="READY",
    )
    assert "tipster" not in _stats_row_to_dict(row)
