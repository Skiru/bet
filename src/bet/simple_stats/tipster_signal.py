"""TIPSTERS: public-opinion coverage as a column beside ``p_low``, never inside it.

The rule this module exists to enforce
--------------------------------------
A tipster pick is an opinion, not an observation. It has no sample behind it, it
is frequently derived from the same public numbers this pipeline already reads,
and it sometimes carries a bookmaker affiliation. Folding it into a probability
would destroy the one property that makes ``p_low`` worth printing: that you can
ask where the number came from and be shown specific matches and specific
providers.

So the signal is reported alongside the statistics and is structurally incapable
of reaching them. ``build_tipster_signal`` produces its own artifact;
``attach_tipster_column`` writes to exactly one optional field of each
``StatsSheetRow`` and touches nothing else. ``tests/simple_stats/
test_tipster_signal.py`` asserts that invariant field by field, because a rule
that is only written down is a rule that erodes.

Two things a naive version of this would get wrong
--------------------------------------------------
**Counting the wrong market.** Tipsters overwhelmingly publish 1X2. Of the 98
picks in the live 2026-08-25 run, 12 were plain match totals; the rest were
outcomes, parlays, team totals, player props or halves. Counting any of those
toward "3 of 5 agree on under 10.5 corners" produces a number that looks like
corroboration and is not about corners at all. :mod:`bet.tipsters.claim` decides
what is comparable and records why each exclusion happened, and the excluded
counts travel into the artifact so an empty column is auditable.

**Counting a different fixture.** Sources spell clubs their own way ("Bodo/Glimt"
vs "Bodø/Glimt", "Sabah Baku (Aze)" vs "Sabah FK"), so matching has to be fuzzy;
but fuzzy matching that is too eager attributes one town's team to another's.
The threshold is deliberately high, both sides must match, and every match
records its score and whether it was exact, so a suspicious attribution is
visible in the artifact rather than buried in an aggregate.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from bet.simple_stats.contracts import (
    EventListV1,
    EventRecord,
    StatsSheetRow,
    StatsSheetV1,
    TipsterColumn,
    TipsterEventSignal,
    TipsterPickRef,
    TipsterSignalV1,
)
from bet.tipsters.claim import MarketClaim, classify_claim
from bet.tipsters.contracts import TipsterPick
from bet.tipsters.matching import pair_score, side_score
from bet.tipsters.normalization import normalize_key

# Both sides must clear this. 82 is what bet.tipsters.pipeline_adapter already
# uses for cross-source event grouping, so a pick that two sources agree is the
# same fixture is matched to our event by the same standard. Raising it loses
# real matches ("Sabah Baku (Aze)" against "Sabah FK" scores in the eighties);
# lowering it starts joining distinct clubs that share a city name.
MATCH_THRESHOLD = 82

# Outcome families whose picks form the public-sentiment summary. Explicitly not
# a superset of the countable markets: these are reported *because* they are a
# different market, and the two counts are never added together.
_LEAN_DIRECTIONS = ("HOME", "AWAY", "DRAW", "DC", "BTTS_YES", "BTTS_NO", "WIN")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_sides(event: EventRecord) -> tuple[str, str]:
    """Home/away for football, player one/two for tennis."""
    if event.sport == "tennis":
        return event.player_one or "", event.player_two or ""
    return event.home_team or "", event.away_team or ""


def _pair_score(pick: TipsterPick, home: str, away: str, sport: str) -> tuple[int, bool]:
    """Best of straight and swapped orientation, via :mod:`bet.tipsters.matching`.

    Sources disagree about which side is listed first often enough that ignoring
    the swap loses genuine matches; ``swapped`` is returned so a caller can tell
    a reversed listing from an exact one.

    Tennis is scored as people rather than clubs: the sides are players, and
    "Sakkari M." is the same person as "Maria Sakkari" for a reason no club rule
    describes.
    """
    return pair_score(
        pick.home_team or "", pick.away_team or "", home, away, person=(sport == "tennis")
    )


# ``bet.tipsters.live`` keeps picks within a day of the betting date, because a
# source states its fixture dates in its own timezone. Here we have the event's
# real UTC kickoff, so the same tolerance can be checked against the actual
# fixture instead of against the calendar day -- which is what stops the second
# leg of a tie, or last week's meeting of the same two clubs, from attaching to
# today's row.
MAX_KICKOFF_DRIFT = timedelta(days=1)


def _event_utc_date(event: EventRecord) -> datetime | None:
    raw = (event.start_time or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _date_is_plausible(pick: TipsterPick, event: EventRecord) -> bool:
    """Could this pick be about this fixture, date-wise?

    Undated picks pass: the only thing known about them is that they appeared on
    a page requested for this day, and refusing them here would silently discard
    every Typersi pick.
    """
    if not pick.match_date:
        return True
    kickoff = _event_utc_date(event)
    if kickoff is None:
        return True
    try:
        stated = datetime.strptime(pick.match_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return abs(stated - kickoff) <= MAX_KICKOFF_DRIFT + timedelta(days=1)


def _match_pick_to_event(pick: TipsterPick, events: list[EventRecord]) -> tuple[EventRecord | None, int, bool]:
    """Best-scoring event above threshold, or nothing.

    Sport must agree exactly. The sources label disciplines themselves
    (ZawodTyper's ``discipline``, which the parser now maps rather than
    defaulting everything to football), so a mismatch here means one of the two
    is wrong about what game it is -- not a naming variation to be smoothed over.
    """
    best: tuple[EventRecord | None, int, bool] = (None, 0, False)
    for event in events:
        if event.sport != pick.sport:
            continue
        home, away = _event_sides(event)
        if not home or not away:
            continue
        if not _date_is_plausible(pick, event):
            continue
        score, swapped = _pair_score(pick, home, away, event.sport)
        if score > best[1]:
            best = (event, score, swapped)
    if best[1] < MATCH_THRESHOLD:
        return None, best[1], False
    return best


def _pick_ref(pick: TipsterPick, claim: MarketClaim) -> TipsterPickRef:
    return TipsterPickRef(
        source_id=pick.source_id,
        source_name=pick.source_name,
        tipster_name=pick.tipster_name,
        claim=claim.raw or pick.market,
        market=claim.market if claim.countable else None,
        line=claim.line if claim.countable else None,
        subjects=list(claim.subjects) if claim.countable else [],
        direction=claim.direction if claim.countable else pick.direction,
        countable=claim.countable,
        reject_reason=claim.reject_reason,
        odds=pick.odds_decimal,
        tipster_accuracy_pct=pick.tipster_accuracy_pct,
        tipster_bet_count=pick.tipster_bet_count,
        match_date=pick.match_date,
        source_url=pick.source_url,
    )


def _public_lean(picks: list[TipsterPick]) -> dict[str, int]:
    """Tally of outcome-market directions for one fixture."""
    lean = Counter(
        pick.direction
        for pick in picks
        if pick.direction in _LEAN_DIRECTIONS and not pick.is_combo
    )
    return dict(sorted(lean.items(), key=lambda item: (-item[1], item[0])))


def build_tipster_signal(
    event_list: EventListV1,
    picks: list[TipsterPick],
    *,
    date_filter: dict[str, int] | None = None,
    sources_attempted: list[str] | None = None,
    sources_blocked: list[dict[str, str]] | None = None,
) -> TipsterSignalV1:
    """Match every pick to a discovered event and classify its claim."""
    events = list(event_list.events)
    by_event: dict[str, list[tuple[TipsterPick, MarketClaim]]] = {}
    match_meta: dict[str, tuple[str, int]] = {}
    unmatched: list[str] = []

    for pick in picks:
        event, score, swapped = _match_pick_to_event(pick, events)
        if event is None:
            unmatched.append(f"{pick.event} [{pick.sport}] via {pick.source_id}")
            continue
        # Scope is judged against the *source's* spelling of the sides, not the
        # event's: the claim text was written by the source, so "FK Sabah" is
        # what has to be recognised in it, not our "Sabah FK".
        claim = classify_claim(pick.market, pick.home_team, pick.away_team)
        # A source-declared parlay outranks the text classification: ZawodTyper's
        # bet builder flag is authoritative about its own products even when the
        # rendered claim reads like a single leg.
        if pick.is_combo and not claim.is_combo:
            claim = MarketClaim(
                raw=claim.raw,
                market=claim.market,
                direction=claim.direction,
                line=claim.line,
                scope=claim.scope,
                is_combo=True,
                countable=False,
                reject_reason="combo_bet_legs_not_separable",
                notes=[*claim.notes, "combo_flagged_by_source"],
            )
        by_event.setdefault(event.event_id, []).append((pick, claim))
        quality = "EXACT" if score == 100 and not swapped else "FUZZY"
        previous = match_meta.get(event.event_id)
        if previous is None or score > previous[1]:
            match_meta[event.event_id] = (quality, score)

    signals: list[TipsterEventSignal] = []
    for event_id, entries in by_event.items():
        event = next(e for e in events if e.event_id == event_id)
        home, away = _event_sides(event)
        quality, score = match_meta[event_id]
        signals.append(
            TipsterEventSignal(
                event_id=event_id,
                home_team=home,
                away_team=away,
                match_quality=quality,  # type: ignore[arg-type]
                match_score=score,
                picks=[_pick_ref(pick, claim) for pick, claim in entries],
                public_lean=_public_lean([pick for pick, _ in entries]),
            )
        )
    signals.sort(key=lambda s: (-len(s.picks), s.event_id))

    matched = sum(len(s.picks) for s in signals)
    return TipsterSignalV1(
        run_id=event_list.run_id,
        date=event_list.date,
        generated_at=_now_iso(),
        sources_attempted=sources_attempted or sorted({p.source_id for p in picks}),
        sources_with_picks=sorted({p.source_id for p in picks}),
        sources_blocked=sources_blocked or [],
        picks_ingested=len(picks),
        picks_matched=matched,
        picks_unmatched=len(unmatched),
        countable_claims=sum(1 for s in signals for p in s.picks if p.countable),
        date_filter=dict(date_filter or {}),
        unmatched_events=sorted(set(unmatched)),
        events=signals,
    )


def column_for_row(
    row: StatsSheetRow,
    signal: TipsterSignalV1,
    events_by_id: dict[str, TipsterEventSignal] | None = None,
) -> TipsterColumn | None:
    """The tipster column for one stats-sheet row, or None if uncovered.

    Line equality is exact and intentionally unforgiving. A tipster on over 9.5
    corners is not evidence about over 10.5: those bets resolve differently, and
    treating them as one is precisely how "3 of 5" stops meaning anything.

    ``events_by_id`` is an optional prebuilt index; without it the lookup is a
    linear scan, which is fine for one row and quadratic across a whole sheet.
    """
    if events_by_id is None:
        events_by_id = {e.event_id: e for e in signal.events}
    event = events_by_id.get(row.event_id)
    if event is None:
        return None

    agree = 0
    oppose = 0
    exact = 0
    sources: set[str] = set()
    excluded: Counter[str] = Counter()

    for pick in event.picks:
        if not pick.countable:
            excluded[pick.reject_reason or "unclassified"] += 1
            continue
        if pick.market != row.market:
            excluded["different_market"] += 1
            continue
        if not _addresses_same_subject(pick, row):
            excluded["different_team_or_player"] += 1
            continue
        stance = _stance(pick, row)
        if stance is None:
            excluded["line_too_weak_to_inform"] += 1
            continue
        if pick.line == row.line:
            exact += 1
        if stance == "AGREE":
            agree += 1
        else:
            oppose += 1
        sources.add(pick.source_id)

    if agree == 0 and oppose == 0:
        verdict = "NO_COVERAGE"
    elif oppose == 0:
        verdict = "CONFIRMS"
    elif agree == 0:
        verdict = "CONTRADICTS"
    else:
        verdict = "SPLIT"

    return TipsterColumn(
        verdict=verdict,  # type: ignore[arg-type]
        agree=agree,
        oppose=oppose,
        exact=exact,
        considered=len(event.picks),
        sources=sorted(sources),
        lean=dict(event.public_lean or {}),
        excluded=dict(sorted(excluded.items())),
    )


def _stance(pick: TipsterPickRef, row: StatsSheetRow) -> str | None:
    """"AGREE", "OPPOSE", or None when the claim says nothing about this row.

    Exact line equality was the original rule, and it is why the column read
    NO_COVERAGE on every row of the 2026-09-01 slate. The sheet prints only the
    one or two lines its own statistics favour -- Barracas Central's fouls at
    8.5 -- while a tipster takes whatever line the bookmaker hung, 13.5. Two
    claims about the same team's fouls, and they could never meet.

    The relation that does hold is implication, and it is exact rather than
    fuzzy. A total is monotone: if a tipster is right that the count clears
    13.5, then it also clears 8.5, so an OVER claim settles every OVER row at or
    below its line and refutes every UNDER row at or below it. Nothing is
    smoothed over and no line is treated as approximately another; a claim
    either settles this row's bet or it is dropped as uninformative.
    """
    if pick.line is None or pick.direction not in ("OVER", "UNDER"):
        return None
    if pick.direction == row.direction:
        stronger = pick.line >= row.line if row.direction == "OVER" else pick.line <= row.line
        return "AGREE" if stronger else None
    # Opposite sides. The claim refutes the row only when its own line leaves no
    # room for the row to win: "under 8.5" kills "over 8.5" and "over 13.5",
    # while "under 13.5" leaves "over 8.5" perfectly winnable.
    refutes = pick.line <= row.line if row.direction == "OVER" else pick.line >= row.line
    return "OPPOSE" if refutes else None


def _addresses_same_subject(pick: TipsterPickRef, row: StatsSheetRow) -> bool:
    """Is the claim about the same team or player this row is about?

    Market and line alone are not enough once per-team and per-player rows are
    countable. A sheet prints ``fouls_for OVER 13.5`` once per side, so a claim
    about one team's fouls matches the market and line of *both* rows, and
    joining on those two fields would report the tipster as corroborating the
    opponent as well -- doubling the agreement count and half of it inverted.

    Names are compared with the same matcher used for fixtures, so the club a
    tipster calls "Barracas Centra" reaches the row the sheet calls "Barracas
    Central".
    """
    # player_name first, and not team_name: every player row carries *both*
    # (all 10,929 of them on the 2026-09-01 sheet), because a prop is drawn from
    # a named XI. Reading team_name first compared "Yamal Lamine celne strzały
    # 2+" against "Barcelona" and silently excluded the entire player-prop
    # family -- the largest one the sheet prints.
    subject = row.player_name or row.team_name
    if subject is None:
        # A match total names no subject, and a claim about one is not about it.
        return not pick.subjects
    if not pick.subjects:
        return False
    person = row.player_name is not None
    return any(side_score(claimed, subject, person=person) >= 90 for claimed in pick.subjects)


def attach_tipster_column(stats_sheet: StatsSheetV1, signal: TipsterSignalV1) -> StatsSheetV1:
    """Return a copy of the sheet with ``row.tipster`` populated.

    Every other field is copied verbatim, and the row order is preserved: the
    sheet's ranking is a statistical ranking and tipster opinion does not get a
    vote in it. Callers that want to see agreement sort by it themselves, on
    screen, where the reordering is visible.
    """
    events_by_id = {event.event_id: event for event in signal.events}
    rows = [
        row.model_copy(update={"tipster": column_for_row(row, signal, events_by_id)})
        for row in stats_sheet.rows
    ]
    return stats_sheet.model_copy(update={"rows": rows})


def summarize(signal: TipsterSignalV1) -> dict[str, object]:
    """Flat metrics for the AGENT_SUMMARY contract."""
    reject_counts: Counter[str] = Counter()
    for event in signal.events:
        for pick in event.picks:
            if not pick.countable:
                reject_counts[pick.reject_reason or "unclassified"] += 1
    return {
        "date": signal.date,
        "events_covered": len(signal.events),
        "picks_ingested": signal.picks_ingested,
        "picks_matched": signal.picks_matched,
        "picks_unmatched": signal.picks_unmatched,
        "countable_claims": signal.countable_claims,
        "sources_with_picks": signal.sources_with_picks,
        "date_filter": signal.date_filter,
        "excluded_by_reason": dict(reject_counts.most_common()),
    }
