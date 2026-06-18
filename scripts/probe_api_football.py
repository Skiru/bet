import json
import os

import requests


def get_api_key():
    dot_env_path = os.path.join(os.getcwd(), '.env')
    if os.path.exists(dot_env_path):
        with open(dot_env_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('API_FOOTBALL_KEY='):
                    val = line.split('=', 1)[1].strip()
                    if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")):
                        val = val[1:-1]
                    return val
    return os.environ.get('API_FOOTBALL_KEY')

def make_request(endpoint, params):
    api_key = get_api_key()
    headers = {
        'x-apisports-key': api_key
    }
    url = f"https://v3.football.api-sports.io{endpoint}"
    response = requests.get(url, headers=headers, params=params)
    return response

def main():
    results = {}

    # Call 1: Fixture discovery
    print("Call 1: Fixture discovery")
    res1 = make_request('/fixtures', {'league': '39', 'season': '2025', 'status': 'FT-AET-PEN'})
    data1 = res1.json()
    results['call_1'] = {
        'status_code': res1.status_code,
        'errors': data1.get('errors', []),
        'results_count': data1.get('results', 0)
    }

    if data1.get('results', 0) == 0:
        print("No fixtures found for 2025. Trying 2024.")
        res1 = make_request('/fixtures', {'league': '39', 'season': '2024', 'status': 'FT-AET-PEN'})
        data1 = res1.json()
        results['call_1_fallback'] = {
            'status_code': res1.status_code,
            'errors': data1.get('errors', []),
            'results_count': data1.get('results', 0)
        }
        season = '2024'
    else:
        season = '2025'

    if data1.get('results', 0) == 0:
        print("No fixtures found.")
        print(json.dumps(results, indent=2))
        return

    fixture = data1['response'][0]
    fixture_id = fixture['fixture']['id']
    home_team_id = fixture['teams']['home']['id']
    away_team_id = fixture['teams']['away']['id']

    results['fixture_id'] = fixture_id
    results['home_team_id'] = home_team_id
    results['away_team_id'] = away_team_id

    # Call 2: Rich fixture package
    print("Call 2: Rich fixture package")
    res2 = make_request('/fixtures', {'id': fixture_id})
    data2 = res2.json()
    results['call_2'] = {
        'status_code': res2.status_code,
        'errors': data2.get('errors', []),
        'has_statistics': 'statistics' in data2['response'][0] if data2.get('response') else False,
        'has_events': 'events' in data2['response'][0] if data2.get('response') else False,
        'has_lineups': 'lineups' in data2['response'][0] if data2.get('response') else False
    }

    # Call 3: H2H
    print("Call 3: H2H")
    res3 = make_request('/fixtures/headtohead', {'h2h': f"{home_team_id}-{away_team_id}"})
    data3 = res3.json()
    results['call_3'] = {
        'status_code': res3.status_code,
        'errors': data3.get('errors', []),
        'results_count': data3.get('results', 0)
    }

    # Call 4: Form proxy HOME (Recovery: fetch all for season and slice)
    print("Call 4: Form proxy HOME (Recovery)")
    res4 = make_request('/fixtures', {'team': home_team_id, 'league': '39', 'season': season})
    data4 = res4.json()
    results['call_4'] = {
        'status_code': res4.status_code,
        'errors': data4.get('errors', []),
        'results_count': data4.get('results', 0),
        'recovered_last_10': len([f for f in data4.get('response', []) if f['fixture']['status']['short'] in ('FT', 'AET', 'PEN')]) >= 10
    }

    # Call 5: Form proxy AWAY (Recovery: fetch all for season and slice)
    print("Call 5: Form proxy AWAY (Recovery)")
    res5 = make_request('/fixtures', {'team': away_team_id, 'league': '39', 'season': season})
    data5 = res5.json()
    results['call_5'] = {
        'status_code': res5.status_code,
        'errors': data5.get('errors', []),
        'results_count': data5.get('results', 0),
        'recovered_last_10': len([f for f in data5.get('response', []) if f['fixture']['status']['short'] in ('FT', 'AET', 'PEN')]) >= 10
    }

    print(json.dumps(results, indent=2))

if __name__ == '__main__':
    main()
