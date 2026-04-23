import re
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'betting', 'data')


def parse_betideas(filepath):
    if not os.path.exists(filepath):
        print('BetIdeas file not found')
        return
    with open(filepath) as f:
        html = f.read()

    print('=== BETIDEAS TOMORROW TIPS ===')
    print('File size: {} chars'.format(len(html)))

    text = re.sub(r'<[^>]+>', '|', html)
    text = re.sub(r'\|+', '|', text)

    # Search for key matches
    for kw in ['Jagiellonia', 'Madrid', 'Struff', 'Tauson', 'Shelton', 'Machac',
               'Sakkari', 'Clermont', 'BTTS', 'Both Teams', 'corners', 'Over 2.5',
               'Under 2.5', 'Ligue 2', 'NBA', 'NHL', 'Ekstraklasa']:
        idx = text.find(kw)
        if idx >= 0:
            snippet = text[max(0, idx - 80):idx + 200]
            snippet = re.sub(r'\s+', ' ', snippet).strip()
            print('  Found "{}": {}'.format(kw, snippet[:200]))

    # Count total tips
    tip_count = len(re.findall(r'(?:tip|pick|prediction)', text.lower()))
    print('  Total tip mentions: {}'.format(tip_count))

    # Find all match references with odds
    matches_with_odds = re.findall(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:v|vs\.?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', text[:50000])
    print('  Matches mentioned: {}'.format(len(matches_with_odds)))
    for m in matches_with_odds[:15]:
        print('    {} vs {}'.format(m[0], m[1]))
    print()


def parse_sportsgambler(filepath):
    if not os.path.exists(filepath):
        print('Sportsgambler file not found')
        return
    with open(filepath) as f:
        html = f.read()

    print('=== SPORTSGAMBLER PREDICTIONS ===')
    print('File size: {} chars'.format(len(html)))

    text = re.sub(r'<[^>]+>', '|', html)
    text = re.sub(r'\|+', '|', text)

    # Find predictions with confidence/probability
    for kw in ['Jagiellonia', 'Madrid', 'Ekstraklasa', 'Ligue 2', 'corners',
               'BTTS', 'Over', 'Under', 'prediction', 'April 24', '24/04',
               'tomorrow', 'Clermont', 'ATP', 'WTA', 'NBA', 'NHL']:
        idx = text.find(kw)
        if idx >= 0:
            snippet = text[max(0, idx - 80):idx + 200]
            snippet = re.sub(r'\s+', ' ', snippet).strip()
            print('  Found "{}": {}'.format(kw, snippet[:200]))
    print()


parse_betideas(os.path.join(DATA, 'betideas_tips_tomorrow.html'))
parse_sportsgambler(os.path.join(DATA, 'sportsgambler_tips.html'))