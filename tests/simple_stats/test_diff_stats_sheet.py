"""scripts/simple/diff_stats_sheet.py -- the Faza 0 safety net from
docs/PLAN_BOGATE_STATYSTYKI.md. Every later phase changes the stats sheet's
row count, so this script (and the frozen fixture + baseline it reads) is
what tells an intended change apart from an accidental regression.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "simple_stats"


def _load_module():
    path = ROOT / "scripts" / "simple" / "diff_stats_sheet.py"
    spec = importlib.util.spec_from_file_location("_diff_stats_sheet", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def diff_mod():
    return _load_module()


def test_the_frozen_fixture_replays_clean_against_its_recorded_baseline(diff_mod):
    """This is Faza 0's own acceptance test: on unchanged code, replaying
    ANALYZE over the frozen dossier must reproduce the recorded baseline
    exactly -- no added, removed or changed row."""
    dossier_list = diff_mod.EventDossierListV1.model_validate_json(
        (FIXTURES / "dossiers_2026-08-31.json").read_text(encoding="utf-8")
    )
    baseline = diff_mod.StatsSheetV1.model_validate_json(
        (FIXTURES / "stats_sheet_baseline_2026-08-31.json").read_text(encoding="utf-8")
    )
    current = diff_mod.analyze_dossiers(dossier_list)
    diff = diff_mod.diff_sheets(baseline, current)
    assert diff == {"added": [], "removed": [], "changed": []}


def test_added_removed_and_changed_rows_are_each_reported(diff_mod):
    row = dict(
        event_id="evt-1", sport="football", market="corners_total", line=8.5,
        direction="OVER", hits=7, sample_size=10, hit_rate=0.7, p_low=0.42,
        mean=9.8, median=10.0, sources=["bzzoiro"],
        cross_provider_agreement="SINGLE_SOURCE", confidence="MEDIUM",
        data_quality="PARTIAL",
    )
    from bet.simple_stats.contracts import StatsSheetRow, StatsSheetV1

    def _sheet(*rows):
        return StatsSheetV1(
            run_id="RID-1", date="2026-08-31",
            generated_at="2026-08-31T00:00:00+00:00", rows=list(rows),
        )

    unchanged = StatsSheetRow(**row)
    removed_only_in_baseline = StatsSheetRow(**{**row, "line": 9.5})
    added_only_in_current = StatsSheetRow(**{**row, "line": 10.5})
    changed_in_current = StatsSheetRow(**{**row, "market": "total_games", "p_low": 0.55})
    changed_in_baseline = StatsSheetRow(**{**row, "market": "total_games", "p_low": 0.30})

    baseline = _sheet(unchanged, removed_only_in_baseline, changed_in_baseline)
    current = _sheet(unchanged, added_only_in_current, changed_in_current)

    diff = diff_mod.diff_sheets(baseline, current)
    assert diff["added"] == [diff_mod._row_key(added_only_in_current)]
    assert diff["removed"] == [diff_mod._row_key(removed_only_in_baseline)]
    assert diff["changed"] == [diff_mod._row_key(changed_in_current)]


def test_a_duplicate_key_is_a_hard_error_not_a_silent_overwrite(diff_mod):
    """Two rows sharing (event_id, market, line, direction, team_name,
    player_name) would mean analyze_dossiers emitted two rows for the same
    bet -- a bug the diff must surface, not hide by keeping whichever came
    last in the list."""
    row = dict(
        event_id="evt-1", sport="football", market="corners_total", line=8.5,
        direction="OVER", hits=7, sample_size=10, hit_rate=0.7, p_low=0.42,
        mean=9.8, median=10.0, sources=["bzzoiro"],
        cross_provider_agreement="SINGLE_SOURCE", confidence="MEDIUM",
        data_quality="PARTIAL",
    )
    from bet.simple_stats.contracts import StatsSheetRow, StatsSheetV1

    dupe_sheet = StatsSheetV1(
        run_id="RID-1", date="2026-08-31", generated_at="2026-08-31T00:00:00+00:00",
        rows=[StatsSheetRow(**row), StatsSheetRow(**{**row, "p_low": 0.60})],
    )
    with pytest.raises(ValueError, match="duplicate stats-sheet row"):
        diff_mod._index(dupe_sheet)


# docs/PLAN_BOGATE_STATYSTYKI.md 3bis.1: the BET_MARKETS_PROFILE=legacy
# rollback switch.


@pytest.fixture(autouse=True)
def _clear_markets_profile_env():
    os.environ.pop("BET_MARKETS_PROFILE", None)
    yield
    os.environ.pop("BET_MARKETS_PROFILE", None)


def test_the_frozen_fixture_replays_clean_under_legacy_profile_too(diff_mod):
    """The rollback switch's own acceptance test (3bis.1): with
    BET_MARKETS_PROFILE=legacy, replaying ANALYZE over the same frozen
    dossier must reproduce the pre-plan market/line grid exactly -- a
    strictly smaller sheet than the v2 baseline, byte-stable on its own."""
    os.environ["BET_MARKETS_PROFILE"] = "legacy"
    dossier_list = diff_mod.EventDossierListV1.model_validate_json(
        (FIXTURES / "dossiers_2026-08-31.json").read_text(encoding="utf-8")
    )
    baseline = diff_mod.StatsSheetV1.model_validate_json(
        (FIXTURES / "stats_sheet_baseline_legacy_2026-08-31.json").read_text(encoding="utf-8")
    )
    current = diff_mod.analyze_dossiers(dossier_list)
    diff = diff_mod.diff_sheets(baseline, current)
    assert diff == {"added": [], "removed": [], "changed": []}
    # Faza 2 alone added 288 rows over this same frozen fixture (see
    # docs/PLAN_BOGATE_STATYSTYKI.md's own log); legacy must not carry them.
    assert len(current.rows) == 618


def test_legacy_profile_produces_a_strict_subset_of_v2_markets(diff_mod):
    """None of the plan's new markets (goals, half-time splits, offsides,
    red cards, shots total, team goals) may leak into legacy -- the whole
    point of the switch is that a betting day can run as if the plan never
    shipped."""
    dossier_list = diff_mod.EventDossierListV1.model_validate_json(
        (FIXTURES / "dossiers_2026-08-31.json").read_text(encoding="utf-8")
    )

    os.environ["BET_MARKETS_PROFILE"] = "legacy"
    legacy_markets = {row.market for row in diff_mod.analyze_dossiers(dossier_list).rows}

    os.environ["BET_MARKETS_PROFILE"] = "v2"
    v2_markets = {row.market for row in diff_mod.analyze_dossiers(dossier_list).rows}

    assert legacy_markets <= v2_markets
    # goals_total is real in v2 (Faza 1) but this frozen fixture predates the
    # provider change that collects it, so it is absent from *both* profiles
    # here -- shots_total/offsides_total/red_cards_total are Faza 2 markets on
    # metrics the fixture already carries, so they are the ones that actually
    # move between profiles on this fixture.
    assert "shots_total" not in legacy_markets
    assert "shots_total" in v2_markets


def test_the_cli_profile_flag_picks_the_legacy_default_baseline(diff_mod, capsys):
    """--profile legacy with no explicit --baseline must diff against the
    dedicated legacy fixture, not the v2 one -- otherwise every row the plan
    added would show up as a false REMOVED."""
    argv = ["diff_stats_sheet.py", "--profile", "legacy"]
    import sys

    original_argv = sys.argv
    sys.argv = argv
    try:
        exit_code = diff_mod.main()
    finally:
        sys.argv = original_argv

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "stats_sheet_baseline_legacy_2026-08-31.json" in out
