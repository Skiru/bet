"""What the 2026-08-28 run got wrong, and what stops each of it happening again.

The run finished, wrote a coupons file, and reported PARTIAL. Nothing raised.
Every defect below produced a plausible number on a sheet a human was going to
bet from, which is the only failure mode this pipeline really has:

  1. espn-tennis served one player's matches under another player's name --
     Qinwen Zheng's row carried Lorenzo Musetti's and Kei Nishikori's.
  2. Nineteen fixtures reached the sheet twice, and one reached the coupon
     twice at the same market, line and direction.
  3. tennis-abstract dates a match by the Monday its tournament started, which
     both double-counted matches across providers and deleted losses within one.
  4. --max-events ranked every event together, so the single-source sport
     sorted last and disappeared entirely.
  5. Retirements counted as completed matches, flattering every UNDER.

No network. Every expected value is measured from the run artifacts in
runs/2026-08-28/, and the measurement is named in each test.
"""
from datetime import datetime, timezone

import pytest

from bet.api_clients.espn import (
    _espn_athlete_name_matches,
    get_espn_league_for_competition,
)
from bet.discovery.dedup import DeduplicationEngine
from bet.discovery.models import DiscoveredEvent
from bet.discovery.team_aliases import TEAM_ALIASES, resolve_team_alias
from bet.simple_stats.contracts import (
    EventDossierV1,
    EventRecord,
    MetricObservation,
    ProviderValue,
)
from bet.simple_stats.enrich import _apportion_cap
from bet.simple_stats.providers import _is_absent_not_zero, _misidentified_reason
from bet.utils import normalize_team_name


# --- 1. espn-tennis served another player's matches ----------------------
#
# Mechanism, measured from betting/data/stats_cache on 2026-08-28: of 441 ESPN
# tennis resolutions cached under the atp directory, 372 came from the
# scoreboard fallback (whose last rule was "the query's surname appears in the
# display name"), 23 resolved to a player ESPN files under the other tour, and
# only 44 used the tour-checked pass. Fifty ESPN athlete ids each answered to
# more than one queried name.


@pytest.mark.parametrize(
    "competition, expected",
    [
        # The table used to assert "atp" for every grand slam. Removing that
        # stopped asserting the wrong tour but left the right one unstated, so
        # these resolved to None and fell to the default -- which is ATP.
        ("US Open, Women (grand_slam)", "wta"),
        ("US Open, Men (grand_slam)", "atp"),
        ("Wimbledon, Women (grand_slam)", "wta"),
        # An explicit tour marker still outranks everything.
        ("Monterrey (wta_500)", "wta"),
        ("Winston Salem (atp_250)", "atp"),
        # No tour and no gender: None, which drops the provider. A challenger
        # draw is not reliably men's, and guessing is what this whole section
        # is about.
        ("Kingston 2, Jamaica (challenger)", None),
        # The gender marker must not reach football. These are answered by the
        # authored table, which is consulted first.
        ("Women's Super League", "eng.w.1"),
        ("England Women's Super League", "eng.w.1"),
        ("Liga F", "esp.w.1"),
        ("Premier League", "eng.1"),
    ],
)
def test_a_gendered_draw_pins_its_tour_and_a_womens_league_stays_football(
    competition, expected
):
    assert get_espn_league_for_competition(competition) == expected


@pytest.mark.parametrize(
    "requested, claimed, expected",
    [
        # ESPN writes Chinese and Japanese names surname-first. Token equality
        # is order-free, so this is the same player -- and it is the query that
        # resolved to a *man* on 2026-08-28.
        ("Qinwen Zheng", "Zheng Qinwen", True),
        ("Anna Bondár", "Anna Bondar", True),
        ("C. Alcaraz", "Carlos Alcaraz", True),
        ("Storm Hunter", "Storm Hunter", True),
        # Every one of these pairs shared a cached ESPN id on 2026-08-28,
        # because the old matcher accepted a shared forename or a surname
        # substring. "henri" is a substring of "henrique".
        ("squire, henri", "Henrique Rocha", False),
        ("eala, alexandra", "Alexandra Wolf", False),
        ("joanna garland", "Anna Kalinskaya", False),
        ("geun jun kim", "Kimberly Birrell", False),
        ("mickoska, sara", "Sara Sorribes Tormo", False),
        ("Alexander Zverev", "Mischa Zverev", False),
        # The placeholder resolved to athlete id -4.
        ("TBD", "Novak Djokovic", False),
    ],
)
def test_espn_athlete_names_are_compared_not_scored(requested, claimed, expected):
    assert _espn_athlete_name_matches(requested, claimed) is expected


