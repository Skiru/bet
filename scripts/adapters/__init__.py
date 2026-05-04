"""Adapters package for scan_events.py

This module exposes a domain -> parser mapping. Each adapter must provide
`parse(html: str, url: str) -> List[Dict]`.
"""
from .raw_adapter import parse as raw_parse
from .flashscore_adapter import parse as flashscore_parse
from .sofascore_adapter import parse as sofascore_parse
from .oddsportal_adapter import parse as oddsportal_parse
from .betclic_adapter import parse as betclic_parse
from .betexplorer_adapter import parse as betexplorer_parse
from .soccerway_adapter import parse as soccerway_parse
from .tennisexplorer_adapter import parse as tennisexplorer_parse
from .soccerstats_adapter import parse as soccerstats_parse
from .forebet_adapter import parse as forebet_parse
from .totalcorner_adapter import parse as totalcorner_parse
from .tennisabstract_adapter import parse as tennisabstract_parse
from .scores24_adapter import parse as scores24_parse
from .whoscored_adapter import parse as whoscored_parse
from .basketball_reference_adapter import parse as basketball_reference_parse
from .hockey_reference_adapter import parse as hockey_reference_parse
from .covers_adapter import parse as covers_parse
from .hltv_adapter import parse as hltv_parse


def dedup_results(results, key_fn=None):
    """Deduplicate adapter results by a key function.

    Default key: (home, away, time). Pass a custom key_fn for different dedup logic.
    """
    if key_fn is None:
        key_fn = lambda r: (r.get("home"), r.get("away"), r.get("time"))
    seen = set()
    dedup = []
    for r in results:
        k = key_fn(r)
        if k in seen:
            continue
        seen.add(k)
        dedup.append(r)
    return dedup

# Domain-specific adapters (optional). If an adapter for a domain is not
# present, `raw_parse` will be used as a fallback.
ADAPTERS = {
    "forebet.com": forebet_parse,
    "protipster.com": raw_parse,
    "predictz.com": raw_parse,
    "bettingexpert.com": raw_parse,
    "zawodtyper.pl": raw_parse,
    "oddspedia.com": raw_parse,
    "betexplorer.com": betexplorer_parse,
    "covers.com": covers_parse,
    "teamrankings.com": raw_parse,
    "tennisabstract.com": tennisabstract_parse,
    "sportsgambler.com": raw_parse,
    "sportytrader.com": raw_parse,
    "flashscore.com": flashscore_parse,
    "sofascore.com": sofascore_parse,
    "oddsportal.com": oddsportal_parse,
    "betclic.pl": betclic_parse,
    "betclic.com": betclic_parse,
    "soccerway.com": soccerway_parse,
    "tennisexplorer.com": tennisexplorer_parse,
    "soccerstats.com": soccerstats_parse,
    "totalcorner.com": totalcorner_parse,
    "scores24.live": scores24_parse,
    "hltv.org": hltv_parse,
    "atptour.com": raw_parse,
    "betaminic.com": raw_parse,
    "whoscored.com": whoscored_parse,
    "basketball-reference.com": basketball_reference_parse,
    "hockey-reference.com": hockey_reference_parse,
}


def get_adapter(domain: str):
    return ADAPTERS.get(domain, raw_parse)


