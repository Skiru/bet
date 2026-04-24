#!/usr/bin/env python3
"""Add new v2 picks to picks-ledger.csv."""

new_picks = [
    '2026-04-24,PK-207,RB Leipzig vs Union Berlin,football,Bundesliga,shots,Over 16.5 Leipzig shots,Betclic,1.75,1.75,0.00,2026-04-24 07:55,0.00,low,4,pending,,ZawodTyper|BetExplorer,BetExplorer,,ZT Magdon: Leipzig 19+24 shots last 2. Union deep block = shots.,Union park the bus differently; Leipzig rotation,CONDITIONAL >= 1.70; v2 morning analysis',
    '2026-04-24,PK-203,RB Leipzig vs Union Berlin,football,Bundesliga,corners_goals,O1.5 goals + O7.5 CK (bet builder),Betclic,1.50,1.50,0.00,2026-04-24 07:55,0.00,low,4,pending,,ZawodTyper|SoccerStats,BetExplorer,,ZT Kowalski: Leipzig avg 9.7 CK total 8/10 home O7.5. Union 9/10 away O7.5.,Both lines near averages; could undershoot,CONDITIONAL >= 1.45; SAME MATCH as PK-207',
    '2026-04-24,PK-208,Palmeiras vs Jacuipense,football,Copa do Brasil,corners,Over 9.5 corners,Betclic,1.50,1.50,0.00,2026-04-24 07:55,0.00,low,4,pending,,ZawodTyper|TotalCorner,ZawodTyper,,ZT Gebczynski: Palmeiras own CK 9+8+7+11+5+8. Total CK 12+11+9+13+13+10.,4th tier opponent may not generate many corners,CONDITIONAL >= 1.45; Copa do Brasil 00:30',
    '2026-04-24,PK-209,Napoli vs Cremonese,football,Coppa Italia,corners,Over 8.5 corners,Betclic,1.55,1.55,0.00,2026-04-24 07:55,0.00,low,3,pending,,ZawodTyper|BetExplorer,BetExplorer,,ZT Nowacki: Napoli dominated corners+shots+chances in first leg. Cremonese Serie B.,Napoli rest key players; cup match lower intensity,CONDITIONAL >= 1.50; Coppa Italia semifinal',
    '2026-04-24,PK-205,Stade Brestois vs RC Lens,football,Ligue 1,match_winner,Lens ML,Betclic,1.69,1.69,0.00,2026-04-24 07:55,0.00,medium,4,pending,,ZawodTyper|SoccerStats,BetExplorer,,ZT Rataj0611: Lens 2nd 4pts behind PSG title chase. 4/4 H2H wins vs Brest.,Brest home or CL focus; Lens fatigue,CONDITIONAL >= 1.60; coupon leg only',
    '2026-04-24,PK-206,Ben Shelton vs Dino Prizmic,tennis,ATP Madrid,match_winner,Shelton ML,Betclic,1.57,1.57,0.00,2026-04-24 07:55,0.00,medium,3,pending,,ZawodTyper|BetExplorer,BetExplorer,,ZT Mateusz P 64%: Shelton won Munich ATP 500 clay. Prizmic 87 fatigue from qualifiers.,Prizmic upset; Shelton clay consistency,CONDITIONAL >= 1.50; coupon leg only',
    '2026-04-24,PK-210,New York Yankees vs Boston Red Sox,baseball,MLB,moneyline,Yankees ML,Betclic,1.62,1.62,0.00,2026-04-24 07:55,0.00,medium,3,pending,,ZawodTyper|ESPN,ESPN,,ZT Sh Ha: Schlittler ERA 1.95 36K/27IP vs Tolle minor league recall. NYY 5W streak.,Fenway rivalry; small sample,CONDITIONAL >= 1.55; night 00:10',
    '2026-04-24,PK-211,Boston Bruins vs Buffalo Sabres,hockey,NHL Playoffs,puck_totals,Under 6.5 goals,Betclic,1.50,1.50,0.00,2026-04-24 07:55,0.00,medium,3,pending,,ZawodTyper|hockey-reference,ZawodTyper,,ZT Magdon: BUF new defensive scheme for Pastrnak. Playoff tightening. Game 3 BOS home.,BOS offense at home; series escalation,CONDITIONAL >= 1.45; NHL Playoffs G3',
    '2026-04-24,PK-212,Poitiers vs Paris,volleyball,Ligue A France,set_points,Paris +5.5 pts 1st set,Betclic,1.65,1.65,0.00,2026-04-24 07:55,0.00,medium,3,pending,,ZawodTyper,ZawodTyper,,ZT Korostenski 63%: Molotkov returns. Paris at 6.5 ML is matrix. Won French Cup beat Tours 3:0 away.,Paris still lost G1 badly; momentum with Poitiers,CONDITIONAL >= 1.60; best value argument',
]

# Read existing, check for duplicates
with open('betting/journal/picks-ledger.csv') as f:
    existing = f.read()

existing_ids = set()
for line in existing.strip().split('\n'):
    parts = line.split(',')
    if len(parts) >= 2:
        existing_ids.add(parts[1])

added = 0
with open('betting/journal/picks-ledger.csv', 'a') as f:
    for pick in new_picks:
        pick_id = pick.split(',')[1]
        if pick_id not in existing_ids:
            f.write(pick + '\n')
            added += 1
            print(f'  Added: {pick_id}')
        else:
            print(f'  Skipped (exists): {pick_id}')

print(f'\nTotal added: {added}')
