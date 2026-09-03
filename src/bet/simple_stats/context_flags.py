"""Circumstances that may argue a stats-sheet row down -- never up, and never
into ``p_low``.

Faza 5b of docs/PLAN_BOGATE_STATYSTYKI.md. Referee discipline, injury counts,
a season xG gap, a derby, and wind speed used to live only in ``bet-analyst``'s
prose, re-derived by hand on every run and easy to forget on a busy slate. Every
input here already sits on the dossier a row is built from -- no new provider
call -- and the one-way rule is enforced by ``bet_builder_draft.tier_for_row``,
not by an agent remembering to apply it.
"""
from __future__ import annotations

import statistics
from collections.abc import Callable

from bet.simple_stats.contracts import ContextFlag, EventDossierV1, StatsSheetRow
from bet.simple_stats.providers import PRIMARY_PROVIDER_BY_SPORT

# Below this many matches a referee's or a season's average is a small sample
# wearing a confident-looking float -- state it plainly rather than acting on
# it. Mirrors RefereeProfile's own "read matches before believing any average"
# warning and TeamSeasonForm's "read xg_games before believing xgf/xga" one.
_MIN_REFEREE_MATCHES = 8
_MIN_XG_GAMES = 5
_MIN_UNAVAILABLE_FOR_FLAG = 4
_MAX_WIND_SPEED_BEFORE_FLAG = 25.0
# A season xG gap this wide (goals per game) is treated as the team over- or
# under-performing its underlying chances rather than as noise.
_MIN_XG_GAP_PER_GAME = 0.75

_CARD_MARKETS = frozenset(
    {"cards_points_total", "cards_points_for", "cards_total", "cards_for"}
)
_FOUL_MARKETS = frozenset({"fouls_total", "fouls_for"})
_SHOT_MARKETS = frozenset(
    {"shots_total", "shots_for", "shots_on_target_total", "shots_on_target_for"}
)
_CORNER_MARKETS = frozenset({"corners_total", "corners_for"})
_SQUAD_SENSITIVE_FOR_MARKETS = frozenset({"shots_for", "shots_on_target_for", "goals_for"})


def _side_for_team(dossier: EventDossierV1, team_name: str | None) -> str | None:
    """"home"/"away" for a per-team row's own team, or None for a match total.

    Football's team_a is always home and team_b always away
    (enrich._side_names), so this is a plain name match against the two names
    the dossier already carries -- no new lookup.
    """
    if team_name is None:
        return None
    if team_name == dossier.team_a_name:
        return "home"
    if team_name == dossier.team_b_name:
        return "away"
    return None


def referee_card_points_per_match(referee) -> float | None:
    """One official's average in the units "Liczba kartek" settles.

    ``None`` when the yellow average is missing -- a reds-only figure is not a
    card-points average. A missing *red* average is read as zero rather than as
    unknown, and that is the one place in the card work where a zero stands in
    for an absence: this is context that can only cap a tier, never a sample
    that prices a line, and a referee whose reds the provider does not publish
    still has a usable yellow rate.
    """
    yellows = getattr(referee, "avg_yellow_per_match", None)
    if yellows is None:
        return None
    reds = getattr(referee, "avg_red_per_match", None) or 0.0
    return yellows + 2.0 * reds


def _referee_flag(row: StatsSheetRow, dossier: EventDossierV1) -> ContextFlag | None:
    """A referee's own season average sitting on the other side of the line.

    Scoped to match-total rows only (``cards_points_total``/``fouls_total``):
    the average describes the whole match, and halving it to compare against a
    per-team line would invent a number the provider never gave.

    On a card-points row the referee's average is converted into the same
    units the line is in -- yellows plus twice the reds. The provider gives no
    type split for an official's reds (``/referees/{id}/`` publishes
    ``avg_red_per_match`` and nothing finer), so each is charged as straight,
    which is the same ``RED_TYPE_UNKNOWN`` convention the observations use.
    Comparing a yellow-only average against a booking-points line was the
    quieter half of the 2026-09-03 card defect: it put the referee on the
    UNDER side of a line he was in fact above.
    """
    referee = dossier.referee
    if referee is None or (referee.matches or 0) < _MIN_REFEREE_MATCHES:
        return None
    if row.team_name is not None:
        return None
    if row.market == "cards_points_total":
        average = referee_card_points_per_match(referee)
    elif row.market == "cards_total":
        average = referee.avg_yellow_per_match
    elif row.market == "fouls_total":
        average = referee.avg_fouls_per_match
    else:
        return None
    if average is None:
        return None
    if row.direction == "OVER" and average < row.line:
        gap = row.line - average
    elif row.direction == "UNDER" and average > row.line:
        gap = average - row.line
    else:
        return None
    return ContextFlag(
        source="referee",
        direction="ARGUES_AGAINST",
        magnitude=round(gap, 2),
        note=(
            f"referee averages {average:.2f}/match over {referee.matches} "
            f"matches, on the other side of this {row.line} line"
        ),
    )


