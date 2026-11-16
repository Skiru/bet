#!/usr/bin/env python3
"""Does the "chwiejna" (shaky) stability label pick legs that realise below
their price? T-STABILITY-LABEL-RETRO (pre-registered in
docs/sofa/evidence/chwiejna_noga_2026-11-16.md, section A) and the forward
test T-STABILITY-LABEL-FORWARD (the analysts' own `stability` field).

    # 1. the blind classifier input - no outcome ever written
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_stability_label.py \\
        build-input --from 2026-10-26 --to 2026-11-15 \\
        --out-dir data/stability_retro_2026-11-16/input --shards 10
    # 2. the measurement - joins the labels to the ledger's grades
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_stability_label.py \\
        measure --from 2026-10-26 --to 2026-11-15 \\
        --labels data/stability_retro_2026-11-16/labels.jsonl \\
        --pairs data/stability_retro_2026-11-16/pairs.jsonl [--md-out f]
    # forward: the label is the read's own `stability` field
    ... measure --from 2026-11-17 --to <d> --from-reads [--db-path <db>]

Unit: a pair (an analysis section, a leg of its match read in the same merge -
the read's `read_at_utc` = the section's `recorded_at_utc` and the same
author), the section merged before the leg's kickoff, the leg graded WIN /
LOSS in the day's 13_results.json (the ledger's grades). Main measure on the
KEEP pairs: (hit - 1/odds) of CHWIEJNA minus that of STABILNA, match
bootstrap. Read-only evidence (CLAUDE.md "Changing the pipeline" 1), never a
gate. Exit 0 OK, 1 labels missing / PARTIAL, 2 bad arguments.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.coupon_results import is_measured, key_of  # noqa: E402

Row = dict[str, Any]
Mapping_ = dict[str, Any]

STABLE, SHAKY, NO_BASIS = "STABILNA", "CHWIEJNA", "BRAK_PODSTAW"
LABELS = (STABLE, SHAKY, NO_BASIS)
CATEGORIES = ("FORMA", "SKŁAD", "ROTACJA", "MOTYWACJA", "ZMIENNOŚĆ", "DANE", "INNE")
DEV_TO = "2026-11-05"          # A3: dev = kickoff <= 11-05, hold-out after
HOLDOUT_MIN_SHAKY = 150         # A5.3
BANDS = ((0.0, 1.10, "<1.10"), (1.10, 1.30, "1.10-1.30"), (1.30, 1.60, "1.30-1.60"),
         (1.60, 2.20, "1.60-2.20"), (2.20, 1e9, ">=2.20"))
SOURCES = (("coupon", "analyses.json", "reads.json"),
           ("slip", "analyses_slip.json", "reads_slip.json"))


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _days(first: str, last: str) -> list[str]:
    a, b = date.fromisoformat(first), date.fromisoformat(last)
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def read_key(r: Mapping_) -> tuple[Any, ...]:
    """(event, market, period, subject, line, direction) - one leg as a read
    names it (a measured sport's `market` is the leg's family)."""
    line = r.get("line")
    return (int(r["sofascore_event_id"]), str(r.get("market") or ""),
            int(r.get("period") or 0), str(r.get("subject") or "").lower(),
            None if line is None else float(line), str(r.get("direction") or ""))



def leg_read_key(leg: Mapping_) -> tuple[Any, ...]:
    """The same key off a coupon leg (sport legs: family / side)."""
    if is_measured(leg):
        return read_key({**leg, "market": leg.get("family") or leg.get("market"),
                         "direction": leg.get("side") or leg.get("direction")})
    return read_key({**leg, "period": 0})


def band(odds: float) -> str:
    return next(name for lo, hi, name in BANDS if lo <= odds < hi)


def coupon_legs(day_dir: Path) -> dict[tuple[Any, ...], list[Mapping_]]:
    """The day's printed singles and read-removed legs by read key."""
    path = day_dir / "11_coupon.json"
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    out: dict[tuple[Any, ...], list[Mapping_]] = defaultdict(list)
    seen: set[str] = set()
    for removed, legs in ((False, doc.get("singles") or []),
                          (True, doc.get("removed_by_reads") or [])):
        for leg in legs:
            k = key_of(leg)
            if k in seen:
                continue
            seen.add(k)
            out[leg_read_key(leg)].append({**leg, "_key": k, "_removed": removed})
    return out


