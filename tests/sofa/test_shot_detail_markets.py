"""The footballer shot-detail markets wired through OFFER, SAMPLES, SHEET,
CONFIDENCE and SETTLE behind epochs.SHOT_DETAIL_MARKETS_FROM_UTC (None).
Offline and fast. Evidence: docs/sofa/evidence/shot_detail_2026-10-14.md.

The Superbet names are the real ones (tests/sofa/golden/offer_mappable_items.
json, Villarreal - Napoli, 2026-10-12); the shotmap is Viking - Bayern
2026-10-13 (tests/sofa/golden/shotmap_viking_bayern_2026-10-13.json), where
Superbet settled "Michael Olise - celne strzały spoza pola karnego powyżej
0.5" WON."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bet.sofa import epochs
from bet.sofa import offer as offer_mod
from bet.sofa import shot_detail as sd
from bet.sofa.cache import SofaCache
from bet.sofa.confidence import (
    PLAYER_PROP_MARKETS,
    Calibration,
    direction_key,
    one_sided_single,
    quantity_family,
)
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import (
    FixtureOffer,
    FixtureSamples,
    GapReason,
    Observation,
    PlayerSample,
    PricedRung,
)
from bet.sofa.line_evidence import LineEvidence
from bet.sofa.market_mapper import (
    classify_player_market,
    fold,
    get_mechanism_family,
    is_player_market,
)
from bet.sofa.offer import classify_odd
from bet.sofa.players import (
    PLAYER_METRICS,
    extract_player_metric,
    position,
    squad_statistics,
)
from bet.sofa.samples import build_player_samples, fetch_shotmap
from bet.sofa.sheet_config import fingerprint
from scripts.sofa import run_settle
from scripts.sofa.run_sheet import (
    load_shot_detail,
    process_fixture,
    sheet_row_json,
    shot_detail_rows,
)
from tests.sofa.offer_mappable_scenarios import (
    FROZEN,
    GOLDEN_DIR,
    _Client,
    dumps,
    fixture,
    payloads,
)

SHOTMAP = json.loads(
    (Path(__file__).parent / "golden" / "shotmap_viking_bayern_2026-10-13.json")
    .read_text(encoding="utf-8"))
OLISE = 978838
STAGED_FIT = Path(__file__).parents[2] / "data" / "refit_shot_detail_2026-10-14" \
    / "sofa_shot_detail.json"
# A fitted file of the staged shape (fit_shot_detail.py), values made up.
FIT: dict[str, Any] = {
    "window": 10, "min_starts": 5,
    "metrics": {m: {"k": 5, "pool": {"G": 0.0, "D": 0.1, "M": 0.3, "F": 0.5},
                    "pool_all": 0.25}
                for m in sd.METRICS},
}
PRE_KICKOFF = datetime(2026, 9, 22, tzinfo=UTC)


def _item(market: str, selection: str, sbv: str, price: float) -> dict[str, Any]:
    return {"marketName": market, "name": selection, "specialBetValue": sbv,
            "offerStateId": 1, "price": price, "status": "active"}


# --- the switch --------------------------------------------------------------


def test_switch_reads_the_day_and_the_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    # operator 2026-10-14: on from 14:20Z into the built day (mixed)
    on = datetime(2026, 10, 14, 14, 20, tzinfo=UTC)
    assert epochs.SHOT_DETAIL_MARKETS_FROM_UTC == on
    switch = epochs.shot_detail_markets
    assert not switch("2026-10-13", datetime(2027, 1, 1, tzinfo=UTC))
    assert not switch("2026-10-14", datetime(2026, 10, 14, 14, 19, tzinfo=UTC))
    assert switch("2026-10-14", on)
    monkeypatch.setattr(epochs, "SHOT_DETAIL_MARKETS_FROM_UTC", None)
    assert epochs.SHOT_DETAIL_MARKETS == "shot_detail_v1"
    late = datetime(2027, 1, 1, tzinfo=UTC)
    assert not epochs.shot_detail_markets("2027-01-01", late)
    monkeypatch.setattr(epochs, "SHOT_DETAIL_MARKETS_FROM_UTC",
                        datetime(2026, 10, 16, tzinfo=UTC))
    assert epochs.shot_detail_markets(
        "2026-10-16", datetime(2026, 10, 16, 1, tzinfo=UTC))
    assert not epochs.shot_detail_markets("2026-10-15", late)
    assert not epochs.shot_detail_markets(
        "2026-10-16", datetime(2026, 10, 15, 23, tzinfo=UTC))


# --- OFFER: the names ---------------------------------------------------------


@pytest.mark.parametrize("name,metric", [
    ("Zawodnik - liczba strzałów spoza pola karnego", "player_shots_outside_box_for"),
    ("Zawodnik - liczba celnych strzałów spoza pola karnego",
     "player_sot_outside_box_for"),
    ("Zawodnik - liczba strzałów głową", "player_headed_shots_for"),
    ("Zawodnik - liczba celnych strzałów głową", "player_sot_headed_for"),
    ("Zawodnik - liczba strzałów lewą nogą", "player_left_foot_shots_for"),
    ("Zawodnik - liczba celnych strzałów lewą nogą", "player_sot_left_foot_for"),
    ("Zawodnik - liczba strzałów prawą nogą", "player_right_foot_shots_for"),
    ("Zawodnik - liczba celnych strzałów prawą nogą", "player_sot_right_foot_for"),
])
def test_the_eight_names_parse_like_the_player_markets_only_when_asked(
        name: str, metric: str) -> None:
    sel = "Olise, Michael - powyżej 0.5"
    sbv = "sr:player:1-Olise, Michael-0.5"
    assert classify_player_market(name, sel, sbv) is None
    assert classify_player_market(name, sel, sbv, sd.MARKET_NAMES) == (
        metric, "Olise, Michael", 0.5, "OVER")
    item = _item(name, sel, sbv, 2.4)
    assert classify_odd(item) == (None, name)
    assert classify_odd(item, shot_detail=True) == (
        (metric, "Olise, Michael", 0.5, "OVER"), None)


def test_the_extra_table_never_changes_an_existing_player_market() -> None:
    args = ("Zawodnik - liczba strzałów", "Kowalski, Jan - powyżej 1.5",
            "sr:player:1-Kowalski, Jan-1.5")
    assert classify_player_market(*args) == classify_player_market(
        *args, sd.MARKET_NAMES) == ("player_shots_for", "Kowalski, Jan", 1.5, "OVER")
    # a goal "spoza pola karnego" is another market, still unread
    assert classify_player_market(
        "Zawodnik - strzeli gola spoza pola karnego", "Kowalski, Jan - powyżej 0.5",
        None, sd.MARKET_NAMES) is None


def _offers(shot_detail: bool) -> dict[int, dict[str, Any]]:
    data = payloads()
    fixtures = [fixture(sport, str(p["eventId"])) for sport, p in sorted(data.items())]
    saved = offer_mod.now
    offer_mod.now = lambda: FROZEN  # type: ignore[assignment]
    try:
        offers = offer_mod.OfferFetcher(
            _Client(data), ampersand_subjects=True, mappable_families=False,
            shot_detail=shot_detail).fetch_offers(fixtures)
    finally:
        offer_mod.now = saved  # type: ignore[assignment]
    return {o.sofascore_event_id: o.model_dump(mode="json") for o in offers}


def test_switch_off_offer_is_byte_identical_to_the_golden() -> None:
    golden = (GOLDEN_DIR / "offer_mappable_off.json").read_text(encoding="utf-8")
    assert dumps(list(_offers(False).values())) + "\n" == golden


def test_switch_on_offer_adds_the_eight_families_to_football_only() -> None:
    data = payloads()
    football_id = int(data["football"]["eventId"])
    tennis_id = int(data["tennis"]["eventId"])
    off, on = _offers(False), _offers(True)
    assert on[tennis_id] == off[tennis_id]
    new = [r for r in on[football_id]["rungs"] if r["market"] in sd.METRICS]
    assert {r["market"] for r in new} == set(sd.METRICS)
    assert all(r["subject"] and r["over_odds"] for r in new)
    rest = [r for r in on[football_id]["rungs"] if r["market"] not in sd.METRICS]
    assert rest == off[football_id]["rungs"]
    left = set(off[football_id]["unmapped_markets"]) - set(
        on[football_id]["unmapped_markets"])
    assert {sd.MARKET_NAMES[fold(n)] for n in left} == set(sd.METRICS)
    assert "Zawodnik - strzeli gola spoza pola karnego" in on[football_id][
        "unmapped_markets"]


# --- players: the counts from the shotmap -------------------------------------


def _olise(total_shots: float | None = 3, substitute: bool = False,
           pid: int = OLISE) -> dict[str, Any]:
    stats: dict[str, Any] = {"minutesPlayed": 90}
    if total_shots is not None:
        stats["totalShots"] = total_shots
    return {"player": {"id": pid, "name": "Michael Olise", "position": "F"},
            "position": "M", "substitute": substitute, "statistics": stats}


def _lineups(*away: dict[str, Any]) -> dict[str, Any]:
    return {"home": {"players": []}, "away": {"players": list(away)}}


def test_squad_statistics_counts_olise_from_the_golden_shotmap() -> None:
    squad = squad_statistics(_lineups(_olise()), is_home=False, shotmap=SHOTMAP)
    assert squad is not None
    olise = squad["michael olise"]
    assert extract_player_metric("player_shots_outside_box_for", olise) == 2.0
    assert extract_player_metric("player_sot_outside_box_for", olise) == 1.0
    assert extract_player_metric("player_left_foot_shots_for", olise) == 3.0
    assert extract_player_metric("player_headed_shots_for", olise) == 0.0
    assert position(olise) == "M"  # the lineups entry's, before the player's


def test_a_shot_total_mismatch_is_a_gap_not_a_count() -> None:
    squad = squad_statistics(_lineups(_olise(total_shots=4)), is_home=False,
                             shotmap=SHOTMAP)
    assert squad is not None
    for metric in sd.METRICS:
        assert extract_player_metric(metric, squad["michael olise"]) == (
            GapReason.STAT_KEY_ABSENT)
    no_total = squad_statistics(_lineups(_olise(total_shots=None)),
                                is_home=False, shotmap=SHOTMAP)
    assert no_total is not None
    assert extract_player_metric(
        "player_sot_outside_box_for", no_total["michael olise"]) == (
        GapReason.STAT_KEY_ABSENT)


def test_no_shotmap_is_a_gap_never_a_zero() -> None:
    for shotmap in (None, {}, {"shotmap": []}):
        squad = squad_statistics(_lineups(_olise()), is_home=False, shotmap=shotmap)
        assert squad is not None
        for metric in sd.METRICS:
            assert extract_player_metric(metric, squad["michael olise"]) == (
                GapReason.STAT_KEY_ABSENT)


def test_a_starter_with_no_shot_and_zero_total_counts_zero() -> None:
    squad = squad_statistics(_lineups(_olise(total_shots=0, pid=1)),
                             is_home=False, shotmap=SHOTMAP)
    assert squad is not None
    for metric in sd.METRICS:
        assert extract_player_metric(metric, squad["michael olise"]) == 0.0


def test_without_a_shotmap_argument_the_squad_is_unchanged() -> None:
    lineups = _lineups(_olise())
    plain = squad_statistics(lineups, is_home=False)
    assert plain is not None
    assert set(plain["michael olise"]) == {"minutesPlayed", "totalShots", "_started"}


def test_every_consumer_knows_the_eight_metrics() -> None:
    for metric in sd.METRICS:
        assert metric in PLAYER_METRICS and metric in PLAYER_PROP_MARKETS
        assert is_player_market(metric)
        assert quantity_family(metric) == quantity_family("shots_for")
        assert get_mechanism_family(metric) == get_mechanism_family("shots_for")


# --- SAMPLES ------------------------------------------------------------------


def test_fetch_shotmap_caches_a_terminal_event_and_its_empty_answer(
        tmp_path: Path) -> None:
    from bet.sofa.db import migrate

    db = str(tmp_path / "sofa.db")
    migrate(db)
    cache = SofaCache(SofaConfig(db_path=db))
    client = MagicMock()
    client.event_shotmap.return_value = SHOTMAP
    event = {"id": 16939021, "status": {"type": "finished"}}
    assert fetch_shotmap(client, cache, event) == SHOTMAP
    assert fetch_shotmap(client, cache, event) == SHOTMAP
    assert client.event_shotmap.call_count == 1
    client.event_shotmap.return_value = None
    empty = {"id": 7, "status": {"type": "finished"}}
    assert fetch_shotmap(client, cache, empty) is None
    assert fetch_shotmap(client, cache, empty) is None
    assert client.event_shotmap.call_count == 2  # {} is a fact, not re-asked
    live = {"id": 8, "status": {"type": "inprogress"}}
    fetch_shotmap(client, cache, live)
    fetch_shotmap(client, cache, live)
    assert client.event_shotmap.call_count == 4  # never saved, asked again


def _history_event(eid: int) -> dict[str, Any]:
    return {"id": eid, "startTimestamp": 1_790_000_000 + eid,
            "status": {"type": "finished"},
            "homeTeam": {"id": 1, "name": "Viking"},
            "awayTeam": {"id": 2, "name": "Bayern"},
            "homeScore": {"current": 1}, "awayScore": {"current": 4}}


def test_samples_asks_the_shotmap_only_when_a_shot_detail_market_is_wanted(
        tmp_path: Path) -> None:
    from bet.sofa.db import migrate
    from bet.sofa.samples import process_historical_event

    db = str(tmp_path / "sofa.db")
    migrate(db)
    cache = SofaCache(SofaConfig(db_path=db))
    client = MagicMock()
    client.event_statistics.return_value = None
    client.event_incidents.return_value = {"incidents": []}
    client.event_lineups.return_value = _lineups(_olise())
    client.event_shotmap.return_value = SHOTMAP
    off = process_historical_event(client, cache, _history_event(1), 2, "football",
                                   set(), MagicMock(), True)
    assert client.event_shotmap.call_count == 0
    assert set(off["squad"]["michael olise"]) == {
        "minutesPlayed", "totalShots", "_started"}
    on = process_historical_event(client, cache, _history_event(2), 2, "football",
                                  set(), MagicMock(), True, True)
    assert client.event_shotmap.call_count == 1
    olise = on["squad"]["michael olise"]
    assert extract_player_metric("player_sot_outside_box_for", olise) == 1.0


def test_a_shotmap_provider_error_costs_the_counts_only(tmp_path: Path) -> None:
    from bet.sofa.db import migrate
    from bet.sofa.errors import ProviderError
    from bet.sofa.samples import process_historical_event

    db = str(tmp_path / "sofa.db")
    migrate(db)
    cache = SofaCache(SofaConfig(db_path=db))
    client = MagicMock()
    client.event_statistics.return_value = None
    client.event_incidents.return_value = {"incidents": []}
    client.event_lineups.return_value = _lineups(_olise())
    client.event_shotmap.side_effect = ProviderError("503")
    res = process_historical_event(client, cache, _history_event(3), 2, "football",
                                   set(), MagicMock(), True, True)
    olise = res["squad"]["michael olise"]
    assert extract_player_metric("player_shots_for", olise) == 3.0
    assert extract_player_metric("player_sot_outside_box_for", olise) == (
        GapReason.STAT_KEY_ABSENT)


def _side_results(positions: list[str]) -> dict[str, list[dict[str, Any]]]:
    out = []
    for i, pos in enumerate(positions):
        entry = _olise()
        entry["position"] = pos
        out.append({
            "event_id": 100 + i,
            "match_date_utc": datetime(2026, 9, 1, tzinfo=UTC) + timedelta(days=i),
            "opponent": "X", "competition_id": 1, "season_id": 1, "venue": "away",
            "squad": squad_statistics(_lineups(entry), is_home=False,
                                      shotmap=SHOTMAP),
        })
    return {"side_a": out, "side_b": []}


def test_a_shot_detail_sample_carries_the_newest_position_others_do_not() -> None:
    gaps: list[Any] = []
    samples = build_player_samples(
        {"player_sot_outside_box_for": {"Olise, Michael"},
         "player_shots_for": {"Olise, Michael"}},
        _side_results(["F", "F", "M"]), gaps, starts_only=True)
    sot = samples["player_sot_outside_box_for|Olise, Michael"]
    assert sot.position == "M"  # the newest match's
    assert [o.value for o in sot.observations] == [1.0, 1.0, 1.0]
    shots = samples["player_shots_for|Olise, Michael"]
    assert shots.position is None
    assert "position" not in shots.model_dump(mode="json")
    assert sot.model_dump(mode="json")["position"] == "M"


# --- SHEET --------------------------------------------------------------------


def _player_samples(values: list[float], metric: str = "player_sot_outside_box_for",
                    pos: str | None = "F") -> FixtureSamples:
    obs = [Observation(sofascore_event_id=1000 + i,
                       match_date_utc=FROZEN - timedelta(days=i + 1),
                       value=float(v), opponent=f"O{i}", venue="home",
                       competition_id=1, season_id=1, minutes=90.0)
           for i, v in enumerate(values)]  # newest first
    sample = PlayerSample(metric=metric, player="Olise, Michael",
                          matched_name="michael olise", side="side_b",
                          squad_matches=len(values), observations=obs,
                          appearances="starts", position=pos)
    return FixtureSamples(sofascore_event_id=1, readiness="READY", gaps=[],
                          metrics={}, players={f"{metric}|Olise, Michael": sample})


def _rung(metric: str = "player_sot_outside_box_for", line: float = 0.5,
          over: float = 3.2) -> PricedRung:
    return PricedRung(market=metric, subject="Olise, Michael", line=line,
                      over_odds=over, under_odds=None, fetched_at_utc=PRE_KICKOFF)


def _fixture_model() -> Any:
    from tests.sofa.test_player_markets import _fixture

    return _fixture()


def _sheet(on: bool, fit: dict[str, Any] | None,
           samples: FixtureSamples | None = None) -> tuple[list[Any], list[Any]]:
    offer = FixtureOffer(sofascore_event_id=1, status="PRICED",
                         unmapped_markets=[], rungs=[_rung()])
    return process_fixture(
        _fixture_model(), samples or _player_samples([1, 0, 2, 0, 1, 0, 1]),
        offer, baselines={}, reliability={}, engine_constants={}, vetoes=[],
        config=SofaConfig(), stats_only=True, shot_detail_on=on,
        shot_detail_fit=fit)


def test_sheet_prices_a_shot_detail_row_with_the_fitted_estimator() -> None:
    rows, skipped = _sheet(True, FIT)
    assert not skipped
    by_dir = {r.direction: sheet_row_json(r) for r in rows}
    want = sd.forecast([1, 0, 1, 0, 2, 0, 1], "F", "player_sot_outside_box_for",
                       0.5, FIT)
    assert want is not None
    over = by_dir["OVER"]
    assert over["p_central"] == round(want, 4)
    assert by_dir["UNDER"]["p_central"] == round(1 - want, 4)
    assert over["shot_detail_rule"] == epochs.SHOT_DETAIL_MARKETS
    assert over["sample_size"] == 7 and over["bar_reason"] == "shot_detail"
    assert over["p_bar"] == over["p_central"] and over["verdict"] != "VALUE"
    assert over["offered_odds"] == 3.2 and over["market_p"] is None
    assert over["epoch"] == "stats_only"
    assert any(n.startswith("SHOT_DETAIL:") for n in over["notes"])
    assert any(n.startswith("PLAYER_STARTS_ONLY") for n in over["notes"])


def test_the_estimator_reads_the_starts_newest_last() -> None:
    # the window is the newest ten: an old run of 5s outside it is not read
    newest_first = [0.0] * 10 + [5.0] * 5
    rows, _ = _sheet(True, FIT, _player_samples(newest_first))
    over = next(r for r in rows if r.direction == "OVER")
    assert over.p_central == round(
        sd.forecast(newest_first[::-1], "F", "player_sot_outside_box_for", 0.5, FIT)
        or 0.0, 4)
    assert over.centre == round((0.0 * 10 + 5 * 0.5) / 15, 4)


def test_no_installed_fit_no_row() -> None:
    rows, skipped = _sheet(True, None)
    assert rows == []
    assert [(s[1], s[2].split(":")[0]) for s in skipped] == [
        (GapReason.NO_SHOT_DETAIL_FIT, "NO_SHOT_DETAIL_FIT")]
    partial = {"metrics": {"player_headed_shots_for": FIT["metrics"][
        "player_headed_shots_for"]}}
    rows, skipped = _sheet(True, partial)
    assert rows == [] and skipped[0][1] == GapReason.NO_SHOT_DETAIL_FIT


def test_too_few_starts_is_a_thin_sample() -> None:
    rows, skipped = _sheet(True, FIT, _player_samples([1, 0, 1, 0]))
    assert rows == [] and skipped[0][1] == GapReason.THIN_SAMPLE


def test_switch_off_sheet_writes_no_shot_detail_row() -> None:
    rows, skipped = _sheet(False, FIT)
    assert rows == [] and skipped[0][1] == GapReason.NO_SHOT_DETAIL_FIT


def test_no_sample_no_row() -> None:
    empty = FixtureSamples(sofascore_event_id=1, readiness="READY", gaps=[],
                           metrics={}, players={})
    out, skipped = shot_detail_rows(_fixture_model(), _rung(), empty, FIT, {}, True)
    assert out == [] and skipped[0][1] == GapReason.NO_ENTITY_FOUND


def test_load_shot_detail_reads_the_installed_file_or_nothing(tmp_path: Path) -> None:
    assert load_shot_detail(tmp_path) is None
    (tmp_path / sd.FIT_FILE).write_text(json.dumps(FIT))
    assert load_shot_detail(tmp_path) == FIT
    (tmp_path / sd.FIT_FILE).write_text(json.dumps({"window": 10}))
    assert load_shot_detail(tmp_path) is None


@pytest.mark.skipif(not STAGED_FIT.is_file(), reason="staged fit not on disk")
def test_the_staged_fit_is_readable_by_the_estimator() -> None:
    fitted = sd.load_fit(STAGED_FIT)
    assert fitted is not None and set(fitted["metrics"]) == set(sd.METRICS)
    p = sd.forecast([1, 0, 1, 0, 2, 0, 1], "F", "player_sot_outside_box_for",
                    0.5, fitted)
    assert p is not None and 0.0 < p < 1.0


def test_the_fit_file_enters_the_fingerprint_only_once_installed(
        tmp_path: Path) -> None:
    before = fingerprint(tmp_path)
    (tmp_path / sd.FIT_FILE).write_text(json.dumps(FIT))
    assert fingerprint(tmp_path) != before
    (tmp_path / sd.FIT_FILE).unlink()
    assert fingerprint(tmp_path) == before


# --- CONFIDENCE: no curve, no lines -> nothing prints today -------------------


def test_installed_curves_and_evidence_give_the_keys_nothing() -> None:
    cal = Calibration.load()
    evidence = LineEvidence.load(v2=True, bucket_deff=True)
    for metric in sd.METRICS:
        for p in (0.72, 0.85):
            assert cal.realised(metric, p, "football", "OVER") is None
        key = direction_key(metric, "OVER")
        assert evidence.read("football", key, 0.85, None, 1.35) is None
    # the one-sided single needs its own market's history curve
    assert not one_sided_single({
        "one_sided_market": True, "overround": None,
        "calibrated_on": "sb:football:player_sot_outside_box_for|OVER",
        "calibration_n": 1000})


def test_confidence_refuses_a_shot_detail_leg(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    from scripts.sofa import run_confidence
    from tests.sofa.test_locked_print import _fixture as base_fixture

    day = "2026-10-15"
    t0 = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
    ko = "2026-10-15T18:00:00Z"
    run = tmp_path / day
    run.mkdir()

    def z(t: datetime) -> str:
        return t.isoformat().replace("+00:00", "Z")

    metric = "player_sot_outside_box_for"
    samples = _player_samples([1, 0, 2, 1, 1, 0, 1, 2, 1, 1])
    fx = {**base_fixture(1), "kickoff_utc": ko, "superbet_kickoff_utc": ko}
    (run / "02_fixtures.json").write_text(json.dumps([fx]))
    (run / "03_samples.json").write_text(json.dumps([samples.model_dump(mode="json")]))
    row = {
        "sofascore_event_id": 1, "sport": "football", "market": metric,
        "subject": "Olise, Michael", "line": 0.5, "direction": "OVER",
        "sample_size": 10, "sample_mean": 1.0, "sample_sd": 0.6, "centre": 0.9,
        "p_central": 0.88, "market_p": None, "ladder_centre": None,
        "ladder_sigma": None, "p_bar": 0.88, "bar_reason": "shot_detail",
        "required_odds": 1.2, "offered_odds": 1.6, "edge": None, "surplus": 0.4,
        "verdict": "LEAN", "notes": ["SHOT_DETAIL: test"], "epoch": "stats_only",
        "forecast_p": None, "forecast_source": None,
        "shot_detail_rule": epochs.SHOT_DETAIL_MARKETS,
    }
    (run / "05_sheet.json").write_text(json.dumps([row]))
    (run / "vetoes.json").write_text("[]")
    (run / "04_offer.json").write_text(json.dumps([{
        "sofascore_event_id": 1, "status": "PRICED", "unmapped_markets": [],
        "price_collisions": [],
        "rungs": [{"market": metric, "subject": "Olise, Michael", "line": 0.5,
                   "over_odds": 1.6, "under_odds": None,
                   "fetched_at_utc": z(t0 - timedelta(minutes=1))}]}]))
    monkeypatch.setenv("SOFA_NOW", z(t0))
    monkeypatch.setattr(sys, "argv", [
        "run_confidence.py", "--date", day, "--runs-dir", str(tmp_path)])
    assert run_confidence.main() == 0
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary["metrics"]["refused"] == {"NO_LINE_EVIDENCE": 1}
    doc = json.loads((run / "08_confidence.json").read_text())
    assert doc["singles"] == [] and doc["legs"] == []


# --- SETTLE -------------------------------------------------------------------


def _settle_row(metric: str, line: float = 0.5) -> dict[str, Any]:
    return {"market": metric, "subject": "Olise, Michael", "line": line,
            "direction": "OVER"}


def _match_squads(entry: dict[str, Any],
                  shotmap: dict[str, Any] | None) -> dict[bool, Any]:
    lineups = _lineups(entry)
    return {True: squad_statistics(lineups, is_home=True, shotmap=shotmap),
            False: squad_statistics(lineups, is_home=False, shotmap=shotmap)}


def test_settle_grades_olise_as_superbet_did() -> None:
    squads = _match_squads(_olise(), SHOTMAP)
    assert run_settle._settle_player(
        _settle_row("player_sot_outside_box_for"), squads, False) == (1.0, "WIN")
    assert run_settle._settle_player(
        _settle_row("player_shots_outside_box_for", 2.5), squads, False) == (
        2.0, "LOSS")
    assert run_settle._settle_player(
        _settle_row("player_headed_shots_for"), squads, False) == (0.0, "LOSS")


def test_settle_a_starter_absent_from_the_shotmap_with_zero_shots_grades_zero() -> None:
    squads = _match_squads(_olise(total_shots=0, pid=1), SHOTMAP)
    assert run_settle._settle_player(
        _settle_row("player_sot_left_foot_for"), squads, False) == (0.0, "LOSS")


def test_settle_a_mismatch_or_no_shotmap_is_a_gap() -> None:
    for squads in (_match_squads(_olise(total_shots=5), SHOTMAP),
                   _match_squads(_olise(), {})):
        assert run_settle._settle_player(
            _settle_row("player_sot_outside_box_for"), squads, False) == (
            "player_sot_outside_box_for:STAT_KEY_ABSENT")


def test_settle_asks_the_shotmap_only_for_a_shot_detail_row() -> None:
    import ast

    src = (Path(__file__).parents[2] / "scripts" / "sofa" / "run_settle.py").read_text(
        encoding="utf-8")
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "fetch_shotmap"]
    assert len(calls) == 1
    assert "SHOT_DETAIL_METRICS for r in event_rows" in src
