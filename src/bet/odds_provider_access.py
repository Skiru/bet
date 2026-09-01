"""Access gate policy for odds providers.

This module is intentionally side-effect free. It only evaluates env-controlled
access posture and never performs network calls or reads secret values.
"""

from __future__ import annotations

import os


# The literal is kept verbatim because reports and tests pin it, but the belief
# it encodes was disproven on 2026-09-01: ``/v4/fixtures`` does not fail access.
# The 403 that produced this name was ``RESTRICTED_ACCESS`` naming the
# *bookmaker* ``superbet.pl``. The gate's *effect* is still right, for a better
# reason -- this plan cannot serve superbet.pl at all, and the entitled
# ``superbet`` storefront prices 0.5-1.5% away from the book the operator bets
# into, so its quotes must never be selected as production odds.
#
# This gate governs OddsPapi as a **price source**. It deliberately does not
# govern ``bet.simple_stats.superbet_identity``, which reads ``/v4/fixtures``
# for Betradar ids and produces no price at all.
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
