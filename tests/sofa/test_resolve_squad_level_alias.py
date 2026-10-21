"""RESOLVE's squad-level alias (2026-10-21): one squad, two level names -
resolve.squad_level_alias_event, resolve.squad_level_shift,
resolve.football_squad_levels, epochs.FOOTBALL_SQUAD_LEVEL_ALIAS_FROM_UTC.

Superbet's "Cosenza U19 - Frosinone U19" is Sofascore's "Cosenza U20 -
Frosinone U20"; "Houston Dynamo II - Los Angeles FC II" is "Houston Dynamo 2
- Los Angeles FC 2"; the level gate refused both. Measured:
scripts/sofa/measure_squad_level_alias.py,
docs/sofa/history/RAPORT_RESOLVE_POZIOM_2026-10-21.md.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.db import migrate
from bet.sofa.names import normalize_name, team_levels
from bet.sofa.resolve import (
    SofaResolver,
    football_squad_levels,
    level_free_name,
    parse_fixture,
    squad_alias_candidate,
    squad_alias_veto,
    squad_level_alias,
    squad_level_alias_event,
    squad_level_shift,
)

NOW = datetime.now(UTC)
KICKOFF = NOW + timedelta(hours=3)
KO_TS = int(KICKOFF.timestamp())


def _team(id_: int, name: str, gender: str = "M") -> dict[str, Any]:
    return {"id": id_, "name": name, "gender": gender, "sport": {"slug": "football"}}


def _ev(eid: int, home: tuple[int, str], away: tuple[int, str],
        dt_min: int = 0, status: str = "notstarted") -> dict[str, Any]:
    return {
        "id": eid, "startTimestamp": KO_TS + 60 * dt_min,
        "status": {"type": status},
        "tournament": {"name": "Primavera 2"},
        "homeTeam": {"id": home[0], "name": home[1], "gender": "M"},
        "awayTeam": {"id": away[0], "name": away[1], "gender": "M"},
    }


COSENZA = (276317, "Cosenza U20")
FROSINONE = (64100, "Frosinone U20")
GAME = _ev(16827389, COSENZA, FROSINONE)
N = normalize_name


def _alias(cands: list[tuple[dict[str, Any], list[dict[str, Any]]]],
           side: str, opp: str, a: str, b: str) -> Any:
    return squad_level_alias_event(cands, KICKOFF, side, opp, a, b)


def test_levels_two_is_a_reserve_only_here() -> None:
    assert football_squad_levels(N("Houston Dynamo 2")) == {"R"}
    assert football_squad_levels(N("Skeid 2 (W)")) == {"R"}
    # Every other reader keeps the old reading (no cache / level change).
    assert team_levels(N("Houston Dynamo 2")) == {"S"}
    assert N("Houston Dynamo 2") == "houston dynamo 2"
    assert football_squad_levels(N("Bohemians 1905")) == {"S"}
    assert level_free_name(N("Los Angeles FC 2")) == "los angeles fc"
    assert level_free_name(N("L.R. Vicenza U20")) == "l.r. vicenza"


def test_which_levels_may_name_each_other() -> None:
    assert squad_level_alias("U19", "U20") and squad_level_alias("U20", "U19")
    assert squad_level_alias("R", "U20") and squad_level_alias("U23", "R")
    assert squad_level_alias("R", "R")
    assert not squad_level_alias("U19", "U21")      # two years apart
    assert not squad_level_alias("R", "U17")        # a reserve side is no U17
    assert not squad_level_alias("S", "U19")        # never youth <-> senior
    assert not squad_level_alias("R", "S")          # never reserves <-> senior
    assert not squad_level_alias("S", "S")


def test_the_shift_is_pair_consistent() -> None:
    assert squad_level_shift(N("Cosenza U19"), N("Cosenza U20"),
                             N("Frosinone U19"), N("Frosinone U20")) == "U19->U20"
    # Sofascore's own mixed pair (Pisa U19 - Ascoli U20) is refused.
    assert squad_level_shift(N("Pisa U19"), N("Pisa U19"),
                             N("Ascoli U19"), N("Ascoli U20")) is None
    # Superbet's own mixed pair (Modena U19 - Cremonese U20) likewise.
    assert squad_level_shift(N("Modena U19"), N("Modena U20"),
                             N("Cremonese U20"), N("Cremonese U20")) is None
    # A senior board side stays senior; the reserve side shifts alone.
    assert squad_level_shift(N("Leuven B"), N("OH Leuven U23"),
                             N("KRC Harelbeke"), N("Racing Club Harelbeke")) == "R->U23"
    assert squad_level_shift(N("Leuven B"), N("OH Leuven U23"),
                             N("KRC Harelbeke"), N("Harelbeke U23")) is None
    # Reserves never become the first team (Mechelen B, 10-17).
    assert squad_level_shift(N("Zulte Waregem B"), N("S.V. Zulte-Waregem B"),
                             N("Mechelen B"), N("Yellow Red K.V. Mechelen")) is None
    # Two senior board sides never shift.
    assert squad_level_shift(N("Roma"), N("Roma U20"),
                             N("Lazio"), N("Lazio U20")) is None


def test_the_primavera_pair_is_found() -> None:
    got = _alias([(_team(*COSENZA), [GAME])], "Cosenza U19", "Frosinone U19",
                 "Cosenza U19", "Frosinone U19")
    assert got is not None and got[1]["id"] == 16827389 and got[2] == "U19->U20"


def test_mls_next_pro_two() -> None:
    game = _ev(17172261, (407234, "Houston Dynamo 2"), (467298, "Los Angeles FC 2"))
    got = _alias([(_team(407234, "Houston Dynamo 2"), [game])], "Houston Dynamo II",
                 "Los Angeles FC II", "Houston Dynamo II", "Los Angeles FC II")
    assert got is not None and got[2] == "R->R"


def test_refusals() -> None:
    cands = [(_team(*COSENZA), [GAME])]
    # Reversed against Superbet's order (F25).
    assert _alias(cands, "Cosenza U19", "Frosinone U19",
                  "Frosinone U19", "Cosenza U19") is None
    # The opponent is another club.
    assert _alias(cands, "Cosenza U19", "Crotone U19",
                  "Cosenza U19", "Crotone U19") is None
    # The board is senior: never a youth game.
    assert _alias(cands, "Cosenza", "Frosinone", "Cosenza", "Frosinone") is None
    # Outside 60 minutes, or postponed.
    late = [(_team(*COSENZA), [_ev(1, COSENZA, FROSINONE, dt_min=90)])]
    assert _alias(late, "Cosenza U19", "Frosinone U19",
                  "Cosenza U19", "Frosinone U19") is None
    off = [(_team(*COSENZA), [_ev(1, COSENZA, FROSINONE, status="postponed")])]
    assert _alias(off, "Cosenza U19", "Frosinone U19",
                  "Cosenza U19", "Frosinone U19") is None
    # Two squads of the pair in the window (U18 and U20 both alias U19): refuse.
    u18 = (276999, "Cosenza U18")
    two = [(_team(*COSENZA), [GAME]),
           (_team(*u18), [_ev(2, u18, (64199, "Frosinone U18"), dt_min=30)])]
    assert _alias(two, "Cosenza U19", "Frosinone U19",
                  "Cosenza U19", "Frosinone U19") is None


def test_own_name_must_be_the_sides() -> None:
    # "CA Independiente" is not "Independiente Rivadavia" (89.7 < 90).
    ca = (2001, "CA Independiente Reserve")
    game = _ev(5, ca, (2002, "Ferro Carril Oeste Reserve"))
    assert _alias([(_team(*ca), [game])], "Independiente Rivadavia U19",
                  "Ferro Carril Oeste U19", "Independiente Rivadavia U19",
                  "Ferro Carril Oeste U19") is None


def test_the_opponents_own_team_playing_elsewhere_vetoes() -> None:
    gc = (3001, "Grasshopper Club Zürich U19")
    game = _ev(16456713, (3000, "FC Winterthur U19"), gc)
    fcz = (3002, "FC Zürich II")
    elsewhere = _ev(7, fcz, (3003, "FC Basel II"), dt_min=-30)
    assert squad_alias_veto(game, KICKOFF, [(_team(*fcz), [elsewhere])])
    # A namesake with no game then does not veto, nor does the game's own side.
    assert not squad_alias_veto(game, KICKOFF, [(_team(*fcz), [])])
    assert not squad_alias_veto(game, KICKOFF, [(_team(*gc), [game])])
    later = _ev(8, fcz, (3003, "FC Basel II"), dt_min=120)
    assert not squad_alias_veto(game, KICKOFF, [(_team(*fcz), [later])])


def test_alias_candidate_filter() -> None:
    assert squad_alias_candidate(N("Cosenza U19"), _team(*COSENZA))
    assert not squad_alias_candidate(N("Cosenza U19"), _team(1, "Cosenza"))
    assert not squad_alias_candidate(N("Cosenza U19"), _team(2, "Cosenza U17"))
    assert not squad_alias_candidate(N("Cosenza U19"), _team(3, "Crotone U20"))
    assert not squad_alias_candidate(N("Cosenza U19"), _team(4, "Cosenza U20", "F"))


class _Client:
    def search(self, q: str) -> dict[str, Any]:
        if "cosenza" in q.lower():
            return {"results": [
                {"type": "team", "entity": _team(1, "Cosenza")},
                {"type": "team", "entity": _team(*COSENZA)}]}
        return {"results": []}

    def entity_events(self, entity_id: int, kind: str, page: int) -> dict[str, Any]:
        if page == 0 and kind == "next" and entity_id == COSENZA[0]:
            return {"events": [GAME], "hasNextPage": False}
        return {"events": [], "hasNextPage": False}

    def event(self, event_id: int) -> dict[str, Any] | None:
        return None


def _resolver(tmp_path: Any, name: str) -> SofaResolver:
    config = SofaConfig(db_path=str(tmp_path / f"{name}.db"))
    migrate(config.db_path)
    return SofaResolver(config, _Client(), SofaCache(config))  # type: ignore[arg-type]


def test_resolve_entity_switch_on_and_off(tmp_path: Any,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    def run(r: SofaResolver) -> tuple[Any, Any, bool]:
        return r.resolve_entity("football", "Cosenza U19", KICKOFF, "Frosinone U19",
                                board_side_a="Cosenza U19",
                                board_side_b="Frosinone U19")

    monkeypatch.setattr(epochs, "FOOTBALL_SEARCHED_ANCHOR_FROM_UTC", None)
    monkeypatch.setattr(epochs, "FOOTBALL_SQUAD_LEVEL_ALIAS_FROM_UTC", None)
    assert run(_resolver(tmp_path, "off")) == (None, None, False)

    monkeypatch.setattr(epochs, "FOOTBALL_SQUAD_LEVEL_ALIAS_FROM_UTC",
                        NOW - timedelta(hours=1))
    r = _resolver(tmp_path, "on")
    entity_id, event, ambiguous = run(r)
    assert (entity_id, ambiguous) == (COSENZA[0], False)
    assert event["id"] == 16827389
    assert event["_match_rule"] == "SQUAD_LEVEL_ALIAS:U19->U20"
    fixture = parse_fixture(event, "football", ["1"], r.client, identity="FUZZY")
    assert fixture.match_rule == "SQUAD_LEVEL_ALIAS:U19->U20"
    # Nothing learned: "cosenza u19" is not a verified alias of the U20 side.
    cached = r.cache.get_entity("football", "cosenza u19")
    assert not cached or cached["status"] != "verified"
    # A miss recorded before the switch does not block the name.
    r2 = _resolver(tmp_path, "miss")
    monkeypatch.setattr(epochs, "FOOTBALL_SQUAD_LEVEL_ALIAS_FROM_UTC", None)
    assert run(r2) == (None, None, False)
    assert r2.cache.get_entity_miss("football", "cosenza u19")
    monkeypatch.setattr(epochs, "FOOTBALL_SQUAD_LEVEL_ALIAS_FROM_UTC",
                        datetime.now(UTC) + timedelta(seconds=1))
    monkeypatch.setattr(epochs.timeutil, "now",
                        lambda: datetime.now(UTC) + timedelta(seconds=5))
    assert run(r2)[0] == COSENZA[0]


def test_the_loose_shift_lets_each_side_shift_alone() -> None:
    """epochs.FOOTBALL_SQUAD_LEVEL_ALIAS_LOOSE_FROM_UTC: the two mixed pairs the
    pair-consistent rule refuses; still never the senior squad."""
    assert squad_level_shift(N("Pisa U19"), N("Pisa U19"), N("Ascoli U19"),
                             N("Ascoli U20"), loose=True) == "U19->U19,U19->U20"
    assert squad_level_shift(N("Modena U19"), N("Modena U20"), N("Cremonese U20"),
                             N("Cremonese U20"), loose=True) == "U19->U20,U20->U20"
    assert squad_level_shift(N("Cosenza U19"), N("Cosenza U20"), N("Frosinone U19"),
                             N("Frosinone U20"), loose=True) == "U19->U20"
    assert squad_level_shift(N("Pisa U19"), N("Pisa"), N("Ascoli U19"),
                             N("Ascoli U20"), loose=True) is None
    assert squad_level_shift(N("Pisa U19"), N("Pisa U17"), N("Ascoli U19"),
                             N("Ascoli U20"), loose=True) is None
