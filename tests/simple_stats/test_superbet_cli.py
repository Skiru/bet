"""CLI wiring for SUPERBET: run_superbet.py, run_analyze.py, build_coupons.py.

The library behaviour lives in test_superbet_offer.py and
test_coupons_superbet.py. What is tested here is the wiring, which is where a
column silently vanishes: a flag that is declared but never read, an artifact
written under a name the next step does not look for, or a date guard that
lets yesterday's prices onto today's sheet.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(script_name: str, module_name: str):
    path = ROOT / "scripts" / "simple" / script_name
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def superbet_module():
    return _load("run_superbet.py", "run_superbet_under_test")


@pytest.fixture(scope="module")
def coupons_module():
    return _load("build_coupons.py", "build_coupons_superbet_under_test")


@pytest.fixture(scope="module")
def analyze_module():
    return _load("run_analyze.py", "run_analyze_superbet_under_test")


def _run_main(module, monkeypatch, argv, script="script.py"):
    monkeypatch.setattr(sys, "argv", [script, *argv])
    try:
        module.main()
    except SystemExit as exc:
        return exc.code
    return 0


# --- artifacts -------------------------------------------------------------


EVENT_LIST = {
    "run_id": "RID-1", "generated_at": "2026-08-29T00:00:00+00:00",
    "date": "2026-08-29", "sports": ["football"],
    "events": [
        {
            "event_id": "evt-1", "sport": "football", "competition": "La Liga",
            "home_team": "Valencia", "away_team": "Real Betis",
            "start_time": "2026-08-29T19:00:00+00:00",
            "identity_confidence": "CONFIRMED", "status": "ACTIVE",
        }
    ],
}

SHEET = {
    "run_id": "RID-1", "date": "2026-08-29", "generated_at": "2026-08-29T00:00:00+00:00",
    "rows": [
        {
            "event_id": "evt-1", "sport": "football", "market": "corners_total",
            "line": 9.5, "direction": "UNDER", "hits": 9, "sample_size": 12,
            "hit_rate": 0.75, "p_low": 0.60, "mean": 9.1, "median": 9.0,
            "sources": ["bzzoiro"], "cross_provider_agreement": "AGREE",
            "confidence": "HIGH", "data_quality": "READY",
        }
    ],
}


def _offer_doc(date="2026-08-29", price=2.20, line=9.5):
    return {
        "run_id": "RID-1", "date": date, "generated_at": "2026-08-29T18:00:00+00:00",
        "events": [
            {
                "superbet_event_id": "900", "superbet_match_name": "Valencia·Real Betis",
                "sport": "football", "kickoff": "2026-08-29T19:00:00Z",
                "event_id": "evt-1", "match_quality": "EXACT",
                "lines": [
                    {
                        "market": "corners_total", "line": line, "direction": "UNDER",
                        "price": price, "status": "active",
                        "source_market_name": "Liczba rzutów rożnych",
                        "source_outcome_name": "poniżej 9.5",
                    }
                ],
            }
        ],
    }


def _write(path: Path, doc) -> Path:
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


# --- run_superbet.py -------------------------------------------------------


class _FakeClient:
    """Stands in for the live offer host. No network in any test here."""

    def __init__(self):
        self.request_count = 0

    def events_by_date(self, start, end, offer_state="prematch"):
        self.request_count += 1
        return [{
            "eventId": 900, "matchName": "Valencia·Real Betis",
            "utcDate": "2026-08-29T19:00:00Z", "sportId": 5, "marketCount": 120,
            "odds": [],
        }]

    def event_odds(self, event_id):
        self.request_count += 1
        return {
            "eventId": 900, "matchName": "Valencia·Real Betis",
            "utcDate": "2026-08-29T19:00:00Z", "sportId": 5, "marketCount": 120,
            "odds": [
                {"marketName": "Liczba rzutów rożnych", "name": "poniżej 9.5",
                 "price": 2.20, "status": "active"},
                {"marketName": "Liczba rzutów rożnych", "name": "powyżej 9.5",
                 "price": 1.70, "status": "active"},
            ],
        }


@pytest.fixture
def fake_client(monkeypatch):
    import bet.api_clients.superbet as superbet_client

    monkeypatch.setattr(superbet_client, "SuperbetClient", lambda *a, **k: _FakeClient())
    return superbet_client


def test_run_superbet_writes_the_offer_artifact(
    superbet_module, monkeypatch, tmp_path, fake_client
):
    event_list = _write(tmp_path / "el.json", EVENT_LIST)
    code = _run_main(
        superbet_module, monkeypatch,
        ["--event-list", str(event_list), "--output-dir", str(tmp_path), "--no-persist"],
    )
    assert code == 0
    offer = json.loads((tmp_path / "2026-08-29_superbet_offer.json").read_text())
    assert offer["events_matched"] == 1
    assert {line["market"] for line in offer["events"][0]["lines"]} == {"corners_total"}


def test_run_superbet_writes_the_comparison_when_given_a_sheet(
    superbet_module, monkeypatch, tmp_path, fake_client
):
    event_list = _write(tmp_path / "el.json", EVENT_LIST)
    sheet = _write(tmp_path / "sheet.json", SHEET)
    code = _run_main(
        superbet_module, monkeypatch,
        ["--event-list", str(event_list), "--output-dir", str(tmp_path),
         "--stats-sheet", str(sheet), "--no-persist"],
    )
    assert code == 0
    comparison = json.loads((tmp_path / "2026-08-29_superbet_comparison.json").read_text())
    assert comparison["verdict_counts"] == {"VALUE": 1}
    assert comparison["rows"][0]["superbet_price"] == 2.20


def test_run_superbet_without_a_sheet_writes_no_comparison(
    superbet_module, monkeypatch, tmp_path, fake_client
):
    event_list = _write(tmp_path / "el.json", EVENT_LIST)
    _run_main(
        superbet_module, monkeypatch,
        ["--event-list", str(event_list), "--output-dir", str(tmp_path), "--no-persist"],
    )
    assert not (tmp_path / "2026-08-29_superbet_comparison.json").exists()


def test_run_superbet_without_an_event_list_is_a_precondition_failure(
    superbet_module, monkeypatch, tmp_path
):
    code = _run_main(
        superbet_module, monkeypatch,
        ["--event-list", str(tmp_path / "missing.json"), "--output-dir", str(tmp_path),
         "--no-persist"],
    )
    assert code == 2


# --- run_analyze.py --------------------------------------------------------


def _values(prefix, samples):
    return [
        {
            "provider": "bzzoiro", "match_id": f"{prefix}{i}",
            "match_date": f"2026-07-{1 + i:02d}", "opponent": f"Opp {i}",
            "value": float(v), "observed_at": "2026-08-29T00:00:00+00:00",
        }
        for i, v in enumerate(samples)
    ]


DOSSIER = {
    "run_id": "RID-1", "date": "2026-08-29", "generated_at": "2026-08-29T00:00:00+00:00",
    "dossiers": [
        {
            "event_id": "evt-1", "sport": "football", "readiness": "READY",
            "team_a_name": "Valencia", "team_b_name": "Real Betis",
            "metrics": {
                "corners_total": {
                    "canonical_name": "corners_total",
                    "team_a_l10": _values("a", [8, 9, 7, 8, 10, 9, 8, 7, 9, 8]),
                    "team_b_l10": _values("b", [9, 8, 10, 7, 8, 9, 8, 9, 7, 8]),
                    "h2h": [],
                }
            },
            "data_gaps": [],
        }
    ],
}


def _write_dossier(path: Path) -> Path:
    return _write(path, DOSSIER)


def test_analyze_attaches_the_superbet_column(analyze_module, monkeypatch, tmp_path):
    dossier = _write_dossier(tmp_path / "2026-08-29_event_dossiers.json")
    offer = _write(tmp_path / "offer.json", _offer_doc())
    code = _run_main(
        analyze_module, monkeypatch,
        ["--dossier", str(dossier), "--output-dir", str(tmp_path),
         "--superbet-offer", str(offer), "--db-path", str(tmp_path / "t.db")],
    )
    # 1, not 0: this scratch DB has no tables and the single-source dossier
    # trips ANALYZE's own PARTIAL verdict. Neither is what this test is about.
    assert code in (0, 1)
    sheet = json.loads(
        (tmp_path / "2026-08-29_event_dossiers_stats_sheet.json").read_text()
    )
    columns = {row["superbet"]["availability"] for row in sheet["rows"]}
    assert "OFFERED" in columns
    priced = [r for r in sheet["rows"] if r["superbet"]["availability"] == "OFFERED"]
    assert priced[0]["superbet"]["price"] == 2.20
    assert priced[0]["superbet"]["superbet_event_id"] == "900"


def test_analyze_refuses_an_offer_from_another_day(analyze_module, monkeypatch, tmp_path):
    """Yesterday's prices on today's rows look exactly like today's prices.

    Same guard the market and tipster columns carry, and it bites harder here:
    a bookmaker re-ladders overnight, so a stale artifact can report a line as
    offered that no longer exists.
    """
    dossier = _write_dossier(tmp_path / "2026-08-29_event_dossiers.json")
    offer = _write(tmp_path / "offer.json", _offer_doc(date="2026-08-28"))
    _run_main(
        analyze_module, monkeypatch,
        ["--dossier", str(dossier), "--output-dir", str(tmp_path),
         "--superbet-offer", str(offer), "--db-path", str(tmp_path / "t.db")],
    )
    sheet = json.loads(
        (tmp_path / "2026-08-29_event_dossiers_stats_sheet.json").read_text()
    )
    assert all(row["superbet"] is None for row in sheet["rows"])


def test_analyze_survives_an_unreadable_offer(analyze_module, monkeypatch, tmp_path):
    dossier = _write_dossier(tmp_path / "2026-08-29_event_dossiers.json")
    broken = tmp_path / "offer.json"
    broken.write_text("{not json", encoding="utf-8")
    code = _run_main(
        analyze_module, monkeypatch,
        ["--dossier", str(dossier), "--output-dir", str(tmp_path),
         "--superbet-offer", str(broken), "--db-path", str(tmp_path / "t.db")],
    )
    assert code in (0, 1)
    sheet = json.loads(
        (tmp_path / "2026-08-29_event_dossiers_stats_sheet.json").read_text()
    )
    assert all(row["superbet"] is None for row in sheet["rows"])


def test_analyze_without_the_flag_leaves_the_column_absent(
    analyze_module, monkeypatch, tmp_path
):
    dossier = _write_dossier(tmp_path / "2026-08-29_event_dossiers.json")
    _run_main(
        analyze_module, monkeypatch,
        ["--dossier", str(dossier), "--output-dir", str(tmp_path),
         "--db-path", str(tmp_path / "t.db")],
    )
    sheet = json.loads(
        (tmp_path / "2026-08-29_event_dossiers_stats_sheet.json").read_text()
    )
    assert all(row["superbet"] is None for row in sheet["rows"])


# --- build_coupons.py ------------------------------------------------------


def test_build_coupons_renders_the_superbet_column(coupons_module, monkeypatch, tmp_path):
    sheet = _write(tmp_path / "sheet.json", SHEET)
    events = _write(tmp_path / "el.json", EVENT_LIST)
    offer = _write(tmp_path / "offer.json", _offer_doc())
    output = tmp_path / "kupony.md"
    code = _run_main(
        coupons_module, monkeypatch,
        ["--stats-sheet", str(sheet), "--event-list", str(events),
         "--superbet-offer", str(offer), "--output", str(output), "--include-started"],
    )
    assert code == 0
    rendered = output.read_text(encoding="utf-8")
    assert "| Superbet |" in rendered
    assert "2.20 ✓" in rendered
    assert "Superbet: 1 z 1 singli" in rendered


def test_build_coupons_names_a_missing_line_rather_than_a_dash(
    coupons_module, monkeypatch, tmp_path
):
    sheet = _write(tmp_path / "sheet.json", SHEET)
    events = _write(tmp_path / "el.json", EVENT_LIST)
    offer = _write(tmp_path / "offer.json", _offer_doc(line=12.5))
    output = tmp_path / "kupony.md"
    _run_main(
        coupons_module, monkeypatch,
        ["--stats-sheet", str(sheet), "--event-list", str(events),
         "--superbet-offer", str(offer), "--output", str(output), "--include-started"],
    )
    rendered = output.read_text(encoding="utf-8")
    assert "brak linii (ma 12.5)" in rendered


def test_build_coupons_resolves_the_offer_from_the_date(
    coupons_module, monkeypatch, tmp_path
):
    """--date alone must find the offer, the same way it finds every other
    artifact. An operator who passes only the day should not silently lose the
    column because he did not know a second flag existed."""
    run_dir = tmp_path / "runs" / "2026-08-29"
    run_dir.mkdir(parents=True)
    _write(run_dir / "2026-08-29_event_dossiers_stats_sheet.json", SHEET)
    _write(run_dir / "2026-08-29_event_list.json", EVENT_LIST)
    _write(run_dir / "2026-08-29_superbet_offer.json", _offer_doc())
    monkeypatch.setattr(coupons_module, "ROOT", tmp_path)
    code = _run_main(
        coupons_module, monkeypatch, ["--date", "2026-08-29", "--include-started"]
    )
    assert code == 0
    assert "2.20 ✓" in (run_dir / "2026-08-29_kupony.md").read_text(encoding="utf-8")


def test_build_coupons_refuses_an_explicitly_named_missing_offer(
    coupons_module, monkeypatch, tmp_path
):
    """An absent optional artifact is fine. An absent *requested* one is not:
    printing a coupon with no Superbet column beside a command that asked for
    one is how a check gets silently skipped."""
    sheet = _write(tmp_path / "sheet.json", SHEET)
    code = _run_main(
        coupons_module, monkeypatch,
        ["--stats-sheet", str(sheet), "--output", str(tmp_path / "k.md"),
         "--superbet-offer", str(tmp_path / "nope.json"), "--include-started"],
    )
    assert code == 2


def test_require_superbet_value_flag_is_wired(coupons_module, monkeypatch, tmp_path):
    sheet = _write(tmp_path / "sheet.json", SHEET)
    events = _write(tmp_path / "el.json", EVENT_LIST)
    offer = _write(tmp_path / "offer.json", _offer_doc(price=1.05))
    output = tmp_path / "kupony.md"
    code = _run_main(
        coupons_module, monkeypatch,
        ["--stats-sheet", str(sheet), "--event-list", str(events),
         "--superbet-offer", str(offer), "--output", str(output),
         "--require-superbet-value", "--include-started"],
    )
    # Exit 1: the only row is priced below its threshold, so nothing survives.
    assert code == 1
