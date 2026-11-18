"""Compact per-game rows for hockey/basketball/volleyball (read-only)."""
import json, sqlite3, sys, gzip
DB = "/Users/mkoziol/projects/bet/data/sofa.db"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
out = gzip.open("games.jsonl.gz", "wt")
q = """select sport, event_id, start_ts,
 json_extract(event_json,'$.tournament.uniqueTournament.id'),
 json_extract(event_json,'$.tournament.uniqueTournament.name'),
 json_extract(event_json,'$.tournament.name'),
 json_extract(event_json,'$.tournament.category.name'),
 json_extract(event_json,'$.season.id'),
 json_extract(event_json,'$.season.name'),
 json_extract(event_json,'$.season.year'),
 json_extract(event_json,'$.roundInfo.round'),
 json_extract(event_json,'$.roundInfo.name'),
 json_extract(event_json,'$.homeTeam.id'), json_extract(event_json,'$.awayTeam.id'),
 json_extract(event_json,'$.homeTeam.name'), json_extract(event_json,'$.awayTeam.name'),
 json_extract(event_json,'$.status.type'), json_extract(event_json,'$.status.description'),
 json_extract(event_json,'$.winnerCode'),
 json_extract(event_json,'$.homeScore.current'), json_extract(event_json,'$.awayScore.current'),
 json_extract(event_json,'$.homeTeam.gender')
 from sofa_listed_event where sport in ('ice-hockey','basketball','volleyball') and start_ts > 1500000000"""
cols = "sport id ts ut_id ut_name t_name cat season_id season_name season_year round round_name h a hn an st sdesc win hs as gender".split()
n = 0
for row in con.execute(q):
    out.write(json.dumps(dict(zip(cols, row))) + "\n"); n += 1
print(n)
