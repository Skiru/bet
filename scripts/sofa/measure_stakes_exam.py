"""Phase B of the FROZEN pre-registration of the football stakes term
(docs/sofa/evidence/stakes_prereg_football_2026-11-18.md, spec commit
646b1317; frozen state module docs/sofa/evidence/stakes_football_2026-11-18/
stakes_state.py, sha256 below). Template: the schedule exam
(scripts/sofa/measure_schedule_exam.py and the evidence scripts of
docs/sofa/evidence/kontekst_terminarza_2026-11-08/scripts/).

Read-only evidence, offline: nothing in config/, src/ or data/sofa.db is
written; every input is the DB copy's replay under SCRATCH.

Stages (each reads the previous stage's pickle under SCRATCH):

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_stakes_exam.py <stage> [...]

  prep      outcome-free inputs: as-of table position terciles (S2 blocks),
            installed schedule term t per side (path ii base), D10 phase
            labels; the 90-minute goals split by the seal (dev / exam_y)
  load      dev rows of every group (X rows + dev y) for the population
  explore   per group: Poisson GLM (offset log final centre, team-season FE),
            S1 / S2 permutation nulls, S3 directions (+ M4 drop)
  validate  S4: fit on exploration, Delta on validation (one logged look)
  power     S5 from the exam X rows only (no outcome)
  freeze    shrunk dev coefficients -> coefficients.json + freeze record
  exam      --mode fake (exam y drawn from the base arm; never logged) or
            --mode exam --spec-sha 646b1317 (opens the sealed exam outcomes
            once, appends one line to docs/sofa/evidence/stakes_exam_log.md)
  seal      chmod 000 every exam outcome file not yet sealed and enter it in
            SCRATCH/exam_seal_manifest.json (prep goals_y seals its own)

--study picks the pre-registration (STUDIES): `football` (2026-11-18, the
default) or `dead_goals` (2026-11-19). Shared inputs (replay, dev.pkl, prep
pickles) live in SCRATCH; each study keeps its own stage outputs.

Guards (scripts/sofa/stakes_exam_guard.py, after the 2026-11-18 deviations):
  - load / explore / validate / power / freeze / submit / exam refuse unless
    every replay run under SCRATCH/full carries a clean DONE.json whose file
    list is the chunk files on disk;
  - exam --mode exam refuses unless the coefficients, the submission, the
    freeze / submission records, this script, the guard module and the state
    module are committed and equal to HEAD (G1 by commit), and unless every
    exam outcome file is still sealed (chmod 000, in the manifest);
  - only exam --mode exam unseals an outcome file (hash checked against the
    manifest), logging each opened path + UTC to <evidence>/run/
    exam_access.log, and seals it again when it ends.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import math
import pickle
import sqlite3
import subprocess
import sys
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO / "src"), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import epochs  # noqa: E402
from bet.sofa.football_1x2_dnb import probabilities  # noqa: E402
from bet.sofa.football_result import load_config  # noqa: E402
from scripts.sofa import stakes_exam_guard as guard  # noqa: E402
from scripts.sofa.fit_confidence import (  # noqa: E402
    EDGES,
    MIN_MARKET_BUCKET,
    MIN_POOLED_BUCKET,
)

MODULE_REL = "docs/sofa/evidence/stakes_football_2026-11-18/stakes_state.py"
MODULE_SHA256 = "99e81fe70f6ed6855afb6264e20c8cdf0798126463ca5cba69c958233bee1949"
SCRATCH = REPO / "data/refit_2026-11-18_stakes"
STATES_DIR = SCRATCH / "phaseA/S"
EXAM_LOG = REPO / "docs/sofa/evidence/stakes_exam_log.md"
SEAL_MANIFEST = SCRATCH / guard.MANIFEST_NAME
# every exam outcome store: prep's 90-minute goals and the recorder's y
SEAL_PATTERNS = ("exam_y/*", "full/*/exam_y/*/*.pkl.gz")
SCRIPT = Path(__file__).resolve()
GUARD_MODULE = REPO / "scripts/sofa/stakes_exam_guard.py"
# D10 of the schedule pre-registration (applies where this spec is silent):
# the season phase refitted on dev, committed in 87a5087f.
PHASE_DEV = (
    REPO
    / "docs/sofa/evidence/kontekst_terminarza_2026-11-08/frozen/season_phase_dev.json"
)


def ts_of(day: str) -> int:
    return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.UTC).timestamp())


GOALS_FROM = ts_of("2024-07-01")
COUNT_FROM = ts_of("2025-01-01")
EXPLORE_END = ts_of("2025-09-01")
DEV_END = ts_of("2026-01-01")
EXAM_FROM = DEV_END
EXAM_TO = ts_of("2026-11-18")  # exam = 2026-01-01 .. 2026-11-17 inclusive
TAU = 0.05
STATES = ("MUST_WIN", "SECURED", "DEAD")
# side_x layout (every state column); a study fits its own subset, COLS
SIDE_COLS = [f"own_{s}" for s in STATES] + [f"opp_{s}" for s in STATES]
GROUPS: dict[str, list[str]] = {
    "goals": ["goals_for", "goals_1h_for", "goals_2h_for"],
    "corners": ["corners_for", "corners_1h_for", "corners_2h_for"],
    "shots_sot": [
        "shots_for",
        "shots_1h_for",
        "shots_2h_for",
        "shots_on_target_for",
        "shots_on_target_1h_for",
        "shots_on_target_2h_for",
    ],
    "cards_fouls": ["cards_points_for", "fouls_for", "fouls_1h_for", "fouls_2h_for"],
}
COUNT_GROUPS = tuple(GROUPS)
FOOTBALL_GROUPS = ("goals", "football_result", "corners", "shots_sot", "cards_fouls")
METRIC_GROUP = {m: g for g, ms in GROUPS.items() for m in ms}
# The one pre-registered pool (spec 8): a powerless shots_sot / corners goes
# to the exam only as this pool; cards_fouls has no partner.
POOL = "shots_sot+corners"
POOL_OF = ("shots_sot", "corners")
GROUPS_ALL: dict[str, list[str]] = {
    **GROUPS,
    POOL: GROUPS["shots_sot"] + GROUPS["corners"],
}
ATTACK = {"goals", "corners", "shots_sot", "football_result"}
# S3 (spec 6): own MUST_WIN -> own attack up; own DEAD / SECURED -> own attack
# down, opp up or 0. Cards / fouls: no direction.
S3_MOTIVATION: dict[str, int] = {
    "own_MUST_WIN": +1,
    "own_SECURED": -1,
    "own_DEAD": -1,
    "opp_SECURED": +1,
    "opp_DEAD": +1,
}
FAMS = epochs.FOOTBALL_FORM_TABLE_FAMILIES
NB_R = load_config().nb_r
MIN_FIT_ROWS = 2000
REPS = 2000
ALPHA = 0.05
P3_UPPER = 2e-4
P4_SLACK = 0.005
P5_GROUP_UPPER = 1e-4
P5_STRATUM_UPPER = 5e-4
P5_MIN_STRATUM_ROWS = 2000
EPS = 1e-6
FAKE_SEED = 20261118
KMAX = 40
# The scored window: the exam tier, or (stage devtest, a plumbing run that
# opens no exam outcome) the validation months of the dev tier.
WIN: dict[str, Any] = {"tier": "exam", "lo": EXAM_FROM, "hi": EXAM_TO}


@dataclass(frozen=True)
class Study:
    """One pre-registration. ``s5``: "c003" = power at |c| = 0.03 (the
    2026-11-18 rule), "frozen_coef" = power per column at the column's frozen
    shrunk goals_for |c|. ``p2``: "per_column" = a material column must itself
    be 1 on >= 2% of the exam `_for` rows; "any_column" = the rows the term
    touches (any of the study's columns = 1) >= 2%."""

    key: str
    name: str
    prereg: str
    spec_sha: str | None
    evidence: Path
    work: Path
    groups: tuple[str, ...]
    cols: tuple[str, ...]
    s3: tuple[tuple[str, int], ...]
    s5: str
    p2: str


STUDIES: dict[str, Study] = {
    "football": Study(
        key="football",
        name="stakes_football_2026-11",
        prereg="docs/sofa/evidence/stakes_prereg_football_2026-11-18.md",
        spec_sha="646b1317",
        evidence=REPO / "docs/sofa/evidence/stakes_football_2026-11-18",
        work=SCRATCH,
        groups=FOOTBALL_GROUPS,
        cols=tuple(SIDE_COLS),
        s3=tuple(S3_MOTIVATION.items()),
        s5="c003",
        p2="per_column",
    ),
    # docs/sofa/evidence/stakes_prereg_dead_goals_2026-11-19.md: a DEAD side
    # (own and / or opponent) -> more goals; direction chosen after the
    # 2026-11-18 exploration, tested on the untouched tiers.
    "dead_goals": Study(
        key="dead_goals",
        name="stakes_dead_goals_2026-11-19",
        prereg="docs/sofa/evidence/stakes_prereg_dead_goals_2026-11-19.md",
        spec_sha=None,
        evidence=REPO / "docs/sofa/evidence/stakes_dead_goals_2026-11-19",
        work=SCRATCH / "dead_goals_2026-11-19",
        groups=("goals",),
        cols=("own_DEAD", "opp_DEAD"),
        s3=(("own_DEAD", +1), ("opp_DEAD", +1)),
        s5="frozen_coef",
        p2="any_column",
    ),
}

# the active study's names (configure() rebinds them)
STUDY_CFG = STUDIES["football"]
STUDY = STUDY_CFG.name
SPEC_SHA = STUDY_CFG.spec_sha
ALL_GROUPS: tuple[str, ...] = STUDY_CFG.groups
COLS: list[str] = list(STUDY_CFG.cols)
S3_DIRECTIONS: dict[str, int] = dict(STUDY_CFG.s3)
EVIDENCE = STUDY_CFG.evidence
RUN = EVIDENCE / "run"
WORK = STUDY_CFG.work
COEF_FILE = EVIDENCE / "coefficients.json"
FREEZE_RECORD = RUN / "freeze_record.json"
SUBMISSION = RUN / "submission.json"
SUBMISSION_RECORD = RUN / "submission_record.json"
ACCESS_LOG = RUN / "exam_access.log"
LOOKS = WORK / "looks.md"
EXPLORE_JSON = WORK / "explore.json"
VALIDATE_JSON = WORK / "validate.json"
POWER_JSON = WORK / "power.json"


def configure(key: str) -> Study:
    global STUDY_CFG, STUDY, SPEC_SHA, ALL_GROUPS, COLS, S3_DIRECTIONS
    global EVIDENCE, RUN, WORK, COEF_FILE, FREEZE_RECORD, SUBMISSION
    global SUBMISSION_RECORD, ACCESS_LOG, LOOKS, EXPLORE_JSON, VALIDATE_JSON
    global POWER_JSON
    st = STUDIES[key]
    STUDY_CFG, STUDY, SPEC_SHA = st, st.name, st.spec_sha
    ALL_GROUPS, COLS, S3_DIRECTIONS = st.groups, list(st.cols), dict(st.s3)
    EVIDENCE, WORK = st.evidence, st.work
    RUN = EVIDENCE / "run"
    COEF_FILE = EVIDENCE / "coefficients.json"
    FREEZE_RECORD = RUN / "freeze_record.json"
    SUBMISSION = RUN / "submission.json"
    SUBMISSION_RECORD = RUN / "submission_record.json"
    ACCESS_LOG = RUN / "exam_access.log"
    LOOKS = WORK / "looks.md"
    EXPLORE_JSON = WORK / "explore.json"
    VALIDATE_JSON = WORK / "validate.json"
    POWER_JSON = WORK / "power.json"
    return st

F64 = npt.NDArray[np.float64]
I64 = npt.NDArray[np.int64]
B = npt.NDArray[np.bool_]
Row = dict[str, Any]


def log(msg: str) -> None:
    print(msg, flush=True)


def dump(obj: Any, name: str) -> None:
    (SCRATCH / name).write_bytes(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))


