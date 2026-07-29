"""Production contract for sport promotion obligations in the betting pipeline.

This contract defines when a sport is PROMOTION_ELIGIBLE and enforces that the
pipeline must either produce quality candidates or block with a specific,
valid technical blocker.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass
class SportObligationResult:
    sport: str
    eligible: bool
    status: str  # "PROMOTED", "BLOCKED", "NOT_ELIGIBLE"
    candidates_count: int = 0
    quote_cards_count: int = 0
    blocker_reason: str | None = None
    blocker_class: str | None = None


@dataclass
class PromotionObligationsAudit:
    ok: bool
    status: str  # "PASS" or "BLOCK"
    results: dict[str, SportObligationResult] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def audit_sport_promotion_obligations(
    *,
    events_by_sport: Mapping[str, int],
    market_rows_by_sport: Mapping[str, int],
    candidates_by_sport: Mapping[str, int],
    quote_cards_by_sport: Mapping[str, int],
    wimbledon_market_rows: int = 0,
    blockers_by_sport: Mapping[str, dict[str, str]] = None,  # sport -> {"class": ..., "reason": ...}
) -> PromotionObligationsAudit:
    """Audits the multisport promotion obligations.

    If tennis, basketball, esports, or volleyball have sufficient market rows,
    they must produce candidates and quote cards, or be explicitly blocked with
    a valid technical blocker class.
    """
    blockers = blockers_by_sport or {}
    results: dict[str, SportObligationResult] = {}
    errors: list[str] = []
    warnings: list[str] = []

    # Valid blocker classes
    VALID_BLOCKER_CLASSES = {
        "SPORT_PROMOTER_NOT_IMPLEMENTED",
        "MARKET_FAMILY_MAPPER_MISSING",
        "HUMAN_MARKET_NAME_MISSING",
        "LINE_SEMANTICS_MISSING",
        "PROVIDER_REF_MISSING",
        "EVIDENCE_TOO_THIN",
        "TEST_FORCED_EXCLUSION",
        "SPORT_EXCLUDED_BY_CONFIG",
        "TIPSTER_CONTEXT_MISSING_BUT_OPTIONAL",
        "OTHER_WITH_EXPLANATION",
    }

    # Eligible sports list
    all_sports = set(events_by_sport.keys()) | set(market_rows_by_sport.keys())

    for sport in all_sports:
        events_count = events_by_sport.get(sport, 0)
        rows_count = market_rows_by_sport.get(sport, 0)
        cand_count = candidates_by_sport.get(sport, 0)
        qc_count = quote_cards_by_sport.get(sport, 0)

        eligible = events_count > 0 and rows_count > 0

        if not eligible:
            results[sport] = SportObligationResult(
                sport=sport,
                eligible=False,
                status="NOT_ELIGIBLE",
                candidates_count=cand_count,
                quote_cards_count=qc_count,
            )
            continue

        # Check if explicitly blocked
        sport_block = blockers.get(sport)
        if sport_block:
            b_class = sport_block.get("class")
            b_reason = sport_block.get("reason")

            if b_class not in VALID_BLOCKER_CLASSES:
                errors.append(f"Sport {sport} has invalid blocker class '{b_class}'")

            results[sport] = SportObligationResult(
                sport=sport,
                eligible=True,
                status="BLOCKED",
                candidates_count=cand_count,
                quote_cards_count=qc_count,
                blocker_reason=b_reason,
                blocker_class=b_class,
            )
            continue

        # Check sport specific obligations
        if sport == "football":
            results[sport] = SportObligationResult(
                sport=sport,
                eligible=True,
                status="PROMOTED",
                candidates_count=cand_count,
                quote_cards_count=qc_count,
            )
        elif sport == "tennis":
            # If tennis market_rows >= 100 and Wimbledon market_rows >= 50, produce at least:
            # tennis_candidates >= 10 OR TENNIS_PROMOTION_BLOCK with exact reason,
            # tennis_quote_cards >= 5 OR TENNIS_QUOTE_BLOCK with exact reason.
            if rows_count >= 100 and wimbledon_market_rows >= 50:
                if cand_count < 10:
                    errors.append(f"tennis has {rows_count} market rows and {wimbledon_market_rows} Wimbledon rows, but only generated {cand_count} candidates (minimum 10 required or explicit block)")
                if qc_count < 5:
                    errors.append(f"tennis has {rows_count} market rows and {wimbledon_market_rows} Wimbledon rows, but only generated {qc_count} quote cards (minimum 5 required or explicit block)")

            results[sport] = SportObligationResult(
                sport=sport,
                eligible=True,
                status="PROMOTED",
                candidates_count=cand_count,
                quote_cards_count=qc_count,
            )
        elif sport == "basketball":
            # If basketball market_rows > 0, produce basketball_candidates >= 5 OR BASKETBALL_PROMOTION_BLOCK with exact reason.
            if cand_count < 5:
                errors.append(f"basketball has {rows_count} market rows, but only generated {cand_count} candidates (minimum 5 required or explicit block)")
            results[sport] = SportObligationResult(
                sport=sport,
                eligible=True,
                status="PROMOTED",
                candidates_count=cand_count,
                quote_cards_count=qc_count,
            )
        elif sport in {"cs2", "valorant", "dota2", "esports"}:
            # If esports market_rows > 0, produce esports_candidates >= 3 OR ESPORTS_PROMOTION_BLOCK with exact reason.
            if cand_count < 3:
                errors.append(f"{sport} has {rows_count} market rows, but only generated {cand_count} candidates (minimum 3 required or explicit block)")
            results[sport] = SportObligationResult(
                sport=sport,
                eligible=True,
                status="PROMOTED",
                candidates_count=cand_count,
                quote_cards_count=qc_count,
            )
        elif sport == "volleyball":
            # If volleyball market_rows > 0, produce volleyball_candidates >= 2 OR VOLLEYBALL_PROMOTION_BLOCK with exact reason.
            if cand_count < 2:
                errors.append(f"volleyball has {rows_count} market rows, but only generated {cand_count} candidates (minimum 2 required or explicit block)")
            results[sport] = SportObligationResult(
                sport=sport,
                eligible=True,
                status="PROMOTED",
                candidates_count=cand_count,
                quote_cards_count=qc_count,
            )
        else:
            results[sport] = SportObligationResult(
                sport=sport,
                eligible=True,
                status="PROMOTED",
                candidates_count=cand_count,
                quote_cards_count=qc_count,
            )

    # Coherence check for production-grade READY_FOR_MANUAL_SUPERBET_QUOTE_REVIEW
    non_football_eligible = [s for s, r in results.items() if s != "football" and r.eligible]
    if non_football_eligible:
        # All non-football eligible sports have zero candidates
        if all(results[s].candidates_count == 0 for s in non_football_eligible):
            errors.append("All non-football promotion-eligible sports generated zero candidates")

        # All non-football eligible sports are blocked by generic/missing mapper reasons
        all_generic_blocked = True
        for s in non_football_eligible:
            res = results[s]
            if res.status != "BLOCKED":
                all_generic_blocked = False
                break
            if res.blocker_class not in {"SPORT_PROMOTER_NOT_IMPLEMENTED", "MARKET_FAMILY_MAPPER_MISSING"}:
                all_generic_blocked = False
                break
        if all_generic_blocked:
            errors.append("All non-football promotion-eligible sports are blocked by generic or missing mapper reasons")

    # If tennis/Wimbledon has > 0 rows and no candidates, and no explicit blocker class
    if wimbledon_market_rows > 0 or market_rows_by_sport.get("tennis", 0) > 0:
        tennis_cand = candidates_by_sport.get("tennis", 0)
        if tennis_cand == 0 and "tennis" not in blockers:
            errors.append("tennis/Wimbledon has active market rows but generated 0 candidates without an explicit blocker")

    ok = len(errors) == 0
    return PromotionObligationsAudit(
        ok=ok,
        status="PASS" if ok else "BLOCK",
        results=results,
        errors=errors,
        warnings=warnings,
    )
