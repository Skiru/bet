"""ESPN league resolution: what the map may assert, and where it must stay silent.

A wrong answer here is worse than none. `_provider_client` pins the ESPN client
to whatever code comes back, so a bad pin sends a Saudi club into a Premier
League team search -- which either finds nothing (a data_gap blaming the team
name for a league problem) or quietly answers with the wrong club's season.

The starting dataset is real: the 41 distinct football competition names in
runs/2026-08-28/2026-08-28_event_list.json. Every expected code in this file
was verified live against ESPN on 2026-08-28 by requesting
/apis/site/v2/sports/soccer/<code>/teams and requiring a non-empty directory --
nothing here is asserted from the shape of the old table, which turned out to
contain 18 codes ESPN does not serve at all.

These tests make no network calls. The competition table and the pin-agreement
gate are both pure functions; the live probing that produced their expected
values is recorded in the comments, not re-run per test.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bet.api_clients.espn import (
    COMPETITION_TO_ESPN_LEAGUE,
    ESPN_COUNTRY_CODE_PREFIXES,
    ESPN_FOOTBALL_LEAGUE_CODES,
    _ESPN_FOOTBALL_COMPETITIONS,
    _ESPN_TOKEN_SYNONYMS,
    _build_espn_signature_index,
    _espn_name_signature,
    _fold_espn_participant_name,
)
from bet.api_clients.espn import get_espn_league_for_competition as resolve
from bet.simple_stats.providers import (
    espn_competition_coverage,
    _ESPN_NON_COUNTRY_PREFIXES,
    _ESPN_PIN_COUNTRY_WORDS,
    _espn_pin_contradicted,
    _ESPNDirectory,
)

# ESPN's non-football /teams surface was never probed, so these codes are not
# in the verification artifact and are kept out of ESPN_FOOTBALL_LEAGUE_CODES.
# Unverified and unreachable-as-football is a defensible position; unverified
# and reachable is not.
NON_FOOTBALL_CODES = {"atp", "wta", "fivb.m", "fivb.w"}

# --- the real slate ------------------------------------------------------

# Ground truth for every football competition name in the 2026-08-28 run.
# None is an answer, not a gap: it means ESPN has no usable surface for that
# competition, or that the name alone does not identify one.
SLATE_2026_08_28 = {
    # --- ESPN serves these -------------------------------------------
    "Austrian Football Bundesliga": "aut.1",
    "Belgium First Div": "bel.1",
    "Brasileirão Serie B": "bra.2",
    "Brazil Série B": "bra.2",
    "Bundesliga": "ger.1",  # added when the run was re-measured
    "Bundesliga - Germany": "ger.1",
    "Bundesliga 2 - Germany": "ger.2",
    "Categoría Primera A": "col.1",
    "Championship": "eng.2",
    "Chinese Super League": "chn.1",
    "Copa Argentina": "arg.copa",  # added when the run was re-measured
    "Denmark Superliga": "den.1",
    "Dutch Eredivisie": "ned.1",
    "EPL": "eng.1",
    "Eerste Divisie": "ned.2",  # added when the run was re-measured
    "Jupiler Pro League": "bel.1",  # added when the run was re-measured
    "La Liga": "esp.1",
    "La Liga - Spain": "esp.1",
    "La Liga 2 - Spain": "esp.2",
    "League Two": "eng.4",  # added when the run was re-measured
    "Liga Portugal Betclic": "por.1",
    "Liga Profesional de Fútbol": "arg.1",
    "Liga de Expansión MX": "mex.2",  # added when the run was re-measured
    # Bare "Ligue 1"/"Ligue 2" stopped resolving on 2026-09-02: on this very
    # slate the bare rows were JS El Biar, US Biskra and company -- Algeria,
    # not France -- and one name cannot be two countries' ground truth.
    "Ligue 1": None,
    "Ligue 1 - France": "fra.1",
    "Ligue 2": None,
    "Ligue 2 - France": "fra.2",
    "National League": "eng.5",
    "Nigeria Premier Football League": "nga.1",
    "Premier League": "eng.1",  # added when the run was re-measured
    "Premier League - Russia": "rus.1",
    "Premiership": "sco.1",  # added when the run was re-measured
    "Primeira Liga - Portugal": "por.1",
    "Primera A": "col.1",  # added when the run was re-measured
    "Primera División - Argentina": "arg.1",
    "Primera División - Chile": "chi.1",
    # Four of this slate's five bare "Pro League" fixtures were Abha, Al Wasl,
    # Al Riyadh and Dubai United -- Saudi Arabia and the UAE, not Belgium. The
    # old bel.1 entry here was itself the wrong answer for most of them.
    "Pro League": None,
    "Saudi Pro League": "ksa.1",
    "Segunda División": "esp.2",  # added when the run was re-measured
    "Serie A - Italy": "ita.1",
    # Bare "Serie B" on this slate was Nautico Recife and Novorizontino:
    # Brazil's second tier, which ita.2 is not.
    "Serie B": None,
    "Serie B - Italy": "ita.2",
    "Super League - China": "chn.1",
    "Taça de Portugal": "por.taca.portugal",  # added when the run was re-measured
    "Trendyol Super Lig": "tur.1",
    "Turkey Super League": "tur.1",
    # --- ESPN has no usable surface for these ------------------------
    # None is an answer, not a gap. Most are women's, youth, regional or
    # cup competitions for which ESPN publishes no team directory; the
    # provider is dropped for them, which is the safe outcome.
    "1 Lyga": None,  # added when the run was re-measured
    "1. Deild": None,  # added when the run was re-measured
    "1. Lig": None,  # added when the run was re-measured
    "1. SNL": None,  # added when the run was re-measured
    "1st Division": None,  # added when the run was re-measured
    "1st League - RS": None,  # added when the run was re-measured
    "2. Liga": None,  # added when the run was re-measured
    "2. SNL": None,  # added when the run was re-measured
    "2. liga": None,  # added when the run was re-measured
    "2nd Division - Group 1": None,  # added when the run was re-measured
    "3. Liga - Germany": None,
    "CBF Brasileiro U20": None,  # added when the run was re-measured
    "Calcutta Premier Division": None,  # added when the run was re-measured
    "Campionato": None,  # added when the run was re-measured
    "Canadian Premier League": None,  # added when the run was re-measured
    "Central Youth League": None,  # added when the run was re-measured
    "Challenge League": None,  # added when the run was re-measured
    "Challenger Pro League": None,  # added when the run was re-measured
    "Club Friendlies": None,
    "Concacaf Central American Cup": None,  # added when the run was re-measured
    "Damallsvenskan": None,  # added when the run was re-measured
    "Division 1": None,  # added when the run was re-measured
    "Division Intermedia": None,  # added when the run was re-measured
    "Division Profesional - Clausura": None,  # added when the run was re-measured
    "Druha Liga": None,  # added when the run was re-measured
    "Ekstraklasa - Poland": None,
    "Elitettan": None,  # added when the run was re-measured
    "Erovnuli Liga 2": None,  # added when the run was re-measured
    "FA Trophy": None,  # added when the run was re-measured
    "FAW Championship": None,  # added when the run was re-measured
    "FNL": None,  # added when the run was re-measured
    "First Division": None,  # added when the run was re-measured
    "First Division League (FDL)": None,  # added when the run was re-measured
    "First League": None,  # added when the run was re-measured
    "First NL": None,  # added when the run was re-measured
    "Frauen Bundesliga": None,  # added when the run was re-measured
    "Frauen-Bundesliga": None,
    "Friendlies Clubs": None,  # added when the run was re-measured
    "Girabola": None,  # added when the run was re-measured
    "I Liga": None,  # added when the run was re-measured
    "K League 2": None,  # added when the run was re-measured
    "League of Ireland": None,
    "Liga 1": None,  # added when the run was re-measured
    "Liga E Pare": None,  # added when the run was re-measured
    "Liga I": None,  # added when the run was re-measured
    "Liga MX U21": None,  # added when the run was re-measured
    "Liga Portugal 2": None,
    "Liga Premier Serie B": None,  # added when the run was re-measured
    "Liga Pro": None,  # added when the run was re-measured
    "Liga Pro Serie B": None,  # added when the run was re-measured
    "Liga Women": None,  # added when the run was re-measured
    "Liga de Ascenso": None,  # added when the run was re-measured
    "Ligi kuu Bara": None,  # added when the run was re-measured
    "Ligue A": None,  # added when the run was re-measured
    "MLS Next Pro": None,  # added when the run was re-measured
    "Mediterranean Games": None,  # added when the run was re-measured
    "Meistaradeildin": None,  # added when the run was re-measured
    "Mineiro U20": None,  # added when the run was re-measured
    "NB I": None,  # added when the run was re-measured
    "Nacional B": None,  # added when the run was re-measured
    "Nationalliga A Women": None,  # added when the run was re-measured
    "Oberliga - Bremen": None,  # added when the run was re-measured
    "Parva Liga": None,
    "Paulista - U20": None,  # added when the run was re-measured
    "Persha Liga": None,  # added when the run was re-measured
    "Pershaya Liga": None,  # added when the run was re-measured
    "Persian Gulf Pro League": None,  # added when the run was re-measured
    "Premier Division": None,  # added when the run was re-measured
    "Premier League 2 Division One": None,  # added when the run was re-measured
    "Premiership Women": None,  # added when the run was re-measured
    "Premijer Liga": None,  # added when the run was re-measured
    "Primera B": None,  # added when the run was re-measured
    "Primera Division": None,  # added when the run was re-measured
    "Primera División": None,  # added when the run was re-measured
    "Primera División - Apertura": None,  # added when the run was re-measured
    "Pro League A": None,  # added when the run was re-measured
    "Regionalliga - North": None,  # added when the run was re-measured
    "Regionalliga - South": None,  # added when the run was re-measured
    "Second NL": None,  # added when the run was re-measured
    "South Australia State League 1": None,  # added when the run was re-measured
    "Stars League": None,  # added when the run was re-measured
    "Super League": None,  # added when the run was re-measured
    "Superliga": None,
    # Was None on 2026-08-28; pinned 2026-09-02 after usa.usl.l1 was probed
    # live (17 teams). A separate, lower division from usa.usl.1.
    "USL League One": "usa.usl.l1",
    "USL Super League": None,  # added when the run was re-measured
    "Vysshaya Liga": None,  # added when the run was re-measured
    "Vysshaya Liga Women": None,  # added when the run was re-measured
    "WK-League": None,  # added when the run was re-measured
    "Ykkösliiga": None,  # added when the run was re-measured
    "Youth Championship": None,  # added when the run was re-measured
}


def test_the_slate_ground_truth_still_covers_the_whole_run():
    """If the run file ever grows a competition, this test names it rather than
    letting it slip through unmeasured."""
    run = (
        Path(__file__).resolve().parents[2]
        / "runs" / "2026-08-28" / "2026-08-28_event_list.json"
    )
    if not run.exists():  # pragma: no cover - the run may be pruned from a checkout
        pytest.skip("2026-08-28 run artefacts not present")
    events = json.loads(run.read_text())["events"]
    names = {e["competition"] for e in events if e.get("sport") == "football"}
    # Named both ways round, because "the run grew a competition" and "the table
    # names one the run no longer has" need different fixes, and a bare set
    # comparison reports them as one indistinguishable diff.
    assert not (names - set(SLATE_2026_08_28)), (
        "competitions in the run with no ground truth: "
        f"{sorted(names - set(SLATE_2026_08_28))}"
    )
    assert not (set(SLATE_2026_08_28) - names), (
        "ground truth names competitions the run no longer has: "
        f"{sorted(set(SLATE_2026_08_28) - names)}"
    )


@pytest.mark.parametrize("competition, expected", sorted(SLATE_2026_08_28.items()))
def test_every_competition_on_the_real_slate_resolves_correctly(competition, expected):
    assert resolve(competition) == expected


# --- the eight measured wrong pins ---------------------------------------


@pytest.mark.parametrize(
    "competition, was, now",
    [
        # Each of these resolved confidently to the wrong code because the old
        # lookup fell back to "longest substring key wins", and ~15 keys were
        # bare category names that any qualified competition contains.
        ("Turkey Super League", "sui.1", "tur.1"),
        ("Super League - China", "sui.1", "chn.1"),
        ("Premier League - Russia", "eng.1", "rus.1"),
        ("Bundesliga 2 - Germany", "ger.1", "ger.2"),
        ("Austrian Football Bundesliga", "ger.1", "aut.1"),
        ("Brasileirão Serie B", "bra.1", "bra.2"),
    ],
)
def test_a_category_key_no_longer_captures_a_qualified_competition(
    competition, was, now
):
    got = resolve(competition)
    assert got == now
    assert got != was


@pytest.mark.parametrize("competition", ["Frauen-Bundesliga", "Liga Portugal 2"])
def test_a_qualifier_with_no_espn_surface_resolves_to_silence(competition):
    """These two were reported as missing codes (ger.w.1, por.2). Both 404 at
    ESPN, so the fix is silence, not a new pin -- and silence is what the old
    table could not produce: it answered ger.1 and por.1, the men's and
    first-division leagues, whose clubs share the same names. Those pins do not
    raise anything downstream; they return a real team and a real season and
    then feed cross_provider_agreement."""
    assert resolve(competition) is None


def test_the_romanian_superliga_is_not_answered_as_danish():
    """Two 2026-08-28 fixtures arrived as a bare "Superliga" and resolved to
    den.1, but the clubs were Universitatea Cluj, Petrolul Ploiesti, Voluntari
    and Otelul Galati. Both countries use the name, so the bare form must not
    resolve; the qualified forms must."""
    assert resolve("Superliga") is None
    assert resolve("Denmark Superliga") == "den.1"
    assert resolve("Romania Superliga") == "rou.1"


def test_englands_fifth_tier_is_resolved_rather_than_dropped():
    """"National League" was 11 of the 80 fixtures that day -- the largest
    single block in the slate -- and resolved to nothing. Identified from the
    fixtures themselves (Wealdstone, Carlisle United, Tamworth, Woking); eng.5
    serves a 24-team directory."""
    assert resolve("National League") == "eng.5"
    assert resolve("Vanarama National League") == "eng.5"


# --- silence where the name does not carry the answer --------------------


@pytest.mark.parametrize(
    "competition",
    [
        # Real leagues ESPN does not cover. Every one used to get a confident
        # pin from whichever category key was the longest substring.
        "Nepal Premier League",
        "Malta Premier League",
        "Bhutan Super League",
        "Kosovo Superliga",
        "Armenian Premier League",
        "Faroe Islands Premier League",
        "Gibraltar National League",
        "Andorran Primera Divisio",
        "Mongolian Premier League",
        "Rwanda Premier League",
        "Laos Premier League",
        "Myanmar National League",
    ],
)
def test_an_uncovered_league_gets_no_pin_from_its_category_word(competition):
    assert resolve(competition) is None


@pytest.mark.parametrize(
    "competition",
    [
        # Category names shared by several countries. The name on its own does
        # not identify a league, so nothing may be returned for it.
        "Super League",  # Switzerland, Greece, China, India, Turkey
        "Superliga",  # Denmark, Romania, Serbia
        "Primera Division",  # Argentina, Chile, Uruguay, Paraguay, Venezuela
        "Liga 1",  # Peru, Romania, Indonesia
        "3. Liga",  # Germany's third tier, which ESPN does not serve
    ],
)
def test_an_ambiguous_category_name_resolves_to_nothing(competition):
    assert resolve(competition) is None


@pytest.mark.parametrize(
    "competition",
    ["Kepler Cup", "Deportivo Epla", "Epsom Town", "Totally Invented Cup", "League A"],
)
def test_a_fragment_of_a_key_is_not_a_match(competition):
    """"epl" sits inside "kepler" and "epsom", and "a league" inside "league a".
    Under substring matching with longest-key-wins these handed unrelated
    fixtures to eng.1 and aus.1."""
    assert resolve(competition) is None


def test_an_unknown_competition_stays_unresolved():
    assert resolve("Totally Invented Cup") is None
    assert resolve("") is None


# --- the names a feed actually uses --------------------------------------


@pytest.mark.parametrize(
    "competition, expected",
    [
        # The odds-api feed names England's top flight "EPL". Without this the
        # best-corroborated league in the sheet resolved to None and every one
        # of its rows came back SINGLE_SOURCE (measured 2026-08-28).
        ("EPL", "eng.1"),
        ("epl", "eng.1"),
        ("Premier League", "eng.1"),
        ("English Premier League", "eng.1"),
        ("Premier League - England", "eng.1"),
    ],
)
def test_englands_top_flight_resolves_under_every_name_a_feed_uses(competition, expected):
    assert resolve(competition) == expected


# --- the digit spellings of England's third and fourth tiers ---------------
#
# Added 2026-09-01. "League 1" was 7 fixtures on that slate and "League 2" was
# 12 -- 19 of 46 unresolved competition names, the largest resolvable block in
# the file -- and every one came back "no ESPN league code for competition
# 'League 1'". Rows only bzzoiro could serve were stuck at SINGLE_SOURCE for it;
# Leicester City - Plymouth Argyle reached the coupon uncorroborated on
# goals_for, a market espn-football serves.


@pytest.mark.parametrize(
    "competition, expected",
    [
        ("League 1", "eng.3"), ("League One", "eng.3"),
        ("League 2", "eng.4"), ("League Two", "eng.4"),
    ],
)
def test_englands_lower_tiers_resolve_under_the_digit_and_the_word(competition, expected):
    assert resolve(competition) == expected


@pytest.mark.parametrize(
    "competition, expected",
    [
        ("France Ligue 1", "fra.1"), ("France Ligue 2", "fra.2"),
        # Bare, the names identify nothing: six of the eight bare "Ligue 1"
        # fixtures on 2026-08-28/29 were Algeria and Tunisia, not France.
        ("Ligue 1", None), ("Ligue 2", None),
    ],
)
def test_the_digit_spellings_do_not_collide_with_france(competition, expected):
    """"League 1" and "Ligue 1" are one character apart and three tiers apart."""
    assert resolve(competition) == expected


def test_the_tier_gate_accepts_the_digit_spelling_of_league_one():
    """The gate reads the digit in a name as a tier claim, and it is right to:
    a name carrying "1" pinned to a tier-3 code is the shape of a paste error.
    England's third tier is the case where the rule and the truth diverge --
    the digit there is the proper noun, not the tier."""
    assert not _espn_pin_contradicted("League 1", "eng.3", "English League One")
    assert not _espn_pin_contradicted("League 2", "eng.4", "English League Two")


@pytest.mark.parametrize(
    "competition, league, espn_name",
    [
        # The exception is a *translation*, not an exemption. Blanking the rank
        # for these two names would have switched the tier check off for them
        # and let exactly this swap through.
        ("League 1", "eng.4", "English League Two"),
        ("League 2", "eng.3", "English League One"),
        ("League 1", "eng.1", "English Premier League"),
        ("League 2", "eng.5", "English National League"),
        # The original gate accepted this one, because "Ligue 1" carries a
        # matching digit. Mapping "League 1" to tier 3 is what rejects it.
        ("League 1", "fra.1", "French Ligue 1"),
    ],
)
def test_the_tier_gate_still_rejects_every_wrong_pin_for_those_names(
    competition, league, espn_name
):
    assert _espn_pin_contradicted(competition, league, espn_name)


def test_a_word_number_is_still_never_read_as_a_tier():
    """The general rule the exception must not soften: English "League One" is
    the third tier, so "one" cannot be allowed to mean 1 anywhere."""
    from bet.simple_stats.providers import _espn_division_ranks, _espn_pin_tokens
    assert _espn_division_ranks(_espn_pin_tokens("League One")) == set()
    assert _espn_division_ranks(_espn_pin_tokens("League 1")) == {1}


@pytest.mark.parametrize(
    "competition, expected",
    [("Euro 2028", "uefa.euro"), ("MLS Cup", "usa.1"), ("UCL", "uefa.champions")],
)
def test_short_and_seasoned_names_still_resolve(competition, expected):
    """A season marker is stripped and an abbreviation is a key in its own
    right, so dropping substring matching does not drop these."""
    assert resolve(competition) == expected


@pytest.mark.parametrize(
    "competition, expected",
    [
        # These are the canonical keys the rest of the pipeline already uses
        # (config/sportdb_competition_map.json), so the ESPN table has to
        # answer them too -- for the ones ESPN actually serves.
        ("premier league", "eng.1"),
        ("championship", "eng.2"),
        ("la liga", "esp.1"),
        # Bare "serie a" and "ligue 1" answer None since 2026-09-02: on the
        # wire the bare spellings were Brazil and Algeria as often as Italy
        # and France, so only the country-qualified forms resolve.
        ("serie a", None),
        ("italy serie a", "ita.1"),
        ("bundesliga", "ger.1"),
        ("ligue 1", None),
        ("france ligue 1", "fra.1"),
        ("eredivisie", "ned.1"),
        ("primeira liga", "por.1"),
        ("super lig", "tur.1"),
        ("allsvenskan", "swe.1"),
        ("eliteserien", "nor.1"),
        ("brazil serie a", "bra.1"),
        ("brazil serie b", "bra.2"),
        ("swiss super league", "sui.1"),
        ("belgian pro league", "bel.1"),
        ("scottish premiership", "sco.1"),
        ("austrian bundesliga", "aut.1"),
        ("j1 league", "jpn.1"),
        ("mls", "usa.1"),
        ("liga mx", "mex.1"),
        ("super league greece", "gre.1"),
        ("fa cup", "eng.fa"),
        ("efl cup", "eng.league_cup"),
        ("saudi pro league", "ksa.1"),
        ("champions league", "uefa.champions"),
        ("europa league", "uefa.europa"),
        ("conference league", "uefa.europa.conf"),
    ],
)
def test_the_pipelines_canonical_competition_keys_resolve(competition, expected):
    assert resolve(competition) == expected


@pytest.mark.parametrize(
    "competition, expected",
    [
        # A sponsor or governing-body prefix is spelled out in the table, never
        # stripped by a rule: "Champions League" is a different competition
        # under UEFA, AFC and CAF, and a body-stripping rule would collapse all
        # three onto whichever one happened to be authored first.
        ("Champions League", "uefa.champions"),
        ("UEFA Champions League", "uefa.champions"),
        ("AFC Champions League", "afc.champions"),
        ("CAF Champions League", "caf.champions"),
        ("UEFA Europa League", "uefa.europa"),
        ("LaLiga EA Sports", "esp.1"),
        ("LaLiga Hypermotion", "esp.2"),
        ("Trendyol Super Lig", "tur.1"),
        ("Vanarama National League", "eng.5"),
        ("Belgium Jupiler Pro League", "bel.1"),
    ],
)
def test_sponsor_and_governing_body_prefixes_are_enumerated(competition, expected):
    assert resolve(competition) == expected


def test_an_unknown_governing_body_is_not_stripped_into_a_known_one():
    """The counterpart to the test above: OFC's Champions League is not UEFA's,
    and no rule may quietly turn it into UEFA's."""
    assert resolve("OFC Champions League") is None


