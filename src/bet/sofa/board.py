from datetime import UTC, datetime, timedelta
from typing import Literal

from bet.sofa.contracts import BoardFixture, Sport
from bet.sofa.superbet import SPORT_BY_ID, SuperbetClient, split_match_name

def fetch_board(date_str: str, client: SuperbetClient | None = None) -> list[BoardFixture]:
    """Fetch board fixtures for a given UTC date (YYYY-MM-DD)."""
    if client is None:
        client = SuperbetClient()
        
    window_start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
    window_end = window_start + timedelta(days=1)
    
    rows = client.events_by_date(window_start, window_end, offer_state="all")
    fixtures: list[BoardFixture] = []
    
    for row in rows:
        sport_id = row.get("sportId")
        if sport_id not in SPORT_BY_ID:
            continue
            
        sport: Sport = SPORT_BY_ID[sport_id] # type: ignore[assignment]
        
        match_name = row.get("matchName") or ""
        
        if sport == "tennis" and "/" in match_name:
            continue  # doubles
            
        side_a, side_b = split_match_name(match_name)
        if not side_a or not side_b:
            continue
            
        raw_utc_date = str(row.get("utcDate") or "")
        try:
            kickoff_utc = datetime.fromisoformat(raw_utc_date.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            continue
            
        if kickoff_utc.strftime("%Y-%m-%d") != date_str:
            continue
            
        event_id = row.get("eventId")
        if event_id is None:
            continue
            
        fixtures.append(
            BoardFixture(
                superbet_event_id=str(event_id),
                sport=sport,
                match_name=match_name,
                side_a=side_a,
                side_b=side_b,
                kickoff_utc=kickoff_utc,
            )
        )
        
    return fixtures
