"""Paper-trading readiness harness for auditable, non-executable bet tracking."""
from __future__ import annotations

import json
from dataclasses import dataclass, fields, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from bet.pipeline.artifact_gate import (
    artifact_path_for,
    expected_s8_coupon_draft_path,
    load_artifact,
    sha256_file,
    validate_s9_human_gate_artifact_for_run,
)
from bet.pipeline.full_shadow_acceptance import (
    build_s9_human_gate_artifact,
    compare_path_snapshots,
    is_protected_repo_path,
    snapshot_protected_repo_paths,
    write_s9_human_gate_artifact,
)
from bet.pipeline.run_evidence import utc_now_iso, write_json_atomic
from bet.pipeline.runtime_modes import RuntimeMode, parse_runtime_mode


TASK_ID = "PIPELINE_PAPER_TRADING_READINESS_A"
SINGLE_COUPON_SOURCE_TASK_ID = "PIPELINE_PAPER_OPERATIONAL_SINGLE_COUPON_SOURCE_A"
REPO_ROOT = Path(__file__).resolve().parents[3]
LEDGER_FILENAME = "paper_coupons.jsonl"
OPEN_STATUS = "OPEN"
SETTLED_WIN_STATUS = "SETTLED_WIN"
SETTLED_LOSS_STATUS = "SETTLED_LOSS"
VOID_STATUS = "VOID"
FINAL_STATUSES = {SETTLED_WIN_STATUS, SETTLED_LOSS_STATUS, VOID_STATUS}
ALL_STATUSES = FINAL_STATUSES | {OPEN_STATUS}
ZERO = Decimal("0")
ONE = Decimal("1")
SINGLE_COUPON_SELECTION_POLICY = "first_fixture_safe_lexicographic"
SKIPPED_OPERATIONAL_OPEN_COUPON = "SKIPPED_OPERATIONAL_OPEN_COUPON"


