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
import itertools
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.confidence import (  # noqa: E402
    BUILDER_CORRELATION_HAIRCUT,
    MAX_BUILDER_LEGS,
    MIN_BUILDER_LEGS,
    MAX_BUILDER_SAMPLE_AGE_DAYS,
    MAX_DISAGREEMENT,
    MAX_OVERROUND,
    MIN_BUILDER_SAMPLE,
    MIN_ODDS_FOR_CEILING,
    Calibration,
    best_leg_per_quantity,
    builder_legs_are_coherent,
    builder_odds,
    is_derived,
    is_stakeable,
    combined_probability,
    empirical_joint,
    fair_odds,
    joint_probability,
    leg_is_ev_positive,
    overround,
    single_is_fairly_priced,
    line_is_beyond_sample,
    mode_loses,
)
from scripts.sofa.run_sheet import determine_side  # noqa: E402
from pydantic import RootModel  # noqa: E402
from bet.sofa.contracts import Fixture  # noqa: E402
from bet.sofa.engine import (  # noqa: E402
    uses_empirical_frequency,
    uses_poisson_floor,
)
from bet.sofa.coupon import MAX_SAMPLE_AGE_DAYS  # noqa: E402
from bet.sofa.veto import load_vetoes, veto_matches  # noqa: E402