def _tennis_row(home, away, home_id="1", away_id="2"):
    """One ESPN-shaped fixture row: two named sides carrying participant ids."""
    return {
        "id": "f1",
        "home_team": home,
        "away_team": away,
        "home_team_id": home_id,
        "away_team_id": away_id,
    }


def test_a_tennis_payload_naming_someone_else_is_refused_whole():
    """The proof that used to live only in verify_tennis_providers.py.

    That script probes a fixed list of canary names before a run, so a crossing
    on one of the day's *actual* players passed the morning check untouched. It
    exited 0 on 2026-08-28.
    """
    rows = [
        _tennis_row("Lorenzo Musetti", "Ugo Humbert"),
        _tennis_row("Lorenzo Musetti", "Kei Nishikori"),
    ]
    reason = _misidentified_reason("espn-tennis", "Qinwen Zheng", "1", rows)
    assert reason is not None
    assert "Lorenzo Musetti" in reason
    assert "Qinwen Zheng" in reason


def test_a_tennis_payload_that_is_his_own_is_accepted():
    rows = [
        _tennis_row("Zheng Qinwen", "Clara Tauson"),
        _tennis_row("Donna Vekic", "Zheng Qinwen", home_id="2", away_id="1"),
    ]
    assert _misidentified_reason("espn-tennis", "Qinwen Zheng", "1", rows) is None


def test_a_row_that_cannot_say_which_side_he_played_is_a_failure_not_an_abstention():
    rows = [_tennis_row("Someone", "Anyone", home_id="7", away_id="8")]
    reason = _misidentified_reason("espn-tennis", "Qinwen Zheng", "1", rows)
    assert reason is not None
    assert "which side" in reason


def test_football_payloads_are_not_subject_to_the_player_identity_test():
    """A club's fixture names two clubs; which side is proved by team id."""
    rows = [_tennis_row("Bayern Munich", "VfB Stuttgart")]
    assert _misidentified_reason("espn-football", "Bayern Munich", "1", rows) is None


# --- 2. one fixture, two events ------------------------------------------
#
# Measured on runs/2026-08-28/2026-08-28_event_list.json: 19 groups of
# same-kickoff same-sport duplicates, 23 surplus fixtures. Re-running discovery
# over that slate with these fixes merges 25 (the extra two are pairs the
# original count's fuzzy detector could not see).


def _discovered(source, external_id, home, away, kickoff, sport="football"):
    return DiscoveredEvent(
        source=source,
        external_id=external_id,
        sport=sport,
        competition="",
        country="",
        home_team=home,
        away_team=away,
        kickoff=kickoff,
        status="scheduled",
        raw_data={},
    )


_KICKOFF = datetime(2026, 8, 28, 18, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "home_a, away_a, home_b, away_b",
    [
        # A qualifier one feed carries and the other does not. token_sort_ratio
        # scores these on length -- "Genk"/"KRC Genk" is 67 -- so all of them
        # fell below any threshold loose enough to be safe.
        ("Genk", "SK Beveren", "KRC Genk", "SK Beveren"),
        ("Alavés", "Villarreal", "Deportivo Alavés", "Villarreal"),
        ("Montpellier", "Boulogne", "Montpellier HSC", "Boulogne"),
        ("Montpellier", "Boulogne", "Montpellier", "US Boulogne Côte-d'Opale"),
        ("Clermont", "Sochaux", "Clermont Foot", "Sochaux"),
        ("Rodez AF", "Pau FC", "Rodez", "Pau FC"),
        ("Nancy", "USL Dunkerque", "Nancy", "Dunkerque"),
        ("Galway United", "Shelbourne Dublin", "Galway United", "Shelbourne"),
        ("Al-Khaleej", "Al-Hilal", "Al Khaleej Saihat", "Al-Hilal Saudi"),
        ("FC Akron Tolyatti", "CSKA Moscow", "Akron", "CSKA Moscow"),
        ("FC CSKA 1948 Sofia", "Lokomotiv Plovdiv", "CSKA 1948", "Lokomotiv Plovdiv"),
        ("FC Voluntari", "SC Oțelul Galați", "FC Voluntari", "Oţelul"),
        # An apostrophe, which normalization used to keep.
        ("St Patricks Athletic", "Waterford FC", "St Patrick's Athl.", "Waterford"),
        # Genuinely different names for one club: the alias table's job.
        ("Stade Lavallois", "Grenoble", "Laval", "Grenoble"),
        ("Rio Ave FC", "Sporting Lisbon", "Rio Ave", "Sporting CP"),
        ("Nautico PE", "Athletic Club", "Nautico Recife", "Athletic Club"),
        ("Shenzhen Peng City FC", "Shanghai SIPG FC", "Shenzhen Peng City", "Shanghai Port"),
        ("Genclerbirligi SK", "Erzurum BB", "Gençlerbirliği", "Erzurumspor FK"),
    ],
)
def test_two_spellings_of_one_fixture_merge(home_a, away_a, home_b, away_b):
    merged = DeduplicationEngine().merge(
        {
            "odds-api": [_discovered("odds-api", "a", home_a, away_a, _KICKOFF)],
            "highlightly": [_discovered("highlightly", "b", home_b, away_b, _KICKOFF)],
        }
    )
    assert len(merged) == 1, [(f.home_team, f.away_team) for f in merged]
    assert {s.source for s in merged[0].sources} == {"odds-api", "highlightly"}


