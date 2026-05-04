"""Simplified configuration loader for the betting system."""

import json
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "betting_config.json"


@dataclass
class BettingConfig:
    bankroll_pln: float
    daily_exposure_range: tuple[float, float]
    max_stake_pln: float
    max_legs_per_coupon: int  # Hard cap: 3
    min_coupons_per_day: int
    preferred_odds_range: tuple[float, float]
    min_safety_score: float  # Default: 0.60
    timezone: str
    sports: list[str]  # 7 sports only
    db_path: str

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "BettingConfig":
        """Load and validate configuration from JSON file."""
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)

        exposure = raw.get("daily_exposure_range", raw.get("suggested_daily_allocation_range_pln", [5.0, 15.0]))
        odds_range = raw.get("preferred_odds_range", [1.30, 3.50])

        config = cls(
            bankroll_pln=raw.get("bankroll_pln", raw.get("working_bankroll_pln", 50.0)),
            daily_exposure_range=(exposure[0], exposure[1]),
            max_stake_pln=raw.get("max_stake_pln", raw.get("higher_risk_coupon_max_stake_pln", 2.0)),
            max_legs_per_coupon=min(raw.get("max_legs_per_coupon", 3), 3),  # Hard cap
            min_coupons_per_day=raw.get("min_coupons_per_day", 3),
            preferred_odds_range=(odds_range[0], odds_range[1]),
            min_safety_score=raw.get("min_safety_score", 0.60),
            timezone=raw.get("timezone", "Europe/Warsaw"),
            sports=raw.get("sports", [
                "football", "volleyball", "basketball", "hockey",
                "tennis", "snooker", "speedway",
            ])[:7],
            db_path=raw.get("db_path", "betting/data/betting.db"),
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
