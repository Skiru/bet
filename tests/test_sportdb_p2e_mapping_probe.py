from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "sportdb_p2e_mapping_probe.py"
SPEC = importlib.util.spec_from_file_location("sportdb_p2e_mapping_probe", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
probe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)
SCRIPT_SOURCE = SCRIPT_PATH.read_text(encoding="utf-8")


def test_parse_sse_data_json_frame() -> None:
    events, payloads = probe.parse_sse_payloads(
        'event: message\ndata: {"jsonrpc":"2.0","result":{"ok":true}}\n\n'
    )
    assert events[0]["event"] == "message"
    assert payloads[0]["result"]["ok"] is True


def test_detect_text_event_stream_as_sse() -> None:
    assert probe.detect_response_mode("text/event-stream; charset=utf-8") == "sse"


def test_required_accept_header_string_exists_in_source() -> None:
    assert 'application/json, text/event-stream' in SCRIPT_SOURCE


def test_rest_country_endpoint_absent_in_source() -> None:
    assert "/api/football/countries" not in SCRIPT_SOURCE


def test_mcp_football_mapping_command_registered() -> None:
    assert '"mcp-football-mapping"' in SCRIPT_SOURCE


def test_schema_summary_loader_reads_tool_schema_structure(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "tool_schemas": {
                    "flashscore_list_sports": {
                        "tool_name": "flashscore_list_sports",
                        "input_schema": {"type": "object"},
                        "required_fields": [],
                        "optional_fields": [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    summary = probe.load_p2e_a2_schema_summary(summary_path)
    tool_schema = probe.get_tool_schema(summary, "flashscore_list_sports")
    assert tool_schema["tool_name"] == "flashscore_list_sports"
    assert tool_schema["input_schema"]["type"] == "object"


def test_payload_builder_fails_closed_when_required_field_missing() -> None:
    tool_schema = {"required_fields": ["sport", "country_id"], "optional_fields": []}
    try:
        probe.build_tool_payload(tool_schema, {"sport_key": "soccer"})
    except probe.RequiredPayloadFieldUnknownError as exc:
        assert exc.field_name == "country_id"
    else:
        raise AssertionError("Expected RequiredPayloadFieldUnknownError")


def test_payload_builder_does_not_invent_unknown_required_fields() -> None:
    tool_schema = {"required_fields": ["mystery_field"], "optional_fields": ["page"]}
    try:
        probe.build_tool_payload(tool_schema, {"page": 1, "sport_key": "soccer"})
    except probe.RequiredPayloadFieldUnknownError as exc:
        assert exc.field_name == "mystery_field"
    else:
        raise AssertionError("Expected RequiredPayloadFieldUnknownError")


def test_classification_enum_names_present_in_source() -> None:
    for name in sorted(probe.ALL_A3_CLASSIFICATIONS):
        assert name in SCRIPT_SOURCE


def test_england_selector_rejects_non_england_substitutes() -> None:
    items = [
        {"id": 1, "name": "United Kingdom", "slug": "united-kingdom"},
        {"id": 2, "name": "Great Britain", "slug": "great-britain"},
        {"id": 3, "name": "Scotland", "slug": "scotland"},
        {"id": 4, "name": "Wales", "slug": "wales"},
        {"id": 5, "name": "Northern Ireland", "slug": "northern-ireland"},
        {"id": 6, "name": "England", "slug": "england"},
    ]
    selected = probe.select_england_country(items)
    assert selected is not None
    assert selected["slug"] == "england"


def test_premier_league_selector_rejects_wrong_competitions() -> None:
    items = [
        {"id": "c1", "name": "Championship", "slug": "championship"},
        {"id": "c2", "name": "Women Super League", "slug": "women-super-league"},
        {"id": "c3", "name": "Premier League Cup", "slug": "premier-league-cup"},
        {"id": "c4", "name": "U21 Premier League", "slug": "u21-premier-league"},
        {"id": "c5", "name": "Premier League 2", "slug": "premier-league-2"},
        {"id": "c6", "name": "Premier League", "slug": "premier-league"},
    ]
    selected = probe.select_premier_league_competition(items)
    assert selected is not None
    assert selected["slug"] == "premier-league"


def test_safe_preview_caps_large_responses_and_redacts_key_name() -> None:
    preview = probe.safe_preview({"blob": "x" * 5000, "note": "SPORTDB_API_KEY"}, max_chars=200)
    assert preview["truncated"] is True
    assert "SPORTDB_API_KEY" not in preview["preview"]
