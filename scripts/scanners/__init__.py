"""Scanner registry — maps sport groups to scanner classes."""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base_scanner import BaseSportScanner

SCANNER_REGISTRY: dict[str, type] = {}

# Maps individual sports to their scanner group
SPORT_TO_GROUP: dict[str, str] = {
    "football": "football",
    "tennis": "tennis",
    "basketball": "basketball",
    "volleyball": "volleyball",
    "hockey": "hockey",
}


def get_scanner(sport_group: str):
    """Get scanner instance for a sport group."""
    if sport_group not in SCANNER_REGISTRY:
        raise ValueError(f"No scanner registered for group: {sport_group}")
    return SCANNER_REGISTRY[sport_group]()


def get_all_scanners():
    """Get instances of all registered scanners."""
    return [cls() for cls in SCANNER_REGISTRY.values()]


def register_scanner(group: str, cls):
    """Register a scanner class for a sport group."""
    SCANNER_REGISTRY[group] = cls


# Import all scanner modules so they self-register
from . import football_scanner  # noqa: E402, F401
from . import tennis_scanner  # noqa: E402, F401
from . import basketball_scanner  # noqa: E402, F401
from . import volleyball_scanner  # noqa: E402, F401
from . import hockey_scanner  # noqa: E402, F401
