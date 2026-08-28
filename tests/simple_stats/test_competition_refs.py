"""Competition resolution: the pinned map, and the search fallback beneath it.

The search payloads under tests/fixtures/simple_stats/sportdb_competition_refs
are real flashscore_search responses captured on 2026-08-25, so the ranking
these tests assert is the ranking the live API produced that day.
"""
import json
from pathlib import Path

import pytest

from bet.simple_stats import providers
from bet.simple_stats.providers import (
    _COMPETITION_MATCH_THRESHOLD,
    _fold,
    _pinned_competition_map,
    _shares_country_token,
    _sportdb_competition_refs,
)

FIXTURES = Path(__file__).parent.parent / "fixtures/simple_stats/sportdb_competition_refs"
MAP_PATH = Path(__file__).resolve().parents[2] / "config" / "sportdb_competition_map.json"


class _SearchOnlyClient:
    """Answers flashscore_search from a captured payload and refuses to invent
    anything else, so a test that accidentally exercises the country path fails
    loudly instead of silently passing."""

    def __init__(self, search_payload: dict, countries: list[dict] | None = None):
        self._search = search_payload
        self._countries = countries if countries is not None else []
        self.calls: list[str] = []

    def call_tool(self, tool: str, arguments: dict):
        self.calls.append(tool)
        if tool == "flashscore_list_countries":
            return {"data": self._countries}
        if tool == "flashscore_search":
            return self._search
        raise AssertionError(f"unexpected tool call: {tool}")


class _ExplodingClient:
    def call_tool(self, tool: str, arguments: dict):
        raise AssertionError(f"a pinned league must cost no provider call, got {tool}")


def _search(name: str) -> dict:
    return json.loads((FIXTURES / f"search_{name}.json").read_text(encoding="utf-8"))


def _countries() -> list[dict]:
    return json.loads((FIXTURES / "list_countries.json").read_text(encoding="utf-8"))["data"]


# --------------------------------------------------------------------------
# the pinned map
# --------------------------------------------------------------------------

def test_pinned_league_resolves_without_touching_the_provider():
    refs = _sportdb_competition_refs(_ExplodingClient(), "Saudi Pro League")
    assert refs == {
        "sport": "football",
        "country_slug": "saudi-arabia",
        "country_id": 165,
        "competition_slug": "saudi-professional-league",
        "competition_id": "tUxUbLR2",
    }


def test_pinned_lookup_is_normalization_insensitive():
    a = _sportdb_competition_refs(_ExplodingClient(), "Saudi Pro League")
    b = _sportdb_competition_refs(_ExplodingClient(), "  saudi   pro  league ")
    assert a == b


def test_the_pin_that_would_have_prevented_the_2026_08_25_defect():
    """The whole point: this name must never again resolve to Switzerland."""
    refs = _sportdb_competition_refs(_ExplodingClient(), "Saudi Pro League")
    assert refs["country_slug"] == "saudi-arabia"


def test_fa_cup_resolves_to_england_which_no_scoring_could_decide():
    """Wales, Oman and the UAE all run a competition named exactly "FA Cup",
    all scoring 1.000 against the query. Only an asserted country picks one."""
    refs = _sportdb_competition_refs(_ExplodingClient(), "FA Cup")
    assert refs["country_slug"] == "england"


def test_caller_cannot_mutate_the_cached_map():
    refs = _sportdb_competition_refs(_ExplodingClient(), "Premier League")
    refs["country_slug"] = "mars"
    again = _sportdb_competition_refs(_ExplodingClient(), "Premier League")
    assert again["country_slug"] == "england"


