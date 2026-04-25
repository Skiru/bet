#!/usr/bin/env python3
"""Append v17 picks to picks-ledger.csv"""
import os

LEDGER = os.path.join(os.path.dirname(__file__), '..', 'betting', 'journal', 'picks-ledger.csv')

v17_picks = [
    "2026-04-25,v17,PK-20260425-01,Heerenveen vs Fortuna Sittard,football,Eredivisie,game_totals,Over 2.5 goals,Betclic,1.50,1.55,-3.2,2026-04-25 12:00,0.00,low,5,pending,,ZawodTyper|BetExplorer,BetExplorer|OddsPortal,,ZT 10/10 O2.5 (100%); Eredivisie 62% O2.5; HEE 53GF/50GA,Streak regression,CONDITIONAL >=1.45; EV +20%; PEWNIAKI #1",
    "2026-04-25,v17,PK-20260425-02,FC Koln vs Bayer Leverkusen,football,Bundesliga,game_totals,Over 2.5 goals,Betclic,1.55,1.60,-3.1,2026-04-25 12:00,0.00,low,4,pending,,BetExplorer|ZawodTyper,BetExplorer|OddsPortal,,BuLi 63% O2.5; Leverkusen offensive; H2H avg 2.75 goals,Rhine derby tactical risk,CONDITIONAL >=1.50; EV +5.4%; PEWNIAKI #2",
    "2026-04-25,v17,PK-20260425-03,Mainz vs Bayern Munchen,football,Bundesliga,game_totals,Over 2.5 goals,Betclic,1.40,1.45,-3.4,2026-04-25 12:00,0.00,low,3,pending,,ZawodTyper|BetExplorer,BetExplorer|OddsPortal,,ZT 9/10 O2.5; BuLi 63% O2.5,Bayern dead rubber rotation,CONDITIONAL >=1.35; conf 3 (dead rubber)",
    "2026-04-25,v17,PK-20260425-04,Motor Lublin vs Falubaz Zielona Gora,speedway,PGE Ekstraliga R3,handicap,HC -3.5 points,Betclic,1.70,1.70,0.0,2026-04-25 12:00,0.00,medium,3,pending,,SpeedwayEkstraliga|SportoweFakty,SpeedwayEkstraliga,,Lublin 1st +60 diff; Zmarzlik home; Falubaz 7th -52,Unpredictable; lineup unconfirmed,CONDITIONAL verify HC line + lineup ~17:00",
    "2026-04-25,v17,PK-20260425-05,Denver Nuggets @ Minnesota Timberwolves,basketball,NBA Playoffs R1 G4,game_totals,Over 229.5 points,Betclic,1.85,1.90,-2.6,2026-04-25 12:00,0.00,medium,3,pending,,ESPN|ScoresAndOdds,BetExplorer|SBR,,Highest total; MIN leads 2-1; DEN must-win,Playoff defense tightens,CONDITIONAL >=1.80; 02:30 CEST",
    "2026-04-25,v17,PK-20260425-06,Arsenal vs Newcastle,football,Premier League,game_totals,Over 2.5 goals,Betclic,1.60,1.65,-3.0,2026-04-25 12:00,0.00,medium,3,pending,,PicksWise|BetIdeas,BetExplorer|OddsPortal,,PW 5star BTTS; Newcastle 18 consecutive scoring,Rice injured; CL Semi Apr 29 rotation,CONDITIONAL check lineup 17:30",
    "2026-04-25,v17,PK-20260425-07,Ugo Humbert vs Terence Atmane,tennis,ATP Madrid R1,game_totals,Over 20.5 games,Betclic,1.45,1.50,-3.3,2026-04-25 12:00,0.00,low,2,pending,,BetExplorer|TennisAbstract,BetExplorer|OddsPortal,,Odds ratio 1.18 GOOD; both main draw; clay altitude,LOW upset risk blowout pattern,CONDITIONAL >=1.40; conf 2 (blowout risk); O20.5 not O21.5",
    "2026-04-25,v17,PK-20260425-08,Zhao Xintong vs Ding Junhui,snooker,World Championship QF,frame_totals,Over 21.5 frames,Betclic,1.70,1.75,-2.9,2026-04-25 12:00,0.00,medium,3,pending,,BetExplorer|Flashscore,BetExplorer,,BO25 Chinese derby; 4-4 after S1 competitive,Ding dominates 13-5 = 18 frames UNDER,CONDITIONAL verify between-session market on Betclic",
    "2026-04-25,v17,PK-20260425-09,Aljamain Sterling vs Elves Zalal,mma,UFC FN Main Event FW 145lbs,method,Over 2.5 rounds,Betclic,1.55,1.60,-3.1,2026-04-25 12:00,0.00,medium,2,pending,,UFC.com|Tapology,BetExplorer,,Sterling former BW champ at FW; technical grinders; 5-round,FW transition unknown; early finish,CONDITIONAL >=1.50; 02:00 CEST; conf 2",
]

with open(LEDGER, 'a') as f:
    for pick in v17_picks:
        f.write(pick + '\n')

print(f"Appended {len(v17_picks)} v17 picks")