@pytest.mark.parametrize(
    "home_a, away_a, home_b, away_b",
    [
        # Containment must not join two different clubs that share a token.
        ("Real Madrid", "Getafe", "Real Sociedad", "Getafe"),
        ("Sporting Braga", "Benfica", "Sporting CP", "Benfica"),
        ("Bayern Munich", "Mainz", "Werder Bremen", "Mainz"),
        # Bilbao's official name is "Athletic Club". Normalization used to
        # reduce both it and the Brazilian side to the single token "club".
        ("Athletic Club", "Getafe", "Athletic Club (MG)", "Sport Recife"),
    ],
)
def test_different_fixtures_do_not_merge(home_a, away_a, home_b, away_b):
    merged = DeduplicationEngine().merge(
        {
            "odds-api": [_discovered("odds-api", "a", home_a, away_a, _KICKOFF)],
            "highlightly": [_discovered("highlightly", "b", home_b, away_b, _KICKOFF)],
        }
    )
    assert len(merged) == 2


def test_containment_needs_an_exact_kickoff_not_the_two_hour_window():
    """Containment alone would merge a first team with a reserve side. The
    exact-kickoff requirement is what makes it safe, and every one of the 23
    surplus fixtures shared an exact kickoff."""
    later = datetime(2026, 8, 28, 19, 30, tzinfo=timezone.utc)
    merged = DeduplicationEngine().merge(
        {
            "odds-api": [_discovered("odds-api", "a", "Genk", "Anderlecht", _KICKOFF)],
            "highlightly": [_discovered("highlightly", "b", "KRC Genk", "Anderlecht", later)],
        }
    )
    assert len(merged) == 2


def test_two_clubs_of_one_city_need_both_sides_to_match_before_they_could_merge():
    """A bound worth stating, because normalization does not enforce it.

    "United" and "City" are stripped as club forms, so Manchester United and
    Manchester City both normalize to "manchester" -- they are already equal
    under the exact key, before containment is consulted. What keeps them apart
    is that a merge needs *both* sides to match at one kickoff, and two clubs
    cannot host the same opponent at the same minute. Removing those words from
    the strip list would cost "Man Utd"/"Manchester United", which is a real
    pairing, to guard one that cannot occur.
    """
    same_away = DeduplicationEngine().merge(
        {
            "odds-api": [_discovered("odds-api", "a", "Manchester United", "Arsenal", _KICKOFF)],
            "highlightly": [_discovered("highlightly", "b", "Manchester City", "Arsenal", _KICKOFF)],
        }
    )
    assert len(same_away) == 1  # the impossible fixture, documented not fixed

    real_matchday = DeduplicationEngine().merge(
        {
            "odds-api": [_discovered("odds-api", "a", "Manchester United", "Arsenal", _KICKOFF)],
            "highlightly": [_discovered("highlightly", "b", "Manchester City", "Everton", _KICKOFF)],
        }
    )
    assert len(real_matchday) == 2


