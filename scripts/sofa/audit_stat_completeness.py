"""AUDIT - which cached /statistics are frozen in a broken state (football, tennis).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_stat_completeness.py
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_stat_completeness.py \
        --date 2026-09-27 --probe 20

Reads sofa_event_stats and the cached listings (read-only), judges every
cached match against the norm of its own group (see bet.sofa.stat_completeness)
and writes reports/sofa_kompletnosc_statystyk_<today>.{md,json}.

  --date D    also say which of D's SETTLE skips sit on a broken match - those
              rows are gradable once the match is re-fetched.
  --probe N   re-ask Sofascore, through the bridge, for N broken + fresh
              matches and count how many now carry what their group expects.
              Nothing is written to the cache. Off by default: it is live
              traffic to a third party.

Exit 0 when nothing fresh is broken, 1 when something is (a re-fetch would
recover it), 2 on a failure to read the cache.
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.config import SofaConfig
from bet.sofa.stat_completeness import (
    BROKEN,
    FRESH_HOURS,
    CachedStats,
    EventMeta,
    Finding,
    build_norms,
    classify,
    event_meta,
    parse_statistics,
)

SPORTS = ("football", "tennis")


def load_meta(conn: sqlite3.Connection) -> dict[int, EventMeta]:
    meta: dict[int, EventMeta] = {}
    for (events_json,) in conn.execute("SELECT events_json FROM sofa_entity_events"):
        try:
            events = json.loads(events_json).get("events", [])
        except ValueError:
            continue
        for event in events:
            eid = event.get("id")
            if not isinstance(eid, int) or eid in meta:
                continue
            m = event_meta(event)
            if m is not None and m.sport in SPORTS:
                meta[eid] = m
    return meta


def load_stats(conn: sqlite3.Connection) -> list[CachedStats]:
    out: list[CachedStats] = []
    for eid, fetched_at, statistics_json in conn.execute(
        "SELECT sofascore_event_id, fetched_at, statistics_json FROM sofa_event_stats"
        " WHERE status_type = 'finished'"
    ):
        keys, periods = parse_statistics(statistics_json)
        fetched = datetime.fromisoformat(fetched_at)
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=UTC)
        out.append(CachedStats(int(eid), fetched.timestamp(), keys, periods))
    return out


def probe(findings: list[Finding], n: int, config: SofaConfig) -> list[dict[str, Any]]:
    """Re-ask Sofascore for n broken, fresh matches. Nothing is cached."""
    from bet.sofa.client import SofascoreClient

    pool = [f for f in findings if f.verdict in BROKEN and f.fresh]
    random.Random(0).shuffle(pool)
    client = SofascoreClient(config)
    now = datetime.now(UTC).timestamp()
    results: list[dict[str, Any]] = []
    for f in pool[:n]:
        body = client.event_statistics(f.event_id)
        keys, periods = parse_statistics(json.dumps(body) if body else None)
        # Recovered means it now carries what it lacked - and something at all.
        recovered = (
            bool(keys)
            and set(f.missing_keys) <= keys
            and set(f.missing_periods) <= periods
        )
        results.append(
            {
                "event_id": f.event_id,
                "sport": f.sport,
                "group": f.group_name,
                "verdict": f.verdict,
                "missing_keys": list(f.missing_keys),
                "age_days_now": None
                if f.start_ts is None
                else round((now - f.start_ts) / 86400.0, 1),
                "keys_now": len(keys),
                "recovered": recovered,
            }
        )
    return results


def settle_skips(date: str, by_id: dict[int, Finding]) -> dict[str, Any] | None:
    path = Path("runs/sofa") / date / "07_settle_skips.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    events = data.get("skipped_events", [])
    stat_gaps = [
        e for e in events if any(":" in reason for reason in (e.get("skipped") or {}))
    ]
    broken = [
        e
        for e in stat_gaps
        if by_id.get(e["sofascore_event_id"], None)
        and by_id[e["sofascore_event_id"]].verdict in BROKEN
    ]
    rows = sum(
        n
        for e in broken
        for reason, n in (e.get("skipped") or {}).items()
        if ":" in reason
    )
    return {
        "date": date,
        "events_with_stat_gap_skips": len(stat_gaps),
        "of_them_broken_in_cache": len(broken),
        "stat_gap_rows_on_broken_events": rows,
        "events": [
            {
                "event_id": e["sofascore_event_id"],
                "match": f"{e.get('home_name', '')} - {e.get('away_name', '')}",
                "verdict": by_id[e["sofascore_event_id"]].verdict,
                "skipped": e.get("skipped"),
            }
            for e in broken
        ],
    }


def lag_bucket(f: Finding) -> str:
    h = f.lag_hours
    if h is None:
        return "?"
    return (
        "<24h"
        if h < 24
        else "24-72h"
        if h < FRESH_HOURS
        else "3-7d"
        if h < 168
        else ">7d"
    )


def render(
    findings: list[Finding],
    skips: dict[str, Any] | None,
    probed: list[dict[str, Any]] | None,
    today: str,
) -> str:
    lines = [
        f"# Kompletność statystyk w cache — {today}",
        "",
        "Każdy zakończony mecz z `sofa_event_stats` porównany z normą własnej grupy "
        "(piłka: rozgrywki, tenis: kategoria). Norma to klucze, które ma co najmniej "
        "połowa niepustych meczów grupy. `PARTIAL_*` i `EMPTY_IN_COVERED` to stan "
        "popsuty; świeże (pobrane < 72 h po starcie) najpewniej odzyska ponowne "
        "pobranie — Sofascore dosyła pełne statystyki niższych lig po kilku dniach.",
        "",
        "Ograniczenie: jeśli w grupie większość meczów zamarzła wcześnie, norma sama "
        "jest zaniżona i audyt tego nie zobaczy — liczby poniżej są dolną granicą.",
        "",
    ]
    for sport in SPORTS:
        mine = [f for f in findings if f.sport == sport]
        if not mine:
            continue
        verdicts = Counter(f.verdict for f in mine)
        lines += [
            f"## {sport}",
            "",
            "| werdykt | meczów | <24h | 24-72h | 3-7d | >7d | ? |",
            "|---|---|---|---|---|---|---|",
        ]
        for verdict, n in verdicts.most_common():
            lags = Counter(lag_bucket(f) for f in mine if f.verdict == verdict)
            lines.append(
                f"| {verdict} | {n} | "
                + " | ".join(
                    str(lags[b]) for b in ("<24h", "24-72h", "3-7d", ">7d", "?")
                )
                + " |"
            )
        broken = [f for f in mine if f.verdict in BROKEN]
        fresh = [f for f in broken if f.fresh]
        lines += [
            "",
            f"Popsutych: **{len(broken)}**, z tego świeżych (do odzyskania): "
            f"**{len(fresh)}**.",
            "",
        ]
        by_group: dict[str, list[Finding]] = defaultdict(list)
        for f in broken:
            by_group[f.group_name].append(f)
        if by_group:
            lines += [
                "Najwięcej popsutych — grupy:",
                "",
                "| grupa | popsutych | świeżych | brakuje najczęściej |",
                "|---|---|---|---|",
            ]
            for name, fs in sorted(by_group.items(), key=lambda kv: -len(kv[1]))[:15]:
                missing = Counter(k for f in fs for k in f.missing_keys).most_common(3)
                lines.append(
                    f"| {name} | {len(fs)} | {sum(f.fresh for f in fs)} | "
                    + ", ".join(k for k, _ in missing)
                    + " |"
                )
            lines.append("")
    if skips is not None:
        lines += [
            f"## Rozliczenie {skips['date']}",
            "",
            "Meczów z pominięciami z braku statystyki: "
            f"{skips['events_with_stat_gap_skips']}; z tego popsutych w cache: "
            f"**{skips['of_them_broken_in_cache']}** "
            f"({skips['stat_gap_rows_on_broken_events']} wierszy do rozliczenia "
            "po ponownym pobraniu).",
            "",
        ]
    if probed is not None:
        ok = sum(p["recovered"] for p in probed)
        lines += [
            "## Próba na żywo",
            "",
            f"Ponownie zapytane: {len(probed)}, "
            f"ma teraz to, czego brakowało: **{ok}**. "
            "Nic nie zapisano do cache.",
            "",
        ]
    lines.append(
        "Audyt tylko czyta. Niczego nie naprawia i nie pobiera ponownie do cache."
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD: cross with that day's SETTLE skips")
    parser.add_argument(
        "--probe",
        type=int,
        default=0,
        help="live re-check N broken+fresh matches via the bridge",
    )
    parser.add_argument("--out-dir", default="reports")
    args = parser.parse_args()

    config = SofaConfig.from_env()
    try:
        conn = sqlite3.connect(f"file:{config.db_path}?mode=ro", uri=True)
        meta = load_meta(conn)
        stats = load_stats(conn)
        conn.close()
    except sqlite3.Error as exc:
        print(f"FAILED reading the cache: {exc}", file=sys.stderr)
        return 2

    norms = build_norms(stats, meta)
    findings = [
        classify(
            s,
            meta.get(s.event_id),
            norms.get((meta[s.event_id].sport, meta[s.event_id].group_id))
            if s.event_id in meta
            else None,
        )
        for s in stats
    ]
    by_id = {f.event_id: f for f in findings}
    skips = settle_skips(args.date, by_id) if args.date else None
    probed = probe(findings, args.probe, config) if args.probe > 0 else None

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"sofa_kompletnosc_statystyk_{today}.md").write_text(
        render(findings, skips, probed, today)
    )
    broken = [f for f in findings if f.verdict in BROKEN]
    (out / f"sofa_kompletnosc_statystyk_{today}.json").write_text(
        json.dumps(
            {
                "generated_at_utc": datetime.now(UTC).isoformat(),
                "counts": {
                    s: dict(Counter(f.verdict for f in findings if f.sport == s))
                    for s in (*SPORTS, "unknown")
                },
                "broken": [
                    {
                        "event_id": f.event_id,
                        "sport": f.sport,
                        "group": f.group_name,
                        "verdict": f.verdict,
                        "missing_keys": list(f.missing_keys),
                        "missing_periods": list(f.missing_periods),
                        "lag_hours": None
                        if f.lag_hours is None
                        else round(f.lag_hours, 1),
                        "fresh": f.fresh,
                    }
                    for f in broken
                ],
                "settle": skips,
                "probe": probed,
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n"
    )

    fresh = sum(f.fresh for f in broken)
    summary = {
        "stage": "AUDIT_STAT_COMPLETENESS",
        "verdict": "PARTIAL" if fresh else "OK",
        "metrics": {
            "cached_finished": len(stats),
            "broken": {s: sum(f.sport == s for f in broken) for s in SPORTS},
            "broken_fresh": {
                s: sum(f.sport == s and f.fresh for f in broken) for s in SPORTS
            },
            "settle_rows_recoverable": skips["stat_gap_rows_on_broken_events"]
            if skips
            else None,
            "probe_recovered": (sum(p["recovered"] for p in probed), len(probed))
            if probed is not None
            else None,
        },
        "output_path": str(out / f"sofa_kompletnosc_statystyk_{today}.md"),
    }
    print("SOFA_SUMMARY: " + json.dumps(summary))
    return 1 if fresh else 0


if __name__ == "__main__":
    sys.exit(main())
