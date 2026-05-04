"""Polish market translations and Betclic navigation hints."""

MARKET_PL: dict[str, str] = {
    "Corners Total O/U": "Rzuty rożne łącznie",
    "Fouls Total O/U": "Faule łącznie",
    "Cards Total O/U": "Kartki łącznie",
    "Shots Total O/U": "Strzały łącznie",
    "Shots on Target Total O/U": "Strzały celne łącznie",
    "Goals Total O/U": "Bramki łącznie",
    "Total Games O/U": "Gemy łącznie",
    "Total Sets O/U": "Sety łącznie",
    "Total Points O/U": "Punkty łącznie",
    "Total Frames O/U": "Frejmy łącznie",
    "Total Runs O/U": "Rundy łącznie",
    "Total Maps O/U": "Mapy łącznie",
    "Total 180s O/U": "180-tki łącznie",
    "Total Legs O/U": "Legi łącznie",
    "Total Goals O/U": "Bramki łącznie",
    "Total Rebounds O/U": "Zbiórki łącznie",
    "Total Aces O/U": "Asy łącznie",
    "Total Assists O/U": "Asysty łącznie",
    "Total Steals O/U": "Przechwyty łącznie",
    "Total Turnovers O/U": "Straty łącznie",
    "Total Shots O/U": "Strzały łącznie",
    "Total PIM O/U": "Minuty karne łącznie",
    "Total Hits O/U": "Hity łącznie",
    "Total Blocks O/U": "Bloki łącznie",
    "Total Double Faults O/U": "Podwójne błędy łącznie",
    "Total Centuries O/U": "Centurie łącznie",
    "Total 50+ Breaks O/U": "Breaki 50+ łącznie",
    "Total Errors O/U": "Błędy łącznie",
    "Total Saves O/U": "Obrony łącznie",
    "Total Suspensions O/U": "Wykluczenia łącznie",
    "Total Penalties O/U": "Kary łącznie",
    "Total Rounds O/U": "Rundy łącznie",
    "Total Significant Strikes O/U": "Celne uderzenia łącznie",
    "Total Takedowns O/U": "Obalenia łącznie",
    "Total Kills O/U": "Zabójstwa łącznie",
    "Total Strikeouts O/U": "Strikeouty łącznie",
    "Total Hits O/U": "Hity łącznie",
    "Total Home Runs O/U": "Home runy łącznie",
    "Total Walks O/U": "Spacery łącznie",
    "Total Heat Wins O/U": "Wygrane biegi łącznie",
    "Break Points Total O/U": "Break pointy łącznie",
    "Total Break Points O/U": "Break pointy łącznie",
    "Team A Corners O/U": "Rzuty rożne drużyny",
    "Team B Corners O/U": "Rzuty rożne drużyny",
    "Team A Fouls O/U": "Faule drużyny",
    "Team B Fouls O/U": "Faule drużyny",
    "Team A Cards O/U": "Kartki drużyny",
    "Team B Cards O/U": "Kartki drużyny",
    "Team A Shots O/U": "Strzały drużyny",
    "Team B Shots O/U": "Strzały drużyny",
    "Team A Shots on Target O/U": "Strzały celne drużyny",
    "Team B Shots on Target O/U": "Strzały celne drużyny",
    "Team A Points O/U": "Punkty drużyny",
    "Team B Points O/U": "Punkty drużyny",
    "Team A Rebounds O/U": "Zbiórki drużyny",
    "Team B Rebounds O/U": "Zbiórki drużyny",
    "Team A Assists O/U": "Asysty drużyny",
    "Team B Assists O/U": "Asysty drużyny",
    "Team A Runs O/U": "Rundy drużyny",
    "Team B Runs O/U": "Rundy drużyny",
    "Team A Goals O/U": "Bramki drużyny",
    "Team B Goals O/U": "Bramki drużyny",
    "Team A Maps O/U": "Mapy drużyny",
    "Team B Maps O/U": "Mapy drużyny",
    "Team A Rounds O/U": "Rundy drużyny",
    "Team B Rounds O/U": "Rundy drużyny",
    "Player A Games O/U": "Gemy zawodnika",
    "Player B Games O/U": "Gemy zawodnika",
    "Player A Aces O/U": "Asy zawodnika",
    "Player B Aces O/U": "Asy zawodnika",
    "Player A Frames O/U": "Frejmy zawodnika",
    "Player B Frames O/U": "Frejmy zawodnika",
    "Player A Legs O/U": "Legi zawodnika",
    "Player B Legs O/U": "Legi zawodnika",
    "Player A 180s O/U": "180-tki zawodnika",
    "Player B 180s O/U": "180-tki zawodnika",
    "Player A Sets O/U": "Sety zawodnika",
    "Player B Sets O/U": "Sety zawodnika",
    "Pair A Games O/U": "Gemy pary",
    "Pair B Games O/U": "Gemy pary",
    "Fighter A Sig Strikes O/U": "Celne uderzenia zawodnika",
    "Fighter B Sig Strikes O/U": "Celne uderzenia zawodnika",
    "Match Winner": "Zwycięzca meczu",
    "1X2": "1X2",
    "Double Chance": "Podwójna szansa",
    "Draw No Bet": "Remis bez zakładu",
    "BTTS": "Obie strzelą",
    "Handicap": "Handicap",
    "Set Handicap": "Handicap setowy",
    "Game Handicap": "Handicap gemowy",
}

