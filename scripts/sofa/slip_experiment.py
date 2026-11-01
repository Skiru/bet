#!/usr/bin/env python3
"""The /kupon experiment harness: many chat slips of one day under a plan of
argument sets, a price-matched random control of each, and the next day's
grading - to judge and improve the /kupon prompt, never the coupon.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/slip_experiment.py run \\
        --date <d> --plan <plan.json> --out-dir runs/sofa/<d>/slip_experiment --round 1
    ... control --date <d> --plan <plan.json> --out-dir <dir> --round <n>
    ... settle  --date <d> --out-dir <dir> [--md-out <report.md>]

`run` calls build_slip.py once per config of the plan (`{"configs": [{"id":
"C01", "args": ["--target", "2", ...]}]}`) with `--json-out` / `--md-out` /
`--read-set-dir` under `<out-dir>/r<round>/`, then unions every config's
read set per sport into `r<round>/union/read_set_slip_<sport>_<i>.json`
(chunks of `--chunk` legs, one analyst each; merge each with
`merge_reads.py --slip --read-set <chunk>`). Re-running round n+1 after the
merge gives the slips the analysts' reads produced (a refused leg replaced).

`control` draws, for each config's slips of that round, a random slip from
the same pool (same window, odds, sample and read filters, the coupon's
price - no re-ask) less the prompt's own legs, each leg priced within 5%
of the prompt's leg (10%, then 20% when none is found), one leg per match: the arm
"the pool without the prompt's choice" (seeded by the config id).

`settle` grades every leg of every round's slips, controls and reserves from
`13_results.json` (`result_key`), reads the leg's last pre-start Superbet
price from `closing.jsonl` (football / tennis), and writes a JSON + Polish
markdown report: slips won / lost / refund / unknown beside their measured
chance and 1/price product, legs' hit rate beside mean 1/odds, the price
move to the close, the analysts' refused legs beside their replacements.
A slip's return is reported at the product of its legs' prices after the
12% tax - a measurement of the arm, never a price of a slip.
Exit: 0 OK, 1 a config failed / legs ungraded, 2 bad arguments.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import os
import random
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_REPO / "src"), str(_REPO)]

from bet.sofa import slip_builder as sb  # noqa: E402
from bet.sofa.coupon_results import key_of  # noqa: E402
from bet.sofa.veto import load_reads, load_vetoes  # noqa: E402
from scripts.sofa.build_slip import window  # noqa: E402
from scripts.sofa.merge_reads import SLIP_READS, SLIP_VETOES  # noqa: E402

CHUNK = 10
CONTROL_TOL = (0.05, 0.10, 0.20)
CONTROL_TRIES = 20000
SKIP_ARGS = ("--md-out", "--json-out", "--read-set-dir", "--date", "--runs-dir")


def round_dir(out_dir: Path, rnd: int) -> Path:
    return out_dir / f"r{rnd}"


def load_plan(path: Path) -> list[dict[str, Any]]:
    configs = json.loads(path.read_text(encoding="utf-8"))["configs"]
    ids = [str(c["id"]) for c in configs]
    if len(set(ids)) != len(ids):
        raise ValueError("plan: config ids must be unique")
    for c in configs:
        if any(a in SKIP_ARGS for a in c["args"]):
            raise ValueError(f"plan {c['id']}: the harness sets {', '.join(SKIP_ARGS)}")
    return list(configs)


def leg_ident(leg: dict[str, Any]) -> str:
    return json.dumps(
        [
            leg.get(k)
            for k in (
                "sofascore_event_id",
                "market",
                "subject",
                "line",
                "direction",
                "period",
                "map_nr",
                "market_id",
            )
        ],
        default=str,
    )


def run(args: argparse.Namespace) -> int:
    configs = load_plan(Path(args.plan))
    base = round_dir(Path(args.out_dir), args.round)
    base.mkdir(parents=True, exist_ok=True)
    summary: list[dict[str, Any]] = []
    for c in configs:
        cid = str(c["id"])
        cmd = [
            sys.executable,
            str(_REPO / "scripts/sofa/build_slip.py"),
            "--date",
            args.date,
            "--runs-dir",
            args.runs_dir,
            *map(str, c["args"]),
            "--md-out",
            str(base / f"{cid}.md"),
            "--json-out",
            str(base / f"{cid}.json"),
            "--read-set-dir",
            str(base / "rs" / cid),
        ]
        if args.no_network:
            cmd += ["--no-fresh-price", "--no-h2h", "--no-lineups"]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": f"{_REPO / 'src'}:{_REPO}"},
        )
        (base / f"{cid}.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
        rec_path = base / f"{cid}.json"
        rec = (
            json.loads(rec_path.read_text(encoding="utf-8"))
            if rec_path.exists()
            else {}
        )
        legs = [g for s in rec.get("slips", []) for g in s["legs"]]
        summary.append(
            {
                "id": cid,
                "args": c["args"],
                "exit": proc.returncode,
                "slips": len(rec.get("slips", [])),
                "legs": len(legs),
                "unread": sum(g["read"] != sb.READ_KEEP for g in legs),
                "first_line": proc.stdout.splitlines()[0] if proc.stdout else "",
            }
        )
        print(
            f"{cid} exit {proc.returncode}: {summary[-1]['slips']} kuponów, "
            f"{len(legs)} nóg, nieczytane {summary[-1]['unread']}"
        )
    written = union_read_sets(base, args.chunk)
    (base / "summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for path, n in written:
        print(f"do przeczytania: {path} ({n})")
    if not written:
        print("do przeczytania: nic")
    return 2 if any(s["exit"] == 2 for s in summary) else 0


def union_read_sets(base: Path, chunk: int) -> list[tuple[Path, int]]:
    """Every config's read set legs, deduplicated per sport, in chunks."""
    by_sport: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for path in sorted((base / "rs").glob("*/read_set_slip_*.json")):
        for leg in json.loads(path.read_text(encoding="utf-8")):
            by_sport[str(leg.get("sport") or "football")].setdefault(
                leg_ident(leg), leg
            )
    out_dir = base / "union"
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("read_set_slip_*.json"):
        stale.unlink()
    written: list[tuple[Path, int]] = []
    for sport, legs in sorted(by_sport.items()):
        # one match's legs stay in one chunk: an analyst reads a match whole
        by_match: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for leg in legs.values():
            by_match[leg.get("sofascore_event_id")].append(leg)
        chunks: list[list[dict[str, Any]]] = [[]]
        for match_legs in by_match.values():
            if chunks[-1] and len(chunks[-1]) + len(match_legs) > chunk:
                chunks.append([])
            chunks[-1].extend(match_legs)
        for i, part in enumerate(chunks, 1):
            path = out_dir / f"read_set_slip_{sport}_{i}.json"
            path.write_text(
                json.dumps(part, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            written.append((path, len(part)))
    return written


def control(args: argparse.Namespace) -> int:
    configs = load_plan(Path(args.plan))
    base = round_dir(Path(args.out_dir), args.round)
    run_dir = Path(args.runs_dir) / args.date
    coupon = json.loads((run_dir / "11_coupon.json").read_text(encoding="utf-8"))
    for c in configs:
        cid = str(c["id"])
        rec_path = base / f"{cid}.json"
        if not rec_path.exists():
            print(f"{cid}: brak zapisu rundy {args.round}")
            continue
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        p = rec["params"]
        now = datetime.datetime.fromisoformat(rec["computed_at_utc"])
        pool, _ = sb.candidates(
            coupon.get("singles") or [],
            now,
            min_odds=float(p["min_odds"]),
            max_odds=float(p["max_odds"]),
            window=window(args.date, p.get("start_from"), p.get("start_to"), now),
            reads=load_reads(run_dir / "reads.json"),
            vetoes=load_vetoes(run_dir / "vetoes.json")
            + load_vetoes(run_dir / SLIP_VETOES),
            built_at=coupon.get("created_at_utc"),
            slip_reads=load_reads(run_dir / SLIP_READS),
            competitions=p.get("competition") or [],
            allow_no_sample=bool(p.get("allow_no_sample")),
        )
        rng = random.Random(int(hashlib.sha256(cid.encode()).hexdigest()[:12], 16))
        drawn: list[sb.Slip] = []
        # the prompt's own legs stay out: the control is the rest of the pool
        mine = {g["result_key"] for s in rec["slips"] for g in s["legs"]}
        pool = [x for x in pool if key_of(x.leg) not in mine]
        for s in rec["slips"]:
            got = draw(pool, [float(g["odds"]) for g in s["legs"]], rng)
            if got is not None:
                drawn.append(got)
        res = sb.Result(drawn, len(rec["slips"]), len(pool))
        out = sb.record(res, now=now, params={**p, "control_of": cid})
        (base / f"{cid}.control.json").write_text(
            json.dumps(out, indent=1, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        print(
            f"{cid}: kontrola {len(drawn)}/{len(rec['slips'])} kuponów "
            f"z puli {len(pool)}"
        )
    return 0


def draw(pool: list[sb.Leg], odds: list[float], rng: random.Random) -> sb.Slip | None:
    """A random slip from distinct matches, leg i priced within CONTROL_TOL of
    the prompt's leg i (the same price profile, a random choice)."""
    for tol in CONTROL_TOL:
        near = [[x for x in pool if abs(x.odds / o - 1) <= tol] for o in odds]
        if any(not legs for legs in near):
            continue
        for _ in range(CONTROL_TRIES):
            legs = [rng.choice(options) for options in near]
            if len({x.match_key for x in legs}) == len(legs):
                return sb.Slip(legs)
    return None


def load_results(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    path = run_dir / "13_results.json"
    if not path.exists():
        return {}, {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return dict(doc.get("legs") or {}), dict(doc.get("builders") or {})


def load_closing(run_dir: Path) -> dict[str, dict[str, Any]]:
    """The last pre-start official close per capture key."""
    out: dict[str, dict[str, Any]] = {}
    path = run_dir / "closing.jsonl"
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("variant") != "official" or r.get("odds_close") is None:
            continue
        if float(r.get("minutes_before") or -1) < 0:
            continue
        old = out.get(r["leg_key"])
        if old is None or float(r["minutes_before"]) < float(old["minutes_before"]):
            out[r["leg_key"]] = r
    return out


def closing_key(leg: dict[str, Any]) -> str:
    return (
        f"{leg['sofascore_event_id']}|{leg['market']}|{leg.get('subject') or ''}"
        f"|{leg['line']}|{leg['direction']}"
    )


def grade_leg(
    leg: dict[str, Any], results: dict[str, Any], closing: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    if leg.get("builder_legs"):
        parts = [grade_leg(b, results, closing) for b in leg["builder_legs"]]
        st = [p["status"] for p in parts]
        status = (
            "lost"
            if "lost" in st
            else "unknown"
            if "unknown" in st
            else "refund"
            if "refund" in st
            else "won"
        )
        return {"status": status, "clv": None}
    got = results.get(str(leg["result_key"])) or {}
    status = str(got.get("status") or "unknown")
    close = closing.get(closing_key(leg)) if leg.get("line") is not None else None
    clv = None
    if close is not None and close.get("odds_close"):
        clv = float(leg["odds"]) / float(close["odds_close"]) - 1
    return {
        "status": status,
        "clv": clv,
        "close_odds": None if close is None else close.get("odds_close"),
    }


def grade_slip(
    slip: dict[str, Any], results: dict[str, Any], closing: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    legs = [{**g, **grade_leg(g, results, closing)} for g in slip["legs"]]
    st = [g["status"] for g in legs]
    if "lost" in st:
        status, ret = "lost", -1.0
    elif "unknown" in st:
        status, ret = "unknown", None
    else:
        live = [g for g in legs if g["status"] == "won"]
        status = "refund" if not live else "won"
        ret = (
            (1 - sb.TAX) * math.prod(float(g["odds"]) for g in live) - 1
            if live
            else 0.0
        )
    return {
        "status": status,
        "return": ret,
        "chance": slip["chance"],
        "inv_product": 1 / float(slip["price_product"]),
        "legs": legs,
        "reached": slip.get("reached", True),
    }


def settle(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    run_dir = Path(args.runs_dir) / args.date
    results, _ = load_results(run_dir)
    closing = load_closing(run_dir)
    graded: list[dict[str, Any]] = []
    for path in sorted(out_dir.rglob("*.json")):
        if path.name == "summary.json":
            continue
        rec = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rec, dict) or rec.get("schema") != sb.SLIP_RECORD_SCHEMA:
            continue
        arm = "control" if path.name.endswith(".control.json") else "prompt"
        cid = path.name.split(".")[0]
        for kind in ("slips", "reserve"):
            for i, s in enumerate(rec[kind], 1):
                graded.append(
                    {
                        "round": path.parent.name,
                        "config": cid,
                        "arm": arm,
                        "kind": kind,
                        "slip": i,
                        "params": rec["params"],
                        **grade_slip(s, results, closing),
                    }
                )
    report = summarise(graded, args.date, bool(results))
    (out_dir / "settled.json").write_text(
        json.dumps(
            {"graded": graded, "summary": report["summary"]},
            indent=1,
            ensure_ascii=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    md = Path(args.md_out) if args.md_out else out_dir / "rozliczenie.md"
    md.write_text(report["md"], encoding="utf-8")
    print(report["md"])
    unknown = sum(g["status"] == "unknown" for g in graded)
    return 1 if unknown or not results else 0


def _final_round(graded: list[dict[str, Any]]) -> dict[str, str]:
    last: dict[str, str] = {}
    for g in graded:
        if g["arm"] == "prompt" and g["round"] > last.get(g["config"], ""):
            last[g["config"]] = g["round"]
    return last


def _arm_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    done = [r for r in rows if r["status"] in ("won", "lost")]
    legs = [g for r in rows for g in r["legs"]]
    leg_done = [g for g in legs if g["status"] in ("won", "lost")]
    clv = [float(g["clv"]) for g in legs if g.get("clv") is not None]
    return {
        "slips": len(rows),
        "won": sum(r["status"] == "won" for r in rows),
        "lost": sum(r["status"] == "lost" for r in rows),
        "refund": sum(r["status"] == "refund" for r in rows),
        "unknown": sum(r["status"] == "unknown" for r in rows),
        "chance_sum": sum(float(r["chance"]) for r in done),
        "inv_product_sum": sum(float(r["inv_product"]) for r in done),
        "return_mean": (
            sum(float(r["return"]) for r in rows if r["return"] is not None)
            / max(1, sum(r["return"] is not None for r in rows))
        ),
        "legs": len(legs),
        "legs_won": sum(g["status"] == "won" for g in leg_done),
        "legs_graded": len(leg_done),
        "legs_inv_odds_sum": sum(1 / float(g["odds"]) for g in leg_done),
        "clv_n": len(clv),
        "clv_mean": sum(clv) / len(clv) if clv else None,
    }


def summarise(
    graded: list[dict[str, Any]], date: str, have_results: bool
) -> dict[str, Any]:
    final = _final_round(graded)
    first = {c: "r1" for c in final}
    arms = {
        "prompt (runda końcowa)": [
            g
            for g in graded
            if g["arm"] == "prompt"
            and g["kind"] == "slips"
            and g["round"] == final[g["config"]]
        ],
        "prompt (runda 1, przed odczytem)": [
            g
            for g in graded
            if g["arm"] == "prompt" and g["kind"] == "slips" and g["round"] == "r1"
        ],
        "kontrola losowa (runda końcowa)": [
            g
            for g in graded
            if g["arm"] == "control" and g["round"] == final.get(g["config"])
        ],
    }
    summary = {k: _arm_stats(v) for k, v in arms.items()}
    per_config: dict[str, dict[str, Any]] = {}
    for cid, rnd in sorted(final.items()):
        per_config[cid] = {
            "prompt": _arm_stats(
                [
                    g
                    for g in graded
                    if g["config"] == cid
                    and g["arm"] == "prompt"
                    and g["kind"] == "slips"
                    and g["round"] == rnd
                ]
            ),
            "control": _arm_stats(
                [
                    g
                    for g in graded
                    if g["config"] == cid
                    and g["arm"] == "control"
                    and g["round"] == rnd
                ]
            ),
        }
    # legs the reads took out between round 1 and the final round
    r1 = {
        g["result_key"]: g
        for r in graded
        if r["arm"] == "prompt" and r["round"] == "r1" and r["kind"] == "slips"
        for g in r["legs"]
        if "result_key" in g
    }
    fin = {
        g["result_key"]: g
        for r in arms["prompt (runda końcowa)"]
        for g in r["legs"]
        if "result_key" in g
    }
    out_legs = [g for k, g in r1.items() if k not in fin]
    in_legs = [g for k, g in fin.items() if k not in r1]
    summary["wymienione_przez_odczyt"] = {
        "wypadly": _leg_stats(out_legs),
        "weszly": _leg_stats(in_legs),
    }
    lines = [f"# Eksperyment /kupon {date} - rozliczenie", ""]
    if not have_results:
        lines += [
            "**Brak `13_results.json` - dzień nierozliczony; najpierw "
            "/sofa-settle i record_results.py.**",
            "",
        ]
    lines += [
        "Zwrot = iloczyn kursów nóg × 0,88 − 1 na wygranej (pomiar ramienia, nie "
        "kurs kuponu Superbetu); noga zwrócona liczy się 1,0.",
        "",
        "| ramię | kupony | W | L | zwrot | ? | Σ szansa (W+L) | Σ 1/iloczyn (W+L) "
        "| śr. zwrot | nogi W/oc. | Σ 1/kurs nóg | CLV śr. (n) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, st in summary.items():
        if name == "wymienione_przez_odczyt":
            continue
        lines.append(_row(name, st))
    lines += [
        "",
        "## Per konfiguracja (runda końcowa)",
        "",
        "| config | ramię | kupony | W | L | zwrot | ? | Σ szansa | Σ 1/iloczyn "
        "| śr. zwrot "
        "| nogi W/oc. | Σ 1/kurs | CLV |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for cid, st in per_config.items():
        lines.append(f"| {cid} " + _row("prompt", st["prompt"])[1:])
        lines.append(f"| {cid} " + _row("kontrola", st["control"])[1:])
    w = summary["wymienione_przez_odczyt"]
    lines += [
        "",
        "## Odczyt analityków: nogi wymienione między rundą 1 a końcową",
        "",
        f"- wypadły: {w['wypadly']}",
        f"- weszły: {w['weszly']}",
        "",
        f"Konfiguracje: {', '.join(f'{c}={r}' for c, r in final.items())} "
        f"(runda 1 = {len(first)} konfiguracji).",
        "",
    ]
    return {"summary": {**summary, "per_config": per_config}, "md": "\n".join(lines)}


def _leg_stats(legs: list[dict[str, Any]]) -> dict[str, Any]:
    done = [g for g in legs if g["status"] in ("won", "lost")]
    return {
        "n": len(legs),
        "won": sum(g["status"] == "won" for g in done),
        "graded": len(done),
        "inv_odds_sum": round(sum(1 / float(g["odds"]) for g in done), 2),
    }


def _row(name: str, st: dict[str, Any]) -> str:
    clv = (
        "—"
        if st["clv_mean"] is None
        else f"{100 * st['clv_mean']:+.1f}% ({st['clv_n']})"
    )
    return (
        f"| {name} | {st['slips']} | {st['won']} | {st['lost']} | {st['refund']} "
        f"| {st['unknown']} | {st['chance_sum']:.2f} | {st['inv_product_sum']:.2f} "
        f"| {100 * st['return_mean']:+.1f}% | {st['legs_won']}/{st['legs_graded']} "
        f"| {st['legs_inv_odds_sum']:.2f} | {clv} |"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "control", "settle"):
        p = sub.add_parser(name)
        p.add_argument("--date", required=True)
        p.add_argument("--out-dir", required=True)
        p.add_argument("--runs-dir", default="runs/sofa")
        if name != "settle":
            p.add_argument("--plan", required=True)
            p.add_argument("--round", type=int, required=True)
        if name == "run":
            p.add_argument("--chunk", type=int, default=CHUNK)
            p.add_argument(
                "--no-network",
                action="store_true",
                help="no re-ask, no h2h / lineups (tests)",
            )
        if name == "settle":
            p.add_argument("--md-out", default=None)
    args = ap.parse_args(argv)
    try:
        return {"run": run, "control": control, "settle": settle}[args.cmd](args)
    except ValueError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
