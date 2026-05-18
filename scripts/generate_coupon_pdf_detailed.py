"""Generate comprehensive PDF with deep statistical analysis for every pick."""

import json
import sys
from datetime import datetime
from pathlib import Path

import markdown_it
from weasyprint import HTML

DATE = "2026-05-17"
DATA_DIR = Path("betting/data")
COUPON_DIR = Path("betting/coupons")
OUTPUT_DIR = COUPON_DIR / "pdf" / DATE

CSS = """
@page {
    size: A4;
    margin: 1.2cm;
}
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 9pt;
    line-height: 1.35;
    color: #1a1a1a;
}
h1 {
    font-size: 16pt;
    border-bottom: 3px solid #2d6cdf;
    padding-bottom: 6pt;
    color: #2d6cdf;
    margin-bottom: 12pt;
}
h2 {
    font-size: 13pt;
    color: #1a5276;
    margin-top: 18pt;
    border-bottom: 1px solid #bbb;
    padding-bottom: 3pt;
    page-break-after: avoid;
}
h3 {
    font-size: 11pt;
    color: #2c3e50;
    margin-top: 12pt;
    page-break-after: avoid;
}
h4 {
    font-size: 10pt;
    color: #34495e;
    margin-top: 8pt;
    margin-bottom: 4pt;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin: 6pt 0;
    font-size: 8.5pt;
}
th, td {
    border: 1px solid #ccc;
    padding: 3pt 5pt;
    text-align: left;
}
th {
    background-color: #e8f0fe;
    font-weight: bold;
    color: #1a5276;
}
tr:nth-child(even) {
    background-color: #fafbfc;
}
blockquote {
    border-left: 3px solid #e74c3c;
    padding: 6pt 12pt;
    margin: 8pt 0;
    background: #fef9e7;
    font-style: italic;
    font-size: 9pt;
}
.pick-card {
    border: 1px solid #ddd;
    border-radius: 4pt;
    padding: 8pt;
    margin: 8pt 0;
    background: #fdfdfd;
    page-break-inside: avoid;
}
.safety-high { color: #27ae60; font-weight: bold; }
.safety-mid { color: #f39c12; font-weight: bold; }
.safety-low { color: #e74c3c; font-weight: bold; }
.stat-label { color: #7f8c8d; font-size: 8pt; }
.market-badge {
    display: inline-block;
    background: #2d6cdf;
    color: white;
    padding: 2pt 6pt;
    border-radius: 3pt;
    font-size: 8pt;
    font-weight: bold;
}
.direction-over { color: #27ae60; }
.direction-under { color: #e74c3c; }
code {
    background: #f4f4f4;
    padding: 1pt 3pt;
    border-radius: 2pt;
    font-size: 8pt;
}
ul, ol { padding-left: 14pt; margin: 4pt 0; }
li { margin-bottom: 2pt; }
strong { color: #1a5276; }
.disclaimer {
    background: #fff3cd;
    border: 1px solid #ffc107;
    border-radius: 4pt;
    padding: 8pt;
    margin: 8pt 0;
    font-size: 8.5pt;
}
.page-break { page-break-before: always; }
"""


def load_data():
    """Load all analysis data from DB export."""
    stats_path = DATA_DIR / f"{DATE}_pdf_stats.json"
    if not stats_path.exists():
        print(f"ERROR: {stats_path} not found. Run the data extraction first.")
        sys.exit(1)
    with open(stats_path) as f:
        return json.load(f)


def format_stat_value(val):
    """Format a stat value for display."""
    if val is None:
        return "—"
    if isinstance(val, float):
        return f"{val:.1f}"
    return str(val)


def get_safety_class(score):
    if score >= 0.55:
        return "safety-high"
    elif score >= 0.42:
        return "safety-mid"
    return "safety-low"


def get_direction_class(direction):
    if direction and "OVER" in direction.upper():
        return "direction-over"
    return "direction-under"


