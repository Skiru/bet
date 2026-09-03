"""The gate on `tipster-reader`'s output, tested from the attacker's side.

This is the only place a language model's reading reaches an operator-facing
file, so the tests below are mostly about what must be *refused*: a paraphrased
claim, an invented tipster, a hallucinated market, a subject who is not playing,
a total with no line. Each of those is a way the appendix could carry a
confident falsehood, and each is a rejection with a named reason rather than a
repair.

The one thing the validator must never do is fix a bad reading. A repaired
reading is one nobody wrote and nobody can check.
"""
from __future__ import annotations

from bet.simple_stats.contracts import (
    TipsterEventSignal,
    TipsterPickRef,
    TipsterSignalV1,
)
from bet.simple_stats.tipster_claims import CANONICAL_MARKETS, validate_readings

AT = "2026-09-03T06:00:00+00:00"
EVENT = "3a0129f6f611332798e5ff6d604b179c7a58ef66c3fd1cae86ad81223734d45a"


def _signal(claim="o2,5", tipster="Elite VIP", home="Grêmio", away="Internacional"):
    return TipsterSignalV1(
        run_id="r",
        date="2026-09-03",
        generated_at=AT,
        picks_ingested=1,
        picks_matched=1,
        events=[
            TipsterEventSignal(
                event_id=EVENT,
                home_team=home,
                away_team=away,
                match_quality="EXACT",
                match_score=100,
                picks=[
                    TipsterPickRef(
                        source_id="zawodtyper",
                        source_name="ZawodTyper",
                        tipster_name=tipster,
                        claim=claim,
                        market=None,
                        line=None,
                        direction="OTHER",
                        subjects=[],
                        countable=False,
                        reject_reason="",
                        odds=1.5,
                        match_date="2026-09-03",
                    )
                ],
                public_lean={},
            )
        ],
    )


def _reading(**over):
    base = {
        "event_id": EVENT,
        "tipster_name": "Elite VIP",
        "source_id": "zawodtyper",
        "claim": "o2,5",
        "read_confidence": "CLEAR",
        "parser_agrees": False,
        "legs": [
            {
                "kind": "TOTAL",
                "market": "goals_total",
                "line": 2.5,
                "direction": "OVER",
                "subject": None,
                "note": "powyżej 2.5 gola",
            }
        ],
    }
    base.update(over)
    return {"readings": [base]}


def _validate(raw, signal=None):
    return validate_readings(raw, signal or _signal(), generated_at=AT)


# --- the happy path --------------------------------------------------------

def test_a_shorthand_total_the_regex_cannot_read_is_accepted():
    """`o2,5` is the whole reason this agent exists: the rules path refuses it
    as a total with no readable line."""
    claims = _validate(_reading())
    assert claims.readings_accepted == 1
    assert claims.readings_rejected == 0
    leg = claims.readings[0].legs[0]
    assert (leg.market, leg.line, leg.direction) == ("goals_total", 2.5, "OVER")
    assert claims.readings[0].parsed_by == "agent"
    assert claims.parser_disagreements == 1


def test_unreadable_is_a_valid_answer():
    """Ten honest refusals beat one confident wrong reading, so `UNREADABLE`
    must survive validation rather than being treated as a malformed leg."""
    claims = _validate(
        _reading(
            claim="4.5+",
            legs=[{"kind": "UNREADABlE".upper(), "market": None, "line": None,
                   "direction": None, "subject": None,
                   "note": "nie wiadomo, czego 4.5"}],
        ),
        _signal(claim="4.5+"),
    )
    assert claims.readings_accepted == 1
    assert claims.legs_unreadable == 1


def test_a_combo_keeps_both_legs_in_written_order():
    signal = _signal(claim="+2,5 kartek w meczu + Jagiellonia strzeli gola")
    claims = _validate(
        _reading(
            claim="+2,5 kartek w meczu + Jagiellonia strzeli gola",
            legs=[
                {"kind": "TOTAL", "market": "cards_total", "line": 2.5,
                 "direction": "OVER", "subject": None, "note": "kartki"},
                {"kind": "OUTCOME", "market": None, "line": None,
                 "direction": None, "subject": "Internacional",
                 "note": "strzeli gola - poza słownikiem"},
            ],
        ),
        signal,
    )
    assert claims.readings_accepted == 1
    assert claims.legs_total == 2
    assert [leg.kind for leg in claims.readings[0].legs] == ["TOTAL", "OUTCOME"]


