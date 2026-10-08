"""Deep per-market audit of one settled day, with the counterfactual.

`audit_settlement.py` answers "how much came in and why not". This one answers
the two questions that come after:

  1. **Per market, what actually happened** — not the win rate, which is
     meaningless on a sheet holding both sides of every rung, but the realised
     value against the line, its sign, and whether the miss was systematic
     (our centre was in the wrong place) or dispersion (our centre was fine
     and the match was not).

  2. **Would the pipeline, as it stands today, still have made this bet?**
     Every gate is a claim that a class of leg loses money. A gate that cannot
     be shown to have removed a real loss is decoration. This replays the
     day's actual coupon through the current gates and reports what each one
     would have caught, what it would have cost, and what it would have missed.

Pure: reads artifacts and the settled table, calls no provider, writes one
markdown file.

    PYTHONPATH=src:. python scripts/sofa/audit_day_deep.py --date 2026-09-19
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pydantic import RootModel  # noqa: E402

from bet.sofa.confidence import (  # noqa: E402
    COUPON_PROFILE,
    MAX_BUILDER_SAMPLE_AGE_DAYS,
    MIN_BUILDER_SAMPLE,
    MIN_ODDS_FOR_CEILING,
    coupon_artifact,
    is_sheet_sport,
    is_stakeable,
    line_is_beyond_sample,
    mode_loses,
    printed_singles,
)
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.contracts import Fixture  # noqa: E402
from bet.sofa.db import get_connection  # noqa: E402
from bet.sofa.settle import line_value  # noqa: E402
from scripts.sofa.run_sheet import determine_side  # noqa: E402


def key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        int(row["sofascore_event_id"]),
        row["market"],
        row.get("subject") or "",
        line_value(row),
        row["direction"],
    )


def table(header: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def pct(a: int, b: int) -> str:
    return f"{100.0 * a / b:.1f}%" if b else "—"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cfg = SofaConfig.from_env()
    run = Path(cfg.runs_dir) / args.date
    # The coupon artifact (11_coupon.json on a stats-only day, K3).
    conf = json.loads(coupon_artifact(run).read_text())
    samples = {s["sofascore_event_id"]: s
               for s in json.loads((run / "03_samples.json").read_text())}
    raw = (run / "02_fixtures.json").read_bytes()
    fx_models = {f.sofascore_event_id: f
                 for f in RootModel[list[Fixture]].model_validate_json(raw).root}

    conn = get_connection(cfg.db_path)
    settled = {key(dict(r)): dict(r) for r in conn.execute(
        "SELECT * FROM sofa_settled_row WHERE run_date = ?", (args.date,))}

    now = datetime.now(UTC)

    def observations(
        eid: int, market: str, subject: str
    ) -> tuple[list[Any], int | None]:
        mv = (samples.get(eid, {}).get("metrics") or {}).get(market)
        if not mv:
            return [], None
        if subject:
            fm = fx_models.get(eid)
            side = determine_side(subject, fm) if fm else None
            obs = list(mv.get(side) or []) if side else []
        else:
            obs, seen = [], set()
            for s in ("side_a", "side_b", "h2h"):
                for o in mv.get(s) or []:
                    if o["sofascore_event_id"] in seen:
                        continue
                    seen.add(o["sofascore_event_id"])
                    obs.append(o)
        vals = [o["value"] for o in obs if o.get("value") is not None]
        dates = [o["match_date_utc"] for o in obs if o.get("value") is not None]
        if not dates:
            return vals, None
        oldest = min(datetime.fromisoformat(d.replace("Z", "+00:00")) for d in dates)
        return vals, (now - oldest).days

    # ---- the day's real coupon: the PDF's builder picks ------------------
    # `is_stakeable` is the one predicate the PDF itself uses. This used to be
    # a fourth, inline copy testing `ev_if_product_priced`, which ignores the
    # measured 12% correlation haircut — so on 2026-09-21 it reported "1 slip,
    # ROI -100.0%" for a builder the PDF had correctly refused to stake
    # (ev_if_product_priced +0.043, ev_after_haircut -0.0821). A deep audit
    # that invents a bet inverts the day it is meant to grade.
    picks = [b for b in conf["builders"] if is_stakeable(b)]
    # And the singles the PDF prints, each a one-leg slip. Until 2026-09-25
    # this audit read builders only, so on a singles-only coupon (09-24: 0
    # builders, 5 singles) it reported "ten dzień nie postawił nic" about a
    # day that staked five bets, and tested no gate on any of them.
    picks += [
        {
            "sofascore_event_id": s_["sofascore_event_id"],
            "match": s_["match"],
            "single": True,
            "legs": [{**s_, "odds": s_["offered_odds"]}],
        }
        # The measured sports' legs on a stats-only coupon are not sheet
        # rows and are graded by coupon_sports (plan F7).
        for s_ in printed_singles(conf) if is_sheet_sport(s_)
    ]
    leg_index = {(conf_leg["sofascore_event_id"], conf_leg["market"],
                  conf_leg["subject"], conf_leg["line"],
                  conf_leg["direction"]): conf_leg for conf_leg in conf["legs"]}

    # Every coupon leg, with its outcome, its evidence, and which of today's
    # gates it would now fail. One row = one staked position.
    k: Any
    positions = []
    for slip_id, b in enumerate(picks):
        for slip_leg in b["legs"]:
            k = (b["sofascore_event_id"], slip_leg["market"], slip_leg["subject"],
                 slip_leg["line"], slip_leg["direction"])
            g = settled.get(k)
            meta = leg_index.get(k, {})
            vals, age = observations(k[0], slip_leg["market"], slip_leg["subject"])
            gates = []
            if not COUPON_PROFILE.clears_price(slip_leg["confidence"],
                                                     slip_leg["odds"]):
                gates.append("NEGATIVE_LEG_EV")
            if slip_leg["odds"] < MIN_ODDS_FOR_CEILING:
                gates.append("ODDS_TOO_LOW")
            if line_is_beyond_sample(slip_leg["line"], slip_leg["direction"], vals):
                gates.append("LINE_BEYOND_SAMPLE")
            if mode_loses(slip_leg["line"], slip_leg["direction"], vals):
                gates.append("MODE_LOSES")
            if len(vals) < MIN_BUILDER_SAMPLE:
                gates.append("THIN_SAMPLE_FOR_BUILDER")
            if age is not None and age > MAX_BUILDER_SAMPLE_AGE_DAYS:
                gates.append("SAMPLE_CROSSES_SEASON")
            positions.append({
                "slip": b["match"] + (" (single)" if b.get("single") else ""),
                "slip_id": slip_id, "eid": b["sofascore_event_id"],
                "market": slip_leg["market"], "subject": slip_leg["subject"],
                "line": slip_leg["line"], "direction": slip_leg["direction"],
                "odds": slip_leg["odds"], "confidence": slip_leg["confidence"],
                "outcome": g["outcome"] if g else None,
                "actual": g["actual_value"] if g else None,
                "sample": sorted(vals), "sample_age": age,
                "market_p": meta.get("market_p"),
                "sample_mean": g["sample_mean"] if g else None,
                "ladder_sigma": g["ladder_sigma"] if g else None,
                "gates": gates,
                "slip_obj": b,
            })

    lines: list[str] = []
    emit = lines.append
    emit(f"# Głęboki audyt typowania — {args.date}")
    emit("")
    emit("Przedmiotem jest **kupon, który naprawdę poszedł**: buildery renderowane "
         "do PDF (`best_for_fixture` i dodatnie EV) oraz single drukowane w PDF — "
         "nie pojedynki VALUE z `06_coupon.json`.")
    emit("")

    # ---- 1. per market, what actually happened --------------------------
    emit("## 1. Każdy rynek na kuponie — wynik faktyczny")
    emit("")
    n_singles = sum(1 for b in picks if b.get("single"))
    graded = [p for p in positions if p["outcome"] in ("WIN", "LOSS")]
    emit(f"{len(picks)} slipów ({len(picks) - n_singles} builderów, {n_singles} "
         f"singli), {len(positions)} nóg, rozliczonych {len(graded)}.")
    emit("")
    if not graded:
        # Sections 1-4 all divide by the settled population. A day on which the
        # PDF staked nothing — 2026-09-22 shipped 0 picks, and 2026-09-21 also
        # staked nothing — used to crash here: first TypeError formatting a None
        # ROI, then ZeroDivisionError on len(graded). The script exits 1 for
        # "findings found", so the crash was indistinguishable from a result.
        # An absence of bets is not a 0% day and must not be rendered as one.
        emit("**Brak rozliczonych nóg — ten dzień nie postawił nic.**")
        emit("")
        emit("To nie jest wynik 0% ani strata. Sekcje 1-4 mierzą populację "
             "rozliczonych pozycji, a ta jest pusta, więc żadnego ROI, żadnej "
             "klasyfikacji przegranych i żadnej kontrfaktycznej oceny bramek nie "
             "da się dla tego dnia policzyć. Bramek nie testowano — dzień bez "
             "zakładu nie jest sprawdzianem dla żadnej z nich.")
        emit("")
        out = (Path(args.out) if args.out
               else Path("reports") / f"sofa_audyt_glaboki_{args.date}.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"WROTE {out}")
        return 0
    by_market = defaultdict(list)
    for p in graded:
        by_market[p["market"]].append(p)
    rows = []
    for m, ps in sorted(by_market.items(), key=lambda kv: -len(kv[1])):
        w = sum(1 for p in ps if p["outcome"] == "WIN")
        # the signed distance from the line, in the direction the bet needed
        margins = [(p["actual"] - p["line"]) if p["direction"] == "OVER"
                   else (p["line"] - p["actual"]) for p in ps]
        centre_err = [p["actual"] - p["sample_mean"] for p in ps
                      if p["sample_mean"] is not None]
        rows.append([
            m, len(ps), w, len(ps) - w, pct(w, len(ps)),
            f"{statistics.median(margins):+g}",
            f"{statistics.mean(centre_err):+.2f}" if centre_err else "—",
        ])
    emit(table(["rynek", "nóg", "weszło", "nie weszło", "% trafień",
                "mediana zapasu do linii", "śr. (wynik − nasz środek)"], rows))
    emit("")
    emit("**Zapas do linii** to odległość wyniku od linii po stronie, której "
         "potrzebowaliśmy: dodatni = weszło i o ile, ujemny = pudło i o ile. "
         "**(wynik − nasz środek)** mierzy, czy środek próbki stał w dobrym "
         "miejscu: systematycznie dodatni znaczy, że zaniżaliśmy ten rynek.")
    emit("")

    # ---- 2. every single position, with its actual value ----------------
    emit("## 2. Pozycja po pozycji — co padło")
    emit("")
    rows = []
    for p in sorted(positions, key=lambda x: (x["outcome"] != "LOSS", x["slip"])):
        subj = f" {p['subject']}" if p["subject"] else ""
        if p["outcome"] is None:
            res, why = "NIEROZLICZONE", "brak statystyk / mecz nie dokończony"
        elif p["outcome"] == "WIN":
            res = "WESZŁO"
            why = f"padło {p['actual']:g}, potrzebne " \
                  f"{'>' if p['direction'] == 'OVER' else '<'} {p['line']:g}"
        else:
            res = "NIE WESZŁO"
            gap = abs(p["actual"] - p["line"])
            why = (f"padło {p['actual']:g}, potrzebne "
                   f"{'>' if p['direction'] == 'OVER' else '<'} {p['line']:g} "
                   f"(brakło {gap:g})")
        rows.append([p["slip"][:34], f"{p['market']}{subj}"[:34],
                     f"{p['direction']} {p['line']:g}", f"{p['odds']:.2f}",
                     f"{p['confidence']:.3f}", res, why])
    emit(table(["mecz", "rynek", "linia", "kurs", "conf", "wynik", "co padło"], rows))
    emit("")

    # ---- 3. why the losses lost -----------------------------------------
    emit("## 3. Dlaczego przegrane przegrały — klasyfikacja")
    emit("")
    losses = [p for p in graded if p["outcome"] == "LOSS"]
    diag = defaultdict(list)
    for p in losses:
        gap = abs(p["actual"] - p["line"])
        sd = statistics.pstdev(p["sample"]) if len(p["sample"]) > 1 else 0.0
        if p["gates"]:
            diag["BRAMKA_ZŁAPAŁABY: " + ", ".join(p["gates"])].append(p)
        elif p["sample"] and (
            p["actual"] > max(p["sample"]) or p["actual"] < min(p["sample"])
        ):
            diag["POZA_CAŁĄ_PRÓBKĄ — wynik spoza historii, jakiej mieliśmy"].append(p)
        elif gap <= 1.0:
            diag["O_WŁOS — pudło o ≤1 jednostkę, w zasięgu szumu"].append(p)
        elif sd and gap > 1.5 * sd:
            diag["ŚRODEK_W_ZŁYM_MIEJSCU — pudło >1.5 sd próbki"].append(p)
        else:
            diag["ZWYKŁA_ZMIENNOŚĆ — w rozrzucie próbki"].append(p)
    rows = [[k, len(v), pct(len(v), len(losses))]
            for k, v in sorted(diag.items(), key=lambda kv: -len(kv[1]))]
    emit(table(["klasa", "pudeł", "udział"], rows))
    emit("")
    for k, v in sorted(diag.items(), key=lambda kv: -len(kv[1])):
        emit(f"**{k}**")
        emit("")
        emit(table(["mecz", "rynek", "linia", "padło", "próbka"],
                   [[p["slip"][:30], f"{p['market']} {p['subject']}".strip()[:30],
                     f"{p['direction']} {p['line']:g}", f"{p['actual']:g}",
                     str(p["sample"])[:52]] for p in v]))
        emit("")

    # ---- 4. the counterfactual ------------------------------------------
    emit("## 4. Kontrfaktyczna: czy dzisiejszy pipeline zagrałby to jeszcze raz?")
    emit("")
    emit("Każda bramka dodana 2026-09-20 jest twierdzeniem, że pewna klasa nóg "
         "traci pieniądze. Poniżej to twierdzenie zderzone z wczorajszym wynikiem.")
    emit("")
    emit("**Miernik.** Pierwsza wersja tego audytu oceniała bramkę odsetkiem pudeł "
         "wśród nóg, które usuwa. To jest zły miernik i dał odwrotną odpowiedź: "
         "bramka na krótkie kursy usuwała nogi, z których 100% weszło, więc "
         "wyglądała na błąd. Zmierzone na 2 492 rozliczonych nogach tego dnia, "
         "nogi poniżej kursu 1,0867 **weszły w 92,5% i zwróciły −3,5%** "
         "(−87,7 jednostki). Noga może wygrywać dziewięć razy na dziesięć i "
         "tracić pieniądze — dlatego bramkę ocenia się **zwrotem**, nie trafieniami.")
    emit("")
    # The coupon is 83 legs; the day's confidence list is 5,334, of which most
    # settled. Judging a gate on the 83 gives it a sample of a dozen or two
    # and a verdict that flips on one result. The same gate evaluated over
    # every settled leg of the day has two orders of magnitude more power, and
    # is the authoritative column below.
    population = []
    for conf_leg in conf["legs"]:
        k = (conf_leg["sofascore_event_id"], conf_leg["market"], conf_leg["subject"],
             conf_leg["line"], conf_leg["direction"])
        g = settled.get(k)
        if not g or g["outcome"] not in ("WIN", "LOSS"):
            continue
        vals, age = observations(k[0], conf_leg["market"], conf_leg["subject"])
        gates = []
        if not COUPON_PROFILE.clears_price(conf_leg["confidence"],
                                                 conf_leg["offered_odds"]):
            gates.append("NEGATIVE_LEG_EV")
        if conf_leg["offered_odds"] < MIN_ODDS_FOR_CEILING:
            gates.append("ODDS_TOO_LOW")
        if line_is_beyond_sample(conf_leg["line"], conf_leg["direction"], vals):
            gates.append("LINE_BEYOND_SAMPLE")
        if mode_loses(conf_leg["line"], conf_leg["direction"], vals):
            gates.append("MODE_LOSES")
        if len(vals) < MIN_BUILDER_SAMPLE:
            gates.append("THIN_SAMPLE_FOR_BUILDER")
        if age is not None and age > MAX_BUILDER_SAMPLE_AGE_DAYS:
            gates.append("SAMPLE_CROSSES_SEASON")
        population.append({"odds": conf_leg["offered_odds"], "outcome": g["outcome"],
                           "gates": gates})

    def roi_of(group: list[dict[str, Any]]) -> tuple[Any, Any, Any]:
        if not group:
            return None, None, None
        ret = sum((x["odds"] - 1.0) if x["outcome"] == "WIN" else -1.0
                  for x in group)
        return len(group), ret, 100.0 * ret / len(group)

    pop_n, pop_ret, pop_roi = roi_of(population)
    if pop_n is None:
        # A day on which nothing settled is a legitimate day — 2026-09-22 shipped
        # a PDF with zero picks. Formatting None here raised TypeError and the
        # script exited 1, which is also its "findings found" code, so a crash
        # was indistinguishable from a result. An absence of bets is not an ROI
        # of zero and must not be printed as one.
        emit("Brak rozliczonych nóg listy pewnościowej dla tego dnia — "
             "**nie ma ROI populacji**. To nie jest wynik 0%, tylko brak zakładów.")
    else:
        emit(f"Kolumna rozstrzygająca to **cały dzień**: {pop_n} rozliczonych nóg "
             f"listy pewnościowej, nie {len(graded)} z kuponu. Punkt odniesienia dla "
             f"całej populacji: **{pop_roi:+.1f}%**.")
    emit("")
    # Minimum n below which this audit refuses to pronounce. Twenty legs of
    # one day flip on a single result; the earlier draft of this table called
    # ODDS_TOO_LOW unjustified off 28 legs that all happened to win, against
    # 2,492 legs of the same class that returned -3.5%.
    min_n_for_verdict = 200
    # And a materiality band. The first version of this column declared
    # LINE_BEYOND_SAMPLE "justified" on -4.3% against a population -4.2% —
    # a tenth of a point, pronounced as a finding. Every class on this day
    # loses about four percent, because that is roughly Superbet's margin on
    # these prices; a gate has to beat that by a visible margin to have
    # separated anything.
    material_pp = 1.5

    rows = []
    for gate in ("NEGATIVE_LEG_EV", "ODDS_TOO_LOW", "LINE_BEYOND_SAMPLE",
                 "MODE_LOSES", "THIN_SAMPLE_FOR_BUILDER", "SAMPLE_CROSSES_SEASON"):
        pn, pret, proi = roi_of([x for x in population if gate in x["gates"]])
        if pn is None:
            verdict, pop_cell = "nie wystąpiła tego dnia", "—"
        elif pn < min_n_for_verdict:
            verdict = f"za mała próbka (n={pn}) — nie rozstrzygam"
            pop_cell = f"{proi:+.1f}% (n={pn})"
        elif proi < pop_roi - material_pp:
            verdict = "uzasadniona — klasa traci istotnie więcej"
            pop_cell = f"**{proi:+.1f}%** (n={pn})"
        elif proi > pop_roi + material_pp:
            verdict = "PRZECIW — klasa radzi sobie istotnie lepiej"
            pop_cell = f"**{proi:+.1f}%** (n={pn})"
        else:
            verdict = (f"nierozstrzygalne — w paśmie ±{material_pp} pkt proc. "
                       "od reszty dnia")
            pop_cell = f"{proi:+.1f}% (n={pn})"
        caught = [p for p in graded if gate in p["gates"]]
        if not caught:
            rows.append([gate, 0, "—", pop_cell, verdict])
            continue
        _, ret, roi = roi_of(caught)
        rows.append([gate, len(caught), f"{roi:+.1f}%", pop_cell, verdict])
    emit(table(["bramka", "nóg z kuponu", "ich ROI (n mały!)",
                "ROI klasy na całym dniu", "ocena"], rows))
    emit("")
    base_ret = sum((p["odds"] - 1.0) if p["outcome"] == "WIN" else -1.0
                   for p in graded)
    emit(f"Punkt odniesienia — wszystkie {len(graded)} nóg kuponu stawiane "
         f"pojedynczo: **{base_ret:+.2f} j., "
         f"{100.0 * base_ret / len(graded):+.1f}%**.")
    emit("")
    emit("### Co z tej tabeli faktycznie wynika")
    emit("")
    emit(f"Każda klasa nóg tego dnia traci około {abs(pop_roi):.0f}% na "
         "pojedynczych zakładach, bo tyle mniej więcej wynosi marża Superbeta na "
         "tych cenach. **Żadna bramka nie separuje klasy istotnie gorszej od "
         "reszty** — co znaczy, że ROI pojedynczej nogi jest złym testem dla "
         "bramki, która dotyczy nóg **mnożonych**.")
    emit("")
    emit("Argument za tymi bramkami jest arytmetyczny, nie empiryczny, i jeden "
         "dzień go nie rozstrzygnie. Noga o pewności 0,92 i kursie 1,06 mnoży "
         "prawdopodobieństwo slipa przez 0,92, a jego kurs tylko przez 1,06: "
         "iloczyn 0,975, więc obniża EV slipa **niezależnie od tego, czy tego "
         "dnia weszła**. Wczoraj weszła 36 razy na 36 i to nie jest kontrargument "
         "— to jest dokładnie to, jak wygląda noga 92-procentowa na próbce 36.")
    emit("")
    emit("Uczciwe podsumowanie: `LINE_BEYOND_SAMPLE` i `THIN_SAMPLE_FOR_BUILDER` "
         "mają słabe wsparcie w danych i mocne w rozumowaniu; `ODDS_TOO_LOW` i "
         "`NEGATIVE_LEG_EV` mają wsparcie **wyłącznie** arytmetyczne i trzeba je "
         "zweryfikować na wyniku slipów przez kilka dni, a nie na ROI nóg.")
    emit("")

    # slip-level counterfactual
    emit("### Efekt na poziomie slipów")
    emit("")
    kept_slips, killed_slips, trimmed = [], [], []
    for slip_id, b in enumerate(picks):
        # By slip, not by fixture: a builder and a single can share one.
        ps = [p for p in positions if p["slip_id"] == slip_id]
        survivors = [p for p in ps if not p["gates"]]
        if len(survivors) == len(ps):
            kept_slips.append((b, ps, survivors))
        elif len(survivors) < (1 if b.get("single") else 2):
            killed_slips.append((b, ps, survivors))
        else:
            trimmed.append((b, ps, survivors))

    def slip_outcome(ps: list[dict[str, Any]]) -> str | None:
        if any(p["outcome"] is None for p in ps):
            return None
        return "WIN" if all(p["outcome"] == "WIN" for p in ps) else "LOSS"

    def money(
        group: list[tuple[Any, list[dict[str, Any]], list[dict[str, Any]]]],
        use_survivors: bool,
    ) -> tuple[float, int]:
        ret, n = 0.0, 0
        for b, ps, sv in group:
            use = sv if use_survivors else ps
            if not use:
                continue
            o = slip_outcome(use)
            if o is None:
                continue
            odds = 1.0
            for p in use:
                odds *= p["odds"]
            ret += (odds - 1.0) if o == "WIN" else -1.0
            n += 1
        return ret, n

    before_ret, before_n = money(kept_slips + killed_slips + trimmed, False)
    after_ret, after_n = money(kept_slips + trimmed, True)
    emit(table(["", "slipów", "wynik (1 j./slip)", "ROI"],
               [["kupon, który poszedł", before_n, f"{before_ret:+.2f} j.",
                 pct_roi(before_ret, before_n)],
                ["po dzisiejszych bramkach", after_n, f"{after_ret:+.2f} j.",
                 pct_roi(after_ret, after_n)]]))
    emit("")
    emit(f"Bramki usunęłyby **{len(killed_slips)}** slipów w całości "
         f"(zostawały <2 nogi) i przycięłyby **{len(trimmed)}**; "
         f"**{len(kept_slips)}** przeszłoby bez zmian.")
    emit("")

    out = (Path(args.out) if args.out
           else Path("reports") / f"sofa_audyt_glaboki_{args.date}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"WROTE {out}")
    return 0


def pct_roi(ret: float, n: int) -> str:
    return f"{100.0 * ret / n:+.1f}%" if n else "—"


if __name__ == "__main__":
    raise SystemExit(main())