# A leg below this is not what the operator means by a strong read. The floor
# is on the measured LOWER bound, not on what the model claims.
DEFAULT_FLOOR = 0.80
# Superbet's own shading is accepted, but a price below this is not a shaded
# price, it is a rounding error with a stake attached.
#
# Raised 2026-09-20 from a flat 1.01 to the curve's own resolution limit. See
# MIN_ODDS_FOR_CEILING: below 1.0867 a leg cannot have positive EV under this
# calibration whatever the fixture, so admitting it and then reporting its
# contribution to a slip's EV was self-contradictory.
MIN_ODDS = MIN_ODDS_FOR_CEILING
MAX_PRICE_AGE = timedelta(minutes=45)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True)
    ap.add_argument("--floor", type=float, default=DEFAULT_FLOOR)
    ap.add_argument("--runs-dir", default="runs/sofa")
    args = ap.parse_args()

    run_dir = Path(args.runs_dir) / args.date
    sheet = json.loads((run_dir / "05_sheet.json").read_text(encoding="utf-8"))
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

    def side_observations(row: dict) -> list[dict]:
        """This row's own past matches, on the side the sheet priced.

        Carries the whole observation, not just its value, because the
        builder's empirical joint has to intersect legs on
        `sofascore_event_id` — which match a number came from is the point.
        """
        mv = (samples.get(row["sofascore_event_id"], {}).get("metrics") or {}).get(
            row["market"]
        )
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
        obs: list[dict],
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
    fetched: dict[tuple, str] = {}
    # The ladder's own margin, per rung. It is a property of the two-sided
    # price, so it is the same for OVER and UNDER of one rung.
    margins: dict[tuple[int, str, str, float, str], float | None] = {}
    for o in offers:
        for r in o.get("rungs", []):
            rung_margin = overround(r.get("over_odds"), r.get("under_odds"))
            for d in ("OVER", "UNDER"):
                fetched[
                    (o["sofascore_event_id"], r["market"], r.get("subject", ""),
                     r["line"], d)
                ] = r.get("fetched_at_utc")
                margins[
                    (o["sofascore_event_id"], r["market"], r.get("subject", ""),
                     r["line"], d)
                ] = rung_margin

    cal = Calibration.load()
    now = datetime.now(timezone.utc)

    # The analyst's vetoes, which until 2026-09-21 this stage did not read.
    # COUPON honoured them and CONFIDENCE did not, so a veto removed a row
    # from 06_coupon.json — the VALUE singles, which the runbook is explicit
    # are not the coupon — and left the same row standing as a leg of the Bet
    # Builder the PDF actually stakes. The one channel a human read has into
    # this pipeline could not reach its product.
    vetoes = load_vetoes(run_dir / "vetoes.json")
    vetoed_keys: set[tuple] = set()

    legs: list[dict] = []
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
        # The EARLIER of the two clocks, as coupon.py has done since F26 —
        # this stage read only Sofascore's, which is the later one for ITF.
        # Sofascore publishes the tournament's local time as though it were
        # UTC there, so the error runs the wrong way: a finished match looks
        # upcoming. On 2026-09-21 the day's only tennis leg was an ITF fixture
        # whose two clocks disagreed by 2.0 h, and the gap reaches 11.0 h
        # elsewhere on that board. The staked path was the one reading the
        # wrong clock.
        clocks = [
            datetime.fromisoformat(t.replace("Z", "+00:00"))
            for t in (fx.get("kickoff_utc"), fx.get("superbet_kickoff_utc"))
            if t
        ]
        if not clocks or min(clocks) <= now:
            refused["KICKED_OFF"] += 1
            continue
        key = (row["sofascore_event_id"], row["market"], row.get("subject", ""),
               row["line"], row["direction"])
        ts = fetched.get(key)
        rung_overround = margins.get(key)
        if ts is None:
            refused["NO_FETCHED_AT"] += 1
            continue
        if now - datetime.fromisoformat(ts.replace("Z", "+00:00")) > MAX_PRICE_AGE:
            refused["STALE_PRICE"] += 1
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
        if not uses_poisson_floor(row["market"]) and not uses_empirical_frequency(
            row["market"]
        ):
            refused["NOT_IN_CALIBRATION_FIT"] += 1
            continue
        # See DERIVED_PREFIXES. A joint of two sides is not a count of one
        # thing, has 2-252 settled rows of its own, and no sample in the
        # artifacts can check it.
        if is_derived(row["market"]):
            refused["DERIVED_NOT_CALIBRATABLE"] += 1
            continue

        hit = cal.realised(row["market"], row["p_central"], row.get("sport"))
        if hit is None:
            # No measurement for this bucket. The model's own number is not a
            # substitute for one, so the leg is refused rather than guessed.
            refused["NOT_CALIBRATED"] += 1
            continue
        realised_lo, source, n_cal = hit
        if realised_lo < args.floor:
            refused["BELOW_CONFIDENCE_FLOOR"] += 1
            continue
        # See MAX_DISAGREEMENT. Shading means the book pays us less than the
        # event is worth; this is the opposite case, where we claim far more
        # than the book does, and it is measured to end below a coin flip.
        if realised_lo - 1.0 / odds > MAX_DISAGREEMENT:
            refused["DISAGREES_WITH_PRICE"] += 1
            continue
        # The leg has to clear its own price using its own number. Without
        # this the builder reported an EV it was simultaneously destroying:
        # `ev_if_product_priced` is prod(confidence * odds) - 1, so a leg
        # whose own product is below 1 drags every slip it joins.
        if not leg_is_ev_positive(realised_lo, odds):
            refused["NEGATIVE_LEG_EV"] += 1
            continue

        observations = side_observations(row)
        values, oldest_days, newest_days = sample_values(observations)
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

        legs.append(
            {
                "sofascore_event_id": row["sofascore_event_id"],
                "match": f"{fx['home_name']} - {fx['away_name']}",
                "competition": fx.get("competition_name"),
                "sport": row["sport"],
                "kickoff_utc": fx["kickoff_utc"],
                "market": row["market"],
                "subject": row.get("subject", ""),
                "line": row["line"],
                "direction": row["direction"],
                "model_p": round(row["p_central"], 4),
                "confidence": realised_lo,
                "calibrated_on": source,
                "calibration_n": n_cal,
                "sample_size": row["sample_size"],
                "sample_observations": len(values),
                "sample_oldest_days": oldest_days,
                "sample_newest_days": newest_days,
                "sample_min": min(values) if values else None,
                "sample_max": max(values) if values else None,
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
                # Not serialised: the builder needs to intersect legs on the
                # matches they came from. Stripped before the artifact is
                # written.
                "_obs_by_match": obs_by_match,
            }
        )

    legs.sort(key=lambda r: (-r["leg_ev"], -r["confidence"]))

    # Singles. Deliberately NOT ranked by `leg_ev` — see MAX_OVERROUND for why
    # that ordering is inverted against the settled outcomes. A single is
    # selected on the two questions the operator actually asks: is it likely,
    # and is the ladder cheap. Ties break on the shorter price, because within
    # a calibration bucket the shorter price is measured to hit more often.
    singles = sorted(
        (leg for leg in legs if single_is_fairly_priced(leg.get("overround"))),
        key=lambda r: (-r["confidence"], r["offered_odds"]),
    )

    # Bet Builders: same fixture, one leg per market family, 2-4 legs.
    builders: list[dict] = []
    by_fixture: dict[int, list[dict]] = defaultdict(list)
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
        pool = sorted(best_leg_per_quantity(group).values(), key=lambda r: -r["leg_ev"])
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
                }
            )
    builders.sort(key=lambda b: (-b["ev_after_haircut"], -b["combined_probability"]))

    # A fixture emits a 2-, 3- and 4-leg builder off the same ranked pool, so
    # the smaller ones are SUBSETS of the larger. Staking all three is staking
    # one opinion three times at three stakes, and on 2026-09-19 that dressed
    # 54 fixtures up as 79 independent bets with 46 of 148 legs repeated.
    # Every builder stays in the artifact because comparing 2 against 4 on one
    # fixture is exactly how the operator picks; only one per fixture is
    # marked as stakeable.
    best_seen: set[int] = set()
    for b in builders:
        eid = b["sofascore_event_id"]
        b["best_for_fixture"] = eid not in best_seen
        best_seen.add(eid)

    for leg in legs:
        leg.pop("_obs_by_match", None)

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

    out = {
        "created_at_utc": now.isoformat().replace("+00:00", "Z"),
        "confidence_floor": args.floor,
        "vetoes_applied": len(vetoes) - len(unmatched),
        "vetoes_unmatched": len(unmatched),
        "legs": legs,
        "singles": [
            {k: v for k, v in s_.items() if not k.startswith("_")} for s_ in singles
        ],
        "builders": builders,
    }
    (run_dir / "08_confidence.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    lines = [
        f"# Confidence view — {args.date}",
        "",
        f"Built {out['created_at_utc']}. Floor: measured lower bound >= {args.floor}.",
        "",
        "`confidence` is the **lower bound of the realised rate** for this market at "
        "this model probability, fitted on 1,868,474 settled rows — not the model's "
        "own claim. The curve tops out near 0.92: there is no 98% leg.",
        "",
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
        f"na tej drabinie; powyżej {MAX_OVERROUND:.1%} noga nie trafia na tę "
        "listę w ogóle.",
        "",
        "To nie jest obietnica zysku. Ta populacja nóg rozliczyła się na "
        "**−4.0%** przy trafialności 87.1% — i niemal wszystko to jeden dzień "
        "(5 220 z 5 285 nóg to 2026-09-19).",
        "",
        "| conf | kurs | marża | próbka | rynek | linia | mecz | start |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for leg in singles[:40]:
        subj = f" {leg['subject']}" if leg["subject"] else ""
        lines.append(
            f"| {leg['confidence']:.3f} | {leg['offered_odds']} | "
            f"{leg['overround']:.1%} | {leg['sample_size']} | "
            f"{leg['market']}{subj} | {leg['line']} {leg['direction']} | "
            f"{leg['match']} | {leg['kickoff_utc'][11:16]}Z |"
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
    (run_dir / "08_confidence.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "stage": "CONFIDENCE", "verdict": "OK",
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
            "stakeable_builders": sum(1 for b in builders if is_stakeable(b)),
            "fixtures_with_legs": len(by_fixture), "refused": dict(refused),
            "vetoes_applied": len(vetoes) - len(unmatched),
            "vetoes_unmatched": len(unmatched),
            "vetoed_rungs": len(vetoed_keys),
        },
        "output_path": str(run_dir / "08_confidence.json"),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