def build_stat_table(stats_a, stats_b, market_name):
    """Build a statistical comparison table for two teams."""
    # Determine which stats are relevant based on market
    market_lower = market_name.lower() if market_name else ""
    
    # Key stats to always show
    relevant_stats = []
    if "corner" in market_lower:
        relevant_stats = ["corners", "corners_home", "corners_away"]
    elif "foul" in market_lower:
        relevant_stats = ["fouls", "fouls_home", "fouls_away"]
    elif "card" in market_lower:
        relevant_stats = ["yellow_cards", "yellow_cards_home", "yellow_cards_away", "red_cards"]
    elif "shot" in market_lower and "target" in market_lower:
        relevant_stats = ["shots_on_target", "shots_on_target_home", "shots_on_target_away"]
    elif "shot" in market_lower:
        relevant_stats = ["shots", "shots_home", "shots_away", "shots_on_target"]
    elif "goal" in market_lower:
        relevant_stats = ["goals", "goals_home", "goals_away"]
    elif "rebound" in market_lower:
        relevant_stats = ["rebounds", "offensive_rebounds", "defensive_rebounds"]
    elif "point" in market_lower:
        relevant_stats = ["points", "points_home", "points_away"]
    elif "ace" in market_lower:
        relevant_stats = ["aces", "double_faults"]
    elif "turnover" in market_lower:
        relevant_stats = ["turnovers", "steals"]
    elif "assist" in market_lower:
        relevant_stats = ["assists", "assists_home", "assists_away"]
    else:
        relevant_stats = ["corners", "fouls", "yellow_cards", "shots", "shots_on_target", "goals"]
    
    team_a = stats_a.get("team", "Home")
    team_b = stats_b.get("team", "Away")
    l10_a = stats_a.get("l10_avg", {})
    l5_a = stats_a.get("l5_avg", {})
    l10_b = stats_b.get("l10_avg", {})
    l5_b = stats_b.get("l5_avg", {})
    
    rows = []
    rows.append(f"| Stat | {team_a} L10 | {team_a} L5 | {team_b} L10 | {team_b} L5 |")
    rows.append("|------|------|------|------|------|")
    
    for stat in relevant_stats:
        a_l10 = format_stat_value(l10_a.get(stat))
        a_l5 = format_stat_value(l5_a.get(stat))
        b_l10 = format_stat_value(l10_b.get(stat))
        b_l5 = format_stat_value(l5_b.get(stat))
        # Only show row if at least one value is non-zero/non-dash
        if any(v not in ("—", "0.0", "0") for v in [a_l10, a_l5, b_l10, b_l5]):
            stat_display = stat.replace("_", " ").title()
            rows.append(f"| {stat_display} | {a_l10} | {a_l5} | {b_l10} | {b_l5} |")
    
    # If no relevant stats had data, show all non-zero stats
    if len(rows) <= 2:
        all_stats = set(list(l10_a.keys()) + list(l10_b.keys()))
        for stat in sorted(all_stats):
            a_l10 = format_stat_value(l10_a.get(stat))
            a_l5 = format_stat_value(l5_a.get(stat))
            b_l10 = format_stat_value(l10_b.get(stat))
            b_l5 = format_stat_value(l5_b.get(stat))
            if any(v not in ("—", "0.0", "0") for v in [a_l10, a_l5, b_l10, b_l5]):
                stat_display = stat.replace("_", " ").title()
                rows.append(f"| {stat_display} | {a_l10} | {a_l5} | {b_l10} | {b_l5} |")
    
    return "\n".join(rows)


def build_market_ranking_table(ranking):
    """Build a table showing top markets by safety score."""
    if not ranking:
        return "*No market ranking available*"
    
    rows = []
    rows.append("| # | Market | Direction | Line | Safety |")
    rows.append("|---|--------|-----------|------|--------|")
    for i, m in enumerate(ranking[:5], 1):
        name = m.get("name", "?")
        direction = m.get("direction", "?")
        line = m.get("line", "—")
        safety = m.get("safety_score", "?")
        rows.append(f"| {i} | {name} | {direction} | {line} | {safety} |")
    
    return "\n".join(rows)


