"""Tests for bet.simple_stats.analyze: hit-rate STATS_SHEET_V1 rows."""
from bet.stats.market_ranking import STANDARD_MARKET_LINES

from bet.simple_stats.analyze import (
    _all_values,
    _cross_provider_agreement,
    analyze_dossier,
    compute_hit_rate,
    corroborated_matches,
    count_model_bound,
    limit_rows_per_event,
    wilson_lower_bound,
)
from bet.simple_stats.contracts import EventDossierV1, MetricObservation, ProviderValue, StatsSheetRow


def _pv(provider, value, match_date, opponent="Opponent FC", match_id="m"):
    return ProviderValue(
        provider=provider,
        match_id=match_id,
        match_date=match_date,
        opponent=opponent,
        value=value,
        observed_at="2026-01-01T00:00:00+00:00",
    )


def test_hit_rate_not_replaced_by_mean():
    # One outlier drags the mean above the line even though only 1 of 5
    # matches actually cleared it -- hit_rate must reflect that, not the mean.
    values = [2.0, 3.0, 4.0, 4.0, 35.0]
    mean = sum(values) / len(values)
    assert mean > 9.5

    hits, total, pushes = compute_hit_rate(values, 9.5, "OVER")
    assert (hits, total, pushes) == (1, 5, 0)
    assert hits / total == 0.2


def test_all_standard_lines_tested():
    values = [8.0, 9.0, 10.0, 11.0, 12.0, 9.0, 10.0, 8.0]
    obs = MetricObservation(
        canonical_name="corners_total",
        team_a_l10=[_pv("espn-football", v, f"2026-01-{i + 1:02d}", match_id=f"a{i}") for i, v in enumerate(values)],
    )
    dossier = EventDossierV1(
        event_id="evt1",
        sport="football",
        metrics={"corners_total": obs},
        readiness="READY",
        data_gaps=[],
    )

    rows = analyze_dossier(dossier)
    corners_market = next(m for m in STANDARD_MARKET_LINES["football"] if m["market"] == "Corners Total")

    seen = {(r.line, r.direction) for r in rows if r.market == "corners_total"}
    for line in corners_market["lines"]:
        assert (line, "OVER") in seen
        assert (line, "UNDER") in seen


def test_goals_total_rows_cover_every_standard_line():
    """docs/PLAN_BOGATE_STATYSTYKI.md Faza 1: goals_total is a match-total
    metric exactly like corners_total, so it must produce a row on every line
    STANDARD_MARKET_LINES prices for it -- 0.5 and 4.5 included, the two
    lines this family did not have before Faza 1 extended the grid."""
    values = [0.0, 1.0, 2.0, 2.0, 3.0, 3.0, 4.0, 5.0]
    obs = MetricObservation(
        canonical_name="goals_total",
        team_a_l10=[_pv("bzzoiro", v, f"2026-01-{i + 1:02d}", match_id=f"g{i}") for i, v in enumerate(values)],
    )
    dossier = EventDossierV1(
        event_id="evt-goals", sport="football", metrics={"goals_total": obs},
        readiness="READY", data_gaps=[],
    )

    rows = analyze_dossier(dossier)
    goals_market = next(m for m in STANDARD_MARKET_LINES["football"] if m["market"] == "Goals Total")
    assert goals_market["lines"] == [0.5, 1.5, 2.5, 3.5, 4.5]

    seen = {(r.line, r.direction) for r in rows if r.market == "goals_total"}
    for line in goals_market["lines"]:
        assert (line, "OVER") in seen
        assert (line, "UNDER") in seen


