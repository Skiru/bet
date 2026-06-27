"""Manual low-stake pilot guard for human-performed bookmaker placement."""
from __future__ import annotations

import json
from dataclasses import dataclass, fields, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from bet.pipeline.full_shadow_acceptance import (
    compare_path_snapshots,
    is_protected_repo_path,
    snapshot_protected_repo_paths,
)
from bet.pipeline.paper_trading import OPEN_STATUS as PAPER_OPEN_STATUS
from bet.pipeline.paper_trading import load_latest_paper_coupons
from bet.pipeline.run_evidence import utc_now_iso
from bet.pipeline.runtime_modes import RuntimeMode, parse_runtime_mode


TASK_ID = "PIPELINE_MANUAL_LOW_STAKE_PILOT_A"
REPO_ROOT = Path(__file__).resolve().parents[3]
ZERO = Decimal("0")
PREPARED_STATUS = "PREPARED"
MANUALLY_PLACED_STATUS = "MANUALLY_PLACED"
SETTLED_WIN_STATUS = "SETTLED_WIN"
SETTLED_LOSS_STATUS = "SETTLED_LOSS"
VOID_STATUS = "VOID"
CANCELLED_STATUS = "CANCELLED"
OPEN_MANUAL_STATUSES = {PREPARED_STATUS, MANUALLY_PLACED_STATUS}
FINAL_MANUAL_STATUSES = {SETTLED_WIN_STATUS, SETTLED_LOSS_STATUS, VOID_STATUS, CANCELLED_STATUS}
ALL_MANUAL_STATUSES = OPEN_MANUAL_STATUSES | FINAL_MANUAL_STATUSES
LEDGER_EVENT_PREPARED = "manual_coupon_prepared"
LEDGER_EVENT_PLACED = "manual_coupon_placed"
LEDGER_EVENT_SETTLED = "manual_coupon_settled"
LEDGER_EVENT_TYPES = {LEDGER_EVENT_PREPARED, LEDGER_EVENT_PLACED, LEDGER_EVENT_SETTLED}


