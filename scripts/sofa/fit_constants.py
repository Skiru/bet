import argparse
import json
import logging
import math
import statistics
import sqlite3
from collections import defaultdict
from pathlib import Path

from bet.sofa.config import SofaConfig
from bet.sofa.engine import predictive_sd, calc_p_central, bar_probability, winning_boundary
from bet.sofa.db import get_connection

logger = logging.getLogger(__name__)

K_GRID = [0.0, 2.0, 5.0, 8.0, 10.0, 15.0, 25.0, 1000.0]

def bucket_p(p: float) -> str:
    # 0.0-0.1, 0.1-0.2, ...
    b = min(9, int(p * 10))
    return f"{b/10.0:.1f}-{(b+1)/10.0:.1f}"

def fit_baselines(conn: sqlite3.Connection):
    # One actual_value per event per market
    cur = conn.execute("""
        SELECT competition_id, market, sofascore_event_id, MAX(actual_value) as val
        FROM sofa_settled_row
        WHERE competition_id IS NOT NULL AND outcome != 'PUSH'
        GROUP BY competition_id, market, sofascore_event_id
    """)
    
    comp_market_vals = defaultdict(lambda: defaultdict(list))
    for row in cur:
        comp_id = str(row["competition_id"])
        market = row["market"]
        val = row["val"]
        comp_market_vals[market][comp_id].append(val)
        
    baselines = {}
    for market, comps in comp_market_vals.items():
        baselines[market] = {}
        all_vals = []
        for comp_id, vals in comps.items():
            all_vals.extend(vals)
            n = len(vals)
            if n >= 30:
                baselines[market][comp_id] = {
                    "mean": round(statistics.mean(vals), 4),
                    "n": n
                }
        if all_vals:
            baselines[market]["global"] = round(statistics.mean(all_vals), 4)
            
    return baselines

def fit_reliability(conn: sqlite3.Connection):
    cur = conn.execute("""
        SELECT market, p_central, outcome
        FROM sofa_settled_row
        WHERE outcome IN ('WIN', 'LOSS')
    """)
    
    market_buckets = defaultdict(lambda: defaultdict(list))
    for row in cur:
        market = row["market"]
        p_central = row["p_central"]
        outcome_val = 1.0 if row["outcome"] == 'WIN' else 0.0
        
        b = bucket_p(p_central)
        market_buckets[market][b].append((p_central, outcome_val))
        
    reliability = {}
    for market, buckets in market_buckets.items():
        reliability[market] = {}
        for b, pairs in buckets.items():
            n = len(pairs)
            if n < 10:
                continue
                
            diffs = [p_c - out for p_c, out in pairs]
            mean_diff = statistics.mean(diffs)
            std_diff = statistics.stdev(diffs) if n > 1 else 0.0
            se = std_diff / math.sqrt(n)
            
            # Confidence interval
            lower = mean_diff - 1.96 * se
            
            if lower > 0:
                correction = mean_diff
            else:
                correction = 0.0
                
            realised = statistics.mean([out for p_c, out in pairs])
            
            reliability[market][b] = {
                "realised": round(realised, 4),
                "n": n,
                "correction": round(correction, 4)
            }
            
    return reliability