def _squad_flag(row: StatsSheetRow, dossier: EventDossierV1) -> ContextFlag | None:
    """Four or more unavailable players argues against that side's own
    shots/shots-on-target/goals continuing at its established rate."""
    if row.direction != "OVER" or row.market not in _SQUAD_SENSITIVE_FOR_MARKETS:
        return None
    side = _side_for_team(dossier, row.team_name)
    if side is None:
        return None
    block = next((s for s in dossier.squad_availability if s.side == side), None)
    if block is None or block.unavailable_count < _MIN_UNAVAILABLE_FOR_FLAG:
        return None
    return ContextFlag(
        source="squad_availability",
        direction="ARGUES_AGAINST",
        magnitude=float(block.unavailable_count),
        note=f"{row.team_name} has {block.unavailable_count} players unavailable",
    )


# Two clubs this close together are in the same city whatever the provider's
# own flag says. 25 km is chosen to be safely inside "same conurbation" and
# safely outside a regional rivalry: the Grenal is 11 km, the two Manchester
# grounds are 6, Milan share a stadium at 0, and Roma-Lazio share one too --
# while Liverpool-Manchester United, which nobody would price as a derby on
# travel alone, is 55.
_DERBY_MAX_TRAVEL_KM = 25.0

# Pairs of bzzoiro team ids that are a derby whatever the provider says, by
# ``frozenset`` so the order of the fixture does not matter.
#
# One entry, and it is here because the provider is *wrong* rather than silent:
# ``/events/587790/`` answers ``"is_local_derby": false`` for
# Grêmio-Internacional with ``"travel_distance_km": 11`` on the same row. The
# distance rule above already catches it; the pin is belt and braces on the
# biggest derby the 2026-09-03 slate had, and the place to add any other case
# where the flag is known to lie.
_PINNED_DERBIES: frozenset[frozenset[str]] = frozenset({frozenset({"154", "161"})})


def is_derby(dossier: EventDossierV1) -> bool:
    """Whether this fixture is a derby, by the provider's flag *or* by distance.

    ``is_local_derby`` alone was the rule until 2026-09-03 and it is not
    reliable: bzzoiro answered false for Grêmio-Internacional, 11 km apart, on
    the same payload that reported the 11 km. No code path had ever degraded
    the biggest derby of that day.
    """
    context = dossier.fixture_context
    if context is None:
        return False
    if context.is_local_derby:
        return True
    pair = frozenset(
        side for side in (context.home_team_id, context.away_team_id) if side
    )
    if len(pair) == 2 and pair in _PINNED_DERBIES:
        return True
    distance = context.travel_distance_km
    return distance is not None and distance < _DERBY_MAX_TRAVEL_KM


def knockout_second_leg_is_live(dossier: EventDossierV1) -> bool:
    """A second leg with the tie still level or within one goal.

    Not every second leg: a tie decided 4-0 in the first leg produces a
    friendly, and its cards behave like a friendly's. What changes a match is
    a tie somebody still has to win, and that is what the aggregate says.

    Both legs' scores are needed, and only the first leg's are available before
    kick-off, so "within one goal" is read off the first leg alone. The score
    is already mapped onto tonight's sides at discovery.
    """
    context = dossier.fixture_context
    if context is None or not context.previous_leg_event_id:
        return False
    home = context.previous_leg_goals_home
    away = context.previous_leg_goals_away
    if home is None or away is None:
        # The pointer exists and the score could not be read. A two-legged tie
        # of unknown aggregate is still a two-legged tie, and the cautious
        # reading of an unknown is the one that keeps the ceiling on.
        return True
    return abs(home - away) <= 1


