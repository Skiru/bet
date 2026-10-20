from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from bet.sofa import unmapped_prices
from bet.sofa.contracts import Fixture, FixtureOffer, PricedRung
from bet.sofa.errors import CircuitOpenError
from bet.sofa.football_1x2_dnb import RESULT_1X2
from bet.sofa.football_1x2_dnb import classify as classify_1x2_dnb
from bet.sofa.football_incidents import classify_incident
from bet.sofa.football_result import DOUBLE_CHANCE, classify_result
from bet.sofa.football_score_markets import classify as classify_score_market
from bet.sofa.market_mapper import (
    PLAYER_PROPS_V2_NAMES,
    classify_derived_market,
    classify_mappable_family,
    classify_market,
    classify_player_market,
    classify_stat_variant,
    is_ladder_answer,
)
from bet.sofa.shot_detail import MARKET_NAMES as SHOT_DETAIL_NAMES
from bet.sofa.superbet import (
    event_started,
    odds_items,
    split_match_name,
    superbet_kickoff,
)
from bet.sofa.tennis_sets import classify_set_complement, classify_set_market
from bet.sofa.tennis_winner import classify_winner
from bet.sofa.timeutil import now


def parse_line(raw_line: object, market: str) -> float:
    """The number Superbet quoted, for markets that scope a line to a period.

    A plain market sends ``specialBetValue`` as "4.5". A set-scoped one sends
    **"1-4.5"** — the set number, a dash, then the line. Reading that with
    ``float`` raises, and every per-set aces, double-faults and combined rung
    on the 2026-09-18 board landed in unmapped_markets as "unparseable line:
    '1-1.5'" (F45). The market name and the prefix carry the same scope, so
    the prefix is not information — but it is a *check*, and a rung whose
    prefix disagrees with its own market name would be a set-1 price on a
    set-2 ladder, which is worse than no rung at all.

    Raises ValueError with the text that goes into unmapped_markets.
    """
    if isinstance(raw_line, int | float):
        return float(raw_line)

    text = str(raw_line).strip()
    try:
        return float(text)
    except ValueError:
        pass

    prefix, _, rest = text.partition("-")
    if rest:
        try:
            line = float(rest)
        except ValueError:
            raise ValueError(f"unparseable line: {raw_line!r}") from None

        scope = None
        for token, name in (("set1", "1"), ("set2", "2"), ("set3", "3")):
            if token in market:
                scope = name
        for token, name in (("_1h", "1"), ("_2h", "2")):
            if token in market:
                scope = name
        if scope is not None and prefix.strip() != scope:
            raise ValueError(
                f"scope prefix {prefix.strip()!r} disagrees with market {market!r}"
            )
        if scope is None:
            # An unscoped market has no business carrying a scope prefix.
            raise ValueError(f"unexpected scope prefix on {market!r}: {raw_line!r}")
        return line

    raise ValueError(f"unparseable line: {raw_line!r}")

# (market, subject, line, direction) - one side of one rung.
ClassifiedOdd = tuple[str, str, float, str]


