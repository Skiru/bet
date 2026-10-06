# ruff: noqa: E501, N806  - report lines are tables; A = lines.append as in audit_settlement.
"""AUDIT - the niche scanner: is Superbet's price wrong in some league, out of sample?

A measurement, never a coupon input. It reads the priced, settled rows of
`sofa_settled_row` (read-only), the days' `02_fixtures.json` for country/tier,
and writes a Polish report plus a JSON artifact. It feeds nothing - not
COUPON, CONFIDENCE, SHEET nor the vetoes - changes no constant, and is not in
DEFAULT_SEQUENCE. Run it after SETTLE, like the other audits:

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_niches.py --from 2026-09-17 --to 2026-09-28

The method is in `bet.sofa.niches`. Offline by construction: no client, no
bridge, no Superbet fetcher is imported.

Exit: 0 OK, 1 PARTIAL (a grouping had no out-of-sample day, or fixtures were
missing for part of the rows), 2 FAILED (no database or no priced rows).
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, "src")

from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.niches import (  # noqa: E402
    FDR_Q,
    MIN_OOS_MATCHES,
    MIN_TRAIN_DAYS,
    MIN_TRAIN_MATCHES,
    SettledRow,
    in_scope,
    scan_all,
)

STAGE = "NICHES"
CACHE_RUN_DATE = "cache-calibration"


def _table(header: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def connect_ro(db_path: str) -> sqlite3.Connection:
    """The database, opened read-only: the scanner may never write it."""
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def load_priced_rows(conn: sqlite3.Connection, date_from: str, date_to: str) -> list[SettledRow]:
    """Every graded row with a Superbet price and a devigged probability.

    `cache-calibration` rows are excluded by name as well as by the date range:
    they have outcomes and no price, and cannot say whether a pattern is priced.
    """
    cur = conn.execute(
        "SELECT run_date, sofascore_event_id, sport, competition_id, market, subject,"
        " line, direction, market_p, offered_odds, outcome, p_central"
        " FROM sofa_settled_row"
        " WHERE run_date >= ? AND run_date <= ? AND run_date != ?"
        " AND offered_odds IS NOT NULL AND offered_odds > 1.0"
        " AND market_p IS NOT NULL AND market_p > 0 AND market_p < 1"
        " AND outcome IN ('WIN', 'LOSS') AND competition_id IS NOT NULL",
        (date_from, date_to, CACHE_RUN_DATE),
    )
    return [
        SettledRow(day=r[0], event=int(r[1]), sport=r[2], competition=int(r[3]),
                   market=r[4], subject=r[5] or "", line=float(r[6]), direction=r[7],
                   market_p=float(r[8]), odds=float(r[9]), won=r[10] == "WIN",
                   p_central=float(r[11]))
        for r in cur
    ]


def load_fixtures(runs_dir: Path, days: list[str]) -> dict[int, dict[str, Any]]:
    """event id -> the fixture as the day's 02_fixtures.json has it."""
    out: dict[int, dict[str, Any]] = {}
    for day in days:
        path = runs_dir / day / "02_fixtures.json"
        if not path.exists():
            continue
        for f in json.loads(path.read_text(encoding="utf-8")):
            out[int(f["sofascore_event_id"])] = f
    return out


