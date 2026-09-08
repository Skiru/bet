"""Do corners/cards/shots/fouls/offsides halves actually sum to their total?

Goals' half split is guarded (``half_time_is_possible``, tested in
``test_regression_2026_09_08_one_row_one_sample.py``) because it is derived by
*subtraction* from the full-time score. Corners, cards, shots, fouls and
offsides are built a different way -- ``_bzzoiro_match_stats`` sums rows the
payload already tags ``"<stat>_1h"``/``"<stat>_2h"``, independently of the
full-match row -- so there is no subtraction to protect and, until this audit
script, no check that bzzoiro's own halves agree with its own total for these
five markets at all.

**Measured 2026-09-08** by ``scripts/simple/audit_half_totals.py`` against
every dossier on disk at the time (``runs/2026-08-25`` through
``runs/2026-09-07``, the plain dated run directories only): 29,441 checks,
deduplicated by ``(market, granularity, match_id)``, found 417 mismatches --
0.91% (corners_for) to 2.21% (offsides_total) per market, 1.42% pooled. That
is the same order of magnitude as the unverified claim this audit was written
to check ("0.2-1.3% of matches"), a little above its upper end on
``cards_total`` and ``offsides_total`` specifically, and nowhere near the
0/10,173 goals gets from its subtraction guard.

This is left unfixed on purpose, not silently: nothing downstream reads these
five markets' halves today (``analyze.py``'s ``_MARKET_STAT_TO_CANONICAL``
maps only ``goals_1h``/``goals_2h``; ``market_ranking.py`` keeps the rest
dossier-only), so a bad split cannot reach a priced row. See the comment next
to ``half_time_is_possible`` in ``providers.py`` for what to do before that
stops being true.

The tests below pin the *script's own arithmetic* (synthetic input, so they
cannot go flaky as ``runs/`` grows or shrinks) rather than the measured rate
itself -- ``runs/`` is gitignored and not present in CI, and a threshold
fitted to one day's slate count would be exactly the kind of overfit
``sample_drift.json``'s docstring already argues against. The numbers above
are the record of what this script found on real data the day it was written.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "simple" / "audit_half_totals.py"


def _module():
    spec = importlib.util.spec_from_file_location("audit_half_totals", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def audit():
    return _module()


def _dossier(sport, metrics):
    return {"sport": sport, "metrics": metrics}


def _metric(rows_by_sample):
    """One metric's payload shape: ``{sample_name: [row, ...]}``."""
    return dict(rows_by_sample)


def _row(match_id, value, provider="bzzoiro"):
    return {"match_id": match_id, "value": value, "provider": provider}