def test_half_goals_rows_are_their_own_match_total_markets():
    """docs/PLAN_BOGATE_STATYSTYKI.md Faza 3: goals_1h_total/goals_2h_total
    are ordinary match-total metrics once collected, exactly like
    goals_total -- ANALYZE needs no special case for them."""
    values = [0.0, 0.0, 1.0, 1.0, 2.0]
    obs = MetricObservation(
        canonical_name="goals_2h_total",
        team_a_l10=[_pv("bzzoiro", v, f"2026-01-{i + 1:02d}", match_id=f"h{i}") for i, v in enumerate(values)],
    )
    dossier = EventDossierV1(
        event_id="evt-half-goals", sport="football", metrics={"goals_2h_total": obs},
        readiness="READY", data_gaps=[],
    )

    rows = analyze_dossier(dossier)
    market = next(m for m in STANDARD_MARKET_LINES["football"] if m["market"] == "Goals 2H Total")
    assert market["lines"] == [0.5]

    over_05 = next(r for r in rows if r.market == "goals_2h_total" and r.line == 0.5 and r.direction == "OVER")
    assert (over_05.hits, over_05.sample_size) == (3, 5)
    assert not [r for r in rows if r.market == "goals_1h_total"]


def test_team_goals_rows_are_two_separate_samples_per_side():
    """Team Goals reads goals_for exactly the way Team Corners reads
    corners_for: two independent per-team samples, told apart by team_name,
    never pooled into one match-level number."""
    team_a_values = [1.0, 1.0, 2.0, 0.0, 3.0]
    team_b_values = [0.0, 0.0, 1.0, 1.0, 2.0]
    obs = MetricObservation(
        canonical_name="goals_for",
        team_a_l10=[_pv("bzzoiro", v, f"2026-02-{i + 1:02d}", match_id=f"a{i}") for i, v in enumerate(team_a_values)],
        team_b_l10=[_pv("bzzoiro", v, f"2026-03-{i + 1:02d}", match_id=f"b{i}") for i, v in enumerate(team_b_values)],
    )
    dossier = EventDossierV1(
        event_id="evt-team-goals", sport="football", metrics={"goals_for": obs},
        team_a_name="Team A", team_b_name="Team B",
        readiness="READY", data_gaps=[],
    )

    rows = analyze_dossier(dossier)
    team_goals_rows = [r for r in rows if r.market == "goals_for"]
    assert team_goals_rows
    assert {r.team_name for r in team_goals_rows} == {"Team A", "Team B"}
    over_05_a = next(r for r in team_goals_rows if r.team_name == "Team A" and r.line == 0.5 and r.direction == "OVER")
    assert over_05_a.sample_size == 5
    assert over_05_a.hits == 4  # everything but the 0.0


def test_shots_total_rows_cover_every_standard_line():
    """docs/PLAN_BOGATE_STATYSTYKI.md Faza 2: shots_total was already collected
    (PRIORITY_METRICS) and priced per-team as Team Shots, but had no
    match-total market -- Superbet's own screenshots showed one."""
    values = [18.0, 20.0, 22.0, 24.0, 26.0, 28.0, 30.0, 21.0]
    obs = MetricObservation(
        canonical_name="shots_total",
        team_a_l10=[_pv("bzzoiro", v, f"2026-01-{i + 1:02d}", match_id=f"s{i}") for i, v in enumerate(values)],
    )
    dossier = EventDossierV1(
        event_id="evt-shots", sport="football", metrics={"shots_total": obs},
        readiness="READY", data_gaps=[],
    )

    rows = analyze_dossier(dossier)
    shots_market = next(m for m in STANDARD_MARKET_LINES["football"] if m["market"] == "Shots Total")
    assert shots_market["lines"] == [19.5, 22.5, 25.5, 28.5]

    seen = {(r.line, r.direction) for r in rows if r.market == "shots_total"}
    for line in shots_market["lines"]:
        assert (line, "OVER") in seen
        assert (line, "UNDER") in seen


