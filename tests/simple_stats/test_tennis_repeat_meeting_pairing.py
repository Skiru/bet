"""Repeat meetings with the same opponent must pair by date, not arrival order.

``_tennis_match_keys`` numbers occurrences per (provider, opponent) so that one
match reported by two providers collapses to one observation while a genuine
second meeting survives. The numbering used to follow the order rows happened
to arrive in, and that mispaired them whenever a provider listed two meetings
out of chronological order.

Andreeva - Tjen on the 2026-09-07 slate is the case. tennis-abstract had one
row (Cincinnati, 20 games) dated 2026-08-13 -- which is the *tournament start*,
because that provider has no match dates at all -- and espn-tennis had two,
listed US Open first (2026-09-01, 16 games) and Cincinnati second (2026-08-18,
20 games). Slot 0 therefore merged tennis-abstract's Cincinnati read with
espn's US Open match and averaged them to **18.0**, a match that never
happened, while the two real Cincinnati reads never met and so never counted as
corroboration.

Measured across that slate: 22 of 707 tennis (bucket, opponent) groups had a
provider carrying two distinct match ids and were exposed to this; 19 merged
values that actually differ, the worst averaging a 22-game match with a
49-game one.

Sorting each provider's rows by ``match_date`` before numbering is a rank
pairing -- no window, no tolerance, nothing fitted -- and it is exactly what
the two providers saw.
"""
from __future__ import annotations

from collections import defaultdict

from bet.simple_stats.analyze import _tennis_match_keys
from bet.simple_stats.contracts import ProviderValue


def _pv(provider: str, match_id: str, match_date: str, opponent: str, value: float):
    return ProviderValue(
        provider=provider,
        match_id=match_id,
        match_date=match_date,
        opponent=opponent,
        value=value,
        observed_at="2026-09-07T00:00:00Z",
    )


def _slots(values):
    grouped = defaultdict(list)
    for key, value in zip(_tennis_match_keys(values), values):
        grouped[key].append(value)
    return grouped


def test_the_andreeva_tjen_case_pairs_cincinnati_with_cincinnati():
    """The regression, with the real values and the real listing order."""
    values = [
        # tennis-abstract dates by tournament week, not by match.
        _pv("tennis-abstract", "ta_Tjen", "2026-08-13", "Janice Tjen", 20.0),
        # espn lists the US Open match *first*.
        _pv("espn-tennis", "182628", "2026-09-01T19:45Z", "Janice Tjen", 16.0),
        _pv("espn-tennis", "182325", "2026-08-18T16:45Z", "Janice Tjen", 20.0),
    ]
    slots = _slots(values)

    assert len(slots) == 2, f"expected two meetings, got {sorted(slots)}"
    first = sorted(slots["janice tjen#0"], key=lambda v: v.provider)
    second = slots["janice tjen#1"]

    # Slot 0 is Cincinnati, seen by both providers, and they agree.
    assert {v.value for v in first} == {20.0}, (
        "slot 0 must hold the two Cincinnati reads; it holds "
        f"{[(v.provider, v.match_date, v.value) for v in first]}"
    )
    assert {v.provider for v in first} == {"tennis-abstract", "espn-tennis"}
    # Slot 1 is the US Open match, alone and unaveraged.
    assert [v.value for v in second] == [16.0]
    assert [v.match_id for v in second] == ["182628"]


def test_no_slot_averages_two_different_matches():
    """The general property: a slot may hold at most one match per provider.

    Two rows from the *same* provider in one slot means two distinct matches
    were merged, which is the defect regardless of which fixture produced it.
    """
    values = [
        _pv("tennis-abstract", "ta_A", "2026-08-13", "Janice Tjen", 20.0),
        _pv("espn-tennis", "182628", "2026-09-01T19:45Z", "Janice Tjen", 16.0),
        _pv("espn-tennis", "182325", "2026-08-18T16:45Z", "Janice Tjen", 20.0),
        _pv("espn-tennis", "182999", "2026-07-02T12:00Z", "Michael Zheng", 22.0),
        _pv("espn-tennis", "183000", "2026-08-20T12:00Z", "Michael Zheng", 49.0),
    ]
    for key, rows in _slots(values).items():
        providers = [row.provider for row in rows]
        assert len(providers) == len(set(providers)), (
            f"slot {key} merges two matches from one provider: "
            f"{[(r.provider, r.match_id, r.value) for r in rows]}"
        )


def test_a_single_meeting_seen_twice_still_collapses():
    """The behaviour the occurrence numbering exists for, unchanged."""
    values = [
        _pv("tennis-abstract", "ta_X", "2026-08-13", "Clara Tauson", 21.0),
        _pv("espn-tennis", "1111", "2026-08-14T12:00Z", "Clara Tauson", 21.0),
    ]
    slots = _slots(values)
    assert list(slots) == ["clara tauson#0"]
    assert len(slots["clara tauson#0"]) == 2


def test_pairing_is_independent_of_listing_order():
    """Determinism: shuffling the input must not change the slots."""
    base = [
        _pv("tennis-abstract", "ta_A", "2026-08-13", "Janice Tjen", 20.0),
        _pv("espn-tennis", "182325", "2026-08-18T16:45Z", "Janice Tjen", 20.0),
        _pv("espn-tennis", "182628", "2026-09-01T19:45Z", "Janice Tjen", 16.0),
    ]
    forward = {k: sorted(v.match_id for v in rows) for k, rows in _slots(base).items()}
    reverse = {
        k: sorted(v.match_id for v in rows)
        for k, rows in _slots(list(reversed(base))).items()
    }
    assert forward == reverse
