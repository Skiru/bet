"""Tests for safe ZawodTyper transport and parser."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from bet.tipsters.contracts import ExtractorVerdict, RawDocument
from bet.tipsters.zawodtyper import build_zawodtyper_daily_url, extract_zawodtyper


def test_build_zawodtyper_daily_url_for_polish_weekday_month():
    # 2026-07-04 is a Saturday (sobota) in July (lipca)
    dt = datetime(2026, 7, 4)
    url = build_zawodtyper_daily_url(dt)
    assert url == "https://www.zawodtyper.pl/typy-dnia-4-lipca-sobota/"


def test_parse_html_fixture_into_candidate_records():
    html_content = """
    <html>
      <body>
        <div class="searched-in">
          <div id="match-name123" class="searched-in">Polska - Niemcy</div>
          <div id="type123" class="searched-in">Powyżej 2.5 bramki</div>
        </div>
        <div id="accuracy-block">
          Skuteczność: 65%
          Kurs: 1.85
          Uzasadnienie: To jest analiza meczu polskiego zespołu z Niemcami. Obie drużyny strzelają dużo bramek.
        </div>
      </body>
    </html>
    """
    doc = RawDocument(
        source_id="zawodtyper",
        url="https://www.zawodtyper.pl/typy-dnia-4-lipca-sobota/",
        fetched_at_utc="2026-07-04T13:30:00Z",
        html=html_content,
        status_code=200,
        content_type="text/html",
    )
    result = extract_zawodtyper(doc)
    assert result.verdict == ExtractorVerdict.OK
    assert len(result.picks) == 1
    pick = result.picks[0]
    assert pick.home_team == "Polska"
    assert pick.away_team == "Niemcy"
    assert pick.market_family == "goals"
    assert pick.direction == "OVER"
    assert pick.odds_decimal == 1.85
    assert pick.valuable_signals["source_quality"] == ["accuracy_pct=65"]


def test_parse_xhr_fixture_through_parser_bridge():
    xhr_content = """
    {
      "success": true,
      "data": [
        {
          "comment_id": "999",
          "comment_type": "bet",
          "match_name": "Hiszpania - Włochy",
          "content": "Analiza meczu Hiszpania vs Włochy. Spodziewam się zaciętego spotkania.",
          "discipline": "Piłka Nożna",
          "type": "Obie strzelą (BTTS)",
          "rate": "1.95",
          "author_name": "TyperKamil",
          "author_stats": {
            "bet_count": 12,
            "ratio": 0.75
          }
        }
      ]
    }
    """
    doc = RawDocument(
        source_id="zawodtyper",
        url="https://www.zawodtyper.pl/NP_ajax.php",
        fetched_at_utc="2026-07-04T13:30:00Z",
        html=xhr_content,
        status_code=200,
        content_type="application/json",
    )
    review_data = {"source_reviews": {"zawodtyper": {"allow_public_xhr_capture": True}}}
    result = extract_zawodtyper(doc, review_data=review_data)
    assert result.verdict == ExtractorVerdict.OK
    assert len(result.picks) == 1
    pick = result.picks[0]
    assert pick.home_team == "Hiszpania"
    assert pick.away_team == "Włochy"
    assert pick.market_family == "btts"
    assert pick.direction == "BTTS_YES"
    assert pick.odds_decimal == 1.95
    assert pick.valuable_signals["source_quality"] == ["accuracy_pct=75"]


def test_rejects_stake_ev_coupon_final_bet():
    from bet.tipsters.legacy_bridge import convert_legacy_pick_to_v2
    legacy_pick = {
        "source_site": "ZawodTyper",
        "source_id": "zawodtyper",
        "tipster_name": "TyperKamil",
        "sport": "football",
        "event": "Hiszpania vs Włochy",
        "home_team": "Hiszpania",
        "away_team": "Włochy",
        "market": "Obie strzelą (BTTS)",
        "odds": 1.95,
        "reasoning": "Analiza meczu Hiszpania vs Włochy. Spodziewam się zaciętego spotkania.",
        "accuracy_pct": 75,
        "stake": "10u",
        "coupon": "some_coupon",
        "ev": "1.25",
        "final_bet": True
    }
    pick = convert_legacy_pick_to_v2(legacy_pick)
    assert not hasattr(pick, "stake")
    assert not hasattr(pick, "ev")
    joined = " ".join(pick.warnings)
    assert "forbidden_fields_dropped" in joined


def test_accuracy_pct_becomes_source_quality_metadata_only():
    html_content = """
    <html>
      <body>
        <div id="match-name1" class="searched-in">Polska - Niemcy</div>
        <div id="type1" class="searched-in">Powyżej 2.5 bramki</div>
        Skuteczność: 65%
      </body>
    </html>
    """
    doc = RawDocument(
        source_id="zawodtyper",
        url="https://www.zawodtyper.pl/typy-dnia-4-lipca-sobota/",
        fetched_at_utc="2026-07-04T13:30:00Z",
        html=html_content,
        status_code=200,
        content_type="text/html",
    )
    result = extract_zawodtyper(doc)
    pick = result.picks[0]
    assert pick.confidence_label == "source_claim"
    assert pick.valuable_signals["source_quality"] == ["accuracy_pct=65"]


def test_missing_review_gives_skip_not_fetch():
    import importlib.util
    from pathlib import Path
    script = Path(__file__).resolve().parents[2] / "scripts/pipeline_steps/s2_tipsters_v2_live_dry_run.py"
    spec = importlib.util.spec_from_file_location("s2_live", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    review_data = {"source_reviews": {}}
    allowed, reason = mod.review_allows_source(review_data, "zawodtyper")
    assert not allowed
    assert "missing" in reason


def test_public_xhr_call_is_disabled_unless_explicit_reviewed_flag_exists():
    html_content = """
    <html>
      <body>
        <div id="app">Vue SPA Shell</div>
      </body>
    </html>
    """
    doc = RawDocument(
        source_id="zawodtyper",
        url="https://www.zawodtyper.pl/typy-dnia-4-lipca-sobota/",
        fetched_at_utc="2026-07-04T13:30:00Z",
        html=html_content,
        status_code=200,
        content_type="text/html",
    )
    result = extract_zawodtyper(doc)
    assert result.verdict == ExtractorVerdict.EMPTY
    assert "NEEDS_PUBLIC_XHR_REVIEW" in result.warnings


def test_no_playwright_or_stealth_imports_in_zawodtyper_transport():
    import_path = Path(__file__).resolve().parents[2] / "src/bet/tipsters/zawodtyper.py"
    content = import_path.read_text(encoding="utf-8")
    assert "import playwright" not in content.lower()
    assert "import stealth" not in content.lower()
    assert "playwright_stealth" not in content.lower()


def test_resolve_target_entrypoints_for_zawodtyper():
    import importlib.util
    from pathlib import Path
    script = Path(__file__).resolve().parents[2] / "scripts/pipeline_steps/s2_tipsters_v2_live_dry_run.py"
    spec = importlib.util.spec_from_file_location("s2_live", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    
    entrypoints, fallback = mod.resolve_target_entrypoints("zawodtyper", "2026-07-04")
    assert len(entrypoints) == 1
    assert entrypoints[0] == "https://www.zawodtyper.pl/typy-dnia-4-lipca-sobota/"
    assert fallback == "https://www.zawodtyper.pl/"


def test_homepage_fixture_with_daily_card_count():
    html_content = """
    <html>
      <body>
        <div class="header">Zawód Typer Największa społeczność</div>
        <div class="daily-summary">
          <span>Typów dnia: 169</span>
        </div>
      </body>
    </html>
    """
    doc = RawDocument(
        source_id="zawodtyper",
        url="https://www.zawodtyper.pl/",
        fetched_at_utc="2026-07-04T13:30:00Z",
        html=html_content,
        status_code=200,
        content_type="text/html",
    )
    result = extract_zawodtyper(doc)
    assert result.expected_visible_count == 169
    assert result.extracted_count == 0
    assert result.coverage_status == "COVERAGE_UNDER_EXTRACTION"
    assert any("coverage_under_extraction:expected=169" in w for w in result.warnings)


def test_daily_page_fixture_with_multiple_visible_tip_cards():
    html_content = """
    <html>
      <body>
        <div>Typów: 2</div>
        <div class="card">
          <div id="match-name1" class="searched-in">Polska - Niemcy</div>
          <div id="type1" class="searched-in">Powyżej 2.5</div>
          <div id="acc1">Skuteczność: 65% Kurs: 1.85</div>
        </div>
        <div class="card">
          <div id="match-name2" class="searched-in">Francja - Włochy</div>
          <div id="type2" class="searched-in">Winner: 1</div>
          <div id="acc2">Skuteczność: 70% Kurs: 2.10</div>
        </div>
      </body>
    </html>
    """
    doc = RawDocument(
        source_id="zawodtyper",
        url="https://www.zawodtyper.pl/typy-dnia-4-lipca-sobota/",
        fetched_at_utc="2026-07-04T13:30:00Z",
        html=html_content,
        status_code=200,
        content_type="text/html",
    )
    result = extract_zawodtyper(doc)
    assert result.expected_visible_count == 2
    assert result.extracted_count == 2
    assert result.coverage_status == "FULL_OR_ACCEPTABLE"
    assert len(result.picks) == 2


def test_fixture_where_visible_count_says_169_but_only_1_extracted():
    html_content = """
    <html>
      <body>
        <div>Typów: 169</div>
        <div class="card">
          <div id="match-name1" class="searched-in">Polska - Niemcy</div>
          <div id="type1" class="searched-in">Powyżej 2.5</div>
          <div id="acc1">Skuteczność: 65% Kurs: 1.85</div>
        </div>
      </body>
    </html>
    """
    doc = RawDocument(
        source_id="zawodtyper",
        url="https://www.zawodtyper.pl/typy-dnia-4-lipca-sobota/",
        fetched_at_utc="2026-07-04T13:30:00Z",
        html=html_content,
        status_code=200,
        content_type="text/html",
    )
    result = extract_zawodtyper(doc)
    assert result.expected_visible_count == 169
    assert result.extracted_count == 1
    assert result.coverage_status == "COVERAGE_UNDER_EXTRACTION"
    assert any("coverage_under_extraction:expected=169 extracted=1" in w for w in result.warnings)


def test_pipeline_use_safely_serialized_to_dict():
    # Verify both list and dict pipeline_use can be formatted safely in python logic
    picks_to_test = [
        {"pipeline_use": ["use_1", "use_2"]},
        {"pipeline_use": {"use_a": True, "use_b": False}},
        {"pipeline_use": None}
    ]
    formatted = []
    for p in picks_to_test:
        p_use = p.get("pipeline_use", [])
        if isinstance(p_use, dict):
            p_use_str = ",".join(p_use.keys())
        elif isinstance(p_use, list):
            p_use_str = ",".join(str(x) for x in p_use)
        else:
            p_use_str = str(p_use)
        formatted.append(p_use_str)
        
    assert formatted[0] == "use_1,use_2"
    assert formatted[1] == "use_a,use_b"
    assert formatted[2] == "None"


def test_xhr_gate_blocks_xhr_payload_without_flag():
    xhr_content = """
    {
      "success": true,
      "data": [
        {
          "comment_id": "999",
          "comment_type": "bet",
          "match_name": "Hiszpania - Włochy",
          "content": "Analiza meczu Hiszpania vs Włochy.",
          "discipline": "Piłka Nożna",
          "type": "Obie strzelą (BTTS)",
          "rate": "1.95",
          "author_name": "TyperKamil",
          "author_stats": {"bet_count": 12, "ratio": 0.75}
        }
      ]
    }
    """
    doc = RawDocument(
        source_id="zawodtyper",
        url="https://www.zawodtyper.pl/NP_ajax.php",
        fetched_at_utc="2026-07-04T13:30:00Z",
        html=xhr_content,
        status_code=200,
        content_type="application/json",
    )
    
    # Test 1: Empty or missing review data (defaults to False)
    result1 = extract_zawodtyper(doc, review_data=None)
    assert len(result1.picks) == 0
    assert "allow_public_xhr_capture_required_for_xhr_parsing" in result1.warnings

    # Test 2: Review data present but allow_public_xhr_capture is False
    review_data = {
        "source_reviews": {
            "zawodtyper": {
                "allow_public_xhr_capture": False
            }
        }
    }
    result2 = extract_zawodtyper(doc, review_data=review_data)
    assert len(result2.picks) == 0
    assert "allow_public_xhr_capture_required_for_xhr_parsing" in result2.warnings


def test_xhr_gate_allows_xhr_payload_with_flag():
    xhr_content = """
    {
      "success": true,
      "data": [
        {
          "comment_id": "999",
          "comment_type": "bet",
          "match_name": "Hiszpania - Włochy",
          "content": "Analiza meczu Hiszpania vs Włochy.",
          "discipline": "Piłka Nożna",
          "type": "Obie strzelą (BTTS)",
          "rate": "1.95",
          "author_name": "TyperKamil",
          "author_stats": {"bet_count": 12, "ratio": 0.75}
        }
      ]
    }
    """
    doc = RawDocument(
        source_id="zawodtyper",
        url="https://www.zawodtyper.pl/NP_ajax.php",
        fetched_at_utc="2026-07-04T13:30:00Z",
        html=xhr_content,
        status_code=200,
        content_type="application/json",
    )
    review_data = {
        "source_reviews": {
            "zawodtyper": {
                "allow_public_xhr_capture": True
            }
        }
    }
    result = extract_zawodtyper(doc, review_data=review_data)
    assert result.verdict == ExtractorVerdict.OK
    assert len(result.picks) == 1


def test_review_gate_enforces_zawodtyper_note_check():
    import importlib.util
    from pathlib import Path
    script = Path(__file__).resolve().parents[2] / "scripts/pipeline_steps/s2_tipsters_v2_live_dry_run.py"
    spec = importlib.util.spec_from_file_location("s2_live", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Test 1: notes missing NP_ajax.php or public XHR review
    review_data_invalid = {
        "source_reviews": {
            "zawodtyper": {
                "status": "allow_live_dry_run",
                "terms_reviewed": True,
                "robots_reviewed": True,
                "public_html_only": True,
                "no_auth_no_premium_no_bypass": True,
                "allow_public_xhr_capture": True,
                "reviewed_by": "Mateusz Kozioł",
                "reviewed_at_utc": "2026-07-04T21:41:21Z",
                "notes": "Some generic notes."
            }
        }
    }
    allowed, reason = mod.review_allows_source(review_data_invalid, "zawodtyper")
    assert not allowed
    assert "notes" in reason or "np_ajax" in reason

    # Test 2: notes containing public XHR review
    review_data_valid = {
        "source_reviews": {
            "zawodtyper": {
                "status": "allow_live_dry_run",
                "terms_reviewed": True,
                "robots_reviewed": True,
                "public_html_only": True,
                "no_auth_no_premium_no_bypass": True,
                "allow_public_xhr_capture": True,
                "reviewed_by": "Mateusz Kozioł",
                "reviewed_at_utc": "2026-07-04T21:41:21Z",
                "notes": "Yes, we did a public XHR review of the source."
            }
        }
    }
    allowed, reason = mod.review_allows_source(review_data_valid, "zawodtyper")
    assert allowed


def test_zawodtyper_daily_url_target_for_runner():
    # 2026-07-05 is a Sunday (niedziela) in July (lipca)
    dt = datetime(2026, 7, 5)
    url = build_zawodtyper_daily_url(dt)
    assert url == "https://www.zawodtyper.pl/typy-dnia-5-lipca-niedziela/"
    assert url != "https://www.zawodtyper.pl/"


def test_zawodtyper_review_template_exists():
    import json
    path = Path(__file__).resolve().parents[2] / "docs/pipeline/tipster_terms_review.example.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    reviews = data.get("source_reviews", {})
    assert "zawodtyper" in reviews
    assert reviews["zawodtyper"]["allow_public_xhr_capture"] is False


def test_zawodtyper_xhr_gate_rejects_without_flag():
    xhr_content = """
    {
      "success": true,
      "data": [
        {
          "comment_id": "999",
          "comment_type": "bet",
          "match_name": "Hiszpania - Włochy",
          "content": "Analiza meczu Hiszpania vs Włochy.",
          "discipline": "Piłka Nożna",
          "type": "Obie strzelą (BTTS)",
          "rate": "1.95",
          "author_name": "TyperKamil",
          "author_stats": {"bet_count": 12, "ratio": 0.75}
        }
      ]
    }
    """
    doc = RawDocument(
        source_id="zawodtyper",
        url="https://www.zawodtyper.pl/NP_ajax.php",
        fetched_at_utc="2026-07-04T13:30:00Z",
        html=xhr_content,
        status_code=200,
        content_type="application/json",
    )
    # No review data means allow_public_xhr_capture is false by default
    result = extract_zawodtyper(doc, review_data=None)
    assert len(result.picks) == 0
    assert "allow_public_xhr_capture_required_for_xhr_parsing" in result.warnings


def test_zawodtyper_xhr_gate_requires_notes_token():
    import importlib.util
    script = Path(__file__).resolve().parents[2] / "scripts/pipeline_steps/s2_tipsters_v2_live_dry_run.py"
    spec = importlib.util.spec_from_file_location("s2_live", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    review_data_invalid = {
        "source_reviews": {
            "zawodtyper": {
                "status": "allow_live_dry_run",
                "terms_reviewed": True,
                "robots_reviewed": True,
                "public_html_only": True,
                "no_auth_no_premium_no_bypass": True,
                "allow_public_xhr_capture": True,
                "reviewed_by": "Mateusz Kozioł",
                "reviewed_at_utc": "2026-07-04T21:41:21Z",
                "notes": "Some generic notes."
            }
        }
    }
    allowed, reason = mod.review_allows_source(review_data_invalid, "zawodtyper")
    assert not allowed
    assert "notes" in reason or "np_ajax" in reason


def test_zawodtyper_static_daily_empty_sets_needs_xhr_review():
    html_content = "<html><body>No tips here</body></html>"
    doc = RawDocument(
        source_id="zawodtyper",
        url="https://www.zawodtyper.pl/typy-dnia-5-lipca-niedziela/",
        fetched_at_utc="2026-07-05T13:30:00Z",
        html=html_content,
        status_code=200,
        content_type="text/html",
    )
    result = extract_zawodtyper(doc)
    assert result.verdict == ExtractorVerdict.EMPTY
    assert result.coverage_status == "NEEDS_PUBLIC_XHR_REVIEW"


def test_summary_helper_pipeline_use_list_dict():
    picks_to_test = [
        {"pipeline_use": ["use_1", "use_2"]},
        {"pipeline_use": {"use_a": True, "use_b": False}},
        {"pipeline_use": None}
    ]
    formatted = []
    for p in picks_to_test:
        p_use = p.get("pipeline_use", [])
        if isinstance(p_use, dict):
            p_use_str = ",".join(p_use.keys())
        elif isinstance(p_use, list):
            p_use_str = ",".join(str(x) for x in p_use)
        else:
            p_use_str = str(p_use)
        formatted.append(p_use_str)
        
    assert formatted[0] == "use_1,use_2"
    assert formatted[1] == "use_a,use_b"
    assert formatted[2] == "None"


def test_no_forbidden_outputs():
    from bet.tipsters.legacy_bridge import convert_legacy_pick_to_v2
    legacy_pick = {
        "source_site": "ZawodTyper",
        "source_id": "zawodtyper",
        "tipster_name": "TyperKamil",
        "sport": "football",
        "event": "Hiszpania vs Włochy",
        "home_team": "Hiszpania",
        "away_team": "Włochy",
        "market": "Obie strzelą",
        "odds": 1.95,
        "stake": "10u",
        "coupon": "some_coupon",
        "ev": "1.25",
        "final_bet": True
    }
    pick = convert_legacy_pick_to_v2(legacy_pick)
    # Check that forbidden fields are removed and do not exist on the object
    assert not hasattr(pick, "stake")
    assert not hasattr(pick, "ev")
    assert not hasattr(pick, "coupon")
    assert not hasattr(pick, "final_bet")


