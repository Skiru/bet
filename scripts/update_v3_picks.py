#!/usr/bin/env python3
"""Update picks-ledger.csv: settle Apr 23 night picks + PK-210/211, add new Apr 24 v3 picks."""
import csv
from datetime import datetime

LEDGER = 'betting/journal/picks-ledger.csv'

# Read existing
with open(LEDGER, 'r') as f:
    reader = csv.reader(f)
    header = next(reader)
    rows = list(reader)

# Settlement map: pick_id -> (status, pnl, notes_append)
settlements = {
    'PK-20260423-90': ('lost', '0.00', 'SETTLED: LAK 2-4 COL = 6 goals OVER. LOST.'),
    'PK-20260423-91': ('won', '0.00', 'SETTLED: OTT 1-2 CAR = 3 goals UNDER. WON.'),
    'PK-20260423-93': ('won', '0.00', 'SETTLED: BOS 2-4 NYY. Yankees WON.'),
    'PK-20260423-95': ('lost', '0.00', 'SETTLED: NYM 10-8 MIN. Mets won. Twins LOST.'),
    'PK-20260423-83': ('won', '0.00', 'SETTLED: GSK 1-3 Fenerbahce = 4 sets. O3.5 WON.'),
    'PK-210': ('won', '0.00', 'SETTLED: BOS 2-4 NYY. Yankees WON. Game at 00:10 CEST.'),
    'PK-211': ('won', '0.00', 'SETTLED: BOS 1-3 BUF = 4 goals. U6.5 WON. Game at 01:00 CEST.'),
}

# Apply settlements
status_col = header.index('status')
pnl_col = header.index('pnl_pln')
notes_col = header.index('notes')
pick_id_col = header.index('pick_id')

for row in rows:
    pid = row[pick_id_col]
    if pid in settlements:
        status, pnl, note = settlements[pid]
        row[status_col] = status
        row[pnl_col] = pnl
        if row[notes_col]:
            row[notes_col] = row[notes_col] + '; ' + note
        else:
            row[notes_col] = note

# New picks to add
now = datetime.now().strftime('%Y-%m-%d %H:%M')
new_picks = [
    # betting_day,pick_id,event,sport,competition,market,selection,bookmaker,bookmaker_odds,market_best_odds,price_gap_pct,odds_checked_at_local,stake_pln,risk_tier,confidence_1_5,status,pnl_pln,stat_sources,market_sources,verification_sources,main_reason,main_risk,notes
    ['2026-04-24','PK-302','Barry Hawkins vs Mark Williams','snooker','World Championship','moneyline','Williams ML','Betclic','1.70','1.70','0.00',now,'0.00','low','3','pending','','OddsPortal','OddsPortal','','Williams higher-ranked, Crucible experience, odds fair','Long-format match volatility; Hawkins Crucible pedigree','CONDITIONAL >= 1.65; snooker World Championship R2'],
    ['2026-04-24','PK-303','Vegas Golden Knights vs Utah Mammoth','hockey','NHL Playoffs','moneyline','Utah Mammoth ML','Betclic','1.91','1.91','0.00',now,'0.00','medium','3','pending','','SBR|PicksWise','SBR','PicksWise','Pickswise backs Mammoth ML. Home ice. Vegas first regulation loss under Tortorella','Vegas strong team; 50/50 game','CONDITIONAL >= 1.85; NHL Playoffs G4 03:30 CEST'],
    ['2026-04-24','PK-304','Montreal Canadiens vs Tampa Bay Lightning','hockey','NHL Playoffs','moneyline','Montreal ML','Betclic','1.83','1.83','0.00',now,'0.00','medium','3','pending','','SBR','SBR','','Home ice advantage; 63% public; playoff momentum','Tampa Bay experience and goaltending','CONDITIONAL >= 1.75; NHL Playoffs G4 01:00 CEST'],
    ['2026-04-24','PK-305','Detroit Tigers vs Cincinnati Reds','baseball','MLB','moneyline','Detroit Tigers ML','Betclic','1.74','1.74','0.00',now,'0.00','medium','3','pending','','SBR|PicksWise','SBR','PicksWise','Pickswise 4-star: Framber Valdez strong; Abbott 0-2 struggling','Road game; Abbott bounce-back potential','CONDITIONAL >= 1.65; MLB 00:40 CEST'],
    ['2026-04-24','PK-306','Herlev vs Herning Blue Fox','hockey','Denmark Metal Ligaen','moneyline','Blue Fox ML','Betclic','1.68','1.68','0.00',now,'0.00','low','3','pending','','BetExplorer|OLBG','BetExplorer','OLBG','OLBG 67% consensus; Blue Fox strong; Herlev bottom','Danish league limited analysis depth; Herlev home ice','CONDITIONAL >= 1.60; Danish hockey 20:30'],
    ['2026-04-24','PK-307','Ottawa Senators vs Carolina Hurricanes','hockey','NHL Playoffs','puck_totals','Under 5.5 goals','Betclic','2.00','2.00','0.00',now,'0.00','medium','3','pending','','SBR|PicksWise','SBR','PicksWise','Pickswise backs U5.5 (+100). Playoff tightening. G3 result 1-2 (3 goals)','Ottawa home offense boost; season avg 6.39','CONDITIONAL >= 1.90; NHL Playoffs G4 25 Apr 21:00 CEST'],
    ['2026-04-24','PK-308','Cleveland Guardians vs Toronto Blue Jays','baseball','MLB','moneyline','Cleveland ML','Betclic','1.77','1.77','0.00',now,'0.00','medium','3','pending','','SBR','SBR','','G. Williams 3-1 strong arm vs aging Scherzer','Scherzer ace-caliber on his day; Toronto home','CONDITIONAL >= 1.70; MLB 01:07 CEST'],
    ['2026-04-24','PK-309','Montreal vs Tampa Bay','hockey','NHL Playoffs','puck_totals','Under 6 goals','Betclic','1.98','1.98','0.00',now,'0.00','medium','3','pending','','SBR','SBR','','SBR line 6 (U6 -102). Playoff hockey lower scoring','Both teams capable of offense','CONDITIONAL >= 1.90; NHL Playoffs G4 01:00 CEST'],
]

rows.extend(new_picks)

# Write back
with open(LEDGER, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(header)
    writer.writerows(rows)

print(f'Updated {LEDGER}: {len(settlements)} settled, {len(new_picks)} new picks added.')
print(f'Total rows: {len(rows)}')
