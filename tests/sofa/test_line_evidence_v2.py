"""Line evidence, second rules (epochs.LINE_EVIDENCE_V2_FROM_UTC, 2026-10-08)."""

from __future__ import annotations

from datetime import UTC, datetime

from bet.sofa import epochs
from bet.sofa import line_evidence as le

BAND = "2.20-1000.00"


def _ev(cells: dict, v2: bool, star: dict | None = None) -> le.LineEvidence:
    bands = {"football": {"k|OVER": {BAND: cells}}}
    if star:
        bands["football"]["*"] = {BAND: star}
    return le.LineEvidence({"keys": {}, "bands": bands}, v2)


def test_the_switch_opens_at_its_moment() -> None:
    at = epochs.LINE_EVIDENCE_V2_FROM_UTC
    assert at is not None
    day = epochs.LINE_EVIDENCE_V2_DATE
    assert not epochs.line_evidence_v2(day, at.replace(minute=at.minute - 1))
    assert epochs.line_evidence_v2(day, at)
    assert not epochs.line_evidence_v2("2026-10-06", at)


def test_a_thin_expensive_cell_widens_down_inside_its_band() -> None:
    # 12 lines at p >= 0.80 (thin), 35 lines at p >= 0.70 realised 0.34:
    # v1 skips the band and reads another cell, v2 reads the widened cell.
    cells = {"0.800-0.825": {"n": 12, "k": 4}, "0.700-0.750": {"n": 23, "k": 8}}
    legacy = _ev(cells, v2=False)
    v2 = _ev(cells, v2=True)
    assert legacy.band_cell("football", "k|OVER", 0.82, 2.5) is None
    n, k, label = v2.band_cell("football", "k|OVER", 0.82, 2.5)  # type: ignore[misc]
    assert (n, k) == (35, 12) and "@2.20-1000.00" in label
    read = v2.read("football", "k|OVER", 0.82, (0.81, "curve", 500), 2.5)
    assert read is not None and read.value < 0.5 and read.band_cap is not None


def test_widening_never_reaches_below_the_printable_floor() -> None:
    cells = {"0.600-0.700": {"n": 40, "k": 10}}
    assert _ev(cells, v2=True).band_cell("football", "k|OVER", 0.82, 2.5) is None


def _no_curve(games: int | None, v2: bool, deff: float = 1.0) -> le.LineEvidence:
    bucket = {"n": 60, "k": 54}
    if games is not None:
        bucket["games"] = games
    return le.LineEvidence({"keys": {"basketball": {"x|OVER": {
        "buckets": {"0.800-0.825": bucket}}}},
        "design_effect": {"basketball": deff}}, v2)


def test_lines_of_a_few_games_are_not_evidence_in_v2() -> None:
    assert _no_curve(6, v2=False).read("basketball", "x|OVER", 0.81, None) is not None
    assert _no_curve(6, v2=True).read("basketball", "x|OVER", 0.81, None) is None
    assert _no_curve(None, v2=True).read("basketball", "x|OVER", 0.81, None) is None


def test_the_design_effect_only_lowers_the_wilson_bound() -> None:
    plain = _no_curve(30, v2=True, deff=1.0).read(
        "basketball", "x|OVER", 0.81, None)
    clustered = _no_curve(30, v2=True, deff=4.0).read(
        "basketball", "x|OVER", 0.81, None)
    old = _no_curve(30, v2=False).read("basketball", "x|OVER", 0.81, None)
    assert plain is not None and clustered is not None and old is not None
    assert clustered.value < plain.value <= old.value + 1e-9


