from typing import Any

from bet.sofa.contracts import GapReason

FOOTBALL_METRICS = {
    "goals_total": {"sofascore": "goals_from_listing", "is_total": True},
    "goals_for": {"sofascore": "goals_from_listing", "is_total": False},
    "goals_1h_total": {"sofascore": "goals_1h_from_listing", "is_total": True},
    "goals_1h_for": {"sofascore": "goals_1h_from_listing", "is_total": False},
    "goals_2h_total": {"sofascore": "goals_2h_from_listing", "is_total": True},
    "goals_2h_for": {"sofascore": "goals_2h_from_listing", "is_total": False},
    "corners_total": {"sofascore": "cornerKicks", "is_total": True},
    "corners_for": {"sofascore": "cornerKicks", "is_total": False},
    "cards_total": {"sofascore": "yellowCards", "is_total": True},
    "cards_for": {"sofascore": "yellowCards", "is_total": False},
    "cards_points_total": {
        "sofascore": "cards_points_from_incidents",
        "is_total": True,
    },
    "cards_points_for": {"sofascore": "cards_points_from_incidents", "is_total": False},
    "fouls_total": {"sofascore": "fouls", "is_total": True},
    "fouls_for": {"sofascore": "fouls", "is_total": False},
    "offsides_total": {"sofascore": "offsides", "is_total": True},
    "offsides_for": {"sofascore": "offsides", "is_total": False},
    "shots_total": {"sofascore": "totalShotsOnGoal", "is_total": True},
    "shots_for": {"sofascore": "totalShotsOnGoal", "is_total": False},
    "shots_on_target_total": {"sofascore": "shotsOnGoal", "is_total": True},
    "shots_on_target_for": {"sofascore": "shotsOnGoal", "is_total": False},
    "xg_total": {"sofascore": "expectedGoals", "is_total": True},
    "xg_for": {"sofascore": "expectedGoals", "is_total": False},
}

TENNIS_METRICS = {
    "games_total": {"sofascore": "gamesWon", "is_total": True},
    "games_won_for": {"sofascore": "gamesWon", "is_total": False},
    "sets_total": {"sofascore": "sets_from_listing", "is_total": True},
    "aces_total": {"sofascore": "aces", "is_total": True},
    "aces_for": {"sofascore": "aces", "is_total": False},
    "double_faults_total": {"sofascore": "doubleFaults", "is_total": True},
    "double_faults_for": {"sofascore": "doubleFaults", "is_total": False},
    "tiebreaks_total": {"sofascore": "tiebreaks", "is_total": True},
}


def extract_flat_statistics(
    statistics: dict[str, Any] | None,
) -> dict[str, dict[str, tuple[float, float]]]:
    """Flatten /statistics into ``{period: {key: (home, away)}}``.

    Search is flat across every group of a period (PULAPKA #2): ``offsides``
    lives under ``Attack``, ``shotsOnGoal`` under ``Shots``, and filtering on
    ``groupName == "Match overview"`` loses half the table in silence.

    A key whose value is missing or non-numeric is **omitted**, never defaulted
    to 0.0 — a zero the provider never sent is the fabrication this pipeline
    exists to avoid (L1/L2).
    """
    flat: dict[str, dict[str, tuple[float, float]]] = {}
    if not statistics:
        return flat
    for period in statistics.get("statistics", []):
        period_name = period.get("period", "ALL")
        bucket = flat.setdefault(period_name, {})
        for group in period.get("groups", []):
            for item in group.get("statisticsItems", []):
                key = item.get("key")
                if not key:
                    continue
                raw_home = item.get("homeValue")
                raw_away = item.get("awayValue")
                if raw_home is None or raw_away is None:
                    continue
                try:
                    bucket[key] = (float(raw_home), float(raw_away))
                except (TypeError, ValueError):
                    continue
    return flat


def infer_best_of(event: dict[str, Any]) -> int | None:
    """Match format (3 or 5) for a *completed* tennis match, from the listing.

    ``defaultPeriodCount`` is the field that states the format, but it lives on
    ``/event/{id}`` only — it is absent from all 30 events of the recorded
    listing ``evidence/team_275923_events_last_0.json``. Filtering a sample on
    it against a listing therefore rejects every historical match and leaves
    tennis with no sample at all, which looks exactly like missing data (L14).

    The listing does decide the question, though, without another call: the
    winner's ``current`` is the number of sets they won, and that number is
    unambiguous.

        3 sets won -> best of 5   (a best-of-3 cannot reach three)
        2 sets won -> best of 3   (a best-of-5 winner needs three)

    Anything else (a retirement, an abandoned match) returns None, and the
    caller must not guess. Verified against the recorded listing: event
    15345277 (Australian Open) reads 3 -> BO5, event 15543167 (Doha) reads
    2 -> BO3.
    """
    home = event.get("homeScore")
    away = event.get("awayScore")
    if not isinstance(home, dict) or not isinstance(away, dict):
        return None
    home_sets = home.get("current")
    away_sets = away.get("current")
    if not isinstance(home_sets, int) or not isinstance(away_sets, int):
        return None

    sets_won = max(home_sets, away_sets)
    if sets_won == 3:
        return 5
    if sets_won == 2:
        return 3
    return None


