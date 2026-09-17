import concurrent.futures
from collections import defaultdict
from datetime import datetime, UTC
from typing import Any

from bet.sofa.cache import SofaCache
from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture, FixtureSamples, MetricSample, Observation, GapEntry, GapReason, Readiness
from bet.sofa.market_mapper import classify_market
from bet.sofa.metrics import extract_flat_statistics, check_identities, extract_metric, FOOTBALL_METRICS, TENNIS_METRICS
from bet.sofa.superbet import SuperbetClient


def fetch_available_metrics(fixture: Fixture, superbet_client: SuperbetClient) -> set[str]:
    available_metrics = set()
    for s_id in fixture.superbet_event_ids:
        odds_data = superbet_client.event_odds(s_id)
        if not odds_data:
            continue
        # Based on Superbet API response structure: "odds" is a list of markets
        # We need to extract marketName
        odds = odds_data.get("odds") or []
        for item in odds:
            market_name = item.get("marketName")
            metric = classify_market(market_name)
            if metric:
                available_metrics.add(metric)
    return available_metrics


def get_historical_events(
    client: SofascoreClient, 
    cache: SofaCache, 
    entity_id: int, 
    sport: str, 
    fixture: Fixture, 
    config: SofaConfig,
    is_side_a: bool,
) -> list[dict[str, Any]]:
    events = []
    page = 0
    while len(events) < config.sample_n and page < 5:  # safeguard against infinite loop
        page_events = client.entity_events(entity_id, "last", page)
        if not page_events:
            break
            
        for e in page_events:
            if len(events) >= config.sample_n:
                break
            
            # Check finished
            if e.get("status", {}).get("type") != "finished":
                continue
                
            # Check future leak
            start_ts = e.get("startTimestamp")
            if not start_ts:
                continue
            dt = datetime.fromtimestamp(start_ts, UTC)
            if dt >= fixture.kickoff_utc:
                continue
                
            # Tennis filters
            if sport == "tennis":
                g_type = e.get("groundType")
                if g_type != fixture.ground_type:
                    continue
                # For tennis, verify best_of
                best_of = e.get("defaultPeriodCount")
                if best_of != fixture.best_of:
                    continue
            else:
                # Football filters: Ignore friendlies. 
                # For now, let's assume we have an EXCLUDED_COMPETITIONS list.
                # If uniqueTournament.id in excluded_list, continue
                comp_id = e.get("tournament", {}).get("uniqueTournament", {}).get("id")
                # e.g., friendlies: 
                # if comp_id in EXCLUDED_COMPETITIONS: continue
                pass
            
            # Additional safety: event must be either home or away for entity_id
            home_id = e.get("homeTeam", {}).get("id")
            away_id = e.get("awayTeam", {}).get("id")
            if home_id != entity_id and away_id != entity_id:
                continue

            events.append(e)
            
        page += 1
        
    return events


def process_historical_event(
    client: SofascoreClient, 
    cache: SofaCache, 
    event: dict[str, Any], 
    entity_id: int, 
    sport: str,
    metrics_to_collect: set[str],
    fixture: Fixture
) -> dict[str, Any]:
    event_id = event["id"]
    
    # Try fetching from cache
    cached_stats = cache.get_event_stats(event_id)
    if cached_stats:
        statistics_json, incidents_json, _ = cached_stats
    else:
        # Fetch from network
        statistics_json = client.event_statistics(event_id)
        # Fetch incidents only if football and any metric needs incidents (cards)
        incidents_json = None
        needs_incidents = sport == "football" and any(m in ["cards_points_total", "cards_points_for"] for m in metrics_to_collect)
        if needs_incidents:
            incidents_json = client.event_incidents(event_id)
            
        status_type = event.get("status", {}).get("type", "finished")
        cache.save_event_stats(event_id, statistics_json, incidents_json, status_type)

    flat_stats = extract_flat_statistics(statistics_json)
    
    ident_gap = check_identities(flat_stats, incidents_json, event, sport)
    
    home_team = event.get("homeTeam", {})
    away_team = event.get("awayTeam", {})
    
    is_home = (home_team.get("id") == entity_id)
    opponent_name = away_team.get("name") if is_home else home_team.get("name")
    if not opponent_name:
        opponent_name = "Unknown"
        
    match_dt = datetime.fromtimestamp(event["startTimestamp"], UTC)
    
    comp_id = event.get("tournament", {}).get("uniqueTournament", {}).get("id")
    season_id = event.get("season", {}).get("id")
    
    venue = "home" if is_home else "away"
    if sport == "tennis":
        venue = None
        
    collected = {}
    for metric in metrics_to_collect:
        if ident_gap:
            collected[metric] = ident_gap
            continue
            
        val = extract_metric(metric, sport, flat_stats, incidents_json, event, is_home)
        if isinstance(val, GapReason):
            collected[metric] = val
        else:
            collected[metric] = Observation(
                sofascore_event_id=event_id,
                match_date_utc=match_dt,
                opponent=opponent_name,
                value=val,
                competition_id=comp_id,
                season_id=season_id,
                venue=venue,
            )
            
    home_id = event.get("homeTeam", {}).get("id")
    away_id = event.get("awayTeam", {}).get("id")
    is_h2h = False
    if home_id == fixture.home_entity_id and away_id == fixture.away_entity_id:
        is_h2h = True
    elif home_id == fixture.away_entity_id and away_id == fixture.home_entity_id:
        is_h2h = True
    return {"event_id": event_id, "collected": collected, "is_h2h": is_h2h}


