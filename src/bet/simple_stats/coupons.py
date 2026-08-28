"""Assemble one betting day's stats sheet into singles and Bet Builder slips.

This is the last computation in the chain, and it is code rather than an agent's
prose for the same reason ``wilson_lower_bound`` is: the numbers it produces are
thresholds a human bets money against. A threshold free-handed in a report
cannot be audited, reproduced, or caught when it slips by a decimal place.

What it does **not** do, and cannot be made to
----------------------------------------------
* **No combined price.** ``BetBuilderDraft.combined_price`` is typed ``None``,
  and nothing here computes one. Corners, cards, fouls and shots in one match
  are strongly positively correlated -- a foul-heavy match is a card-heavy
  match -- so the product of the legs understates the slip's real probability,
  in the direction that flatters the bet. Superbet's own price already accounts
  for the correlation; a number computed here would not, and would read as a
  second opinion confirming the first.
* **No stake.** Not a size, not a fraction of a bankroll, not a Kelly figure.
* **No EV.** EV needs a price, and the only real price is on the operator's own
  screen.

Every coupon is therefore *conditional*: "this lean is worth taking **if** the
screen shows at least X.XX". The operator supplies the price and the decision.

The one number that ranks everything
------------------------------------
``p_low`` -- the Wilson lower bound already on every row. Never ``hit_rate``:
4/4 is a hit rate of 1.00 and a ``p_low`` of 0.51, which is the whole point of
using it. Nothing in this module recomputes it; it is read from the artifact.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import Field

from bet.simple_stats.bet_builder_draft import (
    BetBuilderDraft,
    draft_legs,
    tier_for_row,
)
from bet.simple_stats.contracts import EventListV1, StatsSheetRow, StatsSheetV1
from bet.strict_model import StrictBaseModel

# Human-readable market labels. Sourced from the row's own ``market`` field
# rather than from STANDARD_MARKET_LINES, because that table is keyed by display
# name ("Corners Total") while a row carries the canonical name
# ("corners_total") -- and the mapping between them is not one-to-one for the
# per-team family.
MARKET_LABELS: dict[str, str] = {
    "corners_total": "rożne (mecz)",
    "cards_total": "kartki (mecz)",
    "fouls_total": "faule (mecz)",
    "shots_on_target_total": "strzały celne (mecz)",
    "shots_total": "strzały (mecz)",
    "corners_for": "rożne drużyny",
    "cards_for": "kartki drużyny",
    "fouls_for": "faule drużyny",
    "shots_on_target_for": "strzały celne drużyny",
    "shots_for": "strzały drużyny",
    "player_total_shots": "strzały zawodnika",
    "player_shots_on_target": "strzały celne zawodnika",
    "player_fouls": "faule zawodnika",
    "player_was_fouled": "faulowany",
    "player_cards": "kartka zawodnika",
    "total_games": "gemy (mecz)",
    "aces_total": "asy (mecz)",
    "total_sets": "sety",
    "double_faults_total": "podwójne błędy (mecz)",
    "breaks_total": "przełamania",
    "aces_for": "asy zawodnika",
    "double_faults_for": "podwójne błędy zawodnika",
    "games_won": "gemy zawodnika",
}

# A single must clear this before it is worth an operator's attention.
#
# 0.50 is not arbitrary and is not a probability threshold in disguise: below it
# the fair odds exceed 2.00, and once the tier margin is applied the required
# price passes what these markets realistically pay. A row at p_low 0.35 needs
# 3.14 on a corners line that is quoted near 2.30 -- reporting it as a "bet" is
# reporting something unplaceable.
MIN_SINGLE_P_LOW = 0.50

# Low-line UNDER props are trivially clearable and dominate a p_low sort:
# "player carded UNDER 0.5" at 10/10 lands near 0.72, above almost every corners
# row, because most players are not carded in most matches -- which is also
# exactly why that side is priced near 1.05 and is not a bet. They are not
# dropped (the read is real) but they never lead, and the file says why.
TRIVIAL_UNDER_MAX_LINE = 1.5


class CouponSingle(StrictBaseModel):
    """One standalone bet, with the price that would justify it."""

    rank: int
    event_id: str
    match: str
    competition: str
    kickoff: str
    sport: str
    market: str
    market_label: str
    line: float
    direction: str
    subject: str | None = None
    tier: str
    p_low: float
    hit_rate: float
    hits: int
    sample_size: int
    cross_provider_agreement: str
    fair_odds: float
    min_acceptable_odds: float
    market_verdict: str | None = None
    market_price: float | None = None
    market_bookmaker: str | None = None
    tipster: str | None = None
    caveats: list[str] = Field(default_factory=list)


class CouponSlip(StrictBaseModel):
    """One match's Bet Builder draft, with its match identity resolved."""

    rank: int
    event_id: str
    match: str
    competition: str
    kickoff: str
    draft: BetBuilderDraft
    # Slips are ranked by their weakest leg, not their average or their best.
    # A four-leg slip settles on every leg, so its evidence is the evidence of
    # the leg you are least sure about -- averaging would let three strong legs
    # carry a fourth nobody should be betting.
    weakest_leg_p_low: float


