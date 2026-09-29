"""F54 — per-player football markets, from `/event/{id}/lineups`.

Everything else in this pipeline is measured on a *side*: a team's corners, a
player's games in tennis, where the player IS the side. Superbet also prices
the individual footballer — "Zawodnik - liczba strzalow", 283 selections on one
MLS fixture alone — and until now every one of those landed in
`unmapped_markets`.

Three things make this family different from every other one, and each of them
is a way to get it wrong:

**One call serves every player.** `/event/{id}/player/{playerId}/statistics`
would be one request per player per historical match — for a 20-man squad over
a ten-match sample that is 200 requests for one fixture's shot market, on a
bridge whose whole capacity is 11.7 req/s. `/event/{id}/lineups` carries the
same per-player statistics for both squads in a single payload, and SAMPLES
already visits exactly these events for the team metrics. So a player sample
costs one extra request per historical event, not two hundred.

**The sample is the player's appearances, not the team's matches.** A squad
member who did not take the pitch has `totalShots: 0` in the payload and no
`minutesPlayed` at all. Counting that as a zero would be the L1/L2 fabrication
in its purest form, and it would be wrong about the bet too: Superbet voids a
player market when the player does not play, it does not settle it at zero.
`minutesPlayed` is therefore the appearance gate, and it is the only one.

**A missing statistic here sometimes IS a zero, and we have to prove which.**
`goalAssist` is written for all 31 players who appeared in the recorded payload
(`docs/sofa/evidence/event_16363633_lineups.json`), so a missing one is missing
data. `onTargetScoringAttempt` is written for only 6 of those 31 — Sofascore
omits it when the player had none. Defaulting it to zero would normally be the
forbidden move; here it is provable, because the payload carries the
decomposition:

    totalShots == onTargetScoringAttempt + shotOffTarget
                  + blockedScoringAttempt + hitWoodwork

which held for 31 of 31 appearing players. So the zero is taken only when that
identity closes with it, and refused as INTERNAL_INCONSISTENT when it does not.
A metric with no such identity available does not get a defaulted zero at all,
which is why `totalOffside` is not in this table (see the note there).
"""

from __future__ import annotations

from typing import Any

from bet.sofa.contracts import GapReason
from bet.sofa.names import normalize_name

# The per-player quantities Superbet prices as a ladder AND Sofascore reports
# in `/lineups`. Both halves are required: a metric with no market is a call we
# pay for and cannot bet (A5), and a market with no metric is a row with no
# sample behind it.
#
# `zero_when_absent` says whether Sofascore omits the key for a player whose
# value was zero. When it is True, `identity` names the decomposition that must
# close for the zero to be taken.
PLAYER_METRICS: dict[str, dict[str, Any]] = {
    "player_shots_for": {
        "sofascore": "totalShots",
        # Present for every player in the payload, appearing or not — 40 of
        # 40. Nothing to infer.
        "zero_when_absent": False,
    },
    "player_shots_on_target_for": {
        "sofascore": "onTargetScoringAttempt",
        # Present for 6 of the 31 who appeared. The other 25 had no shot on
        # target, and the shots decomposition proves it.
        "zero_when_absent": True,
        "identity": (
            "totalShots",
            (
                "onTargetScoringAttempt",
                "shotOffTarget",
                "blockedScoringAttempt",
                "hitWoodwork",
            ),
        ),
    },
    "player_assists_for": {
        "sofascore": "goalAssist",
        # Present for 31 of the 31 who appeared, including every zero.
        "zero_when_absent": False,
    },
    # 2026-09-29: the four below are omitted on a zero (present for 9-50% of
    # appearing players over 400 cached matches), and no in-player
    # decomposition proves the zero. The TEAM figure does: over ~1,550
    # team-games the appearing players' values summed exactly to the team's
    # `/statistics` value in 97.7% (fouls), 98.0% (tackles), 97.9%
    # (interceptions) and 98.9% (offsides). So a missing key is taken as zero
    # only in a team-game where that sum closes (`team_sum`), and is a gap in
    # the 1-2% where it does not - the offsides note that stood here asked
    # for exactly this measurement.
    #
    # "Zawodnik - liczba fauli na zawodniku" (`wasFouled`) is NOT here: summed
    # against the opponent's fouls it closed in only 58.1% of team-games, so
    # there is no identity to prove its zeros. "... odbiorow na zawodniku"
    # has no Sofascore key that means it.
    "player_fouls_for": {
        "sofascore": "fouls",
        "zero_when_absent": True,
        "team_sum": "fouls",
    },
    "player_tackles_for": {
        "sofascore": "totalTackle",
        "zero_when_absent": True,
        "team_sum": "totalTackle",
    },
    "player_interceptions_for": {
        "sofascore": "interceptionWon",
        "zero_when_absent": True,
        "team_sum": "interceptionWon",
    },
    "player_offsides_for": {
        "sofascore": "totalOffside",
        "zero_when_absent": True,
        "team_sum": "offsides",
    },
}