def describe_from_cache(
    conn: sqlite3.Connection, cells: list[tuple[int, str]],
) -> list[dict[str, Any]]:
    """How stable a competition's RAW pattern is, from cache-calibration rows.

    Description only: these rows have no price. Per (competition, market) the
    distinct matches are split in two halves by Sofascore event id - ids are
    allocated roughly in time order, so the halves are "older" and "newer" as
    an approximation, not as dates - and each half's mean of the settled
    quantity is reported. A pattern that moves between halves was not a
    property of the league.
    """
    if not cells:
        return []
    comps = sorted({c for c, _ in cells})
    markets = sorted({m for _, m in cells})
    q = (
        "SELECT competition_id, market, subject, sofascore_event_id, MAX(actual_value)"
        " FROM sofa_settled_row WHERE run_date = ?"
        f" AND competition_id IN ({','.join('?' * len(comps))})"
        f" AND market IN ({','.join('?' * len(markets))})"
        " GROUP BY competition_id, market, subject, sofascore_event_id"
    )
    vals: dict[tuple[int, str], list[tuple[int, float]]] = defaultdict(list)
    for comp, market, _subj, ev, actual in conn.execute(q, (CACHE_RUN_DATE, *comps, *markets)):
        vals[(int(comp), market)].append((int(ev), float(actual)))
    out = []
    for comp, market in sorted(set(cells)):
        pts = sorted(vals.get((comp, market), []))
        if len(pts) < 10:
            out.append({"competition_id": comp, "market": market, "matches": len(pts)})
            continue
        half = len(pts) // 2
        older = [a for _, a in pts[:half]]
        newer = [a for _, a in pts[half:]]
        allv = [a for _, a in pts]
        mean = sum(allv) / len(allv)
        sd = math.sqrt(sum((a - mean) ** 2 for a in allv) / (len(allv) - 1))
        out.append({
            "competition_id": comp, "market": market, "matches": len({e for e, _ in pts}),
            "values": len(pts), "mean": round(mean, 3), "sd": round(sd, 3),
            "mean_older_half": round(sum(older) / len(older), 3),
            "mean_newer_half": round(sum(newer) / len(newer), 3),
        })
    return out


def groupings(fixtures: dict[int, dict[str, Any]]) -> dict[str, Any]:
    def by_competition(r: SettledRow) -> str:
        return f"{r.sport}:{r.competition}"

    def by_category(r: SettledRow) -> str | None:
        f = fixtures.get(r.event)
        if f is None or not f.get("category_name"):
            return None
        return f"{r.sport}:{f['category_name']}"

    def whole_market(r: SettledRow) -> str:
        return f"{r.sport}:*"

    return {
        "market": (whole_market, False),
        "competition": (by_competition, False),
        "competition_band": (by_competition, True),
        "category": (by_category, False),
    }


def group_names(fixtures: dict[int, dict[str, Any]]) -> dict[str, str]:
    """group key -> a human name ("football:325" -> "Brasileirão Betano (Brazil)")."""
    out: dict[str, str] = {}
    for f in fixtures.values():
        cid = f.get("competition_id")
        if cid is not None:
            out[f"{f['sport']}:{cid}"] = (f"{f.get('competition_name') or '?'}"
                                          f" ({f.get('category_name') or '?'})")
    return out


def build(
    rows: list[SettledRow], fixtures: dict[int, dict[str, Any]], date_from: str,
    date_to: str, min_matches: int, min_train_days: int,
) -> dict[str, Any]:
    scoped = [r for r in rows if in_scope(r.sport, r.market)]
    skipped = Counter(r.market for r in rows if not in_scope(r.sport, r.market))
    result = scan_all(rows, groupings(fixtures), min_matches=min_matches,
                      min_train_days=min_train_days)
    names = group_names(fixtures)
    for s in result["scans"]:
        for coll in ("candidates", "watch", "raw_top"):
            for c in s[coll]:
                c["name"] = names.get(c["group"], c["group"])
    for c in result["candidates"] + result.get("power", {}).get("largest_cells", []):
        c["name"] = names.get(c["group"], c["group"])
    missing_fx = len({r.event for r in scoped if r.event not in fixtures})
    return {
        "stage": STAGE,
        "from": date_from,
        "to": date_to,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "params": {"min_train_matches": min_matches, "min_train_days": min_train_days,
                   "min_oos_matches": MIN_OOS_MATCHES, "fdr_q": FDR_Q},
        "data": {
            "rows_loaded": len(rows),
            "rows_in_scope": len(scoped),
            "matches_in_scope": len({r.event for r in scoped}),
            "days": sorted({r.day for r in rows}),
            "events_without_fixture": missing_fx,
            "skipped_markets": dict(skipped.most_common()),
        },
        **result,
    }


# ---- rendering -------------------------------------------------------------


def _pp(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:+.1f} pp"


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:+.1f}%"


