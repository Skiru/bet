#!/usr/bin/env python3
"""Merge an analyst's or the verifier's report into the day's vetoes.json
and reads.json - parsed from the report file, validated, then written.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/merge_reads.py --date <d> \\
        --report <md> [--report <md> ...] [--author analyst|verifier] [--slip] \\
        [--dry-run]

--slip: the reads of a chat slip (`build_slip.py`, the `/kupon` loop) go to
vetoes_slip.json / reads_slip.json instead - the slip honours them, the
coupon never reads them (operator: a picks request does not touch the
coupon). Same validation. With --read-set <read_set_slip_*.json> (repeat
per file) every fresh read must cover a leg of those files and every leg
must get a read: UNMATCHED_READ / LEG_WITHOUT_READ are listed, exit 1 (the
merge is still written - a typo in an id would otherwise leave the loop
re-reading a leg it thinks is read). A slip read is stamped `read_at_utc`;
a later read of the same leg by the same author replaces an earlier KEEP
(the slip shows the latest read's time), never a WATCH / NO_BET.

A report ends with fenced JSON arrays (```json vetoes / ```json reads).
Every array is classified by its entries (a `verdict` = reads, a
`reason_class` = vetoes); a label must agree with them. An array of anything
else, a ```json fence that does not close, or no array at all is refused.

Rules (the product reads both files - COUPON, CONFIDENCE, COUPON_ASSEMBLY -
and a bad entry fails them, leaving the earlier build on disk looking
current, so nothing is written unless every entry validates):
* vetoes: contracts.Veto, strict; the day's earlier vetoes are carried over
  (a veto only removes, so keeping one is conservative) and listed; a veto
  matching no 05_sheet.json row and no measured-sport game of the day
  (COUPON_ASSEMBLY applies vetoes to sport legs too) is UNMATCHED_VETO - exit 1
  when a fresh one is, a carried one is only listed;
* reads: contracts.LegRead, strict; appended, an earlier read is never edited
  or dropped (WATCH / NO_BET win over KEEP whoever wrote them); with
  --author every read must carry that author.

Prints the counts and every WATCH / NO_BET. Exit 0 merged, 1 merged with an
UNMATCHED_VETO, 2 refused (nothing written).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pydantic import RootModel, ValidationError  # noqa: E402

from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.contracts import LegRead, SheetRow, Veto  # noqa: E402
from bet.sofa.coupon_sports import sport_event_ids  # noqa: E402
from bet.sofa.slip_builder import row_key  # noqa: E402
from bet.sofa.timeutil import now as utc_now  # noqa: E402
from bet.sofa.veto import find_unmatched_vetoes, veto_matches  # noqa: E402

# A fence may be indented (a block inside a list) and its label may carry a
# note ("```json reads (pass 2)"); every ```json opening must be consumed.
_FENCE = re.compile(r"^[ \t]*```[ \t]*json[ \t]*([A-Za-z_-]*)[^\n]*\n(.*?)^[ \t]*```",
                    re.M | re.S)
_OPEN = re.compile(r"^[ \t]*```[ \t]*json", re.M)


class ReportError(ValueError):
    """A report whose JSON blocks cannot be told apart or parsed."""


def _kind(entries: list[Any]) -> str | None:
    """"reads" (every entry has a verdict), "vetoes" (a reason_class), None
    for an empty array; anything else is refused."""
    if not entries:
        return None
    if all(isinstance(e, dict) and "verdict" in e for e in entries):
        return "reads"
    if all(isinstance(e, dict) and "reason_class" in e for e in entries):
        return "vetoes"
    raise ReportError("a JSON array mixes reads and vetoes, or holds neither")


def parse_report(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(vetoes, reads) from every fenced JSON array of a report, each array
    classified by its entries; a ```json vetoes / ```json reads label must
    agree with them. A report saved from several passes holds several."""
    found: dict[str, list[dict[str, Any]]] = {"vetoes": [], "reads": []}
    arrays = 0
    blocks = _FENCE.findall(text)
    if len(_OPEN.findall(text)) != len(blocks):
        raise ReportError("a ```json block is not closed or not parseable as a "
                          "fence - nothing merged")
    for label, body in blocks:
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ReportError(f"a ```json block does not parse: {exc}") from exc
        if not isinstance(data, list):
            continue  # an example object in the prose, not a verdict array
        arrays += 1
        kind = _kind(data)
        label = label.lower()
        if label in ("vetoes", "reads") and kind not in (None, label):
            raise ReportError(f"a ```json {label} block holds {kind}")
        if kind is not None:
            found[kind] += data
    if not arrays:
        raise ReportError("no fenced JSON array (```json reads) in the report")
    return found["vetoes"], found["reads"]


