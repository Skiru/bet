"""SHEET's football centre terms after `run_sheet.sample_centre`.

A marginal row's centre is the sample centre (prior, K_CENTRE shrink, the
rating blend) carried through, in this order: the league venue prior
(epochs.FOOTBALL_VENUE_PRIOR), GAME_STATE, the count stretch, the referee
term, the closeness stretch, the goals stretch, then - after a footballer's
share / stretch, which stay in run_sheet.process_fixture - the season phase.

One implementation for `run_sheet.process_fixture` (the marginal row) and,
under epochs.JOINT_FILLED_SIDE_CHAIN (review 2026-10-27 R1), for
`run_sheet.sheet_derived_margins` (a joint's side Superbet quoted no ladder
for), so the filled side carries exactly the centre its marginal row would.
Every table None (its switch off) leaves the centre unchanged, byte for byte.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from bet.sofa import referees as referee_terms
from bet.sofa.closeness_stretch import CLOSENESS_UNFITTED, ClosenessStretchTable
from bet.sofa.closeness_stretch import supremacy as closeness_supremacy
from bet.sofa.count_stretch import COUNT_STRETCH_UNFITTED, CountStretchTable
from bet.sofa.count_stretch import is_total as count_stretch_is_total
from bet.sofa.football_rating import VENUE_PRIOR_MARKETS, FootballForecast
from bet.sofa.game_state import GAME_STATE_UNFITTED, GameStateTable
from bet.sofa.goals_stretch import (
    GOALS_STRETCH_UNFITTED,
    GoalsStretchTable,
    stretch_supremacy,
)
from bet.sofa.referees import REFEREE_UNFITTED, RefereeEffectTable, RefereeRead
from bet.sofa.season_phase import SEASON_PHASE_UNFITTED, SeasonPhaseTable
from bet.sofa.season_phase import apply as apply_season_phase
from bet.sofa.supremacy_stretch import stretch_supremacy as side_or_home_supremacy

# the note every derived row whose filled side went through the chain carries
JOINT_SIDE_CHAIN_NOTE = "JOINT_SIDE_CHAIN"


@dataclass(frozen=True)
class CentreTerms:
    """The day's centre tables (None = that switch off) and the fixture's
    football forecast / referee reads - what process_fixture is handed."""

    football: FootballForecast | None
    venue_prior_on: bool = False
    game_state: GameStateTable | None = None
    count_stretch: CountStretchTable | None = None
    referee_effect: RefereeEffectTable | None = None
    referee_reads: Mapping[str, RefereeRead] | None = None
    closeness_stretch: ClosenessStretchTable | None = None
    goals_stretch: GoalsStretchTable | None = None
    season_phase: SeasonPhaseTable | None = None
    season_phase_label: str | None = None


@dataclass
class ChainResult:
    centre: float
    notes: list[str] = field(default_factory=list)
    unfitted: list[str] = field(default_factory=list)
    # the row's referee_read (set whenever the referee table holds the market)
    referee_info: dict[str, Any] | None = None


def apply_team_terms(
    centre: float,
    *,
    market: str,
    side_key: str | None,
    venues: Iterable[str | None],
    rated: tuple[float, str] | None,
    sport: str,
    terms: CentreTerms,
) -> ChainResult:
    """Venue prior .. goals stretch on `centre` (the sample centre). `side_key`
    "side_a" / "side_b" / None (a total); `venues` the priced sample's;
    `rated` sample_centre's rating (a rated centre takes no venue prior)."""
    out = ChainResult(centre)
    football = terms.football
    # epochs.FOOTBALL_VENUE_PRIOR (audit 2026-10-13 B2): a sample-only
    # side centre reads the league's home / away rate as a multiplier
    # - the sample is never split by venue.
    if (terms.venue_prior_on and football is not None and rated is None
            and side_key is not None
            and market in VENUE_PRIOR_MARKETS):
        v_mult = football.venue_multiplier(market, side_key, venues)
        if v_mult is not None:
            v_before = out.centre
            out.centre *= v_mult
            out.notes.append(
                f"VENUE_PRIOR: centre {out.centre:.2f} = {v_before:.2f} x "
                f"{v_mult:.3f} (league rate at today's venue over the "
                "sample's venues; epochs.FOOTBALL_VENUE_PRIOR)")
    # epochs.GAME_STATE (audit 2026-10-13 B1): the favourite /
    # outsider term, exp(beta x the side's expected goal difference).
    game_state = terms.game_state
    if game_state is not None and football is not None and side_key:
        g_sup = football.supremacy(side_key)
        g_mult = game_state.multiplier(market, g_sup)
        if g_mult is not None and g_sup is not None:
            g_before = out.centre
            out.centre *= g_mult
            out.unfitted.extend(GAME_STATE_UNFITTED)
            out.notes.append(
                f"GAME_STATE: centre {out.centre:.2f} = {g_before:.2f} x "
                f"{g_mult:.3f} (expected goal difference {g_sup:+.2f}, "
                f"beta {game_state.betas[market]:+.4f}; "
                "epochs.GAME_STATE)")
    # epochs.FOOTBALL_COUNT_STRETCH: a count centre outside
    # GAME_STATE x the supremacy stretch (side: exp(beta x s [+ beta2
    # x s^2]); total: exp(g1 |s| + g2 s^2), s the home side's), after
    # GAME_STATE and the venue prior, blended or sample-only.
    count_stretch = terms.count_stretch
    if count_stretch is not None and football is not None:
        cs_total = count_stretch_is_total(market)
        cs_sup = side_or_home_supremacy(football, side_key, cs_total)
        cs_mult = count_stretch.multiplier(market, cs_sup)
        if cs_mult is not None and cs_sup is not None:
            cs_before = out.centre
            out.centre *= cs_mult
            out.unfitted.extend(COUNT_STRETCH_UNFITTED)
            out.notes.append(
                f"COUNT_STRETCH: centre {out.centre:.2f} = {cs_before:.2f} x "
                f"{cs_mult:.3f} (expected goal difference {cs_sup:+.2f}"
                f"{' (home)' if cs_total else ''}, "
                f"{count_stretch.describe(market)}; "
                "epochs.FOOTBALL_COUNT_STRETCH)")
    # epochs.FOOTBALL_REFEREE: a cards / fouls centre x the fixture
    # referee's as-of shrunk ratio ** beta (bet.sofa.referees), after
    # GAME_STATE and the count stretch; no referee named (or none
    # with a record in the history) leaves the centre as it is and
    # says so on the row (referee_read.status).
    if (terms.referee_effect is not None and football is not None
            and sport == "football"):
        fam = referee_terms.family_of(market)
        applied = terms.referee_effect.apply(
            market,
            (terms.referee_reads or {}).get(fam) if fam is not None else None)
        if applied is not None:
            r_mult, referee_info = applied
            out.referee_info = referee_info
            if referee_info["status"] == "APPLIED":
                r_before = out.centre
                out.centre *= r_mult
                out.unfitted.extend(REFEREE_UNFITTED)
                out.notes.append(
                    f"REFEREE: centre {out.centre:.2f} = {r_before:.2f} x "
                    f"{r_mult:.3f} (referee {referee_info['referee_id']}, "
                    f"{referee_info['n']} matches, ratio "
                    f"{referee_info['ratio']:.3f}; epochs.FOOTBALL_REFEREE)")
    # epochs.FOOTBALL_CLOSENESS_STRETCH: a count centre x exp(g1 |s|
    # + g2 s^2), s the home side's (|s|, s^2 even), after GAME_STATE
    # and the count stretch, blended or sample-only.
    closeness = terms.closeness_stretch
    if closeness is not None and football is not None:
        cl_sup = closeness_supremacy(football)
        cl_mult = closeness.multiplier(market, cl_sup)
        if cl_mult is not None and cl_sup is not None:
            cl_before = out.centre
            out.centre *= cl_mult
            out.unfitted.extend(CLOSENESS_UNFITTED)
            out.notes.append(
                f"CLOSENESS_STRETCH: centre {out.centre:.2f} = "
                f"{cl_before:.2f} x {cl_mult:.3f} (expected goal "
                f"difference {cl_sup:+.2f} (home), "
                f"{closeness.describe(market)}; "
                "epochs.FOOTBALL_CLOSENESS_STRETCH)")
    # epochs.FOOTBALL_GOALS_STRETCH: a goals centre x the supremacy
    # stretch (side: exp(beta x s); total: exp(g1 |s| + g2 s^2), s
    # the home side's), on the same blended centre; a market with
    # per-phase coefficients reads the fixture's season phase.
    goals_stretch = terms.goals_stretch
    if goals_stretch is not None and football is not None:
        st_sup = stretch_supremacy(football, market, side_key)
        st_mult = goals_stretch.multiplier(
            market, st_sup, terms.season_phase_label)
        if st_mult is not None and st_sup is not None:
            st_before = out.centre
            out.centre *= st_mult
            out.unfitted.extend(GOALS_STRETCH_UNFITTED)
            out.notes.append(
                f"GOALS_STRETCH: centre {out.centre:.2f} = {st_before:.2f} x "
                f"{st_mult:.3f} (expected goal difference {st_sup:+.2f}"
                f"{' (home)' if side_key is None else ''}, "
                f"{goals_stretch.describe(market, terms.season_phase_label)}; "
                "epochs.FOOTBALL_GOALS_STRETCH)")
    return out


