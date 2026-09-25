"""A leg is timed against the price it carries, not against a fresher one.

2026-09-25: SHEET ran at 04:19Z, OFFER was refreshed at 04:31Z and CONFIDENCE
ran 15 s later - the order sofa-rebuild prescribes. The sheet's `offered_odds`
were the older price, the STALE_PRICE gate timed the fresh offer, and 16 of
351 variant legs printed a price Superbet no longer quoted; two failed
confidence x odds >= 0.90 at the live price. The fix refuses such a leg
(PRICE_MOVED_SINCE_SHEET) instead of swapping the price in, because market_p,
p_central and required_odds were all derived from the old one.

The same hole existed for a side the refresh stopped pricing at all:
run_confidence.py recorded a timestamp for OVER and UNDER even when one of
them had no odds, so a withdrawn side passed NO_FETCHED_AT at its old price.

Also here, since they were found in the same review: CONFIDENCE ignored
SOFA_PRICE_MAX_AGE_MIN (COUPON honoured it), the confidence artifacts carried
no UNFITTED_CONSTANTS, and the variant's PDF quoted the official 10.5% margin
as its own limit.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.contracts import Fixture, FixtureOffer, PricedRung, SheetRow
from bet.sofa.coupon import build_coupon
from tests.sofa.test_confidence_wariant_profile import (
    DAY,
    NOW,
    ODDS_A,
    ODDS_B,
    P_A,
    P_B,
    UNDER_A,
    UNDER_B,
    _fixture,
    _offer,
    _pdf_text,
    _run,
    _samples,
    _sheet_row,
)

# ---------------------------------------------------------------------------
# COUPON
# ---------------------------------------------------------------------------

T = datetime(2026, 9, 17, 10, 0, tzinfo=UTC)


def _coupon_row() -> SheetRow:
    return SheetRow(
        sofascore_event_id=1,
        sport="football",
        market="shots_on_target_for",
        subject="Player A",
        line=1.5,
        direction="OVER",
        sample_size=10,
        sample_mean=2.5,
        sample_sd=1.0,
        centre=2.2,
        p_central=0.7,
        market_p=0.66,
        ladder_centre=None,
        ladder_sigma=None,
        p_bar=0.6,
        bar_reason=None,
        required_odds=1.75,
        offered_odds=2.0,
        edge=0.2,
        surplus=0.25,
        verdict="VALUE",
        notes=[],
    )


def _coupon_fixture() -> Fixture:
    return Fixture(
        sofascore_event_id=1,
        superbet_event_ids=["S1"],
        sport="football",
        kickoff_utc=datetime(2026, 9, 17, 20, 0, tzinfo=UTC),
        home_name="Home",
        away_name="Away",
        home_entity_id=10,
        away_entity_id=20,
        competition_name="League",
        competition_id=100,
        season_id=200,
        category_name="Country",
        identity="CONFIRMED",
        round_number=1,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type=None,
        default_period_count=None,
    )


def _coupon(over_odds: float | None) -> Any:
    offer = FixtureOffer(
        sofascore_event_id=1,
        unmapped_markets=[],
        rungs=[
            PricedRung(
                market="shots_on_target_for",
                subject="Player A",
                line=1.5,
                over_odds=over_odds,
                under_odds=2.0,
                fetched_at_utc=T,
            )
        ],
    )
    return build_coupon(
        sheet_rows=[_coupon_row()],
        fixtures=[_coupon_fixture()],
        offers=[offer],
        vetoes=[],
        current_time=T,
        min_kickoff=T + timedelta(minutes=15),
        max_price_age=timedelta(minutes=45),
    )


def test_the_coupon_keeps_a_row_whose_price_did_not_move() -> None:
    result = _coupon(2.0)
    assert [s.sofascore_event_id for s in result.coupon.singles] == [1]


def test_the_coupon_refuses_a_row_whose_price_moved_after_sheet() -> None:
    result = _coupon(1.9)
    assert result.coupon.singles == []
    [dropped] = result.dropped
    assert dropped.reason == "PRICE_MOVED_SINCE_SHEET"
    assert "2.0" in dropped.detail and "1.9" in dropped.detail


def test_the_coupon_refuses_a_side_the_refresh_no_longer_prices() -> None:
    result = _coupon(None)
    assert result.coupon.singles == []
    assert [d.reason for d in result.dropped] == ["STALE_PRICE"]


# ---------------------------------------------------------------------------
# CONFIDENCE, end to end through the script
# ---------------------------------------------------------------------------


def _day(tmp_path: Path, offers: list[dict[str, Any]], notes: list[str]) -> Path:
    run = tmp_path / DAY
    run.mkdir()
    rows = [
        _sheet_row(1, P_A, ODDS_A, P_A - 0.03),
        _sheet_row(2, P_B, ODDS_B, P_B - 0.03),
    ]
    for r in rows:
        r["notes"] = list(notes)
    (run / "02_fixtures.json").write_text(json.dumps([_fixture(1), _fixture(2)]))
    (run / "03_samples.json").write_text(json.dumps([_samples(1), _samples(2)]))
    (run / "04_offer.json").write_text(json.dumps(offers))
    (run / "05_sheet.json").write_text(json.dumps(rows))
    (run / "vetoes.json").write_text("[]")
    return tmp_path


def _variant(day: Path, env: dict[str, str] | None = None) -> dict[str, Any]:
    proc = _run(
        "run_confidence.py", day, "--runs-dir", str(day), "--profile", "wariant",
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    return dict(json.loads((day / DAY / "08_confidence_wariant.json").read_text()))


def _single_ids(doc: dict[str, Any]) -> set[int]:
    return {s["sofascore_event_id"] for s in doc["singles"]}


def test_confidence_ships_both_legs_when_the_offer_matches_the_sheet(
    tmp_path: Path,
) -> None:
    offers = [_offer(1, ODDS_A, UNDER_A), _offer(2, ODDS_B, UNDER_B)]
    assert _single_ids(_variant(_day(tmp_path, offers, []))) == {1, 2}


def test_confidence_refuses_a_leg_whose_price_moved_after_sheet(
    tmp_path: Path,
) -> None:
    # Leg 2's OVER moved 1.30 -> 1.24 in the refresh; the sheet still says 1.30.
    offers = [_offer(1, ODDS_A, UNDER_A), _offer(2, 1.24, UNDER_B)]
    doc = _variant(_day(tmp_path, offers, []))
    assert _single_ids(doc) == {1}
    assert all(leg["sofascore_event_id"] != 2 for leg in doc["legs"])


def test_confidence_refuses_a_side_the_refresh_no_longer_prices(
    tmp_path: Path,
) -> None:
    withdrawn = _offer(2, ODDS_B, UNDER_B)
    withdrawn["rungs"][0]["over_odds"] = None
    offers = [_offer(1, ODDS_A, UNDER_A), withdrawn]
    doc = _variant(_day(tmp_path, offers, []))
    assert _single_ids(doc) == {1}
    # Not merely missing from the singles (the margin filter did that much):
    # gone from the leg pool the builders are made of.
    assert all(leg["sofascore_event_id"] != 2 for leg in doc["legs"])


def test_confidence_honours_the_price_age_the_coupon_honours(
    tmp_path: Path,
) -> None:
    offers = [_offer(1, ODDS_A, UNDER_A), _offer(2, ODDS_B, UNDER_B)]
    old = (NOW - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    for o in offers:
        o["rungs"][0]["fetched_at_utc"] = old
    day = _day(tmp_path, offers, [])
    assert _single_ids(_variant(day)) == {1, 2}  # 30 min < the default 45
    assert _single_ids(_variant(day, env={"SOFA_PRICE_MAX_AGE_MIN": "20"})) == set()


def test_confidence_artifacts_carry_unfitted_constants(tmp_path: Path) -> None:
    offers = [_offer(1, ODDS_A, UNDER_A), _offer(2, ODDS_B, UNDER_B)]
    day = _day(tmp_path, offers, ["UNFITTED_CONSTANTS: K_PRICE, W_FOOTBALL_RATING"])
    doc = _variant(day)
    assert doc["unfitted_constants"] == ["K_PRICE", "W_FOOTBALL_RATING"]
    assert all(
        s["unfitted_constants"] == ["K_PRICE", "W_FOOTBALL_RATING"]
        for s in doc["singles"]
    )
    md = (day / DAY / "08_confidence_wariant.md").read_text()
    assert "UNFITTED_CONSTANTS: K_PRICE, W_FOOTBALL_RATING" in md


@pytest.mark.parametrize(
    ("profile", "margin"), [("standard", "10.5%"), ("wariant", "15.0%")]
)
def test_the_pdf_quotes_the_margin_its_own_artifact_was_selected_under(
    tmp_path: Path, profile: str, margin: str
) -> None:
    offers = [_offer(1, ODDS_A, UNDER_A), _offer(2, ODDS_B, UNDER_B)]
    day = _day(tmp_path, offers, [])
    args = ("--runs-dir", str(day), "--profile", profile)
    assert _run("run_confidence.py", day, *args).returncode == 0
    pdf = _run("build_coupon_pdf.py", day, *args)
    assert pdf.returncode == 0, pdf.stderr
    suffix = "_WARIANT" if profile == "wariant" else ""
    text = " ".join(_pdf_text(day / DAY / f"KUPON_{DAY}{suffix}.pdf").split())
    assert f"Powyżej {margin} noga nie trafia" in text
    if profile == "wariant":
        assert "Powyżej 10.5% noga" not in text