def load_pkl(path: Path) -> Any:
    return pickle.loads(path.read_bytes())


def book_for(market: str) -> int:
    return 2 if f"{market}|OVER" in FAMS else 1


def total_of(metric: str) -> str:
    return metric[: -len("_for")] + "_total"


# --------------------------------------------------------------------------
# X store (record.py chunks; several parallel windows under SCRATCH/full/*)
def chunk_files(tier: str, kind: str) -> list[Path]:
    return sorted((SCRATCH / "full").glob(f"*/{tier}/{kind}/*.pkl.gz"))


# The exam mode's door to the sealed outcomes; None outside it.
_UNSEALER: list[guard.Unsealer] = []


def sealed_path(p: Path) -> Path:
    """A sealed exam outcome file, readable only through the exam mode's
    Unsealer (which checks the manifest hash and logs the access)."""
    if not _UNSEALER:
        raise PermissionError(
            f"{p}: a sealed exam outcome file; only exam --mode exam opens it"
        )
    return _UNSEALER[0].open(p)


def read_chunks(tier: str, kind: str) -> Iterator[Any]:
    for p in chunk_files(tier, kind):
        if tier == "exam_y":
            p = sealed_path(p)
        with gzip.open(p, "rb") as f:
            yield from pickle.load(f)


def require_replay_done(stage: str) -> None:
    """A1: every replay run under SCRATCH/full finished cleanly (DONE.json
    with rc 0 whose file list is the chunk files on disk)."""
    problems = guard.replay_problems(SCRATCH / "full")
    if problems:
        raise SystemExit(
            f"refused ({stage}): replay not complete - " + "; ".join(problems)
        )


def seal_outcomes() -> list[dict[str, Any]]:
    """Seal every exam outcome file not yet sealed (A3)."""
    files = [
        p for pat in SEAL_PATTERNS for p in sorted(SCRATCH.glob(pat)) if p.is_file()
    ]
    added = guard.seal(files, SCRATCH, SEAL_MANIFEST)
    log(f"sealed {len(added)} new file(s); manifest {SEAL_MANIFEST}")
    return added


# --------------------------------------------------------------------------
# population: the frozen phase-A states (inventory.py on the copy)
@dataclass
class Pop:
    states: dict[int, dict[str, Any]]
    season: dict[int, int]
    ut: dict[int, int]


_POP: list[Pop] = []


def population() -> Pop:
    if _POP:
        return _POP[0]
    import pandas as pd  # type: ignore[import-untyped]

    st = pd.read_pickle(STATES_DIR / "states.pkl")
    st = st[~st.nat].drop_duplicates("event_id")
    listed = pd.read_pickle(STATES_DIR / "listed.pkl")[["event_id", "season", "ut"]]
    listed = listed.drop_duplicates("event_id")
    season = {
        int(e): int(s)
        for e, s in zip(listed.event_id, listed.season, strict=True)
        if s == s
    }
    ut = {
        int(e): int(u)
        for e, u in zip(listed.event_id, listed.ut, strict=True)
        if u == u
    }
    states = {int(r["event_id"]): dict(r) for r in st.to_dict("records")}
    _POP.append(Pop(states, season, ut))
    return _POP[0]


def in_pop(eid: int, women: bool | None = False) -> bool:
    """Club league match, no AMBIGUOUS side; women: False = men only,
    True = women only, None = both."""
    s = population().states.get(eid)
    if s is None or s["home"] == "AMBIGUOUS" or s["away"] == "AMBIGUOUS":
        return False
    return women is None or bool(s["women"]) == women


def side_x(eid: int, side: str) -> list[float]:
    s = population().states[eid]
    own, opp = (s["home"], s["away"]) if side == "home" else (s["away"], s["home"])
    return [float(own == c) for c in STATES] + [float(opp == c) for c in STATES]


# --------------------------------------------------------------------------
# prep
def prep_ranks() -> None:
    """As-of table position tercile of each side (S2 blocks): points from the
    group's matches finished strictly before kick-off, rank = 1 + teams with
    more points (ties share the best rank), tercile = ceil(3 rank / n)."""
    import pandas as pd

    st = pd.read_pickle(STATES_DIR / "states.pkl")
    st = st[~st.nat]
    groups = pd.read_pickle(STATES_DIR / "groups.pkl")
    d = pd.read_pickle(STATES_DIR / "listed.pkl")
    d = d[
        d.st.isin(["finished", "notstarted"])
        & (~d.friendly)
        & d.hid.notna()
        & d.aid.notna()
        & d.ut.notna()
    ]
    d = d[~((d.st == "finished") & (d.hg.isna() | d.ag.isna()))]
    d = d[d.cup_rt.isna() & d.rnd_name.isna()]
    keys = {
        (int(r.ut), int(r.season), int(r.tid)) for r in groups.itertuples() if not r.nat
    }
    want = set(st.event_id.astype(int))
    out: dict[int, tuple[int, int]] = {}
    for (ut, season, tid), g in d.groupby(["ut", "season", "tid"], dropna=True):
        if (int(ut), int(season), int(tid)) not in keys:
            continue
        teams = sorted(set(g.hid.astype(int)) | set(g.aid.astype(int)))
        n = len(teams)
        fin = g[g.st == "finished"].sort_values("start_ts")
        evs = list(fin.itertuples())
        for r in evs:
            if int(r.event_id) not in want:
                continue
            pts = dict.fromkeys(teams, 0)
            for x in evs:
                if x.start_ts >= r.start_ts:
                    break
                h, a, hg, ag = int(x.hid), int(x.aid), int(x.hg), int(x.ag)
                pts[h] += 3 if hg > ag else 1 if hg == ag else 0
                pts[a] += 3 if ag > hg else 1 if hg == ag else 0

            def terc(t: int, pts: dict[int, int] = pts) -> int:
                rank = 1 + sum(1 for v in pts.values() if v > pts[t])
                return min(3, math.ceil(3 * rank / n))

            out[int(r.event_id)] = (terc(int(r.hid)), terc(int(r.aid)))
    dump(out, "ranks.pkl")
    log(f"ranks {len(out)}")


def prep_sched() -> None:
    """Installed schedule term (config/sofa_schedule_terms.json) per side of
    every population event: path (ii) base arm (spec 5: the stakes term goes
    AFTER the installed schedule term, in both arms). Outcome-free."""
    from bet.sofa import schedule_term as sterm
    from bet.sofa.schedule_features import calendar_from_events, iter_listed_events

    terms = sterm.load()
    continental = json.loads((REPO / "config/sofa_cup_strength.json").read_text())[
        "competitions"
    ]
    conn = sqlite3.connect(f"file:{SCRATCH / 'sofa.db'}?mode=ro", uri=True)
    cal = calendar_from_events(
        iter_listed_events(conn, "football"),
        "football",
        continental=[int(c) for c in continental],
    )
    pop = population()
    out: dict[int, tuple[float, float, str]] = {}
    for eid in pop.states:
        m = cal._by_id.get(eid)
        if m is None:
            out[eid] = (0.0, 0.0, "NOT_IN_CALENDAR")
            continue
        h = cal.football_side(m.home_id, m.ts, m.competition_id, m.season_id)
        a = cal.football_side(m.away_id, m.ts, m.competition_id, m.season_id)
        ft = sterm.fixture_term(terms, h, a, bool(m.national))
        out[eid] = (ft.t_home, ft.t_away, ft.status)
    dump(out, "sched_t.pkl")
    log(f"sched {len(out)}")


def prep_phase() -> None:
    """D10 phase labels (season_phase.phases_by_event, awarded excluded) from
    the replay's own football history cache on the copy."""
    from bet.sofa import season_phase as sp
    from scripts.sofa.measure_season_phase import load_history

    h = load_history(SCRATCH / "cache/football_history.pkl", awarded_out=True)
    lab = {int(k): v for k, v in sp.phases_by_event(h).items()}
    dump(lab, "phase_labels.pkl")
    log(f"phase labels {len(lab)}")


def prep_goals_y() -> None:
    """90-minute goals per finished event (fr_build.py rule), split by the
    seal: dev -> fr_dev_y.pkl, exam -> exam_y/fr_y.pkl (G2)."""
    from bet.sofa.metrics import played_extra_time

    conn = sqlite3.connect(f"file:{SCRATCH / 'sofa.db'}?mode=ro", uri=True)
    dev: dict[int, tuple[int, int]] = {}
    exam: dict[int, tuple[int, int]] = {}
    for eid, ts, raw in conn.execute(
        "SELECT event_id, start_ts, event_json FROM sofa_listed_event "
        "WHERE sport='football' "
        "AND start_ts >= ? AND start_ts < ?",
        (GOALS_FROM, EXAM_TO),
    ):
        e = json.loads(raw)
        if (e.get("status") or {}).get("type") != "finished":
            continue
        hs, as_ = e.get("homeScore") or {}, e.get("awayScore") or {}
        h, a = hs.get("normaltime"), as_.get("normaltime")
        if not (isinstance(h, int) and isinstance(a, int)):
            try:
                if played_extra_time(e):
                    continue
            except Exception:  # noqa: BLE001
                continue
            h, a = hs.get("current"), as_.get("current")
        if not (isinstance(h, int) and isinstance(a, int)):
            continue
        (exam if ts >= EXAM_FROM else dev)[int(eid)] = (h, a)
    dump(dev, "fr_dev_y.pkl")
    (SCRATCH / "exam_y").mkdir(exist_ok=True)
    (SCRATCH / "exam_y/fr_y.pkl").write_bytes(pickle.dumps(exam))
    seal_outcomes()
    log(f"goals y dev {len(dev)} exam (sealed) {len(exam)}")


# --------------------------------------------------------------------------
# D10 centre
_D10: dict[str, Any] = {}


def d10_centre(market: str, eid: int, final: float, phase_mult: float) -> float:
    if not _D10:
        _D10["c"] = {
            m: v["coefficients"]
            for m, v in json.loads(PHASE_DEV.read_text())["markets"].items()
        }
        _D10["lab"] = load_pkl(SCRATCH / "phase_labels.pkl")
    cm = _D10["c"].get(market)
    if cm is None:
        return final
    lab = _D10["lab"].get(eid)
    c = cm.get(lab, 0.0) if lab not in (None, "mid") else 0.0
    return final / phase_mult * math.exp(float(c))