def test_design_effect_of_independent_and_clustered_lines() -> None:
    independent = [(f"g{i}", i % 2) for i in range(40)]
    clustered = [(f"g{i // 8}", (i // 8) % 2) for i in range(40)]
    assert le.design_effect(independent) == 1.0
    assert le.design_effect(clustered) > 4.0


def _rows(spec: dict[str, tuple[int, int]], sport: str = "cs2") -> list[dict]:
    rows = []
    for key, (lines, games) in spec.items():
        for i in range(lines):
            rows.append({"sport": sport, "key": key, "p": 0.75, "y": i % 2,
                         "game": f"{key}{i % games}", "base": 0.75, "odds": 1.4})
    return rows


def test_a_dominant_key_is_left_out_of_the_pool_for_the_others() -> None:
    doc = le.fit(_rows({"team_rounds|OVER": (80, 40), "handicap|T1": (10, 5),
                        "total|OVER": (10, 5)}))
    pooled = doc["sport_printable"]["cs2"]
    assert pooled["without"]["key"] == "team_rounds|OVER"
    assert pooled["without"]["n"] == 20
    doc["sport_printable"]["cs2"]["without"]["realised_minus_confidence"] = [
        -0.1, -0.2, 0.0]
    doc["sport_printable"]["cs2"]["without"]["games"] = 25
    doc["sport_printable"]["cs2"]["without"]["n"] = 60
    doc["sport_printable"]["cs2"]["games"] = 40
    doc["sport_printable"]["cs2"]["n"] = 100
    doc["sport_printable"]["cs2"]["realised_minus_confidence"] = [-0.3, -0.4, -0.2]
    legacy = le.LineEvidence(doc, False)
    v2 = le.LineEvidence(doc, True)
    assert legacy.offset("cs2", "handicap|T1") == -0.3
    assert v2.offset("cs2", "handicap|T1") == -0.1
    # the dominant key reads its own measured offset (80 lines, 40 games)
    assert v2.offset("cs2", "team_rounds|OVER") == legacy.offset(
        "cs2", "team_rounds|OVER")


def test_no_dominant_key_no_exclusion() -> None:
    doc = le.fit(_rows({"a|OVER": (30, 15), "b|OVER": (30, 15), "c|OVER": (30, 15)}))
    assert "without" not in doc["sport_printable"]["cs2"]
    assert set(doc["design_effect"]) == {"cs2"}
    assert doc["keys"]["cs2"]["a|OVER"]["buckets"]["0.750-0.800"]["games"] == 15


def test_cs2_format_is_not_guessed_from_v2(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from types import SimpleNamespace

    from scripts.sofa import run_sport_confidence as rsc

    seen: list[int] = []

    def fake(line, t1, t2, n1, n2, best_of, maps, ratings, home):  # type: ignore[no-untyped-def]
        seen.append(best_of)
        return SimpleNamespace(p=0.6)

    monkeypatch.setattr(rsc.cs2_engine, "model_probability", fake)
    at = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
    monkeypatch.setattr(epochs, "datetime", SimpleNamespace(now=lambda tz: at))
    fixture = {"home_id": 1, "away_id": 2, "home_is_team1": True, "best_of": None}
    ev = SimpleNamespace(team1="a", team2="b")
    for date, expected in (("2026-10-06", [3]), ("2026-10-08", [3])):
        fc = rsc.DbForecaster("unused.db", at, date)
        fc._cs2 = ([], {}, None)  # type: ignore[assignment]
        got = fc.probability("cs2", fixture, ev, SimpleNamespace())
        if date == "2026-10-06":
            assert got == 0.6 and seen == expected  # the old rule, unchanged
        else:
            assert got is None and seen == expected  # v2: nothing guessed
    fixture["best_of"] = 1
    fc = rsc.DbForecaster("unused.db", at, "2026-10-08")
    fc._cs2 = ([], {}, None)  # type: ignore[assignment]
    assert fc.probability("cs2", fixture, ev, SimpleNamespace()) == 0.6
    assert seen[-1] == 1


def test_settle_cs2_attaches_no_model_to_an_unknown_format(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from contextlib import nullcontext
    from types import SimpleNamespace

    from scripts.sofa import settle_cs2 as sc

    calls: list[int] = []
    monkeypatch.setattr(epochs.timeutil, "now",
                        lambda: datetime(2026, 10, 9, 6, 0, tzinfo=UTC))
    monkeypatch.setattr(sc, "get_connection", lambda db: nullcontext(None))
    monkeypatch.setattr(sc, "load_history", lambda conn, before, eid: [])
    monkeypatch.setattr(sc, "build_ratings", lambda history: {})
    monkeypatch.setattr(sc, "model_probability",
                        lambda *a, **k: calls.append(a[5]) or SimpleNamespace(
                            p=0.6, n=5, model="m"))
    fields = {k: None for k in sc.Cs2Line.__dataclass_fields__}

    def run(kick: datetime, event: dict) -> dict:  # type: ignore[type-arg]
        row = dict(fields)
        ev = SimpleNamespace(team1="a", team2="b")
        sc.attach_model([row], ev, {"id": 1, **event}, {}, True, kick, "x.db")
        return row

    old = run(datetime(2026, 10, 6, 18, tzinfo=UTC), {})
    assert old["model_p"] == 0.6 and calls == [3]  # before v2: bo3 as before
    new = run(datetime(2026, 10, 8, 18, tzinfo=UTC), {})
    assert new["model_p"] is None and calls == [3]
    known = run(datetime(2026, 10, 8, 18, tzinfo=UTC), {"bestOf": 1})
    assert known["model_p"] == 0.6 and calls == [3, 1]


def test_the_design_effect_counts_the_lines_of_keys_without_a_curve() -> None:
    """2026-10-07 audit: CS2's design effect was 1.0 from its 61 rows with a
    curve; the stand-in keys (no curve) that read it measure 2.5-3.2."""
    rows = []
    for i in range(60):  # a key with a curve: independent lines, one a game
        rows.append({"sport": "cs2", "key": "a|OVER", "p": 0.75, "y": i % 2,
                     "game": f"a{i}", "base": 0.75, "odds": 1.4})
    for g in range(10):  # a key with no curve: 12 lines a game, all won or lost
        for _ in range(12):
            rows.append({"sport": "cs2", "key": "b|OVER", "p": 0.75, "y": g % 2,
                         "game": f"b{g}", "base": None, "odds": 1.4})
    assert le.fit(rows)["design_effect"]["cs2"] > 2.5