def _derby_flag(row: StatsSheetRow, dossier: EventDossierV1) -> ContextFlag | None:
    """A local derby supports OVER on cards/fouls: more needle, more cards."""
    if row.direction != "OVER" or row.market not in (_CARD_MARKETS | _FOUL_MARKETS):
        return None
    if not is_derby(dossier):
        return None
    context = dossier.fixture_context
    distance = context.travel_distance_km if context else None
    note = "local derby"
    if context is not None and not context.is_local_derby and distance is not None:
        note = f"derby by distance ({distance:.0f} km apart)"
    return ContextFlag(source="fixture_context", direction="SUPPORTS", magnitude=1.0, note=note)


def _weather_flag(row: StatsSheetRow, dossier: EventDossierV1) -> ContextFlag | None:
    """Strong wind argues against OVER on corners/shots: it suppresses the
    open play that produces both."""
    if row.direction != "OVER" or row.market not in (_CORNER_MARKETS | _SHOT_MARKETS):
        return None
    context = dossier.fixture_context
    weather = context.weather if context is not None else None
    if not isinstance(weather, dict):
        return None
    wind = weather.get("wind_speed")
    if not isinstance(wind, (int, float)) or wind <= _MAX_WIND_SPEED_BEFORE_FLAG:
        return None
    return ContextFlag(
        source="weather", direction="ARGUES_AGAINST", magnitude=float(wind),
        note=f"wind speed {wind}",
    )


def _season_form_flag(row: StatsSheetRow, dossier: EventDossierV1) -> ContextFlag | None:
    """A team scoring well above its own season xG argues against its OVER
    goals continuing at that rate -- regression to underlying chances, measured
    rather than eyeballed.

    ``TeamSeasonForm.xgf`` is the provider's season *total* over ``xg_games``
    matches (the same table row carries ``played``/``points`` as totals too),
    so it is divided here to get a per-game figure comparable to the row's own
    per-match observations.
    """
    if row.direction != "OVER" or row.market != "goals_for":
        return None
    side = _side_for_team(dossier, row.team_name)
    if side is None:
        return None
    form = next((f for f in dossier.season_form if f.side == side), None)
    if form is None or form.xgf is None or (form.xg_games or 0) < _MIN_XG_GAMES:
        return None
    observation = dossier.metrics.get("goals_for")
    if observation is None:
        return None
    bucket = observation.team_a_l10 if side == "home" else observation.team_b_l10
    if not bucket:
        return None
    # Scoped and collapsed exactly as the row's own statistics are, and for the
    # same reasons -- this used to read the raw dossier bucket, which is neither.
    #
    # Two faults, measured over the 2026-09-01 dossier: 78 of the team-side
    # buckets gave a different mean once scoped, by a median of 0.30 goals a
    # game and up to 1.70. One read 2.40/game raw against 1.00 scoped, off ten
    # pre-season friendlies and four previous-season matches. And a match three
    # providers report counted three times, because ``_one_per_day`` had not
    # run.
    #
    # It is wrong in both directions, so "conservative" is not a defence: 39 of
    # the 78 came out too high, which fires ARGUES_AGAINST on a team that is not
    # overperforming and steps a good row's tier down, and 39 came out too low,
    # which is a real regression warning this flag exists to raise and did not.
    #
    # Imported inside the function because ``analyze`` imports this module at
    # module scope; a top-level import back would be a cycle.
    from bet.simple_stats.analyze import _one_per_day, scope_values

    scoped, _ = scope_values(list(bucket))
    if not scoped:
        return None
    independent = _one_per_day(scoped, dossier.sport)
    if not independent:
        return None
    actual_per_game = statistics.fmean(pv.value for pv in independent)
    xgf_per_game = form.xgf / form.xg_games
    gap = actual_per_game - xgf_per_game
    if gap < _MIN_XG_GAP_PER_GAME:
        return None
    return ContextFlag(
        source="season_form",
        direction="ARGUES_AGAINST",
        magnitude=round(gap, 2),
        note=(
            f"{row.team_name} scores {actual_per_game:.2f}/game vs a season xGF "
            f"of {xgf_per_game:.2f}/game over {form.xg_games} games"
        ),
    )