def test_offsides_and_red_cards_rows_are_priced():
    """Faza 2: offsides_total and red_cards_total were collected (highlightly,
    bzzoiro) but never had a STANDARD_MARKET_LINES entry, so no row was ever
    emitted for either. Both are match totals like corners_total."""
    offsides_values = [1.0, 2.0, 3.0, 2.0, 4.0, 1.0]
    red_card_values = [0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
    offsides_obs = MetricObservation(
        canonical_name="offsides_total",
        team_a_l10=[_pv("highlightly", v, f"2026-01-{i + 1:02d}", match_id=f"o{i}") for i, v in enumerate(offsides_values)],
    )
    red_cards_obs = MetricObservation(
        canonical_name="red_cards_total",
        team_a_l10=[_pv("bzzoiro", v, f"2026-01-{i + 1:02d}", match_id=f"r{i}") for i, v in enumerate(red_card_values)],
    )
    dossier = EventDossierV1(
        event_id="evt-offsides-reds",
        sport="football",
        metrics={"offsides_total": offsides_obs, "red_cards_total": red_cards_obs},
        readiness="READY", data_gaps=[],
    )

    rows = analyze_dossier(dossier)

    offsides_market = next(m for m in STANDARD_MARKET_LINES["football"] if m["market"] == "Total Offsides")
    seen_offsides = {(r.line, r.direction) for r in rows if r.market == "offsides_total"}
    for line in offsides_market["lines"]:
        assert (line, "OVER") in seen_offsides
        assert (line, "UNDER") in seen_offsides

    red_cards_market = next(m for m in STANDARD_MARKET_LINES["football"] if m["market"] == "Total Red Cards")
    assert red_cards_market["lines"] == [0.5]
    red_card_row = next(r for r in rows if r.market == "red_cards_total" and r.direction == "UNDER")
    assert red_card_row.hits == 5  # everything but the one red card


def test_team_offsides_rows_are_two_separate_samples_per_side():
    """Team Offsides reads offsides_for the way Team Corners reads
    corners_for -- bzzoiro's /events/{id}/stats/ already carries the
    home/away split that offsides_total is summed from."""
    team_a_values = [1.0, 2.0, 1.0, 3.0, 0.0]
    team_b_values = [2.0, 1.0, 2.0, 1.0, 3.0]
    obs = MetricObservation(
        canonical_name="offsides_for",
        team_a_l10=[_pv("bzzoiro", v, f"2026-02-{i + 1:02d}", match_id=f"a{i}") for i, v in enumerate(team_a_values)],
        team_b_l10=[_pv("bzzoiro", v, f"2026-03-{i + 1:02d}", match_id=f"b{i}") for i, v in enumerate(team_b_values)],
    )
    dossier = EventDossierV1(
        event_id="evt-team-offsides", sport="football", metrics={"offsides_for": obs},
        team_a_name="Team A", team_b_name="Team B",
        readiness="READY", data_gaps=[],
    )

    rows = analyze_dossier(dossier)
    team_offsides_rows = [r for r in rows if r.market == "offsides_for"]
    assert team_offsides_rows
    assert {r.team_name for r in team_offsides_rows} == {"Team A", "Team B"}


def test_blocked_dossier_never_reaches_analyze():
    dossier = EventDossierV1(event_id="evt2", sport="football", metrics={}, readiness="BLOCKED", data_gaps=["x"])
    assert analyze_dossier(dossier) == []


def test_sample_size_zero_rows_are_not_emitted():
    dossier = EventDossierV1(
        event_id="evt3",
        sport="tennis",
        metrics={},  # no observations at all for any tennis market
        readiness="PARTIAL",
        data_gaps=["no data"],
    )
    assert analyze_dossier(dossier) == []


def test_agreement_survives_differing_opponent_spellings():
    """Providers spell the same opponent differently ("Ulsan Hyundai FC" vs
    "Ulsan HD") and stamp dates in different formats. Keying agreement on the
    raw opponent string made every cross-provider pair read as SINGLE_SOURCE,
    silently disabling the check the pipeline exists to surface.
    """
    observations = [
        ProviderValue(
            provider="sportdb", match_id="a", match_date="2026-07-26T10:30:00.000Z",
            opponent="Ulsan HD", value=9.0, observed_at="2026-08-25T00:00:00+00:00",
        ),
        ProviderValue(
            provider="api-football", match_id="b", match_date="2026-07-26T05:00:00+00:00",
            opponent="Ulsan Hyundai FC", value=9.0, observed_at="2026-08-25T00:00:00+00:00",
        ),
    ]
    # The mechanism under test is the clustering, so it is asserted directly:
    # these two rows are one corroborated match, not two single-source ones.
    # ``_cross_provider_agreement`` needs MIN_CORROBORATED_MATCHES of them
    # before it will say AGREE, and that threshold is a separate claim tested
    # in test_regression_2026_09_01_losses.py -- asserting it here would make
    # this test fail for a reason that has nothing to do with spelling.
    assert corroborated_matches("corners_total", observations) == 1


def test_same_day_different_matches_are_not_conflated():
    """Two teams both played on the same day against different opponents;
    that is not corroboration of one match."""
    observations = [
        ProviderValue(
            provider="sportdb", match_id="a", match_date="2026-07-26T10:30:00.000Z",
            opponent="Ulsan HD", value=9.0, observed_at="2026-08-25T00:00:00+00:00",
        ),
        ProviderValue(
            provider="api-football", match_id="b", match_date="2026-07-26T05:00:00+00:00",
            opponent="Daejeon", value=3.0, observed_at="2026-08-25T00:00:00+00:00",
        ),
    ]
    assert _cross_provider_agreement("corners_total", observations) == "SINGLE_SOURCE"


def test_disagreement_detected_across_spellings():
    observations = [
        ProviderValue(
            provider="sportdb", match_id="a", match_date="2026-07-26T10:30:00.000Z",
            opponent="Ulsan HD", value=9.0, observed_at="2026-08-25T00:00:00+00:00",
        ),
        ProviderValue(
            provider="api-football", match_id="b", match_date="2026-07-26T05:00:00+00:00",
            opponent="Ulsan Hyundai FC", value=15.0, observed_at="2026-08-25T00:00:00+00:00",
        ),
    ]
    assert _cross_provider_agreement("corners_total", observations) == "DISAGREE"


# --- The ANALYZE script's tipster-signal guards -------------------------------
#
# Attaching a signal from another day would label yesterday's opinions as
# today's -- silently, and looking exactly like a correct column. These run the
# script, because the guards live in its argument handling, not in analyze.py.


def _minimal_artifacts(tmp_path, *, signal_date: str):
    import json

    dossier = {
        "run_id": "RID-1",
        "date": "2026-08-25",
        "generated_at": "2026-08-25T09:00:00Z",
        "dossiers": [
            {
                "event_id": "EV1",
                "sport": "football",
                "readiness": "PARTIAL",
                "data_gaps": [],
                "metrics": {
                    "corners_total": {
                        "canonical_name": "corners_total",
                        "team_a_l10": [
                            {
                                "provider": "espn-football",
                                "match_id": f"m{i}",
                                "match_date": f"2026-08-0{i+1}",
                                "opponent": f"Opp{i}",
                                "value": 9.0 + i,
                                "observed_at": "2026-08-25T09:00:00Z",
                            }
                            for i in range(6)
                        ],
                        "team_b_l10": [],
                        "h2h": [],
                    }
                },
            }
        ],
    }
    signal = {
        "run_id": "RID-1",
        "date": signal_date,
        "generated_at": "2026-08-25T10:00:00Z",
        "sources_attempted": ["zawodtyper"],
        "sources_with_picks": ["zawodtyper"],
        "picks_ingested": 1,
        "picks_matched": 1,
        "picks_unmatched": 0,
        "countable_claims": 1,
        "events": [
            {
                "event_id": "EV1",
                "home_team": "A",
                "away_team": "B",
                "match_quality": "EXACT",
                "match_score": 100,
                "picks": [
                    {
                        "source_id": "zawodtyper",
                        "source_name": "ZawodTyper",
                        "tipster_name": "AnalystA",
                        "claim": "Poniżej 10,5 rzutów rożnych",
                        "market": "corners_total",
                        "line": 10.5,
                        "direction": "UNDER",
                        "countable": True,
                    }
                ],
                "public_lean": {},
            }
        ],
    }
    dossier_path = tmp_path / "2026-08-25_event_dossiers.json"
    signal_path = tmp_path / "signal.json"
    dossier_path.write_text(json.dumps(dossier), encoding="utf-8")
    signal_path.write_text(json.dumps(signal), encoding="utf-8")
    return dossier_path, signal_path


def _run_analyze(tmp_path, dossier_path, *extra):
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "simple" / "run_analyze.py"),
            "--dossier", str(dossier_path),
            "--output-dir", str(tmp_path),
            "--db-path", str(tmp_path / "x.sqlite"),
            *extra,
        ],
        capture_output=True, text=True, cwd=root,
    )
    import json as _json

    summary = {}
    for line in proc.stdout.splitlines():
        if line.startswith("AGENT_SUMMARY:"):
            summary = _json.loads(line[len("AGENT_SUMMARY:"):])
    return summary


