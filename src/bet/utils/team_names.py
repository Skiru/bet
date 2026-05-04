"""Team name normalization and resolution utilities."""

import re
import unicodedata


def normalize_team_name(name: str) -> str:
    """Normalize team/player name for fuzzy matching across sources.

    Strips diacritics, removes common club suffixes (FC, SC, United, etc.),
    parenthetical qualifiers, and extra whitespace. Returns lowercase.
    """
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\s*\([^)]*\)\s*", " ", s)
    s = re.sub(
        r"\b(FC|SC|CF|CD|SK|FK|AS|AC|US|SS|SV|TSV|VfB|VfL|BSC|"
        r"IF|BK|IFK|AIK|FF|GIF|AFC|RFC|SFC|CFC|United|Utd|City|"
        r"Town|Rovers|Wanderers|Athletic|Athletico|Sporting)\b",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\s+", " ", s).strip()
    return s.lower()


def resolve_team(conn, name: str, sport_id: int) -> int:
    """Resolve a team name to a DB team ID, creating if needed.

    Uses normalize_team_name() for alias matching.
    Returns team.id.
    """
    from bet.db.repositories import TeamRepo

    repo = TeamRepo(conn)
    # Try exact match first
    team = repo.resolve(name, sport_id)
    if team:
        return team.id

    # Try normalized match against all teams in this sport
    normalized = normalize_team_name(name)
    rows = conn.execute(
        "SELECT id, name, aliases FROM teams WHERE sport_id = ?",
        (sport_id,),
    ).fetchall()

    import json

    for row in rows:
        if normalize_team_name(row["name"]) == normalized:
            # Add as alias for future lookups
            aliases = json.loads(row["aliases"])
            if name not in aliases:
                aliases.append(name)
                repo.update_aliases(row["id"], aliases)
            return row["id"]
        for alias in json.loads(row["aliases"]):
            if normalize_team_name(alias) == normalized:
                return row["id"]

    # Not found — create new team
    team = repo.find_or_create(name, sport_id)
    return team.id
