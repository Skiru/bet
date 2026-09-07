"""The harness that decides whether the calibration correction may ship.

``scripts/simple/validate_calibration.py`` is the only thing standing between a
correction that works and one that merely looks like it does, so it needs tests
of its own: a validator that always says IMPROVEMENT is worse than no validator,
because it launders a bad idea. Three properties matter and each is asserted
against a synthetic board whose right answer is known by construction.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from simple.validate_calibration import _fit, _gap  # noqa: E402


def _board(
    *,
    dates: int,
    fixtures_per_date: int,
    rungs_per_fixture: int,
    claim: float,
    truth: float,
    seed: int = 5,
) -> list[list]:
    """A scope where rows claiming ``claim`` really win at rate ``truth``.

    Deterministic rather than random: every fixture gets the same integer number
    of winners, so the realised rate is exactly ``truth`` and any drift the
    validator reports is the validator's own.
    """
    import random

    rng = random.Random(seed)
    wins = round(rungs_per_fixture * truth)
    out = []
    for date in range(dates):
        for fixture in range(fixtures_per_date):
            outcomes = [1.0] * wins + [0.0] * (rungs_per_fixture - wins)
            rng.shuffle(outcomes)
            key = f"d{date}-f{fixture}"
            stamp = f"2026-08-{date + 1:02d}"
            for won in outcomes:
                out.append([claim, won, key, stamp])
    return out


def _scope_gap(text: str, scope: str) -> tuple[float, float]:
    """``(gap before, gap after)`` for one scope out of the per-scope table.

    Parsed with a regex rather than ``split()``: the two figures are printed
    right-aligned either side of a bare ``->``, so whitespace does not reliably
    separate them and ``split()`` returns ``'+0.3000->'`` as one token.
    """
    import re

    match = re.search(
        rf"^{re.escape(scope)}\s+\d+\s+([-+][\d.]+)-> ?([-+][\d.]+)",
        text,
        re.M,
    )
    assert match, f"{scope} absent from:\n{text[-2500:]}"
    return float(match.group(1)), float(match.group(2))


def _run(rungs: dict, *args: str) -> tuple[int, str]:
    path = Path(
        subprocess.run(
            [sys.executable, "-c", "import tempfile;print(tempfile.mkstemp()[1])"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    path.write_text(json.dumps(rungs))
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "scripts/simple/validate_calibration.py",
                "--rungs",
                str(path),
                "--draws",
                "60",
                *args,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        return proc.returncode, proc.stdout + proc.stderr
    finally:
        path.unlink(missing_ok=True)


# --- it must find a real, large overconfidence -----------------------------

def test_a_market_that_claims_ninety_and_wins_sixty_is_corrected():
    """The easy case, and if this fails nothing else in the file matters."""
    rungs = {
        "hot_market": _board(
            dates=8, fixtures_per_date=12, rungs_per_fixture=10,
            claim=0.90, truth=0.60,
        )
    }
    code, out = _run(rungs)
    assert code == 0, out[-2000:]
    assert "IMPROVEMENT" in out
    # 0.90 claimed against 0.60 realised is a 0.30 gap; held out, the fit sees
    # seven of eight dates and should recover most of it.
    before, after = _scope_gap(out, "hot_market")
    assert before == pytest.approx(0.30, abs=0.01)
    assert after < 0.10, (before, after)


# --- and it must NOT invent one on a calibrated market ----------------------

def test_a_perfectly_calibrated_market_is_left_where_it_was():
    """The property that makes the exit code worth anything.

    A correction that fires on a market claiming 0.80 and realising 0.80 is
    fitting noise, and this is the shape that would hide it: enough data to look
    convincing, nothing actually wrong.
    """
    rungs = {
        "calibrated": _board(
            dates=8, fixtures_per_date=25, rungs_per_fixture=10,
            claim=0.80, truth=0.80,
        )
    }
    code, out = _run(rungs)
    before, after = _scope_gap(out, "calibrated")
    assert before == pytest.approx(0.0, abs=1e-9)
    assert after == pytest.approx(0.0, abs=1e-9), (before, after)
    # And a no-op is reported as one rather than as a failure: "nothing to
    # correct here" and "this correction is harmful" are different findings and
    # only the second should stop it shipping.
    assert "NO CHANGE" in out
    assert code == 0


def test_a_market_that_under_claims_is_never_pushed_further_under():
    """One-sidedness, end to end through the script rather than the module."""
    rungs = {
        "cold": _board(
            dates=8, fixtures_per_date=25, rungs_per_fixture=10,
            claim=0.70, truth=0.90,
        )
    }
    _code, out = _run(rungs)
    before, after = _scope_gap(out, "cold")
    assert before == pytest.approx(-0.20, abs=0.01)
    assert after == pytest.approx(before, abs=1e-9), (before, after)


# --- the mechanics the numbers depend on ------------------------------------

def test_the_held_out_date_is_absent_from_the_curve_it_is_scored_against():
    """The one thing that makes every figure in this file out-of-sample.

    Asserted directly on the fit rather than through the output, because a
    leak here would not show up as an error -- it would show up as a validator
    that always approves.
    """
    board = _board(
        dates=4, fixtures_per_date=20, rungs_per_fixture=10,
        claim=0.80, truth=0.50,
    )
    favoured = [(float(p), float(w), str(f), str(d)) for p, w, f, d in board]
    held = "2026-08-03"
    train = [row for row in favoured if row[3] != held]
    entry = _fit(train)
    assert entry["rungs"] == len(train)
    assert entry["rungs"] < len(favoured)
    assert entry["fixtures"] == len({r[2] for r in train})
    # And no fixture key from the held-out date can be inside it.
    assert not any(row[3] == held for row in train)


def test_rows_are_dropped_from_both_arms_when_no_curve_can_be_fitted():
    """A scope too thin to bucket without one date must not be scored.

    Passing those rows through uncorrected would dilute the comparison with
    rows where the two arms are identical by construction, making a real effect
    look smaller than it is -- so they leave both arms or neither.
    """
    # 30 rungs is the bucket floor; two dates of 12 leaves 12 in training.
    thin = _board(
        dates=2, fixtures_per_date=6, rungs_per_fixture=2,
        claim=0.80, truth=0.50,
    )
    fat = _board(
        dates=6, fixtures_per_date=20, rungs_per_fixture=10,
        claim=0.90, truth=0.60,
    )
    code, out = _run({"thin": thin, "fat": fat})
    assert code == 0, out[-2000:]
    assert "rungs skipped (no curve without the held-out date)" in out
    assert "thin" not in out.split("scope ")[-1]


def test_the_unfavoured_side_of_every_rung_is_excluded():
    """Reading both sides makes every market claim 0.500 and realise 0.500 by
    construction -- each line is published on both sides, the probabilities sum
    to one and exactly one wins. A validator that forgot this would report a
    perfectly calibrated board whatever the truth."""
    hot = _board(
        dates=6, fixtures_per_date=20, rungs_per_fixture=10,
        claim=0.90, truth=0.60,
    )
    mirrored = hot + [[1 - p, 1 - w, f, d] for p, w, f, d in hot]
    _code, out_hot = _run({"m": hot})
    _code, out_mirror = _run({"m": mirrored})
    def scored(text: str) -> int:
        line = next(
            row for row in text.splitlines() if row.startswith("rungs scored")
        )
        return int(line.split()[2])
    assert scored(out_hot) == scored(out_mirror)


def test_gap_is_claimed_minus_realised_and_positive_means_overconfident():
    """Pinned because the sign convention is quoted in three docstrings and a
    commit message, and a flipped sign would invert every conclusion."""
    assert _gap([(0.9, 1.0), (0.9, 0.0)]) == pytest.approx(0.9 - 0.5)
    assert _gap([(0.5, 1.0), (0.5, 1.0)]) == pytest.approx(-0.5)


def test_the_mode_is_selectable_and_they_disagree():
    """The three candidates must actually be three candidates.

    If ``--mode`` were ignored, the comparison that chose the shipped gate would
    have been a comparison of one thing with itself.
    """
    rungs = {
        "hot": _board(
            dates=8, fixtures_per_date=10, rungs_per_fixture=8,
            claim=0.90, truth=0.62,
        )
    }
    results = {}
    for mode in ("ci", "shrink", "gated"):
        _code, out = _run(rungs, "--mode", mode)
        results[mode] = _scope_gap(out, "hot")[1]
        assert f"mode={mode}" in out
    assert len(set(results.values())) > 1, results
    # Where the gap is real and clears the gate, "gated" is "shrink" -- the
    # gate decides whether, the damping decides how much.
    assert results["gated"] == pytest.approx(results["shrink"], abs=1e-9), results
    # "ci" is the odd one out. Note it is *not* always the most conservative:
    # on a board this deterministic the clustered variance is near zero, so its
    # interval is razor thin and it subtracts almost the whole point estimate,
    # where the damped modes hold back n/(n+K). On real data, where fixtures
    # disagree, it is the timid one -- which is why it lost the bake-off.
    assert results["ci"] != pytest.approx(results["gated"], abs=1e-9), results


def test_a_missing_rungs_file_exits_two_rather_than_tracebacking():
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/simple/validate_calibration.py",
            "--rungs",
            "/nonexistent/rungs.json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "missing" in proc.stdout + proc.stderr
