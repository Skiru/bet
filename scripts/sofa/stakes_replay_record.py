"""Recording replay of calibrate_from_cache for the stakes exams (moved from
data/refit_2026-11-18_stakes/record.py, 2026-11-19). Measurement only: runs
``calibrate_from_cache.py --no-write`` on a DB COPY (the live data/sofa.db is
refused), live code untouched (module globals monkeypatched inside main()),
nothing in config/, src/ or the DB is written.

Per _settle_centred call one record: event, ts, competition, market, subject,
book (0 none / 1 plain / 2 form table), n, mean, variance, shrunk centre,
hooked (final) centre, season-phase multiplier, dispersion (alpha, family),
empirical flag, tennis rating flag, sample (empirical markets), home, away,
rows; the outcome in a separate y store. Per football forecast (both books):
BASE_METRICS rating centres home / away + home supremacy; per tennis
forecast p_home.

Store (unchanged layout, read by measure_stakes_exam.py):
OUT/<tier>/<kind>/<YYYY-MM>_<part>.pkl.gz, tier dev / exam (X) and exam_y
(outcomes of the exam tier, G2), kind rows / y / forecasts.

What changed against record.py (deviation 15 of the 2026-11-18 exam):
  - the replay is chronological (calibrate_from_cache sorts ``played``), so
    when a record of month M+1 arrives every buffer of a month <= M is
    flushed and OUT/months/<M>.json written: on-disk months are complete as
    soon as the replay moves past them, and only one month is ever buffered
    (record.py held every month's tail until exit);
  - every exam_y chunk is sealed (chmod 000, manifest) right after it is
    written (stakes_exam_guard.seal);
  - DONE.json (stakes_exam_guard.write_done) only at a clean exit (rc 0);
  - resumable: a re-run with the same OUT / window keeps the months already
    marked complete, deletes the chunks of the first unfinished month and
    every later one, and replays from that month's first day (the emit
    window only filters emission; every earlier match still enters the
    histories, so the records are the ones a whole run writes).

usage: stakes_replay_record.py OUT --db COPY --from YYYY-MM-DD --to YYYY-MM-DD
       [--seal-manifest PATH] [--smoke] [--players skip]
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import math
import pickle
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO / "src"), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scripts.sofa import stakes_exam_guard as guard  # noqa: E402

EXAM_FROM = 1767225600  # 2026-01-01 00:00Z (the exam tier of the stakes exams)
LIVE_DB = REPO / "data/sofa.db"
MONTHS_DIR = "months"
KINDS = ("rows", "y", "forecasts")

FLAGS = [
    "--halves", "include", "--player-starts-only",
    "--derived", "cards_points,goals,corners,shots_on_target",
    "--count-dispersion", "--cards-correlation", "--per-market-k",
    "--tennis-scoped-table", "--tennis-rating", "include",
    "--football-rating", "--rated-scope", "--venue-prior", "--game-state",
    "--rating-weight", "--season-phase", "--opponent-correction",
    "--tennis-set-ratings", "--cup-strength", "--sample-cup-strength",
    "--tennis-sample-scope", "--goals-stretch", "--count-stretch",
    "--player-stretch", "--closeness-stretch", "--player-coverage",
    "--awarded-excluded", "--referee", "--player-share",
    "--tennis-score-winner", "--sample-conflict-cut", "--form-table-per-family",
    "--cards-closeness-off",
]


def month_of(ts: int) -> str:
    return time.strftime("%Y-%m", time.gmtime(ts))


def months_between(day_from: str, day_to: str) -> list[str]:
    """Months touched by [day_from, day_to)."""
    a = dt.date.fromisoformat(day_from)
    b = dt.date.fromisoformat(day_to) - dt.timedelta(days=1)
    out: list[str] = []
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def tier_of(ts: int) -> str:
    return "exam" if ts >= EXAM_FROM else "dev"


class Recorder:
    """Buffers the current month only. ``add`` with a later month flushes
    every earlier buffer and marks the months it passed complete; a buffer
    of LIMIT records is flushed early as a numbered part."""

    LIMIT = 400_000

    def __init__(
        self, out: Path, window: list[str], manifest: Path | None = None
    ) -> None:
        self.out = out
        self.window = window
        self.manifest = manifest
        self.buf: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
        self.parts: dict[tuple[str, str, str], int] = defaultdict(int)
        self.counts: dict[str, Counter[str]] = defaultdict(Counter)
        self.current: str | None = None
        self.buffered = 0
        self.max_buffered = 0

    def add(self, kind: str, tier: str, ts: int, rec: Any) -> None:
        mon = month_of(ts)
        if self.current is None:
            self.current = mon
        elif mon > self.current:
            self.complete_before(mon)
            self.current = mon
        key = (kind, tier, mon)
        self.buf[key].append(rec)
        self.counts[mon][f"{tier}/{kind}"] += 1
        self.buffered += 1
        self.max_buffered = max(self.max_buffered, self.buffered)
        if len(self.buf[key]) >= self.LIMIT:
            self.flush(key)

    def flush(self, key: tuple[str, str, str]) -> None:
        recs = self.buf.pop(key, None)
        if not recs:
            return
        kind, tier, mon = key
        d = self.out / tier / kind
        d.mkdir(parents=True, exist_ok=True)
        i = self.parts[key]
        self.parts[key] += 1
        path = d / f"{mon}_{i:03d}.pkl.gz"
        with gzip.open(path, "wb", compresslevel=3) as f:
            pickle.dump(recs, f, protocol=pickle.HIGHEST_PROTOCOL)
        self.buffered -= len(recs)
        if tier == "exam_y" and self.manifest is not None:
            guard.seal([path], self.manifest.parent, self.manifest)

    def mark_complete(self, mon: str) -> None:
        d = self.out / MONTHS_DIR
        d.mkdir(parents=True, exist_ok=True)
        doc = {
            "month": mon,
            "counts": dict(self.counts.get(mon, {})),
            "completed_utc": guard.utc_now(),
        }
        (d / f"{mon}.json").write_text(json.dumps(doc, sort_keys=True) + "\n")

    def complete_before(self, mon: str) -> None:
        for key in [k for k in self.buf if k[2] < mon]:
            self.flush(key)
        for m in self.window:
            if m < mon and not (self.out / MONTHS_DIR / f"{m}.json").exists():
                self.mark_complete(m)

    def finish(self, rc: int | None, extra: dict[str, Any]) -> dict[str, Any] | None:
        """Clean exit only: flush, mark every window month, write DONE.json.
        A failed run keeps what it flushed (complete months) and gets no
        marker; the unfinished month's buffer is dropped (resume redoes it)."""
        if rc != 0:
            return None
        for key in list(self.buf):
            self.flush(key)
        for m in self.window:
            if not (self.out / MONTHS_DIR / f"{m}.json").exists():
                self.mark_complete(m)
        total: Counter[str] = Counter()
        for m in self.window:
            p = self.out / MONTHS_DIR / f"{m}.json"
            total.update(json.loads(p.read_text())["counts"])
        return guard.write_done(
            self.out,
            0,
            {**dict(total), **extra, "max_buffered_records": self.max_buffered},
            note="stakes_replay_record.py clean exit",
        )


