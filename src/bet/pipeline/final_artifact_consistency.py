"""Final artifact consistency and false-approval gates for Superbet sessions.

This module is deliberately pure and side-effect-free.  It validates that the
final report, certification, adversarial review, Wimbledon audit, quote cards,
builder groups, coupon drafts and market matrix all tell the same story.

It catches the exact V16.1 failure class:
- late Wimbledon audit says 30 Wimbledon singles quote cards, but final reports
  still say zero;
- PASS/manual-review artifacts contain unscoped blockers;
- builder groups lack sport identity;
- multi-sport quote board produces football-only coupon drafts without an
  explicit diversification blocker;
- reused market matrix carries an old run_id without source/current lineage;
- final evidence export contains nested absolute paths or OS cache files.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

BLOCK = "BLOCK"
WARN = "WARN"
_ALLOWED_BLOCKER_SCOPES = {"BLOCKED_CANDIDATES_ONLY", "NON_PROMOTED_ITEMS_ONLY"}
_ALLOWED_DRAFT_STATUSES = {"DRAFT_REQUIRES_HUMAN_QUOTES", "COUPON_DRAFT_REQUIRES_HUMAN_QUOTES"}
_ALLOWED_QUOTE_STATUSES = {"QUOTE_REVIEW_ONLY", "READY_FOR_MANUAL_OPERATOR_QUOTE_REVIEW"}
_ALLOWED_ANALYSIS_BOARD_SECTIONS = {
    "TOP_PRICED_ANALYTICAL_CANDIDATES",
    "TOP_PARTIALLY_PRICED_ANALYTICAL_CANDIDATES",
    "TOP_UNPRICED_DEEP_ANALYTICAL_CANDIDATES",
    "TOP_BET_BUILDER_CONCEPT_INPUTS",
    "WATCHLIST_LINE_SENSITIVE",
    "REJECTED_WITH_REASONS",
}
_ALLOWED_ANALYSIS_PORTFOLIO_STYLES = {
    "CONSERVATIVE_ANALYSIS_PORTFOLIO",
    "BALANCED_ANALYSIS_PORTFOLIO",
    "AGGRESSIVE_ANALYSIS_PORTFOLIO",
    "BROAD_ANALYTICAL_SHORTLIST",
    "BET_BUILDER_CONCEPT_PORTFOLIO",
}


@dataclass(frozen=True)
class ConsistencyIssue:
    code: str
    severity: str
    message: str


@dataclass
class ConsistencyReport:
    ok: bool
    issues: list[ConsistencyIssue] = field(default_factory=list)

    @property
    def blockers(self) -> list[ConsistencyIssue]:
        return [issue for issue in self.issues if issue.severity == BLOCK]

    @property
    def warnings(self) -> list[ConsistencyIssue]:
        return [issue for issue in self.issues if issue.severity == WARN]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "issues": [issue.__dict__ for issue in self.issues],
            "blocker_count": len(self.blockers),
            "warning_count": len(self.warnings),
        }


def _get(obj: Mapping[str, Any] | None, *keys: str, default: Any = None) -> Any:
    if not isinstance(obj, Mapping):
        return default
    for key in keys:
        if key in obj:
            return obj[key]
    return default


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _norm_count_map(value: Any) -> dict[str, int] | None:
    if not isinstance(value, Mapping):
        return None
    out: dict[str, int] = {}
    for key, raw in value.items():
        parsed = _int_or_none(raw)
        if parsed is None:
            return None
        out[str(key)] = parsed
    return out


def _line_identity(card: Mapping[str, Any]) -> Any:
    line = card.get("line")
    if line not in (None, "", "UNKNOWN"):
        return line
    line_free = card.get("line_free_market_type")
    if line_free:
        return f"line_free:{line_free}"
    alternatives = card.get("allowed_line_alternatives") or []
    if alternatives:
        return tuple(str(item) for item in alternatives)
    return card.get("line_unknown_reason") or "UNKNOWN_LINE"


def quote_card_signature(card: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        card.get("event_id"),
        card.get("sport"),
        card.get("market_family"),
        card.get("selection") or card.get("human_searchable_market_name"),
        _line_identity(card),
    )


def quote_cards_by_field(cards: Sequence[Mapping[str, Any]], field: str) -> dict[str, int]:
    return dict(Counter(str(card.get(field) or "UNKNOWN") for card in cards))


def _final_status_is_pass(source: Mapping[str, Any]) -> bool:
    return str(_get(source, "STATUS", "status", default="")).upper() == "PASS" or str(
        _get(source, "FINAL_VERDICT", "final_verdict", default="")
    ).upper().startswith("APPROVE")


def _manual_review_allowed(source: Mapping[str, Any]) -> bool:
    return bool(_get(source, "MANUAL_SUPERBET_QUOTE_REVIEW_ALLOWED", "manual_superbet_quote_review_allowed", default=False))


def _declared_wimbledon_count(source: Mapping[str, Any]) -> int | None:
    return _int_or_none(_get(source, "WIMBLEDON_QUOTE_CARDS", "wimbledon_quote_cards", "WIMBLEDON_SINGLES_QUOTE_CARDS", "wimbledon_singles_quote_cards"))


def validate_cross_artifact_consistency(
    *,
    final_report: Mapping[str, Any],
    daily_certification: Mapping[str, Any] | None,
    adversarial_review: Mapping[str, Any] | None,
    wimbledon_audit: Mapping[str, Any] | None,
    export_manifest: Mapping[str, Any] | None,
    quote_cards: Sequence[Mapping[str, Any]],
    builder_groups: Sequence[Mapping[str, Any]] | None = None,
    coupon_drafts: Sequence[Mapping[str, Any]] | None = None,
) -> ConsistencyReport:
    issues: list[ConsistencyIssue] = []
    cards = list(quote_cards)
    actual_by_sport = quote_cards_by_field(cards, "sport")
    signatures = [quote_card_signature(card) for card in cards]
    unique_count = len(set(signatures))

    if unique_count != len(cards):
        issues.append(ConsistencyIssue(
            "QUOTE_CARD_DUPLICATE_INFLATION",
            BLOCK,
            f"Quote cards contain {len(cards) - unique_count} duplicate actionable signatures.",
        ))

    sources: list[tuple[str, Mapping[str, Any]]] = [("final_report", final_report)]
    if daily_certification:
        sources.append(("daily_certification", daily_certification))
    if adversarial_review:
        sources.append(("adversarial_review", adversarial_review))
    if export_manifest:
        sources.append(("export_manifest", export_manifest))

    for label, source in sources:
        declared_by_sport = _norm_count_map(_get(source, "QUOTE_CARDS_BY_SPORT", "quote_cards_by_sport"))
        if declared_by_sport is not None and declared_by_sport != actual_by_sport:
            issues.append(ConsistencyIssue(
                "QUOTE_CARDS_BY_SPORT_MISMATCH",
                BLOCK,
                f"{label} quote_cards_by_sport={declared_by_sport}; actual={actual_by_sport}.",
            ))
        declared_unique = _int_or_none(_get(source, "UNIQUE_QUOTE_CARD_COUNT", "unique_quote_card_count"))
        if declared_unique is not None and declared_unique != unique_count:
            issues.append(ConsistencyIssue(
                "UNIQUE_QUOTE_CARD_COUNT_MISMATCH",
                BLOCK,
                f"{label} unique count={declared_unique}; actual unique quote cards={unique_count}.",
            ))

    # Late Wimbledon audit is authoritative for Wimbledon classification; every
    # final/certification artifact must either match it or fail.  Missing fields
    # are also a block because they caused the V16.1 false approval ambiguity.
    if wimbledon_audit:
        wimbledon_qc = _int_or_none(_get(wimbledon_audit, "wimbledon_singles_quote_cards", "WIMBLEDON_SINGLES_QUOTE_CARDS")) or 0
        if wimbledon_qc > 0:
            for label, source in sources:
                declared = _declared_wimbledon_count(source)
                if declared is None:
                    issues.append(ConsistencyIssue(
                        "WIMBLEDON_QUOTE_CARD_DECLARATION_MISSING",
                        BLOCK,
                        f"{label} does not declare WIMBLEDON_QUOTE_CARDS despite 16E audit={wimbledon_qc}.",
                    ))
                elif declared != wimbledon_qc:
                    issues.append(ConsistencyIssue(
                        "WIMBLEDON_QUOTE_CARD_MISMATCH",
                        BLOCK,
                        f"{label} declares Wimbledon quote cards={declared}; 16E audit={wimbledon_qc}.",
                    ))

    for label, source in sources:
        blockers = _get(source, "BLOCKERS", "blockers", default={}) or {}
        global_blockers = _get(source, "GLOBAL_BLOCKERS", "global_blockers", default={}) or {}
        blocker_scope = _get(source, "BLOCKER_SCOPE", "blocker_scope", default=None)
        if _final_status_is_pass(source) and _manual_review_allowed(source):
            if global_blockers:
                issues.append(ConsistencyIssue(
                    "GLOBAL_BLOCKERS_IN_PASS",
                    BLOCK,
                    f"{label} is pass/manual-review but has GLOBAL_BLOCKERS={global_blockers}.",
                ))
            if blockers and blocker_scope not in _ALLOWED_BLOCKER_SCOPES:
                issues.append(ConsistencyIssue(
                    "UNSCOPED_BLOCKERS_IN_PASS",
                    BLOCK,
                    f"{label} is pass/manual-review but has unscoped BLOCKERS={blockers}.",
                ))

    # Builder group identity and safety.  Same-game/same-match groups must be
    # auditable by sport, competition and event, and every leg must trace to a candidate.
    for idx, group in enumerate(builder_groups or []):
        group_id = group.get("group_id") or f"#{idx}"
        if not group.get("sport"):
            issues.append(ConsistencyIssue("BUILDER_GROUP_SPORT_MISSING", BLOCK, f"Builder group {group_id} lacks sport."))
        if not group.get("competition"):
            issues.append(ConsistencyIssue("BUILDER_GROUP_COMPETITION_MISSING", BLOCK, f"Builder group {group_id} lacks competition."))
        if not group.get("event_id"):
            issues.append(ConsistencyIssue("BUILDER_GROUP_EVENT_ID_MISSING", BLOCK, f"Builder group {group_id} lacks event_id."))
        if group.get("combined_bookmaker_odds_computed") is not False:
            issues.append(ConsistencyIssue("BUILDER_GROUP_COMBINED_ODDS_NOT_FALSE", BLOCK, f"Builder group {group_id} has invalid combined odds flag."))
        legs = group.get("legs") or []
        if not isinstance(legs, Sequence) or isinstance(legs, (str, bytes)) or not legs:
            issues.append(ConsistencyIssue("BUILDER_GROUP_LEGS_MISSING", BLOCK, f"Builder group {group_id} has no legs."))
            continue
        for leg_idx, leg in enumerate(legs):
            if not isinstance(leg, Mapping):
                issues.append(ConsistencyIssue("BUILDER_GROUP_LEG_INVALID", BLOCK, f"Builder group {group_id} leg {leg_idx} is not an object."))
                continue
            for required in ("candidate_id", "event_id", "sport"):
                if not leg.get(required):
                    issues.append(ConsistencyIssue(
                        "BUILDER_GROUP_LEG_FIELD_MISSING",
                        BLOCK,
                        f"Builder group {group_id} leg {leg_idx} lacks {required}.",
                    ))
            if group.get("sport") and leg.get("sport") and group.get("sport") != leg.get("sport"):
                issues.append(ConsistencyIssue(
                    "BUILDER_GROUP_SPORT_MISMATCH",
                    BLOCK,
                    f"Builder group {group_id} sport={group.get('sport')} but leg {leg_idx} sport={leg.get('sport')}.",
                ))

    # Coupon drafts remain non-bettable and must either diversify or explain why
    # not when a multi-sport quote board exists.
    quote_card_ids = {card.get("quote_card_id") for card in cards if card.get("quote_card_id")}
    multi_sport_quote_board = len(actual_by_sport) >= 2
    for draft in coupon_drafts or []:
        draft_id = draft.get("coupon_draft_id") or draft.get("style") or "UNKNOWN_DRAFT"
        if draft.get("bettable") is not False:
            issues.append(ConsistencyIssue("COUPON_DRAFT_BETTABLE_NOT_FALSE", BLOCK, f"Draft {draft_id} is bettable."))
        if draft.get("combined_odds") is not None:
            issues.append(ConsistencyIssue("COUPON_DRAFT_COMBINED_ODDS_PRESENT", BLOCK, f"Draft {draft_id} has combined_odds."))
        if str(draft.get("status")) not in _ALLOWED_DRAFT_STATUSES:
            issues.append(ConsistencyIssue("COUPON_DRAFT_STATUS_INVALID", BLOCK, f"Draft {draft_id} status={draft.get('status')}."))
        legs = draft.get("legs") or []
        leg_sports: set[str] = set()
        for leg_idx, leg in enumerate(legs):
            if not isinstance(leg, Mapping):
                issues.append(ConsistencyIssue("COUPON_DRAFT_LEG_INVALID", BLOCK, f"Draft {draft_id} leg {leg_idx} is not an object."))
                continue
            for required in ("quote_card_id", "candidate_id", "event_id", "sport"):
                if not leg.get(required):
                    issues.append(ConsistencyIssue("COUPON_DRAFT_LEG_FIELD_MISSING", BLOCK, f"Draft {draft_id} leg {leg_idx} lacks {required}."))
            if leg.get("quote_card_id") and quote_card_ids and leg.get("quote_card_id") not in quote_card_ids:
                issues.append(ConsistencyIssue("COUPON_DRAFT_LEG_QUOTE_CARD_REF_MISSING", BLOCK, f"Draft {draft_id} leg {leg_idx} references unknown quote card {leg.get('quote_card_id')}."))
            if leg.get("sport"):
                leg_sports.add(str(leg.get("sport")))
        if multi_sport_quote_board and len(legs) >= 3 and len(leg_sports) <= 1:
            reason = draft.get("single_sport_reason") or draft.get("diversification_blocker")
            if not reason:
                issues.append(ConsistencyIssue(
                    "COUPON_DRAFT_SINGLE_SPORT_WITHOUT_REASON",
                    BLOCK,
                    f"Draft {draft_id} uses one sport despite multi-sport quote board and lacks a diversification blocker.",
                ))

    return ConsistencyReport(ok=not any(issue.severity == BLOCK for issue in issues), issues=issues)


def validate_market_matrix_lineage(
    matrix: Mapping[str, Any],
    *,
    expected_current_run_id: str,
    allowed_source_run_ids: set[str] | None = None,
) -> ConsistencyReport:
    issues: list[ConsistencyIssue] = []
    run_id = _get(matrix, "run_id")
    current_run_id = _get(matrix, "current_run_id")
    source_run_id = _get(matrix, "source_run_id")
    allowed_source_run_ids = allowed_source_run_ids or set()
    if current_run_id:
        if current_run_id != expected_current_run_id:
            issues.append(ConsistencyIssue("MARKET_MATRIX_CURRENT_RUN_ID_MISMATCH", BLOCK, f"current_run_id={current_run_id}; expected={expected_current_run_id}."))
        if source_run_id and allowed_source_run_ids and source_run_id not in allowed_source_run_ids:
            issues.append(ConsistencyIssue("MARKET_MATRIX_SOURCE_RUN_ID_UNEXPECTED", BLOCK, f"source_run_id={source_run_id}; allowed={sorted(allowed_source_run_ids)}."))
    else:
        if run_id != expected_current_run_id:
            issues.append(ConsistencyIssue(
                "MARKET_MATRIX_RUN_LINEAGE_AMBIGUOUS",
                BLOCK,
                f"matrix run_id={run_id} but expected current run={expected_current_run_id}; add current_run_id/source_run_id.",
            ))
    return ConsistencyReport(ok=not any(issue.severity == BLOCK for issue in issues), issues=issues)


def validate_test_manifest(
    manifest: Mapping[str, Any] | None,
    *,
    required_test_files: set[str],
) -> ConsistencyReport:
    issues: list[ConsistencyIssue] = []
    if not manifest:
        return ConsistencyReport(False, [ConsistencyIssue("TEST_MANIFEST_MISSING", BLOCK, "16F/final evidence manifest is missing.")])
    raw_files = _get(manifest, "TEST_FILES_RUN", "test_files_run", "test_files", default=[])
    if isinstance(raw_files, Mapping):
        files = {str(key) for key in raw_files.keys()}
    elif isinstance(raw_files, Sequence) and not isinstance(raw_files, (str, bytes)):
        files = {str(item) for item in raw_files}
    else:
        files = set()
    missing = {path for path in required_test_files if path not in files and Path(path).name not in {Path(f).name for f in files}}
    if missing:
        issues.append(ConsistencyIssue("REQUIRED_TESTS_MISSING_FROM_MANIFEST", BLOCK, f"Manifest lacks required tests: {sorted(missing)}."))
    return ConsistencyReport(ok=not any(issue.severity == BLOCK for issue in issues), issues=issues)


def validate_analysis_first_consistency(
    *,
    final_report: Mapping[str, Any],
    daily_certification: Mapping[str, Any] | None,
    wimbledon_audit: Mapping[str, Any] | None,
    candidate_board_rows: Sequence[Mapping[str, Any]],
    bet_builder_concepts: Sequence[Mapping[str, Any]],
    analysis_portfolios: Sequence[Mapping[str, Any]],
    optional_quote_shortlist: Sequence[Mapping[str, Any]],
    builder_groups: Sequence[Mapping[str, Any]] | None = None,
) -> ConsistencyReport:
    issues: list[ConsistencyIssue] = []
    rows = list(candidate_board_rows)
    sections = Counter(str(row.get("section") or "") for row in rows)
    for section in sections:
        if section not in _ALLOWED_ANALYSIS_BOARD_SECTIONS:
            issues.append(ConsistencyIssue("ANALYSIS_BOARD_SECTION_INVALID", BLOCK, f"Unknown analysis board section {section}."))

    if final_report.get("MANUAL_QUOTE_ENTRY_REQUIRED_FOR_ANALYSIS") is not False:
        issues.append(ConsistencyIssue(
            "ANALYSIS_STILL_REQUIRES_MANUAL_QUOTES",
            BLOCK,
            "Final report must declare MANUAL_QUOTE_ENTRY_REQUIRED_FOR_ANALYSIS=false.",
        ))
    if final_report.get("MANUAL_QUOTE_ENTRY_REQUIRED_FOR_BETTABLE") is not True:
        issues.append(ConsistencyIssue(
            "BETTABLE_DOES_NOT_REQUIRE_MANUAL_QUOTES",
            BLOCK,
            "Final report must declare MANUAL_QUOTE_ENTRY_REQUIRED_FOR_BETTABLE=true.",
        ))
    if final_report.get("FINAL_COUPON_ALLOWED") is not False:
        issues.append(ConsistencyIssue("FINAL_COUPON_ALLOWED_TRUE", BLOCK, "Final coupon must remain disallowed without human odds."))
    if final_report.get("COMBINED_BOOKMAKER_ODDS_COMPUTED") is not False:
        issues.append(ConsistencyIssue("COMBINED_ODDS_COMPUTED_TRUE", BLOCK, "Combined bookmaker odds must remain false."))
    if final_report.get("BETTABLE_COUNT") not in {0, "0"}:
        issues.append(ConsistencyIssue("BETTABLE_COUNT_NONZERO", BLOCK, f"BETTABLE_COUNT={final_report.get('BETTABLE_COUNT')} but must remain zero."))

    for key in ("CURRENT_RUN_ID", "SOURCE_RUN_ID", "INPUT_RUN_ID"):
        if not final_report.get(key):
            issues.append(ConsistencyIssue("RUN_LINEAGE_FIELD_MISSING", BLOCK, f"Final report lacks {key}."))

    if "READY_FOR_MANUAL_SUPERBET_QUOTE_REVIEW" in str(_get(final_report, "FINAL_VERDICT", "final_verdict", default="")):
        issues.append(ConsistencyIssue(
            "LEGACY_OPERATOR_FIRST_VERDICT",
            BLOCK,
            "Final verdict still implies operator-entry-first workflow.",
        ))

    blockers = _get(final_report, "BLOCKERS", "blockers", default={}) or {}
    if not isinstance(blockers, Mapping):
        issues.append(ConsistencyIssue("BLOCKERS_NOT_OBJECT", BLOCK, "Final report BLOCKERS must be a scoped object."))
    else:
        for required in ("GLOBAL_BLOCKERS", "NON_PROMOTED_BLOCKERS", "PRICE_ONLY_BLOCKERS"):
            if required not in blockers:
                issues.append(ConsistencyIssue("BLOCKER_SCOPE_MISSING", BLOCK, f"Final report BLOCKERS lacks {required}."))

    priced = sections.get("TOP_PRICED_ANALYTICAL_CANDIDATES", 0)
    partial = sections.get("TOP_PARTIALLY_PRICED_ANALYTICAL_CANDIDATES", 0)
    unpriced = sections.get("TOP_UNPRICED_DEEP_ANALYTICAL_CANDIDATES", 0)
    if _int_or_none(final_report.get("TOP_PRICED_COUNT")) != priced:
        issues.append(ConsistencyIssue("TOP_PRICED_COUNT_MISMATCH", BLOCK, f"Report TOP_PRICED_COUNT={final_report.get('TOP_PRICED_COUNT')}; board={priced}."))
    if _int_or_none(final_report.get("TOP_PARTIALLY_PRICED_COUNT")) != partial:
        issues.append(ConsistencyIssue("TOP_PARTIAL_COUNT_MISMATCH", BLOCK, f"Report TOP_PARTIALLY_PRICED_COUNT={final_report.get('TOP_PARTIALLY_PRICED_COUNT')}; board={partial}."))
    if _int_or_none(final_report.get("TOP_UNPRICED_COUNT")) != unpriced:
        issues.append(ConsistencyIssue("TOP_UNPRICED_COUNT_MISMATCH", BLOCK, f"Report TOP_UNPRICED_COUNT={final_report.get('TOP_UNPRICED_COUNT')}; board={unpriced}."))
    if _int_or_none(final_report.get("BET_BUILDER_CONCEPTS_COUNT")) != len(bet_builder_concepts):
        issues.append(ConsistencyIssue("BET_BUILDER_COUNT_MISMATCH", BLOCK, f"Report BET_BUILDER_CONCEPTS_COUNT={final_report.get('BET_BUILDER_CONCEPTS_COUNT')}; concepts={len(bet_builder_concepts)}."))
    if _int_or_none(final_report.get("ANALYSIS_PORTFOLIO_DRAFTS_COUNT")) != len(analysis_portfolios):
        issues.append(ConsistencyIssue("PORTFOLIO_COUNT_MISMATCH", BLOCK, f"Report ANALYSIS_PORTFOLIO_DRAFTS_COUNT={final_report.get('ANALYSIS_PORTFOLIO_DRAFTS_COUNT')}; portfolios={len(analysis_portfolios)}."))
    if _int_or_none(final_report.get("OPTIONAL_OPERATOR_QUOTE_SHORTLIST_COUNT")) != len(optional_quote_shortlist):
        issues.append(ConsistencyIssue("QUOTE_SHORTLIST_COUNT_MISMATCH", BLOCK, f"Report OPTIONAL_OPERATOR_QUOTE_SHORTLIST_COUNT={final_report.get('OPTIONAL_OPERATOR_QUOTE_SHORTLIST_COUNT')}; shortlist={len(optional_quote_shortlist)}."))

    if daily_certification:
        declared = _declared_wimbledon_count(daily_certification)
        source = _declared_wimbledon_count(final_report)
        if declared is not None and source is not None and declared != source:
            issues.append(ConsistencyIssue("WIMBLEDON_DECLARATION_MISMATCH", BLOCK, f"Daily certification Wimbledon count={declared}; final report={source}."))

    if wimbledon_audit:
        audited = _int_or_none(_get(wimbledon_audit, "wimbledon_singles_quote_cards", "WIMBLEDON_SINGLES_QUOTE_CARDS"))
        declared = _declared_wimbledon_count(final_report)
        if audited is not None and declared is not None and audited != declared:
            issues.append(ConsistencyIssue("WIMBLEDON_AUDIT_MISMATCH", BLOCK, f"Wimbledon audit={audited}; final report={declared}."))

    for idx, concept in enumerate(bet_builder_concepts):
        concept_id = concept.get("concept_id") or f"#{idx}"
        if concept.get("combined_odds_status") != "OPERATOR_SCREEN_ONLY":
            issues.append(ConsistencyIssue("CONCEPT_COMBINED_STATUS_INVALID", BLOCK, f"Concept {concept_id} combined_odds_status={concept.get('combined_odds_status')}"))
        if concept.get("combined_bookmaker_odds_computed") is not False:
            issues.append(ConsistencyIssue("CONCEPT_COMBINED_ODDS_NOT_FALSE", BLOCK, f"Concept {concept_id} computed combined odds."))
        if concept.get("bettable") is not False:
            issues.append(ConsistencyIssue("CONCEPT_BETTABLE_TRUE", BLOCK, f"Concept {concept_id} is bettable."))

    for portfolio in analysis_portfolios:
        portfolio_id = portfolio.get("portfolio_id") or "UNKNOWN_PORTFOLIO"
        if str(portfolio.get("style")) not in _ALLOWED_ANALYSIS_PORTFOLIO_STYLES:
            issues.append(ConsistencyIssue("PORTFOLIO_STYLE_INVALID", BLOCK, f"Portfolio {portfolio_id} style={portfolio.get('style')}"))
        if portfolio.get("bettable") is not False:
            issues.append(ConsistencyIssue("PORTFOLIO_BETTABLE_TRUE", BLOCK, f"Portfolio {portfolio_id} is bettable."))
        if portfolio.get("final_coupon_allowed") is not False:
            issues.append(ConsistencyIssue("PORTFOLIO_FINAL_COUPON_ALLOWED", BLOCK, f"Portfolio {portfolio_id} allows final coupon."))
        if portfolio.get("combined_odds") is not None:
            issues.append(ConsistencyIssue("PORTFOLIO_COMBINED_ODDS_PRESENT", BLOCK, f"Portfolio {portfolio_id} has combined_odds."))

    for item in optional_quote_shortlist:
        if item.get("manual_quote_entry_required_for_analysis") not in {None, False}:
            issues.append(ConsistencyIssue(
                "SHORTLIST_REQUIRES_ANALYSIS_QUOTES",
                BLOCK,
                "Optional quote shortlist must not declare manual quote entry required for analysis.",
            ))

    for idx, group in enumerate(builder_groups or []):
        group_id = group.get("group_id") or f"#{idx}"
        if not group.get("sport"):
            issues.append(ConsistencyIssue("BUILDER_GROUP_SPORT_MISSING", BLOCK, f"Builder group {group_id} lacks sport."))
        if not group.get("event_id"):
            issues.append(ConsistencyIssue("BUILDER_GROUP_EVENT_ID_MISSING", BLOCK, f"Builder group {group_id} lacks event_id."))
        if group.get("combined_bookmaker_odds_computed") is not False:
            issues.append(ConsistencyIssue("BUILDER_GROUP_COMBINED_ODDS_NOT_FALSE", BLOCK, f"Builder group {group_id} has invalid combined odds flag."))

    return ConsistencyReport(ok=not any(issue.severity == BLOCK for issue in issues), issues=issues)


def scan_artifact_hygiene(run_root: Path) -> ConsistencyReport:
    issues: list[ConsistencyIssue] = []
    if not run_root.exists():
        return ConsistencyReport(False, [ConsistencyIssue("RUN_ROOT_MISSING", BLOCK, f"{run_root} does not exist")])
    nested_absolute_like: list[str] = []
    for path in run_root.rglob("*"):
        rel = str(path.relative_to(run_root))
        if rel.startswith("Users/") or "/Users/" in rel or rel.startswith("private/") or rel.startswith("var/folders/"):
            nested_absolute_like.append(rel)
    if nested_absolute_like:
        issues.append(ConsistencyIssue("NESTED_ABSOLUTE_PATH_ARTIFACTS", BLOCK, f"Run contains {len(nested_absolute_like)} nested absolute-path artifacts."))
    pycache = [str(path.relative_to(run_root)) for path in run_root.rglob("__pycache__")]
    pyc_files = [str(path.relative_to(run_root)) for path in run_root.rglob("*.pyc")]
    ds_store = [str(path.relative_to(run_root)) for path in run_root.rglob(".DS_Store")]
    if pycache or pyc_files:
        issues.append(ConsistencyIssue("PYCACHE_IN_EVIDENCE", WARN, f"Evidence contains {len(pycache)} __pycache__ dirs and {len(pyc_files)} .pyc files."))
    if ds_store:
        issues.append(ConsistencyIssue("DS_STORE_IN_EVIDENCE", WARN, f"Evidence contains {len(ds_store)} .DS_Store files."))
    return ConsistencyReport(ok=not any(issue.severity == BLOCK for issue in issues), issues=issues)
