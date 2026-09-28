"""cs2_watchdog.decide: what one look leads to."""

from datetime import UTC, datetime, timedelta

from scripts.sofa.cs2_watchdog import BRIDGE_STALE_S, SETTLE_RETRY, Seen, decide

NOW = datetime(2026, 9, 30, 6, 0, tzinfo=UTC)
D = "2026-09-29"


def seen(**kw: object) -> Seen:
    base: dict[str, object] = {
        "bridge_up": True,
        "pull_age_s": 1.0,
        "alive": {D: True},
        "done": {D: False},
        "retryable": {D: None},
    }
    base.update(kw)
    return Seen(**base)  # type: ignore[arg-type]


def test_a_healthy_running_day_needs_nothing() -> None:
    assert decide(seen(), NOW, {}, None) == []


def test_a_dead_unfinished_day_is_relaunched() -> None:
    assert decide(seen(alive={D: False}), NOW, {}, None) == [("RELAUNCH", D)]


def test_a_down_bridge_server_is_restarted_and_nothing_settles() -> None:
    s = seen(bridge_up=False, alive={D: False}, done={D: True}, retryable={D: 3})
    assert decide(s, NOW, {}, None) == [("RESTART_BRIDGE", "")]


def test_stale_tabs_alert_at_most_every_half_hour_and_block_settling() -> None:
    s = seen(
        pull_age_s=BRIDGE_STALE_S + 1,
        done={D: True},
        alive={D: False},
        retryable={D: 2},
    )
    assert decide(s, NOW, {}, None) == [("ALERT_TABS", "")]
    assert decide(s, NOW, {}, NOW - timedelta(minutes=10)) == []


def test_a_finished_day_is_resettled_until_nothing_is_left() -> None:
    done = {"done": {D: True}, "alive": {D: False}}
    assert decide(seen(**done, retryable={D: None}), NOW, {}, None) == [("RESETTLE", D)]
    assert decide(seen(**done, retryable={D: 2}), NOW, {}, None) == [("RESETTLE", D)]
    assert decide(seen(**done, retryable={D: 0}), NOW, {}, None) == []
    recent = {D: NOW - SETTLE_RETRY / 2}
    assert decide(seen(**done, retryable={D: 2}), NOW, recent, None) == []


def test_the_settle_window_closes() -> None:
    late = NOW + timedelta(days=5)
    s = seen(done={D: True}, alive={D: False}, retryable={D: 2})
    assert decide(s, late, {}, None) == []
