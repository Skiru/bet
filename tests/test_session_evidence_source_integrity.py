from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SESSION_RUN_ID = os.environ.get("SUPERBET_SESSION_RUN_ID", "FULL_DAY_SESSION_20260702_SUPERBET_B")
SESSION_ROOT = ROOT / "reports" / "pipeline_runs" / SESSION_RUN_ID

FORBIDDEN_SESSION_IDS = {"FULL_DAY_SESSION_20260702_SUPERBET_A"}
DEMO_OR_STALE_EVENT_IDS = {
    "wc2026_spain_poland",
    "wc2026_brazil_norway",
    "wimbledon2026_hurkacz_sinner",
}
PLACEHOLDER_SOURCE_PATTERNS = [
    re.compile(pattern, re.I)
    for pattern in [
        r"\bTipster\s*\d+\b",
        r"Consensus Football Preview",
        r"Polish Sports Portal",
        r"Grass Court Specialist",
        r"Italian Tennis Forum",
        r"Rio Football Analyst",
        r"Scandinavian Football News",
        r"\bTBD\b",
        r"\bTODO\b",
        r"placeholder",
        r"example\.com",
    ]
]
URL_PATTERN = re.compile(r"https?://[^\s\]\)\"'<>]+", re.I)


def _load_json(path: Path) -> dict[str, Any]:
    assert path.exists(), f"Missing JSON artifact: {path.relative_to(ROOT)}"
    return json.loads(path.read_text(encoding="utf-8"))


def _walk_values(value: Any):
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_values(item)
    else:
        yield value


def _collect_urls(value: Any) -> list[str]:
    urls: list[str] = []
    for item in _walk_values(value):
        if isinstance(item, str):
            urls.extend(URL_PATTERN.findall(item))
    return sorted(set(url.rstrip(".,;") for url in urls))


def _slate_artifact() -> Path:
    candidates = [
        SESSION_ROOT / "04_slate_verification.json",
        SESSION_ROOT / "05_slate_verification.json",
        SESSION_ROOT / "slate_verification.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise AssertionError(
        "Missing slate verification artifact for "
        f"SUPERBET_SESSION_RUN_ID={SESSION_RUN_ID}; checked: "
        + ", ".join(str(p.relative_to(ROOT)) for p in candidates)
    )


def _event_pack_paths() -> list[Path]:
    candidates = [
        SESSION_ROOT / "06_event_packs",
        SESSION_ROOT / "event_packs",
    ]
    paths: list[Path] = []
    for directory in candidates:
        if directory.exists():
            paths.extend(sorted(directory.glob("*/evidence_pack.json")))
            paths.extend(sorted(directory.glob("*/evidence_pack.*.json")))
    return sorted(set(paths))


def test_session_run_id_is_not_known_invalid_a() -> None:
    assert SESSION_RUN_ID not in FORBIDDEN_SESSION_IDS, (
        "Do not run integrity tests against known-invalid session A. "
        "Use fish: set -gx SUPERBET_SESSION_RUN_ID FULL_DAY_SESSION_20260702_SUPERBET_B"
    )


def test_session_root_exists_for_requested_run_id() -> None:
    assert SESSION_ROOT.exists(), (
        f"Session root does not exist: {SESSION_ROOT.relative_to(ROOT)}. "
        "Generate the repaired session first, or export the correct run id with: "
        "set -gx SUPERBET_SESSION_RUN_ID FULL_DAY_SESSION_20260702_SUPERBET_B"
    )


def test_pass_slate_requires_explicit_source_urls() -> None:
    slate = _load_json(_slate_artifact())
    events = slate.get("events") or slate.get("verified_events") or []
    assert events, "Slate verification artifact must contain events or verified_events"

    failures: dict[str, list[str]] = {}
    for event in events:
        event_id = str(event.get("event_id") or event.get("id") or "UNKNOWN")
        status = str(event.get("status") or event.get("verification_status") or "").upper()
        if status and status not in {"PASS", "VERIFIED", "READY", "OK"}:
            continue
        urls = _collect_urls(event)
        event_failures: list[str] = []
        if len(urls) < 2:
            event_failures.append(f"requires >=2 explicit source URLs, found {len(urls)}")
        if event_id in DEMO_OR_STALE_EVENT_IDS:
            event_failures.append("known stale/demo event id")
        if event_failures:
            failures[event_id] = event_failures

    assert not failures, f"PASS/verified slate integrity failures: {failures}"


