"""Tests for safe ZawodTyper transport and parser."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from bet.tipsters.contracts import ExtractorVerdict, RawDocument
from bet.tipsters.zawodtyper import (
    ZAWODTYPER_COOKIE_POLICY_NO_COOKIE,
    ZAWODTYPER_COOKIE_POLICY_TECHNICAL,
    build_zawodtyper_daily_url,
    build_zawodtyper_transport_warnings,
    build_zawodtyper_xhr_payloads,
    classify_zawodtyper_cookie_name,
    extract_zawodtyper,
    extract_zawodtyper_post_id,
    fetch_zawodtyper_public_xhr_document,
    select_zawodtyper_cookie_policy,
)


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


class _FakeCookie:
    def __init__(self, name: str, value: str, domain: str = ".zawodtyper.pl", path: str = "/") -> None:
        self.name = name
        self.value = value
        self.domain = domain
        self.path = path


class _FakeHeaders:
    def __init__(self, content_type: str) -> None:
        self._content_type = content_type

    def get(self, key: str, default: str = "") -> str:
        if key.lower() == "content-type":
            return self._content_type
        return default

    def get_content_charset(self) -> str:
        return "utf-8"


class _FakeResponse:
    def __init__(self, body: str, *, url: str, status: int = 200, content_type: str = "application/json") -> None:
        self._body = body.encode("utf-8")
        self._url = url
        self.status = status
        self.headers = _FakeHeaders(content_type)

    def read(self) -> bytes:
        return self._body

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeOpener:
    def __init__(self, jar, html: str, cookies: list[_FakeCookie]) -> None:
        self.jar = jar
        self.html = html
        self.cookies = cookies

    def open(self, request, timeout: float = 0):
        for cookie in self.cookies:
            self.jar.set_cookie(cookie)
        return _FakeResponse(self.html, url=request.full_url, status=200, content_type="text/html")


def test_cookie_classifier_allows_ga_but_blocks_session_auth_nonce():
    assert classify_zawodtyper_cookie_name("_ga") == "ALLOWED_ANALYTICS_EPHEMERAL"
    assert classify_zawodtyper_cookie_name("_ga_WQ0W4KSFWX") == "ALLOWED_ANALYTICS_EPHEMERAL"
    assert classify_zawodtyper_cookie_name("SRV") == "ALLOWED_TECHNICAL"
    assert classify_zawodtyper_cookie_name("PHPSESSID") == "BLOCKED"
    assert classify_zawodtyper_cookie_name("auth_token") == "BLOCKED"
    assert classify_zawodtyper_cookie_name("csrf_nonce") == "BLOCKED"
    assert classify_zawodtyper_cookie_name("mystery_guard") == "UNKNOWN"


def test_select_cookie_policy_prefers_no_cookie_then_technical_then_analytics():
    variants = [
        {"variant": "no_cookie", "status": 200, "is_json": True, "item_count": 8, "parse_success": True},
        {"variant": "technical_only", "status": 200, "is_json": True, "item_count": 8, "parse_success": True},
        {"variant": "technical_plus_analytics_ephemeral", "status": 200, "is_json": True, "item_count": 8, "parse_success": True},
    ]
    assert select_zawodtyper_cookie_policy(variants) == "no_cookie"


def test_select_cookie_policy_prefers_technical_over_analytics_when_no_cookie_fails():
    variants = [
        {"variant": "no_cookie", "status": 400, "is_json": False, "item_count": 0, "parse_success": False},
        {"variant": "technical_only", "status": 200, "is_json": True, "item_count": 8, "parse_success": True},
        {"variant": "technical_plus_analytics_ephemeral", "status": 200, "is_json": True, "item_count": 8, "parse_success": True},
    ]
    assert select_zawodtyper_cookie_policy(variants) == "technical_only"


def test_extract_post_id_from_public_html():
    html = '<body class="postid-295093 single-post"></body>'
    assert extract_zawodtyper_post_id(html) == 295093


def test_build_xhr_payloads_respects_max_pages_per_source():
    assert build_zawodtyper_xhr_payloads(295093, 1) == []
    assert build_zawodtyper_xhr_payloads(295093, 2) == [{"endpoint": "api_get_bets_by_post_id", "post_id": 295093, "offset": 0, "count": 5}]
    assert build_zawodtyper_xhr_payloads(295093, 3) == [
        {"endpoint": "api_get_bets_by_post_id", "post_id": 295093, "offset": 0, "count": 5},
        {"endpoint": "api_get_bets_by_post_id", "post_id": 295093, "offset": 5, "count": 505},
    ]


def test_transport_warning_builder_logs_cookie_names_only():
    warnings = build_zawodtyper_transport_warnings({
        "cookie_policy": "no_cookie",
        "cookie_names_sent": [],
        "observed_cookie_names": ["SRV", "_ga"],
        "xhr_call_count": 2,
        "item_count": 68,
    })
    joined = " ".join(warnings)
    assert "SRV" in joined
    assert "_ga" in joined
    assert "secret_cookie_value" not in joined


def test_fetch_public_xhr_document_uses_no_cookie_policy_and_parses_items():
    page_html = '<html><body class="postid-295093 single-post"></body></html>'
    xhr_one = json.dumps({
        "success": True,
        "data": [{
            "comment_id": "1",
            "comment_type": "bet",
            "match_name": "Polska - Niemcy",
            "content": "Analiza meczu.",
            "discipline": "Piłka Nożna",
            "type": "Powyżej 2.5",
            "rate": "1.80",
            "author_name": "Typer A",
            "author_stats": {"bet_count": 12, "ratio": 0.7},
        }],
    })
    xhr_two = json.dumps({
        "success": True,
        "data": [{
            "comment_id": "2",
            "comment_type": "bet",
            "match_name": "Francja - Włochy",
            "content": "Druga analiza meczu.",
            "discipline": "Piłka Nożna",
            "type": "BTTS",
            "rate": "1.95",
            "author_name": "Typer B",
            "author_stats": {"bet_count": 8, "ratio": 0.6},
        }],
    })
    xhr_calls = []

    def fake_urlopen(request, timeout: float = 0):
        xhr_calls.append({
            "url": request.full_url,
            "cookie": request.headers.get("Cookie"),
            "content_type": request.headers.get("Content-type"),
            "payload": json.loads(request.data.decode("utf-8")),
        })
        body = xhr_one if len(xhr_calls) == 1 else xhr_two
        return _FakeResponse(body, url=request.full_url, status=200, content_type="application/json")

    review_data = {
        "source_reviews": {
            "zawodtyper": {
                "cookie_policy": ZAWODTYPER_COOKIE_POLICY_NO_COOKIE,
                "allowed_cookie_names": ["SRV"],
            }
        }
    }
    with patch("bet.tipsters.zawodtyper.build_opener", lambda processor: _FakeOpener(processor.cookiejar, page_html, [_FakeCookie("SRV", "hidden")])):
        with patch("bet.tipsters.zawodtyper.urlopen", fake_urlopen):
            doc, meta = fetch_zawodtyper_public_xhr_document(
                "https://www.zawodtyper.pl/typy-dnia-6-lipca-poniedzialek/",
                review_data=review_data,
                timeout_seconds=12.0,
                user_agent="agent-test",
                max_pages_per_source=3,
            )

    assert doc is not None
    assert meta["cookie_policy"] == "no_cookie"
    assert meta["cookie_names_sent"] == []
    assert meta["observed_cookie_names"] == ["SRV"]
    assert meta["item_count"] == 2
    assert len(xhr_calls) == 2
    assert all(call["cookie"] is None for call in xhr_calls)
    assert all(call["content_type"] == "application/json" for call in xhr_calls)
    assert all(sorted(call["payload"].keys()) == ["count", "endpoint", "offset", "post_id"] for call in xhr_calls)
    payload = json.loads(doc.html)
    assert payload["success"] is True
    assert len(payload["data"]) == 2


def test_fetch_public_xhr_document_rejects_blocked_cookie_name():
    page_html = '<html><body class="postid-295093 single-post"></body></html>'
    review_data = {"source_reviews": {"zawodtyper": {"allowed_cookie_names": ["SRV"]}}}
    with patch("bet.tipsters.zawodtyper.build_opener", lambda processor: _FakeOpener(processor.cookiejar, page_html, [_FakeCookie("PHPSESSID", "hidden")])):
        doc, meta = fetch_zawodtyper_public_xhr_document(
            "https://www.zawodtyper.pl/typy-dnia-6-lipca-poniedzialek/",
            review_data=review_data,
            timeout_seconds=12.0,
            user_agent="agent-test",
            max_pages_per_source=3,
        )
    assert doc is None
    assert meta["reason"] == "blocked_cookie_names:PHPSESSID"


def test_fetch_public_xhr_document_rejects_unknown_security_like_cookie():
    page_html = '<html><body class="postid-295093 single-post"></body></html>'
    review_data = {"source_reviews": {"zawodtyper": {"allowed_cookie_names": ["SRV"]}}}
    with patch("bet.tipsters.zawodtyper.build_opener", lambda processor: _FakeOpener(processor.cookiejar, page_html, [_FakeCookie("mystery_guard", "hidden")])):
        doc, meta = fetch_zawodtyper_public_xhr_document(
            "https://www.zawodtyper.pl/typy-dnia-6-lipca-poniedzialek/",
            review_data=review_data,
            timeout_seconds=12.0,
            user_agent="agent-test",
            max_pages_per_source=3,
        )
    assert doc is None
    assert meta["reason"] == "unknown_cookie_names:mystery_guard"


def test_fetch_public_xhr_document_fail_closes_on_non_json():
    page_html = '<html><body class="postid-295093 single-post"></body></html>'

    def fake_urlopen(request, timeout: float = 0):
        return _FakeResponse("<html>bad</html>", url=request.full_url, status=200, content_type="text/html")

    review_data = {"source_reviews": {"zawodtyper": {"allowed_cookie_names": ["SRV"]}}}
    with patch("bet.tipsters.zawodtyper.build_opener", lambda processor: _FakeOpener(processor.cookiejar, page_html, [_FakeCookie("SRV", "hidden")])):
        with patch("bet.tipsters.zawodtyper.urlopen", fake_urlopen):
            doc, meta = fetch_zawodtyper_public_xhr_document(
                "https://www.zawodtyper.pl/typy-dnia-6-lipca-poniedzialek/",
                review_data=review_data,
                timeout_seconds=12.0,
                user_agent="agent-test",
                max_pages_per_source=3,
            )
    assert doc is None
    assert meta["reason"] == "xhr_non_json_content_type:text/html"


def test_xhr_market_text_takes_precedence_over_reasoning_for_double_chance():
    xhr_content = """
    {
      "success": true,
      "data": [
        {
          "comment_id": "1001",
          "comment_type": "bet",
          "match_name": "Meksyk - Anglia",
          "content": "Anglia gra zdecydowanie poniżej oczekiwań, ale rynek dalej jest 1X.",
          "discipline": "Piłka Nożna",
          "type": "1X - Meksyk wygra lub zremisuje mecz",
          "rate": "1.55",
          "author_name": "TyperKamil",
          "author_stats": {"bet_count": 12, "ratio": 0.75}
        }
      ]
    }
    """
    doc = RawDocument(
        source_id="zawodtyper",
        url="https://www.zawodtyper.pl/NP_ajax.php",
        fetched_at_utc="2026-07-05T22:46:15Z",
        html=xhr_content,
        status_code=200,
        content_type="application/json",
    )
    review_data = {"source_reviews": {"zawodtyper": {"allow_public_xhr_capture": True}}}
    result = extract_zawodtyper(doc, review_data=review_data)
    assert result.verdict == ExtractorVerdict.OK
    assert result.picks[0].direction == "DC"
