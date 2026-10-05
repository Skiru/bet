"""K12/K14 (plan 2026-10-05): a fresh /event/{id} start replaces RESOLVE's
frozen clock; a postponed / cancelled / abandoned match is refused, with
no bridge nothing is refused."""

from __future__ import annotations

from datetime import UTC, datetime

from bet.sofa import fixture_status as fs
from bet.sofa.locked_print import kicked_off, kickoff_clocks
from scripts.sofa.capture_closing import with_refreshed_kickoff
from scripts.sofa.run_fixture_check import check

FX = {"sofascore_event_id": 7, "kickoff_utc": "2026-10-05T06:20:00Z",
      "superbet_kickoff_utc": "2026-10-05T06:20:00Z"}


def test_a_fresh_start_replaces_the_frozen_clock_70_min_earlier():
    seen = "2026-10-05T07:30:00Z"
    fresh = "2026-10-05T07:30:00Z"
    now = datetime(2026, 10, 5, 6, 30, tzinfo=UTC)
    assert min(kickoff_clocks(FX, seen)).hour == 6  # the old rule: 06:20
    assert min(kickoff_clocks(FX, seen, fresh)) == datetime(
        2026, 10, 5, 7, 30, tzinfo=UTC)
    assert kicked_off(FX, seen, False, now)            # refused on the stale clock
    assert not kicked_off(FX, seen, False, now, fresh)  # open on the fresh one


def test_capture_closing_times_the_close_on_the_fresh_start(tmp_path):
    import json

    (tmp_path / "02_fixtures.json").write_text(json.dumps([FX]))
    (tmp_path / "04_offer.json").write_text(json.dumps([
        {"sofascore_event_id": 7,
         "superbet_kickoff_seen_utc": "2026-10-05T07:30:00Z"}]))
    (tmp_path / fs.FIXTURE_STATUS_FILE).write_text(json.dumps({"events": {"7": {
        "status": "notstarted", "start_utc": "2026-10-05T07:30:00Z"}}}))
    legs = [("official",
             {"sofascore_event_id": 7, "kickoff_utc": "2026-10-05T06:20:00Z"})]
    assert with_refreshed_kickoff(tmp_path, legs)[0][1]["kickoff_utc"] == (
        "2026-10-05T07:30:00Z")


def test_postponed_is_refused_unverified_is_not():
    assert fs.not_as_scheduled({"status": "postponed"}) == "postponed"
    assert fs.not_as_scheduled({"status": "canceled"}) == "canceled"
    assert fs.not_as_scheduled({"status": "notstarted"}) is None
    assert fs.not_as_scheduled({"status": fs.UNVERIFIED}) is None
    # RESOLVE's own status where no fresh check exists
    assert fs.not_as_scheduled(None, "postponed") == "postponed"
    assert fs.refreshed_start({"status": fs.UNVERIFIED, "start_utc": "x"}) is None


def test_a_halted_match_re_dated_is_not_as_scheduled():
    # El Porvenir - Canuelas (15276945), 10-05: kicked off 10-03, halted at
    # 0-0, startTimestamp moved to 10-05 18:00Z with status "interrupted".
    assert fs.not_as_scheduled({"status": "interrupted"}) == "interrupted"
    assert fs.not_as_scheduled({"status": "suspended"}) == "suspended"
    assert fs.not_as_scheduled({"status": "willcontinue"}) == "willcontinue"
    assert fs.not_as_scheduled(None, "interrupted") == "interrupted"
    # a start delayed by minutes has not kicked off
    assert fs.not_as_scheduled({"status": "delayed"}) is None


def test_only_printed_matches_and_moved_clocks_are_asked():
    other = {**FX, "sofascore_event_id": 8}
    printed = {**FX, "sofascore_event_id": 9}
    got = fs.events_to_check([FX, other, printed],
                             {7: "2026-10-05T07:30:00Z", 8: "2026-10-05T06:30:00Z"},
                             {9})
    assert got == {7: "clock_gap", 9: "printed"}


def test_no_bridge_leaves_every_event_unverified_and_stops_at_the_first_refusal():
    from bet.sofa.errors import TransportError

    calls = []

    def fetch(eid: int):
        calls.append(eid)
        raise TransportError("bridge down")

    out, refused = check({1: "printed", 2: "printed"}, fetch, lambda e: None,
                         lambda *a: None)
    assert refused and calls == [1]
    assert {e["status"] for e in out.values()} == {fs.UNVERIFIED}


def test_an_event_payload_gives_status_and_start():
    payload = {"event": {"status": {"type": "postponed", "code": 60},
                         "startTimestamp": 1759670400}}
    e = fs.entry_from_payload(payload, "printed", datetime(2026, 10, 5, tzinfo=UTC))
    assert e["status"] == "postponed" and e["start_utc"].startswith("2025-10-05")


def test_a_match_only_on_the_printed_record_is_still_checked(tmp_path):
    # 10-05: a rebuild took Grenier's leg off 11_coupon.json while the
    # operator held it on the 09:19Z PDF; FIXTURE_CHECK stopped asking, so
    # the lock judged it on the stale printed clock.
    import json

    from scripts.sofa.run_fixture_check import printed_event_ids

    run = tmp_path / "2026-10-05"
    run.mkdir()
    eleven = {"pdf_max_singles": None, "singles": [{"sofascore_event_id": 1}]}
    printed = {"pdf_max_singles": None, "singles": [{"sofascore_event_id": 2}]}
    (run / "11_coupon.json").write_text(json.dumps(eleven))
    (run / "12_printed.json").write_text(json.dumps(printed))
    assert printed_event_ids(run) == {1, 2}
