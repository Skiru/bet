# ruff: noqa: E501 - long markdown / note strings
"""Family table generated from code (pre-registration C2 / C3, r3_final_review.md).

Every football and tennis market key the pipeline can map, price or holds a
curve for, each classified BY MARKET KEY against the code dispatch symbols
(never by a row's notes / forecast_source - C3):

* group  - exam group of rule (c) or ``not_reached``;
* path   - football (i) final-centre multiplier / (ii) pure-rating consumer /
           none; tennis rating / point_model / sample / none;
* reach_note, classified_by.

Read-only: imports bet.sofa, reads config/*.json and the two r1 inventories
(for the comparison only). No DB, no network. Writes family_table.md next to
this file and prints it.

    PYTHONPATH=src:. .venv/bin/python \
        docs/sofa/evidence/kontekst_terminarza_2026-11-08/family_table.py [--date D]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa import (
    epochs,
    player_share,
    players,
    shot_detail,
    tennis_sets,
    tennis_winner,
)
from bet.sofa import football_1x2_dnb as fr1x2
from bet.sofa import football_card_halves as fch
from bet.sofa import football_incidents as finc
from bet.sofa import football_result as fres
from bet.sofa import football_score_markets as fscore
from bet.sofa import market_mapper as mm
from bet.sofa import tennis_rating as tr
from bet.sofa.metrics import CARD_INCIDENT_SCOPES, FOOTBALL_METRICS, TENNIS_METRICS

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
CONFIG = REPO / "config"
OUT = HERE / "family_table.md"

CURVE_FILES = (
    "sofa_confidence_calibration.json",
    "sofa_confidence_calibration.next.json",
    "sofa_confidence_calibration.next.2026-11-07.json",
    "sofa_line_curves.json",
    "sofa_tennis_point_curves.json",
    "sofa_tennis_handicap_point_curves.json",
    "sofa_football_sim_curves.json",
)
# Sections of a curve file whose keys are `[class:]market[@slice]|DIR[@line]`.
CURVE_SECTIONS = (
    "by_market",
    "by_market_direction",
    "thin_by_market_direction",
    "by_market_direction_line",
    "new_market_curves_fitted_from",
)

SIDES = ("Team A", "Team B")

# Exam groups of rule (c) by football metric stem (the metric name with its
# `_for` / `_total` and `_1h` / `_2h` scope removed).
FOOTBALL_STEM_GROUP = {
    "goals": "goals",
    "corners": "corners",
    "shots": "shots_sot",
    "shots_on_target": "shots_sot",
    "cards_points": "cards_fouls",
    "fouls": "cards_fouls",
    "offsides": "offsides",
}


# --------------------------------------------------------------------------
# enumeration
# --------------------------------------------------------------------------


def _derived_keys() -> dict[str, str]:
    """Every key market_mapper's derived / mappable / stat-variant classifiers
    can emit, found by calling the classifiers on each name their own tables
    accept (key -> classifier)."""
    out: dict[str, str] = {}
    names = mm._DERIVED_METRIC_NAMES  # noqa: SLF001 - the classifier's own table

    stat_variant: set[str] = set()

    def add(res: tuple[str, str, float, str] | None, by: str) -> None:
        if res is not None:
            out.setdefault(res[0], by)
            if by == "market_mapper.classify_stat_variant":
                stat_variant.add(res[0])

    cd = mm.classify_derived_market
    for raw in names:
        add(
            cd(f"kazda z druzyn powyzej x {raw}", "tak", "1.5"),
            "market_mapper.classify_derived_market(_BOTH_OVER)",
        )
        add(
            cd(f"najwiecej {raw}", "Team A", None),
            "market_mapper.classify_derived_market(_MOST)",
        )
        add(
            cd(f"liczba {raw} - h2h", "Team A", None),
            "market_mapper.classify_derived_market(_MOST_H2H)",
        )
        add(
            cd(f"liczba {raw} - handicap", "Team A (-1.5)", None),
            "market_mapper.classify_derived_market(_HANDICAP_PATTERNS)",
        )
        for n in ("1", "2"):
            for unit in ("set", "polowa"):
                add(
                    cd(f"{n}. {unit} - najwiecej {raw}", "Team A", None),
                    "market_mapper.classify_derived_market(_MOST_SCOPED)",
                )
    add(
        cd("obie druzyny strzela", "tak", None),
        "market_mapper.classify_derived_market(_BTTS_PLAIN)",
    )
    add(
        cd("rzuty rozne handicap", "Team A (-1.5)", None),
        "market_mapper.classify_derived_market(_HANDICAP_PATTERNS)",
    )
    add(
        cd("handicap gemy", "Team A (-1.5)", None),
        "market_mapper.classify_derived_market(_HANDICAP_PATTERNS)",
    )

    cm = mm.classify_mappable_family
    by = "market_mapper.classify_mappable_family"
    for n in ("1", "2"):
        add(cm(f"{n}.polowa - obie druzyny strzela", "tak", None, SIDES), by)
        add(
            cm(
                f"{n}. polowa - kazda z druzyn powyzej x obronionych strzalow"
                " przez bramkarza",
                "powyzej 1.5 - tak",
                "1.5",
                SIDES,
            ),
            by,
        )
        add(cm(f"{n}. set - handicap gemy", "Team A (-1.5)", f"-1.5-{n}", SIDES), by)
        add(
            cm(f"{n}. polowa - rzuty rozne - handicap", "Team A (-0.5)", "-0.5", SIDES),
            by,
        )
    add(
        cm(
            "kazda z druzyn powyzej x obronionych strzalow przez bramkarza",
            "powyzej 1.5 - tak",
            "1.5",
            SIDES,
        ),
        by,
    )

    cs = mm.classify_stat_variant
    by = "market_mapper.classify_stat_variant"
    for raw in mm._STAT_VARIANT_BOTH_OVER_METRICS:  # noqa: SLF001
        add(cs(f"kazda druzyna powyzej x {raw}", "powyzej 1.5 - tak", "1.5", SIDES), by)
    add(cs("strzaly - handicap", "Team A (-1.5)", "1.5", SIDES), by)
    for n in ("1", "2"):
        add(
            cs(
                f"{n}. polowa - liczba strzalow - handicap",
                "Team A (-1.5)",
                "1.5",
                SIDES,
            ),
            by,
        )
    assert stat_variant == set(mm.STAT_VARIANT_MARKETS), stat_variant ^ set(
        mm.STAT_VARIANT_MARKETS
    )
    return out


def mapped_keys() -> dict[str, str]:
    """key -> the code symbol that maps / defines it as a priced market."""
    keys: dict[str, str] = {}

    def put(ks: Any, by: str) -> None:
        for k in sorted(ks):
            keys.setdefault(k, by)

    put(set(mm.MATCH_MARKET_NAMES.values()), "market_mapper.MATCH_MARKET_NAMES")
    put({m for _, m in mm.TEAM_MARKET_PATTERNS}, "market_mapper.TEAM_MARKET_PATTERNS")
    put(set(mm.PLAYER_MARKET_NAMES.values()), "market_mapper.PLAYER_MARKET_NAMES")
    put(set(mm.PLAYER_PROPS_V2_NAMES.values()), "market_mapper.PLAYER_PROPS_V2_NAMES")
    put(set(shot_detail.MARKET_NAMES.values()), "shot_detail.MARKET_NAMES")
    put({fres.DOUBLE_CHANCE}, "football_result.DOUBLE_CHANCE")
    put(fr1x2.MARKETS, "football_1x2_dnb.MARKETS")
    put(fscore.MARKETS, "football_score_markets.MARKETS")
    put(finc.INCIDENT_MARKETS, "football_incidents.INCIDENT_MARKETS")
    put(fch.MARKETS, "football_card_halves.MARKETS")
    put(epochs.FOOTBALL_SIM_MARKETS, "epochs.FOOTBALL_SIM_MARKETS")
    put(tennis_sets.SET_MARKETS, "tennis_sets.SET_MARKETS")
    put({tennis_winner.MATCH_WON_FOR}, "tennis_winner.MATCH_WON_FOR")
    for k, by in sorted(_derived_keys().items()):
        keys.setdefault(k, by)
    return keys


def _strip_curve_key(raw: str) -> str:
    key = raw.split("|", 1)[0]
    if ":" in key:
        key = key.split(":", 1)[1]
    return key.split("@", 1)[0]


def curve_keys() -> dict[str, set[str]]:
    """market key -> the curve files holding a curve (or fit record) for it."""
    out: dict[str, set[str]] = {}

    def walk(node: Any, fname: str) -> None:
        if not isinstance(node, dict):
            return
        for sec, val in node.items():
            if sec in CURVE_SECTIONS and isinstance(val, dict):
                for raw in val:
                    out.setdefault(_strip_curve_key(raw), set()).add(fname)
            elif sec == "by_class" and isinstance(val, dict):
                for cls in val.values():
                    walk(cls, fname)
            elif sec == "keys" and isinstance(val, list):
                for raw in val:
                    out.setdefault(_strip_curve_key(str(raw)), set()).add(fname)

    for fname in CURVE_FILES:
        path = CONFIG / fname
        if path.exists():
            walk(json.loads(path.read_text()), fname)
    return out


def sport_of(key: str) -> str | None:
    tennis_markets = (
        set(TENNIS_METRICS)
        | tennis_sets.SET_MARKETS
        | epochs.TENNIS_POINT_MODEL_MARKETS
        | epochs.TENNIS_HANDICAP_POINT_MODEL_MARKETS
    )
    football_markets = (
        set(FOOTBALL_METRICS)
        | set(CARD_INCIDENT_SCOPES)
        | set(players.PLAYER_METRICS)
        | {fres.DOUBLE_CHANCE}
        | fr1x2.MARKETS
        | fscore.MARKETS
        | finc.INCIDENT_MARKETS
        | fch.MARKETS
        | epochs.FOOTBALL_SIM_MARKETS
    )
    if key in tennis_markets:
        return "tennis"
    if key in football_markets:
        return "football"
    base = mm.derived_base(key)
    if base is not None:
        side = mm.derived_side_metric(base)
        if side in TENNIS_METRICS:
            return "tennis"
        if side in FOOTBALL_METRICS or side in CARD_INCIDENT_SCOPES:
            return "football"
    return None


# --------------------------------------------------------------------------
# classification (by key against the dispatch symbols - C3)
# --------------------------------------------------------------------------


def _stem(metric: str) -> str:
    m = re.sub(r"_(for|total)$", "", metric)
    return re.sub(r"_[12]h$", "", m)


def _football_group(metric: str) -> str | None:
    return FOOTBALL_STEM_GROUP.get(_stem(metric))


def classify_football(key: str, date: str, at: datetime) -> dict[str, str]:
    floor_dirs = sorted(d for k, d in epochs.FOOTBALL_SIM_FLOOR_KEYS if k == key)
    if key in epochs.FOOTBALL_SIM_MARKETS:
        note = "minute simulator on pure rating goal centres"
        if floor_dirs and epochs.football_sim_floor(date, at):
            note += (
                f"; 0.60 floor key (D13, {'/'.join(floor_dirs)}) - excluded"
                " until floor re-measured"
            )
        return dict(
            group="football_result",
            path="(ii)",
            reach_note=note,
            classified_by="epochs.FOOTBALL_SIM_MARKETS",
        )
    if key == fres.DOUBLE_CHANCE:
        return dict(
            group="football_result",
            path="(ii)",
            reach_note="pure rating NB goals",
            classified_by="football_result.DOUBLE_CHANCE",
        )
    if key in fr1x2.MARKETS:
        return dict(
            group="football_result",
            path="(ii)",
            reach_note="pure rating NB goals",
            classified_by="football_1x2_dnb.MARKETS",
        )
    if key in fscore.MARKETS:
        return dict(
            group="football_result",
            path="(ii)",
            reach_note="pure rating NB goals (slice curves)",
            classified_by="football_score_markets.MARKETS",
        )
    if key == finc.FIRST_GOAL:
        return dict(
            group="football_result",
            path="(ii)",
            reach_note="pure rating NB goals (P(0-0), side share)",
            classified_by="football_incidents.FIRST_GOAL",
        )
    if key in finc.INCIDENT_MARKETS:
        return dict(
            group="not_reached",
            path="none",
            reach_note="league rate (reds/penalties) - not reached, power (M14)",
            classified_by="football_incidents.INCIDENT_MARKETS",
        )
    if key in fch.EVENT_MARKETS and key in fch.TOTAL_MARKETS:
        return dict(
            group="not_reached",
            path="none",
            reach_note="league rate (reds/penalties) - not reached, power (M14)",
            classified_by="football_card_halves.EVENT_MARKETS & TOTAL_MARKETS",
        )
    if key in fch.EVENT_MARKETS:
        return dict(
            group="not_reached",
            path="none",
            reach_note=(
                "league rate x exp(beta*supremacy) (side reds/penalties)"
                " - not reached, power (M14)"
            ),
            classified_by="football_card_halves.EVENT_MARKETS",
        )
    if key in fch.CARD_COUNT_MARKETS:
        return dict(
            group="cards_fouls",
            path="(i)",
            reach_note="as cards_points_for (its live final centre x half share)",
            classified_by="football_card_halves.CARD_COUNT_MARKETS",
        )
    if key in fch.CARD_JOINT_MARKETS:
        return dict(
            group="cards_fouls",
            path="(i)",
            reach_note=f"as {fch.SIDE_METRIC_OF[key]} (two half NBs on cards_points_for)",
            classified_by="football_card_halves.CARD_JOINT_MARKETS",
        )
    if key in shot_detail.METRICS:
        return dict(
            group="not_reached",
            path="none",
            reach_note="shot-detail prop (own starts, position pool) - not reached",
            classified_by="shot_detail.METRICS",
        )
    if key in players.PLAYER_METRICS:
        share_cfg = json.loads((CONFIG / player_share.CONFIG_FILE).read_text())[
            "markets"
        ]
        if key in share_cfg and epochs.FOOTBALL_PLAYER_SHARE_FROM_UTC is not None:
            team = player_share.TEAM_METRIC[key]
            return dict(
                group=_football_group(team) or "not_reached",
                path="(i)",
                reach_note=f"share of {team} final centre (inherits the team term)",
                classified_by="config/sofa_player_share.json markets + player_share.TEAM_METRIC",
            )
        note = "non-share player prop - not reached"
        if key in player_share.TEAM_METRIC:
            note += " (TEAM_METRIC lists it, config has no cell)"
        return dict(
            group="not_reached",
            path="none",
            reach_note=note,
            classified_by="players.PLAYER_METRICS",
        )
    base = mm.derived_base(key)
    if base is not None:
        side = mm.derived_side_metric(base)
        if (
            side in epochs.DERIVED_MARGINAL_CENTRES_METRICS
            and epochs.derived_marginal_centres_enabled(date, at)
        ):
            return dict(
                group=_football_group(side) or "not_reached",
                path="(i)",
                reach_note=f"joint on marginal centres, as {side}",
                classified_by="epochs.DERIVED_MARGINAL_CENTRES_METRICS",
            )
        return dict(
            group="not_reached",
            path="none",
            reach_note=f"raw sample joint ({side}) - not reached",
            classified_by="market_mapper.derived_base + not in DERIVED_MARGINAL_CENTRES_METRICS",
        )
    if key in FOOTBALL_METRICS:
        group = _football_group(key)
        if group is None:
            return dict(
                group="not_reached",
                path="(i)",
                reach_note=(
                    f"team marginal ({_stem(key)}): path (i) would reach it"
                    " mechanically; no exam group in rule (c) - not examined"
                ),
                classified_by="metrics.FOOTBALL_METRICS",
            )
        return dict(
            group=group,
            path="(i)",
            reach_note="team marginal, final centre",
            classified_by="metrics.FOOTBALL_METRICS",
        )
    return dict(group="?", path="?", reach_note="UNCLASSIFIED", classified_by="-")


def classify_tennis(key: str, date: str, at: datetime) -> dict[str, str]:
    point = epochs.tennis_point_markets(date, at)
    floor = ""
    if key in epochs.TENNIS_TOTALS_FLOOR_MARKETS:
        floor = "; 0.60 floor key (D13) - excluded until floor re-measured"
    if key == tennis_winner.MATCH_WON_FOR:
        return dict(
            group="tennis_winner",
            path="rating",
            reach_note="calibrated p_home directly",
            classified_by="tennis_winner.MATCH_WON_FOR",
        )
    if key in point:
        if key in epochs.TENNIS_HANDICAP_POINT_MODEL_MARKETS:
            note = (
                "point model set margin (C3 trap: handicap_games stays on the rating)"
            )
            by = "epochs.tennis_point_markets (TENNIS_HANDICAP_POINT_MODEL_MARKETS)"
        elif key in tr.SET_RATING_PRICED_MARKETS:
            note = (
                "point model replaces the neighbours' p (C3 trap: also in"
                " SET_RATING_PRICED_MARKETS, rows say forecast_source tennis_rating)"
            )
            by = "epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)"
        else:
            note = "point model serve counts"
            by = "epochs.tennis_point_markets (TENNIS_POINT_MODEL_MARKETS)"
        return dict(
            group="tennis_serve", path="point_model", reach_note=note, classified_by=by
        )
    if key in tennis_sets.SET_MARKETS:
        return dict(
            group="tennis_games_sets",
            path="rating",
            reach_note="home player's rating neighbours (set scores)",
            classified_by="tennis_sets.SET_MARKETS",
        )
    if key == "games_total" and key in tr.RATED_MARKETS:
        return dict(
            group="tennis_games_sets",
            path="rating",
            reach_note=(
                f"{tr.W_GAMES_TOTAL_RATING:g} rating neighbours + "
                f"{1 - tr.W_GAMES_TOTAL_RATING:g} sample NB: partly reached"
                " (C14)" + floor
            ),
            classified_by="tennis_rating.RATED_MARKETS + W_GAMES_TOTAL_RATING",
        )
    if key in tr.RATING_PRICED_MARKETS:
        note = "rating neighbours (subject's margin)"
        if key == "handicap_games":
            note += " (C3 trap: not the point model, unlike handicap_games_won_set1/2)"
        if key == "most_games":
            note += "; draw subject stays on the sample"
        return dict(
            group="tennis_games_sets",
            path="rating",
            reach_note=note,
            classified_by="tennis_rating.RATING_PRICED_MARKETS",
        )
    if key in tr.SET_RATING_PRICED_MARKETS:
        return dict(
            group="tennis_games_sets",
            path="rating",
            reach_note="rating neighbours" + floor,
            classified_by="tennis_rating.SET_RATING_PRICED_MARKETS",
        )
    if mm.derived_base(key) is not None:
        return dict(
            group="not_reached",
            path="sample",
            reach_note="raw sample joint - not reached (C14)",
            classified_by="market_mapper.derived_base (tennis, not rating / point model)",
        )
    if key in TENNIS_METRICS:
        return dict(
            group="not_reached",
            path="sample",
            reach_note="players' sample estimator - not reached (C14)",
            classified_by="metrics.TENNIS_METRICS (no rating / point-model symbol)",
        )
    return dict(group="?", path="?", reach_note="UNCLASSIFIED", classified_by="-")


# --------------------------------------------------------------------------
# inventories (comparison only)
# --------------------------------------------------------------------------


def football_inventory() -> set[str]:
    """The 133 keys of r1_football_inventory.md section 5b (one row each)."""
    text = (HERE / "r1_football_inventory.md").read_text()
    sec = text.split("### 5b.", 1)[1].split("\n## ", 1)[0]
    return set(re.findall(r"^\| `([a-z0-9_]+)` \|", sec, flags=re.M))


def tennis_inventory() -> set[str]:
    """The 44 families of r1_tennis_inventory.md section 4 table, its grouped
    rows expanded as that file's sections 1-2 spell them out."""
    text = (HERE / "r1_tennis_inventory.md").read_text()
    sec = text.split("| family | priced rows", 1)[1].split("\n\n", 1)[0]
    out: set[str] = set()
    for first in re.findall(r"^\| ([^|]+?) \|", sec, flags=re.M):
        first = first.strip()
        if first.startswith("serve keys"):
            out |= {
                f"{s}{sc}_{t}"
                for s in ("aces", "double_faults", "serve_points")
                for sc in ("", "_set1", "_set2")
                for t in ("for", "total")
            }
        elif first.startswith("most_aces"):
            # section 1: most_aces(_set1/2), most_double_faults_set1/2,
            # most_serve_points(_set1/2), handicap_aces
            out |= {
                "most_aces",
                "most_aces_set1",
                "most_aces_set2",
                "most_double_faults_set1",
                "most_double_faults_set2",
                "most_serve_points",
                "most_serve_points_set1",
                "most_serve_points_set2",
                "handicap_aces",
            }
        elif first.endswith("set1/2"):
            stem = first[: -len("set1/2")]
            out |= {f"{stem}set1", f"{stem}set2"}
        elif re.fullmatch(r"[a-z0-9_]+", first) and first != "family":
            out.add(first)
    return out


