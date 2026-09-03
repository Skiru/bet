"""The gate between `tipster-reader`'s prose and the coupon file.

The agent reads free-form betting shorthand and says what it means. That is a
capability nothing else here has -- and it is also the only place in this
pipeline where a language model's output could reach an operator-facing file.
So it does not reach one directly. It passes through this module first, which
accepts nothing it cannot check against the artifact the agent was reading.

Four checks, and each one exists because of a specific way an agent output
could be wrong rather than merely unhelpful:

1. **The pick must exist.** `(event_id, tipster_name, claim)` has to match a
   pick that TIPSTERS actually collected, with `claim` equal **byte for byte**.
   An agent that paraphrases a claim, or invents a tipster, or attaches a
   reading to the wrong fixture, is rejected rather than believed. This is the
   check that makes the rest safe: every reading is anchored to a real string a
   human can go and read.
2. **The vocabulary is closed.** `market` must be a canonical market this repo
   prices, `direction` one of ten values, `kind` one of three. A hallucinated
   market name cannot enter, because there is nowhere for it to go.
3. **`subject` must be one of the two participants.** A `*_for` claim is about
   one named side; if the name is not that fixture's `home_team` or
   `away_team`, the leg is dropped. `Tabilo` resolving to `Alejandro Tabilo` is
   fine because that string is in front of the agent; a third party is not.
4. **A total needs a line, an outcome must not have one.** `over` without a
   number is not a claim, and the existing rules path already refuses it; the
   agent gets no licence the rules do not have.

**What this module deliberately does not do:** it does not count, rank, weight
or score anything, and it produces no probability. Its output is a description
of opinions, keyed to the raw text, and `tipster_consensus` does the arithmetic
over it in ordinary deterministic code. Nothing here is read by `coupons.py`,
`analyze.py` or anything on the `p_low` path.

A rejected reading is reported, never silently dropped: `rejected_by_reason`
goes into the artifact and the step's summary, because a systematic rejection
is how you find out the agent has drifted or the prompt needs work.
"""
from __future__ import annotations

from pydantic import Field

from bet.simple_stats.contracts import TipsterSignalV1
from bet.strict_model import StrictBaseModel

# Markets this repo actually prices. A reading naming anything else has nowhere
# to land, so it is refused rather than stored for later.
CANONICAL_MARKETS = frozenset(
    {
        "goals_total", "goals_1h_total", "goals_2h_total", "goals_for",
        "corners_total", "corners_for",
        "cards_points_total", "cards_points_for",
        "cards_total", "cards_for", "red_cards_total",
        "fouls_total", "fouls_for",
        "shots_total", "shots_for",
        "shots_on_target_total", "shots_on_target_for",
        "offsides_total", "offsides_for",
        "total_games", "total_sets", "games_won",
        "aces_total", "aces_for", "double_faults_total", "double_faults_for",
        "player_total_shots", "player_shots_on_target", "player_fouls",
        "player_was_fouled", "player_cards", "player_tackles",
        "player_assists", "player_offsides",
    }
)

# Markets that are about one named subject rather than the match, so a reading
# without one cannot be resolved. Derived rather than listed so that adding a
# market above cannot forget it: `*_for` is one side's count, `player_*` is one
# person's, and `games_won` is one player's games in a tennis match.
_SUBJECT_REQUIRED = frozenset(
    m
    for m in CANONICAL_MARKETS
    if m.endswith("_for") or m.startswith("player_") or m == "games_won"
)

_DIRECTIONS = frozenset(
    {
        "HOME", "AWAY", "DRAW",
        "HOME_OR_DRAW", "AWAY_OR_DRAW", "HOME_OR_AWAY",
        "BTTS_YES", "BTTS_NO",
        "OVER", "UNDER",
    }
)
_TOTAL_DIRECTIONS = frozenset({"OVER", "UNDER"})
_KINDS = frozenset({"OUTCOME", "TOTAL", "UNREADABLE"})
_READ_CONFIDENCE = frozenset({"CLEAR", "PROBABLE", "GUESS"})


class ClaimLeg(StrictBaseModel):
    """One commitment inside a pick. A combo has several, in written order."""

    kind: str
    market: str | None = None
    line: float | None = None
    direction: str | None = None
    subject: str | None = None
    note: str = ""


class ClaimReading(StrictBaseModel):
    """What one tipster's pick claims, anchored to the pick's own raw text.

    ``claim`` is the join key and the audit trail at once: whatever the reading
    says, a human can compare it to the exact string the tipster wrote.
    """

    event_id: str
    tipster_name: str
    source_id: str = ""
    claim: str
    read_confidence: str = "CLEAR"
    parser_agrees: bool = False
    legs: list[ClaimLeg] = Field(default_factory=list)
    # Set by this module, never by the agent: which path produced the reading.
    # A bad agent run is switched off by ignoring readings tagged "agent",
    # which is only possible if the tag is here.
    parsed_by: str = "agent"


class TipsterClaimsV1(StrictBaseModel):
    """TIPSTER_CLAIMS artifact: the agent's readings, validated.

    Carries no probability, no price and no aggregate by construction. Dated
    and written to disk so that re-running a day reuses one fixed reading
    instead of asking the model again -- same discipline as
    ``config/market_priors.json``: a row must not change its meaning because
    it was looked at twice.
    """

    run_id: str = ""
    date: str = ""
    generated_at: str
    readings: list[ClaimReading] = Field(default_factory=list)
    readings_accepted: int = 0
    readings_rejected: int = 0
    rejected_by_reason: dict[str, int] = Field(default_factory=dict)
    legs_total: int = 0
    legs_unreadable: int = 0
    picks_in_signal: int = 0
    parser_disagreements: int = 0


