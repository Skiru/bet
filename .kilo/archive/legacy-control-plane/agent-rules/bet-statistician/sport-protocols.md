# Sport Protocols — Statistician Reference

## §3.0 Market Ranking Protocol (MANDATORY per candidate)
1. List ALL bettable statistical markets for the sport.
2. Per market: L10 avg, H2H avg (specific stat!), L5 avg, bookmaker line, hit rate.
3. Safety = min(hit_rate_L10, hit_rate_H2H). Tiebreaker: margin vs line.
4. Rank ALL. Pick TOP safety score — not favorite/default.
5. Three-Way Cross-Check: L10 + H2H + L5. All must align. 2/3 conflict → DOWNGRADE.

## Football §3.1M — Multi-Market Table (MANDATORY)
| Market | TeamA avg | TeamB avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
|--------|-----------|-----------|---------|------|---------|---------|--------|
| Fouls O/U X.5 | | | | | | | |
| Cards O/U X.5 | | | | | | | |
| Corners O/U X.5 | | | | | | | |
| Shots O/U X.5 | | | | | | | |
| Goals O/U X.5 | | | | | | | |

## Tennis §3.2M — Multi-Market Table
| Market | P1 avg | P2 avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
|--------|--------|--------|---------|------|---------|---------|--------|
| Total Games O/U | | | | | | | |
| Total Sets O/U | | | | | | | |
| P1 Games O/U | | | | | | | |
| P2 Games O/U | | | | | | | |

## Basketball §3.3M — Multi-Market Table
| Market | TeamA avg | TeamB avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
|--------|-----------|-----------|---------|------|---------|---------|--------|
| Total Points O/U | | | | | | | |
| Team A Total O/U | | | | | | | |
| Team B Total O/U | | | | | | | |
| Q1 Total O/U | | | | | | | |

## Volleyball §3.4M — Multi-Market Table
| Market | TeamA avg | TeamB avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
|--------|-----------|-----------|---------|------|---------|---------|--------|
| Total Points O/U | | | | | | | |
| Sets O/U | | | | | | | |
| Set Handicap | | | | | | | |

## Hockey §3.5M — Multi-Market Table
| Market | TeamA avg | TeamB avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
|--------|-----------|-----------|---------|------|---------|---------|--------|
| Total Shots O/U | | | | | | | |
| Total Goals O/U | | | | | | | |
| Period Goals | | | | | | | |

## §S3 Output Template (10 sections per candidate)
§S3.1 H2H Analysis → §S3.2 Form Table → §S3.3 Market Ranking (≥3 rows) →
§S3.4 Three-Way Cross-Check → §S3.5 Coach/Roster → §S3.6 Injuries →
§S3.7 Top 3 Markets → §S3.8 Recommended Market → §S3.9 Sources → §S3.10 Depth Proof

## Data Provenance (§3.0d)
Every stat MUST have: source name, exact data point, fetch reference.
BANNED as sole cell content: "checked", "verified", "good", "fine", "OK", "done", "N/A".