def test_a_per_side_total_records_whose():
    signal = _signal(claim="Liczba fauli Internacional -13,5")
    claims = _validate(
        _reading(
            claim="Liczba fauli Internacional -13,5",
            legs=[{"kind": "TOTAL", "market": "fouls_for", "line": 13.5,
                   "direction": "UNDER", "subject": "Internacional",
                   "note": "faule jednej strony"}],
        ),
        signal,
    )
    assert claims.readings_accepted == 1
    assert claims.readings[0].legs[0].subject == "Internacional"


# --- what must be refused --------------------------------------------------

def test_a_paraphrased_claim_is_rejected():
    """The load-bearing check. If the claim text may drift, the artifact stops
    being anchored to anything a human can go and read."""
    claims = _validate(_reading(claim="over 2.5 goals"))
    assert claims.readings_accepted == 0
    assert claims.rejected_by_reason == {"nie odpowiada żadnemu zebranemu typowi": 1}


def test_an_invented_tipster_is_rejected():
    claims = _validate(_reading(tipster_name="Nobody At All"))
    assert claims.readings_accepted == 0
    assert "nie odpowiada żadnemu zebranemu typowi" in claims.rejected_by_reason


def test_a_reading_pinned_to_the_wrong_fixture_is_rejected():
    claims = _validate(_reading(event_id="f" * 64))
    assert claims.readings_accepted == 0
    assert "nie odpowiada żadnemu zebranemu typowi" in claims.rejected_by_reason


def test_a_hallucinated_market_is_rejected():
    claims = _validate(
        _reading(legs=[{"kind": "TOTAL", "market": "throw_ins_total", "line": 20.5,
                        "direction": "OVER", "subject": None, "note": ""}])
    )
    assert claims.readings_accepted == 0
    assert claims.rejected_by_reason == {
        "rynek poza słownikiem (throw_ins_total)": 1
    }


def test_a_total_without_a_line_is_rejected():
    """The agent gets no licence the rules path does not have: `over` with no
    number is not a claim."""
    claims = _validate(
        _reading(legs=[{"kind": "TOTAL", "market": "goals_total", "line": None,
                        "direction": "OVER", "subject": None, "note": ""}])
    )
    assert claims.rejected_by_reason == {"total bez linii": 1}


def test_a_direction_outside_the_vocabulary_is_rejected():
    claims = _validate(
        _reading(legs=[{"kind": "OUTCOME", "market": None, "line": None,
                        "direction": "HOME_WINS_TO_NIL", "subject": None, "note": ""}])
    )
    assert claims.rejected_by_reason == {
        "kierunek poza słownikiem (HOME_WINS_TO_NIL)": 1
    }


def test_a_subject_who_is_not_playing_is_rejected():
    claims = _validate(
        _reading(legs=[{"kind": "TOTAL", "market": "fouls_for", "line": 13.5,
                        "direction": "UNDER", "subject": "Palmeiras", "note": ""}])
    )
    assert claims.rejected_by_reason == {"podmiot nie jest żadną ze stron meczu": 1}


def test_a_match_total_must_not_carry_a_subject():
    """`fouls_total` with a subject is a category error -- either it is the
    match's fouls or one side's, and the two settle differently."""
    claims = _validate(
        _reading(legs=[{"kind": "TOTAL", "market": "fouls_total", "line": 20.5,
                        "direction": "UNDER", "subject": "Grêmio", "note": ""}])
    )
    assert claims.rejected_by_reason == {
        "fouls_total to total meczowy, a podano podmiot": 1
    }


def test_a_per_side_total_without_a_subject_is_rejected():
    claims = _validate(
        _reading(legs=[{"kind": "TOTAL", "market": "cards_for", "line": 2.5,
                        "direction": "UNDER", "subject": None, "note": ""}])
    )
    assert claims.rejected_by_reason == {"cards_for bez wskazanego podmiotu": 1}


