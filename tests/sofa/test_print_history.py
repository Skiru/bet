"""F0 of the production-grade plan (2026-10-05): nothing is lost in silence.

F0.1 - the print record is append-only (printed/<render>.json) and the lock
       reads every leg's FIRST print across the whole history: on 10-05
       twelve tennis legs left 12_printed.json when a later render overwrote
       it, and no rebuild could see them again.
F0.3 - a tennis match's real first point from /event's `time` block, not
       the order of play's startTimestamp (10-05: Grenier 09:40:52Z, Tarvet
       09:14:04Z).
F0.4 - FIXTURE_CHECK asks every match the coming build could print a leg
       on, so a halted match never reaches its first print.
F0.5 - an UNVERIFIED status says why (404 != no bridge), on the PDF too.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import coupon_sports as cs
from bet.sofa import fixture_status as fs
from bet.sofa.errors import CircuitOpenError, ProviderError, TransportError
from bet.sofa.locked_print import (
    PRINTED_HISTORY_DIR,
    PRINTED_MANIFEST,
    carry_over,
    first_prints,
    leg_started_by,
    print_history,
    record_print,
    started_by_evidence,
)
from scripts.sofa.run_fixture_check import candidate_event_ids, check, targets_for
from tests.sofa.test_stats_only_confidence import (
    DAY,
    _conf,
    _day,
    _row,
    _under,
)

T0 = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
# Fixture 2 starts at 10:00Z, fixture 1 in the evening.
KO = {1: "2026-10-07T18:00:00Z", 2: "2026-10-07T10:00:00Z"}


def _z(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def _confidence(runs: Path, monkeypatch: pytest.MonkeyPatch, at: datetime
                ) -> dict[str, Any]:
    """One CONFIDENCE build at `at` (the offer re-priced a minute before)."""
    from scripts.sofa import run_confidence

    offer = runs / DAY / "04_offer.json"
    doc = json.loads(offer.read_text())
    for o in doc:
        for r in o["rungs"]:
            r["fetched_at_utc"] = _z(at - timedelta(minutes=1))
    offer.write_text(json.dumps(doc))
    monkeypatch.setenv("SOFA_NOW", _z(at))
    monkeypatch.setattr(sys, "argv", [
        "run_confidence.py", "--date", DAY, "--runs-dir", str(runs)])
    assert run_confidence.main() == 0
    out: dict[str, Any] = json.loads((runs / DAY / "08_confidence.json").read_text())
    return out


def _render(run: Path, doc: dict[str, Any], at: datetime,
            drop: frozenset[int] | set[int] = frozenset()) -> Path:
    """What build_coupon_pdf records for one render, with the singles of the
    fixtures in `drop` left out (the render that lost them on 10-05)."""
    printed = {**doc, "singles": [s for s in doc["singles"]
                                  if s["sofascore_event_id"] not in drop],
               "pdf": f"KUPON_{DAY}.pdf", "pdf_rendered_at_utc": _z(at)}
    return record_print(run, printed)


@pytest.fixture()
def two_legs(tmp_path: Path) -> Path:
    p = 0.75
    odds = round(0.95 / _conf(p), 2)
    return _day(tmp_path, [_row(1, p, odds, 0.70), _row(2, p, odds, 0.70)],
                KO, {1: (odds, _under(odds)), 2: (odds, _under(odds))})


# ---------------------------------------------------------------------------
# F0.1 - append-only print record, the lock reads the first print
# ---------------------------------------------------------------------------


def test_every_render_is_kept_and_the_old_record_is_seeded_first(tmp_path):
    run = tmp_path / DAY
    run.mkdir()
    # a day printed before F0.1: 12_printed.json only (10-05, 10:58:53Z)
    old = {"profile": "standard", "created_at_utc": "2026-10-07T10:58:52Z",
           "pdf_rendered_at_utc": "2026-10-07T10:58:53.303787Z", "singles": [
               {"sofascore_event_id": 5}]}
    (run / PRINTED_MANIFEST).write_text(json.dumps(old))
    new = {**old, "pdf_rendered_at_utc": "2026-10-07T11:30:00Z", "singles": []}
    path = record_print(run, new)
    files = sorted(p.name for p in (run / PRINTED_HISTORY_DIR).iterdir())
    assert files == ["20261007T105853.303787Z.json", "20261007T113000.000000Z.json"]
    assert path.name == files[1]
    seeded = json.loads((run / PRINTED_HISTORY_DIR / files[0]).read_text())
    assert seeded == old
    # 12_printed.json is the latest render; the history keeps both
    assert json.loads((run / PRINTED_MANIFEST).read_text()) == new
    assert [d["pdf_rendered_at_utc"] for d in print_history(run)] == [
        old["pdf_rendered_at_utc"], new["pdf_rendered_at_utc"]]
    # the same render twice is one file; another render never overwrites
    record_print(run, new)
    other = {**new, "singles": [{"sofascore_event_id": 6}]}
    record_print(run, other)
    names = {p.name for p in (run / PRINTED_HISTORY_DIR).iterdir()}
    assert names == {*files, "20261007T113000.000000Z-1.json"}
    assert json.loads((run / PRINTED_HISTORY_DIR / files[1]).read_text()) == new
    # both renders of the same instant are in the history, in write order
    assert [d["singles"] for d in print_history(run)] == [
        old["singles"], [], [{"sofascore_event_id": 6}]]


def test_a_day_without_a_history_reads_its_12_printed_as_before(tmp_path):
    run = tmp_path / DAY
    run.mkdir()
    doc = {"profile": "standard", "created_at_utc": "2026-10-07T09:00:00Z",
           "pdf_rendered_at_utc": "2026-10-07T09:01:00Z", "singles": []}
    (run / PRINTED_MANIFEST).write_text(json.dumps(doc))
    history = print_history(run)
    assert [h["printed_in"] for h in history] == [PRINTED_MANIFEST]
    got = first_prints(history, T0 + timedelta(hours=1), leg_started_by())
    assert got is not None and got["singles"] == []
    assert print_history(tmp_path / "nothing") == []


def test_a_leg_of_an_earlier_render_survives_every_rebuild(two_legs, monkeypatch):
    """The 10-05 shape: printed at 09:01Z, its match starts 10:00Z, a render
    after the start leaves it out - and every later render does too. Each
    rebuild still locks it, as FIRST printed (time, odds, confidence)."""
    run = two_legs / DAY
    first = _confidence(two_legs, monkeypatch, T0)
    assert sorted(s["sofascore_event_id"] for s in first["singles"]) == [1, 2]
    _render(run, first, T0 + timedelta(minutes=1))
    leg2 = next(s for s in first["singles"] if s["sofascore_event_id"] == 2)
    at = datetime(2026, 10, 7, 10, 20, tzinfo=UTC)
    for i in range(4):
        doc = _confidence(two_legs, monkeypatch, at)
        locked = [s for s in doc["singles"] if s.get("locked")]
        assert [s["sofascore_event_id"] for s in locked] == [2], i
        assert locked[0]["printed_at_utc"] == "2026-10-07T09:01:00Z"
        assert locked[0]["offered_odds"] == leg2["offered_odds"]
        assert locked[0]["confidence"] == leg2["confidence"]
        if i:  # one render is read as it is (as 12_printed.json was)
            assert locked[0]["printed_in"].startswith(f"{PRINTED_HISTORY_DIR}/")
        assert doc.get("printed_after_start", []) == []
        # the next render leaves it out (as the 10-05 rebuild did)
        _render(run, doc, at + timedelta(minutes=1), drop={2})
        at += timedelta(minutes=15)
    # the history holds every render; the latest one does not hold the leg
    assert len(list((run / PRINTED_HISTORY_DIR).iterdir())) == 5
    latest = json.loads((run / PRINTED_MANIFEST).read_text())
    assert all(s["sofascore_event_id"] != 2 for s in latest["singles"])


def test_a_leg_dropped_on_wrong_evidence_comes_back_from_the_history(
        two_legs, monkeypatch, tmp_path):
    """The 10-05 chain itself: printed 09:01Z; a rebuild believed the match
    began 08:50Z (the order of play's clock) and dropped the leg as printed
    after its start; the next render left it out of 12_printed.json. When
    the real start (10:02Z) is known, the history gives it back - the
    overwritten 12_printed.json alone could not."""
    import shutil

    run = two_legs / DAY
    first = _confidence(two_legs, monkeypatch, T0)
    _render(run, first, T0 + timedelta(minutes=1))
    status = run / fs.FIXTURE_STATUS_FILE
    status.write_text(json.dumps({"events": {"2": {
        "status": "inprogress", "start_utc": "2026-10-07T08:50:00Z",
        "checked_at_utc": "2026-10-07T10:15:00Z"}}}))
    wrong = _confidence(two_legs, monkeypatch,
                        datetime(2026, 10, 7, 10, 20, tzinfo=UTC))
    assert not any(s.get("locked") for s in wrong["singles"])
    assert [x["sofascore_event_id"] for x in wrong["printed_after_start"]] == [2]
    _render(run, wrong, datetime(2026, 10, 7, 10, 21, tzinfo=UTC))
    status.write_text(json.dumps({"events": {"2": {
        "status": "inprogress", "start_utc": "2026-10-07T08:50:00Z",
        "real_start_utc": "2026-10-07T10:02:00Z", "real_start_basis": "first_set",
        "checked_at_utc": "2026-10-07T10:35:00Z"}}}))
    # without the history (12_printed.json only, as before F0.1): lost
    before = tmp_path / "before_f01"
    shutil.copytree(two_legs / DAY, before / DAY)
    shutil.rmtree(before / DAY / PRINTED_HISTORY_DIR)
    later = datetime(2026, 10, 7, 10, 40, tzinfo=UTC)
    lost = _confidence(before, monkeypatch, later)
    assert not any(s.get("locked") for s in lost["singles"])
    # with it: locked, as printed at 09:01Z
    back = _confidence(two_legs, monkeypatch, later)
    locked = [s for s in back["singles"] if s.get("locked")]
    assert [(s["sofascore_event_id"], s["printed_at_utc"]) for s in locked] == [
        (2, "2026-10-07T09:01:00Z")]
    assert back.get("printed_after_start", []) == []


def test_a_leg_removed_by_a_render_before_its_start_stays_removed(
        two_legs, monkeypatch):
    run = two_legs / DAY
    first = _confidence(two_legs, monkeypatch, T0)
    _render(run, first, T0 + timedelta(minutes=1))
    # 09:30Z, before the 10:00Z start: the operator holds a PDF without it
    _render(run, first, T0 + timedelta(minutes=30), drop={2})
    doc = _confidence(two_legs, monkeypatch, datetime(2026, 10, 7, 10, 20, tzinfo=UTC))
    assert not any(s.get("locked") for s in doc["singles"])
    assert doc.get("printed_after_start", []) == []


def test_a_leg_printed_only_after_its_start_is_late_and_on_record(
        two_legs, monkeypatch):
    """No leg ends in printed_after_start without a history entry: the
    entry names the render it comes from, and that render is on disk."""
    run = two_legs / DAY
    first = _confidence(two_legs, monkeypatch, T0)
    _render(run, first, T0 + timedelta(minutes=1), drop={2})
    _render(run, first, datetime(2026, 10, 7, 10, 5, tzinfo=UTC))  # after 10:00Z
    doc = _confidence(two_legs, monkeypatch, datetime(2026, 10, 7, 10, 20, tzinfo=UTC))
    assert not any(s.get("locked") for s in doc["singles"])
    late = doc["printed_after_start"]
    assert [x["sofascore_event_id"] for x in late] == [2]
    assert late[0]["printed_at_utc"] == "2026-10-07T10:05:00Z"
    assert (run / late[0]["printed_in"]).exists()


def test_first_print_is_the_start_of_the_unbroken_run():
    def render(at: str, odds: float | None) -> dict[str, Any]:
        singles = [] if odds is None else [{
            "sofascore_event_id": 1, "market": "goals_total", "subject": "",
            "line": 1.5, "direction": "OVER", "kickoff_utc": "2026-10-07T12:00:00Z",
            "confidence": 0.8, "offered_odds": odds}]
        return {"profile": "standard", "created_at_utc": at,
                "pdf_rendered_at_utc": at, "pdf_max_singles": None,
                "singles": singles, "printed_in": f"printed/{at}.json"}

    history = [render("2026-10-07T08:00:00Z", 1.30),
               render("2026-10-07T09:00:00Z", None),   # withdrawn
               render("2026-10-07T10:00:00Z", 1.35),   # printed again
               render("2026-10-07T11:00:00Z", 1.40),
               render("2026-10-07T12:30:00Z", None)]   # after the start
    now = datetime(2026, 10, 7, 12, 40, tzinfo=UTC)
    got = first_prints(history, now, leg_started_by())
    assert got is not None
    [leg] = got["singles"]
    assert leg["printed_at_utc"] == "2026-10-07T10:00:00Z"
    assert leg["offered_odds"] == 1.35
    out = carry_over(got, "standard", now, lambda eid, ko: True)
    assert [s["offered_odds"] for s in out.singles] == [1.35]
    # an as-of replay at 10:30Z sees only the renders made by then
    early = first_prints(history, datetime(2026, 10, 7, 10, 30, tzinfo=UTC),
                         leg_started_by())
    assert early is not None and early["printed_history"][-1].endswith("10:00:00Z.json")


def test_a_sport_leg_of_an_earlier_render_is_locked_by_the_assembly(tmp_path):
    from scripts.sofa.build_coupon import prepare_sports

    run = tmp_path / "2026-10-07"
    run.mkdir()
    leg = cs.normalize(_sport_leg())
    base = {"profile": "standard", "epoch": "stats_only",
            "created_at_utc": "2026-10-07T09:00:00Z", "pdf_max_singles": None}
    record_print(run, {**base, "singles": [leg],
                       "pdf_rendered_at_utc": "2026-10-07T09:01:00Z"})
    record_print(run, {**base, "singles": [],
                       "pdf_rendered_at_utc": "2026-10-07T12:02:00Z"})
    (run / "vetoes.json").write_text("[]")
    (run / "reads.json").write_text("[]")
    doc = prepare_sports(run, {"legs": [_sport_leg()]},
                         datetime(2026, 10, 7, 12, 5, tzinfo=UTC))
    assert [x.get("locked") for x in doc["legs"]] == [True]
    assert doc["legs"][0]["printed_at_utc"] == "2026-10-07T09:01:00Z"


def _sport_leg() -> dict[str, Any]:
    from tests.sofa.test_coupon_sports import _sport_leg as base

    return base(kickoff_utc="2026-10-07T12:00:00Z")


def test_c2_finds_a_printed_leg_that_vanished_and_an_unrecorded_late_one(tmp_path):
    from scripts.sofa.audit_variants import audit_print_record

    run = tmp_path / DAY
    run.mkdir()
    leg = {"sofascore_event_id": 1, "match": "A - B", "market": "goals_total",
           "subject": "", "line": 1.5, "direction": "OVER",
           "kickoff_utc": "2026-10-07T10:00:00Z", "confidence": 0.8,
           "offered_odds": 1.3}
    base = {"profile": "standard", "created_at_utc": "2026-10-07T09:00:00Z",
            "pdf_max_singles": None}
    record_print(run, {**base, "singles": [leg],
                       "pdf_rendered_at_utc": "2026-10-07T09:01:00Z"})
    record_print(run, {**base, "singles": [],
                       "pdf_rendered_at_utc": "2026-10-07T10:30:00Z"})
    started = started_by_evidence({}, {})
    coupon = {"created_at_utc": "2026-10-07T10:40:00Z", "pdf_max_singles": None,
              "singles": [], "printed_after_start": [
                  {"kind": "single", "key": [9, "goals_total", "", 2.5, "UNDER"],
                   "sofascore_event_id": 9, "match": "C - D"}]}
    found = audit_print_record(run, coupon, "official", started)
    assert any("A - B" in f and "gone from the coupon" in f for f in found)
    assert any("C - D" in f and "without a print record" in f for f in found)
    # locked as printed: clean
    ok = {**coupon, "printed_after_start": [], "singles": [
        {**leg, "locked": True, "printed_at_utc": "2026-10-07T09:01:00Z"}]}
    assert audit_print_record(run, ok, "official", started) == []


# ---------------------------------------------------------------------------
# F0.3 - the real start of a tennis match
# ---------------------------------------------------------------------------


def _tennis(status: dict[str, Any], time: dict[str, Any], start: int) -> dict[str, Any]:
    # The shape of sofa_event_detail.detail_json (cache, read 2026-10-05).
    return {"event": {"status": status, "startTimestamp": start, "time": time,
                      "tournament": {"category": {"sport": {"slug": "tennis"}}}}}


# Hugo Grenier - Georgii Kravchenko (17253654), read 10:17:55Z: 1st set.
GRENIER = _tennis({"code": 8, "description": "1st set", "type": "inprogress"},
                  {"currentPeriodStartTimestamp": 1791193252}, 1791193200)
# Diego Dedura-Palomero - Oliver Tarvet (17253481), read 10:17:55Z: 2nd set.
TARVET = _tennis({"code": 9, "description": "2nd set", "type": "inprogress"},
                 {"period1": 2346, "currentPeriodStartTimestamp": 1791193990},
                 1791191400)


def test_the_real_start_of_grenier_and_tarvet_on_10_05():
    at = datetime(2026, 10, 5, 10, 17, 55, tzinfo=UTC)
    g = fs.entry_from_payload(GRENIER, "printed", at)
    t = fs.entry_from_payload(TARVET, "printed", at)
    assert (g["start_utc"], g["real_start_utc"], g["real_start_basis"]) == (
        "2026-10-05T09:40:00Z", "2026-10-05T09:40:52Z", "first_set")
    assert (t["start_utc"], t["real_start_utc"], t["real_start_basis"]) == (
        "2026-10-05T09:10:00Z", "2026-10-05T09:14:04Z", "derived")


def test_the_lock_reads_the_real_start_not_the_order_of_play():
    started = started_by_evidence({}, {
        1: fs.entry_from_payload(GRENIER, "printed",
                                 datetime(2026, 10, 5, 10, 17, tzinfo=UTC)),
        2: fs.entry_from_payload(TARVET, "printed",
                                 datetime(2026, 10, 5, 10, 17, tzinfo=UTC))})
    # Grenier: startTimestamp 09:40:00Z, the first point 09:40:52Z
    assert not started(1, "2026-10-05T09:00:00Z",
                       datetime(2026, 10, 5, 9, 40, 30, tzinfo=UTC))
    assert started(1, "2026-10-05T09:00:00Z",
                   datetime(2026, 10, 5, 9, 41, tzinfo=UTC))
    # Tarvet: the 09:19:49Z print came after the 09:14Z first set ...
    assert started(2, "2026-10-05T09:00:00Z",
                   datetime(2026, 10, 5, 9, 19, 49, tzinfo=UTC))
    # ... and a print at 09:12Z came before it, though startTimestamp said 09:10Z
    assert not started(2, "2026-10-05T09:00:00Z",
                       datetime(2026, 10, 5, 9, 12, tzinfo=UTC))


def test_real_start_shapes_from_the_cache():
    # finished in three sets: the last set's start minus sets 1 and 2
    done = _tennis({"code": 100, "type": "finished"},
                   {"period1": 2348, "period2": 1394, "period3": 1691,
                    "currentPeriodStartTimestamp": 1791174815}, 1791171000)
    got, basis = fs.real_start(done["event"])
    assert got == fs._z(datetime.fromtimestamp(1791174815 - 2348 - 1394, UTC))
    assert basis == "derived"
    # not started, a walkover, a changeover code, football: no real start
    assert fs.real_start(
        _tennis({"code": 0, "type": "notstarted"}, {}, 1)["event"]) == (None, None)
    assert fs.real_start(_tennis({"code": 91, "type": "finished"},
                                 {"currentPeriodStartTimestamp": 5}, 1)["event"]) == (
        None, None)
    assert fs.real_start(_tennis({"code": 31, "type": "inprogress"},
                                 {"currentPeriodStartTimestamp": 5}, 1)["event"]) == (
        None, None)
    football = {"status": {"code": 6, "type": "inprogress"},
                "time": {"currentPeriodStartTimestamp": 5},
                "tournament": {"category": {"sport": {"slug": "football"}}}}
    assert fs.real_start(football) == (None, None)
    # a set length missing: never subtracted (stays an upper bound)
    gap = _tennis({"code": 10, "type": "inprogress"},
                  {"period1": 100, "currentPeriodStartTimestamp": 10_000}, 1)
    assert fs.real_start(gap["event"])[0] == fs._z(
        datetime.fromtimestamp(10_000 - 100, UTC))


def test_a_cached_status_is_dated_by_its_fetch_not_by_the_check():
    fetched = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
    payload = {"event": {"status": {"type": "notstarted", "code": 0},
                         "startTimestamp": 1791190800}}
    out, _ = check({1: "printed"}, lambda e: None, lambda e: (payload, fetched),
                   lambda *a: None)
    assert out[1]["checked_at_utc"] == "2026-10-05T09:00:00Z"
    # so "notstarted" says nothing about a print at 09:19Z
    started = started_by_evidence({}, out)
    assert started(1, "2026-10-05T09:10:00Z", datetime(2026, 10, 5, 9, 19, tzinfo=UTC))


# ---------------------------------------------------------------------------
# F0.4 - the status before the first print
# ---------------------------------------------------------------------------


def _event(status: str, code: int) -> dict[str, Any]:
    return {"event": {"status": {"type": status, "code": code},
                      "startTimestamp": 1791399600}}


def test_an_interrupted_match_never_reaches_the_first_print(two_legs, monkeypatch):
    """No 08, 11 or print yet - the first build. FIXTURE_CHECK asks both
    sheet fixtures; El Porvenir - Canuelas' shape (halted, re-dated,
    "interrupted") is refused before anything was printed."""
    run = two_legs / DAY
    fixtures = json.loads((run / "02_fixtures.json").read_text())
    targets, over = targets_for(run, fixtures, [], T0)
    assert targets == {2: "candidate", 1: "candidate"} and over == []
    assert list(targets) == [2, 1]  # nearest start first
    payloads = {1: _event("notstarted", 0), 2: _event("interrupted", 80)}
    events, stopped = check(targets, payloads.get, lambda e: None, lambda *a: None)
    assert not stopped
    (run / fs.FIXTURE_STATUS_FILE).write_text(json.dumps(
        {"events": {str(k): v for k, v in events.items()}}))
    doc = _confidence(two_legs, monkeypatch, T0)
    assert [s["sofascore_event_id"] for s in doc["singles"]] == [1]
    assert doc["fixtures_not_as_scheduled"][0]["status"] == "interrupted"
    assert doc["fixture_status_not_asked"] == 0


def test_a_first_print_without_a_check_is_counted(two_legs, monkeypatch):
    doc = _confidence(two_legs, monkeypatch, T0)
    assert doc["fixture_status_not_asked"] == 2


def test_candidates_are_priced_unstarted_sheet_fixtures_and_the_coupons(tmp_path):
    run = tmp_path / DAY
    run.mkdir()
    fx = [{"sofascore_event_id": e, "kickoff_utc": ko, "superbet_kickoff_utc": ko}
          for e, ko in ((1, "2026-10-07T18:00:00Z"), (2, "2026-10-07T08:00:00Z"),
                        (3, "2026-10-07T19:00:00Z"), (4, "2026-10-07T08:30:00Z"))]
    (run / "05_sheet.json").write_text(json.dumps([
        {"sofascore_event_id": 1, "offered_odds": 1.5},
        {"sofascore_event_id": 2, "offered_odds": 1.5},   # under way
        {"sofascore_event_id": 3, "offered_odds": None},  # unpriced
    ]))
    # a leg of the provisional coupon (and a sport leg, which K14 never reads)
    (run / "11_coupon.json").write_text(json.dumps({
        "singles": [{"sofascore_event_id": 4},
                    {"sofascore_event_id": 900, "sport": "hockey"}]}))
    assert candidate_event_ids(run, fx, {}, T0) == [4, 1]
    # FIXTURE_CHECK: 4 is on the coupon artifact (asked as printed, first);
    # the cap drops the furthest candidates, never a printed match
    targets, over = targets_for(run, fx, [], T0)
    assert targets == {4: "printed", 1: "candidate"} and over == []
    targets, over = targets_for(run, fx, [], T0, max_candidates=0)
    assert targets == {4: "printed"} and over == [1]


# ---------------------------------------------------------------------------
# F0.5 - the reason an event is UNVERIFIED
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("exc, reason", [
    (ProviderError("HTTP 403"), fs.PROVIDER_REFUSED),
    (ProviderError("HTTP 429"), fs.PROVIDER_REFUSED),
    (ProviderError("HTTP 503"), fs.PROVIDER_ERROR),
    (ProviderError("HTML instead of JSON"), fs.BAD_PAYLOAD),
    (ProviderError("Network error after retry: refused"), fs.NO_BRIDGE),
    (TransportError("bridge down"), fs.NO_BRIDGE),
    (CircuitOpenError("Circuit breaker is open"), fs.CIRCUIT_OPEN),
])
def test_a_failure_names_its_reason_and_the_rest_is_not_asked(exc, reason):
    def fetch(eid: int) -> Any:
        if eid == 1:
            return None  # 404
        raise exc

    out, stopped = check({1: "printed", 2: "printed", 3: "candidate"}, fetch,
                         lambda e: None, lambda *a: None)
    assert stopped
    assert [out[e]["reason"] for e in (1, 2, 3)] == [fs.NOT_FOUND, reason, fs.NOT_ASKED]
    assert {e["status"] for e in out.values()} == {fs.UNVERIFIED}
    assert fs.unverified_reasons(out.values()) == dict(sorted(
        {fs.NOT_FOUND: 1, reason: 1, fs.NOT_ASKED: 1}.items()))


def test_the_confidence_artifact_and_the_pdf_say_why(two_legs, monkeypatch):
    from scripts.sofa.build_coupon_pdf import fixture_status_notes

    run = two_legs / DAY
    (run / fs.FIXTURE_STATUS_FILE).write_text(json.dumps({"events": {
        "1": {"status": fs.UNVERIFIED, "reason": fs.NOT_FOUND},
        "2": {"status": fs.UNVERIFIED}}}))  # written before F0.5
    doc = _confidence(two_legs, monkeypatch, T0)
    assert doc["fixture_status_unverified_reasons"] == {"NOT_FOUND": 1, "UNKNOWN": 1}
    notes = " ".join(fixture_status_notes(doc))
    assert "2 mecz(e/ów) bez świeżego statusu" in notes
    assert "404" in notes and "powód niezapisany" in notes
    assert "bez mostka" not in notes
    # an artifact from before F0.5: the count, with the reason unknown
    old = " ".join(fixture_status_notes({"fixture_status_unverified": 1}))
    assert "powód niezapisany: 1" in old