@pytest.mark.parametrize(
    "variants, expected",
    [
        (
            ["Chinese Super League", "China Super League", "Super League - China"],
            "chn.1",
        ),
        (["Bundesliga 2", "2. Bundesliga", "Bundesliga 2 - Germany"], "ger.2"),
        (["La Liga", "LaLiga", "La Liga - Spain", "Spain LaLiga"], "esp.1"),
        (["Serie B - Brazil", "Brazil Série B", "Brasileirão Serie B"], "bra.2"),
        (["Turkey Super League", "Süper Lig", "Turkiye Super Lig"], "tur.1"),
    ],
)
def test_word_order_accents_and_punctuation_do_not_change_the_answer(
    variants, expected
):
    """The lookup key is an order-free token signature, which is why the same
    league written four ways is one table row instead of four substring
    hazards."""
    assert {resolve(v) for v in variants} == {expected}


# --- the table itself ----------------------------------------------------

# --- the live verification ------------------------------------------------
#
# config/espn_competition_map_verification.json is written by
# scripts/simple/verify_espn_competition_map.py, which probes every asserted
# code against ESPN and keeps only the ones that answer /teams with a non-empty
# directory. It is an *allowlist*: a code the table pins and the artifact does
# not carry fails the suite, whether or not anyone thought to add it to a list
# of known-dead codes.
#
# That inversion is the point. DEAD_CODES below is a blocklist of the 22 dead
# codes someone happened to probe by hand, and a blocklist cannot catch the
# twenty-third. It is kept because it is free and it records what was found,
# but it is no longer the net.
VERIFICATION = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "config" / "espn_competition_map_verification.json"
    ).read_text(encoding="utf-8")
)


