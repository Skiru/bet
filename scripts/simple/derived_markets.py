#!/usr/bin/env python3
"""Read the comparative markets on Superbet's screen that the pipeline never sees.

    # one fixture, by Superbet's own event id (from the offer artifact)
    python3 scripts/simple/derived_markets.py --date 2026-09-05 --event 13527522

    # every football fixture the day matched, cheapest-first order
    python3 scripts/simple/derived_markets.py --date 2026-09-05 --all

    # re-read a screen already pulled, no network at all
    python3 scripts/simple/derived_markets.py --date 2026-09-05 \
        --event 13527522 --cache-dir /tmp/screens

Why this exists. ``superbet_offer.json`` keeps a market only if its name parses
as powyżej/poniżej, so an entire family -- "Liczba rzutów rożnych - H2H",
"Rzuty rożne handicap", "Najwięcej strzałów", "Najwięcej kartek", the per-half
variants, the range markets -- is invisible to every artifact this pipeline
writes. It is not filtered as unpriceable; it is never seen. On the nine
fixtures measured on 2026-09-05 all nine carried the corner H2H and the corner
handicap.

Two things come back from here and they are not the same thing:

* **A price comparison that needs no model.** The outsider's "+0.5" handicap and
  the three-way's "remis + outsider" pay on exactly the same event; on six of
  six fixtures carrying both, the handicap paid 7.5-10.6% more. That finding is
  arithmetic on two prices and is as certain as the prices are.
* **A probability from our own samples**, for the three metrics where an offline
  replay showed the estimate beats its own base rate -- corners, shots, shots on
  target -- and a refusal with a reason for the ones where it did not (cards,
  fouls, first halves). See ``bet.simple_stats.derived_markets``.

One HTTP GET per fixture against the same public prematch endpoint
``bet.api_clients.superbet`` already reads, and the response is ~4 MB, so
``--all`` over a full slate is 170 requests and 700 MB of traffic. Prefer
``--event``. Nothing here can place a bet, and no derived number may enter a
coupon: it has no tier, no ``p_low``, and no settled record against a price.

Exit codes: 0 = report printed, 2 = bad input or nothing to read.
"""
from __future__ import annotations

import argparse
import json
import mmap
import sys
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bet.api_clients.superbet import DEFAULT_BASE_URL, DEFAULT_LANG  # noqa: E402
from bet.simple_stats.derived_markets import (  # noqa: E402
    CALIBRATION,
    GATE,
    REFUSED,
    devig,
    estimate,
    handicap_versus_three_way,
    overround,
    range_from_ladder,
    required_price,
)

# Superbet's name for each comparison, per metric. Matched exactly rather than
# fuzzily: these strings are the only handle we have on the market, and a fuzzy
# match here would silently price "1. połowa - najwięcej rzutów rożnych" as the
# full-match market. The half variants are deliberately absent -- the replay
# refused them.
THREE_WAY = {
    "corners_for": ("Liczba rzutów rożnych - H2H",),
    "shots_for": ("Najwięcej strzałów",),
    "shots_on_target_for": ("Najwięcej celnych strzałów",),
}
HANDICAP = {
    "corners_for": ("Rzuty rożne handicap",),
    "shots_on_target_for": ("Liczba celnych strzałów - handicap",),
}
# Comparisons Superbet posts that we deliberately do not price. Listed so the
# report can say "offered, refused, here is why" instead of staying silent.
# The range markets and the over/under ladder they repartition. Same quantity,
# same fixture, two ways of selling it -- so the ladder prices the range exactly
# and any difference is margin.
RANGE_AGAINST_LADDER = {
    "Liczba rzutów rożnych - przedziały": "Liczba rzutów rożnych",
    "Liczba kartek - przedziały": "Liczba kartek",
}

POSTED_BUT_REFUSED = {
    "Najwięcej kartek": "cards_for",
    "Liczba kartek - handicap": "cards_for",
    "1. połowa - najwięcej rzutów rożnych": "corners_1h_for",
    "2. połowa - najwięcej rzutów rożnych": "corners_1h_for",
    "1. połowa - rzuty rożne - handicap": "corners_1h_for",
    "2. połowa - rzuty rożne - handicap": "corners_1h_for",
    "1. połowa - najwięcej kartek": "cards_for",
    "2. połowa - najwięcej kartek": "cards_for",
}


def fetch_screen(event_id: str, cache_dir: Path | None) -> dict[str, Any]:
    """The full market list for one fixture: cache first, then one GET."""
    cached = (cache_dir / f"{event_id}.json") if cache_dir else None
    if cached and cached.exists():
        return json.loads(cached.read_text())
    url = f"{DEFAULT_BASE_URL}/v2/{DEFAULT_LANG}/events/{event_id}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=40) as response:  # noqa: S310
        payload = json.loads(response.read().decode())
    if cached:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(payload))
    return payload


