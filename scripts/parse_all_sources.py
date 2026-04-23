import re
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'betting', 'data')


def parse_espn_schedule(filepath, sport):
    if not os.path.exists(filepath):
        print('  {} file not found'.format(sport))
        return
    with open(filepath) as f:
        html = f.read()
    text = re.sub(r'<[^>]+>', '|', html)
    text = re.sub(r'\|+', '|', text)
    # Find team names near odds/spreads
    teams = re.findall(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*(?:vs\.?|@)\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', text)
    print('=== ESPN {} ==='.format(sport))
    print('  Matchups found: {}'.format(len(teams)))
    for t in teams[:10]:
        print('    {} vs {}'.format(t[0], t[1]))
    print()


def parse_scoresandodds(filepath, sport):
    if not os.path.exists(filepath):
        print('  {} file not found'.format(sport))
        return
    with open(filepath) as f:
        html = f.read()
    text = re.sub(r'<[^>]+>', '|', html)
    text = re.sub(r'\|+', '|', text)
    text = re.sub(r'\s+', ' ', text)

    print('=== ScoresAndOdds {} ==='.format(sport))
    # Find total lines (O/U)
    totals = re.findall(r'(?:O|Over|U|Under)\s*(\d+\.?\d*)', text[:10000])
    print('  Total lines found: {}'.format(len(totals)))
    # Find team names
    teams = re.findall(r'([A-Z][a-z]{2,15}(?:\s+[A-Z][a-z]+)?)\s*[-|]\s*(\d+\.?\d*)', text[:10000])
    for t in teams[:10]:
        print('    {} | {}'.format(t[0], t[1]))
    # Find spreads
    spreads = re.findall(r'([+-]\d+\.?\d*)', text[:10000])
    print('  Spread lines: {}'.format(spreads[:10]))
    print()


def parse_soccerstats_corners(filepath, league):
    if not os.path.exists(filepath):
        print('  {} file not found'.format(league))
        return
    with open(filepath) as f:
        html = f.read()

    print('=== SoccerStats Corners: {} ==='.format(league))
    text = re.sub(r'<[^>]+>', '|', html)
    text = re.sub(r'\|+', '|', text)

    # Find corner-related stats
    corner_data = re.findall(r'([A-Za-zÀ-žŁłŚśŻżŹźĆćĄąĘę\s]+)\|(\d+\.?\d*)\|', text[:50000])
    # Look for team names near numbers
    teams = re.findall(r'([A-ZÀ-Ž][a-zà-ž]+(?:\s+[A-ZÀ-Ž][a-zà-ž]+)*)\|[^|]*?(\d+\.\d+)[^|]*?\|', text[:30000])
    for t in teams[:15]:
        print('  {} | {}'.format(t[0].strip(), t[1]))
    print()


def parse_totalcorner(filepath):
    if not os.path.exists(filepath):
        print('  TotalCorner file not found')
        return
    with open(filepath) as f:
        html = f.read()

    print('=== TotalCorner ===')
    text = re.sub(r'<[^>]+>', '|', html)
    text = re.sub(r'\|+', '|', text)
    text = re.sub(r'\s+', ' ', text)

    # Find matches with corner predictions
    matches = re.findall(r'(\d{2}:\d{2})\|([^|]+)\|(?:vs|[-])\|([^|]+)\|.*?(?:corner|Corner).*?(\d+\.?\d*)', text[:30000])
    print('  Matches with corners: {}'.format(len(matches)))
    for m in matches[:15]:
        print('    {} {} vs {} | corners: {}'.format(m[0], m[1].strip(), m[2].strip(), m[3]))

    # Alternative: just find match rows
    all_matches = re.findall(r'(\d{2}:\d{2})\|([^|]{3,30})\|[^|]*\|([^|]{3,30})\|', text[:30000])
    if not matches:
        print('  All match rows: {}'.format(len(all_matches)))
        for m in all_matches[:10]:
            print('    {} {} vs {}'.format(m[0], m[1].strip(), m[2].strip()))
    print()


def parse_olbg(filepath, sport):
    if not os.path.exists(filepath):
        print('  OLBG {} not found'.format(sport))
        return
    with open(filepath) as f:
        html = f.read()

    print('=== OLBG {} ==='.format(sport))
    text = re.sub(r'<[^>]+>', '|', html)
    text = re.sub(r'\|+', '|', text)
    text = re.sub(r'\s+', ' ', text)

    # Look for tip counts and match names
    for kw in ['Madrid', 'Struff', 'Tauson', 'Jagiellonia', 'Clermont', 'Shelton',
               'Machac', 'Sakkari', 'NBA', 'NHL', 'tips']:
        idx = text.find(kw)
        if idx >= 0:
            snippet = text[max(0, idx - 80):idx + 200]
            print('  Found "{}": {}'.format(kw, snippet[:150]))
    print()


# Run all parsers
print('=' * 60)
print('PARSING ALL SOURCES FOR APR 24')
print('=' * 60)

parse_espn_schedule(os.path.join(DATA, 'espn_nba.html'), 'NBA')
parse_espn_schedule(os.path.join(DATA, 'espn_nhl.html'), 'NHL')
parse_scoresandodds(os.path.join(DATA, 'scoresandodds_nba.html'), 'NBA')
parse_scoresandodds(os.path.join(DATA, 'scoresandodds_nhl.html'), 'NHL')
parse_soccerstats_corners(os.path.join(DATA, 'soccerstats_france2_corners.html'), 'France Ligue 2')
parse_soccerstats_corners(os.path.join(DATA, 'soccerstats_ekstraklasa_corners.html'), 'Ekstraklasa')
parse_totalcorner(os.path.join(DATA, 'totalcorner_today.html'))
parse_olbg(os.path.join(DATA, 'olbg_tennis.html'), 'Tennis')
parse_olbg(os.path.join(DATA, 'olbg_football.html'), 'Football')