def plan_resume(out: Path, window: list[str]) -> tuple[str | None, list[Path]]:
    """(first month to replay or None when every month is complete, chunk
    files to delete): the chunks of that month and of every later one."""
    done = {p.stem for p in (out / MONTHS_DIR).glob("*.json")}
    first = next((m for m in window if m not in done), None)
    if first is None:
        return None, []
    stale = [
        p
        for p in sorted(out.glob(guard.CHUNK_GLOB))
        if p.name[:7] >= first
    ]
    stale += [p for p in (out / MONTHS_DIR).glob("*.json") if p.stem >= first]
    return first, stale


def apply_resume(
    out: Path, stale: list[Path], manifest: Path | None
) -> None:
    sealed = [
        p.relative_to(manifest.parent).as_posix()
        for p in stale
        if manifest is not None and "exam_y" in p.parts
    ]
    for p in stale:
        p.unlink()
    if sealed and manifest is not None:
        guard.unlist(sealed, manifest)
    (out / guard.DONE_NAME).unlink(missing_ok=True)


# --------------------------------------------------------------------------
def install_hooks(cfc: Any, rec: Recorder, smoke: dict[str, Any] | None) -> None:
    """record.py's hooks, unchanged arithmetic, writing into ``rec``."""
    from bet.sofa import engine
    from bet.sofa.football_rating import BASE_METRICS

    state: dict[str, Any] = {"book": 0, "phase_mult": 1.0, "seen_fc": set()}

    orig_match_rows = cfc._match_rows

    def match_rows(match: Any, history: Any, baselines: Any, engine_constants: Any,
                   correlations: Any, rating: Any, joint_bases: Any,
                   football: Any) -> Iterator[Any]:
        state["book"] = (
            0 if football is None else (2 if football.rules.form_table else 1)
        )
        yield from orig_match_rows(match, history, baselines, engine_constants,
                                   correlations, rating, joint_bases, football)

    setattr(cfc, "_match_rows", match_rows)  # noqa: B010

    orig_phase = cfc.apply_season_phase

    def phase(centre: Any, market: Any, ph: Any, table: Any) -> Any:
        out = orig_phase(centre, market, ph, table)
        state["phase_mult"] = (out[0] / centre) if centre else 1.0
        return out

    setattr(cfc, "apply_season_phase", phase)  # noqa: B010

    orig_ffc = cfc.FootballRatingReplay.forecast

    def ffc(self: Any, match: Any) -> Any:
        fc = orig_ffc(self, match)
        if fc is None:
            return fc
        book = 2 if self.rules.form_table else 1
        key = (match.event_id, book)
        if key not in state["seen_fc"]:
            state["seen_fc"].add(key)
            cents = {}
            for m in BASE_METRICS:
                for side in ("side_a", "side_b"):
                    c = fc.centre(m, side)
                    cents[(m, side)] = None if c is None else float(c[0])
            r = (match.event_id, match.timestamp, match.competition_id,
                 match.home_id, match.away_id, book, cents, fc.supremacy("side_a"))
            rec.add("forecasts", tier_of(match.timestamp), match.timestamp, r)
        return fc

    setattr(cfc.FootballRatingReplay, "forecast", ffc)  # noqa: B010

    orig_tfc = cfc.RatingReplay.forecast

    def tfc(self: Any, match: Any) -> Any:
        fc = orig_tfc(self, match)
        key = (match.event_id, 0)
        if fc is not None and key not in state["seen_fc"]:
            state["seen_fc"].add(key)
            r = (match.event_id, match.timestamp, None, match.home_id,
                 match.away_id, 0, {"p_home": float(fc.p_home)}, None)
            rec.add("forecasts", tier_of(match.timestamp), match.timestamp, r)
        return fc

    setattr(cfc.RatingReplay, "forecast", tfc)  # noqa: B010

    orig_settle = cfc._settle_centred

    def settle(match: Any, market: Any, subject: Any, actual: Any, sample: Any,
               baselines: Any, engine_constants: Any, rating_p: Any = None,
               centre_hook: Any = None) -> Any:
        got: dict[str, float] = {}

        def hook(c: float) -> float:
            state["phase_mult"] = 1.0
            got["shrunk"] = c
            out = centre_hook(c) if centre_hook is not None else c
            got["final"] = out
            got["phase"] = state["phase_mult"]
            return float(out)

        rows = orig_settle(match, market, subject, actual, sample, baselines,
                           engine_constants, rating_p, hook)
        n = len(sample)
        if n < cfc.MIN_SAMPLE or "final" not in got:
            return rows
        disp = (cfc.COUNT_DISPERSION.read(match.sport, market, match.competition_id)
                if cfc.COUNT_DISPERSION is not None else None)
        mean = sum(sample) / n
        var = (sum((v - mean) ** 2 for v in sample) / (n - 1)) if n > 1 else 0.0
        emp = engine.uses_empirical_frequency(market)
        ts = match.timestamp
        r = (match.event_id, ts, match.competition_id, match.sport, market, subject,
             state["book"], n, mean, var, got["shrunk"], got["final"], got["phase"],
             None if disp is None else (disp.alpha, disp.family),
             emp, rating_p is not None, tuple(sample) if emp else None,
             match.home_id, match.away_id, len(rows))
        tier = tier_of(ts)
        rec.add("rows", tier, ts, r)
        rec.add("y", "exam_y" if tier == "exam" else "dev", ts,
                (match.event_id, market, subject, state["book"], float(actual)))
        if smoke is not None and rows:
            smoke["checked_records"] += 1
            centre = got["final"]
            spread = engine.sheet_predictive_sd(market, match.sport, mean, var, n,
                                                centre, disp)
            for row in rows:
                if rating_p is not None:
                    continue
                boundary = cfc.winning_boundary(row.line, row.direction)
                if emp:
                    p = engine.p_empirical_centred_raw(
                        list(sample), boundary, row.direction, centre - mean)
                else:
                    p = engine.sheet_count_p_raw(market, centre, spread, boundary,
                                                 row.direction, disp)
                d = abs(round(p, 6) - row.p_central)
                smoke["rows"] += 1
                smoke["max"] = max(smoke["max"], d)
                if not d <= 1e-9 or math.isnan(d):
                    smoke["bad"] += 1
        return rows

    setattr(cfc, "_settle_centred", settle)  # noqa: B010


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out")
    ap.add_argument("--db", required=True, help="a COPY of data/sofa.db")
    ap.add_argument("--from", dest="emit_from", required=True)
    ap.add_argument("--to", dest="emit_to", required=True)
    ap.add_argument("--seal-manifest", default=None)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--players", default="skip")
    a = ap.parse_args(argv)
    db = Path(a.db).resolve()
    if db == LIVE_DB.resolve():
        print("refused: --db is the live data/sofa.db; replay a copy",
              file=sys.stderr)
        return 2
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = Path(a.seal_manifest) if a.seal_manifest else None
    window = months_between(a.emit_from, a.emit_to)
    first, stale = plan_resume(out, window)
    if first is None:
        if not (out / guard.DONE_NAME).is_file():
            Recorder(out, window, manifest).finish(0, {"resumed": "all months"})
        print(f"every month of {window[0]}..{window[-1]} complete; nothing to do")
        return 0
    apply_resume(out, stale, manifest)
    emit_from = max(a.emit_from, f"{first}-01")
    rec = Recorder(out, window, manifest)
    smoke = {"rows": 0, "bad": 0, "max": 0.0, "checked_records": 0} if a.smoke else None

    from scripts.sofa import calibrate_from_cache as cfc

    install_hooks(cfc, rec, smoke)
    flags = list(FLAGS)
    if a.players == "skip":
        # --player-share only feeds player rows (team centres untouched)
        flags.remove("--player-share")
    sys.argv = ["calibrate_from_cache.py", "--db-path", str(db),
                "--runs-dir", str(REPO / "runs/sofa"), *flags,
                "--players", a.players, "--from", emit_from, "--no-write",
                "--to", a.emit_to]
    print("argv", " ".join(sys.argv[1:]), flush=True)
    t = time.time()
    rc: int | None = None
    try:
        rc = int(cfc.main())
    finally:
        done = rec.finish(rc, {"resumed_from": emit_from,
                               "secs": round(time.time() - t), "smoke": smoke})
        print("SUMMARY", json.dumps({"rc": rc, "done": done is not None,
                                     "max_buffered": rec.max_buffered}), flush=True)
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