def pairs(runs_dir: str, days: Iterable[str]) -> tuple[list[Row], dict[str, int]]:
    """Every (section, leg) pair of A2 - without any outcome."""
    out: list[Row] = []
    skipped: dict[str, int] = defaultdict(int)
    for d in days:
        dd = Path(runs_dir) / d
        legs = coupon_legs(dd)
        if not legs:
            continue
        for kind, an_name, rd_name in SOURCES:
            an, rd = dd / an_name, dd / rd_name
            if not an.exists() or not rd.exists():
                continue
            events = json.loads(an.read_text(encoding="utf-8")).get("events") or {}
            by_merge: dict[tuple[int, str, str], list[Mapping_]] = defaultdict(list)
            for r in json.loads(rd.read_text(encoding="utf-8")):
                if r.get("read_at_utc"):
                    by_merge[(int(r["sofascore_event_id"]), str(r["author"]),
                              str(r["read_at_utc"]))].append(r)
            for eid, sections in events.items():
                for s in sections:
                    reads = by_merge.get((int(eid), str(s["author"]),
                                          str(s["recorded_at_utc"])), [])
                    if not reads:
                        skipped["section_without_merged_reads"] += 1
                        continue
                    sid = f"{d}|{kind}|{eid}|{s['author']}|{s['recorded_at_utc']}"
                    for r in reads:
                        cand = legs.get(read_key(r), [])
                        if len(cand) != 1:
                            skipped["leg_not_on_coupon" if not cand
                                    else "leg_ambiguous"] += 1
                            continue
                        leg = cand[0]
                        ko = leg.get("kickoff_utc")
                        if not ko:
                            skipped["no_kickoff"] += 1
                            continue
                        if _ts(str(s["recorded_at_utc"])) >= _ts(str(ko)):
                            skipped["section_at_or_after_kickoff"] += 1
                            continue
                        out.append({
                            "day": d, "kind": kind, "section_id": sid,
                            "event": int(eid), "author": s["author"],
                            "report": s.get("report"), "verdict": r["verdict"],
                            "stability": r.get("stability"),
                            "key": leg["_key"], "removed": leg["_removed"],
                            "sport": leg.get("sport") or "football",
                            "kickoff_utc": ko, "half": half(str(ko)),
                            "market": r.get("market"), "subject": r.get("subject"),
                            "line": r.get("line"), "direction": r.get("direction"),
                            "period": r.get("period"),
                            "superbet": superbet_words(leg),
                            "odds": leg.get("offered_odds"),
                        })
    return out, dict(skipped)


def superbet_words(leg: Mapping_) -> str:
    """The leg in Superbet's words ("market: selection")."""
    market = leg.get("superbet_market") or leg.get("market")
    return f"{market}: {leg.get('superbet_selection') or leg.get('direction')}"


def half(kickoff_utc: str) -> str:
    return "dev" if kickoff_utc[:10] <= DEV_TO else "holdout"


