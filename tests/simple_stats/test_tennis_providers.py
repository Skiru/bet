"""Tennis provider identity: what a provider must prove before we believe a row.

Every failure this file guards was live on 2026-08-28, and none of them raised,
404'd, or produced an empty artifact. They produced *plausible numbers*:

  * tennisabstract answers HTTP 200 for a WTA player with Benoit Paire's page
    -- the same 605 KB body for Sabalenka, Swiatek, Gauff, Kostyuk and Shnaider
    -- and the client parsed his match table and filed his serve line under her
    name.
  * espn-tennis recorded a player as his own opponent in every match where ESPN
    listed him first, because the consumer compared a numeric athlete id
    against a display name, never matched, and fell through to a guess.
  * sackmann read two GitHub repositories that no longer exist.

These tests make no network calls. The live probing that produced the expected
values is recorded in comments and re-run by
scripts/simple/verify_tennis_providers.py, whose artifact the last section
checks.
"""
import json
import time
from pathlib import Path

import pytest
import requests

from bet.api_clients import tennis_abstract as ta_module
from bet.api_clients.tennis_abstract import (
    _ROUTE_RETRIES,
    _ROUTES,
    STALE_ROUTE_DAYS,
    TRANSIENT_FALLBACK_TTL_HOURS,
    TennisAbstractClient,
    _fold_player_name,
    identity_matches,
)
from bet.simple_stats.preflight import KNOWN_DEAD_PROVIDERS
from bet.simple_stats.providers import (
    _H2H_SUPPORTED_PROVIDERS,
    PROVIDERS_BY_SPORT,
    _opponent_of,
)

# --- identity: the check that replaces the fuzzy score --------------------


@pytest.mark.parametrize(
    "requested,claimed",
    [
        # The site folds diacritics in `var fullname`; we must fold too, or
        # every Czech and Polish player looks like a mismatch and the provider
        # loses them. Both pairs verified live on 2026-08-28.
        ("Jiří Lehečka", "Jiri Lehecka"),
        ("Iga Świątek", "Iga Swiatek"),
        ("Vít Kopřiva", "Vit Kopriva"),
        # Feeds disagree about word order and punctuation, never about tokens.
        ("Sabalenka Aryna", "Aryna Sabalenka"),
        ("Jean-Julien Rojer", "Jean Julien Rojer"),
        # A forename abbreviated to its initial is the one abbreviation that
        # is safe to accept: it is stated, not guessed at.
        ("C. Alcaraz", "Carlos Alcaraz"),
        ("Carlos Alcaraz", "C. Alcaraz"),
    ],
)
def test_identity_accepts_the_same_player_spelled_differently(requested, claimed):
    assert identity_matches(requested, claimed)


@pytest.mark.parametrize(
    "requested,claimed",
    [
        # The actual fabrication: every one of these requests was answered with
        # Benoit Paire's page, at 200, with a real match table.
        ("Iga Swiatek", "Benoit Paire"),
        ("Aryna Sabalenka", "Benoit Paire"),
        ("Coco Gauff", "Benoit Paire"),
        ("Marta Kostyuk", "Benoit Paire"),
        ("Diana Shnaider", "Benoit Paire"),
        # Shared surname, different player. ESPN's search returns both
        # Alexander Zverev and Vlada Zvereva for "Zverev"; a page-side check
        # must not paper over that either.
        ("Alexander Zverev", "Mischa Zverev"),
        ("Alexander Bublik", "Alexander Shevchenko"),
        # A surname alone is not an identification.
        ("Sinner", "Jannik Sinner"),
        ("", "Jannik Sinner"),
        ("Jannik Sinner", ""),
    ],
)
def test_identity_refuses_a_different_player(requested, claimed):
    assert not identity_matches(requested, claimed)


def test_identity_is_not_a_similarity_score():
    """The guard rail on the guard rail.

    A fuzzy threshold loose enough to accept 'Jiri Lehecka' for 'Jiří Lehečka'
    is loose enough to accept some other player eventually, and that is how the
    WTA fabrication survived. These two names share most of their characters
    and are different people; nothing about character overlap may be consulted.
    """
    assert not identity_matches("Alex de Minaur", "Alex Michelsen")
    assert not identity_matches("Taylor Fritz", "Taylor Townsend")


