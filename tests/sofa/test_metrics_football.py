import json

from bet.sofa.metrics import check_identities, extract_flat_statistics, extract_metric


def test_t08a_shots_identity():
    with open("tests/fixtures/sofascore/event_16363633_statistics.json") as f:
        stats = json.load(f)

    flat = extract_flat_statistics(stats.get("response", {}).get("body", {}))
    # home = Brighton, away = Arsenal
    assert flat["ALL"]["shotsOnGoal"][0] == 6  # Arsenal shots on target
    assert flat["ALL"]["shotsOffGoal"][0] == 6
    assert flat["ALL"]["blockedScoringAttempt"][0] == 8
    assert flat["ALL"]["totalShotsOnGoal"][0] == 20

    res = check_identities(flat, None, {}, "football")
    assert res is None  # No inconsistency

    val = extract_metric("shots_on_target_for", "football", flat, None, {}, True)
    assert val == 6.0

    val_tot = extract_metric("shots_for", "football", flat, None, {}, True)
    assert val_tot == 20.0


def test_t08b_flat_search():
    # offsides is in Attack, not Match overview. Should be found.
    with open("tests/fixtures/sofascore/event_16363633_statistics.json") as f:
        stats = json.load(f)
    flat = extract_flat_statistics(stats.get("response", {}).get("body", {}))
    assert "offsides" in flat["ALL"]


def test_t08c_goals_from_listing():
    listing_event = {
        "homeScore": {"current": 2, "period1": 1, "period2": 1, "normaltime": 2},
        "awayScore": {"current": 1, "period1": 0, "period2": 1, "normaltime": 1},
    }
    # No statistics provided
    res = extract_metric("goals_total", "football", {}, None, listing_event, True)
    assert res == 3.0

    res = extract_metric("goals_1h_for", "football", {}, None, listing_event, True)
    assert res == 1.0


# --------------------------------------------------------------------------
# §5.5, last row: halves are REPORTED, never blocking.
# --------------------------------------------------------------------------


def _period_payload(all_v, first_v, second_v):
    def block(period, value):
        return {
            "period": period,
            "groups": [
                {
                    "statisticsItems": [
                        {"key": "cornerKicks", "homeValue": value, "awayValue": 0}
                    ]
                }
            ],
        }

    return {
        "statistics": [
            block("ALL", all_v),
            block("1ST", first_v),
            block("2ND", second_v),
        ]
    }


def test_halves_that_add_up_report_nothing():
    from bet.sofa.metrics import check_halves_identity, extract_flat_statistics

    flat = extract_flat_statistics(_period_payload(10, 6, 4))
    assert check_halves_identity(flat) == []


def test_halves_that_disagree_are_reported():
    from bet.sofa.metrics import check_halves_identity, extract_flat_statistics

    flat = extract_flat_statistics(_period_payload(10, 6, 3))
    divergences = check_halves_identity(flat)
    assert divergences
    assert "cornerKicks" in divergences[0]


def test_a_halves_divergence_does_not_reject_the_observation():
    """0.9-2.2% divergence is the normal noise floor for this class of data.

    Blocking on it would throw away good observations; the four identities in
    check_identities are the ones that block.
    """
    from bet.sofa.metrics import (
        check_identities,
        extract_flat_statistics,
        extract_metric,
    )

    flat = extract_flat_statistics(_period_payload(10, 6, 3))
    listing = {
        "homeScore": {"current": 1, "period1": 1, "period2": 0, "normaltime": 1},
        "awayScore": {"current": 0, "period1": 0, "period2": 0, "normaltime": 0},
    }
    assert check_identities(flat, None, listing, "football") is None
    assert (
        extract_metric("corners_total", "football", flat, None, listing, True) == 10.0
    )


def test_halves_are_silent_when_only_all_period_was_published():
    from bet.sofa.metrics import check_halves_identity, extract_flat_statistics

    payload = {
        "statistics": [
            {
                "period": "ALL",
                "groups": [
                    {
                        "statisticsItems": [
                            {"key": "cornerKicks", "homeValue": 10, "awayValue": 4}
                        ]
                    }
                ],
            }
        ]
    }
    assert check_halves_identity(extract_flat_statistics(payload)) == []
