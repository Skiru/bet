"""The basketball handicap PAPER test (operator's go 2026-10-31):
bet.sofa.paper_bb_handicap + scripts/sofa/paper_bb_handicap.py.

Offline. The E2E tests replay real SHADOW records of the 10-27 sport day
(files 10-27 and 10-28, trimmed) and real bet365 payloads (trimmed to the
two markets) through the script with a fake client, and assert the
selections and grades the 2026-10-31 backtest (scratchpad secondprice2,
rows.sport_rows + run.fire, basketball handicap t=0) produced for them.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import paper_bb_handicap as pb
from bet.sofa import timeutil
from bet.sofa.errors import ProviderError
from scripts.sofa import paper_bb_handicap as script

FIXTURES = Path(__file__).parent / "fixtures" / "paper_bb_handicap"
NOW = datetime(2026, 10, 31, 14, 0, tzinfo=UTC)

# The backtest's selections for the fixture's games (backtest_sel.json of
# the 2026-10-31 session): sofascore id -> (odds, won, fair p open).
BACKTEST_SELECTED = {
    17183619: (2.05, False, 0.5),
    16665322: (2.07, False, 0.5),
    16561659: (2.17, True, 0.5108317091649132),
    16665325: (2.05, True, 0.4881000064840126),
    17174411: (2.07, True, 0.5),  # file 10-28, kickoff 10-28 00:00Z
    16824766: (1.97, True, 0.5116044544982121),  # file 10-28, 03:00Z
}


class FakeClient:
    def __init__(self, fail: dict[int, Exception] | None = None) -> None:
        self.asked: list[int] = []
        self.fail = fail or {}

    def event_odds(self, id: int) -> Any | None:
        self.asked.append(id)
        if id in self.fail:
            raise self.fail[id]
        path = FIXTURES / "odds" / f"{id}.json"
        return json.loads(path.read_text()) if path.exists() else None


@pytest.fixture
def runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    shutil.copytree(FIXTURES / "shadow", tmp_path / "shadow")
    monkeypatch.setattr(timeutil, "now", lambda: NOW)
    return tmp_path


def _day(runs: Path, date: str) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(
        (runs / "paper" / "bb_handicap" / f"{date}.json").read_text()
    )
    return doc


def _spread(
    home: str, away: str, line: float = -2.5, live: bool = False
) -> dict[str, Any]:
    return {
        "marketName": "Point spread",
        "choiceGroup": None,
        "isLive": live,
        "choices": [
            {"name": f"({line:+.1f}) Home", "initialFractionalValue": home},
            {"name": f"({-line:+.1f}) Away", "initialFractionalValue": away},
        ],
    }


def _row(
    side: str, line: float, odds: float, outcome: str = "WIN", **kw: Any
) -> dict[str, Any]:
    return {
        "family": "handicap",
        "period": 0,
        "subject": "",
        "line": line,
        "side": side,
        "odds": odds,
        "outcome": outcome,
        "superbet_event_id": "1",
        **kw,
    }


def _record(rows: list[dict[str, Any]], h1: bool | None = True) -> dict[str, Any]:
    return {
        "state": "SETTLED",
        "sofascore_event_id": 9,
        "home_is_team1": h1,
        "team1": "A",
        "team2": "B",
        "match_name": "A·B",
        "kickoff_utc": "2026-11-02T18:00:00Z",
        "graded": rows,
    }


# --- units ---------------------------------------------------------------------


def test_fractional_odds_parse_like_the_backtest() -> None:
    assert pb.frac_to_decimal("5/6") == pytest.approx(1 + 5 / 6)
    assert pb.frac_to_decimal("1/1") == 2.0
    assert pb.frac_to_decimal(None) is None
    assert pb.frac_to_decimal("n/a") is None
    assert pb.frac_to_decimal("1/0") is None


def test_power_removal_sums_to_one_and_keeps_the_favourite() -> None:
    p = pb.power_fair([1.5, 2.9])
    assert sum(p) == pytest.approx(1.0, abs=1e-12)
    assert p[0] > 1 / 2.9 and p[0] < 1 / 1.5
    assert pb.power_fair([1 + 5 / 6, 1 + 5 / 6]) == pytest.approx([0.5, 0.5])


def test_fair_open_reads_the_opening_price_inside_the_overround_band() -> None:
    ch = [
        {"initialFractionalValue": "5/6", "fractionalValue": "1/2"},
        {"initialFractionalValue": "5/6", "fractionalValue": "6/4"},
    ]
    assert pb.fair_open(ch, 0) == pytest.approx(0.5)
    # overround 1.33 > 1.25: no fair p
    assert (
        pb.fair_open(
            [{"initialFractionalValue": "1/2"}, {"initialFractionalValue": "1/2"}], 0
        )
        is None
    )
    assert pb.fair_open([{"initialFractionalValue": "5/6"}, {}], 0) is None


def test_live_markets_are_dropped_and_an_empty_payload_is_no_odds() -> None:
    m = pb.b365_markets({"markets": [_spread("5/6", "5/6", live=True)]})
    assert m == {}
    assert pb.b365_markets(None) is None
    assert pb.b365_markets({"markets": []}) is None


def test_line_matching_follows_the_home_side() -> None:
    m = pb.b365_markets({"markets": [_spread("4/5", "10/11", line=-2.5)]})
    assert m is not None
    # Superbet team1 = home, team1 -2.5: home choice for T1, away for T2
    t1 = pb.match_spread(m, -2.5, "T1", True)
    t2 = pb.match_spread(m, -2.5, "T2", True)
    assert t1 is not None and t2 is not None
    assert t1["b365_choice"].endswith("Home") and t2["b365_choice"].endswith("Away")
    assert t1["p_open"] + t2["p_open"] == pytest.approx(1.0)
    # team1 is away: Superbet team1 +2.5 is bet365's home -2.5
    away = pb.match_spread(m, 2.5, "T1", False)
    assert away is not None and away["b365_choice"].endswith("Away")
    assert pb.match_spread(m, -3.5, "T1", True) is None


def test_the_rule_fires_strictly_above_one() -> None:
    assert pb.T == 0.0
    assert not pb.fires(2.0, 0.5)
    assert pb.fires(2.01, 0.5)
    assert not pb.fires(3.0, None)


def test_evaluate_reads_only_graded_full_game_handicap_rows() -> None:
    payload = {"markets": [_spread("5/6", "5/6", line=-2.5)]}
    rec = _record(
        [
            _row("T1", -2.5, 2.10, "WIN"),
            _row("T2", -2.5, 1.70, "LOSS"),
            _row("T1", -2.5, 2.50, "VOID"),
            {**_row("T1", -2.5, 2.50), "period": 1},
            _row("T1", -4.5, 2.60, "LOSS"),  # bet365 has no -4.5: no candidate
        ]
    )
    status, cands = pb.evaluate_event(rec, payload, "2026-11-02", 0)
    assert status == "SELECTED"
    assert [(c["side"], c["odds"], c["selected"]) for c in cands] == [
        ("T1", 2.10, True),
        ("T2", 1.70, False),
    ]
    sel = cands[0]
    assert sel["units"] == pytest.approx(1.10)
    assert sel["units_after_tax"] == pytest.approx(2.10 * 0.88 - 1)
    assert sel["edge"] == pytest.approx(0.05)
    assert pb.evaluate_event(rec, None, "2026-11-02", 0) == ("NO_B365_ODDS", [])
    assert (
        pb.evaluate_event(_record(rec["graded"], h1=None), payload, "d", 0)[0]
        == "ORIENTATION_UNKNOWN"
    )


def test_a_superbet_price_fetched_after_the_start_is_never_read() -> None:
    payload = {"markets": [_spread("5/6", "5/6", line=-2.5)]}
    rec = _record(
        [
            _row("T1", -2.5, 2.10, fetched_at_utc="2026-11-02T17:50:00Z"),
            _row("T2", -2.5, 2.20, fetched_at_utc="2026-11-02T18:00:00Z"),
        ]
    )
    _, cands = pb.evaluate_event(rec, payload, "2026-11-02", 0)
    assert [(c["side"], c["odds"]) for c in cands] == [("T1", 2.10)]


def _sel(ev: int, odds: float, outcome: str, line: float = -2.5) -> dict[str, Any]:
    return {
        "sofascore_event_id": ev,
        "t1_line": line,
        "side": "T1",
        "odds": odds,
        "outcome": outcome,
        "p_open": 0.5,
        "selected": True,
        "order": ["d", ev, 0],
    }


def test_summary_units_tax_and_match_bootstrap() -> None:
    s = pb.summarize([_sel(1, 2.2, "WIN"), _sel(2, 2.1, "LOSS"), _sel(3, 2.0, "WIN")])
    assert (s["n"], s["events"], s["won"]) == (3, 3, 2)
    assert s["units"] == pytest.approx(1.2 - 1 + 1.0)
    assert s["roi"] == pytest.approx(1.2 / 3)
    assert s["units_after_tax"] == pytest.approx(
        (2.2 * 0.88 - 1) - 1 + (2.0 * 0.88 - 1)
    )
    lo, hi = s["roi_after_tax_ci95"]
    assert lo <= s["roi_after_tax"] <= hi
    assert pb.summarize([]) == {"n": 0, "events": 0}
    pending = {**_sel(4, 2.0, "WIN"), "outcome": None}
    assert pb.summarize([pending])["n"] == 0


def test_ledger_keeps_forward_and_backtest_apart() -> None:
    days = [
        {"date": "2026-10-20", "candidates": [_sel(1, 2.2, "WIN")]},
        {"date": "2026-10-28", "candidates": [_sel(2, 2.2, "LOSS")]},
        {"date": "2026-10-31", "candidates": [_sel(5, 2.2, "LOSS")]},
        {
            "date": pb.START_DATE,
            "candidates": [_sel(3, 2.1, "LOSS"), _sel(1, 2.2, "WIN")],
            "pending": [{"superbet_event_id": "x"}],
        },
    ]
    led = pb.build_ledger(days)
    assert led["start_date"] == pb.START_DATE and led["target_n"] == 300
    assert led["forward"]["summary"]["n"] == 1  # event 1's line counted on 10-20 only
    assert led["duplicates_dropped"] == 1
    assert led["forward"]["pending_events"] == 1
    assert not led["forward"]["evaluable"]
    w = led["backtest"]["windows"]
    assert (w["dev"]["n"], w["holdout_posthoc"]["n"], w["registration_day"]["n"]) == (
        1,
        1,
        1,
    )
    text = pb.report_pl(led)
    assert (
        "ocena dopiero przy n >= 300; do tego czasu to nie jest przewaga"
        in text.lower()
    )


def _fwd_sel(i: int, outcome: str, odds: float = 2.0) -> dict[str, Any]:
    day = (date(2026, 11, 1) + timedelta(days=i // 10)).isoformat()
    return {
        **_sel(1000 + i, odds, outcome),
        "kickoff_utc": f"{day}T{10 + i % 10:02d}:00:00Z",
        "order": [day, i, 0],
    }


def _fwd_days(
    sels: list[dict[str, Any]], pending: dict[str, int] | None = None
) -> list[dict[str, Any]]:
    by_day: dict[str, list[dict[str, Any]]] = {}
    for s_ in sels:
        by_day.setdefault(s_["order"][0], []).append(s_)
    for d in pending or {}:
        by_day.setdefault(d, [])
    return [
        {"date": d, "candidates": c, "pending": [{}] * (pending or {}).get(d, 0)}
        for d, c in by_day.items()
    ]


def test_forward_before_target_is_progress_only() -> None:
    sels = [_fwd_sel(i, "WIN") for i in range(pb.TARGET_N - 1)]
    led = pb.build_ledger(_fwd_days(sels))
    fwd = led["forward"]
    assert not fwd["evaluable"] and fwd["evaluation"]["verdict"] is None
    assert fwd["summary"] == {"n": pb.TARGET_N - 1, "events": pb.TARGET_N - 1}
    text = pb.report_pl(led)
    assert f"Postęp: {pb.TARGET_N - 1} / {pb.TARGET_N}" in text
    assert "ROI przed" not in text and "ROI po" not in text.split("Backtest")[0]
    assert "Kryterium" not in text


def test_forward_verdict_is_frozen_at_the_first_target_selections() -> None:
    # the first 300 by kickoff: all lose -> FAIL; 200 later wins never rescue it
    first = [_fwd_sel(i, "LOSS") for i in range(pb.TARGET_N)]
    later = [_fwd_sel(pb.TARGET_N + i, "WIN", 3.0) for i in range(200)]
    led = pb.build_ledger(_fwd_days(first + later))
    ev = led["forward"]["evaluation"]
    assert led["forward"]["evaluable"] and ev["verdict"] == "FAIL"
    assert ev["summary"]["n"] == pb.TARGET_N and ev["summary"]["won"] == 0
    assert ev["after_evaluation"]["n"] == 200 and ev["after_evaluation"]["won"] == 200
    assert ev["cut"]["kickoff_utc"] == first[-1]["kickoff_utc"]
    text = pb.report_pl(led)
    assert "NIESPEŁNIONE" in text
    assert "Po ocenie (nie zmieniają werdyktu):" in text
    # the same 300 in another order of day files: the same verdict and cut
    led2 = pb.build_ledger(list(reversed(_fwd_days(first + later))))
    assert led2["forward"]["evaluation"]["cut"] == ev["cut"]
    assert led2["forward"]["evaluation"]["summary"] == ev["summary"]


def test_forward_selection_order_is_chronological_by_kickoff() -> None:
    # a later-kickoff loser listed first in its day file stays after the cut
    sels = [_fwd_sel(i, "WIN", 3.0) for i in range(pb.TARGET_N)]
    late = {
        **_fwd_sel(0, "LOSS"),
        "sofascore_event_id": 9,
        "kickoff_utc": "2026-12-31T23:00:00Z",
        "order": ["2026-11-01", -1, 0],
    }
    led = pb.build_ledger(_fwd_days([late, *sels]))
    ev = led["forward"]["evaluation"]
    assert ev["summary"]["won"] == pb.TARGET_N and ev["verdict"] == "PASS"
    assert ev["after_evaluation"]["n"] == 1 and ev["after_evaluation"]["won"] == 0


def test_forward_verdict_waits_for_pending_games_up_to_the_cut() -> None:
    sels = [_fwd_sel(i, "WIN", 3.0) for i in range(pb.TARGET_N)]
    cut_day = sels[-1]["order"][0]
    led = pb.build_ledger(_fwd_days(sels, pending={"2026-11-03": 1}))
    ev = led["forward"]["evaluation"]
    assert not ev["evaluable"] and ev["verdict"] is None
    assert ev["pending_before_cut"] == 1 and ev["cut"]["day"] == cut_day
    assert "werdykt po ich rozliczeniu" in pb.report_pl(led)
    # a pending game after the cut day does not hold the verdict back
    led = pb.build_ledger(_fwd_days(sels, pending={"2026-12-30": 1}))
    assert led["forward"]["evaluation"]["verdict"] == "PASS"


def test_forward_window_starts_after_the_registration_day() -> None:
    # check_test_registry: data_window.from > registered_on
    assert pb.START_DATE > pb.FROZEN_AT
    assert pb.section_of(pb.FROZEN_AT) == "backtest"
    reg = json.loads(
        (Path(__file__).parents[2] / "config" / "sofa_test_registry.json").read_text()
    )
    test = next(t for t in reg["tests"] if t["id"] == "T-PAPER-BB-HANDICAP-B365-OPEN")
    assert test["data_window"]["from"] == pb.START_DATE
    assert test["registered_on"] == pb.FROZEN_AT
    assert test["required_n"]["selections"] == pb.TARGET_N


# --- E2E: real days through the script ------------------------------------------


def test_e2e_real_day_reproduces_the_backtest(runs: Path) -> None:
    client = FakeClient()
    code = script.main(
        ["--date", "2026-10-27", "--runs-dir", str(runs)], client_factory=lambda: client
    )
    assert code == 1  # a game still pending (NOT_ON_SOFASCORE within 8 days)
    doc = _day(runs, "2026-10-27")
    got = {
        c["sofascore_event_id"]: (c["odds"], c["outcome"] == "WIN", c["p_open"])
        for c in doc["candidates"]
        if c["selected"]
    }
    assert got.keys() == BACKTEST_SELECTED.keys()
    for ev, (odds, won, p) in BACKTEST_SELECTED.items():
        assert got[ev][0] == odds and got[ev][1] is won
        assert got[ev][2] == pytest.approx(p, abs=1e-12)
    # 10-27 00:00Z belongs to 10-26's window; 10-28 12:00Z+ to 10-28's
    seen = {c["sofascore_event_id"] for c in doc["candidates"]}
    assert 16824758 not in seen and 17210662 not in seen
    assert 16824758 not in client.asked and 17210662 not in client.asked
    assert sorted(client.asked) == [
        16561659,
        16665322,
        16665325,
        16824766,
        17174411,
        17183618,
        17183619,
        17184329,
    ]
    assert [p["superbet_event_id"] for p in doc["pending"]] == ["15435424"]
    assert doc["pending"][0]["superbet_handicap_last_snapshot"]
    assert doc["section"] == "backtest" and doc["selections"] == 6 and doc["won"] == 4
    led = json.loads((runs / "paper" / "bb_handicap" / "ledger.json").read_text())
    assert led["backtest"]["windows"]["holdout_posthoc"]["n"] == 6
    assert led["forward"]["summary"]["n"] == 0


def test_e2e_window_edges_move_games_to_their_sport_day(runs: Path) -> None:
    client = FakeClient()
    script.main(
        ["--date", "2026-10-26", "--runs-dir", str(runs)], client_factory=lambda: client
    )
    assert client.asked == [16824758]
    client2 = FakeClient()
    script.main(
        ["--date", "2026-10-28", "--runs-dir", str(runs)],
        client_factory=lambda: client2,
    )
    assert client2.asked == [17210662]


def test_e2e_rerun_is_idempotent_and_asks_nothing_cached(runs: Path) -> None:
    client = FakeClient()
    args = ["--date", "2026-10-27", "--runs-dir", str(runs)]
    script.main(args, client_factory=lambda: client)
    out = runs / "paper" / "bb_handicap"
    first = {p.name: p.read_bytes() for p in out.glob("*.json")}
    again = FakeClient()
    script.main(args, client_factory=lambda: again)
    assert again.asked == []
    assert {p.name: p.read_bytes() for p in out.glob("*.json")} == first


def test_e2e_writes_nothing_the_coupon_reads(runs: Path) -> None:
    before = {p for p in runs.rglob("*") if p.is_file()}
    script.main(
        ["--date", "2026-10-27", "--runs-dir", str(runs)], client_factory=FakeClient
    )
    new = {p for p in runs.rglob("*") if p.is_file()} - before
    assert new
    assert all(p.relative_to(runs).parts[:2] == ("paper", "bb_handicap") for p in new)
    assert not (runs / "2026-10-27").exists()


def test_e2e_no_fetch_and_refusal_are_fetch_gaps(runs: Path, capsys: Any) -> None:
    code = script.main(
        ["--date", "2026-10-27", "--runs-dir", str(runs), "--no-fetch"],
        client_factory=FakeClient,
    )
    assert code == 1
    doc = _day(runs, "2026-10-27")
    assert len(doc["fetch_gaps"]) == 8 and doc["selections"] == 0
    # a 403 stops the run's fetching: every later game is a gap, nothing cached
    shutil.rmtree(runs / "paper")
    client = FakeClient(fail={17183618: ProviderError("HTTP 403")})
    script.main(
        ["--date", "2026-10-27", "--runs-dir", str(runs)], client_factory=lambda: client
    )
    assert client.asked == [17183618]
    assert len(_day(runs, "2026-10-27")["fetch_gaps"]) == 8


def test_e2e_no_shadow_file_is_failed_and_report_prints_polish(
    runs: Path, capsys: Any
) -> None:
    assert (
        script.main(
            ["--date", "2026-11-05", "--runs-dir", str(runs)], client_factory=FakeClient
        )
        == 2
    )
    assert script.main(["--report", "--runs-dir", str(runs)]) == 0
    assert "do tego czasu to nie jest przewaga" in capsys.readouterr().out


def test_e2e_pending_reruns_partial_days_only(runs: Path) -> None:
    script.main(
        ["--date", "2026-10-26", "--runs-dir", str(runs)], client_factory=FakeClient
    )
    script.main(
        ["--date", "2026-10-27", "--runs-dir", str(runs)], client_factory=FakeClient
    )
    out = runs / "paper" / "bb_handicap"
    assert script.pending_days(out, "2026-10-28") == ["2026-10-27"]
    client = FakeClient()
    code = script.main(
        ["--date", "2026-10-28", "--pending", "--runs-dir", str(runs)],
        client_factory=lambda: client,
    )
    assert code == 1  # 10-27 still pending
    assert client.asked == [17210662]  # 10-27's payloads cached, 10-28's asked


# --- the forward data: bet365 captured before tip-off ----------------------------

FWD = "2026-11-02"  # a forward day (>= pb.START_DATE, >= pb.PRESTART_FROM)


def _payload(line: float, home: str = "5/6", away: str = "5/6") -> dict[str, Any]:
    return {
        "markets": [
            {
                "marketName": "Point spread",
                "choiceGroup": None,
                "isLive": False,
                "choices": [
                    {
                        "name": f"({line:+.1f}) Dolomiti Energia Trento",
                        "initialFractionalValue": home,
                    },
                    {
                        "name": f"({-line:+.1f}) KK Buducnost VOLI",
                        "initialFractionalValue": away,
                    },
                ],
            },
            {
                "marketName": "1st half",
                "choiceGroup": None,
                "isLive": False,
                "choices": [],
            },
        ]
    }


def _forward_day(runs: Path) -> dict[str, Any]:
    """The real Trento - Buducnost record (10-27) moved to a forward day."""
    src = json.loads(
        (FIXTURES / "shadow/basketball/2026-10-27/settled.json").read_text()
    )
    rec = src["events"]["14719965"]
    rec["kickoff_utc"] = rec["sofascore_start_utc"] = f"{FWD}T19:00:00Z"
    d = runs / "shadow" / "basketball" / FWD
    d.mkdir(parents=True)
    (d / "settled.json").write_text(
        json.dumps({"date": FWD, "sport": "basketball", "events": {"14719965": rec}})
    )
    return rec


def _capture(runs: Path, ev: int, *caps: tuple[str, Any]) -> None:
    d = runs / "paper" / "bb_handicap" / "prestart" / FWD
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{ev}.json").write_text(
        json.dumps(
            {
                "sofascore_event_id": ev,
                "captures": [{"fetched_at_utc": at, "payload": p} for at, p in caps],
            }
        )
    )


def test_prestart_payload_is_the_newest_capture_before_the_start() -> None:
    caps = [
        {"fetched_at_utc": "2026-11-02T16:30:00.5Z", "payload": _payload(1.5)},
        {"fetched_at_utc": "2026-11-02T18:45:00.1Z", "payload": _payload(2.5)},
        {"fetched_at_utc": "2026-11-02T19:00:00.1Z", "payload": _payload(3.5)},
        {"fetched_at_utc": "2026-11-02T21:00:00Z", "payload": _payload(4.5)},
    ]
    got = pb.prestart_payload(caps, "2026-11-02T19:00:00Z")
    assert got is not None and got["payload"] == _payload(2.5)
    assert pb.prestart_payload(caps[2:], "2026-11-02T19:00:00Z") is None
    assert (
        pb.start_clock(
            {
                "kickoff_utc": "2026-11-02T19:00:00Z",
                "sofascore_start_utc": "2026-11-02T18:30:00Z",
            }
        )
        == "2026-11-02T18:30:00Z"
    )


def test_prestart_payload_skips_empty_captures_and_prefers_the_spread() -> None:
    start = "2026-11-02T19:00:00Z"
    no_spread = {
        "markets": [
            {"marketName": "Full time", "choiceGroup": None, "isLive": False,
             "choices": [{"name": "1"}, {"name": "2"}]}
        ]
    }
    caps = [
        {"fetched_at_utc": "2026-11-02T16:00:00Z", "payload": _payload(1.5)},
        {"fetched_at_utc": "2026-11-02T17:00:00Z", "payload": _payload(2.5)},
        {"fetched_at_utc": "2026-11-02T18:00:00Z", "payload": no_spread},
        {"fetched_at_utc": "2026-11-02T18:30:00Z", "payload": {"markets": []}},
        {"fetched_at_utc": "2026-11-02T18:45:00Z", "payload": None},  # a 404
        {"fetched_at_utc": "2026-11-02T19:10:00Z", "payload": _payload(9.5)},
    ]
    got = pb.prestart_payload(caps, start)
    # the newest pre-start capture holding "Point spread", not the newer empties
    assert got is not None and got["fetched_at_utc"] == "2026-11-02T17:00:00Z"
    # no spread anywhere before the start: the newest non-empty capture
    got = pb.prestart_payload(caps[2:], start)
    assert got is not None and got["payload"] == no_spread
    # only empty captures before the start (and a valid one after it): none
    assert pb.prestart_payload(caps[3:], start) is None
    # a spread only in a live market does not count as the spread
    live = {"markets": [{**_payload(1.5)["markets"][0], "isLive": True}]}
    caps2 = [
        {"fetched_at_utc": "2026-11-02T16:00:00Z", "payload": no_spread},
        {"fetched_at_utc": "2026-11-02T17:00:00Z", "payload": live},
    ]
    got = pb.prestart_payload(caps2, start)
    assert got is not None and got["payload"] == no_spread


def test_e2e_forward_empty_capture_before_tipoff_keeps_the_earlier_line(
    runs: Path,
) -> None:
    _forward_day(runs)
    _capture(
        runs,
        16561659,
        (f"{FWD}T16:15:00.000001Z", _payload(1.5)),
        (f"{FWD}T18:30:00.000001Z", {"markets": []}),  # bet365 pulled markets
        (f"{FWD}T18:45:00.000001Z", None),  # a 404
    )
    script.main(["--date", FWD, "--runs-dir", str(runs)], client_factory=FakeClient)
    doc = _day(runs, FWD)
    assert doc["counts"].get("no_b365_prestart", 0) == 0
    sel = [c for c in doc["candidates"] if c["selected"]]
    assert [(c["side"], c["t1_line"]) for c in sel] == [("T1", 1.5)]
    assert sel[0]["b365_fetched_at_utc"] == f"{FWD}T16:15:00.000001Z"


def test_e2e_forward_uses_the_prestart_line_not_the_post_match_one(runs: Path) -> None:
    _forward_day(runs)
    # before tip-off bet365 stood at +1.5; after the game its payload says +2.5
    _capture(
        runs,
        16561659,
        (f"{FWD}T16:15:00.000001Z", _payload(1.5)),
        (f"{FWD}T19:05:00.000001Z", _payload(2.5, "4/5", "20/23")),
    )
    client = FakeClient()
    code = script.main(
        ["--date", FWD, "--runs-dir", str(runs)], client_factory=lambda: client
    )
    assert code == 0 and client.asked == []  # forward never asks after the game
    doc = _day(runs, FWD)
    assert doc["b365_source"] == "prestart" and doc["section"] == "forward"
    sel = [c for c in doc["candidates"] if c["selected"]]
    assert [(c["side"], c["t1_line"], c["odds"], c["outcome"]) for c in sel] == [
        ("T1", 1.5, 2.35, "WIN")
    ]
    assert sel[0]["b365_home_line"] == 1.5
    assert sel[0]["b365_fetched_at_utc"] == f"{FWD}T16:15:00.000001Z"
    assert all(c["t1_line"] == 1.5 for c in doc["candidates"])
    led = json.loads((runs / "paper" / "bb_handicap" / "ledger.json").read_text())
    assert led["forward"]["summary"]["n"] == 1
    assert led["forward"]["b365_source"] == "prestart"


def test_e2e_forward_game_without_a_prestart_capture_is_excluded_and_counted(
    runs: Path, capsys: Any
) -> None:
    _forward_day(runs)
    # only a capture taken after tip-off: excluded, never read
    _capture(runs, 16561659, (f"{FWD}T19:00:00.5Z", _payload(1.5)))
    script.main(
        ["--date", FWD, "--runs-dir", str(runs), "--report"], client_factory=FakeClient
    )
    doc = _day(runs, FWD)
    assert doc["counts"]["no_b365_prestart"] == 1
    assert doc["no_b365_prestart"] == [16561659] and doc["candidates"] == []
    led = json.loads((runs / "paper" / "bb_handicap" / "ledger.json").read_text())
    assert led["forward"]["no_b365_prestart"] == 1
    assert "brak bet365 przed startem: 1" in capsys.readouterr().out


def _fixtures_file(runs: Path, date: str, games: list[tuple[int, str]]) -> None:
    d = runs / date
    d.mkdir(parents=True, exist_ok=True)
    (d / "sport_fixtures.json").write_text(
        json.dumps(
            {
                "fixtures": [
                    {
                        "sport": "basketball",
                        "status": "IDENTIFIED",
                        "superbet_event_id": str(ev),
                        "sofascore_event_id": ev,
                        "kickoff_utc": start,
                        "sofascore_start_utc": start,
                        "match_name": f"g{ev}",
                    }
                    for ev, start in games
                ]
            }
        )
    )


def test_capture_asks_only_games_not_started_within_the_horizon(runs: Path) -> None:
    now = datetime(2026, 11, 2, 16, 0, tzinfo=UTC)
    _fixtures_file(
        runs,
        FWD,
        [
            (1, f"{FWD}T15:30:00Z"),  # started: never asked
            (2, f"{FWD}T18:30:00Z"),  # within 3 h
            (3, f"{FWD}T19:30:00Z"),  # beyond 3 h: a later pass
            (4, f"{FWD}T02:00:00Z"),  # the day before's window
        ],
    )
    # a late game of FWD's window listed in FWD+1's file
    _fixtures_file(runs, "2026-11-03", [(5, "2026-11-03T01:00:00Z")])
    client = FakeClient()
    counts = script.capture_pass(str(runs), FWD, lambda: client, now, lambda: now)
    assert client.asked == [2] and counts["no_odds"] == 1
    later = datetime(2026, 11, 2, 22, 30, tzinfo=UTC)
    client2 = FakeClient()
    script.capture_pass(str(runs), FWD, lambda: client2, later, lambda: later)
    assert client2.asked == [5]
    # a second pass within 15 min does not ask again
    client3 = FakeClient()
    assert (
        script.capture_pass(
            str(runs), FWD, lambda: client3, later + timedelta(minutes=5)
        )["recent"]
        == 1
    )
    assert client3.asked == []
    files = sorted(
        p.name for p in (runs / "paper/bb_handicap/prestart" / FWD).iterdir()
    )
    assert files == ["2.json", "5.json"]


def test_capture_keeps_every_capture_trimmed_and_stamped(
    runs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 11, 2, 18, 0, tzinfo=UTC)
    _fixtures_file(runs, FWD, [(16561659, f"{FWD}T19:00:00Z")])

    class Client:
        def event_odds(self, id: int) -> Any:
            return _payload(1.5)

    script.capture_pass(str(runs), FWD, Client, now, stamp=lambda: now)
    script.capture_pass(
        str(runs),
        FWD,
        Client,
        now + timedelta(minutes=15),
        stamp=lambda: now + timedelta(minutes=15, seconds=2),
    )
    doc = json.loads(
        (runs / "paper/bb_handicap/prestart" / FWD / "16561659.json").read_text()
    )
    assert [c["fetched_at_utc"] for c in doc["captures"]] == [
        "2026-11-02T18:00:00Z",
        "2026-11-02T18:15:02Z",
    ]
    assert [m["marketName"] for m in doc["captures"][0]["payload"]["markets"]] == [
        "Point spread"
    ]  # "1st half" trimmed away
    assert doc["start_utc"] == f"{FWD}T19:00:00Z"


def test_capture_loop_runs_until_the_window_ends(runs: Path) -> None:
    times = iter(
        [
            datetime(2026, 11, 3, 4, 50, tzinfo=UTC),
            datetime(2026, 11, 3, 4, 51, tzinfo=UTC),
            datetime(2026, 11, 3, 5, 0, tzinfo=UTC),
        ]
    )
    slept: list[float] = []
    assert (
        script.capture_loop(
            str(runs), FWD, FakeClient, clock=lambda: next(times), sleep=slept.append
        )
        == 0
    )
    assert slept == [9 * 60.0]  # never past end(D) = D+1 05:00Z


def test_ensure_capture_loop_spawns_once_and_never_raises() -> None:
    now = lambda: datetime(2026, 11, 2, 12, 0, tzinfo=UTC)  # noqa: E731
    spawned: list[str] = []
    line = script.ensure_capture_loop(
        FWD, spawn=lambda d: spawned.append(d) or 7, holder=lambda r, d: None, clock=now
    )
    assert spawned == [FWD] and "started pid 7" in line
    assert "already running (pid 9)" in script.ensure_capture_loop(
        FWD, spawn=lambda d: 1, holder=lambda r, d: 9, clock=now
    )
    assert "day over" in script.ensure_capture_loop(
        "2026-11-01", spawn=lambda d: 1, holder=lambda r, d: None, clock=now
    )
    assert "not started" in script.ensure_capture_loop("2026-10-20")
    # the conftest refuses a real spawn: reported, not raised
    assert "NOT started" in script.ensure_capture_loop(
        FWD, holder=lambda r, d: None, clock=now
    )


def test_day_status_warns_when_the_capture_loop_is_missing(runs: Path) -> None:
    from scripts.sofa import day_status

    now = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    snaps = runs / "shadow" / "basketball" / FWD
    snaps.mkdir(parents=True)
    (snaps / "snapshots.jsonl").write_text("")
    assert day_status.paper_capture_check(runs, FWD, now).status == day_status.WARN
    over = datetime(2026, 11, 3, 6, 0, tzinfo=UTC)
    assert day_status.paper_capture_check(runs, FWD, over).status == day_status.OK
    assert (
        day_status.paper_capture_check(runs, "2026-10-20", now).status == day_status.OK
    )


def test_day_status_capture_check_uses_the_injected_process_lookup(runs: Path) -> None:
    """Review 2026-10-31: paper_capture_check ignored the `command_of` seam
    and looked the pid up for real. A live pid (our parent) is the loop only
    when the stub's command line says so - through loop_checks too."""
    import os

    from scripts.sofa import day_status

    now = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    snaps = runs / "shadow" / "basketball" / FWD
    snaps.mkdir(parents=True)
    (snaps / "snapshots.jsonl").write_text("")
    pre = script.prestart_dir(str(runs), FWD)
    pre.mkdir(parents=True, exist_ok=True)
    (pre / script.CAPTURE_PID).write_text(str(os.getppid()))
    asked: list[int] = []

    def loop_cmd(pid: int) -> str:
        asked.append(pid)
        return f"python scripts/sofa/paper_bb_handicap.py --capture --date {FWD} --loop"

    got = day_status.paper_capture_check(runs, FWD, now, command_of=loop_cmd)
    assert got.status == day_status.OK and got.detail == f"pid {os.getppid()}"
    assert asked == [os.getppid()]
    other = day_status.paper_capture_check(runs, FWD, now, command_of=lambda pid: "vim")
    assert other.status == day_status.WARN
    checks = {c.name: c for c in day_status.loop_checks(runs, FWD, now, loop_cmd)}
    assert checks["loop:paper_capture"].status == day_status.OK


def test_shadow_daily_starts_the_paper_capture_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.sofa import shadow_daily

    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(shadow_daily, "REPO", Path("/"))
    events: list[str] = []
    monkeypatch.setattr(
        shadow_daily, "loop", lambda *a, **k: events.append("loop") or 0
    )
    monkeypatch.setattr("sys.argv", ["shadow_daily", "--date", FWD])
    assert (
        shadow_daily.main(
            spawn=lambda d: 1,
            closing=lambda d: "c",
            paper=lambda d: events.append(f"paper:{d}") or "p",
        )
        == 0
    )
    assert events == [f"paper:{FWD}", "loop"]