def test_every_code_the_table_pins_was_proved_live():
    """The table is a set of claims about a provider we do not control. This is
    the only test that can fail because ESPN changed rather than because the
    repo did -- rerun scripts/simple/verify_espn_competition_map.py."""
    asserted = set(COMPETITION_TO_ESPN_LEAGUE.values()) - NON_FOOTBALL_CODES
    unproved = sorted(asserted - set(VERIFICATION["codes"]))
    assert not unproved, (
        f"{unproved} are asserted by the table but carry no live verification; "
        f"run scripts/simple/verify_espn_competition_map.py"
    )


def test_every_proved_code_has_a_non_empty_team_directory():
    """A 200 with zero teams is not a directory -- it is how cze.1, fin.1 and
    usa.w.1 got past the old check and failed downstream as team-name gaps."""
    for code, entry in VERIFICATION["codes"].items():
        assert entry["team_count"] > 0, f"{code} was recorded with no teams"
        assert entry["espn_name"], f"{code} was recorded with no ESPN name"


def test_the_recorded_espn_names_contradict_none_of_their_pins():
    """The verification script runs the production gate against ESPN's own
    league name for every pin, and records the name it used. Replaying that
    here means a change to the gate cannot start rejecting correct pins without
    the suite saying so -- offline, against real recorded provider names."""
    offenders = []
    for code, entry in VERIFICATION["codes"].items():
        for name in entry["pinned_by"]:
            why = _espn_pin_contradicted(name, code, entry["espn_name"])
            if why:
                offenders.append(f"{name!r} -> {code}: {why}")
    assert not offenders, offenders