def test_no_known_demo_or_stale_event_ids_in_pass_slate() -> None:
    slate = _load_json(_slate_artifact())
    events = slate.get("events") or slate.get("verified_events") or []
    ids = {str(event.get("event_id") or event.get("id")) for event in events}
    forbidden = ids & DEMO_OR_STALE_EVENT_IDS
    assert not forbidden, f"PASS slate contains stale/demo event ids: {sorted(forbidden)}"


def test_evidence_packs_have_sources_and_no_placeholder_tipsters() -> None:
    packs = _event_pack_paths()
    assert packs, (
        "No evidence packs found. Expected e.g. "
        f"{(SESSION_ROOT / '06_event_packs').relative_to(ROOT)}/<event_id>/evidence_pack.json"
    )

    failures: dict[str, list[str]] = {}
    for pack_path in packs:
        data = _load_json(pack_path)
        text = json.dumps(data, ensure_ascii=False)
        pack_failures: list[str] = []
        urls = _collect_urls(data)
        if len(urls) < 2:
            pack_failures.append(f"requires >=2 explicit source URLs, found {len(urls)}")

        placeholders = [pat.pattern for pat in PLACEHOLDER_SOURCE_PATTERNS if pat.search(text)]
        if placeholders:
            pack_failures.append(f"placeholder sources found: {placeholders}")

        sport = str(data.get("sport") or "").lower()
        competition = str(data.get("competition") or data.get("tournament") or "")
        if sport == "football" and "World Cup" in competition:
            if not any("fifa.com" in url.lower() for url in urls):
                pack_failures.append("missing official FIFA source URL")
        if "Wimbledon" in competition:
            if not any("wimbledon.com" in url.lower() for url in urls):
                pack_failures.append("missing official Wimbledon source URL")

        if pack_failures:
            failures[str(pack_path.relative_to(ROOT))] = pack_failures

    assert not failures, f"Evidence source integrity failures: {failures}"


def test_manual_quote_cards_reference_verified_event_ids_only() -> None:
    slate = _load_json(_slate_artifact())
    events = slate.get("events") or slate.get("verified_events") or []
    verified_ids = {str(event.get("event_id") or event.get("id")) for event in events}
    verified_ids.discard("None")
    verified_ids.discard("UNKNOWN")

    quote_artifacts = [
        SESSION_ROOT / "09_manual_superbet_quote_cards.json",
        SESSION_ROOT / "manual_superbet_quote_cards.json",
    ]
    quote_path = next((p for p in quote_artifacts if p.exists()), None)
    assert quote_path is not None, (
        "Missing manual Superbet quote cards JSON; checked: "
        + ", ".join(str(p.relative_to(ROOT)) for p in quote_artifacts)
    )

    cards_data = _load_json(quote_path)
    cards = cards_data.get("cards") or cards_data.get("manual_quote_cards") or cards_data.get("quote_cards") or []
    assert isinstance(cards, list), "Manual quote cards must be a list under cards/manual_quote_cards/quote_cards"

    failures: dict[str, str] = {}
    for idx, card in enumerate(cards):
        event_id = str(card.get("event_id") or card.get("match_id") or card.get("fixture_id") or "UNKNOWN")
        if event_id not in verified_ids:
            failures[f"card_{idx}"] = event_id
        if event_id in DEMO_OR_STALE_EVENT_IDS:
            failures[f"card_{idx}"] = event_id

    assert not failures, f"Manual quote cards reference non-verified or stale event ids: {failures}"
