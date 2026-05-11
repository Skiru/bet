#!/usr/bin/env python3
"""Comprehensive adapter audit — tests every adapter against real HTML files.

For each domain with a custom adapter:
1. Loads up to 5 recent HTML files
2. Runs the adapter's parse() function
3. Collects metrics: events found, field coverage, errors
4. Reports per-adapter health and field richness
"""
import json
import sys
import traceback
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from adapters import ADAPTERS, normalize_adapter_output

DATA_DIR = Path(__file__).parent.parent / "betting" / "data"


def audit_adapter(domain: str, parse_fn, max_files: int = 2) -> dict:
    """Run adapter against real HTML and collect metrics."""
    html_dir = DATA_DIR / domain
    if not html_dir.exists():
        return {"domain": domain, "status": "NO_DATA", "html_files": 0}

    # Size cap per domain — flashscore listing pages are 600KB-4MB
    size_cap = 5_000_000 if domain == "flashscore.com" else 500_000

    all_files = sorted(html_dir.glob("*.html"), reverse=True)
    html_files = []
    for f in all_files:
        if f.stat().st_size < size_cap:
            html_files.append(f)
        if len(html_files) >= max_files:
            break
    # Fallback: if all files are large, take the smallest ones
    if not html_files and all_files:
        html_files = sorted(all_files, key=lambda f: f.stat().st_size)[:max_files]
    if not html_files:
        return {"domain": domain, "status": "NO_HTML", "html_files": 0}

    total_events = 0
    total_errors = 0
    field_counts = defaultdict(int)
    sample_event = None
    error_messages = []
    
    # Track which enrichment fields are populated
    enrichment_fields = [
        "home", "away", "time", "league", "sport", "source_url",
        "match_id", "match_url", "score_home", "score_away",
        "period_scores", "status", "is_live", "country",
        "odds", "form_home", "form_away", "h2h",
        "cards", "fouls", "shots", "standings", "predictions",
        "corners",
    ]

    for f in html_files:
        try:
            html = f.read_text(errors="replace")
            url = f"https://www.{domain}/sample/{f.stem}"
            results = parse_fn(html, url)
            
            if not isinstance(results, list):
                total_errors += 1
                error_messages.append(f"{f.name}: returned {type(results).__name__}, not list")
                continue
            
            total_events += len(results)
            
            for event in results:
                if not isinstance(event, dict):
                    continue
                    
                # Check raw adapter output fields
                for field in enrichment_fields:
                    val = event.get(field)
                    if val is not None and val != [] and val != {} and val != "":
                        # For nested dicts, check if any value is non-None
                        if isinstance(val, dict):
                            if any(v is not None for v in val.values()):
                                field_counts[field] += 1
                        else:
                            field_counts[field] += 1
                
                if sample_event is None and event.get("home"):
                    sample_event = event
                    
        except Exception as e:
            total_errors += 1
            error_messages.append(f"{f.name}: {type(e).__name__}: {str(e)[:100]}")

    # Calculate coverage percentages
    field_coverage = {}
    for field in enrichment_fields:
        count = field_counts.get(field, 0)
        pct = round(100 * count / max(total_events, 1), 1)
        field_coverage[field] = {"count": count, "pct": pct}

    # Test normalization on sample
    norm_ok = True
    norm_error = None
    if sample_event:
        try:
            normalized = normalize_adapter_output(sample_event, source_type=domain)
            # Verify key fields survived normalization
            if not normalized.get("home"):
                norm_ok = False
                norm_error = "home field lost in normalization"
        except Exception as e:
            norm_ok = False
            norm_error = f"{type(e).__name__}: {str(e)[:100]}"

    return {
        "domain": domain,
        "status": "OK" if total_errors == 0 else "ERRORS",
        "html_files": len(html_files),
        "total_events": total_events,
        "events_per_file": round(total_events / max(len(html_files), 1), 1),
        "errors": total_errors,
        "error_messages": error_messages[:3],
        "field_coverage": field_coverage,
        "normalization_ok": norm_ok,
        "normalization_error": norm_error,
        "sample_event_keys": sorted(sample_event.keys()) if sample_event else [],
    }