def test_folding_strips_punctuation_and_case_but_keeps_tokens():
    assert _fold_player_name("Jean-Julien  ROJER") == {"jean", "julien", "rojer"}
    assert _fold_player_name("") == frozenset()


# --- routes: the right player is not yet the right era --------------------


def test_atp_route_is_tried_before_the_wta_one():
    """Order matters and is load-bearing, for a reason that is not obvious.

    /jsmatches/<name>.js exists for ATP players too, but it is abandoned data:
    on 2026-08-28 JannikSinner.js held 34 matches whose newest was 2018-11-19,
    while player-classic.cgi held his current season. Preferring jsmatches
    would swap one silent lie (another player's matches) for another (the right
    player's, from eight years ago).
    """
    labels = [label for label, _ in _ROUTES]
    assert labels.index("player-classic") < labels.index("jsmatches")
    assert labels.index("jsmatches") < labels.index("jsmatches-career")


def test_freshness_window_rejects_the_abandoned_2018_files():
    # The abandoned ATP jsmatches files are ~8 years stale; the window has to
    # sit well inside that while still tolerating an injured player's layoff.
    assert 180 <= STALE_ROUTE_DAYS <= 730
    assert not TennisAbstractClient._is_fresh("2018-11-19")
    assert not TennisAbstractClient._is_fresh("")
    assert not TennisAbstractClient._is_fresh(None)


# --- opponents: refusing to guess -----------------------------------------


def _fixture(**kwargs):
    base = {
        "home_team": "", "away_team": "",
        "home_participant_id": "", "away_participant_id": "",
    }
    base.update(kwargs)
    return base


def test_opponent_resolves_from_participant_ids_on_either_side():
    """espn-tennis rows: the player may be listed first or second.

    Shapes taken from the live 2026-08-22 ESPN scoreboard.
    """
    listed_first = _fixture(
        home_team="Iga Swiatek", home_participant_id="3730",
        away_team="Jessica Pegula", away_participant_id="2113",
    )
    listed_second = _fixture(
        home_team="Elena Rybakina", home_participant_id="3126",
        away_team="Iga Swiatek", away_participant_id="3730",
    )
    assert _opponent_of(listed_first, "3730") == "Jessica Pegula"
    assert _opponent_of(listed_second, "3730") == "Elena Rybakina"


def test_opponent_is_never_the_player_himself():
    """The regression, stated as the thing that must not happen.

    Before the fix, a row that identified neither side still produced a
    confident answer, and that answer was the player himself whenever he was
    listed first -- so half of every espn-tennis L10 recorded 'Iga Swiatek vs
    Iga Swiatek' and the sheet averaged it in.
    """
    row = _fixture(
        home_team="Iga Swiatek", home_participant_id="3730",
        away_team="Jessica Pegula", away_participant_id="2113",
    )
    assert _opponent_of(row, "3730") != "Iga Swiatek"


def test_unattributable_row_returns_none_rather_than_guessing():
    """A row that cannot say which side the player was on has no opponent.

    This is the v1 espn-tennis row shape -- two display names, no ids -- which
    a twelve-hour cache can still be holding after the fix ships.
    """
    row = {"home_team": "Iga Swiatek", "away_team": "Jessica Pegula"}
    assert _opponent_of(row, "3730") is None


def test_empty_id_fields_do_not_match_an_empty_team_id():
    """NormalizedFixture defaults both id fields to ''. An empty team_id must
    not therefore 'match' the home side and invent an opponent."""
    row = _fixture(home_team="A", away_team="B")
    assert _opponent_of(row, "") is None


def test_name_keyed_providers_still_resolve():
    """tennis-abstract keys rows by the player's name, not an id, and must keep
    working -- the strictness is aimed at unattributable rows, not at this."""
    row = _fixture(home_team="Carlos Alcaraz", away_team="Tomas Machac")
    assert _opponent_of(row, "Carlos Alcaraz") == "Tomas Machac"


# --- the roster -----------------------------------------------------------


