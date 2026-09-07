#!/usr/bin/env python3
"""Write one day's expectation cards -- what we think will happen, per market.

    python3 scripts/simple/build_forecast.py --date 2026-09-07

    # only the markets whose error has actually been measured
    python3 scripts/simple/build_forecast.py --date 2026-09-07 --measured-only

    # everything, nothing bounded (4.1 MB on the 37-fixture 2026-09-07 slate;
    # 1.1 MB as shipped)
    python3 scripts/simple/build_forecast.py --date 2026-09-07 \
        --min-probability 0 --min-player-probability 0 \
        --include-ceiling --max-player-cards 9999 --max-ladder 999

Produces ``<date>_forecast.json`` and ``<date>_forecast.md`` beside the day's
other artifacts. This is the read the sheet could never state: the sheet says
``P(over 21.5) = 0.59`` and this says *expect 24.0 fouls, 80% between 16 and
32, off a 24-match sample that beat a league constant by 7% over 568 settled
fixtures, with the referee 2.1 below the pairing and the h2h agreeing.*

**The question this file answers** is the operator's own: which statistic, in
which direction, at which value is most likely. So it is ordered by probability
and **nothing in it is filtered, ordered or vetoed by a price**. The price is a
column carrying its own timestamp, and an appendix at the end; he watches it
change live and this process fetches it once a morning, so it is the one input
here that this file has no business ranking on.

Ordered by ``p_honest``, not ``p_central``: the claim after that market's own
settled calibration curve (see ``bet.simple_stats.calibration``). That is what
makes the ranking possible without a price filter -- rank on the raw claim and
the top fills with saturated arithmetic, which is exactly the pressure that put
a price floor in this file in the first place. Correcting the number instead of
hiding the row means a rung the market has not earned sinks on its own measured
record.

Three bounds keep the rendered file readable, all of them stated in the file
with their counts, none of them a price, and every card is in the JSON
regardless: a probability floor on the two summary tables, a per-fixture cap on
prop cards, and the rule that a card represents itself on its strongest
*informative* rung rather than on the count model's clamp.

Exit codes: 0 = written, 2 = missing input.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "src")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from bet.simple_stats.analyze import MAX_COUNT_MODEL_PROBABILITY  # noqa: E402
from bet.simple_stats.artifact_io import write_json_atomic  # noqa: E402
from bet.simple_stats.contracts import (  # noqa: E402
    EventDossierListV1,
    EventListV1,
    StatsSheetV1,
)
from bet.simple_stats.coupons import CERTAINTY_PRICE_FLOOR  # noqa: E402
from bet.simple_stats.forecast import (  # noqa: E402
    _WORSE_THAN_AVERAGE,
    ForecastCard,
    build_cards,
)

# Markets whose card leads the file. Not a whitelist -- everything is written --
# but the file is long and the reader's attention is the scarce thing, so the
# markets that have earned a positive skill go first.
_GRADE_ORDER = {
    "MEASURED": 0,
    "BIASED": 1,
    "LEVEL_ONLY": 2,
    "UNMEASURED": 3,
    # Last, and below UNMEASURED on purpose: an overconfident market has been
    # checked and found to claim more than it delivers, which is worse to read
    # than a market nobody has checked.
    "OVERCONFIDENT": 4,
    "WORSE_THAN_AVERAGE": 5,
}

_PL = {
    "fouls_total": "faule (mecz)",
    "fouls_1h_total": "faule (1. połowa)",
    "fouls_2h_total": "faule (2. połowa)",
    "corners_total": "rożne (mecz)",
    "cards_points_total": "punkty kartkowe (mecz)",
    "cards_total": "kartki (mecz)",
    "goals_total": "gole (mecz)",
    "goals_1h_total": "gole (1. połowa)",
    "goals_2h_total": "gole (2. połowa)",
    "shots_total": "strzały (mecz)",
    "shots_on_target_total": "strzały celne (mecz)",
    "offsides_total": "spalone (mecz)",
    "red_cards_total": "czerwone kartki (mecz)",
    "total_games": "gemy (mecz)",
    "total_sets": "sety (mecz)",
    "games_won": "gemy zawodnika",
    "aces_total": "asy (mecz)",
    "double_faults_total": "podwójne błędy (mecz)",
    # Per-participant markets. Absent until 2026-09-08, when they stopped
    # being unmeasured and became a large share of the file -- rendering them
    # as raw English identifiers next to Polish labels read as a bug.
    "fouls_for": "faule drużyny",
    "corners_for": "rożne drużyny",
    "cards_points_for": "punkty kartkowe drużyny",
    "goals_for": "gole drużyny",
    "goals_against": "gole stracone drużyny",
    "shots_for": "strzały drużyny",
    "shots_on_target_for": "strzały celne drużyny",
    "offsides_for": "spalone drużyny",
    "aces_for": "asy zawodnika",
    "double_faults_for": "podwójne błędy zawodnika",
    "player_fouls": "faule zawodnika",
    "player_was_fouled": "faule na zawodniku",
    "player_total_shots": "strzały zawodnika",
    "player_shots_on_target": "strzały celne zawodnika",
    "player_tackles": "przechwyty zawodnika",
    "player_offsides": "spalone zawodnika",
    "player_assists": "asysty zawodnika",
    "player_cards": "kartka zawodnika",
}

_GRADE_PL = {
    "MEASURED": "ZMIERZONY",
    "LEVEL_ONLY": "TYLKO POZIOM",
    "BIASED": "OBCIĄŻONY",
    "UNMEASURED": "NIEZMIERZONY",
    "OVERCONFIDENT": "PRZESADNIE PEWNY",
    "WORSE_THAN_AVERAGE": "GORSZY OD ŚREDNIEJ",
}

_STATUS_PL = {
    "PRICES_IN": "już w próbce",
    "SHARPENS": "realny dowód",
    "SHIFTS": "koryguje poziom",
    "UNMEASURED": "niezmierzony",
}


def _plural(count: int, one: str, few: str, many: str) -> str:
    """Polish numeral agreement, which "4 kart na 1 rynkach" does not have."""
    if count == 1:
        return one
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return few
    return many


def _pl(value: float) -> str:
    """A signed percentage with a Polish decimal comma."""
    return f"{value:+.1%}".replace(".", ",")


def _grade_census(cards: list[ForecastCard]) -> str:
    """Which markets earned the two negative grades today, and by how much.

    Derived rather than written: the hand-written version of this paragraph
    named a count and three skill figures, and all four were wrong within a
    day of the measurement being rebuilt.

    Both censuses read the *reliability entry*, not the grade. A card carries
    one grade and a market can fail two independent tests at once, so counting
    by grade made the two sentences mutually exclusive and the losing test went
    unreported. On 2026-09-07 that hid the whole finding: every tennis market
    on the board loses to its own constant, and because ``games_won@BO3`` and
    ``total_games@BO3`` also have hot tails, the paragraph named only the two
    that do not (``sety (mecz)`` at -6.2%) and left out ``gemy zawodnika`` at
    -12.4% -- the worst market of the day. The card counts stay grade-based,
    because a card really does display one grade.
    """
    worse: dict[str, float] = {}
    hot: dict[str, float] = {}
    for card in cards:
        entry = card.reliability or {}
        if not entry:
            continue
        # Keyed by the *market*, which is format-blind, while the reliability
        # entry is per scope -- so on a day carrying both tennis formats two
        # different measurements land on one label. The worse one is kept, the
        # same rule ``forecast._entry_for`` uses when it has to choose between
        # formats: a label must not inherit the kinder of the two readings.
        # Last-write-wins reported ``gemy zawodnika`` at -2.5% (BO5) and hid
        # -12.4% (BO3), which was the worst market on the 2026-09-07 board.
        skill = entry.get("skill")
        if skill is not None and float(skill) <= _WORSE_THAN_AVERAGE:
            worse[card.market] = min(worse.get(card.market, 1.0), float(skill))
        if entry.get("hot_above") is not None:
            hot[card.market] = min(
                hot.get(card.market, 1.0), float(entry["hot_above"])
            )
    parts = []
    if worse:
        listed = ", ".join(
            f"{_label(m)} {_pl(s)}" for m, s in sorted(worse.items(), key=lambda kv: kv[1])
        )
        n_cards = sum(
            1
            for c in cards
            if (c.reliability or {}).get("skill") is not None
            and float((c.reliability or {})["skill"]) <= _WORSE_THAN_AVERAGE
        )
        parts.append(
            f"**GORSZY OD ŚREDNIEJ** dziś: {n_cards} "
            f"{_plural(n_cards, 'karta', 'karty', 'kart')} na {len(worse)} "
            f"{_plural(len(worse), 'rynku', 'rynkach', 'rynkach')} — {listed}."
        )
    if hot:
        listed = ", ".join(
            f"{_label(m)} powyżej {t:.0%}".replace("%", "%")
            for m, t in sorted(hot.items(), key=lambda kv: kv[1])
        )
        n_hot = sum(
            1 for c in cards if (c.reliability or {}).get("hot_above") is not None
        )
        parts.append(
            f"**PRZESADNIE PEWNY**: {n_hot} "
            f"{_plural(n_hot, 'karta', 'karty', 'kart')} — {listed}. Poniżej "
            "tych progów te rynki są skalibrowane."
        )
    return "> " + " ".join(parts) + "\n" if parts else ""


def _driver_legend() -> str:
    """The driver rule, with today's measured numbers for one market.

    ``fouls_total`` because it is the operator's own example ("over 21.5 fauli
    bo sędzia lubi kartki, bo h2h ma dużo fauli, bo ostatnie mecze..."), and
    because all three of those drivers are measured on it.
    """
    from bet.simple_stats.forecast import market_reliability_drivers

    measured = (market_reliability_drivers() or {}).get("fouls_total") or {}
    if not measured:
        return ""
    shown = []
    for name in ("h2h", "recency", "referee"):
        entry = measured.get(name)
        if not entry:
            continue
        low, high = entry["ci_familywise"]
        label = {"h2h": "h2h", "recency": "forma", "referee": "sędzia"}[name]
        shown.append(
            f"{label} {entry['partial_r']:+.3f}".replace(".", ",")
            + f" (CI {low:+.3f}…{high:+.3f})".replace(".", ",")
        )
    tests = next(iter(measured.values())).get("tests_in_family")
    return (
        "> **Dlaczego drivery są opisane, a nie dodane.** Surowo, przeciw "
        "rzeczywistej liczbie fauli, próbka koreluje +0,459, sędzia +0,317, h2h "
        "+0,291, forma +0,329 — cztery powody. Przeciw **resztowi**, którego "
        "prognoza nie wyjaśnia, zostaje: " + ", ".join(shown) + ". To nie są "
        "cztery powody, to cztery opisy jednego faktu, a dodanie ich liczy ten "
        f"fakt cztery razy. Przedziały są poprawione na {tests} testów naraz i "
        "**żaden driver na żadnym rynku ich nie przechodzi** — wszystkie są "
        "`już w próbce`: pokaż liczbę jako zgodność, nie podnoś za nią "
        "pewności.\n"
    )


def _label(market: str) -> str:
    return _PL.get(market, market)


def _card_json(card: ForecastCard, identity: dict) -> dict:
    low, high = card.interval
    return {
        "event_id": card.event_id,
        "match": identity.get("match"),
        "competition": identity.get("competition"),
        "kickoff": identity.get("kickoff"),
        "sport": card.sport,
        "market": card.market,
        "market_label": _label(card.market),
        "subject": card.subject,
        "expected": round(card.expected, 3),
        "interval_80": [round(low, 2), round(high, 2)],
        "spread": round(card.spread, 3),
        "sample": {
            "size": card.sample_size,
            "mean": round(card.sample_mean, 3),
            "median": card.sample_median,
            "min": card.sample_min,
            "max": card.sample_max,
            "weight": round(card.weight, 4),
            "excluded": dict(card.scope_excluded or {}),
        },
        "baseline": {
            "value": round(card.baseline, 3) if card.baseline is not None else None,
            "source": card.baseline_source,
            "weight": round(1.0 - card.weight, 4),
        },
        "grade": card.grade,
        "grade_reason": card.grade_reason,
        "reliability": dict(card.reliability) if card.reliability else None,
        # A third question from the grade: whether the sample counts what the
        # book settles. Null on every market measured centred and on every
        # market never measured -- config/sample_drift.json tells those apart.
        "sample_drift": dict(card.drift) if card.drift else None,
        "sample_drift_note": card.drift_note,
        "centre_note": card.centre_note,
        "drivers": [
            {
                "name": d.name,
                "value": round(d.value, 3) if d.value is not None else None,
                "reference": round(d.reference, 3) if d.reference is not None else None,
                "delta": round(d.delta, 3) if d.delta is not None else None,
                "status": d.status,
                "observations": d.observations,
                "detail": d.detail,
            }
            for d in card.drivers
        ],
        "rungs": [
            {
                "line": r.line,
                "direction": r.direction,
                "p_central": round(r.p_central, 4) if r.p_central is not None else None,
                # The ranked number. Never above p_central; see
                # calibration.honest_probability for why the correction is
                # one-sided.
                "p_honest": round(r.p_honest, 4) if r.p_honest is not None else None,
                "calibration_note": r.honest_note,
                "p_low": round(r.p_low, 4) if r.p_low is not None else None,
                "hits": r.hits,
                "sample_size": r.sample_size,
                "superbet_price": r.price,
            }
            for r in card.ranked_rungs()
        ],
    }


def _coverage_block(coverage: list[dict]) -> str:
    """Every fixture DISCOVER returned, and for any without cards, why.

    The operator's instruction is that every match discovered gets enriched and
    analysed. Three of 37 on 2026-09-07 had no card and the file said nothing --
    all three legitimately (``readiness: BLOCKED``, "kickoff already passed:
    cannot be backed pre-match"), but silence and a correct refusal read the
    same on the page, and only one of them is acceptable. So the count is
    stated and every gap is named with the reason the dossier itself recorded.
    """
    covered = [c for c in coverage if c["cards"]]
    gaps = [c for c in coverage if not c["cards"]]
    out = ["## Zasięg dnia\n"]
    total = len(coverage)
    out.append(
        f"**{len(covered)} z {total}** "
        f"{_plural(total, 'meczu z DISCOVER ma karty', 'meczów z DISCOVER ma karty', 'meczów z DISCOVER ma karty')}"
        f" ({sum(c['cards'] for c in coverage)} kart, "
        f"{sum(c['rungs'] for c in coverage)} szczebli).\n"
    )
    if not gaps:
        out.append("Żaden mecz nie został pominięty.\n")
        return "\n".join(out) + "\n"
    out.append(
        f"Bez kart: **{len(gaps)}**. Każdy z powodem, który zapisał dossier — "
        "jeśli którykolwiek powód nie jest „mecz już się zaczął\", to jest luka "
        "w danych, nie decyzja:\n"
    )
    for gap in gaps:
        reason = "; ".join(gap["gaps"]) or "brak zapisanego powodu"
        out.append(
            f"- **{gap['match']}** ({gap['competition'] or '?'}, "
            f"{gap['kickoff'] or '?'}) — `{gap['readiness'] or 'brak'}`: {reason}"
        )
    out.append("")
    return "\n".join(out) + "\n"


def _exclusions_note(
    team: _Ranked,
    over: _Ranked,
    under: _Ranked,
    floor: float,
    player_floor: float,
    player_sample: int,
    ceiling: bool,
) -> str:
    """Everything the three tables above do not show, and on what grounds.

    Written because the tables *are* a summary and a summary excludes things.
    The operator's objection was never to a shorter list, it was to a shorter
    list that does not say what it dropped -- so every ground is counted here
    and none of them is a price.
    """
    lines = [
        "> **Czego nie ma w tych trzech tabelach.** Tabele pokazują po jednym "
        "wierszu na statystykę i stronę, więc coś muszą pomijać — poniżej "
        "dokładnie co i dlaczego. Żaden z tych powodów nie jest ceną.",
        "",
        f"> * **Poniżej progu:** {team.below_floor} kart drużynowych "
        f"(próg {floor:.0%}), {over.below_floor} propowych POWYŻEJ "
        f"(próg {floor:.0%}) i {under.below_floor} propowych PONIŻEJ "
        f"(próg {max(floor, player_floor):.0%}). Karty drużynowe pod progiem "
        "są w całości w sekcjach meczów niżej — próg dotyczy tylko tabeli. "
        "Karty zawodników pod progiem są **tylko w JSON**: jest ich sześć razy "
        "więcej niż drużynowych i sekcja meczu przestawała być czytelna; każdy "
        "mecz podaje, ile ich pominął.",
    ]
    if player_sample:
        lines.append(
            f"> * **Mała próba:** {over.thin_sample} kart zawodników ma "
            f"n < {player_sample} i nie wchodzi do żadnej z tabel propowych. "
            "Przy n=3 „3/3\" daje wysokie prawdopodobieństwo z arytmetyki, a "
            "nie z wiedzy o zawodniku, i takie wiersze zajmowały górę listy. "
            "Progu nie stawiam na 8 — czyli na to, co kupon nazywa „małą "
            "próbą\" — bo tam strona POWYŻEJ traci dwie trzecie treści: na "
            "planszy 2026-09-07 zostawało 108 wierszy wobec 294 przy n ≥ 5. "
            "A n < 8 i tak jest wypisane przy każdym wierszu kuponu jako "
            "zastrzeżenie, więc jest ostrzeżeniem, nie dyskwalifikacją. "
            "`--min-player-sample 0` wyłącza."
        )
    if not ceiling:
        lines.append(
            "> * **Sufit modelu:** licząc „najmocniejszy szczebel\" pomijam "
            f"szczeble na {MAX_COUNT_MODEL_PROBABILITY:.0%} — tam model się "
            "urywa (`_clamp_count_probability`), więc każda taka linia "
            "raportuje tę samą liczbę i żadna nie mówi, która wartość jest "
            "bardziej prawdopodobna. To fakt o naszej arytmetyce, nie o meczu. "
            f"Skutek: {team.demoted_by_ceiling} kart drużynowych, "
            f"{over.demoted_by_ceiling} propowych POWYŻEJ i "
            f"{under.demoted_by_ceiling} propowych PONIŻEJ weszłoby do tabeli "
            "na szczeblu z sufitu, a wchodzi na swoim najmocniejszym "
            "*informacyjnym* szczeblu albo spada pod próg. Kart bez ani "
            f"jednego szczebla poniżej sufitu: {team.ceiling_only} "
            f"drużynowych, {over.ceiling_only} POWYŻEJ, {under.ceiling_only} "
            "PONIŻEJ. `--include-ceiling` wyłącza tę regułę."
        )
    lines.append("")
    return "\n".join(lines)


def _rank_row(card: ForecastCard, rung, identities: dict) -> str:
    identity = identities.get(card.event_id, {})
    subject = "—" if card.subject is None else card.subject
    low, high = card.interval
    price = "—" if rung.price is None else f"{rung.price:.2f}"
    correction = rung.claim_correction
    shift = "—" if not correction else f"{correction * 100:+.1f}".replace(".", ",")
    return (
        f"| **{rung.p_honest:.1%}** | {rung.p_central:.1%} | {shift} | "
        f"{identity.get('match', card.event_id[:10])} | "
        f"{_label(card.market)} | {subject} | "
        f"**{rung.line:g} {rung.direction}** | "
        f"{card.expected:.2f} ({low:.1f}–{high:.1f}) | "
        f"{rung.hits}/{rung.sample_size} | "
        f"{_GRADE_PL.get(card.grade, card.grade)}{_DRIFT_MARK if card.drift else ''}"
        f" | {price} |"
    )


# The ranked table is the first thing read and its grade column is the only
# quality signal in it, so a market whose sample drifts has to be visible
# *there* and not only on the card further down -- ``cards_points_total`` reads
# ZMIERZONY, the best grade in the file, and the mark is what stops that being
# the whole story. Explained once under the table by ``_drift_legend``.
_DRIFT_MARK = " ⚠"


_RANK_HEADER = (
    "| p (uczciwe) | p (model) | korekta pp | Mecz | Statystyka | Kto | "
    "Kierunek | Oczekiwane (80%) | Surowo | Ocena | Kurs |\n"
    "|------------:|----------:|-----------:|------|------------|-----|"
    "----------|------------------|-------:|-------|-----:|"
)


def _ranked_table(rows: list[tuple], identities: dict) -> list[str]:
    out = [_RANK_HEADER]
    out += [_rank_row(card, rung, identities) for _p, card, rung in rows]
    out.append("")
    # Printed only when a marked row is actually in this table, so the legend
    # cannot outlive the drift it explains.
    if any(card.drift for _p, card, _r in rows):
        out += _drift_legend(
            {card.market: card.drift for _p, card, _r in rows if card.drift}
        )
    return out


def _drift_legend(drifted: dict[str, dict]) -> list[str]:
    """What the ⚠ in the grade column means, per market that carries one."""
    lines = [
        "> ⚠ = próbka tego rynku nie mierzy dokładnie tego, co bukmacher "
        "rozlicza. To **osobne pytanie od oceny** — ocena mówi o "
        "umiejętności i kalibracji, a te rynki wypadają w niej dobrze. "
        "Zmierzone przez `scripts/simple/audit_sample_bias.py`, nigdzie nie "
        "skorygowane (dowód out-of-sample jest wymagany, patrz "
        "`config/sample_drift.json`):"
    ]
    for market in sorted(drifted):
        entry = drifted[market] or {}
        delta = float(entry.get("delta") or 0.0)
        side = str(entry.get("overstated_side") or "")
        lines.append(
            f"> - `{market}` — próbka biegnie "
            f"{abs(delta):.2f} na mecz {'nisko' if delta > 0 else 'wysoko'} "
            f"({int(entry.get('fixtures') or 0)} meczów, "
            f"z={float(entry.get('z') or 0.0):+.2f}); **{side} na tym rynku "
            f"jest zawyżone** o mniej więcej tyle."
        )
    lines.append("")
    return lines


class _Ranked(NamedTuple):
    """A ranked table and the full account of what did not reach it.

    Three numbers rather than one, because the first version reported only
    ``ceiling_only`` -- which is zero on a real board -- while the mechanism
    that actually removed 2,781 prop cards went unmentioned. Excluding a card
    from a summary table is defensible; not saying that you did is the thing
    the operator objected to in the first place.
    """

    rows: list[tuple]
    ceiling_only: int
    below_floor: int
    demoted_by_ceiling: int
    thin_sample: int = 0


def _strongest_per_card(
    cards: list[ForecastCard],
    floor: float,
    *,
    ceiling: bool,
    direction: str | None = None,
    min_sample: int = 0,
) -> _Ranked:
    """One row per statistic, plus the account of every card left out.

    A ladder publishes the same read at a dozen lines, and ranking rungs
    directly fills the table with "under 12.5, under 13.5, under 14.5" off one
    sample. The question is which *statistic* is most likely, so each statistic
    gets one line -- its strongest -- and the rest of its ladder is in the
    fixture's own section below with every value spelled out.

    "Strongest" means strongest **informative** rung unless ``ceiling`` is set.
    The count model clamps at ``MAX_COUNT_MODEL_PROBABILITY``, so a line the
    sample never came near reports exactly that number for every such line and
    none of them says which value is likelier. On the 2026-09-07 board 1,261
    prop cards and 9 team cards would have represented themselves in the table
    on such a rung; every one of them has an informative rung too, so none is
    dropped outright -- they enter on their strongest real reading or fall
    under the floor. That is the difference between a table of 2,000 rows that
    all say 95% and a table of the reads that distinguish anything.

    This is a filter on our own arithmetic and not on anybody's price: the
    rungs stay in the JSON and in the fixture's ladder, all three exclusion
    counts are printed in the file, and ``--include-ceiling`` turns it off.
    """
    out = []
    ceiling_only = below_floor = demoted = thin = 0
    for card in cards:
        if card.sample_size < min_sample:
            thin += 1
            continue
        every = card.ranked_rungs(1, direction=direction)
        ranked = card.ranked_rungs(
            1, informative_only=not ceiling, direction=direction
        )
        if not ranked:
            if every:
                ceiling_only += 1
            continue
        rung = ranked[0]
        if rung.p_honest is None or rung.p_honest < floor:
            below_floor += 1
            # Would this card have cleared the floor on its clamped rung? That
            # is the difference the informative-only rule actually makes, and
            # it is much larger than ceiling_only.
            if every and (every[0].p_honest or 0.0) >= floor:
                demoted += 1
            continue

        out.append((rung.p_honest, card, rung))
    out.sort(key=lambda item: (-item[0], -item[2].sample_size, -item[2].line))
    return _Ranked(out, ceiling_only, below_floor, demoted, thin)


def _render(
    cards: list[ForecastCard],
    identities: dict,
    date: str,
    *,
    coverage: list[dict],
    floor: float,
    offer_generated_at: str | None,
    player_floor: float,
    max_ladder: int,
    ceiling: bool,
    max_player_cards: int,
    player_sample: int,
) -> str:
    """The operator-facing file. Probability first, price a column, no gates.

    Rewritten 2026-09-07 on the operator's instruction, and the instruction was
    a correction of this file's own behaviour. It used to rank the day by
    ``p_central``, drop every card whose grade was not MEASURED or BIASED, drop
    every rung claiming at least the count-model clamp -- which is to say
    exactly the highest probabilities on the board -- cap the result at twelve
    rows and then print a second table gated on ``price >= 1.30``. Per fixture
    it showed ``best_rungs(4)``: the four rungs *nearest even money*, the least
    confident of each ladder.

    So four of the six things this file did were forms of deciding for him, and
    the price -- a number he watches change live and this process reads once a
    morning -- was one of the deciders. Now: nothing is filtered on price,
    nothing is filtered on grade, the ranking is on the corrected probability
    so the saturated rows sink on their own measured record rather than on a
    hand-written rule, and every fixture's whole ladder is printed with its
    values. The price appears twice, both times as information: a column, and
    an appendix at the end carrying its own age.
    """
    out: list[str] = []
    out.append(f"# Oczekiwania {date}\n")
    out.append(
        "**Która statystyka, w którą stronę, przy jakiej wartości jest "
        "najbardziej prawdopodobna.** Nic tutaj nie jest odfiltrowane ceną i "
        "nic nie jest odfiltrowane oceną rynku. Kurs jest kolumną — jest z "
        "jednego pobrania z rana, zmienia się w ciągu dnia i to Ty go widzisz "
        "na żywo, nie ten plik.\n"
    )
    out.append(_coverage_block(coverage))
    out.append(
        "> **Dwie kolumny prawdopodobieństwa.** `p (model)` to liczba, którą "
        "liczy arkusz. `p (uczciwe)` to ta sama liczba **po własnej historii "
        "tego rynku**: dla każdego przedziału deklaracji wiemy z rozliczonych "
        "meczów w `runs/`, ile takie wiersze naprawdę realizowały, i tyle "
        "odejmujemy — przeskalowane liczbą meczów, na których to zmierzono, i "
        "**tylko w dół**. Rynek, który w danym przedziale zaniża, zostaje "
        "nietknięty; podnoszenie liczby na podstawie wahnięcia w kubełku "
        "produkowałoby pewność, której nikt nie zmierzył. Sortowanie idzie po "
        "`p (uczciwe)`, więc wiersze z sufitu arytmetycznego (0,95) spadają "
        "same, jeśli ich rynek na tym poziomie nie dowoził — a nie dlatego, że "
        "ktoś je wykluczył regułą.\n"
    )
    out.append(
        "> **Jak czytać ocenę.** Benchmarkiem jest **przewidywanie samej "
        "średniej tego zakresu** — najuczciwsza możliwa stała. `ZMIERZONY` — "
        "próbka tego meczu bije tę średnią, rozdział szczebli opiera się na "
        "dowodzie. `TYLKO POZIOM` — próbka wyszła na remis ze średnią (albo "
        "rynek zdarza się tak rzadko, że jej MAE mierzy częstość bazową, nie "
        "umiejętność); poziom jest coś wart, ale to, co rozdziela sąsiednie "
        "szczeble, jest dopasowanym rozkładem, nie obserwacją. `OBCIĄŻONY` — "
        "prognoza myli się systematycznie w znanym kierunku, popraw ręcznie. "
        "`PRZESADNIE PEWNY` — poziom jest w porządku, a pewność nie; kolumna "
        "`p (uczciwe)` już to odjęła. **`GORSZY OD ŚREDNIEJ`** — próbka tego "
        "meczu *psuje* odpowiedź: sama średnia formatu jest bliżej prawdy, i "
        "tego kalibracja nie naprawia, bo zły jest poziom, nie pewność. "
        "`NIEZMIERZONY` — nikt tego nigdy nie rozliczył; to nie znaczy "
        "„w porządku\".\n"
    )
    out.append(_grade_census(cards))
    out.append(_driver_legend())

    # Tennis ``aces_for``/``double_faults_for``/``games_won`` are per-player and
    # so carry a subject, but they are not props -- they are the tennis
    # equivalent of a ``*_for`` market and belong with the match markets. The
    # split is on the ``player_`` prefix, which is the football prop namespace,
    # not on whether a subject exists.
    players = [c for c in cards if c.market.startswith("player_")]
    team = [c for c in cards if not c.market.startswith("player_")]

    team_ranked = _strongest_per_card(team, floor, ceiling=ceiling)
    # Props, split by side. The two sides of a prop are not comparable as
    # reads: an UNDER on a count averaging 0.4 is near-certain by arithmetic,
    # so a single ranking is always an UNDER ranking. Measured on the
    # 2026-09-07 board, that ranking was 648 UNDER rows out of 688 and only 14
    # of the 688 carried any price at all -- because **Superbet posts football
    # props OVER-only**: of 4,690 prop rows the stats sheet marked ``OFFERED``
    # on that day, every single one was an OVER. (The paragraph rendered below
    # quotes a smaller number, 3,985, and both are right: that one counts
    # priced rungs on the cards this file actually built, which start at
    # ``min_sample`` and are grouped per subject.)
    #
    # So OVER gets the same floor as the team markets and UNDER keeps the
    # higher prop floor. That asymmetry is the volume argument the prop floor
    # was always built on, and the volume is entirely on the UNDER side: at
    # n>=5 and a 0.70 floor the two sides are 294 rows and 937. It is not a
    # price decision -- the price stays a column on every row of both tables,
    # and both floors and both counts are printed.
    over_ranked = _strongest_per_card(
        players, floor, ceiling=ceiling, direction="OVER", min_sample=player_sample
    )
    under_ranked = _strongest_per_card(
        players,
        max(floor, player_floor),
        ceiling=ceiling,
        direction="UNDER",
        min_sample=player_sample,
    )
    ranked_team = team_ranked.rows
    ranked_over = over_ranked.rows
    ranked_under = under_ranked.rows

    out.append(f"## Największe prawdopodobieństwa dnia (od {floor:.0%})\n")
    out.append(
        "Jeden wiersz na statystykę w meczu — jej najmocniejszy szczebel. "
        "Drabinka publikuje ten sam odczyt przy kilkunastu wartościach, więc "
        "pozostałe wartości są niżej, w sekcji tego meczu, wszystkie. "
        "Sortowane wyłącznie po `p (uczciwe)`, bez limitu wierszy.\n"
    )
    out.append(
        _exclusions_note(
            team_ranked,
            over_ranked,
            under_ranked,
            floor,
            player_floor,
            player_sample,
            ceiling,
        )
    )
    out.append(f"### Rynki meczowe i drużynowe — {len(ranked_team)} pozycji\n")
    out += _ranked_table(ranked_team, identities)
    out.append(
        f"### Rynki zawodników — POWYŻEJ — {len(ranked_over)} pozycji "
        f"(próg {floor:.0%}, n ≥ {player_sample})\n"
    )
    # Derived, never written out. The hand-written version of this sentence
    # carried "4,690" as a literal, which is a figure from one day's offer in a
    # file that is rebuilt every day -- the exact failure this file has already
    # been corrected for twice.
    priced = collections.Counter(
        r.direction
        for c in players
        for r in c.rungs
        if r.price is not None
    )
    out.append(
        "**To jest strona, którą bukmacher wystawia.** Na ofercie z tego dnia "
        f"Superbet wycenił {priced['OVER']} szczebli propowych POWYŻEJ i "
        f"{priced['UNDER']} PONIŻEJ"
        + (
            " — propy piłkarskie są u niego jednostronne."
            if not priced["UNDER"]
            else "."
        )
        + f" Dlatego POWYŻEJ ma tu ten sam próg co rynki drużynowe ({floor:.0%}"
        "), a nie podwyższony: zalew, dla którego ten wyższy próg istnieje, "
        "jest w całości po stronie PONIŻEJ. Kurs nadal jest tylko kolumną.\n"
    )
    out += _ranked_table(ranked_over, identities)
    out.append(
        f"### Rynki zawodników — PONIŻEJ — {len(ranked_under)} pozycji "
        f"(próg {max(floor, player_floor):.0%}, n ≥ {player_sample})\n"
    )
    out.append(
        "Wyższy próg, bo tu jest zalew: PONIŻEJ przy średniej 0,4 fauli jest "
        "niemal pewne z arytmetyki, i póki obie strony szły w jednym "
        "sortowaniu, zajmowało 648 z 688 wierszy tej tabeli (zmierzone na "
        "planszy 2026-09-07 — to fakt o starej wersji tego pliku, nie o dziś). "
        "**Superbet tej strony nie wystawia**, więc kolumna kursu będzie tu "
        "prawie zawsze pusta — to nie znaczy, że odczyt jest zły, tylko że nie "
        "ma go jak obstawić w tym rynku. W JSON są wszystkie, bez progu.\n"
    )
    out += _ranked_table(ranked_under, identities)

    # --- per fixture ---------------------------------------------------------
    out.append("---\n")
    out.append("## Karty po meczach\n")
    out.append(
        "Każdy mecz, każda statystyka, **każda wartość** — pełna drabinka "
        "posortowana po `p (uczciwe)`, żebyś widział nie tylko kierunek, ale "
        "i przy jakiej liczbie się kończy.\n"
    )
    by_event: dict[str, list[ForecastCard]] = {}
    for card in cards:
        by_event.setdefault(card.event_id, []).append(card)
    for event_id, event_cards in sorted(
        by_event.items(), key=lambda kv: identities.get(kv[0], {}).get("kickoff") or ""
    ):
        identity = identities.get(event_id, {})
        out.append(
            f"### {identity.get('match', event_id[:12])} — "
            f"{identity.get('competition', '?')} · {identity.get('kickoff', '?')}\n"
        )
        def _strength(card: ForecastCard) -> float:
            ranked = card.ranked_rungs(1, informative_only=not ceiling)
            return ranked[0].p_honest or 0.0 if ranked else 0.0

        team_cards = [c for c in event_cards if not c.market.startswith("player_")]
        prop_cards = sorted(
            (c for c in event_cards if c.market.startswith("player_")),
            key=lambda c: -_strength(c),
        )
        # Above the floor, then capped per fixture. The cap is what keeps this
        # file readable as the slate grows: props are (players x markets) and
        # team cards are just markets, so on 2026-09-06's 117 fixtures they ran
        # 106 cards a fixture against 20, and that day rendered 6.4 MB before
        # this bound. It is a page-length bound and not a judgement -- the JSON
        # has every one, and the number withheld is printed per fixture.
        eligible = [
            c
            for c in prop_cards
            if c.sample_size >= player_sample and _strength(c) >= player_floor
        ]
        shown = team_cards + eligible[:max_player_cards]
        below = len(prop_cards) - len(eligible)
        capped = len(eligible) - min(len(eligible), max_player_cards)
        if below or capped:
            parts = []
            if below:
                parts.append(f"{below} poniżej progu {player_floor:.0%}")
            if capped:
                parts.append(
                    f"{capped} powyżej progu, ale poza limitem "
                    f"{max_player_cards} na mecz"
                )
            out.append(
                f"_Karty zawodników pominięte tutaj: {', '.join(parts)} — "
                "wszystkie są w pliku JSON._\n"
            )
        # Ranked by what the fixture's own strongest read is, so the operator
        # meets each match at its best statistic rather than in alphabetical
        # order of market name.
        shown.sort(
            key=lambda c: -max(
                (r.p_honest or 0.0) for r in c.rungs
            ) if c.rungs else 0.0
        )
        for card in shown:
            low, high = card.interval
            subject = "" if card.subject is None else f" · {card.subject}"
            out.append(
                f"**{_label(card.market)}{subject}** — oczekiwane "
                f"**{card.expected:.2f}**, 80% {low:.1f}–{high:.1f} · "
                f"{_GRADE_PL.get(card.grade, card.grade)}"
            )
            out.append(f"- _{card.grade_reason}_")
            if card.drift_note:
                # Deliberately its own bullet and not appended to the grade
                # line: the grade can read MEASURED and this can read drifted
                # at the same time, which is exactly the 2026-09-07 case, and
                # one sentence containing both would be read as a contradiction
                # rather than as two answers.
                out.append(f"- **dryf próbki**: _{card.drift_note}_")
            baseline = f"{card.baseline:.2f}" if card.baseline is not None else "brak"
            out.append(
                f"- środek = próbka {card.sample_mean:.2f} (n={card.sample_size}, "
                f"waga {card.weight:.2f}) + baza {baseline} "
                f"(`{card.baseline_source}`, waga {1 - card.weight:.2f})"
                + (
                    f", mediana {card.sample_median:g}, zakres "
                    f"{card.sample_min:g}–{card.sample_max:g}"
                    if card.sample_median is not None and card.sample_min is not None
                    else ""
                )
            )
            if card.centre_note:
                out.append(f"- środek skorygowany: {card.centre_note}")
            note = next(
                (r.honest_note for r in card.ranked_rungs() if r.honest_note), None
            )
            if note:
                out.append(f"- kalibracja: {note}")
            for driver in card.drivers:
                delta = driver.delta
                arrow = "" if delta is None else ("↑" if delta > 0 else "↓")
                out.append(
                    f"- driver `{driver.name}` = {driver.value:.2f} wobec "
                    f"{driver.reference:.2f} ({delta:+.2f} {arrow}) — "
                    f"**{_STATUS_PL.get(driver.status, driver.status)}**; "
                    f"{driver.detail}"
                )
            if card.scope_excluded:
                dropped = ", ".join(
                    f"{k}: {v}" for k, v in sorted(card.scope_excluded.items())
                )
                out.append(f"- odrzucone z próbki przed liczeniem: {dropped}")
            # Capped, and the cap is a page-length decision rather than an
            # editorial one: a ladder is the same read restated at a dozen
            # lines, so the six most likely values carry it and the rest are in
            # the JSON.
            #
            # Worth knowing how little this one does: uncapping it costs 107
            # bytes on the 2026-09-07 board, because the 0.5 floor two lines
            # down has already trimmed most ladders below six rungs. The
            # megabytes on that slate came from the two bounds above -- the
            # ceiling rule and the per-fixture prop cap -- and removing all
            # three takes the file from 1.1 MB to 2.8 MB. This one is here for
            # the pathological ladder, not for the common case.
            ranked = [r for r in card.ranked_rungs() if (r.p_honest or 0.0) >= 0.5]
            ladder = ranked[:max_ladder]
            if ladder:
                out.append("")
                out.append(
                    "  | wartość | kierunek | p (uczciwe) | p (model) | p_low | "
                    "surowo | kurs |"
                )
                out.append(
                    "  |--------:|----------|------------:|----------:|------:|"
                    "-------:|-----:|"
                )
                for rung in ladder:
                    price = "—" if rung.price is None else f"{rung.price:.2f}"
                    p_low = "—" if rung.p_low is None else f"{rung.p_low:.3f}"
                    mark = " *sufit*" if rung.at_ceiling else ""
                    out.append(
                        f"  | {rung.line:g} | {rung.direction} | "
                        f"**{rung.p_honest:.3f}**{mark} | {rung.p_central:.3f} | "
                        f"{p_low} | {rung.hits}/{rung.sample_size} | {price} |"
                    )
                if len(ranked) > len(ladder):
                    out.append("")
                    out.append(
                        f"  _+{len(ranked) - len(ladder)} dalszych wartości "
                        "powyżej 50% — w JSON._"
                    )
            out.append("")

    # --- price, last and clearly labelled as one morning's snapshot ----------
    out.append("---\n")
    out.append("## Dodatek: gdzie rynek jeszcze płacił rano\n")
    stamp = offer_generated_at or "nieznana godzina"
    out.append(
        f"Kursy pobrane **{stamp}**, jedno pobranie. Do dziś wieczora część z "
        "nich nie istnieje. Ta sekcja nie jest rekomendacją i nie usuwa "
        "niczego z tabel powyżej — jest po to, żeby nie szukać ręcznie, które "
        f"z najpewniejszych odczytów miały rano kurs co najmniej "
        f"{CERTAINTY_PRICE_FLOOR:.2f}. Poniżej tego pasma zmierzona historia "
        "mówi, że 1,00–1,05 realizuje 97,5% przy 98,5% implikowanych — noga "
        "tam kosztuje około punktu EV, i to jest fakt o cenie, nie o "
        "statystyce.\n"
    )
    paid = [
        item
        for item in (ranked_team + ranked_over + ranked_under)
        if item[2].price is not None and item[2].price >= CERTAINTY_PRICE_FLOOR
    ]
    paid.sort(key=lambda item: -item[0])
    if paid:
        out += _ranked_table(paid, identities)
    else:
        out.append(
            "Rano żaden z tych odczytów nie miał kursu w tym pasmie.\n"
        )
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--run-dir")
    parser.add_argument(
        "--measured-only",
        action="store_true",
        help="Drop UNMEASURED and LEVEL_ONLY cards from the rendered file",
    )
    parser.add_argument(
        "--no-players",
        action="store_true",
        help="Drop player prop cards entirely (they are included by default)",
    )
    parser.add_argument(
        "--min-probability",
        type=float,
        default=0.70,
        help=(
            "Floor for the ranked tables, on the corrected probability. Not a "
            "quality gate -- every card is in the JSON regardless."
        ),
    )
    parser.add_argument(
        "--min-player-probability",
        type=float,
        default=0.85,
        help=(
            "A higher floor for prop cards in the rendered file only. There are "
            "six times as many of them as team cards and the count must not "
            "decide what reaches the top of the page."
        ),
    )
    parser.add_argument(
        "--min-player-sample",
        type=int,
        default=5,
        help=(
            "Smallest sample a prop card may have to reach the ranked tables. "
            "At n=3 a 3/3 is arithmetic rather than knowledge of the player, "
            "and those rows sorted to the top of the file. Never filters the "
            "JSON."
        ),
    )
    parser.add_argument(
        "--include-ceiling",
        action="store_true",
        help=(
            "Let a card whose whole ladder sits at the count model's clamp "
            "represent its statistic in the ranked tables"
        ),
    )
    parser.add_argument(
        "--max-player-cards",
        type=int,
        default=10,
        help=(
            "How many prop cards each fixture's own section prints, strongest "
            "first. Props are players times markets, so this is what keeps the "
            "file bounded as the slate grows; the JSON is never capped."
        ),
    )
    parser.add_argument(
        "--max-ladder",
        type=int,
        default=6,
        help=(
            "How many values of each ladder the rendered file prints, most "
            "likely first. The JSON always carries every one."
        ),
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir) if args.run_dir else ROOT / "runs" / args.date
    sheet_path = run_dir / f"{args.date}_event_dossiers_stats_sheet.json"
    dossier_path = run_dir / f"{args.date}_event_dossiers.json"
    event_path = run_dir / f"{args.date}_event_list.json"
    for path in (sheet_path, dossier_path, event_path):
        if not path.exists():
            print(json.dumps({"error": f"missing {path}"}), file=sys.stderr)
            return 2

    sheet = StatsSheetV1.model_validate_json(sheet_path.read_text(encoding="utf-8"))
    dossiers = EventDossierListV1.model_validate_json(
        dossier_path.read_text(encoding="utf-8")
    )
    events = EventListV1.model_validate_json(event_path.read_text(encoding="utf-8"))

    identities: dict[str, dict] = {}
    competitions: dict[str, str] = {}
    for event in events.events:
        if event.sport == "tennis":
            match = f"{event.player_one} – {event.player_two}"
        else:
            match = f"{event.home_team} – {event.away_team}"
        identities[event.event_id] = {
            "match": match,
            "competition": event.competition,
            "kickoff": event.start_time,
        }
        if event.competition:
            competitions[event.event_id] = event.competition

    cards = build_cards(
        sheet,
        dossiers.dossiers,
        competitions=competitions,
        include_players=not args.no_players,
    )
    rendered = [
        c for c in cards
        if not args.measured_only or c.grade in ("MEASURED", "BIASED")
    ]

    # Every fixture DISCOVER returned, whether or not it produced a card, with
    # the reason the dossier recorded when it did not. Built here rather than
    # in the renderer because it needs the event list and the dossiers, and the
    # renderer is given cards.
    cards_by_event: dict[str, list[ForecastCard]] = {}
    for card in cards:
        cards_by_event.setdefault(card.event_id, []).append(card)
    dossier_by_event = {d.event_id: d for d in dossiers.dossiers}
    coverage = []
    for event in events.events:
        dossier = dossier_by_event.get(event.event_id)
        own = cards_by_event.get(event.event_id, [])
        identity = identities.get(event.event_id, {})
        coverage.append(
            {
                "event_id": event.event_id,
                "match": identity.get("match"),
                "competition": identity.get("competition"),
                "kickoff": identity.get("kickoff"),
                "sport": event.sport,
                "cards": len(own),
                "rungs": sum(len(c.rungs) for c in own),
                "readiness": getattr(dossier, "readiness", None) if dossier else None,
                "gaps": list(getattr(dossier, "data_gaps", None) or []) if dossier else ["no dossier"],
            }
        )

    offer_path = run_dir / f"{args.date}_superbet_offer.json"
    offer_generated_at = None
    if offer_path.exists():
        try:
            offer_generated_at = json.loads(offer_path.read_text(encoding="utf-8")).get(
                "generated_at"
            )
        except (json.JSONDecodeError, OSError):
            # A price stamp is decoration; a missing one must never stop the
            # statistics from being written.
            offer_generated_at = None

    payload = {
        "run_id": sheet.run_id,
        "date": args.date,
        "cards": [_card_json(c, identities.get(c.event_id, {})) for c in cards],
        "coverage": coverage,
        "offer_generated_at": offer_generated_at,
        "counts": {
            "cards": len(cards),
            "events_discovered": len(events.events),
            "events_with_cards": len(cards_by_event),
            "rungs": sum(len(c.rungs) for c in cards),
            "by_grade": {
                grade: sum(1 for c in cards if c.grade == grade)
                for grade in sorted({c.grade for c in cards})
            },
        },
    }
    json_path = run_dir / f"{args.date}_forecast.json"
    md_path = run_dir / f"{args.date}_forecast.md"
    write_json_atomic(json_path, payload)
    md_path.write_text(
        _render(
            rendered,
            identities,
            args.date,
            coverage=coverage,
            floor=args.min_probability,
            offer_generated_at=offer_generated_at,
            player_floor=args.min_player_probability,
            max_ladder=args.max_ladder,
            ceiling=args.include_ceiling,
            max_player_cards=args.max_player_cards,
            player_sample=args.min_player_sample,
        ),
        encoding="utf-8",
    )

    # Prefixed, because run_pipeline.py runs this as a tail step and its
    # _run_step reads exactly this line to record the step's metrics. Without
    # the prefix the step showed up in the run summary with no numbers at all,
    # which is indistinguishable from a step that did nothing.
    print(
        "AGENT_SUMMARY:"
        + json.dumps(
            {
                "step": "simple_stats:FORECAST",
                "verdict": "OK",
                "metrics": {
                    **payload["counts"],
                    "json": str(json_path),
                    "markdown": str(md_path),
                },
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
