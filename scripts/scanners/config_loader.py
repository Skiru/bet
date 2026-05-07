"""Load scan URLs config with backward-compat for old flat format."""
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "scan_urls.json"


def load_scan_config(path: Path | None = None) -> dict:
    """Load scan URLs config. Supports both new sport-grouped and legacy flat formats."""
    config_path = path or CONFIG_PATH
    data = json.loads(config_path.read_text(encoding="utf-8"))

    if "sports" in data:
        return data  # New format

    # Legacy flat format — return as-is for backward compat
    return {"_legacy_urls": data.get("urls", []), "sports": {}, "shared_sources": {}}


def get_urls_for_sport(config: dict, sport_group: str) -> list[str]:
    """Get URLs for a specific sport group from config."""
    if sport_group in config.get("sports", {}):
        return config["sports"][sport_group].get("urls", [])
    return []


def get_all_sport_groups(config: dict) -> list[str]:
    """Get all sport group names from config."""
    return list(config.get("sports", {}).keys())


def get_all_urls_flat(config: dict) -> list[str]:
    """Get all URLs from all sport groups as a flat list (for legacy mode)."""
    if config.get("_legacy_urls"):
        return config["_legacy_urls"]
    urls = []
    for sport_data in config.get("sports", {}).values():
        urls.extend(sport_data.get("urls", []))
    return urls