_FLAG_RULES: tuple[Callable[[StatsSheetRow, EventDossierV1], ContextFlag | None], ...] = (
    _referee_flag,
    _squad_flag,
    _derby_flag,
    _weather_flag,
    _season_form_flag,
)

# Deliberately NOT a rule here, and this one was written, measured and then
# deleted rather than never tried: a team's own home/away split.
#
# ``ProviderValue.venue`` exists as of 2026-09-02 and every football provider
# fills it, so the rule was easy to write -- fire ARGUES_AGAINST when the
# team's record at *this* venue argues the row down. Two shapes were measured
# against the 2026-09-01 slate before either shipped, and both failed:
#
# 1. "the venue-matched mean sits on the other side of the line", the shape
#    ``_referee_flag`` uses. Venue assigned by coin flip so that any firing is
#    subsample noise by construction: it fired on 49% of the per-team rows that
#    reached its minimum sample size, across five independent shuffles. A sheet
#    row's line is chosen near its own sample's median
#    (``offered_lines.select_lines``), so which side a random half-sample lands
#    on is close to a toss-up. On the rows that can actually become bets
#    (``p_low >= 0.50``, tier CALL or LEAN, offered by Superbet) it fired on 0
#    of 20, because those have their line far from the centre by construction.
#    A coin flip where it did not matter and inert where it did.
#
# 2. "relocate the centre to the venue subsample and see whether the row still
#    clears the singles floor". Sharper -- 0.7% null firing against 1.1% on
#    real venue data -- but the real fires turned out to be an artifact of
#    *shrinkage strength*, not of venue: a 4-observation venue subsample is
#    shrunk 71% toward the market prior against the pooled sample's 44%, so the
#    relocated centre sits nearer the prior whichever way the venue record
#    points. Nine of the thirteen real fires were rows whose venue mean was on
#    the *helpful* side.
#
# What settled it. Real home/away was resolved for 191 teams over both slates
# (1,852 match-venue pairs from bzzoiro's own fixture listings) and joined back
# onto the frozen dossiers. Over 358 per-team samples with at least three
# matches at each venue, the gap between a team's home mean and its away mean
# was a median of 0.52 of the sample's own standard deviation, above one sigma
# on 20.9%; the coin-flip null over the same samples gave 0.40-0.53 and
# 10.6-18.9%. **A single team's home/away split is indistinguishable from
# noise at these depths** -- 3 to 5 matches a venue cannot measure an effect of
# a third of a goal.
#
# Home advantage is emphatically real; it is only measurable pooled across
# teams, where it is worth +2.59 shots and -0.52 cards a game at z of 8 and -7.
# So it lives in ``config/market_priors.json`` as a per-venue shrinkage target
# read by ``analyze.shrunk_centre``, which is a change to the price and not a
# tier lever -- and there is nothing left here for a flag to add. See
# tests/simple_stats/test_venue_split.py for the whole measurement.
#
# Also deliberately not a rule: fixture_context.round_name and
# .group_name (bzzoiro's own free-text labels for cup rounds/group stages)
# are plumbed all the way to the dossier, but every fixture checked live on
# 2026-08-31 -- including league fixtures across ten competitions -- came
# back with round_name="" and group_name=None. There is no cup/knockout
# fixture on record yet to prove what a real "Final"/"Semi-final" string
# looks like from this provider, and this file's whole discipline (see the
# derby/weather rules above, and docs/PLAN_BOGATE_STATYSTYKI.md Faza 5b's own
# "seen on a real slate, not guessed" rule) is that a pattern gets encoded
# from provider data, never from what a string "probably" says. Add the rule
# once a real knockout fixture's round_name has been observed and quoted here.
#
# previous_leg_event_id (the first leg of a two-legged tie) is not a rule
# either, for a different reason: which side needs to attack depends on the
# aggregate scoreline, which is not on this fixture's own row -- resolving it
# needs a follow-up call to the other event. That is exactly the kind of
# judgment call bet-analyst already makes live over MCP for referee/injury
# context, so this pipeline only carries the pointer
# (fixture_context.previous_leg_event_id); the analyst is instructed to
# resolve it (.claude/agents/bet-analyst.md).


