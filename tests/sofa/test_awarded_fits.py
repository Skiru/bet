"""Every football fit carries AWARDED_EXCLUDED the way SAMPLES / SHEET read
it from 2026-10-30 (review 2026-10-29 round 2): the replay drops an awarded
result before one listing per match is chosen (a match listed played and
awarded keeps its played copy; any sport, as SAMPLES' admit); the 1X2 / DNB
fit, the count-dispersion cases and the incident fits take the flag and
refuse a cache written under the other rule; every fit records the flag in
its `fitted_from`; prepare_refit warns on a stretch file fitted with the
forfeits in. Offline."""

from __future__ import annotations

import argparse
import gzip
import pickle
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import football_rating as fr
from scripts.sofa import calibrate_from_cache as cfc
from scripts.sofa import fit_incident_set_curves as fisc
from scripts.sofa import fit_result_1x2_dnb_curve as f1x2
from scripts.sofa import measure_count_families as mcf
from scripts.sofa import prepare_refit as pr
from tests.sofa.test_cache_replay_holds_slim_events import _db, _event
from tests.sofa.test_refit_replay_switch_guard import _cfg, _staged

REPO = Path(__file__).resolve().parents[2]
ON = {"closeness_stretch": True, "player_coverage": True, "awarded_excluded": True}


def _awarded(e: dict[str, Any]) -> dict[str, Any]:
    return {**e, "isAwarded": True}


def test_a_match_listed_played_and_awarded_keeps_its_played_copy(
    tmp_path: Path,
) -> None:
    played = _event(1)
    # the same match (names, day) under another id, the newer copy awarded
    twin = _awarded({**_event(1), "id": 2})
    db = _db(tmp_path, "a.db", [played, twin])
    assert [p.event_id for p in cfc.load_cache(db, awarded_out=True)] == [1]


def test_the_replay_drops_an_awarded_result_of_any_sport_as_samples(
    tmp_path: Path,
) -> None:
    def tennis(eid: int) -> dict[str, Any]:
        return {**_event(eid, "tennis"), "winnerCode": 1,
                "homeScore": {"current": 2, "period1": 6, "period2": 6},
                "awayScore": {"current": 0, "period1": 3, "period2": 4}}

    db = _db(tmp_path, "a.db", [tennis(1), _awarded(tennis(300_000))])
    assert [p.event_id for p in cfc.load_cache(db, tennis_sets=True)] == [1, 300_000]
    assert [p.event_id for p in cfc.load_cache(
        db, tennis_sets=True, awarded_out=True)] == [1]


def _history(tmp_path: Path) -> Path:
    rows = [fr.FootballResult(1, 1_780_000_000, 5, 11, 12, {"goals_for": (1, 0)}),
            fr.FootballResult(2, 1_780_100_000, 5, 11, 13, {"goals_for": (3, 0)},
                              awarded=True)]
    path = tmp_path / "football_history.pkl"
    path.write_bytes(pickle.dumps(("fp", rows)))
    return path


def test_the_1x2_fit_drops_awarded_and_refuses_a_cache_of_the_other_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[int]] = []

    def replay(history: list[fr.FootballResult], *_: Any) -> list[Any]:
        seen.append([r.event_id for r in history])
        return []

    monkeypatch.setattr(f1x2, "replay", replay)
    monkeypatch.setattr(f1x2, "phases_by_event", lambda h: {})
    hist = _history(tmp_path)
    cache = tmp_path / "m.csv.gz"
    fp, _ = f1x2.load_matches(hist, 0, 2**31, cache, awarded_out=True)
    assert seen == [[1]] and fp == "fp" + f1x2.AWARDED_TAG
    with gzip.open(cache, "rt") as fh:  # no rows: the header only
        assert fh.readline().startswith("fingerprint")
    f1x2.load_matches(hist, 0, 2**31, None)
    assert seen[-1] == [1, 2]
    # a cache holding rows of one rule is refused under the other
    with gzip.open(cache, "wt") as fh:
        fh.write("fingerprint,ts,event_id,women,link,lh,la,x,y,phase\n"
                 "fp|awarded_excluded,1,1,0,LINKED,1.0,1.0,1,0,\n")
    assert len(f1x2.load_matches(hist, 0, 2**31, cache, awarded_out=True)[1]) == 1
    with pytest.raises(SystemExit, match="awarded-excluded"):
        f1x2.load_matches(hist, 0, 2**31, cache)


def test_the_incident_fits_history_follows_the_flag(tmp_path: Path) -> None:
    _, rows = pickle.loads(_history(tmp_path).read_bytes())
    on = argparse.Namespace(awarded_excluded=True)
    off = argparse.Namespace(awarded_excluded=False)
    assert [r.event_id for r in fisc._history(rows, on)] == [1]
    assert [r.event_id for r in fisc._history(rows, off)] == [1, 2]