def classify_odd(
    item: Mapping[str, Any],
    sides: Sequence[str] = (),
    mappable_families: bool = False,
    listing_names: Sequence[str] = (),
    tennis_winner: bool = False,
    football_result: bool = False,
    shot_detail: bool = False,
    football_incidents: bool = False,
    tennis_sets: bool = False,
    player_props_v2: bool = False,
    stat_variants: bool = False,
) -> tuple[ClassifiedOdd | None, str | None]:
    """One Superbet odd as a rung side, or the label it goes into unmapped.

    Returns ``(classified, None)``, ``(None, label)`` for a market we cannot
    read, or ``(None, None)`` for an odd that is readable but not a side of a
    rung (a mapped market whose selection is neither over nor under).

    Lifted out of `OfferFetcher` on 2026-09-23 so the boost snapshot reads a
    boosted leg with exactly the classification OFFER used for the same odd;
    a second copy would drift from this one, as every duplicated predicate in
    this repo has.

    `sides` - the listing's own participant names (`listing_sides`) - lets a
    club whose name carries "&" be a subject (market_mapper.
    subject_is_combination); empty, the default, refuses every "&" as before
    2026-10-06.

    `mappable_families` (epochs.mappable_families) tries
    market_mapper.classify_mappable_family last, against `listing_names` -
    the listing's own participant names whatever the "&" rule says. Off, the
    default, is the rule before the switch exactly.

    `tennis_winner` (epochs.tennis_match_winner, a tennis fixture only) reads
    "Zwycięzca" "1" / "2" as match_won_for of the first of `listing_names`
    (bet.sofa.tennis_winner), tried before the "unmapped" label like the
    MAPPABLE families. Off, the default, changes nothing.

    `football_result` (epochs.football_result_markets, a football fixture
    only) reads the full-match "Podwójna szansa" as double_chance OVER and
    the "Mecz" outcome it leaves out as its UNDER (bet.sofa.football_result),
    tried last, like the winner. Off, the default, changes nothing.

    `shot_detail` (epochs.shot_detail_markets, a football fixture only) reads
    the eight footballer shot-detail names (shot_detail.MARKET_NAMES) as
    player markets, parsed exactly as PLAYER_MARKET_NAMES are. Off, the
    default, changes nothing.

    `football_incidents` (epochs.football_incident_markets, a football
    fixture only) reads "1. gol", "Liczba czerwonych kartek" and "Liczba
    przyznanych rzutów karnych" (bet.sofa.football_incidents) against
    `listing_names`; `tennis_sets` (epochs.tennis_set_markets, a tennis
    fixture only) reads "X. set - zwycięzca" and the exact sets score
    "Dokładny wynik" (bet.sofa.tennis_sets). Both tried last; off, the
    default, changes nothing.

    `player_props_v2` (epochs.football_player_props_v2, a football fixture
    only) reads "Zawodnik - liczba fauli na zawodniku" as
    player_fouls_drawn_for (market_mapper.PLAYER_PROPS_V2_NAMES), parsed
    exactly as PLAYER_MARKET_NAMES are. Off, the default, changes nothing.
    `stat_variants` (epochs.football_stat_variants, a football fixture only)
    reads the both-teams throw-ins / goal kicks / tackles and the shots
    handicaps (market_mapper.classify_stat_variant) against `listing_names`,
    tried last; off, the default, changes nothing.
    """
    market_name = item.get("marketName")
    if not market_name:
        return None, None
    raw_line = item.get("specialBetValue")
    selection_name = item.get("name")

    classified = classify_market(market_name, sides)
    if classified:
        market, subject = classified

        # A market with no line (or a null one) is not a rung on a ladder.
        # Reading it as 0.0 invents a line nobody quoted; letting the
        # TypeError escape takes the whole day's OFFER down over one
        # malformed market.
        if raw_line is None or raw_line == "":
            return None, f"{market_name} (no line)"
        try:
            line = parse_line(raw_line, market)
        except ValueError as exc:
            return None, f"{market_name} ({exc})"

        name_lower = str(selection_name or "").lower()
        if "poniżej" in name_lower or "under" in name_lower:
            return (market, subject, line, "UNDER"), None
        if "powyżej" in name_lower or "over" in name_lower:
            return (market, subject, line, "OVER"), None
        return None, None

    # The both-teams, comparative and handicap families. They carry their
    # line and their side on the *selection*, not on a shared
    # specialBetValue, so they cannot go through the branch above (F39).
    line_text = str(raw_line) if raw_line not in (None, "") else None
    derived = classify_derived_market(market_name, selection_name, line_text)
    if derived:
        return derived, None
    # F54. Player markets are the same shape as the derived ones - one market
    # name, the subject and the line both on the selection - and are tried
    # last so nothing above changes behaviour.
    player = classify_player_market(
        market_name, selection_name, line_text,
        _player_extra_names(shot_detail, player_props_v2),
    )
    if player:
        return player, None
    if mappable_families:
        mapped = classify_mappable_family(
            market_name, selection_name, line_text, listing_names
        )
        if mapped:
            return mapped, None
    if tennis_winner:
        winner = classify_winner(market_name, selection_name, listing_names)
        if winner:
            return winner, None
    if football_result:
        result = classify_result(market_name, selection_name)
        if result:
            return result, None
    if football_incidents:
        incident = classify_incident(
            market_name, selection_name, line_text, listing_names)
        if incident:
            return incident, None
    if tennis_sets:
        set_market = classify_set_market(market_name, selection_name, listing_names)
        if set_market:
            return set_market, None
    if stat_variants:
        variant = classify_stat_variant(
            market_name, selection_name, line_text, listing_names)
        if variant:
            return variant, None
    return None, str(market_name)