def test_the_sweep_list_was_proved_live_too():
    """A dead code in ESPN_LEAGUES is a guaranteed 404 on every discovery
    sweep, so the sweep list is probed by the same script and held to the same
    allowlist."""
    from bet.api_clients.espn import ESPN_LEAGUES

    unproved = sorted(set(ESPN_LEAGUES["football"]) - set(VERIFICATION["codes"]))
    assert not unproved, (
        f"{unproved} are swept but carry no live verification; "
        f"run scripts/simple/verify_espn_competition_map.py"
    )


def test_the_verification_records_how_it_was_obtained():
    """An artifact that does not say what it proved is a number to be trusted
    on faith, which is what this whole exercise removes."""
    assert "teams" in VERIFICATION["probe"]
    assert VERIFICATION["verified_by"].endswith("verify_espn_competition_map.py")
    assert VERIFICATION["last_run"]


# Codes the old table asserted which ESPN does not serve: 404, or 200 with an
# empty team list. Verified 2026-08-28. Secondary to the allowlist above.
DEAD_CODES = {
    "sau.1", "usa.w.1", "pol.1", "ukr.1", "egy.1", "kor.1", "cro.1", "hun.1",
    "bul.1", "ser.1", "svk.1", "qat.1", "uae.1", "tun.1", "mor.1", "cze.1",
    "fin.1", "conmebol.copa_america", "ger.w.1", "por.2", "ger.3", "irl.1",
}