def test_sackmann_is_restored_and_asserted():
    """github.com/JeffSackmann/tennis_atp and tennis_wta both 404'd at the
    *repository* level 2026-08-28 (the GitHub API answered "Not Found" for
    each, while the account itself stayed alive). Restored 2026-09-15 pointed
    at stats.tennismylife.org, which republishes the identical column schema
    (verified column-for-column, and cross-checked against tennis-abstract's
    own cache the day it was found) under a live, free, MIT-licensed API.

    It covers ATP (incl. Challenger, qualifying) and WTA Tour -- checked
    directly against the file listing, not the marketing page -- and nothing
    at ITF or WTA Challenger level, so it stays second in the roster, behind
    tennis-abstract, as a corroborator rather than a primary."""
    assert "sackmann" in PROVIDERS_BY_SPORT["tennis"]
    assert PROVIDERS_BY_SPORT["tennis"].index("sackmann") > PROVIDERS_BY_SPORT["tennis"].index(
        "tennis-abstract"
    )
    assert "sackmann" in _H2H_SUPPORTED_PROVIDERS
    assert "sackmann" not in KNOWN_DEAD_PROVIDERS


def test_tennis_still_has_two_independent_providers():
    """Two is the number that matters: cross-provider agreement needs two, and
    dropping sackmann must not have left the sport single-sourced."""
    assert len(PROVIDERS_BY_SPORT["tennis"]) >= 2


# --- the live verification ------------------------------------------------
#
# config/tennis_provider_verification.json is written by
# scripts/simple/verify_tennis_providers.py, which resolves each rostered
# player through the production client, fetches his matches, and requires every
# returned row to be named for him by the provider's own name field. It is an
# allowlist: a provider asserted in PROVIDERS_BY_SPORT that the artifact does
# not carry fails the suite.
VERIFICATION = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "config" / "tennis_provider_verification.json"
    ).read_text(encoding="utf-8")
)


def test_every_asserted_tennis_provider_was_proved_on_both_tours():
    """The only test here that can fail because a provider changed rather than
    because the repo did -- rerun scripts/simple/verify_tennis_providers.py.

    Both tours, because that is exactly the axis along which tennis-abstract
    was broken: it proved fine for every ATP player anyone tried, and served
    Benoit Paire to the entire WTA.
    """
    for tour in ("atp", "wta"):
        proved = VERIFICATION["tours"].get(tour, {})
        for provider in PROVIDERS_BY_SPORT["tennis"]:
            players = proved.get(provider) or {}
            assert players, (
                f"{provider} is asserted for tennis but proved no {tour.upper()} "
                f"player; run scripts/simple/verify_tennis_providers.py"
            )


def test_every_proved_player_carries_the_providers_own_name_for_him():
    """An entry without the provider's name field is not evidence of identity,
    it is evidence that something answered."""
    for tour, providers in VERIFICATION["tours"].items():
        for provider, players in providers.items():
            for player, entry in players.items():
                assert entry.get("provider_name"), (
                    f"{tour}/{provider}/{player} was recorded without the "
                    f"provider's own name for the player"
                )
                assert identity_matches(player, entry["provider_name"]), (
                    f"{tour}/{provider}/{player} was proved against "
                    f"{entry['provider_name']!r}, which is a different player"
                )


def test_every_proved_player_actually_returned_matches():
    """Resolving is not serving. espn-tennis resolved every ATP player it was
    asked about while returning zero matches for most of them."""
    for tour, providers in VERIFICATION["tours"].items():
        for provider, players in providers.items():
            for player, entry in players.items():
                assert entry.get("match_count", 0) > 0, (
                    f"{tour}/{provider}/{player} resolved but returned no matches"
                )
                assert entry.get("newest_match"), (
                    f"{tour}/{provider}/{player} returned matches with no date"
                )


def test_verification_artifact_records_how_it_was_produced():
    assert VERIFICATION["verified_by"].endswith("verify_tennis_providers.py")
    assert "name field" in VERIFICATION["probe"]
    assert VERIFICATION["last_run"]


# --- the fabrication, end to end ------------------------------------------


class _FakePage:
    def __init__(self, body, status_code=200):
        self.text = body
        self.status_code = status_code


def _page(fullname, rows):
    """A tennisabstract page body: an identity claim plus a match table."""
    return (
        f"<html><script>var fullname = '{fullname}';\n"
        f"var matchmx = {rows!r};</script></html>"
    ).replace("'", "'")