def pull_dossier(path: Path, event_id: str) -> dict[str, Any] | None:
    """One dossier out of a 200 MB file, without loading the file.

    ``json.load`` on the 2026-09-05 dossier costs about 2 GB of RSS and twenty
    seconds; this is 0.13s and a few kilobytes. Brace matching rather than a
    line heuristic because the artifact's indentation is not part of its
    contract, and string-skipping because a team name may contain a brace.
    """
    needle = f'"event_id": "{event_id}"'.encode()
    with path.open("rb") as handle:
        blob = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        at = blob.find(needle)
        if at < 0:
            return None
        start = blob.rfind(b"{", 0, at)
        depth = 0
        cursor = start
        while True:
            char = blob[cursor : cursor + 1]
            if char == b'"':
                cursor += 1
                while (
                    blob[cursor : cursor + 1] != b'"'
                    or blob[cursor - 1 : cursor] == b"\\"
                ):
                    cursor += 1
            elif char == b"{":
                depth += 1
            elif char == b"}":
                depth -= 1
                if depth == 0:
                    break
            cursor += 1
        return json.loads(blob[start : cursor + 1].decode())


def _prices(odds: Iterable[dict], market: str) -> dict[str, float]:
    return {
        str(o.get("name")): float(o["price"])
        for o in odds
        if o.get("marketName") == market
        and o.get("price")
        and str(o.get("status")) == "active"
    }


def _handicap_plus_half(odds: Iterable[dict], market: str, team: str) -> float | None:
    """The price of ``team`` receiving +0.5 on this handicap ladder.

    Matched on the team's own name and the sign printed beside it, never on
    ``specialBetValue``. That field is the handicap applied to the **home**
    side, so a fixture quotes the same rung twice under opposite signs --
    Newcastle-Bournemouth 2026-09-05 carried ``sbv=-0.5`` (Newcastle -0.5,
    Bournemouth +0.5) *and* ``sbv=0.5`` (Newcastle +0.5, Bournemouth -0.5).
    Reading the sign of ``sbv`` as "favourite versus outsider" therefore means
    reading it as "home versus away", which is right only while the home side
    happens to be the favourite. It was, on all nine fixtures this was first
    measured on, which is exactly how a bug like that survives a demo.
    """
    for o in odds:
        if o.get("marketName") != market or str(o.get("status")) != "active":
            continue
        name = str(o.get("name"))
        if name.strip() == f"{team} (0.5)":
            return float(o["price"])
    return None


# Superbet writes the drawn outcome four ways inside this one family --
# "remis" on the corner H2H, "Remis" on most shots, "X" on cards, "żadna" on the
# race markets -- and the three were found by reading three fixtures, so treat
# this set as incomplete rather than as the vocabulary.
_DRAW_NAMES = {"remis", "x", "żadna", "zadna"}


def _three_way_sides(
    prices: dict[str, float], home: str, away: str
) -> tuple[float, float, float] | None:
    """(home, draw, away) out of Superbet's several spellings of the same three.

    Order matters and cannot be recovered from the prices: the favourite is not
    always the home side. So the two named outcomes are matched to the club
    names first, and the positional "1"/"2" fallback is used only when neither
    name appears -- never the other way round.
    """
    draw_key = next((k for k in prices if k.strip().lower() in _DRAW_NAMES), None)
    if draw_key is None:
        return None
    draw = prices[draw_key]
    home_price = prices.get(home) or prices.get("1")
    away_price = prices.get(away) or prices.get("2")
    if home_price is None or away_price is None:
        rest = [k for k in prices if k != draw_key]
        if len(rest) != 2:
            return None
        home_price, away_price = prices[rest[0]], prices[rest[1]]
    return (home_price, draw, away_price)