def main():
    print("=" * 80)
    print("ADAPTER AUDIT — Testing all adapters against real HTML data")
    print("=" * 80)
    
    results = []
    
    for domain, parse_fn in sorted(ADAPTERS.items()):
        adapter_name = parse_fn.__module__.split(".")[-1] if hasattr(parse_fn, "__module__") else "unknown"
        result = audit_adapter(domain, parse_fn, max_files=5)
        result["adapter"] = adapter_name
        results.append(result)
    
    # Print summary table
    print(f"\n{'Domain':<30} {'Adapter':<25} {'Files':>5} {'Events':>7} {'Avg':>5} {'Errs':>4} {'Norm':>4}")
    print("-" * 85)
    
    for r in sorted(results, key=lambda x: x.get("total_events", 0), reverse=True):
        domain = r["domain"]
        adapter = r["adapter"]
        files = r.get("html_files", 0)
        events = r.get("total_events", 0)
        avg = r.get("events_per_file", 0)
        errors = r.get("errors", 0)
        norm = "✓" if r.get("normalization_ok", False) else "✗"
        status = r.get("status", "?")
        
        flag = "" if status == "OK" else f" ⚠ {status}"
        print(f"{domain:<30} {adapter:<25} {files:>5} {events:>7} {avg:>5} {errors:>4} {norm:>4}{flag}")
    
    # Field coverage matrix
    print(f"\n{'='*80}")
    print("FIELD COVERAGE MATRIX (% of events with field populated)")
    print(f"{'='*80}")
    
    key_fields = ["home", "away", "time", "league", "sport", "match_id", "match_url",
                  "score_home", "score_away", "status", "is_live", "country",
                  "odds", "standings", "predictions", "corners"]
    
    header = f"{'Domain':<25}" + "".join(f"{f[:8]:>9}" for f in key_fields)
    print(header)
    print("-" * len(header))
    
    for r in sorted(results, key=lambda x: x.get("total_events", 0), reverse=True):
        if r.get("total_events", 0) == 0:
            continue
        domain = r["domain"][:24]
        fc = r.get("field_coverage", {})
        cells = []
        for f in key_fields:
            pct = fc.get(f, {}).get("pct", 0)
            if pct == 0:
                cells.append(f"{'—':>9}")
            elif pct == 100:
                cells.append(f"{'100%':>9}")
            else:
                cells.append(f"{pct:>8.0f}%")
            
        print(f"{domain:<25}" + "".join(cells))
    
    # Error details
    errors_found = [r for r in results if r.get("errors", 0) > 0]
    if errors_found:
        print(f"\n{'='*80}")
        print("ERROR DETAILS")
        print(f"{'='*80}")
        for r in errors_found:
            print(f"\n{r['domain']} ({r['errors']} errors):")
            for msg in r.get("error_messages", []):
                print(f"  • {msg}")
    
    # Normalization issues
    norm_issues = [r for r in results if not r.get("normalization_ok", True)]
    if norm_issues:
        print(f"\n{'='*80}")
        print("NORMALIZATION ISSUES")
        print(f"{'='*80}")
        for r in norm_issues:
            print(f"  {r['domain']}: {r.get('normalization_error', 'unknown')}")
    
    # Summary verdicts
    print(f"\n{'='*80}")
    print("VERDICTS")
    print(f"{'='*80}")
    
    total_adapters = len(results)
    ok_adapters = len([r for r in results if r.get("status") == "OK" and r.get("total_events", 0) > 0])
    no_data = len([r for r in results if r.get("status") in ("NO_DATA", "NO_HTML")])
    errored = len([r for r in results if r.get("errors", 0) > 0])
    zero_events = len([r for r in results if r.get("total_events", 0) == 0 and r.get("status") == "OK"])
    
    print(f"  Total adapters tested: {total_adapters}")
    print(f"  ✅ Working (events > 0, no errors): {ok_adapters}")
    print(f"  ⚠️  No HTML data available: {no_data}")
    print(f"  ⚠️  Zero events extracted: {zero_events}")
    print(f"  ❌ Errors during parsing: {errored}")
    
    # Rich data assessment
    print(f"\n  ENRICHMENT DEPTH:")
    rich_adapters = []
    for r in results:
        if r.get("total_events", 0) == 0:
            continue
        fc = r.get("field_coverage", {})
        rich_fields = sum(1 for f in ["score_home", "match_url", "country", "odds", "standings", "predictions"]
                         if fc.get(f, {}).get("pct", 0) > 0)
        rich_adapters.append((r["domain"], rich_fields))
    
    for domain, count in sorted(rich_adapters, key=lambda x: x[1], reverse=True):
        bar = "█" * count + "░" * (6 - count)
        print(f"    {domain:<30} {bar} ({count}/6 enrichment fields)")


if __name__ == "__main__":
    main()
