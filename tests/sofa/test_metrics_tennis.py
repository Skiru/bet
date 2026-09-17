import json

from bet.sofa.metrics import extract_flat_statistics, extract_metric


def test_t09_tennis_metrics():
    with open("tests/fixtures/sofascore/event_15345277_statistics.json") as f:
        stats = json.load(f)

    flat = extract_flat_statistics(stats.get("response", {}).get("body", {}))

    # 5.7 details:
    # serviceGamesTotal 17 + 17 = 34
    # gamesWon 20 + 15 = 35

    games_home = flat["ALL"]["gamesWon"][0]
    games_away = flat["ALL"]["gamesWon"][1]
    assert games_home == 20
    assert games_away == 15

    games_total = extract_metric("games_total", "tennis", flat, None, {}, True)
    assert games_total == 35.0

    # aces
    # T09: "aces_total = suma obu stron (2+7=9), nie 2"
    aces_home = flat["ALL"]["aces"][0]
    aces_away = flat["ALL"]["aces"][1]
    # Check if they are 2 and 7
    assert aces_home + aces_away == 9.0

    aces_total = extract_metric("aces_total", "tennis", flat, None, {}, True)
    assert aces_total == 9.0

    # sets_total
    listing_event = {
        "homeScore": {"period1": 7, "period2": 6, "period3": 7},
        "awayScore": {"period1": 6, "period2": 4, "period3": 5},
    }
    sets_total = extract_metric("sets_total", "tennis", flat, None, listing_event, True)
    assert sets_total == 3.0


# --------------------------------------------------------------------------
# Match format from the listing (§5.7).
# --------------------------------------------------------------------------


def test_best_of_is_inferred_from_the_recorded_listing() -> None:
    """`defaultPeriodCount` is absent from every listing event.

    Verified against docs/sofascore-api/evidence/team_275923_events_last_0.json:
    30 of 30 events carry `groundType`, 0 of 30 carry `defaultPeriodCount`.
    Filtering a sample on that field therefore rejects every historical match
    and leaves tennis with no sample — a gate nobody can pass, which reads as
    missing data (L14).
    """
    import json as _json

    from bet.sofa.metrics import infer_best_of

    body = _json.load(
        open("docs/sofascore-api/evidence/team_275923_events_last_0.json")
    )["response"]["body"]
    events = {e["id"]: e for e in body["events"]}

    assert sum("defaultPeriodCount" in e for e in body["events"]) == 0
    assert sum("groundType" in e for e in body["events"]) == len(body["events"])

    # Australian Open: won 3 sets to 0 -> only a best-of-5 reaches three.
    assert infer_best_of(events[15345277]) == 5
    # Doha: won 2 sets to 0 -> a best-of-5 winner would need three.
    assert infer_best_of(events[15543167]) == 3


def test_best_of_returns_none_when_the_listing_cannot_decide() -> None:
    from bet.sofa.metrics import infer_best_of

    assert (
        infer_best_of({"homeScore": {"current": 1}, "awayScore": {"current": 0}})
        is None
    )
    assert infer_best_of({"homeScore": {}, "awayScore": {}}) is None
    assert infer_best_of({}) is None


def test_every_recorded_tennis_event_resolves_to_three_or_five() -> None:
    """Across the whole recorded listing, the rule is decisive, not occasional."""
    import json as _json

    from bet.sofa.metrics import infer_best_of

    body = _json.load(
        open("docs/sofascore-api/evidence/team_275923_events_last_0.json")
    )["response"]["body"]
    resolved = [infer_best_of(e) for e in body["events"]]
    decided = [r for r in resolved if r is not None]
    assert set(decided) <= {3, 5}
    assert len(decided) >= 25, "the rule must decide the overwhelming majority"
