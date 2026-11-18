"""Compact football listing rows (no outcome analysis; scores only to rebuild tables)."""
import sqlite3, sys
import pandas as pd
sys.path.insert(0, "src")
from bet.sofa.comparability import FRIENDLY_COMPETITION_IDS
OUT = sys.argv[1]
c = sqlite3.connect("file:data/sofa.db?mode=ro", uri=True)
q = """select event_id, start_ts,
 json_extract(event_json,'$.tournament.uniqueTournament.id') ut,
 json_extract(event_json,'$.tournament.uniqueTournament.name') ut_name,
 json_extract(event_json,'$.tournament.id') tid,
 json_extract(event_json,'$.tournament.name') tname,
 json_extract(event_json,'$.tournament.isGroup') is_group,
 json_extract(event_json,'$.tournament.category.name') cat,
 json_extract(event_json,'$.season.id') season,
 json_extract(event_json,'$.season.year') season_year,
 json_extract(event_json,'$.roundInfo.round') rnd,
 json_extract(event_json,'$.roundInfo.name') rnd_name,
 json_extract(event_json,'$.roundInfo.cupRoundType') cup_rt,
 json_extract(event_json,'$.status.type') st,
 json_extract(event_json,'$.homeTeam.id') hid,
 json_extract(event_json,'$.awayTeam.id') aid,
 json_extract(event_json,'$.homeTeam.name') hname,
 json_extract(event_json,'$.awayTeam.name') aname,
 json_extract(event_json,'$.homeTeam.national') hnat,
 json_extract(event_json,'$.homeTeam.gender') gender,
 coalesce(json_extract(event_json,'$.homeScore.normaltime'), json_extract(event_json,'$.homeScore.current')) hg,
 coalesce(json_extract(event_json,'$.awayScore.normaltime'), json_extract(event_json,'$.awayScore.current')) ag,
 json_extract(event_json,'$.homeScore.current') hg_cur,
 json_extract(event_json,'$.awayScore.current') ag_cur,
 json_extract(event_json,'$.isAwarded') awarded
 from sofa_listed_event where sport='football' and start_ts >= 1546300800"""
df = pd.read_sql_query(q, c)
df["friendly"] = df.ut.isin(FRIENDLY_COMPETITION_IDS)
df.to_pickle(OUT)
print(len(df))
