import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from pydantic import RootModel

from bet.sofa.cache import SofaCache
from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture, FixtureSamples
from bet.sofa.samples import process_fixture_samples
from bet.sofa.superbet import SuperbetClient
from bet.sofa.samples import process_fixture_samples
from bet.sofa.superbet import SuperbetClient
from bet.sofa.timeutil import now
import statistics

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD", default=now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    
    config = SofaConfig.from_env()
    client = SofascoreClient(config)
    cache = SofaCache(config)
    superbet_client = SuperbetClient()
    
    fixtures_path = Path(config.runs_dir) / args.date / "02_fixtures.json"
    if not fixtures_path.exists():
        print(f"{fixtures_path} missing", file=sys.stderr)
        sys.exit(2)
        
    with open(fixtures_path, "rb") as f:
        fixtures_data = f.read()
    
    fixtures = RootModel[list[Fixture]].model_validate_json(fixtures_data).root
    

    class CacheStats:
        hits = 0
        misses = 0
    cache_stats = CacheStats()
    
    orig_get_event_stats = cache.get_event_stats
    def tracked_get_event_stats(event_id):
        res = orig_get_event_stats(event_id)
        if res:
            cache_stats.hits += 1
        else:
            cache_stats.misses += 1
        return res
    cache.get_event_stats = tracked_get_event_stats
    
    all_samples = []

    gap_counts = defaultdict(int)
    readiness_counts = defaultdict(int)
    total_metrics = 0
    
    metric_sizes = defaultdict(list)

    for f in fixtures:
        samples = process_fixture_samples(f, client, cache, superbet_client, config)
        all_samples.append(samples)
        
        readiness_counts[samples.readiness] += 1
        for gap in samples.gaps:
            gap_counts[gap.reason.value] += 1
        total_metrics += len(samples.metrics)
        
        for metric_name, m_sample in samples.metrics.items():
            unique_ids = set(o.sofascore_event_id for o in m_sample.side_a + m_sample.side_b + m_sample.h2h)
            metric_sizes[metric_name].append(len(unique_ids))
            
    out_path = Path(config.runs_dir) / args.date / "03_samples.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    dumped = [s.model_dump(mode="json") for s in all_samples]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dumped, f, indent=2)
        

    median_sizes = {m: statistics.median(sizes) for m, sizes in metric_sizes.items() if sizes}
    
    metrics = {
        "input_fixtures": len(fixtures),
        "output_samples": len(all_samples),
        "total_metrics_extracted": total_metrics,
        "readiness": dict(readiness_counts),
        "gaps": dict(sorted(gap_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
        "cache_hits": cache_stats.hits,
        "network_requests": cache_stats.misses,
        "median_sample_size": median_sizes
    }

    
    summary = {
        "stage": "SAMPLES",
        "verdict": "OK" if readiness_counts["READY"] > 0 else "FAILED",
        "metrics": metrics,
        "output_path": str(out_path)
    }
    print(f"SOFA_SUMMARY: {json.dumps(summary)}")
    
if __name__ == "__main__":
    main()
