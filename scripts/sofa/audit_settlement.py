"""AUDIT — what the day's whole board actually did, row by row and reason by reason.

SETTLE writes the graded rows; it prints a twelve-line summary and stops. That
summary answers "did the stage work". It does not answer the question an
operator asks the morning after: of everything we forecast, how much came in,
how much did not, and *why* — where "why" is one of two different things that
must never be pooled:

  * a row that was graded and lost: the reason is arithmetic, `actual` against
    `line`. Nothing is missing; we were wrong.
  * a row that was never graded: the reason is a gap — the fixture did not
    finish, the provider had no statistic, the subject matched neither side.
    We are not wrong, we are blind, and a blind row counted as a loss would
    understate the model exactly as much as counting it as a win overstates it.

Reads the day's artifacts plus `sofa_settled_row` and writes one markdown
report. Pure: no provider calls, no writes to the database.

    PYTHONPATH=src:. python scripts/sofa/audit_settlement.py --date 2026-09-19
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, "src")

from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    BUILDER_CORRELATION_HAIRCUT,
    builder_odds,
    is_stakeable,
)

# A settled row's natural key, as the UNIQUE constraint defines it.
Key = tuple[int, str, str, float, str]


def _key(row: dict) -> Key:
    return (
        int(row["sofascore_event_id"]),
        row["market"],
        row.get("subject") or "",
        float(row["line"]),
        row["direction"],
    )


def _family(market: str) -> str:
    """The market family, for a table that fits on a screen.

    `corners_1h_for` and `corners_total` are the same question asked of
    different scopes; a per-market table on 56k rows is 400 lines long and
    says less than a 12-line one.
    """
    for token in ("corners", "cards", "goals", "shots_on", "shots", "fouls",
                  "offsides", "games_won", "sets", "aces", "double_faults"):
        if token in market:
            return token
    return market.split("_")[0]


def _pct(part: int, whole: int) -> str:
    return f"{100.0 * part / whole:.1f}%" if whole else "—"


def _reason_for_loss(row: dict) -> str:
    line, actual, direction = row["line"], row["actual_value"], row["direction"]
    want = ">" if direction == "OVER" else "<"
    return f"padło {actual:g}, potrzebne {want} {line:g}"


def _table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _load_settled(db_path: str, run_date: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM sofa_settled_row WHERE run_date = ?", (run_date,)
        )]
    finally:
        conn.close()


def _outcome_block(title: str, rows: list[dict]) -> str:
    c = Counter(r["outcome"] for r in rows)
    w, lo, p = c["WIN"], c["LOSS"], c["PUSH"]
    decided = w + lo
    return (f"**{title}** — rozliczonych {len(rows)}: "
            f"weszło {w} ({_pct(w, decided)} z rozstrzygniętych), "
            f"nie weszło {lo}, zwrot {p}")


def settle_singles(singles: list[dict], by_key: dict) -> dict[str, Any]:
    """Grade the PDF's printed singles at their printed odds."""
    won = lost = unsettled = 0
    units = 0.0
    conf_sum = 0.0
    for sgl in singles:
        g = by_key.get((sgl["sofascore_event_id"], sgl["market"], sgl["subject"] or "",
                        float(sgl["line"]), sgl["direction"]))
        if g is None or g["outcome"] == "PUSH":
            unsettled += 1
            continue
        conf_sum += sgl["confidence"]
        if g["outcome"] == "WIN":
            won += 1
            units += sgl["offered_odds"] - 1.0
        else:
            lost += 1
            units -= 1.0
    settled = won + lost
    return {"won": won, "lost": lost, "unsettled": unsettled, "settled": settled,
            "units": units,
            "mean_confidence": conf_sum / settled if settled else 0.0}


