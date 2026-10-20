"""Football referees (bet.sofa.referees): the label tables, the payload
parsers, the backfill's paging and discovery choices, the as-of referee
book (no look-ahead) and the measurement's fit helpers. Offline and fast."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from bet.sofa import referees as rf
from scripts.sofa import backfill_referees as br
from scripts.sofa import measure_referee_effect as mre


def _event(eid: int, ts: int, ut: int = 17, sport: str = "football") -> dict[str, Any]:
    return {"id": eid, "startTimestamp": ts,
            "tournament": {"uniqueTournament": {"id": ut},
                           "category": {"sport": {"slug": sport}}}}


def _detail(eid: int, ts: int, ref: dict[str, Any] | None) -> dict[str, Any]:
    ev = _event(eid, ts)
    if ref is not None:
        ev["referee"] = ref
    return {"event": ev}


def test_from_event_detail_reads_the_referee() -> None:
    label, ref = rf.from_event_detail(
        5, _detail(5, 1000, {"id": 77, "name": "A B", "games": 12,
                             "yellowCards": 40, "redCards": 1,
                             "yellowRedCards": 0, "country": {"name": "Poland"}}))
    assert label == rf.EventReferee(5, 77, "A B", 1000, 17, "football", "event")
    assert ref is not None and ref.country == "Poland" and ref.yellow_cards == 40


def test_from_event_detail_without_referee_is_an_asked_empty_label() -> None:
    label, ref = rf.from_event_detail(5, _detail(5, 1000, None))
    assert ref is None and label.referee_id is None and label.start_ts == 1000


def test_from_referee_page_labels_every_event_and_dates_the_page() -> None:
    payload = {"events": [_event(1, 300), _event(2, 100), {"bad": 1}],
               "hasNextPage": True}
    labels, oldest, has_next = rf.from_referee_page(9, payload, "X")
    assert [lb.event_id for lb in labels] == [1, 2]
    assert all(lb.referee_id == 9 and lb.source == "referee_page" for lb in labels)
    assert oldest == 100 and has_next is True
    assert rf.from_referee_page(9, None) == ([], None, False)


def test_next_page_stops_at_the_cutoff_or_the_last_page() -> None:
    assert rf.next_page([], 500) == 0
    assert rf.next_page([(0, 900, True)], 500) == 1
    assert rf.next_page([(0, 900, True), (1, 400, True)], 500) is None
    assert rf.next_page([(0, 900, False)], 500) is None
    assert rf.next_page([(0, None, False)], 500) is None


def test_store_never_replaces_a_referee_with_an_empty_answer(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    store = rf.RefereeStore(db)
    store.save_labels([rf.EventReferee(1, 77, "A", 10, 17, "football", "referee_page")])
    store.save_labels([rf.EventReferee(1, None, None, 10, 17, "football", "event")])
    found = rf.referee_for_event(db, 1)
    assert found is not None and found.referee_id == 77
    assert found.source == "referee_page"
    store.save_labels([rf.EventReferee(2, None, None, 10, 17, "football", "event")])
    assert rf.referee_for_event(db, 2) is None
    assert rf.load_labels(db) == {1: 77}


def test_referee_for_event_falls_back_to_the_cached_detail(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE sofa_event_detail (sofascore_event_id INTEGER "
                 "PRIMARY KEY, fetched_at TEXT, status_type TEXT, detail_json TEXT)")
    conn.execute("INSERT INTO sofa_event_detail VALUES (?, ?, ?, ?)",
                 (3, "2026-10-20T10:00:00+00:00", "notstarted",
                  json.dumps(_detail(3, 2000, {"id": 55, "name": "R"}))))
    conn.commit()
    conn.close()
    found = rf.referee_for_event(db, 3)
    assert found is not None and found.referee_id == 55 and found.source == "detail"
    assert rf.load_labels(db) == {3: 55}
    assert rf.referee_for_event(db, 4) is None


def test_book_reads_only_matches_strictly_before() -> None:
    metrics = ("cards_points",)
    matches = [rf.MatchTotals(i, 1000 + i, 1, None, {"cards_points": 4.0})
               for i in range(rf.MIN_LEAGUE_MATCHES)]
    # the referee's first match: 8 cards (twice the league), then a match at
    # the same second as another of his - neither sees the other
    matches += [rf.MatchTotals(100, 5000, 1, 7, {"cards_points": 8.0}),
                rf.MatchTotals(101, 6000, 1, 7, {"cards_points": 0.0}),
                rf.MatchTotals(102, 6000, 1, 7, {"cards_points": 0.0}),
                rf.MatchTotals(103, 7000, 1, 7, {"cards_points": 4.0})]
    reads = {m.event_id: r["cards_points"] for m, r in rf.walk_reads(matches, metrics)}
    assert reads[100].n == 0 and reads[100].ratio(10.0) == 1.0
    assert reads[101].n == 1 and reads[102].n == 1
    assert reads[101].ratio_sum == pytest.approx(2.0)
    assert reads[103].n == 3
    assert reads[103].ratio(0.0) == pytest.approx(
        (2.0 + 0.0 + 0.0) / 3, rel=1e-6)
    # the shrunk ratio: (sum + K) / (n + K)
    assert reads[101].ratio(1.0) == pytest.approx(1.5)


def test_book_rejects_out_of_order_matches() -> None:
    ms = [rf.MatchTotals(1, 10, 1, None, {}), rf.MatchTotals(2, 5, 1, None, {})]
    with pytest.raises(ValueError):
        list(rf.walk_reads(ms, ("cards_points",)))


def test_league_mean_needs_enough_matches_and_falls_back_to_pooled() -> None:
    book = rf.RefereeBook(("fouls",))
    assert book.league_mean(1, "fouls") is None
    for _ in range(rf.MIN_LEAGUE_MATCHES):
        book.update(None, 2, {"fouls": 20.0})
    assert book.league_mean(1, "fouls") == pytest.approx(20.0)
    for _ in range(rf.MIN_LEAGUE_MATCHES):
        book.update(None, 1, {"fouls": 30.0})
    assert book.league_mean(1, "fouls") == pytest.approx(30.0)


def test_discovery_round_robins_board_first_newest_first_and_skips_barren() -> None:
    events = [{"id": 1, "ts": 10, "competition": 5}, {"id": 2, "ts": 30, "competition": 6},
              {"id": 3, "ts": 20, "competition": 5}, {"id": 4, "ts": 40, "competition": 9},
              {"id": 5, "ts": 50, "competition": 5}, {"id": 6, "ts": 5, "competition": 8}]
    out = br.discovery_targets(events, done={5}, skip={9}, board={5, 8})
    assert [e["id"] for e in out] == [3, 6, 1, 2]
    m = br.MAX_BARREN_MISSES
    assert br.barren({5: [0, m], 6: [1, 99], 7: [0, 1], 10: [m, m]}) == {5, 6}


def test_an_event_label_keeps_its_source_when_a_page_lists_it(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    store = rf.RefereeStore(db)
    store.save_labels([rf.EventReferee(1, 77, "A", 10, 17, "football", "event")])
    store.save_labels([rf.EventReferee(1, 77, "A", 10, 17, "football", "referee_page")])
    store.save_labels([rf.EventReferee(1, 77, "A", 10, 17, "football", "detail")])
    found = rf.referee_for_event(db, 1)
    assert found is not None and found.source == "event"


def test_labelled_state_counts_detail_hits_and_event_misses(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    store = rf.RefereeStore(db)
    store.save_labels([
        rf.EventReferee(1, 77, "A", 10, 5, "football", "detail"),
        rf.EventReferee(2, None, None, 10, 5, "football", "event"),
        rf.EventReferee(3, 78, "B", 10, 5, "football", "referee_page"),
        rf.EventReferee(4, None, None, 10, 6, "football", "event"),
    ])
    done, comp = br.labelled_state(str(db))
    assert done == {1, 2, 3, 4}
    assert comp == {5: [1, 1], 6: [0, 1]}


def test_pending_referees_lists_the_next_page() -> None:
    pages = {1: [], 2: [(0, 900, True)], 3: [(0, 100, True)]}
    assert br.pending_referees(pages, 500) == [(1, 0), (2, 1)]


def test_runner_pages_a_referee_back_to_the_cutoff(tmp_path: Path) -> None:
    store = rf.RefereeStore(tmp_path / "s.db")
    asked: list[str] = []
    pages = {0: {"events": [_event(1, 900), _event(2, 800)], "hasNextPage": True},
             1: {"events": [_event(3, 400)], "hasNextPage": True}}

    def get(url: str) -> Any:
        asked.append(url)
        return pages[int(url.rsplit("/", 1)[1])]

    runner = br.Runner(get, lambda eid: None, store, None, None, 500, None)
    runner.page_referee((7, 0, "R"))
    assert len(asked) == 2  # page 1 reached past the cutoff: no page 2
    assert rf.load_labels(tmp_path / "s.db") == {1: 7, 2: 7, 3: 7}


def test_fit_beta_recovers_a_multiplier() -> None:
    rng = np.random.default_rng(0)
    c = np.full(20000, 4.0)
    x = rng.normal(0, 0.3, 20000)
    y = rng.poisson(c * np.exp(0.8 * x)).astype(float)
    assert mre.fit_beta(c, x, y) == pytest.approx(0.8, abs=0.05)


def test_log_ratio_is_zero_without_a_record() -> None:
    n = np.array([0.0, 4.0])
    s = np.array([0.0, 6.0])
    out = mre.log_ratio(n, s, 2.0)
    assert out[0] == 0.0 and out[1] == pytest.approx(np.log(8.0 / 6.0))


def test_isotonic_curve_is_monotone() -> None:
    rng = np.random.default_rng(1)
    p = rng.uniform(0, 1, 5000)
    hit = (rng.uniform(0, 1, 5000) < p).astype(float)
    curve = mre.isotonic(p, hit)
    q = mre.apply_curve(curve, np.linspace(0, 1, 50))
    assert np.all(np.diff(q) >= -1e-12)


def test_nb_cdf_matches_poisson_at_zero_alpha() -> None:
    assert mre.nb_cdf(0, 2.0, 0.0) == pytest.approx(np.exp(-2.0))
    assert 0.0 < mre.nb_cdf(3, 4.0, 0.2) < 1.0
