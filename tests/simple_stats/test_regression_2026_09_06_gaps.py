"""The four gaps closed on 2026-09-06, each pinned to the measurement that found it.

Every one of these was invisible to the suite because it lived in the space
between two components that each behaved correctly on their own:

* a provider that omits a zero and a settlement that reads absence as unknown,
* a coupon that grades legs and a bet that pays on slips,
* a family the book prices one-way and a bar that only defends two-way markets.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

from bet.simple_stats.providers import _fill_absent_red_cards
from bet.simple_stats.settle import (
    ABSENT_MEANS_ZERO,
    actual_value,
    settle_row,
)


# --------------------------------------------------------- red cards


def _stats(**total) -> dict:
    """Actuals whose ``total`` block proves the provider answered for the fixture."""
    base = {"shots_total": 20.0, "fouls_total": 22.0, "corners_total": 9.0}
    base.update(total)
    return {"home": {}, "away": {}, "total": base}


def test_an_omitted_red_card_count_settles_as_zero_not_as_a_gap():
    """``red_cards`` is absent from ``/stats/`` when there were none.

    Read as "unknown", the family settles **only on matches that had a red
    card**: every UNDER that would have won returns NO_DATA and every LOST one
    settles. Over the 507 cached fixtures with a statistics block the key is
    present on 95 and 66 of those had a red -- missing-not-at-random in the one
    direction that makes a backtest look worse than the truth.
    """
    actuals = _stats()
    assert "red_cards_total" not in actuals["total"]
    assert actual_value(actuals, "red_cards_total", None) == 0.0
    assert settle_row(
        market="red_cards_total", line=0.5, direction="UNDER", actuals=actuals
    ) == ("WON", 0.0)


def test_a_fixture_with_no_statistics_at_all_is_still_a_gap():
    """Absence means zero only when the provider answered. No block, no inference.

    This is the guard that keeps the rule above from becoming the defect in
    ``a-zero-that-means-unknown``: a fixture the provider published nothing for
    must not be scored as a goalless, cardless, shotless match.
    """
    empty = {"home": {}, "away": {}, "total": {}}
    assert actual_value(empty, "red_cards_total", None) is None
    assert settle_row(
        market="red_cards_total", line=0.5, direction="UNDER", actuals=empty
    ) == ("NO_DATA", None)


def test_a_reported_red_card_still_settles_on_its_own_value():
    actuals = _stats(red_cards_total=2.0)
    assert settle_row(
        market="red_cards_total", line=0.5, direction="UNDER", actuals=actuals
    ) == ("LOST", 2.0)
    assert settle_row(
        market="red_cards_total", line=1.5, direction="OVER", actuals=actuals
    ) == ("WON", 2.0)


def test_only_the_red_card_family_infers_a_zero():
    """A missing corner count is a coverage gap and must stay one.

    Every other metric in the vocabulary is reported as ``0`` when it is zero;
    only ``red_cards`` is omitted. Widening this set without redoing the
    measurement behind it would reintroduce the exact bug it fixes.
    """
    assert ABSENT_MEANS_ZERO == {
        "red_cards_total", "red_cards_1h_total", "red_cards_2h_total",
    }
    actuals = _stats()
    del actuals["total"]["corners_total"]
    assert actual_value(actuals, "corners_total", None) is None


def test_the_sample_path_fills_the_same_zero_as_the_settlement_path():
    """The mirror. Both sides of the comparison must count the same matches.

    Fixing only the settlement leaves the sample built from matches that had a
    red card and compares it against every match -- which is how the bias sweep
    read the sample as *understating* reds by a factor of two when it was
    overstating them. Measured on the 2026-09-06 dossiers: ``red_cards_total``
    carried a median of 12 observations per fixture where ``cards_total``, the
    same matches from the same payload, carried 23.
    """
    totals = {"shots_total": 18.0, "shots_1h_total": 8.0, "shots_2h_total": 10.0}
    _fill_absent_red_cards(totals)
    assert totals["red_cards_total"] == 0.0
    assert totals["red_cards_1h_total"] == 0.0
    assert totals["red_cards_2h_total"] == 0.0


def test_the_sample_path_infers_nothing_without_a_witness():
    """No statistics for that period, no zero -- same rule as the settlement."""
    totals: dict[str, float] = {}
    _fill_absent_red_cards(totals)
    assert totals == {}
    # A full-match witness does not license a half-time inference.
    halves = {"shots_total": 18.0}
    _fill_absent_red_cards(halves)
    assert halves["red_cards_total"] == 0.0
    assert "red_cards_1h_total" not in halves


def test_a_reported_red_card_is_never_overwritten():
    totals = {"shots_total": 18.0, "red_cards_total": 1.0}
    _fill_absent_red_cards(totals)
    assert totals["red_cards_total"] == 1.0


# --------------------------------------------------------- player props


def _prop_sheet():
    from bet.simple_stats.contracts import StatsSheetRow, StatsSheetV1

    def row(market, **kw):
        base = dict(
            event_id="evt-1", sport="football", market=market, line=0.5,
            direction="OVER", hits=8, sample_size=10, hit_rate=0.8,
            p_low=0.62, p_central=0.80, mean=1.4, median=1.0, mode=1.0,
            sample_min=0.0, sample_max=3.0, dispersion=1.2,
            sources=["bzzoiro"], cross_provider_agreement="SINGLE_SOURCE",
            confidence="HIGH", data_quality="READY",
        )
        base.update(kw)
        return StatsSheetRow(**base)

    return StatsSheetV1(
        run_id="RID-1", date="2026-09-06",
        generated_at="2026-09-06T00:00:00+00:00",
        rows=[
            row("player_total_shots", player_id="p1", player_name="Someone"),
            row("player_fouls", player_id="p2", player_name="Another"),
            # Two non-prop rows, because a slip needs at least two legs: with
            # one the leg assertion below would pass on an empty draft and
            # prove nothing.
            row("corners_total", line=8.5, mean=9.9, sample_max=14.0),
            row("fouls_total", line=21.5, mean=23.4, sample_max=30.0),
        ],
    )


def _one_event():
    from bet.simple_stats.contracts import EventListV1, EventRecord

    return EventListV1(
        run_id="RID-1", date="2026-09-06",
        generated_at="2026-09-06T00:00:00+00:00",
        events=[EventRecord(
            event_id="evt-1", sport="football", competition="Premier League",
            home_team="A", away_team="B",
            start_time="2026-09-06T20:00:00+00:00",
            identity_confidence="CONFIRMED", status="ACTIVE",
        )],
    )


def test_a_player_prop_does_not_reach_the_coupon_by_default():
    """Measured -30.5% in the coupon's own band over 3,056 priced rows.

    Not a calibration fault and no threshold fixes it: props *in general* are
    calibrated to within a point, props *the book chooses to post* run 12-13
    points under their claim at every level of confidence. See
    ``ALLOW_PLAYER_PROPS`` for the three fixes that were measured and failed.
    """
    from bet.simple_stats.coupons import build_coupons

    coupons = build_coupons(_prop_sheet(), _one_event(), not_before=None)
    assert [s.market for s in coupons.singles] == ["corners_total", "fouls_total"]
    assert coupons.excluded.get("player_prop_unpriceable") == 2


def test_the_prop_gate_can_be_switched_back_on_for_the_next_measurement():
    """A flag, not a deletion: the measurement is five slates old and the fix
    -- an availability model -- is one this repo could acquire."""
    from bet.simple_stats.coupons import build_coupons

    coupons = build_coupons(
        _prop_sheet(), _one_event(), not_before=None, allow_player_props=True
    )
    assert "player_total_shots" in [s.market for s in coupons.singles]
    assert "player_prop_unpriceable" not in coupons.excluded


def test_a_prop_is_refused_as_a_bet_builder_leg_too():
    """"Every gate a single passes, a leg passes too" -- the invariant broken on
    2026-09-01, when thirty legs went out past gates the singles loop applied.

    A prop leg is the same row off the same unanchored sample as a prop single.
    """
    from bet.simple_stats.coupons import build_coupons

    coupons = build_coupons(_prop_sheet(), _one_event(), not_before=None)
    legs = [
        leg
        for slip in coupons.slips
        for leg in (slip.draft.legs if slip.draft else [])
    ]
    assert legs, "the fixture should still draft a slip from its non-prop rows"
    assert not [leg for leg in legs if leg.market.startswith("player_")]


def test_props_still_reach_the_stats_sheet():
    """The gate is about the coupon. The sheet is the record and keeps them --
    that is what the next measurement will be made from."""
    sheet = _prop_sheet()
    assert "player_total_shots" in {r.market for r in sheet.rows}


# --------------------------------------------------------- the audit's own guard


def test_the_bias_audit_skips_a_slate_older_than_the_definition_that_built_it():
    """A drift report must compare like with like, or it reports a repo diff.

    Before 2026-09-06 a red-card sample was built only from matches that had a
    red card, so every slate on disk from before then reads 0.280 against a
    truth of 0.146 -- and no re-enrichment can fix it, because those fixtures
    finished weeks ago. Reported as drift it is a permanent false alarm; skipped
    it is what it is, a historical document.

    Keyed on the *slate's* date, so a slate enriched by current code is checked
    normally and the skip disappears on its own.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_audit", ROOT / "scripts" / "simple" / "audit_sample_bias.py"
    )
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)

    assert audit._predates_definition_change("red_cards_total", "2026-09-05")
    assert not audit._predates_definition_change("red_cards_total", "2026-09-06")
    assert not audit._predates_definition_change("red_cards_total", "2026-09-07")
    # Every other market is unaffected in both directions.
    assert not audit._predates_definition_change("corners_total", "2020-01-01")


