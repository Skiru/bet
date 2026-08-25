"""Tests for bet.simple_stats.analyze: hit-rate STATS_SHEET_V1 rows."""
from bet.stats.market_ranking import STANDARD_MARKET_LINES

from bet.simple_stats.analyze import (
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
