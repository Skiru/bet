#!/usr/bin/env python3
"""Deep ESPN analysis for May 4, 2026 fixtures.

Fetches L5/L10 per-game stats for all teams in key fixtures,
computes market averages, and outputs analysis for coupon building.
"""
import json
import requests
import sys
from datetime import datetime, timezone

BASE = "http://site.api.espn.com/apis/site/v2/sports"

STAT_KEYS_SOCCER = ["wonCorners", "foulsCommitted", "yellowCards", "totalShots", 
                     "shotsOnTarget", "possessionPct", "offsides", "saves",
                     "totalTackles", "interceptions"]
STAT_KEYS_NHL = ["blockedShots", "hits", "shotsTotal", "penalties", "penaltyMinutes",
                 "faceoffsWon", "faceoffPercent", "powerPlayGoals", "takeaways", "giveaways"]
STAT_KEYS_NBA = ["totalRebounds", "assists", "steals", "blocks", "turnovers", "fouls"]


def get_team_stats(sport, league, team_id, team_name, stat_keys, n=5):
    """Fetch per-game stats for a team's last N finished games."""
    r = requests.get(f"{BASE}/{sport}/{league}/teams/{team_id}/schedule", timeout=10)
    events = r.json().get("events", [])
    
    now = datetime.now(timezone.utc)
    finished = []
    for e in events:
        st = e.get("status", {}).get("type", {})
        if st.get("state") == "post" or st.get("name") in ("STATUS_FULL_TIME", "STATUS_FINAL"):
            finished.append(e)
        else:
            d = e.get("date", "")
            if d:
                try:
                    gd = datetime.fromisoformat(d.rstrip("Z")).replace(tzinfo=timezone.utc)
                    if gd < now:
                        comps = e.get("competitions", [{}])[0].get("competitors", [])
                        if any(c.get("score") is not None for c in comps):
                            finished.append(e)
                except (ValueError, TypeError):
                    pass
    
    finished.sort(key=lambda x: x.get("date", ""), reverse=True)
    
    stats_agg = {k: [] for k in stat_keys}
    goals = []
    
    for game in finished[:n]:
        eid = game.get("id", "")
        try:
            r2 = requests.get(f"{BASE}/{sport}/{league}/summary",
                              params={"event": eid}, timeout=10)
            d = r2.json()
            box = d.get("boxscore", {})
            
            # Get score
            header = d.get("header", {})
            for comp in header.get("competitions", [{}])[0].get("competitors", []):
                cname = comp.get("team", {}).get("displayName", "")
                if team_name.lower() in cname.lower() or cname.lower() in team_name.lower():
                    try:
                        goals.append(float(comp.get("score", 0)))
                    except (ValueError, TypeError):
                        pass
            
            for t in box.get("teams", []):
                tname = t.get("team", {}).get("displayName", "")
                if team_name.lower() in tname.lower() or tname.lower() in team_name.lower():
                    for s in t.get("statistics", []):
                        sname = s.get("name", "")
                        if sname in stat_keys:
                            try:
                                v = float(s.get("displayValue", "0").replace("%", "").strip() or "0")
                                stats_agg[sname].append(v)
                            except (ValueError, TypeError):
                                pass
        except Exception as e:
            print(f"  [warn] Failed for event {eid}: {e}", file=sys.stderr)
    
    if goals:
        stats_agg["goals"] = goals
    
    return stats_agg