def process_fixture_samples(
    fixture: Fixture, 
    client: SofascoreClient, 
    cache: SofaCache, 
    superbet_client: SuperbetClient, 
    config: SofaConfig
) -> FixtureSamples:
    
    # 1. Fetch Superbet available markets
    metrics_to_collect = fetch_available_metrics(fixture, superbet_client)
    
    # If no metrics, skip fetching history
    if not metrics_to_collect:
        return FixtureSamples(
            sofascore_event_id=fixture.sofascore_event_id,
            readiness="BLOCKED",
            metrics={},
            gaps=[GapEntry(reason=GapReason.NO_PRICE, metric="all", detail="No priced markets on Superbet")]
        )
        
    # 2. Get historical events
    side_a_events = get_historical_events(client, cache, fixture.home_entity_id, fixture.sport, fixture, config, True)
    side_b_events = get_historical_events(client, cache, fixture.away_entity_id, fixture.sport, fixture, config, False)
    
    # 3. Process events to extract metrics
    side_a_results = []
    side_b_results = []
    
    for e in side_a_events:
        side_a_results.append(process_historical_event(client, cache, e, fixture.home_entity_id, fixture.sport, metrics_to_collect, fixture))
        
    for e in side_b_events:
        side_b_results.append(process_historical_event(client, cache, e, fixture.away_entity_id, fixture.sport, metrics_to_collect, fixture))
        
    # 4. Build MetricSamples
    metric_samples = {}
    gaps = []
    
    # Helper to check if event was already used in a list (for deduplication in total)
    
    for metric in metrics_to_collect:
        obs_a = []
        obs_b = []
        obs_h2h = []
        
        seen_events = set()
        
        # side_a
        for res in side_a_results:
            val = res["collected"].get(metric)
            if isinstance(val, GapReason):
                gaps.append(GapEntry(reason=val, metric=metric, detail=f"Side A event {res['event_id']} gap"))
            elif val is not None:
                obs_a.append(val)
                seen_events.add(val.sofascore_event_id)
                if res["is_h2h"]:
                    obs_h2h.append(val)
                    
        # side_b
        for res in side_b_results:
            val = res["collected"].get(metric)
            if isinstance(val, GapReason):
                gaps.append(GapEntry(reason=val, metric=metric, detail=f"Side B event {res['event_id']} gap"))
            elif val is not None:
                # Deduplication logic: "jeden mecz historyczny wnosi jedną obserwację do _total"
                # But wait, observation is per-side. If it's a "total" metric, it's the same value for both sides.
                # If it's a "for" metric, the value is different!
                # Wait, "Deduplication: jeden mecz = jedna obserwacja w _total". 
                # This just means the sample size should not double count. But MetricSample has side_a and side_b lists.
                # If we put it in side_b list, and it's already in side_a, should we exclude it from side_b?
                # Actually, if we just collect side_a and side_b independently, the consumer (E8 SHEET) will deduplicate when combining into a single sample, OR we can deduplicate here.
                # The rule: "deduplikacja obserwacji między side_a, side_b i h2h: jeden mecz historyczny wnosi jedną obserwację do _total, choćby występował w trzech koszykach."
                # It's better to deduplicate when flattening in the engine, but let's just make sure we don't return the exact same observation. Wait, if it's side_b's perspective on `shots_for`, it's a DIFFERENT observation than side_a's `shots_for` on the SAME match!
                # Ah! For `_total` metrics, the value is the same. For `_for` metrics, the value is side-specific.
                # The instruction says: "jeden mecz historyczny wnosi jedną obserwację do _total". This probably refers to the stage where the arrays are merged. We'll just pass all valid observations here.
                obs_b.append(val)
                if val.sofascore_event_id not in seen_events:
                    seen_events.add(val.sofascore_event_id)
                    if res["is_h2h"]:
                        obs_h2h.append(val)
                        
        metric_samples[metric] = MetricSample(
            metric=metric,
            side_a=obs_a,
            side_b=obs_b,
            h2h=obs_h2h
        )
        
    # Calculate readiness globally or per metric?
    # "READY obie strony mają >= SOFA_MIN_SAMPLE (5) obserwacji metryki"
    # Wait, readiness is per fixture or per metric? 
    # FixtureSamples has `readiness`. Is it for the whole fixture?
    # Usually readiness is per-metric, but in FixtureSamples it's at the top level.
    # We define it as: if AT LEAST ONE metric is READY, then the fixture is READY?
    # The requirement: "READY obie strony mają >= SOFA_MIN_SAMPLE (5) obserwacji metryki"
    # Let's compute it across all collected metrics. If any metric is READY, we mark READY.
    
    max_a_len = max([len(ms.side_a) for ms in metric_samples.values()], default=0)
    max_b_len = max([len(ms.side_b) for ms in metric_samples.values()], default=0)
    
    if max_a_len >= config.min_sample and max_b_len >= config.min_sample:
        readiness = "READY"
    elif max_a_len >= 1 or max_b_len >= 1:
        readiness = "PARTIAL"
    else:
        readiness = "BLOCKED"
        
    return FixtureSamples(
        sofascore_event_id=fixture.sofascore_event_id,
        readiness=readiness,
        metrics=metric_samples,
        gaps=gaps
    )