def test_a_matching_signal_populates_the_column(tmp_path):
    dossier_path, signal_path = _minimal_artifacts(tmp_path, signal_date="2026-08-25")
    summary = _run_analyze(tmp_path, dossier_path, "--tipster-signal", str(signal_path))
    assert summary["metrics"]["tipster_rows_with_opinion"] >= 1
    assert summary["metrics"]["tipster_countable_claims"] == 1

    import json

    sheet = json.loads((tmp_path / "2026-08-25_event_dossiers_stats_sheet.json").read_text())
    matching = [
        r for r in sheet["rows"]
        if r["market"] == "corners_total" and r["line"] == 10.5 and r["direction"] == "UNDER"
    ]
    assert matching and matching[0]["tipster"]["verdict"] == "CONFIRMS"


def test_a_signal_for_another_day_is_refused(tmp_path):
    dossier_path, signal_path = _minimal_artifacts(tmp_path, signal_date="2026-08-24")
    summary = _run_analyze(tmp_path, dossier_path, "--tipster-signal", str(signal_path))
    assert summary["metrics"]["tipster_signal_error"].startswith("date_mismatch")
    assert summary["metrics"]["tipster_signal"] is None

    import json

    sheet = json.loads((tmp_path / "2026-08-25_event_dossiers_stats_sheet.json").read_text())
    assert all(r["tipster"] is None for r in sheet["rows"])


