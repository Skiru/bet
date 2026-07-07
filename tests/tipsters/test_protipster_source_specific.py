import pytest
from bet.tipsters.contracts import RawDocument, ExtractorVerdict
from bet.tipsters.protipster import (
    is_allowed_protipster_url,
    parse_protipster_tip_cards,
    parse_protipster_top_matches,
    parse_protipster_tipster_stats,
    extract_protipster_document,
)

def test_protipster_url_allowance():
    assert is_allowed_protipster_url("https://www.protipster.pl/") is True
    assert is_allowed_protipster_url("https://www.protipster.pl/typy-bukmacherskie") is True
    assert is_allowed_protipster_url("https://www.protipster.pl/typy-bukmacherskie/pilka-nozna") is True
    # Forbidden links
    assert is_allowed_protipster_url("https://www.protipster.pl/login") is False
    assert is_allowed_protipster_url("https://www.protipster.pl/rejestracja") is False
    assert is_allowed_protipster_url("https://www.protipster.pl/bonus") is False
    assert is_allowed_protipster_url("https://www.protipster.pl/casino") is False

def test_protipster_parse_tip_cards():
    html = """
    <div class="tip-card">
        <span class="sport-league"> Piłka Nożna / Polska Ekstraklasa </span>
        <div class="event-title"> Raków Częstochowa vs Legia Warszawa </div>
        <div class="bet-details">
            <span class="market"> Obie drużyny strzelą </span>
            <span class="pick"> Tak @ 1.95 </span>
        </div>
        <div class="pt-rating"> Ocena typu: 8.4 </div>
        <div class="author"> napisane przez: @expert_typer </div>
        <p class="description"> Zobacz szczegóły typu: Raków Częstochowa i Legia Warszawa grają ofensywnie, obie strzelą bramki w tym meczu. </p>
    </div>
    <div class="tip-card marketing">
        <span> Zagraj w STS z bonusem 100 PLN! Oferta kasyno! </span>
        <button> Zagraj </button>
    </div>
    """
    picks = parse_protipster_tip_cards(html, "https://www.protipster.pl/typy-bukmacherskie")
    assert len(picks) == 1
    p = picks[0]
    assert p.home_team == "Raków Częstochowa"
    assert p.away_team == "Legia Warszawa"
    assert p.odds_decimal == 1.95
    assert p.tipster_name == "@expert_typer"
    assert p.valuable_signals["source_quality"] == ["pt_score=8.4"]
    assert p.reasoning != ""

def test_protipster_ako_coupon_rejection():
    # Verify accumulators are rejected and not parsed as single picks
    html = """
    <div class="tip-card ako">
        <h3> Kupon AKO na dzisiaj </h3>
        <div> Real Madryt wygra + Barcelona wygra </div>
        <span> Łączny kurs: 3.50 </span>
    </div>
    """
    picks = parse_protipster_tip_cards(html, "https://www.protipster.pl/typy-bukmacherskie")
    assert len(picks) == 0

def test_protipster_parse_top_matches_context():
    html = """
    <div class="top-match">
        <span class="match-title"> Real Madrid vs Barcelona </span>
        <span class="count"> 15 typów </span>
        <span class="trend"> trend: Real Madrid faworytem spotkania </span>
    </div>
    """
    signals = parse_protipster_top_matches(html, "https://www.protipster.pl/")
    assert len(signals) == 1
    s = signals[0]
    assert s.event == "Real Madrid vs Barcelona"
    assert s.tips_count == 15
    assert s.trend_text == "Real Madrid faworytem spotkania"

def test_protipster_parse_stats():
    html = """
    <div class="tipster-profile">
        <span class="user"> username: @typer_pro </span>
        <span class="yield"> yield: +12.5% </span>
        <span class="win"> win rate: 60% </span>
        <span class="followers"> 150 obserwujących </span>
    </div>
    """
    stats = parse_protipster_tipster_stats(html, "https://www.protipster.pl/")
    assert len(stats) == 1
    s = stats[0]
    assert s.username == "@typer_pro"
    assert s.yield_pct == 12.5
    assert s.win_rate == 60
    assert s.followers == 150

def test_protipster_extract_document_offline_warning():
    doc = RawDocument(
        source_id="protipster",
        url="https://www.protipster.pl/typy-bukmacherskie",
        fetched_at_utc="2026-07-07T04:00:00Z",
        html="<div class='tip-card'><div class='event-title'>Chelsea vs Arsenal</div><span class='pick'>over 2.5 @ 1.85</span><span class='author'>user: @alex</span></div>",
        status_code=200,
        content_type="text/html"
    )
    res = extract_protipster_document(doc)
    assert res.verdict == ExtractorVerdict.OK
    assert len(res.picks) == 1
    assert "protipster_candidate_blocked_by_robots_txt_offline_only" in res.warnings