def _incident_player_key(incident: dict[str, Any]) -> str | None:
    """Stable identity for the player an incident belongs to."""
    player = incident.get("player")
    if isinstance(player, dict) and player.get("id") is not None:
        return f"id:{player['id']}"
    name = incident.get("playerName")
    if isinstance(name, dict):
        name = name.get("name")
    if name:
        return f"name:{name}"
    return None


def calculate_cards_points(
    incidents: dict[str, Any] | None,
) -> tuple[float, float] | GapReason:
    """Superbet card points from /incidents (PLAN §5.4).

    Scoring: yellow = 1, straight red = 2, and a dismissal for a second yellow
    is worth 3 in total.

    §5.4a asked for one number to be measured: is ``yellowRed`` worth +1 (because
    Sofascore already emitted both yellows) or +3 (because it emitted none)?
    We do not answer it with a constant. The payload answers it per match: count
    how many ``yellow`` incidents that same player already carries and pay the
    remainder up to 3. That is correct under either convention — including a
    third one nobody predicted, where Sofascore emits exactly one yellow — so
    the family is right without a measurement, and stays right if Sofascore
    changes its mind.

    ``rescinded`` cards are dropped unconditionally (PULAPKA #4); a rescinded
    yellow also stops counting toward the second-yellow arithmetic, which is
    what the disciplinary record says happened.
    """
    if incidents is None:
        # A missing payload is not a zero (L3).
        return GapReason.NO_INCIDENTS

    cards = [
        inc
        for inc in incidents.get("incidents", [])
        if inc.get("incidentType") == "card" and not inc.get("rescinded", False)
    ]

    yellows_by_player: dict[str, int] = {}
    for inc in cards:
        if inc.get("incidentClass") == "yellow":
            key = _incident_player_key(inc)
            if key:
                yellows_by_player[key] = yellows_by_player.get(key, 0) + 1

    home = 0.0
    away = 0.0
    for inc in cards:
        cls = inc.get("incidentClass")
        if cls == "yellow":
            pts = 1.0
        elif cls == "red":
            pts = 2.0
        elif cls == "yellowRed":
            key = _incident_player_key(inc)
            already = yellows_by_player.get(key, 0) if key else 0
            # A second-yellow dismissal is 3 points in total; pay only the part
            # the separate yellow incidents have not already paid.
            pts = float(max(0, 3 - already))
        else:
            continue

        if inc.get("isHome", False):
            home += pts
        else:
            away += pts

    return home, away


# Counting statistics whose halves must add up to the full-match figure.
# Reported, never blocking: 0.9-2.2% divergence is the normal noise floor for
# this class of data, so rejecting on it would throw away good observations.
HALVES_CHECKED_KEYS = (
    "cornerKicks",
    "yellowCards",
    "fouls",
    "offsides",
    "totalShotsOnGoal",
    "shotsOnGoal",
)


def check_halves_identity(
    flat_stats: dict[str, dict[str, tuple[float, float]]],
) -> list[str]:
    """1ST + 2ND == ALL for counting keys (PLAN §5.5, reported not blocking)."""
    divergences: list[str] = []
    all_stats = flat_stats.get("ALL")
    first = flat_stats.get("1ST")
    second = flat_stats.get("2ND")
    if not all_stats or not first or not second:
        return divergences

    for key in HALVES_CHECKED_KEYS:
        if key not in all_stats or key not in first or key not in second:
            continue
        for side in (0, 1):
            halves = first[key][side] + second[key][side]
            whole = all_stats[key][side]
            if abs(halves - whole) > 1e-6:
                divergences.append(
                    f"{key}[{'home' if side == 0 else 'away'}]: "
                    f"1ST+2ND={halves:g} != ALL={whole:g}"
                )
    return divergences