def test_a_missing_signal_file_is_a_warning_not_a_crash(tmp_path):
    dossier_path, _ = _minimal_artifacts(tmp_path, signal_date="2026-08-25")
    summary = _run_analyze(tmp_path, dossier_path, "--tipster-signal", str(tmp_path / "gone.json"))
    assert summary["verdict"] in ("OK", "PARTIAL")
    assert "tipster_signal_error" in summary["metrics"]


def test_the_sheet_is_unchanged_when_no_signal_is_passed(tmp_path):
    import json

    dossier_path, signal_path = _minimal_artifacts(tmp_path, signal_date="2026-08-25")
    without = _run_analyze(tmp_path, dossier_path)
    sheet_without = json.loads((tmp_path / "2026-08-25_event_dossiers_stats_sheet.json").read_text())

    with_signal = _run_analyze(tmp_path, dossier_path, "--tipster-signal", str(signal_path))
    sheet_with = json.loads((tmp_path / "2026-08-25_event_dossiers_stats_sheet.json").read_text())

    assert without["metrics"]["total_rows"] == with_signal["metrics"]["total_rows"]
    # Every field except the column itself is identical.
    for a, b in zip(sheet_without["rows"], sheet_with["rows"]):
        assert {k: v for k, v in a.items() if k != "tipster"} == {
            k: v for k, v in b.items() if k != "tipster"
        }
        assert a["tipster"] is None


