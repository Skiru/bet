#!/usr/bin/env python3
"""Scan repository for references to top-level scripts in `scripts/`.
Outputs JSON to stdout with counts and example locations.
"""
import os
import json
import sys

ROOT = os.getcwd()
SCRIPTS_DIR = os.path.join(ROOT, "scripts")

# folders to ignore while scanning for references
IGNORED_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules", "scripts/pipeline_steps", "scripts/tests", "scripts/migrations", "scripts/_helpers", "scripts/_tools"}

# gather top-level script files (direct children of scripts/)
candidates = []
for name in sorted(os.listdir(SCRIPTS_DIR)):
    path = os.path.join(SCRIPTS_DIR, name)
    if os.path.isfile(path) and name.endswith('.py'):
        # ignore obvious internal helpers
        if name.startswith('_'):
            continue
        candidates.append(name)

# scan repository for references
results = {}
for script_name in candidates:
    hits = []
    for root, dirs, files in os.walk(ROOT):
        # prune ignored dirs
        rel = os.path.relpath(root, ROOT)
        if any(rel.startswith(d) for d in IGNORED_DIRS):
            continue
        for f in files:
            # only scan text files
            if f.endswith(('.py', '.md', '.json', '.yaml', '.yml', '.sh', '.txt')):
                fp = os.path.join(root, f)
                try:
                    with open(fp, 'r', encoding='utf-8') as fh:
                        for i, line in enumerate(fh, start=1):
                            if script_name in line:
                                hits.append({'file': os.path.relpath(fp, ROOT), 'line': i, 'text': line.strip()})
                                # cap hits per file to avoid huge outputs
                                break
                except Exception:
                    continue
    results[script_name] = {'refs': len(hits), 'locations': hits[:3]}

# classify
unreferenced = [s for s, info in results.items() if info['refs'] <= 1]

out = {'summary': {'total_scripts': len(candidates), 'unreferenced_candidates': len(unreferenced)}, 'results': results, 'unreferenced': unreferenced}
print(json.dumps(out, indent=2))

# exit with non-zero if there are many unreferenced candidates
if len(unreferenced) > 0:
    sys.exit(2)
else:
    sys.exit(0)