def test_unverified_seed_is_not_a_pin(monkeypatch, tmp_path):
    """A seed with no verification block is a to-do. Treating it as a pin would
    reintroduce exactly the unproven guess the map exists to remove."""
    path = tmp_path / "map.json"
    path.write_text(json.dumps({"competitions": {
        "proven league": {"refs": {"sport": "football", "country_slug": "x"},
                          "verification": {"flashscore_name": "Proven"}},
        "seeded only": {"refs": {"sport": "football", "country_slug": "y"}},
        "no refs": {"verification": {"flashscore_name": "Whatever"}},
    }}), encoding="utf-8")
    monkeypatch.setattr(providers, "_COMPETITION_MAP_PATH", path)
    monkeypatch.setattr(providers, "_COMPETITION_MAP_CACHE", None)

    pinned = _pinned_competition_map()
    assert set(pinned) == {"proven league"}


@pytest.mark.parametrize("body", ["", "{ not json", '{"competitions": "wrong type"}'])
def test_broken_map_file_degrades_to_the_search_path(monkeypatch, tmp_path, body):
    """Config trouble must cost the resolver its shortcut, not abort the run."""
    path = tmp_path / "map.json"
    path.write_text(body, encoding="utf-8")
    monkeypatch.setattr(providers, "_COMPETITION_MAP_PATH", path)
    monkeypatch.setattr(providers, "_COMPETITION_MAP_CACHE", None)

    assert _pinned_competition_map() == {}
    client = _SearchOnlyClient(_search("saudi_pro_league"), _countries())
    assert _sportdb_competition_refs(client, "Saudi Pro League") is not None
    assert "flashscore_search" in client.calls


def test_missing_map_file_degrades_to_the_search_path(monkeypatch, tmp_path):
    monkeypatch.setattr(providers, "_COMPETITION_MAP_PATH", tmp_path / "absent.json")
    monkeypatch.setattr(providers, "_COMPETITION_MAP_CACHE", None)
    assert _pinned_competition_map() == {}


# --------------------------------------------------------------------------
# the shipped map is an artifact under test, not just data
# --------------------------------------------------------------------------

_COHORT_WORDS = {"women", "womens", "u19", "u20", "u21", "u23", "youth",
                 "reserve", "reserves", "futsal", "friendly"}


def test_every_shipped_pin_is_verified_and_self_consistent():
    """A *pin* must carry proof. A *seed* -- an entry with neither refs nor a
    verification block -- is the file's own documented to-do state, written by
    hand and filled in later by build_sportdb_competition_map.py against the
    provider's data. The three UEFA club competitions ship as seeds because
    SportDB answered HTTP 402 on 2026-08-28, and bzzoiro discovers those fixtures
    by league id without needing a pin at all.

    What must never exist is a half-written entry: refs without proof would be
    read by the runtime as a pin.
    """
    document = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    entries = document["competitions"]
    assert entries, "the shipped map must not be empty"

    verified = 0
    for key, entry in entries.items():
        assert _fold(key) == key, f"{key}: map keys must already be folded"
        # Asserted knowledge is required of every entry, pin or seed: it is the
        # input the verifier works from.
        for field in ("display_name", "country", "kind", "flashscore_names"):
            assert entry.get(field), f"{key}: seed is missing {field}"
        assert len(entry.get("expect_teams") or []) >= 2, f"{key}: too few asserted clubs"

        verification = entry.get("verification")
        if verification is None:
            assert "refs" not in entry, f"{key}: refs written without verification"
            continue
        verified += 1
        refs = entry["refs"]
        assert set(refs) == {"sport", "country_slug", "country_id",
                             "competition_slug", "competition_id"}, key
        assert all(str(v) for v in refs.values()), f"{key}: empty ref field"

        # the name written must be one the seed asserted
        accepted = {_fold(n) for n in entry["flashscore_names"]}
        assert _fold(verification["flashscore_name"]) in accepted, key
        # and it must not be a different cohort wearing the same club names
        assert not (_COHORT_WORDS & set(_fold(verification["flashscore_name"]).split())), key
        # proof, not assertion: real clubs found in real season results
        assert len(verification["matched_teams"]) >= 2, key
        assert set(verification["matched_teams"]) <= set(entry["expect_teams"]), key

    assert verified >= 28, "the leagues that already broke must stay pinned"