def apply_season_phase_term(
    centre: float, *, market: str, terms: CentreTerms,
) -> ChainResult:
    """epochs.SEASON_PHASE (audit 2026-10-13 C1): the goals centre x
    exp(c[market][phase]), the phase as of the day's cut."""
    out = ChainResult(centre)
    if terms.season_phase is not None and terms.football is not None:
        p_before = centre
        out.centre, p_mult = apply_season_phase(
            centre, market, terms.season_phase_label, terms.season_phase)
        if p_mult is not None:
            out.unfitted.extend(SEASON_PHASE_UNFITTED)
            out.notes.append(
                f"SEASON_PHASE: centre {out.centre:.2f} = {p_before:.2f} x "
                f"{p_mult:.3f} (phase {terms.season_phase_label}; "
                "epochs.SEASON_PHASE)")
    return out


def apply_centre_chain(
    centre: float,
    *,
    market: str,
    side_key: str | None,
    venues: Iterable[str | None],
    rated: tuple[float, str] | None,
    sport: str,
    terms: CentreTerms,
) -> ChainResult:
    """The whole chain for a team row (no footballer's share / stretch between
    the goals stretch and the season phase)."""
    out = apply_team_terms(centre, market=market, side_key=side_key,
                           venues=venues, rated=rated, sport=sport, terms=terms)
    phase = apply_season_phase_term(out.centre, market=market, terms=terms)
    out.centre = phase.centre
    out.notes.extend(phase.notes)
    out.unfitted.extend(phase.unfitted)
    return out