def _to_decimal(value: Decimal | int | float | str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid decimal value: {value!r}") from exc


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        Path(path).resolve(strict=False).relative_to(Path(root).resolve(strict=False))
    except ValueError:
        return False
    return True


def _serialize_jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [_serialize_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_jsonable(item) for key, item in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return {name: _serialize_jsonable(getattr(value, name)) for name in value.__dataclass_fields__}
    return value


@dataclass(frozen=True)
class PaperTradingConfig:
    base_dir: Path
    betting_day: str
    run_id: str
    ledger_dir: Path
    runtime_mode: str = "DRY_RUN"
    bankroll_units: Decimal = ZERO
    max_stake_units_per_coupon: Decimal = ZERO
    max_daily_risk_units: Decimal = ZERO
    kill_switch: bool = False
    allow_real_bet_execution: bool = False
    allow_betclic_execution: bool = False
    allow_repo_protected_writes: bool = False

    def normalized(self) -> "PaperTradingConfig":
        return PaperTradingConfig(
            base_dir=Path(self.base_dir).resolve(strict=False),
            betting_day=self.betting_day,
            run_id=self.run_id,
            ledger_dir=Path(self.ledger_dir).resolve(strict=False),
            runtime_mode=parse_runtime_mode(self.runtime_mode).value,
            bankroll_units=_to_decimal(self.bankroll_units),
            max_stake_units_per_coupon=_to_decimal(self.max_stake_units_per_coupon),
            max_daily_risk_units=_to_decimal(self.max_daily_risk_units),
            kill_switch=self.kill_switch,
            allow_real_bet_execution=self.allow_real_bet_execution,
            allow_betclic_execution=self.allow_betclic_execution,
            allow_repo_protected_writes=self.allow_repo_protected_writes,
        )


@dataclass(frozen=True)
class PaperCoupon:
    paper_coupon_id: str
    betting_day: str
    run_id: str
    source_s8_coupon_draft_path: str
    source_s8_coupon_draft_sha256: str
    source_s9_artifact_path: str | None
    source_s9_artifact_sha256: str | None
    selection_id: str
    event_id: str
    market: str
    pick: str
    odds_decimal: Decimal
    stake_units: Decimal
    expected_payout_units: Decimal
    created_at_utc: str
    status: str
    pnl_units: Decimal

    def to_jsonable(self) -> dict[str, Any]:
        return _serialize_jsonable({field.name: getattr(self, field.name) for field in fields(self)})


@dataclass(frozen=True)
class PaperTradingReadinessReport:
    task_id: str
    status: str
    betting_day: str
    run_id: str
    ledger_path: str
    coupon_count: int
    total_stake_units: Decimal
    max_stake_units_per_coupon: Decimal
    max_daily_risk_units: Decimal
    kill_switch_active: bool
    duplicate_blocked: bool
    budget_guard_verdict: str
    ledger_schema_verdict: str
    settlement_verdict: str
    no_real_bet_execution_verdict: str
    no_betclic_execution_verdict: str
    protected_repo_write_verdict: str
    ready_for_manual_low_stake_pilot: bool
    ready_for_production_execution: bool
    blockers: list[str]

    def to_jsonable(self) -> dict[str, Any]:
        return _serialize_jsonable({field.name: getattr(self, field.name) for field in fields(self)})


def paper_run_root(config: PaperTradingConfig) -> Path:
    return Path(config.base_dir) / "pipeline_runs" / config.betting_day / config.run_id


def expected_paper_ledger_path(config: PaperTradingConfig) -> Path:
    return Path(config.ledger_dir) / LEDGER_FILENAME


def expected_paper_s8_draft_path(config: PaperTradingConfig) -> Path:
    return expected_s8_coupon_draft_path(config.base_dir, config.betting_day, config.run_id)


def expected_paper_s9_artifact_path(config: PaperTradingConfig) -> Path:
    return artifact_path_for(config.base_dir, config.betting_day, config.run_id, "S9")


def validate_paper_trading_config(
    config: PaperTradingConfig,
    *,
    report_path: Path | None = None,
    repo_root: Path = REPO_ROOT,
) -> list[str]:
    normalized = config.normalized()
    blockers: list[str] = []
    mode = parse_runtime_mode(normalized.runtime_mode)
    repo_root = Path(repo_root).resolve(strict=False)

    if mode == RuntimeMode.PRODUCTION:
        blockers.append("PRODUCTION mode is forbidden for paper trading readiness")
    if normalized.allow_real_bet_execution:
        blockers.append("real bet execution must remain disabled")
    if normalized.allow_betclic_execution:
        blockers.append("Betclic execution must remain disabled")
    if normalized.allow_repo_protected_writes:
        blockers.append("repo protected writes must remain disabled")
    if normalized.kill_switch:
        blockers.append("kill_switch is active")
    if _path_is_within(normalized.base_dir, repo_root):
        blockers.append(f"base_dir must be outside repo root: {normalized.base_dir}")
    if _path_is_within(normalized.ledger_dir, repo_root):
        blockers.append(f"ledger_dir must be outside repo root: {normalized.ledger_dir}")
    if is_protected_repo_path(normalized.base_dir, repo_root):
        blockers.append(f"base_dir cannot be under protected repo-local paths: {normalized.base_dir}")
    if is_protected_repo_path(normalized.ledger_dir, repo_root):
        blockers.append(f"ledger_dir cannot be under protected repo-local paths: {normalized.ledger_dir}")
    if report_path is not None:
        resolved_report_path = Path(report_path).resolve(strict=False)
        if _path_is_within(resolved_report_path, repo_root):
            blockers.append(f"report_path must be outside repo root: {resolved_report_path}")
        if is_protected_repo_path(resolved_report_path, repo_root):
            blockers.append(f"report_path cannot be under protected repo-local paths: {resolved_report_path}")

    if normalized.bankroll_units <= ZERO:
        blockers.append("bankroll_units must be > 0")
    if normalized.max_stake_units_per_coupon <= ZERO:
        blockers.append("max_stake_units_per_coupon must be > 0")
    if normalized.max_daily_risk_units <= ZERO:
        blockers.append("max_daily_risk_units must be > 0")
    if normalized.max_stake_units_per_coupon > normalized.bankroll_units:
        blockers.append("max_stake_units_per_coupon cannot exceed bankroll_units")
    if normalized.max_daily_risk_units > normalized.bankroll_units:
        blockers.append("max_daily_risk_units cannot exceed bankroll_units")

    return blockers


def _validate_coupon_fields(coupon: PaperCoupon, config: PaperTradingConfig) -> list[str]:
    issues: list[str] = []

    if coupon.betting_day != config.betting_day:
        issues.append("paper coupon betting_day must match config")
    if coupon.run_id != config.run_id:
        issues.append("paper coupon run_id must match config")
    if not coupon.paper_coupon_id.strip():
        issues.append("paper_coupon_id must be non-empty")
    if not coupon.source_s8_coupon_draft_path.strip():
        issues.append("source_s8_coupon_draft_path must be non-empty")
    if not coupon.source_s8_coupon_draft_sha256.strip():
        issues.append("source_s8_coupon_draft_sha256 must be non-empty")
    if coupon.source_s9_artifact_path is None or not str(coupon.source_s9_artifact_path).strip():
        issues.append("source_s9_artifact_path must be present for paper coupon creation")
    if coupon.source_s9_artifact_sha256 is None or not str(coupon.source_s9_artifact_sha256).strip():
        issues.append("source_s9_artifact_sha256 must be present for paper coupon creation")
    if not coupon.selection_id.strip():
        issues.append("selection_id must be non-empty")
    if not coupon.event_id.strip():
        issues.append("event_id must be non-empty")
    if not coupon.market.strip():
        issues.append("market must be non-empty")
    if not coupon.pick.strip():
        issues.append("pick must be non-empty")
    if coupon.status not in ALL_STATUSES:
        issues.append(f"status must be one of {sorted(ALL_STATUSES)}")
    if coupon.stake_units <= ZERO:
        issues.append("stake_units must be > 0")
    if coupon.odds_decimal <= Decimal("1"):
        issues.append("odds_decimal must be > 1")
    if coupon.expected_payout_units != coupon.stake_units * coupon.odds_decimal:
        issues.append("expected_payout_units must equal stake_units * odds_decimal")
    return issues


def _coupon_from_jsonable(raw: dict[str, Any]) -> PaperCoupon:
    return PaperCoupon(
        paper_coupon_id=str(raw["paper_coupon_id"]),
        betting_day=str(raw["betting_day"]),
        run_id=str(raw["run_id"]),
        source_s8_coupon_draft_path=str(raw["source_s8_coupon_draft_path"]),
        source_s8_coupon_draft_sha256=str(raw["source_s8_coupon_draft_sha256"]),
        source_s9_artifact_path=(None if raw.get("source_s9_artifact_path") is None else str(raw.get("source_s9_artifact_path"))),
        source_s9_artifact_sha256=(None if raw.get("source_s9_artifact_sha256") is None else str(raw.get("source_s9_artifact_sha256"))),
        selection_id=str(raw["selection_id"]),
        event_id=str(raw["event_id"]),
        market=str(raw["market"]),
        pick=str(raw["pick"]),
        odds_decimal=_to_decimal(raw["odds_decimal"]),
        stake_units=_to_decimal(raw["stake_units"]),
        expected_payout_units=_to_decimal(raw["expected_payout_units"]),
        created_at_utc=str(raw["created_at_utc"]),
        status=str(raw["status"]),
        pnl_units=_to_decimal(raw["pnl_units"]),
    )


def _ledger_event(event_type: str, coupon: PaperCoupon) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "event_type": event_type,
        "recorded_at_utc": utc_now_iso(),
        "coupon": coupon.to_jsonable(),
    }


def _append_ledger_event(ledger_path: Path, event: dict[str, Any]) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def read_ledger_events(ledger_path: Path) -> list[dict[str, Any]]:
    ledger_path = Path(ledger_path)
    if not ledger_path.exists():
        return []

    events: list[dict[str, Any]] = []
    with open(ledger_path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                raise ValueError(f"Blank JSONL line at {ledger_path}:{line_number}")
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {ledger_path}:{line_number}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"Ledger event must be an object at {ledger_path}:{line_number}")
            events.append(payload)
    return events


def load_latest_paper_coupons(ledger_path: Path) -> dict[str, PaperCoupon]:
    coupons: dict[str, PaperCoupon] = {}
    for line_number, event in enumerate(read_ledger_events(ledger_path), start=1):
        event_type = event.get("event_type")
        if event_type not in {"coupon_opened", "coupon_settled"}:
            raise ValueError(f"Unsupported ledger event_type at line {line_number}: {event_type!r}")
        coupon_raw = event.get("coupon")
        if not isinstance(coupon_raw, dict):
            raise ValueError(f"Ledger event coupon must be an object at line {line_number}")
        coupon = _coupon_from_jsonable(coupon_raw)
        issues = _validate_coupon_fields(coupon, PaperTradingConfig(
            base_dir=Path(coupon.source_s8_coupon_draft_path).parent,
            betting_day=coupon.betting_day,
            run_id=coupon.run_id,
            ledger_dir=Path(ledger_path).parent,
            bankroll_units=Decimal("999999"),
            max_stake_units_per_coupon=Decimal("999999"),
            max_daily_risk_units=Decimal("999999"),
        ))
        if issues:
            raise ValueError(f"Invalid coupon payload at line {line_number}: {'; '.join(issues)}")

        existing = coupons.get(coupon.paper_coupon_id)
        if event_type == "coupon_opened":
            if existing is not None:
                raise ValueError(f"Duplicate coupon_opened for {coupon.paper_coupon_id} at line {line_number}")
            if coupon.status != OPEN_STATUS or coupon.pnl_units != ZERO:
                raise ValueError(f"coupon_opened must store OPEN/0 state for {coupon.paper_coupon_id}")
            coupons[coupon.paper_coupon_id] = coupon
            continue

        if existing is None:
            raise ValueError(f"coupon_settled without prior open for {coupon.paper_coupon_id}")
        if existing.status != OPEN_STATUS:
            raise ValueError(f"coupon_settled after terminal state for {coupon.paper_coupon_id}")
        if coupon.status not in FINAL_STATUSES:
            raise ValueError(f"coupon_settled must store terminal status for {coupon.paper_coupon_id}")
        coupons[coupon.paper_coupon_id] = coupon

    return coupons


def validate_ledger_jsonl_schema(ledger_path: Path) -> list[str]:
    issues: list[str] = []
    try:
        load_latest_paper_coupons(ledger_path)
    except ValueError as exc:
        issues.append(str(exc))
    return issues


def open_daily_risk_units(ledger_path: Path) -> Decimal:
    coupons = load_latest_paper_coupons(ledger_path)
    return sum((coupon.stake_units for coupon in coupons.values() if coupon.status == OPEN_STATUS), start=ZERO)


def _coupon_creation_blocked_without_write(
    config: PaperTradingConfig,
    coupon: PaperCoupon,
    *,
    expected_error_fragment: str,
    ledger_path: Path,
    repo_root: Path = REPO_ROOT,
) -> bool:
    before = ledger_path.read_bytes() if ledger_path.exists() else b""
    try:
        create_paper_coupon(config, coupon, repo_root=repo_root)
    except ValueError as exc:
        after = ledger_path.read_bytes() if ledger_path.exists() else b""
        return expected_error_fragment in str(exc) and before == after
    return False


def create_paper_coupon(
    config: PaperTradingConfig,
    coupon: PaperCoupon,
    *,
    repo_root: Path = REPO_ROOT,
) -> PaperCoupon:
    normalized = config.normalized()
    blockers = validate_paper_trading_config(normalized, repo_root=repo_root)
    if blockers:
        raise ValueError("; ".join(blockers))

    if normalized.kill_switch:
        raise ValueError("kill_switch is active")

    ledger_path = expected_paper_ledger_path(normalized)
    issues = _validate_coupon_fields(coupon, normalized)
    if issues:
        raise ValueError("; ".join(issues))
    if coupon.status != OPEN_STATUS or coupon.pnl_units != ZERO:
        raise ValueError("new paper coupon must start with OPEN status and pnl_units=0")
    if coupon.stake_units > normalized.max_stake_units_per_coupon:
        raise ValueError("stake_units exceeds max_stake_units_per_coupon")

    existing = load_latest_paper_coupons(ledger_path)
    if coupon.paper_coupon_id in existing:
        raise ValueError(f"duplicate paper_coupon_id blocked: {coupon.paper_coupon_id}")

    open_risk = sum((item.stake_units for item in existing.values() if item.status == OPEN_STATUS), start=ZERO)
    if coupon.stake_units > normalized.bankroll_units:
        raise ValueError("stake_units exceeds bankroll_units")
    if open_risk + coupon.stake_units > normalized.max_daily_risk_units:
        raise ValueError("coupon would exceed max_daily_risk_units")
    if open_risk + coupon.stake_units > normalized.bankroll_units:
        raise ValueError("coupon would exceed bankroll_units")

    _append_ledger_event(ledger_path, _ledger_event("coupon_opened", coupon))
    return coupon


def settle_paper_coupon(
    config: PaperTradingConfig,
    paper_coupon_id: str,
    result_status: str,
) -> PaperCoupon:
    normalized = config.normalized()
    ledger_path = expected_paper_ledger_path(normalized)
    latest = load_latest_paper_coupons(ledger_path)
    current = latest.get(paper_coupon_id)
    if current is None:
        raise ValueError(f"paper coupon not found: {paper_coupon_id}")
    if current.status != OPEN_STATUS:
        raise ValueError(f"paper coupon already settled: {paper_coupon_id}")
    if result_status not in FINAL_STATUSES:
        raise ValueError(f"unsupported result_status: {result_status}")

    if result_status == SETTLED_WIN_STATUS:
        pnl_units = current.stake_units * (current.odds_decimal - Decimal("1"))
    elif result_status == SETTLED_LOSS_STATUS:
        pnl_units = -current.stake_units
    else:
        pnl_units = ZERO

    settled = replace(current, status=result_status, pnl_units=pnl_units)
    _append_ledger_event(ledger_path, _ledger_event("coupon_settled", settled))
    return settled


def _selection_odds_decimal(selection: dict[str, Any]) -> Decimal:
    for key in ("odds_decimal", "odds", "price"):
        if key in selection and selection[key] not in (None, ""):
            return _to_decimal(selection[key])
    raise ValueError("selection must include odds_decimal/odds/price")


def _selection_stake_units(selection: dict[str, Any]) -> Decimal:
    for key in ("stake_units", "paper_stake_units"):
        if key in selection and selection[key] not in (None, ""):
            return _to_decimal(selection[key])
    return Decimal("1")


def build_paper_coupons_from_bound_s8_s9(
    *,
    config: PaperTradingConfig,
    s8_coupon_draft_path: Path,
    s9_human_gate_artifact_path: Path,
) -> list[PaperCoupon]:
    normalized = config.normalized()
    draft_path = Path(s8_coupon_draft_path).resolve(strict=False)
    s9_path = Path(s9_human_gate_artifact_path).resolve(strict=False)

    if not draft_path.exists():
        raise ValueError(f"S8 coupon draft file not found: {draft_path}")
    if not s9_path.exists():
        raise ValueError(f"S9 human gate artifact file not found: {s9_path}")

    draft = load_artifact(draft_path)
    draft_sha256 = sha256_file(draft_path)
    s9_artifact = load_artifact(s9_path)
    s9_sha256 = sha256_file(s9_path)
    issues = validate_s9_human_gate_artifact_for_run(
        s9_artifact,
        base_dir=normalized.base_dir,
        betting_day=normalized.betting_day,
        run_id=normalized.run_id,
    )
    if issues:
        raise ValueError("S9 artifact is not bound to the canonical S8 draft: " + "; ".join(issue.code for issue in issues))

    if draft.get("artifact_type") != "S8_COUPON_DRAFTS":
        raise ValueError("S8 coupon draft artifact_type must be S8_COUPON_DRAFTS")
    if draft.get("betting_day") != normalized.betting_day or draft.get("run_id") != normalized.run_id:
        raise ValueError("S8 coupon draft must match betting_day and run_id")
    if draft.get("ready_for_production_execution") is True:
        raise ValueError("S8 coupon draft cannot be production-ready")
    if draft.get("production_coupon_write") is True:
        raise ValueError("S8 coupon draft cannot enable production coupon writes")
    if draft.get("executable_coupon") is True:
        raise ValueError("S8 coupon draft cannot be executable")
    if draft.get("betclic_execution_enabled") is True:
        raise ValueError("S8 coupon draft cannot enable Betclic execution")

    drafts = draft.get("drafts")
    if not isinstance(drafts, list) or not drafts:
        raise ValueError("S8 coupon draft must include at least one draft entry")

    coupons: list[PaperCoupon] = []
    for draft_index, draft_entry in enumerate(drafts, start=1):
        if not isinstance(draft_entry, dict):
            raise ValueError("Each S8 draft entry must be an object")
        draft_id = str(draft_entry.get("draft_id") or draft_entry.get("id") or f"draft-{draft_index}")
        selections = draft_entry.get("selections")
        if not isinstance(selections, list) or not selections:
            raise ValueError(f"S8 draft {draft_id} must include selections")
        if draft_entry.get("not_for_production_execution") is not True:
            raise ValueError(f"S8 draft {draft_id} must stay not_for_production_execution=true")

        for selection_index, selection in enumerate(selections, start=1):
            if not isinstance(selection, dict):
                raise ValueError(f"S8 selection at {draft_id}[{selection_index}] must be an object")
            if selection.get("fixture_safe") is not True and selection.get("paper_trade_fixture") is not True:
                raise ValueError(f"S8 selection at {draft_id}[{selection_index}] is not fixture/test-safe")

            selection_id = str(selection.get("selection_id") or selection.get("id") or f"{draft_id}-selection-{selection_index}")
            event_id = str(
                selection.get("event_id")
                or selection.get("fixture_id")
                or selection.get("fixture")
                or selection.get("event")
                or f"{normalized.run_id}-{selection_id}"
            )
            market = str(selection.get("market") or selection.get("market_name") or "UNKNOWN_MARKET")
            pick = str(selection.get("pick") or selection.get("direction") or selection.get("selection") or "UNKNOWN_PICK")
            odds_decimal = _selection_odds_decimal(selection)
            stake_units = _selection_stake_units(selection)
            paper_coupon_id = f"{normalized.run_id}:{draft_id}:{selection_id}"
            coupons.append(
                PaperCoupon(
                    paper_coupon_id=paper_coupon_id,
                    betting_day=normalized.betting_day,
                    run_id=normalized.run_id,
                    source_s8_coupon_draft_path=str(draft_path),
                    source_s8_coupon_draft_sha256=draft_sha256,
                    source_s9_artifact_path=str(s9_path),
                    source_s9_artifact_sha256=s9_sha256,
                    selection_id=selection_id,
                    event_id=event_id,
                    market=market,
                    pick=pick,
                    odds_decimal=odds_decimal,
                    stake_units=stake_units,
                    expected_payout_units=stake_units * odds_decimal,
                    created_at_utc=utc_now_iso(),
                    status=OPEN_STATUS,
                    pnl_units=ZERO,
                )
            )

    return coupons


def write_fixture_paper_trading_artifacts(config: PaperTradingConfig) -> tuple[Path, Path]:
    normalized = config.normalized()
    draft_path = expected_paper_s8_draft_path(normalized)
    s9_path = expected_paper_s9_artifact_path(normalized)
    payload = {
        "schema_version": 1,
        "artifact_type": "S8_COUPON_DRAFTS",
        "betting_day": normalized.betting_day,
        "run_id": normalized.run_id,
        "runtime_mode": normalized.runtime_mode,
        "source_input_path": str(paper_run_root(normalized) / "data" / f"{normalized.betting_day}_s7_gate_results.json"),
        "coupon_draft_count": 1,
        "requires_human_gate": True,
        "ready_for_human_gate": True,
        "ready_for_production_execution": False,
        "production_selectable": False,
        "production_coupon_write": False,
        "executable_coupon": False,
        "betclic_execution_enabled": False,
        "drafts": [
            {
                "draft_id": "paper-ready-draft-1",
                "not_for_production_execution": True,
                "selections": [
                    {
                        "selection_id": "selection-win",
                        "fixture_safe": True,
                        "event_id": "fixture-001",
                        "market": "Goals Over 2.5",
                        "pick": "OVER 2.5",
                        "odds_decimal": "1.95",
                        "stake_units": "1",
                    },
                    {
                        "selection_id": "selection-loss",
                        "fixture_safe": True,
                        "event_id": "fixture-002",
                        "market": "Home Win",
                        "pick": "HOME",
                        "odds_decimal": "2.10",
                        "stake_units": "1",
                    },
                    {
                        "selection_id": "selection-void",
                        "fixture_safe": True,
                        "event_id": "fixture-003",
                        "market": "Both Teams To Score",
                        "pick": "YES",
                        "odds_decimal": "1.80",
                        "stake_units": "1",
                    },
                ],
            }
        ],
    }
    write_json_atomic(draft_path, payload)
    s9_artifact = build_s9_human_gate_artifact(
        normalized,
        coupon_draft_path=draft_path,
        coupon_draft_sha256=sha256_file(draft_path),
    )
    write_s9_human_gate_artifact(normalized, s9_artifact)
    return draft_path, s9_path


def _build_fixture_bound_paper_coupons(config: PaperTradingConfig) -> tuple[Path, Path, list[PaperCoupon]]:
    draft_path, s9_path = write_fixture_paper_trading_artifacts(config)
    coupons = build_paper_coupons_from_bound_s8_s9(
        config=config,
        s8_coupon_draft_path=draft_path,
        s9_human_gate_artifact_path=s9_path,
    )
    return draft_path, s9_path, coupons


def run_paper_trading_readiness(
    config: PaperTradingConfig,
    *,
    task_id: str = TASK_ID,
    report_path: Path | None = None,
    repo_root: Path = REPO_ROOT,
) -> PaperTradingReadinessReport:
    normalized = config.normalized()
    blockers = validate_paper_trading_config(normalized, report_path=report_path, repo_root=repo_root)
    if blockers:
        raise ValueError("; ".join(blockers))

    before_snapshot = snapshot_protected_repo_paths(repo_root)
    ledger_path = expected_paper_ledger_path(normalized)
    _, _, coupons = _build_fixture_bound_paper_coupons(normalized)

    for coupon in coupons:
        create_paper_coupon(normalized, coupon, repo_root=repo_root)

    duplicate_blocked = _coupon_creation_blocked_without_write(
        normalized,
        coupons[0],
        expected_error_fragment="duplicate paper_coupon_id blocked",
        ledger_path=ledger_path,
        repo_root=repo_root,
    )

    over_stake_coupon = replace(
        coupons[0],
        paper_coupon_id=f"{coupons[0].paper_coupon_id}:over-stake",
        stake_units=normalized.max_stake_units_per_coupon + Decimal("0.01"),
        expected_payout_units=(normalized.max_stake_units_per_coupon + Decimal("0.01")) * coupons[0].odds_decimal,
        created_at_utc=utc_now_iso(),
    )
    over_stake_blocked = _coupon_creation_blocked_without_write(
        normalized,
        over_stake_coupon,
        expected_error_fragment="max_stake_units_per_coupon",
        ledger_path=ledger_path,
        repo_root=repo_root,
    )

    over_risk_coupon = replace(
        coupons[0],
        paper_coupon_id=f"{coupons[0].paper_coupon_id}:over-risk",
        selection_id=f"{coupons[0].selection_id}-over-risk",
        event_id=f"{coupons[0].event_id}-over-risk",
        created_at_utc=utc_now_iso(),
    )
    over_risk_blocked = _coupon_creation_blocked_without_write(
        normalized,
        over_risk_coupon,
        expected_error_fragment="max_daily_risk_units",
        ledger_path=ledger_path,
        repo_root=repo_root,
    )

    kill_switch_blocked = _coupon_creation_blocked_without_write(
        replace(normalized, kill_switch=True),
        over_risk_coupon,
        expected_error_fragment="kill_switch is active",
        ledger_path=ledger_path,
        repo_root=repo_root,
    )

    settle_paper_coupon(normalized, coupons[0].paper_coupon_id, SETTLED_WIN_STATUS)
    settle_paper_coupon(normalized, coupons[1].paper_coupon_id, SETTLED_LOSS_STATUS)
    settle_paper_coupon(normalized, coupons[2].paper_coupon_id, VOID_STATUS)
    latest = load_latest_paper_coupons(ledger_path)
    settlement_verdict = "FAIL"
    if latest[coupons[0].paper_coupon_id].pnl_units == Decimal("0.95") and latest[coupons[1].paper_coupon_id].pnl_units == Decimal("-1") and latest[coupons[2].paper_coupon_id].pnl_units == ZERO:
        settlement_verdict = "PASS"
    else:
        blockers.append("settlement PnL math did not match WIN/LOSS/VOID expectations")

    ledger_schema_issues = validate_ledger_jsonl_schema(ledger_path)
    ledger_schema_verdict = "PASS" if not ledger_schema_issues else "FAIL"
    if ledger_schema_issues:
        blockers.extend(ledger_schema_issues)

    after_snapshot = snapshot_protected_repo_paths(repo_root)
    protected_changes = compare_path_snapshots(before_snapshot, after_snapshot)
    protected_repo_write_verdict = "PASS" if not protected_changes else "FAIL"
    if protected_changes:
        blockers.extend(protected_changes)

    budget_guard_verdict = "PASS" if over_stake_blocked and over_risk_blocked and normalized.max_daily_risk_units <= normalized.bankroll_units else "FAIL"
    if budget_guard_verdict == "FAIL":
        blockers.append("budget guard readiness proof failed")
    if not duplicate_blocked:
        blockers.append("duplicate submission was not idempotently blocked")
    if not kill_switch_blocked:
        blockers.append("kill switch did not fail closed")

    no_real_bet_execution_verdict = "PASS"
    no_betclic_execution_verdict = "PASS"
    ready_for_manual_low_stake_pilot = not blockers and settlement_verdict == "PASS"
    status = "PASS" if ready_for_manual_low_stake_pilot else "BLOCKED_PAPER_TRADING_READINESS"
    total_stake_units = sum((coupon.stake_units for coupon in latest.values()), start=ZERO)

    return PaperTradingReadinessReport(
        task_id=task_id,
        status=status,
        betting_day=normalized.betting_day,
        run_id=normalized.run_id,
        ledger_path=str(ledger_path),
        coupon_count=len(latest),
        total_stake_units=total_stake_units,
        max_stake_units_per_coupon=normalized.max_stake_units_per_coupon,
        max_daily_risk_units=normalized.max_daily_risk_units,
        kill_switch_active=normalized.kill_switch,
        duplicate_blocked=duplicate_blocked,
        budget_guard_verdict=budget_guard_verdict,
        ledger_schema_verdict=ledger_schema_verdict,
        settlement_verdict=settlement_verdict,
        no_real_bet_execution_verdict=no_real_bet_execution_verdict,
        no_betclic_execution_verdict=no_betclic_execution_verdict,
        protected_repo_write_verdict=protected_repo_write_verdict,
        ready_for_manual_low_stake_pilot=ready_for_manual_low_stake_pilot,
        ready_for_production_execution=False,
        blockers=blockers,
    )


def run_paper_trading_single_coupon_source(
    config: PaperTradingConfig,
    *,
    report_path: Path | None = None,
    repo_root: Path = REPO_ROOT,
    selection_policy: str = SINGLE_COUPON_SELECTION_POLICY,
    task_id: str = SINGLE_COUPON_SOURCE_TASK_ID,
) -> PaperTradingReadinessReport:
    normalized = config.normalized()
    blockers = validate_paper_trading_config(normalized, report_path=report_path, repo_root=repo_root)
    if selection_policy != SINGLE_COUPON_SELECTION_POLICY:
        blockers.append(f"unsupported selection_policy: {selection_policy}")
    if normalized.max_daily_risk_units > ONE:
        blockers.append("max_daily_risk_units must be <= 1 for single-coupon-source mode")
    if blockers:
        raise ValueError("; ".join(blockers))

    before_snapshot = snapshot_protected_repo_paths(repo_root)
    ledger_path = expected_paper_ledger_path(normalized)
    _, _, coupons = _build_fixture_bound_paper_coupons(normalized)
    ordered_coupons = sorted(coupons, key=lambda coupon: coupon.paper_coupon_id)
    if not ordered_coupons:
        raise ValueError("single-coupon-source mode requires at least one bound paper coupon")

    selected_coupon = ordered_coupons[0]
    create_paper_coupon(normalized, selected_coupon, repo_root=repo_root)

    duplicate_blocked = _coupon_creation_blocked_without_write(
        normalized,
        selected_coupon,
        expected_error_fragment="duplicate paper_coupon_id blocked",
        ledger_path=ledger_path,
        repo_root=repo_root,
    )

    over_stake_coupon = replace(
        selected_coupon,
        paper_coupon_id=f"{selected_coupon.paper_coupon_id}:over-stake",
        stake_units=normalized.max_stake_units_per_coupon + Decimal("0.01"),
        expected_payout_units=(normalized.max_stake_units_per_coupon + Decimal("0.01")) * selected_coupon.odds_decimal,
        created_at_utc=utc_now_iso(),
    )
    over_stake_blocked = _coupon_creation_blocked_without_write(
        normalized,
        over_stake_coupon,
        expected_error_fragment="max_stake_units_per_coupon",
        ledger_path=ledger_path,
        repo_root=repo_root,
    )

    secondary_coupon = next(
        (coupon for coupon in ordered_coupons if coupon.paper_coupon_id != selected_coupon.paper_coupon_id),
        None,
    )
    if secondary_coupon is None:
        blockers.append("single-coupon-source mode requires a second distinct coupon for over-risk proof")
    else:
        secondary_coupon = replace(secondary_coupon, created_at_utc=utc_now_iso())

    over_risk_blocked = False
    kill_switch_blocked = False
    if secondary_coupon is not None:
        over_risk_blocked = _coupon_creation_blocked_without_write(
            normalized,
            secondary_coupon,
            expected_error_fragment="max_daily_risk_units",
            ledger_path=ledger_path,
            repo_root=repo_root,
        )
        kill_switch_blocked = _coupon_creation_blocked_without_write(
            replace(normalized, kill_switch=True),
            secondary_coupon,
            expected_error_fragment="kill_switch is active",
            ledger_path=ledger_path,
            repo_root=repo_root,
        )

    latest = load_latest_paper_coupons(ledger_path)
    if len(latest) != 1:
        blockers.append(f"single-coupon-source mode must leave exactly one latest coupon in ledger; got {len(latest)}")
    if any(coupon.status != OPEN_STATUS for coupon in latest.values()):
        blockers.append("single-coupon-source mode must leave every latest coupon OPEN")

    total_stake_units = sum((coupon.stake_units for coupon in latest.values()), start=ZERO)
    if total_stake_units != ONE:
        blockers.append(f"single-coupon-source mode must leave total_stake_units=1; got {total_stake_units}")

    ledger_schema_issues = validate_ledger_jsonl_schema(ledger_path)
    ledger_schema_verdict = "PASS" if not ledger_schema_issues else "FAIL"
    if ledger_schema_issues:
        blockers.extend(ledger_schema_issues)

    after_snapshot = snapshot_protected_repo_paths(repo_root)
    protected_changes = compare_path_snapshots(before_snapshot, after_snapshot)
    protected_repo_write_verdict = "PASS" if not protected_changes else "FAIL"
    if protected_changes:
        blockers.extend(protected_changes)

    budget_guard_verdict = "PASS" if over_stake_blocked and over_risk_blocked else "FAIL"
    if budget_guard_verdict == "FAIL":
        blockers.append("single-coupon-source budget guard proof failed")
    if not duplicate_blocked:
        blockers.append("duplicate submission was not idempotently blocked")
    if not kill_switch_blocked:
        blockers.append("kill switch did not fail closed")

    no_real_bet_execution_verdict = "PASS"
    no_betclic_execution_verdict = "PASS"
    ready_for_manual_low_stake_pilot = not blockers
    status = "PASS" if ready_for_manual_low_stake_pilot else "BLOCKED_PAPER_TRADING_READINESS"

    return PaperTradingReadinessReport(
        task_id=task_id,
        status=status,
        betting_day=normalized.betting_day,
        run_id=normalized.run_id,
        ledger_path=str(ledger_path),
        coupon_count=len(latest),
        total_stake_units=total_stake_units,
        max_stake_units_per_coupon=normalized.max_stake_units_per_coupon,
        max_daily_risk_units=normalized.max_daily_risk_units,
        kill_switch_active=normalized.kill_switch,
        duplicate_blocked=duplicate_blocked,
        budget_guard_verdict=budget_guard_verdict,
        ledger_schema_verdict=ledger_schema_verdict,
        settlement_verdict=SKIPPED_OPERATIONAL_OPEN_COUPON,
        no_real_bet_execution_verdict=no_real_bet_execution_verdict,
        no_betclic_execution_verdict=no_betclic_execution_verdict,
        protected_repo_write_verdict=protected_repo_write_verdict,
        ready_for_manual_low_stake_pilot=ready_for_manual_low_stake_pilot,
        ready_for_production_execution=False,
        blockers=blockers,
    )