def analyze_soccer(league, event_id, home_name, away_name, home_id, away_id):
    """Full analysis for a soccer match."""
    print(f"\n{'='*70}")
    print(f"  ⚽ {home_name} vs {away_name}")
    print(f"{'='*70}")
    
    # Get odds
    try:
        r = requests.get(f"{BASE}/soccer/{league}/summary",
                         params={"event": event_id}, timeout=10)
        d = r.json()
        odds = d.get("odds", [])
        if odds:
            o = odds[0]
            prov = o.get("provider", {}).get("name", "")
            ou = o.get("overUnder", "")
            hml = o.get("homeTeamOdds", {}).get("moneyLine", "")
            aml = o.get("awayTeamOdds", {}).get("moneyLine", "")
            dml = o.get("drawOdds", {}).get("moneyLine", "")
            spr = o.get("spread", "")
            print(f"  📊 ODDS ({prov}): Home={hml} Draw={dml} Away={aml} | O/U={ou} Spread={spr}")
        h2h = d.get("headToHeadGames", [])
        if h2h:
            print(f"  🔄 H2H: {len(h2h)} previous meetings")
    except:
        pass
    
    # Home team L5
    print(f"\n  --- {home_name} (HOME) L5 ---")
    hs = get_team_stats("soccer", league, home_id, home_name, STAT_KEYS_SOCCER, n=5)
    for k in STAT_KEYS_SOCCER + ["goals"]:
        vals = hs.get(k, [])
        if vals:
            avg = sum(vals)/len(vals)
            print(f"    {k:20s}: L5avg={avg:5.1f} | {vals}")
    
    # Away team L5
    print(f"\n  --- {away_name} (AWAY) L5 ---")
    aws = get_team_stats("soccer", league, away_id, away_name, STAT_KEYS_SOCCER, n=5)
    for k in STAT_KEYS_SOCCER + ["goals"]:
        vals = aws.get(k, [])
        if vals:
            avg = sum(vals)/len(vals)
            print(f"    {k:20s}: L5avg={avg:5.1f} | {vals}")
    
    # Combined markets analysis
    print(f"\n  --- COMBINED MARKET ANALYSIS ---")
    for stat, label in [("wonCorners", "Corners"), ("foulsCommitted", "Fouls"),
                        ("yellowCards", "Cards"), ("totalShots", "Shots"),
                        ("shotsOnTarget", "SoT"), ("goals", "Goals")]:
        h_vals = hs.get(stat, [])
        a_vals = aws.get(stat, [])
        if h_vals and a_vals:
            h_avg = sum(h_vals)/len(h_vals)
            a_avg = sum(a_vals)/len(a_vals)
            total = h_avg + a_avg
            print(f"    {label:12s} Total: {total:5.1f} (H={h_avg:.1f} + A={a_avg:.1f})")


def analyze_nhl(event_id, home_name, away_name, home_id, away_id):
    """Full analysis for an NHL match."""
    print(f"\n{'='*70}")
    print(f"  🏒 {home_name} vs {away_name}")
    print(f"{'='*70}")
    
    # Get odds
    try:
        r = requests.get(f"{BASE}/hockey/nhl/summary", params={"event": event_id}, timeout=10)
        d = r.json()
        odds = d.get("odds", [])
        if odds:
            o = odds[0]
            prov = o.get("provider", {}).get("name", "")
            ou = o.get("overUnder", "")
            hml = o.get("homeTeamOdds", {}).get("moneyLine", "")
            aml = o.get("awayTeamOdds", {}).get("moneyLine", "")
            print(f"  📊 ODDS ({prov}): Home={hml} Away={aml} | O/U={ou}")
    except:
        pass
    
    print(f"\n  --- {home_name} (HOME) L5 ---")
    hs = get_team_stats("hockey", "nhl", home_id, home_name, STAT_KEYS_NHL, n=5)
    for k in STAT_KEYS_NHL:
        vals = hs.get(k, [])
        if vals:
            avg = sum(vals)/len(vals)
            print(f"    {k:20s}: L5avg={avg:5.1f} | {vals}")
    
    print(f"\n  --- {away_name} (AWAY) L5 ---")
    aws = get_team_stats("hockey", "nhl", away_id, away_name, STAT_KEYS_NHL, n=5)
    for k in STAT_KEYS_NHL:
        vals = aws.get(k, [])
        if vals:
            avg = sum(vals)/len(vals)
            print(f"    {k:20s}: L5avg={avg:5.1f} | {vals}")
    
    print(f"\n  --- COMBINED MARKET ANALYSIS ---")
    for stat, label in [("shotsTotal", "Shots"), ("hits", "Hits"), 
                        ("blockedShots", "Blocks"), ("penalties", "Penalties"),
                        ("penaltyMinutes", "PIM")]:
        h_vals = hs.get(stat, [])
        a_vals = aws.get(stat, [])
        if h_vals and a_vals:
            h_avg = sum(h_vals)/len(h_vals)
            a_avg = sum(a_vals)/len(a_vals)
            total = h_avg + a_avg
            print(f"    {label:12s} Total: {total:5.1f} (H={h_avg:.1f} + A={a_avg:.1f})")