# --------------------------------------------------------------------------
# rows
def count_rows(
    tier: str,
    ys: dict[tuple[Any, ...], float] | None,
    women: bool | None,
    metrics: set[str],
    rng: np.random.Generator | None = None,
) -> list[Row]:
    """Count rows of the population for `metrics` (`_for` and `_total`).
    ys None + rng: y drawn from the base NB (fake); ys None, rng None: y = nan
    (outcome-free X)."""
    out: list[Row] = []
    pop = population()
    for r in read_chunks(tier, "rows"):
        (
            eid,
            ts,
            comp,
            sport,
            market,
            subject,
            book,
            _n,
            _mean,
            _var,
            _shrunk,
            final,
            phase,
            disp,
            _emp,
            _rp,
            _sample,
            home,
            away,
            _nrows,
        ) = r
        if sport != "football" or market not in metrics or book != book_for(market):
            continue
        if not in_pop(int(eid), women):
            continue
        floor = GOALS_FROM if market.startswith("goals") else COUNT_FROM
        if ts < floor:
            continue
        if tier == WIN["tier"] and not (WIN["lo"] <= ts < WIN["hi"]):
            continue
        centre = d10_centre(market, int(eid), float(final), float(phase))
        alpha = float(disp[0]) if disp else 0.0
        y: float
        if ys is not None:
            got = ys.get((eid, market, subject, book))
            if got is None:
                continue
            y = float(got)
        elif rng is not None:
            if alpha > 0:
                rr = 1 / alpha
                y = float(rng.negative_binomial(rr, rr / (rr + centre)))
            else:
                y = float(rng.poisson(centre))
        else:
            y = float("nan")
        side = None
        if market.endswith("_for"):
            side = (
                "home"
                if int(subject) == home
                else "away"
                if int(subject) == away
                else None
            )
            if side is None:
                continue
        out.append(
            {
                "eid": int(eid),
                "ts": int(ts),
                "comp": comp,
                "market": market,
                "side": side,
                "y": y,
                "centre": centre,
                "alpha": alpha,
                "home": int(home),
                "away": int(away),
                "season": pop.season.get(int(eid), -1),
                "women": bool(pop.states[int(eid)]["women"]),
            }
        )
    return out


def read_ys(tier: str, metrics: set[str]) -> dict[tuple[Any, ...], float]:
    ys: dict[tuple[Any, ...], float] = {}
    for e, m, s, b, a in read_chunks(tier, "y"):
        if m in metrics:
            ys[(e, m, s, b)] = float(a)
    return ys


def all_metrics() -> set[str]:
    return set(METRIC_GROUP) | {total_of(m) for m in METRIC_GROUP}


def fr_rows(
    tier: str,
    ys: dict[int, tuple[int, int]] | None,
    women: bool | None,
    rng: np.random.Generator | None = None,
    window: tuple[int, int] | None = None,
) -> list[Row]:
    """football_result (path ii): one row per match - rating goals centres of
    book 1 (result_1x2 is not a form-table family) x the installed schedule
    term (base arm), 90-minute goals."""
    sched: dict[int, tuple[float, float, str]] = load_pkl(SCRATCH / "sched_t.pkl")
    pop = population()
    lo, hi = (GOALS_FROM, DEV_END) if tier == "dev" else (EXAM_FROM, EXAM_TO)
    if window is not None:
        lo, hi = window
    out: list[Row] = []
    seen: set[int] = set()
    for rec in read_chunks(tier, "forecasts"):
        eid, ts, comp, home, away, book, cents, sup = rec
        if (
            book != 1
            or eid in seen
            or not (lo <= ts < hi)
            or not in_pop(int(eid), women)
        ):
            continue
        lh, la = cents.get(("goals_for", "side_a")), cents.get(("goals_for", "side_b"))
        if lh is None or la is None or lh <= 0 or la <= 0:
            continue
        th, ta, _st = sched.get(int(eid), (0.0, 0.0, "MISSING"))
        lh, la = lh * math.exp(th), la * math.exp(ta)
        goals: tuple[int, int] | None
        if ys is not None:
            if eid not in ys:
                continue
            goals = ys[eid]
        elif rng is not None:
            pb = probabilities(lh, la, NB_R)
            p1, p2 = pb["1x2:1"], pb["1x2:2"]
            res = str(rng.choice(["1", "X", "2"], p=[p1, 1 - p1 - p2, p2]))
            goals = (1, 0) if res == "1" else (0, 1) if res == "2" else (0, 0)
        else:
            goals = None
        seen.add(int(eid))
        out.append(
            {
                "eid": int(eid),
                "ts": int(ts),
                "comp": comp,
                "home": int(home),
                "away": int(away),
                "lh": float(lh),
                "la": float(la),
                "goals": goals,
                "sup": None if sup is None else abs(float(sup)),
                "season": pop.season.get(int(eid), -1),
                "women": bool(pop.states[int(eid)]["women"]),
            }
        )
    return out


def fr_side_rows(rows: list[Row]) -> list[Row]:
    """football_result rows as goals_for side rows (the GLM's view)."""
    out: list[Row] = []
    for r in rows:
        g = r["goals"]
        for side, c, y in (("home", r["lh"], g[0]), ("away", r["la"], g[1])):
            out.append(
                {
                    "eid": r["eid"],
                    "ts": r["ts"],
                    "comp": r["comp"],
                    "market": "goals_for",
                    "side": side,
                    "y": float(y),
                    "centre": c,
                    "alpha": 0.0,
                    "home": r["home"],
                    "away": r["away"],
                    "season": r["season"],
                    "women": r["women"],
                }
            )
    return out


def load() -> None:
    ms = all_metrics()
    dev = count_rows("dev", read_ys("dev", ms), False, ms)
    women = count_rows("dev", read_ys("dev", ms), True, ms)
    ys: dict[int, tuple[int, int]] = load_pkl(SCRATCH / "fr_dev_y.pkl")
    fr = fr_rows("dev", ys, False)
    dump({"count": dev, "count_women": women, "fr": fr}, "dev.pkl")
    log(f"dev count rows {len(dev)} (women {len(women)}), fr matches {len(fr)}")


# --------------------------------------------------------------------------
# GLM (fb_analysis.py of the schedule study)
def fit_poisson(
    y: F64, off: F64, x: F64, g: I64, fe: F64 | None = None, iters: int = 25
) -> tuple[F64, F64]:
    k = x.shape[1]
    b = np.zeros(k)
    fixed = fe is not None
    a = fe.copy() if fe is not None else np.zeros(int(g.max()) + 1)
    for _ in range(iters):
        if not fixed:
            mu0 = np.exp(off + x @ b)
            a = np.log(
                (np.bincount(g, y, len(a)) + 0.5) / (np.bincount(g, mu0, len(a)) + 0.5)
            )
        if k == 0:
            break
        mu = np.exp(off + a[g] + x @ b)
        grad = x.T @ (y - mu)
        h = x.T @ (x * mu[:, None]) + 1e-6 * np.eye(k)
        step = np.linalg.solve(h, grad)
        b = b + step
        if np.max(np.abs(step)) < 1e-8:
            break
    return b, a


def cluster_se(y: F64, off: F64, x: F64, g: I64, a: F64, b: F64, cl: I64) -> F64:
    mu = np.exp(off + a[g] + x @ b)
    h = x.T @ (x * mu[:, None]) + 1e-6 * np.eye(x.shape[1])
    s = x * (y - mu)[:, None]
    sc = np.zeros((int(cl.max()) + 1, x.shape[1]))
    np.add.at(sc, cl, s)
    hi = np.linalg.inv(h)
    out: F64 = np.sqrt(np.clip(np.diag(hi @ (sc.T @ sc) @ hi), 0, None))
    return out


def deviance_gain(y: F64, off: F64, x: F64, g: I64, fe: F64) -> float:
    b, _ = fit_poisson(y, off, x, g, fe=fe)
    mu0 = np.exp(off + fe[g])
    mu1 = np.exp(off + fe[g] + x @ b)
    return float((y * np.log(mu1 / mu0) - (mu1 - mu0)).sum())


def side_team(r: Row) -> int:
    return int(r["home"] if r["side"] == "home" else r["away"])


def keys_of(rows: list[Row], fn: Any) -> I64:
    keys: dict[Any, int] = {}
    return np.array([keys.setdefault(fn(r), len(keys)) for r in rows], dtype=np.int64)


@dataclass
class Fit:
    b: F64
    se: F64
    cols: list[str]
    y: F64
    off: F64
    x: F64
    g: I64
    a: F64
    rows: list[Row]


def design(rows: list[Row], cols: list[str]) -> F64:
    idx = [SIDE_COLS.index(c) for c in cols]
    x = np.array([side_x(r["eid"], r["side"]) for r in rows], dtype=float).reshape(
        -1, len(SIDE_COLS)
    )
    out: F64 = x[:, idx]
    return out


def metric_rows(rows: list[Row], metric: str, lo: int, hi: int) -> list[Row]:
    return [
        r for r in rows if r["market"] == metric and lo <= r["ts"] < hi and r["side"]
    ]


def fit_metric(rs: list[Row], cols: list[str]) -> Fit:
    y = np.array([r["y"] for r in rs], dtype=float)
    off = np.log(np.array([r["centre"] for r in rs], dtype=float))
    x = design(rs, cols)
    g = keys_of(rs, lambda r: (side_team(r), r["season"]))
    b, a = fit_poisson(y, off, x, g)
    se = cluster_se(y, off, x, g, a, b, keys_of(rs, side_team))
    return Fit(b, se, cols, y, off, x, g, a, rs)


def group_rows(dev: dict[str, Any], group: str) -> list[Row]:
    if group == "football_result":
        return fr_side_rows(dev["fr"])
    rows: list[Row] = dev["count"]
    return rows


def group_metrics(group: str) -> list[str]:
    return ["goals_for"] if group == "football_result" else GROUPS[group]


def blocks_of(keys: I64) -> list[I64]:
    order = np.argsort(keys, kind="stable")
    return list(np.split(order, np.flatnonzero(np.diff(keys[order])) + 1))


def permuted(rng: np.random.Generator, blocks: list[I64], n: int) -> I64:
    perm = np.empty(n, dtype=np.int64)
    for blk in blocks:
        perm[blk] = rng.permutation(blk)
    return perm


