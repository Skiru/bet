"""E2E driver (plan step 33): run one sofa stage in-process on a scratch copy
of 2026-11-08 with epochs.SCHEDULE_TERM moved to 2026-11-08 00:00Z and the
.next.2026-11-10 staged curves read as effective from 2026-11-08 00:00Z.

Usage (env SOFA_RUNS_DIR / SOFA_DB_PATH / SOFA_NOW / SOFA_ICLOUD_KUPONY_DIR set
by the caller):
    driver.py on|off STAGE [extra argv...]
    driver.py on|off PLAN          # rebuild_plan.observe + build_plan, dry
Network is blocked (socket connect raises). Nothing here edits a tracked file.
"""
from __future__ import annotations

import importlib
import os
import socket
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path("/Users/mkoziol/projects/bet")
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]


def _blocked(*a, **k):  # noqa: ANN002, ANN003
    raise RuntimeError(f"E2E NETWORK BLOCKED: {a[:2]}")


socket.socket.connect = _blocked  # type: ignore[method-assign]
socket.socket.connect_ex = _blocked  # type: ignore[method-assign]
socket.create_connection = _blocked  # type: ignore[assignment]

SWITCH = datetime(2026, 11, 8, 0, 0, tzinfo=UTC)
STAGES = {
    "SHEET": "scripts.sofa.run_sheet",
    "COUPON": "scripts.sofa.run_coupon",
    "CONFIDENCE": "scripts.sofa.run_confidence",
    "COUPON_ASSEMBLY": "scripts.sofa.build_coupon",
    "PDF": "scripts.sofa.build_coupon_pdf",
    "DAY_STATUS": "scripts.sofa.day_status",
}


def patch_on() -> None:
    from bet.sofa import confidence, epochs, football_sim_curves

    epochs.SCHEDULE_TERM_FROM_UTC = SWITCH
    for mod in (confidence, football_sim_curves):
        orig = mod._staged_start

        def staged(path: Path, _orig=orig) -> datetime | None:  # noqa: ANN001
            if path.name.endswith(".next.2026-11-10.json"):
                return SWITCH
            return _orig(path)

        mod._staged_start = staged  # type: ignore[assignment]


def main() -> int:
    mode, stage, *extra = sys.argv[1:]
    assert mode in ("on", "off")
    runs = os.environ["SOFA_RUNS_DIR"]
    assert "refit_2026-11-08_schedule/e2e" in runs, runs
    assert "refit_2026-11-08_schedule/e2e" in os.environ["SOFA_DB_PATH"]
    if mode == "on":
        patch_on()
    from bet.sofa import confidence, epochs, football_sim_curves, timeutil

    at = timeutil.now()
    print(f"E2E mode={mode} now={at.isoformat()} "
          f"schedule_term_on={epochs.schedule_term('2026-11-08', at)} "
          f"calibration={confidence.calibration_path_for('2026-11-08', at).name} "
          f"sim_curves={football_sim_curves.path_for('2026-11-08', at).name}",
          file=sys.stderr, flush=True)
    if stage == "PLAN":
        from bet.sofa import rebuild_plan as rp
        from bet.sofa.config import SofaConfig

        cfg = SofaConfig.from_env()
        state = rp.observe(str(Path(runs).resolve()), "2026-11-08", at,
                           timedelta(minutes=cfg.price_max_age_min),
                           db_path=str(Path(cfg.db_path).resolve()))
        print("sheet_schedule_term(marker present):", state.sheet_schedule_term)
        plan = rp.build_plan(state, run_id="e2e-dry")
        for note in plan.notes:
            print("  note:", note)
        if plan.refusal:
            print("  REFUSAL:", plan.refusal)
        for i, s in enumerate(plan.steps, 1):
            print(f"  plan {i:2d}. {s.name:16s} {s.reason}")
        return 0
    module = importlib.import_module(STAGES[stage])
    sys.argv = [STAGES[stage], "--date", "2026-11-08", *extra]
    try:
        rc = module.main()
    except SystemExit as exc:
        rc = exc.code if isinstance(exc.code, int) else 0
    return int(rc or 0)


if __name__ == "__main__":
    sys.exit(main())