def _player_extra_names(
    shot_detail: bool, player_props_v2: bool
) -> dict[str, str] | None:
    """The player-market names beyond PLAYER_MARKET_NAMES the day reads
    (None: none, the rule before either switch)."""
    if not shot_detail and not player_props_v2:
        return None
    names: dict[str, str] = {}
    if shot_detail:
        names.update(SHOT_DETAIL_NAMES)
    if player_props_v2:
        names.update(PLAYER_PROPS_V2_NAMES)
    return names


def day_flags(date: str) -> dict[str, bool]:
    """Every OfferFetcher switch as the day's epochs set it - the one place
    OFFER (run_offer.py), the closing capture and the verifier / scout
    re-asks build their fetcher from, so a reader can never miss a market
    behind a switch (2026-10-15: the verifier's own flag list missed the new
    markets and reported 160 legs "missing"). `record_unmapped` is OFFER's
    alone and not a day switch."""
    from bet.sofa import epochs

    return {
        "ampersand_subjects": epochs.ampersand_subjects(date),
        "mappable_families": epochs.mappable_families(date),
        "tennis_winner": epochs.tennis_match_winner(date),
        "football_result": epochs.football_result_markets(date),
        "shot_detail": epochs.shot_detail_markets(date),
        "football_incidents": epochs.football_incident_markets(date),
        "tennis_sets": epochs.tennis_set_markets(date),
        "football_1x2_dnb": epochs.football_result_1x2_dnb(date),
        "football_score_markets": epochs.football_score_markets(date),
        "tennis_set_complements": epochs.tennis_set_complements(date),
        "player_props_v2": epochs.football_player_props_v2(date),
        "football_stat_variants": epochs.football_stat_variants(date),
    }


