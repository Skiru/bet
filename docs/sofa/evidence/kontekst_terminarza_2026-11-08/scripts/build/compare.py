"""F7 comparison: installed curve (the file days >= 11-07 read) vs control (no
flag) vs --schedule-term, per key. Read-only. -> compare.json + stdout summary."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path("/Users/mkoziol/projects/bet")
F7 = REPO / "data/refit_2026-11-08_schedule/f7"
INSTALLED = REPO / "config/sofa_confidence_calibration.next.2026-11-07.json"
SIM_INSTALLED = REPO / "config/sofa_football_sim_curves.json"


def installed_curve(doc: dict[str, Any], ck: str) -> dict[str, Any] | None:
    klass, _, key = ck.rpartition(":")
    sec = doc["by_class"].get(klass, {}) if klass else doc
    return (sec.get("by_market_direction") or {}).get(key)


def flat(c: dict[str, Any] | None) -> dict[str, tuple[int, float]]:
    return {b: (int(e["n"]), float(e["realised_lo95"])) for b, e in (c or {}).items()}


def diff(a: dict[str, tuple[int, float]], b: dict[str, tuple[int, float]]) -> float | None:
    common = set(a) & set(b)
    if not common:
        return None
    return max(abs(a[x][1] - b[x][1]) for x in common)


def gate_of(doc: dict[str, Any], ck: str) -> Any:
    g = (doc.get("gate") or {}).get(ck) or {}
    return g.get("pass")


def fitted_final(doc: dict[str, Any], ck: str) -> dict[str, Any] | None:
    if "final_curves_all_keys" in doc:
        return doc["final_curves_all_keys"].get(ck)
    return installed_curve(doc, ck)


def compare(group: str, cdir: Path, keys_from: str) -> list[dict[str, Any]]:
    ctrl = json.loads((cdir / "control" / keys_from).read_text())
    term = json.loads((cdir / "term" / keys_from).read_text())
    inst = json.loads(INSTALLED.read_text())
    out = []
    keys = sorted(set(ctrl.get("gate") or {}) | set(term.get("gate") or {}))
    for ck in keys:
        i, c, t = (flat(installed_curve(inst, ck)), flat(fitted_final(ctrl, ck)),
                   flat(fitted_final(term, ck)))
        out.append({
            "group": group, "key": ck, "installed": bool(i),
            "pass_control": gate_of(ctrl, ck), "pass_term": gate_of(term, ck),
            "max_dlo95_control_vs_installed": diff(c, i),
            "max_dlo95_term_vs_control": diff(t, c),
            "n_control": sum(v[0] for v in c.values()),
            "n_term": sum(v[0] for v in t.values()),
            "buckets": {b: {"installed": i.get(b), "control": c.get(b), "term": t.get(b)}
                        for b in sorted(set(i) | set(c) | set(t))},
            "gate_control": (ctrl.get("gate") or {}).get(ck),
            "gate_term": (term.get("gate") or {}).get(ck),
        })
    return out


def compare_sim() -> list[dict[str, Any]]:
    inst = json.loads(SIM_INSTALLED.read_text())
    ctrl = json.loads((F7 / "sim/control/curves.json").read_text())
    term = json.loads((F7 / "sim/term/curves.json").read_text())
    out = []
    for klass in ("", "women"):
        def sec(d: dict[str, Any]) -> dict[str, Any]:
            return d["by_class"].get(klass, {}) if klass else d
        for name in ("by_market_direction", "thin_by_market_direction"):
            keys = sorted(set(sec(inst).get(name) or {}) | set(sec(ctrl).get(name) or {})
                          | set(sec(term).get(name) or {}))
            for k in keys:
                i = flat((sec(inst).get(name) or {}).get(k))
                c = flat((sec(ctrl).get(name) or {}).get(k))
                t = flat((sec(term).get(name) or {}).get(k))
                out.append({"group": "sim", "section": name,
                            "key": f"{klass}:{k}" if klass else k,
                            "max_dlo95_control_vs_installed": diff(c, i),
                            "max_dlo95_term_vs_control": diff(t, c),
                            "n_installed": sum(v[0] for v in i.values()),
                            "n_control": sum(v[0] for v in c.values()),
                            "n_term": sum(v[0] for v in t.values()),
                            "buckets": {b: {"installed": i.get(b), "control": c.get(b),
                                            "term": t.get(b)}
                                        for b in sorted(set(i) | set(c) | set(t))}})
    return out


def main() -> None:
    which = sys.argv[1:] or ["dc", "x1015", "x1105", "score1015", "score1105", "inc", "sim"]
    res: dict[str, Any] = {}
    spec = {"dc": ("dc", F7 / "dc", "curves.json"),
            "x1015": ("1x2_dnb_1015", F7 / "x1x2_1015", "curves.json"),
            "x1105": ("1x2_dnb_1105", F7 / "x1x2_1105", "curves.json"),
            "score1015": ("score_1015", F7 / "score_1015", "football_score_markets/curves.json"),
            "score1105": ("score_1105", F7 / "score_1105", "football_score_markets/curves.json"),
            "inc": ("incidents", F7 / "inc", "football_incidents/curves.json")}
    for w in which:
        if w == "sim":
            res["sim"] = compare_sim()
        else:
            res[w] = compare(*spec[w])
    (F7 / ("compare_" + "_".join(which) + ".json")).write_text(json.dumps(res, indent=1))
    for w, rows in res.items():
        print(f"== {w}: {len(rows)} keys")
        for r in rows:
            if w == "inc" and not r["key"].startswith(("first_goal", "women:first_goal")):
                print(f"  {r['key']}: term-vs-control {r['max_dlo95_term_vs_control']}")
                continue
            if w.startswith("score"):
                continue
            print(f"  {r['key']}: inst={r.get('installed', r.get('n_installed'))} "
                  f"pass c/t={r.get('pass_control')}/{r.get('pass_term')} "
                  f"n c/t={r['n_control']}/{r['n_term']} "
                  f"max|dlo95| c-vs-inst={r['max_dlo95_control_vs_installed']} "
                  f"t-vs-c={r['max_dlo95_term_vs_control']}")
        if w.startswith("score"):
            moved = [r for r in rows if (r["max_dlo95_term_vs_control"] or 0) > 0]
            flips = [r["key"] for r in rows if r["pass_control"] != r["pass_term"]]
            print(f"  keys {len(rows)}; term moved {len(moved)}; max t-vs-c "
                  f"{max((r['max_dlo95_term_vs_control'] or 0) for r in rows):.4f}; "
                  f"max c-vs-inst {max((r['max_dlo95_control_vs_installed'] or 0) for r in rows):.4f}; "
                  f"pass c {sum(bool(r['pass_control']) for r in rows)} "
                  f"t {sum(bool(r['pass_term']) for r in rows)}; flips {flips}")


if __name__ == "__main__":
    main()
