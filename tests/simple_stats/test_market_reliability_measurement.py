"""The reliability measurement, pinned at the points where it can lie quietly.

``config/market_reliability.json`` decides two things that cost money: whether a
market's tier steps down, and what grade the operator reads next to an
expectation. Both are silent failures if the measurement is wrong -- a number
that is merely mistaken looks exactly like a number that is right -- so the
cases asserted here are the ones that produced a wrong file and were caught by
inspecting output rather than by any test.

1. **The measurement scored a replica of the estimator instead of the estimator.**
   Rebuilding the centre from the raw buckets got 185 of 2,688 per-side centres
   wrong against the 2026-09-07 sheet. It was missing ``_one_per_day``,
   ``_adverse_values`` and ``_blend_referee`` -- all three inert on a
   single-provider non-card sample, all three active on exactly the markets with
   two providers or a referee. It now calls ``analyze_dossier``.

2. **Calibration measured a tautology.** Averaging ``p_central`` over every
   published rung gave 0.500 claimed against 0.500 realised on every market on
   the board, necessarily: each line is published on both sides, the two
   probabilities sum to one and exactly one wins.

3. **A market that happens 0.13 times a match scored +24.2% and read as our
   best forecast.** MAE there is dominated by the base rate.

4. **The driver table was a multiple-comparisons problem treated as 22 separate
   ones.** Three drivers cleared their own 95% interval and each was within
   0.011 of containing zero.

5. **A bare ``except Exception`` read a NameError as a bad artifact** and
   reported zero scopes, with no traceback, for a whole run of the script.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "measure_market_reliability", ROOT / "scripts" / "simple" /
    "measure_market_reliability.py"
)
mmr = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mmr)


class _Row:
    """The four fields ``_side_of`` reads, and nothing else."""

    def __init__(self, *, market="fouls_for", team_name=None, player_id=None, venue=None):
        self.market = market
        self.team_name = team_name
        self.player_id = player_id
        self.venue = venue


def test_a_row_is_joined_to_the_scoreboard_column_it_belongs_to():
    """The join, which is the whole of the per-participant measurement.

    ``_side_of`` returns what ``settle.actual_value`` wants: ``None`` for a
    match total, ``"home"``/``"away"`` for a participant, plus the subject key.
    A football row's side is taken off the row rather than recomputed, because
    ANALYZE publishes ``venue`` for exactly this purpose.
    """
    dossier = {"team_a_name": "Llaneros FC", "team_b_name": "Deportes Tolima"}

    assert mmr._side_of(_Row(market="fouls_total"), dossier) == (None, "total")
    assert mmr._side_of(
        _Row(team_name="Llaneros FC", venue="home"), dossier
    ) == ("home", "Llaneros FC")
    assert mmr._side_of(
        _Row(team_name="Deportes Tolima", venue="away"), dossier
    ) == ("away", "Deportes Tolima")
    assert mmr._side_of(
        _Row(market="player_fouls", team_name="Llaneros FC", player_id="2190"), dossier
    ) == (None, "2190")


def test_the_figure_is_read_by_the_shipping_settlement_and_not_here():
    """``settle.actual_value`` carries three rules a lookup written in the
    measurement had wrong or missing, and one of them inverted a finding.

    ``red_cards`` is absent from ``/events/{id}/stats/`` on a match with no red
    card rather than reported as zero, and ``ABSENT_MEANS_ZERO`` is what turns
    that absence into the 0.0 it means. Reading the key directly measured
    ``red_cards_total`` on the 199 fixtures where the field existed -- a sample
    selected on the event being forecast -- and reported +12.9% skill with
    confident rows 12.8 points hot. Over all 593 it scores **-47.0%** and its
    confident rows are calibrated to within half a point.
    """
    from bet.simple_stats.settle import ABSENT_MEANS_ZERO, actual_value

    assert "red_cards_total" in ABSENT_MEANS_ZERO

    # A fixture with a statistics block and no red_cards key: zero, not absent.
    played = {"total": {"fouls_total": 20.0, "corners_total": 8.0}}
    assert actual_value(played, "red_cards_total", None) == 0.0

    # And the market the measurement now reports, from the shipped config.
    from bet.simple_stats.analyze import market_reliability

    entry = market_reliability()["red_cards_total"]
    assert entry["fixtures"] > 500, "the zeros must be in the sample"
    assert entry["actual_mean"] < 0.3
    assert entry["skill"] < -0.2
    assert entry["overconfident_at_75"] is False


def test_a_tennis_row_carries_no_venue_and_is_resolved_by_name():
    """Tennis passes ``venue=None`` -- no tennis market has a venue prior, so
    ``_team_rows`` declines to name a side -- and the two participants are
    matched against the dossier's own two slots instead. Both names come from
    the same dossier field, so equality is exact by construction; a name that
    matches neither slot returns None rather than guessing, because
    attributing one player's games to the other would look like a measurement.

    The settled tennis actuals key the two participants "home"/"away" because
    they inherit the football schema, not because anybody is at home.
    """
    dossier = {"team_a_name": "Iga Świątek", "team_b_name": "Qinwen Zheng"}
    assert mmr._side_of(
        _Row(market="games_won", team_name="Iga Świątek"), dossier
    ) == ("home", "Iga Świątek")
    assert mmr._side_of(
        _Row(market="games_won", team_name="Qinwen Zheng"), dossier
    ) == ("away", "Qinwen Zheng")
    assert mmr._side_of(
        _Row(market="games_won", team_name="Aryna Sabalenka"), dossier
    ) is None

    # ``games_won`` has no ``_for`` suffix, so the suffix rule alone reads it as
    # a match total -- which would settle "Tagger games_won OVER 6.5" against
    # the match's 22 games instead of her 9. ``settle`` keeps the exception and
    # the measurement inherits it rather than repeating it.
    from bet.simple_stats.settle import _PER_SIDE_MARKETS, actual_value

    assert "games_won" in _PER_SIDE_MARKETS
    match = {"home": {"games_won": 12.0}, "away": {"games_won": 19.0},
             "total": {"total_games": 31.0}}
    assert actual_value(match, "games_won", "home") == 12.0
    assert actual_value(match, "games_won", None) is None


def test_team_a_is_the_home_side_in_every_artifact_that_names_both():
    """The load-bearing assumption, checked against the artifacts rather than
    trusted. ``enrich._side_names`` returns ``(home_team, away_team)`` for
    football, so the ``team_a`` slot is the home side -- and if that ever
    reverses, every ``*_for`` measurement silently swaps the two teams.
    """
    import json

    runs = mmr._run_dirs()
    if not runs:
        pytest.skip("no runs/ directory with completed artifacts in this worktree")
    agree = disagree = 0
    for run in runs:
        events = {
            e["event_id"]: e
            for e in json.loads(
                (run / f"{run.name}_event_list.json").read_text()
            )["events"]
        }
        for dossier in json.loads(
            (run / f"{run.name}_event_dossiers.json").read_text()
        )["dossiers"]:
            if dossier.get("sport") != "football":
                continue
            event = events.get(dossier["event_id"])
            names = (dossier.get("team_a_name"), dossier.get("team_b_name"))
            if not event or not all(names):
                continue
            if names == (event.get("home_team"), event.get("away_team")):
                agree += 1
            elif names == (event.get("away_team"), event.get("home_team")):
                disagree += 1

    assert agree > 500, "no artifacts to check the convention against"
    assert disagree == 0


def test_a_push_settles_as_neither_a_win_nor_a_loss():
    """Half-integer lines make this rare and integer lines make it real. A push
    counted as a loss would understate every market that posts whole numbers.
    """
    assert mmr._settle_rung(3.0, 2.5, "OVER") == 1.0
    assert mmr._settle_rung(2.0, 2.5, "OVER") == 0.0
    assert mmr._settle_rung(2.0, 2.5, "UNDER") == 1.0
    assert mmr._settle_rung(3.0, 2.5, "UNDER") == 0.0
    assert mmr._settle_rung(2.0, 2.0, "OVER") is None
    assert mmr._settle_rung(2.0, 2.0, "UNDER") is None


def test_calibration_reads_one_side_of_each_rung_and_not_both():
    """The tautology guard.

    Both sides of a rung are published and their probabilities sum to one, so
    averaging over both gives 0.500 claimed against 0.500 realised whatever the
    forecast does. Here is a market that is badly overconfident -- every 0.90
    claim loses -- and a measurement that reads both sides would call it
    perfectly calibrated.
    """
    rungs: list[tuple[float, float, str]] = []
    for index in range(120):
        fixture = f"f{index}"
        # The favoured side claims 0.90 and loses every time; its mirror claims
        # 0.10 and wins every time. Averaged over both: 0.5 claimed, 0.5 real.
        rungs.append((0.90, 0.0, fixture))
        rungs.append((0.10, 1.0, fixture))

    out = mmr._calibration(rungs)
    assert out["rungs"] == 120, "the mirror side must not be counted"
    assert out["calibration_error"] == pytest.approx(0.90, abs=0.01)
    assert out["at_75"]["claimed"] == pytest.approx(0.90, abs=0.001)
    assert out["at_75"]["realised"] == pytest.approx(0.0, abs=0.001)
    assert out["overconfident_at_75"] is True


def test_a_well_calibrated_market_is_not_flagged():
    """The other half: a market whose 0.80 claims win 80% of the time must not
    be called hot, and the flag needs both a material gap and an interval that
    clears zero -- a small gap on thin data is noise, not a finding.
    """
    rungs = [
        (0.80, float(index % 5 != 0), f"f{index}") for index in range(200)
    ]
    out = mmr._calibration(rungs)
    assert out["at_75"]["realised"] == pytest.approx(0.80, abs=0.001)
    assert out["overconfident_at_75"] is False


def test_a_corrected_interval_is_wider_than_its_own_test():
    """Bonferroni, as arithmetic rather than as prose. Reading further into the
    tail of the same resample must widen the interval, or the correction is not
    doing anything.
    """
    points = [(float(i % 7), float((i * 3) % 5), f"f{i}") for i in range(300)]
    _, lo_95, hi_95 = mmr._bootstrap_correlation(points, draws=4000)
    _, lo_fw, hi_fw = mmr._bootstrap_correlation(points, draws=4000, alpha=0.05 / 22)
    assert lo_fw < lo_95
    assert hi_fw > hi_95


def test_the_shipped_config_carries_what_its_consumers_read():
    """Every field ``bet_builder_draft`` and ``forecast`` branch on, present on
    every scope. A missing key does not raise -- both read with ``.get`` and a
    default -- so it fails as a market quietly never being stepped down.
    """
    from bet.simple_stats.analyze import market_reliability

    table = market_reliability()
    assert len(table) >= 25
    for scope, entry in table.items():
        assert "skill" in entry, scope
        assert "skill_comparable" in entry, scope
        assert "fixtures" in entry and entry["fixtures"] >= mmr.MIN_SCOPE_FIXTURES, scope
        if "at_75" in entry:
            assert "overconfident_at_75" in entry, scope
            tail = entry["at_75"]
            assert {"claimed", "realised", "gap", "gap_ci", "fixtures"} <= set(tail), scope


def test_no_scope_exists_for_a_market_the_sheet_never_prices():
    """The dossier collects 1H/2H splits for fouls, shots, corners, cards and
    offsides, and ``cards_total`` besides. ANALYZE prices none of them, and an
    earlier pass measured all of them off the raw metrics -- which is where
    "cards_total +0.8%" and "fouls_2h_total +5.9%" came from. A phantom scope is
    not a harmless extra line: the analyst reads this file to decide what to
    trust, and the phantoms carried the referee's only SHARPENS verdicts.
    """
    from bet.simple_stats.analyze import market_reliability
    from bet.simple_stats.forecast import market_reliability_drivers

    never_priced = {
        "cards_total",
        "cards_1h_total",
        "cards_2h_total",
        "fouls_1h_total",
        "fouls_2h_total",
        "shots_1h_total",
        "blocked_shots_total",
        "shots_off_target_total",
        "goals_against",
    }
    scopes = {s.split("@")[0] for s in market_reliability()}
    assert not (scopes & never_priced)
    assert not (set(market_reliability_drivers()) & never_priced)


def test_no_driver_survives_the_family_wise_interval():
    """The measured finding, pinned so a rebuild that loses the correction is
    loud. Every driver on every priced market reads PRICES_IN: the sample
    already carries the referee, the h2h and the recent form, and presenting
    them as independent support is counting one fact three times.
    """
    from bet.simple_stats.forecast import market_reliability_drivers

    drivers = market_reliability_drivers()
    assert drivers, "no drivers measured"
    for market, entries in drivers.items():
        for driver, entry in entries.items():
            assert entry["status"] == "PRICES_IN", f"{market}/{driver}"
            assert entry["tests_in_family"] >= 10, f"{market}/{driver}"