def report_fixture(screen: dict, dossier: dict | None, home: str, away: str) -> None:
    odds = screen["data"][0].get("odds") or []
    print(f"\n### {home} - {away}")

    for metric, names in THREE_WAY.items():
        cal = CALIBRATION[metric]
        market = next(
            (n for n in names if any(o.get("marketName") == n for o in odds)), None
        )
        est = None
        if dossier:
            observation = (dossier.get("metrics") or {}).get(metric) or {}
            est = estimate(
                metric,
                [v["value"] for v in observation.get("team_a_l10") or []],
                [v["value"] for v in observation.get("team_b_l10") or []],
            )
        if market is None:
            print(f"  {metric}: rynek porównawczy nieobecny na tym meczu")
            continue
        sides = _three_way_sides(_prices(odds, market), home, away)
        if sides is None:
            print(
                f"  {metric}: {market} obecny,"
                " ale nie dał się rozczytać na trzy strony"
            )
            continue
        book = devig(sides)
        print(f"  {metric}  [{market}]")
        print(
            f"     kurs {sides[0]}/{sides[1]}/{sides[2]}"
            f"  marża {overround(sides) * 100:.1f}%"
            f"   po odjęciu marży: {book[0]:.3f} / {book[1]:.3f} / {book[2]:.3f}"
        )
        if est is None or est.verdict != "USABLE":
            why = est.reason if est else "brak dossier"
            print(f"     nasz szacunek: BRAK - {why}")
        else:
            p = est.probabilities
            print(
                f"     próbka {est.mean_home:.1f} vs {est.mean_away:.1f}"
                f" (n={est.n_home}/{est.n_away})"
                f"  ->  {p[0]:.3f} / {p[1]:.3f} / {p[2]:.3f}"
            )
            side = 0 if est.called_side == "home" else 2
            gap = p[side] - book[side]
            flag = "PEWNY" if est.confident else f"poniżej bramki {GATE}"
            print(
                f"     typ: {'gospodarz' if side == 0 else 'gość'}  {flag}"
                f"  różnica wobec książki {gap:+.3f}"
            )
            if min(est.n_home, est.n_away) < 8:
                print(
                    f"     UWAGA: najcieńsza strona ma n={min(est.n_home, est.n_away)}."
                    " Kupon wymaga n>=8 nawet na CALL - to jest cieńsze"
                    " niż cokolwiek, co trafia na arkusz."
                )
            # Price last, and against the bottom of the measured interval rather
            # than the point estimate. The gate's hit rate was chosen on the same
            # data it is quoted from, so the point estimate is the optimistic end
            # and the CI floor is the number a bet should have to clear.
            if est.confident and cal.price_floor:
                floor = cal.price_floor
                offered = sides[side]
                needed = required_price(floor)
                verdict = "WARTE CENY" if offered >= needed else "NIE WARTE"
                print(
                    f"     cena: oferowana {offered}  wymagana {needed:.2f}"
                    f"  (dolna granica przedziału {floor:.3f}, marża 1.05)"
                    f"  ->  {verdict}"
                )
                if offered < needed:
                    print(
                        f"     na punkcie centralnym {p[side]:.3f}"
                        f" wystarczyłoby {required_price(p[side]):.2f} - różnica"
                        " między tymi dwiema liczbami to cała niepewność"
                        " tego estymatora."
                    )

        for hcp_name in HANDICAP.get(metric, ()):
            # Both sides, not just the outsider: "covers +0.5" is the same event
            # as "wins or draws" whichever side you are on, so the comparison is
            # available twice per fixture and the two need not agree.
            if not any(o.get("marketName") == hcp_name for o in odds):
                continue
            found = False
            for label, team, own, other in (
                ("gospodarz", home, sides[0], sides[2]),
                ("gość", away, sides[2], sides[0]),
            ):
                plus_half = _handicap_plus_half(odds, hcp_name, team)
                if plus_half is None:
                    continue
                found = True
                gapinfo = handicap_versus_three_way(
                    favourite_price=other,
                    draw_price=sides[1],
                    outsider_price=own,
                    handicap_outsider_price=plus_half,
                )
                print(
                    f"     [{hcp_name}] {label} +0.5 dwoma drogami:"
                    f" handicap = {gapinfo.direct_price}"
                    f"  vs  remis+{label} = {gapinfo.synthetic_price:.3f}"
                    f"   ({gapinfo.gain * 100:+.1f}% za identyczne zdarzenie)"
                )
            if not found:
                # The market is on the board but not at the rung that maps onto
                # the H2H. Said out loud, because a silent absence here reads
                # exactly like a comparison that came out level.
                print(
                    f"     [{hcp_name}] obecny, ale bez szczebla ±0.5"
                    " - porównanie z H2H niedostępne na tym meczu"
                )

    report_ranges(odds)

    posted = sorted({o.get("marketName") for o in odds} & set(POSTED_BUT_REFUSED))
    if posted:
        print("  wystawione, świadomie nie wyceniane:")
        for name in posted:
            print(f"     {name} -> {REFUSED[POSTED_BUT_REFUSED[name]].splitlines()[0]}")


