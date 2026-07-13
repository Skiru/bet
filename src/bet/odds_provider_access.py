"""Access gate policy for odds providers.

This module is intentionally side-effect free. It only evaluates env-controlled
access posture and never performs network calls or reads secret values.
"""

from __future__ import annotations

import os


ODDSPAPI_REASON = "disabled_by_access_gate_fail_access_fixtures"


def _flag_enabled(name: str) -> bool:
    return os.getenv(name, "").strip() == "1"


def _env_present(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def odds_source_access_status(source_name: str) -> dict[str, object]:
    source = source_name.strip()

    if source == "oddspapi":
        shadow_enabled = _flag_enabled("ODDSPAPI_ENABLE_SHADOW")
        live_enabled = _flag_enabled("ODDSPAPI_ENABLE_LIVE")
        live_certified = _flag_enabled("ODDSPAPI_LIVE_CERTIFIED")

        if live_enabled and live_certified:
            return {
                "source": source,
                "enabled": True,
                "production_selectable": True,
                "mode": "live",
                "reason": "live_enabled_certified",
            }

        if live_enabled and not live_certified:
            return {
                "source": source,
                "enabled": False,
                "production_selectable": False,
                "mode": "disabled",
                "reason": "live_requires_certification",
            }

        if shadow_enabled:
            return {
                "source": source,
                "enabled": True,
                "production_selectable": False,
                "mode": "shadow",
                "reason": "shadow_enabled_manual_only",
            }

        return {
            "source": source,
            "enabled": False,
            "production_selectable": False,
            "mode": "disabled",
            "reason": ODDSPAPI_REASON,
        }

    if source in {"the-odds-api", "odds-api-io", "api-football-odds"}:
        return {
            "source": source,
            "enabled": True,
            "production_selectable": True,
            "mode": "fallback",
            "reason": "existing_behavior_unchanged",
        }

    return {
        "source": source,
        "enabled": True,
        "production_selectable": True,
        "mode": "fallback",
        "reason": "unmanaged_source",
    }


def is_odds_source_enabled(source_name: str, *, mode: str = "scan") -> bool:
    del mode
    return bool(odds_source_access_status(source_name).get("enabled", False))
