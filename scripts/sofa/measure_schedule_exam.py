"""The ONE exam of the schedule / fatigue term (pre-registration
docs/sofa/evidence/schedule_context_prereg_2026-11-09.md, rule (c) P1-P6,
guards G1-G5; operationalisation: doprecyzowanie 8 of
docs/sofa/history/STAN_KONTEKST_TERMINARZA_2026-11-09.md).

Read-only evidence: nothing in config/ or the database is written.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_schedule_exam.py \\
        --spec-sha <commit> [--mode exam|fake] [--groups g1,g2]

`--spec-sha` is the commit holding the frozen coefficient files and the
measurement scripts; every pinned file is checked byte for byte against it
(G1). Mode `exam` opens the sealed exam outcomes (G2) and appends one line to
docs/sofa/evidence/schedule_context_exam_log.md; it refuses to run when a line
of this study is already there. Mode `fake` draws every exam outcome from the
base arm: a dry run of the machinery, never logged, never a verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import numpy.typing as npt

REPO = Path(__file__).resolve().parents[2]
STUDY = "schedule_context_2026-11"
EXAM_LOG = REPO / "docs/sofa/evidence/schedule_context_exam_log.md"
EVIDENCE = REPO / "docs/sofa/evidence/kontekst_terminarza_2026-11-08"
SCRIPTS = EVIDENCE / "scripts"
SCRATCH = REPO / "data/refit_2026-11-08_schedule"
F0_SHA = "2b291085"
MODULE = "src/bet/sofa/schedule_features.py"
# frozen files used at run time (scratch) -> their committed copy
FROZEN = {
    "fb_frozen.json": "frozen/fb_frozen.json",
    "fr_frozen.json": "frozen/fr_frozen.json",
    "tennis/tw_frozen.json": "frozen/tw_frozen.json",
    "season_phase_dev.json": "frozen/season_phase_dev.json",
}
GROUP_ORDER = ("goals", "football_result", "tennis_winner", "tennis_games_sets")
REPS = 2000
ALPHA = 0.05
P3_UPPER = 2e-4
P4_SLACK = 0.005
P5_GROUP_UPPER = 1e-4
P5_STRATUM_UPPER = 5e-4
P5_MIN_STRATUM_ROWS = 2000

F64 = npt.NDArray[np.float64]


# --------------------------------------------------------------------------
# statistics (pure; tested in tests/sofa/test_measure_schedule_exam.py)
def cluster_boot(
    num: F64,
    den: F64,
    factors: list[tuple[int, list[npt.NDArray[np.int64]]]],
    reps: int = REPS,
    seed: int = 7,
) -> F64:
    """Pigeonhole bootstrap: each factor's clusters drawn with replacement
    (multinomial counts); a unit's weight = product of its clusters' counts
    (a factor with two index arrays - tennis players - multiplies both).
    Replicate = sum(w num) / sum(w den)."""
    rng = np.random.default_rng(seed)
    out = np.empty(reps)
    for k in range(reps):
        w = np.ones(len(num))
        for ncl, idxs in factors:
            wc = rng.multinomial(ncl, np.full(ncl, 1.0 / ncl))
            for ix in idxs:
                w = w * wc[ix]
        d = float((w * den).sum())
        out[k] = float((w * num).sum()) / d if d > 0 else 0.0
    return out


def one_sided_p(boot: F64) -> float:
    """Share of replicates >= 0 (H0: Delta >= 0), floored at 1 / reps."""
    return max(float((boot >= 0).mean()), 1.0 / len(boot))


def holm(pvals: dict[str, float], alpha: float = ALPHA) -> dict[str, dict[str, Any]]:
    """Holm step-down: sorted ascending, reject while p_(i) <= alpha / (K - i);
    the level each group is judged at is returned with the decision."""
    k = len(pvals)
    out: dict[str, dict[str, Any]] = {}
    still = True
    for i, (g, p) in enumerate(sorted(pvals.items(), key=lambda t: (t[1], t[0]))):
        level = alpha / (k - i)
        reject = still and p <= level
        still = reject
        out[g] = {"p": p, "level": level, "reject": reject}
    return out


def per_match(
    row_match: npt.NDArray[np.int64],
    values: F64,
    mask: npt.NDArray[np.bool_],
    n_match: int,
) -> tuple[F64, F64]:
    num = np.bincount(row_match[mask], weights=values[mask], minlength=n_match).astype(
        float
    )
    den = np.bincount(row_match[mask], minlength=n_match).astype(float)
    return num, den


@dataclass(frozen=True)
class Bound:
    point: float
    upper95: float
    n: int


def row_bound(
    row_match: npt.NDArray[np.int64],
    values: F64,
    mask: npt.NDArray[np.bool_],
    n_match: int,
    factors: list[tuple[int, list[npt.NDArray[np.int64]]]],
    seed: int,
) -> Bound:
    num, den = per_match(row_match, values, mask, n_match)
    n = int(mask.sum())
    if n == 0:
        return Bound(float("nan"), float("nan"), 0)
    boot = cluster_boot(num, den, factors, seed=seed)
    return Bound(float(num.sum() / den.sum()), float(np.quantile(boot, 0.95)), n)


def p4_check(cb: F64, ct: F64, y: F64) -> dict[str, Any]:
    sel = cb >= 0.70
    if not sel.any():
        return {"pass": False, "rows": 0, "note": "no baseline row >= 0.70"}
    r = float(y[sel].mean())
    gap_b = abs(r - float(cb[sel].mean()))
    gap_t = abs(r - float(ct[sel].mean()))
    st = ct >= 0.70
    return {
        "pass": gap_t <= gap_b + P4_SLACK,
        "rows": int(sel.sum()),
        "realised": r,
        "mean_cb": float(cb[sel].mean()),
        "mean_ct": float(ct[sel].mean()),
        "gap_base": gap_b,
        "gap_treat": gap_t,
        "treat_selected": {
            "rows": int(st.sum()),
            "realised": float(y[st].mean()) if st.any() else None,
            "mean_ct": float(ct[st].mean()) if st.any() else None,
        },
    }


def verdict(p1: bool, p2: bool, p3: bool, p4: bool, p5: bool, p6: bool | None) -> str:
    return "PASS" if (p1 and p2 and p3 and p4 and p5 and p6 is True) else "NOT_PASSED"


# --------------------------------------------------------------------------
# guards
def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob_sha256(sha: str, rel: str) -> str:
    out = subprocess.run(
        ["git", "show", f"{sha}:{rel}"], cwd=REPO, capture_output=True, check=True
    )
    return hashlib.sha256(out.stdout).hexdigest()


def check_spec(sha: str) -> dict[str, str]:
    """G1: the spec commit exists and holds byte-identical copies of the frozen
    files used at run time, of the scripts imported and of the feature module."""
    subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=REPO, check=True)
    hashes: dict[str, str] = {}
    for used, committed in FROZEN.items():
        rel = str((EVIDENCE / committed).relative_to(REPO))
        h_used, h_com = sha256(SCRATCH / used), git_blob_sha256(sha, rel)
        if h_used != h_com:
            raise SystemExit(f"G1: {used} differs from {rel} at {sha}")
        hashes[used] = h_used
    for f in sorted(SCRIPTS.glob("*.py")):
        rel = str(f.relative_to(REPO))
        if sha256(f) != git_blob_sha256(sha, rel):
            raise SystemExit(f"G1: {rel} differs from {sha}")
        hashes[rel] = sha256(f)
    if sha256(REPO / MODULE) != git_blob_sha256(sha, MODULE):
        raise SystemExit(f"G1: {MODULE} differs from {sha}")
    hashes[MODULE] = sha256(REPO / MODULE)
    return hashes


def exam_already_run(log: Path = EXAM_LOG) -> bool:
    return log.exists() and any(
        f"| {STUDY} |" in ln for ln in log.read_text().splitlines()
    )


# --------------------------------------------------------------------------
def load_groups(mode: str, names: list[str]) -> dict[str, Any]:
    sys.path.insert(0, str(SCRIPTS))
    eg: ModuleType = importlib.import_module("exam_groups")
    for mod in ("exam_groups", "fb_analysis", "fr_analysis", "tw_analysis", "nbvec"):
        origin = Path(str(sys.modules[mod].__file__)).resolve().parent
        if origin != SCRIPTS.resolve():
            raise SystemExit(f"G1: {mod} imported from {origin}, not {SCRIPTS}")
    out: dict[str, Any] = {}
    games = (
        eg.group_tennis_games(mode)
        if {"tennis_games_sets", "tennis_winner"} & set(names)
        else None
    )
    if "goals" in names:
        out["goals"] = eg.group_goals(mode)
    if "football_result" in names:
        out["football_result"] = eg.group_football_result(mode)
    if "tennis_winner" in names:
        out["tennis_winner"] = eg.group_tennis_winner(mode, games)
    if "tennis_games_sets" in names and games is not None:
        tw = out.get("tennis_winner") or eg.group_tennis_winner(mode, None)
        games.other_groups["tennis_winner"] = {
            "row_match": tw.row_match,
            "row_diff": tw.row_diff,
            "clusters": tw.clusters,
        }
        out["tennis_games_sets"] = games
    return out


def evaluate(groups: dict[str, Any]) -> dict[str, Any]:
    res: dict[str, Any] = {}
    pvals: dict[str, float] = {}
    boots: dict[str, F64] = {}
    for i, (name, g) in enumerate(groups.items()):
        md = np.asarray(g.match_diff, dtype=float)
        boot = cluster_boot(md, np.ones(len(md)), g.clusters.factors, seed=100 + i)
        boots[name] = boot
        pvals[name] = one_sided_p(boot)
        n_match = len(md)
        allrows = np.ones(len(g.row_diff), dtype=bool)
        lines = g.lines
        lb = row_bound(
            lines.match,
            eg_ll(lines.ct, lines.y) - eg_ll(lines.cb, lines.y),
            np.ones(len(lines.y), dtype=bool),
            n_match,
            g.clusters.factors,
            200 + i,
        )
        strata = {}
        for s, mask in g.strata.items():
            b = row_bound(
                g.row_match,
                g.row_diff,
                np.asarray(mask, dtype=bool),
                n_match,
                g.clusters.factors,
                300 + i,
            )
            gate = b.n >= P5_MIN_STRATUM_ROWS
            strata[s] = {
                "point": b.point,
                "upper95": b.upper95,
                "rows": b.n,
                "gated": gate,
                "pass": (b.upper95 < P5_STRATUM_UPPER) if gate else None,
            }
        others = {}
        for o, v in g.other_groups.items():
            if isinstance(v, str):
                others[o] = {"pass": True, "note": v}
                continue
            om = np.asarray(v["row_match"])
            ob = row_bound(
                om,
                np.asarray(v["row_diff"], dtype=float),
                np.ones(len(om), dtype=bool),
                int(om.max()) + 1,
                v["clusters"].factors,
                400 + i,
            )
            others[o] = {
                "point": ob.point,
                "upper95": ob.upper95,
                "rows": ob.n,
                "pass": ob.upper95 < P5_GROUP_UPPER,
            }
        whole = row_bound(
            g.row_match, g.row_diff, allrows, n_match, g.clusters.factors, 500 + i
        )
        res[name] = {
            "info": g.info,
            "matches": n_match,
            "P1": {
                "delta": float(md.mean()),
                "p_one_sided": pvals[name],
                "q025": float(np.quantile(boot, 0.025)),
                "q975": float(np.quantile(boot, 0.975)),
            },
            "delta_per_row": {
                "point": whole.point,
                "upper95": whole.upper95,
                "rows": whole.n,
            },
            "P2": g.p2,
            "P3": {
                "point": lb.point,
                "upper95": lb.upper95,
                "rows": lb.n,
                "dropped": lines.dropped,
                "pass": bool(lb.point <= 0 and lb.upper95 < P3_UPPER),
            },
            "P4": p4_check(lines.cb, lines.ct, lines.y),
            "P5": {
                "strata": strata,
                "other_groups": others,
                "pass": all(v["pass"] is not False for v in strata.values())
                and all(v["pass"] for v in others.values()),
            },
            "P6": g.p6,
        }
    hm = holm(pvals)
    for name, r in res.items():
        h = hm[name]
        r["P1"].update(
            holm_level=h["level"],
            upper_at_level=float(np.quantile(boots[name], 1 - h["level"])),
            pass_=bool(h["reject"]),
        )
        r["verdict"] = verdict(
            r["P1"]["pass_"],
            bool(r["P2"]["material"]),
            r["P3"]["pass"],
            r["P4"]["pass"],
            r["P5"]["pass"],
            r["P6"].get("pass"),
        )
    return res


def eg_ll(p: F64, y: F64) -> F64:
    q = np.clip(p, 1e-6, 1 - 1e-6)
    return np.asarray(-(y * np.log(q) + (1 - y) * np.log(1 - q)), dtype=float)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec-sha", required=True)
    ap.add_argument("--mode", choices=("exam", "fake"), default="fake")
    ap.add_argument("--groups", default=",".join(GROUP_ORDER))
    ap.add_argument(
        "--out", help="result JSON (default: evidence dir for exam, scratch for fake)"
    )
    args = ap.parse_args(argv)
    names = [g for g in args.groups.split(",") if g]
    if args.mode == "exam":
        if exam_already_run():
            print(
                f"refused: {EXAM_LOG} already holds a line of {STUDY} (G2)",
                file=sys.stderr,
            )
            return 2
        if names != list(GROUP_ORDER):
            print(
                "refused: the exam runs every submitted group at once", file=sys.stderr
            )
            return 2
    if args.spec_sha == "none":
        if args.mode == "exam":
            print("refused: the exam needs --spec-sha (G1)", file=sys.stderr)
            return 2
        hashes: dict[str, str] = {}
    else:
        hashes = check_spec(args.spec_sha)
    started = datetime.now(UTC).isoformat(timespec="seconds")
    res = evaluate(load_groups(args.mode, names))
    doc = {
        "study": STUDY,
        "mode": args.mode,
        "spec_sha": args.spec_sha,
        "f0_sha": F0_SHA,
        "started_utc": started,
        "finished_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "hashes": hashes,
        "K": len(names),
        "groups": res,
    }
    out = (
        Path(args.out)
        if args.out
        else (
            EVIDENCE / "exam_result.json"
            if args.mode == "exam"
            else SCRATCH / "exam_fake_result.json"
        )
    )
    out.write_text(json.dumps(doc, indent=1, default=float) + "\n")
    summary = ", ".join(f"{g} {r['verdict']}" for g, r in res.items())
    if args.mode == "exam":
        with EXAM_LOG.open("a") as f:
            if f.tell() == 0:
                f.write(
                    "# Log egzaminu: kontekst terminarza "
                    "(G2; jedna linia na badanie)\n\n"
                    "| UTC | badanie | spec SHA | F0 | sha256 modułu | werdykty |\n"
                    "|---|---|---|---|---|---|\n"
                )
            f.write(
                f"| {started} | {STUDY} | {args.spec_sha} | {F0_SHA} | "
                f"{hashes[MODULE][:16]} | {summary} |\n"
            )
    print(
        json.dumps(
            {g: {"verdict": r["verdict"], "P1": r["P1"]} for g, r in res.items()},
            indent=1,
            default=float,
        )
    )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
