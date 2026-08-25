"""Storage helpers for tipster scraper v2 artifacts.

The bundle writes JSON artifacts by default and can optionally persist to a
SQLite database that mirrors the existing pipeline tables without making the
pipeline depend on live scraping during tests.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .claim import classify_claim
from .contracts import ExtractionResult, TipsterPick
from .pipeline_adapter import consensus_from_picks, to_legacy_pick

# The claim_* columns record what bet.tipsters.claim made of each pick. Without
# them the strict classification would exist only in today's artifact, and the
# question this whole column is for -- does public agreement predict anything --
# needs a history that can be queried without re-parsing Polish free text months
# later. match_date is separate from extracted_at_utc so a pick can be
# attributed to a betting day rather than to the moment we happened to fetch it.
TIPSTER_PICK_COLUMNS = [
    "source_id", "source_name", "sport", "event", "home_team", "away_team",
    "market", "market_family", "direction", "line", "odds_decimal",
    "confidence_label", "reasoning", "stats_cited_json", "valuable_signals_json",
    "source_url", "extracted_at_utc", "extraction_quality", "warnings_json",
    "source_record_type", "pipeline_use_json",
    "tipster_name", "match_date", "kickoff_time", "is_combo", "is_settled",
    "tipster_accuracy_pct", "tipster_bet_count", "source_ref",
    "claim_market", "claim_line", "claim_direction", "claim_countable",
    "claim_reject_reason",
]


def _blocked_entry(result: ExtractionResult) -> dict:
    return {
        "source_id": result.source_id,
        "reason": result.block_reason,
        "url": result.url,
        "fallback": result.fallback or "fixture_snapshot_only",
        "live_fetch_allowed": False,
    }


def _skipped_entry(result: ExtractionResult) -> dict:
    entry = {
        "source_id": result.source_id,
        "reason": result.skip_reason,
    }
    if result.required_flags_missing:
        entry["required_flags_missing"] = result.required_flags_missing
    if result.invalid_attestation:
        entry["invalid_attestation"] = result.invalid_attestation
    return entry


def build_payload(results: list[ExtractionResult]) -> dict:
    picks = [p for r in results for p in r.picks]
    blocked_sources = [_blocked_entry(r) for r in results if r.block_reason]
    skipped_sources = [_skipped_entry(r) for r in results if r.skip_reason]
    sources_with_picks = len({r.source_id for r in results if r.pick_count > 0})
    active_results = [r for r in results if not r.block_reason and not r.skip_reason and r.live_fetch_allowed]
    return {
        "schema_version": "tipster_consensus_v2.3",
        "contract": "evidence_only_not_betting_decision",
        "sources": [r.to_dict() for r in results],
        "total_picks": len(picks),
        "sources_with_picks": sources_with_picks,
        "all_picks": [to_legacy_pick(p) for p in picks],
        "consensus": consensus_from_picks(picks),
        "blocked_sources": blocked_sources,
        "skipped_sources": skipped_sources,
        "pipeline_consumers": ["S3 contextual cross-check", "S4 market sanity", "manual Superbet quote review"],
        "fail_closed": len(picks) == 0 or (bool(results) and not active_results),
    }


def write_json_artifact(results: list[ExtractionResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_payload(results), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def init_sqlite(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tipster_picks_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            source_name TEXT NOT NULL,
            sport TEXT NOT NULL,
            event TEXT NOT NULL,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            market TEXT NOT NULL,
            market_family TEXT NOT NULL,
            direction TEXT NOT NULL,
            line REAL,
            odds_decimal REAL,
            confidence_label TEXT NOT NULL,
            reasoning TEXT,
            stats_cited_json TEXT NOT NULL,
            valuable_signals_json TEXT NOT NULL,
            source_url TEXT,
            extracted_at_utc TEXT NOT NULL,
            extraction_quality REAL NOT NULL,
            warnings_json TEXT NOT NULL,
            source_record_type TEXT NOT NULL,
            pipeline_use_json TEXT NOT NULL,
            tipster_name TEXT,
            match_date TEXT,
            kickoff_time TEXT,
            is_combo INTEGER NOT NULL DEFAULT 0,
            is_settled INTEGER NOT NULL DEFAULT 0,
            tipster_accuracy_pct INTEGER,
            tipster_bet_count INTEGER,
            source_ref TEXT,
            claim_market TEXT,
            claim_line REAL,
            claim_direction TEXT,
            claim_countable INTEGER NOT NULL DEFAULT 0,
            claim_reject_reason TEXT,
            -- source_ref is the source's own per-bet id (ZawodTyper's
            -- comment_id). Keyed on rather than the market text so two tipsters
            -- posting the same claim on the same fixture stay two rows: they are
            -- two opinions, and collapsing them is what made the old consensus
            -- denominator always 1.
            UNIQUE(source_id, source_ref, home_team, away_team, market, extracted_at_utc)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tipster_consensus_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT NOT NULL,
            sport TEXT NOT NULL,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            consensus_market TEXT NOT NULL,
            consensus_direction TEXT NOT NULL,
            total_tipsters INTEGER NOT NULL,
            agreement_pct REAL NOT NULL,
            avg_extraction_quality REAL NOT NULL,
            payload_json TEXT NOT NULL,
            created_at_utc TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    _add_missing_columns(conn)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tipster_picks_v2_event ON tipster_picks_v2(sport, home_team, away_team)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tipster_picks_v2_market ON tipster_picks_v2(market_family, direction)")
    # The two queries this table exists to answer: "what did tipsters say about
    # this betting day" and "did the countable claims turn out to be right".
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tipster_picks_v2_date ON tipster_picks_v2(match_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tipster_picks_v2_claim ON tipster_picks_v2(claim_countable, claim_market, claim_line)")


# Columns added after the table's first release, with the type each needs. A
# CREATE TABLE IF NOT EXISTS is a no-op against an existing table, so a database
# created by the earlier schema would keep its old column set and every insert
# would fail on arity. Adding them one at a time is idempotent and cheap.
_LATE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("tipster_name", "TEXT"),
    ("match_date", "TEXT"),
    ("kickoff_time", "TEXT"),
    ("is_combo", "INTEGER NOT NULL DEFAULT 0"),
    ("is_settled", "INTEGER NOT NULL DEFAULT 0"),
    ("tipster_accuracy_pct", "INTEGER"),
    ("tipster_bet_count", "INTEGER"),
    ("source_ref", "TEXT"),
    ("claim_market", "TEXT"),
    ("claim_line", "REAL"),
    ("claim_direction", "TEXT"),
    ("claim_countable", "INTEGER NOT NULL DEFAULT 0"),
    ("claim_reject_reason", "TEXT"),
)


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    """Bring a pre-existing tipster_picks_v2 up to the current column set.

    Only additive: the UNIQUE constraint cannot be altered in place, so a table
    created by the old schema keeps keying on (source_id, source_url, ...)
    instead of source_ref. That is a weaker duplicate guard, not a wrong one --
    extracted_at_utc differs per run either way -- and it is not worth rebuilding
    a table for.
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(tipster_picks_v2)")}
    if not existing:
        return
    for name, decl in _LATE_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE tipster_picks_v2 ADD COLUMN {name} {decl}")


