#!/usr/bin/env python3
"""Write one betting day's coupons: singles + Bet Builder slips, ranked.

Usage:
    python3 scripts/simple/build_coupons.py --date 2026-08-29
    python3 scripts/simple/build_coupons.py --stats-sheet PATH --event-list PATH \
        --output runs/2026-08-29/2026-08-29_kupony.md

Reads the finished artifacts, writes `<date>_kupony.md` (the operator's file)
and `<date>_coupons.json` (the machine-readable one). No network, no DB, no
provider calls -- so it is safe to re-run as often as you like.

**Prints no combined price and cannot be made to.** Corners, cards, fouls and
shots in one match are strongly positively correlated, so multiplying the legs
understates the slip's real probability in the direction that flatters the bet.
Read the combined price off Superbet's own screen.

Exit codes: 0 = coupons written, 1 = nothing cleared the bar, 2 = bad input.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from bet.simple_stats.artifact_io import load_market_context, write_json_atomic  # noqa: E402
from bet.simple_stats.contracts import (  # noqa: E402
    EventListV1,
    MarketContextV1,
    StatsSheetV1,
    SuperbetOfferV1,
    TipsterSignalV1,
)
from bet.simple_stats.bet_builder_draft import (  # noqa: E402
    _CORRELATED_FOOTBALL_FAMILY,
    _CORRELATED_TENNIS_FAMILY,
)
from bet.simple_stats.coupons import (  # noqa: E402
    AnalystVeto,
    CouponSet,
    build_coupons,
    market_label,
)
from bet.simple_stats.tipster_claims import TipsterClaimsV1  # noqa: E402
from bet.simple_stats.tipster_consensus import build_consensus  # noqa: E402


def _kickoff(iso: str) -> str:
    return iso[11:16] if len(iso) >= 16 else ""


def agreement_cell(s) -> str:
    """The "Zgodność" cell: the label, and the share behind it.

    ``AGREE`` used to be printed alone and meant anything from 2 corroborated
    matches out of 23 to 23 out of 23. The share is the evidence for the word,
    it is already on the row (``corroborated_matches``), and one column can
    hold both.
    """
    if s.cross_provider_agreement in ("AGREE", "PARTIAL_AGREE") and s.sample_size:
        return f"{s.cross_provider_agreement} {s.corroborated_matches}/{s.sample_size}"
    return s.cross_provider_agreement


def _singles_row(s, *, edge: str | None = None) -> str:
    """One markdown table row for a single. ``edge`` prepends an extra column
    when given, so the two singles sections (Faza 5c) share one row format."""
    subject = f" · {s.subject}" if s.subject else ""
    market = f"{s.market_label} {s.line}{subject}"
    mkt = "—"
    if s.market_verdict and s.market_verdict != "NO_MARKET_DATA":
        verdict = {
            "CONFIRMS": "POTWIERDZA",
            "CONTRADICTS": "PRZECZY",
            "SPLIT": "PODZIELONY",
        }.get(s.market_verdict, s.market_verdict)
        mkt = verdict
        if s.market_price:
            mkt += f" · {s.market_price} @{s.market_bookmaker}"
    edge_cell = f"| {edge} " if edge is not None else ""
    return (
        f"| {s.rank} {edge_cell}| {s.p_low * 100:.1f}% | {s.match} | {market} | {s.direction} "
        f"| {s.hits}/{s.sample_size} | {s.sample_size} | {agreement_cell(s)} "
        f"| {mkt} | {s.tipster or 'brak'} | **{s.min_acceptable_odds:.2f}** "
        f"| {superbet_cell(s)} | {s.tier} |"
    )


# What the operator's own screen says, in one cell. The distinction the cell
# exists to draw is not cheap-versus-dear but **on the screen versus not**:
# "brak linii" and a low price look nothing alike to a human and looked
# identical to this file until 2026-08-31.
_SUPERBET_CELL = {
    "MARKET_NOT_OFFERED": "brak rynku",
    "EVENT_NOT_MATCHED": "brak meczu",
    "SUSPENDED": "zablokowany",
    # The book has the fixture and prices nothing on it -- it kicked off, or the
    # offer was pulled. Rendering the raw enum here read as an error; it is the
    # clock.
    "OFFER_EMPTY": "mecz już trwa",
    # Ours, not the book's: Superbet prices player props, we do not read them.
    "SCOPE_NOT_SUPPORTED": "nie czytamy",
}


def superbet_cell(s) -> str:
    if s.superbet_availability is None:
        return "—"
    if s.superbet_availability == "LINE_NOT_OFFERED":
        if s.superbet_nearest_line is not None:
            return f"brak linii (ma {s.superbet_nearest_line})"
        return "brak linii"
    if s.superbet_availability != "OFFERED":
        return _SUPERBET_CELL.get(s.superbet_availability, s.superbet_availability)
    if s.superbet_price is None:
        return "—"
    if s.superbet_verdict == "VALUE":
        return f"**{s.superbet_price:.2f} ✓**"
    return f"{s.superbet_price:.2f}"


# The gates added on 2026-09-03, with what each one is, in the header's own
# words. Keyed by the reason string ``build_coupons`` counts under.
#
# Printed because a file that is thinner than yesterday's is either a quiet day
# or a new gate, and the operator cannot tell which from a row count. Every one
# of these removes rows that used to reach him.
_NEW_GATE_LABELS: dict[str, str] = {
    "rung_not_chosen": "inny szczebel tej samej drabinki wygrał punktację",
    "builder_score_below_minimum": "kupon BB poniżej progu §44 (0.60)",
    "duplicate_market_for_event": "ten sam rynek tego samego meczu",
    "tier_weak": "tier WEAK (m.in. sufit LEAN → krok w dół)",
    "tier_drop": "tier DROP",
    "analyst_veto": "weto analityka",
    "p_low_below_threshold": "p_low poniżej progu",
    "superbet_not_value": "cena Superbetu poniżej minimum",
    "kickoff_passed": "mecz już się rozpoczął",
    "over_max_singles": "poza limitem singli",
    "competition_youth_or_friendly": "rozgrywki młodzieżowe/towarzyskie",
    "ambiguous_player_name": "dwóch zawodników o tym samym nazwisku",
    "p_low_not_positive": "p_low = 0",
}


def _render_bar_basis(a, coupons: CouponSet) -> None:
    """What the minimum prices in this file were computed from.

    Three numbers decide every ``Min. kurs`` cell -- the basis, the caps on it,
    and the market prior's ``k`` -- and before 2026-09-03 none of them was in
    the file. The same 5/5 sample produces a 1.14 minimum or a 1.95 one
    depending on them, so a reader who cannot see them cannot check a single
    row.
    """
    bases = {s.bar_basis for s in coupons.singles if s.bar_basis}
    if not bases:
        return
    ks = sorted({s.shrink_k for s in coupons.singles if s.shrink_k is not None})
    reasons: dict[str, int] = {}
    for single in coupons.singles:
        if single.bar_basis_reason:
            reasons[single.bar_basis_reason] = reasons.get(single.bar_basis_reason, 0) + 1
    shrunk = sum(1 for s in coupons.singles if s.sample_weight is not None)

    a(
        "**Podstawa progu:** "
        + "/".join(sorted(bases))
        + (f" · k rynkowe: {', '.join(f'{k:g}' for k in ks)}" if ks else "")
        + f" · z priorem rynku: {shrunk}/{len(coupons.singles)}"
    )
    if reasons:
        a(
            "**Ograniczenia podstawy:** "
            + ", ".join(f"{name} ×{count}" for name, count in sorted(reasons.items()))
        )
    a(
        "> `p_shrunk = w·p_bar + (1−w)·p_mkt`, `w = n/(n+k)`. `p_bar` to własne "
        "zdanie próby po dwóch ograniczeniach (Laplace przy zerowym pudle, "
        "`p_low` przy n<8), `p_mkt` to odwigowana cena Superbetu na tym samym "
        "szczeblu. Minimalny kurs = margines tieru / `p_shrunk`."
    )
    a("")
    removed = {
        reason: count
        for reason, count in sorted(coupons.excluded.items())
        if reason in _NEW_GATE_LABELS and count
    }
    if removed:
        a("**Bramki, które usunęły wiersze:**")
        a("")
        for reason, count in removed.items():
            a(f"- `{reason}` ×{count} — {_NEW_GATE_LABELS[reason]}")
        a("")


def _render_funnel(a, funnel: dict) -> None:
    """Offered → in window → resolved → enriched → priced → above bar.

    The one table that says whether a thin file is a thin day or a narrow
    entry to it. Measured on 2026-09-03: Superbet's board carried 4,041 events
    in window, of which 150 were football and 489 tennis; bzzoiro -- the
    provider of record, and the only source of a per-team sample -- carried 29
    football fixtures in the same window. The ceiling is that 29.
    """
    a("**Lej podaży:**")
    a("")
    a("| etap | liczba |")
    a("|------|-------:|")
    for label, value in funnel.items():
        if value is None:
            continue
        a(f"| {label} | {value} |")
    a("")


def _render_alternative_rungs(a, coupons: CouponSet) -> None:
    """The rung the scorer ranked second, per single.

    Printed because the choice between two rungs of one ladder is the part of
    this file an operator is most likely to disagree with, and before 2026-09-03
    he could not see that a choice had been made -- the other rung was counted
    as ``duplicate_market_for_event`` and vanished. On the Grenal that dropped
    ``cards`` 8.5 UNDER (20/20 with the sample's own maximum below the line) in
    favour of 7.5, which sat on the sample's mode.
    """
    rows = [s for s in coupons.singles if s.alternative_line is not None]
    if not rows:
        return
    a("Alternatywny szczebel (drugi w punktacji tej samej drabinki):")
    a("")
    for single in rows:
        price = (
            f"{single.alternative_price:.2f}"
            if single.alternative_price is not None else "brak ceny"
        )
        minimum = (
            f"{single.alternative_min_acceptable_odds:.2f}"
            if single.alternative_min_acceptable_odds is not None else "—"
        )
        a(
            f"- **#{single.rank} {single.match}** — {single.market_label} "
            f"{single.alternative_line} {single.alternative_direction}: "
            f"Superbet {price}, próg {minimum} "
            f"(punktacja {single.alternative_rung_score:+.3f} "
            f"vs {single.rung_score:+.3f} dla wybranego szczebla)"
        )
    a("")


def render_markdown(coupons: CouponSet, funnel: dict | None = None) -> str:
    """The operator's file. Polish, because that is who reads it."""
    out: list[str] = []
    a = out.append

    a(f"# Kupony {coupons.date}")
    a("")
    a(f"**Run:** `{coupons.run_id}` · **Wygenerowano:** {coupons.generated_at[:19]}Z")
    a(
        f"**Podstawa:** {coupons.rows_considered} wierszy / "
        f"{coupons.events_considered} meczów · "
        f"**{len(coupons.singles)} singli**, **{len(coupons.slips)} kuponów BB**"
    )
    a("")
    _render_bar_basis(a, coupons)
    if funnel:
        _render_funnel(a, funnel)
    for note in coupons.notes:
        a(f"> {note}")
        a(">")
    a("")

    # --- singles ---------------------------------------------------------
    # Two axes, and value is the outer one.
    #
    # The market-reference split (docs/PLAN_BOGATE_STATYSTYKI.md Faza 5c) stays:
    # a row ranked against the market's own price is a different claim from one
    # ranked on p_low alone, and printing them in one list would let a boring
    # high-p_low row outrank a real edge just by sorting above it.
    #
    # But neither of those says whether the bet is worth taking, and that is the
    # question the operator actually has. Measured on 2026-09-01: of 5,000
    # eligible rows exactly 10 were priced above their own minimum acceptable
    # odds, and they were ranks 1-10 -- every other single in the list, and
    # every row below it, is offered at a price the pipeline itself says is
    # against the bettor. Printing all fifteen in one table made those five look
    # like the other ten.
    a("## Single")
    a("")

    def _render_singles(rows: list) -> None:
        with_edge = [s for s in rows if s.edge is not None]
        without_edge = [s for s in rows if s.edge is None]
        if with_edge:
            a("**Z odniesieniem do rynku**")
            a("")
            a(
                "| # | Przewaga | Pewność | Mecz | Rynek | Strona | Surowo | n | "
                "Zgodność | Rynek | Typerzy | Min. kurs | Superbet | Tier |"
            )
            a(
                "|--:|--------:|--------:|------|-------|--------|-------:|--:|"
                "----------|-------|---------|----------:|---------|------|"
            )
            for row in with_edge:
                a(_singles_row(row, edge=f"{row.edge * 100:+.1f}pp"))
            a("")
        if without_edge:
            a("**Bez odniesienia do rynku**")
            a("")
            a("| # | Pewność | Mecz | Rynek | Strona | Surowo | n | Zgodność | Rynek | Typerzy | Min. kurs | Superbet | Tier |")
            a("|--:|--------:|------|-------|--------|-------:|--:|----------|-------|---------|----------:|---------|------|")
            for row in without_edge:
                a(_singles_row(row))
            a("")

    worth_it = [s for s in coupons.singles if s.superbet_verdict == "VALUE"]
    below = [s for s in coupons.singles if s.superbet_verdict != "VALUE"]
    if not coupons.singles:
        a("_Żaden wiersz nie przeszedł progu — dzień bez typów singlowych._")
    else:
        a(f"### Warte swojej ceny w Superbecie ({len(worth_it)})")
        a("")
        if not worth_it:
            a(
                "_Żaden typ nie osiąga dziś swojego minimalnego kursu na ekranie "
                "Superbetu. To jest wynik, nie usterka: dzień bez ceny wartej "
                "wzięcia jest dniem bez zakładu._"
            )
            a("")
        else:
            _render_singles(worth_it)

        a(f"### Poniżej progu — cena nie uzasadnia zakładu ({len(below)})")
        a("")
        if not below:
            a("_Każdy typ powyżej osiąga swój minimalny kurs._")
            a("")
        else:
            a(
                "> Te typy przeszły filtry statystyczne, ale Superbet wystawia je "
                "**taniej niż ich minimalny akceptowalny kurs**. Trzymane tu dla "
                "kompletności rozumowania, nie do postawienia po tej cenie. Kurs "
                "się rusza — jeśli podskoczy powyżej progu, typ staje się grywalny."
            )
            a("")
            _render_singles(below)

        _render_alternative_rungs(a, coupons)

        a("Zastrzeżenia do poszczególnych typów:")
        a("")
        for s in coupons.singles:
            if s.caveats:
                a(f"- **#{s.rank} {s.match}** — {'; '.join(s.caveats)}")
        a("")

    # --- slips -----------------------------------------------------------
    a("## Bet Builder")
    a("")
    if not coupons.slips:
        a("_Żaden mecz nie dał dwóch nóg wystarczającej jakości._")
    else:
        for slip in coupons.slips:
            a(
                f"### {slip.rank}. {slip.match} · {slip.competition} · "
                f"{_kickoff(slip.kickoff)} UTC"
            )
            a("")
            a("| Noga | Strona | Pewność | Surowo | Min. kurs | Superbet | Tier |")
            a("|------|--------|--------:|-------:|----------:|---------|------|")
            for leg in slip.draft.legs:
                who = leg.player_name or leg.team_name
                subject = f" · {who}" if who else ""
                # BetBuilderLeg carries hit_rate and sample_size, not hits.
                hits = int(round(leg.hit_rate * leg.sample_size))
                if leg.superbet_availability is None:
                    sb = "—"
                elif leg.superbet_availability == "OFFERED" and leg.superbet_price:
                    sb = f"{leg.superbet_price:.2f}"
                elif leg.superbet_availability == "LINE_NOT_OFFERED":
                    sb = (
                        f"brak linii (ma {leg.superbet_nearest_line})"
                        if leg.superbet_nearest_line is not None
                        else "brak linii"
                    )
                else:
                    sb = _SUPERBET_CELL.get(
                        leg.superbet_availability, leg.superbet_availability
                    )
                a(
                    f"| {market_label(leg.market)} {leg.line}{subject} | {leg.direction} "
                    f"| {leg.p_low * 100:.1f}% | {hits}/{leg.sample_size} "
                    f"| **{leg.min_acceptable_odds:.2f}** | {sb} | {leg.tier} |"
                )
            a("")
            # The contract's own note is English, because bet-analyst reads it.
            # The operator's file says the same thing in the file's language;
            # the risk level itself comes from the contract, never re-derived.
            football = sum(
                1 for leg in slip.draft.legs if leg.market in _CORRELATED_FOOTBALL_FAMILY
            )
            tennis = sum(
                1 for leg in slip.draft.legs if leg.market in _CORRELATED_TENNIS_FAMILY
            )
            if slip.draft.correlation_risk == "HIGH" and tennis >= 2:
                a(
                    f"⚠️ **Korelacja HIGH** — {tennis} z {len(slip.draft.legs)} nóg mierzy "
                    "to samo: jak długo trwa mecz. Sety, gemy, asy i podwójne błędy rosną "
                    "razem, więc krótki mecz rozlicza wszystkie te UNDER-y naraz, a długi "
                    "żaden. Kupon jest przez to **mniej nieprawdopodobny**, niż sugerują "
                    "same nogi — i kurs Superbetu już to uwzględnia. Nigdy nie mnóż nóg."
                )
            elif slip.draft.correlation_risk == "HIGH":
                a(
                    f"⚠️ **Korelacja HIGH** — {football} z {len(slip.draft.legs)} nóg "
                    "pochodzi z tej samej skorelowanej rodziny (rożne / kartki / faule / "
                    "strzały / **gole** w jednym meczu). Mecz faulowy jest meczem "
                    "kartkowym, a mecz otwarty meczem strzelanym, więc te nogi wchodzą "
                    "razem znacznie częściej, niż wynikałoby z niezależności. "
                    "Kupon jest przez to **mniej nieprawdopodobny**, niż sugerują same nogi "
                    "— i kurs Superbetu już to uwzględnia. Nigdy nie mnóż nóg."
                )
            elif slip.draft.correlation_risk == "LOW":
                a(
                    "ℹ️ Nogi spoza jednej skorelowanej rodziny, ale zdarzenia w tym samym "
                    "meczu nigdy nie są w pełni niezależne."
                )
            a("")
            d = slip.draft
            if d.min_acceptable_combined_odds is not None:
                a(
                    f"**Minimalny kurs łączny: {d.min_acceptable_combined_odds:.2f}** "
                    f"— porównaj z kursem Bet Buildera na ekranie Superbetu. "
                    f"Powyżej tej liczby kupon jest wart postawienia, poniżej nie."
                )
                a("")
                a(
                    f"Liczone jako margines / (iloczyn prawdopodobieństw nóg × λ), "
                    f"gdzie λ = **{d.correlation_lambda:.3f}** — zmierzona, nie założona: "
                    f"na 12 555 par nóg z tego samego meczu, rozliczonych na prawdziwych "
                    f"wynikach, nogi wchodzą razem {d.correlation_lambda:.3f}× częściej niż "
                    f"wynikałoby z niezależności. Łączne prawdopodobieństwo kuponu: "
                    f"**{(d.joint_probability or 0) * 100:.1f}%**."
                )
                a("")
            if d.legs_priced_separately is not None:
                a(
                    f"Te same nogi postawione **osobno** dałyby "
                    f"{d.legs_priced_separately:.2f}. To nie jest kurs tego kuponu — to "
                    f"alternatywa, z którą kupon konkuruje. Różnica między tą liczbą a "
                    f"kursem Bet Buildera na ekranie to marża, którą bukmacher bierze za "
                    f"połączenie nóg; przy λ tak bliskim jedności nie ma korelacji, która "
                    f"by ją uzasadniała."
                )
                a("")
            a("**Kurs łączny sam w sobie nie jest tu liczony** — odczytaj go z ekranu.")
            a("")

    _render_tipster_consensus(a, coupons.tipster_consensus)

    a("---")
    a("")
    a("Bez kursu łącznego, bez EV, bez stawki — celowo. Każdy kurs sprawdzasz sam;")
    a("typ poniżej minimalnego kursu nie jest typem.")
    a("")
    return "\n".join(out)


def _render_tipster_consensus(a, consensus) -> None:
    """The appendix: what the crowd repeated, on a market we do not price.

    Last in the file, after the singles and the slips, because it is context
    and not a recommendation -- there is no `p_low` behind any of it and no
    minimum odds, and the text says so twice rather than once.
    """
    if consensus is None:
        return

    a("---")
    a("")
    a("## Zdanie typerów (inny rynek — nie nasze totale)")
    a("")
    a(
        f"> **To nie są typy z tego arkusza.** Typerzy obstawiają 1X2, BTTS i kombinacje; "
        f"ten pipeline wycenia totale (rożne, kartki, faule, strzały, gole). Jednego nie "
        f"przelicza się na drugie, więc **nie ma tu `p_low`, nie ma minimalnego kursu i nie "
        f"ma progu wartości** — jest liczba osób, które postawiły to samo."
    )
    a(">")
    a(
        f"> Pokrycie: **{consensus.picks_ingested} typów** pobranych, "
        f"{consensus.picks_matched} dopasowanych do meczu, "
        f"**{consensus.countable_claims} policzalnych** dla naszych rynków. "
        f"{consensus.events_covered} meczów ruszonych, z tego "
        f"{consensus.events_with_one_pick} przez jedną osobę — dlatego ta sekcja jest krótka."
    )
    if consensus.sources_blocked:
        a(">")
        a(f"> Źródła niedostępne: {', '.join(consensus.sources_blocked)}")
    a("")

    if consensus.rows:
        a(f"### Powtarzające się typy ({len(consensus.rows)})")
        a("")
        a("| Typerów | Mecz | Co obstawiają | Kurs u nich | Na naszym kuponie | Dopasowanie | Kto |")
        a("|---|---|---|---|---|---|---|")
        for row in consensus.rows:
            odds = f"{row.odds_seen:.2f}" if row.odds_seen is not None else "—"
            on = "**tak**" if row.on_coupon else "nie"
            a(
                f"| **{row.tipster_count}×** | {row.match} | {row.direction_label} | "
                f"{odds} | {on} | {row.match_quality or '—'} | "
                f"{', '.join(row.tipsters)} |"
            )
        a("")
        a(
            "*Dopasowanie* `FUZZY` znaczy, że mecz skojarzono po nazwie, nie po id — "
            "sprawdź, czy to ten sam mecz, zanim cokolwiek z tego użyjesz."
        )
        a("")
    else:
        a("### Powtarzające się typy")
        a("")
        a(
            "Brak — żaden mecz nie zebrał dwóch typerów po tej samej stronie. "
            "To normalna odpowiedź o dniu, nie brak danych."
        )
        a("")

    if consensus.coupon_fixtures:
        a(f"### Typerzy o meczach z naszego kuponu ({len(consensus.coupon_fixtures)})")
        a("")
        a(
            "Pojedyncze typy też, bo pytanie jest inne niż wyżej: nie „co się powtarza\", "
            "ale „czy ktokolwiek patrzył na mecz, który zamierzam obstawić\". "
            "Treść typu **dosłownie** — w kombinacjach tylko tam przeżywają poszczególne nogi."
        )
        a("")
        for fixture in consensus.coupon_fixtures:
            a(f"**{fixture.match}** · dopasowanie {fixture.match_quality or '—'}")
            a("")
            for pick in fixture.picks:
                a(f"- {pick}")
            a("")

    if consensus.unusable_by_reason:
        detail = ", ".join(
            f"{count}× {reason}" for reason, count in consensus.unusable_by_reason.items()
        )
        a(
            f"**Nieczytelne dla tej sekcji:** {consensus.unusable_picks} typów — {detail}. "
            "Nie zgaduję ich: „powyżej\" bez linii to nie jest typ, a „Tabilo\" bez "
            "wskazanego zawodnika nie mówi, kto ma wygrać."
        )
        a("")


def _refresh_offer(previous, event_list, path: Path):
    """Re-collect the Superbet board, keeping the previous offer on any failure.

    Refetching and *failing* would be the worst outcome available: the coupon
    would go out with no Superbet column at all because the network blinked,
    which is strictly less information than an offer an hour old. So a failed
    refresh is a note and the old artifact stands.

    Written back to disk deliberately. The next reader of this day -- a
    backtest, a slip audit, an operator asking why a price moved -- must see
    the prices the coupon was built from, not the ones it replaced.
    """
    from bet.simple_stats.superbet_offer import collect_superbet_offer

    try:
        fresh = collect_superbet_offer(event_list)
    except Exception as exc:  # noqa: BLE001 - a dead offer host is not a dead coupon
        print(
            json.dumps({"warning": f"offer refresh failed, keeping {path}: {exc}"}),
            file=sys.stderr,
        )
        return previous
    if not fresh.events:
        print(
            json.dumps({"warning": f"offer refresh returned no events, keeping {path}"}),
            file=sys.stderr,
        )
        return previous
    write_json_atomic(path, fresh.model_dump(mode="json"))
    print(
        json.dumps({
            "offer_refreshed": str(path),
            "events_matched": fresh.events_matched,
            "requests_made": fresh.requests_made,
            "previous_generated_at": previous.generated_at,
            "generated_at": fresh.generated_at,
        }),
        file=sys.stderr,
    )
    return fresh


def _funnel(offer, sheet, coupons) -> dict[str, int | None]:
    """Offered -> in window -> resolved -> enriched -> priced -> above bar.

    Every number comes from an artifact this script already loaded, so it costs
    nothing and cannot drift from the file it is printed in.

    ``w naszych sportach`` needs ``SuperbetOfferV1.unmatched_events``, which
    only exists on offers collected from 2026-09-03. On an older artifact it
    reads None and the row is omitted rather than guessed -- the count is
    there (``events_unmatched``) but the sports filter is not, and reporting a
    board of 3,200 esports rows as "our sports" would make the funnel say the
    opposite of the truth.
    """
    if offer is None:
        return {}
    ours = None
    if offer.unmatched_events:
        ours = len(offer.events) + len(offer.unmatched_events)
    priced = sum(
        1 for row in sheet.rows
        if row.superbet is not None and row.superbet.price is not None
    )
    worth_it = sum(1 for s in coupons.singles if s.superbet_verdict == "VALUE")
    return {
        "na tablicy Superbetu (wszystkie sporty)": offer.events_on_offer,
        "w oknie i w naszych sportach": ours,
        "dopasowane do naszych meczów": offer.events_matched,
        "wzbogacone (mecze z wierszami)": len({row.event_id for row in sheet.rows}),
        "wiersze z ceną na ekranie": priced,
        "single powyżej progu": worth_it,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--date", default=None, help="Betting day; resolves the default paths under runs/<date>/")
    parser.add_argument("--stats-sheet", default=None)
    parser.add_argument("--event-list", default=None)
    parser.add_argument("--output", default=None, help="Markdown path (default: runs/<date>/<date>_kupony.md)")
    parser.add_argument("--max-singles", type=int, default=15)
    parser.add_argument("--max-slips", type=int, default=8)
    parser.add_argument("--max-legs", type=int, default=4)
    parser.add_argument("--min-p-low", type=float, default=None)
    parser.add_argument(
        "--bar",
        choices=("p_central", "p_low"),
        default="p_central",
        help=(
            "Which probability min_acceptable_odds is derived from. Default "
            "p_central (2026-09-03), which measures -0.000 against realised "
            "results over 5,036 settled rows. p_low understates by +16 to "
            "+22pp depending on band, and because the bar is (1/p) x margin "
            "that inflates the demanded price by ~1.39 before the tier margin "
            "-- a gate advertising 10%% of headroom and demanding 50%%. Pass "
            "p_low to reproduce a file built before the switch, or to compare."
        ),
    )
    parser.add_argument(
        "--not-before",
        default=None,
        help="Drop fixtures kicking off at or before this UTC time (ISO, e.g. "
        "2026-08-28T18:00). Default: now. A started match is not a bet.",
    )
    parser.add_argument(
        "--include-started",
        action="store_true",
        help="Keep fixtures that already kicked off. For reviewing a past day, "
        "not for betting one.",
    )
    parser.add_argument(
        "--vetoes",
        default=None,
        help="Path to <date>_analyst_vetoes.json (a JSON array of "
        "{event_id, market, line, direction, action, reason}) written by the "
        "orchestrator from bet-analyst's output. Missing file or empty list is "
        "the default healthy state, not an error.",
    )
    parser.add_argument(
        "--market-context",
        default=None,
        help="Path to <date>_market_context.json from run_market_context.py. "
        "Read for exactly one thing: whether the \"Football Unlimited\" "
        "entitlement was confirmed missing or erroring anywhere in the run "
        "(docs/PLAN_BOGATE_STATYSTYKI.md 3bis.6) -- if so, a warning goes in "
        "the coupon file's header, since a lapsed entitlement removes market "
        "price and model reference from goals/corners at once. Missing file is "
        "the default healthy (unknown) state, not an error.",
    )
    parser.add_argument(
        "--superbet-offer",
        default=None,
        help="Path to <date>_superbet_offer.json from run_superbet.py. Adds the "
        "one column no other source can fill: whether each line is on the "
        "operator's own screen, and at what price. Rows Superbet prices at or "
        "above their minimum acceptable odds are ranked first; rows it does not "
        "carry are kept and labelled, never dropped. Missing file is the "
        "pre-Superbet behaviour exactly, not an error.",
    )
    parser.add_argument(
        "--refresh-offer",
        action="store_true",
        help=(
            "Re-fetch the Superbet board before pricing, and overwrite the "
            "offer artifact with it. About one request per matched fixture "
            "plus one for the board -- roughly 110 on a normal slate, against "
            "no metered quota. Worth it because this file is read minutes "
            "after it is written and the offer behind it can be hours old: on "
            "2026-09-02 a stale offer reported 52 VALUE rows against the 82 "
            "the live board actually had. Off by default so a re-run of a past "
            "day stays reproducible."
        ),
    )
    parser.add_argument(
        "--tipster-signal",
        default=None,
        help="Path to <date>_tipster_signal.json from run_tipsters.py. Adds the "
        "closing appendix: which fixtures two or more tipsters picked the same "
        "way, plus every pick on a fixture that reached this coupon. It is a "
        "different market from the totals priced above -- 1X2, BTTS, combos -- "
        "so it carries no p_low, no minimum odds and no value test, and it "
        "never touches ranking or tiering. Missing file simply omits the "
        "section.",
    )
    parser.add_argument(
        "--tipster-claims",
        default=None,
        help="Path to <date>_tipster_claims.json from save_tipster_claims.py -- "
        "the `tipster-reader` agent's validated readings of the raw pick text. "
        "Where it has a reading, it replaces the regex path, which cannot read "
        "shorthand like `o2,5` or `1(Superzprzewage)`. Counting stays in code "
        "either way. Missing file falls back to the rules exactly.",
    )
    parser.add_argument(
        "--require-superbet-value", action="store_true",
        help="Keep only singles Superbet actually prices at or above their "
        "minimum acceptable odds. Off by default: on a normal day it empties "
        "the file, and an empty file is not the same information as a full one "
        "with every row honestly labelled unbettable.",
    )
    args = parser.parse_args()

    if not args.date and not args.stats_sheet:
        parser.error("give --date, or --stats-sheet explicitly")

    run_dir = ROOT / "runs" / args.date if args.date else None
    sheet_path = Path(args.stats_sheet) if args.stats_sheet else (
        run_dir / f"{args.date}_event_dossiers_stats_sheet.json"
    )
    if not sheet_path.exists():
        print(json.dumps({"error": f"stats sheet not found: {sheet_path}"}), file=sys.stderr)
        sys.exit(2)

    event_list_path = Path(args.event_list) if args.event_list else (
        run_dir / f"{args.date}_event_list.json" if run_dir else None
    )
    event_list = None
    if event_list_path and event_list_path.exists():
        event_list = EventListV1.model_validate_json(event_list_path.read_text(encoding="utf-8"))
    else:
        # Without it every coupon names a hash instead of a fixture. Worth a
        # loud warning rather than a silently uglier file.
        print(
            f"WARNING: no event list at {event_list_path} -- coupons will not name their fixtures",
            file=sys.stderr,
        )

    vetoes_path = Path(args.vetoes) if args.vetoes else (
        run_dir / f"{args.date}_analyst_vetoes.json" if run_dir else None
    )
    vetoes: list[AnalystVeto] = []
    if vetoes_path and vetoes_path.exists():
        raw = json.loads(vetoes_path.read_text(encoding="utf-8"))
        vetoes = [AnalystVeto.model_validate(entry) for entry in raw]

    market_context_path = Path(args.market_context) if args.market_context else (
        run_dir / f"{args.date}_market_context.json" if run_dir else None
    )
    market_context = None
    if market_context_path and market_context_path.exists():
        market_context, dropped_fields = load_market_context(market_context_path)
        if dropped_fields:
            print(
                f"note: {market_context_path.name} carries {len(dropped_fields)} prediction "
                f"field(s) this schema no longer has, ignored: {', '.join(dropped_fields)}",
                file=sys.stderr,
            )

    superbet_path = Path(args.superbet_offer) if args.superbet_offer else (
        run_dir / f"{args.date}_superbet_offer.json" if run_dir else None
    )
    superbet_offer = None
    if superbet_path and superbet_path.exists():
        superbet_offer = SuperbetOfferV1.model_validate_json(
            superbet_path.read_text(encoding="utf-8")
        )
    elif args.superbet_offer:
        # An explicitly named file that is not there is an operator error, not
        # a missing optional input: silently falling back would print a coupon
        # with no Superbet column beside a command that asked for one.
        print(json.dumps({"error": f"superbet offer not found: {superbet_path}"}), file=sys.stderr)
        sys.exit(2)

    if args.refresh_offer:
        if superbet_offer is None:
            parser.error("--refresh-offer needs an offer to refresh; pass --superbet-offer or --date")
        superbet_offer = _refresh_offer(superbet_offer, event_list, superbet_path)

    sheet = StatsSheetV1.model_validate_json(sheet_path.read_text(encoding="utf-8"))
    kwargs = dict(
        max_singles=args.max_singles, max_slips=args.max_slips, max_legs=args.max_legs,
        vetoes=vetoes, market_context=market_context, superbet_offer=superbet_offer,
        require_superbet_value=args.require_superbet_value,
        bar_basis=args.bar,
    )
    if args.min_p_low is not None:
        kwargs["min_p_low"] = args.min_p_low
    if args.include_started:
        if args.not_before:
            parser.error("--include-started and --not-before contradict each other")
        kwargs["not_before"] = None
    elif args.not_before:
        cutoff = datetime.fromisoformat(args.not_before)
        kwargs["not_before"] = (
            cutoff.replace(tzinfo=timezone.utc) if cutoff.tzinfo is None else cutoff
        ).astimezone(timezone.utc)
    else:
        kwargs["not_before"] = datetime.now(timezone.utc)
    coupons = build_coupons(sheet, event_list, **kwargs)
    funnel = _funnel(superbet_offer, sheet, coupons)

    # Attached *after* the build, deliberately. ``build_coupons`` never receives
    # it, so the appendix cannot reach ranking, tiering, the veto index or the
    # value test even by accident -- the boundary is enforced by call order, not
    # only by convention.
    tipster_path = Path(args.tipster_signal) if args.tipster_signal else (
        run_dir / f"{args.date}_tipster_signal.json" if run_dir else None
    )
    claims_path = Path(args.tipster_claims) if args.tipster_claims else (
        run_dir / f"{args.date}_tipster_claims.json" if run_dir else None
    )
    claims = None
    if claims_path and claims_path.exists():
        claims = TipsterClaimsV1.model_validate_json(
            claims_path.read_text(encoding="utf-8")
        )
    elif args.tipster_claims:
        print(
            json.dumps({"error": f"tipster claims not found: {claims_path}"}),
            file=sys.stderr,
        )
        sys.exit(2)

    if tipster_path and tipster_path.exists():
        signal = TipsterSignalV1.model_validate_json(
            tipster_path.read_text(encoding="utf-8")
        )
        coupons = coupons.model_copy(
            update={
                "tipster_consensus": build_consensus(
                    signal,
                    frozenset(
                        [s.event_id for s in coupons.singles]
                        + [s.event_id for s in coupons.slips]
                    ),
                    claims=claims,
                )
            }
        )
    elif args.tipster_signal:
        print(
            json.dumps({"error": f"tipster signal not found: {tipster_path}"}),
            file=sys.stderr,
        )
        sys.exit(2)

    date = coupons.date or args.date or "unknown"
    md_path = Path(args.output) if args.output else (
        (run_dir or Path.cwd()) / f"{date}_kupony.md"
    )
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(coupons, funnel=funnel), encoding="utf-8")
    write_json_atomic(md_path.parent / f"{date}_coupons.json", coupons.model_dump(mode="json"))

    print(
        json.dumps(
            {
                "markdown": str(md_path),
                "json": str(md_path.parent / f"{date}_coupons.json"),
                "singles": len(coupons.singles),
                "slips": len(coupons.slips),
                "rows_considered": coupons.rows_considered,
                "events_considered": coupons.events_considered,
                "not_before": coupons.not_before,
                "excluded": coupons.excluded,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    if not (coupons.singles or coupons.slips) and coupons.excluded.get("kickoff_passed"):
        # Otherwise this reads as "thin day, nothing cleared the bar" when the
        # real answer is "you are building yesterday against today's clock".
        print(
            f"Pusto, bo wszystkie {coupons.excluded['kickoff_passed']} pozycji "
            f"odpadły na filtrze kick-offu (odcięcie {coupons.not_before}). "
            "Do przeglądu dnia, który już się rozegrał, użyj --include-started.",
            file=sys.stderr,
        )
    sys.exit(0 if (coupons.singles or coupons.slips) else 1)


if __name__ == "__main__":
    main()