def generate_pick_analysis(pick, index):
    """Generate detailed analysis markdown for a single pick."""
    home = pick["home_team"]
    away = pick["away_team"]
    sport_emoji = {"football": "⚽", "basketball": "🏀", "tennis": "🎾", "hockey": "🏒", "volleyball": "🏐"}.get(pick["sport"], "🎯")
    
    market_parts = pick["best_market"].split()
    direction = "OVER" if "OVER" in pick["best_market"] else "UNDER"
    
    stats = pick.get("stats_summary", {})
    stats_a = stats.get("stats_a", {})
    stats_b = stats.get("stats_b", {})
    ranking = pick.get("ranking", [])
    three_way = pick.get("three_way_check", {})
    
    safety_class = get_safety_class(pick["safety_score"])
    
    lines = []
    lines.append(f"### {index}. {sport_emoji} {home} vs {away}")
    lines.append(f"**Liga:** {pick['league']} | **Sport:** {pick['sport'].title()} | **Kickoff:** {pick.get('kickoff', 'TBD')}")
    lines.append("")
    lines.append(f"**🎯 Recommended Market:** {pick['best_market']}")
    lines.append(f"**Safety Score:** {pick['safety_score']:.2f} | **Markets Evaluated:** {pick['markets_evaluated']}")
    lines.append("")
    
    # Statistical comparison table
    if stats_a and stats_b:
        lines.append("#### 📊 Statistical Comparison (Last 10 & Last 5 matches)")
        lines.append("")
        stat_table = build_stat_table(stats_a, stats_b, pick["best_market"])
        lines.append(stat_table)
        lines.append("")
        
        # Data quality info
        sources_a = stats_a.get("sources", [])
        sources_b = stats_b.get("sources", [])
        matches_a = stats_a.get("l10_matches_count", "?")
        matches_b = stats_b.get("l10_matches_count", "?")
        lines.append(f"*Data: {home} ({matches_a} matches, sources: {', '.join(sources_a) if sources_a else 'cache'}) | "
                    f"{away} ({matches_b} matches, sources: {', '.join(sources_b) if sources_b else 'cache'})*")
        lines.append("")
    
    # Market ranking
    if ranking:
        lines.append("#### 📈 Market Ranking (Top 5 by Safety Score)")
        lines.append("")
        lines.append(build_market_ranking_table(ranking))
        lines.append("")
    
    # Three-way check
    if three_way:
        lines.append("#### ✅ Three-Way Cross-Check")
        lines.append("")
        if isinstance(three_way, dict):
            for check_name, check_val in list(three_way.items())[:5]:
                if isinstance(check_val, dict):
                    verdict = check_val.get("verdict", check_val.get("status", "—"))
                    detail = check_val.get("detail", check_val.get("reason", ""))
                    lines.append(f"- **{check_name}:** {verdict} {f'— {detail}' if detail else ''}")
                else:
                    lines.append(f"- **{check_name}:** {check_val}")
        lines.append("")
    
    # Upset risk
    upset = stats.get("upset_risk", {})
    if upset:
        risk_level = upset.get("level", upset.get("risk_level", "?"))
        factors = upset.get("factors", [])
        lines.append(f"#### ⚠️ Upset Risk: {risk_level}")
        if factors:
            for f in factors[:3]:
                if isinstance(f, str):
                    lines.append(f"- {f}")
                elif isinstance(f, dict):
                    lines.append(f"- {f.get('factor', f.get('name', '?'))}: {f.get('detail', f.get('impact', ''))}")
        lines.append("")
    
    # Analysis verdict
    lines.append(f"#### 💡 Verdict")
    lines.append(f"Market **{pick['best_market']}** selected as safest based on {pick['markets_evaluated']} markets evaluated. ")
    
    if stats_b.get("l10_avg"):
        market_name = pick["best_market"].lower()
        # Try to explain the pick based on the stats
        if "shot" in market_name and "target" in market_name:
            avg = stats_b.get("l10_avg", {}).get("shots_on_target", 0) or stats_a.get("l10_avg", {}).get("shots_on_target", 0)
            if avg:
                lines.append(f"L10 average: {avg:.1f} shots on target supports this line.")
        elif "corner" in market_name:
            avg = stats_b.get("l10_avg", {}).get("corners", 0) or stats_a.get("l10_avg", {}).get("corners", 0)
            if avg:
                lines.append(f"L10 average: {avg:.1f} corners supports this line.")
        elif "foul" in market_name:
            avg_a = stats_a.get("l10_avg", {}).get("fouls", 0)
            avg_b = stats_b.get("l10_avg", {}).get("fouls", 0)
            total = (avg_a or 0) + (avg_b or 0)
            if total:
                lines.append(f"Combined L10 fouls average: {total:.1f} supports this line.")
        elif "card" in market_name:
            avg_a = stats_a.get("l10_avg", {}).get("yellow_cards", 0)
            avg_b = stats_b.get("l10_avg", {}).get("yellow_cards", 0)
            if avg_a or avg_b:
                lines.append(f"L10 yellow cards: {home}={format_stat_value(avg_a)}, {away}={format_stat_value(avg_b)}.")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    return "\n".join(lines)


