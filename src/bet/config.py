"""Simplified configuration loader for the betting system."""

import json
from dataclasses import dataclass
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "betting_config.json"


@dataclass
class BettingConfig:
    bankroll_pln: float
    daily_exposure_range: tuple[float, float]
    max_stake_pln: float
    max_legs_per_coupon: int
    min_coupons_per_day: int
    min_safety_score: float
    timezone: str
    sports: list[str]
    db_path: str
    low_risk_coupon_max_stake_pln: float
    higher_risk_coupon_max_stake_pln: float
    min_legs_per_coupon: int
    max_same_sport_legs_in_coupon: int
    low_risk_price_gap_threshold_pct: float
    higher_risk_price_gap_threshold_pct: float
    max_core_coupons: int
    max_combo_coupons: int
    max_singles: int
    max_picks_per_day: int

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "BettingConfig":
        """Load and validate configuration from JSON file."""
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)

        exposure = raw.get("daily_exposure_range", raw.get("suggested_daily_allocation_range_pln", [5.0, 15.0]))

        config = cls(
            bankroll_pln=raw.get("bankroll_pln", raw.get("working_bankroll_pln", 50.0)),
            daily_exposure_range=(exposure[0], exposure[1]),
            max_stake_pln=raw.get("max_stake_pln", raw.get("higher_risk_coupon_max_stake_pln", 2.0)),
            max_legs_per_coupon=raw.get("max_legs_per_coupon", 4),
            min_coupons_per_day=raw.get("min_coupons_per_day", 3),
            min_safety_score=raw.get("min_safety_score", 0.4),
            timezone=raw.get("timezone", "Europe/Warsaw"),
            sports=raw.get("sports", [
                "football", "volleyball", "basketball", "tennis",
                "hockey", "snooker", "speedway", "baseball",
                "esports", "darts", "table_tennis", "handball",
                "mma", "padel",
            ]),
            db_path=raw.get("db_path", "betting/data/betting.db"),
            low_risk_coupon_max_stake_pln=raw.get("low_risk_coupon_max_stake_pln", 3.0),
            higher_risk_coupon_max_stake_pln=raw.get("higher_risk_coupon_max_stake_pln", 2.0),
            min_legs_per_coupon=raw.get("min_legs_per_coupon", 2),
            max_same_sport_legs_in_coupon=raw.get("max_same_sport_legs_in_coupon", 2),
            low_risk_price_gap_threshold_pct=raw.get("low_risk_price_gap_threshold_pct", -2.0),
            higher_risk_price_gap_threshold_pct=raw.get("higher_risk_price_gap_threshold_pct", -5.0),
            max_core_coupons=raw.get("max_core_coupons", 15),
            max_combo_coupons=raw.get("max_combo_coupons", 20),
            max_singles=raw.get("max_singles", 50),
            max_picks_per_day=raw.get("max_picks_per_day", 80),
        )

        # Validate
        if config.bankroll_pln <= 0:
            raise ValueError(f"bankroll_pln must be positive, got {config.bankroll_pln}")
        if config.daily_exposure_range[0] > config.daily_exposure_range[1]:
            raise ValueError(
                f"daily_exposure_range low ({config.daily_exposure_range[0]}) "
                f"> high ({config.daily_exposure_range[1]})"
            )
        if config.max_stake_pln <= 0:
            raise ValueError(f"max_stake_pln must be positive, got {config.max_stake_pln}")

        return config


def get_timezone() -> str:
    """Return configured timezone string. Falls back to Europe/Warsaw."""
    try:
        cfg = BettingConfig.load()
        return cfg.timezone
    except Exception:
        return "Europe/Warsaw"


def get_tz() -> ZoneInfo:
    """Return configured timezone as ZoneInfo object."""
    return ZoneInfo(get_timezone())
