import glob
import json

from bet.sofa.metrics import (
    FOOTBALL_METRICS,
    TENNIS_METRICS,
    GapReason,
    extract_flat_statistics,
    extract_metric,
)


def test_t11_no_fabrication():
    # Every recorded statistics payload, not a chosen few (T11 is a property).
    files = glob.glob("tests/fixtures/sofascore/event_*_statistics.json")
    assert len(files) > 0

    for f in files:
        with open(f) as fh:
            stats = json.load(fh)

        flat = extract_flat_statistics(stats.get("response", {}).get("body", {}))

        # Decide if tennis or football
        # event_15345277 is tennis
        # 16363633 is football
        sport = "tennis" if "15345277" in f else "football"
        metrics = TENNIS_METRICS if sport == "tennis" else FOOTBALL_METRICS

        # Check all metrics
        for metric in metrics:
            val = extract_metric(metric, sport, flat, None, {}, True)

            sofascore_key = metrics[metric]["sofascore"]

            # if we have no listing event, listing metrics should be STAT_KEY_ABSENT
            if sofascore_key in [
                "goals_from_listing",
                "goals_1h_from_listing",
                "goals_2h_from_listing",
                "sets_from_listing",
            ]:
                assert val == GapReason.STAT_KEY_ABSENT
                continue

            if sofascore_key == "cards_points_from_incidents":
                assert val == GapReason.NO_INCIDENTS
                continue

            if sofascore_key == "expectedGoals":
                assert val == GapReason.STAT_KEY_ABSENT
                continue

            # A key absent from the payload must produce STAT_KEY_ABSENT,
            # never a fabricated 0.0.
            #
            # Presence is asked of the period the metric declares, not always
            # "ALL" (F43), and of every underlying key for a metric that is a
            # sum of two (F45) — half of "aces + double faults" is not a
            # smaller version of the market, it is a different number.
            period = metrics[metric].get("period", "ALL")
            underlying = (
                ["aces", "doubleFaults"]
                if sofascore_key == "aces_plus_double_faults"
                else [sofascore_key]
            )

            if period not in flat:
                assert val == GapReason.NO_STATISTICS
                continue

            is_present = all(key in flat[period] for key in underlying)

            if not is_present:
                assert val == GapReason.STAT_KEY_ABSENT
            else:
                assert isinstance(val, float)


def test_a_missing_value_is_not_read_as_zero() -> None:
    """A stat item whose value the provider omitted must not become 0.0.

    This is the 2026-09-12 failure in miniature: invented fallback samples put
    43 of 64 rows on the VALUE list. A default of 0 inside the flattener is the
    quietest possible version of the same mistake, because the key IS present
    and downstream code has no way to tell.
    """
    payload = {
        "statistics": [
            {
                "period": "ALL",
                "groups": [
                    {
                        "statisticsItems": [
                            {"key": "cornerKicks", "homeValue": 5, "awayValue": 4},
                            {"key": "fouls", "homeValue": None, "awayValue": 11},
                            {"key": "offsides", "awayValue": 2},
                            {"key": "yellowCards", "homeValue": "n/a", "awayValue": 1},
                        ]
                    }
                ],
            }
        ]
    }
    flat = extract_flat_statistics(payload)
    assert flat["ALL"]["cornerKicks"] == (5.0, 4.0)
    for absent in ("fouls", "offsides", "yellowCards"):
        assert absent not in flat["ALL"], f"{absent} was fabricated"

    for metric, key in (("fouls_total", "fouls"), ("offsides_total", "offsides")):
        assert extract_metric(metric, "football", flat, None, {}, True) == (
            GapReason.STAT_KEY_ABSENT
        ), f"{metric} ({key}) reported a value it never received"


def test_zero_that_the_provider_really_sent_is_kept() -> None:
    """The mirror image: a genuine 0 is data and must survive."""
    payload = {
        "statistics": [
            {
                "period": "ALL",
                "groups": [
                    {
                        "statisticsItems": [
                            {"key": "offsides", "homeValue": 0, "awayValue": 0}
                        ]
                    }
                ],
            }
        ]
    }
    flat = extract_flat_statistics(payload)
    assert flat["ALL"]["offsides"] == (0.0, 0.0)
    assert extract_metric("offsides_total", "football", flat, None, {}, True) == 0.0