def _ci(ci: list[float] | None) -> str:
    return "—" if not ci else f"[{100 * ci[0]:+.1f}%; {100 * ci[1]:+.1f}%]"


def _need(n: int | None) -> str:
    """Matches needed; past 100 000 the exact figure means only "never"."""
    if n is None:
        return "— (brak przewagi)"
    return "> 100 000" if n > 100_000 else f"{n:,}".replace(",", " ")


def _roi_line(s: dict[str, Any]) -> str:
    return (f"{s['bets']} zakładów / {s['matches']} meczów, ROI {_pct(s['roi'])}, "
            f"95% CI {_ci(s['roi_ci95'])}")


GROUPING_PL = {
    "market": "cały rynek (bez wyboru ligi)",
    "competition": "liga (competition_id)",
    "competition_band": "liga × przedział kursu",
    "category": "kraj/poziom (category_name)",
}


def _cell_rows(cells: list[dict[str, Any]]) -> list[list[Any]]:
    rows = []
    for c in cells:
        o = c["oos"]
        rows.append([
            GROUPING_PL.get(c.get("grouping", ""), c.get("grouping", "")), c["name"],
            c["market"], c["direction"], c["band"] or "—", c["matches"],
            _pp(c["raw_bias"]), _pp(c["shrunk_bias"]), _pp(c["hurdle"]),
            "—" if c["pair_margin"] is None else f"{100 * c['pair_margin']:.1f}%",
            _pct(c["raw_ev"]), _pct(c["predicted_ev"]),
            f"{o['bets']}/{o['matches']}", _pct(o["roi"]), _ci(o["roi_ci95"]),
            f"{c['oos_p']:.3f}",
            _need(c["matches_needed_bh"]),
            _need(c["matches_needed_bh_edge_5pp"]),
        ])
    return rows


CELL_HEADER = ["grupowanie", "grupa", "rynek", "kier.", "kurs", "meczów (in-sample)",
               "bias surowy", "bias po ściągnięciu", "próg (1/kurs − p)", "marża pary",
               "EV surowe", "EV po ściągnięciu", "OOS zakł./mecze", "OOS ROI", "OOS 95% CI", "p (OOS)",
               "meczów potrzeba, gdyby surowe EV było prawdziwe (BH)",
               "meczów potrzeba dla +5 pp (BH)"]


