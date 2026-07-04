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
    result = extract_zawodtyper(doc)
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
