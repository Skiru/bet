"""Compose the staged football calibration for the schedule term (F7 step 26).

Copies config/sofa_confidence_calibration.next.2026-11-07.json and replaces
ONLY the curves of epochs.SCHEDULE_TERM_MARKETS that file holds, each from the
--schedule-term refit of the same fitter and window it was installed from
(new_market_curves_fitted_from). A key whose term refit fails its own gate on the
window it was installed from is REMOVED (no curve: its legs read their own
settled lines or nothing - never the uncorrected curve on corrected p;
operator 2026-11-09 "jezeli poprawnie ale nie ma wartosci to wyczysc";
staged_change.removed_keys). Every other key
is byte-identical. Writes the dated .next.<D>.json and the simulator's dated
staged file. Never touches an installed or an earlier staged file.

    PYTHONPATH=src:. .venv/bin/python data/refit_2026-11-08_schedule/f7/compose_staged.py --day 2026-11-10 [--write]
"""

import argparse
import copy
import json
import sys
from pathlib import Path

from bet.sofa import epochs

REPO = Path(__file__).resolve().parents[3]
F7 = REPO / "data/refit_2026-11-08_schedule/f7"
BASE = REPO / "config/sofa_confidence_calibration.next.2026-11-07.json"
SIM_BASE = REPO / "config/sofa_football_sim_curves.json"


def mk(key: str) -> str:
    return key.split(":")[-1].split("|")[0].split("@")[0]


def source_for(prov: dict) -> Path:
    group = prov.get("group")
    if group == "double_chance":
        return F7 / "dc/term/curves.json"
    if group == "football_result_1x2_dnb":
        return F7 / "x1x2_1015/term/curves.json"
    if group == "football_incidents":
        return F7 / "inc/term/football_incidents/curves.json"
    if group == "football_score_markets":
        before = prov.get("before")
        if before == "2026-10-15":
            return F7 / "score_1015/term/football_score_markets/curves.json"
        if before == "2026-11-05":
            return F7 / "score_1105/term/football_score_markets/curves.json"
    raise SystemExit(f"no term source for provenance {prov}")


def curve_of(out: dict, cls: str | None, key: str):
    if cls is None:
        return out.get("by_market_direction", {}).get(key)
    return out.get("by_class", {}).get(cls, {}).get("by_market_direction", {}).get(key)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--effective-from", default=None,
                    help="exact start (operator moved it), else <day>T00:00:00Z")
    ap.add_argument("--label", default=None)
    ap.add_argument("--force", action="store_true", help="replace an existing output")
    a = ap.parse_args()
    eff = a.effective_from or f"{a.day}T00:00:00Z"
    base = json.loads(BASE.read_text())
    new = copy.deepcopy(base)
    nm = base["new_market_curves_fitted_from"]
    S = epochs.SCHEDULE_TERM_MARKETS
    replaced, kept, outs, paths, removed = [], [], {}, [], []
    slots = [(None, k) for k in base["by_market_direction"]]
    for cls, d in base.get("by_class", {}).items():
        slots += [(cls, k) for k in d.get("by_market_direction", {})]
    for sec in ("by_market", "thin_by_market_direction"):
        assert not [k for k in base.get(sec, {}) if mk(k) in S], sec
    for cls, key in slots:
        if mk(key) not in S:
            continue
        pk = key if cls is None else f"{cls}:{key}"
        prov = nm[pk]
        src = source_for(prov)
        out = outs.setdefault(src, json.loads(src.read_text()))
        gate = out.get("gate", {}).get(pk, {})
        cur = curve_of(out, cls, key)
        if cur is None or not gate.get("pass"):
            kept.append({"key": pk, "why": gate.get("why") or gate.get("reason") or "no curve",
                         "gap": gate.get("gap"), "gap_ci95": gate.get("gap_ci95"), "n": gate.get("n"),
                         "source": str(src.relative_to(REPO))})
            if cls is None:
                del new["by_market_direction"][key]
                removed.append(["by_market_direction", key])
            else:
                del new["by_class"][cls]["by_market_direction"][key]
                removed.append(["by_class", cls, "by_market_direction", key])
            del new["new_market_curves_fitted_from"][pk]
            removed.append(["new_market_curves_fitted_from", pk])
            continue
        if cls is None:
            new["by_market_direction"][key] = cur
            paths.append(["by_market_direction", key])
        else:
            new["by_class"][cls]["by_market_direction"][key] = cur
            paths.append(["by_class", cls, "by_market_direction", key])
        paths.append(["new_market_curves_fitted_from", pk])
        fp = copy.deepcopy(out["fitted_from"])
        fp["installed_from"] = str(src.relative_to(REPO))
        new["new_market_curves_fitted_from"][pk] = fp
        replaced.append(pk)
    new["effective_from"] = eff
    new["staged_change"] = {
        "label": a.label or f"od {a.day[5:]}",
        "effective_from": eff,
        "switch": "SCHEDULE_TERM",
        "rule": epochs.SCHEDULE_TERM,
        "base_file": str(BASE.relative_to(REPO)),
        # every path this file changes against the INSTALLED file: the base
        # staged file's own (11-07) plus the schedule term's
        "refitted_keys": base["staged_change"]["refitted_keys"]
        + [x for x in paths if x not in base["staged_change"]["refitted_keys"]],
        **({"added_keys": base["staged_change"]["added_keys"]}
           if "added_keys" in base["staged_change"] else {}),
        "base_staged_change": {k: v for k, v in base["staged_change"].items()
                               if k not in ("refitted_keys", "added_keys")},
        "schedule_term_keys": replaced,
        "removed_keys": removed,
        "removed_failing_gate": kept,
        "note": "only SCHEDULE_TERM_MARKETS curves refitted with --schedule-term on a DB copy "
                "(data/refit_2026-11-08_schedule/f7); every other key byte-identical to base_file",
    }
    print(f"replaced {len(replaced)} removed {len(kept)}")
    for k in kept:
        print("  REMOVED", k)
    # every other key unchanged
    def cur_of(doc: dict, c: str | None, k: str):
        sec = doc["by_market_direction"] if c is None else doc["by_class"][c]["by_market_direction"]
        return sec.get(k)
    changed = [(c, k) for c, k in slots if cur_of(base, c, k) != cur_of(new, c, k)]
    assert all(mk(k) in S for _, k in changed)
    print(f"curves changed {len(changed)}")
    sim_term = json.loads((F7 / "sim/term/curves.json").read_text())
    sim_term["effective_from"] = eff
    sim_term.setdefault("fitted_from", {})["installed_from"] = "data/refit_2026-11-08_schedule/f7/sim/term/curves.json"
    for f in epochs.SCHEDULE_TERM_FLOOR_EXCLUDED:
        for d in ("OVER", "UNDER"):
            k = f"{f}|{d}"
            sb = json.loads(SIM_BASE.read_text())
            assert sb["by_market_direction"].get(k) == sim_term["by_market_direction"].get(k), k
    out_cal = REPO / f"config/sofa_confidence_calibration.next.{a.day}.json"
    out_sim = REPO / f"config/sofa_football_sim_curves.next.{a.day}.json"
    if a.write:
        for p in (out_cal, out_sim):
            if p.exists() and not a.force:
                sys.exit(f"refuse: {p} exists")
        out_cal.write_text(json.dumps(new, indent=1, sort_keys=False) + "\n")
        out_sim.write_text(json.dumps(sim_term, indent=1, sort_keys=False) + "\n")
        print("wrote", out_cal.relative_to(REPO), out_sim.relative_to(REPO))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