# Written by `squad_statistics` into each appearing player's statistics: the
# Sofascore keys whose absence this team-game proves to be zero.
ZERO_PROVEN_KEY = "_zero_proven_by_team_sum"


def is_player_metric(metric: str) -> bool:
    return metric in PLAYER_METRICS


def _statistic(stats: dict[str, Any], key: str) -> float | None:
    value = stats.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def extract_player_metric(
    metric: str, stats: dict[str, Any] | None
) -> float | GapReason:
    """One player's value for one metric in one match.

    `stats` is the `statistics` object of one entry of a `/lineups` squad list.
    Returns a GapReason rather than a number whenever the payload does not
    settle the question, including the case where an absent key *might* be a
    zero but the identity that would prove it does not close.
    """
    config = PLAYER_METRICS.get(metric)
    if config is None:
        return GapReason.STAT_KEY_ABSENT
    if not stats:
        return GapReason.NO_STATISTICS

    # The appearance gate. A squad member who never came on has no
    # `minutesPlayed`, and Superbet voids his market rather than settling it.
    if _statistic(stats, "minutesPlayed") is None:
        return GapReason.EVENT_NOT_FINISHED

    key = str(config["sofascore"])
    value = _statistic(stats, key)
    if value is not None:
        return value

    if not config.get("zero_when_absent"):
        return GapReason.STAT_KEY_ABSENT

    if config.get("team_sum"):
        proven = stats.get(ZERO_PROVEN_KEY) or ()
        return 0.0 if key in proven else GapReason.STAT_KEY_ABSENT

    identity = config.get("identity")
    if not identity:
        return GapReason.STAT_KEY_ABSENT
    whole_key, part_keys = identity
    whole = _statistic(stats, str(whole_key))
    if whole is None:
        # Without the total there is nothing to check the zero against.
        return GapReason.STAT_KEY_ABSENT
    parts = 0.0
    for part_key in part_keys:
        if part_key == key:
            continue
        part = _statistic(stats, str(part_key))
        if part is not None:
            parts += part
    if abs(whole - parts) > 1e-9:
        # The absent key is not zero: the other components do not account for
        # the player's shots. Refuse rather than invent the remainder.
        return GapReason.INTERNAL_INCONSISTENT
    return 0.0


def team_totals(statistics: Any, *, is_home: bool) -> dict[str, float]:
    """One side's whole-match `/statistics` values, by Sofascore key."""
    out: dict[str, float] = {}
    if not isinstance(statistics, dict):
        return out
    for period in statistics.get("statistics") or []:
        if not isinstance(period, dict) or period.get("period") != "ALL":
            continue
        for group in period.get("groups") or []:
            for item in (group or {}).get("statisticsItems") or []:
                if not isinstance(item, dict):
                    continue
                key = item.get("key")
                value = item.get("homeValue" if is_home else "awayValue")
                if isinstance(key, str) and isinstance(value, int | float):
                    if not isinstance(value, bool):
                        out[key] = float(value)
    return out


def _zero_proven(
    squad: dict[str, dict[str, Any]], totals: dict[str, float]
) -> list[str]:
    """The team_sum metrics whose missing keys this team-game proves zero."""
    proven: list[str] = []
    appearing = [
        st for st in squad.values() if _statistic(st, "minutesPlayed") is not None
    ]
    for config in PLAYER_METRICS.values():
        team_key = config.get("team_sum")
        if not team_key or team_key not in totals or not appearing:
            continue
        key = str(config["sofascore"])
        summed = sum(_statistic(st, key) or 0.0 for st in appearing)
        if abs(summed - totals[team_key]) < 1e-9:
            proven.append(key)
    return proven