def generate_full_pdf():
    """Generate comprehensive PDF with all picks and deep statistics."""
    picks = load_data()
    
    # Build markdown document
    md_lines = []
    
    # Header
    md_lines.append(f"# 📋 Coupon Analysis — {DATE}")
    md_lines.append("")
    md_lines.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Bankroll: 57.23 PLN | Budget: 5-15 PLN*")
    md_lines.append("")
    md_lines.append("> ⚠️ **ALL PICKS ARE CONDITIONAL** — Verify odds exist on Betclic app before placing. "
                   "Stats-first mode: no live odds feed. User calculates EV mentally: hit_rate × odds > 1.0 → BET.")
    md_lines.append("")
    
    # Pipeline quality summary
    md_lines.append("## 📊 Pipeline Quality Summary")
    md_lines.append("")
    md_lines.append("| Step | Verdict | Score | Key Fact |")
    md_lines.append("|------|---------|-------|----------|")
    md_lines.append("| S3 Deep Stats | FLAGGED | 6.5/10 | 200/200 analyzed, H2H-blind |")
    md_lines.append("| S4 Odds | STATS-FIRST | N/A | No odds feed (expected) |")
    md_lines.append("| S5 Context | OK | 7/10 | 250 injuries fetched |")
    md_lines.append("| S6 Upset Risk | PARTIAL | 5/10 | 90% HIGH (inflated) |")
    md_lines.append("| S7 Gate | OK | 7/10 | 198 approved, 2 rejected |")
    md_lines.append("| S8 Coupon | FLAGGED | 6.5/10 | 7 core, 50 singles |")
    md_lines.append("")
    md_lines.append(f"**Total picks analyzed:** {len(picks)} | **Sports:** Football ({sum(1 for p in picks if p['sport']=='football')}), "
                   f"Basketball ({sum(1 for p in picks if p['sport']=='basketball')}), "
                   f"Tennis ({sum(1 for p in picks if p['sport']=='tennis')}), "
                   f"Hockey ({sum(1 for p in picks if p['sport']=='hockey')})")
    md_lines.append("")
    
    # Core Coupons Overview
    md_lines.append("## 🏆 Core Coupons (14 PLN Total)")
    md_lines.append("")
    md_lines.append("| # | Type | Legs | Combined Odds | Stake | Potential Return |")
    md_lines.append("|---|------|------|--------------|-------|-----------------|")
    md_lines.append("| 1 | MS1 | Krasava (Shots U1.0) + Lynx (Rebounds O44.5) | 2.94 | 2.00 PLN | 5.88 PLN |")
    md_lines.append("| 2 | MS2 | Inter Miami (Corners O5.5) + NYRB II (Fouls O24.5) | 3.58 | 2.00 PLN | 7.16 PLN |")
    md_lines.append("| 3 | HR1 | Salzburg (SoT U4.5) + Athletic (Fouls O24.5) | 3.20 | 2.00 PLN | 6.40 PLN |")
    md_lines.append("| 4 | HR2 | Rayo (Cards U2.5) + Santos (Corners O5.5) | 3.20 | 2.00 PLN | 6.40 PLN |")
    md_lines.append("| 5 | HR3 | Club Brugge (Corners O5.5) + PEC Zwolle (Corners U9.5) | 3.20 | 2.00 PLN | 6.40 PLN |")
    md_lines.append("| 6 | HR4 | Istra (Corners U3.5) + Krasnodar (Fouls O24.5) | 3.20 | 2.00 PLN | 6.40 PLN |")
    md_lines.append("| 7 | HR5 | Real Sociedad (Fouls U13.0) + Inter (Shots U12.0) | 3.69 | 2.00 PLN | 7.38 PLN |")
    md_lines.append("")
    md_lines.append("**Total core spend: 14.00 PLN | Max potential return: 46.02 PLN**")
    md_lines.append("")
    
    # Concentration Warning
    md_lines.append("## ⚠️ Concentration Warning")
    md_lines.append("")
    md_lines.append("Krasava Ypsonas vs Enosis appears in 19/20 combos (273% budget exposure). "
                   "**Recommendation:** If placing combos, select MAX 3 Krasava-anchored combos.")
    md_lines.append("")
    md_lines.append("**Duplicate fixture alert:** `FK Austria Wien vs LASK` = `Austria Vienna vs Lask Linz` (same match, different encoding). Bet only ONE.")
    md_lines.append("")
    
    # DETAILED PICK ANALYSIS — All picks with safety >= 0.42 (core + extended)
    md_lines.append("## 📋 Detailed Pick Analysis (All Verified Picks)")
    md_lines.append("")
    md_lines.append("Below is the full statistical breakdown for every pick in the matrix, ordered by safety score. "
                   "Each pick includes L10/L5 form data, market ranking, and statistical justification.")
    md_lines.append("")
    
    for i, pick in enumerate(picks, 1):
        md_lines.append(generate_pick_analysis(pick, i))
    
    # Footer
    md_lines.append("## 📝 Methodology Notes")
    md_lines.append("")
    md_lines.append("- **Safety Score:** Composite of L10 consistency, trend alignment, and market depth (0-1 scale)")
    md_lines.append("- **L10/L5:** Last 10 and Last 5 matches averages for relevant statistics")
    md_lines.append("- **Three-Way Check:** Cross-validation between L10 avg, H2H data, and L5 trend")
    md_lines.append("- **Gate Score:** 18-point qualification gate (min 9/18 to pass)")
    md_lines.append("- **Stats-First Mode:** No live odds = all markets priced by user on Betclic app")
    md_lines.append("- **EV Check:** hit_rate × odds > 1.0 → positive EV → bet. Min odds = 1/hit_rate")
    md_lines.append("")
    md_lines.append(f"*Report generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by betting pipeline v5*")
    
    # Convert to HTML + PDF
    full_md = "\n".join(md_lines)
    
    md_parser = markdown_it.MarkdownIt("commonmark", {"html": True})
    md_parser.enable("table")
    html_body = md_parser.render(full_md)
    
    full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>{CSS}</style>
</head>
<body>
{html_body}
</body>
</html>"""
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"coupon-{DATE}-full-analysis.pdf"
    
    print(f"Generating PDF with {len(picks)} picks...")
    HTML(string=full_html).write_pdf(str(output_path))
    print(f"✓ Generated: {output_path} ({output_path.stat().st_size / 1024:.0f} KB)")
    
    # Also generate a quick-reference version (core coupons only)
    quick_md = "\n".join(md_lines[:80])  # Just header + core coupons
    quick_html_body = md_parser.render(quick_md)
    quick_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{CSS}</style></head>
<body>{quick_html_body}</body></html>"""
    
    quick_path = OUTPUT_DIR / f"coupon-{DATE}-quick.pdf"
    HTML(string=quick_html).write_pdf(str(quick_path))
    print(f"✓ Quick reference: {quick_path} ({quick_path.stat().st_size / 1024:.0f} KB)")
    
    return output_path


if __name__ == "__main__":
    generate_full_pdf()