def explore() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    dev = load_pkl(SCRATCH / "dev.pkl")
    ranks: dict[int, tuple[int, int]] = load_pkl(SCRATCH / "ranks.pkl")
    pop = population()
    rng = np.random.default_rng(13)
    res: dict[str, Any] = {}
    for group in ALL_GROUPS:
        rows = group_rows(dev, group)
        gain_real = 0.0
        null1 = np.zeros(200)
        null2 = np.zeros(200)
        coefs: dict[str, dict[str, list[float]]] = {}
        nrows: dict[str, int] = {}
        exposed: dict[str, dict[str, int]] = {}
        for m in group_metrics(group):
            rs = metric_rows(rows, m, 0, EXPLORE_END)
            nrows[m] = len(rs)
            if len(rs) < MIN_FIT_ROWS:
                log(f"{group} {m} rows {len(rs)} skipped (< {MIN_FIT_ROWS})")
                continue
            f = fit_metric(rs, COLS)
            exposed[m] = {c: int(f.x[:, i].sum()) for i, c in enumerate(COLS)}
            _, fe0 = fit_poisson(f.y, f.off, np.zeros((len(f.y), 0)), f.g)
            gr = deviance_gain(f.y, f.off, f.x, f.g, fe0)
            gain_real += gr
            coefs[m] = {
                c: [float(v), float(s)] for c, v, s in zip(COLS, f.b, f.se, strict=True)
            }
            b1 = blocks_of(f.g)
            k2 = keys_of(
                rs,
                lambda r: (
                    pop.ut.get(r["eid"], -1),
                    r["season"],
                    ranks.get(r["eid"], (0, 0))[0 if r["side"] == "home" else 1],
                    min(9, int(10 * float(pop.states[r["eid"]]["progress"]))),
                ),
            )
            b2 = blocks_of(k2)
            for k in range(200):
                null1[k] += deviance_gain(
                    f.y, f.off, f.x[permuted(rng, b1, len(f.y))], f.g, fe0
                )
                null2[k] += deviance_gain(
                    f.y, f.off, f.x[permuted(rng, b2, len(f.y))], f.g, fe0
                )
            log(f"{group} {m} rows {len(rs)} gain {gr:.2f}")
        if not coefs:
            res[group] = {"fitted": False, "rows": nrows}
            continue
        p1 = (1 + int((null1 >= gain_real).sum())) / 201
        p2 = (1 + int((null2 >= gain_real).sum())) / 201
        s3: dict[str, Any] = {}
        drop: list[str] = []
        if group in ATTACK:
            for col, sign in S3_DIRECTIONS.items():
                vals = [
                    (v[0], v[1])
                    for cf in coefs.values()
                    for n, v in cf.items()
                    if n == col and v[1] > 0
                ]
                if not vals:
                    continue
                w = np.array([1 / s**2 for _, s in vals])
                est = float(np.dot(w, [v for v, _ in vals]) / w.sum())
                ok = est * sign >= 0
                s3[col] = [est, ok]
                if not ok:
                    state = col.split("_", 1)[1]
                    drop += [f"own_{state}", f"opp_{state}"]
        res[group] = {
            "fitted": True,
            "rows": nrows,
            "exposed": exposed,
            "gain": gain_real,
            "S1_p": p1,
            "S2_p": p2,
            "S1": p1 < 0.05,
            "S2": p2 < 0.05,
            "S3": s3,
            "S3_applicable": group in ATTACK,
            "drop": sorted(set(drop)),
            "coefs": coefs,
        }
        log(
            f"{group} gain {gain_real:.2f} S1 p {p1:.4f} S2 p {p2:.4f} S3 "
            f"{ {k: (round(v[0], 4), v[1]) for k, v in s3.items()} } "
            f"drop {sorted(set(drop))}"
        )
    EXPLORE_JSON.write_text(json.dumps(res, indent=1))


# --------------------------------------------------------------------------
# coefficients, treated centres, scores
def fit_coefs(
    rows: list[Row], group: str, lo: int, hi: int, drop: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """Shrunk coefficients per metric (c tau^2 / (tau^2 + SE^2)) with the
    raw value and SE kept beside."""
    cols = [c for c in COLS if c not in drop]
    out: dict[str, dict[str, Any]] = {}
    for m in group_metrics(group):
        rs = metric_rows(rows, m, lo, hi)
        if len(rs) < MIN_FIT_ROWS or not cols:
            continue
        f = fit_metric(rs, cols)
        out[m] = {
            c: {
                "shrunk": float(v * TAU**2 / (TAU**2 + s**2)),
                "raw": float(v),
                "se": float(s),
            }
            for c, v, s in zip(cols, f.b, f.se, strict=True)
        }
        out[m]["_rows"] = {"n": len(rs)}
    return out


def shrunk_of(coefs: dict[str, dict[str, Any]]) -> dict[str, dict[str, float]]:
    return {
        m: {c: float(v["shrunk"]) for c, v in cf.items() if not c.startswith("_")}
        for m, cf in coefs.items()
    }


def side_t(eid: int, side: str, cf: dict[str, float]) -> float:
    x = side_x(eid, side)
    return float(sum(cf.get(c, 0.0) * x[i] for i, c in enumerate(SIDE_COLS)))


def count_treat(rows: list[Row], frozen: dict[str, dict[str, float]]) -> F64:
    """`_for` x exp(t side); `_total` = sum of the sides each with its own t
    (schedule doprecyzowanie 3), sides' centres from the `_for` rows."""
    fors: dict[tuple[int, str, str], float] = {}
    for r in rows:
        if r["side"] is not None:
            fors[(r["eid"], r["market"], r["side"])] = r["centre"]
    out = np.empty(len(rows))
    for i, r in enumerate(rows):
        if r["side"] is not None:
            cf = frozen.get(r["market"])
            out[i] = (
                r["centre"] * math.exp(side_t(r["eid"], r["side"], cf))
                if cf
                else r["centre"]
            )
            continue
        m = r["market"][: -len("_total")] + "_for"
        cf = frozen.get(m)
        h, a = fors.get((r["eid"], m, "home")), fors.get((r["eid"], m, "away"))
        if cf and h is not None and a is not None:
            th, ta = side_t(r["eid"], "home", cf), side_t(r["eid"], "away", cf)
            out[i] = r["centre"] * (h * math.exp(th) + a * math.exp(ta)) / (h + a)
        else:
            out[i] = r["centre"]
    return out


def nb_logscore(y: F64, mu: F64, alpha: F64) -> F64:
    lg = np.vectorize(math.lgamma, otypes=[float])
    out = np.empty(len(y))
    pois = alpha <= 1e-9
    yp, mp = y[pois], mu[pois]
    out[pois] = -(yp * np.log(mp) - mp - lg(yp + 1))
    yn, mn, an = y[~pois], mu[~pois], alpha[~pois]
    r = 1 / an
    out[~pois] = -(
        lg(yn + r)
        - lg(r)
        - lg(yn + 1)
        + r * np.log(r / (r + mn))
        + yn * np.log(mn / (r + mn))
    )
    return out


def group_count_rows(
    rows: list[Row], group: str, frozen: dict[str, dict[str, float]]
) -> list[Row]:
    metrics = [m for m in GROUPS_ALL[group] if m in frozen]
    want = set(metrics) | {total_of(m) for m in metrics}
    return [r for r in rows if r["market"] in want]


def fr_probs(lh: float, la: float) -> tuple[float, float, float]:
    p = probabilities(lh, la, NB_R)
    return p["1x2:1"], 1.0 - p["1x2:1"] - p["1x2:2"], p["1x2:2"]


def fr_ll(rows: list[Row], cf: dict[str, float]) -> tuple[F64, F64, I64]:
    """Per match 1X2 log loss (base, treat) and the outcome index."""
    lb, lt, res = (
        np.empty(len(rows)),
        np.empty(len(rows)),
        np.empty(len(rows), dtype=np.int64),
    )
    for i, r in enumerate(rows):
        hg, ag = r["goals"]
        k = 0 if hg > ag else 2 if ag > hg else 1
        pb = fr_probs(r["lh"], r["la"])
        th, ta = side_t(r["eid"], "home", cf), side_t(r["eid"], "away", cf)
        pt = fr_probs(r["lh"] * math.exp(th), r["la"] * math.exp(ta))
        lb[i], lt[i], res[i] = -math.log(max(pb[k], EPS)), -math.log(max(pt[k], EPS)), k
    return lb, lt, res


def match_delta(rows: list[Row], diff: F64) -> tuple[F64, list[tuple[int, int]]]:
    per: dict[int, float] = defaultdict(float)
    meta: dict[int, tuple[int, int]] = {}
    for r, v in zip(rows, diff, strict=True):
        per[r["eid"]] += float(v)
        meta[r["eid"]] = (r["home"], r["away"])
    eids = list(per)
    return np.array([per[e] for e in eids]), [meta[e] for e in eids]


def boot2(
    diff: F64, pairs: list[tuple[int, int]], reps: int = 2000, seed: int = 5
) -> F64:
    rng = np.random.default_rng(seed)
    hi = {h: i for i, h in enumerate(sorted({h for h, _ in pairs}))}
    ai = {a: i for i, a in enumerate(sorted({a for _, a in pairs}))}
    h = np.array([hi[x] for x, _ in pairs])
    a = np.array([ai[x] for _, x in pairs])
    out = np.empty(reps)
    for k in range(reps):
        wh = rng.multinomial(len(hi), np.full(len(hi), 1 / len(hi)))
        wa = rng.multinomial(len(ai), np.full(len(ai), 1 / len(ai)))
        w = wh[h] * wa[a]
        out[k] = float((w * diff).sum()) / max(float(w.sum()), 1.0)
    return out


def group_delta(
    dev: dict[str, Any],
    group: str,
    frozen: dict[str, dict[str, float]],
    lo: int,
    hi: int,
) -> tuple[F64, list[tuple[int, int]], int]:
    if group == "football_result":
        rows = [r for r in dev["fr"] if lo <= r["ts"] < hi]
        lb, lt, _ = fr_ll(rows, frozen.get("goals_for", {}))
        d = lt - lb
        return d, [(r["home"], r["away"]) for r in rows], len(rows)
    sel = [
        r for r in group_count_rows(dev["count"], group, frozen) if lo <= r["ts"] < hi
    ]
    mt = count_treat(sel, frozen)
    y = np.array([r["y"] for r in sel])
    mb = np.array([r["centre"] for r in sel])
    al = np.array([r["alpha"] for r in sel])
    md, pairs = match_delta(sel, nb_logscore(y, mt, al) - nb_logscore(y, mb, al))
    # every population match of the window counts (ALIVE / ALIVE = 0)
    return md, pairs, len(sel)


def spec_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:12]


def validate(groups: list[str]) -> None:
    unknown = [g for g in groups if g not in ALL_GROUPS]
    if unknown:
        raise SystemExit(f"groups {unknown} are not in study {STUDY}")
    dev = load_pkl(SCRATCH / "dev.pkl")
    ex = json.loads(EXPLORE_JSON.read_text())
    for group in groups:
        e = ex[group]
        drop = e.get("drop", [])
        coefs = shrunk_of(
            fit_coefs(group_rows(dev, group), group, 0, EXPLORE_END, drop)
        )
        diff, pairs, nrows = group_delta(dev, group, coefs, EXPLORE_END, DEV_END)
        bt = boot2(diff, pairs)
        spec = spec_hash({"COLS": COLS, "drop": drop, "tau": TAU, "group": group})
        line = (
            f"| {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%MZ} | {group} | validate | "
            f"spec {spec} | "
            f"matches {len(diff)} rows {nrows} | Delta {diff.mean():+.6f} "
            f"[{np.quantile(bt, 0.025):+.6f}, {np.quantile(bt, 0.975):+.6f}] | "
            f"S4 {'pass' if diff.mean() < 0 else 'fail'} |\n"
        )
        with LOOKS.open("a") as f:
            f.write(line)
        log(line.rstrip())
        done = json.loads(VALIDATE_JSON.read_text()) if VALIDATE_JSON.exists() else {}
        done[group] = {
            "spec": spec,
            "matches": len(diff),
            "rows": nrows,
            "delta": float(diff.mean()),
            "q025": float(np.quantile(bt, 0.025)),
            "q975": float(np.quantile(bt, 0.975)),
            "S4": bool(diff.mean() < 0),
            "coef_explore": coefs,
        }
        VALIDATE_JSON.write_text(json.dumps(done, indent=1))


