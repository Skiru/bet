"""Tests for bet.simple_stats.analyze: hit-rate STATS_SHEET_V1 rows."""
from bet.stats.market_ranking import STANDARD_MARKET_LINES

from bet.simple_stats.analyze import (
    _all_values,
    _cross_provider_agreement,
    analyze_dossier,
    compute_hit_rate,
)
from bet.simple_stats.contracts import EventDossierV1, MetricObservation, ProviderValue


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
    assert _cross_provider_agreement("corners_total", observations) == "AGREE"


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
    assert _cross_provider_agreement("corners_total", values) == "AGREE"


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
    assert round(solo_row.p_low, 3) == 0.409  # not 0.505


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


def test_two_real_matches_on_one_day_are_still_two_matches():
    """A provider reporting two distinct match_ids on the same day saw two
    matches; the collapse must not read its own account of them as one."""
    observations = [
        _pv("bzzoiro", 12.0, "2026-02-01", opponent="Real Betis", match_id="bz1"),
        _pv("bzzoiro", 11.0, "2026-02-01", opponent="Sevilla", match_id="bz2"),
    ]
    row = _corners_row(_corners_dossier(observations))
    assert row.sample_size == 2


def test_undated_observations_are_not_collapsed():
    """No usable date is no proof of which match an observation belongs to, so
    it stands alone -- the same reading the agreement check takes."""
    observations = [
        _pv("bzzoiro", 12.0, "", opponent="Real Betis", match_id=f"bz{i}") for i in range(4)
    ]
    row = _corners_row(_corners_dossier(observations))
    assert row.sample_size == 4
