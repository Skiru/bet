"""The SETTLE stage, and the loop it closes (F53).

Before it existed the pipeline ran BOARD -> RESOLVE -> OFFER -> SAMPLES ->
SHEET -> COUPON and never looked back. `sofa_settled_row` had one writer,
`run_backfill`, which replays cached events and so writes ``market_p = NULL``
by construction. `fit_k_price` selects on ``market_p IS NOT NULL``, so its
input was empty and could never fill — which is why every row of every sheet
carried ``UNFITTED_CONSTANTS: K_PRICE``, permanently.
"""

import pytest

from bet.sofa.db import get_connection, migrate
from bet.sofa.settle import SettledRow, insert_settled_rows


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "sofa.db")
    migrate(path)
    return path


def _row(**over):
    base = dict(
        run_date="2026-09-18",
        sofascore_event_id=16363649,
        sport="football",
        competition_id=17,
        market="corners_1h_total",
        subject="",
        line=3.5,
        direction="OVER",
        sample_size=20,
        sample_mean=5.05,
        sample_sd=2.1,
        p_central=0.7465,
        p_bar=0.7387,
        market_p=0.7233,
        actual_value=5.0,
        outcome="WIN",
        settled_at="2026-09-18T21:00:00+00:00",
        ladder_sigma=0.4,
        offered_odds=1.33,
        verdict="BELOW_BAR",
    )
    base.update(over)
    return SettledRow(**base)


def test_a_settled_row_keeps_the_price_it_was_offered_at(db):
    with get_connection(db) as conn:
        assert insert_settled_rows(conn, [_row()]) == 1
        got = conn.execute(
            "SELECT offered_odds, verdict, market_p, ladder_sigma FROM sofa_settled_row"
        ).fetchone()
    assert got["offered_odds"] == pytest.approx(1.33)
    assert got["verdict"] == "BELOW_BAR"
    assert got["market_p"] == pytest.approx(0.7233)
    assert got["ladder_sigma"] == pytest.approx(0.4)


def test_the_fitter_can_now_see_a_priced_row(db):
    """`fit_k_price`'s WHERE clause, as the reason this stage exists."""
    with get_connection(db) as conn:
        insert_settled_rows(conn, [_row()])
        priced = conn.execute(
            "SELECT COUNT(*) c FROM sofa_settled_row "
            "WHERE outcome IN ('WIN','LOSS') AND market_p IS NOT NULL"
        ).fetchone()["c"]
    assert priced == 1


def test_settling_the_same_day_twice_inserts_nothing_new(db):
    with get_connection(db) as conn:
        assert insert_settled_rows(conn, [_row()]) == 1
        assert insert_settled_rows(conn, [_row()]) == 0
        count = conn.execute("SELECT COUNT(*) c FROM sofa_settled_row").fetchone()["c"]
        assert count == 1


def test_a_row_with_no_price_is_still_storable(db):
    """The backfill's shape must keep working through the widened writer."""
    with get_connection(db) as conn:
        assert (
            insert_settled_rows(
                conn, [_row(market_p=None, offered_odds=None, verdict=None)]
            )
            == 1
        )


def test_migrate_is_idempotent_over_the_new_columns(db):
    migrate(db)
    migrate(db)
    with get_connection(db) as conn:
        names = {r["name"] for r in conn.execute("PRAGMA table_info(sofa_settled_row)")}
    assert {"offered_odds", "verdict", "ladder_sigma"} <= names


# --- which side a per-team row settles against ---------------------------


def _fixture():
    return {"home_name": "SC Verl", "away_name": "FC Würzburger Kickers"}


def test_a_bare_club_name_still_finds_its_side():
    """Superbet writes "Verl", Sofascore writes "SC Verl" — 72.7 on a bare
    ratio, and 738 of the 2026-09-18 sheet's 4,492 per-team rows are like it."""
    from scripts.sofa.run_settle import _subject_is_home

    assert _subject_is_home("verl", _fixture()) is True
    assert _subject_is_home("wurzburger kickers", _fixture()) is False


def test_a_subject_naming_neither_side_is_refused_not_guessed():
    from scripts.sofa.run_settle import _subject_is_home

    assert _subject_is_home("borussia dortmund", _fixture()) is None


def test_a_derived_markets_side_marker_is_refused():
    from scripts.sofa.run_settle import _subject_is_home

    for marker in ("1", "2", "__draw__"):
        assert _subject_is_home(marker, _fixture()) is None


def test_a_total_needs_no_side():
    from scripts.sofa.run_settle import _subject_is_home

    assert _subject_is_home("", _fixture()) is True


def test_two_similar_sides_are_refused_rather_than_split_on_a_rounding():
    from scripts.sofa.run_settle import _subject_is_home

    derby = {"home_name": "Córdoba CF", "away_name": "Córdoba SC"}
    assert _subject_is_home("cordoba", derby) is None