# --- structural ceilings ---------------------------------------------------
#
# A ``ContextFlag`` steps a tier down once and can take a LEAN to WEAK. These
# say something narrower and stronger: "this row is at best a lean", however
# large its sample and however many of them fire. See
# ``StatsSheetRow.lean_ceiling_reasons`` for why a cap rather than a step --
# the Grenal collects three of these at once and is not three tiers worse than
# a fixture that collects one.
#
# All three are scoped to the *UNDER* side of the two markets a rough match
# moves, except the referee one, which is about a missing input rather than
# about the match being rough and therefore applies to both directions.
CEILING_KNOCKOUT_SECOND_LEG = "KNOCKOUT_SECOND_LEG"
CEILING_DERBY = "DERBY"
CEILING_MISSING_REFEREE = "MISSING_REFEREE"
CEILING_NO_REFERENCE_SOURCE = "NO_REFERENCE_SOURCE"

_ROUGH_MATCH_MARKETS = _CARD_MARKETS | _FOUL_MARKETS


def lean_ceilings_for_row(row: StatsSheetRow, dossier: EventDossierV1) -> list[str]:
    """Structural reasons this row may not be a CALL.

    Deliberately parallel to ``context_flags_for_row`` and deliberately not
    merged into it: a flag is a *reading* of a circumstance with a magnitude
    and a note for a human, and these are a ceiling with neither.
    """
    reasons: list[str] = []
    context = dossier.fixture_context

    if row.market in _ROUGH_MATCH_MARKETS and row.direction == "UNDER":
        # A derby and a live second leg both make a match rougher than either
        # side's last ten, so the UNDER is the side the sample flatters. The
        # OVER is left alone: ``_derby_flag`` already SUPPORTS it, and nothing
        # in this pipeline promotes a row on context.
        if is_derby(dossier):
            reasons.append(CEILING_DERBY)
        if knockout_second_leg_is_live(dossier):
            reasons.append(CEILING_KNOCKOUT_SECOND_LEG)

    if dossier.sport not in PRIMARY_PROVIDER_BY_SPORT:
        # No provider of record for the sport, so no row in it is a CALL.
        #
        # For football, ``data_quality == "READY"`` means bzzoiro served a
        # complete sample and that is what buys the top tier
        # (``tier_for_row``). Tennis has no such provider: bzzoiro-tennis
        # answers HTTP 402 (a paid addon) and was withdrawn on 2026-09-02, so
        # the sport's samples come from tennis-abstract and espn-tennis with
        # nothing standing behind either -- and "READY" there means only that
        # those two agreed, which is corroboration and not a reference.
        #
        # Keyed on the roster rather than on the string "tennis", so the day a
        # tennis primary is entitled this lifts by itself.
        reasons.append(CEILING_NO_REFERENCE_SOURCE)

    if row.market in _CARD_MARKETS and (context is None or not context.referee_id):
        # Cards are the one market whose largest single input is a person
        # neither club's history says anything about. Measured live 2026-08-30
        # in one league: Peter Bankes averages 4.15 yellows a match against
        # Michael Oliver's 3.10, a third of the spread in a cards line. On
        # 2026-09-03 the referee was null on 8 of 22 football fixtures and
        # their card rows shipped as CALL.
        reasons.append(CEILING_MISSING_REFEREE)

    return reasons


def context_flags_for_row(row: StatsSheetRow, dossier: EventDossierV1) -> list[ContextFlag]:
    """Every context flag this row's circumstances earn.

    Order carries no meaning: ``tier_for_row`` only checks for *any*
    ``ARGUES_AGAINST`` flag and steps the tier down once regardless of count.
    """
    return [flag for flag in (rule(row, dossier) for rule in _FLAG_RULES) if flag is not None]
