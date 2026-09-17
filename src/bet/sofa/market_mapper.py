import re
import unicodedata

def fold(text: str | None) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")

MATCH_MARKET_NAMES = {
    "liczba goli": "goals_total",
    "liczba rzutow roznych": "corners_total",
    "liczba kartek": "cards_points_total",
    "liczba celnych strzalow": "shots_on_target_total",
    "liczba strzalow": "shots_total",
    "liczba spalonych": "offsides_total",
    "liczba fauli": "fouls_total",
    "1.polowa - liczba goli": "goals_1h_total",
    "1. polowa - liczba goli": "goals_1h_total",
    "2.polowa - liczba goli": "goals_2h_total",
    "2. polowa - liczba goli": "goals_2h_total",
    "liczba asow": "aces_total",
    "liczba podwojnych bledow": "double_faults_total",
    "liczba gemow": "games_total", 
    "liczba setow": "sets_total",
}

TEAM_MARKET_PATTERNS = [
    (re.compile(r"^(?P<team>.+?) - liczba rzutow roznych$"), "corners_for"),
    (re.compile(r"^(?P<team>.+?) - liczba kartek$"), "cards_points_for"),
    (re.compile(r"^(?P<team>.+?) - liczba goli$"), "goals_for"),
    (re.compile(r"^liczba celnych strzalow - (?P<team>.+?)$"), "shots_on_target_for"),
    (re.compile(r"^liczba strzalow (?P<team>.+?)$"), "shots_for"),
    (re.compile(r"^liczba fauli - (?P<team>.+?)$"), "fouls_for"),
    (re.compile(r"^spalone - (?P<team>.+?)$"), "offsides_for"),
    (re.compile(r"^(?P<team>.+?) liczba asow$"), "aces_for"),
    (re.compile(r"^(?P<team>.+?) liczba podwojnych bledow$"), "double_faults_for"),
    (re.compile(r"^(?P<team>.+?) - liczba gemow$"), "games_won_for"),
]

def classify_market(market_name: str | None) -> str | None:
    folded = fold(market_name)
    if not folded:
        return None
    if folded in MATCH_MARKET_NAMES:
        return MATCH_MARKET_NAMES[folded]
    for pattern, market in TEAM_MARKET_PATTERNS:
        if pattern.match(folded):
            return market
    return None