def fit_k_centre(conn: sqlite3.Connection, baselines: dict):
    cur = conn.execute("""
        SELECT competition_id, market, line, direction, sample_size, sample_mean, sample_sd, outcome
        FROM sofa_settled_row
        WHERE outcome IN ('WIN', 'LOSS')
    """)
    
    rows = [dict(r) for r in cur]
    
    best_k = 10.0
    best_mae = float('inf')
    
    mae_by_k = {}
    
    for k in K_GRID:
        errors = []
        for r in rows:
            comp_id = str(r["competition_id"])
            market = r["market"]
            prior = None
            if market in baselines:
                if comp_id in baselines[market]:
                    prior = baselines[market][comp_id]["mean"]
                elif "global" in baselines[market]:
                    prior = baselines[market]["global"]
                    
            mean = r["sample_mean"]
            n = r["sample_size"]
            
            if prior is not None:
                w_c = n / (n + k)
                centre = w_c * mean + (1.0 - w_c) * prior
            else:
                centre = mean
                
            var_sample = max(r["sample_sd"]**2, mean)
            pred_sd = math.sqrt(var_sample * (1.0 + 1.0 / n))
            
            boundary = winning_boundary(r["line"], r["direction"])
            p_cent = calc_p_central(centre, pred_sd, boundary, r["direction"])
            
            outcome_val = 1.0 if r["outcome"] == 'WIN' else 0.0
            errors.append(abs(p_cent - outcome_val))
            
        if not errors:
            break
            
        mae = statistics.median(errors)
        mae_by_k[k] = mae
        
        # We want the smallest K on the plateau.
        # So if mae is very close to best_mae (e.g. within 0.001), we might prefer a certain K.
        # But let's just find the minimum first.
        if mae < best_mae - 0.0001:
            best_mae = mae
            best_k = k
            
    return best_k, mae_by_k

def fit_k_price(conn: sqlite3.Connection):
    cur = conn.execute("""
        SELECT p_central, market_p, sample_size, outcome
        FROM sofa_settled_row
        WHERE outcome IN ('WIN', 'LOSS') AND market_p IS NOT NULL
    """)
    
    rows = [dict(r) for r in cur]
    if not rows:
        return 10.0, {}
        
    best_k = 10.0
    best_mae = float('inf')
    mae_by_k = {}
    
    for k in K_GRID:
        errors = []
        for r in rows:
            p_cent = r["p_central"]
            m_p = r["market_p"]
            n = r["sample_size"]
            
            w = n / (n + k)
            p_bar = w * p_cent + (1.0 - w) * m_p
            
            outcome_val = 1.0 if r["outcome"] == 'WIN' else 0.0
            errors.append(abs(p_bar - outcome_val))
            
        mae = statistics.median(errors)
        mae_by_k[k] = mae
        
        if mae < best_mae - 0.0001:
            best_mae = mae
            best_k = k
            
    return best_k, mae_by_k

def fit_max_ladder_sigma(conn: sqlite3.Connection):
    # TBD, just return 1.25 for now or find where error diverges
    return 1.25

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default=SofaConfig.from_env().db_path)
    parser.add_argument("--config-dir", default="config")
    args = parser.parse_args()
    
    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"DB {db_path} does not exist", file=sys.stderr)
        sys.exit(2)
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    config_dir = Path(args.config_dir)
    config_dir.mkdir(exist_ok=True, parents=True)
    
    baselines = fit_baselines(conn)
    with open(config_dir / "sofa_league_baselines.json", "w", encoding="utf-8") as f:
        json.dump(baselines, f, indent=2, ensure_ascii=False)
        
    reliability = fit_reliability(conn)
    with open(config_dir / "sofa_market_reliability.json", "w", encoding="utf-8") as f:
        json.dump(reliability, f, indent=2, ensure_ascii=False)
        
    k_centre, k_centre_curve = fit_k_centre(conn, baselines)
    k_price, k_price_curve = fit_k_price(conn)
    max_sigma = fit_max_ladder_sigma(conn)
    
    report = {
        "K_CENTRE": {
            "value": k_centre,
            "curve": k_centre_curve
        },
        "K_PRICE": {
            "value": k_price,
            "curve": k_price_curve
        },
        "MAX_LADDER_SIGMA": max_sigma
    }
    
    with open(config_dir / "sofa_engine_constants.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        
    summary = {
        "stage": "FIT_CONSTANTS",
        "verdict": "OK",
        "metrics": {
            "baselines_markets": len(baselines),
            "reliability_markets": len(reliability),
            "k_centre": k_centre,
            "k_price": k_price
        },
        "output_path": str(config_dir)
    }
    print(f"SOFA_SUMMARY: {json.dumps(summary)}")

if __name__ == "__main__":
    main()