def listing_sides(payload: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Superbet's own two participant names of an event payload (matchName)."""
    side_a, side_b = split_match_name(str((payload or {}).get("matchName") or ""))
    return tuple(side for side in (side_a, side_b) if side)


class OfferFetcher:
    def __init__(
        self,
        client: Any,
        ampersand_subjects: bool = False,
        mappable_families: bool = False,
        tennis_winner: bool = False,
        record_unmapped: bool = False,
        football_result: bool = False,
        shot_detail: bool = False,
        football_incidents: bool = False,
        tennis_sets: bool = False,
        football_1x2_dnb: bool = False,
        football_score_markets: bool = False,
        tennis_set_complements: bool = False,
        player_props_v2: bool = False,
        football_stat_variants: bool = False,
    ) -> None:
        self.client = client
        # epochs.football_player_props_v2(date): read the v2 footballer
        # props (market_mapper.PLAYER_PROPS_V2_NAMES). Off is the old rule.
        self.player_props_v2 = player_props_v2
        # epochs.football_stat_variants(date): the football both-teams
        # throw-ins / goal kicks / tackles and the shots handicaps
        # (market_mapper.classify_stat_variant). Off is the old rule.
        self.football_stat_variants = football_stat_variants
        # epochs.football_score_markets(date) / tennis_set_complements(date):
        # the football "or" / handicap / DC & goals markets
        # (bet.sofa.football_score_markets) and the tennis exact-score
        # complements (tennis_sets.classify_set_complement). Off is the old
        # rule.
        self.football_score_markets = football_score_markets
        self.tennis_set_complements = tennis_set_complements
        # epochs.football_result_1x2_dnb(date): read football 1X2 and draw no
        # bet (bet.sofa.football_1x2_dnb). Off is the old rule.
        self.football_1x2_dnb = football_1x2_dnb
        # epochs.football_incident_markets(date) / tennis_set_markets(date):
        # the football first goal, red cards and penalties
        # (bet.sofa.football_incidents) and the tennis set winner and exact
        # sets score (bet.sofa.tennis_sets). Off is the old rule.
        self.football_incidents = football_incidents
        self.tennis_sets = tennis_sets
        # epochs.shot_detail_markets(date): read the footballer shot-detail
        # markets (bet.sofa.shot_detail). Off is the old rule.
        self.shot_detail = shot_detail
        # bet.sofa.unmapped_prices: keep the price of every odd that goes into
        # unmapped_markets, so a market modelled later has a price history.
        # Recording only - it changes no rung and no label.
        self.record_unmapped = record_unmapped
        self.unmapped_odds: list[dict[str, Any]] = []
        # epochs.football_result_markets(date): read the football double
        # chance (bet.sofa.football_result). Off is the old rule.
        self.football_result = football_result
        # epochs.tennis_match_winner(date): read the tennis "Zwycięzca" as
        # match_won_for (bet.sofa.tennis_winner). Off is the old rule.
        self.tennis_winner = tennis_winner
        # epochs.ampersand_subjects(date): read a club named with "&" as a
        # subject when it is the listing's own side. Off is the old rule.
        self.ampersand_subjects = ampersand_subjects
        # epochs.mappable_families(date): read the MAPPABLE families
        # (market_mapper.classify_mappable_family). Off is the old rule.
        self.mappable_families = mappable_families
        # (superbet_event_id, error) per listing that failed. One Superbet
        # error used to raise out of fetch_offers and FAIL the whole OFFER -
        # and with it the chain - over a single listing (a removed event
        # answers 404, which raise_for_status turns into an exception).
        self.errors: list[tuple[str, str]] = []
        # Fixtures never asked because Superbet's breaker opened (F6.1): the
        # fetch stops at the first CircuitOpenError instead of failing the
        # rest of the board one listing at a time. Not a price fact - the
        # caller keeps what it knew about them.
        self.not_reached: list[int] = []

    @property
    def breaker_open(self) -> bool:
        return bool(self.not_reached)

    def _add_price(
        self, item: Mapping[str, Any],
        combined_odds: dict[tuple[str, str, float], dict[str, Any]],
        answer_odds: dict[tuple[str, str, float], dict[str, Any]],
        market: str, subject: str, line: float, direction: str, price: float,
        fetched_at: datetime,
    ) -> None:
        """One active odd's price into its rung side (fetch_offers)."""
        key = (market, subject, line)
        target = combined_odds
        if self.mappable_families and is_ladder_answer(
            item.get("marketName")
        ):
            target = answer_odds
        if key not in target:
            target[key] = {
                "over_odds": None,
                "under_odds": None,
                "fetched_at_utc": fetched_at,
                "collisions": [],
            }

        # Two listings of one match must not silently overwrite
        # each other's price (F27). 20 of 484 fixtures carried two
        # superbet_event_ids; merging by union is right and
        # recovers a listing that is still live, but a *collision*
        # decided by arrival order is not a merge, it is a coin
        # flip on the only number the whole decision rests on. A
        # higher price invents an edge that is not there; a lower
        # one hides value that is.
        #
        # Take the more conservative quote — the lower one, for the
        # side being priced — and record the disagreement.
        field = "over_odds" if direction == "OVER" else "under_odds"
        new_price = price
        existing = target[key][field]
        if existing is not None and existing != new_price:
            target[key]["collisions"].append(
                f"{direction} {market} {subject or '-'} @ {line}: "
                f"{existing} vs {new_price}, taking "
                f"{min(existing, new_price)}"
            )
            new_price = min(existing, new_price)
        target[key][field] = new_price


    def fetch_offers(self, fixtures: list[Fixture]) -> list[FixtureOffer]:
        # Per call: a long-lived fetcher (capture_closing's loop) asks again
        # on its next pass, when the client's breaker lets a probe through.
        self.not_reached = []
        self.unmapped_odds = []
        results = []
        for index, fixture in enumerate(fixtures):
            if self.not_reached:
                self.not_reached.extend(
                    f.sofascore_event_id for f in fixtures[index:]
                )
                break
            combined_odds: dict[tuple[str, str, float], dict[str, Any]] = {}
            # MAPPABLE_FAMILIES: the yes/no answers to a ladder's rung
            # ("<club> strzeli gola" = goals_for 0.5), kept apart and merged
            # after every listing is read - only where no ladder quoted the
            # rung, so one quantity is never two rungs and a ladder's two
            # sides are never mixed with another market's.
            answer_odds: dict[tuple[str, str, float], dict[str, Any]] = {}
            # FOOTBALL_SCORE_MARKETS / TENNIS_SET_COMPLEMENTS: one rung side is
            # often quoted by two Superbet markets of the same event ("Mecz
            # lub liczba goli" and "<team> wygra lub powyżej X goli", "wygra
            # seta" and "Handicap setowy"): the lower price is kept, as for a
            # collision, but it is the same bet - not recorded as one.
            score_odds: dict[tuple[str, str, float], dict[str, Any]] = {}
            unmapped = set()

            failed = 0
            started_at: datetime | None = None
            seen_kickoff: datetime | None = None
            for su_id in fixture.superbet_event_ids:
                try:
                    payload = self.client.event_odds(su_id)
                except CircuitOpenError:
                    # Superbet refused enough in a row: nobody else is asked.
                    self.not_reached.append(fixture.sofascore_event_id)
                    break
                except Exception as exc:  # noqa: BLE001 - one listing, not the stage
                    self.errors.append((str(su_id), f"{type(exc).__name__}: {exc}"))
                    failed += 1
                    continue
                # Any listing Superbet reports under way marks the match: the
                # clocks can both be late, and odds_items has already dropped
                # the live odds, so without this a started match would read as
                # merely unpriced.
                if started_at is None and event_started(payload):
                    started_at = now()
                items = odds_items(payload)
                if not items:
                    continue
                # Only a listing that still quotes: a delisted duplicate keeps
                # whatever date it was pulled with.
                seen = superbet_kickoff(payload)
                if seen is not None and (seen_kickoff is None or seen < seen_kickoff):
                    seen_kickoff = seen

                fetched_at = now()
                winner = self.tennis_winner and fixture.sport == "tennis"
                result = self.football_result and fixture.sport == "football"
                shots = self.shot_detail and fixture.sport == "football"
                props_v2 = self.player_props_v2 and fixture.sport == "football"
                incidents = self.football_incidents and fixture.sport == "football"
                set_markets = self.tennis_sets and fixture.sport == "tennis"
                result_1x2_dnb = (self.football_1x2_dnb
                                  and fixture.sport == "football")
                score_markets = (self.football_score_markets
                                 and fixture.sport == "football")
                set_complements = (self.tennis_set_complements
                                   and fixture.sport == "tennis")
                stat_variants = (self.football_stat_variants
                                 and fixture.sport == "football")
                names = (
                    listing_sides(payload)
                    if (self.ampersand_subjects or self.mappable_families or winner
                        or incidents or set_markets or result_1x2_dnb
                        or score_markets or set_complements or stat_variants)
                    else ()
                )
                sides = names if self.ampersand_subjects else ()

                for item in items:
                    classified_odd, unmapped_label = classify_odd(
                        item, sides, self.mappable_families, names, winner,
                        result, shots, incidents, set_markets, props_v2,
                        stat_variants,
                    )
                    # epochs.FOOTBALL_RESULT_1X2_DNB: one odd may feed a
                    # second rung ("Mecz" 1 is the DC X2's UNDER and the
                    # result_1x2 "1" OVER); off, `extra` is empty.
                    extra = (classify_1x2_dnb(
                        item.get("marketName"), item.get("name"),
                        names[0] if len(names) == 2 else None,
                        names[1] if len(names) == 2 else None)
                        if result_1x2_dnb else [])
                    # FOOTBALL_SCORE_MARKETS / TENNIS_SET_COMPLEMENTS: names
                    # nothing above reads (only when nothing classified it).
                    scored: list[tuple[str, str, float, str]] = []
                    if classified_odd is None and not extra:
                        if score_markets:
                            scored = classify_score_market(
                                item.get("marketName"), item.get("name"),
                                names[0] if len(names) == 2 else None,
                                names[1] if len(names) == 2 else None)
                        elif set_complements:
                            complement = classify_set_complement(
                                item.get("marketName"), item.get("name"), names)
                            scored = [complement] if complement else []
                    if (extra or scored) and unmapped_label is not None:
                        unmapped_label = None
                    if unmapped_label is not None:
                        unmapped.add(unmapped_label)
                        if self.record_unmapped:
                            self.unmapped_odds.append(unmapped_prices.record(
                                fixture.sofascore_event_id, str(su_id), item,
                                fetched_at))
                    if classified_odd is None and not extra and not scored:
                        continue

                    price = item.get("price")
                    if price is None:
                        continue
                    # A suspended odd still carries its last price. It cannot be
                    # bet, so it is not an offer: 378 of 67,690 odds in the
                    # 2026-09-25 payloads were `block`, and every one was read
                    # as a live price. A payload without the field is kept.
                    if item.get("status", "active") != "active":
                        continue
                    for market, subject, line, direction in (
                            ([classified_odd] if classified_odd is not None
                             else []) + extra):
                        self._add_price(item, combined_odds, answer_odds, market,
                                        subject, line, direction, float(price),
                                        fetched_at)
                    for market, subject, line, direction in scored:
                        side = score_odds.setdefault(
                            (market, subject, line),
                            {"over_odds": None, "under_odds": None,
                             "fetched_at_utc": fetched_at, "collisions": []})
                        field = "over_odds" if direction == "OVER" else "under_odds"
                        held = side[field]
                        side[field] = (float(price) if held is None
                                       else min(held, float(price)))


            for key, entry in answer_odds.items():
                if key not in combined_odds:
                    combined_odds[key] = entry
            # Only the OVER of a score / complement rung is priced: an UNDER
            # alone (a "Nie" with no "Tak") is no offer.
            for key, entry in score_odds.items():
                if key not in combined_odds and entry["over_odds"] is not None:
                    combined_odds[key] = entry
            # FOOTBALL_RESULT_MARKETS: a "Mecz" price is only the UNDER of a
            # double chance Superbet quotes - alone it is no DC offer.
            for key in [k for k, e in combined_odds.items()
                        if k[0] == DOUBLE_CHANCE and e["over_odds"] is None]:
                del combined_odds[key]
            # FOOTBALL_RESULT_1X2_DNB: likewise a DC price alone is no 1X2
            # offer (result_1x2 is priced on its OVER only).
            for key in [k for k, e in combined_odds.items()
                        if k[0] == RESULT_1X2 and e["over_odds"] is None]:
                del combined_odds[key]

            rungs = []
            price_collisions: list[str] = []
            for (market, subject, line), odds_dict in combined_odds.items():
                price_collisions.extend(odds_dict["collisions"])
                rungs.append(
                    PricedRung(
                        market=market,
                        subject=subject,
                        line=line,
                        over_odds=odds_dict["over_odds"],
                        under_odds=odds_dict["under_odds"],
                        fetched_at_utc=odds_dict["fetched_at_utc"],
                    )
                )

            if self.not_reached and self.not_reached[-1] == fixture.sofascore_event_id:
                # Half asked (a second listing never was): not an offer.
                continue
            if failed and failed == len(fixture.superbet_event_ids):
                # Nothing was read, so nothing is known: no entry, rather than
                # an empty one that a filtered refresh's merge would let
                # overwrite the prices the previous file still holds.
                continue
            results.append(
                FixtureOffer(
                    sofascore_event_id=fixture.sofascore_event_id,
                    status="PRICED" if rungs else "NO_PRICE",
                    rungs=rungs,
                    unmapped_markets=sorted(list(unmapped)),
                    price_collisions=sorted(price_collisions),
                    superbet_started_utc=started_at,
                    superbet_kickoff_seen_utc=seen_kickoff,
                )
            )

        return results
