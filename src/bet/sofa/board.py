import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from bet.sofa.contracts import BoardFixture, Sport
from bet.sofa.superbet import SPORT_BY_ID, SuperbetClient, split_match_name


def fetch_board(
    date_str: str, client: SuperbetClient | None = None
) -> list[BoardFixture]:
    """Fetch board fixtures for a given UTC date (YYYY-MM-DD)."""
    if client is None:
        client = SuperbetClient()

    window_start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
    window_end = window_start + timedelta(days=1)

    rows = client.events_by_date(window_start, window_end, offer_state="all")
    fixtures: list[BoardFixture] = []
    excluded = load_excluded_tournament_ids()
    skipped_by_exclusion = 0

    for row in rows:
        sport_id = row.get("sportId")
        if sport_id not in SPORT_BY_ID:
            continue

        sport: Sport = SPORT_BY_ID[sport_id]  # type: ignore[assignment]

        match_name = row.get("matchName") or ""

        if sport == "tennis" and "/" in match_name:
            continue  # doubles

        side_a, side_b = split_match_name(match_name)
        if not side_a or not side_b:
            continue

        raw_utc_date = str(row.get("utcDate") or "")
        try:
            kickoff_utc = datetime.fromisoformat(
                raw_utc_date.replace("Z", "+00:00")
            ).astimezone(UTC)
        except ValueError:
            continue

        if kickoff_utc.strftime("%Y-%m-%d") != date_str:
            continue

        event_id = row.get("eventId")
        if event_id is None:
            continue

        tournament_id = row.get("tournamentId")
        tournament_id = int(tournament_id) if tournament_id is not None else None
        if tournament_id is not None and tournament_id in excluded:
            skipped_by_exclusion += 1
            continue

        category_id = row.get("categoryId")

        fixtures.append(
            BoardFixture(
                superbet_event_id=str(event_id),
                sport=sport,
                match_name=match_name,
                side_a=side_a,
                side_b=side_b,
                kickoff_utc=kickoff_utc,
                tournament_id=tournament_id,
                category_id=int(category_id) if category_id is not None else None,
            )
        )

    if skipped_by_exclusion:
        print(
            f"BOARD: {skipped_by_exclusion} fixture(s) excluded by "
            f"config/sofa_board_exclusions.json",
            file=sys.stderr,
            flush=True,
        )
    return fixtures


def load_excluded_tournament_ids() -> set[int]:
    """Superbet tournament ids the operator has decided not to pay for (F12).

    Sofascore keeps no half-time statistics for youth and lowest-division
    competitions, so a fixture there can never produce half the markets, and
    the pipeline pays full price in requests for it.

    Measured before seeding this list, and the measurement matters: of the 290
    football fixtures on the 2026-09-18 board, 256 were in competitions with
    >=90% half coverage, 27 between 50% and 90%, 5 below 50%, and **none at
    0%**. The zero-coverage competitions the finding named — Liga 4 Teleorman,
    Campionatul National U19, Liga Elitelor U17 — turned up in the opponents'
    *historical samples*, not on the board itself. So the list ships empty: an
    exclusion nobody measured is a coverage cut disguised as a saving.

    The mechanism is here so ids can be added from evidence without a code
    change, and BoardFixture.tournament_id is recorded so the evidence can be
    gathered from the artifact rather than a live probe.
    """
    path = Path("config/sofa_board_exclusions.json")
    if not path.exists():
        return set()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    ids = loaded.get("superbet_tournament_ids") if isinstance(loaded, dict) else None
    if not isinstance(ids, list):
        return set()
    return {int(i) for i in ids if isinstance(i, int)}