# --------------------------------------------------------- the header's gate list


def test_every_gate_build_coupons_can_report_is_named_in_the_file():
    """A gate the operator cannot see is a gate that silently thins his file.

    ``player_prop_unpriceable`` removed 38,691 rows on 2026-09-06 -- 38% of the
    sheet -- and the header listed seven gates and not that one, because the
    renderer filtered on ``reason in _NEW_GATE_LABELS``. The filter is gone (an
    unlabelled reason now prints its raw key), and this test is what keeps the
    *phrase* from going missing too.

    Reads the reasons straight out of ``coupons.py``'s own ``exclude("...")``
    calls, so adding a gate without a label fails here rather than in a file the
    operator is reading.
    """
    import importlib.util
    import re

    source = (ROOT / "src" / "bet" / "simple_stats" / "coupons.py").read_text(
        encoding="utf-8"
    )
    reasons = set(re.findall(r'exclude\(\s*"([a-z_]+)"\s*\)', source))
    assert "player_prop_unpriceable" in reasons, "the gate under test must be found"
    assert len(reasons) >= 8, f"suspiciously few gates parsed: {reasons}"

    spec = importlib.util.spec_from_file_location(
        "_build_coupons", ROOT / "scripts" / "simple" / "build_coupons.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    unlabelled = sorted(reasons - set(module._NEW_GATE_LABELS))
    assert not unlabelled, (
        "these exclusion reasons would print as a bare key in the coupon "
        f"header: {unlabelled}"
    )


def test_an_unlabelled_gate_is_printed_rather_than_hidden():
    """The belt to the test above's braces.

    If a gate is ever added and the test above is skipped or edited away, the
    row count must still reach the file -- a wrong-looking line is recoverable,
    a missing one is not.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_build_coupons", ROOT / "scripts" / "simple" / "build_coupons.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    lines: list[str] = []
    # ``_render_bar_basis`` owns the gate list and returns early on a file with
    # no singles, so it needs one row carrying a bar basis to get that far.
    single = type("S", (), {
        "bar_basis": "p_central", "shrink_k": 10.0,
        "bar_basis_reason": None, "sample_weight": 0.5,
    })()
    coupons = type(
        "C", (), {"excluded": {"a_brand_new_gate": 7}, "singles": [single]}
    )()
    module._render_bar_basis(lines.append, coupons)
    body = "\n".join(lines)
    assert "a_brand_new_gate" in body, body
    assert "7" in body, body