# --------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--date",
        default="2026-11-09",
        help="the day whose switches decide the dispatch (end of day)",
    )
    args = ap.parse_args()
    at = datetime.fromisoformat(args.date).replace(hour=23, minute=59, tzinfo=UTC)

    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", "src/bet/sofa", "config"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    mapped = mapped_keys()
    curves = curve_keys()
    metric_only = {k: "metrics.FOOTBALL_METRICS" for k in FOOTBALL_METRICS}
    metric_only |= {k: "metrics.TENNIS_METRICS" for k in TENNIS_METRICS}
    metric_only |= {k: "metrics.CARD_INCIDENT_SCOPES" for k in CARD_INCIDENT_SCOPES}
    metric_only |= {k: "players.PLAYER_METRICS" for k in players.PLAYER_METRICS}

    universe = set(mapped) | set(metric_only) | set(curves)
    rows: list[dict[str, str]] = []
    unclassified: list[tuple[str, str]] = []
    for key in sorted(universe):
        sport = sport_of(key)
        if sport is None:
            unclassified.append(
                (
                    key,
                    "no sport: not in any football / tennis key symbol"
                    f" (curve files: {', '.join(sorted(curves.get(key, ())))})",
                )
            )
            continue
        cls = (classify_football if sport == "football" else classify_tennis)(
            key, args.date, at
        )
        if cls["group"] == "?":
            unclassified.append((key, "no dispatch symbol matched"))
            continue
        source = mapped.get(key) or metric_only.get(key) or "curve file only"
        latent = ""
        if key not in curves:
            # latent: no own curve - name the sibling whose curve / path it shares
            sib = None
            cands = [
                re.sub(r"_[12]h(_for|_total)$", r"\1", key),
                re.sub(r"_[12]h$", "", key),
            ]
            base = mm.derived_base(key)
            if base is not None:
                cands.append(mm.derived_side_metric(base))
            for c in cands:
                if c != key and c in curves:
                    sib = c
                    break
            latent = (
                f"latent, no own curve: reach = as {sib}"
                if sib
                else "latent, no own curve and no sibling curve (NO_LINE_EVIDENCE until measured)"
            )
        rows.append(
            dict(
                sport=sport,
                key=key,
                mapped="yes" if key in mapped else "no",
                source=source,
                curve="yes" if key in curves else "no",
                latent=latent,
                **cls,
            )
        )
        if key not in mapped:
            rows[-1]["reach_note"] += "; no Superbet name maps to it (never priced)"

    rows.sort(key=lambda r: (r["sport"], r["group"], r["path"], r["key"]))
    counts = Counter((r["sport"], r["group"], r["path"]) for r in rows)
    by_sport = Counter(r["sport"] for r in rows)

    fb_inv, tn_inv = football_inventory(), tennis_inventory()
    fb_code = {
        r["key"] for r in rows if r["sport"] == "football" and r["mapped"] == "yes"
    }
    tn_code = {
        r["key"] for r in rows if r["sport"] == "tennis" and r["mapped"] == "yes"
    }
    all_code = {r["key"] for r in rows}

    lines: list[str] = []
    w = lines.append
    w("# Family table - football and tennis market keys, generated from code")
    w("")
    w(
        f"HEAD `{sha}`{' + uncommitted changes under src/bet/sofa or config' if dirty else ''};"
        f" dispatch as of {args.date} 23:59Z; generator `family_table.py` (this folder)."
        f" Keys: football {by_sport['football']}, tennis {by_sport['tennis']},"
        f" unclassified {len(unclassified)}."
    )
    w("")
    w(
        "Classified by market key against the code dispatch symbols (C3), never by row notes /"
        " `forecast_source`. Football path (i) = final-centre multiplier, (ii) = pure-rating"
        " consumer (`FootballForecast.centre`); tennis rating / point_model / sample."
        " `mapped` = some classifier / module emits the key for a Superbet market;"
        " `curve` = a key in a curve file (`" + "`, `".join(CURVE_FILES) + "`)."
    )
    w("")
    w("## Counts per (sport, group, path)")
    w("")
    w("| sport | group | path | keys |")
    w("|---|---|---|---|")
    for (sp, g, p), n in sorted(counts.items()):
        w(f"| {sp} | {g} | {p} | {n} |")
    w("")
    w("## Keys")
    w("")
    w(
        "| sport | key | group | path | reach_note | classified_by | mapped | curve | source |"
    )
    w("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        note = r["reach_note"] + (f"; {r['latent']}" if r["latent"] else "")
        w(
            f"| {r['sport']} | `{r['key']}` | {r['group']} | {r['path']} | {note} |"
            f" `{r['classified_by']}` | {r['mapped']} | {r['curve']} | `{r['source']}` |"
        )
    w("")
    w("## Not classified from code")
    w("")
    if unclassified:
        for k, why in unclassified:
            w(f"- `{k}`: {why}")
    else:
        w("- none")
    w("")
    w("## Comparison with the r1 inventories")
    w("")
    w(
        f"Football inventory (r1 section 5b): {len(fb_inv)} keys; tennis inventory: {len(tn_inv)}."
    )
    w("")
    w(
        "- in the inventory, not in the code table: "
        + (", ".join(f"`{k}`" for k in sorted((fb_inv | tn_inv) - all_code)) or "none")
    )
    w(
        "- football: mapped in code, absent from r1 section 5b: "
        + (", ".join(f"`{k}`" for k in sorted(fb_code - fb_inv)) or "none")
    )
    w(
        "- tennis: mapped in code, absent from r1 tennis: "
        + (", ".join(f"`{k}`" for k in sorted(tn_code - tn_inv)) or "none")
    )
    w(
        "- in a curve file but not mapped by any classifier: "
        + (
            ", ".join(
                f"`{r['key']}`"
                for r in rows
                if r["mapped"] == "no" and r["curve"] == "yes"
            )
            or "none"
        )
    )
    w("")
    text = "\n".join(lines)
    OUT.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
