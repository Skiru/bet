import re
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(BASE, 'betting', 'data', 'espn_nhl_odds.html')) as f:
    html = f.read()

text = re.sub(r'<[^>]+>', '\n', html)
lines = [l.strip() for l in text.split('\n') if l.strip()]

# Find NHL teams first
print('=== NHL TEAMS ===')
nhl_teams = []
for i, line in enumerate(lines):
    if re.match(r'^(Buffalo|Carolina|Colorado|Tampa|Vegas|Edmonton|Dallas|Pittsburgh)', line):
        ctx = lines[i:i + 3]
        print('  {} | {}'.format(line, ctx))
        nhl_teams.append((i, line))

# Find totals near 5-7 range
print('\n=== NHL TOTALS ===')
total_re = re.compile(r'^[oOuU]\s*(\d\.?\d*)$')
for i, line in enumerate(lines):
    clean = line.replace(' ', '')
    m = total_re.match(clean)
    if m:
        val = float(m.group(1))
        if 4 < val < 8:
            ctx = lines[max(0, i - 5):i]
            print('  Total: {} | ctx: {}'.format(val, ' | '.join(ctx[-3:])))

# Find all lines containing 5.5, 6.5 etc
print('\n=== LINES WITH 5.5/6.5 ===')
for i, line in enumerate(lines):
    if '5.5' in line or '6.5' in line:
        ctx = lines[max(0, i - 3):i + 2]
        print('  {}: {} | ctx: {}'.format(i, line, ctx))