def test_no_dead_code_survives_anywhere_in_the_table():
    """The old table asserted 18 codes ESPN does not serve, and five of them
    were asserted as correct by this file's own earlier tests -- so the suite
    was pinning the fiction in place rather than catching it. The allowlist
    above is what catches the next one; this names the ones already found."""
    assert DEAD_CODES.isdisjoint(set(COMPETITION_TO_ESPN_LEAGUE.values()))


@pytest.mark.parametrize(
    "competition, dead, live",
    [
        ("Saudi Pro League", "sau.1", "ksa.1"),
        ("NWSL", "usa.w.1", "usa.nwsl"),
        ("Copa America", "conmebol.copa_america", "conmebol.america"),
    ],
)
def test_a_code_that_moved_now_points_at_the_live_one(competition, dead, live):
    got = resolve(competition)
    assert got == live
    assert got != dead


@pytest.mark.parametrize(
    "competition", ["Ekstraklasa", "Ukrainian Premier League", "K League 1"]
)
def test_a_league_espn_dropped_resolves_to_nothing(competition):
    """pol.1, ukr.1 and kor.1 all 404. The old table asserted all three, and
    the resulting pin failed in resolve_team_id as a team-name problem."""
    assert resolve(competition) is None


def test_the_signature_index_refuses_to_hide_a_collision(monkeypatch):
    """Two names reducing to the same signature but different codes means the
    signature cannot decide between them. Keeping one silently is how a table
    starts guessing, so the build raises instead -- at import, in the first test
    that runs."""
    import bet.api_clients.espn as espn

    monkeypatch.setattr(
        espn,
        "_ESPN_FOOTBALL_COMPETITIONS",
        {"Denmark Superliga": "den.1", "Superliga Denmark": "rou.1"},
    )
    monkeypatch.setattr(espn, "_ESPN_OTHER_COMPETITIONS", {})
    with pytest.raises(ValueError, match="ambiguous ESPN competition signature"):
        _build_espn_signature_index()