# --- a failure must not throw away what was already graded -----------------


def _sheet_row(event_id, line):
    return {
        "sofascore_event_id": event_id,
        "sport": "football",
        "market": "corners_total",
        "subject": "",
        "line": line,
        "direction": "OVER",
        "sample_size": 10,
        "sample_mean": 10.0,
        "sample_sd": 2.0,
        "centre": 10.0,
        "p_central": 0.6,
        "market_p": 0.55,
        "ladder_centre": 9.4,
        "ladder_sigma": 0.3,
        "p_bar": 0.58,
        "bar_reason": "none",
        "calibration_correction": 0.0,
        "required_odds": 1.9,
        "offered_odds": 1.88,
        "edge": 0.05,
        "surplus": -0.02,
        "verdict": "BELOW_BAR",
        "notes": [],
    }


def _fixture_json(event_id):
    return {
        "sofascore_event_id": event_id,
        "superbet_event_ids": ["S1"],
        "sport": "football",
        "kickoff_utc": "2026-09-18T18:30:00Z",
        "home_name": "Home FC",
        "away_name": "Away FC",
        "home_entity_id": 1,
        "away_entity_id": 2,
        "competition_name": "L",
        "competition_id": 1,
        "season_id": 1,
        "category_name": "C",
        "identity": "CONFIRMED",
        "round_number": None,
        "round_name": None,
        "cup_round_type": None,
        "previous_leg_event_id": None,
        "venue_name": None,
        "referee": None,
        "ground_type": None,
        "default_period_count": 2,
        "superbet_kickoff_utc": "2026-09-18T18:30:00Z",
        "kickoff_disagreement_h": 0.0,
    }


def test_a_crash_partway_keeps_the_rows_already_graded(tmp_path, monkeypatch):
    """F15 applied to SETTLE: the insert used to sit after the loop.

    One malformed payload and a whole evening of fetches was thrown away, with
    the day left looking unsettled rather than partly settled.
    """
    import json as _json

    import scripts.sofa.run_settle as stage

    date_dir = tmp_path / "2026-09-18"
    date_dir.mkdir()
    (date_dir / "05_sheet.json").write_text(
        _json.dumps([_sheet_row(11, 9.5), _sheet_row(22, 9.5)])
    )
    (date_dir / "02_fixtures.json").write_text(
        _json.dumps([_fixture_json(11), _fixture_json(22)])
    )

    good = (
        {
            "id": 11,
            "status": {"code": 100, "type": "finished"},
            "homeTeam": {"name": "Home FC"},
            "awayTeam": {"name": "Away FC"},
            "tournament": {"uniqueTournament": {"id": 7}},
        },
        {"ALL": {"cornerKicks": (6.0, 5.0)}},
        None,
    )

    def fake_payload(client, cache, event_id):
        if event_id == 11:
            return good
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(stage, "_event_payload", fake_payload)
    monkeypatch.setattr(stage, "extract_flat_statistics", lambda s: s)
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("SOFA_DB_PATH", str(tmp_path / "sofa.db"))
    monkeypatch.setattr("sys.argv", ["run_settle", "--date", "2026-09-18"])

    with pytest.raises(RuntimeError):
        stage.main()

    with get_connection(str(tmp_path / "sofa.db")) as conn:
        rows = conn.execute(
            "SELECT sofascore_event_id, actual_value, outcome FROM sofa_settled_row"
        ).fetchall()
    assert [r["sofascore_event_id"] for r in rows] == [11]
    assert rows[0]["actual_value"] == pytest.approx(11.0)
    assert rows[0]["outcome"] == "WIN"


def test_a_backfill_can_grade_the_rows_that_carried_no_price():
    """--include-unpriced widens SETTLE from the priced part to the whole board.

    The default is priced-only because K_PRICE is fitted on `market_p`, which
    only a quoted row has. But on 2026-09-19 the sheet held 56,528 rows and
    only 54,834 carried a price: 1,694 forecasts we made and stand behind were
    unaccounted for by construction. An audit that has to say what happened to
    every market considered cannot be run off the priced subset.
    """
    from scripts.sofa.run_settle import rows_to_consider

    sheet = [
        {"market": "corners_total", "offered_odds": 1.85},
        {"market": "cards_total", "offered_odds": None},
        {"market": "goals_total"},
    ]

    assert len(rows_to_consider(sheet, include_unpriced=False)) == 1
    assert len(rows_to_consider(sheet, include_unpriced=True)) == 3


def test_widening_the_selection_does_not_reorder_or_mutate_the_sheet():
    from scripts.sofa.run_settle import rows_to_consider

    sheet = [{"market": "a", "offered_odds": 2.0}, {"market": "b"}]
    got = rows_to_consider(sheet, include_unpriced=True)
    assert [r["market"] for r in got] == ["a", "b"]
    assert got is not sheet
