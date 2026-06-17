import json
import sqlite3
from typing import Dict, List

from bet.enrichment.football.contracts import FootballMetricSample, FootballSide
from bet.enrichment.football.time import format_utc, parse_canonical_or_offset_datetime, require_aware_datetime


class FootballHistoryRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_eligible_observations_by_team(
        self,
        target_canonical_fixture_id: int,
        analysis_cutoff_at: str | None,
        metrics: list[str],
        accepted_statuses: list[str]
    ) -> Dict[int, List[FootballMetricSample]]:

        target_row = self.conn.execute(
            "SELECT home_team_id, away_team_id FROM fixtures WHERE id = ?",
            (target_canonical_fixture_id,)
        ).fetchone()

        if not target_row:
            return {}

        home_team_id, away_team_id = target_row
        target_teams = (home_team_id, away_team_id)

        if not analysis_cutoff_at:
            return {home_team_id: [], away_team_id: []}

        cutoff_dt = parse_canonical_or_offset_datetime(analysis_cutoff_at)
        cutoff_str = format_utc(cutoff_dt)

        if not accepted_statuses:
            return {home_team_id: [], away_team_id: []}

        status_placeholders = ",".join("?" for _ in accepted_statuses)

        query = f"""
            WITH EligibleObs AS (
                SELECT
                    o.id,
                    o.canonical_fixture_id,
                    o.team_id,
                    o.native_fixture_id,
                    o.native_team_id,
                    o.evidence_bundle_id,
                    o.payload_json,
                    o.logical_identity,
                    o.observed_at,
                    f.kickoff,
                    f.home_team_id,
                    f.away_team_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY o.canonical_fixture_id, o.team_id
                        ORDER BY o.observed_at DESC, o.logical_identity DESC
                    ) as rn
                FROM fixture_capability_observation o
                JOIN fixtures f ON o.canonical_fixture_id = f.id
                WHERE o.capability = 'TEAM_MATCH_FACTS'
                  AND o.source = 'api-football'
                  AND o.status IN ({status_placeholders})
                  AND o.team_id IN (?, ?)
                  AND f.id != ?
                  AND f.status IN ('finished', 'FT', 'AET', 'PEN')
                  AND f.kickoff < ?
                  AND o.valid_at <= ?
            )
            SELECT
                id, canonical_fixture_id, team_id, native_fixture_id, native_team_id,
                evidence_bundle_id, payload_json, logical_identity, observed_at,
                kickoff, home_team_id, away_team_id
            FROM EligibleObs
            WHERE rn = 1
            ORDER BY kickoff DESC, native_fixture_id DESC
        """

        params = [
            *accepted_statuses,
            home_team_id, away_team_id,
            target_canonical_fixture_id,
            cutoff_str, cutoff_str
        ]

        rows = self.conn.execute(query, params).fetchall()

        samples: Dict[int, List[FootballMetricSample]] = {home_team_id: [], away_team_id: []}
        for row in rows:
            (obs_id, can_fix_id, t_id, n_fix_id, n_team_id, ev_bundle,
             payload_json, logical_id, obs_at_str, kickoff_str, h_t_id, a_t_id) = row

            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                continue

            kickoff_dt = parse_canonical_or_offset_datetime(kickoff_str)
            obs_dt = parse_canonical_or_offset_datetime(obs_at_str)

            # Use data directly from the team payload, as requested
            side_str = payload.get("side", "")
            if side_str == "HOME":
                side = FootballSide.HOME
            elif side_str == "AWAY":
                side = FootballSide.AWAY
            else:
                side = FootballSide.HOME if t_id == h_t_id else FootballSide.AWAY

            opp_prov = payload.get("provider_opponent_team_id", "")
            if not opp_prov:
                continue

            for m in metrics:
                val = payload.get(m)
                if val is not None:
                    samples[t_id].append(FootballMetricSample(
                        provider_fixture_id=n_fix_id,
                        provider_opponent_team_id=opp_prov,
                        kickoff_at=kickoff_dt,
                        side=side,
                        metric=m,
                        value=float(val),
                        observation_logical_identity=logical_id or "",
                        evidence_bundle_ids=(ev_bundle,) if ev_bundle else (),
                        observed_at=obs_dt
                    ))

        return samples