# --------------------------------------------------------------------------
def power() -> None:
    """S5 from the exam X (rows / forecasts only; no y store opened).
    n_req = 7.85 (1/mu + alpha) 1.75 / 0.03^2; exposed = distinct exam
    match-sides with the column = 1 among the group's `_for` rows (the spec's
    section 8 unit); the template's row count reported beside."""
    ex = json.loads(EXPLORE_JSON.read_text())
    c_of: dict[str, dict[str, float] | None] = {g: None for g in ALL_GROUPS}
    if STUDY_CFG.s5 == "frozen_coef":
        # the frozen (shrunk) full-match coefficient of each column: S5 is
        # power to see the term that would be installed (spec 8)
        doc = json.loads(COEF_FILE.read_text())
        for g in ALL_GROUPS:
            cf = doc["groups"][g]["coef"].get("goals_for", {})
            c_of[g] = {
                c: float(v["shrunk"]) for c, v in cf.items() if not c.startswith("_")
            }
    count_groups = [g for g in ALL_GROUPS if g in GROUPS]
    want = {m for g in count_groups for m in GROUPS[g]}
    rows = count_rows("exam", None, False, want)
    out: dict[str, Any] = {}
    for group in count_groups:
        rs = [r for r in rows if METRIC_GROUP.get(r["market"]) == group]
        out[group] = _power_of(rs, ex[group].get("drop", []), c_of[group])
    if "football_result" in ALL_GROUPS:
        fr = fr_rows("exam", None, False)
        out["football_result"] = _power_of(
            fr_side_rows_x(fr),
            ex["football_result"].get("drop", []),
            c_of["football_result"],
        )
    if all(g in ALL_GROUPS for g in POOL_OF):
        pool = [r for r in rows if METRIC_GROUP.get(r["market"]) in POOL_OF]
        out["pool_shots_sot_corners"] = _power_of(
            pool,
            sorted(
                set(ex["shots_sot"].get("drop", []))
                | set(ex["corners"].get("drop", []))
            ),
        )
    for g, v in out.items():
        log(
            f"S5 {g} rows {v['rows']} mu {v['mu']:.3f} alpha {v['alpha']:.3f} "
            f"n_req {v['n_req']:.0f} best {v['best']} {v['best_sides']} "
            f"pass {v['pass']}"
        )
    POWER_JSON.write_text(json.dumps(out, indent=1))


def submit() -> None:
    """The submission (template: S1-S5 all hold, else the pre-registered pool
    or nothing), after the freeze and before any exam y: S1-S4 from the frozen
    dev snapshot, S5 from power() on the exam X. Conservative reading: the
    pool goes only when both of its groups hold S1-S4 and one of them lacks
    S5 alone; it then replaces both."""
    rec = json.loads(FREEZE_RECORD.read_text())
    if sha256(COEF_FILE) != rec["coefficients_sha256"]:
        raise SystemExit("coefficients.json changed after the freeze")
    if sha256(Path(__file__)) != rec["script_sha256"]:
        raise SystemExit("measure_stakes_exam.py changed after the freeze")
    doc = json.loads(COEF_FILE.read_text())
    pw = json.loads(POWER_JSON.read_text())
    gates: dict[str, dict[str, Any]] = {}
    for g in ALL_GROUPS:
        d = doc["groups"][g]["dev_gates"]
        coef = doc["groups"][g]["coef"]
        left = [c for cf in coef.values() for c in cf if not c.startswith("_")]
        s3 = (not d["S3_applicable"]) or bool(left)
        gates[g] = {
            "S1": bool(d["S1"]),
            "S2": bool(d["S2"]),
            "S3": s3,
            "S4": bool(d["S4"]),
            "S5": bool(pw[g]["pass"]),
            "columns_left": sorted(set(left)),
        }
        gates[g]["S1_S4"] = all(gates[g][k] for k in ("S1", "S2", "S3", "S4"))
    submitted = [
        g
        for g in ALL_GROUPS
        if g not in POOL_OF and gates[g]["S1_S4"] and gates[g]["S5"]
    ]
    pool_note = "pool not needed"
    a, b = POOL_OF
    if not (a in gates and b in gates):
        pool_note = "no pool in this study"
        submitted += [
            g for g in POOL_OF if g in gates and gates[g]["S1_S4"] and gates[g]["S5"]
        ]
    elif gates[a]["S1_S4"] and gates[b]["S1_S4"]:
        if gates[a]["S5"] and gates[b]["S5"]:
            submitted += [a, b]
        elif pw["pool_shots_sot_corners"]["pass"]:
            submitted.append(POOL)
            pool_note = "pool submitted (a member lacks S5 alone)"
        else:
            pool_note = "pool lacks S5 too: neither submitted"
    else:
        for g in POOL_OF:
            if gates[g]["S1_S4"] and gates[g]["S5"]:
                submitted.append(g)
        pool_note = "pool not formed (a member fails S1-S4)"
    out = {
        "written_at_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "coefficients_sha256": rec["coefficients_sha256"],
        "gates": gates,
        "power": pw,
        "pool": pool_note,
        "submitted": submitted,
        "K": len(submitted),
    }
    RUN.mkdir(parents=True, exist_ok=True)
    SUBMISSION.write_text(json.dumps(out, indent=1) + "\n")
    SUBMISSION_RECORD.write_text(
        json.dumps({"submission_sha256": sha256(SUBMISSION)}, indent=1) + "\n"
    )
    log(f"submitted {submitted} K {len(submitted)}; {pool_note}")
    for g, v in gates.items():
        log(f"  {g} {v}")


def frozen_coef(doc: dict[str, Any], name: str) -> dict[str, dict[str, Any]]:
    if name == POOL:
        out: dict[str, dict[str, Any]] = {}
        for g in POOL_OF:
            out.update(doc["groups"][g]["coef"])
        return out
    coef: dict[str, dict[str, Any]] = doc["groups"][name]["coef"]
    return coef


def fr_side_rows_x(rows: list[Row]) -> list[Row]:
    out: list[Row] = []
    for r in rows:
        for side, c in (("home", r["lh"]), ("away", r["la"])):
            out.append({"eid": r["eid"], "side": side, "centre": c, "alpha": 0.0})
    return out


def _power_of(
    rs: list[Row], drop: Sequence[str], c_of: dict[str, float] | None = None
) -> dict[str, Any]:
    """S5. ``c_of`` None: one n_req at |c| = 0.03 (the 2026-11-18 rule);
    else each column's own n_req at its |c| (the study's frozen
    coefficient), and the group holds when any kept column reaches its
    own."""
    fors = [r for r in rs if r["side"] is not None]
    if not fors:
        return {
            "rows": 0,
            "mu": float("nan"),
            "alpha": float("nan"),
            "n_req": float("inf"),
            "best": None,
            "best_sides": 0,
            "pass": False,
            "sides": {},
            "row_counts": {},
        }
    mu = float(np.mean([r["centre"] for r in fors]))
    al = float(np.mean([r["alpha"] for r in fors]))
    need = 7.85 * (1 / mu + al) * 1.75 / 0.03**2
    sides: dict[str, set[tuple[int, str]]] = defaultdict(set)
    rowc: dict[str, int] = defaultdict(int)
    for r in fors:
        x = side_x(r["eid"], r["side"])
        for i, c in enumerate(SIDE_COLS):
            if x[i]:
                sides[c].add((r["eid"], r["side"]))
                rowc[c] += 1
    kept = {c: len(v) for c, v in sides.items() if c in COLS and c not in drop}
    if c_of is None:
        best = max(kept, key=lambda c: kept[c]) if kept else None
        ok = bool(best and kept[best] >= need)
        need_of = dict.fromkeys(kept, need)
    else:
        need_of = {
            c: 7.85 * (1 / mu + al) * 1.75 / max(abs(c_of.get(c, 0.0)), 1e-9) ** 2
            for c in kept
        }
        best = max(kept, key=lambda c: kept[c] / need_of[c]) if kept else None
        ok = bool(best and kept[best] >= need_of[best])
        need = need_of[best] if best else float("inf")
    return {
        "rows": len(fors),
        "mu": mu,
        "alpha": al,
        "n_req": need,
        "n_req_by_column": need_of,
        "c_by_column": c_of,
        "best": best,
        "best_sides": kept.get(best, 0) if best else 0,
        "pass": ok,
        "sides": {c: len(v) for c, v in sides.items()},
        "row_counts": dict(rowc),
    }


