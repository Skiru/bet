"""Two refusals on the day's product (2026-10-01).

FRIENDLY_FIXTURE: config/sofa_friendly_competitions.json kept friendlies out
of the samples only; 15 friendlies were the fixture itself (465 sheet rows,
16 VALUE). COUPON and CONFIDENCE refuse them.

LONG_SHOT: the absolute MAX_DISAGREEMENT admits a model claiming many times
the book's probability at a long price; the VALUE rows it let through at
market_p < 0.05 (09-18..09-30) won 0 of 75. COUPON refuses a single there.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from bet.sofa.contracts import FixtureOffer, PricedRung
from bet.sofa.coupon import MIN_MARKET_P_FOR_SINGLE, build_coupon
from bet.sofa.samples import FRIENDLY_COMPETITION_IDS, is_friendly_fixture
from tests.sofa.test_second_run_fixes import _fixture, _sheet_row

REPO = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 18, 10, 0, tzinfo=UTC)


def _run(row, fixture):  # type: ignore[no-untyped-def]
    fixture.kickoff_utc = NOW + timedelta(hours=8)
    offer = FixtureOffer(
        sofascore_event_id=row.sofascore_event_id,
        status="PRICED",
        rungs=[
            PricedRung(
                market=row.market,
                subject=row.subject,
                line=row.line,
                over_odds=row.offered_odds,
                under_odds=1.55,
                fetched_at_utc=NOW,
            )
        ],
        unmapped_markets=[],
    )
    return build_coupon(
        [row], [fixture], [offer], [], NOW, NOW + timedelta(minutes=15),
        timedelta(minutes=45),
    )


def test_a_friendly_fixture_never_reaches_the_singles() -> None:
    fixture = _fixture(1, ["x"])
    fixture.competition_id = 853  # Club Friendly Games
    fixture.competition_name = "Club Friendly Games"
    result = _run(_sheet_row(1), fixture)
    assert result.coupon.singles == []
    assert [d.reason for d in result.dropped] == ["FRIENDLY_FIXTURE"]


def test_a_league_fixture_is_not_touched_by_the_friendly_gate() -> None:
    fixture = _fixture(1, ["x"])
    result = _run(_sheet_row(1), fixture)
    assert "FRIENDLY_FIXTURE" not in [d.reason for d in result.dropped]


def test_the_friendly_test_reads_sport_and_the_config_ids() -> None:
    assert 853 in FRIENDLY_COMPETITION_IDS and 856 in FRIENDLY_COMPETITION_IDS
    assert is_friendly_fixture("football", 853)
    assert not is_friendly_fixture("tennis", 853)
    assert not is_friendly_fixture("football", None)
    # 2026-10-04: senior national-team friendlies (851) are friendlies too;
    # the women's (852) stay pending a decision.
    assert is_friendly_fixture("football", 851)
    assert not is_friendly_fixture("football", 852)


def test_a_long_shot_single_is_refused() -> None:
    row = _sheet_row(1, odds=27.0)
    row.market_p = 0.011  # Israel - Kosovo goals_total O6.5, 2026-10-01
    row.p_central = 0.074
    result = _run(row, _fixture(1, ["x"]))
    assert result.coupon.singles == []
    assert [d.reason for d in result.dropped] == ["LONG_SHOT"]


def test_the_long_shot_floor_is_strict() -> None:
    row = _sheet_row(1)
    row.market_p = MIN_MARKET_P_FOR_SINGLE
    result = _run(row, _fixture(1, ["x"]))
    assert "LONG_SHOT" not in [d.reason for d in result.dropped]


def test_confidence_refuses_a_friendly_fixture_too() -> None:
    src = (REPO / "scripts/sofa/run_confidence.py").read_text(encoding="utf-8")
    assert 'refused["FRIENDLY_FIXTURE"]' in src
    assert "is_friendly_fixture(" in src