def test_normalization_never_reduces_a_club_to_a_kind_of_club():
    """"Athletic Club" and "Athletic Club (MG)" both used to become "club",
    which made Bilbao and a Serie B side one team to every caller -- including
    team-identity resolution, where a false positive files another club's
    history."""
    assert normalize_team_name("Athletic Club") != "club"
    assert normalize_team_name("Athletic Bilbao") == "bilbao"
    assert normalize_team_name("Sporting CP") != ""


def test_the_alias_table_holds_renames_not_qualifiers():
    """Qualifier pairs belong to containment in dedup.py. A table that also
    held them would grow with every feed instead of only with every rename."""
    for canonical, aliases in TEAM_ALIASES.items():
        for alias in aliases:
            assert resolve_team_alias(alias) == resolve_team_alias(canonical)
    # The qualifier case must NOT be resolved by the table.
    assert resolve_team_alias("KRC Genk") != resolve_team_alias("Genk")


# --- 3. a tournament date is not a match date -----------------------------
#
# Measured on runs/2026-08-28/2026-08-28_event_dossiers.json: 1945 of 2550
# tennis-abstract observations fell on a Monday, against espn-tennis's 510
# spread evenly across the week. Re-analysing that artifact with the opponent
# key takes the tennis sample from 7416 to 11632 and leaves football's 36536
# untouched.


def _pv(value, provider, opponent, date, match_id):
    return ProviderValue(
        provider=provider,
        match_id=match_id,
        match_date=date,
        opponent=opponent,
        value=value,
        observed_at="2026-08-28T00:00:00+00:00",
    )


def _tennis_dossier(bucket):
    return EventDossierV1(
        event_id="evt",
        sport="tennis",
        team_a_name="Darja Semenistaja",
        team_b_name="Storm Hunter",
        metrics={
            "aces_for": MetricObservation(
                canonical_name="aces_for", team_a_l10=bucket, team_b_l10=[]
            )
        },
        readiness="PARTIAL",
    )


def test_two_matches_of_one_tournament_week_are_two_matches():
    """The failure that reported 10/10. Storm Hunter's 9-ace match -- a loss at
    aces UNDER 8.5 -- shared a Monday with a 5-ace match, and _representative
    kept the median, which was the win."""
    from bet.simple_stats.analyze import _one_per_day

    monday = "2026-08-17"
    bucket = [
        _pv(9.0, "tennis-abstract", "Camila Osorio", monday, "ta1"),
        _pv(5.0, "tennis-abstract", "Antonia Ruzic", monday, "ta2"),
    ]
    assert len(_one_per_day(bucket, "tennis")) == 2
    # Football keeps the day key: a club plays at most one match a day, and
    # opponent clustering there mis-split 72 pairs on spelling alone.
    assert len(_one_per_day(bucket, "football")) == 1


def test_one_match_reported_by_two_providers_is_one_match():
    """tennis-abstract stamps the tournament Monday, espn-tennis the real day,
    so the day key saw two days and counted one match twice. 44 such matches
    across 15 events."""
    from bet.simple_stats.analyze import _one_per_day

    bucket = [
        _pv(9.0, "tennis-abstract", "Clara Tauson", "2026-08-23", "ta1"),
        _pv(9.0, "espn-tennis", "Clara Tauson", "2026-08-28", "espn1"),
    ]
    assert len(_one_per_day(bucket, "tennis")) == 1


def test_a_repeat_pairing_survives_the_opponent_key():
    """A constant opponent must not wipe a bucket. The key carries how many
    times *this provider* has already named that opponent, so six meetings the
    provider itself lists as six rows stay six observations."""
    from bet.simple_stats.analyze import _one_per_day

    bucket = [
        _pv(9.0, "tennis-abstract", "Terence Atmane", f"2026-0{i}-01", f"ta{i}")
        for i in range(1, 7)
    ]
    assert len(_one_per_day(bucket, "tennis")) == 6


def test_an_observation_with_no_opponent_is_kept_whole():
    """With nothing to place it by, dropping it would understate and merging it
    would guess. It is kept, exactly as an undated football row is."""
    from bet.simple_stats.analyze import _one_per_day

    bucket = [
        _pv(9.0, "tennis-abstract", "", "2026-08-17", "ta1"),
        _pv(4.0, "tennis-abstract", "", "2026-08-17", "ta2"),
    ]
    assert len(_one_per_day(bucket, "tennis")) == 2


# --- 4. a cap that hid a whole sport --------------------------------------
#
# _enrichment_priority's tie-break rewards corroboration, and corroboration is
# a property of the sport: 39 of 40 tennis fixtures were single-source, so every
# tennis event scored worse than every football event and the sport fell off the
# bottom of --max-events 40. bzzoiro-tennis still held 72 unspent requests.


