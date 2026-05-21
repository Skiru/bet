"""Targeted tests for the shared Flashscore match-page helper."""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = str(ROOT_DIR / "scripts")
SRC_DIR = str(ROOT_DIR / "src")

for path in (SCRIPTS_DIR, SRC_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from _helpers import flashscore_match_page_stats as flashscore_helper


class FakeResponse:
    def __init__(self, status_code: int, text: str = "", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data

    def json(self):
        return self._json_data


class FakeRequests:
    def __init__(self, search_response: FakeResponse, results_response: FakeResponse, stats_response: FakeResponse):
        self.search_response = search_response
        self.results_response = results_response
        self.stats_response = stats_response
        self.calls: list[str] = []

    def get(self, url: str, **kwargs):
        self.calls.append(url)
        if "s.livesport.services/api/v2/search" in url:
            return self.search_response
        if url.endswith("/results/"):
            return self.results_response
        if "/match/" in url and "match-statistics" in url:
            return self.stats_response
        raise AssertionError(f"Unexpected Flashscore URL: {url}")


def test_resolve_flashscore_match_id_falls_back_to_results_page(monkeypatch):
    search_response = FakeResponse(200, json_data={"results": []})
    results_html = "~AA÷MATCH123¬AB÷3¬AE÷Arsenal¬AF÷Chelsea¬PX÷team-1¬PY÷team-1" + (" " * 600)
    results_response = FakeResponse(200, text=results_html)
    requests = FakeRequests(search_response, results_response, FakeResponse(200, text=""))

    monkeypatch.setattr(
        flashscore_helper,
        "_get_flashscore_entity",
        lambda team_name, sport: ("team", "arsenal", "team-1"),
    )

    result = flashscore_helper.resolve_flashscore_match_id(
        "Arsenal",
        "Chelsea",
        c_requests=requests,
        sleep_seconds=0,
    )

    assert result["status"] == "ok"
    assert result["match_id"] == "MATCH123"
    assert result["failure_reason"] is None
    assert len(requests.calls) >= 2


def test_resolve_flashscore_match_id_reports_match_not_found(monkeypatch):
    search_response = FakeResponse(200, json_data={"results": []})
    results_response = FakeResponse(200, text=("x" * 600))
    requests = FakeRequests(search_response, results_response, FakeResponse(200, text=""))

    monkeypatch.setattr(
        flashscore_helper,
        "_get_flashscore_entity",
        lambda team_name, sport: ("team", "arsenal", "team-1"),
    )

    result = flashscore_helper.resolve_flashscore_match_id(
        "Arsenal",
        "Chelsea",
        c_requests=requests,
        sleep_seconds=0,
    )

    assert result["status"] == "failed"
    assert result["failure_reason"] == "match_not_found"


def test_parse_flashscore_match_stats_html_normalizes_rich_families():
    html = """
        <div>7 Corner Kicks 3</div>
        <div>2 Yellow Cards 4</div>
        <div>1 Red Cards 0</div>
        <div>14 Shots on Target 8</div>
        <div>21 Total Shots 12</div>
        <div>15 Fouls 18</div>
        <div>61 Ball Possession 39</div>
    """

    stats = flashscore_helper.parse_flashscore_match_stats_html(html)

    assert stats == {
        "corners": {"home": 7, "away": 3},
        "yellow_cards": {"home": 2, "away": 4},
        "red_cards": {"home": 1, "away": 0},
        "shots_on_target": {"home": 14, "away": 8},
        "shots": {"home": 21, "away": 12},
        "fouls": {"home": 15, "away": 18},
        "possession": {"home": 61, "away": 39},
    }


def test_fetch_flashscore_match_page_stats_parses_representative_html(monkeypatch):
    search_response = FakeResponse(200, json_data={"results": []})
    results_html = "~AA÷MATCH123¬AB÷3¬AE÷Arsenal¬AF÷Chelsea¬PX÷team-1¬PY÷team-1" + (" " * 600)
    stats_html = """
        <div>7 Corner Kicks 3</div>
        <div>2 Yellow Cards 4</div>
        <div>1 Red Cards 0</div>
        <div>14 Shots on Target 8</div>
        <div>21 Total Shots 12</div>
        <div>15 Fouls 18</div>
        <div>61 Ball Possession 39</div>
    """ + (" " * 600)
    requests = FakeRequests(search_response, FakeResponse(200, text=results_html), FakeResponse(200, text=stats_html))

    monkeypatch.setattr(
        flashscore_helper,
        "_get_flashscore_entity",
        lambda team_name, sport: ("team", "arsenal", "team-1"),
    )

    result = flashscore_helper.fetch_flashscore_match_page_stats(
        "Arsenal",
        "Chelsea",
        c_requests=requests,
        sleep_seconds=0,
    )

    assert result["status"] == "ok"
    assert result["match_id"] == "MATCH123"
    assert result["rich_keys_found"] == [
        "corners",
        "yellow_cards",
        "red_cards",
        "shots",
        "shots_on_target",
        "fouls",
        "possession",
    ]
    assert result["stats"]["corners"] == {"home": 7, "away": 3}
    assert result["stats"]["possession"] == {"home": 61, "away": 39}
    assert len(requests.calls) == 3


def test_fetch_flashscore_match_page_stats_encodes_query_uses_numeric_sport_id_and_parses_html():
    search_response = FakeResponse(200, json_data={"results": [{"type": "event", "id": "abc12345"}]})
    stats_response = FakeResponse(200, text="x" * 600 + " 7 Corner Kicks 3 2 Yellow Cards 4 10 Fouls 9 ")
    requests = FakeRequests(search_response, FakeResponse(200, text=""), stats_response)

    result = flashscore_helper.fetch_flashscore_match_page_stats(
        "A&B",
        "Łódź",
        c_requests=requests,
        sleep_seconds=0,
    )

    search_url = requests.calls[0]
    assert "q=A%26B%20%C5%81%C3%B3d%C5%BA" in search_url
    assert "sport=1" in search_url
    assert result["status"] == "ok"
    assert result["stats"]["corners"] == {"home": 7, "away": 3}
    assert result["stats"]["yellow_cards"] == {"home": 2, "away": 4}


def test_fetch_flashscore_match_page_stats_accepts_list_search_payloads():
    search_response = FakeResponse(200, json_data=[{"type": "event", "id": "abc12345"}])
    stats_response = FakeResponse(200, text="x" * 600 + " 7 Corner Kicks 3 ")
    requests = FakeRequests(search_response, FakeResponse(200, text=""), stats_response)

    result = flashscore_helper.fetch_flashscore_match_page_stats(
        "Real Sociedad",
        "Barcelona",
        c_requests=requests,
        sleep_seconds=0,
    )

    assert result["status"] == "ok"
    assert result["stats"] == {"corners": {"home": 7, "away": 3}}


def test_fetch_flashscore_match_page_stats_handles_object_typed_event_results(monkeypatch):
    search_response = FakeResponse(
        200,
        json_data={
            "results": [
                {"id": "team-123", "type": {"id": 2, "name": "Team"}, "name": "Real Sociedad"},
                {
                    "id": "event-row-1",
                    "type": {"id": 1, "name": "Event"},
                    "name": "Real Sociedad - Barcelona",
                    "url": "https://www.flashscore.com/football/spain/laliga/real-sociedad-barcelona-xtzLAF5d/",
                    "participants": [{"name": "Real Sociedad"}, {"name": "Barcelona"}],
                },
            ]
        },
    )
    stats_response = FakeResponse(200, text="x" * 600 + " 7 Corner Kicks 3 ")
    requests = FakeRequests(search_response, FakeResponse(200, text=""), stats_response)

    monkeypatch.setattr(
        flashscore_helper,
        "_get_flashscore_entity",
        lambda team_name, sport: ("team", "arsenal", "team-1"),
    )

    result = flashscore_helper.fetch_flashscore_match_page_stats(
        "Real Sociedad",
        "Barcelona",
        c_requests=requests,
        sleep_seconds=0,
    )

    assert requests.calls[1] == "https://www.flashscore.com/match/xtzLAF5d/#/match-summary/match-statistics/0"
    assert result["status"] == "ok"
    assert result["stats"] == {"corners": {"home": 7, "away": 3}}


def test_fetch_flashscore_match_page_stats_falls_back_to_team_results_page_when_search_has_no_event(monkeypatch):
    search_response = FakeResponse(
        200,
        json_data={
            "results": [
                {"id": "W8mj7MDD", "type": {"name": "Team"}, "name": "Real Madrid"}
            ]
        },
    )
    results_page_response = FakeResponse(
        200,
        text="x" * 600 + "~AA÷8WSYepie¬AB÷3¬AE÷Real Madrid¬AF÷Alaves¬PX÷W8mj7MDD¬PY÷hxt57t2q¬",
    )
    stats_response = FakeResponse(200, text="x" * 600 + " 7 Corner Kicks 3 ")
    requests = FakeRequests(search_response, results_page_response, stats_response)

    monkeypatch.setattr(
        flashscore_helper,
        "_get_flashscore_entity",
        lambda team_name, sport: ("team", "real-madrid", "W8mj7MDD"),
    )

    result = flashscore_helper.fetch_flashscore_match_page_stats(
        "Real Madrid",
        "Alaves",
        c_requests=requests,
        sleep_seconds=0,
    )

    assert requests.calls[1] == "https://www.flashscore.com/team/real-madrid/W8mj7MDD/results/"
    assert requests.calls[2] == "https://www.flashscore.com/match/8WSYepie/#/match-summary/match-statistics/0"
    assert result["status"] == "ok"
    assert result["stats"] == {"corners": {"home": 7, "away": 3}}


def test_fetch_flashscore_match_page_stats_repeats_failed_lookup_attempts(monkeypatch):
    class FailingRequests:
        def __init__(self):
            self.calls: list[str] = []

        def get(self, url: str, **kwargs):
            self.calls.append(url)
            raise Exception("temporary network error")

    monkeypatch.setattr(
        flashscore_helper,
        "_get_flashscore_entity",
        lambda team_name, sport: (None, None, None),
    )

    requests = FailingRequests()
    first = flashscore_helper.fetch_flashscore_match_page_stats(
        "Retry FC",
        "Retry United",
        c_requests=requests,
        sleep_seconds=0,
    )
    second = flashscore_helper.fetch_flashscore_match_page_stats(
        "Retry FC",
        "Retry United",
        c_requests=requests,
        sleep_seconds=0,
    )

    assert first["status"] == "failed"
    assert second["status"] == "failed"
    assert len(requests.calls) == 2
