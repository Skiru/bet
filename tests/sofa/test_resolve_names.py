from datetime import UTC, datetime, timedelta

from bet.sofa.names import normalize_name
from bet.sofa.resolve import SofaResolver


def test_normalize_names_diacritics():
    # fold nie kasuje ø ł đ ı æ ß ð þ
    assert normalize_name("Bodø/Glimt") == "bodo/glimt"
    assert normalize_name("Śląsk Wrocław") == "slask wroclaw"
    assert normalize_name("Đurgarden") == "durgarden"
    assert normalize_name("Beşiktaş") == "besiktas"
    assert normalize_name("Næstved") == "naestved"
    assert normalize_name("Großaspach") == "grossaspach"
    assert normalize_name("Hafnarfjörður") == "hafnarfjordur"
    assert normalize_name("Þróttur") == "throttur"


def test_resolve_window():
    class DummyResolver(SofaResolver):
        def __init__(self):
            pass

    res = DummyResolver()

    kickoff = datetime(2026, 9, 17, 15, 0, tzinfo=UTC)

    # 0 hours diff
    event = {
        "startTimestamp": int(kickoff.timestamp()),
        "homeTeam": {"name": "a"},
        "awayTeam": {"name": "B"},
    }
    assert res._is_match(event, kickoff, "a")

    # 23 hours diff
    event23 = {
        "startTimestamp": int((kickoff + timedelta(hours=23)).timestamp()),
        "homeTeam": {"name": "a"},
        "awayTeam": {"name": "B"},
    }
    assert res._is_match(event23, kickoff, "a")

    # 25 hours diff
    event25 = {
        "startTimestamp": int((kickoff + timedelta(hours=25)).timestamp()),
        "homeTeam": {"name": "a"},
        "awayTeam": {"name": "B"},
    }
    assert not res._is_match(event25, kickoff, "a")

    # 30 hours diff
    event30 = {
        "startTimestamp": int((kickoff + timedelta(hours=30)).timestamp()),
        "homeTeam": {"name": "a"},
        "awayTeam": {"name": "B"},
    }
    assert not res._is_match(event30, kickoff, "a")
