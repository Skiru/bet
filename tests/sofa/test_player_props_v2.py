"""Football player props v2 behind epochs.FOOTBALL_PLAYER_PROPS_V2_FROM_UTC
(None): "Zawodnik - liczba fauli na zawodniku" as player_fouls_drawn_for
(Sofascore /lineups `wasFouled`, a missing key a zero only where the
opponent's team fouls bound the squad's sum). Offline and fast. Evidence:
docs/sofa/evidence/football_player_props_v2_2026-10-21.md."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from bet.sofa import engine, epochs
from bet.sofa import offer as offer_mod
from bet.sofa.confidence import PLAYER_PROP_MARKETS, quantity_family
from bet.sofa.contracts import GapReason
from bet.sofa.leg_relations import mapped_sheet_markets
from bet.sofa.market_mapper import (
    PLAYER_PROPS_V2_NAMES,
    classify_player_market,
    fold,
    get_mechanism_family,
    is_player_market,
)
from bet.sofa.offer import classify_odd
from bet.sofa.players import (
    OPPONENT_BOUND_MAX_SHORTFALL,
    PLAYER_METRICS,
    PLAYER_PROPS_V2_METRICS,
    ZERO_PROVEN_BY_OPPONENT_KEY,
    ZERO_PROVEN_KEY,
    extract_player_metric,
    squad_statistics,
)
from bet.sofa.superbet_names import names
from scripts.sofa import run_settle
from tests.sofa.offer_mappable_scenarios import (
    FROZEN,
    _Client,
    fixture,
    payloads,
)

M = "player_fouls_drawn_for"
NAME = "Zawodnik - liczba fauli na zawodniku"


# --- the switch ---------------------------------------------------------------


def test_switch_is_off_and_reads_the_day_and_the_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    assert epochs.FOOTBALL_PLAYER_PROPS_V2_FROM_UTC is None
    assert epochs.FOOTBALL_PLAYER_PROPS_V2 == "player_props_v2"
    late = datetime(2030, 1, 1, tzinfo=UTC)
    assert not epochs.football_player_props_v2("2030-01-01", late)
    assert offer_mod.day_flags("2030-01-01")["player_props_v2"] is False
    on = datetime(2026, 10, 21, tzinfo=UTC)
    monkeypatch.setattr(epochs, "FOOTBALL_PLAYER_PROPS_V2_FROM_UTC", on)
    assert epochs.football_player_props_v2("2026-10-21", on)
    assert not epochs.football_player_props_v2("2026-10-20", late)
    assert not epochs.football_player_props_v2(
        "2026-10-21", datetime(2026, 10, 20, 23, tzinfo=UTC))


# --- OFFER --------------------------------------------------------------------


def _item(name: str, sel: str, sbv: str | None, price: float) -> dict[str, Any]:
    return {"marketName": name, "name": sel, "specialBetValue": sbv,
            "price": price, "status": "active", "offerStateId": 1}


def test_the_name_parses_only_when_asked() -> None:
    sel = "Santi Comesana - powyżej 1.5"
    sbv = "sr:player:1008335-Santi Comesana-1.5"
    assert classify_player_market(NAME, sel, sbv) is None
    assert classify_player_market(NAME, sel, sbv, PLAYER_PROPS_V2_NAMES) == (
        M, "Santi Comesana", 1.5, "OVER")
    item = _item(NAME, sel, sbv, 2.05)
    assert classify_odd(item) == (None, NAME)
    assert classify_odd(item, player_props_v2=True) == (
        (M, "Santi Comesana", 1.5, "OVER"), None)
    # both extra tables at once: each still reads its own names
    assert classify_odd(item, shot_detail=True, player_props_v2=True)[0] == (
        M, "Santi Comesana", 1.5, "OVER")
    assert classify_odd(item, shot_detail=True) == (None, NAME)
    shot = _item("Zawodnik - liczba strzałów głową", "Olise, Michael - powyżej 0.5",
                 "sr:player:1-Olise, Michael-0.5", 3.0)
    assert classify_odd(shot, shot_detail=True, player_props_v2=True)[0] == (
        "player_headed_shots_for", "Olise, Michael", 0.5, "OVER")
    # the committed-fouls market is untouched by the table
    committed = ("Zawodnik - liczba popełnionych fauli",
                 "Kowalski, Jan - powyżej 1.5", "sr:player:1-Kowalski, Jan-1.5")
    assert classify_player_market(*committed) == classify_player_market(
        *committed, PLAYER_PROPS_V2_NAMES) == (
        "player_fouls_for", "Kowalski, Jan", 1.5, "OVER")


def _offers(v2: bool) -> dict[int, dict[str, Any]]:
    data = payloads()
    fixtures = [fixture(sport, str(p["eventId"])) for sport, p in sorted(data.items())]
    saved = offer_mod.now
    offer_mod.now = lambda: FROZEN  # type: ignore[assignment]
    try:
        offers = offer_mod.OfferFetcher(
            _Client(data), ampersand_subjects=True, player_props_v2=v2,
        ).fetch_offers(fixtures)
    finally:
        offer_mod.now = saved  # type: ignore[assignment]
    return {o.sofascore_event_id: o.model_dump(mode="json") for o in offers}


def test_switch_on_offer_adds_fouls_drawn_rungs_and_nothing_else() -> None:
    data = payloads()
    football_id = int(data["football"]["eventId"])
    tennis_id = int(data["tennis"]["eventId"])
    off, on = _offers(False), _offers(True)
    assert on[tennis_id] == off[tennis_id]
    new = [r for r in on[football_id]["rungs"] if r["market"] == M]
    assert new and all(r["subject"] and r["over_odds"] for r in new)
    assert all(r["under_odds"] is None for r in new)  # Superbet quotes OVER only
    rest = [r for r in on[football_id]["rungs"] if r["market"] != M]
    assert rest == off[football_id]["rungs"]
    assert NAME in off[football_id]["unmapped_markets"]
    assert NAME not in on[football_id]["unmapped_markets"]
    assert not any(r["market"] == M for r in off[football_id]["rungs"])


# --- the zero proof -------------------------------------------------------------


def _entry(name: str, fouled: int | None, *, minutes: int | None = 90,
           substitute: bool = False) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    if minutes is not None:
        stats["minutesPlayed"] = minutes
    if fouled is not None:
        stats["wasFouled"] = fouled
    return {"player": {"id": hash(name) % 10**6, "name": name},
            "substitute": substitute, "statistics": stats}


def _statistics(home_fouls: float, away_fouls: float) -> dict[str, Any]:
    return {"statistics": [{"period": "ALL", "groups": [{"statisticsItems": [
        {"key": "fouls", "homeValue": home_fouls, "awayValue": away_fouls}]}]}]}


def _lineups(home: list[dict[str, Any]]) -> dict[str, Any]:
    return {"home": {"players": home}, "away": {"players": []}}


HOME = [_entry("Jan Kowalski", 3), _entry("Adam Nowak", None),
        _entry("Piotr Zielinski", 1), _entry("Bench Man", None, minutes=None)]


def test_a_missing_key_is_zero_when_the_opponent_fouls_bound_the_sum() -> None:
    # home drew 4 named fouls, the away side committed 5 (one a handball)
    squad = squad_statistics(_lineups(HOME), is_home=True,
                             statistics=_statistics(10, 5))
    assert squad is not None
    assert extract_player_metric(M, squad["jan kowalski"]) == 3.0
    assert extract_player_metric(M, squad["adam nowak"]) == 0.0
    # the bench man never played: the appearance gate, not a zero
    assert isinstance(extract_player_metric(M, squad["bench man"]), GapReason)
    # the team-sum list is what it was: wasFouled is not on it
    assert "wasFouled" not in (squad["adam nowak"].get(ZERO_PROVEN_KEY) or ())
    assert squad["adam nowak"][ZERO_PROVEN_BY_OPPONENT_KEY] == ["wasFouled"]


@pytest.mark.parametrize("away_fouls", [3.0, 4.0 + OPPONENT_BOUND_MAX_SHORTFALL + 1])
def test_a_sum_above_or_far_below_the_opponent_fouls_proves_nothing(
        away_fouls: float) -> None:
    squad = squad_statistics(_lineups(HOME), is_home=True,
                             statistics=_statistics(10, away_fouls))
    assert squad is not None
    assert extract_player_metric(M, squad["adam nowak"]) == GapReason.STAT_KEY_ABSENT
    assert extract_player_metric(M, squad["jan kowalski"]) == 3.0


def test_the_shortfall_edge_is_inclusive() -> None:
    squad = squad_statistics(
        _lineups(HOME), is_home=True,
        statistics=_statistics(10, 4.0 + OPPONENT_BOUND_MAX_SHORTFALL))
    assert squad is not None
    assert extract_player_metric(M, squad["adam nowak"]) == 0.0


def test_no_statistics_or_a_feed_without_the_key_is_a_gap() -> None:
    squad = squad_statistics(_lineups(HOME), is_home=True)
    assert squad is not None
    assert extract_player_metric(M, squad["adam nowak"]) == GapReason.STAT_KEY_ABSENT
    bare = [_entry("Jan Kowalski", None), _entry("Adam Nowak", None)]
    squad = squad_statistics(_lineups(bare), is_home=True,
                             statistics=_statistics(10, 0))
    assert squad is not None
    assert extract_player_metric(M, squad["adam nowak"]) == GapReason.STAT_KEY_ABSENT


def test_the_proof_never_changes_another_metric() -> None:
    entries = [dict(e, statistics=dict(e["statistics"], fouls=1))
               for e in HOME[:3]]
    with_stats = squad_statistics(_lineups(entries), is_home=True,
                                  statistics=_statistics(3, 5))
    assert with_stats is not None
    for name, rec in with_stats.items():
        for metric in PLAYER_METRICS:
            if metric == M:
                continue
            bare = {k: v for k, v in rec.items() if k != ZERO_PROVEN_BY_OPPONENT_KEY}
            assert extract_player_metric(metric, rec) == extract_player_metric(
                metric, bare), (name, metric)


# --- SETTLE -------------------------------------------------------------------


def _row(line: float) -> dict[str, Any]:
    return {"market": M, "subject": "Kowalski, Jan", "line": line,
            "direction": "OVER"}


def test_settle_grades_fouls_drawn_from_his_own_squad() -> None:
    lineups = _lineups(HOME)
    stats = _statistics(10, 5)
    squads = {h: squad_statistics(lineups, is_home=h, statistics=stats)
              for h in (True, False)}
    assert run_settle._settle_player(_row(2.5), squads, True) == (3.0, "WIN")
    assert run_settle._settle_player(_row(3.5), squads, True) == (3.0, "LOSS")
    nowak = {"market": M, "subject": "Nowak, Adam", "line": 0.5, "direction": "OVER"}
    assert run_settle._settle_player(nowak, squads, True) == (0.0, "LOSS")


def test_settle_voids_a_substitute_like_every_player_prop() -> None:
    lineups = _lineups([_entry("Jan Kowalski", 2, substitute=True),
                        _entry("Adam Nowak", 1)])
    stats = _statistics(10, 3)
    squads = {h: squad_statistics(lineups, is_home=h, statistics=stats)
              for h in (True, False)}
    graded = run_settle._settle_player(_row(0.5), squads, True)
    assert graded == "PLAYER_NOT_STARTED"


# --- every consumer knows the metric -----------------------------------------


def test_every_consumer_knows_fouls_drawn() -> None:
    assert PLAYER_PROPS_V2_METRICS == {M} == set(PLAYER_PROPS_V2_NAMES.values())
    assert M in PLAYER_METRICS and M in PLAYER_PROP_MARKETS
    assert is_player_market(M)
    assert fold(NAME) in PLAYER_PROPS_V2_NAMES
    assert quantity_family(M) == quantity_family("fouls_for")
    assert get_mechanism_family(M) == get_mechanism_family("fouls_for")
    assert ("football", M) in mapped_sheet_markets()
    assert engine.uses_negative_binomial(M)
    assert names({"sport": "football", "market": M, "subject": "Kowalski, Jan",
                  "line": 1.5, "direction": "OVER"}) == (
        NAME, "Kowalski, Jan - powyżej 1.5")


# --- SHEET --------------------------------------------------------------------


def _sheet_rows(values: list[float]) -> list[Any]:
    from datetime import timedelta

    from bet.sofa.config import SofaConfig
    from bet.sofa.contracts import (
        FixtureOffer,
        FixtureSamples,
        Observation,
        PlayerSample,
        PricedRung,
    )
    from scripts.sofa.run_sheet import process_fixture
    from tests.sofa.test_player_markets import _fixture

    day = datetime(2026, 9, 22, tzinfo=UTC)
    obs = [Observation(sofascore_event_id=1000 + i,
                       match_date_utc=day - timedelta(days=i + 1),
                       value=float(v), opponent=f"O{i}", venue="home",
                       competition_id=1, season_id=1, minutes=90.0)
           for i, v in enumerate(values)]
    sample = PlayerSample(metric=M, player="Kowalski, Jan",
                          matched_name="jan kowalski", side="side_a",
                          squad_matches=len(values), observations=obs,
                          appearances="starts")
    samples = FixtureSamples(sofascore_event_id=1, readiness="READY", gaps=[],
                             metrics={}, players={f"{M}|Kowalski, Jan": sample})
    rung = PricedRung(market=M, subject="Kowalski, Jan", line=0.5, over_odds=1.27,
                      under_odds=None, fetched_at_utc=day)
    offer = FixtureOffer(sofascore_event_id=1, status="PRICED",
                         unmapped_markets=[], rungs=[rung])
    rows, _ = process_fixture(
        _fixture(), samples, offer, baselines={}, reliability={},
        engine_constants={}, vetoes=[], config=SofaConfig(), stats_only=True)
    return [r for r in rows if r.market == M]


def test_sheet_prices_fouls_drawn_with_the_negative_binomial() -> None:
    import statistics

    values = [2.0, 0.0, 1.0, 3.0, 1.0, 0.0, 2.0]
    over = [r for r in _sheet_rows(values) if r.direction == "OVER"][0]
    mean, var, n = statistics.mean(values), statistics.variance(values), len(values)
    sd = engine.sheet_predictive_sd(M, "football", mean, var, n, mean)
    want = engine.calc_p_central_nb_raw(
        mean, sd, engine.winning_boundary(0.5, "OVER"), "OVER")
    assert over.p_central == pytest.approx(want, abs=1e-4)
    assert over.sample_mean == pytest.approx(mean, abs=1e-3)


def test_the_row_marker_is_absent_unless_set() -> None:
    from scripts.sofa.run_sheet import sheet_row_json

    row = _sheet_rows([2.0, 0.0, 1.0, 3.0, 1.0, 0.0, 2.0])[0]
    assert "player_props_v2_rule" not in sheet_row_json(row)
    marked = row.model_copy(update={
        "player_props_v2_rule": epochs.FOOTBALL_PLAYER_PROPS_V2})
    assert sheet_row_json(marked)["player_props_v2_rule"] == "player_props_v2"


def test_the_staged_curve_group_is_installable_by_name() -> None:
    from scripts.sofa.install_new_market_curves import DEFAULT_TARGET, GROUPS

    assert "player_props_v2" in GROUPS
    assert DEFAULT_TARGET["player_props_v2"] == "sofa_confidence_calibration.json"
