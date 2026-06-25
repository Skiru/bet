"""Canonical S2 tipster source definitions."""
from __future__ import annotations

from bet.pipeline.tipster_contracts import TipsterSourceContract


TIPSTER_SOURCE_CONTRACTS: tuple[TipsterSourceContract, ...] = (
    TipsterSourceContract("ZawodTyper", "zawodtyper", "playwright_xhr", "pl", ("football", "tennis", "basketball", "volleyball", "hockey"), True, wait_after_load_ms=3000),
    TipsterSourceContract("Typersi", "typersi", "playwright_dom", "pl", ("football", "tennis", "basketball", "volleyball", "hockey"), False, wait_after_load_ms=3000),
    TipsterSourceContract("Sportsgambler", "sportsgambler", "http_html", "en", ("football", "tennis", "basketball", "hockey", "volleyball"), False, wait_after_load_ms=0),
    TipsterSourceContract("PicksWise", "pickswise", "playwright_dom", "en", ("football", "tennis", "basketball", "hockey", "volleyball"), True, wait_after_load_ms=3000),
    TipsterSourceContract("BetIdeas", "betideas", "playwright_dom", "en", ("football", "tennis", "basketball", "hockey", "volleyball"), True, wait_after_load_ms=6000),
    TipsterSourceContract("Feedinco", "feedinco", "http_html", "en", ("football", "tennis", "basketball", "volleyball", "hockey"), False, wait_after_load_ms=0),
    TipsterSourceContract("BettingClosed", "bettingclosed", "http_html", "en", ("football", "tennis", "basketball", "volleyball", "hockey"), False, wait_after_load_ms=0),
)


def tipster_site_configs() -> list[dict[str, object]]:
    urls_by_name: dict[str, dict[str, object]] = {
        "ZawodTyper": {"url_template": "https://www.zawodtyper.pl/typy-dnia-{day}-{month}-{weekday}/", "url_builder": "zawodtyper"},
        "Typersi": {"url": "https://typersi.pl/"},
        "Sportsgambler": {"url": "https://www.sportsgambler.com/predictions/today/"},
        "PicksWise": {"urls": [
            "https://www.pickswise.com/soccer/predictions/",
            "https://www.pickswise.com/tennis/predictions/",
            "https://www.pickswise.com/nba/predictions/",
            "https://www.pickswise.com/nhl/predictions/",
            "https://www.pickswise.com/volleyball/predictions/",
        ]},
        "BetIdeas": {"urls": [
            "https://www.betideas.com/tips/football",
            "https://www.betideas.com/tips/tennis",
            "https://www.betideas.com/tips/basketball",
            "https://www.betideas.com/tips/hockey",
            "https://www.betideas.com/tips/volleyball",
        ]},
        "Feedinco": {"url": "https://www.feedinco.com/"},
        "BettingClosed": {"url": "https://www.bettingclosed.com/"},
    }
    configs: list[dict[str, object]] = []
    for contract in TIPSTER_SOURCE_CONTRACTS:
        config = {
            "name": contract.name,
            "parser": contract.parser,
            "language": contract.language,
            "sports": list(contract.sports),
            "accuracy_tracked": contract.accuracy_tracked,
            "wait_after_load": contract.wait_after_load_ms,
            "timeout_seconds": contract.timeout_seconds,
            **urls_by_name[contract.name],
        }
        configs.append(config)
    return configs


TIPSTER_SITES = tipster_site_configs()
