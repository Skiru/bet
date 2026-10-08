"""The fitted football count dispersion (epochs.COUNT_DISPERSION_FROM_UTC, off).

Switch off: every function behaves byte for byte as before (golden values
computed from the code as it was before the change,
tests/sofa/golden/count_estimator_pre_dispersion.json). Switch on: the fitted
alpha prices the row, with the stated fallbacks. Offline.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from bet.sofa import count_dispersion as cd
from bet.sofa import engine, epochs
from bet.sofa.engine import (
    calc_p_central_nb_raw,
    calc_p_central_raw,
    sheet_count_p_raw,
    sheet_predictive_sd,
    support_floor_for,
)
from scripts.sofa import calibrate_from_cache as cc
from scripts.sofa import fit_count_dispersion as fcd
from scripts.sofa import measure_count_families as mcf
from scripts.sofa.calibrate_from_cache import Played, _settle_sample

GOLDEN = Path(__file__).parent / "golden" / "count_estimator_pre_dispersion.json"
BOUNDARIES = (0.5, 1.5, 2.5, 4.5, 9.5, 21.5)


def _table() -> cd.DispersionTable:
    return cd.parse_table({"markets": {
        "goals_for": {"family": "nb", "alpha": 0.25,
                      "by_competition": {"17": 0.10, "8": {"alpha": 0.40}}},
        "shots_total": {"family": "normal", "alpha": 0.013},
        "corners_2h_for": {"family": "nb", "alpha": 0.2},
    }})


# --- switch off: byte-identical -------------------------------------------


def test_off_matches_the_golden_values_from_before_the_change() -> None:
    golden = json.loads(GOLDEN.read_text())
    assert len(golden) == 75
    for g in golden:
        sd = sheet_predictive_sd(
            g["market"], g["sport"], g["mean"], g["var"], g["n"], g["centre"])
        assert sd == g["sd"], g
        explicit = sheet_predictive_sd(
            g["market"], g["sport"], g["mean"], g["var"], g["n"], g["centre"], None)
        assert explicit == g["sd"]
        got = [
            sheet_count_p_raw(g["market"], g["centre"], sd, b, d)
            for b in BOUNDARIES for d in ("OVER", "UNDER")
        ]
        assert got == g["p"], g
        assert got == [
            sheet_count_p_raw(g["market"], g["centre"], sd, b, d, None)
            for b in BOUNDARIES for d in ("OVER", "UNDER")
        ]


def test_the_switch_is_off_until_the_operator_sets_it() -> None:
    assert epochs.COUNT_DISPERSION_FROM_UTC is None
    assert not epochs.count_dispersion_enabled("2026-10-09")
    assert not epochs.count_dispersion_enabled(
        "2030-01-01", datetime(2030, 1, 1, tzinfo=UTC))


def test_the_switch_reads_the_day_and_the_build_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start = datetime(2026, 10, 9, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(epochs, "COUNT_DISPERSION_FROM_UTC", start)
    assert epochs.count_dispersion_enabled("2026-10-09", start)
    assert not epochs.count_dispersion_enabled(
        "2026-10-09", start - timedelta(minutes=1))
    # a rebuild of an earlier day keeps the rule it printed under
    assert not epochs.count_dispersion_enabled("2026-10-08", start + timedelta(days=3))


# --- switch on --------------------------------------------------------------


def test_on_the_fitted_alpha_sets_the_variance_and_the_family() -> None:
    t = _table()
    d = t.read("football", "goals_for", 17)
    assert d is not None and d.source == "competition" and d.alpha == 0.10
    sd = sheet_predictive_sd("goals_for", "football", 1.3, 1.9, 10, 1.2, d)
    assert sd == pytest.approx(math.sqrt(1.2 + 0.10 * 1.2 ** 2))  # no (1 + 1/n)
    for b in BOUNDARIES:
        for direction in ("OVER", "UNDER"):
            assert sheet_count_p_raw("goals_for", 1.2, sd, b, direction, d) == (
                calc_p_central_nb_raw(1.2, sd, b, direction))
    # the sample's mean / variance no longer matter
    assert sd == sheet_predictive_sd("goals_for", "football", 9.0, 0.0, 3, 1.2, d)


def test_a_market_the_plain_normal_priced_becomes_a_nb() -> None:
    d = _table().read("football", "corners_2h_for", 1)
    assert d is not None and "corners_2h_for" not in engine.NEGATIVE_BINOMIAL_METRICS
    sd = sheet_predictive_sd("corners_2h_for", "football", 2.0, 2.5, 10, 1.9, d)
    p = sheet_count_p_raw("corners_2h_for", 1.9, sd, 2.5, "OVER", d)
    assert p == calc_p_central_nb_raw(1.9, sd, 2.5, "OVER")
    assert p != sheet_count_p_raw("corners_2h_for", 1.9, sd, 2.5, "OVER")


def test_shots_total_keeps_the_floored_normal_with_the_fitted_variance() -> None:
    d = _table().read("football", "shots_total", 17)
    assert d is not None and d.family == cd.FAMILY_NORMAL and d.source == "market"
    sd = sheet_predictive_sd("shots_total", "football", 24.0, 30.0, 10, 23.0, d)
    assert sd == pytest.approx(math.sqrt(23.0 + 0.013 * 23.0 ** 2))
    assert sheet_count_p_raw("shots_total", 23.0, sd, 22.5, "OVER", d) == (
        calc_p_central_raw(23.0, sd, 22.5, "OVER", support_floor_for("shots_total")))


def test_fallbacks_are_stated_and_safe() -> None:
    t = _table()
    # a competition the market has no cases for: the market's alpha
    d = t.read("football", "goals_for", 999)
    assert d is not None and d.source == "market" and d.alpha == 0.25
    d = t.read("football", "goals_for", None)
    assert d is not None and d.source == "market"
    # the dict form of a competition cell
    assert t.read("football", "goals_for", 8) == cd.Dispersion(0.40, "nb", "competition")
    # a market the file does not cover (player props, unmeasured): today's estimator
    assert t.read("football", "player_shots_for", 17) is None
    assert t.read("football", "fouls_1h_for", 17) is None
    # tennis and every other sport: untouched
    assert t.read("tennis", "goals_for", 17) is None
    assert t.read(None, "goals_for", 17) is None


def test_a_bad_or_missing_file_raises_rather_than_falling_back(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        cd.load_table(tmp_path / "nope.json")
    with pytest.raises(ValueError):
        cd.parse_table({"markets": {"goals_for": {"family": "zinb", "alpha": 0.1}}})
    with pytest.raises(ValueError):
        cd.parse_table({"markets": {"goals_for": {"family": "nb", "alpha": 0.0}}})


def test_the_shipped_config_is_inert_and_parses() -> None:
    raw = json.loads(cd.config_path(cd.CONFIG_FILE).read_text())
    assert "INERT" in raw["_doc"] and raw["fitted_from"]["db_access"].startswith("read-only")
    assert raw["fitted_from"]["evidence"].endswith("count_families_2026-10-08.md")
    t = cd.load_table()
    assert t.read("football", "shots_total", None) is not None
    assert t.read("football", "shots_total", None).family == "normal"  # type: ignore[union-attr]
    assert t.read("football", "goals_for", None).family == "nb"  # type: ignore[union-attr]
    assert epochs.COUNT_DISPERSION_FROM_UTC is None  # nothing reads it yet


def test_pooled_alpha_is_the_market_alpha_with_no_cases_and_the_leagues_with_many() -> None:
    kw = {"mom": 0.3, "mle": 0.25, "bmean": 4.0, "kc": 100.0}
    assert cd.pooled_alpha(0.0, 0.0, **kw) == pytest.approx(0.25)
    big = cd.pooled_alpha(2000.0, 1e6, **kw)  # a league with alpha_mom 0.002
    assert big < 0.01
    thin = cd.pooled_alpha(2.0, 10.0, **kw)
    assert abs(thin - 0.25) < 0.05  # a handful of cases barely moves it


def test_the_off_path_reads_no_config_and_opens_no_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structural, not a clock: with the switch off nothing loads the table or
    reads a file, and the estimator never touches a dispersion."""
    reads: list[object] = []
    monkeypatch.setattr(cd, "load_table", lambda *a, **k: reads.append("load"))
    real_read_text = Path.read_text

    def spy(self: Path, *a: Any, **k: Any) -> str:
        reads.append(str(self))
        return real_read_text(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", spy)
    assert epochs.COUNT_DISPERSION_FROM_UTC is None
    assert not epochs.count_dispersion_enabled("2026-10-09")
    monkeypatch.setattr(cc, "COUNT_DISPERSION", None)
    for _ in range(50):
        sheet_predictive_sd("goals_for", "football", 1.3, 1.9, 10, 1.2, None)
    sample = [1.0, 3.0, 0.0, 2.0, 5.0, 1.0, 2.0, 4.0, 0.0, 3.0]
    match = Played(event_id=1, timestamp=0, home_id=1, away_id=2, sport="football",
                   competition_id=17, values={})
    assert _settle_sample(match, "goals_for", "", 2.0, sample, {}, {})
    assert reads == []
    # and a table's lookup is a dict read, not a file read
    table = _table()
    reads.clear()
    for _ in range(50):
        table.read("football", "goals_for", 17)
    assert reads == []


# --- the replay and the rebuild ----------------------------------------------


def test_the_replay_prices_with_the_fitted_alpha_only_when_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample = [1.0, 3.0, 0.0, 2.0, 5.0, 1.0, 2.0, 4.0, 0.0, 3.0]
    match = Played(event_id=1, timestamp=0, home_id=1, away_id=2, sport="football",
                   competition_id=17, values={})
    args = (match, "goals_for", "", 2.0, sample, {}, {})
    monkeypatch.setattr(cc, "COUNT_DISPERSION", None)
    plain = _settle_sample(*args)
    assert plain
    mean = sum(sample) / len(sample)
    var = sum((v - mean) ** 2 for v in sample) / (len(sample) - 1)
    # no table: the sample's variance through SHEET's own estimator (centre =
    # mean: no prior)
    plain_sd = sheet_predictive_sd("goals_for", "football", mean, var, len(sample), mean)
    for r in plain:
        assert r.p_central == pytest.approx(round(sheet_count_p_raw(
            "goals_for", mean, plain_sd,
            engine.winning_boundary(r.line, r.direction), r.direction), 6), abs=1e-6)
    monkeypatch.setattr(cc, "COUNT_DISPERSION", _table())
    fitted = _settle_sample(*args)
    sd = math.sqrt(mean + 0.10 * mean ** 2)  # competition 17, centre = mean (no prior)
    for r in fitted:
        want = calc_p_central_nb_raw(
            mean, sd, engine.winning_boundary(r.line, r.direction), r.direction)
        assert r.p_central == pytest.approx(round(want, 6), abs=1e-6)
    assert [r.p_central for r in fitted] != [r.p_central for r in plain]
    assert [(r.line, r.direction) for r in fitted] == [
        (r.line, r.direction) for r in plain]
    # tennis rows never read it
    tennis = Played(event_id=2, timestamp=0, home_id=1, away_id=2, sport="tennis",
                    competition_id=17, values={})
    monkeypatch.setattr(cc, "COUNT_DISPERSION", None)
    base = [r.p_central for r in _settle_sample(tennis, "aces_for", "1", 3.0, sample, {}, {})]
    monkeypatch.setattr(cc, "COUNT_DISPERSION", _table())
    assert [r.p_central for r in _settle_sample(
        tennis, "aces_for", "1", 3.0, sample, {}, {})] == base


def test_a_sheet_of_the_other_rule_is_re_priced_by_the_rebuild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bet.sofa import rebuild_plan as rp

    at = datetime(2026, 10, 9, 7, 0, tzinfo=UTC)
    limit = timedelta(minutes=45)
    assert epochs.sheet_count_dispersion([{"dispersion_rule": epochs.COUNT_DISPERSION}])
    assert not epochs.sheet_count_dispersion(
        [{"dispersion_rule": epochs.COUNT_DISPERSION}, {}])
    assert epochs.sheet_count_dispersion([])
    # off: a sheet without the rule is kept (nothing changes today)
    off = rp.build_plan(rp.DayState("2026-10-09", at, limit, sheet_dispersion=False))
    assert "SHEET" not in off.names()
    monkeypatch.setattr(epochs, "COUNT_DISPERSION_FROM_UTC",
                        datetime(2026, 10, 9, tzinfo=UTC))
    stale = rp.build_plan(rp.DayState("2026-10-09", at, limit, sheet_dispersion=False))
    sheet = next(s for s in stale.steps if s.name == "SHEET")
    assert "dispersion" in sheet.reason
    assert stale.names().index("SHEET") < stale.names().index("CONFIDENCE")
    assert "SHEET" not in rp.build_plan(
        rp.DayState("2026-10-09", at, limit, sheet_dispersion=True)).names()
    old_day = rp.build_plan(rp.DayState("2026-10-08", at, limit, sheet_dispersion=False))
    assert "SHEET" not in old_day.names()


def _sheet_row(**over: Any) -> Any:
    from bet.sofa.contracts import SheetRow

    base: dict[str, Any] = dict(
        sofascore_event_id=1, sport="football", market="corners_total",
        subject="", line=9.5, direction="OVER", sample_size=10, sample_mean=10.0,
        sample_sd=2.0, centre=10.0, p_central=0.6, market_p=0.55,
        ladder_centre=9.4, ladder_sigma=0.3, p_bar=0.58, bar_reason="none",
        required_odds=1.90, offered_odds=1.88, edge=0.05, surplus=-0.02,
        verdict="BELOW_BAR", notes=[])
    base.update(over)
    return SheetRow(**base)


def test_a_sheet_row_carries_the_rule_only_when_it_was_priced_under_it() -> None:
    from bet.sofa.contracts import SheetRow
    from scripts.sofa.run_sheet import sheet_row_json

    assert "dispersion_rule" in SheetRow.model_fields
    plain = sheet_row_json(_sheet_row())
    assert "dispersion_rule" not in plain
    marked = sheet_row_json(_sheet_row(dispersion_rule=epochs.COUNT_DISPERSION))
    assert marked["dispersion_rule"] == epochs.COUNT_DISPERSION
    assert {k: v for k, v in marked.items() if k != "dispersion_rule"} == plain


# --- the fit -----------------------------------------------------------------


def _synthetic_cases(n: int, alpha: float, seed: int = 0) -> mcf.Cases:
    rng = np.random.default_rng(seed)
    mu = rng.uniform(0.8, 3.5, n)
    r = 1.0 / alpha
    y = rng.poisson(rng.gamma(r, mu / r))
    ts = np.linspace(1.6e9, 1.80e9, n)  # 2020 .. 2027-01
    comp = rng.choice([17, 8], n)
    z = np.zeros(n)
    return mcf.Cases(ts, np.arange(n), comp.astype(np.int64), np.zeros(n, np.int64),
                     y.astype(np.float64), np.full(n, 10.0), mu, mu * 2, mu,
                     np.full((n, mcf.SAMPLE_PAD), np.nan) + z[:, None])


def test_the_fit_recovers_the_dispersion_and_never_reads_after_before() -> None:
    cases = _synthetic_cases(30000, 0.3)
    before = datetime(2026, 10, 8, tzinfo=UTC).timestamp()
    val = datetime.fromisoformat(fcd.val_start_for("2026-10-08")).replace(
        tzinfo=UTC).timestamp()
    cell = fcd.fit_market("goals_for", cases, before, val)
    assert cell["status"] == "OK" and cell["family"] == "nb"
    assert cell["alpha"] == pytest.approx(0.3, rel=0.15)
    assert set(cell["by_competition"]) == {"17", "8"}
    assert all(0.15 < a < 0.5 for a in cell["by_competition"].values())
    # cases at or after `before` do not move it: replace them with nonsense
    late = cases.ts >= before
    assert late.any()
    cases.y[late] = 500.0
    assert fcd.fit_market("goals_for", cases, before, val)["alpha"] == cell["alpha"]
    assert fcd.fit_market("shots_total", cases, before, val)["family"] == "normal"


def test_the_fit_refuses_a_thin_market() -> None:
    cases = _synthetic_cases(1500, 0.3)
    before = datetime(2026, 10, 8, tzinfo=UTC).timestamp()
    assert fcd.fit_market("goals_for", cases, before, before - 1e7)["status"] == "TOO_THIN"


def test_the_evidence_gate_admits_only_a_measured_improvement() -> None:
    ev = {
        "goals_for": {"status": "OK", "families": {"nb_lg": {
            "d_ll": [-0.004, -0.0045, -0.0035], "half_d_ll": [-0.004, -0.004]}}},
        "shots_2h_total": {"status": "OK", "families": {"nb_lg": {
            "d_ll": [-0.0007, -0.0012, -0.0000004],
            "half_d_ll": [-0.0017, 0.0003]}}},
        "fouls_1h_for": {"status": "TOO_THIN"},
        "shots_total": {"status": "OK", "families": {"norm_lg": {
            "d_ll": [-0.0009, -0.0012, -0.0007], "half_d_ll": [-0.0009, -0.0009]}}},
    }
    assert fcd.evidence_gate(ev, "goals_for") == (True, [-4.0, -4.5, -3.5])
    assert fcd.evidence_gate(ev, "shots_total")[0]  # judged on norm_lg
    assert not fcd.evidence_gate(ev, "shots_2h_total")[0]  # a half goes the other way
    assert not fcd.evidence_gate(ev, "fouls_1h_for")[0]
    assert not fcd.evidence_gate(ev, "never_scored")[0]
    assert fcd.evidence_gate(None, "anything") == (True, None)


def test_the_written_config_says_what_it_is() -> None:
    cfg = fcd.build_config(
        {"goals_for": {"status": "OK", "family": "nb", "alpha": 0.2,
                       "n_cases": 5, "n_val_cases": 1, "kc": 100.0,
                       "n_competitions": 0, "by_competition": {}},
         "fouls_1h_for": {"status": "TOO_THIN", "family": "nb", "n_cases": 3}},
        before="2026-10-08", val_start="2026-04-08", cases_dir=Path("c"),
        max_case_ts=1.7e9, db_path="data/sofa.db")
    assert "INERT" in cfg["_doc"]
    assert set(cfg["markets"]) == {"goals_for"}
    assert cfg["fitted_from"]["before"] == "2026-10-08"
    assert cfg["fitted_from"]["markets_too_thin"] == ["fouls_1h_for"]
    assert "n_val_cases" not in cfg["markets"]["goals_for"]
    cd.parse_table(cfg)  # the reader accepts what the writer wrote


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.1, 0.0, "abc", None])
def test_every_competition_alpha_is_validated(bad: Any) -> None:
    for form in (bad, {"alpha": bad}):
        with pytest.raises(ValueError):
            cd.parse_table({"markets": {"goals_for": {
                "family": "nb", "alpha": 0.2, "by_competition": {"17": form}}}})
    with pytest.raises(ValueError):  # one bad league among good ones
        cd.parse_table({"markets": {"goals_for": {
            "family": "nb", "alpha": 0.2,
            "by_competition": {"8": 0.3, "17": bad}}}})


