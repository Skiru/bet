#!/usr/bin/env python3
"""Measure, per market, how well this pipeline actually forecasts the count.

    # rebuild both configs from every settled fixture in runs/
    python3 scripts/simple/measure_market_reliability.py --write

    # look without writing
    python3 scripts/simple/measure_market_reliability.py

Why this exists. The sheet has always emitted ``P(over 21.5)`` and has never
once emitted "we expect 24.4 fouls". The two are not the same claim and only
the second one can be checked against a scoreboard: a probability is right or
wrong only in aggregate, while a point forecast has an error you can print. So
every market gets its error measured here, over the fixtures in ``runs/`` that
have been played, and the number travels with the forecast afterwards.

It produces two files, both from one pass because they come from one join:

``config/league_baselines.json``
    ``{market: {competition_id: {mean, matches}}}`` -- what a market averages
    *in that competition*. ``analyze.shrunk_centre`` shrinks a thin sample
    toward a prior, and until now that prior was one number for every league on
    earth. Measured here, ``goals_1h_total`` runs 0.82 in the Argentine Liga
    Profesional and 1.47 in the highest bucket -- an 80% spread that the single
    pinned 1.243 charged to every fixture alike. On 2026-09-07 that difference
    was the whole of the day's only bet: the row cleared its threshold at 1.599
    against a price of 1.62 and needed 1.688 once the prior knew which league
    it was in.

``config/market_reliability.json``
    ``{scope: {bias, mae, mae_baseline, skill, fixtures}}`` -- the forecast's
    measured error, where ``scope`` is the market for football and
    ``market@BO3``/``market@BO5`` for tennis, because those are two different
    forecasting problems and pooling them hides the one that is broken. ``skill``
    is ``1 - mae/mae_baseline``: positive means the sample beat a constant,
    negative means it did not. Two markets are negative and both were shipping
    rungs as though they were not.

**No leakage of the target.** Actuals come from ``runs/_backtest_actuals.json``,
which is a fixture's own result; forecasts come from that fixture's dossier,
which is strictly pre-match. The one place the two could meet is the league
baseline, because a fixture settled in August is an *observation* in
September's dossiers -- so the evaluated fixture's own ``match_id`` is excluded
from the baseline it is scored against.

**What this cannot measure.** ``aces_*`` and ``double_faults_*`` never settle:
ESPN answers ``statsSource: none`` for tennis and bzzoiro's tennis addon is not
paid for. Those markets get no entry rather than an optimistic one, and a
missing entry must read as "never checked", never as "fine".

Exit codes: 0 = measured, 2 = nothing to measure.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "src")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from pydantic import ValidationError  # noqa: E402

from bet.simple_stats.analyze import (  # noqa: E402
    SHRINKAGE_K,
    _competition_id_for,
    analyze_dossier,
    market_priors,
    scope_values,
    shrinkage_target,
    tennis_match_format,
    venue_market_priors,
)
from bet.simple_stats.contracts import EventDossierV1, SuperbetOfferV1  # noqa: E402
from bet.simple_stats.offered_lines import OfferedLines  # noqa: E402
from bet.simple_stats.providers import ProviderValue  # noqa: E402
from bet.simple_stats.settle import actual_value, settle  # noqa: E402

ACTUALS = ROOT / "runs" / "_backtest_actuals.json"
BASELINES_OUT = ROOT / "config" / "league_baselines.json"
RELIABILITY_OUT = ROOT / "config" / "market_reliability.json"

# A competition needs this many independent matches before its own mean is
# preferred to the pooled one. Same floor market_priors.json uses for a pooled
# prior, and for the same reason: below it the "league baseline" is a handful of
# fixtures and shrinking toward it is shrinking toward noise.
MIN_BASELINE_MATCHES = 40

# A scope needs this many settled fixtures before its error is reported. Below
# it the bias is dominated by which week happened to be sampled.
MIN_SCOPE_FIXTURES = 25

# Providers whose observations may build a baseline. bzzoiro alone for football:
# it is the only one that stamps a competition id, and a baseline keyed by
# competition cannot be built from rows that name none (espn-football stamps
# null on all of them). Tennis has no competition-keyed baseline at all -- the
# format is the scope there, not the tournament.
BASELINE_PROVIDERS = ("bzzoiro",)
TENNIS_PROVIDERS = ("tennis-abstract", "espn-tennis", "sackmann")

def _run_dirs() -> list[Path]:
    """Every ``runs/<YYYY-MM-DD>/`` that holds both artifacts this needs."""
    out = []
    for path in sorted((ROOT / "runs").iterdir()):
        if not path.is_dir() or len(path.name) != 10:
            continue
        date = path.name
        if (path / f"{date}_event_dossiers.json").exists() and (
            path / f"{date}_event_list.json"
        ).exists():
            out.append(path)
    return out


def _buckets(metric: dict, providers: tuple[str, ...]) -> dict[str, list[ProviderValue]]:
    """The three raw buckets, parsed, restricted to providers this pass reads.

    Retired providers are skipped rather than parsed: ``bzzoiro-tennis`` appears
    in the older runs and is no longer in the ``ProviderValue`` literal, so
    validating it raises and would abort a measurement over a whole month of
    artifacts for a provider that was removed on purpose.
    """
    out: dict[str, list[ProviderValue]] = {}
    for name in ("team_a_l10", "team_b_l10", "h2h"):
        rows = [r for r in (metric.get(name) or []) if r.get("provider") in providers]
        parsed = []
        for row in rows:
            try:
                parsed.append(ProviderValue.model_validate(row))
            except Exception:  # noqa: BLE001 - a retired provider, not a bug here
                continue
        out[name] = parsed
    return out


def collect_league_baselines() -> tuple[dict, dict]:
    """``({market: {competition: {mean, matches}}}, {(market, comp): mean})``.

    Deduplicated by ``match_id``, so one match seen from both teams' buckets and
    from h2h counts once -- the same collapse the statistics apply, for the same
    reason: a league mean built from row counts would weight the clubs that
    happen to appear on more slates.
    """
    seen: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for run in _run_dirs():
        payload = json.loads((run / f"{run.name}_event_dossiers.json").read_text())
        for dossier in payload["dossiers"]:
            if dossier.get("sport") != "football":
                continue
            for market, metric in (dossier.get("metrics") or {}).items():
                if not isinstance(metric, dict):
                    continue
                for bucket in ("team_a_l10", "team_b_l10", "h2h"):
                    for row in metric.get(bucket) or []:
                        if row.get("provider") not in BASELINE_PROVIDERS:
                            continue
                        competition = row.get("competition_id")
                        if not competition:
                            continue
                        seen[(market, str(competition))][str(row["match_id"])] = float(
                            row["value"]
                        )
    document: dict[str, dict[str, dict]] = defaultdict(dict)
    lookup: dict[tuple[str, str], dict[str, float]] = {}
    for (market, competition), matches in seen.items():
        if len(matches) < MIN_BASELINE_MATCHES:
            continue
        document[market][competition] = {
            "mean": round(statistics.fmean(matches.values()), 4),
            "matches": len(matches),
        }
        lookup[(market, competition)] = matches
    return dict(document), lookup


def _forecast(values: list[float], baseline: float | None) -> float:
    """The centre the sheet prices from: sample shrunk toward its baseline.

    Deliberately the same ``n / (n + k)`` blend ``analyze.shrunk_centre`` uses,
    with the same k, because the point of this script is to score the estimator
    that ships and not a better one invented here -- including its last line,
    "returns the raw mean unchanged when the market has no pinned prior".

    That branch is not hypothetical and skipping it hid a whole market. Tennis
    ``games_won`` has no entry in ``market_priors.json`` and no league baseline
    (tennis is scoped by format, not tournament), so every ``games_won`` row
    ships an unshrunk sample mean -- and an earlier version of this pass
    dropped the market entirely on a ``baseline is None`` guard, which is how
    "how many games will she win" came to be the one per-player question with
    no measured error at all.
    """
    n = len(values)
    mean = statistics.fmean(values)
    if baseline is None:
        return mean
    weight = n / (n + SHRINKAGE_K)
    return weight * mean + (1.0 - weight) * baseline


def _offered_lines(run: Path, dossiers: list[dict]) -> OfferedLines:
    """That day's Superbet ladder, or an empty index.

    Not a nicety. The offer decides which lines the sheet has rows for at all
    (see ``offered_lines``), and the half-market ladders exist only there --
    ``standard_market_lines`` carries no static grid for ``fouls_1h_total`` or
    ``cards_2h_total``, so measuring with ``offered=None`` silently drops every
    scope the book laddered and keeps only the ones the static grid covers. The
    first faithful pass did exactly that and reported 22 scopes where the day's
    own offer yields 44: it was not that those markets forecast badly, it was
    that they were not being measured.
    """
    path = run / f"{run.name}_superbet_offer.json"
    if not path.exists():
        return OfferedLines()
    try:
        offer = SuperbetOfferV1.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return OfferedLines()
    return OfferedLines.from_offer(
        offer,
        player_names_by_event={
            d["event_id"]: [
                o.get("player_name")
                for o in (d.get("player_metrics") or [])
                if o.get("player_name")
            ]
            for d in dossiers
        },
    )


def _side_of(row, dossier: dict) -> tuple[str | None, str] | None:
    """``(side, subject key)`` for one sheet row, or None to skip it.

    ``side`` is what ``settle.actual_value`` wants: ``None`` for a match total,
    ``"home"``/``"away"`` for a participant. It is read off the row rather than
    recomputed -- football rows publish ``venue`` for exactly this purpose, and
    it is the side the subject plays on tonight. That is stricter than
    ``settle.team_side``, which has to match our spelling against the
    provider's; here both names come from the same dossier field, so equality
    is exact by construction and cannot be ambiguous.

    Tennis rows carry ``venue=None`` -- no tennis market has a venue prior, so
    ``_team_rows`` declines to name a side -- which is why the two participants
    are resolved against the dossier's own two slots. The settled tennis
    actuals key them "home"/"away" because they inherit the football schema,
    not because anybody is at home.

    A name matching neither slot returns None rather than guessing: attributing
    one player's games to the other would look exactly like a measurement.
    """
    if row.player_id is not None:
        return None, str(row.player_id)
    if row.team_name is None:
        return None, "total"
    if row.venue in ("home", "away"):
        return row.venue, row.team_name
    for side, name_key in (("home", "team_a_name"), ("away", "team_b_name")):
        if row.team_name == dossier.get(name_key):
            return side, row.team_name
    return None


def measure(baselines: dict, baseline_matches: dict) -> tuple[dict, set[str]]:
    """``(per-scope error, the markets the sheet actually prices)``.

    The forecast scored here is not recomputed -- it is taken from
    ``analyze.analyze_dossier``, the function that builds the sheet, and
    grouped exactly the way ``forecast.build_cards`` groups it: the mean of
    every surviving row's ``shrunk_mean`` for one (fixture, market, subject).

    That is a deliberate reversal. An earlier version of this pass rebuilt the
    estimator here from the raw buckets, and a row-by-row diff against the
    2026-09-07 sheet showed 185 of 2,688 per-side centres did not match the
    number the sheet actually published. The replica was missing three steps
    that only bite on some markets, which is why it looked correct: the
    ``_one_per_day`` collapse, ``_adverse_values`` resolving a provider
    conflict against the side being priced, and ``_blend_referee``. Every one
    of them is inert for a single-provider non-card sample -- and active for
    exactly the markets with two providers (goals, corroborated by
    espn-football; all of tennis) or a referee. Calling the shipping code
    cannot drift from the shipping code.

    ``mae_baseline`` still needs the shrinkage target, which is a published
    function rather than a replica, so it is asked for directly.
    """
    if not ACTUALS.exists():
        return {}, set()
    actuals = json.loads(ACTUALS.read_text())
    # Every market ANALYZE emitted a row for, settled or not. Returned so the
    # driver pass can be held to the same set: the dossier collects far more
    # than the sheet prices (1H/2H splits for fouls, shots, corners, cards and
    # offsides; ``cards_total``, retired on 2026-09-03 for counting yellows
    # while Superbet counts reds) and an earlier version of this script measured
    # all of them off the raw metrics. That is where "cards_total +0.8%",
    # "fouls_2h_total +5.9%" and "cards_2h_total +5.9%" came from -- three
    # numbers about markets no row is ever built for. A scope nothing prices is
    # not a harmless extra line: the analyst reads this file to decide what to
    # trust, and the phantom entries were the ones carrying the referee's only
    # SHARPENS verdicts.
    priced: set[str] = set()
    # (actual, forecast, target, fixture key). The fixture key is carried so
    # ``fixtures`` stays a count of fixtures now that a ``*_for`` scope
    # contributes two records per fixture -- calling those two "two fixtures"
    # would overstate the evidence behind every per-side scope by a factor of
    # two, and the two sides of one match are not two independent draws on the
    # day, the referee or the game state.
    records: dict[str, list[tuple[float, float, float | None, str]]] = defaultdict(list)
    # scope -> (p_central, won) for every rung the sheet published and the
    # scoreboard settles. MAE says how far the *level* was out; this says
    # whether the number the bet is placed from is true, and unlike MAE it is
    # comparable between a market averaging 24 fouls and one averaging 0.13
    # offsides.
    rungs: dict[str, list[tuple[float, float, str]]] = defaultdict(list)

    for run in _run_dirs():
        date = run.name
        events = {
            e["event_id"]: e
            for e in json.loads((run / f"{date}_event_list.json").read_text())["events"]
        }
        payload = json.loads((run / f"{date}_event_dossiers.json").read_text())
        offered = _offered_lines(run, payload["dossiers"])
        for raw in payload["dossiers"]:
            sport = raw.get("sport")
            event = events.get(raw["event_id"]) or {}
            if sport == "football":
                fixture = (event.get("source_ids") or {}).get("bzzoiro")
                settled = actuals.get(str(fixture)) if fixture else None
                fixture_key = str(fixture) if fixture else raw["event_id"]
                fmt = None
            else:
                settled = actuals.get("tennis:" + raw["event_id"])
                fixture_key = raw["event_id"]
                fmt = tennis_match_format(event.get("competition"))
            if not settled:
                # Analysing an unsettled fixture costs the same as a settled one
                # and can be scored against nothing, so the guard comes first.
                continue
            competition = event.get("competition")
            # ValidationError only. A broad ``except Exception`` here read a
            # NameError as "an old artifact" and reported zero scopes with no
            # traceback, which is the failure mode this whole file exists to
            # prevent -- a measurement that silently measures nothing.
            try:
                dossier = EventDossierV1.model_validate(_only_known_providers(raw, sport))
            except ValidationError:
                continue
            rows = analyze_dossier(dossier, offered, competition=competition)

            grouped: dict[tuple, list] = defaultdict(list)
            actual_for: dict[tuple, float] = {}
            for row in rows:
                priced.add(row.market)
                resolved = _side_of(row, raw)
                if resolved is None or row.shrunk_mean is None:
                    continue
                side, key = resolved
                # ``settle.actual_value`` and not a lookup written here. It
                # carries three rules this pass had wrong or missing: the
                # ``games_won`` special case (a per-side market whose name has
                # no ``_for`` suffix), the refusal to settle a total under a
                # side key, and ABSENT_MEANS_ZERO -- the provider omits
                # ``red_cards`` entirely on a match with no red card, so
                # reading the key directly measured red_cards_total *only on
                # fixtures where a red card happened*, a sample selected on the
                # event being forecast.
                figure = actual_value(
                    settled,
                    row.market,
                    side,
                    player_id=key if row.player_id is not None else None,
                )
                if figure is None:
                    continue
                grouped[(row.market, side, key)].append(row)
                actual_for[(row.market, side, key)] = figure

            for group_key, group in grouped.items():
                market = group_key[0]
                actual = actual_for[group_key]
                # Exactly forecast.build_cards: the mean over both directions,
                # because the centre is computed per direction and taking the
                # OVER's alone would tilt every reading the same way.
                forecast = statistics.fmean(
                    r.shrunk_mean for r in group if r.shrunk_mean is not None
                )
                for r in group:
                    if r.p_central is None or r.line is None:
                        continue
                    settled_rung = _settle_rung(actual, float(r.line), r.direction)
                    if settled_rung is None:
                        continue
                    rungs[
                        market if sport == "football" else f"{market}@{fmt or 'UNKNOWN'}"
                    ].append((float(r.p_central), settled_rung, fixture_key))
                venue = next((r.venue for r in group if r.venue), None)
                competition_id = (
                    _competition_id_for(dossier) if sport == "football" else None
                )
                target, _ = shrinkage_target(market, venue, competition_id)
                scope = market if sport == "football" else f"{market}@{fmt or 'UNKNOWN'}"
                records[scope].append((actual, forecast, target, fixture_key))

    out: dict[str, dict] = {}
    for scope, rows in sorted(records.items()):
        # Gated on distinct fixtures, not records.
        fixtures = len({r[3] for r in rows})
        if fixtures < MIN_SCOPE_FIXTURES:
            continue
        actual = [r[0] for r in rows]
        forecast = [r[1] for r in rows]
        # ``None`` where the market has no pinned prior anywhere -- tennis
        # ``games_won`` is the case, and there the forecast simply *is* the
        # sample mean. Those records are left out of ``mae_baseline`` rather
        # than having a target invented for them.
        targets = [(a, t) for a, _, t, _ in rows if t is not None]
        mae = statistics.fmean(abs(f - a) for a, f in zip(actual, forecast, strict=True))
        mae_base = statistics.fmean(abs(t - a) for a, t in targets) if targets else 0.0
        # The honest constant, and the one ``skill`` is computed against: this
        # scope's own mean. ``mae_baseline`` above is the *shrinkage target*,
        # which for a tennis best-of-five is a best-of-three-weighted prior of
        # 23.05 against actuals averaging 36.03 -- beating that is beating a
        # straw man, and it made total_games@BO5 read as the best-forecast
        # market on the board (+38.9%) when its error is eight games.
        scope_mean = statistics.fmean(actual)
        mae_constant = statistics.fmean(abs(scope_mean - a) for a in actual)
        priced_rungs = rungs.get(scope) or []
        out[scope] = {
            "fixtures": fixtures,
            "observations": len(rows),
            "actual_mean": round(scope_mean, 3),
            "actual_sd": (
                round(statistics.pstdev(actual), 3) if len(actual) > 1 else 0.0
            ),
            "bias": round(statistics.fmean(forecast) - scope_mean, 3),
            "mae": round(mae, 3),
            "mae_baseline": round(mae_base, 3),
            "mae_constant": round(mae_constant, 3),
            "shrinkage_target": "prior" if targets else "none",
            "skill": round(1.0 - mae / mae_constant, 4) if mae_constant else 0.0,
            "skill_vs_shrinkage_target": (
                round(1.0 - mae / mae_base, 4) if mae_base else 0.0
            ),
            # Whether ``skill`` may be compared with another scope's at all. A
            # market that happens well under once a match is one where "how
            # many" is really "whether", and there MAE is dominated by the base
            # rate: predicting roughly zero for everybody scores well without
            # discriminating between anybody. player_offsides averages 0.13 a
            # match and reads +24.2%, which is not evidence that we forecast
            # offsides better than we forecast fouls. The flag is read one
            # way only: it withholds *credit* for a positive skill and never
            # excuses a negative one, because losing to the constant is not
            # something luck does.
            "skill_comparable": scope_mean >= _BINARY_MEAN_FLOOR,
            **_calibration(priced_rungs),
        }
    return out, priced


def _only_known_providers(raw: dict, sport: str | None) -> dict:
    """The dossier with retired providers dropped from every bucket.

    ``bzzoiro-tennis`` was removed from the ``ProviderValue`` literal on
    2026-09-02 and still appears in August's artifacts, so validating one
    unmodified raises and would abort a measurement over a whole month for a
    provider that was retired on purpose.
    """
    out = json.loads(json.dumps(raw))
    keep = BASELINE_PROVIDERS + TENNIS_PROVIDERS + ("espn-football", "espn-tennis")
    for metric in (out.get("metrics") or {}).values():
        if not isinstance(metric, dict):
            continue
        for bucket in ("team_a_l10", "team_b_l10", "h2h"):
            if isinstance(metric.get(bucket), list):
                metric[bucket] = [
                    r for r in metric[bucket] if r.get("provider") in keep
                ]
    for observation in (out.get("player_metrics") or []):
        if isinstance(observation.get("l10"), list):
            observation["l10"] = [
                r for r in observation["l10"] if r.get("provider") in keep
            ]
    return out


# How much overstatement counts as material. Not a fitted number -- it is the
# size of gap that changes which side of the bar a row lands on, given the bar
# asks for a relative edge of (margin - 1)/w on a price around 1.8.
_HOT_GAP = 0.05

# Below this many events a match, a count market is really a yes/no market and
# its MAE skill stops being comparable with a market that happens twenty times.
# player_offsides averages 0.13 and scores +24.2% because predicting roughly
# nothing for everybody is close to right without discriminating between
# anybody. It withholds credit for a positive skill and never excuses a
# negative one: red_cards_total scores -47.0% here and is stepped down for it.
_BINARY_MEAN_FLOOR = 0.5


def _settle_rung(actual: float, line: float, direction: str) -> float | None:
    """1.0 if this rung won, 0.0 if it lost, None on a push or a gap.

    Delegated to ``settle.settle`` rather than reimplemented. A push is its own
    verdict there and is excluded from the hit rate rather than counted against
    it, which is the accounting a calibration figure needs: an integer line the
    result lands exactly on tells us nothing about the forecast.
    """
    outcome = settle(direction, line, actual)
    if outcome == "WON":
        return 1.0
    if outcome == "LOST":
        return 0.0
    return None


def _calibration(rungs: list[tuple[float, float, str]]) -> dict:
    """How true the probability the bet is placed from turned out to be.

    ``p_central`` is what the coupon's bar is built on (see
    ``bar-basis-is-now-p-central``), so this is the number with money on it.
    Reported alongside MAE rather than instead of it: MAE says whether the
    centre is in the right place, calibration says whether the spread around
    it is, and a market can pass either one while failing the other. It is also
    the only one of the two that is comparable between a market averaging 24
    fouls and one averaging 0.13 offsides. ``red_cards_total`` is the clearest
    case: the worst MAE on the board (-47.0%, forecasting 0.35 against an
    actual 0.16) and confident rungs calibrated to within half a point.

    Measured **conditionally on the claim**, which is the whole difficulty. A
    first version averaged ``p_central`` over every published rung and compared
    it with the realised rate, and every market on the board came back 0.500
    claimed against 0.500 realised -- necessarily, because each line is
    published on both sides, the two probabilities sum to one and exactly one
    of them wins. That number cannot be anything but a half and says nothing.

    So only the favoured side of each rung is read (``p_central >= 0.5``, one
    row per line, and the side anybody would actually take) and it is bucketed
    by what it claimed. ``calibration_error`` is the count-weighted signed gap,
    positive meaning overconfident. ``at_75`` answers the operator's own
    question -- what a "75% certain" row on this market has really done -- and
    it is reported separately because the average over all buckets can look
    fine while the tail one bets from does not.

    The interval on that tail is bootstrapped **over fixtures**, not rungs. It
    has to be: one match contributes up to forty rungs off one sample, and
    treating them as forty trials is the error that once turned a population
    artifact into a +6.2pp corroboration effect. Clustered, ``shots_for`` still
    runs 7.9 points hot [+4.4, +11.6] and ``fouls_total`` 5.1 points *cold*
    [-9.4, -0.7]: the sheet is conservative where the money is and hot on
    tennis and shots-for.
    """
    favoured = [(p, w, f) for p, w, f in rungs if p >= 0.5]
    if len(favoured) < 50:
        return {"rungs": len(favoured)}
    # Two independent gates, because the two answers need different amounts of
    # data and one of them was being lost to the other, on a market that
    # matters: red_cards_total has 593 favoured rungs but only 162 in the
    # 0.75 tail, and an earlier single gate at 200 rungs decided both. The
    # curve needs enough rungs to fill buckets; the tail needs only the tail.
    buckets: dict[int, list[tuple[float, float, str]]] = defaultdict(list)
    for point in favoured:
        buckets[min(9, int(point[0] * 20) - 10)].append(point)
    curve = {}
    weighted = 0.0
    for index in sorted(buckets):
        group = buckets[index]
        if len(group) < 30:
            continue
        claimed = statistics.fmean(p for p, _, _ in group)
        realised = statistics.fmean(w for _, w, _ in group)
        curve[f"{0.5 + index * 0.05:.2f}"] = {
            "rungs": len(group),
            "claimed": round(claimed, 4),
            "realised": round(realised, 4),
            "gap": round(claimed - realised, 4),
        }
        weighted += (claimed - realised) * len(group)
    out: dict = {"rungs": len(favoured)}
    if curve:
        out["calibration_error"] = round(weighted / len(favoured), 4)
        out["calibration_curve"] = curve
    tail = [(p, w, f) for p, w, f in favoured if p >= 0.75]
    if len(tail) >= 50:
        gap, lo, hi = _clustered_gap(tail)
        out["at_75"] = {
            "rungs": len(tail),
            "fixtures": len({f for _, _, f in tail}),
            "claimed": round(statistics.fmean(p for p, _, _ in tail), 4),
            "realised": round(statistics.fmean(w for _, w, _ in tail), 4),
            "gap": round(gap, 4),
            "gap_ci": [round(lo, 4), round(hi, 4)],
        }
        out["overconfident_at_75"] = bool(gap > _HOT_GAP and lo > 0.0)

    # Where the overconfidence actually starts, which is not the same question
    # and is the one a per-row rule needs. Overconfidence is not flat across
    # the curve: ``shots_for`` reads +0.035, -0.020, +0.011, -0.000 up to a
    # claim of 0.70 and then +0.049, +0.061, +0.083, +0.110, +0.140 -- fine
    # where most rows sit and steadily worse the more it claims. A market-wide
    # step off the 0.75 tail therefore demoted rows the market forecasts well:
    # on the 2026-09-07 slate the three shots_for UNDER 17.5 rows claimed
    # 0.813, 0.773 and 0.680, and the third is inside the calibrated stretch.
    #
    # So: the lowest threshold at or above which the market is measurably hot,
    # pooling every rung that claims at least that much. Pooled rather than
    # per-bucket because a single bucket is thin (36 rungs at 0.90 for
    # shots_for) and because the question a row asks is "is a claim of *at
    # least* this size trustworthy here", which is the pooled one.
    for threshold in (0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90):
        above = [(p, w, f) for p, w, f in favoured if p >= threshold]
        if len(above) < 50 or len({f for _, _, f in above}) < MIN_SCOPE_FIXTURES:
            continue
        gap, lo, _ = _clustered_gap(above)
        if gap > _HOT_GAP and lo > 0.0:
            out["hot_above"] = threshold
            out["hot_above_detail"] = {
                "rungs": len(above),
                "fixtures": len({f for _, _, f in above}),
                "claimed": round(statistics.fmean(p for p, _, _ in above), 4),
                "realised": round(statistics.fmean(w for _, w, _ in above), 4),
                "gap": round(gap, 4),
                "gap_ci_low": round(lo, 4),
            }
            break
    return out


def _clustered_gap(
    tail: list[tuple[float, float, str]], draws: int = 2000
) -> tuple[float, float, float]:
    """``(claimed - realised, lo, hi)`` with fixtures as the resampling unit."""
    import random

    grouped: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for claimed, won, fixture in tail:
        grouped[fixture].append((claimed, won))
    keys = list(grouped)

    def gap(sample: list[list[tuple[float, float]]]) -> float:
        points = [point for group in sample for point in group]
        if not points:
            return 0.0
        return statistics.fmean(p for p, _ in points) - statistics.fmean(
            w for _, w in points
        )

    rng = random.Random(7)
    spread = sorted(
        gap([grouped[rng.choice(keys)] for _ in keys]) for _ in range(draws)
    )
    return gap([grouped[k] for k in keys]), spread[int(0.025 * draws)], spread[
        int(0.975 * draws)
    ]


def measure_drivers(
    baselines: dict, baseline_matches: dict, priced: set[str] | None = None
) -> dict:
    """Per (market, driver): does the driver add anything *beyond* the forecast?

    This is the question the operator's own phrasing raises and it has to be
    asked as a partial correlation, not a raw one. "Over 21.5 fouls because the
    referee books people, because their h2h runs high, and because both sides
    are fouling a lot lately" reads as three reasons. Measured raw, all three
    are real: against the actual foul count the pooled sample scores +0.459,
    the referee's own rate +0.317, the h2h mean +0.291 and recent form +0.329.

    Measured against the *residual* -- what the league-aware forecast already
    got wrong -- they collapse:

        fouls_total   h2h     +0.000  [-0.102, +0.106]
        fouls_total   recency +0.015  [-0.071, +0.098]
        fouls_total   referee +0.113  [-0.030, +0.245]

    So they are not three reasons. They are three descriptions of one fact --
    this is a high-foul pairing in a high-foul league -- and the sample already
    carries it. Presenting them as independent support is how one piece of
    evidence gets counted three times, which is the failure this repository has
    already paid for twice (``p_low`` realising 23 points under its claim, and
    the corroboration effect turning out to be a population artifact).

    A driver is therefore labelled, never summed:

    ``PRICES_IN``  the sample already knows this; show the number as context
                   and do not move the centre for it.
    ``SHIFTS``     it measurably corrects the *level*. The referee blend on card
                   totals is the only one: it does nothing for MAE (-0.021,
                   CI [-0.101, +0.057]) and halves the bias, -0.37 to -0.12.
    ``SHARPENS``   it measurably reduces the error, at a level corrected for
                   how many drivers are being tested at once. Nothing has
                   earned this: the three that cleared their own 95% interval
                   all fail the family-wise one, and they were the three whose
                   intervals came within 0.011 of zero.

    Bootstrapped over fixtures rather than rows, because two rows of one match
    are one observation of the world -- the correction that turned the
    corroboration effect from +6.2pp into nothing.
    """
    if not ACTUALS.exists():
        return {}
    actuals = json.loads(ACTUALS.read_text())
    priors = market_priors()
    # market -> driver -> list of (driver deviation, residual, fixture id)
    rows: dict[str, dict[str, list[tuple[float, float, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for run in _run_dirs():
        date = run.name
        events = {
            e["event_id"]: e
            for e in json.loads((run / f"{date}_event_list.json").read_text())["events"]
        }
        for dossier in json.loads(
            (run / f"{date}_event_dossiers.json").read_text()
        )["dossiers"]:
            if dossier.get("sport") != "football":
                continue
            event = events.get(dossier["event_id"]) or {}
            fixture = (event.get("source_ids") or {}).get("bzzoiro")
            settled = actuals.get(str(fixture)) if fixture else None
            if not settled:
                continue
            totals = settled.get("total") or {}
            referee = dossier.get("referee") or {}
            competition_id = str((dossier.get("fixture_context") or {}).get("league_id"))
            for market, metric in (dossier.get("metrics") or {}).items():
                actual = totals.get(market)
                if not isinstance(metric, dict) or actual is None:
                    continue
                if priced is not None and market not in priced:
                    # A market the sheet never builds a row for has no forecast
                    # for a driver to add to, so its drivers are not findings
                    # about anything. Both of the referee's SHARPENS verdicts
                    # used to sit on such markets (cards_total, cards_1h_total),
                    # and for the card market that does ship,
                    # cards_points_total, the referee reads PRICES_IN -- which
                    # is the correct reading rather than a weaker one, because
                    # analyze._blend_referee already puts the referee into that
                    # centre, so the residual should have nothing left of it.
                    continue
                buckets = _buckets(metric, BASELINE_PROVIDERS)
                kept = {k: scope_values(v)[0] for k, v in buckets.items()}
                own = kept["team_a_l10"] + kept["team_b_l10"]
                h2h = kept["h2h"]
                if len(kept["team_a_l10"]) < 2 or len(kept["team_b_l10"]) < 2:
                    continue
                pooled = [r.value for r in own + h2h]
                baseline = _baseline_for(
                    market, competition_id, fixture, baselines, baseline_matches, priors
                )
                if baseline is None or len(pooled) < 3:
                    continue
                residual = float(actual) - _forecast(pooled, baseline)
                sides = statistics.fmean(r.value for r in own)
                if len(h2h) >= 2:
                    rows[market]["h2h"].append(
                        (statistics.fmean(r.value for r in h2h) - sides, residual, str(fixture))
                    )
                recent = _recent_mean(kept["team_a_l10"]), _recent_mean(kept["team_b_l10"])
                if all(r is not None for r in recent):
                    rows[market]["recency"].append(
                        (statistics.fmean(recent) - sides, residual, str(fixture))
                    )
                rate = _referee_rate(market, referee)
                if rate is not None:
                    rows[market]["referee"].append((rate, residual, str(fixture)))

    # Every (market, driver) pair that will be tested, counted before any of
    # them is judged. This whole table is a multiple-comparisons problem and
    # was not being treated as one: at a 95% interval per test, twenty-odd
    # tests are expected to throw up about one spurious exclusion of zero, and
    # the three SHARPENS verdicts the uncorrected pass produced -- goals_total
    # h2h [-0.256, -0.011], offsides_total h2h [+0.003, +0.253],
    # offsides_total recency [+0.002, +0.180] -- were each within 0.011 of
    # containing zero, which is exactly what chance looks like. A driver that
    # is allowed to move a bet has to clear the whole family, not its own test.
    candidates = [
        (market, driver, points)
        for market, drivers in sorted(rows.items())
        for driver, points in sorted(drivers.items())
        if len(points) >= MIN_SCOPE_FIXTURES * 2
    ]
    alpha = 0.05 / max(1, len(candidates))

    out: dict[str, dict] = {}
    for market, driver, points in candidates:
        if driver == "referee":
            centre = statistics.fmean(p[0] for p in points)
            points = [(p[0] - centre, p[1], p[2]) for p in points]
        r, lo, hi = _bootstrap_correlation(points)
        f_lo, f_hi = _bootstrap_correlation(points, draws=4000, alpha=alpha)[1:]
        out.setdefault(market, {})[driver] = {
            "observations": len(points),
            "fixtures": len({p[2] for p in points}),
            "partial_r": round(r, 3),
            "ci": [round(lo, 3), round(hi, 3)],
            "ci_familywise": [round(f_lo, 3), round(f_hi, 3)],
            "tests_in_family": len(candidates),
            # Only a correlation whose *family-wise* interval clears zero may be
            # called anything but PRICES_IN, and the label says what it earned:
            # a correlation with the residual is sharpening, not shifting.
            "status": "SHARPENS" if (f_lo > 0 or f_hi < 0) else "PRICES_IN",
            "status_at_95": "SHARPENS" if (lo > 0 or hi < 0) else "PRICES_IN",
        }
    return out


def _recent_mean(rows: list, n: int = 3) -> float | None:
    """The mean of the ``n`` newest observations in a bucket, or None."""
    dated = sorted(
        [r for r in rows if r.match_date], key=lambda r: r.match_date, reverse=True
    )[:n]
    return statistics.fmean(r.value for r in dated) if dated else None


def _referee_rate(market: str, referee: dict) -> float | None:
    """The official's own rate in this market's units, when it is comparable.

    Only the three markets a referee plausibly controls, and only above the
    sample floor the blend itself uses -- a rate off eight matches is a rate
    with a standard error wider than the effect being looked for.
    """
    if (referee.get("matches") or 0) < 15:
        return None
    if market in ("fouls_total", "fouls_1h_total", "fouls_2h_total"):
        return referee.get("avg_fouls_per_match")
    if market in ("cards_total", "cards_1h_total", "cards_2h_total"):
        return referee.get("avg_yellow_per_match")
    if market == "cards_points_total":
        yellows = referee.get("avg_yellow_per_match")
        if yellows is None:
            return None
        return yellows + 2.0 * (referee.get("avg_red_per_match") or 0.0)
    if market in ("goals_total", "goals_1h_total", "goals_2h_total"):
        return referee.get("avg_goals_per_match")
    return None


def _bootstrap_correlation(
    points: list[tuple[float, float, str]], draws: int = 2000, alpha: float = 0.05
) -> tuple[float, float, float]:
    """``(r, lo, hi)`` -- Pearson r with a two-sided interval resampled by fixture.

    ``alpha`` is the two-sided level, so the default is the plain 95% interval
    and a Bonferroni-corrected call passes ``0.05 / tests``. A corrected level
    reads further into the tail of the same resample, so it needs more draws
    to be stable there -- hence the caller doubling them.
    """
    import random

    def pearson(sample: list[tuple[float, float, str]]) -> float:
        xs = [p[0] for p in sample]
        ys = [p[1] for p in sample]
        n = len(xs)
        if n < 3:
            return 0.0
        mx, my = statistics.fmean(xs), statistics.fmean(ys)
        sx = sum((x - mx) ** 2 for x in xs) ** 0.5
        sy = sum((y - my) ** 2 for y in ys) ** 0.5
        if not sx or not sy:
            return 0.0
        return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (sx * sy)

    by_fixture: dict[str, list[tuple[float, float, str]]] = defaultdict(list)
    for point in points:
        by_fixture[point[2]].append(point)
    keys = list(by_fixture)
    random.seed(17)
    spread = []
    for _ in range(draws):
        resampled: list[tuple[float, float, str]] = []
        for _ in keys:
            resampled += by_fixture[random.choice(keys)]
        spread.append(pearson(resampled))
    spread.sort()
    lo = spread[min(draws - 1, max(0, int((alpha / 2.0) * draws)))]
    hi = spread[min(draws - 1, max(0, int((1.0 - alpha / 2.0) * draws)))]
    return pearson(points), lo, hi


def _baseline_for(
    market, competition_id, fixture, baselines, baseline_matches, priors, *, venue=None
):
    """This market's baseline for this competition, with the fixture removed.

    The three tiers, in the order ``analyze.shrinkage_target`` applies them:
    the league's own mean, then the venue prior for the football ``*_for``
    markets that have one, then the pooled prior. Falling through is never an
    error -- an unmeasured league is not a league with a mean of zero.
    """
    entry = (baselines.get(market) or {}).get(str(competition_id or ""))
    if entry is None:
        if venue is not None:
            prior = venue_market_priors().get((market, venue))
            if prior is not None:
                return prior
        return priors.get(market)
    matches = baseline_matches.get((market, str(competition_id)))
    if matches and fixture and str(fixture) in matches:
        # The evaluated fixture's own result cannot be part of the number it is
        # scored against. One match in forty barely moves the mean, but "barely"
        # is not a property to rely on when removing it is this cheap.
        rest = {k: v for k, v in matches.items() if k != str(fixture)}
        if len(rest) >= MIN_BASELINE_MATCHES:
            return statistics.fmean(rest.values())
    return entry["mean"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write both config files")
    args = parser.parse_args()

    baselines, baseline_matches = collect_league_baselines()
    if not baselines:
        print(json.dumps({"error": "no dossiers to measure"}), file=sys.stderr)
        return 2
    reliability, priced = measure(baselines, baseline_matches)
    drivers = measure_drivers(baselines, baseline_matches, priced)

    pinned = sum(len(v) for v in baselines.values())
    print(f"league baselines: {len(baselines)} markets, {pinned} (market, competition) pairs")
    print(f"reliability scopes: {len(reliability)}\n")
    print(
        f"{'scope':<28} {'fix':>4} {'actual':>8} {'bias':>7} {'MAE':>6} "
        f"{'skill':>8} {'rungs':>6} {'calib':>7}   {'claims 75%+ -> real':>22}"
    )
    for scope, row in sorted(reliability.items(), key=lambda kv: -kv[1]["skill"]):
        mark = "" if row["skill_comparable"] else " *"
        calib = row.get("calibration_error")  # None when the curve is too thin
        tail = row.get("at_75")
        hot = row.get("hot_above")
        tail_text = (
            f"{tail['claimed']:.3f} -> {tail['realised']:.3f} "
            f"[{tail['gap_ci'][0]:+.3f},{tail['gap_ci'][1]:+.3f}]"
            if tail
            else "-"
        ) + (f"  HOT>={hot:.2f}" if hot else "")
        print(
            f"{scope:<28} {row['fixtures']:>4} {row['actual_mean']:>8.2f} "
            f"{row['bias']:>+7.2f} {row['mae']:>6.2f} "
            f"{row['skill']:>+7.1%}{mark:<2} {row.get('rungs', 0):>6} "
            + (f"{calib:>+7.3f}" if calib is not None else f"{'-':>7}")
            + f"   {tail_text:>22}"
        )
    print("  * skill not comparable: the market happens under 0.5 times a match")
    print("  calib = count-weighted claimed minus realised; positive = overconfident")

    print(
        f"\n{'market':<24} {'driver':<10} {'obs':>5} {'partial r':>10} "
        f"{'95% CI':>18} {'family-wise CI':>18}  status"
    )
    for market, entries in sorted(drivers.items()):
        for driver, row in sorted(entries.items()):
            ci = f"[{row['ci'][0]:+.3f}, {row['ci'][1]:+.3f}]"
            fci = f"[{row['ci_familywise'][0]:+.3f}, {row['ci_familywise'][1]:+.3f}]"
            flag = "" if row["status"] == row["status_at_95"] else "  (95% only)"
            print(
                f"{market:<24} {driver:<10} {row['observations']:>5} "
                f"{row['partial_r']:>+10.3f} {ci:>18} {fci:>18}  "
                f"{row['status']}{flag}"
            )

    if args.write:
        BASELINES_OUT.write_text(
            json.dumps(
                {
                    "_purpose": (
                        "Per-competition mean for each counting market, read by "
                        "analyze.shrunk_centre as the shrinkage target in place of the "
                        "single pooled number in market_priors.json. Rebuild with "
                        "scripts/simple/measure_market_reliability.py --write."
                    ),
                    "_why": (
                        "market_priors.json pins one prior per market for every league "
                        "on earth and says so in its own _venue_limits ('league-blind'). "
                        "Measured over every dossier in runs/, goals_1h_total runs 0.821 "
                        "in the Argentine Liga Profesional (145 matches) against a pinned "
                        "1.243 -- and on 2026-09-07 that gap was the entire edge of the "
                        "day's only bet, which needed 1.688 rather than 1.599 once the "
                        "prior knew the league."
                    ),
                    "_rule": ( f"A competition needs {MIN_BASELINE_MATCHES} independent matches "
                        "before its own mean is used; below that the pooled prior stands. "
                        "Deduplicated by match_id. bzzoiro only, because it is the only "
                        "football provider that stamps a competition id at all."
                    ),
                    "baselines": baselines, }, ensure_ascii=False, indent=1, ) + "\n",
            encoding="utf-8",
        )
        RELIABILITY_OUT.write_text(
            json.dumps(
                {
                    "_purpose": (
                        "How well this pipeline's point forecast has actually done, per "
                        "market, over the settled fixtures in runs/. Read by "
                        "simple_stats/forecast.py so every expectation card carries its "
                        "own measured error instead of an implied precision it has not "
                        "earned. Rebuild with "
                        "scripts/simple/measure_market_reliability.py --write."
                    ),
                    "_reading_it": (
                        "skill = 1 - mae/mae_constant, where mae_constant is the error "
                        "of predicting this scope's own mean. That is the honest "
                        "benchmark: positive skill means the fixture-specific sample "
                        "beat 'just say the average', negative means it lost to it and "
                        "the rungs are separated by a fitted distribution rather than "
                        "by evidence about this fixture. bias is signed forecast minus "
                        "actual, so negative means the forecast runs low. "
                        "skill_vs_shrinkage_target is the same ratio against the "
                        "shrinkage prior instead, kept only because it is what an "
                        "earlier pass reported and it flatters tennis badly -- the "
                        "best-of-five total scores +38.9% against a "
                        "best-of-three-weighted prior of 23.05 and -14.0% against the "
                        "36.03 those fixtures actually average."
                    ),
                    "_the_finding": (
                        "Football counting markets beat the constant and every tennis "
                        "market loses to it. cards_points_total +9.7%, fouls_total "
                        "+8.5% over 580 fixtures, offsides_total +5.0%, down to "
                        "shots_on_target_total at +0.0%; against that games_won@BO5 "
                        "-2.5%, total_sets@BO3 -6.2%, total_games@BO3 -8.8%, "
                        "games_won@BO3 -12.4%, total_sets@BO5 -59.9%. For any tennis "
                        "market this pipeline's best available answer is the format "
                        "average and its own forecast is worse than that answer -- "
                        "which is what the two tennis estimators disagreeing about the "
                        "*sign* of the error was already saying (pooled runs 5.85 games "
                        "low on best-of-five, framed 3.81 high). The one football "
                        "exception is red_cards_total at -47.0%, forecasting 0.35 red "
                        "cards against an actual 0.16 -- and its confident rungs are "
                        "calibrated to within half a point all the same, because they "
                        "are UNDERs on a rare event. Read skill and at_75 as two "
                        "questions; that market is the clearest case for why."
                    ),
                    "_scope_coverage": (
                        "A scope exists here only if ANALYZE emits rows for it. The "
                        "dossier collects far more than the sheet prices -- 1H/2H "
                        "splits for fouls, shots, corners, cards and offsides, plus "
                        "cards_total, retired 2026-09-03 for counting yellows while "
                        "Superbet counts reds -- and an earlier pass measured all of "
                        "them straight off the raw metrics. That is where "
                        "'cards_total +0.8%', 'fouls_2h_total +5.9%' and "
                        "'cards_2h_total +5.9%' came from: markets no row is ever "
                        "built for. They are gone, and the per-participant markets "
                        "they crowded out are here instead."
                    ),
                    "_fidelity": (
                        "The forecast scored here is taken from analyze.analyze_dossier "
                        "and grouped exactly as forecast.build_cards groups it, rather "
                        "than rebuilt. A row-by-row diff against the 2026-09-07 sheet "
                        "caught the earlier replica getting 185 of 2,688 per-side "
                        "centres wrong: it was missing the _one_per_day collapse, "
                        "_adverse_values resolving a provider conflict against the side "
                        "being priced, and _blend_referee. All three are inert for a "
                        "single-provider non-card sample, which is why the replica "
                        "looked right, and all three are active for exactly the markets "
                        "with two providers (goals, corroborated by espn-football; all "
                        "of tennis) or a referee. Each day is replayed against its own "
                        "Superbet ladder, because the offer decides which lines have "
                        "rows at all."
                    ),
                    "_leakage": (
                        "Actuals are a fixture's own result and forecasts come from its "
                        "strictly pre-match dossier, so the only contact is the league "
                        "baseline: a fixture settled in August is an observation in "
                        "September's dossiers. Calling the shipping estimator means the "
                        "baseline is read from config rather than recomputed "
                        "leave-one-out, so the evaluated fixture is inside its own "
                        "target. That was bounded analytically at first and has since "
                        "been measured: rebuild the baselines with a whole date "
                        "removed and score only that date. Over 2026-09-05 and "
                        "2026-09-06, 34 (date, market) pairs, the held-out skill "
                        "differs from the in-sample one by -3.2% to +2.5% with no "
                        "systematic sign -- 16 pairs where holding out helped against "
                        "18 where it hurt, and fouls_total scores *better* held out "
                        "(+11.0% against +8.3%). Those are single-date sampling "
                        "swings on 53-374 observations, not leakage: leakage can only "
                        "flatter, and this does not."
                    ),
                    "_not_measurable": (
                        "aces_total, aces_for, double_faults_total and double_faults_for "
                        "never settle -- ESPN answers statsSource: none for tennis and the "
                        "bzzoiro tennis addon is unpaid. Neither does any player prop: "
                        "runs/_backtest_actuals.json has a total bucket and a bucket per "
                        "side, and no per-player bucket at all, so the ten thousand prop "
                        "rows a slate carries are scored by nothing here. They are "
                        "absent on purpose and an absent scope means never checked, "
                        "never fine."
                    ),
                    "_drivers": (
                        "Per (market, driver) partial correlation with the residual "
                        "the league-aware forecast leaves. PRICES_IN means the sample "
                        "already carries it and an analysis must show the number as "
                        "context without moving the centre or raising confidence for "
                        "it; SHARPENS means it measurably reduces the error and may be "
                        "used as independent evidence. Nothing is SHARPENS. Every "
                        "driver on every market the sheet prices reads PRICES_IN, and "
                        "the interval that decides it is corrected for how many drivers "
                        "are tested at once -- 22 of them, where a per-test 95% "
                        "interval is expected to throw about one spurious result. It "
                        "threw three (goals_total h2h, offsides_total h2h and recency), "
                        "each within 0.011 of containing zero, and none survives the "
                        "family-wise interval. ci is the plain 95% one and "
                        "ci_familywise is the one status is read from. The referee "
                        "blend on card totals is separately measured to correct bias "
                        "(-0.37 to -0.12) while doing nothing for MAE, which is why it "
                        "lives in analyze._blend_referee and not here -- and why the "
                        "referee reading PRICES_IN against cards_points_total is the "
                        "expected result rather than a demotion: that centre already "
                        "has the referee in it, so the residual should have none left."
                    ),
                    "scopes": reliability, "drivers": drivers, }, ensure_ascii=False, indent=1, ) + "\n",
            encoding="utf-8",
        )
        print(f"\nwrote {BASELINES_OUT.relative_to(ROOT)}")
        print(f"wrote {RELIABILITY_OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
