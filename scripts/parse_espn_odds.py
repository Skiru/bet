import re
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'betting', 'data')


def parse_espn_odds(filepath, sport):
    if not os.path.exists(filepath):
        print('{} odds file not found'.format(sport))
        return
    with open(filepath) as f:
        html = f.read()

    print('=== ESPN {} ODDS ==='.format(sport))
    print('File size: {} chars'.format(len(html)))

    text = re.sub(r'<[^>]+>', '\n', html)
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    # Find team names
    team_indices = []
    for i, line in enumerate(lines):
        # NBA/NHL team names are often in specific format
        if re.match(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*$', line) and len(line) > 3 and len(line) < 30:
            # Check if near odds-related content
            ctx = ' '.join(lines[max(0, i-2):i+5])
            if any(w in ctx for w in ['Over', 'Under', 'Spread', 'O/U', 'ML', '+', '-']):
                team_indices.append((i, line))

    print('Potential teams near odds: {}'.format(len(team_indices)))
    for idx, name in team_indices[:20]:
        ctx = lines[idx:idx + 5]
        print('  {} | ctx: {}'.format(name, ' | '.join(ctx[:4])))

    # Find O/U totals
    totals = []
    for i, line in enumerate(lines):
        m = re.match(r'^[OoUu]\s*(\d{2,3}\.?\d*)$', line)
        if m:
            totals.append((i, float(m.group(1))))

    print('O/U totals found: {}'.format(len(totals)))
    for idx, val in totals[:20]:
        ctx_before = lines[max(0, idx - 5):idx]
        print('  Total: {} | context: {}'.format(val, ' | '.join(ctx_before[-3:])))

    # Find spread lines
    spreads = []
    for i, line in enumerate(lines):
        m = re.match(r'^([+-]\d+\.?\d*)$', line)
        if m:
            val = float(m.group(1))
            if abs(val) < 30:  # reasonable spread
                spreads.append((i, val))

    print('Spreads found: {}'.format(len(spreads)))
    for idx, val in spreads[:20]:
        ctx_before = lines[max(0, idx - 3):idx]
        print('  Spread: {} | context: {}'.format(val, ' | '.join(ctx_before[-2:])))

    # Find American odds
    am_odds = []
    for i, line in enumerate(lines):
        m = re.match(r'^([+-]\d{3,4})$', line)
        if m:
            val = int(m.group(1))
            if abs(val) < 2000:
                am_odds.append((i, val))

    print('American odds found: {}'.format(len(am_odds)))
    for idx, val in am_odds[:20]:
        # Convert to decimal
        if val > 0:
            dec = 1 + val / 100.0
        else:
            dec = 1 + 100.0 / abs(val)
        ctx = lines[max(0, idx - 2):idx]
        print('  {} (dec: {:.2f}) | ctx: {}'.format(val, dec, ' | '.join(ctx[-2:])))

    print()


parse_espn_odds(os.path.join(DATA, 'espn_nba_odds.html'), 'NBA')
parse_espn_odds(os.path.join(DATA, 'espn_nhl_odds.html'), 'NHL')
parse_espn_odds(os.path.join(DATA, 'espn_mlb_odds.html'), 'MLB')