def analyze_nba(event_id, home_name, away_name, home_id, away_id):
    """Full analysis for an NBA match."""
    print(f"\n{'='*70}")
    print(f"  🏀 {home_name} vs {away_name}")
    print(f"{'='*70}")
    
    try:
        r = requests.get(f"{BASE}/basketball/nba/summary", params={"event": event_id}, timeout=10)
        d = r.json()
        odds = d.get("odds", [])
        if odds:
            o = odds[0]
            prov = o.get("provider", {}).get("name", "")
            ou = o.get("overUnder", "")
            hml = o.get("homeTeamOdds", {}).get("moneyLine", "")
            aml = o.get("awayTeamOdds", {}).get("moneyLine", "")
            spr = o.get("spread", "")
            print(f"  📊 ODDS ({prov}): Home={hml} Away={aml} | O/U={ou} Spread={spr}")
    except:
        pass
    
    print(f"\n  --- {home_name} (HOME) L5 ---")
    hs = get_team_stats("basketball", "nba", home_id, home_name, STAT_KEYS_NBA, n=5)
    for k in STAT_KEYS_NBA:
        vals = hs.get(k, [])
        if vals:
            avg = sum(vals)/len(vals)
            print(f"    {k:20s}: L5avg={avg:5.1f} | {vals}")
    
    print(f"\n  --- {away_name} (AWAY) L5 ---")
    aws = get_team_stats("basketball", "nba", away_id, away_name, STAT_KEYS_NBA, n=5)
    for k in STAT_KEYS_NBA:
        vals = aws.get(k, [])
        if vals:
            avg = sum(vals)/len(vals)
            print(f"    {k:20s}: L5avg={avg:5.1f} | {vals}")
    
    print(f"\n  --- COMBINED MARKET ANALYSIS ---")
    for stat, label in [("totalRebounds", "Rebounds"), ("assists", "Assists"),
                        ("turnovers", "Turnovers"), ("fouls", "Fouls")]:
        h_vals = hs.get(stat, [])
        a_vals = aws.get(stat, [])
        if h_vals and a_vals:
            h_avg = sum(h_vals)/len(h_vals)
            a_avg = sum(a_vals)/len(a_vals)
            total = h_avg + a_avg
            print(f"    {label:12s} Total: {total:5.1f} (H={h_avg:.1f} + A={a_avg:.1f})")


def get_team_id(sport, league, name):
    """Resolve team name to ESPN team ID."""
    r = requests.get(f"{BASE}/{sport}/{league}/teams", timeout=10)
    d = r.json()
    teams = []
    for s in d.get("sports", []):
        for l in s.get("leagues", []):
            for t in l.get("teams", []):
                teams.append(t.get("team", t))
    
    nl = name.lower()
    for t in teams:
        dn = t.get("displayName", "").lower()
        sn = t.get("shortDisplayName", "").lower()
        if nl == dn or nl == sn or nl in dn or dn in nl:
            return str(t.get("id", ""))
    return None


if __name__ == "__main__":
    print("=" * 70)
    print("  DEEP ESPN ANALYSIS — MAY 4, 2026")
    print("=" * 70)
    
    # Resolve team IDs first
    print("\nResolving team IDs...")
    
    teams = {
        "soccer/eng.1": {
            "Chelsea": None, "Nottingham Forest": None,
            "Manchester City": None, "Everton": None,
        },
        "soccer/esp.1": {"Real Sociedad": None, "Sevilla": None},
        "soccer/ita.1": {"Fiorentina": None, "AS Roma": None},
        "hockey/nhl": {"Carolina Hurricanes": None, "Philadelphia Flyers": None},
        "basketball/nba": {"New York Knicks": None, "Philadelphia 76ers": None},
    }
    
    for path, team_dict in teams.items():
        sport, league = path.split("/")
        for name in team_dict:
            tid = get_team_id(sport, league, name)
            team_dict[name] = tid
            print(f"  {name}: {tid}")
    
    # Soccer analyses
    epl = teams["soccer/eng.1"]
    analyze_soccer("eng.1", "740940", "Chelsea", "Nottingham Forest", epl["Chelsea"], epl["Nottingham Forest"])
    analyze_soccer("eng.1", "740941", "Everton", "Manchester City", epl["Everton"], epl["Manchester City"])
    
    esp = teams["soccer/esp.1"]
    analyze_soccer("esp.1", "748478", "Sevilla", "Real Sociedad", esp["Sevilla"], esp["Real Sociedad"])
    
    ita = teams["soccer/ita.1"]
    analyze_soccer("ita.1", "737125", "AS Roma", "Fiorentina", ita["AS Roma"], ita["Fiorentina"])
    
    # NHL
    nhl = teams["hockey/nhl"]
    analyze_nhl("401871411", "Carolina Hurricanes", "Philadelphia Flyers", nhl["Carolina Hurricanes"], nhl["Philadelphia Flyers"])
    
    # NBA
    nba = teams["basketball/nba"]
    analyze_nba("401871159", "New York Knicks", "Philadelphia 76ers", nba["New York Knicks"], nba["Philadelphia 76ers"])
    
    print("\n" + "=" * 70)
    print("  ANALYSIS COMPLETE")
    print("=" * 70)