def test_a_numeric_string_alpha_is_the_number_it_spells() -> None:
    t = cd.parse_table({"markets": {"goals_for": {
        "family": "nb", "alpha": 0.2, "by_competition": {"17": "0.3"}}}})
    assert t.read("football", "goals_for", 17).alpha == 0.3  # type: ignore[union-attr]


def test_the_replayed_joint_reads_the_same_alpha_as_sheet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """replay == SHEET on a goals joint under COUNT_DISPERSION."""
    from bet.sofa.contracts import FixtureOffer, PricedRung
    from bet.sofa.derived import price_derived_rungs
    from bet.sofa.timeutil import now
    from tests.sofa.test_derived_markets import make_fixture, make_samples

    a = [2, 0, 1, 3, 1, 0, 2, 1, 1, 2]
    b = [0, 1, 1, 0, 2, 1, 0, 0, 1, 1]
    c_home, c_away = 1.45, 0.80
    table = cd.parse_table({"markets": {"goals_for": {
        "family": "nb", "alpha": 0.25, "by_competition": {"17": 0.40}}}})
    offer = FixtureOffer(sofascore_event_id=1, status="PRICED", unmapped_markets=[],
                         rungs=[PricedRung(market="both_over_goals", subject="",
                                           line=0.5, over_odds=1.8, under_odds=1.95,
                                           fetched_at_utc=now())])

    def sheet(tbl: cd.DispersionTable | None) -> float:
        rows, _ = price_derived_rungs(
            fixture=make_fixture(), samples=make_samples("goals_for", a, b),
            offer=offer, correlations={"goals": 0.1}, vetoes=[], min_sample=5,
            max_ladder_sigma=9.0, k_price=10.0, unfitted=[], stats_only=True,
            marginal_centres={("goals_for", "side_a"): c_home,
                              ("goals_for", "side_b"): c_away},
            dispersion_table=tbl)
        return next(r.p_central for r in rows if r.direction == "OVER")

    def replay() -> float:
        match = Played(event_id=1, timestamp=0, home_id=1, away_id=2,
                       sport="football", competition_id=17,
                       values={"goals": (2.0, 1.0)})
        rows = [r for r in cc.football_joint_rows(
            match, "goals", [float(v) for v in a], [float(v) for v in b],
            (c_home, c_away), 0.1)
            if r.market == "both_over_goals" and r.line == 0.5
            and r.direction == "OVER"]
        assert len(rows) == 1
        return rows[0].p_central

    monkeypatch.setattr(cc, "COUNT_DISPERSION", None)
    assert replay() == pytest.approx(sheet(None), abs=6e-5)
    monkeypatch.setattr(cc, "COUNT_DISPERSION", table)
    assert replay() == pytest.approx(sheet(table), abs=6e-5)
    assert sheet(table) != pytest.approx(sheet(None), abs=1e-3)  # the switch bites