def _key(entry: dict[str, Any]) -> str:
    return json.dumps(entry, sort_keys=True)


def _leg_key(entry: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(entry.get(k) for k in ("sofascore_event_id", "market", "subject",
                                        "line", "direction", "period", "author"))


SLIP_VETOES, SLIP_READS = "vetoes_slip.json", "reads_slip.json"


def merge(run: Path, reports: list[Path], author: str | None, dry_run: bool,
          slip: bool = False, read_sets: list[Path] | None = None) -> int:
    fresh_v: list[dict[str, Any]] = []
    fresh_r: list[dict[str, Any]] = []
    for path in reports:
        report_v, report_r = parse_report(path.read_text(encoding="utf-8"))
        print(f"{path}: {len(report_v)} vetoes, {len(report_r)} reads")
        if not report_r:
            print(f"  WARNING: {path} holds no reads - an analyst / verifier "
                  "report without its reads block broke its contract")
        fresh_v += report_v
        fresh_r += report_r
    if author is not None:
        wrong = [r for r in fresh_r if r.get("author") != author]
        if wrong:
            raise ReportError(f"{len(wrong)} reads not authored {author!r}: "
                              f"{json.dumps(wrong[0], ensure_ascii=False)}")

    veto_path, reads_path = (
        (run / SLIP_VETOES, run / SLIP_READS) if slip
        else (run / "vetoes.json", run / "reads.json"))
    earlier_v = _load(veto_path)
    fresh_keys = {_key(v) for v in fresh_v}
    carried = [v for v in earlier_v if _key(v) not in fresh_keys]
    merged_v = _dedupe(fresh_v) + carried
    earlier_r = _load(reads_path)
    if slip:
        # a slip's read is stamped, and a later read of the same leg by the
        # same author replaces an earlier KEEP (its time is what the slip
        # shows); an earlier WATCH / NO_BET is never replaced - it wins
        stamp = utc_now().isoformat(timespec="seconds")
        fresh_r = [{**r, "read_at_utc": stamp} for r in fresh_r]
        again = {_leg_key(r) for r in fresh_r}
        earlier_r = [r for r in earlier_r
                     if r.get("verdict") != "KEEP" or _leg_key(r) not in again]
    seen = {_key(r) for r in earlier_r}
    merged_r = earlier_r + [r for r in _dedupe(fresh_r) if _key(r) not in seen]

    vetoes = RootModel[list[Veto]].model_validate(merged_v).root
    RootModel[list[LegRead]].model_validate(merged_r)

    unmatched: list[Veto] = []
    sheet = run / "05_sheet.json"
    if vetoes and sheet.exists():
        rows = RootModel[list[SheetRow]].model_validate_json(
            sheet.read_text(encoding="utf-8")).root
        sports = sport_event_ids(run)
        unmatched = [v for v in find_unmatched_vetoes(rows, vetoes)
                     if v.sofascore_event_id not in sports]
    elif fresh_v:
        print(f"  NOTE: no {sheet.name} - the vetoes' match was not checked")

    def rung(v: Any) -> tuple[Any, ...]:
        get = v.get if isinstance(v, dict) else lambda k: getattr(v, k)
        return tuple(get(k) for k in ("sofascore_event_id", "market", "subject",
                                      "line", "direction", "reason"))

    fresh_unmatched = {rung(v) for v in unmatched} & {rung(v) for v in fresh_v}

    print(f"vetoes: {len(fresh_v)} fresh, {len(carried)} carried over, "
          f"{len(merged_v)} in {veto_path.name}")
    for v in carried[:10]:
        print("  CARRIED:", json.dumps(v, ensure_ascii=False))
    if len(carried) > 10:
        print(f"  ... {len(carried) - 10} more carried vetoes in {veto_path.name}")
    for u in unmatched:
        tag = "" if rung(u) in fresh_unmatched else " (carried)"
        print(f"  UNMATCHED_VETO{tag}:", u.model_dump_json())
    counts = {x: sum(r["verdict"] == x for r in merged_r)
              for x in ("KEEP", "WATCH", "NO_BET")}
    print(f"reads: {len(merged_r) - len(earlier_r)} new, {len(merged_r)} in "
          f"{reads_path.name} {counts}")
    for r in merged_r[len(earlier_r):]:
        if r["verdict"] != "KEEP":
            print(f"  {r['verdict']} {r['author']} {r['sofascore_event_id']} "
                  f"{r.get('market')} {r.get('line')} {r.get('direction')} "
                  f"p{r.get('period')} - {r['reason']}")
    if dry_run:
        print("dry run: nothing written")
    else:
        if merged_v or veto_path.exists():
            write_atomic(veto_path,
                         json.dumps(merged_v, indent=2, ensure_ascii=False) + "\n")
        write_atomic(reads_path,
                     json.dumps(merged_r, indent=2, ensure_ascii=False) + "\n")
    off_set = _check_read_sets(read_sets or [], fresh_r, fresh_v)
    return 1 if fresh_unmatched or off_set else 0


def _check_read_sets(paths: list[Path], fresh_r: list[dict[str, Any]],
                     fresh_v: list[dict[str, Any]]) -> bool:
    """Every fresh read covers a leg of the files, every leg got a read or a
    veto; prints each miss. True when anything is off."""
    if not paths:
        return False
    legs = [leg for p in paths
            for leg in json.loads(p.read_text(encoding="utf-8"))]
    reads = [LegRead.model_validate(r) for r in fresh_r]
    vetoes = [Veto.model_validate(v) for v in fresh_v]
    keys = [row_key(leg) for leg in legs]
    off = False
    for r in reads:
        if not any(veto_matches(r, **k) for k in keys):
            off = True
            print(f"  UNMATCHED_READ: {r.sofascore_event_id} {r.market} "
                  f"{r.line} {r.direction} p{r.period} - no leg of the read set")
    for leg, k in zip(legs, keys, strict=True):
        if not any(veto_matches(x, **k) for x in reads) and not any(
                veto_matches(v, **k) for v in vetoes):
            off = True
            print(f"  LEG_WITHOUT_READ: {leg.get('match')} - "
                  f"{leg.get('superbet_market')}: {leg.get('superbet_selection')}")
    return off


def _load(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ReportError(f"{path} is not a JSON array")
    return data


def _dedupe(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for e in entries:
        if _key(e) not in seen:
            seen.add(_key(e))
            out.append(e)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--report", action="append", required=True, type=Path)
    ap.add_argument("--author", choices=("analyst", "verifier"))
    ap.add_argument("--runs-dir", default="runs/sofa")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--slip", action="store_true",
                    help="a chat slip's reads: *_slip.json, never the coupon's")
    ap.add_argument("--read-set", action="append", type=Path, default=[],
                    help="check the reads against this read-set file")
    args = ap.parse_args(argv)
    try:
        return merge(Path(args.runs_dir) / args.date, args.report, args.author,
                     args.dry_run, slip=args.slip, read_sets=args.read_set)
    except (OSError, ValueError, ValidationError) as exc:
        print(f"merge_reads: REFUSED, nothing written - {type(exc).__name__}: "
              f"{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
