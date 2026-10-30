"""Line evidence's offset by d = curve - 1/odds (epochs.PRICE_GAP_OFFSET_FROM_UTC)."""

from __future__ import annotations

from datetime import timedelta

from bet.sofa import epochs
from bet.sofa import line_evidence as le


def _rows(n: int, game0: int, base: float, odds: float, wins: int) -> list[le.Row]:
    return [{"sport": "football", "key": "goals_for|OVER", "p": base, "base": base,
             "y": 1 if i < wins else 0, "game": f"g{game0 + i}", "odds": odds}
            for i in range(n)]


def _fitted() -> dict:
    # d < -0.05 (curve 0.80 at 1.10, 1/odds 0.909): 100 lines, 90 won (+0.10);
    # d >= 0.06 (curve 0.80 at 1.40, 1/odds 0.714): 100 lines, 60 won (-0.20).
    doc = le.fit(_rows(100, 0, 0.80, 1.10, 90) + _rows(100, 100, 0.80, 1.40, 60))
    doc["price_gap_shrink_k"] = le.PRICE_GAP_SHRINK_K
    return doc


def test_the_bucket_counts_the_edges_at_or_below_d() -> None:
    assert le.price_gap_bucket(0.80, 1.10) == "0"   # d -0.109
    assert le.price_gap_bucket(0.80, 1.22) == "1"   # d -0.020
    assert le.price_gap_bucket(0.80, 1.25) == "2"   # d 0.000: at the edge, above
    assert le.price_gap_bucket(0.80, 1.27) == "2"   # d +0.013
    assert le.price_gap_bucket(0.80, 1.31) == "3"   # d +0.037
    assert le.price_gap_bucket(0.80, 1.40) == "4"   # d +0.086


def test_fit_writes_the_key_and_sport_cells() -> None:
    doc = _fitted()
    key = doc["keys"]["football"]["goals_for|OVER"]["printable_by_gap"]
    assert key["0"]["n"] == 100 and abs(key["0"]["gap_sum"] - 10.0) < 1e-6
    assert abs(key["4"]["gap_sum"] + 20.0) < 1e-6
    sport = doc["sport_printable_by_gap"]["football"]
    assert sport["0"]["gap"] == 0.1 and sport["4"]["gap"] == -0.2


def test_on_a_leg_far_above_its_price_is_lowered_by_its_bucket() -> None:
    doc = _fitted()
    on = le.LineEvidence(doc, v2=True, price_gap_sports=frozenset({"football"}))
    off = le.LineEvidence(doc, v2=True)
    # key offset (one number): mean gap -0.05 over 200 lines
    assert off.offset("football", "goals_for|OVER") == -0.05
    high = on.read("football", "goals_for|OVER", 0.80, (0.80, "c", 500), 1.40)
    assert high is not None and high.offset == -0.2 and high.value == 0.6
    assert "sbd4" in high.source
    # the lines where the curve sat under the price over-realised: never raised
    low = on.read("football", "goals_for|OVER", 0.80, (0.80, "c", 500), 1.10)
    assert low is not None and low.offset == 0.0 and low.value == 0.8


def test_a_thin_key_cell_shrinks_to_the_sport_bucket() -> None:
    doc = _fitted()
    doc["keys"]["football"]["k2|UNDER"] = {"printable_by_gap": {
        "4": {"n": 20, "games": 20, "gap_sum": 0.0}}}
    ev = le.LineEvidence(doc, price_gap_sports=frozenset({"football"}))
    got = ev.gap_offset("football", "k2|UNDER", 0.80, 1.40)
    # (0 + 200 * -0.2) / (20 + 200)
    assert got == (round(-40.0 / 220, 4), "4")
    # a key with no cell in the bucket reads the sport's
    assert ev.gap_offset("football", "k3|OVER", 0.80, 1.40) == (-0.2, "4")


def test_off_sport_no_price_or_old_file_keep_the_key_offset() -> None:
    doc = _fitted()
    ev = le.LineEvidence(doc, v2=True, price_gap_sports=frozenset({"tennis"}))
    r = ev.read("football", "goals_for|OVER", 0.80, (0.80, "c", 500), 1.40)
    assert r is not None and r.offset == -0.05
    ev = le.LineEvidence(doc, v2=True, price_gap_sports=frozenset({"football"}))
    r = ev.read("football", "goals_for|OVER", 0.80, (0.80, "c", 500), None)
    assert r is not None and r.offset == -0.05
    old = dict(doc)
    old.pop("sport_printable_by_gap")
    ev = le.LineEvidence(old, v2=True, price_gap_sports=frozenset({"football"}))
    r = ev.read("football", "goals_for|OVER", 0.80, (0.80, "c", 500), 1.40)
    assert r is not None and r.offset == -0.05


def test_the_switch_opens_at_its_moment_for_three_sports() -> None:
    at = epochs.PRICE_GAP_OFFSET_FROM_UTC
    assert at is not None
    day = at.strftime("%Y-%m-%d")
    assert epochs.price_gap_offset_sports(day, at - timedelta(minutes=1)) == frozenset()
    assert epochs.price_gap_offset_sports(day, at) == frozenset(
        {"football", "tennis", "hockey"})
    assert epochs.price_gap_offset_sports("2026-10-29", at) == frozenset()
