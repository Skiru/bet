"""Shopping list output — Polish-language Betclic navigation guide.

Writes coupon shopping list to `betting/coupons/YYYY-MM-DD.md`.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from bet.config import BettingConfig
from bet.coupon.translations import SPORT_EMOJI
from bet.db.models import Bet, Coupon

COUPON_DIR = Path(__file__).parent.parent.parent.parent / "betting" / "coupons"


def format_shopping_list(
    coupons: list[tuple[Coupon, list[Bet]]],
    config: BettingConfig,
) -> str:
    """Format coupons as a Polish-language shopping list for Betclic.

    Each coupon shows legs with Polish market descriptions,
    min odds, safety scores, and Betclic app navigation hints.
    """
    if not coupons:
        return "# Brak kuponów do postawienia\n"

    lines: list[str] = []
    lines.append(f"# Lista zakupów — {date.today().isoformat()}\n")

    for coupon, bets in coupons:
        odds_str = f"{coupon.total_odds:.2f}" if coupon.total_odds else "?"
        stake_str = f"{coupon.stake_pln:.2f}" if coupon.stake_pln else "?"
        lines.append(
            f"## {coupon.coupon_id} | Kurs: {odds_str} | Stawka: {stake_str} PLN\n"
        )

        for i, bet in enumerate(bets, 1):
            emoji = SPORT_EMOJI.get(bet.sport, "")
            safety_str = f"{bet.safety_score:.2f}" if bet.safety_score else "?"
            hit_str = f"{bet.hit_rate:.0%}" if bet.hit_rate else "?"
            min_odds_str = f"{bet.min_odds:.2f}" if bet.min_odds else "?"

            lines.append(
                f"{i}. {emoji} {bet.event_name} — {bet.market_pl}"
            )
            lines.append(
                f"   Min kurs: {min_odds_str} | "
                f"Bezpieczeństwo: {safety_str} | "
                f"Trafialność: {hit_str}"
            )
            if bet.navigation_hint:
                lines.append(f"   → Betclic: {bet.navigation_hint}")

            # Deep stats section
            if bet.stats_detail:
                sd = bet.stats_detail
                if sd.get('l10_avg') is not None:
                    trend_arrow = {"up": "↑", "down": "↓", "stable": "→"}.get(sd.get("trend", ""), "")
                    lines.append(f"   📊 L10 śr: {sd['l10_avg']:.1f} | L5 śr: {sd['l5_avg']:.1f} | Trend: {trend_arrow} {sd.get('trend','')}")
                if sd.get('hit_l10') is not None:
                    h2h_str = sd['hit_h2h'] if sd.get('hit_h2h') else '–'
                    aligned_str = '✓' if sd.get('aligned') else '✗'
                    lines.append(f"   📊 Hit L10: {sd['hit_l10']}/{sd['total_l10']} | H2H: {h2h_str} | 3-Way: {aligned_str}")
                if sd.get('recent_values'):
                    recent = sd['recent_values'][:5]
                    recent_str = ", ".join(f"{v:.0f}" for v in recent)
                    lines.append(f"   📊 Ostatnie 5: [{recent_str}]")

            lines.append("")

        lines.append("---\n")

    return "\n".join(lines)


def format_summary(
    coupons: list[tuple[Coupon, list[Bet]]],
    total_candidates: int,
    config: BettingConfig,
) -> str:
    """Format summary statistics.

    Shows: coupon count, total legs, sport distribution,
    average safety, total stake, bankroll exposure %.
    """
    if not coupons:
        return "Brak kuponów.\n"

    total_legs = sum(len(bets) for _, bets in coupons)
    total_stake = sum(c.stake_pln or 0 for c, _ in coupons)
    bankroll_pct = (total_stake / config.bankroll_pln * 100) if config.bankroll_pln > 0 else 0

    # Sport distribution
    sport_counts: dict[str, int] = {}
    all_safeties: list[float] = []
    for _, bets in coupons:
        for bet in bets:
            sport_counts[bet.sport] = sport_counts.get(bet.sport, 0) + 1
            if bet.safety_score is not None:
                all_safeties.append(bet.safety_score)

    avg_safety = sum(all_safeties) / len(all_safeties) if all_safeties else 0

    lines: list[str] = []
    lines.append("## Podsumowanie\n")
    lines.append(f"- Kupony: {len(coupons)}")
    lines.append(f"- Nogi łącznie: {total_legs}")
    lines.append(f"- Kandydaci rozpatrzeni: {total_candidates}")
    lines.append(f"- Średnie bezpieczeństwo: {avg_safety:.2f}")
    lines.append(f"- Stawka łączna: {total_stake:.2f} PLN")
    lines.append(f"- Ekspozycja bankrolla: {bankroll_pct:.1f}%")
    lines.append("")
    lines.append("### Rozkład sportów\n")
    for sport, count in sorted(sport_counts.items(), key=lambda x: -x[1]):
        emoji = SPORT_EMOJI.get(sport, "")
        lines.append(f"- {emoji} {sport}: {count} nóg")
    lines.append("")

    return "\n".join(lines)


def write_shopping_list(
    coupons: list[tuple[Coupon, list[Bet]]],
    config: BettingConfig,
    total_candidates: int = 0,
    output_path: Path | None = None,
) -> Path:
    """Write shopping list + summary to markdown file.

    Default output: betting/coupons/YYYY-MM-DD.md
    Returns the output path.
    """
    if output_path is None:
        COUPON_DIR.mkdir(parents=True, exist_ok=True)
        output_path = COUPON_DIR / f"{date.today().isoformat()}.md"

    content = format_shopping_list(coupons, config)
    content += "\n" + format_summary(coupons, total_candidates, config)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")

    return output_path
