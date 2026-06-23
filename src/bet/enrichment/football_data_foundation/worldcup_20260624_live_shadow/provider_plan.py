from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

@dataclass(frozen=True)
class ProviderPlan:
    provider_key: str
    access_mode: str
    max_requests_per_fixture: int
    max_rps: float | None
    cache_subdir: str
    required: bool
    notes: Tuple[str, ...] = field(default_factory=tuple)

    def to_json(self) -> Dict[str, Any]:
        return {
            "provider_key": self.provider_key,
            "access_mode": self.access_mode,
            "max_requests_per_fixture": self.max_requests_per_fixture,
            "max_rps": self.max_rps,
            "cache_subdir": self.cache_subdir,
            "required": self.required,
            "notes": list(self.notes),
        }


def build_provider_plans() -> List[ProviderPlan]:
    return [
        ProviderPlan(
            provider_key="sportdb",
            access_mode="live_api_cache_then_replay",
            max_requests_per_fixture=8,
            max_rps=2.5,
            cache_subdir="sportdb",
            required=True,
            notes=(
                "Use dashboard-correct /api/flashscore routes",
                "Respect SportDB 2.5 RPS free limit",
            ),
        ),
        ProviderPlan(
            provider_key="highlightly",
            access_mode="live_api_cache_then_replay",
            max_requests_per_fixture=6,
            max_rps=1.0,
            cache_subdir="highlightly",
            required=True,
            notes=(
                "Use https://soccer.highlightly.net football API",
                "Match search first, detail endpoints after real ID",
            ),
        ),
        ProviderPlan(
            provider_key="api-football",
            access_mode="live_api_cache_then_replay",
            max_requests_per_fixture=6,
            max_rps=1.0,
            cache_subdir="api-football",
            required=True,
            notes=("Use existing API_FOOTBALL_KEY env mapping",),
        ),
        ProviderPlan(
            provider_key="football-data-org",
            access_mode="reference_api_cache_then_replay",
            max_requests_per_fixture=3,
            max_rps=1.0,
            cache_subdir="football-data-org",
            required=True,
            notes=("Reference/status/score only",),
        ),
        ProviderPlan(
            provider_key="espn-baseline",
            access_mode="public_reference_cache_then_replay",
            max_requests_per_fixture=3,
            max_rps=1.0,
            cache_subdir="espn-baseline",
            required=False,
            notes=("Unofficial shadow cross-check; no article/story/media text",),
        ),
    ]
