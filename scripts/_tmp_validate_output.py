"""Validate today's pipeline output quality."""
import json

data = json.load(open('betting/coupons/2026-05-27.json'))
print(f"Approved: {data['approved_count']}, Strong: {data['strong_count']}, Moderate: {data['moderate_count']}, Discovery: {data['discovery_count']}")
print(f"Core coupons: {len(data.get('core_coupons',[]))}, Combos: {len(data.get('combos',[]))}, Singles: {len(data.get('singles',[]))}")
print(f"Extended pool: {len(data.get('extended_pool',[]))}, Rejected: {len(data.get('rejected',[]))}")

# Sports distribution across all picks
sports = {}
markets = {}
all_picks = data.get('singles', []) + data.get('discovery_singles', [])
for c in data.get('core_coupons', []):
    all_picks.extend(c.get('legs', []))
for c in data.get('combos', []):
    all_picks.extend(c.get('legs', []))

for p in all_picks:
    s = p.get('sport', '?')
    m = p.get('market', '?')
    sports[s] = sports.get(s, 0) + 1
    markets[m] = markets.get(m, 0) + 1

print(f"\nSport distribution: {sports}")
print(f"Market distribution (top 10): {dict(sorted(markets.items(), key=lambda x: -x[1])[:10])}")

# Check quality markers
has_tipster = sum(1 for s in all_picks if s.get('tipster_backing') or s.get('tipster') or s.get('tipster_consensus'))
has_ev = sum(1 for s in all_picks if s.get('ev_pct') is not None)
has_safety = sum(1 for s in all_picks if s.get('safety_score') is not None)
has_gate = sum(1 for s in all_picks if s.get('gate_hits') is not None or s.get('gate_total') is not None)
print(f"\nQuality markers: tipster={has_tipster}/{len(all_picks)}, EV={has_ev}/{len(all_picks)}, safety={has_safety}/{len(all_picks)}, gate={has_gate}/{len(all_picks)}")

# Sample first 3 singles
print("\n--- First 3 singles ---")
for i, s in enumerate(data.get('singles', [])[:3]):
    print(f"{i+1}. {s.get('event','')} | {s.get('sport','')} | {s.get('market','')} | odds={s.get('odds','')} | safety={s.get('safety_score','')}")
    print(f"   gate={s.get('gate_hits','?')}/{s.get('gate_total','?')} | dir={s.get('direction','?')} | EV={s.get('ev_pct','?')}%")

# Check for football stat markets (should be present per learning)
football_stats = [p for p in all_picks if p.get('sport') == 'football' and p.get('market','') in ('corners', 'team_corners', 'cards', 'fouls', 'shots')]
print(f"\nFootball stat markets (corners/cards/fouls/shots): {len(football_stats)}")
if not football_stats:
    print("⚠️ WARNING: No football stat markets found! Learning says these are 75-84% hit rate.")