def slip_status(outcomes: list[str | None]) -> str:
    """A slip's result from its legs' outcomes (None = not settled).

    One lost leg loses the slip whatever the others did. Until 2026-09-23 an
    unsettled leg was checked first, so the 2026-09-22 Accrington slip - one
    leg LOSS in 07_settled.json - was reported as unsettled and left out of
    the day's ROI, which then read -17.7% instead of about -34%.
    """
    if any(o == "LOSS" for o in outcomes):
        return "NIE WESZŁO"
    if any(o is None or o == "PUSH" for o in outcomes):
        return "NIEROZLICZONY"
    return "WESZŁO"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    config = SofaConfig.from_env()
    run_dir = Path(config.runs_dir) / args.date
    sheet = json.loads((run_dir / "05_sheet.json").read_text())
    fixtures = json.loads((run_dir / "02_fixtures.json").read_text())
    coupon_path = run_dir / "06_coupon.json"
    coupon = json.loads(coupon_path.read_text())["singles"] if coupon_path.exists() else []
    settled_path = run_dir / "07_settled.json"
    settled_artifact = json.loads(settled_path.read_text()) if settled_path.exists() else []

    settled_db = _load_settled(config.db_path, args.date)
    by_key = {_key(r): r for r in settled_db}

    fixture_by_id = {f["sofascore_event_id"]: f for f in fixtures}
    sheet_by_key = {_key(r): r for r in sheet}

    # Which board rows never reached a grade, and why. The reason has to come
    # from the row itself — a missing settled row is the *symptom*, not the
    # cause, and "UNSETTLED" as a single bucket is the answer that hides the
    # difference between "the match was postponed" and "we have no reading of
    # that statistic".
    ungraded: list[dict] = []
    for row in sheet:
        if _key(row) not in by_key:
            ungraded.append(row)

    graded_event_ids = {r["sofascore_event_id"] for r in settled_db}

    # The stage's own counter, when it left one: it knows *which* gap stopped
    # each row, and this file cannot rediscover that. The reconstruction below
    # is the fallback for days settled before the counter was written.
    skips_path = run_dir / "07_settle_skips.json"
    stage_skips: dict[str, int] = {}
    if skips_path.exists():
        stage_skips = json.loads(skips_path.read_text()).get("skipped", {})

    ungraded_reasons: Counter[str] = Counter()
    for row in ungraded:
        eid = row["sofascore_event_id"]
        if eid not in graded_event_ids:
            fixture = fixture_by_id.get(eid)
            if fixture is None:
                ungraded_reasons["FIXTURE_NIE_W_ARTEFAKCIE"] += 1
            else:
                ungraded_reasons["MECZ_NIEROZEGRANY_LUB_BEZ_DANYCH"] += 1
        else:
            ungraded_reasons[f"BRAK_ODCZYTU_METRYKI: {row['market']}"] += 1

    lines: list[str] = []
    A = lines.append

    A(f"# Audyt rozliczenia — {args.date}")
    A("")
    A("Wygenerowane przez `scripts/sofa/audit_settlement.py`. Źródła: "
      f"`{run_dir}/05_sheet.json` (co prognozowaliśmy), tabela "
      f"`sofa_settled_row` w `{config.db_path}` (co się wydarzyło), "
      f"`{run_dir}/06_coupon.json` (co trafiło na kupon).")
    A("")

    # ---- 1. zakres -------------------------------------------------------
    A("## 1. Zakres")
    A("")
    priced = [r for r in sheet if r.get("offered_odds")]
    A(_table(
        ["", "liczba"],
        [["fixture'ów na tablicy", len(fixture_by_id)],
         ["fixture'ów z choć jednym wierszem", len({r['sofascore_event_id'] for r in sheet})],
         ["wierszy (rynek × linia × strona) rozważonych", len(sheet)],
         ["— w tym z ceną Superbeta", len(priced)],
         ["— w tym bez ceny (NO_PRICE)", len(sheet) - len(priced)],
         ["wierszy rozliczonych", len(settled_db)],
         ["fixture'ów rozliczonych", len(graded_event_ids)],
         ["wierszy nierozliczonych", len(ungraded)]]))
    A("")

    # ---- 2. wynik --------------------------------------------------------
    A("## 2. Ile weszło, ile nie weszło")
    A("")
    c = Counter(r["outcome"] for r in settled_db)
    decided = c["WIN"] + c["LOSS"]
    A(_table(
        ["wynik", "liczba", "% rozstrzygniętych", "% wszystkich rozważonych"],
        [["WESZŁO (WIN)", c["WIN"], _pct(c["WIN"], decided), _pct(c["WIN"], len(sheet))],
         ["NIE WESZŁO (LOSS)", c["LOSS"], _pct(c["LOSS"], decided), _pct(c["LOSS"], len(sheet))],
         ["ZWROT (PUSH)", c["PUSH"], "—", _pct(c["PUSH"], len(sheet))],
         ["NIEROZLICZONE", len(ungraded), "—", _pct(len(ungraded), len(sheet))]]))
    A("")
    A("**Czytaj to ostrożnie.** Arkusz trzyma obie strony każdego szczebla — "
      "OVER i UNDER tej samej linii — więc jedna z nich musi wejść. Odsetek "
      "trafień liczony na całej tablicy dąży do 50% z konstrukcji i nie jest "
      "wynikiem. Wynikiem są sekcje 5 (co wybrało sito), 7 (co poszło na "
      "kupon) i 8 (czy prawdopodobieństwa są uczciwe).")
    A("")
    A("PUSH to linia całkowita trafiona co do jednego — stawka wraca, żadna "
      "strona nie wygrała. Liczenie jej po którejkolwiek stronie to fikcyjna "
      "przewaga, więc siedzi w osobnym wierszu.")
    A("")

    # ---- 3. dlaczego nie weszło -----------------------------------------
    A("## 3. Dlaczego nie weszło — wiersze rozliczone i przegrane")
    A("")
    A("Tu powód jest arytmetyczny: znamy wynik, linia go nie objęła.")
    A("")
    losses = [r for r in settled_db if r["outcome"] == "LOSS"]
    fam_loss: dict[str, Counter] = defaultdict(Counter)
    for r in settled_db:
        fam_loss[_family(r["market"])][r["outcome"]] += 1
    rows = []
    for fam, cc in sorted(fam_loss.items(), key=lambda kv: -sum(kv[1].values())):
        d = cc["WIN"] + cc["LOSS"]
        rows.append([fam, sum(cc.values()), cc["WIN"], cc["LOSS"], cc["PUSH"], _pct(cc["WIN"], d)])
    A(_table(["rodzina rynku", "rozliczone", "weszło", "nie weszło", "zwrot", "% trafień"], rows))
    A("")

    # the single most common shape of a miss, per family
    A("### Najczęstszy kształt pudła")
    A("")
    rows = []
    by_fam_loss: dict[str, list[dict]] = defaultdict(list)
    for r in losses:
        by_fam_loss[_family(r["market"])].append(r)
    for fam, rs in sorted(by_fam_loss.items(), key=lambda kv: -len(kv[1]))[:12]:
        over = sum(1 for r in rs if r["direction"] == "OVER")
        miss = [abs(r["actual_value"] - r["line"]) for r in rs]
        miss.sort()
        med = miss[len(miss) // 2] if miss else 0.0
        rows.append([fam, len(rs), over, len(rs) - over, f"{med:g}"])
    A(_table(["rodzina", "pudeł", "pudła na OVER", "pudła na UNDER",
              "mediana odchylenia od linii"], rows))
    A("")
    A("Przewaga pudeł po jednej stronie to nie pech, tylko przesunięcie "
      "środka próbki względem tego, co się dzieje.")
    A("")

    # ---- 4. dlaczego nie rozliczone -------------------------------------
    A("## 4. Dlaczego nie rozliczone — wiersze bez oceny")
    A("")
    A("Tu powód jest luką, nie błędem. Taki wiersz **nie jest przegraną** i "
      "nie wolno go doliczać do pudeł.")
    A("")
    if stage_skips:
        A("Powody zapisane przez sam etap SETTLE (`07_settle_skips.json`) — "
          "pełna lista, nie próbka:")
        A("")
        A(_table(["powód", "wierszy"], [[k, v] for k, v in stage_skips.items()]))
        A("")
        A("Słownik: `NOT_FINISHED` — mecz nie doszedł do normalnego końca "
          "(przełożony, w toku, krecz, walkower); `NO_EVENT` — Sofascore nie "
          "zna tego zdarzenia; `<rynek>:<GAP>` — mecz się odbył, ale dostawca "
          "nie ma odczytu tej statystyki; `SUBJECT_NOT_MATCHED` — wiersz "
          "dotyczy drużyny/zawodnika, którego nie dało się jednoznacznie "
          "przypisać do żadnej ze stron (odmowa zgadywania: zła strona "
          "odwraca pomiar, a nie tylko go psuje); `PROVIDER_ERROR` — awaria "
          "po stronie dostawcy.")
        A("")
        A("Rekonstrukcja z artefaktów, dla porównania:")
        A("")
    if ungraded_reasons:
        A(_table(["powód", "wierszy"],
                 [[k, v] for k, v in ungraded_reasons.most_common(25)]))
    else:
        A("Brak — rozliczone zostało wszystko.")
    A("")
    unsettled_events = sorted({r["sofascore_event_id"] for r in ungraded
                               if r["sofascore_event_id"] not in graded_event_ids})
    if unsettled_events:
        A(f"### Fixture'y bez ani jednego rozliczonego wiersza ({len(unsettled_events)})")
        A("")
        rows = []
        for eid in unsettled_events[:60]:
            f = fixture_by_id.get(eid, {})
            rows.append([eid,
                         f"{f.get('home_name','?')} – {f.get('away_name','?')}",
                         f.get("sport", "?"),
                         f.get("kickoff_utc", "?"),
                         sum(1 for r in ungraded if r["sofascore_event_id"] == eid)])
        A(_table(["event_id", "mecz", "sport", "start (UTC)", "wierszy straconych"], rows))
        if len(unsettled_events) > 60:
            A("")
            A(f"…oraz {len(unsettled_events) - 60} dalszych.")
        A("")

    # ---- 5. po werdykcie -------------------------------------------------
    A("## 5. Po werdykcie — czy sito coś wybierało")
    A("")
    rows = []
    for verdict in ("VALUE", "LEAN", "BELOW_BAR", "NO_PRICE"):
        vr = [r for r in settled_db if (sheet_by_key.get(_key(r)) or {}).get("verdict") == verdict]
        cc = Counter(r["outcome"] for r in vr)
        d = cc["WIN"] + cc["LOSS"]
        in_sheet = sum(1 for r in sheet if r["verdict"] == verdict)
        rows.append([verdict, in_sheet, len(vr), cc["WIN"], cc["LOSS"], cc["PUSH"], _pct(cc["WIN"], d)])
    A(_table(["werdykt", "na tablicy", "rozliczone", "weszło", "nie weszło", "zwrot", "% trafień"], rows))
    A("")

    # ---- 6. po sporcie ---------------------------------------------------
    A("## 6. Po sporcie")
    A("")
    rows = []
    for sport in sorted({r["sport"] for r in settled_db}):
        sr = [r for r in settled_db if r["sport"] == sport]
        cc = Counter(r["outcome"] for r in sr)
        d = cc["WIN"] + cc["LOSS"]
        rows.append([sport, len(sr), cc["WIN"], cc["LOSS"], cc["PUSH"], _pct(cc["WIN"], d)])
    A(_table(["sport", "rozliczone", "weszło", "nie weszło", "zwrot", "% trafień"], rows))
    A("")

    # ---- 7. kupon --------------------------------------------------------
    # Not "the coupon": 06_coupon.json holds the VALUE singles, and the PDF
    # is what gets staked (7c). The old heading said the opposite.
    A("## 7. Pojedyncze VALUE (06_coupon.json) — materiał wejściowy, nie kupon")
    A("")
    if not coupon:
        A("06_coupon.json nie ma ani jednej pozycji (albo pliku brak). "
          "Kupon z PDF jest w sekcji 7c.")
    else:
        graded_legs, ungraded_legs = [], []
        for leg in coupon:
            got = by_key.get(_key(leg))
            (graded_legs if got else ungraded_legs).append((leg, got))
        cc = Counter(g["outcome"] for _, g in graded_legs)
        d = cc["WIN"] + cc["LOSS"]
        A(_table(["", "liczba"],
                 [["nóg na kuponie", len(coupon)],
                  ["rozliczonych", len(graded_legs)],
                  ["WESZŁO", cc["WIN"]],
                  ["NIE WESZŁO", cc["LOSS"]],
                  ["ZWROT", cc["PUSH"]],
                  ["nierozliczonych", len(ungraded_legs)],
                  ["% trafień", _pct(cc["WIN"], d)]]))
        A("")
        stake_return = sum(
            (g["offered_odds"] - 1.0) if g["outcome"] == "WIN"
            else (0.0 if g["outcome"] == "PUSH" else -1.0)
            for _, g in graded_legs if g["offered_odds"])
        n_staked = sum(1 for _, g in graded_legs if g["offered_odds"])
        A(f"Przy stawce 1 jednostki na każdą rozliczoną nogę: wynik "
          f"**{stake_return:+.2f} j.** na {n_staked} nogach, ROI "
          f"**{100.0 * stake_return / n_staked:+.1f}%**." if n_staked else "")
        A("")
        A("### Noga po nodze")
        A("")
        rows = []
        for leg, got in sorted(graded_legs, key=lambda x: (x[1]["outcome"] != "LOSS", -(x[0].get("offered_odds") or 0))):
            rows.append([
                leg.get("match_name", leg["sofascore_event_id"]),
                f"{leg['market']} {leg.get('subject') or ''}".strip(),
                f"{leg['direction']} {leg['line']:g}",
                f"{leg.get('offered_odds') or 0:.2f}",
                f"{leg.get('p_bar', 0):.3f}",
                {"WIN": "WESZŁO", "LOSS": "NIE WESZŁO", "PUSH": "ZWROT"}[got["outcome"]],
                _reason_for_loss(got) if got["outcome"] == "LOSS" else f"padło {got['actual_value']:g}",
            ])
        A(_table(["mecz", "rynek", "linia", "kurs", "p_bar", "wynik", "powód"], rows))
        A("")
        if ungraded_legs:
            A(f"### Nogi bez rozliczenia ({len(ungraded_legs)})")
            A("")
            rows = []
            for leg, _ in ungraded_legs:
                eid = leg["sofascore_event_id"]
                reason = ("mecz nierozegrany lub bez statystyk"
                          if eid not in graded_event_ids
                          else f"brak odczytu metryki `{leg['market']}`")
                rows.append([leg.get("match_name", eid),
                             f"{leg['market']} {leg.get('subject') or ''}".strip(),
                             f"{leg['direction']} {leg['line']:g}", reason])
            A(_table(["mecz", "rynek", "linia", "powód"], rows))
            A("")

    # ---- 7b/7c. the coupon that was actually printed ---------------------
    #
    # L: the 2026-09-08 "analysis" that never touched the six real VALUE bets.
    # The day leaves three different selections on disk and only one of them
    # is the coupon: `06_coupon.json` is the VALUE singles, `08_confidence.json`
    # holds every leg over the confidence floor, and the PDF renders the
    # subset of `builders` with `best_for_fixture` and a positive EV. Auditing
    # the first and calling it "the coupon" is how a losing day gets reported
    # as a winning one, or the reverse.
    conf_path = run_dir / "08_confidence.json"
    if conf_path.exists():
        conf = json.loads(conf_path.read_text())
        A("## 7b. Lista pewnościowa — wszystkie nogi nad progiem")
        A("")
        legs = conf["legs"]
        graded = [(L, by_key[_key({**L, "sofascore_event_id": L["sofascore_event_id"]})])
                  for L in legs
                  if _key({**L, "sofascore_event_id": L["sofascore_event_id"]}) in by_key]
        decided = [(L, g) for L, g in graded if g["outcome"] != "PUSH"]
        won = sum(1 for _, g in decided if g["outcome"] == "WIN")
        ret = sum((L["offered_odds"] - 1.0) if g["outcome"] == "WIN" else -1.0
                  for L, g in decided)
        declared = sum(L["confidence"] for L, _ in decided) / len(decided) if decided else 0.0
        A(_table(["", "liczba"],
                 [["nóg nad progiem", len(legs)],
                  ["rozliczonych", len(decided)],
                  ["nierozliczonych", len(legs) - len(graded)],
                  ["WESZŁO", won],
                  ["NIE WESZŁO", len(decided) - won],
                  ["% trafień", _pct(won, len(decided))],
                  ["deklarowana pewność (śr.)", f"{declared:.3f}"],
                  ["ROI przy 1 j. na nogę", f"{100.0 * ret / len(decided):+.1f}%" if decided else "—"]]))
        A("")
        A("`confidence` to **dolne ograniczenie** zrealizowanego odsetka, nie "
          "deklaracja modelu. Jeśli rzeczywistość wychodzi powyżej niego, "
          "krzywa działa. Ujemne ROI przy poprawnej kalibracji znaczy jedno: "
          "marża Superbeta na krótkich kursach jest większa niż nasza "
          "przewaga — mamy rację co do meczu i i tak płacimy za nią za dużo.")
        A("")
        rows = []
        cb: dict[int, list] = defaultdict(list)
        for L, g in decided:
            cb[min(int(L["confidence"] * 20), 19)].append((L, g))
        for k in sorted(cb):
            rs = cb[k]
            dec = sum(L["confidence"] for L, _ in rs) / len(rs)
            real = sum(1 for _, g in rs if g["outcome"] == "WIN") / len(rs)
            rows.append([f"{k / 20:.2f}–{(k + 1) / 20:.2f}", len(rs),
                         f"{dec:.3f}", f"{real:.3f}", f"{real - dec:+.3f}"])
        A(_table(["kubełek confidence", "nóg", "deklarowane", "rzeczywiste", "różnica"], rows))
        A("")

        A("## 7c. KUPON Z PDF — to, co naprawdę poszło na typ")
        A("")
        A("PDF renderuje te Bet Buildery, które mają `best_for_fixture` i "
          "dodatnie EV. To jest kupon. Sekcja 7 (pojedynki VALUE) i 7b (cała "
          "lista nóg) to materiał wejściowy, nie zakład.")
        A("")
        # Screen prices, when the operator recorded them. Key: the fixture's
        # sofascore_event_id as a string. A measured price always beats the
        # haircut estimate, and until this file exists for a day, every slip
        # ROI in this report is an estimate and says so.
        screen_path = run_dir / "09_screen_prices.json"
        screen = (json.loads(screen_path.read_text(encoding="utf-8"))
                  if screen_path.exists() else {})
        picks = [b for b in conf["builders"] if is_stakeable(b)]

        def slip_odds(b: dict) -> tuple[float, bool]:
            """What this slip really paid, and whether we measured it."""
            real = screen.get(str(b["sofascore_event_id"]))
            if real is not None:
                return float(real), True
            return builder_odds(b["odds_if_product"]), False

        slip_rows, sw, sl, su, sret, sn = [], 0, 0, 0, 0.0, 0
        n_measured = 0
        lw = ll = lu = 0
        for b in picks:
            outs = []
            for L in b["legs"]:
                g = by_key.get((b["sofascore_event_id"], L["market"], L["subject"] or "",
                                float(L["line"]), L["direction"]))
                outs.append((L, g))
                if g is None or g["outcome"] == "PUSH":
                    lu += 1
                elif g["outcome"] == "WIN":
                    lw += 1
                else:
                    ll += 1
            status = slip_status([None if g is None else g["outcome"] for _, g in outs])
            if status == "NIEROZLICZONY":
                su += 1
            elif status == "WESZŁO":
                sw, sn = sw + 1, sn + 1
                odds, measured = slip_odds(b)
                n_measured += measured
                sret += odds - 1.0
            else:
                sl, sn = sl + 1, sn + 1
                sret -= 1.0
            slip_rows.append((b, status, outs))
        A(_table(["", "liczba"],
                 [["slipów na kuponie", len(picks)],
                  ["rozliczonych", sn],
                  ["WESZŁO (cały slip)", sw],
                  ["NIE WESZŁO", sl],
                  ["nierozliczonych", su],
                  ["% slipów trafionych", _pct(sw, sn)],
                  ["nóg: weszło / nie weszło", f"{lw} / {ll}"],
                  ["% nóg trafionych", _pct(lw, lw + ll)],
                  ["deklarowane combined_probability (śr.)",
                   f"{sum(b['combined_probability'] for b in picks) / len(picks):.3f}" if picks else "—"],
                  ["cen z ekranu", f"{n_measured} / {sw} wygranych slipów"],
                  ["wynik przy 1 j. na slip", f"{sret:+.2f} j."],
                  ["ROI", f"{100.0 * sret / sn:+.1f}%" if sn else "—"]]))
        A("")
        if n_measured < sw:
            A(f"**Kurs slipa jest w większości szacowany.** Zmierzonych cen z "
              f"ekranu: {n_measured} z {sw}. Reszta to iloczyn kursów nóg "
              f"pomniejszony o {BUILDER_CORRELATION_HAIRCUT:.0%} — zmierzony "
              "narzut Superbeta za korelację (8,8% / 15,8% / 19,6% na trzech "
              "slipach z 2026-09-20). Wcześniejsze wersje tego raportu liczyły "
              "sam iloczyn i zawyżały ROI o kilkanaście punktów procentowych. "
              "Żeby to przestało być szacunkiem, wpisz ceny do "
              "`09_screen_prices.json` (klucz: `sofascore_event_id`).")
            A("")
        A(f"Do tego {sn} slipów to próbka, w której odchylenie standardowe "
          "wyniku sięga kilku jednostek: to nie jest dowód przewagi, to brak "
          "dowodu straty.")
        A("")
        A("### Slip po slipie")
        A("")
        rows = []
        for b, status, outs in sorted(slip_rows, key=lambda x: (x[1] != "NIE WESZŁO",)):
            broke = [f"{L['market']} {L['subject'] or ''} {L['direction']} {L['line']:g} "
                     f"(padło {g['actual_value']:g})"
                     for L, g in outs if g is not None and g["outcome"] == "LOSS"]
            missing = [f"{L['market']} {L['subject'] or ''}".strip()
                       for L, g in outs if g is None]
            reason = ("; ".join(broke) if broke
                      else ("brak rozliczenia: " + ", ".join(missing) if missing
                            else "wszystkie nogi weszły"))
            odds, measured = slip_odds(b)
            rows.append([b["match"], b["n_legs"], f"{b['odds_if_product']:.2f}",
                         f"{odds:.2f}" + ("" if measured else " (szac.)"),
                         f"{b['combined_probability']:.3f}", status, reason])
        A(_table(["mecz", "nóg", "iloczyn", "kurs użyty", "p slipa", "wynik",
                  "co położyło slip"], rows))
        A("")

        # The PDF prints singles too (since 2026-09-22), and on 2026-09-23 it
        # printed 216 singles and no builder - a day this section would have
        # reported as "0 slips" without one word about what was on the page.
        singles = conf.get("singles") or []
        A("### Zakłady pojedyncze z PDF")
        A("")
        if not singles:
            A("PDF nie drukował pojedynczych.")
            A("")
        else:
            res = settle_singles(singles, by_key)
            A(_table(["", "liczba"],
                     [["pojedynczych na kuponie", len(singles)],
                      ["rozliczonych", res["settled"]],
                      ["weszło / nie weszło", f"{res['won']} / {res['lost']}"],
                      ["nierozliczonych", res["unsettled"]],
                      ["% trafionych", _pct(res["won"], res["settled"])],
                      ["deklarowana pewność (śr.)", f"{res['mean_confidence']:.3f}"
                       if res["settled"] else "—"],
                      ["wynik przy 1 j. na pozycję", f"{res['units']:+.2f} j."],
                      ["ROI", f"{100.0 * res['units'] / res['settled']:+.1f}%"
                       if res["settled"] else "—"]]))
            A("")
            A("To są pozycje wydrukowane, nie postawione: PDF nie wie, które z "
              "nich operator wziął. Kurs to `offered_odds` z artefaktu.")
            A("")

    # ---- 8. kalibracja ---------------------------------------------------
    A("## 8. Kalibracja — czy 70% znaczy 70%")
    A("")
    A("Liczone na `p_bar`, czyli na tej liczbie, którą kupon faktycznie "
      "porównuje z kursem. PUSH-e wyrzucone.")
    A("")
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in settled_db:
        if r["outcome"] == "PUSH":
            continue
        b = min(int(r["p_bar"] * 10), 9)
        buckets[f"{b / 10:.1f}–{(b + 1) / 10:.1f}"].append(r)
    rows = []
    for label in sorted(buckets):
        rs = buckets[label]
        pred = sum(r["p_bar"] for r in rs) / len(rs)
        real = sum(1 for r in rs if r["outcome"] == "WIN") / len(rs)
        rows.append([label, len(rs), f"{pred:.3f}", f"{real:.3f}", f"{real - pred:+.3f}"])
    A(_table(["kubełek p_bar", "wierszy", "prognoza (śr. p_bar)", "rzeczywistość", "różnica"], rows))
    A("")
    A("Dodatnia różnica = byliśmy zbyt ostrożni, ujemna = zbyt pewni.")
    A("")

    A("## 9. Czego ten raport nie mówi")
    A("")
    A("- ROI liczone jest tylko tam, gdzie znamy kurs Superbeta z dnia. "
      "Wiersze NO_PRICE mają rozliczony wynik i żadnej ceny, więc wchodzą do "
      "kalibracji, a nie do rachunku pieniędzy.")
    A("- Wiersz nierozliczony nie jest przegraną. Sekcja 4 trzyma je osobno "
      "celowo; wrzucenie ich do pudeł zaniżyłoby model dokładnie tak samo, "
      "jak wrzucenie do trafień by go zawyżyło.")
    A("- `07_settled.json` z tego dnia ma "
      f"{len(settled_artifact)} wierszy; baza ma {len(settled_db)}. "
      "Rozjazd oznacza, że dzień rozliczano więcej niż raz.")

    out = Path(args.out) if args.out else Path("reports") / f"sofa_audyt_rozliczenia_{args.date}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"WROTE {out} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
