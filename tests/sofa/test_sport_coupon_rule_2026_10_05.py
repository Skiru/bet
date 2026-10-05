"""The sport coupons' rule from 2026-10-05 (the operator's order).

fair_p x odds >= 0.90 and the official margin cap (15%) for every sport;
hockey and basketball gate on and print a recalibrated probability; a
volleyball leg needs a tournament with a settled event. Days before the
cutover keep the rule they were printed under.
"""

from __future__ import annotations

import dataclasses
import json
import math
import random
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import sport_coupon as sc
from scripts.sofa import audit_variants, fit_sport_price_calibration, run_sport_coupon
from tests.sofa.test_sport_coupon import AT, DATE, snap, total_pair, write_snaps
from tests.sofa.test_sport_coupon_gradeable import with_tournament, write_settled

NEW = "2026-10-05"


def cands(
    snaps: list[dict[str, Any]],
    rule: sc.Rule,
    sport: sc.SportKey = "hockey",
    settled: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    counts: dict[str, int] = {}
    events = sc.latest_events(sport, snaps)
    return sc.candidates(sport, events, AT, rule, counts, settled=settled), counts


@pytest.fixture()
def calibration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[float, float]:
    a, c = -0.01, 0.89
    (tmp_path / sc.PRICE_CALIBRATION_FILE).write_text(
        json.dumps(
            {
                "sports": {
                    "hockey": {"a": a, "c": c},
                    "basketball": {"a": 0.0, "c": 0.88},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SOFA_CONFIG_DIR", str(tmp_path))
    return a, c


def test_a_day_before_the_cutover_keeps_its_old_rule() -> None:
    old = sc.rule_for("hockey", "2026-10-04")
    assert old == sc.Rule()
    assert (old.min_x, old.calibration, old.max_overround) == (None, None, 0.105)
    assert not sc.rule_for("volleyball", "2026-10-04").requires_settled_tournament


def test_the_new_rule_per_sport(calibration: tuple[float, float]) -> None:
    for sport in sc.SPORT_KEYS:
        rule = sc.rule_for(sport, NEW)
        assert (rule.floor, rule.min_x, rule.max_overround) == (0.70, 0.90, 0.15)
        assert (rule.calibration is not None) is (sport in ("hockey", "basketball"))
        assert rule.requires_settled_tournament is (sport == "volleyball")
    assert sc.rule_for("hockey", NEW).calibration == calibration


def test_a_missing_calibration_fails_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOFA_CONFIG_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        sc.rule_for("hockey", NEW)
    assert sc.rule_for("cs2", NEW).calibration is None  # needs no file


def test_calibrated_p_is_the_logistic_line() -> None:
    assert sc.calibrated_p(0.5, 0.0, 0.9) == pytest.approx(0.5)
    p = 0.80
    want = 1 / (1 + math.exp(-(-0.01 + 0.89 * math.log(p / (1 - p)))))
    assert sc.calibrated_p(p, -0.01, 0.89) == pytest.approx(want)
    assert sc.calibrated_p(p, -0.01, 0.89) < p  # a favourite is pulled down


def test_min_x_refuses_a_side_paying_back_under_90_percent() -> None:
    fresh = AT - timedelta(minutes=10)
    # 1.15 / 3.60: a 14.7% margin, under the 15% cap. The pipeline's devig
    # leaves most of it on the long side: OVER fair ~0.826, x ~0.950 - in;
    # UNDER fair ~0.174, x ~0.63 - out on MIN_X (the floor is opened here so
    # that MIN_X is what decides). 1.12 / 3.40 (~19%) is out on the cap.
    rule = sc.Rule(floor=0.0, max_overround=0.15, min_x=0.90)
    got, counts = cands(
        [
            snap("2", total_pair("2", 1.12, 3.40), fresh),
            snap("3", total_pair("3", 1.15, 3.60), fresh),
        ],
        rule,
    )
    assert [(c["superbet_event_id"], c["side"]) for c in got] == [("3", "OVER")]
    assert counts == {"BELOW_MIN_X": 1, "MARGIN_TOO_HIGH": 2}
    # the old rule had no MIN_X
    _, old = cands(
        [snap("3", total_pair("3", 1.15, 3.60), fresh)],
        sc.Rule(floor=0.0, max_overround=0.15),
    )
    assert "BELOW_MIN_X" not in old


def test_the_floor_and_x_read_the_calibrated_p() -> None:
    fresh = AT - timedelta(minutes=10)
    lines = [snap("1", total_pair("1", 1.20, 4.20), fresh)]
    [plain], _ = cands(lines, sc.Rule(max_overround=0.15, min_x=0.90))
    assert "p" not in plain
    # a correction strong enough to pull this ~0.78 favourite under 0.70
    strong = sc.Rule(max_overround=0.15, min_x=0.90, calibration=(-0.5, 0.5))
    got, counts = cands(lines, strong)
    assert got == [] and counts["BELOW_FLOOR"] == 2
    mild = sc.Rule(max_overround=0.15, min_x=0.80, calibration=(-0.01, 0.89))
    [leg], _ = cands(lines, mild)
    assert leg["p"] == pytest.approx(
        sc.calibrated_p(leg["fair_p"], -0.01, 0.89), abs=1e-4
    )
    assert leg["p"] < leg["fair_p"]
    assert leg["p_x_odds"] == pytest.approx(leg["p"] * leg["odds"], abs=1e-3)


def test_a_volleyball_leg_needs_a_settled_tournament(tmp_path: Path) -> None:
    write_settled(
        tmp_path,
        "volleyball",
        "2026-10-03",
        {
            "1": {"tournament": "Liga", "state": "SETTLED"},
            "2": {"tournament": "Puchar", "state": "NOT_ON_SOFASCORE"},
        },
    )
    known = sc.settled_tournaments(str(tmp_path), "volleyball", NEW)
    assert known == ["Liga"]
    fresh = AT - timedelta(minutes=10)
    snaps = [
        with_tournament(snap("1", total_pair("1", 1.20, 4.20), fresh), "Liga"),
        with_tournament(snap("2", total_pair("2", 1.20, 4.20), fresh), "Nowy"),
    ]
    rule = sc.Rule(requires_settled_tournament=True)
    got, counts = cands(snaps, rule, "volleyball", known)
    assert {c["superbet_event_id"] for c in got} == {"1"}
    assert counts["tournament_never_settled"] == 1
    # without the requirement an unseen tournament is still allowed
    got, _ = cands(snaps, sc.Rule(), "volleyball", known)
    assert {c["superbet_event_id"] for c in got} == {"1", "2"}


def test_the_rule_round_trips_through_the_artifact() -> None:
    rule = sc.Rule(
        max_overround=0.15,
        min_x=0.9,
        calibration=(-0.01, 0.89),
        requires_settled_tournament=True,
    )
    # min_odds is written rounded to 4 places, as it always was
    back = sc.Rule.from_dict(json.loads(json.dumps(rule.as_dict())))
    assert back == dataclasses.replace(rule, min_odds=round(rule.min_odds, 4))
    old = sc.Rule().as_dict()
    for key in ("min_x", "price_calibration", "requires_settled_tournament"):
        old.pop(key)
    assert sc.Rule.from_dict(old) == sc.Rule(min_odds=round(sc.MIN_ODDS, 4))


def test_a_new_day_builds_audits_clean_and_prints_the_calibrated_p(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calibration: tuple[float, float]
) -> None:
    runs = tmp_path / "runs"
    at = AT.replace(year=2026, month=10, day=5)
    d = write_snaps(
        runs,
        "hockey",
        NEW,
        [
            snap(
                str(i),
                total_pair(str(i), 1.20, 4.20),
                at - timedelta(minutes=5),
                kickoff=at + timedelta(hours=1 + i),
            )
            for i in range(2)
        ],
    )
    monkeypatch.setenv("SOFA_RUNS_DIR", str(runs))
    monkeypatch.setattr(run_sport_coupon, "now", lambda: at)
    monkeypatch.setattr("sys.argv", ["x", "--date", NEW, "--sport", "hockey"])
    assert run_sport_coupon.main() == 0
    doc = json.loads((d / sc.COUPON_FILE).read_text(encoding="utf-8"))
    assert doc["rule"]["min_x"] == 0.9
    assert doc["rule"]["price_calibration"] == {
        "a": calibration[0],
        "c": calibration[1],
    }
    assert all(leg["p"] < leg["fair_p"] for leg in doc["legs"]) and doc["legs"]
    md = (d / sc.COUPON_MD).read_text(encoding="utf-8")
    assert "(cena " in md
    found = audit_variants.audit_sport(str(runs), "hockey", NEW)
    assert [f for f in found if f.startswith(("S2", "S3", "S5"))] == []
    # a leg whose p was edited is caught
    doc["legs"][0]["p"] = doc["legs"][0]["fair_p"]
    (d / sc.COUPON_FILE).write_text(json.dumps(doc), encoding="utf-8")
    found = audit_variants.audit_sport(str(runs), "hockey", NEW)
    assert any("from fair_p" in f for f in found)


def test_the_fit_recovers_a_known_line() -> None:
    rng = random.Random(3)
    rows = []
    for i in range(20000):
        p = rng.uniform(0.05, 0.95)
        q = sc.calibrated_p(p, -0.05, 0.85)
        rows.append(
            (f"2026-09-{29 + i % 2}", str(i), p, 1.0 if rng.random() < q else 0.0)
        )
    a, c = fit_sport_price_calibration.fit(rows)
    assert a == pytest.approx(-0.05, abs=0.06) and c == pytest.approx(0.85, abs=0.05)
    out = fit_sport_price_calibration.lodo(rows)
    assert out["days"] == 2 and out["oos_lines_p70"] > 0


def test_the_ledger_replays_a_past_day_under_its_own_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.sofa import record_results

    seen: list[sc.Rule] = []

    def fake(
        runs_dir: str, sport: str, dates: list[str], rule: sc.Rule
    ) -> dict[str, Any]:
        seen.append(rule)
        return {"n": 0}

    monkeypatch.setattr(sc, "load_settled", lambda *a: {"events": {}})
    monkeypatch.setattr(sc, "rule_history", fake)
    record_results.rule_rows("unused", DATE)
    assert seen and all(r == sc.Rule() for r in seen)