def test_the_real_table_builds_without_a_collision():
    assert _build_espn_signature_index()


def test_a_season_marker_is_stripped_but_a_division_number_is_not():
    assert _espn_name_signature("Bundesliga 2025/26") == _espn_name_signature(
        "Bundesliga"
    )
    assert _espn_name_signature("Bundesliga 2") != _espn_name_signature("Bundesliga")


# --- sport separation ----------------------------------------------------


@pytest.mark.parametrize(
    "competition, expected",
    [
        ("WTA Monterrey Open", "wta"),
        ("WTA 1000 Beijing", "wta"),
        ("ATP Cincinnati", "atp"),
        ("ATP Masters 1000 Rome", "atp"),
        ("ATP Finals", "atp"),
    ],
)
def test_an_explicit_tour_marker_names_the_tennis_tour(competition, expected):
    """The 2026-08-25 run's only tennis competition was "WTA Monterrey Open",
    which resolved to nothing and left _provider_client on the default
    espn-tennis client -- pinned to "atp". ESPN's tennis /scoreboard turns out
    not to be tour-scoped in content (verified 2026-08-28: the atp and wta
    scoreboards return identical competitions), so no history was lost, but the
    tour is what lets _resolve_athlete_id match on its strict, league-checked
    pass instead of the league-blind fallback that can answer with a different
    player of the same surname."""
    assert resolve(competition) == expected


def test_a_tour_ambiguous_tennis_name_resolves_to_nothing():
    """The table used to map every grand slam and masters event to "atp"
    unconditionally, which was an assertion about the men's draw applied to
    both. Those entries are gone."""
    assert resolve("Wimbledon") is None
    assert resolve("US Open") is None
    assert resolve("ATP/WTA Mixed Doubles") is None


def test_no_tennis_code_is_reachable_as_a_football_league():
    """_provider_client checks the resolved code against this set, so a single
    mistyped table row cannot pin ESPNClient(sport="football") to "atp"."""
    assert "atp" not in ESPN_FOOTBALL_LEAGUE_CODES
    assert "wta" not in ESPN_FOOTBALL_LEAGUE_CODES
    assert "eng.1" in ESPN_FOOTBALL_LEAGUE_CODES
    assert "ksa.1" in ESPN_FOOTBALL_LEAGUE_CODES


# --- the provider-side gate ----------------------------------------------


def test_a_two_hundred_with_no_teams_is_not_a_directory():
    """ESPN answers 200 with an empty team list for retired and
    never-populated codes -- verified 2026-08-28 for cze.1 ("Gambrinus Liga"),
    fin.1, usa.w.1 and irl.1. The gate used to treat any 200 as success, so all
    four passed it and then failed in resolve_team_id as a team-name problem."""
    empty = _ESPNDirectory(served=True, league_name="Gambrinus Liga", team_count=0)
    real = _ESPNDirectory(served=True, league_name="Spanish LALIGA", team_count=20)
    assert not empty.usable
    assert not _ESPNDirectory(served=False).usable
    assert real.usable


@pytest.mark.parametrize(
    "competition, league, espn_name",
    [
        # A wrong country: the kind that does die downstream, but as a
        # team-name data_gap that never names the league.
        ("Turkey Super League", "sui.1", "Swiss Super League"),
        ("Premier League - Russia", "eng.1", "English Premier League"),
        # A wrong gender or division inside the right country: the kind that
        # does not die at all, because the clubs share their names.
        ("Frauen-Bundesliga", "ger.1", "German Bundesliga"),
        ("Bundesliga 2 - Germany", "ger.1", "German Bundesliga"),
        ("Liga Portugal 2", "por.1", "Portuguese Primeira Liga"),
    ],
)
def test_the_gate_rejects_a_pin_espns_own_league_name_contradicts(
    competition, league, espn_name
):
    """Defence in depth behind the table, aimed at the failure the table cannot
    catch: a code pasted onto the wrong row. Each pair here is a pin the old
    lookup actually produced."""
    assert _espn_pin_contradicted(competition, league, espn_name)


@pytest.mark.parametrize(
    "competition, league, espn_name",
    [
        ("Turkey Super League", "tur.1", "Turkish Super Lig"),
        ("Super League - China", "chn.1", "Chinese Super League"),
        ("Premier League - Russia", "rus.1", "Russian Premier League"),
        ("Bundesliga 2 - Germany", "ger.2", "German 2. Bundesliga"),
        ("Austrian Football Bundesliga", "aut.1", "Austrian Bundesliga"),
        ("Brasileirão Serie B", "bra.2", "Brazilian Serie B"),
        ("Saudi Pro League", "ksa.1", "Saudi Pro League"),
        ("National League", "eng.5", "English National League"),
        ("WSL", "eng.w.1", "English Women's Super League"),
        # Names that share no comparable word with ESPN's. The gate must not be
        # the reason a correct pin is dropped, so an unrecognised word proves
        # nothing.
        ("EPL", "eng.1", "English Premier League"),
        ("Ekstraklasa", "pol.1", "Polish Ekstraklasa"),
        (
            "Liga Profesional de Fútbol",
            "arg.1",
            "Argentine Liga Profesional de Fútbol",
        ),
        ("Categoría Primera A", "col.1", "Colombian Primera A"),
        ("Liga Portugal Betclic", "por.1", "Portuguese Primeira Liga"),
        ("MLS", "usa.1", "MLS"),
        ("Champions League", "uefa.champions", "UEFA Champions League"),
    ],
)
def test_the_gate_passes_every_correct_pin(competition, league, espn_name):
    assert _espn_pin_contradicted(competition, league, espn_name) == ""


def test_the_gate_reads_the_country_off_the_code_when_the_name_is_bare():
    """ESPN calls ksa.1 the "Saudi Pro League" but calls rsa.1 the "South
    African Premiership": only the code prefix says which country a bare name
    belongs to."""
    assert _espn_pin_contradicted(
        "Saudi Pro League", "rsa.1", "South African Premiership"
    )
    assert _espn_pin_contradicted(
        "Nigeria Premier League", "rsa.1", "South African Premiership"
    )