def _to_decimal(value: Decimal | int | float | str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
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


def _status_from_result(result: str) -> str:
    normalized = str(result).strip().upper()
    mapping = {
        "WIN": SETTLED_WIN_STATUS,
        "LOSS": SETTLED_LOSS_STATUS,
        "VOID": VOID_STATUS,
    }
    if normalized not in mapping:
        raise ValueError(f"result must be one of {sorted(mapping)}")
    return mapping[normalized]


def _manual_coupon_id(config: "ManualLowStakePilotConfig", source_paper_coupon_id: str) -> str:
    return f"{config.run_id}:manual:{source_paper_coupon_id}"


@dataclass(frozen=True)
class ManualLowStakePilotConfig:
    base_dir: Path
    betting_day: str
    run_id: str
    pilot_dir: Path
    ledger_path: Path
    runtime_mode: str = "DRY_RUN"
    max_manual_coupons_per_day: int = 1
    max_stake_units_per_coupon: Decimal = Decimal("1")
    max_daily_risk_units: Decimal = Decimal("1")
    daily_stop_loss_units: Decimal = Decimal("1")
    kill_switch: bool = False
    legal_operator_attested: bool = False
    age_kyc_attested: bool = False
    responsible_gambling_limits_attested: bool = False
    manual_click_attested: bool = False
    allow_automated_bookmaker_placement: bool = False
    allow_betclic_api: bool = False
    allow_browser_automation: bool = False
    allow_repo_protected_writes: bool = False

    def normalized(self) -> "ManualLowStakePilotConfig":
        return ManualLowStakePilotConfig(
            base_dir=Path(self.base_dir).resolve(strict=False),
            betting_day=self.betting_day,
            run_id=self.run_id,
            pilot_dir=Path(self.pilot_dir).resolve(strict=False),
            ledger_path=Path(self.ledger_path).resolve(strict=False),
            runtime_mode=parse_runtime_mode(self.runtime_mode).value,
            max_manual_coupons_per_day=int(self.max_manual_coupons_per_day),
            max_stake_units_per_coupon=_to_decimal(self.max_stake_units_per_coupon),
            max_daily_risk_units=_to_decimal(self.max_daily_risk_units),
            daily_stop_loss_units=_to_decimal(self.daily_stop_loss_units),
            kill_switch=self.kill_switch,
            legal_operator_attested=self.legal_operator_attested,
            age_kyc_attested=self.age_kyc_attested,
            responsible_gambling_limits_attested=self.responsible_gambling_limits_attested,
            manual_click_attested=self.manual_click_attested,
            allow_automated_bookmaker_placement=self.allow_automated_bookmaker_placement,
            allow_betclic_api=self.allow_betclic_api,
            allow_browser_automation=self.allow_browser_automation,
            allow_repo_protected_writes=self.allow_repo_protected_writes,
        )


@dataclass(frozen=True)
class ManualPilotCoupon:
    manual_pilot_coupon_id: str
    betting_day: str
    run_id: str
    source_paper_coupon_id: str
    source_s8_coupon_draft_path: str
    source_s8_coupon_draft_sha256: str
    source_s9_artifact_path: str
    source_s9_artifact_sha256: str
    source_paper_ledger_path: str
    selection_id: str
    event_id: str
    market: str
    pick: str
    odds_decimal: Decimal
    stake_units: Decimal
    expected_payout_units: Decimal
    created_at_utc: str
    manual_bookmaker_name: str
    manual_bookmaker_ticket_id: str
    manual_placed_at_utc: str
    status: str
    pnl_units: Decimal

    def to_jsonable(self) -> dict[str, Any]:
        return _serialize_jsonable({field.name: getattr(self, field.name) for field in fields(self)})


@dataclass(frozen=True)
class ManualLowStakePilotReport:
    task_id: str
    status: str
    betting_day: str
    run_id: str
    pilot_dir: str
    ledger_path: str
    manual_coupon_count: int
    max_manual_coupons_per_day: int
    total_stake_units: Decimal
    max_stake_units_per_coupon: Decimal
    max_daily_risk_units: Decimal
    daily_stop_loss_units: Decimal
    kill_switch_active: bool
    legal_operator_attestation_verdict: str
    age_kyc_attestation_verdict: str
    responsible_gambling_limits_verdict: str
    manual_click_required_verdict: str
    one_coupon_limit_verdict: str
    budget_guard_verdict: str
    stop_loss_guard_verdict: str
    duplicate_blocking_verdict: str
    ledger_schema_verdict: str
    manual_placement_recording_verdict: str
    settlement_verdict: str
    no_automated_bookmaker_placement_verdict: str
    no_betclic_api_verdict: str
    no_browser_automation_verdict: str
    protected_repo_write_verdict: str
    ready_for_controlled_manual_pilot: bool
    ready_for_production_execution: bool
    blockers: list[str]

    def to_jsonable(self) -> dict[str, Any]:
        return _serialize_jsonable({field.name: getattr(self, field.name) for field in fields(self)})


def _validate_common_config(
    config: ManualLowStakePilotConfig,
    *,
    report_path: Path | None = None,
    repo_root: Path = REPO_ROOT,
) -> list[str]:
    normalized = config.normalized()
    repo_root = Path(repo_root).resolve(strict=False)
    blockers: list[str] = []
    mode = parse_runtime_mode(normalized.runtime_mode)

    if mode == RuntimeMode.PRODUCTION:
        blockers.append("PRODUCTION mode is forbidden for manual low-stake pilot")
    if normalized.allow_automated_bookmaker_placement:
        blockers.append("automated bookmaker placement must remain disabled")
    if normalized.allow_betclic_api:
        blockers.append("Betclic API execution must remain disabled")
    if normalized.allow_browser_automation:
        blockers.append("browser automation must remain disabled")
    if normalized.allow_repo_protected_writes:
        blockers.append("repo protected writes must remain disabled")
    if normalized.kill_switch:
        blockers.append("kill_switch is active")

    for field_name, path in (
        ("base_dir", normalized.base_dir),
        ("pilot_dir", normalized.pilot_dir),
        ("ledger_path", normalized.ledger_path),
    ):
        if _path_is_within(path, repo_root):
            blockers.append(f"{field_name} must be outside repo root: {path}")
        if is_protected_repo_path(path, repo_root):
            blockers.append(f"{field_name} cannot be under protected repo-local paths: {path}")

    if report_path is not None:
        resolved_report_path = Path(report_path).resolve(strict=False)
        if _path_is_within(resolved_report_path, repo_root):
            blockers.append(f"report_path must be outside repo root: {resolved_report_path}")
        if is_protected_repo_path(resolved_report_path, repo_root):
            blockers.append(f"report_path cannot be under protected repo-local paths: {resolved_report_path}")

    if not _path_is_within(normalized.pilot_dir, normalized.base_dir):
        blockers.append("pilot_dir must be within base_dir")
    if not _path_is_within(normalized.ledger_path, normalized.pilot_dir):
        blockers.append("ledger_path must be within pilot_dir")
    if normalized.max_manual_coupons_per_day <= 0:
        blockers.append("max_manual_coupons_per_day must be > 0")
    if normalized.max_stake_units_per_coupon <= ZERO:
        blockers.append("max_stake_units_per_coupon must be > 0")
    if normalized.max_daily_risk_units <= ZERO:
        blockers.append("max_daily_risk_units must be > 0")
    if normalized.daily_stop_loss_units <= ZERO:
        blockers.append("daily_stop_loss_units must be > 0")
    if normalized.max_stake_units_per_coupon > normalized.max_daily_risk_units:
        blockers.append("max_stake_units_per_coupon cannot exceed max_daily_risk_units")

    return blockers


def validate_manual_low_stake_pilot_config(
    config: ManualLowStakePilotConfig,
    *,
    report_path: Path | None = None,
    repo_root: Path = REPO_ROOT,
) -> list[str]:
    blockers = _validate_common_config(config, report_path=report_path, repo_root=repo_root)
    normalized = config.normalized()
    if not normalized.legal_operator_attested:
        blockers.append("legal_operator_attested must be true")
    if not normalized.age_kyc_attested:
        blockers.append("age_kyc_attested must be true")
    if not normalized.responsible_gambling_limits_attested:
        blockers.append("responsible_gambling_limits_attested must be true")
    if not normalized.manual_click_attested:
        blockers.append("manual_click_attested must be true")
    return blockers


def _validate_coupon_fields(coupon: ManualPilotCoupon, config: ManualLowStakePilotConfig) -> list[str]:
    issues: list[str] = []
    if coupon.betting_day != config.betting_day:
        issues.append("manual pilot coupon betting_day must match config")
    if coupon.run_id != config.run_id:
        issues.append("manual pilot coupon run_id must match config")
    for field_name in (
        "manual_pilot_coupon_id",
        "source_paper_coupon_id",
        "source_s8_coupon_draft_path",
        "source_s8_coupon_draft_sha256",
        "source_s9_artifact_path",
        "source_s9_artifact_sha256",
        "source_paper_ledger_path",
        "selection_id",
        "event_id",
        "market",
        "pick",
        "created_at_utc",
        "manual_bookmaker_name",
    ):
        if not str(getattr(coupon, field_name)).strip():
            issues.append(f"{field_name} must be non-empty")

    if coupon.status not in ALL_MANUAL_STATUSES:
        issues.append(f"status must be one of {sorted(ALL_MANUAL_STATUSES)}")
    if coupon.stake_units <= ZERO:
        issues.append("stake_units must be > 0")
    if coupon.odds_decimal <= Decimal("1"):
        issues.append("odds_decimal must be > 1")
    if coupon.expected_payout_units != coupon.stake_units * coupon.odds_decimal:
        issues.append("expected_payout_units must equal stake_units * odds_decimal")

    if coupon.status == PREPARED_STATUS:
        if coupon.manual_bookmaker_ticket_id:
            issues.append("manual_bookmaker_ticket_id must be empty before placement")
        if coupon.manual_placed_at_utc:
            issues.append("manual_placed_at_utc must be empty before placement")
        if coupon.pnl_units != ZERO:
            issues.append("pnl_units must be 0 before placement")
    elif coupon.status == MANUALLY_PLACED_STATUS:
        if not coupon.manual_bookmaker_ticket_id.strip():
            issues.append("manual_bookmaker_ticket_id must be non-empty after placement")
        if not coupon.manual_placed_at_utc.strip():
            issues.append("manual_placed_at_utc must be non-empty after placement")
        if coupon.pnl_units != ZERO:
            issues.append("pnl_units must be 0 for placed coupons")
    elif coupon.status == SETTLED_WIN_STATUS:
        if coupon.pnl_units != coupon.stake_units * (coupon.odds_decimal - Decimal("1")):
            issues.append("WIN pnl_units must equal stake_units * (odds_decimal - 1)")
    elif coupon.status == SETTLED_LOSS_STATUS:
        if coupon.pnl_units != -coupon.stake_units:
            issues.append("LOSS pnl_units must equal -stake_units")
    else:
        if coupon.pnl_units != ZERO:
            issues.append(f"{coupon.status} pnl_units must equal 0")

    if coupon.status in {MANUALLY_PLACED_STATUS, SETTLED_WIN_STATUS, SETTLED_LOSS_STATUS, VOID_STATUS}:
        if not coupon.manual_bookmaker_ticket_id.strip():
            issues.append("manual_bookmaker_ticket_id must be non-empty once placement is recorded")
        if not coupon.manual_placed_at_utc.strip():
            issues.append("manual_placed_at_utc must be non-empty once placement is recorded")

    return issues


def _coupon_from_jsonable(raw: dict[str, Any]) -> ManualPilotCoupon:
    return ManualPilotCoupon(
        manual_pilot_coupon_id=str(raw["manual_pilot_coupon_id"]),
        betting_day=str(raw["betting_day"]),
        run_id=str(raw["run_id"]),
        source_paper_coupon_id=str(raw["source_paper_coupon_id"]),
        source_s8_coupon_draft_path=str(raw["source_s8_coupon_draft_path"]),
        source_s8_coupon_draft_sha256=str(raw["source_s8_coupon_draft_sha256"]),
        source_s9_artifact_path=str(raw["source_s9_artifact_path"]),
        source_s9_artifact_sha256=str(raw["source_s9_artifact_sha256"]),
        source_paper_ledger_path=str(raw["source_paper_ledger_path"]),
        selection_id=str(raw["selection_id"]),
        event_id=str(raw["event_id"]),
        market=str(raw["market"]),
        pick=str(raw["pick"]),
        odds_decimal=_to_decimal(raw["odds_decimal"]),
        stake_units=_to_decimal(raw["stake_units"]),
        expected_payout_units=_to_decimal(raw["expected_payout_units"]),
        created_at_utc=str(raw["created_at_utc"]),
        manual_bookmaker_name=str(raw["manual_bookmaker_name"]),
        manual_bookmaker_ticket_id=str(raw.get("manual_bookmaker_ticket_id", "")),
        manual_placed_at_utc=str(raw.get("manual_placed_at_utc", "")),
        status=str(raw["status"]),
        pnl_units=_to_decimal(raw["pnl_units"]),
    )


def _ledger_event(event_type: str, coupon: ManualPilotCoupon) -> dict[str, Any]:
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


def _coupon_identity(existing: ManualPilotCoupon) -> tuple[Any, ...]:
    return (
        existing.manual_pilot_coupon_id,
        existing.betting_day,
        existing.run_id,
        existing.source_paper_coupon_id,
        existing.source_s8_coupon_draft_path,
        existing.source_s8_coupon_draft_sha256,
        existing.source_s9_artifact_path,
        existing.source_s9_artifact_sha256,
        existing.source_paper_ledger_path,
        existing.selection_id,
        existing.event_id,
        existing.market,
        existing.pick,
        existing.odds_decimal,
        existing.stake_units,
        existing.expected_payout_units,
        existing.created_at_utc,
    )


def load_latest_manual_pilot_coupons(ledger_path: Path) -> dict[str, ManualPilotCoupon]:
    coupons: dict[str, ManualPilotCoupon] = {}
    for line_number, event in enumerate(read_ledger_events(ledger_path), start=1):
        event_type = event.get("event_type")
        if event_type not in LEDGER_EVENT_TYPES:
            raise ValueError(f"Unsupported ledger event_type at line {line_number}: {event_type!r}")
        coupon_raw = event.get("coupon")
        if not isinstance(coupon_raw, dict):
            raise ValueError(f"Ledger event coupon must be an object at line {line_number}")
        coupon = _coupon_from_jsonable(coupon_raw)
        issues = _validate_coupon_fields(
            coupon,
            ManualLowStakePilotConfig(
                base_dir=Path(coupon.source_paper_ledger_path).parent,
                betting_day=coupon.betting_day,
                run_id=coupon.run_id,
                pilot_dir=Path(ledger_path).parent,
                ledger_path=Path(ledger_path),
                max_manual_coupons_per_day=999999,
                max_stake_units_per_coupon=Decimal("999999"),
                max_daily_risk_units=Decimal("999999"),
                daily_stop_loss_units=Decimal("999999"),
                legal_operator_attested=True,
                age_kyc_attested=True,
                responsible_gambling_limits_attested=True,
                manual_click_attested=True,
            ),
        )
        if issues:
            raise ValueError(f"Invalid coupon payload at line {line_number}: {'; '.join(issues)}")

        existing = coupons.get(coupon.manual_pilot_coupon_id)
        if event_type == LEDGER_EVENT_PREPARED:
            if existing is not None:
                raise ValueError(f"Duplicate manual_coupon_prepared for {coupon.manual_pilot_coupon_id} at line {line_number}")
            if coupon.status != PREPARED_STATUS or coupon.pnl_units != ZERO:
                raise ValueError(f"manual_coupon_prepared must store PREPARED/0 state for {coupon.manual_pilot_coupon_id}")
            coupons[coupon.manual_pilot_coupon_id] = coupon
            continue

        if existing is None:
            raise ValueError(f"{event_type} without prior prepare for {coupon.manual_pilot_coupon_id}")
        if _coupon_identity(existing) != _coupon_identity(coupon):
            raise ValueError(f"Immutable coupon fields changed for {coupon.manual_pilot_coupon_id} at line {line_number}")

        if event_type == LEDGER_EVENT_PLACED:
            if existing.status != PREPARED_STATUS:
                raise ValueError(f"manual_coupon_placed requires PREPARED state for {coupon.manual_pilot_coupon_id}")
            if coupon.status != MANUALLY_PLACED_STATUS:
                raise ValueError(f"manual_coupon_placed must store MANUALLY_PLACED state for {coupon.manual_pilot_coupon_id}")
            coupons[coupon.manual_pilot_coupon_id] = coupon
            continue

        if existing.status != MANUALLY_PLACED_STATUS:
            raise ValueError(f"manual_coupon_settled requires MANUALLY_PLACED state for {coupon.manual_pilot_coupon_id}")
        if coupon.status not in {SETTLED_WIN_STATUS, SETTLED_LOSS_STATUS, VOID_STATUS}:
            raise ValueError(f"manual_coupon_settled must store WIN/LOSS/VOID state for {coupon.manual_pilot_coupon_id}")
        if existing.manual_bookmaker_name != coupon.manual_bookmaker_name or existing.manual_bookmaker_ticket_id != coupon.manual_bookmaker_ticket_id or existing.manual_placed_at_utc != coupon.manual_placed_at_utc:
            raise ValueError(f"Placement metadata changed during settlement for {coupon.manual_pilot_coupon_id}")
        coupons[coupon.manual_pilot_coupon_id] = coupon

    return coupons


def validate_ledger_jsonl_schema(ledger_path: Path) -> list[str]:
    issues: list[str] = []
    try:
        load_latest_manual_pilot_coupons(ledger_path)
    except ValueError as exc:
        issues.append(str(exc))
    return issues


def _daily_coupons(coupons: dict[str, ManualPilotCoupon], betting_day: str) -> list[ManualPilotCoupon]:
    return [coupon for coupon in coupons.values() if coupon.betting_day == betting_day]


def open_daily_risk_units(ledger_path: Path, *, betting_day: str | None = None) -> Decimal:
    coupons = load_latest_manual_pilot_coupons(ledger_path)
    if betting_day is not None:
        filtered = _daily_coupons(coupons, betting_day)
    else:
        filtered = list(coupons.values())
    return sum((coupon.stake_units for coupon in filtered if coupon.status in OPEN_MANUAL_STATUSES), start=ZERO)


def realized_loss_units(ledger_path: Path, *, betting_day: str | None = None) -> Decimal:
    coupons = load_latest_manual_pilot_coupons(ledger_path)
    if betting_day is not None:
        filtered = _daily_coupons(coupons, betting_day)
    else:
        filtered = list(coupons.values())
    return sum((-coupon.pnl_units for coupon in filtered if coupon.pnl_units < ZERO), start=ZERO)


def _stop_loss_exposure_units(coupons: list[ManualPilotCoupon]) -> Decimal:
    open_risk = sum((coupon.stake_units for coupon in coupons if coupon.status in OPEN_MANUAL_STATUSES), start=ZERO)
    realized_losses = sum((-coupon.pnl_units for coupon in coupons if coupon.pnl_units < ZERO), start=ZERO)
    return open_risk + realized_losses


def _report_verdict(flag: bool) -> str:
    return "PASS" if flag else "FAIL"


def _load_open_paper_coupon(paper_ledger_path: Path, source_paper_coupon_id: str):
    latest = load_latest_paper_coupons(Path(paper_ledger_path))
    source_coupon = latest.get(source_paper_coupon_id)
    if source_coupon is None:
        raise ValueError(f"paper coupon not found: {source_paper_coupon_id}")
    if source_coupon.status != PAPER_OPEN_STATUS:
        raise ValueError(f"paper coupon must be OPEN: {source_paper_coupon_id}")
    if not source_coupon.source_s8_coupon_draft_path or not source_coupon.source_s8_coupon_draft_sha256:
        raise ValueError("paper coupon must include bound S8 metadata")
    if not source_coupon.source_s9_artifact_path or not source_coupon.source_s9_artifact_sha256:
        raise ValueError("paper coupon must include bound S9 metadata")
    return source_coupon


def prepare_manual_pilot_from_paper_coupon(
    *,
    config: ManualLowStakePilotConfig,
    paper_ledger_path: Path,
    source_paper_coupon_id: str,
    manual_bookmaker_name: str,
) -> ManualPilotCoupon:
    normalized = config.normalized()
    blockers = validate_manual_low_stake_pilot_config(normalized)
    if blockers:
        raise ValueError("; ".join(blockers))

    if not str(manual_bookmaker_name).strip():
        raise ValueError("manual_bookmaker_name must be non-empty")

    ledger_path = normalized.ledger_path
    existing = load_latest_manual_pilot_coupons(ledger_path)
    manual_pilot_coupon_id = _manual_coupon_id(normalized, source_paper_coupon_id)
    if manual_pilot_coupon_id in existing:
        raise ValueError(f"duplicate manual_pilot_coupon_id blocked: {manual_pilot_coupon_id}")

    daily_coupons = _daily_coupons(existing, normalized.betting_day)
    if len(daily_coupons) >= normalized.max_manual_coupons_per_day:
        raise ValueError("manual coupon would exceed max_manual_coupons_per_day")

    source_coupon = _load_open_paper_coupon(Path(paper_ledger_path), source_paper_coupon_id)
    if source_coupon.stake_units > normalized.max_stake_units_per_coupon:
        raise ValueError("stake_units exceeds max_stake_units_per_coupon")

    open_risk = sum((coupon.stake_units for coupon in daily_coupons if coupon.status in OPEN_MANUAL_STATUSES), start=ZERO)
    if open_risk + source_coupon.stake_units > normalized.max_daily_risk_units:
        raise ValueError("coupon would exceed max_daily_risk_units")

    stop_loss_exposure = _stop_loss_exposure_units(daily_coupons)
    if stop_loss_exposure + source_coupon.stake_units > normalized.daily_stop_loss_units:
        raise ValueError("coupon would exceed daily_stop_loss_units")

    prepared = ManualPilotCoupon(
        manual_pilot_coupon_id=manual_pilot_coupon_id,
        betting_day=normalized.betting_day,
        run_id=normalized.run_id,
        source_paper_coupon_id=source_coupon.paper_coupon_id,
        source_s8_coupon_draft_path=source_coupon.source_s8_coupon_draft_path,
        source_s8_coupon_draft_sha256=source_coupon.source_s8_coupon_draft_sha256,
        source_s9_artifact_path=str(source_coupon.source_s9_artifact_path),
        source_s9_artifact_sha256=str(source_coupon.source_s9_artifact_sha256),
        source_paper_ledger_path=str(Path(paper_ledger_path).resolve(strict=False)),
        selection_id=source_coupon.selection_id,
        event_id=source_coupon.event_id,
        market=source_coupon.market,
        pick=source_coupon.pick,
        odds_decimal=source_coupon.odds_decimal,
        stake_units=source_coupon.stake_units,
        expected_payout_units=source_coupon.stake_units * source_coupon.odds_decimal,
        created_at_utc=utc_now_iso(),
        manual_bookmaker_name=str(manual_bookmaker_name).strip(),
        manual_bookmaker_ticket_id="",
        manual_placed_at_utc="",
        status=PREPARED_STATUS,
        pnl_units=ZERO,
    )
    issues = _validate_coupon_fields(prepared, normalized)
    if issues:
        raise ValueError("; ".join(issues))

    _append_ledger_event(ledger_path, _ledger_event(LEDGER_EVENT_PREPARED, prepared))
    return prepared


def record_manual_bookmaker_placement(
    *,
    config: ManualLowStakePilotConfig,
    manual_pilot_coupon_id: str,
    manual_bookmaker_name: str,
    manual_bookmaker_ticket_id: str,
    manual_placed_at_utc: str,
) -> ManualPilotCoupon:
    normalized = config.normalized()
    blockers = _validate_common_config(normalized)
    if blockers:
        raise ValueError("; ".join(blockers))
    if not normalized.manual_click_attested:
        raise ValueError("manual_click_attested must be true")
    if not str(manual_bookmaker_name).strip():
        raise ValueError("manual_bookmaker_name must be non-empty")
    if not str(manual_bookmaker_ticket_id).strip():
        raise ValueError("manual_bookmaker_ticket_id must be non-empty")
    if not str(manual_placed_at_utc).strip():
        raise ValueError("manual_placed_at_utc must be non-empty")

    latest = load_latest_manual_pilot_coupons(normalized.ledger_path)
    current = latest.get(manual_pilot_coupon_id)
    if current is None:
        raise ValueError(f"manual pilot coupon not found: {manual_pilot_coupon_id}")
    if current.status != PREPARED_STATUS:
        raise ValueError(f"manual pilot coupon not in PREPARED state: {manual_pilot_coupon_id}")

    placed = replace(
        current,
        manual_bookmaker_name=str(manual_bookmaker_name).strip(),
        manual_bookmaker_ticket_id=str(manual_bookmaker_ticket_id).strip(),
        manual_placed_at_utc=str(manual_placed_at_utc).strip(),
        status=MANUALLY_PLACED_STATUS,
        pnl_units=ZERO,
    )
    issues = _validate_coupon_fields(placed, normalized)
    if issues:
        raise ValueError("; ".join(issues))

    _append_ledger_event(normalized.ledger_path, _ledger_event(LEDGER_EVENT_PLACED, placed))
    return placed


def settle_manual_pilot_coupon(
    *,
    config: ManualLowStakePilotConfig,
    manual_pilot_coupon_id: str,
    result: str,
) -> ManualPilotCoupon:
    normalized = config.normalized()
    blockers = _validate_common_config(normalized)
    if blockers:
        raise ValueError("; ".join(blockers))

    latest = load_latest_manual_pilot_coupons(normalized.ledger_path)
    current = latest.get(manual_pilot_coupon_id)
    if current is None:
        raise ValueError(f"manual pilot coupon not found: {manual_pilot_coupon_id}")
    if current.status != MANUALLY_PLACED_STATUS:
        raise ValueError(f"manual pilot coupon not in MANUALLY_PLACED state: {manual_pilot_coupon_id}")

    result_status = _status_from_result(result)
    if result_status == SETTLED_WIN_STATUS:
        pnl_units = current.stake_units * (current.odds_decimal - Decimal("1"))
    elif result_status == SETTLED_LOSS_STATUS:
        pnl_units = -current.stake_units
    else:
        pnl_units = ZERO

    settled = replace(current, status=result_status, pnl_units=pnl_units)
    issues = _validate_coupon_fields(settled, normalized)
    if issues:
        raise ValueError("; ".join(issues))

    _append_ledger_event(normalized.ledger_path, _ledger_event(LEDGER_EVENT_SETTLED, settled))
    return settled


def build_manual_low_stake_pilot_report(
    config: ManualLowStakePilotConfig,
    *,
    task_id: str = TASK_ID,
    report_path: Path | None = None,
    repo_root: Path = REPO_ROOT,
    protected_changes: list[str] | None = None,
) -> ManualLowStakePilotReport:
    normalized = config.normalized()
    common_blockers = _validate_common_config(normalized, report_path=report_path, repo_root=repo_root)
    coupons = load_latest_manual_pilot_coupons(normalized.ledger_path)
    daily_coupons = _daily_coupons(coupons, normalized.betting_day)
    manual_coupon_count = len(daily_coupons)
    total_stake_units = sum((coupon.stake_units for coupon in daily_coupons), start=ZERO)
    open_risk_units = sum((coupon.stake_units for coupon in daily_coupons if coupon.status in OPEN_MANUAL_STATUSES), start=ZERO)
    stop_loss_exposure = _stop_loss_exposure_units(daily_coupons)
    ledger_schema_issues = validate_ledger_jsonl_schema(normalized.ledger_path)

    attestation_proven_by_existing_coupon = manual_coupon_count > 0
    legal_operator_attestation_verdict = _report_verdict(
        normalized.legal_operator_attested or attestation_proven_by_existing_coupon
    )
    age_kyc_attestation_verdict = _report_verdict(
        normalized.age_kyc_attested or attestation_proven_by_existing_coupon
    )
    responsible_gambling_limits_verdict = _report_verdict(
        normalized.responsible_gambling_limits_attested or attestation_proven_by_existing_coupon
    )
    manual_click_required_verdict = _report_verdict(
        normalized.manual_click_attested or any(coupon.status != PREPARED_STATUS for coupon in daily_coupons)
    )
    one_coupon_limit_verdict = _report_verdict(manual_coupon_count <= normalized.max_manual_coupons_per_day)
    budget_guard_verdict = _report_verdict(
        all(coupon.stake_units <= normalized.max_stake_units_per_coupon for coupon in daily_coupons)
        and open_risk_units <= normalized.max_daily_risk_units
    )
    stop_loss_guard_verdict = _report_verdict(stop_loss_exposure <= normalized.daily_stop_loss_units)
    duplicate_blocking_verdict = _report_verdict(len({coupon.manual_pilot_coupon_id for coupon in daily_coupons}) == manual_coupon_count)
    ledger_schema_verdict = _report_verdict(not ledger_schema_issues)
    manual_placement_recording_verdict = _report_verdict(
        all(
            coupon.status == PREPARED_STATUS
            or (coupon.manual_bookmaker_ticket_id.strip() and coupon.manual_placed_at_utc.strip())
            for coupon in daily_coupons
        )
    )
    settlement_verdict = _report_verdict(
        all(
            (
                coupon.status == SETTLED_WIN_STATUS
                and coupon.pnl_units == coupon.stake_units * (coupon.odds_decimal - Decimal("1"))
            )
            or (coupon.status == SETTLED_LOSS_STATUS and coupon.pnl_units == -coupon.stake_units)
            or (coupon.status in {VOID_STATUS, CANCELLED_STATUS} and coupon.pnl_units == ZERO)
            or (coupon.status in OPEN_MANUAL_STATUSES and coupon.pnl_units == ZERO)
            for coupon in daily_coupons
        )
    )
    no_automated_bookmaker_placement_verdict = _report_verdict(not normalized.allow_automated_bookmaker_placement)
    no_betclic_api_verdict = _report_verdict(not normalized.allow_betclic_api)
    no_browser_automation_verdict = _report_verdict(not normalized.allow_browser_automation)
    protected_repo_write_verdict = _report_verdict(not protected_changes)

    blockers = list(common_blockers)
    if legal_operator_attestation_verdict == "FAIL":
        blockers.append("legal operator attestation missing")
    if age_kyc_attestation_verdict == "FAIL":
        blockers.append("age/KYC attestation missing")
    if responsible_gambling_limits_verdict == "FAIL":
        blockers.append("responsible gambling limits attestation missing")
    if manual_click_required_verdict == "FAIL":
        blockers.append("manual click attestation missing")
    if one_coupon_limit_verdict == "FAIL":
        blockers.append("manual coupon count exceeds max_manual_coupons_per_day")
    if budget_guard_verdict == "FAIL":
        blockers.append("manual coupon budget guard failed")
    if stop_loss_guard_verdict == "FAIL":
        blockers.append("daily stop-loss guard failed")
    if duplicate_blocking_verdict == "FAIL":
        blockers.append("duplicate manual pilot coupon IDs detected")
    blockers.extend(ledger_schema_issues)
    if manual_placement_recording_verdict == "FAIL":
        blockers.append("manual placement recording is incomplete")
    if settlement_verdict == "FAIL":
        blockers.append("settlement PnL math failed")
    if protected_changes:
        blockers.extend(protected_changes)

    ready_for_controlled_manual_pilot = not blockers
    status = "PASS" if ready_for_controlled_manual_pilot else "BLOCKED_MANUAL_LOW_STAKE_PILOT"
    return ManualLowStakePilotReport(
        task_id=task_id,
        status=status,
        betting_day=normalized.betting_day,
        run_id=normalized.run_id,
        pilot_dir=str(normalized.pilot_dir),
        ledger_path=str(normalized.ledger_path),
        manual_coupon_count=manual_coupon_count,
        max_manual_coupons_per_day=normalized.max_manual_coupons_per_day,
        total_stake_units=total_stake_units,
        max_stake_units_per_coupon=normalized.max_stake_units_per_coupon,
        max_daily_risk_units=normalized.max_daily_risk_units,
        daily_stop_loss_units=normalized.daily_stop_loss_units,
        kill_switch_active=normalized.kill_switch,
        legal_operator_attestation_verdict=legal_operator_attestation_verdict,
        age_kyc_attestation_verdict=age_kyc_attestation_verdict,
        responsible_gambling_limits_verdict=responsible_gambling_limits_verdict,
        manual_click_required_verdict=manual_click_required_verdict,
        one_coupon_limit_verdict=one_coupon_limit_verdict,
        budget_guard_verdict=budget_guard_verdict,
        stop_loss_guard_verdict=stop_loss_guard_verdict,
        duplicate_blocking_verdict=duplicate_blocking_verdict,
        ledger_schema_verdict=ledger_schema_verdict,
        manual_placement_recording_verdict=manual_placement_recording_verdict,
        settlement_verdict=settlement_verdict,
        no_automated_bookmaker_placement_verdict=no_automated_bookmaker_placement_verdict,
        no_betclic_api_verdict=no_betclic_api_verdict,
        no_browser_automation_verdict=no_browser_automation_verdict,
        protected_repo_write_verdict=protected_repo_write_verdict,
        ready_for_controlled_manual_pilot=ready_for_controlled_manual_pilot,
        ready_for_production_execution=False,
        blockers=blockers,
    )


def execute_with_report(
    *,
    config: ManualLowStakePilotConfig,
    report_path: Path,
    operation,
    repo_root: Path = REPO_ROOT,
):
    before_snapshot = snapshot_protected_repo_paths(repo_root)
    result = operation()
    after_snapshot = snapshot_protected_repo_paths(repo_root)
    protected_changes = compare_path_snapshots(before_snapshot, after_snapshot)
    report = build_manual_low_stake_pilot_report(
        config,
        report_path=report_path,
        repo_root=repo_root,
        protected_changes=protected_changes,
    )
    return result, report