# --------------------------------------------------------------------------
def freeze(spec_sha: str) -> None:
    dev = load_pkl(SCRATCH / "dev.pkl")
    ex = json.loads(EXPLORE_JSON.read_text())
    doc: dict[str, Any] = {
        "_doc": (
            "Frozen shrunk dev coefficients of the football stakes term "
            f"(study {STUDY}, pre-registration {STUDY_CFG.prereg}, spec {spec_sha}): "
            "t_side = sum coef[own_<state of side>] + coef[opp_<state of opponent>], "
            "ALIVE = 0, per (base metric, half); fitted on exploration + validation "
            "(< 2026-01-01), c_shr = c tau^2 / (tau^2 + SE^2). "
            "A PROPOSAL only: nothing "
            "is installed; only the groups that PASS the exam would be."
        ),
        "tau": TAU,
        "cols": COLS,
        "frozen_at_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "module_sha256": MODULE_SHA256,
        "spec_sha": spec_sha,
        "study": STUDY,
        "unfitted_constants": [
            "Z boundary (3 at n <= 16 else 4)",
            "boundaries {1, n - Z}",
            "exact enumeration r <= 8",
            "12 teams",
            "25% inferred",
            "30 days season in progress",
            "tau 0.05",
        ],
        "groups": {},
    }
    for group in ALL_GROUPS:
        drop = ex[group].get("drop", [])
        doc["groups"][group] = {
            "drop": drop,
            "coef": fit_coefs(group_rows(dev, group), group, 0, DEV_END, drop),
        }
    val = json.loads(VALIDATE_JSON.read_text())
    for group in ALL_GROUPS:
        e = ex[group]
        doc["groups"][group]["dev_gates"] = {
            "S1_p": e.get("S1_p"),
            "S2_p": e.get("S2_p"),
            "S1": e.get("S1", False),
            "S2": e.get("S2", False),
            "S3": e.get("S3", {}),
            "S3_applicable": e.get("S3_applicable", False),
            "S4_delta": val.get(group, {}).get("delta"),
            "S4": val.get(group, {}).get("S4", False),
        }
    RUN.mkdir(parents=True, exist_ok=True)
    COEF_FILE.write_text(json.dumps(doc, indent=1) + "\n")
    rec = {
        "coefficients_sha256": sha256(COEF_FILE),
        "script_sha256": sha256(Path(__file__)),
        "guard_sha256": sha256(GUARD_MODULE),
        "spec_sha": spec_sha,
        "written_at_utc": doc["frozen_at_utc"],
    }
    FREEZE_RECORD.write_text(json.dumps(rec, indent=1) + "\n")
    log(f"frozen -> {COEF_FILE} sha256 {rec['coefficients_sha256']}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# exam statistics (measure_schedule_exam.py, unchanged arithmetic)
def cluster_boot(
    num: F64,
    den: F64,
    factors: list[tuple[int, list[I64]]],
    reps: int = REPS,
    seed: int = 7,
) -> F64:
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
    return max(float((boot >= 0).mean()), 1.0 / len(boot))


def holm(pvals: dict[str, float], alpha: float = ALPHA) -> dict[str, dict[str, Any]]:
    k = len(pvals)
    out: dict[str, dict[str, Any]] = {}
    still = True
    for i, (g, p) in enumerate(sorted(pvals.items(), key=lambda t: (t[1], t[0]))):
        level = alpha / (k - i)
        reject = still and p <= level
        still = reject
        out[g] = {"p": p, "level": level, "reject": reject}
    return out


@dataclass(frozen=True)
class Bound:
    point: float
    upper95: float
    lower025: float
    upper975: float
    n: int


def row_bound(
    row_match: I64,
    values: F64,
    mask: B,
    n_match: int,
    factors: list[tuple[int, list[I64]]],
    seed: int,
) -> Bound:
    n = int(mask.sum())
    if n == 0:
        nan = float("nan")
        return Bound(nan, nan, nan, nan, 0)
    num = np.bincount(row_match[mask], weights=values[mask], minlength=n_match).astype(
        float
    )
    den = np.bincount(row_match[mask], minlength=n_match).astype(float)
    boot = cluster_boot(num, den, factors, seed=seed)
    return Bound(
        float(num.sum() / den.sum()),
        float(np.quantile(boot, 0.95)),
        float(np.quantile(boot, 0.025)),
        float(np.quantile(boot, 0.975)),
        n,
    )


def football_clusters(home: I64, away: I64) -> list[tuple[int, list[I64]]]:
    _, h = np.unique(home, return_inverse=True)
    _, a = np.unique(away, return_inverse=True)
    return [
        (int(h.max()) + 1, [h.astype(np.int64)]),
        (int(a.max()) + 1, [a.astype(np.int64)]),
    ]


def bucket(p: F64) -> I64:
    b = np.searchsorted(np.asarray(EDGES), p, side="right") - 1
    out: I64 = np.clip(b, 0, len(EDGES) - 2).astype(np.int64)
    return out


def wilson_lo(k: F64, n: F64, z: float = 1.959964) -> F64:
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    out: F64 = np.maximum(0.0, c - m)
    return out


class Curves:
    """P3 dev curves per arm: EDGES buckets per (market, direction) key, Wilson
    lo95, key bucket >= 400 rows else the group's pooled bucket >= 200."""

    def __init__(self, p: F64, y: F64, key: I64, nkeys: int) -> None:
        nb = len(EDGES) - 1
        b = bucket(np.round(p, 6))
        code = key * nb + b
        n = np.bincount(code, minlength=nkeys * nb).astype(float)
        k = np.bincount(code, weights=y.astype(float), minlength=nkeys * nb)
        self.key_val = np.where(
            n >= MIN_MARKET_BUCKET,
            wilson_lo(k.astype(float), np.maximum(n, 1.0)),
            np.nan,
        )
        pn = np.bincount(b, minlength=nb).astype(float)
        pk = np.bincount(b, weights=y.astype(float), minlength=nb)
        self.pool_val = np.where(
            pn >= MIN_POOLED_BUCKET,
            wilson_lo(pk.astype(float), np.maximum(pn, 1.0)),
            np.nan,
        )
        self.nb = nb

    def apply(self, p: F64, key: I64) -> F64:
        b = bucket(np.round(p, 6))
        v = self.key_val[key * self.nb + b]
        out: F64 = np.where(np.isnan(v), self.pool_val[b], v)
        return out


@dataclass
class Lines:
    match: I64
    cb: F64
    ct: F64
    y: F64
    dropped: int


def calibrated_lines(
    dev: tuple[F64, F64, F64, I64], exam: tuple[F64, F64, F64, I64, I64], nkeys: int
) -> Lines:
    pb_d, pt_d, y_d, k_d = dev
    cur_b, cur_t = Curves(pb_d, y_d, k_d, nkeys), Curves(pt_d, y_d, k_d, nkeys)
    pb, pt, y, k, m = exam
    cb, ct = cur_b.apply(pb, k), cur_t.apply(pt, k)
    ok = ~(np.isnan(cb) | np.isnan(ct))
    return Lines(m[ok], cb[ok], ct[ok], y[ok].astype(float), int((~ok).sum()))


def survival_table(mean: F64, alpha: F64) -> F64:
    """nbvec.survival_table (engine.nb_survival, vectorised)."""
    var = mean + alpha * mean * mean
    pois = var <= mean * (1.0 + 1e-9)
    out = np.empty((len(mean), KMAX))
    r = np.where(pois, 1.0, mean * mean / np.where(pois, 1.0, var - mean))
    p = r / (r + mean)
    pmf = np.exp(r * np.log(p))
    acc = pmf.copy()
    q = 1.0 - p
    pm = np.exp(-mean)
    acc_p = pm.copy()
    for k in range(KMAX):
        if k > 0:
            pmf = pmf * (k - 1 + r) / k * q
            acc = acc + pmf
            pm = pm * mean / k
            acc_p = acc_p + pm
        a = np.where(pois, acc_p, acc)
        out[:, k] = np.maximum(0.0, 1.0 - np.minimum(a, 1.0))
    out[mean <= 0.0] = 0.0
    return out


def p_lines(mean: F64, alpha: F64, lowest: F64) -> F64:
    s = survival_table(mean, alpha)
    idx = lowest[:, None].astype(int) + np.arange(9)[None, :]
    out: F64 = np.take_along_axis(s, np.minimum(idx, KMAX - 1), axis=1)
    return out


def count_lines(
    rows: list[Row], mt: F64, key_of: dict[str, int], match: I64 | None
) -> tuple[Any, ...]:
    mb = np.array([r["centre"] for r in rows], dtype=float)
    al = np.array([r["alpha"] for r in rows], dtype=float)
    y = np.array([r["y"] for r in rows], dtype=float)
    low = np.maximum(0, np.floor(mb) - 4)
    pb, pt = p_lines(mb, al, low), p_lines(mt, al, low)
    yo = (y[:, None] > (low[:, None] + np.arange(9)[None, :])).astype(np.int8)
    mk = np.array([key_of[r["market"]] for r in rows], dtype=np.int64)
    keys = np.concatenate([np.repeat(2 * mk, 9), np.repeat(2 * mk + 1, 9)])
    pbs = np.concatenate([pb.ravel(), 1 - pb.ravel()])
    pts = np.concatenate([pt.ravel(), 1 - pt.ravel()])
    ys = np.concatenate([yo.ravel(), 1 - yo.ravel()]).astype(float)
    if match is None:
        return pbs, pts, ys, keys
    return (
        pbs,
        pts,
        ys,
        keys,
        np.concatenate([np.repeat(match, 9), np.repeat(match, 9)]),
    )


def fr_lines(
    rows: list[Row], cf: dict[str, float], match: I64 | None
) -> tuple[Any, ...]:
    pb, pt, y, k = [], [], [], []
    for r in rows:
        hg, ag = r["goals"]
        res = 0 if hg > ag else 2 if ag > hg else 1
        b = fr_probs(r["lh"], r["la"])
        th, ta = side_t(r["eid"], "home", cf), side_t(r["eid"], "away", cf)
        t = fr_probs(r["lh"] * math.exp(th), r["la"] * math.exp(ta))
        for j in range(3):
            pb.append(b[j])
            pt.append(t[j])
            y.append(float(res == j))
            k.append(j)
    arr = (np.array(pb), np.array(pt), np.array(y), np.array(k, dtype=np.int64))
    if match is None:
        return arr
    return (*arr, np.repeat(match, 3))


def ll(p: F64, y: F64) -> F64:
    q = np.clip(p, EPS, 1 - EPS)
    out: F64 = -(y * np.log(q) + (1 - y) * np.log(1 - q))
    return out


def p4_check(cb: F64, ct: F64, y: F64) -> dict[str, Any]:
    sel = cb >= 0.70
    if not sel.any():
        return {"pass": False, "rows": 0, "note": "no baseline row >= 0.70"}
    r = float(y[sel].mean())
    gap_b, gap_t = abs(r - float(cb[sel].mean())), abs(r - float(ct[sel].mean()))
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


# --------------------------------------------------------------------------
@dataclass
class GroupData:
    match_diff: F64
    factors: list[tuple[int, list[I64]]]
    row_match: I64
    row_diff: F64
    strata: dict[str, B]
    lines: Lines
    p2: dict[str, Any]
    p6: dict[str, Any]
    women: dict[str, Any] = field(default_factory=dict)
    info: dict[str, Any] = field(default_factory=dict)


_CTX: dict[str, Any] = {}


def strata_ctx() -> dict[str, Any]:
    """Favourite |supremacy| tercile edges from the dev population (book 1
    forecasts) and the continental competition ids."""
    if _CTX:
        return _CTX
    sup: dict[int, float] = {}
    for tier in sorted({"dev", WIN["tier"]}):
        for rec in read_chunks(tier, "forecasts"):
            if rec[5] == 1 and rec[7] is not None:
                sup[int(rec[0])] = abs(float(rec[7]))
    pop = population()
    dev_s = np.array(
        [
            v
            for e, v in sup.items()
            if e in pop.states and pop.states[e]["ts"] < DEV_END and in_pop(e, False)
        ]
    )
    cont = {
        int(c)
        for c in json.loads((REPO / "config/sofa_cup_strength.json").read_text())[
            "competitions"
        ]
    }
    _CTX.update(sup=sup, edges=np.quantile(dev_s, [1 / 3, 2 / 3]), cont=cont)
    return _CTX


def strata_of(eids: I64, sides: list[str | None]) -> dict[str, B]:
    c = strata_ctx()
    pop = population()
    s = np.array([c["sup"].get(int(e), np.nan) for e in eids])
    lo, hi = c["edges"]
    st = [pop.states[int(e)] for e in eids]
    cont = np.array([pop.ut.get(int(e), -1) in c["cont"] for e in eids], dtype=bool)
    ko = np.array([bool(x["ko"]) for x in st], dtype=bool)
    exact = np.array([bool(x["exact"]) for x in st], dtype=bool)
    tb = np.array([bool(x["tb_home"]) or bool(x["tb_away"]) for x in st], dtype=bool)
    left = np.array(
        [min(int(x["left_home"]), int(x["left_away"])) <= 3 for x in st], dtype=bool
    )
    return {
        "fav_s_t1": s < lo,
        "fav_s_t2": (s >= lo) & (s < hi),
        "fav_s_t3": s >= hi,
        "continental": cont,
        "domestic": ~cont,
        "ko_rounds": ko,
        "no_ko_rounds": ~ko,
        "exact": exact,
        "bounds": ~exact,
        "tb": tb,
        "no_tb": ~tb,
        "left_le3": left,
        "left_gt3": ~left,
    }


def match_index(eids: I64) -> tuple[I64, I64]:
    u, inv = np.unique(eids, return_inverse=True)
    return u.astype(np.int64), inv.astype(np.int64)


def exposure_material(
    frozen: dict[str, dict[str, float]], rows: list[Row]
) -> dict[str, Any]:
    """P2: any frozen |c| >= 0.03 on a state column (own / opp) that is 1 on
    >= 2% of the group's exam `_for` rows."""
    n = 0
    exp_: dict[str, int] = defaultdict(int)
    for r in rows:
        if r["side"] is None:
            continue
        n += 1
        x = side_x(r["eid"], r["side"])
        for i, c in enumerate(SIDE_COLS):
            exp_[c] += int(x[i] > 0)
        exp_["_any_study_column"] += int(
            any(x[SIDE_COLS.index(c)] > 0 for c in COLS)
        )
    share = {k: v / max(n, 1) for k, v in exp_.items()}

    def exposed(c: str) -> float:
        # p2 "any_column": the bucket is every row the term touches
        return share.get(
            "_any_study_column" if STUDY_CFG.p2 == "any_column" else c, 0.0
        )

    hits = [
        {"metric": m, "coef": c, "c": v, "exposed_share": exposed(c)}
        for m, cf in frozen.items()
        for c, v in cf.items()
        if abs(v) >= 0.03 and exposed(c) >= 0.02
    ]
    return {
        "material": bool(hits),
        "hits": hits,
        "rows": n,
        "p2_rule": STUDY_CFG.p2,
        "exposure": share,
    }


def refit_signs(
    rows: list[Row], frozen_cols: dict[str, list[str]], hits: list[dict[str, Any]]
) -> dict[str, Any]:
    out: list[dict[str, Any]] = []
    by_metric: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for h in hits:
        by_metric[h["metric"]].append(h)
    for m, hs in by_metric.items():
        rs = metric_rows(rows, m, WIN["lo"], WIN["hi"])
        if len(rs) < MIN_FIT_ROWS:
            out += [
                {**h, "exam_b": None, "same_sign": False, "note": "< 2000 rows"}
                for h in hs
            ]
            continue
        f = fit_metric(rs, frozen_cols[m])
        for h in hs:
            i = f.cols.index(h["coef"])
            v = float(f.b[i])
            out.append(
                {
                    **h,
                    "exam_b": v,
                    "exam_se": float(f.se[i]),
                    "same_sign": bool(np.sign(v) == np.sign(h["c"])),
                }
            )
    return {"pass": bool(out) and all(o["same_sign"] for o in out), "coefs": out}


def women_layer(diff: F64, pairs: list[tuple[int, int]], nrows: int) -> dict[str, Any]:
    if len(diff) == 0:
        return {"matches": 0}
    bt = boot2(diff, pairs, seed=77)
    return {
        "matches": len(diff),
        "rows": nrows,
        "delta_match": float(diff.mean()),
        "q025": float(np.quantile(bt, 0.025)),
        "q975": float(np.quantile(bt, 0.975)),
        "upper95": float(np.quantile(bt, 0.95)),
    }


def exam_count_group(
    group: str,
    frozen: dict[str, dict[str, float]],
    cols: dict[str, list[str]],
    ys: dict[tuple[Any, ...], float] | None,
    rng: np.random.Generator | None,
    dev_rows: list[Row],
) -> GroupData:
    metrics = set(GROUPS_ALL[group]) | {total_of(m) for m in GROUPS_ALL[group]}
    ex = group_count_rows(
        count_rows(WIN["tier"], ys, False, metrics, rng), group, frozen
    )
    mt = count_treat(ex, frozen)
    y = np.array([r["y"] for r in ex])
    mb = np.array([r["centre"] for r in ex])
    al = np.array([r["alpha"] for r in ex])
    row_diff = nb_logscore(y, mt, al) - nb_logscore(y, mb, al)
    eids = np.array([r["eid"] for r in ex], dtype=np.int64)
    u, inv = match_index(eids)
    match_diff = np.bincount(inv, weights=row_diff, minlength=len(u)).astype(float)
    first: dict[int, int] = {}
    for i, e in enumerate(inv):
        first.setdefault(int(e), i)
    fi = np.array([first[k] for k in range(len(u))])
    home = np.array([ex[i]["home"] for i in fi], dtype=np.int64)
    away = np.array([ex[i]["away"] for i in fi], dtype=np.int64)
    strata = strata_of(eids, [r["side"] for r in ex])
    markets = sorted(metrics)
    key_of = {m: i for i, m in enumerate(markets)}
    dsel = group_count_rows(dev_rows, group, frozen)
    lines = calibrated_lines(
        count_lines(dsel, count_treat(dsel, frozen), key_of, None),
        count_lines(ex, mt, key_of, inv),
        2 * len(markets),
    )
    p2 = exposure_material(frozen, ex)
    p6 = (
        refit_signs(ex, cols, p2["hits"])
        if ys is not None
        else {"pass": None, "coefs": [], "note": "fake mode"}
    )
    wx = group_count_rows(
        count_rows(WIN["tier"], ys, True, metrics, rng), group, frozen
    )
    wdiff = (
        (
            nb_logscore(
                np.array([r["y"] for r in wx]),
                count_treat(wx, frozen),
                np.array([r["alpha"] for r in wx]),
            )
            - nb_logscore(
                np.array([r["y"] for r in wx]),
                np.array([r["centre"] for r in wx]),
                np.array([r["alpha"] for r in wx]),
            )
        )
        if wx
        else np.zeros(0)
    )
    wmd, wpairs = match_delta(wx, wdiff) if wx else (np.zeros(0), [])
    return GroupData(
        match_diff,
        football_clusters(home, away),
        inv,
        row_diff,
        strata,
        lines,
        p2,
        p6,
        women={
            "layer": women_layer(wmd, wpairs, len(wx)),
            "row_diff": wdiff,
            "rows": wx,
        },
        info={"rows": len(ex), "matches": len(u)},
    )


def exam_fr_group(
    frozen: dict[str, dict[str, float]],
    cols: dict[str, list[str]],
    ys: dict[int, tuple[int, int]] | None,
    rng: np.random.Generator | None,
    dev_fr: list[Row],
) -> GroupData:
    cf = frozen.get("goals_for", {})
    ex = fr_rows(WIN["tier"], ys, False, rng, (WIN["lo"], WIN["hi"]))
    lb, lt, _ = fr_ll(ex, cf)
    row_diff = lt - lb
    eids = np.array([r["eid"] for r in ex], dtype=np.int64)
    m = np.arange(len(ex), dtype=np.int64)
    strata = strata_of(eids, [None] * len(ex))
    lines = calibrated_lines(fr_lines(dev_fr, cf, None), fr_lines(ex, cf, m), 3)
    side_rows = (
        fr_side_rows(ex)
        if ys is not None
        else [
            {"eid": r["eid"], "side": s, "market": "goals_for"}
            for r in ex
            for s in ("home", "away")
        ]
    )
    p2 = exposure_material(frozen, side_rows)
    p6 = (
        refit_signs(side_rows, cols, p2["hits"])
        if ys is not None
        else {"pass": None, "coefs": [], "note": "fake mode"}
    )
    wx = fr_rows(WIN["tier"], ys, True, rng, (WIN["lo"], WIN["hi"]))
    wlb, wlt, _ = fr_ll(wx, cf) if wx else (np.zeros(0), np.zeros(0), np.zeros(0))
    wdiff = wlt - wlb
    home = np.array([r["home"] for r in ex], dtype=np.int64)
    away = np.array([r["away"] for r in ex], dtype=np.int64)
    return GroupData(
        row_diff.copy(),
        football_clusters(home, away),
        m,
        row_diff,
        strata,
        lines,
        p2,
        p6,
        women={
            "layer": women_layer(wdiff, [(r["home"], r["away"]) for r in wx], len(wx)),
            "row_diff": wdiff,
            "rows": wx,
        },
        info={"matches": len(ex)},
    )


def evaluate(groups: dict[str, GroupData]) -> dict[str, Any]:
    res: dict[str, Any] = {}
    pvals: dict[str, float] = {}
    boots: dict[str, F64] = {}
    for i, (name, g) in enumerate(groups.items()):
        md = g.match_diff
        boot = cluster_boot(md, np.ones(len(md)), g.factors, seed=100 + i)
        boots[name], pvals[name] = boot, one_sided_p(boot)
        n_match = len(md)
        lines = g.lines
        lb = row_bound(
            lines.match,
            ll(lines.ct, lines.y) - ll(lines.cb, lines.y),
            np.ones(len(lines.y), dtype=bool),
            n_match,
            g.factors,
            200 + i,
        )
        strata: dict[str, Any] = {}
        for s, mask in g.strata.items():
            b = row_bound(g.row_match, g.row_diff, mask, n_match, g.factors, 300 + i)
            gate = b.n >= P5_MIN_STRATUM_ROWS
            strata[s] = {
                "point": b.point,
                "upper95": b.upper95,
                "rows": b.n,
                "gated": gate,
                "pass": (b.upper95 < P5_STRATUM_UPPER) if gate else None,
            }
        # women: a stratum of the pre-registered list (men's coefficients)
        wl = g.women["layer"]
        wrows = g.women["rows"]
        if wrows:
            weid = np.array([r["eid"] for r in wrows], dtype=np.int64)
            wu, winv = match_index(weid)
            first: dict[int, int] = {}
            for j, e in enumerate(winv):
                first.setdefault(int(e), j)
            fi = np.array([first[k] for k in range(len(wu))])
            wf = football_clusters(
                np.array([wrows[j]["home"] for j in fi], dtype=np.int64),
                np.array([wrows[j]["away"] for j in fi], dtype=np.int64),
            )
            wb = row_bound(
                winv,
                np.asarray(g.women["row_diff"], dtype=float),
                np.ones(len(winv), dtype=bool),
                len(wu),
                wf,
                350 + i,
            )
            gate = wb.n >= P5_MIN_STRATUM_ROWS
            strata["women"] = {
                "point": wb.point,
                "upper95": wb.upper95,
                "rows": wb.n,
                "gated": gate,
                "pass": (wb.upper95 < P5_STRATUM_UPPER) if gate else None,
            }
        whole = row_bound(
            g.row_match,
            g.row_diff,
            np.ones(len(g.row_diff), dtype=bool),
            n_match,
            g.factors,
            500 + i,
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
                "other_groups": {
                    "all": {
                        "pass": True,
                        "note": (
                            "0 by construction: each group's term touches only "
                            "its own rows "
                            "(path (i) per metric; path (ii) only the "
                            "rating result rows)"
                        ),
                    }
                },
                "pass": all(v["pass"] is not False for v in strata.values()),
            },
            "P6": g.p6,
            "women_layer": wl,
        }
    hm = holm(pvals)
    for name, r in res.items():
        h = hm[name]
        r["P1"].update(
            holm_level=h["level"],
            upper_at_level=float(np.quantile(boots[name], 1 - h["level"])),
            pass_=bool(h["reject"]),
        )
        ok = (
            r["P1"]["pass_"]
            and bool(r["P2"]["material"])
            and r["P3"]["pass"]
            and r["P4"]["pass"]
            and r["P5"]["pass"]
            and r["P6"].get("pass") is True
        )
        r["verdict"] = "PASS" if ok else "NOT_PASSED"
    return res


