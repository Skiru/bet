# ruff: noqa: E501
import json
import sqlite3

from bet.enrichment.football.contracts import FootballMetricSample, FootballSide
from bet.enrichment.football.time import (
    format_utc,
    parse_canonical_or_offset_datetime,
)


class FootballHistoryRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_eligible_observations_by_team(
        self,
        target_canonical_fixture_id: int,
        analysis_cutoff_at,
        metrics: list[str],
        accepted_statuses: list[str]
    ) -> dict[int, list[FootballMetricSample]]:

        target_row = self.conn.execute(
            "SELECT home_team_id, away_team_id FROM fixtures WHERE id = ?",
            (target_canonical_fixture_id,)
        ).fetchone()

        if not target_row:
            return {}

        home_team_id, away_team_id = target_row

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
                  AND o.observed_at <= ?
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

        samples: dict[int, list[FootballMetricSample]] = {home_team_id: [], away_team_id: []}
        for row in rows:
            (obs_id, can_fix_id, t_id, n_fix_id, n_team_id, ev_bundle,
             payload_json, logical_id, obs_at_str, kickoff_str, h_t_id, a_t_id) = row

            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                continue

            kickoff_dt = parse_canonical_or_offset_datetime(kickoff_str)
            obs_dt = parse_canonical_or_offset_datetime(obs_at_str)

            # Determine flat or nested payload
            opp_prov = payload.get("provider_opponent_team_id", "")
            side_str = payload.get("side", "")

            # Nested legacy payload support
            side_data = {}
            if not opp_prov and ("home" in payload or "away" in payload):
                home_prov = payload.get("fixture", {}).get("home_provider_team_id", "")
                away_prov = payload.get("fixture", {}).get("away_provider_team_id", "")
                if t_id == h_t_id:
                    opp_prov = away_prov
                    side_str = "HOME"
                    side_data = payload.get("home", {})
                else:
                    opp_prov = home_prov
                    side_str = "AWAY"
                    side_data = payload.get("away", {})

            if not opp_prov:
                continue

            if side_str == "HOME":
                side = FootballSide.HOME
            elif side_str == "AWAY":
                side = FootballSide.AWAY
            else:
                side = FootballSide.HOME if t_id == h_t_id else FootballSide.AWAY

            for m in metrics:
                val = payload.get(m)
                if val is None and side_data:
                    val = side_data.get(m)

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