class TestCollect:
    def test_a_matching_split_is_not_a_mismatch(self, audit, tmp_path) -> None:
        payload = {
            "dossiers": [
                _dossier("football", {
                    "corners_total": _metric({"team_a_l10": [_row("m1", 10.0)]}),
                    "corners_1h_total": _metric({"team_a_l10": [_row("m1", 4.0)]}),
                    "corners_2h_total": _metric({"team_a_l10": [_row("m1", 6.0)]}),
                })
            ]
        }
        run_dir = tmp_path / "2026-09-08"
        run_dir.mkdir()
        (run_dir / "2026-09-08_event_dossiers.json").write_text(__import__("json").dumps(payload))

        seen = audit.collect(tmp_path)
        rows = audit.report(seen)
        row = next(r for r in rows if r["market"] == "corners" and r["granularity"] == "total")
        assert row["checks"] == 1
        assert row["mismatches"] == 0

    def test_a_split_that_does_not_sum_is_a_mismatch(self, audit, tmp_path) -> None:
        payload = {
            "dossiers": [
                _dossier("football", {
                    "cards_total": _metric({"h2h": [_row("m2", 6.0)]}),
                    "cards_1h_total": _metric({"h2h": [_row("m2", 0.0)]}),
                    "cards_2h_total": _metric({"h2h": [_row("m2", 3.0)]}),
                })
            ]
        }
        run_dir = tmp_path / "2026-09-08"
        run_dir.mkdir()
        (run_dir / "2026-09-08_event_dossiers.json").write_text(__import__("json").dumps(payload))

        seen = audit.collect(tmp_path)
        rows = audit.report(seen)
        row = next(r for r in rows if r["market"] == "cards" and r["granularity"] == "total")
        assert row["checks"] == 1
        assert row["mismatches"] == 1
        assert row["examples"] == [("m2", 6.0, 0.0, 3.0)]

    def test_a_non_bzzoiro_row_is_ignored(self, audit, tmp_path) -> None:
        """The 1h/2h split is bzzoiro-only; another provider's row under the
        same metric name must not be read as a half-split observation."""
        payload = {
            "dossiers": [
                _dossier("football", {
                    "fouls_total": _metric({"team_a_l10": [_row("m3", 20.0, provider="espn-football")]}),
                    "fouls_1h_total": _metric({"team_a_l10": []}),
                    "fouls_2h_total": _metric({"team_a_l10": []}),
                })
            ]
        }
        run_dir = tmp_path / "2026-09-08"
        run_dir.mkdir()
        (run_dir / "2026-09-08_event_dossiers.json").write_text(__import__("json").dumps(payload))

        seen = audit.collect(tmp_path)
        assert seen.get(("fouls", "total"), {}) == {}

    def test_a_tennis_dossier_is_skipped(self, audit, tmp_path) -> None:
        payload = {
            "dossiers": [
                _dossier("tennis", {
                    "corners_total": _metric({"team_a_l10": [_row("m4", 10.0)]}),
                    "corners_1h_total": _metric({"team_a_l10": [_row("m4", 4.0)]}),
                    "corners_2h_total": _metric({"team_a_l10": [_row("m4", 5.0)]}),
                })
            ]
        }
        run_dir = tmp_path / "2026-09-08"
        run_dir.mkdir()
        (run_dir / "2026-09-08_event_dossiers.json").write_text(__import__("json").dumps(payload))

        seen = audit.collect(tmp_path)
        assert seen.get(("corners", "total"), {}) == {}

    def test_merged_and_prerun_variant_directories_are_not_read(self, audit, tmp_path) -> None:
        """Only ``runs/YYYY-MM-DD/`` counts. The repo also carries re-saved
        snapshots of a handful of dates under names like
        ``2026-09-04_step4_merged`` -- reading those too would count the same
        underlying match several times under different directory names."""
        payload = {
            "dossiers": [
                _dossier("football", {
                    "shots_total": _metric({"h2h": [_row("m5", 10.0)]}),
                    "shots_1h_total": _metric({"h2h": [_row("m5", 4.0)]}),
                    "shots_2h_total": _metric({"h2h": [_row("m5", 5.0)]}),
                })
            ]
        }
        variant_dir = tmp_path / "2026-09-08_step2_merged"
        variant_dir.mkdir()
        (variant_dir / "2026-09-08_event_dossiers.json").write_text(__import__("json").dumps(payload))

        seen = audit.collect(tmp_path)
        assert seen.get(("shots", "total"), {}) == {}

    def test_a_later_dated_directory_overrides_an_earlier_reading_of_the_same_match(
        self, audit, tmp_path
    ) -> None:
        import json as _json

        early = {
            "dossiers": [
                _dossier("football", {
                    "offsides_total": _metric({"team_a_l10": [_row("m6", 3.0)]}),
                    "offsides_1h_total": _metric({"team_a_l10": [_row("m6", 1.0)]}),
                    "offsides_2h_total": _metric({"team_a_l10": [_row("m6", 1.0)]}),  # mismatch
                })
            ]
        }
        late = {
            "dossiers": [
                _dossier("football", {
                    "offsides_total": _metric({"team_a_l10": [_row("m6", 3.0)]}),
                    "offsides_1h_total": _metric({"team_a_l10": [_row("m6", 1.0)]}),
                    "offsides_2h_total": _metric({"team_a_l10": [_row("m6", 2.0)]}),  # corrected
                })
            ]
        }
        (tmp_path / "2026-09-01").mkdir()
        (tmp_path / "2026-09-01" / "2026-09-01_event_dossiers.json").write_text(_json.dumps(early))
        (tmp_path / "2026-09-07").mkdir()
        (tmp_path / "2026-09-07" / "2026-09-07_event_dossiers.json").write_text(_json.dumps(late))

        seen = audit.collect(tmp_path)
        assert seen[("offsides", "total")]["m6"] == (3.0, 1.0, 2.0)


class TestReportAndMain:
    def test_report_is_empty_for_no_checkable_pairs(self, audit) -> None:
        assert audit.report({}) == []

    def test_main_exits_zero_without_check_even_with_mismatches(self, audit, tmp_path, capsys) -> None:
        import json as _json
        import sys as _sys

        payload = {
            "dossiers": [
                _dossier("football", {
                    "cards_total": _metric({"h2h": [_row("m7", 6.0)]}),
                    "cards_1h_total": _metric({"h2h": [_row("m7", 0.0)]}),
                    "cards_2h_total": _metric({"h2h": [_row("m7", 3.0)]}),
                })
            ]
        }
        run_dir = tmp_path / "2026-09-08"
        run_dir.mkdir()
        (run_dir / "2026-09-08_event_dossiers.json").write_text(_json.dumps(payload))

        argv = _sys.argv
        try:
            _sys.argv = ["audit_half_totals.py", "--runs-dir", str(tmp_path)]
            code = audit.main()
        finally:
            _sys.argv = argv
        assert code == 0

    def test_main_exits_one_with_check_when_mismatches_exist(self, audit, tmp_path) -> None:
        import json as _json
        import sys as _sys

        payload = {
            "dossiers": [
                _dossier("football", {
                    "cards_total": _metric({"h2h": [_row("m8", 6.0)]}),
                    "cards_1h_total": _metric({"h2h": [_row("m8", 0.0)]}),
                    "cards_2h_total": _metric({"h2h": [_row("m8", 3.0)]}),
                })
            ]
        }
        run_dir = tmp_path / "2026-09-08"
        run_dir.mkdir()
        (run_dir / "2026-09-08_event_dossiers.json").write_text(_json.dumps(payload))

        argv = _sys.argv
        try:
            _sys.argv = ["audit_half_totals.py", "--check", "--runs-dir", str(tmp_path)]
            code = audit.main()
        finally:
            _sys.argv = argv
        assert code == 1