def check_identities(
    flat_stats: dict[str, dict[str, tuple[float, float]]],
    incidents: dict[str, Any] | None,
    listing_event: dict[str, Any],
    sport: str,
) -> GapReason | None:
    """The four blocking internal identities of PLAN §5.5.

    With one provider there is nobody to disagree with, so the payload has to
    disagree with itself. A divergence here is a transcription signal, not
    noise: the observation is rejected, never averaged.
    """
    if "ALL" in flat_stats:
        stats = flat_stats["ALL"]
        if (
            "totalShotsOnGoal" in stats
            and "shotsOnGoal" in stats
            and "shotsOffGoal" in stats
            and "blockedScoringAttempt" in stats
        ):
            for side in (0, 1):
                s_on = stats["shotsOnGoal"][side]
                s_off = stats["shotsOffGoal"][side]
                s_blk = stats["blockedScoringAttempt"][side]
                s_tot = stats["totalShotsOnGoal"][side]
                if s_on + s_off + s_blk != s_tot:
                    return GapReason.INTERNAL_INCONSISTENT

    if sport == "football" and incidents is not None:
        goal_incs = sum(
            1
            for i in incidents.get("incidents", [])
            if i.get("incidentType") == "goal" and not i.get("rescinded", False)
        )
        hs = listing_event.get("homeScore", {})
        as_ = listing_event.get("awayScore", {})

        c_h = hs.get("current")
        c_a = as_.get("current")

        if c_h is not None and c_a is not None:
            # Extra time / penalties goals might be excluded or included.
            # In regular matches without ET, current = normaltime.
            if hs.get("normaltime") is not None and hs.get("normaltime") == c_h:
                if goal_incs != c_h + c_a:
                    return GapReason.INTERNAL_INCONSISTENT

    if sport == "football":
        hs = listing_event.get("homeScore", {})
        if "period1" in hs and "period2" in hs and "normaltime" in hs:
            if hs["period1"] + hs["period2"] != hs["normaltime"]:
                return GapReason.INTERNAL_INCONSISTENT

    if sport == "tennis":
        if "ALL" in flat_stats and "gamesWon" in flat_stats["ALL"]:
            hs = listing_event.get("homeScore", {})
            as_ = listing_event.get("awayScore", {})
            set_keys = [f"period{i}" for i in range(1, 6)]
            home_sets = sum(hs.get(k, 0) for k in set_keys if k in hs)
            away_sets = sum(as_.get(k, 0) for k in set_keys if k in as_)

            # tiebreak games might need to be included?
            # The rule says: "suma gamesWon obu stron == suma gemów z wyniku setowego"
            # periodNTieBreak holds points, not games; the set score (7-6)
            # already counts the tie-break game itself.

            home_stat = flat_stats["ALL"]["gamesWon"][0]
            away_stat = flat_stats["ALL"]["gamesWon"][1]
            if home_sets != home_stat or away_sets != away_stat:
                return GapReason.INTERNAL_INCONSISTENT

    return None


def extract_metric(
    metric_name: str,
    sport: str,
    flat_stats: dict[str, dict[str, tuple[float, float]]],
    incidents: dict[str, Any] | None,
    listing_event: dict[str, Any],
    is_home: bool,
) -> float | GapReason:
    metrics_map = FOOTBALL_METRICS if sport == "football" else TENNIS_METRICS
    if metric_name not in metrics_map:
        return GapReason.STAT_KEY_ABSENT

    config = metrics_map[metric_name]
    sofascore_key = config["sofascore"]
    is_total = config["is_total"]

    if sofascore_key == "goals_from_listing":
        h = listing_event.get("homeScore", {}).get("current")
        a = listing_event.get("awayScore", {}).get("current")
        if h is None or a is None:
            return GapReason.STAT_KEY_ABSENT
        return float(h + a) if is_total else float(h if is_home else a)

    if sofascore_key == "goals_1h_from_listing":
        h = listing_event.get("homeScore", {}).get("period1")
        a = listing_event.get("awayScore", {}).get("period1")
        if h is None or a is None:
            return GapReason.STAT_KEY_ABSENT
        return float(h + a) if is_total else float(h if is_home else a)

    if sofascore_key == "goals_2h_from_listing":
        h = listing_event.get("homeScore", {}).get("period2")
        a = listing_event.get("awayScore", {}).get("period2")
        if h is None or a is None:
            return GapReason.STAT_KEY_ABSENT
        return float(h + a) if is_total else float(h if is_home else a)

    if sofascore_key == "cards_points_from_incidents":
        pts = calculate_cards_points(incidents)
        if isinstance(pts, GapReason):
            return pts
        h, a = pts
        return float(h + a) if is_total else float(h if is_home else a)

    if sofascore_key == "sets_from_listing":
        # Both players contest the same sets, so "sets played" is the count of
        # period keys either score carries — not a per-side figure.
        home_score = listing_event.get("homeScore", {})
        away_score = listing_event.get("awayScore", {})
        set_keys = [f"period{i}" for i in range(1, 6)]
        played_sets = sum(1 for k in set_keys if k in home_score or k in away_score)
        if played_sets == 0:
            return GapReason.STAT_KEY_ABSENT
        return float(played_sets)

    if sofascore_key == "expectedGoals" and not listing_event.get("hasXg", False):
        return GapReason.STAT_KEY_ABSENT

    # Default stats lookup
    if "ALL" not in flat_stats:
        return GapReason.NO_STATISTICS

    stats = flat_stats["ALL"]
    if sofascore_key not in stats:
        return GapReason.STAT_KEY_ABSENT

    h, a = stats[sofascore_key]
    return float(h + a) if is_total else float(h if is_home else a)