def section_texts(runs_dir: str, ids: set[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    cache: dict[str, Mapping_] = {}
    for sid in ids:
        d, kind, eid, author, rec = sid.split("|")
        name = "analyses.json" if kind == "coupon" else "analyses_slip.json"
        path = str(Path(runs_dir) / d / name)
        if path not in cache:
            cache[path] = json.loads(Path(path).read_text(encoding="utf-8"))
        for s in cache[path]["events"].get(eid, []):
            if s["author"] == author and s["recorded_at_utc"] == rec:
                out[sid] = s["markdown"]
                break
    return out


def build_input(runs_dir: str, days: list[str], out_dir: Path, shards: int) -> int:
    """The classifier's blind input: one JSON line per section with its legs
    (Superbet's words, line, direction, printed odds) - never an outcome, a
    verdict-independent label or anything after the kickoff. Pairs are
    sectioned by match and spread over `shards` files of about equal legs."""
    ps, skipped = pairs(runs_dir, days)
    # A2: only legs the ledger graded WIN / LOSS (a read-removed leg is
    # graded by graded_confidence at measure time) - the outcome itself is
    # never written to the input
    cache: dict[str, dict[str, Mapping_]] = {}
    ps = [p for p in ps if p["removed"] or (cache.setdefault(
        p["day"], grades(runs_dir, p["day"])).get(p["key"]) or {}).get(
            "outcome") in ("WIN", "LOSS")]
    by_section: dict[str, list[Row]] = defaultdict(list)
    for p in ps:
        by_section[p["section_id"]].append(p)
    texts = section_texts(runs_dir, set(by_section))
    records: list[Row] = []
    for i, sid in enumerate(sorted(by_section)):
        legs = by_section[sid]
        for j, p in enumerate(legs):
            p["leg_id"] = f"{i:05d}#{j}"
        records.append({
            "section_id": sid, "sport": legs[0]["sport"], "event_id": legs[0]["event"],
            "author": legs[0]["author"], "analysis": texts.get(sid, ""),
            "legs": [{"leg_id": p["leg_id"], "market": p["market"],
                      "subject": p["subject"], "line": p["line"],
                      "direction": p["direction"], "period": p["period"],
                      "superbet": p["superbet"], "odds": p["odds"]}
                     for p in legs],
        })
    # group a match's sections together, then fill the lightest shard
    by_match: dict[tuple[str, int], list[Row]] = defaultdict(list)
    for rec in records:
        by_match[(rec["section_id"].split("|")[0], rec["event_id"])].append(rec)
    loads = [0] * shards
    files: list[list[Row]] = [[] for _ in range(shards)]
    def weight(kv: tuple[tuple[str, int], list[Row]]) -> int:
        return -sum(len(r["legs"]) for r in kv[1])

    for _, recs in sorted(by_match.items(), key=weight):
        i = loads.index(min(loads))
        files[i].extend(recs)
        loads[i] += sum(len(r["legs"]) for r in recs)
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, recs in enumerate(files):
        with (out_dir / f"shard_{i:02d}.jsonl").open("w", encoding="utf-8") as f:
            for rec in recs:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    # the join file stays beside the input, outside every shard
    (out_dir.parent / "pairs.jsonl").write_text(
        "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in ps), encoding="utf-8")
    print(json.dumps({"pairs": len(ps), "sections": len(records), "shards": loads,
                      "skipped": skipped}, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------- measurement

def grades(runs_dir: str, day: str) -> dict[str, Mapping_]:
    path = Path(runs_dir) / day / "13_results.json"
    if not path.exists():
        return {}
    return dict(json.loads(path.read_text(encoding="utf-8")).get("legs") or {})


def removed_grades(runs_dir: str, day: str, db_path: str) -> dict[str, Mapping_]:
    """The read-removed legs as the ledger grades them (removed:reads)."""
    from scripts.sofa.record_results import graded_confidence
    out: dict[str, Mapping_] = {}
    for var in graded_confidence(runs_dir, day, db_path):
        if var["variant"] != "removed:reads":
            continue
        for pos in var["singles"]:
            o = str(pos.get("outcome"))
            out[key_of(pos["source"])] = {
                "outcome": {"WON": "WIN", "LOST": "LOSS"}.get(o, o),
                "odds": pos.get("odds") or pos["source"].get("offered_odds"),
                "confidence": pos["source"].get("confidence")}
    return out


def graded_rows(ps: list[Row], runs_dir: str, db_path: str | None = None) -> list[Row]:
    """The pairs graded WIN / LOSS by the day's 13_results.json (a removed
    leg: removed:reads, when `db_path` is given), with the printed odds and
    confidence."""
    cache: dict[str, dict[str, Mapping_]] = {}
    rcache: dict[str, dict[str, Mapping_]] = {}
    out: list[Row] = []
    for p in ps:
        if p["removed"]:
            if db_path is None:
                continue
            g = rcache.setdefault(p["day"], removed_grades(
                runs_dir, p["day"], db_path)).get(p["key"])
        else:
            g = cache.setdefault(p["day"], grades(runs_dir, p["day"])).get(p["key"])
        if not g or g.get("outcome") not in ("WIN", "LOSS") or not g.get("odds"):
            continue
        out.append({**p, "win": g["outcome"] == "WIN", "odds": float(g["odds"]),
                    "conf": float(g.get("confidence") or 0.0)})
    return out


def stats(rs: list[Row]) -> dict[str, float]:
    n = len(rs)
    if not n:
        return {"n": 0}
    return {"n": n, "matches": len({(r["day"], r["event"]) for r in rs}),
            "hit": sum(r["win"] for r in rs) / n,
            "price": sum(1 / r["odds"] for r in rs) / n,
            "conf": sum(r["conf"] for r in rs) / n,
            "vs_price": sum(r["win"] - 1 / r["odds"] for r in rs) / n,
            "vs_conf": sum(r["win"] - r["conf"] for r in rs) / n,
            "roi": sum((r["odds"] - 1) if r["win"] else -1.0 for r in rs) / n}


def _edge(rs: list[Row], field: str = "vs_price") -> float | None:
    return stats(rs).get(field) if rs else None


def diff(rs: list[Row], field: str = "vs_price") -> float | None:
    """field(CHWIEJNA) - field(STABILNA); None when a side is empty."""
    a = _edge([r for r in rs if r["label"] == SHAKY], field)
    b = _edge([r for r in rs if r["label"] == STABLE], field)
    return None if a is None or b is None else a - b


def stratified(rs: list[Row]) -> float | None:
    """A6: the band differences weighted by CHWIEJNA pairs in the band."""
    num = den = 0.0
    for _, _, name in BANDS:
        sub = [r for r in rs if band(r["odds"]) == name]
        d = diff(sub)
        w = sum(r["label"] == SHAKY for r in sub)
        if d is not None and w:
            num += w * d
            den += w
    return num / den if den else None


def bootstrap(rs: list[Row], f: Callable[[list[Row]], float | None], b: int = 2000,
              seed: int = 1) -> tuple[float, float] | None:
    by: dict[tuple[str, int], list[Row]] = defaultdict(list)
    for r in rs:
        by[(r["day"], r["event"])].append(r)
    keys = sorted(by)
    if not keys:
        return None
    rng = random.Random(seed)
    vals: list[float] = []
    for _ in range(b):
        v = f([x for k in rng.choices(keys, k=len(keys)) for x in by[k]])
        if v is not None:
            vals.append(v)
    if len(vals) < b * 0.9:
        return None
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]


def verdict(dev: list[Row], hold: list[Row],
            require_dev: bool = True) -> dict[str, Any]:
    """A5 (frozen): hold-out difference < 0 with the 95% upper bound < 0, the
    dev difference < 0, >= 150 CHWIEJNA pairs on the hold-out; A6's
    stratified hold-out difference < 0 is the extra condition for proposing
    a removal."""
    d_hold, d_dev = diff(hold), diff(dev)
    ci = bootstrap(hold, diff)
    n_shaky = sum(r["label"] == SHAKY for r in hold)
    strat = stratified(hold)
    dev_ok = not require_dev or (d_dev is not None and d_dev < 0)
    passed = (d_hold is not None and d_hold < 0 and ci is not None and ci[1] < 0
              and dev_ok and n_shaky >= HOLDOUT_MIN_SHAKY)
    return {"verdict": "PASSED" if passed else "NOT_PASSED",
            "holdout_diff": d_hold, "holdout_ci": ci, "dev_diff": d_dev,
            "dev_ci": bootstrap(dev, diff), "holdout_shaky": n_shaky,
            "holdout_stratified": strat, "min_shaky": HOLDOUT_MIN_SHAKY,
            "holdout_stratified_ci": bootstrap(hold, stratified),
            "removal_may_be_proposed": passed and strat is not None and strat < 0}


FORWARD_REQUIRED_SHAKY = 300  # T-STABILITY-LABEL-FORWARD required_n


def forward_cut(rows: list[Row],
                n: int = FORWARD_REQUIRED_SHAKY) -> tuple[list[Row], bool]:
    """The pairs up to the n-th CHWIEJNA pair's kickoff (kickoff order) and
    whether n was reached - the forward test is judged once on them."""
    rows = sorted(rows, key=lambda r: str(r["kickoff_utc"]))
    shaky = [r for r in rows if r["label"] == SHAKY]
    if len(shaky) < n:
        return rows, False
    edge = str(shaky[n - 1]["kickoff_utc"])
    return [r for r in rows if str(r["kickoff_utc"]) <= edge], True


def load_labels(path: Path) -> dict[str, Mapping_]:
    out: dict[str, Mapping_] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            x = json.loads(line)
            if x.get("stability") in LABELS:
                out[str(x["leg_id"])] = x
    return out


def labelled(runs_dir: str, days: list[str], labels: Path | None,
             pairs_file: Path | None) -> tuple[list[Row], dict[str, int]]:
    """Pairs with a label: the classifier's (by leg_id from the input's
    pairs.jsonl) or, forward, the read's own `stability`."""
    if labels is not None:
        assert pairs_file is not None
        ps = [json.loads(x) for x in pairs_file.read_text(encoding="utf-8").splitlines()
              if x.strip()]
        lab = load_labels(labels)
        missing = sum(p["leg_id"] not in lab for p in ps)
        ps = [{**p, "label": lab[p["leg_id"]]["stability"],
               "category": lab[p["leg_id"]].get("category")}
              for p in ps if p["leg_id"] in lab]
        return ps, {"unlabelled_pairs": missing}
    ps, skipped = pairs(runs_dir, days)
    out = [{**p, "label": p["stability"]} for p in ps if p.get("stability") in LABELS]
    skipped["pairs_without_stability"] = len(ps) - len(out)
    return out, skipped


def _pp(x: float | None) -> str:
    return "–" if x is None else f"{100 * x:+.1f}"


def _ci(c: tuple[float, float] | None) -> str:
    return "–" if c is None else f"[{100 * c[0]:+.1f}, {100 * c[1]:+.1f}]"


def table(title: str, groups: list[tuple[str, list[Row]]]) -> list[str]:
    out = [f"### {title}", "",
           "| grupa | etykieta | n | mecze | traf. | 1/kurs | pewność | traf.−1/kurs "
           "| traf.−pewność | ROI | Δ CH−ST (traf.−1/kurs) | 95% |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, rs in groups:
        for lab in LABELS:
            sub = [r for r in rs if r["label"] == lab]
            s = stats(sub)
            if not s["n"]:
                continue
            extra = ("", "")
            if lab == SHAKY:
                extra = (_pp(diff(rs)), _ci(bootstrap(rs, diff)))
            out.append(f"| {name} | {lab} | {s['n']} | {s['matches']} "
                       f"| {s['hit']:.3f} | "
                       f"{s['price']:.3f} | {s['conf']:.3f} | {_pp(s['vs_price'])} | "
                       f"{_pp(s['vs_conf'])} | {100 * s['roi']:+.1f}% "
                       f"| {extra[0]} | {extra[1]} |")
    return out + [""]


def report(rows: list[Row], removed: list[Row], v: dict[str, Any],
           meta: dict[str, Any]) -> str:
    dev = [r for r in rows if r["half"] == "dev"]
    hold = [r for r in rows if r["half"] == "holdout"]
    sports = sorted({r["sport"] for r in rows})
    out = [f"## Pomiar ({meta['from']}..{meta['to']}, pary KEEP rozliczone)", "",
           f"**Werdykt A5: {v['verdict']}** — hold-out Δ {_pp(v['holdout_diff'])} pp "
           f"{_ci(v['holdout_ci'])}, dev Δ {_pp(v['dev_diff'])} pp {_ci(v['dev_ci'])}, "
           f"CHWIEJNA na hold-oucie {v['holdout_shaky']} (min {v['min_shaky']}); "
           f"stratyfikowana po pasmach (A6) {_pp(v['holdout_stratified'])} pp "
           f"{_ci(v['holdout_stratified_ci'])}; wniosek o usuwanie możliwy: "
           f"{'tak' if v['removal_may_be_proposed'] else 'nie'}.", "",
           f"Pominięte: {json.dumps(meta['skipped'], ensure_ascii=False)}", ""]
    out += table("Razem", [("dev", dev), ("hold-out", hold), ("razem", rows)])
    for title, rs in (("hold-out", hold), ("dev", dev)):
        out += table(f"Per sport ({title})",
                     [(sp, [r for r in rs if r["sport"] == sp]) for sp in sports])
    for title, rs in (("hold-out", hold), ("dev", dev)):
        out += table(f"Pasma kursu ({title})",
                     [(name, [r for r in rs if band(r["odds"]) == name])
                      for _, _, name in BANDS])
    out += table("Autor (razem)", [(a, [r for r in rows if r["author"] == a])
                                   for a in ("analyst", "verifier")])
    cats = sorted({str(r.get("category")) for r in rows if r["label"] == SHAKY})
    out += ["### CHWIEJNA wg kategorii (razem; opis, poza regułą)", "",
            "| kategoria | n | traf.−1/kurs | ROI |", "|---|---|---|---|"]
    for c in cats:
        s = stats([r for r in rows
                   if r["label"] == SHAKY and str(r.get("category")) == c])
        out.append(f"| {c} | {s['n']} | {_pp(s['vs_price'])} "
                   f"| {100 * s['roi']:+.1f}% |")
    out.append("")
    if removed:
        out += table("Nogi zdjęte przez odczyt (WATCH / NO_BET; poza regułą)",
                     [("zdjęte", removed)])
    return "\n".join(out)


def measure(args: argparse.Namespace) -> int:
    days = _days(args.date_from, args.date_to)
    ps, skipped = labelled(args.runs_dir, days, args.labels, args.pairs)
    graded = graded_rows(ps, args.runs_dir, args.db_path)
    keep = [r for r in graded if r["verdict"] == "KEEP"]
    removed = [r for r in graded if r["verdict"] != "KEEP"]
    if args.from_reads:
        # forward (T-STABILITY-LABEL-FORWARD): every pair is the hold-out, cut
        # at the 300th CHWIEJNA pair's kickoff, no dev condition
        keep, reached = forward_cut(keep)
        for r in keep:
            r["half"] = "holdout"
        dev: list[Row] = []
        hold = keep
        v = verdict(dev, hold, require_dev=False)
        v["forward_n_reached"] = reached
        v["min_shaky"] = FORWARD_REQUIRED_SHAKY
        if not reached:
            v["verdict"] = "NOT_YET_JUDGED"
    else:
        dev = [r for r in keep if r["half"] == "dev"]
        hold = [r for r in keep if r["half"] == "holdout"]
        v = verdict(dev, hold)
    meta = {"from": args.date_from, "to": args.date_to,
            "skipped": {**skipped, "ungraded_pairs": len(ps) - len(graded)}}
    md = report(keep, removed, v, meta)
    if args.md_out:
        Path(args.md_out).write_text(md + "\n", encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps({"verdict": v, "meta": meta,
                                                   "n_keep": len(keep)}, indent=1),
                                       encoding="utf-8")
    print(md)
    return 1 if skipped.get("unlabelled_pairs") else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("build-input", "measure"):
        p = sub.add_parser(name)
        p.add_argument("--from", dest="date_from", required=True)
        p.add_argument("--to", dest="date_to", required=True)
        p.add_argument("--runs-dir", default="runs/sofa")
    sub.choices["build-input"].add_argument("--out-dir", type=Path, required=True)
    sub.choices["build-input"].add_argument("--shards", type=int, default=10)
    m = sub.choices["measure"]
    m.add_argument("--labels", type=Path)
    m.add_argument("--pairs", type=Path, help="the build-input pairs.jsonl")
    m.add_argument("--from-reads", action="store_true",
                   help="forward: the label is the read's own `stability`")
    m.add_argument("--db-path", help="read-only; grades the read-removed legs")
    m.add_argument("--md-out")
    m.add_argument("--json-out")
    args = ap.parse_args(argv)
    if args.cmd == "build-input":
        return build_input(args.runs_dir, _days(args.date_from, args.date_to),
                           args.out_dir, args.shards)
    if args.labels is not None and args.pairs is None:
        ap.error("--labels needs --pairs")
    if (args.labels is None) != args.from_reads:
        ap.error("name the label source: --labels (retro) or --from-reads (forward)")
    return measure(args)


if __name__ == "__main__":
    sys.exit(main())
