"""A market measured to drift must say so in the files the operator reads.

The defect this guards against was not a wrong number anywhere. Every number
was right: ``audit_sample_bias.py`` measured ``cards_points_total`` running 0.55
of a booking point low against what Superbet settles (z=+3.86 over 266 settled
fixtures) and ``cards_points_for`` 0.28 low (z=+3.84 over 525), and both are
real. The defect was that the measurement existed **only in that script's
stdout**. Nothing carried it: the forecast handed both markets ``MEASURED``, its
best grade, with no qualification at all, and the 2026-09-07 coupon put four
card rows on the operator's file of which three were UNDERs -- the side a low
sample inflates -- with no caveat naming that.

So these tests assert against the *generated artifacts*. A unit test on
``_drift_note`` would have passed for the whole period the defect existed,
because the function it would have tested is the part that was never wired to
anything. What has to hold is a property of the files:

* every drifted market's forecast card names the drift;
* every coupon row on a drifted market carries a caveat that names it;
* the caveat names the correct *side*, which is the one thing here that can be
  wrong in a way that looks like a fix.

The side is worth its own test because the sign convention inverts so easily.
``delta`` is *actual minus sample*, so positive means the sample runs LOW, and a
low sample makes UNDER look likelier than it is. Flip that and the pipeline
warns about the OVER while the money sits on the UNDER.

Read-only: no network, no provider calls, no rebuild. They read the artifacts
already on disk and skip when the day is absent.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DATE = "2026-09-07"
RUN = ROOT / "runs" / DATE
DRIFT_CONFIG = ROOT / "config" / "sample_drift.json"


def _drifted() -> dict[str, dict]:
    """The markets the config marks drifted, or ``{}`` if it is absent."""
    if not DRIFT_CONFIG.exists():
        return {}
    markets = json.loads(DRIFT_CONFIG.read_text(encoding="utf-8")).get("markets") or {}
    return {m: e for m, e in markets.items() if e.get("drifted") is True}


@pytest.fixture(scope="module")
def drifted() -> dict[str, dict]:
    found = _drifted()
    if not found:
        pytest.skip("no market is currently marked as drifted")
    return found


@pytest.fixture(scope="module")
def forecast() -> dict:
    path = RUN / f"{DATE}_forecast.json"
    if not path.exists():
        pytest.skip(f"{path.name} not on disk")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def coupons() -> dict:
    path = RUN / f"{DATE}_coupons.json"
    if not path.exists():
        pytest.skip(f"{path.name} not on disk")
    return json.loads(path.read_text(encoding="utf-8"))


class TestTheConfigItself:
    def test_the_written_side_matches_the_sign_of_the_delta(self, drifted) -> None:
        """``overstated_side`` is the one field a reader must not have to derive.

        Both consumers read it rather than the sign, so if it were ever written
        inconsistently with ``delta`` every caveat downstream would point at
        the wrong half of the board while still looking measured.
        """
        for market, entry in drifted.items():
            expected = "UNDER" if entry["delta"] > 0 else "OVER"
            assert entry["overstated_side"] == expected, (
                f"{market}: delta {entry['delta']:+.3f} means the sample runs "
                f"{'low' if entry['delta'] > 0 else 'high'}, so the overstated "
                f"side is {expected}, not {entry['overstated_side']}"
            )

    def test_a_drifted_market_cleared_the_thresholds_it_claims(self, drifted) -> None:
        """``drifted`` is not a hand-set flag: it is the thresholds applied."""
        config = json.loads(DRIFT_CONFIG.read_text(encoding="utf-8"))
        limits = config["thresholds"]
        for market, entry in drifted.items():
            assert entry["fixtures"] >= limits["min_fixtures"], market
            assert abs(entry["z"]) > limits["max_abs_z"], market
            assert entry["priced"] is True, (
                f"{market} is marked drifted but Superbet does not price it -- "
                f"a drift that cannot reach a bet must not raise a caveat"
            )


class TestTheForecast:
    def test_every_card_on_a_drifted_market_names_the_drift(
        self, forecast, drifted
    ) -> None:
        """The grade is not allowed to be the whole story on these markets.

        ``cards_points_total`` scores +9.7% skill and a calibration error of
        0.0001, so it earns ``MEASURED`` honestly and will keep earning it. That
        is exactly why silence here is dangerous rather than merely incomplete:
        the best grade in the file sat beside a sample half a point off what the
        book settles, and the card said nothing.
        """
        checked = 0
        for card in forecast["cards"]:
            if card["market"] not in drifted:
                continue
            checked += 1
            note = card.get("sample_drift_note")
            assert note, (
                f"{card['market']} on {card.get('match')} is a drifted market "
                f"graded {card['grade']} with no drift note on the card"
            )
            assert card.get("sample_drift"), f"{card['market']}: no drift payload"
        assert checked, "no card on the day is on a drifted market -- nothing tested"

    def test_the_note_names_the_overstated_side(self, forecast, drifted) -> None:
        for card in forecast["cards"]:
            entry = drifted.get(card["market"])
            if entry is None:
                continue
            note = card["sample_drift_note"]
            side = entry["overstated_side"]
            other = "OVER" if side == "UNDER" else "UNDER"
            assert f"every {side} rung here is overstated" in note, (
                f"{card['market']}: the note must say {side} is the overstated "
                f"side; it reads: {note[:200]}"
            )
            assert f"every {other} understated" in note, card["market"]

    def test_a_centred_market_carries_no_drift_note(self, forecast, drifted) -> None:
        """The complement, and the half that keeps this from being vacuous.

        A note on every card would satisfy the tests above and tell the reader
        nothing. ``goals_total`` and ``corners_total`` are measured and centred;
        they must stay silent.
        """
        for card in forecast["cards"]:
            if card["market"] in drifted:
                continue
            assert not card.get("sample_drift_note"), (
                f"{card['market']} is not marked drifted but its card carries "
                f"a drift note"
            )


class TestTheCoupon:
    def test_every_row_on_a_drifted_market_carries_the_caveat(
        self, coupons, drifted
    ) -> None:
        """The file with money on it.

        On 2026-09-07 this is four rows -- three UNDERs and one OVER on
        ``cards_points_total`` -- and before the fix not one of them mentioned
        the drift.
        """
        checked = 0
        for single in coupons["singles"]:
            if single["market"] not in drifted:
                continue
            checked += 1
            assert any("dryf próbki" in c for c in single.get("caveats") or []), (
                f"single #{single['rank']} {single['market']} "
                f"{single['line']} {single['direction']} is on a drifted "
                f"market and carries no drift caveat"
            )
        assert checked, "no coupon row is on a drifted market -- nothing tested"

    def test_the_caveat_tells_the_row_which_way_the_drift_cuts(
        self, coupons, drifted
    ) -> None:
        """A row on the inflated side must be told so in those words.

        The generic sentence would be true on both sides and useless on both.
        What the operator needs is whether *this* row is the one flattered.
        """
        for single in coupons["singles"]:
            entry = drifted.get(single["market"])
            if entry is None:
                continue
            caveat = next(
                (c for c in single["caveats"] if "dryf próbki" in c), None
            )
            # Asserted rather than let StopIteration through: the sibling test
            # covers absence, and a bare next() here reports it as an error
            # rather than as the failure it is.
            assert caveat is not None, (
                f"single #{single['rank']} {single['market']} carries no drift "
                f"caveat to check the direction of"
            )
            if single["direction"] == entry["overstated_side"]:
                assert "wygląda pewniej, niż jest" in caveat, (
                    f"single #{single['rank']} is an "
                    f"{single['direction']} on a market whose "
                    f"{entry['overstated_side']} is overstated, so the caveat "
                    f"must say the row looks safer than it is: {caveat}"
                )
            else:
                assert "raczej zaniżony" in caveat, (
                    f"single #{single['rank']} is on the understated side and "
                    f"the caveat should say so: {caveat}"
                )

    def test_no_drifted_row_had_its_probability_quietly_adjusted(
        self, coupons, drifted
    ) -> None:
        """The drift is a statement, never a correction.

        ``p_central`` is a function of the sample and the line, so on a drifted
        market it must still equal what the sheet computed. This is the test
        that fails if somebody later decides to "just subtract the delta" --
        which is forbidden until ``validate_calibration.py`` shows out of sample
        that it helps, for the reason ``market_priors.json`` records against
        fitting a prior to the slates it was measured on.
        """
        sheet_path = RUN / f"{DATE}_event_dossiers_stats_sheet.json"
        if not sheet_path.exists():
            pytest.skip("stats sheet not on disk")
        rows = json.loads(sheet_path.read_text(encoding="utf-8"))["rows"]
        by_key = {
            (r["event_id"], r["market"], r.get("player_name") or r.get("team_name"),
             r["line"], r["direction"]): r
            for r in rows
        }
        checked = 0
        for single in coupons["singles"]:
            if single["market"] not in drifted:
                continue
            row = by_key.get((
                single["event_id"], single["market"], single.get("subject"),
                single["line"], single["direction"],
            ))
            if row is None:
                continue
            checked += 1
            assert single["p_central"] == pytest.approx(row["p_central"], abs=5e-5), (
                f"single #{single['rank']} {single['market']}: p_central "
                f"{single['p_central']} does not match the sheet's "
                f"{row['p_central']} -- the drift must not move a probability"
            )
        assert checked, "no drifted coupon row joined back to the sheet"


class TestTheBetBuilderDraft:
    """The third consumer, and the one the first fix missed.

    ``coupons.py`` and ``bet_builder_draft.py`` hold two separate
    implementations of the same caveat list -- one Polish, one English -- and
    on 2026-09-07 only the first learned about drift. ``draft_legs`` states as
    its own invariant that every gate a single passes a leg passes too, so a
    leg on ``cards_points_total`` with an empty ``caveats`` list while the
    single beside it carried the drift was that invariant failing quietly.

    Driven through ``draft_legs`` rather than the artifact, because the draft
    is generated on demand by the analyst and never written to ``runs/``. Costs
    no provider calls: sheet and offer both come off disk.
    """

    def test_a_drifted_leg_carries_the_caveat_and_names_the_side(
        self, drifted
    ) -> None:
        from bet.simple_stats.bet_builder_draft import draft_legs
        from bet.simple_stats.contracts import StatsSheetV1

        sheet_path = RUN / f"{DATE}_event_dossiers_stats_sheet.json"
        if not sheet_path.exists():
            pytest.skip("stats sheet not on disk")
        sheet = StatsSheetV1.model_validate_json(
            sheet_path.read_text(encoding="utf-8")
        )
        event_ids = sorted({row.event_id for row in sheet.rows})
        checked = 0
        for event_id in event_ids:
            draft = draft_legs(sheet, event_id, max_legs=4)
            for leg in draft.legs:
                entry = drifted.get(leg.market)
                if entry is None:
                    continue
                checked += 1
                caveat = next(
                    (c for c in leg.caveats if "sample drift" in c), None
                )
                assert caveat is not None, (
                    f"{event_id[:8]} leg {leg.market} {leg.line} "
                    f"{leg.direction} is on a drifted market and carries no "
                    f"drift caveat; it has: {leg.caveats}"
                )
                if leg.direction == entry["overstated_side"]:
                    assert "looks safer than it is" in caveat, caveat
                else:
                    assert "understated" in caveat, caveat
        if not checked:
            pytest.skip("no drafted leg on the day sits on a drifted market")

    def test_a_centred_leg_stays_silent(self, drifted) -> None:
        """The complement, without which a note on every leg would pass."""
        from bet.simple_stats.bet_builder_draft import draft_legs
        from bet.simple_stats.contracts import StatsSheetV1

        sheet_path = RUN / f"{DATE}_event_dossiers_stats_sheet.json"
        if not sheet_path.exists():
            pytest.skip("stats sheet not on disk")
        sheet = StatsSheetV1.model_validate_json(
            sheet_path.read_text(encoding="utf-8")
        )
        for event_id in sorted({row.event_id for row in sheet.rows}):
            for leg in draft_legs(sheet, event_id, max_legs=4).legs:
                if leg.market in drifted:
                    continue
                assert not any("sample drift" in c for c in leg.caveats), (
                    f"{leg.market} is not marked drifted but its leg claims a "
                    f"sample drift"
                )
