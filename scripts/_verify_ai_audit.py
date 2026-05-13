"""Verify AI configuration audit — all 5 phases."""
import os
import re
import sys

GITHUB_DIR = os.path.join(os.path.dirname(__file__), "..", ".github")
PLANS_DIR = os.path.join(GITHUB_DIR, "plans")

def search_files(directory, pattern, exclude_dirs=None):
    """Search for regex pattern in all .md files, return matches."""
    exclude_dirs = exclude_dirs or []
    matches = []
    for root, dirs, files in os.walk(directory):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if os.path.join(root, d) not in exclude_dirs]
        for f in files:
            if not f.endswith(".md"):
                continue
            path = os.path.join(root, f)
            try:
                with open(path, "r") as fh:
                    for i, line in enumerate(fh, 1):
                        if re.search(pattern, line):
                            rel = os.path.relpath(path, GITHUB_DIR)
                            matches.append(f"  {rel}:{i}: {line.strip()[:100]}")
            except Exception:
                pass
    return matches


def check(label, pattern, should_exist=False, exclude_plans=True):
    """Run a verification check. Returns True if passed."""
    exclude = [os.path.abspath(PLANS_DIR)] if exclude_plans else []
    hits = search_files(os.path.abspath(GITHUB_DIR), pattern, exclude_dirs=exclude)
    
    if should_exist:
        ok = len(hits) > 0
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {label} — {'found' if ok else 'NOT found'}")
    else:
        ok = len(hits) == 0
        status = "PASS" if ok else f"FAIL ({len(hits)} hits)"
        print(f"  [{status}] {label}")
    
    if not ok:
        for h in hits[:5]:
            print(f"    {h}")
    return ok


def main():
    results = []
    
    print("=== PHASE 1: Critical Fixes ===")
    results.append(check("bet-reading-html removed", r"bet-reading-html"))
    results.append(check("19 rules → 20 rules", r"These 19 rules"))
    results.append(check("Per-sport scanners removed", r"bet-scanner-(football|tennis|basketball|volleyball|hockey)"))
    results.append(check("<2h kickoff removal gone", r"<2h to kickoff.*(remove[^)]|filter|exclude|drop)"))
    results.append(check("<4 picks NO BET gone", r"declare NO BET|<[34] picks.* NO BET day"))
    
    print("\n=== PHASE 2: Architecture Alignment ===")
    results.append(check("Old API chain gone", r"api-football.*football-data-org"))
    results.append(check("14 sports gone from descriptions", r"(all |any of the )14 (betting|supported) sports"))
    results.append(check("S0.7 stealth warmup added", r"S0\.7.*[Ss]tealth|daily_odds_warmup", should_exist=True))
    
    print("\n=== PHASE 3: Tool & Execution Patterns ===")
    results.append(check(".venv/bin/python removed", r"\.venv/bin/python"))
    results.append(check("Parallel S2+S2.5 noted", r"PARALLEL.*S2.*S2\.5|S2.*S2\.5.*PARALLEL|S2\+S2\.5.*parallel", should_exist=True))
    
    print("\n=== PHASE 4: Web Research Enhancement ===")
    results.append(check("GCP tools removed from agents", r"gcp-(gcloud|observability|storage)"))
    results.append(check("playwright/* on scanner", r"playwright/\*", should_exist=True, exclude_plans=True))
    
    print("\n=== PHASE 5: Consistency Sweep ===")
    # Check for duplicate sequentialthinking in multi-line agent files (not orchestrator)
    agents_dir = os.path.join(os.path.abspath(GITHUB_DIR), "agents")
    dup_hits = []
    for f in os.listdir(agents_dir):
        if not f.endswith(".md") or f == "bet-orchestrator.agent.md":
            continue
        path = os.path.join(agents_dir, f)
        with open(path) as fh:
            content = fh.read()
        count = content.count('"sequentialthinking/sequentialthinking"')
        if count > 0:
            dup_hits.append(f"  {f}: {count} occurrences")
    
    ok = len(dup_hits) == 0
    status = "PASS" if ok else f"FAIL ({len(dup_hits)} agents)"
    print(f"  [{status}] Duplicate sequentialthinking removed")
    for h in dup_hits:
        print(f"    {h}")
    results.append(ok)
    
    results.append(check("PYTHONPATH=src:. standardized", r"PYTHONPATH=src:\."))
    
    # Summary
    passed = sum(results)
    total = len(results)
    print(f"\n{'='*40}")
    print(f"RESULT: {passed}/{total} checks passed")
    if passed == total:
        print("ALL CHECKS PASSED ✓")
    else:
        print(f"FAILURES: {total - passed} — review above")
    
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