def test_one_match_counts_once_across_overlapping_buckets():
    """A league fixture the two sides already played this season sits in
    team_a's last-10, team_b's last-10 and h2h. Counted once per bucket it
    tripled sample_size, and sample_size is what _confidence reads."""
    def pv(match_id, value, provider="sportdb"):
        return ProviderValue(
            provider=provider, match_id=match_id, match_date="2026-02-01",
            opponent="Real Betis", value=value,
            observed_at="2026-02-01T00:00:00+00:00",
        )

    obs = MetricObservation(
        canonical_name="corners_total",
        team_a_l10=[pv("A1", 8.0), pv("H2H1", 12.0)],
        team_b_l10=[pv("B1", 7.0), pv("H2H1", 12.0)],
        h2h=[pv("H2H1", 12.0)],
    )

    values = _all_values(obs)
    assert [v.match_id for v in values] == ["A1", "H2H1", "B1"]
    assert sum(1 for v in values if v.match_id == "H2H1") == 1


def test_two_providers_on_the_same_match_both_survive_dedup():
    """Cross-provider corroboration is the point of the pipeline; dedup keys on
    (provider, match_id) precisely so it is not destroyed."""
    def pv(provider, value):
        return ProviderValue(
            provider=provider, match_id="M1", match_date="2026-02-01",
            opponent="Real Betis", value=value,
            observed_at="2026-02-01T00:00:00+00:00",
        )

    obs = MetricObservation(
        canonical_name="corners_total",
        team_a_l10=[pv("sportdb", 9.0)],
        team_b_l10=[pv("espn-football", 9.0)],
        h2h=[],
    )
    values = _all_values(obs)
    assert {v.provider for v in values} == {"sportdb", "espn-football"}
    # The claim is that dedup did not throw one of the two providers away, so
    # it is asserted on the corroboration count rather than on the AGREE
    # verdict: one corroborated match is below MIN_CORROBORATED_MATCHES, and
    # that threshold is a different claim from this one.
    assert corroborated_matches("corners_total", values) == 1


def test_observations_without_a_match_id_are_never_collapsed():
    """No id means no proof they are the same match, so all of them are kept."""
    def pv(value):
        return ProviderValue(
            provider="api-football", match_id="", match_date="2026-02-01",
            opponent="Real Betis", value=value,
            observed_at="2026-02-01T00:00:00+00:00",
        )

    obs = MetricObservation(
        canonical_name="corners_total",
        team_a_l10=[pv(8.0), pv(8.0)], team_b_l10=[pv(8.0)], h2h=[],
    )
    assert len(_all_values(obs)) == 3


# --- Corroboration is not a second trial -------------------------------------
#
# _all_values keeps two providers on one match, on purpose: that is the
# corroboration _cross_provider_agreement checks. Everything past that check
# reads one value per match, because sample_size feeds wilson_lower_bound and a
# duplicate there buys confidence no extra match earned.


def _corners_dossier(observations, event_id="evt-indep"):
    return EventDossierV1(
        event_id=event_id,
        sport="football",
        metrics={
            "corners_total": MetricObservation(
                canonical_name="corners_total", team_a_l10=list(observations)
            )
        },
        team_a_name="Team A",
        team_b_name="Team B",
        readiness="READY",
        data_gaps=[],
    )


def _corners_row(dossier, line=9.5, direction="OVER"):
    return next(
        r
        for r in analyze_dossier(dossier)
        if r.market == "corners_total" and r.line == line and r.direction == direction
    )