# One real row, trimmed to the columns _create_match_dicts reads. Shape taken
# from the live 2026-08-28 payloads; index 21 onward is the serve line.
def _row(date, opponent, aces):
    row = [""] * 44
    row[0], row[1], row[2], row[3], row[4] = date, "Cincinnati", "Hard", "M", "W"
    row[8], row[9], row[11], row[12] = "F", "6-4 6-4", opponent, "10"
    row[21], row[22], row[23], row[24] = str(aces), "1", "70", "45"
    row[25], row[26], row[27], row[28], row[29] = "30", "15", "10", "2", "4"
    row[30], row[31], row[32], row[33] = "3", "2", "68", "40"
    row[34], row[35], row[36], row[37], row[38] = "28", "14", "10", "1", "3"
    return row


@pytest.fixture
def offline_client(monkeypatch):
    """A client whose only contact with the world is the routes dict below."""
    client = TennisAbstractClient.__new__(TennisAbstractClient)
    client.api_name = "tennis-abstract"
    client._last_matches_cache = {}
    client._proved_names = {}
    monkeypatch.setattr(client, "_check_cache", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(client, "_save_to_cache", lambda *a, **k: None, raising=False)
    return client


def _serve(client, monkeypatch, by_url):
    """Wire a fake ``_make_scrape_request`` that always succeeds or 404s.

    Matches ``TennisAbstractClient._ScrapeAttempt``'s contract: a body means a
    clean 200, ``None`` means a clean "nothing here" (404), and ``failed`` is
    never set here because these tests are not about retries or rate limits
    -- see ``test_transient_failure_*`` below for those.
    """
    from bet.api_clients.tennis_abstract import _ScrapeAttempt

    seen = []

    def fake_request(url, label="", retries=None):
        seen.append(url)
        body = by_url.get(next((k for k in by_url if k in url), ""), None)
        return _ScrapeAttempt(response=_FakePage(body) if body is not None else None)

    monkeypatch.setattr(client, "_make_scrape_request", fake_request, raising=False)
    return seen


def test_the_wta_page_swap_is_refused_and_the_real_route_is_used(
    offline_client, monkeypatch
):
    """The exact 2026-08-28 fabrication, reproduced offline.

    player-classic.cgi answers 200 with Benoit Paire's table for a WTA request;
    jsmatches answers with hers. The old client took the first non-empty match
    table it found, which was his.
    """
    seen = _serve(offline_client, monkeypatch, {
        "player-classic.cgi": _page("Benoit Paire", [_row("20260810", "Jo Wilfried Tsonga", 9)]),
        "jsmatches/IgaSwiatek.js": _page("Iga Swiatek", [_row("20260813", "Jessica Pegula", 1)]),
    })

    matches = offline_client._fetch_player_matches("Iga Swiatek")

    assert matches, "the WTA route must still serve her matches"
    assert {m["opp"] for m in matches} == {"Jessica Pegula"}
    assert "Jo Wilfried Tsonga" not in {m["opp"] for m in matches}
    assert offline_client._proved_names["IgaSwiatek"] == "Iga Swiatek"
    # It must have *looked* at the ATP route and rejected it, not skipped it.
    assert any("player-classic.cgi" in url for url in seen)


def test_a_player_the_site_does_not_have_resolves_to_nothing(
    offline_client, monkeypatch
):
    """No identity claim anywhere is an unresolved player, not an empty one --
    and certainly not whoever's table happened to be on the page."""
    _serve(offline_client, monkeypatch, {
        "player-classic.cgi": _page("Benoit Paire", [_row("20260810", "Someone", 9)]),
    })
    assert offline_client._fetch_player_matches("Zzzz Notarealplayer") is None
    assert offline_client.resolve_team_id("Zzzz Notarealplayer") is None


def test_a_stale_route_loses_to_a_fresh_one(offline_client, monkeypatch):
    """Both routes are the right player; only one is this decade.

    This is the abandoned-2018-jsmatches case, and the reason route order alone
    is not enough: the fresher table must win even when the stale one is
    perfectly well identified.
    """
    from datetime import UTC, datetime

    recent = datetime.now(UTC).strftime("%Y%m%d")
    _serve(offline_client, monkeypatch, {
        # player-classic is tried first and proves identity, but is ancient.
        "player-classic.cgi": _page("Jannik Sinner", [_row("20181119", "Old Opponent", 4)]),
        "jsmatches/JannikSinner.js": _page("Jannik Sinner", [_row(recent, "Alexander Zverev", 6)]),
    })

    matches = offline_client._fetch_player_matches("Jannik Sinner")

    assert {m["opp"] for m in matches} == {"Alexander Zverev"}


def test_a_stale_route_is_still_used_when_nothing_fresher_exists(
    offline_client, monkeypatch
):
    """Being the only evidence beats being no evidence -- an injured player's
    real history is worth having, as long as nobody pretends it is current."""
    _serve(offline_client, monkeypatch, {
        "player-classic.cgi": _page("Carlos Alcaraz", [_row("20260413", "Tomas Machac", 5)]),
    })
    matches = offline_client._fetch_player_matches("Carlos Alcaraz")
    assert {m["opp"] for m in matches} == {"Tomas Machac"}


def test_a_cache_entry_without_an_identity_proof_is_not_trusted(
    offline_client, monkeypatch
):
    """Entries written before the identity check may hold anyone's matches, so
    they are re-fetched rather than served for another six hours."""
    monkeypatch.setattr(
        offline_client, "_check_cache",
        lambda *a, **k: {"matches": [{"opp": "Benoit Paire's victim", "date": "2026-08-10"}]},
        raising=False,
    )
    _serve(offline_client, monkeypatch, {
        "jsmatches/IgaSwiatek.js": _page("Iga Swiatek", [_row("20260813", "Jessica Pegula", 1)]),
    })

    matches = offline_client._fetch_player_matches("Iga Swiatek")

    assert {m["opp"] for m in matches} == {"Jessica Pegula"}


# --- h2h scoping ----------------------------------------------------------


def test_h2h_passes_the_competition_through_to_the_provider_client():
    """The competition is what scopes the client: espn-football cannot build
    one without it, and espn-tennis silently searches the wrong tour. Every
    other entry point threaded it; this one dropped it on the floor."""
    from bet.simple_stats import providers

    seen = []

    def spy(provider, one, two, limiter, last_n=10, competition=""):
        seen.append(competition)
        return providers.FetchOutcome()

    original = providers._fetch_h2h_generic
    providers._fetch_h2h_generic = spy
    try:
        providers.fetch_h2h_metrics(
            "tennis", "Iga Swiatek", "Aryna Sabalenka", None, competition="WTA Tour"
        )
    finally:
        providers._fetch_h2h_generic = original

    assert seen, "no h2h-capable tennis provider was called"
    assert set(seen) == {"WTA Tour"}


def test_h2h_meetings_carry_a_redeemable_fixture_id(offline_client, monkeypatch):
    """The silent-nothing bug: H2H returned raw rows with no id of any kind.

    providers._fetch_h2h_generic reads id/fixture_id off each meeting and skips
    the ones without, so it skipped every one -- and recorded no data_gap
    either, because from its point of view nothing had failed. tennis-abstract
    H2H returned exactly nothing for its whole existence, quietly, which left
    ANALYZE unable to tell "they have never met" from "the provider never ran".
    """
    _serve(offline_client, monkeypatch, {
        "player-classic.cgi": _page("Jannik Sinner", [
            _row("20260712", "Alexander Zverev", 6),
            _row("20260710", "Novak Djokovic", 11),
            _row("20260601", "Novak Djokovic", 8),
        ]),
    })

    meetings = offline_client.get_h2h("Jannik Sinner", "Novak Djokovic")

    assert len(meetings) == 2, "only the Djokovic meetings are h2h"
    for meeting in meetings:
        assert meeting["id"] and meeting["fixture_id"] == meeting["id"]
        # An id the caller cannot redeem is no better than no id.
        stats = offline_client.get_fixture_stats(meeting["id"])
        assert stats is not None
        assert stats.away_team == "Novak Djokovic"


def test_h2h_opponent_matching_is_not_fuzzy(offline_client, monkeypatch):
    """Both strings come from tennisabstract itself, so they are compared.

    A rapidfuzz ratio of 85 was how the opponent used to be matched -- the same
    mistake, one level down, that let another player's entire page through.
    """
    _serve(offline_client, monkeypatch, {
        "player-classic.cgi": _page("Alexander Zverev", [
            _row("20260712", "Mischa Zverev", 6),
            _row("20260710", "Jannik Sinner", 11),
        ]),
    })

    assert offline_client.get_h2h("Alexander Zverev", "Jannik Sinner")
    assert not offline_client.get_h2h("Alexander Zverev", "Alexander Bublik")


def test_last_fixtures_does_not_wipe_cached_h2h_rows(offline_client, monkeypatch):
    """The two paths share one cache; replacing it lost whichever ran first."""
    _serve(offline_client, monkeypatch, {
        "player-classic.cgi": _page("Jannik Sinner", [
            _row("20260710", "Novak Djokovic", 11),
            _row("20260712", "Alexander Zverev", 6),
        ]),
    })

    meetings = offline_client.get_h2h("Jannik Sinner", "Novak Djokovic")
    offline_client.get_team_last_fixtures("Jannik Sinner", last_n=10)

    assert offline_client.get_fixture_stats(meetings[0]["id"]) is not None


# --- transient failure vs. genuine absence ---------------------------------
#
# Live on 2026-09-14: eight ``player-classic`` requests fired at once
# (ThreadPoolExecutor(max_workers=8), matching enrich.py) drew Cloudflare 429s,
# each with a real ``Retry-After`` header, past the first three to five --
# not a connection reset or a timeout. Retrying once ``Retry-After`` elapsed
# always got a 200 with fresh 2026 rows. The tests below reproduce that
# distinction offline: a route that never actually answered must not be read
# the same way as a route that answered and had nothing.


class _FakeResponse:
    def __init__(self, status_code, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class _ScriptedSession:
    """A fake ``requests.Session`` whose ``.get()`` answers from a per-URL script.

    Each key's script is a list of responses/exceptions, consumed in order and
    held at the last entry once exhausted -- so "429 forever" is one-element
    list, and "429 twice then 200" is a three-element list.
    """

    def __init__(self, scripts):
        self.scripts = {
            k: (v if isinstance(v, list) else [v]) for k, v in scripts.items()
        }
        self._counts = {k: 0 for k in self.scripts}
        self.calls: list[str] = []

    def get(self, url, timeout=15):
        self.calls.append(url)
        key = next((k for k in self.scripts if k in url), None)
        if key is None:
            return _FakeResponse(404)
        script = self.scripts[key]
        idx = min(self._counts[key], len(script) - 1)
        self._counts[key] += 1
        outcome = script[idx]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _raw_client(monkeypatch, scripts):
    """A client with a scripted session, no cache, no pacing, no real sleeps."""
    client = TennisAbstractClient.__new__(TennisAbstractClient)
    client.api_name = "tennis-abstract"
    client._last_matches_cache = {}
    client._proved_names = {}
    client._session = _ScriptedSession(scripts)
    monkeypatch.setattr(client, "_check_cache", lambda *a, **k: None, raising=False)
    saved: dict[str, dict] = {}
    monkeypatch.setattr(
        client, "_save_to_cache",
        lambda key, data: saved.__setitem__(key, data), raising=False,
    )
    monkeypatch.setattr(ta_module, "_pace", lambda *a, **k: None)
    monkeypatch.setattr(ta_module.time, "sleep", lambda *a, **k: None)
    return client, saved


def _pc_calls(client):
    return [c for c in client._session.calls if "player-classic" in c]


def test_baseline_player_classic_succeeds_first_try_no_fallback(monkeypatch):
    """The happy path: unchanged. One request, fresh data, no fallback."""
    client, saved = _raw_client(monkeypatch, {
        "player-classic.cgi": _FakeResponse(
            200, _page("Carlos Alcaraz", [_row("20260901", "Jannik Sinner", 10)])
        ),
    })

    matches = client._fetch_player_matches("Carlos Alcaraz")

    assert {m["opp"] for m in matches} == {"Jannik Sinner"}
    assert len(client._session.calls) == 1, "no retry, no fallback route touched"
    record = saved["tennis-abstract/player/CarlosAlcaraz"]
    assert record["route"] == "player-classic"
    assert "fallback_reason" not in record


def test_transient_failure_then_success_recovers_the_live_route(monkeypatch):
    """The exact bug: player-classic 429s twice, then succeeds.

    Must retry through it and use the fresh data -- not fall through to
    jsmatches's stale table, which is what the un-fixed client did.
    """
    fresh = _page("Tallon Griekspoor", [_row("20260901", "Jack Draper", 7)])
    stale = _page("Tallon Griekspoor", [_row("20181029", "Old Opponent", 3)])
    client, saved = _raw_client(monkeypatch, {
        "player-classic.cgi": [
            _FakeResponse(429, headers={"Retry-After": "2"}),
            _FakeResponse(429, headers={"Retry-After": "2"}),
            _FakeResponse(200, fresh),
        ],
        "jsmatches/TallonGriekspoor.js": _FakeResponse(200, stale),
    })

    matches = client._fetch_player_matches("Tallon Griekspoor")

    assert {m["opp"] for m in matches} == {"Jack Draper"}
    assert len(_pc_calls(client)) == 3, "two 429s, then the recovering attempt"
    assert not any("jsmatches" in c for c in client._session.calls), (
        "jsmatches must never be touched once player-classic recovered"
    )
    record = saved["tennis-abstract/player/TallonGriekspoor"]
    assert record["route"] == "player-classic"
    assert "fallback_reason" not in record


def test_genuine_exhaustion_falls_through_and_is_marked_failure_driven(monkeypatch):
    """player-classic 429s on every attempt -- real exhaustion, not one bad
    roll. Falls through to jsmatches, but the cached record must say the
    fallback happened because the live route failed, not because it was ever
    proven not to have him."""
    stale = _page("Tallon Griekspoor", [_row("20181029", "Old Opponent", 3)])
    client, saved = _raw_client(monkeypatch, {
        "player-classic.cgi": _FakeResponse(429, headers={"Retry-After": "3"}),
        "jsmatches/TallonGriekspoor.js": _FakeResponse(200, stale),
    })

    matches = client._fetch_player_matches("Tallon Griekspoor")

    assert {m["opp"] for m in matches} == {"Old Opponent"}
    assert len(_pc_calls(client)) == _ROUTE_RETRIES["player-classic"], (
        "player-classic gets its full, larger retry budget before giving up"
    )
    record = saved["tennis-abstract/player/TallonGriekspoor"]
    assert record["route"] == "jsmatches"
    assert record["fallback_reason"] == "transient_failure"


def test_genuine_wrong_player_absence_is_not_marked_as_failure(monkeypatch):
    """player-classic answers every time with Benoit Paire's page -- a clean
    identity refusal, proven absent, not a failure. Must not be retried like
    one, and must not carry the failure-driven marker."""
    client, saved = _raw_client(monkeypatch, {
        "player-classic.cgi": _FakeResponse(
            200, _page("Benoit Paire", [_row("20260810", "Someone", 5)])
        ),
        "jsmatches/IgaSwiatek.js": _FakeResponse(
            200, _page("Iga Swiatek", [_row("20260813", "Jessica Pegula", 1)])
        ),
    })

    matches = client._fetch_player_matches("Iga Swiatek")

    assert {m["opp"] for m in matches} == {"Jessica Pegula"}
    assert len(_pc_calls(client)) == 1, "an identity refusal is not a failure, not retried"
    record = saved["tennis-abstract/player/IgaSwiatek"]
    assert "fallback_reason" not in record


def test_404_is_treated_as_absence_not_retried_like_a_failure(monkeypatch):
    """A 404 will not turn into a 200 on retry; retrying it wastes politeness
    budget for nothing and must not happen."""
    client, saved = _raw_client(monkeypatch, {
        "player-classic.cgi": _FakeResponse(404),
        "jsmatches/ZzzzNotarealplayer.js": _FakeResponse(404),
        "jsmatches/ZzzzNotarealplayerCareer.js": _FakeResponse(404),
    })

    matches = client._fetch_player_matches("Zzzz Notarealplayer")

    assert matches is None
    assert len(_pc_calls(client)) == 1
    assert "tennis-abstract/player/ZzzzNotarealplayer" not in saved


def test_backoff_honours_retry_after_and_is_not_a_tight_loop(monkeypatch):
    """Assert real backoff behaviour via mocked ``time.sleep`` -- the server's
    own ``Retry-After`` is used verbatim (within the polite bounds), not a
    flat or trivially-short delay."""
    sleeps = []
    monkeypatch.setattr(ta_module.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(ta_module, "_pace", lambda *a, **k: None)
    monkeypatch.setattr(ta_module.random, "uniform", lambda a, b: 0.0)

    client = TennisAbstractClient.__new__(TennisAbstractClient)
    client.api_name = "tennis-abstract"
    client._session = _ScriptedSession({
        "player-classic.cgi": [
            _FakeResponse(429, headers={"Retry-After": "5"}),
            _FakeResponse(429, headers={"Retry-After": "3"}),
            _FakeResponse(200, _page("Carlos Alcaraz", [_row("20260901", "X", 1)])),
        ],
    })

    attempt = client._make_scrape_request(
        "https://www.tennisabstract.com/cgi-bin/player-classic.cgi?p=CarlosAlcaraz",
        label="player-classic",
    )

    assert attempt.response is not None and not attempt.failed
    assert sleeps == [5.0, 3.0], (
        "must wait exactly what the server asked for, not a flat/tight retry"
    )


def test_transient_fallback_cache_expires_within_the_short_ttl(monkeypatch):
    """A failure-driven stale fallback is not trusted for the normal 6h.

    Within TRANSIENT_FALLBACK_TTL_HOURS it is still served (no need to hammer
    the site again seconds later); past it, it is treated as a cache miss so a
    retry can recover the real route -- rather than being stuck with an
    eight-year-old sample for the rest of the 6h window.
    """
    from datetime import datetime, timedelta, timezone

    client = TennisAbstractClient.__new__(TennisAbstractClient)
    client.api_name = "tennis-abstract"
    client._proved_names = {}

    stale_matches = [{"opp": "Old Opponent", "date": "2018-10-29"}]

    def cached_at(age):
        return {
            "matches": stale_matches,
            "proved_name": "Tallon Griekspoor",
            "route": "jsmatches",
            "newest_match": "2018-10-29",
            "fallback_reason": "transient_failure",
            "last_updated": (datetime.now(timezone.utc) - age).isoformat(),
        }

    # Within the short TTL: served as-is, no refetch attempted.
    monkeypatch.setattr(
        client, "_check_cache",
        lambda *a, **k: cached_at(timedelta(minutes=5)), raising=False,
    )

    def must_not_refetch(*a, **k):
        raise AssertionError("must not refetch within the short TTL")

    monkeypatch.setattr(client, "_fetch_route", must_not_refetch, raising=False)
    assert client._fetch_player_matches("Tallon Griekspoor") == stale_matches
    assert TRANSIENT_FALLBACK_TTL_HOURS < 1, "sanity: the short TTL really is short"

    # Past the short TTL (but still well within the normal 6h): a miss.
    monkeypatch.setattr(
        client, "_check_cache",
        lambda *a, **k: cached_at(timedelta(hours=1)), raising=False,
    )
    refetched_labels = []

    def refetch(url, label, player_name):
        refetched_labels.append(label)
        if label != "player-classic":
            return None
        return {
            "label": "player-classic", "proved_name": "Tallon Griekspoor",
            "matches": [{"opp": "Jack Draper", "date": "2026-09-01"}],
            "newest": "2026-09-01",
        }

    monkeypatch.setattr(client, "_fetch_route", refetch, raising=False)
    monkeypatch.setattr(client, "_save_to_cache", lambda *a, **k: None, raising=False)

    matches = client._fetch_player_matches("Tallon Griekspoor")

    assert refetched_labels, "an expired failure-driven fallback must trigger a real refetch"
    assert {m["opp"] for m in matches} == {"Jack Draper"}


def test_pacer_serializes_requests_issued_from_multiple_threads(monkeypatch):
    """The other half of the bug: get_client() builds a fresh client and
    session per call, so nothing but a module-level pacer can space out the
    eight concurrent requests enrich.py's ThreadPoolExecutor(max_workers=8)
    issues. Real threads, real elapsed time, mocked HTTP layer -- no network.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(ta_module, "_next_allowed_request_time", 0.0)

    lock = threading.Lock()
    stamps: list[float] = []

    def call(_):
        ta_module._pace(min_interval=0.05)
        with lock:
            stamps.append(time.monotonic())

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(call, range(6)))

    stamps.sort()
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    assert all(gap >= 0.04 for gap in gaps), (
        f"pacer did not serialize across threads: gaps were {gaps}"
    )