def test_an_outcome_carrying_a_line_is_rejected():
    claims = _validate(
        _reading(legs=[{"kind": "OUTCOME", "market": None, "line": 2.5,
                        "direction": "HOME", "subject": None, "note": ""}])
    )
    assert claims.rejected_by_reason == {"OUTCOME z rynkiem/linią": 1}


def test_unreadable_claiming_something_is_rejected():
    """`UNREADABLE` means "I could not tell". A leg that says that *and* names a
    market is incoherent, and letting it through would hide a real reading
    behind a refusal."""
    claims = _validate(
        _reading(legs=[{"kind": "UNREADABLE", "market": "goals_total", "line": 2.5,
                        "direction": "OVER", "subject": None, "note": ""}])
    )
    assert claims.rejected_by_reason == {
        "UNREADABLE z wypełnionym rynkiem/linią/kierunkiem": 1
    }


def test_a_guess_confidence_is_stored_not_refused():
    """`GUESS` is discouraged in the prompt, not forbidden by the contract --
    the operator should see one that slipped through, labelled, rather than
    have it vanish."""
    claims = _validate(_reading(read_confidence="GUESS"))
    assert claims.readings_accepted == 1
    assert claims.readings[0].read_confidence == "GUESS"


def test_an_unknown_confidence_value_is_rejected():
    claims = _validate(_reading(read_confidence="VERY_SURE"))
    assert claims.rejected_by_reason == {"nieznane read_confidence (VERY_SURE)": 1}


def test_a_reading_with_no_legs_is_rejected():
    claims = _validate(_reading(legs=[]))
    assert claims.rejected_by_reason == {"brak nóg w odczycie": 1}


# --- behaviour of the gate as a whole --------------------------------------

def test_one_bad_reading_does_not_cost_the_others():
    """Rejection is per reading. A malformed entry must not throw away the
    day's other fifty."""
    good = _reading()["readings"][0]
    bad = dict(good, claim="paraphrased")
    claims = _validate({"readings": [good, bad]})
    assert (claims.readings_accepted, claims.readings_rejected) == (1, 1)


def test_nothing_is_repaired_only_dropped():
    """A repaired reading is one nobody wrote and nobody can check, so the
    accepted set is a strict subset of the input -- never a corrected version."""
    claims = _validate(
        _reading(legs=[{"kind": "TOTAL", "market": "goals_total", "line": None,
                        "direction": "OVER", "subject": None, "note": ""}])
    )
    assert claims.readings == []


def test_player_props_may_name_somebody_who_is_not_a_listed_side():
    """A football fixture lists clubs, so a player prop's subject is a person
    and cannot be one of the two names. Refusing it would delete the whole
    player-prop family from this appendix."""
    signal = _signal(claim="MANTOVA POWYŻEJ 9.5 STRZAŁÓW")
    claims = _validate(
        _reading(
            claim="MANTOVA POWYŻEJ 9.5 STRZAŁÓW",
            legs=[{"kind": "TOTAL", "market": "player_total_shots", "line": 9.5,
                   "direction": "OVER", "subject": "Some Player", "note": ""}],
        ),
        signal,
    )
    assert claims.readings_accepted == 1


def test_totals_are_reported_for_the_step_summary():
    claims = _validate(_reading())
    assert claims.picks_in_signal == 1
    assert claims.legs_total == 1
    assert claims.date == "2026-09-03"


def test_no_probability_or_price_field_exists_on_the_contract():
    """The boundary in the type system: this artifact describes opinions. A
    p_low or a fair price here would read as a model output."""
    from bet.simple_stats.tipster_claims import ClaimLeg, ClaimReading, TipsterClaimsV1

    banned = {
        "p_low", "p_central", "fair_odds", "min_acceptable_odds", "tier",
        "probability", "edge", "hit_rate", "confidence_pct",
    }
    for model in (ClaimLeg, ClaimReading, TipsterClaimsV1):
        assert not set(model.model_fields) & banned, model.__name__


def test_market_vocabulary_matches_what_the_sheet_prices():
    """If the two drift, the agent is told to use a market that has nowhere to
    land, or refused one it should be allowed."""
    for market in ("goals_total", "cards_for", "total_games", "player_total_shots"):
        assert market in CANONICAL_MARKETS
    assert "throw_ins_total" not in CANONICAL_MARKETS