def squad_statistics(
    lineups: dict[str, Any] | None,
    *,
    is_home: bool,
    statistics: Any = None,
) -> dict[str, dict[str, Any]] | None:
    """`{normalised player name: statistics}` for one side of one match.

    None when the payload carries no squad for that side, which is a different
    fact from an empty squad and must not be read as "nobody played".

    `statistics` is the match's `/statistics` payload, when the caller holds
    it: it is what proves a team_sum metric's missing keys zero (each
    appearing player's statistics then carry ZERO_PROVEN_KEY). Without it a
    missing key of such a metric stays a gap.
    """
    if not lineups:
        return None
    side = lineups.get("home" if is_home else "away")
    if not isinstance(side, dict):
        return None
    players = side.get("players")
    if not isinstance(players, list):
        return None

    out: dict[str, dict[str, Any]] = {}
    homonyms: set[str] = set()
    for entry in players:
        if not isinstance(entry, dict):
            continue
        player = entry.get("player")
        if not isinstance(player, dict):
            continue
        name = player.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        stats = entry.get("statistics")
        key = normalize_name(name)
        if key in out:
            # Two squad members with one name (24 of 1,806 cached football
            # squad-sides, 2026-09-29: "ederson", "marcos paulo"): which one
            # Superbet means cannot be told, and the later one used to
            # overwrite the earlier. Neither is a candidate.
            homonyms.add(key)
        out[key] = dict(stats) if isinstance(stats, dict) else {}
    for key in homonyms:
        del out[key]
    if statistics is not None:
        proven = _zero_proven(out, team_totals(statistics, is_home=is_home))
        if proven:
            for st in out.values():
                if _statistic(st, "minutesPlayed") is not None:
                    st[ZERO_PROVEN_KEY] = proven
    return out


# How close a Superbet player name has to come to a Sofascore one.
#
# Higher than the team threshold of 70. A squad is a closed list of ~20 names
# competing for one match, and the failure mode is not "no match" but "the
# wrong team-mate" — two forwards from the same country share more of a name
# than two clubs do.
#
# Neither number is fitted, and both should be said plainly: 85 is chosen
# because a squad is a harder discrimination than a two-club board, and the
# margin of 5.0 is simply the one `run_settle._subject_is_home` already uses.
# That margin was set for a choice between TWO candidates; a squad offers
# twenty, so the maximum of the noise is larger and 5.0 is, if anything,
# generous. It is inherited rather than measured because there is no settled
# player row to measure it on yet — which is exactly what the first settled
# day of this family will provide.
PLAYER_MATCH_THRESHOLD = 85.0
PLAYER_MATCH_MARGIN = 5.0


def match_player(
    superbet_name: str, candidates: dict[str, dict[str, Any]]
) -> str | None:
    """Which squad member Superbet means, or None when it is not clear.

    Superbet writes "Tolo, Nouhou" and "Castan, Luciano"; Sofascore writes
    "Nouhou Tolo". `token_sort_ratio` bridges the inversion — it is the same
    scorer `determine_side` uses on club names — and the comma is dropped by
    the normaliser's non-ASCII pass, so no special case is needed for it.

    Returning None rather than the best guess is the point. A player market
    priced against a team-mate's sample is the F31 defect with a smaller
    subject, and nothing downstream could catch it on merit.
    """
    from rapidfuzz import fuzz

    target = normalize_name(superbet_name.replace(",", " "))
    if not target or not candidates:
        return None

    scored = sorted(
        ((fuzz.token_sort_ratio(target, name), name) for name in candidates),
        reverse=True,
    )
    best_score, best_name = scored[0]
    if best_score < PLAYER_MATCH_THRESHOLD:
        return None
    if len(scored) > 1 and best_score - scored[1][0] < PLAYER_MATCH_MARGIN:
        return None
    return best_name


def player_sample_key(market: str, subject: str) -> str:
    """How a player sample is keyed in `FixtureSamples.players`.

    Exactly the (market, subject) pair a rung carries, so nothing downstream
    has to re-run the name match SAMPLES already did — and so the sheet, the
    confidence view and any audit all look the sample up the same way.
    """
    return f"{market}|{subject}"


def player_observations(
    fixture_samples: dict[str, Any], market: str, subject: str
) -> list[Any]:
    """This player row's own observations out of a raw 03_samples.json entry.

    Takes the JSON dict rather than the model because that is what the
    artifact-reading stages hold. Returns [] when the player has no sample,
    which is the same answer the metrics axis gives for a missing metric.
    """
    entry = (fixture_samples.get("players") or {}).get(
        player_sample_key(market, subject)
    )
    if not isinstance(entry, dict):
        return []
    observations = entry.get("observations")
    return list(observations) if isinstance(observations, list) else []