def _pick_index(signal: TipsterSignalV1) -> dict[tuple[str, str, str], object]:
    """Every collected pick, keyed by what a reading must reproduce exactly."""
    index: dict[tuple[str, str, str], object] = {}
    for event in signal.events:
        for pick in event.picks or []:
            index[(event.event_id, pick.tipster_name or "", pick.claim or "")] = pick
    return index


def _participants(signal: TipsterSignalV1) -> dict[str, set[str]]:
    return {
        event.event_id: {
            name for name in (event.home_team, event.away_team) if name
        }
        for event in signal.events
    }


def _leg_error(leg: dict, sides: set[str]) -> str | None:
    """Why this leg cannot be stored, or None if it can."""
    kind = leg.get("kind")
    if kind not in _KINDS:
        return f"nieznany kind ({kind})"

    market = leg.get("market")
    line = leg.get("line")
    direction = leg.get("direction")
    subject = leg.get("subject")

    if kind == "UNREADABLE":
        # An honest refusal. Only requirement is that it claims nothing.
        if market or line is not None or direction:
            return "UNREADABLE z wypełnionym rynkiem/linią/kierunkiem"
        return None

    if direction is not None and direction not in _DIRECTIONS:
        return f"kierunek poza słownikiem ({direction})"

    if kind == "TOTAL":
        if market not in CANONICAL_MARKETS:
            return f"rynek poza słownikiem ({market})"
        if line is None:
            return "total bez linii"
        if direction not in _TOTAL_DIRECTIONS:
            return f"total z kierunkiem {direction}"
        if market in _SUBJECT_REQUIRED and not subject:
            return f"{market} bez wskazanego podmiotu"
        if market not in _SUBJECT_REQUIRED and subject:
            return f"{market} to total meczowy, a podano podmiot"
    elif kind == "OUTCOME":
        if market or line is not None:
            return "OUTCOME z rynkiem/linią"
        if direction is not None and direction in _TOTAL_DIRECTIONS:
            return "OUTCOME z kierunkiem OVER/UNDER"

    # A player prop names somebody who is not a listed side, and football
    # fixtures list clubs -- so only reject a subject that is neither a
    # participant nor plausibly a player of one.
    if subject and subject not in sides and not (market or "").startswith("player_"):
        return "podmiot nie jest żadną ze stron meczu"
    return None


def validate_readings(
    raw: dict,
    signal: TipsterSignalV1,
    *,
    generated_at: str,
) -> TipsterClaimsV1:
    """Turn the agent's JSON into the artifact, keeping only what checks out.

    Rejection is per reading, not per file: one malformed entry must not cost
    the day's other fifty, and the count is reported so a systematic problem is
    visible rather than averaged away.
    """
    picks = _pick_index(signal)
    sides = _participants(signal)

    accepted: list[ClaimReading] = []
    rejected: dict[str, int] = {}
    rejected_count = 0
    legs_total = 0
    legs_unreadable = 0
    disagreements = 0

    def reject(reason: str) -> None:
        nonlocal rejected_count
        rejected_count += 1
        rejected[reason] = rejected.get(reason, 0) + 1

    for entry in raw.get("readings") or []:
        if not isinstance(entry, dict):
            reject("wpis nie jest obiektem")
            continue
        event_id = str(entry.get("event_id") or "")
        tipster = str(entry.get("tipster_name") or "")
        claim = entry.get("claim")
        if claim is None:
            reject("brak claimu")
            continue
        key = (event_id, tipster, str(claim))
        if key not in picks:
            # The load-bearing check. Covers a paraphrased claim, an invented
            # tipster, and a reading pinned to the wrong fixture, all at once.
            reject("nie odpowiada żadnemu zebranemu typowi")
            continue
        confidence = entry.get("read_confidence") or "CLEAR"
        if confidence not in _READ_CONFIDENCE:
            reject(f"nieznane read_confidence ({confidence})")
            continue

        legs_in = entry.get("legs") or []
        if not isinstance(legs_in, list) or not legs_in:
            reject("brak nóg w odczycie")
            continue
        legs: list[ClaimLeg] = []
        error: str | None = None
        for leg in legs_in:
            if not isinstance(leg, dict):
                error = "noga nie jest obiektem"
                break
            error = _leg_error(leg, sides.get(event_id, set()))
            if error:
                break
            legs.append(
                ClaimLeg(
                    kind=leg["kind"],
                    market=leg.get("market"),
                    line=leg.get("line"),
                    direction=leg.get("direction"),
                    subject=leg.get("subject"),
                    note=str(leg.get("note") or ""),
                )
            )
        if error:
            reject(error)
            continue

        legs_total += len(legs)
        legs_unreadable += sum(1 for leg in legs if leg.kind == "UNREADABLE")
        agrees = bool(entry.get("parser_agrees"))
        if not agrees:
            disagreements += 1
        accepted.append(
            ClaimReading(
                event_id=event_id,
                tipster_name=tipster,
                source_id=str(entry.get("source_id") or ""),
                claim=str(claim),
                read_confidence=confidence,
                parser_agrees=agrees,
                legs=legs,
                parsed_by="agent",
            )
        )

    return TipsterClaimsV1(
        run_id=signal.run_id,
        date=signal.date,
        generated_at=generated_at,
        readings=accepted,
        readings_accepted=len(accepted),
        readings_rejected=rejected_count,
        rejected_by_reason=dict(sorted(rejected.items())),
        legs_total=legs_total,
        legs_unreadable=legs_unreadable,
        picks_in_signal=len(picks),
        parser_disagreements=disagreements,
    )
