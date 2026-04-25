#!/usr/bin/env python3
"""Fix picks-ledger.csv: remove duplicate v17 entries, clean whitespace."""
import os

LEDGER = os.path.join(os.path.dirname(__file__), '..', 'betting', 'journal', 'picks-ledger.csv')

with open(LEDGER, 'r') as f:
    lines = f.readlines()

clean = []
seen_v17 = set()
for line in lines:
    s = line.strip()
    if not s:
        continue
    if '2026-04-25,v17,' in s:
        parts = s.split(',')
        pid = parts[2] if len(parts) >= 3 else s
        if pid in seen_v17:
            continue
        seen_v17.add(pid)
    clean.append(s + '\n')

with open(LEDGER, 'w') as f:
    f.writelines(clean)

v17 = sum(1 for l in clean if '2026-04-25,v17,' in l)
print(f"Done. v17 picks: {v17}, total lines: {len(clean)}")