def test_the_two_football_switches_cannot_be_on_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = datetime(2026, 10, 9, 7, 0, tzinfo=UTC)
    day = "2026-10-09"
    epochs.require_k_with_dispersion(day, at)  # both off: fine
    monkeypatch.setattr(epochs, "COUNT_DISPERSION_FROM_UTC",
                        datetime(2026, 10, 9, tzinfo=UTC))
    with pytest.raises(ValueError, match="PER_MARKET_K"):
        epochs.require_k_with_dispersion(day, at)
    monkeypatch.setattr(epochs, "COUNT_DISPERSION_FROM_UTC", None)
    monkeypatch.setattr(epochs, "PER_MARKET_K_FROM_UTC",
                        datetime(2026, 10, 9, tzinfo=UTC))
    with pytest.raises(ValueError, match="COUNT_DISPERSION"):
        epochs.require_k_with_dispersion(day, at)
    monkeypatch.setattr(epochs, "COUNT_DISPERSION_FROM_UTC",
                        datetime(2026, 10, 9, tzinfo=UTC))
    epochs.require_k_with_dispersion(day, at)  # together: fine
    epochs.require_k_with_dispersion("2026-10-08", at)  # before the date: both off


def test_the_fit_writes_only_with_write_and_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "meta.json").write_text("{}")
    out = tmp_path / "cfg.json"
    out.write_text("LIVE")
    base = ["fit_count_dispersion.py", "--before", "2026-10-08", "--cases",
            str(cases), "--out", str(out), "--evidence-json",
            str(tmp_path / "none.json")]
    monkeypatch.setattr("sys.argv", base)
    assert fcd.main() == 0
    assert out.read_text() == "LIVE"  # no --write: nothing written
    monkeypatch.setattr("sys.argv", [*base, "--write", "--dry-run"])
    assert fcd.main() == 0 and out.read_text() == "LIVE"
    monkeypatch.setattr("sys.argv", [*base, "--write"])
    assert fcd.main() == 0
    cfg = json.loads(out.read_text())
    assert cfg["markets"] == {}
    assert not list(tmp_path.glob("cfg.json.*.tmp"))


def test_the_provenance_is_durable() -> None:
    cfg = fcd.build_config(
        {}, before="2026-10-08", val_start="2026-04-08",
        cases_dir=Path("/private/tmp/xyz/count_cases"), max_case_ts=1.7e9,
        db_path="/private/tmp/xyz/sofa_replay.db", fingerprint="abc",
        min_case_ts=1.6e9)
    ff = cfg["fitted_from"]
    assert "/private/tmp" not in json.dumps(ff)
    assert ff["cases_fingerprint_sha256"] == "abc"
    assert ff["min_case_date"] < ff["max_case_date"]
    assert ff["evidence"].endswith(".md") and ff["evidence_json"].endswith(".json")