def _pick_row(p: TipsterPick) -> tuple:
    claim = classify_claim(p.market, p.home_team, p.away_team)
    return (
        p.source_id, p.source_name, p.sport, p.event, p.home_team, p.away_team,
        p.market, p.market_family, p.direction, p.line, p.odds_decimal,
        p.confidence_label, p.reasoning, json.dumps(p.stats_cited, ensure_ascii=False),
        json.dumps(p.valuable_signals, ensure_ascii=False), p.source_url,
        p.extracted_at_utc, p.extraction_quality, json.dumps(p.warnings, ensure_ascii=False),
        p.source_record_type, json.dumps(p.pipeline_use, ensure_ascii=False),
        p.tipster_name, p.match_date, p.kickoff_time, int(p.is_combo), int(p.is_settled),
        p.tipster_accuracy_pct, p.tipster_bet_count, p.source_ref,
        claim.market, claim.line, claim.direction,
        int(claim.countable and not p.is_combo),
        claim.reject_reason or ("combo_bet_legs_not_separable" if p.is_combo else ""),
    )


def persist_sqlite(results: list[ExtractionResult], db_path: Path) -> dict[str, int]:
    picks = [p for r in results for p in r.picks]
    consensus = consensus_from_picks(picks)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        init_sqlite(conn)
        conn.executemany(
            f"""
            INSERT OR IGNORE INTO tipster_picks_v2 ({','.join(TIPSTER_PICK_COLUMNS)})
            VALUES ({','.join('?' for _ in TIPSTER_PICK_COLUMNS)})
            """,
            [_pick_row(p) for p in picks],
        )
        conn.executemany(
            """
            INSERT INTO tipster_consensus_v2 (
                event, sport, home_team, away_team, consensus_market, consensus_direction,
                total_tipsters, agreement_pct, avg_extraction_quality, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["event"], row["sport"], row["home_team"], row["away_team"],
                    row["consensus_market"], row["consensus_direction"], row["total_tipsters"],
                    row["agreement_pct"], row["avg_extraction_quality"],
                    json.dumps(row, ensure_ascii=False),
                )
                for row in consensus
            ],
        )
        conn.commit()
    return {"picks": len(picks), "consensus": len(consensus)}