@pytest.mark.parametrize(
    "competition, league, espn_name",
    [
        # Every one of these was MISSED before the tier check learned letters,
        # while the digit spelling of the same mistake was CAUGHT. Measured
        # against the 2026-08-28 table.
        ("Brasileirão Serie B", "bra.1", "Brazilian Serie A"),
        ("Serie B - Italy", "ita.1", "Italian Serie A"),
        ("Primera B Nacional", "arg.1", "Argentine Liga Profesional"),
        ("Serie C - Italy", "ita.1", "Italian Serie A"),
        # The ordinal-word spelling of the same claim.
        ("Segunda Division", "esp.1", "Spanish LALIGA"),
        # The digit case, which already worked and must keep working.
        ("Bundesliga 2 - Germany", "ger.1", "German Bundesliga"),
    ],
)
def test_a_letter_division_is_caught_like_a_digit_one(competition, league, espn_name):
    """The silent class: right country, real clubs, nothing raises, and the
    phantom second provider goes on to feed cross_provider_agreement. The check
    compared digits only, so which of two identical mistakes it caught came
    down to whether the league spells its tier "2" or "B"."""
    assert _espn_pin_contradicted(competition, league, espn_name)


@pytest.mark.parametrize(
    "competition, league, espn_name",
    [
        # A bare letter is not a tier. aus.1 is the top flight.
        ("A-League Men", "aus.1", "Australian A-League Men"),
        # UEFA's Nations League "leagues" are seeding pots, not divisions.
        ("UEFA Nations League - League B", "uefa.nations", "UEFA Nations League"),
        ("Liga F", "esp.w.1", "Spanish Liga F"),
        # Word numbers are never read: English "League One" is the *third*
        # tier, so reading "one" as 1 would reject a correct pin.
        ("League One", "eng.3", "English League One"),
        ("England League Two", "eng.4", "English League Two"),
        ("AFC Champions League Two", "afc.cup", "AFC Champions League Two"),
        # A letter that does name a tier, on a code that agrees.
        ("Brasileirão Serie B", "bra.2", "Brazilian Serie B"),
        ("Categoría Primera A", "col.1", "Colombian Primera A"),
        ("Belgium First Division A", "bel.1", "Belgian Pro League"),
        ("Argentina Nacional B", "arg.2", "Argentine Nacional B"),
    ],
)
def test_the_tier_check_stays_silent_where_it_has_no_evidence(
    competition, league, espn_name
):
    """This gate must never be the reason a correct pin is dropped, so the
    letters only count after a word that names a league family and the word
    numbers never count at all."""
    assert _espn_pin_contradicted(competition, league, espn_name) == ""


@pytest.mark.parametrize(
    "competition, league, espn_name",
    [
        ("Osterreich Bundesliga", "ger.1", "German Bundesliga"),
        ("Ecuadorian Serie A", "per.1", "Peruvian Liga 1"),
        ("Serie A Italiana", "esp.1", "Spanish LALIGA"),
        ("Danmark Superliga", "rou.1", "Romanian Liga 1"),
        ("Brasil Serie A", "arg.1", "Argentine Liga Profesional"),
    ],
)
def test_the_gate_reads_every_country_spelling_the_resolver_folds(
    competition, league, espn_name
):
    """These five were among 24 spellings the resolver understood and the gate
    did not. Not a wrong answer -- silence, which reads as a pass, so the
    safety net was thinnest exactly where the resolver was most permissive."""
    assert _espn_pin_contradicted(competition, league, espn_name)


def test_the_resolver_and_the_gate_share_one_country_vocabulary():
    """Derived, not duplicated: teaching the resolver a new spelling teaches
    the gate the same one in the same commit. Two hand-kept lists is how they
    drifted by 24 words in the first place."""
    for spelling, folded in _ESPN_TOKEN_SYNONYMS.items():
        prefix = ESPN_COUNTRY_CODE_PREFIXES.get(folded)
        if prefix is None:  # a fold that is not a country ("women", "2")
            continue
        assert _ESPN_PIN_COUNTRY_WORDS.get(spelling) == prefix, spelling


def test_the_gate_knows_every_country_the_table_pins():
    """A code whose country the gate cannot name is a code whose country it
    cannot contradict."""
    pinned = {code.split(".")[0] for code in _ESPN_FOOTBALL_COMPETITIONS.values()}
    countries = pinned - _ESPN_NON_COUNTRY_PREFIXES
    assert countries <= set(ESPN_COUNTRY_CODE_PREFIXES.values())


def test_the_gate_says_nothing_when_espn_gave_no_name():
    """No evidence is not evidence of a contradiction."""
    assert _espn_pin_contradicted("Turkey Super League", "sui.1", "") == ""


# --- the drift signal ----------------------------------------------------


def _event(competition, sport="football"):
    return SimpleNamespace(sport=sport, competition=competition)


def test_coverage_counts_fixtures_as_well_as_names():
    """One unresolved *name* was eleven unresolved *fixtures* on 2026-08-28 --
    "National League", the largest block in the slate -- so a name-weighted
    number alone would have understated it eleven-fold."""
    events = [_event("Nepal Premier League")] * 11 + [_event("EPL")] * 3
    coverage = espn_competition_coverage(events)
    assert coverage["football_fixtures"] == 14
    assert coverage["fixtures_resolved"] == 3
    assert coverage["names_unresolved"] == 1
    assert coverage["fixtures_unresolved_pct"] == 78.6
    assert coverage["unresolved_by_fixtures"] == {"Nepal Premier League": 11}


def test_coverage_names_what_it_could_not_resolve():
    """Counted-only drift is a number nobody can act on. Each name here is one
    authored table row away from being a second provider."""
    coverage = espn_competition_coverage(
        [_event("Parva Liga"), _event("Ekstraklasa"), _event("EPL")]
    )
    assert set(coverage["unresolved_by_fixtures"]) == {"Parva Liga", "Ekstraklasa"}