def _bucket_rungs(label: str) -> tuple[float | None, float | None, int]:
    """Which ladder rungs a range bucket is made of, and which slice to read.

    Superbet writes the buckets in whole events ("<9", "9-11", "12+") and quotes
    the ladder on half lines, so "<9" *is* "poniżej 8.5". Returned in the terms
    ``range_from_ladder`` takes -- (lower under-line, upper under-line) -- plus
    the index of the slice this bucket corresponds to, because the three buckets
    read three different outputs of the same call:

        "<9"    -> (8.5, None),  slice 0   = P(under 8.5)
        "9-11"  -> (8.5, 11.5),  slice 1   = P(under 11.5) - P(under 8.5)
        "12+"   -> (None, 11.5), slice 2   = 1 - P(under 11.5)
    """
    text = label.strip()
    if text.startswith("<"):
        return (float(text[1:]) - 0.5, None, 0)
    if text.endswith("+"):
        return (None, float(text[:-1]) - 0.5, 2)
    if "-" in text:
        low, high = text.split("-", 1)
        return (float(low) - 0.5, float(high) + 0.5, 1)
    return (None, None, 1)


def report_ranges(odds: list[dict]) -> None:
    """Price each range bucket off the over/under ladder that already covers it."""
    for range_market, ladder_market in RANGE_AGAINST_LADDER.items():
        buckets = _prices(odds, range_market)
        if not buckets:
            continue
        # Both sides of every rung, because the bucket probabilities are
        # differences of devigged numbers and a one-sided read would compare a
        # vigged quantity with a vigged quantity.
        rungs: dict[float, dict[str, float]] = {}
        for o in odds:
            if o.get("marketName") != ladder_market or str(o.get("status")) != "active":
                continue
            if o.get("specialBetValue") is None:
                continue
            name = str(o.get("name", ""))
            side = "under" if name.startswith("poniżej") else (
                "over" if name.startswith("powyżej") else None
            )
            if side is None:
                continue
            rungs.setdefault(float(o["specialBetValue"]), {})[side] = float(o["price"])
        pairs = {
            line: (sides["under"], sides["over"])
            for line, sides in rungs.items()
            if "under" in sides and "over" in sides
        }
        if not pairs:
            print(
                f"  [{range_market}] wystawiony, ale drabina {ladder_market}"
                " nie ma ani jednego szczebla wycenionego obustronnie"
            )
            continue
        overround_here = sum(1.0 / price for price in buckets.values()) - 1.0
        print(
            f"  [{range_market}] wobec drabiny {ladder_market}"
            f"   (marża samego rynku przedziałów {overround_here * 100:.1f}%)"
        )
        for label, offered in buckets.items():
            low_line, high_line, slice_index = _bucket_rungs(label)
            implied = range_from_ladder(
                under_low=pairs.get(low_line) if low_line is not None else None,
                under_high=pairs.get(high_line) if high_line is not None else None,
            )[slice_index]
            if implied is None or implied <= 0:
                print(
                    f"     {label:6s} {offered:6.2f}"
                    "   drabina nie ma szczebla, który go domyka"
                )
                continue
            fair = 1.0 / implied
            print(
                f"     {label:6s} {offered:6.2f}   uczciwa z drabiny {fair:6.2f}"
                f"   ({offered * implied - 1:+.1%})"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--date", required=True)
    parser.add_argument(
        "--event", action="append", default=[], help="Superbet event id; repeatable"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="every matched football fixture (one GET each)",
    )
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--runs-dir", type=Path, default=ROOT / "runs")
    args = parser.parse_args(argv)

    base = args.runs_dir / args.date
    offer_path = base / f"{args.date}_superbet_offer.json"
    dossier_path = base / f"{args.date}_event_dossiers.json"
    if not offer_path.exists():
        print(f"brak artefaktu oferty: {offer_path}", file=sys.stderr)
        return 2

    offer = json.loads(offer_path.read_text())
    matched = {
        str(e["superbet_event_id"]): e
        for e in offer["events"]
        if e.get("event_id") and e.get("sport") == "football"
    }
    by_size = sorted(matched, key=lambda k: -(matched[k].get("market_count") or 0))
    wanted = args.event or (by_size if args.all else [])
    if not wanted:
        print("podaj --event <id> albo --all", file=sys.stderr)
        return 2

    for event_id in wanted:
        entry = matched.get(str(event_id))
        if entry is None:
            print(
                f"\n### {event_id}: nie ma go wśród sparowanych"
                " meczów piłkarskich tego dnia"
            )
            continue
        try:
            screen = fetch_screen(str(event_id), args.cache_dir)
        except Exception as exc:  # noqa: BLE001 - a dead host is a report line, not a crash
            print(
                f"\n### {entry['superbet_match_name']}:"
                f" nie udało się pobrać ekranu ({exc})"
            )
            continue
        home, away = (part.strip() for part in entry["superbet_match_name"].split("·"))
        dossier = (
            pull_dossier(dossier_path, entry["event_id"])
            if dossier_path.exists()
            else None
        )
        report_fixture(screen, dossier, home, away)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
