"""T36 — the full pipeline, offline, against frozen artifacts.

This is the only test that crosses stage boundaries, so it is the only one that
can catch a change which is locally correct in every stage and wrong between
them.

Three rules it follows, each because the previous version of this test broke
them and caught nothing:

1. **Nothing is stubbed out.** Every stage's real `main()` runs. Replacing a
   stage with a function that writes `[]` makes the downstream stages trivially
   pass on an empty input.
2. **No exception is swallowed.** A stage that raises fails the test.
3. **Emptiness is a failure.** Every artifact is asserted non-empty and its row
   count is frozen. Six files existing proves nothing; the previous version
   asserted exactly that and passed while pricing zero rows.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import RootModel

from bet.sofa.client import SofascoreClient, TransportResponse
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import (
    BoardFixture,
    Coupon,
    Fixture,
    FixtureOffer,
    FixtureSamples,
    SheetRow,
)
from bet.sofa.db import migrate
from scripts.sofa import run_pipeline

BUNDLE_PATH = Path("tests/fixtures/sofascore/e2e_bundle.json")
EXPECTED_PATH = Path("tests/fixtures/sofascore/e2e_expected.json")
RUN_DATE = "2026-09-17"
# Well before the fixtures' kickoffs, so the coupon's kickoff and price-freshness
# gates are exercised in their passing direction rather than skipped.
FROZEN_NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def bundle() -> dict[str, Any]:
    return json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))


class ReplayResponse:
    def __init__(self, status_code: int, data: Any) -> None:
        self._status_code = status_code
        self._data = data

    @property
    def status_code(self) -> int:
        return self._status_code

    def json(self) -> Any:
        if self._data is None:
            raise ValueError("no body")
        return self._data

    @property
    def text(self) -> str:
        return json.dumps(self._data)


class ReplayTransport:
    """Serves the bundle by exact route; anything else is a 404.

    404 rather than a default body on purpose: an unexpected request should
    look to the pipeline like a resource that does not exist (which is a
    legitimate answer it must handle), not like data we invented for it.
    """

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.requested: list[str] = []

    def get(self, url: str, timeout: float = 10.0) -> TransportResponse:
        suffix = url.split("/api/v1/", 1)[-1]
        self.requested.append(suffix)
        if suffix in self.routes:
            return ReplayResponse(200, self.routes[suffix])
        # search/all is quoted by the client; compare on the decoded query too.
        from urllib.parse import unquote

        decoded = unquote(suffix)
        if decoded in self.routes:
            return ReplayResponse(200, self.routes[decoded])
        return ReplayResponse(404, None)


class ReplaySuperbetClient:
    def __init__(self, board: list[dict[str, Any]], odds: dict[str, Any]) -> None:
        self._board = board
        self._odds = odds
        self.odds_calls = 0

    def events_by_date(
        self,
        window_start: datetime,
        window_end: datetime,
        *,
        offer_state: str = "prematch",
    ) -> list[dict[str, Any]]:
        return self._board

    def event_odds(self, event_id: int | str) -> dict[str, Any] | None:
        self.odds_calls += 1
        return self._odds.get(str(event_id))


@pytest.fixture
def pipeline_env(
    bundle: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[SofaConfig, ReplayTransport, ReplaySuperbetClient]:
    config = SofaConfig(
        db_path=str(tmp_path / "sofa.db"),
        runs_dir=str(tmp_path / "runs"),
        target_rps=100000,
        min_sample=5,
        sample_n=10,
    )
    migrate(config.db_path)

    transport = ReplayTransport(bundle["sofascore"])
    superbet = ReplaySuperbetClient(
        bundle["superbet"]["events_by_date"], bundle["superbet"]["event_odds"]
    )

    monkeypatch.setattr(SofaConfig, "from_env", classmethod(lambda cls: config))

    original_init = SofascoreClient.__init__

    def replay_init(
        self: SofascoreClient, cfg: SofaConfig, transport_arg: Any = None
    ) -> None:
        original_init(self, cfg, transport=transport)

    monkeypatch.setattr(SofascoreClient, "__init__", replay_init)

    for module in (
        "bet.sofa.samples",
        "bet.sofa.board",
        "scripts.sofa.run_board",
        "scripts.sofa.run_samples",
        "scripts.sofa.run_offer",
    ):
        try:
            monkeypatch.setattr(f"{module}.SuperbetClient", lambda *a, **k: superbet)
        except AttributeError:
            pass

    monkeypatch.setattr("bet.sofa.timeutil.now", lambda: FROZEN_NOW)
    for module in (
        "bet.sofa.offer",
        "bet.sofa.client",
        "bet.sofa.cache",
        "bet.sofa.superbet",
        "scripts.sofa.run_board",
        "scripts.sofa.run_resolve",
        "scripts.sofa.run_samples",
        "scripts.sofa.run_offer",
        "scripts.sofa.run_sheet",
        "scripts.sofa.run_coupon",
        "scripts.sofa.run_pipeline",
    ):
        try:
            monkeypatch.setattr(f"{module}.now", lambda: FROZEN_NOW)
        except AttributeError:
            pass

    return config, transport, superbet


def read_artifact(run_dir: Path, name: str) -> Any:
    path = run_dir / name
    assert path.exists(), f"{name} was never written"
    return json.loads(path.read_text(encoding="utf-8"))


def read_bytes(run_dir: Path, name: str) -> bytes:
    """T15: an artifact must reload through its own model from the bytes on
    disk, with no tolerance. That is the same call production makes."""
    path = run_dir / name
    assert path.exists(), f"{name} was never written"
    return path.read_bytes()


def test_full_pipeline_offline(
    pipeline_env: tuple[SofaConfig, ReplayTransport, ReplaySuperbetClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, transport, superbet = pipeline_env
    monkeypatch.setattr("sys.argv", ["run_pipeline.py", "--date", RUN_DATE])

    exit_code = run_pipeline.main()
    run_dir = Path(config.runs_dir) / RUN_DATE

    # --- every artifact exists, validates against its own model, and is non-empty
    board = (
        RootModel[list[BoardFixture]]
        .model_validate_json(read_bytes(run_dir, "01_board.json"))
        .root
    )
    assert len(board) == 3, "board lost fixtures"
    assert {b.sport for b in board} == {"football", "tennis"}

    fixtures = (
        RootModel[list[Fixture]]
        .model_validate_json(read_bytes(run_dir, "02_fixtures.json"))
        .root
    )
    assert len(fixtures) == 3, "resolve lost fixtures"
    assert all(f.kickoff_utc.tzinfo is not None for f in fixtures)

    samples = (
        RootModel[list[FixtureSamples]]
        .model_validate_json(read_bytes(run_dir, "03_samples.json"))
        .root
    )
    assert len(samples) == 3
    ready = [s for s in samples if s.readiness == "READY"]
    assert ready, "no fixture reached READY; a gate nobody can pass looks like no data"
    assert any(s.metrics for s in samples), "no metric was sampled at all"

    offers = (
        RootModel[list[FixtureOffer]]
        .model_validate_json(read_bytes(run_dir, "04_offer.json"))
        .root
    )
    assert len(offers) == 3
    priced = [o for o in offers if o.rungs]
    assert priced, "offer produced no priced rung"

    sheet = (
        RootModel[list[SheetRow]]
        .model_validate_json(read_bytes(run_dir, "05_sheet.json"))
        .root
    )
    assert sheet, "the sheet is empty: the engine priced nothing"
    assert all(r.required_odds > 1.0 for r in sheet)
    for row in sheet:
        if row.market_p is not None:
            assert row.edge == pytest.approx(
                round(row.p_central - row.market_p, 4), abs=1e-9
            )

    coupon = Coupon.model_validate_json(read_bytes(run_dir, "06_coupon.json"))
    assert coupon.created_at_utc == FROZEN_NOW

    markdown = (run_dir / "06_coupon.md").read_text(encoding="utf-8")
    assert markdown.strip()

    # A4: the offer is read twice, so every fixture's odds are fetched twice.
    assert superbet.odds_calls >= 2 * len(fixtures)

    assert exit_code in (0, 1), f"pipeline reported FAILED (exit {exit_code})"


def test_artifacts_match_the_frozen_expectation(
    pipeline_env: tuple[SofaConfig, ReplayTransport, ReplaySuperbetClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Freeze the shape of all six artifacts.

    Regenerate with SOFA_FREEZE_E2E=1 after a *deliberate* change, and read the
    diff before committing it — that diff is the whole point of this test.
    """
    import os

    config, _transport, _superbet = pipeline_env
    monkeypatch.setattr("sys.argv", ["run_pipeline.py", "--date", RUN_DATE])
    run_pipeline.main()

    run_dir = Path(config.runs_dir) / RUN_DATE
    sheet = read_artifact(run_dir, "05_sheet.json")
    samples = read_artifact(run_dir, "03_samples.json")
    offers = read_artifact(run_dir, "04_offer.json")
    coupon = read_artifact(run_dir, "06_coupon.json")

    actual = {
        "board_fixtures": len(read_artifact(run_dir, "01_board.json")),
        "resolved_fixtures": len(read_artifact(run_dir, "02_fixtures.json")),
        "samples_readiness": sorted(s["readiness"] for s in samples),
        "sampled_metrics": sorted({m for s in samples for m in s.get("metrics", {})}),
        "sample_sizes": sorted(
            len(m["side_a"]) + len(m["side_b"])
            for s in samples
            for m in s.get("metrics", {}).values()
        ),
        "offer_rungs": sorted(len(o["rungs"]) for o in offers),
        "sheet_rows": len(sheet),
        "sheet_verdicts": sorted({r["verdict"] for r in sheet}),
        "coupon_singles": len(coupon["singles"]),
    }

    if os.environ.get("SOFA_FREEZE_E2E") == "1":
        EXPECTED_PATH.write_text(
            json.dumps(actual, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        pytest.skip(f"froze new expectation into {EXPECTED_PATH}")

    assert EXPECTED_PATH.exists(), (
        f"{EXPECTED_PATH} missing — generate it with SOFA_FREEZE_E2E=1"
    )
    expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    assert actual == expected