def test_the_runtime_ignores_an_unverified_seed():
    """The map's own contract: an entry with no verification is a to-do, not a
    pin. If the runtime read one it would resolve a league off hand-asserted
    names -- exactly the guess the pinned map exists to remove."""
    document = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    seeds = {
        key for key, entry in document["competitions"].items()
        if entry.get("verification") is None
    }
    runtime = _pinned_competition_map()
    assert not (seeds & set(runtime))


def test_shipped_map_pins_the_leagues_that_actually_broke():
    document = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    entries = document["competitions"]
    assert entries["saudi pro league"]["refs"]["country_slug"] == "saudi-arabia"
    assert entries["swiss super league"]["refs"]["country_slug"] == "switzerland"
    # the two must never be the same league again
    assert (entries["saudi pro league"]["refs"]["competition_id"]
            != entries["swiss super league"]["refs"]["competition_id"])


# --------------------------------------------------------------------------
# the search fallback, on real captured payloads
# --------------------------------------------------------------------------

def test_partial_country_token_wins_against_a_same_named_foreign_league(monkeypatch):
    """Unpinned, "Saudi Pro League" used to lose to Switzerland's and China's
    "Super League" (both 0.800) with the correct "Saudi Professional League"
    third at 0.757. The country is in the payload; scoring now reads it."""
    monkeypatch.setattr(providers, "_COMPETITION_MAP_CACHE", {})
    client = _SearchOnlyClient(_search("saudi_pro_league"), _countries())
    refs = _sportdb_competition_refs(client, "Saudi Pro League")
    assert refs is not None
    assert refs["country_slug"] == "saudi-arabia"
    assert refs["competition_slug"] == "saudi-professional-league"


def test_distinctive_names_still_win_on_the_name_alone(monkeypatch):
    monkeypatch.setattr(providers, "_COMPETITION_MAP_CACHE", {})
    client = _SearchOnlyClient(_search("k_league_1"), _countries())
    refs = _sportdb_competition_refs(client, "K League 1")
    assert refs["country_slug"] == "south-korea"

    client = _SearchOnlyClient(_search("efl_cup"), _countries())
    refs = _sportdb_competition_refs(client, "EFL Cup")
    assert refs["country_slug"] == "england"


def test_the_bonus_cannot_lift_a_weak_match_over_the_threshold():
    """Sized to break ties, not to promote. A 0.55 name match with a country
    token still has to clear 0.75 and does not."""
    assert providers._PARTIAL_COUNTRY_BONUS + 0.55 < _COMPETITION_MATCH_THRESHOLD


@pytest.mark.parametrize(
    "query,country,expected",
    [
        ("saudi pro league", "saudi arabia", True),
        ("k league 1", "south korea", False),
        ("efl cup", "england", False),
        ("super league", "switzerland", False),
        ("saudi pro league", "", False),
        # short tokens are not country evidence: "usa" would otherwise fire on
        # any query happening to contain it
        ("liga mx", "usa", False),
    ],
)
def test_country_token_sharing_is_whole_words_only(query, country, expected):
    assert _shares_country_token(query, country) is expected


# --------------------------------------------------------------------------
# the builder's own season-label logic, which silently cost six leagues
# --------------------------------------------------------------------------

def test_builder_asks_about_both_season_conventions():
    """The first build tried the first two _season_candidates entries, which are
    two *spans* -- so a calendar-year league was never asked about "2026" and
    K League 1, Eliteserien, both Brazilian tiers, MLS and Liga MX all failed to
    verify despite existing."""
    import importlib.util

    path = (Path(__file__).resolve().parents[2]
            / "scripts" / "simple" / "build_sportdb_competition_map.py")
    spec = importlib.util.spec_from_file_location("_builder", path)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)

    labels = builder._season_labels("2026-2027")
    assert labels == ["2026-2027", "2026"]
    assert any("-" in x for x in labels) and any("-" not in x for x in labels)
