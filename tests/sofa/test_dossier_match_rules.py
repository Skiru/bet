"""bet.sofa.dossier: a prop's pre-match lineup status honours every name rule
SAMPLES uses (transliteration, inner_surname, slug ...) by reading the
sample's own `matched_name`, and the samples block keeps each gap's detail so
the coverage audit's two new meanings of ENTITY_CONFLICT / THIN_SAMPLE read
apart from the old ones."""

from __future__ import annotations

from typing import Any

from bet.sofa import dossier

ENTRY: dict[str, Any] = {
    "home": {
        "starters": [{"id": 11, "name": "Julian Chabot"},
                     {"id": 12, "name": "Javi Martinez"}],
        "substitutes": [{"id": 13, "name": "Rafal Wolski"}],
        "missing": [],
    },
    "away": {"starters": [], "substitutes": [], "missing": []},
}


def _leg(subject: str) -> dict[str, Any]:
    return {"subject": subject, "market": "player_shots_for"}


def _sample(subject: str, matched: str, rule: str) -> dict[str, Any]:
    return {
        "players": {
            f"player_shots_for|{subject}": {
                "matched_name": matched, "side": "home", "match_rule": rule,
                "observations": [{"value": 2}, {"value": 1}],
            }
        },
        "gaps": [],
    }


def test_slug_matched_prop_is_found_through_the_samples_matched_name() -> None:
    # Superbet "Chabot Jules" - no name rule places it in the lineup; SAMPLES
    # matched it by slug to Sofascore's "Julian Chabot".
    leg = _leg("Chabot Jules")
    rows = dossier.player_leg_status(
        ENTRY, [leg], _sample("Chabot Jules", "Julian Chabot", "slug"))
    assert rows[0]["status"] == "XI"
    assert rows[0]["matched_name"] == "julian chabot"
    assert rows[0]["match_rule"] == "slug"


def test_inner_surname_rule_runs_in_the_dossier_without_a_sample() -> None:
    leg = _leg("Javier Martinez Calvo")
    rows = dossier.player_leg_status(ENTRY, [leg])
    assert rows[0]["status"] == "XI"
    assert rows[0]["match_rule"] == "inner_surname"


def test_transliteration_matched_prop_is_found_through_the_sample() -> None:
    leg = _leg("Rafał Wolski")
    entry = {"home": {"starters": [], "missing": [],
                      "substitutes": [{"id": 13, "name": "Rafal Wolsky"}]}}
    rows = dossier.player_leg_status(
        entry, [leg], _sample("Rafał Wolski", "Rafal Wolsky", "transliteration"))
    assert rows[0]["status"] == "ławka"


def test_unplaced_name_is_still_not_on_the_list() -> None:
    rows = dossier.player_leg_status(ENTRY, [_leg("Nobody Atall")])
    assert rows[0]["status"].startswith("nie ma na liście")


def test_samples_block_keeps_gap_detail_and_player_match_rule() -> None:
    sample = _sample("Chabot Jules", "Julian Chabot", "slug")
    sample["gaps"] = [
        {"reason": "ENTITY_CONFLICT", "metric": "all",
         "detail": "entity 5: clash; sample cut at the clash, 12 matches after it"},
        {"reason": "THIN_SAMPLE", "metric": "player_shots_for",
         "detail": "PLAYER_HISTORY_ANY_TEAM: player 'x' 3 starts ..."},
    ]
    block = dossier.samples_block(sample, [_leg("Chabot Jules")])
    assert block["gaps"][0]["reason"] == "ENTITY_CONFLICT"
    assert "sample cut at the clash" in block["gaps"][0]["detail"]
    assert block["gaps"][1]["detail"].startswith("PLAYER_HISTORY_ANY_TEAM")
    assert block["players"]["player_shots_for|Chabot Jules"]["match_rule"] == "slug"


def test_the_samples_matched_name_is_read_from_his_own_side_only() -> None:
    # Review R5 #3: the sampled player (side_b, the away side) is missing from
    # the away list; a home player of the same name is another person.
    leg = _leg("J. Chabot")
    sample = _sample("J. Chabot", "Julian Chabot", "slug")
    sample["players"]["player_shots_for|J. Chabot"]["side"] = "side_b"
    rows = dossier.player_leg_status(ENTRY, [leg], sample)
    assert rows[0].get("match_rule") != "slug"
    sample["players"]["player_shots_for|J. Chabot"]["side"] = "side_a"
    rows = dossier.player_leg_status(ENTRY, [leg], sample)
    assert rows[0]["match_rule"] == "slug" and rows[0]["status"] == "XI"
