from __future__ import annotations

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
]

FBREF_LEAGUES = {
    "Big 5 European Leagues Combined": ("Europe", "Big 5"),
    "ENG-Premier League": ("England", "Premier League"),
    "ESP-La Liga": ("Spain", "La Liga"),
    "GER-Bundesliga": ("Germany", "Bundesliga"),
    "ITA-Serie A": ("Italy", "Serie A"),
    "FRA-Ligue 1": ("France", "Ligue 1"),
}

SPORT_SOURCE_MAP = {
    "football": ["fbref", "espn", "flashscore"],
    "basketball": ["nba-api", "basketball-reference", "espn", "flashscore"],
    "tennis": ["sackmann", "sofascore-tennis", "espn", "flashscore"],
    "hockey": ["nhl-api", "hockey-reference", "espn", "flashscore"],
    "volleyball": ["volleybox", "sofascore-volleyball", "espn", "flashscore"],
}

DEFAULT_RATE_DELAYS = {
    "fbref": (3.0, 6.0),
    "nba-api": (0.6, 1.5),
    "basketball-reference": (3.0, 5.0),
    "sackmann": (0.5, 1.0),
    "sofascore-tennis": (2.0, 4.0),
    "nhl-api": (1.0, 2.0),
    "hockey-reference": (3.0, 5.0),
    "volleybox": (3.0, 5.0),
    "sofascore-volleyball": (1.5, 3.0),
    "flashscore": (1.5, 3.0),
    "espn": (0.2, 0.5),
}

# NBA API season format
NBA_SEASONS = {
    "2425": "2024-25",
    "2324": "2023-24",
    "2223": "2022-23",
}

# Sackmann CSV URL templates
SACKMANN_ATP_URL = "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_matches_{year}.csv"
SACKMANN_WTA_URL = "https://raw.githubusercontent.com/JeffSackmann/tennis_wta/master/wta_matches_{year}.csv"
