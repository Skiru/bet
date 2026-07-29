from bet.enrichment.football_data_foundation.live_response_corpus_capture.providers import (
    find_matching_football_data_org_id,
    find_matching_api_football_id,
)


def test_find_matching_football_data_org_id():
    data = {
        "matches": [
            {
                "id": 12345,
                "homeTeam": {"name": "Norway"},
                "awayTeam": {"name": "Senegal"},
            },
            {
                "id": 67890,
                "homeTeam": {"name": "England"},
                "awayTeam": {"name": "Italy"},
            }
        ]
    }

    assert find_matching_football_data_org_id(data, "Norway", "Senegal") == "12345"
    assert find_matching_football_data_org_id(data, "England", "Italy") == "67890"
    assert find_matching_football_data_org_id(data, "France", "Spain") is None


def test_find_matching_api_football_id():
    data = {
        "response": [
            {
                "fixture": {"id": 1122},
                "teams": {
                    "home": {"name": "Norway"},
                    "away": {"name": "Senegal"},
                }
            },
            {
                "fixture": {"id": 3344},
                "teams": {
                    "home": {"name": "England"},
                    "away": {"name": "Italy"},
                }
            }
        ]
    }

    assert find_matching_api_football_id(data, "Norway", "Senegal") == "1122"
    assert find_matching_api_football_id(data, "England", "Italy") == "3344"
    assert find_matching_api_football_id(data, "France", "Spain") is None
