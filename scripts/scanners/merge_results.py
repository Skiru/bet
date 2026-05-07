"""Merge per-sport scan results into unified scan_summary.json."""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE.parent / "src"))

from bet.db.connection import get_db
from bet.db.repositories import ScanResultRepo

DATA_DIR = BASE.parent / "betting" / "data"


def merge_scan_results(betting_date: str) -> Path:
    """Read all scan_results from DB and produce scan_summary.json.

    Output format matches current scan_events.py: {url_key: [list_of_event_dicts], ...}
    """
    with get_db() as conn:
        repo = ScanResultRepo(conn)
        results = repo.get_all_by_date(betting_date)

    # Group by source domain (matching current format)
    summary: dict[str, list[dict]] = {}
    for r in results:
        url_key = r.source_domain
        if url_key not in summary:
            summary[url_key] = []

        event = r.raw_data if isinstance(r.raw_data, dict) else {}
        # Ensure standard fields present
        event.setdefault("home", r.home_team)
        event.setdefault("away", r.away_team)
        event.setdefault("time", r.kickoff)
        event.setdefault("league", r.competition)
        event.setdefault("sport", r.sport)
        summary[url_key].append(event)

    out_path = DATA_DIR / "scan_summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def merge_scan_results_from_json(sport_outputs: dict[str, Path]) -> Path:
    """Fallback: merge from per-sport JSON files when DB unavailable."""
    summary: dict[str, list[dict]] = {}
    for sport, path in sport_outputs.items():
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            for url_key, events in data.items():
                if url_key not in summary:
                    summary[url_key] = []
                summary[url_key].extend(events)

    out_path = DATA_DIR / "scan_summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path