class CouponSet(StrictBaseModel):
    """COUPONS artifact for one betting day."""

    run_id: str = ""
    date: str = ""
    generated_at: str
    singles: list[CouponSingle] = Field(default_factory=list)
    slips: list[CouponSlip] = Field(default_factory=list)
    # Deliberately typed None, never a number. See the module docstring.
    combined_price: None = None
    rows_considered: int = 0
    events_considered: int = 0
    # The kickoff cutoff this set was built against, or None when the caller
    # asked for every fixture regardless of clock. Recorded so a file can still
    # be audited after the fact: "why is that match missing" has an answer here.
    not_before: str | None = None
    excluded: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def market_label(market: str) -> str:
    return MARKET_LABELS.get(market, market.replace("_", " "))


def _subject(row: StatsSheetRow) -> str | None:
    """Whose line this is: a player, a team, or nobody (a match total)."""
    if row.player_name:
        return row.player_name
    if row.team_name:
        return row.team_name
    return None


def _is_trivial_under(row: StatsSheetRow) -> bool:
    return row.direction == "UNDER" and row.line <= TRIVIAL_UNDER_MAX_LINE


def _caveats(row: StatsSheetRow) -> list[str]:
    notes: list[str] = []
    if row.cross_provider_agreement == "SINGLE_SOURCE":
        notes.append("jedno źródło — nic tego nie potwierdza")
    if row.cross_provider_agreement == "DISAGREE":
        notes.append("providerzy się nie zgadzają — wartości nieuśrednione")
    if row.player_id and (row.lineup_status or "") != "confirmed":
        notes.append(f"skład {row.lineup_status or 'nieznany'} — premisa to zgadywanka")
    if row.sample_size < 8:
        notes.append(f"mała próba (n={row.sample_size})")
    if _is_trivial_under(row):
        notes.append("niska linia UNDER — łatwa do trafienia i zwykle wyceniana ~1.05")
    return notes


def _kickoff_passed(kickoff: str, not_before: datetime | None) -> bool:
    """True when this fixture has already started and is no longer bettable.

    An unparseable or missing kickoff returns False. Not knowing when a match
    starts is not evidence that it started -- dropping it would silently hide a
    live fixture, which is the failure this check exists to prevent.
    """
    if not_before is None or not kickoff:
        return False
    try:
        start = datetime.fromisoformat(kickoff)
    except ValueError:
        return False
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return start <= not_before


def _tipster_summary(row: StatsSheetRow) -> str | None:
    if row.tipster is None or row.tipster.verdict == "NO_COVERAGE":
        return None
    return f"{row.tipster.agree}/{row.tipster.agree + row.tipster.oppose}"


