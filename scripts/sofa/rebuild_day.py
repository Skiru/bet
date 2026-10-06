#!/usr/bin/env python3
"""The one rebuild command: a day's coupon from the artifacts on disk, in order.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <d> \\
        [--dry-run] [--skip-audits]

Plan 2026-10-05 production grade, F0.2. The plan is decided in
bet.sofa.rebuild_plan (offline, tested) from the files' ages and the clock:

1. freshness, only while the day is live: OFFER (run_offer.py
   --min-minutes-to-kickoff 20) when the open fixtures' oldest price would be
   STALE_PRICE by the time CONFIDENCE runs; SHADOW (run_shadow.py
   --horizon-h <to the farthest open start>) and CS2 when a sport price
   nears sport_day.MAX_PRICE_AGE or SHADOW skipped an event beyond its
   horizon; then ensure_bridge + SPORT_IDENTITY;
2. SHEET only when CONFIDENCE would refuse the sheet (epoch); COUPON
   (06_coupon.json, audit_coupon's input, not the coupon) when it is older
   than the sheet / vetoes / reads;
3. ensure_bridge + FIXTURE_CHECK, CONFIDENCE, SPORT_CONFIDENCE,
   COUPON_ASSEMBLY (build_coupon.py), PDF (build_coupon_pdf.py), then
   audit_variants.py and audit_coupon.py (--skip-audits leaves them out and
   says so).

Every step is a subprocess with the same command the docs use; each one's
output goes to runs/sofa/<d>/rebuild_<ts>.log and its SOFA_SUMMARY line is
read into a compact line here. A FAILED step stops the steps after it
(SKIPPED), except the bridge steps (ensure_bridge, FIXTURE_CHECK,
SPORT_IDENTITY - no bridge is UNVERIFIED / NOT_IDENTIFIED downstream,
nothing refused) and the sport snapshots (SHADOW, CS2 - only the sport legs
go STALE_PRICE) and COUPON (06 is not the coupon): those make the rebuild
PARTIAL. --dry-run prints the plan
and runs nothing.

Refuses SOFA_NOW (a frozen replay clock), like run_pipeline. Honours
SOFA_RUNS_DIR. Never runs SAMPLES, RESOLVE or a fit.

Exit: 0 OK, 1 PARTIAL, 2 FAILED.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import rebuild_plan as rp  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.timeutil import now  # noqa: E402

VERDICT = {0: "OK", 1: "PARTIAL"}


def summary_of(lines: list[str]) -> dict[str, Any] | None:
    """The step's own SOFA_SUMMARY: the last one that is not run_pipeline's
    PIPELINE wrapper (which carries only the verdicts), else the last one."""
    found: list[dict[str, Any]] = []
    for line in lines:
        if not line.startswith("SOFA_SUMMARY:"):
            continue
        try:
            doc = json.loads(line.split(":", 1)[1])
        except ValueError:
            continue
        if isinstance(doc, dict):
            found.append(doc)
    own = [d for d in found if d.get("stage") != "PIPELINE"]
    pick = own or found
    return pick[-1] if pick else None


def compact(summary: dict[str, Any] | None, limit: int = 8) -> str:
    """A step's scalar metrics, on one line."""
    if not summary:
        return "no SOFA_SUMMARY"
    metrics = summary.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {k: v for k, v in summary.items()
                   if k not in ("stage", "verdict", "output_path")}
    parts = [f"{k}={v}" for k, v in metrics.items()
             if isinstance(v, (int, float, str, bool)) or v is None][:limit]
    return " ".join(parts) or "-"


def unmatched_counts(lines: list[str]) -> dict[str, int]:
    """UNMATCHED_VETO / UNMATCHED_READ / UNMATCHED_READ_REQUEST lines of a
    step (stderr): a veto or read that did nothing must not pass in silence;
    the lines themselves are in the log."""
    out: dict[str, int] = {}
    for line in lines:
        if line.startswith("UNMATCHED_"):
            key = line.split(":", 1)[0]
            out[key] = out.get(key, 0) + 1
    return out


def overall(results: list[dict[str, Any]]) -> int:
    worst = 0
    for r in results:
        code = r["exit"]
        if r["verdict"] == "SKIPPED":
            code = 2
        elif r["soft"] and code >= 2:
            code = 1
        worst = max(worst, code)
    return worst