def git_blob_sha256(sha: str, rel: str) -> str:
    out = subprocess.run(
        ["git", "show", f"{sha}:{rel}"], cwd=REPO, capture_output=True, check=True
    )
    return hashlib.sha256(out.stdout).hexdigest()


def check_guards(spec_sha: str) -> dict[str, str]:
    """G1: the module at the spec commit and on disk is the frozen one; the
    coefficient file and this script are the ones hashed at freeze time."""
    subprocess.run(
        ["git", "cat-file", "-e", f"{spec_sha}^{{commit}}"], cwd=REPO, check=True
    )
    h_disk = sha256(REPO / MODULE_REL)
    h_com = git_blob_sha256(spec_sha, MODULE_REL)
    h_run = sha256(STATES_DIR / "stakes_state.py")
    if not (h_disk == h_com == h_run == MODULE_SHA256):
        raise SystemExit(
            f"G1: stakes_state.py sha256 differs ({h_disk} / {h_com} / {h_run})"
        )
    rec = json.loads(FREEZE_RECORD.read_text())
    if sha256(COEF_FILE) != rec["coefficients_sha256"]:
        raise SystemExit("G1: coefficients.json changed after the freeze")
    if sha256(Path(__file__)) != rec["script_sha256"]:
        raise SystemExit("G1: measure_stakes_exam.py changed after the freeze")
    if "guard_sha256" in rec and sha256(GUARD_MODULE) != rec["guard_sha256"]:
        raise SystemExit("G1: stakes_exam_guard.py changed after the freeze")
    if rec.get("spec_sha", spec_sha) != spec_sha:
        raise SystemExit(f"G1: frozen on spec {rec['spec_sha']}, not {spec_sha}")
    prereg = subprocess.run(
        ["git", "cat-file", "-e", f"{spec_sha}:{STUDY_CFG.prereg}"], cwd=REPO
    )
    if prereg.returncode != 0:
        raise SystemExit(f"G1: {STUDY_CFG.prereg} is not in commit {spec_sha}")
    return {
        "module": h_disk,
        "coefficients": rec["coefficients_sha256"],
        "script": rec["script_sha256"],
    }


