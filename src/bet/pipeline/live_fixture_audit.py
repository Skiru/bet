from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from bet.pipeline.analysis_status import has_explicit_test_provenance

WARSAW = ZoneInfo("Europe/Warsaw")


def _parse_aware(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing {label}")
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed


def _get_run_clock() -> datetime:
    val = os.environ.get("BET_PIPELINE_RUN_AS_OF_UTC")
    if val:
        try:
            return _parse_aware(val, "BET_PIPELINE_RUN_AS_OF_UTC")
        except Exception:
            raise ValueError("invalid BET_PIPELINE_RUN_AS_OF_UTC")
    raise ValueError("missing BET_PIPELINE_RUN_AS_OF_UTC")


class LiveFixtureAudit:
    def __init__(self, target_date: str):
        self.target_date = target_date

    def audit_candidate(self, candidate: dict[str, Any]) -> tuple[str, str]:
        """Audit a single candidate. Returns (status, reason)."""
        if has_explicit_test_provenance(candidate):
            return "REJECTED_TEST_OR_SYNTHETIC_FIXTURE", "Candidate has explicit test provenance"

        betting_day = candidate.get("betting_day")
        if betting_day and betting_day != self.target_date:
            return "REJECTED_WRONG_BETTING_DAY", f"Candidate betting day {betting_day} does not match target {self.target_date}"

        kickoff_str = candidate.get("kickoff") or candidate.get("start_time") or ""
        if not kickoff_str:
            return "REJECTED_UNVERIFIED_FIXTURE_IDENTITY", "Missing kickoff timestamp"

        try:
            kickoff_dt = _parse_aware(kickoff_str, "kickoff")
            now_dt = _get_run_clock()
            if kickoff_dt <= now_dt:
                return "REJECTED_ALREADY_STARTED", f"Kickoff {kickoff_str} is in the past relative to current time {now_dt.isoformat()}"

            kickoff_date_warsaw = kickoff_dt.astimezone(WARSAW).strftime("%Y-%m-%d")
            if kickoff_date_warsaw != self.target_date:
                return "REJECTED_WRONG_BETTING_DAY", f"Kickoff date {kickoff_date_warsaw} does not match target {self.target_date}"
        except Exception as e:
            return "REJECTED_UNVERIFIED_FIXTURE_IDENTITY", f"Failed to parse kickoff timestamp: {e}"

        home_team = candidate.get("home_team") or candidate.get("participant_a")
        away_team = candidate.get("away_team") or candidate.get("participant_b")
        if not home_team or not away_team:
            return "REJECTED_PARTICIPANT_MISMATCH", "Missing home_team or away_team"

        as_of = candidate.get("probability_as_of") or candidate.get("stats_as_of")
        try:
            as_of_dt = _parse_aware(as_of, "candidate source as_of")
            now_dt = _get_run_clock()
            age_hours = (now_dt - as_of_dt).total_seconds() / 3600.0
            if age_hours < 0:
                return "REJECTED_UNVERIFIED_FIXTURE_IDENTITY", "Candidate source as_of is in the future"
            if age_hours > 24.0:
                return "REJECTED_STALE_FIXTURE", f"Source artifact is stale (age: {age_hours:.1f} hours > 24h TTL)"
        except Exception as exc:
            return "REJECTED_UNVERIFIED_FIXTURE_IDENTITY", f"Invalid candidate source timestamp: {exc}"

        verification = candidate.get("fixture_verification")
        if not isinstance(verification, dict):
            return "REJECTED_UNVERIFIED_FIXTURE_IDENTITY", "Missing source-bound fixture_verification evidence"
        if verification.get("status") != "LIVE_FIXTURE_VERIFIED_NOT_STARTED":
            return "REJECTED_UNVERIFIED_FIXTURE_IDENTITY", "Fixture verification status is not verified/not-started"
        if not str(verification.get("source") or "").strip():
            return "REJECTED_UNVERIFIED_FIXTURE_IDENTITY", "Fixture verification source is missing"
        try:
            verified_at = _parse_aware(verification.get("verified_at_utc"), "fixture verified_at_utc")
        except Exception as exc:
            return "REJECTED_UNVERIFIED_FIXTURE_IDENTITY", str(exc)
        if verified_at > now_dt or (now_dt - verified_at).total_seconds() > 3600:
            return "REJECTED_STALE_FIXTURE", "Fixture verification is future-dated or older than one hour"
        expected_event_id = candidate.get("canonical_event_id") or candidate.get("event_id")
        if not expected_event_id or verification.get("canonical_event_id") != expected_event_id:
            return "REJECTED_UNVERIFIED_FIXTURE_IDENTITY", "Fixture verification event identity mismatch"

        return "LIVE_FIXTURE_VERIFIED_NOT_STARTED", "PASS"

    def assign_tiers(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Score and assign tiers to candidates."""
        scored_candidates = []
        for c in candidates:
            score = 0.0
            prob = c.get("model_probability") or c.get("probability")
            if prob is not None:
                prob_val = float(prob)
                score += prob_val * 10.0

            hydration = str(c.get("hydration_status") or "").upper()
            sample_size = max(
                len(c.get("team_a_l10") or []),
                len(c.get("team_b_l10") or [])
            )

            is_minimal = (hydration == "MINIMAL_HYDRATION")
            is_tiny_sample = (sample_size < 5)
            is_small_sample = (sample_size < 8)

            if is_minimal:
                c["risk_label"] = "MINIMAL_HYDRATION_HIGH_UNCERTAINTY"
                score -= 3.0
            else:
                c["risk_label"] = "STANDARD_HYDRATION"

            dq = c.get("data_quality") or {}
            dq_label = str(dq.get("label") or "").upper()
            if dq_label == "HIGH":
                score += 2.0
            elif dq_label == "MEDIUM":
                score += 1.0
            elif dq_label == "MINIMAL":
                score -= 1.0

            best_market = c.get("best_market") or {}
            safety = float(best_market.get("safety_score") or c.get("safety_score") or 0.0)
            score += safety * 5.0

            c["review_score"] = round(score, 2)

            if is_tiny_sample or is_minimal:
                tier = "C_WATCHLIST_ONLY"
            elif is_small_sample:
                tier = "B_MANUAL_QUOTE_SECONDARY"
            elif score >= 7.5:
                tier = "A_MANUAL_QUOTE_PRIORITY"
            elif score >= 5.0:
                tier = "B_MANUAL_QUOTE_SECONDARY"
            else:
                tier = "C_WATCHLIST_ONLY"

            c["review_tier"] = tier
            scored_candidates.append(c)

        scored_candidates.sort(key=lambda x: x.get("review_score", 0.0), reverse=True)

        a_count = 0
        ab_count = 0
        final_candidates = []

        for c in scored_candidates:
            tier = c["review_tier"]
            if tier == "A_MANUAL_QUOTE_PRIORITY":
                if a_count < 12 and ab_count < 25:
                    a_count += 1
                    ab_count += 1
                else:
                    c["review_tier"] = "B_MANUAL_QUOTE_SECONDARY"
                    if ab_count < 25:
                        ab_count += 1
                    else:
                        c["review_tier"] = "C_WATCHLIST_ONLY"
            elif tier == "B_MANUAL_QUOTE_SECONDARY":
                if ab_count < 25:
                    ab_count += 1
                else:
                    c["review_tier"] = "C_WATCHLIST_ONLY"
            final_candidates.append(c)

        return final_candidates
