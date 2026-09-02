"""MARKET_CONTEXT: what the market and a model currently think, as its own artifact.

Why this is a stage and not part of ENRICH
------------------------------------------
ENRICH's entire model is sample arithmetic. A ``ProviderValue`` is an observation
of a match that was played, carrying a match id and a date you can go and check,
and ``RunBudget`` is sized around roughly thirty such calls per event. What this
module collects is a *single point-in-time snapshot*: a price is what a
bookmaker thinks right now, and a prediction is what a model thinks right now.
Neither has any matches behind it.

Folding the two together is the obvious move -- odds arrive as numbers, ENRICH
already knows how to average numbers and take a Wilson bound of them -- and it
is the one thing that would destroy ``p_low``. That figure is worth printing
only because you can ask which matches produced it and be shown them. A price
coerced into a ``ProviderValue`` answers that question with a bookmaker's name.

So this is TIPSTERS' shape, for TIPSTERS' reason: optional, additive, attached
after the sheet's own numbers already exist, structurally incapable of reaching
them. ``run_pipeline.py`` lists it in ``OPTIONAL_STEPS``, and a betting day that
loses it loses a column, not a verdict.

Three live findings this module is built around
-----------------------------------------------
Each contradicts the endpoint whose name suggests otherwise (all verified live
against sports.bzzoiro.com on 2026-08-28):

1. **The corners price comes from ``/odds/?event_id=``, never
   ``/events/{id}/odds/``.** The latter reads like "this event's odds" and
   carries no corners market at all -- only 1x2, goals over/under and BTTS. It
   is collected as context, and nothing that can promote a row reads it.
2. **``/odds/best/`` is not a per-event lookup.** It is scoped by date range and
   league; one response held 313 unrelated fixtures. The best price per line is
   therefore computed in the client, from the event's own quotes.
3. **The comparison grid is entitled on this account, and asked anyway.** It
   answered 200 with 26 bookmakers, so "Football Unlimited" is live -- but an
   entitlement is a billing state, and billing states lapse mid-run. The 403
   path is a first-class outcome, recorded as a fact rather than retried.

The uniform-provenance rule
---------------------------
When the account *is* entitled, the comparison grid already contains the corners
quotes ``/odds/`` returns, and skipping the second call would save one request
per event. It is spent anyway. The corners signal is the one thing here that can
move a row's tier, and if its source silently switched between two endpoints
depending on a subscription state, then "where did this number come from" would
have a different answer on different days for reasons having nothing to do with
football. Football is uncapped; a stable answer is worth one call.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bet.api_clients import get_client
from bet.api_clients.rate_limiter import RateLimiter
from bet.integration.source_result import SourceOperationResult, SourceResultStatus
from bet.simple_stats.contracts import (
    EventListV1,
    EventMarketContext,
    EventRecord,
    MarketContextV1,
    MarketOddsLine,
    MarketSignalColumn,
    ModelPrediction,
    StatsSheetRow,
    StatsSheetV1,
)
from bet.simple_stats.providers import RunBudget

PROVIDER = "bzzoiro"

# This stage is football-only, and after 2026-09-02 that is stated rather than
# implied. It used to also fetch a tennis model forecast from bzzoiro's tennis
# product; that provider has answered HTTP 402 ``addon_required`` since
# 2026-09-01 and has been removed from the pipeline, so there is no tennis
# model to consult and no call to make. A tennis row's ``market_signal`` is
# whatever ``market_signal_for_row`` makes of having neither a model nor a
# market probability -- which is ``NO_MARKET_DATA``, the same verdict it
# reached on every tennis row of the last slate that ran.

# The only market this stage fetches quotes for.
#
# Not an arbitrary narrowing: bzzoiro's odds feed publishes fourteen markets and
# **none of them is cards, fouls or shots-on-target**, so three of the five
# markets this pipeline prices can never receive a real price no matter how much
# quota is spent. Of what remains, corners is the single market where the
# pipeline's own historical hit-rate, a real bookmaker price, and an independent
# model probability all exist at the same line -- which is the whole premise of
# the signal built on top of this.
#
# Goals is the other one: ENRICH now extracts home_score/away_score into
# goals_total/goals_for (docs/PLAN_BOGATE_STATYSTYKI.md Faza 1), and the feed
# already carries both the price (``over_under_05/15/25/35``) and the model
# probability (``prob_goals_over_15/25/35``) for it. BTTS is still not here:
# the feed has a price for it, but no row exists for it yet.
SIGNAL_MARKET = "total_corners"

# Per-event call cost, so a caller can size a run before spending anything:
# quotes, consensus block, comparison grid -- and the prediction only for the
# fixtures the day's ``/predictions/`` listing did not already cover.
#
# Three, not four, since 2026-08-30. The listing costs one call for the whole
# slate (146 forecasts for one date, measured live) and the per-event endpoint
# survives as the fallback, so the true cost is ``3N + 1`` plus one call for
# each fixture the model has not published yet. Kept as the pessimistic 4 for
# sizing: a day the model has not forecast at all still has to fit.
CALLS_PER_EVENT = 4

# Account-wide and process-wide, mirroring how ``providers.py`` memoizes ESPN's
# league capability. Keyed by nothing because there is nothing to key on: the
# entitlement belongs to the subscription, not to a league or a fixture, so one
# probe answers for every event in the run.
_ENTITLEMENT_CACHE: dict[str, str] = {}


def reset_entitlement_cache() -> None:
    """Forget the probe result. For tests, and for a long-lived process that
    wants a fresh answer rather than one cached across betting days."""
    _ENTITLEMENT_CACHE.clear()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def eligible_events(event_list: EventListV1, now: datetime | None = None) -> list[EventRecord]:
    """Events this stage can and should spend calls on, in ENRICH's own order.

    Football only, and that is a quota decision rather than a coverage one:
    bzzoiro's tennis product is a separate 95-a-day bucket (``bzzoiro-tennis``)
    that ENRICH already spends against, and roughly six fully enriched fixtures
    exhausts it. Market context for tennis would come out of the same allowance
    that produces tennis's actual statistics, so it waits for a measurement of
    what a normal tennis run leaves over -- not a guess.

    An event needs bzzoiro's own id: every endpoint here is keyed by it, and an
    event some other source found alone has nothing to look up.

    **The sort is ``_enrichment_priority``, deliberately borrowed from ENRICH.**
    Both stages take a ``--max-events`` slice, and taking them in different
    orders is not a cosmetic difference: on the first live run of this stage
    (2026-08-28, ``--max-events 12``) ENRICH ranked by identity confidence then
    kickoff while this stage took event-list order, and the two slices
    overlapped on **three of twelve fixtures**. Three quarters of the calls
    bought context for events that produced no stats-sheet row, and three
    quarters of the rows that could have carried a signal got
    ``NO_MARKET_DATA``. Sharing the ranking is what makes a capped run's two
    budgets land on the same matches.

    ``now`` is injectable only so a test can pin the clock. ``_enrichment_priority``
    demotes started fixtures, so a test that hardcodes a kickoff date is a time
    bomb: this stage's ordering test held all morning on 2026-08-28 and began
    failing at 18:00 UTC that day, when its "early" fixture kicked off and sorted
    behind its "late" one. A suite whose answer changes with the wall clock
    cannot tell tomorrow's regression from tomorrow's afternoon.
    """
    from bet.simple_stats.enrich import _enrichment_priority

    now = now or datetime.now(timezone.utc)
    candidates = [
        event
        for event in event_list.events
        if event.sport == "football"
        and event.status == "ACTIVE"
        and event.source_ids.get(PROVIDER)
    ]
    candidates.sort(key=lambda event: _enrichment_priority(event, now))
    return candidates


def _probe_entitlement(client: Any, provider_event_id: str) -> tuple[str, SourceOperationResult | None]:
    """Is this account entitled to the per-bookmaker grid? Asked once per run.

    The probe is a real comparison call against a real discovered fixture rather
    than a synthetic one, so its answer is also the first event's data and no
    call is wasted establishing it.
    """
    cached = _ENTITLEMENT_CACHE.get("football_unlimited")
    if cached is not None:
        return cached, None
    result = client.get_odds_comparison_result(provider_event_id)
    entitlement = _entitlement_of(result)
    # Only a definitive answer is cached. A transport error says nothing about
    # the subscription, and caching it would silently disable the grid for the
    # rest of a run over one dropped connection.
    if entitlement in ("ENTITLED", "NOT_ENTITLED"):
        _ENTITLEMENT_CACHE["football_unlimited"] = entitlement
    return entitlement, result


def _entitlement_of(result: SourceOperationResult) -> str:
    if result.status in (SourceResultStatus.SUCCESS, SourceResultStatus.VALID_EMPTY):
        value = result.value or {}
        return str(value.get("entitlement") or "ERROR")
    return "ERROR"


def _quotes_from(result: SourceOperationResult) -> list[MarketOddsLine]:
    if result.status not in (SourceResultStatus.SUCCESS, SourceResultStatus.VALID_EMPTY):
        return []
    value = result.value or {}
    return [MarketOddsLine(**quote) for quote in value.get("quotes") or []]


def collect_market_context(
    event_list: EventListV1,
    rate_limiter: RateLimiter,
    *,
    max_events: int | None = None,
    budget: RunBudget | None = None,
) -> MarketContextV1:
    """Fetch prices and model reads for a day's football slate.

    Never raises on a provider problem. Every failure lands in the event's
    ``data_gaps`` and the run continues: this artifact is optional by
    construction, and the stats sheet does not depend on it.
    """
    budget = budget or RunBudget()
    candidates = eligible_events(event_list)
    if max_events is not None:
        candidates = candidates[:max_events]

    client = get_client(PROVIDER, rate_limiter=rate_limiter)
    contexts: list[EventMarketContext] = []
    calls = 0
    entitlement_seen: str | None = None

    # --- one call that answers the model for the whole slate ---------------
    #
    # ``/predictions/`` carries the same forecast ``/events/{id}/prediction/``
    # serves one fixture at a time: 146 of them for a single date, measured
    # live 2026-08-30. Prefetching turns the per-event cost from four calls
    # into three, and the per-event endpoint stays as the fallback for
    # fixtures the list did not cover rather than being replaced by it.
    #
    # A failure here is not a gap on any event: nothing was promised and the
    # fallback path is unchanged, so the run simply pays the old price.
    prefetched: dict[str, dict[str, Any]] = {}
    prefetch_note = ""
    if candidates and budget.try_consume(PROVIDER):
        calls += 1
        listing = client.get_predictions_list_result(date=event_list.date)
        if listing.status in (SourceResultStatus.SUCCESS, SourceResultStatus.VALID_EMPTY):
            prefetched = dict((listing.value or {}).get("predictions") or {})
        else:
            prefetch_note = (
                f"model prediction listing unavailable: {listing.status} "
                f"{listing.error_code}; fell back to one call per fixture"
            )

    for event in candidates:
        provider_event_id = event.source_ids[PROVIDER]
        gaps: list[str] = []
        unknown_markets: list[str] = []

        # --- the signal path: this event's corners quotes ------------------
        odds: list[MarketOddsLine] = []
        if budget.try_consume(PROVIDER):
            calls += 1
            result = client.get_odds_result(provider_event_id, market=SIGNAL_MARKET)
            if result.status in (SourceResultStatus.SUCCESS, SourceResultStatus.VALID_EMPTY):
                odds = _quotes_from(result)
                unknown_markets.extend((result.value or {}).get("unknown_markets") or [])
                if not odds:
                    gaps.append(f"no {SIGNAL_MARKET} quotes published for this fixture")
            else:
                gaps.append(f"corners odds unavailable: {result.status} {result.error_code}")
        else:
            gaps.append("corners odds skipped: run call budget exhausted")

        # --- context: the provider's consensus block ----------------------
        consensus: dict[str, float] = {}
        if budget.try_consume(PROVIDER):
            calls += 1
            result = client.get_consensus_odds_result(provider_event_id)
            if result.status in (SourceResultStatus.SUCCESS, SourceResultStatus.VALID_EMPTY):
                consensus = dict((result.value or {}).get("consensus_odds") or {})
            else:
                gaps.append(f"consensus odds unavailable: {result.status} {result.error_code}")
        else:
            gaps.append("consensus odds skipped: run call budget exhausted")

        # --- depth: the per-bookmaker grid, entitlement permitting ---------
        comparison: list[MarketOddsLine] = []
        entitlement = "NOT_ATTEMPTED"
        bookmakers_count = 0
        if _ENTITLEMENT_CACHE.get("football_unlimited") != "NOT_ENTITLED":
            if budget.try_consume(PROVIDER):
                calls += 1
                entitlement, result = _probe_entitlement(client, provider_event_id)
                if result is None:
                    # The probe was already answered by an earlier event, so this
                    # is a plain fetch rather than a probe.
                    result = client.get_odds_comparison_result(provider_event_id)
                    entitlement = _entitlement_of(result)
                if entitlement == "ENTITLED":
                    comparison = _quotes_from(result)
                    bookmakers_count = int((result.value or {}).get("bookmakers_count") or 0)
                    unknown_markets.extend((result.value or {}).get("unknown_markets") or [])
                elif entitlement == "ERROR":
                    gaps.append(
                        f"bookmaker comparison unavailable: {result.status} {result.error_code}"
                    )
                # An entitlement that worked earlier this run and 403s now is
                # surfaced rather than smoothed over: a subscription that lapses
                # mid-run makes the artifact half one thing and half another,
                # and that is exactly what an operator needs told.
                if (
                    entitlement_seen == "ENTITLED"
                    and entitlement == "NOT_ENTITLED"
                ):
                    gaps.append(
                        "ANOMALY: bookmaker comparison was entitled earlier in this "
                        "run and answered 403 here -- the grid in this artifact is "
                        "not uniform across events"
                    )
            else:
                gaps.append("bookmaker comparison skipped: run call budget exhausted")
        else:
            entitlement = "NOT_ENTITLED"
        if entitlement in ("ENTITLED", "NOT_ENTITLED"):
            entitlement_seen = entitlement

        # --- the independent second opinion -------------------------------
        prediction: ModelPrediction | None = None
        if prefetch_note:
            gaps.append(prefetch_note)
        if provider_event_id in prefetched:
            # Same parser, same fields, no request. The list and the per-event
            # endpoint share ``_parse_prediction_row`` precisely so that this
            # branch cannot produce a different number from the one below.
            prediction = ModelPrediction(**prefetched[provider_event_id])
        elif budget.try_consume(PROVIDER):
            calls += 1
            result = client.get_prediction_result(provider_event_id)
            if result.status is SourceResultStatus.SUCCESS:
                prediction = ModelPrediction(**(result.value or {})["prediction"])
            elif result.status is SourceResultStatus.NOT_FOUND:
                gaps.append("no model prediction published for this fixture")
            else:
                gaps.append(f"model prediction unavailable: {result.status} {result.error_code}")
        else:
            gaps.append("model prediction skipped: run call budget exhausted")

        contexts.append(
            EventMarketContext(
                event_id=event.event_id,
                provider_event_id=provider_event_id,
                odds=odds,
                consensus_odds=consensus,
                bookmaker_comparison=comparison,
                comparison_entitlement=entitlement,  # type: ignore[arg-type]
                bookmakers_count=bookmakers_count,
                predictions=prediction,
                unknown_markets=sorted(set(unknown_markets)),
                data_gaps=gaps,
            )
        )

    return MarketContextV1(
        run_id=event_list.run_id,
        date=event_list.date,
        generated_at=_now_iso(),
        football_unlimited_entitled=_entitlement_cache_as_bool(),
        events_considered=len(candidates),
        provider_calls=calls,
        events=contexts,
    )


def _entitlement_cache_as_bool() -> bool | None:
    """None when never probed -- which is a different statement from False.

    A run that spent no calls has learned nothing about the subscription, and
    reporting that as "not entitled" would have an operator chasing a billing
    problem that does not exist.
    """
    cached = _ENTITLEMENT_CACHE.get("football_unlimited")
    if cached == "ENTITLED":
        return True
    if cached == "NOT_ENTITLED":
        return False
    return None


# ---------------------------------------------------------------------------
# The column: triangulation, and the four ways it must refuse to produce one.

# Stats-sheet markets this signal may ever be computed for, mapped to the odds
# feed's own market code.
#
# ``goals_total``'s value here is a placeholder, never read as the actual feed
# code: unlike every other entry, the feed has one market *per line*
# (``over_under_05/15/25/35``, see ``GOALS_FEED_MARKETS`` below), so
# ``market_signal_for_row`` resolves its real feed market from the row's line
# rather than from this table. The entry still has to exist here, because this
# table is also the gate that decides whether a market is in scope at all --
# without it a goals row would return ``None`` (out of scope) instead of
# ``NO_MARKET_DATA`` on 4.5, the one line the feed has no code for at all.
#
# Of the five football markets this pipeline prices, bzzoiro's odds feed covers
# exactly two: there is no cards market, no fouls market and no
# shots-on-target market anywhere in its fourteen codes, and the CatBoost
# model publishes probabilities for none of them either. A row on
# ``cards_total`` therefore cannot be handed a signal -- not a weak one, not a
# partial one -- and the restriction lives here, in the one function that
# could otherwise invent it.
#
# ``corners_for`` and ``goals_for`` are absent for the same reason: the feed's
# markets are match totals, so pointing a per-team row at one would compare a
# single team's total against a price for both teams'.
SIGNAL_MARKETS: dict[str, str] = {
    "corners_total": SIGNAL_MARKET,
    "goals_total": "over_under_by_line",
    # Tennis had two entries here between 2026-08-30 and 2026-09-02. They are
    # gone with the provider that filled them: this stage's only tennis input
    # was bzzoiro's model forecast, and with no model and no tennis odds a
    # tennis market is not "in scope but unpriced", it is out of scope. Left in
    # place, the entries would have every tennis row report a
    # ``NO_MARKET_DATA`` verdict -- a sentence that reads as "the model and the
    # market did not agree enough to say" when what happened is that neither
    # was ever consulted.
}

# goals_total's feed code depends on the line, unlike every other market this
# stage handles. 4.5 has no code in the feed at all (bzzoiro publishes exactly
# four over/under lines) and is never interpolated from 3.5's.
GOALS_FEED_MARKETS: dict[float, str] = {
    0.5: "over_under_05",
    1.5: "over_under_15",
    2.5: "over_under_25",
    3.5: "over_under_35",
}

# Stats-sheet line -> the model's field for P(over) at that exact line.
#
# The model publishes three corner lines. ``STANDARD_MARKET_LINES`` prices four
# (8.5, 9.5, 10.5, 11.5), so an 11.5 row has no model probability and is told so.
# There is deliberately no nearest-line fallback: over 10.5 is not weak evidence
# about over 11.5, it is evidence about a different bet.
MODEL_CORNERS_FIELDS: dict[float, str] = {
    8.5: "prob_corners_over_85",
    9.5: "prob_corners_over_95",
    10.5: "prob_corners_over_105",
}

# The model publishes 1.5/2.5/3.5. ``STANDARD_MARKET_LINES`` also prices 0.5
# and 4.5 -- neither has a model field, so both are told so rather than
# interpolated from a neighbour.
MODEL_GOALS_FIELDS: dict[float, str] = {
    1.5: "prob_goals_over_15",
    2.5: "prob_goals_over_25",
    3.5: "prob_goals_over_35",
}



def _model_probability(
    prediction: ModelPrediction | None,
    line: float,
    direction: str,
    market: str = "corners_total",
) -> float | None:
    """P(this direction at this exact line) from the model, or None.

    Never interpolates between lines. Over 10.5 corners is not weak evidence
    about over 11.5 -- it is evidence about a different bet.
    """
    if prediction is None:
        return None
    if market == "corners_total":
        field = MODEL_CORNERS_FIELDS.get(line)
    elif market == "goals_total":
        field = MODEL_GOALS_FIELDS.get(line)
    else:
        return None
    if field is None:
        return None
    prob_over = getattr(prediction, field)
    if prob_over is None:
        return None
    return prob_over if direction == "OVER" else 1.0 - prob_over


def _best_quote(quotes: list[MarketOddsLine], market: str, line: float, outcome: str) -> MarketOddsLine | None:
    """The highest price on this exact (market, line, outcome), or None.

    Recomputed here rather than trusting the ``is_best`` flag set at parse time,
    because these quotes may have arrived from either the odds feed or the
    comparison grid and only one list has been through ``_mark_best_quotes``.
    """
    candidates = [
        quote
        for quote in quotes
        if quote.market == market and quote.line == line and quote.outcome == outcome
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda quote: quote.price)


# Preferred for the de-vig because it is the lowest-margin book in the feed
# (verified live 2026-08-28) -- when it quotes both sides of a line, that pair
# has the least overround of any available, so removing it distorts the
# probability the least.
PREFERRED_DEVIG_BOOKMAKER = "pinnacle"


def _same_bookmaker_probability(
    quotes: list[MarketOddsLine], market: str, line: float, direction: str
) -> tuple[float | None, str]:
    """De-vigged P(direction) at this line, from **one** bookmaker's own over
    and under prices, or None and why not.

    Never pairs an over from one book with an under from another. The two
    legs of one book's own line are guaranteed to sum to roughly that book's
    margin (~1.02-1.08); the best over across ~26 books and the best under
    across the same ~26 can come from different books entirely, and their
    sum can land anywhere -- below 1.00 (a synthetic arbitrage that exists only
    on paper) or comfortably above it, and the ratio the probability is read
    from tilts toward whichever side more books are pricing aggressively. At
    corners' ~12 quotes a match that distortion is small; at goals' ~624
    quotes across ~26 books (verified live 2026-08-30) it is not.

    Pinnacle is tried first when it quotes both sides of this exact line;
    otherwise the first bookmaker, in quote order, that quotes both sides is
    used. A bookmaker that quotes only one side of a line never contributes
    a pairing here, which is a difference from ``_best_quote``: that function
    is allowed to answer from one side, this one is not.
    """
    by_book: dict[str | None, dict[str, MarketOddsLine]] = {}
    book_order: list[str | None] = []
    for quote in quotes:
        if quote.market != market or quote.line != line or quote.outcome not in ("over", "under"):
            continue
        book = quote.bookmaker_slug
        if book not in by_book:
            by_book[book] = {}
            book_order.append(book)
        sides = by_book[book]
        existing = sides.get(quote.outcome)
        if existing is None or quote.price > existing.price:
            sides[quote.outcome] = quote

    ordered_books = book_order
    if PREFERRED_DEVIG_BOOKMAKER in by_book:
        ordered_books = [PREFERRED_DEVIG_BOOKMAKER] + [b for b in book_order if b != PREFERRED_DEVIG_BOOKMAKER]

    for book in ordered_books:
        sides = by_book.get(book, {})
        over = sides.get("over")
        under = sides.get("under")
        if over is None or under is None:
            continue
        implied_over = 1.0 / over.price
        implied_under = 1.0 / under.price
        total = implied_over + implied_under
        if total <= 0:
            continue
        probability = (implied_over if direction == "OVER" else implied_under) / total
        return probability, ""

    return None, f"no single bookmaker quotes both sides of line {line}"


def _market_probability(
    quotes: list[MarketOddsLine], market: str, line: float, direction: str
) -> tuple[float | None, MarketOddsLine | None, str]:
    """De-vigged P(direction) at this line, the best price for this leg, and
    why not if there is no probability.

    The price and the probability are allowed to come from different places
    on purpose: the reported price is the best available across every
    bookmaker (what an operator would actually be offered), while the
    probability is computed from a single bookmaker's own paired quotes (see
    ``_same_bookmaker_probability``) so the overround being removed is a real
    one, not an artefact of mixing books.

    **Both legs are required.** A single leg's 1/decimal_odds is not a
    probability: it carries the bookmaker's whole margin, so an over quoted at
    1.38 reads as a 72% chance when the two-way market is really pricing it near
    68%. Since the only thing this number is used for is a threshold comparison
    against a model probability, an inflated one turns the margin itself into
    agreement -- consistently, and in the direction of confirming whatever the
    row already says.

    So a line quoted on one side only yields a price (which is real, and worth
    reporting) and no probability (which would not be).
    """
    over = _best_quote(quotes, market, line, "over")
    under = _best_quote(quotes, market, line, "under")
    wanted = over if direction == "OVER" else under
    if over is None and under is None:
        return None, None, f"no market quote at line {line}"
    if over is None or under is None:
        return None, wanted, (
            f"line {line} is quoted on one side only, so the overround cannot be "
            "removed and no implied probability is reported"
        )
    probability, reason = _same_bookmaker_probability(quotes, market, line, direction)
    if probability is None:
        return None, wanted, reason
    return probability, wanted, ""


def market_signal_for_row(
    row: StatsSheetRow,
    context: EventMarketContext | None,
) -> MarketSignalColumn | None:
    """The market column for one stats-sheet row, or None if out of scope.

    None and ``NO_MARKET_DATA`` mean different things and both are used. None is
    "this row is not the kind of thing a market signal can address" -- a cards
    row, a player prop, a tennis total -- and leaves the field unset, exactly as
    a run without this stage would. ``NO_MARKET_DATA`` is "this row is in scope
    and the data did not turn up", which is a fact about today worth recording
    with a reason attached.

    A verdict needs **both** signals. One alone is not triangulation: the model
    and the market are frequently fitted to overlapping information, and a single
    agreeing number is the easiest possible thing to find in support of a
    direction already chosen. This mirrors the two-independent-domains bar the
    analyst doc already applies to web evidence.
    """
    feed_market = SIGNAL_MARKETS.get(row.market)
    if feed_market is None:
        return None
    if context is None:
        return MarketSignalColumn(verdict="NO_MARKET_DATA", reason="no market context for this event")

    # goals_total is one feed code *per line* (SIGNAL_MARKETS' entry for it is
    # a placeholder, not a real code -- see the comment there), unlike every
    # other market handled here, which is one code for every line it prices.
    if row.market == "goals_total":
        feed_market = GOALS_FEED_MARKETS.get(row.line)

    model_probability = _model_probability(
        context.predictions, row.line, row.direction, row.market
    )
    # Concatenated, never `or`: `context.odds` carries only `total_corners`, so
    # whenever any corners quote exists the `or` short-circuits and every quote
    # in `bookmaker_comparison` -- where goals and BTTS actually live -- is
    # silently dropped. `_best_quote` already filters by (market, line,
    # outcome), so combining the two lists cannot introduce a wrong match.
    quotes = [*context.odds, *context.bookmaker_comparison]
    market_probability, quote, market_reason = _market_probability(
        quotes, feed_market, row.line, row.direction
    )

    sources: list[str] = []
    if model_probability is not None and context.predictions is not None:
        sources.append(f"model:{context.predictions.model_version or 'unknown'}")
    if quote is not None:
        sources.append(f"market:{quote.bookmaker_slug or 'unknown'}")

    if model_probability is None or market_probability is None:
        reasons = []
        if row.market == "corners_total":
            known_lines = MODEL_CORNERS_FIELDS
        else:
            known_lines = MODEL_GOALS_FIELDS
        if model_probability is None:
            reasons.append(
                f"no model probability at line {row.line}"
                if row.line not in known_lines
                else f"model published no {row.market} probability for this fixture"
            )
        if market_probability is None:
            reasons.append(market_reason or "no market probability")
        return MarketSignalColumn(
            verdict="NO_MARKET_DATA",
            model_probability=model_probability,
            market_implied_probability=market_probability,
            market_price=quote.price if quote is not None else None,
            market_bookmaker=quote.bookmaker_slug if quote is not None else None,
            sources=sources,
            reason="; ".join(reasons),
        )

    model_backs = model_probability > 0.5
    market_backs = market_probability > 0.5
    if model_backs and market_backs:
        verdict = "CONFIRMS"
    elif not model_backs and not market_backs:
        # Both at exactly 0.5 lands here rather than in CONFIRMS: a coin flip is
        # not support for a direction.
        verdict = "CONTRADICTS"
    else:
        verdict = "SPLIT"

    return MarketSignalColumn(
        verdict=verdict,  # type: ignore[arg-type]
        model_probability=model_probability,
        market_implied_probability=market_probability,
        market_price=quote.price if quote is not None else None,
        market_bookmaker=quote.bookmaker_slug if quote is not None else None,
        sources=sources,
    )


def attach_market_context_column(
    stats_sheet: StatsSheetV1, context: MarketContextV1
) -> StatsSheetV1:
    """Return a copy of the sheet with ``row.market_signal`` populated.

    Every other field is copied verbatim and the row order is preserved. The
    sheet's ranking is a statistical ranking, and neither a bookmaker nor a model
    gets a vote in it -- a reader who wants to sort by market agreement does it
    on screen, where the reordering is visible.
    """
    by_event = {event.event_id: event for event in context.events}
    rows = [
        row.model_copy(
            update={"market_signal": market_signal_for_row(row, by_event.get(row.event_id))}
        )
        for row in stats_sheet.rows
    ]
    return stats_sheet.model_copy(update={"rows": rows})


def summarize(context: MarketContextV1) -> dict[str, object]:
    """Flat metrics for the AGENT_SUMMARY contract."""
    with_odds = sum(1 for event in context.events if event.odds)
    with_predictions = sum(1 for event in context.events if event.predictions is not None)
    with_corner_model = sum(
        1
        for event in context.events
        if event.predictions is not None
        and any(
            getattr(event.predictions, field) is not None
            for field in (
                "prob_corners_over_85",
                "prob_corners_over_95",
                "prob_corners_over_105",
            )
        )
    )
    unknown: set[str] = set()
    for event in context.events:
        unknown.update(event.unknown_markets)
    # Kept as a standing statement rather than a per-fixture gap. This stage is
    # football-only: its one tennis input was bzzoiro's tennis model, removed on
    # 2026-09-02 with the rest of that provider, so there is no longer a
    # per-event fact to report -- only a fact about the stage.
    #
    # The metric survives the provider because what it exists to prevent has
    # not changed. Until 2026-09-02 a structurally empty tennis column read
    # identically to a slate with no tennis on it, and the operator had no way
    # to tell "nobody bought the addon" from "there was no tennis today". Now
    # the run says which it is before anyone has to ask.
    tennis_unaddressable = [
        "MARKET_CONTEXT is football-only since 2026-09-02: its one tennis input "
        "was the bzzoiro tennis model, removed after answering HTTP 402 "
        "addon_required, so no tennis row carries a market_signal at all"
    ]
    return {
        "date": context.date,
        "events_considered": context.events_considered,
        "events_with_odds": with_odds,
        "events_with_predictions": with_predictions,
        "events_with_corner_model": with_corner_model,
        "football_unlimited_entitled": context.football_unlimited_entitled,
        "provider_calls": context.provider_calls,
        "unknown_markets": sorted(unknown),
        "tennis_model_unavailable": tennis_unaddressable,
    }