def _event(event_id, sport, start_time="2026-08-28T20:00:00+00:00", confirmed=False):
    kwargs = dict(
        event_id=event_id,
        sport=sport,
        competition="X",
        start_time=start_time,
        identity_confidence="CONFIRMED" if confirmed else "FUZZY_MATCHED",
        status="ACTIVE",
    )
    if sport == "tennis":
        kwargs.update(player_one="A", player_two="B")
    else:
        kwargs.update(home_team="A", away_team="B")
    return EventRecord(**kwargs)


def test_the_cap_is_split_between_sports_so_none_can_be_zeroed():
    """The real 2026-08-28 shape: 347 football, 40 tennis, cap 40."""
    now = datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc)
    active = [_event(f"f{i}", "football", confirmed=True) for i in range(347)]
    active += [_event(f"t{i}", "tennis") for i in range(40)]

    kept, skipped = _apportion_cap(active, 40, now)

    assert len(kept) == 40
    assert len(kept) + len(skipped) == len(active)
    by_sport = {"football": 0, "tennis": 0}
    for event in kept:
        by_sport[event.sport] += 1
    # Proportional: 40 of 387 is a tenth of the slate.
    assert by_sport == {"football": 36, "tennis": 4}


def test_a_sport_that_cannot_fill_its_share_hands_the_slots_back():
    """A thin tennis day must not leave football slots unspent."""
    now = datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc)
    active = [_event(f"f{i}", "football") for i in range(50)]
    active += [_event("t0", "tennis")]

    kept, skipped = _apportion_cap(active, 20, now)

    assert len(kept) == 20
    assert sum(1 for e in kept if e.sport == "tennis") == 1
    assert sum(1 for e in kept if e.sport == "football") == 19


def test_every_sport_present_gets_at_least_one_slot():
    now = datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc)
    active = [_event(f"f{i}", "football") for i in range(400)]
    active += [_event("t0", "tennis")]

    kept, _ = _apportion_cap(active, 5, now)
    assert sum(1 for e in kept if e.sport == "tennis") == 1
    assert len(kept) == 5


def test_the_cap_still_ranks_within_a_sport():
    """Apportionment decides how many, _enrichment_priority still decides which:
    a started fixture is not bettable pre-match and goes last."""
    now = datetime(2026, 8, 28, 20, 0, tzinfo=timezone.utc)
    started = _event("started", "football", start_time="2026-08-28T10:00:00+00:00")
    upcoming = _event("upcoming", "football", start_time="2026-08-28T23:00:00+00:00")

    kept, skipped = _apportion_cap([started, upcoming], 1, now)
    assert [e.event_id for e in kept] == ["upcoming"]
    assert [e.event_id for e in skipped] == ["started"]


# --- 5. a payload that is not a completed match ---------------------------


@pytest.mark.parametrize(
    "combined, provider, expected",
    [
        # espn-football publishes 0.0 for stats it does not carry, and the
        # collapse preferred that zero over bzzoiro's real value. 237 false
        # observations across 17 events; sheet-wide DISAGREE fell 250 to 26.
        ({"corners_total": 0.0, "fouls_total": 0.0}, "espn-football", True),
        ({"fouls_total": 0.0, "corners_total": 9.0}, "espn-football", True),
        ({"corners_total": 9.0, "fouls_total": 22.0}, "espn-football", False),
        # A completed singles match is at least 6-0 6-0. Anything shorter is a
        # retirement or a walkover, and it flatters every UNDER it enters: 12
        # such rows were on the 2026-08-28 sheet, one of them a 3-game "match".
        ({"total_games": 3.0, "total_sets": 0.0}, "espn-tennis", True),
        ({"total_games": 9.0, "total_sets": 1.0}, "tennis-abstract", True),
        ({"total_games": 12.0, "total_sets": 2.0}, "espn-tennis", False),
        ({"total_games": 21.0, "total_sets": 2.0}, "tennis-abstract", False),
        # A payload that simply does not carry the field is not judged by it.
        ({"aces_total": 4.0}, "tennis-abstract", False),
        ({}, "tennis-abstract", False),
    ],
)
def test_an_incomplete_payload_is_absent_not_zero(combined, provider, expected):
    assert _is_absent_not_zero(combined, provider) is expected
