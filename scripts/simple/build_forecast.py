#!/usr/bin/env python3
"""Write one day's expectation cards -- what we think will happen, per market.

    python3 scripts/simple/build_forecast.py --date 2026-09-07

    # only the markets whose error has actually been measured
    python3 scripts/simple/build_forecast.py --date 2026-09-07 --measured-only

Produces ``<date>_forecast.json`` and ``<date>_forecast.md`` beside the day's
other artifacts. This is the read the sheet could never state: the sheet says
``P(over 21.5) = 0.59`` and this says *expect 24.0 fouls, 80% between 16 and
32, off a 24-match sample that beat a league constant by 7% over 568 settled
fixtures, with the referee 2.1 below the pairing and the h2h agreeing.*

**Ordered by confidence, never by price.** The price is a column and the
threshold gap is a column; neither removes a row. A rung a few percent under
its own threshold is still a read the operator may want and the decision is
his. The one thing this file will not do is present a rung whose probability
comes from arithmetic rather than evidence without saying so -- that is what
the grade is for, and ``LEVEL_ONLY`` means the sample did not beat a league
average for that market however confident the number looks.

Exit codes: 0 = written, 2 = missing input.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "src")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from bet.simple_stats.artifact_io import write_json_atomic  # noqa: E402
from bet.simple_stats.contracts import (  # noqa: E402
    EventDossierListV1,
    EventListV1,
    StatsSheetV1,
)
from bet.simple_stats.analyze import MAX_COUNT_MODEL_PROBABILITY  # noqa: E402
from bet.simple_stats.coupons import CERTAINTY_PRICE_FLOOR  # noqa: E402
from bet.simple_stats.forecast import ForecastCard, build_cards  # noqa: E402

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
    """
    worse: dict[str, float] = {}
    hot: dict[str, float] = {}
    for card in cards:
        entry = card.reliability or {}
        if card.grade == "WORSE_THAN_AVERAGE":
            worse[card.market] = float(entry.get("skill") or 0.0)
        elif card.grade == "OVERCONFIDENT" and entry.get("hot_above") is not None:
            hot[card.market] = float(entry["hot_above"])
    parts = []
    if worse:
        listed = ", ".join(
            f"{_label(m)} {_pl(s)}" for m, s in sorted(worse.items(), key=lambda kv: kv[1])
        )
        n_cards = sum(1 for c in cards if c.grade == "WORSE_THAN_AVERAGE")
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
        n_hot = sum(1 for c in cards if c.grade == "OVERCONFIDENT")
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
                "p_low": round(r.p_low, 4) if r.p_low is not None else None,
                "hits": r.hits,
                "sample_size": r.sample_size,
                "superbet_price": r.price,
            }
            for r in card.rungs
        ],
    }


