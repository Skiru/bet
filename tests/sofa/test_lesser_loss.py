"""Lesser-loss legs (operator 2026-11-11): bet.sofa.lesser_loss - the frozen
thresholds, the "pewna" tier, missing fields, the epoch switch, the sentence,
and its place in the coupon (annotation only). Measurement:
docs/sofa/evidence/mniej_zle_nogi_2026-11-11.md."""

from __future__ import annotations

import datetime
from typing import Any

from bet.sofa import coupon_html as ch
from bet.sofa import epochs
from bet.sofa import lesser_loss as ll
from scripts.sofa.build_coupon import assemble, render_md
from scripts.sofa.build_coupon_pdf import lesser_loss_label

UTC = datetime.UTC


def leg(eid: int = 1, conf: float = 0.80, odds: float = 1.22,
        overround: float | None = 0.07, sample: int | None = 20,
        **kw: Any) -> dict[str, Any]:
    return {"sofascore_event_id": eid, "sport": "football",
            "market": "goals_total", "subject": "", "line": 2.5,
            "direction": "OVER", "confidence": conf, "offered_odds": odds,
            "match": f"M{eid}", "kickoff_utc": "2026-11-12T18:00:00Z",
            "group_key": f"sofa:{eid}", "overround": overround,
            "sample_size": sample, **kw}


def test_the_thresholds_are_frozen() -> None:
    assert (ll.MAX_OVERROUND, ll.MIN_CONFIDENCE_MINUS_PRICE, ll.MIN_SAMPLE,
            ll.STRONG_MIN_CONFIDENCE) == (0.086, -0.047, 20, 0.85)


def test_a_leg_passing_all_three_is_marked() -> None:
    # 1 / 1.22 = 0.8197: 0.80 sits 1.97 pp under the price
    m = ll.annotate(leg())
    assert m is not None
    assert m["tier"] == "mniej_zla" and m["sample_size"] == 20
    assert m["confidence_minus_price"] == round(0.80 - 1 / 1.22, 4)


def test_each_threshold_alone_refuses() -> None:
    assert ll.annotate(leg(overround=0.086)) is None          # margin at the edge
    assert ll.annotate(leg(sample=19)) is None                # short sample
    assert ll.annotate(leg(conf=0.77, odds=1.20)) is None     # 6.3 pp under price
    # 1 / 1.20 = 0.8333: 0.786 sits 4.73 pp under (refused), 0.7866 4.67 pp
    assert ll.annotate(leg(conf=0.786, odds=1.20)) is None
    assert ll.annotate(leg(conf=0.7866, odds=1.20)) is not None


def test_missing_fields_are_never_marked() -> None:
    assert ll.annotate(leg(overround=None)) is None   # one-sided market
    assert ll.annotate(leg(sample=None)) is None
    assert ll.annotate({**leg(), "offered_odds": None}) is None
    assert ll.annotate({**leg(), "offered_odds": 1.0}) is None


def test_the_strong_tier_is_confidence_085() -> None:
    assert ll.annotate(leg(conf=0.85, odds=1.15))["tier"] == "pewna"  # type: ignore[index]
    assert ll.annotate(leg(conf=0.849, odds=1.15))["tier"] == "mniej_zla"  # type: ignore[index]


def test_the_switch_starts_on_2026_11_12_at_midnight() -> None:
    at = datetime.datetime(2026, 11, 12, 0, 0, tzinfo=UTC)
    assert epochs.lesser_loss_mark("2026-11-12", at) is True
    assert epochs.lesser_loss_mark("2026-11-13", at) is True
    assert epochs.lesser_loss_mark("2026-11-11", at) is False
    before = at - datetime.timedelta(minutes=1)
    assert epochs.lesser_loss_mark("2026-11-12", before) is False


def test_the_sentences_carry_the_measurement() -> None:
    plain = {"lesser_loss": ll.annotate(leg())}
    text = ll.label(plain)
    assert text.startswith("mniej zła noga") and "−1,7%" in text
    assert "nie przewaga" in text and "przed podatkiem" in text
    strong = {"lesser_loss": ll.annotate(leg(conf=0.88, odds=1.12))}
    st = ll.label(strong)
    assert st.startswith("PEWNA") and "90,4%" in st and "wybrany po obejrzeniu" in st
    assert ll.label(leg()) == ""


def _conf(singles: list[dict[str, Any]]) -> dict[str, Any]:
    return {"profile": "standard", "epoch": "stats_only", "created_at_utc": "x",
            "singles": singles, "legs": singles, "builders": []}


def test_the_coupon_is_the_same_and_says_it() -> None:
    marked = leg(1)
    plain = leg(2, overround=0.12)
    strong = leg(3, conf=0.88, odds=1.12)
    on = assemble(_conf([marked, plain, strong]), None, [], {}, "now",
                  "2026-11-12", lesser_loss_active=True)
    off = assemble(_conf([leg(1), leg(2, overround=0.12),
                          leg(3, conf=0.88, odds=1.12)]), None, [], {}, "now",
                   "2026-11-12")

    def key(d: dict[str, Any]) -> list[tuple[Any, ...]]:
        return [(s["sofascore_event_id"], s["market"], s["position"],
                 s["confidence"]) for s in d["singles"]]

    assert key(on) == key(off)
    assert on["lesser_loss"]["legs"] == 2 and off["lesser_loss"]["legs"] == 0
    assert all("lesser_loss" not in s for s in off["singles"])
    by_ev = {s["sofascore_event_id"]: s for s in on["singles"]}
    assert "mniej zła noga" in lesser_loss_label(by_ev[1])
    assert lesser_loss_label(by_ev[2]) == ""
    assert "PEWNA" in lesser_loss_label(by_ev[3])
    rows = {r["match"]: r for r in ch.build_view(on, "2026-11-12", None)["rows"]}
    assert rows["M1"]["lesser"] and not rows["M1"]["lesser_strong"]
    assert not rows["M2"]["lesser"] and rows["M2"]["lesser_loss"] == ""
    assert rows["M3"]["lesser_strong"]
    assert "mniej zła noga" in render_md(on, "2026-11-12")


def test_an_inactive_build_clears_an_old_mark() -> None:
    stale = {**leg(1), "lesser_loss": {"rule": "x", "tier": "pewna",
                                        "overround": 0.0,
                                        "confidence_minus_price": 0.0,
                                        "sample_size": 99}}
    off = assemble(_conf([stale]), None, [], {}, "now", "2026-11-12")
    assert "lesser_loss" not in off["singles"][0]
