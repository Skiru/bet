"""Fit the player shots stretch (epochs.FOOTBALL_PLAYER_STRETCH) into
config/sofa_player_stretch.json.

beta per market of player_stretch.PLAYER_STRETCH_MARKETS (or --markets): a
footballer's centre (the mean of his sample) x exp(beta x s), s his side's
expected goal difference, by Poisson pseudo-likelihood, log link, offset log
centre (supremacy_stretch.fit_terms), on every player sample the cache
replay prices (calibrate_from_cache.build_player_rows - the sample SAMPLES
and SHEET build, starts only by default, as Superbet settles: its
``on_sample`` hook collects one observation per priced sample) of a match
from --train-from to the day before --before. s comes from the football
rating book replayed to each match's UTC day start
(calibrate_from_cache.FootballRatingReplay, read in kickoff order by
target_supremacy), with the book rules SHEET builds the day before --before
with (epochs as of --before 00:00Z) and, by default, the league strength
learnt in international club cups (epochs.FOOTBALL_CUP_STRENGTH, on live
since 2026-10-16; the 2026-10-17 measurement read the cup book;
config/sofa_cup_strength.json of the config dir, --cup-strength FILE another,
--no-cup-strength the plain book). A sample whose side has no goals rating
is left out.

Unlike the measurement, no sample is dropped for having fewer than 3 sample
matches with a rated supremacy: that filter existed to compare the s-today
covariate with the relative one (s today minus the sample's mean s) on the
same rows, and the relative covariate is not used. SHEET applies the term to
every player row with s today, so the fit reads that population.

Dry run by default: prints the table; --write writes the file atomically.
The file is read only while epochs.FOOTBALL_PLAYER_STRETCH_FROM_UTC is set
(inert otherwise). Run it on a COPY of the DB (CLAUDE.md, Changing the pipeline 4).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_player_stretch.py \\
        --before 2026-10-17 --db-path data/refit_<d>/sofa_replay.db \\
        [--no-cup-strength] [--train-from 2024-10-01] [--all-appearances] \\
        [--write [--out <file>]]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import epochs  # noqa: E402
from bet.sofa import player_stretch as pst  # noqa: E402
from bet.sofa import supremacy_stretch as ss  # noqa: E402
from bet.sofa.atomic import write_bytes_atomic  # noqa: E402
from bet.sofa.config import SofaConfig, config_path  # noqa: E402
from bet.sofa.cup_strength import load as load_cup_strength  # noqa: E402
from scripts.sofa import calibrate_from_cache as cfc  # noqa: E402

# a line per market: build_player_rows prices a sample only for a metric with
# a line, and the fit reads the sample, never the rows
FIT_LADDER_LINE = 0.5


@dataclass(frozen=True)
class PlayerObs:
    event_id: int
    kickoff: int
    is_home: bool
    metric: str
    centre: float  # the sample's mean (SHEET's player centre)
    y: float


def collect(
    db_path: Path, markets: Sequence[str], from_ts: int | None, to_ts: int,
    *, sample_n: int, min_sample: int, starts_only: bool = True,
) -> tuple[list[PlayerObs], dict[int, dict[str, Any]]]:
    """(one observation per priced player sample of a match kicking off in
    [from_ts, to_ts), the targets' events by id)."""
    obs: list[PlayerObs] = []
    events: dict[int, dict[str, Any]] = {}

    def hook(event: dict[str, Any], is_home: bool, _name: str, metric: str,
             mean: float, _n: int, actual: float) -> None:
        kickoff = int(event["startTimestamp"])
        if kickoff >= to_ts or (from_ts is not None and kickoff < from_ts):
            return
        eid = int(event["id"])
        events[eid] = event
        obs.append(PlayerObs(eid, kickoff, is_home, metric, mean, actual))

    cfc.build_player_rows(
        db_path, {m: [FIT_LADDER_LINE] for m in markets}, sample_n=sample_n,
        min_sample=min_sample, starts_only=starts_only, on_sample=hook)
    return obs, events


def book_rules(before: str, cup_path: str | None,
               no_cup: bool) -> cfc.CentreRules:
    """The rating book's rules as SHEET builds the day before ``before``
    (epochs as of ``before`` 00:00Z), the cup league strength unless
    ``no_cup``."""
    last_day = (date.fromisoformat(before) - timedelta(days=1)).isoformat()
    at = datetime.fromisoformat(before).replace(tzinfo=UTC)
    return cfc.CentreRules(
        football_rating=True,
        cup_strength=(None if no_cup else load_cup_strength(
            Path(cup_path) if cup_path else None)),
        cup_strength_path=(None if no_cup
                           else cup_path or "config/sofa_cup_strength.json"),
        shared_league_link=epochs.link_shared_league(last_day, at),
        unit_strength_from_parent=epochs.unit_strength_from_parent(last_day, at),
        strict_league_rate=epochs.football_league_rate_rule(last_day, at),
    )


def fit_observations(
    obs: Sequence[PlayerObs], supremacy: dict[int, dict[bool, float | None]],
    markets: Sequence[str],
) -> dict[str, dict[str, object]]:
    """market -> its file cell (beta, n_rows, n_matches); an observation
    whose side has no supremacy is left out."""
    out: dict[str, dict[str, object]] = {}
    for m in markets:
        centres: list[float] = []
        sup: list[float] = []
        y: list[float] = []
        matches: set[int] = set()
        for o in obs:
            if o.metric != m:
                continue
            s = supremacy.get(o.event_id, {}).get(o.is_home)
            if s is None:
                continue
            centres.append(o.centre)
            sup.append(s)
            y.append(o.y)
            matches.add(o.event_id)
        coefs = ss.fit_terms(False, centres, sup, y, 1)
        cell: dict[str, object] = dict(ss.cell_json(False, coefs))
        cell.update({"n_rows": len(y), "n_matches": len(matches)})
        out[m] = cell
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--train-from", default=None,
                    help="first kickoff day of the fit (default: every sample)")
    ap.add_argument("--markets", nargs="+",
                    default=list(pst.PLAYER_STRETCH_MARKETS))
    ap.add_argument("--db-path", help="the DB (a copy); default SOFA_DB_PATH "
                    "/ data/sofa.db")
    ap.add_argument("--all-appearances", action="store_true",
                    help="every appearance, not starts only (the live rule "
                    "since epochs.PLAYER_STARTS_ONLY is starts)")
    ap.add_argument("--cup-strength", default=None, metavar="FILE",
                    help="the cup list the rating book learns from (default "
                    "the installed config/sofa_cup_strength.json)")
    ap.add_argument("--no-cup-strength", action="store_true",
                    help="the plain rating book, no cup league strength")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out", help="default config/sofa_player_stretch.json")
    ap.add_argument("--awarded-excluded", action="store_true",
                    help="football results awarded at the table (isAwarded) out "
                    "of the rating history and the players' histories")
    args = ap.parse_args()
    bad = [m for m in args.markets if m not in pst.PLAYER_STRETCH_MARKETS]
    if bad:
        print(f"not player-stretch markets: {bad}", file=sys.stderr)
        return 2
    if args.no_cup_strength and args.cup_strength:
        print("--cup-strength and --no-cup-strength", file=sys.stderr)
        return 2
    markets = tuple(args.markets)
    config = SofaConfig.from_env()
    db = Path(args.db_path) if args.db_path else Path(config.db_path)
    to_ts = cfc.day_ts(args.before)
    assert to_ts is not None
    # a player's history as calibrate_from_cache --awarded-excluded reads it
    cfc.AWARDED_EXCLUDED = bool(args.awarded_excluded)
    obs, events = collect(
        db, markets, cfc.day_ts(args.train_from), to_ts,
        sample_n=config.sample_n, min_sample=config.min_sample,
        starts_only=not args.all_appearances)
    rules = book_rules(args.before, args.cup_strength, args.no_cup_strength)
    football = cfc.FootballRatingReplay.from_db(
        db, rules, awarded_out=args.awarded_excluded)
    supremacy = cfc.target_supremacy(list(events.values()), football)
    table = fit_observations(obs, supremacy, markets)
    doc = {
        "_doc": ("Player shots stretch (epochs.FOOTBALL_PLAYER_STRETCH): a "
                 "footballer's shots centre x exp(beta x s), s his side's "
                 "expected goal difference. INERT while "
                 "epochs.FOOTBALL_PLAYER_STRETCH_FROM_UTC is None. Written by "
                 "scripts/sofa/fit_player_stretch.py."),
        "fitted_from": {
            "awarded_excluded": bool(args.awarded_excluded),
            "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "train_from": args.train_from, "before": args.before,
            "db_path": str(db),
            "method": "Poisson pseudo-likelihood, log link, offset log centre",
            "samples": ("calibrate_from_cache.build_player_rows, "
                        + ("every appearance" if args.all_appearances
                           else "starts only")),
            "book_rules": rules.describe(),
            "evidence": pst.EVIDENCE,
        },
        "unfitted_constants": list(pst.PLAYER_STRETCH_UNFITTED),
        "markets": table,
    }
    pst.parse_table(doc)  # what is written must be readable
    text = json.dumps(doc, indent=2) + "\n"
    print(text)
    if args.write:
        target = Path(args.out) if args.out else config_path(pst.CONFIG_FILE)
        write_bytes_atomic(target, text.encode("utf-8"))
        print(f"wrote {target}")
    else:
        print("dry run: nothing written (--write to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
