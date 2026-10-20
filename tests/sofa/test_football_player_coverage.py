"""Football player-prop coverage in SAMPLES (epochs.FOOTBALL_PLAYER_COVERAGE_FROM_UTC,
off until the main session dates it; docs/sofa/evidence/
football_player_coverage_2026-10-21.md).

(a) a missing `onTargetScoringAttempt` beside a `hitWoodwork` is a proven
    zero: the woodwork shot is already in `shotOffTarget` - 213,047 of
    213,047 appearing footballers close the three-part identity;
(b) a footballer with fewer than min_sample starts in the team's last ten is
    sampled from his newest starts (at most ten) in the last twenty;
(c) the Polish / English transliteration and a surname inside a full Spanish
    name find the squad member - and never a team-mate.
Off, every path is what it was.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa.contracts import GapReason, Observation, PlayerSample
from bet.sofa.players import (
    extract_player_metric,
    match_player,
    match_player_by_inner_surname,
    match_player_by_surname,
    match_player_by_tokens,
    match_player_by_transliteration,
)
from bet.sofa.samples import build_player_samples, coverage_player_samples
from scripts.sofa import run_settle
from scripts.sofa.run_sheet import player_coverage_notes

SOT = "player_shots_on_target_for"
SHOTS = "player_shots_for"


def _woodwork_zero() -> dict[str, Any]:
    # Sofascore 17215596: one shot, off the post - no onTargetScoringAttempt
    return {"minutesPlayed": 90, "totalShots": 1, "shotOffTarget": 1,
            "hitWoodwork": 1}


def test_a_woodwork_shot_is_not_counted_twice_only_under_the_switch() -> None:
    assert extract_player_metric(SOT, _woodwork_zero()) is (
        GapReason.INTERNAL_INCONSISTENT)
    assert extract_player_metric(SOT, _woodwork_zero(), woodwork_once=True) == 0.0


def test_the_identity_still_refuses_what_does_not_close() -> None:
    # two shots, one accounted for: the missing one is not provably zero
    stats = {"minutesPlayed": 90, "totalShots": 2, "shotOffTarget": 1,
             "hitWoodwork": 1}
    assert extract_player_metric(SOT, stats, woodwork_once=True) is (
        GapReason.INTERNAL_INCONSISTENT)
    present = {"minutesPlayed": 90, "totalShots": 2,
               "onTargetScoringAttempt": 1, "shotOffTarget": 1}
    assert extract_player_metric(SOT, present, woodwork_once=True) == 1.0
    # the flag reads only the shots identity
    assert extract_player_metric(SHOTS, _woodwork_zero(), woodwork_once=True) == 1.0


@pytest.mark.parametrize(
    ("superbet", "sofascore"),
    [
        ("Jehor Macenko", "yegor matsenko"),
        ("Wiktor Cyhankow", "viktor tsygankov"),
        ("Władisław Krasowskij", "vladislav krasovskiy"),
        ("Bohdan Wjunnyk", "bogdan viunnyk"),
        ("Artem Putiwcew", "artem putivtsev"),
        ("Roman Jakuba", "roman yakuba"),
        ("Daniel N`Lundulu", "dan n'lundulu"),
        ("Kochergin, Vladyslav", "wladyslaw kocherhin"),
    ],
)
def test_a_transliterated_name_finds_the_player(superbet: str, sofascore: str) -> None:
    squad = {sofascore: {}, "piotr nowak": {}, "jan kowalski": {}}
    assert match_player(superbet, squad) is None
    assert match_player_by_tokens(superbet, squad) is None
    assert match_player_by_surname(superbet, squad) is None
    assert match_player_by_transliteration(superbet, squad) == sofascore


@pytest.mark.parametrize(
    ("superbet", "sofascore"),
    [
        ("Javier Martinez Calvo", "javi martinez"),
        ("Juan Jose Sanchez Romero", "juanjo sanchez"),
        ("Santiago Garcia Gonzalez", "santi garcia"),
        ("Daniel Diaz Gandara", "dani diaz"),
        ("Javier Villar del Fraile", "javi villar"),
    ],
)
def test_a_surname_inside_the_full_name_finds_the_player(
    superbet: str, sofascore: str
) -> None:
    squad = {sofascore: {}, "piotr nowak": {}}
    assert match_player_by_surname(superbet, squad) is None
    assert match_player_by_inner_surname(superbet, squad) == sofascore


@pytest.mark.parametrize(
    ("superbet", "rival"),
    [
        # 10-12..10-20: two men of one squad; the folded fuzzy try matched them
        ("Kirian Rodriguez", "adrian rodriguez"),
        ("Wanderson", "wenderson"),
        ("Alessandro Arena", "alessandro renzi"),
        ("Al Khaibari, Abdulelah", "abdul rahman al khaibari"),
        ("Abdulelah Al Khaibari", "abdul rahman al khaibari"),
        # a double letter is not folded: "saleem" is not "salem"
        ("Abdulrahman Salem A Al-Safari", "salem al saleem"),
        # the K7 cases stay refused
        ("Edenilson Andrade dos Santos", "eduardo santos"),
        ("Leonardo Caetano Silva", "lucas silva"),
    ],
)
def test_another_man_is_never_matched(superbet: str, rival: str) -> None:
    squad = {rival: {}, "piotr nowak": {}}
    assert match_player_by_transliteration(superbet, squad) is None
    assert match_player_by_inner_surname(superbet, squad) is None


def test_two_folded_candidates_are_no_answer() -> None:
    squad = {"viktor tsygankov": {}, "wiktor cyhankow": {}}
    assert match_player_by_transliteration("Wiktor Cyhankow", squad) is None
    assert match_player_by_inner_surname(
        "Javier Martinez Calvo", {"javi martinez": {}, "javier martinez": {}}) is None


def _played(shots: float, *, started: bool = True) -> dict[str, Any]:
    return {"minutesPlayed": 90.0, "totalShots": shots, "_started": started}


def _result(event_id: int, squad: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "collected": {},
        "is_h2h": False,
        "halves_divergences": [],
        "squad": squad,
        # event 1 is the newest
        "match_date_utc": datetime(2026, 10, 1, tzinfo=UTC) - timedelta(days=event_id),
        "opponent": "Someone",
        "competition_id": 7,
        "season_id": 1,
        "venue": "home",
    }


def _side(starts: list[bool], first: int = 1) -> list[dict[str, Any]]:
    return [
        _result(first + i, {"jan kowalski": _played(float(i), started=s),
                            "piotr nowak": _played(1.0)})
        for i, s in enumerate(starts)
    ]


WANT = {SHOTS: {"Jan Kowalski"}}
KEY = f"{SHOTS}|Jan Kowalski"


def test_a_thin_starter_is_sampled_over_the_last_twenty() -> None:
    # 3 starts in the last ten, 6 more in the next ten
    base = {"side_a": _side([True, False, True, False, True] + [False] * 5),
            "side_b": []}
    wide = {"side_a": base["side_a"] + _side([True] * 6 + [False] * 4, first=11),
            "side_b": []}
    calls: list[int] = []

    def fetch() -> dict[str, list[dict[str, Any]]]:
        calls.append(1)
        return wide

    gaps: list[Any] = []
    got = coverage_player_samples(WANT, base, fetch, gaps, min_sample=5,
                                  sample_n=10, starts_only=True)
    sample = got[KEY]
    assert sample.wide_window == 20
    # his newest starts: events 1, 3, 5, 11..16 - nine of them, at most ten
    assert [o.sofascore_event_id for o in sample.observations] == [
        1, 3, 5, 11, 12, 13, 14, 15, 16]
    assert calls == [1]
    # the wider window is written on the artifact, absent otherwise
    assert sample.model_dump()["wide_window"] == 20
    plain = build_player_samples(WANT, base, [], starts_only=True)[KEY]
    assert "wide_window" not in plain.model_dump()
    assert len(plain.observations) == 3


def test_the_wide_sample_keeps_at_most_ten_and_a_full_sample_is_untouched() -> None:
    base = {"side_a": _side([True] * 2 + [False] * 8), "side_b": []}
    wide = {"side_a": base["side_a"] + _side([True] * 10, first=11), "side_b": []}
    got = coverage_player_samples(WANT, base, lambda: wide, [], min_sample=5,
                                  sample_n=10, starts_only=True)[KEY]
    assert len(got.observations) == 10
    assert got.observations[0].sofascore_event_id == 1

    full = {"side_a": _side([True] * 6 + [False] * 4), "side_b": []}

    def never() -> dict[str, list[dict[str, Any]]]:
        raise AssertionError("a full sample asks for no wider history")

    kept = coverage_player_samples(WANT, full, never, [], min_sample=5,
                                   sample_n=10, starts_only=True)[KEY]
    assert kept.wide_window is None
    assert kept == build_player_samples(WANT, full, [], starts_only=True,
                                        coverage=True)[KEY]


def test_still_thin_in_twenty_keeps_the_first_attempt_and_its_gaps() -> None:
    base = {"side_a": _side([True] + [False] * 9), "side_b": []}
    wide = {"side_a": base["side_a"] + _side([True, True] + [False] * 8, first=11),
            "side_b": []}
    gaps: list[Any] = []
    got = coverage_player_samples(WANT, base, lambda: wide, gaps, min_sample=5,
                                  sample_n=10, starts_only=True)[KEY]
    assert got.wide_window is None and len(got.observations) == 1


def test_a_squad_new_player_found_only_in_the_older_matches_is_not_invented() -> None:
    # never in the last ten: NO_ENTITY_FOUND stays unless the twenty hold 5
    base = {"side_a": [_result(i, {"piotr nowak": _played(1.0)}) for i in range(1, 11)],
            "side_b": []}
    gaps: list[Any] = []
    got = coverage_player_samples(WANT, base, lambda: base, gaps, min_sample=5,
                                  sample_n=10, starts_only=True)
    assert got == {}
    assert [g.reason for g in gaps] == [GapReason.NO_ENTITY_FOUND]


def test_the_new_name_rules_run_only_with_coverage_and_after_the_others() -> None:
    want = {SHOTS: {"Jehor Macenko"}}
    sides = {"side_a": [_result(i, {"yegor matsenko": _played(1.0)})
                        for i in range(1, 6)], "side_b": []}
    assert build_player_samples(want, sides, [], token_fallback=True,
                                surname_fallback=True) == {}
    got = build_player_samples(want, sides, [], token_fallback=True,
                               surname_fallback=True, coverage=True)
    sample = got[f"{SHOTS}|Jehor Macenko"]
    assert (sample.match_rule, sample.matched_name) == (
        "transliteration", "yegor matsenko")
    notes = player_coverage_notes("Jehor Macenko", sample)
    assert notes and notes[0].startswith("PLAYER_NAME_TRANSLITERATION")


def test_samples_woodwork_zero_only_with_coverage() -> None:
    want = {SOT: {"Jan Kowalski"}}
    sides = {"side_a": [_result(i, {"jan kowalski": dict(_woodwork_zero(),
                                                         _started=True)})
                        for i in range(1, 6)], "side_b": []}
    off_gaps: list[Any] = []
    off = build_player_samples(want, sides, off_gaps, starts_only=True)
    assert off == {}
    assert {g.reason for g in off_gaps} >= {GapReason.INTERNAL_INCONSISTENT}
    on = build_player_samples(want, sides, [], starts_only=True, coverage=True)
    assert [o.value for o in on[f"{SOT}|Jan Kowalski"].observations] == [0.0] * 5


def _obs(i: int) -> Observation:
    return Observation(sofascore_event_id=i, match_date_utc=datetime(2026, 9, i,
                       tzinfo=UTC), opponent="X", value=1.0, competition_id=7,
                       season_id=1, venue="home")


def test_sheet_notes_say_what_the_switch_did_and_nothing_otherwise() -> None:
    plain = PlayerSample(metric=SHOTS, player="Jan Kowalski",
                         matched_name="jan kowalski", side="side_a",
                         squad_matches=10, observations=[_obs(1)])
    assert player_coverage_notes("Jan Kowalski", plain) == []
    wide = plain.model_copy(update={"wide_window": 20})
    assert player_coverage_notes("Jan Kowalski", wide)[0].startswith(
        "PLAYER_WIDE_WINDOW: his newest 1 starts in the team's last 20")
    inner = plain.model_copy(update={"match_rule": "inner_surname"})
    assert player_coverage_notes("Jan Kowalski", inner)[0].startswith(
        "PLAYER_NAME_INNER_SURNAME")


def test_settle_grades_the_new_rules_by_matched_name_and_woodwork_zero() -> None:
    doc = [{"sofascore_event_id": 9, "players": {
        f"{SHOTS}|Jehor Macenko": {"match_rule": "transliteration",
                                   "matched_name": "yegor matsenko"},
        f"{SHOTS}|Javier Martinez Calvo": {"match_rule": "inner_surname",
                                           "matched_name": "javi martinez"},
        f"{SHOTS}|Jan Kowalski": {"match_rule": "fuzzy",
                                  "matched_name": "jan kowalski"}}}]
    assert run_settle.player_token_names(doc) == {
        (9, f"{SHOTS}|Jehor Macenko"): "yegor matsenko",
        (9, f"{SHOTS}|Javier Martinez Calvo"): "javi martinez",
    }
    row = {"market": SOT, "subject": "Jan Kowalski", "line": 0.5,
           "direction": "UNDER"}
    squads = {True: {"jan kowalski": dict(_woodwork_zero(), _started=True)},
              False: {"piotr nowak": _played(1.0)}}
    assert run_settle._settle_player(row, squads, True) == (
        f"{SOT}:INTERNAL_INCONSISTENT")
    assert run_settle._settle_player(row, squads, True, coverage=True) == (
        0.0, "WIN")


def test_the_switch_reads_the_day_and_the_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = datetime(2026, 10, 21, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(epochs, "FOOTBALL_PLAYER_COVERAGE_FROM_UTC", None)
    assert epochs.football_player_coverage("2099-01-01", at) is False
    monkeypatch.setattr(epochs, "FOOTBALL_PLAYER_COVERAGE_FROM_UTC", at)
    assert epochs.football_player_coverage("2026-10-21", at) is True
    assert epochs.football_player_coverage("2026-10-20", at) is False
    assert epochs.football_player_coverage(
        "2026-10-21", at - timedelta(minutes=1)) is False


# --- the history replay (calibrate_from_cache --player-coverage) -----------


def _replay_squad(shots: float, started: bool = True) -> dict[str, dict[str, Any]]:
    return {"jan kowalski": _played(shots, started=started),
            "piotr nowak": _played(1.0)}


def _replay(wide: bool) -> list[Any]:
    from scripts.sofa import calibrate_from_cache as cfc

    base = [_replay_squad(2.0, started=i < 3) for i in range(10)]
    older = [_replay_squad(1.0) for _ in range(10)]
    event = {"id": 999, "tournament": {"uniqueTournament": {"id": 17}}}
    return cfc.player_rows_for_event(
        event, {True: _replay_squad(2.0), False: None},
        {True: base, False: []}, {SHOTS: [1.5]}, 5,
        starters_only=True, starts_only=True,
        wide_history={True: base + older, False: []} if wide else None,
        sample_n=10)


def test_the_replay_widens_a_thin_starter_like_samples() -> None:
    assert [r for r in _replay(False) if r.subject == "jan kowalski"] == []
    rows = [r for r in _replay(True) if r.subject == "jan kowalski"]
    assert rows and {r.sample_size for r in rows} == {10}
    # his 3 starts of the last ten (2 shots) and the 7 newest older ones (1)
    assert {r.sample_mean for r in rows} == {round((3 * 2.0 + 7 * 1.0) / 10, 4)}
    # a full sample is untouched by the flag
    full = {(r.line, r.direction, r.p_central) for r in _replay(False)
            if r.subject == "piotr nowak"}
    assert full == {(r.line, r.direction, r.p_central) for r in _replay(True)
                    if r.subject == "piotr nowak"}
