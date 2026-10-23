"""P6 of the coverage audit 2026-10-23 (B6): a footballer's zero offsides
from the team's rebuilt 0-0 (epochs.PLAYER_OMITTED_ZERO_FROM_UTC).

The per-half full feed drops `offsides` on a 0-0; the team reader restores
the 0-0 (metrics.fill_omitted_zero_pairs) but the player reader read the raw
payload, so every player's missing `totalOffside` stayed STAT_KEY_ABSENT and
the genuine zeros left the sample. Off: exactly that. On: the zeros count.
"""

from __future__ import annotations

from typing import Any

from bet.sofa.contracts import GapReason
from bet.sofa.players import extract_player_metric, squad_statistics, team_totals


def item(key: str, home: float, away: float) -> dict[str, Any]:
    return {"key": key, "homeValue": home, "awayValue": away}


def stats(*, offsides_all: tuple[float, float] | None = None,
          offsides_half: bool = False) -> dict[str, Any]:
    whole = [item("passes", 400, 380), item("fouls", 10, 12)]
    if offsides_all is not None:
        whole.append(item("offsides", *offsides_all))
    first = [item("passes", 200, 190)]
    if offsides_half:
        first.append(item("offsides", 1, 0))
    return {"statistics": [
        {"period": "ALL", "groups": [{"statisticsItems": whole}]},
        {"period": "1ST", "groups": [{"statisticsItems": first}]},
        {"period": "2ND", "groups": [{"statisticsItems": [item("passes", 200, 190)]}]},
    ]}


def lineups() -> dict[str, Any]:
    def entry(i: int, minutes: int | None) -> dict[str, Any]:
        st: dict[str, Any] = {"fouls": 1}
        if minutes is not None:
            st["minutesPlayed"] = minutes
        return {"player": {"name": f"Player {i}", "id": i}, "substitute": i > 11,
                "statistics": st}
    players = [entry(i, 90) for i in range(1, 12)] + [entry(12, None)]
    return {"home": {"players": players}, "away": {"players": players}}


def offsides(payload: dict[str, Any], omitted_zero: bool) -> float | GapReason:
    squad = squad_statistics(lineups(), is_home=True, statistics=payload,
                             omitted_zero=omitted_zero)
    assert squad is not None
    return extract_player_metric("player_offsides_for", squad["player 1"])


def test_off_the_omitted_team_zero_leaves_the_player_a_gap() -> None:
    assert offsides(stats(), omitted_zero=False) is GapReason.STAT_KEY_ABSENT


def test_on_the_omitted_team_zero_proves_the_player_zero() -> None:
    assert offsides(stats(), omitted_zero=True) == 0.0


def test_on_a_half_carrying_offsides_is_not_that_shape() -> None:
    assert offsides(stats(offsides_half=True), omitted_zero=True) is (
        GapReason.STAT_KEY_ABSENT)


def test_a_sent_key_is_never_touched() -> None:
    payload = stats(offsides_all=(2.0, 1.0))
    assert team_totals(payload, is_home=True, omitted_zero=True)["offsides"] == 2.0
    # the players' sum (0) does not close the team's 2: a gap either way
    for on in (False, True):
        assert offsides(payload, omitted_zero=on) is GapReason.STAT_KEY_ABSENT


def test_team_totals_off_is_the_raw_payload() -> None:
    assert "offsides" not in team_totals(stats(), is_home=True)
    assert team_totals(stats(), is_home=False, omitted_zero=True)["offsides"] == 0.0


def test_a_player_who_never_came_on_stays_out() -> None:
    squad = squad_statistics(lineups(), is_home=True, statistics=stats(),
                             omitted_zero=True)
    assert squad is not None
    assert extract_player_metric("player_offsides_for", squad["player 12"]) is (
        GapReason.EVENT_NOT_FINISHED)