def test_count_cases_refuse_a_played_pickle_of_the_other_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "cases"
    out.mkdir()
    (out / "played.pkl").write_bytes(pickle.dumps(([], {})))  # pre-flag: off
    ns = argparse.Namespace(out=str(out), db="x", refresh=False,
                            awarded_excluded=True)
    assert mcf.cmd_collect(ns) == 2


def test_extract_played_drops_awarded_before_one_listing(tmp_path: Path) -> None:
    db = _db(tmp_path, "a.db", [_event(1), _awarded({**_event(1), "id": 2}),
                                _awarded(_event(300_000))])
    played, _ = mcf.extract_played(db, awarded_out=True)
    assert [p.event_id for p in played] == [1]
    played, _ = mcf.extract_played(db)
    assert 300_000 in [p.event_id for p in played]


@pytest.mark.parametrize("script", [
    "fit_goals_stretch", "fit_count_stretch", "fit_closeness_stretch",
    "fit_game_state", "fit_player_stretch", "fit_joint_curves",
    "fit_double_chance_curve", "fit_result_1x2_dnb_curve",
    "fit_incident_set_curves", "fit_count_dispersion",
])
def test_every_football_fit_records_the_flag(script: str) -> None:
    src = (REPO / "scripts" / "sofa" / f"{script}.py").read_text()
    assert "--awarded-excluded" in src
    assert re.search(r'"awarded_excluded":', src), script


def test_prepare_refit_warns_on_a_stretch_fitted_with_forfeits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(epochs, "AWARDED_EXCLUDED_FROM_UTC",
                        datetime(2026, 10, 30, tzinfo=UTC))
    cfg = _cfg(tmp_path)
    (cfg / "sofa_goals_stretch.json").write_text('{"fitted_from": {}}')
    (cfg / "sofa_count_stretch.json").write_text(
        '{"fitted_from": {"awarded_excluded": true}}')
    eve = datetime(2026, 10, 29, 22, 0, tzinfo=UTC)
    refusals, warnings = pr.replay_switch_gaps(
        _staged(**ON, goals_stretch=True, count_stretch=True), at=eve,
        config_dir=cfg)
    assert refusals == []
    hits = [w for w in warnings if "awarded at the table in" in w]
    assert len(hits) == 1 and "sofa_goals_stretch.json" in hits[0]
    # the stretch not replayed: nothing to say
    _, warnings = pr.replay_switch_gaps(_staged(**ON), at=eve, config_dir=cfg)
    assert not any("awarded at the table in" in w for w in warnings)


def test_an_empty_1x2_cache_reads_under_either_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(f1x2, "replay", lambda *a: [])
    monkeypatch.setattr(f1x2, "phases_by_event", lambda h: {})
    cache = tmp_path / "m.csv.gz"
    f1x2.load_matches(_history(tmp_path), 0, 2**31, cache, awarded_out=True)
    for rule in (True, False):
        assert f1x2.load_matches(_history(tmp_path), 0, 2**31, cache,
                                 awarded_out=rule)[1] == []


def test_a_played_pickle_with_the_flag_is_refused_without_it(tmp_path: Path) -> None:
    out = tmp_path / "cases"
    out.mkdir()
    (out / "played.pkl").write_bytes(pickle.dumps(([], {}, True)))
    ns = argparse.Namespace(out=str(out), db="x", refresh=False)  # pre-flag ns: off
    assert mcf.cmd_collect(ns) == 2


def test_count_dispersion_refuses_cases_of_the_other_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.sofa import fit_count_dispersion as fcd
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "meta.json").write_text('{"names": {}, "sizes": {}}')  # pre-flag
    monkeypatch.setattr("sys.argv", ["fit_count_dispersion.py", "--before",
                                     "2026-10-30", "--cases", str(cases),
                                     "--awarded-excluded"])
    assert fcd.main() == 2


def test_double_chance_regate_cannot_change_the_rule(tmp_path: Path) -> None:
    from scripts.sofa import fit_double_chance_curve as fdc
    (tmp_path / "curves.json").write_text('{"fitted_from": {}}')
    ns = argparse.Namespace(awarded_excluded=True)
    assert fdc.regate(tmp_path, ns) == 2


def test_prepare_refit_warns_on_count_dispersion_fitted_with_forfeits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(epochs, "AWARDED_EXCLUDED_FROM_UTC",
                        datetime(2026, 10, 30, tzinfo=UTC))
    cfg = _cfg(tmp_path)
    (cfg / "sofa_count_dispersion.json").write_text('{"fitted_from": {}}')
    _, warnings = pr.replay_switch_gaps(
        _staged(**ON, count_dispersion=True),
        at=datetime(2026, 10, 29, 22, 0, tzinfo=UTC), config_dir=cfg)
    assert any("sofa_count_dispersion.json" in w for w in warnings)
