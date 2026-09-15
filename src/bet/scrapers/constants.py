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
    "tennis": ["sackmann", "espn", "flashscore"],
    "hockey": ["nhl-api", "hockey-reference", "espn", "flashscore"],
    "volleyball": ["volleybox", "espn", "flashscore"],
}

DEFAULT_RATE_DELAYS = {
    "fbref": (3.0, 6.0),
    "nba-api": (0.6, 1.5),
    "basketball-reference": (3.0, 5.0),
    "sackmann": (0.5, 1.0),
    "nhl-api": (1.0, 2.0),
    "hockey-reference": (3.0, 5.0),
    "volleybox": (3.0, 5.0),
    "flashscore": (1.5, 3.0),
    "espn": (0.2, 0.5),
}

# Per-scraper capabilities for shortlist scope (team_list in scrape_team_season_stats).
# True = scraper supports team_list kwarg, can limit to shortlist teams.
# False = scraper always fetches all teams for the competition.
SCRAPER_SCOPE_CAPABILITIES: dict[tuple[str, str], bool] = {
    ("football", "flashscore"): True,
    ("basketball", "flashscore"): True,
    ("tennis", "flashscore"): True,
    ("hockey", "flashscore"): True,
    ("volleyball", "flashscore"): True,
    # All other scrapers default to scope_unsupported (False).
}

# NBA API season format
NBA_SEASONS = {
    "2425": "2024-25",
    "2324": "2023-24",
    "2223": "2022-23",
}

# Sackmann-schema CSV URL templates. The original host --
# github.com/JeffSackmann/tennis_atp and tennis_wta -- 404'd at the
# *repository* level on 2026-08-28 (checked via the GitHub API; the account
# itself is alive). stats.tennismylife.org republishes the same schema
# (tourney_id, w_ace, w_df, w_svpt, ... -- verified column-for-column against
# JeffSackmann's original CSVs) under a live, MIT-licensed API, found and
# cross-checked against our own tennis-abstract sample 2026-09-15 (Nadia
# Podoroska's last 10 double-faults matched exactly on every overlapping
# match). It does not cover ITF or WTA Challenger -- only ATP (incl.
# Challenger, qualifying) and WTA Tour -- so it is a corroborator for those
# two, not a replacement for tennis-abstract.
SACKMANN_ATP_URL = "https://stats.tennismylife.org/data/{year}.csv"
SACKMANN_WTA_URL = "https://stats.tennismylife.org/data/{year}_wta.csv"
SACKMANN_ATP_CHALLENGER_URL = "https://stats.tennismylife.org/data/{year}_challenger.csv"
# "Ongoing" files hold matches from tournaments still in progress, folded
# into the main yearly file only once the event finishes -- this is where a
# match from earlier the same day or the day before actually is.
SACKMANN_ATP_ONGOING_URL = "https://stats.tennismylife.org/data/ongoing_tourneys.csv"
SACKMANN_WTA_ONGOING_URL = "https://stats.tennismylife.org/data/wta_ongoing_tourneys.csv"
SACKMANN_ATP_CHALLENGER_ONGOING_URL = "https://stats.tennismylife.org/data/challenger_ongoing_tourneys.csv"

# Kept for provenance only -- not fetched by anything. If tennismylife.org
# ever goes away, this is where the schema came from originally.
SACKMANN_ATP_URL_ORIGINAL = "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_matches_{year}.csv"
SACKMANN_WTA_URL_ORIGINAL = "https://raw.githubusercontent.com/JeffSackmann/tennis_wta/master/wta_matches_{year}.csv"
