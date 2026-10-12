# ruff: noqa: E501  - Superbet's market names are quoted whole.
"""MARKET COVERAGE of the measured sports (night plan 2026-10-12, C5).

SHADOW and CS2 record only the lines they read, so the unread names come from
raw Superbet payloads. Every name below is Superbet's own, from the 10-13
offer probed 2026-10-12 (64 events: 15 hockey, 23 basketball, 12 volleyball,
14 CS2; 0 UNCLASSIFIED).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.market_coverage import (
    LABELS,
    _RULES_BY_SPORT,
    build_sports_report,
    classify_sport_market_name,
    snapshot_inventory,
    sport_payload_names,
)
from scripts.sofa.report_market_coverage import main

HOCKEY = ["KooKoo Kouvola", "Mannheim"]
NHL = ["Detroit Red Wings", "Boston Bruins"]
BASKET = ["Fenerbahce", "Anadolu Efes"]
VOLLEY = ["Vilsbiburg (K)", "Suhl Thuringen (K)"]
CS2 = ["100 Thieves", "JiJieHao"]


@pytest.mark.parametrize(
    ("name", "sport", "sides", "label", "family"),
    [
        ("Podwójna szansa", "hockey", HOCKEY, "COMPUTABLE", "hk.double_chance"),
        ("1. tercja - podwójna szansa", "hockey", HOCKEY, "COMPUTABLE", "hk.double_chance"),
        ("1. gol", "hockey", HOCKEY, "NOT_COMPUTABLE", "hk.goal_order"),
        ("1. tercja - 1. gol", "hockey", HOCKEY, "NOT_COMPUTABLE", "hk.goal_order"),
        ("Drużyna zdobędzie 1.gola w meczu (z dogrywką i rzutami karnymi)", "hockey", NHL,
         "NOT_COMPUTABLE", "hk.goal_order"),
        ("Wyścig do X goli (z dogrywką i rzutami karnymi)", "hockey", NHL, "NOT_COMPUTABLE", "hk.goal_order"),
        ("Liczba goli (z dogrywką i rzutami karnymi)", "hockey", NHL, "COMPUTABLE", "hk.ot_so_scope"),
        ("Detroit Red Wings - liczba goli (z dogrywką i rzutami karnymi)", "hockey", NHL,
         "COMPUTABLE", "hk.ot_so_scope"),
        ("Handicap (z dogrywką i rzutami karnymi)", "hockey", NHL, "COMPUTABLE", "hk.ot_so_scope"),
        ("2. połowa - podwójna szansa", "basketball", BASKET, "COMPUTABLE", "bb.double_chance"),
        ("Wyścig do X punktów (z dogrywką)", "basketball", BASKET, "NOT_COMPUTABLE", "bb.score_order"),
        ("Punkty zawodnika (z dogrywką)", "basketball", BASKET, "MAPPABLE", "bb.player_milestone"),
        ("Trafione rzuty za 3pkt zawodnika (z dogrywką)", "basketball", BASKET, "MAPPABLE",
         "bb.player_milestone"),
        ("Punkty + zbiórki + asysty zawodnika (z dogrywką)", "basketball", BASKET, "MAPPABLE",
         "bb.player_milestone"),
        ("Zawodnik - double double (z dogrywką)", "basketball", BASKET, "COMPUTABLE", "bb.double_double"),
        ("Fenerbahce - liczba asyst (z dogrywką)", "basketball", BASKET, "COMPUTABLE", "bb.team_box"),
        ("Liczba trafionych rzutów za 3pkt (z dogrywką)", "basketball", BASKET, "COMPUTABLE", "bb.team_box"),
        ("Najwięcej zbiórek (z dogrywką)", "basketball", BASKET, "COMPUTABLE", "bb.team_box"),
        ("Dokładna liczba setów", "volleyball", VOLLEY, "MAPPABLE", "vb.sets_count"),
        ("Czy będzie 5. set?", "volleyball", VOLLEY, "MAPPABLE", "vb.exact_sets_derived"),
        ("Vilsbiburg (K) wygra seta", "volleyball", VOLLEY, "MAPPABLE", "vb.exact_sets_derived"),
        ("Suhl Thuringen (K) wygra dokładnie 2 sety", "volleyball", VOLLEY, "MAPPABLE",
         "vb.exact_sets_derived"),
        ("1.Set/Mecz", "volleyball", VOLLEY, "COMPUTABLE", "vb.set_and_match"),
        ("1. set - handicap punkty", "volleyball", VOLLEY, "COMPUTABLE", "vb.set_points_handicap"),
        ("Drużyna - najwięcej wygranych rund w meczu (z dogrywką)", "cs2", CS2, "COMPUTABLE",
         "cs2.series_rounds"),
        ("Nieparzysta/parzysta liczba rund (z dogrywką)", "cs2", CS2, "COMPUTABLE", "cs2.round_parity"),
        ("Liczba dogrywek", "cs2", CS2, "COMPUTABLE", "cs2.overtimes"),
        ("1.mapa -  liczba zabójstw (z dogrywką)", "cs2", CS2, "COMPUTABLE", "cs2.map_kills_total"),
        ("2.mapa - Zwycięzca i liczba rund (z dogrywką)", "cs2", CS2, "COMPUTABLE", "cs2.map_winner_rounds"),
        ("3.mapa - Dokładny wynik", "cs2", CS2, "COMPUTABLE", "cs2.map_exact"),
        ("X.mapa - Zwycięzca 3-drogowo", "cs2", CS2, "COMPUTABLE", "cs2.map_winner_3way"),
        # Superbet's own combinations: COMPUTABLE by their parts (a joint).
        ("100 Thieves wygra 1. mapę; 0SAMAS powyżej 14.5 zabójstw na 1. mapie; m1N1 powyżej 15.5 zabójstw na 1. mapie",
         "cs2", CS2, "COMPUTABLE", "superbet_combo"),
        ("Bibu powyżej 7.5 headshotów na 1. mapie; 0SAMAS powyżej 7.5 headshotów na 1. mapie",
         "cs2", CS2, "COMPUTABLE", "superbet_combo"),
    ],
)
def test_every_unread_sport_name_has_one_label(
    name: str, sport: str, sides: list[str], label: str, family: str
) -> None:
    c = classify_sport_market_name(name, sport, sides)
    assert (c.label, c.family) == (label, family)


def test_a_combination_with_an_unknown_part_is_unclassified_never_guessed() -> None:
    c = classify_sport_market_name("100 Thieves wygra 1. mapę; coś zupełnie nowego", "cs2", CS2)
    assert c.label == "UNCLASSIFIED"
    assert classify_sport_market_name("Nowy rynek", "hockey", HOCKEY).label == "UNCLASSIFIED"


def test_every_sport_rule_carries_one_of_the_three_labels() -> None:
    for sport in ("hockey", "basketball", "volleyball", "cs2"):
        for rule in _RULES_BY_SPORT[sport]:
            assert rule.label in LABELS[:3]


def _payload(match: str, sport_id: int, odds: list[dict[str, Any]]) -> dict[str, Any]:
    return {"eventId": "1", "sportId": sport_id, "matchName": match, "odds": odds}


def test_shadow_reads_by_market_id_and_the_rest_is_unread() -> None:
    payload = _payload("KooKoo Kouvola·Mannheim", 3, [
        {"marketName": "Liczba goli", "name": "powyżej 4.5", "specialBetValue": "4.5",
         "price": 1.9, "marketId": 623, "status": "active"},
        # A suspended market SHADOW reads is still read.
        {"marketName": "Liczba goli", "name": "poniżej 4.5", "specialBetValue": "4.5",
         "price": 1.9, "marketId": 623, "status": "block"},
        {"marketName": "Podwójna szansa", "name": "1X", "price": 1.2, "marketId": 606,
         "status": "active"},
    ])
    sides, read, unread = sport_payload_names(payload, "hockey")
    assert sides == ("KooKoo Kouvola", "Mannheim")
    assert (read, unread) == (["Liczba goli"], ["Podwójna szansa"])


def test_cs2_reads_by_name_and_selection() -> None:
    payload = _payload("100 Thieves·JiJieHao", 55, [
        {"marketName": "Zwycięzca (z dogrywką)", "name": "100 Thieves", "price": 1.4,
         "status": "active"},
        {"marketName": "Zwycięzca (z dogrywką)", "name": "JiJieHao", "price": 2.8,
         "status": "active"},
        {"marketName": "Liczba dogrywek", "name": "Poniżej 0.5", "specialBetValue": "0.5",
         "price": 1.2, "status": "active"},
    ])
    _, read, unread = sport_payload_names(payload, "cs2")
    assert (read, unread) == (["Zwycięzca (z dogrywką)"], ["Liczba dogrywek"])


def test_snapshot_inventory_reads_each_events_last_snapshot() -> None:
    records = [
        {"superbet_event_id": "1", "fetched_at_utc": "2026-10-12T08:00:00Z",
         "lines": [{"family": "total"}, {"family": "total"}, {"family": "winner"}]},
        {"superbet_event_id": "1", "fetched_at_utc": "2026-10-12T10:00:00Z",
         "lines": [{"family": "total"}]},
        {"superbet_event_id": "2", "fetched_at_utc": "2026-10-12T09:00:00Z",
         "lines": [{"family": "handicap"}]},
    ]
    assert snapshot_inventory(records) == {
        "events": 2, "lines": 2, "by_family": {"total": 1, "handicap": 1}}


def test_report_counts_every_unread_name_once() -> None:
    events = [
        {"sport": "hockey", "team1": "KooKoo Kouvola", "team2": "Mannheim",
         "read": ["Liczba goli"], "unread": ["Podwójna szansa", "1. gol"]},
        {"sport": "volleyball", "team1": VOLLEY[0], "team2": VOLLEY[1],
         "read": [], "unread": ["Dokładna liczba setów", "Nowy rynek"]},
    ]
    report = build_sports_report(events, date="2026-10-13")
    assert report["unread_names"] == {"hockey": 2, "volleyball": 2}
    assert report["read_names"] == {"hockey": 1, "volleyball": 0}
    assert sum(v["occurrences"] for v in report["by_label"].values()) == 4
    assert report["by_sport_label"]["hockey"] == {"COMPUTABLE": 1, "NOT_COMPUTABLE": 1}
    assert report["unclassified"] == [
        {"sport": "volleyball", "template": "nowy rynek", "occurrences": 1}]


def test_script_reads_saved_payloads_and_writes_only_its_report(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    day = runs / "2026-10-13"
    day.mkdir(parents=True)
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "ev.json").write_text(json.dumps(_payload("KooKoo Kouvola·Mannheim", 3, [
        {"marketName": "Liczba goli", "name": "powyżej 4.5", "specialBetValue": "4.5",
         "price": 1.9, "marketId": 623, "status": "active"},
        {"marketName": "Podwójna szansa", "name": "1X", "price": 1.2, "marketId": 606,
         "status": "active"},
    ])), encoding="utf-8")
    # A football payload is not a measured sport: skipped.
    (raw / "fb.json").write_text(json.dumps(_payload("A·B", 5, [])), encoding="utf-8")
    snap = runs / "shadow" / "hockey" / "2026-10-13"
    snap.mkdir(parents=True)
    (snap / "snapshots.jsonl").write_text(json.dumps(
        {"superbet_event_id": "1", "fetched_at_utc": "x", "lines": [{"family": "total"}]}) + "\n",
        encoding="utf-8")
    out = tmp_path / "out"

    rc = main(["--date", "2026-10-13", "--runs-dir", str(runs), "--sports-only",
               "--sports-raw-dir", str(raw), "--sports-out-dir", str(out)])
    assert rc == 0
    report = json.loads((out / "market_coverage_sports.json").read_text(encoding="utf-8"))
    assert report["probed_events"] == {"hockey": 1}
    assert report["snapshots"]["hockey"]["lines"] == 1
    assert (out / "market_coverage_sports.md").exists()
    # Report only: nothing written into the day, nothing the pipeline reads.
    assert list(day.iterdir()) == []
