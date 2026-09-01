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

_CARD_MARKETS = frozenset({"cards_total", "cards_for"})
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


def _referee_flag(row: StatsSheetRow, dossier: EventDossierV1) -> ContextFlag | None:
    """A referee's own season average sitting on the other side of the line.

    Scoped to match-total rows only (``cards_total``/``fouls_total``): the
    average describes the whole match, and halving it to compare against a
    per-team line would invent a number the provider never gave.
    """
    referee = dossier.referee
    if referee is None or (referee.matches or 0) < _MIN_REFEREE_MATCHES:
        return None
    if row.team_name is not None:
        return None
    if row.market == "cards_total":
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


def _derby_flag(row: StatsSheetRow, dossier: EventDossierV1) -> ContextFlag | None:
    """A local derby supports OVER on cards/fouls: more needle, more cards."""
    if row.direction != "OVER" or row.market not in (_CARD_MARKETS | _FOUL_MARKETS):
        return None
    context = dossier.fixture_context
    if context is None or not context.is_local_derby:
        return None
    return ContextFlag(source="fixture_context", direction="SUPPORTS", magnitude=1.0, note="local derby")


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
    actual_per_game = statistics.fmean(pv.value for pv in bucket)
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

# Deliberately NOT a sixth rule here yet: fixture_context.round_name and
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


def context_flags_for_row(row: StatsSheetRow, dossier: EventDossierV1) -> list[ContextFlag]:
    """Every context flag this row's circumstances earn.

    Order carries no meaning: ``tier_for_row`` only checks for *any*
    ``ARGUES_AGAINST`` flag and steps the tier down once regardless of count.
    """
    return [flag for flag in (rule(row, dossier) for rule in _FLAG_RULES) if flag is not None]
