import sqlite3, json, gzip
con=sqlite3.connect("file:/Users/mkoziol/projects/bet/data/sofa.db?mode=ro",uri=True)
q="""select event_id, """+",".join(f"json_extract(event_json,'$.homeScore.period{i}'),json_extract(event_json,'$.awayScore.period{i}')" for i in range(1,6))+""" from sofa_listed_event where sport='volleyball' and start_ts between 1719792000 and 1751328000"""
out=gzip.open("vb_periods_dev.jsonl.gz","wt")
for r in con.execute(q): out.write(json.dumps(r)+"\n")
