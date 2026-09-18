#!/usr/bin/env python3
"""The `sofa` pipeline, end to end (PLAN §A3, §A4).

Runs BOARD -> RESOLVE -> OFFER -> SAMPLES -> OFFER -> SHEET -> COUPON.

The offer is read **twice on purpose** (A4): once before sampling, so we only
pay for metrics somebody actually prices, and once immediately before the coupon
so the price the bar is compared against is fresh. Leaving that to "whoever runs
the stages in the right order" is how a morning price ends up on an evening
coupon, so the order lives in code.

The first half of that sentence was untrue until F19. SAMPLES built its own
SuperbetClient and asked Superbet again, once per fixture, so the pre-sample
OFFER had no reader at all: it wrote 04_offer.json, nothing opened it, and the
second call overwrote it. Its only effects were ~600 requests a day and the
ability to fail the run — which is exactly what happened on 2026-09-18. SAMPLES
now reads the artifact, and falls back to a live call only for a fixture the
artifact does not cover.

Each stage is still runnable on its own against the artifact on disk; this
script only sequences them.

Exit: 0 = OK, 1 = PARTIAL, 2 = FAILED.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Before any first-party import, because this is what makes them resolvable.
#
# Running a file puts *its own directory* on sys.path — here `scripts/sofa` —
# and neither the package root (`src`, where `bet` lives) nor the repository
# root (where `scripts` lives, and stages are imported as `scripts.sofa.*`).
# So the command in this module's docstring only ever worked for a caller who
# had already arranged PYTHONPATH, and failed with a bare ModuleNotFoundError
# for anyone who took the docstring at its word.
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.timeutil import now  # noqa: E402

# Stage entry points are imported lazily inside run_stage so that a broken
# stage module fails that stage, not the whole run.
STAGE_MODULES: dict[str, str] = {
    "BOARD": "scripts.sofa.run_board",
    "RESOLVE": "scripts.sofa.run_resolve",
    "OFFER": "scripts.sofa.run_offer",
    "SAMPLES": "scripts.sofa.run_samples",
    "SHEET": "scripts.sofa.run_sheet",
    "COUPON": "scripts.sofa.run_coupon",
    # Not in DEFAULT_SEQUENCE, and that is the whole design: SETTLE grades a
    # day that is over, so running it against today's date would find every
    # fixture unfinished. Invoke it for D-1:
    #
    #     python scripts/sofa/run_pipeline.py --date 2026-09-18 --only SETTLE
    #
    # It is the only writer that puts a Superbet price next to an outcome, and
    # therefore the only source `fit_k_price` and MAX_LADDER_SIGMA can ever fit
    # from (F53).
    "SETTLE": "scripts.sofa.run_settle",
}

# (stage, label) — OFFER appears twice by design.
DEFAULT_SEQUENCE: list[tuple[str, str]] = [
    ("BOARD", "BOARD"),
    ("RESOLVE", "RESOLVE"),
    ("OFFER", "OFFER (pre-sample: which markets have a price at all)"),
    ("SAMPLES", "SAMPLES"),
    ("OFFER", "OFFER (refresh: the price the bar is measured against)"),
    ("SHEET", "SHEET"),
    ("COUPON", "COUPON"),
]


@dataclass
class StageResult:
    stage: str
    label: str
    exit_code: int

    @property
    def verdict(self) -> str:
        return {0: "OK", 1: "PARTIAL"}.get(self.exit_code, "FAILED")


def run_stage(stage: str, date: str) -> int:
    """Invoke one stage's main() with the date argument it expects."""
    import importlib

    module = importlib.import_module(STAGE_MODULES[stage])
    main: Callable[[], int | None] = module.main

    argv = sys.argv
    sys.argv = [STAGE_MODULES[stage], "--date", date]
    try:
        result = main()
    except SystemExit as exc:  # stages that still exit rather than return
        code = exc.code
        return code if isinstance(code, int) else 0
    except Exception as exc:
        # A stage that raises fails *that stage*, not the run (F15). The lazy
        # import above only ever defended against a broken module; an exception
        # at execution time — the likelier one — went straight through main()
        # and took the five remaining stages with it, even though
        # --stop-on-failure had not been asked for.
        run_id = os.environ.get("SOFA_RUN_ID", "")
        print(
            f"STAGE_EXCEPTION run_id={run_id} stage={stage}: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
            flush=True,
        )
        traceback.print_exc()
        return 2
    finally:
        sys.argv = argv
    return result if isinstance(result, int) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=now().strftime("%Y-%m-%d"), help="YYYY-MM-DD")
    parser.add_argument(
        "--only",
        help="run just this stage, whether or not it is in the daily sequence",
    )
    parser.add_argument(
        "--from-stage",
        choices=list(STAGE_MODULES),
        help="resume at this stage, reusing the artifacts already on disk",
    )
    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="abort the run at the first FAILED stage instead of continuing",
    )
    parser.add_argument(
        "--run-id",
        help="reuse this run id instead of minting a new one (for resuming)",
    )
    args = parser.parse_args()

    # One id for the whole sequence, minted *before* the stages run — it used
    # to be set after the loop, so every log row from a pipeline run carried
    # run_id "" and F8 was inert (F13). Assignment, not setdefault: an id
    # inherited from a previous run's shell would silently merge two runs in
    # the log, which is the same defect with the sign flipped.
    run_id = args.run_id or uuid.uuid4().hex[:12]
    os.environ["SOFA_RUN_ID"] = run_id

    sequence = DEFAULT_SEQUENCE
    if args.only:
        if args.only not in STAGE_MODULES:
            print(f"unknown stage {args.only}", file=sys.stderr)
            return 2
        sequence = [(args.only, args.only)]
    elif args.from_stage:
        start = next(
            (i for i, (s, _) in enumerate(sequence) if s == args.from_stage), None
        )
        if start is None:
            print(f"unknown stage {args.from_stage}", file=sys.stderr)
            return 2
        sequence = sequence[start:]

    results: list[StageResult] = []
    for stage, label in sequence:
        print(f"--- {label} ---", file=sys.stderr, flush=True)
        code = run_stage(stage, args.date)
        result = StageResult(stage, label, code)
        results.append(result)
        # Every stage reports its verdict, not just the failures (F18). A
        # verdict is information you need *during* the run; the second live
        # run spent three hours on SAMPLES after OFFER had already decided
        # there would be no coupon, and the log said nothing.
        print(f"{label}: {result.verdict} (exit {code})", file=sys.stderr, flush=True)
        if code >= 2 and args.stop_on_failure:
            break

    worst = max((r.exit_code for r in results), default=0)
    verdict = {0: "OK", 1: "PARTIAL"}.get(worst, "FAILED")

    config = SofaConfig.from_env()
    summary = {
        "stage": "PIPELINE",
        "verdict": verdict,
        "run_id": run_id,
        "metrics": {
            "stages": [
                {"stage": r.stage, "label": r.label, "verdict": r.verdict}
                for r in results
            ]
        },
        "output_path": str(Path(config.runs_dir) / args.date),
    }
    print(f"SOFA_SUMMARY: {json.dumps(summary)}", flush=True)
    return 0 if verdict == "OK" else (1 if verdict == "PARTIAL" else 2)


if __name__ == "__main__":
    sys.exit(main())