def test_corroborated_match_is_one_trial_not_two():
    """The inflation this split exists to remove.

    Eight matches, six over 9.5. Reported by one provider that is 6/8 and
    p_low 0.409; reported by two it was read as 12/16 and p_low 0.505 -- the
    same evidence, +9.6pp of "Pewnosc", and p_low is the sort key of the whole
    coupons file.

    Note the two providers stamp *different* match_ids for the same match, as
    they do in production: each stamps its own native id, so match_id alone
    would collapse nothing here.
    """
    values = [12.0, 11.0, 10.0, 10.0, 11.0, 10.0, 8.0, 7.0]  # 6 over 9.5
    solo = [
        _pv("bzzoiro", v, f"2026-02-{i + 1:02d}", opponent=f"Opp {i}", match_id=f"bz{i}")
        for i, v in enumerate(values)
    ]
    corroborated = solo + [
        _pv("espn-football", v, f"2026-02-{i + 1:02d}", opponent=f"Opp {i}", match_id=f"es{i}")
        for i, v in enumerate(values)
    ]

    solo_row = _corners_row(_corners_dossier(solo))
    both_row = _corners_row(_corners_dossier(corroborated))

    assert (solo_row.hits, solo_row.sample_size) == (6, 8)
    assert (both_row.hits, both_row.sample_size) == (6, 8)
    assert both_row.p_low == solo_row.p_low
    # The claim is about the *trial count*, so it is asserted on the instrument
    # that reads trial counts. Sixteen trials would have bought 0.505 here and
    # eight buy 0.409, and the dedup is what keeps it at eight.
    assert round(wilson_lower_bound(6, 8), 3) == 0.409
    assert round(wilson_lower_bound(12, 16), 3) == 0.505
    # The row itself lands lower than either, because ``p_low`` is also capped
    # by how close 9.5 sits to this sample -- mean 9.875, barely a third of a
    # corner clear of the line. Both instruments are asserted rather than only
    # the smaller: a regression that dropped the Wilson half would otherwise
    # pass here unnoticed.
    assert round(solo_row.p_low, 3) == 0.283
    assert solo_row.p_low < wilson_lower_bound(6, 8)


def test_corroboration_still_reaches_the_agreement_check_and_sources():
    """Collapsing the statistical sample must not cost the pipeline the very
    signal the duplicates carry: two providers agreeing on a match."""
    observations = [
        _pv("bzzoiro", 11.0, "2026-02-01", opponent="Real Betis", match_id="bz1"),
        _pv("espn-football", 11.0, "01/02/2026", opponent="Betis", match_id="es1"),
        _pv("bzzoiro", 12.0, "2026-02-08", opponent="Sevilla", match_id="bz2"),
        _pv("espn-football", 12.0, "08/02/2026", opponent="Sevilla FC", match_id="es2"),
    ]
    row = _corners_row(_corners_dossier(observations))

    assert row.sample_size == 2  # two matches, not four observations
    assert row.cross_provider_agreement == "AGREE"
    assert row.sources == ["bzzoiro", "espn-football"]


def test_disagreeing_providers_contribute_one_reported_value():
    """When providers disagree the representative is one of the values they
    actually reported -- never their average, which would invent a figure no
    provider stands behind and could land a synthetic push on a whole line."""
    observations = [
        _pv("bzzoiro", 9.0, "2026-02-01", opponent="Real Betis", match_id="bz1"),
        _pv("espn-football", 10.0, "2026-02-01", opponent="Betis", match_id="es1"),
    ]
    row = _corners_row(_corners_dossier(observations))

    assert row.sample_size == 1
    assert row.mean in (9.0, 10.0)


def test_same_day_in_one_bucket_is_one_match_however_the_opponent_is_spelled():
    """The overstatement a name-based collapse could not see.

    A team plays at most one match per day, so two observations in the *same*
    bucket stamped the same day are the same match -- even though the fuzzy
    matcher rejects the pair (`_team_matches('milton keynes dons', 'mk dons')`
    is False, verified). Collapsing on names left this as two independent
    trials and inflated p_low; 72 such pairs were measured across the
    2026-08-25 and 2026-08-28 runs.
    """
    observations = [
        _pv("bzzoiro", 12.0, "2026-08-08", opponent="Milton Keynes Dons", match_id="bz1"),
        _pv("espn-football", 12.0, "2026-08-08", opponent="MK Dons", match_id="es1"),
    ]
    row = _corners_row(_corners_dossier(observations))
    assert row.sample_size == 1