def test_coverage_ignores_tennis_and_survives_an_empty_slate():
    """Tennis resolves through a tour marker, not a league table, so counting
    it here would report a table failure that is not one."""
    assert espn_competition_coverage([_event("WTA Monterrey Open", "tennis")]) == (
        espn_competition_coverage([])
    )
    assert espn_competition_coverage([])["fixtures_unresolved_pct"] == 0.0


def test_coverage_on_the_real_slate_matches_the_ground_truth():
    """The drift signal and the hand-checked slate must agree about which
    competitions ESPN cannot serve, or one of them is wrong."""
    run = (
        Path(__file__).resolve().parents[2]
        / "runs" / "2026-08-28" / "2026-08-28_event_list.json"
    )
    if not run.exists():  # pragma: no cover - the run may be pruned
        pytest.skip("2026-08-28 run artefacts not present")
    events = [
        SimpleNamespace(**{k: e.get(k) for k in ("sport", "competition")})
        for e in json.loads(run.read_text())["events"]
    ]
    coverage = espn_competition_coverage(events)
    expected = {name for name, code in SLATE_2026_08_28.items() if code is None}
    assert set(coverage["unresolved_by_fixtures"]) == expected
    # 347, not the 80 this once asserted: the 2026-08-28 run was re-run with a
    # larger --max-events after the first pass was found to have been capped,
    # and it overwrote the artifact this test reads. That is worth knowing about
    # the number rather than pinning: what the test is for is the *agreement*
    # between the coverage signal and the hand-checked table above, and a count
    # that moves whenever a day is re-run only ever fails for that reason.
    assert coverage["football_fixtures"] == 347


# --- participant name folding -------------------------------------------


@pytest.mark.parametrize(
    "feed_name, espn_name",
    [
        # Every one of these resolved to None on the 2026-08-28 slate once the
        # leagues were pinned correctly, and surfaced as "could not resolve
        # team identity" -- a league-shaped failure wearing a team-name label.
        ("Al-Hilal", "Al Hilal"),
        ("Al-Nassr", "Al Nassr"),
        ("Al-Khaleej", "Al Khaleej"),
        ("Paris Saint Germain", "Paris Saint-Germain"),
        ("VfL Osnabrück", "VfL Osnabruck"),
        ("Gençlerbirliği", "Genclerbirligi"),
        ("Anna Bondár", "Anna Bondar"),
        ("Deportivo Alavés", "Deportivo Alaves"),
    ],
)
def test_accents_and_separators_do_not_break_a_name_match(feed_name, espn_name):
    assert _fold_espn_participant_name(feed_name) == _fold_espn_participant_name(
        espn_name
    )


def test_folding_does_not_merge_genuinely_different_names():
    fold = _fold_espn_participant_name
    assert fold("Al Hilal") != fold("Al Ahli")
    assert fold("Alexander Zverev") != fold("Vlada Zvereva")
    assert fold("Manchester United") != fold("Manchester City")


# --- the discovery sweep list --------------------------------------------


def test_the_discovery_sweep_list_carries_no_known_dead_code():
    """ESPN_LEAGUES drives the per-league discovery sweep, so a dead code here
    is a guaranteed 404 on every sweep. 21 of the 104 football entries were
    dead, and the three that answered 200 with an empty team list (cze.1,
    fin.1, usa.w.1) did not even fail loudly.
    test_the_sweep_list_was_proved_live_too is the live version of this."""
    from bet.api_clients.espn import ESPN_LEAGUES

    football = ESPN_LEAGUES["football"]
    assert DEAD_CODES.isdisjoint(set(football))
    assert {"geo.1", "kaz.1", "uzb.1"}.isdisjoint(set(football))
    assert len(football) == len(set(football)), "a duplicated code sweeps twice"


def test_the_sweep_list_can_see_the_leagues_the_table_pins():
    """A competition the table resolves but the sweep cannot enumerate is a
    league the pipeline can enrich but never discover. eng.5 was exactly that:
    11 of the 80 fixtures on 2026-08-28."""
    from bet.api_clients.espn import ESPN_LEAGUES

    football = set(ESPN_LEAGUES["football"])
    for code in ("ksa.1", "usa.nwsl", "eng.5", "rus.1", "bra.2", "ger.2"):
        assert code in football, f"{code} is pinned by the table but never swept"


# --- a possessive is not a token -------------------------------------------


def test_a_possessive_apostrophe_does_not_split_a_league_into_two_keys():
    """Found 2026-09-02. ``re.sub`` on punctuation turned "Women's" into
    "women s", so the pinned "UEFA Women's Champions League" carried a stray
    "s" token the feed's own "UEFA Champions League Women" did not -- two keys
    for one competition, and nine fixtures losing ESPN over one letter."""
    assert _espn_name_signature("UEFA Women's Champions League") == _espn_name_signature(
        "UEFA Champions League Women"
    )
    assert resolve("UEFA Champions League Women") == "uefa.wchampions"
    assert "s" not in _espn_name_signature("Women's Super League")


def test_the_possessive_fold_does_not_erase_a_real_trailing_s():
    """"Chess" must not become "Che". Only ``'s`` goes."""
    assert "champions" in _espn_name_signature("UEFA Champions League")
    assert resolve("England Women's Super League") == "eng.w.1"
    assert resolve("Women's Super League") == "eng.w.1"


def test_the_codes_probed_on_2026_09_02_are_pinned():
    """Three of 48 unmapped names had a live ESPN directory. The rest -- Puchar
    Polski, Cupa Romaniei, Svenska Cupen, a Japanese league cup code -- were
    probed the same day and 404, so they stay None on purpose."""
    assert resolve("USL League One") == "usa.usl.l1"
    assert resolve("Copa Colombia") == "col.copa"
    assert resolve("EFL Trophy") == "eng.trophy"
    # Right country, wrong tier: pinning League One to the Championship's code
    # is the failure the division-marker gate exists for.
    assert resolve("USL Championship") == "usa.usl.1"