def _render(cards: list[ForecastCard], identities: dict, date: str) -> str:
    """The operator-facing file. Confidence first, price as a column."""
    out: list[str] = []
    out.append(f"# Oczekiwania {date}\n")
    out.append(
        "**Czego się spodziewamy, zanim cokolwiek o cenie.** Każda karta podaje "
        "wartość oczekiwaną w jednostkach, w których rynek się rozlicza, przedział "
        "80%, z czego ten środek się składa, i **zmierzony błąd tego rynku** na "
        "rozegranych już meczach z `runs/`.\n"
    )
    # Both legends below are derived from the day's own cards and the shipped
    # config, never written out by hand. The hand-written version went stale
    # inside a day: it claimed "all 14 such cards today are tennis length
    # markets (BO3 games -9.2%, BO5 games -14.0%, BO5 sets -38.2%)" after the
    # count had become 4 and every one of those three figures had changed.
    out.append(
        "> **Jak czytać ocenę.** Benchmarkiem jest **przewidywanie samej średniej "
        "tego zakresu** — najuczciwsza możliwa stała. `ZMIERZONY` — próbka tego "
        "meczu bije tę średnią, rozdział szczebli opiera się na dowodzie. "
        "`TYLKO POZIOM` — próbka wyszła na remis ze średnią (albo rynek zdarza "
        "się tak rzadko, że jej MAE mierzy częstość bazową, nie umiejętność); "
        "poziom jest coś wart, ale to, co rozdziela sąsiednie szczeble, jest "
        "dopasowanym rozkładem, nie obserwacją. `OBCIĄŻONY` — prognoza myli się "
        "systematycznie w znanym kierunku, popraw ręcznie. **`PRZESADNIE PEWNY`** "
        "— poziom jest w porządku, a pewność nie: wiersze tego rynku, które "
        "deklarowały co najmniej pewien próg, realizowały mniej. **`GORSZY OD "
        "ŚREDNIEJ`** — próbka tego meczu *psuje* odpowiedź: sama średnia formatu "
        "jest bliżej prawdy i żaden szczebel tam nie jest dowodem o tym meczu. "
        "`NIEZMIERZONY` — nikt tego nigdy nie rozliczył; to nie znaczy "
        "„w porządku\".\n"
    )
    out.append(_grade_census(cards))
    out.append(_driver_legend())

    by_event: dict[str, list[ForecastCard]] = {}
    for card in cards:
        by_event.setdefault(card.event_id, []).append(card)

    # --- the day's most informative reads, ranked by confidence alone ---------
    ranked = []
    for card in cards:
        # OVERCONFIDENT is excluded here even though it is a measured grade:
        # this block ranks the day's reads *by confidence*, and the one thing
        # measured about those markets is that their confidence is overstated.
        # red_cards_total would otherwise lead the section on the strength of
        # the best MAE on the board while its 75%+ rows realise 74%.
        if card.grade not in ("MEASURED", "BIASED"):
            continue
        for rung in card.rungs:
            if rung.p_central is None or rung.p_low is None:
                continue
            # A rung sitting *at* the clamp is a ceiling, not a measurement:
            # ``analyze._clamp_count_probability`` caps a count model at
            # MAX_COUNT_MODEL_PROBABILITY, so "goals 2H under 4.5" off a sample
            # that never exceeded two reports exactly that number and says
            # nothing about the match. This filter used to read <= 0.97, which
            # is above the clamp and therefore never fired -- so the section
            # meant to hold the day's most informative reads was 28 rows of
            # saturated arithmetic priced at 1.00-1.05, all tied at the cap.
            # Below 0.55 there is nothing to say either.
            if not 0.55 <= rung.p_central < MAX_COUNT_MODEL_PROBABILITY:
                continue
            ranked.append((rung.p_central, card, rung))
    # Ties broken toward the wider, more informative claim: more evidence
    # first, then the higher line, so a rung at the top of a market's ladder
    # outranks the fourth restatement of the same read one line down.
    ranked.sort(key=lambda item: (-item[0], -item[2].sample_size, -item[2].line))

    def _table(rows: list, limit: int) -> None:
        out.append(
            "| Pewność | Mecz | Rynek | Szczebel | Oczekiwane | Surowo | n | Ocena | Superbet |"
        )
        out.append(
            "|--------:|------|-------|----------|-----------:|-------:|--:|-------|---------:|"
        )
        for p_central, card, rung in rows[:limit]:
            identity = identities.get(card.event_id, {})
            subject = "" if card.subject is None else f" · {card.subject}"
            low, high = card.interval
            price = "—" if rung.price is None else f"{rung.price:.2f}"
            out.append(
                f"| {p_central:.1%} | {identity.get('match', card.event_id[:10])} | "
                f"{_label(card.market)}{subject} | {rung.line} {rung.direction} | "
                f"{card.expected:.2f} ({low:.1f}–{high:.1f}) | "
                f"{rung.hits}/{rung.sample_size} | {rung.sample_size} | "
                f"{_GRADE_PL.get(card.grade, card.grade)} | {price} |"
            )
        out.append("")

    out.append("## Najpewniejsze czytania dnia\n")
    out.append(
        "Sortowane **wyłącznie po pewności modelu**, bez żadnego filtra cenowego. "
        "Kolumna Superbet jest informacją, nie bramką.\n"
    )
    _table(ranked, 12)

    # The same ranking with a price floor, and it is a different list. Ranked on
    # confidence alone the table fills with reads the book has already priced at
    # 1.01-1.07 -- true, and worth nothing to know, because the book knows them
    # too. Measured over the settled history the 1.00-1.05 band realises 97.5%
    # against 98.5% implied, so such a row is a point of EV *behind* its price.
    # The band that pays is 1.35-1.60 at +7.3%, and a confident read that still
    # gets a price is the intersection the operator actually asked for.
    # Priced rows first, then the unpriced ones. An unpriced row belongs here --
    # the book posting no market states no opinion, so nothing has been
    # discounted away -- but it cannot be taken, and sorting it level with a
    # row that can be filled the whole table with dashes.
    paid = sorted(
        (
            item
            for item in ranked
            if item[2].price is None or item[2].price >= CERTAINTY_PRICE_FLOOR
        ),
        key=lambda item: (item[2].price is None, -item[0]),
    )
    if paid:
        out.append(f"### …za które rynek jeszcze płaci (kurs ≥ {CERTAINTY_PRICE_FLOOR:.2f})\n")
        out.append(
            "Ta sama kolejność, jeden filtr: kurs co najmniej "
            f"{CERTAINTY_PRICE_FLOOR:.2f}, albo brak ceny (bukmacher nie wystawił "
            "rynku, więc nie ma swojej opinii). Powyżej pewność jest prawdziwa, "
            "ale w pasmie 1,00–1,05 arkusz realizuje 97,5% przy 98,5% "
            "implikowanych — noga tam kosztuje około punktu EV. Pasmo, które "
            "płaci, to 1,35–1,60: +7,3%.\n"
        )
        _table(paid, 18)

    # --- per fixture ---------------------------------------------------------
    out.append("---\n")
    out.append("## Karty po meczach\n")
    for event_id, event_cards in sorted(
        by_event.items(), key=lambda kv: identities.get(kv[0], {}).get("kickoff") or ""
    ):
        identity = identities.get(event_id, {})
        out.append(
            f"### {identity.get('match', event_id[:12])} — "
            f"{identity.get('competition', '?')} · {identity.get('kickoff', '?')}\n"
        )
        event_cards.sort(
            key=lambda c: (_GRADE_ORDER.get(c.grade, 9), c.market, c.subject or "")
        )
        for card in event_cards:
            low, high = card.interval
            # The subject is inside the bolded market label, so it must not
            # carry its own asterisks -- nested bold renders literally, and
            # every per-participant card printed "**faule drużyny · **Nantes****".
            subject = "" if card.subject is None else f" · {card.subject}"
            out.append(
                f"**{_label(card.market)}{subject}** — oczekiwane **{card.expected:.2f}**, "
                f"80% {low:.1f}–{high:.1f} · {_GRADE_PL.get(card.grade, card.grade)}"
            )
            out.append(f"- _{card.grade_reason}_")
            baseline = (
                f"{card.baseline:.2f}" if card.baseline is not None else "brak"
            )
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
            for driver in card.drivers:
                delta = driver.delta
                arrow = "" if delta is None else ("↑" if delta > 0 else "↓")
                out.append(
                    f"- driver `{driver.name}` = {driver.value:.2f} wobec "
                    f"{driver.reference:.2f} ({delta:+.2f} {arrow}) — "
                    f"**{_STATUS_PL.get(driver.status, driver.status)}**; {driver.detail}"
                )
            if card.scope_excluded:
                dropped = ", ".join(
                    f"{k}: {v}" for k, v in sorted(card.scope_excluded.items())
                )
                out.append(f"- odrzucone z próbki przed liczeniem: {dropped}")
            informative = card.best_rungs(4)
            if informative:
                out.append("")
                out.append("  | szczebel | p_central | p_low | surowo | Superbet |")
                out.append("  |----------|----------:|------:|-------:|---------:|")
                for rung in informative:
                    price = "—" if rung.price is None else f"{rung.price:.2f}"
                    out.append(
                        f"  | {rung.line} {rung.direction} | {rung.p_central:.3f} | "
                        f"{rung.p_low:.3f} | {rung.hits}/{rung.sample_size} | {price} |"
                    )
            out.append("")
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
    parser.add_argument("--include-players", action="store_true")
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
        include_players=args.include_players,
    )
    rendered = [
        c for c in cards
        if not args.measured_only or c.grade in ("MEASURED", "BIASED")
    ]

    payload = {
        "run_id": sheet.run_id,
        "date": args.date,
        "cards": [_card_json(c, identities.get(c.event_id, {})) for c in cards],
        "counts": {
            "cards": len(cards),
            "by_grade": {
                grade: sum(1 for c in cards if c.grade == grade)
                for grade in sorted({c.grade for c in cards})
            },
        },
    }
    json_path = run_dir / f"{args.date}_forecast.json"
    md_path = run_dir / f"{args.date}_forecast.md"
    write_json_atomic(json_path, payload)
    md_path.write_text(_render(rendered, identities, args.date), encoding="utf-8")

    print(
        json.dumps(
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
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
