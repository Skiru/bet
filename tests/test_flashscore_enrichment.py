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