def test_different_days_in_one_bucket_stay_separate_matches():
    """The day is the identity, so distinct days are distinct matches and the
    collapse must not reach across them."""
    observations = [
        _pv("bzzoiro", 12.0, "2026-02-01", opponent="Real Betis", match_id="bz1"),
        _pv("bzzoiro", 11.0, "2026-02-08", opponent="Sevilla", match_id="bz2"),
    ]
    row = _corners_row(_corners_dossier(observations))
    assert row.sample_size == 2


def test_head_to_head_fixture_counts_once_across_all_three_buckets():
    """The one match that legitimately sits in all three buckets.

    A and B played each other on 2026-02-01, so it is in A's last-10 (opponent
    "B"), B's last-10 (opponent "A") and h2h. `_one_per_day` works one bucket at
    a time and cannot see that, and the buckets name *different* opponents for
    it, so no opponent-name rule could either. Across providers the match_ids
    differ too, so without the head-to-head fold this one match would land three
    independent trials in the sample.
    """
    obs = MetricObservation(
        canonical_name="corners_total",
        team_a_l10=[
            _pv("bzzoiro", 12.0, "2026-02-01", opponent="Team B", match_id="bz-a"),
            _pv("espn-football", 12.0, "2026-02-01", opponent="Team B FC", match_id="es-a"),
        ],
        team_b_l10=[_pv("bzzoiro", 12.0, "2026-02-01", opponent="Team A", match_id="bz-b")],
        h2h=[_pv("espn-football", 12.0, "2026-02-01", opponent="Team A", match_id="es-h")],
    )
    dossier = EventDossierV1(
        event_id="evt-h2h",
        sport="football",
        metrics={"corners_total": obs},
        team_a_name="Team A",
        team_b_name="Team B",
        readiness="READY",
        data_gaps=[],
    )
    assert _corners_row(dossier).sample_size == 1


def test_undated_observations_are_not_collapsed():
    """No usable date is no proof of which match an observation belongs to, so
    it stands alone -- the same reading the agreement check takes."""
    observations = [
        _pv("bzzoiro", 12.0, "", opponent="Real Betis", match_id=f"bz{i}") for i in range(4)
    ]
    row = _corners_row(_corners_dossier(observations))
    assert row.sample_size == 4


def _row(event_id: str, p_low: float, market: str = "corners_total") -> StatsSheetRow:
    return StatsSheetRow(
        event_id=event_id, sport="football", market=market, line=9.5, direction="OVER",
        hits=8, sample_size=10, hit_rate=0.8, p_low=p_low, mean=10.0, median=10.0,
        cross_provider_agreement="AGREE", confidence="HIGH", data_quality="READY",
    )


def test_limit_rows_per_event_keeps_the_strongest_rows_seen_first():
    """docs/PLAN_BOGATE_STATYSTYKI.md Faza 2 sizing guard: rows arrive
    strongest-p_low-first (as analyze_dossiers leaves them), so capping per
    event must keep the first N seen for that event_id and drop the rest,
    regardless of any other event's rows interleaved between them."""
    rows = [
        _row("evt-a", 0.90), _row("evt-b", 0.85), _row("evt-a", 0.80),
        _row("evt-a", 0.70), _row("evt-b", 0.65), _row("evt-a", 0.60),
    ]
    kept = limit_rows_per_event(rows, max_per_event=2)
    assert [(r.event_id, r.p_low) for r in kept] == [
        ("evt-a", 0.90), ("evt-b", 0.85), ("evt-a", 0.80), ("evt-b", 0.65),
    ]


def test_limit_rows_per_event_unlimited_by_default():
    rows = [_row("evt-a", 0.90), _row("evt-a", 0.80), _row("evt-a", 0.70)]
    assert limit_rows_per_event(rows, max_per_event=None) == rows
