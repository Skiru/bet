#!/usr/bin/env python3
"""Fix corrupted picks-ledger.csv by removing duplicate lines."""

with open('betting/journal/picks-ledger.csv') as f:
    lines = f.readlines()

seen = set()
clean = []
for line in lines:
    stripped = line.strip()
    if not stripped:
        continue
    if stripped.startswith('betting_day,'):
        if 'betting_day' not in seen:
            clean.append(stripped)
            seen.add('betting_day')
        continue
    if stripped.startswith('2026-'):
        parts = stripped.split(',')
        if len(parts) >= 2:
            pick_id = parts[1]
            if pick_id not in seen:
                clean.append(stripped)
                seen.add(pick_id)

with open('betting/journal/picks-ledger.csv', 'w') as f:
    for line in clean:
        f.write(line + '\n')

print(f'Cleaned: {len(clean)} lines (1 header + {len(clean)-1} picks)')
for line in clean[-12:]:
    parts = line.split(',')
    if len(parts) >= 6:
        print(f'  {parts[0]} | {parts[1]} | {parts[2][:35]}... | {parts[5]}')
