import json
import sqlite3
from datetime import UTC, datetime

from bet.enrichment.football.contracts import FootballMetricSample, FootballSide


class FootballHistoryRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_eligible_observations_by_team(
        self,
        target_canonical_fixture_id: int,
        analysis_cutoff_at: datetime,
        metrics: list[str],
        accepted_statuses: list[str]
    ) -> dict[int, list[FootballMetricSample]]:

        # We need ALL eligible historical observations for the teams involved in the target fixture.
        # But wait, which teams? We need home and away team of the target fixture.
        target_row = self.conn.execute(
            "SELECT home_team_id, away_team_id FROM fixtures WHERE id = ?",
            (target_canonical_fixture_id,)
        ).fetchone()

        if not target_row:
            return []

        home_team_id, away_team_id = target_row
        target_teams = (home_team_id, away_team_id)

        cutoff_str = analysis_cutoff_at.isoformat()

        # Query observations where team is one of target_teams,
        # fixture kickoff < cutoff, observed_at <= cutoff, fixture is finished, target is excluded

        # We only want the *latest eligible revision* per fixture/team.
        # "Each fixture is one database transaction... Append a new observation... update sports_sync_item"
        # We group by (canonical_fixture_id, team_id) and take the one with highest id.

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
                        ORDER BY o.id DESC
                    ) as rn
                FROM fixture_capability_observation o
                JOIN fixtures f ON o.canonical_fixture_id = f.id
                WHERE o.capability = 'TEAM_MATCH_FACTS'
                  AND o.source = 'api-football'
                  AND o.status IN ({status_placeholders})
                  AND o.team_id IN (?, ?)
                  AND f.id != ?
                  AND f.status = 'finished'
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

        samples = {home_team_id: [], away_team_id: []}
        for row in rows:
            (obs_id, can_fix_id, t_id, n_fix_id, n_team_id, ev_bundle,
             payload_json, logical_id, obs_at_str, kickoff_str, h_t_id, a_t_id) = row

            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                continue

            kickoff_dt = datetime.fromisoformat(kickoff_str).astimezone(UTC)
            obs_dt = datetime.fromisoformat(obs_at_str).astimezone(UTC)

            side = FootballSide.HOME if t_id == h_t_id else FootballSide.AWAY

            # Opponent team ID based on payload or local?
            # The schema doesn't store native_opponent_team_id natively.
            # But the payload might not either, wait, facts has side, goals, etc.
            # Actually, the domain dto has home_provider_team_id and away_provider_team_id inside the fixture.
            # Let's extract from payload.
            fix_node = payload.get("fixture", {})
            h_prov = fix_node.get("home_provider_team_id", "")
            a_prov = fix_node.get("away_provider_team_id", "")
            if h_prov == n_team_id:
                opp_prov = a_prov
            else:
                opp_prov = h_prov

            team_node = payload.get("home", {}) if side == FootballSide.HOME else payload.get("away", {})

            for m in metrics:
                val = team_node.get(m)
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

