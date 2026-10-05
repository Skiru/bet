#!/usr/bin/env python3
"""CONFIDENCE — rank legs by measured reliability, and build Bet Builders.

The coupon stage answers "is this worth its price". This one answers "how
often does this actually happen", which is the question an operator who has
already accepted a shaded price is asking. See bet.sofa.confidence for why the
two are different and why the first one is a losing argument here.

Reads the sheet, the offer and the fixtures that are already on disk. Costs no
provider call. Writes 08_confidence.json and 08_confidence.md.

Usage:
    python -m scripts.sofa.run_confidence --date 2026-09-19 --floor 0.80
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
# The day's real artifacts; --calibration refuses to write here.
REAL_RUNS_DIR = _REPO / "runs" / "sofa"
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pydantic import RootModel  # noqa: E402

from bet.sofa import timeutil  # noqa: E402
from bet.sofa.artifact_guard import incomplete_reason  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    BUILDER_CORRELATION_HAIRCUT,
    MAX_BUILDER_LEGS,
    MAX_BUILDER_SAMPLE_AGE_DAYS,
    MIN_BUILDER_LEGS,
    MIN_BUILDER_SAMPLE,
    MIN_ODDS_FOR_CEILING,
    PROFILES,
    STAKEABLE_RULE_X,
    Calibration,
    best_leg_per_quantity,
    builder_legs_are_coherent,
    builder_odds,
    combined_probability,
    confidence_artifact,
    coupon_artifact,
    coupon_sort_key,
    disagrees_with_price,
    empirical_joint,
    fair_odds,
    fixture_leg_counts,
    has_cross_league_unlinked_note,
    has_unreachable_bar_note,
    is_derived,
    is_stakeable,
    joint_probability,
    line_is_beyond_sample,
    match_class,
    mode_loses,
    model_above_own_sample,
    overround,
    own_hit_rate,
    profile_retired,
    reads_catch_all_bucket,
    too_close_to_kickoff,
)
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.contracts import Fixture  # noqa: E402
from bet.sofa.coupon import MAX_SAMPLE_AGE_DAYS  # noqa: E402
from bet.sofa.engine import (  # noqa: E402
    has_calibratable_model,
)
from bet.sofa.epochs import (  # noqa: E402
    STATS_ONLY,
    STATS_ONLY_FROM_UTC,
    sheet_epoch,
)
from bet.sofa.epochs import stats_only as stats_only_epoch  # noqa: E402
from bet.sofa.locked_print import (  # noqa: E402
    PRINTED_MANIFEST,
    carry_over,
    kicked_off,
    kickoff_clocks,
    leg_key,
    merge_locked,
)
from bet.sofa.players import (  # noqa: E402
    is_player_metric,
    player_observations,
)
from bet.sofa.samples import is_friendly_fixture  # noqa: E402
from bet.sofa.schedule import FixtureSchedule  # noqa: E402
from bet.sofa.veto import (  # noqa: E402
    load_reads,
    load_vetoes,
    matching_reads,
    read_refusal,
    veto_matches,
)
from scripts.sofa.run_sheet import determine_side  # noqa: E402

# A leg below this is not what the operator means by a strong read. The floor
# is on the measured LOWER bound, not on what the model claims.
#
# Lowered from 0.80 to 0.70 on 2026-09-22, as a deliberate operator decision
# rather than a fitted one. Replayed over the three settled days, football
# legs that also clear the ladder-margin filter:
#
#     floor    legs    hit     ROI
#     0.85      111   0.820   -4.01%
#     0.80      339   0.788   -2.96%
#     0.75      623   0.754   -2.41%
#     0.70     1010   0.719   -2.75%
#     0.65     1467   0.680   -3.00%
#     0.60     2217   0.634   -4.84%
#
# Read that as "costs nothing down to about 0.70, and triples the volume",
# NOT as "0.70 is optimal" — 0.75 scored marginally better and 0.65 marginally
# worse, all three inside the noise. Below 0.65 it degrades for real.
#
# The honest caveat is large: 09-19 carries
# n=298-1940 per floor, 09-20 carries n=17-253 and 09-21 carries n=1-24, so
# the table is effectively one slate. Leave-one-day-out picked 0.75, 0.70,
# 0.75 and "won" 2 of 3 days on held-out samples of 6 and 9 legs, which is not
# evidence of anything.
#
# What does NOT move with it is `leg_is_ev_positive`. The floor asks how
# likely the event is; that gate asks whether the price pays for it, and it is
# the only thing that finds the one mispriced side of a two-sided market. The
# bookmaker's 8.6-10.2% margin is spread ACROSS both sides, so it does not
# make every leg negative — measured, rows at p_bar 0.85-0.95 priced 1.20-1.35
# returned +1.94%. Lowering the floor buys volume; lowering the EV gate would
# just buy the wrong side more often.
#
# The official profile keeps both. The `wariant` profile (confidence.PROFILES)
# lowers both on purpose, at the operator's request, into its own artifacts -
# measured -3.2% against the official -2.9% before it was added, i.e. the price
# of volume, not an edge. It never writes 08_confidence.json.
DEFAULT_FLOOR = 0.70
# Superbet's own shading is accepted, but a price below this is not a shaded
# price, it is a rounding error with a stake attached.
#
# Raised 2026-09-20 from a flat 1.01 to the curve's own resolution limit. See
# MIN_ODDS_FOR_CEILING: below 1.0867 a leg cannot have positive EV under this
# calibration whatever the fixture, so admitting it and then reporting its
# contribution to a slip's EV was self-contradictory.
MIN_ODDS = MIN_ODDS_FOR_CEILING


def unfitted_from_notes(notes: list[str] | None) -> list[str]:
    """The constants a sheet row names in its UNFITTED_CONSTANTS note."""
    found: set[str] = set()
    for note in notes or []:
        if note.startswith("UNFITTED_CONSTANTS:"):
            found.update(
                c.strip() for c in note.split(":", 1)[1].split(",") if c.strip()
            )
    return sorted(found)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True)
    ap.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="standard",
        help=(
            "standard = the official coupon (08_confidence.json). wariant = "
            "floor 0.65, a price up to 10%% below fair and a ladder margin up "
            "to 15%% (the coupon: 10.5%%), written to its own "
            "08_confidence_wariant.* so the official files are untouched."
        ),
    )
    ap.add_argument(
        "--floor",
        type=float,
        default=None,
        help="override the profile's floor (standard: 0.70, wariant: 0.65)",
    )
    # The same directory every other stage reads (SofaConfig.runs_dir). A
    # hard-coded default let a scratch rebuild under SOFA_RUNS_DIR overwrite
    # the real day's 08_confidence.json and PDF on 2026-09-23.
    ap.add_argument(
        "--runs-dir", default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa")
    )
    ap.add_argument(
        "--calibration", default=None,
        help="calibration file to read instead of the installed one (a "
        "scratch copy, e.g. with gap_shrink_k set, to see what it would "
        "print); it writes the same artifact names, so pair it with a scratch "
        "--runs-dir or it overwrites the day's real confidence view",
    )
    args = ap.parse_args()
    profile = PROFILES[args.profile]
    if args.floor is None:
        args.floor = profile.floor
    artifact = confidence_artifact(profile)

    run_dir = Path(args.runs_dir) / args.date
    frozen = timeutil.frozen_clock_refusal(args.runs_dir)
    if frozen:
        print(frozen, file=sys.stderr)
        return 2
    # A scratch calibration must never write the real day's confidence view
    # (2026-09-23: a scratch rebuild clobbered the real coupon).
    if args.calibration and Path(args.runs_dir).resolve() == REAL_RUNS_DIR.resolve():
        print(
            "REFUSED: --calibration writes the same artifact names; pass a "
            "scratch --runs-dir (not runs/sofa)",
            file=sys.stderr,
        )
        return 2
    # The same limit COUPON reads. A hard-coded 45 here let
    # SOFA_PRICE_MAX_AGE_MIN move COUPON's gate and not this one's.
    max_price_age = timedelta(minutes=SofaConfig.from_env().price_max_age_min)
    refusal = incomplete_reason(run_dir / "02_fixtures.json")
    if refusal:
        print(refusal, file=sys.stderr)
        return 2
    sheet = json.loads((run_dir / "05_sheet.json").read_text(encoding="utf-8"))
    # One clock for every stage (bet.sofa.timeutil), so a rebuild or a test
    # that fixes the time fixes it here too.
    now = timeutil.now()
    # bet.sofa.epochs (plan 2026-10-05, K0): from the stats-only rebuild of
    # 10-05 on, the coupon's confidence is the statistics' alone.
    so = stats_only_epoch(args.date, now)
    # K5: the WARIANT is no longer built for a stats-only day.
    if profile_retired(profile, args.date, now):
        print(
            f"REFUSED: the {profile.name} profile is retired from "
            f"{STATS_ONLY_FROM_UTC.isoformat()} (plan 2026-10-05, K5: one "
            "coupon); its earlier days stay readable",
            file=sys.stderr,
        )
        return 2
    if so and sheet and sheet_epoch(sheet) != STATS_ONLY:
        print(
            "REFUSED: this is a stats-only build and 05_sheet.json was not "
            f"built under that rule (epoch {sheet_epoch(sheet)!r}); a rebuild "
            "starts at SHEET",
            file=sys.stderr,
        )
        return 2
    fixtures = {
        f["sofascore_event_id"]: f
        for f in json.loads((run_dir / "02_fixtures.json").read_text(encoding="utf-8"))
    }
    raw_fx = (run_dir / "02_fixtures.json").read_bytes()
    fx_models = {
        f.sofascore_event_id: f
        for f in RootModel[list[Fixture]].model_validate_json(raw_fx).root
    }
    samples = {
        s["sofascore_event_id"]: s
        for s in json.loads((run_dir / "03_samples.json").read_text(encoding="utf-8"))
    }

    def schedule_flags(event_id: int) -> list[str]:
        raw = (samples.get(event_id) or {}).get("schedule")
        if not raw:
            return []
        return FixtureSchedule.model_validate_json(json.dumps(raw)).flags()

    def side_observations(row: dict[str, Any]) -> list[dict[str, Any]]:
        """This row's own past matches, on the side the sheet priced.

        Carries the whole observation, not just its value, because the
        builder's empirical joint has to intersect legs on
        `sofascore_event_id` — which match a number came from is the point.
        """
        fixture_samples = samples.get(row["sofascore_event_id"], {})

        # F54. A player row's sample is not on the metrics axis at all — it is
        # one person's appearances, keyed exactly as the rung is. Without this
        # the row reached the builder pool with NO observations, so every
        # shape gate that reads the distribution (extremum, mode, freshness)
        # was answering a question about an empty list.
        if is_player_metric(row["market"]):
            return player_observations(
                fixture_samples, row["market"], row.get("subject") or ""
            )

        mv = (fixture_samples.get("metrics") or {}).get(row["market"])
        if not mv:
            return []
        subject = row.get("subject") or ""
        if subject:
            fx_model = fx_models.get(row["sofascore_event_id"])
            side = determine_side(subject, fx_model) if fx_model else None
            return list(mv.get(side) or []) if side else []
        obs, seen = [], set()
        for side_key in ("side_a", "side_b", "h2h"):
            for o in mv.get(side_key) or []:
                if o["sofascore_event_id"] in seen:
                    continue
                seen.add(o["sofascore_event_id"])
                obs.append(o)
        return obs

    def sample_values(
        obs: list[dict[str, Any]],
    ) -> tuple[list[float], int | None, int | None]:
        """These observations' values, and the age of the oldest, in days.

        The sheet carries mean/sd/n but not the distribution, so the shape
        gates (extremum, mode) cannot be answered from it. SAMPLES holds every
        observation with its date; this reads the same side the sheet priced.
        """
        values = [o["value"] for o in obs if o.get("value") is not None]
        dates = [o["match_date_utc"] for o in obs if o.get("value") is not None]
        if not dates:
            return values, None, None
        parsed = [datetime.fromisoformat(d.replace("Z", "+00:00")) for d in dates]
        return values, (now - min(parsed)).days, (now - max(parsed)).days

    offers = json.loads((run_dir / "04_offer.json").read_text(encoding="utf-8"))
    fetched: dict[tuple[Any, ...], str] = {}
    # The price this offer quotes for the side, so a leg is only timed against
    # the price it actually carries. The sheet's `offered_odds` is from the
    # OFFER that fed SHEET; a rebuild refreshes OFFER without re-running SHEET
    # (sofa-rebuild), and until 2026-09-25 this stage then timed the fresh
    # offer while printing the sheet's price - 16 of 351 variant legs that day
    # printed a price the book no longer quoted, two of them failing x >= 0.90
    # at the live price. A side the refresh no longer prices has no timestamp.
    fresh_odds: dict[tuple[int, str, str, float, str], float] = {}
    # The ladder's own margin, per rung. It is a property of the two-sided
    # price, so it is the same for OVER and UNDER of one rung.
    margins: dict[tuple[int, str, str, float, str], float | None] = {}
    # Fixtures a fetch found Superbet reporting under way (coupon.
    # superbet_started): refused whatever the two clocks say, since both can
    # be late and a started match takes no pre-match bet.
    started_ids = {
        o["sofascore_event_id"] for o in offers if o.get("superbet_started_utc")
    }
    # Superbet's start time as OFFER last saw it: a third clock beside the two
    # RESOLVE froze, since Superbet moves starts earlier too.
    seen_kickoff = {
        o["sofascore_event_id"]: o["superbet_kickoff_seen_utc"]
        for o in offers if o.get("superbet_kickoff_seen_utc")
    }
    for o in offers:
        for r in o.get("rungs", []):
            rung_margin = overround(r.get("over_odds"), r.get("under_odds"))
            for d, side_odds in (
                ("OVER", r.get("over_odds")),
                ("UNDER", r.get("under_odds")),
            ):
                if side_odds is None:
                    continue
                key = (o["sofascore_event_id"], r["market"], r.get("subject", ""),
                       r["line"], d)
                fetched[key] = r.get("fetched_at_utc")
                fresh_odds[key] = side_odds
                margins[key] = rung_margin

    cal = Calibration.load(args.calibration) if args.calibration else Calibration.load()
    if so:
        # K2: no anti-selection shrink toward the price; K13: a thin
        # direction bucket caps the market curve as it caps a pool.
        cal = dataclasses.replace(cal, gap_shrink_k=0.0, cap_market_by_thin=True)
    # Superbet's own side names, for the match class ("(K)" = women's).
    board_sides: dict[str, tuple[str, str]] = {}
    board_path = run_dir / "01_board.json"
    if board_path.exists():
        board_doc = json.loads(board_path.read_text(encoding="utf-8"))
        for entry in board_doc if isinstance(board_doc, list) else board_doc.get(
                "fixtures", board_doc.get("events", [])):
            if isinstance(entry, dict) and entry.get("superbet_event_id"):
                board_sides[str(entry["superbet_event_id"])] = (
                    str(entry.get("side_a") or ""), str(entry.get("side_b") or ""))
    # The previous build of THIS profile, read before it is overwritten: the
    # legs it printed whose match has started since are carried over as
    # printed (bet.sofa.locked_print - the operator's decision of
    # 2026-10-05). An unreadable previous artifact refuses the build rather
    # than overwrite the only record of what was printed.
    previous: dict[str, Any] | None = None
    # Stats-only: what was printed is the coupon artifact (11_coupon.json
    # once build_coupon.py has run, the morning's 08 before it) - K3.
    previous_path = coupon_artifact(run_dir) if so else run_dir / artifact
    if previous_path.exists():
        try:
            loaded = json.loads(previous_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            print(
                f"REFUSED: the previous {previous_path.name} is unreadable "
                f"({exc}); it is "
                "the only record of the legs already printed - move it aside "
                "deliberately before rebuilding",
                file=sys.stderr,
            )
            return 2
        previous = loaded if isinstance(loaded, dict) else None
    # "Printed" means a PDF was rendered from that build: the provisional
    # build before the analysts' read never reaches a PDF, and a leg the
    # operator never saw is not locked. A build whose PDF is missing or older
    # than it carries over only the legs it had itself locked from an earlier,
    # printed build.
    previous_pdf = run_dir / f"KUPON_{args.date}{profile.pdf_suffix}.pdf"
    previous_printed = (
        previous is not None
        and previous_pdf.exists()
        and previous_pdf.stat().st_mtime >= previous_path.stat().st_mtime
    )

    # The analyst's vetoes, which until 2026-09-21 this stage did not read.
    # COUPON honoured them and CONFIDENCE did not, so a veto removed a row
    # from 06_coupon.json — the VALUE singles, which the runbook is explicit
    # are not the coupon — and left the same row standing as a leg of the Bet
    # Builder the PDF actually stakes. The one channel a human read has into
    # this pipeline could not reach its product.
    vetoes = load_vetoes(run_dir / "vetoes.json")
    vetoed_keys: set[tuple[Any, ...]] = set()
    # The analysts' and the verifier's reads (contracts.LegRead, 2026-10-04):
    # NO_BET refuses everywhere, WATCH where the profile honours it, and a
    # read that covers a printed leg rides on the leg so the ledger can tell
    # a watched leg from the rest.
    reads = load_reads(run_dir / "reads.json")
    read_keys: set[tuple[Any, ...]] = set()

    legs: list[dict[str, Any]] = []
    # K6 (stats-only): a leg that passed every gate and was removed by a read
    # (reads.json) or by the automatic WATCH - graded on its own (7h), never
    # in the coupon's result.
    removed_by_reads: list[dict[str, Any]] = []
    refused: dict[str, int] = defaultdict(int)
    for row in sheet:
        odds = row.get("offered_odds")
        if odds is None:
            refused["NO_PRICE"] += 1
            continue
        if odds < MIN_ODDS:
            refused["ODDS_TOO_LOW"] += 1
            continue
        fx = fixtures.get(row["sofascore_event_id"])
        if fx is None:
            refused["NO_FIXTURE"] += 1
            continue
        if any(
            veto_matches(
                v,
                sofascore_event_id=row["sofascore_event_id"],
                market=row["market"],
                subject=row.get("subject") or "",
                line=row["line"],
                direction=row["direction"],
            )
            for v in vetoes
        ):
            refused["VETOED"] += 1
            vetoed_keys.add(
                (
                    row["sofascore_event_id"],
                    row["market"],
                    row.get("subject") or "",
                    row["line"],
                    row["direction"],
                )
            )
            continue
        row_reads = matching_reads(
            reads,
            sofascore_event_id=row["sofascore_event_id"],
            market=row["market"],
            subject=row.get("subject") or "",
            line=row["line"],
            direction=row["direction"],
        )
        if row_reads:
            read_keys.add(
                (
                    row["sofascore_event_id"],
                    row["market"],
                    row.get("subject") or "",
                    row["line"],
                    row["direction"],
                )
            )
        read_refused = read_refusal(row_reads, profile.honours_watch)
        # Stats-only: the read is applied at the END of the chain (K6), so a
        # leg it removes is known to have passed everything else.
        if read_refused is not None and not so:
            refused[read_refused] += 1
            continue
        # The EARLIER of the two clocks, as coupon.py has done since F26 —
        # this stage read only Sofascore's, which is the later one for ITF.
        # Sofascore publishes the tournament's local time as though it were
        # UTC there, so the error runs the wrong way: a finished match looks
        # upcoming. On 2026-09-21 the day's only tennis leg was an ITF fixture
        # whose two clocks disagreed by 2.0 h, and the gap reaches 11.0 h
        # elsewhere on that board. The staked path was the one reading the
        # wrong clock.
        # The same predicate locks an already printed leg (locked_print), so
        # a fixture's fresh rows are refused exactly when its printed legs
        # are carried over.
        clocks = kickoff_clocks(fx, seen_kickoff.get(row["sofascore_event_id"]))
        if kicked_off(
            fx,
            seen_kickoff.get(row["sofascore_event_id"]),
            row["sofascore_event_id"] in started_ids,
            now,
        ):
            refused["KICKED_OFF"] += 1
            continue
        # The leg is GATED on the earlier clock, so it must be PRINTED on the
        # earlier clock too. Until 2026-09-23 the leg carried Sofascore's,
        # which for ITF is the later one by 7-9 h: 11 of the 30 singles on that
        # PDF showed a start time after the one Superbet would accept a bet
        # against, the worst by 8 h (13:00Z on the page, 05:00Z at the book).
        # A page an operator reads to decide WHEN to place a bet cannot show a
        # time the stage itself does not believe.
        effective_kickoff = min(clocks)
        key = (row["sofascore_event_id"], row["market"], row.get("subject", ""),
               row["line"], row["direction"])
        ts = fetched.get(key)
        rung_overround = margins.get(key)
        if ts is None:
            refused["NO_FETCHED_AT"] += 1
            continue
        if now - datetime.fromisoformat(ts.replace("Z", "+00:00")) > max_price_age:
            refused["STALE_PRICE"] += 1
            continue
        # Refused, not re-priced: market_p, p_central (tennis blends the price
        # in) and required_odds were all computed from the sheet's price, so
        # swapping the odds alone would pair a new price with an old
        # probability. Re-running SHEET is what re-prices a leg.
        sheet_odds: float | None = None
        if not math.isclose(fresh_odds[key], odds, abs_tol=1e-9):
            if not so:
                refused["PRICE_MOVED_SINCE_SHEET"] += 1
                continue
            # K2: in the stats-only epoch no probability read the price, so
            # the leg is judged at the fresh price (x, margin, ODDS_TOO_LOW).
            sheet_odds, odds = odds, fresh_odds[key]
            if odds < MIN_ODDS:
                refused["ODDS_TOO_LOW"] += 1
                continue

        # A metric with no model at all is refused. Empirical-frequency
        # metrics are NOT in that class any more: since 2026-09-21
        # fit_confidence fits them from the `p_central` the sheet stored,
        # so they carry a measured curve like everything else.
        #
        # They used to be banned here, and the ban was the wrong fix for a
        # real problem. The raw frequency is overconfident at the top — on
        # 9,286 settled `games_won_for` rows a claimed 0.95 realises 0.728 —
        # which is exactly what produced the 0.811-against-20.00 leg the ban
        # was written for. A curve solves that by capping the top bucket; the
        # ban solved it by deleting tennis. `games_won_for` alone was 1084 of
        # a Monday sheet's 3026 tennis rows, and it was simultaneously the
        # largest single component of the VALUE path, whose measured ROI is
        # negative. The good path could not see it and the bad path was made
        # of it.
        #
        # A market that still has no curve falls out below, on
        # `cal.realised(...) is None`, which is the honest place for it.
        # `tiebreaks_total` is neither, and has a model all the same — see
        # NORMAL_NON_COUNT_METRICS. It was refused here on every row.
        if not has_calibratable_model(row["market"]):
            refused["NOT_IN_CALIBRATION_FIT"] += 1
            continue
        # "This row missed the bar" and "no sample could have cleared it at
        # this price" are different statements, and only the second one is a
        # refusal this stage is allowed to ignore — it isn't. CONFIDENCE
        # deliberately does not ask COUPON's question, so BELOW_BAR alone must
        # NOT be filtered here: 9,867 of the 2026-09-23 sheet's 10,917 rows are
        # BELOW_BAR, and banning them collapses this stage into the one it
        # exists to complement.
        #
        # UNREACHABLE_BAR is the other kind. It says the offered price cannot
        # be justified by ANY sample of this size — not that our sample failed
        # to justify it — so no confidence number can rescue it and there is
        # nothing left for this stage to have an opinion about. run_coupon
        # already excludes these rows even from its near-misses list, for the
        # same reason.
        #
        # On 2026-09-23 COUPON selected zero VALUE singles, so the whole PDF
        # came from here, and 29 of the 30 printed singles carried this note.
        # Not in the stats-only epoch (D1): it is a statement about the price.
        if not so and has_unreachable_bar_note(row.get("notes")):
            refused["UNREACHABLE_BAR"] += 1
            continue
        # See has_cross_league_unlinked_note: two football sides that share
        # no league and whose leagues' strengths are unmeasured.
        if has_cross_league_unlinked_note(row.get("notes")):
            refused["CROSS_LEAGUE_UNLINKED"] += 1
            continue
        # A friendly is not a fixture to price (samples.is_friendly_fixture).
        fx_row = fixtures.get(row["sofascore_event_id"]) or {}
        if is_friendly_fixture(str(fx_row.get("sport")), fx_row.get("competition_id")):
            refused["FRIENDLY_FIXTURE"] += 1
            continue
        # See DERIVED_PREFIXES. A joint of two sides is not a count of one
        # thing, has 2-252 settled rows of its own, and no sample in the
        # artifacts can check it.
        if is_derived(row["market"]):
            refused["DERIVED_NOT_CALIBRATABLE"] += 1
            continue

        # See Calibration.admitted_player_markets: a curve is not an admission.
        if cal.player_prop_not_admitted(row["market"]):
            refused["PLAYER_PROP_NOT_ADMITTED"] += 1
            continue
        # See Calibration.admitted_tennis_set_markets (TENNIS_SET_GAMES).
        if cal.tennis_set_market_not_admitted(row["market"]):
            refused["TENNIS_SET_MARKET_NOT_ADMITTED"] += 1
            continue
        # See Calibration.refused_markets: the operator's own refusals.
        if cal.refused_by_operator(row["market"], row.get("direction")):
            refused["OPERATOR_REFUSED"] += 1
            continue

        sides = next(
            (board_sides[str(i)] for i in fx.get("superbet_event_ids") or []
             if str(i) in board_sides), None)
        klass = match_class(
            row.get("sport"),
            fx.get("category_name") if row.get("sport") == "tennis"
            else fx.get("competition_name"),
            sides,
            fx.get("competition_id"),
        )
        hit = cal.realised(
            row["market"], row["p_central"], row.get("sport"), row["direction"],
            klass,
        )
        if hit is None and klass is not None and cal.realised(
            row["market"], row["p_central"], row.get("sport"), row["direction"]
        ) is not None:
            # Refused only because of its class: the unclassed curves would
            # have served it (Calibration.realised). A class leg nothing would
            # have served falls through to NOT_CALIBRATED like any other -
            # on the 10-01 verification run 757 of 777 were that.
            refused["NO_CLASS_CURVE"] += 1
            continue
        if hit is None:
            # No measurement for this bucket. The model's own number is not a
            # substitute for one, so the leg is refused rather than guessed.
            refused["NOT_CALIBRATED"] += 1
            continue
        realised_lo, source, n_cal = hit
        # See Calibration.shrink_for_gap: off (k = 0) unless the operator put
        # gap_shrink_k into the calibration file. Applied before the floor and
        # the price gate, so a shrunk leg is judged on the number it prints.
        curve_lo = realised_lo
        realised_lo = cal.shrink_for_gap(
            realised_lo, row["p_central"], row.get("market_p")
        )
        if realised_lo < args.floor:
            refused["BELOW_CONFIDENCE_FLOOR"] += 1
            continue
        # See CATCH_ALL_BUCKET_TOP: the bottom bucket's lower bound is an
        # average over claims from 0.00 to 0.60 and cannot vouch for one.
        if reads_catch_all_bucket(row["p_central"]):
            refused["CATCH_ALL_BUCKET"] += 1
            continue
        # See MAX_DISAGREEMENT. Shading means the book pays us less than the
        # event is worth; this is the opposite case, where we claim far more
        # than the book does, and it is measured to end below a coin flip.
        # Off in the stats-only epoch (D1; measured 09-24..10-04: refused
        # -3.7% [-9.6; +2.1] against admitted -4.8% [-6.1; -3.4]).
        if not so and disagrees_with_price(
            row["p_central"],
            row.get("market_p"),
            realised_lo,
            odds,
            row.get("sample_frequency"),
        ):
            refused["DISAGREES_WITH_PRICE"] += 1
            continue
        # The leg has to clear its own price using its own number. Without
        # this the builder reported an EV it was simultaneously destroying:
        # `ev_if_product_priced` is prod(confidence * odds) - 1, so a leg
        # whose own product is below 1 drags every slip it joins.
        # The wariant profile relaxes exactly this gate, and says by how much
        # (ConfidenceProfile.min_ev); since 2026-10-05 the official one does too.
        if not profile.clears_price(realised_lo, odds):
            refused["NEGATIVE_LEG_EV"] += 1
            continue

        observations = side_observations(row)
        values, oldest_days, newest_days = sample_values(observations)
        # SHEET measures freshness per side and keeps the staler one; the pool
        # read here would let a fresh opponent hide a stale side (2026-10-01).
        sheet_newest = row.get("sample_newest_days")
        if sheet_newest is not None:
            newest_days = max(newest_days or 0, int(sheet_newest))
        obs_by_match = {
            o["sofascore_event_id"]: o["value"]
            for o in observations
            if o.get("value") is not None
        }
        # The shape gates. These need the distribution, not the summary: a
        # sample can report 20/20 and mean nothing (every observation on the
        # same side of a line it has never approached), and a mean can sit
        # comfortably above a line whose modal outcome loses.
        if line_is_beyond_sample(row["line"], row["direction"], values):
            refused["LINE_BEYOND_SAMPLE"] += 1
            continue
        if mode_loses(row["line"], row["direction"], values):
            refused["MODE_LOSES"] += 1
            continue
        if len(values) < MIN_BUILDER_SAMPLE:
            refused["THIN_SAMPLE_FOR_BUILDER"] += 1
            continue
        if oldest_days is not None and oldest_days > MAX_BUILDER_SAMPLE_AGE_DAYS:
            refused["SAMPLE_CROSSES_SEASON"] += 1
            continue
        # How far BACK a sample reaches and whether it is still CURRENT are
        # two questions, and until 2026-09-21 this stage only asked the first.
        # The coupon asked the second and refused at 60 days; the PDF — the
        # artifact actually staked — asked nothing, so the more important
        # path was the more permissive one. Same constant in both places, so
        # they cannot drift apart again.
        if newest_days is not None and newest_days > MAX_SAMPLE_AGE_DAYS:
            refused["STALE_SAMPLE"] += 1
            continue
        # An automatic WATCH (confidence.MAX_OWN_SAMPLE_GAP): refused where
        # the profile honours WATCH, kept and marked where it does not.
        own_gap = model_above_own_sample(
            row["sport"], row["p_central"], values, row["line"], row["direction"],
            row["market"],
        )
        auto_watch: list[str] = []
        removal: tuple[str, str] | None = None
        if own_gap is not None:
            if profile.honours_watch:
                if not so:
                    refused["MODEL_ABOVE_OWN_SAMPLE"] += 1
                    continue
                removal = ("MODEL_ABOVE_OWN_SAMPLE", "auto")
                auto_watch.append(f"MODEL_ABOVE_OWN_SAMPLE(+{own_gap:.2f})")
            else:
                auto_watch.append(f"MODEL_ABOVE_OWN_SAMPLE(+{own_gap:.2f})")
        if so and read_refused is not None:
            # A person's read before the automatic one: who removed it.
            refusing = [
                r for r in row_reads
                if r.verdict == ("NO_BET" if read_refused == "READ_NO_BET" else "WATCH")
            ]
            removal = (read_refused, "+".join(sorted({r.author for r in refusing})))

        leg = (
            {
                "sofascore_event_id": row["sofascore_event_id"],
                "match": f"{fx['home_name']} - {fx['away_name']}",
                "competition": fx.get("competition_name"),
                "sport": row["sport"],
                "kickoff_utc": effective_kickoff.isoformat().replace(
                    "+00:00", "Z"
                ),
                "market": row["market"],
                "subject": row.get("subject", ""),
                "line": row["line"],
                "direction": row["direction"],
                "model_p": round(row["p_central"], 4),
                "confidence": realised_lo,
                # The curve's own number before the gap shrink - written only
                # while the shrink is on, so an artifact built with it off is
                # byte-for-byte what it was before 2026-10-04.
                **({"confidence_curve": curve_lo} if cal.gap_shrink_k > 0 else {}),
                "calibrated_on": source,
                "calibration_n": n_cal,
                "sample_size": row["sample_size"],
                "sample_observations": len(values),
                "sample_oldest_days": oldest_days,
                "sample_newest_days": newest_days,
                "sample_min": min(values) if values else None,
                "sample_max": max(values) if values else None,
                # How often the line held in the leg's own sample - the
                # number the verifier compared by hand on 2026-10-04 (model
                # 0.786 against 14/20 on Farense - Chaves). Shown, not gated:
                # measure_own_sample_gap.py found no gap band that realises
                # worse than the price on all rows (data/analysis_2026-10-04_
                # history/own_sample_gap_football.md).
                "sample_hit_rate": (
                    round(own_rate, 4)
                    if (own_rate := own_hit_rate(values, row["line"], row["direction"]))
                    is not None else None
                ),
                # bet.sofa.schedule's tags for the fixture (make-up fixture,
                # long layoff, congestion) and an automatic WATCH this profile
                # kept, written only when there is one.
                **(
                    {"context_flags": flags}
                    if (flags := schedule_flags(row["sofascore_event_id"])
                        + auto_watch)
                    else {}
                ),
                "offered_odds": odds,
                "implied_p": round(1.0 / odds, 4),
                # What Superbet's shading costs on THIS leg, in probability
                # and then in money. The operator has accepted the shading;
                # this is so he can see how much of it he is accepting.
                "shading": round(realised_lo - 1.0 / odds, 4),
                "leg_ev": round(realised_lo * odds - 1.0, 4),
                "market_p": row.get("market_p"),
                # See MAX_OVERROUND. What share of this ladder's price is the
                # bookmaker's own margin — the operator's "is this robbery"
                # question, answered from the two-sided price and nothing else.
                "overround": (
                    round(rung_overround, 4) if rung_overround is not None else None
                ),
                # CLAUDE.md: never strip UNFITTED_CONSTANTS from a row. The
                # sheet stamps it in `notes`, which a leg does not carry, so
                # until 2026-09-25 both confidence artifacts and their .md
                # said it zero times - only the PDF banner re-read the sheet.
                "unfitted_constants": unfitted_from_notes(row.get("notes")),
                # The reads that cover the leg (reads.json), written only when
                # there is one - a WATCH leg the WARIANT kept is marked, so the
                # ledger can grade WATCH; an artifact without reads is
                # byte-for-byte what it was before 2026-10-04.
                **(
                    {"reads": [
                        {"verdict": r.verdict, "author": r.author, "reason": r.reason}
                        for r in row_reads
                    ]}
                    if row_reads else {}
                ),
                # The stats-only epoch (K0/K11): the second number, never
                # calibrated, never a gate; the price the sheet carried when
                # the leg was re-priced at the fresh one (K2).
                **(
                    {
                        "epoch": STATS_ONLY,
                        "forecast_p": row.get("forecast_p"),
                        "forecast_source": row.get("forecast_source"),
                        **(
                            {"sheet_odds": sheet_odds}
                            if sheet_odds is not None else {}
                        ),
                    }
                    if so else {}
                ),
                # Not serialised: the builder needs to intersect legs on the
                # matches they came from. Stripped before the artifact is
                # written.
                "_obs_by_match": obs_by_match,
            }
        )
        if removal is not None:
            refused[removal[0]] += 1
            # Only a leg the page would have printed as a single is "removed
            # from the coupon"; the rest was never on it.
            if profile.single_is_fairly_priced(leg.get("overround")):
                removed_by_reads.append({
                    **{k: v for k, v in leg.items() if not k.startswith("_")},
                    "refusal": removal[0],
                    "reason": removal[1],
                })
            continue
        legs.append(leg)

    # Legs the previous build of this profile printed and whose match has
    # started (or is inside the kickoff margin) by now: kept exactly as
    # printed, first on the page (locked_print). A leg the previous build
    # printed and this one drops BEFORE its match starts is not here - the
    # operator saw this PDF before the kickoff.
    def is_locked(event_id: int, printed_kickoff: str | None) -> bool:
        fx_now = fixtures.get(event_id)
        if fx_now is None:
            # No fixture any more: the printed (earliest) clock is all there is.
            return too_close_to_kickoff(kickoff_clocks(None, printed_kickoff), now)
        return kicked_off(
            fx_now, seen_kickoff.get(event_id), event_id in started_ids, now
        )

    locked = carry_over(
        previous, profile.name, now, is_locked, pdf_printed=previous_printed,
        sports=frozenset({"football", "tennis"}) if so else None,
    )
    # Stats-only: the coupon as its PDF last printed it (PRINTED_MANIFEST)
    # is carried over too, so an unprinted rebuild in between cannot drop a
    # leg the operator holds on paper.
    manifest_path = run_dir / PRINTED_MANIFEST
    if so and manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            print(f"REFUSED: {PRINTED_MANIFEST} is unreadable ({exc}); it is the "
                  "record of the last printed coupon", file=sys.stderr)
            return 2
        locked = merge_locked(
            carry_over(manifest, profile.name, now, is_locked, pdf_printed=True,
                       sports=frozenset({"football", "tennis"})),
            locked,
        )
    locked_keys = locked.keys
    # Never the same leg twice: the gate above already refuses a locked
    # fixture's rows, this holds even if the two ever disagree.
    legs = [leg for leg in legs if leg_key(leg) not in locked_keys]
    # A veto or a NO_BET / WATCH read covering a locked leg does not remove
    # it (its match is under way); it is recorded and shown, never acted on.
    late_refusals: list[dict[str, Any]] = []
    locked_rungs = [("single", leg_key(s_)) for s_ in locked.singles] + [
        ("builder_leg", leg_key(x_, b_["sofascore_event_id"]))
        for b_ in locked.builders
        for x_ in b_.get("legs") or []
    ]
    for kind, (eid_, market_, subject_, line_, direction_) in locked_rungs:
        if any(
            veto_matches(
                v, sofascore_event_id=eid_, market=market_, subject=subject_,
                line=line_, direction=direction_,
            )
            for v in vetoes
        ):
            why: str | None = "VETOED"
        else:
            why = read_refusal(
                matching_reads(
                    reads, sofascore_event_id=eid_, market=market_,
                    subject=subject_, line=line_, direction=direction_,
                ),
                profile.honours_watch,
            )
        if why is not None:
            rung = [eid_, market_, subject_, line_, direction_]
            late_refusals.append({"key": rung, "as": kind, "refusal": why})
            print(f"LOCKED_DESPITE_LATE_REFUSAL: {why} {kind} {rung}", file=sys.stderr)

    # K3 (stats-only): confidence, the earlier start, the match - never EV.
    if so:
        legs.sort(key=coupon_sort_key)
    else:
        legs.sort(key=lambda r: (-r["leg_ev"], -r["confidence"]))

    # Singles. Deliberately NOT ranked by `leg_ev` — see MAX_OVERROUND for why
    # that ordering is inverted against the settled outcomes. A single is
    # selected on the two questions the operator actually asks: is it likely,
    # and is the ladder cheap. Ties break on the shorter price, because within
    # a calibration bucket the shorter price is measured to hit more often.
    singles = sorted(
        (leg for leg in legs
         if profile.single_is_fairly_priced(leg.get("overround"))),
        key=(
            coupon_sort_key if so
            else lambda r: (-r["confidence"], r["offered_odds"])
        ),
    )
    # Locked singles first; the fresh ones fill the room left on the page
    # (printed_singles cuts the list at pdf_max_singles).
    singles = [*locked.singles, *singles]
    pdf_max_singles = profile.pdf_max_singles
    if pdf_max_singles is not None and len(locked.singles) > pdf_max_singles:
        # Only if the page limit was lowered between two builds: a printed
        # leg is never pushed off the page by the limit.
        pdf_max_singles = len(locked.singles)

    # Bet Builders: same fixture, one leg per market family, 2-4 legs.
    builders: list[dict[str, Any]] = []
    by_fixture: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for leg in legs:
        by_fixture[leg["sofascore_event_id"]].append(leg)
    for eid, group in by_fixture.items():
        # One leg per QUANTITY, not per market: a team's goals and the match
        # total are the same quantity counted twice (lambda 2.165), and
        # multiplying them would sell two legs as four. See QUANTITY_FAMILIES.
        # Ranked by leg EV, not by confidence — **at both levels**, which is
        # the part that was missing. Ranking by confidence is ranking by
        # shortness of price: the two are near-inverses, because the book
        # prices a near-certainty at a near-certainty. That was the root cause
        # of the 2026-09-20 defect, and fixing only the cross-family sort left
        # it alive one level down — a family's EV-positive leg was discarded in
        # favour of its shortest-priced sibling *before* the EV ordering ever
        # ran, so the pool it ranked was already the wrong pool.
        # Stats-only (D3, K10): chosen and ordered by confidence instead.
        pool = (
            sorted(best_leg_per_quantity(group, by_confidence=True).values(),
                   key=coupon_sort_key)
            if so
            else sorted(best_leg_per_quantity(group).values(),
                        key=lambda r: -r["leg_ev"])
        )
        if len(pool) < MIN_BUILDER_LEGS:
            continue
        for size in range(MIN_BUILDER_LEGS, min(MAX_BUILDER_LEGS, len(pool)) + 1):
            combo = pool[:size]
            # Multiplying assumes independence. Legs that disagree about
            # tempo are negatively correlated, so the product overstates the
            # joint and the slip's EV would be reported too high.
            if not builder_legs_are_coherent(combo):
                refused["BUILDER_LEGS_INCOHERENT"] += 1
                continue
            product_p = combined_probability([c["confidence"] for c in combo])
            hits, n_joint = empirical_joint(
                [c["_obs_by_match"] for c in combo],
                [(c["line"], c["direction"]) for c in combo],
            )
            p = joint_probability(product_p, hits, n_joint)
            odds_product = math.prod(c["offered_odds"] for c in combo)
            effective_odds = builder_odds(odds_product)
            builders.append(
                {
                    "sofascore_event_id": eid,
                    "match": combo[0]["match"],
                    "competition": combo[0]["competition"],
                    "kickoff_utc": combo[0]["kickoff_utc"],
                    "legs": [
                        {
                            "market": c["market"], "subject": c["subject"],
                            "line": c["line"], "direction": c["direction"],
                            "confidence": c["confidence"], "odds": c["offered_odds"],
                            "unfitted_constants": c["unfitted_constants"],
                        }
                        for c in combo
                    ],
                    "n_legs": size,
                    "combined_probability": round(p, 4),
                    # The product on its own, kept so the two estimates stay
                    # comparable in the artifact.
                    "product_probability": round(product_p, 4),
                    # How often every leg held in the SAME past match. `n` is
                    # the intersection of the legs' samples, so it is smaller
                    # than any single leg's sample and is often 0.
                    "empirical_joint_hits": hits,
                    "empirical_joint_n": n_joint,
                    "fair_odds": fair_odds(p),
                    # Shading compounds. Each leg returns confidence*odds; a
                    # builder priced at the product of its legs returns the
                    # product of those, so a 4.5 pp shade per leg is not a
                    # 4.5 pp shade on the slip. This is the reference price,
                    # NOT Superbet's builder price (see fair_odds).
                    "odds_if_product": round(odds_product, 2),
                    "ev_if_product_priced": round(
                        math.prod(
                            c["confidence"] * c["offered_odds"] for c in combo
                        )
                        - 1.0,
                        4,
                    ),
                    # The price the operator can actually expect, and the only
                    # EV this stage selects on. See BUILDER_CORRELATION_HAIRCUT:
                    # Superbet takes 9-20% for the correlation, so ranking on
                    # the raw product ranked on a price the book never quoted.
                    "haircut": BUILDER_CORRELATION_HAIRCUT,
                    "odds_after_haircut": round(effective_odds, 3),
                    "ev_after_haircut": round(p * effective_odds - 1.0, 4),
                    # K10: which predicate decides it (confidence.is_stakeable).
                    **({"stakeable_rule": STAKEABLE_RULE_X} if so else {}),
                }
            )
    if so:
        # K10: the most likely combination first; best_for_fixture follows.
        builders.sort(key=lambda b: (
            -b["combined_probability"], b["kickoff_utc"], b["sofascore_event_id"],
            b["n_legs"]))
    else:
        builders.sort(key=lambda b: (-b["ev_after_haircut"], -b["combined_probability"]))

    # A fixture emits a 2-, 3- and 4-leg builder off the same ranked pool, so
    # the smaller ones are SUBSETS of the larger. Staking all three is staking
    # one opinion three times at three stakes, and on 2026-09-19 that dressed
    # 54 fixtures up as 79 independent bets with 46 of 148 legs repeated.
    # Every builder stays in the artifact because comparing 2 against 4 on one
    # fixture is exactly how the operator picks; only one per fixture is
    # marked as stakeable.
    # A fixture whose printed builder is locked keeps that one as its stake.
    best_seen: set[int] = set(locked.builder_fixtures)
    for b in builders:
        eid = b["sofascore_event_id"]
        b["best_for_fixture"] = eid not in best_seen
        best_seen.add(eid)

    for leg in legs:
        leg.pop("_obs_by_match", None)
    legs = [*locked.legs, *legs]
    builders = [*locked.builders, *builders]

    # T27, applied here too: a veto that matched no row on the sheet is a typo
    # or a row that moved between the analyst's read and this rebuild. Either
    # way it did nothing, and a silent no-op reads exactly like a veto that was
    # honoured.
    unmatched = [
        v
        for v in vetoes
        if not any(
            veto_matches(
                v,
                sofascore_event_id=row["sofascore_event_id"],
                market=row["market"],
                subject=row.get("subject") or "",
                line=row["line"],
                direction=row["direction"],
            )
            for row in sheet
        )
    ]
    for v in unmatched:
        print(f"UNMATCHED_VETO: {v.model_dump_json()}", file=sys.stderr)
    # The same for reads: a read that covers no row on the sheet did nothing.
    reads_unmatched = [
        r
        for r in reads
        if not any(
            veto_matches(
                r,
                sofascore_event_id=row["sofascore_event_id"],
                market=row["market"],
                subject=row.get("subject") or "",
                line=row["line"],
                direction=row["direction"],
            )
            for row in sheet
        )
    ]
    for r in reads_unmatched:
        print(f"UNMATCHED_READ: {r.model_dump_json()}", file=sys.stderr)

    out = {
        "created_at_utc": now.isoformat().replace("+00:00", "Z"),
        "profile": profile.name,
        # bet.sofa.epochs; written only in the stats-only epoch, so an older
        # build is byte-for-byte what it was.
        **({"epoch": STATS_ONLY, "stakeable_rule": STAKEABLE_RULE_X} if so else {}),
        "confidence_floor": args.floor,
        "min_ev": profile.min_ev,
        "max_overround": profile.max_overround,
        "pdf_max_singles": pdf_max_singles,
        "prints_builders": profile.prints_builders,
        **({"gap_shrink_k": cal.gap_shrink_k} if cal.gap_shrink_k > 0 else {}),
        "vetoes_applied": len(vetoes) - len(unmatched),
        "vetoes_unmatched": len(unmatched),
        # Written only when something was carried over, so an artifact
        # without a locked leg is byte-for-byte what it was before 2026-10-05.
        **(
            {
                "locked_from_utc": locked.previous_created_at_utc,
                "locked_singles": len(locked.singles),
                "locked_builders": len(locked.builders),
                "locked_late_refusals": late_refusals,
            }
            if locked else {}
        ),
        # Written only when reads.json holds any, so a day without reads is
        # byte-for-byte what it was before 2026-10-04.
        **(
            {
                "honours_watch": profile.honours_watch,
                "reads_applied": len(reads) - len(reads_unmatched),
                "reads_unmatched": len(reads_unmatched),
            }
            if reads else {}
        ),
        "unfitted_constants": sorted(
            {
                c
                for item in [*singles, *(x for b in builders for x in b["legs"])]
                for c in item.get("unfitted_constants") or []
            }
        ),
        "legs": legs,
        **({"removed_by_reads": removed_by_reads} if so else {}),
        "singles": [
            {k: v for k, v in s_.items() if not k.startswith("_")} for s_ in singles
        ],
        "builders": builders,
    }
    write_atomic(
        run_dir / artifact, json.dumps(out, indent=1, ensure_ascii=False) + "\n"
    )

    lines = [
        f"# Confidence view — {args.date}"
        + ("" if profile.name == "standard" else f" — WARIANT ({profile.name})"),
        "",
        f"Built {out['created_at_utc']}. Floor: measured lower bound >= {args.floor}. "
        + (
            "Price: confidence x odds > 1.00."
            if profile.min_ev is None
            else f"Price: confidence x odds >= {profile.min_ev:.2f} (a price up to "
            f"{1 - profile.min_ev:.0%} below fair is accepted), ladder margin "
            f"<= {profile.max_overround:.1%}."
            + ("" if profile.name == "standard"
               else " NOT the official coupon - settled beside it.")
        ),
        "",
        "`confidence` is the **lower bound of the realised rate** for this market at "
        "this model probability, fitted on 1,868,474 settled rows — not the model's "
        "own claim. The curve tops out near 0.92: there is no 98% leg.",
        "",
        *(
            [
                f"**UNFITTED_CONSTANTS: {', '.join(out['unfitted_constants'])}** "
                "- these constants are not fitted to settlements; the numbers "
                "below stand on them.",
                "",
            ]
            if out["unfitted_constants"]
            else []
        ),
        "## Legs",
        "",
        "| conf | odds | implied | shading | leg EV | market | line | match | kickoff |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for leg in legs[:60]:
        subj = f" {leg['subject']}" if leg["subject"] else ""
        lines.append(
            f"| {leg['confidence']:.3f} | {leg['offered_odds']} | "
            f"{leg['implied_p']:.3f} | {leg['shading']:+.3f} | {leg['leg_ev']:+.3f} | "
            f"{leg['market']}{subj} | {leg['line']} {leg['direction']} | "
            f"{leg['match']} | {leg['kickoff_utc'][11:16]}Z |"
        )
    lines += [
        "",
        "## Pojedyncze zakłady",
        "",
        "Uszeregowane po **pewności**, nie po `leg EV` — to drugie jest zmierzone "
        "jako odwrócone (patrz `MAX_OVERROUND`): wewnątrz jednego kubełka "
        "kalibracji `leg EV` rośnie wyłącznie z kursem, a dłużej wyceniona "
        "jedna trzecia kubełka trafia **rzadziej**. `marża` to narzut Superbeta "
        f"na tej drabinie; powyżej {profile.max_overround:.1%} noga nie "
        "trafia na tę listę w ogóle.",
        "",
        "To nie jest obietnica zysku. Ta populacja nóg rozliczyła się na "
        "**−4.0%** przy trafialności 87.1% — i niemal wszystko to jeden dzień "
        "(5 220 z 5 285 nóg to 2026-09-19).",
        "",
        "| conf | kurs | x | marża | próbka | rynek | linia | mecz |"
        " start |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    # See fixture_leg_counts: singles of one match are one bet in pieces.
    per_fixture = fixture_leg_counts(singles[:40])
    for leg in singles[:40]:
        subj = f" {leg['subject']}" if leg["subject"] else ""
        n_same = per_fixture[int(leg["sofascore_event_id"])]
        same = f" (ten sam mecz: {n_same} nóg)" if n_same > 1 else ""
        if leg.get("locked"):
            same += " (w grze - wydrukowane przed startem)"
        lines.append(
            f"| {leg['confidence']:.3f} | {leg['offered_odds']} | "
            f"{leg['leg_ev'] + 1.0:.2f} | "
            f"{leg['overround']:.1%} | {leg['sample_size']} | "
            f"{leg['market']}{subj} | {leg['line']} {leg['direction']} | "
            f"{leg['match']}{same} | {leg['kickoff_utc'][11:16]}Z |"
        )
    if not singles:
        lines.append("| — | — | — | — | brak nóg na uczciwej drabinie | — | — | — |")
    lines += [
        "",
        "## Bet Builders (same match)",
        "",
        "`fair_odds` is what the combination must pay to be worth its risk. "
        "`odds after haircut` is the product of the legs less the measured "
        f"{BUILDER_CORRELATION_HAIRCUT:.0%} correlation markup (8.8-19.6% on the "
        "three builders priced off Superbet's screen on 2026-09-20), and **EV** is "
        "computed against it. If the screen shows more than `odds after haircut`, "
        "the slip is better than this table says; if less, it is worse.",
        "",
        "`combined p` is the lower of the leg product and the empirical joint — how "
        "often every leg held in the same past match. `joint` shows that count.",
        "",
        "| legs | combined p | joint | fair odds | product | after haircut | EV | match | selection |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for b in [x for x in builders if x["best_for_fixture"]][:40]:
        sel = " + ".join(
            f"{x['market']} {x['line']} {x['direction']}" for x in b["legs"]
        )
        joint = (
            f"{b['empirical_joint_hits']}/{b['empirical_joint_n']}"
            if b["empirical_joint_n"]
            else "—"
        )
        lines.append(
            f"| {b['n_legs']} | {b['combined_probability']:.3f} | {joint} | "
            f"{b['fair_odds']} | {b['odds_if_product']} | "
            f"{b['odds_after_haircut']} | {b['ev_after_haircut']:+.3f} | "
            f"{b['match']} | {sel} |"
        )
    write_atomic(run_dir / artifact.replace(".json", ".md"), "\n".join(lines) + "\n")

    print(json.dumps({
        "stage": "CONFIDENCE", "verdict": "OK", "profile": profile.name,
        "metrics": {
            "legs": len(legs), "singles": len(singles),
            "builders": len(builders),
            # Both halves of the PDF's own gate, separately, because reporting
            # only the first one made CONFIDENCE contradict the coupon it
            # feeds: on 2026-09-21 this said "3 stakeable" on a day the PDF
            # staked nothing, all three having been refused for negative EV
            # after the measured correlation haircut. A summary that disagrees
            # with the artifact downstream of it is worse than no summary.
            "best_for_fixture": sum(1 for b in builders if b["best_for_fixture"]),
            # What the PDF prints, so a profile that prints no builders
            # cannot report stakeable ones (the variant said 2 over 0 on
            # 2026-09-29, before it printed builders).
            "stakeable_builders": (
                sum(1 for b in builders if is_stakeable(b))
                if profile.prints_builders else 0
            ),
            "fixtures_with_legs": len(by_fixture), "refused": dict(refused),
            "locked_singles": len(locked.singles),
            "locked_builders": len(locked.builders),
            "locked_late_refusals": len(late_refusals),
            "vetoes_applied": len(vetoes) - len(unmatched),
            "vetoes_unmatched": len(unmatched),
            "vetoed_rungs": len(vetoed_keys),
            "reads_applied": len(reads) - len(reads_unmatched),
            "reads_unmatched": len(reads_unmatched),
            "read_rungs": len(read_keys),
            "epoch": STATS_ONLY if so else "old",
            "removed_by_reads": len(removed_by_reads),
        },
        "output_path": str(run_dir / artifact),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
