import pytest
from scripts.adapters.flashscore_adapter import parse


def test_flashscore_enrichment():
    html = """
    <html>
    <body>
        <div class="headerLeague">
            <span class="headerLeague__category-text">USA</span>
            <span class="headerLeague__title-text">NBA - Play Offs</span>
        </div>
        
        <div id="g_3_Match1234" class="event__match">
            <a href="https://www.flashscore.com/match/basketball/1234" class="eventRowLink"></a>
            <div class="event__time">21:00</div>
            <div class="event__homeParticipant">Team A</div>
            <div class="event__awayParticipant">Team B</div>
            <span class="event__score event__score--home" data-side="1">114</span>
            <span class="event__score event__score--away" data-side="2">109</span>
            <div class="event__part event__part--home event__part--1">34</div>
            <div class="event__part event__part--home event__part--2">26</div>
            <div class="event__part event__part--away event__part--1">30</div>
            <div class="event__part event__part--away event__part--2">26</div>
            <div class="event__stage--block">Finished</div>
        </div>

        <div id="g_1_Match5678" class="event__match">
            <div class="event__time">23:00</div>
            <div class="event__homeParticipant">Team C</div>
            <div class="event__awayParticipant">Team D</div>
            <div class="event__stage--block">23:00</div>
        </div>
        
        <div id="g_2_Match9012" class="event__match">
            <div class="event__time">01:00</div>
            <div class="event__homeParticipant">Team E</div>
            <div class="event__awayParticipant">Team F</div>
            <div class="event__stage--block">2nd Quarter</div>
        </div>
    </body>
    </html>
    """
    
    results = parse(html, "https://www.flashscore.com/basketball/")
    
    assert len(results) == 3
    
    # Finished match
    match1 = results[0]
    assert match1["home"] == "Team A"
    assert match1["away"] == "Team B"
    assert match1["match_id"] == "Match1234"
    assert match1["score_home"] == 114
    assert match1["score_away"] == 109
    assert match1["period_scores"] == {"home": [34, 26], "away": [30, 26]}
    assert match1["match_url"] == "https://www.flashscore.com/match/basketball/1234"
    assert match1["status"] == "Finished"
    assert match1["is_live"] is False
    assert match1["country"] == "USA"
    assert match1["league"] == "NBA - Play Offs"
    
    # Upcoming match
    match2 = results[1]
    assert match2["home"] == "Team C"
    assert match2["match_id"] == "Match5678"
    assert match2["score_home"] is None
    assert match2["score_away"] is None
    assert match2["period_scores"] is None
    assert match2["match_url"] is None
    assert match2["status"] == "23:00"
    assert match2["is_live"] is False
    assert match2["country"] == "USA"
    assert match2["league"] == "NBA - Play Offs"
    
    # Live match
    match3 = results[2]
    assert match3["home"] == "Team E"
    assert match3["match_id"] == "Match9012"
    assert match3["status"] == "2nd Quarter"
    assert match3["is_live"] is True
    assert match3["country"] == "USA"
    assert match3["league"] == "NBA - Play Offs"


def test_flashscore_relative_url():
    """match_url with relative href must be normalized to absolute."""
    html = """
    <html><body>
        <div id="g_1_AbcDef" class="event__match">
            <a href="/match/football/abcdef" class="eventRowLink"></a>
            <div class="event__homeParticipant">Arsenal</div>
            <div class="event__awayParticipant">Chelsea</div>
        </div>
    </body></html>
    """
    results = parse(html, "https://www.flashscore.com/football/england/premier-league/")
    assert len(results) == 1
    assert results[0]["match_url"] == "https://www.flashscore.com/match/football/abcdef"


def test_flashscore_zero_score():
    """score_home=0 must not be dropped (integer zero is valid)."""
    html = """
    <html><body>
        <div id="g_1_ZeroTest" class="event__match">
            <div class="event__homeParticipant">Team X</div>
            <div class="event__awayParticipant">Team Y</div>
            <span class="event__score event__score--home">0</span>
            <span class="event__score event__score--away">3</span>
            <div class="event__stage--block">Finished</div>
        </div>
    </body></html>
    """
    results = parse(html, "https://www.flashscore.com/football/")
    assert len(results) == 1
    assert results[0]["score_home"] == 0
    assert results[0]["score_away"] == 3


def test_ingest_deep_parse_none_safe():
    """deep_parse=None must not raise AttributeError during ingest."""
    from scripts.ingest_scan_stats import ingest_event as ingest_scan_event

    event = {
        "sport": "football",
        "home": "Alpha FC",
        "away": "Beta FC",
        "odds": {"w1": 2.0, "x": 3.2, "w2": 3.8},
        "form_home": ["W", "W", "L"],  # Plain strings — must not crash
        "form_away": [],
        "h2h": {},
        "deep_parse": None,  # Explicitly None — must not raise
    }
    # Should not raise; result may be True or False depending on cache state
    try:
        ingest_scan_event("https://www.flashscore.com/football/", event, dry_run=True)
    except AttributeError as e:
        pytest.fail(f"ingest_scan_event raised AttributeError with deep_parse=None: {e}")