def exam_preflight(spec_sha: str) -> dict[str, str]:
    """Every refusal of the exam mode before an outcome is opened: G1 hashes,
    G1 by commit (A2) and the seal (A3)."""
    hashes = check_guards(spec_sha)
    problems = guard.uncommitted(
        REPO,
        [
            COEF_FILE,
            FREEZE_RECORD,
            SUBMISSION,
            SUBMISSION_RECORD,
            SCRIPT,
            GUARD_MODULE,
            REPO / MODULE_REL,
        ],
    )
    problems += guard.seal_problems(SCRATCH, SEAL_MANIFEST, SEAL_PATTERNS)
    if problems:
        raise SystemExit("refused (exam): " + "; ".join(problems))
    return hashes


def exam_already_run() -> bool:
    return EXAM_LOG.exists() and any(
        f"| {STUDY} |" in ln for ln in EXAM_LOG.read_text().splitlines()
    )


def exam(mode: str, spec_sha: str) -> int:
    if mode == "exam" and exam_already_run():
        print(
            f"refused: {EXAM_LOG} already holds a line of {STUDY} (G2)", file=sys.stderr
        )
        return 2
    started = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    dev = load_pkl(SCRATCH / "dev.pkl")
    rng = np.random.default_rng(FAKE_SEED) if mode == "fake" else None
    dev_count: list[Row] = dev["count"]
    dev_fr: list[Row] = dev["fr"]
    if mode == "devtest":
        # Plumbing on the dev tier only: explore-only coefficients scored on
        # the validation months with their real dev y; curves from explore.
        WIN.update(tier="dev", lo=EXPLORE_END, hi=DEV_END)
        hashes = {"note": "devtest - no guards"}
        ex = json.loads(EXPLORE_JSON.read_text())
        doc: dict[str, Any] = {"groups": {}}
        for g in ALL_GROUPS:
            if ex[g].get("fitted"):
                doc["groups"][g] = {
                    "coef": fit_coefs(
                        group_rows(dev, g), g, 0, EXPLORE_END, ex[g].get("drop", [])
                    )
                }
        submitted = list(doc["groups"])
        dev_count = [r for r in dev_count if r["ts"] < EXPLORE_END]
        dev_fr = [r for r in dev_fr if r["ts"] < EXPLORE_END]
    elif mode == "exam":
        hashes = exam_preflight(spec_sha)
        doc = json.loads(COEF_FILE.read_text())
        srec = json.loads(SUBMISSION_RECORD.read_text())
        if sha256(SUBMISSION) != srec["submission_sha256"]:
            raise SystemExit("G1: submission.json changed after it was written")
        sub = json.loads(SUBMISSION.read_text())
        if sub["coefficients_sha256"] != hashes["coefficients"]:
            raise SystemExit("G1: submission made on other coefficients")
        submitted = sub["submitted"]
        hashes["submission"] = srec["submission_sha256"]
    else:
        hashes = check_guards(spec_sha)
        doc = json.loads(COEF_FILE.read_text())
        srec = json.loads(SUBMISSION_RECORD.read_text())
        if sha256(SUBMISSION) != srec["submission_sha256"]:
            raise SystemExit("G1: submission.json changed after it was written")
        sub = json.loads(SUBMISSION.read_text())
        if sub["coefficients_sha256"] != hashes["coefficients"]:
            raise SystemExit("G1: submission made on other coefficients")
        submitted = sub["submitted"]
        hashes["submission"] = srec["submission_sha256"]
    if mode == "exam":
        with guard.unsealing(SCRATCH, SEAL_MANIFEST, ACCESS_LOG) as u:
            _UNSEALER.append(u)
            try:
                groups = build_groups(mode, doc, submitted, rng, dev_count, dev_fr)
            finally:
                _UNSEALER.clear()
    else:
        groups = build_groups(mode, doc, submitted, rng, dev_count, dev_fr)
    res = evaluate(groups)
    return report(mode, spec_sha, started, hashes, submitted, res)


def build_groups(
    mode: str,
    doc: dict[str, Any],
    submitted: list[str],
    rng: np.random.Generator | None,
    dev_count: list[Row],
    dev_fr: list[Row],
) -> dict[str, GroupData]:
    groups: dict[str, GroupData] = {}
    for name in submitted:
        coef = frozen_coef(doc, name)
        frozen = shrunk_of(coef)
        cols = {m: [c for c in cf if not c.startswith("_")] for m, cf in coef.items()}
        if name == "football_result":
            ys_fr: dict[int, tuple[int, int]] | None = None
            if mode == "exam":
                ys_fr = load_pkl(sealed_path(SCRATCH / "exam_y/fr_y.pkl"))
            elif mode == "devtest":
                ys_fr = load_pkl(SCRATCH / "fr_dev_y.pkl")
            groups[name] = exam_fr_group(frozen, cols, ys_fr, rng, dev_fr)
        else:
            metrics = set(GROUPS_ALL[name]) | {total_of(m) for m in GROUPS_ALL[name]}
            ys = None
            if mode == "exam":
                ys = read_ys("exam_y", metrics)
            elif mode == "devtest":
                ys = read_ys("dev", metrics)
            groups[name] = exam_count_group(name, frozen, cols, ys, rng, dev_count)
        log(f"built {name} {groups[name].info}")
    return groups


def report(
    mode: str,
    spec_sha: str,
    started: str,
    hashes: dict[str, str],
    submitted: list[str],
    res: dict[str, Any],
) -> int:
    out = {
        "study": STUDY,
        "mode": mode,
        "spec_sha": spec_sha,
        "started_utc": started,
        "finished_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "hashes": hashes,
        "K": len(submitted),
        "groups": res,
    }
    path = (
        (EVIDENCE / "exam_result.json")
        if mode == "exam"
        else (WORK / f"exam_{mode}_result.json")
    )
    path.write_text(json.dumps(out, indent=1, default=float) + "\n")
    order = [g for g in (*ALL_GROUPS, POOL) if not (g in POOL_OF and POOL in res)]
    if mode == "exam" and ACCESS_LOG.exists():
        out["access_log"] = ACCESS_LOG.read_text().splitlines()
        path.write_text(json.dumps(out, indent=1, default=float) + "\n")
    verdicts = [
        f"{g} {res[g]['verdict']}" if g in res else f"{g} NOT_SUBMITTED"
        for g in order
        if g != POOL or g in res
    ]
    summary = ", ".join(verdicts) + (
        f" (K={len(submitted)}"
        + (", egzamin nieotwarty" if not submitted else "")
        + f"; moduł {str(hashes.get('module', ''))[:16]})"
    )
    if mode == "exam":
        # The file exists (the sports study's line, 2f08d0d7): its header is
        # | UTC | badanie | spec SHA | sha256 współczynników | werdykty |.
        with EXAM_LOG.open("a") as f:
            f.write(
                f"| {started} | {STUDY} | {spec_sha} | "
                f"{str(hashes.get('coefficients', ''))[:16]} | {summary} |\n"
            )
    log(
        json.dumps(
            {g: {"verdict": r["verdict"], "P1": r["P1"]} for g, r in res.items()},
            indent=1,
            default=float,
        )
    )
    log(f"wrote {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "stage",
        choices=(
            "prep",
            "load",
            "explore",
            "validate",
            "freeze",
            "power",
            "submit",
            "exam",
            "seal",
        ),
    )
    ap.add_argument("--study", choices=sorted(STUDIES), default="football")
    ap.add_argument("--part", default="ranks,sched,phase,goals_y")
    ap.add_argument("--groups", default=None)
    ap.add_argument("--mode", choices=("exam", "fake", "devtest"), default="fake")
    ap.add_argument("--spec-sha", default=None)
    a = ap.parse_args(argv)
    st = configure(a.study)
    groups = [g for g in (a.groups or ",".join(ALL_GROUPS)).split(",") if g]
    spec_sha = a.spec_sha or st.spec_sha
    if a.stage in ("load", "explore", "validate", "power", "freeze", "submit", "exam"):
        require_replay_done(a.stage)
    if a.stage in ("freeze", "exam") and not spec_sha:
        raise SystemExit(f"--spec-sha required for {a.stage} of study {STUDY}")
    if a.stage == "prep":
        steps = {
            "ranks": prep_ranks,
            "sched": prep_sched,
            "phase": prep_phase,
            "goals_y": prep_goals_y,
        }
        for p in a.part.split(","):
            steps[p]()
    elif a.stage == "load":
        load()
    elif a.stage == "explore":
        explore()
    elif a.stage == "validate":
        validate(groups)
    elif a.stage == "power":
        power()
    elif a.stage == "freeze":
        freeze(str(spec_sha))
    elif a.stage == "submit":
        submit()
    elif a.stage == "exam":
        return exam(a.mode, str(spec_sha))
    elif a.stage == "seal":
        seal_outcomes()
    return 0


if __name__ == "__main__":
    sys.exit(main())