DIRECTION_PL: dict[str, str] = {
    "OVER": "powyżej",
    "UNDER": "poniżej",
}

SPORT_EMOJI: dict[str, str] = {
    "football": "⚽",
    "basketball": "🏀",
    "tennis": "🎾",
    "volleyball": "🏐",
    "hockey": "🏒",
    "baseball": "⚾",
    "handball": "🤾",
    "esports": "🎮",
    "snooker": "🎱",
    "table_tennis": "🏓",
    "darts": "🎯",
    "mma": "🥊",
    "padel": "🏸",
    "speedway": "🏍️",
}

# Market category mapping for Betclic navigation
_MARKET_CATEGORY: dict[str, str] = {
    "corners": "Statystyki → Rzuty rożne",
    "fouls": "Statystyki → Faule",
    "cards": "Statystyki → Kartki",
    "shots": "Statystyki → Strzały",
    "goals": "Bramki",
    "points": "Punkty",
    "sets": "Sety",
    "games": "Gemy",
    "frames": "Frejmy",
    "maps": "Mapy",
    "rounds": "Rundy",
    "legs": "Legi",
    "aces": "Asy",
    "rebounds": "Zbiórki",
    "180s": "180-tki",
}

_SPORT_PL: dict[str, str] = {
    "football": "Piłka nożna",
    "basketball": "Koszykówka",
    "tennis": "Tenis",
    "volleyball": "Siatkówka",
    "hockey": "Hokej",
    "snooker": "Snooker",
    "speedway": "Żużel",
    "handball": "Piłka ręczna",
    "baseball": "Baseball",
    "esports": "Esport",
    "darts": "Darts",
    "table_tennis": "Tenis stołowy",
    "mma": "MMA",
    "padel": "Padel",
}


def translate_market(
    market_name: str, direction: str, line: float, team_name: str = ""
) -> str:
    """Build Polish market description for Betclic.

    E.g., 'Rzuty rożne łącznie Powyżej 9.5'
    """
    base = MARKET_PL.get(market_name, market_name)
    dir_pl = DIRECTION_PL.get(direction.upper(), direction)
    line_str = f"{line:g}"

    if team_name and ("Team A" in market_name or "Team B" in market_name
                      or "Player A" in market_name or "Player B" in market_name
                      or "Pair A" in market_name or "Pair B" in market_name
                      or "Fighter A" in market_name or "Fighter B" in market_name):
        return f"{base} ({team_name}) {dir_pl.capitalize()} {line_str}"
    return f"{base} {dir_pl.capitalize()} {line_str}"


def betclic_navigation(
    sport: str,
    competition: str,
    home: str,
    away: str,
    market_category: str,
) -> str:
    """Generate Betclic app navigation hint.

    E.g., 'Piłka nożna → Premier League → Liverpool-Arsenal → Statystyki → Rzuty rożne'
    """
    sport_pl = _SPORT_PL.get(sport, sport.capitalize())
    nav_suffix = _MARKET_CATEGORY.get(market_category, market_category)
    return f"{sport_pl} → {competition} → {home}-{away} → {nav_suffix}"
