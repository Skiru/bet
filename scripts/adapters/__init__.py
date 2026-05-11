"""Adapters package for scan_events.py

This module exposes a domain -> parser mapping. Each adapter must provide
`parse(html: str, url: str) -> List[Dict]`.
"""
import copy
import sys

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
    "atptour.com": raw_parse,
    "betaminic.com": raw_parse,
    "whoscored.com": whoscored_parse,
    "basketball-reference.com": basketball_reference_parse,
    "hockey-reference.com": hockey_reference_parse,
}


def get_adapter(domain: str):
    return ADAPTERS.get(domain, raw_parse)

ENRICHED_EVENT_DEFAULTS = {
    "home": None,
    "away": None,
    "time": None,
    "sport": None,
    "league": None,
    "source_url": None,
    "source_type": None,
    "match_id": None,
    "match_url": None,
    "score_home": None,
    "score_away": None,
    "period_scores": None,
    "status": None,
    "is_live": False,
    "country": None,
    "predictions": {
        "prob_home": None,
        "prob_draw": None,
        "prob_away": None,
        "predicted_winner": None,
        "predicted_score": None,
        "avg_stat": None
    },
    "odds": {
        "w1": None,
        "x": None,
        "w2": None,
        "total_lines": []
    },
    "corners": {
        "handicap": None,
        "home": None,
        "away": None
    },
    "form_home": [],
    "form_away": [],
    "h2h": [],
    "cards": {},
    "fouls": {},
    "shots": {},
    "raw": {}
}

def normalize_adapter_output(event: dict, source_type: str) -> dict:
    """Normalize event structure mapping legacy fields to standard schema."""
    try:
        normalized = {k: (copy.copy(v) if isinstance(v, (dict, list)) else v)
                      for k, v in ENRICHED_EVENT_DEFAULTS.items()}
        normalized["source_type"] = source_type
        
        # Legacy mapping
        if "home_team" in event and not event.get("home"):
            normalized["home"] = event["home_team"]
        if "away_team" in event and not event.get("away"):
            normalized["away"] = event["away_team"]
        if "kickoff" in event and not event.get("time"):
            normalized["time"] = event["kickoff"]
        if "competition" in event and not event.get("league"):
            normalized["league"] = event["competition"]
        
        if "source" in event and str(event["source"]).startswith("http") and not event.get("source_url"):
            normalized["source_url"] = event["source"]
        if "url" in event and not event.get("source_url"):
            normalized["source_url"] = event["url"]
            
        predictions = normalized["predictions"]
        if "forebet_probs" in event:
            fp = event["forebet_probs"]
            predictions["prob_home"] = fp.get("home") or fp.get("1")
            predictions["prob_draw"] = fp.get("draw") or fp.get("X")
            predictions["prob_away"] = fp.get("away") or fp.get("2")
        if "forebet_prediction" in event:
            predictions["predicted_winner"] = event["forebet_prediction"]
        if "forebet_score" in event:
            predictions["predicted_score"] = event["forebet_score"]
        if "forebet_avg" in event:
            predictions["avg_stat"] = event["forebet_avg"]
            
        corners = normalized["corners"]
        if "corner_handicap" in event:
            corners["handicap"] = event["corner_handicap"]
        if "corner_count" in event and isinstance(event["corner_count"], str) and "-" in event["corner_count"]:
            parts = event["corner_count"].split("-")
            corners["home"] = parts[0].strip()
            corners["away"] = parts[1].strip()
            
        odds = normalized["odds"]
        if "total_goals_line" in event:
            try:
                line = float(str(event["total_goals_line"]).split()[0])
                odds["total_lines"].append({"line": line})
            except Exception:
                pass
                
        if "odds" in event:
            if isinstance(event["odds"], list):
                if len(event["odds"]) >= 1: odds["w1"] = event["odds"][0]
                if len(event["odds"]) >= 2: 
                    if len(event["odds"]) == 2:
                        odds["w2"] = event["odds"][1]
                    else:
                        odds["x"] = event["odds"][1]
                        odds["w2"] = event["odds"][2]
            elif isinstance(event["odds"], dict):
                odds.update(event["odds"])
                
        if "consensus" in event and isinstance(event["consensus"], dict):
            # Try to map spread/total/moneyline into odds
            for k, v in event["consensus"].items():
                odds[k] = v
            
        if "sofascore_id" in event:
            normalized["match_id"] = event["sofascore_id"]
        if "detail_url" in event:
            normalized["match_url"] = event["detail_url"]
            
        # Copy direct standard fields (only if present and non-None — don't overwrite with empty)
        for field in ["home", "away", "time", "sport", "league", "source_url", "match_id", "match_url", 
                      "form_home", "form_away", "h2h", "cards", "fouls", "shots",
                      "score_home", "score_away", "period_scores", "status", "is_live", "country"]:
            if field in event and event[field] is not None:
                normalized[field] = event[field]
        # Merge predictions dict if adapter provides it
        if "predictions" in event and isinstance(event["predictions"], dict):
            for k, v in event["predictions"].items():
                if v is not None:
                    normalized["predictions"][k] = v
        if "corners" in event and isinstance(event["corners"], dict):
            normalized["corners"].update(event["corners"])
            
        # Store unmapped fields in raw
        normalized["raw"] = event
        
        return normalized
    except Exception as e:
        # Fallback to raw event — log so pipeline agent sees normalization failures
        print(f"[normalize] failed for {event.get('home', '?')} vs {event.get('away', '?')}: {e}", file=sys.stderr)
        return event

def normalize_batch(events: list[dict], source_type: str) -> list[dict]:
    """Normalize a batch of events."""
    return [normalize_adapter_output(event, source_type) for event in events]