def run_step(step: rp.Step, env: dict[str, str], log: Path) -> tuple[int, list[str]]:
    argv = [sys.executable if a == rp.PY else a for a in step.argv]
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"\n===== {step.name}: {' '.join(step.argv)}\n")
        fh.flush()
        proc = subprocess.Popen(argv, cwd=_REPO, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        assert proc.stdout is not None
        lines: list[str] = []
        for line in proc.stdout:
            fh.write(line)
            lines.append(line.rstrip("\n"))
            if line.startswith(("REFUSED", "STAGE_EXCEPTION")):
                print(f"    {line.rstrip()}", flush=True)
        code = proc.wait()
    return code, lines


def main() -> int:
    if os.environ.get("SOFA_NOW"):
        print("REFUSED: SOFA_NOW is set (a frozen replay clock); a rebuild runs on "
              "the live clock - unset it", file=sys.stderr)
        return 2
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", default=now().strftime("%Y-%m-%d"))
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan and its reasons; run nothing")
    ap.add_argument("--skip-audits", action="store_true",
                    help="leave out audit_variants / audit_coupon "
                    "(named in the summary)")
    args = ap.parse_args()

    config = SofaConfig.from_env()
    runs_dir = str(Path(config.runs_dir).resolve())
    at = now()
    run_id = "rebuild-" + uuid.uuid4().hex[:8]
    state = rp.observe(runs_dir, args.date, at, timedelta(
        minutes=config.price_max_age_min))
    plan = rp.build_plan(state, run_id=run_id, skip_audits=args.skip_audits)

    print(f"REBUILD {args.date} epoch={plan.epoch} sports_on_coupon="
          f"{plan.sports_on_coupon} runs_dir={runs_dir} now={at.isoformat()}",
          flush=True)
    for note in plan.notes:
        print(f"  note: {note}", flush=True)
    for i, step in enumerate(plan.steps, 1):
        print(f"  plan {i:2d}. {step.name:16s} {step.reason}", flush=True)
        print(f"            $ {' '.join(step.argv)}", flush=True)

    base: dict[str, Any] = {
        "stage": "REBUILD", "date": args.date, "run_id": run_id,
        "epoch": plan.epoch, "notes": plan.notes,
        "state": rp.state_summary(state),
        "output_path": str(Path(runs_dir) / args.date),
    }
    if plan.refusal:
        print(f"REFUSED: {plan.refusal}", file=sys.stderr, flush=True)
        print("SOFA_SUMMARY: " + json.dumps(
            {**base, "verdict": "FAILED", "refusal": plan.refusal}), flush=True)
        return 2
    if args.dry_run:
        print("SOFA_SUMMARY: " + json.dumps(
            {**base, "verdict": "DRY_RUN",
             "plan": [{"step": s.name, "reason": s.reason,
                       "argv": list(s.argv), "soft": s.soft}
                      for s in plan.steps]}), flush=True)
        return 0

    env = dict(os.environ)
    env["SOFA_RUNS_DIR"] = runs_dir
    env["SOFA_RUN_ID"] = run_id
    env["PYTHONPATH"] = os.pathsep.join(
        [str(_REPO / "src"), str(_REPO)]
        + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    log = Path(runs_dir) / args.date / f"rebuild_{at.strftime('%Y%m%dT%H%M%SZ')}.log"
    print(f"log: {log}", flush=True)
    results: list[dict[str, Any]] = []
    stopped_by: str | None = None
    for i, step in enumerate(plan.steps, 1):
        if stopped_by is not None:
            results.append({"step": step.name, "verdict": "SKIPPED", "exit": None,
                            "soft": step.soft, "summary": None})
            print(f"[{i}/{len(plan.steps)}] {step.name}: SKIPPED (after "
                  f"{stopped_by} FAILED)", flush=True)
            continue
        print(f"[{i}/{len(plan.steps)}] {step.name} ... ({step.reason})", flush=True)
        code, lines = run_step(step, env, log)
        summary = summary_of(lines)
        verdict = VERDICT.get(code, "FAILED")
        unmatched = unmatched_counts(lines)
        results.append({"step": step.name, "verdict": verdict, "exit": code,
                        "soft": step.soft, "unmatched": unmatched,
                        "summary": summary and {k: summary.get(k) for k in
                                                ("verdict", "metrics", "output_path")}})
        print(f"[{i}/{len(plan.steps)}] {step.name}: {verdict} (exit {code}) "
              f"{compact(summary)}", flush=True)
        if unmatched:
            print(f"    {' '.join(f'{k}={v}' for k, v in unmatched.items())} "
                  "(the lines are in the log)", flush=True)
        if code >= 2 and not step.soft:
            stopped_by = step.name
        elif code >= 2:
            print(f"    {step.name} FAILED but is soft: the rebuild goes on "
                  "(PARTIAL)", flush=True)
    worst = overall(results)
    print("SOFA_SUMMARY: " + json.dumps(
        {**base, "verdict": {0: "OK", 1: "PARTIAL"}.get(worst, "FAILED"),
         "log": str(log),
         "steps": [{"step": r["step"], "verdict": r["verdict"], "exit": r["exit"],
                    **({"unmatched": r["unmatched"]} if r.get("unmatched") else {})}
                   for r in results],
         "step_summaries": {r["step"]: r["summary"] for r in results
                            if r["summary"]}}), flush=True)
    return worst


if __name__ == "__main__":
    sys.exit(main())