def render(art: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    A = lines.append
    d = art["data"]
    found = art["verdict"] == "NISZA_ZNALEZIONA"
    A(f"# Skaner nisz — {art['from']} … {art['to']}")
    A("")
    A("Pomiar, nie kupon. Ten raport nie zasila COUPON, CONFIDENCE, SHEET ani wet, "
      "nie zmienia żadnej stałej i nie jest listą zakładów. **Decyzja o stawce "
      "należy do operatora.**")
    A("")
    A("## 1. Werdykt")
    A("")
    A(f"**{'NISZA ZNALEZIONA' if found else 'BRAK NISZY'}** — kandydatów: "
      f"{len(art['candidates'])} po korekcie Benjaminiego–Hochberga (FDR "
      f"{art['bh']['q']:.2f}) na {art['bh']['m']} przeskanowanych komórkach "
      f"we wszystkich grupowaniach; odrzuceń H0: {art['bh']['rejected']}.")
    A("")
    A(f"Dane: `sofa_settled_row`, wiersze z ceną Superbeta i `market_p`, "
      f"{d['days'][0] if d['days'] else '—'} … {d['days'][-1] if d['days'] else '—'}: "
      f"{d['rows_loaded']} wierszy, w zakresie skanu {d['rows_in_scope']} "
      f"({d['matches_in_scope']} meczów). Po deduplikacji jeden szczebel na "
      f"(mecz, rynek, podmiot, kierunek).")
    A("")
    A("Wynik poza próbą (walk-forward: komórki na dzień D wybrane tylko z dni < D, "
      "K również), przy wydrukowanych kursach, 1 j. na zakład:")
    A("")
    rows = []
    for s in art["scans"]:
        h = s["headline"]
        rows.append([GROUPING_PL.get(s["grouping"], s["grouping"]),
                     f"{len(s['days_bet'])} ({s['days_bet'][0] if s['days_bet'] else '—'} …)",
                     _roi_line(h["selector"]), _roi_line(h["baseline"]),
                     _ci(h["diff_ci95"]).replace("%", " pp")])
    A(_table(["grupowanie", "dni OOS", "selektor", "baza (te same rynki/kierunki, bez ligi)",
              "selektor − baza, 95% CI"], rows))
    A("")
    idle = [GROUPING_PL.get(s["grouping"], s["grouping"]) for s in art["scans"]
            if s["days_bet"] and not s["headline"]["selector"]["bets"]]
    if idle:
        A("Selektor bez ani jednego zakładu (" + ", ".join(idle) + ") to wynik, nie "
          "awaria: na każdy dzień ściąganie dopasowane na dniach wcześniejszych "
          "sprowadzało bias komórek tak blisko ceny, że żadna nie pokonywała własnej "
          "marży (sekcja 4). Baza jest wtedy pusta, bo liczy się tylko w rynkach "
          "wybranych komórek.")
        A("")
    A("Baza to wszystkie zakłady dnia D w tych samych (rynek, kierunek, przedział) co "
      "wybrane komórki, bez wyboru ligi — więc różnica mierzy wartość samego wyboru "
      "ligi. Przedziały: bootstrap po meczach (2000 losowań, ziarno stałe).")
    A("")
    if not found:
        A("**Czego trzeba, żeby to się zmieniło:** patrz kolumna „meczów potrzeba” "
          "w sekcji 3 — to liczba rozliczonych meczów z ceną, przy której przewaga "
          "danej wielkości byłaby odróżnialna od zera (moc 80%, próg BH dla jednego "
          "odkrycia w tej rodzinie testów).")
        A("")

    pw = art.get("power") or {}
    if pw:
        A(f"**Moc.** Odchylenie zysku na zakład (jeden zakład na mecz, grupowanie "
          f"„{GROUPING_PL.get(pw['grouping'], pw['grouping'])}”): {pw['sd_profit_per_bet']:.3f} j. "
          f"Próg BH dla jednego odkrycia wśród {art['bh']['m']} komórek: "
          f"α = {pw['alpha_bh']:.2e}. Ilu różnych meczów potrzeba JEDNEJ komórce, żeby "
          "prawdziwa przewaga była widoczna z mocą 80%:")
        A("")
        A(_table(["przewaga (ROI)", "meczów, jeden test (α 0,05)", "meczów, po korekcie BH"],
                 [[f"+{100 * r['edge_roi']:.0f}%", _need(r["matches_single_test"]),
                   _need(r["matches_bh"])] for r in pw["rows"]]))
        A("")
        A(f"Największe komórki po {pw['days']} dniach:")
        A("")
        A(_table(["grupa", "rynek", "kier.", "meczów", "meczów/dzień"],
                 [[c.get("name", c["group"]), c["market"], c["direction"], c["matches"],
                   c["matches_per_day"]] for c in pw["largest_cells"]]))
        A("")
    A("## 2. Kandydaci na niszę")
    A("")
    if art["candidates"]:
        A("Wszystkie trzy warunki naraz: ściągnięty bias pokonuje własną marżę komórki "
          "(przewidywane EV > 0 na całości), ROI poza próbą > 0, i komórka przechodzi "
          "BH. Nadal pomiar — nie zakład.")
        A("")
        A(_table(CELL_HEADER, _cell_rows(art["candidates"])))
    else:
        A("Brak. Żadna komórka nie spełnia naraz: ściągnięty bias > własna marża, "
          "ROI poza próbą > 0, przejście korekty BH.")
    A("")

    A("## 3. Lista obserwacyjna — obiecujące, NIE udowodnione")
    A("")
    A(f"Komórki z ≥ {art['params']['min_train_matches']} meczami, których surowa "
      "średnia albo bias po ściągnięciu na całym okresie (in-sample) pokonuje własną "
      "marżę, albo które poza próbą mają ROI > 0 na ≥ 10 meczach — i nie przeszły "
      f"testu. „p (OOS)” = 1 oznacza < {MIN_OOS_MATCHES} meczów poza próbą albo brak "
      "wyboru. To nie są typy.")
    A("")
    for s in art["scans"]:
        A(f"### {GROUPING_PL.get(s['grouping'], s['grouping'])} — "
          f"{s['watch_total']} komórek (pokazane {len(s['watch'])})")
        A("")
        if s["watch"]:
            A(_table(CELL_HEADER, _cell_rows([{**c, "grouping": s["grouping"]}
                                              for c in s["watch"]])))
        else:
            A("Brak.")
        A("")

    A("## 4. Ściąganie do rynku — dopasowanie K (Brier poza próbą)")
    A("")
    A("Dwa poziomy: bias komórki = n/(n+K) × bias komórki + K/(n+K) × cel, "
      "a cel = bias rynku ściągnięty do zera (do ceny) wagą K_rynku; n = mecze. "
      "(K, K_rynku) dopasowane regułą właściwą (Brier) na dniach poza próbą; na "
      "dzień D użyta jest para najlepsza na dniach < D. K = 0 to surowa średnia "
      "komórki; (inf, inf) to goła cena. Pełna siatka w JSON.")
    A("")
    for s in art["scans"]:
        kf = s["k_fit"]
        grid = {(str(r["k"]), str(r["k_market"])): r["brier"] for r in kf["brier_by_k"]}
        best = kf["k_final"]
        picks = [("najlepsza para", best),
                 ("surowa komórka, K=0 (przy najlepszym K_rynku)", [0.0, best[1]] if best else None),
                 ("liga = bias rynku z treningu (inf, 0)", ["inf", 0.0]),
                 ("goła cena (inf, inf)", ["inf", "inf"])]
        rows = []
        for label, kp in picks:
            if kp is None:
                continue
            v = grid.get((str(kp[0]), str(kp[1])))
            rows.append([label, f"({kp[0]}, {kp[1]})", "—" if v is None else f"{v:.6f}"])
        A(f"**{GROUPING_PL.get(s['grouping'], s['grouping'])}** — {kf['scored_units']} "
          f"ocenionych jednostek; para użyta dzień po dniu: "
          + ", ".join(f"{d[5:]}=({k[0]}, {k[1]})" for d, k in s["k_by_day"].items()))
        A("")
        A(_table(["wariant", "(K, K_rynku)", "Brier poza próbą"], rows))
        A("")

    A("## 5. Kontekst in-sample (tylko tło — nie dowód)")
    A("")
    A("### 5a. Bias rynku (realizacja − cena bez marży), po deduplikacji")
    A("")
    ctx = art["context"]
    focus = [r for r in ctx["market_bias"] if r["matches"] >= 100]
    A(_table(["rynek", "kier.", "meczów", "zakładów", "bias", "próg", "ROI"],
             [[r["market"], r["direction"], r["matches"], r["units"], _pp(r["bias"]),
               _pp(r["hurdle"]), _pct(r["roi"])] for r in focus]))
    A("")
    A("### 5b. Czy liga z pierwszej połowy dni powtarza się w drugiej (OVER)")
    A("")
    A("Korelacja Pearsona (bez wag) biasu ligi w pierwszej i drugiej połowie dni, "
      "ligi z ≥ 5 meczami w obu połowach; potem: co ligi dodatnie w 1. połowie "
      "zrobiły w 2.")
    A("")
    A(_table(["rodzina", "dni 1", "dni 2", "lig (≥5 meczów w obu)", "korelacja",
              "lig dodatnich w 1.", "ich bias w 2.", "ich ROI w 2."],
             [[p["family"], "–".join(x[5:] for x in p.get("first_days", [])),
               "–".join(x[5:] for x in p.get("second_days", [])), p["groups"],
               p.get("corr"), p.get("first_positive_groups", "—"),
               _pp(p.get("their_second_half_bias")), _pct(p.get("their_second_half_roi"))]
              for p in ctx["persistence"]]))
    A("")
    A("### 5b'. corners_total na surowych wierszach (wszystkie szczeble, obie strony)")
    A("")
    A("Tylko do porównania z liczbami podawanymi wcześniej na poziomie wierszy; "
      "skan czyta jednostki po deduplikacji (5a).")
    A("")
    A(_table(["kier.", "od", "do", "wierszy", "meczów", "bias"],
             [[r["direction"], r["from"] or "początek", r["to"] or "koniec", r["rows"],
               r["matches"], _pp(r["bias"])] for r in ctx["row_level_corners_total"]]))
    A("")
    A("### 5c. „Próbka ≥ 10 pp nad progiem” — przybliżenie")
    A("")
    A("Tabela rozliczeń nie trzyma surowej częstości z próbki drużyny, tylko "
      "`p_central` (model po ściągnięciu). To więc przybliżenie: wiersze, gdzie "
      "`p_central − 1/kurs ≥ 0,10`, wszystkie szczeble, bez deduplikacji.")
    A("")
    A(_table(["rynek", "zakładów", "ROI"],
             [[p["market"], p["bets"], _pct(p["roi"])] for p in ctx["disagreement_proxy"]]))
    A("")
    A("### 5d. Złudzenie surowej średniej — komórki z najwyższym surowym biasem ponad próg")
    A("")
    A("To jest to, co widać bez ściągania i bez walidacji: najwyższe surowe średnie "
      "na małym n. Obok ta sama komórka po ściągnięciu.")
    A("")
    s0 = next((s for s in art["scans"] if s["grouping"] == "competition"), None)
    if s0:
        A(_table(["grupa", "rynek", "kier.", "meczów", "bias surowy", "próg",
                  "bias po ściągnięciu", "ROI in-sample"],
                 [[c["name"], c["market"], c["direction"], c["matches"], _pp(c["raw_bias"]),
                   _pp(c["hurdle"]), _pp(c["shrunk_bias"]), _pct(c["in_sample_roi"])]
                  for c in s0["raw_top"]]))
    A("")
    A(f"Marża Superbeta z par OVER/UNDER tej samej linii: {art['margin']['pairs']} par, "
      f"średnio {_pct(art['margin']['mean']).lstrip('+')}.")
    A("")

    A("## 6. Stabilność surowego wzorca ligi z `cache-calibration` (bez cen)")
    A("")
    cache = art.get("cache_describe")
    if cache is None:
        A("Nie liczone (`--no-cache-describe`). **Pominięte.**")
    elif not cache:
        A("Brak komórek ligowych na liście obserwacyjnej — nic do opisania.")
    else:
        A("Tylko opis: te wiersze nie mają ceny, więc nie mówią nic o tym, czy wzorzec "
          "jest wyceniony. Połowy to podział meczów wg id zdarzenia Sofascore "
          "(przybliżenie kolejności w czasie, nie daty).")
        A("")
        described = [c for c in cache if "mean" in c]
        thin = len(cache) - len(described)
        if described:
            A(_table(["liga", "rynek", "meczów", "średnia", "SD", "starsza połowa",
                      "nowsza połowa"],
                     [[c.get("name", c["competition_id"]), c["market"], c["matches"],
                       c["mean"], c["sd"], c["mean_older_half"], c["mean_newer_half"]]
                      for c in described]))
            A("")
        A(f"Bez opisu (< 10 meczów w `cache-calibration` — m.in. rynki połówkowe i "
          f"turnieje tenisowe): {thin} z {len(cache)} par (liga, rynek).")
    A("")

    A("## 7. Zastrzeżenia i czego nie sprawdzono")
    A("")
    A("- **Superbet może liczyć rożne inaczej niż Sofascore** (jeden zrzut: 7 wobec 6). "
      "Gdyby tak było, rozliczenie z Sofascore przesuwa rożne w stronę UNDER. "
      "**Niezmierzone** — dodatni bias UNDER na rożnych może być artefaktem liczenia.")
    A("- Wczesne odczyty Sofascore bywały błędne i zostały przeliczone "
      "(`regrade_settled.py`); raport czyta bazę po przeliczeniu.")
    A("- Kartki to punkty karne (booking points), nie liczba kartek.")
    A("- Tie-breaki meczowe w tenisie poprawione 2026-09-29 (afdb886f, 3fa56742, c16759b5).")
    A("- Tenis: `competition_id` to turniej, który trwa tydzień — komórki ligowe prawie "
      "się nie powtarzają; sensowne jest grupowanie kraj/poziom.")
    A("- Pominięte rynki (props zawodników, rynki łączone `both_over_`/`most_`/`handicap_`, "
      "oraz rodziny spoza zakresu): "
      f"{sum(d['skipped_markets'].values())} wierszy — lista w JSON (`data.skipped_markets`).")
    A(f"- Mecze bez `02_fixtures.json` (grupowanie kraj/poziom ich nie widzi): "
      f"{d['events_without_fixture']}.")
    rp = art.get("repriced_rows")
    if rp is not None:
        A(f"- `market_p` przeliczone z wydrukowanej pary OVER/UNDER (devig potęgowy "
          f"`devig_many`) dla każdej linii z obiema stronami; {rp} wierszy ruszyło się "
          "o > 0,5 pp — zapisane `market_p` pochodziło z innego odświeżenia oferty niż "
          "kurs. Wiersz jednostronny zostaje z zapisanym `market_p`.")
    A("- Dzień D-1 jest w treningu dnia D w całości; w praktyce rozlicza się go rano "
      "dnia D, a mecze D-1 kończą się najpóźniej w nocy — nakładanie się z meczami D "
      "jest znikome, ale nie jest zerowe. **Nie mierzone.**")
    A("- Ten sam mecz pod dwoma id zdarzenia byłby liczony jako dwa mecze "
      "(naprawione dla próbek 2026-09-27, tutaj nie sprawdzane).")
    A("- Wynik rozliczony to fakt o dniu, nie o decyzji. Ten raport jest dowodem, "
      "nie listą zakładów.")
    A("")
    return lines


# ---- section 7h of audit_settlement -----------------------------------------


def latest_artifact(reports_dir: Path, date: str) -> dict[str, Any] | None:
    """The newest scanner artifact whose window ends on or before `date`."""
    best: tuple[str, Path] | None = None
    for p in reports_dir.glob("sofa_nisze_*.json"):
        to = p.stem.removeprefix("sofa_nisze_")
        if to <= date and (best is None or to > best[0]):
            best = (to, p)
    if best is None:
        return None
    try:
        art: dict[str, Any] = json.loads(best[1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return art


def render_section(art: dict[str, Any] | None, heading: str) -> list[str]:
    """audit_settlement's 7h: the scanner's latest out-of-sample verdict.

    Separate from 7c (the coupon) and never pooled with it -
    the scanner bets nothing.
    """
    out = [heading, ""]
    if art is None:
        out += ["Brak danych — skaner nisz nie ma artefaktu (`reports/sofa_nisze_<data>.json`) "
                "z oknem kończącym się do tego dnia. Uruchom `audit_niches.py`.", ""]
        return out
    found = art.get("verdict") == "NISZA_ZNALEZIONA"
    out.append(f"Okno {art['from']} … {art['to']}: **{'NISZA ZNALEZIONA' if found else 'BRAK NISZY'}** "
               f"— kandydatów {len(art.get('candidates', []))}, BH na "
               f"{art['bh']['m']} komórkach (FDR {art['bh']['q']:.2f}). Pomiar, nie kupon; "
               "nie łączyć z 7c.")
    out.append("")
    rows = []
    for s in art.get("scans", []):
        h = s["headline"]
        rows.append([GROUPING_PL.get(s["grouping"], s["grouping"]), len(s["days_bet"]),
                     f"{h['selector']['bets']}", _pct(h["selector"]["roi"]),
                     _ci(h["selector"]["roi_ci95"]), _pct(h["baseline"]["roi"]),
                     _ci(h["baseline"]["roi_ci95"]), s["watch_total"]])
    out.append(_table(["grupowanie", "dni OOS", "zakł. selektora", "ROI selektora",
                       "95% CI", "ROI bazy", "95% CI bazy", "lista obserwacyjna"], rows))
    out.append("")
    out.append(f"Pełny raport: `reports/sofa_nisze_{art['to']}.md`.")
    out.append("")
    return out


# ---- main -------------------------------------------------------------------


def summary_line(art: dict[str, Any], status: str) -> str:
    comp = next((s for s in art.get("scans", []) if s["grouping"] == "competition"), None)
    head = comp["headline"] if comp else None
    return "SOFA_SUMMARY: " + json.dumps({
        "stage": STAGE, "status": status, "from": art.get("from"), "to": art.get("to"),
        "verdict": art.get("verdict"), "candidates": len(art.get("candidates", [])),
        "bh_m": art.get("bh", {}).get("m"),
        "selector_roi": head["selector"]["roi"] if head else None,
        "selector_bets": head["selector"]["bets"] if head else None,
        "baseline_roi": head["baseline"]["roi"] if head else None,
        "watch": sum(s["watch_total"] for s in art.get("scans", [])),
    })


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="date_from", required=True)
    ap.add_argument("--to", dest="date_to", required=True)
    ap.add_argument("--min-matches", type=int, default=MIN_TRAIN_MATCHES)
    ap.add_argument("--min-train-days", type=int, default=MIN_TRAIN_DAYS)
    ap.add_argument("--json", default=None, help="artifact path (default reports/sofa_nisze_<to>.json)")
    ap.add_argument("--out", default=None, help="report path (default reports/sofa_nisze_<to>.md)")
    ap.add_argument("--db-path", default=None)
    ap.add_argument("--runs-dir", default=None)
    ap.add_argument("--no-cache-describe", action="store_true",
                    help="skip the cache-calibration description (one full scan)")
    args = ap.parse_args(argv)

    config = SofaConfig.from_env()
    db_path = args.db_path or config.db_path
    runs_dir = Path(args.runs_dir or config.runs_dir)
    json_path = Path(args.json) if args.json else Path("reports") / f"sofa_nisze_{args.date_to}.json"
    md_path = Path(args.out) if args.out else Path("reports") / f"sofa_nisze_{args.date_to}.md"

    empty = {"from": args.date_from, "to": args.date_to, "verdict": "BRAK_DANYCH"}
    if not Path(db_path).exists():
        print(f"FAILED: no database at {db_path}")
        print(summary_line(empty, "FAILED"))
        return 2
    conn = connect_ro(db_path)
    try:
        rows = load_priced_rows(conn, args.date_from, args.date_to)
        if not rows:
            print(f"FAILED: no priced settled rows in {args.date_from}..{args.date_to}")
            print(summary_line(empty, "FAILED"))
            return 2
        fixtures = load_fixtures(runs_dir, sorted({r.day for r in rows}))
        art = build(rows, fixtures, args.date_from, args.date_to,
                    args.min_matches, args.min_train_days)
        if args.no_cache_describe:
            art["cache_describe"] = None
        else:
            cells = sorted({
                (int(c["group"].split(":", 1)[1]), c["market"])
                for s in art["scans"] if s["grouping"].startswith("competition")
                for c in s["watch"] + s["candidates"]
            })
            desc = describe_from_cache(conn, cells)
            names = group_names(fixtures)
            sport_of = {r.competition: r.sport for r in rows}
            for c in desc:
                sport = sport_of.get(c["competition_id"], "football")
                c["name"] = names.get(f"{sport}:{c['competition_id']}", str(c["competition_id"]))
            art["cache_describe"] = desc
    finally:
        conn.close()

    partial = (any(not s["days_bet"] for s in art["scans"])
               or art["data"]["events_without_fixture"] > 0)
    status = "PARTIAL" if partial else "OK"
    art["status"] = status
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(art, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(render(art)), encoding="utf-8")
    print(f"WROTE {md_path}")
    print(f"WROTE {json_path}")
    print(summary_line(art, status))
    return 1 if partial else 0


if __name__ == "__main__":
    raise SystemExit(main())