def build_coupons(
    stats_sheet: StatsSheetV1,
    event_list: EventListV1 | None = None,
    *,
    max_singles: int = 15,
    max_slips: int = 8,
    max_legs: int = 4,
    min_p_low: float = MIN_SINGLE_P_LOW,
    not_before: datetime | None = None,
) -> CouponSet:
    """Turn a finished stats sheet into the day's singles and slips.

    Pure: no network, no DB, no clock. Given the same artifact *and the same*
    ``not_before`` it returns the same coupons, which is what makes a bad call
    reviewable after the fact -- the cutoff is an argument, never a call to
    ``now()`` inside, precisely so that property survives.

    ``not_before`` drops fixtures that have already kicked off. A coupon file
    is read hours after it is written, and a match in the past is not a bet at
    any price, however good its ``p_low`` looks. Pass ``None`` to keep the
    whole day, which is what a post-hoc review of yesterday wants.
    """
    events = {e.event_id: e for e in (event_list.events if event_list else [])}

    def identity(event_id: str) -> tuple[str, str, str]:
        event = events.get(event_id)
        if event is None:
            # The sheet alone cannot name a fixture; saying so beats printing a
            # hash at a human.
            return (f"[nieznany mecz {event_id[:12]}]", "", "")
        if event.sport == "tennis":
            match = f"{event.player_one or '?'} – {event.player_two or '?'}"
        else:
            match = f"{event.home_team or '?'} – {event.away_team or '?'}"
        return match, event.competition, event.start_time

    excluded: dict[str, int] = {}

    def exclude(reason: str) -> None:
        excluded[reason] = excluded.get(reason, 0) + 1

    # --- singles ----------------------------------------------------------
    candidates: list[tuple[StatsSheetRow, str]] = []
    for row in stats_sheet.rows:
        tier = tier_for_row(row)
        if tier in ("WEAK", "DROP"):
            exclude(f"tier_{tier.lower()}")
            continue
        if row.p_low < min_p_low:
            exclude("p_low_below_threshold")
            continue
        candidates.append((row, tier))

    # A fixture contributes at most one single per market family, so one match
    # with a strong corners read cannot occupy six rows of the file at four
    # different lines -- they are the same read, and only the best line of it is
    # a distinct bet.
    seen: set[tuple[str, str, str | None]] = set()
    singles: list[CouponSingle] = []
    for row, tier in sorted(
        candidates,
        key=lambda pair: (_is_trivial_under(pair[0]), -pair[0].p_low, pair[0].event_id),
    ):
        key = (row.event_id, row.market, _subject(row))
        if key in seen:
            exclude("duplicate_market_for_event")
            continue
        seen.add(key)
        match, competition, kickoff = identity(row.event_id)
        # Checked before the max_singles slot is spent: a started match must not
        # push a bettable one off the end of the list.
        if _kickoff_passed(kickoff, not_before):
            exclude("kickoff_passed")
            continue
        if len(singles) >= max_singles:
            exclude("over_max_singles")
            continue
        fair = 1.0 / row.p_low
        margin = {"CALL": 1.05, "LEAN": 1.10}[tier]
        singles.append(
            CouponSingle(
                rank=len(singles) + 1,
                event_id=row.event_id,
                match=match,
                competition=competition,
                kickoff=kickoff,
                sport=row.sport,
                market=row.market,
                market_label=market_label(row.market),
                line=row.line,
                direction=row.direction,
                subject=_subject(row),
                tier=tier,
                p_low=row.p_low,
                hit_rate=row.hit_rate,
                hits=row.hits,
                sample_size=row.sample_size,
                cross_provider_agreement=row.cross_provider_agreement,
                fair_odds=round(fair, 4),
                min_acceptable_odds=round(fair * margin, 4),
                market_verdict=row.market_signal.verdict if row.market_signal else None,
                market_price=row.market_signal.market_price if row.market_signal else None,
                market_bookmaker=(
                    row.market_signal.market_bookmaker if row.market_signal else None
                ),
                tipster=_tipster_summary(row),
                caveats=_caveats(row),
            )
        )

    # --- slips ------------------------------------------------------------
    slips: list[CouponSlip] = []
    for event_id in {row.event_id for row in stats_sheet.rows}:
        draft = draft_legs(stats_sheet, event_id, max_legs=max_legs)
        # A one-leg "slip" is a single wearing a different hat, and printing it
        # in both sections would double-count the same read.
        if len(draft.legs) < 2:
            continue
        match, competition, kickoff = identity(event_id)
        if _kickoff_passed(kickoff, not_before):
            exclude("kickoff_passed")
            continue
        slips.append(
            CouponSlip(
                rank=0,
                event_id=event_id,
                match=match,
                competition=competition,
                kickoff=kickoff,
                draft=draft,
                weakest_leg_p_low=min(leg.p_low for leg in draft.legs),
            )
        )

    slips.sort(key=lambda s: (-s.weakest_leg_p_low, s.event_id))
    slips = [s.model_copy(update={"rank": i + 1}) for i, s in enumerate(slips[:max_slips])]

    notes = [
        "Kurs łączny NIE jest liczony i nie może być — nogi w jednym meczu są "
        "skorelowane dodatnio, więc iloczyn zaniża prawdopodobieństwo kuponu. "
        "Kurs łączny odczytujesz z ekranu Superbetu.",
        "Pewność to dolna granica Wilsona 95% (p_low), nie surowy hit rate. "
        "sample_size łączy obie drużyny i h2h, więc obserwacje nie są niezależne "
        "— to optymistyczna podłoga, nie gwarancja.",
        "Brak stawek i brak EV — celowo. Typ poniżej minimalnego kursu nie jest typem.",
    ]
    if excluded.get("kickoff_passed"):
        notes.append(
            f"Odrzucono {excluded['kickoff_passed']} pozycji, których mecz już "
            f"się rozpoczął (odcięcie {not_before:%H:%M} UTC). Mecz w przeszłości "
            "nie jest typem, choćby jego p_low wyglądało najlepiej w pliku."
        )
    if any(_is_trivial_under(r) for r, _ in candidates):
        notes.append(
            "Niskie linie UNDER (≤1.5) zepchnięto na koniec listy singli: przy "
            "10/10 wychodzą wysoko w p_low, ale rynek wycenia je ~1.05."
        )

    return CouponSet(
        run_id=stats_sheet.run_id,
        date=stats_sheet.date,
        generated_at=_now_iso(),
        singles=singles,
        slips=slips,
        rows_considered=len(stats_sheet.rows),
        events_considered=len({row.event_id for row in stats_sheet.rows}),
        not_before=not_before.isoformat() if not_before else None,
        excluded=dict(sorted(excluded.items())),
        notes=notes,
    )
